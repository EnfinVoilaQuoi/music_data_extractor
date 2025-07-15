# extractors/web_scrapers/tunebat_scraper.py
import logging
import re
import time
import json
from typing import Dict, List, Optional, Any
from urllib.parse import quote, urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from ...core.exceptions import ExtractionError, RateLimitError
from ...core.cache import CacheManager
from ...core.rate_limiter import RateLimiter
from ...config.settings import settings
from ...utils.text_utils import clean_text, normalize_title


class TuneBatScraper:
    """
    Scraper spécialisé pour TuneBat.com.
    
    Responsabilités :
    - Extraction des données BPM et métadonnées audio
    - Analyse musicale avancée (énergie, dansabilité, etc.)
    - Informations de clé musicale et mode
    - Données spécialisées pour les DJs et producteurs
    """
    
    def __init__(self):
        self.base_url = "https://tunebat.com"
        self.search_url = f"{self.base_url}/Search"
        
        # Configuration
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Referer": "https://tunebat.com/",
            "Cache-Control": "max-age=0"
        }
        
        # Composants
        self.logger = logging.getLogger(f"{__name__}.TuneBatScraper")
        self.cache_manager = CacheManager()
        self.rate_limiter = RateLimiter(
            requests_per_period=settings.get('rate_limits.tunebat.requests_per_minute', 20),
            period_seconds=60
        )
        
        # Session HTTP
        self.session = self._create_session()
        
        # Configuration scraping
        self.config = {
            'delay_between_requests': 3,  # TuneBat est plus strict
            'max_search_results': 15,
            'timeout': 30,
            'enable_caching': True,
            'cache_duration_days': 7,
            'include_audio_features': True,  # Énergie, dansabilité, etc.
            'retry_on_fail': True
        }
        
        self.logger.info("TuneBatScraper initialisé")
    
    def _create_session(self) -> requests.Session:
        """Crée une session HTTP optimisée pour TuneBat"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=2,
            backoff_factor=3,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(self.headers)
        
        return session
    
    def search_track(self, artist_name: str, track_title: str) -> Optional[Dict[str, Any]]:
        """
        Recherche un morceau sur TuneBat.
        
        Args:
            artist_name: Nom de l'artiste
            track_title: Titre du morceau
        
        Returns:
            Dict contenant les données audio ou None si non trouvé
        """
        cache_key = f"tunebat_search_{artist_name}_{track_title}"
        
        # Vérifier le cache
        if self.config['enable_caching']:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.logger.debug(f"Cache hit pour {artist_name} - {track_title}")
                return cached_result
        
        try:
            # Effectuer la recherche
            search_results = self._perform_search(artist_name, track_title)
            
            if not search_results:
                self.logger.info(f"Aucun résultat trouvé sur TuneBat pour {artist_name} - {track_title}")
                return None
            
            # Trouver la meilleure correspondance
            best_match = self._find_best_match(search_results, artist_name, track_title)
            
            if not best_match:
                self.logger.info(f"Aucune correspondance fiable pour {artist_name} - {track_title}")
                return None
            
            # Extraire les détails complets
            track_details = self._extract_track_details(best_match['url'])
            
            if track_details:
                # Fusionner les données
                final_result = {**best_match, **track_details}
                
                # Ajouter des métadonnées
                final_result.update({
                    'source': 'tunebat',
                    'scraped_at': time.time(),
                    'search_query': f"{artist_name} {track_title}",
                    'confidence_score': self._calculate_confidence_score(final_result, artist_name, track_title)
                })
                
                # Mettre en cache
                if self.config['enable_caching']:
                    self.cache_manager.set(cache_key, final_result, expire_days=self.config['cache_duration_days'])
                
                self.logger.info(f"Données audio trouvées pour {artist_name} - {track_title}: {final_result.get('bpm', 'N/A')} BPM")
                return final_result
            
            return None
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche sur TuneBat pour {artist_name} - {track_title}: {e}")
            return None
    
    def _perform_search(self, artist_name: str, track_title: str) -> List[Dict[str, Any]]:
        """Effectue la recherche sur TuneBat"""
        self.rate_limiter.wait_if_needed()
        
        # Construction de la requête
        query = f"{artist_name} {track_title}".strip()
        
        try:
            # Pause anti-détection
            time.sleep(self.config['delay_between_requests'])
            
            # TuneBat utilise parfois des requêtes AJAX, essayer d'abord la recherche standard
            search_params = {'q': query}
            
            response = self.session.get(
                self.search_url,
                params=search_params,
                timeout=self.config['timeout']
            )
            response.raise_for_status()
            
            # Parser les résultats
            soup = BeautifulSoup(response.content, 'html.parser')
            results = self._parse_search_results(soup)
            
            # Si pas de résultats, essayer une approche alternative
            if not results and self.config['retry_on_fail']:
                results = self._alternative_search(artist_name, track_title)
            
            return results
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur réseau lors de la recherche TuneBat: {e}")
            return []
    
    def _parse_search_results(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse les résultats de recherche depuis la page HTML"""
        results = []
        
        try:
            # TuneBat utilise des structures spécifiques
            result_containers = soup.find_all('div', class_=re.compile(r'track|song|result|item'))
            
            if not result_containers:
                # Essayer d'autres sélecteurs
                result_containers = soup.find_all('a', href=re.compile(r'/Info/'))
            
            for container in result_containers[:self.config['max_search_results']]:
                result_data = self._extract_search_result_data(container)
                if result_data:
                    results.append(result_data)
            
            # Recherche par liens directs si les conteneurs ne fonctionnent pas
            if not results:
                results = self._extract_links_as_results(soup)
            
        except Exception as e:
            self.logger.warning(f"Erreur lors du parsing des résultats TuneBat: {e}")
        
        return results
    
    def _extract_search_result_data(self, container) -> Optional[Dict[str, Any]]:
        """Extrait les données d'un résultat de recherche"""
        try:
            result_data = {}
            
            # URL du track (TuneBat utilise /Info/)
            link_elem = container.find('a', href=re.compile(r'/Info/')) or container
            if link_elem and link_elem.get('href'):
                result_data['url'] = urljoin(self.base_url, link_elem['href'])
            else:
                return None
            
            # Titre et artiste
            text = clean_text(container.get_text())
            
            # TuneBat affiche souvent "Artist - Title"
            if ' - ' in text:
                parts = text.split(' - ', 1)
                result_data['artist'] = clean_text(parts[0])
                result_data['title'] = clean_text(parts[1])
            else:
                result_data['title'] = text
            
            # Chercher des infos BPM dans le texte
            bpm_match = re.search(r'(\d+)\s*BPM', text, re.IGNORECASE)
            if bpm_match:
                result_data['bpm'] = int(bpm_match.group(1