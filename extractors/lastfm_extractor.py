# extractors/lastfm_extractor.py
import logging
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base_extractor import BaseExtractor, ExtractionResult, ExtractorConfig
from models.enums import ExtractorType, DataSource
from core.exceptions import ExtractionError, RateLimitError, ValidationError
from config.settings import settings
from utils.text_utils import clean_text, normalize_title


class LastFMExtractor(BaseExtractor):
    """
    Extracteur spécialisé pour Last.fm.
    
    Responsabilités :
    - Extraction des métadonnées musicales (tags, genres)
    - Informations sur la popularité (scrobbles, listeners)
    - Données d'albums et d'artistes complémentaires
    - Tags et genres pour enrichir les données
    """
    
    def __init__(self, config: Optional[ExtractorConfig] = None):
        super().__init__(ExtractorType.LASTFM, config)
        
        # Configuration Last.fm
        self.api_key = settings.lastfm_api_key
        if not self.api_key:
            self.logger.warning("Clé API Last.fm manquante - fonctionnalités limitées")
        
        self.base_url = "https://ws.audioscrobbler.com/2.0/"
        
        # Headers pour les requêtes
        self.headers = {
            "User-Agent": "MusicDataExtractor/1.0"
        }
        
        # Session HTTP
        self.session = self._create_session()
        
        # Configuration spécifique à Last.fm
        self.lastfm_config = {
            'include_tags': settings.get('lastfm.include_tags', True),
            'include_similar_artists': settings.get('lastfm.include_similar_artists', True),
            'include_wiki': settings.get('lastfm.include_wiki', False),
            'max_tags': settings.get('lastfm.max_tags', 10),
            'tag_threshold': settings.get('lastfm.tag_threshold', 50),  # Seuil de popularité des tags
            'language': settings.get('lastfm.language', 'en')
        }
        
        self.logger.info("LastFMExtractor initialisé")
    
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
    
    def _make_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Effectue une requête à l'API Last.fm"""
        if not self.api_key:
            raise ExtractionError("Clé API Last.fm requise")
        
        self.rate_limiter.wait_if_needed()
        
        # Paramètres de base
        request_params = {
            'method': method,
            'api_key': self.api_key,
            'format': 'json'
        }
        request_params.update(params)
        
        try:
            response = self.session.get(self.base_url, params=request_params, timeout=self.config.timeout)
            
            if response.status_code == 429:
                raise RateLimitError("Rate limit Last.fm atteint")
            
            response.raise_for_status()
            data = response.json()
            
            # Vérifier les erreurs Last.fm
            if 'error' in data:
                error_code = data.get('error', 0)
                error_message = data.get('message', 'Erreur inconnue')
                
                if error_code == 6:  # Track not found
                    return {}
                elif error_code == 11:  # Service offline
                    raise ExtractionError("Service Last.fm temporairement indisponible")
                else:
                    raise ExtractionError(f"Erreur Last.fm {error_code}: {error_message}")
            
            return data
            
        except requests.exceptions.RequestException as e:
            raise ExtractionError(f"Erreur réseau Last.fm: {e}")
    
    def extract_track_info(self, track_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations d'un morceau depuis Last.fm.
        
        Args:
            track_id: Non utilisé pour Last.fm (utilise artist + track)
            **kwargs: Paramètres requis
                - artist: str - Nom de l'artiste
                - track: str - Titre du morceau
                - mbid: str - MusicBrainz ID (optionnel)
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        artist = kwargs.get('artist')
        track = kwargs.get('track')
        mbid = kwargs.get('mbid')
        
        if not artist or not track:
            return ExtractionResult(
                success=False,
                error="Paramètres 'artist' et 'track' requis pour Last.fm",
                source=self.extractor_type.value
            )
        
        cache_key = self.get_cache_key("extract_track_info", artist, track, mbid)
        
        def _extract():
            try:
                # Récupération des informations du track
                track_data = self._get_track_info(artist, track, mbid)
                
                if not album_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Album '{album}' par {artist} non trouvé sur Last.fm",
                        source=self.extractor_type.value
                    )
                
                # Enrichissement avec des données supplémentaires
                enriched_data = self._enrich_album_data(album_data, artist, album)
                
                # Calcul du score de qualité
                quality_score = self._calculate_album_quality_score(enriched_data)
                
                return ExtractionResult(
                    success=True,
                    data=enriched_data,
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
        Extrait les informations d'un artiste depuis Last.fm.
        
        Args:
            artist_id: Non utilisé pour Last.fm
            **kwargs: Paramètres requis
                - artist: str - Nom de l'artiste
                - mbid: str - MusicBrainz ID (optionnel)
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        artist = kwargs.get('artist', artist_id)  # Fallback sur artist_id si artist pas fourni
        mbid = kwargs.get('mbid')
        
        if not artist:
            return ExtractionResult(
                success=False,
                error="Paramètre 'artist' requis pour Last.fm",
                source=self.extractor_type.value
            )
        
        cache_key = self.get_cache_key("extract_artist_info", artist, mbid)
        
        def _extract():
            try:
                # Récupération des informations de l'artiste
                artist_data = self._get_artist_info(artist, mbid)
                
                if not artist_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Artiste '{artist}' non trouvé sur Last.fm",
                        source=self.extractor_type.value
                    )
                
                # Enrichissement avec des données supplémentaires
                enriched_data = self._enrich_artist_data(artist_data, artist)
                
                # Calcul du score de qualité
                quality_score = self._calculate_artist_quality_score(enriched_data)
                
                return ExtractionResult(
                    success=True,
                    data=enriched_data,
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
        Recherche des morceaux sur Last.fm.
        
        Args:
            query: Requête de recherche
            limit: Nombre maximum de résultats
            **kwargs: Options additionnelles
        
        Returns:
            ExtractionResult: Résultat de la recherche
        """
        cache_key = self.get_cache_key("search_tracks", query, limit, **kwargs)
        
        def _extract():
            try:
                search_results = self._search_tracks(query, limit)
                
                if not search_results:
                    return ExtractionResult(
                        success=False,
                        error=f"Aucun résultat pour: {query}",
                        source=self.extractor_type.value
                    )
                
                # Traitement des résultats
                processed_results = self._process_search_results(search_results)
                
                return ExtractionResult(
                    success=True,
                    data={'results': processed_results, 'total': len(processed_results)},
                    source=self.extractor_type.value,
                    quality_score=0.7
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def _get_track_info(self, artist: str, track: str, mbid: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Récupère les informations d'un track depuis Last.fm"""
        params = {
            'artist': artist,
            'track': track
        }
        
        if mbid:
            params['mbid'] = mbid
        
        try:
            response = self._make_request('track.getInfo', params)
            return response.get('track', {})
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération du track {artist} - {track}: {e}")
            return None
    
    def _get_album_info(self, artist: str, album: str, mbid: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Récupère les informations d'un album depuis Last.fm"""
        params = {
            'artist': artist,
            'album': album
        }
        
        if mbid:
            params['mbid'] = mbid
        
        try:
            response = self._make_request('album.getInfo', params)
            return response.get('album', {})
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de l'album {artist} - {album}: {e}")
            return None
    
    def _get_artist_info(self, artist: str, mbid: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Récupère les informations d'un artiste depuis Last.fm"""
        params = {'artist': artist}
        
        if mbid:
            params['mbid'] = mbid
        
        try:
            response = self._make_request('artist.getInfo', params)
            return response.get('artist', {})
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de l'artiste {artist}: {e}")
            return None
    
    def _search_tracks(self, query: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        """Effectue une recherche de tracks sur Last.fm"""
        params = {
            'track': query,
            'limit': min(limit, 100)  # Last.fm limite à 100
        }
        
        try:
            response = self._make_request('track.search', params)
            results = response.get('results', {}).get('trackmatches', {}).get('track', [])
            
            # Assurer que c'est une liste
            if isinstance(results, dict):
                results = [results]
            
            return results
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche '{query}': {e}")
            return None
    
    def _enrich_track_data(self, track_data: Dict[str, Any], artist: str, track: str) -> Dict[str, Any]:
        """Enrichit les données d'un track avec des informations supplémentaires"""
        enriched = {
            'lastfm_name': track_data.get('name'),
            'lastfm_artist': track_data.get('artist', {}).get('name') if isinstance(track_data.get('artist'), dict) else track_data.get('artist'),
            'lastfm_url': track_data.get('url'),
            'lastfm_mbid': track_data.get('mbid'),
            'duration_seconds': self._parse_duration(track_data.get('duration', '0')),
            'playcount': self._safe_int(track_data.get('playcount', 0)),
            'listeners': self._safe_int(track_data.get('listeners', 0)),
            'tags': [],
            'wiki': {},
            'similar_tracks': [],
            'album_info': {}
        }
        
        # Traitement des tags si configuré
        if self.lastfm_config['include_tags']:
            tags_data = track_data.get('toptags', {}).get('tag', [])
            enriched['tags'] = self._process_tags(tags_data)
        
        # Informations d'album
        album_data = track_data.get('album')
        if album_data:
            enriched['album_info'] = {
                'name': album_data.get('title'),
                'artist': album_data.get('artist'),
                'mbid': album_data.get('mbid'),
                'url': album_data.get('url'),
                'image': self._extract_images(album_data.get('image', []))
            }
        
        # Wiki/Description
        wiki_data = track_data.get('wiki')
        if wiki_data and self.lastfm_config['include_wiki']:
            enriched['wiki'] = {
                'summary': clean_text(wiki_data.get('summary', '')),
                'content': clean_text(wiki_data.get('content', '')),
                'published': wiki_data.get('published')
            }
        
        # Métadonnées d'extraction
        enriched['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'extractor': self.extractor_type.value,
            'api_method': 'track.getInfo',
            'search_artist': artist,
            'search_track': track
        }
        
        # Données brutes pour debug
        enriched['raw_data'] = track_data
        
        return enriched
    
    def _enrich_album_data(self, album_data: Dict[str, Any], artist: str, album: str) -> Dict[str, Any]:
        """Enrichit les données d'un album avec des informations supplémentaires"""
        enriched = {
            'lastfm_name': album_data.get('name'),
            'lastfm_artist': album_data.get('artist'),
            'lastfm_url': album_data.get('url'),
            'lastfm_mbid': album_data.get('mbid'),
            'release_date': album_data.get('releasedate'),
            'playcount': self._safe_int(album_data.get('playcount', 0)),
            'listeners': self._safe_int(album_data.get('listeners', 0)),
            'tags': [],
            'wiki': {},
            'tracks': [],
            'images': []
        }
        
        # Traitement des tags
        if self.lastfm_config['include_tags']:
            tags_data = album_data.get('tags', {}).get('tag', [])
            enriched['tags'] = self._process_tags(tags_data)
        
        # Tracklist
        tracks_data = album_data.get('tracks', {}).get('track', [])
        if isinstance(tracks_data, dict):
            tracks_data = [tracks_data]
        
        enriched_tracks = []
        for track in tracks_data:
            track_info = {
                'name': track.get('name'),
                'duration_seconds': self._parse_duration(track.get('duration', '0')),
                'rank': self._safe_int(track.get('@attr', {}).get('rank', 0)),
                'url': track.get('url'),
                'streamable': track.get('streamable') == '1'
            }
            enriched_tracks.append(track_info)
        
        enriched['tracks'] = enriched_tracks
        enriched['track_count'] = len(enriched_tracks)
        
        # Images
        images_data = album_data.get('image', [])
        enriched['images'] = self._extract_images(images_data)
        
        # Wiki
        wiki_data = album_data.get('wiki')
        if wiki_data and self.lastfm_config['include_wiki']:
            enriched['wiki'] = {
                'summary': clean_text(wiki_data.get('summary', '')),
                'content': clean_text(wiki_data.get('content', '')),
                'published': wiki_data.get('published')
            }
        
        # Métadonnées d'extraction
        enriched['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'extractor': self.extractor_type.value,
            'api_method': 'album.getInfo',
            'search_artist': artist,
            'search_album': album
        }
        
        enriched['raw_data'] = album_data
        
        return enriched
    
    def _enrich_artist_data(self, artist_data: Dict[str, Any], artist: str) -> Dict[str, Any]:
        """Enrichit les données d'un artiste avec des informations supplémentaires"""
        enriched = {
            'lastfm_name': artist_data.get('name'),
            'lastfm_url': artist_data.get('url'),
            'lastfm_mbid': artist_data.get('mbid'),
            'playcount': self._safe_int(artist_data.get('stats', {}).get('playcount', 0)),
            'listeners': self._safe_int(artist_data.get('stats', {}).get('listeners', 0)),
            'tags': [],
            'similar_artists': [],
            'wiki': {},
            'images': []
        }
        
        # Traitement des tags
        if self.lastfm_config['include_tags']:
            tags_data = artist_data.get('tags', {}).get('tag', [])
            enriched['tags'] = self._process_tags(tags_data)
        
        # Artistes similaires
        if self.lastfm_config['include_similar_artists']:
            similar_data = artist_data.get('similar', {}).get('artist', [])
            if isinstance(similar_data, dict):
                similar_data = [similar_data]
            
            similar_artists = []
            for similar in similar_data[:10]:  # Limiter à 10
                similar_info = {
                    'name': similar.get('name'),
                    'url': similar.get('url'),
                    'match': self._safe_float(similar.get('match', 0))
                }
                similar_artists.append(similar_info)
            
            enriched['similar_artists'] = similar_artists
        
        # Images
        images_data = artist_data.get('image', [])
        enriched['images'] = self._extract_images(images_data)
        
        # Wiki/Biographie
        bio_data = artist_data.get('bio')
        if bio_data and self.lastfm_config['include_wiki']:
            enriched['wiki'] = {
                'summary': clean_text(bio_data.get('summary', '')),
                'content': clean_text(bio_data.get('content', '')),
                'published': bio_data.get('published')
            }
        
        # Métadonnées d'extraction
        enriched['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'extractor': self.extractor_type.value,
            'api_method': 'artist.getInfo',
            'search_artist': artist
        }
        
        enriched['raw_data'] = artist_data
        
        return enriched
    
    def _process_tags(self, tags_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Traite les tags Last.fm"""
        if isinstance(tags_data, dict):
            tags_data = [tags_data]
        
        processed_tags = []
        for tag in tags_data[:self.lastfm_config['max_tags']]:
            tag_info = {
                'name': tag.get('name'),
                'count': self._safe_int(tag.get('count', 0)),
                'url': tag.get('url')
            }
            
            # Filtrer par seuil de popularité si configuré
            if tag_info['count'] >= self.lastfm_config['tag_threshold']:
                processed_tags.append(tag_info)
        
        # Trier par popularité
        processed_tags.sort(key=lambda x: x['count'], reverse=True)
        
        return processed_tags
    
    def _extract_images(self, images_data: List[Dict[str, Any]]) -> Dict[str, str]:
        """Extrait les URLs d'images par taille"""
        images = {}
        
        if isinstance(images_data, list):
            for image in images_data:
                size = image.get('size', 'unknown')
                url = image.get('#text', '')
                if url:
                    images[size] = url
        
        return images
    
    def _process_search_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Traite les résultats de recherche"""
        processed = []
        
        for result in results:
            processed_result = {
                'lastfm_name': result.get('name'),
                'lastfm_artist': result.get('artist'),
                'lastfm_url': result.get('url'),
                'lastfm_mbid': result.get('mbid'),
                'listeners': self._safe_int(result.get('listeners', 0)),
                'images': self._extract_images(result.get('image', [])),
                'streamable': result.get('streamable') == '1',
                'source': self.extractor_type.value
            }
            
            # Score de pertinence basique basé sur les listeners
            listeners = processed_result['listeners']
            if listeners > 100000:
                processed_result['relevance_score'] = 1.0
            elif listeners > 10000:
                processed_result['relevance_score'] = 0.8
            elif listeners > 1000:
                processed_result['relevance_score'] = 0.6
            else:
                processed_result['relevance_score'] = 0.4
            
            processed.append(processed_result)
        
        # Trier par score de pertinence
        processed.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return processed
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse une durée Last.fm (en millisecondes) vers secondes"""
        try:
            duration_ms = int(duration_str)
            return duration_ms // 1000 if duration_ms > 0 else 0
        except (ValueError, TypeError):
            return 0
    
    def _safe_int(self, value: Any) -> int:
        """Conversion sécurisée vers int"""
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    
    def _safe_float(self, value: Any) -> float:
        """Conversion sécurisée vers float"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    def _calculate_album_quality_score(self, album_data: Dict[str, Any]) -> float:
        """Calcule un score de qualité pour un album"""
        score = 0.0
        max_score = 0.0
        
        # Présence des champs de base (40%)
        base_fields = ['lastfm_name', 'lastfm_artist', 'track_count']
        for field in base_fields:
            max_score += 0.4 / len(base_fields)
            if album_data.get(field):
                score += 0.4 / len(base_fields)
        
        # Popularité (30%)
        max_score += 0.3
        listeners = album_data.get('listeners', 0)
        if listeners > 0:
            # Score logarithmique basé sur les listeners
            import math
            popularity_score = min(math.log10(listeners) / 6.0, 1.0)  # Normaliser sur 1M listeners
            score += 0.3 * popularity_score
        
        # Métadonnées enrichies (30%)
        metadata_score = 0.0
        metadata_fields = ['tags', 'wiki', 'images', 'release_date']
        for field in metadata_fields:
            if album_data.get(field):
                if isinstance(album_data[field], (list, dict)) and len(album_data[field]) > 0:
                    metadata_score += 1.0
                elif isinstance(album_data[field], str) and album_data[field].strip():
                    metadata_score += 1.0
        
        max_score += 0.3
        score += 0.3 * (metadata_score / len(metadata_fields))
        
        return min(score / max_score if max_score > 0 else 0.0, 1.0)
    
    def _calculate_artist_quality_score(self, artist_data: Dict[str, Any]) -> float:
        """Calcule un score de qualité pour un artiste"""
        score = 0.0
        max_score = 1.0
        
        # Champs de base
        if artist_data.get('lastfm_name'):
            score += 0.2
        
        # Popularité
        listeners = artist_data.get('listeners', 0)
        if listeners > 0:
            import math
            popularity_score = min(math.log10(listeners) / 7.0, 0.3)  # Max 0.3
            score += popularity_score
        
        # Tags
        tags = artist_data.get('tags', [])
        if tags:
            score += min(len(tags) / 10.0, 0.2)  # Max 0.2
        
        # Artistes similaires
        similar = artist_data.get('similar_artists', [])
        if similar:
            score += min(len(similar) / 10.0, 0.1)  # Max 0.1
        
        # Wiki/Bio
        wiki = artist_data.get('wiki', {})
        if wiki and wiki.get('summary'):
            score += 0.1
        
        # Images
        images = artist_data.get('images', {})
        if images:
            score += 0.1
        
        return min(score / max_score, 1.0)
    
    def get_top_tags(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Récupère les tags les plus populaires sur Last.fm"""
        cache_key = self.get_cache_key("get_top_tags", limit)
        
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            params = {'limit': min(limit, 100)}
            response = self._make_request('tag.getTopTags', params)
            
            tags_data = response.get('toptags', {}).get('tag', [])
            if isinstance(tags_data, dict):
                tags_data = [tags_data]
            
            processed_tags = []
            for tag in tags_data:
                tag_info = {
                    'name': tag.get('name'),
                    'count': self._safe_int(tag.get('count', 0)),
                    'reach': self._safe_int(tag.get('reach', 0)),
                    'taggings': self._safe_int(tag.get('taggings', 0)),
                    'streamable': tag.get('streamable') == '1',
                    'wiki': tag.get('wiki', {})
                }
                processed_tags.append(tag_info)
            
            # Mettre en cache pour 24h
            self.cache_manager.set(cache_key, processed_tags, expire_days=1)
            
            return processed_tags
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des top tags: {e}")
            return []
    
    def get_track_correction(self, artist: str, track: str) -> Optional[Dict[str, str]]:
        """Obtient la correction orthographique pour un track"""
        try:
            params = {
                'artist': artist,
                'track': track
            }
            response = self._make_request('track.getCorrection', params)
            
            correction = response.get('corrections', {}).get('correction', {})
            if correction:
                track_info = correction.get('track', {})
                artist_info = correction.get('artist', {})
                
                return {
                    'corrected_track': track_info.get('name'),
                    'corrected_artist': artist_info.get('name'),
                    'track_mbid': track_info.get('mbid'),
                    'artist_mbid': artist_info.get('mbid')
                }
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Pas de correction trouvée pour {artist} - {track}: {e}")
            return None track_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Track '{track}' par {artist} non trouvé sur Last.fm",
                        source=self.extractor_type.value
                    )
                
                # Enrichissement avec des données supplémentaires
                enriched_data = self._enrich_track_data(track_data, artist, track)
                
                # Calcul du score de qualité
                quality_score = self.calculate_quality_score(enriched_data)
                
                return ExtractionResult(
                    success=True,
                    data=enriched_data,
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
        Extrait les informations d'un album depuis Last.fm.
        
        Args:
            album_id: Non utilisé pour Last.fm
            **kwargs: Paramètres requis
                - artist: str - Nom de l'artiste
                - album: str - Titre de l'album
                - mbid: str - MusicBrainz ID (optionnel)
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        artist = kwargs.get('artist')
        album = kwargs.get('album')
        mbid = kwargs.get('mbid')
        
        if not artist or not album:
            return ExtractionResult(
                success=False,
                error="Paramètres 'artist' et 'album' requis pour Last.fm",
                source=self.extractor_type.value
            )
        
        cache_key = self.get_cache_key("extract_album_info", artist, album, mbid)
        
        def _extract():
            try:
                # Récupération des informations de l'album
                album_data = self._get_album_info(artist, album, mbid)
                
                if not