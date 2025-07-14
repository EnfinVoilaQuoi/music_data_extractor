# utils/selenium_manager.py
import logging
import time
import random
from typing import Optional, Dict, List, Any, Callable
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import (
        TimeoutException, 
        NoSuchElementException, 
        ElementClickInterceptedException,
        StaleElementReferenceException,
        WebDriverException
    )
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from ..config.settings import settings  # CORRECTION: Import relatif correct
from ..core.exceptions import ScrapingError, SeleniumError  # CORRECTION: Import relatif correct
from ..core.rate_limiter import RateLimiter  # CORRECTION: Import relatif correct

class SeleniumManager:
    """
    Gestionnaire Selenium pour le scraping web intelligent.
    
    Fonctionnalités :
    - Gestion automatique du WebDriver
    - Anti-détection (user agents, délais aléatoires)
    - Retry automatique sur les erreurs
    - Screenshots en cas d'erreur
    - Gestion des popups et cookies
    """
    
    def __init__(self):
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium n'est pas installé. Installez-le avec: pip install selenium webdriver-manager")
        
        self.logger = logging.getLogger(__name__)
        
        # Configuration depuis settings
        self.config = {
            'headless': settings.get('selenium.headless', True),
            'timeout': settings.get('selenium.timeout', 30),
            'retry_failed_pages': settings.get('selenium.retry_failed_pages', 2),
            'screenshot_on_error': settings.get('selenium.screenshot_on_error', True),
            'browser': settings.get('selenium.browser', 'chrome')
        }
        
        # Rate limiter pour éviter les blocages
        self.rate_limiter = RateLimiter(
            requests_per_period=settings.get('rate_limits.web_scraping.requests_per_minute', 20),
            period_seconds=60
        )
        
        # Driver WebDriver actuel
        self.driver: Optional[webdriver.Chrome] = None
        self.driver_created_at: Optional[datetime] = None
        
        # Statistiques
        self.stats = {
            'pages_visited': 0,
            'successful_scrapes': 0,
            'failed_scrapes': 0,
            'retries_performed': 0,
            'screenshots_taken': 0
        }
        
        # User agents pour rotation
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
        ]
        
        self.logger.info("SeleniumManager initialisé")
    
    def _create_driver(self) -> webdriver.Chrome:
        """Crée et configure un nouveau WebDriver Chrome"""
        try:
            # Options Chrome
            options = Options()
            
            if self.config['headless']:
                options.add_argument('--headless')
            
            # Options anti-détection
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # User agent aléatoire
            user_agent = random.choice(self.user_agents)
            options.add_argument(f'--user-agent={user_agent}')
            
            # Autres options utiles
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            options.add_argument('--disable-images')  # Plus rapide
            
            # Taille de fenêtre
            options.add_argument('--window-size=1920,1080')
            
            # Service avec WebDriver Manager
            service = Service(ChromeDriverManager().install())
            
            # Création du driver
            driver = webdriver.Chrome(service=service, options=options)
            
            # Configuration supplémentaire
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": user_agent})
            
            # Timeouts
            driver.implicitly_wait(10)
            driver.set_page_load_timeout(self.config['timeout'])
            
            self.driver_created_at = datetime.now()
            self.logger.info(f"WebDriver Chrome créé (User-Agent: {user_agent[:50]}...)")
            
            return driver
            
        except Exception as e:
            raise SeleniumError("driver_creation", str(e))
    
    @contextmanager
    def get_driver(self):
        """Context manager pour utiliser le WebDriver"""
        if self.driver is None:
            self.driver = self._create_driver()
        
        try:
            yield self.driver
        except Exception as e:
            # Screenshot en cas d'erreur si configuré
            if self.config['screenshot_on_error']:
                self._take_screenshot(f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            raise
        finally:
            # Optionnel: fermer le driver après chaque utilisation
            # self._close_driver()
            pass
    
    def navigate_to(self, url: str, max_retries: Optional[int] = None) -> bool:
        """
        Navigue vers une URL avec retry automatique.
        
        Args:
            url: URL à visiter
            max_retries: Nombre maximum de tentatives
            
        Returns:
            True si succès, False sinon
        """
        max_retries = max_retries or self.config['retry_failed_pages']
        
        for attempt in range(max_retries + 1):
            try:
                # Rate limiting
                self.rate_limiter.wait_if_needed('web_scraping')
                
                with self.get_driver() as driver:
                    # Délai aléatoire anti-détection
                    if attempt > 0:
                        delay = random.uniform(2, 5)
                        time.sleep(delay)
                    
                    self.logger.info(f"Navigation vers: {url} (tentative {attempt + 1})")
                    driver.get(url)
                    
                    # Attendre que la page soit chargée
                    WebDriverWait(driver, self.config['timeout']).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    # Gestion des popups/cookies courants
                    self._handle_common_popups(driver)
                    
                    self.stats['pages_visited'] += 1
                    self.stats['successful_scrapes'] += 1
                    
                    return True
                    
            except TimeoutException:
                self.logger.warning(f"Timeout lors du chargement de {url} (tentative {attempt + 1})")
                self.stats['failed_scrapes'] += 1
                
            except WebDriverException as e:
                self.logger.warning(f"Erreur WebDriver pour {url}: {e} (tentative {attempt + 1})")
                self.stats['failed_scrapes'] += 1
                
                # Recréer le driver si erreur critique
                if "chrome not reachable" in str(e).lower():
                    self._close_driver()
                
            except Exception as e:
                self.logger.error(f"Erreur inattendue lors de la navigation vers {url}: {e}")
                self.stats['failed_scrapes'] += 1
            
            if attempt < max_retries:
                self.stats['retries_performed'] += 1
                delay = random.uniform(3, 7) * (attempt + 1)  # Backoff exponentiel
                self.logger.info(f"Nouvelle tentative dans {delay:.1f}s...")
                time.sleep(delay)
        
        self.logger.error(f"Échec de navigation vers {url} après {max_retries + 1} tentatives")
        return False
    
    def find_element_safe(self, by: By, value: str, timeout: int = 10) -> Optional[Any]:
        """
        Trouve un élément de manière sécurisée avec timeout.
        
        Args:
            by: Type de sélecteur (By.CLASS_NAME, By.ID, etc.)
            value: Valeur du sélecteur
            timeout: Timeout en secondes
            
        Returns:
            Element trouvé ou None
        """
        try:
            with self.get_driver() as driver:
                element = WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
                return element
        except TimeoutException:
            self.logger.debug(f"Element non trouvé: {by}='{value}' (timeout {timeout}s)")
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de la recherche d'élément {by}='{value}': {e}")
            return None
    
    def find_elements_safe(self, by: By, value: str, timeout: int = 10) -> List[Any]:
        """
        Trouve plusieurs éléments de manière sécurisée.
        
        Args:
            by: Type de sélecteur
            value: Valeur du sélecteur
            timeout: Timeout en secondes
            
        Returns:
            Liste des éléments trouvés
        """
        try:
            with self.get_driver() as driver:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((by, value))
                )
                return driver.find_elements(by, value)
        except TimeoutException:
            self.logger.debug(f"Aucun élément trouvé: {by}='{value}'")
            return []
        except Exception as e:
            self.logger.warning(f"Erreur lors de la recherche d'éléments {by}='{value}': {e}")
            return []
    
    def click_element_safe(self, element, max_retries: int = 3) -> bool:
        """
        Clique sur un élément de manière sécurisée avec retry.
        
        Args:
            element: Element WebDriver à cliquer
            max_retries: Nombre maximum de tentatives
            
        Returns:
            True si succès, False sinon
        """
        for attempt in range(max_retries):
            try:
                # Scroll vers l'élément si nécessaire
                with self.get_driver() as driver:
                    driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(0.5)  # Petite pause après scroll
                    
                    # Clic
                    element.click()
                    return True
                    
            except ElementClickInterceptedException:
                self.logger.warning(f"Clic intercepté, tentative {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    
            except StaleElementReferenceException:
                self.logger.warning(f"Référence d'élément obsolète, tentative {attempt + 1}")
                return False  # Impossible de retry avec une référence obsolète
                
            except Exception as e:
                self.logger.warning(f"Erreur lors du clic (tentative {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
        
        return False
    
    def extract_text_safe(self, element) -> str:
        """
        Extrait le texte d'un élément de manière sécurisée.
        
        Args:
            element: Element WebDriver
            
        Returns:
            Texte extrait ou chaîne vide
        """
        try:
            return element.text.strip()
        except StaleElementReferenceException:
            self.logger.warning("Référence d'élément obsolète lors de l'extraction de texte")
            return ""
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction de texte: {e}")
            return ""
    
    def wait_for_element_clickable(self, by: By, value: str, timeout: int = 10) -> Optional[Any]:
        """
        Attend qu'un élément soit cliquable.
        
        Args:
            by: Type de sélecteur
            value: Valeur du sélecteur
            timeout: Timeout en secondes
            
        Returns:
            Element cliquable ou None
        """
        try:
            with self.get_driver() as driver:
                element = WebDriverWait(driver, timeout).until(
                    EC.element_to_be_clickable((by, value))
                )
                return element
        except TimeoutException:
            self.logger.debug(f"Element non cliquable dans les temps: {by}='{value}'")
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'attente de cliquabilité: {e}")
            return None
    
    def execute_script_safe(self, script: str, *args) -> Any:
        """
        Exécute du JavaScript de manière sécurisée.
        
        Args:
            script: Code JavaScript à exécuter
            *args: Arguments pour le script
            
        Returns:
            Résultat du script ou None
        """
        try:
            with self.get_driver() as driver:
                return driver.execute_script(script, *args)
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'exécution du script: {e}")
            return None
    
    def _handle_common_popups(self, driver):
        """Gère les popups et bannières de cookies courants"""
        popup_selectors = [
            # Cookies
            "button[id*='accept']",
            "button[class*='accept']",
            "button[id*='cookie']",
            "button[class*='cookie']",
            ".cookie-accept",
            ".accept-cookies",
            
            # GDPR
            "button[id*='consent']",
            "button[class*='consent']",
            ".consent-accept",
            
            # Génériques
            "button[aria-label*='Accept']",
            "button[aria-label*='Accepter']",
            "button[data-testid*='accept']"
        ]
        
        for selector in popup_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        self.logger.debug(f"Fermeture popup avec sélecteur: {selector}")
                        element.click()
                        time.sleep(0.5)
                        break
            except Exception:
                continue  # Ignorer les erreurs de popup
    
    def _take_screenshot(self, filename: str):
        """Prend une capture d'écran"""
        try:
            if self.driver:
                screenshot_dir = settings.logs_dir / "screenshots"
                screenshot_dir.mkdir(exist_ok=True)
                
                filepath = screenshot_dir / f"{filename}.png"
                self.driver.save_screenshot(str(filepath))
                
                self.stats['screenshots_taken'] += 1
                self.logger.info(f"Screenshot sauvegardée: {filepath}")
        except Exception as e:
            self.logger.warning(f"Erreur lors de la capture d'écran: {e}")
    
    def _close_driver(self):
        """Ferme le WebDriver proprement"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("WebDriver fermé")
            except Exception as e:
                self.logger.warning(f"Erreur lors de la fermeture du WebDriver: {e}")
            finally:
                self.driver = None
                self.driver_created_at = None
    
    def restart_driver(self):
        """Force le redémarrage du WebDriver"""
        self.logger.info("Redémarrage forcé du WebDriver")
        self._close_driver()
        # Le driver sera recréé automatiquement au prochain usage
    
    def get_page_source(self) -> str:
        """Récupère le source HTML de la page actuelle"""
        try:
            with self.get_driver() as driver:
                return driver.page_source
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération du source: {e}")
            return ""
    
    def get_current_url(self) -> str:
        """Récupère l'URL actuelle"""
        try:
            with self.get_driver() as driver:
                return driver.current_url
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération de l'URL: {e}")
            return ""
    
    def set_window_size(self, width: int, height: int):
        """Définit la taille de la fenêtre"""
        try:
            with self.get_driver() as driver:
                driver.set_window_size(width, height)
        except Exception as e:
            self.logger.warning(f"Erreur lors du redimensionnement: {e}")
    
    def add_cookies(self, cookies: List[Dict[str, Any]]):
        """Ajoute des cookies au navigateur"""
        try:
            with self.get_driver() as driver:
                for cookie in cookies:
                    driver.add_cookie(cookie)
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'ajout de cookies: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'utilisation"""
        stats = self.stats.copy()
        
        if self.stats['pages_visited'] > 0:
            stats['success_rate'] = (self.stats['successful_scrapes'] / self.stats['pages_visited']) * 100
        else:
            stats['success_rate'] = 0.0
        
        # Temps de fonctionnement du driver
        if self.driver_created_at:
            uptime = datetime.now() - self.driver_created_at
            stats['driver_uptime_seconds'] = uptime.total_seconds()
        else:
            stats['driver_uptime_seconds'] = 0
        
        return stats
    
    def reset_stats(self):
        """Remet à zéro les statistiques"""
        self.stats = {
            'pages_visited': 0,
            'successful_scrapes': 0,
            'failed_scrapes': 0,
            'retries_performed': 0,
            'screenshots_taken': 0
        }
    
    def __enter__(self):
        """Support du context manager"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Nettoyage automatique à la sortie"""
        self._close_driver()

# Fonctions utilitaires pour un usage simple

def scrape_with_selenium(url: str, scraping_function: Callable, max_retries: int = 2) -> Any:
    """
    Fonction utilitaire pour scraper une page avec Selenium.
    
    Args:
        url: URL à scraper
        scraping_function: Fonction qui prend le WebDriver et retourne les données
        max_retries: Nombre maximum de tentatives
        
    Returns:
        Résultat de scraping_function ou None
    """
    with SeleniumManager() as manager:
        if manager.navigate_to(url, max_retries):
            try:
                with manager.get_driver() as driver:
                    return scraping_function(driver)
            except Exception as e:
                logging.getLogger(__name__).error(f"Erreur dans scraping_function: {e}")
                return None
        return None

def extract_genius_credits(track_url: str) -> List[Dict[str, str]]:
    """
    Exemple d'utilisation : extraction des crédits depuis une page Genius.
    
    Args:
        track_url: URL de la page Genius du morceau
        
    Returns:
        Liste des crédits trouvés
    """
    def scrape_credits(driver):
        credits = []
        
        # Chercher les sections de crédits
        credit_sections = driver.find_elements(By.CSS_SELECTOR, "[class*='SongCredit']")
        
        for section in credit_sections:
            try:
                # Type de crédit
                credit_type_elem = section.find_element(By.CSS_SELECTOR, "h3, .credit-type")
                credit_type = credit_type_elem.text.strip()
                
                # Personnes/entités
                people_elems = section.find_elements(By.CSS_SELECTOR, "a[href*='/artists/']")
                
                for person_elem in people_elems:
                    person_name = person_elem.text.strip()
                    if person_name:
                        credits.append({
                            'type': credit_type,
                            'person': person_name,
                            'source': 'genius_selenium'
                        })
                        
            except Exception as e:
                logging.getLogger(__name__).warning(f"Erreur extraction crédit: {e}")
                continue
        
        return credits
    
    return scrape_with_selenium(track_url, scrape_credits) or []