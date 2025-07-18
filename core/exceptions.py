# core/exceptions.py
"""
Module d'exceptions personnalisées pour Music Data Extractor.
Définit une hiérarchie d'exceptions claire pour une gestion d'erreurs robuste.
"""

from typing import Optional, Dict, Any
from functools import lru_cache


class MusicDataExtractorError(Exception):
    """Exception de base pour tous les erreurs du projet"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Détails: {self.details}"
        return self.message
    
    @lru_cache(maxsize=128)
    def get_error_code(self) -> str:
        """Retourne un code d'erreur unique basé sur la classe"""
        return f"{self.__class__.__module__}.{self.__class__.__name__}"


# ===== EXCEPTIONS API =====

class APIError(MusicDataExtractorError):
    """Exception de base pour les erreurs d'API"""
    
    def __init__(self, message: str, api_name: str, details: Optional[Dict[str, Any]] = None):
        self.api_name = api_name
        details = details or {}
        details['api'] = api_name
        super().__init__(message, details)


class APIRateLimitError(APIError):
    """Exception levée quand la limite de taux d'API est atteinte"""
    
    def __init__(self, api_name: str, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        message = f"Limite de taux atteinte pour l'API {api_name}"
        if retry_after:
            message += f" - Réessayer dans {retry_after} secondes"
        super().__init__(message, api_name, {"retry_after": retry_after})


class APIAuthenticationError(APIError):
    """Exception levée pour les erreurs d'authentification API"""
    
    def __init__(self, api_name: str, key_name: str):
        self.key_name = key_name
        message = f"Erreur d'authentification pour l'API {api_name} - Vérifiez {key_name}"
        super().__init__(message, api_name, {"key": key_name})


class APIQuotaExceededError(APIError):
    """Exception levée quand le quota d'API est dépassé"""
    
    def __init__(self, api_name: str, quota_type: str = "daily"):
        self.quota_type = quota_type
        message = f"Quota {quota_type} dépassé pour l'API {api_name}"
        super().__init__(message, api_name, {"quota_type": quota_type})


class APIResponseError(APIError):
    """Exception levée pour les réponses d'API invalides"""
    
    def __init__(self, api_name: str, status_code: int, response_text: Optional[str] = None):
        self.status_code = status_code
        self.response_text = response_text
        message = f"Réponse invalide de l'API {api_name} - Code: {status_code}"
        super().__init__(message, api_name, {
            "status_code": status_code,
            "response": response_text
        })


# ===== EXCEPTIONS WEB SCRAPING =====

class ScrapingError(MusicDataExtractorError):
    """Exception de base pour les erreurs de scraping"""
    
    def __init__(self, message: str, url: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        self.url = url
        details = details or {}
        if url:
            details['url'] = url
        super().__init__(message, details)


class PageNotFoundError(ScrapingError):
    """Exception levée quand une page n'est pas trouvée"""
    
    def __init__(self, url: str):
        message = f"Page non trouvée: {url}"
        super().__init__(message, url)


class ElementNotFoundError(ScrapingError):
    """Exception levée quand un élément HTML n'est pas trouvé"""
    
    def __init__(self, selector: str, url: Optional[str] = None):
        self.selector = selector
        message = f"Élément non trouvé: {selector}"
        if url:
            message += f" sur {url}"
        super().__init__(message, url, {"selector": selector})


class SeleniumError(ScrapingError):
    """Exception levée pour les erreurs Selenium"""
    
    def __init__(self, action: str, error_message: str, url: Optional[str] = None):
        self.action = action
        self.error_message = error_message
        message = f"Erreur Selenium lors de '{action}': {error_message}"
        if url:
            message += f" sur {url}"
        super().__init__(message, url, {
            "action": action,
            "selenium_error": error_message
        })


# ===== EXCEPTIONS BASE DE DONNÉES =====

class DatabaseError(MusicDataExtractorError):
    """Exception de base pour les erreurs de base de données"""
    
    def __init__(self, message: str, db_path: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        self.db_path = db_path
        details = details or {}
        if db_path:
            details['db_path'] = db_path
        super().__init__(message, details)


class DatabaseConnectionError(DatabaseError):
    """Exception levée pour les erreurs de connexion à la base de données"""
    
    def __init__(self, db_path: str, original_error: Optional[Exception] = None):
        self.original_error = original_error
        message = f"Impossible de se connecter à la base de données: {db_path}"
        if original_error:
            message += f" - {str(original_error)}"
        details = {}
        if original_error:
            details['original_error'] = str(original_error)
        super().__init__(message, db_path, details)


class DatabaseSchemaError(DatabaseError):
    """Exception levée pour les erreurs de schéma de base de données"""
    
    def __init__(self, expected_version: str, actual_version: str, db_path: Optional[str] = None):
        self.expected_version = expected_version
        self.actual_version = actual_version
        message = f"Version de schéma incompatible - Attendu: {expected_version}, Actuel: {actual_version}"
        super().__init__(message, db_path, {
            "expected_version": expected_version,
            "actual_version": actual_version
        })


class DatabaseIntegrityError(DatabaseError):
    """Exception levée pour les erreurs d'intégrité de base de données"""
    
    def __init__(self, constraint: str, table: str, db_path: Optional[str] = None):
        self.constraint = constraint
        self.table = table
        message = f"Violation de contrainte '{constraint}' sur la table '{table}'"
        super().__init__(message, db_path, {
            "constraint": constraint,
            "table": table
        })


# ===== EXCEPTIONS DONNÉES =====

class DataError(MusicDataExtractorError):
    """Exception de base pour les erreurs de données"""
    pass


class DataValidationError(DataError):
    """Exception levée pour les erreurs de validation de données"""
    
    def __init__(self, field: str, value: Any, expected_type: str, entity_id: Optional[str] = None):
        self.field = field
        self.value = value
        self.expected_type = expected_type
        self.entity_id = entity_id
        message = f"Validation échouée pour le champ '{field}': {value} (attendu: {expected_type})"
        if entity_id:
            message += f" - Entité: {entity_id}"
        super().__init__(message, {
            "field": field,
            "value": str(value),
            "expected_type": expected_type,
            "entity_id": entity_id
        })


class DataInconsistencyError(DataError):
    """Exception levée pour les incohérences de données"""
    
    def __init__(self, description: str, entity_type: str, entity_id: Optional[str] = None):
        self.entity_type = entity_type
        self.entity_id = entity_id
        message = f"Incohérence de données ({entity_type}): {description}"
        if entity_id:
            message += f" - ID: {entity_id}"
        super().__init__(message, {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "description": description
        })


# ===== EXCEPTIONS EXTRACTION =====

class ExtractionError(MusicDataExtractorError):
    """Exception de base pour les erreurs d'extraction"""
    pass


class ArtistNotFoundError(ExtractionError):
    """Exception levée quand un artiste n'est pas trouvé"""
    
    def __init__(self, artist_name: str, source: Optional[str] = None):
        self.artist_name = artist_name
        self.source = source
        message = f"Artiste non trouvé: '{artist_name}'"
        if source:
            message += f" sur {source}"
        super().__init__(message, {
            "artist_name": artist_name,
            "source": source
        })


class TrackExtractionError(ExtractionError):
    """Exception levée pour les erreurs d'extraction de morceaux"""
    
    def __init__(self, track_id: str, error_message: str, source: Optional[str] = None):
        self.track_id = track_id
        self.source = source
        message = f"Erreur extraction morceau {track_id}: {error_message}"
        if source:
            message += f" (source: {source})"
        super().__init__(message, {
            "track_id": track_id,
            "source": source,
            "error_message": error_message
        })


class CreditExtractionError(ExtractionError):
    """Exception levée pour les erreurs d'extraction de crédits"""
    
    def __init__(self, track_id: str, credit_type: str, error_message: str):
        self.track_id = track_id
        self.credit_type = credit_type
        message = f"Erreur extraction crédit '{credit_type}' pour {track_id}: {error_message}"
        super().__init__(message, {
            "track_id": track_id,
            "credit_type": credit_type,
            "error_message": error_message
        })


# ===== EXCEPTIONS CACHE =====

class CacheError(MusicDataExtractorError):
    """Exception de base pour les erreurs de cache"""
    pass


class CacheExpiredError(CacheError):
    """Exception levée quand une entrée de cache a expiré"""
    
    def __init__(self, cache_key: str, expired_at: str):
        self.cache_key = cache_key
        self.expired_at = expired_at
        message = f"Cache expiré pour la clé '{cache_key}' (expiré le {expired_at})"
        super().__init__(message, {"key": cache_key, "expired_at": expired_at})


class CacheCorruptedError(CacheError):
    """Exception levée quand une entrée de cache est corrompue"""
    
    def __init__(self, cache_key: str, corruption_details: str):
        self.cache_key = cache_key
        self.corruption_details = corruption_details
        message = f"Cache corrompu pour la clé '{cache_key}': {corruption_details}"
        super().__init__(message, {"key": cache_key, "details": corruption_details})


# ===== EXCEPTIONS SESSION =====

class SessionError(MusicDataExtractorError):
    """Exception de base pour les erreurs de session"""
    pass


class SessionNotFoundError(SessionError):
    """Exception levée quand une session n'est pas trouvée"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        message = f"Session non trouvée: {session_id}"
        super().__init__(message, {"session_id": session_id})


class SessionCorruptedError(SessionError):
    """Exception levée quand une session est corrompue"""
    
    def __init__(self, session_id: str, corruption_details: str):
        self.session_id = session_id
        self.corruption_details = corruption_details
        message = f"Session corrompue '{session_id}': {corruption_details}"
        super().__init__(message, {"session_id": session_id, "details": corruption_details})


class SessionStatusError(SessionError):
    """Exception levée pour les changements d'état invalides"""
    
    def __init__(self, session_id: str, current_status: str, requested_status: str):
        self.session_id = session_id
        self.current_status = current_status
        self.requested_status = requested_status
        message = f"Changement d'état invalide pour session {session_id}: {current_status} -> {requested_status}"
        super().__init__(message, {
            "session_id": session_id,
            "current_status": current_status,
            "requested_status": requested_status
        })


# ===== EXCEPTIONS EXPORT =====

class ExportError(MusicDataExtractorError):
    """Exception de base pour les erreurs d'export"""
    pass


class ExportFormatError(ExportError):
    """Exception levée pour les formats d'export non supportés"""
    
    def __init__(self, format_name: str, supported_formats: list):
        self.format_name = format_name
        self.supported_formats = supported_formats
        message = f"Format d'export non supporté: {format_name}. Formats supportés: {', '.join(supported_formats)}"
        super().__init__(message, {
            "format_name": format_name,
            "supported_formats": supported_formats
        })


class ExportDataError(ExportError):
    """Exception levée pour les erreurs de données lors de l'export"""
    
    def __init__(self, data_type: str, error_message: str, export_format: Optional[str] = None):
        self.data_type = data_type
        self.export_format = export_format
        message = f"Erreur export de données '{data_type}': {error_message}"
        if export_format:
            message += f" (format: {export_format})"
        super().__init__(message, {
            "data_type": data_type,
            "export_format": export_format,
            "error_message": error_message
        })


# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=256)
def get_exception_hierarchy() -> Dict[str, list]:
    """Retourne la hiérarchie des exceptions du projet"""
    hierarchy = {}
    
    # Mappage des exceptions par catégorie
    exception_categories = {
        'api': [APIError, APIRateLimitError, APIAuthenticationError, APIQuotaExceededError, APIResponseError],
        'scraping': [ScrapingError, PageNotFoundError, ElementNotFoundError, SeleniumError],
        'database': [DatabaseError, DatabaseConnectionError, DatabaseSchemaError, DatabaseIntegrityError],
        'data': [DataError, DataValidationError, DataInconsistencyError],
        'extraction': [ExtractionError, ArtistNotFoundError, TrackExtractionError, CreditExtractionError],
        'cache': [CacheError, CacheExpiredError, CacheCorruptedError],
        'session': [SessionError, SessionNotFoundError, SessionCorruptedError, SessionStatusError],
        'export': [ExportError, ExportFormatError, ExportDataError]
    }
    
    for category, exceptions in exception_categories.items():
        hierarchy[category] = [exc.__name__ for exc in exceptions]
    
    return hierarchy


def is_retryable_error(exception: Exception) -> bool:
    """Détermine si une exception justifie une nouvelle tentative"""
    retryable_types = (
        APIRateLimitError,
        DatabaseConnectionError,
        SeleniumError,
        CacheExpiredError
    )
    
    return isinstance(exception, retryable_types)


def get_error_severity(exception: Exception) -> str:
    """Retourne le niveau de sévérité d'une exception"""
    critical_types = (DatabaseConnectionError, DatabaseSchemaError, SessionCorruptedError)
    warning_types = (APIRateLimitError, CacheExpiredError, PageNotFoundError)
    
    if isinstance(exception, critical_types):
        return "CRITICAL"
    elif isinstance(exception, warning_types):
        return "WARNING"
    elif isinstance(exception, MusicDataExtractorError):
        return "ERROR"
    else:
        return "UNKNOWN"