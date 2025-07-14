# steps/step1_discover.py
import logging
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from dataclasses import dataclass

from ..models.entities import Track, Artist, Session
from ..models.enums import SessionStatus, ExtractionStatus, DataSource, ProcessingStep
from ..discovery.genius_discovery import GeniusDiscovery, DiscoveryResult
from ..extractors.web_scrapers.rapedia_scraper import RapediaScraper
from ..core.database import Database
from ..core.session_manager import SessionManager, get_session_manager
from ..core.exceptions import ExtractionError, ArtistNotFoundError
from ..config.settings import settings
from ..utils.text_utils import clean_artist_name, normalize_title

@dataclass
class DiscoveryStats:
    """Statistiques de la découverte"""
    total_found: int = 0
    genius_found: int = 0
    rapedia_found: int = 0
    duplicates_removed: int = 0
    final_count: int = 0
    discovery_time_seconds: float = 0.0

class DiscoveryStep:
    """
    Étape 1 : Découverte des morceaux d'un artiste.
    
    Responsabilités :
    - Recherche de l'artiste sur différentes sources
    - Découverte de tous ses morceaux
    - Déduplication et consolidation
    - Création des entités de base en base de données
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None, 
                 database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        
        # Composants
        self.session_manager = session_manager or get_session_manager()
        self.database = database or Database()
        
        # Découvreurs
        self.genius_discovery = GeniusDiscovery()
        self.rapedia_scraper = RapediaScraper()
        
        # Configuration
        self.config = {
            'max_tracks_per_source': settings.get('discovery.max_tracks_per_source', 200),
            'enable_rapedia': settings.get('discovery.enable_rapedia', True),
            'enable_genius': settings.get('discovery.enable_genius', True),
            'similarity_threshold': settings.get('discovery.similarity_threshold', 0.85),
            'prefer_verified_sources': settings.get('discovery.prefer_verified_sources', True)
        }
        
        self.logger.info("DiscoveryStep initialisé")
    
    def discover_artist_tracks(self, artist_name: str, 
                             session_id: Optional[str] = None,
                             max_tracks: Optional[int] = None) -> Tuple[List[Track], DiscoveryStats]:
        """
        Découvre tous les morceaux d'un artiste depuis toutes les sources.
        
        Args:
            artist_name: Nom de l'artiste à découvrir
            session_id: ID de session existante ou None pour en créer une nouvelle
            max_tracks: Limite du nombre de morceaux (optionnel)
            
        Returns:
            Tuple[List[Track], DiscoveryStats]: Morceaux découverts et statistiques
        """
        start_time = datetime.now()
        
        # Gestion de la session
        if session_id:
            session = self.session_manager.get_session(session_id)
            if not session:
                raise ExtractionError(f"Session {session_id} non trouvée")
        else:
            session_id = self.session_manager.create_session(
                artist_name, 
                metadata={'step': ProcessingStep.DISCOVERY.value}
            )
            session = self.session_manager.get_session(session_id)
        
        try:
            self.logger.info(f"🔍 Début de la découverte pour '{artist_name}'")
            
            # Mise à jour de la session
            self.session_manager.update_session(
                session_id, 
                current_step="discovery_started"
            )
            
            # 1. Recherche et validation de l'artiste
            artist = self._find_or_create_artist(artist_name)
            
            # 2. Découverte depuis les différentes sources
            all_tracks = []
            stats = DiscoveryStats()
            
            # Genius Discovery
            if self.config['enable_genius']:
                genius_tracks = self._discover_from_genius(artist_name, max_tracks)
                all_tracks.extend(genius_tracks)
                stats.genius_found = len(genius_tracks)
                
                self.session_manager.update_session(
                    session_id,
                    current_step="genius_discovery_completed"
                )
            
            # Rapedia Discovery (pour le rap français)
            if self.config['enable_rapedia'] and self._is_french_rap_artist(artist_name):
                rapedia_tracks = self._discover_from_rapedia(artist_name, max_tracks)
                all_tracks.extend(rapedia_tracks)
                stats.rapedia_found = len(rapedia_tracks)
                
                self.session_manager.update_session(
                    session_id,
                    current_step="rapedia_discovery_completed"
                )
            
            stats.total_found = len(all_tracks)
            
            # 3. Déduplication et consolidation
            unique_tracks = self._deduplicate_tracks(all_tracks)
            stats.duplicates_removed = stats.total_found - len(unique_tracks)
            
            # 4. Limitation si demandée
            if max_tracks and len(unique_tracks) > max_tracks:
                unique_tracks = self._prioritize_tracks(unique_tracks)[:max_tracks]
            
            stats.final_count = len(unique_tracks)
            
            # 5. Association à l'artiste et sauvegarde
            final_tracks = self._finalize_tracks(unique_tracks, artist)
            
            # 6. Sauvegarde en base de données
            saved_tracks = self._save_tracks_to_database(final_tracks, session_id)
            
            # Calcul du temps
            end_time = datetime.now()
            stats.discovery_time_seconds = (end_time - start_time).total_seconds()
            
            # Mise à jour finale de la session
            self.session_manager.update_session(
                session_id,
                current_step="discovery_completed",
                total_tracks_found=stats.final_count,
                tracks_processed=0  # Sera mis à jour dans les étapes suivantes
            )
            
            self.logger.info(
                f"✅ Découverte terminée pour '{artist_name}': "
                f"{stats.final_count} morceaux trouvés "
                f"(Genius: {stats.genius_found}, Rapedia: {stats.rapedia_found}, "
                f"doublons supprimés: {stats.duplicates_removed})"
            )
            
            return saved_tracks, stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de la découverte pour '{artist_name}': {e}")
            
            # Marquer la session comme échouée
            self.session_manager.fail_session(session_id, str(e))
            
            raise ExtractionError(f"Échec de la découverte pour {artist_name}: {e}")
    
    def _find_or_create_artist(self, artist_name: str) -> Artist:
        """Trouve ou crée un artiste en base de données"""
        try:
            # Recherche d'un artiste existant
            existing_artist = self.database.get_artist_by_name(artist_name)
            
            if existing_artist:
                self.logger.info(f"Artiste trouvé en base: {existing_artist.name}")
                return existing_artist
            
            # Création d'un nouvel artiste
            new_artist = Artist(
                name=artist_name,
                extraction_status=ExtractionStatus.IN_PROGRESS,
                created_at=datetime.now()
            )
            
            artist_id = self.database.create_artist(new_artist)
            new_artist.id = artist_id
            
            self.logger.info(f"Nouvel artiste créé: {artist_name} (ID: {artist_id})")
            return new_artist
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la création/recherche d'artiste: {e}")
            raise ExtractionError(f"Impossible de traiter l'artiste {artist_name}: {e}")
    
    def _discover_from_genius(self, artist_name: str, max_tracks: Optional[int]) -> List[Dict[str, Any]]:
        """Découvre les morceaux depuis Genius"""
        try:
            self.logger.info(f"🎵 Découverte Genius pour {artist_name}")
            
            limit = max_tracks or self.config['max_tracks_per_source']
            
            result = self.genius_discovery.discover_artist_tracks(artist_name, limit)
            
            if not result.success:
                self.logger.warning(f"Échec découverte Genius: {result.error}")
                return []
            
            # Conversion des données Genius en format standardisé
            tracks = []
            for track_data in result.tracks:
                standardized_track = self._standardize_genius_track(track_data, artist_name)
                if standardized_track:
                    tracks.append(standardized_track)
            
            self.logger.info(f"Genius: {len(tracks)} morceaux trouvés")
            return tracks
            
        except Exception as e:
            self.logger.error(f"Erreur découverte Genius: {e}")
            return []
    
    def _discover_from_rapedia(self, artist_name: str, max_tracks: Optional[int]) -> List[Dict[str, Any]]:
        """Découvre les morceaux depuis Rapedia"""
        try:
            self.logger.info(f"🎵 Découverte Rapedia pour {artist_name}")
            
            # Recherche de l'artiste sur Rapedia
            search_results = self.rapedia_scraper.search_artist(artist_name)
            
            if not search_results:
                self.logger.info(f"Artiste non trouvé sur Rapedia: {artist_name}")
                return []
            
            # Prendre le meilleur match
            best_match = search_results[0]
            if best_match['match_score'] < 0.7:
                self.logger.info(f"Score de correspondance trop faible sur Rapedia: {best_match['match_score']}")
                return []
            
            # Scraper les morceaux
            limit = max_tracks or self.config['max_tracks_per_source']
            raw_tracks = self.rapedia_scraper.scrape_artist_tracks(best_match['url'], limit)
            
            # Conversion en format standardisé
            tracks = []
            for track_data in raw_tracks:
                standardized_track = self._standardize_rapedia_track(track_data, artist_name)
                if standardized_track:
                    tracks.append(standardized_track)
            
            self.logger.info(f"Rapedia: {len(tracks)} morceaux trouvés")
            return tracks
            
        except Exception as e:
            self.logger.error(f"Erreur découverte Rapedia: {e}")
            return []
    
    def _standardize_genius_track(self, track_data: Dict[str, Any], artist_name: str) -> Optional[Dict[str, Any]]:
        """Standardise un morceau depuis les données Genius"""
        try:
            standardized = {
                'title': track_data.get('title', '').strip(),
                'artist_name': artist_name,
                'genius_id': track_data.get('genius_id'),
                'genius_url': track_data.get('url'),
                'release_date': track_data.get('release_date'),
                'featuring_artists': track_data.get('featured_artists', []),
                'source': DataSource.GENIUS.value,
                'discovery_metadata': {
                    'pageviews': track_data.get('stats', {}).get('pageviews'),
                    'hot': track_data.get('stats', {}).get('hot', False),
                    'header_image': track_data.get('header_image')
                },
                'raw_data': track_data
            }
            
            # Validation minimale
            if not standardized['title'] or len(standardized['title']) < 2:
                return None
            
            return standardized
            
        except Exception as e:
            self.logger.warning(f"Erreur standardisation track Genius: {e}")
            return None
    
    def _standardize_rapedia_track(self, track_data: Dict[str, Any], artist_name: str) -> Optional[Dict[str, Any]]:
        """Standardise un morceau depuis les données Rapedia"""
        try:
            standardized = {
                'title': track_data.get('title', '').strip(),
                'artist_name': artist_name,
                'rapedia_url': track_data.get('url'),
                'album': track_data.get('album'),
                'release_date': track_data.get('release_date'),
                'release_year': track_data.get('release_year'),
                'genre': track_data.get('genre'),
                'source': DataSource.RAPEDIA.value,
                'discovery_metadata': {
                    'cover_image': track_data.get('cover_image'),
                    'external_links': track_data.get('external_links', [])
                },
                'credits': track_data.get('credits', []),  # Rapedia a souvent des crédits dès la découverte
                'raw_data': track_data
            }
            
            # Validation minimale
            if not standardized['title'] or len(standardized['title']) < 2:
                return None
            
            return standardized
            
        except Exception as e:
            self.logger.warning(f"Erreur standardisation track Rapedia: {e}")
            return None
    
    def _deduplicate_tracks(self, tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Déduplique les morceaux trouvés sur plusieurs sources"""
        seen_tracks = {}
        unique_tracks = []
        
        for track in tracks:
            # Génération d'une clé de déduplication
            title_normalized = normalize_title(track.get('title', ''))
            artist_normalized = clean_artist_name(track.get('artist_name', ''))
            
            dedup_key = f"{artist_normalized}_{title_normalized}"
            
            if dedup_key in seen_tracks:
                # Fusion des données si doublon trouvé
                existing_track = seen_tracks[dedup_key]
                merged_track = self._merge_duplicate_tracks(existing_track, track)
                seen_tracks[dedup_key] = merged_track
            else:
                seen_tracks[dedup_key] = track
        
        # Conversion en liste
        unique_tracks = list(seen_tracks.values())
        
        self.logger.info(f"Déduplication: {len(tracks)} -> {len(unique_tracks)} morceaux")
        return unique_tracks
    
    def _merge_duplicate_tracks(self, track1: Dict[str, Any], track2: Dict[str, Any]) -> Dict[str, Any]:
        """Fusionne deux morceaux dupliqués en privilégiant les meilleures données"""
        
        # Priorité des sources (Rapedia > Genius pour la fiabilité)
        source_priority = {
            DataSource.RAPEDIA.value: 1,
            DataSource.GENIUS.value: 2,
            DataSource.MANUAL.value: 3
        }
        
        primary_track = track1
        secondary_track = track2
        
        # Déterminer le morceau principal basé sur la priorité de source
        if (source_priority.get(track2.get('source'), 999) < 
            source_priority.get(track1.get('source'), 999)):
            primary_track = track2
            secondary_track = track1
        
        # Fusionner les données
        merged = primary_track.copy()
        
        # Ajouter les données manquantes du secondaire
        for key, value in secondary_track.items():
            if not merged.get(key) and value:
                merged[key] = value
        
        # Fusionner les métadonnées de découverte
        if 'discovery_metadata' in secondary_track:
            merged_metadata = merged.get('discovery_metadata', {})
            merged_metadata.update(secondary_track['discovery_metadata'])
            merged['discovery_metadata'] = merged_metadata
        
        # Fusionner les crédits si disponibles
        credits1 = primary_track.get('credits', [])
        credits2 = secondary_track.get('credits', [])
        if credits1 or credits2:
            merged['credits'] = credits1 + credits2
        
        # Marquer comme fusionné
        merged['merged_from_sources'] = [
            primary_track.get('source'),
            secondary_track.get('source')
        ]
        
        return merged
    
    def _prioritize_tracks(self, tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Priorise les morceaux selon différents critères"""
        
        def calculate_priority_score(track: Dict[str, Any]) -> float:
            score = 0.0
            
            # Bonus pour source fiable
            if track.get('source') == DataSource.RAPEDIA.value:
                score += 2.0
            elif track.get('source') == DataSource.GENIUS.value:
                score += 1.0
            
            # Bonus pour morceaux avec des crédits déjà présents
            if track.get('credits'):
                score += 1.5
            
            # Bonus pour morceaux avec album
            if track.get('album'):
                score += 1.0
            
            # Bonus pour morceaux récents
            if track.get('release_year'):
                year = track['release_year']
                if year >= 2020:
                    score += 1.0
                elif year >= 2015:
                    score += 0.5
            
            # Bonus pour popularité (Genius)
            pageviews = track.get('discovery_metadata', {}).get('pageviews')
            if pageviews:
                if pageviews > 100000:
                    score += 1.5
                elif pageviews > 10000:
                    score += 1.0
                elif pageviews > 1000:
                    score += 0.5
            
            # Bonus pour morceaux "hot" sur Genius
            if track.get('discovery_metadata', {}).get('hot'):
                score += 0.5
            
            # Bonus pour featuring (collaborations intéressantes)
            if track.get('featuring_artists'):
                score += 0.5
            
            return score
        
        # Tri par score de priorité décroissant
        prioritized = sorted(tracks, key=calculate_priority_score, reverse=True)
        
        self.logger.info(f"Priorisation: {len(tracks)} morceaux triés par pertinence")
        return prioritized
    
    def _finalize_tracks(self, tracks: List[Dict[str, Any]], artist: Artist) -> List[Track]:
        """Finalise les morceaux en créant les entités Track"""
        finalized_tracks = []
        
        for track_data in tracks:
            try:
                # Création de l'entité Track
                track = Track(
                    title=track_data.get('title', '').strip(),
                    artist_id=artist.id,
                    artist_name=artist.name,
                    album_title=track_data.get('album'),
                    genius_id=track_data.get('genius_id'),
                    genius_url=track_data.get('genius_url'),
                    release_date=track_data.get('release_date'),
                    release_year=track_data.get('release_year'),
                    extraction_status=ExtractionStatus.PENDING,
                    data_sources=[DataSource(track_data.get('source', 'manual'))],
                    featuring_artists=track_data.get('featuring_artists', []),
                    created_at=datetime.now()
                )
                
                # Ajouter les URLs spécifiques aux sources
                if track_data.get('rapedia_url'):
                    track.lastfm_url = track_data['rapedia_url']  # Réutiliser ce champ pour Rapedia
                
                # Ajouter les crédits si déjà découverts (Rapedia notamment)
                if track_data.get('credits'):
                    from ..models.entities import Credit
                    from ..models.enums import CreditType, CreditCategory
                    
                    for credit_data in track_data['credits']:
                        try:
                            credit = Credit(
                                track_id=None,  # Sera mis à jour après sauvegarde
                                credit_category=CreditCategory(credit_data.get('credit_category', 'other')),
                                credit_type=CreditType(credit_data.get('credit_type', 'other')),
                                person_name=credit_data.get('person_name', ''),
                                role_detail=credit_data.get('role_detail'),
                                data_source=DataSource(credit_data.get('source', 'manual')),
                                extraction_date=datetime.now()
                            )
                            track.credits.append(credit)
                        except Exception as e:
                            self.logger.warning(f"Erreur création crédit: {e}")
                
                finalized_tracks.append(track)
                
            except Exception as e:
                self.logger.warning(f"Erreur finalisation track '{track_data.get('title')}': {e}")
                continue
        
        self.logger.info(f"Finalisation: {len(finalized_tracks)} morceaux créés")
        return finalized_tracks
    
    def _save_tracks_to_database(self, tracks: List[Track], session_id: str) -> List[Track]:
        """Sauvegarde les morceaux en base de données"""
        saved_tracks = []
        
        for track in tracks:
            try:
                # Vérifier si le morceau existe déjà
                existing_track = None
                if track.genius_id:
                    existing_track = self.database.get_track_by_genius_id(int(track.genius_id))
                
                if existing_track:
                    # Mise à jour du morceau existant
                    self.logger.debug(f"Morceau existant trouvé: {track.title}")
                    
                    # Fusionner les données
                    self._update_existing_track(existing_track, track)
                    self.database.update_track(existing_track)
                    saved_tracks.append(existing_track)
                else:
                    # Nouveau morceau
                    track_id = self.database.create_track(track)
                    track.id = track_id
                    
                    # Sauvegarder les crédits
                    for credit in track.credits:
                        credit.track_id = track_id
                        self.database.create_credit(credit)
                    
                    saved_tracks.append(track)
                    self.logger.debug(f"Nouveau morceau sauvegardé: {track.title}")
                
            except Exception as e:
                self.logger.error(f"Erreur sauvegarde track '{track.title}': {e}")
                continue
        
        self.logger.info(f"Sauvegarde: {len(saved_tracks)} morceaux en base")
        return saved_tracks
    
    def _update_existing_track(self, existing_track: Track, new_track: Track):
        """Met à jour un morceau existant avec de nouvelles données"""
        # Mise à jour des champs si vides ou meilleurs
        if not existing_track.album_title and new_track.album_title:
            existing_track.album_title = new_track.album_title
        
        if not existing_track.release_date and new_track.release_date:
            existing_track.release_date = new_track.release_date
            
        if not existing_track.release_year and new_track.release_year:
            existing_track.release_year = new_track.release_year
        
        # Fusionner les sources de données
        for source in new_track.data_sources:
            if source not in existing_track.data_sources:
                existing_track.data_sources.append(source)
        
        # Fusionner les featuring artists
        for featuring in new_track.featuring_artists:
            if featuring not in existing_track.featuring_artists:
                existing_track.featuring_artists.append(featuring)
        
        # Fusionner les crédits
        existing_credit_keys = set(
            (c.person_name.lower(), c.credit_type) for c in existing_track.credits
        )
        
        for new_credit in new_track.credits:
            credit_key = (new_credit.person_name.lower(), new_credit.credit_type)
            if credit_key not in existing_credit_keys:
                existing_track.credits.append(new_credit)
        
        existing_track.updated_at = datetime.now()
    
    def _is_french_rap_artist(self, artist_name: str) -> bool:
        """Détermine si un artiste est probablement du rap français"""
        # Liste d'artistes rap français connus (échantillon)
        french_rap_indicators = [
            'mc', 'dj', 'nekfeu', 'orelsan', 'pnl', 'damso', 'ninho', 'aya nakamura',
            'jul', 'soprano', 'bigflo', 'oli', 'freeze corleone', 'laylow', 'lomepal',
            'alpha wann', 'koba lad', 'soso maness', 'gradur', 'booba', 'kaaris'
        ]
        
        artist_lower = artist_name.lower()
        
        # Vérification directe
        if any(indicator in artist_lower for indicator in french_rap_indicators):
            return True
        
        # Autres heuristiques (noms français, etc.)
        french_patterns = ['mc ', 'dj ', ' feat ', ' ft ']
        if any(pattern in artist_lower for pattern in french_patterns):
            return True
        
        # Par défaut, essayer Rapedia pour tous (il filtrera lui-même)
        return True
    
    def get_discovery_summary(self, session_id: str) -> Dict[str, Any]:
        """Retourne un résumé de la découverte pour une session"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                return {}
            
            # Statistiques de base depuis la session
            summary = {
                'session_id': session_id,
                'artist_name': session.artist_name,
                'status': session.status.value,
                'total_tracks_found': session.total_tracks_found,
                'current_step': session.current_step,
                'created_at': session.created_at.isoformat() if session.created_at else None,
                'updated_at': session.updated_at.isoformat() if session.updated_at else None
            }
            
            # Ajout des statistiques détaillées si disponibles
            if session.metadata:
                summary.update(session.metadata)
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Erreur récupération résumé découverte: {e}")
            return {}
    
    def resume_discovery(self, session_id: str) -> Tuple[List[Track], DiscoveryStats]:
        """Reprend une découverte interrompue"""
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                raise ExtractionError(f"Session {session_id} non trouvée")
            
            if session.status != SessionStatus.PAUSED:
                raise ExtractionError(f"Session {session_id} n'est pas en pause")
            
            self.logger.info(f"Reprise de la découverte pour la session {session_id}")
            
            # Reprendre selon l'étape actuelle
            current_step = session.current_step
            
            if current_step in ['discovery_started', 'genius_discovery_completed']:
                # Relancer la découverte complète
                return self.discover_artist_tracks(
                    session.artist_name, 
                    session_id=session_id
                )
            else:
                # Découverte déjà terminée, récupérer les morceaux existants
                artist = self.database.get_artist_by_name(session.artist_name)
                if artist:
                    tracks = self.database.get_tracks_by_artist_id(artist.id)
                    stats = DiscoveryStats(final_count=len(tracks))
                    return tracks, stats
                else:
                    raise ExtractionError("Artiste non trouvé en base")
                    
        except Exception as e:
            self.logger.error(f"Erreur reprise découverte: {e}")
            raise ExtractionError(f"Impossible de reprendre la découverte: {e}")
    
    def validate_discovery_results(self, tracks: List[Track]) -> Dict[str, Any]:
        """Valide les résultats de la découverte"""
        validation_report = {
            'total_tracks': len(tracks),
            'valid_tracks': 0,
            'tracks_with_credits': 0,
            'tracks_with_albums': 0,
            'tracks_with_features': 0,
            'issues': [],
            'recommendations': []
        }
        
        for track in tracks:
            is_valid = True
            
            # Validation du titre
            if not track.title or len(track.title.strip()) < 2:
                validation_report['issues'].append(f"Titre invalide: '{track.title}'")
                is_valid = False
            
            # Validation de l'artiste
            if not track.artist_name:
                validation_report['issues'].append(f"Artiste manquant pour '{track.title}'")
                is_valid = False
            
            if is_valid:
                validation_report['valid_tracks'] += 1
            
            # Comptages
            if track.credits:
                validation_report['tracks_with_credits'] += 1
            
            if track.album_title:
                validation_report['tracks_with_albums'] += 1
            
            if track.featuring_artists:
                validation_report['tracks_with_features'] += 1
        
        # Recommandations
        if validation_report['tracks_with_credits'] == 0:
            validation_report['recommendations'].append(
                "Aucun crédit trouvé - considérer l'extraction depuis Genius Web"
            )
        
        if validation_report['tracks_with_albums'] < len(tracks) * 0.5:
            validation_report['recommendations'].append(
                "Peu d'informations d'albums - considérer l'extraction depuis Spotify/Discogs"
            )
        
        # Score de qualité global
        quality_score = validation_report['valid_tracks'] / max(len(tracks), 1)
        validation_report['quality_score'] = quality_score
        validation_report['quality_level'] = self._determine_quality_level(quality_score)
        
        return validation_report
    
    def _determine_quality_level(self, score: float) -> str:
        """Détermine le niveau de qualité basé sur le score"""
        if score >= 0.9:
            return "Excellent"
        elif score >= 0.75:
            return "Bon"
        elif score >= 0.5:
            return "Moyen"
        elif score >= 0.25:
            return "Faible"
        else:
            return "Très faible"
    
    def cleanup_failed_discovery(self, session_id: str):
        """Nettoie une découverte échouée"""
        try:
            session = self.session_manager.get_session(session_id)
            if session and session.status == SessionStatus.FAILED:
                # Supprimer les morceaux partiellement créés si nécessaire
                # (Implémentation selon les besoins)
                self.logger.info(f"Nettoyage de la découverte échouée {session_id}")
        except Exception as e:
            self.logger.error(f"Erreur nettoyage découverte: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du module de découverte"""
        return {
            'genius_stats': self.genius_discovery.get_stats(),
            'rapedia_stats': self.rapedia_scraper.get_stats(),
            'config': self.config
        }