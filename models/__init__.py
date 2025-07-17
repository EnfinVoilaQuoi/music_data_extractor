# models/__init__.py - Version corrigée
"""Modèles de données et entités du projet"""

import logging

__all__ = []

logger = logging.getLogger(__name__)

# Import des entités avec gestion d'erreurs
try:
    from .entities import Artist, Album, Track, Credit, Session, QualityReport, ExtractionResult
    __all__.extend(['Artist', 'Album', 'Track', 'Credit', 'Session', 'QualityReport', 'ExtractionResult'])
    logger.info("✅ Entités importées")
except ImportError as e:
    logger.warning(f"⚠️ Impossible d'importer les entités: {e}")

# Import des énumérations avec gestion d'erreurs
try:
    from .enums import (
        AlbumType, CreditCategory, CreditType, SessionStatus, 
        ExtractionStatus, DataSource, Genre, QualityLevel, ExportFormat
    )
    __all__.extend([
        'AlbumType', 'CreditCategory', 'CreditType', 'SessionStatus',
        'ExtractionStatus', 'DataSource', 'Genre', 'QualityLevel', 'ExportFormat'
    ])
    logger.info("✅ Énumérations importées")
except ImportError as e:
    logger.warning(f"⚠️ Impossible d'importer les énumérations: {e}")

# Import des schémas avec gestion d'erreurs
try:
    from .schemas import (
        ArtistSchema, AlbumSchema, TrackSchema, CreditSchema,
        QualityCheckSchema, ExtractionSessionSchema, ExportSchema, StatsSchema
    )
    __all__.extend([
        'ArtistSchema', 'AlbumSchema', 'TrackSchema', 'CreditSchema',
        'QualityCheckSchema', 'ExtractionSessionSchema', 'ExportSchema', 'StatsSchema'
    ])
    logger.info("✅ Schémas importés")
except ImportError as e:
    logger.warning(f"⚠️ Impossible d'importer les schémas: {e}")

logger.info("✅ Module models initialisé")