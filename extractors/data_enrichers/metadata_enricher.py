# extractors/data_enrichers/metadata_enricher.py
"""
Enrichisseur optimisé pour les métadonnées musicales - complète et améliore les données.
Version optimisée avec cache intelligent, règles d'inférence et validation croisée.
"""

import logging
import re
from functools import lru_cache
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime, timedelta
from collections import defaultdict, Counter

# Imports absolus
from core.cache import CacheManager
from config.settings import settings
from utils.text_utils import normalize_text, clean_artist_name, calculate_similarity
from models.enums import DataSource, Genre, CreditCategory, DataQuality


class MetadataEnricher:
    """
    Enrichisseur spécialisé pour les métadonnées musicales.
    
    Fonctionnalités optimisées :
    - Complément des données manquantes par inférence
    - Validation et correction des métadonnées existantes
    - Enrichissement croisé entre sources multiples
    - Normalisation des formats et standards
    - Détection et résolution des incohérences
    - Cache intelligent pour éviter les retraitements
    - Scoring de qualité et confiance des données
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration optimisée
        self.config = {
            'enable_inference': settings.get('enrichment.enable_inference', True),
            'confidence_threshold': settings.get('enrichment.confidence_threshold', 0.7),
            'cross_validation': settings.get('enrichment.cross_validation', True),
            'auto_correction': settings.get('enrichment.auto_correction', True),
            'preserve_original': settings.get('enrichment.preserve_original', True),
            'max_inference_depth': settings.get('enrichment.max_inference_depth', 3),
            'genre_normalization': settings.get('enrichment.genre_normalization', True)
        }
        
        # Cache manager
        self.cache_manager = CacheManager(namespace='metadata_enrichment') if CacheManager else None
        
        # Règles d'enrichissement et patterns
        self.enrichment_rules = self._load_enrichment_rules()
        self.genre_mappings = self._load_genre_mappings()
        self.validation_patterns = self._compile_validation_patterns()
        
        # Statistiques d'enrichissement
        self.stats = {
            'items_enriched': 0,
            'fields_added': 0,
            'corrections_made': 0,
            'inferences_applied': 0,
            'validations_performed': 0,
            'cache_hits': 0,
            'total_processing_time': 0.0
        }
        
        self.logger.info("✅ MetadataEnricher optimisé initialisé")
    
    @lru_cache(maxsize=1)
    def _load_enrichment_rules(self) -> Dict[str, Any]:
        """Charge les règles d'enrichissement avec cache"""
        return {
            'duration_rules': {
                'min_duration_seconds': 10,
                'max_duration_seconds': 1800,  # 30 minutes
                'typical_track_range': (60, 600),  # 1-10 minutes
                'ep_max_duration': 1800,  # 30 minutes
                'album_min_duration': 900   # 15 minutes
            },
            'date_rules': {
                'earliest_valid_year': 1900,
                'latest_valid_year': datetime.now().year + 2,
                'common_formats': ['YYYY', 'YYYY-MM-DD', 'DD/MM/YYYY'],
                'inference_patterns': {
                    'album_from_tracks': True,
                    'era_from_year': True
                }
            },
            'genre_rules': {
                'max_genres_per_track': 5,
                'primary_genre_weight': 0.6,
                'sub_genre_inheritance': True,
                'auto_categorization': True
            },
            'quality_rules': {
                'required_fields': ['title', 'artist'],
                'recommended_fields': ['album', 'duration', 'release_date'],
                'quality_weights': {
                    'completeness': 0.4,
                    'accuracy': 0.3,
                    'consistency': 0.2,
                    'freshness': 0.1
                }
            }
        }
    
    @lru_cache(maxsize=1)
    def _load_genre_mappings(self) -> Dict[str, str]:
        """Charge les mappings de genres avec cache"""
        return {
            # Hip-Hop et variantes
            'hip hop': 'Hip-Hop',
            'hip-hop': 'Hip-Hop',
            'hiphop': 'Hip-Hop',
            'rap': 'Hip-Hop',
            'rap music': 'Hip-Hop',
            'trap': 'Trap',
            'drill': 'Drill',
            'boom bap': 'Boom Bap',
            'old school hip hop': 'Old School Hip-Hop',
            'gangsta rap': 'Gangsta Rap',
            'conscious rap': 'Conscious Hip-Hop',
            
            # Genres français
            'rap français': 'Rap Français',
            'rap francais': 'Rap Français',
            'french rap': 'Rap Français',
            'rap fr': 'Rap Français',
            'chanson française': 'Chanson Française',
            
            # Électronique
            'electronic': 'Electronic',
            'techno': 'Techno',
            'house': 'House',
            'dubstep': 'Dubstep',
            'drum and bass': 'Drum & Bass',
            'dnb': 'Drum & Bass',
            
            # Rock et variantes
            'rock': 'Rock',
            'hard rock': 'Hard Rock',
            'punk': 'Punk',
            'metal': 'Metal',
            'heavy metal': 'Heavy Metal',
            
            # Autres
            'pop': 'Pop',
            'r&b': 'R&B',
            'rnb': 'R&B',
            'soul': 'Soul',
            'funk': 'Funk',
            'jazz': 'Jazz',
            'blues': 'Blues',
            'reggae': 'Reggae',
            'country': 'Country'
        }
    
    @lru_cache(maxsize=1)
    def _compile_validation_patterns(self) -> Dict[str, re.Pattern]:
        """Compile les patterns de validation avec cache"""
        return {
            'year_pattern': re.compile(r'\b(19|20)\d{2}\b'),
            'duration_pattern': re.compile(r'(\d+):(\d{2})'),
            'featuring_pattern': re.compile(r'\b(feat\.?|featuring|ft\.?|avec)\s+(.+)', re.IGNORECASE),
            'remix_pattern': re.compile(r'\b(remix|rmx|rework)\b', re.IGNORECASE),
            'version_pattern': re.compile(r'\b(acoustic|live|instrumental|acapella|demo)\b', re.IGNORECASE),
            'language_indicators': re.compile(r'\b(french|français|english|spanish|german)\b', re.IGNORECASE)
        }
    
    # ===== MÉTHODES PRINCIPALES =====
    
    def enrich_metadata(self, data_item: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Enrichit les métadonnées d'un élément de données.
        
        Args:
            data_item: Élément à enrichir
            context: Contexte additionnel pour l'enrichissement
            
        Returns:
            Élément enrichi avec métadonnées améliorées
        """
        import time
        start_time = time.time()
        
        if not data_item:
            return self._empty_result("Élément de données vide")
        
        # Génération de la clé de cache
        cache_key = self._generate_cache_key(data_item, context)
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            # Copie de travail en préservant l'original
            enriched_item = data_item.copy() if self.config['preserve_original'] else data_item
            original_item = data_item.copy()
            
            enrichment_log = []
            
            # 1. Validation et nettoyage initial
            if self.config['auto_correction']:
                corrected_fields = self._validate_and_correct_data(enriched_item)
                if corrected_fields:
                    enrichment_log.extend(corrected_fields)
                    self.stats['corrections_made'] += len(corrected_fields)
            
            # 2. Enrichissement par inférence
            if self.config['enable_inference']:
                inferred_fields = self._apply_inference_rules(enriched_item, context)
                if inferred_fields:
                    enrichment_log.extend(inferred_fields)
                    self.stats['inferences_applied'] += len(inferred_fields)
            
            # 3. Normalisation des genres
            if self.config['genre_normalization']:
                genre_changes = self._normalize_genres(enriched_item)
                if genre_changes:
                    enrichment_log.extend(genre_changes)
            
            # 4. Enrichissement croisé (si contexte fourni)
            if context and self.config['cross_validation']:
                cross_enrichments = self._apply_cross_validation(enriched_item, context)
                if cross_enrichments:
                    enrichment_log.extend(cross_enrichments)
            
            # 5. Calcul de la qualité des données
            quality_score = self._calculate_data_quality(enriched_item)
            
            # 6. Détection des champs manquants recommandés
            missing_fields = self._identify_missing_fields(enriched_item)
            
            # Compilation du résultat
            result = {
                'success': True,
                'enriched_data': enriched_item,
                'original_data': original_item,
                'enrichment_log': enrichment_log,
                'quality_score': quality_score,
                'missing_fields': missing_fields,
                'enrichment_stats': {
                    'fields_added': len([e for e in enrichment_log if e['action'] == 'added']),
                    'fields_corrected': len([e for e in enrichment_log if e['action'] == 'corrected']),
                    'fields_normalized': len([e for e in enrichment_log if e['action'] == 'normalized']),
                    'confidence_average': sum(e.get('confidence', 1.0) for e in enrichment_log) / len(enrichment_log) if enrichment_log else 1.0
                },
                'processing_metadata': {
                    'processed_at': datetime.now().isoformat(),
                    'enricher_version': '1.0.0',
                    'processing_time': time.time() - start_time
                }
            }
            
            # Mise en cache
            if self.cache_manager:
                self.cache_manager.set(cache_key, result, ttl=3600)
            
            self.stats['items_enriched'] += 1
            self.stats['fields_added'] += result['enrichment_stats']['fields_added']
            self.stats['total_processing_time'] += time.time() - start_time
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Erreur enrichissement métadonnées: {e}")
            return self._empty_result(f"Erreur d'enrichissement: {str(e)}")
    
    def _validate_and_correct_data(self, data_item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Valide et corrige les données existantes"""
        corrections = []
        
        try:
            # Validation des durées
            duration = data_item.get('duration_ms') or data_item.get('duration')
            if duration:
                corrected_duration = self._validate_duration(duration)
                if corrected_duration != duration:
                    data_item['duration_ms'] = corrected_duration
                    corrections.append({
                        'field': 'duration_ms',
                        'action': 'corrected',
                        'old_value': duration,
                        'new_value': corrected_duration,
                        'confidence': 0.9,
                        'reason': 'Duration validation and normalization'
                    })
            
            # Validation des dates
            release_date = data_item.get('release_date') or data_item.get('year')
            if release_date:
                corrected_date = self._validate_date(release_date)
                if corrected_date and corrected_date != release_date:
                    data_item['release_date'] = corrected_date
                    corrections.append({
                        'field': 'release_date',
                        'action': 'corrected',
                        'old_value': release_date,
                        'new_value': corrected_date,
                        'confidence': 0.8,
                        'reason': 'Date format standardization'
                    })
            
            # Nettoyage des titres et noms d'artistes
            title = data_item.get('title') or data_item.get('name')
            if title:
                cleaned_title = self._clean_title(title)
                if cleaned_title != title:
                    data_item['title'] = cleaned_title
                    corrections.append({
                        'field': 'title',
                        'action': 'corrected',
                        'old_value': title,
                        'new_value': cleaned_title,
                        'confidence': 0.95,
                        'reason': 'Title cleaning and normalization'
                    })
            
            # Nettoyage des noms d'artistes
            artist = data_item.get('artist') or data_item.get('artist_name')
            if artist:
                cleaned_artist = clean_artist_name(artist)
                if cleaned_artist != artist:
                    data_item['artist'] = cleaned_artist
                    corrections.append({
                        'field': 'artist',
                        'action': 'corrected',
                        'old_value': artist,
                        'new_value': cleaned_artist,
                        'confidence': 0.95,
                        'reason': 'Artist name cleaning'
                    })
            
        except Exception as e:
            self.logger.debug(f"Erreur validation données: {e}")
        
        return corrections
    
    def _apply_inference_rules(self, data_item: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Applique les règles d'inférence pour compléter les données manquantes"""
        inferences = []
        
        try:
            # Inférence de l'année depuis la date de sortie
            if not data_item.get('year') and data_item.get('release_date'):
                year = self._extract_year_from_date(data_item['release_date'])
                if year:
                    data_item['year'] = year
                    inferences.append({
                        'field': 'year',
                        'action': 'added',
                        'value': year,
                        'confidence': 0.9,
                        'reason': 'Inferred from release_date',
                        'source': 'inference'
                    })
            
            # Inférence du genre principal
            if not data_item.get('primary_genre'):
                primary_genre = self._infer_primary_genre(data_item)
                if primary_genre:
                    data_item['primary_genre'] = primary_genre
                    inferences.append({
                        'field': 'primary_genre',
                        'action': 'added',
                        'value': primary_genre,
                        'confidence': 0.7,
                        'reason': 'Inferred from genre list or context',
                        'source': 'inference'
                    })
            
            # Inférence de la langue
            if not data_item.get('language'):
                language = self._infer_language(data_item, context)
                if language:
                    data_item['language'] = language
                    inferences.append({
                        'field': 'language',
                        'action': 'added',
                        'value': language,
                        'confidence': 0.6,
                        'reason': 'Inferred from language list or context',
                        'source': 'inference'
                    })