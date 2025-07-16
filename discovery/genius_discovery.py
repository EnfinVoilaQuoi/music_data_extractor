# discovery/genius_discovery.py - Version complète corrigée
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import time
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# IMPORTS ABSOLUS - CORRECTION MAJEURE
from config.settings import settings
from models.entities import Track, Artist
from models.enums import DataSource, QualityLevel
from core.exceptions import APIError, APIRateLimitError, DataValidationError
# Import conditionnel pour les modules qui peuvent ne pas exister encore
try:
    from core.cache import CacheManager
except ImportError:
    CacheManager = None

try:
    from core.rate_limiter import RateLimiter
except ImportError:
    RateLimiter = None

# Import des fonctions text_utils avec noms corrects
from utils.text_utils import clean_artist_name, normalize_text

@dataclass
class DiscoveryResult:
    """Résultat d'une découverte de morceaux"""
    success: bool
    tracks: List[Dict[str, Any]] = None
    total_found: int = 0
    error: Optional[str] = None
    source: str = "genius"
    quality_score: float = 0.0
    
    def __post_init__(self):
        if self.tracks is None:
            self.tracks = []
        self.total_found = len(self.tracks)

class GeniusDiscovery:
    """
    Découverte de morceaux via l'API Genius.
    
    Responsabilités :
    - Recherche d'artistes sur Genius
    - Découverte de tous leurs morceaux
    - Extraction des métadonnées de base
    - Filtrage et validation des résultats
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration API Genius
        self.api_key = settings.genius_api_key
        if not self.api_key:
            raise APIError("Clé API Genius manquante")
        
        self.base_url = "https://api.genius.com"
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'User-Agent': 'MusicDataExtractor/1.0'
        }
        
        # Session HTTP avec retry automatique
        self.session = self._create_session()
        
        # Cache et rate limiting (optionnels)
        self.cache_manager = CacheManager() if CacheManager else None
        self.rate_limiter = RateLimiter(30, 60) if RateLimiter else None
        
        # Statistiques
        self.stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'artists_found': 0,
            'tracks_discovered': 0
        }
        
        self.logger.info("GeniusDiscovery initialisé avec cache" if self.cache_manager else "GeniusDiscovery initialisé sans cache")
    
    def _create_session(self) -> requests.Session:
        """Crée une session HTTP avec retry automatique"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def discover_artist_tracks(self, artist_name: str, max_tracks: int = 100) -> DiscoveryResult:
        """
        Découvre les morceaux d'un artiste sur Genius
        
        Args:
            artist_name: Nom de l'artiste à rechercher
            max_tracks: Nombre maximum de morceaux à récupérer
            
        Returns:
            DiscoveryResult avec les morceaux trouvés
        """
        try:
            self.logger.info(f"🔍 Découverte de {artist_name} sur Genius (max {max_tracks} tracks)")
            
            # Nettoyer le nom de l'artiste
            clean_name = clean_artist_name(artist_name)
            self.logger.info(f"Nom nettoyé: '{clean_name}'")
            
            # Rechercher l'artiste
            artist_info = self._search_artist(clean_name)
            if not artist_info:
                # Essayer avec le nom original si différent
                if clean_name != artist_name:
                    self.logger.info(f"Tentative avec le nom original: '{artist_name}'")
                    artist_info = self._search_artist(artist_name)
                
                if not artist_info:
                    self.logger.warning(f"❌ Artiste '{artist_name}' non trouvé sur Genius")
                    return DiscoveryResult(
                        success=False,
                        error=f"Artiste '{artist_name}' non trouvé sur Genius"
                    )
            
            self.logger.info(f"✅ Artiste trouvé: {artist_info.get('name')} (ID: {artist_info.get('id')})")
            
            # Découvrir les morceaux
            tracks = self._get_artist_songs(artist_info['id'], max_tracks)
            
            # Calculer le score de qualité
            quality_score = self._calculate_quality_score(tracks)
            
            result = DiscoveryResult(
                success=True,
                tracks=tracks,
                total_found=len(tracks),
                source="genius",
                quality_score=quality_score
            )
            
            self.stats['tracks_discovered'] += len(tracks)
            self.logger.info(f"🎵 Découverte terminée: {len(tracks)} morceaux trouvés pour {artist_name}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de la découverte de {artist_name}: {e}")
            return DiscoveryResult(
                success=False,
                error=str(e)
            )
    
    def _search_artist(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """Recherche un artiste sur Genius (principal ET featuring)"""
        cache_key = f"genius_artist_search_{normalize_text(artist_name)}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached = self.cache_manager.get(cache_key)
            if cached:
                self.stats['cache_hits'] += 1
                self.logger.info(f"💾 Cache hit pour artiste: {artist_name}")
                return cached
        
        # Rate limiting
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        # Recherche API
        try:
            url = f"{self.base_url}/search"
            params = {'q': artist_name}
            
            self.logger.info(f"🌐 Recherche API Genius: '{artist_name}'")
            response = self.session.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            self.stats['api_calls'] += 1
            
            data = response.json()
            hits = data.get('response', {}).get('hits', [])
            
            self.logger.info(f"📊 API Genius retourne {len(hits)} résultats")
            
            # Debug: afficher les premiers résultats
            for i, hit in enumerate(hits[:3]):
                result = hit.get('result', {})
                primary_artist = result.get('primary_artist', {})
                self.logger.debug(f"  {i+1}. {result.get('title', 'N/A')} - {primary_artist.get('name', 'N/A')}")
            
            # Chercher l'artiste dans les résultats (artiste principal ET featuring)
            for i, hit in enumerate(hits):
                result = hit.get('result', {})
                
                # Vérifier l'artiste principal
                if result.get('primary_artist'):
                    artist = result['primary_artist']
                    if self._is_matching_artist(artist['name'], artist_name):
                        self.logger.info(f"🎯 Artiste principal trouvé: {artist['name']} (ID: {artist.get('id')})")
                        # CORRECTION: expire_days au lieu de expire_hours
                        if self.cache_manager:
                            self.cache_manager.set(cache_key, artist, expire_days=1)
                        
                        self.stats['artists_found'] += 1
                        return artist
                
                # Vérifier les artistes en featuring
                featured_artists = result.get('featured_artists', [])
                for featured in featured_artists:
                    if self._is_matching_artist(featured['name'], artist_name):
                        self.logger.info(f"🎯 Artiste en featuring trouvé: {featured['name']} (ID: {featured.get('id')})")
                        # CORRECTION: expire_days au lieu de expire_hours
                        if self.cache_manager:
                            self.cache_manager.set(cache_key, featured, expire_days=1)
                        
                        self.stats['artists_found'] += 1
                        return featured
            
            self.logger.warning(f"⚠️ Aucun artiste correspondant trouvé pour: {artist_name}")
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Erreur recherche artiste {artist_name}: {e}")
            raise APIError(f"Erreur API Genius: {e}")
    
    def _get_artist_songs(self, artist_id: int, max_tracks: int) -> List[Dict[str, Any]]:
        """Récupère les morceaux d'un artiste (principal ET featuring)"""
        songs = []
        page = 1
        per_page = 50
        
        self.logger.info(f"🎵 Recherche des morceaux pour l'artiste ID {artist_id}")
        
        while len(songs) < max_tracks:
            try:
                # Rate limiting
                if self.rate_limiter:
                    self.rate_limiter.wait_if_needed()
                
                url = f"{self.base_url}/artists/{artist_id}/songs"
                params = {
                    'page': page,
                    'per_page': min(per_page, max_tracks - len(songs)),
                    'sort': 'popularity'
                }
                
                self.logger.info(f"📄 Récupération page {page} (jusqu'à {params['per_page']} morceaux)")
                response = self.session.get(url, headers=self.headers, params=params, timeout=30)
                response.raise_for_status()
                
                self.stats['api_calls'] += 1
                
                data = response.json()
                page_songs = data.get('response', {}).get('songs', [])
                
                if not page_songs:
                    self.logger.info(f"📄 Aucun morceau trouvé à la page {page}, arrêt")
                    break
                
                self.logger.info(f"📄 Page {page}: {len(page_songs)} morceaux trouvés")
                
                # Filtrer et convertir les morceaux
                for song in page_songs:
                    if len(songs) >= max_tracks:
                        break
                    
                    processed_song = self._process_song_data(song)
                    if processed_song:
                        songs.append(processed_song)
                        self.logger.debug(f"  ✅ Morceau ajouté: {processed_song.get('title')}")
                
                page += 1
                time.sleep(0.5)  # Délai entre les requêtes (plus conservateur)
                
            except Exception as e:
                self.logger.error(f"❌ Erreur récupération morceaux page {page}: {e}")
                break
        
        self.logger.info(f"🎵 Total de {len(songs)} morceaux récupérés pour l'artiste {artist_id}")
        return songs
    
    def _process_song_data(self, song_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Traite les données d'un morceau depuis l'API Genius"""
        try:
            # Filtrer les morceaux non pertinents
            if not self._is_valid_song(song_data):
                return None
            
            # Extraire les informations
            processed = {
                'title': song_data.get('title', '').strip(),
                'artist_name': song_data.get('primary_artist', {}).get('name', '').strip(),
                'genius_id': str(song_data.get('id', '')),
                'genius_url': song_data.get('url', ''),
                'release_date': song_data.get('release_date_for_display'),
                'featured_artists': [],
                'album_name': None,
                'source': DataSource.GENIUS
            }
            
            # Album
            album = song_data.get('album')
            if album:
                processed['album_name'] = album.get('name', '').strip()
            
            # Artistes en featuring
            featured_artists = song_data.get('featured_artists', [])
            if featured_artists:
                processed['featured_artists'] = [
                    artist.get('name', '').strip() 
                    for artist in featured_artists
                ]
            
            return processed
            
        except Exception as e:
            self.logger.error(f"❌ Erreur traitement morceau: {e}")
            return None
    
    def _is_valid_song(self, song_data: Dict[str, Any]) -> bool:
        """Vérifie si un morceau est valide pour l'extraction"""
        # Vérifier que c'est bien un morceau (pas un album ou autre)
        if not song_data.get('primary_artist'):
            return False
        
        # Vérifier qu'il y a un titre
        title = song_data.get('title', '').strip()
        if not title:
            return False
        
        # Filtrer les types non désirés (annotations, etc.)
        song_type = song_data.get('_type', '')
        if song_type in ['annotation', 'album']:
            return False
        
        # Filtrer les titres suspects (souvent des erreurs)
        suspicious_patterns = [
            'track list',
            'tracklist',
            'album art',
            'credits',
            'liner notes'
        ]
        
        title_lower = title.lower()
        for pattern in suspicious_patterns:
            if pattern in title_lower:
                return False
        
        return True
    
    def _is_matching_artist(self, api_name: str, search_name: str) -> bool:
        """Vérifie si le nom d'artiste de l'API correspond à la recherche"""
        if not api_name or not search_name:
            return False
        
        # Normaliser les noms pour la comparaison
        api_normalized = normalize_text(api_name).lower()
        search_normalized = normalize_text(search_name).lower()
        
        # Correspondance exacte
        if api_normalized == search_normalized:
            return True
        
        # Correspondance partielle (pour gérer les variations)
        if search_normalized in api_normalized or api_normalized in search_normalized:
            return True
        
        # Correspondance avec séparateurs différents
        api_no_separators = api_normalized.replace(' ', '').replace('-', '').replace('_', '')
        search_no_separators = search_normalized.replace(' ', '').replace('-', '').replace('_', '')
        
        if api_no_separators == search_no_separators:
            return True
        
        return False
    
    def _calculate_quality_score(self, tracks: List[Dict[str, Any]]) -> float:
        """Calcule un score de qualité pour les morceaux découverts"""
        if not tracks:
            return 0.0
        
        score = 0.0
        total_tracks = len(tracks)
        
        for track in tracks:
            track_score = 0.0
            
            # Points pour les métadonnées disponibles
            if track.get('title'):
                track_score += 1.0
            if track.get('album_name'):
                track_score += 0.5
            if track.get('release_date'):
                track_score += 0.5
            if track.get('genius_url'):
                track_score += 0.3
            if track.get('featured_artists'):
                track_score += 0.2
            
            # Score maximum par track: 2.5
            score += min(track_score, 2.5)
        
        # Score final sur 100
        max_possible_score = total_tracks * 2.5
        return (score / max_possible_score) * 100 if max_possible_score > 0 else 0.0
    
    def debug_search_artist(self, artist_name: str) -> Dict[str, Any]:
        """Méthode de debug pour voir ce que retourne Genius"""
        try:
            url = f"{self.base_url}/search"
            params = {'q': artist_name}
            
            response = self.session.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            hits = data.get('response', {}).get('hits', [])
            
            debug_info = {
                'search_query': artist_name,
                'total_hits': len(hits),
                'results': []
            }
            
            for i, hit in enumerate(hits[:10]):  # Seulement les 10 premiers
                result = hit.get('result', {})
                debug_info['results'].append({
                    'index': i,
                    'title': result.get('title', 'N/A'),
                    'primary_artist': result.get('primary_artist', {}).get('name', 'N/A'),
                    'primary_artist_id': result.get('primary_artist', {}).get('id', 'N/A'),
                    'featured_artists': [fa.get('name') for fa in result.get('featured_artists', [])],
                    'type': result.get('_type', 'N/A'),
                    'url': result.get('url', 'N/A')
                })
            
            return debug_info
            
        except Exception as e:
            return {'error': str(e)}
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'utilisation"""
        return self.stats.copy()
    
    def reset_stats(self):
        """Remet à zéro les statistiques"""
        self.stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'artists_found': 0,
            'tracks_discovered': 0
        }
        self.logger.info("Statistiques GeniusDiscovery remises à zéro")