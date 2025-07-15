# steps/step2_extract.py
import logging
import time
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# IMPORTS ABSOLUS - CORRECTION MAJEURE
from models.entities import Track, Album, Credit, Artist
from models.enums import SessionStatus, ExtractionStatus, DataSource
from core.database import Database
from core.session_manager import SessionManager, get_session_manager
from core.exceptions import ExtractionError, APIRateLimitError
from config.settings import settings
from utils.text_utils import clean_track_title, normalize_text

# Imports conditionnels pour les extracteurs (peuvent ne pas exister)
try:
    from extractors.genius_extractor import GeniusExtractor
except (ImportError, SyntaxError) as e:
    print(f"⚠️ GeniusExtractor non disponible: {e}")
    GeniusExtractor = None

try:
    from extractors.spotify_extractor import SpotifyExtractor
except (ImportError, SyntaxError) as e:
    print(f"⚠️ SpotifyExtractor non disponible: {e}")
    SpotifyExtractor = None

try:
    from extractors.credit_extractor import CreditExtractor
except (ImportError, SyntaxError) as e:
    print(f"⚠️ CreditExtractor non disponible: {e}")
    CreditExtractor = None

@dataclass
class ExtractionStats:
    """Statistiques de l'extraction"""
    total_tracks: int = 0
    successful_extractions: int = 0
    failed_extractions: int = 0
    tracks_with_credits: int = 0
    tracks_with_spotify_data: int = 0
    tracks_with_genius_data: int = 0
    api_calls_made: int = 0
    extraction_time_seconds: float = 0.0
    average_time_per_track: float = 0.0

@dataclass
class TrackExtractionResult:
    """Résultat d'extraction pour un track"""
    track: Track
    success: bool
    credits_found: int = 0
    spotify_data_found: bool = False
    genius_data_found: bool = False
    errors: List[str] = None
    extraction_time: float = 0.0
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []

class ExtractionStep:
    """
    Étape 2 : Extraction détaillée des données des morceaux.
    
    Responsabilités :
    - Extraction des crédits complets depuis toutes les sources
    - Enrichissement avec données Spotify (BPM, audio features)
    - Extraction des informations d'albums
    - Gestion parallèle et rate limiting
    - Mise à jour progressive de la base de données
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None,
                 database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        
        # Composants
        self.session_manager = session_manager or get_session_manager()
        self.database = database or Database()
        
        # Extracteurs (conditionnels)
        self.genius_extractor = GeniusExtractor() if GeniusExtractor else None
        self.spotify_extractor = SpotifyExtractor() if SpotifyExtractor else None
        self.credit_extractor = CreditExtractor() if CreditExtractor else None
        
        # Configuration
        self.config = {
            'batch_size': settings.get('extraction.batch_size', 10),
            'max_workers': settings.get('extraction.max_workers', 3),
            'retry_failed': settings.get('extraction.retry_failed', True),
            'max_retries': settings.get('extraction.max_retries', 2),
            'enable_spotify': settings.get('extraction.enable_spotify', True) and self.spotify_extractor is not None,
            'enable_genius_detailed': settings.get('extraction.enable_genius_detailed', True) and self.genius_extractor is not None,
            'extract_lyrics': settings.get('extraction.extract_lyrics', False),
            'delay_between_batches': settings.get('extraction.delay_between_batches', 2.0)
        }
        
        # Locks pour thread safety
        self._stats_lock = Lock()
        self._db_lock = Lock()
        
        available_extractors = []
        if self.genius_extractor:
            available_extractors.append("Genius")
        if self.spotify_extractor:
            available_extractors.append("Spotify")
        if self.credit_extractor:
            available_extractors.append("Credits")
        
        self.logger.info(f"ExtractionStep initialisé avec extracteurs: {', '.join(available_extractors) if available_extractors else 'Aucun'}")
    
    def extract_tracks_data(self, session_id: str, 
                          force_refresh: bool = False) -> Tuple[List[Track], ExtractionStats]:
        """
        Extrait les données détaillées pour tous les morceaux d'une session.
        
        Args:
            session_id: ID de la session
            force_refresh: Forcer la ré-extraction même si les données existent
            
        Returns:
            Tuple (tracks mis à jour, statistiques)
        """
        start_time = datetime.now()
        stats = ExtractionStats()
        
        try:
            self.logger.info(f"🔧 Début extraction détaillée pour session: {session_id}")
            
            # Récupérer la session
            session = self.session_manager.get_session(session_id)
            if not session:
                raise ExtractionError(f"Session {session_id} non trouvée")
            
            # Récupérer les tracks à traiter
            artist = self.database.get_artist_by_name(session.artist_name)
            if not artist:
                raise ExtractionError(f"Artiste '{session.artist_name}' non trouvé")
            
            tracks = self.database.get_tracks_by_artist_id(artist.id)
            if not tracks:
                raise ExtractionError("Aucun morceau trouvé pour cet artiste")
            
            stats.total_tracks = len(tracks)
            self.logger.info(f"📋 {stats.total_tracks} morceaux à traiter")
            
            # Mettre à jour le statut de la session
            session.current_step = "extraction_started"
            session.total_tracks_found = stats.total_tracks
            self.session_manager.update_session(session)
            
            # Traitement par lots
            processed_tracks = []
            batch_size = self.config['batch_size']
            
            for i in range(0, len(tracks), batch_size):
                batch = tracks[i:i + batch_size]
                batch_results = self._process_batch(batch, session_id, force_refresh)
                
                # Compiler les résultats
                for result in batch_results:
                    processed_tracks.append(result.track)
                    
                    with self._stats_lock:
                        if result.success:
                            stats.successful_extractions += 1
                        else:
                            stats.failed_extractions += 1
                        
                        if result.credits_found > 0:
                            stats.tracks_with_credits += 1
                        if result.spotify_data_found:
                            stats.tracks_with_spotify_data += 1
                        if result.genius_data_found:
                            stats.tracks_with_genius_data += 1
                
                # Mettre à jour la progression
                progress = len(processed_tracks)
                session.tracks_processed = progress
                self.session_manager.update_session(session)
                
                self.logger.info(f"📊 Lot traité: {progress}/{stats.total_tracks} morceaux")
                
                # Délai entre les lots pour éviter le rate limiting
                if i + batch_size < len(tracks):
                    time.sleep(self.config['delay_between_batches'])
            
            # Calcul des statistiques finales
            end_time = datetime.now()
            stats.extraction_time_seconds = (end_time - start_time).total_seconds()
            if stats.total_tracks > 0:
                stats.average_time_per_track = stats.extraction_time_seconds / stats.total_tracks
            
            # Mettre à jour le statut final
            session.current_step = "extraction_completed"
            session.tracks_with_credits = stats.tracks_with_credits
            session.status = SessionStatus.COMPLETED
            self.session_manager.update_session(session)
            
            self.logger.info(f"✅ Extraction terminée: {stats.successful_extractions}/{stats.total_tracks} réussies en {stats.extraction_time_seconds:.1f}s")
            
            return processed_tracks, stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de l'extraction: {e}")
            # Marquer la session comme échouée
            if 'session' in locals():
                session.status = SessionStatus.FAILED
                session.last_error = str(e)
                self.session_manager.update_session(session)
            raise ExtractionError(f"Erreur extraction session {session_id}: {e}")
    
    def _process_batch(self, tracks: List[Track], session_id: str, 
                      force_refresh: bool) -> List[TrackExtractionResult]:
        """Traite un lot de tracks en parallèle"""
        results = []
        
        # Si pas d'extracteurs disponibles, créer des résultats de base
        if not any([self.genius_extractor, self.spotify_extractor, self.credit_extractor]):
            self.logger.warning("⚠️ Aucun extracteur disponible, extraction de base seulement")
            for track in tracks:
                result = TrackExtractionResult(
                    track=track,
                    success=True,
                    errors=["Aucun extracteur disponible"]
                )
                results.append(result)
            return results
        
        # Traitement parallèle si des extracteurs sont disponibles
        max_workers = min(self.config['max_workers'], len(tracks))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_track = {
                executor.submit(self._extract_single_track, track, force_refresh): track
                for track in tracks
            }
            
            for future in as_completed(future_to_track):
                track = future_to_track[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Erreur extraction track '{track.title}': {e}")
                    result = TrackExtractionResult(
                        track=track,
                        success=False,
                        errors=[str(e)]
                    )
                    results.append(result)
        
        return results
    
    def _extract_single_track(self, track: Track, force_refresh: bool) -> TrackExtractionResult:
        """Extrait les données d'un seul morceau"""
        start_time = time.time()
        result = TrackExtractionResult(track=track, success=True)
        
        try:
            # Nettoyer le titre
            clean_title = clean_track_title(track.title)
            if clean_title != track.title:
                track.title = clean_title
                self.logger.debug(f"Titre nettoyé: {track.title}")
            
            # Extraction Genius détaillée
            if self.config['enable_genius_detailed'] and self.genius_extractor:
                try:
                    genius_result = self._extract_genius_data(track, force_refresh)
                    if genius_result:
                        result.genius_data_found = True
                        # Ajouter les données Genius au track
                        if genius_result.get('lyrics'):
                            track.lyrics = genius_result['lyrics']
                            track.has_lyrics = True
                except Exception as e:
                    result.errors.append(f"Genius: {e}")
            
            # Extraction Spotify
            if self.config['enable_spotify'] and self.spotify_extractor:
                try:
                    spotify_result = self._extract_spotify_data(track, force_refresh)
                    if spotify_result:
                        result.spotify_data_found = True
                        # Ajouter les données Spotify au track
                        if spotify_result.get('bpm'):
                            track.bpm = spotify_result['bpm']
                        if spotify_result.get('duration_ms'):
                            track.duration = spotify_result['duration_ms'] // 1000
                except Exception as e:
                    result.errors.append(f"Spotify: {e}")
            
            # Extraction des crédits
            if self.credit_extractor:
                try:
                    credits = self._extract_credits(track, force_refresh)
                    if credits:
                        result.credits_found = len(credits)
                        track.credits = credits
                except Exception as e:
                    result.errors.append(f"Credits: {e}")
            
            # Sauvegarder le track mis à jour
            with self._db_lock:
                track.extraction_status = ExtractionStatus.COMPLETED
                track.updated_at = datetime.now()
                self.database.update_track(track)
            
            result.extraction_time = time.time() - start_time
            
        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            self.logger.error(f"Erreur extraction '{track.title}': {e}")
        
        return result
    
    def _extract_genius_data(self, track: Track, force_refresh: bool) -> Optional[Dict[str, Any]]:
        """Extrait les données détaillées depuis Genius"""
        if not track.genius_id:
            return None
        
        # Simuler l'extraction Genius (à implémenter selon votre extracteur)
        self.logger.debug(f"Extraction Genius pour: {track.title}")
        
        # Placeholder - à remplacer par votre implémentation
        return {
            'lyrics': f"Paroles simulées pour {track.title}",
            'genius_url': f"https://genius.com/songs/{track.genius_id}"
        }
    
    def _extract_spotify_data(self, track: Track, force_refresh: bool) -> Optional[Dict[str, Any]]:
        """Extrait les données depuis Spotify"""
        # Simuler l'extraction Spotify
        self.logger.debug(f"Extraction Spotify pour: {track.title}")
        
        # Placeholder - à remplacer par votre implémentation
        return {
            'bpm': 120,  # BPM simulé
            'duration_ms': 180000,  # 3 minutes
            'energy': 0.8,
            'danceability': 0.7
        }
    
    def _extract_credits(self, track: Track, force_refresh: bool) -> List[Credit]:
        """Extrait les crédits du morceau"""
        # Simuler l'extraction de crédits
        self.logger.debug(f"Extraction crédits pour: {track.title}")
        
        # Placeholder - à remplacer par votre implémentation
        credits = []
        
        # Créer un crédit de producteur simulé
        if "prod" in track.title.lower() or "beat" in track.title.lower():
            credit = Credit(
                track_id=track.id,
                credit_type=CreditType.PRODUCER,
                person_name="Producteur Simulé",
                data_source=DataSource.GENIUS,
                created_at=datetime.now()
            )
            credits.append(credit)
        
        return credits
    
    def get_extraction_progress(self, session_id: str) -> Dict[str, Any]:
        """Retourne la progression de l'extraction"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {"error": "Session non trouvée"}
            
            progress_percentage = 0.0
            if session.total_tracks_found > 0:
                progress_percentage = (session.tracks_processed / session.total_tracks_found) * 100
            
            return {
                "session_id": session_id,
                "status": session.status.value,
                "current_step": session.current_step,
                "total_tracks": session.total_tracks_found,
                "processed_tracks": session.tracks_processed,
                "tracks_with_credits": session.tracks_with_credits,
                "progress_percentage": round(progress_percentage, 1),
                "updated_at": session.updated_at.isoformat() if session.updated_at else None
            }
            
        except Exception as e:
            self.logger.error(f"Erreur récupération progression: {e}")
            return {"error": str(e)}