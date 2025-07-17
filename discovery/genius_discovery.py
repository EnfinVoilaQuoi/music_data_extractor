# discovery/genius_discovery.py - Version complète corrigée
import logging
import traceback
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import time
import re
from urllib.parse import quote
from datetime import datetime, timezone

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
    Version corrigée avec gestion d'erreur ultra-robuste et logs détaillés
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration API Genius
        self.api_key = settings.genius_api_key
        if not self.api_key:
            raise APIError("Clé API Genius manquante - configurez GENIUS_API_KEY dans .env")
        
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
        
        # Patterns pour SIGNALER (pas filtrer) les battles et freestyles suspects
        self.warning_patterns = [
            # Patterns très spécifiques uniquement
            r'\brap[\s\-]*contenders?\s+(?:battle|vs|versus)\b',
            r'\brentre\s+dans\s+le\s+cercle\s+(?:battle|vs|versus)\b',
            r'\bgr[üu]nt\s+(?:battle|vs|versus|freestyle)\b',
            r'\bbattle\s+(?:rap|hip[\s\-]*hop)\s+(?:vs|versus)\b',
            r'\brap2france\s+(?:battle|vs|versus)\b',
            r'\bmusicast\s+(?:battle|freestyle)\b',
            r'\bdim\s+dak\s+freestyle\b',
            r'\b(?:eliminatoire|demi[\s\-]*finale|finale)\s+(?:battle|rap)\b',
            r'\btournoi\s+(?:de\s+)?rap\b'
        ]
        
        # Compiler les patterns pour performance
        self.compiled_warning_patterns = [re.compile(p, re.IGNORECASE) for p in self.warning_patterns]
        
        # Statistiques
        self.stats = {
            'api_calls': 0,
            'tracks_found': 0,
            'artists_found': 0,
            'battles_detected': 0
        }
        
        self.logger.info(f"✅ GeniusDiscovery initialisé avec clé API: {self.api_key[:8]}...")
    
    def _create_session(self) -> requests.Session:
        """Crée une session HTTP avec retry automatique"""
        session = requests.Session()
        
        # Configuration retry
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _safe_get(self, data: Any, key: str, default: Any = None) -> Any:
        """
        MÉTHODE CRUCIALE : Accès sécurisé aux données avec gestion d'erreurs
        Cette méthode résout le problème "No item with that key"
        """
        try:
            if isinstance(data, dict):
                return data.get(key, default)
            elif isinstance(data, list) and isinstance(key, int):
                return data[key] if 0 <= key < len(data) else default
            else:
                self.logger.warning(f"🔍 _safe_get: Type inattendu - data: {type(data)}, key: {key}")
                return default
        except Exception as e:
            self.logger.error(f"🔍 _safe_get ERROR: {e} - data: {type(data)}, key: {key}")
            return default
    
    def _is_battle_or_freestyle_suspect(self, title: str, artist_name: str = "", 
                                      featured_artists: List[str] = None) -> tuple[bool, str]:
        """
        Vérifie si un morceau est suspect (battle/freestyle) - ALERTE seulement
        
        Returns:
            (is_suspect, reason)
        """
        try:
            if not title:
                return False, ""
            
            # Créer le texte combiné pour l'analyse
            featured_artists = featured_artists or []
            combined_text = f"{title} {artist_name} {' '.join(featured_artists)}"
            
            for pattern in self.compiled_warning_patterns:
                if pattern.search(combined_text):
                    reason = f"Pattern détecté: {pattern.pattern}"
                    self.logger.debug(f"⚠️ Morceau SUSPECT: '{title}' - {reason}")
                    return True, reason
            
            return False, ""
            
        except Exception as e:
            self.logger.error(f"🔍 Erreur vérification battle: {e}")
            return False, f"Erreur vérification: {e}"
    
    def discover_artist_tracks(self, artist_name: str, max_tracks: int = 100) -> DiscoveryResult:
        """Découvre les morceaux d'un artiste avec DEBUG ultra-détaillé"""
        try:
            self.logger.info(f"🔍 DEBUG: Début découverte pour '{artist_name}' (max: {max_tracks})")
            
            # Étape 1: Rechercher l'artiste
            self.logger.info("🔍 DEBUG: Étape 1 - Recherche artiste...")
            artist_data = self._search_artist_debug(artist_name)
            
            if not artist_data:
                error_msg = f"Artiste '{artist_name}' non trouvé sur Genius"
                self.logger.error(f"🔍 DEBUG: {error_msg}")
                return DiscoveryResult(success=False, error=error_msg)
            
            artist_id = self._safe_get(artist_data, 'id')
            if not artist_id:
                error_msg = "ID artiste manquant dans la réponse"
                self.logger.error(f"🔍 DEBUG: {error_msg}")
                return DiscoveryResult(success=False, error=error_msg)
            
            self.logger.info(f"🔍 DEBUG: Artiste trouvé - ID: {artist_id}, Nom: {self._safe_get(artist_data, 'name', 'N/A')}")
            
            # Étape 2: Récupérer les morceaux
            self.logger.info("🔍 DEBUG: Étape 2 - Récupération morceaux...")
            songs = self._get_artist_songs_debug(artist_id, max_tracks)
            
            self.logger.info(f"🔍 DEBUG: {len(songs)} morceaux bruts récupérés")
            
            # Étape 3: Traiter les morceaux
            self.logger.info("🔍 DEBUG: Étape 3 - Traitement morceaux...")
            processed_tracks = []
            suspect_count = 0
            
            for i, song_data in enumerate(songs):
                try:
                    self.logger.debug(f"🔍 DEBUG: Traitement morceau {i+1}/{len(songs)}")
                    
                    # Extraction des données avec _safe_get
                    title = self._safe_get(song_data, 'title', 'Titre inconnu')
                    song_id = self._safe_get(song_data, 'id')
                    url = self._safe_get(song_data, 'url', '')
                    
                    # Extraction artiste principal
                    primary_artist = self._safe_get(song_data, 'primary_artist', {})
                    artist_name_found = self._safe_get(primary_artist, 'name', artist_name)
                    
                    # Extraction album
                    album = self._safe_get(song_data, 'album')
                    album_name = self._safe_get(album, 'name') if album else None
                    
                    # Extraction date
                    release_date_components = self._safe_get(song_data, 'release_date_components')
                    release_date = None
                    if release_date_components:
                        year = self._safe_get(release_date_components, 'year')
                        month = self._safe_get(release_date_components, 'month', 1)
                        day = self._safe_get(release_date_components, 'day', 1)
                        if year:
                            try:
                                release_date = datetime(year, month, day).isoformat()
                            except:
                                self.logger.debug(f"Date invalide: {year}-{month}-{day}")
                    
                    # Extraction artistes featuring
                    featured_artists = []
                    featured_artists_data = self._safe_get(song_data, 'featured_artists', [])
                    for featured in featured_artists_data:
                        featured_name = self._safe_get(featured, 'name')
                        if featured_name:
                            featured_artists.append(featured_name)
                    
                    # Vérification battle/freestyle (alerte seulement)
                    is_suspect, suspect_reason = self._is_battle_or_freestyle_suspect(
                        title, artist_name_found, featured_artists
                    )
                    
                    if is_suspect:
                        suspect_count += 1
                        self.stats['battles_detected'] += 1
                    
                    # Créer l'objet track
                    track_data = {
                        'title': title,
                        'artist_name': artist_name_found,
                        'genius_id': song_id,
                        'genius_url': url,
                        'album_name': album_name,
                        'release_date': release_date,
                        'featured_artists': featured_artists,
                        'battle_warning': is_suspect,
                        'battle_reason': suspect_reason if is_suspect else None,
                        'source': 'genius'
                    }
                    
                    processed_tracks.append(track_data)
                    self.logger.debug(f"✅ Track traité: {title}")
                    
                except Exception as e:
                    self.logger.error(f"❌ Erreur traitement morceau {i+1}: {e}")
                    continue
            
            # Statistiques finales
            self.stats['tracks_found'] += len(processed_tracks)
            
            self.logger.info(f"✅ DEBUG: Découverte terminée - {len(processed_tracks)} morceaux traités")
            if suspect_count > 0:
                self.logger.warning(f"⚠️ {suspect_count} morceaux suspects détectés (battles/freestyles possibles)")
            
            return DiscoveryResult(
                success=True,
                tracks=processed_tracks,
                total_found=len(processed_tracks),
                source="genius",
                quality_score=0.9 if len(processed_tracks) > 0 else 0.0
            )
            
        except Exception as e:
            error_msg = f"Erreur découverte Genius: {e}"
            self.logger.error(f"❌ {error_msg}")
            self.logger.error(f"🔍 DEBUG: Traceback:\n{traceback.format_exc()}")
            return DiscoveryResult(success=False, error=error_msg)
    
    def _search_artist_debug(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """Recherche un artiste avec logs debug ultra-détaillés"""
        try:
            if self.rate_limiter:
                self.rate_limiter.wait_if_needed()
            
            search_query = clean_artist_name(artist_name)
            self.logger.info(f"🔍 DEBUG: Recherche '{search_query}' (original: '{artist_name}')")
            
            # URL et paramètres
            url = f"{self.base_url}/search"
            params = {'q': search_query}
            
            self.logger.debug(f"🔍 DEBUG: URL: {url}, Params: {params}")
            
            # Requête API
            response = self.session.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            self.stats['api_calls'] += 1
            self.logger.debug(f"🔍 DEBUG: Status: {response.status_code}")
            
            # Parse JSON avec gestion d'erreur
            try:
                data = response.json()
            except Exception as json_error:
                self.logger.error(f"🔍 DEBUG: Erreur JSON: {json_error}")
                self.logger.error(f"🔍 DEBUG: Response text: {response.text[:200]}")
                raise APIError(f"Réponse JSON invalide: {json_error}")
            
            # Vérification structure réponse
            response_data = self._safe_get(data, 'response', {})
            hits = self._safe_get(response_data, 'hits', [])
            
            self.logger.info(f"🔍 DEBUG: {len(hits)} résultats trouvés")
            
            # Recherche de l'artiste exact
            clean_target = clean_artist_name(artist_name).lower()
            self.logger.debug(f"🔍 DEBUG: Recherche exacte pour: '{clean_target}'")
            
            for i, hit in enumerate(hits):
                try:
                    self.logger.debug(f"🔍 DEBUG: Analyse hit {i+1}/{len(hits)}")
                    
                    result = self._safe_get(hit, 'result', {})
                    primary_artist = self._safe_get(result, 'primary_artist', {})
                    
                    artist_name_found = self._safe_get(primary_artist, 'name', default='')
                    if artist_name_found:
                        clean_found = clean_artist_name(artist_name_found).lower()
                        self.logger.debug(f"🔍 DEBUG: Comparaison '{clean_found}' vs '{clean_target}'")
                        
                        if clean_found == clean_target:
                            self.logger.info(f"✅ Artiste trouvé: {artist_name_found}")
                            self.stats['artists_found'] += 1
                            return primary_artist
                    
                except Exception as e:
                    self.logger.error(f"🔍 DEBUG: Erreur traitement hit {i+1}: {e}")
                    continue
            
            self.logger.warning(f"🔍 DEBUG: Aucun artiste exact trouvé pour '{artist_name}'")
            return None
            
        except Exception as e:
            self.logger.error(f"🔍 DEBUG: Erreur recherche artiste: {e}")
            self.logger.error(f"🔍 DEBUG: Traceback:\n{traceback.format_exc()}")
            raise APIError(f"Erreur API Genius: {e}")
    
    def _get_artist_songs_debug(self, artist_id: int, max_tracks: int) -> List[Dict[str, Any]]:
        """Récupère les morceaux avec logs debug"""
        songs = []
        page = 1
        per_page = 50
        
        self.logger.info(f"🔍 DEBUG: Récupération morceaux pour artiste {artist_id}")
        
        while len(songs) < max_tracks:
            try:
                if self.rate_limiter:
                    self.rate_limiter.wait_if_needed()
                
                url = f"{self.base_url}/artists/{artist_id}/songs"
                params = {
                    'page': page,
                    'per_page': min(per_page, max_tracks - len(songs)),
                    'sort': 'popularity'
                }
                
                self.logger.debug(f"🔍 DEBUG: Page {page}, URL: {url}")
                
                response = self.session.get(url, headers=self.headers, params=params, timeout=30)
                response.raise_for_status()
                
                self.stats['api_calls'] += 1
                
                data = response.json()
                response_data = self._safe_get(data, 'response', default={})
                page_songs = self._safe_get(response_data, 'songs', default=[])
                
                if not page_songs:
                    self.logger.info(f"🔍 DEBUG: Pas de morceaux page {page}, arrêt")
                    break
                
                # Filtrer les morceaux de l'artiste principal
                artist_songs = []
                for song in page_songs:
                    primary_artist = self._safe_get(song, 'primary_artist', {})
                    song_artist_id = self._safe_get(primary_artist, 'id')
                    
                    if song_artist_id == artist_id:
                        artist_songs.append(song)
                
                songs.extend(artist_songs)
                self.logger.debug(f"🔍 DEBUG: Page {page}: {len(artist_songs)}/{len(page_songs)} morceaux de l'artiste")
                
                # Pagination
                next_page = self._safe_get(response_data, 'next_page')
                if not next_page or len(page_songs) < per_page:
                    self.logger.info(f"🔍 DEBUG: Fin pagination (next_page: {next_page})")
                    break
                
                page += 1
                
                # Protection contre boucle infinie
                if page > 20:
                    self.logger.warning("🔍 DEBUG: Protection pagination - arrêt à 20 pages")
                    break
                    
            except Exception as e:
                self.logger.error(f"🔍 DEBUG: Erreur page {page}: {e}")
                break
        
        self.logger.info(f"🔍 DEBUG: Total morceaux récupérés: {len(songs)}")
        return songs[:max_tracks]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'utilisation"""
        return self.stats.copy()
    
    def reset_stats(self):
        """Remet à zéro les statistiques"""
        self.stats = {
            'api_calls': 0,
            'tracks_found': 0,
            'artists_found': 0,
            'battles_detected': 0
        }