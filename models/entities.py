# models/entities.py - Version corrigée
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import re
from urllib.parse import urlparse

# Import des enums - CORRECTION MAJEURE
from .enums import (
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
        
        # Validation des IDs externes
        self._validate_external_ids()

    def _normalize_name(self, name: str) -> str:
        """Normalise le nom pour la recherche"""
        # Supprimer les caractères spéciaux, convertir en minuscules
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        # Remplacer les espaces multiples par un seul
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _validate_external_ids(self):
        """Valide les IDs externes"""
        # Validation Spotify ID (format: 22 caractères alphanumériques)
        if self.spotify_id and not re.match(r'^[a-zA-Z0-9]{22}$', self.spotify_id):
            print(f"⚠️ Format Spotify ID invalide pour {self.name}: {self.spotify_id}")
            
        # Validation Genius ID (numérique)
        if self.genius_id and not self.genius_id.isdigit():
            print(f"⚠️ Format Genius ID invalide pour {self.name}: {self.genius_id}")

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
    artist_name: Optional[str] = None
    
    # Informations de sortie
    release_date: Optional[str] = None
    release_year: Optional[int] = None
    album_type: Optional[AlbumType] = None
    
    # IDs externes
    spotify_id: Optional[str] = None
    discogs_id: Optional[str] = None
    genius_id: Optional[str] = None
    
    # Métadonnées
    genre: Optional[str] = None
    label: Optional[str] = None
    track_count: Optional[int] = None
    total_duration: Optional[int] = None  # en secondes
    cover_url: Optional[str] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Initialisation post-création"""
        if self.created_at is None:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
        
        # Auto-détection du type d'album basé sur le nombre de tracks
        if self.album_type is None and self.track_count is not None:
            if self.track_count == 1:
                self.album_type = AlbumType.SINGLE
            elif self.track_count <= 6:
                self.album_type = AlbumType.EP
            else:
                self.album_type = AlbumType.ALBUM
        
        # Extraire l'année de la date si pas fournie
        if self.release_date and not self.release_year:
            try:
                if '-' in self.release_date:
                    self.release_year = int(self.release_date.split('-')[0])
            except (ValueError, IndexError):
                pass
        
        # Validation URL de cover
        if self.cover_url:
            self._validate_cover_url()

    def _validate_cover_url(self):
        """Valide l'URL de la pochette"""
        try:
            result = urlparse(self.cover_url)
            if not all([result.scheme, result.netloc]):
                print(f"⚠️ URL de pochette invalide pour {self.title}: {self.cover_url}")
        except Exception:
            print(f"⚠️ Erreur validation URL pochette pour {self.title}")

    def get_duration_formatted(self) -> str:
        """Retourne la durée formatée (MM:SS ou HH:MM:SS)"""
        if not self.total_duration:
            return "Unknown"
        
        hours = self.total_duration // 3600
        minutes = (self.total_duration % 3600) // 60
        seconds = self.total_duration % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'title': self.title,
            'artist_id': self.artist_id,
            'artist_name': self.artist_name,
            'release_date': self.release_date,
            'release_year': self.release_year,
            'album_type': self.album_type.value if self.album_type else None,
            'genre': self.genre,
            'label': self.label,
            'spotify_id': self.spotify_id,
            'discogs_id': self.discogs_id,
            'genius_id': self.genius_id,
            'track_count': self.track_count,
            'total_duration': self.total_duration,
            'duration_formatted': self.get_duration_formatted(),
            'cover_url': self.cover_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

@dataclass
class Track:
    """Entité représentant un morceau"""
    id: Optional[int] = None
    title: str = ""
    artist_id: Optional[int] = None
    artist_name: Optional[str] = None
    album_id: Optional[int] = None
    album_title: Optional[str] = None
    track_number: Optional[int] = None
    disc_number: int = 1
    
    # IDs externes
    genius_id: Optional[str] = None
    spotify_id: Optional[str] = None
    genius_url: Optional[str] = None
    lastfm_url: Optional[str] = None
    
    # Métadonnées audio
    duration_seconds: Optional[int] = None
    bpm: Optional[int] = None
    key: Optional[str] = None
    
    # Informations de sortie
    release_date: Optional[str] = None
    release_year: Optional[int] = None
    
    # Contenu
    has_lyrics: bool = False
    lyrics: Optional[str] = None
    lyrics_snippet: Optional[str] = None
    
    # Statut extraction
    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    data_sources: List[DataSource] = field(default_factory=list)
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    extraction_date: Optional[datetime] = None
    
    # Relations - CORRECTION: featuring_artists au lieu de features string
    credits: List['Credit'] = field(default_factory=list)
    featuring_artists: List[str] = field(default_factory=list)  # Noms des artistes en featuring

    def __post_init__(self):
        """Initialisation post-création"""
        if self.created_at is None:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
        
        # Extraire l'année de la date si pas fournie
        if self.release_date and not self.release_year:
            try:
                if '-' in self.release_date:
                    self.release_year = int(self.release_date.split('-')[0])
            except (ValueError, IndexError):
                pass
        
        # Validation des URLs
        self._validate_urls()
        
        # Validation des données audio
        self._validate_audio_data()

    def _validate_urls(self):
        """Valide les URLs"""
        urls_to_check = {
            'genius_url': self.genius_url,
            'lastfm_url': self.lastfm_url
        }
        
        for url_name, url in urls_to_check.items():
            if url:
                try:
                    result = urlparse(url)
                    if not all([result.scheme, result.netloc]):
                        print(f"⚠️ {url_name} invalide pour {self.title}: {url}")
                except Exception:
                    print(f"⚠️ Erreur validation {url_name} pour {self.title}")

    def _validate_audio_data(self):
        """Valide les données audio"""
        # Validation BPM
        if self.bpm and (self.bpm < 40 or self.bpm > 300):
            print(f"⚠️ BPM suspect pour {self.title}: {self.bpm}")
        
        # Validation durée
        if self.duration_seconds and (self.duration_seconds < 10 or self.duration_seconds > 1800):
            print(f"⚠️ Durée suspecte pour {self.title}: {self.duration_seconds}s")

    def get_duration_formatted(self) -> str:
        """Retourne la durée formatée (MM:SS)"""
        if not self.duration_seconds:
            return "Unknown"
        
        minutes = self.duration_seconds // 60
        seconds = self.duration_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def get_credits_by_category(self, category: CreditCategory) -> List['Credit']:
        """Retourne les crédits d'une catégorie spécifique"""
        return [credit for credit in self.credits if credit.credit_category == category]

    def get_credits_by_type(self, credit_type: CreditType) -> List['Credit']:
        """Retourne les crédits d'un type spécifique"""
        return [credit for credit in self.credits if credit.credit_type == credit_type]

    def get_producers(self) -> List[str]:
        """Retourne la liste des producteurs"""
        producer_credits = self.get_credits_by_category(CreditCategory.PRODUCER)
        return [credit.person_name for credit in producer_credits]

    def get_unique_collaborators(self) -> List[str]:
        """Retourne la liste des collaborateurs uniques (hors artiste principal)"""
        collaborators = set()
        for credit in self.credits:
            if credit.person_name and credit.person_name != self.artist_name:
                collaborators.add(credit.person_name)
        # Ajouter les featuring artists
        for featuring in self.featuring_artists:
            if featuring != self.artist_name:
                collaborators.add(featuring)
        return sorted(list(collaborators))

    def has_category_credit(self, category: CreditCategory) -> bool:
        """Vérifie si le track a des crédits d'une catégorie donnée"""
        return any(credit.credit_category == category for credit in self.credits)

    def add_credit(self, credit: 'Credit'):
        """Ajoute un crédit au track"""
        # Éviter les doublons basés sur le nom et le type
        if not any(c.person_name == credit.person_name and 
                  c.credit_type == credit.credit_type for c in self.credits):
            self.credits.append(credit)
            self.updated_at = datetime.now()

    def add_data_source(self, source: DataSource):
        """Ajoute une source de données"""
        if source not in self.data_sources:
            self.data_sources.append(source)
            self.updated_at = datetime.now()

    def add_featuring_artist(self, artist_name: str):
        """Ajoute un artiste en featuring"""
        if artist_name not in self.featuring_artists and artist_name != self.artist_name:
            self.featuring_artists.append(artist_name)
            self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'title': self.title,
            'artist_id': self.artist_id,
            'artist_name': self.artist_name,
            'album_id': self.album_id,
            'album_title': self.album_title,
            'track_number': self.track_number,
            'disc_number': self.disc_number,
            'genius_id': self.genius_id,
            'spotify_id': self.spotify_id,
            'genius_url': self.genius_url,
            'lastfm_url': self.lastfm_url,
            'duration_seconds': self.duration_seconds,
            'duration_formatted': self.get_duration_formatted(),
            'bpm': self.bpm,
            'key': self.key,
            'release_date': self.release_date,
            'release_year': self.release_year,
            'has_lyrics': self.has_lyrics,
            'lyrics': self.lyrics,
            'lyrics_snippet': self.lyrics_snippet,
            'extraction_status': self.extraction_status.value,
            'data_sources': [source.value for source in self.data_sources],
            'featuring_artists': self.featuring_artists,  # CORRECTION
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
        name = re.sub(r'^(by |prod\.?\s*by |produced\s*by )\s*', '', name, flags=re.IGNORECASE)
        # Supprimer les suffixes
        name = re.sub(r'\s*\(uncredited\)$', '', name, flags=re.IGNORECASE)
        # Nettoyer les espaces multiples
        name = re.sub(r'\s+', ' ', name)
        return name.strip()

    def _detect_category(self) -> CreditCategory:
        """Détecte automatiquement la catégorie de crédit"""
        type_to_category = {
            # Production
            CreditType.PRODUCER: CreditCategory.PRODUCER,
            CreditType.EXECUTIVE_PRODUCER: CreditCategory.PRODUCER,
            CreditType.CO_PRODUCER: CreditCategory.PRODUCER,
            CreditType.ADDITIONAL_PRODUCTION: CreditCategory.PRODUCER,
            
            # Instruments
            CreditType.GUITAR: CreditCategory.INSTRUMENT,
            CreditType.BASS: CreditCategory.INSTRUMENT,
            CreditType.DRUMS: CreditCategory.INSTRUMENT,
            CreditType.PIANO: CreditCategory.INSTRUMENT,
            CreditType.KEYBOARD: CreditCategory.INSTRUMENT,
            CreditType.SAXOPHONE: CreditCategory.INSTRUMENT,
            CreditType.TRUMPET: CreditCategory.INSTRUMENT,
            CreditType.VIOLIN: CreditCategory.INSTRUMENT,
            
            # Technique
            CreditType.MIXING: CreditCategory.TECHNICAL,
            CreditType.MASTERING: CreditCategory.TECHNICAL,
            CreditType.RECORDING: CreditCategory.TECHNICAL,
            CreditType.ENGINEERING: CreditCategory.TECHNICAL,
            
            # Vocal
            CreditType.LEAD_VOCALS: CreditCategory.VOCAL,
            CreditType.BACKING_VOCALS: CreditCategory.VOCAL,
            CreditType.RAP: CreditCategory.VOCAL,
            CreditType.FEATURING: CreditCategory.FEATURING,
            
            # Composition
            CreditType.SONGWRITER: CreditCategory.COMPOSER,
            CreditType.COMPOSER: CreditCategory.COMPOSER,
            CreditType.LYRICIST: CreditCategory.COMPOSER,
            
            # Sample
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
        now = datetime.now()
        if self.created_at is None:
            self.created_at = now
        if self.start_time is None:
            self.start_time = now
        if self.last_activity is None:
            self.last_activity = now
        self.updated_at = now
        
        # Génération d'un ID unique si pas fourni
        if not self.id:
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            artist_clean = "".join(c for c in self.artist_name if c.isalnum())[:10]
            self.id = f"{artist_clean}_{timestamp}"

    def get_progress_percentage(self) -> float:
        """Calcule le pourcentage de progression"""
        if self.total_tracks_found == 0:
            return 0.0
        return (self.tracks_processed / self.total_tracks_found) * 100

    def get_credits_percentage(self) -> float:
        """Calcule le pourcentage de tracks avec crédits"""
        if self.tracks_processed == 0:
            return 0.0
        return (self.tracks_with_credits / self.tracks_processed) * 100

    def get_success_rate(self) -> float:
        """Calcule le taux de succès"""
        if self.tracks_processed == 0:
            return 0.0
        successful = self.tracks_processed - self.failed_tracks
        return (successful / self.tracks_processed) * 100

    def update_stats(self, tracks_processed: int = 0, tracks_with_credits: int = 0, 
                    tracks_with_albums: int = 0, failed_tracks: int = 0):
        """Met à jour les statistiques de progression"""
        if tracks_processed > 0:
            self.tracks_processed += tracks_processed
        if tracks_with_credits > 0:
            self.tracks_with_credits += tracks_with_credits
        if tracks_with_albums > 0:
            self.tracks_with_albums += tracks_with_albums
        if failed_tracks > 0:
            self.failed_tracks += failed_tracks
        
        self.updated_at = datetime.now()
        self.last_activity = datetime.now()

    def add_error(self, error_message: str):
        """Ajoute une erreur à la session"""
        self.error_count += 1
        self.last_error = error_message
        self.updated_at = datetime.now()
        self.last_activity = datetime.now()

    def complete_session(self):
        """Marque la session comme terminée"""
        self.status = SessionStatus.COMPLETED
        self.end_time = datetime.now()
        self.updated_at = datetime.now()
        if self.start_time:
            self.processing_time_seconds = (self.end_time - self.start_time).total_seconds()

    def fail_session(self, error_message: str = None):
        """Marque la session comme échouée"""
        self.status = SessionStatus.FAILED
        self.end_time = datetime.now()
        if error_message:
            self.add_error(error_message)

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
            'credits_percentage': self.get_credits_percentage(),
            'success_rate': self.get_success_rate(),
            'processing_time_seconds': self.processing_time_seconds,
            'error_count': self.error_count,
            'last_error': self.last_error
        }

@dataclass
class QualityReport:
    """Rapport de qualité pour un morceau - CORRECTION MAJEURE"""
    id: Optional[int] = None
    track_id: Optional[int] = None
    issues: List[str] = field(default_factory=list)
    quality_score: float = 0.0  # Score 0-100
    quality_level: QualityLevel = QualityLevel.AVERAGE  # CORRECTION: utiliser l'enum
    checked_at: Optional[datetime] = None
    
    # Détails des vérifications
    has_producer: bool = False
    has_bpm: bool = False
    has_duration: bool = False
    has_valid_duration: bool = False
    has_album_info: bool = False
    has_lyrics: bool = False
    has_credits: bool = False

    def __post_init__(self):
        """Initialisation post-création"""
        if self.checked_at is None:
            self.checked_at = datetime.now()
        
        # Calculer le niveau de qualité basé sur le score
        self.quality_level = self._determine_quality_level()

    def _determine_quality_level(self) -> QualityLevel:
        """Détermine le niveau de qualité basé sur le score"""
        if self.quality_score >= 90:
            return QualityLevel.EXCELLENT
        elif self.quality_score >= 75:
            return QualityLevel.GOOD
        elif self.quality_score >= 50:
            return QualityLevel.AVERAGE
        elif self.quality_score >= 25:
            return QualityLevel.POOR
        else:
            return QualityLevel.VERY_POOR

    def add_issue(self, issue: str):
        """Ajoute un problème détecté"""
        if issue not in self.issues:
            self.issues.append(issue)

    def calculate_score(self) -> float:
        """Calcule le score de qualité basé sur les problèmes et critères"""
        base_score = 50.0  # Score de base
        
        # Critères principaux (points bonus)
        if self.has_producer:
            base_score += 15
        if self.has_bpm:
            base_score += 10
        if self.has_duration and self.has_valid_duration:
            base_score += 10
        if self.has_album_info:
            base_score += 10
        if self.has_lyrics:
            base_score += 3
        if self.has_credits:
            base_score += 2
        
        # Problèmes détectés (points négatifs)
        critical_issues = [i for i in self.issues if "critique" in i.lower()]
        minor_issues = len(self.issues) - len(critical_issues)
        
        base_score -= len(critical_issues) * 20  # -20 points par problème critique
        base_score -= minor_issues * 5           # -5 points par problème mineur
        
        # Score final entre 0 et 100
        self.quality_score = max(0.0, min(100.0, base_score))
        return self.quality_score

    def get_quality_level_text(self) -> str:
        """Retourne le niveau de qualité sous forme de texte"""
        return {
            QualityLevel.EXCELLENT: "Excellent",
            QualityLevel.GOOD: "Bon",
            QualityLevel.AVERAGE: "Moyen",
            QualityLevel.POOR: "Faible",
            QualityLevel.VERY_POOR: "Très faible"
        }.get(self.quality_level, "Inconnu")

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'entité en dictionnaire pour l'export"""
        return {
            'id': self.id,
            'track_id': self.track_id,
            'quality_score': self.quality_score,
            'quality_level': self.quality_level.value,
            'quality_level_text': self.get_quality_level_text(),
            'issues': self.issues,
            'has_producer': self.has_producer,
            'has_bpm': self.has_bpm,
            'has_duration': self.has_duration,
            'has_valid_duration': self.has_valid_duration,
            'has_album_info': self.has_album_info,
            'has_lyrics': self.has_lyrics,
            'has_credits': self.has_credits,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None
        }