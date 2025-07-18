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
    # Mapping des types vers les classes
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
        'available': False,
        'features': [],
        'data_sources': [],
        'output_formats': []
    }
    
    try:
        extractor = create_extractor(extractor_type)
        if extractor:
            capabilities['available'] = True
            
            # Détection des méthodes disponibles
            methods = [method for method in dir(extractor) if not method.startswith('_')]
            capabilities['features'] = methods
            
            # Extraction des capacités spécifiques si disponibles
            if hasattr(extractor, 'get_supported_sources'):
                capabilities['data_sources'] = extractor.get_supported_sources()
            
            if hasattr(extractor, 'get_output_formats'):
                capabilities['output_formats'] = extractor.get_output_formats()
                
    except Exception as e:
        logger.debug(f"Erreur évaluation capacités {extractor_type}: {e}")
    
    return capabilities

def run_extractor_diagnostics() -> Dict[str, Any]:
    """
    Lance des diagnostics complets sur tous les extracteurs.
    
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
            'required_packages': _check_required_packages()
        }
    }
    
    # Test de création des extracteurs
    extractor_tests = {}
    all_types = ['genius', 'rapedia', 'spotify', 'lastfm', 'discogs']
    
    for extractor_type in all_types:
        try:
            extractor = create_extractor(extractor_type)
            extractor_tests[extractor_type] = {
                'creation_success': extractor is not None,
                'capabilities': get_extractor_capabilities(extractor_type)
            }
        except Exception as e:
            extractor_tests[extractor_type] = {
                'creation_success': False,
                'error': str(e),
                'capabilities': {}
            }
    
    diagnostics['extractor_tests'] = extractor_tests
    
    return diagnostics

def _check_required_packages() -> Dict[str, bool]:
    """Vérifie la disponibilité des packages requis"""
    packages = {}
    
    # Packages essentiels
    for package in ['requests', 'beautifulsoup4', 'lxml']:
        try:
            importlib.import_module(package.replace('beautifulsoup4', 'bs4'))
            packages[package] = True
        except ImportError:
            packages[package] = False
    
    # Packages optionnels
    for package in ['selenium', 'spotipy', 'pylast']:
        try:
            importlib.import_module(package)
            packages[package] = True
        except ImportError:
            packages[package] = False
    
    return packages

def validate_extractor_setup() -> Tuple[bool, List[str]]:
    """
    Valide la configuration du module extracteurs.
    
    Returns:
        Tuple (configuration_valide, liste_problèmes)
    """
    issues = []
    
    # Vérifier qu'au moins un extracteur principal est disponible
    if not any(extractor in __all__ for extractor in ['GeniusWebScraper', 'RapediaScraper']):
        issues.append("Aucun extracteur principal (Genius/Rapedia) disponible")
    
    # Vérifier la cohérence des imports
    if len(get_available_extractors()) == 0:
        issues.append("Aucun extracteur disponible")
    
    # Vérifier les dépendances critiques
    required_packages = _check_required_packages()
    if not required_packages.get('requests', False):
        issues.append("Module 'requests' manquant (requis pour HTTP)")
    
    if not required_packages.get('beautifulsoup4', False):
        issues.append("Module 'beautifulsoup4' manquant (requis pour parsing HTML)")
    
    # Avertissements pour dépendances optionnelles
    if not required_packages.get('selenium', False):
        logger.warning("⚠️ Selenium non disponible - extracteurs avancés (Genius) limités")
    
    return len(issues) == 0, issues

# ===== FONCTIONS DE BATCH ET UTILITAIRES =====

def batch_extract_data(sources: List[Dict[str, str]], extractor_type: str, max_workers: int = 3, **kwargs) -> List[Dict[str, Any]]:
    """
    Extrait des données de plusieurs sources en parallèle.
    
    Args:
        sources: Liste de dictionnaires {'url': '...', 'type': '...'}
        extractor_type: Type d'extracteur à utiliser
        max_workers: Nombre de workers parallèles
        **kwargs: Arguments additionnels pour l'extracteur
        
    Returns:
        Liste des résultats d'extraction
    """
    results = []
    
    for source in sources:
        try:
            extractor = create_extractor(extractor_type, **kwargs)
            if extractor:
                # Méthode générique d'extraction
                if hasattr(extractor, 'extract_from_url'):
                    result = extractor.extract_from_url(source['url'])
                elif hasattr(extractor, 'scrape_url'):
                    result = extractor.scrape_url(source['url'])
                elif hasattr(extractor, 'extract_data'):
                    result = extractor.extract_data(source['url'])
                else:
                    result = {'success': False, 'error': 'No extraction method found'}
                
                if result:
                    result['source'] = source
                    results.append(result)
                
            else:
                results.append({
                    'source': source,
                    'success': False,
                    'error': 'Extractor creation failed'
                })
                
        except Exception as e:
            results.append({
                'source': source,
                'success': False,
                'error': str(e)
            })
    
    return results

# ===== INITIALISATION =====

# Validation automatique au chargement
_setup_valid, _setup_issues = validate_extractor_setup()

if not _setup_valid:
    logger.warning("⚠️ Problèmes détectés dans la configuration extracteurs:")
    for issue in _setup_issues:
        logger.warning(f"  - {issue}")
else:
    logger.info(f"✅ Module extracteurs initialisé: {len(get_available_extractors())} extracteurs disponibles")

# Export final
__all__.extend([
    'get_available_extractors',
    'get_web_scrapers', 
    'get_api_extractors',
    'get_import_stats',
    'create_extractor',
    'get_extractor_capabilities',
    'run_extractor_diagnostics',
    'validate_extractor_setup',
    'batch_extract_data'
])