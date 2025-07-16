# extractors/web_scrapers/text_utils.py
"""Alias pour compatibilité avec l'ancienne structure"""

try:
    from utils.text_utils import *
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Impossible d'importer depuis utils.text_utils: {e}")
    pass
