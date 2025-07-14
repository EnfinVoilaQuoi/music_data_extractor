# models/enums.py
from enum import Enum

class AlbumType(Enum):
    """Types d'albums supportés"""
    ALBUM = "album"
    EP = "ep" 
    SINGLE = "single"
    COMPILATION = "compilation"
    MIXTAPE = "mixtape"
    LIVE = "live"

class CreditCategory(Enum):
    """Catégories de crédits musicaux"""
    PRODUCER = "producer"
    INSTRUMENT = "instrument"
    VOCAL = "vocal"
    TECHNICAL = "technical"
    FEATURING = "featuring"
    COMPOSER = "composer"
    SAMPLE = "sample"
    OTHER = "other"

class CreditType(Enum):
    """Types spécifiques de crédits"""
    # Production
    PRODUCER = "producer"
    EXECUTIVE_PRODUCER = "executive_producer"
    CO_PRODUCER = "co_producer"
    ADDITIONAL_PRODUCTION = "additional_production"
    VOCAL_PRODUCER = "vocal_producer"
    
    # Instruments
    GUITAR = "guitar"
    BASS = "bass"
    DRUMS = "drums"
    PIANO = "piano"
    KEYBOARD = "keyboard"
    SAXOPHONE = "saxophone"
    TRUMPET = "trumpet"
    VIOLIN = "violin"
    STRINGS = "strings"
    BRASS = "brass"
    
    # Technique
    MIXING = "mixing"
    MASTERING = "mastering"
    RECORDING = "recording"
    ENGINEERING = "engineering"
    
    # Vocal
    LEAD_VOCALS = "lead_vocals"
    BACKING_VOCALS = "backing_vocals"
    RAP = "rap"
    HOOK = "hook"
    CHORUS = "chorus"
    FEATURING = "featuring"
    AD_LIBS = "ad_libs"
    
    # Composition
    SONGWRITER = "songwriter"
    COMPOSER = "composer"
    LYRICIST = "lyricist"
    
    # Hip-hop spécifique
    DJ = "dj"
    SCRATCH = "scratch"
    TURNTABLES = "turntables"
    
    # Autre
    SAMPLE = "sample"
    INTERPOLATION = "interpolation"
    OTHER = "other"

class SessionStatus(Enum):
    """Statuts des sessions d'extraction"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"

class ExtractionStatus(Enum):
    """Statuts d'extraction pour les entités"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"

class DataSource(Enum):
    """Sources de données supportées"""
    GENIUS = "genius"
    GENIUS_API = "genius_api"
    GENIUS_WEB = "genius_web"
    SPOTIFY = "spotify"
    DISCOGS = "discogs"
    LASTFM = "lastfm"
    SONGBPM = "songbpm"
    TUNEBAT = "tunebat"
    RAPEDIA = "rapedia"
    WEB_SCRAPING = "web_scraping"
    MANUAL = "manual"

class ExtractorType(Enum):
    """Types d'extracteurs disponibles"""
    GENIUS = "genius"
    SPOTIFY = "spotify"
    DISCOGS = "discogs"
    LASTFM = "lastfm"
    SONGBPM = "songbpm"
    TUNEBAT = "tunebat"
    RAPEDIA = "rapedia"
    CREDIT_EXTRACTOR = "credit_extractor"

class Genre(Enum):
    """Genres musicaux supportés (focus rap/hip-hop)"""
    RAP = "rap"
    HIP_HOP = "hip_hop"
    TRAP = "trap"
    DRILL = "drill"
    BOOM_BAP = "boom_bap"
    CLOUD_RAP = "cloud_rap"
    GANGSTA_RAP = "gangsta_rap"
    CONSCIOUS_RAP = "conscious_rap"
    FRENCH_RAP = "french_rap"
    JAZZ_RAP = "jazz_rap"
    EXPERIMENTAL_HIP_HOP = "experimental_hip_hop"
    AFRO_TRAP = "afro_trap"
    DRILL_FR = "drill_fr"
    OTHER = "other"

class QualityLevel(Enum):
    """Niveaux de qualité des données"""
    EXCELLENT = "excellent"     # 90-100%
    GOOD = "good"              # 75-89%
    AVERAGE = "average"        # 50-74%
    POOR = "poor"             # 25-49%
    VERY_POOR = "very_poor"   # 0-24%

class ExportFormat(Enum):
    """Formats d'export supportés"""
    JSON = "json"
    CSV = "csv"
    EXCEL = "excel"
    HTML = "html"
    XML = "xml"
    PDF = "pdf"

class DataQuality(Enum):
    """Niveaux de qualité des données extraites"""
    VERIFIED = "verified"      # Données vérifiées manuellement
    HIGH = "high"             # Confiance élevée (source primaire)
    MEDIUM = "medium"         # Confiance moyenne (source secondaire)
    LOW = "low"              # Confiance faible (scraping/estimation)
    UNKNOWN = "unknown"       # Qualité inconnue

class ProcessingStep(Enum):
    """Étapes du pipeline de traitement"""
    DISCOVERY = "discovery"
    EXTRACTION = "extraction"
    CLEANING = "cleaning"
    VALIDATION = "validation"
    ENRICHMENT = "enrichment"
    DEDUPLICATION = "deduplication"
    EXPORT = "export"
    COMPLETED = "completed"

class ScraperType(Enum):
    """Types de scrapers web"""
    SELENIUM = "selenium"
    REQUESTS = "requests"
    BEAUTIFULSOUP = "beautifulsoup"
    API = "api"