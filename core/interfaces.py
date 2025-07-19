# core/interfaces.py
"""
Interfaces et protocoles communs pour Music Data Extractor.
Définit les contrats pour les composants réutilisables.
"""

from typing import Protocol, Dict, Any, Optional, List, runtime_checkable
from datetime import datetime
from abc import ABC, abstractmethod


@runtime_checkable
class StatsProvider(Protocol):
    """Interface pour les composants qui fournissent des statistiques"""
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du composant"""
        ...
    
    def reset_stats(self) -> None:
        """Réinitialise les statistiques"""
        ...


@runtime_checkable
class CacheableComponent(Protocol):
    """Interface pour les composants avec cache"""
    
    def clear_cache(self) -> None:
        """Vide le cache du composant"""
        ...
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du cache"""
        ...
    
    def cache_hit_rate(self) -> float:
        """Retourne le taux de cache hit"""
        ...


@runtime_checkable
class HealthCheckable(Protocol):
    """Interface pour les composants avec health check"""
    
    def health_check(self) -> Dict[str, Any]:
        """
        Vérifie l'état de santé du composant.
        
        Returns:
            Dict avec 'status' (healthy/unhealthy), 'details', etc.
        """
        ...


@runtime_checkable
class PerformanceTracker(Protocol):
    """Interface pour le tracking de performance"""
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Retourne les stats de performance"""
        ...
    
    def reset_performance_stats(self) -> None:
        """Réinitialise les stats de performance"""
        ...


class BaseExtractor(ABC):
    """Classe de base pour tous les extracteurs"""
    
    def __init__(self):
        self.stats = {
            'created_at': datetime.now(),
            'requests_made': 0,
            'requests_successful': 0,
            'requests_failed': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': []
        }
    
    @abstractmethod
    def extract_data(self, **kwargs) -> Dict[str, Any]:
        """Méthode principale d'extraction"""
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Implémentation standard des stats"""
        elapsed = (datetime.now() - self.stats['created_at']).total_seconds()
        total_requests = self.stats['requests_made']
        
        return {
            'created_at': self.stats['created_at'].isoformat(),
            'elapsed_seconds': round(elapsed, 2),
            'requests': {
                'total': total_requests,
                'successful': self.stats['requests_successful'],
                'failed': self.stats['requests_failed'],
                'success_rate': round(
                    (self.stats['requests_successful'] / max(total_requests, 1)) * 100, 2
                )
            },
            'cache': {
                'hits': self.stats['cache_hits'],
                'misses': self.stats['cache_misses'],
                'hit_rate': self.cache_hit_rate()
            },
            'errors': {
                'count': len(self.stats['errors']),
                'recent': self.stats['errors'][-5:]
            }
        }
    
    def reset_stats(self) -> None:
        """Réinitialise les statistiques"""
        self.stats = {
            'created_at': datetime.now(),
            'requests_made': 0,
            'requests_successful': 0,
            'requests_failed': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': []
        }
    
    def cache_hit_rate(self) -> float:
        """Calcule le taux de cache hit"""
        total_cache_ops = self.stats['cache_hits'] + self.stats['cache_misses']
        if total_cache_ops == 0:
            return 0.0
        return round((self.stats['cache_hits'] / total_cache_ops) * 100, 2)
    
    def record_request(self, success: bool, error: Optional[str] = None):
        """Enregistre une requête"""
        self.stats['requests_made'] += 1
        
        if success:
            self.stats['requests_successful'] += 1
        else:
            self.stats['requests_failed'] += 1
            if error:
                self.stats['errors'].append({
                    'timestamp': datetime.now().isoformat(),
                    'error': error
                })
    
    def record_cache_hit(self):
        """Enregistre un cache hit"""
        self.stats['cache_hits'] += 1
    
    def record_cache_miss(self):
        """Enregistre un cache miss"""
        self.stats['cache_misses'] += 1


class BaseProcessor(ABC):
    """Classe de base pour tous les processeurs"""
    
    def __init__(self):
        self.stats = {
            'created_at': datetime.now(),
            'items_processed': 0,
            'items_successful': 0,
            'items_failed': 0,
            'processing_times': []
        }
    
    @abstractmethod
    def process(self, data: Any) -> Any:
        """Méthode principale de traitement"""
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du processeur"""
        elapsed = (datetime.now() - self.stats['created_at']).total_seconds()
        total_items = self.stats['items_processed']
        
        # Calcul des temps de traitement
        processing_times = self.stats['processing_times']
        avg_time = sum(processing_times) / len(processing_times) if processing_times else 0
        
        return {
            'created_at': self.stats['created_at'].isoformat(),
            'elapsed_seconds': round(elapsed, 2),
            'items': {
                'total': total_items,
                'successful': self.stats['items_successful'],
                'failed': self.stats['items_failed'],
                'success_rate': round(
                    (self.stats['items_successful'] / max(total_items, 1)) * 100, 2
                )
            },
            'performance': {
                'items_per_second': round(total_items / max(elapsed, 1), 2),
                'average_processing_time': round(avg_time, 3),
                'min_processing_time': round(min(processing_times), 3) if processing_times else 0,
                'max_processing_time': round(max(processing_times), 3) if processing_times else 0
            }
        }
    
    def reset_stats(self) -> None:
        """Réinitialise les statistiques"""
        self.stats = {
            'created_at': datetime.now(),
            'items_processed': 0,
            'items_successful