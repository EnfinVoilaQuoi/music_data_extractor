# core/session_manager.py - Version hybride avec toutes les fonctionnalités
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
    """Gestionnaire des sessions hybride - Simplicité + Fonctionnalités avancées"""
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.active_sessions: Dict[str, Session] = {}
        
        # Configuration
        self.auto_save_interval = settings.get('sessions.auto_save_interval', 60)
        self.max_sessions = settings.get('sessions.max_sessions', 20)  # Augmenté
        self.cleanup_after_days = settings.get('sessions.cleanup_after_days', 30)
        
        # Sauvegarde intelligente
        self._sessions_modified = set()  # IDs des sessions modifiées
        self._last_activity_time = None
        self._save_only_if_active = settings.get('sessions.save_only_if_active', True)
        
        # Threading pour sauvegarde automatique (optionnel)
        self._auto_save_thread = None
        self._stop_auto_save = threading.Event()
        self._session_lock = threading.Lock()
        
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
        if settings.get('sessions.enable_auto_save', True):
            self._start_auto_save()
        
        tz_msg = "avec timezone France" if USE_FRANCE_TZ else "sans timezone (UTC)"
        auto_save_msg = "avec sauvegarde auto" if self._auto_save_thread else "sans sauvegarde auto"
        print(f"✅ SessionManager hybride initialisé {tz_msg}, {auto_save_msg}")
    
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
    
    def _mark_session_modified(self, session_id: str):
        """Marque une session comme modifiée pour la sauvegarde intelligente"""
        with self._session_lock:
            self._sessions_modified.add(session_id)
            self._last_activity_time = self._get_current_time()
    
    def _start_auto_save(self):
        """Démarre le thread de sauvegarde automatique"""
        if self._auto_save_thread and self._auto_save_thread.is_alive():
            return
        
        self._stop_auto_save.clear()
        self._auto_save_thread = threading.Thread(target=self._auto_save_worker, daemon=True)
        self._auto_save_thread.start()
        
        save_mode = "intelligente" if self._save_only_if_active else "systématique"
        print(f"🔄 Auto-sauvegarde {save_mode} démarrée (intervalle: {self.auto_save_interval}s)")
    
    def _auto_save_worker(self):
        """Worker pour la sauvegarde automatique intelligente"""
        while not self._stop_auto_save.wait(self.auto_save_interval):
            try:
                if self._save_only_if_active:
                    self._smart_save_active_sessions()
                else:
                    self._save_active_sessions()
            except Exception as e:
                print(f"⚠️ Erreur lors de la sauvegarde automatique: {e}")
    
    def _smart_save_active_sessions(self):
        """Sauvegarde intelligente - seulement si activité récente"""
        with self._session_lock:
            # Vérifier s'il y a eu de l'activité récente
            if not self._last_activity_time:
                return
            
            # Seulement sauvegarder si activité dans les dernières 5 minutes
            current_time = self._get_current_time()
            time_since_activity = current_time - self._last_activity_time
            if time_since_activity.total_seconds() > 300:  # 5 minutes
                return
            
            # Sauvegarder seulement les sessions modifiées
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
    
    def _save_active_sessions(self):
        """Sauvegarde toutes les sessions actives"""
        with self._session_lock:
            saved_count = 0
            for session in self.active_sessions.values():
                try:
                    self.db.update_session(session)
                    saved_count += 1
                except Exception as e:
                    print(f"⚠️ Erreur sauvegarde session {session.id}: {e}")
            
            if saved_count > 0:
                print(f"💾 {saved_count} session(s) sauvegardée(s)")
    
    def create_session(self, artist_name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Crée une nouvelle session avec gestion intelligente des limites"""
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
            with self._session_lock:
                # Vérifier la limite de sessions actives
                if len(self.active_sessions) >= self.max_sessions:
                    self._cleanup_old_active_sessions()
                
                # Ajouter la session
                self.active_sessions[session_id] = session
                self._mark_session_modified(session_id)
            
            # Sauvegarder en base
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
            return session_id  # Retourner quand même l'ID pour continuer
    
    def _cleanup_old_active_sessions(self):
        """Nettoie les sessions actives les plus anciennes pour faire de la place"""
        try:
            # Trier par date de mise à jour (plus ancien en premier)
            sorted_sessions = sorted(
                self.active_sessions.items(),
                key=lambda x: x[1].updated_at or datetime.min
            )
            
            # Retirer les plus anciennes (garder juste en dessous de la limite)
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
                print(f"🧹 Session {session_id[:8]} retirée des sessions actives (limite atteinte)")
                
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
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Récupère une session par ID avec normalisation timezone"""
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
        """Met à jour une session (accepte l'objet Session directement)"""
        try:
            if not session or not session.id:
                print("⚠️ Session invalide pour mise à jour")
                return False
            
            session.updated_at = self._get_current_time()
            
            with self._session_lock:
                # Mettre à jour en mémoire
                self.active_sessions[session.id] = session
                self._mark_session_modified(session.id)
            
            # Sauvegarder en base
            self.db.update_session(session)
            
            self._trigger_event('session_updated', session)
            return True
            
        except Exception as e:
            print(f"⚠️ Erreur mise à jour session {getattr(session, 'id', 'UNKNOWN')}: {e}")
            return False
    
    def update_session_by_id(self, session_id: str, **updates) -> bool:
        """Met à jour une session par ID et mises à jour"""
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
    
    def update_progress(self, session_id: str, tracks_processed: Optional[int] = None,
                       tracks_with_credits: Optional[int] = None, 
                       tracks_with_albums: Optional[int] = None,
                       current_step: Optional[str] = None) -> bool:
        """Met à jour le progrès d'une session"""
        updates = {}
        if tracks_processed is not None:
            updates['tracks_processed'] = tracks_processed
        if tracks_with_credits is not None:
            updates['tracks_with_credits'] = tracks_with_credits
        if tracks_with_albums is not None:
            updates['tracks_with_albums'] = tracks_with_albums
        if current_step is not None:
            updates['current_step'] = current_step
        
        return self.update_session_by_id(session_id, **updates)
    
    def complete_session(self, session_id: str, final_stats: Optional[Dict[str, Any]] = None) -> bool:
        """Marque une session comme terminée"""
        try:
            session = self.get_session(session_id)
            if not session:
                print(f"⚠️ Session {session_id} non trouvée pour finalisation")
                return False
            
            current_time = self._get_current_time()
            session.status = SessionStatus.COMPLETED
            session.updated_at = current_time
            
            if final_stats:
                session.metadata.update(final_stats)
            
            # Calculer la durée totale
            if session.created_at:
                duration = current_time - session.created_at
                session.metadata['total_duration_seconds'] = int(duration.total_seconds())
            
            with self._session_lock:
                # Sauvegarder en base
                self.db.update_session(session)
                
                # Retirer des sessions actives
                if session_id in self.active_sessions:
                    del self.active_sessions[session_id]
                self._sessions_modified.discard(session_id)
            
            print(f"✅ Session terminée: {session_id[:8]}")
            self._trigger_event('session_completed', session)
            return True
            
        except Exception as e:
            print(f"⚠️ Erreur finalisation session {session_id}: {e}")
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
            
            with self._session_lock:
                # Sauvegarder en base
                self.db.update_session(session)
                
                # Retirer des sessions actives
                if session_id in self.active_sessions:
                    del self.active_sessions[session_id]
                self._sessions_modified.discard(session_id)
            
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
            
            # Normaliser les timestamps pour tous
            for session in sessions:
                session.created_at = self._normalize_datetime(session.created_at)
                session.updated_at = self._normalize_datetime(session.updated_at)
            
            return sessions
        except Exception as e:
            print(f"⚠️ Erreur listage sessions: {e}")
            return []
    
    def get_active_sessions(self) -> List[Session]:
        """Récupère toutes les sessions actives"""
        with self._session_lock:
            return list(self.active_sessions.values())
    
    # ==================== NOUVELLES FONCTIONNALITÉS RÉCUPÉRÉES ====================
    
    def create_checkpoint(self, session_id: str, step_name: str, data: Dict[str, Any]) -> bool:
        """Crée un point de sauvegarde pour une session"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        try:
            self.db.save_checkpoint(session_id, step_name, data)
            print(f"💾 Checkpoint créé pour {session_id[:8]}: {step_name}")
            return True
        except Exception as e:
            print(f"⚠️ Erreur création checkpoint: {e}")
            return False
    
    def get_checkpoint(self, session_id: str, step_name: str) -> Optional[Dict[str, Any]]:
        """Récupère un checkpoint spécifique"""
        try:
            return self.db.get_checkpoint(session_id, step_name)
        except Exception as e:
            print(f"⚠️ Erreur récupération checkpoint: {e}")
            return None
    
    def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        """Liste tous les checkpoints d'une session"""
        try:
            return self.db.list_checkpoints(session_id)
        except Exception as e:
            print(f"⚠️ Erreur listage checkpoints: {e}")
            return []
    
    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Récupère un résumé complet d'une session"""
        session = self.get_session(session_id)
        if not session:
            return None
        
        try:
            summary = {
                'session_id': session.id,
                'artist_name': session.artist_name,
                'status': session.status.value,
                'current_step': session.current_step,
                'created_at': session.created_at.isoformat() if session.created_at else None,
                'updated_at': session.updated_at.isoformat() if session.updated_at else None,
                'progress': {
                    'total_tracks_found': session.total_tracks_found,
                    'tracks_processed': session.tracks_processed,
                    'tracks_with_credits': session.tracks_with_credits,
                    'tracks_with_albums': session.tracks_with_albums,
                    'failed_tracks': session.failed_tracks
                },
                'metadata': session.metadata,
                'checkpoints': self.list_checkpoints(session_id)
            }
            
            # Calculer le pourcentage de progression
            if session.total_tracks_found and session.total_tracks_found > 0:
                summary['progress']['percentage'] = round(
                    (session.tracks_processed / session.total_tracks_found) * 100, 2
                )
            else:
                summary['progress']['percentage'] = 0.0
            
            # Calculer la durée
            if session.created_at:
                current_time = self._get_current_time()
                if session.status == SessionStatus.COMPLETED:
                    # Chercher la durée dans les métadonnées
                    duration = session.metadata.get('total_duration_seconds')
                    if duration:
                        summary['duration_seconds'] = duration
                    else:
                        # Fallback: calculer depuis les timestamps
                        if session.updated_at:
                            duration = session.updated_at - session.created_at
                            summary['duration_seconds'] = int(duration.total_seconds())
                else:
                    # Session en cours
                    duration = current_time - session.created_at
                    summary['duration_seconds'] = int(duration.total_seconds())
            
            return summary
            
        except Exception as e:
            print(f"⚠️ Erreur création résumé session: {e}")
            return None
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques globales des sessions"""
        try:
            stats = {
                'active_sessions_count': len(self.active_sessions),
                'sessions_by_status': {},
                'avg_completion_time_seconds': 0,
                'top_artists': [],
                'total_sessions': 0,
                'total_tracks_discovered': 0,
                'total_tracks_processed': 0
            }
            
            # Sessions par statut
            all_sessions = self.db.list_sessions()
            stats['total_sessions'] = len(all_sessions)
            
            for status in SessionStatus:
                count = len([s for s in all_sessions if s.status == status])
                stats['sessions_by_status'][status.value] = count
            
            # Calculs pour les sessions terminées
            completed_sessions = [s for s in all_sessions if s.status == SessionStatus.COMPLETED]
            if completed_sessions:
                total_duration = 0
                valid_durations = 0
                
                for session in completed_sessions:
                    # Accumuler les totaux
                    stats['total_tracks_discovered'] += session.total_tracks_found or 0
                    stats['total_tracks_processed'] += session.tracks_processed or 0
                    
                    # Calculer la durée
                    if session.created_at and session.updated_at:
                        session.created_at = self._normalize_datetime(session.created_at)
                        session.updated_at = self._normalize_datetime(session.updated_at)
                        
                        duration = session.updated_at - session.created_at
                        total_duration += duration.total_seconds()
                        valid_durations += 1
                
                if valid_durations > 0:
                    stats['avg_completion_time_seconds'] = int(total_duration / valid_durations)
            
            # Top artistes par nombre de sessions
            artist_counts = {}
            for session in all_sessions:
                artist_counts[session.artist_name] = artist_counts.get(session.artist_name, 0) + 1
            
            stats['top_artists'] = [
                {'artist': artist, 'sessions': count}
                for artist, count in sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            ]
            
            return stats
            
        except Exception as e:
            print(f"⚠️ Erreur statistiques globales: {e}")
            return {'error': str(e)}
    
    def cleanup_old_sessions(self):
        """Nettoie les anciennes sessions terminées en base"""
        try:
            current_time = self._get_current_time()
            cutoff_date = current_time - timedelta(days=self.cleanup_after_days)
            
            # Nettoyer en base via la méthode de la DB
            cleaned_count = self.db.cleanup_old_sessions(cutoff_date)
            
            # Nettoyer en mémoire aussi
            to_remove = []
            for session_id, session in self.active_sessions.items():
                if session.created_at and session.created_at < cutoff_date:
                    to_remove.append(session_id)
            
            for session_id in to_remove:
                del self.active_sessions[session_id]
                self._sessions_modified.discard(session_id)
            
            total_cleaned = cleaned_count + len(to_remove)
            if total_cleaned > 0:
                print(f"🧹 {total_cleaned} sessions anciennes nettoyées")
            
            return total_cleaned
            
        except Exception as e:
            print(f"⚠️ Erreur nettoyage sessions: {e}")
            return 0
    
    # ==================== MÉTHODES UTILITAIRES ====================
    
    def manual_save_all(self):
        """Sauvegarde manuelle de toutes les sessions actives"""
        try:
            with self._session_lock:
                saved_count = 0
                for session in self.active_sessions.values():
                    try:
                        self.db.update_session(session)
                        saved_count += 1
                    except Exception as e:
                        print(f"⚠️ Erreur sauvegarde {session.id}: {e}")
                
                # Nettoyer la liste des modifiées
                self._sessions_modified.clear()
                
                if saved_count > 0:
                    print(f"💾 {saved_count} session(s) sauvegardée(s) manuellement")
                return saved_count
                
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde globale: {e}")
            return 0
    
    def restart_failed_session(self, session_id: str) -> bool:
        """Redémarre une session échouée"""
        try:
            session = self.get_session(session_id)
            if not session:
                print(f"⚠️ Session {session_id} non trouvée")
                return False
            
            if session.status != SessionStatus.FAILED:
                print(f"⚠️ Session {session_id} n'est pas en échec (statut: {session.status.value})")
                return False
            
            # Réinitialiser le statut
            current_time = self._get_current_time()
            session.status = SessionStatus.IN_PROGRESS
            session.last_error = None
            session.error_count = 0
            session.updated_at = current_time
            
            # Nettoyer les métadonnées d'erreur
            if 'error_message' in session.metadata:
                del session.metadata['error_message']
            if 'failed_at' in session.metadata:
                del session.metadata['failed_at']
            
            # Ajouter info de redémarrage
            session.metadata['restarted_at'] = current_time.isoformat()
            session.metadata['restart_count'] = session.metadata.get('restart_count', 0) + 1
            
            # Remettre en sessions actives et sauvegarder
            with self._session_lock:
                self.active_sessions[session_id] = session
                self._mark_session_modified(session_id)
            
            result = self.update_session(session)
            
            if result:
                print(f"🔄 Session redémarrée: {session_id[:8]}")
                self._trigger_event('session_resumed', session)
            
            return result
            
        except Exception as e:
            print(f"⚠️ Erreur redémarrage session {session_id}: {e}")
            return False
    
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
        
        # Arrêter le thread de sauvegarde
        if self._auto_save_thread:
            self._stop_auto_save.set()
            if self._auto_save_thread.is_alive():
                self._auto_save_thread.join(timeout=5)
        
        # Sauvegarder une dernière fois toutes les sessions actives
        self._save_active_sessions()
        
        print("✅ Gestionnaire de sessions arrêté")
    
    def __enter__(self):
        """Support du context manager"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Nettoyage automatique à la sortie"""
        self.stop()


# Instance globale du gestionnaire de sessions
_session_manager = None

def get_session_manager() -> SessionManager:
    """Récupère l'instance globale du gestionnaire de sessions"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager

def reset_session_manager():
    """Remet à zéro l'instance globale (pour les tests)"""
    global _session_manager
    if _session_manager:
        _session_manager.stop()
    _session_manager = None