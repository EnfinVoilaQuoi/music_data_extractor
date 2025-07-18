# processors/data_validator.py - VERSION CORRIGÉE
"""
Validateur de données pour l'extraction musicale.
Détecte les incohérences, valide la qualité et propose des corrections.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from models.entities import Track, Credit, Artist, Album, QualityReport
from models.enums import CreditType, CreditCategory, DataSource, QualityLevel, AlbumType
from core.database import Database
from config.settings import settings
from utils.text_utils import validate_artist_name, similarity_ratio

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
    Utilise des règles configurables et des patterns pour détecter les problèmes.
    """
    
    def __init__(self, validation_level: ValidationLevel = ValidationLevel.STANDARD):
        self.logger = logging.getLogger(__name__)
        self.validation_level = validation_level
        self.database = Database()
        
        # Configuration des seuils selon le niveau de validation
        self.config = self._load_validation_config()
        
        # Patterns de validation (compilation unique)
        self.validation_patterns = self._compile_validation_patterns()
        
        # Cache pour éviter la revalidation
        self._cache = {}
        
        # Statistiques de session
        self.session_stats = ValidationStats()
        
        self.logger.info(f"DataValidator initialisé - Niveau: {validation_level.value}")
    
    def _load_validation_config(self) -> Dict[str, Any]:
        """Charge la configuration de validation selon le niveau"""
        base_config = {
            'min_track_duration': 15,       # Durée minimale en secondes
            'max_track_duration': 600,      # Durée maximale en secondes
            'min_bpm': 60,                  # BPM minimum
            'max_bpm': 200,                 # BPM maximum
            'min_title_length': 1,          # Longueur minimale du titre
            'max_title_length': 200,        # Longueur maximale du titre
            'quality_threshold': 70.0,      # Seuil de qualité acceptable
            'similarity_threshold': 0.85,   # Seuil de similarité pour doublons
            'auto_fix_enabled': True,       # Auto-correction activée
            'strict_validation': False      # Validation stricte
        }
        
        # Ajustements selon le niveau
        if self.validation_level == ValidationLevel.STRICT:
            base_config.update({
                'min_track_duration': 30,
                'quality_threshold': 80.0,
                'strict_validation': True
            })
        elif self.validation_level == ValidationLevel.PARANOID:
            base_config.update({
                'min_track_duration': 45,
                'quality_threshold': 90.0,
                'strict_validation': True,
                'similarity_threshold': 0.90
            })
        
        return base_config
    
    def _compile_validation_patterns(self) -> Dict[str, Any]:
        """Compile les patterns de validation pour optimiser les performances"""
        return {
            'title': {
                'suspicious_patterns': [
                    r'^[^a-zA-Z0-9]+$',          # Que des caractères spéciaux
                    r'^\s*$',                     # Que des espaces
                    r'^(test|debug|temp)',        # Mots de test
                    r'[<>{}]',                    # Balises HTML/XML
                    r'(javascript|script)',       # Code suspect
                ],
                'invalid_chars': re.compile(r'[<>{}|\\^`\[\]]'),
                'normalization': re.compile(r'\s+')
            },
            'artist_name': {
                'suspicious_patterns': [
                    r'^[^a-zA-Z0-9\s\-\'\.]+$',  # Que des caractères spéciaux
                    r'^(unknown|n\/a|none|null|undefined)',  # Valeurs nulles
                    r'^[0-9]+$',                  # Que des chiffres
                ],
                'required_chars': re.compile(r'[a-zA-Z]'),  # Au moins une lettre
            },
            'external_ids': {
                'spotify_id': re.compile(r'^[a-zA-Z0-9]{22}$'),
                'genius_id': re.compile(r'^\d+$'),
                'youtube_id': re.compile(r'^[a-zA-Z0-9_-]{11}$')
            },
            'years': {
                'active_years': re.compile(r'^\d{4}(-\d{4})?$'),
                'release_year': re.compile(r'^(19|20)\d{2}$')
            }
        }
    
    # ===== MÉTHODES PRINCIPALES DE VALIDATION =====
    
    def validate_track(self, track: Track) -> ValidationResult:
        """
        Valide un track complet.
        
        Args:
            track: Track à valider
            
        Returns:
            ValidationResult: Résultat de la validation
        """
        cache_key = f"track_{track.id}_{hash(str(track))}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        issues = []
        
        # Validation du titre
        issues.extend(self._validate_track_title(track))
        
        # Validation de l'artiste
        issues.extend(self._validate_track_artist(track))
        
        # Validation des données audio
        issues.extend(self._validate_audio_data(track))
        
        # Validation des crédits (si présents)
        if hasattr(track, 'credits') and track.credits:
            issues.extend(self._validate_track_credits(track))
        
        # Validation des informations d'album
        issues.extend(self._validate_track_album_info(track))
        
        # Validation technique (selon niveau)
        if self.validation_level in [ValidationLevel.STRICT, ValidationLevel.PARANOID]:
            issues.extend(self._validate_track_technical_data(track))
        
        # Calcul du score de qualité
        quality_score = self._calculate_quality_score(track, issues)
        quality_level = self._determine_quality_level(quality_score)
        
        # Détermination de la validité
        is_valid = not any(issue.type == IssueType.CRITICAL for issue in issues)
        
        # Mise à jour des statistiques
        self._update_validation_stats(is_valid, issues)
        
        result = ValidationResult(
            entity_type="track",
            entity_id=track.id,
            is_valid=is_valid,
            quality_score=quality_score,
            quality_level=quality_level,
            issues=issues,
            metadata={
                'validation_level': self.validation_level.value,
                'timestamp': datetime.now().isoformat(),
                'auto_fixes_available': self._count_auto_fixable_issues(issues)
            }
        )
        
        # Mise en cache
        self._cache[cache_key] = result
        
        return result
    
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
            
            if artist.spotify_id and not self.validation_patterns['external_ids']['spotify_id'].match(artist.spotify_id):
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="invalid_external_id",
                    message="ID Spotify invalide",
                    field="spotify_id"
                ))
            
            # Validation des années d'activité
            if artist.active_years:
                if not self.validation_patterns['years']['active_years'].match(artist.active_years):
                    issues.append(ValidationIssue(
                        type=IssueType.WARNING,
                        category="invalid_years",
                        message=f"Format d'années d'activité invalide: '{artist.active_years}'",
                        field="active_years",
                        suggested_fix="Format attendu: YYYY ou YYYY-YYYY"
                    ))
        
        except Exception as e:
            self.logger.error(f"Erreur validation artiste {artist.name}: {e}")
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="validation_error",
                message=f"Erreur lors de la validation: {str(e)}"
            ))
        
        # Calcul du score et résultat
        quality_score = self._calculate_artist_quality_score(artist, issues)
        quality_level = self._determine_quality_level(quality_score)
        is_valid = not any(issue.type == IssueType.CRITICAL for issue in issues)
        
        return ValidationResult(
            entity_type="artist",
            entity_id=getattr(artist, 'id', None),
            is_valid=is_valid,
            quality_score=quality_score,
            quality_level=quality_level,
            issues=issues,
            metadata={
                'validation_level': self.validation_level.value,
                'timestamp': datetime.now().isoformat()
            }
        )
    
    def validate_credit(self, credit: Credit) -> ValidationResult:
        """
        Valide un crédit.
        
        Args:
            credit: Crédit à valider
            
        Returns:
            ValidationResult: Résultat de la validation
        """
        issues = []
        
        # Validation du nom de personne
        if not credit.person_name or not credit.person_name.strip():
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="required_field",
                message="Nom de personne manquant",
                field="person_name"
            ))
        
        # Validation du rôle
        if not credit.role or not credit.role.strip():
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="required_field",
                message="Rôle manquant",
                field="role"
            ))
        elif credit.role not in [ct.value for ct in CreditType]:
            issues.append(ValidationIssue(
                type=IssueType.WARNING,
                category="unknown_role",
                message=f"Rôle non reconnu: '{credit.role}'",
                field="role",
                suggested_fix="Utiliser un rôle standard ou ajouter à la liste"
            ))
        
        # Validation de la cohérence track/album
        if not credit.track_id and not credit.album_id:
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="missing_reference",
                message="Crédit non lié à un track ou album",
                field="track_id"
            ))
        
        quality_score = self._calculate_credit_quality_score(credit, issues)
        quality_level = self._determine_quality_level(quality_score)
        is_valid = not any(issue.type == IssueType.CRITICAL for issue in issues)
        
        return ValidationResult(
            entity_type="credit",
            entity_id=getattr(credit, 'id', None),
            is_valid=is_valid,
            quality_score=quality_score,
            quality_level=quality_level,
            issues=issues,
            metadata={
                'validation_level': self.validation_level.value,
                'timestamp': datetime.now().isoformat()
            }
        )
    
    # ===== MÉTHODES DE VALIDATION SPÉCIALISÉES =====
    
    def _validate_track_title(self, track: Track) -> List[ValidationIssue]:
        """Valide le titre d'un track"""
        issues = []
        
        if not track.title:
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="required_field",
                message="Titre manquant",
                field="title"
            ))
            return issues
        
        title = track.title.strip()
        
        # Validation contre patterns suspects
        for pattern in self.validation_patterns['title']['suspicious_patterns']:
            if re.match(pattern, title, re.IGNORECASE):
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="suspicious_title",
                    message=f"Titre suspect: '{title}'",
                    field="title",
                    suggested_fix="Vérifier le titre du morceau"
                ))
                break
        
        # Validation de la longueur
        if len(title) < self.config['min_title_length']:
            issues.append(ValidationIssue(
                type=IssueType.CRITICAL,
                category="title_length",
                message="Titre trop court",
                field="title"
            ))
        elif len(title) > self.config['max_title_length']:
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
            if re.match(pattern, artist_name, re.IGNORECASE):
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
                    field="duration_seconds"
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
        
        return issues
    
    def _validate_track_credits(self, track: Track) -> List[ValidationIssue]:
        """Valide les crédits d'un track"""
        issues = []
        
        credits = getattr(track, 'credits', [])
        if not credits:
            issues.append(ValidationIssue(
                type=IssueType.INFO,
                category="missing_credits",
                message="Aucun crédit trouvé",
                field="credits",
                suggested_fix="Ajouter les crédits de production"
            ))
        else:
            # Vérification de la présence d'un producteur
            has_producer = any(
                credit.role in ['Producer', 'Executive Producer', 'Co-Producer'] 
                for credit in credits
            )
            if not has_producer:
                issues.append(ValidationIssue(
                    type=IssueType.WARNING,
                    category="missing_producer",
                    message="Aucun producteur identifié",
                    field="credits",
                    suggested_fix="Ajouter les crédits de production"
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
        
        if track.spotify_id and not self.validation_patterns['external_ids']['spotify_id'].match(track.spotify_id):
            issues.append(ValidationIssue(
                type=IssueType.WARNING,
                category="invalid_external_id",
                message="ID Spotify invalide",
                field="spotify_id"
            ))
        
        return issues
    
    # ===== CALCULS DE QUALITÉ =====
    
    def _calculate_quality_score(self, track: Track, issues: List[ValidationIssue]) -> float:
        """Calcule le score de qualité d'un track (0-100)"""
        base_score = 100.0
        
        # Pénalités selon le type d'issue
        for issue in issues:
            if issue.type == IssueType.CRITICAL:
                base_score -= 30.0
            elif issue.type == IssueType.WARNING:
                base_score -= 10.0
            elif issue.type == IssueType.INFO:
                base_score -= 5.0
            elif issue.type == IssueType.SUGGESTION:
                base_score -= 2.0
        
        # Bonus pour données complètes
        completeness_bonus = 0.0
        if track.title and len(track.title.strip()) > 0:
            completeness_bonus += 5.0
        if track.artist_name and len(track.artist_name.strip()) > 0:
            completeness_bonus += 5.0
        if track.duration_seconds:
            completeness_bonus += 3.0
        if track.bpm:
            completeness_bonus += 3.0
        if getattr(track, 'lyrics', None):
            completeness_bonus += 4.0
        
        base_score += completeness_bonus
        
        return max(0.0, min(100.0, base_score))
    
    def _calculate_artist_quality_score(self, artist: Artist, issues: List[ValidationIssue]) -> float:
        """Calcule le score de qualité d'un artiste"""
        base_score = 100.0
        
        for issue in issues:
            if issue.type == IssueType.CRITICAL:
                base_score -= 40.0
            elif issue.type == IssueType.WARNING:
                base_score -= 15.0
            elif issue.type == IssueType.INFO:
                base_score -= 5.0
        
        # Bonus pour données complètes
        if artist.name and len(artist.name.strip()) > 0:
            base_score += 10.0
        if getattr(artist, 'genius_id', None):
            base_score += 5.0
        if getattr(artist, 'spotify_id', None):
            base_score += 5.0
        
        return max(0.0, min(100.0, base_score))
    
    def _calculate_credit_quality_score(self, credit: Credit, issues: List[ValidationIssue]) -> float:
        """Calcule le score de qualité d'un crédit"""
        base_score = 100.0
        
        for issue in issues:
            if issue.type == IssueType.CRITICAL:
                base_score -= 35.0
            elif issue.type == IssueType.WARNING:
                base_score -= 15.0
            elif issue.type == IssueType.INFO:
                base_score -= 5.0
        
        return max(0.0, min(100.0, base_score))
    
    def _determine_quality_level(self, score: float) -> QualityLevel:
        """Détermine le niveau de qualité basé sur le score"""
        if score >= 90:
            return QualityLevel.EXCELLENT
        elif score >= 80:
            return QualityLevel.GOOD
        elif score >= 70:
            return QualityLevel.AVERAGE
        elif score >= 50:
            return QualityLevel.POOR
        else:
            return QualityLevel.VERY_POOR
    
    # ===== MÉTHODES UTILITAIRES =====
    
    def _update_validation_stats(self, is_valid: bool, issues: List[ValidationIssue]):
        """Met à jour les statistiques de validation"""
        self.session_stats.total_validated += 1
        
        if is_valid:
            self.session_stats.valid_entities += 1
        else:
            self.session_stats.invalid_entities += 1
        
        for issue in issues:
            if issue.type == IssueType.CRITICAL:
                self.session_stats.critical_issues += 1
            elif issue.type == IssueType.WARNING:
                self.session_stats.warnings += 1
            elif issue.type == IssueType.SUGGESTION:
                self.session_stats.suggestions += 1
    
    def _count_auto_fixable_issues(self, issues: List[ValidationIssue]) -> int:
        """Compte les issues qui peuvent être corrigées automatiquement"""
        auto_fixable_categories = [
            'title_length', 'suspicious_title', 'missing_album_title',
            'invalid_track_number', 'suspicious_duration'
        ]
        
        return sum(1 for issue in issues if issue.category in auto_fixable_categories)
    
    @lru_cache(maxsize=256)
    def check_duplicate_tracks(self, track1_signature: str, track2_signature: str) -> float:
        """Vérifie si deux tracks sont des doublons (avec cache)"""
        return similarity_ratio(track1_signature, track2_signature)
    
    # ===== MÉTHODES PUBLIQUES D'ANALYSE =====
    
    def batch_validate(self, entities: List[Any]) -> Dict[str, List[ValidationResult]]:
        """
        Valide une liste d'entités en lot.
        
        Args:
            entities: Liste d'entités à valider
            
        Returns:
            Dictionnaire des résultats par type d'entité
        """
        results = {
            'tracks': [],
            'artists': [],
            'credits': [],
            'albums': []
        }
        
        for entity in entities:
            try:
                if isinstance(entity, Track):
                    results['tracks'].append(self.validate_track(entity))
                elif isinstance(entity, Artist):
                    results['artists'].append(self.validate_artist(entity))
                elif isinstance(entity, Credit):
                    results['credits'].append(self.validate_credit(entity))
                elif isinstance(entity, Album):
                    # Note: validate_album à implémenter si nécessaire
                    pass
                    
            except Exception as e:
                self.logger.error(f"Erreur validation entité {type(entity).__name__}: {e}")
        
        return results
    
    def generate_quality_report(self, validation_results: List[ValidationResult]) -> QualityReport:
        """
        Génère un rapport de qualité basé sur les résultats de validation.
        
        Args:
            validation_results: Liste des résultats de validation
            
        Returns:
            QualityReport: Rapport de qualité complet
        """
        if not validation_results:
            return QualityReport()
        
        # Calcul des statistiques globales
        total_entities = len(validation_results)
        valid_entities = sum(1 for r in validation_results if r.is_valid)
        average_score = sum(r.quality_score for r in validation_results) / total_entities
        
        # Analyse des problèmes par catégorie
        issue_categories = {}
        for result in validation_results:
            for issue in result.issues:
                if issue.category not in issue_categories:
                    issue_categories[issue.category] = {
                        'count': 0,
                        'severity': issue.type.value,
                        'examples': []
                    }
                issue_categories[issue.category]['count'] += 1
                if len(issue_categories[issue.category]['examples']) < 3:
                    issue_categories[issue.category]['examples'].append(issue.message)
        
        # Distribution des scores
        score_ranges = {'0-50': 0, '50-70': 0, '70-85': 0, '85-95': 0, '95-100': 0}
        for result in validation_results:
            score = result.quality_score
            if score < 50:
                score_ranges['0-50'] += 1
            elif score < 70:
                score_ranges['50-70'] += 1
            elif score < 85:
                score_ranges['70-85'] += 1
            elif score < 95:
                score_ranges['85-95'] += 1
            else:
                score_ranges['95-100'] += 1
        
        score_distribution = {k: (v / total_entities) * 100 for k, v in score_ranges.items()}
        
        # Top 5 des problèmes les plus fréquents
        top_issues = sorted(
            issue_categories.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )[:5]
        
        return {
            'total_entities': total_entities,
            'valid_entities': valid_entities,
            'validation_rate': (valid_entities / total_entities) * 100,
            'average_quality_score': round(average_score, 2),
            'quality_distribution': {
                'excellent': len([r for r in validation_results if r.quality_level == QualityLevel.EXCELLENT]),
                'good': len([r for r in validation_results if r.quality_level == QualityLevel.GOOD]),
                'average': len([r for r in validation_results if r.quality_level == QualityLevel.AVERAGE]),
                'poor': len([r for r in validation_results if r.quality_level == QualityLevel.POOR]),
                'very_poor': len([r for r in validation_results if r.quality_level == QualityLevel.VERY_POOR])
            },
            'issue_categories': {
                category: data for category, data in issue_categories.items()
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
    
    def get_session_stats(self) -> ValidationStats:
        """Retourne les statistiques de la session actuelle"""
        if self.session_stats.total_validated > 0:
            self.session_stats.average_quality_score = (
                self.session_stats.valid_entities / self.session_stats.total_validated
            ) * 100
        
        return self.session_stats
    
    def clear_cache(self):
        """Vide le cache de validation"""
        self._cache.clear()
        self.logger.info("Cache de validation vidé")
    
    def health_check(self) -> Dict[str, Any]:
        """Effectue un diagnostic de santé du validateur"""
        return {
            'validation_level': self.validation_level.value,
            'cache_size': len(self._cache),
            'patterns_compiled': len(self.validation_patterns),
            'session_stats': {
                'total_validated': self.session_stats.total_validated,
                'success_rate': (
                    self.session_stats.valid_entities / max(self.session_stats.total_validated, 1)
                ) * 100
            },
            'config': self.config,
            'status': 'healthy'
        }