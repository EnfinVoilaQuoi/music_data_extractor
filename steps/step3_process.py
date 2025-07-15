# steps/step3_process.py
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

# IMPORTS ABSOLUS
from models.entities import Track, Artist, QualityReport
from models.enums import SessionStatus, ExtractionStatus, QualityLevel
from core.database import Database
from core.session_manager import SessionManager, get_session_manager
from core.exceptions import ExtractionError
from config.settings import settings
from utils.text_utils import normalize_text

@dataclass
class ProcessingStats:
    """Statistiques du traitement"""
    total_tracks: int = 0
    tracks_processed: int = 0
    tracks_cleaned: int = 0
    duplicates_removed: int = 0
    quality_reports_generated: int = 0
    processing_time_seconds: float = 0.0

class ProcessingStep:
    """
    Étape 3 : Traitement et nettoyage des données.
    
    Responsabilités :
    - Nettoyage et normalisation des données
    - Détection et suppression des doublons
    - Génération de rapports de qualité
    - Validation des données
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None,
                 database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        
        # Composants
        self.session_manager = session_manager or get_session_manager()
        self.database = database or Database()
        
        # Configuration
        self.config = {
            'enable_duplicate_detection': settings.get('processing.enable_duplicate_detection', True),
            'enable_quality_check': settings.get('processing.enable_quality_check', True),
            'enable_data_cleaning': settings.get('processing.enable_data_cleaning', True),
            'similarity_threshold': settings.get('processing.similarity_threshold', 0.9)
        }
        
        self.logger.info("ProcessingStep initialisé")
    
    def process_session_data(self, session_id: str) -> ProcessingStats:
        """
        Traite les données d'une session.
        
        Args:
            session_id: ID de la session à traiter
            
        Returns:
            Statistiques de traitement
        """
        start_time = datetime.now()
        stats = ProcessingStats()
        
        try:
            self.logger.info(f"🧹 Début traitement des données pour session: {session_id}")
            
            # Récupérer la session
            session = self.session_manager.get_session(session_id)
            if not session:
                raise ExtractionError(f"Session {session_id} non trouvée")
            
            # Récupérer les tracks
            artist = self.database.get_artist_by_name(session.artist_name)
            if not artist:
                raise ExtractionError(f"Artiste '{session.artist_name}' non trouvé")
            
            tracks = self.database.get_tracks_by_artist_id(artist.id)
            stats.total_tracks = len(tracks)
            
            # Mettre à jour le statut
            session.current_step = "processing_started"
            self.session_manager.update_session(session)
            
            # Nettoyage des données
            if self.config['enable_data_cleaning']:
                cleaned_count = self._clean_tracks_data(tracks)
                stats.tracks_cleaned = cleaned_count
                self.logger.info(f"✨ {cleaned_count} morceaux nettoyés")
            
            # Détection des doublons
            if self.config['enable_duplicate_detection']:
                duplicates_removed = self._remove_duplicates(tracks)
                stats.duplicates_removed = duplicates_removed
                self.logger.info(f"🗑️ {duplicates_removed} doublons supprimés")
            
            # Génération des rapports de qualité
            if self.config['enable_quality_check']:
                quality_reports = self._generate_quality_reports(tracks)
                stats.quality_reports_generated = len(quality_reports)
                self.logger.info(f"📊 {len(quality_reports)} rapports de qualité générés")
            
            stats.tracks_processed = len(tracks)
            
            # Calcul du temps de traitement
            end_time = datetime.now()
            stats.processing_time_seconds = (end_time - start_time).total_seconds()
            
            # Mettre à jour le statut final
            session.current_step = "processing_completed"
            self.session_manager.update_session(session)
            
            self.logger.info(f"✅ Traitement terminé en {stats.processing_time_seconds:.1f}s")
            
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors du traitement: {e}")
            raise ExtractionError(f"Erreur traitement session {session_id}: {e}")
    
    def _clean_tracks_data(self, tracks: List[Track]) -> int:
        """Nettoie les données des tracks"""
        cleaned_count = 0
        
        for track in tracks:
            original_title = track.title
            
            # Normaliser le titre
            if track.title:
                normalized_title = normalize_text(track.title).strip()
                if normalized_title != track.title:
                    track.title = normalized_title
                    cleaned_count += 1
            
            # Nettoyer les featuring artists
            if track.featuring_artists:
                cleaned_featuring = []
                for artist in track.featuring_artists:
                    cleaned_artist = normalize_text(artist).strip()
                    if cleaned_artist and cleaned_artist not in cleaned_featuring:
                        cleaned_featuring.append(cleaned_artist)
                track.featuring_artists = cleaned_featuring
            
            # Sauvegarder si modifié
            if track.title != original_title:
                track.updated_at = datetime.now()
                self.database.update_track(track)
        
        return cleaned_count
    
    def _remove_duplicates(self, tracks: List[Track]) -> int:
        """Supprime les doublons de tracks"""
        duplicates_removed = 0
        seen_tracks = set()
        tracks_to_remove = []
        
        for track in tracks:
            # Créer une signature unique pour le track
            signature = self._create_track_signature(track)
            
            if signature in seen_tracks:
                tracks_to_remove.append(track)
                duplicates_removed += 1
            else:
                seen_tracks.add(signature)
        
        # Supprimer les doublons de la base
        for track in tracks_to_remove:
            self.database.delete_track(track.id)
            self.logger.debug(f"Doublon supprimé: {track.title}")
        
        return duplicates_removed
    
    def _create_track_signature(self, track: Track) -> str:
        """Crée une signature unique pour un track"""
        # Normaliser les éléments de comparaison
        title = normalize_text(track.title).lower().strip()
        artist = normalize_text(track.artist_name).lower().strip()
        
        # Créer la signature
        signature = f"{title}:{artist}"
        
        # Ajouter l'album si disponible
        if track.album_name:
            album = normalize_text(track.album_name).lower().strip()
            signature += f":{album}"
        
        return signature
    
    def _generate_quality_reports(self, tracks: List[Track]) -> List[QualityReport]:
        """Génère des rapports de qualité pour les tracks"""
        quality_reports = []
        
        for track in tracks:
            report = self._analyze_track_quality(track)
            if report:
                # Sauvegarder le rapport
                self.database.save_quality_report(report)
                quality_reports.append(report)
        
        return quality_reports
    
    def _analyze_track_quality(self, track: Track) -> Optional[QualityReport]:
        """Analyse la qualité d'un track"""
        try:
            report = QualityReport(
                track_id=track.id,
                artist_id=track.artist_id,
                overall_score=0.0,
                created_at=datetime.now()
            )
            
            # Critères de qualité
            quality_score = 0.0
            max_score = 100.0
            
            # Titre présent et valide (20 points)
            if track.title and len(track.title.strip()) > 0:
                quality_score += 20
            else:
                report.missing_fields.append("title")
            
            # Artiste présent (15 points)
            if track.artist_name and len(track.artist_name.strip()) > 0:
                quality_score += 15
            else:
                report.missing_fields.append("artist_name")
            
            # Données Genius (15 points)
            if track.genius_id:
                quality_score += 15
            else:
                report.missing_fields.append("genius_id")
            
            # Durée présente (10 points)
            if track.duration and track.duration > 0:
                quality_score += 10
            else:
                report.missing_fields.append("duration")
            
            # BPM présent (10 points)
            if track.bpm and track.bpm > 0:
                quality_score += 10
            else:
                report.missing_fields.append("bpm")
            
            # Album présent (10 points)
            if track.album_name:
                quality_score += 10
            else:
                report.missing_fields.append("album")
            
            # Paroles présentes (10 points)
            if track.has_lyrics and track.lyrics:
                quality_score += 10
            else:
                report.missing_fields.append("lyrics")
            
            # Crédits présents (10 points)
            if track.credits and len(track.credits) > 0:
                quality_score += 10
            else:
                report.missing_fields.append("credits")
            
            # Calcul du score final
            report.overall_score = quality_score / max_score
            
            # Déterminer le niveau de qualité
            if report.overall_score >= 0.9:
                report.quality_level = QualityLevel.EXCELLENT
            elif report.overall_score >= 0.75:
                report.quality_level = QualityLevel.GOOD
            elif report.overall_score >= 0.5:
                report.quality_level = QualityLevel.AVERAGE
            elif report.overall_score >= 0.25:
                report.quality_level = QualityLevel.POOR
            else:
                report.quality_level = QualityLevel.VERY_POOR
            
            return report
            
        except Exception as e:
            self.logger.error(f"Erreur analyse qualité track {track.title}: {e}")
            return None