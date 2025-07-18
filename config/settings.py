# config/settings.py - VERSION OPTIMISÉE
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import lru_cache
import threading

class Settings:
    """Configuration centralisée du projet Music Data Extractor"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton thread-safe"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Éviter la réinitialisation multiple du singleton
        if hasattr(self, '_initialized'):
            return
        
        self.project_root = Path(__file__).parent.parent
        self.config_file = self.project_root / "config" / "default_config.yaml"
        self.credit_mappings_file = self.project_root / "config" / "credit_mappings.yaml"
        
        # Chargement de la configuration avec cache
        self.config = self._load_config()
        
        # Variables d'environnement - Mise en cache pour éviter les accès répétés
        self._api_keys = self._load_api_keys()
        
        # Variables d'environnement - Configuration
        self.environment = os.getenv("MDE_ENV", "development")
        self.debug_mode = os.getenv("MDE_DEBUG", "false").lower() == "true"
        
        # Validation des clés API
        self._validate_api_keys()
        
        # Chemins des dossiers - calculés une seule fois
        self._paths = self._calculate_paths()
        
        # Création des dossiers si nécessaires
        self._ensure_directories()
        
        # Configuration dérivée
        self._setup_derived_config()
        
        self._initialized = True
    
    @property
    def genius_api_key(self) -> Optional[str]:
        return self._api_keys.get('genius')
    
    @property
    def discogs_token(self) -> Optional[str]:
        return self._api_keys.get('discogs')
    
    @property
    def lastfm_api_key(self) -> Optional[str]:
        return self._api_keys.get('lastfm')
    
    @property
    def spotify_client_id(self) -> Optional[str]:
        return self._api_keys.get('spotify_id')
    
    @property
    def spotify_client_secret(self) -> Optional[str]:
        return self._api_keys.get('spotify_secret')
    
    @property
    def data_dir(self) -> Path:
        return self._paths['data_dir']
    
    @property
    def cache_dir(self) -> Path:
        return self._paths['cache_dir']
    
    @property
    def sessions_dir(self) -> Path:
        return self._paths['sessions_dir']
    
    @property
    def exports_dir(self) -> Path:
        return self._paths['exports_dir']
    
    @property
    def logs_dir(self) -> Path:
        return self._paths['logs_dir']
    
    @property
    def temp_dir(self) -> Path:
        return self._paths['temp_dir']
    
    @property
    def screenshots_dir(self) -> Path:
        return self._paths['screenshots_dir']
    
    def _load_api_keys(self) -> Dict[str, Optional[str]]:
        """Charge toutes les clés API en une seule fois"""
        return {
            'genius': os.getenv("GENIUS_API_KEY"),
            'discogs': os.getenv("DISCOGS_TOKEN"),
            'lastfm': os.getenv("LAST_FM_API_KEY"),
            'spotify_id': os.getenv("SPOTIFY_CLIENT_ID"),
            'spotify_secret': os.getenv("SPOTIFY_CLIENT_SECRET")
        }
    
    def _calculate_paths(self) -> Dict[str, Path]:
        """Calcule tous les chemins en une seule fois"""
        data_dir = self.project_root / "data"
        logs_dir = self.project_root / "logs"
        
        return {
            'data_dir': data_dir,
            'cache_dir': data_dir / "cache",
            'sessions_dir': data_dir / "sessions",
            'exports_dir': data_dir / "exports",
            'logs_dir': logs_dir,
            'temp_dir': data_dir / "temp",
            'screenshots_dir': logs_dir / "screenshots"
        }
    
    @lru_cache(maxsize=1)
    def _load_config(self) -> Dict[str, Any]:
        """Charge la configuration depuis le fichier YAML avec cache"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                print(f"✅ Configuration chargée depuis {self.config_file}")
                return config
            else:
                print(f"⚠️ Fichier de config non trouvé: {self.config_file}")
                print("📁 Utilisation de la configuration par défaut")
                return self._get_default_config()
                
        except Exception as e:
            print(f"❌ Erreur lors du chargement de la config: {e}")
            print("📁 Utilisation de la configuration par défaut")
            return self._get_default_config()
    
    @lru_cache(maxsize=1)
    def _get_default_config(self) -> Dict[str, Any]:
        """Configuration par défaut du projet - mise en cache"""
        return {
            # Configuration des sessions
            'sessions': {
                'auto_save_interval': 60,  # secondes
                'max_sessions': 10,
                'cleanup_completed_after_days': 7,
                'default_max_tracks': 200,
                'pause_between_batches': 2.0
            },
            
            # Configuration de performance
            'performance': {
                'concurrent_extractions': 3,
                'batch_size': 15,
                'request_timeout': 30,
                'max_retries': 3,
                'retry_delay': 5.0
            },
            
            # Configuration du cache
            'cache': {
                'enabled': True,
                'ttl_hours': 168,  # 7 jours
                'max_size_mb': 500,
                'cleanup_on_startup': False,
                'compress_data': True
            },
            
            # Configuration des albums
            'albums': {
                'prefer_spotify': True,
                'fallback_to_discogs': True,
                'match_threshold': 0.8,
                'include_singles': True
            },
            
            # Configuration de qualité
            'quality': {
                'min_duration_seconds': 30,
                'max_duration_seconds': 600,
                'require_credits': False,
                'skip_instrumentals': False
            },
            
            # Configuration Selenium
            'selenium': {
                'headless': True,
                'window_size': [1920, 1080],
                'implicit_wait': 10,
                'page_load_timeout': 30,
                'screenshot_on_error': True
            },
            
            # Configuration des exports
            'exports': {
                'include_lyrics': True,
                'include_raw_data': False,
                'default_format': 'json',
                'auto_cleanup_days': 30
            },
            
            # Configuration du logging
            'logging': {
                'level': 'INFO',
                'console_colors': True,
                'file_rotation': 'daily',
                'max_file_size_mb': 10,
                'keep_files_days': 30
            },
            
            # Configuration des rate limits
            'rate_limits': {
                'genius': {
                    'requests_per_minute': 30,
                    'burst_limit': 10
                },
                'spotify': {
                    'requests_per_minute': 100,
                    'burst_limit': 20
                },
                'discogs': {
                    'requests_per_minute': 60,
                    'burst_limit': 15
                },
                'lastfm': {
                    'requests_per_minute': 300,
                    'burst_limit': 50
                },
                'rapedia': {
                    'requests_per_minute': 30,
                    'burst_limit': 5
                }
            }
        }
    
    def _validate_api_keys(self):
        """Valide et affiche le statut des clés API - optimisé"""
        # Regroupement des vérifications pour efficacité
        required_keys = {'genius': self.genius_api_key}
        optional_keys = {
            'spotify': self.spotify_client_id and self.spotify_client_secret,
            'discogs': self.discogs_token,
            'lastfm': self.lastfm_api_key
        }
        
        # Calcul unique des statistiques
        missing_required = [key for key, value in required_keys.items() if not value]
        missing_optional = [key for key, value in optional_keys.items() if not value]
        available_apis = len(required_keys) + len(optional_keys) - len(missing_required) - len(missing_optional)
        total_apis = len(required_keys) + len(optional_keys)
        
        # Affichage groupé pour réduire les I/O
        if missing_required:
            print(f"❌ Clés API requises manquantes: {', '.join(missing_required)}")
            print("⚠️ L'application ne fonctionnera pas correctement sans ces clés")
        else:
            print("✅ Toutes les clés API requises sont configurées")
        
        if missing_optional:
            print(f"⚠️ Clés API optionnelles manquantes: {', '.join(missing_optional)}")
            print("Certaines fonctionnalités seront limitées.")
        
        print(f"🔑 APIs configurées: {available_apis}/{total_apis}")
    
    def _ensure_directories(self):
        """Crée les dossiers nécessaires - version optimisée"""
        directories = list(self._paths.values())
        
        # Création en lot avec gestion d'erreurs optimisée
        created_dirs = []
        for directory in directories:
            if not directory.exists():
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                    created_dirs.append(directory.name)
                except OSError as e:
                    print(f"❌ Erreur création dossier {directory.name}: {e}")
        
        if created_dirs:
            print(f"📁 Dossiers créés: {', '.join(created_dirs)}")
    
    def _setup_derived_config(self):
        """Configure les paramètres dérivés - version optimisée"""
        # Éviter les setdefault répétés en groupant les modifications
        if self.debug_mode:
            self.config.setdefault('logging', {}).update({
                'level': 'DEBUG'
            })
            self.config.setdefault('selenium', {}).update({
                'headless': False
            })
            self.config.setdefault('performance', {}).update({
                'concurrent_extractions': 1
            })
        
        if self.environment == "production":
            self.config.setdefault('selenium', {}).update({
                'headless': True
            })
            self.config.setdefault('logging', {}).update({
                'console_colors': False
            })
            self.config.setdefault('cache', {}).update({
                'cleanup_on_startup': True
            })
        
        # Configuration conditionnelle des APIs
        albums_config = self.config.setdefault('albums', {})
        if not self.spotify_client_id:
            albums_config['prefer_spotify'] = False
        if not self.discogs_token:
            albums_config['fallback_to_discogs'] = False
    
    @lru_cache(maxsize=128)
    def get(self, key: str, default=None):
        """
        Récupère une valeur de configuration avec cache LRU.
        
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
        Définit une valeur de configuration avec invalidation du cache.
        
        Args:
            key: Clé de configuration (ex: "sessions.auto_save_interval")
            value: Nouvelle valeur
        """
        # Invalider le cache LRU lors des modifications
        self.get.cache_clear()
        
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
        """Sauvegarde optimisée de la configuration"""
        target_file = file_path or self.config_file
        
        try:
            # S'assurer que le dossier parent existe
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Sauvegarde atomique via fichier temporaire
            temp_file = target_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, indent=2, allow_unicode=True)
            
            # Renommage atomique
            temp_file.replace(target_file)
            print(f"✅ Configuration sauvegardée dans {target_file}")
            
        except Exception as e:
            print(f"❌ Erreur lors de la sauvegarde de la config: {e}")
    
    def reload_config(self):
        """Recharge la configuration avec invalidation du cache"""
        old_config = self.config.copy()
        
        # Invalider les caches
        self._load_config.cache_clear()
        self.get.cache_clear()
        
        self.config = self._load_config()
        self._setup_derived_config()
        
        print("🔄 Configuration rechargée")
        
        return {
            'old': old_config,
            'new': self.config
        }
    
    @lru_cache(maxsize=32)
    def get_api_config(self, api_name: str) -> Dict[str, Any]:
        """
        Configuration API avec cache pour éviter les recalculs.
        
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
        
        # Mapping optimisé des clés API
        api_key_mapping = {
            'genius': ('api_key', self.genius_api_key),
            'spotify': ('client_credentials', (self.spotify_client_id, self.spotify_client_secret)),
            'discogs': ('token', self.discogs_token),
            'lastfm': ('api_key', self.lastfm_api_key)
        }
        
        if api_name in api_key_mapping:
            key_type, key_value = api_key_mapping[api_name]
            
            if api_name == 'spotify':
                api_config['client_id'] = key_value[0]
                api_config['client_secret'] = key_value[1]
                api_config['enabled'] = bool(key_value[0] and key_value[1])
            else:
                api_config[key_type] = key_value
                api_config['enabled'] = bool(key_value)
        
        return api_config
    
    @lru_cache(maxsize=1)
    def get_file_paths(self) -> Dict[str, Path]:
        """Retourne tous les chemins de fichiers - avec cache"""
        return {
            'project_root': self.project_root,
            **self._paths,
            'config_file': self.config_file,
            'credit_mappings_file': self.credit_mappings_file
        }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Informations système optimisées"""
        # Calcul unique des états d'existence des fichiers
        file_paths = self.get_file_paths()
        directories_exist = {
            name: path.exists() 
            for name, path in file_paths.items()
            if isinstance(path, Path) and name.endswith('_dir')
        }
        
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
            'directories_exist': directories_exist
        }
    
    def validate_configuration(self) -> List[str]:
        """Validation optimisée de la configuration"""
        issues = []
        
        # Validation groupée des valeurs numériques
        numeric_checks = [
            ('sessions.auto_save_interval', 10, 3600),
            ('sessions.max_sessions', 1, 50),
            ('performance.batch_size', 1, 100),
            ('performance.concurrent_extractions', 1, 10),
            ('quality.min_duration_seconds', 1, 300),
            ('quality.max_duration_seconds', 300, 7200)
        ]
        
        # Traitement en lot pour réduire les appels get()
        values_to_check = {key: self.get(key) for key, _, _ in numeric_checks}
        
        for (key, min_val, max_val) in numeric_checks:
            value = values_to_check[key]
            if value is not None:
                if not isinstance(value, (int, float)) or value < min_val or value > max_val:
                    issues.append(f"Valeur invalide pour {key}: {value} (doit être entre {min_val} et {max_val})")
        
        # Validation groupée des chemins critiques
        critical_paths = ['data_dir', 'cache_dir', 'logs_dir']
        for path_name in critical_paths:
            path = self._paths.get(path_name)
            if path and not path.exists():
                issues.append(f"Dossier manquant: {path_name} ({path})")
        
        # Validation de cohérence
        cohérence_checks = [
            ('albums.prefer_spotify', self.spotify_client_id, "clé API Spotify"),
            ('albums.fallback_to_discogs', self.discogs_token, "token Discogs")
        ]
        
        for setting_key, required_value, description in cohérence_checks:
            if self.get(setting_key) and not required_value:
                issues.append(f"{setting_key} activé mais {description} manquante")
        
        return issues

# Instance globale des settings (Singleton)
settings = Settings()

# Fonctions de convenance pour accès rapide
def get_setting(key: str, default=None):
    """Fonction de convenance pour récupérer une configuration"""
    return settings.get(key, default)

def set_setting(key: str, value: Any):
    """Fonction de convenance pour définir une configuration"""
    return settings.set(key, value)