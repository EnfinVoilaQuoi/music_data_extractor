# core/rate_limiter.py - Version optimisée et simplifiée
import time
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, Optional

class RateLimiter:
    """Rate limiter simple et efficace pour les APIs musicales"""
    
    def __init__(self, requests_per_minute: int = 30, requests_per_hour: int = 1800):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        
        # Historique des requêtes par API
        self.request_history: Dict[str, deque] = defaultdict(lambda: deque())
        self.lock = threading.Lock()
        
        # APIs courantes avec leurs limites
        self.api_limits = {
            'genius': {'per_minute': 30, 'per_hour': 1800},
            'spotify': {'per_minute': 100, 'per_hour': 3600}, 
            'discogs': {'per_minute': 60, 'per_hour': 1000},
            'lastfm': {'per_minute': 50, 'per_hour': 2000}
        }
        
        print(f"✅ RateLimiter initialisé ({requests_per_minute}/min, {requests_per_hour}/h)")
    
    def can_make_request(self, api_name: str = 'default') -> bool:
        """Vérifie si une requête peut être faite"""
        with self.lock:
            now = datetime.now()
            history = self.request_history[api_name]
            
            # Nettoyer l'historique ancien
            self._cleanup_history(history, now)
            
            # Récupérer les limites pour cette API
            limits = self.api_limits.get(api_name, {
                'per_minute': self.requests_per_minute,
                'per_hour': self.requests_per_hour
            })
            
            # Vérifier limite par minute
            minute_ago = now - timedelta(minutes=1)
            requests_last_minute = sum(1 for req_time in history if req_time > minute_ago)
            if requests_last_minute >= limits['per_minute']:
                return False
            
            # Vérifier limite par heure
            hour_ago = now - timedelta(hours=1)
            requests_last_hour = sum(1 for req_time in history if req_time > hour_ago)
            if requests_last_hour >= limits['per_hour']:
                return False
            
            return True
    
    def record_request(self, api_name: str = 'default'):
        """Enregistre qu'une requête a été faite"""
        with self.lock:
            now = datetime.now()
            self.request_history[api_name].append(now)
    
    def wait_if_needed(self, api_name: str = 'default') -> float:
        """Attend si nécessaire avant de faire une requête"""
        if self.can_make_request(api_name):
            self.record_request(api_name)
            return 0.0
        
        # Calculer le temps d'attente
        wait_time = self._calculate_wait_time(api_name)
        
        if wait_time > 0:
            print(f"⏳ Rate limit atteint pour {api_name}, attente {wait_time:.1f}s")
            time.sleep(wait_time)
        
        self.record_request(api_name)
        return wait_time
    
    def _cleanup_history(self, history: deque, now: datetime):
        """Nettoie l'historique des requêtes anciennes"""
        cutoff = now - timedelta(hours=1)
        while history and history[0] < cutoff:
            history.popleft()
    
    def _calculate_wait_time(self, api_name: str) -> float:
        """Calcule le temps d'attente nécessaire"""
        with self.lock:
            now = datetime.now()
            history = self.request_history[api_name]
            limits = self.api_limits.get(api_name, {
                'per_minute': self.requests_per_minute,
                'per_hour': self.requests_per_hour
            })
            
            # Vérifier si on doit attendre pour la limite par minute
            minute_ago = now - timedelta(minutes=1)
            recent_requests = [req_time for req_time in history if req_time > minute_ago]
            
            if len(recent_requests) >= limits['per_minute']:
                # Attendre jusqu'à ce que la plus ancienne requête ait plus d'1 minute
                oldest_recent = min(recent_requests)
                wait_until = oldest_recent + timedelta(minutes=1, seconds=1)
                wait_time = (wait_until - now).total_seconds()
                return max(0, wait_time)
            
            return 0.0
    
    def get_stats(self, api_name: str = 'default') -> Dict[str, int]:
        """Retourne les statistiques d'utilisation"""
        with self.lock:
            now = datetime.now()
            history = self.request_history[api_name]
            
            minute_ago = now - timedelta(minutes=1)
            hour_ago = now - timedelta(hours=1)
            
            return {
                'requests_last_minute': sum(1 for req_time in history if req_time > minute_ago),
                'requests_last_hour': sum(1 for req_time in history if req_time > hour_ago),
                'total_requests': len(history)
            }
    
    def reset_stats(self, api_name: Optional[str] = None):
        """Remet à zéro les statistiques"""
        with self.lock:
            if api_name:
                self.request_history[api_name].clear()
            else:
                self.request_history.clear()