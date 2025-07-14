# extractors/credit_extractor.py
import logging
import yaml
from typing import Dict, List, Optional, Any, Union, Set, Tuple
from datetime import datetime
from dataclasses import dataclass
import re

from .base_extractor import BaseExtractor, ExtractionResult, ExtractorConfig
from ..models.enums import ExtractorType, CreditType, CreditCategory, DataSource, DataQuality
from ..models.entities import Track, Credit
from ..core.exceptions import ExtractionError, DataValidationError
from ..config.settings import settings
from ..utils.text_utils import clean_text, normalize_title, clean_credit_role

@dataclass
class CreditMatch:
    """Représente un crédit trouvé avec son score de confiance"""
    person_name: str
    credit_type: CreditType
    credit_category: CreditCategory
    instrument: Optional[str] = None
    role_detail: Optional[str] = None
    source: DataSource = DataSource.MANUAL
    confidence_score: float = 0.0
    raw_data: Optional[str] = None
    is_primary: bool = False
    is_featuring: bool = False

class CreditExtractor(BaseExtractor):
    """
    Extracteur intelligent pour les crédits musicaux.
    
    Responsabilités :
    - Orchestration de l'extraction depuis multiples sources
    - Application des patterns de reconnaissance intelligents
    - Déduplication et priorisation des crédits
    - Normalisation et validation des données
    """
    
    def __init__(self, config: Optional[ExtractorConfig] = None):
        super().__init__(ExtractorType.CREDIT_EXTRACTOR, config)
        
        # Chargement des mappings de crédits
        self.credit_mappings = self._load_credit_mappings()
        
        # Configuration d'extraction
        self.extraction_config = self.credit_mappings.get('extraction_config', {})
        self.source_priority = self.extraction_config.get('source_priority', {})
        self.confidence_thresholds = self.extraction_config.get('confidence_thresholds', {
            'high': 0.9,
            'medium': 0.7,
            'low': 0.5
        })
        
        # Patterns de reconnaissance
        self.instrument_patterns = self.credit_mappings.get('instrument_patterns', {})
        self.role_patterns = self.credit_mappings.get('role_patterns', {})
        self.hiphop_patterns = self.credit_mappings.get('hiphop_specific', {})
        self.exclusion_patterns = self.credit_mappings.get('exclusion_patterns', [])
        
        # Normalisation
        self.name_cleaning = self.credit_mappings.get('name_cleaning', {})
        self.role_normalization = self.credit_mappings.get('role_normalization', {})
        
        # Auto-détection
        self.auto_detection = self.credit_mappings.get('auto_detection', {})
        
        # Cache pour éviter de retraiter les mêmes données
        self._processed_cache = {}
        
        self.logger.info("CreditExtractor initialisé avec mappings intelligents")
    
    def _load_credit_mappings(self) -> Dict[str, Any]:
        """Charge les mappings de crédits depuis le fichier YAML"""
        try:
            mappings_file = settings.project_root / "config" / "credit_mappings.yaml"
            
            with open(mappings_file, 'r', encoding='utf-8') as f:
                mappings = yaml.safe_load(f)
            
            self.logger.info(f"Mappings de crédits chargés depuis {mappings_file}")
            return mappings
            
        except FileNotFoundError:
            self.logger.warning("Fichier credit_mappings.yaml non trouvé, utilisation des patterns par défaut")
            return self._get_default_mappings()
        except Exception as e:
            self.logger.error(f"Erreur lors du chargement des mappings: {e}")
            return self._get_default_mappings()
    
    def _get_default_mappings(self) -> Dict[str, Any]:
        """Retourne des mappings par défaut en cas d'erreur"""
        return {
            'role_patterns': {
                'producer': ['produced by', 'producer', 'prod by', 'prod.', 'beats by'],
                'mixing': ['mixed by', 'mix', 'mixing'],
                'mastering': ['mastered by', 'master', 'mastering'],
                'featuring': ['feat.', 'feat', 'featuring', 'ft.', 'ft']
            },
            'extraction_config': {
                'source_priority': {
                    'genius_web': 1,
                    'genius_api': 2,
                    'spotify': 3,
                    'discogs': 4,
                    'rapedia': 1,  # Très fiable pour le rap français
                    'manual': 6
                },
                'confidence_thresholds': {
                    'high': 0.9,
                    'medium': 0.7,
                    'low': 0.5
                }
            }
        }
    
    def extract_track_credits(self, track: Track, force_refresh: bool = False) -> ExtractionResult:
        """
        Extrait tous les crédits d'un morceau depuis toutes les sources disponibles.
        
        Args:
            track: Morceau pour lequel extraire les crédits
            force_refresh: Force la ré-extraction même si en cache
            
        Returns:
            ExtractionResult: Résultat de l'extraction avec crédits consolidés
        """
        cache_key = f"track_credits_{track.genius_id or track.id}_{track.title}"
        
        # Vérification du cache
        if not force_refresh and cache_key in self._processed_cache:
            cached_result = self._processed_cache[cache_key]
            self.logger.debug(f"Crédits en cache pour {track.title}")
            return cached_result
        
        try:
            all_credits = []
            extraction_sources = []
            
            # 1. Extraction depuis les sources disponibles
            if track.genius_id:
                genius_credits = self._extract_from_genius(track)
                all_credits.extend(genius_credits)
                extraction_sources.append('genius')
            
            if track.spotify_id:
                spotify_credits = self._extract_from_spotify(track)
                all_credits.extend(spotify_credits)
                extraction_sources.append('spotify')
            
            # Extraction depuis les données déjà présentes dans le track
            existing_credits = self._extract_from_existing_data(track)
            all_credits.extend(existing_credits)
            
            # 2. Application des patterns de reconnaissance intelligents
            enhanced_credits = self._apply_intelligent_patterns(all_credits, track)
            
            # 3. Déduplication et consolidation
            final_credits = self._deduplicate_and_consolidate(enhanced_credits)
            
            # 4. Validation et scoring
            validated_credits = self._validate_and_score_credits(final_credits, track)
            
            # 5. Filtrage par seuil de confiance
            high_quality_credits = self._filter_by_confidence(validated_credits)
            
            # Calcul du score de qualité global
            quality_score = self._calculate_extraction_quality_score(
                high_quality_credits, extraction_sources, track
            )
            
            result = ExtractionResult(
                success=True,
                data={
                    'credits': [credit.__dict__ for credit in high_quality_credits],
                    'total_found': len(all_credits),
                    'after_deduplication': len(final_credits),
                    'high_quality': len(high_quality_credits),
                    'sources_used': extraction_sources,
                    'extraction_metadata': {
                        'track_title': track.title,
                        'track_artist': track.artist_name,
                        'extracted_at': datetime.now().isoformat(),
                        'patterns_applied': True,
                        'auto_detection_used': True
                    }
                },
                source=self.extractor_type.value,
                quality_score=quality_score
            )
            
            # Mise en cache
            self._processed_cache[cache_key] = result
            
            self.logger.info(
                f"Extraction crédits terminée pour '{track.title}': "
                f"{len(high_quality_credits)} crédits de qualité trouvés"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'extraction des crédits pour {track.title}: {e}")
            return ExtractionResult(
                success=False,
                error=str(e),
                source=self.extractor_type.value
            )
    
    def _extract_from_genius(self, track: Track) -> List[CreditMatch]:
        """Extrait les crédits depuis les données Genius (API + Web)"""
        credits = []
        
        try:
            # Utilisation des extracteurs Genius existants si disponibles
            from .genius_extractor import GeniusExtractor
            
            genius_extractor = GeniusExtractor()
            genius_result = genius_extractor.extract_track_info(
                str(track.genius_id), 
                include_credits=True
            )
            
            if genius_result.success and genius_result.data:
                raw_credits = genius_result.data.get('credits', [])
                
                for raw_credit in raw_credits:
                    credit_match = self._parse_raw_credit(
                        raw_credit, 
                        DataSource.GENIUS_WEB if raw_credit.get('source') == 'genius_web' else DataSource.GENIUS_API
                    )
                    if credit_match:
                        credits.append(credit_match)
            
        except Exception as e:
            self.logger.warning(f"Erreur extraction Genius pour {track.title}: {e}")
        
        return credits
    
    def _extract_from_spotify(self, track: Track) -> List[CreditMatch]:
        """Extrait les crédits depuis Spotify (limités mais fiables)"""
        credits = []
        
        try:
            # Spotify a des crédits limités mais on peut extraire des infos des métadonnées
            from .spotify_extractor import SpotifyExtractor
            
            spotify_extractor = SpotifyExtractor()
            spotify_result = spotify_extractor.extract_track_info(
                track.spotify_id,
                include_audio_features=True
            )
            
            if spotify_result.success and spotify_result.data:
                # Extraction des artistes et features
                all_artists = spotify_result.data.get('all_artists', [])
                featuring_artists = spotify_result.data.get('featuring_artists', [])
                
                # Créer des crédits pour les features
                for featuring in featuring_artists:
                    if featuring != track.artist_name:
                        credit = CreditMatch(
                            person_name=featuring,
                            credit_type=CreditType.FEATURING,
                            credit_category=CreditCategory.FEATURING,
                            source=DataSource.SPOTIFY,
                            confidence_score=0.95,  # Très fiable pour les features
                            is_featuring=True
                        )
                        credits.append(credit)
            
        except Exception as e:
            self.logger.warning(f"Erreur extraction Spotify pour {track.title}: {e}")
        
        return credits
    
    def _extract_from_existing_data(self, track: Track) -> List[CreditMatch]:
        """Extrait les crédits depuis les données déjà présentes dans le track"""
        credits = []
        
        # Conversion des crédits existants
        for existing_credit in track.credits:
            credit_match = CreditMatch(
                person_name=existing_credit.person_name,
                credit_type=existing_credit.credit_type,
                credit_category=existing_credit.credit_category,
                instrument=existing_credit.instrument,
                source=existing_credit.data_source,
                confidence_score=0.8,  # Score moyen pour les données existantes
                is_primary=existing_credit.is_primary,
                is_featuring=existing_credit.is_featuring
            )
            credits.append(credit_match)
        
        # Extraction des featuring artists
        for featuring in track.featuring_artists:
            if featuring != track.artist_name:
                credit_match = CreditMatch(
                    person_name=featuring,
                    credit_type=CreditType.FEATURING,
                    credit_category=CreditCategory.FEATURING,
                    source=DataSource.MANUAL,
                    confidence_score=0.9,
                    is_featuring=True
                )
                credits.append(credit_match)
        
        return credits
    
    def _parse_raw_credit(self, raw_credit: Dict[str, Any], source: DataSource) -> Optional[CreditMatch]:
        """Parse un crédit brut et le convertit en CreditMatch"""
        try:
            name = raw_credit.get('name', '').strip()
            role = raw_credit.get('role', '').strip()
            
            if not name or not role:
                return None
            
            # Nettoyage du nom
            cleaned_name = self._clean_person_name(name)
            if self._is_excluded_name(cleaned_name):
                return None
            
            # Détection du type et catégorie de crédit
            credit_type, credit_category = self._detect_credit_type_and_category(role)
            
            # Détection d'instrument si applicable
            instrument = self._detect_instrument(role)
            
            # Score de confiance basé sur la source et la clarté du pattern
            confidence_score = self._calculate_confidence_score(role, source)
            
            return CreditMatch(
                person_name=cleaned_name,
                credit_type=credit_type,
                credit_category=credit_category,
                instrument=instrument,
                role_detail=role,
                source=source,
                confidence_score=confidence_score,
                raw_data=str(raw_credit)
            )
            
        except Exception as e:
            self.logger.warning(f"Erreur parsing crédit brut: {e}")
            return None
    
    def _apply_intelligent_patterns(self, credits: List[CreditMatch], track: Track) -> List[CreditMatch]:
        """Applique les patterns de reconnaissance intelligents"""
        enhanced_credits = []
        
        for credit in credits:
            # Application des patterns de normalisation
            normalized_credit = self._normalize_credit_with_patterns(credit)
            
            # Détection automatique de patterns cachés
            auto_detected_credits = self._auto_detect_hidden_patterns(normalized_credit, track)
            
            enhanced_credits.append(normalized_credit)
            enhanced_credits.extend(auto_detected_credits)
        
        return enhanced_credits
    
    def _normalize_credit_with_patterns(self, credit: CreditMatch) -> CreditMatch:
        """Normalise un crédit en utilisant les patterns définis"""
        # Normalisation du rôle
        if credit.role_detail:
            normalized_role = credit.role_detail.lower().strip()
            
            # Application des patterns de normalisation
            for pattern, replacement in self.role_normalization.items():
                if pattern in normalized_role:
                    # Mise à jour du type de crédit si pattern trouvé
                    try:
                        new_credit_type = CreditType(replacement)
                        credit.credit_type = new_credit_type
                        credit.credit_category = self._get_category_for_type(new_credit_type)
                    except ValueError:
                        pass
        
        # Amélioration du score de confiance si pattern reconnu
        if self._is_recognized_pattern(credit.role_detail or ""):
            credit.confidence_score = min(1.0, credit.confidence_score + 0.1)
        
        return credit
    
    def _auto_detect_hidden_patterns(self, credit: CreditMatch, track: Track) -> List[CreditMatch]:
        """Détecte automatiquement des patterns cachés"""
        detected_credits = []
        
        # Détection de crédits implicites basés sur le nom
        name_lower = credit.person_name.lower()
        
        # Patterns pour producteurs célèbres
        producer_keywords = self.auto_detection.get('production_keywords', [])
        for keyword in producer_keywords:
            if keyword in credit.role_detail.lower() and credit.credit_type != CreditType.PRODUCER:
                # Créer un crédit producteur supplémentaire
                producer_credit = CreditMatch(
                    person_name=credit.person_name,
                    credit_type=CreditType.PRODUCER,
                    credit_category=CreditCategory.PRODUCER,
                    source=credit.source,
                    confidence_score=0.7,
                    raw_data=f"Auto-détecté depuis: {credit.role_detail}"
                )
                detected_credits.append(producer_credit)
                break
        
        return detected_credits
    
    def _deduplicate_and_consolidate(self, credits: List[CreditMatch]) -> List[CreditMatch]:
        """Déduplique et consolide les crédits"""
        seen_credits = {}
        consolidated_credits = []
        
        # Grouper par (nom, type)
        for credit in credits:
            key = (credit.person_name.lower(), credit.credit_type)
            
            if key in seen_credits:
                # Conserver le crédit avec le meilleur score de confiance
                existing = seen_credits[key]
                if credit.confidence_score > existing.confidence_score:
                    seen_credits[key] = credit
                elif credit.source != existing.source:
                    # Combiner les sources si différentes
                    existing.confidence_score = min(1.0, existing.confidence_score + 0.1)
            else:
                seen_credits[key] = credit
        
        # Conversion en liste triée par priorité de source
        for credit in seen_credits.values():
            source_priority = self.source_priority.get(credit.source.value, 999)
            credit.source_priority = source_priority
            consolidated_credits.append(credit)
        
        # Tri par priorité de source puis par score de confiance
        consolidated_credits.sort(
            key=lambda x: (x.source_priority, -x.confidence_score)
        )
        
        return consolidated_credits
    
    def _validate_and_score_credits(self, credits: List[CreditMatch], track: Track) -> List[CreditMatch]:
        """Valide et ajuste les scores des crédits"""
        validated_credits = []
        
        for credit in credits:
            # Validation du nom
            if not self._is_valid_person_name(credit.person_name):
                continue
            
            # Validation contextuelle
            if not self._is_contextually_valid(credit, track):
                credit.confidence_score *= 0.8  # Réduction du score
            
            # Boost pour certains patterns fiables
            if self._is_high_confidence_pattern(credit):
                credit.confidence_score = min(1.0, credit.confidence_score + 0.2)
            
            validated_credits.append(credit)
        
        return validated_credits
    
    def _filter_by_confidence(self, credits: List[CreditMatch]) -> List[Credit]:
        """Filtre les crédits par seuil de confiance et les convertit en entités"""
        threshold = self.confidence_thresholds.get('medium', 0.7)
        high_quality_credits = []
        
        for credit_match in credits:
            if credit_match.confidence_score >= threshold:
                # Conversion en entité Credit
                credit_entity = Credit(
                    credit_category=credit_match.credit_category,
                    credit_type=credit_match.credit_type,
                    person_name=credit_match.person_name,
                    role_detail=credit_match.role_detail,
                    instrument=credit_match.instrument,
                    is_primary=credit_match.is_primary,
                    is_featuring=credit_match.is_featuring,
                    data_source=credit_match.source,
                    extraction_date=datetime.now()
                )
                high_quality_credits.append(credit_entity)
        
        return high_quality_credits
    
    # Méthodes utilitaires
    
    def _clean_person_name(self, name: str) -> str:
        """Nettoie le nom d'une personne selon les règles définies"""
        cleaned = name.strip()
        
        # Suppression des préfixes
        for prefix in self.name_cleaning.get('remove_prefixes', []):
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()
        
        # Suppression des suffixes
        for suffix in self.name_cleaning.get('remove_suffixes', []):
            if cleaned.lower().endswith(suffix.lower()):
                cleaned = cleaned[:-len(suffix)].strip()
        
        # Application des remplacements
        for replacement in self.name_cleaning.get('replace_patterns', []):
            cleaned = cleaned.replace(replacement['from'], replacement['to'])
        
        return cleaned
    
    def _is_excluded_name(self, name: str) -> bool:
        """Vérifie si un nom doit être exclu"""
        name_lower = name.lower()
        return any(pattern.lower() in name_lower for pattern in self.exclusion_patterns)
    
    def _detect_credit_type_and_category(self, role: str) -> Tuple[CreditType, CreditCategory]:
        """Détecte le type et la catégorie de crédit depuis le rôle"""
        role_lower = role.lower().strip()
        
        # Recherche dans les patterns définis
        for category_name, patterns in self.role_patterns.items():
            for pattern in patterns:
                if pattern.lower() in role_lower:
                    try:
                        # Mapping vers les enums
                        credit_type = CreditType(category_name.upper() if category_name.upper() in [ct.value.upper() for ct in CreditType] else 'OTHER')
                        credit_category = self._get_category_for_type(credit_type)
                        return credit_type, credit_category
                    except ValueError:
                        continue
        
        # Patterns spécifiques hip-hop
        for category_name, patterns in self.hiphop_patterns.items():
            for pattern in patterns:
                if pattern.lower() in role_lower:
                    try:
                        credit_type = CreditType(category_name.upper() if category_name.upper() in [ct.value.upper() for ct in CreditType] else 'OTHER')
                        credit_category = self._get_category_for_type(credit_type)
                        return credit_type, credit_category
                    except ValueError:
                        continue
        
        # Par défaut
        return CreditType.OTHER, CreditCategory.OTHER
    
    def _detect_instrument(self, role: str) -> Optional[str]:
        """Détecte l'instrument depuis le rôle"""
        role_lower = role.lower()
        
        for instrument, patterns in self.instrument_patterns.items():
            for pattern in patterns:
                if pattern.lower() in role_lower:
                    return instrument
        
        return None
    
    def _get_category_for_type(self, credit_type: CreditType) -> CreditCategory:
        """Retourne la catégorie appropriée pour un type de crédit"""
        type_to_category = {
            CreditType.PRODUCER: CreditCategory.PRODUCER,
            CreditType.EXECUTIVE_PRODUCER: CreditCategory.PRODUCER,
            CreditType.CO_PRODUCER: CreditCategory.PRODUCER,
            CreditType.MIXING: CreditCategory.TECHNICAL,
            CreditType.MASTERING: CreditCategory.TECHNICAL,
            CreditType.FEATURING: CreditCategory.FEATURING,
            CreditType.RAP: CreditCategory.VOCAL,
            CreditType.GUITAR: CreditCategory.INSTRUMENT,
            CreditType.PIANO: CreditCategory