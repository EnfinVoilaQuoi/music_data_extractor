# steps/step2_extract.py
"""Étape 2: Extraction des données musicales"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from core.database import Database
from core.session_manager import SessionManager
from core.rate_limiter import RateLimiter
from models.entities import Artist, Album, Track, Session
from models.enums import ExtractionStatus, SessionStatus
from utils.logging_config import get_session_logger

class ExtractionStep:
    """Étape d'extraction des données détaillées"""
    
    def __init__(self, db: Database, session_manager: SessionManager):
        self.db = db
        self.session_manager = session_manager
        self.rate_limiter = RateLimiter()
        self.logger = logging.getLogger(__name__)
    
    async def run(self, session: Session, progress_tracker=None) -> Dict[str, Any]:
        """
        Exécute l'étape d'extraction
        
        Args:
            session: Session d'extraction
            progress_tracker: Tracker de progression optionnel
            
        Returns:
            Résultats de l'extraction
        """
        logger = get_session_logger(session.id, "extraction")
        logger.info("🚀 Début de l'étape d'extraction")
        
        try:
            # Récupérer l'artiste depuis la découverte
            artist = self.db.get_artist_by_name(session.artist_name)
            if not artist:
                raise ValueError(f"Artiste '{session.artist_name}' non trouvé en base")
            
            logger.info(f"🎵 Extraction pour {artist.name}")
            
            # Initialiser le tracker de progression
            if progress_tracker:
                step_name = "extraction"
                if step_name not in progress_tracker.steps:
                    progress_tracker.add_step(step_name, "Extraction des données", 100)
                progress_tracker.start_step(step_name)
            
            # Simuler l'extraction (à remplacer par la vraie logique)
            extraction_results = {
                'artist_id': artist.id,
                'tracks_extracted': 0,
                'albums_extracted': 0,
                'credits_extracted': 0,
                'status': ExtractionStatus.COMPLETED
            }
            
            # Mettre à jour la session
            session.status = SessionStatus.PROCESSING
            session.current_step = "extraction"
            session.progress = 50
            session.updated_at = datetime.utcnow()
            self.session_manager.update_session(session)
            
            logger.info("✅ Étape d'extraction terminée")
            return extraction_results
            
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'extraction: {e}")
            session.status = SessionStatus.ERROR
            session.error_message = str(e)
            self.session_manager.update_session(session)
            raise
