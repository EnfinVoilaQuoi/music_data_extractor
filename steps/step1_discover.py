# steps/step1_discover.py
import logging
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from dataclasses import dataclass
from functools import lru_cache
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

# IMPORTS ABSOLUS - CORRECTION MAJEURE
from models.entities import Track, Artist, Session
from models.enums import SessionStatus, ExtractionStatus, DataSource
from core.database import Database
from core.session_manager import SessionManager, get_session_manager
from core.exceptions import ExtractionError, ArtistNotFoundError
from core.cache import smart_cache
from config.settings import settings

# Imports conditionnels pour les modules de découverte
try:
    from discovery.genius_discovery import GeniusDiscovery, DiscoveryResult
except ImportError:
    GeniusDiscovery = None
    DiscoveryResult = None

try:
    from extractors.web_scrapers.rapedia_scraper import RapediaScraper
except ImportError:
    RapediaScraper = None

@dataclass
class DiscoveryStats:
    """Statistiques de la découverte avec optimisations"""
    total_found: int = 0
    genius_found: int = 0
    rapedia_found: int = 0
    duplicates_removed: int = 0
    final_count: int = 0
    discovery_time_seconds: float = 0.0
    sources_used: List[str] = None
    cache_hits: int = 0
    api_calls: int = 0
    
    def __post_init__(self):
        if self.sources_used is None:
            self.sources_used = []
    
    @property
    def cache_hit_rate(self) -> float:
        """Taux de réussite du cache"""
        total_requests = self.cache_hits + self.api_calls
        if total_requests == 0:
            return 0.0
        return (self.cache_hits / total_requests) * 100
    
    @property
    def discovery_rate(self) -> float:
        """Morceaux découverts par seconde"""
        if self.discovery_time_seconds == 0:
            return 0.0
        return self.final_count / self.discovery_time_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour export"""
        return {
            'total_found': self.total_found,
            'genius_found': self.genius_found,
            'rapedia_found': self.rapedia_found,
            'duplicates_removed': self.duplicates_removed,
            'final_count': self.final_count,
            'discovery_time_seconds': self.discovery_time_seconds,
            'sources_used': self.sources_used,
            'cache_hits': self.cache_hits,
            'api_calls': self.api_calls,
            'cache_hit_rate': self.cache_hit_rate,
            'discovery_rate': self.discovery_rate
        }


class DiscoveryStep:
    """
    Étape 1 : Découverte optimisée des morceaux d'un artiste.
    
    Responsabilités :
    - Recherche multi-sources parallèle
    - Cache intelligent des résultats
    - Déduplication avancée
    - Création des entités de base en base de données
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None, 
                 database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        
        # Composants core
        self.session_manager = session_manager or get_session_manager()
        self.database = database or Database()
        
        # Découvreurs avec vérification de disponibilité
        self.genius_discovery = GeniusDiscovery() if GeniusDiscovery else None
        self.rapedia_scraper = RapediaScraper() if RapediaScraper else None
        
        # Configuration optimisée
        self.config = self._load_optimized_config()
        
        # Cache pour éviter les recherches répétées
        self._artist_cache = {}
        self._similarity_cache = {}
        
        # Statistiques de performance
        self.performance_stats = {
            'total_discoveries': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'average_discovery_time': 0.0
        }
        
        self.logger.info(f"DiscoveryStep optimisé initialisé (Genius: {bool(self.genius_discovery)}, "
                        f"Rapedia: {bool(self.rapedia_scraper)})")
    
    def _load_optimized_config(self) -> Dict[str, Any]:
        """Charge la configuration optimisée"""
        return {
            'max_tracks_per_source': settings.get('discovery.max_tracks_per_source', 200),
            'enable_rapedia': settings.get('discovery.enable_rapedia', True) and bool(self.rapedia_scraper),
            'enable_genius': settings.get('discovery.enable_genius', True) and bool(self.genius_discovery),
            'similarity_threshold': settings.get('discovery.similarity_threshold', 0.85),
            'prefer_verified_sources': settings.get('discovery.prefer_verified_sources', True),
            'parallel_discovery': settings.get('discovery.parallel_discovery', True),
            'cache_discovery_results': settings.get('discovery.cache_results', True),
            'max_concurrent_sources': settings.get('discovery.max_concurrent_sources', 3),
            'timeout_per_source': settings.get('discovery.timeout_per_source', 60)
        }
    
    @smart_cache.cache_result("artist_discovery", expire_days=7)
    def discover_artist_tracks(self, artist_name: str, 
                             session_id: Optional[str] = None,
                             max_tracks: Optional[int] = None) -> Tuple[List[Track], DiscoveryStats]:
        """
        Découvre tous les morceaux d'un artiste avec optimisations avancées.
        
        Args:
            artist_name: Nom de l'artiste
            session_id: ID de session optionnel
            max_tracks: Limite de morceaux (optionnel)
            
        Returns:
            Tuple[List[Track], DiscoveryStats]: Morceaux découverts et statistiques
        """
        start_time = datetime.now()
        stats = DiscoveryStats()
        
        try:
            # Normalisation et validation de l'artiste
            normalized_artist = self._normalize_artist_name(artist_name)
            if not normalized_artist:
                raise ArtistNotFoundError(artist_name)
            
            self.logger.info(f"🔍 Découverte pour '{artist_name}' (normalisé: '{normalized_artist}')")
            
            # Vérification du cache artiste
            cache_key = f"discovery:{normalized_artist}"
            if self.config['cache_discovery_results']:
                cached_result = self._check_artist_cache(cache_key)
                if cached_result:
                    stats.cache_hits += 1
                    self.logger.info(f"💾 Résultat trouvé en cache pour {artist_name}")
                    return cached_result
            
            # Obtenir ou créer l'entité Artist
            artist = self._get_or_create_artist(normalized_artist)
            
            # Découverte multi-sources
            if self.config['parallel_discovery']:
                all_tracks = self._discover_parallel_sources(artist, stats, max_tracks)
            else:
                all_tracks = self._discover_sequential_sources(artist, stats, max_tracks)
            
            # Déduplication et nettoyage
            unique_tracks = self._deduplicate_tracks(all_tracks, stats)
            
            # Application de la limite de morceaux
            if max_tracks and len(unique_tracks) > max_tracks:
                unique_tracks = unique_tracks[:max_tracks]
                self.logger.info(f"✂️ Limitation à {max_tracks} morceaux")
            
            # Sauvegarde en base de données
            saved_tracks = self._save_tracks_to_database(artist, unique_tracks)
            
            # Finalisation des statistiques
            end_time = datetime.now()
            stats.discovery_time_seconds = (end_time - start_time).total_seconds()
            stats.final_count = len(saved_tracks)
            
            # Mise en cache du résultat
            if self.config['cache_discovery_results']:
                self._cache_artist_result(cache_key, (saved_tracks, stats))
            
            # Mise à jour des stats globales
            self._update_performance_stats(stats.discovery_time_seconds)
            
            self.logger.info(f"✅ Découverte terminée: {stats.final_count} morceaux "
                           f"en {stats.discovery_time_seconds:.2f}s")
            
            return saved_tracks, stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de la découverte pour {artist_name}: {e}")
            raise ExtractionError(f"Échec de la découverte: {e}")
    
    def _discover_parallel_sources(self, artist: Artist, stats: DiscoveryStats, 
                                 max_tracks: Optional[int]) -> List[Track]:
        """Découverte parallèle depuis toutes les sources"""
        all_tracks = []
        
        # Préparer les tâches de découverte
        discovery_tasks = []
        
        if self.config['enable_genius'] and self.genius_discovery:
            discovery_tasks.append(('genius', self._discover_from_genius))
            stats.sources_used.append('genius')
        
        if self.config['enable_rapedia'] and self.rapedia_scraper:
            discovery_tasks.append(('rapedia', self._discover_from_rapedia))
            stats.sources_used.append('rapedia')
        
        if not discovery_tasks:
            self.logger.warning("⚠️ Aucune source de découverte disponible")
            return []
        
        # Exécution parallèle avec ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.config['max_concurrent_sources']) as executor:
            future_to_source = {
                executor.submit(self._safe_discover_wrapper, task_func, artist, max_tracks): source_name
                for source_name, task_func in discovery_tasks
            }
            
            for future in as_completed(future_to_source, timeout=self.config['timeout_per_source']):
                source_name = future_to_source[future]
                try:
                    tracks = future.result()
                    if tracks:
                        all_tracks.extend(tracks)
                        
                        # Mise à jour des stats par source
                        if source_name == 'genius':
                            stats.genius_found = len(tracks)
                        elif source_name == 'rapedia':
                            stats.rapedia_found = len(tracks)
                        
                        stats.api_calls += 1
                        self.logger.info(f"✅ {source_name}: {len(tracks)} morceaux trouvés")
                    else:
                        self.logger.warning(f"⚠️ {source_name}: aucun morceau trouvé")
                        
                except Exception as e:
                    self.logger.error(f"❌ Erreur avec {source_name}: {e}")
                    continue
        
        stats.total_found = len(all_tracks)
        return all_tracks
    
    def _discover_sequential_sources(self, artist: Artist, stats: DiscoveryStats,
                                   max_tracks: Optional[int]) -> List[Track]:
        """Découverte séquentielle depuis toutes les sources"""
        all_tracks = []
        
        # Genius en premier (source principale)
        if self.config['enable_genius'] and self.genius_discovery:
            genius_tracks = self._safe_discover_wrapper(self._discover_from_genius, artist, max_tracks)
            if genius_tracks:
                all_tracks.extend(genius_tracks)
                stats.genius_found = len(genius_tracks)
                stats.sources_used.append('genius')
                stats.api_calls += 1
                self.logger.info(f"✅ Genius: {len(genius_tracks)} morceaux")
        
        # Rapedia en complément
        if self.config['enable_rapedia'] and self.rapedia_scraper:
            # Limiter si déjà beaucoup de morceaux trouvés
            remaining_limit = max_tracks - len(all_tracks) if max_tracks else None
            if not remaining_limit or remaining_limit > 0:
                rapedia_tracks = self._safe_discover_wrapper(self._discover_from_rapedia, artist, remaining_limit)
                if rapedia_tracks:
                    all_tracks.extend(rapedia_tracks)
                    stats.rapedia_found = len(rapedia_tracks)
                    stats.sources_used.append('rapedia')
                    stats.api_calls += 1
                    self.logger.info(f"✅ Rapedia: {len(rapedia_tracks)} morceaux")
        
        stats.total_found = len(all_tracks)
        return all_tracks
    
    def _safe_discover_wrapper(self, discover_func, artist: Artist, max_tracks: Optional[int]) -> List[Track]:
        """Wrapper sécurisé pour les fonctions de découverte"""
        try:
            return discover_func(artist, max_tracks)
        except Exception as e:
            self.logger.error(f"Erreur dans {discover_func.__name__}: {e}")
            return []
    
    def _discover_from_genius(self, artist: Artist, max_tracks: Optional[int]) -> List[Track]:
        """Découverte depuis Genius"""
        if not self.genius_discovery:
            return []
        
        try:
            results = self.genius_discovery.discover_artist_tracks(
                artist.name, 
                max_tracks=max_tracks or self.config['max_tracks_per_source']
            )
            
            return self._convert_genius_results_to_tracks(artist, results)
            
        except Exception as e:
            self.logger.error(f"Erreur Genius pour {artist.name}: {e}")
            return []
    
    def _discover_from_rapedia(self, artist: Artist, max_tracks: Optional[int]) -> List[Track]:
        """Découverte depuis Rapedia"""
        if not self.rapedia_scraper:
            return []
        
        try:
            tracks = self.rapedia_scraper.search_artist_tracks(
                artist.name,
                max_tracks=max_tracks or self.config['max_tracks_per_source']
            )
            
            return self._convert_rapedia_results_to_tracks(artist, tracks)
            
        except Exception as e:
            self.logger.error(f"Erreur Rapedia pour {artist.name}: {e}")
            return []
    
    def _convert_genius_results_to_tracks(self, artist: Artist, results) -> List[Track]:
        """Convertit les résultats Genius en entités Track"""
        tracks = []
        
        if not results or not hasattr(results, 'tracks'):
            return tracks
        
        for genius_track in results.tracks:
            try:
                track = Track(
                    title=genius_track.get('title', ''),
                    artist_id=artist.id,
                    artist_name=artist.name,
                    genius_id=genius_track.get('id'),
                    genius_url=genius_track.get('url'),
                    source=DataSource.GENIUS,
                    extraction_status=ExtractionStatus.PENDING
                )
                tracks.append(track)
                
            except Exception as e:
                self.logger.warning(f"Erreur conversion morceau Genius: {e}")
                continue
        
        return tracks
    
    def _convert_rapedia_results_to_tracks(self, artist: Artist, rapedia_tracks) -> List[Track]:
        """Convertit les résultats Rapedia en entités Track"""
        tracks = []
        
        for rapedia_track in rapedia_tracks:
            try:
                track = Track(
                    title=rapedia_track.get('title', ''),
                    artist_id=artist.id,
                    artist_name=artist.name,
                    album_name=rapedia_track.get('album'),
                    source=DataSource.RAPEDIA,
                    extraction_status=ExtractionStatus.PENDING,
                    metadata={'rapedia_data': rapedia_track}
                )
                tracks.append(track)
                
            except Exception as e:
                self.logger.warning(f"Erreur conversion morceau Rapedia: {e}")
                continue
        
        return tracks
    
    @lru_cache(maxsize=512)
    def _calculate_track_similarity(self, title1: str, title2: str, artist1: str, artist2: str) -> float:
        """Calcule la similarité entre deux morceaux - avec cache"""
        try:
            from utils.text_utils import calculate_similarity
            
            # Normalisation des titres
            norm_title1 = self._normalize_track_title(title1)
            norm_title2 = self._normalize_track_title(title2)
            
            # Normalisation des artistes
            norm_artist1 = self._normalize_artist_name(artist1)
            norm_artist2 = self._normalize_artist_name(artist2)
            
            # Calcul de similarité pondérée
            title_similarity = calculate_similarity(norm_title1, norm_title2)
            artist_similarity = calculate_similarity(norm_artist1, norm_artist2)
            
            # Pondération: titre = 70%, artiste = 30%
            return (title_similarity * 0.7) + (artist_similarity * 0.3)
            
        except ImportError:
            # Fallback simple si utils.text_utils non disponible
            return 1.0 if (title1.lower() == title2.lower() and artist1.lower() == artist2.lower()) else 0.0
    
    def _deduplicate_tracks(self, tracks: List[Track], stats: DiscoveryStats) -> List[Track]:
        """Déduplication avancée des morceaux avec algorithme optimisé"""
        if not tracks:
            return []
        
        unique_tracks = []
        seen_signatures = set()
        duplicate_count = 0
        
        # Trier les morceaux par priorité de source
        source_priority = {
            DataSource.GENIUS: 1,
            DataSource.RAPEDIA: 2,
            DataSource.UNKNOWN: 3
        }
        
        sorted_tracks = sorted(tracks, key=lambda t: source_priority.get(t.source, 999))
        
        for track in sorted_tracks:
            # Génération de signature unique
            signature = self._generate_track_signature(track)
            
            if signature not in seen_signatures:
                # Vérification de similarité avec les morceaux existants
                is_duplicate = False
                
                for existing_track in unique_tracks:
                    similarity = self._calculate_track_similarity(
                        track.title, existing_track.title,
                        track.artist_name, existing_track.artist_name
                    )
                    
                    if similarity >= self.config['similarity_threshold']:
                        is_duplicate = True
                        duplicate_count += 1
                        self.logger.debug(f"Doublon détecté: '{track.title}' "
                                        f"(similarité: {similarity:.2f})")
                        break
                
                if not is_duplicate:
                    unique_tracks.append(track)
                    seen_signatures.add(signature)
            else:
                duplicate_count += 1
        
        stats.duplicates_removed = duplicate_count
        
        self.logger.info(f"🔄 Déduplication: {len(tracks)} -> {len(unique_tracks)} "
                        f"({duplicate_count} doublons supprimés)")
        
        return unique_tracks
    
    @lru_cache(maxsize=1024)
    def _generate_track_signature(self, track: Track) -> str:
        """Génère une signature unique pour un morceau - avec cache"""
        import hashlib
        
        # Normalisation pour signature
        normalized_title = self._normalize_track_title(track.title)
        normalized_artist = self._normalize_artist_name(track.artist_name)
        
        # Génération de la signature
        signature_text = f"{normalized_artist}|{normalized_title}"
        return hashlib.md5(signature_text.encode()).hexdigest()
    
    @lru_cache(maxsize=256)
    def _normalize_artist_name(self, name: str) -> str:
        """Normalise le nom d'artiste pour comparaison - avec cache"""
        if not name:
            return ""
        
        try:
            from utils.text_utils import clean_artist_name
            return clean_artist_name(name)
        except ImportError:
            # Fallback simple
            return name.lower().strip()
    
    @lru_cache(maxsize=512)
    def _normalize_track_title(self, title: str) -> str:
        """Normalise le titre de morceau pour comparaison - avec cache"""
        if not title:
            return ""
        
        try:
            from utils.text_utils import clean_track_title
            return clean_track_title(title)
        except ImportError:
            # Fallback simple
            import re
            # Supprimer feat., remix, etc.
            cleaned = re.sub(r'\s*[\(\[][^)\]]*[\)\]]\s*', ' ', title)
            return cleaned.lower().strip()
    
    def _get_or_create_artist(self, artist_name: str) -> Artist:
        """Obtient ou crée l'entité Artist"""
        # Vérification en cache local
        if artist_name in self._artist_cache:
            return self._artist_cache[artist_name]
        
        # Recherche en base de données
        artist = self.database.get_artist_by_name(artist_name)
        
        if not artist:
            # Création d'un nouvel artiste
            artist = Artist(
                name=artist_name,
                extraction_status=ExtractionStatus.IN_PROGRESS,
                created_at=datetime.now()
            )
            
            # Sauvegarde en base
            artist_id = self.database.save_artist(artist)
            artist.id = artist_id
            
            self.logger.info(f"➕ Nouvel artiste créé: {artist_name} (ID: {artist_id})")
        else:
            self.logger.info(f"👤 Artiste existant trouvé: {artist_name} (ID: {artist.id})")
        
        # Mise en cache
        self._artist_cache[artist_name] = artist
        return artist
    
    def _save_tracks_to_database(self, artist: Artist, tracks: List[Track]) -> List[Track]:
        """Sauvegarde les morceaux en base de données avec gestion des doublons"""
        saved_tracks = []
        
        try:
            with self.database.get_connection() as conn:
                for track in tracks:
                    # Vérifier si le morceau existe déjà
                    existing_track = self.database.get_track_by_title_and_artist(
                        track.title, artist.id
                    )
                    
                    if existing_track:
                        # Mettre à jour les données manquantes
                        self._update_existing_track(existing_track, track)
                        saved_tracks.append(existing_track)
                    else:
                        # Sauvegarder nouveau morceau
                        track_id = self.database.save_track(track)
                        track.id = track_id
                        saved_tracks.append(track)
            
            # Mettre à jour le compteur de morceaux de l'artiste
            artist.total_tracks = len(saved_tracks)
            self.database.update_artist(artist)
            
            self.logger.info(f"💾 {len(saved_tracks)} morceaux sauvegardés pour {artist.name}")
            
        except Exception as e:
            self.logger.error(f"❌ Erreur sauvegarde: {e}")
            raise
        
        return saved_tracks
    
    def _update_existing_track(self, existing_track: Track, new_track: Track):
        """Met à jour un morceau existant avec les nouvelles données"""
        updated = False
        
        # Mise à jour des IDs externes manquants
        if not existing_track.genius_id and new_track.genius_id:
            existing_track.genius_id = new_track.genius_id
            updated = True
        
        if not existing_track.genius_url and new_track.genius_url:
            existing_track.genius_url = new_track.genius_url
            updated = True
        
        # Mise à jour des métadonnées
        if new_track.metadata:
            if not existing_track.metadata:
                existing_track.metadata = {}
            existing_track.metadata.update(new_track.metadata)
            updated = True
        
        # Amélioration de la source si nécessaire
        source_priority = {
            DataSource.GENIUS: 1,
            DataSource.RAPEDIA: 2,
            DataSource.UNKNOWN: 3
        }
        
        if (source_priority.get(new_track.source, 999) < 
            source_priority.get(existing_track.source, 999)):
            existing_track.source = new_track.source
            updated = True
        
        if updated:
            existing_track.updated_at = datetime.now()
            self.database.update_track(existing_track)
    
    def _check_artist_cache(self, cache_key: str) -> Optional[Tuple[List[Track], DiscoveryStats]]:
        """Vérifie le cache pour un artiste"""
        try:
            from core.cache import cache_manager
            return cache_manager.get(cache_key)
        except:
            return None
    
    def _cache_artist_result(self, cache_key: str, result: Tuple[List[Track], DiscoveryStats]):
        """Met en cache le résultat de découverte"""
        try:
            from core.cache import cache_manager
            cache_manager.set(cache_key, result, expire_days=7)
        except Exception as e:
            self.logger.warning(f"Erreur mise en cache: {e}")
    
    def _update_performance_stats(self, discovery_time: float):
        """Met à jour les statistiques de performance"""
        self.performance_stats['total_discoveries'] += 1
        
        # Calcul de la moyenne mobile
        current_avg = self.performance_stats['average_discovery_time']
        total_count = self.performance_stats['total_discoveries']
        
        new_avg = ((current_avg * (total_count - 1)) + discovery_time) / total_count
        self.performance_stats['average_discovery_time'] = new_avg
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance"""
        return {
            **self.performance_stats,
            'cache_hit_rate': (self.performance_stats['cache_hits'] / 
                              max(1, self.performance_stats['cache_hits'] + self.performance_stats['api_calls'])) * 100,
            'sources_available': {
                'genius': bool(self.genius_discovery),
                'rapedia': bool(self.rapedia_scraper)
            },
            'config': self.config
        }
    
    def reset_performance_stats(self):
        """Remet à zéro les statistiques de performance"""
        self.performance_stats = {
            'total_discoveries': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'average_discovery_time': 0.0
        }
        
        # Vider les caches locaux
        self._artist_cache.clear()
        self._similarity_cache.clear()
        
        self.logger.info("🔄 Statistiques de performance remises à zéro")
    
    async def discover_artist_tracks_async(self, artist_name: str, 
                                         session_id: Optional[str] = None,
                                         max_tracks: Optional[int] = None,
                                         progress_callback: Optional[callable] = None) -> Tuple[List[Track], DiscoveryStats]:
        """Version asynchrone de la découverte avec callback de progression"""
        
        def progress_update(step: str, current: int, total: int):
            if progress_callback:
                progress_callback(step, current, total)
        
        # Utiliser un executor pour la partie synchrone
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            self.discover_artist_tracks,
            artist_name, session_id, max_tracks
        )