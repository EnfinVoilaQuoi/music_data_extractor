# discovery/album_resolver.py
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict, Counter
import re
from datetime import datetime

from ..models.entities import Track, Album, Artist
from ..models.enums import AlbumType, DataSource, ExtractionStatus
from ..config.settings import settings
from ..core.database import Database
from ..utils.text_utils import normalize_text, calculate_similarity


class AlbumResolver:
    """
    Résolveur d'albums pour organiser et regrouper les tracks découverts.
    
    Fonctionnalités principales:
    - Regroupement automatique des tracks par album
    - Détection des singles/EPs/albums
    - Résolution des conflits de nommage
    - Enrichissement des métadonnées d'albums
    """
    
    def __init__(self, database: Database):
        self.db = database
        self.config = settings.get('albums', {})
        
        # Configuration par défaut
        self.min_tracks_for_album = self.config.get('min_tracks_for_album', 4)
        self.detect_singles = self.config.get('detect_singles', True)
        self.similarity_threshold = 0.85
        
        # Patterns pour détecter les types d'albums
        self.ep_patterns = [
            r'\bep\b', r'\bmini.?album\b', r'\bextended.?play\b'
        ]
        self.mixtape_patterns = [
            r'\bmixtape\b', r'\bmix.?tape\b', r'\btape\b'
        ]
        self.compilation_patterns = [
            r'\bcompilation\b', r'\bbest.?of\b', r'\bgreatest.?hits\b',
            r'\bcollection\b', r'\bantology\b'
        ]
        self.live_patterns = [
            r'\blive\b', r'\bconcert\b', r'\btour\b'
        ]
    
    def resolve_albums_for_tracks(self, tracks: List[Track], artist: Artist) -> List[Album]:
        """
        Résout les albums pour une liste de tracks d'un artiste.
        
        Args:
            tracks: Liste des tracks à organiser
            artist: Artiste concerné
            
        Returns:
            Liste des albums créés/mis à jour
        """
        print(f"🔍 Résolution des albums pour {artist.name} ({len(tracks)} tracks)")
        
        # Étape 1: Grouper les tracks par album potentiel
        album_groups = self._group_tracks_by_album(tracks)
        
        # Étape 2: Analyser et classifier chaque groupe
        resolved_albums = []
        
        for album_title, track_group in album_groups.items():
            try:
                album = self._resolve_single_album(album_title, track_group, artist)
                if album:
                    resolved_albums.append(album)
                    print(f"✅ Album résolu: {album.title} ({len(track_group)} tracks)")
            except Exception as e:
                print(f"❌ Erreur lors de la résolution de {album_title}: {e}")
        
        # Étape 3: Gérer les tracks sans album
        orphan_tracks = [t for t in tracks if not t.album_title]
        if orphan_tracks:
            print(f"🔍 Gestion de {len(orphan_tracks)} tracks orphelins")
            orphan_albums = self._handle_orphan_tracks(orphan_tracks, artist)
            resolved_albums.extend(orphan_albums)
        
        print(f"✅ Résolution terminée: {len(resolved_albums)} albums créés")
        return resolved_albums
    
    def _group_tracks_by_album(self, tracks: List[Track]) -> Dict[str, List[Track]]:
        """Groupe les tracks par nom d'album potentiel"""
        album_groups = defaultdict(list)
        
        for track in tracks:
            if track.album_title:
                # Normaliser le nom d'album pour le regroupement
                normalized_title = normalize_text(track.album_title)
                album_groups[normalized_title].append(track)
            else:
                # Tracks sans album -> groupe spécial
                album_groups["_ORPHANS_"].append(track)
        
        return dict(album_groups)
    
    def _resolve_single_album(self, album_title: str, tracks: List[Track], artist: Artist) -> Optional[Album]:
        """Résout un album spécifique à partir d'un groupe de tracks"""
        
        if not tracks:
            return None
        
        # Vérifier si l'album existe déjà en base
        existing_album = self._find_existing_album(album_title, artist.id)
        if existing_album:
            self._update_album_with_tracks(existing_album, tracks)
            return existing_album
        
        # Créer un nouvel album
        album = Album(
            title=self._get_best_album_title(tracks),
            artist_id=artist.id,
            artist_name=artist.name,
            track_count=len(tracks)
        )
        
        # Enrichir les métadonnées de l'album
        self._enrich_album_metadata(album, tracks)
        
        # Déterminer le type d'album
        album.album_type = self._detect_album_type(album, tracks)
        
        # Sauvegarder en base
        try:
            album_id = self.db.create_album(album)
            album.id = album_id
            
            # Mettre à jour les tracks avec l'ID de l'album
            for track in tracks:
                track.album_id = album_id
                track.album_title = album.title
                if track.id:
                    self.db.update_track(track)
            
            return album
            
        except Exception as e:
            print(f"❌ Erreur création album {album.title}: {e}")
            return None
    
    def _find_existing_album(self, album_title: str, artist_id: int) -> Optional[Album]:
        """Recherche un album existant par titre et artiste"""
        try:
            return self.db.get_album_by_title_and_artist(album_title, artist_id)
        except AttributeError:
            # Méthode non encore implémentée dans Database
            return None
    
    def _get_best_album_title(self, tracks: List[Track]) -> str:
        """Détermine le meilleur titre d'album à partir des tracks"""
        titles = [t.album_title for t in tracks if t.album_title]
        
        if not titles:
            return "Unknown Album"
        
        # Compter les occurrences
        title_counts = Counter(titles)
        most_common_title = title_counts.most_common(1)[0][0]
        
        # Si plusieurs variantes, choisir la plus propre
        similar_titles = [t for t in titles if calculate_similarity(t, most_common_title) > 0.9]
        
        # Préférer les titres les plus courts et propres
        best_title = min(similar_titles, key=lambda x: (len(x), x.count('('), x.count('[')))
        
        return best_title.strip()
    
    def _enrich_album_metadata(self, album: Album, tracks: List[Track]):
        """Enrichit les métadonnées de l'album à partir des tracks"""
        
        # Calculer la durée totale
        durations = [t.duration_seconds for t in tracks if t.duration_seconds]
        if durations:
            album.total_duration = sum(durations)
        
        # Détecter la date de sortie
        release_dates = [t.release_date for t in tracks if t.release_date]
        if release_dates:
            # Prendre la date la plus ancienne
            album.release_date = min(release_dates)
            try:
                album.release_year = int(album.release_date.split('-')[0])
            except (ValueError, IndexError):
                pass
        
        # Détecter le genre (mode basique)
        # Pour l'instant, utiliser le genre de l'artiste ou "rap" par défaut
        album.genre = "rap"
        
        # Récupérer les IDs externes si disponibles
        spotify_ids = [t.spotify_id for t in tracks if t.spotify_id]
        if spotify_ids:
            # Logic pour déduire l'album Spotify ID (à implémenter)
            pass
    
    def _detect_album_type(self, album: Album, tracks: List[Track]) -> AlbumType:
        """Détecte le type d'album basé sur le titre et le nombre de tracks"""
        
        title_lower = album.title.lower()
        track_count = len(tracks)
        
        # Single: 1-2 tracks ou contient "single" dans le titre
        if track_count <= 2 or any(pattern in title_lower for pattern in ['single', 'feat.', 'ft.']):
            return AlbumType.SINGLE
        
        # EP: 3-6 tracks ou patterns EP
        if track_count <= 6 or any(re.search(pattern, title_lower) for pattern in self.ep_patterns):
            return AlbumType.EP
        
        # Mixtape
        if any(re.search(pattern, title_lower) for pattern in self.mixtape_patterns):
            return AlbumType.MIXTAPE
        
        # Compilation
        if any(re.search(pattern, title_lower) for pattern in self.compilation_patterns):
            return AlbumType.COMPILATION
        
        # Live
        if any(re.search(pattern, title_lower) for pattern in self.live_patterns):
            return AlbumType.LIVE
        
        # Album: plus de 6 tracks par défaut
        if track_count >= self.min_tracks_for_album:
            return AlbumType.ALBUM
        
        # Cas par défaut: EP pour 3-6 tracks, Album pour plus
        return AlbumType.EP if track_count <= 6 else AlbumType.ALBUM
    
    def _handle_orphan_tracks(self, orphan_tracks: List[Track], artist: Artist) -> List[Album]:
        """Gère les tracks sans album en créant des albums dédiés"""
        
        if not orphan_tracks:
            return []
        
        resolved_albums = []
        
        # Stratégie 1: Grouper par année de sortie
        tracks_by_year = defaultdict(list)
        tracks_no_date = []
        
        for track in orphan_tracks:
            if track.release_year:
                tracks_by_year[track.release_year].append(track)
            else:
                tracks_no_date.append(track)
        
        # Créer des albums par année si assez de tracks
        for year, year_tracks in tracks_by_year.items():
            if len(year_tracks) >= 3:  # Seuil minimum pour créer un album
                album_title = f"{artist.name} - Singles {year}"
                album = self._create_singles_album(album_title, year_tracks, artist, year)
                if album:
                    resolved_albums.append(album)
            else:
                tracks_no_date.extend(year_tracks)
        
        # Créer un album "Singles" pour les tracks restants
        if tracks_no_date:
            if len(tracks_no_date) == 1:
                # Track unique -> créer un single
                track = tracks_no_date[0]
                album_title = f"{track.title} - Single"
                album = self._create_singles_album(album_title, [track], artist)
                if album:
                    resolved_albums.append(album)
            else:
                # Plusieurs tracks -> album "Singles"
                album_title = f"{artist.name} - Singles Collection"
                album = self._create_singles_album(album_title, tracks_no_date, artist)
                if album:
                    resolved_albums.append(album)
        
        return resolved_albums
    
    def _create_singles_album(self, title: str, tracks: List[Track], artist: Artist, year: Optional[int] = None) -> Optional[Album]:
        """Crée un album regroupant des singles"""
        
        album = Album(
            title=title,
            artist_id=artist.id,
            artist_name=artist.name,
            album_type=AlbumType.COMPILATION,
            track_count=len(tracks),
            release_year=year
        )
        
        # Enrichir avec les métadonnées des tracks
        self._enrich_album_metadata(album, tracks)
        
        try:
            album_id = self.db.create_album(album)
            album.id = album_id
            
            # Mettre à jour les tracks
            for track in tracks:
                track.album_id = album_id
                track.album_title = album.title
                if track.id:
                    self.db.update_track(track)
            
            return album
            
        except Exception as e:
            print(f"❌ Erreur création album singles {title}: {e}")
            return None
    
    def _update_album_with_tracks(self, album: Album, tracks: List[Track]):
        """Met à jour un album existant avec de nouveaux tracks"""
        
        # Mettre à jour le nombre de tracks
        album.track_count = len(tracks)
        
        # Recalculer les métadonnées
        self._enrich_album_metadata(album, tracks)
        
        # Sauvegarder les modifications
        try:
            self.db.update_album(album)
            
            # Mettre à jour les tracks
            for track in tracks:
                track.album_id = album.id
                track.album_title = album.title
                if track.id:
                    self.db.update_track(track)
                    
        except Exception as e:
            print(f"❌ Erreur mise à jour album {album.title}: {e}")
    
    def analyze_album_coverage(self, artist_id: int) -> Dict[str, any]:
        """Analyse la couverture des albums pour un artiste"""
        
        tracks = self.db.get_tracks_by_artist_id(artist_id)
        
        analysis = {
            'total_tracks': len(tracks),
            'tracks_with_album': len([t for t in tracks if t.album_id]),
            'tracks_without_album': len([t for t in tracks if not t.album_id]),
            'unique_albums': len(set(t.album_id for t in tracks if t.album_id)),
            'album_types': defaultdict(int),
            'tracks_by_album_type': defaultdict(list)
        }
        
        # Analyser par type d'album
        albums = set()
        for track in tracks:
            if track.album_id:
                # Récupérer l'album (méthode à implémenter dans Database)
                try:
                    album = self.db.get_album_by_id(track.album_id)
                    if album and album not in albums:
                        albums.add(album)
                        analysis['album_types'][album.album_type.value] += 1
                        analysis['tracks_by_album_type'][album.album_type.value].append(track)
                except AttributeError:
                    pass
        
        # Calculer les pourcentages
        if analysis['total_tracks'] > 0:
            analysis['coverage_percentage'] = (analysis['tracks_with_album'] / analysis['total_tracks']) * 100
        else:
            analysis['coverage_percentage'] = 0
        
        return analysis
    
    def suggest_album_improvements(self, artist_id: int) -> List[Dict[str, str]]:
        """Suggère des améliorations pour l'organisation des albums"""
        
        suggestions = []
        analysis = self.analyze_album_coverage(artist_id)
        
        # Suggestion 1: Tracks orphelins
        if analysis['tracks_without_album'] > 0:
            suggestions.append({
                'type': 'orphan_tracks',
                'message': f"{analysis['tracks_without_album']} tracks sans album détecté",
                'action': 'Regrouper en albums thématiques ou par période'
            })
        
        # Suggestion 2: Trop de singles
        if analysis['album_types'].get('single', 0) > 10:
            suggestions.append({
                'type': 'too_many_singles',
                'message': f"{analysis['album_types']['single']} singles détectés",
                'action': 'Regrouper les singles par période ou thème'
            })
        
        # Suggestion 3: Albums avec peu de tracks
        # Cette analyse nécessiterait plus de données de la base
        
        return suggestions
    
    def resolve_album_conflicts(self, tracks: List[Track]) -> List[Track]:
        """Résout les conflits de nommage d'albums"""
        
        # Grouper par similarité de nom d'album
        album_groups = defaultdict(list)
        
        for track in tracks:
            if track.album_title:
                # Trouver le groupe le plus similaire
                best_group = None
                best_similarity = 0
                
                for existing_title in album_groups.keys():
                    similarity = calculate_similarity(track.album_title, existing_title)
                    if similarity > best_similarity and similarity > self.similarity_threshold:
                        best_similarity = similarity
                        best_group = existing_title
                
                if best_group:
                    album_groups[best_group].append(track)
                else:
                    album_groups[track.album_title].append(track)
        
        # Unifier les noms d'albums dans chaque groupe
        resolved_tracks = []
        for album_title, group_tracks in album_groups.items():
            if len(group_tracks) > 1:
                # Choisir le meilleur nom d'album
                best_title = self._get_best_album_title(group_tracks)
                
                # Mettre à jour tous les tracks du groupe
                for track in group_tracks:
                    track.album_title = best_title
                    resolved_tracks.append(track)
            else:
                resolved_tracks.extend(group_tracks)
        
        return resolved_tracks