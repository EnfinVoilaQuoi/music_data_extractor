# core/__init__.py
"""Modules core du projet - base de données, cache, sessions"""

import logging
from typing import List, Dict, Any, Optional
from functools import lru_cache

# Configuration du logging pour le module core
logger = logging.getLogger(__name__)

__all__ = []
_import_errors = {}  # Tracking des erreurs d'import pour diagnostic

# ===== IMPORTS OPTIMISÉS AVEC GESTION D'ERREURS =====

def _safe_import(module_name: str, class_names: List[str], description: str) -> bool:
    """Import sécurisé avec gestion d'erreurs centralisée"""
    try:
        module = __import__(f".{module_name}", package=__name__, fromlist=class_names)
        
        # Ajouter les classes à __all__
        for class_name in class_names:
            if hasattr(module, class_name):
                globals()[class_name] = getattr(module, class_name)
                __all__.append(class_name)
        
        logger.debug(f"✅ {description} importé")
        return True
        
    except ImportError as e:
        error_msg = f"Erreur import {description}: {e}"
        _import_errors[module_name] = error_msg
        logger.warning(f"⚠️ {error_msg}")
        return False
    except Exception as e:
        error_msg = f"Erreur inattendue import {description}: {e}"
        _import_errors[module_name] = error_msg
        logger.error(f"❌ {error_msg}")
        return False

# Import des exceptions en premier (pas de dépendances)
_safe_import("exceptions", [
    "MusicDataExtractorError",
    "APIError", "APIRateLimitError", "APIAuthenticationError", "APIQuotaExceededError", "APIResponseError",
    "ScrapingError", "PageNotFoundError", "ElementNotFoundError", "SeleniumError",
    "DatabaseError", "DatabaseConnectionError", "DatabaseSchemaError", "DatabaseIntegrityError",
    "DataError", "DataValidationError", "DataInconsistencyError",
    "ExtractionError", "ArtistNotFoundError", "TrackExtractionError", "CreditExtractionError",
    "CacheError", "CacheExpiredError", "CacheCorruptedError",
    "SessionError", "SessionNotFoundError", "SessionCorruptedError", "SessionStatusError",
    "ExportError", "ExportFormatError", "ExportDataError"
], "Core exceptions")

# Import de la base de données
_safe_import("database", ["Database"], "Database")

# Import du cache
_safe_import("cache", ["CacheManager", "SmartCache", "CacheStats"], "CacheManager")

# Import du rate limiter
_safe_import("rate_limiter", ["RateLimiter"], "RateLimiter")

# Import du gestionnaire de sessions
_safe_import("session_manager", ["SessionManager", "get_session_manager"], "SessionManager")

# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_available_core_modules() -> List[str]:
    """Retourne la liste des modules core disponibles - avec cache"""
    return sorted(__all__)

@lru_cache(maxsize=1)
def get_import_errors() -> Dict[str, str]:
    """Retourne les erreurs d'import pour diagnostic - avec cache"""
    return _import_errors.copy()

def get_core_status() -> Dict[str, Any]:
    """Retourne le statut complet du module core"""
    total_modules = 5  # exceptions, database, cache, rate_limiter, session_manager
    available_modules = len([m for m in ['exceptions', 'database', 'cache', 'rate_limiter', 'session_manager'] 
                           if m not in _import_errors])
    
    # Modules critiques vs optionnels
    critical_modules = ['exceptions', 'database']
    critical_available = all(m not in _import_errors for m in critical_modules)
    
    return {
        'available_modules': get_available_core_modules(),
        'import_errors': get_import_errors(),
        'module_count': {
            'total': total_modules,
            'available': available_modules,
            'failed': len(_import_errors)
        },
        'status': {
            'overall': 'HEALTHY' if available_modules >= 4 else 'DEGRADED' if critical_available else 'CRITICAL',
            'critical_modules_ok': critical_available,
            'completion_rate': round((available_modules / total_modules) * 100, 1)
        }
    }

def validate_core_dependencies() -> List[str]:
    """Valide les dépendances entre modules core"""
    issues = []
    
    # Vérifier que les modules critiques sont disponibles
    if 'Database' not in __all__:
        issues.append("Module Database indisponible - fonctionnalité de base compromise")
    
    if 'SessionManager' not in __all__:
        issues.append("Module SessionManager indisponible - gestion des sessions impossible")
    
    # Vérifier la cohérence des exceptions
    exception_classes = [name for name in __all__ if name.endswith('Error')]
    if len(exception_classes) < 5:
        issues.append(f"Exceptions incomplètes: {len(exception_classes)} trouvées, 15+ attendues")
    
    # Vérifier les dépendances optionnelles
    optional_warnings = []
    if 'CacheManager' not in __all__:
        optional_warnings.append("CacheManager indisponible - performance réduite")
    
    if 'RateLimiter' not in __all__:
        optional_warnings.append("RateLimiter indisponible - risque de dépassement de quotas API")
    
    if optional_warnings:
        issues.extend(optional_warnings)
    
    return issues

def initialize_core_modules(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Initialise les modules core avec configuration optionnelle"""
    config = config or {}
    results = {
        'initialized': [],
        'failed': [],
        'skipped': []
    }
    
    # Initialisation de la base de données
    if 'Database' in __all__:
        try:
            db = Database()
            db.initialize()  # Méthode d'init si elle existe
            results['initialized'].append('Database')
        except Exception as e:
            results['failed'].append(f"Database: {e}")
    else:
        results['skipped'].append('Database')
    
    # Initialisation du cache
    if 'CacheManager' in __all__:
        try:
            cache = CacheManager()
            if config.get('cache_auto_cleanup', False):
                cache.clear_expired()
            results['initialized'].append('CacheManager')
        except Exception as e:
            results['failed'].append(f"CacheManager: {e}")
    else:
        results['skipped'].append('CacheManager')
    
    # Initialisation du gestionnaire de sessions
    if 'get_session_manager' in __all__:
        try:
            session_manager = get_session_manager()
            results['initialized'].append('SessionManager')
        except Exception as e:
            results['failed'].append(f"SessionManager: {e}")
    else:
        results['skipped'].append('SessionManager')
    
    return results

# ===== CLEANUP ET GESTION DES RESSOURCES =====

def cleanup_core_resources():
    """Nettoie les ressources des modules core"""
    cleanup_results = []
    
    # Arrêter le gestionnaire de sessions
    if 'get_session_manager' in __all__:
        try:
            session_manager = get_session_manager()
            if hasattr(session_manager, 'stop'):
                session_manager.stop()
            cleanup_results.append("SessionManager arrêté")
        except Exception as e:
            cleanup_results.append(f"Erreur arrêt SessionManager: {e}")
    
    # Nettoyer le cache si configuré
    if 'CacheManager' in __all__:
        try:
            # Ne pas nettoyer automatiquement - laisser à l'utilisateur
            cleanup_results.append("Cache préservé")
        except Exception as e:
            cleanup_results.append(f"Erreur cache: {e}")
    
    return cleanup_results

# ===== DIAGNOSTIC ET MONITORING =====

@lru_cache(maxsize=1)
def get_core_info() -> Dict[str, Any]:
    """Informations complètes sur le module core - avec cache"""
    return {
        'version': '1.0.0',
        'modules': get_available_core_modules(),
        'status': get_core_status(),
        'dependencies': validate_core_dependencies()
    }

def run_core_diagnostics() -> Dict[str, Any]:
    """Exécute un diagnostic complet des modules core"""
    diagnostics = {
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'core_info': get_core_info(),
        'import_status': get_core_status(),
        'dependency_issues': validate_core_dependencies()
    }
    
    # Tests de fonctionnement de base
    functional_tests = {}
    
    # Test Database
    if 'Database' in __all__:
        try:
            db = Database()
            # Test de connexion basique
            with db.get_connection() as conn:
                cursor = conn.execute("SELECT 1")
                functional_tests['database'] = 'OK'
        except Exception as e:
            functional_tests['database'] = f'FAILED: {e}'
    
    # Test Cache
    if 'CacheManager' in __all__:
        try:
            cache = CacheManager()
            test_key = "core_diagnostic_test"
            cache.set(test_key, "test_value", expire_days=1)
            result = cache.get(test_key)
            cache.delete(test_key)
            functional_tests['cache'] = 'OK' if result == "test_value" else 'FAILED: Value mismatch'
        except Exception as e:
            functional_tests['cache'] = f'FAILED: {e}'
    
    diagnostics['functional_tests'] = functional_tests
    
    return diagnostics

# ===== LOGGING ET ÉTAT =====

# Affichage du statut au chargement du module (uniquement si debugging activé)
if logger.isEnabledFor(logging.DEBUG):
    status = get_core_status()
    logger.info(f"🔧 Module core chargé - {status['status']['overall']} "
               f"({status['module_count']['available']}/{status['module_count']['total']} modules)")
    
    if _import_errors:
        logger.warning(f"⚠️ Modules avec erreurs: {list(_import_errors.keys())}")

# Export des fonctions utilitaires
__all__.extend([
    'get_available_core_modules',
    'get_import_errors', 
    'get_core_status',
    'validate_core_dependencies',
    'initialize_core_modules',
    'cleanup_core_resources',
    'get_core_info',
    'run_core_diagnostics'
])