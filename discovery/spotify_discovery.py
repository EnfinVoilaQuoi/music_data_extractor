# discovery/spotify_discovery.py
"""
Découverte de morceaux via l'API Spotify.
Version optimisée avec cache intelligent, authentification automatique et enrichissement des métadonnées.
"""

import logging
import time
import base64
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Imports absolus
from config.settings import settings
from models.entities import Track, Artist, Album
from models.enums import DataSource, QualityLevel
from core.exceptions import APIError, APIRateLimitError, DataValidationError

# Imports conditionnels
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
class SpotifyDiscoveryResult:
    """
    Résultat optimisé d'une découverte Spotify avec métriques détaillées.
    """
    success: bool
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    albums: List[Dict[str, Any]] = field(default_factory=list)
    artist_info: Optional[Dict[str, Any]] = None
    total_found: int = 0
    error: Optional[str] = None
    source: str = "spotify"
    api_calls_made: int = 0
    cache_hits: int = 0
    discovery_time_seconds: float = 0.0
    
    def __post_init__(self):
        self.total_found = len(self.tracks)
    
    @property
    def cache_hit_rate(self) -> float:
        """Calcule le taux de succès du cache"""
        total_requests = self.cache_hits + self.api_calls_made
        if total_requests == 0:
            return 0.0
        return (self.cache_hits / total_requests) * 100


class SpotifyDiscovery:
    """
    Découverte optimisée de morceaux via l'API Spotify.
    
    Fonctionnalités:
    - Authentification automatique avec Client Credentials Flow
    - Cache intelligent des tokens et résultats
    - Rate limiting respectueux des limites Spotify
    - Enrichissement des métadonnées (popularity, preview_url, etc.)
    - Gestion robuste des erreurs avec retry
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration API Spotify
        self.client_id = settings.spotify_client_id
        self.client_secret = settings.spotify_client_secret
        
        if not self.client_id or not self.client_secret:
            raise APIError("Identifiants Spotify manquants dans la configuration")
        
        self.base_url = "https://api.spotify.com/v1"
        self.auth_url = "https://accounts.spotify.com/api/token"
        
        # Session HTTP optimisée
        self.session = self._create_optimized_session()
        
        # Token management
        self.access_token = None
        self.token_expires_at = None
        
        # Composants optionnels
        self.cache_manager = CacheManager() if CacheManager else None
        self.rate_limiter = RateLimiter(calls_per_minute=100) if RateLimiter else None  # Spotify: ~100 req/min
        
        # Métriques de performance
        self.performance_metrics = {
            'total_api_calls': 0,
            'total_cache_hits': 0,
            'total_tracks_found': 0,
            'authentication_count': 0,
            'average_response_time': 0.0,
            'error_count': 0
        }
        
        self.logger.info("✅ SpotifyDiscovery optimisé initialisé")
    
    def _create_optimized_session(self) -> requests.Session:
        """Crée une session HTTP optimisée pour Spotify"""
        session = requests.Session()
        
        # Configuration du retry
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.timeout = 30
        return session
    
    def _authenticate(self) -> bool:
        """
        Authentification via Client Credentials Flow avec cache du token.
        
        Returns:
            True si l'authentification réussit
        """
        # Vérifier si le token est encore valide
        if self.access_token and self.token_expires_at:
            if datetime.now() < self.token_expires_at - timedelta(minutes=5):  # Marge de 5 minutes
                return True
        
        try:
            # Préparer les données d'authentification
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            
            headers = {
                'Authorization': f'Basic {auth_b64}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {'grant_type': 'client_credentials'}
            
            response = self.session.post(self.auth_url, headers=headers, data=data)
            response.raise_for_status()
            
            auth_data = response.json()
            
            # Stocker le token
            self.access_token = auth_data['access_token']
            expires_in = auth_data.get('expires_in', 3600)  # Défaut: 1 heure
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            self.performance_metrics['authentication_count'] += 1
            self.logger.debug("🔑 Authentification Spotify réussie")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erreur authentification Spotify: {e}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """Retourne les headers pour les requêtes API"""
        if not self._authenticate():
            raise APIError("Impossible de s'authentifier auprès de Spotify")
        
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    @lru_cache(maxsize=128)
    def discover_artist_tracks(self, artist_name: str, max_tracks: Optional[int] = None) -> SpotifyDiscoveryResult:
        """
        Découvre les morceaux d'un artiste sur Spotify avec cache LRU.
        
        Args:
            artist_name: Nom de l'artiste à rechercher
            max_tracks: Nombre maximum de morceaux à récupérer
            
        Returns:
            SpotifyDiscoveryResult avec les morceaux trouvés
        """
        start_time = time.time()
        
        try:
            normalized_artist = clean_artist_name(artist_name)
            self.logger.info(f"🔍 Recherche Spotify pour: {normalized_artist}")
            
            # Vérification du cache
            cache_key = f"spotify_discovery_{normalized_artist}_{max_tracks}"
            
            if self.cache_manager:
                cached_result = self.cache_manager.get(cache_key)
                if cached_result:
                    self.performance_metrics['total_cache_hits'] += 1
                    self.logger.info(f"💾 Cache hit Spotify pour {normalized_artist}")
                    
                    result = SpotifyDiscoveryResult(**cached_result)
                    result.cache_hits = 1
                    return result
            
            # Recherche de l'artiste
            artist_data = self._search_artist(normalized_artist)
            if not artist_data:
                return SpotifyDiscoveryResult(
                    success=False,
                    error=f"Artiste '{artist_name}' non trouvé sur Spotify",
                    discovery_time_seconds=time.time() - start_time
                )
            
            # Récupération des albums
            albums = self._get_artist_albums(artist_data['id'])
            
            # Récupération des top tracks
            top_tracks = self._get_artist_top_tracks(artist_data['id'])
            
            # Récupération des tracks de tous les albums
            all_tracks = []
            for album in albums:
                album_tracks = self._get_album_tracks(album['id'])
                # Enrichir avec les infos de l'album
                for track in album_tracks:
                    track['album_info'] = album
                all_tracks.extend(album_tracks)
            
            # Ajouter les top tracks avec déduplication
            existing_track_ids = {track.get('id') for track in all_tracks}
            for track in top_tracks:
                if track.get('id') not in existing_track_ids:
                    all_tracks.append(track)
            
            # Limiter si nécessaire
            if max_tracks and len(all_tracks) > max_tracks:
                # Trier par popularité décroissante
                all_tracks.sort(key=lambda x: x.get('popularity', 0), reverse=True)
                all_tracks = all_tracks[:max_tracks]
            
            # Enrichissement final
            enriched_tracks = self._enrich_tracks_metadata(all_tracks, artist_data)
            
            # Création du résultat
            discovery_time = time.time() - start_time
            result = SpotifyDiscoveryResult(
                success=True,
                tracks=enriched_tracks,
                albums=albums,
                artist_info=artist_data,
                api_calls_made=3 + len(albums),  # search + albums + top_tracks + album_tracks
                discovery_time_seconds=discovery_time
            )
            
            # Mise en cache
            if self.cache_manager and result.success:
                self.cache_manager.set(cache_key, result.__dict__, expire_hours=6)
            
            # Mise à jour des métriques
            self._update_performance_metrics(result)
            
            self.logger.info(f"✅ Spotify: {result.total_found} morceaux trouvés "
                           f"en {discovery_time:.2f}s")
            
            return result
            
        except APIRateLimitError:
            self.logger.warning("⚠️ Limite de taux API Spotify atteinte")
            return SpotifyDiscoveryResult(
                success=False,
                error="Rate limit atteint",
                discovery_time_seconds=time.time() - start_time
            )
        except Exception as e:
            self.logger.error(f"❌ Erreur Spotify pour {artist_name}: {e}")
            self.performance_metrics['error_count'] += 1
            return SpotifyDiscoveryResult(
                success=False,
                error=str(e),
                discovery_time_seconds=time.time() - start_time
            )
    
    def _search_artist(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """
        Recherche un artiste sur Spotify.
        
        Args:
            artist_name: Nom de l'artiste
            
        Returns:
            Données de l'artiste ou None
        """
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        try:
            url = f"{self.base_url}/search"
            params = {
                'q': f'artist:"{artist_name}"',
                'type': 'artist',
                'limit': 1
            }
            
            response = self.session.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            
            self.performance_metrics['total_api_calls'] += 1
            
            data = response.json()
            artists = data.get('artists', {}).get('items', [])
            
            if artists:
                artist = artists[0]
                # Vérification de similarité du nom
                found_name = normalize_text(artist['name'])
                search_name = normalize_text(artist_name)
                
                if found_name == search_name or search_name in found_name:
                    self.logger.debug(f"✅ Artiste Spotify trouvé: {artist['name']}")
                    return artist
            
            self.logger.warning(f"⚠️ Artiste '{artist_name}' non trouvé sur Spotify")
            return None
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Erreur recherche artiste Spotify: {e}")
            return None
    
    def _get_artist_albums(self, artist_id: str) -> List[Dict[str, Any]]:
        """
        Récupère tous les albums d'un artiste.
        
        Args:
            artist_id: ID Spotify de l'artiste
            
        Returns:
            Liste des albums
        """
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        try:
            url = f"{self.base_url}/artists/{artist_id}/albums"
            params = {
                'include_groups': 'album,single,compilation',
                'market': 'FR',  # Marché français pour le rap français
                'limit': 50
            }
            
            response = self.session.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            
            self.performance_metrics['total_api_calls'] += 1
            
            data = response.json()
            albums = data.get('items', [])
            
            self.logger.debug(f"📀 {len(albums)} albums trouvés sur Spotify")
            return albums
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Erreur récupération albums Spotify: {e}")
            return []
    
    def _get_artist_top_tracks(self, artist_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les top tracks d'un artiste.
        
        Args:
            artist_id: ID Spotify de l'artiste
            
        Returns:
            Liste des top tracks
        """
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        try:
            url = f"{self.base_url}/artists/{artist_id}/top-tracks"
            params = {'market': 'FR'}
            
            response = self.session.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            
            self.performance_metrics['total_api_calls'] += 1
            
            data = response.json()
            tracks = data.get('tracks', [])
            
            self.logger.debug(f"🔥 {len(tracks)} top tracks trouvés sur Spotify")
            return tracks
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Erreur récupération top tracks Spotify: {e}")
            return []
    
    def _get_album_tracks(self, album_id: str) -> List[Dict[str, Any]]:
        """
        Récupère toutes les tracks d'un album.
        
        Args:
            album_id: ID Spotify de l'album
            
        Returns:
            Liste des tracks de l'album
        """
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        try:
            url = f"{self.base_url}/albums/{album_id}/tracks"
            params = {'market': 'FR', 'limit': 50}
            
            response = self.session.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            
            self.performance_metrics['total_api_calls'] += 1
            
            data = response.json()
            tracks = data.get('items', [])
            
            return tracks
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Erreur récupération tracks album Spotify: {e}")
            return []
    
    def _enrich_tracks_metadata(self, tracks: List[Dict[str, Any]], artist_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Enrichit les métadonnées des tracks avec les informations Spotify.
        
        Args:
            tracks: Liste des tracks brutes
            artist_data: Données de l'artiste principal
            
        Returns:
            Tracks enrichies
        """
        enriched_tracks = []
        
        for track in tracks:
            try:
                enriched_track = {
                    # Identifiants Spotify
                    'spotify_id': track.get('id'),
                    'spotify_uri': track.get('uri'),
                    'spotify_url': track.get('external_urls', {}).get('spotify'),
                    
                    # Données de base
                    'title': track.get('name', ''),
                    'track_number': track.get('track_number'),
                    'disc_number': track.get('disc_number', 1),
                    'duration_ms': track.get('duration_ms'),
                    'duration_seconds': track.get('duration_ms', 0) // 1000 if track.get('duration_ms') else None,
                    'explicit': track.get('explicit', False),
                    'popularity': track.get('popularity', 0),
                    'preview_url': track.get('preview_url'),
                    
                    # Artiste principal
                    'primary_artist': {
                        'spotify_id': artist_data.get('id'),
                        'name': artist_data.get('name', ''),
                        'spotify_url': artist_data.get('external_urls', {}).get('spotify'),
                        'followers': artist_data.get('followers', {}).get('total', 0),
                        'popularity': artist_data.get('popularity', 0),
                        'genres': artist_data.get('genres', [])
                    },
                    
                    # Artistes supplémentaires (features)
                    'featured_artists': [
                        {
                            'spotify_id': artist.get('id'),
                            'name': artist.get('name', ''),
                            'spotify_url': artist.get('external_urls', {}).get('spotify')
                        }
                        for artist in track.get('artists', [])[1:]  # Exclure l'artiste principal
                    ],
                    
                    # Informations d'album
                    'album': self._extract_album_info(track),
                    
                    # Métadonnées Spotify
                    'is_local': track.get('is_local', False),
                    'is_playable': track.get('is_playable', True),
                    'markets': track.get('available_markets', []),
                    
                    # Source et qualité
                    'data_source': DataSource.SPOTIFY.value,
                    'quality_level': self._assess_spotify_track_quality(track),
                    
                    # Timestamp d'extraction
                    'extracted_at': datetime.now().isoformat(),
                    'extraction_source': 'spotify_api'
                }
                
                enriched_tracks.append(enriched_track)
                
            except Exception as e:
                self.logger.warning(f"⚠️ Erreur enrichissement track Spotify: {e}")
                continue
        
        self.logger.debug(f"🔍 {len(enriched_tracks)}/{len(tracks)} tracks Spotify enrichies")
        return enriched_tracks
    
    def _extract_album_info(self, track: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extrait les informations d'album d'une track.
        
        Args:
            track: Données de la track
            
        Returns:
            Informations d'album ou None
        """
        album_data = track.get('album') or track.get('album_info')
        
        if not album_data:
            return None
        
        return {
            'spotify_id': album_data.get('id'),
            'name': album_data.get('name', ''),
            'spotify_url': album_data.get('external_urls', {}).get('spotify'),
            'album_type': album_data.get('album_type', ''),
            'release_date': album_data.get('release_date', ''),
            'release_date_precision': album_data.get('release_date_precision', ''),
            'total_tracks': album_data.get('total_tracks', 0),
            'images': album_data.get('images', []),
            'cover_art_url': album_data.get('images', [{}])[0].get('url', '') if album_data.get('images') else ''
        }
    
    @lru_cache(maxsize=128)
    def _assess_spotify_track_quality(self, track: Dict[str, Any]) -> str:
        """
        Évalue la qualité des données d'une track Spotify avec cache.
        
        Args:
            track: Données de la track
            
        Returns:
            Niveau de qualité
        """
        score = 0
        
        # Critères de qualité Spotify
        if track.get('popularity', 0) > 50:
            score += 3
        elif track.get('popularity', 0) > 20:
            score += 2
        elif track.get('popularity', 0) > 0:
            score += 1
        
        if track.get('preview_url'):
            score += 2
        
        if track.get('duration_ms') and track.get('duration_ms') > 30000:  # Plus de 30 secondes
            score += 1
        
        if track.get('album'):
            score += 2
        
        if not track.get('explicit'):  # Préférence pour le contenu non explicite
            score += 1
        
        if track.get('is_playable', True):
            score += 1
        
        # Classification par score
        if score >= 8:
            return QualityLevel.HIGH.value
        elif score >= 5:
            return QualityLevel.MEDIUM.value
        else:
            return QualityLevel.LOW.value
    
    def _update_performance_metrics(self, result: SpotifyDiscoveryResult) -> None:
        """Met à jour les métriques de performance globales"""
        self.performance_metrics['total_api_calls'] += result.api_calls_made
        self.performance_metrics['total_cache_hits'] += result.cache_hits
        self.performance_metrics['total_tracks_found'] += result.total_found
        
        # Mise à jour de la moyenne du temps de réponse
        current_avg = self.performance_metrics['average_response_time']
        new_time = result.discovery_time_seconds
        
        if current_avg == 0:
            self.performance_metrics['average_response_time'] = new_time
        else:
            self.performance_metrics['average_response_time'] = (current_avg + new_time) / 2
    
    # ===== MÉTHODES UTILITAIRES =====
    
    @lru_cache(maxsize=1)
    def get_performance_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance avec cache"""
        total_requests = (self.performance_metrics['total_api_calls'] + 
                         self.performance_metrics['total_cache_hits'])
        
        return {
            'total_api_calls': self.performance_metrics['total_api_calls'],
            'total_cache_hits': self.performance_metrics['total_cache_hits'],
            'cache_hit_rate': (self.performance_metrics['total_cache_hits'] / max(total_requests, 1)) * 100,
            'total_tracks_found': self.performance_metrics['total_tracks_found'],
            'authentication_count': self.performance_metrics['authentication_count'],
            'average_response_time': self.performance_metrics['average_response_time'],
            'error_count': self.performance_metrics['error_count'],
            'tracks_per_api_call': (self.performance_metrics['total_tracks_found'] / 
                                  max(self.performance_metrics['total_api_calls'], 1)),
            'token_valid': self.access_token is not None and 
                          self.token_expires_at is not None and 
                          datetime.now() < self.token_expires_at
        }
    
    def reset_performance_stats(self) -> None:
        """Remet à zéro les statistiques de performance"""
        self.performance_metrics = {
            'total_api_calls': 0,
            'total_cache_hits': 0,
            'total_tracks_found': 0,
            'authentication_count': 0,
            'average_response_time': 0.0,
            'error_count': 0
        }
        
        # Vider le cache LRU
        self.discover_artist_tracks.cache_clear()
        self._assess_spotify_track_quality.cache_clear()
        self.get_performance_stats.cache_clear()
        
        self.logger.info("📊 Statistiques Spotify réinitialisées")
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Teste la connexion à l'API Spotify.
        
        Returns:
            Tuple (succès, message)
        """
        try:
            # Test d'authentification
            auth_success = self._authenticate()
            if not auth_success:
                return False, "Échec de l'authentification Spotify"
            
            # Test de requête simple
            url = f"{self.base_url}/search"
            params = {'q': 'test', 'type': 'artist', 'limit': 1}
            
            response = self.session.get(url, headers=self._get_headers(), params=params, timeout=10)
            response.raise_for_status()
            
            return True, "Connexion Spotify API réussie"
            
        except requests.exceptions.RequestException as e:
            return False, f"Erreur connexion Spotify API: {e}"
    
    def get_audio_features(self, track_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Récupère les caractéristiques audio des tracks (BPM, clé, etc.).
        
        Args:
            track_ids: Liste des IDs Spotify des tracks
            
        Returns:
            Liste des caractéristiques audio
        """
        if not track_ids:
            return []
        
        try:
            # Spotify permet jusqu'à 100 tracks par requête
            batch_size = 100
            all_features = []
            
            for i in range(0, len(track_ids), batch_size):
                batch_ids = track_ids[i:i + batch_size]
                
                if self.rate_limiter:
                    self.rate_limiter.wait_if_needed()
                
                url = f"{self.base_url}/audio-features"
                params = {'ids': ','.join(batch_ids)}
                
                response = self.session.get(url, headers=self._get_headers(), params=params)
                response.raise_for_status()
                
                data = response.json()
                features = data.get('audio_features', [])
                all_features.extend([f for f in features if f])  # Exclure les None
                
                self.performance_metrics['total_api_calls'] += 1
            
            self.logger.debug(f"🎵 Caractéristiques audio récupérées pour {len(all_features)} tracks")
            return all_features
            
        except Exception as e:
            self.logger.error(f"❌ Erreur récupération audio features: {e}")
            return []
    
    def __repr__(self) -> str:
        """Représentation string de l'instance"""
        stats = self.get_performance_stats()
        return (f"SpotifyDiscovery(api_calls={stats['total_api_calls']}, "
                f"tracks_found={stats['total_tracks_found']}, "
                f"cache_hit_rate={stats['cache_hit_rate']:.1f}%, "
                f"token_valid={stats['token_valid']})")


# ===== FONCTIONS UTILITAIRES MODULE =====

def create_spotify_discovery() -> Optional[SpotifyDiscovery]:
    """
    Factory function pour créer une instance SpotifyDiscovery.
    
    Returns:
        Instance SpotifyDiscovery ou None si échec
    """
    try:
        return SpotifyDiscovery()
    except Exception as e:
        logging.getLogger(__name__).error(f"❌ Impossible de créer SpotifyDiscovery: {e}")
        return None


def test_spotify_api() -> Dict[str, Any]:
    """
    Teste l'API Spotify et retourne un rapport de diagnostic.
    
    Returns:
        Dictionnaire avec les résultats du test
    """
    logger = logging.getLogger(__name__)
    
    try:
        discovery = create_spotify_discovery()
        if not discovery:
            return {
                'success': False,
                'error': 'Impossible de créer une instance SpotifyDiscovery',
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
                test_result = SpotifyDiscoveryResult(success=False, error=str(e))
        
        return {
            'success': connection_ok and (test_result.success if test_result else False),
            'connection_status': connection_msg,
            'api_available': connection_ok,
            'test_search_success': test_result.success if test_result else False,
            'test_tracks_found': test_result.total_found if test_result else 0,
            'performance_stats': discovery.get_performance_stats(),
            'credentials_configured': bool(settings.spotify_client_id and settings.spotify_client_secret)
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur test Spotify API: {e}")
        return {
            'success': False,
            'error': str(e),
            'api_available': False
        }