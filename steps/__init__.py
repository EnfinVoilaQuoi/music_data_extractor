# steps/__init__.py - Version corrigée sans imports circulaires
"""Étapes de traitement du pipeline d'extraction"""

import logging

__all__ = []

# Configuration du logger
logger = logging.getLogger(__name__)

# PAS D'IMPORTS DIRECTS - pour éviter les imports circulaires
# Les modules qui ont besoin des steps les importeront directement

# Fonction helper pour lister les étapes disponibles
def get_available_steps():
    """Retourne la liste des étapes disponibles"""
    return [
        'DiscoveryStep',
        'ExtractionStep', 
        'ProcessingStep',
        'ExportStep'
    ]

# Fonctions d'import dynamique pour éviter les imports circulaires
def get_discovery_step():
    """Import dynamique de DiscoveryStep"""
    try:
        from .step1_discover import DiscoveryStep
        return DiscoveryStep
    except ImportError as e:
        logger.warning(f"⚠️ Erreur import DiscoveryStep: {e}")
        return None

def get_extraction_step():
    """Import dynamique d'ExtractionStep"""
    try:
        from .step2_extract import ExtractionStep
        return ExtractionStep
    except ImportError as e:
        logger.warning(f"⚠️ Erreur import ExtractionStep: {e}")
        return None

def get_processing_step():
    """Import dynamique de ProcessingStep"""
    try:
        from .step3_process import ProcessingStep
        return ProcessingStep
    except ImportError as e:
        logger.warning(f"⚠️ Erreur import ProcessingStep: {e}")
        return None

def get_export_step():
    """Import dynamique d'ExportStep"""
    try:
        from .step4_export import ExportStep
        return ExportStep
    except ImportError as e:
        logger.warning(f"⚠️ Erreur import ExportStep: {e}")
        return None

logger.info("✅ Module steps initialisé sans imports circulaires")