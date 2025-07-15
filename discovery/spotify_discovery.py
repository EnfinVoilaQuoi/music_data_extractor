# discovery/spotify_discovery.py
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import base64

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..core.exceptions import ExtractionError, RateLimitError, ValidationError
from ..core.cache import CacheManager
from ..core.rate_limiter import RateLimiter
from ..config.settings import settings
from ..models.entities import Artist, Album, Track
from ..models.enums import AlbumType, DataSource, ExtractionStatus
from ..utils.text_utils import clean_text, normalize_title, extract_featuring_artists


class SpotifyDiscovery:
    """
    Module de découverte pour Spotify.
    
    Responsabilités :
    - Découverte des albums d'un artiste
    - Récupération de la discographie complète
    - Organisation des tracks par albums/singles/compilations
    - Extraction des métadonnées de base (durée, année, etc.)
    """
    
    def __init__(self):
        self.client_id = settings.spotify_client_id
        self.client_secret = settings.spotify_client_secret
        
        if not self.client_id or not self.client_secret:
            raise ExtractionError("Identifiants Spotify manquants")
        
        # Configuration
        self.base_url = "https://api.spotify.com/v1"
        self.auth_url = "https://accounts.spotify.com/api/token"
        
        # Gestion des tokens
        self.access_token = None
        self.token_expires_at = None
        
        # Composants
        self.logger = logging.getLogger(f"{__name__}.SpotifyDiscovery")
        self.cache_manager = CacheManager()
        self.rate_limiter = RateLimiter(
            requests_per_period=settings.get('rate_limits.spotify.requests_per_minute', 100),
            period_seconds=60
        )
        
        # Session HTTP
        self.session = self._create_session()
        
        # Configuration spécifique
        self.config = {
            'include_singles': settings.get('albums.detect_singles', True),
            'include_compilations': settings.get('spotify.include_compilations', False),
            'include_appears_on': settings.get('spotify.include_appears_on', True),
            'market': settings.get('spotify.market', 'US'),  # Marché pour la disponibilité
            'limit_albums': settings.get('spotify.max_albums_per_artist', 50),
            'prefer_original_releases': settings.get('albums.prefer_spotify', True)
        }
        
        self.logger.info("SpotifyDiscovery initialisé")
    
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
    
    def _get_access_token(self) -> str:
        """Obtient ou renouvelle le token d'accès Spotify"""
        # Vérifier si le token actuel est encore valide
        if (self.access_token and self.token_expires_at and 
            datetime.now() < self.token_expires_at - timedelta(minutes=5)):
            return self.access_token
        
        # Demander un nouveau token
        auth_header = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {"grant_type": "client_credentials"}
        
        try:
            response = self.session.post(self.auth_url, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            self.logger.debug("Token Spotify renouvelé")
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            raise ExtractionError(f"Erreur lors de l'authentification Spotify: {e}")
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Effectue une requête à l'API Spotify"""
        self.rate_limiter.wait_if_needed()
        
        # S'assurer d'avoir un token valide
        token = self._get_access_token()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.get(url, headers=headers, params=params)
            
            if response.status_code == 429:
                # Rate limit atteint
                retry_after = int(response.headers.get('Retry-After', 60))
                raise RateLimitError(f"Rate limit Spotify, retry après {retry_after}s")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise ExtractionError(f"Erreur API Spotify: {e}")
    
    def discover_artist_albums(self, artist_name: str) -> Dict[str, Any]:
        """
        Découvre tous les albums d'un artiste.
        
        Args:
            artist_name: Nom de l'artiste
        
        Returns:
            Dict contenant la discographie organisée
        """
        cache_key = f"spotify_discovery_albums_{artist_name}"
        cached_result = self.cache_manager.get(cache_key)
        
        if cached_result:
            self.logger.debug(f"Cache hit pour albums de {artist_name}")
            return cached_result
        
        try:
            # 1. Rechercher l'artiste
            artist_data = self._search_artist(artist_name)
            if not artist_data:
                raise ExtractionError(f"Artiste '{artist_name}' non trouvé sur Spotify")
            
            artist_id = artist_data['id']
            
            # 2. Récupérer tous les albums
            all_albums = self._get_artist_albums(artist_id)
            
            # 3. Organiser par type
            organized_albums = self._organize_albums_by_type(all_albums)
            
            # 4. Enrichir avec les détails et tracks
            enriched_albums = self._enrich_albums_with_tracks(organized_albums)
            
            # 5. Construire le résultat final
            result = {
                'artist': artist_data,
                'discovery_date': datetime.now().isoformat(),
                'total_albums': len(all_albums),
                'albums_by_type': {
                    'studio_albums': enriched_albums.get('album', []),
                    'singles': enriched_albums.get('single', []),
                    'compilations': enriched_albums.get('compilation', []),
                    'appears_on': enriched_albums.get('appears_on', [])
                },
                'statistics': self._calculate_discovery_stats(enriched_albums),
                'metadata': {
                    'include_singles': self.config['include_singles'],
                    'include_compilations': self.config['include_compilations'],
                    'include_appears_on': self.config['include_appears_on'],
                    'market': self.config['market']
                }
            }
            
            # Mettre en cache
            self.cache_manager.set(cache_key, result, expire_days=1)  # Cache court pour la découverte
            
            self.logger.info(f"Découverte terminée pour {artist_name}: {result['total_albums']} albums trouvés")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la découverte pour {artist_name}: {e}")
            raise
    
    def _search_artist(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """Recherche un artiste sur Spotify"""
        params = {
            'q': f'artist:"{artist_name}"',
            'type': 'artist',
            'limit': 10
        }
        
        try:
            response = self._make_request('search', params)
            artists = response.get('artists', {}).get('items', [])
            
            if not artists:
                # Tentative avec recherche moins restrictive
                params['q'] = artist_name
                response = self._make_request('search', params)
                artists = response.get('artists', {}).get('items', [])
            
            if artists:
                # Trouver la meilleure correspondance
                best_match = self._find_best_artist_match(artists, artist_name)
                return best_match
            
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche d'artiste '{artist_name}': {e}")
            return None
    
    def _find_best_artist_match(self, artists: List[Dict[str, Any]], target_name: str) -> Dict[str, Any]:
        """Trouve la meilleure correspondance d'artiste"""
        target_normalized = normalize_title(target_name)
        
        best_match = None
        best_score = 0.0
        
        for artist in artists:
            artist_name = artist.get('name', '')
            artist_normalized = normalize_title(artist_name)
            
            # Score de similarité
            score = self._calculate_name_similarity(artist_normalized, target_normalized)
            
            # Bonus pour la popularité (artistes plus connus = plus fiables)
            popularity = artist.get('popularity', 0)
            score += (popularity / 100) * 0.1  # Bonus max de 0.1
            
            # Bonus pour les genres rap/hip-hop
            genres = artist.get('genres', [])
            if any(genre in ['hip hop', 'rap', 'hip-hop'] for genre in genres):
                score += 0.1
            
            if score > best_score:
                best_score = score
                best_match = artist
        
        return best_match
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calcule la similarité entre deux noms d'artistes"""
        if not name1 or not name2:
            return 0.0
        
        # Correspondance exacte
        if name1 == name2:
            return 1.0
        
        # Correspondance par mots
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _get_artist_albums(self, artist_id: str) -> List[Dict[str, Any]]:
        """Récupère tous les albums d'un artiste"""
        all_albums = []
        
        # Types d'albums à récupérer
        album_types = ['album']
        if self.config['include_singles']:
            album_types.append('single')
        if self.config['include_compilations']:
            album_types.append('compilation')
        if self.config['include_appears_on']:
            album_types.append('appears_on')
        
        for album_type in album_types:
            albums = self._get_albums_by_type(artist_id, album_type)
            all_albums.extend(albums)
        
        # Supprimer les doublons basés sur l'ID
        seen_ids = set()
        unique_albums = []
        for album in all_albums:
            if album['id'] not in seen_ids:
                seen_ids.add(album['id'])
                unique_albums.append(album)
        
        # Limiter le nombre d'albums
        if len(unique_albums) > self.config['limit_albums']:
            self.logger.warning(f"Limitation à {self.config['limit_albums']} albums (trouvés: {len(unique_albums)})")
            unique_albums = unique_albums[:self.config['limit_albums']]
        
        return unique_albums
    
    def _get_albums_by_type(self, artist_id: str, album_type: str) -> List[Dict[str, Any]]:
        """Récupère les albums d'un type spécifique"""
        albums = []
        offset = 0
        limit = 50
        
        while True:
            params = {
                'include_groups': album_type,
                'market': self.config['market'],
                'limit': limit,
                'offset': offset
            }
            
            try:
                response = self._make_request(f'artists/{artist_id}/albums', params)
                batch_albums = response.get('items', [])
                
                if not batch_albums:
                    break
                
                albums.extend(batch_albums)
                
                # Vérifier s'il y a plus de résultats
                if len(batch_albums) < limit:
                    break
                
                offset += limit
                
                # Limite de sécurité
                if offset >= 500:  # Max 500 albums par type
                    self.logger.warning(f"Limite de sécurité atteinte pour {album_type}")
                    break
                
            except Exception as e:
                self.logger.error(f"Erreur lors de la récupération des albums {album_type}: {e}")
                break
        
        return albums
    
    def _organize_albums_by_type(self, albums: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Organise les albums par type"""
        organized = {
            'album': [],
            'single': [],
            'compilation': [],
            'appears_on': []
        }
        
        for album in albums:
            album_type = album.get('album_type', 'album')
            if album_type in organized:
                organized[album_type].append(album)
            else:
                organized['album'].append(album)  # Par défaut dans albums
        
        # Trier chaque type par date de sortie (plus récent en premier)
        for album_type in organized:
            organized[album_type].sort(
                key=lambda x: x.get('release_date', '0000-01-01'),
                reverse=True
            )
        
        return organized
    
    def _enrich_albums_with_tracks(self, organized_albums: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
        """Enrichit les albums avec leurs tracks"""
        enriched = {}
        
        for album_type, albums in organized_albums.items():
            enriched[album_type] = []
            
            for album in albums:
                try:
                    # Récupérer les détails complets de l'album
                    detailed_album = self._get_album_details(album['id'])
                    
                    if detailed_album:
                        # Récupérer les tracks
                        tracks = self._get_album_tracks(album['id'])
                        detailed_album['tracks'] = tracks
                        detailed_album['total_tracks'] = len(tracks)
                        
                        # Calculer la durée totale
                        total_duration_ms = sum(track.get('duration_ms', 0) for track in tracks)
                        detailed_album['total_duration_ms'] = total_duration_ms
                        detailed_album['total_duration_formatted'] = self._format_duration(total_duration_ms)
                        
                        # Ajouter des métadonnées de découverte
                        detailed_album['discovery_metadata'] = {
                            'discovered_at': datetime.now().isoformat(),
                            'source': 'spotify_discovery',
                            'original_album_type': album.get('album_type'),
                            'market': self.config['market']
                        }
                        
                        enriched[album_type].append(detailed_album)
                    
                except Exception as e:
                    self.logger.warning(f"Erreur lors de l'enrichissement de l'album {album.get('name', 'Unknown')}: {e}")
                    # Ajouter l'album sans enrichissement
                    enriched[album_type].append(album)
        
        return enriched
    
    def _get_album_details(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les détails complets d'un album"""
        try:
            params = {'market': self.config['market']}
            response = self._make_request(f'albums/{album_id}', params)
            return response
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des détails de l'album {album_id}: {e}")
            return None
    
    def _get_album_tracks(self, album_id: str) -> List[Dict[str, Any]]:
        """Récupère toutes les tracks d'un album"""
        tracks = []
        offset = 0
        limit = 50
        
        while True:
            params = {
                'market': self.config['market'],
                'limit': limit,
                'offset': offset
            }
            
            try:
                response = self._make_request(f'albums/{album_id}/tracks', params)
                batch_tracks = response.get('items', [])
                
                if not batch_tracks:
                    break
                
                # Enrichir chaque track avec des métadonnées
                for track in batch_tracks:
                    enriched_track = self._enrich_track_data(track)
                    tracks.append(enriched_track)
                
                if len(batch_tracks) < limit:
                    break
                
                offset += limit
                
            except Exception as e:
                self.logger.error(f"Erreur lors de la récupération des tracks de l'album {album_id}: {e}")
                break
        
        return tracks
    
    def _enrich_track_data(self, track: Dict[str, Any]) -> Dict[str, Any]:
        """Enrichit les données d'un track"""
        enriched = track.copy()
        
        # Artistes principaux et featuring
        artists = track.get('artists', [])
        if artists:
            enriched['primary_artist'] = artists[0]['name']
            enriched['all_artists'] = [artist['name'] for artist in artists]
            
            # Détecter les featuring
            featuring_artists = extract_featuring_artists(track.get('name', ''))
            if featuring_artists:
                enriched['featuring_artists'] = featuring_artists
        
        # Durée formatée
        duration_ms = track.get('duration_ms', 0)
        enriched['duration_formatted'] = self._format_duration(duration_ms)
        enriched['duration_seconds'] = duration_ms // 1000 if duration_ms else 0
        
        # Analyse du titre pour extraire des infos
        title_analysis = self._analyze_track_title(track.get('name', ''))
        enriched.update(title_analysis)
        
        # URLs et métadonnées
        enriched['spotify_url'] = track.get('external_urls', {}).get('spotify', '')
        enriched['preview_url'] = track.get('preview_url', '')
        
        # Numéro de track
        enriched['track_number'] = track.get('track_number', 0)
        enriched['disc_number'] = track.get('disc_number', 1)
        
        # Disponibilité
        enriched['is_playable'] = track.get('is_playable', True)
        enriched['explicit'] = track.get('explicit', False)
        
        return enriched
    
    def _analyze_track_title(self, title: str) -> Dict[str, Any]:
        """Analyse le titre d'un track pour extraire des informations"""
        analysis = {}
        
        # Détecter les remix, versions spéciales, etc.
        title_lower = title.lower()
        
        # Types de versions
        if any(word in title_lower for word in ['remix', 'rmx', 'rework']):
            analysis['is_remix'] = True
            analysis['version_type'] = 'remix'
        elif any(word in title_lower for word in ['acoustic', 'unplugged']):
            analysis['is_acoustic'] = True
            analysis['version_type'] = 'acoustic'
        elif any(word in title_lower for word in ['live', 'concert']):
            analysis['is_live'] = True
            analysis['version_type'] = 'live'
        elif any(word in title_lower for word in ['instrumental', 'inst']):
            analysis['is_instrumental'] = True
            analysis['version_type'] = 'instrumental'
        elif any(word in title_lower for word in ['extended', 'extended mix', 'ext']):
            analysis['is_extended'] = True
            analysis['version_type'] = 'extended'
        else:
            analysis['version_type'] = 'original'
        
        # Détecter les featuring dans le titre
        featuring_match = re.search(r'\(feat\.?\s+([^)]+)\)', title, re.IGNORECASE)
        if featuring_match:
            analysis['featuring_in_title'] = featuring_match.group(1)
        
        # Nettoyer le titre de base
        clean_title = re.sub(r'\s*\([^)]*\)\s*', '', title)  # Supprimer parenthèses
        clean_title = re.sub(r'\s*\[[^\]]*\]\s*', '', clean_title)  # Supprimer crochets
        analysis['clean_title'] = clean_title.strip()
        
        return analysis
    
    def _calculate_discovery_stats(self, enriched_albums: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Calcule les statistiques de découverte"""
        stats = {
            'total_albums': 0,
            'total_tracks': 0,
            'total_duration_ms': 0,
            'albums_by_type': {},
            'years_span': {},
            'earliest_release': None,
            'latest_release': None,
            'average_tracks_per_album': 0.0,
            'average_album_duration_minutes': 0.0
        }
        
        all_albums = []
        for album_type, albums in enriched_albums.items():
            stats['albums_by_type'][album_type] = len(albums)
            stats['total_albums'] += len(albums)
            all_albums.extend(albums)
        
        if not all_albums:
            return stats
        
        # Calculs détaillés
        total_tracks = 0
        total_duration = 0
        release_years = []
        
        for album in all_albums:
            # Tracks
            album_tracks = len(album.get('tracks', []))
            total_tracks += album_tracks
            
            # Durée
            album_duration = album.get('total_duration_ms', 0)
            total_duration += album_duration
            
            # Années
            release_date = album.get('release_date', '')
            if release_date and len(release_date) >= 4:
                try:
                    year = int(release_date[:4])
                    release_years.append(year)
                except ValueError:
                    pass
        
        stats['total_tracks'] = total_tracks
        stats['total_duration_ms'] = total_duration
        
        # Moyennes
        if stats['total_albums'] > 0:
            stats['average_tracks_per_album'] = total_tracks / stats['total_albums']
            stats['average_album_duration_minutes'] = (total_duration / 1000 / 60) / stats['total_albums']
        
        # Années
        if release_years:
            stats['earliest_release'] = min(release_years)
            stats['latest_release'] = max(release_years)
            stats['career_span_years'] = max(release_years) - min(release_years)
            
            # Distribution par décennie
            decade_counts = {}
            for year in release_years:
                decade = (year // 10) * 10
                decade_counts[f"{decade}s"] = decade_counts.get(f"{decade}s", 0) + 1
            stats['albums_by_decade'] = decade_counts
        
        # Durée totale formatée
        stats['total_duration_formatted'] = self._format_duration(total_duration)
        
        return stats
    
    def _format_duration(self, duration_ms: int) -> str:
        """Formate une durée en millisecondes vers HH:MM:SS ou MM:SS"""
        if not duration_ms:
            return "0:00"
        
        total_seconds = duration_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    def get_artist_top_tracks(self, artist_id: str, market: str = 'US') -> List[Dict[str, Any]]:
        """Récupère les top tracks d'un artiste"""
        try:
            params = {'market': market}
            response = self._make_request(f'artists/{artist_id}/top-tracks', params)
            
            tracks = response.get('tracks', [])
            
            # Enrichir les tracks
            enriched_tracks = []
            for track in tracks:
                enriched_track = self._enrich_track_data(track)
                enriched_track['popularity'] = track.get('popularity', 0)
                enriched_tracks.append(enriched_track)
            
            return enriched_tracks
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des top tracks pour {artist_id}: {e}")
            return []
    
    def search_track_by_name(self, artist_name: str, track_name: str) -> Optional[Dict[str, Any]]:
        """Recherche un track spécifique par nom d'artiste et titre"""
        params = {
            'q': f'artist:"{artist_name}" track:"{track_name}"',
            'type': 'track',
            'limit': 10,
            'market': self.config['market']
        }
        
        try:
            response = self._make_request('search', params)
            tracks = response.get('tracks', {}).get('items', [])
            
            if not tracks:
                # Recherche moins restrictive
                params['q'] = f'"{artist_name}" "{track_name}"'
                response = self._make_request('search', params)
                tracks = response.get('tracks', {}).get('items', [])
            
            if tracks:
                # Trouver la meilleure correspondance
                best_match = self._find_best_track_match(tracks, artist_name, track_name)
                if best_match:
                    return self._enrich_track_data(best_match)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche du track '{track_name}' par {artist_name}: {e}")
            return None
    
    def _find_best_track_match(self, tracks: List[Dict[str, Any]], target_artist: str, target_track: str) -> Optional[Dict[str, Any]]:
        """Trouve la meilleure correspondance de track"""
        target_artist_norm = normalize_title(target_artist)
        target_track_norm = normalize_title(target_track)
        
        best_match = None
        best_score = 0.0
        
        for track in tracks:
            # Score basé sur l'artiste
            artists = track.get('artists', [])
            artist_score = 0.0
            for artist in artists:
                artist_name_norm = normalize_title(artist['name'])
                similarity = self._calculate_name_similarity(artist_name_norm, target_artist_norm)
                artist_score = max(artist_score, similarity)
            
            # Score basé sur le titre
            track_name_norm = normalize_title(track.get('name', ''))
            track_score = self._calculate_name_similarity(track_name_norm, target_track_norm)
            
            # Score total (artiste 40%, titre 60%)
            total_score = (artist_score * 0.4) + (track_score * 0.6)
            
            # Bonus pour la popularité
            popularity = track.get('popularity', 0)
            total_score += (popularity / 100) * 0.1
            
            if total_score > best_score:
                best_score = total_score
                best_match = track
        
        # Retourner seulement si le score est suffisant
        return best_match if best_score >= 0.6 else None
    
    def get_album_by_id(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Récupère un album par son ID Spotify"""
        try:
            album = self._get_album_details(album_id)
            if album:
                tracks = self._get_album_tracks(album_id)
                album['tracks'] = tracks
                album['total_tracks'] = len(tracks)
                
                # Calculer la durée totale
                total_duration_ms = sum(track.get('duration_ms', 0) for track in tracks)
                album['total_duration_ms'] = total_duration_ms
                album['total_duration_formatted'] = self._format_duration(total_duration_ms)
                
                return album
            return None
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de l'album {album_id}: {e}")
            return None