# run_interface.py
"""
Script de lancement de l'interface Streamlit pour Music Data Extractor
"""

import os
import sys
import subprocess
from pathlib import Path

def setup_environment():
    """Configure l'environnement avant le lancement"""
    
    # Ajouter le répertoire du projet au PATH Python
    project_root = Path(__file__).parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # Vérifier les variables d'environnement essentielles
    required_env_vars = [
        'GENIUS_API_KEY',
        'SPOTIFY_CLIENT_ID', 
        'SPOTIFY_CLIENT_SECRET'
    ]
    
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("⚠️  Variables d'environnement manquantes:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nCertaines fonctionnalités seront limitées.")
        print("Consultez le README pour configurer les clés API.")
        print()
    
    # Créer les dossiers nécessaires
    folders_to_create = [
        'data',
        'data/cache', 
        'data/sessions',
        'data/exports',
        'logs'
    ]
    
    for folder in folders_to_create:
        folder_path = project_root / folder
        folder_path.mkdir(parents=True, exist_ok=True)
    
    print("✅ Environnement configuré")

def check_dependencies():
    """Vérifie que les dépendances sont installées"""
    required_packages = [
        'streamlit',
        'plotly', 
        'pandas',
        'requests',
        'selenium',
        'beautifulsoup4',
        'lxml'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Packages manquants:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\nInstallation...")
        
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install"
            ] + missing_packages)
            print("✅ Packages installés")
        except subprocess.CalledProcessError:
            print("❌ Erreur lors de l'installation des packages")
            print("Veuillez installer manuellement:")
            print(f"pip install {' '.join(missing_packages)}")
            return False
    
    return True

def main():
    """Lance l'interface Streamlit"""
    print("🎵 Music Data Extractor - Interface Streamlit")
    print("=" * 50)
    
    # Configuration de l'environnement
    setup_environment()
    
    # Vérification des dépendances
    if not check_dependencies():
        sys.exit(1)
    
    # Lancement de Streamlit
    print("🚀 Lancement de l'interface...")
    print("📍 L'interface sera disponible sur: http://localhost:8501")
    print("💡 Utilisez Ctrl+C pour arrêter l'interface")
    print()
    
    try:
        # Configuration Streamlit
        streamlit_config = [
            "streamlit", "run", "streamlit_app.py",
            "--server.port=8501",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
            "--server.fileWatcherType=none"  # Évite les problèmes avec certains systèmes
        ]
        
        subprocess.run(streamlit_config)
        
    except KeyboardInterrupt:
        print("\n👋 Interface arrêtée par l'utilisateur")
    except FileNotFoundError:
        print("❌ Streamlit n'est pas installé ou introuvable")
        print("Installation: pip install streamlit")
    except Exception as e:
        print(f"❌ Erreur lors du lancement: {e}")

if __name__ == "__main__":
    main()
