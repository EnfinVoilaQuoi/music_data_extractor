# steps/step4_export.py
"""Étape 4: Export optimisé multi-format des données traitées"""

import logging
import asyncio
import json
import csv
import yaml
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache
import zipfile
import io

from core.database import Database
from core.session_manager import SessionManager, get_session_manager
from core.cache import smart_cache
from core.exceptions import ExportError
from models.entities import Artist, Track, Credit, Album, Session
from models.enums import ExportFormat, QualityLevel, SessionStatus
from config.settings import settings

# Imports conditionnels pour les exporters
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None

try:
    from openpyxl import Workbook
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    Workbook = None

try:
    import xml.etree.ElementTree as ET
    XML_AVAILABLE = True
except ImportError:
    XML_AVAILABLE = False
    ET = None

try:
    from jinja2 import Template
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    Template = None

@dataclass
class ExportJob:
    """Tâche d'export avec métadonnées"""
    job_id: str
    artist_name: str
    formats: List[ExportFormat]
    options: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed
    file_paths: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    @property
    def duration_seconds(self) -> Optional[float]:
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds()

@dataclass
class ExportStats:
    """Statistiques détaillées de l'export"""
    total_items: int = 0
    exported_tracks: int = 0
    exported_credits: int = 0
    exported_albums: int = 0
    exported_sessions: int = 0
    
    # Formats générés
    formats_generated: List[str] = field(default_factory=list)
    total_file_size_bytes: int = 0
    compressed_size_bytes: int = 0
    
    # Performance
    export_time_seconds: float = 0.0
    cache_hits: int = 0
    template_renderings: int = 0
    
    # Fichiers générés
    files_created: List[str] = field(default_factory=list)
    archive_created: Optional[str] = None
    
    @property
    def compression_ratio(self) -> float:
        """Taux de compression (0-1)"""
        if self.total_file_size_bytes == 0:
            return 0.0
        return 1 - (self.compressed_size_bytes / self.total_file_size_bytes)
    
    @property
    def export_rate(self) -> float:
        """Éléments exportés par seconde"""
        if self.export_time_seconds == 0:
            return 0.0
        return self.total_items / self.export_time_seconds
    
    @property
    def average_file_size_mb(self) -> float:
        """Taille moyenne des fichiers en MB"""
        if not self.files_created:
            return 0.0
        return (self.total_file_size_bytes / len(self.files_created)) / (1024 * 1024)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour export"""
        return {
            'total_items': self.total_items,
            'exported_tracks': self.exported_tracks,
            'exported_credits': self.exported_credits,
            'exported_albums': self.exported_albums,
            'exported_sessions': self.exported_sessions,
            'formats_generated': self.formats_generated,
            'total_file_size_bytes': self.total_file_size_bytes,
            'total_file_size_mb': round(self.total_file_size_bytes / (1024 * 1024), 2),
            'compressed_size_bytes': self.compressed_size_bytes,
            'compressed_size_mb': round(self.compressed_size_bytes / (1024 * 1024), 2),
            'compression_ratio': self.compression_ratio,
            'export_time_seconds': self.export_time_seconds,
            'cache_hits': self.cache_hits,
            'template_renderings': self.template_renderings,
            'files_created': self.files_created,
            'archive_created': self.archive_created,
            'export_rate': self.export_rate,
            'average_file_size_mb': self.average_file_size_mb
        }


class ExportStep:
    """
    Étape 4: Export optimisé multi-format des données traitées.
    
    Responsabilités :
    - Export vers multiples formats (JSON, CSV, Excel, HTML, XML, YAML)
    - Génération de rapports visuels
    - Compression et archivage automatiques
    - Templates personnalisables
    - Export incrémental et par lots
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None, 
                 database: Optional[Database] = None):
        self.logger = logging.getLogger(__name__)
        
        # Composants core
        self.session_manager = session_manager or get_session_manager()
        self.database = database or Database()
        
        # Configuration optimisée
        self.config = self._load_optimized_config()
        
        # Cache pour templates et données
        self._template_cache = {}
        self._data_cache = {}
        
        # Gestionnaire de jobs d'export
        self._export_jobs = {}
        
        # Templates par défaut
        self._default_templates = self._load_default_templates()
        
        # Statistiques de performance
        self.performance_stats = {
            'total_exports': 0,
            'total_files_created': 0,
            'total_size_generated_mb': 0.0,
            'average_export_time': 0.0
        }
        
        self.logger.info(f"ExportStep optimisé initialisé "
                        f"(Pandas: {PANDAS_AVAILABLE}, "
                        f"Excel: {OPENPYXL_AVAILABLE}, "
                        f"Templates: {JINJA2_AVAILABLE})")
    
    def _load_optimized_config(self) -> Dict[str, Any]:
        """Charge la configuration optimisée"""
        exports_dir = Path(settings.exports_dir)
        exports_dir.mkdir(parents=True, exist_ok=True)
        
        return {
            'exports_dir': exports_dir,
            'include_lyrics': settings.get('exports.include_lyrics', True),
            'include_raw_data': settings.get('exports.include_raw_data', False),
            'include_metadata': settings.get('exports.include_metadata', True),
            'include_quality_scores': settings.get('exports.include_quality_scores', True),
            'compress_exports': settings.get('exports.compress_exports', True),
            'create_archive': settings.get('exports.create_archive', True),
            'cache_templates': settings.get('exports.cache_templates', True),
            'auto_cleanup_days': settings.get('exports.auto_cleanup_days', 30),
            'max_items_per_file': settings.get('exports.max_items_per_file', 10000),
            'use_custom_templates': settings.get('exports.use_custom_templates', True),
            'generate_summary': settings.get('exports.generate_summary', True),
            'parallel_export': settings.get('exports.parallel_export', True)
        }
    
    def _load_default_templates(self) -> Dict[str, str]:
        """Charge les templates par défaut"""
        if not JINJA2_AVAILABLE:
            return {}
        
        return {
            'html_report': """
<!DOCTYPE html>
<html>
<head>
    <title>{{ artist_name }} - Rapport d'extraction</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #f4f4f4; padding: 20px; border-radius: 5px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .stat-card { background: white; border: 1px solid #ddd; padding: 15px; border-radius: 5px; }
        .track-list { margin-top: 20px; }
        .track { border-bottom: 1px solid #eee; padding: 10px 0; }
        .credits { font-size: 0.9em; color: #666; margin-top: 5px; }
        .quality-high { color: #28a745; }
        .quality-medium { color: #ffc107; }
        .quality-low { color: #dc3545; }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ artist_name }}</h1>
        <p>Rapport généré le {{ export_date }}</p>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <h3>Morceaux</h3>
            <p><strong>{{ tracks|length }}</strong> morceaux extraits</p>
        </div>
        <div class="stat-card">
            <h3>Crédits</h3>
            <p><strong>{{ credits|length }}</strong> crédits trouvés</p>
        </div>
        <div class="stat-card">
            <h3>Qualité</h3>
            <p>Score moyen: <strong>{{ average_quality_score|round(1) }}/100</strong></p>
        </div>
    </div>
    
    <div class="track-list">
        <h2>Liste des morceaux</h2>
        {% for track in tracks %}
        <div class="track">
            <h4>{{ track.title }}</h4>
            {% if track.album_name %}<p><em>Album: {{ track.album_name }}</em></p>{% endif %}
            {% if track.duration_formatted %}<p>Durée: {{ track.duration_formatted }}</p>{% endif %}
            {% if track.quality_score %}
                <p class="quality-{{ 'high' if track.quality_score >= 80 else 'medium' if track.quality_score >= 60 else 'low' }}">
                    Qualité: {{ track.quality_score|round(1) }}/100
                </p>
            {% endif %}
            {% if track.credits %}
                <div class="credits">
                    <strong>Crédits:</strong>
                    {% for credit in track.credits %}
                        {{ credit.person_name }} ({{ credit.credit_type.replace('_', ' ').title() }}){% if not loop.last %}, {% endif %}
                    {% endfor %}
                </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
</body>
</html>
            """,
            
            'summary_template': """
# {{ artist_name }} - Résumé d'extraction

**Date d'export:** {{ export_date }}
**Formats générés:** {{ formats_generated|join(', ') }}

## Statistiques

- **Morceaux:** {{ tracks|length }}
- **Crédits:** {{ credits|length }}
- **Albums:** {{ albums|length }}
- **Score qualité moyen:** {{ average_quality_score|round(1) }}/100

## Répartition qualité

- **Haute qualité:** {{ high_quality_count }} morceaux
- **Qualité moyenne:** {{ medium_quality_count }} morceaux  
- **Faible qualité:** {{ low_quality_count }} morceaux

## Top contributeurs

{% for contributor in top_contributors[:10] %}
- **{{ contributor.name }}:** {{ contributor.credit_count }} crédits
{% endfor %}

---
*Généré par Music Data Extractor*
            """
        }
    
    @smart_cache.cache_result("artist_export", expire_days=1)
    async def export_artist_data(self, artist_name: str,
                                formats: List[Union[str, ExportFormat]],
                                options: Optional[Dict[str, Any]] = None,
                                progress_callback: Optional[callable] = None) -> Tuple[List[str], ExportStats]:
        """
        Exporte toutes les données d'un artiste vers les formats spécifiés.
        
        Args:
            artist_name: Nom de l'artiste
            formats: Liste des formats d'export
            options: Options d'export (optionnel)
            progress_callback: Callback de progression
            
        Returns:
            Tuple[List[str], ExportStats]: Chemins des fichiers générés et statistiques
        """
        start_time = datetime.now()
        stats = ExportStats()
        options = options or {}
        
        # Normalisation des formats
        export_formats = self._normalize_formats(formats)
        if not export_formats:
            raise ExportError("Aucun format d'export valide spécifié")
        
        try:
            # Création du job d'export
            job_id = f"export_{artist_name}_{start_time.strftime('%Y%m%d_%H%M%S')}"
            export_job = ExportJob(
                job_id=job_id,
                artist_name=artist_name,
                formats=export_formats,
                options=options
            )
            
            self._export_jobs[job_id] = export_job
            export_job.started_at = start_time
            export_job.status = "running"
            
            self.logger.info(f"📤 Export démarré pour {artist_name}: {[f.value for f in export_formats]}")
            
            # Récupération des données
            export_data = await self._gather_export_data(artist_name, options, stats)
            if not export_data:
                raise ExportError(f"Aucune donnée trouvée pour l'artiste '{artist_name}'")
            
            # Création du dossier d'export
            export_dir = self._create_export_directory(artist_name, job_id)
            
            # Export parallèle vers tous les formats
            if self.config['parallel_export'] and len(export_formats) > 1:
                file_paths = await self._export_parallel_formats(
                    export_data, export_formats, export_dir, stats, progress_callback
                )
            else:
                file_paths = await self._export_sequential_formats(
                    export_data, export_formats, export_dir, stats, progress_callback
                )
            
            # Génération du résumé
            if self.config['generate_summary']:
                summary_path = await self._generate_summary_report(
                    export_data, export_dir, stats
                )
                file_paths.append(summary_path)
            
            # Création d'une archive si demandé
            if self.config['create_archive'] and len(file_paths) > 1:
                archive_path = await self._create_export_archive(
                    file_paths, export_dir, artist_name
                )
                stats.archive_created = str(archive_path)
                stats.compressed_size_bytes = archive_path.stat().st_size
            
            # Finalisation
            end_time = datetime.now()
            stats.export_time_seconds = (end_time - start_time).total_seconds()
            stats.files_created = [str(p) for p in file_paths]
            stats.formats_generated = [f.value for f in export_formats]
            
            export_job.completed_at = end_time
            export_job.status = "completed"
            export_job.file_paths = stats.files_created
            
            # Mise à jour des stats globales
            self._update_performance_stats(stats)
            
            self.logger.info(f"✅ Export terminé pour {artist_name}: "
                           f"{len(file_paths)} fichiers générés "
                           f"({stats.total_file_size_bytes / (1024*1024):.1f} MB) "
                           f"en {stats.export_time_seconds:.2f}s")
            
            return stats.files_created, stats
            
        except Exception as e:
            export_job.status = "failed"
            export_job.error_message = str(e)
            self.logger.error(f"❌ Erreur export pour {artist_name}: {e}")
            raise ExportError(f"Échec export: {e}")
    
    def _normalize_formats(self, formats: List[Union[str, ExportFormat]]) -> List[ExportFormat]:
        """Normalise la liste des formats d'export"""
        normalized = []
        
        for fmt in formats:
            if isinstance(fmt, str):
                try:
                    export_format = ExportFormat(fmt.lower())
                    normalized.append(export_format)
                except ValueError:
                    self.logger.warning(f"Format d'export inconnu: {fmt}")
            elif isinstance(fmt, ExportFormat):
                normalized.append(fmt)
        
        return normalized
    
    async def _gather_export_data(self, artist_name: str, 
                                options: Dict[str, Any], 
                                stats: ExportStats) -> Dict[str, Any]:
        """Rassemble toutes les données à exporter"""
        
        # Récupération de l'artiste
        artist = self.database.get_artist_by_name(artist_name)
        if not artist:
            return {}
        
        # Récupération des données associées
        tracks = self.database.get_tracks_by_artist(artist.id)
        credits = self.database.get_credits_by_artist(artist.id)
        albums = self.database.get_albums_by_artist(artist.id)
        sessions = self.database.get_sessions_by_artist(artist_name)
        
        # Filtrage selon les options
        if not options.get('include_failed_extractions', True):
            tracks = [t for t in tracks if t.extraction_status != 'failed']
        
        if options.get('min_quality_score'):
            min_score = options['min_quality_score']
            tracks = [t for t in tracks if t.quality_score >= min_score]
        
        # Statistiques
        stats.total_items = len(tracks) + len(credits) + len(albums)
        stats.exported_tracks = len(tracks)
        stats.exported_credits = len(credits)
        stats.exported_albums = len(albums)
        stats.exported_sessions = len(sessions)
        
        # Préparation des données d'export
        export_data = {
            'artist': artist.to_dict(),
            'tracks': [self._prepare_track_for_export(t, options) for t in tracks],
            'credits': [self._prepare_credit_for_export(c, options) for c in credits],
            'albums': [self._prepare_album_for_export(a, options) for a in albums],
            'sessions': [self._prepare_session_for_export(s, options) for s in sessions],
            'metadata': {
                'export_date': datetime.now().isoformat(),
                'artist_name': artist_name,
                'total_tracks': len(tracks),
                'total_credits': len(credits),
                'total_albums': len(albums),
                'average_quality_score': sum(t.quality_score or 0 for t in tracks) / max(len(tracks), 1),
                'options': options
            }
        }
        
        # Enrichissement avec données dérivées
        export_data.update(self._calculate_derived_data(export_data))
        
        return export_data
    
    def _prepare_track_for_export(self, track: Track, options: Dict[str, Any]) -> Dict[str, Any]:
        """Prépare un morceau pour l'export"""
        track_data = track.to_dict()
        
        # Filtrage des données selon les options
        if not options.get('include_lyrics', self.config['include_lyrics']):
            track_data.pop('lyrics', None)
        
        if not options.get('include_raw_data', self.config['include_raw_data']):
            track_data.pop('metadata', None)
        
        # Ajout de données calculées
        track_data['has_complete_credits'] = bool(track.credits and len(track.credits) > 2)
        track_data['quality_category'] = self._get_quality_category(track.quality_score)
        
        return track_data
    
    def _prepare_credit_for_export(self, credit: Credit, options: Dict[str, Any]) -> Dict[str, Any]:
        """Prépare un crédit pour l'export"""
        credit_data = credit.to_dict()
        
        # Ajout de données enrichies
        credit_data['category_display'] = credit.credit_category.value.replace('_', ' ').title()
        credit_data['type_display'] = credit.credit_type.value.replace('_', ' ').title()
        
        return credit_data
    
    def _prepare_album_for_export(self, album: Album, options: Dict[str, Any]) -> Dict[str, Any]:
        """Prépare un album pour l'export"""
        return album.to_dict()
    
    def _prepare_session_for_export(self, session: Session, options: Dict[str, Any]) -> Dict[str, Any]:
        """Prépare une session pour l'export"""
        session_data = session.to_dict()
        
        # Filtrage des métadonnées sensibles
        if 'metadata' in session_data and not options.get('include_raw_data', False):
            filtered_metadata = {k: v for k, v in session_data['metadata'].items() 
                               if not k.startswith('_') and k != 'error_details'}
            session_data['metadata'] = filtered_metadata
        
        return session_data
    
    def _calculate_derived_data(self, export_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calcule des données dérivées pour l'export"""
        tracks = export_data['tracks']
        credits = export_data['credits']
        
        # Top contributeurs
        contributor_counts = {}
        for credit in credits:
            name = credit['person_name']
            contributor_counts[name] = contributor_counts.get(name, 0) + 1
        
        top_contributors = [
            {'name': name, 'credit_count': count}
            for name, count in sorted(contributor_counts.items(), key=lambda x: x[1], reverse=True)
        ]
        
        # Répartition qualité
        quality_distribution = {'high': 0, 'medium': 0, 'low': 0}
        for track in tracks:
            category = self._get_quality_category(track.get('quality_score', 0))
            quality_distribution[category] += 1
        
        # Statistiques par type de crédit
        credit_type_stats = {}
        for credit in credits:
            credit_type = credit['credit_type']
            credit_type_stats[credit_type] = credit_type_stats.get(credit_type, 0) + 1
        
        return {
            'top_contributors': top_contributors,
            'quality_distribution': quality_distribution,
            'high_quality_count': quality_distribution['high'],
            'medium_quality_count': quality_distribution['medium'],
            'low_quality_count': quality_distribution['low'],
            'credit_type_stats': credit_type_stats,
            'most_common_credit_type': max(credit_type_stats.items(), key=lambda x: x[1])[0] if credit_type_stats else None
        }
    
    @lru_cache(maxsize=128)
    def _get_quality_category(self, score: Optional[float]) -> str:
        """Retourne la catégorie de qualité - avec cache"""
        if not score:
            return 'low'
        if score >= 80:
            return 'high'
        elif score >= 60:
            return 'medium'
        else:
            return 'low'
    
    def _create_export_directory(self, artist_name: str, job_id: str) -> Path:
        """Crée le dossier d'export"""
        # Normalisation du nom d'artiste pour le système de fichiers
        safe_artist_name = "".join(c for c in artist_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_artist_name = safe_artist_name.replace(' ', '_')
        
        export_dir = self.config['exports_dir'] / f"{safe_artist_name}_{job_id}"
        export_dir.mkdir(parents=True, exist_ok=True)
        
        return export_dir
    
    async def _export_parallel_formats(self, export_data: Dict[str, Any],
                                     formats: List[ExportFormat],
                                     export_dir: Path,
                                     stats: ExportStats,
                                     progress_callback: Optional[callable] = None) -> List[Path]:
        """Exporte vers plusieurs formats en parallèle"""
        
        loop = asyncio.get_event_loop()
        
        # Créer les tâches d'export
        tasks = []
        for fmt in formats:
            task = loop.run_in_executor(
                None,
                self._export_single_format,
                export_data, fmt, export_dir, stats
            )
            tasks.append(task)
        
        # Exécuter en parallèle
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        file_paths = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"❌ Erreur export {formats[i].value}: {result}")
            else:
                file_paths.append(result)
                if progress_callback:
                    progress = ((i + 1) / len(formats)) * 90  # 90% de la progression
                    progress_callback("export", int(progress), 100)
        
        return file_paths
    
    async def _export_sequential_formats(self, export_data: Dict[str, Any],
                                       formats: List[ExportFormat],
                                       export_dir: Path,
                                       stats: ExportStats,
                                       progress_callback: Optional[callable] = None) -> List[Path]:
        """Exporte vers plusieurs formats de manière séquentielle"""
        
        file_paths = []
        
        for i, fmt in enumerate(formats):
            try:
                file_path = self._export_single_format(export_data, fmt, export_dir, stats)
                file_paths.append(file_path)
                
                if progress_callback:
                    progress = ((i + 1) / len(formats)) * 90
                    progress_callback("export", int(progress), 100)
                    
            except Exception as e:
                self.logger.error(f"❌ Erreur export {fmt.value}: {e}")
        
        return file_paths
    
    def _export_single_format(self, export_data: Dict[str, Any],
                            format_type: ExportFormat,
                            export_dir: Path,
                            stats: ExportStats) -> Path:
        """Exporte vers un format unique"""
        
        artist_name = export_data['metadata']['artist_name']
        safe_name = "".join(c for c in artist_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
        
        # Dispatch vers la méthode appropriée
        export_methods = {
            ExportFormat.JSON: self._export_json,
            ExportFormat.CSV: self._export_csv,
            ExportFormat.EXCEL: self._export_excel,
            ExportFormat.HTML: self._export_html,
            ExportFormat.XML: self._export_xml,
            ExportFormat.YAML: self._export_yaml
        }
        
        method = export_methods.get(format_type)
        if not method:
            raise ExportError(f"Format d'export non supporté: {format_type.value}")
        
        file_path = method(export_data, export_dir, safe_name)
        
        # Mise à jour des statistiques
        if file_path.exists():
            file_size = file_path.stat().st_size
            stats.total_file_size_bytes += file_size
        
        return file_path
    
    def _export_json(self, export_data: Dict[str, Any], export_dir: Path, safe_name: str) -> Path:
        """Export au format JSON"""
        file_path = export_dir / f"{safe_name}_export.json"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
        
        self.logger.info(f"✅ Export JSON: {file_path}")
        return file_path
    
    def _export_csv(self, export_data: Dict[str, Any], export_dir: Path, safe_name: str) -> Path:
        """Export au format CSV (multiple files)"""
        files_created = []
        
        # Export des morceaux
        tracks_file = export_dir / f"{safe_name}_tracks.csv"
        with open(tracks_file, 'w', newline='', encoding='utf-8') as f:
            if export_data['tracks']:
                writer = csv.DictWriter(f, fieldnames=export_data['tracks'][0].keys())
                writer.writeheader()
                writer.writerows(export_data['tracks'])
        files_created.append(tracks_file)
        
        # Export des crédits
        credits_file = export_dir / f"{safe_name}_credits.csv"
        with open(credits_file, 'w', newline='', encoding='utf-8') as f:
            if export_data['credits']:
                writer = csv.DictWriter(f, fieldnames=export_data['credits'][0].keys())
                writer.writeheader()
                writer.writerows(export_data['credits'])
        files_created.append(credits_file)
        
        # Export des albums
        albums_file = export_dir / f"{safe_name}_albums.csv"
        with open(albums_file, 'w', newline='', encoding='utf-8') as f:
            if export_data['albums']:
                writer = csv.DictWriter(f, fieldnames=export_data['albums'][0].keys())
                writer.writeheader()
                writer.writerows(export_data['albums'])
        files_created.append(albums_file)
        
        self.logger.info(f"✅ Export CSV: {len(files_created)} fichiers créés")
        return files_created[0]  # Retourner le fichier principal
    
    def _export_excel(self, export_data: Dict[str, Any], export_dir: Path, safe_name: str) -> Path:
        """Export au format Excel"""
        if not PANDAS_AVAILABLE or not OPENPYXL_AVAILABLE:
            raise ExportError("Pandas et openpyxl requis pour l'export Excel")
        
        file_path = export_dir / f"{safe_name}_export.xlsx"
        
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            # Feuille artiste
            artist_df = pd.DataFrame([export_data['artist']])
            artist_df.to_excel(writer, sheet_name='Artiste', index=False)
            
            # Feuille morceaux
            if export_data['tracks']:
                tracks_df = pd.DataFrame(export_data['tracks'])
                tracks_df.to_excel(writer, sheet_name='Morceaux', index=False)
            
            # Feuille crédits
            if export_data['credits']:
                credits_df = pd.DataFrame(export_data['credits'])
                credits_df.to_excel(writer, sheet_name='Crédits', index=False)
            
            # Feuille albums
            if export_data['albums']:
                albums_df = pd.DataFrame(export_data['albums'])
                albums_df.to_excel(writer, sheet_name='Albums', index=False)
            
            # Feuille statistiques
            stats_data = {
                'Métrique': ['Total morceaux', 'Total crédits', 'Total albums', 'Score qualité moyen'],
                'Valeur': [
                    len(export_data['tracks']),
                    len(export_data['credits']),
                    len(export_data['albums']),
                    export_data['metadata']['average_quality_score']
                ]
            }
            stats_df = pd.DataFrame(stats_data)
            stats_df.to_excel(writer, sheet_name='Statistiques', index=False)
        
        self.logger.info(f"✅ Export Excel: {file_path}")
        return file_path
    
    def _export_html(self, export_data: Dict[str, Any], export_dir: Path, safe_name: str) -> Path:
        """Export au format HTML avec template"""
        file_path = export_dir / f"{safe_name}_report.html"
        
        if JINJA2_AVAILABLE and 'html_report' in self._default_templates:
            # Utiliser le template Jinja2
            template = Template(self._default_templates['html_report'])
            html_content = template.render(**export_data)
        else:
            # Template HTML simple fallback
            html_content = self._generate_simple_html_report(export_data)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.logger.info(f"✅ Export HTML: {file_path}")
        return file_path
    
    def _export_xml(self, export_data: Dict[str, Any], export_dir: Path, safe_name: str) -> Path:
        """Export au format XML"""
        if not XML_AVAILABLE:
            raise ExportError("Module xml.etree.ElementTree requis pour l'export XML")
        
        file_path = export_dir / f"{safe_name}_export.xml"
        
        # Création de la structure XML
        root = ET.Element("music_data")
        root.set("artist", export_data['metadata']['artist_name'])
        root.set("export_date", export_data['metadata']['export_date'])
        
        # Artiste
        artist_elem = ET.SubElement(root, "artist")
        for key, value in export_data['artist'].items():
            if value is not None:
                elem = ET.SubElement(artist_elem, key)
                elem.text = str(value)
        
        # Morceaux
        tracks_elem = ET.SubElement(root, "tracks")
        for track in export_data['tracks']:
            track_elem = ET.SubElement(tracks_elem, "track")
            for key, value in track.items():
                if value is not None and key != 'metadata':
                    elem = ET.SubElement(track_elem, key)
                    elem.text = str(value)
        
        # Crédits
        credits_elem = ET.SubElement(root, "credits")
        for credit in export_data['credits']:
            credit_elem = ET.SubElement(credits_elem, "credit")
            for key, value in credit.items():
                if value is not None:
                    elem = ET.SubElement(credit_elem, key)
                    elem.text = str(value)
        
        # Sauvegarde
        tree = ET.ElementTree(root)
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
        
        self.logger.info(f"✅ Export XML: {file_path}")
        return file_path
    
    def _export_yaml(self, export_data: Dict[str, Any], export_dir: Path, safe_name: str) -> Path:
        """Export au format YAML"""
        file_path = export_dir / f"{safe_name}_export.yaml"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(export_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        self.logger.info(f"✅ Export YAML: {file_path}")
        return file_path
    
    def _generate_simple_html_report(self, export_data: Dict[str, Any]) -> str:
        """Génère un rapport HTML simple (fallback)"""
        artist_name = export_data['metadata']['artist_name']
        export_date = export_data['metadata']['export_date']
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{artist_name} - Rapport d'extraction</title>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #f4f4f4; padding: 20px; }}
        .stats {{ margin: 20px 0; }}
        .track {{ border-bottom: 1px solid #eee; padding: 10px 0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{artist_name}</h1>
        <p>Rapport généré le {export_date}</p>
    </div>
    
    <div class="stats">
        <h2>Statistiques</h2>
        <ul>
            <li>Morceaux: {len(export_data['tracks'])}</li>
            <li>Crédits: {len(export_data['credits'])}</li>
            <li>Albums: {len(export_data['albums'])}</li>
        </ul>
    </div>
    
    <div class="tracks">
        <h2>Morceaux</h2>
        """
        
        for track in export_data['tracks'][:50]:  # Limiter à 50 pour la performance
            html += f"""
        <div class="track">
            <h4>{track.get('title', 'Titre inconnu')}</h4>
            <p>Album: {track.get('album_name', 'N/A')}</p>
            <p>Durée: {track.get('duration_formatted', 'N/A')}</p>
        </div>
            """
        
        html += """
    </div>
</body>
</html>
        """
        
        return html
    
    async def _generate_summary_report(self, export_data: Dict[str, Any],
                                     export_dir: Path,
                                     stats: ExportStats) -> Path:
        """Génère un rapport de résumé"""
        file_path = export_dir / "RESUME.md"
        
        if JINJA2_AVAILABLE and 'summary_template' in self._default_templates:
            template = Template(self._default_templates['summary_template'])
            summary_content = template.render(
                **export_data,
                formats_generated=stats.formats_generated
            )
        else:
            # Fallback simple
            summary_content = f"""
# {export_data['metadata']['artist_name']} - Résumé d'extraction

**Date d'export:** {export_data['metadata']['export_date']}
**Formats générés:** {', '.join(stats.formats_generated)}

## Statistiques

- **Morceaux:** {len(export_data['tracks'])}
- **Crédits:** {len(export_data['credits'])}
- **Albums:** {len(export_data['albums'])}

---
*Généré par Music Data Extractor*
            """
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(summary_content)
        
        self.logger.info(f"✅ Résumé généré: {file_path}")
        return file_path
    
    async def _create_export_archive(self, file_paths: List[Path],
                                   export_dir: Path,
                                   artist_name: str) -> Path:
        """Crée une archive ZIP des fichiers exportés"""
        safe_name = "".join(c for c in artist_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
        archive_path = export_dir / f"{safe_name}_complete_export.zip"
        
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in file_paths:
                if file_path.exists():
                    # Utiliser seulement le nom du fichier dans l'archive
                    arcname = file_path.name
                    zipf.write(file_path, arcname)
        
        self.logger.info(f"✅ Archive créée: {archive_path} ({archive_path.stat().st_size / (1024*1024):.1f} MB)")
        return archive_path
    
    def _update_performance_stats(self, stats: ExportStats):
        """Met à jour les statistiques de performance globales"""
        self.performance_stats['total_exports'] += 1
        self.performance_stats['total_files_created'] += len(stats.files_created)
        self.performance_stats['total_size_generated_mb'] += stats.total_file_size_bytes / (1024 * 1024)
        
        # Moyenne mobile du temps d'export
        current_avg = self.performance_stats['average_export_time']
        total_count = self.performance_stats['total_exports']
        
        new_avg = ((current_avg * (total_count - 1)) + stats.export_time_seconds) / total_count
        self.performance_stats['average_export_time'] = new_avg
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de performance"""
        return {
            **self.performance_stats,
            'formats_available': {
                'json': True,
                'csv': True,
                'excel': PANDAS_AVAILABLE and OPENPYXL_AVAILABLE,
                'html': True,
                'xml': XML_AVAILABLE,
                'yaml': True
            },
            'template_features': {
                'jinja2_templates': JINJA2_AVAILABLE,
                'custom_templates': self.config['use_custom_templates']
            },
            'config': self.config,
            'active_jobs': len([j for j in self._export_jobs.values() if j.status == 'running']),
            'completed_jobs': len([j for j in self._export_jobs.values() if j.status == 'completed'])
        }
    
    def get_export_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retourne le statut d'un job d'export"""
        job = self._export_jobs.get(job_id)
        if not job:
            return None
        
        return {
            'job_id': job.job_id,
            'artist_name': job.artist_name,
            'status': job.status,
            'formats': [f.value for f in job.formats],
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'duration_seconds': job.duration_seconds,
            'file_paths': job.file_paths,
            'error_message': job.error_message
        }
    
    def list_export_jobs(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Liste tous les jobs d'export"""
        jobs = []
        for job in self._export_jobs.values():
            if status_filter and job.status != status_filter:
                continue
            jobs.append(self.get_export_job_status(job.job_id))
        
        return sorted(jobs, key=lambda x: x['created_at'], reverse=True)
    
    def cleanup_old_exports(self, days: Optional[int] = None) -> int:
        """Nettoie les anciens exports"""
        cleanup_days = days or self.config['auto_cleanup_days']
        if cleanup_days <= 0:
            return 0
        
        cutoff_date = datetime.now() - timedelta(days=cleanup_days)
        exports_dir = self.config['exports_dir']
        
        cleaned_count = 0
        
        try:
            for export_subdir in exports_dir.iterdir():
                if export_subdir.is_dir():
                    # Vérifier la date de création du dossier
                    creation_time = datetime.fromtimestamp(export_subdir.stat().st_ctime)
                    
                    if creation_time < cutoff_date:
                        # Supprimer le dossier et son contenu
                        import shutil
                        shutil.rmtree(export_subdir)
                        cleaned_count += 1
                        self.logger.info(f"🗑️ Dossier d'export nettoyé: {export_subdir.name}")
        
        except Exception as e:
            self.logger.error(f"❌ Erreur nettoyage exports: {e}")
        
        # Nettoyer aussi les jobs terminés anciens
        old_job_ids = [
            job_id for job_id, job in self._export_jobs.items()
            if job.completed_at and job.completed_at < cutoff_date
        ]
        
        for job_id in old_job_ids:
            del self._export_jobs[job_id]
        
        if cleaned_count > 0:
            self.logger.info(f"🧹 Nettoyage terminé: {cleaned_count} exports supprimés")
        
        return cleaned_count
    
    def reset_performance_stats(self):
        """Remet à zéro les statistiques de performance"""
        self.performance_stats = {
            'total_exports': 0,
            'total_files_created': 0,
            'total_size_generated_mb': 0.0,
            'average_export_time': 0.0
        }
        
        self._template_cache.clear()
        self._data_cache.clear()
        self._export_jobs.clear()
        
        self.logger.info("🔄 Statistiques d'export remises à zéro")