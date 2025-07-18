# extractors/text_processors/__init__.py
"""
Module de traitement de texte optimisé pour l'analyse des données musicales.
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

# 1. Processeurs de texte principaux
_safe_import('lyrics_processor', ['LyricsProcessor'])
_safe_import('credit_parser', ['CreditParser'])

# 2. Processeurs de texte optionnels
_safe_import('metadata_normalizer', ['MetadataNormalizer'])
_safe_import('text_classifier', ['TextClassifier'])

# ===== FONCTIONS UTILITAIRES =====

@lru_cache(maxsize=1)
def get_available_processors() -> List[str]:
    """
    Retourne la liste des processeurs de texte disponibles avec cache.
    
    Returns:
        Liste des processeurs disponibles
    """
    return [name for name in __all__ if any(suffix in name for suffix in ['Processor', 'Parser', 'Normalizer', 'Classifier'])]

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
        'available_processors': get_available_processors(),
        'successful_modules': _import_stats['successful'],
        'failed_modules': _import_stats['failed']
    }

def create_processor(processor_type: str, **kwargs) -> Optional[Any]:
    """
    Factory pour créer un processeur de texte avec gestion d'erreurs.
    
    Args:
        processor_type: Type de processeur ('lyrics', 'credit', 'metadata', etc.)
        **kwargs: Arguments pour le constructeur
        
    Returns:
        Instance du processeur ou None si échec
    """
    # Mapping des types vers les classes
    processor_mapping = {
        'lyrics': 'LyricsProcessor',
        'lyrics_processor': 'LyricsProcessor',
        'credit': 'CreditParser',
        'credit_parser': 'CreditParser',
        'credits': 'CreditParser',
        'metadata': 'MetadataNormalizer',
        'metadata_normalizer': 'MetadataNormalizer',
        'normalizer': 'MetadataNormalizer',
        'classifier': 'TextClassifier',
        'text_classifier': 'TextClassifier'
    }
    
    class_name = processor_mapping.get(processor_type.lower())
    if not class_name:
        logger.error(f"❌ Type de processeur inconnu: {processor_type}")
        return None
    
    if class_name not in globals():
        logger.error(f"❌ Processeur {class_name} non disponible")
        return None
    
    try:
        processor_class = globals()[class_name]
        return processor_class(**kwargs)
    except Exception as e:
        logger.error(f"❌ Erreur création {class_name}: {e}")
        return None

@lru_cache(maxsize=32)
def get_processor_capabilities(processor_type: str) -> Dict[str, Any]:
    """
    Retourne les capacités d'un processeur de texte avec cache.
    
    Args:
        processor_type: Type de processeur
        
    Returns:
        Dictionnaire des capacités
    """
    capabilities = {
        'available': False,
        'features': [],
        'input_types': [],
        'output_formats': [],
        'languages_supported': []
    }
    
    try:
        processor = create_processor(processor_type)
        if processor:
            capabilities['available'] = True
            
            # Détection des méthodes disponibles
            methods = [method for method in dir(processor) if not method.startswith('_') and callable(getattr(processor, method))]
            capabilities['features'] = methods
            
            # Extraction des capacités spécifiques si disponibles
            if hasattr(processor, 'get_supported_inputs'):
                capabilities['input_types'] = processor.get_supported_inputs()
            
            if hasattr(processor, 'get_output_formats'):
                capabilities['output_formats'] = processor.get_output_formats()
            
            if hasattr(processor, 'get_supported_languages'):
                capabilities['languages_supported'] = processor.get_supported_languages()
                
    except Exception as e:
        logger.debug(f"Erreur évaluation capacités {processor_type}: {e}")
    
    return capabilities

def run_text_diagnostics() -> Dict[str, Any]:
    """
    Lance des diagnostics complets sur tous les processeurs de texte.
    
    Returns:
        Rapport de diagnostic détaillé
    """
    diagnostics = {
        'module_info': {
            'version': __version__,
            'total_classes': len(__all__),
            'available_processors': get_available_processors()
        },
        'import_status': get_import_stats(),
        'system_info': {
            'python_version': sys.version,
            'required_packages': _check_required_packages()
        }
    }
    
    # Test de création des processeurs
    processor_tests = {}
    all_types = ['lyrics', 'credit', 'metadata', 'classifier']
    
    for processor_type in all_types:
        try:
            processor = create_processor(processor_type)
            processor_tests[processor_type] = {
                'creation_success': processor is not None,
                'capabilities': get_processor_capabilities(processor_type)
            }
            
            # Test de santé si disponible
            if processor and hasattr(processor, 'health_check'):
                processor_tests[processor_type]['health_check'] = processor.health_check()
                
        except Exception as e:
            processor_tests[processor_type] = {
                'creation_success': False,
                'error': str(e),
                'capabilities': {}
            }
    
    diagnostics['processor_tests'] = processor_tests
    
    return diagnostics

def _check_required_packages() -> Dict[str, bool]:
    """Vérifie la disponibilité des packages requis"""
    packages = {}
    
    # Packages essentiels
    for package in ['re', 'collections', 'datetime']:
        try:
            importlib.import_module(package)
            packages[package] = True
        except ImportError:
            packages[package] = False
    
    # Packages optionnels pour NLP
    for package in ['nltk', 'spacy', 'textblob']:
        try:
            importlib.import_module(package)
            packages[package] = True
        except ImportError:
            packages[package] = False
    
    return packages

def validate_text_setup() -> Tuple[bool, List[str]]:
    """
    Valide la configuration du module text processors.
    
    Returns:
        Tuple (configuration_valide, liste_problèmes)
    """
    issues = []
    
    # Vérifier qu'au moins un processeur principal est disponible
    if not any(processor in __all__ for processor in ['LyricsProcessor', 'CreditParser']):
        issues.append("Aucun processeur principal (Lyrics/Credit) disponible")
    
    # Vérifier la cohérence des imports
    if len(get_available_processors()) == 0:
        issues.append("Aucun processeur de texte disponible")
    
    return len(issues) == 0, issues

# ===== FONCTIONS DE TRAITEMENT BATCH =====

def batch_process_texts(texts: List[Dict[str, Any]], processor_types: List[str], **kwargs) -> Dict[str, List[Dict[str, Any]]]:
    """
    Traite une liste de textes avec plusieurs processeurs.
    
    Args:
        texts: Liste de textes avec métadonnées {'content': '...', 'type': '...', 'metadata': {...}}
        processor_types: Liste des types de processeurs à utiliser
        **kwargs: Arguments additionnels pour les processeurs
        
    Returns:
        Dictionnaire des résultats par processeur
    """
    results = {}
    
    for processor_type in processor_types:
        processor = create_processor(processor_type, **kwargs)
        if not processor:
            continue
            
        processor_results = []
        
        for text_data in texts:
            try:
                content = text_data.get('content', '')
                text_type = text_data.get('type', 'unknown')
                metadata = text_data.get('metadata', {})
                
                if not content:
                    continue
                
                # Appel de la méthode appropriée selon le type de processeur
                if processor_type in ['lyrics', 'lyrics_processor'] and hasattr(processor, 'process_lyrics'):
                    result = processor.process_lyrics(content, metadata)
                elif processor_type in ['credit', 'credit_parser'] and hasattr(processor, 'parse_credits'):
                    result = processor.parse_credits(content, metadata)
                elif hasattr(processor, 'process_text'):
                    result = processor.process_text(content, metadata)
                else:
                    result = None
                
                if result:
                    result['original_data'] = text_data
                    result['processor_type'] = processor_type
                    processor_results.append(result)
                    
            except Exception as e:
                logger.error(f"❌ Erreur traitement {processor_type} pour texte: {e}")
                continue
        
        results[processor_type] = processor_results
    
    return results

def analyze_text_quality(text_results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Analyse la qualité des résultats de traitement de texte.
    
    Args:
        text_results: Résultats des processeurs de texte
        
    Returns:
        Analyse de qualité
    """
    quality_analysis = {
        'overall_score': 0.0,
        'processor_scores': {},
        'success_rates': {},
        'recommendations': []
    }
    
    total_score = 0.0
    processor_count = 0
    
    for processor_type, results in text_results.items():
        if not results:
            continue
        
        # Calculer le score moyen pour ce processeur
        successful_results = [r for r in results if r.get('success', False)]
        success_rate = len(successful_results) / len(results) if results else 0
        
        # Score de qualité basé sur la confiance moyenne
        quality_scores = [r.get('quality_score', 0) for r in successful_results if 'quality_score' in r]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        processor_score = (success_rate + avg_quality) / 2
        
        quality_analysis['processor_scores'][processor_type] = processor_score
        quality_analysis['success_rates'][processor_type] = success_rate
        
        total_score += processor_score
        processor_count += 1
        
        # Recommandations basées sur les performances
        if success_rate < 0.7:
            quality_analysis['recommendations'].append(
                f"Taux de succès faible pour {processor_type} ({success_rate:.1%}). Vérifier la qualité des données d'entrée."
            )
        
        if avg_quality < 0.6:
            quality_analysis['recommendations'].append(
                f"Qualité moyenne faible pour {processor_type} ({avg_quality:.2f}). Envisager un pré-traitement des données."
            )
    
    quality_analysis['overall_score'] = total_score / processor_count if processor_count > 0 else 0
    
    return quality_analysis

def extract_key_insights(text_results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Extrait les insights clés des résultats de traitement de texte.
    
    Args:
        text_results: Résultats des processeurs de texte
        
    Returns:
        Insights extraits
    """
    insights = {
        'lyrics_insights': {},
        'credit_insights': {},
        'common_themes': [],
        'artist_patterns': {},
        'collaboration_networks': {}
    }
    
    # Analyse des résultats de paroles
    lyrics_results = text_results.get('lyrics', []) + text_results.get('lyrics_processor', [])
    if lyrics_results:
        insights['lyrics_insights'] = _analyze_lyrics_insights(lyrics_results)
    
    # Analyse des résultats de crédits
    credit_results = text_results.get('credit', []) + text_results.get('credit_parser', [])
    if credit_results:
        insights['credit_insights'] = _analyze_credit_insights(credit_results)
    
    # Analyse croisée
    if lyrics_results and credit_results:
        insights['cross_analysis'] = _perform_cross_analysis(lyrics_results, credit_results)
    
    return insights

def _analyze_lyrics_insights(lyrics_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyse les insights des paroles"""
    insights = {
        'total_tracks_analyzed': len(lyrics_results),
        'language_distribution': {},
        'theme_frequency': {},
        'explicit_content_rate': 0.0,
        'collaboration_rate': 0.0,
        'average_vocabulary_richness': 0.0
    }
    
    try:
        successful_results = [r for r in lyrics_results if r.get('success', False)]
        
        if not successful_results:
            return insights
        
        # Distribution des langues
        languages = {}
        themes_counter = {}
        explicit_count = 0
        collaboration_count = 0
        vocab_richness_scores = []
        
        for result in successful_results:
            data = result.get('data', {}) if isinstance(result.get('data'), dict) else {}
            
            # Langue
            language_info = data.get('language', {})
            primary_lang = language_info.get('primary_language', 'unknown')
            languages[primary_lang] = languages.get(primary_lang, 0) + 1
            
            # Thèmes
            themes = data.get('themes', {}).get('detected_themes', {})
            for theme, count in themes.items():
                themes_counter[theme] = themes_counter.get(theme, 0) + count
            
            # Contenu explicite
            explicit_info = data.get('explicit_content', {})
            if explicit_info.get('is_explicit', False):
                explicit_count += 1
            
            # Collaborations
            featuring_info = data.get('featuring', {})
            if featuring_info.get('collaboration_detected', False):
                collaboration_count += 1
            
            # Richesse vocabulaire
            vocab_info = data.get('vocabulary', {})
            richness = vocab_info.get('vocabulary_richness', 0)
            if richness > 0:
                vocab_richness_scores.append(richness)
        
        insights.update({
            'language_distribution': languages,
            'theme_frequency': dict(sorted(themes_counter.items(), key=lambda x: x[1], reverse=True)[:10]),
            'explicit_content_rate': explicit_count / len(successful_results),
            'collaboration_rate': collaboration_count / len(successful_results),
            'average_vocabulary_richness': sum(vocab_richness_scores) / len(vocab_richness_scores) if vocab_richness_scores else 0
        })
        
    except Exception as e:
        logger.debug(f"Erreur analyse insights paroles: {e}")
    
    return insights

def _analyze_credit_insights(credit_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyse les insights des crédits"""
    insights = {
        'total_credits_parsed': 0,
        'role_distribution': {},
        'collaboration_patterns': {},
        'most_frequent_collaborators': [],
        'production_teams': [],
        'average_credits_per_track': 0.0
    }
    
    try:
        successful_results = [r for r in credit_results if r.get('success', False)]
        
        if not successful_results:
            return insights
        
        all_credits = []
        role_counter = {}
        collaborator_counter = {}
        
        for result in successful_results:
            credits = result.get('credits', [])
            all_credits.extend(credits)
            
            for credit in credits:
                # Comptage des rôles
                role = credit.get('normalized_role', credit.get('role', 'Unknown'))
                role_counter[role] = role_counter.get(role, 0) + 1
                
                # Comptage des collaborateurs
                names = credit.get('names', [])
                for name in names:
                    collaborator_counter[name] = collaborator_counter.get(name, 0) + 1
        
        insights.update({
            'total_credits_parsed': len(all_credits),
            'role_distribution': dict(sorted(role_counter.items(), key=lambda x: x[1], reverse=True)[:15]),
            'most_frequent_collaborators': sorted(collaborator_counter.items(), key=lambda x: x[1], reverse=True)[:20],
            'average_credits_per_track': len(all_credits) / len(successful_results) if successful_results else 0
        })
        
    except Exception as e:
        logger.debug(f"Erreur analyse insights crédits: {e}")
    
    return insights

def _perform_cross_analysis(lyrics_results: List[Dict[str, Any]], credit_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Effectue une analyse croisée entre paroles et crédits"""
    cross_analysis = {
        'theme_producer_correlation': {},
        'language_collaboration_patterns': {},
        'explicit_content_production_style': {}
    }
    
    try:
        # Analyser les corrélations entre thèmes des paroles et types de production
        successful_lyrics = [r for r in lyrics_results if r.get('success', False)]
        successful_credits = [r for r in credit_results if r.get('success', False)]
        
        # Cette analyse pourrait être étendue selon les besoins spécifiques
        logger.debug("Analyse croisée paroles/crédits effectuée")
        
    except Exception as e:
        logger.debug(f"Erreur analyse croisée: {e}")
    
    return cross_analysis

def generate_processing_report(text_results: Dict[str, List[Dict[str, Any]]], 
                             output_format: str = 'dict') -> Union[Dict[str, Any], str]:
    """
    Génère un rapport complet des résultats de traitement de texte.
    
    Args:
        text_results: Résultats des processeurs
        output_format: Format de sortie ('dict', 'markdown', 'html')
        
    Returns:
        Rapport formaté
    """
    # Collecte des données pour le rapport
    quality_analysis = analyze_text_quality(text_results)
    key_insights = extract_key_insights(text_results)
    
    report_data = {
        'generation_info': {
            'generated_at': datetime.now().isoformat(),
            'report_version': '1.0.0',
            'total_processors_used': len(text_results),
            'total_texts_processed': sum(len(results) for results in text_results.values())
        },
        'quality_analysis': quality_analysis,
        'key_insights': key_insights,
        'detailed_results': text_results
    }
    
    if output_format == 'dict':
        return report_data
    elif output_format == 'markdown':
        return _format_report_markdown(report_data)
    elif output_format == 'html':
        return _format_report_html(report_data)
    else:
        return report_data

def _format_report_markdown(report_data: Dict[str, Any]) -> str:
    """Formate le rapport en Markdown"""
    md_content = []
    
    # En-tête
    md_content.append("# Rapport de Traitement de Texte")
    md_content.append(f"**Généré le:** {report_data['generation_info']['generated_at']}")
    md_content.append("")
    
    # Résumé
    gen_info = report_data['generation_info']
    md_content.append("## Résumé")
    md_content.append(f"- **Processeurs utilisés:** {gen_info['total_processors_used']}")
    md_content.append(f"- **Textes traités:** {gen_info['total_texts_processed']}")
    md_content.append("")
    
    # Analyse de qualité
    quality = report_data['quality_analysis']
    md_content.append("## Analyse de Qualité")
    md_content.append(f"**Score global:** {quality['overall_score']:.2f}")
    md_content.append("")
    
    md_content.append("### Scores par processeur")
    for processor, score in quality['processor_scores'].items():
        md_content.append(f"- **{processor}:** {score:.2f}")
    md_content.append("")
    
    # Insights
    insights = report_data['key_insights']
    md_content.append("## Insights Clés")
    
    if 'lyrics_insights' in insights:
        lyrics = insights['lyrics_insights']
        md_content.append("### Analyse des Paroles")
        md_content.append(f"- **Tracks analysées:** {lyrics.get('total_tracks_analyzed', 0)}")
        md_content.append(f"- **Taux de collaboration:** {lyrics.get('collaboration_rate', 0):.1%}")
        md_content.append(f"- **Contenu explicite:** {lyrics.get('explicit_content_rate', 0):.1%}")
        md_content.append("")
    
    return "\n".join(md_content)

def _format_report_html(report_data: Dict[str, Any]) -> str:
    """Formate le rapport en HTML"""
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Rapport de Traitement de Texte</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .header { background: #f4f4f4; padding: 20px; border-radius: 5px; }
            .section { margin: 20px 0; }
            .metric { display: inline-block; margin: 10px; padding: 10px; background: #e8f4fd; border-radius: 3px; }
            .score { font-weight: bold; color: #2c5aa0; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Rapport de Traitement de Texte</h1>
            <p>Généré le: {generated_at}</p>
        </div>
        
        <div class="section">
            <h2>Résumé</h2>
            <div class="metric">Processeurs: <span class="score">{processors}</span></div>
            <div class="metric">Textes traités: <span class="score">{texts}</span></div>
            <div class="metric">Score global: <span class="score">{overall_score:.2f}</span></div>
        </div>
        
        <!-- Contenu détaillé ici -->
        
    </body>
    </html>
    """
    
    return html_template.format(
        generated_at=report_data['generation_info']['generated_at'],
        processors=report_data['generation_info']['total_processors_used'],
        texts=report_data['generation_info']['total_texts_processed'],
        overall_score=report_data['quality_analysis']['overall_score']
    )

# ===== INITIALISATION =====

# Validation automatique au chargement
_setup_valid, _setup_issues = validate_text_setup()

if not _setup_valid:
    logger.warning("⚠️ Problèmes détectés dans la configuration text processors:")
    for issue in _setup_issues:
        logger.warning(f"  - {issue}")
else:
    logger.info(f"✅ Module text processors initialisé: {len(get_available_processors())} processeurs disponibles")

# Export final
__all__.extend([
    'get_available_processors',
    'get_import_stats',
    'create_processor',
    'get_processor_capabilities',
    'run_text_diagnostics',
    'validate_text_setup',
    'batch_process_texts',
    'analyze_text_quality',
    'extract_key_insights',
    'generate_processing_report'
])