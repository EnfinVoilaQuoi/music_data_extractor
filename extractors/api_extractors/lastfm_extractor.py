# extractors/api_extractors/lastfm_extractor.py
"""
Extracteur optimisé pour l'API Last.fm - spécialisé dans les tags, genres et popularité.
Version optimisée avec cache intelligent, retry automatique et gestion d'erreurs robuste.
"""

import logging
import time
import hashlib
from functools import lru_cache
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
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
from models.enums import DataSource, Genre


class LastFMExtractor:
    """
    Extracteur spécialisé pour l'API Last.fm.
    
    Fonctionnalités optimisées :
    - Extraction des métadonnées musicales (tags, genres)
    - Informations sur la popularité (scrobbles, listeners)
    - Données d'albums et d'artistes complémentaires
    - Tags et genres pour enrichir les données
    - Cache intelligent pour éviter les requêtes répétées
    - Rate limiting respectueux des limites Last.fm
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration API Last.fm depuis variables d'environnement
        self.api_key = settings.last_fm_api_key
        
        if not self.api_key:
            self.logger.warning("⚠️ Clé API Last.fm manquante - fonctionnalités limitées")
        
        # URLs de base
        self.base_url = "https://ws.audioscrobbler.com/2.0/"
        
        # Configuration optimisée
        self.config = {
            'max_retries': settings.get('lastfm.max_retries', 3),
            'timeout': settings.get('lastfm.timeout', 15),
            'rate_limit_requests_per_second': settings.get('lastfm.rate_limit', 5),
            'include_tags': settings.get('lastfm.include_tags', True),
            'include_similar_artists': settings.get('lastfm.include_similar_artists', True),
            'include_wiki': settings.get('lastfm.include_wiki', False),
            'max_tags': settings.get('lastfm.max_tags', 10),
            'min_tag_weight': settings.get('lastfm.min_tag_weight', 10),
            'auto_correct': settings.get('lastfm.auto_correct', True)
        }
        
        # Headers pour les requêtes
        self.headers = {
            "User-Agent": "MusicDataExtractor/1.0 (+https://github.com/your-project)"
        }
        
        # Session HTTP optimisée
        self.session = self._create_session()
        
        # Rate limiter
        self.rate_limiter = RateLimiter(
            requests_per_second=self.config['rate_limit_requests_per_second']
        )
        
        # Cache manager
        self.cache_manager = CacheManager(namespace='lastfm') if CacheManager else None
        
        # Statistiques de performance
        self.stats = {
            'tracks_extracted': 0,
            'albums_extracted': 0,
            'artists_extracted': 0,
            'tags_extracted': 0,
            'api_calls_made': 0,
            'cache_hits': 0,
            'failed_requests': 0,
            'total_time_spent': 0.0
        }
        
        self.logger.info("✅ LastFMExtractor optimisé initialisé")
    
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
    
    def _make_api_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Effectue une requête API avec gestion d'erreurs et rate limiting"""
        if not self.api_key:
            self.logger.error("❌ Clé API Last.fm manquante")
            return None
        
        self.rate_limiter.wait()
        
        # Paramètres de base
        request_params = {
            'method': method,
            'api_key': self.api_key,
            'format': 'json',
            **params
        }
        
        # Auto-correction si activée
        if self.config['auto_correct']:
            request_params['autocorrect'] = '1'
        
        try:
            start_time = time.time()
            response = self.session.get(
                self.base_url,
                params=request_params,
                headers=self.headers,
                timeout=self.config['timeout']
            )
            
            self.stats['api_calls_made'] += 1
            self.stats['total_time_spent'] += time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                
                # Vérifier les erreurs Last.fm
                if 'error' in data:
                    error_code = data.get('error')
                    error_message = data.get('message', 'Unknown error')
                    
                    if error_code == 29:  # Rate limit exceeded
                        self.logger.warning("⚠️ Rate limit Last.fm atteint")
                        raise APIRateLimitError("LastFM", 60)
                    elif error_code == 10:  # Invalid API key
                        raise APIAuthenticationError("LastFM", "LAST_FM_API_KEY")
                    else:
                        self.logger.error(f"❌ Erreur API Last.fm {error_code}: {error_message}")
                        return None
                
                return data
                
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                self.logger.warning(f"⚠️ Rate limit atteint, attente {retry_after}s")
                raise APIRateLimitError("LastFM", retry_after)
            else:
                self.logger.error(f"❌ Erreur HTTP Last.fm {response.status_code}: {response.text}")
                self.stats['failed_requests'] += 1
                return None
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Erreur réseau Last.fm: {e}")
            self.stats['failed_requests'] += 1
            return None
    
    # ===== MÉTHODES D'EXTRACTION PRINCIPALES =====
    
    def get_track_info(self, artist: str, track: str, mbid: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Récupère les informations d'un track depuis Last.fm.
        
        Args:
            artist: Nom de l'artiste
            track: Titre du track
            mbid: MusicBrainz ID (optionnel)
            
        Returns:
            Dictionnaire avec les données du track
        """
        cache_key = f"track_info_{artist}_{track}_{mbid}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        params = {
            'artist': artist,
            'track': track
        }
        
        if mbid:
            params['mbid'] = mbid
        
        data = self._make_api_request('track.getInfo', params)
        if not data:
            return None
        
        track_data = data.get('track')
        if not track_data:
            return None
        
        processed_data = self._process_track_data(track_data)
        
        # Mise en cache
        if self.cache_manager:
            self.cache_manager.set(cache_key, processed_data, ttl=3600)
        
        self.stats['tracks_extracted'] += 1
        return processed_data
    
    def get_album_info(self, artist: str, album: str, mbid: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Récupère les informations d'un album depuis Last.fm.
        
        Args:
            artist: Nom de l'artiste
            album: Nom de l'album
            mbid: MusicBrainz ID (optionnel)
            
        Returns:
            Dictionnaire avec les données de l'album
        """
        cache_key = f"album_info_{artist}_{album}_{mbid}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        params = {
            'artist': artist,
            'album': album
        }
        
        if mbid:
            params['mbid'] = mbid
        
        data = self._make_api_request('album.getInfo', params)
        if not data:
            return None
        
        album_data = data.get('album')
        if not album_data:
            return None
        
        processed_data = self._process_album_data(album_data)
        
        # Mise en cache
        if self.cache_manager:
            self.cache_manager.set(cache_key, processed_data, ttl=3600)
        
        self.stats['albums_extracted'] += 1
        return processed_data
    
    def get_artist_info(self, artist: str, mbid: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Récupère les informations d'un artiste depuis Last.fm.
        
        Args:
            artist: Nom de l'artiste
            mbid: MusicBrainz ID (optionnel)
            
        Returns:
            Dictionnaire avec les données de l'artiste
        """
        cache_key = f"artist_info_{artist}_{mbid}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        params = {'artist': artist}
        if mbid:
            params['mbid'] = mbid
        
        data = self._make_api_request('artist.getInfo', params)
        if not data:
            return None
        
        artist_data = data.get('artist')
        if not artist_data:
            return None
        
        processed_data = self._process_artist_data(artist_data)
        
        # Mise en cache
        if self.cache_manager:
            self.cache_manager.set(cache_key, processed_data, ttl=3600)
        
        self.stats['artists_extracted'] += 1
        return processed_data
    
    def get_top_tags(self, artist: Optional[str] = None, track: Optional[str] = None, 
                     album: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Récupère les tags populaires pour un artiste, track ou album.
        
        Args:
            artist: Nom de l'artiste
            track: Titre du track (nécessite artist)
            album: Nom de l'album (nécessite artist)
            
        Returns:
            Liste des tags avec leur poids
        """
        if not self.config['include_tags']:
            return []
        
        method = None
        params = {}
        
        if track and artist:
            method = 'track.getTopTags'
            params = {'artist': artist, 'track': track}
        elif album and artist:
            method = 'album.getTopTags'
            params = {'artist': artist, 'album': album}
        elif artist:
            method = 'artist.getTopTags'
            params = {'artist': artist}
        else:
            return []
        
        data = self._make_api_request(method, params)
        if not data:
            return []
        
        tags_data = data.get('toptags', {}).get('tag', [])
        if isinstance(tags_data, dict):
            tags_data = [tags_data]
        
        processed_tags = []
        for tag in tags_data[:self.config['max_tags']]:
            weight = int(tag.get('count', 0))
            if weight >= self.config['min_tag_weight']:
                processed_tags.append({
                    'name': tag.get('name', '').lower(),
                    'weight': weight,
                    'url': tag.get('url')
                })
        
        self.stats['tags_extracted'] += len(processed_tags)
        return processed_tags
    
    # ===== MÉTHODES DE TRAITEMENT =====
    
    def _process_track_data(self, track_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et nettoie les données d'un track"""
        processed = {
            'lastfm_id': track_data.get('mbid'),
            'name': track_data.get('name'),
            'artist': track_data.get('artist', {}).get('name') if isinstance(track_data.get('artist'), dict) else track_data.get('artist'),
            'url': track_data.get('url'),
            'duration': self._parse_duration(track_data.get('duration')),
            'playcount': self._safe_int(track_data.get('playcount')),
            'listeners': self._safe_int(track_data.get('listeners')),
            'userplaycount': self._safe_int(track_data.get('userplaycount'))
        }
        
        # Album info
        album = track_data.get('album')
        if album:
            processed['album'] = album.get('title') or album.get('name')
            processed['album_mbid'] = album.get('mbid')
            processed['album_url'] = album.get('url')
            
            # Images de l'album
            images = album.get('image', [])
            if images and isinstance(images, list):
                processed['album_art_url'] = next(
                    (img.get('#text') for img in reversed(images) if img.get('#text')), None
                )
        
        # Tags
        tags = track_data.get('toptags', {}).get('tag', [])
        if isinstance(tags, dict):
            tags = [tags]
        processed['tags'] = [tag.get('name') for tag in tags if tag.get('name')]
        
        # Wiki/description
        wiki = track_data.get('wiki')
        if wiki:
            processed['wiki_summary'] = wiki.get('summary')
            processed['wiki_content'] = wiki.get('content')
        
        # Métadonnées d'extraction
        processed['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'source': DataSource.LASTFM.value,
            'extractor_version': '1.0.0'
        }
        
        return processed
    
    def _process_album_data(self, album_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et nettoie les données d'un album"""
        processed = {
            'lastfm_id': album_data.get('mbid'),
            'name': album_data.get('name'),
            'artist': album_data.get('artist'),
            'url': album_data.get('url'),
            'playcount': self._safe_int(album_data.get('playcount')),
            'listeners': self._safe_int(album_data.get('listeners'))
        }
        
        # Images
        images = album_data.get('image', [])
        if images and isinstance(images, list):
            processed['cover_art_url'] = next(
                (img.get('#text') for img in reversed(images) if img.get('#text')), None
            )
        
        # Tags
        tags = album_data.get('tags', {}).get('tag', [])
        if isinstance(tags, dict):
            tags = [tags]
        processed['tags'] = [tag.get('name') for tag in tags if tag.get('name')]
        
        # Tracks
        tracks = album_data.get('tracks', {}).get('track', [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        processed['tracks'] = [
            {
                'name': track.get('name'),
                'duration': self._parse_duration(track.get('duration')),
                'rank': self._safe_int(track.get('@attr', {}).get('rank')) if track.get('@attr') else None,
                'url': track.get('url')
            }
            for track in tracks
        ]
        
        # Wiki
        wiki = album_data.get('wiki')
        if wiki:
            processed['wiki_summary'] = wiki.get('summary')
            processed['wiki_content'] = wiki.get('content')
        
        return processed
    
    def _process_artist_data(self, artist_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et nettoie les données d'un artiste"""
        processed = {
            'lastfm_id': artist_data.get('mbid'),
            'name': artist_data.get('name'),
            'url': artist_data.get('url'),
            'playcount': self._safe_int(artist_data.get('stats', {}).get('playcount')),
            'listeners': self._safe_int(artist_data.get('stats', {}).get('listeners'))
        }
        
        # Images
        images = artist_data.get('image', [])
        if images and isinstance(images, list):
            processed['image_url'] = next(
                (img.get('#text') for img in reversed(images) if img.get('#text')), None
            )
        
        # Tags
        tags = artist_data.get('tags', {}).get('tag', [])
        if isinstance(tags, dict):
            tags = [tags]
        processed['tags'] = [tag.get('name') for tag in tags if tag.get('name')]
        
        # Artistes similaires
        similar = artist_data.get('similar', {}).get('artist', [])
        if isinstance(similar, dict):
            similar = [similar]
        processed['similar_artists'] = [
            {
                'name': artist.get('name'),
                'url': artist.get('url'),
                'match': artist.get('match')
            }
            for artist in similar
        ]
        
        # Bio/wiki
        bio = artist_data.get('bio')
        if bio:
            processed['bio_summary'] = bio.get('summary')
            processed['bio_content'] = bio.get('content')
        
        return processed
    
    def _parse_duration(self, duration: Any) -> Optional[int]:
        """Parse la durée en secondes"""
        if not duration:
            return None
        
        try:
            # Last.fm renvoie parfois la durée en millisecondes
            duration_int = int(duration)
            if duration_int > 10000:  # Probablement en millisecondes
                return duration_int // 1000
            return duration_int
        except (ValueError, TypeError):
            return None
    
    def _safe_int(self, value: Any) -> Optional[int]:
        """Conversion sécurisée en entier"""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    # ===== MÉTHODES UTILITAIRES =====
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance"""
        return self.stats.copy()
    
    def clear_cache(self) -> bool:
        """Vide le cache Last.fm"""
        if self.cache_manager:
            return self.cache_manager.clear()
        return True
    
    def health_check(self) -> Dict[str, Any]:
        """Vérifie l'état de santé de l'extracteur"""
        health = {
            'status': 'healthy',
            'issues': [],
            'api_key_configured': bool(self.api_key)
        }
        
        if not self.api_key:
            health['status'] = 'degraded'
            health['issues'].append('API key not configured')
            return health
        
        # Test API simple
        try:
            test_result = self._make_api_request('chart.getTopTracks', {'limit': 1})
            if not test_result:
                health['status'] = 'degraded'
                health['issues'].append('API test failed')
        except Exception as e:
            health['status'] = 'unhealthy'
            health['issues'].append(f'API error: {str(e)}')
        
        return health