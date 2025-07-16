# extractors/genius_extractor.py
import logging
import re
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from .base_extractor import BaseExtractor, ExtractionResult, ExtractorConfig
from models.enums import ExtractorType, CreditType, DataSource
from models.entities import Track, Album, Artist, Credit
from core.exceptions import ExtractionError, APIRateLimitError, DataValidationError
from config.settings import settings
from utils.text_utils import normalize_text, extract_featuring_artists, clean_track_title


class GeniusExtractor(BaseExtractor):
    """
    Extracteur spécialisé pour Genius.
    
    Responsabilités :
    - Extraction détaillée des données de morceaux depuis Genius
    - Scraping des pages pour récupérer les crédits
    - Extraction des paroles et métadonnées
    - Gestion des formats spécifiques à Genius (annotations, etc.)
    """
    
    def __init__(self, config: Optional[ExtractorConfig] = None):
        super().__init__(ExtractorType.GENIUS, config)
        
        # Configuration API Genius
        self.api_key = settings.genius_api_key
        if not self.api_key:
            raise ExtractionError("Clé API Genius manquante")
        
        self.base_url = "https://api.genius.com"
        self.base_web_url = "https://genius.com"
        
        # Headers pour API
        self.api_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "MusicDataExtractor/1.0"
        }
        
        # Headers pour scraping web
        self.web_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        
        # Sessions séparées pour API et web scraping
        self.api_session = self._create_api_session()
        self.web_session = self._create_web_session()
        
        # Configuration spécifique à Genius
        self.genius_config = {
            'expand_credits': settings.get('credits.expand_all_credits', True),
            'wait_after_expand': settings.get('credits.wait_after_expand', 2),
            'max_retries': settings.get('credits.max_retries', 3),
            'extract_lyrics': settings.get('genius.extract_lyrics', False),
            'extract_annotations': settings.get('genius.extract_annotations', False)
        }
        
        self.logger.info("GeniusExtractor initialisé")
    
    def _create_api_session(self) -> requests.Session:
        """Crée une session pour l'API Genius"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(self.api_headers)
        
        return session
    
    def _create_web_session(self) -> requests.Session:
        """Crée une session pour le scraping web"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=2,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(self.web_headers)
        
        return session
    
    def extract_track_info(self, track_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations complètes d'un morceau depuis Genius.
        
        Args:
            track_id: ID du morceau sur Genius
            **kwargs: Options additionnelles
                - include_lyrics: bool - Inclure les paroles
                - include_credits: bool - Inclure les crédits détaillés
                - include_annotations: bool - Inclure les annotations
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        cache_key = self.get_cache_key("extract_track_info", track_id, **kwargs)
        
        def _extract():
            try:
                # Extraction via API
                api_data = self._get_track_from_api(track_id)
                if not api_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Morceau {track_id} non trouvé via API",
                        source=self.extractor_type.value
                    )
                
                # Extraction via scraping web si nécessaire
                web_data = {}
                track_url = api_data.get('url')
                
                if track_url and (kwargs.get('include_credits', True) or 
                                kwargs.get('include_lyrics', self.genius_config['extract_lyrics'])):
                    web_data = self._scrape_track_page(track_url)
                
                # Fusion des données
                combined_data = self._merge_track_data(api_data, web_data)
                
                # Validation
                is_valid, errors = self.validate_track_data(combined_data)
                if not is_valid:
                    self.logger.warning(f"Données invalides pour {track_id}: {errors}")
                
                # Calcul du score de qualité
                quality_score = self.calculate_quality_score(combined_data)
                
                return ExtractionResult(
                    success=True,
                    data=combined_data,
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
        Extrait les informations d'un album depuis Genius.
        
        Args:
            album_id: ID de l'album sur Genius
            **kwargs: Options additionnelles
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        cache_key = self.get_cache_key("extract_album_info", album_id, **kwargs)
        
        def _extract():
            try:
                # Extraction via API
                api_data = self._get_album_from_api(album_id)
                if not api_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Album {album_id} non trouvé",
                        source=self.extractor_type.value
                    )
                
                # Nettoyage et structuration des données
                album_data = self._process_album_data(api_data)
                
                # Calcul du score de qualité
                quality_score = self._calculate_album_quality_score(album_data)
                
                return ExtractionResult(
                    success=True,
                    data=album_data,
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
        Extrait les informations d'un artiste depuis Genius.
        
        Args:
            artist_id: ID de l'artiste sur Genius
            **kwargs: Options additionnelles
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        cache_key = self.get_cache_key("extract_artist_info", artist_id, **kwargs)
        
        def _extract():
            try:
                # Extraction via API
                api_data = self._get_artist_from_api(artist_id)
                if not api_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Artiste {artist_id} non trouvé",
                        source=self.extractor_type.value
                    )
                
                # Nettoyage et structuration des données
                artist_data = self._process_artist_data(api_data)
                
                # Calcul du score de qualité
                quality_score = self._calculate_artist_quality_score(artist_data)
                
                return ExtractionResult(
                    success=True,
                    data=artist_data,
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
        Recherche des morceaux sur Genius.
        
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
                # Recherche via API
                search_results = self._search_via_api(query, limit)
                
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
    
    def _get_track_from_api(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Récupère un morceau via l'API Genius"""
        try:
            self.rate_limiter.wait_if_needed()
            
            response = self.api_session.get(
                f"{self.base_url}/songs/{track_id}",
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise RateLimitError("Rate limit Genius API atteint")
            
            response.raise_for_status()
            data = response.json()
            
            return data.get('response', {}).get('song')
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur API lors de la récupération du morceau {track_id}: {e}")
            return None
    
    def _get_album_from_api(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Récupère un album via l'API Genius"""
        try:
            self.rate_limiter.wait_if_needed()
            
            response = self.api_session.get(
                f"{self.base_url}/albums/{album_id}",
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise RateLimitError("Rate limit Genius API atteint")
            
            response.raise_for_status()
            data = response.json()
            
            return data.get('response', {}).get('album')
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur API lors de la récupération de l'album {album_id}: {e}")
            return None
    
    def _get_artist_from_api(self, artist_id: str) -> Optional[Dict[str, Any]]:
        """Récupère un artiste via l'API Genius"""
        try:
            self.rate_limiter.wait_if_needed()
            
            response = self.api_session.get(
                f"{self.base_url}/artists/{artist_id}",
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise RateLimitError("Rate limit Genius API atteint")
            
            response.raise_for_status()
            data = response.json()
            
            return data.get('response', {}).get('artist')
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur API lors de la récupération de l'artiste {artist_id}: {e}")
            return None
    
    def _search_via_api(self, query: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        """Effectue une recherche via l'API Genius"""
        try:
            self.rate_limiter.wait_if_needed()
            
            params = {
                'q': query,
                'per_page': min(limit, 50)  # Genius limite à 50 par page
            }
            
            response = self.api_session.get(
                f"{self.base_url}/search",
                params=params,
                timeout=self.config.timeout
            )
            
            if response.status_code == 429:
                raise RateLimitError("Rate limit Genius API atteint")
            
            response.raise_for_status()
            data = response.json()
            
            hits = data.get('response', {}).get('hits', [])
            return [hit.get('result') for hit in hits if hit.get('result')]
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur API lors de la recherche '{query}': {e}")
            return None
    
    def _scrape_track_page(self, track_url: str) -> Dict[str, Any]:
        """
        Scrape la page web d'un morceau pour récupérer les données supplémentaires.
        
        Args:
            track_url: URL de la page du morceau
            
        Returns:
            Dict contenant les données scrapées
        """
        scraped_data = {}
        
        try:
            # Pause pour éviter la détection de bot
            time.sleep(0.5)
            
            response = self.web_session.get(track_url, timeout=self.config.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extraction des crédits
            if self.genius_config['expand_credits']:
                credits = self._extract_credits_from_page(soup, track_url)
                if credits:
                    scraped_data['credits'] = credits
            
            # Extraction des paroles
            if self.genius_config['extract_lyrics']:
                lyrics = self._extract_lyrics_from_page(soup)
                if lyrics:
                    scraped_data['lyrics'] = lyrics
            
            # Extraction des métadonnées additionnelles
            metadata = self._extract_metadata_from_page(soup)
            if metadata:
                scraped_data.update(metadata)
            
        except Exception as e:
            self.logger.warning(f"Erreur lors du scraping de {track_url}: {e}")
        
        return scraped_data
    
    def _extract_credits_from_page(self, soup: BeautifulSoup, track_url: str) -> List[Dict[str, Any]]:
        """
        Extrait les crédits depuis la page web du morceau.
        
        Args:
            soup: Objet BeautifulSoup de la page
            track_url: URL de la page (pour les requêtes AJAX)
            
        Returns:
            Liste des crédits trouvés
        """
        credits = []
        
        try:
            # Recherche des sections de crédits
            credits_sections = soup.find_all('div', class_=re.compile(r'SongCredits'))
            
            for section in credits_sections:
                # Extraction du titre de la section
                section_title = section.find('h3')
                if section_title:
                    credit_type = clean_text(section_title.get_text())
                    
                    # Extraction des personnes/entités
                    credit_items = section.find_all('a', class_=re.compile(r'SongCredits.*Link'))
                    
                    for item in credit_items:
                        name = clean_text(item.get_text())
                        if name:
                            credits.append({
                                'name': name,
                                'role': credit_type,
                                'source': 'genius_web'
                            })
            
            # Tentative d'expansion des crédits via JavaScript (si configuré)
            if self.genius_config['expand_credits'] and not credits:
                credits = self._try_expand_credits(track_url)
            
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction des crédits: {e}")
        
        return credits
    
    def _try_expand_credits(self, track_url: str) -> List[Dict[str, Any]]:
        """
        Tente d'étendre les crédits en cliquant sur les boutons d'expansion.
        
        Args:
            track_url: URL de la page du morceau
            
        Returns:
            Liste des crédits étendus
        """
        credits = []
        
        try:
            # Cette méthode nécessiterait Selenium pour être pleinement fonctionnelle
            # Pour l'instant, on retourne une liste vide
            # TODO: Implémenter avec Selenium si nécessaire
            
            self.logger.info("Expansion des crédits non implémentée (nécessite Selenium)")
            
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'expansion des crédits: {e}")
        
        return credits
    
    def _extract_lyrics_from_page(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait les paroles depuis la page web.
        
        Args:
            soup: Objet BeautifulSoup de la page
            
        Returns:
            Texte des paroles ou None
        """
        try:
            # Recherche de la div contenant les paroles
            lyrics_div = soup.find('div', class_=re.compile(r'Lyrics__Container'))
            
            if lyrics_div:
                # Nettoyage du HTML et extraction du texte
                lyrics_text = lyrics_div.get_text(separator='\n', strip=True)
                return clean_text(lyrics_text)
            
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction des paroles: {e}")
        
        return None
    
    def _extract_metadata_from_page(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Extrait les métadonnées additionnelles depuis la page web.
        
        Args:
            soup: Objet BeautifulSoup de la page
            
        Returns:
            Dict contenant les métadonnées
        """
        metadata = {}
        
        try:
            # Extraction de la date de sortie
            release_date = soup.find('span', class_=re.compile(r'HeaderMetadata.*Value'))
            if release_date:
                metadata['release_date_scraped'] = clean_text(release_date.get_text())
            
            # Extraction des tags/genres
            tags = soup.find_all('a', class_=re.compile(r'Tag'))
            if tags:
                metadata['tags'] = [clean_text(tag.get_text()) for tag in tags]
            
            # Extraction des statistiques de vues
            stats = soup.find('div', class_=re.compile(r'HeaderMetadata.*Stats'))
            if stats:
                views_text = stats.get_text()
                views_match = re.search(r'([\d,]+)\s*views?', views_text, re.IGNORECASE)
                if views_match:
                    views_str = views_match.group(1).replace(',', '')
                    try:
                        metadata['pageviews_scraped'] = int(views_str)
                    except ValueError:
                        pass
            
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction des métadonnées: {e}")
        
        return metadata
    
    def _merge_track_data(self, api_data: Dict[str, Any], web_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fusionne les données API et web d'un morceau.
        
        Args:
            api_data: Données de l'API
            web_data: Données du scraping web
            
        Returns:
            Dict contenant les données fusionnées
        """
        merged = {}
        
        # Données de base depuis l'API
        merged.update({
            'genius_id': api_data.get('id'),
            'title': api_data.get('title'),
            'artist': api_data.get('primary_artist', {}).get('name'),
            'artist_id': api_data.get('primary_artist', {}).get('id'),
            'url': api_data.get('url'),
            'path': api_data.get('path'),
            'release_date': api_data.get('release_date_for_display'),
            'pageviews': api_data.get('stats', {}).get('pageviews'),
            'hot': api_data.get('stats', {}).get('hot', False),
            'header_image': api_data.get('header_image_thumbnail_url'),
            'featured_artists': [artist.get('name') for artist in api_data.get('featured_artists', [])],
            'producer_artists': [artist.get('name') for artist in api_data.get('producer_artists', [])],
            'writer_artists': [artist.get('name') for artist in api_data.get('writer_artists', [])],
            'description': api_data.get('description', {}).get('plain') if api_data.get('description') else None,
            'apple_music_id': api_data.get('apple_music_id'),
            'spotify_uuid': api_data.get('spotify_uuid'),
            'youtube_url': api_data.get('youtube_url'),
            'soundcloud_url': api_data.get('soundcloud_url')
        })
        
        # Album information
        album_info = api_data.get('album')
        if album_info:
            merged['album'] = {
                'id': album_info.get('id'),
                'name': album_info.get('name'),
                'url': album_info.get('url'),
                'cover_art_url': album_info.get('cover_art_url'),
                'release_date': album_info.get('release_date_for_display')
            }
        
        # Données supplémentaires du web scraping
        if web_data:
            # Crédits
            if 'credits' in web_data:
                existing_credits = merged.get('credits', [])
                existing_credits.extend(web_data['credits'])
                merged['credits'] = existing_credits
            
            # Paroles
            if 'lyrics' in web_data:
                merged['lyrics'] = web_data['lyrics']
            
            # Métadonnées additionnelles
            for key, value in web_data.items():
                if key not in ['credits', 'lyrics']:
                    merged[f'web_{key}'] = value
        
        # Consolidation des crédits depuis l'API
        api_credits = []
        
        # Producteurs
        for producer in api_data.get('producer_artists', []):
            api_credits.append({
                'name': producer.get('name'),
                'role': 'Producer',
                'source': 'genius_api'
            })
        
        # Auteurs
        for writer in api_data.get('writer_artists', []):
            api_credits.append({
                'name': writer.get('name'),
                'role': 'Writer',
                'source': 'genius_api'
            })
        
        # Artistes invités
        for featured in api_data.get('featured_artists', []):
            api_credits.append({
                'name': featured.get('name'),
                'role': 'Featured Artist',
                'source': 'genius_api'
            })
        
        # Fusion des crédits
        all_credits = api_credits + merged.get('credits', [])
        if all_credits:
            merged['credits'] = self._deduplicate_credits(all_credits)
        
        # Données brutes pour debug
        merged['raw_data'] = {
            'api': api_data,
            'web': web_data
        }
        
        # Métadonnées d'extraction
        merged['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'extractor': self.extractor_type.value,
            'api_used': True,
            'web_scraped': bool(web_data)
        }
        
        return merged
    
    def _deduplicate_credits(self, credits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Supprime les doublons dans les crédits.
        
        Args:
            credits: Liste des crédits
            
        Returns:
            Liste sans doublons
        """
        seen = set()
        deduplicated = []
        
        for credit in credits:
            name = credit.get('name', '').strip()
            role = credit.get('role', '').strip()
            
            if not name or not role:
                continue
            
            # Clé unique basée sur le nom et le rôle
            key = (name.lower(), role.lower())
            
            if key not in seen:
                seen.add(key)
                deduplicated.append(credit)
        
        return deduplicated
    
    def _process_album_data(self, api_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite et nettoie les données d'un album.
        
        Args:
            api_data: Données brutes de l'API
            
        Returns:
            Dict contenant les données nettoyées
        """
        return {
            'genius_id': api_data.get('id'),
            'name': api_data.get('name'),
            'artist': api_data.get('artist', {}).get('name'),
            'artist_id': api_data.get('artist', {}).get('id'),
            'url': api_data.get('url'),
            'cover_art_url': api_data.get('cover_art_url'),
            'release_date': api_data.get('release_date_for_display'),
            'description': api_data.get('description', {}).get('plain') if api_data.get('description') else None,
            'track_count': len(api_data.get('song_performances', [])),
            'songs': [song.get('song') for song in api_data.get('song_performances', [])],
            'raw_data': api_data,
            'extraction_metadata': {
                'extracted_at': datetime.now().isoformat(),
                'extractor': self.extractor_type.value
            }
        }
    
    def _process_artist_data(self, api_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite et nettoie les données d'un artiste.
        
        Args:
            api_data: Données brutes de l'API
            
        Returns:
            Dict contenant les données nettoyées
        """
        return {
            'genius_id': api_data.get('id'),
            'name': api_data.get('name'),
            'url': api_data.get('url'),
            'image_url': api_data.get('image_url'),
            'header_image_url': api_data.get('header_image_url'),
            'description': api_data.get('description', {}).get('plain') if api_data.get('description') else None,
            'followers_count': api_data.get('followers_count'),
            'instagram_name': api_data.get('instagram_name'),
            'twitter_name': api_data.get('twitter_name'),
            'facebook_name': api_data.get('facebook_name'),
            'raw_data': api_data,
            'extraction_metadata': {
                'extracted_at': datetime.now().isoformat(),
                'extractor': self.extractor_type.value
            }
        }
    
    def _process_search_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Traite les résultats de recherche.
        
        Args:
            results: Résultats bruts de la recherche
            
        Returns:
            Liste des résultats nettoyés
        """
        processed = []
        
        for result in results:
            if not result:
                continue
            
            processed_result = {
                'genius_id': result.get('id'),
                'title': result.get('title'),
                'artist': result.get('primary_artist', {}).get('name'),
                'artist_id': result.get('primary_artist', {}).get('id'),
                'url': result.get('url'),
                'path': result.get('path'),
                'header_image': result.get('header_image_thumbnail_url')
            }

            processed.append(processed_result)
        return processed