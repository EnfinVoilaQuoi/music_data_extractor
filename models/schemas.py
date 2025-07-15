# models/schemas.py
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum
import re

# Import avec imports absolus
from models.enums import Genre, ExtractionStatus, DataSource, CreditType, AlbumType


class BaseSchema(BaseModel):
    """Schéma de base avec configuration commune"""
    
    model_config = {
        # Permet l'utilisation d'enums
        "use_enum_values": True,
        # Validation stricte des types
        "validate_assignment": True,
        # Sérialisation des dates en ISO format
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }
    }


class ArtistSchema(BaseSchema):
    """Schéma de validation pour un artiste"""
    
    name: str = Field(..., min_length=1, max_length=200, description="Nom de l'artiste")
    normalized_name: Optional[str] = Field(None, description="Nom normalisé pour la recherche")
    genre: Optional[Genre] = Field(None, description="Genre principal")
    country: Optional[str] = Field(None, max_length=100, description="Pays d'origine")
    active_years: Optional[str] = Field(None, description="Années d'activité (ex: 2010-2024)")
    description: Optional[str] = Field(None, description="Description/biographie courte")
    
    # Sources d'information
    genius_id: Optional[str] = Field(None, description="ID Genius")
    spotify_id: Optional[str] = Field(None, description="ID Spotify")
    discogs_id: Optional[str] = Field(None, description="ID Discogs")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """Valide et nettoie le nom de l'artiste"""
        if not v or not v.strip():
            raise ValueError("Le nom ne peut pas être vide")
        return v.strip()


class AlbumSchema(BaseSchema):
    """Schéma de validation pour un album"""
    
    title: str = Field(..., min_length=1, max_length=300, description="Titre de l'album")
    artist_name: str = Field(..., description="Artiste principal")
    album_type: AlbumType = Field(default=AlbumType.ALBUM, description="Type d'album")
    
    # Informations de sortie
    release_date: Optional[date] = Field(None, description="Date de sortie")
    release_year: Optional[int] = Field(None, ge=1900, le=2030, description="Année de sortie")
    total_tracks: Optional[int] = Field(None, ge=1, le=200, description="Nombre total de tracks")
    
    # Sources d'information
    spotify_id: Optional[str] = Field(None, description="ID Spotify")
    discogs_id: Optional[str] = Field(None, description="ID Discogs")
    genius_id: Optional[str] = Field(None, description="ID Genius")
    
    # Métadonnées
    cover_url: Optional[str] = Field(None, description="URL de la pochette")
    label: Optional[str] = Field(None, max_length=200, description="Label/maison de disques")

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        """Valide et nettoie le titre"""
        if not v or not v.strip():
            raise ValueError("Le titre ne peut pas être vide")
        return v.strip()

    @model_validator(mode='after')
    def validate_dates(self):
        """Valide la cohérence des dates"""
        if self.release_date and self.release_year:
            if self.release_date.year != self.release_year:
                raise ValueError("L'année de release_date doit correspondre à release_year")
        elif self.release_date and not self.release_year:
            self.release_year = self.release_date.year
            
        return self


class TrackSchema(BaseSchema):
    """Schéma de validation pour une track"""
    
    title: str = Field(..., min_length=1, max_length=300, description="Titre de la track")
    artist_name: str = Field(..., description="Artiste principal")
    album_title: Optional[str] = Field(None, description="Titre de l'album")
    track_number: Optional[int] = Field(None, ge=1, description="Numéro de track dans l'album")
    
    # Informations techniques
    duration_seconds: Optional[int] = Field(None, ge=1, le=1800, description="Durée en secondes")
    bpm: Optional[int] = Field(None, ge=40, le=300, description="BPM")
    key: Optional[str] = Field(None, description="Tonalité musicale")
    
    # Informations de sortie
    release_date: Optional[date] = Field(None, description="Date de sortie")
    release_year: Optional[int] = Field(None, ge=1900, le=2030, description="Année de sortie")
    
    # Sources d'information
    genius_id: Optional[str] = Field(None, description="ID Genius")
    spotify_id: Optional[str] = Field(None, description="ID Spotify")
    lastfm_url: Optional[str] = Field(None, description="URL Last.fm")
    
    # Contenu
    lyrics: Optional[str] = Field(None, description="Paroles complètes")
    lyrics_snippet: Optional[str] = Field(None, max_length=500, description="Extrait des paroles")
    
    # Métadonnées d'extraction
    extraction_status: ExtractionStatus = Field(default=ExtractionStatus.PENDING)
    extraction_date: Optional[datetime] = Field(default_factory=datetime.now)
    data_sources: List[DataSource] = Field(default_factory=list, description="Sources des données")

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        """Valide et nettoie le titre"""
        if not v or not v.strip():
            raise ValueError("Le titre ne peut pas être vide")
        # Nettoyer les caractères spéciaux problématiques
        cleaned = re.sub(r'[^\w\s\-\.\(\)\[\]&,\'\"!?]', '', v.strip())
        return cleaned

    @field_validator('bpm')
    @classmethod
    def validate_bpm(cls, v):
        """Valide le BPM"""
        if v is not None and (v < 40 or v > 300):
            raise ValueError("BPM doit être entre 40 et 300")
        return v

    @field_validator('key')
    @classmethod
    def validate_key(cls, v):
        """Valide la tonalité musicale"""
        if v is not None:
            # Format accepté: C, C#, Db, etc. avec optionnellement 'major' ou 'minor'
            valid_pattern = re.compile(r'^[A-G][#b]?\s*(major|minor|maj|min)?$', re.IGNORECASE)
            if not valid_pattern.match(v.strip()):
                raise ValueError("Format de tonalité invalide")
            return v.strip()
        return v


class CreditSchema(BaseSchema):
    """Schéma de validation pour un crédit"""
    
    track_id: int = Field(..., description="ID de la track")
    person_name: str = Field(..., min_length=1, max_length=200, description="Nom de la personne")
    credit_type: CreditType = Field(..., description="Type de crédit")
    role_detail: Optional[str] = Field(None, max_length=200, description="Détail du rôle")
    instrument: Optional[str] = Field(None, max_length=100, description="Instrument joué")
    
    # Informations supplémentaires
    is_primary: bool = Field(default=False, description="Crédit principal pour ce type")
    is_featuring: bool = Field(default=False, description="Featuring/collaboration")
    is_uncredited: bool = Field(default=False, description="Crédit non officiel")
    
    # Source de l'information
    data_source: DataSource = Field(..., description="Source de ce crédit")
    extraction_date: datetime = Field(default_factory=datetime.now)

    @field_validator('person_name')
    @classmethod
    def validate_person_name(cls, v):
        """Valide et nettoie le nom de la personne"""
        if not v or not v.strip():
            raise ValueError("Le nom ne peut pas être vide")
        # Nettoyer et normaliser
        cleaned = v.strip()
        # Supprimer les préfixes/suffixes courants
        cleaned = re.sub(r'^(by |prod\.|produced\s*by )\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\(uncredited\)$', '', cleaned, flags=re.IGNORECASE)
        return cleaned

    @field_validator('instrument')
    @classmethod
    def validate_instrument(cls, v):
        """Valide l'instrument"""
        if v is not None:
            return v.strip().lower()
        return v


class QualityCheckSchema(BaseSchema):
    """Schéma pour les vérifications qualité"""
    
    track_id: int = Field(..., description="ID de la track")
    check_type: str = Field(..., description="Type de vérification")
    status: str = Field(..., description="Statut (PASS/FAIL/WARNING)")
    message: str = Field(..., description="Message descriptif")
    severity: str = Field(default="INFO", description="Sévérité (INFO/WARNING/ERROR)")
    
    check_date: datetime = Field(default_factory=datetime.now)

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        """Valide le statut"""
        valid_statuses = ['PASS', 'FAIL', 'WARNING']
        if v not in valid_statuses:
            raise ValueError(f"Statut doit être un de: {valid_statuses}")
        return v

    @field_validator('severity')
    @classmethod
    def validate_severity(cls, v):
        """Valide la sévérité"""
        valid_severities = ['INFO', 'WARNING', 'ERROR']
        if v not in valid_severities:
            raise ValueError(f"Sévérité doit être un de: {valid_severities}")
        return v


class ExtractionSessionSchema(BaseSchema):
    """Schéma pour une session d'extraction"""
    
    session_id: str = Field(..., description="ID unique de la session")
    artist_name: str = Field(..., description="Artiste en cours d'extraction")
    status: ExtractionStatus = Field(default=ExtractionStatus.IN_PROGRESS)
    
    # Statistiques
    total_tracks: int = Field(default=0, ge=0)
    completed_tracks: int = Field(default=0, ge=0)
    failed_tracks: int = Field(default=0, ge=0)
    
    # Temporisation
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = Field(None)
    last_activity: datetime = Field(default_factory=datetime.now)
    
    # Configuration utilisée
    config_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Config au moment de l'extraction")

    @model_validator(mode='after')
    def validate_progress(self):
        """Valide la cohérence des statistiques"""
        if self.completed_tracks + self.failed_tracks > self.total_tracks:
            raise ValueError("completed_tracks + failed_tracks ne peut pas dépasser total_tracks")
        return self


class ExportSchema(BaseSchema):
    """Schéma pour les exports de données"""
    
    export_id: str = Field(..., description="ID unique de l'export")
    artist_name: str = Field(..., description="Artiste exporté")
    format: str = Field(..., description="Format d'export (JSON/CSV/HTML)")
    
    # Filtres appliqués
    filters: Dict[str, Any] = Field(default_factory=dict, description="Filtres appliqués")
    include_lyrics: bool = Field(default=False, description="Inclure les paroles")
    include_credits: bool = Field(default=True, description="Inclure les crédits")
    
    # Métadonnées
    created_at: datetime = Field(default_factory=datetime.now)
    file_path: Optional[str] = Field(None, description="Chemin du fichier généré")
    file_size_bytes: Optional[int] = Field(None, ge=0, description="Taille du fichier")

    @field_validator('format')
    @classmethod
    def validate_format(cls, v):
        """Valide le format d'export"""
        valid_formats = ['JSON', 'CSV', 'HTML']
        if v.upper() not in valid_formats:
            raise ValueError(f"Format doit être un de: {valid_formats}")
        return v.upper()


class StatsSchema(BaseSchema):
    """Schéma pour les statistiques générales"""
    
    total_artists: int = Field(default=0, ge=0, description="Nombre total d'artistes")
    total_tracks: int = Field(default=0, ge=0, description="Nombre total de tracks")
    total_albums: int = Field(default=0, ge=0, description="Nombre total d'albums")
    total_credits: int = Field(default=0, ge=0, description="Nombre total de crédits")
    
    # Statistiques qualité
    tracks_with_lyrics: int = Field(default=0, ge=0, description="Tracks avec paroles")
    tracks_with_bpm: int = Field(default=0, ge=0, description="Tracks avec BPM")
    tracks_with_producer: int = Field(default=0, ge=0, description="Tracks avec producteur")
    
    # Métadonnées
    generated_at: datetime = Field(default_factory=datetime.now)
    scope: str = Field(default="global", description="Périmètre des stats")

    @model_validator(mode='after')
    def validate_consistency(self):
        """Valide la cohérence des statistiques"""
        if self.tracks_with_lyrics > self.total_tracks:
            raise ValueError("tracks_with_lyrics ne peut pas dépasser total_tracks")
        if self.tracks_with_bpm > self.total_tracks:
            raise ValueError("tracks_with_bpm ne peut pas dépasser total_tracks")
        if self.tracks_with_producer > self.total_tracks:
            raise ValueError("tracks_with_producer ne peut pas dépasser total_tracks")
        return self