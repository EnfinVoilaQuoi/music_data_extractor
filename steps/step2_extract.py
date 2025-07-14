# steps/step2_extract.py
import logging
import time
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from ..models.entities import Track, Album, Credit, Artist
from ..models.enums import SessionStatus, ExtractionStatus, DataSource, ProcessingStep
from ..extractors.genius_extractor import GeniusExtractor
from ..extractors.spotify_extractor import SpotifyExtractor
from ..extractors.credit_extractor import CreditExtractor
from ..core.database import Database
from ..core.session_manager import SessionManager, get_session_manager
from ..core.exceptions import ExtractionError, APIRateLimitError
from ..config.settings import settings
from ..utils.text_utils import clean_text, normalize_title

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
        
        # Extracteurs
        self.genius_extractor = GeniusExtractor()
        self.spotify_extractor = SpotifyExtractor()
        self.credit_extractor = CreditExtractor()
        
        # Configuration
        self.config = {
            'batch_size': settings.get('extraction.batch_size', 10),
            'max_workers': settings.get('extraction.max_workers', 3),
            'retry_failed': settings.get('extraction.retry_failed', True),
            'max_retries': settings.get('extraction.max_retries', 2),
            'enable_spotify': settings.get('extraction.enable_spotify', True),
            'enable_genius_detailed': settings.get('extraction.enable_genius_detailed', True),
            'extract_lyrics': settings.get('extraction.extract_lyrics', False),
            'delay_between_batches': settings.get('extraction.delay_between_batches', 2.0)
        }
        
        # Locks pour thread safety
        self._stats_lock = Lock()
        self._db_lock = Lock()
        
        self.logger.info("ExtractionStep initialisé")
    
    def extract_tracks_data(self, session_id: str, 
                          force_refresh: bool = False) -> Tuple[List[Track], ExtractionStats]:
        """
        Extrait les données détaillées pour tous les morceaux d'une session.
        
        Args:
            session_id: ID de la session
            force_refresh: Force la ré-extraction même si déjà fait
            
        Returns:
            Tuple[List[Track], ExtractionStats]: Tracks enrichis et statistiques
        """
        start_time = datetime.now()
        
        # Récupération de la session
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ExtractionError(f"Session {session_id} non trouvée")
        
        try:
            self.logger.info(f"🔍 Début de l'extraction pour la session {session_id}")
            
            # Mise à jour de la session
            self.session_manager.update_session(
                session_id,
                current_step="extraction_started"
            )
            
            # Récupération des morceaux à traiter
            tracks_to_process = self._get_tracks_to_process(session, force_refresh)
            
            if not tracks_to_process:
                self.logger.warning("Aucun morceau à traiter")
                return [], ExtractionStats()
            
            # Initialisation des statistiques
            stats = ExtractionStats(total_tracks=len(tracks_to_process))
            
            # Traitement par batches
            all_results = []
            processed_count = 0
            
            for batch_start in range(0, len(tracks_to_process), self.config['batch_size']):
                batch_end = min(batch_start + self.config['batch_size'], len(tracks_to_process))
                batch_tracks = tracks_to_process[batch_start:batch_end]
                
                self.logger.info(f"Traitement du batch {batch_start//self.config['batch_size'] + 1}: "
                               f"morceaux {batch_start + 1}-{batch_end}")
                
                # Traitement parallèle du batch
                batch_results = self._process_batch_parallel(batch_tracks)
                all_results.extend(batch_results)
                
                # Mise à jour des statistiques et de la session
                processed_count += len(batch_tracks)
                self._update_stats_from_results(stats, batch_results)
                
                # Sauvegarde progressive
                successful_tracks = [r.track for r in batch_results if r.success]
                self._save_tracks_batch(successful_tracks)
                
                # Mise à jour de la session
                self.session_manager.update_progress(
                    session_id,
                    tracks_processed=processed_count,
                    tracks_with_credits=stats.tracks_with_credits
                )
                
                # Pause entre les batches pour respecter le rate limiting
                if batch_end < len(tracks_to_process):
                    time.sleep(self.config['delay_between_batches'])
            
            # Calcul du temps total
            end_time = datetime.now()
            stats.extraction_time_seconds = (end_time - start_time).total_seconds()
            stats.average_time_per_track = (stats.extraction_time_seconds / 
                                           max(stats.total_tracks, 1))
            
            # Finalisation
            successful_tracks = [r.track for r in all_results if r.success]
            
            # Mise à jour finale de la session
            self.session_manager.update_session(
                session_id,
                current_step="extraction_completed",
                tracks_processed=stats.successful_extractions,
                tracks_with_credits=stats.tracks_with_credits
            )
            
            self.logger.info(
                f"✅ Extraction terminée: {stats.successful_extractions}/{stats.total_tracks} "
                f"réussies ({stats.tracks_with_credits} avec crédits) "
                f"en {stats.extraction_time_seconds:.1f}s"
            )
            
            return successful_tracks, stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de l'extraction: {e}")
            self.session_manager.fail_session(session_id, str(e))
            raise ExtractionError(f"Échec de l'extraction: {e}")
    
    def _get_tracks_to_process(self, session, force_refresh: bool) -> List[Track]:
        """Récupère les morceaux à traiter pour la session"""
        try:
            # Récupération de l'artiste
            artist = self.database.get_artist_by_name(session.artist_name)
            if not artist:
                raise ExtractionError(f"Artiste '{session.artist_name}' non trouvé")
            
            # Récupération des morceaux
            all_tracks = self.database.get_tracks_by_artist_id(artist.id)
            
            if force_refresh:
                # Traiter tous les morceaux
                tracks_to_process = all_tracks
            else:
                # Traiter seulement ceux qui n'ont pas été extraits
                tracks_to_process = [
                    track for track in all_tracks
                    if track.extraction_status in [ExtractionStatus.PENDING, ExtractionStatus.FAILED]
                ]
            
            self.logger.info(f"Morceaux à traiter: {len(tracks_to_process)}/{len(all_tracks)}")
            return tracks_to_process
            
        except Exception as e:
            self.logger.error(f"Erreur récupération morceaux: {e}")
            return []
    
    def _process_batch_parallel(self, tracks: List[Track]) -> List[TrackExtractionResult]:
        """Traite un batch de morceaux en parallèle"""
        results = []
        
        # Traitement parallèle avec limitation du nombre de threads
        with ThreadPoolExecutor(max_workers=self.config['max_workers']) as executor:
            # Soumission des tâches
            future_to_track = {
                executor.submit(self._extract_single_track, track): track
                for track in tracks
            }
            
            # Récupération des résultats
            for future in as_completed(future_to_track):
                track = future_to_track[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Erreur extraction track '{track.title}': {e}")
                    error_result = TrackExtractionResult(
                        track=track,
                        success=False,
                        errors=[str(e)]
                    )
                    results.append(error_result)
        
        return results
    
    def _extract_single_track(self, track: Track) -> TrackExtractionResult:
        """Extrait les données d'un seul morceau"""
        start_time = time.time()
        result = TrackExtractionResult(track=track, success=False)
        
        try:
            self.logger.debug(f"Extraction: {track.title}")
            
            # 1. Extraction des crédits (priorité absolue)
            credits_success = self._extract_track_credits(track, result)
            
            # 2. Enrichissement avec Spotify (BPM, audio features)
            if self.config['enable_spotify']:
                spotify_success = self._enrich_with_spotify(track, result)
            
            # 3. Extraction Genius détaillée (paroles, métadonnées)
            if self.config['enable_genius_detailed']:
                genius_success = self._extract_genius_details(track, result)
            
            # 4. Résolution de l'album si possible
            album_success = self._resolve_track_album(track, result)
            
            # Détermination du succès global
            result.success = credits_success or spotify_success or genius_success
            
            # Mise à jour du statut d'extraction
            if result.success:
                track.extraction_status = ExtractionStatus.COMPLETED
                track.extraction_date = datetime.now()
            else:
                track.extraction_status = ExtractionStatus.FAILED
            
            track.updated_at = datetime.now()
            
        except Exception as e:
            self.logger.error(f"Erreur extraction {track.title}: {e}")
            result.errors.append(str(e))
            result.success = False
            track.extraction_status = ExtractionStatus.FAILED
        
        result.extraction_time = time.time() - start_time
        return result
    
    def _extract_track_credits(self, track: Track, result: TrackExtractionResult) -> bool:
        """Extrait les crédits d'un morceau"""
        try:
            # Utilisation du CreditExtractor intelligent
            extraction_result = self.credit_extractor.extract_track_credits(track)
            
            if extraction_result.success:
                # Mise à jour des crédits du track
                new_credits = extraction_result.data.get('credits', [])
                
                # Conversion des dictionnaires en entités Credit
                for credit_dict in new_credits:
                    try:
                        from ..models.entities import Credit
                        from ..models.enums import CreditType, CreditCategory, DataSource
                        
                        credit = Credit(
                            track_id=track.id,
                            credit_category=CreditCategory(credit_dict.get('credit_category', 'other')),
                            credit_type=CreditType(credit_dict.get('credit_type', 'other')),
                            person_name=credit_dict.get('person_name', ''),
                            role_detail=credit_dict.get('role_detail'),
                            instrument=credit_dict.get('instrument'),
                            is_primary=credit_dict.get('is_primary', False),
                            is_featuring=credit_dict.get('is_featuring', False),
                            data_source=DataSource(credit_dict.get('data_source', 'manual')),
                            extraction_date=datetime.now()
                        )
                        track.credits.append(credit)
                    except Exception as e:
                        self.logger.warning(f"Erreur conversion crédit: {e}")
                
                result.credits_found = len(new_credits)
                if new_credits:
                    result.track.add_data_source(DataSource.GENIUS)  # Source principale pour crédits
                
                self.logger.debug(f"Crédits extraits pour {track.title}: {len(new_credits)}")
                return True
            else:
                result.errors.append(f"Échec extraction crédits: {extraction_result.error}")
                return False
                
        except Exception as e:
            self.logger.warning(f"Erreur extraction crédits pour {track.title}: {e}")
            result.errors.append(f"Erreur extraction crédits: {e}")
            return False
    
    def _enrich_with_spotify(self, track: Track, result: TrackExtractionResult) -> bool:
        """Enrichit un morceau avec les données Spotify"""
        try:
            # Recherche du morceau sur Spotify s'il n'a pas d'ID
            spotify_id = track.spotify_id
            
            if not spotify_id:
                spotify_id = self._find_track_on_spotify(track)
                if spotify_id:
                    track.spotify_id = spotify_id
            
            if not spotify_id:
                return False
            
            # Extraction des données Spotify
            extraction_result = self.spotify_extractor.extract_track_info(
                spotify_id,
                include_audio_features=True
            )
            
            if extraction_result.success:
                spotify_data = extraction_result.data
                
                # Enrichissement avec les audio features
                audio_features = spotify_data.get('audio_features', {})
                if audio_features:
                    track.bpm = audio_features.get('tempo')
                    track.key = audio_features.get('key')
                    
                    # Durée si pas déjà présente
                    if not track.duration_seconds and spotify_data.get('duration_seconds'):
                        track.duration_seconds = spotify_data['duration_seconds']
                
                # Informations d'album
                album_info = spotify_data.get('album', {})
                if album_info and not track.album_title:
                    track.album_title = album_info.get('name')
                    track.release_date = album_info.get('release_date')
                    track.release_year = spotify_data.get('release_year')
                
                # Features
                featuring_artists = spotify_data.get('featuring_artists', [])
                for featuring in featuring_artists:
                    track.add_featuring_artist(featuring)
                
                track.add_data_source(DataSource.SPOTIFY)
                result.spotify_data_found = True
                
                self.logger.debug(f"Données Spotify ajoutées pour {track.title}")
                return True
            else:
                result.errors.append(f"Échec Spotify: {extraction_result.error}")
                return False
                
        except Exception as e:
            self.logger.warning(f"Erreur enrichissement Spotify pour {track.title}: {e}")
            result.errors.append(f"Erreur Spotify: {e}")
            return False
    
    def _extract_genius_details(self, track: Track, result: TrackExtractionResult) -> bool:
        """Extrait les détails Genius (paroles, métadonnées)"""
        try:
            if not track.genius_id:
                return False
            
            # Extraction détaillée depuis Genius
            extraction_result = self.genius_extractor.extract_track_info(
                str(track.genius_id),
                include_lyrics=self.config['extract_lyrics'],
                include_credits=True  # Pour compléter les crédits
            )
            
            if extraction_result.success:
                genius_data = extraction_result.data
                
                # Paroles
                if self.config['extract_lyrics'] and genius_data.get('lyrics'):
                    track.lyrics = genius_data['lyrics']
                    track.has_lyrics = True
                
                # Métadonnées additionnelles
                if not track.release_date and genius_data.get('release_date'):
                    track.release_date = genius_data['release_date']
                
                # Album si pas déjà présent
                album_info = genius_data.get('album', {})
                if album_info and not track.album_title:
                    track.album_title = album_info.get('name')
                
                # Features depuis Genius
                featuring_artists = genius_data.get('featured_artists', [])
                for featuring in featuring_artists:
                    track.add_featuring_artist(featuring)
                
                track.add_data_source(DataSource.GENIUS)
                result.genius_data_found = True
                
                self.logger.debug(f"Détails Genius ajoutés pour {track.title}")
                return True
            else:
                result.errors.append(f"Échec Genius: {extraction_result.error}")
                return False
                
        except Exception as e:
            self.logger.warning(f"Erreur extraction Genius pour {track.title}: {e}")
            result.errors.append(f"Erreur Genius: {e}")
            return False
    
    def _resolve_track_album(self, track: Track, result: TrackExtractionResult) -> bool:
        """Résout et associe l'album du morceau"""
        try:
            if not track.album_title:
                return False
            
            # Recherche ou création de l'album
            album = self._find_or_create_album(track)
            
            if album:
                track.album_id = album.id
                self.logger.debug(f"Album résolu pour {track.title}: {album.title}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Erreur résolution album pour {track.title}: {e}")
            result.errors.append(f"Erreur album: {e}")
            return False
    
    def _find_track_on_spotify(self, track: Track) -> Optional[str]:
        """Recherche un morceau sur Spotify par titre et artiste"""
        try:
            # Construction de la requête de recherche
            query = f"{track.title} {track.artist_name}"
            
            search_result = self.spotify_extractor.search_tracks(query, limit=5)
            
            if search_result.success:
                results = search_result.data.get('results', [])
                
                # Recherche du meilleur match
                for result in results:
                    if self._is_good_spotify_match(track, result):
                        return result.get('spotify_id')
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Erreur recherche Spotify pour {track.title}: {e}")
            return None
    
    def _is_good_spotify_match(self, track: Track, spotify_result: Dict[str, Any]) -> bool:
        """Vérifie si un résultat Spotify correspond bien au morceau"""
        # Comparaison des titres
        spotify_title = normalize_title(spotify_result.get('name', ''))
        track_title = normalize_title(track.title)
        
        title_match = spotify_title == track_title or spotify_title in track_title or track_title in spotify_title
        
        # Comparaison des artistes
        spotify_artist = spotify_result.get('artist', '').lower()
        track_artist = track.artist_name.lower()
        
        artist_match = spotify_artist == track_artist or spotify_artist in track_artist or track_artist in spotify_artist
        
        return title_match and artist_match
    
    def _find_or_create_album(self, track: Track) -> Optional[Album]:
        """Trouve ou crée un album pour le morceau"""
        try:
            # Recherche d'un album existant
            # Note: Implémentation simplifiée, pourrait être plus sophistiquée
            
            album_title = track.album_title.strip()
            if not album_title:
                return None
            
            # Création d'un nouvel album (logique simplifiée)
            from ..models.entities import Album
            from ..models.enums import AlbumType
            
            album = Album(
                title=album_title,
                artist_id=track.artist_id,
                artist_name=track.artist_name,
                release_date=track.release_date,
                release_year=track.release_year,
                album_type=AlbumType.ALBUM,  # Par défaut
                created_at=datetime.now()
            )
            
            # Sauvegarde en base (thread-safe)
            with self._db_lock:
                album_id = self.database.create_album(album)
                album.id = album_id
            
            return album
            
        except Exception as e:
            self.logger.warning(f"Erreur création album '{track.album_title}': {e}")
            return None
    
    def _update_stats_from_results(self, stats: ExtractionStats, results: List[TrackExtractionResult]):
        """Met à jour les statistiques depuis les résultats de batch"""
        with self._stats_lock:
            for result in results:
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
    
    def _save_tracks_batch(self, tracks: List[Track]):
        """Sauvegarde un batch de morceaux en base de données"""
        try:
            with self._db_lock:
                for track in tracks:
                    # Mise à jour du morceau
                    self.database.update_track(track)
                    
                    # Sauvegarde des nouveaux crédits
                    for credit in track.credits:
                        if not credit.id:  # Nouveau crédit
                            self.database.create_credit(credit)
            
            self.logger.debug(f"Batch sauvegardé: {len(tracks)} morceaux")
            
        except Exception as e:
            self.logger.error(f"Erreur sauvegarde batch: {e}")
    
    def retry_failed_extractions(self, session_id: str) -> Tuple[List[Track], ExtractionStats]:
        """Relance l'extraction pour les morceaux échoués"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                raise ExtractionError(f"Session {session_id} non trouvée")
            
            # Récupération des morceaux échoués
            artist = self.database.get_artist_by_name(session.artist_name)
            all_tracks = self.database.get_tracks_by_artist_id(artist.id)
            
            failed_tracks = [
                track for track in all_tracks
                if track.extraction_status == ExtractionStatus.FAILED
            ]
            
            if not failed_tracks:
                self.logger.info("Aucun morceau échoué à relancer")
                return [], ExtractionStats()
            
            self.logger.info(f"Relance de l'extraction pour {len(failed_tracks)} morceaux échoués")
            
            # Traitement avec retry
            results = []
            for track in failed_tracks:
                for attempt in range(self.config['max_retries']):
                    try:
                        result = self._extract_single_track(track)
                        results.append(result)
                        
                        if result.success:
                            break  # Succès, pas besoin de retry
                        else:
                            time.sleep(2 ** attempt)  # Backoff exponentiel
                            
                    except Exception as e:
                        self.logger.warning(f"Tentative {attempt + 1} échouée pour {track.title}: {e}")
                        if attempt == self.config['max_retries'] - 1:
                            # Dernière tentative échouée
                            error_result = TrackExtractionResult(
                                track=track,
                                success=False,
                                errors=[str(e)]
                            )
                            results.append(error_result)
            
            # Compilation des statistiques
            stats = ExtractionStats(total_tracks=len(failed_tracks))
            self._update_stats_from_results(stats, results)
            
            # Sauvegarde
            successful_tracks = [r.track for r in results if r.success]
            self._save_tracks_batch(successful_tracks)
            
            self.logger.info(f"Retry terminé: {stats.successful_extractions}/{len(failed_tracks)} réussies")
            
            return successful_tracks, stats
            
        except Exception as e:
            self.logger.error(f"Erreur retry extractions: {e}")
            raise ExtractionError(f"Échec du retry: {e}")
    
    def extract_specific_tracks(self, track_ids: List[int], 
                              force_refresh: bool = False) -> List[TrackExtractionResult]:
        """Extrait des morceaux spécifiques par leurs IDs"""
        try:
            tracks = []
            for track_id in track_ids:
                # Récupération du morceau depuis la base
                # Note: Nécessiterait une méthode get_track_by_id dans Database
                pass
            
            # Traitement des morceaux sélectionnés
            results = []
            for track in tracks:
                if force_refresh or track.extraction_status != ExtractionStatus.COMPLETED:
                    result = self._extract_single_track(track)
                    results.append(result)
            
            # Sauvegarde
            successful_tracks = [r.track for r in results if r.success]
            self._save_tracks_batch(successful_tracks)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Erreur extraction spécifique: {e}")
            return []
    
    def get_extraction_progress(self, session_id: str) -> Dict[str, Any]:
        """Récupère le progrès de l'extraction pour une session"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {}
            
            # Récupération des morceaux pour calculer les détails
            artist = self.database.get_artist_by_name(session.artist_name)
            if not artist:
                return {}
            
            all_tracks = self.database.get_tracks_by_artist_id(artist.id)
            
            # Calcul des statistiques détaillées
            stats = {
                'session_id': session_id,
                'artist_name': session.artist_name,
                'total_tracks': len(all_tracks),
                'completed': len([t for t in all_tracks if t.extraction_status == ExtractionStatus.COMPLETED]),
                'failed': len([t for t in all_tracks if t.extraction_status == ExtractionStatus.FAILED]),
                'pending': len([t for t in all_tracks if t.extraction_status == ExtractionStatus.PENDING]),
                'with_credits': len([t for t in all_tracks if t.credits]),
                'with_bpm': len([t for t in all_tracks if t.bpm]),
                'with_albums': len([t for t in all_tracks if t.album_title]),
                'progress_percentage': session.get_progress_percentage(),
                'current_step': session.current_step,
                'updated_at': session.updated_at.isoformat() if session.updated_at else None
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Erreur récupération progrès: {e}")
            return {}
    
    def validate_extraction_quality(self, session_id: str) -> Dict[str, Any]:
        """Valide la qualité de l'extraction"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {}
            
            artist = self.database.get_artist_by_name(session.artist_name)
            tracks = self.database.get_tracks_by_artist_id(artist.id)
            
            validation = {
                'total_tracks': len(tracks),
                'quality_metrics': {
                    'tracks_with_credits': len([t for t in tracks if t.credits]),
                    'tracks_with_producer': len([t for t in tracks if any(c.credit_type.value == 'producer' for c in t.credits)]),
                    'tracks_with_bpm': len([t for t in tracks if t.bpm]),
                    'tracks_with_duration': len([t for t in tracks if t.duration_seconds]),
                    'tracks_with_albums': len([t for t in tracks if t.album_title]),
                    'tracks_with_lyrics': len([t for t in tracks if t.has_lyrics]),
                },
                'data_sources': {},
                'issues': [],
                'recommendations': []
            }
            
            # Analyse des sources de données
            source_counts = {}
            for track in tracks:
                for source in track.data_sources:
                    source_counts[source.value] = source_counts.get(source.value, 0) + 1
            validation['data_sources'] = source_counts
            
            # Calcul du score de qualité global
            total = len(tracks)
            if total > 0:
                quality_score = (
                    validation['quality_metrics']['tracks_with_credits'] * 0.4 +
                    validation['quality_metrics']['tracks_with_producer'] * 0.3 +
                    validation['quality_metrics']['tracks_with_bpm'] * 0.2 +
                    validation['quality_metrics']['tracks_with_albums'] * 0.1
                ) / total
                
                validation['quality_score'] = quality_score
                validation['quality_level'] = self._determine_quality_level(quality_score)
            
            # Identification des problèmes
            if validation['quality_metrics']['tracks_with_credits'] < total * 0.5:
                validation['issues'].append("Moins de 50% des morceaux ont des crédits")
                validation['recommendations'].append("Améliorer l'extraction des crédits depuis Genius")
            
            if validation['quality_metrics']['tracks_with_bpm'] < total * 0.3:
                validation['issues'].append("Peu de morceaux ont des données BPM")
                validation['recommendations'].append("Améliorer la couverture Spotify")
            
            return validation
            
        except Exception as e:
            self.logger.error(f"Erreur validation qualité: {e}")
            return {}
    
    def _determine_quality_level(self, score: float) -> str:
        """Détermine le niveau de qualité basé sur le score"""
        if score >= 0.9:
            return "Excellent"
        elif score >= 0.75:
            return "Bon"
        elif score >= 0.5:
            return "Moyen"
        elif score >= 0.25:
            return "Faible"
        else:
            return "Très faible"
    
    def cleanup_extraction_data(self, session_id: str):
        """Nettoie les données d'extraction temporaires"""
        try:
            # Nettoyage des caches des extracteurs
            self.credit_extractor.clear_cache()
            
            # Autres nettoyages si nécessaire
            self.logger.info(f"Données d'extraction nettoyées pour la session {session_id}")
            
        except Exception as e:
            self.logger.error(f"Erreur nettoyage: {e}")
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques globales d'extraction"""
        return {
            'genius_extractor_stats': self.genius_extractor.get_stats(),
            'spotify_extractor_stats': self.spotify_extractor.get_stats(),
            'credit_extractor_stats': self.credit_extractor.get_extraction_stats(),
            'config': self.config
        }