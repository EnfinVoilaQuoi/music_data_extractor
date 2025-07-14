# music_data_extractor/__init__.py
"""
Music Data Extractor - Extracteur de données musicales avec focus rap/hip-hop

Ce package permet d'extraire, traiter et analyser les données musicales
depuis diverses sources (Genius, Spotify, Discogs, Last.fm, Rapedia.fr) pour créer
une base de données complète avec crédits détaillés par artiste.
"""

__version__ = "1.0.0"
__author__ = "Jeremy Buisan"
__email__ = "therapie@google.com"

# Imports principaux pour l'API publique
from .core import Database, CacheManager, SessionManager
from .models import Artist, Track, Album, Credit, Session
from .discovery import GeniusDiscovery
from .config import settings

# Configuration du logging de base
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    'Database',
    'CacheManager', 
    'SessionManager',
    'Artist',
    'Track',
    'Album',
    'Credit',
    'Session',
    'GeniusDiscovery',
    'settings'
]

# ===== config/__init__.py =====
"""Configuration centralisée du projet"""

from .settings import settings

__all__ = ['settings']

# ===== core/__init__.py =====
"""Modules core du projet - base de données, cache, sessions"""

from .database import Database
from .cache import CacheManager, SmartCache, CacheStats
from .rate_limiter import RateLimiter, AdaptiveRateLimiter
from .session_manager import SessionManager, get_session_manager
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

__all__ = [
    # Database
    'Database',
    
    # Cache
    'CacheManager',
    'SmartCache', 
    'CacheStats',
    
    # Rate limiting
    'RateLimiter',
    'AdaptiveRateLimiter',
    
    # Sessions
    'SessionManager',
    'get_session_manager',
    
    # Exceptions
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
]

# ===== models/__init__.py =====
"""Modèles de données et entités du projet"""

from .entities import Artist, Album, Track, Credit, Session, QualityReport, ExtractionResult
from .enums import (
    AlbumType,
    CreditCategory,
    CreditType, 
    SessionStatus,
    ExtractionStatus,
    DataSource,
    Genre,
    QualityLevel,
    ExportFormat
)
from .schemas import (
    ArtistSchema,
    AlbumSchema,
    TrackSchema,
    CreditSchema,
    QualityCheckSchema,
    ExtractionSessionSchema,
    ExportSchema,
    StatsSchema
)

__all__ = [
    # Entities
    'Artist',
    'Album',
    'Track', 
    'Credit',
    'Session',
    'QualityReport',
    'ExtractionResult',
    
    # Enums
    'AlbumType',
    'CreditCategory',
    'CreditType',
    'SessionStatus', 
    'ExtractionStatus',
    'DataSource',
    'Genre',
    'QualityLevel',
    'ExportFormat',
    
    # Schemas
    'ArtistSchema',
    'AlbumSchema',
    'TrackSchema',
    'CreditSchema',
    'QualityCheckSchema',
    'ExtractionSessionSchema',
    'ExportSchema',
    'StatsSchema'
]

# ===== discovery/__init__.py =====
"""Modules de découverte de morceaux depuis diverses sources"""

from .genius_discovery import GeniusDiscovery, DiscoveryResult

# Imports conditionnels pour les modules optionnels
try:
    from .spotify_discovery import SpotifyDiscovery
    __all__ = ['GeniusDiscovery', 'SpotifyDiscovery', 'DiscoveryResult']
except ImportError:
    __all__ = ['GeniusDiscovery', 'DiscoveryResult']

try:
    from .album_resolver import AlbumResolver
    __all__.append('AlbumResolver')
except ImportError:
    pass

# ===== extractors/__init__.py =====
"""Extracteurs de données depuis diverses sources"""

from .base_extractor import BaseExtractor, ExtractionResult, ExtractorConfig

# Imports conditionnels pour les extracteurs optionnels
_available_extractors = ['BaseExtractor']

try:
    from .genius_extractor import GeniusExtractor
    _available_extractors.append('GeniusExtractor')
except ImportError:
    pass

try:
    from .spotify_extractor import SpotifyExtractor
    _available_extractors.append('SpotifyExtractor')
except ImportError:
    pass

try:
    from .discogs_extractor import DiscogsExtractor
    _available_extractors.append('DiscogsExtractor')
except ImportError:
    pass

try:
    from .lastfm_extractor import LastFmExtractor
    _available_extractors.append('LastFmExtractor')
except ImportError:
    pass

__all__ = _available_extractors + ['ExtractionResult', 'ExtractorConfig']

# ===== utils/__init__.py =====
"""Utilitaires et fonctions helper"""

from .text_utils import (
    clean_artist_name,
    normalize_title,
    extract_featured_artists_from_title,
    parse_artist_list,
    clean_album_title,
    detect_language,
    similarity_ratio,
    extract_year_from_date,
    clean_credit_role,
    truncate_text,
    validate_artist_name,
    format_duration,
    parse_duration
)

# Imports conditionnels pour les modules optionnels
_available_utils = [
    'clean_artist_name',
    'normalize_title', 
    'extract_featured_artists_from_title',
    'parse_artist_list',
    'clean_album_title',
    'detect_language',
    'similarity_ratio',
    'extract_year_from_date',
    'clean_credit_role',
    'truncate_text',
    'validate_artist_name',
    'format_duration',
    'parse_duration'
]

try:
    from .selenium_manager import SeleniumManager
    _available_utils.append('SeleniumManager')
except ImportError:
    pass

try:
    from .export_utils import ExportManager, ExportFormat
    _available_utils.extend(['ExportManager', 'ExportFormat'])
except ImportError:
    pass

try:
    from .progress_tracker import ProgressTracker
    _available_utils.append('ProgressTracker')
except ImportError:
    pass

try:
    from .logging_config import setup_logging, get_logger
    _available_utils.extend(['setup_logging', 'get_logger'])
except ImportError:
    pass

__all__ = _available_utils

# ===== steps/__init__.py =====
"""Étapes de traitement du pipeline d'extraction"""

# Imports conditionnels pour les étapes
_available_steps = []

try:
    from .step1_discover import DiscoveryStep
    _available_steps.append('DiscoveryStep')
except ImportError:
    pass

try:
    from .step2_extract import ExtractionStep
    _available_steps.append('ExtractionStep')
except ImportError:
    pass

try:
    from .step3_process import ProcessingStep
    _available_steps.append('ProcessingStep')
except ImportError:
    pass

try:
    from .step4_export import ExportStep
    _available_steps.append('ExportStep')
except ImportError:
    pass

__all__ = _available_steps

# Fonction helper pour lister les étapes disponibles
def get_available_steps():
    """Retourne la liste des étapes disponibles"""
    return _available_steps