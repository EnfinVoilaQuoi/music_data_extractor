# steps/step1_discover.py
import logging
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from dataclasses import dataclass

# IMPORTS ABSOLUS - CORRECTION MAJEURE
from models.entities import Track, Artist, Session
from models.enums import SessionStatus, ExtractionStatus, DataSource
from discovery.genius_discovery import GeniusDiscovery, DiscoveryResult
from core.database import Database
from core.session_manager import SessionManager, get_session_manager
from core.exceptions import ExtractionError, ArtistNotFoundError
from config.settings import settings
from utils.text_utils import clean_artist_name, normalize_text

# Imports conditionnels pour les modules optionnels
try:
    from extractors.web_scrapers.rapedia_scraper import RapediaScraper
except ImportError:
    RapediaScraper = None

@dataclass
class DiscoveryStats:
    """Statistiques de la découverte"""
    total_found: int = 0
    genius_found: int = 0
    rapedia_found: int = 0
    duplicates_removed: int = 0
    final_count: int = 0
    discovery_time_seconds: float = 0.0

class DiscoveryStep:
    """
    Étape 1 : Découverte des morceaux d'un artiste.
    
    Responsabilités :
    - Recherche de l'artiste sur différentes sources
    - Découverte de tous ses morceaux
    - Déduplication et consolidation
    - Création des entités de base en base de données
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None, 
                 database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        
        # Composants
        self.session_manager = session_manager or get_session_manager()
        self.database = database or Database()
        
        # Découvreurs
        self.genius_discovery = GeniusDiscovery()
        self.rapedia_scraper = RapediaScraper() if RapediaScraper else None
        
        # Configuration
        self.config = {
            'max_tracks_per_source': settings.get('discovery.max_tracks_per_source', 200),
            'enable_rapedia': settings.get('discovery.enable_rapedia', True) and RapediaScraper is not None,
            'enable_genius': settings.get('discovery.enable_genius', True),
            'similarity_threshold': settings.get('discovery.similarity_threshold', 0.85),
            'prefer_verified_sources': settings.get('discovery.prefer_verified_sources', True)
        }
        
        self.logger.info(f"DiscoveryStep initialisé (Genius: {self.config['enable_genius']}, Rapedia: {self.config['enable_rapedia']})")
    
    def discover_artist_tracks(self, artist_name: str, 
                             session_id: Optional[str] = None,
                             max_tracks: Optional[int] = None) -> Tuple[List[Track], DiscoveryStats]:
        """
        Découvre tous les morceaux d'un artiste depuis toutes les sources.
        
        Args:
            artist_name: Nom de l'artiste à rechercher
            session_id: ID de session (optionnel)
            max_tracks: Nombre maximum de tracks à découvrir
            
        Returns:
            Tuple (liste des tracks, statistiques)
        """
        start_time = datetime.now()
        stats = DiscoveryStats()
        
        try:
            self.logger.info(f"🔍 Début découverte pour: {artist_name}")
            
            # Nettoyer le nom de l'artiste
            clean_name = clean_artist_name(artist_name)
            max_tracks = max_tracks or self.config['max_tracks_per_source']
            
            # Créer ou récupérer l'artiste en base
            artist = self._get_or_create_artist(clean_name)
            
            # Créer ou mettre à jour la session
            if session_id:
                session = self.session_manager.get_session(session_id)
                if session:
                    session.current_step = "discovery_started"
                    session.artist_name = clean_name
                    self.session_manager.update_session(session)
            
            # Découverte depuis Genius
            genius_tracks = []
            if self.config['enable_genius']:
                self.logger.info("🎵 Découverte via Genius...")
                genius_result = self.genius_discovery.discover_artist_tracks(clean_name, max_tracks)
                
                if genius_result.success:
                    genius_tracks = self._convert_genius_tracks(genius_result.tracks, artist.id)
                    stats.genius_found = len(genius_tracks)
                    self.logger.info(f"✅ Genius: {stats.genius_found} morceaux trouvés")
                else:
                    self.logger.warning(f"⚠️ Genius: {genius_result.error}")
            
            # Découverte depuis Rapedia (optionnel)
            rapedia_tracks = []
            if self.config['enable_rapedia'] and self.rapedia_scraper:
                self.logger.info("🎵 Découverte via Rapedia...")
                try:
                    # Simuler la découverte Rapedia (implémentation dépend du scraper)
                    rapedia_tracks = []  # À implémenter selon votre scraper
                    stats.rapedia_found = len(rapedia_tracks)
                    self.logger.info(f"✅ Rapedia: {stats.rapedia_found} morceaux trouvés")
                except Exception as e:
                    self.logger.warning(f"⚠️ Rapedia: {e}")
            
            # Consolidation et déduplication
            all_tracks = genius_tracks + rapedia_tracks
            stats.total_found = len(all_tracks)
            
            # Déduplication basée sur le titre et l'artiste
            unique_tracks = self._deduplicate_tracks(all_tracks)
            stats.duplicates_removed = stats.total_found - len(unique_tracks)
            stats.final_count = len(unique_tracks)
            
            # Sauvegarde en base de données
            saved_tracks = []
            for track in unique_tracks:
                try:
                    saved_track = self.database.save_track(track)
                    saved_tracks.append(saved_track)
                except Exception as e:
                    self.logger.error(f"Erreur sauvegarde track '{track.title}': {e}")
            
            # Mettre à jour les statistiques
            if session_id:
                session = self.session_manager.get_session(session_id)
                if session:
                    session.total_tracks_found = len(saved_tracks)
                    session.current_step = "discovery_completed"
                    self.session_manager.update_session(session)
            
            # Calculer le temps d'exécution
            end_time = datetime.now()
            stats.discovery_time_seconds = (end_time - start_time).total_seconds()
            
            self.logger.info(f"✅ Découverte terminée: {stats.final_count} morceaux uniques en {stats.discovery_time_seconds:.1f}s")
            
            return saved_tracks, stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de la découverte: {e}")
            raise ExtractionError(f"Erreur découverte pour {artist_name}: {e}")
    
    def _get_or_create_artist(self, artist_name: str) -> Artist:
        """Récupère ou crée un artiste en base"""
        # Chercher l'artiste existant
        artist = self.database.get_artist_by_name(artist_name)
        
        if not artist:
            # Créer un nouvel artiste
            artist = Artist(
                name=artist_name,
                normalized_name=normalize_text(artist_name),
                extraction_status=ExtractionStatus.IN_PROGRESS,
                created_at=datetime.now()
            )
            artist = self.database.save_artist(artist)
            self.logger.info(f"✨ Nouvel artiste créé: {artist_name}")
        
        return artist
    
    def _convert_genius_tracks(self, genius_tracks: List[Dict[str, Any]], artist_id: int) -> List[Track]:
        """Convertit les données Genius en entités Track"""
        tracks = []
        
        for track_data in genius_tracks:
            try:
                track = Track(
                    title=track_data.get('title', ''),
                    artist_id=artist_id,
                    artist_name=track_data.get('artist_name', ''),
                    genius_id=track_data.get('genius_id'),
                    genius_url=track_data.get('genius_url'),
                    release_date=track_data.get('release_date'),
                    album_name=track_data.get('album_name'),
                    featuring_artists=track_data.get('featured_artists', []),
                    data_sources=[DataSource.GENIUS],
                    extraction_status=ExtractionStatus.PENDING,
                    created_at=datetime.now()
                )
                tracks.append(track)
                
            except Exception as e:
                self.logger.error(f"Erreur conversion track Genius: {e}")
                continue
        
        return tracks
    
    def _deduplicate_tracks(self, tracks: List[Track]) -> List[Track]:
        """Supprime les doublons de la liste de tracks"""
        seen = set()
        unique_tracks = []
        
        for track in tracks:
            # Créer une clé unique basée sur le titre normalisé et l'artiste
            key = f"{normalize_text(track.title).lower()}:{normalize_text(track.artist_name).lower()}"
            
            if key not in seen:
                seen.add(key)
                unique_tracks.append(track)
            else:
                self.logger.debug(f"Doublon supprimé: {track.title}")
        
        return unique_tracks
    
    def resume_discovery(self, session_id: str) -> Tuple[List[Track], DiscoveryStats]:
        """Reprend une découverte interrompue"""
        try:
            self.logger.info(f"🔄 Reprise de la découverte pour session: {session_id}")
            
            session = self.session_manager.get_session(session_id)
            if not session:
                raise ExtractionError(f"Session {session_id} non trouvée")
            
            if session.status != SessionStatus.PAUSED:
                raise ExtractionError(f"Session {session_id} n'est pas en pause")
            
            # Reprendre la découverte
            return self.discover_artist_tracks(
                session.artist_name, 
                session_id=session_id
            )
                    
        except Exception as e:
            self.logger.error(f"Erreur reprise découverte: {e}")
            raise ExtractionError(f"Impossible de reprendre la découverte: {e}")
    
    def get_discovery_status(self, session_id: str) -> Dict[str, Any]:
        """Retourne le statut de la découverte pour une session"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {"error": "Session non trouvée"}
            
            return {
                "session_id": session_id,
                "artist_name": session.artist_name,
                "status": session.status.value,
                "current_step": session.current_step,
                "total_tracks_found": session.total_tracks_found,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None
            }
            
        except Exception as e:
            self.logger.error(f"Erreur récupération statut: {e}")
            return {"error": str(e)}