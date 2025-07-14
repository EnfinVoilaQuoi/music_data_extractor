# utils/export_utils.py
import json
import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import logging

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from ..config.settings import settings  # CORRECTION: Import relatif correct
from ..models.entities import Artist, Track, Album, Credit  # CORRECTION: Import relatif correct
from ..models.enums import ExportFormat  # CORRECTION: Import relatif correct
from ..core.exceptions import ExportError, ExportPermissionError, ExportFormatError  # CORRECTION: Import relatif correct

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
            artist: Données de l'artiste
            tracks: Liste des morceaux
            albums: Liste des albums (optionnel)
            format: Format d'export
            filename: Nom de fichier personnalisé (optionnel)
            options: Options d'export spécifiques au format
            
        Returns:
            Chemin du fichier créé
        """
        try:
            # Validation du format
            if isinstance(format, str):
                try:
                    format = ExportFormat(format.lower())
                except ValueError:
                    raise ExportFormatError(format, [f.value for f in ExportFormat])
            
            # Préparation des données
            export_data = self._prepare_export_data(artist, tracks, albums, options or {})
            
            # Génération du nom de fichier
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_artist_name = "".join(c for c in artist.name if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_artist_name = safe_artist_name.replace(' ', '_')
                filename = f"{safe_artist_name}_{timestamp}"
            
            # Export selon le format
            if format == ExportFormat.JSON:
                filepath = self._export_json(export_data, filename, options or {})
            elif format == ExportFormat.CSV:
                filepath = self._export_csv(export_data, filename, options or {})
            elif format == ExportFormat.EXCEL:
                filepath = self._export_excel(export_data, filename, options or {})
            elif format == ExportFormat.HTML:
                filepath = self._export_html(export_data, filename, options or {})
            elif format == ExportFormat.XML:
                filepath = self._export_xml(export_data, filename, options or {})
            else:
                raise ExportFormatError(format.value, [f.value for f in ExportFormat])
            
            # Mise à jour des statistiques
            self._update_stats(filepath, format)
            
            self.logger.info(f"Export réussi: {filepath}")
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'export: {e}")
            raise ExportError(f"Échec de l'export en format {format}: {str(e)}")
    
    def _prepare_export_data(self, 
                           artist: Artist, 
                           tracks: List[Track], 
                           albums: List[Album] = None,
                           options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Prépare les données pour l'export"""
        options = options or {}
        
        # Données de base
        export_data = {
            'metadata': {
                'exported_at': datetime.now().isoformat(),
                'artist_name': artist.name,
                'total_tracks': len(tracks),
                'total_albums': len(albums) if albums else 0,
                'extractor_version': '1.0.0',
                'options': options
            },
            'artist': artist.to_dict(),
            'tracks': [track.to_dict() for track in tracks]
        }
        
        # Albums si fournis
        if albums:
            export_data['albums'] = [album.to_dict() for album in albums]
        
        # Statistiques calculées
        export_data['statistics'] = self._calculate_statistics(artist, tracks, albums)
        
        # Filtrage des données selon les options
        if not options.get('include_lyrics', True):
            for track in export_data['tracks']:
                track.pop('lyrics', None)
        
        if not options.get('include_raw_data', False):
            for track in export_data['tracks']:
                track.pop('raw_data', None)
        
        return export_data
    
    def _calculate_statistics(self, 
                            artist: Artist, 
                            tracks: List[Track], 
                            albums: List[Album] = None) -> Dict[str, Any]:
        """Calcule des statistiques sur les données"""
        stats = {
            'tracks': {
                'total': len(tracks),
                'with_bpm': sum(1 for t in tracks if t.bpm),
                'with_lyrics': sum(1 for t in tracks if t.has_lyrics),
                'with_credits': sum(1 for t in tracks if t.credits),
                'avg_duration': sum(t.duration_seconds for t in tracks if t.duration_seconds) / len(tracks) if tracks else 0
            },
            'credits': {
                'total': sum(len(t.credits) for t in tracks),
                'unique_collaborators': len(set(
                    credit.person_name for track in tracks 
                    for credit in track.credits 
                    if credit.person_name != artist.name
                )),
                'by_category': {}
            },
            'temporal': {
                'year_range': self._get_year_range(tracks),
                'tracks_by_year': self._get_tracks_by_year(tracks)
            }
        }
        
        # Statistiques par catégorie de crédit
        from ..models.enums import CreditCategory  # CORRECTION: Import relatif correct
        for category in CreditCategory:
            count = sum(
                1 for track in tracks 
                for credit in track.credits 
                if credit.credit_category == category
            )
            stats['credits']['by_category'][category.value] = count
        
        # Top collaborateurs
        collaborator_counts = {}
        for track in tracks:
            for credit in track.credits:
                if credit.person_name and credit.person_name != artist.name:
                    collaborator_counts[credit.person_name] = collaborator_counts.get(credit.person_name, 0) + 1
        
        stats['top_collaborators'] = sorted(
            collaborator_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]
        
        return stats
    
    def _get_year_range(self, tracks: List[Track]) -> Dict[str, Optional[int]]:
        """Calcule la plage d'années des morceaux"""
        years = [t.release_year for t in tracks if t.release_year]
        if years:
            return {'first': min(years), 'last': max(years)}
        return {'first': None, 'last': None}
    
    def _get_tracks_by_year(self, tracks: List[Track]) -> Dict[int, int]:
        """Compte les morceaux par année"""
        year_counts = {}
        for track in tracks:
            if track.release_year:
                year_counts[track.release_year] = year_counts.get(track.release_year, 0) + 1
        return year_counts
    
    def _export_json(self, data: Dict[str, Any], filename: str, options: Dict[str, Any]) -> Path:
        """Exporte en format JSON"""
        filepath = self.export_dir / f"{filename}.json"
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return filepath
            
        except PermissionError:
            raise ExportPermissionError(str(filepath), "écriture")
    
    def _export_csv(self, data: Dict[str, Any], filename: str, options: Dict[str, Any]) -> Path:
        """Exporte en format CSV (tracks principalement)"""
        filepath = self.export_dir / f"{filename}.csv"
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                if not data['tracks']:
                    return filepath
                
                # Utiliser les clés du premier track comme headers
                fieldnames = list(data['tracks'][0].keys())
                
                # Exclure les champs complexes pour CSV
                complex_fields = ['credits', 'raw_data', 'extraction_metadata']
                fieldnames = [f for f in fieldnames if f not in complex_fields]
                
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for track in data['tracks']:
                    # Nettoyer les données pour CSV
                    clean_track = {k: v for k, v in track.items() if k in fieldnames}
                    
                    # Convertir les listes en strings
                    for key, value in clean_track.items():
                        if isinstance(value, list):
                            clean_track[key] = ', '.join(str(v) for v in value)
                    
                    writer.writerow(clean_track)
            
            return filepath
            
        except PermissionError:
            raise ExportPermissionError(str(filepath), "écriture")
    
    def _export_excel(self, data: Dict[str, Any], filename: str, options: Dict[str, Any]) -> Path:
        """Exporte en format Excel avec plusieurs onglets"""
        if not PANDAS_AVAILABLE:
            raise ExportError("Pandas n'est pas installé, impossible d'exporter en Excel")
        
        filepath = self.export_dir / f"{filename}.xlsx"
        
        try:
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # Onglet tracks
                if data['tracks']:
                    tracks_df = pd.json_normalize(data['tracks'])
                    # Supprimer les colonnes trop complexes
                    cols_to_drop = [col for col in tracks_df.columns if 'raw_data' in col or 'extraction_metadata' in col]
                    tracks_df = tracks_df.drop(columns=cols_to_drop, errors='ignore')
                    tracks_df.to_excel(writer, sheet_name='Tracks', index=False)
                
                # Onglet albums si disponible
                if data.get('albums'):
                    albums_df = pd.json_normalize(data['albums'])
                    albums_df.to_excel(writer, sheet_name='Albums', index=False)
                
                # Onglet crédits (aplatir la structure)
                credits_data = []
                for track in data['tracks']:
                    for credit in track.get('credits', []):
                        credits_data.append({
                            'track_title': track.get('title'),
                            'track_id': track.get('id'),
                            'credit_type': credit.get('credit_type'),
                            'credit_category': credit.get('credit_category'),
                            'person_name': credit.get('person_name'),
                            'instrument': credit.get('instrument'),
                            'data_source': credit.get('data_source')
                        })
                
                if credits_data:
                    credits_df = pd.DataFrame(credits_data)
                    credits_df.to_excel(writer, sheet_name='Credits', index=False)
                
                # Onglet statistiques
                stats_data = []
                for key, value in data['statistics'].items():
                    if isinstance(value, dict):
                        for subkey, subvalue in value.items():
                            stats_data.append({
                                'Category': key,
                                'Metric': subkey,
                                'Value': str(subvalue)
                            })
                    else:
                        stats_data.append({
                            'Category': 'General',
                            'Metric': key,
                            'Value': str(value)
                        })
                
                if stats_data:
                    stats_df = pd.DataFrame(stats_data)
                    stats_df.to_excel(writer, sheet_name='Statistics', index=False)
            
            return filepath
            
        except PermissionError:
            raise ExportPermissionError(str(filepath), "écriture")
    
    def _export_html(self, data: Dict[str, Any], filename: str, options: Dict[str, Any]) -> Path:
        """Exporte en format HTML avec mise en forme"""
        filepath = self.export_dir / f"{filename}.html"
        
        try:
            html_content = self._generate_html_report(data, options)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return filepath
            
        except PermissionError:
            raise ExportPermissionError(str(filepath), "écriture")
    
    def _export_xml(self, data: Dict[str, Any], filename: str, options: Dict[str, Any]) -> Path:
        """Exporte en format XML"""
        filepath = self.export_dir / f"{filename}.xml"
        
        try:
            root = ET.Element("music_data")
            
            # Métadonnées
            metadata_elem = ET.SubElement(root, "metadata")
            for key, value in data['metadata'].items():
                elem = ET.SubElement(metadata_elem, key)
                elem.text = str(value)
            
            # Artiste
            artist_elem = ET.SubElement(root, "artist")
            for key, value in data['artist'].items():
                if value is not None:
                    elem = ET.SubElement(artist_elem, key)
                    elem.text = str(value)
            
            # Tracks
            tracks_elem = ET.SubElement(root, "tracks")
            for track_data in data['tracks']:
                track_elem = ET.SubElement(tracks_elem, "track")
                track_elem.set("id", str(track_data.get('id', '')))
                
                for key, value in track_data.items():
                    if key == 'credits' and isinstance(value, list):
                        credits_elem = ET.SubElement(track_elem, "credits")
                        for credit in value:
                            credit_elem = ET.SubElement(credits_elem, "credit")
                            for c_key, c_value in credit.items():
                                if c_value is not None:
                                    c_elem = ET.SubElement(credit_elem, c_key)
                                    c_elem.text = str(c_value)
                    elif value is not None and not isinstance(value, (dict, list)):
                        elem = ET.SubElement(track_elem, key)
                        elem.text = str(value)
            
            # Statistiques
            stats_elem = ET.SubElement(root, "statistics")
            for key, value in data['statistics'].items():
                if isinstance(value, dict):
                    section_elem = ET.SubElement(stats_elem, key)
                    for s_key, s_value in value.items():
                        s_elem = ET.SubElement(section_elem, s_key)
                        s_elem.text = str(s_value)
                else:
                    elem = ET.SubElement(stats_elem, key)
                    elem.text = str(value)
            
            # Écriture du fichier
            tree = ET.ElementTree(root)
            ET.indent(tree, space="  ", level=0)  # Pretty print
            tree.write(filepath, encoding='utf-8', xml_declaration=True)
            
            return filepath
            
        except PermissionError:
            raise ExportPermissionError(str(filepath), "écriture")
    
    def _generate_html_report(self, data: Dict[str, Any], options: Dict[str, Any]) -> str:
        """Génère un rapport HTML complet avec styles"""
        artist_name = data['artist']['name']
        tracks = data['tracks']
        stats = data['statistics']
        
        html = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rapport Musical - {artist_name}</title>
    <style>
        {self._get_html_styles()}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>🎵 Rapport Musical</h1>
            <h2>{artist_name}</h2>
            <div class="meta">
                Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} | 
                {len(tracks)} morceaux analysés
            </div>
        </header>
        
        <section class="summary">
            <h3>📊 Résumé</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{stats['tracks']['total']}</div>
                    <div class="stat-label">Morceaux</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{stats['credits']['total']}</div>
                    <div class="stat-label">Crédits</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{stats['credits']['unique_collaborators']}</div>
                    <div class="stat-label">Collaborateurs</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{stats['tracks']['with_bpm']}</div>
                    <div class="stat-label">Avec BPM</div>
                </div>
            </div>
        </section>
        
        <section class="collaborators">
            <h3>🤝 Top Collaborateurs</h3>
            <div class="collaborators-list">
                {self._generate_collaborators_html(stats.get('top_collaborators', []))}
            </div>
        </section>
        
        <section class="tracks">
            <h3>🎤 Morceaux</h3>
            <div class="tracks-table">
                {self._generate_tracks_table_html(tracks)}
            </div>
        </section>
        
        <section class="timeline">
            <h3>📅 Timeline</h3>
            <div class="timeline-chart">
                {self._generate_timeline_html(stats.get('temporal', {}))}
            </div>
        </section>
        
        <footer class="footer">
            <p>Généré par Music Data Extractor v1.0</p>
            <p>Données extraites depuis: Genius, Spotify, Discogs</p>
        </footer>
    </div>
    
    <script>
        {self._get_html_scripts()}
    </script>
</body>
</html>
"""
        return html
    
    def _generate_collaborators_html(self, collaborators: List[tuple]) -> str:
        """Génère le HTML pour la liste des collaborateurs"""
        if not collaborators:
            return "<p>Aucun collaborateur trouvé.</p>"
        
        html = "<ul class='collaborators-grid'>"
        for name, count in collaborators[:10]:
            html += f"""
                <li class="collaborator-item">
                    <span class="collaborator-name">{name}</span>
                    <span class="collaborator-count">{count} collaboration{'s' if count > 1 else ''}</span>
                </li>
            """
        html += "</ul>"
        return html
    
    def _generate_tracks_table_html(self, tracks: List[Dict]) -> str:
        """Génère le tableau HTML des morceaux"""
        if not tracks:
            return "<p>Aucun morceau trouvé.</p>"
        
        html = """
        <table class="tracks-table">
            <thead>
                <tr>
                    <th>Titre</th>
                    <th>Album</th>
                    <th>Année</th>
                    <th>Durée</th>
                    <th>BPM</th>
                    <th>Crédits</th>
                </tr>
            </thead>
            <tbody>
        """
        
        for track in tracks:
            duration = track.get('duration_formatted', 'N/A')
            bpm = track.get('bpm', 'N/A')
            credits_count = len(track.get('credits', []))
            year = track.get('release_year', 'N/A')
            album = track.get('album_title', 'N/A')
            
            html += f"""
                <tr>
                    <td class="track-title">{track.get('title', 'N/A')}</td>
                    <td>{album}</td>
                    <td>{year}</td>
                    <td>{duration}</td>
                    <td>{bpm}</td>
                    <td><span class="credits-badge">{credits_count}</span></td>
                </tr>
            """
        
        html += """
            </tbody>
        </table>
        """
        return html
    
    def _generate_timeline_html(self, temporal_data: Dict) -> str:
        """Génère le HTML pour la timeline"""
        tracks_by_year = temporal_data.get('tracks_by_year', {})
        if not tracks_by_year:
            return "<p>Aucune donnée temporelle disponible.</p>"
        
        html = "<div class='timeline-bars'>"
        max_tracks = max(tracks_by_year.values()) if tracks_by_year else 1
        
        for year in sorted(tracks_by_year.keys()):
            count = tracks_by_year[year]
            height_percent = (count / max_tracks) * 100
            
            html += f"""
                <div class="timeline-bar">
                    <div class="bar" style="height: {height_percent}%" title="{year}: {count} morceau{'s' if count > 1 else ''}"></div>
                    <div class="year-label">{year}</div>
                    <div class="count-label">{count}</div>
                </div>
            """
        
        html += "</div>"
        return html
    
    def _get_html_styles(self) -> str:
        """Retourne les styles CSS pour le rapport HTML"""
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
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        .header {
            text-align: center;
            padding: 2rem 0;
            border-bottom: 3px solid #667eea;
            margin-bottom: 2rem;
        }
        
        .header h1 {
            color: #667eea;
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }
        
        .header h2 {
            color: #555;
            font-size: 2rem;
            font-weight: 300;
        }
        
        .meta {
            color: #888;
            font-size: 0.9rem;
            margin-top: 1rem;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 1rem 0;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 1.5rem;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        
        .stat-number {
            font-size: 2.5rem;
            font-weight: bold;
            margin-bottom: 0.5rem;
        }
        
        .stat-label {
            font-size: 0.9rem;
            opacity: 0.9;
        }
        
        section {
            margin: 2rem 0;
            padding: 1rem 0;
        }
        
        h3 {
            color: #667eea;
            font-size: 1.5rem;
            margin-bottom: 1rem;
            border-left: 4px solid #667eea;
            padding-left: 1rem;
        }
        
        .collaborators-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 0.5rem;
            list-style: none;
        }
        
        .collaborator-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem;
            background: #f8f9fa;
            border-radius: 6px;
            border-left: 3px solid #667eea;
        }
        
        .collaborator-name {
            font-weight: 500;
        }
        
        .collaborator-count {
            background: #667eea;
            color: white;
            padding: 0.25rem 0.5rem;
            border-radius: 12px;
            font-size: 0.8rem;
        }
        
        .tracks-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .tracks-table th {
            background: #667eea;
            color: white;
            padding: 1rem;
            text-align: left;
            font-weight: 500;
        }
        
        .tracks-table td {
            padding: 0.75rem 1rem;
            border-bottom: 1px solid #eee;
        }
        
        .tracks-table tr:hover {
            background: #f8f9fa;
        }
        
        .track-title {
            font-weight: 500;
            color: #667eea;
        }
        
        .credits-badge {
            background: #28a745;
            color: white;
            padding: 0.25rem 0.5rem;
            border-radius: 10px;
            font-size: 0.8rem;
        }
        
        .timeline-bars {
            display: flex;
            align-items: end;
            gap: 0.5rem;
            padding: 1rem;
            background: #f8f9fa;
            border-radius: 8px;
            min-height: 200px;
        }
        
        .timeline-bar {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-width: 60px;
        }
        
        .bar {
            width: 100%;
            background: linear-gradient(to top, #667eea, #764ba2);
            border-radius: 4px 4px 0 0;
            min-height: 10px;
            margin-bottom: 0.5rem;
            transition: all 0.3s ease;
        }
        
        .bar:hover {
            opacity: 0.8;
            transform: scale(1.05);
        }
        
        .year-label {
            font-size: 0.8rem;
            color: #666;
            font-weight: 500;
        }
        
        .count-label {
            font-size: 0.7rem;
            color: #888;
        }
        
        .footer {
            text-align: center;
            padding: 2rem 0;
            border-top: 1px solid #eee;
            color: #888;
            font-size: 0.9rem;
        }
        
        @media (max-width: 768px) {
            .container {
                margin: 10px;
                padding: 15px;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .header h2 {
                font-size: 1.5rem;
            }
            
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .tracks-table {
                font-size: 0.9rem;
            }
            
            .tracks-table th,
            .tracks-table td {
                padding: 0.5rem;
            }
        }
        """
    
    def _get_html_scripts(self) -> str:
        """Retourne les scripts JavaScript pour l'interactivité"""
        return """
        // Animation au scroll
        function animateOnScroll() {
            const elements = document.querySelectorAll('.stat-card, .collaborator-item, .timeline-bar');
            
            elements.forEach(element => {
                const elementTop = element.getBoundingClientRect().top;
                const elementVisible = 150;
                
                if (elementTop < window.innerHeight - elementVisible) {
                    element.style.opacity = '1';
                    element.style.transform = 'translateY(0)';
                }
            });
        }
        
        // Initialisation
        document.addEventListener('DOMContentLoaded', function() {
            // Style initial pour l'animation
            const animatedElements = document.querySelectorAll('.stat-card, .collaborator-item, .timeline-bar');
            animatedElements.forEach(element => {
                element.style.opacity = '0';
                element.style.transform = 'translateY(20px)';
                element.style.transition = 'all 0.6s ease';
            });
            
            // Déclenchement de l'animation
            setTimeout(animateOnScroll, 100);
            window.addEventListener('scroll', animateOnScroll);
            
            // Tooltips interactifs
            const bars = document.querySelectorAll('.bar');
            bars.forEach(bar => {
                bar.addEventListener('mouseenter', function() {
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
            days_old: Nombre de jours après lesquels supprimer
            
        Returns:
            Nombre de fichiers supprimés
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)
        deleted_count = 0
        
        for file_path in self.export_dir.glob("*"):
            if file_path.is_file():
                try:
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_mtime < cutoff_date:
                        file_path.unlink()
                        deleted_count += 1
                        self.logger.info(f"Export supprimé: {file_path.name}")
                except Exception as e:
                    self.logger.warning(f"Erreur suppression {file_path}: {e}")
        
        return deleted_count

# Fonctions utilitaires pour un usage simple

def quick_export_json(artist: Artist, tracks: List[Track], filename: Optional[str] = None) -> str:
    """Export rapide en JSON"""
    manager = ExportManager()
    return manager.export_artist_data(artist, tracks, format=ExportFormat.JSON, filename=filename)

def quick_export_html(artist: Artist, tracks: List[Track], filename: Optional[str] = None) -> str:
    """Export rapide en HTML"""
    manager = ExportManager()
    return manager.export_artist_data(artist, tracks, format=ExportFormat.HTML, filename=filename)

def export_all_formats(artist: Artist, tracks: List[Track], base_filename: Optional[str] = None) -> Dict[str, str]:
    """Exporte dans tous les formats disponibles"""
    manager = ExportManager()
    results = {}
    
    for format in ExportFormat:
        try:
            filename = f"{base_filename}_{format.value}" if base_filename else None
            filepath = manager.export_artist_data(artist, tracks, format=format, filename=filename)
            results[format.value] = filepath
        except Exception as e:
            logging.getLogger(__name__).error(f"Erreur export {format.value}: {e}")
            results[format.value] = None
    
    return results