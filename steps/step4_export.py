# steps/step4_export.py
import json
import csv
import html
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import zipfile
import tempfile

from core.database import Database
from models.entities import Artist, Album, Track, Credit, Session
from models.enums import ExportFormat, AlbumType, CreditCategory
from config.settings import settings
from utils.progress_tracker import ProgressTracker
from utils.logging_config import get_session_logger
from utils.export_utils import ExportUtils


class Step4Export:
    """
    Étape 4: Export des données extraites en multiple formats.
    
    Formats supportés:
    - JSON (détaillé et compact)
    - CSV (tracks, credits, albums séparés)
    - HTML (rapport visuel avec graphiques)
    - Excel (multi-onglets)
    - Formats pour infographies (stats JSON)
    """
    
    def __init__(self, database: Database):
        self.db = database
        self.exports_dir = settings.exports_dir
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        
    def execute(self, session: Session, progress_tracker: Optional[ProgressTracker] = None,
                export_formats: Optional[List[ExportFormat]] = None) -> Dict[str, Any]:
        """
        Exécute l'étape d'export.
        
        Args:
            session: Session d'extraction
            progress_tracker: Tracker de progression
            export_formats: Formats d'export souhaités
            
        Returns:
            Résultats de l'export avec chemins des fichiers
        """
        logger = get_session_logger(session.id, "export")
        logger.info("🚀 Début de l'étape d'export")
        
        # Formats par défaut
        if not export_formats:
            export_formats = [ExportFormat.JSON, ExportFormat.CSV, ExportFormat.HTML]
        
        # Initialiser le tracker
        if progress_tracker:
            step_name = "export"
            if step_name not in progress_tracker.steps:
                progress_tracker.add_step(step_name, "Export des données", len(export_formats))
            progress_tracker.start_step(step_name)
        
        try:
            # Récupérer l'artiste et ses données
            artist = self.db.get_artist_by_name(session.artist_name)
            if not artist:
                raise ValueError(f"Artiste '{session.artist_name}' non trouvé")
            
            logger.info(f"📊 Export des données pour {artist.name}")
            
            # Charger toutes les données
            tracks = self.db.get_tracks_by_artist_id(artist.id)
            albums = self.db.get_albums_by_artist_id(artist.id)
            
            logger.info(f"📈 Données à exporter: {len(tracks)} tracks, {len(albums)} albums")
            
            # Créer le dossier d'export pour cette session
            export_folder = self._create_export_folder(session.id, artist.name)
            
            # Générer les statistiques
            stats = self._generate_statistics(artist, tracks, albums)
            
            # Exporter dans chaque format demandé
            exported_files = {}
            
            for i, format_type in enumerate(export_formats):
                try:
                    logger.info(f"📋 Export au format {format_type.value}")
                    
                    if format_type == ExportFormat.JSON:
                        files = self._export_json(export_folder, artist, tracks, albums, stats)
                        exported_files.update(files)
                    
                    elif format_type == ExportFormat.CSV:
                        files = self._export_csv(export_folder, artist, tracks, albums)
                        exported_files.update(files)
                    
                    elif format_type == ExportFormat.HTML:
                        files = self._export_html(export_folder, artist, tracks, albums, stats)
                        exported_files.update(files)
                    
                    elif format_type == ExportFormat.EXCEL:
                        files = self._export_excel(export_folder, artist, tracks, albums, stats)
                        exported_files.update(files)
                    
                    # Mise à jour progression
                    if progress_tracker:
                        progress_tracker.update_step_progress("export", i + 1)
                    
                    logger.info(f"✅ Export {format_type.value} terminé")
                    
                except Exception as e:
                    logger.error(f"❌ Erreur export {format_type.value}: {e}")
                    if progress_tracker:
                        progress_tracker.add_step_error("export", f"Erreur {format_type.value}: {str(e)}")
            
            # Créer un fichier ZIP avec tous les exports
            zip_file = self._create_zip_archive(export_folder, exported_files)
            exported_files["archive"] = str(zip_file)
            
            # Finaliser
            if progress_tracker:
                progress_tracker.complete_step("export")
            
            logger.info(f"🎉 Export terminé - {len(exported_files)} fichiers créés")
            
            return {
                "success": True,
                "export_folder": str(export_folder),
                "exported_files": exported_files,
                "statistics": stats,
                "formats": [f.value for f in export_formats]
            }
            
        except Exception as e:
            logger.error(f"💥 Erreur dans l'étape d'export: {e}")
            if progress_tracker:
                progress_tracker.fail_step("export", str(e))
            
            return {
                "success": False,
                "error": str(e),
                "exported_files": {}
            }
    
    def _create_export_folder(self, session_id: str, artist_name: str) -> Path:
        """Crée le dossier d'export pour la session"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{artist_name}_{session_id}_{timestamp}"
        # Nettoyer le nom de dossier
        folder_name = "".join(c for c in folder_name if c.isalnum() or c in "._-")
        
        export_folder = self.exports_dir / folder_name
        export_folder.mkdir(parents=True, exist_ok=True)
        
        return export_folder
    
    def _generate_statistics(self, artist: Artist, tracks: List[Track], albums: List[Album]) -> Dict[str, Any]:
        """Génère les statistiques complètes pour l'artiste"""
        
        # Statistiques générales
        total_tracks = len(tracks)
        total_albums = len(albums)
        total_duration = sum(t.duration_seconds or 0 for t in tracks)
        
        # Statistiques par type d'album
        albums_by_type = {}
        for album_type in AlbumType:
            count = len([a for a in albums if a.album_type == album_type])
            if count > 0:
                albums_by_type[album_type.value] = count
        
        # Statistiques de crédits
        all_credits = []
        for track in tracks:
            all_credits.extend(track.credits)
        
        credits_by_category = {}
        for category in CreditCategory:
            count = len([c for c in all_credits if c.credit_category == category])
            if count > 0:
                credits_by_category[category.value] = count
        
        # Top collaborateurs
        collaborators = {}
        for track in tracks:
            for credit in track.credits:
                if credit.person_name and credit.person_name != artist.name:
                    collaborators[credit.person_name] = collaborators.get(credit.person_name, 0) + 1
        
        top_collaborators = sorted(collaborators.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Producteurs récurrents
        producers = {}
        for track in tracks:
            track_producers = track.get_producers()
            for producer in track_producers:
                if producer != artist.name:
                    producers[producer] = producers.get(producer, 0) + 1
        
        top_producers = sorted(producers.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Statistiques par année
        tracks_by_year = {}
        for track in tracks:
            year = track.release_year or "Unknown"
            tracks_by_year[str(year)] = tracks_by_year.get(str(year), 0) + 1
        
        # Statistiques BPM
        bpm_values = [t.bpm for t in tracks if t.bpm]
        bpm_stats = {}
        if bpm_values:
            bpm_stats = {
                "average": round(sum(bpm_values) / len(bpm_values), 1),
                "min": min(bpm_values),
                "max": max(bpm_values),
                "count": len(bpm_values)
            }
        
        # Compilation des statistiques
        stats = {
            "artist": {
                "name": artist.name,
                "total_tracks": total_tracks,
                "total_albums": total_albums,
                "total_duration_seconds": total_duration,
                "total_duration_formatted": self._format_duration(total_duration),
                "tracks_with_lyrics": len([t for t in tracks if t.has_lyrics]),
                "tracks_with_bpm": len([t for t in tracks if t.bpm]),
                "tracks_with_credits": len([t for t in tracks if t.credits])
            },
            "albums": {
                "by_type": albums_by_type,
                "total": total_albums
            },
            "credits": {
                "total": len(all_credits),
                "by_category": credits_by_category,
                "unique_collaborators": len(collaborators),
                "top_collaborators": top_collaborators,
                "top_producers": top_producers
            },
            "timeline": {
                "tracks_by_year": tracks_by_year,
                "years_active": len([y for y in tracks_by_year.keys() if y != "Unknown"])
            },
            "audio": {
                "bpm_statistics": bpm_stats,
                "average_track_duration": round(total_duration / total_tracks, 1) if total_tracks > 0 else 0
            },
            "quality": {
                "completeness_score": self._calculate_completeness_score(tracks),
                "data_coverage": self._calculate_data_coverage(tracks)
            }
        }
        
        return stats
    
    def _export_json(self, export_folder: Path, artist: Artist, tracks: List[Track], 
                    albums: List[Album], stats: Dict[str, Any]) -> Dict[str, str]:
        """Export au format JSON"""
        files = {}
        
        # Export complet détaillé
        complete_data = {
            "metadata": {
                "export_date": datetime.now().isoformat(),
                "format": "complete",
                "version": "1.0"
            },
            "artist": artist.to_dict(),
            "albums": [album.to_dict() for album in albums],
            "tracks": [track.to_dict() for track in tracks],
            "statistics": stats
        }
        
        complete_file = export_folder / f"{artist.name}_complete.json"
        with open(complete_file, 'w', encoding='utf-8') as f:
            json.dump(complete_data, f, indent=2, ensure_ascii=False)
        files["json_complete"] = str(complete_file)
        
        # Export compact pour infographies
        compact_data = {
            "artist_name": artist.name,
            "statistics": stats,
            "tracks_summary": [
                {
                    "title": track.title,
                    "album": track.album_title,
                    "year": track.release_year,
                    "duration": track.duration_seconds,
                    "bpm": track.bpm,
                    "producers": track.get_producers(),
                    "featuring": track.featuring_artists,
                    "credits_count": len(track.credits)
                }
                for track in tracks
            ]
        }
        
        compact_file = export_folder / f"{artist.name}_infographics.json"
        with open(compact_file, 'w', encoding='utf-8') as f:
            json.dump(compact_data, f, indent=2, ensure_ascii=False)
        files["json_infographics"] = str(compact_file)
        
        # Export statistiques seules
        stats_file = export_folder / f"{artist.name}_statistics.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        files["json_statistics"] = str(stats_file)
        
        return files
    
    def _export_csv(self, export_folder: Path, artist: Artist, tracks: List[Track], 
                   albums: List[Album]) -> Dict[str, str]:
        """Export au format CSV"""
        files = {}
        
        # CSV des tracks
        tracks_file = export_folder / f"{artist.name}_tracks.csv"
        with open(tracks_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # En-têtes
            headers = [
                'title', 'album', 'track_number', 'release_year', 'duration_seconds',
                'duration_formatted', 'bpm', 'key', 'has_lyrics', 'genius_url',
                'producers', 'featuring_artists', 'credits_count', 'unique_collaborators'
            ]
            writer.writerow(headers)
            
            # Données des tracks
            for track in tracks:
                writer.writerow([
                    track.title,
                    track.album_title or '',
                    track.track_number or '',
                    track.release_year or '',
                    track.duration_seconds or '',
                    track.get_duration_formatted(),
                    track.bpm or '',
                    track.key or '',
                    'Yes' if track.has_lyrics else 'No',
                    track.genius_url or '',
                    '; '.join(track.get_producers()),
                    '; '.join(track.featuring_artists),
                    len(track.credits),
                    len(track.get_unique_collaborators())
                ])
        
        files["csv_tracks"] = str(tracks_file)
        
        # CSV des crédits
        credits_file = export_folder / f"{artist.name}_credits.csv"
        with open(credits_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # En-têtes
            headers = [
                'track_title', 'track_album', 'credit_category', 'credit_type',
                'person_name', 'instrument', 'is_primary', 'is_featuring', 'data_source'
            ]
            writer.writerow(headers)
            
            # Données des crédits
            for track in tracks:
                for credit in track.credits:
                    writer.writerow([
                        track.title,
                        track.album_title or '',
                        credit.credit_category.value if credit.credit_category else '',
                        credit.credit_type.value,
                        credit.person_name,
                        credit.instrument or '',
                        'Yes' if credit.is_primary else 'No',
                        'Yes' if credit.is_featuring else 'No',
                        credit.data_source.value
                    ])
        
        files["csv_credits"] = str(credits_file)
        
        # CSV des albums
        albums_file = export_folder / f"{artist.name}_albums.csv"
        with open(albums_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # En-têtes
            headers = [
                'title', 'release_year', 'album_type', 'track_count',
                'total_duration_seconds', 'duration_formatted', 'genre', 'label'
            ]
            writer.writerow(headers)
            
            # Données des albums
            for album in albums:
                writer.writerow([
                    album.title,
                    album.release_year or '',
                    album.album_type.value if album.album_type else '',
                    album.track_count or '',
                    album.total_duration or '',
                    album.get_duration_formatted(),
                    album.genre or '',
                    album.label or ''
                ])
        
        files["csv_albums"] = str(albums_file)
        
        return files
    
    def _export_html(self, export_folder: Path, artist: Artist, tracks: List[Track],
                    albums: List[Album], stats: Dict[str, Any]) -> Dict[str, str]:
        """Export au format HTML avec rapport visuel"""
        files = {}
        
        html_content = self._generate_html_report(artist, tracks, albums, stats)
        
        html_file = export_folder / f"{artist.name}_report.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        files["html_report"] = str(html_file)
        return files
    
    def _export_excel(self, export_folder: Path, artist: Artist, tracks: List[Track],
                     albums: List[Album], stats: Dict[str, Any]) -> Dict[str, str]:
        """Export au format Excel avec multiple onglets"""
        files = {}
        
        try:
            import pandas as pd
            
            excel_file = export_folder / f"{artist.name}_data.xlsx"
            
            with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
                # Onglet Résumé
                summary_data = {
                    'Métrique': ['Nombre de tracks', 'Nombre d\'albums', 'Durée totale (h)', 
                               'Tracks avec paroles', 'Tracks avec BPM', 'Collaborateurs uniques'],
                    'Valeur': [
                        stats['artist']['total_tracks'],
                        stats['artist']['total_albums'],
                        round(stats['artist']['total_duration_seconds'] / 3600, 1),
                        stats['artist']['tracks_with_lyrics'],
                        stats['artist']['tracks_with_bpm'],
                        stats['credits']['unique_collaborators']
                    ]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Résumé', index=False)
                
                # Onglet Tracks
                tracks_data = []
                for track in tracks:
                    tracks_data.append({
                        'Titre': track.title,
                        'Album': track.album_title or '',
                        'Numéro': track.track_number or '',
                        'Année': track.release_year or '',
                        'Durée (s)': track.duration_seconds or '',
                        'BPM': track.bpm or '',
                        'Clé': track.key or '',
                        'Paroles': 'Oui' if track.has_lyrics else 'Non',
                        'Producteurs': '; '.join(track.get_producers()),
                        'Featuring': '; '.join(track.featuring_artists),
                        'Nb Crédits': len(track.credits)
                    })
                pd.DataFrame(tracks_data).to_excel(writer, sheet_name='Tracks', index=False)
                
                # Onglet Albums
                albums_data = []
                for album in albums:
                    albums_data.append({
                        'Titre': album.title,
                        'Année': album.release_year or '',
                        'Type': album.album_type.value if album.album_type else '',
                        'Nb Tracks': album.track_count or '',
                        'Durée (s)': album.total_duration or '',
                        'Genre': album.genre or '',
                        'Label': album.label or ''
                    })
                pd.DataFrame(albums_data).to_excel(writer, sheet_name='Albums', index=False)
                
                # Onglet Crédits
                credits_data = []
                for track in tracks:
                    for credit in track.credits:
                        credits_data.append({
                            'Track': track.title,
                            'Album': track.album_title or '',
                            'Catégorie': credit.credit_category.value if credit.credit_category else '',
                            'Type': credit.credit_type.value,
                            'Personne': credit.person_name,
                            'Instrument': credit.instrument or '',
                            'Source': credit.data_source.value
                        })
                pd.DataFrame(credits_data).to_excel(writer, sheet_name='Crédits', index=False)
            
            files["excel_data"] = str(excel_file)
            
        except ImportError:
            print("⚠️ pandas non disponible, export Excel ignoré")
        
        return files
    
    def _generate_html_report(self, artist: Artist, tracks: List[Track],
                             albums: List[Album], stats: Dict[str, Any]) -> str:
        """Génère un rapport HTML complet"""
        
        html = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rapport d'extraction - {html.escape(artist.name)}</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
        .stat-card {{ background: #ecf0f1; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #3498db; }}
        .stat-label {{ color: #7f8c8d; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #3498db; color: white; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .progress-bar {{ background: #ecf0f1; height: 20px; border-radius: 10px; overflow: hidden; margin: 5px 0; }}
        .progress-fill {{ height: 100%; background: #3498db; transition: width 0.3s ease; }}
        .album-type {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 0.8em; margin: 2px; }}
        .album {{ background: #3498db; color: white; }}
        .ep {{ background: #e74c3c; color: white; }}
        .single {{ background: #f39c12; color: white; }}
        .mixtape {{ background: #9b59b6; color: white; }}
        .footer {{ margin-top: 40px; text-align: center; color: #7f8c8d; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Rapport d'extraction - {html.escape(artist.name)}</h1>
        <p><strong>Date d'export:</strong> {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
        
        <h2>📈 Statistiques générales</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{stats['artist']['total_tracks']}</div>
                <div class="stat-label">Tracks totaux</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['artist']['total_albums']}</div>
                <div class="stat-label">Albums</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['artist']['total_duration_formatted']}</div>
                <div class="stat-label">Durée totale</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['credits']['unique_collaborators']}</div>
                <div class="stat-label">Collaborateurs</div>
            </div>
        </div>
        
        <h2>🎵 Répartition par type d'album</h2>
        <div class="stats-grid">
        """
        
        for album_type, count in stats['albums']['by_type'].items():
            html += f"""
            <div class="stat-card">
                <div class="stat-number">{count}</div>
                <div class="stat-label">{album_type.title()}</div>
            </div>
            """
        
        html += """
        </div>
        
        <h2>🏆 Top Collaborateurs</h2>
        <table>
            <thead>
                <tr><th>Collaborateur</th><th>Nombre de tracks</th><th>Pourcentage</th></tr>
            </thead>
            <tbody>
        """
        
        total_tracks = stats['artist']['total_tracks']
        for collaborator, count in stats['credits']['top_collaborators'][:10]:
            percentage = (count / total_tracks * 100) if total_tracks > 0 else 0
            html += f"""
                <tr>
                    <td>{html.escape(collaborator)}</td>
                    <td>{count}</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {percentage}%"></div>
                        </div>
                        {percentage:.1f}%
                    </td>
                </tr>
            """
        
        html += """
            </tbody>
        </table>
        
        <h2>🎛️ Top Producteurs</h2>
        <table>
            <thead>
                <tr><th>Producteur</th><th>Nombre de tracks</th><th>Pourcentage</th></tr>
            </thead>
            <tbody>
        """
        
        for producer, count in stats['credits']['top_producers'][:10]:
            percentage = (count / total_tracks * 100) if total_tracks > 0 else 0
            html += f"""
                <tr>
                    <td>{html.escape(producer)}</td>
                    <td>{count}</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {percentage}%"></div>
                        </div>
                        {percentage:.1f}%
                    </td>
                </tr>
            """
        
        html += """
            </tbody>
        </table>
        
        <h2>📅 Timeline</h2>
        <table>
            <thead>
                <tr><th>Année</th><th>Nombre de tracks</th><th>Répartition</th></tr>
            </thead>
            <tbody>
        """
        
        max_tracks_year = max(stats['timeline']['tracks_by_year'].values()) if stats['timeline']['tracks_by_year'] else 1
        for year, count in sorted(stats['timeline']['tracks_by_year'].items()):
            percentage = (count / max_tracks_year * 100)
            html += f"""
                <tr>
                    <td>{year}</td>
                    <td>{count}</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {percentage}%"></div>
                        </div>
                    </td>
                </tr>
            """
        
        # Statistiques audio si disponibles
        bpm_stats = stats['audio']['bpm_statistics']
        if bmp_stats:
            html += f"""
        </tbody>
        </table>
        
        <h2>🎵 Statistiques Audio</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{bpm_stats.get('average', 'N/A')}</div>
                <div class="stat-label">BPM moyen</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{bpm_stats.get('min', 'N/A')}</div>
                <div class="stat-label">BPM min</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{bmp_stats.get('max', 'N/A')}</div>
                <div class="stat-label">BPM max</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{bmp_stats.get('count', 'N/A')}</div>
                <div class="stat-label">Tracks avec BPM</div>
            </div>
        </div>
            """
        
        html += f"""
        
        <h2>✅ Qualité des données</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{stats['quality']['completeness_score']:.1f}%</div>
                <div class="stat-label">Score de complétude</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['artist']['tracks_with_lyrics']}</div>
                <div class="stat-label">Tracks avec paroles</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['artist']['tracks_with_bpm']}</div>
                <div class="stat-label">Tracks avec BPM</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats['artist']['tracks_with_credits']}</div>
                <div class="stat-label">Tracks avec crédits</div>
            </div>
        </div>
        
        <div class="footer">
            <p>Rapport généré par Music Data Extractor | {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
        </div>
    </div>
</body>
</html>
        """
        
        return html
    
    def _create_zip_archive(self, export_folder: Path, exported_files: Dict[str, str]) -> Path:
        """Crée une archive ZIP avec tous les fichiers exportés"""
        zip_path = export_folder / f"{export_folder.name}.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_type, file_path in exported_files.items():
                if file_type != "archive":  # Éviter la récursion
                    file_path_obj = Path(file_path)
                    if file_path_obj.exists():
                        # Ajouter le fichier avec un nom relatif
                        arcname = file_path_obj.name
                        zipf.write(file_path, arcname)
        
        return zip_path
    
    def _format_duration(self, seconds: int) -> str:
        """Formate une durée en secondes vers un format lisible"""
        if seconds is None or seconds <= 0:
            return "0:00"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"
    
    def _calculate_completeness_score(self, tracks: List[Track]) -> float:
        """Calcule un score de complétude des données"""
        if not tracks:
            return 0.0
        
        total_score = 0
        for track in tracks:
            track_score = 0
            max_score = 7  # Nombre de critères
            
            # Critères de complétude
            if track.duration_seconds:
                track_score += 1
            if track.bpm:
                track_score += 1
            if track.album_title:
                track_score += 1
            if track.release_year:
                track_score += 1
            if track.credits:
                track_score += 1
            if track.has_lyrics:
                track_score += 1
            if track.featuring_artists:
                track_score += 0.5  # Bonus pour featuring
            
            total_score += (track_score / max_score)
        
        return (total_score / len(tracks)) * 100
    
    def _calculate_data_coverage(self, tracks: List[Track]) -> Dict[str, float]:
        """Calcule la couverture des données par catégorie"""
        if not tracks:
            return {}
        
        total = len(tracks)
        
        return {
            "duration": (len([t for t in tracks if t.duration_seconds]) / total) * 100,
            "bpm": (len([t for t in tracks if t.bpm]) / total) * 100,
            "albums": (len([t for t in tracks if t.album_title]) / total) * 100,
            "lyrics": (len([t for t in tracks if t.has_lyrics]) / total) * 100,
            "credits": (len([t for t in tracks if t.credits]) / total) * 100,
            "featuring": (len([t for t in tracks if t.featuring_artists]) / total) * 100
        }