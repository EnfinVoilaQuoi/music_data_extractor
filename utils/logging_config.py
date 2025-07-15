# utils/logging_config.py
import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import sys
import os

from ..config.settings import settings


class ColoredFormatter(logging.Formatter):
    """Formatter avec couleurs pour la console"""
    
    # Codes couleurs ANSI
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Vert
        'WARNING': '\033[33m',    # Jaune
        'ERROR': '\033[31m',      # Rouge
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        # Ajouter la couleur au niveau de log
        level_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname_colored = f"{level_color}{record.levelname}{self.COLORS['RESET']}"
        
        # Formatter avec couleur
        return super().format(record)


class SessionAwareFilter(logging.Filter):
    """Filtre qui ajoute l'ID de session aux logs"""
    
    def __init__(self, session_id: Optional[str] = None):
        super().__init__()
        self.session_id = session_id
    
    def filter(self, record):
        # Ajouter l'ID de session au record
        record.session_id = getattr(record, 'session_id', self.session_id or 'NO_SESSION')
        return True


class MusicDataLogger:
    """Gestionnaire de logging centralisé pour Music Data Extractor"""
    
    def __init__(self):
        self.logs_dir = settings.logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration par défaut
        self.log_level = logging.INFO
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        self.backup_count = 5
        self.date_format = "%Y-%m-%d %H:%M:%S"
        
        # Loggers configurés
        self._configured_loggers: Dict[str, logging.Logger] = {}
        
        # Configuration initiale
        self._setup_root_logger()
    
    def _setup_root_logger(self):
        """Configure le logger racine"""
        root_logger = logging.getLogger('music_data_extractor')
        root_logger.setLevel(self.log_level)
        
        # Éviter la duplication des handlers
        if root_logger.handlers:
            return
        
        # Handler console avec couleurs
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = ColoredFormatter(
            fmt='%(asctime)s | %(levelname_colored)s | %(name)s | %(message)s',
            datefmt=self.date_format
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # Handler fichier général avec rotation
        general_log_file = self.logs_dir / "music_extractor.log"
        file_handler = logging.handlers.RotatingFileHandler(
            general_log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(session_id)-15s | %(message)s',
            datefmt=self.date_format
        )
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(SessionAwareFilter())
        root_logger.addHandler(file_handler)
        
        # Handler erreurs séparé
        error_log_file = self.logs_dir / "errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        error_handler.addFilter(SessionAwareFilter())
        root_logger.addHandler(error_handler)
        
        self._configured_loggers['root'] = root_logger
    
    def get_logger(self, name: str, session_id: Optional[str] = None) -> logging.Logger:
        """
        Récupère ou crée un logger spécialisé.
        
        Args:
            name: Nom du logger (ex: 'genius_extractor', 'database')
            session_id: ID de session pour traçabilité
            
        Returns:
            Logger configuré
        """
        logger_key = f"{name}_{session_id}" if session_id else name
        
        if logger_key in self._configured_loggers:
            return self._configured_loggers[logger_key]
        
        # Créer un nouveau logger
        logger = logging.getLogger(f"music_data_extractor.{name}")
        logger.setLevel(self.log_level)
        
        # Ajouter un filtre de session si fourni
        if session_id:
            session_filter = SessionAwareFilter(session_id)
            for handler in logger.handlers:
                handler.addFilter(session_filter)
        
        self._configured_loggers[logger_key] = logger
        return logger
    
    def get_session_logger(self, session_id: str, component: str = "session") -> logging.Logger:
        """
        Crée un logger spécifique à une session avec fichier dédié.
        
        Args:
            session_id: ID de la session
            component: Composant (ex: 'extraction', 'discovery')
            
        Returns:
            Logger avec fichier de session dédié
        """
        logger_name = f"session.{session_id}.{component}"
        
        if logger_name in self._configured_loggers:
            return self._configured_loggers[logger_name]
        
        # Créer le logger de session
        logger = logging.getLogger(f"music_data_extractor.{logger_name}")
        logger.setLevel(logging.DEBUG)
        
        # Fichier de log spécifique à la session
        session_log_file = self.logs_dir / f"session_{session_id}_{component}.log"
        session_handler = logging.FileHandler(session_log_file, encoding='utf-8')
        session_handler.setLevel(logging.DEBUG)
        
        session_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt=self.date_format
        )
        session_handler.setFormatter(session_formatter)
        logger.addHandler(session_handler)
        
        # Ajouter le filtre de session
        session_filter = SessionAwareFilter(session_id)
        session_handler.addFilter(session_filter)
        
        self._configured_loggers[logger_name] = logger
        return logger
    
    def get_extraction_logger(self, session_id: str, extractor_name: str) -> logging.Logger:
        """
        Logger spécialisé pour un extracteur spécifique.
        
        Args:
            session_id: ID de session
            extractor_name: Nom de l'extracteur (genius, spotify, etc.)
            
        Returns:
            Logger configuré pour l'extracteur
        """
        return self.get_session_logger(session_id, f"extraction_{extractor_name}")
    
    def get_scraper_logger(self, session_id: str, scraper_name: str) -> logging.Logger:
        """
        Logger spécialisé pour un scraper web.
        
        Args:
            session_id: ID de session
            scraper_name: Nom du scraper (genius_scraper, tunebat, etc.)
            
        Returns:
            Logger configuré pour le scraper
        """
        return self.get_session_logger(session_id, f"scraper_{scraper_name}")
    
    def get_database_logger(self, session_id: Optional[str] = None) -> logging.Logger:
        """Logger spécialisé pour les opérations de base de données"""
        return self.get_logger("database", session_id)
    
    def set_debug_mode(self, enabled: bool = True):
        """Active/désactive le mode debug pour tous les loggers"""
        new_level = logging.DEBUG if enabled else logging.INFO
        self.log_level = new_level
        
        # Mettre à jour tous les loggers existants
        for logger in self._configured_loggers.values():
            logger.setLevel(new_level)
        
        print(f"🔧 Mode debug {'activé' if enabled else 'désactivé'}")
    
    def log_extraction_start(self, session_id: str, artist_name: str, logger: Optional[logging.Logger] = None):
        """Log le début d'une extraction"""
        if not logger:
            logger = self.get_session_logger(session_id, "extraction")
        
        logger.info(f"🚀 DÉBUT EXTRACTION | Artiste: {artist_name}")
        logger.info(f"📋 Session ID: {session_id}")
        logger.info(f"🕐 Timestamp: {datetime.now().isoformat()}")
    
    def log_extraction_end(self, session_id: str, artist_name: str, success: bool, 
                          stats: Optional[Dict[str, Any]] = None, logger: Optional[logging.Logger] = None):
        """Log la fin d'une extraction"""
        if not logger:
            logger = self.get_session_logger(session_id, "extraction")
        
        status = "✅ SUCCÈS" if success else "❌ ÉCHEC"
        logger.info(f"{status} EXTRACTION | Artiste: {artist_name}")
        
        if stats:
            logger.info(f"📊 Statistiques:")
            for key, value in stats.items():
                logger.info(f"   {key}: {value}")
    
    def log_step_progress(self, session_id: str, step_name: str, current: int, total: int,
                         logger: Optional[logging.Logger] = None):
        """Log la progression d'une étape"""
        if not logger:
            logger = self.get_session_logger(session_id, "progress")
        
        percentage = (current / total * 100) if total > 0 else 0
        logger.info(f"📈 {step_name}: {current}/{total} ({percentage:.1f}%)")
    
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
        else:
            logger.debug(log_msg)
    
    def log_scraping_activity(self, session_id: str, scraper_name: str, url: str,
                             success: bool, data_extracted: Optional[Dict[str, Any]] = None,
                             logger: Optional[logging.Logger] = None):
        """Log une activité de scraping"""
        if not logger:
            logger = self.get_scraper_logger(session_id, scraper_name)
        
        status = "✅" if success else "❌"
        logger.info(f"{status} SCRAPING | {scraper_name} | {url}")
        
        if data_extracted:
            logger.debug(f"📦 Données extraites: {list(data_extracted.keys())}")
    
    def log_database_operation(self, session_id: str, operation: str, table: str,
                              records_affected: Optional[int] = None, duration: Optional[float] = None,
                              logger: Optional[logging.Logger] = None):
        """Log une opération de base de données"""
        if not logger:
            logger = self.get_database_logger(session_id)
        
        log_msg = f"🗃️ DB {operation.upper()} | {table}"
        if records_affected is not None:
            log_msg += f" | {records_affected} enregistrements"
        if duration:
            log_msg += f" | {duration:.3f}s"
        
        logger.debug(log_msg)
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """Nettoie les anciens fichiers de log"""
        cutoff_date = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
        
        deleted_count = 0
        for log_file in self.logs_dir.glob("*.log*"):
            if log_file.stat().st_mtime < cutoff_date:
                try:
                    log_file.unlink()
                    deleted_count += 1
                except OSError as e:
                    print(f"❌ Erreur suppression {log_file}: {e}")
        
        if deleted_count > 0:
            print(f"🧹 {deleted_count} anciens fichiers de log supprimés")
    
    def get_log_summary(self) -> Dict[str, Any]:
        """Retourne un résumé des logs"""
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
    logger_manager.cleanup_old_logs(days_to_keep)


# Exemples d'utilisation pour documentation
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

# Mode debug
set_debug_mode(True)

# Nettoyage
cleanup_logs(days_to_keep=7)
"""