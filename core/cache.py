# core/cache.py
import hashlib
import json
import pickle
import zlib
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, Callable, List, Union, Tuple
from functools import wraps, lru_cache
import fnmatch
import threading
from contextlib import contextmanager

from config.settings import settings
from core.database import Database
from core.exceptions import CacheError, CacheExpiredError, CacheCorruptedError


class CacheManager:
    """Gestionnaire de cache intelligent avec expiration automatique et optimisations"""
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.default_expire_days = settings.get('cache.ttl_hours', 168) // 24  # Convertir heures en jours
        self.max_size_mb = settings.get('cache.max_size_mb', 500)
        self.compress_data = settings.get('cache.compress_data', True)
        
        # Cache en mémoire pour les accès fréquents
        self._memory_cache: Dict[str, Tuple[Any, datetime]] = {}
        self._memory_cache_lock = threading.RLock()
        self._cache_stats = {
            'hits': 0,
            'misses': 0,
            'memory_hits': 0,
            'db_hits': 0,
            'sets': 0,
            'deletes': 0,
            'size_bytes': 0
        }
        
        # Configuration
        self.memory_cache_size = settings.get('cache.memory_cache_entries', 1000)
        self.auto_cleanup_enabled = settings.get('cache.cleanup_on_startup', False)
        
        if self.auto_cleanup_enabled:
            self._auto_cleanup()
    
    @lru_cache(maxsize=1024)
    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Génère une clé de cache unique basée sur les paramètres - avec cache LRU"""
        # Créer une chaîne unique à partir des arguments
        key_data = {
            'args': args,
            'kwargs': kwargs
        }
        key_string = json.dumps(key_data, sort_keys=True, default=str)
        
        # Hasher pour éviter les clés trop longues
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        
        return f"{prefix}:{key_hash}"
    
    def _serialize_value(self, value: Any) -> bytes:
        """Sérialise et compresse optionnellement une valeur"""
        try:
            serialized = pickle.dumps(value)
            
            if self.compress_data and len(serialized) > 1024:  # Compresser si > 1KB
                return zlib.compress(serialized)
            
            return serialized
        except Exception as e:
            raise CacheCorruptedError("serialization", f"Erreur sérialisation: {e}")
    
    def _deserialize_value(self, data: bytes) -> Any:
        """Désérialise et décompresse optionnellement une valeur"""
        try:
            # Tenter de décompresser d'abord
            try:
                if self.compress_data:
                    data = zlib.decompress(data)
            except zlib.error:
                # Pas compressé, continuer
                pass
            
            return pickle.loads(data)
        except Exception as e:
            raise CacheCorruptedError("deserialization", f"Erreur désérialisation: {e}")
    
    def _check_memory_cache(self, key: str) -> Optional[Any]:
        """Vérifie le cache en mémoire"""
        with self._memory_cache_lock:
            if key in self._memory_cache:
                value, expires_at = self._memory_cache[key]
                if expires_at > datetime.now():
                    self._cache_stats['memory_hits'] += 1
                    self._cache_stats['hits'] += 1
                    return value
                else:
                    # Expiré, supprimer
                    del self._memory_cache[key]
        return None
    
    def _set_memory_cache(self, key: str, value: Any, expires_at: datetime):
        """Met en cache en mémoire avec gestion de la taille"""
        with self._memory_cache_lock:
            # Nettoyage si cache plein
            if len(self._memory_cache) >= self.memory_cache_size:
                self._evict_memory_cache()
            
            self._memory_cache[key] = (value, expires_at)
    
    def _evict_memory_cache(self):
        """Éviction LRU du cache mémoire"""
        # Supprimer les entrées expirées d'abord
        now = datetime.now()
        expired_keys = [
            key for key, (_, expires_at) in self._memory_cache.items()
            if expires_at <= now
        ]
        
        for key in expired_keys:
            del self._memory_cache[key]
        
        # Si encore trop plein, supprimer 25% des plus anciennes
        if len(self._memory_cache) >= self.memory_cache_size:
            items_to_remove = max(1, len(self._memory_cache) // 4)
            # Trier par date d'expiration (plus proche = plus ancien)
            sorted_items = sorted(
                self._memory_cache.items(),
                key=lambda x: x[1][1]  # Trier par expires_at
            )
            
            for i in range(items_to_remove):
                key = sorted_items[i][0]
                del self._memory_cache[key]
    
    def get(self, key: str) -> Optional[Any]:
        """Récupère une valeur du cache avec cache multi-niveau"""
        # Vérifier cache mémoire d'abord
        memory_result = self._check_memory_cache(key)
        if memory_result is not None:
            return memory_result
        
        # Puis base de données
        try:
            db_result = self.db.get_cache(key)
            if db_result is not None:
                # Ajouter au cache mémoire pour les prochains accès
                expires_at = datetime.now() + timedelta(days=self.default_expire_days)
                self._set_memory_cache(key, db_result, expires_at)
                
                self._cache_stats['db_hits'] += 1
                self._cache_stats['hits'] += 1
                return db_result
            
            self._cache_stats['misses'] += 1
            return None
            
        except Exception as e:
            raise CacheError(f"Erreur lecture cache: {e}")
    
    def set(self, key: str, value: Any, expire_days: Optional[int] = None) -> None:
        """Met une valeur en cache avec optimisations"""
        if expire_days is None:
            expire_days = self.default_expire_days
        
        expires_at = datetime.now() + timedelta(days=expire_days)
        
        try:
            # Sauvegarder en base
            self.db.set_cache(key, value, expires_at)
            
            # Ajouter au cache mémoire
            self._set_memory_cache(key, value, expires_at)
            
            self._cache_stats['sets'] += 1
            
            # Vérifier la taille du cache périodiquement
            if self._cache_stats['sets'] % 100 == 0:
                self._check_cache_size()
                
        except Exception as e:
            raise CacheError(f"Erreur écriture cache: {e}")
    
    def delete(self, key: str) -> None:
        """Supprime une entrée du cache"""
        try:
            # Supprimer de la base
            with self.db.get_connection() as conn:
                conn.execute("DELETE FROM cache WHERE cache_key = ?", (key,))
            
            # Supprimer du cache mémoire
            with self._memory_cache_lock:
                self._memory_cache.pop(key, None)
            
            self._cache_stats['deletes'] += 1
            
        except Exception as e:
            raise CacheError(f"Erreur suppression cache: {e}")
    
    def clear_expired(self) -> int:
        """Nettoie le cache expiré et retourne le nombre d'entrées supprimées"""
        try:
            # Nettoyer base de données
            count_db = self.db.clear_expired_cache()
            
            # Nettoyer cache mémoire
            now = datetime.now()
            with self._memory_cache_lock:
                expired_keys = [
                    key for key, (_, expires_at) in self._memory_cache.items()
                    if expires_at <= now
                ]
                for key in expired_keys:
                    del self._memory_cache[key]
            
            total_cleaned = count_db + len(expired_keys)
            if total_cleaned > 0:
                print(f"🗑️ Cache nettoyé: {total_cleaned} entrées expirées supprimées")
            
            return total_cleaned
            
        except Exception as e:
            raise CacheError(f"Erreur nettoyage cache: {e}")
    
    def clear_all(self) -> None:
        """Vide tout le cache"""
        try:
            with self.db.get_connection() as conn:
                conn.execute("DELETE FROM cache")
            
            with self._memory_cache_lock:
                self._memory_cache.clear()
            
            # Reset des stats
            self._cache_stats = {key: 0 for key in self._cache_stats}
            
            print("🗑️ Cache entièrement vidé")
            
        except Exception as e:
            raise CacheError(f"Erreur vidage cache: {e}")
    
    def get_cache_keys(self, pattern: Optional[str] = None) -> List[str]:
        """Récupère toutes les clés de cache, optionnellement filtrées par pattern"""
        try:
            with self.db.get_connection() as conn:
                if pattern:
                    # Convertir pattern Unix vers SQL LIKE
                    sql_pattern = pattern.replace('*', '%').replace('?', '_')
                    cursor = conn.execute(
                        "SELECT cache_key FROM cache WHERE cache_key LIKE ? ORDER BY cache_key",
                        (sql_pattern,)
                    )
                else:
                    cursor = conn.execute("SELECT cache_key FROM cache ORDER BY cache_key")
                
                return [row['cache_key'] for row in cursor.fetchall()]
                
        except Exception as e:
            raise CacheError(f"Erreur récupération clés cache: {e}")
    
    def _check_cache_size(self):
        """Vérifie et gère la taille du cache"""
        try:
            stats = self.get_stats()
            if stats['cache_size_mb'] > self.max_size_mb:
                # Supprimer 25% des entrées les plus anciennes
                self._cleanup_old_entries(0.25)
                
        except Exception as e:
            print(f"⚠️ Erreur vérification taille cache: {e}")
    
    def _cleanup_old_entries(self, percentage: float):
        """Supprime un pourcentage des entrées les plus anciennes"""
        try:
            with self.db.get_connection() as conn:
                # Compter le nombre total d'entrées
                cursor = conn.execute("SELECT COUNT(*) as count FROM cache")
                total_count = cursor.fetchone()['count']
                
                entries_to_remove = int(total_count * percentage)
                if entries_to_remove > 0:
                    # Supprimer les plus anciennes
                    conn.execute("""
                        DELETE FROM cache 
                        WHERE cache_key IN (
                            SELECT cache_key FROM cache 
                            ORDER BY created_at ASC 
                            LIMIT ?
                        )
                    """, (entries_to_remove,))
                    
                    print(f"🗑️ Nettoyage cache: {entries_to_remove} anciennes entrées supprimées")
                    
        except Exception as e:
            print(f"⚠️ Erreur nettoyage entrées anciennes: {e}")
    
    def _auto_cleanup(self):
        """Nettoyage automatique au démarrage"""
        try:
            expired_count = self.clear_expired()
            stats = self.get_stats()
            
            if stats['cache_size_mb'] > self.max_size_mb * 0.8:  # Si > 80% de la limite
                self._cleanup_old_entries(0.2)  # Supprimer 20% des anciennes
                
        except Exception as e:
            print(f"⚠️ Erreur nettoyage automatique: {e}")
    
    @contextmanager
    def batch_operations(self):
        """Context manager pour les opérations en lot"""
        # Désactiver temporairement les vérifications de taille
        old_check_frequency = 100
        try:
            yield
        finally:
            # Vérifier la taille une fois à la fin
            self._check_cache_size()
    
    def get_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques détaillées du cache"""
        try:
            with self.db.get_connection() as conn:
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
                
                # Stats du cache mémoire
                memory_stats = {
                    'entries': len(self._memory_cache),
                    'max_entries': self.memory_cache_size
                }
                
                # Calcul du hit rate
                total_requests = self._cache_stats['hits'] + self._cache_stats['misses']
                hit_rate = (self._cache_stats['hits'] / total_requests * 100) if total_requests > 0 else 0
                
                return {
                    'total_entries': total_entries,
                    'expired_entries': expired_entries,
                    'active_entries': total_entries - expired_entries,
                    'cache_size_bytes': cache_size_bytes,
                    'cache_size_mb': round(cache_size_bytes / (1024 * 1024), 2),
                    'max_size_mb': self.max_size_mb,
                    'prefix_distribution': prefix_stats,
                    'memory_cache': memory_stats,
                    'performance': {
                        'hit_rate': round(hit_rate, 2),
                        'total_hits': self._cache_stats['hits'],
                        'total_misses': self._cache_stats['misses'],
                        'memory_hits': self._cache_stats['memory_hits'],
                        'db_hits': self._cache_stats['db_hits'],
                        'total_sets': self._cache_stats['sets'],
                        'total_deletes': self._cache_stats['deletes']
                    }
                }
                
        except Exception as e:
            raise CacheError(f"Erreur récupération stats cache: {e}")
    
    def cleanup_recommendations(self) -> List[str]:
        """Recommandations pour optimiser le cache"""
        recommendations = []
        stats = self.get_stats()
        
        if stats['expired_entries'] > 0:
            recommendations.append(f"Nettoyer {stats['expired_entries']} entrées expirées")
        
        if stats['cache_size_mb'] > self.max_size_mb * 0.9:
            recommendations.append(f"Cache proche de la limite ({stats['cache_size_mb']}/{self.max_size_mb}MB)")
        
        # Analyser la performance
        perf = stats['performance']
        if perf['hit_rate'] < 70:
            recommendations.append(f"Taux de réussite faible ({perf['hit_rate']}%), considérer augmenter TTL")
        
        # Analyser la distribution des préfixes
        total = stats['total_entries']
        for prefix, count in stats['prefix_distribution'].items():
            percentage = (count / total) * 100
            if percentage > 50:
                recommendations.append(f"Préfixe '{prefix}' représente {percentage:.1f}% du cache")
        
        # Cache mémoire
        memory_usage = (stats['memory_cache']['entries'] / stats['memory_cache']['max_entries']) * 100
        if memory_usage > 90:
            recommendations.append(f"Cache mémoire saturé ({memory_usage:.1f}%)")
        
        return recommendations


class SmartCache:
    """Cache intelligent avec fonctionnalités avancées"""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
        self.invalidation_rules: Dict[str, List[str]] = {
            'artist_updated': ['artist:*', 'discovery:*'],
            'track_updated': ['track:*', 'credits:*', 'lyrics:*'],
            'album_updated': ['album:*', 'track:*'],
            'session_completed': ['stats:*', 'session:*']
        }
    
    def cache_result(self, prefix: str, expire_days: Optional[int] = None):
        """Décorateur pour mettre en cache le résultat d'une fonction"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Générer la clé de cache
                cache_key = self.cache._generate_cache_key(prefix, *args, **kwargs)
                
                # Tenter de récupérer du cache
                cached_result = self.cache.get(cache_key)
                if cached_result is not None:
                    return cached_result
                
                # Exécuter la fonction et mettre en cache
                result = func(*args, **kwargs)
                if result is not None:  # Ne pas cacher les résultats None
                    self.cache.set(cache_key, result, expire_days)
                
                return result
            return wrapper
        return decorator
    
    def invalidate_on_event(self, event: str, entity_id: Optional[str] = None):
        """Invalide le cache basé sur un événement"""
        if event in self.invalidation_rules:
            patterns = self.invalidation_rules[event]
            for pattern in patterns:
                if entity_id:
                    pattern = pattern.replace('*', f'*{entity_id}*')
                self._invalidate_pattern(pattern)
    
    def _invalidate_pattern(self, pattern: str):
        """Invalide les entrées de cache correspondant à un pattern"""
        try:
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
                
        except Exception as e:
            print(f"⚠️ Erreur invalidation pattern {pattern}: {e}")
    
    def prefetch_data(self, prefetch_rules: Dict[str, List[str]]):
        """Pré-charge les données selon des règles définies"""
        for event, patterns in prefetch_rules.items():
            try:
                # Logic de pré-chargement basée sur les patterns
                # Implementation dépendante du contexte
                pass
            except Exception as e:
                print(f"⚠️ Erreur pré-chargement pour {event}: {e}")
    
    @lru_cache(maxsize=64)
    def get_cache_strategy(self, data_type: str) -> Dict[str, Any]:
        """Retourne la stratégie de cache optimale pour un type de données"""
        strategies = {
            'artist_info': {'ttl_days': 30, 'priority': 'high'},
            'track_metadata': {'ttl_days': 14, 'priority': 'high'},
            'lyrics': {'ttl_days': 90, 'priority': 'medium'},
            'credits': {'ttl_days': 60, 'priority': 'high'},
            'album_info': {'ttl_days': 45, 'priority': 'medium'},
            'api_response': {'ttl_days': 1, 'priority': 'low'},
            'search_results': {'ttl_days': 7, 'priority': 'low'}
        }
        
        return strategies.get(data_type, {'ttl_days': 7, 'priority': 'low'})


class CacheStats:
    """Statistiques et monitoring avancé du cache"""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
        self._performance_history = []
        self._last_stats_time = datetime.now()
    
    def record_performance_snapshot(self):
        """Enregistre un instantané des performances"""
        try:
            stats = self.cache.get_stats()
            snapshot = {
                'timestamp': datetime.now(),
                'hit_rate': stats['performance']['hit_rate'],
                'total_entries': stats['total_entries'],
                'cache_size_mb': stats['cache_size_mb'],
                'memory_usage': (stats['memory_cache']['entries'] / stats['memory_cache']['max_entries']) * 100
            }
            
            self._performance_history.append(snapshot)
            
            # Garder seulement les 100 derniers snapshots
            if len(self._performance_history) > 100:
                self._performance_history = self._performance_history[-100:]
                
        except Exception as e:
            print(f"⚠️ Erreur enregistrement snapshot: {e}")
    
    def get_performance_trends(self) -> Dict[str, Any]:
        """Analyse les tendances de performance"""
        if len(self._performance_history) < 2:
            return {'insufficient_data': True}
        
        recent = self._performance_history[-10:]  # 10 derniers points
        older = self._performance_history[-20:-10] if len(self._performance_history) >= 20 else []
        
        if not older:
            return {'insufficient_data': True}
        
        # Calculs de tendances
        recent_hit_rate = sum(s['hit_rate'] for s in recent) / len(recent)
        older_hit_rate = sum(s['hit_rate'] for s in older) / len(older)
        
        recent_size = sum(s['cache_size_mb'] for s in recent) / len(recent)
        older_size = sum(s['cache_size_mb'] for s in older) / len(older)
        
        return {
            'hit_rate_trend': recent_hit_rate - older_hit_rate,
            'size_trend_mb': recent_size - older_size,
            'recent_hit_rate': round(recent_hit_rate, 2),
            'size_growth_rate': round(((recent_size - older_size) / older_size) * 100, 2) if older_size > 0 else 0,
            'data_points': len(self._performance_history)
        }
    
    def generate_health_report(self) -> Dict[str, Any]:
        """Génère un rapport de santé complet du cache"""
        try:
            stats = self.get_stats()
            trends = self.get_performance_trends()
            recommendations = self.cache.cleanup_recommendations()
            
            # Évaluation de la santé globale
            health_score = self._calculate_health_score(stats, trends)
            
            return {
                'health_score': health_score,
                'status': self._get_health_status(health_score),
                'current_stats': stats,
                'performance_trends': trends,
                'recommendations': recommendations,
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'error': f"Erreur génération rapport: {e}",
                'generated_at': datetime.now().isoformat()
            }
    
    def _calculate_health_score(self, stats: Dict, trends: Dict) -> int:
        """Calcule un score de santé de 0-100"""
        score = 100
        
        # Pénalités basées sur les stats
        hit_rate = stats['performance']['hit_rate']
        if hit_rate < 70:
            score -= (70 - hit_rate)
        
        # Utilisation de l'espace
        usage_percent = (stats['cache_size_mb'] / stats['max_size_mb']) * 100
        if usage_percent > 90:
            score -= (usage_percent - 90) * 2
        
        # Entrées expirées
        expired_percent = (stats['expired_entries'] / max(stats['total_entries'], 1)) * 100
        if expired_percent > 20:
            score -= (expired_percent - 20)
        
        # Tendances
        if not trends.get('insufficient_data', False):
            if trends['hit_rate_trend'] < -5:  # Dégradation significative
                score -= 10
            if trends['size_growth_rate'] > 50:  # Croissance trop rapide
                score -= 15
        
        return max(0, min(100, int(score)))
    
    def _get_health_status(self, score: int) -> str:
        """Convertit le score en statut"""
        if score >= 90:
            return "EXCELLENT"
        elif score >= 75:
            return "GOOD"
        elif score >= 60:
            return "WARNING"
        elif score >= 40:
            return "POOR"
        else:
            return "CRITICAL"


# Instances globales optimisées
cache_manager = CacheManager()
smart_cache = SmartCache(cache_manager)
cache_stats = CacheStats(cache_manager)