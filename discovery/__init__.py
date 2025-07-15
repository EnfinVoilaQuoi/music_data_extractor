# discovery/__init__.py
"""Modules de découverte de morceaux depuis diverses sources"""

__all__ = []

# Import de GeniusDiscovery (principal)
try:
    from .genius_discovery import GeniusDiscovery, DiscoveryResult
    __all__.extend(['GeniusDiscovery', 'DiscoveryResult'])
    print("✅ GeniusDiscovery importé")
except ImportError as e:
    print(f"⚠️ Erreur import GeniusDiscovery: {e}")

# Imports conditionnels pour les modules optionnels
try:
    from .spotify_discovery import SpotifyDiscovery
    __all__.append('SpotifyDiscovery')
    print("✅ SpotifyDiscovery importé")
except ImportError:
    pass

try:
    from .album_resolver import AlbumResolver
    __all__.append('AlbumResolver')
    print("✅ AlbumResolver importé")
except ImportError:
    pass

# Fonction helper
def get_available_discoverers():
    """Retourne la liste des découvreurs disponibles"""
    return __all__