# extractors/__init__.py
"""
Module d'extraction optimisé avec scrapers web avancés.
Version optimisée avec imports sécurisés, cache intelligent et diagnostics.
"""

import logging
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple
import importlib
import sys

__version__ = "1.0.0"
__all__ = []

# Configuration du logger pour ce module
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
        module_name: Nom du module à importer
        class_names: Liste des classes à importer
        
    Returns:
        Tuple (succès, erreur_éventuelle)
    """
    global _import_stats
    _import_stats['total_attempts'] += 1
    
    try:
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

# 1. Web Scrapers (modules principaux)
_safe_import('web_scrapers.genius_scraper', ['GeniusWebScraper'])
_safe_import('web_scrapers.rapedia_scraper', ['RapediaScraper'])

# 2. API Extractors (optionnels)
_safe_import('api_extractors.spotify_extractor', ['SpotifyExtractor'])
_safe_import('api_extractors.lastfm_extractor', ['LastFMExtractor'])
_safe_import('api_extractors.discogs_extractor', ['DiscogsExtractor'])

# 3. Text Processors (optionnels)
_safe_import('text_processors.lyrics_processor', ['LyricsProcessor'])
_safe_import('text_processors.credit_parser', ['CreditParser'])

# 4. Data Enrichers (optionnels)
_safe_import('data_enrichers.metadata_enricher', ['MetadataEnricher'])
_safe_import('data_enrichers.audio_analyzer', ['AudioAnalyzer'])

# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_available_extractors() -> List[str]:
    """
    Retourne la liste des extracteurs disponibles avec cache.
    
    Returns:
        Liste des classes d'extraction disponibles
    """
    return [name for name in __all__ if any(suffix in name for suffix in ['Scraper', 'Extractor', 'Processor', 'Enricher'])]

@lru_cache(maxsize=1)
def get_web_scrapers() -> List[str]:
    """
    Retourne la liste des scrapers web disponibles.
    
    Returns:
        Liste des scrapers web
    """
    return [name for name in __all__ if 'Scraper' in name]

@lru_cache(maxsize=1)
def get_api_extractors() -> List[str]:
    """
    Retourne la liste des extracteurs API disponibles.
    
    Returns:
        Liste des extracteurs API
    """
    return [name for name in __all__ if 'Extractor' in name]

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
        'available_extractors': get_available_extractors(),
        'web_scrapers': get_web_scrapers(),
        'api_extractors': get_api_extractors(),
        'successful_modules': _import_stats['successful'],
        'failed_modules': _import_stats['failed']
    }

def create_extractor(extractor_type: str, **kwargs) -> Optional[Any]:
    """
    Factory pour créer un extracteur avec gestion d'erreurs.
    
    Args:
        extractor_type: Type d'extracteur ('genius_scraper', 'spotify', etc.)
        **kwargs: Arguments pour le constructeur
        
    Returns:
        Instance de l'extracteur ou None si échec
    """
    extractor_mapping = {
        'genius_scraper': 'GeniusWebScraper',
        'genius': 'GeniusWebScraper',
        'rapedia_scraper': 'RapediaScraper',
        'rapedia': 'RapediaScraper',
        'spotify_extractor': 'SpotifyExtractor',
        'spotify': 'SpotifyExtractor',
        'lastfm_extractor': 'LastFMExtractor',
        'lastfm': 'LastFMExtractor',
        'discogs_extractor': 'DiscogsExtractor',
        'discogs': 'DiscogsExtractor',
        'lyrics_processor': 'LyricsProcessor',
        'credit_parser': 'CreditParser',
        'metadata_enricher': 'MetadataEnricher',
        'audio_analyzer': 'AudioAnalyzer'
    }
    
    class_name = extractor_mapping.get(extractor_type.lower())
    if not class_name:
        logger.error(f"❌ Type d'extracteur inconnu: {extractor_type}")
        return None
    
    if class_name not in globals():
        logger.error(f"❌ Extracteur {class_name} non disponible")
        return None
    
    try:
        extractor_class = globals()[class_name]
        return extractor_class(**kwargs)
    except Exception as e:
        logger.error(f"❌ Erreur création {class_name}: {e}")
        return None

@lru_cache(maxsize=32)
def get_extractor_capabilities(extractor_type: str) -> Dict[str, Any]:
    """
    Retourne les capacités d'un type d'extracteur avec cache.
    
    Args:
        extractor_type: Type d'extracteur
        
    Returns:
        Dictionnaire des capacités
    """
    capabilities = {
        'genius_scraper': {
            'supports_lyrics': True,
            'supports_credits': True,
            'supports_albums': True,
            'requires_selenium': True,
            'can_expand_hidden_credits': True,
            'data_quality': 'high',
            'extraction_speed': 'slow'
        },
        'rapedia_scraper': {
            'supports_lyrics': False,
            'supports_credits': True,
            'supports_albums': True,
            'requires_selenium': False,
            'language_focus': 'french_rap',
            'data_quality': 'very_high',
            'extraction_speed': 'medium'
        },
        'spotify_extractor': {
            'supports_lyrics': False,
            'supports_credits': False,
            'supports_albums': True,
            'supports_audio_features': True,
            'requires_api_key': True,
            'data_quality': 'medium',
            'extraction_speed': 'fast'
        },
        'lastfm_extractor': {
            'supports_lyrics': False,
            'supports_credits': False,
            'supports_albums': True,
            'supports_tags': True,
            'requires_api_key': True,
            'data_quality': 'medium',
            'extraction_speed': 'fast'
        },
        'discogs_extractor': {
            'supports_lyrics': False,
            'supports_credits': True,
            'supports_albums': True,
            'supports_release_info': True,
            'requires_api_key': True,
            'data_quality': 'high',
            'extraction_speed': 'medium'
        }
    }
    
    return capabilities.get(extractor_type.lower(), {})

def run_extraction_diagnostics() -> Dict[str, Any]:
    """
    Exécute un diagnostic complet du module extractors.
    
    Returns:
        Rapport de diagnostic détaillé
    """
    diagnostics = {
        'module_info': {
            'version': __version__,
            'total_classes': len(__all__),
            'available_extractors': get_available_extractors(),
            'web_scrapers': get_web_scrapers(),
            'api_extractors': get_api_extractors()
        },
        'import_status': get_import_stats(),
        'system_info': {
            'python_version': sys.version,
            'selenium_available': _check_selenium_availability(),
            'required_dependencies': _check_dependencies()
        }
    }
    
    # Test de création des extracteurs
    extraction_tests = {}
    for extractor_type in ['genius_scraper', 'rapedia_scraper', 'spotify_extractor', 'lastfm_extractor', 'discogs_extractor']:
        try:
            extractor = create_extractor(extractor_type)
            extraction_tests[extractor_type] = {
                'creation_success': extractor is not None,
                'class_available': any(extractor_type.replace('_', '').title().replace('Extractor', 'Extractor').replace('Scraper', 'Scraper') in name 
                                     for name in __all__),
                'capabilities': get_extractor_capabilities(extractor_type)
            }
        except Exception as e:
            extraction_tests[extractor_type] = {
                'creation_success': False,
                'error': str(e),
                'capabilities': {}
            }
    
    diagnostics['extraction_tests'] = extraction_tests
    
    return diagnostics

def _check_selenium_availability() -> bool:
    """Vérifie la disponibilité de Selenium"""
    try:
        import selenium
        return True
    except ImportError:
        return False

def _check_dependencies() -> Dict[str, bool]:
    """Vérifie la disponibilité des dépendances requises"""
    dependencies = {
        'requests': False,
        'beautifulsoup4': False,
        'selenium': False,
        'webdriver_manager': False,
        'lxml': False
    }
    
    for dep in dependencies:
        try:
            if dep == 'beautifulsoup4':
                import bs4
            elif dep == 'webdriver_manager':
                import webdriver_manager
            else:
                importlib.import_module(dep)
            dependencies[dep] = True
        except ImportError:
            pass
    
    return dependencies

# ===== CONFIGURATION ET VALIDATION =====

def validate_extraction_setup() -> Tuple[bool, List[str]]:
    """
    Valide la configuration du module extractors.
    
    Returns:
        Tuple (configuration_valide, liste_problèmes)
    """
    issues = []
    
    # Vérifier qu'au moins un scraper principal est disponible
    if not any(scraper in __all__ for scraper in ['GeniusWebScraper', 'RapediaScraper']):
        issues.append("Aucun scraper principal (Genius/Rapedia) disponible")
    
    # Vérifier la cohérence des imports
    if len(__all__) == 0:
        issues.append("Aucun module d'extraction disponible")
    
    # Vérifier les dépendances critiques
    dependencies = _check_dependencies()
    if not dependencies['requests']:
        issues.append("Module 'requests' manquant (requis pour HTTP)")
    
    if not dependencies['beautifulsoup4']:
        issues.append("Module 'beautifulsoup4' manquant (requis pour parsing HTML)")
    
    # Avertissements pour dépendances optionnelles
    if not dependencies['selenium']:
        logger.warning("⚠️ Selenium non disponible - scrapers avancés limités")
    
    if not dependencies['webdriver_manager']:
        logger.warning("⚠️ WebDriver Manager non disponible - gestion automatique des drivers limitée")
    
    return len(issues) == 0, issues

def get_extraction_pipeline() -> List[str]:
    """
    Retourne l'ordre recommandé d'exécution des extracteurs.
    
    Returns:
        Liste ordonnée des extracteurs
    """
    pipeline = []
    
    # 1. Scrapers web (données de haute qualité)
    if 'GeniusWebScraper' in __all__:
        pipeline.append('genius_scraper')
    if 'RapediaScraper' in __all__:
        pipeline.append('rapedia_scraper')
    
    # 2. API extractors (métadonnées additionnelles)
    if 'SpotifyExtractor' in __all__:
        pipeline.append('spotify_extractor')
    if 'DiscogsExtractor' in __all__:
        pipeline.append('discogs_extractor')
    if 'LastFMExtractor' in __all__:
        pipeline.append('lastfm_extractor')
    
    # 3. Processors (enrichissement)
    if 'LyricsProcessor' in __all__:
        pipeline.append('lyrics_processor')
    if 'CreditParser' in __all__:
        pipeline.append('credit_parser')
    if 'MetadataEnricher' in __all__:
        pipeline.append('metadata_enricher')
    
    return pipeline

# ===== INITIALISATION =====

# Validation automatique au chargement
_setup_valid, _setup_issues = validate_extraction_setup()

if not _setup_valid:
    logger.warning("⚠️ Problèmes détectés dans la configuration extractors:")
    for issue in _setup_issues:
        logger.warning(f"  - {issue}")

logger.info(f"✅ Module extractors initialisé: {len(__all__)} classes disponibles")

# Export des fonctions utilitaires
__all__.extend([
    'get_available_extractors',
    'get_web_scrapers',
    'get_api_extractors',
    'get_import_stats', 
    'create_extractor',
    'get_extractor_capabilities',
    'run_extraction_diagnostics',
    'validate_extraction_setup',
    'get_extraction_pipeline'
])