# utils/text_utils.py - VERSION CORRIGÉE ET RÉORGANISÉE
"""
Utilitaires optimisés pour la manipulation et normalisation de texte.
Fonctions spécialisées pour les données musicales (artistes, titres, albums).
"""

import re
import logging
import unicodedata
from typing import List, Dict, Optional, Tuple, Set, Any
from functools import lru_cache
from difflib import SequenceMatcher

# Configuration du logging
logger = logging.getLogger(__name__)

# ===== PATTERNS DE NORMALISATION (COMPILÉS POUR PERFORMANCE) =====

# Patterns pour featuring/collaborations
FEATURING_PATTERNS = [
    re.compile(r'\b(?:feat\.?|featuring|ft\.?|avec|with)\s+(.+)', re.IGNORECASE),
    re.compile(r'\((?:feat\.?|featuring|ft\.?|avec|with)\s+([^)]+)\)', re.IGNORECASE),
    re.compile(r'\[(?:feat\.?|featuring|ft\.?|avec|with)\s+([^\]]+)\]', re.IGNORECASE)
]

# Patterns pour nettoyer les noms
CLEAN_PATTERNS = {
    'extra_spaces': re.compile(r'\s+'),
    'leading_trailing': re.compile(r'^\s+|\s+$'),
    'special_chars': re.compile(r'[^\w\s\-\'\.&]'),
    'multiple_dots': re.compile(r'\.{2,}'),
    'multiple_dashes': re.compile(r'-{2,}'),
    'parenthetical': re.compile(r'\([^)]*\)'),
    'brackets': re.compile(r'\[[^\]]*\]'),
    'version_info': re.compile(r'\b(?:remix|version|edit|mix|instrumental|acapella|radio|clean|explicit)\b', re.IGNORECASE)
}

# Patterns pour validation
VALIDATION_PATTERNS = {
    'artist_name': re.compile(r'^[a-zA-Z0-9\s\-\'\.&]+$'),
    'has_letters': re.compile(r'[a-zA-Z]'),
    'suspicious_chars': re.compile(r'[<>{}|\\^`\[\]"]'),
    'only_special': re.compile(r'^[^a-zA-Z0-9]+$')
}

# Mots vides pour différentes langues
STOP_WORDS = {
    'french': {'le', 'la', 'les', 'de', 'du', 'des', 'et', 'ou', 'à', 'dans', 'pour', 'avec', 'sur'},
    'english': {'the', 'a', 'an', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'},
    'common': {'feat', 'featuring', 'ft', 'remix', 'version', 'edit', 'mix'}
}

# Correspondances de caractères spéciaux
CHAR_REPLACEMENTS = {
    'à': 'a', 'á': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a', 'å': 'a',
    'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
    'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
    'ò': 'o', 'ó': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
    'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u',
    'ý': 'y', 'ÿ': 'y',
    'ñ': 'n', 'ç': 'c',
    'œ': 'oe', 'æ': 'ae',
    '&': 'and', '@': 'at'
}

# ===== FONCTIONS PRINCIPALES DE NETTOYAGE =====

@lru_cache(maxsize=512)
def clean_artist_name(name: str) -> str:
    """
    Nettoie et normalise un nom d'artiste.
    
    Args:
        name: Nom d'artiste brut
        
    Returns:
        Nom d'artiste nettoyé
    """
    if not name or not isinstance(name, str):
        return ""
    
    # Suppression des espaces en début/fin
    cleaned = name.strip()
    
    # Normalisation Unicode
    cleaned = unicodedata.normalize('NFKD', cleaned)
    
    # Remplacement des caractères spéciaux
    for old_char, new_char in CHAR_REPLACEMENTS.items():
        cleaned = cleaned.replace(old_char, new_char)
    
    # Suppression des caractères suspects
    if VALIDATION_PATTERNS['suspicious_chars'].search(cleaned):
        cleaned = VALIDATION_PATTERNS['suspicious_chars'].sub('', cleaned)
    
    # Normalisation des espaces
    cleaned = CLEAN_PATTERNS['extra_spaces'].sub(' ', cleaned)
    
    # Nettoyage final
    cleaned = cleaned.strip()
    
    return cleaned if cleaned else name  # Retour au nom original si nettoyage échoue

@lru_cache(maxsize=512)
def normalize_title(title: str, remove_featuring: bool = False, remove_version: bool = False) -> str:
    """
    Normalise un titre de morceau.
    
    Args:
        title: Titre brut
        remove_featuring: Supprimer les mentions de featuring
        remove_version: Supprimer les infos de version
        
    Returns:
        Titre normalisé
    """
    if not title or not isinstance(title, str):
        return ""
    
    # Nettoyage initial
    normalized = title.strip()
    
    # Normalisation Unicode
    normalized = unicodedata.normalize('NFKD', normalized)
    
    # Suppression des featuring si demandé
    if remove_featuring:
        for pattern in FEATURING_PATTERNS:
            normalized = pattern.sub('', normalized)
    
    # Suppression des infos de version si demandé
    if remove_version:
        normalized = CLEAN_PATTERNS['version_info'].sub('', normalized)
    
    # Nettoyage des parenthèses/crochets vides
    normalized = re.sub(r'\(\s*\)', '', normalized)
    normalized = re.sub(r'\[\s*\]', '', normalized)
    
    # Normalisation des espaces et ponctuation
    normalized = CLEAN_PATTERNS['extra_spaces'].sub(' ', normalized)
    normalized = CLEAN_PATTERNS['multiple_dots'].sub('.', normalized)
    normalized = CLEAN_PATTERNS['multiple_dashes'].sub('-', normalized)
    
    # Nettoyage final
    normalized = normalized.strip()
    
    return normalized if normalized else title

@lru_cache(maxsize=256)
def clean_album_title(album_title: str, remove_year: bool = True) -> str:
    """
    Nettoie un titre d'album.
    
    Args:
        album_title: Titre d'album brut
        remove_year: Supprimer l'année en fin de titre
        
    Returns:
        Titre d'album nettoyé
    """
    if not album_title or not isinstance(album_title, str):
        return ""
    
    cleaned = album_title.strip()
    
    # Normalisation Unicode
    cleaned = unicodedata.normalize('NFKD', cleaned)
    
    # Suppression de l'année si demandé
    if remove_year:
        # Pattern pour année en fin de titre
        year_pattern = re.compile(r'\s*\(?\d{4}\)?$')
        cleaned = year_pattern.sub('', cleaned)
    
    # Nettoyage standard
    cleaned = CLEAN_PATTERNS['extra_spaces'].sub(' ', cleaned)
    cleaned = cleaned.strip()
    
    return cleaned if cleaned else album_title

@lru_cache(maxsize=512)
def normalize_text(text: str, aggressive: bool = False) -> str:
    """
    Normalisation complète d'un texte.
    
    Args:
        text: Texte à normaliser
        aggressive: Normalisation agressive (supprime plus d'éléments)
        
    Returns:
        Texte normalisé
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Normalisation Unicode
    normalized = unicodedata.normalize('NFKD', text)
    
    # Conversion en minuscules
    normalized = normalized.lower()
    
    # Remplacement des caractères spéciaux
    for old_char, new_char in CHAR_REPLACEMENTS.items():
        normalized = normalized.replace(old_char.lower(), new_char)
    
    # Suppression des caractères non-alphanumériques (sauf espaces et tirets)
    if aggressive:
        normalized = re.sub(r'[^a-z0-9\s\-]', '', normalized)
    else:
        normalized = re.sub(r'[^a-z0-9\s\-\']', '', normalized)
    
    # Normalisation des espaces
    normalized = CLEAN_PATTERNS['extra_spaces'].sub(' ', normalized)
    normalized = normalized.strip()
    
    return normalized

@lru_cache(maxsize=256)
def clean_text(text: str, remove_extra_spaces: bool = True, remove_special_chars: bool = False) -> str:
    """
    Nettoyage basique d'un texte.
    
    Args:
        text: Texte à nettoyer
        remove_extra_spaces: Supprimer les espaces multiples
        remove_special_chars: Supprimer les caractères spéciaux
        
    Returns:
        Texte nettoyé
    """
    if not text or not isinstance(text, str):
        return ""
    
    cleaned = text.strip()
    
    if remove_special_chars:
        cleaned = CLEAN_PATTERNS['special_chars'].sub('', cleaned)
    
    if remove_extra_spaces:
        cleaned = CLEAN_PATTERNS['extra_spaces'].sub(' ', cleaned)
    
    return cleaned.strip()

def remove_special_chars(text: str, keep_chars: str = " -'&.") -> str:
    """
    Supprime les caractères spéciaux d'un texte.
    
    Args:
        text: Texte à nettoyer
        keep_chars: Caractères spéciaux à conserver
        
    Returns:
        Texte sans caractères spéciaux
    """
    if not text:
        return ""
    
    # Pattern pour garder les caractères autorisés
    pattern = f'[^a-zA-Z0-9{re.escape(keep_chars)}]'
    cleaned = re.sub(pattern, '', text)
    
    # Nettoyage des espaces
    cleaned = CLEAN_PATTERNS['extra_spaces'].sub(' ', cleaned)
    
    return cleaned.strip()

# ===== FONCTIONS D'EXTRACTION =====

def extract_featured_artists_from_title(title: str) -> Tuple[str, List[str]]:
    """
    Extrait les artistes en featuring d'un titre.
    
    Args:
        title: Titre contenant potentiellement des featuring
        
    Returns:
        Tuple (titre_nettoyé, liste_artistes_featuring)
    """
    if not title:
        return "", []
    
    featured_artists = []
    clean_title = title
    
    # Recherche avec tous les patterns de featuring
    for pattern in FEATURING_PATTERNS:
        match = pattern.search(clean_title)
        if match:
            # Extraction des artistes
            artist_string = match.group(1).strip()
            artists = parse_artist_list(artist_string)
            featured_artists.extend(artists)
            
            # Suppression du featuring du titre
            clean_title = pattern.sub('', clean_title)
    
    # Nettoyage final du titre
    clean_title = normalize_title(clean_title)
    
    # Suppression des doublons dans la liste d'artistes
    featured_artists = list(dict.fromkeys(featured_artists))  # Préserve l'ordre
    
    return clean_title, featured_artists

def parse_artist_list(artist_string: str) -> List[str]:
    """
    Parse une chaîne contenant plusieurs artistes.
    
    Args:
        artist_string: Chaîne d'artistes séparés
        
    Returns:
        Liste d'artistes individuels
    """
    if not artist_string:
        return []
    
    # Séparateurs possibles
    separators = [',', '&', ' and ', ' et ', ' feat ', ' ft ', ' featuring ']
    
    # Remplacement des séparateurs par une virgule
    normalized = artist_string
    for sep in separators:
        normalized = re.sub(re.escape(sep), ',', normalized, flags=re.IGNORECASE)
    
    # Extraction des artistes
    artists = []
    for artist in normalized.split(','):
        cleaned_artist = clean_artist_name(artist)
        if cleaned_artist and len(cleaned_artist) > 1:  # Éviter les initiales isolées
            artists.append(cleaned_artist)
    
    return artists

def extract_parenthetical_info(text: str) -> Tuple[str, List[str]]:
    """
    Extrait les informations entre parenthèses d'un texte.
    
    Args:
        text: Texte contenant des parenthèses
        
    Returns:
        Tuple (texte_sans_parenthèses, liste_contenus_parenthèses)
    """
    if not text:
        return "", []
    
    parenthetical_info = []
    
    # Extraction du contenu entre parenthèses
    parentheses_pattern = re.compile(r'\(([^)]+)\)')
    matches = parentheses_pattern.findall(text)
    parenthetical_info.extend(matches)
    
    # Extraction du contenu entre crochets
    brackets_pattern = re.compile(r'\[([^\]]+)\]')
    matches = brackets_pattern.findall(text)
    parenthetical_info.extend(matches)
    
    # Suppression des parenthèses/crochets du texte
    clean_text = parentheses_pattern.sub('', text)
    clean_text = brackets_pattern.sub('', clean_text)
    
    # Nettoyage final
    clean_text = CLEAN_PATTERNS['extra_spaces'].sub(' ', clean_text).strip()
    
    return clean_text, parenthetical_info

def split_featured_artists(featuring_string: str) -> List[str]:
    """
    Sépare une chaîne d'artistes en featuring.
    
    Args:
        featuring_string: Chaîne contenant les artistes
        
    Returns:
        Liste d'artistes individuels
    """
    return parse_artist_list(featuring_string)

def normalize_featuring(title: str) -> Tuple[str, str]:
    """
    Normalise les mentions de featuring dans un titre.
    
    Args:
        title: Titre avec featuring
        
    Returns:
        Tuple (titre_principal, featuring_normalisé)
    """
    if not title:
        return "", ""
    
    clean_title, featured_artists = extract_featured_artists_from_title(title)
    
    # Construction du featuring normalisé
    if featured_artists:
        featuring_normalized = f"feat. {', '.join(featured_artists)}"
    else:
        featuring_normalized = ""
    
    return clean_title, featuring_normalized

# ===== FONCTIONS DE VALIDATION =====

@lru_cache(maxsize=256)
def validate_artist_name(name: str) -> bool:
    """
    Valide un nom d'artiste.
    
    Args:
        name: Nom d'artiste à valider
        
    Returns:
        True si le nom est valide
    """
    if not name or not isinstance(name, str):
        return False
    
    # Vérifications de base
    if len(name.strip()) < 1:
        return False
    
    # Doit contenir au moins une lettre
    if not VALIDATION_PATTERNS['has_letters'].search(name):
        return False
    
    # Ne doit pas être que des caractères spéciaux
    if VALIDATION_PATTERNS['only_special'].match(name.strip()):
        return False
    
    # Longueur raisonnable
    if len(name) > 100:
        return False
    
    return True

def validate_title(title: str) -> bool:
    """
    Valide un titre de morceau.
    
    Args:
        title: Titre à valider
        
    Returns:
        True si le titre est valide
    """
    if not title or not isinstance(title, str):
        return False
    
    # Longueur minimale
    if len(title.strip()) < 1:
        return False
    
    # Doit contenir au moins une lettre ou un chiffre
    if not re.search(r'[a-zA-Z0-9]', title):
        return False
    
    # Longueur maximale raisonnable
    if len(title) > 200:
        return False
    
    return True

# ===== FONCTIONS DE SIMILARITÉ =====

@lru_cache(maxsize=512)
def similarity_ratio(text1: str, text2: str) -> float:
    """
    Calcule la similarité entre deux textes (0.0 à 1.0).
    
    Args:
        text1: Premier texte
        text2: Deuxième texte
        
    Returns:
        Ratio de similarité (0.0 = différent, 1.0 = identique)
    """
    if not text1 or not text2:
        return 0.0
    
    # Normalisation pour comparaison
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    
    # Calcul de la similarité
    return SequenceMatcher(None, norm1, norm2).ratio()

def fuzzy_match_artist(target: str, candidates: List[str], threshold: float = 0.8) -> Optional[str]:
    """
    Trouve l'artiste le plus similaire dans une liste.
    
    Args:
        target: Nom d'artiste recherché
        candidates: Liste des candidats
        threshold: Seuil de similarité minimum
        
    Returns:
        Meilleur candidat ou None
    """
    if not target or not candidates:
        return None
    
    best_match = None
    best_score = 0.0
    
    target_normalized = normalize_text(target)
    
    for candidate in candidates:
        if not candidate:
            continue
            
        candidate_normalized = normalize_text(candidate)
        score = similarity_ratio(target_normalized, candidate_normalized)
        
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate
    
    return best_match

# ===== FONCTIONS DE DÉTECTION DE LANGUE =====

@lru_cache(maxsize=256)
def detect_language(text: str) -> str:
    """
    Détection basique de langue (français/anglais).
    
    Args:
        text: Texte à analyser
        
    Returns:
        Code de langue ('fr', 'en', 'unknown')
    """
    if not text:
        return 'unknown'
    
    # Normalisation pour analyse
    normalized = normalize_text(text, aggressive=False)
    words = set(normalized.split())
    
    # Comptage des mots indicateurs
    french_indicators = words.intersection(STOP_WORDS['french'])
    english_indicators = words.intersection(STOP_WORDS['english'])
    
    # Patterns spécifiques au français
    french_patterns = [
        r'\bde\b', r'\ble\b', r'\bla\b', r'\bdes\b', r'\bdu\b',
        r'\bà\b', r'\bet\b', r'\bou\b', r'\bdans\b'
    ]
    
    french_score = len(french_indicators)
    for pattern in french_patterns:
        if re.search(pattern, normalized):
            french_score += 1
    
    english_score = len(english_indicators)
    
    # Décision
    if french_score > english_score:
        return 'fr'
    elif english_score > french_score:
        return 'en'
    else:
        return 'unknown'

# ===== FONCTIONS UTILITAIRES =====

def get_text_stats(text: str) -> Dict[str, Any]:
    """
    Retourne des statistiques sur un texte.
    
    Args:
        text: Texte à analyser
        
    Returns:
        Dictionnaire des statistiques
    """
    if not text:
        return {
            'length': 0,
            'words': 0,
            'characters': 0,
            'language': 'unknown',
            'has_featuring': False,
            'special_chars': 0
        }
    
    # Extraction des featuring
    _, featured_artists = extract_featured_artists_from_title(text)
    
    # Comptage des caractères spéciaux
    special_chars = len(VALIDATION_PATTERNS['suspicious_chars'].findall(text))
    
    return {
        'length': len(text),
        'words': len(text.split()),
        'characters': len([c for c in text if c.isalnum()]),
        'language': detect_language(text),
        'has_featuring': len(featured_artists) > 0,
        'featured_artists': featured_artists,
        'special_chars': special_chars,
        'is_valid_artist': validate_artist_name(text),
        'is_valid_title': validate_title(text)
    }

def batch_clean_names(names: List[str], clean_func=clean_artist_name) -> List[str]:
    """
    Nettoie une liste de noms en lot.
    
    Args:
        names: Liste de noms à nettoyer
        clean_func: Fonction de nettoyage à utiliser
        
    Returns:
        Liste de noms nettoyés
    """
    if not names:
        return []
    
    return [clean_func(name) for name in names if name]

def create_search_terms(artist_name: str, title: str) -> List[str]:
    """
    Crée des termes de recherche optimisés.
    
    Args:
        artist_name: Nom de l'artiste
        title: Titre du morceau
        
    Returns:
        Liste de termes de recherche
    """
    terms = []
    
    if artist_name and title:
        # Recherche complète
        terms.append(f"{clean_artist_name(artist_name)} {normalize_title(title)}")
        
        # Recherche sans featuring
        clean_title, _ = extract_featured_artists_from_title(title)
        if clean_title != title:
            terms.append(f"{clean_artist_name(artist_name)} {clean_title}")
        
        # Termes séparés
        terms.append(clean_artist_name(artist_name))
        terms.append(normalize_title(title))
    
    return [term for term in terms if term and len(term.strip()) > 2]

# ===== DIAGNOSTIC ET TESTS =====

def run_text_utils_tests() -> Dict[str, bool]:
    """
    Lance des tests sur les fonctions utilitaires.
    
    Returns:
        Dictionnaire des résultats de tests
    """
    tests = {}
    
    # Test de nettoyage d'artiste
    try:
        result = clean_artist_name("  Nekfeu  ")
        tests['clean_artist_name'] = result == "Nekfeu"
    except Exception:
        tests['clean_artist_name'] = False
    
    # Test de normalisation de titre
    try:
        result = normalize_title("Test Song (feat. Artist)")
        tests['normalize_title'] = len(result) > 0
    except Exception:
        tests['normalize_title'] = False
    
    # Test d'extraction de featuring
    try:
        title, artists = extract_featured_artists_from_title("Song feat. Artist1 & Artist2")
        tests['extract_featuring'] = len(artists) == 2
    except Exception:
        tests['extract_featuring'] = False
    
    # Test de validation
    try:
        tests['validate_artist'] = validate_artist_name("Valid Artist")
        tests['validate_title'] = validate_title("Valid Title")
    except Exception:
        tests['validate_artist'] = False
        tests['validate_title'] = False
    
    # Test de similarité
    try:
        ratio = similarity_ratio("test", "test")
        tests['similarity'] = ratio == 1.0
    except Exception:
        tests['similarity'] = False
    
    return tests

def get_functions_list() -> List[str]:
    """Retourne la liste des fonctions publiques disponibles"""
    return [
        'clean_artist_name', 'normalize_title', 'clean_album_title',
        'normalize_text', 'clean_text', 'remove_special_chars',
        'extract_featured_artists_from_title', 'parse_artist_list',
        'extract_parenthetical_info', 'split_featured_artists', 'normalize_featuring',
        'validate_artist_name', 'validate_title',
        'similarity_ratio', 'fuzzy_match_artist', 'detect_language',
        'get_text_stats', 'batch_clean_names', 'create_search_terms',
        'run_text_utils_tests', 'get_functions_list'
    ]

# ===== LOGGING =====

logger.info("Module text_utils initialisé avec succès")

# ===== EXEMPLES D'UTILISATION =====
"""
Exemples d'utilisation:

# Nettoyage d'artiste
clean_name = clean_artist_name("  Nekfeu  ")  # "Nekfeu"

# Normalisation de titre
title = normalize_title("Ma Song (feat. Artist)")  # "Ma Song (feat. Artist)"

# Extraction de featuring
clean_title, artists = extract_featured_artists_from_title("Song feat. A & B")
# clean_title = "Song", artists = ["A", "B"]

# Validation
is_valid = validate_artist_name("Nekfeu")  # True

# Similarité
ratio = similarity_ratio("Nekfeu", "nekfeu")  # 1.0

# Statistiques
stats = get_text_stats("Ma Song feat. Artist")

# Tests
test_results = run_text_utils_tests()
print(f"Tests réussis: {sum(test_results.values())}/{len(test_results)}")
"""