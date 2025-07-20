# extractors/web_scrapers/songbpm_scraper.py
import logging
import re
import time
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
from ...utils.text_utils import normalize_text

class SongBPMScraper:
    """
    Scraper spécialisé pour SongBPM.com.
    """
    def __init__(self):
        self.base_url = "https://songbpm.com"
        self.search_url = f"{self.base_url}/search"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0"
        }
        self.logger = logging.getLogger(f"{__name__}.SongBPMScraper")
        self.cache_manager = CacheManager()
        self.rate_limiter = RateLimiter(
            requests_per_period=settings.get('rate_limits.songbpm.requests_per_minute', 30),
            period_seconds=60
        )
        self.session = self._create_session()
        self.config = {
            'delay_between_requests': settings.get('selenium.retry_failed_pages', 2),
            'max_search_results': settings.get('songbpm.max_search_results', 20),
            'timeout': settings.get('selenium.timeout', 30),
            'enable_caching': True,
            'cache_duration_days': 7
        }
        self.logger.info("SongBPMScraper initialisé")

    def _create_session(self) -> requests.Session:
        """Crée une session HTTP optimisée"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(self.headers)
        return session

    def search_track(self, artist_name: str, track_title: str) -> Optional[Dict[str, Any]]:
        """
        Recherche un morceau sur SongBPM.
        """
        cache_key = f"songbpm_search_{artist_name}_{track_title}"
        if self.config['enable_caching']:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.logger.debug(f"Cache hit pour {artist_name} - {track_title}")
                return cached_result
        try:
            search_results = self._perform_search(artist_name, track_title)
            if not search_results:
                self.logger.info(f"Aucun résultat trouvé pour {artist_name} - {track_title}")
                return None
            best_match = self._find_best_match(search_results, artist_name, track_title)
            if not best_match:
                self.logger.info(f"Aucune correspondance fiable pour {artist_name} - {track_title}")
                return None
            track_details = self._extract_track_details(best_match['url'])
            if track_details:
                final_result = {**best_match, **track_details}
                final_result.update({
                    'source': 'songbpm',
                    'scraped_at': time.time(),
                    'search_query': f"{artist_name} {track_title}",
                    'confidence_score': self._calculate_confidence_score(final_result, artist_name, track_title)
                })
                if self.config['enable_caching']:
                    self.cache_manager.set(cache_key, final_result, expire_days=self.config['cache_duration_days'])
                self.logger.info(f"Données BPM trouvées pour {artist_name} - {track_title}: {final_result.get('bpm', 'N/A')} BPM")
                return final_result
            return None
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche sur SongBPM pour {artist_name} - {track_title}: {e}")
            return None

    def _perform_search(self, artist_name: str, track_title: str) -> List[Dict[str, Any]]:
        """Effectue la recherche sur SongBPM"""
        self.rate_limiter.wait_if_needed()
        query = f"{artist_name} {track_title}".strip()
        search_params = {'q': query}
        try:
            time.sleep(self.config['delay_between_requests'])
            response = self.session.get(
                self.search_url,
                params=search_params,
                timeout=self.config['timeout']
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            return self._parse_search_results(soup)
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur réseau lors de la recherche: {e}")
            return []

    def _parse_search_results(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse les résultats de recherche depuis la page HTML"""
        results = []
        try:
            result_containers = soup.find_all('div', class_=re.compile(r'track|song|result'))
            if not result_containers:
                result_containers = soup.find_all('article') or soup.find_all('li', class_=re.compile(r'track|song'))
            for container in result_containers[:self.config['max_search_results']]:
                result_data = self._extract_search_result_data(container)
                if result_data:
                    results.append(result_data)
            if not results:
                results = self._fallback_search_parsing(soup)
        except Exception as e:
            self.logger.warning(f"Erreur lors du parsing des résultats de recherche: {e}")
        return results

    def _extract_search_result_data(self, container) -> Optional[Dict[str, Any]]:
        """Extrait les données d'un résultat de recherche"""
        try:
            result_data = {}
            title_elem = container.find(['h2', 'h3', 'h4']) or container.find('a', class_=re.compile(r'title|name|track'))
            if title_elem:
                result_data['title'] = normalize_text(title_elem.get_text())
                link = title_elem.find('a') or title_elem
                if link and link.get('href'):
                    result_data['url'] = urljoin(self.base_url, link['href'])
            artist_elem = container.find(text=re.compile(r'by\s+', re.IGNORECASE)) or \
                container.find('span', class_=re.compile(r'artist|by'))
            if artist_elem:
                if hasattr(artist_elem, 'get_text'):
                    artist_text = artist_elem.get_text()
                else:
                    artist_text = str(artist_elem)
                result_data['artist'] = normalize_text(artist_text.replace('by', '').strip())
            bpm_elem = container.find(text=re.compile(r'\d+\s*bpm', re.IGNORECASE))
            if bpm_elem:
                bpm_match = re.search(r'(\d+)', str(bpm_elem))
                if bpm_match:
                    result_data['bpm'] = int(bpm_match.group(1))
            key_elem = container.find(text=re.compile(r'[A-G][#b]?\s*(major|minor|maj|min)?', re.IGNORECASE))
            if key_elem:
                key_match = re.search(r'([A-G][#b]?\s*(?:major|minor|maj|min)?)', str(key_elem), re.IGNORECASE)
                if key_match:
                    result_data['key'] = key_match.group(1).strip()
            return result_data if result_data.get('title') and result_data.get('url') else None
        except Exception as e:
            self.logger.debug(f"Erreur lors de l'extraction d'un résultat: {e}")
            return None

    def _fallback_search_parsing(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parsing de fallback si les sélecteurs principaux échouent"""
        results = []
        try:
            all_links = soup.find_all('a', href=re.compile(r'/[^/]+/[^/]+/?'))
            for link in all_links[:10]:
                href = link.get('href', '')
                text = normalize_text(link.get_text())
                if len(text) > 5 and href.startswith('/'):
                    result_data = {
                        'title': text,
                        'url': urljoin(self.base_url, href),
                        'artist': 'Unknown'
                    }
                    results.append(result_data)
        except Exception as e:
            self.logger.debug(f"Erreur dans le fallback parsing: {e}")
        return results

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
            result_title_norm = normalize_text(result.get('title', ''))
            title_similarity = self._calculate_similarity(result_title_norm, target_title_norm)
            score += title_similarity * 0.6
            result_artist_norm = normalize_text(result.get('artist', ''))
            artist_similarity = self._calculate_similarity(result_artist_norm, target_artist_norm)
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
        """Extrait les détails complets depuis la page d'un morceau"""
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
        """Parse les détails depuis la page HTML du morceau"""
        details = {'url': track_url}
        try:
            title_elem = soup.find('h1') or soup.find('title')
            if title_elem:
                title_text = normalize_text(title_elem.get_text())
                details['page_title'] = title_text
                if ' - ' in title_text:
                    parts = title_text.split(' - ', 1)
                    details['artist'] = normalize_text(parts[0])
                    details['title'] = normalize_text(parts[1].replace(' | SongBPM', ''))
            bpm_patterns = [
                r'(?:BPM|Tempo):\s*(\d+)',
                r'(\d+)\s*BPM',
                r'Beats Per Minute.*?(\d+)',
                r'<strong[^>]*>(\d+)</strong>\s*(?:BPM|bpm)'
            ]
            page_text = str(soup)
            for pattern in bpm_patterns:
                bpm_match = re.search(pattern, page_text, re.IGNORECASE)
                if bpm_match:
                    try:
                        details['bpm'] = int(bpm_match.group(1))
                        break
                    except ValueError:
                        continue
            key_patterns = [
                r'(?:Key|Tonalité):\s*([A-G][#b]?\s*(?:major|minor|maj|min)?)',
                r'Musical Key.*?([A-G][#b]?\s*(?:major|minor|maj|min)?)',
                r'<strong[^>]*>([A-G][#b]?\s*(?:major|minor|maj|min)?)</strong>'
            ]
            for pattern in key_patterns:
                key_match = re.search(pattern, page_text, re.IGNORECASE)
                if key_match:
                    details['key'] = normalize_text(key_match.group(1))
                    break
            duration_patterns = [
                r'(?:Duration|Length):\s*(\d+):(\d+)',
                r'(\d+):(\d+)\s*(?:minutes?|mins?)',
                r'Track Length.*?(\d+):(\d+)'
            ]
            for pattern in duration_patterns:
                duration_match = re.search(pattern, page_text, re.IGNORECASE)
                if duration_match:
                    try:
                        minutes = int(duration_match.group(1))
                        seconds = int(duration_match.group(2))
                        details['duration_seconds'] = minutes * 60 + seconds
                        details['duration_formatted'] = f"{minutes}:{seconds:02d}"
                        break
                    except ValueError:
                        continue
            genre_elem = soup.find(text=re.compile(r'genre|style', re.IGNORECASE))
            if genre_elem:
                parent = genre_elem.parent if hasattr(genre_elem, 'parent') else None
                if parent:
                    genre_text = normalize_text(parent.get_text())
                    genre_match = re.search(r'(?:genre|style)[:\s]*([^,\n]+)', genre_text, re.IGNORECASE)
                    if genre_match:
                        details['genre'] = normalize_text(genre_match.group(1))
            album_elem = soup.find(text=re.compile(r'album', re.IGNORECASE))
            if album_elem:
                parent = album_elem.parent if hasattr(album_elem, 'parent') else None
                if parent:
                    album_text = normalize_text(parent.get_text())
                    album_match = re.search(r'album[:\s]*([^,\n]+)', album_text, re.IGNORECASE)
                    if album_match:
                        details['album'] = normalize_text(album_match.group(1))
            year_match = re.search(r'(?:year|released?)[:\s]*(\d{4})', page_text, re.IGNORECASE)
            if year_match:
                details['release_year'] = int(year_match.group(1))
            label_match = re.search(r'(?:label|record label)[:\s]*([^,\n]+)', page_text, re.IGNORECASE)
            if label_match:
                details['label'] = normalize_text(label_match.group(1))
        except Exception as e:
            self.logger.warning(f"Erreur lors du parsing des détails: {e}")
        return details

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
        bonus_fields = ['key', 'duration_seconds', 'genre', 'album', 'release_year']
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
                        'source': 'songbpm'
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
                    'source': 'songbpm'
                })
        self.logger.info(f"Traitement terminé: {len([r for r in results if r.get('bpm')])} tracks avec BPM sur {len(tracks_list)}")
        return results

    def clear_cache(self):
        """Vide le cache SongBPM"""
        try:
            cache_keys = self.cache_manager.get_cache_keys("songbpm_*")
            for key in cache_keys:
                self.cache_manager.delete(key)
            self.logger.info(f"Cache SongBPM vidé: {len(cache_keys)} entrées supprimées")
        except Exception as e:
            self.logger.error(f"Erreur lors du vidage du cache: {e}")

    def get_cache_stats(self) -> Dict[str, int]:
        """Retourne les statistiques du cache"""
        try:
            cache_keys = self.cache_manager.get_cache_keys("songbpm_*")
            return {
                'total_cached_searches': len(cache_keys),
                'cache_enabled': self.config['enable_caching']
            }
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des stats du cache: {e}")
            return {'total_cached_searches': 0, 'cache_enabled': False}