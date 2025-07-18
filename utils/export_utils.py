# utils/export_utils.py - VERSION CORRIGÉE
"""
Gestionnaire d'exports multi-formats pour les données musicales.
Supporte JSON, CSV, Excel, HTML et XML avec optimisations de performance.
"""

import json
import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import logging
from functools import lru_cache

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logging.getLogger(__name__).info("Pandas non disponible - exports Excel limités")

from config.settings import settings
from models.entities import Artist, Track, Album, Credit
from models.enums import ExportFormat
from core.exceptions import ExportError, ExportPermissionError, ExportFormatError

class ExportManager:
    """
    Gestionnaire d'exports multi-formats pour les données musicales.
    
    Formats supportés :
    - JSON (structure complète)
    - CSV (données tabulaires)
    - Excel (plusieurs onglets si pandas disponible)
    - HTML (rapport web avec styles)
    - XML (structure hiérarchique)
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.export_dir = settings.exports_dir
        self.export_dir.mkdir(exist_ok=True)
        
        # Templates HTML
        self.html_template = self._load_html_template()
        
        # Statistiques d'export
        self.stats = {
            'exports_created': 0,
            'total_size_bytes': 0,
            'formats_used': {},
            'last_export': None
        }
        
        self.logger.info("ExportManager initialisé")
    
    def export_artist_data(self, 
                          artist: Artist, 
                          tracks: List[Track],
                          albums: List[Album] = None,
                          format: Union[str, ExportFormat] = ExportFormat.JSON,
                          filename: Optional[str] = None,
                          options: Dict[str, Any] = None) -> str:
        """
        Exporte les données d'un artiste dans le format spécifié.
        
        Args:
            artist: Artiste à exporter
            tracks: Liste des tracks
            albums: Liste des albums (optionnel)
            format: Format d'export
            filename: Nom de fichier personnalisé
            options: Options d'export spécifiques
            
        Returns:
            Chemin du fichier exporté
        """
        try:
            # Normalisation du format
            if isinstance(format, str):
                try:
                    format = ExportFormat(format.lower())
                except ValueError:
                    raise ExportFormatError(f"Format non supporté: {format}")
            
            # Préparation des données
            export_data = self._prepare_artist_data(artist, tracks, albums or [])
            
            # Génération du nom de fichier
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_artist_name = self._sanitize_filename(artist.name)
                filename = f"{safe_artist_name}_{timestamp}"
            
            # Export selon le format
            if format == ExportFormat.JSON:
                filepath = self._export_json(export_data, filename, options)
            elif format == ExportFormat.CSV:
                filepath = self._export_csv(export_data, filename, options)
            elif format == ExportFormat.EXCEL:
                filepath = self._export_excel(export_data, filename, options)
            elif format == ExportFormat.HTML:
                filepath = self._export_html(export_data, filename, options)
            elif format == ExportFormat.XML:
                filepath = self._export_xml(export_data, filename, options)
            else:
                raise ExportFormatError(f"Format non implémenté: {format}")
            
            # Mise à jour des statistiques
            self._update_stats(Path(filepath), format)
            
            self.logger.info(f"✅ Export réussi: {filepath}")
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"❌ Erreur export artiste {artist.name}: {e}")
            raise ExportError(f"Échec export: {str(e)}") from e
    
    def export_tracks_list(self, 
                          tracks: List[Track], 
                          format: Union[str, ExportFormat] = ExportFormat.CSV,
                          filename: Optional[str] = None,
                          options: Dict[str, Any] = None) -> str:
        """
        Exporte une liste de tracks.
        
        Args:
            tracks: Liste des tracks à exporter
            format: Format d'export
            filename: Nom de fichier
            options: Options d'export
            
        Returns:
            Chemin du fichier exporté
        """
        try:
            # Normalisation du format
            if isinstance(format, str):
                format = ExportFormat(format.lower())
            
            # Préparation des données
            export_data = self._prepare_tracks_data(tracks)
            
            # Génération du nom de fichier
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"tracks_export_{timestamp}"
            
            # Export selon le format
            if format == ExportFormat.JSON:
                filepath = self._export_json(export_data, filename, options)
            elif format == ExportFormat.CSV:
                filepath = self._export_csv(export_data, filename, options)
            elif format == ExportFormat.EXCEL:
                filepath = self._export_excel(export_data, filename, options)
            elif format == ExportFormat.HTML:
                filepath = self._export_html(export_data, filename, options)
            elif format == ExportFormat.XML:
                filepath = self._export_xml(export_data, filename, options)
            else:
                raise ExportFormatError(f"Format non supporté: {format}")
            
            self._update_stats(Path(filepath), format)
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"❌ Erreur export tracks: {e}")
            raise ExportError(f"Échec export tracks: {str(e)}") from e
    
    # ===== MÉTHODES DE PRÉPARATION DES DONNÉES =====
    
    def _prepare_artist_data(self, artist: Artist, tracks: List[Track], albums: List[Album]) -> Dict[str, Any]:
        """Prépare les données d'artiste pour export"""
        
        # Données de base de l'artiste
        artist_data = {
            'id': getattr(artist, 'id', None),
            'name': artist.name,
            'genius_id': getattr(artist, 'genius_id', None),
            'spotify_id': getattr(artist, 'spotify_id', None),
            'active_years': getattr(artist, 'active_years', None),
            'description': getattr(artist, 'description', None),
            'image_url': getattr(artist, 'image_url', None)
        }
        
        # Données des tracks
        tracks_data = []
        for track in tracks:
            track_dict = {
                'id': getattr(track, 'id', None),
                'title': track.title,
                'artist_name': track.artist_name,
                'album_title': getattr(track, 'album_title', None),
                'album_id': getattr(track, 'album_id', None),
                'track_number': getattr(track, 'track_number', None),
                'duration_seconds': getattr(track, 'duration_seconds', None),
                'bpm': getattr(track, 'bpm', None),
                'key': getattr(track, 'key', None),
                'explicit': getattr(track, 'explicit', None),
                'release_date': getattr(track, 'release_date', None),
                'genius_id': getattr(track, 'genius_id', None),
                'spotify_id': getattr(track, 'spotify_id', None),
                'youtube_url': getattr(track, 'youtube_url', None),
                'lyrics': getattr(track, 'lyrics', None),
                'source': getattr(track, 'source', None)
            }
            
            # Ajout des crédits si disponibles
            if hasattr(track, 'credits') and track.credits:
                track_dict['credits'] = [
                    {
                        'person_name': credit.person_name,
                        'role': credit.role,
                        'category': getattr(credit, 'category', None)
                    }
                    for credit in track.credits
                ]
            
            tracks_data.append(track_dict)
        
        # Données des albums
        albums_data = []
        for album in albums:
            album_dict = {
                'id': getattr(album, 'id', None),
                'title': album.title,
                'artist_name': getattr(album, 'artist_name', None),
                'release_date': getattr(album, 'release_date', None),
                'album_type': getattr(album, 'album_type', None),
                'track_count': getattr(album, 'track_count', None),
                'genius_id': getattr(album, 'genius_id', None),
                'spotify_id': getattr(album, 'spotify_id', None),
                'cover_url': getattr(album, 'cover_url', None)
            }
            albums_data.append(album_dict)
        
        # Statistiques générales
        stats = self._calculate_artist_stats(tracks, albums)
        
        return {
            'artist': artist_data,
            'tracks': tracks_data,
            'albums': albums_data,
            'statistics': stats,
            'export_metadata': {
                'exported_at': datetime.now().isoformat(),
                'total_tracks': len(tracks),
                'total_albums': len(albums),
                'exporter_version': '1.0'
            }
        }
    
    def _prepare_tracks_data(self, tracks: List[Track]) -> Dict[str, Any]:
        """Prépare les données de tracks pour export"""
        
        tracks_data = []
        for track in tracks:
            track_dict = {
                'id': getattr(track, 'id', None),
                'title': track.title,
                'artist_name': track.artist_name,
                'album_title': getattr(track, 'album_title', None),
                'duration_seconds': getattr(track, 'duration_seconds', None),
                'bpm': getattr(track, 'bpm', None),
                'release_date': getattr(track, 'release_date', None),
                'source': getattr(track, 'source', None)
            }
            tracks_data.append(track_dict)
        
        return {
            'tracks': tracks_data,
            'export_metadata': {
                'exported_at': datetime.now().isoformat(),
                'total_tracks': len(tracks),
                'exporter_version': '1.0'
            }
        }
    
    def _calculate_artist_stats(self, tracks: List[Track], albums: List[Album]) -> Dict[str, Any]:
        """Calcule les statistiques d'un artiste"""
        
        stats = {
            'total_tracks': len(tracks),
            'total_albums': len(albums),
            'total_duration_seconds': 0,
            'average_track_duration': 0,
            'tracks_with_lyrics': 0,
            'tracks_with_bpm': 0,
            'most_recent_release': None,
            'oldest_release': None,
            'average_bpm': 0
        }
        
        if not tracks:
            return stats
        
        # Calculs sur les durées
        durations = [t.duration_seconds for t in tracks if getattr(t, 'duration_seconds', None)]
        if durations:
            stats['total_duration_seconds'] = sum(durations)
            stats['average_track_duration'] = sum(durations) / len(durations)
        
        # Calculs sur les BPM
        bpms = [t.bpm for t in tracks if getattr(t, 'bpm', None)]
        if bpms:
            stats['tracks_with_bpm'] = len(bpms)
            stats['average_bpm'] = sum(bpms) / len(bpms)
        
        # Comptage des lyrics
        stats['tracks_with_lyrics'] = len([t for t in tracks if getattr(t, 'lyrics', None)])
        
        # Dates de sortie
        release_dates = [t.release_date for t in tracks if getattr(t, 'release_date', None)]
        if release_dates:
            release_dates.sort()
            stats['oldest_release'] = release_dates[0].isoformat() if hasattr(release_dates[0], 'isoformat') else str(release_dates[0])
            stats['most_recent_release'] = release_dates[-1].isoformat() if hasattr(release_dates[-1], 'isoformat') else str(release_dates[-1])
        
        return stats
    
    # ===== MÉTHODES D'EXPORT PAR FORMAT =====
    
    def _export_json(self, data: Dict[str, Any], filename: str, options: Optional[Dict[str, Any]] = None) -> Path:
        """Export au format JSON"""
        options = options or {}
        
        filepath = self.export_dir / f"{filename}.json"
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(
                    data, 
                    f, 
                    indent=options.get('indent', 2),
                    ensure_ascii=options.get('ensure_ascii', False),
                    default=str  # Pour les objets non sérialisables
                )
            
            return filepath
            
        except Exception as e:
            raise ExportError(f"Erreur export JSON: {e}") from e
    
    def _export_csv(self, data: Dict[str, Any], filename: str, options: Optional[Dict[str, Any]] = None) -> Path:
        """Export au format CSV"""
        options = options or {}
        
        # Export des tracks (principal)
        filepath = self.export_dir / f"{filename}_tracks.csv"
        
        try:
            tracks_data = data.get('tracks', [])
            if not tracks_data:
                raise ExportError("Aucune donnée de tracks à exporter")
            
            # Aplatissement des données pour CSV
            flattened_tracks = []
            for track in tracks_data:
                flat_track = track.copy()
                
                # Gestion des crédits
                if 'credits' in flat_track:
                    credits_str = '; '.join([
                        f"{credit['person_name']} ({credit['role']})"
                        for credit in flat_track['credits']
                    ])
                    flat_track['credits'] = credits_str
                
                flattened_tracks.append(flat_track)
            
            # Écriture du CSV
            if flattened_tracks:
                fieldnames = flattened_tracks[0].keys()
                
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(
                        f, 
                        fieldnames=fieldnames,
                        delimiter=options.get('delimiter', ','),
                        quotechar=options.get('quotechar', '"')
                    )
                    writer.writeheader()
                    writer.writerows(flattened_tracks)
            
            # Export des albums si présents
            if data.get('albums'):
                albums_filepath = self.export_dir / f"{filename}_albums.csv"
                with open(albums_filepath, 'w', newline='', encoding='utf-8') as f:
                    albums_data = data['albums']
                    if albums_data:
                        fieldnames = albums_data[0].keys()
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(albums_data)
            
            return filepath
            
        except Exception as e:
            raise ExportError(f"Erreur export CSV: {e}") from e
    
    def _export_excel(self, data: Dict[str, Any], filename: str, options: Optional[Dict[str, Any]] = None) -> Path:
        """Export au format Excel"""
        options = options or {}
        
        filepath = self.export_dir / f"{filename}.xlsx"
        
        if not PANDAS_AVAILABLE:
            self.logger.warning("Pandas non disponible - export Excel de base")
            return self._export_csv(data, filename, options)  # Fallback vers CSV
        
        try:
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                
                # Onglet tracks
                if data.get('tracks'):
                    tracks_df = pd.DataFrame(data['tracks'])
                    tracks_df.to_excel(writer, sheet_name='Tracks', index=False)
                
                # Onglet albums
                if data.get('albums'):
                    albums_df = pd.DataFrame(data['albums'])
                    albums_df.to_excel(writer, sheet_name='Albums', index=False)
                
                # Onglet artiste
                if data.get('artist'):
                    artist_df = pd.DataFrame([data['artist']])
                    artist_df.to_excel(writer, sheet_name='Artist', index=False)
                
                # Onglet statistiques
                if data.get('statistics'):
                    stats_df = pd.DataFrame([data['statistics']])
                    stats_df.to_excel(writer, sheet_name='Statistics', index=False)
            
            return filepath
            
        except Exception as e:
            raise ExportError(f"Erreur export Excel: {e}") from e
    
    def _export_html(self, data: Dict[str, Any], filename: str, options: Optional[Dict[str, Any]] = None) -> Path:
        """Export au format HTML"""
        options = options or {}
        
        filepath = self.export_dir / f"{filename}.html"
        
        try:
            # Génération du HTML
            html_content = self._generate_html_content(data, options)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return filepath
            
        except Exception as e:
            raise ExportError(f"Erreur export HTML: {e}") from e
    
    def _export_xml(self, data: Dict[str, Any], filename: str, options: Optional[Dict[str, Any]] = None) -> Path:
        """Export au format XML"""
        options = options or {}
        
        filepath = self.export_dir / f"{filename}.xml"
        
        try:
            # Création de l'arbre XML
            root = ET.Element("music_data")
            
            # Métadonnées d'export
            metadata = ET.SubElement(root, "metadata")
            if data.get('export_metadata'):
                for key, value in data['export_metadata'].items():
                    elem = ET.SubElement(metadata, key)
                    elem.text = str(value)
            
            # Données artiste
            if data.get('artist'):
                artist_elem = ET.SubElement(root, "artist")
                for key, value in data['artist'].items():
                    if value is not None:
                        elem = ET.SubElement(artist_elem, key)
                        elem.text = str(value)
            
            # Tracks
            if data.get('tracks'):
                tracks_elem = ET.SubElement(root, "tracks")
                for track in data['tracks']:
                    track_elem = ET.SubElement(tracks_elem, "track")
                    for key, value in track.items():
                        if value is not None:
                            if key == 'credits' and isinstance(value, list):
                                credits_elem = ET.SubElement(track_elem, "credits")
                                for credit in value:
                                    credit_elem = ET.SubElement(credits_elem, "credit")
                                    for credit_key, credit_value in credit.items():
                                        elem = ET.SubElement(credit_elem, credit_key)
                                        elem.text = str(credit_value)
                            else:
                                elem = ET.SubElement(track_elem, key)
                                elem.text = str(value)
            
            # Albums
            if data.get('albums'):
                albums_elem = ET.SubElement(root, "albums")
                for album in data['albums']:
                    album_elem = ET.SubElement(albums_elem, "album")
                    for key, value in album.items():
                        if value is not None:
                            elem = ET.SubElement(album_elem, key)
                            elem.text = str(value)
            
            # Écriture du fichier XML
            tree = ET.ElementTree(root)
            tree.write(filepath, encoding='utf-8', xml_declaration=True)
            
            return filepath
            
        except Exception as e:
            raise ExportError(f"Erreur export XML: {e}") from e
    
    def _generate_html_content(self, data: Dict[str, Any], options: Dict[str, Any]) -> str:
        """Génère le contenu HTML"""
        
        # Template HTML de base
        html_template = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Export Musical - {data.get('artist', {}).get('name', 'Artiste')}</title>
    <style>
        {self._get_html_styles()}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 Export Musical</h1>
            <p class="export-date">Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
        </header>
        
        {self._generate_artist_section(data.get('artist', {}))}
        {self._generate_statistics_section(data.get('statistics', {}))}
        {self._generate_tracks_section(data.get('tracks', []))}
        {self._generate_albums_section(data.get('albums', []))}
        
        <footer>
            <p>Généré par Music Data Extractor v1.0</p>
        </footer>
    </div>
    
    <script>
        {self._get_html_scripts()}
    </script>
</body>
</html>
        """
        
        return html_template
    
    def _generate_artist_section(self, artist_data: Dict[str, Any]) -> str:
        """Génère la section artiste en HTML"""
        if not artist_data:
            return ""
        
        return f"""
        <section class="artist-section">
            <h2>🎤 Artiste: {artist_data.get('name', 'N/A')}</h2>
            <div class="artist-info">
                <p><strong>ID Genius:</strong> {artist_data.get('genius_id', 'N/A')}</p>
                <p><strong>ID Spotify:</strong> {artist_data.get('spotify_id', 'N/A')}</p>
                <p><strong>Années d'activité:</strong> {artist_data.get('active_years', 'N/A')}</p>
                {f'<p><strong>Description:</strong> {artist_data.get("description", "")}</p>' if artist_data.get('description') else ''}
            </div>
        </section>
        """
    
    def _generate_statistics_section(self, stats: Dict[str, Any]) -> str:
        """Génère la section statistiques en HTML"""
        if not stats:
            return ""
        
        return f"""
        <section class="statistics-section">
            <h2>📈 Statistiques</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>{stats.get('total_tracks', 0)}</h3>
                    <p>Tracks totaux</p>
                </div>
                <div class="stat-card">
                    <h3>{stats.get('total_albums', 0)}</h3>
                    <p>Albums</p>
                </div>
                <div class="stat-card">
                    <h3>{round(stats.get('average_track_duration', 0) / 60, 1) if stats.get('average_track_duration') else 0} min</h3>
                    <p>Durée moyenne</p>
                </div>
                <div class="stat-card">
                    <h3>{round(stats.get('average_bpm', 0)) if stats.get('average_bpm') else 'N/A'}</h3>
                    <p>BPM moyen</p>
                </div>
            </div>
        </section>
        """
    
    def _generate_tracks_section(self, tracks: List[Dict[str, Any]]) -> str:
        """Génère la section tracks en HTML"""
        if not tracks:
            return ""
        
        tracks_html = """
        <section class="tracks-section">
            <h2>🎵 Tracks</h2>
            <div class="tracks-container">
                <table class="tracks-table">
                    <thead>
                        <tr>
                            <th>Titre</th>
                            <th>Album</th>
                            <th>Durée</th>
                            <th>BPM</th>
                            <th>Source</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for track in tracks:
            duration = track.get('duration_seconds')
            duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "N/A"
            
            tracks_html += f"""
                        <tr>
                            <td><strong>{track.get('title', 'N/A')}</strong></td>
                            <td>{track.get('album_title', 'N/A')}</td>
                            <td>{duration_str}</td>
                            <td>{track.get('bpm', 'N/A')}</td>
                            <td>{track.get('source', 'N/A')}</td>
                        </tr>
            """
        
        tracks_html += """
                    </tbody>
                </table>
            </div>
        </section>
        """
        
        return tracks_html
    
    def _generate_albums_section(self, albums: List[Dict[str, Any]]) -> str:
        """Génère la section albums en HTML"""
        if not albums:
            return ""
        
        albums_html = """
        <section class="albums-section">
            <h2>💿 Albums</h2>
            <div class="albums-grid">
        """
        
        for album in albums:
            albums_html += f"""
                <div class="album-card">
                    <h3>{album.get('title', 'N/A')}</h3>
                    <p><strong>Type:</strong> {album.get('album_type', 'N/A')}</p>
                    <p><strong>Tracks:</strong> {album.get('track_count', 'N/A')}</p>
                    <p><strong>Sortie:</strong> {album.get('release_date', 'N/A')}</p>
                </div>
            """
        
        albums_html += """
            </div>
        </section>
        """
        
        return albums_html
    
    @lru_cache(maxsize=1)
    def _get_html_styles(self) -> str:
        """Retourne les styles CSS pour l'export HTML"""
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: white;
            margin-top: 20px;
            margin-bottom: 20px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        header {
            text-align: center;
            padding: 20px 0;
            border-bottom: 2px solid #eee;
            margin-bottom: 30px;
        }
        
        header h1 {
            color: #2c3e50;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .export-date {
            color: #7f8c8d;
            font-style: italic;
        }
        
        section {
            margin: 30px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #3498db;
        }
        
        h2 {
            color: #2c3e50;
            margin-bottom: 20px;
            font-size: 1.8em;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
        }
        
        .stat-card h3 {
            font-size: 2em;
            color: #e74c3c;
            margin-bottom: 10px;
        }
        
        .tracks-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .tracks-table th {
            background: #34495e;
            color: white;
            padding: 15px;
            text-align: left;
        }
        
        .tracks-table td {
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
        }
        
        .tracks-table tr:hover {
            background: #f5f5f5;
        }
        
        .albums-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
        }
        
        .album-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        
        .album-card:hover {
            transform: translateY(-3px);
        }
        
        .album-card h3 {
            color: #2c3e50;
            margin-bottom: 15px;
            font-size: 1.2em;
        }
        
        .artist-info p {
            margin: 10px 0;
            padding: 8px;
            background: white;
            border-radius: 4px;
        }
        
        footer {
            text-align: center;
            padding: 20px;
            color: #7f8c8d;
            border-top: 1px solid #eee;
            margin-top: 40px;
        }
        
        @media (max-width: 768px) {
            .container {
                margin: 10px;
                padding: 15px;
            }
            
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .tracks-table {
                font-size: 0.9em;
            }
        }
        """
    
    @lru_cache(maxsize=1)
    def _get_html_scripts(self) -> str:
        """Retourne les scripts JavaScript pour l'export HTML"""
        return """
        // Animation au scroll
        document.addEventListener('DOMContentLoaded', function() {
            const cards = document.querySelectorAll('.stat-card, .album-card');
            
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.style.opacity = '1';
                        entry.target.style.transform = 'translateY(0)';
                    }
                });
            });
            
            cards.forEach(card => {
                card.style.opacity = '0';
                card.style.transform = 'translateY(20px)';
                card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
                observer.observe(card);
            });
            
            // Interaction hover sur les lignes du tableau
            const tableRows = document.querySelectorAll('.tracks-table tr');
            tableRows.forEach(row => {
                row.addEventListener('mouseenter', function() {
                    this.style.cursor = 'pointer';
                });
            });
        });
        """
    
    def _load_html_template(self) -> str:
        """Charge un template HTML personnalisé si disponible"""
        template_path = settings.data_dir / "templates" / "export_template.html"
        if template_path.exists():
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                self.logger.warning(f"Erreur lors du chargement du template: {e}")
        
        return ""  # Template par défaut sera utilisé
    
    def _update_stats(self, filepath: Path, format: ExportFormat):
        """Met à jour les statistiques d'export"""
        try:
            file_size = filepath.stat().st_size
            self.stats['exports_created'] += 1
            self.stats['total_size_bytes'] += file_size
            self.stats['formats_used'][format.value] = self.stats['formats_used'].get(format.value, 0) + 1
            self.stats['last_export'] = datetime.now().isoformat()
        except Exception as e:
            self.logger.warning(f"Erreur mise à jour stats: {e}")
    
    def _sanitize_filename(self, filename: str) -> str:
        """Nettoie un nom de fichier"""
        # Remplacement des caractères problématiques
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
        sanitized = re.sub(r'\s+', '_', sanitized)
        sanitized = sanitized.strip('._')
        
        # Limitation de longueur
        if len(sanitized) > 50:
            sanitized = sanitized[:50]
        
        return sanitized if sanitized else "export"
    
    # ===== MÉTHODES PUBLIQUES UTILITAIRES =====
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'export"""
        stats = self.stats.copy()
        stats['total_size_mb'] = round(stats['total_size_bytes'] / (1024 * 1024), 2)
        return stats
    
    def list_exports(self) -> List[Dict[str, Any]]:
        """Liste tous les fichiers d'export disponibles"""
        exports = []
        
        for file_path in self.export_dir.glob("*"):
            if file_path.is_file():
                try:
                    stat = file_path.stat()
                    exports.append({
                        'filename': file_path.name,
                        'path': str(file_path),
                        'format': file_path.suffix[1:].upper(),
                        'size_bytes': stat.st_size,
                        'size_mb': round(stat.st_size / (1024 * 1024), 2),
                        'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except Exception as e:
                    self.logger.warning(f"Erreur lecture fichier {file_path}: {e}")
        
        return sorted(exports, key=lambda x: x['modified_at'], reverse=True)
    
    def cleanup_old_exports(self, days_old: int = 30) -> int:
        """
        Supprime les exports anciens.
        
        Args:
            days_old: Âge limite en jours
            
        Returns:
            Nombre de fichiers supprimés
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)
        deleted_count = 0
        
        for file_path in self.export_dir.glob("*"):
            if file_path.is_file():
                try:
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_date:
                        file_path.unlink()
                        deleted_count += 1
                        self.logger.debug(f"Fichier supprimé: {file_path.name}")
                except Exception as e:
                    self.logger.warning(f"Erreur suppression {file_path}: {e}")
        
        self.logger.info(f"🧹 {deleted_count} anciens exports supprimés")
        return deleted_count
    
    def export_data(self, data: Any, format_type: str = "json", filename: Optional[str] = None) -> Optional[str]:
        """
        Méthode générique d'export pour n'importe quel type de données.
        
        Args:
            data: Données à exporter
            format_type: Type de format ('json', 'csv', etc.)
            filename: Nom de fichier optionnel
            
        Returns:
            Chemin du fichier exporté ou None en cas d'erreur
        """
        try:
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"generic_export_{timestamp}"
            
            # Conversion des données en format exportable
            if hasattr(data, '__dict__'):
                export_data = data.__dict__
            elif isinstance(data, (list, dict)):
                export_data = data
            else:
                export_data = {'data': str(data)}
            
            # Ajout de métadonnées
            final_data = {
                'content': export_data,
                'export_metadata': {
                    'exported_at': datetime.now().isoformat(),
                    'data_type': type(data).__name__,
                    'exporter_version': '1.0'
                }
            }
            
            # Export selon le format
            format_enum = ExportFormat(format_type.lower())
            
            if format_enum == ExportFormat.JSON:
                filepath = self._export_json(final_data, filename)
            elif format_enum == ExportFormat.CSV:
                # Pour CSV, essayer de convertir en format tabulaire
                if isinstance(export_data, list) and export_data and isinstance(export_data[0], dict):
                    filepath = self._export_csv({'tracks': export_data}, filename)
                else:
                    # Fallback vers JSON si les données ne sont pas tabulaires
                    filepath = self._export_json(final_data, filename)
            else:
                filepath = self._export_json(final_data, filename)
            
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"❌ Erreur export générique: {e}")
            return None
    
    def health_check(self) -> Dict[str, Any]:
        """Effectue un diagnostic de santé de l'ExportManager"""
        return {
            'export_dir_exists': self.export_dir.exists(),
            'export_dir_writable': os.access(self.export_dir, os.W_OK) if self.export_dir.exists() else False,
            'pandas_available': PANDAS_AVAILABLE,
            'total_exports': self.stats['exports_created'],
            'supported_formats': [fmt.value for fmt in ExportFormat],
            'disk_space_mb': self._get_available_disk_space(),
            'status': 'healthy'
        }
    
    def _get_available_disk_space(self) -> float:
        """Retourne l'espace disque disponible en MB"""
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.export_dir)
            return round(free / (1024 * 1024), 2)
        except Exception:
            return -1  # Impossible de déterminer


# ===== FONCTIONS UTILITAIRES GLOBALES =====

def export_all_formats(artist: Artist, tracks: List[Track], albums: List[Album] = None, 
                      base_filename: Optional[str] = None) -> Dict[str, str]:
    """
    Exporte les données dans tous les formats supportés.
    
    Args:
        artist: Artiste à exporter
        tracks: Liste des tracks
        albums: Liste des albums
        base_filename: Nom de base pour les fichiers
        
    Returns:
        Dictionnaire {format: chemin_fichier} des exports créés
    """
    manager = ExportManager()
    results = {}
    
    formats_to_export = [ExportFormat.JSON, ExportFormat.CSV, ExportFormat.HTML]
    
    # Ajouter Excel si pandas est disponible
    if PANDAS_AVAILABLE:
        formats_to_export.append(ExportFormat.EXCEL)
    
    for format_type in formats_to_export:
        try:
            filename = f"{base_filename}_{format_type.value}" if base_filename else None
            filepath = manager.export_artist_data(
                artist=artist,
                tracks=tracks,
                albums=albums or [],
                format=format_type,
                filename=filename
            )
            results[format_type.value] = filepath
            
        except Exception as e:
            manager.logger.error(f"❌ Erreur export {format_type.value}: {e}")
            results[format_type.value] = None
    
    return results

def cleanup_old_exports(days_to_keep: int = 30) -> int:
    """
    Fonction de convenance pour nettoyer les anciens exports.
    
    Args:
        days_to_keep: Nombre de jours à conserver
        
    Returns:
        Nombre de fichiers supprimés
    """
    manager = ExportManager()
    return manager.cleanup_old_exports(days_to_keep)

def get_export_stats() -> Dict[str, Any]:
    """
    Fonction de convenance pour obtenir les statistiques d'export.
    
    Returns:
        Statistiques d'export
    """
    manager = ExportManager()
    return manager.get_stats()

def validate_export_permissions() -> Tuple[bool, List[str]]:
    """
    Valide que les permissions d'écriture sont correctes pour les exports.
    
    Returns:
        Tuple (permissions_ok, liste_problèmes)
    """
    issues = []
    manager = ExportManager()
    
    # Vérifier que le répertoire d'export existe
    if not manager.export_dir.exists():
        try:
            manager.export_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            issues.append(f"Impossible de créer le répertoire d'export: {e}")
    
    # Vérifier les permissions d'écriture
    if manager.export_dir.exists():
        import os
        if not os.access(manager.export_dir, os.W_OK):
            issues.append("Pas de permission d'écriture dans le répertoire d'export")
    
    # Vérifier l'espace disque (minimum 100MB)
    try:
        import shutil
        total, used, free = shutil.disk_usage(manager.export_dir)
        free_mb = free / (1024 * 1024)
        if free_mb < 100:
            issues.append(f"Espace disque insuffisant: {free_mb:.1f}MB disponibles")
    except Exception:
        issues.append("Impossible de vérifier l'espace disque")
    
    return len(issues) == 0, issues

# ===== LOGGING =====

import os  # Import manquant ajouté

logger = logging.getLogger(__name__)
logger.info("Module export_utils initialisé avec succès")

# ===== EXEMPLES D'UTILISATION =====
"""
Exemples d'utilisation:

# Export simple
manager = ExportManager()
filepath = manager.export_artist_data(artist, tracks, format=ExportFormat.JSON)

# Export dans tous les formats
results = export_all_formats(artist, tracks, albums, "nekfeu_2024")

# Nettoyage des anciens fichiers
deleted = cleanup_old_exports(days_to_keep=14)

# Statistiques
stats = get_export_stats()
print(f"Total exports: {stats['exports_created']}")

# Validation des permissions
permissions_ok, issues = validate_export_permissions()
if not permissions_ok:
    print(f"Problèmes: {issues}")
"""