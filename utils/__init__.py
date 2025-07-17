# utils/__init__.py - Version optimisée et simplifiée
"""Utilitaires et fonctions helper"""

__all__ = []

# Import direct des fonctions essentielles
try:
    from .text_utils import (
        clean_artist_name,
        normalize_text,
        clean_track_title,
        extract_featuring_artists,
        calculate_similarity
    )
    __all__.extend([
        'clean_artist_name',
        'normalize_text', 
        'clean_track_title',
        'extract_featuring_artists',
        'calculate_similarity'
    ])
    print("✅ Text utils essentiels importés")
except ImportError as e:
    print(f"⚠️ Erreur import text_utils: {e}")

# Import conditionnel d'ExportManager
try:
    from .export_utils import ExportManager
    __all__.append('ExportManager')
    print("✅ ExportManager importé")
except ImportError as e:
    print(f"⚠️ ExportManager non disponible: {e}")

# Fonction helper simplifiée
def get_available_utils():
    """Retourne la liste des utilitaires disponibles"""
    return __all__