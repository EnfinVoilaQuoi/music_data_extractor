# extractors/web_scrapers/genius_scraper.py
"""
Scraper web optimisé pour Genius.com - spécialisé dans l'extraction des crédits complets.
Version optimisée avec Selenium, expansion automatique des crédits cachés et cache intelligent.
"""

import logging
import time
import re
from functools import lru_cache
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from urllib.parse import urljoin, urlparse
from contextlib import contextmanager

# Imports conditionnels pour Selenium
try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException, 
        ElementClickInterceptedException, StaleElementReferenceException
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Imports absolus
from utils.selenium_manager import SeleniumManager
from core.exceptions import ScrapingError, ElementNotFoundError
from core.cache import CacheManager
from config.settings import settings
from utils.text_utils import normalize_text, clean_artist_name
from models.enums import DataSource, CreditType, CreditCategory


class GeniusWebScraper:
    """
    Scraper web avancé pour Genius.com - spécialisé dans l'extraction des crédits complets.
    
    OBJECTIF PRINCIPAL : Cliquer sur les boutons "EXPAND" pour révéler TOUS les crédits cachés !
    
    Fonctionnalités optimisées :
    - Navigation intelligente des pages Genius
    - Expansion automatique des crédits cachés avec retry
    - Extraction exhaustive des crédits détaillés
    - Gestion avancée des erreurs et retry automatique
    - Cache intelligent pour éviter les re-scraping
    - Anti-détection avec rotation d'User-Agents
    - Parsing intelligent des structures HTML dynamiques
    """
    
    def __init__(self):
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium est requis pour GeniusWebScraper. Installez-le avec: pip install selenium webdriver-manager")
        
        self.logger = logging.getLogger(__name__)
        
        # Composants core
        self.selenium_manager = SeleniumManager()
        self.cache_manager = CacheManager() if CacheManager else None
        
        # Configuration optimisée spécifique Genius
        self.config = {
            'expand_all_credits': settings.get('genius.expand_all_credits', True),
            'wait_after_expand': settings.get('genius.wait_after_expand', 2),
            'max_retries': settings.get('genius.max_retries', 3),
            'timeout': settings.get('selenium.timeout', 30),
            'extract_lyrics': settings.get('genius.extract_lyrics', True),
            'anti_detection': settings.get('genius.anti_detection', True),
            'scroll_to_load': settings.get('genius.scroll_to_load', True),
            'screenshot_on_error': settings.get('genius.screenshot_on_error', True)
        }
        
        # Sélecteurs CSS spécifiques à Genius (mise à jour 2024)
        self.selectors = self._compile_selectors()
        
        # Patterns de reconnaissance pour les crédits avec cache
        self.credit_patterns = self._load_credit_patterns()
        
        # Cache pour éviter les recalculs
        self._selector_cache = {}
        self._pattern_cache = {}
        
        # Statistiques de performance
        self.stats = {
            'pages_scraped': 0,
            'credits_extracted': 0,
            'expand_buttons_clicked': 0,
            'failed_extractions': 0,
            'cache_hits': 0,
            'total_time_spent': 0.0,
            'average_page_time': 0.0
        }
        
        self.logger.info("✅ GeniusWebScraper optimisé initialisé - prêt pour l'extraction des crédits complets")
    
    @lru_cache(maxsize=1)
    def _compile_selectors(self) -> Dict[str, List[str]]:
        """
        Compile les sélecteurs CSS avec cache pour optimisation.
        
        Returns:
            Dictionnaire des sélecteurs compilés
        """
        return {
            'credits_section': [
                '[data-lyrics-container="true"] + div',
                '.SongCredits',
                '[class*="SongCredit"]',
                '.song_credits',
                '[data-testid*="credits"]',
                '.credits-container',
                '#credits-section'
            ],
            'expand_button': [
                'button[class*="expand"]',
                'button[aria-label*="expand"]',
                '.expand-button',
                '[data-testid*="expand"]',
                'button:contains("Show")',
                'button:contains("More")',
                '[class*="ShowMore"]',
                '[class*="ExpandButton"]'
            ],
            'credit_item': [
                '[class*="Credit"]',
                '.credit-item',
                '.song-credit-item',
                '[data-testid*="credit"]',
                '.credit-row',
                '.producer-credit',
                '.songwriter-credit'
            ],
            'credit_role': [
                'h3', 'h4', 'h5',
                '.credit-role',
                '.credit-type',
                '[class*="CreditRole"]',
                '[class*="Role"]',
                '.role-title',
                '.credit-category'
            ],
            'credit_person': [
                'a[href*="/artists/"]',
                '.credit-person',
                '[class*="CreditArtist"]',
                '.artist-link',
                '.producer-name',
                '.songwriter-name',
                '.contributor-name'
            ],
            'lyrics_container': [
                '[data-lyrics-container="true"]',
                '.Lyrics__Container',
                '.lyrics',
                '[class*="Lyrics"]',
                '#lyrics-root'
            ],
            'song_header': [
                '.SongHeaderdesktop',
                '.song-header',
                'h1',
                '.track-info',
                '.song-title'
            ],
            'album_info': [
                '.SongHeaderMetadata',
                '.song-metadata',
                '[class*="Metadata"]',
                '.album-link',
                '.release-info'
            ]
        }
    
    @lru_cache(maxsize=1)
    def _load_credit_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Charge et compile les patterns de reconnaissance des crédits avec cache"""
        patterns = {
            'production_roles': [
                r'produced by',
                r'producer',
                r'production',
                r'prod\.?\s*by',
                r'beat\s*by',
                r'instrumental\s*by',
                r'track\s*by'
            ],
            'writing_roles': [
                r'written by',
                r'songwriter',
                r'lyrics\s*by',
                r'composed\s*by',
                r'words\s*by'
            ],
            'engineering_roles': [
                r'mixed\s*by',
                r'mastered\s*by',
                r'recorded\s*by',
                r'engineered\s*by',
                r'additional\s*engineering',
                r'vocal\s*engineering'
            ],
            'performance_roles': [
                r'performed\s*by',
                r'vocals\s*by',
                r'featuring',
                r'guest\s*vocals',
                r'additional\s*vocals',
                r'background\s*vocals'
            ],
            'other_roles': [
                r'executive\s*producer',
                r'co-producer',
                r'additional\s*production',
                r'sample\s*source',
                r'interpolates',
                r'contains\s*sample'
            ]
        }
        
        # Compilation des patterns avec cache
        compiled_patterns = {}
        for category, pattern_list in patterns.items():
            compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE) for pattern in pattern_list
            ]
        
        return compiled_patterns
    
    @contextmanager
    def _timing_context(self, operation_name: str):
        """Context manager pour mesurer les performances"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.stats['total_time_spent'] += duration
            self.logger.debug(f"⏱️ {operation_name}: {duration:.2f}s")
    
    def scrape_track_credits(self, track_url: str, max_retries: Optional[int] = None) -> Dict[str, Any]:
        """
        Scrape les crédits complets d'une track Genius avec optimisations.
        
        Args:
            track_url: URL de la track Genius
            max_retries: Nombre maximum de tentatives
            
        Returns:
            Dictionnaire avec les crédits extraits et métadonnées
        """
        max_retries = max_retries or self.config['max_retries']
        
        with self._timing_context(f"scrape_track_credits({track_url})"):
            # Vérification du cache
            cache_key = self._url_to_cache_key(track_url)
            
            if self.cache_manager:
                cached_result = self.cache_manager.get(f"genius_credits_{cache_key}")
                if cached_result:
                    self.stats['cache_hits'] += 1
                    self.logger.info(f"💾 Cache hit pour {track_url}")
                    return cached_result
            
            # Tentatives d'extraction avec retry
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    self.logger.info(f"🎯 Extraction crédits Genius (tentative {attempt + 1}/{max_retries}): {track_url}")
                    
                    result = self._scrape_track_attempt(track_url)
                    
                    if result and result.get('success'):
                        # Mise en cache du succès
                        if self.cache_manager:
                            self.cache_manager.set(f"genius_credits_{cache_key}", result, expire_hours=24)
                        
                        self.stats['pages_scraped'] += 1
                        self.stats['credits_extracted'] += len(result.get('credits', []))
                        
                        self.logger.info(f"✅ Extraction réussie: {len(result.get('credits', []))} crédits trouvés")
                        return result
                    else:
                        raise ScrapingError(result.get('error', 'Unknown error'))
                
                except Exception as e:
                    last_error = e
                    self.logger.warning(f"⚠️ Tentative {attempt + 1} échouée: {e}")
                    
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + 1  # Backoff exponentiel
                        self.logger.info(f"⏳ Attente {wait_time}s avant nouvelle tentative...")
                        time.sleep(wait_time)
            
            # Toutes les tentatives ont échoué
            self.stats['failed_extractions'] += 1
            error_result = {
                'success': False,
                'error': f"Échec après {max_retries} tentatives: {last_error}",
                'url': track_url,
                'credits': [],
                'metadata': {}
            }
            
            self.logger.error(f"❌ Échec définitif pour {track_url}: {last_error}")
            return error_result
    
    def _scrape_track_attempt(self, track_url: str) -> Dict[str, Any]:
        """
        Tentative unique d'extraction des crédits avec gestion complète.
        
        Args:
            track_url: URL de la track
            
        Returns:
            Résultat de l'extraction
        """
        with self.selenium_manager.get_driver() as driver:
            try:
                # Navigation vers la page
                if not self.selenium_manager.navigate_to(track_url):
                    raise ScrapingError("Impossible de naviguer vers la page")
                
                # Attente du chargement complet
                self._wait_for_page_load(driver)
                
                # Anti-détection : simulation d'interaction utilisateur
                if self.config['anti_detection']:
                    self._simulate_user_behavior(driver)
                
                # Expansion des crédits cachés (CŒUR DE LA FONCTIONNALITÉ)
                expanded_count = self._expand_all_credits(driver)
                self.stats['expand_buttons_clicked'] += expanded_count
                
                # Extraction des crédits maintenant visibles
                credits = self._extract_all_credits(driver)
                
                # Extraction des métadonnées additionnelles
                metadata = self._extract_track_metadata(driver)
                
                # Extraction des paroles si configuré
                lyrics = None
                if self.config['extract_lyrics']:
                    lyrics = self._extract_lyrics(driver)
                
                return {
                    'success': True,
                    'url': track_url,
                    'credits': credits,
                    'metadata': metadata,
                    'lyrics': lyrics,
                    'expanded_sections': expanded_count,
                    'extraction_time': datetime.now().isoformat(),
                    'data_source': DataSource.GENIUS.value
                }
                
            except Exception as e:
                # Screenshot en cas d'erreur pour debugging
                if self.config['screenshot_on_error']:
                    try:
                        screenshot_path = f"error_genius_{int(time.time())}.png"
                        driver.save_screenshot(screenshot_path)
                        self.logger.debug(f"📸 Screenshot sauvegardé: {screenshot_path}")
                    except:
                        pass
                
                raise ScrapingError(f"Erreur durant l'extraction: {e}")
    
    def _wait_for_page_load(self, driver) -> None:
        """Attend le chargement complet de la page Genius"""
        try:
            # Attendre que l'élément principal soit présent
            WebDriverWait(driver, self.config['timeout']).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.SongHeaderdesktop')),
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.song-header')),
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'h1'))
                )
            )
            
            # Attendre un peu plus pour le contenu dynamique
            time.sleep(2)
            
            # Scroll pour déclencher le lazy loading si configuré
            if self.config['scroll_to_load']:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, 0);")
            
        except TimeoutException:
            self.logger.warning("⚠️ Timeout en attendant le chargement de la page")
    
    def _simulate_user_behavior(self, driver) -> None:
        """Simule un comportement utilisateur pour éviter la détection de bot"""
        try:
            # Scroll aléatoire
            scroll_positions = [0.3, 0.6, 0.9, 0.5, 0.1]
            for position in scroll_positions:
                driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {position});")
                time.sleep(0.5 + (time.time() % 1))  # Délai aléatoire
            
            # Retour en haut
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
        except Exception as e:
            self.logger.debug(f"Erreur simulation utilisateur: {e}")
    
    def _expand_all_credits(self, driver) -> int:
        """
        Expand tous les boutons de crédits cachés - FONCTION CLÉE !
        
        Args:
            driver: WebDriver Selenium
            
        Returns:
            Nombre de boutons expandés
        """
        expanded_count = 0
        
        try:
            # Méthode 1: Recherche par sélecteurs CSS
            for selector_group in self.selectors['expand_button']:
                try:
                    buttons = driver.find_elements(By.CSS_SELECTOR, selector_group)
                    
                    for button in buttons:
                        try:
                            # Vérifier que le bouton est visible et cliquable
                            if button.is_displayed() and button.is_enabled():
                                # Scroll vers le bouton
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(0.5)
                                
                                # Clic sur le bouton
                                button.click()
                                expanded_count += 1
                                
                                # Attendre que le contenu se charge
                                time.sleep(self.config['wait_after_expand'])
                                
                                self.logger.debug(f"🔍 Bouton expand cliqué: {selector_group}")
                                
                        except (ElementClickInterceptedException, StaleElementReferenceException) as e:
                            # Tentative de clic via JavaScript
                            try:
                                driver.execute_script("arguments[0].click();", button)
                                expanded_count += 1
                                time.sleep(self.config['wait_after_expand'])
                                self.logger.debug(f"🔍 Bouton expand cliqué via JS: {selector_group}")
                            except Exception as js_error:
                                self.logger.debug(f"Erreur clic JS: {js_error}")
                        
                        except Exception as e:
                            self.logger.debug(f"Erreur clic bouton: {e}")
                
                except Exception as e:
                    self.logger.debug(f"Erreur recherche boutons {selector_group}: {e}")
            
            # Méthode 2: Recherche par texte si peu de boutons trouvés
            if expanded_count < 2:
                text_patterns = ["Show", "More", "Expand", "See all", "View more"]
                for pattern in text_patterns:
                    try:
                        xpath = f"//button[contains(text(), '{pattern}')]"
                        buttons = driver.find_elements(By.XPATH, xpath)
                        
                        for button in buttons:
                            try:
                                if button.is_displayed():
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                    time.sleep(0.5)
                                    button.click()
                                    expanded_count += 1
                                    time.sleep(self.config['wait_after_expand'])
                                    self.logger.debug(f"🔍 Bouton text expand cliqué: {pattern}")
                            except Exception as e:
                                self.logger.debug(f"Erreur clic bouton text: {e}")
                    except Exception as e:
                        self.logger.debug(f"Erreur recherche text {pattern}: {e}")
            
            # Méthode 3: Expansion JavaScript directe
            if expanded_count == 0:
                try:
                    js_script = """
                    var expandButtons = document.querySelectorAll('[class*="expand"], [class*="show"], [class*="more"]');
                    var clickedCount = 0;
                    expandButtons.forEach(function(btn) {
                        try {
                            if (btn.tagName === 'BUTTON' && btn.offsetParent !== null) {
                                btn.click();
                                clickedCount++;
                            }
                        } catch(e) { console.log('Button click error:', e); }
                    });
                    return clickedCount;
                    """
                    
                    js_expanded = driver.execute_script(js_script)
                    if js_expanded:
                        expanded_count += js_expanded
                        time.sleep(self.config['wait_after_expand'] * 2)  # Plus de temps pour le JS
                        self.logger.debug(f"🔍 {js_expanded} boutons expandés via JavaScript")
                
                except Exception as e:
                    self.logger.debug(f"Erreur expansion JavaScript: {e}")
            
            self.logger.info(f"🔍 Total boutons expand cliqués: {expanded_count}")
            
        except Exception as e:
            self.logger.error(f"❌ Erreur générale expansion crédits: {e}")
        
        return expanded_count
    
    def _extract_all_credits(self, driver) -> List[Dict[str, Any]]:
        """Extrait tous les crédits de la page (maintenant étendus)"""
        credits = []
        
        try:
            # Méthode 1: Extraction par sections de crédits
            for selector_group in self.selectors['credits_section']:
                try:
                    sections = driver.find_elements(By.CSS_SELECTOR, selector_group)
                    
                    for section in sections:
                        section_credits = self._extract_credits_from_section(section)
                        credits.extend(section_credits)
                        
                except Exception as e:
                    self.logger.debug(f"Erreur extraction section {selector_group}: {e}")
            
            # Méthode 2: Extraction par items de crédits individuels
            if len(credits) < 3:  # Si peu de crédits trouvés, méthode alternative
                for selector_group in self.selectors['credit_item']:
                    try:
                        items = driver.find_elements(By.CSS_SELECTOR, selector_group)
                        
                        for item in items:
                            item_credit = self._extract_credit_from_item(item)
                            if item_credit:
                                credits.append(item_credit)
                                
                    except Exception as e:
                        self.logger.debug(f"Erreur extraction item {selector_group}: {e}")
            
            # Méthode 3: Extraction par analyse de texte si très peu de résultats
            if len(credits) < 2:
                text_credits = self._extract_credits_from_page_text(driver)
                credits.extend(text_credits)
            
            # Déduplication et nettoyage
            credits = self._clean_and_deduplicate_credits(credits)
            
            self.logger.debug(f"🎯 Total crédits extraits: {len(credits)}")
            
        except Exception as e:
            self.logger.error(f"❌ Erreur extraction crédits: {e}")
        
        return credits
    
    def _extract_credits_from_section(self, section) -> List[Dict[str, Any]]:
        """Extrait les crédits d'une section spécifique"""
        credits = []
        
        try:
            # Rechercher le titre de la section (type de crédit)
            credit_role = None
            
            for role_selector in self.selectors['credit_role']:
                try:
                    role_elem = section.find_element(By.CSS_SELECTOR, role_selector)
                    credit_role = self._extract_text_safe(role_elem)
                    if credit_role:
                        break
                except NoSuchElementException:
                    continue
            
            # Si pas de rôle trouvé, essayer d'autres méthodes
            if not credit_role:
                # Essayer de trouver dans le texte parent
                section_text = self._extract_text_safe(section)
                credit_role = self._infer_credit_role_from_text(section_text)
            
            # Rechercher les personnes/artistes dans cette section
            for person_selector in self.selectors['credit_person']:
                try:
                    person_elems = section.find_elements(By.CSS_SELECTOR, person_selector)
                    
                    for person_elem in person_elems:
                        person_name = self._extract_text_safe(person_elem)
                        person_url = person_elem.get_attribute('href') if person_elem.tag_name == 'a' else None
                        
                        if person_name:
                            credit = {
                                'credit_type': self._normalize_credit_role(credit_role or 'Unknown'),
                                'credit_category': self._categorize_credit(credit_role or 'Unknown'),
                                'person_name': person_name.strip(),
                                'person_url': person_url,
                                'source_section': self._extract_text_safe(section)[:100],
                                'extraction_method': 'section_parsing'
                            }
                            credits.append(credit)
                            
                except Exception as e:
                    self.logger.debug(f"Erreur extraction personne: {e}")
            
            # Si pas de personnes trouvées avec les sélecteurs, analyser le texte
            if not credits and credit_role:
                section_text = self._extract_text_safe(section)
                text_credits = self._extract_credits_from_text(section_text, credit_role)
                credits.extend(text_credits)
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction section: {e}")
        
        return credits
    
    def _extract_credit_from_item(self, item) -> Optional[Dict[str, Any]]:
        """Extrait un crédit depuis un item individuel"""
        try:
            item_text = self._extract_text_safe(item)
            if not item_text:
                return None
            
            # Rechercher un lien d'artiste dans l'item
            person_url = None
            person_name = None
            
            try:
                link_elem = item.find_element(By.CSS_SELECTOR, 'a[href*="/artists/"]')
                person_url = link_elem.get_attribute('href')
                person_name = self._extract_text_safe(link_elem)
            except NoSuchElementException:
                # Pas de lien, extraire le nom depuis le texte
                person_name = item_text.strip()
            
            # Inférer le type de crédit depuis le contexte
            credit_role = self._infer_credit_role_from_text(item_text)
            
            return {
                'credit_type': self._normalize_credit_role(credit_role),
                'credit_category': self._categorize_credit(credit_role),
                'person_name': person_name,
                'person_url': person_url,
                'source_text': item_text,
                'extraction_method': 'item_parsing'
            }
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction item: {e}")
            return None
    
    def _extract_credits_from_page_text(self, driver) -> List[Dict[str, Any]]:
        """Méthode de fallback: extraction par analyse du texte complet"""
        credits = []
        
        try:
            # Récupérer tout le texte de la page
            page_text = driver.find_element(By.TAG_NAME, 'body').text
            
            # Analyser le texte avec les patterns de crédits
            for category, patterns in self.credit_patterns.items():
                for pattern in patterns:
                    matches = pattern.finditer(page_text)
                    
                    for match in matches:
                        # Extraire le contexte autour du match
                        start = max(0, match.start() - 50)
                        end = min(len(page_text), match.end() + 100)
                        context = page_text[start:end]
                        
                        # Essayer d'extraire les noms des personnes depuis le contexte
                        extracted_credits = self._parse_credits_from_context(context, category)
                        credits.extend(extracted_credits)
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction texte page: {e}")
        
        return credits
    
    def _extract_credits_from_text(self, text: str, base_role: str) -> List[Dict[str, Any]]:
        """Extrait les crédits depuis un texte en utilisant les patterns"""
        credits = []
        
        try:
            # Normaliser le texte
            normalized_text = normalize_text(text)
            
            # Séparer les noms (patterns communs)
            separators = [',', ';', '&', ' and ', ' et ', '\n']
            parts = [text]
            
            for sep in separators:
                new_parts = []
                for part in parts:
                    new_parts.extend(part.split(sep))
                parts = new_parts
            
            # Nettoyer et créer les crédits
            for part in parts:
                cleaned_name = part.strip()
                if cleaned_name and len(cleaned_name) > 1:
                    # Filtrer les mots-clés non pertinents
                    if not any(keyword in cleaned_name.lower() for keyword in 
                              ['produced', 'mixed', 'written', 'by', 'credits', 'show', 'more']):
                        
                        credit = {
                            'credit_type': self._normalize_credit_role(base_role),
                            'credit_category': self._categorize_credit(base_role),
                            'person_name': cleaned_name,
                            'person_url': None,
                            'source_text': text,
                            'extraction_method': 'text_parsing'
                        }
                        credits.append(credit)
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction texte: {e}")
        
        return credits
    
    @lru_cache(maxsize=256)
    def _infer_credit_role_from_text(self, text: str) -> str:
        """Infère le type de crédit depuis le texte avec cache"""
        if not text:
            return "Unknown"
        
        text_lower = text.lower()
        
        # Recherche de patterns dans le texte
        for category, patterns in self.credit_patterns.items():
            for pattern in patterns:
                if pattern.search(text_lower):
                    return category.replace('_roles', '').replace('_', ' ').title()
        
        # Patterns spécifiques simples
        if any(word in text_lower for word in ['produc', 'beat', 'instrumental']):
            return "Producer"
        elif any(word in text_lower for word in ['mix', 'engineer']):
            return "Engineer"
        elif any(word in text_lower for word in ['writ', 'lyric', 'compos']):
            return "Songwriter"
        elif any(word in text_lower for word in ['vocal', 'perform', 'feat']):
            return "Performer"
        
        return "Contributor"
    
    @lru_cache(maxsize=128)
    def _normalize_credit_role(self, role: str) -> str:
        """Normalise un rôle de crédit avec cache"""
        if not role:
            return "Unknown"
        
        role_lower = role.lower().strip()
        
        # Mapping des rôles normalisés
        role_mapping = {
            'producer': 'Producer',
            'produced by': 'Producer',
            'production': 'Producer',
            'beat by': 'Producer',
            'instrumental': 'Producer',
            'songwriter': 'Songwriter',
            'written by': 'Songwriter',
            'lyrics by': 'Songwriter',
            'composed by': 'Songwriter',
            'mixed by': 'Mix Engineer',
            'mastered by': 'Master Engineer',
            'recorded by': 'Recording Engineer',
            'engineered by': 'Engineer',
            'performed by': 'Performer',
            'vocals by': 'Vocalist',
            'featuring': 'Featured Artist',
            'executive producer': 'Executive Producer'
        }
        
        return role_mapping.get(role_lower, role.title())
    
    @lru_cache(maxsize=64)
    def _categorize_credit(self, role: str) -> str:
        """Catégorise un crédit selon son type avec cache"""
        if not role:
            return CreditCategory.OTHER.value
        
        role_lower = role.lower()
        
        if any(word in role_lower for word in ['produc', 'beat', 'instrumental']):
            return CreditCategory.PRODUCTION.value
        elif any(word in role_lower for word in ['writ', 'lyric', 'compos']):
            return CreditCategory.WRITING.value
        elif any(word in role_lower for word in ['mix', 'master', 'engineer', 'record']):
            return CreditCategory.ENGINEERING.value
        elif any(word in role_lower for word in ['vocal', 'perform', 'feat', 'sing']):
            return CreditCategory.PERFORMANCE.value
        
        return CreditCategory.OTHER.value
    
    def _clean_and_deduplicate_credits(self, credits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Nettoie et déduplique la liste des crédits"""
        if not credits:
            return []
        
        cleaned_credits = []
        seen_combinations = set()
        
        for credit in credits:
            # Nettoyage des données
            person_name = credit.get('person_name', '').strip()
            credit_type = credit.get('credit_type', '').strip()
            
            if not person_name or len(person_name) < 2:
                continue
            
            # Créer une clé unique pour déduplication
            dedup_key = (person_name.lower(), credit_type.lower())
            
            if dedup_key not in seen_combinations:
                seen_combinations.add(dedup_key)
                
                # Crédit nettoyé
                cleaned_credit = {
                    'credit_type': credit_type or 'Unknown',
                    'credit_category': credit.get('credit_category', CreditCategory.OTHER.value),
                    'person_name': person_name,
                    'person_url': credit.get('person_url'),
                    'source_text': credit.get('source_text', ''),
                    'extraction_method': credit.get('extraction_method', 'unknown')
                }
                
                cleaned_credits.append(cleaned_credit)
        
        self.logger.debug(f"🧹 Nettoyage: {len(cleaned_credits)}/{len(credits)} crédits conservés")
        return cleaned_credits
    
    def _extract_track_metadata(self, driver) -> Dict[str, Any]:
        """Extrait les métadonnées de la track"""
        metadata = {}
        
        try:
            # Titre de la track
            for selector in self.selectors['song_header']:
                try:
                    title_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    metadata['title'] = self._extract_text_safe(title_elem)
                    break
                except NoSuchElementException:
                    continue
            
            # Informations d'album
            for selector in self.selectors['album_info']:
                try:
                    album_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    album_text = self._extract_text_safe(album_elem)
                    if album_text:
                        metadata['album_info'] = album_text
                        break
                except NoSuchElementException:
                    continue
            
            # URL de la page
            metadata['page_url'] = driver.current_url
            
            # Timestamp d'extraction
            metadata['extracted_at'] = datetime.now().isoformat()
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction métadonnées: {e}")
        
        return metadata
    
    def _extract_lyrics(self, driver) -> Optional[str]:
        """Extrait les paroles si configuré"""
        if not self.config['extract_lyrics']:
            return None
        
        try:
            for selector in self.selectors['lyrics_container']:
                try:
                    lyrics_elem = driver.find_element(By.CSS_SELECTOR, selector)
                    lyrics_text = self._extract_text_safe(lyrics_elem)
                    if lyrics_text and len(lyrics_text) > 50:  # Validation basique
                        return lyrics_text
                except NoSuchElementException:
                    continue
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction paroles: {e}")
        
        return None
    
    def _extract_text_safe(self, element) -> str:
        """Extraction sécurisée de texte depuis un élément"""
        try:
            if element:
                return element.text.strip()
        except Exception:
            pass
        return ""
    
    def _parse_credits_from_context(self, context: str, category: str) -> List[Dict[str, Any]]:
        """Parse les crédits depuis un contexte textuel"""
        credits = []
        
        try:
            # Extraction basique des noms après patterns
            lines = context.split('\n')
            for line in lines:
                line = line.strip()
                if line and len(line) > 2:
                    # Recherche de noms (heuristique simple)
                    if any(char.isupper() for char in line) and not line.isupper():
                        credit = {
                            'credit_type': category.replace('_roles', '').title(),
                            'credit_category': self._categorize_credit(category),
                            'person_name': line,
                            'person_url': None,
                            'source_text': context,
                            'extraction_method': 'context_parsing'
                        }
                        credits.append(credit)
        
        except Exception as e:
            self.logger.debug(f"Erreur parse contexte: {e}")
        
        return credits
    
    def _url_to_cache_key(self, url: str) -> str:
        """Convertit une URL en clé de cache valide"""
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    # ===== MÉTHODES BATCH ET UTILITAIRES =====
    
    def batch_scrape_tracks(self, track_urls: List[str], max_workers: int = 2) -> List[Dict[str, Any]]:
        """
        Scrape plusieurs tracks en mode batch avec parallélisation contrôlée.
        
        Args:
            track_urls: Liste des URLs de tracks
            max_workers: Nombre de workers parallèles (limité pour éviter la détection)
            
        Returns:
            Liste des résultats
        """
        results = []
        total_urls = len(track_urls)
        
        self.logger.info(f"🚀 Démarrage batch scraping: {total_urls} tracks")
        
        try:
            import concurrent.futures
            
            def scrape_single_track(url: str) -> Dict[str, Any]:
                try:
                    # Délai aléatoire entre requêtes pour éviter la détection
                    import random
                    time.sleep(random.uniform(1, 3))
                    
                    return self.scrape_track_credits(url)
                    
                except Exception as e:
                    return {
                        'success': False,
                        'url': url,
                        'error': str(e),
                        'credits': []
                    }
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_url = {executor.submit(scrape_single_track, url): url for url in track_urls}
                
                for future in concurrent.futures.as_completed(future_to_url):
                    result = future.result()
                    results.append(result)
                    
                    # Log du progrès
                    progress = len(results)
                    success_count = len([r for r in results if r.get('success', False)])
                    self.logger.info(f"📊 Progrès: {progress}/{total_urls} - {success_count} succès")
        
        except ImportError:
            self.logger.warning("⚠️ concurrent.futures non disponible, scraping séquentiel")
            
            # Fallback séquentiel
            for i, url in enumerate(track_urls):
                try:
                    result = self.scrape_track_credits(url)
                    results.append(result)
                    
                    # Rate limiting
                    time.sleep(2)
                    
                    # Log du progrès
                    success_count = len([r for r in results if r.get('success', False)])
                    self.logger.info(f"📊 Progrès: {i+1}/{total_urls} - {success_count} succès")
                    
                except Exception as e:
                    results.append({
                        'success': False,
                        'url': url,
                        'error': str(e),
                        'credits': []
                    })
        
        # Mise à jour des statistiques moyennes
        if self.stats['pages_scraped'] > 0:
            self.stats['average_page_time'] = self.stats['total_time_spent'] / self.stats['pages_scraped']
        
        self.logger.info(f"🏁 Batch scraping terminé: {len([r for r in results if r.get('success')])} succès sur {total_urls}")
        
        return results
    
    @lru_cache(maxsize=1)
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance avec cache"""
        stats = self.stats.copy()
        
        # Calculs additionnels
        if stats['pages_scraped'] > 0:
            stats['success_rate'] = ((stats['pages_scraped'] - stats['failed_extractions']) / stats['pages_scraped']) * 100
            stats['average_credits_per_page'] = stats['credits_extracted'] / stats['pages_scraped']
        else:
            stats['success_rate'] = 0.0
            stats['average_credits_per_page'] = 0.0
        
        return stats
    
    def reset_stats(self) -> None:
        """Remet à zéro les statistiques"""
        self.stats = {
            'pages_scraped': 0,
            'credits_extracted': 0,
            'expand_buttons_clicked': 0,
            'failed_extractions': 0,
            'cache_hits': 0,
            'total_time_spent': 0.0,
            'average_page_time': 0.0
        }
        
        # Vider les caches LRU
        self.get_stats.cache_clear()
        self._infer_credit_role_from_text.cache_clear()
        self._normalize_credit_role.cache_clear()
        self._categorize_credit.cache_clear()
        
        self.logger.info("📊 Statistiques GeniusWebScraper réinitialisées")
    
    def __enter__(self):
        """Support du context manager"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Nettoyage automatique"""
        try:
            if hasattr(self, 'selenium_manager'):
                self.selenium_manager.__exit__(exc_type, exc_val, exc_tb)
        except Exception as e:
            self.logger.debug(f"Erreur nettoyage: {e}")


# ===== FONCTIONS UTILITAIRES MODULE =====

def create_genius_scraper() -> Optional[GeniusWebScraper]:
    """
    Factory function pour créer une instance GeniusWebScraper.
    
    Returns:
        Instance GeniusWebScraper ou None si échec
    """
    try:
        return GeniusWebScraper()
    except Exception as e:
        logging.getLogger(__name__).error(f"❌ Impossible de créer GeniusWebScraper: {e}")
        return None


def extract_artist_credits_complete(artist_genius_urls: List[str]) -> Dict[str, Any]:
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
        }