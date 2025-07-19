import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from statistics import mean, median, stdev

from ..models.entities import Track, Credit, Artist, Album, QualityReport
from ..models.enums import CreditType, CreditCategory, DataSource, QualityLevel
from ..core.database import Database
from ..config.settings import settings
from ..utils.text_utils import validate_artist_name

class QualityMetric(Enum):
    """Métriques de qualité"""
    COMPLETENESS = "completeness"        # Complétude des données
    ACCURACY = "accuracy"               # Précision des données
    CONSISTENCY = "consistency"         # Cohérence des données
    FRESHNESS = "freshness"            # Fraîcheur des données
    VALIDITY = "validity"              # Validité des données
    UNIQUENESS = "uniqueness"          # Unicité des données

class QualityCheck(Enum):
    """Types de vérifications de qualité"""
    MISSING_PRODUCER = "missing_producer"
    MISSING_BPM = "missing_bpm"
    MISSING_DURATION = "missing_duration"
    SUSPICIOUS_DURATION = "suspicious_duration"
    SUSPICIOUS_BPM = "suspicious_bpm"
    INVALID_ARTIST_NAME = "invalid_artist_name"
    MISSING_ALBUM = "missing_album"
    INCONSISTENT_ALBUM = "inconsistent_album"
    DUPLICATE_CREDITS = "duplicate_credits"
    EMPTY_CREDITS = "empty_credits"
    OUTDATED_DATA = "outdated_data"
    INVALID_EXTERNAL_IDS = "invalid_external_ids"
    INCONSISTENT_FEATURING = "inconsistent_featuring"

@dataclass
class QualityIssue:
    """Représente un problème de qualité"""
    check_type: QualityCheck
    metric: QualityMetric
    severity: str  # 'critical', 'major', 'minor', 'info'
    message: str
    field: Optional[str] = None
    value: Optional[Any] = None
    suggestion: Optional[str] = None
    confidence: float = 1.0

@dataclass
class QualityMetrics:
    """Métriques globales de qualité"""
    total_tracks: int = 0
    tracks_with_producer: int = 0
    tracks_with_bpm: int = 0
    tracks_with_duration: int = 0
    tracks_with_valid_duration: int = 0
    tracks_with_album: int = 0
    tracks_with_lyrics: int = 0
    tracks_with_credits: int = 0
    average_credits_per_track: float = 0.0
    data_freshness_score: float = 0.0
    overall_quality_score: float = 0.0

@dataclass
class QualityAnalysis:
    """Analyse complète de qualité"""
    entity_id: int
    entity_type: str
    quality_level: QualityLevel
    quality_score: float
    metrics: Dict[QualityMetric, float]
    issues: List[QualityIssue]
    recommendations: List[str]
    last_checked: datetime

class QualityChecker:
    """
    Vérificateur de qualité des données musicales.
    
    Responsabilités :
    - Évaluation de la qualité des données
    - Détection d'anomalies et d'incohérences
    - Calcul de métriques de qualité
    - Génération de rapports de qualité
    - Suggestions d'amélioration
    """
    
    def __init__(self, database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        self.database = database or Database()
        
        # Configuration des vérifications
        self.config = {
            'min_duration': settings.get('quality.min_duration_seconds', 30),
            'max_duration': settings.get('quality.max_duration_seconds', 1800),
            'min_bpm': settings.get('quality.min_bpm', 40),
            'max_bpm': settings.get('quality.max_bpm', 300),
            'require_producer': settings.get('quality.check_missing_producer', True),
            'require_bpm': settings.get('quality.check_missing_bpm', True),
            'data_freshness_days': settings.get('quality.freshness_threshold_days', 30),
            'min_credits_per_track': settings.get('quality.min_credits_per_track', 1),
            'suspicious_bpm_threshold': settings.get('quality.suspicious_bpm_threshold', 0.1)
        }
        
        # Seuils de qualité
        self.quality_thresholds = {
            QualityLevel.EXCELLENT: 90.0,
            QualityLevel.GOOD: 75.0,
            QualityLevel.AVERAGE: 50.0,
            QualityLevel.POOR: 25.0,
            QualityLevel.VERY_POOR: 0.0
        }
        
        self.logger.info("QualityChecker initialisé")
    
    def check_track_quality(self, track: Track) -> QualityAnalysis:
        """
        Vérifie la qualité d'un track.
        
        Args:
            track: Track à, track.spotify_id):
            issues.append(QualityIssue(
                check_type=QualityCheck.INVALID_EXTERNAL_IDS,
                metric=QualityMetric.VALIDITY,
                severity="minor",
                message="ID Spotify invalide",
                field="spotify_id",
                value=track.spotify_id,
                suggestion="Corriger l'ID Spotify"
            ))
            score -= 5
        
        return issues, max(score, 0.0)
    
    def _check_track_consistency(self, track: Track) -> Tuple[List[QualityIssue], float]:
        """Vérifie la cohérence des données d'un track"""
        issues = []
        score = 100.0
        
        # Cohérence album
        if track.album_id and not track.album_title:
            issues.append(QualityIssue(
                check_type=QualityCheck.INCONSISTENT_ALBUM,
                metric=QualityMetric.CONSISTENCY,
                severity="minor",
                message="ID album présent mais titre manquant",
                field="album_title",
                suggestion="Récupérer le titre de l'album"
            ))
            score -= 10
        elif track.album_title and not track.album_id:
            issues.append(QualityIssue(
                check_type=QualityCheck.INCONSISTENT_ALBUM,
                metric=QualityMetric.CONSISTENCY,
                severity="minor",
                message="Titre album présent mais ID manquant",
                field="album_id",
                suggestion="Lier le track à l'album correspondant"
            ))
            score -= 10
        
        # Cohérence featuring
        if track.featuring_artists:
            # Vérifier que l'artiste principal n'est pas dans les featuring
            for featuring in track.featuring_artists:
                if featuring.lower() == track.artist_name.lower():
                    issues.append(QualityIssue(
                        check_type=QualityCheck.INCONSISTENT_FEATURING,
                        metric=QualityMetric.CONSISTENCY,
                        severity="minor",
                        message=f"Artiste principal en featuring: '{featuring}'",
                        field="featuring_artists",
                        suggestion="Supprimer l'artiste principal des featuring"
                    ))
                    score -= 5
        
        # Vérifier doublons dans les crédits
        if track.credits:
            credit_keys = [(c.person_name.lower(), c.credit_type) for c in track.credits]
            if len(credit_keys) != len(set(credit_keys)):
                issues.append(QualityIssue(
                    check_type=QualityCheck.DUPLICATE_CREDITS,
                    metric=QualityMetric.CONSISTENCY,
                    severity="minor",
                    message="Crédits en double détectés",
                    field="credits",
                    suggestion="Supprimer les crédits en double"
                ))
                score -= 15
        
        # Cohérence durée/BPM (estimation grossière)
        if track.duration_seconds and track.bpm:
            estimated_beats = (track.duration_seconds / 60) * track.bpm
            if estimated_beats < 50 or estimated_beats > 1000:
                issues.append(QualityIssue(
                    check_type=QualityCheck.SUSPICIOUS_BPM,
                    metric=QualityMetric.CONSISTENCY,
                    severity="info",
                    message="Incohérence possible entre durée et BPM",
                    suggestion="Vérifier les valeurs de durée et BPM",
                    confidence=0.6
                ))
                score -= 5
        
        return issues, max(score, 0.0)
    
    def _check_track_accuracy(self, track: Track) -> Tuple[List[QualityIssue], float]:
        """Vérifie la précision des données d'un track"""
        issues = []
        score = 100.0
        
        # Vérifier la qualité des crédits
        if track.credits:
            empty_credits = [c for c in track.credits if not c.person_name or not c.person_name.strip()]
            if empty_credits:
                issues.append(QualityIssue(
                    check_type=QualityCheck.EMPTY_CREDITS,
                    metric=QualityMetric.ACCURACY,
                    severity="major",
                    message=f"{len(empty_credits)} crédit(s) avec nom vide",
                    field="credits",
                    suggestion="Supprimer ou corriger les crédits vides"
                ))
                score -= 20
            
            # Vérifier les crédits suspects
            suspicious_names = ['unknown', 'n/a', 'various', 'tba']
            suspicious_credits = [
                c for c in track.credits 
                if any(sus in c.person_name.lower() for sus in suspicious_names)
            ]
            if suspicious_credits:
                issues.append(QualityIssue(
                    check_type=QualityCheck.EMPTY_CREDITS,
                    metric=QualityMetric.ACCURACY,
                    severity="minor",
                    message=f"{len(suspicious_credits)} crédit(s) avec nom suspect",
                    field="credits",
                    suggestion="Vérifier et corriger les noms de créditeurs"
                ))
                score -= 10
        
        # Vérifier les sources de données
        if track.data_sources:
            # Bonus pour multiple sources (plus fiable)
            if len(track.data_sources) > 1:
                score += 5
            
            # Malus si seulement des sources peu fiables
            reliable_sources = [DataSource.GENIUS_API, DataSource.SPOTIFY, DataSource.DISCOGS]
            has_reliable = any(source in reliable_sources for source in track.data_sources)
            if not has_reliable:
                issues.append(QualityIssue(
                    check_type=QualityCheck.OUTDATED_DATA,
                    metric=QualityMetric.ACCURACY,
                    severity="info",
                    message="Aucune source fiable identifiée",
                    suggestion="Valider avec des sources de référence"
                ))
                score -= 10
        
        return issues, max(score, 0.0)
    
    def _check_track_freshness(self, track: Track) -> Tuple[List[QualityIssue], float]:
        """Vérifie la fraîcheur des données d'un track"""
        issues = []
        score = 100.0
        
        # Vérifier la date d'extraction
        if track.extraction_date:
            days_old = (datetime.now() - track.extraction_date).days
            freshness_threshold = self.config['data_freshness_days']
            
            if days_old > freshness_threshold:
                severity = "major" if days_old > freshness_threshold * 2 else "minor"
                issues.append(QualityIssue(
                    check_type=QualityCheck.OUTDATED_DATA,
                    metric=QualityMetric.FRESHNESS,
                    severity=severity,
                    message=f"Données extraites il y a {days_old} jours",
                    suggestion="Réextraire les données"
                ))
                # Score décroît avec l'âge
                score -= min(50, days_old / freshness_threshold * 30)
        else:
            issues.append(QualityIssue(
                check_type=QualityCheck.OUTDATED_DATA,
                metric=QualityMetric.FRESHNESS,
                severity="info",
                message="Date d'extraction inconnue",
                suggestion="Enregistrer la date d'extraction"
            ))
            score -= 20
        
        return issues, max(score, 0.0)
    
    def _check_track_uniqueness(self, track: Track) -> Tuple[List[QualityIssue], float]:
        """Vérifie l'unicité des données d'un track"""
        issues = []
        score = 100.0
        
        # Cette vérification nécessiterait d'interroger la base pour les doublons
        # Pour l'instant, on fait une vérification basique
        
        # Vérifier l'unicité des IDs externes
        if track.genius_id:
            try:
                with self.database.get_connection() as conn:
                    cursor = conn.execute(
                        "SELECT COUNT(*) as count FROM tracks WHERE genius_id = ? AND id != ?",
                        (track.genius_id, track.id or 0)
                    )
                    count = cursor.fetchone()['count']
                    
                    if count > 0:
                        issues.append(QualityIssue(
                            check_type=QualityCheck.DUPLICATE_CREDITS,  # Placeholder
                            metric=QualityMetric.UNIQUENESS,
                            severity="major",
                            message=f"ID Genius en double: {track.genius_id}",
                            field="genius_id",
                            suggestion="Vérifier et corriger les doublons"
                        ))
                        score -= 30
            except Exception as e:
                self.logger.warning(f"Erreur vérification unicité Genius ID: {e}")
        
        return issues, max(score, 0.0)
    
    def _calculate_overall_quality_score(self, metrics: Dict[QualityMetric, float], issues: List[QualityIssue]) -> float:
        """Calcule le score global de qualité"""
        if not metrics:
            return 0.0
        
        # Moyenne pondérée des métriques
        weights = {
            QualityMetric.COMPLETENESS: 0.25,
            QualityMetric.VALIDITY: 0.20,
            QualityMetric.CONSISTENCY: 0.20,
            QualityMetric.ACCURACY: 0.15,
            QualityMetric.FRESHNESS: 0.10,
            QualityMetric.UNIQUENESS: 0.10
        }
        
        weighted_score = 0.0
        total_weight = 0.0
        
        for metric, score in metrics.items():
            weight = weights.get(metric, 0.1)
            weighted_score += score * weight
            total_weight += weight
        
        if total_weight > 0:
            base_score = weighted_score / total_weight
        else:
            base_score = 50.0
        
        # Malus pour les problèmes critiques
        critical_issues = [i for i in issues if i.severity == "critical"]
        major_issues = [i for i in issues if i.severity == "major"]
        
        penalty = len(critical_issues) * 15 + len(major_issues) * 5
        
        return max(0.0, min(100.0, base_score - penalty))
    
    def _determine_quality_level(self, score: float) -> QualityLevel:
        """Détermine le niveau de qualité basé sur le score"""
        if score >= self.quality_thresholds[QualityLevel.EXCELLENT]:
            return QualityLevel.EXCELLENT
        elif score >= self.quality_thresholds[QualityLevel.GOOD]:
            return QualityLevel.GOOD
        elif score >= self.quality_thresholds[QualityLevel.AVERAGE]:
            return QualityLevel.AVERAGE
        elif score >= self.quality_thresholds[QualityLevel.POOR]:
            return QualityLevel.POOR
        else:
            return QualityLevel.VERY_POOR
    
    def _generate_track_recommendations(self, issues: List[QualityIssue]) -> List[str]:
        """Génère des recommandations d'amélioration"""
        recommendations = []
        
        # Prioriser par sévérité
        critical_issues = [i for i in issues if i.severity == "critical"]
        major_issues = [i for i in issues if i.severity == "major"]
        
        # Recommandations pour problèmes critiques
        if critical_issues:
            recommendations.append("URGENT: Corriger les problèmes critiques")
            for issue in critical_issues[:3]:  # Top 3
                if issue.suggestion:
                    recommendations.append(f"• {issue.suggestion}")
        
        # Recommandations pour problèmes majeurs
        if major_issues:
            recommendations.append("Corriger les problèmes majeurs")
            for issue in major_issues[:3]:  # Top 3
                if issue.suggestion:
                    recommendations.append(f"• {issue.suggestion}")
        
        # Recommandations générales
        issue_types = [i.check_type for i in issues]
        
        if QualityCheck.MISSING_PRODUCER in issue_types:
            recommendations.append("Améliorer l'extraction des crédits de production")
        
        if QualityCheck.MISSING_BPM in issue_types:
            recommendations.append("Compléter les données BPM manquantes")
        
        if QualityCheck.OUTDATED_DATA in issue_types:
            recommendations.append("Mettre à jour les données obsolètes")
        
        return recommendations
    
    def check_artist_quality(self, artist_id: int) -> QualityAnalysis:
        """
        Vérifie la qualité globale d'un artiste.
        
        Args:
            artist_id: ID de l'artiste
            
        Returns:
            QualityAnalysis: Analyse de qualité de l'artiste
        """
        try:
            tracks = self.database.get_tracks_by_artist_id(artist_id)
            artist = self.database.get_artist_by_name("placeholder")  # À améliorer
            
            if not tracks:
                return QualityAnalysis(
                    entity_id=artist_id,
                    entity_type="artist",
                    quality_level=QualityLevel.VERY_POOR,
                    quality_score=0.0,
                    metrics={},
                    issues=[QualityIssue(
                        check_type=QualityCheck.EMPTY_CREDITS,
                        metric=QualityMetric.COMPLETENESS,
                        severity="critical",
                        message="Aucun track trouvé pour cet artiste"
                    )],
                    recommendations=["Ajouter des tracks pour cet artiste"],
                    last_checked=datetime.now()
                )
            
            # Analyser tous les tracks
            track_analyses = [self.check_track_quality(track) for track in tracks]
            
            # Calculer les métriques globales
            metrics = self._calculate_artist_metrics(track_analyses)
            issues = self._aggregate_artist_issues(track_analyses)
            
            # Score global
            track_scores = [analysis.quality_score for analysis in track_analyses]
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
            metrics[metric] = mean(scores) if scores else 0.0
        
        return metrics
    
    def _aggregate_artist_issues(self, track_analyses: List[QualityAnalysis]) -> List[QualityIssue]:
        """Agrège les problèmes de tous les tracks d'un artiste"""
        issue_counts = {}
        
        for analysis in track_analyses:
            for issue in analysis.issues:
                key = (issue.check_type, issue.severity)
                if key not in issue_counts:
                    issue_counts[key] = {
                        'count': 0,
                        'example': issue
                    }
                issue_counts[key]['count'] += 1
        
        # Créer des issues agrégées
        aggregated_issues = []
        for (check_type, severity), data in issue_counts.items():
            if data['count'] > 1:
                aggregated_issues.append(QualityIssue(
                    check_type=check_type,
                    metric=data['example'].metric,
                    severity=severity,
                    message=f"{data['example'].message} ({data['count']} tracks affectés)",
                    suggestion=data['example'].suggestion
                ))
        
        return aggregated_issues
    
    def _generate_artist_recommendations(self, issues: List[QualityIssue], track_analyses: List[QualityAnalysis]) -> List[str]:
        """Génère des recommandations pour un artiste"""
        recommendations = []
        
        total_tracks = len(track_analyses)
        
        # Statistiques globales
        poor_quality_tracks = sum(1 for a in track_analyses if a.quality_level in [QualityLevel.POOR, QualityLevel.VERY_POOR])
        
        if poor_quality_tracks > total_tracks * 0.3:
            recommendations.append(f"PRIORITÉ: {poor_quality_tracks}/{total_tracks} tracks de mauvaise qualité")
        
        # Problèmes récurrents
        common_issues = {}
        for analysis in track_analyses:
            for issue in analysis.issues:
                common_issues[issue.check_type] = common_issues.get(issue.check_type, 0) + 1
        
        # Top 3 des problèmes les plus fréquents
        top_issues = sorted(common_issues.items(), key=lambda x: x[1], reverse=True)[:3]
        
        for issue_type, count in top_issues:
            if count > total_tracks * 0.2:  # Plus de 20% des tracks
                if issue_type == QualityCheck.MISSING_PRODUCER:
                    recommendations.append(f"Améliorer l'extraction des producteurs ({count} tracks)")
                elif issue_type == QualityCheck.MISSING_BPM:
                    recommendations.append(f"Compléter les BPM manquants ({count} tracks)")
                elif issue_type == QualityCheck.MISSING_DURATION:
                    recommendations.append(f"Ajouter les durées manquantes ({count} tracks)")
        
        return recommendations
    
    def generate_global_quality_metrics(self, artist_ids: Optional[List[int]] = None) -> QualityMetrics:
        """
        Génère des métriques globales de qualité.
        
        Args:
            artist_ids: Liste des artistes à analyser (None pour tous)
            
        Returns:
            QualityMetrics: Métriques globales
        """
        try:
            # Récupérer les tracks
            if artist_ids:
                all_tracks = []
                for artist_id in artist_ids:
                    tracks = self.database.get_tracks_by_artist_id(artist_id)
                    all_tracks.extend(tracks)
            else:
                with self.database.get_connection() as conn:
                    cursor = conn.execute("SELECT * FROM tracks")
                    all_tracks = []
                    for row in cursor.fetchall():
                        track = self.database._row_to_track(row)
                        track.credits = self.database.get_credits_by_track_id(track.id)
                        all_tracks.append(track)
            
            metrics = QualityMetrics()
            metrics.total_tracks = len(all_tracks)
            
            if not all_tracks:
                return metrics
            
            # Calculer les métriques
            for track in all_tracks:
                # Producteur
                if any(c.credit_category == CreditCategory.PRODUCER for c in track.credits):
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
            QualityReport: Rapport de qualité
        """
        try:
            analysis = self.check_track_quality(track)
            
            report = QualityReport(
                track_id=track.id,
                quality_score=analysis.quality_score,
                quality_level=analysis.quality_level,
                checked_at=datetime.now()
            )
            
            # Analyser les critères de qualité
            report.has_producer = any(
                c.credit_category == CreditCategory.PRODUCER for c in track.credits
            )
            report.has_bpm = track.bpm is not None
            report.has_duration = track.duration_seconds is not None
            report.has_valid_duration = (
                track.duration_seconds is not None and 
                self.config['min_duration'] <= track.duration_seconds <= self.config['max_duration']
            )
            report.has_album_info = track.album_title is not None
            report.has_lyrics = track.has_lyrics
            report.has_credits = len(track.credits) > 0
            
            # Ajouter les problèmes détectés
            for issue in analysis.issues:
                if issue.severity in ['critical', 'major']:
                    report.add_issue(f"{issue.check_type.value}: {issue.message}")
            
            # Calculer le score final
            report.calculate_score()
            
            return report
            
        except Exception as e:
            self.logger.error(f"Erreur création rapport qualité pour track {track.id}: {e}")
            return QualityReport(
                track_id=track.id,
                quality_score=0.0,
                quality_level=QualityLevel.VERY_POOR
            )
    
    def batch_quality_check(self, entity_type: str, entity_ids: List[int]) -> List[QualityAnalysis]:
        """
        Effectue une vérification de qualité en lot.
        
        Args:
            entity_type: Type d'entité ('track', 'artist')
            entity_ids: Liste des IDs à vérifier
            
        Returns:
            Liste des analyses de qualité
        """
        results = []
        
        try:
            self.logger.info(f"Début vérification qualité en lot: {len(entity_ids)} {entity_type}s")
            
            for entity_id in entity_ids:
                try:
                    if entity_type == 'track':
                        # Récupérer le track
                        with self.database.get_connection() as conn:
                            cursor = conn.execute("SELECT * FROM tracks WHERE id = ?", (entity_id,))
                            row = cursor.fetchone()
                            if row:
                                track = self.database._row_to_track(row)
                                track.credits = self.database.get_credits_by_track_id(track.id)
                                track.featuring_artists = self.database.get_features_by_track_id(track.id)
                                analysis = self.check_track_quality(track)
                                results.append(analysis)
                    
                    elif entity_type == 'artist':
                        analysis = self.check_artist_quality(entity_id)
                        results.append(analysis)
                    
                except Exception as e:
                    self.logger.error(f"Erreur vérification qualité {entity_type} {entity_id}: {e}")
                    # Ajouter une analyse d'erreur
                    results.append(QualityAnalysis(
                        entity_id=entity_id,
                        entity_type=entity_type,
                        quality_level=QualityLevel.VERY_POOR,
                        quality_score=0.0,
                        metrics={},
                        issues=[QualityIssue(
                            check_type=QualityCheck.EMPTY_CREDITS,
                            metric=QualityMetric.VALIDITY,
                            severity="critical",
                            message=f"Erreur lors de la vérification: {e}"
                        )],
                        recommendations=[],
                        last_checked=datetime.now()
                    ))
            
            self.logger.info(f"Vérification qualité en lot terminée: {len(results)} analyses")
            return results
            
        except Exception as e:
            self.logger.error(f"Erreur vérification qualité en lot: {e}")
            return results
    
    def generate_quality_dashboard(self, artist_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Génère un tableau de bord de qualité.
        
        Args:
            artist_ids: Liste des artistes à inclure (None pour tous)
            
        Returns:
            Données du tableau de bord
        """
        try:
            # Métriques globales
            global_metrics = self.generate_global_quality_metrics(artist_ids)
            
            # Récupérer les tracks pour analyse détaillée
            if artist_ids:
                all_tracks = []
                for artist_id in artist_ids:
                    tracks = self.database.get_tracks_by_artist_id(artist_id)
                    all_tracks.extend(tracks)
            else:
                with self.database.get_connection() as conn:
                    cursor = conn.execute("SELECT * FROM tracks LIMIT 1000")  # Limiter pour performance
                    all_tracks = []
                    for row in cursor.fetchall():
                        track = self.database._row_to_track(row)
                        track.credits = self.database.get_credits_by_track_id(track.id)
                        all_tracks.append(track)
            
            # Analyse par niveau de qualité
            quality_distribution = {level.value: 0 for level in QualityLevel}
            
            # Échantillonnage pour performance
            sample_tracks = all_tracks[:min(100, len(all_tracks))]
            sample_analyses = [self.check_track_quality(track) for track in sample_tracks]
            
            for analysis in sample_analyses:
                quality_distribution[analysis.quality_level.value] += 1
            
            # Problèmes les plus fréquents
            issue_frequency = {}
            for analysis in sample_analyses:
                for issue in analysis.issues:
                    key = issue.check_type.value
                    issue_frequency[key] = issue_frequency.get(key, 0) + 1
            
            top_issues = sorted(issue_frequency.items(), key=lambda x: x[1], reverse=True)[:10]
            
            # Tendances (simulation basique)
            trends = {
                'quality_trend': 'stable',  # À calculer avec historique
                'completeness_trend': 'improving',
                'data_freshness_trend': 'declining'
            }
            
            # Recommandations prioritaires
            priority_recommendations = []
            
            if global_metrics.tracks_with_producer / global_metrics.total_tracks < 0.8:
                priority_recommendations.append("Améliorer l'extraction des crédits de production")
            
            if global_metrics.tracks_with_duration / global_metrics.total_tracks < 0.9:
                priority_recommendations.append("Compléter les durées manquantes")
            
            if global_metrics.data_freshness_score < 70:
                priority_recommendations.append("Mettre à jour les données obsolètes")
            
            return {
                'overview': {
                    'total_tracks': global_metrics.total_tracks,
                    'overall_quality_score': round(global_metrics.overall_quality_score, 1),
                    'data_freshness_score': round(global_metrics.data_freshness_score, 1),
                    'average_credits_per_track': round(global_metrics.average_credits_per_track, 1)
                },
                'completeness': {
                    'tracks_with_producer': {
                        'count': global_metrics.tracks_with_producer,
                        'percentage': round((global_metrics.tracks_with_producer / global_metrics.total_tracks) * 100, 1)
                    },
                    'tracks_with_bpm': {
                        'count': global_metrics.tracks_with_bpm,
                        'percentage': round((global_metrics.tracks_with_bpm / global_metrics.total_tracks) * 100, 1)
                    },
                    'tracks_with_duration': {
                        'count': global_metrics.tracks_with_duration,
                        'percentage': round((global_metrics.tracks_with_duration / global_metrics.total_tracks) * 100, 1)
                    },
                    'tracks_with_album': {
                        'count': global_metrics.tracks_with_album,
                        'percentage': round((global_metrics.tracks_with_album / global_metrics.total_tracks) * 100, 1)
                    }
                },
                'quality_distribution': quality_distribution,
                'top_issues': top_issues,
                'trends': trends,
                'priority_recommendations': priority_recommendations,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur génération tableau de bord qualité: {e}")
            return {
                'error': f"Erreur lors de la génération: {e}",
                'last_updated': datetime.now().isoformat()
            }
    
    def suggest_quality_improvements(self, analysis: QualityAnalysis) -> List[Dict[str, Any]]:
        """
        Suggère des améliorations spécifiques basées sur l'analyse.
        
        Args:
            analysis: Analyse de qualité
            
        Returns:
            Liste de suggestions d'amélioration
        """
        improvements = []
        
        try:
            # Analyser les métriques faibles
            low_metrics = [
                metric for metric, score in analysis.metrics.items() 
                if score < 70
            ]
            
            for metric in low_metrics:
                if metric == QualityMetric.COMPLETENESS:
                    improvements.append({
                        'category': 'Complétude',
                        'priority': 'High',
                        'action': 'Compléter les données manquantes',
                        'impact': 'Améliore significativement la qualité globale',
                        'effort': 'Medium',
                        'tools': ['extractors', 'manual_input']
                    })
                
                elif metric == QualityMetric.VALIDITY:
                    improvements.append({
                        'category': 'Validité',
                        'priority': 'High',
                        'action': 'Corriger les données invalides',
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
            
            # Suggestionsspécifiques aux problèmes critiques
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
            return {'error': f'Erreur lors du monitoring: {e}'}# processors/quality_checker.py
import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from statistics import mean, median, stdev

from ..models.entities import Track, Credit, Artist, Album, QualityReport
from ..models.enums import CreditType, CreditCategory, DataSource, QualityLevel
from ..core.database import Database
from ..config.settings import settings
from ..utils.text_utils import validate_artist_name

class QualityMetric(Enum):
    """Métriques de qualité"""
    COMPLETENESS = "completeness"        # Complétude des données
    ACCURACY = "accuracy"               # Précision des données
    CONSISTENCY = "consistency"         # Cohérence des données
    FRESHNESS = "freshness"            # Fraîcheur des données
    VALIDITY = "validity"              # Validité des données
    UNIQUENESS = "uniqueness"          # Unicité des données

class QualityCheck(Enum):
    """Types de vérifications de qualité"""
    MISSING_PRODUCER = "missing_producer"
    MISSING_BPM = "missing_bpm"
    MISSING_DURATION = "missing_duration"
    SUSPICIOUS_DURATION = "suspicious_duration"
    SUSPICIOUS_BPM = "suspicious_bpm"
    INVALID_ARTIST_NAME = "invalid_artist_name"
    MISSING_ALBUM = "missing_album"
    INCONSISTENT_ALBUM = "inconsistent_album"
    DUPLICATE_CREDITS = "duplicate_credits"
    EMPTY_CREDITS = "empty_credits"
    OUTDATED_DATA = "outdated_data"
    INVALID_EXTERNAL_IDS = "invalid_external_ids"
    INCONSISTENT_FEATURING = "inconsistent_featuring"

@dataclass
class QualityIssue:
    """Représente un problème de qualité"""
    check_type: QualityCheck
    metric: QualityMetric
    severity: str  # 'critical', 'major', 'minor', 'info'
    message: str
    field: Optional[str] = None
    value: Optional[Any] = None
    suggestion: Optional[str] = None
    confidence: float = 1.0

@dataclass
class QualityMetrics:
    """Métriques globales de qualité"""
    total_tracks: int = 0
    tracks_with_producer: int = 0
    tracks_with_bpm: int = 0
    tracks_with_duration: int = 0
    tracks_with_valid_duration: int = 0
    tracks_with_album: int = 0
    tracks_with_lyrics: int = 0
    tracks_with_credits: int = 0
    average_credits_per_track: float = 0.0
    data_freshness_score: float = 0.0
    overall_quality_score: float = 0.0

@dataclass
class QualityAnalysis:
    """Analyse complète de qualité"""
    entity_id: int
    entity_type: str
    quality_level: QualityLevel
    quality_score: float
    metrics: Dict[QualityMetric, float]
    issues: List[QualityIssue]
    recommendations: List[str]
    last_checked: datetime

class QualityChecker:
    """
    Vérificateur de qualité des données musicales.
    
    Responsabilités :
    - Évaluation de la qualité des données
    - Détection d'anomalies et d'incohérences
    - Calcul de métriques de qualité
    - Génération de rapports de qualité
    - Suggestions d'amélioration
    """
    
    def __init__(self, database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        self.database = database or Database()
        
        # Configuration des vérifications
        self.config = {
            'min_duration': settings.get('quality.min_duration_seconds', 30),
            'max_duration': settings.get('quality.max_duration_seconds', 1800),
            'min_bpm': settings.get('quality.min_bpm', 40),
            'max_bpm': settings.get('quality.max_bpm', 300),
            'require_producer': settings.get('quality.check_missing_producer', True),
            'require_bpm': settings.get('quality.check_missing_bpm', True),
            'data_freshness_days': settings.get('quality.freshness_threshold_days', 30),
            'min_credits_per_track': settings.get('quality.min_credits_per_track', 1),
            'suspicious_bpm_threshold': settings.get('quality.suspicious_bpm_threshold', 0.1)
        }
        
        # Seuils de qualité
        self.quality_thresholds = {
            QualityLevel.EXCELLENT: 90.0,
            QualityLevel.GOOD: 75.0,
            QualityLevel.AVERAGE: 50.0,
            QualityLevel.POOR: 25.0,
            QualityLevel.VERY_POOR: 0.0
        }
        
        self.logger.info("QualityChecker initialisé")
    
    def check_track_quality(self, track: Track) -> QualityAnalysis:
        """
        Vérifie la qualité d'un track.
        
        Args:
            track: Track à
                def check_track_quality(self, track: Track) -> QualityAnalysis:
        """
        Vérifie la qualité d'un track.
        
        Args:
            track: Track à analyser
            
        Returns:
            QualityAnalysis: Analyse complète de la qualité
        """
        issues = []
        metrics = {}
        
        try:
            # Vérifications de complétude
            completeness_issues, completeness_score = self._check_track_completeness(track)
            issues.extend(completeness_issues)
            metrics[QualityMetric.COMPLETENESS] = completeness_score
            
            # Vérifications de validité
            validity_issues, validity_score = self._check_track_validity(track)
            issues.extend(validity_issues)
            metrics[QualityMetric.VALIDITY] = validity_score
            
            # Vérifications de cohérence
            consistency_issues, consistency_score = self._check_track_consistency(track)
            issues.extend(consistency_issues)
            metrics[QualityMetric.CONSISTENCY] = consistency_score
            
            # Vérifications de précision
            accuracy_issues, accuracy_score = self._check_track_accuracy(track)
            issues.extend(accuracy_issues)
            metrics[QualityMetric.ACCURACY] = accuracy_score
            
            # Vérifications de fraîcheur
            freshness_issues, freshness_score = self._check_track_freshness(track)
            issues.extend(freshness_issues)
            metrics[QualityMetric.FRESHNESS] = freshness_score
            
            # Vérifications d'unicité
            uniqueness_issues, uniqueness_score = self._check_track_uniqueness(track)
            issues.extend(uniqueness_issues)
            metrics[QualityMetric.UNIQUENESS] = uniqueness_score
            
            # Calcul du score global
            overall_score = self._calculate_overall_quality_score(metrics, issues)
            quality_level = self._determine_quality_level(overall_score)
            
            # Génération des recommandations
            recommendations = self._generate_track_recommendations(issues)
            
            return QualityAnalysis(
                entity_id=track.id,
                entity_type="track",
                quality_level=quality_level,
                quality_score=overall_score,
                metrics=metrics,
                issues=issues,
                recommendations=recommendations,
                last_checked=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Erreur vérification qualité track '{track.title}': {e}")
            return QualityAnalysis(
                entity_id=track.id,
                entity_type="track",
                quality_level=QualityLevel.VERY_POOR,
                quality_score=0.0,
                metrics={},
                issues=[QualityIssue(
                    check_type=QualityCheck.EMPTY_CREDITS,  # Placeholder
                    metric=QualityMetric.VALIDITY,
                    severity="critical",
                    message=f"Erreur lors de la vérification: {e}"
                )],
                recommendations=[],
                last_checked=datetime.now()
            )
    
    def _check_track_completeness(self, track: Track) -> Tuple[List[QualityIssue], float]:
        """Vérifie la complétude des données d'un track"""
        issues = []
        score = 0.0
        max_score = 100.0
        
        # Vérification des champs essentiels
        if not track.title or not track.title.strip():
            issues.append(QualityIssue(
                check_type=QualityCheck.MISSING_PRODUCER,  # Placeholder car pas de MISSING_TITLE
                metric=QualityMetric.COMPLETENESS,
                severity="critical",
                message="Titre manquant",
                field="title",
                suggestion="Ajouter un titre valide"
            ))
        else:
            score += 20
        
        if not track.artist_name:
            issues.append(QualityIssue(
                check_type=QualityCheck.INVALID_ARTIST_NAME,
                metric=QualityMetric.COMPLETENESS,
                severity="critical",
                message="Nom d'artiste manquant",
                field="artist_name",
                suggestion="Ajouter le nom de l'artiste"
            ))
        else:
            score += 20
        
        # Vérification producteur
        has_producer = any(c.credit_category == CreditCategory.PRODUCER for c in track.credits)
        if not has_producer and self.config['require_producer']:
            issues.append(QualityIssue(
                check_type=QualityCheck.MISSING_PRODUCER,
                metric=QualityMetric.COMPLETENESS,
                severity="major",
                message="Aucun producteur identifié",
                field="credits",
                suggestion="Ajouter les crédits de production"
            ))
        else:
            score += 15
        
        # Vérification durée
        if not track.duration_seconds:
            if self.config['require_bpm']:  # Utiliser la config existante
                issues.append(QualityIssue(
                    check_type=QualityCheck.MISSING_DURATION,
                    metric=QualityMetric.COMPLETENESS,
                    severity="major",
                    message="Durée manquante",
                    field="duration_seconds",
                    suggestion="Ajouter la durée du morceau"
                ))
        else:
            score += 10
        
        # Vérification BPM
        if not track.bpm and self.config['require_bpm']:
            issues.append(QualityIssue(
                check_type=QualityCheck.MISSING_BPM,
                metric=QualityMetric.COMPLETENESS,
                severity="minor",
                message="BPM manquant",
                field="bpm",
                suggestion="Ajouter le BPM du morceau"
            ))
        else:
            score += 10
        
        # Vérification album
        if not track.album_title:
            issues.append(QualityIssue(
                check_type=QualityCheck.MISSING_ALBUM,
                metric=QualityMetric.COMPLETENESS,
                severity="minor",
                message="Informations d'album manquantes",
                field="album_title",
                suggestion="Associer le track à un album"
            ))
        else:
            score += 10
        
        # Vérification crédits
        if not track.credits:
            issues.append(QualityIssue(
                check_type=QualityCheck.EMPTY_CREDITS,
                metric=QualityMetric.COMPLETENESS,
                severity="major",
                message="Aucun crédit trouvé",
                field="credits",
                suggestion="Ajouter les crédits du morceau"
            ))
        else:
            score += 10
        
        # Bonus pour données additionnelles
        if track.lyrics:
            score += 3
        if track.key:
            score += 2
        
        return issues, min(score, max_score)
    
    def _check_track_validity(self, track: Track) -> Tuple[List[QualityIssue], float]:
        """Vérifie la validité des données d'un track"""
        issues = []
        score = 100.0
        
        # Validation nom d'artiste
        if track.artist_name and not validate_artist_name(track.artist_name):
            issues.append(QualityIssue(
                check_type=QualityCheck.INVALID_ARTIST_NAME,
                metric=QualityMetric.VALIDITY,
                severity="major",
                message=f"Nom d'artiste invalide: '{track.artist_name}'",
                field="artist_name",
                value=track.artist_name,
                suggestion="Corriger le nom de l'artiste"
            ))
            score -= 20
        
        # Validation durée
        if track.duration_seconds:
            if track.duration_seconds < self.config['min_duration']:
                issues.append(QualityIssue(
                    check_type=QualityCheck.SUSPICIOUS_DURATION,
                    metric=QualityMetric.VALIDITY,
                    severity="major",
                    message=f"Durée très courte: {track.duration_seconds}s",
                    field="duration_seconds",
                    value=track.duration_seconds,
                    suggestion="Vérifier la durée du morceau"
                ))
                score -= 15
            elif track.duration_seconds > self.config['max_duration']:
                issues.append(QualityIssue(
                    check_type=QualityCheck.SUSPICIOUS_DURATION,
                    metric=QualityMetric.VALIDITY,
                    severity="minor",
                    message=f"Durée très longue: {track.duration_seconds}s",
                    field="duration_seconds",
                    value=track.duration_seconds,
                    suggestion="Vérifier la durée du morceau"
                ))
                score -= 10
        
        # Validation BPM
        if track.bpm:
            if track.bpm < self.config['min_bpm'] or track.bpm > self.config['max_bpm']:
                issues.append(QualityIssue(
                    check_type=QualityCheck.SUSPICIOUS_BPM,
                    metric=QualityMetric.VALIDITY,
                    severity="minor",
                    message=f"BPM suspect: {track.bpm}",
                    field="bpm",
                    value=track.bpm,
                    suggestion="Vérifier le BPM du morceau"
                ))
                score -= 10
        
        # Validation IDs externes
        if track.genius_id and not str(track.genius_id).isdigit():
            issues.append(QualityIssue(
                check_type=QualityCheck.INVALID_EXTERNAL_IDS,
                metric=QualityMetric.VALIDITY,
                severity="minor",
                message="ID Genius invalide",
                field="genius_id",
                value=track.genius_id,
                suggestion="Corriger l'ID Genius"
            ))
            score -= 5
        
        if track.spotify_id and not re.match(r'^[a-zA-Z0-9]{22}# processors/quality_checker.py