# utils/cache_helpers.py
"""
Module d'aide pour la gestion du cache dans Music Data Extractor.
Centralise les fonctions de cache pour éviter la duplication.
"""

import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, Union, List
from functools import wraps, lru_cache
import pickle

logger = logging.getLogger(__name__)


def generate_cache_key(*args, prefix: str = "", **kwargs) -> str:
    """
    Génère une clé de cache unique basée sur les arguments.
    
    Args:
        *args: Arguments positionnels
        prefix: Préfixe pour la clé
        **kwargs: Arguments nommés
        
    Returns:
        Clé de cache unique
    """
    # Construire une représentation stable des arguments
    key_parts = [prefix] if prefix else []
    
    # Ajouter les args
    for arg in args:
        if isinstance(arg, (str, int, float, bool)):
            key_parts.append(str(arg))
        elif isinstance(arg, (list, tuple)):
            key_parts.append(json.dumps(sorted(arg), sort_keys=True))
        elif isinstance(arg, dict):
            key_parts.append(json.dumps(arg, sort_keys=True))
        else:
            # Pour les objets complexes, utiliser leur repr ou type
            key_parts.append(f"{type(arg).__name__}_{id(arg)}")
    
    # Ajouter les kwargs triés
    if kwargs:
        sorted_kwargs = sorted(kwargs.items())
        key_parts.append(json.dumps(dict(sorted_kwargs), sort_keys=True))
    
    # Créer un hash de la clé complète
    key_string = "|".join(key_parts)
    key_hash = hashlib.md5(key_string.encode()).hexdigest()
    
    # Retourner avec préfixe lisible si fourni
    if prefix:
        return f"{prefix}:{key_hash}"
    
    return key_hash


def clear_cache(cache_manager=None, pattern: Optional[str] = None) -> int:
    """
    Vide le cache selon un pattern optionnel.
    
    Args:
        cache_manager: Instance du gestionnaire de cache
        pattern: Pattern pour filtrer les clés à supprimer
        
    Returns:
        Nombre d'entrées supprimées
    """
    if cache_manager is None:
        # Importer ici pour éviter les imports circulaires
        from core.cache import CacheManager
        cache_manager = CacheManager()
    
    if pattern:
        # Utiliser la méthode de suppression par pattern si disponible
        if hasattr(cache_manager, '_invalidate_pattern'):
            return cache_manager._invalidate_pattern(pattern)
        else:
            # Fallback: parcourir toutes les clés
            deleted = 0
            if hasattr(cache_manager, 'get_cache_keys'):
                for key in cache_manager.get_cache_keys():
                    if pattern in key:
                        cache_manager.delete(key)
                        deleted += 1
            return deleted
    else:
        # Vider tout le cache
        if hasattr(cache_manager, 'clear_all'):
            cache_manager.clear_all()
            return -1  # Nombre inconnu
        else:
            cache_manager.clear_expired()
            return -1


def cache_hit_rate(hits: int, misses: int) -> float:
    """
    Calcule le taux de cache hit.
    
    Args:
        hits: Nombre de cache hits
        misses: Nombre de cache misses
        
    Returns:
        Taux de hit en pourcentage
    """
    total = hits + misses
    if total == 0:
        return 0.0
    
    return round((hits / total) * 100, 2)


def get_cache_info(cache_manager=None) -> Dict[str, Any]:
    """
    Récupère les informations complètes sur le cache.
    
    Args:
        cache_manager: Instance du gestionnaire de cache
        
    Returns:
        Informations détaillées sur le cache
    """
    if cache_manager is None:
        from core.cache import CacheManager
        cache_manager = CacheManager()
    
    # Récupérer les stats de base
    stats = cache_manager.get_stats() if hasattr(cache_manager, 'get_stats') else {}
    
    # Ajouter des informations supplémentaires
    info = {
        'stats': stats,
        'health': {
            'hit_rate': stats.get('hit_rate', 0.0),
            'total_operations': stats.get('hits', 0) + stats.get('misses', 0),
            'memory_usage': stats.get('memory_usage_mb', 0),
            'entries_count': stats.get('entries', 0)
        },
        'recommendations': []
    }
    
    # Générer des recommandations
    hit_rate = info['health']['hit_rate']
    if hit_rate < 50.0 and info['health']['total_operations'] > 100:
        info['recommendations'].append(
            f"Taux de cache hit faible ({hit_rate}%). "
            "Considérer l'augmentation de la taille du cache ou l'optimisation des clés."
        )
    
    if info['health']['memory_usage'] > 500:  # Plus de 500 MB
        info['recommendations'].append(
            f"Utilisation mémoire élevée ({info['health']['memory_usage']} MB). "
            "Considérer le nettoyage des entrées anciennes."
        )
    
    return info


def smart_cache_decorator(prefix: str, 
                         expire_hours: int = 24,
                         cache_none: bool = False,
                         key_generator: Optional[Callable] = None):
    """
    Décorateur de cache intelligent avec options avancées.
    
    Args:
        prefix: Préfixe pour les clés de cache
        expire_hours: Durée d'expiration en heures
        cache_none: Si True, met en cache les résultats None
        key_generator: Fonction personnalisée pour générer les clés
        
    Returns:
        Décorateur
    """
    def decorator(func):
        # Import local pour éviter les dépendances circulaires
        from core.cache import CacheManager
        cache_manager = CacheManager()
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Générer la clé de cache
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                # Exclure 'self' des args pour les méthodes
                cache_args = args[1:] if args and hasattr(args[0], '__dict__') else args
                cache_key = generate_cache_key(*cache_args, prefix=f"{prefix}:{func.__name__}", **kwargs)
            
            # Vérifier le cache
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit pour {cache_key}")
                # Enregistrer le hit si la méthode existe
                if hasattr(args[0], '_record_cache_hit') and args:
                    args[0]._record_cache_hit()
                return cached_result
            
            # Pas en cache, exécuter la fonction
            logger.debug(f"Cache miss pour {cache_key}")
            if hasattr(args[0], '_record_cache_miss') and args:
                args[0]._record_cache_miss()
            
            try:
                result = func(*args, **kwargs)
                
                # Mettre en cache si le résultat n'est pas None ou si cache_none est True
                if result is not None or cache_none:
                    cache_manager.set(
                        cache_key, 
                        result, 
                        expire_days=expire_hours / 24
                    )
                
                return result
                
            except Exception as e:
                logger.error(f"Erreur dans {func.__name__}: {e}")
                raise
        
        # Ajouter des méthodes utiles au wrapper
        wrapper.clear_cache = lambda: clear_cache(cache_manager, prefix)
        wrapper.cache_info = lambda: get_cache_info(cache_manager)
        
        return wrapper
    
    return decorator


def batch_cache_operations(cache_manager=None):
    """
    Context manager pour les opérations de cache en batch.
    
    Usage:
        with batch_cache_operations() as batch:
            batch.set('key1', 'value1')
            batch.set('key2', 'value2')
    """
    class BatchCacheContext:
        def __init__(self, manager):
            self.manager = manager
            self.operations = []
        
        def set(self, key: str, value: Any, expire_days: float = 7):
            self.operations.append(('set', key, value, expire_days))
        
        def delete(self, key: str):
            self.operations.append(('delete', key))
        
        def __enter__(self):
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            # Exécuter toutes les opérations
            for op in self.operations:
                if op[0] == 'set':
                    self.manager.set(op[1], op[2], op[3])
                elif op[0] == 'delete':
                    self.manager.delete(op[1])
    
    if cache_manager is None:
        from core.cache import CacheManager
        cache_manager = CacheManager()
    
    return BatchCacheContext(cache_manager)


def cache_warmup(keys_data: List[Tuple[str, Callable, tuple]], 
                cache_manager=None) -> Dict[str, Any]:
    """
    Précharge le cache avec des données.
    
    Args:
        keys_data: Liste de tuples (key, function, args)
        cache_manager: Instance du gestionnaire de cache
        
    Returns:
        Statistiques du warmup
    """
    if cache_manager is None:
        from core.cache import CacheManager
        cache_manager = CacheManager()
    
    stats = {
        'total': len(keys_data),
        'loaded': 0,
        'errors': 0,
        'duration': 0
    }
    
    start_time = datetime.now()
    
    for key, func, args in keys_data:
        try:
            # Vérifier si déjà en cache
            if cache_manager.get(key) is None:
                # Générer la valeur
                value = func(*args)
                # Mettre en cache
                cache_manager.set(key, value)
                stats['loaded'] += 1
        except Exception as e:
            logger.error(f"Erreur warmup pour {key}: {e}")
            stats['errors'] += 1
    
    stats['duration'] = (datetime.now() - start_time).total_seconds()
    
    logger.info(
        f"Cache warmup terminé: {stats['loaded']}/{stats['total']} "
        f"entrées chargées en {stats['duration']:.2f}s"
    )
    
    return stats


# Export des fonctions principales
__all__ = [
    'generate_cache_key',
    'clear_cache',
    'cache_hit_rate',
    'get_cache_info',
    'smart_cache_decorator',
    'batch_cache_operations',
    'cache_warmup'
]
