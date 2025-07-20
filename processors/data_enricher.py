# processors/data_enricher.py
"""
Module d'enrichissement des données pour Music Data Extractor.
Améliore la qualité et la complétude des données extraites.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

from models.entities import Track, Credit, Artist, Album
from models.enums import CreditType, CreditCategory, DataSource, QualityLevel
from core.database import Database
from config.settings import settings
from utils.text_utils import normalize_text, calculate_similarity


class EnrichmentType(Enum):
    """Types d'enrichissement disponibles"""
    METADATA = "metadata"           # Métadonnées générales
    CREDITS = "credits"             # Crédits détaillés
    TECHNICAL = "technical"         # Données techniques (BPM, key, etc.)
    LYRICS = "lyrics"              # Paroles
    FEATURES = "features"          # Caractéristiques audio
    RELATIONSHIPS = "relationships" # Relations entre entités
    INFERENCE = "inference"        # Données inférées


class EnrichmentSource(Enum):
    """Sources d'enrichissement"""
    EXTERNAL_API = "external_api"
    DATABASE = "database"
    INFERENCE = "inference"
    USER_INPUT = "user_input"
    CROSS_REFERENCE = "cross_reference"


@dataclass
class EnrichmentResult:
    """Résultat d'un enrichissement"""
    entity_id: int
    entity_type: str
    field: str
    original_value: Any
    enriched_value: Any
    enrichment_type: EnrichmentType
    source: EnrichmentSource
    confidence: float
    success: bool
    message: str
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class DataEnricher:
    """
    Enrichisseur de données pour améliorer la qualité et complétude.
    
    Fonctionnalités:
    - Enrichissement des métadonnées manquantes
    - Inférence de données à partir du contexte
    - Cross-référencement entre sources
    - Validation et amélioration de la qualité
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.database = Database()
        
        # Configuration
        self.config = {
            'min_confidence': settings.get('enrichment.min_confidence', 0.7),
            'enable_inference': settings.get('enrichment.enable_inference', True),
            'batch_size': settings.get('enrichment.batch_size', 50),
            'cache_results': settings.get('enrichment.cache_results', True)
        }
        
        # Statistiques
        self.stats = {
            'total_enrichments': 0,
            'successful_enrichments': 0,
            'failed_enrichments': 0,
            'fields_enriched': defaultdict(int),
            'sources_used': defaultdict(int)
        }
    
    def enrich_track(self, track: Track, enrichment_types: Optional[List[EnrichmentType]] = None) -> List[EnrichmentResult]:
        """
        Enrichit les données d'un track.
        
        Args:
            track: Track à enrichir
            enrichment_types: Types d'enrichissement à appliquer
            
        Returns:
            Liste des résultats d'enrichissement
        """
        if enrichment_types is None:
            enrichment_types = list(EnrichmentType)
        
        results = []
        
        for enrichment_type in enrichment_types:
            try:
                if enrichment_type == EnrichmentType.METADATA:
                    results.extend(self._enrich_metadata(track))
                elif enrichment_type == EnrichmentType.CREDITS:
                    results.extend(self._enrich_credits(track))
                elif enrichment_type == EnrichmentType.TECHNICAL:
                    results.extend(self._enrich_technical_data(track))
                elif enrichment_type == EnrichmentType.INFERENCE:
                    results.extend(self._enrich_by_inference(track))
                    
            except Exception as e:
                self.logger.error(f"Erreur enrichissement {enrichment_type} pour track {track.id}: {e}")
                results.append(EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    field=enrichment_type.value,
                    original_value=None,
                    enriched_value=None,
                    enrichment_type=enrichment_type,
                    source=EnrichmentSource.EXTERNAL_API,
                    confidence=0.0,
                    success=False,
                    message=str(e)
                ))
        
        # Mettre à jour les stats
        self._update_stats(results)
        
        return results
    
    def _enrich_metadata(self, track: Track) -> List[EnrichmentResult]:
        """Enrichit les métadonnées du track"""
        results = []
        
        # Enrichir l'album si manquant
        if not track.album_title and track.album_id:
            album = self.database.get_album_by_id(track.album_id)
            if album:
                results.append(EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    field="album_title",
                    original_value=None,
                    enriched_value=album.title,
                    enrichment_type=EnrichmentType.METADATA,
                    source=EnrichmentSource.DATABASE,
                    confidence=1.0,
                    success=True,
                    message="Album trouvé dans la base de données"
                ))
                
                # Mettre à jour le track
                track.album_title = album.title
                self.database.update_track(track)
        
        # Enrichir la date de sortie
        if not track.release_date and track.album_id:
            album = self.database.get_album_by_id(track.album_id)
            if album and album.release_date:
                results.append(EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    field="release_date",
                    original_value=None,
                    enriched_value=album.release_date,
                    enrichment_type=EnrichmentType.METADATA,
                    source=EnrichmentSource.DATABASE,
                    confidence=0.9,
                    success=True,
                    message="Date inférée depuis l'album"
                ))
        
        return results
    
    def _enrich_credits(self, track: Track) -> List[EnrichmentResult]:
        """Enrichit les crédits du track"""
        results = []
        
        # Vérifier si le track a un producteur
        has_producer = any(
            credit.credit_type == CreditType.PRODUCER 
            for credit in track.credits
        )
        
        if not has_producer:
            # Essayer d'inférer le producteur depuis d'autres tracks du même album
            if track.album_id:
                similar_tracks = self.database.get_tracks_by_album_id(track.album_id)
                
                # Chercher des patterns de producteurs
                producer_counts = defaultdict(int)
                for similar_track in similar_tracks:
                    if similar_track.id != track.id:
                        for credit in similar_track.credits:
                            if credit.credit_type == CreditType.PRODUCER:
                                producer_counts[credit.person_name] += 1
                
                # Si un producteur revient souvent, l'inférer
                if producer_counts:
                    most_common_producer = max(producer_counts, key=producer_counts.get)
                    confidence = producer_counts[most_common_producer] / len(similar_tracks)
                    
                    if confidence >= self.config['min_confidence']:
                        results.append(EnrichmentResult(
                            entity_id=track.id,
                            entity_type="track",
                            field="producer",
                            original_value=None,
                            enriched_value=most_common_producer,
                            enrichment_type=EnrichmentType.CREDITS,
                            source=EnrichmentSource.INFERENCE,
                            confidence=confidence,
                            success=True,
                            message=f"Producteur inféré depuis l'album (confiance: {confidence:.2f})"
                        ))
        
        return results
    
    def _enrich_technical_data(self, track: Track) -> List[EnrichmentResult]:
        """Enrichit les données techniques du track"""
        results = []
        
        # BPM manquant
        if not track.bpm:
            # Inférer depuis le genre ou des tracks similaires
            inferred_bpm = self._infer_bpm_from_context(track)
            if inferred_bpm:
                results.append(EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    field="bpm",
                    original_value=None,
                    enriched_value=inferred_bpm['value'],
                    enrichment_type=EnrichmentType.TECHNICAL,
                    source=EnrichmentSource.INFERENCE,
                    confidence=inferred_bpm['confidence'],
                    success=True,
                    message=inferred_bpm['message']
                ))
        
        return results
    
    def _enrich_by_inference(self, track: Track) -> List[EnrichmentResult]:
        """Enrichit par inférence depuis le contexte"""
        results = []
        
        if not self.config['enable_inference']:
            return results
        
        # Inférer le genre si manquant
        if not track.genres:
            inferred_genres = self._infer_genres(track)
            if inferred_genres:
                results.append(EnrichmentResult(
                    entity_id=track.id,
                    entity_type="track",
                    field="genres",
                    original_value=[],
                    enriched_value=inferred_genres['genres'],
                    enrichment_type=EnrichmentType.INFERENCE,
                    source=EnrichmentSource.INFERENCE,
                    confidence=inferred_genres['confidence'],
                    success=True,
                    message="Genres inférés depuis l'artiste et le contexte"
                ))
        
        return results
    
    def _infer_bpm_from_context(self, track: Track) -> Optional[Dict[str, Any]]:
        """Infère le BPM depuis le contexte"""
        # Logique simplifiée - à améliorer
        genre_bpm_ranges = {
            'hip-hop': (80, 100),
            'rap': (80, 100),
            'trap': (130, 150),
            'drill': (140, 145),
            'boom bap': (85, 95)
        }
        
        for genre in track.genres:
            genre_lower = genre.lower()
            for key, (min_bpm, max_bpm) in genre_bpm_ranges.items():
                if key in genre_lower:
                    avg_bpm = (min_bpm + max_bpm) // 2
                    return {
                        'value': avg_bpm,
                        'confidence': 0.6,
                        'message': f"BPM estimé depuis le genre {genre}"
                    }
        
        return None
    
    def _infer_genres(self, track: Track) -> Optional[Dict[str, Any]]:
        """Infère les genres depuis le contexte"""
        # Obtenir les genres de l'artiste
        artist = self.database.get_artist_by_id(track.artist_id)
        if artist and artist.genres:
            return {
                'genres': artist.genres,
                'confidence': 0.8
            }
        
        return None
    
    def _update_stats(self, results: List[EnrichmentResult]):
        """Met à jour les statistiques"""
        for result in results:
            self.stats['total_enrichments'] += 1
            
            if result.success:
                self.stats['successful_enrichments'] += 1
                self.stats['fields_enriched'][result.field] += 1
                self.stats['sources_used'][result.source.value] += 1
            else:
                self.stats['failed_enrichments'] += 1
    
    def enrich_artist_data(self, artist_id: int) -> Dict[str, Any]:
        """
        Enrichit toutes les données d'un artiste.
        
        Args:
            artist_id: ID de l'artiste
            
        Returns:
            Résumé de l'enrichissement
        """
        try:
            # Obtenir tous les tracks de l'artiste
            tracks = self.database.get_tracks_by_artist_id(artist_id)
            
            all_results = []
            enriched_tracks = 0
            
            for track in tracks:
                results = self.enrich_track(track)
                if any(r.success for r in results):
                    enriched_tracks += 1
                all_results.extend(results)
            
            # Générer le résumé
            successful = [r for r in all_results if r.success]
            failed = [r for r in all_results if not r.success]
            
            return {
                'artist_id': artist_id,
                'total_tracks': len(tracks),
                'enriched_tracks': enriched_tracks,
                'total_enrichments': len(all_results),
                'successful_enrichments': len(successful),
                'failed_enrichments': len(failed),
                'success_rate': len(successful) / len(all_results) * 100 if all_results else 0,
                'enrichments_by_type': self._group_by_type(successful),
                'enrichments_by_source': self._group_by_source(successful),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur enrichissement artiste {artist_id}: {e}")
            return {'error': str(e)}
    
    def _group_by_type(self, results: List[EnrichmentResult]) -> Dict[str, int]:
        """Groupe les résultats par type"""
        grouped = defaultdict(int)
        for result in results:
            grouped[result.enrichment_type.value] += 1
        return dict(grouped)
    
    def _group_by_source(self, results: List[EnrichmentResult]) -> Dict[str, int]:
        """Groupe les résultats par source"""
        grouped = defaultdict(int)
        for result in results:
            grouped[result.source.value] += 1
        return dict(grouped)
    
    def generate_enrichment_report(self, results: List[EnrichmentResult]) -> Dict[str, Any]:
        """
        Génère un rapport détaillé sur les enrichissements.
        
        Args:
            results: Liste des résultats d'enrichissement
            
        Returns:
            Rapport détaillé
        """
        try:
            if not results:
                return {'message': 'Aucun enrichissement à rapporter'}
            
            # Séparer succès et échecs
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
            
            # Statistiques globales
            total_results = len(results)
            success_rate = len(successful) / total_results * 100 if total_results else 0
            
            # Grouper par différents critères
            by_enrichment_type = defaultdict(list)
            by_source = defaultdict(list)
            by_field = defaultdict(list)
            
            for result in results:
                by_enrichment_type[result.enrichment_type.value].append(result)
                by_source[result.source.value].append(result)
                by_field[result.field].append(result)
            
            # Top améliorations (par confiance)
            top_improvements = sorted(successful, key=lambda r: r.confidence, reverse=True)[:10]
            
            # Analyse des échecs
            failure_reasons = {}
            for result in failed:
                reason = result.message
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
            
            # Calcul score de confiance moyen
            if successful:
                avg_confidence = sum(r.confidence for r in successful) / len(successful)
            else:
                avg_confidence = 0.0
            
            return {
                'summary': {
                    'total_enrichments': total_results,
                    'successful': len(successful),
                    'failed': len(failed),
                    'success_rate': round(success_rate, 1),
                    'average_confidence': round(avg_confidence, 2)
                },
                'by_enrichment_type': {k: len(v) for k, v in by_enrichment_type.items()},
                'by_source': {k: len(v) for k, v in by_source.items()},
                'by_field': {k: len(v) for k, v in by_field.items()},
                'top_improvements': [
                    {
                        'entity_id': r.entity_id,
                        'entity_type': r.entity_type,
                        'field': r.field,
                        'enrichment_type': r.enrichment_type.value,
                        'source': r.source.value,
                        'confidence': r.confidence,
                        'message': r.message
                    }
                    for r in top_improvements
                ],
                'failure_analysis': failure_reasons,
                'recommendations': self._generate_enrichment_recommendations(results),
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur génération rapport: {e}")
            return {'error': f'Erreur lors de la génération du rapport: {e}'}
    
    def _generate_enrichment_recommendations(self, results: List[EnrichmentResult]) -> List[str]:
        """Génère des recommandations basées sur les résultats"""
        recommendations = []
        
        try:
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
            
            # Analyser les échecs
            if failed:
                failure_rate = len(failed) / len(results) * 100
                if failure_rate > 20:
                    recommendations.append(f"Taux d'échec élevé ({failure_rate:.1f}%) - Vérifier la configuration")
                
                # Analyser les types d'échecs
                failed_types = {}
                for result in failed:
                    etype = result.enrichment_type.value
                    failed_types[etype] = failed_types.get(etype, 0) + 1
                
                if failed_types:
                    worst_type = max(failed_types.items(), key=lambda x: x[1])
                    recommendations.append(f"Type d'enrichissement le plus problématique: {worst_type[0]}")
            
            # Recommandations générales
            if len(successful) > 0:
                avg_confidence = sum(r.confidence for r in successful) / len(successful)
                if avg_confidence < 0.7:
                    recommendations.append("Confiance moyenne faible - Améliorer les algorithmes d'inférence")
            
            inference_count = sum(1 for r in successful if r.source == EnrichmentSource.INFERENCE)
            if inference_count > len(successful) * 0.7:
                recommendations.append("Forte dépendance à l'inférence - Considérer plus de sources externes")
            
        except Exception as e:
            self.logger.warning(f"Erreur génération recommandations: {e}")
            recommendations.append("Erreur lors de la génération des recommandations")
        
        return recommendations
    
    def suggest_enrichment_priorities(self, artist_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Suggère des priorités d'enrichissement.
        
        Args:
            artist_id: ID de l'artiste (optionnel)
            
        Returns:
            Suggestions de priorités
        """
        try:
            if artist_id:
                tracks = self.database.get_tracks_by_artist_id(artist_id)
                scope = f"Artiste {artist_id}"
            else:
                # Analyser un échantillon global
                with self.database.get_connection() as conn:
                    cursor = conn.execute("""
                        SELECT * FROM tracks 
                        ORDER BY RANDOM() 
                        LIMIT 1000
                    """)
                    tracks = [self.database._row_to_track(row) for row in cursor.fetchall()]
                scope = "Échantillon global"
            
            if not tracks:
                return {'error': 'Aucun track à analyser'}
            
            # Analyser les données manquantes
            missing_data = {
                'album': 0,
                'release_date': 0,
                'duration': 0,
                'bpm': 0,
                'key': 0,
                'genres': 0,
                'producer': 0,
                'lyrics': 0
            }
            
            for track in tracks:
                if not track.album_title:
                    missing_data['album'] += 1
                if not track.release_date:
                    missing_data['release_date'] += 1
                if not track.duration_seconds:
                    missing_data['duration'] += 1
                if not track.bpm:
                    missing_data['bpm'] += 1
                if not track.key:
                    missing_data['key'] += 1
                if not track.genres:
                    missing_data['genres'] += 1
                if not track.has_lyrics:
                    missing_data['lyrics'] += 1
                
                # Vérifier le producteur
                has_producer = any(
                    credit.credit_type == CreditType.PRODUCER 
                    for credit in track.credits
                )
                if not has_producer:
                    missing_data['producer'] += 1
            
            total_tracks = len(tracks)
            
            # Calculer les priorités
            priorities = []
            for field, count in missing_data.items():
                if count > 0:
                    percentage = (count / total_tracks) * 100
                    priority = self._calculate_priority(field, percentage)
                    
                    priorities.append({
                        'field': field,
                        'missing_count': count,
                        'percentage': round(percentage, 1),
                        'priority': priority,
                        'effort': self._estimate_effort(field),
                        'potential_sources': self._get_potential_sources(field)
                    })
            
            # Trier par priorité
            priority_order = {'High': 0, 'Medium': 1, 'Low': 2, 'Optional': 3}
            priorities.sort(key=lambda x: (priority_order.get(x['priority'], 4), -x['percentage']))
            
            # Suggestions d'actions
            action_plan = []
            high_priority = [p for p in priorities if p['priority'] == 'High']
            
            if high_priority:
                action_plan.append({
                    'phase': 'Phase 1 - Urgent',
                    'actions': [f"Enrichir {p['field']} ({p['missing_count']} tracks)" for p in high_priority],
                    'estimated_impact': 'High'
                })
            
            medium_priority = [p for p in priorities if p['priority'] == 'Medium']
            if medium_priority:
                action_plan.append({
                    'phase': 'Phase 2 - Important',
                    'actions': [f"Enrichir {p['field']} ({p['missing_count']} tracks)" for p in medium_priority],
                    'estimated_impact': 'Medium'
                })
            
            # Calcul du score de complétude global
            total_possible_fields = len(missing_data)
            fields_with_data = sum(1 for count in missing_data.values() if count < total_tracks * 0.5)
            completeness_score = (fields_with_data / total_possible_fields) * 100
            
            return {
                'scope': scope,
                'total_tracks_analyzed': total_tracks,
                'completeness_score': round(completeness_score, 1),
                'missing_data_analysis': missing_data,
                'enrichment_priorities': priorities,
                'action_plan': action_plan,
                'recommendations': [
                    "Commencer par les champs à haute priorité",
                    "Utiliser des sources multiples pour améliorer la confiance",
                    "Valider les enrichissements avant sauvegarde"
                ],
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur analyse priorités: {e}")
            return {'error': f'Erreur lors de l\'analyse: {e}'}
    
    def _calculate_priority(self, field: str, missing_percentage: float) -> str:
        """Calcule la priorité d'un champ"""
        # Champs critiques
        critical_fields = ['producer', 'album', 'duration']
        
        if field in critical_fields and missing_percentage > 20:
            return 'High'
        elif missing_percentage > 50:
            return 'High'
        elif missing_percentage > 30:
            return 'Medium'
        elif missing_percentage > 10:
            return 'Low'
        else:
            return 'Optional'
    
    def _estimate_effort(self, field: str) -> str:
        """Estime l'effort nécessaire pour enrichir un champ"""
        effort_map = {
            'album': 'Low',
            'release_date': 'Low',
            'duration': 'Low',
            'bpm': 'Medium',
            'key': 'Medium',
            'genres': 'Low',
            'producer': 'High',
            'lyrics': 'High'
        }
        return effort_map.get(field, 'Medium')
    
    def _get_potential_sources(self, field: str) -> List[str]:
        """Retourne les sources potentielles pour un champ"""
        sources_map = {
            'album': ['Database', 'Spotify', 'Discogs'],
            'release_date': ['Database', 'Spotify', 'Discogs'],
            'duration': ['Spotify', 'YouTube'],
            'bpm': ['Spotify', 'Essentia', 'Inference'],
            'key': ['Spotify', 'Essentia'],
            'genres': ['Database', 'Spotify', 'LastFM', 'Inference'],
            'producer': ['Genius', 'Discogs', 'Database'],
            'lyrics': ['Genius', 'Musixmatch']
        }
        return sources_map.get(field, ['External API'])
    
    def create_enrichment_plan(self, artist_id: int, target_completeness: float = 80.0) -> Dict[str, Any]:
        """
        Crée un plan d'enrichissement détaillé pour atteindre un niveau de complétude cible.
        
        Args:
            artist_id: ID de l'artiste
            target_completeness: Niveau de complétude cible (0-100)
            
        Returns:
            Plan d'enrichissement détaillé
        """
        try:
            priorities = self.suggest_enrichment_priorities(artist_id)
            
            if 'error' in priorities:
                return priorities
            
            current_completeness = priorities['completeness_score']
            tracks_count = priorities['total_tracks_analyzed']
            
            if current_completeness >= target_completeness:
                return {
                    'message': f'Complétude actuelle ({current_completeness}%) déjà supérieure à la cible ({target_completeness}%)',
                    'current_completeness': current_completeness,
                    'target_completeness': target_completeness
                }
            
            # Calculer les enrichissements nécessaires
            enrichment_tasks = []
            estimated_improvements = 0
            
            for priority in priorities['enrichment_priorities']:
                if estimated_improvements + current_completeness >= target_completeness:
                    break
                
                field = priority['field']
                missing_count = priority['missing_count']
                
                # Estimer l'amélioration de complétude
                field_weight = self._get_field_weight(field)
                potential_improvement = (missing_count / tracks_count) * field_weight
                
                enrichment_tasks.append({
                    'field': field,
                    'tracks_to_enrich': missing_count,
                    'priority': priority['priority'],
                    'effort': priority['effort'],
                    'sources': priority['potential_sources'],
                    'estimated_improvement': round(potential_improvement, 1),
                    'estimated_time': self._estimate_enrichment_time(field, missing_count)
                })
                
                estimated_improvements += potential_improvement
            
            # Calcul des coûts et bénéfices
            total_estimated_time = sum(task['estimated_time'] for task in enrichment_tasks)
            expected_final_completeness = min(100.0, current_completeness + estimated_improvements)
            
            return {
                'artist_id': artist_id,
                'current_completeness': current_completeness,
                'target_completeness': target_completeness,
                'expected_final_completeness': round(expected_final_completeness, 1),
                'enrichment_tasks': enrichment_tasks,
                'execution_plan': {
                    'total_tasks': len(enrichment_tasks),
                    'estimated_total_time_hours': round(total_estimated_time, 1),
                    'high_priority_tasks': len([t for t in enrichment_tasks if t['priority'] == 'High']),
                    'external_api_calls_needed': self._estimate_api_calls(enrichment_tasks)
                },
                'recommendations': [
                    "Commencer par les tâches haute priorité",
                    "Utiliser l'inférence quand possible pour réduire les coûts",
                    "Valider les enrichissements avec des sources multiples"
                ],
                'created_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur création plan enrichissement: {e}")
            return {'error': f'Erreur lors de la création du plan: {e}'}
    
    def _get_field_weight(self, field: str) -> float:
        """Retourne le poids d'un champ dans le calcul de complétude"""
        weights = {
            'producer': 20.0,
            'album': 15.0,
            'duration': 10.0,
            'genres': 10.0,
            'release_date': 10.0,
            'bpm': 10.0,
            'key': 5.0,
            'lyrics': 20.0
        }
        return weights.get(field, 10.0)
    
    def _estimate_enrichment_time(self, field: str, count: int) -> float:
        """Estime le temps nécessaire pour enrichir un champ (en heures)"""
        # Temps moyen par item (en secondes)
        time_per_item = {
            'album': 0.5,
            'release_date': 0.5,
            'duration': 1.0,
            'bpm': 2.0,
            'key': 2.0,
            'genres': 1.0,
            'producer': 3.0,
            'lyrics': 5.0
        }
        
        seconds = time_per_item.get(field, 2.0) * count
        return seconds / 3600  # Convertir en heures
    
    def _estimate_api_calls(self, tasks: List[Dict]) -> int:
        """Estime le nombre d'appels API nécessaires"""
        total_calls = 0
        
        for task in tasks:
            # Estimer selon les sources
            if 'Spotify' in task['sources']:
                total_calls += task['tracks_to_enrich']
            if 'Genius' in task['sources']:
                total_calls += task['tracks_to_enrich']
            if 'Discogs' in task['sources']:
                total_calls += task['tracks_to_enrich'] // 10  # Batch possible
        
        return total_calls
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'enrichissement"""
        return {
            'total_enrichments': self.stats['total_enrichments'],
            'successful_enrichments': self.stats['successful_enrichments'],
            'failed_enrichments': self.stats['failed_enrichments'],
            'success_rate': round(
                self.stats['successful_enrichments'] / max(self.stats['total_enrichments'], 1) * 100, 
                2
            ),
            'fields_enriched': dict(self.stats['fields_enriched']),
            'sources_used': dict(self.stats['sources_used'])
        }
    
    def reset_stats(self):
        """Réinitialise les statistiques"""
        self.stats = {
            'total_enrichments': 0,
            'successful_enrichments': 0,
            'failed_enrichments': 0,
            'fields_enriched': defaultdict(int),
            'sources_used': defaultdict(int)
        }