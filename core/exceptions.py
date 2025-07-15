# core/exceptions.py
"""
Module d'exceptions personnalisées pour Music Data Extractor.
Définit une hiérarchie d'exceptions claire pour une gestion d'erreurs robuste.
"""

from typing import Optional, Dict, Any


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


# ===== EXCEPTIONS API =====

class APIError(MusicDataExtractorError):
    """Exception de base pour les erreurs d'API"""
    pass


class APIRateLimitError(APIError):
    """Exception levée quand la limite de taux d'API est atteinte"""
    
    def __init__(self, api_name: str, retry_after: Optional[int] = None):
        self.api_name = api_name
        self.retry_after = retry_after
        message = f"Limite de taux atteinte pour l'API {api_name}"
        if retry_after:
            message += f" - Réessayer dans {retry_after} secondes"
        super().__init__(message, {"api": api_name, "retry_after": retry_after})


class APIAuthenticationError(APIError):
    """Exception levée pour les erreurs d'authentification API"""
    
    def __init__(self, api_name: str, key_name: str):
        self.api_name = api_name
        self.key_name = key_name
        message = f"Erreur d'authentification pour l'API {api_name} - Vérifiez {key_name}"
        super().__init__(message, {"api": api_name, "key": key_name})


class APIQuotaExceededError(APIError):
    """Exception levée quand le quota d'API est dépassé"""
    
    def __init__(self, api_name: str, quota_type: str = "daily"):
        self.api_name = api_name
        self.quota_type = quota_type
        message = f"Quota {quota_type} dépassé pour l'API {api_name}"
        super().__init__(message, {"api": api_name, "quota_type": quota_type})


class APIResponseError(APIError):
    """Exception levée pour les réponses d'API invalides"""
    
    def __init__(self, api_name: str, status_code: int, response_text: Optional[str] = None):
        self.api_name = api_name
        self.status_code = status_code
        self.response_text = response_text
        message = f"Réponse invalide de l'API {api_name} - Code: {status_code}"
        super().__init__(message, {
            "api": api_name, 
            "status_code": status_code,
            "response": response_text
        })


# ===== EXCEPTIONS WEB SCRAPING =====

class ScrapingError(MusicDataExtractorError):
    """Exception de base pour les erreurs de scraping"""
    pass


class PageNotFoundError(ScrapingError):
    """Exception levée quand une page n'est pas trouvée"""
    
    def __init__(self, url: str):
        self.url = url
        message = f"Page non trouvée: {url}"
        super().__init__(message, {"url": url})


class ElementNotFoundError(ScrapingError):
    """Exception levée quand un élément HTML n'est pas trouvé"""
    
    def __init__(self, selector: str, url: Optional[str] = None):
        self.selector = selector
        self.url = url
        message = f"Élément non trouvé: {selector}"
        if url:
            message += f" sur {url}"
        super().__init__(message, {"selector": selector, "url": url})


class SeleniumError(ScrapingError):
    """Exception levée pour les erreurs Selenium"""
    
    def __init__(self, action: str, error_message: str, url: Optional[str] = None):
        self.action = action
        self.error_message = error_message
        self.url = url
        message = f"Erreur Selenium lors de '{action}': {error_message}"
        if url:
            message += f" sur {url}"
        super().__init__(message, {
            "action": action,
            "selenium_error": error_message,
            "url": url
        })


# ===== EXCEPTIONS BASE DE DONNÉES =====

class DatabaseError(MusicDataExtractorError):
    """Exception de base pour les erreurs de base de données"""
    pass


class DatabaseConnectionError(DatabaseError):
    """Exception levée pour les erreurs de connexion à la base de données"""
    
    def __init__(self, db_path: str, original_error: Optional[Exception] = None):
        self.db_path = db_path
        self.original_error = original_error
        message = f"Impossible de se connecter à la base de données: {db_path}"
        if original_error:
            message += f" - {str(original_error)}"
        super().__init__(message, {"db_path": db_path, "original_error": str(original_error)})


class DatabaseIntegrityError(DatabaseError):
    """Exception levée pour les erreurs d'intégrité de la base de données"""
    
    def __init__(self, table: str, constraint: str, values: Optional[Dict[str, Any]] = None):
        self.table = table
        self.constraint = constraint
        self.values = values
        message = f"Violation de contrainte '{constraint}' dans la table '{table}'"
        super().__init__(message, {
            "table": table,
            "constraint": constraint,
            "values": values
        })


# ===== EXCEPTIONS DONNÉES =====

class DataError(MusicDataExtractorError):
    """Exception de base pour les erreurs de données"""
    pass


class DataValidationError(DataError):
    """Exception levée pour les erreurs de validation des données"""
    
    def __init__(self, field: str, value: Any, expected: str):
        self.field = field
        self.value = value
        self.expected = expected
        message = f"Validation échouée pour '{field}': valeur '{value}', attendu {expected}"
        super().__init__(message, {
            "field": field,
            "value": value,
            "expected": expected
        })


class DuplicateDataError(DataError):
    """Exception levée quand des données en doublon sont détectées"""
    
    def __init__(self, entity_type: str, identifier: str, existing_id: Optional[int] = None):
        self.entity_type = entity_type
        self.identifier = identifier
        self.existing_id = existing_id
        message = f"Doublon détecté pour {entity_type}: {identifier}"
        if existing_id:
            message += f" (ID existant: {existing_id})"
        super().__init__(message, {
            "entity_type": entity_type,
            "identifier": identifier,
            "existing_id": existing_id
        })


class MissingDataError(DataError):
    """Exception levée quand des données requises sont manquantes"""
    
    def __init__(self, entity_type: str, missing_fields: list, context: Optional[str] = None):
        self.entity_type = entity_type
        self.missing_fields = missing_fields
        self.context = context
        message = f"Données manquantes pour {entity_type}: {', '.join(missing_fields)}"
        if context:
            message += f" - Contexte: {context}"
        super().__init__(message, {
            "entity_type": entity_type,
            "missing_fields": missing_fields,
            "context": context
        })


# ===== EXCEPTIONS EXTRACTION =====

class ExtractionError(MusicDataExtractorError):
    """Exception de base pour les erreurs d'extraction"""
    pass


class ArtistNotFoundError(ExtractionError):
    """Exception levée quand un artiste n'est pas trouvé"""
    
    def __init__(self, artist_name: str, source: str):
        self.artist_name = artist_name
        self.source = source
        message = f"Artiste '{artist_name}' non trouvé sur {source}"
        super().__init__(message, {"artist": artist_name, "source": source})


class TrackNotFoundError(ExtractionError):
    """Exception levée quand un morceau n'est pas trouvé"""
    
    def __init__(self, track_title: str, artist_name: str, source: str):
        self.track_title = track_title
        self.artist_name = artist_name
        self.source = source
        message = f"Morceau '{track_title}' de '{artist_name}' non trouvé sur {source}"
        super().__init__(message, {
            "track": track_title,
            "artist": artist_name,
            "source": source
        })


class CreditExtractionError(ExtractionError):
    """Exception levée pour les erreurs d'extraction de crédits"""
    
    def __init__(self, track_title: str, credit_type: str, error_details: str):
        self.track_title = track_title
        self.credit_type = credit_type
        self.error_details = error_details
        message = f"Erreur d'extraction des crédits '{credit_type}' pour '{track_title}': {error_details}"
        super().__init__(message, {
            "track": track_title,
            "credit_type": credit_type,
            "error": error_details
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
            "requested_format": format_name,
            "supported_formats": supported_formats
        })


class ExportPermissionError(ExportError):
    """Exception levée pour les erreurs de permissions lors de l'export"""
    
    def __init__(self, file_path: str, operation: str):
        self.file_path = file_path
        self.operation = operation
        message = f"Permissions insuffisantes pour {operation} le fichier: {file_path}"
        super().__init__(message, {"file_path": file_path, "operation": operation})


# ===== UTILITAIRES =====

def get_exception_hierarchy() -> Dict[str, list]:
    """Retourne la hiérarchie des exceptions pour debug/documentation"""
    return {
        "MusicDataExtractorError": [
            {
                "APIError": [
                    "APIRateLimitError",
                    "APIAuthenticationError", 
                    "APIQuotaExceededError",
                    "APIResponseError"
                ]
            },
            {
                "ScrapingError": [
                    "PageNotFoundError",
                    "ElementNotFoundError",
                    "SeleniumError"
                ]
            },
            {
                "DatabaseError": [
                    "DatabaseConnectionError",
                    "DatabaseIntegrityError"
                ]
            },
            {
                "DataError": [
                    "DataValidationError",
                    "DuplicateDataError",
                    "MissingDataError"
                ]
            },
            {
                "ExtractionError": [
                    "ArtistNotFoundError",
                    "TrackNotFoundError",
                    "CreditExtractionError"
                ]
            },
            {
                "CacheError": [
                    "CacheExpiredError",
                    "CacheCorruptedError"
                ]
            },
            {
                "SessionError": [
                    "SessionNotFoundError",
                    "SessionCorruptedError"
                ]
            },
            {
                "ExportError": [
                    "ExportFormatError",
                    "ExportPermissionError"
                ]
            }
        ]
    }