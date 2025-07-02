# discovery/genius_discovery.py
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import time
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config.settings import settings
from ..models.entities import Track, Artist
from ..models.enums import DataSource, QualityLevel
from ..core.exceptions import DiscoveryError, RateLimitError, ValidationError
from ..core.cache import CacheManager
from ..core.rate_limiter import RateLimiter
from ..utils.text_utils import clean_artist_name, normalize_title


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
    - Récupération de la liste complète des morceaux d'un artiste
    - Filtrage et validation des résultats
    - Gestion du rate limiting et du cache
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration API
        self.api_key = settings.genius_api_key
        if not self.api_key:
            raise DiscoveryError("Clé API Genius manquante")
        
        self.base_url = "https://api.genius.com"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "MusicDataExtractor/1.0"
        }
        
        # Composants
        self.cache_manager = CacheManager()
        self.rate_limiter = RateLimiter(
            requests_per_period=settings.get('api.genius.rate_limit', 60),
            period_seconds=60
        )
        
        # Session HTTP avec retry automatique
        self.session = self._create_session()
        
        # Statistiques
        self.stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'artists_discovered': 0,
            'tracks_discovered': 0,
            'errors': 0
        }
        
        self.logger.info("GeniusDiscovery initialisé")
    
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
        session.headers.update(self.headers)
        
        return session
    
    def discover_artist_tracks(self, artist_name: str, max_tracks: int = 200) -> DiscoveryResult:
        """
        Découvre tous les morceaux d'un artiste.
        
        Args:
            artist_name: Nom de l'artiste
            max_tracks: Nombre maximum de morceaux à récupérer
            
        Returns:
            DiscoveryResult: Résultat de la découverte
        """
        try:
            self.logger.info(f"Découverte des morceaux pour l'artiste: {artist_name}")
            
            # Recherche de l'artiste
            artist_info = self._search_artist(artist_name)
            if not artist_info:
                return DiscoveryResult(
                    success=False,
                    error=f"Artiste '{artist_name}' non trouvé sur Genius"
                )
            
            artist_id = artist_info['id']
            self.logger.info(f"Artiste trouvé - ID: {artist_id}, Nom: {artist_info['name']}")
            
            # Récupération des morceaux
            tracks = self._get_artist_songs(artist_id, max_tracks)
            
            if not tracks:
                return DiscoveryResult(
                    success=False,
                    error=f"Aucun morceau trouvé pour l'artiste {artist_name}"
                )
            
            # Filtrage et nettoyage
            filtered_tracks = self._filter_and_clean_tracks(tracks, artist_name)
            
            # Calcul du score de qualité
            quality_score = self._calculate_quality_score(filtered_tracks, artist_info)
            
            self.stats['artists_discovered'] += 1
            self.stats['tracks_discovered'] += len(filtered_tracks)
            
            result = DiscoveryResult(
                success=True,
                tracks=filtered_tracks,
                quality_score=quality_score
            )
            
            self.logger.info(f"Découverte terminée: {len(filtered_tracks)} morceaux trouvés")
            return result
            
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"Erreur lors de la découverte: {e}")
            return DiscoveryResult(
                success=False,
                error=str(e)
            )
    
    def _search_artist(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """
        Recherche un artiste sur Genius.
        
        Args:
            artist_name: Nom de l'artiste à rechercher
            
        Returns:
            Dict contenant les infos de l'artiste ou None
        """
        cache_key = f"genius_artist_search_{clean_artist_name(artist_name)}"
        
        # Vérification du cache
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            self.stats['cache_hits'] += 1
            return cached_result
        
        try:
            # Recherche via API
            self.rate_limiter.wait_if_needed()
            
            params = {
                'q': artist_name,
                'per_page': 10
            }
            
            response = self.session.get(
                f"{self.base_url}/search",
                params=params,
                timeout=settings.get('api.timeout', 30)
            )
            
            self.stats['api_calls'] += 1
            
            if response.status_code == 429:
                raise RateLimitError("Rate limit Genius atteint")
            
            response.raise_for_status()
            data = response.json()
            
            # Recherche du meilleur match
            artist_info = self._find_best_artist_match(data.get('response', {}).get('hits', []), artist_name)
            
            if artist_info:
                # Mise en cache
                self.cache_manager.set(cache_key, artist_info)
            
            return artist_info
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur API lors de la recherche d'artiste: {e}")
            raise DiscoveryError(f"Erreur de recherche d'artiste: {e}")
    
    def _find_best_artist_match(self, hits: List[Dict], target_name: str) -> Optional[Dict[str, Any]]:
        """
        Trouve le meilleur match d'artiste dans les résultats de recherche.
        
        Args:
            hits: Résultats de recherche Genius
            target_name: Nom d'artiste recherché
            
        Returns:
            Dict avec les infos de l'artiste ou None
        """
        target_clean = clean_artist_name(target_name).lower()
        best_match = None
        best_score = 0
        
        for hit in hits:
            result = hit.get('result', {})
            primary_artist = result.get('primary_artist', {})
            
            if not primary_artist:
                continue
            
            artist_name = primary_artist.get('name', '')
            artist_clean = clean_artist_name(artist_name).lower()
            
            # Score de correspondance simple
            if artist_clean == target_clean:
                return primary_artist  # Match parfait
            
            # Score basé sur la similarité des noms
            score = self._calculate_name_similarity(target_clean, artist_clean)
            
            if score > best_score and score > 0.7:  # Seuil de similarité
                best_score = score
                best_match = primary_artist
        
        return best_match
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Calcule la similarité entre deux noms d'artistes.
        
        Args:
            name1, name2: Noms à comparer
            
        Returns:
            Score de similarité entre 0 et 1
        """
        # Algorithme simple de similarité basé sur les mots communs
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _get_artist_songs(self, artist_id: int, max_tracks: int) -> List[Dict[str, Any]]:
        """
        Récupère tous les morceaux d'un artiste.
        
        Args:
            artist_id: ID Genius de l'artiste
            max_tracks: Nombre maximum de morceaux
            
        Returns:
            Liste des morceaux
        """
        cache_key = f"genius_artist_songs_{artist_id}_{max_tracks}"
        
        # Vérification du cache
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            self.stats['cache_hits'] += 1
            return cached_result
        
        all_songs = []
        page = 1
        per_page = min(50, max_tracks)  # Genius limite à 50 par page
        
        try:
            while len(all_songs) < max_tracks:
                self.rate_limiter.wait_if_needed()
                
                params = {
                    'page': page,
                    'per_page': per_page,
                    'sort': 'popularity'  # Tri par popularité
                }
                
                response = self.session.get(
                    f"{self.base_url}/artists/{artist_id}/songs",
                    params=params,
                    timeout=settings.get('api.timeout', 30)
                )
                
                self.stats['api_calls'] += 1
                
                if response.status_code == 429:
                    raise RateLimitError("Rate limit Genius atteint")
                
                response.raise_for_status()
                data = response.json()
                
                songs = data.get('response', {}).get('songs', [])
                
                if not songs:
                    break  # Plus de morceaux disponibles
                
                all_songs.extend(songs)
                page += 1
                
                # Pause entre les requêtes
                time.sleep(0.1)
            
            # Limitation au nombre demandé
            result_songs = all_songs[:max_tracks]
            
            # Mise en cache
            self.cache_manager.set(cache_key, result_songs)
            
            return result_songs
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur API lors de la récupération des morceaux: {e}")
            raise DiscoveryError(f"Erreur de récupération des morceaux: {e}")
    
    def _filter_and_clean_tracks(self, tracks: List[Dict], artist_name: str) -> List[Dict[str, Any]]:
        """
        Filtre et nettoie la liste des morceaux.
        
        Args:
            tracks: Liste brute des morceaux
            artist_name: Nom de l'artiste principal
            
        Returns:
            Liste filtrée et nettoyée
        """
        filtered_tracks = []
        seen_titles = set()
        artist_clean = clean_artist_name(artist_name).lower()
        
        for track in tracks:
            try:
                # Validation de base
                if not self._is_valid_track(track):
                    continue
                
                # Extraction des infos
                title = track.get('title', '').strip()
                primary_artist = track.get('primary_artist', {})
                primary_artist_name = primary_artist.get('name', '')
                
                # Filtrage des doublons
                title_normalized = normalize_title(title)
                if title_normalized in seen_titles:
                    continue
                seen_titles.add(title_normalized)
                
                # Vérification que c'est bien l'artiste principal
                if not self._is_primary_artist_match(primary_artist_name, artist_name):
                    continue
                
                # Construction de l'objet track nettoyé
                clean_track = {
                    'genius_id': track.get('id'),
                    'title': title,
                    'artist': primary_artist_name,
                    'url': track.get('url'),
                    'release_date': track.get('release_date_for_display'),
                    'featured_artists': self._extract_featured_artists(track),
                    'stats': {
                        'pageviews': track.get('stats', {}).get('pageviews'),
                        'hot': track.get('stats', {}).get('hot', False)
                    },
                    'api_path': track.get('api_path'),
                    'header_image': track.get('header_image_thumbnail_url'),
                    'raw_data': track  # Garder les données brutes pour debug
                }
                
                filtered_tracks.append(clean_track)
                
            except Exception as e:
                self.logger.warning(f"Erreur lors du traitement d'un morceau: {e}")
                continue
        
        self.logger.info(f"Filtrage terminé: {len(filtered_tracks)}/{len(tracks)} morceaux conservés")
        return filtered_tracks
    
    def _is_valid_track(self, track: Dict) -> bool:
        """
        Valide qu'un morceau contient les données minimales.
        
        Args:
            track: Données du morceau
            
        Returns:
            True si valide
        """
        required_fields = ['id', 'title', 'primary_artist']
        
        for field in required_fields:
            if not track.get(field):
                return False
        
        # Vérification que le titre n'est pas vide
        title = track.get('title', '').strip()
        if not title or len(title) < 2:
            return False
        
        return True
    
    def _is_primary_artist_match(self, genius_artist: str, target_artist: str) -> bool:
        """
        Vérifie si l'artiste Genius correspond à l'artiste recherché.
        
        Args:
            genius_artist: Nom de l'artiste sur Genius
            target_artist: Nom de l'artiste recherché
            
        Returns:
            True si correspondance
        """
        genius_clean = clean_artist_name(genius_artist).lower()
        target_clean = clean_artist_name(target_artist).lower()
        
        # Match exact
        if genius_clean == target_clean:
            return True
        
        # Vérification de similarité élevée
        similarity = self._calculate_name_similarity(genius_clean, target_clean)
        return similarity > 0.8
    
    def _extract_featured_artists(self, track: Dict) -> List[str]:
        """
        Extrait la liste des artistes invités.
        
        Args:
            track: Données du morceau
            
        Returns:
            Liste des noms d'artistes invités
        """
        featured_artists = []
        
        for artist in track.get('featured_artists', []):
            if isinstance(artist, dict) and artist.get('name'):
                featured_artists.append(artist['name'])
        
        return featured_artists
    
    def _calculate_quality_score(self, tracks: List[Dict], artist_info: Dict) -> float:
        """
        Calcule un score de qualité pour la découverte.
        
        Args:
            tracks: Liste des morceaux découverts
            artist_info: Informations de l'artiste
            
        Returns:
            Score de qualité entre 0 et 1
        """
        if not tracks:
            return 0.0
        
        score = 0.0
        
        # Score basé sur le nombre de morceaux (30%)
        track_count_score = min(len(tracks) / 100, 1.0)  # 100 morceaux = score parfait
        score += 0.3 * track_count_score
        
        # Score basé sur la complétude des données (40%)
        complete_tracks = 0
        for track in tracks:
            if (track.get('title') and 
                track.get('artist') and 
                track.get('url') and
                track.get('genius_id')):
                complete_tracks += 1
        
        completeness_score = complete_tracks / len(tracks)
        score += 0.4 * completeness_score
        
        # Score basé sur la diversité (30%)
        unique_titles = len(set(normalize_title(t.get('title', '')) for t in tracks))
        diversity_score = unique_titles / len(tracks)
        score += 0.3 * diversity_score
        
        return min(score, 1.0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de découverte"""
        return {
            **self.stats,
            'cache_hit_rate': self.stats['cache_hits'] / max(self.stats['api_calls'], 1)
        }
    
    def reset_stats(self):
        """Remet à zéro les statistiques"""
        self.stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'artists_discovered': 0,
            'tracks_discovered': 0,
            'errors': 0
        }
