# Alias pour compatibilité avec les imports existants
try:
    from models.schemas import *
except ImportError:
    # Si models.schemas n'existe pas, créer des classes vides
    pass