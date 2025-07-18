# models/__init__.py
"""Modèles de données et entités du projet - Version optimisée"""

import logging
from typing import List, Dict, Any, Optional, Type
from functools import lru_cache

# Configuration du logging pour le module models
logger = logging.getLogger(__name__)

__all__ = []
_import_errors = {}  # Tracking des erreurs d'import

def _safe_import(module_name: str, class_names: List[str], description: str) -> bool:
    """Import sécurisé avec gestion d'erreurs centralisée"""
    try:
        module = __import__(f".{module_name}", package=__name__, fromlist=class_names)
        
        # Ajouter les classes à __all__ et aux globals
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

# ===== IMPORTS OPTIMISÉS =====

# Import des enums en premier (pas de dépendances externes)
_enums_imported = _safe_import("enums", [
    "AlbumType", "CreditCategory", "CreditType", "SessionStatus",
    "ExtractionStatus", "DataSource", "Genre", "QualityLevel",
    "ExportFormat", "ExtractorType", "DataQuality"
], "Core enums")

# Import des entités (dépendent des enums)
_entities_imported = _safe_import("entities", [
    "Artist", "Album", "Track", "Credit", "Session", 
    "QualityReport", "ExtractionResult"
], "Core entities")

# Import des schémas (dépendent des enums et entités - optionnels)
_schemas_imported = _safe_import("schemas", [
    "ArtistSchema", "AlbumSchema", "TrackSchema", "CreditSchema",
    "QualityCheckSchema", "ExtractionSessionSchema", "ExportSchema", "StatsSchema"
], "Validation schemas")

# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_available_models() -> List[str]:
    """Retourne la liste des modèles disponibles - avec cache"""
    return sorted(__all__)

@lru_cache(maxsize=1)
def get_import_errors() -> Dict[str, str]:
    """Retourne les erreurs d'import pour diagnostic - avec cache"""
    return _import_errors.copy()

def get_models_status() -> Dict[str, Any]:
    """Retourne le statut complet du module models"""
    total_modules = 3  # enums, entities, schemas
    available_modules = sum([_enums_imported, _entities_imported, _schemas_imported])
    
    # Modules critiques vs optionnels
    critical_modules = ['enums', 'entities']
    critical_available = all(m not in _import_errors for m in critical_modules)
    
    return {
        'available_models': get_available_models(),
        'import_errors': get_import_errors(),
        'module_count': {
            'total': total_modules,
            'available': available_modules,
            'failed': len(_import_errors)
        },
        'status': {
            'overall': 'HEALTHY' if available_modules >= 2 else 'DEGRADED' if critical_available else 'CRITICAL',
            'critical_modules_ok': critical_available,
            'completion_rate': round((available_modules / total_modules) * 100, 1)
        },
        'modules': {
            'enums': _enums_imported,
            'entities': _entities_imported,
            'schemas': _schemas_imported
        }
    }

@lru_cache(maxsize=32)
def get_model_by_name(model_name: str) -> Optional[Type]:
    """Retourne une classe de modèle par son nom - avec cache"""
    if model_name in globals():
        return globals()[model_name]
    return None

def get_enum_classes() -> Dict[str, Type]:
    """Retourne toutes les classes enum disponibles"""
    enum_classes = {}
    
    if _enums_imported:
        enum_names = [
            "AlbumType", "CreditCategory", "CreditType", "SessionStatus",
            "ExtractionStatus", "DataSource", "Genre", "QualityLevel",
            "ExportFormat", "ExtractorType", "DataQuality"
        ]
        
        for enum_name in enum_names:
            if enum_name in globals():
                enum_classes[enum_name] = globals()[enum_name]
    
    return enum_classes

def get_entity_classes() -> Dict[str, Type]:
    """Retourne toutes les classes d'entités disponibles"""
    entity_classes = {}
    
    if _entities_imported:
        entity_names = [
            "Artist", "Album", "Track", "Credit", "Session",
            "QualityReport", "ExtractionResult"
        ]
        
        for entity_name in entity_names:
            if entity_name in globals():
                entity_classes[entity_name] = globals()[entity_name]
    
    return entity_classes

def validate_models_dependencies() -> List[str]:
    """Valide les dépendances entre modèles"""
    issues = []
    
    # Vérifier que les modules critiques sont disponibles
    if not _enums_imported:
        issues.append("Module enums indisponible - définitions de base manquantes")
    
    if not _entities_imported:
        issues.append("Module entities indisponible - modèles de données indisponibles")
    
    # Vérifier la cohérence des enums
    if _enums_imported:
        enum_classes = get_enum_classes()
        expected_enums = [
            "AlbumType", "CreditCategory", "CreditType", "SessionStatus",
            "ExtractionStatus", "DataSource", "Genre", "QualityLevel"
        ]
        
        missing_enums = [name for name in expected_enums if name not in enum_classes]
        if missing_enums:
            issues.append(f"Enums manquants: {', '.join(missing_enums)}")
    
    # Vérifier la cohérence des entités
    if _entities_imported:
        entity_classes = get_entity_classes()
        expected_entities = ["Artist", "Album", "Track", "Credit", "Session"]
        
        missing_entities = [name for name in expected_entities if name not in entity_classes]
        if missing_entities:
            issues.append(f"Entités manquantes: {', '.join(missing_entities)}")
    
    # Avertissements pour modules optionnels
    if not _schemas_imported:
        issues.append("Schemas de validation indisponibles (optionnel)")
    
    return issues

def create_entity_from_dict(entity_type: str, data: Dict[str, Any]) -> Optional[Any]:
    """Crée une entité depuis un dictionnaire"""
    entity_class = get_model_by_name(entity_type)
    
    if not entity_class:
        logger.error(f"Classe d'entité inconnue: {entity_type}")
        return None
    
    try:
        # Filtrer les champs qui existent sur l'entité
        if hasattr(entity_class, '__dataclass_fields__'):
            valid_fields = entity_class.__dataclass_fields__.keys()
            filtered_data = {k: v for k, v in data.items() if k in valid_fields}
            return entity_class(**filtered_data)
        else:
            logger.warning(f"{entity_type} n'est pas une dataclass")
            return entity_class(**data)
            
    except Exception as e:
        logger.error(f"Erreur création entité {entity_type}: {e}")
        return None

def export_model_schemas() -> Dict[str, Dict[str, Any]]:
    """Exporte les schémas des modèles pour documentation"""
    schemas = {}
    
    # Schémas des entités
    entity_classes = get_entity_classes()
    for name, entity_class in entity_classes.items():
        if hasattr(entity_class, '__dataclass_fields__'):
            fields = {}
            for field_name, field_info in entity_class.__dataclass_fields__.items():
                fields[field_name] = {
                    'type': str(field_info.type),
                    'default': str(field_info.default) if field_info.default != field_info.default_factory else 'factory',
                    'required': field_info.default == field_info.default_factory
                }
            schemas[name] = {
                'type': 'entity',
                'fields': fields
            }
    
    # Schémas des enums
    enum_classes = get_enum_classes()
    for name, enum_class in enum_classes.items():
        schemas[name] = {
            'type': 'enum',
            'values': [item.value for item in enum_class]
        }
    
    return schemas

# ===== MÉTHODES D'ANALYSE =====

def analyze_models_usage() -> Dict[str, Any]:
    """Analyse l'utilisation des modèles"""
    analysis = {
        'total_classes': len(__all__),
        'enum_classes': len(get_enum_classes()),
        'entity_classes': len(get_entity_classes()),
        'import_success_rate': 0.0,
        'critical_modules_ok': len(_import_errors) == 0,
        'optional_features': {
            'schemas': _schemas_imported
        }
    }
    
    # Calcul du taux de succès d'import
    total_expected = 3  # enums, entities, schemas
    successful_imports = sum([_enums_imported, _entities_imported, _schemas_imported])
    analysis['import_success_rate'] = (successful_imports / total_expected) * 100
    
    return analysis

def get_models_info() -> Dict[str, Any]:
    """Informations complètes sur le module models"""
    return {
        'version': '1.0.0',
        'available_models': get_available_models(),
        'status': get_models_status(),
        'dependencies': validate_models_dependencies(),
        'usage_analysis': analyze_models_usage(),
        'schemas': export_model_schemas() if _entities_imported else {}
    }

# ===== LOGGING ET ÉTAT =====

# Affichage du statut au chargement du module (uniquement si debugging activé)
if logger.isEnabledFor(logging.DEBUG):
    status = get_models_status()
    logger.info(f"📊 Module models chargé - {status['status']['overall']} "
               f"({status['module_count']['available']}/{status['module_count']['total']} modules)")
    
    if _import_errors:
        logger.warning(f"⚠️ Modules avec erreurs: {list(_import_errors.keys())}")

# Export des fonctions utilitaires
__all__.extend([
    'get_available_models',
    'get_import_errors',
    'get_models_status',
    'get_model_by_name',
    'get_enum_classes',
    'get_entity_classes',
    'validate_models_dependencies',
    'create_entity_from_dict',
    'export_model_schemas',
    'analyze_models_usage',
    'get_models_info'
])