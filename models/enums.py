# models/enums.py
from enum import Enum, IntEnum, auto
from functools import lru_cache
from typing import List, Dict, Any, Optional


class AlbumType(Enum):
    """Types d'albums"""
    ALBUM = "album"
    SINGLE = "single" 
    EP = "ep"
    COMPILATION = "compilation"
    REMIX = "remix"
    LIVE = "live"
    SOUNDTRACK = "soundtrack"
    MIXTAPE = "mixtape"
    DEMO = "demo"
    BOOTLEG = "bootleg"
    UNKNOWN = "unknown"

    @classmethod
    @lru_cache(maxsize=1)
    def get_all_values(cls) -> List[str]:
        """Retourne toutes les valeurs possibles - avec cache"""
        return [item.value for item in cls]
    
    @classmethod
    def from_string(cls, value: str) -> 'AlbumType':
        """Convertit une chaîne en AlbumType"""
        if not value:
            return cls.UNKNOWN
        
        value_lower = value.lower().strip()
        for item in cls:
            if item.value == value_lower:
                return item
        return cls.UNKNOWN


class CreditCategory(Enum):
    """Catégories principales de crédits"""
    ARTIST = "artist"           # Artiste principal
    PRODUCTION = "production"   # Production, réalisation
    ENGINEERING = "engineering" # Ingénierie audio (mix, mastering)
    MUSICIAN = "musician"       # Musiciens, instrumentistes
    VOCALS = "vocals"          # Voix additionnelles
    SONGWRITING = "songwriting" # Écriture, composition
    VISUAL = "visual"          # Artwork, vidéos
    BUSINESS = "business"      # Label, management
    OTHER = "other"            # Autres rôles
    UNKNOWN = "unknown"

    @classmethod
    @lru_cache(maxsize=1)
    def get_creative_categories(cls) -> List['CreditCategory']:
        """Retourne les catégories créatives - avec cache"""
        return [cls.ARTIST, cls.PRODUCTION, cls.SONGWRITING, cls.MUSICIAN, cls.VOCALS]
    
    @classmethod
    @lru_cache(maxsize=1)
    def get_technical_categories(cls) -> List['CreditCategory']:
        """Retourne les catégories techniques - avec cache"""
        return [cls.ENGINEERING, cls.PRODUCTION]


class CreditType(Enum):
    """Types spécifiques de crédits musicaux"""
    # Artistes principaux
    MAIN_ARTIST = "main_artist"
    FEATURING = "featuring"
    COLLABORATOR = "collaborator"
    
    # Production
    PRODUCER = "producer"
    EXECUTIVE_PRODUCER = "executive_producer"
    CO_PRODUCER = "co_producer"
    ADDITIONAL_PRODUCER = "additional_producer"
    
    # Composition et écriture
    SONGWRITER = "songwriter"
    COMPOSER = "composer"
    LYRICIST = "lyricist"
    ARRANGER = "arranger"
    
    # Ingénierie audio
    MIXING_ENGINEER = "mixing_engineer"
    MASTERING_ENGINEER = "mastering_engineer"
    RECORDING_ENGINEER = "recording_engineer"
    ASSISTANT_ENGINEER = "assistant_engineer"
    
    # Musiciens et instruments
    DRUMS = "drums"
    BASS = "bass"
    GUITAR = "guitar"
    PIANO = "piano"
    KEYBOARD = "keyboard"
    VIOLIN = "violin"
    SAXOPHONE = "saxophone"
    TRUMPET = "trumpet"
    SYNTHESIZER = "synthesizer"
    PERCUSSION = "percussion"
    OTHER_INSTRUMENT = "other_instrument"
    
    # Voix
    LEAD_VOCALS = "lead_vocals"
    BACKING_VOCALS = "backing_vocals"
    HARMONY_VOCALS = "harmony_vocals"
    VOCAL_ARRANGEMENT = "vocal_arrangement"
    
    # Sampling et interpolation
    SAMPLE = "sample"
    INTERPOLATION = "interpolation"
    CONTAINS_SAMPLE = "contains_sample"
    
    # Autres rôles
    REMIXER = "remixer"
    DJ = "dj"
    SCRATCHES = "scratches"
    PROGRAMMING = "programming"
    SEQUENCING = "sequencing"
    
    # Visuel et design
    ARTWORK = "artwork"
    PHOTOGRAPHY = "photography"
    DESIGN = "design"
    
    # Business
    LABEL = "label"
    PUBLISHER = "publisher"
    MANAGER = "manager"
    
    # Générique
    UNKNOWN = "unknown"
    OTHER = "other"

    @classmethod
    @lru_cache(maxsize=1)
    def get_by_category(cls, category: CreditCategory) -> List['CreditType']:
        """Retourne les types de crédits par catégorie - avec cache"""
        mapping = {
            CreditCategory.ARTIST: [
                cls.MAIN_ARTIST, cls.FEATURING, cls.COLLABORATOR
            ],
            CreditCategory.PRODUCTION: [
                cls.PRODUCER, cls.EXECUTIVE_PRODUCER, cls.CO_PRODUCER, cls.ADDITIONAL_PRODUCER
            ],
            CreditCategory.ENGINEERING: [
                cls.MIXING_ENGINEER, cls.MASTERING_ENGINEER, cls.RECORDING_ENGINEER, cls.ASSISTANT_ENGINEER
            ],
            CreditCategory.MUSICIAN: [
                cls.DRUMS, cls.BASS, cls.GUITAR, cls.PIANO, cls.KEYBOARD,
                cls.VIOLIN, cls.SAXOPHONE, cls.TRUMPET, cls.SYNTHESIZER,
                cls.PERCUSSION, cls.OTHER_INSTRUMENT
            ],
            CreditCategory.VOCALS: [
                cls.LEAD_VOCALS, cls.BACKING_VOCALS, cls.HARMONY_VOCALS, cls.VOCAL_ARRANGEMENT
            ],
            CreditCategory.SONGWRITING: [
                cls.SONGWRITER, cls.COMPOSER, cls.LYRICIST, cls.ARRANGER
            ],
            CreditCategory.VISUAL: [
                cls.ARTWORK, cls.PHOTOGRAPHY, cls.DESIGN
            ],
            CreditCategory.BUSINESS: [
                cls.LABEL, cls.PUBLISHER, cls.MANAGER
            ],
            CreditCategory.OTHER: [
                cls.SAMPLE, cls.INTERPOLATION, cls.CONTAINS_SAMPLE,
                cls.REMIXER, cls.DJ, cls.SCRATCHES, cls.PROGRAMMING,
                cls.SEQUENCING, cls.OTHER
            ]
        }
        return mapping.get(category, [cls.UNKNOWN])
    
    @classmethod
    def get_category(cls, credit_type: 'CreditType') -> CreditCategory:
        """Retourne la catégorie d'un type de crédit"""
        for category in CreditCategory:
            if credit_type in cls.get_by_category(category):
                return category
        return CreditCategory.UNKNOWN
    
    @classmethod
    def from_string(cls, value: str) -> 'CreditType':
        """Convertit une chaîne en CreditType avec normalisation"""
        if not value:
            return cls.UNKNOWN
        
        value_normalized = value.lower().strip().replace(' ', '_').replace('-', '_')
        
        # Correspondances directes
        for item in cls:
            if item.value == value_normalized:
                return item
        
        # Correspondances partielles
        partial_matches = {
            'prod': cls.PRODUCER,
            'mix': cls.MIXING_ENGINEER,
            'master': cls.MASTERING_ENGINEER,
            'feat': cls.FEATURING,
            'vocal': cls.LEAD_VOCALS,
            'guitar': cls.GUITAR,
            'drum': cls.DRUMS,
            'bass': cls.BASS,
            'piano': cls.PIANO,
            'keyboard': cls.KEYBOARD
        }
        
        for key, credit_type in partial_matches.items():
            if key in value_normalized:
                return credit_type
        
        return cls.UNKNOWN


class SessionStatus(IntEnum):
    """Statuts d'une session d'extraction (IntEnum pour comparaison)"""
    PENDING = 0      # En attente
    IN_PROGRESS = 1  # En cours
    PAUSED = 2       # En pause
    COMPLETED = 3    # Terminée avec succès
    FAILED = 4       # Échec
    CANCELLED = 5    # Annulée

    @property
    def is_active(self) -> bool:
        """Vérifie si le statut indique une session active"""
        return self in [self.IN_PROGRESS, self.PAUSED]
    
    @property
    def is_final(self) -> bool:
        """Vérifie si le statut est final (pas de changement possible)"""
        return self in [self.COMPLETED, self.FAILED, self.CANCELLED]
    
    @classmethod
    @lru_cache(maxsize=1)
    def get_active_statuses(cls) -> List['SessionStatus']:
        """Retourne les statuts actifs - avec cache"""
        return [cls.IN_PROGRESS, cls.PAUSED]
    
    @classmethod
    @lru_cache(maxsize=1)
    def get_final_statuses(cls) -> List['SessionStatus']:
        """Retourne les statuts finaux - avec cache"""
        return [cls.COMPLETED, cls.FAILED, cls.CANCELLED]


class ExtractionStatus(IntEnum):
    """Statuts d'extraction pour les entités"""
    PENDING = 0      # En attente
    IN_PROGRESS = 1  # En cours
    COMPLETED = 2    # Terminé
    FAILED = 3       # Échec
    SKIPPED = 4      # Ignoré
    RETRY = 5        # À réessayer

    @property
    def is_final(self) -> bool:
        """Vérifie si le statut est final"""
        return self in [self.COMPLETED, self.FAILED, self.SKIPPED]
    
    @property
    def needs_processing(self) -> bool:
        """Vérifie si l'entité nécessite un traitement"""
        return self in [self.PENDING, self.RETRY]


class DataSource(Enum):
    """Sources de données"""
    GENIUS = "genius"
    SPOTIFY = "spotify"
    DISCOGS = "discogs"
    LASTFM = "lastfm"
    RAPEDIA = "rapedia"
    MANUAL = "manual"
    CACHE = "cache"
    DATABASE = "database"
    API = "api"
    WEB_SCRAPING = "web_scraping"
    UNKNOWN = "unknown"

    @property
    def is_api_source(self) -> bool:
        """Vérifie si c'est une source API"""
        return self in [self.GENIUS, self.SPOTIFY, self.DISCOGS, self.LASTFM]
    
    @property
    def is_scraping_source(self) -> bool:
        """Vérifie si c'est une source de scraping"""
        return self in [self.RAPEDIA, self.WEB_SCRAPING]
    
    @classmethod
    @lru_cache(maxsize=1)
    def get_external_sources(cls) -> List['DataSource']:
        """Retourne les sources externes - avec cache"""
        return [cls.GENIUS, cls.SPOTIFY, cls.DISCOGS, cls.LASTFM, cls.RAPEDIA]
    
    @classmethod
    @lru_cache(maxsize=1)
    def get_internal_sources(cls) -> List['DataSource']:
        """Retourne les sources internes - avec cache"""
        return [cls.CACHE, cls.DATABASE, cls.MANUAL]


class Genre(Enum):
    """Genres musicaux (focus rap/hip-hop mais extensible)"""
    # Hip-Hop et Rap
    HIP_HOP = "hip_hop"
    RAP = "rap"
    TRAP = "trap"
    DRILL = "drill"
    GRIME = "grime"
    BOOM_BAP = "boom_bap"
    MUMBLE_RAP = "mumble_rap"
    CONSCIOUS_RAP = "conscious_rap"
    GANGSTA_RAP = "gangsta_rap"
    CLOUD_RAP = "cloud_rap"
    
    # Genres connexes
    RNB = "rnb"
    SOUL = "soul"
    FUNK = "funk"
    JAZZ = "jazz"
    BLUES = "blues"
    
    # Électronique
    ELECTRONIC = "electronic"
    HOUSE = "house"
    TECHNO = "techno"
    DUBSTEP = "dubstep"
    
    # Autres
    POP = "pop"
    ROCK = "rock"
    REGGAE = "reggae"
    AFROBEAT = "afrobeat"
    LATIN = "latin"
    
    # Générique
    UNKNOWN = "unknown"
    OTHER = "other"

    @classmethod
    @lru_cache(maxsize=1)
    def get_hip_hop_genres(cls) -> List['Genre']:
        """Retourne les genres hip-hop - avec cache"""
        return [
            cls.HIP_HOP, cls.RAP, cls.TRAP, cls.DRILL, cls.GRIME,
            cls.BOOM_BAP, cls.MUMBLE_RAP, cls.CONSCIOUS_RAP,
            cls.GANGSTA_RAP, cls.CLOUD_RAP
        ]
    
    @property
    def is_hip_hop(self) -> bool:
        """Vérifie si c'est un genre hip-hop"""
        return self in self.get_hip_hop_genres()


class QualityLevel(IntEnum):
    """Niveaux de qualité des données (IntEnum pour comparaison)"""
    UNKNOWN = 0      # Qualité inconnue
    POOR = 1         # Données incomplètes/douteuses
    LOW = 2          # Données basiques
    MEDIUM = 3       # Données correctes
    HIGH = 4         # Données complètes et fiables
    EXCELLENT = 5    # Données parfaites

    @property
    def is_acceptable(self) -> bool:
        """Vérifie si la qualité est acceptable"""
        return self >= self.MEDIUM
    
    @property
    def is_high_quality(self) -> bool:
        """Vérifie si c'est une haute qualité"""
        return self >= self.HIGH
    
    @classmethod
    def from_score(cls, score: float) -> 'QualityLevel':
        """Convertit un score (0-100) en niveau de qualité"""
        if score >= 90:
            return cls.EXCELLENT
        elif score >= 75:
            return cls.HIGH
        elif score >= 60:
            return cls.MEDIUM
        elif score >= 40:
            return cls.LOW
        elif score >= 20:
            return cls.POOR
        else:
            return cls.UNKNOWN


class ExportFormat(Enum):
    """Formats d'export disponibles"""
    JSON = "json"
    CSV = "csv"
    EXCEL = "excel"
    XML = "xml"
    HTML = "html"
    YAML = "yaml"
    SQLITE = "sqlite"
    PDF = "pdf"

    @property
    def file_extension(self) -> str:
        """Retourne l'extension de fichier"""
        extensions = {
            self.JSON: '.json',
            self.CSV: '.csv',
            self.EXCEL: '.xlsx',
            self.XML: '.xml',
            self.HTML: '.html',
            self.YAML: '.yaml',
            self.SQLITE: '.db',
            self.PDF: '.pdf'
        }
        return extensions.get(self, '.txt')
    
    @property
    def mime_type(self) -> str:
        """Retourne le type MIME"""
        mime_types = {
            self.JSON: 'application/json',
            self.CSV: 'text/csv',
            self.EXCEL: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            self.XML: 'application/xml',
            self.HTML: 'text/html',
            self.YAML: 'application/yaml',
            self.SQLITE: 'application/x-sqlite3',
            self.PDF: 'application/pdf'
        }
        return mime_types.get(self, 'text/plain')
    
    @classmethod
    @lru_cache(maxsize=1)
    def get_structured_formats(cls) -> List['ExportFormat']:
        """Retourne les formats structurés - avec cache"""
        return [cls.JSON, cls.XML, cls.YAML]
    
    @classmethod
    @lru_cache(maxsize=1)
    def get_tabular_formats(cls) -> List['ExportFormat']:
        """Retourne les formats tabulaires - avec cache"""
        return [cls.CSV, cls.EXCEL, cls.SQLITE]


class ExtractorType(Enum):
    """Types d'extracteurs disponibles"""
    GENIUS = "genius"
    SPOTIFY = "spotify"
    DISCOGS = "discogs"
    LASTFM = "lastfm"
    RAPEDIA = "rapedia"
    CREDIT = "credit"
    LYRIC = "lyric"
    ALBUM = "album"
    METADATA = "metadata"

    @property
    def is_api_extractor(self) -> bool:
        """Vérifie si c'est un extracteur API"""
        return self in [self.GENIUS, self.SPOTIFY, self.DISCOGS, self.LASTFM]
    
    @property
    def is_scraping_extractor(self) -> bool:
        """Vérifie si c'est un extracteur de scraping"""
        return self in [self.RAPEDIA]


class DataQuality(IntEnum):
    """Qualité des données extraites (pour validation)"""
    INVALID = 0      # Données invalides
    SUSPICIOUS = 1   # Données suspectes
    BASIC = 2        # Données basiques valides
    GOOD = 3         # Bonnes données
    EXCELLENT = 4    # Données excellentes

    @property
    def is_valid(self) -> bool:
        """Vérifie si les données sont valides"""
        return self >= self.BASIC


# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_all_enum_values() -> Dict[str, List[str]]:
    """Retourne toutes les valeurs des enums - avec cache global"""
    return {
        'AlbumType': [item.value for item in AlbumType],
        'CreditCategory': [item.value for item in CreditCategory],
        'CreditType': [item.value for item in CreditType],
        'SessionStatus': [item.value for item in SessionStatus],
        'ExtractionStatus': [item.value for item in ExtractionStatus],
        'DataSource': [item.value for item in DataSource],
        'Genre': [item.value for item in Genre],
        'QualityLevel': [item.value for item in QualityLevel],
        'ExportFormat': [item.value for item in ExportFormat],
        'ExtractorType': [item.value for item in ExtractorType],
        'DataQuality': [item.value for item in DataQuality]
    }


def get_enum_by_name(enum_name: str) -> Optional[type]:
    """Retourne une classe enum par son nom"""
    enum_mapping = {
        'AlbumType': AlbumType,
        'CreditCategory': CreditCategory,
        'CreditType': CreditType,
        'SessionStatus': SessionStatus,
        'ExtractionStatus': ExtractionStatus,
        'DataSource': DataSource,
        'Genre': Genre,
        'QualityLevel': QualityLevel,
        'ExportFormat': ExportFormat,
        'ExtractorType': ExtractorType,
        'DataQuality': DataQuality
    }
    return enum_mapping.get(enum_name)