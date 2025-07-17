# core/session_manager.py - Version optimisée sans complexité inutile
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from config.settings import settings
from models.entities import Session
from models.enums import SessionStatus  
from core.database import Database

class SessionManager:
    """Gestionnaire des sessions simplifié et efficace"""
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.active_sessions: Dict[str, Session] = {}
        
        # Configuration simplifiée
        self.max_sessions = getattr(settings, 'max_sessions', 20)
        self.cleanup_after_days = getattr(settings, 'cleanup_after_days', 30)
        
        # Charger les sessions actives
        self._load_active_sessions()
        
        print(f"✅ SessionManager simplifié initialisé")
    
    def create_session(self, artist_name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Crée une nouvelle session"""
        try:
            session_id = str(uuid.uuid4())
            current_time = datetime.now()
            
            session = Session(
                id=session_id,
                artist_name=artist_name,
                status=SessionStatus.IN_PROGRESS,
                current_step="created",
                created_at=current_time,
                updated_at=current_time,
                metadata=metadata or {}
            )
            
            # Sauvegarder en base
            self.db.save_session(session)
            
            # Ajouter aux sessions actives
            self.active_sessions[session_id] = session
            
            # Nettoyer si trop de sessions actives
            if len(self.active_sessions) > self.max_sessions:
                self._cleanup_old_active_sessions()
            
            print(f"✨ Session créée: {session_id[:8]} - {artist_name}")
            return session_id
            
        except Exception as e:
            print(f"⚠️ Erreur création session: {e}")
            raise
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Récupère une session"""
        try:
            # Vérifier en mémoire d'abord
            if session_id in self.active_sessions:
                return self.active_sessions[session_id]
            
            # Charger depuis la base
            session = self.db.get_session(session_id)
            if session:
                # Ajouter aux sessions actives si elle est en cours
                if session.status == SessionStatus.IN_PROGRESS:
                    self.active_sessions[session_id] = session
            
            return session
            
        except Exception as e:
            print(f"⚠️ Erreur récupération session {session_id}: {e}")
            return None
    
    def update_session(self, session: Session) -> bool:
        """Met à jour une session"""
        try:
            session.updated_at = datetime.now()
            
            # Sauvegarder en base
            self.db.update_session(session)
            
            # Mettre à jour en mémoire
            if session.id in self.active_sessions:
                self.active_sessions[session.id] = session
            
            return True
            
        except Exception as e:
            print(f"⚠️ Erreur mise à jour session {session.id}: {e}")
            return False
    
    def complete_session(self, session_id: str, final_stats: Optional[Dict[str, Any]] = None) -> bool:
        """Marque une session comme terminée"""
        try:
            session = self.get_session(session_id)
            if not session:
                return False
            
            session.status = SessionStatus.COMPLETED
            session.current_step = "completed"
            session.updated_at = datetime.now()
            
            if final_stats:
                session.metadata.update({'final_stats': final_stats})
            
            result = self.update_session(session)
            
            # Retirer des sessions actives
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            if result:
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
                return False
            
            session.status = SessionStatus.FAILED
            session.current_step = "failed"
            session.updated_at = datetime.now()
            session.metadata['error_message'] = error_message
            session.metadata['failed_at'] = datetime.now().isoformat()
            
            result = self.update_session(session)
            
            # Retirer des sessions actives
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            if result:
                print(f"❌ Session échouée: {session_id[:8]} - {error_message}")
            
            return result
            
        except Exception as e:
            print(f"⚠️ Erreur échec session {session_id}: {e}")
            return False
    
    def list_sessions(self, status: Optional[SessionStatus] = None, limit: Optional[int] = None) -> List[Session]:
        """Liste les sessions"""
        try:
            return self.db.list_sessions(status, limit)
        except Exception as e:
            print(f"⚠️ Erreur listage sessions: {e}")
            return []
    
    def delete_session(self, session_id: str) -> bool:
        """Supprime une session"""
        try:
            # Retirer de la mémoire
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
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
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Récupérer les sessions anciennes
            all_sessions = self.db.list_sessions()
            old_sessions = [
                s for s in all_sessions 
                if s.updated_at and s.updated_at < cutoff_date
            ]
            
            # Supprimer les anciennes sessions
            deleted_count = 0
            for session in old_sessions:
                if self.delete_session(session.id):
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
                'status_breakdown': {}
            }
            
            # Répartition par statut
            for session in all_sessions:
                status = session.status.value if hasattr(session.status, 'value') else str(session.status)
                stats['status_breakdown'][status] = stats['status_breakdown'].get(status, 0) + 1
            
            return stats
            
        except Exception as e:
            print(f"⚠️ Erreur récupération stats: {e}")
            return {}
    
    def _load_active_sessions(self):
        """Charge les sessions actives depuis la base"""
        try:
            in_progress_sessions = self.db.list_sessions(SessionStatus.IN_PROGRESS)
            paused_sessions = self.db.list_sessions(SessionStatus.PAUSED)
            
            for session in in_progress_sessions + paused_sessions:
                self.active_sessions[session.id] = session
            
            print(f"📥 {len(self.active_sessions)} session(s) active(s) chargée(s)")
            
        except Exception as e:
            print(f"⚠️ Erreur chargement sessions actives: {e}")
    
    def _cleanup_old_active_sessions(self):
        """Nettoie les sessions actives les plus anciennes"""
        try:
            # Trier par date de mise à jour (plus ancien en premier)
            sorted_sessions = sorted(
                self.active_sessions.items(),
                key=lambda x: x[1].updated_at or datetime.min
            )
            
            # Retirer les plus anciennes
            sessions_to_remove = sorted_sessions[:len(sorted_sessions) - self.max_sessions + 2]
            
            for session_id, session in sessions_to_remove:
                # Sauvegarder une dernière fois
                try:
                    self.db.update_session(session)
                except Exception as e:
                    print(f"⚠️ Erreur sauvegarde finale session {session_id}: {e}")
                
                # Retirer de la mémoire
                del self.active_sessions[session_id]
                print(f"🧹 Session {session_id[:8]} retirée des sessions actives")
                
        except Exception as e:
            print(f"⚠️ Erreur nettoyage sessions actives: {e}")

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
    _session_manager = None