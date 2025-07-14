# extractors/spotify_extractor.py
import logging
import base64
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base_extractor import BaseExtractor, ExtractionResult, ExtractorConfig
from ..models.enums import ExtractorType, DataSource
from ..core.exceptions import APIError, APIRateLimitError, APIAuthenticationError
from ..config.settings import settings
from ..utils.text_utils import clean_artist_name, normalize_title, extract_year_from_date

class SpotifyExtractor(BaseExtractor):
    """
    Extracteur spécialisé pour l'API Spotify.
    
    Responsabilités :
    - Extraction des métadonnées audio (BPM, key, danceability, etc.)
    - Récupération des informations d'albums
    - Recherche de morceaux et artistes
    - Gestion de l'authentification OAuth2
    """
    
    def __init__(self, config: Optional[ExtractorConfig] = None):
        super().__init__(ExtractorType.SPOTIFY, config)
        
        # Configuration API Spotify
        self.client_id = settings.spotify_client_id
        self.client_secret = settings.spotify_client_secret
        
        if not self.client_id or not self.client_secret:
            raise APIAuthenticationError("spotify", "SPOTIFY_CLIENT_ID et SPOTIFY_CLIENT_SECRET")
        
        self.base_url = "https://api.spotify.com/v1"
        self.auth_url = "https://accounts.spotify.com/api/token"
        
        # Token d'accès et gestion
        self.access_token = None
        self.token_expires_at = None
        
        # Session HTTP
        self.session = self._create_session()
        
        # Authentification initiale
        self._authenticate()
        
        self.logger.info("SpotifyExtractor initialisé")
    
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
    
    def _authenticate(self):
        """Authentifie auprès de l'API Spotify (Client Credentials Flow)"""
        try:
            # Encodage des credentials
            credentials = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode()
            ).decode()
            
            headers = {
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {"grant_type": "client_credentials"}
            
            response = self.session.post(
                self.auth_url,
                headers=headers,
                data=data,
                timeout=self.config.timeout
            )
            
            if response.status_code == 401:
                raise APIAuthenticationError("spotify", "client_id/client_secret invalides")
            
            response.raise_for_status()
            auth_data = response.json()
            
            self.access_token = auth_data["access_token"]
            expires_in = auth_data.get("expires_in", 3600)  # Par défaut 1h
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)  # Marge de 60s
            
            # Mettre à jour les headers de session
            self.session.headers.update({
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            })
            
            self.logger.info("Authentification Spotify réussie")
            
        except requests.exceptions.RequestException as e:
            raise APIError(f"Erreur d'authentification Spotify: {e}")
    
    def _ensure_authenticated(self):
        """Vérifie et renouvelle le token si nécessaire"""
        if not self.access_token or datetime.now() >= self.token_expires_at:
            self.logger.info("Renouvellement du token Spotify")
            self._authenticate()
    
    def extract_track_info(self, track_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations complètes d'un morceau depuis Spotify.
        
        Args:
            track_id: ID Spotify du morceau
            **kwargs: Options additionnelles
                - include_audio_features: bool - Inclure les features audio
                - include_audio_analysis: bool - Inclure l'analyse audio détaillée
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        cache_key = self.get_cache_key("extract_track_info", track_id, **kwargs)
        
        def _extract():
            try:
                self._ensure_authenticated()
                
                # Extraction des infos de base
                track_data = self._get_track_basic_info(track_id)
                if not track_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Morceau {track_id} non trouvé sur Spotify",
                        source=self.extractor_type.value
                    )
                
                combined_data = track_data.copy()
                
                # Audio features si demandées
                if kwargs.get('include_audio_features', True):
                    audio_features = self._get_audio_features(track_id)
                    if audio_features:
                        combined_data['audio_features'] = audio_features
                
                # Audio analysis si demandée
                if kwargs.get('include_audio_analysis', False):
                    audio_analysis = self._get_audio_analysis(track_id)
                    if audio_analysis:
                        combined_data['audio_analysis'] = audio_analysis
                
                # Traitement et nettoyage
                processed_data = self._process_track_data(combined_data)
                
                # Validation
                is_valid, errors = self.validate_track_data(processed_data)
                if not is_valid:
                    self.logger.warning(f"Données invalides pour {track_id}: {errors}")
                
                # Calcul du score de qualité
                quality_score = self.calculate_quality_score(processed_data)
                
                return ExtractionResult(
                    success=True,
                    data=processed_data,
                    source=self.extractor_type.value,
                    quality_score=quality_score
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def extract_album_info(self, album_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations d'un album depuis Spotify.
        
        Args:
            album_id: ID Spotify de l'album
            **kwargs: Options additionnelles
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        cache_key = self.get_cache_key("extract_album_info", album_id, **kwargs)
        
        def _extract():
            try:
                self._ensure_authenticated()
                
                # Extraction des infos d'album
                album_data = self._get_album_info(album_id)
                if not album_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Album {album_id} non trouvé sur Spotify",
                        source=self.extractor_type.value
                    )
                
                # Traitement des données
                processed_data = self._process_album_data(album_data)
                
                # Calcul du score de qualité
                quality_score = self._calculate_album_quality_score(processed_data)
                
                return ExtractionResult(
                    success=True,
                    data=processed_data,
                    source=self.extractor_type.value,
                    quality_score=quality_score
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def extract_artist_info(self, artist_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations d'un artiste depuis Spotify.
        
        Args:
            artist_id: ID Spotify de l'artiste
            **kwargs: Options additionnelles
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        cache_key = self.get_cache_key("extract_artist_info", artist_id, **kwargs)
        
        def _extract():
            try:
                self._ensure_authenticated()
                
                # Extraction des infos d'artiste
                artist_data = self._get_artist_info(artist_id)
                if not artist_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Artiste {artist_id} non trouvé sur Spotify",
                        source=self.extractor_type.value
                    )
                
                # Traitement des données
                processed_data = self._process_artist_data(artist_data)
                
                # Calcul du score de qualité
                quality_score = self._calculate_artist_quality_score(processed_data)
                
                return ExtractionResult(
                    success=True,
                    data=processed_data,
                    source=self.extractor_type.value,
                    quality_score=quality_score
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def search_tracks(self, query: str, limit: int = 50, **kwargs) -> ExtractionResult:
        """
        Recherche des morceaux sur Spotify.
        
        Args:
            query: Requête de recherche
            limit: Nombre maximum de résultats
            **kwargs: Options additionnelles
                - artist: str - Filtrer par artiste
                - album: str - Filtrer par album
                - year: int - Filtrer par année
        
        Returns:
            ExtractionResult: Résultat de la recherche
        """
        cache_key = self.get_cache_key("search_tracks", query, limit, **kwargs)
        
        def _extract():
            try:
                self._ensure_authenticated()
                
                # Construction de la requête
                search_query = self._build_search_query(query, **kwargs)
                
                # Recherche via API
                search_results = self._search_spotify(search_query, 'track', limit)
                
                if not search_results:
                    return ExtractionResult(
                        success=False,
                        error=f"Aucun résultat pour la requête: {query}",
                        source=self.extractor_type.value
                    )
                
                # Traitement des résultats
                processed_results = self._process_search_results(search_results)
                
                return ExtractionResult(
                    success=True,
                    data={'results': processed_results, 'total': len(processed_results)},
                    source=self.extractor_type.value,
                    quality_score=0.8  # Score fixe pour les recherches
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def _get_track_basic_info(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations de base d'un morceau"""
        try:
            self.rate_limiter.wait_if_needed('spotify')
            
            response = self.session.get(
                f"{self.base_url}/tracks/{track_id}",
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise APIRateLimitError("spotify")
            elif response.status_code == 404:
                return None
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur API lors de la récupération du morceau {track_id}: {e}")
            return None
    
    def _get_audio_features(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les features audio d'un morceau"""
        try:
            self.rate_limiter.wait_if_needed('spotify')
            
            response = self.session.get(
                f"{self.base_url}/audio-features/{track_id}",
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise APIRateLimitError("spotify")
            elif response.status_code == 404:
                return None
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Erreur lors de la récupération des audio features pour {track_id}: {e}")
            return None
    
    def _get_audio_analysis(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Récupère l'analyse audio détaillée d'un morceau"""
        try:
            self.rate_limiter.wait_if_needed('spotify')
            
            response = self.session.get(
                f"{self.base_url}/audio-analysis/{track_id}",
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise APIRateLimitError("spotify")
            elif response.status_code == 404:
                return None
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Erreur lors de la récupération de l'audio analysis pour {track_id}: {e}")
            return None
    
    def _get_album_info(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations d'un album"""
        try:
            self.rate_limiter.wait_if_needed('spotify')
            
            response = self.session.get(
                f"{self.base_url}/albums/{album_id}",
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise APIRateLimitError("spotify")
            elif response.status_code == 404:
                return None
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur API lors de la récupération de l'album {album_id}: {e}")
            return None
    
    def _get_artist_info(self, artist_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations d'un artiste"""
        try:
            self.rate_limiter.wait_if_needed('spotify')
            
            response = self.session.get(
                f"{self.base_url}/artists/{artist_id}",
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise APIRateLimitError("spotify")
            elif response.status_code == 404:
                return None
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur API lors de la récupération de l'artiste {artist_id}: {e}")
            return None
    
    def _search_spotify(self, query: str, search_type: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        """Effectue une recherche sur Spotify"""
        try:
            self.rate_limiter.wait_if_needed('spotify')
            
            params = {
                'q': query,
                'type': search_type,
                'limit': min(limit, 50),  # Spotify limite à 50 par requête
                'market': 'US'  # Marché pour éviter les restrictions géographiques
            }
            
            response = self.session.get(
                f"{self.base_url}/search",
                params=params,
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise APIRateLimitError("spotify")
            
            response.raise_for_status()
            data = response.json()
            
            # Extraire les résultats selon le type
            if search_type == 'track':
                return data.get('tracks', {}).get('items', [])
            elif search_type == 'album':
                return data.get('albums', {}).get('items', [])
            elif search_type == 'artist':
                return data.get('artists', {}).get('items', [])
            
            return []
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur API lors de la recherche '{query}': {e}")
            return None
    
    def _build_search_query(self, base_query: str, **filters) -> str:
        """Construit une requête de recherche Spotify avec filtres"""
        query_parts = [base_query]
        
        # Ajouter les filtres
        if filters.get('artist'):
            query_parts.append(f'artist:"{filters["artist"]}"')
        if filters.get('album'):
            query_parts.append(f'album:"{filters["album"]}"')
        if filters.get('year'):
            query_parts.append(f'year:{filters["year"]}')
        if filters.get('genre'):
            query_parts.append(f'genre:"{filters["genre"]}"')
        
        return ' '.join(query_parts)
    
    def _process_track_data(self, track_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et nettoie les données d'un morceau"""
        processed = {}
        
        # Informations de base
        processed.update({
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
            'is_local': track_data.get('is_local', False)
        })
        
        # Artistes
        artists = track_data.get('artists', [])
        if artists:
            processed['artist'] = artists[0].get('name')
            processed['artist_id'] = artists[0].get('id')
            processed['all_artists'] = [artist.get('name') for artist in artists]
            processed['artist_ids'] = [artist.get('id') for artist in artists]
            
            # Features (artistes supplémentaires)
            if len(artists) > 1:
                processed['featuring_artists'] = [artist.get('name') for artist in artists[1:]]
        
        # Album
        album = track_data.get('album', {})
        if album:
            processed['album'] = {
                'id': album.get('id'),
                'name': album.get('name'),
                'album_type': album.get('album_type'),
                'release_date': album.get('release_date'),
                'release_date_precision': album.get('release_date_precision'),
                'total_tracks': album.get('total_tracks'),
                'images': album.get('images', []),
                'external_urls': album.get('external_urls', {})
            }
            
            # Extraire l'année de sortie
            release_date = album.get('release_date')
            if release_date:
                processed['release_year'] = extract_year_from_date(release_date)
        
        # Audio features (si disponibles)
        audio_features = track_data.get('audio_features', {})
        if audio_features and audio_features.get('id'):  # Vérifier que ce ne sont pas des données vides
            processed['audio_features'] = {
                'acousticness': audio_features.get('acousticness'),
                'danceability': audio_features.get('danceability'),
                'energy': audio_features.get('energy'),
                'instrumentalness': audio_features.get('instrumentalness'),
                'liveness': audio_features.get('liveness'),
                'loudness': audio_features.get('loudness'),
                'speechiness': audio_features.get('speechiness'),
                'valence': audio_features.get('valence'),
                'tempo': audio_features.get('tempo'),  # BPM
                'time_signature': audio_features.get('time_signature'),
                'key': self._convert_spotify_key(audio_features.get('key')),
                'mode': audio_features.get('mode')  # 0 = minor, 1 = major
            }
            
            # Mapping direct pour certains champs
            if audio_features.get('tempo'):
                processed['bpm'] = round(audio_features['tempo'])
            if audio_features.get('key') is not None:
                processed['key'] = self._convert_spotify_key(audio_features['key'])
        
        # Données brutes pour debug
        processed['raw_data'] = {
            'spotify': track_data
        }
        
        # Métadonnées d'extraction
        processed['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'extractor': self.extractor_type.value,
            'source': DataSource.SPOTIFY.value
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
            'images': album_data.get('images', []),
            'external_urls': album_data.get('external_urls', {}),
            'copyrights': album_data.get('copyrights', []),
            'label': album_data.get('label')
        }
        
        # Artistes
        artists = album_data.get('artists', [])
        if artists:
            processed['artist'] = artists[0].get('name')
            processed['artist_id'] = artists[0].get('id')
            processed['all_artists'] = [artist.get('name') for artist in artists]
        
        # Extraire l'année
        if album_data.get('release_date'):
            processed['release_year'] = extract_year_from_date(album_data['release_date'])
        
        # URL de la pochette (prendre la plus grande image disponible)
        images = album_data.get('images', [])
        if images:
            # Trier par taille (hauteur * largeur) et prendre la plus grande
            sorted_images = sorted(images, key=lambda x: (x.get('height', 0) * x.get('width', 0)), reverse=True)
            processed['cover_url'] = sorted_images[0].get('url')
        
        # Tracks (si incluses)
        tracks = album_data.get('tracks', {}).get('items', [])
        if tracks:
            processed['tracks'] = [
                {
                    'id': track.get('id'),
                    'name': track.get('name'),
                    'track_number': track.get('track_number'),
                    'disc_number': track.get('disc_number', 1),
                    'duration_ms': track.get('duration_ms'),
                    'explicit': track.get('explicit', False),
                    'preview_url': track.get('preview_url')
                }
                for track in tracks
            ]
        
        # Données brutes et métadonnées
        processed['raw_data'] = {'spotify': album_data}
        processed['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'extractor': self.extractor_type.value,
            'source': DataSource.SPOTIFY.value
        }
        
        return processed
    
    def _process_artist_data(self, artist_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et nettoie les données d'un artiste"""
        processed = {
            'spotify_id': artist_data.get('id'),
            'name': artist_data.get('name'),
            'popularity': artist_data.get('popularity'),
            'followers': artist_data.get('followers', {}).get('total'),
            'genres': artist_data.get('genres', []),
            'images': artist_data.get('images', []),
            'external_urls': artist_data.get('external_urls', {})
        }
        
        # URL de l'image (prendre la plus grande)
        images = artist_data.get('images', [])
        if images:
            sorted_images = sorted(images, key=lambda x: (x.get('height', 0) * x.get('width', 0)), reverse=True)
            processed['image_url'] = sorted_images[0].get('url')
        
        # Genre principal (prendre le premier)
        genres = artist_data.get('genres', [])
        if genres:
            processed['primary_genre'] = genres[0]
        
        # Données brutes et métadonnées
        processed['raw_data'] = {'spotify': artist_data}
        processed['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'extractor': self.extractor_type.value,
            'source': DataSource.SPOTIFY.value
        }
        
        return processed
    
    def _process_search_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Traite les résultats de recherche"""
        processed_results = []
        
        for result in results:
            if not result:
                continue
            
            processed_result = {
                'spotify_id': result.get('id'),
                'name': result.get('name'),
                'popularity': result.get('popularity'),
                'external_urls': result.get('external_urls', {}),
                'preview_url': result.get('preview_url')
            }
            
            # Artistes
            artists = result.get('artists', [])
            if artists:
                processed_result['artist'] = artists[0].get('name')
                processed_result['artist_id'] = artists[0].get('id')
                if len(artists) > 1:
                    processed_result['featuring_artists'] = [a.get('name') for a in artists[1:]]
            
            # Album
            album = result.get('album', {})
            if album:
                processed_result['album'] = {
                    'id': album.get('id'),
                    'name': album.get('name'),
                    'release_date': album.get('release_date')
                }
            
            # Durée
            if result.get('duration_ms'):
                processed_result['duration_ms'] = result['duration_ms']
                processed_result['duration_seconds'] = result['duration_ms'] // 1000
            
            processed_results.append(processed_result)
        
        return processed_results
    
    def _convert_spotify_key(self, key_number: Optional[int]) -> Optional[str]:
        """Convertit la notation numérique Spotify en notation musicale"""
        if key_number is None or key_number < 0:
            return None
        
        # Mapping Spotify: 0=C, 1=C#/Db, 2=D, etc.
        key_mapping = {
            0: 'C',
            1: 'C#/Db',
            2: 'D',
            3: 'D#/Eb',
            4: 'E',
            5: 'F',
            6: 'F#/Gb',
            7: 'G',
            8: 'G#/Ab',
            9: 'A',
            10: 'A#/Bb',
            11: 'B'
        }
        
        return key_mapping.get(key_number)
    
    def _calculate_album_quality_score(self, album_data: Dict[str, Any]) -> float:
        """Calcule un score de qualité pour un album"""
        score = 0.0
        
        # Présence des champs de base (40%)
        base_fields = ['name', 'artist', 'release_date']
        for field in base_fields:
            if album_data.get(field):
                score += 0.4 / len(base_fields)
        
        # Métadonnées additionnelles (30%)
        metadata_fields = ['total_tracks', 'genres', 'cover_url', 'label']
        for field in metadata_fields:
            if album_data.get(field):
                score += 0.3 / len(metadata_fields)
        
        # Qualité des images (15%)
        images = album_data.get('images', [])
        if images:
            # Score basé sur le nombre et la qualité des images
            score += 0.15 * min(len(images) / 3, 1.0)
        
        # Popularité (15%)
        popularity = album_data.get('popularity')
        if popularity is not None:
            score += 0.15 * (popularity / 100)
        
        return min(score, 1.0)
    
    def _calculate_artist_quality_score(self, artist_data: Dict[str, Any]) -> float:
        """Calcule un score de qualité pour un artiste"""
        score = 0.0
        
        # Présence des champs de base (50%)
        if artist_data.get('name'):
            score += 0.5
        
        # Métadonnées (30%)
        metadata_fields = ['genres', 'image_url', 'followers']
        for field in metadata_fields:
            if artist_data.get(field):
                score += 0.3 / len(metadata_fields)
        
        # Popularité (20%)
        popularity = artist_data.get('popularity')
        if popularity is not None:
            score += 0.2 * (popularity / 100)
        
        return min(score, 1.0)
    
    def get_multiple_audio_features(self, track_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Récupère les audio features pour plusieurs morceaux en une seule requête.
        Plus efficace pour traiter de nombreux morceaux.
        
        Args:
            track_ids: Liste des IDs Spotify des morceaux (max 100)
            
        Returns:
            Dict: {track_id: audio_features}
        """
        if not track_ids:
            return {}
        
        # Spotify limite à 100 IDs par requête
        track_ids = track_ids[:100]
        
        try:
            self._ensure_authenticated()
            self.rate_limiter.wait_if_needed('spotify')
            
            params = {'ids': ','.join(track_ids)}
            
            response = self.session.get(
                f"{self.base_url}/audio-features",
                params=params,
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise APIRateLimitError("spotify")
            
            response.raise_for_status()
            data = response.json()
            
            # Organiser les résultats par ID
            features_by_id = {}
            for features in data.get('audio_features', []):
                if features:  # Peut être None si le track n'existe pas
                    features_by_id[features['id']] = features
            
            return features_by_id
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur lors de la récupération des audio features multiples: {e}")
            return {}
    
    def get_artist_top_tracks(self, artist_id: str, market: str = 'US') -> List[Dict[str, Any]]:
        """
        Récupère les morceaux les plus populaires d'un artiste.
        
        Args:
            artist_id: ID Spotify de l'artiste
            market: Code du marché (pays)
            
        Returns:
            Liste des top tracks
        """
        try:
            self._ensure_authenticated()
            self.rate_limiter.wait_if_needed('spotify')
            
            params = {'market': market}
            
            response = self.session.get(
                f"{self.base_url}/artists/{artist_id}/top-tracks",
                params=params,
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise APIRateLimitError("spotify")
            elif response.status_code == 404:
                return []
            
            response.raise_for_status()
            data = response.json()
            
            return data.get('tracks', [])
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur lors de la récupération des top tracks pour {artist_id}: {e}")
            return []
        """