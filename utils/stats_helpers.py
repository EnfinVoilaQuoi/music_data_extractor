# utils/stats_helpers.py
"""
Module d'aide pour la gestion des statistiques dans Music Data Extractor.
Centralise les fonctions de statistiques pour éviter la duplication.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from functools import lru_cache
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


class StatsCollector:
    """Collecteur de statistiques réutilisable"""
    
    def __init__(self, name: str):
        self.name = name
        self.stats = {
            'created_at': datetime.now().isoformat(),
            'name': name,
            'counters': defaultdict(int),
            'timers': defaultdict(list),
            'errors': [],
            'performance': {
                'start_time': datetime.now(),
                'operations': 0,
                'cache_hits': 0,
                'cache_misses': 0
            }
        }
    
    def increment(self, key: str, value: int = 1):
        """Incrémente un compteur"""
        self.stats['counters'][key] += value
        self.stats['performance']['operations'] += 1
    
    def record_time(self, operation: str, duration: float):
        """Enregistre une durée d'opération"""
        self.stats['timers'][operation].append(duration)
    
    def record_error(self, error: str, context: Optional[Dict] = None):
        """Enregistre une erreur"""
        self.stats['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'error': error,
            'context': context or {}
        })
    
    def record_cache_hit(self):
        """Enregistre un cache hit"""
        self.stats['performance']['cache_hits'] += 1
    
    def record_cache_miss(self):
        """Enregistre un cache miss"""
        self.stats['performance']['cache_misses'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques complètes"""
        elapsed = (datetime.now() - self.stats['performance']['start_time']).total_seconds()
        
        return {
            'name': self.name,
            'created_at': self.stats['created_at'],
            'elapsed_seconds': round(elapsed, 2),
            'counters': dict(self.stats['counters']),
            'timers': self._calculate_timer_stats(),
            'errors': {
                'count': len(self.stats['errors']),
                'recent': self.stats['errors'][-10:] if self.stats['errors'] else []
            },
            'performance': {
                'total_operations': self.stats['performance']['operations'],
                'operations_per_second': round(
                    self.stats['performance']['operations'] / max(elapsed, 1), 2
                ),
                'cache_hit_rate': self._calculate_cache_hit_rate()
            }
        }
    
    def _calculate_timer_stats(self) -> Dict[str, Dict[str, float]]:
        """Calcule les statistiques des timers"""
        timer_stats = {}
        
        for operation, times in self.stats['timers'].items():
            if times:
                timer_stats[operation] = {
                    'count': len(times),
                    'total': round(sum(times), 3),
                    'average': round(sum(times) / len(times), 3),
                    'min': round(min(times), 3),
                    'max': round(max(times), 3)
                }
        
        return timer_stats
    
    def _calculate_cache_hit_rate(self) -> float:
        """Calcule le taux de cache hit"""
        hits = self.stats['performance']['cache_hits']
        misses = self.stats['performance']['cache_misses']
        total = hits + misses
        
        if total == 0:
            return 0.0
        
        return round((hits / total) * 100, 2)
    
    def reset(self):
        """Réinitialise les statistiques"""
        self.__init__(self.name)
    
    def merge(self, other: 'StatsCollector'):
        """Fusionne avec d'autres statistiques"""
        for key, value in other.stats['counters'].items():
            self.stats['counters'][key] += value
        
        for operation, times in other.stats['timers'].items():
            self.stats['timers'][operation].extend(times)
        
        self.stats['errors'].extend(other.stats['errors'])
        self.stats['performance']['operations'] += other.stats['performance']['operations']
        self.stats['performance']['cache_hits'] += other.stats['performance']['cache_hits']
        self.stats['performance']['cache_misses'] += other.stats['performance']['cache_misses']


# Instance globale pour les stats générales
_global_stats = StatsCollector('global')


def get_stats(component: Optional[str] = None) -> Dict[str, Any]:
    """
    Fonction générique pour obtenir les statistiques d'un composant.
    
    Args:
        component: Nom du composant (None pour stats globales)
        
    Returns:
        Dictionnaire des statistiques
    """
    if component is None:
        return _global_stats.get_stats()
    
    # Pour un composant spécifique, créer un collecteur temporaire
    collector = StatsCollector(component)
    return collector.get_stats()


def reset_stats(component: Optional[str] = None):
    """
    Réinitialise les statistiques d'un composant.
    
    Args:
        component: Nom du composant (None pour stats globales)
    """
    if component is None:
        _global_stats.reset()
    
    logger.info(f"📊 Stats réinitialisées pour: {component or 'global'}")


def get_performance_stats(start_time: datetime, 
                         operations_count: int,
                         cache_hits: int = 0,
                         cache_misses: int = 0,
                         errors_count: int = 0) -> Dict[str, Any]:
    """
    Calcule les statistiques de performance standardisées.
    
    Args:
        start_time: Heure de début
        operations_count: Nombre d'opérations
        cache_hits: Nombre de cache hits
        cache_misses: Nombre de cache misses
        errors_count: Nombre d'erreurs
        
    Returns:
        Dictionnaire des stats de performance
    """
    elapsed = (datetime.now() - start_time).total_seconds()
    total_cache_ops = cache_hits + cache_misses
    
    return {
        'elapsed_seconds': round(elapsed, 2),
        'operations': {
            'total': operations_count,
            'per_second': round(operations_count / max(elapsed, 1), 2),
            'errors': errors_count,
            'success_rate': round(
                ((operations_count - errors_count) / max(operations_count, 1)) * 100, 2
            )
        },
        'cache': {
            'hits': cache_hits,
            'misses': cache_misses,
            'total': total_cache_ops,
            'hit_rate': round(
                (cache_hits / max(total_cache_ops, 1)) * 100, 2
            ) if total_cache_ops > 0 else 0.0
        },
        'performance_rating': _calculate_performance_rating(
            operations_count / max(elapsed, 1),
            cache_hits / max(total_cache_ops, 1) if total_cache_ops > 0 else 0,
            errors_count / max(operations_count, 1)
        )
    }


def _calculate_performance_rating(ops_per_second: float, 
                                 cache_hit_rate: float,
                                 error_rate: float) -> str:
    """Calcule une note de performance"""
    score = 0
    
    # Opérations par seconde (max 40 points)
    if ops_per_second >= 10:
        score += 40
    elif ops_per_second >= 5:
        score += 30
    elif ops_per_second >= 1:
        score += 20
    else:
        score += 10
    
    # Taux de cache hit (max 40 points)
    score += int(cache_hit_rate * 40)
    
    # Taux d'erreur (max 20 points)
    score += int((1 - error_rate) * 20)
    
    # Conversion en rating
    if score >= 90:
        return "Excellent"
    elif score >= 75:
        return "Bon"
    elif score >= 50:
        return "Moyen"
    else:
        return "Faible"


def aggregate_stats(stats_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Agrège une liste de statistiques.
    
    Args:
        stats_list: Liste de dictionnaires de stats
        
    Returns:
        Stats agrégées
    """
    if not stats_list:
        return {}
    
    aggregated = {
        'total_items': len(stats_list),
        'counters': defaultdict(int),
        'timers': defaultdict(list),
        'errors': [],
        'performance': {
            'total_operations': 0,
            'total_cache_hits': 0,
            'total_cache_misses': 0
        }
    }
    
    for stats in stats_list:
        # Agrégation des compteurs
        if 'counters' in stats:
            for key, value in stats['counters'].items():
                aggregated['counters'][key] += value
        
        # Agrégation des timers
        if 'timers' in stats:
            for operation, times in stats['timers'].items():
                if isinstance(times, list):
                    aggregated['timers'][operation].extend(times)
                elif isinstance(times, dict) and 'total' in times:
                    aggregated['timers'][operation].append(times['total'])
        
        # Agrégation des erreurs
        if 'errors' in stats:
            if isinstance(stats['errors'], dict) and 'recent' in stats['errors']:
                aggregated['errors'].extend(stats['errors']['recent'])
            elif isinstance(stats['errors'], list):
                aggregated['errors'].extend(stats['errors'])
        
        # Agrégation des performances
        if 'performance' in stats:
            perf = stats['performance']
            aggregated['performance']['total_operations'] += perf.get('total_operations', 0)
            
            if 'cache' in perf:
                aggregated['performance']['total_cache_hits'] += perf['cache'].get('hits', 0)
                aggregated['performance']['total_cache_misses'] += perf['cache'].get('misses', 0)
    
    # Calcul des moyennes et ratios
    total_cache_ops = (aggregated['performance']['total_cache_hits'] + 
                      aggregated['performance']['total_cache_misses'])
    
    aggregated['summary'] = {
        'average_operations_per_item': round(
            aggregated['performance']['total_operations'] / max(len(stats_list), 1), 2
        ),
        'overall_cache_hit_rate': round(
            (aggregated['performance']['total_cache_hits'] / max(total_cache_ops, 1)) * 100, 2
        ) if total_cache_ops > 0 else 0.0,
        'total_errors': len(aggregated['errors'])
    }
    
    return dict(aggregated)


def format_stats_for_display(stats: Dict[str, Any], 
                            format_type: str = 'text') -> str:
    """
    Formate les statistiques pour l'affichage.
    
    Args:
        stats: Dictionnaire de stats
        format_type: 'text', 'json', ou 'markdown'
        
    Returns:
        Stats formatées
    """
    if format_type == 'json':
        return json.dumps(stats, indent=2, default=str)
    
    elif format_type == 'markdown':
        lines = [
            "# Statistiques\n",
            f"**Créé le:** {stats.get('created_at', 'N/A')}",
            f"**Durée:** {stats.get('elapsed_seconds', 0)}s\n",
            "## Compteurs"
        ]
        
        for key, value in stats.get('counters', {}).items():
            lines.append(f"- **{key}:** {value}")
        
        if stats.get('performance'):
            perf = stats['performance']
            lines.extend([
                "\n## Performance",
                f"- **Opérations totales:** {perf.get('total_operations', 0)}",
                f"- **Opérations/seconde:** {perf.get('operations_per_second', 0)}",
                f"- **Taux de cache hit:** {perf.get('cache_hit_rate', 0)}%"
            ])
        
        return '\n'.join(lines)
    
    else:  # format_type == 'text'
        lines = [
            f"=== Statistiques {stats.get('name', 'N/A')} ===",
            f"Créé le: {stats.get('created_at', 'N/A')}",
            f"Durée: {stats.get('elapsed_seconds', 0)}s"
        ]
        
        if stats.get('counters'):
            lines.append("\nCompteurs:")
            for key, value in stats['counters'].items():
                lines.append(f"  {key}: {value}")
        
        if stats.get('performance'):
            perf = stats['performance']
            lines.extend([
                "\nPerformance:",
                f"  Opérations totales: {perf.get('total_operations', 0)}",
                f"  Opérations/seconde: {perf.get('operations_per_second', 0)}",
                f"  Taux de cache hit: {perf.get('cache_hit_rate', 0)}%"
            ])
        
        return '\n'.join(lines)


# Export des fonctions principales
__all__ = [
    'StatsCollector',
    'get_stats',
    'reset_stats',
    'get_performance_stats',
    'aggregate_stats',
    'format_stats_for_display'
]
