# utils/__init__.py - VERSION CORRIGÉE
"""
Module utilitaires pour Music Data Extractor.
Fonctions helper, exports, manipulation de texte et configuration de logging.
"""

import logging
from functools import lru_cache
from typing import List, Dict, Any, Optional

# Configuration du logging
logger = logging.getLogger(__name__)

# Liste des exports publics et tracking des erreurs
__all__ = []
_import_errors = {}
_available_modules = {}

def _safe_import_utility(util_name: str, module_name: str, items: List[str]) -> bool:
    """Import sécurisé d'un module utilitaire avec gestion d'erreurs"""
    try:
        module = __import__(f".{module_name}", package=__name__, fromlist=items)
        
        imported_items = []
        for item_name in items:
            if hasattr(module, item_name):
                globals()[item_name] = getattr(module, item_name)
                __all__.append(item_name)
                imported_items.append(item_name)
            else:
                logger.warning(f"⚠️ {item_name} non trouvé dans {module_name}")
        
        if imported_items:
            _available_modules[util_name] = {
                'module': module_name,
                'items': imported_items,
                'status': 'success'
            }
            logger.debug(f"✅ {util_name} importé: {imported_items}")
            return True
        else:
            error_msg = f"Aucun élément importé depuis {module_name}"
            _import_errors[util_name] = error_msg
            _available_modules[util_name] = {
                'module': module_name,
                'items': [],
                'status': 'partial_failure',
                'error': error_msg
            }
            return False
            
    except ImportError as e:
        error_msg = f"Erreur import {module_name}: {e}"
        _import_errors[util_name] = error_msg
        _available_modules[util_name] = {
            'module': module_name,
            'items': [],
            'status': 'import_error',
            'error': error_msg
        }
        logger.warning(f"⚠️ {error_msg}")
        return False
    except Exception as e:
        error_msg = f"Erreur inattendue import {module_name}: {e}"
        _import_errors[util_name] = error_msg
        _available_modules[util_name] = {
            'module': module_name,
            'items': [],
            'status': 'unexpected_error',
            'error': error_msg
        }
        logger.error(f"❌ {error_msg}")
        return False

# ===== IMPORTS SÉCURISÉS DES MODULES UTILITAIRES =====

# Import des fonctions de manipulation de texte
_text_utils_imported = _safe_import_utility(
    "text_utils", 
    "text_utils", 
    [
        'clean_artist_name', 'normalize_title', 'extract_featured_artists_from_title',
        'parse_artist_list', 'clean_album_title', 'detect_language', 'similarity_ratio',
        'validate_artist_name', 'normalize_text', 'clean_text', 'extract_parenthetical_info',
        'remove_special_chars', 'split_featured_artists', 'normalize_featuring'
    ]
)

# Import du gestionnaire d'exports
_export_utils_imported = _safe_import_utility(
    "export_utils",
    "export_utils",
    ['ExportManager', 'export_all_formats', 'cleanup_old_exports']
)

# Import de la configuration de logging
_logging_config_imported = _safe_import_utility(
    "logging_config",
    "logging_config",
    [
        'setup_logging', 'get_logger', 'get_session_logger', 
        'set_debug_mode', 'cleanup_logs', 'MusicDataLogger'
    ]
)

# Import des utilitaires de validation (si disponibles)
_validation_utils_imported = _safe_import_utility(
    "validation_utils",
    "validation_utils",
    ['validate_url', 'validate_email', 'sanitize_filename', 'check_file_permissions']
)

# Import des utilitaires de performance (si disponibles)
_performance_utils_imported = _safe_import_utility(
    "performance_utils",
    "performance_utils",
    ['profile_function', 'measure_time', 'memory_usage', 'benchmark']
)

# ===== FONCTIONS UTILITAIRES PUBLIQUES =====

@lru_cache(maxsize=1)
def get_available_utils() -> List[str]:
    """Retourne la liste des utilitaires disponibles - avec cache"""
    return sorted(__all__)

@lru_cache(maxsize=1)
def get_available_modules() -> Dict[str, Dict[str, Any]]:
    """Retourne les informations sur les modules disponibles"""
    return _available_modules.copy()

@lru_cache(maxsize=1)
def get_import_errors() -> Dict[str, str]:
    """Retourne les erreurs d'import pour diagnostic"""
    return _import_errors.copy()

def get_utils_status() -> Dict[str, Any]:
    """Retourne le statut complet du module utils"""
    total_modules = len(_available_modules)
    successful_modules = len([m for m in _available_modules.values() if m['status'] == 'success'])
    success_rate = (successful_modules / max(total_modules, 1)) * 100
    
    return {
        'total_modules': total_modules,
        'successful_modules': successful_modules,
        'failed_modules': len(_import_errors),
        'success_rate': round(success_rate, 2),
        'available_functions': len(__all__),
        'available_utils': get_available_utils(),
        'module_details': get_available_modules(),
        'import_errors': get_import_errors()
    }

def list_text_utils() -> List[str]:
    """Liste les fonctions de manipulation de texte disponibles"""
    text_funcs = []
    if 'text_utils' in _available_modules:
        text_funcs = _available_modules['text_utils']['items']
    return text_funcs

def list_export_utils() -> List[str]:
    """Liste les utilitaires d'export disponibles"""
    export_funcs = []
    if 'export_utils' in _available_modules:
        export_funcs = _available_modules['export_utils']['items']
    return export_funcs

def list_logging_utils() -> List[str]:
    """Liste les utilitaires de logging disponibles"""
    logging_funcs = []
    if 'logging_config' in _available_modules:
        logging_funcs = _available_modules['logging_config']['items']
    return logging_funcs

# ===== FONCTIONS DE DIAGNOSTIC =====

def run_utils_diagnostics() -> Dict[str, Any]:
    """
    Lance des diagnostics complets sur tous les utilitaires.
    
    Returns:
        Rapport de diagnostic détaillé
    """
    diagnostics = {
        'module_info': {
            'total_functions': len(__all__),
            'available_modules': len(_available_modules),
            'failed_imports': len(_import_errors)
        },
        'status_summary': get_utils_status(),
        'module_breakdown': {
            'text_utils': {
                'available': 'text_utils' in _available_modules,
                'functions': list_text_utils(),
                'status': _available_modules.get('text_utils', {}).get('status', 'not_imported')
            },
            'export_utils': {
                'available': 'export_utils' in _available_modules,
                'functions': list_export_utils(),
                'status': _available_modules.get('export_utils', {}).get('status', 'not_imported')
            },
            'logging_config': {
                'available': 'logging_config' in _available_modules,
                'functions': list_logging_utils(),
                'status': _available_modules.get('logging_config', {}).get('status', 'not_imported')
            }
        }
    }
    
    # Test de fonctionnement des utilitaires critiques
    function_tests = {}
    
    # Test des fonctions de texte
    if 'clean_artist_name' in globals():
        try:
            test_result = clean_artist_name("  Test Artist  ")
            function_tests['clean_artist_name'] = {
                'working': True,
                'test_result': test_result
            }
        except Exception as e:
            function_tests['clean_artist_name'] = {
                'working': False,
                'error': str(e)
            }
    
    # Test du gestionnaire d'export
    if 'ExportManager' in globals():
        try:
            export_mgr = ExportManager()
            function_tests['ExportManager'] = {
                'working': True,
                'instance_created': export_mgr is not None
            }
        except Exception as e:
            function_tests['ExportManager'] = {
                'working': False,
                'error': str(e)
            }
    
    diagnostics['function_tests'] = function_tests
    
    return diagnostics

def validate_utils_setup() -> Tuple[bool, List[str]]:
    """
    Valide la configuration du module utils.
    
    Returns:
        Tuple (configuration_valide, liste_problèmes)
    """
    issues = []
    
    # Vérifier que les utilitaires critiques sont disponibles
    critical_utils = ['text_utils', 'export_utils', 'logging_config']
    available_modules = list(_available_modules.keys())
    
    for util in critical_utils:
        if util not in available_modules:
            issues.append(f"Module utilitaire critique manquant: {util}")
        elif _available_modules[util]['status'] != 'success':
            issues.append(f"Module utilitaire {util} en erreur: {_available_modules[util].get('error', 'Erreur inconnue')}")
    
    # Vérifier qu'au moins quelques fonctions sont disponibles
    if len(__all__) < 5:
        issues.append("Trop peu de fonctions utilitaires disponibles")
    
    return len(issues) == 0, issues

# ===== FONCTIONS DE CONVENANCE =====

def quick_text_clean(text: str) -> str:
    """Fonction de convenance pour nettoyage rapide de texte"""
    if 'normalize_text' in globals():
        return normalize_text(text)
    else:
        # Fallback basique si text_utils n'est pas disponible
        return text.strip() if text else ""

def quick_export(data: Any, format_type: str = "json", filename: Optional[str] = None) -> Optional[str]:
    """Fonction de convenance pour export rapide"""
    if 'ExportManager' in globals():
        try:
            manager = ExportManager()
            return manager.export_data(data, format_type, filename)
        except Exception as e:
            logger.error(f"Erreur export rapide: {e}")
            return None
    else:
        logger.warning("ExportManager non disponible pour l'export rapide")
        return None

def get_text_utils_help() -> str:
    """Retourne l'aide pour les fonctions de manipulation de texte"""
    if not list_text_utils():
        return "❌ Aucune fonction de manipulation de texte disponible"
    
    help_text = "📝 Fonctions de manipulation de texte disponibles:\n"
    for func_name in list_text_utils():
        if func_name in globals():
            func = globals()[func_name]
            if hasattr(func, '__doc__') and func.__doc__:
                help_text += f"  • {func_name}: {func.__doc__.split('.')[0]}\n"
            else:
                help_text += f"  • {func_name}\n"
    
    return help_text

# ===== LOGGING ET INITIALISATION =====

logger.info(f"Module utils initialisé - {len(__all__)} fonctions disponibles")

if _import_errors:
    logger.warning(f"⚠️ Erreurs d'import détectées: {list(_import_errors.keys())}")

# ===== EXEMPLES D'UTILISATION =====
"""
Exemples d'utilisation:

# Utilisation des fonctions de texte
if 'clean_artist_name' in dir():
    clean_name = clean_artist_name("  Nekfeu  ")

# Export rapide
export_path = quick_export(data, "json", "my_data")

# Diagnostic complet
status = get_utils_status()
print(f"Utilitaires disponibles: {status['available_functions']}")

# Aide sur les fonctions de texte
print(get_text_utils_help())

# Validation de la configuration
is_valid, issues = validate_utils_setup()
if not is_valid:
    print(f"Problèmes détectés: {issues}")
"""