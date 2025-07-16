# extractors/web_scrapers/__init__.py - VERSION CORRIGÉE
"""Module de compatibilité pour web scrapers"""

import logging

__all__ = []

logger = logging.getLogger(__name__)

# SUPPRESSION DES RÉEXPORTS PROBLÉMATIQUES
# Ces imports créent des imports circulaires car ils tentent d'importer depuis steps/
# qui lui-même peut importer depuis extractors/

# Au lieu d'importer automatiquement, on propose des fonctions d'import dynamique
def get_discovery_step():
    """Import dynamique de DiscoveryStep pour éviter les imports circulaires"""
    try:
        from steps.step1_discover import DiscoveryStep
        return DiscoveryStep
    except ImportError as e:
        logger.warning(f"⚠️ Impossible d'importer DiscoveryStep: {e}")
        return None

def get_extraction_step():
    """Import dynamique d'ExtractionStep pour éviter les imports circulaires"""
    try:
        from steps.step2_extract import ExtractionStep
        return ExtractionStep
    except ImportError as e:
        logger.warning(f"⚠️ Impossible d'importer ExtractionStep: {e}")
        return None

def get_processing_step():
    """Import dynamique de ProcessingStep pour éviter les imports circulaires"""
    try:
        from steps.step3_process import ProcessingStep
        return ProcessingStep
    except ImportError as e:
        logger.warning(f"⚠️ Impossible d'importer ProcessingStep: {e}")
        return None

def get_export_step():
    """Import dynamique d'ExportStep pour éviter les imports circulaires"""
    try:
        from steps.step4_export import ExportStep
        return ExportStep
    except ImportError as e:
        logger.warning(f"⚠️ Impossible d'importer ExportStep: {e}")
        return None

# Import sécurisé des utilitaires (pas de risque d'import circulaire)
try:
    from utils.text_utils import (
        clean_artist_name, normalize_text, clean_track_title,
        extract_featuring_artists, calculate_similarity
    )
    __all__.extend([
        'clean_artist_name', 'normalize_text', 'clean_track_title',
        'extract_featuring_artists', 'calculate_similarity'
    ])
    logger.info("✅ Text utils importées")
except ImportError as e:
    logger.warning(f"⚠️ Impossible d'importer text_utils: {e}")

logger.info("✅ Module web_scrapers initialisé sans imports circulaires")