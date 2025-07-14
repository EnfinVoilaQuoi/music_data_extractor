# extractors/web_scrapers/rapedia_scraper.py
import logging
import time
import re
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urljoin, quote
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ...core.exceptions import ScrapingError, PageNotFoundError, ElementNotFoundError
from ...core.rate_limiter import RateLimiter
from ...core.cache import CacheManager
from ...config.settings import settings
from ...utils.text_utils import clean_text, normalize_title, clean_artist_name
from ...models.enums import DataSource, CreditType, CreditCategory

class RapediaScraper:
    """
    Scraper spécialisé pour Rapedia.fr - source très fiable pour le rap français.
    
    Rapedia.fr contient des informations détaillées et vérifiées sur le rap français,
    incluant des crédits précis, des dates de sortie, et des collaborations.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.base_url = "https://rapedia.fr"
        self.search_url = f"{self.base_url}/rechercher"
        
        # Headers pour éviter la détection de bot
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        # Composants
        self.rate_limiter = RateLimiter(requests_per_period=10, period_seconds=60)  # Respectueux
        self.cache_manager = CacheManager()
        
        # Session HTTP avec retry
        self.session = self._create_session()
        
        # Patterns de reconnaissance spécifiques à Rapedia
        self.rapedia_patterns = {
            'producer_patterns': [
                r'(?:Produit par|Production[:\s]*|Prod[.\s]*:?\s*|Beat[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Réalisé par|Réalisation[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Instrumental[:\s]*)(.*?)(?:\n|$|;)'
            ],
            'featuring_patterns': [
                r'(?:feat\.?\s*|featuring\s*|avec\s*)(.*?)(?:\n|$|;)',
                r'(?:en duo avec|collaboration avec)(.*?)(?:\n|$|;)'
            ],
            'credit_patterns': [
                r'(?:Mix[:\s]*|Mixage[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Master[:\s]*|Mastering[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Enregistrement[:\s]*|Recording[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Paroles[:\s]*|Lyrics[:\s]*)(.*?)(?:\n|$|;)'
            ]
        }
        
        # Cache des pages visitées pour éviter les requêtes répétées
        self._visited_pages = set()
        
        self.logger.info("RapediaScraper initialisé")
    
    def _create_session(self) -> requests.Session:
        """Crée une session HTTP avec retry automatique"""
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
    
    def search_artist(self, artist_name: str) -> List[Dict[str, Any]]:
        """
        Recherche un artiste sur Rapedia.
        
        Args:
            artist_name: Nom de l'artiste à rechercher
            
        Returns:
            Liste des résultats de recherche avec URLs et métadonnées
        """
        cache_key = f"rapedia_search_{clean_artist_name(artist_name)}"
        
        # Vérification du cache
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            self.logger.debug(f"Résultats de recherche en cache pour {artist_name}")
            return cached_result
        
        try:
            self.logger.info(f"Recherche de '{artist_name}' sur Rapedia")
            
            # Respecter le rate limiting
            self.rate_limiter.wait_if_needed('rapedia')
            
            # Effectuer la recherche
            search_params = {
                'q': artist_name,
                'type': 'artiste'
            }
            
            response = self.session.get(
                self.search_url,
                params=search_params,
                timeout=30
            )
            
            if response.status_code == 404:
                self.logger.warning(f"Page de recherche non trouvée pour {artist_name}")
                return []
            
            response.raise_for_status()
            
            # Parser les résultats
            soup = BeautifulSoup(response.content, 'html.parser')
            results = self._parse_search_results(soup, artist_name)
            
            # Mise en cache
            self.cache_manager.set(cache_key, results)
            
            self.logger.info(f"Trouvé {len(results)} résultat(s) pour {artist_name}")
            return results
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur lors de la recherche sur Rapedia: {e}")
            raise ScrapingError(f"Erreur recherche Rapedia: {e}")
    
    def _parse_search_results(self, soup: BeautifulSoup, query: str) -> List[Dict[str, Any]]:
        """Parse les résultats de recherche"""
        results = []
        
        try:
            # Rechercher les éléments contenant les résultats
            # Note: Les sélecteurs peuvent changer, adapter selon la structure réelle
            result_items = soup.find_all(['div', 'article'], class_=re.compile(r'search-result|artist-result|result-item', re.I))
            
            if not result_items:
                # Tentative avec sélecteurs plus génériques
                result_items = soup.find_all('a', href=re.compile(r'/artiste/|/artist/'))
            
            for item in result_items:
                try:
                    # Extraction du nom et de l'URL
                    link = item.find('a') if item.name != 'a' else item
                    if not link:
                        continue
                    
                    url = link.get('href', '')
                    if url and not url.startswith('http'):
                        url = urljoin(self.base_url, url)
                    
                    # Extraction du nom de l'artiste
                    name_element = link.find(['h1', 'h2', 'h3', 'span', 'div'])
                    artist_name = clean_text(name_element.get_text()) if name_element else clean_text(link.get_text())
                    
                    if artist_name and url:
                        result = {
                            'name': artist_name,
                            'url': url,
                            'source': 'rapedia',
                            'match_score': self._calculate_match_score(artist_name, query)
                        }
                        
                        # Extraction d'informations supplémentaires si disponibles
                        desc_element = item.find(class_=re.compile(r'description|bio|summary', re.I))
                        if desc_element:
                            result['description'] = clean_text(desc_element.get_text())
                        
                        results.append(result)
                        
                except Exception as e:
                    self.logger.warning(f"Erreur parsing résultat de recherche: {e}")
                    continue
            
        except Exception as e:
            self.logger.error(f"Erreur lors du parsing des résultats de recherche: {e}")
        
        # Tri par score de correspondance
        results.sort(key=lambda x: x['match_score'], reverse=True)
        return results
    
    def scrape_artist_tracks(self, artist_url: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Scrape les morceaux d'un artiste depuis sa page Rapedia.
        
        Args:
            artist_url: URL de la page de l'artiste
            limit: Nombre maximum de morceaux à récupérer
            
        Returns:
            Liste des morceaux avec métadonnées et crédits
        """
        cache_key = f"rapedia_tracks_{self._url_to_cache_key(artist_url)}"
        
        # Vérification du cache
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            self.logger.debug(f"Morceaux en cache pour {artist_url}")
            return cached_result[:limit]
        
        try:
            self.logger.info(f"Scraping des morceaux depuis {artist_url}")
            
            if artist_url in self._visited_pages:
                self.logger.debug(f"Page déjà visitée: {artist_url}")
            
            # Respecter le rate limiting
            self.rate_limiter.wait_if_needed('rapedia')
            
            response = self.session.get(artist_url, timeout=30)
            
            if response.status_code == 404:
                raise PageNotFoundError(artist_url)
            
            response.raise_for_status()
            self._visited_pages.add(artist_url)
            
            # Parser la page
            soup = BeautifulSoup(response.content, 'html.parser')
            tracks = self._parse_artist_page(soup, artist_url)
            
            # Limitation du nombre de résultats
            limited_tracks = tracks[:limit]
            
            # Mise en cache
            self.cache_manager.set(cache_key, tracks)
            
            self.logger.info(f"Trouvé {len(limited_tracks)} morceau(x) sur Rapedia")
            return limited_tracks
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erreur lors du scraping de {artist_url}: {e}")
            raise ScrapingError(f"Erreur scraping page artiste: {e}")
    
    def _parse_artist_page(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Parse la page d'un artiste pour extraire les morceaux"""
        tracks = []
        
        try:
            # Rechercher les sections contenant les morceaux
            track_sections = soup.find_all(['div', 'article', 'section'], 
                                         class_=re.compile(r'track|song|morceau|titre', re.I))
            
            # Si pas de sections spécifiques, chercher des liens vers des morceaux
            if not track_sections:
                track_links = soup.find_all('a', href=re.compile(r'/titre/|/track/|/song/|/morceau/'))
                for link in track_links:
                    track_url = urljoin(base_url, link.get('href', ''))
                    track_title = clean_text(link.get_text())
                    
                    if track_title and track_url:
                        track_data = self.scrape_track_details(track_url)
                        if track_data:
                            tracks.append(track_data)
            else:
                # Parser chaque section de morceau
                for section in track_sections:
                    track_data = self._parse_track_section(section, base_url)
                    if track_data:
                        tracks.append(track_data)
            
        except Exception as e:
            self.logger.error(f"Erreur lors du parsing de la page artiste: {e}")
        
        return tracks
    
    def scrape_track_details(self, track_url: str) -> Optional[Dict[str, Any]]:
        """
        Scrape les détails d'un morceau spécifique.
        
        Args:
            track_url: URL de la page du morceau
            
        Returns:
            Dictionnaire avec les détails du morceau et crédits
        """
        cache_key = f"rapedia_track_{self._url_to_cache_key(track_url)}"
        
        # Vérification du cache
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        try:
            self.logger.debug(f"Scraping détails du morceau: {track_url}")
            
            # Respecter le rate limiting
            self.rate_limiter.wait_if_needed('rapedia')
            
            response = self.session.get(track_url, timeout=30)
            
            if response.status_code == 404:
                self.logger.warning(f"Page de morceau non trouvée: {track_url}")
                return None
            
            response.raise_for_status()
            
            # Parser la page
            soup = BeautifulSoup(response.content, 'html.parser')
            track_data = self._parse_track_page(soup, track_url)
            
            # Mise en cache si données trouvées
            if track_data:
                self.cache_manager.set(cache_key, track_data)
            
            return track_data
            
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Erreur lors du scraping du morceau {track_url}: {e}")
            return None
    
    def _parse_track_page(self, soup: BeautifulSoup, track_url: str) -> Optional[Dict[str, Any]]:
        """Parse une page de morceau pour extraire toutes les informations"""
        try:
            track_data = {
                'url': track_url,
                'source': DataSource.RAPEDIA.value,
                'scraped_at': datetime.now().isoformat(),
                'credits': [],
                'metadata': {}
            }
            
            # Extraction du titre
            title_selectors = ['h1', '.track-title', '.song-title', '.titre']
            title = self._extract_with_selectors(soup, title_selectors)
            if title:
                track_data['title'] = clean_text(title)
            
            # Extraction de l'artiste
            artist_selectors = ['.artist-name', '.artiste', '.artist', 'h2']
            artist = self._extract_with_selectors(soup, artist_selectors)
            if artist:
                track_data['artist'] = clean_text(artist)
            
            # Extraction de l'album
            album_selectors = ['.album-name', '.album', '.album-title']
            album = self._extract_with_selectors(soup, album_selectors)
            if album:
                track_data['album'] = clean_text(album)
            
            # Extraction de la date de sortie
            date_selectors = ['.release-date', '.date', '.sortie']
            release_date = self._extract_with_selectors(soup, date_selectors)
            if release_date:
                track_data['release_date'] = clean_text(release_date)
            
            # Extraction des crédits - c'est la partie la plus importante
            credits_section = soup.find(['div', 'section'], class_=re.compile(r'credit|prod|info', re.I))
            if credits_section:
                credits = self._extract_credits_from_section(credits_section)
                track_data['credits'].extend(credits)
            
            # Recherche de crédits dans le texte général
            main_content = soup.find(['div', 'article'], class_=re.compile(r'content|main|body', re.I))
            if main_content:
                text_credits = self._extract_credits_from_text(main_content.get_text())
                track_data['credits'].extend(text_credits)
            
            # Extraction des paroles si disponibles
            lyrics_section = soup.find(['div', 'section'], class_=re.compile(r'lyrics|paroles', re.I))
            if lyrics_section:
                lyrics = clean_text(lyrics_section.get_text())
                if lyrics and len(lyrics) > 50:  # Filtrer les faux positifs
                    track_data['lyrics'] = lyrics
            
            # Extraction d'autres métadonnées
            self._extract_additional_metadata(soup, track_data)
            
            return track_data if track_data.get('title') else None
            
        except Exception as e:
            self.logger.error(f"Erreur lors du parsing de la page de morceau: {e}")
            return None
    
    def _parse_track_section(self, section: BeautifulSoup, base_url: str) -> Optional[Dict[str, Any]]:
        """Parse une section contenant un morceau"""
        try:
            track_data = {
                'source': DataSource.RAPEDIA.value,
                'credits': []
            }
            
            # Extraction du titre depuis la section
            title_element = section.find(['h1', 'h2', 'h3', 'h4', 'a'])
            if title_element:
                track_data['title'] = clean_text(title_element.get_text())
                
                # Si c'est un lien, récupérer l'URL pour plus de détails
                if title_element.name == 'a':
                    track_url = urljoin(base_url, title_element.get('href', ''))
                    track_data['url'] = track_url
            
            # Extraction des crédits depuis la section
            credits = self._extract_credits_from_section(section)
            track_data['credits'].extend(credits)
            
            return track_data if track_data.get('title') else None
            
        except Exception as e:
            self.logger.warning(f"Erreur parsing section morceau: {e}")
            return None
    
    def _extract_credits_from_section(self, section: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extrait les crédits depuis une section HTML"""
        credits = []
        
        try:
            # Recherche de patterns dans le texte de la section
            section_text = section.get_text()
            text_credits = self._extract_credits_from_text(section_text)
            credits.extend(text_credits)
            
            # Recherche de listes de crédits structurées
            credit_lists = section.find_all(['ul', 'ol', 'dl'])
            for credit_list in credit_lists:
                list_items = credit_list.find_all(['li', 'dt', 'dd'])
                for item in list_items:
                    item_text = clean_text(item.get_text())
                    if item_text:
                        parsed_credits = self._parse_credit_text(item_text)
                        credits.extend(parsed_credits)
            
        except Exception as e:
            self.logger.warning(f"Erreur extraction crédits depuis section: {e}")
        
        return credits
    
    def _extract_credits_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extrait les crédits depuis un texte en utilisant les patterns"""
        credits = []
        
        try:
            # Application des patterns de reconnaissance
            for credit_type, patterns in self.rapedia_patterns.items():
                for pattern in patterns:
                    matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
                    
                    for match in matches:
                        credit_text = match.group(1).strip()
                        if credit_text:
                            parsed_credits = self._parse_credit_text(credit_text, credit_type)
                            credits.extend(parsed_credits)
            
            # Patterns génériques pour autres crédits
            generic_patterns = [
                r'(?:Crédits?[:\s]*)(.*?)(?:\n|$)',
                r'(?:Participants?[:\s]*)(.*?)(?:\n|$)',
                r'(?:Équipe[:\s]*)(.*?)(?:\n|$)'
            ]
            
            for pattern in generic_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    credit_text = match.group(1).strip()
                    if credit_text:
                        parsed_credits = self._parse_credit_text(credit_text)
                        credits.extend(parsed_credits)
            
        except Exception as e:
            self.logger.warning(f"Erreur extraction crédits depuis texte: {e}")
        
        return credits
    
    def _parse_credit_text(self, credit_text: str, credit_hint: str = None) -> List[Dict[str, Any]]:
        """Parse un texte de crédit pour extraire les personnes et rôles"""
        credits = []
        
        try:
            # Nettoyage du texte
            cleaned_text = credit_text.strip()
            
            # Séparation multiple par virgules, points-virgules, "et", "and"
            separators = [',', ';', ' et ', ' and ', ' & ']
            names = [cleaned_text]
            
            for separator in separators:
                new_names = []
                for name in names:
                    new_names.extend([n.strip() for n in name.split(separator)])
                names = new_names
            
            # Détermination du type de crédit
            credit_type, credit_category = self._determine_credit_type(credit_hint, cleaned_text)
            
            # Création des crédits pour chaque nom
            for name in names:
                name = name.strip()
                if name and len(name) > 1 and not self._is_excluded_name(name):
                    credit = {
                        'person_name': name,
                        'credit_type': credit_type.value if credit_type else 'other',
                        'credit_category': credit_category.value if credit_category else 'other',
                        'role_detail': cleaned_text,
                        'source': DataSource.RAPEDIA.value,
                        'confidence_score': 0.9,  # Rapedia est très fiable
                        'raw_text': credit_text
                    }
                    credits.append(credit)
            
        except Exception as e:
            self.logger.warning(f"Erreur parsing texte crédit '{credit_text}': {e}")
        
        return credits
    
    def _determine_credit_type(self, hint: str, text: str) -> tuple:
        """Détermine le type et la catégorie de crédit"""
        text_lower = text.lower()
        
        # Mapping basé sur les hints
        if hint:
            hint_mapping = {
                'producer_patterns': (CreditType.PRODUCER, CreditCategory.PRODUCER),
                'featuring_patterns': (CreditType.FEATURING, CreditCategory.FEATURING),
                'credit_patterns': (CreditType.OTHER, CreditCategory.TECHNICAL)
            }
            
            if hint in hint_mapping:
                return hint_mapping[hint]
        
        # Détection basée sur le contenu du texte
        if any(word in text_lower for word in ['produit', 'prod', 'beat', 'instrumental']):
            return CreditType.PRODUCER, CreditCategory.PRODUCER
        elif any(word in text_lower for word in ['feat', 'featuring', 'avec', 'duo']):
            return CreditType.FEATURING, CreditCategory.FEATURING
        elif any(word in text_lower for word in ['mix', 'mixage']):
            return CreditType.MIXING, CreditCategory.TECHNICAL
        elif any(word in text_lower for word in ['master', 'mastering']):
            return CreditType.MASTERING, CreditCategory.TECHNICAL
        elif any(word in text_lower for word in ['paroles', 'lyrics', 'texte']):
            return CreditType.LYRICIST, CreditCategory.COMPOSER
        elif any(word in text_lower for word in ['guitare', 'guitar']):
            return CreditType.GUITAR, CreditCategory.INSTRUMENT
        elif any(word in text_lower for word in ['piano', 'clavier']):
            return CreditType.PIANO, CreditCategory.INSTRUMENT
        elif any(word in text_lower for word in ['batterie', 'drums']):
            return CreditType.DRUMS, CreditCategory.INSTRUMENT
        elif any(word in text_lower for word in ['basse', 'bass']):
            return CreditType.BASS, CreditCategory.INSTRUMENT
        
        # Par défaut
        return CreditType.OTHER, CreditCategory.OTHER
    
    def _extract_with_selectors(self, soup: BeautifulSoup, selectors: List[str]) -> Optional[str]:
        """Extrait du texte en testant plusieurs sélecteurs CSS"""
        for selector in selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    text = clean_text(element.get_text())
                    if text:
                        return text
            except Exception:
                continue
        return None
    
    def _extract_additional_metadata(self, soup: BeautifulSoup, track_data: Dict[str, Any]):
        """Extrait des métadonnées additionnelles depuis la page"""
        try:
            # Extraction de l'année
            year_pattern = r'20\d{2}'
            page_text = soup.get_text()
            year_matches = re.findall(year_pattern, page_text)
            if year_matches:
                # Prendre l'année la plus récente trouvée
                track_data['release_year'] = max(int(year) for year in year_matches)
            
            # Extraction du genre si mentionné
            genre_keywords = ['rap', 'hip-hop', 'trap', 'drill', 'rnb', 'r&b']
            for keyword in genre_keywords:
                if keyword.lower() in page_text.lower():
                    track_data['genre'] = keyword
                    break
            
            # Extraction des liens externes (YouTube, Spotify, etc.)
            external_links = soup.find_all('a', href=re.compile(r'youtube|spotify|deezer|soundcloud'))
            if external_links:
                track_data['external_links'] = []
                for link in external_links:
                    href = link.get('href', '')
                    platform = self._identify_platform(href)
                    if platform:
                        track_data['external_links'].append({
                            'platform': platform,
                            'url': href
                        })
            
            # Extraction des images (pochettes)
            images = soup.find_all('img', src=re.compile(r'\.(jpg|jpeg|png|webp)', re.I))
            for img in images:
                src = img.get('src', '')
                alt = img.get('alt', '').lower()
                if any(keyword in alt for keyword in ['pochette', 'cover', 'album']):
                    track_data['cover_image'] = urljoin(track_data['url'], src)
                    break
            
        except Exception as e:
            self.logger.warning(f"Erreur extraction métadonnées additionnelles: {e}")
    
    def _identify_platform(self, url: str) -> Optional[str]:
        """Identifie la plateforme depuis une URL"""
        url_lower = url.lower()
        platforms = {
            'youtube': 'youtube',
            'spotify': 'spotify',
            'deezer': 'deezer',
            'soundcloud': 'soundcloud',
            'apple': 'apple_music',
            'bandcamp': 'bandcamp'
        }
        
        for keyword, platform in platforms.items():
            if keyword in url_lower:
                return platform
        
        return None
    
    def _calculate_match_score(self, found_name: str, query: str) -> float:
        """Calcule un score de correspondance entre le nom trouvé et la requête"""
        found_clean = clean_artist_name(found_name).lower()
        query_clean = clean_artist_name(query).lower()
        
        # Match exact
        if found_clean == query_clean:
            return 1.0
        
        # Match avec mots dans le bon ordre
        found_words = found_clean.split()
        query_words = query_clean.split()
        
        if len(query_words) == 1:
            # Recherche simple
            if query_words[0] in found_words:
                return 0.8
        else:
            # Recherche multi-mots
            matches = sum(1 for word in query_words if word in found_words)
            if matches == len(query_words):
                return 0.9
            elif matches > len(query_words) / 2:
                return 0.6
        
        # Similarité de caractères
        if found_clean in query_clean or query_clean in found_clean:
            return 0.4
        
        return 0.0
    
    def _is_excluded_name(self, name: str) -> bool:
        """Vérifie si un nom doit être exclu"""
        name_lower = name.lower()
        excluded_patterns = [
            'inconnu', 'unknown', 'various', 'divers', 'multiple',
            'tba', 'à déterminer', 'non renseigné', 'n/a'
        ]
        
        return any(pattern in name_lower for pattern in excluded_patterns)
    
    def _url_to_cache_key(self, url: str) -> str:
        """Convertit une URL en clé de cache valide"""
        # Garder seulement la partie significative de l'URL
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du scraper"""
        return {
            'pages_visited': len(self._visited_pages),
            'cache_size': len(self.cache_manager._cache) if hasattr(self.cache_manager, '_cache') else 0,
            'source': 'rapedia',
            'reliability_score': 0.95  # Très fiable pour le rap français
        }
    
    def clear_cache(self):
        """Vide le cache et remet à zéro les pages visitées"""
        if hasattr(self.cache_manager, 'clear_all'):
            self.cache_manager.clear_all()
        self._visited_pages.clear()
        self.logger.info("Cache Rapedia vidé")
    
    def test_connection(self) -> bool:
        """Teste la connexion à Rapedia"""
        try:
            response = self.session.get(self.base_url, timeout=10)
            return response.status_code == 200
        except:
            return False