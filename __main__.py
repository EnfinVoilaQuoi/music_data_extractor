# __main__.py
"""
Music Data Extractor - Point d'entrée principal

Usage:
    python -m music_data_extractor --help
    python -m music_data_extractor extract "Nom Artiste"
    python -m music_data_extractor gui
    python -m music_data_extractor stats
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Optional

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import settings
from core.session_manager import get_session_manager
from core.database import Database
from steps.step1_discover import DiscoveryStep
from steps.step2_extract import ExtractionStep
from utils.export_utils import ExportManager, export_all_formats
from utils.logging_config import setup_logging
from models.enums import ExportFormat

class MusicDataExtractorCLI:
    """Interface en ligne de commande pour Music Data Extractor"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.session_manager = get_session_manager()
        self.database = Database()
        
    def extract_artist(self, artist_name: str, max_tracks: Optional[int] = None, 
                      export_format: Optional[str] = None) -> str:
        """
        Pipeline complet d'extraction pour un artiste.
        
        Args:
            artist_name: Nom de l'artiste
            max_tracks: Limite du nombre de morceaux
            export_format: Format d'export ('json', 'html', 'csv', 'all')
            
        Returns:
            ID de session créée
        """
        print(f"\n🎵 === EXTRACTION POUR {artist_name.upper()} ===")
        
        try:
            # Étape 1: Découverte
            print("\n📍 ÉTAPE 1: Découverte des morceaux...")
            discovery_step = DiscoveryStep(self.session_manager, self.database)
            tracks, discovery_stats = discovery_step.discover_artist_tracks(
                artist_name, max_tracks=max_tracks
            )
            
            if not tracks:
                print("❌ Aucun morceau trouvé pour cet artiste")
                return None
            
            print(f"✅ {len(tracks)} morceaux découverts")
            
            # Récupérer l'ID de session
            sessions = self.session_manager.get_active_sessions()
            current_session = None
            for session in sessions:
                if session.artist_name == artist_name:
                    current_session = session
                    break
            
            if not current_session:
                print("❌ Erreur: session non trouvée")
                return None
            
            # Étape 2: Extraction détaillée
            print(f"\n📍 ÉTAPE 2: Extraction détaillée des crédits...")
            extraction_step = ExtractionStep(self.session_manager, self.database)
            enriched_tracks, extraction_stats = extraction_step.extract_tracks_data(
                current_session.id
            )
            
            print(f"✅ {extraction_stats.successful_extractions} morceaux traités avec succès")
            print(f"   - {extraction_stats.tracks_with_credits} avec crédits")
            print(f"   - {extraction_stats.tracks_with_spotify_data} avec données Spotify")
            
            # Étape 3: Export
            if export_format:
                print(f"\n📍 ÉTAPE 3: Export en format {export_format}...")
                self._export_results(artist_name, enriched_tracks, export_format)
            
            # Finaliser la session
            self.session_manager.complete_session(
                current_session.id,
                {
                    'total_tracks': len(tracks),
                    'successful_extractions': extraction_stats.successful_extractions,
                    'credits_found': extraction_stats.tracks_with_credits
                }
            )
            
            print(f"\n🎉 EXTRACTION TERMINÉE AVEC SUCCÈS !")
            print(f"   Session ID: {current_session.id}")
            
            return current_session.id
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'extraction: {e}")
            print(f"❌ Erreur: {e}")
            return None
    
    def _export_results(self, artist_name: str, tracks: list, export_format: str):
        """Exporte les résultats dans le format demandé"""
        try:
            # Récupérer l'artiste
            artist = self.database.get_artist_by_name(artist_name)
            if not artist:
                print("⚠️ Artiste non trouvé pour l'export")
                return
            
            export_manager = ExportManager()
            
            if export_format.lower() == 'all':
                # Export dans tous les formats
                results = export_all_formats(artist, tracks, artist_name)
                print("📁 Fichiers générés:")
                for format_name, filepath in results.items():
                    if filepath:
                        print(f"   - {format_name.upper()}: {filepath}")
            else:
                # Export dans un format spécifique
                try:
                    format_enum = ExportFormat(export_format.lower())
                    filepath = export_manager.export_artist_data(
                        artist, tracks, format=format_enum
                    )
                    print(f"📁 Fichier généré: {filepath}")
                except ValueError:
                    print(f"⚠️ Format non supporté: {export_format}")
                    print(f"   Formats disponibles: {', '.join([f.value for f in ExportFormat])}")
        
        except Exception as e:
            print(f"⚠️ Erreur lors de l'export: {e}")
    
    def show_stats(self, artist_name: Optional[str] = None):
        """Affiche les statistiques"""
        print("\n📊 === STATISTIQUES ===")
        
        try:
            if artist_name:
                # Stats pour un artiste spécifique
                artist = self.database.get_artist_by_name(artist_name)
                if artist:
                    stats = self.database.get_stats(artist.id)
                    print(f"\n🎤 Artiste: {artist.name}")
                    print(f"   - Morceaux: {stats.get('total_tracks', 0)}")
                    print(f"   - Avec paroles: {stats.get('tracks_with_lyrics', 0)}")
                    print(f"   - Avec crédits: {stats.get('tracks_with_credits', 0)}")
                else:
                    print(f"❌ Artiste '{artist_name}' non trouvé")
            else:
                # Stats générales
                stats = self.database.get_stats()
                print(f"📈 Statistiques générales:")
                print(f"   - Artistes: {stats.get('total_artists', 0)}")
                print(f"   - Morceaux: {stats.get('total_tracks', 0)}")
                print(f"   - Crédits: {stats.get('total_credits', 0)}")
                
                # Sessions actives
                active_sessions = self.session_manager.get_active_sessions()
                print(f"   - Sessions actives: {len(active_sessions)}")
        
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des stats: {e}")
    
    def list_sessions(self):
        """Liste les sessions récentes"""
        print("\n📋 === SESSIONS RÉCENTES ===")
        
        try:
            sessions = self.session_manager.list_sessions()[:10]  # 10 plus récentes
            
            if not sessions:
                print("Aucune session trouvée")
                return
            
            for session in sessions:
                status_emoji = {
                    'completed': '✅',
                    'failed': '❌',
                    'in_progress': '⏳',
                    'paused': '⏸️'
                }.get(session.status.value, '❓')
                
                print(f"{status_emoji} {session.artist_name}")
                print(f"   ID: {session.id}")
                print(f"   Statut: {session.status.value}")
                print(f"   Morceaux: {session.tracks_processed}/{session.total_tracks_found}")
                if session.updated_at:
                    print(f"   Dernière MAJ: {session.updated_at.strftime('%d/%m/%Y %H:%M')}")
                print()
        
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des sessions: {e}")
    
    def resume_session(self, session_id: str):
        """Reprend une session interrompue"""
        print(f"\n⏯️ === REPRISE DE SESSION {session_id} ===")
        
        try:
            session = self.session_manager.get_session(session_id)
            if not session:
                print(f"❌ Session '{session_id}' non trouvée")
                return
            
            print(f"🎤 Artiste: {session.artist_name}")
            print(f"📊 Progression: {session.tracks_processed}/{session.total_tracks_found}")
            
            # Reprendre selon l'étape actuelle
            if 'discovery' in session.current_step.lower():
                print("🔄 Reprise de la découverte...")
                discovery_step = DiscoveryStep(self.session_manager, self.database)
                tracks, _ = discovery_step.resume_discovery(session_id)
            elif 'extraction' in session.current_step.lower():
                print("🔄 Reprise de l'extraction...")
                extraction_step = ExtractionStep(self.session_manager, self.database)
                tracks, _ = extraction_step.extract_tracks_data(session_id)
            else:
                print("✅ Session déjà terminée")
                return
            
            print("✅ Session reprise avec succès")
        
        except Exception as e:
            print(f"❌ Erreur lors de la reprise: {e}")

def main():
    """Fonction principale avec parsing des arguments"""
    parser = argparse.ArgumentParser(
        description="Music Data Extractor - Extraction de données musicales avec crédits complets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  python -m music_data_extractor extract "Nekfeu"
  python -m music_data_extractor extract "PNL" --max-tracks 50 --export html
  python -m music_data_extractor gui
  python -m music_data_extractor stats
  python -m music_data_extractor sessions
  python -m music_data_extractor resume session_123456
        """
    )
    
    # Commandes principales
    subparsers = parser.add_subparsers(dest='command', help='Commandes disponibles')
    
    # Commande extract
    extract_parser = subparsers.add_parser('extract', help='Extraire les données d\'un artiste')
    extract_parser.add_argument('artist', help='Nom de l\'artiste')
    extract_parser.add_argument('--max-tracks', type=int, help='Nombre maximum de morceaux')
    extract_parser.add_argument('--export', choices=['json', 'csv', 'html', 'excel', 'xml', 'all'], 
                               help='Format d\'export')
    
    # Commande GUI
    gui_parser = subparsers.add_parser('gui', help='Lancer l\'interface graphique')
    
    # Commande stats
    stats_parser = subparsers.add_parser('stats', help='Afficher les statistiques')
    stats_parser.add_argument('--artist', help='Statistiques pour un artiste spécifique')
    
    # Commande sessions
    sessions_parser = subparsers.add_parser('sessions', help='Lister les sessions')
    
    # Commande resume
    resume_parser = subparsers.add_parser('resume', help='Reprendre une session')
    resume_parser.add_argument('session_id', help='ID de la session à reprendre')
    
    # Options globales
    parser.add_argument('--debug', action='store_true', help='Mode debug')
    parser.add_argument('--headless', action='store_true', help='Mode sans interface (pour Selenium)')
    
    args = parser.parse_args()
    
    # Configuration du logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level=log_level)
    
    # Configuration Selenium si spécifiée
    if args.headless:
        settings.config['selenium']['headless'] = True
    
    # Initialisation de l'interface CLI
    cli = MusicDataExtractorCLI()
    
    # Exécution de la commande
    if args.command == 'extract':
        session_id = cli.extract_artist(
            args.artist, 
            max_tracks=args.max_tracks,
            export_format=args.export
        )
        
    elif args.command == 'gui':
        # Lancer l'interface graphique
        try:
            from gui.streamlit_app import run_streamlit_app
            print("🖥️ Lancement de l'interface graphique...")
            print("   L'interface va s'ouvrir dans votre navigateur")
            run_streamlit_app()
        except ImportError:
            print("❌ Interface graphique non disponible")
            print("   Installez Streamlit: pip install streamlit")
            print("   Ou utilisez la CLI: python -m music_data_extractor extract \"Artiste\"")
    
    elif args.command == 'stats':
        cli.show_stats(args.artist)
    
    elif args.command == 'sessions':
        cli.list_sessions()
    
    elif args.command == 'resume':
        cli.resume_session(args.session_id)
    
    else:
        # Aucune commande fournie - afficher l'aide et proposer le GUI
        parser.print_help()
        print("\n💡 Conseil: Pour une interface plus conviviale, essayez:")
        print("   python -m music_data_extractor gui")

if __name__ == '__main__':
    main()