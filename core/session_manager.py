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
            
            # Sauvegarde immédiate en base
            self.db.create_session(session)
            
            # Nettoyage léger SI nécessaire (sans blocage)
            if len(self.active_sessions) > self.max_sessions:
                self._simple_cleanup()
            
            print(f"✨ Session créée rapidement: {session_id[:8]} pour {artist_name}")
            self._trigger_event('session_created', session)
            
            return session_id
            
        except Exception as e:
            # En cas d'erreur, on essaie quand même de retourner l'ID
            print(f"⚠️ Erreur création session (mais continuons): {e}")
            return session_id
    
    def _simple_cleanup(self):
        """Nettoyage simple sans requêtes complexes"""
        try:
            # Garder seulement les N sessions les plus récentes
            if len(self.active_sessions) <= self.max_sessions:
                return
            
            # Trier par date de mise à jour
            sorted_sessions = sorted(
                self.active_sessions.items(),
                key=lambda x: x[1].updated_at or datetime.min,
                reverse=True
            )
            
            # Garder les plus récentes
            sessions_to_keep = dict(sorted_sessions[:self.max_sessions])
            sessions_to_remove = []
            
            for session_id in list(self.active_sessions.keys()):
                if session_id not in sessions_to_keep:
                    sessions_to_remove.append(session_id)
            
            # Supprimer de la mémoire (on garde en base)
            for session_id in sessions_to_remove:
                if session_id in self.active_sessions:
                    del self.active_sessions[session_id]
            
            if sessions_to_remove:
                print(f"🧹 {len(sessions_to_remove)} sessions retirées de la mémoire")
                
        except Exception as e:
            print(f"⚠️ Erreur nettoyage simple: {e}")
    
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
    
    def update_session(self, session_id: str, **updates) -> bool:
        """Met à jour une session"""
        try:
            session = self.get_session(session_id)
            if not session:
                return False
            
            # Appliquer les mises à jour
            for field, value in updates.items():
                if hasattr(session, field):
                    setattr(session, field, value)
            
            session.updated_at = datetime.now()
            
            # Mettre à jour en mémoire
            self.active_sessions[session_id] = session
            
            # Sauvegarder en base
            self.db.update_session(session)
            
            self._trigger_event('session_updated', session)
            return True
            
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
        
        return self.update_session(session_id, **updates)
    
    def complete_session(self, session_id: str, final_stats: Optional[Dict[str, Any]] = None) -> bool:
        """Marque une session comme terminée"""
        try:
            session = self.get_session(session_id)
            if not session:
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
            self.active_sessions[session_id] = session
            self.db.update_session(session)
            
            # Retirer des sessions actives (optionnel)
            # del self.active_sessions[session_id]
            
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
                return False
            
            session.status = SessionStatus.FAILED
            session.updated_at = datetime.now()
            session.metadata['error_message'] = error_message
            session.metadata['failed_at'] = datetime.now().isoformat()
            
            # Sauvegarder
            self.active_sessions[session_id] = session
            self.db.update_session(session)
            
            print(f"❌ Session échouée: {session_id[:8]} - {error_message}")
            self._trigger_event('session_failed', session)
            return True
            
        except Exception as e:
            print(f"⚠️ Erreur échec session {session_id}: {e}")
            return False
    
    def pause_session(self, session_id: str) -> bool:
        """Met en pause une session"""
        result = self.update_session(session_id, status=SessionStatus.PAUSED)
        if result:
            session = self.get_session(session_id)
            self._trigger_event('session_paused', session)
            print(f"⏸️ Session en pause: {session_id[:8]}")
        return result
    
    def resume_session(self, session_id: str) -> bool:
        """Reprend une session en pause"""
        result = self.update_session(session_id, status=SessionStatus.IN_PROGRESS)
        if result:
            session = self.get_session(session_id)
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
            
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde manuelle: {e}")
            return 0


# Instance globale du gestionnaire de sessions
_session_manager = None

def get_session_manager() -> SessionManager:
    """Récupère l'instance globale du gestionnaire de sessions"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager