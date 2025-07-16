# extractors/step1_discover.py
"""Alias pour compatibilité avec l'ancienne structure"""

try:
    from steps.step1_discover import *
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Impossible d'importer depuis steps.step1_discover: {e}")
    pass
