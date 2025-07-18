# extractors/web_scrapers/__init__.py
"""
Module web scrapers optimisé avec imports sécurisés et diagnostics avancés.
Version corrigée sans imports circulaires.
"""

import logging
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple, Callable
import importlib
import sys

__version__ = "1.0.0"
__all__ = []

# Configuration du logger
logger = logging.getLogger(__name__)

# Statistiques d'imports
_import_stats = {
    'successful': [],
    'failed': [],
    'total_attempts': 0
}

def _safe_import(module_name: str, class_names: List[str]) -> Tuple[bool, Optional[Exception]]:
    """
    Import sécurisé avec tracking des erreurs.
    
    Args:
        module_name: Nom du module à importer (sans le préfixe)
        class_names: Liste des classes à importer
        
    Returns:
        Tuple (succès, erreur_éventuelle)
    """
    global _import_stats
    _import_stats['total_attempts'] += 1
    
    try:
        # Import relatif depuis le package actuel
        module = importlib.import_module(f'.{module_name}', package=__name__)
        
        for class_name in class_names:
            if hasattr(module, class_name):
                globals()[class_name] = getattr(module, class_name)
                __all__.append(class_name)
            else:
                logger.warning(f"⚠️ Classe {class_name} non trouvée dans {module_name}")
        
        _import_stats['successful'].append(module_name)
        logger.debug(f"✅ {module_name} importé avec succès")
        return True, None
        
    except ImportError as e:
        _import_stats['failed'].append({'module': module_name, 'error': str(e)})
        logger.debug(f"⚠️ Échec import {module_name}: {e}")
        return False, e
    except Exception as e:
        _import_stats['failed'].append({'module': module_name, 'error': f"Erreur inattendue: {str(e)}"})
        logger.error(f"❌ Erreur inattendue lors de l'import {module_name}: {e}")
        return False, e

# ===== IMPORTS PRINCIPAUX =====

# 1. Scrapers web principaux
_safe_import('genius_scraper', ['GeniusWebScraper'])
_safe_import('rapedia_scraper', ['RapediaScraper'])

# 2. Scrapers web additionnels (optionnels)
_safe_import('lastfm_scraper', ['LastFMScraper'])
_safe_import('discogs_scraper', ['DiscogsScraper'])
_safe_import('bandcamp_scraper', ['BandcampScraper'])

# ===== IMPORTS UTILITAIRES SÉCURISÉS =====

def _import_text_utils():
    """Import sécurisé des utilitaires de texte"""
    try:
        # Essai d'import depuis utils (niveau racine)
        from utils.text_utils import (
            clean_artist_name, normalize_text, clean_track_title,
            extract_featuring_artists, calculate_similarity
        )
        
        # Ajout au namespace global
        globals().update({
            'clean_artist_name': clean_artist_name,
            'normalize_text': normalize_text,
            'clean_track_title': clean_track_title,
            'extract_featuring_artists': extract_featuring_artists,
            'calculate_similarity': calculate_similarity
        })
        
        __all__.extend([
            'clean_artist_name', 'normalize_text', 'clean_track_title',
            'extract_featuring_artists', 'calculate_similarity'
        ])
        
        logger.debug("✅ Text utils importées depuis utils.text_utils")
        return True
        
    except ImportError:
        logger.warning("⚠️ Impossible d'importer text_utils depuis utils")
        
        # Fallback: créer des fonctions de base
        def clean_artist_name(name: str) -> str:
            """Fallback pour clean_artist_name"""
            return name.strip() if name else ""
        
        def normalize_text(text: str) -> str:
            """Fallback pour normalize_text"""
            return text.lower().strip() if text else ""
        
        def clean_track_title(title: str) -> str:
            """Fallback pour clean_track_title"""
            return title.strip() if title else ""
        
        def extract_featuring_artists(title: str) -> Tuple[str, List[str]]:
            """Fallback pour extract_featuring_artists"""
            return title, []
        
        def calculate_similarity(text1: str, text2: str) -> float:
            """Fallback pour calculate_similarity"""
            return 1.0 if text1.lower() == text2.lower() else 0.0
        
        # Ajout des fallbacks au namespace
        globals().update({
            'clean_artist_name': clean_artist_name,
            'normalize_text': normalize_text,
            'clean_track_title': clean_track_title,
            'extract_featuring_artists': extract_featuring_artists,
            'calculate_similarity': calculate_similarity
        })
        
        __all__.extend([
            'clean_artist_name', 'normalize_text', 'clean_track_title',
            'extract_featuring_artists', 'calculate_similarity'
        ])
        
        logger.info("✅ Fonctions text_utils de fallback créées")
        return False

# Import des text utils
_import_text_utils()

# ===== FONCTIONS FACTORY DYNAMIQUES =====

def get_discovery_step():
    """Import dynamique de DiscoveryStep pour éviter les imports circulaires"""
    try:
        from steps.step1_discover import DiscoveryStep
        return DiscoveryStep
    except ImportError as e:
        logger.warning(f"⚠️ Impossible d'importer DiscoveryStep: {e}")
        return None

def get_extraction_step():
    """Import dynamique d'ExtractionStep pour éviter les imports circulaires"""
    try:
        from steps.step2_extract import ExtractionStep
        return ExtractionStep
    except ImportError as e:
        logger.warning(f"⚠️ Impossible d'importer ExtractionStep: {e}")
        return None

def get_processing_step():
    """Import dynamique de ProcessingStep pour éviter les imports circulaires"""
    try:
        from steps.step3_process import ProcessingStep
        return ProcessingStep
    except ImportError as e:
        logger.warning(f"⚠️ Impossible d'importer ProcessingStep: {e}")
        return None

def get_export_step():
    """Import dynamique d'ExportStep pour éviter les imports circulaires"""
    try:
        from steps.step4_export import ExportStep
        return ExportStep
    except ImportError as e:
        logger.warning(f"⚠️ Impossible d'importer ExportStep: {e}")
        return None

# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_available_scrapers() -> List[str]:
    """
    Retourne la liste des scrapers disponibles avec cache.
    
    Returns:
        Liste des classes de scraping disponibles
    """
    return [name for name in __all__ if name.endswith('Scraper')]

@lru_cache(maxsize=1)
def get_utility_functions() -> List[str]:
    """
    Retourne la liste des fonctions utilitaires disponibles.
    
    Returns:
        Liste des fonctions utilitaires
    """
    return [name for name in __all__ if not name.endswith('Scraper')]

@lru_cache(maxsize=1)
def get_import_stats() -> Dict[str, Any]:
    """
    Retourne les statistiques d'import avec cache.
    
    Returns:
        Dictionnaire des statistiques d'import
    """
    return {
        'total_modules_attempted': _import_stats['total_attempts'],
        'successful_imports': len(_import_stats['successful']),
        'failed_imports': len(_import_stats['failed']),
        'success_rate': (len(_import_stats['successful']) / max(_import_stats['total_attempts'], 1)) * 100,
        'available_scrapers': get_available_scrapers(),
        'utility_functions': get_utility_functions(),
        'successful_modules': _import_stats['successful'],
        'failed_modules': _import_stats['failed']
    }

def create_scraper(scraper_type: str, **kwargs) -> Optional[Any]:
    """
    Factory pour créer un scraper avec gestion d'erreurs.
    
    Args:
        scraper_type: Type de scraper ('genius', 'rapedia', etc.)
        **kwargs: Arguments pour le constructeur
        
    Returns:
        Instance du scraper ou None si échec
    """
    scraper_mapping = {
        'genius': 'GeniusWebScraper',
        'genius_scraper': 'GeniusWebScraper',
        'rapedia': 'RapediaScraper',
        'rapedia_scraper': 'RapediaScraper',
        'lastfm': 'LastFMScraper',
        'lastfm_scraper': 'LastFMScraper',
        'discogs': 'DiscogsScraper',
        'discogs_scraper': 'DiscogsScraper',
        'bandcamp': 'BandcampScraper',
        'bandcamp_scraper': 'BandcampScraper'
    }
    
    class_name = scraper_mapping.get(scraper_type.lower())
    if not class_name:
        logger.error(f"❌ Type de scraper inconnu: {scraper_type}")
        return None
    
    if class_name not in globals():
        logger.error(f"❌ Scraper {class_name} non disponible")
        return None
    
    try:
        scraper_class = globals()[class_name]
        return scraper_class(**kwargs)
    except Exception as e:
        logger.error(f"❌ Erreur création {class_name}: {e}")
        return None

@lru_cache(maxsize=32)
def get_scraper_capabilities(scraper_type: str) -> Dict[str, Any]:
    """
    Retourne les capacités d'un type de scraper avec cache.
    
    Args:
        scraper_type: Type de scraper
        
    Returns:
        Dictionnaire des capacités
    """
    capabilities = {
        'genius': {
            'supports_lyrics': True,
            'supports_credits': True,
            'supports_albums': True,
            'requires_selenium': True,
            'can_expand_hidden_credits': True,
            'data_quality': 'high',
            'extraction_speed': 'slow',
            'anti_detection': True
        },
        'rapedia': {
            'supports_lyrics': False,
            'supports_credits': True,
            'supports_albums': True,
            'requires_selenium': False,
            'language_focus': 'french_rap',
            'data_quality': 'very_high',
            'extraction_speed': 'medium',
            'anti_detection': False
        },
        'lastfm': {
            'supports_lyrics': False,
            'supports_credits': False,
            'supports_albums': True,
            'supports_tags': True,
            'requires_selenium': False,
            'data_quality': 'medium',
            'extraction_speed': 'fast',
            'anti_detection': False
        },
        'discogs': {
            'supports_lyrics': False,
            'supports_credits': True,
            'supports_albums': True,
            'supports_release_info': True,
            'requires_selenium': False,
            'data_quality': 'high',
            'extraction_speed': 'medium',
            'anti_detection': False
        }
    }
    
    return capabilities.get(scraper_type.lower(), {})

def run_scraper_diagnostics() -> Dict[str, Any]:
    """
    Exécute un diagnostic complet du module web scrapers.
    
    Returns:
        Rapport de diagnostic détaillé
    """
    diagnostics = {
        'module_info': {
            'version': __version__,
            'total_classes': len(__all__),
            'available_scrapers': get_available_scrapers(),
            'utility_functions': get_utility_functions()
        },
        'import_status': get_import_stats(),
        'system_info': {
            'python_version': sys.version,
            'selenium_available': _check_selenium_availability(),
            'requests_available': _check_requests_availability(),
            'beautifulsoup_available': _check_beautifulsoup_availability()
        }
    }
    
    # Test de création des scrapers
    scraper_tests = {}
    for scraper_type in ['genius', 'rapedia', 'lastfm', 'discogs', 'bandcamp']:
        try:
            scraper = create_scraper(scraper_type)
            scraper_tests[scraper_type] = {
                'creation_success': scraper is not None,
                'class_available': scraper_type.title() + 'Scraper' in __all__ or 
                                 scraper_type.title() + 'WebScraper' in __all__,
                'capabilities': get_scraper_capabilities(scraper_type)
            }
        except Exception as e:
            scraper_tests[scraper_type] = {
                'creation_success': False,
                'error': str(e),
                'capabilities': {}
            }
    
    diagnostics['scraper_tests'] = scraper_tests
    
    return diagnostics

def _check_selenium_availability() -> bool:
    """Vérifie la disponibilité de Selenium"""
    try:
        import selenium
        return True
    except ImportError:
        return False

def _check_requests_availability() -> bool:
    """Vérifie la disponibilité de Requests"""
    try:
        import requests
        return True
    except ImportError:
        return False

def _check_beautifulsoup_availability() -> bool:
    """Vérifie la disponibilité de BeautifulSoup"""
    try:
        import bs4
        return True
    except ImportError:
        return False

# ===== CONFIGURATION ET VALIDATION =====

def validate_scraper_setup() -> Tuple[bool, List[str]]:
    """
    Valide la configuration du module web scrapers.
    
    Returns:
        Tuple (configuration_valide, liste_problèmes)
    """
    issues = []
    
    # Vérifier qu'au moins un scraper principal est disponible
    if not any(scraper in __all__ for scraper in ['GeniusWebScraper', 'RapediaScraper']):
        issues.append("Aucun scraper principal (Genius/Rapedia) disponible")
    
    # Vérifier la cohérence des imports
    if len(get_available_scrapers()) == 0:
        issues.append("Aucun scraper web disponible")
    
    # Vérifier les dépendances critiques
    if not _check_requests_availability():
        issues.append("Module 'requests' manquant (requis pour HTTP)")
    
    if not _check_beautifulsoup_availability():
        issues.append("Module 'beautifulsoup4' manquant (requis pour parsing HTML)")
    
    # Avertissements pour dépendances optionnelles
    if not _check_selenium_availability():
        logger.warning("⚠️ Selenium non disponible - scrapers avancés (Genius) limités")
    
    return len(issues) == 0, issues

# ===== FONCTIONS DE SCRAPING UTILITAIRES =====

def scrape_with_fallback(url: str, scrapers: List[str], **kwargs) -> Optional[Dict[str, Any]]:
    """
    Scrape une URL avec fallback entre plusieurs scrapers.
    
    Args:
        url: URL à scraper
        scrapers: Liste des scrapers à essayer (par ordre de préférence)
        **kwargs: Arguments additionnels pour les scrapers
        
    Returns:
        Résultats du premier scraper qui réussit ou None
    """
    for scraper_type in scrapers:
        try:
            scraper = create_scraper(scraper_type, **kwargs)
            if scraper:
                logger.info(f"🔄 Tentative avec {scraper_type} pour {url}")
                
                # Méthode générique de scraping
                if hasattr(scraper, 'scrape_url'):
                    result = scraper.scrape_url(url)
                elif hasattr(scraper, 'scrape_track'):
                    result = scraper.scrape_track(url)
                elif hasattr(scraper, 'extract_data'):
                    result = scraper.extract_data(url)
                else:
                    logger.warning(f"⚠️ Aucune méthode de scraping trouvée pour {scraper_type}")
                    continue
                
                if result and result.get('success', False):
                    logger.info(f"✅ Succès avec {scraper_type}")
                    return result
                
        except Exception as e:
            logger.warning(f"⚠️ Échec {scraper_type}: {e}")
            continue
    
    logger.error(f"❌ Tous les scrapers ont échoué pour {url}")
    return None

def batch_scrape_urls(urls: List[str], scraper_type: str, max_workers: int = 3, **kwargs) -> List[Dict[str, Any]]:
    """
    Scrape une liste d'URLs en parallèle avec un scraper spécifique.
    
    Args:
        urls: Liste des URLs à scraper
        scraper_type: Type de scraper à utiliser
        max_workers: Nombre de workers parallèles
        **kwargs: Arguments pour le scraper
        
    Returns:
        Liste des résultats
    """
    results = []
    
    try:
        import concurrent.futures
        import time
        
        def scrape_single_url(url: str) -> Dict[str, Any]:
            try:
                scraper = create_scraper(scraper_type, **kwargs)
                if not scraper:
                    return {'url': url, 'success': False, 'error': 'Scraper creation failed'}
                
                # Rate limiting simple
                time.sleep(0.5)  # Délai entre requêtes
                
                if hasattr(scraper, 'scrape_url'):
                    result = scraper.scrape_url(url)
                elif hasattr(scraper, 'scrape_track'):
                    result = scraper.scrape_track(url)
                else:
                    return {'url': url, 'success': False, 'error': 'No scraping method found'}
                
                if result:
                    result['url'] = url
                    return result
                else:
                    return {'url': url, 'success': False, 'error': 'No result returned'}
                    
            except Exception as e:
                return {'url': url, 'success': False, 'error': str(e)}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(scrape_single_url, url): url for url in urls}
            
            for future in concurrent.futures.as_completed(future_to_url):
                result = future.result()
                results.append(result)
                
                # Log du progrès
                if len(results) % 10 == 0:
                    success_count = len([r for r in results if r.get('success', False)])
                    logger.info(f"📊 Progrès: {len(results)}/{len(urls)} - {success_count} succès")
        
    except ImportError:
        logger.warning("⚠️ concurrent.futures non disponible, scraping séquentiel")
        
        # Fallback séquentiel
        for url in urls:
            try:
                scraper = create_scraper(scraper_type, **kwargs)
                if scraper and hasattr(scraper, 'scrape_url'):
                    result = scraper.scrape_url(url)
                    if result:
                        result['url'] = url
                        results.append(result)
                    else:
                        results.append({'url': url, 'success': False, 'error': 'No result'})
                else:
                    results.append({'url': url, 'success': False, 'error': 'Scraper unavailable'})
                    
                # Rate limiting
                time.sleep(1)
                
            except Exception as e:
                results.append({'url': url, 'success': False, 'error': str(e)})
    
    success_count = len([r for r in results if r.get('success', False)])
    logger.info(f"🏁 Batch scraping terminé: {success_count}/{len(urls)} succès")
    
    return results

def extract_genius_credits(track_url: str) -> List[Dict[str, str]]:
    """
    Exemple d'utilisation : extraction des crédits depuis une page Genius.
    
    Args:
        track_url: URL de la track Genius
        
    Returns:
        Liste des crédits extraits
    """
    try:
        scraper = create_scraper('genius')
        if not scraper:
            logger.error("❌ Impossible de créer le scraper Genius")
            return []
        
        result = scraper.scrape_track_credits(track_url)
        if result and result.get('success'):
            return result.get('credits', [])
        else:
            logger.error(f"❌ Échec extraction crédits: {result.get('error', 'Unknown error')}")
            return []
            
    except Exception as e:
        logger.error(f"❌ Erreur extraction crédits Genius: {e}")
        return []

def extract_rapedia_data(artist_name: str) -> Dict[str, Any]:
    """
    Exemple d'utilisation : extraction des données depuis Rapedia.
    
    Args:
        artist_name: Nom de l'artiste
        
    Returns:
        Données extraites de Rapedia
    """
    try:
        scraper = create_scraper('rapedia')
        if not scraper:
            logger.error("❌ Impossible de créer le scraper Rapedia")
            return {}
        
        result = scraper.search_artist_tracks(artist_name)
        if result and isinstance(result, list):
            return {
                'success': True,
                'tracks_found': len(result),
                'tracks': result
            }
        else:
            return {'success': False, 'error': 'No results found'}
            
    except Exception as e:
        logger.error(f"❌ Erreur extraction Rapedia: {e}")
        return {'success': False, 'error': str(e)}

# ===== INITIALISATION =====

# Validation automatique au chargement
_setup_valid, _setup_issues = validate_scraper_setup()

if not _setup_valid:
    logger.warning("⚠️ Problèmes détectés dans la configuration web scrapers:")
    for issue in _setup_issues:
        logger.warning(f"  - {issue}")

logger.info(f"✅ Module web_scrapers initialisé: {len(get_available_scrapers())} scrapers disponibles")

# Export des fonctions utilitaires
__all__.extend([
    'get_available_scrapers',
    'get_utility_functions',
    'get_import_stats',
    'create_scraper',
    'get_scraper_capabilities',
    'run_scraper_diagnostics',
    'validate_scraper_setup',
    'scrape_with_fallback',
    'batch_scrape_urls',
    'extract_genius_credits',
    'extract_rapedia_data',
    'get_discovery_step',
    'get_extraction_step',
    'get_processing_step',
    'get_export_step'
])