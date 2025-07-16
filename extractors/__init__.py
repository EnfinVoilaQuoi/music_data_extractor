# extractors/__init__.py
"""Modèles de données et entités du projet"""

import logging

__all__ = []

# Import des modèles depuis le répertoire parent
try:
    from models.entities import Artist, Album, Track, Credit, Session, QualityReport, ExtractionResult
    __all__.extend(['Artist', 'Album', 'Track', 'Credit', 'Session', 'QualityReport', 'ExtractionResult'])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer les entités: {e}")

try:
    from models.enums import (
        AlbumType, CreditCategory, CreditType, SessionStatus, 
        ExtractionStatus, DataSource, Genre, QualityLevel, ExportFormat
    )
    __all__.extend([
        'AlbumType', 'CreditCategory', 'CreditType', 'SessionStatus',
        'ExtractionStatus', 'DataSource', 'Genre', 'QualityLevel', 'ExportFormat'
    ])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer les énumérations: {e}")

try:
    from models.schemas import (
        ArtistSchema, AlbumSchema, TrackSchema, CreditSchema,
        QualityCheckSchema, ExtractionSessionSchema, ExportSchema, StatsSchema
    )
    __all__.extend([
        'ArtistSchema', 'AlbumSchema', 'TrackSchema', 'CreditSchema',
        'QualityCheckSchema', 'ExtractionSessionSchema', 'ExportSchema', 'StatsSchema'
    ])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer les schémas: {e}")

# Import des extracteurs principaux
try:
    from .genius_extractor import GeniusExtractor
    __all__.append('GeniusExtractor')
except (ImportError, SyntaxError) as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer GeniusExtractor: {e}")

try:
    from .spotify_extractor import SpotifyExtractor
    __all__.append('SpotifyExtractor')
except (ImportError, SyntaxError) as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer SpotifyExtractor: {e}")

try:
    from .credit_extractor import CreditExtractor
    __all__.append('CreditExtractor')
except (ImportError, SyntaxError) as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer CreditExtractor: {e}")

# Import des étapes depuis le répertoire parent
try:
    from steps.step1_discover import DiscoveryStep
    __all__.append('DiscoveryStep')
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer DiscoveryStep: {e}")

try:
    from steps.step2_extract import ExtractionStep
    __all__.append('ExtractionStep')
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer ExtractionStep: {e}")

try:
    from steps.step3_process import ProcessingStep
    __all__.append('ProcessingStep')
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer ProcessingStep: {e}")

try:
    from steps.step4_export import ExportStep
    __all__.append('ExportStep')
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer ExportStep: {e}")

# Import des utilitaires depuis le répertoire parent
try:
    from utils.export_utils import ExportManager
    __all__.append('ExportManager')
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer export_utils: {e}")

try:
    from utils.text_utils import (
        clean_artist_name, normalize_text, clean_track_title,
        extract_featuring_artists, calculate_similarity
    )
    __all__.extend([
        'clean_artist_name', 'normalize_text', 'clean_track_title',
        'extract_featuring_artists', 'calculate_similarity'
    ])
except ImportError as e:
    logging.getLogger(__name__).warning(f"Impossible d'importer text_utils: {e}")
