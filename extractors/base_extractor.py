# extractors/base_extractor.py
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta

from ..models.entities import Track, Album, Artist, Credit
from ..models.enums import CreditType, ExtractorType, DataQuality
from ..core.exceptions import ExtractionError, RateLimitError, ValidationError
from ..core.cache import CacheManager
from ..core.rate_limiter import RateLimiter
from ..config.settings import settings


@dataclass
class ExtractionResult:
    """Résultat d'une extraction avec métadonnées"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    source: Optional[str] = None
    timestamp: Optional[datetime] = None
    cache_used: bool = False
    quality_score: float = 0.0
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class ExtractorConfig:
    """Configuration pour un extracteur"""
    use_cache: bool = True
    cache_duration: int = 7  # jours
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: int = 30
    rate_limit_requests: int = 60
    rate_limit_period: int = 60  # secondes
    quality_threshold: float = 0.5


class BaseExtractor(ABC):
    """
    Classe de base abstraite pour tous les extracteurs de données musicales.
    
    Fournit les fonctionnalités communes :
    - Gestion du cache
    - Limitation du taux de requêtes
    - Gestion des erreurs et des retry
    - Validation des données
    - Logging unifié
    """
    
    def __init__(self, extractor_type: ExtractorType, config: Optional[ExtractorConfig] = None):
        self.extractor_type = extractor_type
        self.config = config or ExtractorConfig()
        
        # Initialisation des composants
        self.logger = logging.getLogger(f"{__name__}.{extractor_type.value}")
        self.cache_manager = CacheManager()
        self.rate_limiter = RateLimiter(
            requests_per_period=self.config.rate_limit_requests,
            period_seconds=self.config.rate_limit_period
        )
        
        # Statistiques d'extraction
        self.stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': 0,
            'successful_extractions': 0
        }
        
        self.logger.info(f"Extracteur {extractor_type.value} initialisé")
    
    @abstractmethod
    def extract_track_info(self, track_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations d'un morceau.
        
        Args:
            track_id: Identifiant du morceau
            **kwargs: Paramètres additionnels spécifiques à l'extracteur
            
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        pass
    
    @abstractmethod
    def extract_album_info(self, album_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations d'un album.
        
        Args:
            album_id: Identifiant de l'album
            **kwargs: Paramètres additionnels
            
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        pass
    
    @abstractmethod
    def extract_artist_info(self, artist_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations d'un artiste.
        
        Args:
            artist_id: Identifiant de l'artiste
            **kwargs: Paramètres additionnels
            
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        pass
    
    @abstractmethod
    def search_tracks(self, query: str, limit: int = 50, **kwargs) -> ExtractionResult:
        """
        Recherche des morceaux.
        
        Args:
            query: Requête de recherche
            limit: Nombre maximum de résultats
            **kwargs: Paramètres additionnels
            
        Returns:
            ExtractionResult: Résultat de la recherche
        """
        pass
    
    def extract_with_cache(self, cache_key: str, extraction_func, *args, **kwargs) -> ExtractionResult:
        """
        Effectue une extraction avec gestion du cache.
        
        Args:
            cache_key: Clé de cache
            extraction_func: Fonction d'extraction à exécuter
            *args, **kwargs: Arguments pour la fonction
            
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        self.stats['total_requests'] += 1
        
        # Vérification du cache si activé
        if self.config.use_cache:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result is not None:
                self.stats['cache_hits'] += 1
                self.logger.debug(f"Cache hit pour {cache_key}")
                
                result = ExtractionResult(
                    success=True,
                    data=cached_result,
                    source=self.extractor_type.value,
                    cache_used=True,
                    quality_score=self._calculate_cache_quality_score(cached_result)
                )
                return result
        
        self.stats['cache_misses'] += 1
        
        # Extraction avec retry
        result = self._extract_with_retry(extraction_func, *args, **kwargs)
        
        # Mise en cache si succès
        if result.success and self.config.use_cache and result.data:
            cache_duration = timedelta(days=self.config.cache_duration)
            self.cache_manager.set(cache_key, result.data, cache_duration)
            self.logger.debug(f"Données mises en cache pour {cache_key}")
        
        return result
    
    def _extract_with_retry(self, extraction_func, *args, **kwargs) -> ExtractionResult:
        """
        Effectue une extraction avec retry automatique.
        
        Args:
            extraction_func: Fonction d'extraction
            *args, **kwargs: Arguments pour la fonction
            
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                # Respect du rate limiting
                self.rate_limiter.wait_if_needed()
                
                # Tentative d'extraction
                result = extraction_func(*args, **kwargs)
                
                if result.success:
                    self.stats['successful_extractions'] += 1
                    return result
                else:
                    last_error = result.error
                    
            except RateLimitError as e:
                self.logger.warning(f"Rate limit atteint, attente... (tentative {attempt + 1})")
                if attempt < self.config.max_retries:
                    import time
                    time.sleep(self.config.retry_delay * (2 ** attempt))  # Backoff exponentiel
                last_error = str(e)
                
            except Exception as e:
                self.logger.error(f"Erreur lors de l'extraction (tentative {attempt + 1}): {e}")
                last_error = str(e)
                
                if attempt < self.config.max_retries:
                    import time
                    time.sleep(self.config.retry_delay)
        
        # Échec après tous les retries
        self.stats['errors'] += 1
        return ExtractionResult(
            success=False,
            error=f"Échec après {self.config.max_retries + 1} tentatives: {last_error}",
            source=self.extractor_type.value
        )
    
    def validate_track_data(self, data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Valide les données d'un morceau.
        
        Args:
            data: Données à valider
            
        Returns:
            tuple: (est_valide, liste_des_erreurs)
        """
        errors = []
        
        # Champs obligatoires
        required_fields = ['title', 'artist']
        for field in required_fields:
            if not data.get(field):
                errors.append(f"Champ manquant: {field}")
        
        # Validation de la durée
        duration = data.get('duration_ms')
        if duration:
            min_duration = settings.get('quality.min_duration_seconds', 30) * 1000
            max_duration = settings.get('quality.max_duration_seconds', 1800) * 1000
            
            if duration < min_duration:
                errors.append(f"Durée trop courte: {duration}ms")
            elif duration > max_duration:
                errors.append(f"Durée trop longue: {duration}ms")
        
        # Validation des crédits
        credits = data.get('credits', [])
        if isinstance(credits, list):
            for credit in credits:
                if not isinstance(credit, dict):
                    errors.append("Format de crédit invalide")
                    continue
                    
                if not credit.get('name'):
                    errors.append("Nom manquant dans un crédit")
                
                if not credit.get('role'):
                    errors.append("Rôle manquant dans un crédit")
        
        return len(errors) == 0, errors
    
    def calculate_quality_score(self, data: Dict[str, Any]) -> float:
        """
        Calcule un score de qualité pour les données extraites.
        
        Args:
            data: Données à évaluer
            
        Returns:
            float: Score de qualité entre 0 et 1
        """
        score = 0.0
        max_score = 0.0
        
        # Présence des champs de base (40% du score)
        base_fields = ['title', 'artist', 'duration_ms']
        for field in base_fields:
            max_score += 0.4 / len(base_fields)
            if data.get(field):
                score += 0.4 / len(base_fields)
        
        # Présence des métadonnées (30% du score)
        metadata_fields = ['album', 'release_date', 'genres', 'bpm']
        for field in metadata_fields:
            max_score += 0.3 / len(metadata_fields)
            if data.get(field):
                score += 0.3 / len(metadata_fields)
        
        # Qualité des crédits (30% du score)
        credits = data.get('credits', [])
        max_score += 0.3
        
        if credits:
            credit_score = 0.0
            for credit in credits:
                if isinstance(credit, dict) and credit.get('name') and credit.get('role'):
                    credit_score += 1.0
            
            if len(credits) > 0:
                credit_quality = credit_score / len(credits)
                score += 0.3 * credit_quality
        
        return min(score / max_score if max_score > 0 else 0.0, 1.0)
    
    def _calculate_cache_quality_score(self, cached_data: Dict[str, Any]) -> float:
        """Calcule le score de qualité pour des données en cache"""
        return self.calculate_quality_score(cached_data)
    
    def get_cache_key(self, method: str, *args, **kwargs) -> str:
        """
        Génère une clé de cache unique.
        
        Args:
            method: Nom de la méthode
            *args, **kwargs: Arguments de la méthode
            
        Returns:
            str: Clé de cache
        """
        import hashlib
        
        # Création d'un hash des arguments
        args_str = str(args) + str(sorted(kwargs.items()))
        args_hash = hashlib.md5(args_str.encode()).hexdigest()[:8]
        
        return f"{self.extractor_type.value}_{method}_{args_hash}"
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retourne les statistiques d'utilisation de l'extracteur.
        
        Returns:
            Dict: Statistiques d'utilisation
        """
        cache_hit_rate = 0.0
        if self.stats['total_requests'] > 0:
            cache_hit_rate = self.stats['cache_hits'] / self.stats['total_requests']
        
        success_rate = 0.0
        extraction_attempts = self.stats['successful_extractions'] + self.stats['errors']
        if extraction_attempts > 0:
            success_rate = self.stats['successful_extractions'] / extraction_attempts
        
        return {
            **self.stats,
            'cache_hit_rate': cache_hit_rate,
            'success_rate': success_rate,
            'extractor_type': self.extractor_type.value
        }
    
    def reset_stats(self):
        """Remet à zéro les statistiques"""
        self.stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': 0,
            'successful_extractions': 0
        }
        self.logger.info("Statistiques remises à zéro")
    
    def __str__(self) -> str:
        return f"<{self.__class__.__name__} type={self.extractor_type.value}>"
    
    def __repr__(self) -> str:
        return self.__str__()