# extractors/api_extractors/discogs_extractor.py
"""
Extracteur optimisé pour l'API Discogs - spécialisé dans les crédits détaillés et informations de release.
Version optimisée avec cache intelligent, retry automatique et gestion d'erreurs robuste.
"""

import logging
import time
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
from models.enums import DataSource, CreditType, CreditCategory


class DiscogsExtractor:
    """
    Extracteur spécialisé pour l'API Discogs.
    
    Fonctionnalités optimisées :
    - Extraction détaillée des crédits de production
    - Informations complètes sur les releases et pressings
    - Métadonnées avancées (labels, formats, années)
    - Recherche avancée avec filtres spécialisés
    - Cache intelligent pour éviter les requêtes répétées
    - Rate limiting respectueux des limites Discogs
    - Gestion robuste des erreurs avec retry
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration API Discogs depuis variables d'environnement
        self.token = settings.discogs_token
        
        if not self.token:
            self.logger.warning("⚠️ Token Discogs manquant - fonctionnalités limitées")
        
        # URLs de base
        self.base_url = "https://api.discogs.com"
        
        # Configuration optimisée
        self.config = {
            'max_retries': settings.get('discogs.max_retries', 3),
            'timeout': settings.get('discogs.timeout', 20),
            'rate_limit_requests_per_second': settings.get('discogs.rate_limit', 1),  # Discogs limite à 60/min
            'include_tracklist': settings.get('discogs.include_tracklist', True),
            'include_credits': settings.get('discogs.include_credits', True),
            'include_images': settings.get('discogs.include_images', True),
            'search_limit': settings.get('discogs.search_limit', 25),
            'preferred_formats': settings.get('discogs.preferred_formats', ['Vinyl', 'CD', 'Digital']),
            'country_filter': settings.get('discogs.country_filter', None)
        }
        
        # Headers optimisés
        self.headers = {
            "User-Agent": "MusicDataExtractor/1.0 +https://github.com/your-project",
            "Accept": "application/vnd.discogs.v2.discogs+json",
            "Accept-Encoding": "gzip"
        }
        
        if self.token:
            self.headers["Authorization"] = f"Discogs token={self.token}"
        
        # Session HTTP optimisée
        self.session = self._create_session()
        
        # Rate limiter - Discogs limite à 60 req/min pour les utilisateurs authentifiés
        self.rate_limiter = RateLimiter(
            requests_per_second=self.config['rate_limit_requests_per_second']
        )
        
        # Cache manager
        self.cache_manager = CacheManager(namespace='discogs') if CacheManager else None
        
        # Statistiques de performance
        self.stats = {
            'releases_extracted': 0,
            'masters_extracted': 0,
            'artists_extracted': 0,
            'searches_performed': 0,
            'api_calls_made': 0,
            'cache_hits': 0,
            'failed_requests': 0,
            'total_time_spent': 0.0
        }
        
        self.logger.info("✅ DiscogsExtractor optimisé initialisé")
    
    def _create_session(self) -> requests.Session:
        """Crée une session HTTP avec retry automatique"""
        session = requests.Session()
        
        # Configuration du retry
        retry_strategy = Retry(
            total=self.config['max_retries'],
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _make_api_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Effectue une requête API avec gestion d'erreurs et rate limiting"""
        self.rate_limiter.wait()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            start_time = time.time()
            response = self.session.get(
                url,
                headers=self.headers,
                params=params or {},
                timeout=self.config['timeout']
            )
            
            self.stats['api_calls_made'] += 1
            self.stats['total_time_spent'] += time.time() - start_time
            
            if response.status_code == 200:
                return response.json()
                
            elif response.status_code == 401:
                raise APIAuthenticationError("Discogs", "DISCOGS_TOKEN")
                
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                self.logger.warning(f"⚠️ Rate limit Discogs atteint, attente {retry_after}s")
                time.sleep(retry_after)
                raise APIRateLimitError("Discogs", retry_after)
                
            elif response.status_code == 404:
                self.logger.debug(f"Ressource non trouvée: {endpoint}")
                return None
                
            else:
                self.logger.error(f"❌ Erreur API Discogs {response.status_code}: {response.text}")
                self.stats['failed_requests'] += 1
                return None
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Erreur réseau Discogs: {e}")
            self.stats['failed_requests'] += 1
            return None
    
    # ===== MÉTHODES D'EXTRACTION PRINCIPALES =====
    
    def search_release(self, query: str, artist: Optional[str] = None, 
                      format_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Recherche de releases sur Discogs avec scoring de pertinence.
        
        Args:
            query: Titre de l'album/release à rechercher
            artist: Nom de l'artiste (optionnel mais recommandé)
            format_filter: Filtre de format ('Vinyl', 'CD', etc.)
            
        Returns:
            Liste des releases trouvées avec score de pertinence
        """
        cache_key = f"search_release_{query}_{artist}_{format_filter}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            # Construction des paramètres de recherche
            params = {
                'type': 'release',
                'q': query,
                'per_page': self.config['search_limit']
            }
            
            if artist:
                params['artist'] = artist
            
            if format_filter:
                params['format'] = format_filter
            elif self.config['preferred_formats']:
                params['format'] = ','.join(self.config['preferred_formats'])
            
            if self.config['country_filter']:
                params['country'] = self.config['country_filter']
            
            data = self._make_api_request('database/search', params)
            if not data or 'results' not in data:
                return []
            
            releases = data.get('results', [])
            
            # Processing et scoring des résultats
            processed_releases = []
            for release in releases:
                processed_release = self._process_search_result(release)
                
                # Calcul du score de pertinence
                relevance_score = self._calculate_release_relevance_score(
                    processed_release, query, artist
                )
                processed_release['relevance_score'] = relevance_score
                
                processed_releases.append(processed_release)
            
            # Tri par score de pertinence
            processed_releases.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
            
            # Mise en cache
            if self.cache_manager:
                self.cache_manager.set(cache_key, processed_releases, ttl=3600)
            
            self.stats['searches_performed'] += 1
            return processed_releases
            
        except Exception as e:
            self.logger.error(f"❌ Erreur recherche Discogs: {e}")
            return []
    
    def get_release_details(self, release_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """
        Récupère les détails complets d'une release Discogs.
        
        Args:
            release_id: ID Discogs de la release
            
        Returns:
            Dictionnaire avec toutes les données de la release
        """
        cache_key = f"release_details_{release_id}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            data = self._make_api_request(f'releases/{release_id}')
            if not data:
                return None
            
            processed_data = self._process_release_data(data)
            
            # Mise en cache
            if self.cache_manager:
                self.cache_manager.set(cache_key, processed_data, ttl=3600)
            
            self.stats['releases_extracted'] += 1
            return processed_data
            
        except Exception as e:
            self.logger.error(f"❌ Erreur récupération release {release_id}: {e}")
            return None
    
    def get_master_details(self, master_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """
        Récupère les détails d'un master release Discogs.
        
        Args:
            master_id: ID Discogs du master
            
        Returns:
            Dictionnaire avec les données du master
        """
        cache_key = f"master_details_{master_id}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            data = self._make_api_request(f'masters/{master_id}')
            if not data:
                return None
            
            processed_data = self._process_master_data(data)
            
            # Mise en cache
            if self.cache_manager:
                self.cache_manager.set(cache_key, processed_data, ttl=3600)
            
            self.stats['masters_extracted'] += 1
            return processed_data
            
        except Exception as e:
            self.logger.error(f"❌ Erreur récupération master {master_id}: {e}")
            return None
    
    def get_artist_details(self, artist_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """
        Récupère les détails d'un artiste Discogs.
        
        Args:
            artist_id: ID Discogs de l'artiste
            
        Returns:
            Dictionnaire avec les données de l'artiste
        """
        cache_key = f"artist_details_{artist_id}"
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            data = self._make_api_request(f'artists/{artist_id}')
            if not data:
                return None
            
            processed_data = self._process_artist_data(data)
            
            # Mise en cache
            if self.cache_manager:
                self.cache_manager.set(cache_key, processed_data, ttl=3600)
            
            self.stats['artists_extracted'] += 1
            return processed_data
            
        except Exception as e:
            self.logger.error(f"❌ Erreur récupération artiste {artist_id}: {e}")
            return None
    
    # ===== MÉTHODES DE TRAITEMENT =====
    
    def _process_search_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Traite un résultat de recherche Discogs"""
        processed = {
            'discogs_id': result.get('id'),
            'type': result.get('type'),
            'title': result.get('title'),
            'uri': result.get('uri'),
            'resource_url': result.get('resource_url'),
            'thumb': result.get('thumb'),
            'cover_image': result.get('cover_image'),
            'year': result.get('year'),
            'format': result.get('format', []),
            'label': result.get('label', []),
            'genre': result.get('genre', []),
            'style': result.get('style', []),
            'country': result.get('country'),
            'catno': result.get('catno'),
            'barcode': result.get('barcode', [])
        }
        
        return processed
    
    def _process_release_data(self, release_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et nettoie les données d'une release"""
        processed = {
            'discogs_id': release_data.get('id'),
            'title': release_data.get('title'),
            'year': release_data.get('year'),
            'released': release_data.get('released'),
            'released_formatted': release_data.get('released_formatted'),
            'country': release_data.get('country'),
            'genres': release_data.get('genres', []),
            'styles': release_data.get('styles', []),
            'master_id': release_data.get('master_id'),
            'master_url': release_data.get('master_url'),
            'uri': release_data.get('uri'),
            'resource_url': release_data.get('resource_url'),
            'data_quality': release_data.get('data_quality'),
            'status': release_data.get('status'),
            'notes': release_data.get('notes'),
            'estimated_weight': release_data.get('estimated_weight')
        }
        
        # Artistes
        artists = release_data.get('artists', [])
        if artists:
            processed['artists'] = [
                {
                    'id': artist.get('id'),
                    'name': clean_artist_name(artist.get('name', '')),
                    'anv': artist.get('anv'),  # Artist Name Variation
                    'join': artist.get('join'),
                    'role': artist.get('role'),
                    'tracks': artist.get('tracks'),
                    'resource_url': artist.get('resource_url')
                }
                for artist in artists
            ]
            
            # Artiste principal
            main_artist = artists[0] if artists else {}
            processed['main_artist'] = clean_artist_name(main_artist.get('name', ''))
            processed['main_artist_id'] = main_artist.get('id')
        
        # Labels
        labels = release_data.get('labels', [])
        if labels:
            processed['labels'] = [
                {
                    'id': label.get('id'),
                    'name': label.get('name'),
                    'catno': label.get('catno'),
                    'resource_url': label.get('resource_url')
                }
                for label in labels
            ]
            
            # Label principal
            main_label = labels[0] if labels else {}
            processed['main_label'] = main_label.get('name')
            processed['catalog_number'] = main_label.get('catno')
        
        # Formats
        formats = release_data.get('formats', [])
        if formats:
            processed['formats'] = [
                {
                    'name': fmt.get('name'),
                    'qty': fmt.get('qty'),
                    'text': fmt.get('text'),
                    'descriptions': fmt.get('descriptions', [])
                }
                for fmt in formats
            ]
            
            # Format principal
            main_format = formats[0] if formats else {}
            processed['main_format'] = main_format.get('name')
            processed['format_descriptions'] = main_format.get('descriptions', [])
        
        # Images
        images = release_data.get('images', [])
        if images and self.config['include_images']:
            processed['images'] = [
                {
                    'type': img.get('type'),
                    'uri': img.get('uri'),
                    'uri150': img.get('uri150'),
                    'width': img.get('width'),
                    'height': img.get('height')
                }
                for img in images
            ]
            
            # Image principale (cover)
            cover_image = next(
                (img for img in images if img.get('type') == 'primary'), 
                images[0] if images else None
            )
            if cover_image:
                processed['cover_art_url'] = cover_image.get('uri')
        
        # Tracklist
        tracklist = release_data.get('tracklist', [])
        if tracklist and self.config['include_tracklist']:
            processed['tracklist'] = [
                {
                    'position': track.get('position'),
                    'type_': track.get('type_'),
                    'title': track.get('title'),
                    'duration': track.get('duration'),
                    'extraartists': self._process_track_credits(track.get('extraartists', [])),
                    'artists': [
                        {
                            'id': artist.get('id'),
                            'name': clean_artist_name(artist.get('name', '')),
                            'anv': artist.get('anv'),
                            'join': artist.get('join'),
                            'role': artist.get('role')
                        }
                        for artist in track.get('artists', [])
                    ]
                }
                for track in tracklist
            ]
        
        # Crédits extraartists (producteurs, ingénieurs, etc.)
        extraartists = release_data.get('extraartists', [])
        if extraartists and self.config['include_credits']:
            processed['credits'] = self._process_track_credits(extraartists)
        
        # Identifiants
        identifiers = release_data.get('identifiers', [])
        if identifiers:
            processed['identifiers'] = [
                {
                    'type': ident.get('type'),
                    'value': ident.get('value'),
                    'description': ident.get('description')
                }
                for ident in identifiers
            ]
            
            # Extraction des identifiants spéciaux
            for ident in identifiers:
                if ident.get('type') == 'Barcode':
                    processed['barcode'] = ident.get('value')
                elif ident.get('type') == 'Matrix / Runout':
                    processed['matrix_number'] = ident.get('value')
        
        # Métadonnées d'extraction
        processed['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'source': DataSource.DISCOGS.value,
            'extractor_version': '1.0.0'
        }
        
        return processed
    
    def _process_master_data(self, master_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et nettoie les données d'un master release"""
        processed = {
            'discogs_master_id': master_data.get('id'),
            'title': master_data.get('title'),
            'year': master_data.get('year'),
            'genres': master_data.get('genres', []),
            'styles': master_data.get('styles', []),
            'uri': master_data.get('uri'),
            'resource_url': master_data.get('resource_url'),
            'data_quality': master_data.get('data_quality'),
            'num_for_sale': master_data.get('num_for_sale'),
            'lowest_price': master_data.get('lowest_price'),
            'notes': master_data.get('notes')
        }
        
        # Artistes
        artists = master_data.get('artists', [])
        if artists:
            processed['artists'] = [
                {
                    'id': artist.get('id'),
                    'name': clean_artist_name(artist.get('name', '')),
                    'anv': artist.get('anv'),
                    'join': artist.get('join'),
                    'role': artist.get('role'),
                    'resource_url': artist.get('resource_url')
                }
                for artist in artists
            ]
            
            # Artiste principal
            main_artist = artists[0] if artists else {}
            processed['main_artist'] = clean_artist_name(main_artist.get('name', ''))
            processed['main_artist_id'] = main_artist.get('id')
        
        # Images
        images = master_data.get('images', [])
        if images:
            cover_image = next(
                (img for img in images if img.get('type') == 'primary'), 
                images[0] if images else None
            )
            if cover_image:
                processed['cover_art_url'] = cover_image.get('uri')
        
        # Tracklist
        tracklist = master_data.get('tracklist', [])
        if tracklist:
            processed['tracklist'] = [
                {
                    'position': track.get('position'),
                    'type_': track.get('type_'),
                    'title': track.get('title'),
                    'duration': track.get('duration'),
                    'extraartists': self._process_track_credits(track.get('extraartists', []))
                }
                for track in tracklist
            ]
        
        return processed
    
    def _process_artist_data(self, artist_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et nettoie les données d'un artiste"""
        processed = {
            'discogs_artist_id': artist_data.get('id'),
            'name': clean_artist_name(artist_data.get('name', '')),
            'real_name': artist_data.get('realname'),
            'profile': artist_data.get('profile'),
            'uri': artist_data.get('uri'),
            'resource_url': artist_data.get('resource_url'),
            'data_quality': artist_data.get('data_quality')
        }
        
        # Images
        images = artist_data.get('images', [])
        if images:
            processed['image_url'] = images[0].get('uri')
        
        # Noms alternatifs
        namevariations = artist_data.get('namevariations', [])
        if namevariations:
            processed['name_variations'] = namevariations
        
        # Aliases
        aliases = artist_data.get('aliases', [])
        if aliases:
            processed['aliases'] = [
                {
                    'id': alias.get('id'),
                    'name': alias.get('name'),
                    'resource_url': alias.get('resource_url')
                }
                for alias in aliases
            ]
        
        # URLs
        urls = artist_data.get('urls', [])
        if urls:
            processed['urls'] = urls
        
        return processed
    
    def _process_track_credits(self, extraartists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Traite les crédits d'un track ou d'une release"""
        credits = []
        
        for artist in extraartists:
            credit = {
                'artist_id': artist.get('id'),
                'artist_name': clean_artist_name(artist.get('name', '')),
                'anv': artist.get('anv'),  # Artist Name Variation
                'join': artist.get('join'),
                'role': artist.get('role', ''),
                'tracks': artist.get('tracks', ''),
                'resource_url': artist.get('resource_url')
            }
            
            # Normalisation du rôle
            role = artist.get('role', '').lower()
            credit['normalized_role'] = self._normalize_discogs_role(role)
            credit['credit_category'] = self._categorize_discogs_credit(role)
            
            credits.append(credit)
        
        return credits
    
    @lru_cache(maxsize=128)
    def _normalize_discogs_role(self, role: str) -> str:
        """Normalise un rôle Discogs vers notre système de crédits"""
        role_lower = role.lower().strip()
        
        # Mapping des rôles Discogs vers nos catégories
        role_mapping = {
            'producer': 'Producer',
            'executive producer': 'Executive Producer',
            'mixed by': 'Mixing Engineer',
            'mastered by': 'Mastering Engineer',
            'recorded by': 'Recording Engineer',
            'written-by': 'Songwriter',
            'lyrics by': 'Lyricist',
            'music by': 'Composer',
            'arranged by': 'Arranger',
            'vocals': 'Vocalist',
            'rap': 'Rapper',
            'guitar': 'Guitarist',
            'bass': 'Bassist',
            'drums': 'Drummer',
            'keyboards': 'Keyboardist',
            'piano': 'Pianist',
            'synthesizer': 'Synthesizer',
            'sampled': 'Sample Source',
            'featuring': 'Featured Artist'
        }
        
        # Recherche exacte
        if role_lower in role_mapping:
            return role_mapping[role_lower]
        
        # Recherche partielle
        for key, value in role_mapping.items():
            if key in role_lower:
                return value
        
        return role.title()
    
    @lru_cache(maxsize=64)
    def _categorize_discogs_credit(self, role: str) -> str:
        """Catégorise un crédit Discogs"""
        role_lower = role.lower()
        
        if any(word in role_lower for word in ['produc', 'beat', 'instrumental']):
            return CreditCategory.PRODUCTION.value
        elif any(word in role_lower for word in ['mix', 'master', 'engineer', 'record']):
            return CreditCategory.ENGINEERING.value
        elif any(word in role_lower for word in ['writ', 'lyric', 'compos', 'arrang']):
            return CreditCategory.WRITING.value
        elif any(word in role_lower for word in ['vocal', 'rap', 'sing', 'feat']):
            return CreditCategory.PERFORMANCE.value
        elif any(word in role_lower for word in ['guitar', 'bass', 'drum', 'keyboard', 'piano', 'synth']):
            return CreditCategory.INSTRUMENTATION.value
        else:
            return CreditCategory.OTHER.value
    
    def _calculate_release_relevance_score(self, release_data: Dict[str, Any], 
                                         search_title: str, search_artist: Optional[str] = None) -> float:
        """Calcule un score de pertinence pour un résultat de recherche"""
        score = 0.0
        
        release_title = release_data.get('title', '').lower()
        
        # Score basé sur le titre (poids: 60%)
        title_similarity = self._calculate_text_similarity(search_title.lower(), release_title)
        score += title_similarity * 0.6
        
        # Score basé sur l'artiste (poids: 25%)
        if search_artist:
            artist_name = release_data.get('main_artist', '').lower()
            if artist_name:
                artist_similarity = self._calculate_text_similarity(search_artist.lower(), artist_name)
                score += artist_similarity * 0.25
        
        # Bonus format préféré (poids: 10%)
        release_format = release_data.get('main_format', '')
        if release_format in self.config['preferred_formats']:
            score += 0.1
        
        # Bonus année récente (poids: 5%)
        year = release_data.get('year')
        if year and isinstance(year, int) and year >= 2000:
            score += 0.05
        
        return min(score, 1.0)
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calcule la similarité entre deux textes"""
        if text1 == text2:
            return 1.0
        
        if text1 in text2 or text2 in text1:
            return 0.8
        
        # Similarité basée sur les mots
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    # ===== MÉTHODES UTILITAIRES =====
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance"""
        return self.stats.copy()
    
    def clear_cache(self) -> bool:
        """Vide le cache Discogs"""
        if self.cache_manager:
            return self.cache_manager.clear()
        return True
    
    def health_check(self) -> Dict[str, Any]:
        """Vérifie l'état de santé de l'extracteur"""
        health = {
            'status': 'healthy',
            'issues': [],
            'token_configured': bool(self.token)
        }
        
        if not self.token:
            health['status'] = 'degraded'
            health['issues'].append('Token not configured - search limited')
            return health
        
        # Test API simple
        try:
            test_result = self._make_api_request('database/search', {
                'q': 'test', 'type': 'release', 'per_page': 1
            })
            if not test_result:
                health['status'] = 'degraded'
                health['issues'].append('API test failed')
        except Exception as e:
            health['status'] = 'unhealthy'
            health['issues'].append(f'API error: {str(e)}')
        
        return health