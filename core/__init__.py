# core/__init__.py
"""Modules core du projet - base de données, cache, sessions"""

__all__ = []

# Import des exceptions en premier (pas de dépendances)
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
    print("✅ Core exceptions importées")
except ImportError as e:
    print(f"⚠️ Erreur import exceptions: {e}")

# Import des autres modules core
try:
    from .database import Database
    __all__.append('Database')
    print("✅ Database importé")
except ImportError as e:
    print(f"⚠️ Erreur import Database: {e}")

try:
    from .cache import CacheManager
    __all__.append('CacheManager')
    print("✅ CacheManager importé")
except ImportError as e:
    print(f"⚠️ Erreur import CacheManager: {e}")

try:
    from .rate_limiter import RateLimiter
    __all__.append('RateLimiter')
    print("✅ RateLimiter importé")
except ImportError as e:
    print(f"⚠️ Erreur import RateLimiter: {e}")

try:
    from .session_manager import SessionManager, get_session_manager
    __all__.extend(['SessionManager', 'get_session_manager'])
    print("✅ SessionManager importé")
except ImportError as e:
    print(f"⚠️ Erreur import SessionManager: {e}")

def get_available_core_modules():
    """Retourne la liste des modules core disponibles"""
    return __all__