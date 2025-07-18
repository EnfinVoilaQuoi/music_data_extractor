# steps/__init__.py
"""Étapes de traitement du pipeline d'extraction - Version optimisée"""

import logging
from typing import List, Dict, Any, Optional, Type
from functools import lru_cache

# Configuration du logging pour le module steps
logger = logging.getLogger(__name__)

__all__ = []
_import_errors = {}  # Tracking des erreurs d'import
_step_classes = {}   # Cache des classes d'étapes

def _safe_import_step(step_name: str, module_name: str, class_name: str) -> bool:
    """Import sécurisé d'une étape avec gestion d'erreurs"""
    try:
        module = __import__(f".{module_name}", package=__name__, fromlist=[class_name])
        
        if hasattr(module, class_name):
            step_class = getattr(module, class_name)
            globals()[class_name] = step_class
            _step_classes[step_name] = step_class
            __all__.append(class_name)
            
            logger.debug(f"✅ {class_name} importé depuis {module_name}")
            return True
        else:
            error_msg = f"Classe {class_name} non trouvée dans {module_name}"
            _import_errors[step_name] = error_msg
            logger.warning(f"⚠️ {error_msg}")
            return False
            
    except ImportError as e:
        error_msg = f"Erreur import {class_name}: {e}"
        _import_errors[step_name] = error_msg
        logger.warning(f"⚠️ {error_msg}")
        return False
    except Exception as e:
        error_msg = f"Erreur inattendue import {class_name}: {e}"
        _import_errors[step_name] = error_msg
        logger.error(f"❌ {error_msg}")
        return False

# ===== IMPORTS SÉCURISÉS DES ÉTAPES =====

# Import des étapes du pipeline
_step1_imported = _safe_import_step("discovery", "step1_discover", "DiscoveryStep")
_step2_imported = _safe_import_step("extraction", "step2_extract", "ExtractionStep")
_step3_imported = _safe_import_step("processing", "step3_process", "ProcessingStep")
_step4_imported = _safe_import_step("export", "step4_export", "ExportStep")

# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_available_steps() -> List[str]:
    """Retourne la liste des étapes disponibles - avec cache"""
    return list(_step_classes.keys())

@lru_cache(maxsize=1)
def get_available_step_classes() -> List[str]:
    """Retourne la liste des classes d'étapes disponibles"""
    return sorted(__all__)

@lru_cache(maxsize=1)
def get_import_errors() -> Dict[str, str]:
    """Retourne les erreurs d'import pour diagnostic"""
    return _import_errors.copy()

def get_steps_status() -> Dict[str, Any]:
    """Retourne le statut complet du module steps"""
    total_steps = 4  # discovery, extraction, processing, export
    available_steps = len(_step_classes)
    
    # Étapes critiques vs optionnelles
    critical_steps = ['discovery', 'extraction']
    critical_available = all(step not in _import_errors for step in critical_steps)
    
    return {
        'available_steps': get_available_steps(),
        'available_step_classes': get_available_step_classes(),
        'import_errors': get_import_errors(),
        'step_count': {
            'total': total_steps,
            'available': available_steps,
            'failed': len(_import_errors)
        },
        'status': {
            'overall': 'HEALTHY' if available_steps >= 3 else 'DEGRADED' if critical_available else 'CRITICAL',
            'critical_steps_ok': critical_available,
            'completion_rate': round((available_steps / total_steps) * 100, 1)
        },
        'steps': {
            'discovery': _step1_imported,
            'extraction': _step2_imported,
            'processing': _step3_imported,
            'export': _step4_imported
        }
    }

# ===== IMPORTS DYNAMIQUES POUR ÉVITER LES IMPORTS CIRCULAIRES =====

def get_discovery_step() -> Optional[Type]:
    """Import dynamique de DiscoveryStep"""
    if 'discovery' in _step_classes:
        return _step_classes['discovery']
    
    # Tentative d'import si pas encore fait
    if _safe_import_step("discovery", "step1_discover", "DiscoveryStep"):
        return _step_classes.get('discovery')
    
    return None

def get_extraction_step() -> Optional[Type]:
    """Import dynamique d'ExtractionStep"""
    if 'extraction' in _step_classes:
        return _step_classes['extraction']
    
    if _safe_import_step("extraction", "step2_extract", "ExtractionStep"):
        return _step_classes.get('extraction')
    
    return None

def get_processing_step() -> Optional[Type]:
    """Import dynamique de ProcessingStep"""
    if 'processing' in _step_classes:
        return _step_classes['processing']
    
    if _safe_import_step("processing", "step3_process", "ProcessingStep"):
        return _step_classes.get('processing')
    
    return None

def get_export_step() -> Optional[Type]:
    """Import dynamique d'ExportStep"""
    if 'export' in _step_classes:
        return _step_classes['export']
    
    if _safe_import_step("export", "step4_export", "ExportStep"):
        return _step_classes.get('export')
    
    return None

def get_step_by_name(step_name: str) -> Optional[Type]:
    """Retourne une classe d'étape par son nom"""
    step_mapping = {
        'discovery': get_discovery_step,
        'extraction': get_extraction_step,
        'processing': get_processing_step,
        'export': get_export_step
    }
    
    getter = step_mapping.get(step_name.lower())
    if getter:
        return getter()
    
    return None

def validate_steps_dependencies() -> List[str]:
    """Valide les dépendances entre étapes"""
    issues = []
    
    # Vérifier que les étapes critiques sont disponibles
    if not _step1_imported:
        issues.append("DiscoveryStep indisponible - impossible de découvrir les morceaux")
    
    if not _step2_imported:
        issues.append("ExtractionStep indisponible - impossible d'extraire les données")
    
    # Vérifier les dépendances logiques
    if _step2_imported and not _step1_imported:
        issues.append("ExtractionStep disponible mais DiscoveryStep manquant - pipeline incomplet")
    
    if _step4_imported and not _step3_imported:
        issues.append("ExportStep disponible mais ProcessingStep manquant - pipeline incomplet")
    
    # Avertissements pour étapes optionnelles
    optional_warnings = []
    if not _step3_imported:
        optional_warnings.append("ProcessingStep indisponible - pas de traitement post-extraction")
    
    if not _step4_imported:
        optional_warnings.append("ExportStep indisponible - pas d'export automatique")
    
    if optional_warnings:
        issues.extend(optional_warnings)
    
    return issues

# ===== PIPELINE ET ORCHESTRATION =====

class PipelineOrchestrator:
    """Orchestrateur pour exécuter le pipeline complet"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.PipelineOrchestrator")
        self.steps = {}
        self._initialize_steps()
    
    def _initialize_steps(self):
        """Initialise les étapes disponibles"""
        step_getters = {
            'discovery': get_discovery_step,
            'extraction': get_extraction_step,
            'processing': get_processing_step,
            'export': get_export_step
        }
        
        for step_name, getter in step_getters.items():
            step_class = getter()
            if step_class:
                self.steps[step_name] = step_class
                self.logger.debug(f"Étape {step_name} initialisée")
            else:
                self.logger.warning(f"Étape {step_name} non disponible")
    
    def get_available_pipeline_steps(self) -> List[str]:
        """Retourne les étapes disponibles pour le pipeline"""
        return list(self.steps.keys())
    
    def can_run_full_pipeline(self) -> bool:
        """Vérifie si le pipeline complet peut être exécuté"""
        critical_steps = ['discovery', 'extraction']
        return all(step in self.steps for step in critical_steps)
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Retourne le statut du pipeline"""
        return {
            'available_steps': self.get_available_pipeline_steps(),
            'can_run_full': self.can_run_full_pipeline(),
            'step_count': len(self.steps),
            'critical_steps_ok': all(step in self.steps for step in ['discovery', 'extraction'])
        }

# ===== ANALYSE ET DIAGNOSTIC =====

def analyze_steps_performance() -> Dict[str, Any]:
    """Analyse les performances des étapes"""
    analysis = {
        'total_steps': len(_step_classes),
        'import_success_rate': 0.0,
        'critical_steps_ok': len([s for s in ['discovery', 'extraction'] if s not in _import_errors]) == 2,
        'optional_steps_available': {
            'processing': _step3_imported,
            'export': _step4_imported
        }
    }
    
    # Calcul du taux de succès d'import
    total_expected = 4  # 4 étapes
    successful_imports = len(_step_classes)
    analysis['import_success_rate'] = (successful_imports / total_expected) * 100
    
    return analysis

def get_steps_info() -> Dict[str, Any]:
    """Informations complètes sur le module steps"""
    return {
        'version': '1.0.0',
        'available_steps': get_available_steps(),
        'available_classes': get_available_step_classes(),
        'status': get_steps_status(),
        'dependencies': validate_steps_dependencies(),
        'performance_analysis': analyze_steps_performance(),
        'pipeline_status': PipelineOrchestrator().get_pipeline_status()
    }

def run_steps_diagnostics() -> Dict[str, Any]:
    """Exécute un diagnostic complet des étapes"""
    return {
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'steps_info': get_steps_info(),
        'import_status': get_steps_status(),
        'dependency_issues': validate_steps_dependencies(),
        'orchestrator_status': PipelineOrchestrator().get_pipeline_status()
    }

# ===== LOGGING ET ÉTAT =====

# Affichage du statut au chargement du module
if logger.isEnabledFor(logging.DEBUG):
    status = get_steps_status()
    logger.info(f"🔧 Module steps chargé - {status['status']['overall']} "
               f"({status['step_count']['available']}/{status['step_count']['total']} étapes)")
    
    if _import_errors:
        logger.warning(f"⚠️ Étapes avec erreurs: {list(_import_errors.keys())}")

# Export des fonctions utilitaires
__all__.extend([
    'get_available_steps',
    'get_available_step_classes',
    'get_import_errors',
    'get_steps_status',
    'get_discovery_step',
    'get_extraction_step',
    'get_processing_step',
    'get_export_step',
    'get_step_by_name',
    'validate_steps_dependencies',
    'PipelineOrchestrator',
    'analyze_steps_performance',
    'get_steps_info',
    'run_steps_diagnostics'
])