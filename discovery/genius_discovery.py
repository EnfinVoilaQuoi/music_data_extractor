# discovery/genius_discovery.py
"""
Découverte de morceaux via l'API Genius.
Version optimisée avec cache intelligent, rate limiting et gestion d'erreurs robuste.
"""

import logging
import re
import time
from functools import lru_cache
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Imports absolus
from config.settings import settings
from models.entities import Track, Artist
from models.enums import DataSource, QualityLevel
from core.exceptions import APIError, APIRateLimitError, DataValidationError

# Imports conditionnels optimisés
try:
    from core.cache import CacheManager
except ImportError:
    CacheManager = None

try:
    from core.rate_limiter import RateLimiter
except ImportError:
    RateLimiter = None

from utils.text_utils import clean_artist_name, normalize_text


@dataclass
class DiscoveryResult:
    """
    Résultat optimisé d'une découverte de morceaux avec métriques de performance.
    """
    success: bool
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    total_found: int = 0
    error: Optional[str] = None
    source: str = "genius"
    quality_score: float = 0.0
    api_calls_made: int = 0
    cache_hits: int = 0
    discovery_time_seconds: float = 0.0
    
    def __post_init__(self):
        """Post-initialisation avec calculs automatiques"""
        self.total_found = len(self.tracks)
        if self.total_found > 0 and self.quality_score == 0.0:
            self.quality_score = self._calculate_quality_score()
    
    @lru_cache(maxsize=1)
    def _calculate_quality_score(self) -> float:
        """Calcule le score de qualité basé sur les données disponibles"""
        if not self.tracks:
            return 0.0
        
        total_score = 0.0
        for track in self.tracks:
            score = 0.0
            
            # Critères de qualité (pondérés)
            if track.get('lyrics_state') == 'complete':
                score += 0.3
            if track.get('primary_artist'):
                score += 0.2
            if track.get('release_date_formatted'):
                score += 0.15
            if track.get('album'):
                score += 0.15
            if track.get('featured_artists'):
                score += 0.1
            if track.get('producer_artists'):
                score += 0.1
            
            total_score += score
        
        return (total_score / len(self.tracks)) * 100
    
    @property
    def cache_hit_rate(self) -> float:
        """Calcule le taux de succès du cache"""
        total_requests = self.cache_hits + self.api_calls_made
        if total_requests == 0:
            return 0.0
        return (self.cache_hits / total_requests) * 100
    
    @property
    def tracks_per_second(self) -> float:
        """Calcule le taux de découverte (tracks/seconde)"""
        if self.discovery_time_seconds == 0:
            return 0.0
        return self.total_found / self.discovery_time_seconds


class GeniusDiscovery:
    """
    Découverte optimisée de morceaux via l'API Genius.
    
    Fonctionnalités:
    - Cache LRU intelligent pour éviter les appels répétés
    - Rate limiting pour respecter les limites API
    - Retry automatique avec backoff exponentiel
    - Filtrage intelligent des résultats
    - Métriques de performance en temps réel
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration API Genius
        self.api_key = settings.genius_api_key
        if not self.api_key:
            raise APIError("Clé API Genius manquante dans la configuration")
        
        self.base_url = "https://api.genius.com"
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'User-Agent': 'MusicDataExtractor/1.0',
            'Accept': 'application/json'
        }
        
        # Session HTTP optimisée avec retry et timeout
        self.session = self._create_optimized_session()
        
        # Composants optionnels avec fallback
        self.cache_manager = CacheManager() if CacheManager else None
        self.rate_limiter = RateLimiter(calls_per_minute=30) if RateLimiter else None
        
        # Configuration des patterns de filtrage (signalement uniquement)
        self.warning_patterns = self._compile_warning_patterns()
        
        # Métriques de performance
        self.performance_metrics = {
            'total_api_calls': 0,
            'total_cache_hits': 0,
            'total_tracks_found': 0,
            'average_response_time': 0.0,
            'error_count': 0
        }
        
        self.logger.info("✅ GeniusDiscovery optimisé initialisé")
    
    def _create_optimized_session(self) -> requests.Session:
        """Crée une session HTTP optimisée avec retry et timeout"""
        session = requests.Session()
        
        # Configuration du retry avec backoff exponentiel
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Timeout par défaut
        session.timeout = 30
        
        return session
    
    @lru_cache(maxsize=128)
    def _compile_warning_patterns(self) -> List[re.Pattern]:
        """Compile les patterns de détection avec cache"""
        patterns = [
            # Patterns très spécifiques pour battles et freestyles
            r'\brap[\s\-]*contenders?\s+(?:battle|vs|versus)\b',
            r'\brentre\s+dans\s+le\s+cercle\s+(?:battle|vs|versus)\b',
            r'\bgr[üu]nt\s+(?:battle|vs|versus|freestyle)\b',
            r'\bbattle\s+(?:rap|hip[\s\-]*hop)\s+(?:vs|versus)\b',
            r'\brap2france\s+(?:battle|vs|versus)\b',
            r'\bmusicast\s+(?:battle|freestyle)\b',
            r'\bdim\s+dak\s+freestyle\b',
            r'\b(?:eliminatoire|demi[\s\-]*finale|finale)\s+(?:battle|rap)\b',
            r'\btournoi\s+(?:battle|rap)\b',
            # Remixes suspects
            r'\bunofficial\s+remix\b',
            r'\bbootleg\s+remix\b'
        ]
        
        return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    
    @lru_cache(maxsize=256)
    def discover_artist_tracks(self, artist_name: str, max_tracks: Optional[int] = None) -> DiscoveryResult:
        """
        Découvre les morceaux d'un artiste avec cache LRU et optimisations.
        
        Args:
            artist_name: Nom de l'artiste à rechercher
            max_tracks: Nombre maximum de morceaux à récupérer
            
        Returns:
            DiscoveryResult avec les morceaux trouvés et métriques
        """
        start_time = time.time()
        
        try:
            # Normalisation du nom d'artiste
            normalized_artist = clean_artist_name(artist_name)
            
            self.logger.info(f"🔍 Recherche Genius pour: {normalized_artist}")
            
            # Vérification du cache
            cache_key = f"genius_discovery_{normalized_artist}_{max_tracks}"
            
            if self.cache_manager:
                cached_result = self.cache_manager.get(cache_key)
                if cached_result:
                    self.performance_metrics['total_cache_hits'] += 1
                    self.logger.info(f"💾 Cache hit pour {normalized_artist}")
                    
                    # Convertir le cache en DiscoveryResult
                    result = DiscoveryResult(**cached_result)
                    result.cache_hits = 1
                    return result
            
            # Recherche de l'artiste
            artist_data = self._search_artist(normalized_artist)
            if not artist_data:
                return DiscoveryResult(
                    success=False,
                    error=f"Artiste '{artist_name}' non trouvé sur Genius",
                    discovery_time_seconds=time.time() - start_time
                )
            
            # Récupération des morceaux
            tracks = self._fetch_artist_tracks(artist_data['id'], max_tracks)
            
            # Filtrage et enrichissement
            filtered_tracks = self._filter_and_enrich_tracks(tracks, normalized_artist)
            
            # Création du résultat
            discovery_time = time.time() - start_time
            result = DiscoveryResult(
                success=True,
                tracks=filtered_tracks,
                api_calls_made=2,  # search_artist + fetch_tracks
                discovery_time_seconds=discovery_time
            )
            
            # Mise en cache
            if self.cache_manager and result.success:
                self.cache_manager.set(cache_key, result.__dict__, expire_days=1)
            
            # Mise à jour des métriques
            self._update_performance_metrics(result)
            
            self.logger.info(f"✅ Genius: {result.total_found} morceaux trouvés "
                           f"en {discovery_time:.2f}s (score: {result.quality_score:.1f}%)")
            
            return result
            
        except APIRateLimitError:
            self.logger.warning("⚠️ Limite de taux API Genius atteinte")
            return DiscoveryResult(
                success=False,
                error="Rate limit atteint",
                discovery_time_seconds=time.time() - start_time
            )
        except Exception as e:
            self.logger.error(f"❌ Erreur Genius pour {artist_name}: {e}")
            self.performance_metrics['error_count'] += 1
            return DiscoveryResult(
                success=False,
                error=str(e),
                discovery_time_seconds=time.time() - start_time
            )
    
    def _search_artist(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """
        Recherche un artiste sur Genius avec optimisations.
        
        Args:
            artist_name: Nom de l'artiste
            
        Returns:
            Données de l'artiste ou None si non trouvé
        """
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        try:
            url = f"{self.base_url}/search"
            params = {'q': artist_name}
            
            response = self.session.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            self.performance_metrics['total_api_calls'] += 1
            
            data = response.json()
            hits = data.get('response', {}).get('hits', [])
            
            # Recherche de l'artiste principal dans les résultats
            for hit in hits:
                result = hit.get('result', {})
                primary_artist = result.get('primary_artist', {})
                
                if primary_artist and primary_artist.get('name'):
                    # Normalisation pour comparaison
                    found_name = normalize_text(primary_artist['name'])
                    search_name = normalize_text(artist_name)
                    
                    # Correspondance exacte ou très proche
                    if found_name == search_name or search_name in found_name:
                        self.logger.debug(f"✅ Artiste trouvé: {primary_artist['name']}")
                        return primary_artist
            
            self.logger.warning(f"⚠️ Artiste '{artist_name}' non trouvé dans les résultats")
            return None
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Erreur requête Genius search: {e}")
            return None
    
    def _fetch_artist_tracks(self, artist_id: int, max_tracks: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Récupère les morceaux d'un artiste avec pagination optimisée.
        
        Args:
            artist_id: ID Genius de l'artiste
            max_tracks: Limite du nombre de morceaux
            
        Returns:
            Liste des morceaux trouvés
        """
        all_tracks = []
        page = 1
        per_page = 50  # Maximum autorisé par Genius
        
        max_tracks = max_tracks or 200  # Valeur par défaut
        
        while len(all_tracks) < max_tracks:
            if self.rate_limiter:
                self.rate_limiter.wait_if_needed()
            
            try:
                url = f"{self.base_url}/artists/{artist_id}/songs"
                params = {
                    'per_page': per_page,
                    'page': page,
                    'sort': 'popularity'  # Trier par popularité
                }
                
                response = self.session.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                self.performance_metrics['total_api_calls'] += 1
                
                data = response.json()
                songs = data.get('response', {}).get('songs', [])
                
                if not songs:
                    self.logger.debug(f"📄 Page {page}: aucun morceau supplémentaire")
                    break
                
                all_tracks.extend(songs)
                self.logger.debug(f"📄 Page {page}: {len(songs)} morceaux ajoutés")
                
                # Condition d'arrêt si moins de morceaux que demandé
                if len(songs) < per_page:
                    break
                
                page += 1
                
                # Sécurité: éviter les boucles infinies
                if page > 20:  # Max 1000 morceaux (20 pages * 50)
                    self.logger.warning("⚠️ Limite de pages atteinte (20 pages)")
                    break
                
            except requests.exceptions.RequestException as e:
                self.logger.error(f"❌ Erreur récupération page {page}: {e}")
                break
        
        # Limiter au nombre demandé
        if len(all_tracks) > max_tracks:
            all_tracks = all_tracks[:max_tracks]
        
        self.logger.debug(f"📊 Total récupéré: {len(all_tracks)} morceaux sur {page-1} pages")
        return all_tracks
    
    def _filter_and_enrich_tracks(self, tracks: List[Dict[str, Any]], artist_name: str) -> List[Dict[str, Any]]:
        """
        Filtre et enrichit la liste des morceaux avec détection des contenus suspects.
        
        Args:
            tracks: Liste brute des morceaux
            artist_name: Nom de l'artiste pour validation
            
        Returns:
            Liste filtrée et enrichie des morceaux
        """
        filtered_tracks = []
        warnings_count = 0
        
        for track in tracks:
            try:
                # Extraction des données de base
                title = track.get('title', '').strip()
                if not title:
                    continue
                
                # Vérification de l'artiste principal
                primary_artist = track.get('primary_artist', {})
                if not primary_artist or not primary_artist.get('name'):
                    continue
                
                # Normalisation pour comparaison
                track_artist = normalize_text(primary_artist['name'])
                search_artist = normalize_text(artist_name)
                
                # Vérifier que c'est bien l'artiste recherché
                if track_artist != search_artist and search_artist not in track_artist:
                    self.logger.debug(f"⏭️ Artiste différent: {primary_artist['name']} != {artist_name}")
                    continue
                
                # Détection des contenus suspects (signalement uniquement)
                is_suspicious = self._is_suspicious_content(title)
                if is_suspicious:
                    warnings_count += 1
                    self.logger.debug(f"⚠️ Contenu suspect détecté: {title}")
                
                # Enrichissement des métadonnées
                enriched_track = self._enrich_track_metadata(track)
                
                # Ajout du flag de suspicion
                enriched_track['is_suspicious'] = is_suspicious
                enriched_track['data_source'] = DataSource.GENIUS.value
                enriched_track['quality_level'] = self._assess_track_quality(enriched_track)
                
                filtered_tracks.append(enriched_track)
                
            except Exception as e:
                self.logger.warning(f"⚠️ Erreur traitement track '{title}': {e}")
                continue
        
        if warnings_count > 0:
            self.logger.info(f"⚠️ {warnings_count} morceaux suspects détectés (gardés avec flag)")
        
        self.logger.debug(f"🔍 Filtrage: {len(filtered_tracks)}/{len(tracks)} morceaux conservés")
        return filtered_tracks
    
    @lru_cache(maxsize=512)
    def _is_suspicious_content(self, title: str) -> bool:
        """
        Détecte si un titre correspond à du contenu suspect avec cache.
        
        Args:
            title: Titre à analyser
            
        Returns:
            True si le contenu semble suspect
        """
        title_lower = title.lower()
        
        for pattern in self.warning_patterns:
            if pattern.search(title_lower):
                return True
        
        return False
    
    def _enrich_track_metadata(self, track: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrichit les métadonnées d'un morceau avec données additionnelles.
        
        Args:
            track: Données brutes du morceau
            
        Returns:
            Morceau avec métadonnées enrichies
        """
        enriched = {
            # Données de base
            'genius_id': track.get('id'),
            'title': track.get('title', ''),
            'url': track.get('url', ''),
            'path': track.get('path', ''),
            
            # Artiste principal
            'primary_artist': {
                'id': track.get('primary_artist', {}).get('id'),
                'name': track.get('primary_artist', {}).get('name', ''),
                'url': track.get('primary_artist', {}).get('url', ''),
                'image_url': track.get('primary_artist', {}).get('image_url', '')
            },
            
            # Artistes supplémentaires
            'featured_artists': [
                {
                    'id': artist.get('id'),
                    'name': artist.get('name', ''),
                    'url': artist.get('url', '')
                }
                for artist in track.get('featured_artists', [])
            ],
            
            # Informations de production
            'producer_artists': [
                {
                    'id': artist.get('id'),
                    'name': artist.get('name', ''),
                    'url': artist.get('url', '')
                }
                for artist in track.get('producer_artists', [])
            ],
            
            # Album
            'album': {
                'id': track.get('album', {}).get('id') if track.get('album') else None,
                'name': track.get('album', {}).get('name', '') if track.get('album') else '',
                'url': track.get('album', {}).get('url', '') if track.get('album') else '',
                'cover_art_url': track.get('album', {}).get('cover_art_url', '') if track.get('album') else ''
            } if track.get('album') else None,
            
            # Métadonnées
            'release_date_formatted': track.get('release_date_formatted', ''),
            'lyrics_state': track.get('lyrics_state', ''),
            'pageviews': track.get('stats', {}).get('pageviews') if track.get('stats') else None,
            'annotation_count': track.get('annotation_count', 0),
            
            # Médias
            'song_art_image_url': track.get('song_art_image_url', ''),
            'header_image_url': track.get('header_image_url', ''),
            
            # Timestamp d'extraction
            'extracted_at': datetime.now(timezone.utc).isoformat(),
            'extraction_source': 'genius_api'
        }
        
        return enriched
    
    @lru_cache(maxsize=128)
    def _assess_track_quality(self, track: Dict[str, Any]) -> str:
        """
        Évalue la qualité des données d'un morceau avec cache.
        
        Args:
            track: Données du morceau enrichies
            
        Returns:
            Niveau de qualité ('high', 'medium', 'low')
        """
        score = 0
        
        # Critères de qualité
        if track.get('lyrics_state') == 'complete':
            score += 3
        elif track.get('lyrics_state') == 'partial':
            score += 1
        
        if track.get('primary_artist', {}).get('name'):
            score += 2
        
        if track.get('album') and track.get('album', {}).get('name'):
            score += 2
        
        if track.get('release_date_formatted'):
            score += 1
        
        if track.get('featured_artists'):
            score += 1
        
        if track.get('producer_artists'):
            score += 2
        
        if track.get('pageviews', 0) > 1000:
            score += 1
        
        # Classification par score
        if score >= 8:
            return QualityLevel.HIGH.value
        elif score >= 5:
            return QualityLevel.MEDIUM.value
        else:
            return QualityLevel.LOW.value
    
    def _update_performance_metrics(self, result: DiscoveryResult) -> None:
        """
        Met à jour les métriques de performance globales.
        
        Args:
            result: Résultat de découverte à intégrer
        """
        self.performance_metrics['total_api_calls'] += result.api_calls_made
        self.performance_metrics['total_cache_hits'] += result.cache_hits
        self.performance_metrics['total_tracks_found'] += result.total_found
        
        # Mise à jour de la moyenne du temps de réponse
        current_avg = self.performance_metrics['average_response_time']
        new_time = result.discovery_time_seconds
        
        if current_avg == 0:
            self.performance_metrics['average_response_time'] = new_time
        else:
            # Moyenne mobile simple
            self.performance_metrics['average_response_time'] = (current_avg + new_time) / 2
    
    # ===== MÉTHODES UTILITAIRES =====
    
    @lru_cache(maxsize=1)
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Retourne les statistiques de performance avec cache.
        
        Returns:
            Dictionnaire des métriques de performance
        """
        total_requests = (self.performance_metrics['total_api_calls'] + 
                         self.performance_metrics['total_cache_hits'])
        
        return {
            'total_api_calls': self.performance_metrics['total_api_calls'],
            'total_cache_hits': self.performance_metrics['total_cache_hits'],
            'cache_hit_rate': (self.performance_metrics['total_cache_hits'] / max(total_requests, 1)) * 100,
            'total_tracks_found': self.performance_metrics['total_tracks_found'],
            'average_response_time': self.performance_metrics['average_response_time'],
            'error_count': self.performance_metrics['error_count'],
            'tracks_per_api_call': (self.performance_metrics['total_tracks_found'] / 
                                  max(self.performance_metrics['total_api_calls'], 1))
        }
    
    def reset_performance_stats(self) -> None:
        """Remet à zéro les statistiques de performance"""
        self.performance_metrics = {
            'total_api_calls': 0,
            'total_cache_hits': 0,
            'total_tracks_found': 0,
            'average_response_time': 0.0,
            'error_count': 0
        }
        
        # Vider le cache LRU si nécessaire
        self.discover_artist_tracks.cache_clear()
        self._is_suspicious_content.cache_clear()
        self._assess_track_quality.cache_clear()
        
        self.logger.info("📊 Statistiques de performance réinitialisées")
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Teste la connexion à l'API Genius.
        
        Returns:
            Tuple (succès, message)
        """
        try:
            url = f"{self.base_url}/search"
            params = {'q': 'test'}
            
            response = self.session.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            return True, "Connexion Genius API réussie"
            
        except requests.exceptions.RequestException as e:
            return False, f"Erreur connexion Genius API: {e}"
    
    def __repr__(self) -> str:
        """Représentation string de l'instance"""
        stats = self.get_performance_stats()
        return (f"GeniusDiscovery(api_calls={stats['total_api_calls']}, "
                f"tracks_found={stats['total_tracks_found']}, "
                f"cache_hit_rate={stats['cache_hit_rate']:.1f}%)")


# ===== FONCTIONS UTILITAIRES MODULE =====

def create_genius_discovery() -> Optional[GeniusDiscovery]:
    """
    Factory function pour créer une instance GeniusDiscovery avec gestion d'erreurs.
    
    Returns:
        Instance GeniusDiscovery ou None si échec
    """
    try:
        return GeniusDiscovery()
    except Exception as e:
        logging.getLogger(__name__).error(f"❌ Impossible de créer GeniusDiscovery: {e}")
        return None


def test_genius_api() -> Dict[str, Any]:
    """
    Teste l'API Genius et retourne un rapport de diagnostic.
    
    Returns:
        Dictionnaire avec les résultats du test
    """
    logger = logging.getLogger(__name__)
    
    try:
        discovery = create_genius_discovery()
        if not discovery:
            return {
                'success': False,
                'error': 'Impossible de créer une instance GeniusDiscovery',
                'api_available': False
            }
        
        # Test de connexion
        connection_ok, connection_msg = discovery.test_connection()
        
        # Test de recherche simple
        test_result = None
        if connection_ok:
            try:
                test_result = discovery.discover_artist_tracks("Eminem", max_tracks=1)
            except Exception as e:
                test_result = DiscoveryResult(success=False, error=str(e))
        
        return {
            'success': connection_ok and (test_result.success if test_result else False),
            'connection_status': connection_msg,
            'api_available': connection_ok,
            'test_search_success': test_result.success if test_result else False,
            'test_tracks_found': test_result.total_found if test_result else 0,
            'performance_stats': discovery.get_performance_stats(),
            'api_key_configured': bool(settings.genius_api_key)
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur test Genius API: {e}")
        return {
            'success': False,
            'error': str(e),
            'api_available': False
        }