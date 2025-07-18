# utils/logging_config.py - VERSION CORRIGÉE
"""
Configuration optimisée du système de logging pour Music Data Extractor.
Gestion des logs par session, niveaux configurables et nettoyage automatique.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
from functools import lru_cache
import threading
import json

from config.settings import settings

class MusicDataLogger:
    """
    Gestionnaire de logging optimisé pour Music Data Extractor.
    Supporte les logs par session, rotation automatique et nettoyage.
    """
    
    def __init__(self):
        self.logs_dir = settings.logs_dir
        self.logs_dir.mkdir(exist_ok=True)
        
        # Configuration du logging
        self.log_level = getattr(logging, settings.get('logging.level', 'INFO').upper())
        self.max_file_size = settings.get('logging.max_file_size', 10 * 1024 * 1024)  # 10MB
        self.backup_count = settings.get('logging.backup_count', 5)
        self.retention_days = settings.get('logging.retention_days', 30)
        
        # Cache des loggers
        self._loggers_cache = {}
        self._lock = threading.Lock()
        
        # Configuration des formatters
        self._setup_formatters()
        
        # Configuration du logger principal
        self._setup_main_logger()
        
        # Statistiques de logging
        self.stats = {
            'logs_created': 0,
            'total_log_entries': 0,
            'errors_logged': 0,
            'warnings_logged': 0,
            'sessions_logged': set()
        }
    
    def _setup_formatters(self):
        """Configure les formatters pour différents types de logs"""
        
        # Formatter détaillé pour les fichiers
        self.detailed_formatter = logging.Formatter(
            fmt='%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Formatter simple pour la console
        self.console_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Formatter pour les sessions
        self.session_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Formatter JSON pour les logs structurés
        self.json_formatter = JsonFormatter()
    
    def _setup_main_logger(self):
        """Configure le logger principal de l'application"""
        
        # Logger racine pour l'application
        main_logger = logging.getLogger('music_data_extractor')
        main_logger.setLevel(self.log_level)
        
        # Éviter la duplication des handlers
        if main_logger.handlers:
            main_logger.handlers.clear()
        
        # Handler pour fichier principal avec rotation
        main_file_handler = logging.handlers.RotatingFileHandler(
            filename=self.logs_dir / 'music_data_extractor.log',
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        main_file_handler.setLevel(self.log_level)
        main_file_handler.setFormatter(self.detailed_formatter)
        
        # Handler console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(max(self.log_level, logging.INFO))  # Au minimum INFO sur console
        console_handler.setFormatter(self.console_formatter)
        
        # Ajout des handlers
        main_logger.addHandler(main_file_handler)
        main_logger.addHandler(console_handler)
        
        # Éviter la propagation vers le logger racine
        main_logger.propagate = False
        
        self._loggers_cache['main'] = main_logger
    
    @lru_cache(maxsize=128)
    def get_logger(self, name: str, session_id: Optional[str] = None) -> logging.Logger:
        """
        Récupère ou crée un logger avec cache.
        
        Args:
            name: Nom du logger
            session_id: ID de session optionnel
            
        Returns:
            Logger configuré
        """
        cache_key = f"{name}_{session_id}" if session_id else name
        
        with self._lock:
            if cache_key in self._loggers_cache:
                return self._loggers_cache[cache_key]
            
            # Création du nouveau logger
            logger = logging.getLogger(cache_key)
            logger.setLevel(self.log_level)
            
            # Éviter la duplication des handlers
            if logger.handlers:
                logger.handlers.clear()
            
            # Handler pour fichier spécifique
            if session_id:
                log_filename = f"{name}_{session_id}.log"
            else:
                log_filename = f"{name}.log"
            
            file_handler = logging.handlers.RotatingFileHandler(
                filename=self.logs_dir / log_filename,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(self.detailed_formatter)
            
            logger.addHandler(file_handler)
            logger.propagate = False
            
            self._loggers_cache[cache_key] = logger
            self.stats['logs_created'] += 1
            
            return logger
    
    def get_session_logger(self, session_id: str, component: str = "session") -> logging.Logger:
        """
        Crée un logger dédié pour une session.
        
        Args:
            session_id: Identifiant unique de la session
            component: Composant de la session
            
        Returns:
            Logger de session configuré
        """
        logger_name = f"session_{component}"
        session_logger = self.get_logger(logger_name, session_id)
        
        # Ajout à la liste des sessions trackées
        self.stats['sessions_logged'].add(session_id)
        
        return session_logger
    
    def set_debug_mode(self, enabled: bool = True):
        """
        Active ou désactive le mode debug sur tous les loggers.
        
        Args:
            enabled: True pour activer le debug
        """
        new_level = logging.DEBUG if enabled else logging.INFO
        
        with self._lock:
            for logger in self._loggers_cache.values():
                logger.setLevel(new_level)
                for handler in logger.handlers:
                    handler.setLevel(new_level)
        
        self.log_level = new_level
        
        main_logger = logging.getLogger('music_data_extractor')
        main_logger.info(f"🔧 Mode debug {'activé' if enabled else 'désactivé'}")
    
    # ===== MÉTHODES DE LOGGING SPÉCIALISÉES =====
    
    def log_extraction_start(self, session_id: str, artist_name: str, 
                           logger: Optional[logging.Logger] = None):
        """Log le début d'une extraction"""
        if not logger:
            logger = self.get_session_logger(session_id, "extraction")
        
        logger.info(f"🚀 DÉBUT EXTRACTION: {artist_name}")
        logger.info(f"📅 Session: {session_id}")
        logger.info(f"⏰ Heure: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.stats['total_log_entries'] += 3
    
    def log_extraction_end(self, session_id: str, artist_name: str, 
                          tracks_found: int, success: bool,
                          logger: Optional[logging.Logger] = None):
        """Log la fin d'une extraction"""
        if not logger:
            logger = self.get_session_logger(session_id, "extraction")
        
        status_emoji = "✅" if success else "❌"
        status_text = "SUCCÈS" if success else "ÉCHEC"
        
        logger.info(f"{status_emoji} FIN EXTRACTION: {artist_name}")
        logger.info(f"📊 Tracks trouvés: {tracks_found}")
        logger.info(f"🎯 Statut: {status_text}")
        
        self.stats['total_log_entries'] += 3
    
    def log_step_progress(self, session_id: str, step_name: str, current: int, total: int,
                         logger: Optional[logging.Logger] = None):
        """Log la progression d'une étape"""
        if not logger:
            logger = self.get_session_logger(session_id, "progress")
        
        percentage = (current / total * 100) if total > 0 else 0
        logger.info(f"📈 {step_name}: {current}/{total} ({percentage:.1f}%)")
        
        self.stats['total_log_entries'] += 1
    
    def log_error_with_context(self, session_id: str, error: Exception, context: Dict[str, Any],
                              logger: Optional[logging.Logger] = None):
        """Log une erreur avec contexte détaillé"""
        if not logger:
            logger = self.get_session_logger(session_id, "errors")
        
        logger.error(f"💥 ERREUR: {type(error).__name__}: {str(error)}")
        logger.error(f"📍 Contexte:")
        for key, value in context.items():
            logger.error(f"   {key}: {value}")
        
        # Log la stack trace en debug
        logger.debug(f"🔍 Stack trace:", exc_info=True)
        
        self.stats['errors_logged'] += 1
        self.stats['total_log_entries'] += 2 + len(context)
    
    def log_api_call(self, session_id: str, api_name: str, endpoint: str, 
                    response_code: Optional[int] = None, duration: Optional[float] = None,
                    logger: Optional[logging.Logger] = None):
        """Log un appel API"""
        if not logger:
            logger = self.get_session_logger(session_id, f"api_{api_name}")
        
        log_msg = f"🌐 API {api_name} | {endpoint}"
        if response_code:
            log_msg += f" | Code: {response_code}"
        if duration:
            log_msg += f" | Durée: {duration:.2f}s"
        
        if response_code and response_code >= 400:
            logger.warning(log_msg)
            self.stats['warnings_logged'] += 1
        else:
            logger.debug(log_msg)
        
        self.stats['total_log_entries'] += 1
    
    def log_scraping_activity(self, session_id: str, scraper_name: str, url: str,
                             success: bool, data_extracted: Optional[Dict[str, Any]] = None,
                             logger: Optional[logging.Logger] = None):
        """Log une activité de scraping"""
        if not logger:
            logger = self.get_session_logger(session_id, f"scraper_{scraper_name}")
        
        status_emoji = "✅" if success else "❌"
        logger.info(f"{status_emoji} SCRAPING {scraper_name}")
        logger.debug(f"🔗 URL: {url}")
        
        if data_extracted:
            logger.debug(f"📦 Données extraites: {len(data_extracted)} éléments")
        
        self.stats['total_log_entries'] += 2
    
    def log_validation_results(self, session_id: str, entity_type: str, 
                              total_validated: int, errors_found: int,
                              logger: Optional[logging.Logger] = None):
        """Log les résultats de validation"""
        if not logger:
            logger = self.get_session_logger(session_id, "validation")
        
        success_rate = ((total_validated - errors_found) / total_validated * 100) if total_validated > 0 else 0
        
        logger.info(f"🔍 VALIDATION {entity_type.upper()}")
        logger.info(f"📊 Total validé: {total_validated}")
        logger.info(f"⚠️ Erreurs trouvées: {errors_found}")
        logger.info(f"✅ Taux de succès: {success_rate:.1f}%")
        
        self.stats['total_log_entries'] += 4
    
    # ===== MÉTHODES DE GESTION DES LOGS =====
    
    def cleanup_old_logs(self, days_to_keep: int = 30) -> int:
        """
        Supprime les logs anciens.
        
        Args:
            days_to_keep: Nombre de jours à conserver
            
        Returns:
            Nombre de fichiers supprimés
        """
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        deleted_count = 0
        
        for log_file in self.logs_dir.glob("*.log*"):
            try:
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_time < cutoff_date:
                    log_file.unlink()
                    deleted_count += 1
            except Exception as e:
                # Utiliser le logger principal pour cette erreur
                main_logger = logging.getLogger('music_data_extractor')
                main_logger.warning(f"Erreur suppression log {log_file}: {e}")
        
        main_logger = logging.getLogger('music_data_extractor')
        main_logger.info(f"🧹 {deleted_count} anciens logs supprimés")
        
        return deleted_count
    
    def rotate_logs(self):
        """Force la rotation de tous les logs"""
        with self._lock:
            for logger in self._loggers_cache.values():
                for handler in logger.handlers:
                    if isinstance(handler, logging.handlers.RotatingFileHandler):
                        handler.doRollover()
    
    def flush_all_logs(self):
        """Force l'écriture de tous les logs en attente"""
        with self._lock:
            for logger in self._loggers_cache.values():
                for handler in logger.handlers:
                    handler.flush()
    
    def get_log_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de logging"""
        log_files = list(self.logs_dir.glob("*.log"))
        
        stats = self.stats.copy()
        stats['sessions_logged'] = len(stats['sessions_logged'])
        stats['active_loggers'] = len(self._loggers_cache)
        stats['log_files_count'] = len(log_files)
        stats['logs_directory'] = str(self.logs_dir)
        
        return stats
    
    def get_logs_summary(self) -> Dict[str, Any]:
        """Retourne un résumé des logs disponibles"""
        log_files = list(self.logs_dir.glob("*.log"))
        
        summary = {
            'total_log_files': len(log_files),
            'total_size_mb': sum(f.stat().st_size for f in log_files) / (1024 * 1024),
            'log_files': [
                {
                    'name': f.name,
                    'size_mb': f.stat().st_size / (1024 * 1024),
                    'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                }
                for f in log_files
            ]
        }
        
        return summary


class JsonFormatter(logging.Formatter):
    """Formatter JSON pour logs structurés"""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)


# ===== FONCTIONS DE CONFIGURATION GLOBALES =====

def setup_logging(level: str = "INFO", debug_mode: bool = False) -> MusicDataLogger:
    """
    Configure le système de logging pour l'application.
    
    Args:
        level: Niveau de logging ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        debug_mode: Activer le mode debug
        
    Returns:
        Instance du gestionnaire de logging
    """
    # Création du gestionnaire global
    logger_manager = MusicDataLogger()
    
    # Configuration du niveau
    if debug_mode:
        logger_manager.set_debug_mode(True)
    else:
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger_manager.log_level = log_level
    
    # Log de démarrage
    main_logger = logger_manager.get_logger('music_data_extractor')
    main_logger.info("🎵 Music Data Extractor - Logging initialisé")
    main_logger.info(f"📁 Répertoire logs: {logger_manager.logs_dir}")
    main_logger.info(f"📊 Niveau: {level}")
    main_logger.info(f"🔧 Mode debug: {'Activé' if debug_mode else 'Désactivé'}")
    
    return logger_manager


# Instance globale du gestionnaire de logging
logger_manager = MusicDataLogger()

# Fonctions de convenance pour accès rapide
def get_logger(name: str, session_id: Optional[str] = None) -> logging.Logger:
    """Fonction de convenance pour récupérer un logger"""
    return logger_manager.get_logger(name, session_id)

def get_session_logger(session_id: str, component: str = "session") -> logging.Logger:
    """Fonction de convenance pour un logger de session"""
    return logger_manager.get_session_logger(session_id, component)

def set_debug_mode(enabled: bool = True):
    """Fonction de convenance pour le mode debug"""
    logger_manager.set_debug_mode(enabled)

def cleanup_logs(days_to_keep: int = 30):
    """Fonction de convenance pour nettoyer les logs"""
    return logger_manager.cleanup_old_logs(days_to_keep)

def get_logging_stats() -> Dict[str, Any]:
    """Fonction de convenance pour obtenir les statistiques"""
    return logger_manager.get_log_stats()

def flush_logs():
    """Fonction de convenance pour forcer l'écriture des logs"""
    logger_manager.flush_all_logs()

def rotate_logs():
    """Fonction de convenance pour forcer la rotation"""
    logger_manager.rotate_logs()

# ===== FONCTIONS DE DIAGNOSTIC =====

def validate_logging_setup() -> Tuple[bool, List[str]]:
    """
    Valide que le système de logging est correctement configuré.
    
    Returns:
        Tuple (configuration_valide, liste_problèmes)
    """
    issues = []
    
    # Vérifier que le répertoire de logs existe
    if not logger_manager.logs_dir.exists():
        try:
            logger_manager.logs_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            issues.append(f"Impossible de créer le répertoire de logs: {e}")
    
    # Vérifier les permissions d'écriture
    if logger_manager.logs_dir.exists():
        import os
        if not os.access(logger_manager.logs_dir, os.W_OK):
            issues.append("Pas de permission d'écriture dans le répertoire de logs")
    
    # Vérifier que le logger principal existe
    try:
        main_logger = logger_manager.get_logger('music_data_extractor')
        if not main_logger:
            issues.append("Logger principal non créé")
    except Exception as e:
        issues.append(f"Erreur création logger principal: {e}")
    
    # Vérifier l'espace disque (minimum 50MB)
    try:
        import shutil
        total, used, free = shutil.disk_usage(logger_manager.logs_dir)
        free_mb = free / (1024 * 1024)
        if free_mb < 50:
            issues.append(f"Espace disque insuffisant: {free_mb:.1f}MB disponibles")
    except Exception:
        issues.append("Impossible de vérifier l'espace disque")
    
    return len(issues) == 0, issues

def run_logging_diagnostics() -> Dict[str, Any]:
    """
    Lance des diagnostics complets sur le système de logging.
    
    Returns:
        Rapport de diagnostic détaillé
    """
    diagnostics = {
        'setup_validation': {},
        'statistics': logger_manager.get_log_stats(),
        'logs_summary': logger_manager.get_logs_summary(),
        'configuration': {
            'log_level': logging.getLevelName(logger_manager.log_level),
            'logs_directory': str(logger_manager.logs_dir),
            'max_file_size_mb': logger_manager.max_file_size / (1024 * 1024),
            'backup_count': logger_manager.backup_count,
            'retention_days': logger_manager.retention_days
        }
    }
    
    # Validation de la configuration
    is_valid, issues = validate_logging_setup()
    diagnostics['setup_validation'] = {
        'is_valid': is_valid,
        'issues': issues
    }
    
    # Test de création de logger
    try:
        test_logger = logger_manager.get_logger('diagnostic_test')
        test_logger.info("Test de diagnostic logging")
        diagnostics['logger_creation_test'] = {
            'success': True,
            'message': "Logger de test créé avec succès"
        }
    except Exception as e:
        diagnostics['logger_creation_test'] = {
            'success': False,
            'error': str(e)
        }
    
    # Test des différents niveaux de log
    log_levels_test = {}
    for level_name in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
        try:
            test_logger = logger_manager.get_logger('level_test')
            level = getattr(logging, level_name)
            test_logger.log(level, f"Test niveau {level_name}")
            log_levels_test[level_name] = True
        except Exception:
            log_levels_test[level_name] = False
    
    diagnostics['log_levels_test'] = log_levels_test
    
    return diagnostics

def create_session_logs_summary(session_id: str) -> Dict[str, Any]:
    """
    Crée un résumé des logs pour une session donnée.
    
    Args:
        session_id: ID de la session
        
    Returns:
        Résumé des logs de la session
    """
    session_logs = []
    
    # Recherche des fichiers de logs pour cette session
    for log_file in logger_manager.logs_dir.glob(f"*{session_id}*.log"):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                session_logs.append({
                    'file': log_file.name,
                    'lines_count': len(lines),
                    'file_size_kb': log_file.stat().st_size / 1024,
                    'last_modified': datetime.fromtimestamp(log_file.stat().st_mtime).isoformat()
                })
        except Exception as e:
            session_logs.append({
                'file': log_file.name,
                'error': f"Erreur lecture: {e}"
            })
    
    return {
        'session_id': session_id,
        'total_log_files': len(session_logs),
        'log_files': session_logs,
        'generated_at': datetime.now().isoformat()
    }

# ===== CONTEXTE MANAGERS POUR LOGGING =====

class LoggingContext:
    """Context manager pour logging avec session"""
    
    def __init__(self, session_id: str, component: str, logger_manager: MusicDataLogger = None):
        self.session_id = session_id
        self.component = component
        self.manager = logger_manager or globals()['logger_manager']
        self.logger = None
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger = self.manager.get_session_logger(self.session_id, self.component)
        self.logger.info(f"🚀 Début {self.component} - Session {self.session_id}")
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = datetime.now() - self.start_time
        
        if exc_type is None:
            self.logger.info(f"✅ Fin {self.component} - Durée: {duration.total_seconds():.2f}s")
        else:
            self.logger.error(f"❌ Erreur {self.component} - {exc_type.__name__}: {exc_val}")
            self.logger.error(f"⏱️ Durée avant erreur: {duration.total_seconds():.2f}s")
        
        return False  # Ne pas supprimer l'exception

class TimedLogging:
    """Context manager pour mesurer et logger des opérations"""
    
    def __init__(self, operation_name: str, logger: logging.Logger = None, threshold_seconds: float = 1.0):
        self.operation_name = operation_name
        self.logger = logger or logging.getLogger('music_data_extractor')
        self.threshold_seconds = threshold_seconds
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.debug(f"⏱️ Début: {self.operation_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = datetime.now() - self.start_time
        duration_seconds = duration.total_seconds()
        
        if exc_type is None:
            if duration_seconds > self.threshold_seconds:
                self.logger.warning(f"🐌 {self.operation_name} lent: {duration_seconds:.2f}s")
            else:
                self.logger.debug(f"✅ {self.operation_name}: {duration_seconds:.2f}s")
        else:
            self.logger.error(f"❌ Erreur {self.operation_name}: {exc_val} (après {duration_seconds:.2f}s)")
        
        return False

# ===== DÉCORATEURS DE LOGGING =====

def log_function_calls(logger_name: str = None):
    """
    Décorateur pour logger automatiquement les appels de fonction.
    
    Args:
        logger_name: Nom du logger à utiliser
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or func.__module__)
            
            # Log de l'entrée
            logger.debug(f"🔗 Appel {func.__name__} avec args={len(args)}, kwargs={len(kwargs)}")
            
            start_time = datetime.now()
            try:
                result = func(*args, **kwargs)
                duration = datetime.now() - start_time
                logger.debug(f"✅ {func.__name__} terminé en {duration.total_seconds():.3f}s")
                return result
            except Exception as e:
                duration = datetime.now() - start_time
                logger.error(f"❌ Erreur {func.__name__} après {duration.total_seconds():.3f}s: {e}")
                raise
        
        return wrapper
    return decorator

def log_errors_only(logger_name: str = None):
    """
    Décorateur pour logger uniquement les erreurs d'une fonction.
    
    Args:
        logger_name: Nom du logger à utiliser
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger = get_logger(logger_name or func.__module__)
                logger.error(f"💥 Erreur dans {func.__name__}: {type(e).__name__}: {e}")
                logger.debug(f"🔍 Stack trace complète:", exc_info=True)
                raise
        
        return wrapper
    return decorator

# ===== LOGGING PRINCIPAL =====

main_logger = logging.getLogger('music_data_extractor')
main_logger.info("Module logging_config initialisé avec succès")

# ===== EXEMPLES D'UTILISATION =====
"""
Exemples d'utilisation:

# Logger général
logger = get_logger("genius_extractor", session_id="session_123")
logger.info("Début extraction Genius")

# Logger de session avec fichier dédié
session_logger = get_session_logger("session_123", "extraction")
session_logger.info("Traitement du morceau X")

# Logs spécialisés avec contexte
logger_manager.log_extraction_start("session_123", "Nekfeu")
logger_manager.log_api_call("session_123", "genius", "/songs/123", 200, 0.5)
logger_manager.log_scraping_activity("session_123", "genius_scraper", "https://genius.com/song", True)

# Context managers
with LoggingContext("session_123", "extraction") as logger:
    logger.info("Traitement en cours...")

with TimedLogging("Opération longue", logger, threshold_seconds=2.0):
    # Opération à mesurer
    pass

# Décorateurs
@log_function_calls("my_module")
def ma_fonction():
    pass

@log_errors_only("my_module")  
def fonction_avec_erreurs():
    pass

# Mode debug
set_debug_mode(True)

# Nettoyage
cleanup_logs(days_to_keep=7)

# Diagnostics
diagnostics = run_logging_diagnostics()
print(f"Système de logging valide: {diagnostics['setup_validation']['is_valid']}")

# Statistiques
stats = get_logging_stats()
print(f"Total logs créés: {stats['logs_created']}")
"""