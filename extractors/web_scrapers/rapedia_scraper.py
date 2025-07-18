# extractors/web_scrapers/rapedia_scraper.py
"""
Scraper optimisé pour Rapedia.fr - source très fiable pour le rap français.
Version optimisée avec cache intelligent, parsing avancé et gestion d'erreurs robuste.
"""

import logging
import time
import re
from functools import lru_cache
from typing import Dict, List, Optional, Any, Union, Tuple
from urllib.parse import urljoin, quote
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Imports absolus
from core.exceptions import ScrapingError, PageNotFoundError, ElementNotFoundError
from core.rate_limiter import RateLimiter
from core.cache import CacheManager
from config.settings import settings
from utils.text_utils import normalize_text, clean_artist_name
from models.enums import DataSource, CreditType, CreditCategory


class RapediaScraper:
    """
    Scraper spécialisé optimisé pour Rapedia.fr - source très fiable pour le rap français.
    
    Rapedia.fr contient des informations détaillées et vérifiées sur le rap français,
    incluant des crédits précis, des dates de sortie, et des collaborations.
    
    Fonctionnalités optimisées :
    - Cache intelligent pour éviter les requêtes répétées
    - Parsing avancé avec patterns spécifiques au rap français
    - Rate limiting respectueux du site
    - Gestion robuste des erreurs avec retry
    - Extraction complète des métadonnées
    - Déduplication intelligente des résultats
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration optimisée
        self.base_url = "https://rapedia.fr"
        self.search_url = f"{self.base_url}/rechercher"
        
        # Headers pour éviter la détection de bot
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none"
        }
        
        # Composants optimisés
        self.rate_limiter = RateLimiter(requests_per_period=15, period_seconds=60)  # Respectueux
        self.cache_manager = CacheManager() if CacheManager else None
        
        # Session HTTP optimisée avec retry
        self.session = self._create_optimized_session()
        
        # Patterns de reconnaissance spécifiques à Rapedia et au rap français
        self.rapedia_patterns = self._compile_rapedia_patterns()
        
        # Cache pour éviter les recalculs
        self._visited_pages = set()
        self._artist_cache = {}
        self._pattern_cache = {}
        
        # Statistiques de performance
        self.stats = {
            'searches_performed': 0,
            'pages_scraped': 0,
            'tracks_found': 0,
            'credits_extracted': 0,
            'cache_hits': 0,
            'failed_requests': 0,
            'total_time_spent': 0.0
        }
        
        self.logger.info("✅ RapediaScraper optimisé initialisé - spécialisé rap français")
    
    def _create_optimized_session(self) -> requests.Session:
        """Crée une session HTTP optimisée avec retry et timeout"""
        session = requests.Session()
        
        # Configuration du retry avec backoff exponentiel
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update(self.headers)
        session.timeout = 30
        
        return session
    
    @lru_cache(maxsize=1)
    def _compile_rapedia_patterns(self) -> Dict[str, List[re.Pattern]]:
        """
        Compile les patterns de reconnaissance spécifiques à Rapedia avec cache.
        
        Returns:
            Dictionnaire des patterns compilés
        """
        patterns = {
            'producer_patterns': [
                r'(?:Produit par|Production[:\s]*|Prod[.\s]*:?\s*|Beat[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Réalisé par|Réalisation[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Instrumental[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Beatmaker[:\s]*)(.*?)(?:\n|$|;)'
            ],
            'featuring_patterns': [
                r'(?:feat\.?\s*|featuring\s*|avec\s*)(.*?)(?:\n|$|;)',
                r'(?:en duo avec|collaboration avec)(.*?)(?:\n|$|;)',
                r'(?:invité[:\s]*)(.*?)(?:\n|$|;)'
            ],
            'engineering_patterns': [
                r'(?:Mix[:\s]*|Mixage[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Master[:\s]*|Mastering[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Enregistrement[:\s]*|Recording[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Prise de son[:\s]*)(.*?)(?:\n|$|;)'
            ],
            'writing_patterns': [
                r'(?:Paroles[:\s]*|Lyrics[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Texte[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Écrit par[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Compositeur[:\s]*)(.*?)(?:\n|$|;)'
            ],
            'label_patterns': [
                r'(?:Label[:\s]*|Maison de disque[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Distribué par[:\s]*)(.*?)(?:\n|$|;)'
            ],
            'date_patterns': [
                r'(?:Sortie[:\s]*|Date de sortie[:\s]*)(.*?)(?:\n|$|;)',
                r'(?:Publié le[:\s]*)(.*?)(?:\n|$|;)',
                r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})',
                r'(\d{4})'
            ]
        }
        
        # Compilation avec cache
        compiled_patterns = {}
        for category, pattern_list in patterns.items():
            compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in pattern_list
            ]
        
        return compiled_patterns
    
    def search_artist_tracks(self, artist_name: str, max_tracks: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Recherche les morceaux d'un artiste sur Rapedia avec optimisations.
        
        Args:
            artist_name: Nom de l'artiste à rechercher
            max_tracks: Nombre maximum de morceaux à récupérer
            
        Returns:
            Liste des morceaux trouvés avec métadonnées complètes
        """
        start_time = time.time()
        
        try:
            normalized_artist = clean_artist_name(artist_name)
            self.logger.info(f"🔍 Recherche Rapedia pour: {normalized_artist}")
            
            # Vérification du cache
            cache_key = f"rapedia_search_{normalized_artist}_{max_tracks}"
            
            if self.cache_manager:
                cached_result = self.cache_manager.get(cache_key)
                if cached_result:
                    self.stats['cache_hits'] += 1
                    self.logger.info(f"💾 Cache hit Rapedia pour {normalized_artist}")
                    return cached_result
            
            # Rate limiting
            if self.rate_limiter:
                self.rate_limiter.wait_if_needed()
            
            # Recherche sur Rapedia
            search_results = self._perform_search(normalized_artist)
            
            if not search_results:
                self.logger.warning(f"⚠️ Aucun résultat trouvé pour '{artist_name}' sur Rapedia")
                return []
            
            # Extraction détaillée des morceaux
            all_tracks = []
            
            for result in search_results:
                try:
                    if result.get('type') == 'artist':
                        # Page d'artiste - extraire tous les morceaux
                        artist_tracks = self._extract_tracks_from_artist_page(result['url'])
                        all_tracks.extend(artist_tracks)
                    elif result.get('type') == 'track':
                        # Morceau individuel
                        track_data = self._extract_track_details(result['url'])
                        if track_data:
                            all_tracks.append(track_data)
                    
                    # Limiter si nécessaire
                    if max_tracks and len(all_tracks) >= max_tracks:
                        all_tracks = all_tracks[:max_tracks]
                        break
                        
                except Exception as e:
                    self.logger.warning(f"⚠️ Erreur extraction résultat {result.get('url', 'unknown')}: {e}")
                    continue
            
            # Déduplication et enrichissement
            final_tracks = self._deduplicate_and_enrich_tracks(all_tracks, normalized_artist)
            
            # Mise en cache
            if self.cache_manager and final_tracks:
                self.cache_manager.set(cache_key, final_tracks, expire_hours=12)
            
            # Mise à jour des statistiques
            self.stats['searches_performed'] += 1
            self.stats['tracks_found'] += len(final_tracks)
            self.stats['total_time_spent'] += time.time() - start_time
            
            self.logger.info(f"✅ Rapedia: {len(final_tracks)} morceaux trouvés en {time.time() - start_time:.2f}s")
            
            return final_tracks
            
        except Exception as e:
            self.stats['failed_requests'] += 1
            self.logger.error(f"❌ Erreur recherche Rapedia pour {artist_name}: {e}")
            return []
    
    def _perform_search(self, artist_name: str) -> List[Dict[str, Any]]:
        """
        Effectue la recherche sur Rapedia avec parsing intelligent.
        
        Args:
            artist_name: Nom de l'artiste
            
        Returns:
            Liste des résultats de recherche
        """
        try:
            # Préparation de la requête de recherche
            search_params = {
                'q': artist_name,
                'type': 'all'  # Rechercher artistes et morceaux
            }
            
            response = self.session.get(self.search_url, params=search_params)
            response.raise_for_status()
            
            # Parsing du HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extraction des résultats
            results = self._parse_search_results(soup, artist_name)
            
            self.logger.debug(f"📊 Trouvé {len(results)} résultat(s) pour {artist_name}")
            return results
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Erreur lors de la recherche sur Rapedia: {e}")
            raise ScrapingError(f"Erreur recherche Rapedia: {e}")
    
    def _parse_search_results(self, soup: BeautifulSoup, query: str) -> List[Dict[str, Any]]:
        """Parse les résultats de recherche avec sélecteurs adaptatifs"""
        results = []
        
        try:
            # Sélecteurs multiples pour les résultats (structure adaptative)
            result_selectors = [
                '.search-result',
                '.result-item',
                '[class*="result"]',
                'article',
                '.artist-item',
                '.track-item'
            ]
            
            result_items = []
            for selector in result_selectors:
                items = soup.select(selector)
                if items:
                    result_items = items
                    break
            
            # Fallback: recherche de liens d'artistes/morceaux
            if not result_items:
                result_items = soup.find_all('a', href=re.compile(r'/(artiste|artist|track|morceau)/'))
            
            for item in result_items:
                try:
                    result_data = self._extract_search_result_data(item, query)
                    if result_data:
                        results.append(result_data)
                        
                except Exception as e:
                    self.logger.debug(f"Erreur extraction item: {e}")
                    continue
            
            # Déduplication par URL
            seen_urls = set()
            unique_results = []
            for result in results:
                url = result.get('url')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(result)
            
            return unique_results
            
        except Exception as e:
            self.logger.error(f"❌ Erreur parsing résultats recherche: {e}")
            return []
    
    def _extract_search_result_data(self, item, query: str) -> Optional[Dict[str, Any]]:
        """Extrait les données d'un résultat de recherche"""
        try:
            # Extraction du lien
            link = item.find('a') if item.name != 'a' else item
            if not link:
                return None
            
            url = link.get('href', '')
            if url and not url.startswith('http'):
                url = urljoin(self.base_url, url)
            
            if not url:
                return None
            
            # Extraction du nom/titre
            title_element = (
                link.find(['h1', 'h2', 'h3', 'h4']) or
                link.find(class_=re.compile(r'title|name')) or
                link
            )
            
            title = self._extract_text_safe(title_element)
            if not title:
                return None
            
            # Détermination du type (artiste ou morceau)
            result_type = 'track'  # Défaut
            if any(indicator in url.lower() for indicator in ['/artiste/', '/artist/']):
                result_type = 'artist'
            elif any(indicator in url.lower() for indicator in ['/track/', '/morceau/', '/song/']):
                result_type = 'track'
            
            # Vérification de pertinence
            if not self._is_relevant_result(title, query):
                return None
            
            # Extraction de métadonnées additionnelles
            metadata = self._extract_result_metadata(item)
            
            return {
                'title': title.strip(),
                'url': url,
                'type': result_type,
                'relevance_score': self._calculate_relevance_score(title, query),
                **metadata
            }
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction résultat: {e}")
            return None
    
    def _extract_tracks_from_artist_page(self, artist_url: str) -> List[Dict[str, Any]]:
        """
        Extrait tous les morceaux depuis une page d'artiste Rapedia.
        
        Args:
            artist_url: URL de la page artiste
            
        Returns:
            Liste des morceaux avec métadonnées
        """
        if artist_url in self._visited_pages:
            return []
        
        self._visited_pages.add(artist_url)
        
        try:
            if self.rate_limiter:
                self.rate_limiter.wait_if_needed()
            
            response = self.session.get(artist_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            tracks = []
            
            # Sélecteurs pour les listes de morceaux
            track_selectors = [
                '.track-list .track-item',
                '.discography .track',
                '[class*="track"]',
                '.song-list .song',
                'ul li a[href*="/track/"]',
                'ul li a[href*="/morceau/"]'
            ]
            
            for selector in track_selectors:
                track_elements = soup.select(selector)
                
                for element in track_elements:
                    try:
                        track_data = self._extract_track_from_element(element, artist_url)
                        if track_data:
                            tracks.append(track_data)
                    except Exception as e:
                        self.logger.debug(f"Erreur extraction track element: {e}")
                        continue
            
            # Si peu de morceaux trouvés, essayer méthode alternative
            if len(tracks) < 3:
                alternative_tracks = self._extract_tracks_alternative_method(soup, artist_url)
                tracks.extend(alternative_tracks)
            
            self.stats['pages_scraped'] += 1
            self.logger.debug(f"📀 {len(tracks)} morceaux extraits de la page artiste")
            
            return tracks
            
        except Exception as e:
            self.logger.error(f"❌ Erreur extraction page artiste {artist_url}: {e}")
            return []
    
    def _extract_track_details(self, track_url: str) -> Optional[Dict[str, Any]]:
        """
        Extrait les détails complets d'un morceau depuis sa page Rapedia.
        
        Args:
            track_url: URL de la page du morceau
            
        Returns:
            Détails du morceau avec crédits complets
        """
        if track_url in self._visited_pages:
            return None
        
        self._visited_pages.add(track_url)
        
        try:
            if self.rate_limiter:
                self.rate_limiter.wait_if_needed()
            
            response = self.session.get(track_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extraction des informations de base
            track_data = {
                'url': track_url,
                'data_source': DataSource.RAPEDIA.value,
                'extracted_at': datetime.now().isoformat()
            }
            
            # Titre du morceau
            title_selectors = ['h1', '.track-title', '.song-title', '[class*="title"]']
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    track_data['title'] = self._extract_text_safe(title_elem)
                    break
            
            # Artiste principal
            artist_selectors = ['.artist-name', '.main-artist', 'h2', '[class*="artist"]']
            for selector in artist_selectors:
                artist_elem = soup.select_one(selector)
                if artist_elem:
                    track_data['artist_name'] = self._extract_text_safe(artist_elem)
                    break
            
            # Extraction des crédits complets
            credits = self._extract_credits_from_page(soup)
            track_data['credits'] = credits
            self.stats['credits_extracted'] += len(credits)
            
            # Métadonnées additionnelles
            metadata = self._extract_track_metadata(soup)
            track_data.update(metadata)
            
            self.stats['pages_scraped'] += 1
            
            return track_data
            
        except Exception as e:
            self.logger.error(f"❌ Erreur extraction détails track {track_url}: {e}")
            return None
    
    def _extract_credits_from_page(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extrait les crédits depuis une page avec patterns spécialisés"""
        credits = []
        
        try:
            # Recherche des sections de crédits
            credit_sections = soup.find_all(['div', 'section', 'article'], 
                                          class_=re.compile(r'credit|production|info', re.I))
            
            if not credit_sections:
                # Fallback: toute la page
                credit_sections = [soup]
            
            for section in credit_sections:
                section_credits = self._extract_credits_from_section(section)
                credits.extend(section_credits)
            
            # Déduplication
            credits = self._deduplicate_credits(credits)
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction crédits: {e}")
        
        return credits
    
    def _extract_credits_from_section(self, section) -> List[Dict[str, Any]]:
        """Extrait les crédits depuis une section HTML avec patterns français"""
        credits = []
        
        try:
            # Récupération du texte de la section
            section_text = self._extract_text_safe(section)
            
            if not section_text:
                return credits
            
            # Application des patterns de reconnaissance
            for category, patterns in self.rapedia_patterns.items():
                for pattern in patterns:
                    matches = pattern.finditer(section_text)
                    
                    for match in matches:
                        try:
                            credit_text = match.group(1).strip() if match.groups() else match.group(0)
                            
                            if credit_text:
                                parsed_credits = self._parse_credit_text(credit_text, category)
                                credits.extend(parsed_credits)
                                
                        except Exception as e:
                            self.logger.debug(f"Erreur parsing match: {e}")
                            continue
            
            # Recherche de listes de crédits structurées
            credit_lists = section.find_all(['ul', 'ol', 'dl'])
            for credit_list in credit_lists:
                list_items = credit_list.find_all(['li', 'dt', 'dd'])
                for item in list_items:
                    item_text = self._extract_text_safe(item)
                    if item_text:
                        parsed_credits = self._parse_credit_text(item_text)
                        credits.extend(parsed_credits)
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction crédits section: {e}")
        
        return credits
    
    @lru_cache(maxsize=256)
    def _parse_credit_text(self, text: str, category: str = None) -> List[Dict[str, Any]]:
        """Parse un texte de crédit avec cache pour optimisation"""
        credits = []
        
        try:
            if not text or len(text.strip()) < 2:
                return credits
            
            # Nettoyage du texte
            cleaned_text = text.strip()
            
            # Séparation des noms multiples
            separators = [',', ';', '&', ' et ', ' and ', '\n', ' / ']
            names = [cleaned_text]
            
            for sep in separators:
                new_names = []
                for name in names:
                    new_names.extend([n.strip() for n in name.split(sep) if n.strip()])
                names = new_names
            
            # Création des crédits
            for name in names:
                if len(name) > 1 and self._is_valid_credit_name(name):
                    credit_type = self._infer_credit_type_from_category(category) if category else 'Contributor'
                    
                    credit = {
                        'credit_type': credit_type,
                        'credit_category': self._map_category_to_enum(category),
                        'person_name': name,
                        'source_text': text,
                        'data_source': DataSource.RAPEDIA.value,
                        'extraction_method': 'pattern_parsing'
                    }
                    credits.append(credit)
            
        except Exception as e:
            self.logger.debug(f"Erreur parse credit text: {e}")
        
        return credits
    
    @lru_cache(maxsize=128)
    def _infer_credit_type_from_category(self, category: str) -> str:
        """Infère le type de crédit depuis la catégorie avec cache"""
        category_mapping = {
            'producer_patterns': 'Producer',
            'featuring_patterns': 'Featured Artist',
            'engineering_patterns': 'Engineer',
            'writing_patterns': 'Songwriter',
            'label_patterns': 'Label',
            'date_patterns': 'Release Info'
        }
        
        return category_mapping.get(category, 'Contributor')
    
    @lru_cache(maxsize=64)
    def _map_category_to_enum(self, category: str) -> str:
        """Mappe une catégorie vers un enum de crédit avec cache"""
        if not category:
            return CreditCategory.OTHER.value
        
        if 'producer' in category.lower():
            return CreditCategory.PRODUCTION.value
        elif 'writing' in category.lower():
            return CreditCategory.WRITING.value
        elif 'engineering' in category.lower():
            return CreditCategory.ENGINEERING.value
        elif 'featuring' in category.lower():
            return CreditCategory.PERFORMANCE.value
        
        return CreditCategory.OTHER.value
    
    def _is_valid_credit_name(self, name: str) -> bool:
        """Valide si un nom est un crédit valide"""
        if not name or len(name.strip()) < 2:
            return False
        
        # Filtrer les mots-clés non pertinents
        excluded_keywords = [
            'produit', 'par', 'mixé', 'masterisé', 'écrit', 'featuring',
            'feat', 'avec', 'et', 'and', 'the', 'le', 'la', 'les',
            'de', 'du', 'des', 'en', 'sur', 'pour', 'dans'
        ]
        
        name_lower = name.lower().strip()
        
        # Exclure si c'est uniquement un mot-clé
        if name_lower in excluded_keywords:
            return False
        
        # Exclure les phrases trop longues (probablement pas un nom)
        if len(name.split()) > 4:
            return False
        
        # Doit contenir au moins une lettre
        if not any(c.isalpha() for c in name):
            return False
        
        return True
    
    def _extract_track_metadata(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extrait les métadonnées additionnelles d'une track"""
        metadata = {}
        
        try:
            # Date de sortie
            date_selectors = ['.release-date', '.date', '[class*="date"]']
            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date_text = self._extract_text_safe(date_elem)
                    if date_text:
                        metadata['release_date'] = date_text
                        break
            
            # Album
            album_selectors = ['.album-name', '.album-title', '[class*="album"]']
            for selector in album_selectors:
                album_elem = soup.select_one(selector)
                if album_elem:
                    album_text = self._extract_text_safe(album_elem)
                    if album_text:
                        metadata['album_title'] = album_text
                        break
            
            # Label/Maison de disque
            label_selectors = ['.label', '.record-label', '[class*="label"]']
            for selector in label_selectors:
                label_elem = soup.select_one(selector)
                if label_elem:
                    label_text = self._extract_text_safe(label_elem)
                    if label_text:
                        metadata['label'] = label_text
                        break
            
            # Genre
            genre_selectors = ['.genre', '.style', '[class*="genre"]']
            for selector in genre_selectors:
                genre_elem = soup.select_one(selector)
                if genre_elem:
                    genre_text = self._extract_text_safe(genre_elem)
                    if genre_text:
                        metadata['genre'] = genre_text
                        break
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction métadonnées: {e}")
        
        return metadata
    
    def _extract_text_safe(self, element) -> str:
        """Extraction sécurisée de texte depuis un élément"""
        try:
            if element:
                return element.get_text(strip=True)
        except Exception:
            pass
        return ""
    
    def _deduplicate_and_enrich_tracks(self, tracks: List[Dict[str, Any]], artist_name: str) -> List[Dict[str, Any]]:
        """Déduplique et enrichit la liste des tracks"""
        if not tracks:
            return []
        
        # Déduplication par titre et URL
        seen_tracks = set()
        unique_tracks = []
        
        for track in tracks:
            # Clé de déduplication
            title = normalize_text(track.get('title', ''))
            url = track.get('url', '')
            dedup_key = (title, url)
            
            if dedup_key not in seen_tracks and title:
                seen_tracks.add(dedup_key)
                
                # Enrichissement
                track['artist_name'] = track.get('artist_name', artist_name)
                track['data_source'] = DataSource.RAPEDIA.value
                track['quality_score'] = self._calculate_track_quality_score(track)
                
                unique_tracks.append(track)
        
        # Tri par score de qualité
        unique_tracks.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        
        self.logger.debug(f"🧹 Déduplication: {len(unique_tracks)}/{len(tracks)} tracks conservées")
        
        return unique_tracks
    
    def _calculate_track_quality_score(self, track: Dict[str, Any]) -> float:
        """Calcule un score de qualité pour une track"""
        score = 0.0
        
        # Critères de qualité spécifiques à Rapedia
        if track.get('credits'):
            score += len(track['credits']) * 0.5  # Plus de crédits = meilleure qualité
        
        if track.get('release_date'):
            score += 2.0
        
        if track.get('album_title'):
            score += 1.5
        
        if track.get('label'):
            score += 1.0
        
        if track.get('genre'):
            score += 0.5
        
        # Bonus pour la présence de métadonnées étendues
        metadata_fields = ['url', 'title', 'artist_name']
        score += sum(1.0 for field in metadata_fields if track.get(field))
        
        return min(score, 10.0)  # Score maximum de 10
    
    def _deduplicate_credits(self, credits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Déduplique les crédits"""
        if not credits:
            return []
        
        seen_credits = set()
        unique_credits = []
        
        for credit in credits:
            # Clé de déduplication
            person_name = normalize_text(credit.get('person_name', ''))
            credit_type = credit.get('credit_type', '')
            dedup_key = (person_name, credit_type)
            
            if dedup_key not in seen_credits and person_name:
                seen_credits.add(dedup_key)
                unique_credits.append(credit)
        
        return unique_credits
    
    def _is_relevant_result(self, title: str, query: str) -> bool:
        """Vérifie la pertinence d'un résultat"""
        if not title or not query:
            return False
        
        title_normalized = normalize_text(title)
        query_normalized = normalize_text(query)
        
        # Correspondance exacte
        if query_normalized == title_normalized:
            return True
        
        # Correspondance partielle
        if query_normalized in title_normalized or title_normalized in query_normalized:
            return True
        
        # Correspondance des mots clés
        query_words = set(query_normalized.split())
        title_words = set(title_normalized.split())
        
        if len(query_words.intersection(title_words)) > 0:
            return True
        
        return False
    
    def _calculate_relevance_score(self, title: str, query: str) -> float:
        """Calcule un score de pertinence"""
        if not title or not query:
            return 0.0
        
        title_normalized = normalize_text(title)
        query_normalized = normalize_text(query)
        
        # Score basé sur la similarité
        if query_normalized == title_normalized:
            return 1.0
        elif query_normalized in title_normalized:
            return 0.8
        elif title_normalized in query_normalized:
            return 0.7
        else:
            # Score basé sur les mots communs
            query_words = set(query_normalized.split())
            title_words = set(title_normalized.split())
            common_words = query_words.intersection(title_words)
            
            if not query_words:
                return 0.0
            
            return len(common_words) / len(query_words)
    
    def _extract_result_metadata(self, item) -> Dict[str, Any]:
        """Extrait les métadonnées d'un résultat de recherche"""
        metadata = {}
        
        try:
            # Description/snippet
            desc_elem = item.find(class_=re.compile(r'description|snippet|summary'))
            if desc_elem:
                metadata['description'] = self._extract_text_safe(desc_elem)
            
            # Date si visible
            date_elem = item.find(class_=re.compile(r'date'))
            if date_elem:
                metadata['date'] = self._extract_text_safe(date_elem)
            
            # Genre/catégorie si visible
            genre_elem = item.find(class_=re.compile(r'genre|category'))
            if genre_elem:
                metadata['genre'] = self._extract_text_safe(genre_elem)
                
        except Exception as e:
            self.logger.debug(f"Erreur extraction métadonnées résultat: {e}")
        
        return metadata
    
    def _extract_track_from_element(self, element, source_url: str) -> Optional[Dict[str, Any]]:
        """Extrait une track depuis un élément HTML"""
        try:
            # Lien vers la track
            link = element.find('a') if element.name != 'a' else element
            if not link:
                return None
            
            track_url = link.get('href', '')
            if track_url and not track_url.startswith('http'):
                track_url = urljoin(self.base_url, track_url)
            
            # Titre de la track
            title = self._extract_text_safe(link)
            if not title:
                return None
            
            return {
                'title': title,
                'url': track_url,
                'source_page': source_url,
                'extraction_method': 'element_parsing'
            }
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction track element: {e}")
            return None
    
    def _extract_tracks_alternative_method(self, soup: BeautifulSoup, source_url: str) -> List[Dict[str, Any]]:
        """Méthode alternative d'extraction des tracks"""
        tracks = []
        
        try:
            # Recherche de tous les liens vers des tracks/morceaux
            track_links = soup.find_all('a', href=re.compile(r'/(track|morceau|song)/'))
            
            for link in track_links:
                try:
                    track_url = link.get('href')
                    if track_url and not track_url.startswith('http'):
                        track_url = urljoin(self.base_url, track_url)
                    
                    title = self._extract_text_safe(link)
                    
                    if title and track_url:
                        track = {
                            'title': title,
                            'url': track_url,
                            'source_page': source_url,
                            'extraction_method': 'alternative_parsing'
                        }
                        tracks.append(track)
                        
                except Exception as e:
                    self.logger.debug(f"Erreur extraction alternative: {e}")
                    continue
            
        except Exception as e:
            self.logger.debug(f"Erreur méthode alternative: {e}")
        
        return tracks
    
    def _url_to_cache_key(self, url: str) -> str:
        """Convertit une URL en clé de cache valide"""
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    # ===== MÉTHODES UTILITAIRES =====
    
    @lru_cache(maxsize=1)
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques avec cache"""
        stats = self.stats.copy()
        
        # Calculs additionnels
        if stats['searches_performed'] > 0:
            stats['average_tracks_per_search'] = stats['tracks_found'] / stats['searches_performed']
            stats['average_time_per_search'] = stats['total_time_spent'] / stats['searches_performed']
        else:
            stats['average_tracks_per_search'] = 0.0
            stats['average_time_per_search'] = 0.0
        
        if stats['pages_scraped'] > 0:
            stats['average_credits_per_page'] = stats['credits_extracted'] / stats['pages_scraped']
        else:
            stats['average_credits_per_page'] = 0.0
        
        # Taux de succès
        total_requests = stats['searches_performed'] + stats['pages_scraped']
        if total_requests > 0:
            stats['success_rate'] = ((total_requests - stats['failed_requests']) / total_requests) * 100
        else:
            stats['success_rate'] = 0.0
        
        # Source et fiabilité
        stats['source'] = 'rapedia'
        stats['reliability_score'] = 0.95  # Très fiable pour le rap français
        
        return stats
    
    def clear_cache(self) -> None:
        """Vide le cache et remet à zéro les pages visitées"""
        if self.cache_manager and hasattr(self.cache_manager, 'clear_all'):
            self.cache_manager.clear_all()
        
        self._visited_pages.clear()
        self._artist_cache.clear()
        self._pattern_cache.clear()
        
        # Vider les caches LRU
        self._parse_credit_text.cache_clear()
        self._infer_credit_type_from_category.cache_clear()
        self._map_category_to_enum.cache_clear()
        self.get_stats.cache_clear()
        
        self.logger.info("🧹 Cache Rapedia vidé")
    
    def reset_stats(self) -> None:
        """Remet à zéro les statistiques"""
        self.stats = {
            'searches_performed': 0,
            'pages_scraped': 0,
            'tracks_found': 0,
            'credits_extracted': 0,
            'cache_hits': 0,
            'failed_requests': 0,
            'total_time_spent': 0.0
        }
        
        self.get_stats.cache_clear()
        self.logger.info("📊 Statistiques Rapedia réinitialisées")
    
    def test_connection(self) -> Tuple[bool, str]:
        """Teste la connexion à Rapedia"""
        try:
            response = self.session.get(self.base_url, timeout=10)
            if response.status_code == 200:
                return True, "Connexion Rapedia réussie"
            else:
                return False, f"Erreur HTTP {response.status_code}"
        except Exception as e:
            return False, f"Erreur connexion: {e}"
    
    def batch_search_artists(self, artist_names: List[str], max_tracks_per_artist: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        """
        Recherche en lot pour plusieurs artistes.
        
        Args:
            artist_names: Liste des noms d'artistes
            max_tracks_per_artist: Nombre maximum de tracks par artiste
            
        Returns:
            Dictionnaire {nom_artiste: [tracks]}
        """
        results = {}
        
        for artist_name in artist_names:
            try:
                self.logger.info(f"🔍 Recherche batch: {artist_name}")
                tracks = self.search_artist_tracks(artist_name, max_tracks_per_artist)
                results[artist_name] = tracks
                
                # Rate limiting entre artistes
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"❌ Erreur batch pour {artist_name}: {e}")
                results[artist_name] = []
        
        self.logger.info(f"🏁 Recherche batch terminée: {len(results)} artistes traités")
        return results
    
    def __repr__(self) -> str:
        """Représentation string de l'instance"""
        stats = self.get_stats()
        return (f"RapediaScraper(searches={stats['searches_performed']}, "
                f"tracks_found={stats['tracks_found']}, "
                f"success_rate={stats['success_rate']:.1f}%)")


# ===== FONCTIONS UTILITAIRES MODULE =====

def create_rapedia_scraper() -> Optional[RapediaScraper]:
    """
    Factory function pour créer une instance RapediaScraper.
    
    Returns:
        Instance RapediaScraper ou None si échec
    """
    try:
        return RapediaScraper()
    except Exception as e:
        logging.getLogger(__name__).error(f"❌ Impossible de créer RapediaScraper: {e}")
        return None


def test_rapedia_scraping(artist_name: str = "Booba") -> Dict[str, Any]:
    """
    Teste le scraping Rapedia et retourne un rapport de diagnostic.
    
    Args:
        artist_name: Nom d'artiste pour le test
        
    Returns:
        Dictionnaire avec les résultats du test
    """
    logger = logging.getLogger(__name__)
    
    try:
        scraper = create_rapedia_scraper()
        if not scraper:
            return {
                'success': False,
                'error': 'Impossible de créer une instance RapediaScraper'
            }
        
        # Test de connexion
        connection_ok, connection_msg = scraper.test_connection()
        
        # Test de recherche
        test_tracks = []
        if connection_ok:
            try:
                test_tracks = scraper.search_artist_tracks(artist_name, max_tracks=3)
            except Exception as e:
                logger.error(f"Erreur test recherche: {e}")
        
        return {
            'success': connection_ok and len(test_tracks) > 0,
            'connection_status': connection_msg,
            'test_artist': artist_name,
            'tracks_found': len(test_tracks),
            'sample_tracks': test_tracks[:2] if test_tracks else [],
            'performance_stats': scraper.get_stats(),
            'rapedia_available': connection_ok
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur test Rapedia: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def extract_rap_francais_data(artist_names: List[str]) -> Dict[str, Any]:
    """
    Extraction spécialisée pour le rap français via Rapedia.
    
    Args:
        artist_names: Liste des artistes de rap français
        
    Returns:
        Compilation des données extraites
    """
    logger = logging.getLogger(__name__)
    
    try:
        scraper = create_rapedia_scraper()
        if not scraper:
            return {'success': False, 'error': 'Scraper creation failed'}
        
        logger.info(f"🎯 Extraction rap français: {len(artist_names)} artistes")
        
        # Recherche en lot
        all_results = scraper.batch_search_artists(artist_names, max_tracks_per_artist=50)
        
        # Compilation des statistiques
        total_tracks = sum(len(tracks) for tracks in all_results.values())
        total_credits = sum(
            len(track.get('credits', [])) 
            for tracks in all_results.values() 
            for track in tracks
        )
        
        # Collecte des collaborateurs uniques
        all_collaborators = set()
        for tracks in all_results.values():
            for track in tracks:
                for credit in track.get('credits', []):
                    collaborator = credit.get('person_name')
                    if collaborator:
                        all_collaborators.add(collaborator)
        
        return {
            'success': True,
            'artists_processed': len(artist_names),
            'total_tracks_found': total_tracks,
            'total_credits_extracted': total_credits,
            'unique_collaborators': len(all_collaborators),
            'collaborators_sample': sorted(list(all_collaborators))[:20],
            'detailed_results': all_results,
            'extraction_stats': scraper.get_stats()
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur extraction rap français: {e}")
        return {'success': False, 'error': str(e)}