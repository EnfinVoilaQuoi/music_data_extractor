# extractors/web_scrapers/__init__.py
"""Module de compatibilité pour web scrapers"""

import logging

__all__ = []

logger = logging.getLogger(__name__)

# Réexporter les étapes depuis le module steps
try:
    from steps.step1_discover import DiscoveryStep
    __all__.append('DiscoveryStep')
    logger.info("✅ DiscoveryStep réexporté")
except ImportError as e:
    logger.warning(f"⚠️ Impossible de réexporter DiscoveryStep: {e}")

try:
    from steps.step2_extract import ExtractionStep
    __all__.append('ExtractionStep')
    logger.info("✅ ExtractionStep réexporté")
except ImportError as e:
    logger.warning(f"⚠️ Impossible de réexporter ExtractionStep: {e}")

try:
    from steps.step3_process import ProcessingStep
    __all__.append('ProcessingStep')
    logger.info("✅ ProcessingStep réexporté")
except ImportError as e:
    logger.warning(f"⚠️ Impossible de réexporter ProcessingStep: {e}")

try:
    from steps.step4_export import ExportStep
    __all__.append('ExportStep')
    logger.info("✅ ExportStep réexporté")
except ImportError as e:
    logger.warning(f"⚠️ Impossible de réexporter ExportStep: {e}")

# Réexporter les utilitaires
try:
    from utils.text_utils import *
    logger.info("✅ Text utils réexportées")
except ImportError as e:
    logger.warning(f"⚠️ Impossible de réexporter text_utils: {e}")
