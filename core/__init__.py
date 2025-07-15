# core/__init__.py
"""Modules core du projet - base de données, cache, sessions"""

import logging

# Liste des exports disponibles
__all__ = []

# Import de la base de données
try:
    from .database import Database
    __all__.append('Database')
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer Database: {e}")

# Import du cache
try:
    from .cache import CacheManager, SmartCache, CacheStats
    __all__.extend(['CacheManager', 'SmartCache', 'CacheStats'])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer les modules de cache: {e}")

# Import du rate limiter
try:
    from .rate_limiter import RateLimiter, AdaptiveRateLimiter
    __all__.extend(['RateLimiter', 'AdaptiveRateLimiter'])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer les rate limiters: {e}")

# Import du gestionnaire de sessions
try:
    from .session_manager import SessionManager, get_session_manager
    __all__.extend(['SessionManager', 'get_session_manager'])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer le session manager: {e}")

# Import des exceptions
try:
    from .exceptions import (
        MusicDataExtractorError,
        APIError,
        APIRateLimitError,
        APIAuthenticationError,
        ScrapingError,
        DatabaseError,
        DataError,
        ExtractionError,
        CacheError,
        SessionError,
        ExportError
    )
    __all__.extend([
        'MusicDataExtractorError',
        'APIError',
        'APIRateLimitError',
        'APIAuthenticationError',
        'ScrapingError',
        'DatabaseError',
        'DataError',
        'ExtractionError',
        'CacheError',
        'SessionError',
        'ExportError'
    ])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer les exceptions: {e}")