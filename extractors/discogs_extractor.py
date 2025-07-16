# extractors/discogs_extractor.py
import logging
import re
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

import discogs_client
from discogs_client.exceptions import HTTPError

from .base_extractor import BaseExtractor, ExtractionResult, ExtractorConfig
from models.enums import ExtractorType, CreditType, DataSource, CreditCategory
from models.entities import Track, Album, Artist, Credit
from core.exceptions import ExtractionError, RateLimitError, ValidationError
from config.settings import settings
from utils.text_utils import clean_text, normalize_title, extract_featuring_artists


class DiscogsExtractor(BaseExtractor):
    """
    Extracteur spécialisé pour Discogs.
    
    Responsabilités :
    - Extraction détaillée des crédits depuis Discogs
    - Informations d'albums avec personnel complet
    - Métadonnées de pressage et édition
    - Focus sur les crédits de production, mix, mastering (crucial pour le rap/hip-hop)
    """
    
    def __init__(self, config: Optional[ExtractorConfig] = None):
        super().__init__(ExtractorType.DISCOGS, config)
        
        # Configuration Discogs
        self.token = settings.discogs_token
        if not self.token:
            raise ExtractionError("Token Discogs manquant")
        
        # Client Discogs
        self.client = discogs_client.Client(
            'MusicDataExtractor/1.0',
            user_token=self.token
        )
        
        # Configuration spécifique à Discogs
        self.discogs_config = {
            'extract_all_credits': settings.get('credits.expand_all_credits', True),
            'prefer_original_release': settings.get('discogs.prefer_original_release', True),
            'include_unofficial_releases': settings.get('discogs.include_unofficial_releases', False),
            'max_search_results': settings.get('discogs.max_search_results', 20),
            'focus_hip_hop': settings.get('discogs.focus_hip_hop', True)
        }
        
        # Mapping des rôles Discogs vers nos types de crédits
        self.role_mappings = self._setup_role_mappings()
        
        self.logger.info("DiscogsExtractor initialisé")
    
    def _setup_role_mappings(self) -> Dict[str, CreditType]:
        """Configure le mapping des rôles Discogs vers nos types de crédits"""
        return {
            # Production (très important pour le rap/hip-hop)
            'producer': CreditType.PRODUCER,
            'executive producer': CreditType.EXECUTIVE_PRODUCER,
            'co-producer': CreditType.CO_PRODUCER,
            'additional production': CreditType.ADDITIONAL_PRODUCTION,
            'beats': CreditType.PRODUCER,
            'beat maker': CreditType.PRODUCER,
            'programmed by': CreditType.PRODUCER,
            
            # Technique (crucial pour la qualité)
            'mixed by': CreditType.MIXING,
            'mastered by': CreditType.MASTERING,
            'recorded by': CreditType.RECORDING,
            'engineer': CreditType.ENGINEERING,
            'recording engineer': CreditType.RECORDING,
            'mixing engineer': CreditType.MIXING,
            'mastering engineer': CreditType.MASTERING,
            
            # Instruments
            'guitar': CreditType.GUITAR,
            'bass': CreditType.BASS,
            'drums': CreditType.DRUMS,
            'piano': CreditType.PIANO,
            'keyboards': CreditType.KEYBOARD,
            'synthesizer': CreditType.KEYBOARD,
            'saxophone': CreditType.SAXOPHONE,
            'trumpet': CreditType.TRUMPET,
            'violin': CreditType.VIOLIN,
            
            # Vocal
            'vocals': CreditType.LEAD_VOCALS,
            'backing vocals': CreditType.BACKING_VOCALS,
            'rap': CreditType.RAP,
            'featuring': CreditType.FEATURING,
            'guest': CreditType.FEATURING,
            
            # Composition
            'written-by': CreditType.SONGWRITER,
            'composed by': CreditType.COMPOSER,
            'lyrics by': CreditType.LYRICIST,
            'music by': CreditType.COMPOSER,
            
            # Samples (important pour le hip-hop)
            'sampled': CreditType.SAMPLE,
            'interpolated': CreditType.INTERPOLATION,
            'contains sample': CreditType.SAMPLE,
            'based on': CreditType.SAMPLE,
        }
    
    def extract_track_info(self, track_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations d'un morceau depuis Discogs.
        
        Args:
            track_id: ID du morceau/release sur Discogs
            **kwargs: Options additionnelles
                - search_query: str - Requête de recherche si pas d'ID direct
                - artist_name: str - Nom de l'artiste pour filtrer
                - track_title: str - Titre du morceau pour filtrer
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        cache_key = self.get_cache_key("extract_track_info", track_id, **kwargs)
        
        def _extract():
            try:
                # Si on a une query de recherche, chercher d'abord
                if kwargs.get('search_query'):
                    search_result = self._search_track(
                        kwargs['search_query'],
                        kwargs.get('artist_name'),
                        kwargs.get('track_title')
                    )
                    if not search_result:
                        return ExtractionResult(
                            success=False,
                            error=f"Aucun résultat trouvé pour: {kwargs['search_query']}",
                            source=self.extractor_type.value
                        )
                    track_id = search_result['id']
                
                # Récupération de la release
                release_data = self._get_release_data(track_id)
                if not release_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Release {track_id} non trouvée",
                        source=self.extractor_type.value
                    )
                
                # Extraction des informations de track spécifique
                track_data = self._extract_track_from_release(
                    release_data,
                    kwargs.get('track_title'),
                    kwargs.get('track_number')
                )
                
                # Calcul du score de qualité
                quality_score = self.calculate_quality_score(track_data)
                
                return ExtractionResult(
                    success=True,
                    data=track_data,
                    source=self.extractor_type.value,
                    quality_score=quality_score
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def extract_album_info(self, album_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations complètes d'un album depuis Discogs.
        
        Args:
            album_id: ID de la release sur Discogs
            **kwargs: Options additionnelles
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        cache_key = self.get_cache_key("extract_album_info", album_id, **kwargs)
        
        def _extract():
            try:
                # Récupération de la release
                release_data = self._get_release_data(album_id)
                if not release_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Album {album_id} non trouvé",
                        source=self.extractor_type.value
                    )
                
                # Traitement des données d'album
                album_data = self._process_album_data(release_data)
                
                # Calcul du score de qualité
                quality_score = self._calculate_album_quality_score(album_data)
                
                return ExtractionResult(
                    success=True,
                    data=album_data,
                    source=self.extractor_type.value,
                    quality_score=quality_score
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def extract_artist_info(self, artist_id: str, **kwargs) -> ExtractionResult:
        """
        Extrait les informations d'un artiste depuis Discogs.
        
        Args:
            artist_id: ID de l'artiste sur Discogs
            **kwargs: Options additionnelles
        
        Returns:
            ExtractionResult: Résultat de l'extraction
        """
        cache_key = self.get_cache_key("extract_artist_info", artist_id, **kwargs)
        
        def _extract():
            try:
                artist_data = self._get_artist_data(artist_id)
                if not artist_data:
                    return ExtractionResult(
                        success=False,
                        error=f"Artiste {artist_id} non trouvé",
                        source=self.extractor_type.value
                    )
                
                # Traitement des données d'artiste
                processed_data = self._process_artist_data(artist_data)
                
                # Calcul du score de qualité
                quality_score = self._calculate_artist_quality_score(processed_data)
                
                return ExtractionResult(
                    success=True,
                    data=processed_data,
                    source=self.extractor_type.value,
                    quality_score=quality_score
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def search_tracks(self, query: str, limit: int = 50, **kwargs) -> ExtractionResult:
        """
        Recherche des morceaux sur Discogs.
        
        Args:
            query: Requête de recherche
            limit: Nombre maximum de résultats
            **kwargs: Options additionnelles
                - artist: str - Filtrer par artiste
                - genre: str - Filtrer par genre
                - year: int - Filtrer par année
        
        Returns:
            ExtractionResult: Résultat de la recherche
        """
        cache_key = self.get_cache_key("search_tracks", query, limit, **kwargs)
        
        def _extract():
            try:
                search_results = self._search_releases(query, limit, **kwargs)
                
                if not search_results:
                    return ExtractionResult(
                        success=False,
                        error=f"Aucun résultat pour: {query}",
                        source=self.extractor_type.value
                    )
                
                # Traitement des résultats
                processed_results = self._process_search_results(search_results)
                
                return ExtractionResult(
                    success=True,
                    data={'results': processed_results, 'total': len(processed_results)},
                    source=self.extractor_type.value,
                    quality_score=0.8
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def _get_release_data(self, release_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les données d'une release depuis Discogs"""
        try:
            self.rate_limiter.wait_if_needed()
            
            # Récupération de la release
            release = self.client.release(release_id)
            
            # Conversion en dictionnaire
            release_data = {
                'id': release.id,
                'title': release.title,
                'artists': [{'name': artist.name, 'id': artist.id} for artist in release.artists],
                'formats': [format.name for format in release.formats],
                'year': release.year,
                'released': release.released,
                'country': release.country,
                'labels': [{'name': label.name, 'id': label.id} for label in release.labels],
                'genres': release.genres,
                'styles': release.styles,
                'tracklist': [],
                'credits': [],
                'notes': release.notes,
                'data_quality': release.data_quality,
                'master_id': getattr(release, 'master_id', None),
                'master_url': getattr(release, 'master_url', None),
                'images': [{'uri': img['uri'], 'type': img['type']} for img in getattr(release, 'images', [])],
                'videos': [{'uri': video['uri'], 'title': video['title']} for video in getattr(release, 'videos', [])]
            }
            
            # Extraction de la tracklist avec positions et durées
            if hasattr(release, 'tracklist'):
                for track in release.tracklist:
                    track_info = {
                        'position': track.position,
                        'title': track.title,
                        'duration': track.duration,
                        'type_': getattr(track, 'type_', 'track'),
                        'artists': []
                    }
                    
                    # Artistes spécifiques à ce track
                    if hasattr(track, 'artists'):
                        track_info['artists'] = [{'name': artist.name, 'id': artist.id} for artist in track.artists]
                    
                    # Extraperformers et credits pour ce track
                    if hasattr(track, 'extraartists'):
                        track_info['extraartists'] = []
                        for extraartist in track.extraartists:
                            track_info['extraartists'].append({
                                'name': extraartist.name,
                                'role': extraartist.role,
                                'tracks': getattr(extraartist, 'tracks', ''),
                                'id': extraartist.id
                            })
                    
                    release_data['tracklist'].append(track_info)
            
            # Extraction des crédits globaux (extraartists)
            if hasattr(release, 'extraartists'):
                for extraartist in release.extraartists:
                    credit_info = {
                        'name': extraartist.name,
                        'role': extraartist.role,
                        'tracks': getattr(extraartist, 'tracks', ''),
                        'id': extraartist.id
                    }
                    release_data['credits'].append(credit_info)
            
            return release_data
            
        except HTTPError as e:
            if e.status_code == 429:
                raise RateLimitError("Rate limit Discogs atteint")
            self.logger.error(f"Erreur HTTP Discogs pour release {release_id}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération release {release_id}: {e}")
            return None
    
    def _get_artist_data(self, artist_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les données d'un artiste depuis Discogs"""
        try:
            self.rate_limiter.wait_if_needed()
            
            artist = self.client.artist(artist_id)
            
            return {
                'id': artist.id,
                'name': artist.name,
                'real_name': getattr(artist, 'real_name', ''),
                'profile': getattr(artist, 'profile', ''),
                'urls': getattr(artist, 'urls', []),
                'aliases': [alias.name for alias in getattr(artist, 'aliases', [])],
                'groups': [group.name for group in getattr(artist, 'groups', [])],
                'members': [member.name for member in getattr(artist, 'members', [])],
                'images': [{'uri': img['uri'], 'type': img['type']} for img in getattr(artist, 'images', [])],
                'data_quality': getattr(artist, 'data_quality', 'Unknown')
            }
            
        except HTTPError as e:
            if e.status_code == 429:
                raise RateLimitError("Rate limit Discogs atteint")
            self.logger.error(f"Erreur HTTP Discogs pour artiste {artist_id}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération artiste {artist_id}: {e}")
            return None
    
    def _search_releases(self, query: str, limit: int, **kwargs) -> Optional[List[Dict[str, Any]]]:
        """Effectue une recherche de releases sur Discogs"""
        try:
            self.rate_limiter.wait_if_needed()
            
            # Paramètres de recherche
            search_params = {
                'query': query,
                'type': 'release',
                'per_page': min(limit, 100)  # Discogs limite à 100
            }
            
            # Filtres additionnels
            if kwargs.get('artist'):
                search_params['artist'] = kwargs['artist']
            if kwargs.get('genre'):
                search_params['genre'] = kwargs['genre']
            if kwargs.get('year'):
                search_params['year'] = kwargs['year']
            
            # Si focus hip-hop activé, filtrer par genre
            if self.discogs_config['focus_hip_hop']:
                if 'genre' not in search_params:
                    search_params['genre'] = 'Hip Hop'
            
            # Effectuer la recherche
            search_results = self.client.search(**search_params)
            
            results = []
            for result in search_results[:limit]:
                result_data = {
                    'id': result.id,
                    'title': result.title,
                    'artist': getattr(result, 'artist', ''),
                    'year': getattr(result, 'year', None),
                    'format': getattr(result, 'format', []),
                    'label': getattr(result, 'label', []),
                    'catno': getattr(result, 'catno', ''),
                    'genre': getattr(result, 'genre', []),
                    'style': getattr(result, 'style', []),
                    'country': getattr(result, 'country', ''),
                    'thumb': getattr(result, 'thumb', ''),
                    'resource_url': getattr(result, 'resource_url', ''),
                    'community': getattr(result, 'community', {}),
                    'type': 'release'
                }
                results.append(result_data)
            
            return results
            
        except HTTPError as e:
            if e.status_code == 429:
                raise RateLimitError("Rate limit Discogs atteint")
            self.logger.error(f"Erreur HTTP lors de la recherche '{query}': {e}")
            return None
        except Exception as e:
            self.logger.error(f"Erreur lors de la recherche '{query}': {e}")
            return None
    
    def _search_track(self, query: str, artist_name: Optional[str] = None, track_title: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Recherche un track spécifique"""
        search_results = self._search_releases(query, 20, artist=artist_name)
        
        if not search_results:
            return None
        
        # Si on a un titre de track, chercher dans les tracklists
        if track_title:
            for result in search_results:
                release_data = self._get_release_data(str(result['id']))
                if release_data and 'tracklist' in release_data:
                    for track in release_data['tracklist']:
                        if self._titles_match(track['title'], track_title):
                            result['track_info'] = track
                            return result
        
        # Sinon retourner le premier résultat
        return search_results[0] if search_results else None
    
    def _titles_match(self, title1: str, title2: str, threshold: float = 0.8) -> bool:
        """Vérifie si deux titres correspondent (avec tolérance)"""
        # Normalisation simple
        t1 = normalize_title(title1)
        t2 = normalize_title(title2)
        
        # Correspondance exacte
        if t1 == t2:
            return True
        
        # Correspondance avec score de similarité (simplifiée)
        words1 = set(t1.split())
        words2 = set(t2.split())
        
        if not words1 or not words2:
            return False
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold
    
    def _extract_track_from_release(self, release_data: Dict[str, Any], track_title: Optional[str] = None, track_number: Optional[int] = None) -> Dict[str, Any]:
        """Extrait les informations d'un track spécifique depuis une release"""
        track_data = {
            'discogs_release_id': release_data['id'],
            'album_title': release_data['title'],
            'album_year': release_data['year'],
            'album_country': release_data['country'],
            'album_genres': release_data['genres'],
            'album_styles': release_data['styles'],
            'album_labels': release_data['labels'],
            'album_formats': release_data['formats'],
            'credits': [],
            'tracks': [],
            'raw_data': release_data
        }
        
        # Artistes principaux de l'album
        if release_data['artists']:
            track_data['album_artists'] = [artist['name'] for artist in release_data['artists']]
            track_data['primary_artist'] = release_data['artists'][0]['name']
        
        # Si on recherche un track spécifique
        target_track = None
        if track_title or track_number:
            for track in release_data['tracklist']:
                match = False
                
                if track_title and self._titles_match(track['title'], track_title):
                    match = True
                elif track_number and track['position']:
                    # Parser la position (peut être "1", "A1", "1-1", etc.)
                    pos_num = self._extract_track_number(track['position'])
                    if pos_num == track_number:
                        match = True
                
                if match:
                    target_track = track
                    break
        
        # Traitement du track trouvé ou de tous les tracks
        tracks_to_process = [target_track] if target_track else release_data['tracklist']
        
        for track in tracks_to_process:
            if not track:
                continue
            
            track_info = {
                'title': track['title'],
                'position': track['position'],
                'duration': track['duration'],
                'duration_seconds': self._parse_duration(track['duration']),
                'type': track.get('type_', 'track'),
                'artists': track.get('artists', []),
                'credits': []
            }
            
            # Crédits spécifiques au track
            if 'extraartists' in track:
                for extraartist in track['extraartists']:
                    credit = self._process_credit(extraartist, track_specific=True)
                    if credit:
                        track_info['credits'].append(credit)
            
            track_data['tracks'].append(track_info)
        
        # Crédits globaux de l'album/release
        for credit_raw in release_data['credits']:
            credit = self._process_credit(credit_raw, track_specific=False)
            if credit:
                track_data['credits'].append(credit)
        
        # Métadonnées d'extraction
        track_data['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'extractor': self.extractor_type.value,
            'data_quality': release_data.get('data_quality', 'Unknown'),
            'source_url': f"https://www.discogs.com/release/{release_data['id']}"
        }
        
        return track_data
    
    def _process_credit(self, extraartist: Dict[str, Any], track_specific: bool = False) -> Optional[Dict[str, Any]]:
        """Traite un crédit depuis les données Discogs"""
        name = extraartist.get('name', '').strip()
        role = extraartist.get('role', '').strip().lower()
        tracks = extraartist.get('tracks', '').strip()
        
        if not name or not role:
            return None
        
        # Mapping du rôle vers notre type de crédit
        credit_type = self._map_role_to_credit_type(role)
        
        # Détection de la catégorie
        credit_category = self._detect_credit_category(credit_type, role)
        
        # Nettoyage du nom
        clean_name = self._clean_credit_name(name)
        
        credit = {
            'person_name': clean_name,
            'role_detail': role,
            'credit_type': credit_type.value,
            'credit_category': credit_category.value,
            'tracks_specified': tracks,
            'is_track_specific': track_specific,
            'data_source': DataSource.DISCOGS.value,
            'discogs_artist_id': extraartist.get('id'),
            'raw_role': extraartist.get('role', '')  # Role original pour debug
        }
        
        # Détection d'instrument si applicable
        instrument = self._extract_instrument_from_role(role)
        if instrument:
            credit['instrument'] = instrument
        
        return credit
    
    def _map_role_to_credit_type(self, role: str) -> CreditType:
        """Mappe un rôle Discogs vers notre type de crédit"""
        role_lower = role.lower().strip()
        
        # Recherche exacte d'abord
        if role_lower in self.role_mappings:
            return self.role_mappings[role_lower]
        
        # Recherche par mots-clés pour les rôles composés
        for keyword, credit_type in self.role_mappings.items():
            if keyword in role_lower:
                return credit_type
        
        # Patterns spéciaux pour le hip-hop
        if any(word in role_lower for word in ['beat', 'producer', 'prod']):
            return CreditType.PRODUCER
        elif any(word in role_lower for word in ['mix', 'mixed']):
            return CreditType.MIXING
        elif any(word in role_lower for word in ['master', 'mastered']):
            return CreditType.MASTERING
        elif any(word in role_lower for word in ['rap', 'mc', 'emcee']):
            return CreditType.RAP
        elif any(word in role_lower for word in ['feat', 'guest', 'featuring']):
            return CreditType.FEATURING
        elif any(word in role_lower for word in ['sample', 'interpolat']):
            return CreditType.SAMPLE
        
        return CreditType.OTHER
    
    def _detect_credit_category(self, credit_type: CreditType, role: str) -> CreditCategory:
        """Détecte la catégorie de crédit basée sur le type et le rôle"""
        # Production
        if credit_type in [CreditType.PRODUCER, CreditType.EXECUTIVE_PRODUCER, 
                          CreditType.CO_PRODUCER, CreditType.ADDITIONAL_PRODUCTION]:
            return CreditCategory.PRODUCER
        
        # Technique
        elif credit_type in [CreditType.MIXING, CreditType.MASTERING, 
                           CreditType.RECORDING, CreditType.ENGINEERING]:
            return CreditCategory.TECHNICAL
        
        # Instruments
        elif credit_type in [CreditType.GUITAR, CreditType.BASS, CreditType.DRUMS,
                           CreditType.PIANO, CreditType.KEYBOARD, CreditType.SAXOPHONE,
                           CreditType.TRUMPET, CreditType.VIOLIN]:
            return CreditCategory.INSTRUMENT
        
        # Vocal
        elif credit_type in [CreditType.LEAD_VOCALS, CreditType.BACKING_VOCALS, CreditType.RAP]:
            return CreditCategory.VOCAL
        
        # Featuring
        elif credit_type == CreditType.FEATURING:
            return CreditCategory.FEATURING
        
        # Composition
        elif credit_type in [CreditType.SONGWRITER, CreditType.COMPOSER, CreditType.LYRICIST]:
            return CreditCategory.COMPOSER
        
        # Samples
        elif credit_type in [CreditType.SAMPLE, CreditType.INTERPOLATION]:
            return CreditCategory.SAMPLE
        
        # Par défaut
        return CreditCategory.TECHNICAL
    
    def _extract_instrument_from_role(self, role: str) -> Optional[str]:
        """Extrait l'instrument depuis le rôle si possible"""
        role_lower = role.lower()
        
        instruments = [
            'guitar', 'bass', 'drums', 'piano', 'keyboard', 'synthesizer',
            'saxophone', 'trumpet', 'violin', 'cello', 'flute', 'clarinet',
            'organ', 'harmonica', 'accordion', 'banjo', 'mandolin'
        ]
        
        for instrument in instruments:
            if instrument in role_lower:
                return instrument
        
        return None
    
    def _clean_credit_name(self, name: str) -> str:
        """Nettoie le nom d'une personne dans les crédits"""
        # Supprimer les numéros entre parenthèses (variants Discogs)
        name = re.sub(r'\s*\(\d+\)\s*, '', name)
        
        # Supprimer les préfixes courants
        name = re.sub(r'^(The |DJ |Dr\. |Mr\. |Ms\. )', '', name, flags=re.IGNORECASE)
        
        # Nettoyer les espaces multiples
        name = re.sub(r'\s+', ' ', name)
        
        return name.strip()
    
    def _extract_track_number(self, position: str) -> Optional[int]:
        """Extrait le numéro de track depuis la position Discogs"""
        if not position:
            return None
        
        # Patterns courants: "1", "A1", "1-1", "CD1-1", etc.
        match = re.search(r'(\d+), position)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        
        return None
    
    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """Parse une durée Discogs (format MM:SS) vers secondes"""
        if not duration_str:
            return None
        
        try:
            # Format MM:SS ou M:SS
            if ':' in duration_str:
                parts = duration_str.split(':')
                if len(parts) == 2:
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    return minutes * 60 + seconds
        except (ValueError, IndexError):
            pass
        
        return None
    
    def _process_album_data(self, release_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et structure les données d'un album depuis Discogs"""
        album_data = {
            'discogs_id': release_data['id'],
            'title': release_data['title'],
            'artists': [artist['name'] for artist in release_data['artists']],
            'primary_artist': release_data['artists'][0]['name'] if release_data['artists'] else None,
            'year': release_data['year'],
            'released': release_data['released'],
            'country': release_data['country'],
            'genres': release_data['genres'],
            'styles': release_data['styles'],
            'labels': [label['name'] for label in release_data['labels']],
            'formats': release_data['formats'],
            'data_quality': release_data['data_quality'],
            'track_count': len(release_data['tracklist']),
            'total_duration_seconds': 0,
            'tracks': [],
            'credits': [],
            'images': release_data['images'],
            'videos': release_data['videos'],
            'notes': release_data.get('notes', ''),
            'master_id': release_data.get('master_id'),
            'source_url': f"https://www.discogs.com/release/{release_data['id']}"
        }
        
        # Traitement des tracks
        total_duration = 0
        for track in release_data['tracklist']:
            track_info = {
                'position': track['position'],
                'title': track['title'],
                'duration': track['duration'],
                'duration_seconds': self._parse_duration(track['duration']),
                'type': track.get('type_', 'track'),
                'artists': [artist['name'] for artist in track.get('artists', [])],
                'credits': []
            }
            
            # Ajouter à la durée totale
            if track_info['duration_seconds']:
                total_duration += track_info['duration_seconds']
            
            # Crédits spécifiques au track
            if 'extraartists' in track:
                for extraartist in track['extraartists']:
                    credit = self._process_credit(extraartist, track_specific=True)
                    if credit:
                        track_info['credits'].append(credit)
            
            album_data['tracks'].append(track_info)
        
        album_data['total_duration_seconds'] = total_duration
        
        # Crédits globaux de l'album
        for credit_raw in release_data['credits']:
            credit = self._process_credit(credit_raw, track_specific=False)
            if credit:
                album_data['credits'].append(credit)
        
        # Métadonnées d'extraction
        album_data['extraction_metadata'] = {
            'extracted_at': datetime.now().isoformat(),
            'extractor': self.extractor_type.value,
            'data_quality': release_data.get('data_quality', 'Unknown')
        }
        
        return album_data
    
    def _process_artist_data(self, artist_data: Dict[str, Any]) -> Dict[str, Any]:
        """Traite et structure les données d'un artiste depuis Discogs"""
        return {
            'discogs_id': artist_data['id'],
            'name': artist_data['name'],
            'real_name': artist_data.get('real_name', ''),
            'profile': artist_data.get('profile', ''),
            'urls': artist_data.get('urls', []),
            'aliases': artist_data.get('aliases', []),
            'groups': artist_data.get('groups', []),
            'members': artist_data.get('members', []),
            'images': artist_data.get('images', []),
            'data_quality': artist_data.get('data_quality', 'Unknown'),
            'source_url': f"https://www.discogs.com/artist/{artist_data['id']}",
            'extraction_metadata': {
                'extracted_at': datetime.now().isoformat(),
                'extractor': self.extractor_type.value
            }
        }
    
    def _process_search_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Traite les résultats de recherche depuis Discogs"""
        processed = []
        
        for result in results:
            processed_result = {
                'discogs_id': result['id'],
                'title': result['title'],
                'artist': result.get('artist', ''),
                'year': result.get('year'),
                'formats': result.get('format', []),
                'labels': result.get('label', []),
                'catalog_number': result.get('catno', ''),
                'genres': result.get('genre', []),
                'styles': result.get('style', []),
                'country': result.get('country', ''),
                'thumbnail': result.get('thumb', ''),
                'resource_url': result.get('resource_url', ''),
                'type': result.get('type', 'release'),
                'community_stats': result.get('community', {}),
                'source': self.extractor_type.value
            }
            
            # Score de pertinence basique
            relevance_score = self._calculate_search_relevance(result)
            processed_result['relevance_score'] = relevance_score
            
            processed.append(processed_result)
        
        # Trier par score de pertinence
        processed.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return processed
    
    def _calculate_search_relevance(self, result: Dict[str, Any]) -> float:
        """Calcule un score de pertinence pour un résultat de recherche"""
        score = 0.0
        
        # Bonus pour la qualité des données
        data_quality = result.get('community', {}).get('rating', {}).get('average', 0)
        if data_quality:
            score += data_quality * 0.3
        
        # Bonus pour les genres hip-hop si focus activé
        if self.discogs_config['focus_hip_hop']:
            genres = result.get('genre', [])
            if any('hip hop' in genre.lower() for genre in genres):
                score += 2.0
            elif any(genre.lower() in ['rap', 'hip-hop', 'hip hop'] for genre in genres):
                score += 1.5
        
        # Bonus pour les formats standards
        formats = result.get('format', [])
        if any(fmt in ['CD', 'Vinyl', 'Digital'] for fmt in formats):
            score += 0.5
        
        # Pénalité pour les formats non standards
        if any(fmt in ['Promo', 'White Label', 'Test Pressing'] for fmt in formats):
            score -= 0.3
        
        # Bonus pour les releases récentes (hip-hop évolue vite)
        year = result.get('year')
        if year and year >= 2000:
            score += (year - 2000) * 0.01  # Petit bonus croissant
        
        return max(0.0, score)
    
    def _calculate_album_quality_score(self, album_data: Dict[str, Any]) -> float:
        """Calcule un score de qualité pour un album"""
        score = 0.0
        max_score = 0.0
        
        # Présence des champs de base (30%)
        base_fields = ['title', 'primary_artist', 'year', 'track_count']
        for field in base_fields:
            max_score += 0.3 / len(base_fields)
            if album_data.get(field):
                score += 0.3 / len(base_fields)
        
        # Qualité des métadonnées (25%)
        metadata_fields = ['genres', 'styles', 'labels', 'country', 'formats']
        for field in metadata_fields:
            max_score += 0.25 / len(metadata_fields)
            if album_data.get(field):
                score += 0.25 / len(metadata_fields)
        
        # Présence de crédits (35%)
        max_score += 0.35
        credits = album_data.get('credits', [])
        if credits:
            # Score basé sur le nombre et la diversité des crédits
            credit_score = min(len(credits) / 10.0, 1.0)  # Normaliser sur 10 crédits
            
            # Bonus pour la diversité des types de crédits
            credit_types = set(credit.get('credit_type', '') for credit in credits)
            diversity_bonus = min(len(credit_types) / 5.0, 0.3)  # Max 30% bonus
            
            score += 0.35 * (credit_score + diversity_bonus)
        
        # Qualité des données Discogs (10%)
        max_score += 0.1
        data_quality = album_data.get('data_quality', '')
        quality_scores = {
            'Complete and Correct': 1.0,
            'Correct': 0.8,
            'Needs Vote': 0.6,
            'Needs Minor Changes': 0.4,
            'Needs Major Changes': 0.2,
            'Entirely Incorrect': 0.0
        }
        if data_quality in quality_scores:
            score += 0.1 * quality_scores[data_quality]
        
        return min(score / max_score if max_score > 0 else 0.0, 1.0)
    
    def _calculate_artist_quality_score(self, artist_data: Dict[str, Any]) -> float:
        """Calcule un score de qualité pour un artiste"""
        score = 0.0
        max_score = 1.0
        
        # Présence des champs de base
        if artist_data.get('name'):
            score += 0.3
        if artist_data.get('profile'):
            score += 0.2
        if artist_data.get('real_name'):
            score += 0.1
        
        # Présence d'informations supplémentaires
        if artist_data.get('urls'):
            score += 0.1
        if artist_data.get('aliases'):
            score += 0.1
        if artist_data.get('images'):
            score += 0.1
        
        # Qualité des données
        data_quality = artist_data.get('data_quality', '')
        quality_scores = {
            'Complete and Correct': 0.1,
            'Correct': 0.08,
            'Needs Vote': 0.06,
            'Needs Minor Changes': 0.04,
            'Needs Major Changes': 0.02,
            'Entirely Incorrect': 0.0
        }
        if data_quality in quality_scores:
            score += quality_scores[data_quality]
        
        return min(score / max_score, 1.0)
    
    def search_by_artist_and_title(self, artist_name: str, track_title: str, album_title: Optional[str] = None) -> ExtractionResult:
        """
        Recherche spécialisée par artiste et titre de morceau.
        
        Args:
            artist_name: Nom de l'artiste
            track_title: Titre du morceau
            album_title: Titre de l'album (optionnel)
        
        Returns:
            ExtractionResult: Résultat de la recherche
        """
        cache_key = self.get_cache_key("search_by_artist_and_title", artist_name, track_title, album_title)
        
        def _extract():
            try:
                # Construction de la requête
                if album_title:
                    query = f'artist:"{artist_name}" release:"{album_title}"'
                else:
                    query = f'artist:"{artist_name}" "{track_title}"'
                
                # Recherche
                search_results = self._search_releases(query, 10, artist=artist_name)
                
                if not search_results:
                    return ExtractionResult(
                        success=False,
                        error=f"Aucun résultat pour {artist_name} - {track_title}",
                        source=self.extractor_type.value
                    )
                
                # Analyser les résultats pour trouver le bon morceau
                best_match = None
                best_score = 0.0
                
                for result in search_results[:5]:  # Analyser les 5 premiers
                    release_data = self._get_release_data(str(result['id']))
                    if not release_data:
                        continue
                    
                    # Chercher le track dans la tracklist
                    for track in release_data['tracklist']:
                        similarity_score = self._calculate_track_similarity(
                            track['title'], track_title,
                            release_data['artists'], artist_name
                        )
                        
                        if similarity_score > best_score:
                            best_score = similarity_score
                            best_match = {
                                'release': result,
                                'release_data': release_data,
                                'track': track,
                                'similarity_score': similarity_score
                            }
                
                if not best_match or best_score < 0.6:  # Seuil de confiance
                    return ExtractionResult(
                        success=False,
                        error=f"Aucune correspondance fiable trouvée (score: {best_score:.2f})",
                        source=self.extractor_type.value
                    )
                
                # Extraire les données du meilleur match
                track_data = self._extract_track_from_release(
                    best_match['release_data'],
                    track_title
                )
                
                track_data['similarity_score'] = best_score
                track_data['matched_track'] = best_match['track']
                
                return ExtractionResult(
                    success=True,
                    data=track_data,
                    source=self.extractor_type.value,
                    quality_score=self.calculate_quality_score(track_data)
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def _calculate_track_similarity(self, discogs_title: str, target_title: str, 
                                   discogs_artists: List[Dict[str, Any]], target_artist: str) -> float:
        """Calcule la similarité entre un track Discogs et le track recherché"""
        score = 0.0
        
        # Similarité du titre (60% du score)
        title_similarity = self._text_similarity(
            normalize_title(discogs_title),
            normalize_title(target_title)
        )
        score += title_similarity * 0.6
        
        # Similarité de l'artiste (40% du score)
        artist_similarity = 0.0
        target_artist_norm = normalize_title(target_artist)
        
        for artist in discogs_artists:
            artist_name_norm = normalize_title(artist['name'])
            similarity = self._text_similarity(artist_name_norm, target_artist_norm)
            artist_similarity = max(artist_similarity, similarity)
        
        score += artist_similarity * 0.4
        
        return score
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calcule la similarité entre deux textes (Jaccard simplifiée)"""
        if not text1 or not text2:
            return 0.0
        
        # Conversion en sets de mots
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        # Coefficient de Jaccard
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def get_master_release_versions(self, master_id: str) -> ExtractionResult:
        """
        Récupère toutes les versions d'un master release.
        
        Args:
            master_id: ID du master release sur Discogs
        
        Returns:
            ExtractionResult: Liste des versions
        """
        cache_key = self.get_cache_key("get_master_release_versions", master_id)
        
        def _extract():
            try:
                self.rate_limiter.wait_if_needed()
                
                master = self.client.master(master_id)
                versions = []
                
                for version in master.versions[:20]:  # Limiter à 20 versions
                    version_data = {
                        'id': version.id,
                        'title': version.title,
                        'format': getattr(version, 'format', []),
                        'label': getattr(version, 'label', ''),
                        'catno': getattr(version, 'catno', ''),
                        'year': getattr(version, 'year', None),
                        'country': getattr(version, 'country', ''),
                        'status': getattr(version, 'status', ''),
                        'resource_url': getattr(version, 'resource_url', ''),
                        'thumb': getattr(version, 'thumb', '')
                    }
                    versions.append(version_data)
                
                return ExtractionResult(
                    success=True,
                    data={'master_id': master_id, 'versions': versions},
                    source=self.extractor_type.value,
                    quality_score=0.9
                )
                
            except Exception as e:
                return ExtractionResult(
                    success=False,
                    error=str(e),
                    source=self.extractor_type.value
                )
        
        return self.extract_with_cache(cache_key, _extract)
    
    def get_recommended_version(self, master_id: str, prefer_cd: bool = True) -> Optional[str]:
        """
        Recommande la meilleure version d'un master release.
        
        Args:
            master_id: ID du master release
            prefer_cd: Préférer les versions CD
        
        Returns:
            ID de la version recommandée ou None
        """
        versions_result = self.get_master_release_versions(master_id)
        
        if not versions_result.success or not versions_result.data:
            return None
        
        versions = versions_result.data['versions']
        
        if not versions:
            return None
        
        # Scoring des versions
        scored_versions = []
        for version in versions:
            score = 0.0
            
            # Bonus pour CD si préféré
            formats = version.get('format', [])
            if prefer_cd and 'CD' in formats:
                score += 3.0
            elif 'Vinyl' in formats:
                score += 2.0
            elif 'Digital' in formats:
                score += 1.5
            
            # Pénalité pour les formats non-standards
            if any(fmt in formats for fmt in ['Promo', 'White Label', 'Test Pressing']):
                score -= 2.0
            
            # Bonus pour les releases officielles
            if version.get('status') == 'Accepted':
                score += 1.0
            
            # Bonus pour les années récentes (meilleure qualité d'enregistrement)
            year = version.get('year')
            if year and year >= 1990:
                score += (year - 1990) * 0.01
            
            scored_versions.append((score, version))
        
        # Trier par score et retourner le meilleur
        scored_versions.sort(key=lambda x: x[0], reverse=True)
        
        return str(scored_versions[0][1]['id']) if scored_versions else None