# extractors/web_scrapers/tunebat_scraper.py
import logging
import re
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from ...core.exceptions import ExtractionError, RateLimitError
from ...core.cache import CacheManager
from ...core.rate_limiter import RateLimiter
from ...config.settings import settings
from ...utils.text_utils import normalize_text

class TuneBatScraper:
    """
    Scraper spécialisé pour TuneBat.com.
    """
    def __init__(self):
        self.base_url = "https://tunebat.com"
        self.search_url = f"{self.base_url}/Search"
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
        self.logger = logging.getLogger(f"{__name__}.TuneBatScraper")
        self.cache_manager = CacheManager()
        self.rate_limiter = RateLimiter(
            requests_per_period=settings.get('rate_limits.tunebat.requests_per_minute', 20),
            period_seconds=60
        )
        self.session = self._create_session()
        self.config = {
            'delay_between_requests': 3,  # TuneBat est plus strict
            'max_search_results': 15,
            'timeout': 30,
            'enable_caching': True,
            'cache_duration_days': 7,
            'include_audio_features': True,
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
        """
        cache_key = f"tunebat_search_{artist_name}_{track_title}"
        if self.config['enable_caching']:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.logger.debug(f"Cache hit pour {artist_name} - {track_title}")
                return cached_result
        try:
            search_results = self._perform_search(artist_name, track_title)
            if not search_results:
                self.logger.info(f"Aucun résultat trouvé sur TuneBat pour {artist_name} - {track_title}")
                return None
            best_match = self._find_best_match(search_results, artist_name, track_title)
            if not best_match:
                self.logger.info(f"Aucune correspondance fiable pour {artist_name} - {track_title}")
                return None
            track_details = self._extract_track_details(best_match['url'])
            if track_details:
                final_result = {**best_match, **track_details}
                final_result.update({
                    'source': 'tunebat',
                    'scraped_at': time.time(),
                    'search_query': f"{artist_name} {track_title}",
                    'confidence_score': self._calculate_confidence_score(final_result, artist_name, track_title)
                })
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
        query = f"{artist_name} {track_title}".strip()
        try:
            time.sleep(self.config['delay_between_requests'])
            search_params = {'q': query}
            response = self.session.get(
                self.search_url,
                params=search_params,
                timeout=self.config['timeout']
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            results = self._parse_search_results(soup)
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
            result_containers = soup.find_all('div', class_=re.compile(r'track|song|result|item'))
            if not result_containers:
                result_containers = soup.find_all('a', href=re.compile(r'/Info/'))
            for container in result_containers[:self.config['max_search_results']]:
                result_data = self._extract_search_result_data(container)
                if result_data:
                    results.append(result_data)
            if not results:
                results = self._extract_links_as_results(soup)
        except Exception as e:
            self.logger.warning(f"Erreur lors du parsing des résultats TuneBat: {e}")
        return results

    def _extract_search_result_data(self, container) -> Optional[Dict[str, Any]]:
        """Extrait les données d'un résultat de recherche"""
        try:
            result_data = {}
            link_elem = container.find('a', href=re.compile(r'/Info/')) or container
            if link_elem and link_elem.get('href'):
                result_data['url'] = urljoin(self.base_url, link_elem['href'])
            else:
                return None
            text = normalize_text(container.get_text())
            if ' - ' in text:
                parts = text.split(' - ', 1)
                result_data['artist'] = normalize_text(parts[0])
                result_data['title'] = normalize_text(parts[1])
            else:
                result_data['title'] = text
            bpm_match = re.search(r'(\d+)\s*BPM', text, re.IGNORECASE)
            if bpm_match:
                result_data['bpm'] = int(bpm_match.group(1))
            return result_data if result_data.get('url') and result_data.get('title') else None
        except Exception as e:
            self.logger.debug(f"Erreur extraction résultat TuneBat: {e}")
            return None

    def _extract_links_as_results(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extraction basée sur les liens si parsing standard échoue"""
        results = []
        try:
            all_links = soup.find_all('a', href=re.compile(r'/Info/'))
            for link in all_links:
                href = link.get('href', '')
                text = normalize_text(link.get_text())
                if len(text) > 5 and href.startswith('/Info/'):
                    result_data = {
                        'url': urljoin(self.base_url, href),
                        'title': text,
                        'artist': 'Unknown'
                    }
                    results.append(result_data)
        except Exception as e:
            self.logger.debug(f"Erreur fallback links TuneBat: {e}")
        return results

    def _alternative_search(self, artist_name: str, track_title: str) -> List[Dict[str, Any]]:
        """Approche alternative si la recherche principale échoue (peut être enrichie)"""
        # Pour le moment, retourne []
        return []

    def _find_best_match(self, search_results: List[Dict[str, Any]], target_artist: str, target_title: str) -> Optional[Dict[str, Any]]:
        """Trouve la meilleure correspondance parmi les résultats"""
        if not search_results:
            return None
        target_artist_norm = normalize_text(target_artist)
        target_title_norm = normalize_text(target_title)
        best_match = None
        best_score = 0.0
        for result in search_results:
            score = 0.0
            title_similarity = self._calculate_similarity(normalize_text(result.get('title', '')), target_title_norm)
            score += title_similarity * 0.6
            artist_similarity = self._calculate_similarity(normalize_text(result.get('artist', '')), target_artist_norm)
            score += artist_similarity * 0.4
            if result.get('bpm'):
                score += 0.1
            if score > best_score:
                best_score = score
                best_match = result
        return best_match if best_score >= 0.5 else None

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcule la similarité entre deux textes"""
        if not text1 or not text2:
            return 0.0
        if text1 == text2:
            return 1.0
        words1 = set(text1.split())
        words2 = set(text2.split())
        if not words1 or not words2:
            return 0.0
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        return intersection / union if union > 0 else 0.0

    def _extract_track_details(self, track_url: str) -> Optional[Dict[str, Any]]:
        """Extrait les détails complets depuis la page d'un morceau TuneBat"""
        self.rate_limiter.wait_if_needed()
        try:
            time.sleep(self.config['delay_between_requests'])
            response = self.session.get(track_url, timeout=self.config['timeout'])
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            return self._parse_track_details(soup, track_url)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur lors de la récupération des détails de {track_url}: {e}")
            return None

    def _parse_track_details(self, soup: BeautifulSoup, track_url: str) -> Dict[str, Any]:
        """Parse les détails depuis la page HTML du morceau TuneBat"""
        details = {'url': track_url}
        try:
            # Titre et artiste
            title_elem = soup.find('h1') or soup.find('title')
            if title_elem:
                title_text = normalize_text(title_elem.get_text())
                details['page_title'] = title_text
                if ' - ' in title_text:
                    parts = title_text.split(' - ', 1)
                    details['artist'] = normalize_text(parts[0])
                    details['title'] = normalize_text(parts[1].replace(' | TuneBat', ''))
            # BPM
            bpm_elem = soup.find(text=re.compile(r'BPM', re.IGNORECASE))
            if bpm_elem:
                bpm_match = re.search(r'(\d+)\s*BPM', str(bpm_elem), re.IGNORECASE)
                if bpm_match:
                    details['bpm'] = int(bpm_match.group(1))
            # Key
            key_elem = soup.find(text=re.compile(r'Key', re.IGNORECASE))
            if key_elem:
                key_match = re.search(r'Key[:\s]*([A-G][#b]?\s*(?:major|minor|maj|min)?)', str(key_elem), re.IGNORECASE)
                if key_match:
                    details['key'] = normalize_text(key_match.group(1))
            # Energy, Danceability, etc.
            if self.config.get('include_audio_features'):
                energy_elem = soup.find(string=re.compile(r'Energy', re.IGNORECASE))
                if energy_elem:
                    value = self._extract_numeric_feature(energy_elem)
                    if value is not None:
                        details['energy'] = value
                dance_elem = soup.find(string=re.compile(r'Danceability', re.IGNORECASE))
                if dance_elem:
                    value = self._extract_numeric_feature(dance_elem)
                    if value is not None:
                        details['danceability'] = value
                valence_elem = soup.find(string=re.compile(r'Valence', re.IGNORECASE))
                if valence_elem:
                    value = self._extract_numeric_feature(valence_elem)
                    if value is not None:
                        details['valence'] = value
                acoustic_elem = soup.find(string=re.compile(r'Acousticness', re.IGNORECASE))
                if acoustic_elem:
                    value = self._extract_numeric_feature(acoustic_elem)
                    if value is not None:
                        details['acousticness'] = value
                instrumental_elem = soup.find(string=re.compile(r'Instrumentalness', re.IGNORECASE))
                if instrumental_elem:
                    value = self._extract_numeric_feature(instrumental_elem)
                    if value is not None:
                        details['instrumentalness'] = value
            # Durée
            duration_elem = soup.find(text=re.compile(r'Duration|Length', re.IGNORECASE))
            if duration_elem:
                duration_match = re.search(r'(\d+):(\d+)', str(duration_elem))
                if duration_match:
                    try:
                        minutes = int(duration_match.group(1))
                        seconds = int(duration_match.group(2))
                        details['duration_seconds'] = minutes * 60 + seconds
                        details['duration_formatted'] = f"{minutes}:{seconds:02d}"
                    except ValueError:
                        pass
        except Exception as e:
            self.logger.warning(f"Erreur lors du parsing des détails TuneBat: {e}")
        return details

    def _extract_numeric_feature(self, elem) -> Optional[float]:
        """Essaye d'extraire une valeur numérique à côté d'un label"""
        try:
            text = str(elem)
            match = re.search(r'(\d+(\.\d+)?)', text)
            if match:
                return float(match.group(1))
        except Exception:
            pass
        return None

    def _calculate_confidence_score(self, result: Dict[str, Any], target_artist: str, target_title: str) -> float:
        """Calcule un score de confiance pour le résultat"""
        score = 0.0
        if result.get('bpm'):
            score += 0.4
            bpm = result['bpm']
            if 60 <= bpm <= 200:
                score += 0.1
        if result.get('artist'):
            artist_similarity = self._calculate_similarity(
                normalize_text(result['artist']),
                normalize_text(target_artist)
            )
            score += artist_similarity * 0.2
        if result.get('title'):
            title_similarity = self._calculate_similarity(
                normalize_text(result['title']),
                normalize_text(target_title)
            )
            score += title_similarity * 0.2
        bonus_fields = ['key', 'energy', 'danceability', 'valence', 'acousticness', 'instrumentalness', 'duration_seconds']
        for field in bonus_fields:
            if result.get(field):
                score += 0.02
        return min(score, 1.0)

    def get_bulk_tracks(self, tracks_list: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Récupère les données BPM pour une liste de morceaux.
        """
        results = []
        for i, track_info in enumerate(tracks_list):
            artist = track_info.get('artist', '')
            title = track_info.get('title', '')
            if not artist or not title:
                self.logger.warning(f"Informations incomplètes pour le track {i}: {track_info}")
                continue
            try:
                result = self.search_track(artist, title)
                if result:
                    result['bulk_index'] = i
                    results.append(result)
                else:
                    results.append({
                        'bulk_index': i,
                        'artist': artist,
                        'title': title,
                        'found': False,
                        'source': 'tunebat'
                    })
                if i < len(tracks_list) - 1:
                    time.sleep(self.config['delay_between_requests'])
            except Exception as e:
                self.logger.error(f"Erreur pour le track {artist} - {title}: {e}")
                results.append({
                    'bulk_index': i,
                    'artist': artist,
                    'title': title,
                    'error': str(e),
                    'source': 'tunebat'
                })
        self.logger.info(f"Traitement terminé: {len([r for r in results if r.get('bpm')])} tracks avec BPM sur {len(tracks_list)}")
        return results

    def clear_cache(self):
        """Vide le cache TuneBat"""
        try:
            cache_keys = self.cache_manager.get_cache_keys("tunebat_*")
            for key in cache_keys:
                self.cache_manager.delete(key)
            self.logger.info(f"Cache TuneBat vidé: {len(cache_keys)} entrées supprimées")
        except Exception as e:
            self.logger.error(f"Erreur lors du vidage du cache: {e}")

    def get_cache_stats(self) -> Dict[str, int]:
        """Retourne les statistiques du cache"""
        try:
            cache_keys = self.cache_manager.get_cache_keys("tunebat_*")
            return {
                'total_cached_searches': len(cache_keys),
                'cache_enabled': self.config['enable_caching']
            }
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des stats du cache: {e}")
            return {'total_cached_searches': 0, 'cache_enabled': False}