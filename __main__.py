# __main__.py - VERSION CORRIGÉE
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
            artist_name: Nom de l'artiste à extraire
            max_tracks: Nombre maximum de tracks à traiter
            export_format: Format d'export ('json', 'csv', 'html', 'all')
            
        Returns:
            ID de la session créée
        """
        # Import dynamique pour éviter les imports circulaires
        from steps.step1_discover import DiscoveryStep
        from steps.step2_extract import ExtractionStep
        
        self.logger.info(f"🎯 Début extraction pour: {artist_name}")
        
        # Créer une session
        session_id = self.session_manager.create_session(
            artist_name=artist_name,
            metadata={'cli_extraction': True, 'max_tracks': max_tracks}
        )
        
        try:
            # Étape 1: Découverte
            discovery_step = DiscoveryStep(self.session_manager, self.database)
            tracks, discovery_stats = discovery_step.discover_artist_tracks(
                artist_name, session_id, max_tracks
            )
            
            self.logger.info(f"📊 Découverte terminée: {discovery_stats.final_count} morceaux trouvés")
            
            if not tracks:
                self.logger.warning("❌ Aucun morceau trouvé")
                self.session_manager.fail_session(session_id, "Aucun morceau trouvé")
                return session_id
            
            # Étape 2: Extraction
            extraction_step = ExtractionStep(self.session_manager, self.database)
            extraction_results = extraction_step.extract_tracks_data(tracks, session_id)
            
            self.logger.info(f"🔍 Extraction terminée: {len(extraction_results)} morceaux traités")
            
            # Étape 3: Export
            if export_format:
                export_manager = ExportManager(self.database)
                artist = self.database.get_artist_by_name(artist_name)
                
                if artist:
                    if export_format.lower() == 'all':
                        files = export_all_formats(export_manager, artist)
                    else:
                        format_enum = ExportFormat(export_format.lower())
                        files = export_manager.export_artist_data(artist, [format_enum])
                    
                    self.logger.info(f"📤 Export terminé: {len(files)} fichiers créés")
                    for file_path in files.values():
                        self.logger.info(f"   📁 {file_path}")
            
            # Marquer comme terminé
            self.session_manager.complete_session(session_id, {
                'tracks_discovered': len(tracks),
                'tracks_extracted': len(extraction_results),
                'export_format': export_format
            })
            
            self.logger.info(f"✅ Extraction terminée avec succès pour {artist_name}")
            
        except Exception as e:
            self.logger.error(f"❌ Erreur lors de l'extraction: {e}")
            self.session_manager.fail_session(session_id, str(e))
            raise
        
        return session_id
    
    def show_stats(self, artist_name: Optional[str] = None):
        """Affiche les statistiques"""
        print("\n📈 === STATISTIQUES ===")
        
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
            sessions = self.session_manager.list_sessions(limit=10)  # 10 plus récentes
            
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
                
                print(f"{status_emoji} {session.artist_name} ({session.id[:8]}...)")
                print(f"   Status: {session.status.value}")
                if session.created_at:
                    print(f"   Créé le: {session.created_at.strftime('%d/%m/%Y %H:%M')}")
                print()
        
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des sessions: {e}")

def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(description="Music Data Extractor")
    
    subparsers = parser.add_subparsers(dest='command', help='Commandes disponibles')
    
    # Commande extract
    extract_parser = subparsers.add_parser('extract', help='Extraire les données d\'un artiste')
    extract_parser.add_argument('artist_name', help='Nom de l\'artiste')
    extract_parser.add_argument('--max-tracks', type=int, help='Nombre maximum de morceaux')
    extract_parser.add_argument('--export', choices=['json', 'csv', 'html', 'all'], 
                               help='Format d\'export des données')
    extract_parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                               default='INFO', help='Niveau de logging')
    
    # Commande GUI
    gui_parser = subparsers.add_parser('gui', help='Lancer l\'interface graphique')
    
    # Commande stats
    stats_parser = subparsers.add_parser('stats', help='Afficher les statistiques')
    stats_parser.add_argument('--artist', help='Artiste spécifique (optionnel)')
    
    # Commande sessions
    sessions_parser = subparsers.add_parser('sessions', help='Lister les sessions')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Configuration du logging
    if hasattr(args, 'log_level'):
        setup_logging(level=getattr(logging, args.log_level))
    else:
        setup_logging()
    
    cli = MusicDataExtractorCLI()
    
    if args.command == 'extract':
        try:
            session_id = cli.extract_artist(
                artist_name=args.artist_name,
                max_tracks=args.max_tracks,
                export_format=args.export
            )
            print(f"\n✅ Extraction terminée. Session ID: {session_id}")
        except Exception as e:
            print(f"\n❌ Erreur: {e}")
            sys.exit(1)
    
    elif args.command == 'gui':
        try:
            import streamlit.web.cli as stcli
            sys.argv = ["streamlit", "run", "streamlit_app.py"]
            stcli.main()
        except ImportError:
            print("❌ Streamlit n'est pas installé. Installez-le avec: pip install streamlit")
            sys.exit(1)
    
    elif args.command == 'stats':
        cli.show_stats(args.artist if hasattr(args, 'artist') else None)
    
    elif args.command == 'sessions':
        cli.list_sessions()

if __name__ == "__main__":
    main()