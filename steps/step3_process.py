# steps/step3_process.py
"""Étape 3: Traitement et validation optimisés des données extraites"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

from core.database import Database
from core.session_manager import SessionManager, get_session_manager
from core.cache import smart_cache
from core.exceptions import DataValidationError, ProcessingError
from models.entities import Artist, Track, Credit, Album, QualityReport
from models.enums import ExtractionStatus, QualityLevel, CreditType, CreditCategory
from config.settings import settings

# Imports conditionnels pour les processeurs
try:
    from processors.data_validator import DataValidator
except ImportError:
    DataValidator = None

try:
    from processors.credit_processor import CreditProcessor
except ImportError:
    CreditProcessor = None

try:
    from processors.text_processor import TextProcessor
except ImportError:
    TextProcessor = None

try:
    from processors.quality_analyzer import QualityAnalyzer
except ImportError:
    QualityAnalyzer = None

@dataclass
class ProcessingBatch:
    """Lot de données pour traitement optimisé"""
    tracks: List[Track]
    batch_id: str
    processing_type: str  # 'validation', 'enrichment', 'quality'
    priority: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

@dataclass
class ProcessingStats:
    """Statistiques détaillées du traitement"""
    total_items: int = 0
    items_processed: int = 0
    items_validated: int = 0
    items_enriched: int = 0
    items_cleaned: int = 0
    
    # Qualité des données
    high_quality_items: int = 0
    medium_quality_items: int = 0
    low_quality_items: int = 0
    
    # Corrections appliquées
    duplicates_removed: int = 0
    data_normalized: int = 0
    missing_data_filled: int = 0
    inconsistencies_fixed: int = 0
    
    # Performance
    processing_time_seconds: float = 0.0
    cache_hits: int = 0
    validation_operations: int = 0
    enrichment_operations: int = 0
    
    # Erreurs et avertissements
    errors_found: int = 0
    warnings_generated: int = 0
    
    @property
    def success_rate(self) -> float:
        """Taux de succès du traitement"""
        if self.items_processed == 0:
            return 0.0
        successful = self.items_validated + self.items_enriched + self.items_cleaned
        return (successful / self.items_processed) * 100
    
    @property
    def quality_score(self) -> float:
        """Score de qualité global (0-100)"""
        if self.items_processed == 0:
            return 0.0
        
        weighted_quality = (
            (self.high_quality_items * 100) +
            (self.medium_quality_items * 70) +
            (self.low_quality_items * 40)
        )
        return weighted_quality / self.items_processed
    
    @property
    def processing_rate(self) -> float:
        """Éléments traités par seconde"""
        if self.processing_time_seconds == 0:
            return 0.0
        return self.items_processed / self.processing_time_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour export"""
        return {
            'total_items': self.total_items,
            'items_processed': self.items_processed,
            'items_validated': self.items_validated,
            'items_enriched': self.items_enriched,
            'items_cleaned': self.items_cleaned,
            'high_quality_items': self.high_quality_items,
            'medium_quality_items': self.medium_quality_items,
            'low_quality_items': self.low_quality_items,
            'duplicates_removed': self.duplicates_removed,
            'data_normalized': self.data_normalized,
            'missing_data_filled': self.missing_data_filled,
            'inconsistencies_fixed': self.inconsistencies_fixed,
            'processing_time_seconds': self.processing_time_seconds,
            'cache_hits': self.cache_hits,
            'validation_operations': self.validation_operations,
            'enrichment_operations': self.enrichment_operations,
            'errors_found': self.errors_found,
            'warnings_generated': self.warnings_generated,
            'success_rate': self.success_rate,
            'quality_score': self.quality_score,
            'processing_rate': self.processing_rate
        }


class ProcessingStep:
    """
    Étape 3: Traitement et validation optimisés des données extraites.
    
    Responsabilités :
    - Validation intelligente des données
    - Nettoyage et normalisation automatiques
    - Enrichissement des données manquantes
    - Analyse de qualité et scoring
    - Détection et correction des incohérences
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None, 
                 database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        
        # Composants core
        self.session_manager = session_manager or get_session_manager()
        self.database = database or Database()
        
        # Processeurs avec vérification de disponibilité
        self.data_validator = DataValidator() if DataValidator else None
        self.credit_processor = CreditProcessor() if CreditProcessor else None
        self.text_processor = TextProcessor() if TextProcessor else None
        self.quality_analyzer = QualityAnalyzer() if QualityAnalyzer else None
        
        # Configuration optimisée
        self.config = self._load_optimized_config()
        
        # Cache pour éviter les retraitements
        self._processing_cache = {}
        self._quality_cache = {}
        
        # Pool de threads pour traitement parallèle
        self.thread_pool = ThreadPoolExecutor(
            max_workers=self.config['max_concurrent_processors']
        )
        
        # Statistiques de performance
        self.performance_stats = {
            'total_processing_sessions': 0,
            'average_processing_time': 0.0,
            'cache_efficiency': 0.0
        }
        
        self.logger.info(f"ProcessingStep optimisé initialisé "
                        f"(Validator: {bool(self.data_validator)}, "
                        f"Credits: {bool(self.credit_processor)}, "
                        f"Text: {bool(self.text_processor)}, "
                        f"Quality: {bool(self.quality_analyzer)})")
    
    def _load_optimized_config(self) -> Dict[str, Any]:
        """Charge la configuration optimisée"""
        return {
            'batch_size': settings.get('processing.batch_size', 20),
            'max_concurrent_processors': settings.get('processing.max_concurrent', 4),
            'validate_data': settings.get('processing.validate_data', True),
            'clean_data': settings.get('processing.clean_data', True),
            'enrich_data': settings.get('processing.enrich_data', True),
            'analyze_quality': settings.get('processing.analyze_quality', True),
            'fix_inconsistencies': settings.get('processing.fix_inconsistencies', True),
            'remove_duplicates': settings.get('processing.remove_duplicates', True),
            'normalize_text': settings.get('processing.normalize_text', True),
            'cache_results': settings.get('processing.cache_results', True),
            'quality_threshold': settings.get('processing.quality_threshold', 70.0),
            'auto_fix_errors': settings.get('processing.auto_fix_errors', True),
            'generate_quality_reports': settings.get('processing.generate_reports', True)
        }
    
    @smart_cache.cache_result("data_processing", expire_days=7)
    async def process_artist_data(self, artist_name: str,
                                session_id: Optional[str] = None,
                                progress_callback: Optional[callable] = None) -> Tuple[Dict[str, Any], ProcessingStats]:
        """
        Traite et valide toutes les données pour un artiste.
        
        Args:
            artist_name: Nom de l'artiste
            session_id: ID de session optionnel
            progress_callback: Callback de progression
            
        Returns:
            Tuple[Dict[str, Any], ProcessingStats]: Données traitées et statistiques
        """
        start_time = datetime.now()
        stats = ProcessingStats()
        
        try:
            # Récupération des données à traiter
            artist = self.database.get_artist_by_name(artist_name)
            if not artist:
                raise ProcessingError(f"Artiste '{artist_name}' non trouvé")
            
            tracks = self.database.get_tracks_by_artist(artist.id)
            credits = self.database.get_credits_by_artist(artist.id)
            albums = self.database.get_albums_by_artist(artist.id)
            
            stats.total_items = len(tracks) + len(credits) + len(albums)
            self.logger.info(f"🔄 Traitement pour {artist_name}: "
                           f"{len(tracks)} morceaux, {len(credits)} crédits, {len(albums)} albums")
            
            # Traitement par phases
            processing_results = {}
            
            # Phase 1: Validation des données
            if self.config['validate_data']:
                validation_results = await self._process_validation_phase(
                    tracks, credits, albums, stats, progress_callback
                )
                processing_results.update(validation_results)
            
            # Phase 2: Nettoyage et normalisation
            if self.config['clean_data']:
                cleaning_results = await self._process_cleaning_phase(
                    tracks, credits, albums, stats, progress_callback
                )
                processing_results.update(cleaning_results)
            
            # Phase 3: Enrichissement des données
            if self.config['enrich_data']:
                enrichment_results = await self._process_enrichment_phase(
                    tracks, credits, albums, stats, progress_callback
                )
                processing_results.update(enrichment_results)
            
            # Phase 4: Analyse de qualité
            if self.config['analyze_quality']:
                quality_results = await self._process_quality_phase(
                    tracks, credits, albums, stats, progress_callback
                )
                processing_results.update(quality_results)
            
            # Finalisation
            end_time = datetime.now()
            stats.processing_time_seconds = (end_time - start_time).total_seconds()
            
            # Mise à jour de l'artiste avec les résultats
            await self._update_artist_processing_status(artist, stats)
            
            # Génération des rapports
            if self.config['generate_quality_reports']:
                quality_report = await self._generate_quality_report(artist, stats)
                processing_results['quality_report'] = quality_report
            
            self._update_performance_stats(stats)
            
            self.logger.info(f"✅ Traitement terminé pour {artist_name}: "
                           f"Score qualité {stats.quality_score:.1f}/100 "
                           f"en {stats.processing_time_seconds:.2f}s")
            
            return processing_results, stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur traitement pour {artist_name}: {e}")
            raise ProcessingError(f"Échec traitement: {e}")
    
    async def _process_validation_phase(self, tracks: List[Track], credits: List[Credit],
                                      albums: List[Album], stats: ProcessingStats,
                                      progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Phase de validation des données"""
        
        validation_results = {
            'validated_tracks': [],
            'validated_credits': [],
            'validated_albums': [],
            'validation_errors': []
        }
        
        if not self.data_validator:
            self.logger.warning("⚠️ DataValidator non disponible")
            return validation_results
        
        self.logger.info("🔍 Phase de validation démarrée")
        
        # Validation des morceaux
        for i, track in enumerate(tracks):
            try:
                validation_result = self._validate_single_track(track)
                if validation_result['is_valid']:
                    validation_results['validated_tracks'].append(validation_result)
                    stats.items_validated += 1
                else:
                    validation_results['validation_errors'].extend(validation_result['errors'])
                    stats.errors_found += len(validation_result['errors'])
                
                stats.validation_operations += 1
                
                if progress_callback and i % 10 == 0:
                    progress = (i / len(tracks)) * 25  # 25% de la progression totale
                    progress_callback("validation", int(progress), 100)
                    
            except Exception as e:
                self.logger.error(f"Erreur validation morceau {track.title}: {e}")
                stats.errors_found += 1
        
        # Validation des crédits
        for credit in credits:
            try:
                credit_validation = self._validate_single_credit(credit)
                if credit_validation['is_valid']:
                    validation_results['validated_credits'].append(credit_validation)
                    stats.items_validated += 1
                else:
                    validation_results['validation_errors'].extend(credit_validation['errors'])
                    stats.errors_found += len(credit_validation['errors'])
                
                stats.validation_operations += 1
                
            except Exception as e:
                self.logger.error(f"Erreur validation crédit: {e}")
                stats.errors_found += 1
        
        stats.items_processed += len(tracks) + len(credits) + len(albums)
        
        self.logger.info(f"✅ Validation terminée: {stats.items_validated} éléments validés, "
                        f"{stats.errors_found} erreurs trouvées")
        
        return validation_results
    
    async def _process_cleaning_phase(self, tracks: List[Track], credits: List[Credit],
                                    albums: List[Album], stats: ProcessingStats,
                                    progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Phase de nettoyage et normalisation"""
        
        cleaning_results = {
            'cleaned_tracks': [],
            'cleaned_credits': [],
            'removed_duplicates': [],
            'normalized_data': []
        }
        
        self.logger.info("🧹 Phase de nettoyage démarrée")
        
        # Suppression des doublons
        if self.config['remove_duplicates']:
            unique_tracks = self._remove_duplicate_tracks(tracks)
            unique_credits = self._remove_duplicate_credits(credits)
            
            duplicates_removed = (len(tracks) - len(unique_tracks)) + (len(credits) - len(unique_credits))
            stats.duplicates_removed = duplicates_removed
            
            tracks = unique_tracks
            credits = unique_credits
            
            cleaning_results['removed_duplicates'] = [
                f"{duplicates_removed} doublons supprimés"
            ]
        
        # Normalisation du texte
        if self.config['normalize_text'] and self.text_processor:
            for track in tracks:
                original_title = track.title
                track.title = self.text_processor.normalize_title(track.title)
                
                if track.lyrics:
                    track.lyrics = self.text_processor.clean_lyrics(track.lyrics)
                
                if original_title != track.title:
                    stats.data_normalized += 1
                    cleaning_results['normalized_data'].append({
                        'track_id': track.id,
                        'field': 'title',
                        'original': original_title,
                        'normalized': track.title
                    })
            
            for credit in credits:
                original_name = credit.person_name
                credit.person_name = self.text_processor.normalize_person_name(credit.person_name)
                
                if original_name != credit.person_name:
                    stats.data_normalized += 1
                    cleaning_results['normalized_data'].append({
                        'credit_id': credit.id,
                        'field': 'person_name',
                        'original': original_name,
                        'normalized': credit.person_name
                    })
        
        # Correction des incohérences
        if self.config['fix_inconsistencies']:
            inconsistencies_fixed = self._fix_data_inconsistencies(tracks, credits)
            stats.inconsistencies_fixed = inconsistencies_fixed
        
        # Remplissage des données manquantes
        missing_data_filled = self._fill_missing_data(tracks, credits)
        stats.missing_data_filled = missing_data_filled
        
        stats.items_cleaned = len(tracks) + len(credits)
        
        self.logger.info(f"✅ Nettoyage terminé: {stats.duplicates_removed} doublons, "
                        f"{stats.data_normalized} normalisations, "
                        f"{stats.inconsistencies_fixed} corrections")
        
        return cleaning_results
    
    async def _process_enrichment_phase(self, tracks: List[Track], credits: List[Credit],
                                      albums: List[Album], stats: ProcessingStats,
                                      progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Phase d'enrichissement des données"""
        
        enrichment_results = {
            'enriched_tracks': [],
            'enriched_credits': [],
            'new_relationships': []
        }
        
        self.logger.info("🔗 Phase d'enrichissement démarrée")
        
        # Enrichissement des crédits
        if self.credit_processor:
            for credit in credits:
                try:
                    enhanced_credit = self.credit_processor.enhance_credit(credit)
                    if enhanced_credit:
                        enrichment_results['enriched_credits'].append(enhanced_credit)
                        stats.items_enriched += 1
                        stats.enrichment_operations += 1
                        
                except Exception as e:
                    self.logger.warning(f"Erreur enrichissement crédit: {e}")
        
        # Détection de nouvelles relations
        new_relationships = self._detect_credit_relationships(tracks, credits)
        enrichment_results['new_relationships'] = new_relationships
        stats.enrichment_operations += len(new_relationships)
        
        self.logger.info(f"✅ Enrichissement terminé: {stats.items_enriched} éléments enrichis, "
                        f"{len(new_relationships)} nouvelles relations")
        
        return enrichment_results
    
    async def _process_quality_phase(self, tracks: List[Track], credits: List[Credit],
                                   albums: List[Album], stats: ProcessingStats,
                                   progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Phase d'analyse de qualité"""
        
        quality_results = {
            'quality_scores': [],
            'quality_reports': [],
            'recommendations': []
        }
        
        if not self.quality_analyzer:
            self.logger.warning("⚠️ QualityAnalyzer non disponible")
            return quality_results
        
        self.logger.info("⭐ Phase d'analyse qualité démarrée")
        
        # Analyse qualité des morceaux
        for track in tracks:
            quality_score = self._analyze_track_quality(track)
            track.quality_score = quality_score.score
            track.quality_level = quality_score.level
            
            quality_results['quality_scores'].append({
                'track_id': track.id,
                'score': quality_score.score,
                'level': quality_score.level.value
            })
            
            # Comptage par niveau de qualité
            if quality_score.level == QualityLevel.HIGH or quality_score.level == QualityLevel.EXCELLENT:
                stats.high_quality_items += 1
            elif quality_score.level == QualityLevel.MEDIUM:
                stats.medium_quality_items += 1
            else:
                stats.low_quality_items += 1
        
        # Analyse qualité des crédits
        for credit in credits:
            quality_score = self._analyze_credit_quality(credit)
            credit.confidence_score = quality_score.score / 100  # Conversion en 0-1
            
            if quality_score.score >= 80:
                stats.high_quality_items += 1
            elif quality_score.score >= 60:
                stats.medium_quality_items += 1
            else:
                stats.low_quality_items += 1
        
        # Génération de recommandations
        recommendations = self._generate_quality_recommendations(tracks, credits, stats)
        quality_results['recommendations'] = recommendations
        
        self.logger.info(f"✅ Analyse qualité terminée: "
                        f"Score global {stats.quality_score:.1f}/100")
        
        return quality_results
    
    @lru_cache(maxsize=512)
    def _validate_single_track(self, track: Track) -> Dict[str, Any]:
        """Valide un morceau unique - avec cache"""
        validation_result = {
            'track_id': track.id,
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Validation des champs obligatoires
        if not track.title or not track.title.strip():
            validation_result['errors'].append("Titre manquant")
            validation_result['is_valid'] = False
        
        if not track.artist_name or not track.artist_name.strip():
            validation_result['errors'].append("Nom d'artiste manquant")
            validation_result['is_valid'] = False
        
        # Validation de la durée
        if track.duration_seconds is not None:
            if track.duration_seconds < 10:
                validation_result['warnings'].append("Durée très courte")
            elif track.duration_seconds > 1800:  # 30 minutes
                validation_result['warnings'].append("Durée très longue")
        
        # Validation du BPM
        if track.bpm is not None:
            if track.bpm < 60 or track.bpm > 200:
                validation_result['warnings'].append("BPM suspect")
        
        return validation_result
    
    @lru_cache(maxsize=512)
    def _validate_single_credit(self, credit: Credit) -> Dict[str, Any]:
        """Valide un crédit unique - avec cache"""
        validation_result = {
            'credit_id': credit.id,
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Validation des champs obligatoires
        if not credit.person_name or not credit.person_name.strip():
            validation_result['errors'].append("Nom de personne manquant")
            validation_result['is_valid'] = False
        
        if credit.credit_type == CreditType.UNKNOWN:
            validation_result['warnings'].append("Type de crédit non spécifié")
        
        # Validation de la cohérence
        if credit.credit_category == CreditCategory.UNKNOWN:
            validation_result['warnings'].append("Catégorie de crédit non spécifiée")
        
        return validation_result
    
    def _remove_duplicate_tracks(self, tracks: List[Track]) -> List[Track]:
        """Supprime les morceaux en double"""
        seen_signatures = set()
        unique_tracks = []
        
        for track in tracks:
            signature = f"{track.artist_name.lower()}|{track.title.lower()}"
            if signature not in seen_signatures:
                unique_tracks.append(track)
                seen_signatures.add(signature)
        
        return unique_tracks
    
    def _remove_duplicate_credits(self, credits: List[Credit]) -> List[Credit]:
        """Supprime les crédits en double"""
        seen_signatures = set()
        unique_credits = []
        
        for credit in credits:
            signature = f"{credit.track_id}|{credit.person_name.lower()}|{credit.credit_type.value}"
            if signature not in seen_signatures:
                unique_credits.append(credit)
                seen_signatures.add(signature)
        
        return unique_credits
    
    def _fix_data_inconsistencies(self, tracks: List[Track], credits: List[Credit]) -> int:
        """Corrige les incohérences dans les données"""
        fixes_applied = 0
        
        # Correction des noms d'artistes incohérents
        track_artists = {}
        for track in tracks:
            if track.artist_id not in track_artists:
                track_artists[track.artist_id] = []
            track_artists[track.artist_id].append(track.artist_name)
        
        for artist_id, names in track_artists.items():
            if len(set(names)) > 1:
                # Utiliser le nom le plus fréquent
                most_common_name = max(set(names), key=names.count)
                for track in tracks:
                    if track.artist_id == artist_id and track.artist_name != most_common_name:
                        track.artist_name = most_common_name
                        fixes_applied += 1
        
        return fixes_applied
    
    def _fill_missing_data(self, tracks: List[Track], credits: List[Credit]) -> int:
        """Remplit les données manquantes quand possible"""
        filled_count = 0
        
        # Remplir les album_name manquants si on a l'album_id
        for track in tracks:
            if track.album_id and not track.album_name:
                album = self.database.get_album(track.album_id)
                if album:
                    track.album_name = album.title
                    filled_count += 1
        
        return filled_count
    
    def _detect_credit_relationships(self, tracks: List[Track], credits: List[Credit]) -> List[Dict]:
        """Détecte de nouvelles relations entre crédits"""
        relationships = []
        
        # Grouper les crédits par personne
        person_credits = {}
        for credit in credits:
            person_name = credit.person_name.lower()
            if person_name not in person_credits:
                person_credits[person_name] = []
            person_credits[person_name].append(credit)
        
        # Détecter les collaborations fréquentes
        for person_name, person_credit_list in person_credits.items():
            if len(person_credit_list) >= 3:  # Au moins 3 crédits
                relationships.append({
                    'type': 'frequent_collaborator',
                    'person': person_name,
                    'credit_count': len(person_credit_list),
                    'credit_types': list(set(c.credit_type.value for c in person_credit_list))
                })
        
        return relationships
    
    def _analyze_track_quality(self, track: Track) -> QualityReport:
        """Analyse la qualité d'un morceau"""
        score = 100.0
        issues = []
        
        # Déductions pour données manquantes
        if not track.lyrics:
            score -= 20
            issues.append("Paroles manquantes")
        
        if not track.duration_seconds:
            score -= 15
            issues.append("Durée manquante")
        
        if not track.bpm:
            score -= 10
            issues.append("BPM manquant")
        
        if not track.album_name:
            score -= 10
            issues.append("Album manquant")
        
        # Bonus pour données riches
        if track.genius_id and track.spotify_id:
            score += 5
        
        if track.metadata and len(track.metadata) > 3:
            score += 5
        
        # Déterminer le niveau de qualité
        level = QualityLevel.from_score(score)
        
        return QualityReport(
            entity_type="track",
            entity_id=track.id,
            quality_level=level,
            quality_score=max(0, min(100, score)),
            missing_fields=[issue for issue in issues if "manquant" in issue],
            checked_at=datetime.now()
        )
    
    def _analyze_credit_quality(self, credit: Credit) -> QualityReport:
        """Analyse la qualité d'un crédit"""
        score = 100.0
        issues = []
        
        # Déductions pour données manquantes ou imprécises
        if credit.credit_type == CreditType.UNKNOWN:
            score -= 30
            issues.append("Type de crédit inconnu")
        
        if credit.credit_category == CreditCategory.UNKNOWN:
            score -= 20
            issues.append("Catégorie de crédit inconnue")
        
        if not credit.role_detail and credit.credit_type == CreditType.OTHER_INSTRUMENT:
            score -= 15
            issues.append("Détail de rôle manquant pour instrument")
        
        # Bonus pour données riches
        if credit.confidence_score > 0.8:
            score += 10
        
        if credit.source != 'unknown':
            score += 5
        
        level = QualityLevel.from_score(score)
        
        return QualityReport(
            entity_type="credit",
            entity_id=credit.id,
            quality_level=level,
            quality_score=max(0, min(100, score)),
            missing_fields=[issue for issue in issues if "manquant" in issue],
            checked_at=datetime.now()
        )
    
    def _generate_quality_recommendations(self, tracks: List[Track], 
                                        credits: List[Credit], 
                                        stats: ProcessingStats) -> List[str]:
        """Génère des recommandations pour améliorer la qualité"""
        recommendations = []
        
        # Recommandations basées sur les stats
        if stats.quality_score < 70:
            recommendations.append("Score de qualité faible - considérer une re-extraction")
        
        if stats.errors_found > len(tracks) * 0.1:  # Plus de 10% d'erreurs
            recommendations.append("Taux d'erreur élevé - vérifier les sources de données")
        
        # Recommandations spécifiques
        tracks_without_lyrics = sum(1 for t in tracks if not t.lyrics)
        if tracks_without_lyrics > len(tracks) * 0.5:
            recommendations.append(f"{tracks_without_lyrics} morceaux sans paroles - enrichir via Genius")
        
        tracks_without_bpm = sum(1 for t in tracks if not t.bpm)
        if tracks_without_bpm > len(tracks) * 0.3:
            recommendations.append(f"{tracks_without_bpm} morceaux sans BPM - enrichir via Spotify")
        
        return recommendations
    
    async def _update_artist_processing_status(self, artist: Artist, stats: ProcessingStats):
        """Met à jour le statut de traitement de l'artiste"""
        # Mettre à jour les métadonnées de l'artiste
        if not artist.metadata:
            artist.metadata = {}
        
        artist.metadata['processing_stats'] = stats.to_dict()
        artist.metadata['last_processed'] = datetime.now().isoformat()
        artist.metadata['quality_score'] = stats.quality_score
        
        artist.updated_at = datetime.now()
        self.database.update_artist(artist)
    
    async def _generate_quality_report(self, artist: Artist, stats: ProcessingStats) -> Dict[str, Any]:
        """Génère un rapport de qualité complet"""
        return {
            'artist_id': artist.id,
            'artist_name': artist.name,
            'processing_date': datetime.now().isoformat(),
            'statistics': stats.to_dict(),
            'quality_level': 'HIGH' if stats.quality_score >= 80 else 'MEDIUM' if stats.quality_score >= 60 else 'LOW',
            'recommendations': self._generate_quality_recommendations([], [], stats)
        }
    
    def _update_performance_stats(self, stats: ProcessingStats):
        """Met à jour les statistiques de performance globales"""
        self.performance_stats['total_processing_sessions'] += 1
        
        # Moyenne mobile du temps de traitement
        current_avg = self.performance_stats['average_processing_time']
        total_count = self.performance_stats['total_processing_sessions']
        
        new_avg = ((current_avg * (total_count - 1)) + stats.processing_time_seconds) / total_count
        self.performance_stats['average_processing_time'] = new_avg
        
        # Efficacité du cache
        if stats.cache_hits + stats.validation_operations > 0:
            cache_rate = (stats.cache_hits / (stats.cache_hits + stats.validation_operations)) * 100
            self.performance_stats['cache_efficiency'] = cache_rate
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance"""
        return {
            **self.performance_stats,
            'processors_available': {
                'validator': bool(self.data_validator),
                'credit_processor': bool(self.credit_processor),
                'text_processor': bool(self.text_processor),
                'quality_analyzer': bool(self.quality_analyzer)
            },
            'config': self.config,
            'cache_size': len(self._processing_cache),
            'quality_cache_size': len(self._quality_cache)
        }
    
    def reset_performance_stats(self):
        """Remet à zéro les statistiques et caches"""
        self.performance_stats = {
            'total_processing_sessions': 0,
            'average_processing_time': 0.0,
            'cache_efficiency': 0.0
        }
        
        self._processing_cache.clear()
        self._quality_cache.clear()
        
        self.logger.info("🔄 Statistiques de traitement remises à zéro")
    
    def __del__(self):
        """Nettoyage lors de la destruction"""
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=True)