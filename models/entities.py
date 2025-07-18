# models/entities.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import re
from urllib.parse import urlparse
from functools import lru_cache
import hashlib

# Import des enums avec imports absolus
from models.enums import (
    AlbumType, CreditCategory, CreditType, SessionStatus, 
    ExtractionStatus, DataSource, Genre, QualityLevel
)


@dataclass
class Artist:
    """Entité représentant un artiste avec optimisations"""
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
    extracted_tracks: int = 0
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Métadonnées d'extraction
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialisation post-création optimisée"""
        current_time = datetime.now()
        
        if self.created_at is None:
            self.created_at = current_time
        self.updated_at = current_time
        
        # Générer le nom normalisé si pas fourni
        if not self.normalized_name and self.name:
            self.normalized_name = self._normalize_name(self.name)
    
    @lru_cache(maxsize=128)
    def _normalize_name(self, name: str) -> str:
        """Normalise le nom pour la recherche - avec cache"""
        if not name:
            return ""
        
        # Supprimer les caractères spéciaux, convertir en minuscules
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        # Remplacer les espaces multiples par un seul
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    @property
    def extraction_progress(self) -> float:
        """Retourne le pourcentage d'extraction (0-100)"""
        if self.total_tracks == 0:
            return 0.0
        return min(100.0, (self.extracted_tracks / self.total_tracks) * 100)
    
    @property
    def is_extraction_complete(self) -> bool:
        """Vérifie si l'extraction est terminée"""
        return self.extraction_status == ExtractionStatus.COMPLETED
    
    def get_external_ids(self) -> Dict[str, str]:
        """Retourne tous les IDs externes disponibles"""
        return {
            'genius': self.genius_id,
            'spotify': self.spotify_id,
            'discogs': self.discogs_id,
            'lastfm': self.lastfm_name
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export - optimisé"""
        return {
            'id': self.id,
            'name': self.name,
            'normalized_name': self.normalized_name,
            'external_ids': self.get_external_ids(),
            'genre': self.genre.value if self.genre else None,
            'country': self.country,
            'active_years': self.active_years,
            'description': self.description,
            'extraction_status': self.extraction_status.value,
            'total_tracks': self.total_tracks,
            'extracted_tracks': self.extracted_tracks,
            'extraction_progress': self.extraction_progress,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata
        }


@dataclass
class Album:
    """Entité représentant un album avec optimisations"""
    id: Optional[int] = None
    title: str = ""
    normalized_title: Optional[str] = None
    artist_id: Optional[int] = None
    artist_name: Optional[str] = None
    
    # Métadonnées album
    album_type: AlbumType = AlbumType.ALBUM
    release_date: Optional[datetime] = None
    track_count: int = 0
    genre: Optional[Genre] = None
    
    # IDs externes
    spotify_id: Optional[str] = None
    discogs_id: Optional[str] = None
    genius_id: Optional[str] = None
    
    # Informations complémentaires
    label: Optional[str] = None
    catalog_number: Optional[str] = None
    cover_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Métadonnées
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialisation post-création"""
        current_time = datetime.now()
        
        if self.created_at is None:
            self.created_at = current_time
        self.updated_at = current_time
        
        # Générer le titre normalisé
        if not self.normalized_title and self.title:
            self.normalized_title = self._normalize_title(self.title)
    
    @lru_cache(maxsize=128)
    def _normalize_title(self, title: str) -> str:
        """Normalise le titre pour la recherche"""
        if not title:
            return ""
        
        normalized = re.sub(r'[^\w\s]', '', title.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    @property
    def duration_formatted(self) -> str:
        """Retourne la durée formatée (MM:SS ou HH:MM:SS)"""
        if not self.duration_seconds:
            return "00:00"
        
        hours, remainder = divmod(self.duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    @property
    def is_single(self) -> bool:
        """Vérifie si c'est un single (1-3 morceaux)"""
        return self.album_type == AlbumType.SINGLE or self.track_count <= 3
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'title': self.title,
            'normalized_title': self.normalized_title,
            'artist_id': self.artist_id,
            'artist_name': self.artist_name,
            'album_type': self.album_type.value,
            'release_date': self.release_date.isoformat() if self.release_date else None,
            'track_count': self.track_count,
            'genre': self.genre.value if self.genre else None,
            'external_ids': {
                'spotify': self.spotify_id,
                'discogs': self.discogs_id,
                'genius': self.genius_id
            },
            'label': self.label,
            'catalog_number': self.catalog_number,
            'cover_url': self.cover_url,
            'duration_seconds': self.duration_seconds,
            'duration_formatted': self.duration_formatted,
            'is_single': self.is_single,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata
        }


@dataclass
class Track:
    """Entité représentant un morceau avec optimisations"""
    id: Optional[int] = None
    title: str = ""
    normalized_title: Optional[str] = None
    artist_id: Optional[int] = None
    artist_name: Optional[str] = None
    album_id: Optional[int] = None
    album_name: Optional[str] = None
    
    # Métadonnées musicales
    duration_seconds: Optional[int] = None
    bpm: Optional[float] = None
    key_signature: Optional[str] = None
    time_signature: Optional[str] = None
    
    # Informations album
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    
    # IDs externes
    genius_id: Optional[str] = None
    spotify_id: Optional[str] = None
    discogs_id: Optional[str] = None
    
    # Contenu
    lyrics: Optional[str] = None
    has_lyrics: bool = False
    is_instrumental: bool = False
    
    # Qualité des données
    quality_score: float = 0.0
    quality_level: QualityLevel = QualityLevel.UNKNOWN
    
    # URLs
    genius_url: Optional[str] = None
    spotify_url: Optional[str] = None
    youtube_url: Optional[str] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Métadonnées d'extraction
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    source: DataSource = DataSource.UNKNOWN
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialisation post-création"""
        current_time = datetime.now()
        
        if self.created_at is None:
            self.created_at = current_time
        self.updated_at = current_time
        
        # Générer le titre normalisé
        if not self.normalized_title and self.title:
            self.normalized_title = self._normalize_title(self.title)
        
        # Mise à jour automatique has_lyrics
        self.has_lyrics = bool(self.lyrics and self.lyrics.strip())
    
    @lru_cache(maxsize=256)
    def _normalize_title(self, title: str) -> str:
        """Normalise le titre pour la recherche"""
        if not title:
            return ""
        
        # Supprimer les éléments entre parenthèses/crochets (feat, remix, etc.)
        normalized = re.sub(r'\s*[\(\[][^)\]]*[\)\]]\s*', ' ', title)
        # Supprimer les caractères spéciaux
        normalized = re.sub(r'[^\w\s]', '', normalized.lower())
        # Nettoyer les espaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    @property
    def duration_formatted(self) -> str:
        """Retourne la durée formatée (MM:SS)"""
        if not self.duration_seconds:
            return "00:00"
        
        minutes, seconds = divmod(self.duration_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    @property
    def is_complete(self) -> bool:
        """Vérifie si le morceau a toutes les données essentielles"""
        return all([
            self.title,
            self.artist_name,
            self.duration_seconds is not None,
            self.extraction_status == ExtractionStatus.COMPLETED
        ])
    
    @property
    def unique_identifier(self) -> str:
        """Génère un identifiant unique pour éviter les doublons"""
        text = f"{self.artist_name}|{self.title}|{self.album_name or ''}"
        return hashlib.md5(text.encode()).hexdigest()
    
    def get_external_urls(self) -> Dict[str, str]:
        """Retourne toutes les URLs externes disponibles"""
        return {
            'genius': self.genius_url,
            'spotify': self.spotify_url,
            'youtube': self.youtube_url
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'title': self.title,
            'normalized_title': self.normalized_title,
            'artist_id': self.artist_id,
            'artist_name': self.artist_name,
            'album_id': self.album_id,
            'album_name': self.album_name,
            'duration_seconds': self.duration_seconds,
            'duration_formatted': self.duration_formatted,
            'bpm': self.bpm,
            'key_signature': self.key_signature,
            'time_signature': self.time_signature,
            'track_number': self.track_number,
            'disc_number': self.disc_number,
            'external_ids': {
                'genius': self.genius_id,
                'spotify': self.spotify_id,
                'discogs': self.discogs_id
            },
            'external_urls': self.get_external_urls(),
            'lyrics': self.lyrics,
            'has_lyrics': self.has_lyrics,
            'is_instrumental': self.is_instrumental,
            'quality_score': self.quality_score,
            'quality_level': self.quality_level.value,
            'extraction_status': self.extraction_status.value,
            'source': self.source.value,
            'is_complete': self.is_complete,
            'unique_identifier': self.unique_identifier,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata
        }


@dataclass
class Credit:
    """Entité représentant un crédit musical avec optimisations"""
    id: Optional[int] = None
    track_id: Optional[int] = None
    person_name: str = ""
    normalized_name: Optional[str] = None
    
    # Type et catégorie de crédit
    credit_type: CreditType = CreditType.UNKNOWN
    credit_category: CreditCategory = CreditCategory.UNKNOWN
    
    # Détails du rôle
    role_detail: Optional[str] = None
    instrument: Optional[str] = None
    is_primary: bool = False
    is_featuring: bool = False
    
    # Métadonnées
    source: DataSource = DataSource.UNKNOWN
    confidence_score: float = 0.0
    raw_data: Optional[str] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialisation post-création"""
        current_time = datetime.now()
        
        if self.created_at is None:
            self.created_at = current_time
        self.updated_at = current_time
        
        # Générer le nom normalisé
        if not self.normalized_name and self.person_name:
            self.normalized_name = self._normalize_name(self.person_name)
    
    @lru_cache(maxsize=256)
    def _normalize_name(self, name: str) -> str:
        """Normalise le nom de la personne"""
        if not name:
            return ""
        
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    @property
    def is_high_confidence(self) -> bool:
        """Vérifie si le crédit a un score de confiance élevé"""
        return self.confidence_score >= 0.8
    
    @property
    def display_name(self) -> str:
        """Nom d'affichage avec détails du rôle"""
        base_name = self.person_name
        
        if self.role_detail:
            base_name += f" ({self.role_detail})"
        elif self.instrument:
            base_name += f" ({self.instrument})"
        
        if self.is_featuring:
            base_name += " [feat.]"
        
        return base_name
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'track_id': self.track_id,
            'person_name': self.person_name,
            'normalized_name': self.normalized_name,
            'credit_type': self.credit_type.value,
            'credit_category': self.credit_category.value,
            'role_detail': self.role_detail,
            'instrument': self.instrument,
            'is_primary': self.is_primary,
            'is_featuring': self.is_featuring,
            'source': self.source.value,
            'confidence_score': self.confidence_score,
            'is_high_confidence': self.is_high_confidence,
            'display_name': self.display_name,
            'raw_data': self.raw_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


@dataclass
class Session:
    """Entité représentant une session d'extraction avec optimisations"""
    id: Optional[str] = None
    artist_name: str = ""
    status: SessionStatus = SessionStatus.PENDING
    
    # Configuration de la session
    max_tracks: Optional[int] = None
    current_track_index: int = 0
    total_tracks_found: int = 0
    
    # Progression
    tracks_processed: int = 0
    tracks_successful: int = 0
    tracks_failed: int = 0
    credits_extracted: int = 0
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Erreurs et logs
    last_error: Optional[str] = None
    error_count: int = 0
    
    # Métadonnées
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialisation post-création"""
        current_time = datetime.now()
        
        if self.created_at is None:
            self.created_at = current_time
        self.updated_at = current_time
        
        # Générer un ID unique si pas fourni
        if not self.id:
            timestamp = current_time.strftime("%Y%m%d_%H%M%S")
            artist_normalized = re.sub(r'[^\w]', '_', self.artist_name.lower())[:20]
            self.id = f"{artist_normalized}_{timestamp}"
    
    @property
    def progress_percentage(self) -> float:
        """Retourne le pourcentage de progression (0-100)"""
        if self.total_tracks_found == 0:
            return 0.0
        return min(100.0, (self.tracks_processed / self.total_tracks_found) * 100)
    
    @property
    def success_rate(self) -> float:
        """Retourne le taux de succès (0-100)"""
        if self.tracks_processed == 0:
            return 0.0
        return (self.tracks_successful / self.tracks_processed) * 100
    
    @property
    def duration_seconds(self) -> Optional[int]:
        """Retourne la durée de la session en secondes"""
        if not self.started_at:
            return None
        
        end_time = self.completed_at or datetime.now()
        return int((end_time - self.started_at).total_seconds())
    
    @property
    def duration_formatted(self) -> str:
        """Retourne la durée formatée"""
        duration = self.duration_seconds
        if duration is None:
            return "00:00:00"
        
        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    @property
    def is_active(self) -> bool:
        """Vérifie si la session est active"""
        return self.status in [SessionStatus.IN_PROGRESS, SessionStatus.PAUSED]
    
    @property
    def is_complete(self) -> bool:
        """Vérifie si la session est terminée"""
        return self.status in [SessionStatus.COMPLETED, SessionStatus.FAILED]
    
    def update_progress(self, tracks_processed: int = None, tracks_successful: int = None, 
                       tracks_failed: int = None, credits_extracted: int = None):
        """Met à jour la progression de la session"""
        if tracks_processed is not None:
            self.tracks_processed = tracks_processed
        if tracks_successful is not None:
            self.tracks_successful = tracks_successful
        if tracks_failed is not None:
            self.tracks_failed = tracks_failed
        if credits_extracted is not None:
            self.credits_extracted = credits_extracted
        
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'artist_name': self.artist_name,
            'status': self.status.value,
            'max_tracks': self.max_tracks,
            'current_track_index': self.current_track_index,
            'total_tracks_found': self.total_tracks_found,
            'tracks_processed': self.tracks_processed,
            'tracks_successful': self.tracks_successful,
            'tracks_failed': self.tracks_failed,
            'credits_extracted': self.credits_extracted,
            'progress_percentage': self.progress_percentage,
            'success_rate': self.success_rate,
            'duration_seconds': self.duration_seconds,
            'duration_formatted': self.duration_formatted,
            'is_active': self.is_active,
            'is_complete': self.is_complete,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'last_error': self.last_error,
            'error_count': self.error_count,
            'metadata': self.metadata
        }


@dataclass
class QualityReport:
    """Rapport de qualité pour les données extraites"""
    entity_type: str
    entity_id: Optional[int] = None
    quality_level: QualityLevel = QualityLevel.UNKNOWN
    quality_score: float = 0.0
    
    # Détails de la qualité
    missing_fields: List[str] = field(default_factory=list)
    suspicious_data: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    # Métadonnées
    checked_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.checked_at is None:
            self.checked_at = datetime.now()
    
    @property
    def is_high_quality(self) -> bool:
        """Vérifie si la qualité est élevée"""
        return self.quality_level in [QualityLevel.HIGH, QualityLevel.EXCELLENT]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'quality_level': self.quality_level.value,
            'quality_score': self.quality_score,
            'is_high_quality': self.is_high_quality,
            'missing_fields': self.missing_fields,
            'suspicious_data': self.suspicious_data,
            'recommendations': self.recommendations,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None,
            'metadata': self.metadata
        }


@dataclass
class ExtractionResult:
    """Résultat d'une extraction avec métadonnées complètes"""
    success: bool
    entity_type: str
    entity_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    source: DataSource = DataSource.UNKNOWN
    timestamp: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    cache_used: bool = False
    quality_score: float = 0.0
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    @property
    def is_successful(self) -> bool:
        """Vérifie si l'extraction a réussi"""
        return self.success and self.data is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            'success': self.success,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'is_successful': self.is_successful,
            'data': self.data,
            'error': self.error,
            'source': self.source.value,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'duration_seconds': self.duration_seconds,
            'cache_used': self.cache_used,
            'quality_score': self.quality_score
        }