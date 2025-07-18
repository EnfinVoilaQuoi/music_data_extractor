# discovery/__init__.py
"""
Modules de découverte de morceaux depuis diverses sources.
Version optimisée avec cache, imports sécurisés et diagnostics.
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

# 1. GeniusDiscovery (module principal)
_safe_import('genius_discovery', ['GeniusDiscovery', 'DiscoveryResult'])

# 2. SpotifyDiscovery (optionnel)
_safe_import('spotify_discovery', ['SpotifyDiscovery'])

# 3. AlbumResolver (optionnel)
_safe_import('album_resolver', ['AlbumResolver'])

# 4. Autres découvreurs (optionnels)
_safe_import('lastfm_discovery', ['LastFMDiscovery'])
_safe_import('discogs_discovery', ['DiscogsDiscovery'])

# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_available_discoverers() -> List[str]:
    """
    Retourne la liste des découvreurs disponibles avec cache.
    
    Returns:
        Liste des classes de découverte disponibles
    """
    return [name for name in __all__ if name.endswith('Discovery')]

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
        'available_discoverers': get_available_discoverers(),
        'successful_modules': _import_stats['successful'],
        'failed_modules': _import_stats['failed']
    }

def create_discoverer(discoverer_type: str, **kwargs) -> Optional[Any]:
    """
    Factory pour créer un découvreur avec gestion d'erreurs.
    
    Args:
        discoverer_type: Type de découvreur ('genius', 'spotify', etc.)
        **kwargs: Arguments pour le constructeur
        
    Returns:
        Instance du découvreur ou None si échec
    """
    discoverer_mapping = {
        'genius': 'GeniusDiscovery',
        'spotify': 'SpotifyDiscovery',
        'lastfm': 'LastFMDiscovery',
        'discogs': 'DiscogsDiscovery'
    }
    
    class_name = discoverer_mapping.get(discoverer_type.lower())
    if not class_name:
        logger.error(f"❌ Type de découvreur inconnu: {discoverer_type}")
        return None
    
    if class_name not in globals():
        logger.error(f"❌ Découvreur {class_name} non disponible")
        return None
    
    try:
        discoverer_class = globals()[class_name]
        return discoverer_class(**kwargs)
    except Exception as e:
        logger.error(f"❌ Erreur création {class_name}: {e}")
        return None

@lru_cache(maxsize=32)
def get_discoverer_capabilities(discoverer_type: str) -> Dict[str, Any]:
    """
    Retourne les capacités d'un type de découvreur avec cache.
    
    Args:
        discoverer_type: Type de découvreur
        
    Returns:
        Dictionnaire des capacités
    """
    capabilities = {
        'genius': {
            'supports_lyrics': True,
            'supports_credits': True,
            'supports_albums': True,
            'rate_limited': True,
            'requires_api_key': True,
            'data_quality': 'high'
        },
        'spotify': {
            'supports_lyrics': False,
            'supports_credits': False,
            'supports_albums': True,
            'rate_limited': True,
            'requires_api_key': True,
            'data_quality': 'medium'
        },
        'lastfm': {
            'supports_lyrics': False,
            'supports_credits': False,
            'supports_albums': True,
            'rate_limited': True,
            'requires_api_key': True,
            'data_quality': 'medium'
        },
        'discogs': {
            'supports_lyrics': False,
            'supports_credits': True,
            'supports_albums': True,
            'rate_limited': True,
            'requires_api_key': True,
            'data_quality': 'high'
        }
    }
    
    return capabilities.get(discoverer_type.lower(), {})

def run_discovery_diagnostics() -> Dict[str, Any]:
    """
    Exécute un diagnostic complet du module discovery.
    
    Returns:
        Rapport de diagnostic détaillé
    """
    diagnostics = {
        'module_info': {
            'version': __version__,
            'total_classes': len(__all__),
            'available_discoverers': get_available_discoverers()
        },
        'import_status': get_import_stats(),
        'system_info': {
            'python_version': sys.version,
            'available_memory': 'N/A'  # À implémenter si nécessaire
        }
    }
    
    # Test de création des découvreurs
    discovery_tests = {}
    for discoverer_type in ['genius', 'spotify', 'lastfm', 'discogs']:
        try:
            discoverer = create_discoverer(discoverer_type)
            discovery_tests[discoverer_type] = {
                'creation_success': discoverer is not None,
                'class_available': discoverer_type.title() + 'Discovery' in __all__,
                'capabilities': get_discoverer_capabilities(discoverer_type)
            }
        except Exception as e:
            discovery_tests[discoverer_type] = {
                'creation_success': False,
                'error': str(e),
                'capabilities': {}
            }
    
    diagnostics['discovery_tests'] = discovery_tests
    
    return diagnostics

# ===== CONFIGURATION ET VALIDATION =====

def validate_discovery_setup() -> Tuple[bool, List[str]]:
    """
    Valide la configuration du module discovery.
    
    Returns:
        Tuple (configuration_valide, liste_problèmes)
    """
    issues = []
    
    # Vérifier qu'au moins un découvreur principal est disponible
    if 'GeniusDiscovery' not in __all__:
        issues.append("GeniusDiscovery (module principal) non disponible")
    
    # Vérifier la cohérence des imports
    if len(__all__) == 0:
        issues.append("Aucun module de découverte disponible")
    
    # Vérifier les dépendances critiques
    try:
        import requests
    except ImportError:
        issues.append("Module 'requests' manquant (requis pour les API)")
    
    return len(issues) == 0, issues

# ===== INITIALISATION =====

# Validation automatique au chargement
_setup_valid, _setup_issues = validate_discovery_setup()

if not _setup_valid:
    logger.warning("⚠️ Problèmes détectés dans la configuration discovery:")
    for issue in _setup_issues:
        logger.warning(f"  - {issue}")

logger.info(f"✅ Module discovery initialisé: {len(__all__)} classes disponibles")

# Export des fonctions utilitaires
__all__.extend([
    'get_available_discoverers',
    'get_import_stats', 
    'create_discoverer',
    'get_discoverer_capabilities',
    'run_discovery_diagnostics',
    'validate_discovery_setup'
])