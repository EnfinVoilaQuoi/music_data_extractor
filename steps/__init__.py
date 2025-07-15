# steps/__init__.py
"""Étapes de traitement du pipeline d'extraction"""

__all__ = []

# Imports conditionnels pour les étapes
try:
    from .step1_discover import DiscoveryStep
    __all__.append('DiscoveryStep')
    print("✅ DiscoveryStep importé")
except ImportError as e:
    print(f"⚠️ Erreur import DiscoveryStep: {e}")

try:
    from .step2_extract import ExtractionStep
    __all__.append('ExtractionStep')
    print("✅ ExtractionStep importé")
except ImportError as e:
    print(f"⚠️ Erreur import ExtractionStep: {e}")

try:
    from .step3_process import ProcessingStep
    __all__.append('ProcessingStep')
    print("✅ ProcessingStep importé")
except ImportError as e:
    print(f"⚠️ Erreur import ProcessingStep: {e}")

try:
    from .step4_export import ExportStep
    __all__.append('ExportStep')
    print("✅ ExportStep importé")
except ImportError as e:
    print(f"⚠️ Erreur import ExportStep: {e}")

# Fonction helper pour lister les étapes disponibles
def get_available_steps():
    """Retourne la liste des étapes disponibles"""
    return __all__