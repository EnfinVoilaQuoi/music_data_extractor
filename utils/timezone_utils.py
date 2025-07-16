# utils/timezone_utils.py - Gestion des fuseaux horaires
from datetime import datetime, timezone, timedelta
from typing import Optional
import pytz

# Fuseau horaire français
FRANCE_TZ = pytz.timezone('Europe/Paris')

def now_france() -> datetime:
    """Retourne l'heure actuelle en fuseau horaire français"""
    return datetime.now(FRANCE_TZ)

def now_utc() -> datetime:
    """Retourne l'heure actuelle en UTC"""
    return datetime.now(timezone.utc)

def to_france_timezone(dt: Optional[datetime]) -> Optional[datetime]:
    """Convertit une datetime vers le fuseau horaire français"""
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        # Si pas de timezone, on assume UTC
        dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.astimezone(FRANCE_TZ)

def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convertit une datetime vers UTC"""
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        # Si pas de timezone, on assume le fuseau français
        dt = FRANCE_TZ.localize(dt)
    
    return dt.astimezone(timezone.utc)

def format_france_time(dt: Optional[datetime], format_str: str = "%d/%m/%Y %H:%M:%S") -> str:
    """Formate une datetime en heure française"""
    if dt is None:
        return "N/A"
    
    france_dt = to_france_timezone(dt)
    return france_dt.strftime(format_str)

def parse_with_timezone(date_string: str, timezone_aware: bool = True) -> datetime:
    """Parse une date string et retourne avec ou sans timezone"""
    try:
        # Essayer format ISO
        dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        
        if timezone_aware and dt.tzinfo is None:
            # Si pas de timezone et on en veut une, utiliser France
            dt = FRANCE_TZ.localize(dt)
        elif not timezone_aware and dt.tzinfo is not None:
            # Si timezone présente et on n'en veut pas, la retirer
            dt = dt.replace(tzinfo=None)
            
        return dt
        
    except Exception:
        # Fallback: datetime naive actuel
        if timezone_aware:
            return now_france()
        else:
            return datetime.now()

# Constantes utiles
SECONDS_IN_HOUR = 3600
SECONDS_IN_DAY = 86400
SECONDS_IN_WEEK = 604800