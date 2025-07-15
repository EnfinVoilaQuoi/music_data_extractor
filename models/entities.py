# models/entities.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import re
from urllib.parse import urlparse

# Import des enums avec imports absolus
from models.enums import (
    AlbumType, CreditCategory, CreditType, SessionStatus, 
    ExtractionStatus, DataSource, Genre, QualityLevel
)

@dataclass
class Artist:
    """Entité représentant un artiste"""
    id: Optional[int] = None
    name: str = ""
    normalized_name: Optional[str] = None
    
    # IDs externes
    genius_id: Optional[str] = None
    spotify_id: Optional[str] = None
    discogs_id: Optional[str] = None
    lastfm_name: Optional[str] = None
    
    # Métadonnées
    genre: Optional[Genre] = None
    country: Optional[str] = None
    active_years: Optional[str] = None
    description: Optional[str] = None
    
    # Statut extraction
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    total_tracks: int = 0
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialisation post-création"""
        if self.created_at is None:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
        
        # Générer le nom normalisé si pas fourni
        if not self.normalized_name and self.name:
            self.normalized_name = self._normalize_name(self.name)

    def _normalize_name(self, name: str) -> str:
        """Normalise le nom pour la recherche"""
        # Supprimer les caractères spéciaux, convertir en minuscules
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        # Remplacer les espaces multiples par un seul
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'name': self.name,
            'normalized_name': self.normalized_name,
            'genius_id': self.genius_id,
            'spotify_id': self.spotify_id,
            'discogs_id': self.discogs_id,
            'lastfm_name': self.lastfm_name,
            'genre': self.genre.value if self.genre else None,
            'country': self.country,
            'active_years': self.active_years,
            'description': self.description,
            'extraction_status': self.extraction_status.value,
            'total_tracks': self.total_tracks,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

@dataclass
class Album:
    """Entité représentant un album"""
    id: Optional[int] = None
    title: str = ""
    artist_id: Optional[int] = None
    artist_name: str = ""
    
    # Métadonnées de base
    album_type: AlbumType = AlbumType.ALBUM
    release_date: Optional[str] = None
    release_year: Optional[int] = None
    total_tracks: int = 0
    
    # IDs externes
    spotify_id: Optional[str] = None
    discogs_id: Optional[str] = None
    genius_id: Optional[str] = None
    
    # Métadonnées étendues
    label: Optional[str] = None
    genre: Optional[Genre] = None
    description: Optional[str] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialisation post-création"""
        if self.created_at is None:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'title': self.title,
            'artist_id': self.artist_id,
            'artist_name': self.artist_name,
            'album_type': self.album_type.value,
            'release_date': self.release_date,
            'release_year': self.release_year,
            'total_tracks': self.total_tracks,
            'spotify_id': self.spotify_id,
            'discogs_id': self.discogs_id,
            'genius_id': self.genius_id,
            'label': self.label,
            'genre': self.genre.value if self.genre else None,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

@dataclass
class Track:
    """Entité représentant un morceau"""
    id: Optional[int] = None
    title: str = ""
    artist_id: Optional[int] = None
    artist_name: str = ""
    album_id: Optional[int] = None
    album_name: Optional[str] = None
    
    # Métadonnées audio
    duration: Optional[int] = None  # en secondes
    bpm: Optional[int] = None
    key: Optional[str] = None
    
    # Métadonnées de sortie
    release_date: Optional[str] = None
    release_year: Optional[int] = None
    track_number: Optional[int] = None
    
    # IDs externes
    genius_id: Optional[str] = None
    spotify_id: Optional[str] = None
    discogs_id: Optional[str] = None
    
    # Contenu
    has_lyrics: bool = False
    lyrics: Optional[str] = None
    lyrics_snippet: Optional[str] = None
    
    # Statut et qualité
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    data_sources: List[DataSource] = field(default_factory=list)
    
    # Relations
    featuring_artists: List[str] = field(default_factory=list)
    credits: List['Credit'] = field(default_factory=list)
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    extraction_date: Optional[datetime] = None

    def __post_init__(self):
        """Initialisation post-création"""
        if self.created_at is None:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
        if self.extraction_date is None:
            self.extraction_date = datetime.now()

    def get_producers(self) -> List[str]:
        """Retourne la liste des producteurs"""
        return [
            credit.person_name for credit in self.credits 
            if credit.credit_type == CreditType.PRODUCER
        ]

    def get_unique_collaborators(self) -> List[str]:
        """Retourne la liste des collaborateurs uniques"""
        collaborators = set()
        for credit in self.credits:
            if credit.person_name:
                collaborators.add(credit.person_name)
        return list(collaborators)

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'title': self.title,
            'artist_id': self.artist_id,
            'artist_name': self.artist_name,
            'album_id': self.album_id,
            'album_name': self.album_name,
            'duration': self.duration,
            'bpm': self.bpm,
            'key': self.key,
            'release_date': self.release_date,
            'release_year': self.release_year,
            'track_number': self.track_number,
            'genius_id': self.genius_id,
            'spotify_id': self.spotify_id,
            'discogs_id': self.discogs_id,
            'has_lyrics': self.has_lyrics,
            'lyrics': self.lyrics,
            'lyrics_snippet': self.lyrics_snippet,
            'extraction_status': self.extraction_status.value,
            'data_sources': [source.value for source in self.data_sources],
            'featuring_artists': self.featuring_artists,
            'credits': [credit.to_dict() for credit in self.credits],
            'producers': self.get_producers(),
            'unique_collaborators': self.get_unique_collaborators(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'extraction_date': self.extraction_date.isoformat() if self.extraction_date else None
        }

@dataclass
class Credit:
    """Entité représentant un crédit sur un morceau"""
    id: Optional[int] = None
    track_id: Optional[int] = None
    credit_category: Optional[CreditCategory] = None
    credit_type: CreditType = CreditType.OTHER
    person_name: str = ""
    role_detail: Optional[str] = None
    instrument: Optional[str] = None
    
    # Flags
    is_primary: bool = False
    is_featuring: bool = False
    is_uncredited: bool = False
    
    # Source
    data_source: DataSource = DataSource.MANUAL
    extraction_date: Optional[datetime] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialisation post-création"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.extraction_date is None:
            self.extraction_date = datetime.now()
        
        # Auto-détection de la catégorie basée sur le type de crédit
        if self.credit_category is None:
            self.credit_category = self._detect_category()
        
        # Nettoyage du nom de la personne
        if self.person_name:
            self.person_name = self._clean_person_name(self.person_name)

    def _clean_person_name(self, name: str) -> str:
        """Nettoie le nom de la personne"""
        # Supprimer les préfixes courants
        name = re.sub(r'^(by |prod\.|produced by )', '', name.strip())
        # Supprimer les parenthèses vides
        name = re.sub(r'\(\s*\)', '', name)
        return name.strip()

    def _detect_category(self) -> CreditCategory:
        """Détecte automatiquement la catégorie de crédit"""
        type_to_category = {
            CreditType.PRODUCER: CreditCategory.PRODUCTION,
            CreditType.EXECUTIVE_PRODUCER: CreditCategory.PRODUCTION,
            CreditType.MIXING_ENGINEER: CreditCategory.TECHNICAL,
            CreditType.MASTERING_ENGINEER: CreditCategory.TECHNICAL,
            CreditType.RECORDING_ENGINEER: CreditCategory.TECHNICAL,
            CreditType.COMPOSER: CreditCategory.COMPOSITION,
            CreditType.SONGWRITER: CreditCategory.COMPOSITION,
            CreditType.LYRICIST: CreditCategory.COMPOSITION,
            CreditType.FEATURING: CreditCategory.PERFORMANCE,
            CreditType.VOCALIST: CreditCategory.PERFORMANCE,
            CreditType.RAPPER: CreditCategory.PERFORMANCE,
            CreditType.SAMPLE: CreditCategory.SAMPLE,
            CreditType.INTERPOLATION: CreditCategory.SAMPLE,
        }
        
        return type_to_category.get(self.credit_type, CreditCategory.TECHNICAL)

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'track_id': self.track_id,
            'credit_category': self.credit_category.value if self.credit_category else None,
            'credit_type': self.credit_type.value,
            'person_name': self.person_name,
            'role_detail': self.role_detail,
            'instrument': self.instrument,
            'is_primary': self.is_primary,
            'is_featuring': self.is_featuring,
            'is_uncredited': self.is_uncredited,
            'data_source': self.data_source.value,
            'extraction_date': self.extraction_date.isoformat() if self.extraction_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

@dataclass
class Session:
    """Entité représentant une session de travail"""
    id: str = ""
    artist_name: str = ""
    status: SessionStatus = SessionStatus.IN_PROGRESS
    current_step: Optional[str] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    
    # Configuration
    metadata: Dict[str, Any] = field(default_factory=dict)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    # Statistiques de progression
    total_tracks_found: int = 0
    tracks_processed: int = 0
    tracks_with_credits: int = 0
    tracks_with_albums: int = 0
    failed_tracks: int = 0
    
    # Métriques de performance
    processing_time_seconds: float = 0.0
    error_count: int = 0
    last_error: Optional[str] = None

    def __post_init__(self):
        """Initialisation post-création"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.start_time is None:
            self.start_time = datetime.now()
        self.updated_at = datetime.now()
        self.last_activity = datetime.now()

    def get_progress_percentage(self) -> float:
        """Calcule le pourcentage de progression"""
        if self.total_tracks_found == 0:
            return 0.0
        return (self.tracks_processed / self.total_tracks_found) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'artist_name': self.artist_name,
            'status': self.status.value,
            'current_step': self.current_step,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
            'metadata': self.metadata,
            'config_snapshot': self.config_snapshot,
            'total_tracks_found': self.total_tracks_found,
            'tracks_processed': self.tracks_processed,
            'tracks_with_credits': self.tracks_with_credits,
            'tracks_with_albums': self.tracks_with_albums,
            'failed_tracks': self.failed_tracks,
            'progress_percentage': self.get_progress_percentage(),
            'processing_time_seconds': self.processing_time_seconds,
            'error_count': self.error_count,
            'last_error': self.last_error
        }

@dataclass 
class QualityReport:
    """Rapport de qualité des données extraites"""
    id: Optional[int] = None
    track_id: Optional[int] = None
    artist_id: Optional[int] = None
    
    # Scores de qualité (0.0 à 1.0)
    overall_score: float = 0.0
    credits_completeness: float = 0.0
    metadata_accuracy: float = 0.0
    source_reliability: float = 0.0
    
    # Problèmes détectés
    missing_fields: List[str] = field(default_factory=list)
    suspicious_data: List[str] = field(default_factory=list) 
    inconsistencies: List[str] = field(default_factory=list)
    
    # Métadonnées
    created_at: Optional[datetime] = None
    quality_level: QualityLevel = QualityLevel.AVERAGE
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        
        # Calcul du niveau de qualité basé sur le score
        if self.overall_score >= 0.9:
            self.quality_level = QualityLevel.EXCELLENT
        elif self.overall_score >= 0.75:
            self.quality_level = QualityLevel.GOOD
        elif self.overall_score >= 0.5:
            self.quality_level = QualityLevel.AVERAGE
        elif self.overall_score >= 0.25:
            self.quality_level = QualityLevel.POOR
        else:
            self.quality_level = QualityLevel.VERY_POOR

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'track_id': self.track_id,
            'artist_id': self.artist_id,
            'overall_score': self.overall_score,
            'credits_completeness': self.credits_completeness,
            'metadata_accuracy': self.metadata_accuracy,
            'source_reliability': self.source_reliability,
            'missing_fields': self.missing_fields,
            'suspicious_data': self.suspicious_data,
            'inconsistencies': self.inconsistencies,
            'quality_level': self.quality_level.value,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

@dataclass
class ExtractionResult:
    """Résultat d'une extraction avec métadonnées"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    source: Optional[str] = None
    timestamp: Optional[datetime] = None
    cache_used: bool = False
    quality_score: float = 0.0
    
    # Statistiques d'extraction
    tracks_processed: int = 0
    credits_found: int = 0
    albums_resolved: int = 0
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'success': self.success,
            'data': self.data,
            'error': self.error,
            'source': self.source,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'cache_used': self.cache_used,
            'quality_score': self.quality_score,
            'tracks_processed': self.tracks_processed,
            'credits_found': self.credits_found,
            'albums_resolved': self.albums_resolved
        }