# discovery/album_resolver.py
"""
Résolveur d'albums optimisé pour organiser et regrouper les tracks découverts.
Version avec cache intelligent, détection de types d'albums et métadonnées enrichies.
"""

import logging
import re
from functools import lru_cache
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict, Counter
from datetime import datetime

# Imports absolus
from models.entities import Track, Album, Artist
from models.enums import AlbumType, DataSource, ExtractionStatus
from config.settings import settings
from core.database import Database
from utils.text_utils import normalize_text, calculate_similarity


class AlbumResolver:
    """
    Résolveur d'albums optimisé pour organiser et regrouper les tracks découverts.
    
    Fonctionnalités principales:
    - Regroupement automatique des tracks par album avec cache
    - Détection intelligente des singles/EPs/albums/mixtapes
    - Résolution des conflits de nommage
    - Enrichissement des métadonnées d'albums
    - Déduplication avancée
    """
    
    def __init__(self, database: Database):
        self.logger = logging.getLogger(__name__)
        self.db = database
        self.config = settings.get('albums', {})
        
        # Configuration optimisée avec valeurs par défaut
        self.min_tracks_for_album = self.config.get('min_tracks_for_album', 4)
        self.max_tracks_for_single = self.config.get('max_tracks_for_single', 2)
        self.max_tracks_for_ep = self.config.get('max_tracks_for_ep', 8)
        self.detect_singles = self.config.get('detect_singles', True)
        self.similarity_threshold = self.config.get('similarity_threshold', 0.85)
        self.auto_merge_similar = self.config.get('auto_merge_similar', True)
        
        # Patterns compilés pour optimisation avec cache
        self._compiled_patterns = self._compile_detection_patterns()
        
        # Cache pour éviter les recalculs
        self._similarity_cache = {}
        self._album_cache = {}
        
        # Statistiques de résolution
        self.resolution_stats = {
            'albums_created': 0,
            'albums_updated': 0,
            'tracks_processed': 0,
            'duplicates_merged': 0,
            'orphans_handled': 0
        }
        
        self.logger.info("✅ AlbumResolver optimisé initialisé")
    
    @lru_cache(maxsize=1)
    def _compile_detection_patterns(self) -> Dict[str, List[re.Pattern]]:
        """
        Compile les patterns de détection de types d'albums avec cache.
        
        Returns:
            Dictionnaire des patterns compilés par type
        """
        patterns = {
            'ep': [
                r'\bep\b',
                r'\bmini[\s\-]*album\b',
                r'\bextended[\s\-]*play\b',
                r'\bplaylist\b'
            ],
            'mixtape': [
                r'\bmixtape\b',
                r'\bmix[\s\-]*tape\b',
                r'\btape\b',
                r'\bfree[\s\-]*tape\b'
            ],
            'compilation': [
                r'\bcompilation\b',
                r'\bbest[\s\-]*of\b',
                r'\bgreatest[\s\-]*hits\b',
                r'\bcollection\b',
                r'\bantology\b',
                r'\bselected\b'
            ],
            'live': [
                r'\blive\b',
                r'\bconcert\b',
                r'\btour\b',
                r'\ben[\s\-]*direct\b'
            ],
            'single': [
                r'\bsingle\b',
                r'\bfeat\.?\b',
                r'\bft\.?\b',
                r'\bwith\b.*\bfeat\b'
            ],
            'remix': [
                r'\bremix\b',
                r'\brework\b',
                r'\bremaster\b',
                r'\bversion\b'
            ],
            'deluxe': [
                r'\bdeluxe\b',
                r'\bexpanded\b',
                r'\bspecial[\s\-]*edition\b',
                r'\breissue\b'
            ]
        }
        
        compiled_patterns = {}
        for category, pattern_list in patterns.items():
            compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE) for pattern in pattern_list
            ]
        
        return compiled_patterns
    
    def resolve_albums_for_tracks(self, tracks: List[Track], artist: Artist) -> List[Album]:
        """
        Résout les albums pour une liste de tracks d'un artiste avec optimisations.
        
        Args:
            tracks: Liste des tracks à organiser
            artist: Artiste concerné
            
        Returns:
            Liste des albums créés/mis à jour
        """
        if not tracks:
            self.logger.warning("⚠️ Aucune track fournie pour la résolution d'albums")
            return []
        
        self.logger.info(f"🔍 Résolution d'albums pour {artist.name} ({len(tracks)} tracks)")
        
        # Réinitialiser les stats pour cette session
        self.resolution_stats['tracks_processed'] = len(tracks)
        
        try:
            # Étape 1: Préprocessing et nettoyage des données
            cleaned_tracks = self._preprocess_tracks(tracks)
            
            # Étape 2: Groupement intelligent par album
            album_groups = self._group_tracks_by_album(cleaned_tracks)
            
            # Étape 3: Fusion des albums similaires
            if self.auto_merge_similar:
                album_groups = self._merge_similar_albums(album_groups)
            
            # Étape 4: Résolution individuelle de chaque album
            resolved_albums = []
            
            for album_title, track_group in album_groups.items():
                try:
                    album = self._resolve_single_album(album_title, track_group, artist)
                    if album:
                        resolved_albums.append(album)
                        self.logger.debug(f"✅ Album résolu: {album.title} ({len(track_group)} tracks)")
                except Exception as e:
                    self.logger.error(f"❌ Erreur résolution album '{album_title}': {e}")
                    continue
            
            # Étape 5: Gestion des tracks orphelines
            orphan_tracks = [t for t in cleaned_tracks if not t.album_title or t.album_title.strip() == '']
            if orphan_tracks:
                self.logger.info(f"🔍 Traitement de {len(orphan_tracks)} tracks orphelines")
                orphan_albums = self._handle_orphan_tracks(orphan_tracks, artist)
                resolved_albums.extend(orphan_albums)
                self.resolution_stats['orphans_handled'] = len(orphan_tracks)
            
            # Étape 6: Post-traitement et validation
            validated_albums = self._validate_and_finalize_albums(resolved_albums)
            
            self.logger.info(f"✅ Résolution terminée: {len(validated_albums)} albums créés/mis à jour")
            self._log_resolution_summary()
            
            return validated_albums
            
        except Exception as e:
            self.logger.error(f"❌ Erreur générale lors de la résolution d'albums: {e}")
            return []
    
    def _preprocess_tracks(self, tracks: List[Track]) -> List[Track]:
        """
        Préprocessing des tracks pour optimiser la résolution.
        
        Args:
            tracks: Liste des tracks brutes
            
        Returns:
            Liste des tracks nettoyées
        """
        cleaned_tracks = []
        
        for track in tracks:
            # Nettoyage du titre d'album
            if track.album_title:
                # Suppression des caractères parasites
                clean_title = track.album_title.strip()
                clean_title = re.sub(r'\s+', ' ', clean_title)  # Normaliser les espaces
                clean_title = re.sub(r'[^\w\s\-\'\"()&]', '', clean_title)  # Garder uniquement les caractères utiles
                track.album_title = clean_title
            
            # Validation des données de base
            if track.title and track.title.strip():
                cleaned_tracks.append(track)
            else:
                self.logger.warning(f"⚠️ Track sans titre ignorée: {track}")
        
        self.logger.debug(f"🧹 Préprocessing: {len(cleaned_tracks)}/{len(tracks)} tracks conservées")
        return cleaned_tracks
    
    def _group_tracks_by_album(self, tracks: List[Track]) -> Dict[str, List[Track]]:
        """
        Groupe les tracks par nom d'album potentiel avec normalisation avancée.
        
        Args:
            tracks: Liste des tracks à grouper
            
        Returns:
            Dictionnaire {nom_album_normalisé: [tracks]}
        """
        album_groups = defaultdict(list)
        
        for track in tracks:
            if track.album_title and track.album_title.strip():
                # Normalisation avancée du nom d'album
                normalized_title = self._normalize_album_title(track.album_title)
                album_groups[normalized_title].append(track)
            else:
                # Tracks sans album -> groupe spécial
                album_groups["_ORPHANS_"].append(track)
        
        # Conversion en dict normal pour éviter les defaultdict
        return dict(album_groups)
    
    @lru_cache(maxsize=256)
    def _normalize_album_title(self, title: str) -> str:
        """
        Normalise un titre d'album pour le regroupement avec cache.
        
        Args:
            title: Titre brut
            
        Returns:
            Titre normalisé
        """
        if not title:
            return "_UNKNOWN_"
        
        # Étapes de normalisation
        normalized = title.lower().strip()
        
        # Suppression des indicateurs de version/édition pour regroupement
        patterns_to_remove = [
            r'\b(deluxe|expanded|special|limited|collector\'s?)\s*(edition|version)?\b',
            r'\b(remaster|remastered|anniversary)\s*(edition|version)?\b',
            r'\b\d{4}\s*(remaster|edition|version)\b',
            r'\[.*?\]',  # Texte entre crochets
            r'\(.*?(deluxe|expanded|special|remaster).*?\)',  # Parenthèses avec mots-clés
        ]
        
        for pattern in patterns_to_remove:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        
        # Nettoyage final
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        normalized = normalize_text(normalized)  # Utilise la fonction utils
        
        return normalized if normalized else "_UNKNOWN_"
    
    def _merge_similar_albums(self, album_groups: Dict[str, List[Track]]) -> Dict[str, List[Track]]:
        """
        Fusionne les albums similaires pour éviter les doublons.
        
        Args:
            album_groups: Dictionnaire des groupes d'albums
            
        Returns:
            Dictionnaire avec albums fusionnés
        """
        if len(album_groups) <= 1:
            return album_groups
        
        merged_groups = {}
        processed_titles = set()
        
        for title1, tracks1 in album_groups.items():
            if title1 in processed_titles:
                continue
            
            # Recherche d'albums similaires
            similar_albums = [title1]
            all_tracks = tracks1.copy()
            
            for title2, tracks2 in album_groups.items():
                if title2 == title1 or title2 in processed_titles:
                    continue
                
                # Calcul de similarité avec cache
                similarity = self._get_album_similarity(title1, title2)
                
                if similarity >= self.similarity_threshold:
                    similar_albums.append(title2)
                    all_tracks.extend(tracks2)
                    processed_titles.add(title2)
                    self.resolution_stats['duplicates_merged'] += 1
            
            # Choisir le meilleur titre pour le groupe fusionné
            best_title = self._choose_best_album_title(similar_albums, all_tracks)
            merged_groups[best_title] = all_tracks
            processed_titles.add(title1)
        
        if self.resolution_stats['duplicates_merged'] > 0:
            self.logger.info(f"🔗 {self.resolution_stats['duplicates_merged']} albums similaires fusionnés")
        
        return merged_groups
    
    @lru_cache(maxsize=512)
    def _get_album_similarity(self, title1: str, title2: str) -> float:
        """
        Calcule la similarité entre deux titres d'albums avec cache.
        
        Args:
            title1, title2: Titres à comparer
            
        Returns:
            Score de similarité (0.0 à 1.0)
        """
        return calculate_similarity(title1, title2)
    
    def _choose_best_album_title(self, titles: List[str], tracks: List[Track]) -> str:
        """
        Choisit le meilleur titre d'album parmi plusieurs options.
        
        Args:
            titles: Liste des titres candidats
            tracks: Tracks associées
            
        Returns:
            Meilleur titre d'album
        """
        if len(titles) == 1:
            return titles[0]
        
        # Compter les occurrences dans les tracks originales
        title_counts = Counter()
        for track in tracks:
            if track.album_title:
                normalized = self._normalize_album_title(track.album_title)
                if normalized in titles:
                    title_counts[normalized] += 1
        
        # Choisir le plus fréquent, sinon le plus court et propre
        if title_counts:
            most_common = title_counts.most_common(1)[0][0]
            return most_common
        
        # Fallback: titre le plus court et propre
        return min(titles, key=lambda x: (len(x), x.count('('), x.count('['), x.lower()))
    
    def _resolve_single_album(self, album_title: str, tracks: List[Track], artist: Artist) -> Optional[Album]:
        """
        Résout un album spécifique à partir d'un groupe de tracks.
        
        Args:
            album_title: Titre de l'album
            tracks: Liste des tracks de l'album
            artist: Artiste concerné
            
        Returns:
            Album créé/mis à jour ou None si échec
        """
        if not tracks:
            self.logger.warning(f"⚠️ Aucune track pour l'album '{album_title}'")
            return None
        
        try:
            # Vérifier si l'album existe déjà
            existing_album = self._find_existing_album(album_title, artist.id)
            if existing_album:
                self._update_album_with_tracks(existing_album, tracks)
                self.resolution_stats['albums_updated'] += 1
                return existing_album
            
            # Créer un nouvel album
            album = Album(
                title=self._get_best_album_title(tracks),
                artist_id=artist.id,
                artist_name=artist.name,
                track_count=len(tracks)
            )
            
            # Enrichissement des métadonnées
            self._enrich_album_metadata(album, tracks)
            
            # Détermination du type d'album
            album.album_type = self._detect_album_type(album, tracks)
            
            # Assignation de la source de données
            album.data_source = self._determine_primary_source(tracks)
            album.extraction_status = ExtractionStatus.COMPLETED
            
            # Sauvegarde en base de données
            album_id = self._save_album_to_database(album, tracks)
            if album_id:
                album.id = album_id
                self.resolution_stats['albums_created'] += 1
                return album
            else:
                self.logger.error(f"❌ Échec sauvegarde album '{album.title}'")
                return None
            
        except Exception as e:
            self.logger.error(f"❌ Erreur résolution album '{album_title}': {e}")
            return None
    
    def _find_existing_album(self, album_title: str, artist_id: int) -> Optional[Album]:
        """
        Recherche un album existant par titre et artiste avec cache.
        
        Args:
            album_title: Titre de l'album
            artist_id: ID de l'artiste
            
        Returns:
            Album existant ou None
        """
        cache_key = f"album_{artist_id}_{self._normalize_album_title(album_title)}"
        
        if cache_key in self._album_cache:
            return self._album_cache[cache_key]
        
        try:
            # Tentative de récupération depuis la base
            album = self.db.get_album_by_title_and_artist(album_title, artist_id)
            self._album_cache[cache_key] = album
            return album
        except (AttributeError, Exception):
            # Méthode non implémentée ou erreur
            self._album_cache[cache_key] = None
            return None
    
    def _get_best_album_title(self, tracks: List[Track]) -> str:
        """
        Détermine le meilleur titre d'album à partir des tracks.
        
        Args:
            tracks: Liste des tracks
            
        Returns:
            Meilleur titre d'album
        """
        titles = [t.album_title for t in tracks if t.album_title and t.album_title.strip()]
        
        if not titles:
            return "Unknown Album"
        
        # Compter les occurrences exactes
        title_counts = Counter(titles)
        most_common_title = title_counts.most_common(1)[0][0]
        
        # Si plusieurs variantes similaires, choisir la plus propre
        similar_titles = []
        for title in titles:
            if calculate_similarity(title, most_common_title) > 0.9:
                similar_titles.append(title)
        
        if similar_titles:
            # Préférer les titres les plus courts et propres
            best_title = min(similar_titles, key=lambda x: (
                len(x),
                x.count('('),
                x.count('['),
                x.count('{'),
                x.lower()
            ))
            return best_title.strip()
        
        return most_common_title.strip()
    
    def _enrich_album_metadata(self, album: Album, tracks: List[Track]) -> None:
        """
        Enrichit les métadonnées de l'album à partir des tracks.
        
        Args:
            album: Album à enrichir
            tracks: Tracks source des métadonnées
        """
        # Calcul de la durée totale
        durations = [t.duration_seconds for t in tracks if t.duration_seconds and t.duration_seconds > 0]
        if durations:
            album.total_duration = sum(durations)
        
        # Détection de la date de sortie (la plus ancienne)
        release_dates = []
        for track in tracks:
            if track.release_date:
                try:
                    if isinstance(track.release_date, str):
                        # Parsing de différents formats de date
                        for fmt in ['%Y-%m-%d', '%Y', '%d/%m/%Y', '%m/%d/%Y']:
                            try:
                                date_obj = datetime.strptime(track.release_date, fmt)
                                release_dates.append(date_obj)
                                break
                            except ValueError:
                                continue
                    else:
                        release_dates.append(track.release_date)
                except Exception:
                    continue
        
        if release_dates:
            earliest_date = min(release_dates)
            album.release_date = earliest_date.strftime('%Y-%m-%d') if hasattr(earliest_date, 'strftime') else str(earliest_date)
            try:
                album.release_year = earliest_date.year if hasattr(earliest_date, 'year') else int(str(earliest_date)[:4])
            except (ValueError, TypeError):
                pass
        
        # Détection du genre (basé sur les tracks ou artiste)
        genres = [t.genre for t in tracks if t.genre]
        if genres:
            # Prendre le genre le plus fréquent
            genre_counts = Counter(genres)
            album.genre = genre_counts.most_common(1)[0][0]
        else:
            # Valeur par défaut pour le rap/hip-hop
            album.genre = "rap"
        
        # Collecte des IDs externes pour déduction
        spotify_ids = [t.spotify_id for t in tracks if t.spotify_id]
        genius_ids = [t.genius_id for t in tracks if hasattr(t, 'genius_id') and t.genius_id]
        
        # Métadonnées supplémentaires
        album.total_tracks = len(tracks)
        album.has_explicit_content = any(getattr(t, 'explicit', False) for t in tracks)
        
        # Calcul du score de popularité basé sur les tracks
        pageviews = [getattr(t, 'pageviews', 0) for t in tracks if hasattr(t, 'pageviews') and getattr(t, 'pageviews', 0)]
        if pageviews:
            album.popularity_score = sum(pageviews) / len(pageviews)
    
    @lru_cache(maxsize=64)
    def _detect_album_type(self, album: Album, tracks: List[Track]) -> AlbumType:
        """
        Détecte le type d'album basé sur le titre et le nombre de tracks avec cache.
        
        Args:
            album: Album à analyser
            tracks: Tracks de l'album
            
        Returns:
            Type d'album détecté
        """
        title_lower = album.title.lower()
        track_count = len(tracks)
        
        # Single: 1-2 tracks ou contient des indicateurs de single
        if (track_count <= self.max_tracks_for_single or 
            any(pattern.search(title_lower) for pattern in self._compiled_patterns['single'])):
            return AlbumType.SINGLE
        
        # EP: 3-8 tracks ou contient des indicateurs d'EP
        if (track_count <= self.max_tracks_for_ep or 
            any(pattern.search(title_lower) for pattern in self._compiled_patterns['ep'])):
            return AlbumType.EP
        
        # Mixtape: indicateurs spécifiques
        if any(pattern.search(title_lower) for pattern in self._compiled_patterns['mixtape']):
            return AlbumType.MIXTAPE
        
        # Live: indicateurs de concert/live
        if any(pattern.search(title_lower) for pattern in self._compiled_patterns['live']):
            return AlbumType.LIVE
        
        # Compilation: best-of, greatest hits, etc.
        if any(pattern.search(title_lower) for pattern in self._compiled_patterns['compilation']):
            return AlbumType.COMPILATION
        
        # Album standard: plus de tracks et pas d'indicateur spécial
        if track_count >= self.min_tracks_for_album:
            return AlbumType.ALBUM
        
        # Défaut: EP pour les cas ambigus
        return AlbumType.EP
    
    def _determine_primary_source(self, tracks: List[Track]) -> DataSource:
        """
        Détermine la source de données principale pour l'album.
        
        Args:
            tracks: Tracks de l'album
            
        Returns:
            Source de données principale
        """
        sources = [getattr(t, 'data_source', None) for t in tracks if hasattr(t, 'data_source')]
        
        if not sources:
            return DataSource.GENIUS  # Défaut
        
        # Compter les occurrences des sources
        source_counts = Counter(sources)
        primary_source = source_counts.most_common(1)[0][0]
        
        # Convertir en DataSource si c'est une string
        if isinstance(primary_source, str):
            try:
                return DataSource(primary_source)
            except ValueError:
                return DataSource.GENIUS
        
        return primary_source
    
    def _save_album_to_database(self, album: Album, tracks: List[Track]) -> Optional[int]:
        """
        Sauvegarde l'album en base de données et met à jour les tracks.
        
        Args:
            album: Album à sauvegarder
            tracks: Tracks associées
            
        Returns:
            ID de l'album créé ou None si échec
        """
        try:
            # Création de l'album
            album_id = self.db.create_album(album)
            
            if album_id:
                # Mise à jour des tracks avec l'ID de l'album
                for track in tracks:
                    track.album_id = album_id
                    track.album_title = album.title
                    if hasattr(track, 'id') and track.id:
                        try:
                            self.db.update_track(track)
                        except Exception as e:
                            self.logger.warning(f"⚠️ Erreur mise à jour track {track.title}: {e}")
                
                self.logger.debug(f"💾 Album '{album.title}' sauvegardé avec ID: {album_id}")
                return album_id
            
        except Exception as e:
            self.logger.error(f"❌ Erreur sauvegarde album '{album.title}': {e}")
        
        return None
    
    def _update_album_with_tracks(self, album: Album, tracks: List[Track]) -> None:
        """
        Met à jour un album existant avec de nouvelles tracks.
        
        Args:
            album: Album existant
            tracks: Nouvelles tracks à ajouter
        """
        try:
            # Mise à jour du nombre de tracks
            album.track_count = max(album.track_count or 0, len(tracks))
            album.total_tracks = album.track_count
            
            # Re-calcul des métadonnées si nécessaire
            self._enrich_album_metadata(album, tracks)
            
            # Mise à jour en base
            self.db.update_album(album)
            
            # Mise à jour des tracks
            for track in tracks:
                track.album_id = album.id
                track.album_title = album.title
                if hasattr(track, 'id') and track.id:
                    try:
                        self.db.update_track(track)
                    except Exception as e:
                        self.logger.warning(f"⚠️ Erreur mise à jour track {track.title}: {e}")
            
            self.logger.debug(f"🔄 Album '{album.title}' mis à jour avec {len(tracks)} tracks")
            
        except Exception as e:
            self.logger.error(f"❌ Erreur mise à jour album '{album.title}': {e}")
    
    def _handle_orphan_tracks(self, orphan_tracks: List[Track], artist: Artist) -> List[Album]:
        """
        Gère les tracks orphelines (sans album assigné).
        
        Args:
            orphan_tracks: Tracks sans album
            artist: Artiste concerné
            
        Returns:
            Liste des albums créés pour les orphelines
        """
        if not orphan_tracks:
            return []
        
        created_albums = []
        
        # Stratégie 1: Grouper par patterns dans le titre
        grouped_orphans = self._group_orphans_by_patterns(orphan_tracks)
        
        for group_name, group_tracks in grouped_orphans.items():
            try:
                # Créer un album pour chaque groupe
                album_title = group_name if group_name != "_SINGLES_" else f"{artist.name} - Singles"
                
                album = Album(
                    title=album_title,
                    artist_id=artist.id,
                    artist_name=artist.name,
                    track_count=len(group_tracks),
                    album_type=AlbumType.SINGLE if group_name == "_SINGLES_" else AlbumType.EP
                )
                
                # Enrichissement et sauvegarde
                self._enrich_album_metadata(album, group_tracks)
                album_id = self._save_album_to_database(album, group_tracks)
                
                if album_id:
                    album.id = album_id
                    created_albums.append(album)
                    self.logger.debug(f"📦 Album orphelin créé: {album.title}")
                
            except Exception as e:
                self.logger.error(f"❌ Erreur création album orphelin '{group_name}': {e}")
        
        return created_albums
    
    def _group_orphans_by_patterns(self, orphan_tracks: List[Track]) -> Dict[str, List[Track]]:
        """
        Groupe les tracks orphelines par patterns détectés.
        
        Args:
            orphan_tracks: Tracks orphelines
            
        Returns:
            Dictionnaire des groupes créés
        """
        groups = defaultdict(list)
        
        for track in orphan_tracks:
            group_name = "_SINGLES_"  # Groupe par défaut
            
            # Essayer de détecter des patterns dans le titre
            title_lower = track.title.lower()
            
            # Pattern de featuring/collaboration
            if any(pattern in title_lower for pattern in ['feat.', 'ft.', 'featuring', 'with']):
                group_name = f"{track.artist_name} - Collaborations"
            
            # Pattern de remix
            elif any(pattern in title_lower for pattern in ['remix', 'rework', 'version']):
                group_name = f"{track.artist_name} - Remixes"
            
            # Pattern de freestyle
            elif any(pattern in title_lower for pattern in ['freestyle', 'cypher', 'snippet']):
                group_name = f"{track.artist_name} - Freestyles"
            
            groups[group_name].append(track)
        
        return dict(groups)
    
    def _validate_and_finalize_albums(self, albums: List[Album]) -> List[Album]:
        """
        Valide et finalise les albums créés.
        
        Args:
            albums: Albums à valider
            
        Returns:
            Albums validés
        """
        validated_albums = []
        
        for album in albums:
            try:
                # Validation de base
                if not album.title or not album.artist_id:
                    self.logger.warning(f"⚠️ Album invalide ignoré: {album}")
                    continue
                
                # Validation du nombre de tracks
                if album.track_count <= 0:
                    self.logger.warning(f"⚠️ Album sans tracks ignoré: {album.title}")
                    continue
                
                # Finalisation des métadonnées
                album.created_at = datetime.now()
                album.updated_at = album.created_at
                
                validated_albums.append(album)
                
            except Exception as e:
                self.logger.error(f"❌ Erreur validation album {album.title}: {e}")
        
        return validated_albums
    
    def _log_resolution_summary(self) -> None:
        """Log un résumé des statistiques de résolution"""
        stats = self.resolution_stats
        self.logger.info(
            f"📊 Résumé résolution: "
            f"{stats['albums_created']} créés, "
            f"{stats['albums_updated']} mis à jour, "
            f"{stats['tracks_processed']} tracks traitées, "
            f"{stats['duplicates_merged']} doublons fusionnés, "
            f"{stats['orphans_handled']} orphelines gérées"
        )
    
    # ===== MÉTHODES UTILITAIRES =====
    
    @lru_cache(maxsize=1)
    def get_resolution_stats(self) -> Dict[str, Any]:
        """
        Retourne les statistiques de résolution avec cache.
        
        Returns:
            Dictionnaire des statistiques
        """
        return {
            **self.resolution_stats,
            'cache_size': len(self._album_cache),
            'similarity_cache_size': len(self._similarity_cache),
            'success_rate': (
                (self.resolution_stats['albums_created'] + self.resolution_stats['albums_updated']) /
                max(self.resolution_stats['tracks_processed'], 1)
            ) * 100
        }
    
    def clear_caches(self) -> None:
        """Vide tous les caches pour libérer la mémoire"""
        self._album_cache.clear()
        self._similarity_cache.clear()
        
        # Vider les caches LRU
        self._normalize_album_title.cache_clear()
        self._get_album_similarity.cache_clear()
        self._detect_album_type.cache_clear()
        self.get_resolution_stats.cache_clear()
        
        self.logger.debug("🧹 Caches AlbumResolver vidés")
    
    def reset_stats(self) -> None:
        """Remet à zéro les statistiques de résolution"""
        self.resolution_stats = {
            'albums_created': 0,
            'albums_updated': 0,
            'tracks_processed': 0,
            'duplicates_merged': 0,
            'orphans_handled': 0
        }
        
        self.logger.debug("📊 Statistiques AlbumResolver réinitialisées")
    
    def __repr__(self) -> str:
        """Représentation string de l'instance"""
        stats = self.get_resolution_stats()
        return (f"AlbumResolver(albums_created={stats['albums_created']}, "
                f"albums_updated={stats['albums_updated']}, "
                f"success_rate={stats['success_rate']:.1f}%)")


# ===== FONCTIONS UTILITAIRES MODULE =====

def create_album_resolver(database: Database) -> Optional[AlbumResolver]:
    """
    Factory function pour créer une instance AlbumResolver avec gestion d'erreurs.
    
    Args:
        database: Instance de base de données
        
    Returns:
        Instance AlbumResolver ou None si échec
    """
    try:
        return AlbumResolver(database)
    except Exception as e:
        logging.getLogger(__name__).error(f"❌ Impossible de créer AlbumResolver: {e}")
        return None


def test_album_resolution(tracks: List[Track], artist: Artist, database: Database) -> Dict[str, Any]:
    """
    Teste la résolution d'albums et retourne un rapport de diagnostic.
    
    Args:
        tracks: Tracks de test
        artist: Artiste de test
        database: Base de données
        
    Returns:
        Dictionnaire avec les résultats du test
    """
    logger = logging.getLogger(__name__)
    
    try:
        resolver = create_album_resolver(database)
        if not resolver:
            return {
                'success': False,
                'error': 'Impossible de créer une instance AlbumResolver'
            }
        
        # Test de résolution
        start_time = datetime.now()
        albums = resolver.resolve_albums_for_tracks(tracks, artist)
        end_time = datetime.now()
        
        return {
            'success': True,
            'albums_created': len(albums),
            'resolution_time_seconds': (end_time - start_time).total_seconds(),
            'resolution_stats': resolver.get_resolution_stats(),
            'albums_summary': [
                {
                    'title': album.title,
                    'type': album.album_type.value if album.album_type else 'unknown',
                    'track_count': album.track_count
                }
                for album in albums
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur test AlbumResolver: {e}")
        return {
            'success': False,
            'error': str(e)
        }