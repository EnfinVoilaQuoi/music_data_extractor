# models/__init__.py
"""Modèles de données et entités du projet"""

__all__ = []

# Import des enums en premier (pas de dépendances externes)
try:
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
    __all__.extend([
        'AlbumType',
        'CreditCategory',
        'CreditType',
        'SessionStatus', 
        'ExtractionStatus',
        'DataSource',
        'Genre',
        'QualityLevel',
        'ExportFormat'
    ])
except ImportError as e:
    print(f"⚠️ Erreur import enums: {e}")

# Import des entités (dépendent des enums)
try:
    from .entities import Artist, Album, Track, Credit, Session, QualityReport, ExtractionResult
    __all__.extend([
        'Artist',
        'Album',
        'Track', 
        'Credit',
        'Session',
        'QualityReport',
        'ExtractionResult'
    ])
except ImportError as e:
    print(f"⚠️ Erreur import entities: {e}")

# Import des schémas (dépendent des enums et entités)
try:
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
    __all__.extend([
        'ArtistSchema',
        'AlbumSchema',
        'TrackSchema',
        'CreditSchema',
        'QualityCheckSchema',
        'ExtractionSessionSchema',
        'ExportSchema',
        'StatsSchema'
    ])
except ImportError as e:
    print(f"⚠️ Erreur import schemas: {e}")
    # Les schémas sont optionnels (nécessitent pydantic)