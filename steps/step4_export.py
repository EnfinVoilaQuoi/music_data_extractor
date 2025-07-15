# steps/step4_export.py
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

# IMPORTS ABSOLUS
from models.entities import Track, Artist
from models.enums import SessionStatus, ExportFormat
from core.database import Database
from core.session_manager import SessionManager, get_session_manager
from core.exceptions import ExtractionError, ExportError
from config.settings import settings
from utils.export_utils import ExportManager

@dataclass
class ExportStats:
    """Statistiques d'export"""
    total_tracks: int = 0
    exported_tracks: int = 0
    export_formats: List[str] = None
    export_files: List[str] = None
    export_time_seconds: float = 0.0
    total_size_bytes: int = 0
    
    def __post_init__(self):
        if self.export_formats is None:
            self.export_formats = []
        if self.export_files is None:
            self.export_files = []

class ExportStep:
    """
    Étape 4 : Export des données dans différents formats.
    
    Responsabilités :
    - Export multi-formats (JSON, CSV, HTML, Excel)
    - Génération de rapports détaillés
    - Options d'export personnalisables
    - Gestion des fichiers de sortie
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None,
                 database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        
        # Composants
        self.session_manager = session_manager or get_session_manager()
        self.database = database or Database()
        self.export_manager = ExportManager()
        
        # Configuration
        self.config = {
            'default_formats': settings.get('export.default_formats', ['JSON', 'CSV']),
            'include_lyrics': settings.get('export.include_lyrics', True),
            'include_credits': settings.get('export.include_credits', True),
            'include_quality_reports': settings.get('export.include_quality_reports', False),
            'output_dir': settings.exports_dir
        }
        
        # Créer le dossier d'export si nécessaire
        self.config['output_dir'].mkdir(parents=True, exist_ok=True)
        
        self.logger.info("ExportStep initialisé")
    
    def export_session_data(self, session_id: str, 
                           formats: Optional[List[str]] = None,
                           options: Optional[Dict[str, Any]] = None) -> ExportStats:
        """
        Exporte les données d'une session.
        
        Args:
            session_id: ID de la session à exporter
            formats: Liste des formats d'export (défaut: config)
            options: Options d'export personnalisées
            
        Returns:
            Statistiques d'export
        """
        start_time = datetime.now()
        stats = ExportStats()
        
        try:
            self.logger.info(f"📤 Début export pour session: {session_id}")
            
            # Récupérer la session
            session = self.session_manager.get_session(session_id)
            if not session:
                raise ExportError(f"Session {session_id} non trouvée")
            
            # Récupérer les données
            artist = self.database.get_artist_by_name(session.artist_name)
            if not artist:
                raise ExportError(f"Artiste '{session.artist_name}' non trouvé")
            
            tracks = self.database.get_tracks_by_artist_id(artist.id)
            albums = self.database.get_albums_by_artist_id(artist.id)
            
            stats.total_tracks = len(tracks)
            
            # Configuration des formats
            export_formats = formats or self.config['default_formats']
            export_options = {**self.config, **(options or {})}
            
            # Mettre à jour le statut
            session.current_step = "export_started"
            self.session_manager.update_session(session)
            
            # Export dans chaque format
            for format_name in export_formats:
                try:
                    export_file = self._export_format(
                        artist, tracks, albums, format_name, export_options, session_id
                    )
                    
                    if export_file:
                        stats.export_files.append(str(export_file))
                        stats.export_formats.append(format_name)
                        
                        # Calculer la taille du fichier
                        if Path(export_file).exists():
                            stats.total_size_bytes += Path(export_file).stat().st_size
                        
                        self.logger.info(f"✅ Export {format_name} terminé: {export_file}")
                    
                except Exception as e:
                    self.logger.error(f"❌ Erreur export {format_name}: {e}")
                    continue
            
            stats.exported_tracks = len(tracks)
            
            # Calcul du temps d'export
            end_time = datetime.now()
            stats.export_time_seconds = (end_time - start_time).total_seconds()
            
            # Mettre à jour le statut final
            session.current_step = "export_completed"
            self.session_manager.update_session(session)
            
            self.logger.info(f"✅ Export terminé: {len(stats.export_files)} fichiers générés en {stats.export_time_seconds:.1f}s")
            
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de l'export: {e}")
            raise ExportError(f"Erreur export session {session_id}: {e}")
    
    def _export_format(self, artist: Artist, tracks: List[Track], albums: List,
                      format_name: str, options: Dict[str, Any], session_id: str) -> Optional[str]:
        """Exporte dans un format spécifique"""
        try:
            # Nom du fichier
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{artist.name}_{session_id[:8]}_{timestamp}.{format_name.lower()}"
            output_path = self.config['output_dir'] / filename
            
            if format_name.upper() == "JSON":
                return self._export_json(artist, tracks, albums, output_path, options)
            elif format_name.upper() == "CSV":
                return self._export_csv(artist, tracks, output_path, options)
            elif format_name.upper() == "HTML":
                return self._export_html(artist, tracks, albums, output_path, options)
            elif format_name.upper() == "EXCEL":
                return self._export_excel(artist, tracks, albums, output_path, options)
            else:
                self.logger.warning(f"Format non supporté: {format_name}")
                return None
                
        except Exception as e:
            self.logger.error(f"Erreur export {format_name}: {e}")
            return None
    
    def _export_json(self, artist: Artist, tracks: List[Track], albums: List,
                    output_path: Path, options: Dict[str, Any]) -> str:
        """Export au format JSON"""
        import json
        
        # Préparer les données
        export_data = {
            "artist": artist.to_dict(),
            "export_info": {
                "format": "JSON",
                "generated_at": datetime.now().isoformat(),
                "total_tracks": len(tracks),
                "total_albums": len(albums),
                "options": {
                    "include_lyrics": options.get('include_lyrics', True),
                    "include_credits": options.get('include_credits', True)
                }
            },
            "tracks": [],
            "albums": [album.to_dict() for album in albums] if albums else []
        }
        
        # Ajouter les tracks
        for track in tracks:
            track_data = track.to_dict()
            
            # Filtrer selon les options
            if not options.get('include_lyrics', True):
                track_data.pop('lyrics', None)
                track_data.pop('lyrics_snippet', None)
            
            if not options.get('include_credits', True):
                track_data.pop('credits', None)
            
            export_data["tracks"].append(track_data)
        
        # Écrire le fichier
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        return str(output_path)
    
    def _export_csv(self, artist: Artist, tracks: List[Track], 
                   output_path: Path, options: Dict[str, Any]) -> str:
        """Export au format CSV"""
        import csv
        
        # Préparer les en-têtes
        headers = [
            'title', 'artist_name', 'album_name', 'duration', 'bpm', 
            'release_date', 'genius_id', 'spotify_id', 'has_lyrics'
        ]
        
        if options.get('include_credits', True):
            headers.append('producers')
            headers.append('total_credits')
        
        # Écrire le fichier CSV
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for track in tracks:
                row = {
                    'title': track.title,
                    'artist_name': track.artist_name,
                    'album_name': track.album_name or '',
                    'duration': track.duration or '',
                    'bpm': track.bpm or '',
                    'release_date': track.release_date or '',
                    'genius_id': track.genius_id or '',
                    'spotify_id': track.spotify_id or '',
                    'has_lyrics': track.has_lyrics
                }
                
                if options.get('include_credits', True):
                    producers = track.get_producers() if hasattr(track, 'get_producers') else []
                    row['producers'] = '; '.join(producers)
                    row['total_credits'] = len(track.credits) if track.credits else 0
                
                writer.writerow(row)
        
        return str(output_path)
    
    def _export_html(self, artist: Artist, tracks: List[Track], albums: List,
                    output_path: Path, options: Dict[str, Any]) -> str:
        """Export au format HTML"""
        html_content = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Extraction - {artist.name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #667eea; color: white; padding: 20px; border-radius: 10px; }}
        .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; flex: 1; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; font-weight: bold; }}
        .track-title {{ font-weight: bold; color: #333; }}
        .album-name {{ color: #666; font-style: italic; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎵 {artist.name}</h1>
        <p>Rapport d'extraction généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <h3>📊 Statistiques</h3>
            <p><strong>Morceaux:</strong> {len(tracks)}</p>
            <p><strong>Albums:</strong> {len(albums)}</p>
        </div>
        <div class="stat-card">
            <h3>🎯 Qualité</h3>
            <p><strong>Avec paroles:</strong> {sum(1 for t in tracks if t.has_lyrics)}</p>
            <p><strong>Avec BPM:</strong> {sum(1 for t in tracks if t.bpm)}</p>
        </div>
    </div>
    
    <h2>🎵 Morceaux</h2>
    <table>
        <thead>
            <tr>
                <th>Titre</th>
                <th>Album</th>
                <th>Durée</th>
                <th>BPM</th>
                <th>Date</th>
                <th>Paroles</th>
            </tr>
        </thead>
        <tbody>
"""
        
        # Ajouter les tracks
        for track in tracks:
            duration_str = f"{track.duration//60}:{track.duration%60:02d}" if track.duration else "N/A"
            html_content += f"""
            <tr>
                <td class="track-title">{track.title}</td>
                <td class="album-name">{track.album_name or 'N/A'}</td>
                <td>{duration_str}</td>
                <td>{track.bpm or 'N/A'}</td>
                <td>{track.release_date or 'N/A'}</td>
                <td>{'✅' if track.has_lyrics else '❌'}</td>
            </tr>
"""
        
        html_content += """
        </tbody>
    </table>
    
    <footer style="margin-top: 40px; color: #666; font-size: 0.9em;">
        <p>Généré par Music Data Extractor</p>
    </footer>
</body>
</html>
"""
        
        # Écrire le fichier
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return str(output_path)
    
    def _export_excel(self, artist: Artist, tracks: List[Track], albums: List,
                     output_path: Path, options: Dict[str, Any]) -> str:
        """Export au format Excel (nécessite pandas)"""
        try:
            import pandas as pd
            
            # Préparer les données pour pandas
            tracks_data = []
            for track in tracks:
                track_dict = {
                    'Titre': track.title,
                    'Artiste': track.artist_name,
                    'Album': track.album_name or '',
                    'Durée (sec)': track.duration or '',
                    'BPM': track.bpm or '',
                    'Date de sortie': track.release_date or '',
                    'A des paroles': track.has_lyrics,
                    'Genius ID': track.genius_id or '',
                    'Spotify ID': track.spotify_id or ''
                }
                tracks_data.append(track_dict)
            
            # Créer le DataFrame
            df = pd.DataFrame(tracks_data)
            
            # Sauvegarder en Excel
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Morceaux', index=False)
                
                # Ajouter une feuille avec les statistiques
                stats_data = {
                    'Métrique': ['Total morceaux', 'Avec paroles', 'Avec BPM', 'Avec durée'],
                    'Valeur': [
                        len(tracks),
                        sum(1 for t in tracks if t.has_lyrics),
                        sum(1 for t in tracks if t.bpm),
                        sum(1 for t in tracks if t.duration)
                    ]
                }
                stats_df = pd.DataFrame(stats_data)
                stats_df.to_excel(writer, sheet_name='Statistiques', index=False)
            
            return str(output_path)
            
        except ImportError:
            self.logger.warning("pandas non disponible, export Excel ignoré")
            return None