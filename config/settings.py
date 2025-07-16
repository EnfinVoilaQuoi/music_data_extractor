# config/settings.py
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List

class Settings:
    """Configuration centralisée du projet Music Data Extractor"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_file = self.project_root / "config" / "default_config.yaml"
        self.credit_mappings_file = self.project_root / "config" / "credit_mappings.yaml"
        
        # Chargement de la configuration
        self.config = self._load_config()
        
        # Variables d'environnement - Clés API
        self.genius_api_key = os.getenv("GENIUS_API_KEY")
        self.discogs_token = os.getenv("DISCOGS_TOKEN")
        self.lastfm_api_key = os.getenv("LAST_FM_API_KEY")
        self.spotify_client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.spotify_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        
        # Variables d'environnement - Configuration
        self.environment = os.getenv("MDE_ENV", "development")
        self.debug_mode = os.getenv("MDE_DEBUG", "false").lower() == "true"
        
        # Validation des clés API
        self._validate_api_keys()
        
        # Chemins des dossiers
        self.data_dir = self.project_root / "data"
        self.cache_dir = self.data_dir / "cache"
        self.sessions_dir = self.data_dir / "sessions"
        self.exports_dir = self.data_dir / "exports"
        self.logs_dir = self.project_root / "logs"
        self.temp_dir = self.data_dir / "temp"
        self.screenshots_dir = self.logs_dir / "screenshots"
        
        # Création des dossiers si nécessaires
        self._ensure_directories()
        
        # Configuration dérivée
        self._setup_derived_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Charge la configuration depuis le fichier YAML"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                print(f"✅ Configuration chargée depuis {self.config_file}")
                return config
            else:
                print(f"⚠️ Fichier de config non trouvé: {self.config_file}")
                return self._get_default_config()
        except Exception as e:
            print(f"❌ Erreur lors du chargement de la config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Configuration par défaut si le fichier n'existe pas"""
        return {
            # Gestion des sessions
            "sessions": {
                "auto_save_interval": 60,
                "max_sessions": 10,
                "cleanup_after_days": 30,
                "save_only_if_active": True,
                "checkpoint_interval": 300  # 5 minutes
            },
            
            # Découverte des morceaux
            "discovery": {
                "max_tracks_per_source": 200,
                "enable_rapedia": True,
                "enable_genius": True,
                "similarity_threshold": 0.85,
                "prefer_verified_sources": True,
                "timeout_seconds": 30
            },
            
            # Extraction des crédits
            "credits": {
                "expand_all_credits": True,
                "wait_after_expand": 2,
                "max_retries": 3,
                "scroll_pause": 1,
                "custom_patterns_file": "credit_mappings.yaml",
                "detect_features": True,
                "normalize_names": True
            },
            
            # Résolution des albums
            "albums": {
                "prefer_spotify": True,
                "fallback_to_discogs": True,
                "detect_singles": True,
                "min_tracks_for_album": 4,
                "max_tracks_for_single": 3,
                "group_by_year": True,
                "resolve_missing_covers": True
            },
            
            # Validation qualité
            "quality": {
                "check_missing_bpm": True,
                "check_missing_producer": True,
                "check_suspicious_duration": True,
                "min_duration_seconds": 30,
                "max_duration_seconds": 1800,
                "require_album_info": False,
                "flag_incomplete_credits": True,
                "completeness_threshold": 0.7
            },
            
            # Configuration Selenium
            "selenium": {
                "headless": True,
                "timeout": 30,
                "retry_failed_pages": 2,
                "screenshot_on_error": True,
                "browser": "chrome",
                "window_size": "1920,1080",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "enable_javascript": True,
                "load_images": False,
                "page_load_strategy": "normal"
            },
            
            # Performance et optimisation
            "performance": {
                "batch_size": 10,
                "concurrent_extractions": 3,
                "cache_expire_days": 7,
                "max_memory_mb": 512,
                "enable_parallel_processing": True,
                "thread_pool_size": 4,
                "connection_pool_size": 10,
                "request_timeout": 30
            },
            
            # Rate limiting par API
            "rate_limits": {
                "genius": {
                    "requests_per_minute": 30,
                    "requests_per_hour": 1000,
                    "burst_limit": 5,
                    "retry_after_seconds": 60
                },
                "spotify": {
                    "requests_per_minute": 100,
                    "requests_per_hour": 3000,
                    "burst_limit": 10,
                    "retry_after_seconds": 60
                },
                "discogs": {
                    "requests_per_minute": 60,
                    "requests_per_hour": 1000,
                    "burst_limit": 5,
                    "retry_after_seconds": 60
                },
                "tunebat": {
                    "requests_per_minute": 20,
                    "requests_per_hour": 500,
                    "burst_limit": 3,
                    "retry_after_seconds": 180
                },
                "rapedia": {
                    "requests_per_minute": 30,
                    "requests_per_hour": 800,
                    "burst_limit": 5,
                    "retry_after_seconds": 60
                }
            },
            
            # Cache et stockage
            "cache": {
                "enable_cache": True,
                "cache_size_mb": 100,
                "default_expire_hours": 24,
                "api_cache_expire_hours": 168,  # 1 semaine
                "scraping_cache_expire_hours": 72,  # 3 jours
                "cleanup_on_startup": True,
                "compress_cache": True
            },
            
            # Logging
            "logging": {
                "level": "INFO",
                "file_rotation": True,
                "max_file_size_mb": 10,
                "backup_count": 5,
                "console_colors": True,
                "log_api_calls": True,
                "log_scraping_activity": True,
                "session_specific_logs": True,
                "performance_logs": False
            },
            
            # Export et formats
            "exports": {
                "default_formats": ["json", "csv"],
                "include_statistics": True,
                "include_metadata": True,
                "compress_exports": False,
                "export_quality_reports": True,
                "max_export_size_mb": 50,
                "backup_exports": True
            },
            
            # Interface utilisateur
            "ui": {
                "theme": "dark",
                "show_progress_bars": True,
                "auto_refresh_interval": 5,
                "max_recent_sessions": 10,
                "enable_notifications": True,
                "compact_mode": False
            },
            
            # Sécurité
            "security": {
                "validate_urls": True,
                "sanitize_filenames": True,
                "max_file_size_mb": 100,
                "allowed_domains": [
                    "genius.com",
                    "spotify.com", 
                    "discogs.com",
                    "tunebat.com",
                    "rapedia.com"
                ],
                "enable_ssl_verification": True
            },
            
            # Fonctionnalités expérimentales
            "experimental": {
                "ai_credit_detection": False,
                "advanced_deduplication": True,
                "smart_retry_logic": True,
                "predictive_caching": False,
                "auto_quality_improvement": True
            }
        }
    
    def _validate_api_keys(self):
        """Valide que les clés API nécessaires sont présentes"""
        required_keys = {
            "GENIUS_API_KEY": self.genius_api_key,
        }
        
        optional_keys = {
            "SPOTIFY_CLIENT_ID": self.spotify_client_id,
            "SPOTIFY_CLIENT_SECRET": self.spotify_client_secret,
            "DISCOGS_TOKEN": self.discogs_token,
            "LAST_FM_API_KEY": self.lastfm_api_key
        }
        
        # Vérifier les clés obligatoires
        missing_required = [key for key, value in required_keys.items() if not value]
        if missing_required:
            print(f"❌ Clés API obligatoires manquantes: {', '.join(missing_required)}")
            print("L'application ne pourra pas fonctionner correctement.")
        
        # Vérifier les clés optionnelles
        missing_optional = [key for key, value in optional_keys.items() if not value]
        if missing_optional:
            print(f"⚠️ Clés API optionnelles manquantes: {', '.join(missing_optional)}")
            print("Certaines fonctionnalités seront limitées.")
        
        # Compter les APIs disponibles
        available_apis = len([key for key, value in {**required_keys, **optional_keys}.items() if value])
        total_apis = len(required_keys) + len(optional_keys)
        print(f"🔑 APIs configurées: {available_apis}/{total_apis}")
    
    def _ensure_directories(self):
        """Crée les dossiers nécessaires s'ils n'existent pas"""
        directories = [
            self.data_dir,
            self.cache_dir, 
            self.sessions_dir,
            self.exports_dir,
            self.logs_dir,
            self.temp_dir,
            self.screenshots_dir
        ]
        
        created_dirs = []
        for directory in directories:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                created_dirs.append(directory.name)
        
        if created_dirs:
            print(f"📁 Dossiers créés: {', '.join(created_dirs)}")
    
    def _setup_derived_config(self):
        """Configure les paramètres dérivés de la configuration principale"""
        # Mode debug global
        if self.debug_mode:
            self.config.setdefault('logging', {})['level'] = 'DEBUG'
            self.config.setdefault('selenium', {})['headless'] = False
            self.config.setdefault('performance', {})['concurrent_extractions'] = 1
        
        # Environnement de production
        if self.environment == "production":
            self.config.setdefault('selenium', {})['headless'] = True
            self.config.setdefault('logging', {})['console_colors'] = False
            self.config.setdefault('cache', {})['cleanup_on_startup'] = True
        
        # Configuration automatique selon les APIs disponibles
        if not self.spotify_client_id:
            self.config.setdefault('albums', {})['prefer_spotify'] = False
        
        if not self.discogs_token:
            self.config.setdefault('albums', {})['fallback_to_discogs'] = False
    
    def get(self, key: str, default=None):
        """
        Récupère une valeur de configuration avec notation pointée.
        
        Args:
            key: Clé de configuration (ex: "sessions.auto_save_interval")
            default: Valeur par défaut si la clé n'existe pas
            
        Returns:
            Valeur de configuration ou valeur par défaut
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """
        Définit une valeur de configuration avec notation pointée.
        
        Args:
            key: Clé de configuration (ex: "sessions.auto_save_interval")
            value: Nouvelle valeur
        """
        keys = key.split('.')
        config = self.config
        
        # Naviguer jusqu'au dernier niveau
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        
        # Définir la valeur finale
        config[keys[-1]] = value
    
    def save_config(self, file_path: Optional[Path] = None):
        """
        Sauvegarde la configuration actuelle dans un fichier YAML.
        
        Args:
            file_path: Chemin du fichier (par défaut: fichier de config principal)
        """
        target_file = file_path or self.config_file
        
        try:
            # S'assurer que le dossier parent existe
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, indent=2, allow_unicode=True)
            
            print(f"✅ Configuration sauvegardée dans {target_file}")
            
        except Exception as e:
            print(f"❌ Erreur lors de la sauvegarde de la config: {e}")
    
    def reload_config(self):
        """Recharge la configuration depuis le fichier"""
        old_config = self.config.copy()
        self.config = self._load_config()
        self._setup_derived_config()
        
        print("🔄 Configuration rechargée")
        
        # Retourner les changements pour logging
        return {
            'old': old_config,
            'new': self.config
        }
    
    def get_api_config(self, api_name: str) -> Dict[str, Any]:
        """
        Récupère la configuration complète pour une API spécifique.
        
        Args:
            api_name: Nom de l'API (genius, spotify, discogs, etc.)
            
        Returns:
            Configuration de l'API avec clés, rate limits, etc.
        """
        api_config = {
            'rate_limits': self.get(f'rate_limits.{api_name}', {}),
            'timeout': self.get('performance.request_timeout', 30),
            'enabled': True
        }
        
        # Ajouter les clés API spécifiques
        if api_name == 'genius':
            api_config['api_key'] = self.genius_api_key
            api_config['enabled'] = bool(self.genius_api_key)
        elif api_name == 'spotify':
            api_config['client_id'] = self.spotify_client_id
            api_config['client_secret'] = self.spotify_client_secret
            api_config['enabled'] = bool(self.spotify_client_id and self.spotify_client_secret)
        elif api_name == 'discogs':
            api_config['token'] = self.discogs_token
            api_config['enabled'] = bool(self.discogs_token)
        elif api_name == 'lastfm':
            api_config['api_key'] = self.lastfm_api_key
            api_config['enabled'] = bool(self.lastfm_api_key)
        
        return api_config
    
    def get_file_paths(self) -> Dict[str, Path]:
        """Retourne tous les chemins de fichiers importants"""
        return {
            'project_root': self.project_root,
            'data_dir': self.data_dir,
            'cache_dir': self.cache_dir,
            'sessions_dir': self.sessions_dir,
            'exports_dir': self.exports_dir,
            'logs_dir': self.logs_dir,
            'temp_dir': self.temp_dir,
            'screenshots_dir': self.screenshots_dir,
            'config_file': self.config_file,
            'credit_mappings_file': self.credit_mappings_file
        }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Retourne les informations système pour diagnostic"""
        return {
            'environment': self.environment,
            'debug_mode': self.debug_mode,
            'project_root': str(self.project_root),
            'config_loaded': self.config_file.exists(),
            'api_keys_available': {
                'genius': bool(self.genius_api_key),
                'spotify': bool(self.spotify_client_id and self.spotify_client_secret),
                'discogs': bool(self.discogs_token),
                'lastfm': bool(self.lastfm_api_key)
            },
            'directories_exist': {
                name: path.exists() 
                for name, path in self.get_file_paths().items()
                if isinstance(path, Path)
            }
        }
    
    def validate_configuration(self) -> List[str]:
        """
        Valide la configuration et retourne une liste des problèmes trouvés.
        
        Returns:
            Liste des messages d'erreur ou avertissements
        """
        issues = []
        
        # Validation des valeurs numériques
        numeric_checks = [
            ('sessions.auto_save_interval', 10, 3600),
            ('sessions.max_sessions', 1, 50),
            ('performance.batch_size', 1, 100),
            ('performance.concurrent_extractions', 1, 10),
            ('quality.min_duration_seconds', 1, 300),
            ('quality.max_duration_seconds', 300, 7200)
        ]
        
        for key, min_val, max_val in numeric_checks:
            value = self.get(key)
            if value is not None:
                if not isinstance(value, (int, float)) or value < min_val or value > max_val:
                    issues.append(f"Valeur invalide pour {key}: {value} (doit être entre {min_val} et {max_val})")
        
        # Validation des chemins
        critical_paths = ['data_dir', 'cache_dir', 'logs_dir']
        for path_name in critical_paths:
            path = getattr(self, path_name, None)
            if path and not path.exists():
                issues.append(f"Dossier manquant: {path_name} ({path})")
        
        # Validation de la cohérence
        if self.get('albums.prefer_spotify') and not self.spotify_client_id:
            issues.append("albums.prefer_spotify activé mais clé API Spotify manquante")
        
        if self.get('albums.fallback_to_discogs') and not self.discogs_token:
            issues.append("albums.fallback_to_discogs activé mais token Discogs manquant")
        
        return issues

# Instance globale des settings
settings = Settings()

# Fonction de convenance pour accès rapide
def get_setting(key: str, default=None):
    """Fonction de convenance pour récupérer une configuration"""
    return settings.get(key, default)

def set_setting(key: str, value: Any):
    """Fonction de convenance pour définir une configuration"""
    return settings.set(key, value)