# extractors/api_extractors/__init__.py
"""
Module d'extracteurs API optimisé pour les services musicaux.
Version optimisée avec imports sécurisés, cache intelligent et diagnostics.
"""

import logging
from functools import lru_cache
from typing import List, Dict, Any, Optional, Tuple
import importlib
import sys

__version__ = "1.0.0"
__all__ = []

# Configuration du logger pour ce module
logger = logging.getLogger(__name__)

# Statistiques d'imports
_import_stats = {
    'successful': [],
    'failed': [],
    'total_attempts': 0
}

def _safe_import(module_name: str, class_names: List[str]) -> Tuple[bool, Optional[Exception]]:
    """
    Import sécurisé avec tracking des erreurs.
    
    Args:
        module_name: Nom du module à importer
        class_names: Liste des classes à importer
        
    Returns:
        Tuple (succès, erreur_éventuelle)
    """
    global _import_stats
    _import_stats['total_attempts'] += 1
    
    try:
        module = importlib.import_module(f'.{module_name}', package=__name__)
        
        for class_name in class_names:
            if hasattr(module, class_name):
                globals()[class_name] = getattr(module, class_name)
                __all__.append(class_name)
            else:
                logger.warning(f"⚠️ Classe {class_name} non trouvée dans {module_name}")
        
        _import_stats['successful'].append(module_name)
        logger.debug(f"✅ {module_name} importé avec succès")
        return True, None
        
    except ImportError as e:
        _import_stats['failed'].append({'module': module_name, 'error': str(e)})
        logger.debug(f"⚠️ Échec import {module_name}: {e}")
        return False, e
    except Exception as e:
        _import_stats['failed'].append({'module': module_name, 'error': f"Erreur inattendue: {str(e)}"})
        logger.error(f"❌ Erreur inattendue lors de l'import {module_name}: {e}")
        return False, e

# ===== IMPORTS PRINCIPAUX =====

# 1. Extracteurs API principaux
_safe_import('spotify_extractor', ['SpotifyExtractor'])
_safe_import('lastfm_extractor', ['LastFMExtractor'])
_safe_import('discogs_extractor', ['DiscogsExtractor'])

# 2. Extracteurs API optionnels
_safe_import('musicbrainz_extractor', ['MusicBrainzExtractor'])
_safe_import('deezer_extractor', ['DeezerExtractor'])

# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_available_extractors() -> List[str]:
    """
    Retourne la liste des extracteurs API disponibles avec cache.
    
    Returns:
        Liste des extracteurs disponibles
    """
    return [name for name in __all__ if name.endswith('Extractor')]

@lru_cache(maxsize=1)
def get_import_stats() -> Dict[str, Any]:
    """
    Retourne les statistiques d'import avec cache.
    
    Returns:
        Dictionnaire des statistiques d'import
    """
    return {
        'total_modules_attempted': _import_stats['total_attempts'],
        'successful_imports': len(_import_stats['successful']),
        'failed_imports': len(_import_stats['failed']),
        'success_rate': (len(_import_stats['successful']) / max(_import_stats['total_attempts'], 1)) * 100,
        'available_extractors': get_available_extractors(),
        'successful_modules': _import_stats['successful'],
        'failed_modules': _import_stats['failed']
    }

def create_extractor(extractor_type: str, **kwargs) -> Optional[Any]:
    """
    Factory pour créer un extracteur API avec gestion d'erreurs.
    
    Args:
        extractor_type: Type d'extracteur ('spotify', 'lastfm', 'discogs', etc.)
        **kwargs: Arguments pour le constructeur
        
    Returns:
        Instance de l'extracteur ou None si échec
    """
    # Mapping des types vers les classes
    extractor_mapping = {
        'spotify': 'SpotifyExtractor',
        'spotify_extractor': 'SpotifyExtractor',
        'lastfm': 'LastFMExtractor',
        'lastfm_extractor': 'LastFMExtractor',
        'last_fm': 'LastFMExtractor',
        'discogs': 'DiscogsExtractor',
        'discogs_extractor': 'DiscogsExtractor',
        'musicbrainz': 'MusicBrainzExtractor',
        'musicbrainz_extractor': 'MusicBrainzExtractor',
        'deezer': 'DeezerExtractor',
        'deezer_extractor': 'DeezerExtractor'
    }
    
    class_name = extractor_mapping.get(extractor_type.lower())
    if not class_name:
        logger.error(f"❌ Type d'extracteur API inconnu: {extractor_type}")
        return None
    
    if class_name not in globals():
        logger.error(f"❌ Extracteur {class_name} non disponible")
        return None
    
    try:
        extractor_class = globals()[class_name]
        return extractor_class(**kwargs)
    except Exception as e:
        logger.error(f"❌ Erreur création {class_name}: {e}")
        return None

@lru_cache(maxsize=32)
def get_extractor_capabilities(extractor_type: str) -> Dict[str, Any]:
    """
    Retourne les capacités d'un extracteur API avec cache.
    
    Args:
        extractor_type: Type d'extracteur
        
    Returns:
        Dictionnaire des capacités
    """
    capabilities = {
        'available': False,
        'features': [],
        'data_types': [],
        'rate_limits': {},
        'authentication': {}
    }
    
    try:
        extractor = create_extractor(extractor_type)
        if extractor:
            capabilities['available'] = True
            
            # Détection des méthodes disponibles
            methods = [method for method in dir(extractor) if not method.startswith('_') and callable(getattr(extractor, method))]
            capabilities['features'] = methods
            
            # Extraction des capacités spécifiques si disponibles
            if hasattr(extractor, 'get_supported_data_types'):
                capabilities['data_types'] = extractor.get_supported_data_types()
            
            if hasattr(extractor, 'get_rate_limits'):
                capabilities['rate_limits'] = extractor.get_rate_limits()
            
            if hasattr(extractor, 'get_auth_info'):
                capabilities['authentication'] = extractor.get_auth_info()
                
    except Exception as e:
        logger.debug(f"Erreur évaluation capacités {extractor_type}: {e}")
    
    return capabilities

def run_api_diagnostics() -> Dict[str, Any]:
    """
    Lance des diagnostics complets sur tous les extracteurs API.
    
    Returns:
        Rapport de diagnostic détaillé
    """
    diagnostics = {
        'module_info': {
            'version': __version__,
            'total_classes': len(__all__),
            'available_extractors': get_available_extractors()
        },
        'import_status': get_import_stats(),
        'system_info': {
            'python_version': sys.version,
            'required_packages': _check_required_packages()
        }
    }
    
    # Test de création des extracteurs
    extractor_tests = {}
    all_types = ['spotify', 'lastfm', 'discogs', 'musicbrainz', 'deezer']
    
    for extractor_type in all_types:
        try:
            extractor = create_extractor(extractor_type)
            extractor_tests[extractor_type] = {
                'creation_success': extractor is not None,
                'capabilities': get_extractor_capabilities(extractor_type)
            }
            
            # Test de santé si disponible
            if extractor and hasattr(extractor, 'health_check'):
                extractor_tests[extractor_type]['health_check'] = extractor.health_check()
                
        except Exception as e:
            extractor_tests[extractor_type] = {
                'creation_success': False,
                'error': str(e),
                'capabilities': {}
            }
    
    diagnostics['extractor_tests'] = extractor_tests
    
    return diagnostics

def _check_required_packages() -> Dict[str, bool]:
    """Vérifie la disponibilité des packages requis"""
    packages = {}
    
    # Packages essentiels
    for package in ['requests', 'urllib3']:
        try:
            importlib.import_module(package)
            packages[package] = True
        except ImportError:
            packages[package] = False
    
    # Packages spécifiques aux APIs
    for package in ['spotipy', 'pylast', 'discogs_client']:
        try:
            importlib.import_module(package)
            packages[package] = True
        except ImportError:
            packages[package] = False
    
    return packages

def validate_api_setup() -> Tuple[bool, List[str]]:
    """
    Valide la configuration du module API extractors.
    
    Returns:
        Tuple (configuration_valide, liste_problèmes)
    """
    issues = []
    
    # Vérifier qu'au moins un extracteur principal est disponible
    if not any(extractor in __all__ for extractor in ['SpotifyExtractor', 'LastFMExtractor']):
        issues.append("Aucun extracteur API principal (Spotify/LastFM) disponible")
    
    # Vérifier la cohérence des imports
    if len(get_available_extractors()) == 0:
        issues.append("Aucun extracteur API disponible")
    
    # Vérifier les dépendances critiques
    required_packages = _check_required_packages()
    if not required_packages.get('requests', False):
        issues.append("Module 'requests' manquant (requis pour HTTP)")
    
    return len(issues) == 0, issues

# ===== FONCTIONS DE BATCH ET ENRICHISSEMENT =====

def batch_extract_data(sources: List[Dict[str, str]], extractor_types: List[str], **kwargs) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extrait des données de plusieurs sources avec plusieurs extracteurs.
    
    Args:
        sources: Liste de sources {'type': 'track/album/artist', 'id': '...'}
        extractor_types: Liste des types d'extracteurs à utiliser
        **kwargs: Arguments additionnels pour les extracteurs
        
    Returns:
        Dictionnaire des résultats par extracteur
    """
    results = {}
    
    for extractor_type in extractor_types:
        extractor = create_extractor(extractor_type, **kwargs)
        if not extractor:
            continue
            
        extractor_results = []
        
        for source in sources:
            try:
                source_type = source.get('type', 'track')
                source_id = source.get('id')
                
                if not source_id:
                    continue
                
                # Appel de la méthode appropriée selon le type
                if source_type == 'track' and hasattr(extractor, 'get_track_details'):
                    result = extractor.get_track_details(source_id)
                elif source_type == 'album' and hasattr(extractor, 'get_album_details'):
                    result = extractor.get_album_details(source_id)
                elif source_type == 'artist' and hasattr(extractor, 'get_artist_details'):
                    result = extractor.get_artist_details(source_id)
                else:
                    result = None
                
                if result:
                    result['source'] = source
                    extractor_results.append(result)
                    
            except Exception as e:
                logger.error(f"❌ Erreur extraction {extractor_type} pour {source}: {e}")
                continue
        
        results[extractor_type] = extractor_results
    
    return results

def cross_reference_data(data_sets: Dict[str, List[Dict[str, Any]]], 
                        match_fields: List[str] = ['title', 'artist']) -> List[Dict[str, Any]]:
    """
    Croise les données de plusieurs extracteurs pour enrichir les informations.
    
    Args:
        data_sets: Données par extracteur
        match_fields: Champs utilisés pour matcher les enregistrements
        
    Returns:
        Liste des enregistrements enrichis
    """
    enriched_records = []
    
    # Utiliser le premier dataset comme référence
    reference_extractor = list(data_sets.keys())[0] if data_sets else None
    if not reference_extractor:
        return enriched_records
    
    reference_data = data_sets[reference_extractor]
    
    for ref_record in reference_data:
        enriched_record = {
            'primary_source': reference_extractor,
            'data': {reference_extractor: ref_record},
            'confidence': 1.0
        }
        
        # Chercher des matches dans les autres extracteurs
        for extractor_name, extractor_data in data_sets.items():
            if extractor_name == reference_extractor:
                continue
            
            best_match = None
            best_score = 0.0
            
            for record in extractor_data:
                score = _calculate_match_score(ref_record, record, match_fields)
                if score > best_score:
                    best_score = score
                    best_match = record
            
            if best_match and best_score > 0.7:  # Seuil de confiance
                enriched_record['data'][extractor_name] = best_match
                enriched_record['confidence'] *= best_score
        
        enriched_records.append(enriched_record)
    
    return enriched_records

def _calculate_match_score(record1: Dict[str, Any], record2: Dict[str, Any], 
                          match_fields: List[str]) -> float:
    """Calcule un score de correspondance entre deux enregistrements"""
    from utils.text_utils import calculate_similarity
    
    scores = []
    
    for field in match_fields:
        value1 = str(record1.get(field, '')).lower().strip()
        value2 = str(record2.get(field, '')).lower().strip()
        
        if value1 and value2:
            similarity = calculate_similarity(value1, value2)
            scores.append(similarity)
    
    return sum(scores) / len(scores) if scores else 0.0

# ===== INITIALISATION =====

# Validation automatique au chargement
_setup_valid, _setup_issues = validate_api_setup()

if not _setup_valid:
    logger.warning("⚠️ Problèmes détectés dans la configuration API extractors:")
    for issue in _setup_issues:
        logger.warning(f"  - {issue}")
else:
    logger.info(f"✅ Module API extractors initialisé: {len(get_available_extractors())} extracteurs disponibles")

# Export final
__all__.extend([
    'get_available_extractors',
    'get_import_stats',
    'create_extractor',
    'get_extractor_capabilities',
    'run_api_diagnostics',
    'validate_api_setup',
    'batch_extract_data',
    'cross_reference_data'
])
