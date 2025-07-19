# utils/import_helpers.py
"""
Module d'aide pour les imports sécurisés dans Music Data Extractor.
Centralise la logique d'import avec gestion d'erreurs et tracking.
"""

import importlib
import logging
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple, Type
import sys

logger = logging.getLogger(__name__)

# Cache global des imports réussis/échoués
_import_cache = {
    'successful': {},
    'failed': {},
    'stats': {
        'total_attempts': 0,
        'successful': 0,
        'failed': 0
    }
}


def safe_import(module_name: str, class_names: List[str], 
                package: Optional[str] = None,
                description: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
    """
    Import sécurisé avec tracking et gestion d'erreurs centralisée.
    
    Args:
        module_name: Nom du module à importer
        class_names: Liste des classes/fonctions à importer
        package: Package parent pour les imports relatifs
        description: Description pour les logs
        
    Returns:
        Tuple (succès, dict des objets importés)
    """
    global _import_cache
    _import_cache['stats']['total_attempts'] += 1
    
    # Vérifier le cache
    cache_key = f"{package}.{module_name}" if package else module_name
    if cache_key in _import_cache['successful']:
        return True, _import_cache['successful'][cache_key]
    
    imported_objects = {}
    desc = description or f"module {module_name}"
    
    try:
        # Import du module
        if package:
            module = importlib.import_module(f".{module_name}", package=package)
        else:
            module = importlib.import_module(module_name)
        
        # Extraire les classes/fonctions demandées
        missing_items = []
        for class_name in class_names:
            if hasattr(module, class_name):
                imported_objects[class_name] = getattr(module, class_name)
            else:
                missing_items.append(class_name)
        
        if missing_items:
            logger.warning(f"⚠️ {desc}: éléments manquants {missing_items}")
        
        # Mettre en cache et tracker
        _import_cache['successful'][cache_key] = imported_objects
        _import_cache['stats']['successful'] += 1
        
        if imported_objects:
            logger.debug(f"✅ {desc} importé ({len(imported_objects)} éléments)")
            return True, imported_objects
        else:
            return False, {}
            
    except ImportError as e:
        error_msg = f"Erreur import {desc}: {e}"
        _import_cache['failed'][cache_key] = error_msg
        _import_cache['stats']['failed'] += 1
        logger.debug(f"⚠️ {error_msg}")
        return False, {}
        
    except Exception as e:
        error_msg = f"Erreur inattendue import {desc}: {e}"
        _import_cache['failed'][cache_key] = error_msg
        _import_cache['stats']['failed'] += 1
        logger.error(f"❌ {error_msg}")
        return False, {}


def safe_import_module(module_path: str, required: bool = False) -> Optional[Any]:
    """
    Import sécurisé d'un module complet.
    
    Args:
        module_path: Chemin complet du module
        required: Si True, log une erreur si l'import échoue
        
    Returns:
        Module importé ou None
    """
    try:
        return importlib.import_module(module_path)
    except ImportError as e:
        if required:
            logger.error(f"❌ Module requis manquant: {module_path} - {e}")
        else:
            logger.debug(f"⚠️ Module optionnel manquant: {module_path}")
        return None


def batch_import(imports: List[Dict[str, Any]], globals_dict: Dict[str, Any],
                 all_list: List[str]) -> Dict[str, Any]:
    """
    Import en batch de plusieurs modules avec mise à jour des globals et __all__.
    
    Args:
        imports: Liste des imports à effectuer
        globals_dict: Dictionnaire globals() du module appelant
        all_list: Liste __all__ du module appelant
        
    Returns:
        Statistiques des imports
    """
    stats = {
        'attempted': len(imports),
        'successful': 0,
        'failed': 0,
        'imported_items': []
    }
    
    for import_spec in imports:
        module_name = import_spec.get('module')
        class_names = import_spec.get('classes', [])
        package = import_spec.get('package')
        description = import_spec.get('description')
        required = import_spec.get('required', False)
        
        success, objects = safe_import(
            module_name, class_names, package, description
        )
        
        if success and objects:
            # Mettre à jour globals et __all__
            for name, obj in objects.items():
                globals_dict[name] = obj
                if name not in all_list:
                    all_list.append(name)
                stats['imported_items'].append(name)
            
            stats['successful'] += 1
        else:
            stats['failed'] += 1
            if required:
                logger.error(f"❌ Import requis échoué: {module_name}")
    
    return stats


@lru_cache(maxsize=1)
def get_import_stats() -> Dict[str, Any]:
    """
    Retourne les statistiques globales d'import.
    
    Returns:
        Dictionnaire des statistiques
    """
    stats = _import_cache['stats'].copy()
    stats['success_rate'] = (
        (stats['successful'] / max(stats['total_attempts'], 1)) * 100
    )
    stats['failed_modules'] = list(_import_cache['failed'].keys())
    stats['successful_modules'] = list(_import_cache['successful'].keys())
    
    return stats


def check_dependencies(dependencies: List[str]) -> Dict[str, bool]:
    """
    Vérifie la disponibilité des dépendances.
    
    Args:
        dependencies: Liste des modules à vérifier
        
    Returns:
        Dict module -> disponible
    """
    results = {}
    
    for dep in dependencies:
        try:
            importlib.import_module(dep)
            results[dep] = True
        except ImportError:
            results[dep] = False
            
    return results


def lazy_import(module_path: str) -> Type:
    """
    Import paresseux d'un module (import au premier accès).
    
    Args:
        module_path: Chemin du module
        
    Returns:
        Proxy pour l'import paresseux
    """
    class LazyModule:
        _module = None
        
        def __getattr__(self, name):
            if self._module is None:
                self._module = importlib.import_module(module_path)
            return getattr(self._module, name)
    
    return LazyModule()


# Export des fonctions principales
__all__ = [
    'safe_import',
    'safe_import_module',
    'batch_import',
    'get_import_stats',
    'check_dependencies',
    'lazy_import'
]
