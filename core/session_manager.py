# core/session_manager.py
import uuid
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path

from config.settings import settings
from core.database import Database
from models.entities import Session
from models.enums import SessionStatus

class SessionManager:
    """Gestionnaire des sessions de travail avec sauvegarde automatique"""
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.active_sessions: Dict[str, Session] = {}
        self.auto_save_interval = settings.get('sessions.auto_save_interval', 60)
        self.max_sessions = settings.get('sessions.max_sessions', 10)
        self.cleanup_after_days = settings.get('sessions.cleanup_after_days', 30)
        
        # Thread pour la sauvegarde automatique
        self._auto_save_thread = None
        self._stop_auto_save = threading.Event()
        self._session_lock = threading.Lock()
        
        # Callbacks pour les événements de session
        self.event_callbacks: Dict[str, List[Callable]] = {
            'session_created': [],
            'session_updated': [],
            'session_completed': [],
            'session_failed': [],
            'session_paused': [],
            'session_resumed': []
        }
        
        self._start_auto_save()
        self._load_active_sessions()
    
    def _start_auto_save(self):
        """Démarre le thread de sauvegarde automatique"""
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
                self._save_active_sessions()
            except Exception as e:
                print(f"⚠️ Erreur lors de la sauvegarde automatique: {e}")
    
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
    
    def _load_active_sessions(self):
        """Charge les sessions en cours depuis la base"""
        try:
            in_progress_sessions = self.db.list_sessions(SessionStatus.IN_PROGRESS)
            paused_sessions = self.db.list_sessions(SessionStatus.PAUSED)
            
            for session in in_progress_sessions + paused_sessions:
                self.active_sessions[session.id] = session
            
            if self.active_sessions:
                print(f"🔄 {len(self.active_sessions)} session(s) active(s) rechargée(s)")
        except Exception as e:
            print(f"⚠️ Erreur lors du chargement des sessions: {e}")
    
    def create_session(self, artist_name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Crée une nouvelle session"""
        session_id = str(uuid.uuid4())
        
        session = Session(
            id=session_id,
            artist_name=artist_name,
            status=SessionStatus.IN_PROGRESS,
            current_step="initialization",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata=metadata or {}
        )
        
        with self._session_lock:
            # Vérifier la limite de sessions
            if len(self.active_sessions) >= self.max_sessions:
                self._cleanup_old_sessions()
            
            # Ajouter la session
            self.active_sessions[session_id] = session
            
            # Sauvegarder en base
            self.db.create_session(session)
        
        print(f"✨ Nouvelle session créée: {session_id} pour {artist_name}")
        self._trigger_event('session_created', session)
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Récupère une session par son ID"""
        with self._session_lock:
            # Vérifier d'abord dans les sessions actives
            if session_id in self.active_sessions:
                return self.active_sessions[session_id]
            
            # Sinon chercher en base et la charger
            session = self.db.get_session(session_id)
            if session and session.status in [SessionStatus.IN_PROGRESS, SessionStatus.PAUSED]:
                self.active_sessions[session_id] = session
            
            return session
    
    def update_session(self, session_id: str, **updates) -> bool:
        """Met à jour une session"""
        session = self.get_session(session_id)
        if not session:
            print(f"⚠️ Session non trouvée: {session_id}")
            return False
        
        with self._session_lock:
            # Appliquer les mises à jour
            for key, value in updates.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            
            session.updated_at = datetime.now()
            
            # Sauvegarder en base immédiatement pour les mises à jour importantes
            if any(key in ['status', 'current_step', 'total_tracks_found'] for key in updates.keys()):
                self.db.update_session(session)
        
        self._trigger_event('session_updated', session)
        return True
    
    def update_progress(self, session_id: str, 
                      tracks_processed: Optional[int] = None,
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
        session = self.get_session(session_id)
        if not session:
            return False
        
        with self._session_lock:
            session.status = SessionStatus.COMPLETED
            session.updated_at = datetime.now()
            
            if final_stats:
                session.metadata.update(final_stats)
            
            # Calculer la durée totale
            if session.created_at:
                duration = datetime.now() - session.created_at
                session.metadata['total_duration_seconds'] = int(duration.total_seconds())
            
            # Sauvegarder et retirer des sessions actives
            self.db.update_session(session)
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
        
        print(f"✅ Session terminée: {session_id}")
        self._trigger_event('session_completed', session)
        return True
    
    def fail_session(self, session_id: str, error_message: str) -> bool:
        """Marque une session comme échouée"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        with self._session_lock:
            session.status = SessionStatus.FAILED
            session.updated_at = datetime.now()
            session.metadata['error_message'] = error_message
            session.metadata['failed_at'] = datetime.now().isoformat()
            
            # Sauvegarder et retirer des sessions actives
            self.db.update_session(session)
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
        
        print(f"❌ Session échouée: {session_id} - {error_message}")
        self._trigger_event('session_failed', session)
        return True
    
    def pause_session(self, session_id: str) -> bool:
        """Met en pause une session"""
        result = self.update_session(session_id, status=SessionStatus.PAUSED)
        if result:
            session = self.get_session(session_id)
            self._trigger_event('session_paused', session)
            print(f"⏸️ Session mise en pause: {session_id}")
        return result
    
    def resume_session(self, session_id: str) -> bool:
        """Reprend une session en pause"""
        result = self.update_session(session_id, status=SessionStatus.IN_PROGRESS)
        if result:
            session = self.get_session(session_id)
            self._trigger_event('session_resumed', session)
            print(f"▶️ Session reprise: {session_id}")
        return result
    
    def list_sessions(self, status: Optional[SessionStatus] = None) -> List[Session]:
        """Liste les sessions, optionnellement filtrées par statut"""
        return self.db.list_sessions(status)
    
    def get_active_sessions(self) -> List[Session]:
        """Récupère toutes les sessions actives"""
        with self._session_lock:
            return list(self.active_sessions.values())
    
    def create_checkpoint(self, session_id: str, step_name: str, data: Dict[str, Any]) -> bool:
        """Crée un point de sauvegarde pour une session"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        try:
            with self.db.get_connection() as conn:
                conn.execute("""
                    INSERT INTO checkpoints (session_id, step_name, data)
                    VALUES (?, ?, ?)
                """, (session_id, step_name, json.dumps(data)))
            
            print(f"💾 Checkpoint créé pour {session_id}: {step_name}")
            return True
        except Exception as e:
            print(f"⚠️ Erreur création checkpoint: {e}")
            return False
    
    def get_checkpoint(self, session_id: str, step_name: str) -> Optional[Dict[str, Any]]:
        """Récupère un checkpoint spécifique"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT data FROM checkpoints 
                    WHERE session_id = ? AND step_name = ?
                    ORDER BY created_at DESC LIMIT 1
                """, (session_id, step_name))
                
                row = cursor.fetchone()
                if row:
                    return json.loads(row['data'])
        except Exception as e:
            print(f"⚠️ Erreur récupération checkpoint: {e}")
        
        return None
    
    def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        """Liste tous les checkpoints d'une session"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT step_name, data, created_at FROM checkpoints 
                    WHERE session_id = ?
                    ORDER BY created_at DESC
                """, (session_id,))
                
                checkpoints = []
                for row in cursor.fetchall():
                    checkpoints.append({
                        'step_name': row['step_name'],
                        'data': json.loads(row['data']),
                        'created_at': row['created_at']
                    })
                
                return checkpoints
        except Exception as e:
            print(f"⚠️ Erreur listage checkpoints: {e}")
        
        return []
    
    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Récupère un résumé complet d'une session"""
        session = self.get_session(session_id)
        if not session:
            return None
        
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
                'tracks_with_albums': session.tracks_with_albums
            },
            'metadata': session.metadata,
            'checkpoints': self.list_checkpoints(session_id)
        }
        
        # Calculer le pourcentage de progression
        if session.total_tracks_found and session.total_tracks_found > 0:
            summary['progress']['percentage'] = round(
                (session.tracks_processed / session.total_tracks_found) * 100, 2
            )
        
        # Calculer la durée
        if session.created_at:
            if session.status == SessionStatus.COMPLETED:
                # Chercher la durée dans les métadonnées
                duration = session.metadata.get('total_duration_seconds')
                if duration:
                    summary['duration_seconds'] = duration
            else:
                # Session en cours
                duration = datetime.now() - session.created_at
                summary['duration_seconds'] = int(duration.total_seconds())
        
        return summary
    
    def _cleanup_old_sessions(self):
        """Nettoie les anciennes sessions pour faire de la place"""
        try:
            # Supprimer d'abord les sessions les plus anciennes des sessions actives
            sorted_sessions = sorted(
                self.active_sessions.items(),
                key=lambda x: x[1].updated_at or datetime.min
            )
            
            sessions_to_remove = sorted_sessions[:max(1, len(sorted_sessions) - self.max_sessions + 1)]
            
            for session_id, session in sessions_to_remove:
                # Sauvegarder une dernière fois avant suppression
                self.db.update_session(session)
                del self.active_sessions[session_id]
                print(f"🧹 Session {session_id} retirée des sessions actives (nettoyage)")
            
            # Nettoyer aussi les anciennes sessions en base
            self._cleanup_old_database_sessions()
            
        except Exception as e:
            print(f"⚠️ Erreur lors du nettoyage: {e}")
    
    def _cleanup_old_database_sessions(self):
        """Nettoie les anciennes sessions en base de données"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.cleanup_after_days)
            
            with self.db.get_connection() as conn:
                # Compter d'abord
                cursor = conn.execute("""
                    SELECT COUNT(*) as count FROM sessions 
                    WHERE status IN ('completed', 'failed') 
                    AND updated_at < ?
                """, (cutoff_date.isoformat(),))
                
                count = cursor.fetchone()['count']
                
                if count > 0:
                    # Supprimer les checkpoints associés
                    conn.execute("""
                        DELETE FROM checkpoints 
                        WHERE session_id IN (
                            SELECT id FROM sessions 
                            WHERE status IN ('completed', 'failed') 
                            AND updated_at < ?
                        )
                    """, (cutoff_date.isoformat(),))
                    
                    # Supprimer les sessions
                    conn.execute("""
                        DELETE FROM sessions 
                        WHERE status IN ('completed', 'failed') 
                        AND updated_at < ?
                    """, (cutoff_date.isoformat(),))
                    
                    print(f"🧹 {count} ancienne(s) session(s) supprimée(s) de la base")
                    
        except Exception as e:
            print(f"⚠️ Erreur nettoyage base de données: {e}")
    
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
        """Arrête le gestionnaire de sessions"""
        print("🛑 Arrêt du gestionnaire de sessions...")
        
        # Arrêter le thread de sauvegarde
        self._stop_auto_save.set()
        if self._auto_save_thread and self._auto_save_thread.is_alive():
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
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques globales des sessions"""
        try:
            with self.db.get_connection() as conn:
                stats = {}
                
                # Sessions par statut
                cursor = conn.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM sessions 
                    GROUP BY status
                """)
                stats['sessions_by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}
                
                # Sessions actives
                stats['active_sessions_count'] = len(self.active_sessions)
                
                # Durée moyenne des sessions terminées
                cursor = conn.execute("""
                    SELECT AVG(
                        CAST((julianday(updated_at) - julianday(created_at)) * 86400 AS INTEGER)
                    ) as avg_duration
                    FROM sessions 
                    WHERE status = 'completed' AND created_at IS NOT NULL
                """)
                row = cursor.fetchone()
                if row and row['avg_duration']:
                    stats['avg_completion_time_seconds'] = int(row['avg_duration'])
                
                # Top artistes traités
                cursor = conn.execute("""
                    SELECT artist_name, COUNT(*) as session_count
                    FROM sessions 
                    GROUP BY artist_name 
                    ORDER BY session_count DESC 
                    LIMIT 10
                """)
                stats['top_artists'] = [
                    {'artist': row['artist_name'], 'sessions': row['session_count']}
                    for row in cursor.fetchall()
                ]
                
                return stats
                
        except Exception as e:
            print(f"⚠️ Erreur statistiques globales: {e}")
            return {}


# Instance globale du gestionnaire de sessions
_session_manager = None

def get_session_manager() -> SessionManager:
    """Récupère l'instance globale du gestionnaire de sessions"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager