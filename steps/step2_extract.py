# steps/step2_extract.py
"""Étape 2: Extraction optimisée des données musicales détaillées"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from core.database import Database
from core.session_manager import SessionManager, get_session_manager
from core.rate_limiter import RateLimiter
from core.cache import smart_cache
from core.exceptions import ExtractionError, APIRateLimitError
from models.entities import Artist, Album, Track, Credit, Session
from models.enums import ExtractionStatus, SessionStatus, DataSource, CreditType
from config.settings import settings

# Imports conditionnels des extracteurs
try:
    from extractors.genius_extractor import GeniusExtractor
except ImportError:
    GeniusExtractor = None

try:
    from extractors.spotify_extractor import SpotifyExtractor
except ImportError:
    SpotifyExtractor = None

try:
    from extractors.credit_extractor import CreditExtractor
except ImportError:
    CreditExtractor = None

try:
    from extractors.lyric_extractor import LyricExtractor
except ImportError:
    LyricExtractor = None

@dataclass
class ExtractionBatch:
    """Lot de morceaux pour traitement optimisé"""
    tracks: List[Track]
    batch_id: str
    priority: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> Optional[float]:
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds()

@dataclass
class ExtractionStats:
    """Statistiques détaillées de l'extraction avec optimisations"""
    total_tracks: int = 0
    tracks_processed: int = 0
    tracks_successful: int = 0
    tracks_failed: int = 0
    tracks_skipped: int = 0
    
    # Données extraites
    lyrics_extracted: int = 0
    credits_extracted: int = 0
    albums_extracted: int = 0
    metadata_extracted: int = 0
    
    # Performance
    extraction_time_seconds: float = 0.0
    cache_hits: int = 0
    api_calls: int = 0
    rate_limit_hits: int = 0
    
    # Sources utilisées
    sources_used: List[str] = field(default_factory=list)
    extractors_used: List[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Taux de succès (0-100)"""
        if self.tracks_processed == 0:
            return 0.0
        return (self.tracks_successful / self.tracks_processed) * 100
    
    @property
    def cache_hit_rate(self) -> float:
        """Taux de réussite du cache"""
        total_requests = self.cache_hits + self.api_calls
        if total_requests == 0:
            return 0.0
        return (self.cache_hits / total_requests) * 100
    
    @property
    def extraction_rate(self) -> float:
        """Morceaux traités par seconde"""
        if self.extraction_time_seconds == 0:
            return 0.0
        return self.tracks_processed / self.extraction_time_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour export"""
        return {
            'total_tracks': self.total_tracks,
            'tracks_processed': self.tracks_processed,
            'tracks_successful': self.tracks_successful,
            'tracks_failed': self.tracks_failed,
            'tracks_skipped': self.tracks_skipped,
            'lyrics_extracted': self.lyrics_extracted,
            'credits_extracted': self.credits_extracted,
            'albums_extracted': self.albums_extracted,
            'metadata_extracted': self.metadata_extracted,
            'extraction_time_seconds': self.extraction_time_seconds,
            'cache_hits': self.cache_hits,
            'api_calls': self.api_calls,
            'rate_limit_hits': self.rate_limit_hits,
            'sources_used': self.sources_used,
            'extractors_used': self.extractors_used,
            'success_rate': self.success_rate,
            'cache_hit_rate': self.cache_hit_rate,
            'extraction_rate': self.extraction_rate
        }


class ExtractionStep:
    """
    Étape 2: Extraction optimisée des données musicales détaillées.
    
    Responsabilités :
    - Extraction parallèle des lyrics, crédits, métadonnées
    - Gestion intelligente du cache et des rate limits
    - Traitement par lots optimisé
    - Récupération automatique en cas d'erreur
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None, 
                 database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        
        # Composants core
        self.session_manager = session_manager or get_session_manager()
        self.database = database or Database()
        self.rate_limiter = RateLimiter()
        
        # Extracteurs avec vérification de disponibilité
        self.genius_extractor = GeniusExtractor() if GeniusExtractor else None
        self.spotify_extractor = SpotifyExtractor() if SpotifyExtractor else None
        self.credit_extractor = CreditExtractor() if CreditExtractor else None
        self.lyric_extractor = LyricExtractor() if LyricExtractor else None
        
        # Configuration optimisée
        self.config = self._load_optimized_config()
        
        # Cache pour éviter les extractions répétées
        self._extraction_cache = {}
        self._failed_tracks = set()  # Éviter de réessayer les échecs permanents
        
        # Pool de threads pour extraction parallèle
        self.thread_pool = ThreadPoolExecutor(
            max_workers=self.config['max_concurrent_extractions']
        )
        
        # Statistiques de performance
        self.performance_stats = {
            'total_extractions': 0,
            'average_extraction_time': 0.0,
            'cache_efficiency': 0.0,
            'rate_limit_events': 0
        }
        
        self.logger.info(f"ExtractionStep optimisé initialisé "
                        f"(Genius: {bool(self.genius_extractor)}, "
                        f"Spotify: {bool(self.spotify_extractor)}, "
                        f"Credits: {bool(self.credit_extractor)}, "
                        f"Lyrics: {bool(self.lyric_extractor)})")
    
    def _load_optimized_config(self) -> Dict[str, Any]:
        """Charge la configuration optimisée"""
        return {
            'batch_size': settings.get('extraction.batch_size', 10),
            'max_concurrent_extractions': settings.get('extraction.max_concurrent', 5),
            'extract_lyrics': settings.get('extraction.include_lyrics', True),
            'extract_credits': settings.get('extraction.include_credits', True),
            'extract_albums': settings.get('extraction.include_albums', True),
            'extract_metadata': settings.get('extraction.include_metadata', True),
            'cache_results': settings.get('extraction.cache_results', True),
            'retry_failed': settings.get('extraction.retry_failed', True),
            'max_retries': settings.get('extraction.max_retries', 3),
            'retry_delay': settings.get('extraction.retry_delay', 5.0),
            'skip_failed_permanently': settings.get('extraction.skip_failed_permanently', True),
            'rate_limit_backoff': settings.get('extraction.rate_limit_backoff', 30),
            'prefer_cached_data': settings.get('extraction.prefer_cached_data', True)
        }
    
    @smart_cache.cache_result("track_extraction", expire_days=14)
    async def extract_artist_data(self, artist_name: str, 
                                session_id: Optional[str] = None,
                                progress_callback: Optional[callable] = None) -> Tuple[Dict[str, Any], ExtractionStats]:
        """
        Extrait toutes les données pour un artiste de manière optimisée.
        
        Args:
            artist_name: Nom de l'artiste
            session_id: ID de session optionnel
            progress_callback: Callback de progression
            
        Returns:
            Tuple[Dict[str, Any], ExtractionStats]: Données extraites et statistiques
        """
        start_time = datetime.now()
        stats = ExtractionStats()
        
        try:
            # Récupération de l'artiste et de ses morceaux
            artist = self.database.get_artist_by_name(artist_name)
            if not artist:
                raise ExtractionError(f"Artiste '{artist_name}' non trouvé")
            
            tracks = self.database.get_tracks_by_artist(artist.id)
            if not tracks:
                raise ExtractionError(f"Aucun morceau trouvé pour '{artist_name}'")
            
            stats.total_tracks = len(tracks)
            self.logger.info(f"🎵 Extraction pour {artist_name}: {len(tracks)} morceaux")
            
            # Filtrage des morceaux déjà traités ou à ignorer
            tracks_to_process = self._filter_tracks_for_extraction(tracks)
            self.logger.info(f"📋 {len(tracks_to_process)} morceaux à traiter")
            
            # Traitement par lots pour optimiser les performances
            batches = self._create_extraction_batches(tracks_to_process)
            
            # Extraction parallèle par lots
            extraction_results = await self._process_batches_parallel(
                batches, stats, progress_callback
            )
            
            # Finalisation des statistiques
            end_time = datetime.now()
            stats.extraction_time_seconds = (end_time - start_time).total_seconds()
            
            # Mise à jour de l'artiste
            await self._update_artist_completion_status(artist, stats)
            
            # Mise à jour des stats globales
            self._update_performance_stats(stats)
            
            self.logger.info(f"✅ Extraction terminée pour {artist_name}: "
                           f"{stats.tracks_successful}/{stats.total_tracks} succès "
                           f"en {stats.extraction_time_seconds:.2f}s")
            
            return extraction_results, stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur extraction pour {artist_name}: {e}")
            raise ExtractionError(f"Échec extraction: {e}")
    
    def _filter_tracks_for_extraction(self, tracks: List[Track]) -> List[Track]:
        """Filtre les morceaux selon les critères d'extraction"""
        filtered_tracks = []
        
        for track in tracks:
            # Ignorer les morceaux déjà complètement extraits
            if track.extraction_status == ExtractionStatus.COMPLETED:
                continue
            
            # Ignorer les échecs permanents
            if (self.config['skip_failed_permanently'] and 
                track.id in self._failed_tracks):
                continue
            
            # Ignorer les morceaux sans titre ou artiste
            if not track.title or not track.artist_name:
                continue
            
            filtered_tracks.append(track)
        
        return filtered_tracks
    
    def _create_extraction_batches(self, tracks: List[Track]) -> List[ExtractionBatch]:
        """Crée des lots optimisés pour l'extraction"""
        batches = []
        batch_size = self.config['batch_size']
        
        # Trier les morceaux par priorité
        sorted_tracks = self._sort_tracks_by_priority(tracks)
        
        # Créer les lots
        for i in range(0, len(sorted_tracks), batch_size):
            batch_tracks = sorted_tracks[i:i + batch_size]
            batch = ExtractionBatch(
                tracks=batch_tracks,
                batch_id=f"batch_{i//batch_size + 1}",
                priority=self._calculate_batch_priority(batch_tracks)
            )
            batches.append(batch)
        
        self.logger.info(f"📦 {len(batches)} lots créés (taille: {batch_size})")
        return batches
    
    def _sort_tracks_by_priority(self, tracks: List[Track]) -> List[Track]:
        """Trie les morceaux par priorité d'extraction"""
        def priority_score(track: Track) -> int:
            score = 0
            
            # Priorité aux morceaux avec des IDs externes
            if track.genius_id:
                score += 10
            if track.spotify_id:
                score += 5
            
            # Priorité aux morceaux sans données extraites
            if not track.lyrics:
                score += 3
            if track.extraction_status == ExtractionStatus.PENDING:
                score += 2
            
            # Priorité selon la source
            source_priority = {
                DataSource.GENIUS: 5,
                DataSource.SPOTIFY: 3,
                DataSource.RAPEDIA: 1
            }
            score += source_priority.get(track.source, 0)
            
            return score
        
        return sorted(tracks, key=priority_score, reverse=True)
    
    def _calculate_batch_priority(self, tracks: List[Track]) -> int:
        """Calcule la priorité d'un lot"""
        if not tracks:
            return 0
        
        # Moyenne des priorités individuelles
        individual_priorities = [self._sort_tracks_by_priority([track])[0] for track in tracks]
        return sum(individual_priorities) // len(individual_priorities)
    
    async def _process_batches_parallel(self, batches: List[ExtractionBatch], 
                                      stats: ExtractionStats,
                                      progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Traite les lots en parallèle de manière optimisée"""
        
        results = {
            'tracks': [],
            'lyrics': [],
            'credits': [],
            'albums': [],
            'metadata': []
        }
        
        # Traitement parallèle des lots
        loop = asyncio.get_event_loop()
        
        # Créer les tâches pour chaque lot
        tasks = []
        for batch in batches:
            task = loop.run_in_executor(
                self.thread_pool,
                self._process_single_batch,
                batch, stats
            )
            tasks.append(task)
        
        # Exécuter et collecter les résultats
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Agrégation des résultats
        for i, batch_result in enumerate(batch_results):
            if isinstance(batch_result, Exception):
                self.logger.error(f"❌ Erreur lot {batches[i].batch_id}: {batch_result}")
                continue
            
            # Fusion des résultats
            for key, value in batch_result.items():
                if isinstance(value, list):
                    results[key].extend(value)
            
            # Callback de progression
            if progress_callback:
                progress = ((i + 1) / len(batches)) * 100
                progress_callback("extraction", int(progress), 100)
        
        return results
    
    def _process_single_batch(self, batch: ExtractionBatch, 
                            stats: ExtractionStats) -> Dict[str, Any]:
        """Traite un lot unique de morceaux"""
        batch.started_at = datetime.now()
        
        batch_results = {
            'tracks': [],
            'lyrics': [],
            'credits': [],
            'albums': [],
            'metadata': []
        }
        
        self.logger.info(f"🔄 Traitement lot {batch.batch_id}: {len(batch.tracks)} morceaux")
        
        for track in batch.tracks:
            try:
                # Extraction des données pour ce morceau
                track_data = self._extract_single_track_data(track, stats)
                
                if track_data:
                    # Agrégation des résultats
                    batch_results['tracks'].append(track_data['track'])
                    
                    if track_data.get('lyrics'):
                        batch_results['lyrics'].extend(track_data['lyrics'])
                        stats.lyrics_extracted += len(track_data['lyrics'])
                    
                    if track_data.get('credits'):
                        batch_results['credits'].extend(track_data['credits'])
                        stats.credits_extracted += len(track_data['credits'])
                    
                    if track_data.get('albums'):
                        batch_results['albums'].extend(track_data['albums'])
                        stats.albums_extracted += len(track_data['albums'])
                    
                    if track_data.get('metadata'):
                        batch_results['metadata'].append(track_data['metadata'])
                        stats.metadata_extracted += 1
                    
                    stats.tracks_successful += 1
                else:
                    stats.tracks_failed += 1
                    self._failed_tracks.add(track.id)
                
                stats.tracks_processed += 1
                
            except Exception as e:
                self.logger.error(f"❌ Erreur morceau {track.title}: {e}")
                stats.tracks_failed += 1
                stats.tracks_processed += 1
                continue
        
        batch.completed_at = datetime.now()
        
        self.logger.info(f"✅ Lot {batch.batch_id} terminé en {batch.duration_seconds:.2f}s")
        return batch_results
    
    def _extract_single_track_data(self, track: Track, stats: ExtractionStats) -> Optional[Dict[str, Any]]:
        """Extrait toutes les données pour un morceau unique"""
        
        # Vérification du cache
        cache_key = f"track_data:{track.id}"
        if self.config['cache_results'] and cache_key in self._extraction_cache:
            stats.cache_hits += 1
            return self._extraction_cache[cache_key]
        
        track_data = {'track': track}
        extraction_successful = False
        
        try:
            # Extraction des paroles
            if self.config['extract_lyrics'] and self.lyric_extractor:
                lyrics = self._extract_track_lyrics(track, stats)
                if lyrics:
                    track_data['lyrics'] = lyrics
                    track.lyrics = lyrics[0].get('text', '') if lyrics else None
                    track.has_lyrics = bool(track.lyrics)
                    extraction_successful = True
            
            # Extraction des crédits
            if self.config['extract_credits'] and self.credit_extractor:
                credits = self._extract_track_credits(track, stats)
                if credits:
                    track_data['credits'] = credits
                    extraction_successful = True
            
            # Extraction des métadonnées
            if self.config['extract_metadata']:
                metadata = self._extract_track_metadata(track, stats)
                if metadata:
                    track_data['metadata'] = metadata
                    # Mise à jour du track avec les métadonnées
                    self._update_track_with_metadata(track, metadata)
                    extraction_successful = True
            
            # Extraction des informations d'album
            if self.config['extract_albums']:
                albums = self._extract_track_albums(track, stats)
                if albums:
                    track_data['albums'] = albums
                    extraction_successful = True
            
            # Mise à jour du statut d'extraction
            if extraction_successful:
                track.extraction_status = ExtractionStatus.COMPLETED
                track.updated_at = datetime.now()
                self.database.update_track(track)
                
                # Mise en cache du résultat
                if self.config['cache_results']:
                    self._extraction_cache[cache_key] = track_data
                
                stats.api_calls += 1
                return track_data
            else:
                track.extraction_status = ExtractionStatus.FAILED
                self.database.update_track(track)
                return None
                
        except APIRateLimitError as e:
            self.logger.warning(f"⏳ Rate limit atteint pour {track.title}")
            stats.rate_limit_hits += 1
            # Programmer une nouvelle tentative
            if self.config['retry_failed']:
                track.extraction_status = ExtractionStatus.RETRY
                self.database.update_track(track)
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Erreur extraction {track.title}: {e}")
            track.extraction_status = ExtractionStatus.FAILED
            self.database.update_track(track)
            return None
    
    def _extract_track_lyrics(self, track: Track, stats: ExtractionStats) -> Optional[List[Dict]]:
        """Extrait les paroles d'un morceau"""
        if not self.lyric_extractor:
            return None
        
        try:
            lyrics_result = self.lyric_extractor.extract_lyrics(track)
            if lyrics_result and lyrics_result.success:
                return [{'text': lyrics_result.data.get('lyrics', ''), 'source': lyrics_result.source}]
        except Exception as e:
            self.logger.warning(f"Erreur extraction paroles {track.title}: {e}")
        
        return None
    
    def _extract_track_credits(self, track: Track, stats: ExtractionStats) -> Optional[List[Dict]]:
        """Extrait les crédits d'un morceau"""
        if not self.credit_extractor:
            return None
        
        try:
            credits_result = self.credit_extractor.extract_credits(track)
            if credits_result and credits_result.success:
                return credits_result.data.get('credits', [])
        except Exception as e:
            self.logger.warning(f"Erreur extraction crédits {track.title}: {e}")
        
        return None
    
    def _extract_track_metadata(self, track: Track, stats: ExtractionStats) -> Optional[Dict]:
        """Extrait les métadonnées d'un morceau"""
        metadata = {}
        
        # Extraction depuis Spotify
        if self.spotify_extractor and track.spotify_id:
            try:
                spotify_data = self.spotify_extractor.get_track_info(track.spotify_id)
                if spotify_data:
                    metadata.update({
                        'duration_ms': spotify_data.get('duration_ms'),
                        'bpm': spotify_data.get('audio_features', {}).get('tempo'),
                        'key': spotify_data.get('audio_features', {}).get('key'),
                        'popularity': spotify_data.get('popularity'),
                        'spotify_data': spotify_data
                    })
            except Exception as e:
                self.logger.warning(f"Erreur métadonnées Spotify {track.title}: {e}")
        
        # Extraction depuis Genius
        if self.genius_extractor and track.genius_id:
            try:
                genius_data = self.genius_extractor.get_song_info(track.genius_id)
                if genius_data:
                    metadata.update({
                        'genius_stats': genius_data.get('stats'),
                        'release_date': genius_data.get('release_date_for_display'),
                        'genius_data': genius_data
                    })
            except Exception as e:
                self.logger.warning(f"Erreur métadonnées Genius {track.title}: {e}")
        
        return metadata if metadata else None
    
    def _extract_track_albums(self, track: Track, stats: ExtractionStats) -> Optional[List[Dict]]:
        """Extrait les informations d'album d'un morceau"""
        # À implémenter selon les besoins spécifiques
        return None
    
    def _update_track_with_metadata(self, track: Track, metadata: Dict):
        """Met à jour un morceau avec les métadonnées extraites"""
        if 'duration_ms' in metadata:
            track.duration_seconds = metadata['duration_ms'] // 1000
        
        if 'bpm' in metadata:
            track.bpm = metadata['bpm']
        
        if 'key' in metadata:
            track.key_signature = str(metadata['key'])
        
        # Mise à jour des métadonnées
        if not track.metadata:
            track.metadata = {}
        track.metadata.update(metadata)
    
    async def _update_artist_completion_status(self, artist: Artist, stats: ExtractionStats):
        """Met à jour le statut de completion de l'artiste"""
        # Calculer le pourcentage d'extraction
        if stats.total_tracks > 0:
            completion_rate = (stats.tracks_successful / stats.total_tracks) * 100
            artist.extracted_tracks = stats.tracks_successful
            
            # Mettre à jour le statut selon le taux de réussite
            if completion_rate >= 90:
                artist.extraction_status = ExtractionStatus.COMPLETED
            elif completion_rate >= 50:
                artist.extraction_status = ExtractionStatus.IN_PROGRESS
            else:
                artist.extraction_status = ExtractionStatus.FAILED
            
            artist.updated_at = datetime.now()
            self.database.update_artist(artist)
    
    def _update_performance_stats(self, stats: ExtractionStats):
        """Met à jour les statistiques de performance globales"""
        self.performance_stats['total_extractions'] += 1
        
        # Moyenne mobile du temps d'extraction
        current_avg = self.performance_stats['average_extraction_time']
        total_count = self.performance_stats['total_extractions']
        
        new_avg = ((current_avg * (total_count - 1)) + stats.extraction_time_seconds) / total_count
        self.performance_stats['average_extraction_time'] = new_avg
        
        # Efficacité du cache
        self.performance_stats['cache_efficiency'] = stats.cache_hit_rate
        self.performance_stats['rate_limit_events'] += stats.rate_limit_hits
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance"""
        return {
            **self.performance_stats,
            'extractors_available': {
                'genius': bool(self.genius_extractor),
                'spotify': bool(self.spotify_extractor),
                'credits': bool(self.credit_extractor),
                'lyrics': bool(self.lyric_extractor)
            },
            'config': self.config,
            'cache_size': len(self._extraction_cache),
            'failed_tracks_count': len(self._failed_tracks)
        }
    
    def reset_performance_stats(self):
        """Remet à zéro les statistiques et caches"""
        self.performance_stats = {
            'total_extractions': 0,
            'average_extraction_time': 0.0,
            'cache_efficiency': 0.0,
            'rate_limit_events': 0
        }
        
        self._extraction_cache.clear()
        self._failed_tracks.clear()
        
        self.logger.info("🔄 Statistiques d'extraction remises à zéro")
    
    def __del__(self):
        """Nettoyage lors de la destruction"""
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=True)