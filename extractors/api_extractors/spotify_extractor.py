# extractors/api_extractors/spotify_extractor.py
"""
Extracteur optimisé pour l'API Spotify - spécialisé dans les métadonnées audio et collaborations.
Version optimisée avec cache intelligent, retry automatique et gestion d'erreurs robuste.
"""

import logging
import time
import base64
from functools import lru_cache
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Imports absolus
from core.exceptions import APIError, APIRateLimitError, APIAuthenticationError
from core.rate_limiter import RateLimiter
from core.cache import CacheManager
from config.settings import settings
from utils.text_utils import normalize_text, clean_artist_name
from models.enums import DataSource, CreditType, AudioFeature


class SpotifyExtractor:
    """
    Extracteur spécialisé pour l'API Spotify Web.
    
    Fonctionnalités optimisées :
    - Authentification OAuth automatique avec refresh
    - Extraction des métadonnées audio avancées
    - Recherche de tracks et albums avec scoring
    - Analyse des features audio (tempo, clé, etc.)
    - Cache intelligent pour éviter les requêtes répétées
    - Rate limiting respectueux des limites Spotify
    - Gestion robuste des erreurs avec retry
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration API Spotify depuis variables d'environnement
        self.client_id = settings.spotify_client_id
        self.client_secret = settings.spotify_client_secret
        
        if not self.client_id or not self.client_secret:
            raise APIAuthenticationError("Spotify", "SPOTIFY_CLIENT_ID et SPOTIFY_CLIENT_SECRET manquants")
        
        # URLs de base
        self.base_url = "https://api.spotify.com/v1"
        self.auth_url = "https://accounts.spotify.com/api/token"
        
        # Gestion des tokens
        self.access_token = None
        self.token_expires_at = None
        
        # Configuration optimisée
        self.config = {
            'max_retries': settings.get('spotify.max_retries', 3),
            'timeout': settings.get('spotify.timeout', 30),
            'rate_limit_requests_per_second': settings.get('spotify.rate_limit', 10),
            'include_audio_features': settings.get('spotify.include_audio_features', True),
            'include_album_info': settings.get('spotify.include_album_info', True),
            'search_limit': settings.get('spotify.search_limit', 50),
            'market': settings.get('spotify.market', 'FR')
        }
        
        # Session HTTP optimisée
        self.session = self._create_session()
        
        # Rate limiter
        self.rate_limiter = RateLimiter(
            requests_per_second=self.config['rate_limit_requests_per_second']
        )
        
        # Cache manager
        self.cache_manager = CacheManager(namespace='spotify') if CacheManager else None
        
        # Authentification initiale
        self._authenticate()
        
        # Statistiques de performance
        self.stats = {
            'tracks_extracted': 0,
            'albums_extracted': 0,
            'searches_performed': 0,
            'api_calls_made': 0,
            'cache_hits': 0,
            'failed_requests': 0,
            'total_time_spent': 0.0
        }
        
        self.logger.info("✅ SpotifyExtractor optimisé initialisé")
    
    def _create_session(self) -> requests.Session:
        """Crée une session HTTP avec retry automatique"""
        session = requests.Session()
        
        # Configuration du retry
        retry_strategy = Retry(
            total=self.config['max_retries'],
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _authenticate(self) -> bool:
        """Authentification OAuth2 Client Credentials Flow"""
        try:
            # Préparer les credentials
            credentials = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode()
            ).decode()
            
            headers = {
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "grant_type": "client_credentials"
            }
            
            response = self.session.post(
                self.auth_url,
                headers=headers,
                data=data,
                timeout=self.config['timeout']
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                expires_in = token_data.get('expires_in', 3600)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
                
                self.logger.info("✅ Authentification Spotify réussie")
                return True
            else:
                self.logger.error(f"❌ Échec authentification Spotify: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Erreur authentification Spotify: {e}")
            return False
    
    def _ensure_authenticated(self) -> bool:
        """S'assure que le token est valide, le renouvelle si nécessaire"""
        if not self.access_token or datetime.now() >= self.token_expires_at:
            return self._authenticate()
        return True
    
    def _make_api_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Effectue une requête API avec gestion d'erreurs et rate limiting"""
        self.rate_limiter.wait()
        
        if not self._ensure_authenticated():
            raise APIAuthenticationError("Spotify", "Impossible de s'authentifier")
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            start_time = time.time()
            response = self.session.get(
                url,
                headers=headers,
                params=params or {},
                timeout=self.config['timeout']
            )
            
            self.stats['api_calls_made'] += 1
            self.stats['total_time_spent'] += time.time() - start_time
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 1))
                self.logger.warning(f"⚠️ Rate limit atteint, attente {retry_after}s")
                time.sleep(retry_after)
                raise APIRateLimitError("Spotify", retry_after)
            elif response.status_code == 401:
                self.logger.warning("⚠️ Token expiré, renouvellement...")
                self._authenticate()
                return self._make_api_request(endpoint, params)
            else:
                self.logger.error(f"❌ Erreur API Spotify {response.status_code}: {response.text}")
                self.stats['failed_requests'] += 1
                return None
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Erreur réseau Spotify: {e}")
            self.stats['failed_requests'] += 1
            return None
    
    # ===== MÉTHODES D'EXTRACTION PRINCIPALES =====
    
    def search_track(self, query: str, artist: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Recherche de tracks sur Spotify avec scoring de pertinence.
        
        Args:
            query: Titre du morceau à rechercher
            artist: Nom de l'artiste (optionnel mais recommandé)
            limit: Nombre max de résultats (max 50)
            
        Returns:
            Liste des tracks trouvées avec score de pertinence
        """
        cache_key = f"search_track_{query}_{artist}_{limit}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            # Construction de la requête optimisée
            search_query = self._build_search_query(query, artist=artist)
            
            params = {
                'q': search_query,
                'type': 'track',
                'limit': min(limit, 50),
                'market': self.config['market']
            }
            
            data = self._make_api_request('search', params)
            if not data:
                return []
            
            tracks = data.get('tracks', {}).get('items', [])
            
            # Processing et scoring des résultats
            processed_tracks = []
            for track in tracks:
                processed_track = self._process_track_data(track)
                
                # Calcul du score de pertinence
                relevance_score = self._calculate_relevance_score(
                    processed_track, query, artist
                )
                processed_track['relevance_score'] = relevance_score
                
                processed_tracks.append(processed_track)
            
            # Tri par score de pertinence
            processed_tracks.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
            
            # Mise en cache
            if self.cache_manager:
                self.cache_manager.set(cache_key, processed_tracks, ttl=3600)
            
            self.stats['searches_performed'] += 1
            return processed_tracks
            
        except Exception as e:
            self.logger.error(f"❌ Erreur recherche Spotify: {e}")
            return []
    
    def get_track_details(self, track_id: str, include_audio_features: bool = True) -> Optional[Dict[str, Any]]:
        """
        Récupère les détails complets d'un track Spotify.
        
        Args:
            track_id: ID Spotify du track
            include_audio_features: Inclure les features audio
            
        Returns:
            Dictionnaire avec toutes les données du track
        """
        cache_key = f"track_details_{track_id}_{include_audio_features}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            # Données de base du track
            track_data = self._make_api_request(f'tracks/{track_id}')
            if not track_data:
                return None
            
            processed_data = self._process_track_data(track_data)
            
            # Audio features si demandées
            if include_audio_features:
                audio_features = self._get_audio_features(track_id)
                if audio_features:
                    processed_data['audio_features'] = audio_features
            
            # Mise en cache
            if self.cache_manager:
                self.cache_manager.set(cache_key, processed_data, ttl=3600)
            
            self.stats['tracks_extracted'] += 1
            return processed_data
            
        except Exception as e:
            self.logger.error(f"❌ Erreur récupération track {track_id}: {e}")
            return None
    
    def get_album_details(self, album_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les détails complets d'un album Spotify.
        
        Args:
            album_id: ID Spotify de l'album
            
        Returns:
            Dictionnaire avec toutes les données de l'album
        """
        cache_key = f"album_details_{album_id}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            album_data = self._make_api_request(f'albums/{album_id}')
            if not album_data:
                return None
            
            processed_data = self._process_album_data(album_data)
            
            # Mise en cache
            if self.cache_manager:
                self.cache_manager.set(cache_key, processed_data, ttl=3600)
            
            self.stats['albums_extracted'] += 1
            return processed_data
            
        except Exception as e:
            self.logger.error(f"❌ Erreur récupération album {album_id}: {e}")
            return None
    
    def _get_audio_features(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les audio features d'un track"""
        try:
            data = self._make_api_request(f'audio-features/{track_id}')
            if data:
                return self._process_audio_features(data)
            return None
        except Exception as e:
            self.logger.debug(f"Erreur audio features {track_id}: {e}")
            return None
    
    # ===== MÉTHODES DE TRAITEMENT =====
    
    def _process_track_data(self, track_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et nettoie les données d'un track"""
        processed = {
            'spotify_id': track_data.get('id'),
            'title': track_data.get('name'),
            'duration_ms': track_data.get('duration_ms'),
            'duration_seconds': track_data.get('duration_ms', 0) // 1000 if track_data.get('duration_ms') else None,
            'explicit': track_data.get('explicit', False),
            'popularity': track_data.get('popularity'),
            'preview_url': track_data.get('preview_url'),
            'external_urls': track_data.get('external_urls', {}),
            'disc_number': track_data.get('disc_number', 1),
            'track_number': track_data.get('track_number'),
            'is_local': track_data.get('is_local', False),
            'available_markets': track_data.get('available_markets', [])
        }
        
        # Artistes
        artists = track_data.get('artists', [])
        if artists:
            processed['artist'] = clean_artist_name(artists[0].get('name', ''))
            processed['artist_id'] = artists[0].get('id')
            processed['all_artists'] = [clean_artist_name(artist.get('name', '')) for artist in artists]
            processed['all_artist_ids'] = [artist.get('id') for artist in artists]
        
        # Album
        album = track_data.get('album', {})
        if album:
            processed['album'] = album.get('name')
            processed['album_id'] = album.get('id')
            processed['album_type'] = album.get('album_type')
            processed['release_date'] = album.get('release_date')
            
            # Images de l'album
            images = album.get('images', [])
            if images:
                processed['album_art_url'] = images[0].get('url')  # Plus grande image
                processed['album_images'] = images
        
        # Métadonnées d'extraction
        processed['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'source': DataSource.SPOTIFY.value,
            'extractor_version': '1.0.0'
        }
        
        return processed
    
    def _process_album_data(self, album_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et nettoie les données d'un album"""
        processed = {
            'spotify_id': album_data.get('id'),
            'name': album_data.get('name'),
            'album_type': album_data.get('album_type'),
            'total_tracks': album_data.get('total_tracks'),
            'release_date': album_data.get('release_date'),
            'release_date_precision': album_data.get('release_date_precision'),
            'genres': album_data.get('genres', []),
            'popularity': album_data.get('popularity'),
            'external_urls': album_data.get('external_urls', {}),
            'copyrights': album_data.get('copyrights', []),
            'label': album_data.get('label'),
            'available_markets': album_data.get('available_markets', [])
        }
        
        # Artistes
        artists = album_data.get('artists', [])
        if artists:
            processed['artist'] = clean_artist_name(artists[0].get('name', ''))
            processed['artist_id'] = artists[0].get('id')
            processed['all_artists'] = [clean_artist_name(artist.get('name', '')) for artist in artists]
        
        # Images
        images = album_data.get('images', [])
        if images:
            processed['cover_art_url'] = images[0].get('url')
            processed['images'] = images
        
        # Tracks de l'album
        tracks = album_data.get('tracks', {}).get('items', [])
        if tracks:
            processed['tracks'] = [
                {
                    'id': track.get('id'),
                    'name': track.get('name'),
                    'track_number': track.get('track_number'),
                    'duration_ms': track.get('duration_ms'),
                    'explicit': track.get('explicit')
                }
                for track in tracks
            ]
        
        return processed
    
    def _process_audio_features(self, features_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite les audio features"""
        return {
            'danceability': features_data.get('danceability'),
            'energy': features_data.get('energy'),
            'key': features_data.get('key'),
            'loudness': features_data.get('loudness'),
            'mode': features_data.get('mode'),
            'speechiness': features_data.get('speechiness'),
            'acousticness': features_data.get('acousticness'),
            'instrumentalness': features_data.get('instrumentalness'),
            'liveness': features_data.get('liveness'),
            'valence': features_data.get('valence'),
            'tempo': features_data.get('tempo'),
            'time_signature': features_data.get('time_signature'),
            # Champs dérivés
            'bpm': round(features_data.get('tempo', 0)) if features_data.get('tempo') else None,
            'key_name': self._convert_spotify_key(features_data.get('key')) if features_data.get('key') is not None else None,
            'mode_name': 'Major' if features_data.get('mode') == 1 else 'Minor' if features_data.get('mode') == 0 else None
        }
    
    def _build_search_query(self, track_title: str, artist: Optional[str] = None) -> str:
        """Construit une requête de recherche optimisée"""
        query_parts = [f'track:"{track_title}"']
        
        if artist:
            query_parts.append(f'artist:"{artist}"')
        
        return ' '.join(query_parts)
    
    def _calculate_relevance_score(self, track_data: Dict[str, Any], 
                                 search_title: str, search_artist: Optional[str] = None) -> float:
        """Calcule un score de pertinence pour un résultat de recherche"""
        score = 0.0
        
        track_title = track_data.get('title', '').lower()
        track_artist = track_data.get('artist', '').lower()
        
        # Score basé sur le titre (poids: 60%)
        title_similarity = self._calculate_text_similarity(search_title.lower(), track_title)
        score += title_similarity * 0.6
        
        # Score basé sur l'artiste (poids: 30%)
        if search_artist:
            artist_similarity = self._calculate_text_similarity(search_artist.lower(), track_artist)
            score += artist_similarity * 0.3
        
        # Bonus popularité (poids: 10%)
        popularity = track_data.get('popularity', 0)
        score += (popularity / 100) * 0.1
        
        return min(score, 1.0)
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calcule la similarité entre deux textes (algorithme simple)"""
        if text1 == text2:
            return 1.0
        
        if text1 in text2 or text2 in text1:
            return 0.8
        
        # Jaccard similarity sur les mots
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    @lru_cache(maxsize=12)
    def _convert_spotify_key(self, key_number: int) -> str:
        """Convertit un numéro de clé Spotify en nom de note"""
        key_mapping = {
            0: 'C', 1: 'C#', 2: 'D', 3: 'D#', 4: 'E', 5: 'F',
            6: 'F#', 7: 'G', 8: 'G#', 9: 'A', 10: 'A#', 11: 'B'
        }
        return key_mapping.get(key_number, 'Unknown')
    
    # ===== MÉTHODES UTILITAIRES =====
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance"""
        return self.stats.copy()
    
    def clear_cache(self) -> bool:
        """Vide le cache Spotify"""
        if self.cache_manager:
            return self.cache_manager.clear()
        return True
    
    def health_check(self) -> Dict[str, Any]:
        """Vérifie l'état de santé de l'extracteur"""
        health = {
            'status': 'healthy',
            'issues': [],
            'authenticated': bool(self.access_token),
            'token_expires_at': self.token_expires_at.isoformat() if self.token_expires_at else None
        }
        
        # Vérifier l'authentification
        if not self._ensure_authenticated():
            health['status'] = 'unhealthy'
            health['issues'].append('Authentication failed')
        
        # Test API simple
        try:
            test_result = self._make_api_request('search', {'q': 'test', 'type': 'track', 'limit': 1})
            if not test_result:
                health['status'] = 'degraded'
                health['issues'].append('API test failed')
        except Exception as e:
            health['status'] = 'unhealthy'
            health['issues'].append(f'API error: {str(e)}')
        
        return health
