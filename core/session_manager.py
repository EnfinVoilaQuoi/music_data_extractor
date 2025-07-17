# core/session_manager.py - Version corrigée sans problèmes de freeze
import uuid
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable

from config.settings import settings
from models.entities import Session
from models.enums import SessionStatus  
from core.database import Database

# Import du gestionnaire de timezone
try:
    from utils.timezone_utils import now_france, to_france_timezone
    USE_FRANCE_TZ = True
except ImportError:
    # Fallback si le module n'existe pas encore
    def now_france():
        return datetime.now()
    def to_france_timezone(dt):
        return dt if dt else datetime.now()
    USE_FRANCE_TZ = False

class SessionManager:
    """Gestionnaire des sessions sans threading pour éviter les freezes"""
    
    def __init__(self, db: Optional[Database] = None, enable_threading: bool = False):
        self.db = db or Database()
        self.active_sessions: Dict[str, Session] = {}
        
        # Configuration
        self.auto_save_interval = settings.get('sessions.auto_save_interval', 60)
        self.max_sessions = settings.get('sessions.max_sessions', 20)
        self.cleanup_after_days = settings.get('sessions.cleanup_after_days', 30)
        
        # Threading DÉSACTIVÉ par défaut pour éviter les freezes
        self.enable_threading = enable_threading
        self._sessions_modified = set()
        self._last_activity_time = None
        
        # Threading optionnel (désactivé par défaut)
        self._auto_save_thread = None
        self._stop_auto_save = threading.Event()
        self._session_lock = threading.Lock() if enable_threading else None
        
        # Callbacks pour les événements
        self.event_callbacks: Dict[str, List[Callable]] = {
            'session_created': [],
            'session_updated': [],
            'session_completed': [],
            'session_failed': [],
            'session_paused': [],
            'session_resumed': []
        }
        
        # Initialisation
        self._load_active_sessions()
        
        # Auto-save seulement si threading explicitement activé
        if enable_threading and settings.get('sessions.enable_auto_save', False):
            self._start_auto_save()
        
        threading_msg = "avec threading" if enable_threading else "sans threading (stable)"
        print(f"✅ SessionManager initialisé {threading_msg}")
    
    def _get_current_time(self) -> datetime:
        """Retourne l'heure actuelle selon la configuration timezone"""
        return now_france() if USE_FRANCE_TZ else datetime.now()
    
    def _normalize_datetime(self, dt: Optional[datetime]) -> Optional[datetime]:
        """Normalise une datetime pour éviter les conflits timezone"""
        if dt is None:
            return None
        
        if USE_FRANCE_TZ:
            return to_france_timezone(dt)
        else:
            # Retirer la timezone pour éviter les conflits
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
    
    def _with_lock(self, func):
        """Exécute une fonction avec ou sans lock selon la configuration"""
        if self.enable_threading and self._session_lock:
            with self._session_lock:
                return func()
        else:
            return func()
    
    def _mark_session_modified(self, session_id: str):
        """Marque une session comme modifiée"""
        self._sessions_modified.add(session_id)
        self._last_activity_time = self._get_current_time()
    
    def _start_auto_save(self):
        """Démarre le thread de sauvegarde automatique (si threading activé)"""
        if not self.enable_threading:
            return
            
        if self._auto_save_thread and self._auto_save_thread.is_alive():
            return
        
        self._stop_auto_save.clear()
        self._auto_save_thread = threading.Thread(target=self._auto_save_worker, daemon=True)
        self._auto_save_thread.start()
        print(f"🔄 Auto-sauvegarde démarrée (intervalle: {self.auto_save_interval}s)")
    
    def _auto_save_worker(self):
        """Worker pour la sauvegarde automatique"""
        while not self._stop_auto_save.wait(self.auto_save_interval):
            try:
                self._save_modified_sessions()
            except Exception as e:
                print(f"⚠️ Erreur lors de la sauvegarde automatique: {e}")
    
    def _save_modified_sessions(self):
        """Sauvegarde seulement les sessions modifiées"""
        def _save_logic():
            if not self._sessions_modified:
                return
            
            saved_count = 0
            sessions_to_remove = set()
            
            for session_id in self._sessions_modified:
                if session_id in self.active_sessions:
                    try:
                        session = self.active_sessions[session_id]
                        self.db.update_session(session)
                        saved_count += 1
                        sessions_to_remove.add(session_id)
                    except Exception as e:
                        print(f"⚠️ Erreur sauvegarde session {session_id}: {e}")
            
            # Nettoyer la liste des sessions modifiées
            self._sessions_modified -= sessions_to_remove
            
            if saved_count > 0:
                print(f"💾 {saved_count} session(s) modifiée(s) sauvegardée(s)")
        
        self._with_lock(_save_logic)
    
    def _save_all_sessions(self):
        """Sauvegarde toutes les sessions actives"""
        def _save_logic():
            saved_count = 0
            for session in self.active_sessions.values():
                try:
                    self.db.update_session(session)
                    saved_count += 1
                except Exception as e:
                    print(f"⚠️ Erreur sauvegarde session {session.id}: {e}")
            
            if saved_count > 0:
                print(f"💾 {saved_count} session(s) sauvegardée(s)")
        
        self._with_lock(_save_logic)
    
    def _cleanup_old_active_sessions(self):
        """Nettoie les sessions actives les plus anciennes"""
        try:
            # Trier par date de mise à jour (plus ancien en premier)
            sorted_sessions = sorted(
                self.active_sessions.items(),
                key=lambda x: x[1].updated_at or datetime.min
            )
            
            # Retirer les plus anciennes
            sessions_to_remove = sorted_sessions[:max(1, len(sorted_sessions) - self.max_sessions + 2)]
            
            for session_id, session in sessions_to_remove:
                # Sauvegarder une dernière fois
                try:
                    self.db.update_session(session)
                except Exception as e:
                    print(f"⚠️ Erreur sauvegarde finale session {session_id}: {e}")
                
                # Retirer de la mémoire
                del self.active_sessions[session_id]
                self._sessions_modified.discard(session_id)
                print(f"🧹 Session {session_id[:8]} retirée des sessions actives")
                
        except Exception as e:
            print(f"⚠️ Erreur nettoyage sessions actives: {e}")
    
    def _load_active_sessions(self):
        """Charge les sessions actives depuis la base"""
        try:
            # Charger seulement les sessions en cours et en pause
            in_progress = self.db.list_sessions(SessionStatus.IN_PROGRESS, limit=self.max_sessions)
            paused = self.db.list_sessions(SessionStatus.PAUSED, limit=10)
            
            for session in in_progress + paused:
                # Normaliser les timestamps
                session.created_at = self._normalize_datetime(session.created_at)
                session.updated_at = self._normalize_datetime(session.updated_at)
                
                self.active_sessions[session.id] = session
            
            if self.active_sessions:
                print(f"🔄 {len(self.active_sessions)} session(s) active(s) chargée(s)")
                
        except Exception as e:
            print(f"⚠️ Erreur chargement sessions (continuons sans): {e}")
    
    def create_session(self, artist_name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Crée une nouvelle session SANS threading pour éviter les freezes"""
        session_id = str(uuid.uuid4())
        current_time = self._get_current_time()
        
        session = Session(
            id=session_id,
            artist_name=artist_name,
            status=SessionStatus.IN_PROGRESS,
            current_step="initialization",
            created_at=current_time,
            updated_at=current_time,
            metadata=metadata or {}
        )
        
        try:
            def _create_logic():
                # Vérifier la limite de sessions actives
                if len(self.active_sessions) >= self.max_sessions:
                    self._cleanup_old_active_sessions()
                
                # Ajouter la session
                self.active_sessions[session_id] = session
                self._mark_session_modified(session_id)
                return session_id
            
            # Exécuter avec ou sans lock
            result_id = self._with_lock(_create_logic)
            
            # Sauvegarder en base IMMÉDIATEMENT (pas de thread)
            self.db.create_session(session)
            
            # Déclencher l'événement
            self._trigger_event('session_created', session)
            
            time_str = current_time.strftime('%H:%M:%S') if USE_FRANCE_TZ else current_time.strftime('%H:%M:%S UTC')
            print(f"✨ Session créée ({time_str}): {session_id[:8]} pour {artist_name}")
            return session_id
            
        except Exception as e:
            print(f"⚠️ Erreur création session {artist_name}: {e}")
            # Nettoyer si erreur
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            # Retourner quand même l'ID pour que l'app continue
            return session_id
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Récupère une session par ID"""
        # Chercher en mémoire d'abord
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        # Puis en base
        try:
            session = self.db.get_session(session_id)
            if session:
                # Normaliser les timestamps
                session.created_at = self._normalize_datetime(session.created_at)
                session.updated_at = self._normalize_datetime(session.updated_at)
            return session
        except Exception as e:
            print(f"⚠️ Erreur récupération session {session_id}: {e}")
            return None
    
    def update_session(self, session: Session) -> bool:
        """Met à jour une session"""
        try:
            if not session or not session.id:
                print("⚠️ Session invalide pour mise à jour")
                return False
            
            session.updated_at = self._get_current_time()
            
            def _update_logic():
                # Mettre à jour en mémoire
                self.active_sessions[session.id] = session
                self._mark_session_modified(session.id)
            
            self._with_lock(_update_logic)
            
            # Sauvegarder en base IMMÉDIATEMENT
            self.db.update_session(session)
            
            self._trigger_event('session_updated', session)
            return True
            
        except Exception as e:
            print(f"⚠️ Erreur mise à jour session {getattr(session, 'id', 'UNKNOWN')}: {e}")
            return False
    
    def update_session_by_id(self, session_id: str, **updates) -> bool:
        """Met à jour une session par ID"""
        try:
            session = self.get_session(session_id)
            if not session:
                print(f"⚠️ Session {session_id} non trouvée pour mise à jour")
                return False
            
            # Appliquer les mises à jour
            for field, value in updates.items():
                if hasattr(session, field):
                    setattr(session, field, value)
                else:
                    print(f"⚠️ Champ {field} non trouvé sur Session")
            
            return self.update_session(session)
            
        except Exception as e:
            print(f"⚠️ Erreur mise à jour session {session_id}: {e}")
            return False
    
    def complete_session(self, session_id: str, final_stats: Optional[Dict[str, Any]] = None) -> bool:
        """Marque une session comme terminée"""
        try:
            current_time = self._get_current_time()
            
            updates = {
                'status': SessionStatus.COMPLETED,
                'updated_at': current_time,
                'current_step': 'completed'
            }
            
            if final_stats:
                updates['metadata'] = {
                    **(self.get_session(session_id).metadata if self.get_session(session_id) else {}),
                    'final_stats': final_stats,
                    'completed_at': current_time.isoformat()
                }
            
            result = self.update_session_by_id(session_id, **updates)
            
            if result:
                session = self.get_session(session_id)
                if session:
                    self._trigger_event('session_completed', session)
                    print(f"✅ Session terminée: {session_id[:8]}")
            
            return result
            
        except Exception as e:
            print(f"⚠️ Erreur completion session {session_id}: {e}")
            return False
    
    def fail_session(self, session_id: str, error_message: str) -> bool:
        """Marque une session comme échouée"""
        try:
            session = self.get_session(session_id)
            if not session:
                print(f"⚠️ Session {session_id} non trouvée pour échec")
                return False
            
            current_time = self._get_current_time()
            session.status = SessionStatus.FAILED
            session.updated_at = current_time
            session.last_error = error_message
            session.metadata['error_message'] = error_message
            session.metadata['failed_at'] = current_time.isoformat()
            
            def _fail_logic():
                # Sauvegarder en base
                self.db.update_session(session)
                
                # Retirer des sessions actives
                if session_id in self.active_sessions:
                    del self.active_sessions[session_id]
                self._sessions_modified.discard(session_id)
            
            self._with_lock(_fail_logic)
            
            print(f"❌ Session échouée: {session_id[:8]} - {error_message}")
            self._trigger_event('session_failed', session)
            return True
            
        except Exception as e:
            print(f"⚠️ Erreur échec session {session_id}: {e}")
            return False
    
    def pause_session(self, session_id: str) -> bool:
        """Met en pause une session"""
        result = self.update_session_by_id(session_id, status=SessionStatus.PAUSED)
        if result:
            session = self.get_session(session_id)
            if session:
                self._trigger_event('session_paused', session)
                print(f"⏸️ Session en pause: {session_id[:8]}")
        return result
    
    def resume_session(self, session_id: str) -> bool:
        """Reprend une session en pause"""
        result = self.update_session_by_id(session_id, status=SessionStatus.IN_PROGRESS)
        if result:
            session = self.get_session(session_id)
            if session:
                self._trigger_event('session_resumed', session)
                print(f"▶️ Session reprise: {session_id[:8]}")
        return result
    
    def list_sessions(self, status: Optional[SessionStatus] = None, limit: Optional[int] = None) -> List[Session]:
        """Liste les sessions avec timestamps normalisés"""
        try:
            sessions = self.db.list_sessions(status, limit)
            
            # Normaliser les timestamps
            for session in sessions:
                session.created_at = self._normalize_datetime(session.created_at)
                session.updated_at = self._normalize_datetime(session.updated_at)
            
            return sessions
            
        except Exception as e:
            print(f"⚠️ Erreur listage sessions: {e}")
            return []
    
    def delete_session(self, session_id: str) -> bool:
        """Supprime une session"""
        try:
            def _delete_logic():
                # Retirer de la mémoire
                if session_id in self.active_sessions:
                    del self.active_sessions[session_id]
                self._sessions_modified.discard(session_id)
            
            self._with_lock(_delete_logic)
            
            # Supprimer de la base
            success = self.db.delete_session(session_id)
            
            if success:
                print(f"🗑️ Session supprimée: {session_id[:8]}")
            
            return success
            
        except Exception as e:
            print(f"⚠️ Erreur suppression session {session_id}: {e}")
            return False
    
    def cleanup_old_sessions(self, days: Optional[int] = None) -> int:
        """Nettoie les anciennes sessions"""
        try:
            days = days or self.cleanup_after_days
            cutoff_date = self._get_current_time() - timedelta(days=days)
            
            # Récupérer les sessions anciennes
            old_sessions = []
            all_sessions = self.db.list_sessions()
            
            for session in all_sessions:
                session_date = self._normalize_datetime(session.updated_at or session.created_at)
                if session_date and session_date < cutoff_date:
                    old_sessions.append(session.id)
            
            # Supprimer les anciennes sessions
            deleted_count = 0
            for session_id in old_sessions:
                if self.delete_session(session_id):
                    deleted_count += 1
            
            if deleted_count > 0:
                print(f"🧹 {deleted_count} ancienne(s) session(s) supprimée(s)")
            
            return deleted_count
            
        except Exception as e:
            print(f"⚠️ Erreur nettoyage anciennes sessions: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du gestionnaire"""
        try:
            all_sessions = self.db.list_sessions()
            
            stats = {
                'total_sessions': len(all_sessions),
                'active_sessions': len(self.active_sessions),
                'status_breakdown': {},
                'recent_activity': 0
            }
            
            # Répartition par statut
            for session in all_sessions:
                status = session.status.value if hasattr(session.status, 'value') else str(session.status)
                stats['status_breakdown'][status] = stats['status_breakdown'].get(status, 0) + 1
            
            # Activité récente (dernières 24h)
            recent_cutoff = self._get_current_time() - timedelta(hours=24)
            for session in all_sessions:
                session_date = self._normalize_datetime(session.updated_at or session.created_at)
                if session_date and session_date > recent_cutoff:
                    stats['recent_activity'] += 1
            
            return stats
            
        except Exception as e:
            print(f"⚠️ Erreur récupération stats: {e}")
            return {}
    
    def add_event_callback(self, event_type: str, callback: Callable):
        """Ajoute un callback pour un événement de session"""
        if event_type in self.event_callbacks:
            self.event_callbacks[event_type].append(callback)
        else:
            print(f"⚠️ Type d'événement inconnu: {event_type}")
    
    def _trigger_event(self, event_type: str, session: Session):
        """Déclenche les callbacks d'un événement"""
        for callback in self.event_callbacks.get(event_type, []):
            try:
                callback(session)
            except Exception as e:
                print(f"⚠️ Erreur callback {event_type}: {e}")
    
    def stop(self):
        """Arrête le gestionnaire de sessions proprement"""
        print("🛑 Arrêt du gestionnaire de sessions...")
        
        # Arrêter le thread de sauvegarde si activé
        if self._auto_save_thread:
            self._stop_auto_save.set()
            if self._auto_save_thread.is_alive():
                self._auto_save_thread.join(timeout=5)
        
        # Sauvegarder une dernière fois toutes les sessions actives
        self._save_all_sessions()
        
        print("✅ Gestionnaire de sessions arrêté")
    
    def force_save_all(self):
        """Force la sauvegarde de toutes les sessions actives"""
        self._save_all_sessions()
    
    def __enter__(self):
        """Support du context manager"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Nettoyage automatique à la sortie"""
        self.stop()


# Instance globale du gestionnaire de sessions
_session_manager = None

def get_session_manager(enable_threading: bool = False) -> SessionManager:
    """Récupère l'instance globale du gestionnaire de sessions"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(enable_threading=enable_threading)
    return _session_manager

def reset_session_manager():
    """Remet à zéro l'instance globale (pour les tests)"""
    global _session_manager
    if _session_manager:
        _session_manager.stop()
    _session_manager = None

def create_session_safe(artist_name: str, metadata: dict = None, 
                       fallback_to_temp: bool = True) -> str:
    """
    Fonction utilitaire pour créer une session de manière sécurisée.
    Fallback automatique vers session temporaire si problème.
    """
    print(f"🔍 Création session sécurisée pour {artist_name}")
    
    try:
        # Tentative normale sans threading
        session_manager = get_session_manager(enable_threading=False)
        session_id = session_manager.create_session(artist_name, metadata)
        print(f"✅ Session normale créée: {session_id[:8]}")
        return session_id
        
    except Exception as e:
        print(f"⚠️ Échec création normale: {e}")
        
        if fallback_to_temp:
            # Fallback vers session temporaire
            import time
            session_id = f"temp_{int(time.time())}_{str(uuid.uuid4())[:8]}"
            print(f"🔄 Session temporaire créée: {session_id}")
            return session_id
        else:
            raise e