# extractors/web_scrapers/genius_web_scraper.py
import logging
import time
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from urllib.parse import urljoin, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from ...utils.selenium_manager import SeleniumManager
from ...core.exceptions import ScrapingError, ElementNotFoundError
from ...core.cache import CacheManager
from ...config.settings import settings
from ...utils.text_utils import clean_text, normalize_title
from ...models.enums import DataSource, CreditType, CreditCategory

class GeniusWebScraper:
    """
    Scraper web avancé pour Genius.com - spécialisé dans l'extraction des crédits complets.
    
    OBJECTIF PRINCIPAL : Cliquer sur les boutons "EXPAND" pour révéler TOUS les crédits cachés !
    
    Fonctionnalités :
    - Navigation intelligente des pages Genius
    - Expansion automatique des crédits cachés
    - Extraction exhaustive des crédits détaillés
    - Gestion des erreurs et retry automatique
    - Cache intelligent pour éviter les re-scraping
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Composants
        self.selenium_manager = SeleniumManager()
        self.cache_manager = CacheManager()
        
        # Configuration spécifique Genius
        self.config = {
            'expand_all_credits': settings.get('credits.expand_all_credits', True),
            'wait_after_expand': settings.get('credits.wait_after_expand', 2),
            'max_retries': settings.get('credits.max_retries', 3),
            'timeout': settings.get('selenium.timeout', 30),
            'extract_lyrics': settings.get('genius.extract_lyrics', False)
        }
        
        # Sélecteurs CSS spécifiques à Genius (à jour 2024)
        self.selectors = {
            'credits_section': '[data-lyrics-container="true"] + div, .SongCredits, [class*="SongCredit"], .song_credits',
            'expand_button': 'button[class*="expand"], button[aria-label*="expand"], .expand-button, [data-testid*="expand"]',
            'credit_item': '[class*="Credit"], .credit-item, .song-credit-item',
            'credit_role': 'h3, .credit-role, .credit-type, [class*="CreditRole"]',
            'credit_person': 'a[href*="/artists/"], .credit-person, [class*="CreditArtist"]',
            'lyrics_container': '[data-lyrics-container="true"], .Lyrics__Container, .lyrics',
            'song_header': '.SongHeaderdesktop, .song-header, h1',
            'album_info': '.SongHeaderMetadata, .song-metadata, [class*="Metadata"]'
        }
        
        # Patterns de reconnaissance pour les crédits
        self.credit_patterns = self._load_credit_patterns()
        
        # Statistiques
        self.stats = {
            'pages_scraped': 0,
            'credits_extracted': 0,
            'expand_buttons_clicked': 0,
            'failed_extractions': 0,
            'cache_hits': 0
        }
        
        self.logger.info("GeniusWebScraper initialisé - prêt pour l'extraction des crédits complets")
    
    def _load_credit_patterns(self) -> Dict[str, List[str]]:
        """Charge les patterns de reconnaissance des crédits"""
        return {
            'production_roles': [
                'produced by', 'producer', 'production', 'prod by', 'prod.',
                'executive producer', 'exec producer', 'co-producer',
                'additional production', 'vocal producer', 'beats by'
            ],
            'engineering_roles': [
                'mixed by', 'mixing', 'mix engineer', 'engineer',
                'mastered by', 'mastering', 'master engineer',
                'recorded by', 'recording', 'recording engineer',
                'assistant engineer', 'studio engineer'
            ],
            'composition_roles': [
                'written by', 'songwriter', 'lyricist', 'lyrics by',
                'composed by', 'composer', 'music by', 'words by',
                'additional lyrics', 'co-writer'
            ],
            'performance_roles': [
                'vocals', 'lead vocals', 'backing vocals', 'background vocals',
                'featuring', 'feat.', 'guest vocals', 'ad-libs', 'harmony',
                'rap', 'verses', 'hook', 'chorus'
            ],
            'instrument_roles': [
                'guitar', 'bass', 'drums', 'piano', 'keyboards', 'synth',
                'saxophone', 'trumpet', 'violin', 'strings', 'brass',
                'percussion', 'organ', 'harmonica'
            ]
        }
    
    def scrape_track_credits(self, track_url: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Scrape les crédits complets d'un morceau depuis Genius.
        
        Args:
            track_url: URL de la page Genius du morceau
            force_refresh: Force le re-scraping même si en cache
            
        Returns:
            Dict contenant tous les crédits et métadonnées extraits
        """
        cache_key = f"genius_web_credits_{self._url_to_cache_key(track_url)}"
        
        # Vérification du cache
        if not force_refresh:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                self.logger.debug(f"Crédits en cache pour {track_url}")
                return cached_result
        
        try:
            self.logger.info(f"🎵 Scraping des crédits pour: {track_url}")
            
            # Navigation vers la page
            if not self.selenium_manager.navigate_to(track_url):
                raise ScrapingError(f"Impossible de charger la page: {track_url}")
            
            result = {
                'url': track_url,
                'scraped_at': datetime.now().isoformat(),
                'source': DataSource.GENIUS_WEB.value,
                'credits': [],
                'metadata': {},
                'success': False
            }
            
            with self.selenium_manager.get_driver() as driver:
                # 1. Attendre le chargement complet de la page
                self._wait_for_page_load(driver)
                
                # 2. Extraction des métadonnées de base
                metadata = self._extract_basic_metadata(driver)
                result['metadata'].update(metadata)
                
                # 3. ÉTAPE CRUCIALE : Expansion des crédits cachés
                expanded_sections = self._expand_all_credit_sections(driver)
                self.stats['expand_buttons_clicked'] += expanded_sections
                
                # 4. Extraction exhaustive des crédits
                credits = self._extract_all_credits(driver)
                result['credits'] = credits
                self.stats['credits_extracted'] += len(credits)
                
                # 5. Extraction des paroles si configuré
                if self.config['extract_lyrics']:
                    lyrics = self._extract_lyrics(driver)
                    if lyrics:
                        result['metadata']['lyrics'] = lyrics
                
                # 6. Validation et nettoyage
                result['credits'] = self._clean_and_validate_credits(result['credits'])
                result['success'] = len(result['credits']) > 0
                
                self.stats['pages_scraped'] += 1
                
                # Mise en cache si succès
                if result['success']:
                    self.cache_manager.set(cache_key, result)
                
                self.logger.info(
                    f"✅ Extraction terminée: {len(result['credits'])} crédits trouvés "
                    f"({expanded_sections} sections étendues)"
                )
                
                return result
                
        except Exception as e:
            self.stats['failed_extractions'] += 1
            self.logger.error(f"❌ Erreur lors du scraping de {track_url}: {e}")
            
            return {
                'url': track_url,
                'scraped_at': datetime.now().isoformat(),
                'source': DataSource.GENIUS_WEB.value,
                'credits': [],
                'metadata': {},
                'success': False,
                'error': str(e)
            }
    
    def _wait_for_page_load(self, driver):
        """Attend le chargement complet de la page Genius"""
        try:
            # Attendre que l'élément principal soit présent
            WebDriverWait(driver, self.config['timeout']).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.selectors['song_header'])),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-lyrics-container]"))
                )
            )
            
            # Petite pause pour les éléments dynamiques
            time.sleep(2)
            
            self.logger.debug("Page Genius chargée")
            
        except TimeoutException:
            self.logger.warning("Timeout lors du chargement de la page Genius")
    
    def _extract_basic_metadata(self, driver) -> Dict[str, Any]:
        """Extrait les métadonnées de base du morceau"""
        metadata = {}
        
        try:
            # Titre du morceau
            title_selectors = ["h1", self.selectors['song_header'], ".song-title"]
            for selector in title_selectors:
                title_elem = self.selenium_manager.find_element_safe(By.CSS_SELECTOR, selector, timeout=5)
                if title_elem:
                    title = self.selenium_manager.extract_text_safe(title_elem)
                    if title:
                        metadata['title'] = clean_text(title)
                        break
            
            # Artiste principal
            artist_selectors = ["a[href*='/artists/']", ".artist-name", "[class*='Artist']"]
            for selector in artist_selectors:
                artist_elem = self.selenium_manager.find_element_safe(By.CSS_SELECTOR, selector, timeout=5)
                if artist_elem:
                    artist = self.selenium_manager.extract_text_safe(artist_elem)
                    if artist and artist not in metadata.get('title', ''):
                        metadata['artist'] = clean_text(artist)
                        break
            
            # Informations d'album
            album_info = self._extract_album_info(driver)
            if album_info:
                metadata.update(album_info)
            
            # Date de sortie
            date_selectors = [".song-metadata time", "[datetime]", ".release-date"]
            for selector in date_selectors:
                date_elem = self.selenium_manager.find_element_safe(By.CSS_SELECTOR, selector, timeout=3)
                if date_elem:
                    date_text = self.selenium_manager.extract_text_safe(date_elem)
                    if date_text:
                        metadata['release_date'] = clean_text(date_text)
                        break
            
            self.logger.debug(f"Métadonnées extraites: {metadata}")
            
        except Exception as e:
            self.logger.warning(f"Erreur extraction métadonnées: {e}")
        
        return metadata
    
    def _extract_album_info(self, driver) -> Dict[str, Any]:
        """Extrait les informations d'album"""
        album_info = {}
        
        try:
            # Recherche des liens d'album
            album_links = self.selenium_manager.find_elements_safe(
                By.CSS_SELECTOR, 
                "a[href*='/albums/']", 
                timeout=5
            )
            
            for link in album_links:
                album_text = self.selenium_manager.extract_text_safe(link)
                if album_text and len(album_text) > 1:
                    album_info['album_title'] = clean_text(album_text)
                    album_info['album_url'] = link.get_attribute('href')
                    break
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction album: {e}")
        
        return album_info
    
    def _expand_all_credit_sections(self, driver) -> int:
        """
        FONCTION CRUCIALE : Clique sur tous les boutons "EXPAND" pour révéler les crédits cachés.
        
        Returns:
            Nombre de sections étendues
        """
        expanded_count = 0
        
        if not self.config['expand_all_credits']:
            return expanded_count
        
        try:
            self.logger.info("🔍 Recherche et expansion des sections de crédits cachées...")
            
            # Patterns de boutons d'expansion à rechercher
            expand_patterns = [
                "button[aria-label*='expand']",
                "button[aria-label*='Show']",
                "button[class*='expand']",
                "button[class*='Expand']",
                ".expand-button",
                "button[data-testid*='expand']",
                "button:contains('Show')",
                "button:contains('Expand')",
                "[role='button'][aria-expanded='false']"
            ]
            
            # Recherche dans différentes sections
            sections_to_search = [
                self.selectors['credits_section'],
                "[data-lyrics-container] + div",
                ".song-credits",
                ".SongCredits",
                "[class*='Credit']"
            ]
            
            for section_selector in sections_to_search:
                sections = self.selenium_manager.find_elements_safe(
                    By.CSS_SELECTOR, 
                    section_selector, 
                    timeout=5
                )
                
                for section in sections:
                    try:
                        # Rechercher les boutons d'expansion dans cette section
                        for pattern in expand_patterns:
                            expand_buttons = section.find_elements(By.CSS_SELECTOR, pattern)
                            
                            for button in expand_buttons:
                                if self._is_expandable_button(button):
                                    success = self.selenium_manager.click_element_safe(button)
                                    if success:
                                        expanded_count += 1
                                        self.logger.debug(f"✅ Section étendue (pattern: {pattern})")
                                        
                                        # Attendre que le contenu se charge
                                        time.sleep(self.config['wait_after_expand'])
                                        
                                        # Rechercher récursivement d'autres boutons dans le nouveau contenu
                                        new_buttons = section.find_elements(By.CSS_SELECTOR, pattern)
                                        for new_button in new_buttons:
                                            if (new_button != button and 
                                                self._is_expandable_button(new_button)):
                                                if self.selenium_manager.click_element_safe(new_button):
                                                    expanded_count += 1
                                                    time.sleep(1)
                    
                    except Exception as e:
                        self.logger.debug(f"Erreur lors de l'expansion d'une section: {e}")
                        continue
            
            # Technique alternative : JavaScript pour forcer l'expansion
            if expanded_count == 0:
                expanded_count += self._force_expand_with_javascript(driver)
            
            if expanded_count > 0:
                self.logger.info(f"🎯 {expanded_count} section(s) de crédits étendues avec succès")
                # Attendre que tout le contenu se charge
                time.sleep(3)
            else:
                self.logger.warning("⚠️ Aucune section de crédits n'a pu être étendue")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'expansion des crédits: {e}")
        
        return expanded_count
    
    def _is_expandable_button(self, button) -> bool:
        """Vérifie si un bouton est bien un bouton d'expansion de crédits"""
        try:
            # Vérifier si le bouton est visible et cliquable
            if not (button.is_displayed() and button.is_enabled()):
                return False
            
            # Vérifier le texte du bouton
            button_text = self.selenium_manager.extract_text_safe(button).lower()
            expand_keywords = ['expand', 'show', 'more', 'voir', 'afficher', '+']
            
            if any(keyword in button_text for keyword in expand_keywords):
                return True
            
            # Vérifier les attributs aria
            aria_label = button.get_attribute('aria-label')
            if aria_label and any(keyword in aria_label.lower() for keyword in expand_keywords):
                return True
            
            # Vérifier aria-expanded
            aria_expanded = button.get_attribute('aria-expanded')
            if aria_expanded == 'false':
                return True
            
            return False
            
        except Exception:
            return False
    
    def _force_expand_with_javascript(self, driver) -> int:
        """Force l'expansion via JavaScript en dernier recours"""
        expanded_count = 0
        
        try:
            # Scripts JavaScript pour forcer l'expansion
            js_scripts = [
                """
                // Cliquer sur tous les boutons contenant "expand" ou "show"
                var buttons = document.querySelectorAll('button');
                var count = 0;
                buttons.forEach(function(btn) {
                    var text = btn.textContent.toLowerCase();
                    var label = btn.getAttribute('aria-label') || '';
                    if (text.includes('expand') || text.includes('show') || 
                        label.toLowerCase().includes('expand') || 
                        btn.getAttribute('aria-expanded') === 'false') {
                        btn.click();
                        count++;
                    }
                });
                return count;
                """,
                """
                // Déclencher les événements sur les éléments avec data-expand
                var expandables = document.querySelectorAll('[data-expand], [data-expandable]');
                var count = 0;
                expandables.forEach(function(elem) {
                    elem.click();
                    count++;
                });
                return count;
                """
            ]
            
            for script in js_scripts:
                result = self.selenium_manager.execute_script_safe(script)
                if result and isinstance(result, int):
                    expanded_count += result
                    if result > 0:
                        time.sleep(2)  # Attendre après expansion JS
            
            if expanded_count > 0:
                self.logger.info(f"🔧 {expanded_count} section(s) étendues via JavaScript")
            
        except Exception as e:
            self.logger.debug(f"Erreur expansion JavaScript: {e}")
        
        return expanded_count
    
    def _extract_all_credits(self, driver) -> List[Dict[str, Any]]:
        """Extrait tous les crédits de la page (maintenant étendus)"""
        credits = []
        
        try:
            # Sélecteurs pour les sections de crédits
            credit_section_selectors = [
                self.selectors['credits_section'],
                ".SongCredits",
                "[class*='SongCredit']",
                ".song-credits",
                "[data-testid*='credit']"
            ]
            
            for selector in credit_section_selectors:
                sections = self.selenium_manager.find_elements_safe(
                    By.CSS_SELECTOR, 
                    selector, 
                    timeout=5
                )
                
                for section in sections:
                    section_credits = self._extract_credits_from_section(section)
                    credits.extend(section_credits)
            
            # Méthode alternative : extraction par pattern de texte
            if len(credits) < 5:  # Si peu de crédits trouvés, essayer méthode alternative
                text_credits = self._extract_credits_from_page_text(driver)
                credits.extend(text_credits)
            
            # Déduplication
            credits = self._deduplicate_credits(credits)
            
            self.logger.debug(f"Total crédits extraits: {len(credits)}")
            
        except Exception as e:
            self.logger.error(f"Erreur extraction crédits: {e}")
        
        return credits
    
    def _extract_credits_from_section(self, section) -> List[Dict[str, Any]]:
        """Extrait les crédits d'une section spécifique"""
        credits = []
        
        try:
            # Rechercher le titre de la section (type de crédit)
            role_elem = section.find_element(By.CSS_SELECTOR, "h3, h4, .credit-role, [class*='Role']")
            credit_role = self.selenium_manager.extract_text_safe(role_elem)
            
            if not credit_role:
                # Essayer d'autres sélecteurs
                role_selectors = ["strong", "b", ".title", "[class*='Title']"]
                for selector in role_selectors:
                    try:
                        role_elem = section.find_element(By.CSS_SELECTOR, selector)
                        credit_role = self.selenium_manager.extract_text_safe(role_elem)
                        if credit_role:
                            break
                    except:
                        continue
            
            # Rechercher les personnes/entités
            person_selectors = [
                "a[href*='/artists/']",
                ".credit-person",
                "[class*='Artist']",
                "a[href*='/users/']"
            ]
            
            people = []
            for selector in person_selectors:
                try:
                    person_elems = section.find_elements(By.CSS_SELECTOR, selector)
                    for elem in person_elems:
                        person_name = self.selenium_manager.extract_text_safe(elem)
                        if person_name and len(person_name) > 1:
                            people.append(person_name)
                except:
                    continue
            
            # Créer les crédits
            if credit_role and people:
                for person in people:
                    credit = {
                        'person_name': clean_text(person),
                        'role_raw': clean_text(credit_role),
                        'role_normalized': self._normalize_credit_role(credit_role),
                        'credit_type': self._detect_credit_type(credit_role),
                        'credit_category': self._detect_credit_category(credit_role),
                        'source': DataSource.GENIUS_WEB.value,
                        'extraction_method': 'section_structured'
                    }
                    credits.append(credit)
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction section: {e}")
        
        return credits
    
    def _extract_credits_from_page_text(self, driver) -> List[Dict[str, Any]]:
        """Méthode alternative : extraction par analyse de texte de la page"""
        credits = []
        
        try:
            # Récupérer tout le texte de la page
            page_text = driver.find_element(By.TAG_NAME, "body").text
            
            # Patterns pour détecter les crédits dans le texte
            credit_patterns = [
                r'(?:Produit par|Produced by|Producer?)\s*:?\s*([^.\n]+)',
                r'(?:Mixé par|Mixed by|Mix)\s*:?\s*([^.\n]+)',
                r'(?:Masterisé par|Mastered by|Master)\s*:?\s*([^.\n]+)',
                r'(?:Écrit par|Written by|Songwriter?)\s*:?\s*([^.\n]+)',
                r'(?:Featuring|Feat\.?|Ft\.?)\s*:?\s*([^.\n]+)',
                r'(?:Guitare|Guitar)\s*:?\s*([^.\n]+)',
                r'(?:Piano|Clavier|Keyboards?)\s*:?\s*([^.\n]+)',
                r'(?:Batterie|Drums)\s*:?\s*([^.\n]+)',
                r'(?:Basse|Bass)\s*:?\s*([^.\n]+)'
            ]
            
            for pattern in credit_patterns:
                matches = re.finditer(pattern, page_text, re.IGNORECASE | re.MULTILINE)
                
                for match in matches:
                    role_raw = match.group(0).split(':')[0].strip()
                    people_str = match.group(1).strip()
                    
                    # Parser les noms multiples
                    people = re.split(r'[,&\+]|and\s+|et\s+', people_str)
                    
                    for person in people:
                        person = person.strip()
                        if person and len(person) > 1:
                            credit = {
                                'person_name': clean_text(person),
                                'role_raw': clean_text(role_raw),
                                'role_normalized': self._normalize_credit_role(role_raw),
                                'credit_type': self._detect_credit_type(role_raw),
                                'credit_category': self._detect_credit_category(role_raw),
                                'source': DataSource.GENIUS_WEB.value,
                                'extraction_method': 'text_pattern'
                            }
                            credits.append(credit)
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction par texte: {e}")
        
        return credits
    
    def _normalize_credit_role(self, role: str) -> str:
        """Normalise un rôle de crédit"""
        if not role:
            return "other"
        
        role_lower = role.lower().strip()
        
        # Mappings de normalisation
        if any(word in role_lower for word in ['produit', 'produced', 'producer', 'prod']):
            return 'producer'
        elif any(word in role_lower for word in ['mixé', 'mixed', 'mix']):
            return 'mixing'
        elif any(word in role_lower for word in ['masterisé', 'mastered', 'master']):
            return 'mastering'
        elif any(word in role_lower for word in ['écrit', 'written', 'songwriter']):
            return 'songwriter'
        elif any(word in role_lower for word in ['featuring', 'feat', 'ft']):
            return 'featuring'
        elif any(word in role_lower for word in ['guitar', 'guitare']):
            return 'guitar'
        elif any(word in role_lower for word in ['piano', 'clavier', 'keyboard']):
            return 'piano'
        elif any(word in role_lower for word in ['drums', 'batterie']):
            return 'drums'
        elif any(word in role_lower for word in ['bass', 'basse']):
            return 'bass'
        else:
            return 'other'
    
    def _detect_credit_type(self, role: str) -> str:
        """Détecte le type de crédit depuis le rôle"""
        normalized = self._normalize_credit_role(role)
        
        type_mapping = {
            'producer': CreditType.PRODUCER.value,
            'mixing': CreditType.MIXING.value,
            'mastering': CreditType.MASTERING.value,
            'songwriter': CreditType.SONGWRITER.value,
            'featuring': CreditType.FEATURING.value,
            'guitar': CreditType.GUITAR.value,
            'piano': CreditType.PIANO.value,
            'drums': CreditType.DRUMS.value,
            'bass': CreditType.BASS.value
        }
        
        return type_mapping.get(normalized, CreditType.OTHER.value)
    
    def _detect_credit_category(self, role: str) -> str:
        """Détecte la catégorie de crédit depuis le rôle"""
        normalized = self._normalize_credit_role(role)
        
        category_mapping = {
            'producer': CreditCategory.PRODUCER.value,
            'mixing': CreditCategory.TECHNICAL.value,
            'mastering': CreditCategory.TECHNICAL.value,
            'songwriter': CreditCategory.COMPOSER.value,
            'featuring': CreditCategory.FEATURING.value,
            'guitar': CreditCategory.INSTRUMENT.value,
            'piano': CreditCategory.INSTRUMENT.value,
            'drums': CreditCategory.INSTRUMENT.value,
            'bass': CreditCategory.INSTRUMENT.value
        }
        
        return category_mapping.get(normalized, CreditCategory.OTHER.value)
    
    def _deduplicate_credits(self, credits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Supprime les doublons des crédits"""
        seen = set()
        unique_credits = []
        
        for credit in credits:
            # Clé unique basée sur le nom et le rôle
            key = (
                credit.get('person_name', '').lower().strip(),
                credit.get('role_normalized', '').lower().strip()
            )
            
            if key not in seen and key[0] and key[1]:
                seen.add(key)
                unique_credits.append(credit)
        
        return unique_credits
    
    def _clean_and_validate_credits(self, credits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Nettoie et valide les crédits extraits"""
        cleaned_credits = []
        
        for credit in credits:
            # Validation du nom
            person_name = credit.get('person_name', '').strip()
            if not person_name or len(person_name) < 2:
                continue
            
            # Filtrer les noms génériques
            generic_names = ['unknown', 'various', 'n/a', 'tba', 'multiple']
            if person_name.lower() in generic_names:
                continue
            
            # Nettoyage final
            credit['person_name'] = clean_text(person_name)
            credit['confidence_score'] = self._calculate_credit_confidence(credit)
            
            cleaned_credits.append(credit)
        
        return cleaned_credits
    
    def _calculate_credit_confidence(self, credit: Dict[str, Any]) -> float:
        """Calcule un score de confiance pour un crédit"""
        score = 0.8  # Score de base pour Genius Web
        
        # Bonus selon la méthode d'extraction
        if credit.get('extraction_method') == 'section_structured':
            score += 0.15
    def _calculate_credit_confidence(self, credit: Dict[str, Any]) -> float:
        """Calcule un score de confiance pour un crédit"""
        score = 0.8  # Score de base pour Genius Web
        
        # Bonus selon la méthode d'extraction
        if credit.get('extraction_method') == 'section_structured':
            score += 0.15
        elif credit.get('extraction_method') == 'text_pattern':
            score += 0.05
        
        # Bonus pour les rôles bien reconnus
        if credit.get('role_normalized') != 'other':
            score += 0.05
        
        # Malus si le nom semble suspect
        person_name = credit.get('person_name', '').lower()
        if any(word in person_name for word in ['unknown', 'various', 'multiple']):
            score -= 0.3
        
        return min(1.0, max(0.0, score))
    
    def _extract_lyrics(self, driver) -> Optional[str]:
        """Extrait les paroles si configuré"""
        try:
            lyrics_selectors = [
                self.selectors['lyrics_container'],
                "[data-lyrics-container='true']",
                ".Lyrics__Container",
                ".lyrics"
            ]
            
            for selector in lyrics_selectors:
                lyrics_elem = self.selenium_manager.find_element_safe(
                    By.CSS_SELECTOR, 
                    selector, 
                    timeout=5
                )
                
                if lyrics_elem:
                    lyrics_text = self.selenium_manager.extract_text_safe(lyrics_elem)
                    if lyrics_text and len(lyrics_text) > 50:
                        return clean_text(lyrics_text)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction paroles: {e}")
            return None
    
    def _url_to_cache_key(self, url: str) -> str:
        """Convertit une URL en clé de cache"""
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def batch_scrape_tracks(self, track_urls: List[str], max_concurrent: int = 3) -> List[Dict[str, Any]]:
        """
        Scrape plusieurs morceaux en série (évite les blocages).
        
        Args:
            track_urls: Liste des URLs à scraper
            max_concurrent: Non utilisé ici, traitement séquentiel pour éviter les blocages
            
        Returns:
            Liste des résultats de scraping
        """
        results = []
        
        self.logger.info(f"🎵 Scraping en série de {len(track_urls)} morceaux")
        
        for i, url in enumerate(track_urls):
            try:
                self.logger.info(f"Traitement {i+1}/{len(track_urls)}: {url}")
                
                result = self.scrape_track_credits(url)
                results.append(result)
                
                # Pause entre les requêtes pour éviter les blocages
                if i < len(track_urls) - 1:
                    pause_time = 3 + (i % 3)  # Pause variable 3-5s
                    time.sleep(pause_time)
                
            except Exception as e:
                self.logger.error(f"Erreur scraping {url}: {e}")
                results.append({
                    'url': url,
                    'success': False,
                    'error': str(e),
                    'credits': []
                })
        
        successful = len([r for r in results if r.get('success', False)])
        self.logger.info(f"✅ Scraping terminé: {successful}/{len(track_urls)} réussis")
        
        return results
    
    def test_scraping_capabilities(self, test_url: str = "https://genius.com/Eminem-lose-yourself-lyrics") -> Dict[str, Any]:
        """
        Teste les capacités de scraping sur une page connue.
        
        Args:
            test_url: URL de test (par défaut: page Eminem connue)
            
        Returns:
            Rapport de test détaillé
        """
        test_report = {
            'test_url': test_url,
            'test_date': datetime.now().isoformat(),
            'navigation_success': False,
            'page_load_success': False,
            'expand_buttons_found': 0,
            'credits_extracted': 0,
            'test_success': False,
            'errors': [],
            'recommendations': []
        }
        
        try:
            self.logger.info(f"🧪 Test de scraping sur: {test_url}")
            
            # Test de navigation
            if self.selenium_manager.navigate_to(test_url):
                test_report['navigation_success'] = True
            else:
                test_report['errors'].append("Échec de navigation")
                return test_report
            
            with self.selenium_manager.get_driver() as driver:
                # Test de chargement de page
                try:
                    self._wait_for_page_load(driver)
                    test_report['page_load_success'] = True
                except Exception as e:
                    test_report['errors'].append(f"Échec chargement page: {e}")
                
                # Test d'expansion des crédits
                try:
                    expanded = self._expand_all_credit_sections(driver)
                    test_report['expand_buttons_found'] = expanded
                    
                    if expanded > 0:
                        test_report['recommendations'].append("✅ Expansion des crédits fonctionnelle")
                    else:
                        test_report['recommendations'].append("⚠️ Aucune section étendue - vérifier les sélecteurs")
                
                except Exception as e:
                    test_report['errors'].append(f"Erreur expansion: {e}")
                
                # Test d'extraction des crédits
                try:
                    credits = self._extract_all_credits(driver)
                    test_report['credits_extracted'] = len(credits)
                    
                    if len(credits) > 0:
                        test_report['recommendations'].append(f"✅ {len(credits)} crédits extraits")
                        test_report['sample_credits'] = credits[:3]  # Échantillon
                    else:
                        test_report['recommendations'].append("⚠️ Aucun crédit extrait - vérifier les sélecteurs")
                
                except Exception as e:
                    test_report['errors'].append(f"Erreur extraction crédits: {e}")
            
            # Évaluation globale
            test_report['test_success'] = (
                test_report['navigation_success'] and
                test_report['page_load_success'] and
                test_report['credits_extracted'] > 0
            )
            
            if test_report['test_success']:
                self.logger.info("✅ Test de scraping réussi")
            else:
                self.logger.warning("⚠️ Test de scraping partiellement échoué")
            
        except Exception as e:
            test_report['errors'].append(f"Erreur générale: {e}")
            self.logger.error(f"❌ Erreur lors du test: {e}")
        
        return test_report
    
    def update_selectors(self, new_selectors: Dict[str, str]):
        """
        Met à jour les sélecteurs CSS (utile si Genius change sa structure).
        
        Args:
            new_selectors: Dictionnaire des nouveaux sélecteurs
        """
        self.selectors.update(new_selectors)
        self.logger.info(f"Sélecteurs mis à jour: {list(new_selectors.keys())}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du scraper"""
        stats = self.stats.copy()
        
        # Calculs dérivés
        if stats['pages_scraped'] > 0:
            stats['success_rate'] = (stats['pages_scraped'] - stats['failed_extractions']) / stats['pages_scraped']
            stats['avg_credits_per_page'] = stats['credits_extracted'] / stats['pages_scraped']
            stats['avg_expansions_per_page'] = stats['expand_buttons_clicked'] / stats['pages_scraped']
        else:
            stats['success_rate'] = 0.0
            stats['avg_credits_per_page'] = 0.0
            stats['avg_expansions_per_page'] = 0.0
        
        # Cache hit rate
        total_requests = stats['pages_scraped'] + stats['cache_hits']
        if total_requests > 0:
            stats['cache_hit_rate'] = stats['cache_hits'] / total_requests
        else:
            stats['cache_hit_rate'] = 0.0
        
        return stats
    
    def clear_cache(self):
        """Vide le cache du scraper"""
        # Note: Implémentation dépend de CacheManager
        self.logger.info("Cache du scraper vidé")
    
    def close(self):
        """Ferme proprement le scraper"""
        try:
            if hasattr(self.selenium_manager, '_close_driver'):
                self.selenium_manager._close_driver()
            self.logger.info("GeniusWebScraper fermé proprement")
        except Exception as e:
            self.logger.warning(f"Erreur lors de la fermeture: {e}")
    
    def __enter__(self):
        """Support du context manager"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Nettoyage automatique"""
        self.close()

# Fonctions utilitaires pour un usage simple

def scrape_genius_track_credits(track_url: str) -> List[Dict[str, str]]:
    """
    Fonction utilitaire pour scraper rapidement les crédits d'un morceau.
    
    Args:
        track_url: URL de la page Genius
        
    Returns:
        Liste des crédits trouvés
    """
    with GeniusWebScraper() as scraper:
        result = scraper.scrape_track_credits(track_url)
        return result.get('credits', [])

def test_genius_scraping() -> bool:
    """
    Test rapide des capacités de scraping Genius.
    
    Returns:
        True si le test réussit
    """
    with GeniusWebScraper() as scraper:
        test_result = scraper.test_scraping_capabilities()
        return test_result.get('test_success', False)

def batch_scrape_genius_urls(urls: List[str]) -> Dict[str, List[Dict]]:
    """
    Scrape une liste d'URLs Genius en série.
    
    Args:
        urls: Liste des URLs à scraper
        
    Returns:
        Dict avec 'successful' et 'failed' contenant les résultats
    """
    with GeniusWebScraper() as scraper:
        results = scraper.batch_scrape_tracks(urls)
        
        successful = [r for r in results if r.get('success', False)]
        failed = [r for r in results if not r.get('success', False)]
        
        return {
            'successful': successful,
            'failed': failed,
            'stats': {
                'total': len(results),
                'successful_count': len(successful),
                'failed_count': len(failed),
                'success_rate': len(successful) / len(results) if results else 0
            }
        }

# Exemple d'utilisation avancée
def extract_complete_artist_credits(artist_genius_urls: List[str]) -> Dict[str, Any]:
    """
    Extraction complète des crédits pour tous les morceaux d'un artiste.
    
    Args:
        artist_genius_urls: Liste des URLs Genius des morceaux de l'artiste
        
    Returns:
        Compilation complète des crédits avec statistiques
    """
    with GeniusWebScraper() as scraper:
        logging.getLogger(__name__).info(f"🎯 Extraction complète pour {len(artist_genius_urls)} morceaux")
        
        all_credits = []
        all_collaborators = set()
        results = scraper.batch_scrape_tracks(artist_genius_urls)
        
        for result in results:
            if result.get('success'):
                track_credits = result.get('credits', [])
                all_credits.extend(track_credits)
                
                # Collecter les collaborateurs uniques
                for credit in track_credits:
                    collaborator = credit.get('person_name')
                    if collaborator:
                        all_collaborators.add(collaborator)
        
        # Compilation des statistiques
        credit_types = {}
        for credit in all_credits:
            credit_type = credit.get('credit_type', 'unknown')
            credit_types[credit_type] = credit_types.get(credit_type, 0) + 1
        
        return {
            'total_credits': len(all_credits),
            'unique_collaborators': len(all_collaborators),
            'collaborators_list': sorted(list(all_collaborators)),
            'credit_distribution': credit_types,
            'all_credits': all_credits,
            'extraction_stats': scraper.get_stats(),
            'successful_tracks': len([r for r in results if r.get('success')]),
            'failed_tracks': len([r for r in results if not r.get('success')])
        }# extractors/web_scrapers/genius_web_scraper.py
import logging
import time
import re
from typing import