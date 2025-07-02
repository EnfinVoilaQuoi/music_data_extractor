# models/schemas.py
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, validator, root_validator
from enum import Enum
import re

from .enums import Genre, ExtractionStatus, DataSource, CreditType, AlbumType


class BaseSchema(BaseModel):
    """Schéma de base avec configuration commune"""
    
    class Config:
        # Permet l'utilisation d'enums
        use_enum_values = True
        # Validation stricte des types
        validate_assignment = True
        # Sérialisation des dates en ISO format
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
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
    lastfm_name: Optional[str] = Field(None, description="Nom Last.fm")
    
    # Métadonnées
    extraction_status: ExtractionStatus = Field(default=ExtractionStatus.PENDING)
    last_updated: Optional[datetime] = Field(default_factory=datetime.now)
    total_tracks: int = Field(default=0, ge=0, description="Nombre total de tracks")
    
    @validator('name')
    def validate_name(cls, v):
        """Valide et nettoie le nom de l'artiste"""
        if not v or not v.strip():
            raise ValueError("Le nom de l'artiste ne peut pas être vide")
        return v.strip()
    
    @validator('active_years')
    def validate_active_years(cls, v):
        """Valide le format des années d'activité"""
        if v and not re.match(r'^\d{4}(-\d{4})?$', v):
            raise ValueError("Format années d'activité invalide (ex: 2010 ou 2010-2024)")
        return v


class AlbumSchema(BaseSchema):
    """Schéma de validation pour un album"""
    
    title: str = Field(..., min_length=1, max_length=300, description="Titre de l'album")
    artist_name: str = Field(..., description="Nom de l'artiste principal")
    album_type: AlbumType = Field(default=AlbumType.ALBUM)
    release_date: Optional[date] = Field(None, description="Date de sortie")
    release_year: Optional[int] = Field(None, ge=1900, le=2030, description="Année de sortie")
    
    # Informations techniques
    total_tracks: int = Field(default=0, ge=0, description="Nombre de tracks")
    duration_seconds: Optional[int] = Field(None, ge=0, description="Durée totale en secondes")
    
    # Sources d'information
    spotify_id: Optional[str] = Field(None, description="ID Spotify")
    discogs_id: Optional[str] = Field(None, description="ID Discogs")
    genius_id: Optional[str] = Field(None, description="ID Genius")
    
    # Métadonnées
    cover_url: Optional[str] = Field(None, description="URL de la pochette")
    label: Optional[str] = Field(None, max_length=200, description="Label/maison de disques")
    
    @validator('title')
    def validate_title(cls, v):
        """Valide et nettoie le titre"""
        if not v or not v.strip():
            raise ValueError("Le titre ne peut pas être vide")
        return v.strip()
    
    @root_validator
    def validate_dates(cls, values):
        """Valide la cohérence des dates"""
        release_date = values.get('release_date')
        release_year = values.get('release_year')
        
        if release_date and release_year:
            if release_date.year != release_year:
                raise ValueError("L'année de release_date doit correspondre à release_year")
        elif release_date and not release_year:
            values['release_year'] = release_date.year
            
        return values


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
    
    @validator('title')
    def validate_title(cls, v):
        """Valide et nettoie le titre"""
        if not v or not v.strip():
            raise ValueError("Le titre ne peut pas être vide")
        # Nettoyer les caractères spéciaux problématiques
        cleaned = re.sub(r'[^\w\s\-\.\(\)\[\]&,\'\"!?]', '', v.strip())
        return cleaned
    
    @validator('bpm')
    def validate_bpm(cls, v):
        """Valide le BPM"""
        if v is not None and (v < 40 or v > 300):
            raise ValueError("BPM doit être entre 40 et 300")
        return v
    
    @validator('key')
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
    
    @validator('person_name')
    def validate_person_name(cls, v):
        """Valide et nettoie le nom de la personne"""
        if not v or not v.strip():
            raise ValueError("Le nom ne peut pas être vide")
        # Nettoyer et normaliser
        cleaned = v.strip()
        # Supprimer les préfixes/suffixes courants
        cleaned = re.sub(r'^(by |prod\.?\s*by |produced\s*by )\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*\(uncredited\)$', '', cleaned, flags=re.IGNORECASE)
        return cleaned
    
    @validator('instrument')
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
    
    @validator('status')
    def validate_status(cls, v):
        """Valide le statut"""
        valid_statuses = ['PASS', 'FAIL', 'WARNING']
        if v not in valid_statuses:
            raise ValueError(f"Statut doit être un de: {valid_statuses}")
        return v
    
    @validator('severity')
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
    
    @root_validator
    def validate_progress(cls, values):
        """Valide la cohérence des statistiques"""
        total = values.get('total_tracks', 0)
        completed = values.get('completed_tracks', 0)
        failed = values.get('failed_tracks', 0)
        
        if completed + failed > total:
            raise ValueError("completed_tracks + failed_tracks ne peut pas dépasser total_tracks")
        
        return values


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
    
    @validator('format')
    def validate_format(cls, v):
        """Valide le format d'export"""
        valid_formats = ['JSON', 'CSV', 'HTML']
        if v.upper() not in valid_formats:
            raise ValueError(f"Format doit être un de: {valid_formats}")
        return v.upper()


# Schémas pour les réponses API
class TrackWithCreditsSchema(TrackSchema):
    """Track avec ses crédits inclus"""
    credits: List[CreditSchema] = Field(default_factory=list)
    quality_checks: List[QualityCheckSchema] = Field(default_factory=list)


class ArtistCompleteSchema(ArtistSchema):
    """Artiste avec toutes ses données"""
    albums: List[AlbumSchema] = Field(default_factory=list)
    tracks: List[TrackWithCreditsSchema] = Field(default_factory=list)
    total_credits: int = Field(default=0, description="Nombre total de crédits")
    extraction_sessions: List[ExtractionSessionSchema] = Field(default_factory=list)


class StatsSchema(BaseSchema):
    """Schéma pour les statistiques d'un artiste"""
    
    artist_name: str = Field(..., description="Nom de l'artiste")
    
    # Statistiques générales
    total_tracks: int = Field(default=0, ge=0)
    total_albums: int = Field(default=0, ge=0)
    total_credits: int = Field(default=0, ge=0)
    unique_collaborators: int = Field(default=0, ge=0)
    
    # Statistiques temporelles
    career_span_years: Optional[int] = Field(None, ge=0)
    first_release_year: Optional[int] = Field(None)
    last_release_year: Optional[int] = Field(None)
    tracks_per_year: Dict[str, int] = Field(default_factory=dict)
    
    # Statistiques par genre de crédit
    credits_by_type: Dict[str, int] = Field(default_factory=dict)
    top_producers: List[Dict[str, Union[str, int]]] = Field(default_factory=list)
    top_collaborators: List[Dict[str, Union[str, int]]] = Field(default_factory=list)
    
    # Statistiques techniques
    average_bpm: Optional[float] = Field(None, ge=0)
    average_duration: Optional[float] = Field(None, ge=0)
    most_common_key: Optional[str] = Field(None)
    
    # Métadonnées
    generated_at: datetime = Field(default_factory=datetime.now)
    data_completeness: float = Field(default=0.0, ge=0.0, le=1.0, description="Complétude des données (0-1)")
