# extractors/text_processors/lyrics_processor.py
"""
Processeur optimisé pour l'analyse et le traitement des paroles.
Version optimisée avec cache intelligent, analyse sémantique et détection de patterns.
"""

import logging
import re
from functools import lru_cache
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime
from collections import Counter, defaultdict

# Imports absolus
from core.cache import CacheManager
from config.settings import settings
from utils.text_utils import normalize_text, clean_text
from models.enums import DataSource, Genre, LyricsFeature


class LyricsProcessor:
    """
    Processeur spécialisé pour l'analyse des paroles de rap/hip-hop.
    
    Fonctionnalités optimisées :
    - Nettoyage et normalisation des paroles
    - Détection des structures (couplets, refrains, ponts)
    - Analyse des patterns de rime et flow
    - Extraction des thèmes et références
    - Détection des collaborations (featuring, couplets)
    - Statistiques avancées (vocabulaire, complexité)
    - Cache intelligent pour éviter les retraitements
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration optimisée
        self.config = {
            'min_lyrics_length': settings.get('lyrics.min_length', 50),
            'max_lyrics_length': settings.get('lyrics.max_length', 50000),
            'detect_structure': settings.get('lyrics.detect_structure', True),
            'analyze_rhymes': settings.get('lyrics.analyze_rhymes', True),
            'extract_themes': settings.get('lyrics.extract_themes', True),
            'detect_features': settings.get('lyrics.detect_features', True),
            'language_detection': settings.get('lyrics.language_detection', True),
            'explicit_detection': settings.get('lyrics.explicit_detection', True),
            'vocabulary_analysis': settings.get('lyrics.vocabulary_analysis', True)
        }
        
        # Cache manager
        self.cache_manager = CacheManager(namespace='lyrics') if CacheManager else None
        
        # Patterns pré-compilés pour optimisation
        self.patterns = self._compile_patterns()
        
        # Dictionnaires de mots-clés pour analyse thématique
        self.theme_keywords = self._load_theme_keywords()
        
        # Mots vides français et anglais
        self.stop_words = self._load_stop_words()
        
        # Statistiques de traitement
        self.stats = {
            'lyrics_processed': 0,
            'structures_detected': 0,
            'themes_extracted': 0,
            'features_detected': 0,
            'cache_hits': 0,
            'total_processing_time': 0.0
        }
        
        self.logger.info("✅ LyricsProcessor optimisé initialisé")
    
    @lru_cache(maxsize=1)
    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Compile les patterns regex avec cache"""
        return {
            # Structure des paroles
            'verse_markers': re.compile(r'\[(verse|couplet|v)\s*(\d+)?\]', re.IGNORECASE),
            'chorus_markers': re.compile(r'\[(chorus|refrain|hook|r)\s*(\d+)?\]', re.IGNORECASE),
            'bridge_markers': re.compile(r'\[(bridge|pont|b)\s*(\d+)?\]', re.IGNORECASE),
            'intro_markers': re.compile(r'\[(intro|introduction)\]', re.IGNORECASE),
            'outro_markers': re.compile(r'\[(outro|conclusion)\]', re.IGNORECASE),
            
            # Featuring et collaborations
            'featuring_markers': re.compile(r'\[(feat\.?|featuring|ft\.?)\s*([^\]]+)\]', re.IGNORECASE),
            'artist_markers': re.compile(r'\[([^\]]+):\]', re.IGNORECASE),
            
            # Nettoyage
            'html_tags': re.compile(r'<[^>]+>'),
            'extra_whitespace': re.compile(r'\s+'),
            'bracket_content': re.compile(r'\[[^\]]*\]'),
            'parentheses_content': re.compile(r'\([^)]*\)'),
            
            # Analyse de rimes
            'end_words': re.compile(r'\b(\w+)\s*$', re.MULTILINE),
            'internal_rhymes': re.compile(r'\b(\w+)\b.*?\b(\w+)\b', re.IGNORECASE),
            
            # Détection explicite
            'explicit_words': re.compile(r'\b(' + '|'.join([
                'shit', 'fuck', 'bitch', 'ass', 'damn', 'hell',
                'merde', 'putain', 'connard', 'salope', 'bordel'
            ]) + r')\b', re.IGNORECASE),
            
            # URLs et mentions
            'urls': re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'),
            'mentions': re.compile(r'@\w+'),
            'hashtags': re.compile(r'#\w+')
        }
    
    @lru_cache(maxsize=1)
    def _load_theme_keywords(self) -> Dict[str, List[str]]:
        """Charge les mots-clés thématiques avec cache"""
        return {
            'money': [
                'money', 'cash', 'dollar', 'euro', 'rich', 'wealth', 'millionaire', 'billionaire',
                'argent', 'fric', 'thune', 'riche', 'fortune', 'millionnaire', 'milliardaire'
            ],
            'success': [
                'success', 'win', 'victory', 'champion', 'top', 'best', 'first', 'boss',
                'succès', 'réussir', 'victoire', 'champion', 'premier', 'meilleur', 'patron'
            ],
            'struggle': [
                'struggle', 'fight', 'battle', 'hard', 'difficult', 'pain', 'suffer',
                'galère', 'combat', 'bataille', 'dur', 'difficile', 'douleur', 'souffrir'
            ],
            'street': [
                'street', 'hood', 'ghetto', 'block', 'corner', 'trap', 'hustle',
                'rue', 'quartier', 'banlieue', 'cité', 'tess', 'tieks'
            ],
            'family': [
                'family', 'mother', 'father', 'brother', 'sister', 'mama', 'papa',
                'famille', 'mère', 'père', 'frère', 'sœur', 'maman', 'papa'
            ],
            'love': [
                'love', 'girl', 'woman', 'heart', 'baby', 'honey', 'bae',
                'amour', 'fille', 'femme', 'cœur', 'bébé', 'chérie', 'meuf'
            ],
            'drugs': [
                'weed', 'smoke', 'high', 'joint', 'blunt', 'cannabis', 'marijuana',
                'shit', 'beuh', 'fumette', 'joint', 'pétard', 'cannabis'
            ],
            'violence': [
                'gun', 'shoot', 'kill', 'murder', 'blood', 'war', 'fight',
                'flingue', 'tirer', 'tuer', 'meurtre', 'sang', 'guerre', 'bagarre'
            ]
        }
    
    @lru_cache(maxsize=1)
    def _load_stop_words(self) -> Set[str]:
        """Charge les mots vides avec cache"""
        french_stop_words = {
            'le', 'de', 'et', 'à', 'un', 'il', 'être', 'et', 'en', 'avoir', 'que', 'pour',
            'dans', 'ce', 'son', 'une', 'sur', 'avec', 'ne', 'se', 'pas', 'tout', 'plus',
            'par', 'grand', 'end', 'le', 'bien', 'autre', 'pour', 'ce', 'grand', 'le'
        }
        
        english_stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before', 'after',
            'above', 'below', 'between', 'among', 'through', 'during', 'before', 'after'
        }
        
        return french_stop_words.union(english_stop_words)
    
    # ===== MÉTHODES PRINCIPALES =====
    
    def process_lyrics(self, lyrics: str, track_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Traite et analyse des paroles complètes.
        
        Args:
            lyrics: Texte des paroles brutes
            track_metadata: Métadonnées du track pour contexte
            
        Returns:
            Dictionnaire avec toutes les analyses
        """
        import time
        start_time = time.time()
        
        if not lyrics or len(lyrics) < self.config['min_lyrics_length']:
            return self._empty_result("Paroles trop courtes ou vides")
        
        if len(lyrics) > self.config['max_lyrics_length']:
            return self._empty_result("Paroles trop longues")
        
        # Génération de la clé de cache
        cache_key = self._generate_cache_key(lyrics, track_metadata)
        
        # Vérifier le cache
        if self.cache_manager:
            cached_result = self.cache_manager.get(cache_key)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        try:
            # 1. Nettoyage et normalisation
            cleaned_lyrics = self._clean_lyrics(lyrics)
            
            # 2. Analyse de base
            basic_analysis = self._analyze_basic_stats(cleaned_lyrics)
            
            # 3. Détection de structure
            structure_analysis = {}
            if self.config['detect_structure']:
                structure_analysis = self._analyze_structure(lyrics)  # Utiliser les paroles brutes pour les marqueurs
                self.stats['structures_detected'] += 1
            
            # 4. Analyse des rimes
            rhyme_analysis = {}
            if self.config['analyze_rhymes']:
                rhyme_analysis = self._analyze_rhymes(cleaned_lyrics)
            
            # 5. Extraction des thèmes
            theme_analysis = {}
            if self.config['extract_themes']:
                theme_analysis = self._extract_themes(cleaned_lyrics)
                self.stats['themes_extracted'] += 1
            
            # 6. Détection des featuring
            featuring_analysis = {}
            if self.config['detect_features']:
                featuring_analysis = self._detect_featuring_artists(lyrics)
                if featuring_analysis.get('featuring_artists'):
                    self.stats['features_detected'] += 1
            
            # 7. Détection de langue
            language_analysis = {}
            if self.config['language_detection']:
                language_analysis = self._detect_language(cleaned_lyrics)
            
            # 8. Détection de contenu explicite
            explicit_analysis = {}
            if self.config['explicit_detection']:
                explicit_analysis = self._detect_explicit_content(cleaned_lyrics)
            
            # 9. Analyse du vocabulaire
            vocabulary_analysis = {}
            if self.config['vocabulary_analysis']:
                vocabulary_analysis = self._analyze_vocabulary(cleaned_lyrics)
            
            # Compilation du résultat
            result = {
                'success': True,
                'processed_lyrics': cleaned_lyrics,
                'basic_stats': basic_analysis,
                'structure': structure_analysis,
                'rhymes': rhyme_analysis,
                'themes': theme_analysis,
                'featuring': featuring_analysis,
                'language': language_analysis,
                'explicit_content': explicit_analysis,
                'vocabulary': vocabulary_analysis,
                'processing_metadata': {
                    'processed_at': datetime.now().isoformat(),
                    'processor_version': '1.0.0',
                    'processing_time': time.time() - start_time,
                    'original_length': len(lyrics),
                    'cleaned_length': len(cleaned_lyrics)
                }
            }
            
            # Mise en cache
            if self.cache_manager:
                self.cache_manager.set(cache_key, result, ttl=3600)
            
            self.stats['lyrics_processed'] += 1
            self.stats['total_processing_time'] += time.time() - start_time
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Erreur traitement paroles: {e}")
            return self._empty_result(f"Erreur de traitement: {str(e)}")
    
    def _clean_lyrics(self, lyrics: str) -> str:
        """Nettoie et normalise les paroles"""
        try:
            # Supprimer les balises HTML
            text = self.patterns['html_tags'].sub('', lyrics)
            
            # Supprimer les URLs, mentions, hashtags
            text = self.patterns['urls'].sub('', text)
            text = self.patterns['mentions'].sub('', text)
            text = self.patterns['hashtags'].sub('', text)
            
            # Normaliser les espaces
            text = self.patterns['extra_whitespace'].sub(' ', text)
            
            # Supprimer les lignes vides multiples
            lines = text.split('\n')
            cleaned_lines = []
            prev_empty = False
            
            for line in lines:
                line = line.strip()
                if line:
                    cleaned_lines.append(line)
                    prev_empty = False
                elif not prev_empty:
                    cleaned_lines.append('')
                    prev_empty = True
            
            return '\n'.join(cleaned_lines).strip()
            
        except Exception as e:
            self.logger.debug(f"Erreur nettoyage paroles: {e}")
            return lyrics.strip()
    
    def _analyze_basic_stats(self, lyrics: str) -> Dict[str, Any]:
        """Analyse les statistiques de base des paroles"""
        lines = lyrics.split('\n')
        words = lyrics.split()
        
        # Compter les lignes non vides
        non_empty_lines = [line for line in lines if line.strip()]
        
        # Compter les mots uniques
        unique_words = set(word.lower().strip('.,!?;:') for word in words if word.strip())
        
        # Longueur moyenne des lignes
        avg_line_length = sum(len(line) for line in non_empty_lines) / len(non_empty_lines) if non_empty_lines else 0
        
        # Longueur moyenne des mots
        avg_word_length = sum(len(word) for word in words) / len(words) if words else 0
        
        return {
            'total_characters': len(lyrics),
            'total_lines': len(lines),
            'non_empty_lines': len(non_empty_lines),
            'total_words': len(words),
            'unique_words': len(unique_words),
            'vocabulary_richness': len(unique_words) / len(words) if words else 0,
            'average_line_length': round(avg_line_length, 2),
            'average_word_length': round(avg_word_length, 2),
            'lines_per_word': round(len(non_empty_lines) / len(words), 4) if words else 0
        }
    
    def _analyze_structure(self, lyrics: str) -> Dict[str, Any]:
        """Analyse la structure des paroles (couplets, refrains, etc.)"""
        structure = {
            'sections': [],
            'verse_count': 0,
            'chorus_count': 0,
            'bridge_count': 0,
            'has_intro': False,
            'has_outro': False,
            'estimated_structure': []
        }
        
        try:
            lines = lyrics.split('\n')
            current_section = None
            section_content = []
            
            for i, line in enumerate(lines):
                line_lower = line.lower().strip()
                
                # Détecter les marqueurs de section
                if self.patterns['verse_markers'].search(line):
                    if current_section:
                        structure['sections'].append({
                            'type': current_section,
                            'content': '\n'.join(section_content),
                            'line_start': i - len(section_content),
                            'line_count': len(section_content)
                        })
                    current_section = 'verse'
                    structure['verse_count'] += 1
                    section_content = []
                    
                elif self.patterns['chorus_markers'].search(line):
                    if current_section:
                        structure['sections'].append({
                            'type': current_section,
                            'content': '\n'.join(section_content),
                            'line_start': i - len(section_content),
                            'line_count': len(section_content)
                        })
                    current_section = 'chorus'
                    structure['chorus_count'] += 1
                    section_content = []
                    
                elif self.patterns['bridge_markers'].search(line):
                    if current_section:
                        structure['sections'].append({
                            'type': current_section,
                            'content': '\n'.join(section_content),
                            'line_start': i - len(section_content),
                            'line_count': len(section_content)
                        })
                    current_section = 'bridge'
                    structure['bridge_count'] += 1
                    section_content = []
                    
                elif self.patterns['intro_markers'].search(line):
                    structure['has_intro'] = True
                    current_section = 'intro'
                    section_content = []
                    
                elif self.patterns['outro_markers'].search(line):
                    structure['has_outro'] = True
                    current_section = 'outro'
                    section_content = []
                    
                else:
                    # Contenu de section
                    if line.strip():
                        section_content.append(line)
            
            # Ajouter la dernière section
            if current_section and section_content:
                structure['sections'].append({
                    'type': current_section,
                    'content': '\n'.join(section_content),
                    'line_start': len(lines) - len(section_content),
                    'line_count': len(section_content)
                })
            
            # Estimation de structure si pas de marqueurs explicites
            if not structure['sections']:
                structure['estimated_structure'] = self._estimate_structure(lyrics)
            
        except Exception as e:
            self.logger.debug(f"Erreur analyse structure: {e}")
        
        return structure
    
    def _estimate_structure(self, lyrics: str) -> List[Dict[str, Any]]:
        """Estime la structure basée sur la répétition de lignes"""
        lines = [line.strip() for line in lyrics.split('\n') if line.strip()]
        
        if len(lines) < 4:
            return []
        
        # Détecter les lignes répétées (potentiels refrains)
        line_counts = Counter(lines)
        repeated_lines = {line: count for line, count in line_counts.items() if count > 1}
        
        estimated_sections = []
        current_section_lines = []
        section_type = 'verse'
        
        for line in lines:
            if line in repeated_lines and len(current_section_lines) > 0:
                # Fin de section potentielle
                if current_section_lines:
                    estimated_sections.append({
                        'type': section_type,
                        'content': '\n'.join(current_section_lines),
                        'confidence': 0.6,
                        'estimated': True
                    })
                
                # Nouvelle section (probablement refrain)
                section_type = 'chorus' if line in repeated_lines else 'verse'
                current_section_lines = [line]
            else:
                current_section_lines.append(line)
        
        # Ajouter la dernière section
        if current_section_lines:
            estimated_sections.append({
                'type': section_type,
                'content': '\n'.join(current_section_lines),
                'confidence': 0.6,
                'estimated': True
            })
        
        return estimated_sections
    
    def _analyze_rhymes(self, lyrics: str) -> Dict[str, Any]:
        """Analyse les schémas de rimes"""
        rhyme_analysis = {
            'end_rhymes': [],
            'internal_rhymes': [],
            'rhyme_scheme': '',
            'rhyme_density': 0.0,
            'rhyme_complexity': 0.0
        }
        
        try:
            lines = [line.strip() for line in lyrics.split('\n') if line.strip()]
            
            # Extraire les mots de fin de ligne
            end_words = []
            for line in lines:
                match = self.patterns['end_words'].search(line)
                if match:
                    end_words.append(match.group(1).lower())
            
            # Analyser les rimes de fin
            rhyme_groups = defaultdict(list)
            for i, word in enumerate(end_words):
                # Simplification: considérer les 2-3 derniers phonèmes
                rhyme_key = word[-3:] if len(word) >= 3 else word
                rhyme_groups[rhyme_key].append((i, word))
            
            # Filtrer les vrais groupes de rimes (2+ occurrences)
            actual_rhymes = {k: v for k, v in rhyme_groups.items() if len(v) >= 2}
            
            rhyme_analysis['end_rhymes'] = [
                {
                    'rhyme_sound': rhyme_key,
                    'words': [word for _, word in positions],
                    'line_positions': [pos for pos, _ in positions],
                    'frequency': len(positions)
                }
                for rhyme_key, positions in actual_rhymes.items()
            ]
            
            # Calculer la densité de rimes
            rhyming_lines = sum(len(positions) for positions in actual_rhymes.values())
            rhyme_analysis['rhyme_density'] = rhyming_lines / len(end_words) if end_words else 0
            
            # Complexité basée sur la variété des schémas
            rhyme_analysis['rhyme_complexity'] = len(actual_rhymes) / len(end_words) if end_words else 0
            
        except Exception as e:
            self.logger.debug(f"Erreur analyse rimes: {e}")
        
        return rhyme_analysis
    
    def _extract_themes(self, lyrics: str) -> Dict[str, Any]:
        """Extrait les thèmes principaux des paroles"""
        theme_analysis = {
            'detected_themes': {},
            'theme_intensity': {},
            'dominant_themes': [],
            'theme_words': {}
        }
        
        try:
            words = lyrics.lower().split()
            word_count = len(words)
            
            # Analyser chaque thème
            for theme, keywords in self.theme_keywords.items():
                matches = []
                for word in words:
                    clean_word = word.strip('.,!?;:()[]')
                    if clean_word in keywords:
                        matches.append(clean_word)
                
                if matches:
                    frequency = len(matches)
                    intensity = frequency / word_count if word_count > 0 else 0
                    
                    theme_analysis['detected_themes'][theme] = frequency
                    theme_analysis['theme_intensity'][theme] = round(intensity * 100, 2)
                    theme_analysis['theme_words'][theme] = list(set(matches))
            
            # Identifier les thèmes dominants
            if theme_analysis['theme_intensity']:
                sorted_themes = sorted(
                    theme_analysis['theme_intensity'].items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                theme_analysis['dominant_themes'] = [
                    theme for theme, intensity in sorted_themes[:3] if intensity > 0.5
                ]
            
        except Exception as e:
            self.logger.debug(f"Erreur extraction thèmes: {e}")
        
        return theme_analysis
    
    def _detect_featuring_artists(self, lyrics: str) -> Dict[str, Any]:
        """Détecte les artistes en featuring dans les paroles"""
        featuring_analysis = {
            'featuring_artists': [],
            'artist_sections': [],
            'collaboration_detected': False
        }
        
        try:
            # Détecter les marqueurs de featuring explicites
            feat_matches = self.patterns['featuring_markers'].findall(lyrics)
            for match in feat_matches:
                if len(match) >= 2:
                    artist_name = match[1].strip()
                    featuring_analysis['featuring_artists'].append({
                        'name': artist_name,
                        'detection_method': 'explicit_marker',
                        'confidence': 0.9
                    })
            
            # Détecter les marqueurs d'artiste (format [Artiste:])
            artist_matches = self.patterns['artist_markers'].findall(lyrics)
            for artist_name in artist_matches:
                artist_name = artist_name.strip()
                if artist_name and ':' not in artist_name:  # Éviter les faux positifs
                    featuring_analysis['artist_sections'].append({
                        'artist': artist_name,
                        'detection_method': 'section_marker',
                        'confidence': 0.8
                    })
            
            # Marquer comme collaboration si on a trouvé des featuring ou sections
            featuring_analysis['collaboration_detected'] = (
                len(featuring_analysis['featuring_artists']) > 0 or
                len(featuring_analysis['artist_sections']) > 0
            )
            
        except Exception as e:
            self.logger.debug(f"Erreur détection featuring: {e}")
        
        return featuring_analysis
    
    def _detect_language(self, lyrics: str) -> Dict[str, Any]:
        """Détecte la langue principale des paroles"""
        language_analysis = {
            'primary_language': 'unknown',
            'confidence': 0.0,
            'detected_languages': {}
        }
        
        try:
            words = [word.lower().strip('.,!?;:()[]') for word in lyrics.split()]
            
            # Mots indicateurs de langue française
            french_indicators = {
                'le', 'la', 'les', 'de', 'du', 'des', 'et', 'est', 'que', 'qui', 'pour',
                'dans', 'avec', 'sur', 'par', 'mais', 'ou', 'donc', 'ni', 'car', 'je',
                'tu', 'il', 'elle', 'nous', 'vous', 'ils', 'elles', 'mon', 'ma', 'mes',
                'ton', 'ta', 'tes', 'son', 'sa', 'ses', 'notre', 'votre', 'leur', 'leurs'
            }
            
            # Mots indicateurs de langue anglaise
            english_indicators = {
                'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
                'by', 'from', 'about', 'like', 'that', 'this', 'these', 'those', 'i',
                'you', 'he', 'she', 'we', 'they', 'my', 'your', 'his', 'her', 'our',
                'their', 'me', 'him', 'us', 'them', 'am', 'is', 'are', 'was', 'were'
            }
            
            # Compter les occurrences
            french_count = sum(1 for word in words if word in french_indicators)
            english_count = sum(1 for word in words if word in english_indicators)
            
            total_words = len(words)
            french_ratio = french_count / total_words if total_words > 0 else 0
            english_ratio = english_count / total_words if total_words > 0 else 0
            
            language_analysis['detected_languages'] = {
                'french': round(french_ratio * 100, 2),
                'english': round(english_ratio * 100, 2)
            }
            
            # Déterminer la langue principale
            if french_ratio > english_ratio and french_ratio > 0.05:
                language_analysis['primary_language'] = 'french'
                language_analysis['confidence'] = min(french_ratio * 2, 1.0)
            elif english_ratio > french_ratio and english_ratio > 0.05:
                language_analysis['primary_language'] = 'english'
                language_analysis['confidence'] = min(english_ratio * 2, 1.0)
            elif french_ratio > 0.03 and english_ratio > 0.03:
                language_analysis['primary_language'] = 'mixed'
                language_analysis['confidence'] = 0.7
            
        except Exception as e:
            self.logger.debug(f"Erreur détection langue: {e}")
        
        return language_analysis
    
    def _detect_explicit_content(self, lyrics: str) -> Dict[str, Any]:
        """Détecte le contenu explicite dans les paroles"""
        explicit_analysis = {
            'is_explicit': False,
            'explicit_words_found': [],
            'explicit_word_count': 0,
            'explicit_density': 0.0,
            'severity_level': 'clean'
        }
        
        try:
            # Rechercher les mots explicites
            matches = self.patterns['explicit_words'].findall(lyrics.lower())
            explicit_words = [match for match in matches if match]
            
            explicit_analysis['explicit_words_found'] = list(set(explicit_words))
            explicit_analysis['explicit_word_count'] = len(explicit_words)
            
            # Calculer la densité
            total_words = len(lyrics.split())
            if total_words > 0:
                explicit_analysis['explicit_density'] = len(explicit_words) / total_words
            
            # Déterminer si c'est explicite
            if len(explicit_words) > 0:
                explicit_analysis['is_explicit'] = True
                
                # Déterminer le niveau de sévérité
                density = explicit_analysis['explicit_density']
                if density > 0.05:  # Plus de 5% de mots explicites
                    explicit_analysis['severity_level'] = 'high'
                elif density > 0.02:  # Plus de 2% de mots explicites
                    explicit_analysis['severity_level'] = 'medium'
                else:
                    explicit_analysis['severity_level'] = 'low'
        
        except Exception as e:
            self.logger.debug(f"Erreur détection contenu explicite: {e}")
        
        return explicit_analysis
    
    def _analyze_vocabulary(self, lyrics: str) -> Dict[str, Any]:
        """Analyse le vocabulaire et la complexité linguistique"""
        vocabulary_analysis = {
            'unique_words': 0,
            'total_words': 0,
            'vocabulary_richness': 0.0,
            'average_word_length': 0.0,
            'long_words_ratio': 0.0,
            'rare_words': [],
            'most_frequent_words': []
        }
        
        try:
            # Nettoyage et extraction des mots
            words = []
            for word in lyrics.lower().split():
                clean_word = word.strip('.,!?;:()[]"\'')
                if clean_word and clean_word not in self.stop_words:
                    words.append(clean_word)
            
            if not words:
                return vocabulary_analysis
            
            # Statistiques de base
            unique_words = set(words)
            vocabulary_analysis['unique_words'] = len(unique_words)
            vocabulary_analysis['total_words'] = len(words)
            vocabulary_analysis['vocabulary_richness'] = len(unique_words) / len(words)
            
            # Longueur moyenne des mots
            vocabulary_analysis['average_word_length'] = sum(len(word) for word in words) / len(words)
            
            # Ratio de mots longs (6+ caractères)
            long_words = [word for word in words if len(word) >= 6]
            vocabulary_analysis['long_words_ratio'] = len(long_words) / len(words)
            
            # Fréquence des mots
            word_counts = Counter(words)
            
            # Mots les plus fréquents (top 10)
            vocabulary_analysis['most_frequent_words'] = [
                {'word': word, 'count': count}
                for word, count in word_counts.most_common(10)
            ]
            
            # Mots rares (apparaissent une seule fois et sont longs)
            vocabulary_analysis['rare_words'] = [
                word for word, count in word_counts.items()
                if count == 1 and len(word) >= 7
            ][:20]  # Limiter à 20 mots rares
            
        except Exception as e:
            self.logger.debug(f"Erreur analyse vocabulaire: {e}")
        
        return vocabulary_analysis
    
    # ===== MÉTHODES UTILITAIRES =====
    
    def _generate_cache_key(self, lyrics: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Génère une clé de cache pour les paroles"""
        import hashlib
        
        content = lyrics
        if metadata:
            content += str(sorted(metadata.items()))
        
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _empty_result(self, error_message: str) -> Dict[str, Any]:
        """Retourne un résultat vide avec message d'erreur"""
        return {
            'success': False,
            'error': error_message,
            'processed_lyrics': '',
            'basic_stats': {},
            'structure': {},
            'rhymes': {},
            'themes': {},
            'featuring': {},
            'language': {},
            'explicit_content': {},
            'vocabulary': {},
            'processing_metadata': {
                'processed_at': datetime.now().isoformat(),
                'processor_version': '1.0.0'
            }
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de traitement"""
        return self.stats.copy()
    
    def clear_cache(self) -> bool:
        """Vide le cache du processeur"""
        if self.cache_manager:
            return self.cache_manager.clear()
        return True