# core/cache.py - Version optimisée et simplifiée
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
from pathlib import Path

from config.settings import settings

class CacheManager:
    """Gestionnaire de cache simple et efficace"""
    
    def __init__(self, cache_db_path: Optional[Path] = None):
        self.cache_db_path = cache_db_path or (settings.data_dir / "cache.db")
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Durées de cache par défaut (en heures)
        self.default_durations = {
            'artist_search': 24,      # Recherche d'artiste
            'track_list': 12,         # Liste des morceaux
            'track_details': 48,      # Détails d'un morceau
            'api_response': 6         # Réponses API génériques
        }
        
        self._init_cache_db()
        print(f"✅ CacheManager initialisé (DB: {self.cache_db_path})")
    
    def _init_cache_db(self):
        """Initialise la base de données du cache"""
        with sqlite3.connect(self.cache_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    cache_type TEXT DEFAULT 'general'
                )
            """)
            
            # Index pour améliorer les performances
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_expires 
                ON cache(expires_at)
            """)
    
    def get(self, key: str) -> Optional[Any]:
        """Récupère une valeur du cache"""
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT data FROM cache 
                    WHERE cache_key = ? 
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                """, (key,))
                row = cursor.fetchone()
                
                if row:
                    return json.loads(row['data'])
            return None
        except Exception as e:
            print(f"⚠️ Erreur lecture cache {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, duration_hours: Optional[int] = None, cache_type: str = 'general') -> bool:
        """Stocke une valeur dans le cache"""
        try:
            # Calculer l'expiration
            expires_at = None
            if duration_hours:
                expires_at = datetime.now() + timedelta(hours=duration_hours)
            elif cache_type in self.default_durations:
                expires_at = datetime.now() + timedelta(hours=self.default_durations[cache_type])
            
            with sqlite3.connect(self.cache_db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO cache (cache_key, data, expires_at, cache_type)
                    VALUES (?, ?, ?, ?)
                """, (
                    key,
                    json.dumps(value),
                    expires_at.isoformat() if expires_at else None,
                    cache_type
                ))
            return True
        except Exception as e:
            print(f"⚠️ Erreur écriture cache {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Supprime une entrée du cache"""
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.execute("DELETE FROM cache WHERE cache_key = ?", (key,))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"⚠️ Erreur suppression cache {key}: {e}")
            return False
    
    def clear(self, cache_type: Optional[str] = None) -> int:
        """Vide le cache (optionnellement par type)"""
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                if cache_type:
                    cursor = conn.execute("DELETE FROM cache WHERE cache_type = ?", (cache_type,))
                else:
                    cursor = conn.execute("DELETE FROM cache")
                
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    print(f"🧹 {deleted_count} entrée(s) de cache supprimée(s)")
                
                return deleted_count
        except Exception as e:
            print(f"⚠️ Erreur vidage cache: {e}")
            return 0
    
    def cleanup_expired(self) -> int:
        """Supprime les entrées de cache expirées"""
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM cache 
                    WHERE expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP
                """)
                
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    print(f"🧹 {deleted_count} entrée(s) expirée(s) supprimée(s)")
                
                return deleted_count
        except Exception as e:
            print(f"⚠️ Erreur nettoyage expirations: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du cache"""
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Statistiques générales
                cursor = conn.execute("SELECT COUNT(*) as total FROM cache")
                total_entries = cursor.fetchone()['total']
                
                # Entrées expirées
                cursor = conn.execute("""
                    SELECT COUNT(*) as expired FROM cache 
                    WHERE expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP
                """)
                expired_entries = cursor.fetchone()['expired']
                
                # Répartition par type
                cursor = conn.execute("""
                    SELECT cache_type, COUNT(*) as count 
                    FROM cache 
                    GROUP BY cache_type
                """)
                type_breakdown = {row['cache_type']: row['count'] for row in cursor.fetchall()}
                
                return {
                    'total_entries': total_entries,
                    'expired_entries': expired_entries,
                    'valid_entries': total_entries - expired_entries,
                    'type_breakdown': type_breakdown
                }
        except Exception as e:
            print(f"⚠️ Erreur stats cache: {e}")
            return {}
    
    def cache_artist_search(self, artist_name: str, data: Any) -> bool:
        """Cache spécialisé pour les recherches d'artiste"""
        key = f"artist_search:{artist_name.lower()}"
        return self.set(key, data, cache_type='artist_search')
    
    def get_cached_artist_search(self, artist_name: str) -> Optional[Any]:
        """Récupère une recherche d'artiste en cache"""
        key = f"artist_search:{artist_name.lower()}"
        return self.get(key)
    
    def cache_track_list(self, artist_id: str, tracks: Any) -> bool:
        """Cache spécialisé pour les listes de morceaux"""
        key = f"track_list:{artist_id}"
        return self.set(key, tracks, cache_type='track_list')
    
    def get_cached_track_list(self, artist_id: str) -> Optional[Any]:
        """Récupère une liste de morceaux en cache"""
        key = f"track_list:{artist_id}"
        return self.get(key)

# Instance globale du gestionnaire de cache
_cache_manager = None

def get_cache_manager() -> CacheManager:
    """Récupère l'instance globale du gestionnaire de cache"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager