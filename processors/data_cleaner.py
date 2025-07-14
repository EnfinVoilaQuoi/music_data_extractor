# processors/data_cleaner.py
import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from dataclasses import dataclass
from difflib import SequenceMatcher

from ..models.entities import Track, Credit, Artist, Album
from ..models.enums import CreditType, CreditCategory, DataSource
from ..core.database import Database
from ..config.settings import settings
from ..utils.text_utils import (
    clean_text, normalize_title, clean_artist_name, 
    similarity_ratio, extract_featured_artists_from_title,
    clean_credit_role, validate_artist_name
)

@dataclass
class CleaningStats:
    """Statistiques du nettoyage"""
    tracks_processed: int = 0
    tracks_cleaned: int = 0
    credits_processed: int = 0
    credits_cleaned: int = 0
    credits_removed: int = 0
    duplicates_removed: int = 0
    names_normalized: int = 0
    errors_fixed: int = 0

class DataCleaner:
    """
    Processeur de nettoyage des données.
    
    Responsabilités :
    - Normalisation des noms d'artistes et de morceaux
    - Nettoyage et validation des crédits
    - Suppression des doublons
    - Correction des erreurs de saisie
    - Standardisation des formats
    """
    
    def __init__(self, database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        self.database = database or Database()
        
        # Configuration du nettoyage
        self.config = {
            'remove_duplicates': settings.get('cleaning.remove_duplicates', True),
            'normalize_names': settings.get('cleaning.normalize_names', True),
            'fix_encoding': settings.get('cleaning.fix_encoding', True),
            'validate_credits': settings.get('cleaning.validate_credits', True),
            'merge_similar_names': settings.get('cleaning.merge_similar_names', True),
            'similarity_threshold': settings.get('cleaning.similarity_threshold', 0.9)
        }
        
        # Patterns de nettoyage
        self.cleaning_patterns = self._load_cleaning_patterns()
        
        # Cache pour éviter les recalculs
        self._normalized_names_cache = {}
        
        self.logger.info("DataCleaner initialisé")
    
    def _load_cleaning_patterns(self) -> Dict[str, Any]:
        """Charge les patterns de nettoyage"""
        return {
            'name_patterns': {
                # Suppression des caractères indésirables
                'unwanted_chars': re.compile(r'[^\w\s\-\.\'\(\)&]'),
                # Espaces multiples
                'multiple_spaces': re.compile(r'\s+'),
                # Parenthèses vides
                'empty_parentheses': re.compile(r'\(\s*\)'),
                # Caractères de contrôle
                'control_chars': re.compile(r'[\x00-\x1f\x7f-\x9f]')
            },
            'credit_patterns': {
                # Patterns à nettoyer dans les crédits
                'remove_prefixes': [
                    r'^(by\s+|par\s+|prod\.?\s*by\s+|produced\s*by\s+)',
                    r'^(mixed\s*by\s+|mixé\s*par\s+)',
                    r'^(mastered\s*by\s+|masterisé\s*par\s+)'
                ],
                'remove_suffixes': [
                    r'\s*\(uncredited\)$',
                    r'\s*\[uncredited\]$',
                    r'\s*\(non\s*crédité\)$'
                ]
            },
            'title_patterns': {
                # Nettoyage des titres de morceaux
                'feat_patterns': [
                    r'\s+feat\.?\s+',
                    r'\s+ft\.?\s+',
                    r'\s+featuring\s+',
                    r'\s+avec\s+'
                ]
            }
        }
    
    def clean_artist_data(self, artist_id: int) -> CleaningStats:
        """
        Nettoie toutes les données d'un artiste.
        
        Args:
            artist_id: ID de l'artiste à nettoyer
            
        Returns:
            CleaningStats: Statistiques du nettoyage
        """
        stats = CleaningStats()
        
        try:
            self.logger.info(f"🧹 Début du nettoyage des données pour l'artiste {artist_id}")
            
            # Récupération des données
            tracks = self.database.get_tracks_by_artist_id(artist_id)
            stats.tracks_processed = len(tracks)
            
            # Nettoyage des morceaux
            for track in tracks:
                track_cleaned = self._clean_track(track, stats)
                if track_cleaned:
                    stats.tracks_cleaned += 1
                    self.database.update_track(track)
            
            # Nettoyage global des crédits
            if self.config['remove_duplicates']:
                duplicates_removed = self._remove_duplicate_credits(artist_id)
                stats.duplicates_removed = duplicates_removed
            
            # Fusion des noms similaires
            if self.config['merge_similar_names']:
                names_merged = self._merge_similar_credit_names(artist_id)
                stats.names_normalized += names_merged
            
            self.logger.info(
                f"✅ Nettoyage terminé pour l'artiste {artist_id}: "
                f"{stats.tracks_cleaned}/{stats.tracks_processed} morceaux nettoyés, "
                f"{stats.credits_cleaned} crédits nettoyés, "
                f"{stats.duplicates_removed} doublons supprimés"
            )
            
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du nettoyage de l'artiste {artist_id}: {e}")
            return stats
    
    def _clean_track(self, track: Track, stats: CleaningStats) -> bool:
        """Nettoie un morceau spécifique"""
        cleaned = False
        
        try:
            # Nettoyage du titre
            original_title = track.title
            cleaned_title = self._clean_track_title(track.title)
            if cleaned_title != original_title:
                track.title = cleaned_title
                cleaned = True
                stats.errors_fixed += 1
            
            # Nettoyage du nom d'artiste
            if track.artist_name:
                original_artist = track.artist_name
                cleaned_artist = self._clean_person_name(track.artist_name)
                if cleaned_artist != original_artist:
                    track.artist_name = cleaned_artist
                    cleaned = True
                    stats.errors_fixed += 1
            
            # Nettoyage du titre d'album
            if track.album_title:
                original_album = track.album_title
                cleaned_album = self._clean_album_title(track.album_title)
                if cleaned_album != original_album:
                    track.album_title = cleaned_album
                    cleaned = True
                    stats.errors_fixed += 1
            
            # Nettoyage des featuring artists
            if track.featuring_artists:
                cleaned_features = []
                for featuring in track.featuring_artists:
                    cleaned_featuring = self._clean_person_name(featuring)
                    if cleaned_featuring and cleaned_featuring not in cleaned_features:
                        cleaned_features.append(cleaned_featuring)
                
                if cleaned_features != track.featuring_artists:
                    track.featuring_artists = cleaned_features
                    cleaned = True
                    stats.errors_fixed += 1
            
            # Nettoyage des crédits
            credits_cleaned = self._clean_track_credits(track, stats)
            if credits_cleaned:
                cleaned = True
            
            # Validation et correction des données numériques
            numeric_cleaned = self._clean_numeric_data(track)
            if numeric_cleaned:
                cleaned = True
                stats.errors_fixed += 1
            
            if cleaned:
                track.updated_at = datetime.now()
            
            return cleaned
            
        except Exception as e:
            self.logger.warning(f"Erreur nettoyage track '{track.title}': {e}")
            return False
    
    def _clean_track_title(self, title: str) -> str:
        """Nettoie le titre d'un morceau"""
        if not title:
            return ""
        
        cleaned = title.strip()
        
        # Suppression des caractères de contrôle
        cleaned = self.cleaning_patterns['name_patterns']['control_chars'].sub('', cleaned)
        
        # Correction de l'encodage courant
        if self.config['fix_encoding']:
            cleaned = self._fix_encoding_issues(cleaned)
        
        # Normalisation des espaces
        cleaned = self.cleaning_patterns['name_patterns']['multiple_spaces'].sub(' ', cleaned)
        
        # Suppression des parenthèses vides
        cleaned = self.cleaning_patterns['name_patterns']['empty_parentheses'].sub('', cleaned)
        
        # Nettoyage spécifique aux titres
        cleaned = self._clean_title_featuring(cleaned)
        
        return cleaned.strip()
    
    def _clean_person_name(self, name: str) -> str:
        """Nettoie le nom d'une personne (artiste, créditeur)"""
        if not name:
            return ""
        
        # Utiliser le cache si disponible
        if name in self._normalized_names_cache:
            return self._normalized_names_cache[name]
        
        cleaned = name.strip()
        
        # Suppression des caractères de contrôle
        cleaned = self.cleaning_patterns['name_patterns']['control_chars'].sub('', cleaned)
        
        # Correction de l'encodage
        if self.config['fix_encoding']:
            cleaned = self._fix_encoding_issues(cleaned)
        
        # Suppression des préfixes de crédit
        for pattern in self.cleaning_patterns['credit_patterns']['remove_prefixes']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()
        
        # Suppression des suffixes
        for pattern in self.cleaning_patterns['credit_patterns']['remove_suffixes']:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()
        
        # Normalisation des espaces
        cleaned = self.cleaning_patterns['name_patterns']['multiple_spaces'].sub(' ', cleaned)
        
        # Capitalisation appropriée
        cleaned = self._normalize_capitalization(cleaned)
        
        # Mise en cache
        self._normalized_names_cache[name] = cleaned
        
        return cleaned
    
    def _clean_album_title(self, title: str) -> str:
        """Nettoie le titre d'un album"""
        if not title:
            return ""
        
        cleaned = title.strip()
        
        # Suppression des caractères de contrôle
        cleaned = self.cleaning_patterns['name_patterns']['control_chars'].sub('', cleaned)
        
        # Correction de l'encodage
        if self.config['fix_encoding']:
            cleaned = self._fix_encoding_issues(cleaned)
        
        # Normalisation des espaces
        cleaned = self.cleaning_patterns['name_patterns']['multiple_spaces'].sub(' ', cleaned)
        
        return cleaned.strip()
    
    def _clean_title_featuring(self, title: str) -> str:
        """Nettoie les featuring dans les titres"""
        if not title:
            return ""
        
        # Utiliser la fonction de text_utils pour extraire et nettoyer
        clean_title, featuring_artists = extract_featured_artists_from_title(title)
        return clean_title
    
    def _fix_encoding_issues(self, text: str) -> str:
        """Corrige les problèmes d'encodage courants"""
        if not text:
            return ""
        
        # Corrections d'encodage courantes
        encoding_fixes = {
            'Ã¡': 'á', 'Ã©': 'é', 'Ã­': 'í', 'Ã³': 'ó', 'Ãº': 'ú',
            'Ã ': 'à', 'Ã¨': 'è', 'Ã¬': 'ì', 'Ã²': 'ò', 'Ã¹': 'ù',
            'Ã¢': 'â', 'Ãª': 'ê', 'Ã®': 'î', 'Ã´': 'ô', 'Ã»': 'û',
            'Ã§': 'ç', 'Ã±': 'ñ', 'Ã¼': 'ü', 'ÃŸ': 'ß',
            'â€™': "'", 'â€œ': '"', 'â€': '"', 'â€"': '–', 'â€"': '—'
        }
        
        for wrong, correct in encoding_fixes.items():
            text = text.replace(wrong, correct)
        
        return text
    
    def _normalize_capitalization(self, name: str) -> str:
        """Normalise la capitalisation des noms"""
        if not name:
            return ""
        
        # Mots qui doivent rester en minuscules
        lowercase_words = {'de', 'la', 'le', 'du', 'des', 'and', 'the', 'of', 'feat', 'ft'}
        
        words = name.split()
        normalized_words = []
        
        for i, word in enumerate(words):
            # Premier mot toujours en majuscule
            if i == 0:
                normalized_words.append(word.capitalize())
            # Mots spéciaux en minuscules
            elif word.lower() in lowercase_words:
                normalized_words.append(word.lower())
            # Autres mots en majuscule
            else:
                normalized_words.append(word.capitalize())
        
        return ' '.join(normalized_words)
    
    def _clean_track_credits(self, track: Track, stats: CleaningStats) -> bool:
        """Nettoie les crédits d'un track"""
        cleaned = False
        credits_to_remove = []
        
        for i, credit in enumerate(track.credits):
            stats.credits_processed += 1
            
            # Nettoyage du nom de la personne
            original_name = credit.person_name
            cleaned_name = self._clean_person_name(credit.person_name)
            
            # Validation du nom nettoyé
            if not validate_artist_name(cleaned_name):
                credits_to_remove.append(i)
                stats.credits_removed += 1
                continue
            
            if cleaned_name != original_name:
                credit.person_name = cleaned_name
                cleaned = True
                stats.credits_cleaned += 1
            
            # Nettoyage du détail d'instrument
            if credit.instrument:
                original_instrument = credit.instrument
                cleaned_instrument = self._clean_instrument_detail(credit.instrument)
                if cleaned_instrument != original_instrument:
                    credit.instrument = cleaned_instrument
                    cleaned = True
            
            # Validation et correction du type de crédit
            if self._validate_and_fix_credit_type(credit):
                cleaned = True
                stats.credits_cleaned += 1
        
        # Suppression des crédits invalides (en ordre inverse pour préserver les index)
        for i in reversed(credits_to_remove):
            track.credits.pop(i)
        
        return cleaned
    
    def _clean_instrument_detail(self, instrument: str) -> str:
        """Nettoie les détails d'instrument"""
        if not instrument:
            return ""
        
        cleaned = instrument.strip().lower()
        
        # Normalisation des instruments communs
        instrument_mappings = {
            'keys': 'keyboard',
            'synth': 'synthesizer',
            'drums': 'drums',
            'percussion': 'drums',
            'guitar': 'guitar',
            'bass': 'bass guitar',
            'sax': 'saxophone',
            'vocals': 'vocals'
        }
        
        return instrument_mappings.get(cleaned, cleaned)
    
    def _validate_and_fix_credit_type(self, credit: Credit) -> bool:
        """Valide et corrige le type de crédit"""
        if not credit.person_name:
            return False
        
        # Utiliser clean_credit_role de text_utils
        normalized_role = clean_credit_role(credit.credit_type.value)
        
        # Mapping vers les types d'enum valides
        role_to_type = {
            'producer': CreditType.PRODUCER,
            'executive_producer': CreditType.EXECUTIVE_PRODUCER,
            'co_producer': CreditType.CO_PRODUCER,
            'mixing': CreditType.MIXING,
            'mastering': CreditType.MASTERING,
            'recording': CreditType.RECORDING,
            'featuring': CreditType.FEATURING,
            'songwriter': CreditType.SONGWRITER,
            'composer': CreditType.COMPOSER,
            'guitar': CreditType.GUITAR,
            'piano': CreditType.PIANO,
            'drums': CreditType.DRUMS,
            'bass': CreditType.BASS,
            'saxophone': CreditType.SAXOPHONE
        }
        
        new_type = role_to_type.get(normalized_role)
        if new_type and new_type != credit.credit_type:
            credit.credit_type = new_type
            return True
        
        return False
    
    def _clean_numeric_data(self, track: Track) -> bool:
        """Valide et corrige les données numériques"""
        cleaned = False
        
        # Validation BPM
        if track.bpm:
            if track.bpm < 40 or track.bpm > 300:
                self.logger.warning(f"BPM suspect pour '{track.title}': {track.bpm}")
                # Ne pas supprimer, mais signaler
            elif track.bpm < 60:
                # Doubler les BPM trop bas (erreur courante)
                track.bpm *= 2
                cleaned = True
        
        # Validation durée
        if track.duration_seconds:
            if track.duration_seconds < 10:
                self.logger.warning(f"Durée trop courte pour '{track.title}': {track.duration_seconds}s")
            elif track.duration_seconds > 1800:  # 30 minutes
                self.logger.warning(f"Durée trop longue pour '{track.title}': {track.duration_seconds}s")
        
        # Validation track number
        if track.track_number and track.track_number < 0:
            track.track_number = None
            cleaned = True
        
        return cleaned
    
    def _remove_duplicate_credits(self, artist_id: int) -> int:
        """Supprime les crédits en double pour un artiste"""
        duplicates_removed = 0
        
        try:
            tracks = self.database.get_tracks_by_artist_id(artist_id)
            
            for track in tracks:
                # Grouper les crédits par (nom, type)
                credit_groups = {}
                for credit in track.credits:
                    key = (credit.person_name.lower(), credit.credit_type)
                    if key not in credit_groups:
                        credit_groups[key] = []
                    credit_groups[key].append(credit)
                
                # Garder seulement le premier de chaque groupe
                unique_credits = []
                for credits_group in credit_groups.values():
                    unique_credits.append(credits_group[0])  # Garder le premier
                    duplicates_removed += len(credits_group) - 1
                
                # Mettre à jour si des doublons ont été trouvés
                if len(unique_credits) != len(track.credits):
                    track.credits = unique_credits
                    self.database.update_track(track)
            
            return duplicates_removed
            
        except Exception as e:
            self.logger.error(f"Erreur suppression doublons pour artiste {artist_id}: {e}")
            return 0
    
    def _merge_similar_credit_names(self, artist_id: int) -> int:
        """Fusionne les noms de crédits similaires"""
        names_merged = 0
        
        try:
            tracks = self.database.get_tracks_by_artist_id(artist_id)
            
            # Collecter tous les noms de crédits
            all_names = set()
            for track in tracks:
                for credit in track.credits:
                    if credit.person_name:
                        all_names.add(credit.person_name)
            
            # Grouper les noms similaires
            name_groups = self._group_similar_names(list(all_names))
            
            # Créer un mapping de correction
            name_corrections = {}
            for group in name_groups:
                if len(group) > 1:
                    # Prendre le nom le plus fréquent comme référence
                    canonical_name = max(group, key=len)  # ou une autre logique
                    for name in group:
                        if name != canonical_name:
                            name_corrections[name] = canonical_name
                            names_merged += 1
            
            # Appliquer les corrections
            if name_corrections:
                for track in tracks:
                    track_modified = False
                    for credit in track.credits:
                        if credit.person_name in name_corrections:
                            credit.person_name = name_corrections[credit.person_name]
                            track_modified = True
                    
                    if track_modified:
                        self.database.update_track(track)
            
            return names_merged
            
        except Exception as e:
            self.logger.error(f"Erreur fusion noms similaires pour artiste {artist_id}: {e}")
            return 0
    
    def _group_similar_names(self, names: List[str]) -> List[List[str]]:
        """Groupe les noms similaires"""
        groups = []
        threshold = self.config['similarity_threshold']
        
        for name in names:
            added_to_group = False
            
            for group in groups:
                # Vérifier la similarité avec le premier nom du groupe
                if similarity_ratio(name, group[0]) >= threshold:
                    group.append(name)
                    added_to_group = True
                    break
            
            if not added_to_group:
                groups.append([name])
        
        return groups
    
    def clean_all_data(self) -> CleaningStats:
        """Nettoie toutes les données de la base"""
        total_stats = CleaningStats()
        
        try:
            self.logger.info("🧹 Début du nettoyage global de la base de données")
            
            # Obtenir tous les artistes
            # Note: Cette méthode devrait être ajoutée à Database
            # Pour l'instant, on peut utiliser une requête directe
            with self.database.get_connection() as conn:
                cursor = conn.execute("SELECT id FROM artists")
                artist_ids = [row['id'] for row in cursor.fetchall()]
            
            for artist_id in artist_ids:
                stats = self.clean_artist_data(artist_id)
                
                # Agréger les statistiques
                total_stats.tracks_processed += stats.tracks_processed
                total_stats.tracks_cleaned += stats.tracks_cleaned
                total_stats.credits_processed += stats.credits_processed
                total_stats.credits_cleaned += stats.credits_cleaned
                total_stats.credits_removed += stats.credits_removed
                total_stats.duplicates_removed += stats.duplicates_removed
                total_stats.names_normalized += stats.names_normalized
                total_stats.errors_fixed += stats.errors_fixed
            
            self.logger.info(
                f"✅ Nettoyage global terminé: "
                f"{total_stats.tracks_cleaned}/{total_stats.tracks_processed} morceaux nettoyés, "
                f"{total_stats.credits_cleaned} crédits nettoyés, "
                f"{total_stats.duplicates_removed} doublons supprimés"
            )
            
            return total_stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du nettoyage global: {e}")
            return total_stats
    
    def validate_track_integrity(self, track: Track) -> List[str]:
        """Valide l'intégrité d'un track et retourne les problèmes détectés"""
        issues = []
        
        # Validation du titre
        if not track.title or len(track.title.strip()) < 1:
            issues.append("Titre manquant ou vide")
        
        # Validation de l'artiste
        if not track.artist_name or not validate_artist_name(track.artist_name):
            issues.append("Nom d'artiste invalide")
        
        # Validation de la durée
        if track.duration_seconds:
            if track.duration_seconds < 30:
                issues.append("Durée suspecte (< 30s)")
            elif track.duration_seconds > 1800:
                issues.append("Durée suspecte (> 30min)")
        
        # Validation BPM
        if track.bpm:
            if track.bpm < 40 or track.bpm > 300:
                issues.append("BPM suspect")
        
        # Validation des crédits
        if not track.credits:
            issues.append("Aucun crédit trouvé")
        else:
            # Vérifier qu'il y a au moins un producteur
            has_producer = any(
                credit.credit_category == CreditCategory.PRODUCER 
                for credit in track.credits
            )
            if not has_producer:
                issues.append("Aucun producteur identifié")
        
        return issues
    
    def get_cleaning_report(self, artist_id: Optional[int] = None) -> Dict[str, Any]:
        """Génère un rapport de nettoyage"""
        try:
            if artist_id:
                tracks = self.database.get_tracks_by_artist_id(artist_id)
            else:
                # Obtenir tous les tracks (méthode à ajouter à Database)
                with self.database.get_connection() as conn:
                    cursor = conn.execute("SELECT * FROM tracks")
                    tracks = [self.database._row_to_track(row) for row in cursor.fetchall()]
            
            report = {
                'total_tracks': len(tracks),
                'tracks_with_issues': 0,
                'common_issues': {},
                'quality_distribution': {
                    'excellent': 0,
                    'good': 0,
                    'average': 0,
                    'poor': 0
                },
                'missing_data': {
                    'bpm': 0,
                    'duration': 0,
                    'producer': 0,
                    'album': 0
                }
            }
            
            for track in tracks:
                issues = self.validate_track_integrity(track)
                
                if issues:
                    report['tracks_with_issues'] += 1
                    
                    # Compter les problèmes communs
                    for issue in issues:
                        report['common_issues'][issue] = report['common_issues'].get(issue, 0) + 1
                
                # Statistiques des données manquantes
                if not track.bpm:
                    report['missing_data']['bpm'] += 1
                if not track.duration_seconds:
                    report['missing_data']['duration'] += 1
                if not any(c.credit_category == CreditCategory.PRODUCER for c in track.credits):
                    report['missing_data']['producer'] += 1
                if not track.album_title:
                    report['missing_data']['album'] += 1
                
                # Distribution de qualité (simple)
                issue_count = len(issues)
                if issue_count == 0:
                    report['quality_distribution']['excellent'] += 1
                elif issue_count <= 1:
                    report['quality_distribution']['good'] += 1
                elif issue_count <= 3:
                    report['quality_distribution']['average'] += 1
                else:
                    report['quality_distribution']['poor'] += 1
            
            return report
            
        except Exception as e:
            self.logger.error(f"Erreur génération rapport de nettoyage: {e}")
            return {}
