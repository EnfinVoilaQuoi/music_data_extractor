# processors/duplicate_detector.py
import logging
import re
from typing import Dict, List, Optional, Any, Set, Tuple, Union
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from difflib import SequenceMatcher

from ..models.entities import Track, Credit, Artist, Album
from ..models.enums import CreditType, CreditCategory, DataSource
from ..core.database import Database
from ..config.settings import settings
from ..utils.text_utils import (
    normalize_title, clean_artist_name, similarity_ratio,
    extract_featured_artists_from_title
)

class DuplicateType(Enum):
    """Types de doublons détectés"""
    EXACT = "exact"                    # Doublons exacts
    SIMILAR_TITLE = "similar_title"    # Titres similaires
    SIMILAR_ARTIST = "similar_artist"  # Artistes similaires
    REMIX_VARIANT = "remix_variant"    # Variantes/remixes
    FEATURING_VARIANT = "featuring_variant"  # Variantes avec featuring différent
    CREDIT_DUPLICATE = "credit_duplicate"    # Crédits en double
    ALBUM_DUPLICATE = "album_duplicate"      # Albums en double

class MatchConfidence(Enum):
    """Niveaux de confiance pour les matches"""
    CERTAIN = "certain"        # 95-100% - Quasi certain
    HIGH = "high"             # 85-94% - Haute confiance
    MEDIUM = "medium"         # 70-84% - Confiance moyenne
    LOW = "low"              # 50-69% - Faible confiance
    UNCERTAIN = "uncertain"   # <50% - Incertain

@dataclass
class DuplicateMatch:
    """Représente une correspondance de doublon"""
    entity1_id: int
    entity2_id: int
    duplicate_type: DuplicateType
    confidence: MatchConfidence
    similarity_score: float  # Score de 0 à 1
    details: Dict[str, Any]
    suggested_action: str
    entity_type: str  # 'track', 'artist', 'album', 'credit'

@dataclass
class DeduplicationStats:
    """Statistiques de déduplication"""
    total_processed: int = 0
    exact_duplicates: int = 0
    similar_duplicates: int = 0
    potential_duplicates: int = 0
    credits_merged: int = 0
    tracks_merged: int = 0
    artists_merged: int = 0
    albums_merged: int = 0

class DuplicateDetector:
    """
    Détecteur de doublons pour les données musicales.
    
    Responsabilités :
    - Détection de doublons exacts et similaires
    - Analyse de similarité avancée
    - Suggestion d'actions de fusion
    - Déduplication automatique (selon configuration)
    """
    
    def __init__(self, database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        self.database = database or Database()
        
        # Configuration de détection
        self.config = {
            'exact_match_threshold': settings.get('deduplication.exact_threshold', 1.0),
            'high_similarity_threshold': settings.get('deduplication.high_threshold', 0.9),
            'medium_similarity_threshold': settings.get('deduplication.medium_threshold', 0.75),
            'low_similarity_threshold': settings.get('deduplication.low_threshold', 0.6),
            'auto_merge_exact': settings.get('deduplication.auto_merge_exact', False),
            'auto_merge_high_similarity': settings.get('deduplication.auto_merge_high', False),
            'ignore_featuring_differences': settings.get('deduplication.ignore_featuring', True),
            'normalize_before_compare': settings.get('deduplication.normalize_before_compare', True)
        }
        
        # Patterns pour les variantes
        self.variant_patterns = self._load_variant_patterns()
        
        self.logger.info("DuplicateDetector initialisé")
    
    def _load_variant_patterns(self) -> Dict[str, List[str]]:
        """Charge les patterns pour détecter les variantes"""
        return {
            'remix_indicators': [
                r'\s*\(.*remix.*\)',
                r'\s*\[.*remix.*\]',
                r'\s*-\s*remix',
                r'\s*remix$',
                r'\s*rmx$'
            ],
            'version_indicators': [
                r'\s*\(.*version.*\)',
                r'\s*\[.*version.*\]',
                r'\s*\(.*edit.*\)',
                r'\s*\[.*edit.*\]',
                r'\s*\(.*mix.*\)',
                r'\s*\[.*mix.*\]'
            ],
            'quality_indicators': [
                r'\s*\(.*remaster.*\)',
                r'\s*\[.*remaster.*\]',
                r'\s*\(.*clean.*\)',
                r'\s*\[.*clean.*\]',
                r'\s*\(.*explicit.*\)',
                r'\s*\[.*explicit.*\]'
            ],
            'live_indicators': [
                r'\s*\(.*live.*\)',
                r'\s*\[.*live.*\]',
                r'\s*-\s*live'
            ]
        }
    
    def detect_track_duplicates(self, artist_id: Optional[int] = None) -> List[DuplicateMatch]:
        """
        Détecte les doublons de tracks.
        
        Args:
            artist_id: ID de l'artiste (None pour tous les tracks)
            
        Returns:
            Liste des doublons détectés
        """
        matches = []
        
        try:
            # Récupération des tracks
            if artist_id:
                tracks = self.database.get_tracks_by_artist_id(artist_id)
                self.logger.info(f"Détection doublons pour artiste {artist_id}: {len(tracks)} tracks")
            else:
                # Récupérer tous les tracks (méthode à ajouter à Database)
                with self.database.get_connection() as conn:
                    cursor = conn.execute("SELECT * FROM tracks ORDER BY artist_id, title")
                    tracks = []
                    for row in cursor.fetchall():
                        track = self.database._row_to_track(row)
                        track.credits = self.database.get_credits_by_track_id(track.id)
                        track.featuring_artists = self.database.get_features_by_track_id(track.id)
                        tracks.append(track)
                self.logger.info(f"Détection doublons globale: {len(tracks)} tracks")
            
            # Comparaison par paires
            for i in range(len(tracks)):
                for j in range(i + 1, len(tracks)):
                    track1, track2 = tracks[i], tracks[j]
                    
                    # Skip si artistes différents (sauf si détection globale)
                    if artist_id is None and track1.artist_id != track2.artist_id:
                        continue
                    
                    match = self._compare_tracks(track1, track2)
                    if match:
                        matches.append(match)
            
            self.logger.info(f"Détection terminée: {len(matches)} doublons potentiels trouvés")
            return matches
            
        except Exception as e:
            self.logger.error(f"Erreur détection doublons tracks: {e}")
            return []
    
    def _compare_tracks(self, track1: Track, track2: Track) -> Optional[DuplicateMatch]:
        """Compare deux tracks pour détecter les doublons"""
        
        # Normalisation des titres pour comparaison
        title1_norm = normalize_title(track1.title) if self.config['normalize_before_compare'] else track1.title
        title2_norm = normalize_title(track2.title) if self.config['normalize_before_compare'] else track2.title
        
        # Calcul de similarité des titres
        title_similarity = similarity_ratio(title1_norm, title2_norm)
        
        # Détection doublons exacts
        if title_similarity >= self.config['exact_match_threshold']:
            return DuplicateMatch(
                entity1_id=track1.id,
                entity2_id=track2.id,
                duplicate_type=DuplicateType.EXACT,
                confidence=MatchConfidence.CERTAIN,
                similarity_score=title_similarity,
                details={
                    'title1': track1.title,
                    'title2': track2.title,
                    'title_similarity': title_similarity,
                    'same_artist': track1.artist_id == track2.artist_id,
                    'same_album': track1.album_id == track2.album_id
                },
                suggested_action="Fusionner les tracks identiques",
                entity_type="track"
            )
        
        # Détection variantes de remix/version
        if self._is_remix_variant(track1.title, track2.title):
            return DuplicateMatch(
                entity1_id=track1.id,
                entity2_id=track2.id,
                duplicate_type=DuplicateType.REMIX_VARIANT,
                confidence=MatchConfidence.HIGH,
                similarity_score=title_similarity,
                details={
                    'title1': track1.title,
                    'title2': track2.title,
                    'variant_type': 'remix/version',
                    'base_similarity': title_similarity
                },
                suggested_action="Vérifier s'il s'agit de variantes du même titre",
                entity_type="track"
            )
        
        # Détection variantes featuring
        featuring_match = self._compare_featuring_variants(track1, track2)
        if featuring_match:
            return featuring_match
        
        # Détection similarité élevée
        if title_similarity >= self.config['high_similarity_threshold']:
            confidence = self._determine_confidence(title_similarity)
            return DuplicateMatch(
                entity1_id=track1.id,
                entity2_id=track2.id,
                duplicate_type=DuplicateType.SIMILAR_TITLE,
                confidence=confidence,
                similarity_score=title_similarity,
                details={
                    'title1': track1.title,
                    'title2': track2.title,
                    'title_similarity': title_similarity,
                    'duration_diff': abs((track1.duration_seconds or 0) - (track2.duration_seconds or 0)),
                    'same_album': track1.album_id == track2.album_id
                },
                suggested_action="Vérifier manuellement la similarité",
                entity_type="track"
            )
        
        return None
    
    def _is_remix_variant(self, title1: str, title2: str) -> bool:
        """Vérifie si deux titres sont des variantes remix/version"""
        
        # Extraire les titres de base (sans les indicateurs)
        base_title1 = self._extract_base_title(title1)
        base_title2 = self._extract_base_title(title2)
        
        # Si les titres de base sont identiques mais les titres complets différents
        if base_title1 == base_title2 and title1 != title2:
            return True
        
        # Vérifier si l'un contient l'autre + indicateur de variante
        shorter = title1 if len(title1) < len(title2) else title2
        longer = title2 if len(title1) < len(title2) else title1
        
        if shorter in longer:
            # Vérifier si la différence contient un indicateur de variante
            diff = longer.replace(shorter, '').strip()
            for pattern_list in self.variant_patterns.values():
                for pattern in pattern_list:
                    if re.search(pattern, diff, re.IGNORECASE):
                        return True
        
        return False
    
    def _extract_base_title(self, title: str) -> str:
        """Extrait le titre de base en supprimant les indicateurs de variante"""
        base_title = title
        
        # Supprimer tous les indicateurs de variante
        for pattern_list in self.variant_patterns.values():
            for pattern in pattern_list:
                base_title = re.sub(pattern, '', base_title, flags=re.IGNORECASE)
        
        return base_title.strip()
    
    def _compare_featuring_variants(self, track1: Track, track2: Track) -> Optional[DuplicateMatch]:
        """Compare les tracks pour détecter les variantes featuring"""
        
        if not self.config['ignore_featuring_differences']:
            return None
        
        # Extraire titres et featuring
        title1_clean, feat1 = extract_featured_artists_from_title(track1.title)
        title2_clean, feat2 = extract_featured_artists_from_title(track2.title)
        
        # Ajouter les featuring explicites
        all_feat1 = set(feat1 + (track1.featuring_artists or []))
        all_feat2 = set(feat2 + (track2.featuring_artists or []))
        
        # Si les titres de base sont identiques mais featuring différent
        title_similarity = similarity_ratio(title1_clean, title2_clean)
        
        if title_similarity >= 0.95 and all_feat1 != all_feat2:
            return DuplicateMatch(
                entity1_id=track1.id,
                entity2_id=track2.id,
                duplicate_type=DuplicateType.FEATURING_VARIANT,
                confidence=MatchConfidence.HIGH,
                similarity_score=title_similarity,
                details={
                    'base_title1': title1_clean,
                    'base_title2': title2_clean,
                    'featuring1': list(all_feat1),
                    'featuring2': list(all_feat2),
                    'title_similarity': title_similarity
                },
                suggested_action="Vérifier les variantes featuring",
                entity_type="track"
            )
        
        return None
    
    def _determine_confidence(self, similarity_score: float) -> MatchConfidence:
        """Détermine le niveau de confiance basé sur le score de similarité"""
        if similarity_score >= 0.95:
            return MatchConfidence.CERTAIN
        elif similarity_score >= 0.85:
            return MatchConfidence.HIGH
        elif similarity_score >= 0.70:
            return MatchConfidence.MEDIUM
        elif similarity_score >= 0.50:
            return MatchConfidence.LOW
        else:
            return MatchConfidence.UNCERTAIN
    
    def detect_credit_duplicates(self, track_ids: Optional[List[int]] = None) -> List[DuplicateMatch]:
        """
        Détecte les doublons de crédits.
        
        Args:
            track_ids: Liste des IDs de tracks à analyser (None pour tous)
            
        Returns:
            Liste des doublons de crédits détectés
        """
        matches = []
        
        try:
            # Récupération des tracks
            if track_ids:
                tracks = []
                for track_id in track_ids:
                    with self.database.get_connection() as conn:
                        cursor = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
                        row = cursor.fetchone()
                        if row:
                            track = self.database._row_to_track(row)
                            track.credits = self.database.get_credits_by_track_id(track.id)
                            tracks.append(track)
            else:
                # Récupérer tous les tracks avec crédits
                with self.database.get_connection() as conn:
                    cursor = conn.execute("""
                        SELECT DISTINCT t.* FROM tracks t 
                        JOIN credits c ON t.id = c.track_id
                    """)
                    tracks = []
                    for row in cursor.fetchall():
                        track = self.database._row_to_track(row)
                        track.credits = self.database.get_credits_by_track_id(track.id)
                        tracks.append(track)
            
            self.logger.info(f"Analyse doublons crédits sur {len(tracks)} tracks")
            
            # Analyser les crédits de chaque track
            for track in tracks:
                track_matches = self._detect_track_credit_duplicates(track)
                matches.extend(track_matches)
            
            self.logger.info(f"Détection crédits terminée: {len(matches)} doublons trouvés")
            return matches
            
        except Exception as e:
            self.logger.error(f"Erreur détection doublons crédits: {e}")
            return []
    
    def _detect_track_credit_duplicates(self, track: Track) -> List[DuplicateMatch]:
        """Détecte les doublons de crédits dans un track"""
        matches = []
        
        if not track.credits:
            return matches
        
        # Grouper les crédits par (nom, type) pour détecter les doublons exacts
        credit_groups = {}
        for i, credit in enumerate(track.credits):
            key = (credit.person_name.lower().strip(), credit.credit_type)
            if key not in credit_groups:
                credit_groups[key] = []
            credit_groups[key].append((i, credit))
        
        # Identifier les doublons exacts
        for key, credits_list in credit_groups.items():
            if len(credits_list) > 1:
                # Créer des matches pour chaque paire de doublons
                for i in range(len(credits_list)):
                    for j in range(i + 1, len(credits_list)):
                        idx1, credit1 = credits_list[i]
                        idx2, credit2 = credits_list[j]
                        
                        matches.append(DuplicateMatch(
                            entity1_id=credit1.id or idx1,  # Utiliser l'index si pas d'ID
                            entity2_id=credit2.id or idx2,
                            duplicate_type=DuplicateType.CREDIT_DUPLICATE,
                            confidence=MatchConfidence.CERTAIN,
                            similarity_score=1.0,
                            details={
                                'person_name': credit1.person_name,
                                'credit_type': credit1.credit_type.value,
                                'track_id': track.id,
                                'track_title': track.title
                            },
                            suggested_action="Supprimer le crédit en double",
                            entity_type="credit"
                        ))
        
        # Détecter les noms similaires avec même type de crédit
        for i in range(len(track.credits)):
            for j in range(i + 1, len(track.credits)):
                credit1, credit2 = track.credits[i], track.credits[j]
                
                # Skip si déjà détecté comme doublon exact
                if (credit1.person_name.lower().strip(), credit1.credit_type) == \
                   (credit2.person_name.lower().strip(), credit2.credit_type):
                    continue
                
                # Vérifier similarité des noms avec même type
                if credit1.credit_type == credit2.credit_type:
                    name_similarity = similarity_ratio(credit1.person_name, credit2.person_name)
                    
                    if name_similarity >= self.config['high_similarity_threshold']:
                        matches.append(DuplicateMatch(
                            entity1_id=credit1.id or i,
                            entity2_id=credit2.id or j,
                            duplicate_type=DuplicateType.CREDIT_DUPLICATE,
                            confidence=self._determine_confidence(name_similarity),
                            similarity_score=name_similarity,
                            details={
                                'person_name1': credit1.person_name,
                                'person_name2': credit2.person_name,
                                'credit_type': credit1.credit_type.value,
                                'name_similarity': name_similarity,
                                'track_id': track.id,
                                'track_title': track.title
                            },
                            suggested_action="Vérifier et fusionner les noms similaires",
                            entity_type="credit"
                        ))
        
        return matches
    
    def detect_artist_duplicates(self) -> List[DuplicateMatch]:
        """Détecte les doublons d'artistes"""
        matches = []
        
        try:
            # Récupérer tous les artistes
            with self.database.get_connection() as conn:
                cursor = conn.execute("SELECT * FROM artists ORDER BY name")
                artists = []
                for row in cursor.fetchall():
                    from ..models.enums import Genre
                    artist = Artist(
                        id=row['id'],
                        name=row['name'],
                        genius_id=row['genius_id'],
                        spotify_id=row['spotify_id'],
                        discogs_id=row['discogs_id'],
                        genre=Genre(row['genre']) if row['genre'] else None,
                        country=row['country'],
                        active_years=row['active_years']
                    )
                    artists.append(artist)
            
            self.logger.info(f"Détection doublons artistes: {len(artists)} artistes")
            
            # Comparaison par paires
            for i in range(len(artists)):
                for j in range(i + 1, len(artists)):
                    artist1, artist2 = artists[i], artists[j]
                    match = self._compare_artists(artist1, artist2)
                    if match:
                        matches.append(match)
            
            self.logger.info(f"Détection artistes terminée: {len(matches)} doublons trouvés")
            return matches
            
        except Exception as e:
            self.logger.error(f"Erreur détection doublons artistes: {e}")
            return []
    
    def _compare_artists(self, artist1: Artist, artist2: Artist) -> Optional[DuplicateMatch]:
        """Compare deux artistes pour détecter les doublons"""
        
        # Normalisation des noms
        name1_norm = clean_artist_name(artist1.name) if self.config['normalize_before_compare'] else artist1.name
        name2_norm = clean_artist_name(artist2.name) if self.config['normalize_before_compare'] else artist2.name
        
        name_similarity = similarity_ratio(name1_norm, name2_norm)
        
        # Doublons exacts
        if name_similarity >= self.config['exact_match_threshold']:
            return DuplicateMatch(
                entity1_id=artist1.id,
                entity2_id=artist2.id,
                duplicate_type=DuplicateType.EXACT,
                confidence=MatchConfidence.CERTAIN,
                similarity_score=name_similarity,
                details={
                    'name1': artist1.name,
                    'name2': artist2.name,
                    'name_similarity': name_similarity,
                    'same_genius_id': artist1.genius_id == artist2.genius_id,
                    'same_spotify_id': artist1.spotify_id == artist2.spotify_id
                },
                suggested_action="Fusionner les artistes identiques",
                entity_type="artist"
            )
        
        # Artistes similaires
        if name_similarity >= self.config['high_similarity_threshold']:
            # Vérifier les IDs externes pour renforcer la confiance
            id_match = False
            if (artist1.genius_id and artist2.genius_id and artist1.genius_id == artist2.genius_id) or \
               (artist1.spotify_id and artist2.spotify_id and artist1.spotify_id == artist2.spotify_id):
                id_match = True
            
            confidence = MatchConfidence.CERTAIN if id_match else self._determine_confidence(name_similarity)
            
            return DuplicateMatch(
                entity1_id=artist1.id,
                entity2_id=artist2.id,
                duplicate_type=DuplicateType.SIMILAR_ARTIST,
                confidence=confidence,
                similarity_score=name_similarity,
                details={
                    'name1': artist1.name,
                    'name2': artist2.name,
                    'name_similarity': name_similarity,
                    'external_id_match': id_match,
                    'genius_ids': [artist1.genius_id, artist2.genius_id],
                    'spotify_ids': [artist1.spotify_id, artist2.spotify_id]
                },
                suggested_action="Vérifier et fusionner si identiques",
                entity_type="artist"
            )
        
        return None
    
    def auto_merge_duplicates(self, matches: List[DuplicateMatch], dry_run: bool = True) -> DeduplicationStats:
        """
        Fusionne automatiquement les doublons selon la configuration.
        
        Args:
            matches: Liste des doublons détectés
            dry_run: Si True, simule sans modifier la base
            
        Returns:
            Statistiques de déduplication
        """
        stats = DeduplicationStats()
        stats.total_processed = len(matches)
        
        try:
            self.logger.info(f"Début fusion automatique: {len(matches)} matches (dry_run={dry_run})")
            
            for match in matches:
                should_merge = self._should_auto_merge(match)
                
                if should_merge:
                    if match.duplicate_type == DuplicateType.EXACT:
                        stats.exact_duplicates += 1
                    else:
                        stats.similar_duplicates += 1
                    
                    if not dry_run:
                        success = self._merge_entities(match)
                        if success:
                            if match.entity_type == "track":
                                stats.tracks_merged += 1
                            elif match.entity_type == "artist":
                                stats.artists_merged += 1
                            elif match.entity_type == "credit":
                                stats.credits_merged += 1
                else:
                    stats.potential_duplicates += 1
            
            action = "Simulation terminée" if dry_run else "Fusion terminée"
            self.logger.info(f"{action}: {stats.exact_duplicates} doublons exacts, {stats.similar_duplicates} similaires")
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Erreur fusion automatique: {e}")
            return stats
    
    def _should_auto_merge(self, match: DuplicateMatch) -> bool:
        """Détermine si un match doit être fusionné automatiquement"""
        
        # Fusion des doublons exacts si activée
        if match.duplicate_type == DuplicateType.EXACT and self.config['auto_merge_exact']:
            return True
        
        # Fusion des similarités élevées si activée
        if (match.confidence in [MatchConfidence.CERTAIN, MatchConfidence.HIGH] and 
            self.config['auto_merge_high_similarity']):
            return True
        
        # Fusion automatique des crédits en double
        if match.duplicate_type == DuplicateType.CREDIT_DUPLICATE and match.confidence == MatchConfidence.CERTAIN:
            return True
        
        return False
    
    def _merge_entities(self, match: DuplicateMatch) -> bool:
        """Fusionne deux entités"""
        try:
            if match.entity_type == "track":
                return self._merge_tracks(match.entity1_id, match.entity2_id)
            elif match.entity_type == "artist":
                return self._merge_artists(match.entity1_id, match.entity2_id)
            elif match.entity_type == "credit":
                return self._merge_credits(match.entity1_id, match.entity2_id)
            else:
                self.logger.warning(f"Type d'entité non supporté pour fusion: {match.entity_type}")
                return False
                
        except Exception as e:
            self.logger.error(f"Erreur fusion {match.entity_type} {match.entity1_id}/{match.entity2_id}: {e}")
            return False
    
    def _merge_tracks(self, track1_id: int, track2_id: int) -> bool:
        """Fusionne deux tracks"""
        # Pour l'instant, on marque simplement le second comme doublon
        # Une implémentation complète nécessiterait une logique de fusion plus sophistiquée
        try:
            with self.database.get_connection() as conn:
                # Marquer le track2 comme doublon du track1
                conn.execute("""
                    UPDATE tracks SET 
                        title = title || ' [DUPLICATE]',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (track2_id,))
                
                # Log de la fusion
                self.logger.info(f"Track {track2_id} marqué comme doublon de {track1_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Erreur fusion tracks {track1_id}/{track2_id}: {e}")
            return False
    
    def _merge_artists(self, artist1_id: int, artist2_id: int) -> bool:
        """Fusionne deux artistes"""
        try:
            with self.database.get_connection() as conn:
                # Transférer tous les tracks de artist2 vers artist1
                conn.execute("""
                    UPDATE tracks SET artist_id = ? WHERE artist_id = ?
                """, (artist1_id, artist2_id))
                
                # Marquer artist2 comme doublon
                conn.execute("""
                    UPDATE artists SET 
                        name = name || ' [DUPLICATE]'
                    WHERE id = ?
                """, (artist2_id,))
                
                self.logger.info(f"Artiste {artist2_id} fusionné avec {artist1_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"Erreur fusion artistes {artist1_id}/{artist2_id}: {e}")
            return False
    
    def _merge_credits(self, credit1_id: int, credit2_id: int) -> bool:
        """Fusionne deux crédits (supprime le second)"""
        try:
            with self.database.get_connection() as conn:
                # Supprimer le crédit en double
                conn.execute("DELETE FROM credits WHERE id = ?", (credit2_id,))
                
                self.logger.info(f"Crédit {credit2_id} supprimé (doublon de {credit1_id})")
                return True
                
        except Exception as e:
            self.logger.error(f"Erreur fusion crédits {credit1_id}/{credit2_id}: {e}")
            return False
    
    def generate_deduplication_report(self, matches: List[DuplicateMatch]) -> Dict[str, Any]:
        """
        Génère un rapport de déduplication.
        
        Args:
            matches: Liste des doublons détectés
            
        Returns:
            Rapport détaillé
        """
        try:
            # Statistiques par type
            type_stats = {}
            confidence_stats = {}
            entity_stats = {}
            
            for match in matches:
                # Par type de doublon
                dtype = match.duplicate_type.value
                type_stats[dtype] = type_stats.get(dtype, 0) + 1
                
                # Par niveau de confiance
                conf = match.confidence.value
                confidence_stats[conf] = confidence_stats.get(conf, 0) + 1
                
                # Par type d'entité
                entity = match.entity_type
                entity_stats[entity] = entity_stats.get(entity, 0) + 1
            
            # Calculs de scores
            total_matches = len(matches)
            high_confidence = sum(1 for m in matches if m.confidence in [MatchConfidence.CERTAIN, MatchConfidence.HIGH])
            exact_duplicates = sum(1 for m in matches if m.duplicate_type == DuplicateType.EXACT)
            
            # Top doublons par score de similarité
            top_matches = sorted(matches, key=lambda x: x.similarity_score, reverse=True)[:10]
            
            return {
                'summary': {
                    'total_duplicates': total_matches,
                    'exact_duplicates': exact_duplicates,
                    'high_confidence_matches': high_confidence,
                    'duplicate_rate': (total_matches / 1000) if total_matches > 0 else 0  # Estimation
                },
                'by_type': type_stats,
                'by_confidence': confidence_stats,
                'by_entity': entity_stats,
                'recommendations': {
                    'auto_mergeable': high_confidence,
                    'manual_review_needed': total_matches - high_confidence,
                    'priority_actions': self._generate_priority_actions(matches)
                },
                'top_matches': [
                    {
                        'entities': f"{m.entity1_id} / {m.entity2_id}",
                        'type': m.duplicate_type.value,
                        'confidence': m.confidence.value,
                        'similarity': round(m.similarity_score, 3),
                        'details': m.details
                    }
                    for m in top_matches
                ],
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Erreur génération rapport déduplication: {e}")
            return {}
    
    def _generate_priority_actions(self, matches: List[DuplicateMatch]) -> List[str]:
        """Génère une liste d'actions prioritaires"""
        actions = []
        
        # Compter les types de problèmes
        exact_count = sum(1 for m in matches if m.duplicate_type == DuplicateType.EXACT)
        credit_count = sum(1 for m in matches if m.duplicate_type == DuplicateType.CREDIT_DUPLICATE)
        similar_count = sum(1 for m in matches if m.duplicate_type == DuplicateType.SIMILAR_TITLE)
        
        if exact_count > 0:
            actions.append(f"Fusionner {exact_count} doublons exacts")
        
        if credit_count > 0:
            actions.append(f"Nettoyer {credit_count} crédits en double")
        
        if similar_count > 0:
            actions.append(f"Vérifier manuellement {similar_count} titres similaires")
        
        return actions