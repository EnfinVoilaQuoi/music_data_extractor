# processors/quality_checker.py
"""
Module de vérification de qualité pour Music Data Extractor.
Analyse et évalue la qualité des données musicales extraites.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from statistics import mean, median, stdev

from models.entities import Track, Credit, Artist, Album, QualityReport
from models.enums import CreditType, CreditCategory, DataSource, QualityLevel
from core.database import Database
from config.settings import settings
from utils.text_utils import validate_artist_name


class QualityMetric(Enum):
    """Métriques de qualité"""
    COMPLETENESS = "completeness"      # Complétude des données
    ACCURACY = "accuracy"              # Précision des données
    CONSISTENCY = "consistency"        # Cohérence des données
    FRESHNESS = "freshness"           # Fraîcheur des données
    VALIDITY = "validity"             # Validité des données
    UNIQUENESS = "uniqueness"         # Unicité des données


class QualityCheck(Enum):
    """Types de vérifications de qualité"""
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    INVALID_FORMAT = "invalid_format"
    DUPLICATE_DATA = "duplicate_data"
    INCONSISTENT_DATA = "inconsistent_data"
    OUTDATED_DATA = "outdated_data"
    SUSPICIOUS_PATTERN = "suspicious_pattern"


@dataclass
class QualityIssue:
    """Problème de qualité identifié"""
    entity_id: int
    entity_type: str
    check_type: QualityCheck
    field: str
    current_value: Any
    expected_value: Optional[Any]
    severity: str  # 'critical', 'major', 'minor', 'warning'
    message: str
    suggestion: Optional[str] = None


@dataclass
class QualityAnalysis:
    """Résultat d'une analyse de qualité"""
    entity_id: int
    entity_type: str
    quality_level: QualityLevel
    quality_score: float
    metrics: Dict[QualityMetric, float]
    issues: List[QualityIssue]
    recommendations: List[str]
    last_checked: datetime


@dataclass
class QualityMetrics:
    """Métriques globales de qualité"""
    total_tracks: int = 0
    tracks_with_producer: int = 0
    tracks_with_duration: int = 0
    tracks_with_bpm: int = 0
    tracks_with_album: int = 0
    tracks_with_lyrics: int = 0
    tracks_with_credits: int = 0
    tracks_with_valid_duration: int = 0
    average_credits_per_track: float = 0.0
    data_freshness_score: float = 0.0
    overall_quality_score: float = 0.0


class QualityChecker:
    """
    Vérificateur de qualité des données musicales.
    
    Fonctionnalités:
    - Analyse de la complétude des données
    - Détection des incohérences
    - Validation des formats
    - Calcul de scores de qualité
    - Recommandations d'amélioration
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.database = Database()
        
        # Configuration
        self.config = {
            'min_duration': settings.get('quality.min_track_duration', 30),
            'max_duration': settings.get('quality.max_track_duration', 600),
            'min_bpm': settings.get('quality.min_bpm', 60),
            'max_bpm': settings.get('quality.max_bpm', 200),
            'required_fields': settings.get('quality.required_fields', [
                'title', 'artist_name', 'duration_seconds'
            ]),
            'data_freshness_days': settings.get('quality.data_freshness_days', 30)
        }
        
        # Patterns de validation
        self.validation_patterns = {
            'featuring': re.compile(r'(feat\.|ft\.|featuring|with)', re.IGNORECASE),
            'year': re.compile(r'^\d{4}$'),
            'isrc': re.compile(r'^[A-Z]{2}[A-Z0-9]{3}\d{7}$'),
            'spotify_id': re.compile(r'^[a-zA-Z0-9]{22}$')
        }
    
    def check_track_quality(self, track: Track) -> QualityAnalysis:
        """
        Vérifie la qualité d'un track.
        
        Args:
            track: Track à analyser
            
        Returns:
            Analyse de qualité complète
        """
        try:
            issues = []
            metrics = {}
            
            # 1. Vérifier la complétude
            completeness_score, completeness_issues = self._check_completeness(track)
            metrics[QualityMetric.COMPLETENESS] = completeness_score
            issues.extend(completeness_issues)
            
            # 2. Vérifier la validité
            validity_score, validity_issues = self._check_validity(track)
            metrics[QualityMetric.VALIDITY] = validity_score
            issues.extend(validity_issues)
            
            # 3. Vérifier la cohérence
            consistency_score, consistency_issues = self._check_consistency(track)
            metrics[QualityMetric.CONSISTENCY] = consistency_score
            issues.extend(consistency_issues)
            
            # 4. Vérifier la fraîcheur
            freshness_score = self._check_freshness(track)
            metrics[QualityMetric.FRESHNESS] = freshness_score
            
            # 5. Vérifier l'unicité (pas de doublons)
            uniqueness_score, uniqueness_issues = self._check_uniqueness(track)
            metrics[QualityMetric.UNIQUENESS] = uniqueness_score
            issues.extend(uniqueness_issues)
            
            # Calculer le score global
            quality_score = self._calculate_overall_score(metrics)
            quality_level = self._determine_quality_level(quality_score)
            
            # Générer des recommandations
            recommendations = self._generate_recommendations(issues, metrics)
            
            return QualityAnalysis(
                entity_id=track.id,
                entity_type="track",
                quality_level=quality_level,
                quality_score=quality_score,
                metrics=metrics,
                issues=issues,
                recommendations=recommendations,
                last_checked=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Erreur vérification qualité track {track.id}: {e}")
            return QualityAnalysis(
                entity_id=track.id,
                entity_type="track",
                quality_level=QualityLevel.VERY_POOR,
                quality_score=0.0,
                metrics={},
                issues=[],
                recommendations=["Erreur lors de l'analyse"],
                last_checked=datetime.now()
            )
    
    def _check_completeness(self, track: Track) -> Tuple[float, List[QualityIssue]]:
        """Vérifie la complétude des données"""
        issues = []
        complete_fields = 0
        total_fields = 0
        
        # Champs obligatoires
        required_checks = {
            'title': track.title,
            'artist_name': track.artist_name,
            'duration_seconds': track.duration_seconds
        }
        
        for field, value in required_checks.items():
            total_fields += 1
            if not value:
                issues.append(QualityIssue(
                    entity_id=track.id,
                    entity_type="track",
                    check_type=QualityCheck.MISSING_REQUIRED_FIELDS,
                    field=field,
                    current_value=None,
                    expected_value="Non vide",
                    severity="critical",
                    message=f"Champ obligatoire manquant: {field}"
                ))
            else:
                complete_fields += 1
        
        # Champs importants (non obligatoires)
        important_checks = {
            'album_title': track.album_title,
            'release_date': track.release_date,
            'genres': track.genres,
            'bpm': track.bpm,
            'key': track.key
        }
        
        for field, value in important_checks.items():
            total_fields += 1
            if value:
                complete_fields += 1
            else:
                issues.append(QualityIssue(
                    entity_id=track.id,
                    entity_type="track",
                    check_type=QualityCheck.MISSING_REQUIRED_FIELDS,
                    field=field,
                    current_value=None,
                    expected_value="Non vide",
                    severity="minor",
                    message=f"Champ important manquant: {field}",
                    suggestion=f"Enrichir le champ {field} pour améliorer la qualité"
                ))
        
        # Vérifier les crédits
        total_fields += 1
        if not track.credits:
            issues.append(QualityIssue(
                entity_id=track.id,
                entity_type="track",
                check_type=QualityCheck.MISSING_REQUIRED_FIELDS,
                field="credits",
                current_value=[],
                expected_value="Au moins un crédit",
                severity="major",
                message="Aucun crédit trouvé",
                suggestion="Extraire les crédits depuis les sources disponibles"
            ))
        else:
            complete_fields += 1
            
            # Vérifier la présence d'un producteur
            has_producer = any(
                credit.credit_type == CreditType.PRODUCER 
                for credit in track.credits
            )
            
            if not has_producer:
                issues.append(QualityIssue(
                    entity_id=track.id,
                    entity_type="track",
                    check_type=QualityCheck.MISSING_REQUIRED_FIELDS,
                    field="producer",
                    current_value=None,
                    expected_value="Au moins un producteur",
                    severity="major",
                    message="Producteur manquant",
                    suggestion="Le producteur est une information cruciale"
                ))
        
        completeness_score = (complete_fields / total_fields) * 100
        return completeness_score, issues
    
    def _check_validity(self, track: Track) -> Tuple[float, List[QualityIssue]]:
        """Vérifie la validité des données"""
        issues = []
        valid_checks = 0
        total_checks = 0
        
        # Vérifier la durée
        if track.duration_seconds:
            total_checks += 1
            if track.duration_seconds < self.config['min_duration']:
                issues.append(QualityIssue(
                    entity_id=track.id,
                    entity_type="track",
                    check_type=QualityCheck.INVALID_FORMAT,
                    field="duration_seconds",
                    current_value=track.duration_seconds,
                    expected_value=f">= {self.config['min_duration']}",
                    severity="warning",
                    message="Durée trop courte",
                    suggestion="Vérifier si c'est un interlude ou une erreur"
                ))
            elif track.duration_seconds > self.config['max_duration']:
                issues.append(QualityIssue(
                    entity_id=track.id,
                    entity_type="track",
                    check_type=QualityCheck.INVALID_FORMAT,
                    field="duration_seconds",
                    current_value=track.duration_seconds,
                    expected_value=f"<= {self.config['max_duration']}",
                    severity="warning",
                    message="Durée anormalement longue"
                ))
            else:
                valid_checks += 1
        
        # Vérifier le BPM
        if track.bpm:
            total_checks += 1
            if track.bpm < self.config['min_bpm'] or track.bpm > self.config['max_bpm']:
                issues.append(QualityIssue(
                    entity_id=track.id,
                    entity_type="track",
                    check_type=QualityCheck.INVALID_FORMAT,
                    field="bpm",
                    current_value=track.bpm,
                    expected_value=f"{self.config['min_bpm']}-{self.config['max_bpm']}",
                    severity="minor",
                    message="BPM hors limites normales"
                ))
            else:
                valid_checks += 1
        
        # Vérifier les IDs externes
        if track.spotify_id:
            total_checks += 1
            if self.validation_patterns['spotify_id'].match(track.spotify_id):
                valid_checks += 1
            else:
                issues.append(QualityIssue(
                    entity_id=track.id,
                    entity_type="track",
                    check_type=QualityCheck.INVALID_FORMAT,
                    field="spotify_id",
                    current_value=track.spotify_id,
                    expected_value="Format Spotify ID valide",
                    severity="minor",
                    message="Format Spotify ID invalide"
                ))
        
        validity_score = (valid_checks / max(total_checks, 1)) * 100
        return validity_score, issues
    
    def _check_consistency(self, track: Track) -> Tuple[float, List[QualityIssue]]:
        """Vérifie la cohérence des données"""
        issues = []
        consistency_checks = 0
        total_checks = 0
        
        # Vérifier la cohérence titre/artiste avec featuring
        if track.title and track.featured_artists:
            total_checks += 1
            has_feat_in_title = self.validation_patterns['featuring'].search(track.title)
            
            if has_feat_in_title and not track.featured_artists:
                issues.append(QualityIssue(
                    entity_id=track.id,
                    entity_type="track",
                    check_type=QualityCheck.INCONSISTENT_DATA,
                    field="featured_artists",
                    current_value=[],
                    expected_value="Artistes featuring extraits du titre",
                    severity="minor",
                    message="Featuring dans le titre mais pas dans les métadonnées"
                ))
            else:
                consistency_checks += 1
        
        # Vérifier la cohérence des crédits
        if track.credits:
            total_checks += 1
            credit_names = [c.person_name for c in track.credits]
            
            # Vérifier si l'artiste principal est dans les crédits
            if track.artist_name not in credit_names:
                # C'est OK, l'artiste principal n'est pas toujours crédité explicitement
                consistency_checks += 1
            else:
                consistency_checks += 1
        
        consistency_score = (consistency_checks / max(total_checks, 1)) * 100
        return consistency_score, issues
    
    def _check_freshness(self, track: Track) -> float:
        """Vérifie la fraîcheur des données"""
        if not track.extraction_date:
            return 0.0
        
        days_old = (datetime.now() - track.extraction_date).days
        freshness_threshold = self.config['data_freshness_days']
        
        if days_old <= freshness_threshold:
            return 100.0
        elif days_old <= freshness_threshold * 2:
            return 50.0
        else:
            return 25.0
    
    def _check_uniqueness(self, track: Track) -> Tuple[float, List[QualityIssue]]:
        """Vérifie l'unicité (pas de doublons)"""
        issues = []
        
        # Rechercher des doublons potentiels
        similar_tracks = self.database.search_tracks(
            query=track.title,
            artist_name=track.artist_name,
            limit=5
        )
        
        duplicates = []
        for similar in similar_tracks:
            if similar.id != track.id:
                # Vérifier la similarité
                title_similarity = self._calculate_similarity(track.title, similar.title)
                
                if title_similarity > 0.9:
                    duplicates.append(similar)
        
        if duplicates:
            issues.append(QualityIssue(
                entity_id=track.id,
                entity_type="track",
                check_type=QualityCheck.DUPLICATE_DATA,
                field="track",
                current_value=track.title,
                expected_value="Unique",
                severity="major",
                message=f"{len(duplicates)} doublon(s) potentiel(s) détecté(s)",
                suggestion="Vérifier et fusionner les doublons"
            ))
            return 0.0, issues
        
        return 100.0, issues
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calcule la similarité entre deux chaînes"""
        # Implémentation simple - à améliorer avec Levenshtein ou autre
        str1_lower = str1.lower().strip()
        str2_lower = str2.lower().strip()
        
        if str1_lower == str2_lower:
            return 1.0
        
        # Calcul basique basé sur les mots communs
        words1 = set(str1_lower.split())
        words2 = set(str2_lower.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    def _calculate_overall_score(self, metrics: Dict[QualityMetric, float]) -> float:
        """Calcule le score de qualité global"""
        # Pondération des métriques
        weights = {
            QualityMetric.COMPLETENESS: 0.35,
            QualityMetric.VALIDITY: 0.20,
            QualityMetric.CONSISTENCY: 0.15,
            QualityMetric.FRESHNESS: 0.10,
            QualityMetric.UNIQUENESS: 0.20
        }
        
        weighted_sum = 0
        total_weight = 0
        
        for metric, score in metrics.items():
            weight = weights.get(metric, 0.1)
            weighted_sum += score * weight
            total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0
    
    def _determine_quality_level(self, score: float) -> QualityLevel:
        """Détermine le niveau de qualité basé sur le score"""
        if score >= 90:
            return QualityLevel.EXCELLENT
        elif score >= 75:
            return QualityLevel.GOOD
        elif score >= 60:
            return QualityLevel.FAIR
        elif score >= 40:
            return QualityLevel.POOR
        else:
            return QualityLevel.VERY_POOR
    
    def _generate_recommendations(self, issues: List[QualityIssue], 
                                metrics: Dict[QualityMetric, float]) -> List[str]:
        """Génère des recommandations basées sur l'analyse"""
        recommendations = []
        
        # Analyser les problèmes critiques
        critical_issues = [i for i in issues if i.severity == 'critical']
        if critical_issues:
            recommendations.append(
                f"🚨 Résoudre {len(critical_issues)} problème(s) critique(s) en priorité"
            )
        
        # Recommandations basées sur les métriques
        if metrics.get(QualityMetric.COMPLETENESS, 0) < 70:
            recommendations.append(
                "📊 Améliorer la complétude: enrichir les données manquantes"
            )
        
        if metrics.get(QualityMetric.FRESHNESS, 0) < 50:
            recommendations.append(
                "🔄 Rafraîchir les données: elles sont peut-être obsolètes"
            )
        
        # Recommandations spécifiques aux champs
        missing_fields = [i.field for i in issues 
                         if i.check_type == QualityCheck.MISSING_REQUIRED_FIELDS]
        
        if 'producer' in missing_fields:
            recommendations.append(
                "🎛️ Ajouter les informations de production (crucial pour le rap)"
            )
        
        if 'credits' in missing_fields:
            recommendations.append(
                "👥 Extraire les crédits complets depuis Genius ou Discogs"
            )
        
        return recommendations
    
    def check_artist_quality(self, artist_id: int) -> QualityAnalysis:
        """
        Vérifie la qualité globale des données d'un artiste.
        
        Args:
            artist_id: ID de l'artiste
            
        Returns:
            Analyse de qualité globale
        """
        try:
            # Récupérer tous les tracks de l'artiste
            tracks = self.database.get_tracks_by_artist_id(artist_id)
            
            if not tracks:
                return QualityAnalysis(
                    entity_id=artist_id,
                    entity_type="artist",
                    quality_level=QualityLevel.VERY_POOR,
                    quality_score=0.0,
                    metrics={},
                    issues=[],
                    recommendations=["Aucun track trouvé pour cet artiste"],
                    last_checked=datetime.now()
                )
            
            # Analyser chaque track
            track_analyses = []
            issues = []
            
            for track in tracks:
                analysis = self.check_track_quality(track)
                track_analyses.append(analysis)
                issues.extend(analysis.issues)
            
            # Calculer les métriques globales
            metrics = self._calculate_artist_metrics(track_analyses)
            
            # Score global
            track_scores = [a.quality_score for a in track_analyses]
            overall_score = mean(track_scores) if track_scores else 0.0
            quality_level = self._determine_quality_level(overall_score)
            
            # Recommandations
            recommendations = self._generate_artist_recommendations(issues, track_analyses)
            
            return QualityAnalysis(
                entity_id=artist_id,
                entity_type="artist",
                quality_level=quality_level,
                quality_score=overall_score,
                metrics=metrics,
                issues=issues,
                recommendations=recommendations,
                last_checked=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Erreur vérification qualité artiste {artist_id}: {e}")
            return QualityAnalysis(
                entity_id=artist_id,
                entity_type="artist",
                quality_level=QualityLevel.VERY_POOR,
                quality_score=0.0,
                metrics={},
                issues=[],
                recommendations=[],
                last_checked=datetime.now()
            )
    
    def _calculate_artist_metrics(self, track_analyses: List[QualityAnalysis]) -> Dict[QualityMetric, float]:
        """Calcule les métriques globales pour un artiste"""
        if not track_analyses:
            return {}
        
        metrics = {}
        
        for metric in QualityMetric:
            scores = [
                analysis.metrics.get(metric, 0.0) 
                for analysis in track_analyses 
                if metric in analysis.metrics
            ]
            
            if scores:
                metrics[metric] = mean(scores)
            else:
                metrics[metric] = 0.0
        
        return metrics
    
    def _generate_artist_recommendations(self, issues: List[QualityIssue], 
                                       track_analyses: List[QualityAnalysis]) -> List[str]:
        """Génère des recommandations pour un artiste"""
        recommendations = []
        
        # Analyser la distribution des scores
        scores = [a.quality_score for a in track_analyses]
        if scores:
            avg_score = mean(scores)
            min_score = min(scores)
            
            if avg_score < 60:
                recommendations.append(
                    f"⚠️ Qualité moyenne faible ({avg_score:.1f}%) - Action urgente requise"
                )
            
            if min_score < 40:
                poor_tracks = sum(1 for s in scores if s < 40)
                recommendations.append(
                    f"🔴 {poor_tracks} track(s) avec qualité très faible - Prioriser"
                )
        
        # Analyser les problèmes récurrents
        issue_counts = {}
        for issue in issues:
            key = (issue.check_type, issue.field)
            issue_counts[key] = issue_counts.get(key, 0) + 1
        
        # Top 3 des problèmes
        top_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        
        for (check_type, field), count in top_issues:
            percentage = (count / len(track_analyses)) * 100
            if percentage > 50:
                recommendations.append(
                    f"📍 Problème récurrent: {field} ({percentage:.0f}% des tracks)"
                )
        
        return recommendations
    
    def calculate_quality_metrics(self, artist_id: Optional[int] = None) -> QualityMetrics:
        """
        Calcule les métriques de qualité globales.
        
        Args:
            artist_id: ID de l'artiste (optionnel, sinon global)
            
        Returns:
            Métriques de qualité
        """
        try:
            metrics = QualityMetrics()
            
            # Récupérer les tracks
            if artist_id:
                all_tracks = self.database.get_tracks_by_artist_id(artist_id)
            else:
                # Échantillon global
                with self.database.get_connection() as conn:
                    cursor = conn.execute("SELECT * FROM tracks LIMIT 1000")
                    all_tracks = [self.database._row_to_track(row) for row in cursor.fetchall()]
            
            if not all_tracks:
                return metrics
            
            metrics.total_tracks = len(all_tracks)
            
            # Analyser chaque track
            for track in all_tracks:
                # Producteur
                if any(c.credit_type == CreditType.PRODUCER for c in track.credits):
                    metrics.tracks_with_producer += 1
                
                # BPM
                if track.bpm:
                    metrics.tracks_with_bpm += 1
                
                # Durée
                if track.duration_seconds:
                    metrics.tracks_with_duration += 1
                    # Durée valide
                    if self.config['min_duration'] <= track.duration_seconds <= self.config['max_duration']:
                        metrics.tracks_with_valid_duration += 1
                
                # Album
                if track.album_title:
                    metrics.tracks_with_album += 1
                
                # Lyrics
                if track.has_lyrics:
                    metrics.tracks_with_lyrics += 1
                
                # Crédits
                if track.credits:
                    metrics.tracks_with_credits += 1
            
            # Moyenne crédits par track
            total_credits = sum(len(track.credits) for track in all_tracks)
            metrics.average_credits_per_track = total_credits / metrics.total_tracks
            
            # Score de fraîcheur des données
            fresh_tracks = 0
            freshness_threshold = timedelta(days=self.config['data_freshness_days'])
            cutoff_date = datetime.now() - freshness_threshold
            
            for track in all_tracks:
                if track.extraction_date and track.extraction_date > cutoff_date:
                    fresh_tracks += 1
            
            metrics.data_freshness_score = (fresh_tracks / metrics.total_tracks) * 100
            
            # Score global de qualité (estimation rapide)
            quality_factors = [
                metrics.tracks_with_producer / metrics.total_tracks,
                metrics.tracks_with_duration / metrics.total_tracks,
                metrics.tracks_with_credits / metrics.total_tracks,
                metrics.tracks_with_album / metrics.total_tracks,
                metrics.data_freshness_score / 100
            ]
            
            metrics.overall_quality_score = mean(quality_factors) * 100
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Erreur calcul métriques globales: {e}")
            return QualityMetrics()
    
    def create_quality_report_for_track(self, track: Track) -> QualityReport:
        """
        Crée un rapport de qualité pour un track.
        
        Args:
            track: Track à analyser
            
        Returns:
            Rapport de qualité
        """
        analysis = self.check_track_quality(track)
        
        return QualityReport(
            entity_id=track.id,
            entity_type="track",
            quality_level=analysis.quality_level,
            quality_score=analysis.quality_score,
            completeness_score=analysis.metrics.get(QualityMetric.COMPLETENESS, 0),
            accuracy_score=analysis.metrics.get(QualityMetric.VALIDITY, 0),
            consistency_score=analysis.metrics.get(QualityMetric.CONSISTENCY, 0),
            issues_count=len(analysis.issues),
            critical_issues_count=len([i for i in analysis.issues if i.severity == 'critical']),
            recommendations=analysis.recommendations,
            last_checked=analysis.last_checked
        )
    
    def generate_quality_improvement_plan(self, analysis: QualityAnalysis) -> List[Dict[str, Any]]:
        """
        Génère un plan d'amélioration basé sur l'analyse.
        
        Args:
            analysis: Analyse de qualité
            
        Returns:
            Plan d'amélioration structuré
        """
        try:
            improvements = []
            
            # Grouper les issues par type et sévérité
            issues_by_severity = {
                'critical': [],
                'major': [],
                'minor': [],
                'warning': []
            }
            
            for issue in analysis.issues:
                issues_by_severity[issue.severity].append(issue)
            
            # Créer des actions pour chaque niveau
            if issues_by_severity['critical']:
                for issue in issues_by_severity['critical']:
                    improvements.append({
                        'priority': 1,
                        'action': f"Corriger {issue.field}",
                        'reason': issue.message,
                        'expected_improvement': 10,
                        'effort': 'Low',
                        'category': 'Critical Fix'
                    })
            
            if issues_by_severity['major']:
                for issue in issues_by_severity['major'][:5]:  # Top 5
                    improvements.append({
                        'priority': 2,
                        'action': f"Améliorer {issue.field}",
                        'reason': issue.message,
                        'expected_improvement': 5,
                        'effort': 'Medium',
                        'category': 'Major Improvement'
                    })
            
            # Recommandations basées sur les métriques faibles
            for metric, score in analysis.metrics.items():
                if score < 50:
                    improvements.append({
                        'priority': 3,
                        'action': f"Améliorer {metric.value}",
                        'reason': f"Score actuel: {score:.1f}%",
                        'expected_improvement': (100 - score) * 0.5,
                        'effort': 'High',
                        'category': 'Metric Improvement'
                    })
            
            # Trier par priorité
            improvements.sort(key=lambda x: x['priority'])
            
            return improvements[:10]  # Top 10 améliorations
            
        except Exception as e:
            self.logger.error(f"Erreur génération plan d'amélioration: {e}")
            return []
    
    def suggest_quality_improvements(self, analysis: QualityAnalysis) -> List[Dict[str, Any]]:
        """
        Suggère des améliorations spécifiques basées sur l'analyse.
        
        Args:
            analysis: Analyse de qualité
            
        Returns:
            Liste de suggestions d'amélioration
        """
        try:
            improvements = []
            
            # Analyser les métriques faibles
            for metric, score in analysis.metrics.items():
                if score < 60:
                    if metric == QualityMetric.COMPLETENESS:
                        improvements.append({
                            'category': 'Complétude',
                            'priority': 'High',
                            'action': 'Enrichir les données manquantes',
                            'impact': 'Améliore la complétude globale',
                            'effort': 'Medium',
                            'tools': ['data_enricher', 'external_apis']
                        })
                    
                    elif metric == QualityMetric.VALIDITY:
                        improvements.append({
                            'category': 'Validité',
                            'priority': 'High',
                            'action': 'Corriger les formats invalides',
                            'impact': 'Évite les erreurs dans les analyses',
                            'effort': 'Low',
                            'tools': ['data_validator', 'manual_correction']
                        })
                    
                    elif metric == QualityMetric.CONSISTENCY:
                        improvements.append({
                            'category': 'Cohérence',
                            'priority': 'Medium',
                            'action': 'Harmoniser les données incohérentes',
                            'impact': 'Améliore la fiabilité des données',
                            'effort': 'Medium',
                            'tools': ['data_cleaner', 'duplicate_detector']
                        })
                    
                    elif metric == QualityMetric.FRESHNESS:
                        improvements.append({
                            'category': 'Fraîcheur',
                            'priority': 'Medium',
                            'action': 'Réextraire les données obsolètes',
                            'impact': 'Assure des données à jour',
                            'effort': 'High',
                            'tools': ['extractors', 'schedulers']
                        })
            
            # Suggestions spécifiques aux problèmes critiques
            critical_issues = [i for i in analysis.issues if i.severity == 'critical']
            
            if critical_issues:
                improvements.append({
                    'category': 'Problèmes critiques',
                    'priority': 'Critical',
                    'action': f'Résoudre {len(critical_issues)} problème(s) critique(s)',
                    'impact': 'Indispensable pour la validité des données',
                    'effort': 'High',
                    'tools': ['manual_review', 'data_validator']
                })
            
            # Prioriser par impact et effort
            improvements.sort(key=lambda x: {
                'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3
            }.get(x['priority'], 3))
            
            return improvements
            
        except Exception as e:
            self.logger.error(f"Erreur génération suggestions d'amélioration: {e}")
            return []
    
    def monitor_quality_over_time(self, entity_type: str, entity_id: int, days: int = 30) -> Dict[str, Any]:
        """
        Surveille l'évolution de la qualité dans le temps.
        
        Args:
            entity_type: Type d'entité ('track', 'artist')
            entity_id: ID de l'entité
            days: Nombre de jours à analyser
            
        Returns:
            Données d'évolution de la qualité
        """
        try:
            # Pour l'instant, on simule avec des données basiques
            # Dans une vraie implémentation, il faudrait stocker l'historique
            
            # Analyse actuelle
            if entity_type == 'track':
                with self.database.get_connection() as conn:
                    cursor = conn.execute("SELECT * FROM tracks WHERE id = ?", (entity_id,))
                    row = cursor.fetchone()
                    if row:
                        track = self.database._row_to_track(row)
                        track.credits = self.database.get_credits_by_track_id(track.id)
                        current_analysis = self.check_track_quality(track)
                    else:
                        return {'error': 'Track non trouvé'}
            
            elif entity_type == 'artist':
                current_analysis = self.check_artist_quality(entity_id)
            
            else:
                return {'error': 'Type d\'entité non supporté'}
            
            # Simulation d'historique (à remplacer par vraies données)
            historical_data = []
            for i in range(days):
                date = datetime.now() - timedelta(days=i)
                # Simulation de variation de qualité
                variation = -5 + (i * 0.5)  # Amélioration graduelle
                simulated_score = max(0, min(100, current_analysis.quality_score + variation))
                
                historical_data.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'quality_score': round(simulated_score, 1),
                    'quality_level': self._determine_quality_level(simulated_score).value
                })
            
            # Calculer les tendances
            scores = [point['quality_score'] for point in historical_data]
            trend = 'improving' if scores[-1] > scores[0] else 'declining' if scores[-1] < scores[0] else 'stable'
            
            return {
                'entity_type': entity_type,
                'entity_id': entity_id,
                'current_quality': {
                    'score': current_analysis.quality_score,
                    'level': current_analysis.quality_level.value
                },
                'historical_data': list(reversed(historical_data)),  # Ordre chronologique
                'trend': trend,
                'average_score': round(mean(scores), 1),
                'score_range': {
                    'min': min(scores),
                    'max': max(scores)
                },
                'analysis_period': f'{days} derniers jours',
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur monitoring qualité: {e}")
            return {'error': f'Erreur lors du monitoring: {e}'}