# utils/text_utils.py
import re
import unicodedata
from typing import List, Optional, Set
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    """
    Normalise un texte pour la comparaison et la recherche.
    
    Args:
        text: Texte à normaliser
        
    Returns:
        Texte normalisé
    """
    if not text:
        return ""
    
    # Convertir en minuscules
    text = text.lower()
    
    # Supprimer les accents
    text = remove_accents(text)
    
    # Supprimer les caractères spéciaux mais garder les espaces et tirets
    text = re.sub(r'[^\w\s\-]', '', text)
    
    # Normaliser les espaces multiples
    text = re.sub(r'\s+', ' ', text)
    
    # Supprimer les espaces en début/fin
    text = text.strip()
    
    return text


def remove_accents(text: str) -> str:
    """
    Supprime les accents d'un texte.
    
    Args:
        text: Texte avec accents
        
    Returns:
        Texte sans accents
    """
    if not text:
        return ""
    
    # Normalisation NFD puis suppression des caractères de combinaison
    nfd = unicodedata.normalize('NFD', text)
    without_accents = ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')
    
    return without_accents


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calcule la similarité entre deux textes (0-1).
    
    Args:
        text1: Premier texte
        text2: Deuxième texte
        
    Returns:
        Score de similarité entre 0 et 1
    """
    if not text1 or not text2:
        return 0.0
    
    # Normaliser les deux textes
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    
    if norm1 == norm2:
        return 1.0
    
    # Utiliser SequenceMatcher pour calculer la similarité
    matcher = SequenceMatcher(None, norm1, norm2)
    return matcher.ratio()


def extract_featuring_artists(title: str) -> tuple[str, List[str]]:
    """
    Extrait les artistes en featuring d'un titre de morceau.
    
    Args:
        title: Titre du morceau
        
    Returns:
        Tuple (titre_nettoyé, liste_des_featuring)
    """
    featuring_artists = []
    
    # Patterns pour détecter les featuring
    featuring_patterns = [
        r'\(feat\.?\s+([^)]+)\)',
        r'\(ft\.?\s+([^)]+)\)',
        r'\(featuring\s+([^)]+)\)',
        r'\sfeat\.?\s+([^(\[]+)',
        r'\sft\.?\s+([^(\[]+)',
        r'\sfeaturing\s+([^(\[]+)'
    ]
    
    clean_title = title
    
    for pattern in featuring_patterns:
        matches = re.finditer(pattern, title, re.IGNORECASE)
        for match in matches:
            # Extraire les artistes
            artists_str = match.group(1).strip()
            
            # Séparer les artistes multiples
            artists = split_multiple_artists(artists_str)
            featuring_artists.extend(artists)
            
            # Supprimer le featuring du titre
            clean_title = clean_title.replace(match.group(0), '').strip()
    
    # Nettoyer le titre final
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    
    # Supprimer les doublons en gardant l'ordre
    unique_featuring = []
    for artist in featuring_artists:
        if artist and artist not in unique_featuring:
            unique_featuring.append(artist)
    
    return clean_title, unique_featuring


def split_multiple_artists(artists_str: str) -> List[str]:
    """
    Sépare une chaîne contenant plusieurs artistes.
    
    Args:
        artists_str: Chaîne d'artistes séparés
        
    Returns:
        Liste des artistes individuels
    """
    if not artists_str:
        return []
    
    # Patterns de séparation
    separators = [' & ', ' and ', ', ', ' x ', ' X ', ' feat. ', ' ft. ']
    
    artists = [artists_str]
    
    for separator in separators:
        new_artists = []
        for artist in artists:
            new_artists.extend(artist.split(separator))
        artists = new_artists
    
    # Nettoyer chaque artiste
    cleaned_artists = []
    for artist in artists:
        cleaned = artist.strip()
        if cleaned and len(cleaned) > 1:  # Éviter les initiales isolées
            cleaned_artists.append(cleaned)
    
    return cleaned_artists


def clean_track_title(title: str) -> str:
    """
    Nettoie un titre de morceau en supprimant les éléments parasites.
    
    Args:
        title: Titre brut
        
    Returns:
        Titre nettoyé
    """
    if not title:
        return ""
    
    # Supprimer les featuring (ils seront gérés séparément)
    clean_title, _ = extract_featuring_artists(title)
    
    # Supprimer les indicateurs de version/remix courants
    version_patterns = [
        r'\(explicit\)',
        r'\(clean\)',
        r'\(radio edit\)',
        r'\(instrumental\)',
        r'\(acapella\)',
        r'\(bonus track\)',
        r'\(deluxe\)',
        r'\(remastered\)',
        r'\(live\)',
        r'\[explicit\]',
        r'\[clean\]',
        r'\[radio edit\]'
    ]
    
    for pattern in version_patterns:
        clean_title = re.sub(pattern, '', clean_title, flags=re.IGNORECASE)
    
    # Nettoyer les espaces
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    
    return clean_title


def clean_artist_name(name: str) -> str:
    """
    Nettoie un nom d'artiste.
    
    Args:
        name: Nom brut
        
    Returns:
        Nom nettoyé
    """
    if not name:
        return ""
    
    # Supprimer les préfixes courants
    prefixes = ['by ', 'prod. by ', 'produced by ', 'feat. ', 'ft. ']
    
    clean_name = name.strip()
    
    for prefix in prefixes:
        if clean_name.lower().startswith(prefix):
            clean_name = clean_name[len(prefix):].strip()
    
    # Supprimer les suffixes
    suffixes = [' (uncredited)', ' (prod)', ' (producer)']
    
    for suffix in suffixes:
        if clean_name.lower().endswith(suffix):
            clean_name = clean_name[:-len(suffix)].strip()
    
    return clean_name


def extract_bpm_from_text(text: str) -> Optional[int]:
    """
    Extrait le BPM d'un texte.
    
    Args:
        text: Texte contenant potentiellement un BPM
        
    Returns:
        BPM extrait ou None
    """
    if not text:
        return None
    
    # Patterns pour détecter le BPM
    bpm_patterns = [
        r'(\d{2,3})\s*bpm',
        r'(\d{2,3})\s*beats?\s*per\s*minute',
        r'tempo:?\s*(\d{2,3})',
        r'(\d{2,3})\s*beats'
    ]
    
    for pattern in bpm_patterns:
        match = re.search(pattern, text.lower())
        if match:
            bpm = int(match.group(1))
            # Validation basique du BPM
            if 40 <= bpm <= 300:
                return bpm
    
    return None


def extract_duration_from_text(text: str) -> Optional[int]:
    """
    Extrait la durée en secondes d'un texte.
    
    Args:
        text: Texte contenant une durée (ex: "3:45", "2m 30s")
        
    Returns:
        Durée en secondes ou None
    """
    if not text:
        return None
    
    # Pattern MM:SS
    mmss_match = re.search(r'(\d{1,2}):(\d{2})', text)
    if mmss_match:
        minutes = int(mmss_match.group(1))
        seconds = int(mmss_match.group(2))
        return minutes * 60 + seconds
    
    # Pattern HH:MM:SS
    hhmmss_match = re.search(r'(\d{1,2}):(\d{2}):(\d{2})', text)
    if hhmmss_match:
        hours = int(hhmmss_match.group(1))
        minutes = int(hhmmss_match.group(2))
        seconds = int(hhmmss_match.group(3))
        return hours * 3600 + minutes * 60 + seconds
    
    # Pattern "Xm Ys"
    ms_match = re.search(r'(\d+)m\s*(\d+)s', text)
    if ms_match:
        minutes = int(ms_match.group(1))
        seconds = int(ms_match.group(2))
        return minutes * 60 + seconds
    
    # Pattern "X minutes Y seconds"
    full_match = re.search(r'(\d+)\s*minutes?\s*(\d+)\s*seconds?', text)
    if full_match:
        minutes = int(full_match.group(1))
        seconds = int(full_match.group(2))
        return minutes * 60 + seconds
    
    return None


def is_similar_album_title(title1: str, title2: str, threshold: float = 0.85) -> bool:
    """
    Vérifie si deux titres d'albums sont similaires.
    
    Args:
        title1: Premier titre
        title2: Deuxième titre
        threshold: Seuil de similarité
        
    Returns:
        True si les titres sont similaires
    """
    return calculate_similarity(title1, title2) >= threshold


def extract_year_from_text(text: str) -> Optional[int]:
    """
    Extrait une année d'un texte.
    
    Args:
        text: Texte contenant potentiellement une année
        
    Returns:
        Année extraite ou None
    """
    if not text:
        return None
    
    # Chercher une année entre 1900 et 2030
    year_match = re.search(r'\b(19\d{2}|20[0-3]\d)\b', text)
    if year_match:
        return int(year_match.group(1))
    
    return None


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Tronque un texte à une longueur maximale.
    
    Args:
        text: Texte à tronquer
        max_length: Longueur maximale
        suffix: Suffixe à ajouter si tronqué
        
    Returns:
        Texte tronqué
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def contains_explicit_content_markers(text: str) -> bool:
    """
    Vérifie si un texte contient des marqueurs de contenu explicite.
    
    Args:
        text: Texte à vérifier
        
    Returns:
        True si contient des marqueurs explicites
    """
    explicit_markers = [
        'explicit', 'parental advisory', 'nsfw', 'mature content',
        'adult content', 'strong language', 'uncensored'
    ]
    
    text_lower = text.lower()
    return any(marker in text_lower for marker in explicit_markers)


def generate_search_variants(text: str) -> List[str]:
    """
    Génère des variantes de recherche pour un texte.
    
    Args:
        text: Texte original
        
    Returns:
        Liste des variantes de recherche
    """
    variants = [text]
    
    # Version normalisée
    normalized = normalize_text(text)
    if normalized and normalized != text:
        variants.append(normalized)
    
    # Version sans accents
    no_accents = remove_accents(text)
    if no_accents and no_accents != text:
        variants.append(no_accents)
    
    # Version sans caractères spéciaux
    no_special = re.sub(r'[^\w\s]', '', text)
    if no_special and no_special != text:
        variants.append(no_special)
    
    # Supprimer les doublons en gardant l'ordre
    unique_variants = []
    for variant in variants:
        if variant and variant not in unique_variants:
            unique_variants.append(variant)
    
    return unique_variants