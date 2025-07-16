# steps/step3_process.py
"""Étape 3: Traitement et nettoyage des données"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from core.database import Database
from core.session_manager import SessionManager
from models.entities import Artist, Album, Track, Session
from models.enums import SessionStatus
from utils.logging_config import get_session_logger
from utils.text_utils import clean_artist_name, clean_track_title

class ProcessingStep:
    """Étape de traitement et nettoyage des données"""
    
    def __init__(self, db: Database, session_manager: SessionManager):
        self.db = db
        self.session_manager = session_manager
        self.logger = logging.getLogger(__name__)
    
    async def run(self, session: Session, progress_tracker=None) -> Dict[str, Any]:
        """
        Exécute l'étape de traitement
        
        Args:
            session: Session d'extraction
            progress_tracker: Tracker de progression optionnel
            
        Returns:
            Résultats du traitement
        """
        logger = get_session_logger(session.id, "processing")
        logger.info("🚀 Début de l'étape de traitement")
        
        try:
            # Récupérer l'artiste
            artist = self.db.get_artist_by_name(session.artist_name)
            if not artist:
                raise ValueError(f"Artiste '{session.artist_name}' non trouvé")
            
            logger.info(f"🔄 Traitement des données pour {artist.name}")
            
            # Initialiser le tracker
            if progress_tracker:
                step_name = "processing"
                if step_name not in progress_tracker.steps:
                    progress_tracker.add_step(step_name, "Traitement des données", 100)
                progress_tracker.start_step(step_name)
            
            # Récupérer les données à traiter
            tracks = self.db.get_tracks_by_artist_id(artist.id)
            albums = self.db.get_albums_by_artist_id(artist.id)
            
            logger.info(f"📊 Traitement de {len(tracks)} tracks et {len(albums)} albums")
            
            # Traitement des données (exemple basique)
            processed_tracks = 0
            processed_albums = 0
            
            # Nettoyer les titres de tracks
            for track in tracks:
                if track.title:
                    original_title = track.title
                    track.title = clean_track_title(track.title)
                    if track.title != original_title:
                        self.db.update_track(track)
                        processed_tracks += 1
            
            # Nettoyer les noms d'albums
            for album in albums:
                if album.title:
                    original_title = album.title
                    # Appliquer un nettoyage basique
                    album.title = album.title.strip()
                    if album.title != original_title:
                        self.db.update_album(album)
                        processed_albums += 1
            
            processing_results = {
                'artist_id': artist.id,
                'tracks_processed': processed_tracks,
                'albums_processed': processed_albums,
                'total_tracks': len(tracks),
                'total_albums': len(albums)
            }
            
            # Mettre à jour la session
            session.status = SessionStatus.PROCESSING
            session.current_step = "processing"
            session.progress = 75
            session.updated_at = datetime.utcnow()
            self.session_manager.update_session(session)
            
            logger.info(f"✅ Traitement terminé: {processed_tracks} tracks et {processed_albums} albums traités")
            return processing_results
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du traitement: {e}")
            session.status = SessionStatus.ERROR
            session.error_message = str(e)
            self.session_manager.update_session(session)
            raise
