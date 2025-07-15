# config/__init__.py
"""Configuration centralisée du projet"""

# Import sécurisé
try:
    from .settings import settings
    __all__ = ['settings']
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Impossible d'importer settings: {e}")
    __all__ = []