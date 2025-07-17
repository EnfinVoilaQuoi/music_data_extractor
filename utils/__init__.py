# utils/__init__.py
"""Utilitaires et fonctions helper"""

__all__ = []

# Import automatique de toutes les fonctions disponibles de text_utils
try:
    import utils.text_utils as text_utils_module
    
    # Récupérer toutes les fonctions publiques
    text_utils_functions = [
        name for name in dir(text_utils_module) 
        if not name.startswith('_') and callable(getattr(text_utils_module, name))
    ]
    
    # Import dynamique des fonctions disponibles
    for func_name in text_utils_functions:
        globals()[func_name] = getattr(text_utils_module, func_name)
        __all__.append(func_name)
    
    print(f"✅ Text utils importées: {text_utils_functions}")
    
except ImportError as e:
    print(f"⚠️ Erreur import text_utils: {e}")

# Imports conditionnels pour les modules optionnels (sans imports relatifs)
try:
    from .export_utils import ExportManager
    __all__.append('ExportManager')
    print("✅ ExportManager importé")
except ImportError as e:
    print(f"⚠️ ExportManager non disponible: {e}")

# Fonction helper pour lister les utilitaires disponibles
def get_available_utils():
    """Retourne la liste des utilitaires disponibles"""
    return __all__