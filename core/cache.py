# core/cache.py
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, Callable, List
from functools import wraps
import fnmatch

from config.settings import settings
from core.database import Database

class CacheManager:
    """Gestionnaire de cache intelligent avec expiration automatique"""
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.default_expire_days = settings.get('performance.cache_expire_days', 7)
    
    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Génère une clé de cache unique basée sur les paramètres"""
        # Créer une chaîne unique à partir des arguments
        key_data = {
            'args': args,
            'kwargs': kwargs
        }
        key_string = json.dumps(key_data, sort_keys=True, default=str)
        
        # Hasher pour éviter les clés trop longues
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        
        return f"{prefix}:{key_hash}"
    
    def get(self, key: str) -> Optional[Any]:
        """Récupère une valeur du cache"""
        return self.db.get_cache(key)
    
    def set(self, key: str, value: Any, expire_days: Optional[int] = None) -> None:
        """Met une valeur en cache avec expiration"""
        if expire_days is None:
            expire_days = self.default_expire_days
        
        expires_at = datetime.now() + timedelta(days=expire_days)
        self.db.set_cache(key, value, expires_at)
    
    def delete(self, key: str) -> None:
        """Supprime une entrée du cache"""
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM cache WHERE cache_key = ?", (key,))
    
    def clear_expired(self) -> None:
        """Nettoie le cache expiré"""
        self.db.clear_expired_cache()
    
    def clear_all(self) -> None:
        """Vide tout le cache"""
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM cache")
    
    def get_cache_keys(self, pattern: Optional[str] = None) -> List[str]:
        """Récupère toutes les clés de cache, optionnellement filtrées par pattern"""
        with self.db.get_connection() as conn:
            if pattern:
                cursor = conn.execute(
                    "SELECT cache_key FROM cache WHERE cache_key LIKE ?",
                    (pattern.replace('*', '%'),)
                )
            else:
                cursor = conn.execute("SELECT cache_key FROM cache")
            
            return [row['cache_key'] for row in cursor.fetchall()]
    
    def cached_api_call(self, api_name: str, expire_days: int = 7):
        """Décorateur pour mettre en cache les appels API"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Générer la clé de cache
                cache_key = self._generate_cache_key(f"api:{api_name}:{func.__name__}", *args, **kwargs)
                
                # Vérifier le cache
                cached_result = self.get(cache_key)
                if cached_result is not None:
                    print(f"🎯 Cache hit pour {api_name}: {func.__name__}")
                    return cached_result
                
                # Appeler la fonction et mettre en cache
                print(f"⏳ Appel API {api_name}: {func.__name__}")
                result = func(*args, **kwargs)
                if result is not None:  # Ne pas cacher les résultats vides
                    self.set(cache_key, result, expire_days)
                    print(f"💾 Résultat mis en cache pour {api_name}")
                
                return result
            
            return wrapper
        return decorator
    
    def cached_extraction(self, source: str, expire_days: int = 7):
        """Décorateur spécialisé pour les extractions de données"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                cache_key = self._generate_cache_key(f"extraction:{source}:{func.__name__}", *args, **kwargs)
                
                cached_result = self.get(cache_key)
                if cached_result is not None:
                    print(f"🎯 Cache hit pour {source}: {func.__name__}")
                    return cached_result
                
                print(f"⏳ Extraction {source}: {func.__name__}")
                result = func(*args, **kwargs)
                
                if result is not None:
                    self.set(cache_key, result, expire_days)
                    print(f"💾 Résultat mis en cache pour {source}")
                
                return result
            
            return wrapper
        return decorator

class SmartCache:
    """Cache intelligent avec invalidation automatique"""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
        self.invalidation_rules = self._setup_invalidation_rules()
    
    def _setup_invalidation_rules(self) -> Dict[str, List[str]]:
        """Définit les règles d'invalidation du cache"""
        return {
            # Quand un track est modifié, invalider ses caches
            'track_updated': [
                'api:genius:*',
                'api:spotify:*',
                'extraction:*'
            ],
            # Quand un artiste est modifié
            'artist_updated': [
                'api:genius:artist:*',
                'api:spotify:artist:*'
            ],
            # Quand de nouveaux crédits sont ajoutés
            'credits_updated': [
                'extraction:genius:credits:*',
                'stats:*'
            ]
        }
    
    def invalidate_by_event(self, event: str, entity_id: Optional[str] = None):
        """Invalide le cache basé sur un événement"""
        if event in self.invalidation_rules:
            patterns = self.invalidation_rules[event]
            for pattern in patterns:
                if entity_id:
                    pattern = pattern.replace('*', f'*{entity_id}*')
                self._invalidate_pattern(pattern)
    
    def _invalidate_pattern(self, pattern: str):
        """Invalide les entrées de cache correspondant à un pattern"""
        # Récupérer toutes les clés de cache
        all_keys = self.cache.get_cache_keys()
        
        # Trouver les clés qui correspondent au pattern
        matching_keys = []
        for key in all_keys:
            if fnmatch.fnmatch(key, pattern):
                matching_keys.append(key)
        
        # Supprimer les clés correspondantes
        for key in matching_keys:
            self.cache.delete(key)
        
        if matching_keys:
            print(f"🗑️ Invalidé {len(matching_keys)} entrées de cache pour le pattern: {pattern}")

class CacheStats:
    """Statistiques et monitoring du cache"""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
    
    def get_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques du cache"""
        with self.cache.db.get_connection() as conn:
            # Nombre total d'entrées
            cursor = conn.execute("SELECT COUNT(*) as count FROM cache")
            total_entries = cursor.fetchone()['count']
            
            # Entrées expirées
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM cache 
                WHERE expires_at IS NOT NULL AND expires_at < ?
            """, (datetime.now().isoformat(),))
            expired_entries = cursor.fetchone()['count']
            
            # Taille approximative du cache
            cursor = conn.execute("SELECT SUM(LENGTH(data)) as size FROM cache")
            cache_size_bytes = cursor.fetchone()['size'] or 0
            
            # Répartition par préfixe
            cursor = conn.execute("""
                SELECT SUBSTR(cache_key, 1, INSTR(cache_key || ':', ':') - 1) as prefix,
                       COUNT(*) as count
                FROM cache
                GROUP BY prefix
                ORDER BY count DESC
            """)
            prefix_stats = {row['prefix']: row['count'] for row in cursor.fetchall()}
            
            return {
                'total_entries': total_entries,
                'expired_entries': expired_entries,
                'active_entries': total_entries - expired_entries,
                'cache_size_bytes': cache_size_bytes,
                'cache_size_mb': round(cache_size_bytes / (1024 * 1024), 2),
                'prefix_distribution': prefix_stats,
                'hit_rate': self._calculate_hit_rate()
            }
    
    def _calculate_hit_rate(self) -> float:
        """Calcule approximativement le taux de réussite du cache"""
        # Simplification: basé sur le ratio entrées actives / total
        stats = self.get_stats()
        if stats['total_entries'] == 0:
            return 0.0
        
        return round((stats['active_entries'] / stats['total_entries']) * 100, 2)
    
    def cleanup_recommendations(self) -> List[str]:
        """Recommandations pour optimiser le cache"""
        recommendations = []
        stats = self.get_stats()
        
        if stats['expired_entries'] > 0:
            recommendations.append(f"Nettoyer {stats['expired_entries']} entrées expirées")
        
        if stats['cache_size_mb'] > 50:  # Si > 50MB
            recommendations.append(f"Cache volumineux ({stats['cache_size_mb']}MB), considérer un nettoyage")
        
        # Analyser la distribution des préfixes
        total = stats['total_entries']
        for prefix, count in stats['prefix_distribution'].items():
            percentage = (count / total) * 100
            if percentage > 50:
                recommendations.append(f"Préfixe '{prefix}' représente {percentage:.1f}% du cache")
        
        return recommendations

# Instance globale du gestionnaire de cache
cache_manager = CacheManager()
smart_cache = SmartCache(cache_manager)
cache_stats = CacheStats(cache_manager)