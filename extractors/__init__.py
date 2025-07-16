# extractors/__init__.py
"""Extracteurs et modules d'extraction de données musicales"""

import logging

__all__ = []

# Configuration du logger
logger = logging.getLogger(__name__)

# Import des extracteurs principaux
try:
    from .genius_extractor import GeniusExtractor
    __all__.append('GeniusExtractor')
    logger.info("✅ GeniusExtractor importé")
except (ImportError, SyntaxError) as e:
    logger.warning(f"⚠️ Impossible d'importer GeniusExtractor: {e}")

try:
    from .spotify_extractor import SpotifyExtractor
    __all__.append('SpotifyExtractor')
    logger.info("✅ SpotifyExtractor importé")
except (ImportError, SyntaxError) as e:
    logger.warning(f"⚠️ Impossible d'importer SpotifyExtractor: {e}")

try:
    from .credit_extractor import CreditExtractor
    __all__.append('CreditExtractor')
    logger.info("✅ CreditExtractor importé")
except (ImportError, SyntaxError) as e:
    logger.warning(f"⚠️ Impossible d'importer CreditExtractor: {e}")

# Import des utilitaires
try:
    from utils.export_utils import ExportManager
    __all__.append('ExportManager')
    logger.info("✅ ExportManager importé")
except ImportError as e:
    logger.warning(f"⚠️ Impossible d'importer ExportManager: {e}")

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
