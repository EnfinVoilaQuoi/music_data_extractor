# processors/data_validator.py
import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from ..models.entities import Track, Credit, Artist, Album, QualityReport
from ..models.enums import CreditType, CreditCategory, DataSource, QualityLevel, AlbumType
from ..core.database import Database
from ..config.settings import settings
from ..utils.text_utils import validate_artist_name, similarity_ratio

class ValidationLevel(Enum):
    """Niveaux de validation"""
    BASIC = "basic"           # Validation minimale
    STANDARD = "standard"     # Validation standard
    STRICT = "strict"         # Validation stricte
    PARANOID = "paranoid"     # Validation très stricte

class IssueType(Enum):
    """Types de problèmes détectés"""
    CRITICAL = "critical"     # Problème critique
    WARNING = "warning"       # Avertissement
    INFO = "info"            # Information
    SUGGESTION = "suggestion" # Suggestion d'amélioration

@dataclass
class ValidationIssue:
    """Représente un problème de validation"""
    type: IssueType
    category: str
    message: str
    field: Optional[str] = None
    suggested_fix: Optional[str] = None
    confidence: float = 1.0  # Confiance dans la détection (0-1)

@dataclass
class ValidationResult:
    """Résultat de validation pour une entité"""
    entity_type: str
    entity_id: Optional[int]
    is_valid: bool
    quality_score: float  # Score de 0 à 100
    quality_level: QualityLevel
    issues: List[ValidationIssue]
    metadata: Dict[str, Any]

@dataclass
class ValidationStats:
    """Statistiques de validation"""
    total_validated: int = 0
    valid_entities: int = 0
    invalid_entities: int = 0
    critical_issues: int = 0
    warnings: int = 0
    suggestions: int = 0
    average_quality_score: float = 0.0

class DataValidator:
    """
    Validateur de données pour l'extraction musicale.
    
    Responsabilités :
    - Validation de l'intégrité des données
    - Détection d'anomalies et d'incohérences
    - Calcul de scores de qualité
    - Génération de rapports de validation
    """
    
    def __init__(self, database: Optional[Database] = None, validation_level: ValidationLevel = ValidationLevel.STANDARD):
        self.logger = logging.getLogger(__name__)
        self.database = database or Database()
        self.validation_level = validation_level
        
        # Configuration de validation
        self.config = {
            'min_track_duration': settings.get('quality.min_duration_seconds', 30),
            'max_track_duration': settings.get('quality.max_duration_seconds', 1800),
            'min_bpm': settings.get('validation.min_bpm', 40),
            'max_bpm': settings.get('validation.max_bpm', 300),
            'require_producer': settings.get('validation.require_producer', True),
            'require_duration': settings.get('validation.require_duration', False),
            'similarity_threshold': settings.get('validation.similarity_threshold', 0.85)
        }
        
        # Patterns de validation
        self.validation_patterns = self._load_validation_patterns()
        
        self.logger.info(f"DataValidator initialisé (niveau: {validation_level.value})")
    
    def _load_validation_patterns(self) -> Dict[str, Any]:
        """Charge les patterns de validation"""
        return {
            'artist_name': {
                'invalid_patterns': [
                    r'^unknown\s*artist',
                    r'^various\s*artists?',
                    r'^compilation',
                    r'^soundtrack',
                    r'^\[.*\]$',
                    r'^\d+$',
                    r'^feat\.?\s',
                    r'^ft\.?\s'
                ],
                'suspicious_patterns': [
                    r'^\w{1}$',  # Un seul caractère
                    r'^\d+\w*$',  # Commence par des chiffres
                    r'^[^a-zA-Z]*$'  # Pas de lettres
                ]
            },
            'track_title': {
                'invalid_patterns': [
                    r'^track\s*\d+',
                    r'^untitled',
                    r'^unknown',
                    r'^test',
                    r'^\s*$'
                ],
                'suspicious_patterns': [
                    r'^\d+\.$',  # Juste un numéro
                    r'^[^a-zA-Z]*$'  # Pas de lettres
                ]
            },
            'album_title': {
                'invalid_patterns': [
                    r'^unknown\s*album',
                    r'^untitled',
                    r'^various',
                    r'^\s*$'
                ]
            },
            'urls': {
                'genius_pattern': r'^https?://genius\.com/.*',
                'spotify_pattern': r'^https?://open\.spotify\.com/.*',
                'lastfm_pattern': r'^https?://www\.last\.fm/.*'
            }
        }
    
    def validate_track(self, track: Track) -> ValidationResult:
        """
        Valide un morceau complet.
        
        Args:
            track: Morceau à valider
            
        Returns:
            ValidationResult: Résultat de la validation
        """
        issues = []
        
        try:
            # Validation des champs obligatoires
            issues.extend(self._validate_track_required_fields(track))
            
            # Validation du titre
            issues.extend(self._validate_track_title(track))
            
            # Validation de l'artiste
            issues.extend(self._validate_track_artist(track))
            
            # Validation des données audio
            issues.extend(self._validate_audio_data(track))
            
            # Validation des crédits
            issues.extend(self._validate_track_credits(track))
            
            # Validation des featuring
            issues.extend(self._validate_featuring_artists(track))
            
            # Validation des URLs
            issues.extend(self._validate_track_urls(track))
            
            # Validation de l'album
            issues.extend(self._validate_track_album_info(track))
            
            # Validation des données techniques
            if self.validation_level in [ValidationLevel.STRICT, ValidationLevel.PARANOID]:
                issues.extend(self._validate_track_technical_data(track))
            
            # Calcul du score de qualité
            quality_score = self._calculate_track_quality_score(track, issues)
            quality_level = self._determine_quality_level(quality_score)
            
            # Détermination de la validité
            critical_issues = [i for i in issues if i.type == IssueType.CRITICAL]
            is_valid = len(critical_issues) == 0
            
            return ValidationResult(
                entity_type="track",
                entity_id=track.id,
                is_valid=is_valid,
                quality_score=quality_score,
                quality_level=quality_level,
                issues=issues,
                metadata={
                    'title': track.title,
                    'artist': track.artist_name,
                    'credits_count': len(track.credits),
                    'duration': track.duration_seconds
                }
            )
            
        except Exception as e:
            self.logger.error(f"Erreur validation track '{track.title}': {e}")
            return ValidationResult(
                entity_type="track",
                entity_id=track.id,
                is_valid=False,
                quality_score=0.0,
                quality_level=QualityLevel.VERY_POOR,
                issues=[ValidationIssue(
                    type=IssueType.CRITICAL,
                    category="system",
                    message=f"Erreur lors de la validation: {e}"
                )],
                metadata={}
            )
    
    def _validate_track_required_fields(self, track: Track) -> List[ValidationIssue]:
        """Valide les champs obligatoires d'un track"""
        issues = []
        
        if not track.title or not track.title.strip():
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="required_field",
                message="Titre manquant",
                field="title",
                suggested_fix="Ajouter un titre valide"
            ))
        
        if not track.artist_name or not track.artist_name.strip():
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="required_field",
                message="Nom d'artiste manquant",
                field="artist_name",
                suggested_fix="Ajouter le nom de l'artiste"
            ))
        
        if not track.artist_id:
            issues.append(ValidationIssue(
                type=IssueType.WARNING,
                category="required_field",
                message="ID d'artiste manquant",
                field="artist_id",
                suggested_fix="Associer le track à un artiste"
            ))
        
        return issues
    
    def _validate_track_title(self, track: Track) -> List[ValidationIssue]:
        """Valide le titre d'un track"""
        issues = []
        
        if not track.title:
            return issues
        
        title = track.title.strip()
        
        # Validation contre les patterns invalides
        for pattern in self.validation_patterns['track_title']['invalid_patterns']:
            if re.match(pattern, title, re.IGNORECASE):
                issues.append(ValidationIssue(
                    type=IssueType.CRITICAL,
                    category="invalid_title",
                    message=f"Titre invalide: '{title}'",
                    field="title",
                    suggested_fix="Corriger le titre du morceau"
                ))
                break
        
        # Validation contre les patterns suspects
        for pattern in self.validation_patterns['track_title']['suspicious_patterns']:
            if re.match(pattern, title):
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="suspicious_title",
                    message=f"Titre suspect: '{title}'",
                    field="title",
                    suggested_fix="Vérifier le titre du morceau"
                ))
                break
        
        # Validation de la longueur
        if len(title) < 1:
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="title_length",
                message="Titre trop court",
                field="title"
            ))
        elif len(title) > 200:
            issues.append(ValidationIssue(
                type=IssueType.WARNING,
                category="title_length",
                message="Titre très long (> 200 caractères)",
                field="title"
            ))
        
        return issues
    
    def _validate_track_artist(self, track: Track) -> List[ValidationIssue]:
        """Valide l'artiste d'un track"""
        issues = []
        
        if not track.artist_name:
            return issues
        
        artist_name = track.artist_name.strip()
        
        # Utiliser la fonction de validation des text_utils
        if not validate_artist_name(artist_name):
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="invalid_artist",
                message=f"Nom d'artiste invalide: '{artist_name}'",
                field="artist_name",
                suggested_fix="Corriger le nom de l'artiste"
            ))
        
        # Validation contre patterns suspects
        for pattern in self.validation_patterns['artist_name']['suspicious_patterns']:
            if re.match(pattern, artist_name):
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="suspicious_artist",
                    message=f"Nom d'artiste suspect: '{artist_name}'",
                    field="artist_name"
                ))
                break
        
        return issues
    
    def _validate_audio_data(self, track: Track) -> List[ValidationIssue]:
        """Valide les données audio d'un track"""
        issues = []
        
        # Validation de la durée
        if track.duration_seconds is not None:
            if track.duration_seconds < self.config['min_track_duration']:
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="suspicious_duration",
                    message=f"Durée très courte: {track.duration_seconds}s",
                    field="duration_seconds",
                    suggested_fix="Vérifier la durée du morceau"
                ))
            elif track.duration_seconds > self.config['max_track_duration']:
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="suspicious_duration",
                    message=f"Durée très longue: {track.duration_seconds}s",
                    field="duration_seconds",
                    suggested_fix="Vérifier la durée du morceau"
                ))
        elif self.config['require_duration']:
            issues.append(ValidationIssue(
                type=IssueType.WARNING,
                category="missing_data",
                message="Durée manquante",
                field="duration_seconds",
                suggested_fix="Ajouter la durée du morceau"
            ))
        
        # Validation du BPM
        if track.bpm is not None:
            if track.bpm < self.config['min_bpm'] or track.bpm > self.config['max_bpm']:
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="suspicious_bpm",
                    message=f"BPM suspect: {track.bpm}",
                    field="bpm",
                    suggested_fix="Vérifier le BPM du morceau"
                ))
        
        # Validation de la clé musicale
        if track.key:
            valid_keys = [
                'C', 'C#', 'Db', 'D', 'D#', 'Eb', 'E', 'F', 'F#', 'Gb', 
                'G', 'G#', 'Ab', 'A', 'A#', 'Bb', 'B',
                'Cm', 'C#m', 'Dm', 'D#m', 'Em', 'Fm', 'F#m', 'Gm', 
                'G#m', 'Am', 'A#m', 'Bm'
            ]
            if track.key not in valid_keys:
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="invalid_key",
                    message=f"Clé musicale invalide: '{track.key}'",
                    field="key",
                    suggested_fix="Corriger la clé musicale"
                ))
        
        return issues
    
    def _validate_track_credits(self, track: Track) -> List[ValidationIssue]:
        """Valide les crédits d'un track"""
        issues = []
        
        if not track.credits:
            if self.config['require_producer']:
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="missing_credits",
                    message="Aucun crédit trouvé",
                    field="credits",
                    suggested_fix="Ajouter les crédits du morceau"
                ))
            return issues
        
        # Vérifier la présence d'un producteur
        has_producer = any(
            credit.credit_category == CreditCategory.PRODUCER 
            for credit in track.credits
        )
        
        if not has_producer and self.config['require_producer']:
            issues.append(ValidationIssue(
                type=IssueType.WARNING,
                category="missing_producer",
                message="Aucun producteur identifié",
                field="credits",
                suggested_fix="Ajouter le producteur du morceau"
            ))
        
        # Validation individuelle des crédits
        credit_names = set()
        for i, credit in enumerate(track.credits):
            credit_issues = self._validate_credit(credit, i)
            issues.extend(credit_issues)
            
            # Détection de doublons de crédits
            credit_key = (credit.person_name.lower(), credit.credit_type)
            if credit_key in credit_names:
                issues.append(ValidationIssue(
                    type=IssueType.INFO,
                    category="duplicate_credit",
                    message=f"Crédit en double: {credit.person_name} ({credit.credit_type.value})",
                    field=f"credits[{i}]",
                    suggested_fix="Supprimer le crédit en double"
                ))
            else:
                credit_names.add(credit_key)
        
        return issues
    
    def _validate_credit(self, credit: Credit, index: int) -> List[ValidationIssue]:
        """Valide un crédit individuel"""
        issues = []
        
        # Validation du nom de la personne
        if not credit.person_name or not credit.person_name.strip():
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="invalid_credit",
                message="Nom de créditeur manquant",
                field=f"credits[{index}].person_name",
                suggested_fix="Ajouter le nom du créditeur"
            ))
        elif not validate_artist_name(credit.person_name):
            issues.append(ValidationIssue(
                type=IssueType.WARNING,
                category="invalid_credit",
                message=f"Nom de créditeur suspect: '{credit.person_name}'",
                field=f"credits[{index}].person_name"
            ))
        
        # Validation de la cohérence catégorie/type
        if credit.credit_category and credit.credit_type:
            expected_category = self._get_expected_category_for_type(credit.credit_type)
            if expected_category and expected_category != credit.credit_category:
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="inconsistent_credit",
                    message=f"Incohérence catégorie/type: {credit.credit_category.value}/{credit.credit_type.value}",
                    field=f"credits[{index}]",
                    suggested_fix=f"Corriger la catégorie vers {expected_category.value}"
                ))
        
        return issues
    
    def _get_expected_category_for_type(self, credit_type: CreditType) -> Optional[CreditCategory]:
        """Retourne la catégorie attendue pour un type de crédit"""
        type_to_category = {
            CreditType.PRODUCER: CreditCategory.PRODUCER,
            CreditType.EXECUTIVE_PRODUCER: CreditCategory.PRODUCER,
            CreditType.CO_PRODUCER: CreditCategory.PRODUCER,
            CreditType.MIXING: CreditCategory.TECHNICAL,
            CreditType.MASTERING: CreditCategory.TECHNICAL,
            CreditType.RECORDING: CreditCategory.TECHNICAL,
            CreditType.FEATURING: CreditCategory.FEATURING,
            CreditType.LEAD_VOCALS: CreditCategory.VOCAL,
            CreditType.BACKING_VOCALS: CreditCategory.VOCAL,
            CreditType.RAP: CreditCategory.VOCAL,
            CreditType.SONGWRITER: CreditCategory.COMPOSER,
            CreditType.COMPOSER: CreditCategory.COMPOSER,
            CreditType.GUITAR: CreditCategory.INSTRUMENT,
            CreditType.PIANO: CreditCategory.INSTRUMENT,
            CreditType.DRUMS: CreditCategory.INSTRUMENT,
            CreditType.BASS: CreditCategory.INSTRUMENT,
            CreditType.SAXOPHONE: CreditCategory.INSTRUMENT,
            CreditType.SAMPLE: CreditCategory.SAMPLE,
            CreditType.INTERPOLATION: CreditCategory.SAMPLE
        }
        return type_to_category.get(credit_type)
    
    def _validate_featuring_artists(self, track: Track) -> List[ValidationIssue]:
        """Valide les artistes en featuring"""
        issues = []
        
        if not track.featuring_artists:
            return issues
        
        for i, featuring in enumerate(track.featuring_artists):
            if not featuring or not featuring.strip():
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="invalid_featuring",
                    message="Artiste featuring vide",
                    field=f"featuring_artists[{i}]",
                    suggested_fix="Supprimer l'entrée vide"
                ))
            elif not validate_artist_name(featuring):
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="invalid_featuring",
                    message=f"Nom d'artiste featuring suspect: '{featuring}'",
                    field=f"featuring_artists[{i}]"
                ))
            
            # Vérifier que l'artiste featuring n'est pas l'artiste principal
            if featuring.lower() == track.artist_name.lower():
                issues.append(ValidationIssue(
                    type=IssueType.INFO,
                    category="redundant_featuring",
                    message=f"Artiste principal en featuring: '{featuring}'",
                    field=f"featuring_artists[{i}]",
                    suggested_fix="Supprimer l'artiste principal des featuring"
                ))
        
        # Vérifier les doublons
        seen = set()
        for i, featuring in enumerate(track.featuring_artists):
            if featuring.lower() in seen:
                issues.append(ValidationIssue(
                    type=IssueType.INFO,
                    category="duplicate_featuring",
                    message=f"Artiste featuring en double: '{featuring}'",
                    field=f"featuring_artists[{i}]",
                    suggested_fix="Supprimer le doublon"
                ))
            else:
                seen.add(featuring.lower())
        
        return issues
    
    def _validate_track_urls(self, track: Track) -> List[ValidationIssue]:
        """Valide les URLs d'un track"""
        issues = []
        
        # Validation URL Genius
        if track.genius_url:
            if not re.match(self.validation_patterns['urls']['genius_pattern'], track.genius_url):
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="invalid_url",
                    message="URL Genius invalide",
                    field="genius_url",
                    suggested_fix="Corriger l'URL Genius"
                ))
        
        # Validation URL Last.fm
        if track.lastfm_url:
            if not re.match(self.validation_patterns['urls']['lastfm_pattern'], track.lastfm_url):
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="invalid_url",
                    message="URL Last.fm invalide",
                    field="lastfm_url",
                    suggested_fix="Corriger l'URL Last.fm"
                ))
        
        return issues
    
    def _validate_track_album_info(self, track: Track) -> List[ValidationIssue]:
        """Valide les informations d'album d'un track"""
        issues = []
        
        # Validation cohérence album_id et album_title
        if track.album_id and not track.album_title:
            issues.append(ValidationIssue(
                type=IssueType.INFO,
                category="missing_album_title",
                message="ID album présent mais titre manquant",
                field="album_title",
                suggested_fix="Récupérer le titre de l'album"
            ))
        elif track.album_title and not track.album_id:
            issues.append(ValidationIssue(
                type=IssueType.INFO,
                category="missing_album_id",
                message="Titre album présent mais ID manquant",
                field="album_id",
                suggested_fix="Lier le track à l'album correspondant"
            ))
        
        # Validation track_number
        if track.track_number is not None:
            if track.track_number < 1 or track.track_number > 100:
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="invalid_track_number",
                    message=f"Numéro de track suspect: {track.track_number}",
                    field="track_number"
                ))
        
        return issues
    
    def _validate_track_technical_data(self, track: Track) -> List[ValidationIssue]:
        """Validation technique approfondie (niveau strict/paranoid)"""
        issues = []
        
        # Validation cohérence durée/BPM
        if track.duration_seconds and track.bpm:
            # Estimation grossière du nombre de battements
            estimated_beats = (track.duration_seconds / 60) * track.bpm
            if estimated_beats < 50 or estimated_beats > 1000:
                issues.append(ValidationIssue(
                    type=IssueType.INFO,
                    category="technical_inconsistency",
                    message="Incohérence possible entre durée et BPM",
                    field="bpm",
                    confidence=0.6
                ))
        
        # Validation des IDs externes
        if track.genius_id and not str(track.genius_id).isdigit():
            issues.append(ValidationIssue(
                type=IssueType.WARNING,
                category="invalid_external_id",
                message="ID Genius invalide",
                field="genius_id"
            ))
        
        if track.spotify_id and not re.match(r'^[a-zA-Z0-9]{22}$', track.spotify_id):
            issues.append(ValidationIssue(
                type=IssueType.WARNING,
                category="invalid_external_id",
                message="ID Spotify invalide",
                field="spotify_id"
            ))
        
        return issues
    
    def _calculate_track_quality_score(self, track: Track, issues: List[ValidationIssue]) -> float:
        """Calcule le score de qualité d'un track"""
        base_score = 50.0
        
        # Bonus pour les données présentes
        if track.title and track.title.strip():
            base_score += 10
        if track.artist_name and validate_artist_name(track.artist_name):
            base_score += 10
        if track.duration_seconds:
            base_score += 8
        if track.bpm:
            base_score += 7
        if track.credits:
            base_score += 10
            # Bonus pour producteur
            if any(c.credit_category == CreditCategory.PRODUCER for c in track.credits):
                base_score += 5
        if track.album_title:
            base_score += 5
        if track.lyrics:
            base_score += 3
        if track.key:
            base_score += 2
        
        # Malus pour les problèmes
        for issue in issues:
            if issue.type == IssueType.CRITICAL:
                base_score -= 15
            elif issue.type == IssueType.WARNING:
                base_score -= 5
            elif issue.type == IssueType.INFO:
                base_score -= 1
        
        return max(0.0, min(100.0, base_score))
    
    def _determine_quality_level(self, score: float) -> QualityLevel:
        """Détermine le niveau de qualité basé sur le score"""
        if score >= 90:
            return QualityLevel.EXCELLENT
        elif score >= 75:
            return QualityLevel.GOOD
        elif score >= 50:
            return QualityLevel.AVERAGE
        elif score >= 25:
            return QualityLevel.POOR
        else:
            return QualityLevel.VERY_POOR
    
    def validate_artist_tracks(self, artist_id: int) -> List[ValidationResult]:
        """Valide tous les tracks d'un artiste"""
        try:
            tracks = self.database.get_tracks_by_artist_id(artist_id)
            results = []
            
            for track in tracks:
                result = self.validate_track(track)
                results.append(result)
            
            self.logger.info(f"Validation terminée pour l'artiste {artist_id}: {len(results)} tracks validés")
            return results
            
        except Exception as e:
            self.logger.error(f"Erreur validation artiste {artist_id}: {e}")
            return []
    
    def create_quality_report(self, track: Track, validation_result: ValidationResult) -> QualityReport:
        """Crée un rapport de qualité basé sur la validation"""
        report = QualityReport(
            track_id=track.id,
            quality_score=validation_result.quality_score,
            quality_level=validation_result.quality_level
        )
        
        # Analyser les critères de qualité
        report.has_producer = any(
            c.credit_category == CreditCategory.PRODUCER for c in track.credits
        )
        report.has_bpm = track.bpm is not None
        report.has_duration = track.duration_seconds is not None
        report.has_valid_duration = (
            track.duration_seconds is not None and 
            self.config['min_track_duration'] <= track.duration_seconds <= self.config['max_track_duration']
        )
        report.has_album_info = track.album_title is not None
        report.has_lyrics = track.has_lyrics
        report.has_credits = len(track.credits) > 0
        
        # Ajouter les problèmes détectés
        for issue in validation_result.issues:
            if issue.type in [IssueType.CRITICAL, IssueType.WARNING]:
                report.add_issue(f"{issue.category}: {issue.message}")
        
        # Calculer le score final
        report.calculate_score()
        
        return report
    
    def generate_validation_summary(self, results: List[ValidationResult]) -> ValidationStats:
        """Génère un résumé des résultats de validation"""
        stats = ValidationStats()
        
        stats.total_validated = len(results)
        stats.valid_entities = sum(1 for r in results if r.is_valid)
        stats.invalid_entities = stats.total_validated - stats.valid_entities
        
        # Compter les types de problèmes
        for result in results:
            for issue in result.issues:
                if issue.type == IssueType.CRITICAL:
                    stats.critical_issues += 1
                elif issue.type == IssueType.WARNING:
                    stats.warnings += 1
                elif issue.type == IssueType.SUGGESTION:
                    stats.suggestions += 1
        
        # Calculer le score moyen
        if results:
            total_score = sum(r.quality_score for r in results)
            stats.average_quality_score = total_score / len(results)
        
        return stats
    
    def validate_album(self, album: Album) -> ValidationResult:
        """
        Valide un album.
        
        Args:
            album: Album à valider
            
        Returns:
            ValidationResult: Résultat de la validation
        """
        issues = []
        
        try:
            # Validation des champs obligatoires
            if not album.title or not album.title.strip():
                issues.append(ValidationIssue(
                    type=IssueType.CRITICAL,
                    category="required_field",
                    message="Titre d'album manquant",
                    field="title"
                ))
            
            if not album.artist_name:
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="required_field",
                    message="Nom d'artiste manquant",
                    field="artist_name"
                ))
            
            # Validation du titre d'album
            if album.title:
                for pattern in self.validation_patterns['album_title']['invalid_patterns']:
                    if re.match(pattern, album.title, re.IGNORECASE):
                        issues.append(ValidationIssue(
                            type=IssueType.CRITICAL,
                            category="invalid_title",
                            message=f"Titre d'album invalide: '{album.title}'",
                            field="title"
                        ))
                        break
            
            # Validation des dates
            if album.release_date:
                # Validation format de date basique
                if not re.match(r'^\d{4}(-\d{2}(-\d{2})?)?, album.release_date):
                    issues.append(ValidationIssue(
                        type=IssueType.WARNING,
                        category="invalid_date",
                        message=f"Format de date suspect: '{album.release_date}'",
                        field="release_date"
                    ))
            
            # Validation cohérence release_year
            if album.release_year:
                if album.release_year < 1900 or album.release_year > datetime.now().year + 1:
                    issues.append(ValidationIssue(
                        type=IssueType.WARNING,
                        category="invalid_year",
                        message=f"Année de sortie suspecte: {album.release_year}",
                        field="release_year"
                    ))
            
            # Validation du nombre de tracks
            if album.track_count is not None:
                if album.track_count < 1 or album.track_count > 100:
                    issues.append(ValidationIssue(
                        type=IssueType.WARNING,
                        category="invalid_track_count",
                        message=f"Nombre de tracks suspect: {album.track_count}",
                        field="track_count"
                    ))
                
                # Validation cohérence type d'album / nombre de tracks
                if album.album_type:
                    expected_range = self._get_expected_track_range(album.album_type)
                    if expected_range and not (expected_range[0] <= album.track_count <= expected_range[1]):
                        issues.append(ValidationIssue(
                            type=IssueType.INFO,
                            category="type_track_mismatch",
                            message=f"Incohérence type/nombre de tracks: {album.album_type.value} avec {album.track_count} tracks",
                            field="album_type",
                            suggested_fix="Vérifier le type d'album"
                        ))
            
            # Validation de la durée totale
            if album.total_duration:
                if album.total_duration < 60 or album.total_duration > 10800:  # 1min à 3h
                    issues.append(ValidationIssue(
                        type=IssueType.WARNING,
                        category="invalid_duration",
                        message=f"Durée totale suspecte: {album.total_duration}s",
                        field="total_duration"
                    ))
            
            # Validation des IDs externes
            if album.spotify_id and not re.match(r'^[a-zA-Z0-9]{22}, album.spotify_id):
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="invalid_external_id",
                    message="ID Spotify invalide",
                    field="spotify_id"
                ))
            
            # Calcul du score de qualité
            quality_score = self._calculate_album_quality_score(album, issues)
            quality_level = self._determine_quality_level(quality_score)
            
            is_valid = not any(issue.type == IssueType.CRITICAL for issue in issues)
            
            return ValidationResult(
                entity_type="album",
                entity_id=album.id,
                is_valid=is_valid,
                quality_score=quality_score,
                quality_level=quality_level,
                issues=issues,
                metadata={
                    'title': album.title,
                    'artist': album.artist_name,
                    'track_count': album.track_count,
                    'album_type': album.album_type.value if album.album_type else None
                }
            )
            
        except Exception as e:
            self.logger.error(f"Erreur validation album '{album.title}': {e}")
            return ValidationResult(
                entity_type="album",
                entity_id=album.id,
                is_valid=False,
                quality_score=0.0,
                quality_level=QualityLevel.VERY_POOR,
                issues=[ValidationIssue(
                    type=IssueType.CRITICAL,
                    category="system",
                    message=f"Erreur lors de la validation: {e}"
                )],
                metadata={}
            )
    
    def _get_expected_track_range(self, album_type: AlbumType) -> Optional[Tuple[int, int]]:
        """Retourne la plage attendue de tracks pour un type d'album"""
        ranges = {
            AlbumType.SINGLE: (1, 3),
            AlbumType.EP: (4, 8),
            AlbumType.ALBUM: (8, 50),
            AlbumType.COMPILATION: (10, 100),
            AlbumType.MIXTAPE: (5, 30),
            AlbumType.LIVE: (5, 50)
        }
        return ranges.get(album_type)
    
    def _calculate_album_quality_score(self, album: Album, issues: List[ValidationIssue]) -> float:
        """Calcule le score de qualité d'un album"""
        base_score = 50.0
        
        # Bonus pour les données présentes
        if album.title and album.title.strip():
            base_score += 15
        if album.artist_name:
            base_score += 10
        if album.release_date:
            base_score += 10
        if album.album_type:
            base_score += 8
        if album.track_count:
            base_score += 7
        if album.total_duration:
            base_score += 5
        if album.genre:
            base_score += 3
        if album.label:
            base_score += 2
        
        # Malus pour les problèmes
        for issue in issues:
            if issue.type == IssueType.CRITICAL:
                base_score -= 20
            elif issue.type == IssueType.WARNING:
                base_score -= 7
            elif issue.type == IssueType.INFO:
                base_score -= 2
        
        return max(0.0, min(100.0, base_score))
    
    def validate_artist(self, artist: Artist) -> ValidationResult:
        """
        Valide un artiste.
        
        Args:
            artist: Artiste à valider
            
        Returns:
            ValidationResult: Résultat de la validation
        """
        issues = []
        
        try:
            # Validation du nom
            if not artist.name or not artist.name.strip():
                issues.append(ValidationIssue(
                    type=IssueType.CRITICAL,
                    category="required_field",
                    message="Nom d'artiste manquant",
                    field="name"
                ))
            elif not validate_artist_name(artist.name):
                issues.append(ValidationIssue(
                    type=IssueType.CRITICAL,
                    category="invalid_name",
                    message=f"Nom d'artiste invalide: '{artist.name}'",
                    field="name"
                ))
            
            # Validation des IDs externes
            if artist.genius_id and not str(artist.genius_id).isdigit():
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="invalid_external_id",
                    message="ID Genius invalide",
                    field="genius_id"
                ))
            
            if artist.spotify_id and not re.match(r'^[a-zA-Z0-9]{22}, artist.spotify_id):
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="invalid_external_id",
                    message="ID Spotify invalide",
                    field="spotify_id"
                ))
            
            # Validation des années d'activité
            if artist.active_years:
                if not re.match(r'^\d{4}(-\d{4})?( - present)?, artist.active_years):
                    issues.append(ValidationIssue(
                        type=IssueType.INFO,
                        category="invalid_years",
                        message=f"Format années d'activité suspect: '{artist.active_years}'",
                        field="active_years"
                    ))
            
            # Calcul du score de qualité
            quality_score = self._calculate_artist_quality_score(artist, issues)
            quality_level = self._determine_quality_level(quality_score)
            
            is_valid = not any(issue.type == IssueType.CRITICAL for issue in issues)
            
            return ValidationResult(
                entity_type="artist",
                entity_id=artist.id,
                is_valid=is_valid,
                quality_score=quality_score,
                quality_level=quality_level,
                issues=issues,
                metadata={
                    'name': artist.name,
                    'genre': artist.genre.value if artist.genre else None,
                    'total_tracks': artist.total_tracks
                }
            )
            
        except Exception as e:
            self.logger.error(f"Erreur validation artiste '{artist.name}': {e}")
            return ValidationResult(
                entity_type="artist",
                entity_id=artist.id,
                is_valid=False,
                quality_score=0.0,
                quality_level=QualityLevel.VERY_POOR,
                issues=[ValidationIssue(
                    type=IssueType.CRITICAL,
                    category="system",
                    message=f"Erreur lors de la validation: {e}"
                )],
                metadata={}
            )
    
    def _calculate_artist_quality_score(self, artist: Artist, issues: List[ValidationIssue]) -> float:
        """Calcule le score de qualité d'un artiste"""
        base_score = 50.0
        
        # Bonus pour les données présentes
        if artist.name and validate_artist_name(artist.name):
            base_score += 20
        if artist.genius_id:
            base_score += 10
        if artist.spotify_id:
            base_score += 10
        if artist.genre:
            base_score += 5
        if artist.country:
            base_score += 3
        if artist.active_years:
            base_score += 2
        
        # Malus pour les problèmes
        for issue in issues:
            if issue.type == IssueType.CRITICAL:
                base_score -= 25
            elif issue.type == IssueType.WARNING:
                base_score -= 10
            elif issue.type == IssueType.INFO:
                base_score -= 3
        
        return max(0.0, min(100.0, base_score))
    
    def batch_validate(self, entity_type: str, entity_ids: List[int]) -> List[ValidationResult]:
        """
        Valide plusieurs entités en lot.
        
        Args:
            entity_type: Type d'entité ('track', 'album', 'artist')
            entity_ids: Liste des IDs à valider
            
        Returns:
            Liste des résultats de validation
        """
        results = []
        
        try:
            self.logger.info(f"Début validation par lot: {len(entity_ids)} {entity_type}s")
            
            for entity_id in entity_ids:
                try:
                    if entity_type == 'track':
                        # Récupérer le track (méthode à ajouter à Database)
                        with self.database.get_connection() as conn:
                            cursor = conn.execute("SELECT * FROM tracks WHERE id = ?", (entity_id,))
                            row = cursor.fetchone()
                            if row:
                                track = self.database._row_to_track(row)
                                track.credits = self.database.get_credits_by_track_id(track.id)
                                track.featuring_artists = self.database.get_features_by_track_id(track.id)
                                result = self.validate_track(track)
                                results.append(result)
                    
                    elif entity_type == 'artist':
                        # Récupérer l'artiste (méthode à ajouter à Database)
                        with self.database.get_connection() as conn:
                            cursor = conn.execute("SELECT * FROM artists WHERE id = ?", (entity_id,))
                            row = cursor.fetchone()
                            if row:
                                from ..models.enums import Genre
                                artist = Artist(
                                    id=row['id'],
                                    name=row['name'],
                                    genius_id=row['genius_id'],
                                    spotify_id=row['spotify_id'],
                                    discogs_id=row['discogs_id'],
                                    genre=Genre(row['genre']) if row['genre'] else None,
                                    country=row['country'],
                                    active_years=row['active_years']
                                )
                                result = self.validate_artist(artist)
                                results.append(result)
                    
                    # Albums validation pourrait être ajoutée ici
                    
                except Exception as e:
                    self.logger.error(f"Erreur validation {entity_type} {entity_id}: {e}")
                    results.append(ValidationResult(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        is_valid=False,
                        quality_score=0.0,
                        quality_level=QualityLevel.VERY_POOR,
                        issues=[ValidationIssue(
                            type=IssueType.CRITICAL,
                            category="system",
                            message=f"Erreur lors de la validation: {e}"
                        )],
                        metadata={}
                    ))
            
            self.logger.info(f"Validation par lot terminée: {len(results)} résultats")
            return results
            
        except Exception as e:
            self.logger.error(f"Erreur validation par lot: {e}")
            return results
    
    def generate_detailed_report(self, results: List[ValidationResult]) -> Dict[str, Any]:
        """
        Génère un rapport détaillé de validation.
        
        Args:
            results: Résultats de validation
            
        Returns:
            Rapport détaillé
        """
        stats = self.generate_validation_summary(results)
        
        # Analyse par catégorie de problème
        issue_categories = {}
        for result in results:
            for issue in result.issues:
                category = issue.category
                if category not in issue_categories:
                    issue_categories[category] = {
                        'count': 0,
                        'critical': 0,
                        'warning': 0,
                        'info': 0,
                        'examples': []
                    }
                
                issue_categories[category]['count'] += 1
                issue_categories[category][issue.type.value] += 1
                
                if len(issue_categories[category]['examples']) < 3:
                    issue_categories[category]['examples'].append(issue.message)
        
        # Distribution des scores de qualité
        score_distribution = {
            'excellent': 0,
            'good': 0,
            'average': 0,
            'poor': 0,
            'very_poor': 0
        }
        
        for result in results:
            score_distribution[result.quality_level.value] += 1
        
        # Top problèmes
        top_issues = sorted(
            issue_categories.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )[:10]
        
        return {
            'summary': {
                'total_validated': stats.total_validated,
                'valid_entities': stats.valid_entities,
                'invalid_entities': stats.invalid_entities,
                'validation_rate': (stats.valid_entities / stats.total_validated * 100) if stats.total_validated > 0 else 0,
                'average_quality_score': round(stats.average_quality_score, 2)
            },
            'issues': {
                'critical': stats.critical_issues,
                'warnings': stats.warnings,
                'suggestions': stats.suggestions,
                'by_category': issue_categories
            },
            'quality_distribution': score_distribution,
            'top_issues': top_issues,
            'recommendations': self._generate_recommendations(issue_categories),
            'generated_at': datetime.now().isoformat()
        }
    
    def _generate_recommendations(self, issue_categories: Dict[str, Any]) -> List[str]:
        """Génère des recommandations basées sur les problèmes détectés"""
        recommendations = []
        
        # Recommandations basées sur les problèmes les plus fréquents
        sorted_issues = sorted(
            issue_categories.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )
        
        for category, data in sorted_issues[:5]:
            if data['count'] > 0:
                if category == 'missing_producer':
                    recommendations.append("Améliorer l'extraction des crédits de production")
                elif category == 'missing_data':
                    recommendations.append("Compléter les données manquantes (BPM, durée, etc.)")
                elif category == 'invalid_title':
                    recommendations.append("Vérifier et corriger les titres de morceaux")
                elif category == 'suspicious_duration':
                    recommendations.append("Valider les durées suspectes")
                elif category == 'invalid_external_id':
                    recommendations.append("Corriger les IDs externes malformés")
        
        return recommendations