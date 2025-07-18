# processors/__init__.py - VERSION CORRIGÉE
"""
Module de traitement et validation des données extraites.
Gère la validation, le nettoyage et l'enrichissement des données musicales.
"""

import logging
from functools import lru_cache
from typing import Dict, Any, List, Optional, Type

# Configuration du logging
logger = logging.getLogger(__name__)

# Liste des exports publics et tracking des erreurs
__all__ = []
_import_errors = {}
_processor_classes = {}

def _safe_import_processor(processor_name: str, module_name: str, class_name: str) -> bool:
    """Import sécurisé d'un processeur avec gestion d'erreurs"""
    try:
        module = __import__(f".{module_name}", package=__name__, fromlist=[class_name])
        
        if hasattr(module, class_name):
            processor_class = getattr(module, class_name)
            globals()[class_name] = processor_class
            _processor_classes[processor_name] = processor_class
            __all__.append(class_name)
            
            logger.debug(f"✅ {class_name} importé depuis {module_name}")
            return True
        else:
            error_msg = f"Classe {class_name} non trouvée dans {module_name}"
            _import_errors[processor_name] = error_msg
            logger.warning(f"⚠️ {error_msg}")
            return False
            
    except ImportError as e:
        error_msg = f"Erreur import {class_name}: {e}"
        _import_errors[processor_name] = error_msg
        logger.warning(f"⚠️ {error_msg}")
        return False
    except Exception as e:
        error_msg = f"Erreur inattendue import {class_name}: {e}"
        _import_errors[processor_name] = error_msg
        logger.error(f"❌ {error_msg}")
        return False

# ===== IMPORTS SÉCURISÉS DES PROCESSEURS =====

# Import du validateur de données
_validator_imported = _safe_import_processor("data_validator", "data_validator", "DataValidator")

# Import du processeur de crédits
_credit_imported = _safe_import_processor("credit_processor", "credit_processor", "CreditProcessor")

# Import du processeur de texte
_text_imported = _safe_import_processor("text_processor", "text_processor", "TextProcessor")

# Import de l'analyseur de qualité
_quality_imported = _safe_import_processor("quality_analyzer", "quality_analyzer", "QualityAnalyzer")

# Import du processeur de métadonnées
_metadata_imported = _safe_import_processor("metadata_processor", "metadata_processor", "MetadataProcessor")

# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_available_processors() -> List[str]:
    """Retourne la liste des processeurs disponibles - avec cache"""
    return list(_processor_classes.keys())

@lru_cache(maxsize=1)
def get_available_processor_classes() -> List[str]:
    """Retourne la liste des classes de processeurs disponibles"""
    return sorted(__all__)

@lru_cache(maxsize=1)
def get_import_errors() -> Dict[str, str]:
    """Retourne les erreurs d'import pour diagnostic"""
    return _import_errors.copy()

def create_processor(processor_type: str, **kwargs) -> Optional[Any]:
    """
    Factory pour créer un processeur avec gestion d'erreurs.
    
    Args:
        processor_type: Type de processeur ('data_validator', 'credit_processor', etc.)
        **kwargs: Arguments pour le constructeur
        
    Returns:
        Instance du processeur ou None si échec
    """
    if processor_type not in _processor_classes:
        logger.error(f"❌ Type de processeur inconnu: {processor_type}")
        return None
    
    try:
        processor_class = _processor_classes[processor_type]
        return processor_class(**kwargs)
    except Exception as e:
        logger.error(f"❌ Erreur création {processor_type}: {e}")
        return None

@lru_cache(maxsize=32)
def get_processor_capabilities(processor_type: str) -> Dict[str, Any]:
    """
    Retourne les capacités d'un processeur avec cache.
    
    Args:
        processor_type: Type de processeur
        
    Returns:
        Dictionnaire des capacités
    """
    capabilities = {
        'available': False,
        'features': [],
        'methods': [],
        'configuration': {}
    }
    
    try:
        processor = create_processor(processor_type)
        if processor:
            capabilities['available'] = True
            
            # Détection des méthodes disponibles
            methods = [method for method in dir(processor) 
                      if not method.startswith('_') and callable(getattr(processor, method))]
            capabilities['methods'] = methods
            
            # Extraction des capacités spécifiques si disponibles
            if hasattr(processor, 'get_capabilities'):
                capabilities['features'] = processor.get_capabilities()
            
            if hasattr(processor, 'get_config'):
                capabilities['configuration'] = processor.get_config()
                
    except Exception as e:
        logger.debug(f"Erreur évaluation capacités {processor_type}: {e}")
    
    return capabilities

def get_processors_status() -> Dict[str, Any]:
    """Retourne le statut complet du module processors"""
    total_processors = len(_processor_classes) + len(_import_errors)
    success_rate = (len(_processor_classes) / max(total_processors, 1)) * 100
    
    return {
        'total_processors': total_processors,
        'available_processors': len(_processor_classes),
        'failed_imports': len(_import_errors),
        'success_rate': round(success_rate, 2),
        'available_types': get_available_processors(),
        'available_classes': get_available_processor_classes(),
        'import_errors': get_import_errors()
    }

def run_processors_diagnostics() -> Dict[str, Any]:
    """
    Lance des diagnostics complets sur tous les processeurs.
    
    Returns:
        Rapport de diagnostic détaillé
    """
    diagnostics = {
        'module_info': {
            'total_classes': len(__all__),
            'available_processors': get_available_processors()
        },
        'import_status': get_processors_status(),
        'capabilities': {}
    }
    
    # Test de création des processeurs
    processor_tests = {}
    
    for processor_type in get_available_processors():
        try:
            processor = create_processor(processor_type)
            processor_tests[processor_type] = {
                'creation_success': processor is not None,
                'capabilities': get_processor_capabilities(processor_type)
            }
            
            # Test de santé si disponible
            if processor and hasattr(processor, 'health_check'):
                processor_tests[processor_type]['health_check'] = processor.health_check()
                
        except Exception as e:
            processor_tests[processor_type] = {
                'creation_success': False,
                'error': str(e),
                'capabilities': {}
            }
    
    diagnostics['processor_tests'] = processor_tests
    
    return diagnostics

def validate_processors_setup() -> Tuple[bool, List[str]]:
    """
    Valide la configuration du module processors.
    
    Returns:
        Tuple (configuration_valide, liste_problèmes)
    """
    issues = []
    
    # Vérifier qu'au moins un processeur principal est disponible
    critical_processors = ['data_validator', 'credit_processor']
    available = get_available_processors()
    
    for processor in critical_processors:
        if processor not in available:
            issues.append(f"Processeur critique manquant: {processor}")
    
    # Vérifier la cohérence des imports
    if len(get_available_processors()) == 0:
        issues.append("Aucun processeur disponible")
    
    return len(issues) == 0, issues

# ===== FONCTIONS DE TRAITEMENT BATCH =====

def batch_process_data(data_items: List[Dict[str, Any]], processor_types: List[str], 
                       **kwargs) -> Dict[str, List[Dict[str, Any]]]:
    """
    Traite une liste d'éléments avec plusieurs processeurs.
    
    Args:
        data_items: Liste d'éléments à traiter
        processor_types: Liste des types de processeurs à utiliser
        **kwargs: Arguments additionnels pour les processeurs
        
    Returns:
        Dictionnaire des résultats par processeur
    """
    results = {}
    
    for processor_type in processor_types:
        processor = create_processor(processor_type, **kwargs)
        if not processor:
            continue
            
        processor_results = []
        
        for item in data_items:
            try:
                # Appel de la méthode appropriée selon le type de processeur
                if hasattr(processor, 'process_item'):
                    result = processor.process_item(item)
                elif hasattr(processor, 'validate'):
                    result = processor.validate(item)
                elif hasattr(processor, 'analyze'):
                    result = processor.analyze(item)
                else:
                    continue
                
                if result:
                    result['original_item'] = item
                    result['processor_type'] = processor_type
                    processor_results.append(result)
                    
            except Exception as e:
                logger.error(f"❌ Erreur traitement {processor_type} pour item: {e}")
                continue
        
        results[processor_type] = processor_results
    
    return results

# ===== LOGGING ET DIAGNOSTICS =====

logger.info(f"Module processors initialisé - {len(__all__)} processeurs disponibles")

if _import_errors:
    logger.warning(f"⚠️ Erreurs d'import détectées: {list(_import_errors.keys())}")

# ===== EXEMPLES D'UTILISATION =====
"""
Exemples d'utilisation:

# Création d'un validateur
validator = create_processor('data_validator')
if validator:
    result = validator.validate_track(track)

# Diagnostic complet
status = get_processors_status()
print(f"Processeurs disponibles: {status['available_processors']}")

# Traitement en lot
results = batch_process_data(
    data_items=[track1, track2, track3],
    processor_types=['data_validator', 'quality_analyzer']
)
"""