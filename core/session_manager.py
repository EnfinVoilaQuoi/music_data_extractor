# core/session_manager.py - Version corrigée sans threading
import uuid
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable

from config.settings import settings
from models.entities import Session
from models.enums import SessionStatus  
from core.database import Database

class SessionManager:
    """Gestionnaire des sessions SANS threading - Version stable"""
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.active_sessions: Dict[str, Session] = {}
        
        # Configuration simplifiée
        self.max_sessions = settings.get('sessions.max_sessions', 50)  # Augmenté
        self.cleanup_after_days = settings.get('sessions.cleanup_after_days', 30)
        
        # PAS de threading - juste callbacks
        self.event_callbacks: Dict[str, List[Callable]] = {
            'session_created': [],
            'session_updated': [],
            'session_completed': [],
            'session_failed': [],
            'session_paused': [],
            'session_resumed': []
        }
        
        # Chargement initial SANS auto-save
        self._load_active_sessions()
        print("✅ SessionManager simplifié initialisé (sans threading)")
    
    def create_session(self, artist_name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Crée une nouvelle session - VERSION SIMPLIFIÉE"""
        
        # Génération d'ID
        session_id = str(uuid.uuid4())
        
        # Création de l'objet session
        session = Session(
            id=session_id,
            artist_name=artist_name,
            status=SessionStatus.IN_PROGRESS,
            current_step="initialization",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata=metadata or {}
        )
        
        try:
            # PAS de verrous compliqués - juste ajouter
            self.active_sessions[session_id] = session
            
            # Sauvegarder en base
            self.db.create_session(session)
            
            # Déclencher l'événement
            self._trigger_event('session_created', session)
            
            print(f"✨ Session créée rapidement: {session_id[:8]} pour {artist_name}")
            return session_id
            
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde manuelle: {e}")
            return 0
    
    def cleanup_old_sessions(self):
        """Nettoie les anciennes sessions terminées ou échouées"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.cleanup_after_days)
            
            # Récupérer les sessions anciennes
            all_sessions = self.db.list_sessions()
            old_sessions = [
                s for s in all_sessions 
                if s.status in [SessionStatus.COMPLETED, SessionStatus.FAILED] 
                and s.updated_at and s.updated_at < cutoff_date
            ]
            
            cleaned_count = 0
            for session in old_sessions:
                try:
                    # Retirer de la mémoire si présent
                    if session.id in self.active_sessions:
                        del self.active_sessions[session.id]
                    
                    # Note: Ici on pourrait supprimer de la base aussi, mais on garde pour l'historique
                    cleaned_count += 1
                    
                except Exception as e:
                    print(f"⚠️ Erreur nettoyage session {session.id}: {e}")
            
            if cleaned_count > 0:
                print(f"🧹 {cleaned_count} anciennes sessions nettoyées de la mémoire")
            
            return cleaned_count
            
        except Exception as e:
            print(f"⚠️ Erreur nettoyage sessions: {e}")
            return 0
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Retourne des statistiques sur les sessions"""
        try:
            all_sessions = self.db.list_sessions()
            
            stats = {
                'total_sessions': len(all_sessions),
                'active_in_memory': len(self.active_sessions),
                'by_status': {},
                'average_duration': 0.0,
                'total_tracks_discovered': 0,
                'total_tracks_processed': 0
            }
            
            # Statistiques par statut
            for status in SessionStatus:
                count = len([s for s in all_sessions if s.status == status])
                stats['by_status'][status.value] = count
            
            # Calculs de durée et totaux
            completed_sessions = [s for s in all_sessions if s.status == SessionStatus.COMPLETED]
            if completed_sessions:
                total_duration = 0
                for session in completed_sessions:
                    if session.created_at and session.updated_at:
                        duration = (session.updated_at - session.created_at).total_seconds()
                        total_duration += duration
                    
                    stats['total_tracks_discovered'] += session.total_tracks_found
                    stats['total_tracks_processed'] += session.tracks_processed
                
                stats['average_duration'] = total_duration / len(completed_sessions)
            
            return stats
            
        except Exception as e:
            print(f"⚠️ Erreur calcul statistiques sessions: {e}")
            return {'error': str(e)}
    
    def debug_session(self, session_id: str) -> Dict[str, Any]:
        """Informations de debug pour une session"""
        try:
            session = self.get_session(session_id)
            if not session:
                return {'error': f'Session {session_id} non trouvée'}
            
            debug_info = {
                'session_id': session.id,
                'artist_name': session.artist_name,
                'status': session.status.value,
                'current_step': session.current_step,
                'created_at': session.created_at.isoformat() if session.created_at else None,
                'updated_at': session.updated_at.isoformat() if session.updated_at else None,
                'in_memory': session.id in self.active_sessions,
                'metadata_keys': list(session.metadata.keys()) if session.metadata else [],
                'progress': {
                    'total_tracks_found': session.total_tracks_found,
                    'tracks_processed': session.tracks_processed,
                    'tracks_with_credits': session.tracks_with_credits,
                    'tracks_with_albums': session.tracks_with_albums,
                    'failed_tracks': session.failed_tracks
                },
                'error_info': {
                    'error_count': session.error_count,
                    'last_error': session.last_error
                }
            }
            
            # Calcul de durée si applicable
            if session.created_at and session.updated_at:
                duration = session.updated_at - session.created_at
                debug_info['duration_seconds'] = duration.total_seconds()
                debug_info['duration_formatted'] = str(duration)
            
            return debug_info
            
        except Exception as e:
            return {'error': f'Erreur debug session: {e}'}
    
    def force_sync_session(self, session_id: str) -> bool:
        """Force la synchronisation d'une session entre mémoire et base"""
        try:
            # Récupérer depuis la base
            db_session = self.db.get_session(session_id)
            if not db_session:
                print(f"⚠️ Session {session_id} non trouvée en base")
                return False
            
            # Mettre à jour en mémoire
            self.active_sessions[session_id] = db_session
            print(f"🔄 Session {session_id[:8]} synchronisée")
            return True
            
        except Exception as e:
            print(f"⚠️ Erreur sync session {session_id}: {e}")
            return False
    
    def get_session_by_artist(self, artist_name: str, status: Optional[SessionStatus] = None) -> List[Session]:
        """Récupère les sessions pour un artiste donné"""
        try:
            all_sessions = self.db.list_sessions(status)
            artist_sessions = [
                s for s in all_sessions 
                if s.artist_name.lower() == artist_name.lower()
            ]
            
            # Trier par date de création (plus récent en premier)
            artist_sessions.sort(key=lambda x: x.created_at or datetime.min, reverse=True)
            
            return artist_sessions
            
        except Exception as e:
            print(f"⚠️ Erreur récupération sessions pour {artist_name}: {e}")
            return []
    
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
            session.status = SessionStatus.IN_PROGRESS
            session.last_error = None
            session.error_count = 0
            session.updated_at = datetime.now()
            
            # Nettoyer les métadonnées d'erreur
            if 'error_message' in session.metadata:
                del session.metadata['error_message']
            if 'failed_at' in session.metadata:
                del session.metadata['failed_at']
            
            # Ajouter info de redémarrage
            session.metadata['restarted_at'] = datetime.now().isoformat()
            session.metadata['restart_count'] = session.metadata.get('restart_count', 0) + 1
            
            # Sauvegarder
            result = self.update_session(session)
            
            if result:
                print(f"🔄 Session redémarrée: {session_id[:8]}")
                self._trigger_event('session_resumed', session)
            
            return result
            
        except Exception as e:
            print(f"⚠️ Erreur redémarrage session {session_id}: {e}")
            return False


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
    _session_manager = None as e:
            print(f"⚠️ Erreur création session {artist_name}: {e}")
            # Nettoyer si erreur
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            return session_id  # Retourner quand même l'ID pour continuer
    
    def _load_active_sessions(self):
        """Charge les sessions actives depuis la base"""
        try:
            # Charger seulement les sessions en cours et en pause
            in_progress = self.db.list_sessions(SessionStatus.IN_PROGRESS, limit=20)
            paused = self.db.list_sessions(SessionStatus.PAUSED, limit=10)
            
            for session in in_progress + paused:
                self.active_sessions[session.id] = session
            
            if self.active_sessions:
                print(f"🔄 {len(self.active_sessions)} session(s) active(s) chargée(s)")
                
        except Exception as e:
            print(f"⚠️ Erreur chargement sessions (continuons sans): {e}")
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Récupère une session par ID"""
        # Chercher en mémoire d'abord
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        # Puis en base
        try:
            return self.db.get_session(session_id)
        except Exception as e:
            print(f"⚠️ Erreur récupération session {session_id}: {e}")
            return None
    
    def update_session(self, session: Session) -> bool:
        """Met à jour une session (accepte l'objet Session directement)"""
        try:
            if not session or not session.id:
                print("⚠️ Session invalide pour mise à jour")
                return False
            
            session.updated_at = datetime.now()
            
            # Mettre à jour en mémoire
            self.active_sessions[session.id] = session
            
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
            
            session.status = SessionStatus.COMPLETED
            session.updated_at = datetime.now()
            
            if final_stats:
                session.metadata.update(final_stats)
            
            # Calculer la durée totale
            if session.created_at:
                duration = datetime.now() - session.created_at
                session.metadata['total_duration_seconds'] = int(duration.total_seconds())
            
            # Sauvegarder
            result = self.update_session(session)
            
            if result:
                print(f"✅ Session terminée: {session_id[:8]}")
                self._trigger_event('session_completed', session)
            
            return result
            
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
            
            session.status = SessionStatus.FAILED
            session.updated_at = datetime.now()
            session.last_error = error_message
            session.metadata['error_message'] = error_message
            session.metadata['failed_at'] = datetime.now().isoformat()
            
            # Sauvegarder
            result = self.update_session(session)
            
            if result:
                print(f"❌ Session échouée: {session_id[:8]} - {error_message}")
                self._trigger_event('session_failed', session)
            
            return result
            
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
        """Liste les sessions"""
        try:
            return self.db.list_sessions(status, limit)
        except Exception as e:
            print(f"⚠️ Erreur listage sessions: {e}")
            return []
    
    def get_active_sessions(self) -> List[Session]:
        """Récupère toutes les sessions actives"""
        return list(self.active_sessions.values())
    
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
    
    def manual_save_all(self):
        """Sauvegarde manuelle de toutes les sessions actives"""
        try:
            saved_count = 0
            for session in self.active_sessions.values():
                try:
                    self.db.update_session(session)
                    saved_count += 1
                except Exception as e:
                    print(f"⚠️ Erreur sauvegarde {session.id}: {e}")
            
            if saved_count > 0:
                print(f"💾 {saved_count} session(s) sauvegardée(s) manuellement")
            return saved_count
            
        except Exception