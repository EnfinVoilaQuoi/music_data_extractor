# extractors/web_scrapers/step2_extract.py
"""Alias pour compatibilité avec l'ancienne structure"""

try:
    from steps.step2_extract import *
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Impossible d'importer depuis steps.step2_extract: {e}")
    pass
