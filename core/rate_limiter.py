# core/rate_limiter.py - Version corrigée
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable, List
from functools import wraps
import threading

from config.settings import settings

class RateLimiter:
    """Gestionnaire de limitations de taux pour les APIs"""
    
    def __init__(self, requests_per_period: int = 60, period_seconds: int = 60):
        """
        CORRECTION: Constructeur avec paramètres par défaut pour compatibilité
        avec base_extractor.py
        """
        # Charger les limites depuis la config ou utiliser les paramètres
        self.api_limits = self._load_rate_limits()
        
        # Si des paramètres sont fournis, créer une limite personnalisée
        if requests_per_period != 60 or period_seconds != 60:
            self.custom_limit = {
                'requests_per_minute': requests_per_period if period_seconds == 60 else int(requests_per_period * 60 / period_seconds),
                'requests_per_hour': requests_per_period * 3600 // period_seconds
            }
        else:
            self.custom_limit = None
        
        self.request_history: Dict[str, deque] = defaultdict(lambda: deque())
        self.lock = threading.Lock()
    
    def _load_rate_limits(self) -> Dict[str, Dict[str, int]]:
        """Charge les limites de taux depuis la configuration"""
        return settings.get('rate_limits', {
            'genius': {
                'requests_per_minute': 30,
                'requests_per_hour': 1000
            },
            'spotify': {
                'requests_per_minute': 100,
                'requests_per_hour': 3000
            },
            'discogs': {
                'requests_per_minute': 60,
                'requests_per_hour': 1000
            },
            'lastfm': {
                'requests_per_minute': 300,
                'requests_per_hour': 5000
            },
            'web_scraping': {
                'requests_per_minute': 20,
                'requests_per_hour': 200
            }
        })
    
    def can_make_request(self, api_name: str = 'default') -> bool:
        """Vérifie si une requête peut être faite maintenant"""
        # Utiliser la limite personnalisée si définie, sinon la limite de l'API
        if self.custom_limit and api_name == 'default':
            limits = self.custom_limit
        else:
            limits = self.api_limits.get(api_name, self.custom_limit or {})
        
        if not limits:
            return True
        
        with self.lock:
            now = datetime.now()
            history = self.request_history[api_name]
            
            # Nettoyer l'historique ancien
            self._cleanup_history(history, now)
            
            # Vérifier les limites par minute
            if 'requests_per_minute' in limits:
                minute_ago = now - timedelta(minutes=1)
                requests_last_minute = sum(1 for req_time in history if req_time > minute_ago)
                if requests_last_minute >= limits['requests_per_minute']:
                    return False
            
            # Vérifier les limites par heure
            if 'requests_per_hour' in limits:
                hour_ago = now - timedelta(hours=1)
                requests_last_hour = sum(1 for req_time in history if req_time > hour_ago)
                if requests_last_hour >= limits['requests_per_hour']:
                    return False
            
            return True
    
    def wait_if_needed(self, api_name: str = 'default') -> float:
        """Attend si nécessaire avant de faire une requête. Retourne le temps d'attente."""
        # Utiliser la limite personnalisée si définie
        if self.custom_limit and api_name == 'default':
            limits = self.custom_limit
        else:
            limits = self.api_limits.get(api_name, self.custom_limit or {})
        
        if not limits:
            return 0.0
        
        start_time = time.time()
        
        while not self.can_make_request(api_name):
            sleep_time = self._calculate_sleep_time(api_name)
            print(f"⏳ Rate limit atteint pour {api_name}, attente de {sleep_time:.1f}s...")
            time.sleep(sleep_time)
        
        return time.time() - start_time
    
    def record_request(self, api_name: str = 'default'):
        """Enregistre qu'une requête a été faite"""
        with self.lock:
            self.request_history[api_name].append(datetime.now())
    
    def _cleanup_history(self, history: deque, now: datetime):
        """Nettoie l'historique des requêtes anciennes"""
        # Garder seulement les requêtes de la dernière heure
        cutoff = now - timedelta(hours=1)
        while history and history[0] < cutoff:
            history.popleft()
    
    def _calculate_sleep_time(self, api_name: str) -> float:
        """Calcule le temps d'attente optimal"""
        if self.custom_limit and api_name == 'default':
            limits = self.custom_limit
        else:
            limits = self.api_limits.get(api_name, self.custom_limit or {})
        
        if not limits:
            return 0.0
        
        history = self.request_history[api_name]
        now = datetime.now()
        
        # Temps d'attente basé sur la limite par minute (plus restrictive généralement)
        if 'requests_per_minute' in limits:
            minute_ago = now - timedelta(minutes=1)
            requests_last_minute = [req_time for req_time in history if req_time > minute_ago]
            
            if len(requests_last_minute) >= limits['requests_per_minute']:
                # Attendre jusqu'à ce que la plus ancienne requête sorte de la fenêtre
                oldest_request = min(requests_last_minute)
                next_available = oldest_request + timedelta(minutes=1)
                sleep_seconds = (next_available - now).total_seconds()
                return max(0.0, sleep_seconds + 0.1)  # +0.1s de marge
        
        # Temps d'attente par défaut
        return 1.0
    
    def get_status(self, api_name: str = 'default') -> Dict[str, any]:
        """Récupère le statut actuel des limites pour une API"""
        if self.custom_limit and api_name == 'default':
            limits = self.custom_limit
        else:
            limits = self.api_limits.get(api_name, self.custom_limit or {})
        
        if not limits:
            return {'status': 'no_limits'}
        
        with self.lock:
            now = datetime.now()
            history = self.request_history[api_name]
            
            self._cleanup_history(history, now)
            
            # Compter les requêtes récentes
            minute_ago = now - timedelta(minutes=1)
            hour_ago = now - timedelta(hours=1)
            
            requests_last_minute = sum(1 for req_time in history if req_time > minute_ago)
            requests_last_hour = sum(1 for req_time in history if req_time > hour_ago)
            
            return {
                'api_name': api_name,
                'requests_last_minute': requests_last_minute,
                'requests_last_hour': requests_last_hour,
                'limit_per_minute': limits.get('requests_per_minute'),
                'limit_per_hour': limits.get('requests_per_hour'),
                'can_make_request': self.can_make_request(api_name),
                'estimated_wait_time': self._calculate_sleep_time(api_name) if not self.can_make_request(api_name) else 0
            }
    
    def rate_limited_call(self, api_name: str):
        """Décorateur pour appliquer automatiquement le rate limiting"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Attendre si nécessaire
                wait_time = self.wait_if_needed(api_name)
                if wait_time > 0:
                    print(f"⏰ Attente de {wait_time:.1f}s pour {api_name}")
                
                try:
                    # Faire l'appel
                    result = func(*args, **kwargs)
                    # Enregistrer la requête réussie
                    self.record_request(api_name)
                    return result
                except Exception as e:
                    # Enregistrer quand même la tentative pour éviter les spam en cas d'erreur
                    self.record_request(api_name)
                    raise
            
            return wrapper
        return decorator

class AdaptiveRateLimiter(RateLimiter):
    """Rate limiter adaptatif qui ajuste automatiquement les limites"""
    
    def __init__(self, requests_per_period: int = 60, period_seconds: int = 60):
        super().__init__(requests_per_period, period_seconds)
        self.error_history: Dict[str, deque] = defaultdict(lambda: deque())
        self.success_rates: Dict[str, float] = defaultdict(lambda: 1.0)
        self.adaptive_multipliers: Dict[str, float] = defaultdict(lambda: 1.0)
    
    def record_error(self, api_name: str, error_type: str = 'rate_limit'):
        """Enregistre une erreur liée au rate limiting"""
        with self.lock:
            self.error_history[api_name].append({
                'timestamp': datetime.now(),
                'error_type': error_type
            })
            
            # Ajuster le multiplicateur adaptatif
            if error_type == 'rate_limit':
                # Réduire la vitesse en cas d'erreur de rate limit
                self.adaptive_multipliers[api_name] *= 0.8
                self.adaptive_multipliers[api_name] = max(0.1, self.adaptive_multipliers[api_name])
                print(f"🔻 Réduction du taux pour {api_name}: x{self.adaptive_multipliers[api_name]:.2f}")
    
    def record_success(self, api_name: str):
        """Enregistre un succès"""
        with self.lock:
            # Augmenter légèrement la vitesse en cas de succès
            self.adaptive_multipliers[api_name] *= 1.02
            self.adaptive_multipliers[api_name] = min(1.0, self.adaptive_multipliers[api_name])
    
    def _get_adaptive_limit(self, api_name: str, limit_type: str) -> int:
        """Calcule la limite adaptative"""
        if self.custom_limit and api_name == 'default':
            limits = self.custom_limit
        else:
            limits = self.api_limits.get(api_name, self.custom_limit or {})
        
        base_limit = limits.get(limit_type, 0)
        if base_limit == 0:
            return 0
        
        multiplier = self.adaptive_multipliers[api_name]
        adaptive_limit = int(base_limit * multiplier)
        return max(1, adaptive_limit)  # Au moins 1 requête
    
    def can_make_request(self, api_name: str = 'default') -> bool:
        """Version adaptative de can_make_request"""
        if self.custom_limit and api_name == 'default':
            limits = self.custom_limit
        else:
            limits = self.api_limits.get(api_name, self.custom_limit or {})
        
        if not limits:
            return True
        
        with self.lock:
            now = datetime.now()
            history = self.request_history[api_name]
            
            # Nettoyer l'historique
            self._cleanup_history(history, now)
            self._cleanup_error_history(api_name, now)
            
            # Utiliser les limites adaptatives
            minute_limit = self._get_adaptive_limit(api_name, 'requests_per_minute')
            hour_limit = self._get_adaptive_limit(api_name, 'requests_per_hour')
            
            # Vérifier les limites
            if minute_limit > 0:
                minute_ago = now - timedelta(minutes=1)
                requests_last_minute = sum(1 for req_time in history if req_time > minute_ago)
                if requests_last_minute >= minute_limit:
                    return False
            
            if hour_limit > 0:
                hour_ago = now - timedelta(hours=1)
                requests_last_hour = sum(1 for req_time in history if req_time > hour_ago)
                if requests_last_hour >= hour_limit:
                    return False
            
            return True
    
    def _cleanup_error_history(self, api_name: str, now: datetime):
        """Nettoie l'historique des erreurs"""
        history = self.error_history[api_name]
        cutoff = now - timedelta(hours=1)
        while history and history[0]['timestamp'] < cutoff:
            history.popleft()

# Instance globale du rate limiter
rate_limiter = AdaptiveRateLimiter()