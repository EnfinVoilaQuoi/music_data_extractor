# models/__init__.py
"""Modèles de données et entités du projet"""

import logging

__all__ = []

# Import des entités
try:
    from .entities import Artist, Album, Track, Credit, Session, QualityReport, ExtractionResult
    __all__.extend(['Artist', 'Album', 'Track', 'Credit', 'Session', 'QualityReport', 'ExtractionResult'])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer les entités: {e}")

# Import des énumérations
try:
    from .enums import (
        AlbumType, CreditCategory, CreditType, SessionStatus, 
        ExtractionStatus, DataSource, Genre, QualityLevel, ExportFormat
    )
    __all__.extend([
        'AlbumType', 'CreditCategory', 'CreditType', 'SessionStatus',
        'ExtractionStatus', 'DataSource', 'Genre', 'QualityLevel', 'ExportFormat'
    ])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer les énumérations: {e}")

# Import des schémas
try:
    from .schemas import (
        ArtistSchema, AlbumSchema, TrackSchema, CreditSchema,
        QualityCheckSchema, ExtractionSessionSchema, ExportSchema, StatsSchema
    )
    __all__.extend([
        'ArtistSchema', 'AlbumSchema', 'TrackSchema', 'CreditSchema',
        'QualityCheckSchema', 'ExtractionSessionSchema', 'ExportSchema', 'StatsSchema'
    ])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer les schémas: {e}")

# ===== steps/__init__.py =====
"""Étapes du pipeline d'extraction"""

import logging

__all__ = []

try:
    from .step1_discover import DiscoveryStep
    __all__.append('DiscoveryStep')
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer DiscoveryStep: {e}")

try:
    from .step2_extract import ExtractionStep
    __all__.append('ExtractionStep')
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer ExtractionStep: {e}")

try:
    from steps.step3_process import ProcessingStep
    __all__.append('ProcessingStep')
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer ProcessingStep: {e}")

try:
    from .step4_export import ExportStep
    __all__.append('ExportStep')
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer ExportStep: {e}")

# ===== utils/__init__.py =====
"""Utilitaires et fonctions helper"""

import logging

__all__ = []

try:
    from .export_utils import ExportManager, ExportFormat
    __all__.extend(['ExportManager', 'ExportFormat'])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer export_utils: {e}")

try:
    from .text_utils import (
        clean_artist_name, normalize_title, extract_featured_artists_from_title,
        parse_artist_list, clean_album_title, detect_language, similarity_ratio
    )
    __all__.extend([
        'clean_artist_name', 'normalize_title', 'extract_featured_artists_from_title',
        'parse_artist_list', 'clean_album_title', 'detect_language', 'similarity_ratio'
    ])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer text_utils: {e}")
