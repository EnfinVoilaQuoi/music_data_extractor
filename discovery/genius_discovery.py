# discovery/genius_discovery.py - Version DEBUG avec correction timezone
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
    Version DEBUG avec gestion d'erreur ultra-robuste et logs détaillés
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
            r'\btournoi\s+(?:rap|battle)\b',
        ]
        
        # Compiler les patterns pour performance
        self.compiled_warning_patterns = [
            re.compile(pattern, re.IGNORECASE | re.UNICODE)
            for pattern in self.warning_patterns
        ]
        
        # Statistiques
        self.stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'artists_found': 0,
            'tracks_discovered': 0,
            'tracks_flagged': 0,
            'errors': 0
        }
        
        self.logger.info("🔍 GeniusDiscovery DEBUG initialisé - logs détaillés activés")
    
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
    
    def _safe_get(self, data: Dict[str, Any], *keys, default=None):
        """Accès sécurisé aux données imbriquées avec logs debug"""
        try:
            current = data
            path = []
            
            for key in keys:
                path.append(str(key))
                if not isinstance(current, dict):
                    self.logger.debug(f"🔍 Accès échec: {' -> '.join(path[:-1])} n'est pas un dict, type: {type(current)}")
                    return default
                
                if key not in current:
                    self.logger.debug(f"🔍 Clé manquante: {' -> '.join(path)}")
                    return default
                
                current = current[key]
            
            self.logger.debug(f"🔍 Accès réussi: {' -> '.join(path)} = {str(current)[:100]}")
            return current
            
        except Exception as e:
            self.logger.error(f"🔍 Erreur accès données: {' -> '.join(path)} - {e}")
            return default
    
    def _check_battle_warning(self, title: str, artist_name: str = "", album_name: str = "") -> tuple[bool, str]:
        """Vérifie si un morceau est potentiellement un battle/freestyle SANS le filtrer"""
        try:
            combined_text = f"{title} {artist_name} {album_name}".lower()
            
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
                    
                    # Traiter les données
                    track_data = self._process_song_data_debug(song_data, artist_name)
                    
                    # Vérifier si suspect (sans filtrer)
                    is_suspect, warning_reason = self._check_battle_warning(
                        track_data.get('title', ''),
                        track_data.get('artist_name', ''),
                        track_data.get('album_name', '')
                    )
                    
                    # Ajouter métadonnées d'avertissement
                    track_data['battle_warning'] = is_suspect
                    track_data['warning_reason'] = warning_reason if is_suspect else None
                    
                    if is_suspect:
                        suspect_count += 1
                        self.logger.info(f"⚠️ Morceau SUSPECT conservé: '{track_data.get('title')}' - {warning_reason}")
                    
                    processed_tracks.append(track_data)
                    
                except Exception as e:
                    self.logger.error(f"🔍 DEBUG: Erreur traitement morceau {i+1}: {e}")
                    self.logger.error(f"🔍 DEBUG: Données morceau: {str(song_data)[:200]}...")
                    continue
            
            self.stats['tracks_discovered'] += len(processed_tracks)
            self.stats['tracks_flagged'] = suspect_count
            
            self.logger.info(f"🔍 DEBUG: Terminé - {len(processed_tracks)} morceaux traités ({suspect_count} flaggés)")
            
            return DiscoveryResult(
                success=True,
                tracks=processed_tracks,
                total_found=len(processed_tracks),
                source="genius"
            )
            
        except Exception as e:
            self.stats['errors'] += 1
            error_msg = f"Erreur découverte pour {artist_name}: {e}"
            self.logger.error(f"🔍 DEBUG: {error_msg}")
            self.logger.error(f"🔍 DEBUG: Traceback complet:\n{traceback.format_exc()}")
            
            return DiscoveryResult(
                success=False,
                error=str(e)  # Juste l'erreur, pas le préfixe
            )
    
    def _search_artist_debug(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """Recherche un artiste avec logs debug ultra-détaillés"""
        try:
            self.logger.info(f"🔍 DEBUG: Recherche API '{artist_name}'")
            
            # Rate limiting
            if self.rate_limiter:
                self.rate_limiter.wait_if_needed()
            
            url = f"{self.base_url}/search"
            params = {'q': artist_name}
            
            self.logger.debug(f"🔍 DEBUG: URL: {url}, Params: {params}")
            
            response = self.session.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            
            self.stats['api_calls'] += 1
            self.logger.debug(f"🔍 DEBUG: Réponse HTTP {response.status_code}")
            
            # Parser la réponse JSON
            try:
                data = response.json()
                self.logger.debug(f"🔍 DEBUG: JSON parsé, clés racine: {list(data.keys())}")
            except Exception as e:
                raise APIError(f"Erreur parsing JSON: {e}")
            
            # Accès sécurisé aux données
            response_data = self._safe_get(data, 'response', default={})
            if not response_data:
                self.logger.warning("🔍 DEBUG: Pas de clé 'response' dans la réponse")
                return None
            
            hits = self._safe_get(response_data, 'hits', default=[])
            if not hits:
                self.logger.warning("🔍 DEBUG: Pas de 'hits' dans response")
                return None
            
            self.logger.info(f"🔍 DEBUG: {len(hits)} résultats trouvés")
            
            # Chercher l'artiste exact
            clean_target = clean_artist_name(artist_name).lower()
            self.logger.debug(f"🔍 DEBUG: Recherche de '{clean_target}'")
            
            for i, hit in enumerate(hits):
                try:
                    self.logger.debug(f"🔍 DEBUG: Examen hit {i+1}")
                    
                    result = self._safe_get(hit, 'result', default={})
                    if not result:
                        self.logger.debug(f"🔍 DEBUG: Hit {i+1} sans 'result'")
                        continue
                    
                    primary_artist = self._safe_get(result, 'primary_artist', default={})
                    if not primary_artist:
                        self.logger.debug(f"🔍 DEBUG: Hit {i+1} sans 'primary_artist'")
                        continue
                    
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
                    self.logger.info(f"🔍 DEBUG: Aucun morceau page {page}")
                    break
                
                songs.extend(page_songs)
                self.logger.info(f"🔍 DEBUG: Page {page}: +{len(page_songs)} morceaux (total: {len(songs)})")
                
                page += 1
                time.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"🔍 DEBUG: Erreur page {page}: {e}")
                break
        
        self.logger.info(f"🔍 DEBUG: Total récupéré: {len(songs)} morceaux")
        return songs
    
    def _process_song_data_debug(self, song_data: Dict[str, Any], artist_name: str) -> Dict[str, Any]:
        """Traite les données d'un morceau avec logs debug"""
        try:
            self.logger.debug(f"🔍 DEBUG: Traitement morceau, clés: {list(song_data.keys())}")
            
            # Extractions sécurisées
            title = self._safe_get(song_data, 'title', default='').strip()
            genius_id = self._safe_get(song_data, 'id')
            genius_url = self._safe_get(song_data, 'url', default='')
            
            primary_artist = self._safe_get(song_data, 'primary_artist', default={})
            album = self._safe_get(song_data, 'album')
            
            # Featured artists
            featured_artists = []
            featured_list = self._safe_get(song_data, 'featured_artists', default=[])
            if isinstance(featured_list, list):
                for fa in featured_list:
                    if isinstance(fa, dict):
                        fa_name = self._safe_get(fa, 'name')
                        if fa_name:
                            featured_artists.append(fa_name)
            
            # Album name
            album_name = ''
            if isinstance(album, dict):
                album_name = self._safe_get(album, 'name', default='')
            
            # Stats
            stats = self._safe_get(song_data, 'stats', default={})
            page_views = None
            hot = False
            if isinstance(stats, dict):
                page_views = self._safe_get(stats, 'pageviews')
                hot = self._safe_get(stats, 'hot', default=False)
            
            track_data = {
                'title': title,
                'artist_name': artist_name,
                'genius_id': genius_id,
                'genius_url': genius_url,
                'release_date': self._safe_get(song_data, 'release_date_for_display'),
                'album_name': album_name,
                'featured_artists': featured_artists,
                'primary_artist_id': self._safe_get(primary_artist, 'id') if isinstance(primary_artist, dict) else None,
                'primary_artist_name': self._safe_get(primary_artist, 'name', default='') if isinstance(primary_artist, dict) else '',
                'page_views': page_views,
                'hot': hot,
                'song_art_image_url': self._safe_get(song_data, 'song_art_image_url', default=''),
                'header_image_url': self._safe_get(song_data, 'header_image_url', default=''),
                'battle_warning': False,
                'warning_reason': None,
            }
            
            self.logger.debug(f"🔍 DEBUG: Morceau traité: '{title}'")
            return track_data
            
        except Exception as e:
            self.logger.error(f"🔍 DEBUG: Erreur traitement morceau: {e}")
            self.logger.error(f"🔍 DEBUG: Données: {str(song_data)[:300]}")
            
            # Retour minimal pour continuer
            return {
                'title': self._safe_get(song_data, 'title', default='Titre inconnu'),
                'artist_name': artist_name,
                'genius_id': self._safe_get(song_data, 'id'),
                'genius_url': self._safe_get(song_data, 'url', default=''),
                'featured_artists': [],
                'album_name': '',
                'release_date': None,
                'primary_artist_id': None,
                'primary_artist_name': '',
                'page_views': None,
                'hot': False,
                'song_art_image_url': '',
                'header_image_url': '',
                'battle_warning': False,
                'warning_reason': None,
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques"""
        return self.stats.copy()
    
    def reset_stats(self):
        """Remet à zéro les statistiques"""
        self.stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'artists_found': 0,
            'tracks_discovered': 0,
            'tracks_flagged': 0,
            'errors': 0
        }