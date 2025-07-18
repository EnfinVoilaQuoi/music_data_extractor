# extractors/data_enrichers/__init__.py
"""
Module d'enrichissement de données optimisé pour les métadonnées musicales.
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

# 1. Enrichisseurs de données principaux
_safe_import('metadata_enricher', ['MetadataEnricher'])
_safe_import('audio_analyzer', ['AudioAnalyzer'])

# 2. Enrichisseurs spécialisés optionnels
_safe_import('genre_classifier', ['GenreClassifier'])
_safe_import('similarity_analyzer', ['SimilarityAnalyzer'])
_safe_import('trend_analyzer', ['TrendAnalyzer'])

# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_available_enrichers() -> List[str]:
    """
    Retourne la liste des enrichisseurs disponibles avec cache.
    
    Returns:
        Liste des enrichisseurs disponibles
    """
    return [name for name in __all__ if any(suffix in name for suffix in ['Enricher', 'Analyzer', 'Classifier'])]

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
        'available_enrichers': get_available_enrichers(),
        'successful_modules': _import_stats['successful'],
        'failed_modules': _import_stats['failed']
    }

def create_enricher(enricher_type: str, **kwargs) -> Optional[Any]:
    """
    Factory pour créer un enrichisseur avec gestion d'erreurs.
    
    Args:
        enricher_type: Type d'enrichisseur ('metadata', 'audio', 'genre', etc.)
        **kwargs: Arguments pour le constructeur
        
    Returns:
        Instance de l'enrichisseur ou None si échec
    """
    # Mapping des types vers les classes
    enricher_mapping = {
        'metadata': 'MetadataEnricher',
        'metadata_enricher': 'MetadataEnricher',
        'audio': 'AudioAnalyzer',
        'audio_analyzer': 'AudioAnalyzer',
        'genre': 'GenreClassifier',
        'genre_classifier': 'GenreClassifier',
        'similarity': 'SimilarityAnalyzer',
        'similarity_analyzer': 'SimilarityAnalyzer',
        'trend': 'TrendAnalyzer',
        'trend_analyzer': 'TrendAnalyzer'
    }
    
    class_name = enricher_mapping.get(enricher_type.lower())
    if not class_name:
        logger.error(f"❌ Type d'enrichisseur inconnu: {enricher_type}")
        return None
    
    if class_name not in globals():
        logger.error(f"❌ Enrichisseur {class_name} non disponible")
        return None
    
    try:
        enricher_class = globals()[class_name]
        return enricher_class(**kwargs)
    except Exception as e:
        logger.error(f"❌ Erreur création {class_name}: {e}")
        return None

@lru_cache(maxsize=32)
def get_enricher_capabilities(enricher_type: str) -> Dict[str, Any]:
    """
    Retourne les capacités d'un enrichisseur avec cache.
    
    Args:
        enricher_type: Type d'enrichisseur
        
    Returns:
        Dictionnaire des capacités
    """
    capabilities = {
        'available': False,
        'features': [],
        'input_types': [],
        'output_formats': [],
        'enrichment_types': []
    }
    
    try:
        enricher = create_enricher(enricher_type)
        if enricher:
            capabilities['available'] = True
            
            # Détection des méthodes disponibles
            methods = [method for method in dir(enricher) if not method.startswith('_') and callable(getattr(enricher, method))]
            capabilities['features'] = methods
            
            # Extraction des capacités spécifiques si disponibles
            if hasattr(enricher, 'get_supported_inputs'):
                capabilities['input_types'] = enricher.get_supported_inputs()
            
            if hasattr(enricher, 'get_output_formats'):
                capabilities['output_formats'] = enricher.get_output_formats()
            
            if hasattr(enricher, 'get_enrichment_types'):
                capabilities['enrichment_types'] = enricher.get_enrichment_types()
                
    except Exception as e:
        logger.debug(f"Erreur évaluation capacités {enricher_type}: {e}")
    
    return capabilities

def run_enrichment_diagnostics() -> Dict[str, Any]:
    """
    Lance des diagnostics complets sur tous les enrichisseurs.
    
    Returns:
        Rapport de diagnostic détaillé
    """
    diagnostics = {
        'module_info': {
            'version': __version__,
            'total_classes': len(__all__),
            'available_enrichers': get_available_enrichers()
        },
        'import_status': get_import_stats(),
        'system_info': {
            'python_version': sys.version,
            'required_packages': _check_required_packages()
        }
    }
    
    # Test de création des enrichisseurs
    enricher_tests = {}
    all_types = ['metadata', 'audio', 'genre', 'similarity', 'trend']
    
    for enricher_type in all_types:
        try:
            enricher = create_enricher(enricher_type)
            enricher_tests[enricher_type] = {
                'creation_success': enricher is not None,
                'capabilities': get_enricher_capabilities(enricher_type)
            }
            
            # Test de santé si disponible
            if enricher and hasattr(enricher, 'health_check'):
                enricher_tests[enricher_type]['health_check'] = enricher.health_check()
                
        except Exception as e:
            enricher_tests[enricher_type] = {
                'creation_success': False,
                'error': str(e),
                'capabilities': {}
            }
    
    diagnostics['enricher_tests'] = enricher_tests
    
    return diagnostics

def _check_required_packages() -> Dict[str, bool]:
    """Vérifie la disponibilité des packages requis"""
    packages = {}
    
    # Packages essentiels
    for package in ['numpy', 'pandas']:
        try:
            importlib.import_module(package)
            packages[package] = True
        except ImportError:
            packages[package] = False
    
    # Packages pour analyse audio
    for package in ['librosa', 'soundfile', 'scipy']:
        try:
            importlib.import_module(package)
            packages[package] = True
        except ImportError:
            packages[package] = False
    
    # Packages pour ML
    for package in ['sklearn', 'tensorflow', 'torch']:
        try:
            importlib.import_module(package)
            packages[package] = True
        except ImportError:
            packages[package] = False
    
    return packages

def validate_enrichment_setup() -> Tuple[bool, List[str]]:
    """
    Valide la configuration du module data enrichers.
    
    Returns:
        Tuple (configuration_valide, liste_problèmes)
    """
    issues = []
    
    # Vérifier qu'au moins un enrichisseur principal est disponible
    if not any(enricher in __all__ for enricher in ['MetadataEnricher', 'AudioAnalyzer']):
        issues.append("Aucun enrichisseur principal (Metadata/Audio) disponible")
    
    # Vérifier la cohérence des imports
    if len(get_available_enrichers()) == 0:
        issues.append("Aucun enrichisseur de données disponible")
    
    # Vérifier les dépendances importantes (pas critiques)
    required_packages = _check_required_packages()
    if not required_packages.get('numpy', False):
        logger.warning("⚠️ NumPy non disponible - analyses numériques limitées")
    
    return len(issues) == 0, issues

# ===== FONCTIONS D'ENRICHISSEMENT BATCH =====

def batch_enrich_data(data_items: List[Dict[str, Any]], enricher_types: List[str], **kwargs) -> Dict[str, List[Dict[str, Any]]]:
    """
    Enrichit une liste d'éléments de données avec plusieurs enrichisseurs.
    
    Args:
        data_items: Liste d'éléments à enrichir
        enricher_types: Liste des types d'enrichisseurs à utiliser
        **kwargs: Arguments additionnels pour les enrichisseurs
        
    Returns:
        Dictionnaire des résultats par enrichisseur
    """
    results = {}
    
    for enricher_type in enricher_types:
        enricher = create_enricher(enricher_type, **kwargs)
        if not enricher:
            continue
            
        enricher_results = []
        
        for data_item in data_items:
            try:
                # Appel de la méthode appropriée selon le type d'enrichisseur
                if enricher_type in ['metadata', 'metadata_enricher'] and hasattr(enricher, 'enrich_metadata'):
                    result = enricher.enrich_metadata(data_item)
                elif enricher_type in ['audio', 'audio_analyzer'] and hasattr(enricher, 'analyze_audio'):
                    result = enricher.analyze_audio(data_item)
                elif hasattr(enricher, 'enrich_data'):
                    result = enricher.enrich_data(data_item)
                else:
                    result = None
                
                if result:
                    result['original_data'] = data_item
                    result['enricher_type'] = enricher_type
                    enricher_results.append(result)
                    
            except Exception as e:
                logger.error(f"❌ Erreur enrichissement {enricher_type} pour item: {e}")
                continue
        
        results[enricher_type] = enricher_results
    
    return results

def merge_enrichment_results(enrichment_results: Dict[str, List[Dict[str, Any]]], 
                           merge_strategy: str = 'union') -> List[Dict[str, Any]]:
    """
    Fusionne les résultats d'enrichissement de plusieurs enrichisseurs.
    
    Args:
        enrichment_results: Résultats par enrichisseur
        merge_strategy: Stratégie de fusion ('union', 'intersection', 'weighted')
        
    Returns:
        Liste des éléments enrichis fusionnés
    """
    if not enrichment_results:
        return []
    
    # Utiliser le premier enrichisseur comme référence
    reference_enricher = list(enrichment_results.keys())[0]
    reference_data = enrichment_results[reference_enricher]
    
    merged_results = []
    
    for ref_item in reference_data:
        merged_item = {
            'original_data': ref_item.get('original_data', {}),
            'enrichments': {
                reference_enricher: ref_item
            },
            'confidence_scores': {
                reference_enricher: ref_item.get('confidence', 1.0)
            },
            'merge_strategy': merge_strategy
        }
        
        # Chercher des correspondances dans les autres enrichisseurs
        for enricher_name, enricher_data in enrichment_results.items():
            if enricher_name == reference_enricher:
                continue
            
            # Trouver l'élément correspondant (basé sur l'ID ou similarité)
            matching_item = _find_matching_item(ref_item, enricher_data)
            if matching_item:
                merged_item['enrichments'][enricher_name] = matching_item
                merged_item['confidence_scores'][enricher_name] = matching_item.get('confidence', 1.0)
        
        # Calculer le score de confiance global
        confidence_values = list(merged_item['confidence_scores'].values())
        if merge_strategy == 'weighted':
            merged_item['overall_confidence'] = sum(confidence_values) / len(confidence_values)
        elif merge_strategy == 'intersection':
            merged_item['overall_confidence'] = min(confidence_values)
        else:  # union
            merged_item['overall_confidence'] = max(confidence_values)
        
        merged_results.append(merged_item)
    
    return merged_results

def _find_matching_item(reference_item: Dict[str, Any], candidate_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Trouve l'élément correspondant dans une liste de candidats"""
    ref_original = reference_item.get('original_data', {})
    ref_id = ref_original.get('id') or ref_original.get('track_id') or ref_original.get('title', '')
    
    for candidate in candidate_items:
        cand_original = candidate.get('original_data', {})
        cand_id = cand_original.get('id') or cand_original.get('track_id') or cand_original.get('title', '')
        
        # Correspondance exacte par ID
        if ref_id and cand_id and ref_id == cand_id:
            return candidate
        
        # Correspondance par similarité de titre (fallback)
        if ref_id and cand_id:
            try:
                from utils.text_utils import calculate_similarity
                similarity = calculate_similarity(str(ref_id).lower(), str(cand_id).lower())
                if similarity > 0.8:
                    return candidate
            except ImportError:
                pass
    
    return None

def analyze_enrichment_quality(enrichment_results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Analyse la qualité des résultats d'enrichissement.
    
    Args:
        enrichment_results: Résultats d'enrichissement
        
    Returns:
        Analyse de qualité
    """
    quality_analysis = {
        'overall_score': 0.0,
        'enricher_scores': {},
        'success_rates': {},
        'coverage_analysis': {},
        'recommendations': []
    }
    
    total_score = 0.0
    enricher_count = 0
    
    for enricher_type, results in enrichment_results.items():
        if not results:
            continue
        
        # Calculer le taux de succès
        successful_results = [r for r in results if r.get('success', True)]
        success_rate = len(successful_results) / len(results) if results else 0
        
        # Calculer la couverture des enrichissements
        coverage_scores = []
        for result in successful_results:
            # Analyser la complétude des enrichissements
            enriched_fields = result.get('enriched_fields', [])
            original_fields = result.get('original_data', {}).keys()
            
            if original_fields:
                coverage = len(enriched_fields) / len(original_fields)
                coverage_scores.append(coverage)
        
        avg_coverage = sum(coverage_scores) / len(coverage_scores) if coverage_scores else 0
        
        # Score de qualité basé sur confiance moyenne
        confidence_scores = [r.get('confidence', 0) for r in successful_results if 'confidence' in r]
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        enricher_score = (success_rate + avg_coverage + avg_confidence) / 3
        
        quality_analysis['enricher_scores'][enricher_type] = enricher_score
        quality_analysis['success_rates'][enricher_type] = success_rate
        quality_analysis['coverage_analysis'][enricher_type] = avg_coverage
        
        total_score += enricher_score
        enricher_count += 1
        
        # Recommandations basées sur les performances
        if success_rate < 0.8:
            quality_analysis['recommendations'].append(
                f"Taux de succès faible pour {enricher_type} ({success_rate:.1%}). Vérifier la qualité des données d'entrée."
            )
        
        if avg_coverage < 0.5:
            quality_analysis['recommendations'].append(
                f"Couverture faible pour {enricher_type} ({avg_coverage:.1%}). Considérer des sources de données additionnelles."
            )
    
    quality_analysis['overall_score'] = total_score / enricher_count if enricher_count > 0 else 0
    
    return quality_analysis

def generate_enrichment_report(enrichment_results: Dict[str, List[Dict[str, Any]]], 
                             output_format: str = 'dict') -> Union[Dict[str, Any], str]:
    """
    Génère un rapport complet des résultats d'enrichissement.
    
    Args:
        enrichment_results: Résultats d'enrichissement
        output_format: Format de sortie ('dict', 'markdown', 'html')
        
    Returns:
        Rapport formaté
    """
    from datetime import datetime
    
    quality_analysis = analyze_enrichment_quality(enrichment_results)
    
    report_data = {
        'generation_info': {
            'generated_at': datetime.now().isoformat(),
            'report_version': '1.0.0',
            'total_enrichers_used': len(enrichment_results),
            'total_items_processed': sum(len(results) for results in enrichment_results.values())
        },
        'quality_analysis': quality_analysis,
        'detailed_results': enrichment_results,
        'summary_statistics': _calculate_enrichment_statistics(enrichment_results)
    }
    
    if output_format == 'dict':
        return report_data
    elif output_format == 'markdown':
        return _format_enrichment_report_markdown(report_data)
    elif output_format == 'html':
        return _format_enrichment_report_html(report_data)
    else:
        return report_data

def _calculate_enrichment_statistics(enrichment_results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Calcule les statistiques d'enrichissement"""
    stats = {
        'total_enrichments_applied': 0,
        'average_confidence': 0.0,
        'enricher_distribution': {},
        'field_enrichment_frequency': {}
    }
    
    all_confidences = []
    
    for enricher_type, results in enrichment_results.items():
        stats['enricher_distribution'][enricher_type] = len(results)
        
        for result in results:
            stats['total_enrichments_applied'] += 1
            
            confidence = result.get('confidence', 0)
            if confidence > 0:
                all_confidences.append(confidence)
            
            # Compter les champs enrichis
            enriched_fields = result.get('enriched_fields', [])
            for field in enriched_fields:
                stats['field_enrichment_frequency'][field] = stats['field_enrichment_frequency'].get(field, 0) + 1
    
    stats['average_confidence'] = sum(all_confidences) / len(all_confidences) if all_confidences else 0
    
    return stats

def _format_enrichment_report_markdown(report_data: Dict[str, Any]) -> str:
    """Formate le rapport d'enrichissement en Markdown"""
    md_content = []
    
    # En-tête
    md_content.append("# Rapport d'Enrichissement de Données")
    md_content.append(f"**Généré le:** {report_data['generation_info']['generated_at']}")
    md_content.append("")
    
    # Résumé
    gen_info = report_data['generation_info']
    md_content.append("## Résumé")
    md_content.append(f"- **Enrichisseurs utilisés:** {gen_info['total_enrichers_used']}")
    md_content.append(f"- **Éléments traités:** {gen_info['total_items_processed']}")
    md_content.append("")
    
    # Analyse de qualité
    quality = report_data['quality_analysis']
    md_content.append("## Analyse de Qualité")
    md_content.append(f"**Score global:** {quality['overall_score']:.2f}")
    md_content.append("")
    
    md_content.append("### Scores par enrichisseur")
    for enricher, score in quality['enricher_scores'].items():
        md_content.append(f"- **{enricher}:** {score:.2f}")
    md_content.append("")
    
    # Statistiques
    stats = report_data['summary_statistics']
    md_content.append("## Statistiques")
    md_content.append(f"- **Total enrichissements:** {stats['total_enrichments_applied']}")
    md_content.append(f"- **Confiance moyenne:** {stats['average_confidence']:.2f}")
    md_content.append("")
    
    return "\n".join(md_content)

def _format_enrichment_report_html(report_data: Dict[str, Any]) -> str:
    """Formate le rapport d'enrichissement en HTML"""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Rapport d'Enrichissement de Données</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .header { background: #f0f8ff; padding: 20px; border-radius: 5px; }
            .section { margin: 20px 0; }
            .metric { display: inline-block; margin: 10px; padding: 10px; background: #e8f8e8; border-radius: 3px; }
            .score { font-weight: bold; color: #2c5aa0; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Rapport d'Enrichissement de Données</h1>
            <p>Généré le: {generated_at}</p>
        </div>
        
        <div class="section">
            <h2>Résumé</h2>
            <div class="metric">Enrichisseurs: <span class="score">{enrichers}</span></div>
            <div class="metric">Éléments traités: <span class="score">{items}</span></div>
            <div class="metric">Score global: <span class="score">{overall_score:.2f}</span></div>
        </div>
        
    </body>
    </html>
    """
    
    return html_template.format(
        generated_at=report_data['generation_info']['generated_at'],
        enrichers=report_data['generation_info']['total_enrichers_used'],
        items=report_data['generation_info']['total_items_processed'],
        overall_score=report_data['quality_analysis']['overall_score']
    )

# ===== PIPELINE D'ENRICHISSEMENT =====

def create_enrichment_pipeline(enricher_configs: List[Dict[str, Any]], 
                             cache_results: bool = True) -> 'EnrichmentPipeline':
    """
    Crée un pipeline d'enrichissement avec plusieurs étapes.
    
    Args:
        enricher_configs: Liste des configurations d'enrichisseurs
        cache_results: Si True, met en cache les résultats intermédiaires
        
    Returns:
        Pipeline d'enrichissement configuré
    """
    return EnrichmentPipeline(enricher_configs, cache_results)

class EnrichmentPipeline:
    """Pipeline d'enrichissement de données avec étapes configurable"""
    
    def __init__(self, enricher_configs: List[Dict[str, Any]], cache_results: bool = True):
        self.enricher_configs = enricher_configs
        self.cache_results = cache_results
        self.enrichers = []
        self.pipeline_stats = {
            'items_processed': 0,
            'total_enrichments': 0,
            'processing_time': 0.0,
            'cache_hits': 0
        }
        
        # Initialiser les enrichisseurs
        self._initialize_enrichers()
    
    def _initialize_enrichers(self):
        """Initialise les enrichisseurs du pipeline"""
        for config in self.enricher_configs:
            enricher_type = config.get('type')
            enricher_kwargs = config.get('kwargs', {})
            
            enricher = create_enricher(enricher_type, **enricher_kwargs)
            if enricher:
                self.enrichers.append({
                    'enricher': enricher,
                    'config': config,
                    'enabled': config.get('enabled', True)
                })
    
    def process(self, data_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Traite une liste d'éléments à travers le pipeline d'enrichissement.
        
        Args:
            data_items: Liste des éléments à enrichir
            
        Returns:
            Liste des éléments enrichis
        """
        import time
        
        start_time = time.time()
        enriched_items = data_items.copy()
        
        for enricher_info in self.enrichers:
            if not enricher_info['enabled']:
                continue
            
            enricher = enricher_info['enricher']
            config = enricher_info['config']
            
            try:
                # Traitement avec l'enrichisseur actuel
                step_results = []
                
                for item in enriched_items:
                    try:
                        # Appliquer l'enrichisseur selon sa méthode principale
                        if hasattr(enricher, 'enrich_data'):
                            enriched_item = enricher.enrich_data(item)
                        elif hasattr(enricher, 'enrich_metadata'):
                            enriched_item = enricher.enrich_metadata(item)
                        elif hasattr(enricher, 'analyze_audio'):
                            enriched_item = enricher.analyze_audio(item)
                        else:
                            enriched_item = item  # Pas d'enrichissement possible
                        
                        if enriched_item:
                            step_results.append(enriched_item)
                            self.pipeline_stats['total_enrichments'] += 1
                        else:
                            step_results.append(item)  # Garder l'original si échec
                            
                    except Exception as e:
                        logger.debug(f"Erreur enrichissement item avec {config['type']}: {e}")
                        step_results.append(item)  # Garder l'original si erreur
                
                enriched_items = step_results
                
            except Exception as e:
                logger.error(f"❌ Erreur dans le pipeline avec {config['type']}: {e}")
                continue
        
        self.pipeline_stats['items_processed'] += len(data_items)
        self.pipeline_stats['processing_time'] += time.time() - start_time
        
        return enriched_items
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du pipeline"""
        return self.pipeline_stats.copy()

# ===== INITIALISATION =====

# Validation automatique au chargement
_setup_valid, _setup_issues = validate_enrichment_setup()

if not _setup_valid:
    logger.warning("⚠️ Problèmes détectés dans la configuration data enrichers:")
    for issue in _setup_issues:
        logger.warning(f"  - {issue}")
else:
    logger.info(f"✅ Module data enrichers initialisé: {len(get_available_enrichers())} enrichisseurs disponibles")

# Export final
__all__.extend([
    'get_available_enrichers',
    'get_import_stats',
    'create_enricher',
    'get_enricher_capabilities',
    'run_enrichment_diagnostics',
    'validate_enrichment_setup',
    'batch_enrich_data',
    'merge_enrichment_results',
    'analyze_enrichment_quality',
    'generate_enrichment_report',
    'create_enrichment_pipeline',
    'EnrichmentPipeline'
])