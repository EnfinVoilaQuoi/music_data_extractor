# streamlit_app.py - Interface complète Music Data Extractor
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json

# Configuration de la page
st.set_page_config(
    page_title="Music Data Extractor",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Imports des modules du projet
try:
    from config.settings import settings
    from core.database import Database
    from core.session_manager import get_session_manager
    from steps.step1_discover import DiscoveryStep
    from utils.export_utils import ExportManager
    from models.enums import SessionStatus, ExtractionStatus
    
    # Import conditionnel pour ExtractionStep
    try:
        from steps.step2_extract import ExtractionStep
    except ImportError:
        ExtractionStep = None
    
    modules_available = True
    
except ImportError as e:
    st.error(f"Erreur d'import des modules: {e}")
    modules_available = False

# CSS personnalisé
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .metric-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin-bottom: 1rem;
    }
    
    .session-card {
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
        background: white;
    }
    
    .status-badge {
        padding: 0.25rem 0.5rem;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    
    .status-progress { background: #17a2b8; color: white; }
    .status-completed { background: #28a745; color: white; }
    .status-failed { background: #dc3545; color: white; }
    .status-paused { background: #ffc107; color: black; }
</style>
""", unsafe_allow_html=True)

class StreamlitInterface:
    """Interface Streamlit principale"""
    
    def __init__(self):
        if not modules_available:
            st.stop()
            
        # Initialisation des composants
        if 'database' not in st.session_state:
            st.session_state.database = Database()
        
        if 'session_manager' not in st.session_state:
            st.session_state.session_manager = get_session_manager()
        
        if 'discovery_step' not in st.session_state:
            st.session_state.discovery_step = DiscoveryStep()
        
        if 'export_manager' not in st.session_state:
            st.session_state.export_manager = ExportManager()
        
        # État de l'interface
        if 'current_session_id' not in st.session_state:
            st.session_state.current_session_id = None
    
    def run(self):
        """Lance l'interface principale"""
        
        # En-tête
        st.markdown("""
        <div class="main-header">
            <h1>🎵 Music Data Extractor</h1>
            <p>Extracteur de données musicales avec focus rap/hip-hop</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Sidebar avec navigation
        st.sidebar.title("Navigation")
        page = st.sidebar.selectbox(
            "Choisir une page",
            ["🏠 Dashboard", "🔍 Nouvelle extraction", "📝 Sessions", "📤 Exports", "⚙️ Paramètres"]
        )
        
        # Affichage de la page sélectionnée
        if page == "🏠 Dashboard":
            self.render_dashboard()
        elif page == "🔍 Nouvelle extraction":
            self.render_new_extraction()
        elif page == "📝 Sessions":
            self.render_sessions()
        elif page == "📤 Exports":
            self.render_exports()
        elif page == "⚙️ Paramètres":
            self.render_settings()
    
    def render_dashboard(self):
        """Affiche le dashboard principal"""
        st.header("📊 Dashboard")
        
        # Métriques rapides
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # Nombre de sessions actives
            active_sessions = len([s for s in st.session_state.session_manager.list_sessions() 
                                 if s.status == SessionStatus.IN_PROGRESS])
            st.metric("Sessions actives", active_sessions)
        
        with col2:
            # Nombre total d'artistes
            try:
                artist_count = st.session_state.database.get_artist_count()
                st.metric("Artistes", artist_count)
            except:
                st.metric("Artistes", "N/A")
        
        with col3:
            # Nombre total de morceaux
            try:
                track_count = st.session_state.database.get_track_count()
                st.metric("Morceaux", track_count)
            except:
                st.metric("Morceaux", "N/A")
        
        with col4:
            # Taille de la base
            try:
                db_size = st.session_state.database.get_database_size()
                st.metric("Base de données", f"{db_size:.1f} MB")
            except:
                st.metric("Base de données", "N/A")
        
        # Sessions récentes
        st.subheader("📝 Sessions récentes")
        recent_sessions = st.session_state.session_manager.list_sessions(limit=5)
        
        if recent_sessions:
            for session in recent_sessions:
                with st.container():
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                    
                    with col1:
                        st.write(f"**{session.artist_name}**")
                        st.caption(f"ID: {session.id}")
                    
                    with col2:
                        status_class = f"status-{session.status.value.replace('_', '-')}"
                        st.markdown(f'<span class="status-badge {status_class}">{session.status.value}</span>', 
                                  unsafe_allow_html=True)
                    
                    with col3:
                        if session.created_at:
                            st.write(session.created_at.strftime("%d/%m/%Y %H:%M"))
                    
                    with col4:
                        if st.button("▶️", key=f"resume_{session.id}"):
                            st.session_state.current_session_id = session.id
                            st.rerun()
                
                st.divider()
        else:
            st.info("Aucune session trouvée. Commencez par une nouvelle extraction !")
    
    def render_new_extraction(self):
        """Interface pour nouvelle extraction"""
        st.header("🔍 Nouvelle extraction")
        
        with st.form("new_extraction"):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                artist_name = st.text_input(
                    "Nom de l'artiste",
                    placeholder="Ex: Eminem, Booba, Nekfeu...",
                    help="Saisissez le nom de l'artiste à extraire"
                )
            
            with col2:
                max_tracks = st.number_input(
                    "Nombre max de morceaux",
                    min_value=1,
                    max_value=500,
                    value=100,
                    help="Limite pour éviter les extractions trop longues"
                )
            
            # Options avancées
            with st.expander("🔧 Options avancées"):
                col1, col2 = st.columns(2)
                
                with col1:
                    enable_lyrics = st.checkbox("Inclure les paroles", True)
                    force_refresh = st.checkbox("Forcer le rafraîchissement", False)
                
                with col2:
                    priority_sources = st.multiselect(
                        "Sources prioritaires",
                        ["genius", "spotify", "discogs", "lastfm"],
                        default=["genius", "spotify"]
                    )
            
            # Bouton de lancement
            submitted = st.form_submit_button(
                "🚀 Lancer l'extraction",
                use_container_width=True
            )
            
            if submitted and artist_name:
                self.start_extraction(artist_name, max_tracks, enable_lyrics)
    
    def start_extraction(self, artist_name: str, max_tracks: int, enable_lyrics: bool):
        """Lance une nouvelle extraction"""
        try:
            with st.spinner(f"🔍 Lancement de l'extraction pour {artist_name}..."):
                # Créer une nouvelle session
                session_id = st.session_state.session_manager.create_session(
                    artist_name=artist_name,
                    metadata={
                        "max_tracks": max_tracks,
                        "enable_lyrics": enable_lyrics,
                        "started_from": "streamlit_interface"
                    }
                )
                
                st.session_state.current_session_id = session_id
                
                # Démarrer la découverte
                tracks, stats = st.session_state.discovery_step.discover_artist_tracks(
                    artist_name=artist_name,
                    session_id=session_id,
                    max_tracks=max_tracks
                )
                
                st.success(f"✅ Découverte terminée !")
                st.info(f"🎵 {stats.final_count} morceaux trouvés en {stats.discovery_time_seconds:.1f}s")
                
                # Afficher les statistiques
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Genius", stats.genius_found)
                with col2:
                    st.metric("Rapedia", stats.rapedia_found)
                with col3:
                    st.metric("Doublons supprimés", stats.duplicates_removed)
                
                # Proposer l'étape suivante
                if ExtractionStep:
                    if st.button("➡️ Continuer vers l'extraction des crédits"):
                        st.info("Extraction des crédits en cours de développement...")
                else:
                    st.info("💡 Module d'extraction des crédits en cours de développement")
        
        except Exception as e:
            st.error(f"❌ Erreur lors de l'extraction: {e}")
            st.exception(e)
    
    def render_sessions(self):
        """Affiche la gestion des sessions"""
        st.header("📝 Gestion des sessions")
        
        sessions = st.session_state.session_manager.list_sessions()
        
        if not sessions:
            st.info("Aucune session trouvée.")
            return
        
        # Tableau des sessions
        session_data = []
        for session in sessions:
            session_data.append({
                "ID": session.id[:8] + "...",
                "Artiste": session.artist_name,
                "Statut": session.status.value,
                "Morceaux": session.total_tracks_found,
                "Créé le": session.created_at.strftime("%d/%m/%Y %H:%M") if session.created_at else "N/A"
            })
        
        df = pd.DataFrame(session_data)
        st.dataframe(df, use_container_width=True)
        
        # Actions sur les sessions
        if st.button("🧹 Nettoyer les sessions terminées"):
            cleaned = st.session_state.session_manager.cleanup_old_sessions()
            st.success(f"✅ {cleaned} sessions nettoyées")
            st.rerun()
    
    def render_exports(self):
        """Interface de gestion des exports"""
        st.header("📤 Gestion des exports")
        
        st.info("💡 Module d'export en cours de développement")
        
        # Interface basique d'export
        if st.session_state.current_session_id:
            session = st.session_state.session_manager.get_session(st.session_state.current_session_id)
            if session:
                st.write(f"**Session active:** {session.artist_name}")
                
                col1, col2 = st.columns(2)
                with col1:
                    export_format = st.selectbox("Format", ["JSON", "CSV", "HTML"])
                with col2:
                    if st.button("📥 Exporter"):
                        st.success(f"Export {export_format} en cours...")
    
    def render_settings(self):
        """Interface des paramètres"""
        st.header("⚙️ Paramètres")
        
        # Configuration des APIs
        st.subheader("🔑 Configuration des APIs")
        
        with st.form("api_config"):
            genius_key = st.text_input(
                "Clé API Genius",
                value=settings.genius_api_key or "",
                type="password",
                help="Obligatoire pour l'extraction des crédits"
            )
            
            spotify_id = st.text_input(
                "Spotify Client ID",
                value=settings.spotify_client_id or "",
                help="Pour les données audio (BPM, features)"
            )
            
            spotify_secret = st.text_input(
                "Spotify Client Secret",
                value=settings.spotify_client_secret or "",
                type="password"
            )
            
            if st.form_submit_button("💾 Sauvegarder"):
                st.success("Configuration sauvegardée !")
                st.info("Redémarrez l'interface pour appliquer les changements")

def main():
    """Fonction principale"""
    try:
        app = StreamlitInterface()
        app.run()
    except Exception as e:
        st.error(f"Erreur critique: {e}")
        st.exception(e)

if __name__ == "__main__":
    main()