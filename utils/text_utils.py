# utils/text_utils.py
import re
import unicodedata
from typing import Optional, List, Dict, Set
import logging

logger = logging.getLogger(__name__)


def clean_artist_name(name: str) -> str:
    """
    Nettoie et normalise un nom d'artiste.
    
    Args:
        name: Nom d'artiste brut
        
    Returns:
        Nom d'artiste nettoyé
    """
    if not name:
        return ""
    
    # Suppression des espaces en début/fin
    name = name.strip()
    
    # Normalisation Unicode (supprime les accents pour la comparaison)
    name = unicodedata.normalize('NFKD', name)
    
    # Suppression des caractères de contrôle
    name = ''.join(char for char in name if not unicodedata.category(char).startswith('C'))
    
    # Remplacement des espaces multiples par un seul
    name = re.sub(r'\s+', ' ', name)
    
    # Suppression des parenthèses avec contenu générique
    patterns_to_remove = [
        r'\s*\(Official.*?\)',  # (Official Artist)
        r'\s*\(Verified.*?\)',  # (Verified)
        r'\s*\[Official.*?\]',  # [Official Artist]
        r'\s*\[Verified.*?\]',  # [Verified]
    ]
    
    for pattern in patterns_to_remove:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    return name.strip()


def normalize_title(title: str) -> str:
    """
    Normalise un titre de morceau pour la détection de doublons.
    
    Args:
        title: Titre brut
        
    Returns:
        Titre normalisé
    """
    if not title:
        return ""
    
    # Conversion en minuscules
    title = title.lower().strip()
    
    # Suppression des featuring/feat/ft
    feat_patterns = [
        r'\s*\(feat\.?\s+[^)]+\)',
        r'\s*\(featuring\s+[^)]+\)',
        r'\s*\(ft\.?\s+[^)]+\)',
        r'\s*feat\.?\s+.*$',
        r'\s*featuring\s+.*$',
        r'\s*ft\.?\s+.*$',
    ]
    
    for pattern in feat_patterns:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    
    # Suppression des versions/remix/remaster
    version_patterns = [
        r'\s*\(.*?version.*?\)',
        r'\s*\(.*?remix.*?\)',
        r'\s*\(.*?remaster.*?\)',
        r'\s*\(.*?edit.*?\)',
        r'\s*\(live.*?\)',
        r'\s*\(acoustic.*?\)',
        r'\s*\(instrumental.*?\)',
        r'\s*\(clean.*?\)',
        r'\s*\(explicit.*?\)',
    ]
    
    for pattern in version_patterns:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    
    # Suppression de la ponctuation non significative
    title = re.sub(r'[^\w\s]', '', title)
    
    # Remplacement des espaces multiples
    title = re.sub(r'\s+', ' ', title)
    
    return title.strip()


def extract_featured_artists_from_title(title: str) -> tuple[str, List[str]]:
    """
    Extrait les artistes invités du titre d'un morceau.
    
    Args:
        title: Titre complet avec featuring
        
    Returns:
        tuple: (titre_nettoyé, liste_artistes_invités)
    """
    original_title = title.strip()
    featured_artists = []
    
    # Patterns pour détecter les featuring
    feat_patterns = [
        r'\s*\(feat\.?\s+([^)]+)\)',
        r'\s*\(featuring\s+([^)]+)\)',
        r'\s*\(ft\.?\s+([^)]+)\)',
        r'\s*feat\.?\s+(.+)$',
        r'\s*featuring\s+(.+)$',
        r'\s*ft\.?\s+(.+)$',
    ]
    
    clean_title = title
    
    for pattern in feat_patterns:
        match = re.search(pattern, title, flags=re.IGNORECASE)
        if match:
            # Extraction des artistes
            artists_str = match.group(1)
            artists = parse_artist_list(artists_str)
            featured_artists.extend(artists)
            
            # Suppression du featuring du titre
            clean_title = re.sub(pattern, '', title, flags=re.IGNORECASE).strip()
            break
    
    # Déduplication des artistes
    featured_artists = list(dict.fromkeys(featured_artists))  # Préserve l'ordre
    
    return clean_title, featured_artists


def parse_artist_list(artists_str: str) -> List[str]:
    """
    Parse une chaîne contenant plusieurs artistes.
    
    Args:
        artists_str: Chaîne avec les artistes (ex: "Artist1, Artist2 & Artist3")
        
    Returns:
        Liste des noms d'artistes
    """
    if not artists_str:
        return []
    
    # Séparateurs communs
    separators = [',', '&', 'and', '+', 'x', '×']
    
    # Remplacement des séparateurs par des virgules
    for sep in separators:
        if sep in ['and']:
            artists_str = re.sub(f' {sep} ', ',', artists_str, flags=re.IGNORECASE)
        else:
            artists_str = artists_str.replace(sep, ',')
    
    # Division et nettoyage
    artists = [artist.strip() for artist in artists_str.split(',')]
    artists = [artist for artist in artists if artist and len(artist) > 1]
    
    return artists


def clean_album_title(title: str) -> str:
    """
    Nettoie un titre d'album.
    
    Args:
        title: Titre d'album brut
        
    Returns:
        Titre nettoyé
    """
    if not title:
        return ""
    
    title = title.strip()
    
    # Suppression des éditions spéciales
    edition_patterns = [
        r'\s*\(Deluxe.*?\)',
        r'\s*\(Extended.*?\)',
        r'\s*\(Special.*?\)',
        r'\s*\(Limited.*?\)',
        r'\s*\(Collector.*?\)',
        r'\s*\(Anniversary.*?\)',
        r'\s*\(Remaster.*?\)',
        r'\s*\(Re-?issue.*?\)',
    ]
    
    for pattern in edition_patterns:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    
    return title.strip()


def detect_language(text: str) -> str:
    """
    Détecte la langue d'un texte (français/anglais principalement).
    
    Args:
        text: Texte à analyser
        
    Returns:
        Code de langue ('fr', 'en', 'unknown')
    """
    if not text:
        return 'unknown'
    
    text_lower = text.lower()
    
    # Mots français communs
    french_words = {
        'le', 'la', 'les', 'de', 'du', 'des', 'et', 'est', 'avec', 'dans', 
        'pour', 'sur', 'par', 'une', 'un', 'ce', 'cette', 'qui', 'que',
        'où', 'quand', 'comment', 'pourquoi', 'tout', 'tous', 'toute',
        'être', 'avoir', 'faire', 'dire', 'aller', 'voir', 'savoir'
    }
    
    # Mots anglais communs
    english_words = {
        'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
        'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
        'before', 'after', 'above', 'below', 'between', 'among', 'this',
        'that', 'these', 'those', 'what', 'where', 'when', 'why', 'how'
    }
    
    words = re.findall(r'\b\w+\b', text_lower)
    
    if not words:
        return 'unknown'
    
    french_score = sum(1 for word in words if word in french_words)
    english_score = sum(1 for word in words if word in english_words)
    
    if french_score > english_score and french_score > 0:
        return 'fr'
    elif english_score > french_score and english_score > 0:
        return 'en'
    else:
        return 'unknown'


def similarity_ratio(str1: str, str2: str) -> float:
    """
    Calcule un ratio de similarité entre deux chaînes.
    
    Args:
        str1, str2: Chaînes à comparer
        
    Returns:
        Ratio de similarité entre 0 et 1
    """
    if not str1 or not str2:
        return 0.0
    
    str1 = str1.lower().strip()
    str2 = str2.lower().strip()
    
    if str1 == str2:
        return 1.0
    
    # Algorithme simple basé sur les caractères communs
    len1, len2 = len(str1), len(str2)
    max_len = max(len1, len2)
    
    if max_len == 0:
        return 1.0
    
    # Comptage des caractères communs
    common_chars = 0
    str2_chars = list(str2)
    
    for char in str1:
        if char in str2_chars:
            str2_chars.remove(char)
            common_chars += 1
    
    return common_chars / max_len


def extract_year_from_date(date_str: str) -> Optional[int]:
    """
    Extrait l'année d'une chaîne de date.
    
    Args:
        date_str: Chaîne contenant une date
        
    Returns:
        Année extraite ou None
    """
    if not date_str:
        return None
    
    # Recherche d'une année (4 chiffres)
    year_match = re.search(r'\b(19|20)\d{2}\b', str(date_str))
    
    if year_match:
        try:
            return int(year_match.group(0))
        except ValueError:
            pass
    
    return None


def clean_credit_role(role: str) -> str:
    """
    Nettoie et normalise un rôle de crédit.
    
    Args:
        role: Rôle brut
        
    Returns:
        Rôle nettoyé et normalisé
    """
    if not role:
        return ""
    
    role = role.strip().lower()
    
    # Mappings de normalisation
    role_mappings = {
        'prod': 'producer',
        'production': 'producer',
        'produced by': 'producer',
        'executive prod': 'executive_producer',
        'exec producer': 'executive_producer',
        'co-producer': 'co_producer',
        'additional prod': 'additional_production',
        'mix': 'mixing',
        'mixed by': 'mixing',
        'master': 'mastering',
        'mastered by': 'mastering',
        'engineer': 'engineering',
        'engineered by': 'engineering',
        'rec': 'recording',
        'recorded by': 'recording',
        'songwriter': 'songwriter',
        'written by': 'songwriter',
        'composer': 'composer',
        'composed by': 'composer',
        'feat': 'featuring',
        'featuring': 'featuring',
        'ft': 'featuring',
        'vocals': 'lead_vocals',
        'lead vocal': 'lead_vocals',
        'backing vocal': 'backing_vocals',
        'background vocals': 'backing_vocals',
    }
    
    # Application des mappings
    normalized_role = role_mappings.get(role, role)
    
    # Nettoyage final
    normalized_role = re.sub(r'[^\w_]', '_', normalized_role)
    normalized_role = re.sub(r'_+', '_', normalized_role)
    normalized_role = normalized_role.strip('_')
    
    return normalized_role


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


def validate_artist_name(name: str) -> bool:
    """
    Valide qu'un nom d'artiste est acceptable.
    
    Args:
        name: Nom à valider
        
    Returns:
        True si valide
    """
    if not name or len(name.strip()) < 2:
        return False
    
    # Patterns à rejeter
    invalid_patterns = [
        r'^unknown\s*artist',
        r'^various\s*artists?',
        r'^compilation',
        r'^soundtrack',
        r'^\[.*\]$',  # Noms entre crochets uniquement
        r'^\d+$',     # Nombres uniquement
    ]
    
    name_lower = name.lower().strip()
    
    for pattern in invalid_patterns:
        if re.match(pattern, name_lower):
            return False
    
    return True


def format_duration(duration_ms: Optional[int]) -> str:
    """
    Formate une durée en millisecondes en format MM:SS.
    
    Args:
        duration_ms: Durée en millisecondes
        
    Returns:
        Durée formatée (ex: "3:45")
    """
    if not duration_ms or duration_ms <= 0:
        return "0:00"
    
    total_seconds = duration_ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    
    return f"{minutes}:{seconds:02d}"


def parse_duration(duration_str: str) -> Optional[int]:
    """
    Parse une durée au format "MM:SS" vers millisecondes.
    
    Args:
        duration_str: Durée au format texte
        
    Returns:
        Durée en millisecondes ou None
    """
    if not duration_str:
        return None
    
    # Pattern MM:SS ou M:SS
    match = re.match(r'^(\d{1,2}):(\d{2})$', duration_str.strip())
    
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        
        if seconds < 60:  # Validation
            return (minutes * 60 + seconds) * 1000
    
    return None
