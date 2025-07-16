# extractors/web_scrapers/step3_process.py
"""Alias pour compatibilité avec l'ancienne structure"""

try:
    from steps.step3_process import *
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Impossible d'importer depuis steps.step3_process: {e}")
    pass
