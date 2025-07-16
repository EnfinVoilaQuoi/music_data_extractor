# steps/step3_process.py
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from ..models.entities import Track, Artist, Session, QualityReport
from ..models.enums import SessionStatus, ExtractionStatus, ProcessingStep, QualityLevel
from ..processors.data_cleaner import DataCleaner, CleaningStats
from ..processors.data_validator import DataValidator, ValidationResult, ValidationStats
from ..processors.duplicate_detector import DuplicateDetector, DuplicateMatch, DeduplicationStats
from ..processors.quality_checker import QualityChecker, QualityAnalysis, QualityMetrics
from ..processors.data_enricher import DataEnricher, EnrichmentResult, EnrichmentStats
from ..core.database import Database
from ..core.session_manager import SessionManager, get_session_manager
from ..core.exceptions import ProcessingError
from ..config.settings import settings

@dataclass
class ProcessingStats:
    """Statistiques du traitement"""
    total_tracks: int = 0
    tracks_cleaned: int = 0
    tracks_validated: int = 0
    tracks_enriched: int = 0
    duplicates_removed: int = 0
    quality_improved: int = 0
    errors_fixed: int = 0
    processing_time_seconds: float = 0.0
    
    # Statistiques détaillées
    cleaning_stats: Optional[CleaningStats] = None
    validation_stats: Optional[ValidationStats] = None
    enrichment_stats: Optional[EnrichmentStats] = None
    deduplication_stats: Optional[DeduplicationStats] = None

@dataclass
class ProcessingResult:
    """Résultat du traitement pour un track"""
    track: Track
    success: bool
    operations_performed: List[str] = None
    issues_fixed: List[str] = None
    quality_improved: bool = False
    processing_time: float = 0.0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.operations_performed is None:
            self.operations_performed = []
        if self.issues_fixed is None:
            self.issues_fixed = []
        if self.errors is None:
            self.errors = []

class ProcessingStep:
    """
    Étape 3 : Traitement et amélioration de la qualité des données.
    
    Responsabilités :
    - Nettoyage et normalisation des données
    - Validation et détection d'erreurs
    - Déduplication des données
    - Enrichissement automatique
    - Amélioration de la qualité globale
    - Génération de rapports qualité
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None,
                 database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        
        # Composants
        self.session_manager = session_manager or get_session_manager()
        self.database = database or Database()
        
        # Processeurs
        self.data_cleaner = DataCleaner(self.database)
        self.data_validator = DataValidator(self.database)
        self.duplicate_detector = DuplicateDetector(self.database)
        self.quality_checker = QualityChecker(self.database)
        self.data_enricher = DataEnricher(self.database)
        
        # Configuration
        self.config = {
            'enable_cleaning': settings.get('processing.enable_cleaning', True),
            'enable_validation': settings.get('processing.enable_validation', True),
            'enable_deduplication': settings.get('processing.enable_deduplication', True),
            'enable_enrichment': settings.get('processing.enable_enrichment', True),
            'auto_fix_issues': settings.get('processing.auto_fix_issues', True),
            'batch_size': settings.get('processing.batch_size', 20),
            'max_workers': settings.get('processing.max_workers', 2),
            'quality_threshold': settings.get('processing.min_quality_score', 70.0),
            'generate_reports': settings.get('processing.generate_reports', True)
        }
        
        # Locks pour thread safety
        self._stats_lock = Lock()
        self._db_lock = Lock()
        
        self.logger.info("ProcessingStep initialisé")
    
    def process_tracks_data(self, session_id: str, 
                          processing_steps: Optional[List[str]] = None) -> Tuple[List[Track], ProcessingStats]:
        """
        Traite les données extraites pour une session.
        
        Args:
            session_id: ID de la session
            processing_steps: Étapes spécifiques à exécuter (None pour toutes)
            
        Returns:
            Tuple[List[Track], ProcessingStats]: Tracks traités et statistiques
        """
        start_time = datetime.now()
        
        # Récupération de la session
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ProcessingError(f"Session {session_id} non trouvée")
        
        try:
            self.logger.info(f"🔧 Début du traitement pour la session {session_id}")
            
            # Mise à jour de la session
            self.session_manager.update_session(
                session_id,
                current_step="processing_started"
            )
            
            # Récupération des morceaux à traiter
            tracks_to_process = self._get_tracks_to_process(session)
            
            if not tracks_to_process:
                self.logger.warning("Aucun morceau à traiter")
                return [], ProcessingStats()
            
            # Initialisation des statistiques
            stats = ProcessingStats(total_tracks=len(tracks_to_process))
            
            # Définition des étapes de traitement
            if processing_steps is None:
                processing_steps = ['cleaning', 'validation', 'deduplication', 'enrichment', 'quality_check']
            
            # Exécution des étapes de traitement
            processed_tracks = tracks_to_process.copy()
            
            for step in processing_steps:
                self.logger.info(f"Exécution de l'étape: {step}")
                
                if step == 'cleaning' and self.config['enable_cleaning']:
                    processed_tracks, cleaning_stats = self._execute_cleaning_step(
                        processed_tracks, session_id
                    )
                    stats.cleaning_stats = cleaning_stats
                    stats.tracks_cleaned = cleaning_stats.tracks_cleaned
                    stats.errors_fixed += cleaning_stats.errors_fixed
                
                elif step == 'validation' and self.config['enable_validation']:
                    processed_tracks, validation_stats = self._execute_validation_step(
                        processed_tracks, session_id
                    )
                    stats.validation_stats = validation_stats
                    stats.tracks_validated = validation_stats.valid_entities
                
                elif step == 'deduplication' and self.config['enable_deduplication']:
                    processed_tracks, dedup_stats = self._execute_deduplication_step(
                        processed_tracks, session_id
                    )
                    stats.deduplication_stats = dedup_stats
                    stats.duplicates_removed = dedup_stats.duplicates_removed
                
                elif step == 'enrichment' and self.config['enable_enrichment']:
                    processed_tracks, enrichment_stats = self._execute_enrichment_step(
                        processed_tracks, session_id
                    )
                    stats.enrichment_stats = enrichment_stats
                    stats.tracks_enriched = enrichment_stats.successful_enrichments
                
                elif step == 'quality_check':
                    quality_improved = self._execute_quality_check_step(
                        processed_tracks, session_id
                    )
                    stats.quality_improved = quality_improved
            
            # Calcul du temps total
            end_time = datetime.now()
            stats.processing_time_seconds = (end_time - start_time).total_seconds()
            
            # Sauvegarde finale des tracks traités
            self._save_processed_tracks(processed_tracks)
            
            # Génération des rapports si activée
            if self.config['generate_reports']:
                self._generate_processing_reports(session_id, stats, processed_tracks)
            
            # Mise à jour finale de la session
            self.session_manager.update_session(
                session_id,
                current_step="processing_completed"
            )
            
            self.logger.info(
                f"✅ Traitement terminé: {len(processed_tracks)} morceaux traités "
                f"({stats.tracks_cleaned} nettoyés, {stats.duplicates_removed} doublons supprimés, "
                f"{stats.tracks_enriched} enrichis) en {stats.processing_time_seconds:.1f}s"
            )
            
            return processed_tracks, stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du traitement: {e}")
            self.session_manager.fail_session(session_id, str(e))
            raise ProcessingError(f"Échec du traitement: {e}")
    
    def _get_tracks_to_process(self, session) -> List[Track]:
        """Récupère les morceaux à traiter pour la session"""
        try:
            # Récupération de l'artiste
            artist = self.database.get_artist_by_name(session.artist_name)
            if not artist:
                raise ProcessingError(f"Artiste '{session.artist_name}' non trouvé")
            
            # Récupération des morceaux extraits
            all_tracks = self.database.get_tracks_by_artist_id(artist.id)
            
            # Filtrer les morceaux qui ont été extraits
            tracks_to_process = [
                track for track in all_tracks
                if track.extraction_status == ExtractionStatus.COMPLETED
            ]
            
            self.logger.info(f"Morceaux à traiter: {len(tracks_to_process)}/{len(all_tracks)}")
            return tracks_to_process
            
        except Exception as e:
            self.logger.error(f"Erreur récupération morceaux: {e}")
            return []
    
    def _execute_cleaning_step(self, tracks: List[Track], session_id: str) -> Tuple[List[Track], CleaningStats]:
        """Exécute l'étape de nettoyage des données"""
        try:
            self.logger.info(f"🧹 Nettoyage des données: {len(tracks)} morceaux")
            
            # Mise à jour de la session
            self.session_manager.update_session(session_id, current_step="cleaning_data")
            
            # Nettoyage par batch pour optimiser les performances
            all_stats = CleaningStats()
            cleaned_tracks = []
            
            for i in range(0, len(tracks), self.config['batch_size']):
                batch = tracks[i:i + self.config['batch_size']]
                
                # Traitement parallèle du batch
                with ThreadPoolExecutor(max_workers=self.config['max_workers']) as executor:
                    futures = [executor.submit(self._clean_single_track, track) for track in batch]
                    
                    for future in as_completed(futures):
                        try:
                            cleaned_track, track_stats = future.result()
                            cleaned_tracks.append(cleaned_track)
                            
                            # Agrégation des statistiques
                            all_stats.tracks_processed += 1
                            if track_stats.tracks_cleaned > 0:
                                all_stats.tracks_cleaned += 1
                            all_stats.credits_cleaned += track_stats.credits_cleaned
                            all_stats.errors_fixed += track_stats.errors_fixed
                            
                        except Exception as e:
                            self.logger.error(f"Erreur nettoyage track: {e}")
            
            self.logger.info(f"Nettoyage terminé: {all_stats.tracks_cleaned} morceaux nettoyés")
            return cleaned_tracks, all_stats
            
        except Exception as e:
            self.logger.error(f"Erreur étape nettoyage: {e}")
            return tracks, CleaningStats()
    
    def _clean_single_track(self, track: Track) -> Tuple[Track, CleaningStats]:
        """Nettoie un seul morceau"""
        try:
            # Utilisation du DataCleaner
            issues_before = self.data_validator.validate_track(track)
            initial_issue_count = len([i for i in issues_before.issues if i.type.value == "critical"])
            
            # Validation de l'intégrité
            integrity_issues = self.data_cleaner.validate_track_integrity(track)
            
            # Nettoyage si des problèmes détectés
            stats = CleaningStats(tracks_processed=1)
            
            if integrity_issues or initial_issue_count > 0:
                # Le track nécessite un nettoyage
                from ..processors.data_cleaner import CleaningStats as SingleStats
                single_stats = SingleStats()
                
                # Appel du nettoyage sur l'artiste (inclut ce track)
                if track.artist_id:
                    artist_stats = self.data_cleaner.clean_artist_data(track.artist_id)
                    
                    # Copie des stats pertinentes
                    if artist_stats.tracks_cleaned > 0:
                        stats.tracks_cleaned = 1
                        stats.credits_cleaned = artist_stats.credits_cleaned
                        stats.errors_fixed = artist_stats.errors_fixed
            
            return track, stats
            
        except Exception as e:
            self.logger.warning(f"Erreur nettoyage track '{track.title}': {e}")
            return track, CleaningStats(tracks_processed=1)
    
    def _execute_validation_step(self, tracks: List[Track], session_id: str) -> Tuple[List[Track], ValidationStats]:
        """Exécute l'étape de validation des données"""
        try:
            self.logger.info(f"✅ Validation des données: {len(tracks)} morceaux")
            
            # Mise à jour de la session
            self.session_manager.update_session(session_id, current_step="validating_data")
            
            # Validation de tous les tracks
            validation_results = []
            
            for track in tracks:
                try:
                    result = self.data_validator.validate_track(track)
                    validation_results.append(result)
                    
                    # Auto-correction si activée
                    if self.config['auto_fix_issues'] and not result.is_valid:
                        self._auto_fix_validation_issues(track, result)
                        
                except Exception as e:
                    self.logger.warning(f"Erreur validation track '{track.title}': {e}")
            
            # Génération des statistiques
            stats = self.data_validator.generate_validation_summary(validation_results)
            
            self.logger.info(f"Validation terminée: {stats.valid_entities}/{stats.total_validated} valides")
            return tracks, stats
            
        except Exception as e:
            self.logger.error(f"Erreur étape validation: {e}")
            return tracks, ValidationStats()
    
    def _auto_fix_validation_issues(self, track: Track, validation_result: ValidationResult):
        """Tente de corriger automatiquement les problèmes de validation"""
        try:
            for issue in validation_result.issues:
                if issue.suggested_fix:
                    # Implémentation de corrections automatiques basiques
                    if "Titre manquant" in issue.message and not track.title:
                        track.title = f"Unknown Track {track.id}"
                        self.logger.debug(f"Titre corrigé pour track {track.id}")
                    
                    elif "Nom d'artiste manquant" in issue.message and not track.artist_name:
                        if track.artist_id:
                            # Récupérer le nom depuis l'artiste
                            artist = self.database.get_artist_by_name("placeholder")  # À améliorer
                            if artist:
                                track.artist_name = artist.name
                                self.logger.debug(f"Nom d'artiste corrigé pour track {track.id}")
                    
                    # Autres corrections possibles...
                    
        except Exception as e:
            self.logger.warning(f"Erreur auto-correction track '{track.title}': {e}")
    
    def _execute_deduplication_step(self, tracks: List[Track], session_id: str) -> Tuple[List[Track], DeduplicationStats]:
        """Exécute l'étape de déduplication"""
        try:
            self.logger.info(f"🔍 Déduplication: {len(tracks)} morceaux")
            
            # Mise à jour de la session
            self.session_manager.update_session(session_id, current_step="deduplicating_data")
            
            # Détection des doublons de tracks
            track_duplicates = self.duplicate_detector.detect_track_duplicates()
            
            # Détection des doublons de crédits
            track_ids = [track.id for track in tracks if track.id]
            credit_duplicates = self.duplicate_detector.detect_credit_duplicates(track_ids)
            
            # Fusion automatique des doublons
            all_duplicates = track_duplicates + credit_duplicates
            stats = self.duplicate_detector.auto_merge_duplicates(all_duplicates, dry_run=False)
            
            # Filtrer les tracks supprimés après déduplication
            remaining_tracks = [track for track in tracks if track.id]  # Simplified logic
            
            self.logger.info(f"Déduplication terminée: {stats.duplicates_removed} doublons supprimés")
            return remaining_tracks, stats
            
        except Exception as e:
            self.logger.error(f"Erreur étape déduplication: {e}")
            return tracks, DeduplicationStats()
    
    def _execute_enrichment_step(self, tracks: List[Track], session_id: str) -> Tuple[List[Track], EnrichmentStats]:
        """Exécute l'étape d'enrichissement des données"""
        try:
            self.logger.info(f"📈 Enrichissement: {len(tracks)} morceaux")
            
            # Mise à jour de la session
            self.session_manager.update_session(session_id, current_step="enriching_data")
            
            # Enrichissement par batch
            all_results = []
            enriched_tracks = []
            
            for i in range(0, len(tracks), self.config['batch_size']):
                batch = tracks[i:i + self.config['batch_size']]
                
                for track in batch:
                    try:
                        # Enrichissement du track
                        results = self.data_enricher.enrich_track(track)
                        all_results.extend(results)
                        enriched_tracks.append(track)
                        
                    except Exception as e:
                        self.logger.warning(f"Erreur enrichissement track '{track.title}': {e}")
                        enriched_tracks.append(track)  # Garder le track même en cas d'erreur
            
            # Compilation des statistiques
            successful_results = [r for r in all_results if r.success]
            stats = EnrichmentStats(
                total_processed=len(tracks),
                successful_enrichments=len(successful_results)
            )
            
            # Compter par champ enrichi
            for result in successful_results:
                field = result.field
                stats.fields_enriched[field] = stats.fields_enriched.get(field, 0) + 1
            
            self.logger.info(f"Enrichissement terminé: {len(successful_results)} améliorations")
            return enriched_tracks, stats
            
        except Exception as e:
            self.logger.error(f"Erreur étape enrichissement: {e}")
            return tracks, EnrichmentStats()
    
    def _execute_quality_check_step(self, tracks: List[Track], session_id: str) -> int:
        """Exécute l'étape de vérification qualité"""
        try:
            self.logger.info(f"📊 Vérification qualité: {len(tracks)} morceaux")
            
            # Mise à jour de la session
            self.session_manager.update_session(session_id, current_step="quality_checking")
            
            quality_improved = 0
            
            for track in tracks:
                try:
                    # Analyse de qualité
                    analysis = self.quality_checker.check_track_quality(track)
                    
                    # Création d'un rapport de qualité
                    report = self.quality_checker.create_quality_report_for_track(track)
                    
                    # Vérifier si la qualité est acceptable
                    if analysis.quality_score >= self.config['quality_threshold']:
                        quality_improved += 1
                    
                    # Sauvegarder le rapport (si implémenté en base)
                    # self.database.create_quality_report(report)
                    
                except Exception as e:
                    self.logger.warning(f"Erreur vérification qualité track '{track.title}': {e}")
            
            self.logger.info(f"Vérification qualité terminée: {quality_improved} tracks de bonne qualité")
            return quality_improved
            
        except Exception as e:
            self.logger.error(f"Erreur étape vérification qualité: {e}")
            return 0
    
    def _save_processed_tracks(self, tracks: List[Track]):
        """Sauvegarde les tracks traités en base de données"""
        try:
            with self._db_lock:
                for track in tracks:
                    # Mise à jour du track
                    self.database.update_track(track)
                    
                    # Mise à jour des crédits
                    for credit in track.credits:
                        if not credit.id:  # Nouveau crédit créé pendant le traitement
                            self.database.create_credit(credit)
            
            self.logger.debug(f"Sauvegarde terminée: {len(tracks)} morceaux")
            
        except Exception as e:
            self.logger.error(f"Erreur sauvegarde tracks traités: {e}")
    
    def _generate_processing_reports(self, session_id: str, stats: ProcessingStats, tracks: List[Track]):
        """Génère les rapports de traitement"""
        try:
            # Rapport de traitement général
            processing_report = {
                'session_id': session_id,
                'processing_date': datetime.now().isoformat(),
                'summary': {
                    'total_tracks': stats.total_tracks,
                    'tracks_cleaned': stats.tracks_cleaned,
                    'tracks_validated': stats.tracks_validated,
                    'tracks_enriched': stats.tracks_enriched,
                    'duplicates_removed': stats.duplicates_removed,
                    'quality_improved': stats.quality_improved,
                    'processing_time': stats.processing_time_seconds
                },
                'detailed_stats': {
                    'cleaning': stats.cleaning_stats.__dict__ if stats.cleaning_stats else {},
                    'validation': stats.validation_stats.__dict__ if stats.validation_stats else {},
                    'enrichment': stats.enrichment_stats.__dict__ if stats.enrichment_stats else {},
                    'deduplication': stats.deduplication_stats.__dict__ if stats.deduplication_stats else {}
                }
            }
            
            # Rapport de qualité global
            quality_metrics = self.quality_checker.generate_global_quality_metrics()
            quality_report = {
                'session_id': session_id,
                'quality_metrics': quality_metrics.__dict__,
                'quality_distribution': self._analyze_quality_distribution(tracks),
                'recommendations': self._generate_quality_recommendations(tracks)
            }
            
            # Sauvegarde des rapports (si nécessaire)
            self.logger.info("Rapports de traitement générés")
            
        except Exception as e:
            self.logger.error(f"Erreur génération rapports: {e}")
    
    def _analyze_quality_distribution(self, tracks: List[Track]) -> Dict[str, int]:
        """Analyse la distribution de qualité des tracks"""
        try:
            distribution = {level.value: 0 for level in QualityLevel}
            
            # Échantillonnage pour performance
            sample_size = min(50, len(tracks))
            sample_tracks = tracks[:sample_size]
            
            for track in sample_tracks:
                try:
                    analysis = self.quality_checker.check_track_quality(track)
                    distribution[analysis.quality_level.value] += 1
                except Exception as e:
                    self.logger.warning(f"Erreur analyse qualité track '{track.title}': {e}")
                    distribution[QualityLevel.POOR.value] += 1
            
            return distribution
            
        except Exception as e:
            self.logger.error(f"Erreur analyse distribution qualité: {e}")
            return {}
    
    def _generate_quality_recommendations(self, tracks: List[Track]) -> List[str]:
        """Génère des recommandations d'amélioration de qualité"""
        try:
            recommendations = []
            
            # Statistiques rapides
            total = len(tracks)
            tracks_with_credits = len([t for t in tracks if t.credits])
            tracks_with_bpm = len([t for t in tracks if t.bpm])
            tracks_with_albums = len([t for t in tracks if t.album_title])
            
            # Recommandations basées sur les manques
            if tracks_with_credits / total < 0.7:
                recommendations.append("Améliorer l'extraction des crédits (< 70% des tracks)")
            
            if tracks_with_bpm / total < 0.5:
                recommendations.append("Enrichir les données BPM via Spotify (< 50% des tracks)")
            
            if tracks_with_albums / total < 0.8:
                recommendations.append("Compléter les informations d'albums (< 80% des tracks)")
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Erreur génération recommandations: {e}")
            return []
    
    def get_processing_progress(self, session_id: str) -> Dict[str, Any]:
        """Récupère le progrès du traitement pour une session"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {}
            
            # Récupération des morceaux pour calculer les détails
            artist = self.database.get_artist_by_name(session.artist_name)
            if not artist:
                return {}
            
            all_tracks = self.database.get_tracks_by_artist_id(artist.id)
            
            # Calcul des statistiques de traitement
            stats = {
                'session_id': session_id,
                'artist_name': session.artist_name,
                'current_step': session.current_step,
                'total_tracks': len(all_tracks),
                'tracks_completed': len([t for t in all_tracks if t.extraction_status == ExtractionStatus.COMPLETED]),
                'processing_status': self._get_processing_status(all_tracks),
                'quality_stats': self._get_quick_quality_stats(all_tracks),
                'updated_at': session.updated_at.isoformat() if session.updated_at else None
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Erreur récupération progrès traitement: {e}")
            return {}
    
    def _get_processing_status(self, tracks: List[Track]) -> Dict[str, int]:
        """Calcule le statut de traitement des tracks"""
        return {
            'total': len(tracks),
            'with_credits': len([t for t in tracks if t.credits]),
            'with_bpm': len([t for t in tracks if t.bpm]),
            'with_albums': len([t for t in tracks if t.album_title]),
            'with_lyrics': len([t for t in tracks if t.has_lyrics])
        }
    
    def _get_quick_quality_stats(self, tracks: List[Track]) -> Dict[str, float]:
        """Calcule des statistiques de qualité rapides"""
        if not tracks:
            return {}
        
        total = len(tracks)
        return {
            'completeness_score': len([t for t in tracks if t.credits and t.duration_seconds]) / total * 100,
            'data_richness': len([t for t in tracks if len(t.credits) >= 2]) / total * 100,
            'album_coverage': len([t for t in tracks if t.album_title]) / total * 100
        }
    
    def validate_processing_quality(self, session_id: str) -> Dict[str, Any]:
        """Valide la qualité du traitement effectué"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {}
            
            artist = self.database.get_artist_by_name(session.artist_name)
            tracks = self.database.get_tracks_by_artist_id(artist.id)
            
            # Validation globale
            validation_results = []
            for track in tracks[:20]:  # Échantillon pour performance
                result = self.data_validator.validate_track(track)
                validation_results.append(result)
            
            # Compilation des résultats
            total_issues = sum(len(r.issues) for r in validation_results)
            critical_issues = sum(len([i for i in r.issues if i.type.value == "critical"]) for r in validation_results)
            
            # Score de qualité global
            avg_quality = sum(r.quality_score for r in validation_results) / len(validation_results)
            
            validation_report = {
                'session_id': session_id,
                'validation_date': datetime.now().isoformat(),
                'sample_size': len(validation_results),
                'average_quality_score': round(avg_quality, 2),
                'total_issues': total_issues,
                'critical_issues': critical_issues,
                'validation_passed': critical_issues == 0 and avg_quality >= self.config['quality_threshold'],
                'recommendations': []
            }
            
            # Recommandations
            if critical_issues > 0:
                validation_report['recommendations'].append(f"Corriger {critical_issues} problème(s) critique(s)")
            
            if avg_quality < self.config['quality_threshold']:
                validation_report['recommendations'].append("Améliorer la qualité globale des données")
            
            if total_issues > len(validation_results) * 2:
                validation_report['recommendations'].append("Réexécuter le nettoyage des données")
            
            return validation_report
            
        except Exception as e:
            self.logger.error(f"Erreur validation qualité traitement: {e}")
            return {}
    
    def retry_failed_processing(self, session_id: str, 
                              retry_steps: Optional[List[str]] = None) -> Tuple[List[Track], ProcessingStats]:
        """Relance le traitement pour les éléments échoués"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                raise ProcessingError(f"Session {session_id} non trouvée")
            
            self.logger.info(f"Relance du traitement pour la session {session_id}")
            
            # Récupération des morceaux problématiques
            artist = self.database.get_artist_by_name(session.artist_name)
            all_tracks = self.database.get_tracks_by_artist_id(artist.id)
            
            # Identifier les tracks qui nécessitent un retraitement
            problematic_tracks = []
            for track in all_tracks:
                try:
                    validation = self.data_validator.validate_track(track)
                    if not validation.is_valid or validation.quality_score < self.config['quality_threshold']:
                        problematic_tracks.append(track)
                except Exception:
                    problematic_tracks.append(track)
            
            if not problematic_tracks:
                self.logger.info("Aucun morceau problématique à retraiter")
                return [], ProcessingStats()
            
            self.logger.info(f"Retraitement de {len(problematic_tracks)} morceaux problématiques")
            
            # Relance du traitement sur les tracks problématiques
            retry_steps = retry_steps or ['cleaning', 'validation', 'enrichment']
            
            # Simulation du retraitement (logique simplifiée)
            reprocessed_tracks = []
            stats = ProcessingStats(total_tracks=len(problematic_tracks))
            
            for track in problematic_tracks:
                try:
                    # Nettoyage répété
                    if 'cleaning' in retry_steps:
                        track_stats = CleaningStats()
                        if track.artist_id:
                            artist_stats = self.data_cleaner.clean_artist_data(track.artist_id)
                            stats.tracks_cleaned += 1 if artist_stats.tracks_cleaned > 0 else 0
                    
                    # Validation répétée
                    if 'validation' in retry_steps:
                        validation = self.data_validator.validate_track(track)
                        if validation.is_valid:
                            stats.tracks_validated += 1
                    
                    # Enrichissement répété
                    if 'enrichment' in retry_steps:
                        enrichment_results = self.data_enricher.enrich_track(track)
                        if any(r.success for r in enrichment_results):
                            stats.tracks_enriched += 1
                    
                    reprocessed_tracks.append(track)
                    
                except Exception as e:
                    self.logger.warning(f"Erreur retraitement track '{track.title}': {e}")
            
            # Sauvegarde des tracks retraités
            self._save_processed_tracks(reprocessed_tracks)
            
            self.logger.info(f"Retraitement terminé: {len(reprocessed_tracks)} morceaux retraités")
            return reprocessed_tracks, stats
            
        except Exception as e:
            self.logger.error(f"Erreur relance traitement: {e}")
            raise ProcessingError(f"Échec de la relance: {e}")
    
    def optimize_data_quality(self, session_id: str) -> Dict[str, Any]:
        """Optimise la qualité des données de manière ciblée"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {}
            
            self.logger.info(f"Optimisation de la qualité pour la session {session_id}")
            
            artist = self.database.get_artist_by_name(session.artist_name)
            tracks = self.database.get_tracks_by_artist_id(artist.id)
            
            optimization_results = {
                'session_id': session_id,
                'optimization_date': datetime.now().isoformat(),
                'tracks_analyzed': len(tracks),
                'optimizations_applied': [],
                'quality_improvement': 0.0
            }
            
            # Analyse des priorités d'optimisation
            priorities = self.data_enricher.suggest_enrichment_priorities(artist.id)
            
            if 'error' not in priorities:
                # Appliquer les optimisations prioritaires
                high_priority_fields = [
                    p for p in priorities.get('enrichment_priorities', [])
                    if p.get('priority') == 'High'
                ]
                
                for field_info in high_priority_fields[:3]:  # Top 3 priorités
                    field = field_info['field']
                    missing_count = field_info['missing_count']
                    
                    if field == 'producer':
                        # Améliorer l'extraction des producteurs
                        improved = self._optimize_producer_extraction(tracks)
                        optimization_results['optimizations_applied'].append(
                            f"Producteurs améliorés: {improved} tracks"
                        )
                    
                    elif field == 'bpm':
                        # Enrichir les BPM manquants
                        improved = self._optimize_bpm_data(tracks)
                        optimization_results['optimizations_applied'].append(
                            f"BPM enrichis: {improved} tracks"
                        )
                    
                    elif field == 'album':
                        # Améliorer les informations d'albums
                        improved = self._optimize_album_data(tracks)
                        optimization_results['optimizations_applied'].append(
                            f"Albums enrichis: {improved} tracks"
                        )
            
            # Calcul de l'amélioration globale
            if optimization_results['optimizations_applied']:
                # Recalcul de la qualité après optimisation
                quality_after = self._calculate_global_quality_score(tracks)
                optimization_results['quality_improvement'] = quality_after
                
                self.logger.info(f"Optimisation terminée: {len(optimization_results['optimizations_applied'])} améliorations")
            
            return optimization_results
            
        except Exception as e:
            self.logger.error(f"Erreur optimisation qualité: {e}")
            return {}
    
    def _optimize_producer_extraction(self, tracks: List[Track]) -> int:
        """Optimise l'extraction des crédits de producteurs"""
        improved = 0
        
        for track in tracks:
            try:
                # Vérifier si le track manque de producteurs
                has_producer = any(
                    'producer' in credit.credit_type.value.lower() 
                    for credit in track.credits
                )
                
                if not has_producer:
                    # Tentative d'inférence de producteur
                    enrichment_results = self.data_enricher.enrich_track(track)
                    producer_results = [
                        r for r in enrichment_results 
                        if r.field == 'credits' and 'producer' in str(r.new_value).lower()
                    ]
                    
                    if producer_results and any(r.success for r in producer_results):
                        improved += 1
                        
            except Exception as e:
                self.logger.warning(f"Erreur optimisation producteur pour '{track.title}': {e}")
        
        return improved
    
    def _optimize_bpm_data(self, tracks: List[Track]) -> int:
        """Optimise les données BPM"""
        improved = 0
        
        for track in tracks:
            try:
                if not track.bpm:
                    # Tentative d'enrichissement BPM
                    enrichment_results = self.data_enricher.enrich_track(track)
                    bpm_results = [r for r in enrichment_results if r.field == 'bpm']
                    
                    if bmp_results and any(r.success for r in bmp_results):
                        improved += 1
                        
            except Exception as e:
                self.logger.warning(f"Erreur optimisation BPM pour '{track.title}': {e}")
        
        return improved
    
    def _optimize_album_data(self, tracks: List[Track]) -> int:
        """Optimise les données d'albums"""
        improved = 0
        
        for track in tracks:
            try:
                if not track.album_title:
                    # Tentative d'inférence d'album
                    enrichment_results = self.data_enricher.enrich_track(track)
                    album_results = [r for r in enrichment_results if r.field == 'album_title']
                    
                    if album_results and any(r.success for r in album_results):
                        improved += 1
                        
            except Exception as e:
                self.logger.warning(f"Erreur optimisation album pour '{track.title}': {e}")
        
        return improved
    
    def _calculate_global_quality_score(self, tracks: List[Track]) -> float:
        """Calcule un score de qualité global"""
        if not tracks:
            return 0.0
        
        try:
            # Échantillonnage pour performance
            sample_size = min(20, len(tracks))
            sample_tracks = tracks[:sample_size]
            
            quality_scores = []
            for track in sample_tracks:
                try:
                    analysis = self.quality_checker.check_track_quality(track)
                    quality_scores.append(analysis.quality_score)
                except Exception:
                    quality_scores.append(0.0)
            
            return sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
            
        except Exception as e:
            self.logger.error(f"Erreur calcul score qualité global: {e}")
            return 0.0
    
    def generate_processing_summary(self, session_id: str) -> Dict[str, Any]:
        """Génère un résumé complet du traitement"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {}
            
            artist = self.database.get_artist_by_name(session.artist_name)
            tracks = self.database.get_tracks_by_artist_id(artist.id)
            
            # Statistiques générales
            summary = {
                'session_info': {
                    'session_id': session_id,
                    'artist_name': session.artist_name,
                    'processing_date': datetime.now().isoformat(),
                    'total_tracks': len(tracks)
                },
                'data_quality': {
                    'overall_score': self._calculate_global_quality_score(tracks),
                    'completeness': self._calculate_completeness_score(tracks),
                    'consistency': self._calculate_consistency_score(tracks),
                    'enrichment_level': self._calculate_enrichment_level(tracks)
                },
                'processing_results': {
                    'tracks_with_credits': len([t for t in tracks if t.credits]),
                    'tracks_with_bpm': len([t for t in tracks if t.bpm]),
                    'tracks_with_albums': len([t for t in tracks if t.album_title]),
                    'tracks_with_lyrics': len([t for t in tracks if t.has_lyrics])
                },
                'recommendations': self._generate_final_recommendations(tracks)
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Erreur génération résumé traitement: {e}")
            return {}
    
    def _calculate_completeness_score(self, tracks: List[Track]) -> float:
        """Calcule un score de complétude des données"""
        if not tracks:
            return 0.0
        
        completeness_factors = []
        for track in tracks:
            factors = [
                1.0 if track.title else 0.0,
                1.0 if track.artist_name else 0.0,
                1.0 if track.credits else 0.0,
                1.0 if track.duration_seconds else 0.0,
                1.0 if track.album_title else 0.0
            ]
            completeness_factors.append(sum(factors) / len(factors))
        
        return sum(completeness_factors) / len(completeness_factors) * 100
    
    def _calculate_consistency_score(self, tracks: List[Track]) -> float:
        """Calcule un score de cohérence des données"""
        if not tracks:
            return 0.0
        
        consistency_issues = 0
        total_checks = 0
        
        for track in tracks:
            total_checks += 1
            
            # Vérifications de cohérence
            if track.album_id and not track.album_title:
                consistency_issues += 1
            
            if track.album_title and not track.album_id:
                consistency_issues += 1
            
            # Vérification durée/BPM cohérente
            if track.duration_seconds and track.bpm:
                estimated_beats = (track.duration_seconds / 60) * track.bpm
                if estimated_beats < 50 or estimated_beats > 1000:
                    consistency_issues += 1
        
        if total_checks == 0:
            return 100.0
        
        return max(0.0, (1 - consistency_issues / total_checks) * 100)
    
    def _calculate_enrichment_level(self, tracks: List[Track]) -> float:
        """Calcule le niveau d'enrichissement des données"""
        if not tracks:
            return 0.0
        
        enrichment_factors = []
        for track in tracks:
            factors = [
                1.0 if track.bpm else 0.0,
                1.0 if track.key else 0.0,
                1.0 if track.has_lyrics else 0.0,
                1.0 if len(track.credits) >= 2 else 0.0,
                1.0 if track.featuring_artists else 0.0
            ]
            enrichment_factors.append(sum(factors) / len(factors))
        
        return sum(enrichment_factors) / len(enrichment_factors) * 100
    
    def _generate_final_recommendations(self, tracks: List[Track]) -> List[str]:
        """Génère des recommandations finales"""
        recommendations = []
        
        if not tracks:
            return ["Aucune donnée à analyser"]
        
        total = len(tracks)
        
        # Analyse des manques
        tracks_without_credits = len([t for t in tracks if not t.credits])
        tracks_without_bpm = len([t for t in tracks if not t.bpm])
        tracks_without_albums = len([t for t in tracks if not t.album_title])
        
        if tracks_without_credits / total > 0.3:
            recommendations.append(
                f"Améliorer l'extraction des crédits ({tracks_without_credits} tracks sans crédits)"
            )
        
        if tracks_without_bpm / total > 0.5:
            recommendations.append(
                f"Enrichir les données BPM via Spotify ({tracks_without_bpm} tracks sans BPM)"
            )
        
        if tracks_without_albums / total > 0.2:
            recommendations.append(
                f"Compléter les informations d'albums ({tracks_without_albums} tracks sans album)"
            )
        
        # Recommandations générales
        overall_quality = self._calculate_global_quality_score(tracks)
        if overall_quality < 70:
            recommendations.append("Considérer une réextraction complète pour améliorer la qualité")
        elif overall_quality < 85:
            recommendations.append("Optimiser les données existantes avec l'enrichissement automatique")
        
        return recommendations if recommendations else ["Qualité des données satisfaisante"]
    
    def cleanup_processing_data(self, session_id: str):
        """Nettoie les données temporaires du traitement"""
        try:
            # Nettoyage des caches des processeurs
            if hasattr(self.data_cleaner, 'clear_cache'):
                self.data_cleaner._normalized_names_cache.clear()
            
            if hasattr(self.data_enricher, 'clear_cache'):
                self.data_enricher._enrichment_cache.clear()
            
            # Autres nettoyages si nécessaire
            self.logger.info(f"Données de traitement nettoyées pour la session {session_id}")
            
        except Exception as e:
            self.logger.error(f"Erreur nettoyage traitement: {e}")
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques globales de traitement"""
        return {
            'data_cleaner_stats': getattr(self.data_cleaner, 'get_stats', lambda: {})(),
            'data_validator_stats': getattr(self.data_validator, 'get_stats', lambda: {})(),
            'duplicate_detector_stats': getattr(self.duplicate_detector, 'get_stats', lambda: {})(),
            'quality_checker_stats': getattr(self.quality_checker, 'get_stats', lambda: {})(),
            'data_enricher_stats': getattr(self.data_enricher, 'get_stats', lambda: {})(),
            'config': self.config
        }