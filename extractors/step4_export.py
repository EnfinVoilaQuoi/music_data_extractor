# extractors/step4_export.py
"""Alias pour compatibilité avec l'ancienne structure"""

try:
    from steps.step4_export import *
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Impossible d'importer depuis steps.step4_export: {e}")
    pass
