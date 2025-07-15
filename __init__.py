# __init__.py - Racine du projet
"""
Music Data Extractor - Extracteur de données musicales avec focus rap/hip-hop
"""

__version__ = "1.0.0"
__author__ = "Jeremy Buisan"

# Configuration du logging de base
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

# Imports sécurisés avec gestion d'erreurs
__all__ = []

# Import de la configuration
try:
    from config.settings import settings
    __all__.append('settings')
except ImportError:
    pass

# Imports des modules core
try:
    from core.database import Database
    __all__.append('Database')
except ImportError:
    pass

try:
    from core.session_manager import SessionManager, get_session_manager
    __all__.extend(['SessionManager', 'get_session_manager'])
except ImportError:
    pass

try:
    from core.cache import CacheManager
    __all__.append('CacheManager')
except ImportError:
    pass

# Imports des modèles
try:
    from models.entities import Artist, Track, Album, Credit, Session
    __all__.extend(['Artist', 'Track', 'Album', 'Credit', 'Session'])
except ImportError:
    pass

try:
    from models.enums import SessionStatus, ExtractionStatus
    __all__.extend(['SessionStatus', 'ExtractionStatus'])
except ImportError:
    pass

# Imports des découvreurs
try:
    from discovery.genius_discovery import GeniusDiscovery
    __all__.append('GeniusDiscovery')
except ImportError:
    pass