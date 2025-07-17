# utils/logging_config.py - Version optimisée et simplifiée
import logging
import logging.handlers
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config.settings import settings

class MusicDataLogger:
    """Gestionnaire de logging simplifié pour Music Data Extractor"""
    
    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration de base
        self.log_level = logging.DEBUG if os.getenv('MDE_DEBUG') == 'true' else logging.INFO
        self.max_log_size = 10 * 1024 * 1024  # 10MB
        self.backup_count = 5
        
        # Initialiser le logging
        self._setup_logging()
        
        print(f"✅ Logging configuré (niveau: {logging.getLevelName(self.log_level)})")
    
    def _setup_logging(self):
        """Configure le système de logging"""
        # Logger principal
        self.main_logger = logging.getLogger('music_data_extractor')
        self.main_logger.setLevel(self.log_level)
        
        # Éviter les doublons
        if self.main_logger.handlers:
            return
        
        # Formatter simple et lisible
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler pour fichier principal (avec rotation)
        main_log_file = self.log_dir / "music_data_extractor.log"
        file_handler = logging.handlers.RotatingFileHandler(
            main_log_file,
            maxBytes=self.max_log_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(self.log_level)
        
        # Handler pour console (seulement INFO et plus)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        
        # Ajouter les handlers
        self.main_logger.addHandler(file_handler)
        self.main_logger.addHandler(console_handler)
        
        # Logger pour les erreurs uniquement
        error_log_file = self.log_dir / "errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=self.max_log_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        
        # Logger spécialisé pour les erreurs
        self.error_logger = logging.getLogger('music_data_extractor.errors')
        self.error_logger.addHandler(error_handler)
        self.error_logger.setLevel(logging.ERROR)
    
    def get_logger(self, name: str, session_id: Optional[str] = None) -> logging.Logger:
        """Récupère un logger avec nom spécifique"""
        logger_name = f"music_data_extractor.{name}"
        if session_id:
            logger_name += f".{session_id[:8]}"
        
        logger = logging.getLogger(logger_name)
        logger.setLevel(self.log_level)
        
        # Hériter des handlers du logger principal si pas de handlers
        if not logger.handlers:
            logger.parent = self.main_logger
        
        return logger
    
    def get_session_logger(self, session_id: str, component: str = "session") -> logging.Logger:
        """Récupère un logger pour une session spécifique"""
        # Créer un fichier de log dédié pour la session si mode debug
        logger = self.get_logger(component, session_id)
        
        if os.getenv('MDE_DEBUG') == 'true' and session_id:
            session_log_file = self.log_dir / f"session_{session_id[:8]}.log"
            
            # Vérifier si le handler existe déjà
            has_session_handler = any(
                isinstance(h, logging.FileHandler) and h.baseFilename == str(session_log_file)
                for h in logger.handlers
            )
            
            if not has_session_handler:
                session_handler = logging.FileHandler(session_log_file, encoding='utf-8')
                session_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%H:%M:%S'
                ))
                session_handler.setLevel(logging.DEBUG)
                logger.addHandler(session_handler)
        
        return logger
    
    def set_debug_mode(self, enabled: bool = True):
        """Active/désactive le mode debug"""
        new_level = logging.DEBUG if enabled else logging.INFO
        
        # Mettre à jour tous les loggers
        for logger_name in logging.Logger.manager.loggerDict:
            if logger_name.startswith('music_data_extractor'):
                logger = logging.getLogger(logger_name)
                logger.setLevel(new_level)
        
        self.log_level = new_level
        os.environ['MDE_DEBUG'] = 'true' if enabled else 'false'
        
        print(f"🔧 Mode debug {'activé' if enabled else 'désactivé'}")
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """Nettoie les anciens fichiers de log"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            deleted_count = 0
            
            for log_file in self.log_dir.glob("*.log*"):
                try:
                    file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if file_time < cutoff_date:
                        log_file.unlink()
                        deleted_count += 1
                except Exception as e:
                    print(f"⚠️ Erreur suppression {log_file}: {e}")
            
            if deleted_count > 0:
                print(f"🧹 {deleted_count} ancien(s) fichier(s) de log supprimé(s)")
            
            return deleted_count
            
        except Exception as e:
            print(f"⚠️ Erreur nettoyage logs: {e}")
            return 0
    
    def get_log_summary(self) -> dict:
        """Retourne un résumé des logs"""
        try:
            log_files = list(self.log_dir.glob("*.log"))
            
            return {
                'log_directory': str(self.log_dir),
                'log_count': len(log_files),
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
        except Exception as e:
            print(f"⚠️ Erreur résumé logs: {e}")
            return {}

# Instance globale du gestionnaire de logging
logger_manager = MusicDataLogger()

# Fonctions de convenance
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