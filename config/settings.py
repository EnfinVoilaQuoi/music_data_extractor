# config/settings.py
import os
import yaml
from pathlib import Path
from typing import Dict, Any

class Settings:
    """Configuration centralisée du projet"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_file = self.project_root / "config" / "default_config.yaml"
        self.credit_mappings_file = self.project_root / "config" / "credit_mappings.yaml"
        
        # Chargement de la configuration
        self.config = self._load_config()
        
        # Variables d'environnement
        self.genius_api_key = os.getenv("GENIUS_API_KEY")
        self.discogs_token = os.getenv("DISCOGS_TOKEN")
        self.lastfm_api_key = os.getenv("LAST_FM_API_KEY")
        self.spotify_client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.spotify_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        
        # Validation des clés API
        self._validate_api_keys()
        
        # Chemins des dossiers
        self.data_dir = self.project_root / "data"
        self.cache_dir = self.data_dir / "cache"
        self.sessions_dir = self.data_dir / "sessions"
        self.exports_dir = self.data_dir / "exports"
        self.logs_dir = self.project_root / "logs"
        
        # Création des dossiers si nécessaires
        self._ensure_directories()
    
    def _load_config(self) -> Dict[str, Any]:
        """Charge la configuration depuis le fichier YAML"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Fichier de config non trouvé: {self.config_file}")
            return self._get_default_config()
        except Exception as e:
            print(f"Erreur lors du chargement de la config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Configuration par défaut si le fichier n'existe pas"""
        return {
            "sessions": {
                "auto_save_interval": 60,
                "max_sessions": 10,
                "cleanup_after_days": 30
            },
            "credits": {
                "expand_all_credits": True,
                "wait_after_expand": 2,
                "max_retries": 3
            },
            "albums": {
                "prefer_spotify": True,
                "fallback_to_discogs": True,
                "detect_singles": True,
                "min_tracks_for_album": 4
            },
            "quality": {
                "check_missing_bpm": True,
                "check_missing_producer": True,
                "check_suspicious_duration": True,
                "min_duration_seconds": 30,
                "max_duration_seconds": 1800
            },
            "selenium": {
                "headless": True,
                "timeout": 30,
                "retry_failed_pages": 2,
                "screenshot_on_error": True,
                "browser": "chrome"
            },
            "performance": {
                "batch_size": 10,
                "concurrent_extractions": 3,
                "cache_expire_days": 7,
                "max_memory_mb": 512
            },
            "rate_limits": {
                "genius": {
                    "requests_per_minute": 30,
                    "requests_per_hour": 1000
                },
                "spotify": {
                    "requests_per_minute": 100,
                    "requests_per_hour": 3000
                },
                "discogs": {
                    "requests_per_minute": 60,
                    "requests_per_hour": 1000
                }
            },
            "logging": {
                "level": "INFO",
                "file_rotation": True,
                "max_file_size_mb": 10,
                "backup_count": 5
            }
        }
    
    def _validate_api_keys(self):
        """Valide que les clés API nécessaires sont présentes"""
        required_keys = {
            "GENIUS_API_KEY": self.genius_api_key,
            "SPOTIFY_CLIENT_ID": self.spotify_client_id,
            "SPOTIFY_CLIENT_SECRET": self.spotify_client_secret
        }
        
        missing_keys = [key for key, value in required_keys.items() if not value]
        
        if missing_keys:
            print(f"⚠️  Clés API manquantes: {', '.join(missing_keys)}")
            print("Certaines fonctionnalités seront limitées.")
    
    def _ensure_directories(self):
        """Crée les dossiers nécessaires s'ils n'existent pas"""
        for directory in [self.data_dir, self.cache_dir, self.sessions_dir, 
                         self.exports_dir, self.logs_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str, default=None):
        """Récupère une valeur de configuration"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value

# Instance globale des settings
settings = Settings()