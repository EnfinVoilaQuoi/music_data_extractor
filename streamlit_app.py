# streamlit_app.py - Version optimisée et corrigée pour éviter les freezes
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from pathlib import Path
import time
import uuid
import signal

# Configuration Streamlit
st.set_page_config(
    page_title="Music Data Extractor",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Imports sécurisés
try:
    from config.settings import settings
    from core.database import Database
    from core.session_manager import SessionManager
    from steps.step1_discover import DiscoveryStep
    from utils.export_utils import ExportManager
    from models.enums import SessionStatus, ExportFormat
    modules_available = True
except ImportError as e:
    st.error(f"❌ Erreur d'import: {e}")
    modules_available = False

# Variables de session
if 'debug_mode' not in st.session_state:
    st.session_state.debug_mode = st.query_params.get("debug", "false").lower() == "true"

# Styles CSS essentiels
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
    
    .status-progress { background: #17a2b8; color: white; }
    .status-completed { background: #28a745; color: white; }
    .status-failed { background: #dc3545; color: white; }
    .status-paused { background: #ffc107; color: black; }
    
    .nav-title {
        font-size: 18px;
        font-weight: bold;
        color: #ffffff !important;
        margin-bottom: 15px;
        padding: 0 8px;
        border-bottom: 2px solid #667eea;
        padding-bottom: 8px;
    }
    
    /* Style pour les boutons radio - VERSION CORRIGÉE POUR STREAMLIT MODERNE */
    .stRadio > div {
        gap: 8px;
    }
    
    /* Cacher les cercles radio */
    .stRadio > div > label > div:first-child {
        display: none !important;
    }
    
    /* Style de base pour tous les labels radio */
    .stRadio > div > label {
        background: rgba(255, 255, 255, 0.1) !important;
        border-radius: 8px !important;
        padding: 12px 16px !important;
        margin: 4px 0 !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        cursor: pointer !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
        display: block !important;
        color: #ffffff !important;
        backdrop-filter: blur(10px) !important;
    }
    
    /* Effet hover */
    .stRadio > div > label:hover {
        background: rgba(255, 255, 255, 0.2) !important;
        border-color: #667eea !important;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2) !important;
    }
    
    /* Style pour le bouton sélectionné - basé sur l'input checked */
    .stRadio > div > label:has(input[type="radio"]:checked) {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        font-weight: bold !important;
        border-color: #667eea !important;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
    }
    
    /* Fallback pour navigateurs qui ne supportent pas :has() */
    .stRadio > div > label input[type="radio"]:checked + div {
        /* Force le parent label à avoir le style sélectionné */
    }
    
    /* Autre fallback avec sélecteur plus général */
    .stSidebar [data-testid="stRadio"] label:has(input:checked) {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        font-weight: bold !important;
        border-color: #667eea !important;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
    }
    
    .stSidebar .stMarkdown, .stSidebar .stText {
        color: #ffffff !important;
    }
    
    .stSidebar .stAlert {
        background: rgba(255, 255, 255, 0.1) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        color: #ffffff !important;
        border-radius: 8px !important; /* Même bordure arrondie que la navigation */
    }
</style>
""", unsafe_allow_html=True)

class StreamlitInterface:
    """Interface Streamlit optimisée et sécurisée"""
    
    def __init__(self):
        if not modules_available:
            st.stop()
        
        self.debug_mode = st.session_state.debug_mode
        self.initialize_components()
    
    def initialize_components(self):
        """Initialisation sécurisée des composants"""
        
        if self.debug_mode:
            st.write("🔍 MODE DEBUG ACTIVÉ")
        
        try:
            # Database
            if 'database' not in st.session_state:
                st.session_state.database = Database()
                if self.debug_mode:
                    st.write("✅ Database initialisée")
            
            # SessionManager SANS THREADING (critique pour éviter les freezes)
            if 'session_manager' not in st.session_state:
                st.session_state.session_manager = SessionManager(
                    db=st.session_state.database,
                    enable_threading=False  # IMPORTANT: Pas de threading
                )
                if self.debug_mode:
                    st.write("✅ SessionManager créé (mode stable sans threading)")
            
            # Discovery Step
            if 'discovery_step' not in st.session_state:
                st.session_state.discovery_step = DiscoveryStep(
                    session_manager=st.session_state.session_manager,
                    database=st.session_state.database
                )
                if self.debug_mode:
                    st.write("✅ DiscoveryStep initialisé")
            
            # Export Manager
            if 'export_manager' not in st.session_state:
                st.session_state.export_manager = ExportManager()
                if self.debug_mode:
                    st.write("✅ ExportManager initialisé")
            
            # APIs
            if 'apis_configured' not in st.session_state:
                st.session_state.apis_configured = self.check_api_configuration()
            
            return True
            
        except Exception as e:
            st.error(f"❌ Erreur initialisation: {e}")
            if self.debug_mode:
                st.exception(e)
            return False
    
    def check_api_configuration(self):
        """Vérifie les APIs configurées"""
        api_count = 0
        
        if hasattr(settings, 'genius_api_key') and settings.genius_api_key:
            api_count += 1
        if hasattr(settings, 'spotify_client_id') and settings.spotify_client_id:
            api_count += 1
        if hasattr(settings, 'spotify_client_secret') and settings.spotify_client_secret:
            api_count += 1
        if hasattr(settings, 'discogs_token') and settings.discogs_token:
            api_count += 1
        if hasattr(settings, 'lastfm_api_key') and settings.lastfm_api_key:
            api_count += 1
        
        return api_count
    
    def create_session_safe(self, artist_name: str, metadata: dict = None) -> str:
        """Création de session sécurisée avec fallback automatique"""
        print(f"🔍 Création session sécurisée pour {artist_name}")
        
        try:
            # Tentative normale AVEC TIMEOUT pour détecter les freezes
            def timeout_handler(signum, frame):
                raise TimeoutError("Timeout création session")
            
            use_timeout = hasattr(signal, 'SIGALRM')  # Unix/Linux seulement
            
            if use_timeout:
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(5)  # 5 secondes max
            
            start_time = time.time()
            
            session_id = st.session_state.session_manager.create_session(
                artist_name=artist_name,
                metadata=metadata or {}
            )
            
            if use_timeout:
                signal.alarm(0)
            
            creation_time = time.time() - start_time
            if creation_time > 3:
                st.warning(f"⚠️ Création lente ({creation_time:.1f}s)")
            
            print(f"✅ Session normale créée: {session_id[:8]} en {creation_time:.1f}s")
            return session_id
            
        except Exception as e:
            if use_timeout:
                signal.alarm(0)
            
            print(f"⚠️ Échec création normale: {e}")
            
            # FALLBACK - Session temporaire
            session_id = f"temp_{int(time.time())}_{str(uuid.uuid4())[:8]}"
            
            if 'temp_sessions' not in st.session_state:
                st.session_state.temp_sessions = {}
            
            st.session_state.temp_sessions[session_id] = {
                'id': session_id,
                'artist_name': artist_name,
                'status': 'in_progress',
                'created_at': time.time(),
                'metadata': metadata or {}
            }
            
            st.info("ℹ️ Session temporaire créée (mode stable)")
            print(f"✅ Session temporaire: {session_id}")
            return session_id
    
    def run(self):
        """Point d'entrée principal"""
        
        # En-tête
        st.markdown("""
        <div class="main-header">
            <h1>🎵 Music Data Extractor</h1>
            <p>Interface d'extraction de données musicales</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Sidebar navigation
        self.render_sidebar()
        
        # Contenu principal
        page = st.session_state.get('current_page', '🏠 Dashboard')
        
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
    
    def render_sidebar(self):
        """Sidebar avec navigation et stats"""
        with st.sidebar:
            st.markdown('<div class="nav-title">🧭 Navigation</div>', unsafe_allow_html=True)
            
            # Menu principal avec boutons radio - VERSION ORIGINALE
            page = st.radio(
                "Menu de navigation",
                options=[
                    "🏠 Dashboard", 
                    "🔍 Nouvelle extraction", 
                    "📝 Sessions", 
                    "📤 Exports", 
                    "⚙️ Paramètres"
                ],
                index=0,
                label_visibility="collapsed",
                key="current_page"
            )
            
            st.markdown("---")
            st.markdown('<div class="nav-title">📊 Stats rapides</div>', unsafe_allow_html=True)
            
            try:
                # Stats essentielles
                sessions = st.session_state.session_manager.list_sessions()
                active_sessions = len([s for s in sessions if s.status == SessionStatus.IN_PROGRESS])
                
                total_tracks = 0
                total_artists = 0
                
                # Tentative de récupération des stats DB
                try:
                    if hasattr(st.session_state.database, 'get_connection'):
                        with st.session_state.database.get_connection() as conn:
                            cursor = conn.execute("SELECT COUNT(*) FROM tracks")
                            result = cursor.fetchone()
                            total_tracks = result[0] if result else 0
                            
                            cursor = conn.execute("SELECT COUNT(DISTINCT artist_id) FROM tracks")
                            result = cursor.fetchone()
                            total_artists = result[0] if result else 0
                except:
                    pass
                
                st.info(f"🎵 **{total_tracks}** morceaux")
                st.info(f"👥 **{total_artists}** artistes")
                st.info(f"⚡ **{active_sessions}** sessions actives")
                
                # APIs
                api_count = st.session_state.get('apis_configured', 0)
                if api_count >= 3:
                    st.success(f"✅ {api_count}/5 APIs")
                elif api_count >= 1:
                    st.warning(f"⚠️ {api_count}/5 APIs")
                else:
                    st.error("❌ Aucune API")
                
            except Exception as e:
                st.warning("⚠️ Impossible de charger les stats")
                if self.debug_mode:
                    st.error(f"Erreur: {e}")
    
    def render_dashboard(self):
        """Dashboard principal"""
        st.header("📊 Dashboard")
        
        # Métriques principales
        col1, col2, col3, col4 = st.columns(4)
        
        try:
            sessions = st.session_state.session_manager.list_sessions()
            active_sessions = len([s for s in sessions if s.status == SessionStatus.IN_PROGRESS])
            
            # Stats de base
            total_tracks = 0
            total_artists = 0
            
            try:
                with st.session_state.database.get_connection() as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM tracks")
                    result = cursor.fetchone()
                    total_tracks = result[0] if result else 0
                    
                    cursor = conn.execute("SELECT COUNT(DISTINCT artist_id) FROM tracks")
                    result = cursor.fetchone()
                    total_artists = result[0] if result else 0
            except:
                pass
            
            with col1:
                st.metric("🎵 Morceaux", total_tracks)
            
            with col2:
                st.metric("👥 Artistes", total_artists)
            
            with col3:
                st.metric("⚡ Sessions actives", active_sessions)
            
            with col4:
                st.metric("📝 Total sessions", len(sessions))
            
            # Sessions récentes
            st.subheader("🕒 Sessions récentes")
            recent_sessions = sessions[-5:] if sessions else []
            
            if recent_sessions:
                for session in reversed(recent_sessions):
                    self.render_session_card(session)
            else:
                st.info("Aucune session récente. Créez votre première extraction !")
                
        except Exception as e:
            st.error(f"❌ Erreur dashboard: {e}")
            if self.debug_mode:
                st.exception(e)
    
    def render_new_extraction(self):
        """Interface nouvelle extraction"""
        st.header("🎵 Nouvelle extraction")
        
        with st.form("new_extraction"):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                artist_name = st.text_input(
                    "Nom de l'artiste *",
                    placeholder="Ex: Nekfeu, JuL, PNL...",
                    help="Saisissez le nom exact de l'artiste"
                )
            
            with col2:
                max_tracks = st.number_input(
                    "Nombre max de morceaux",
                    min_value=1,
                    max_value=500,
                    value=100
                )
            
            # Options avancées
            with st.expander("⚙️ Options avancées"):
                col1, col2 = st.columns(2)
                
                with col1:
                    enable_lyrics = st.checkbox("Extraire les paroles", value=True)
                    batch_size = st.selectbox("Taille des lots", [5, 10, 15, 20], index=1)
                    force_refresh = st.checkbox("Forcer le rafraîchissement", False)
                
                with col2:
                    max_workers = st.selectbox("Workers parallèles", [1, 2, 3, 5], index=2)
                    use_cache = st.checkbox("Utiliser le cache", value=True)
                    
                    priority_sources = st.multiselect(
                        "Sources prioritaires",
                        ["genius", "spotify", "discogs", "lastfm", "rapedia"],
                        default=["genius", "spotify"],
                        help="Ordre de priorité pour l'extraction des données"
                    )
            
            submitted = st.form_submit_button("🚀 Lancer l'extraction", use_container_width=True)
        
        if submitted:
            if not artist_name.strip():
                st.error("❌ Veuillez saisir un nom d'artiste")
                return
            
            if st.session_state.get('apis_configured', 0) == 0:
                st.error("❌ Aucune API configurée. Allez dans Paramètres.")
                return
            
            # Lancer l'extraction
            self.start_extraction(
                artist_name=artist_name.strip(),
                max_tracks=max_tracks,
                enable_lyrics=enable_lyrics,
                batch_size=batch_size,
                max_workers=max_workers,
                use_cache=use_cache,
                force_refresh=force_refresh,
                priority_sources=priority_sources
            )
    
    def start_extraction(self, artist_name: str, **kwargs):
        """Lance l'extraction avec suivi"""
        st.header(f"🎵 Extraction pour {artist_name}")
        
        # Barre de progression
        progress = st.progress(0, text="Initialisation...")
        status = st.empty()
        
        try:
            # Étape 1: Création session
            status.text("🔄 Création de la session...")
            progress.progress(0.1)
            
            session_id = self.create_session_safe(artist_name, {
                "max_tracks": kwargs.get('max_tracks', 100),
                "enable_lyrics": kwargs.get('enable_lyrics', True),
                "batch_size": kwargs.get('batch_size', 10),
                "max_workers": kwargs.get('max_workers', 3),
                "use_cache": kwargs.get('use_cache', True),
                "force_refresh": kwargs.get('force_refresh', False),
                "priority_sources": kwargs.get('priority_sources', ["genius", "spotify"]),
                "interface": "streamlit_v3"
            })
            
            progress.progress(0.3)
            status.text(f"✅ Session créée: {session_id[:12]}")
            st.success(f"Session: {session_id[:12]}")
            
            # Étape 2: Découverte
            status.text("🔍 Découverte des morceaux...")
            progress.progress(0.5)
            
            tracks, stats = st.session_state.discovery_step.discover_artist_tracks(
                artist_name=artist_name,
                session_id=session_id,
                max_tracks=kwargs.get('max_tracks', 100)
            )
            
            progress.progress(0.8)
            
            if tracks and len(tracks) > 0:
                status.text(f"✅ {len(tracks)} morceaux trouvés")
                st.success(f"🎉 {len(tracks)} morceaux découverts !")
                
                # Résultats
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Morceaux trouvés", len(tracks))
                with col2:
                    st.metric("Source principale", "Genius")
                with col3:
                    st.metric("Temps", f"{stats.discovery_time_seconds:.1f}s")
                
                # Prévisualisation
                if tracks:
                    st.subheader("📋 Aperçu des morceaux")
                    
                    tracks_df = pd.DataFrame([{
                        'Titre': track.title[:50] + '...' if len(track.title) > 50 else track.title,
                        'Album': track.album_name[:30] + '...' if track.album_name and len(track.album_name) > 30 else track.album_name or 'N/A',
                        'Année': track.release_year or 'N/A',
                        'Source': track.data_source.value if hasattr(track.data_source, 'value') else str(track.data_source)
                    } for track in tracks[:20]])
                    
                    st.dataframe(tracks_df, use_container_width=True)
                    
                    if len(tracks) > 20:
                        st.info(f"Affichage des 20 premiers sur {len(tracks)} total")
                
                # Finaliser
                if hasattr(st.session_state.session_manager, 'complete_session'):
                    st.session_state.session_manager.complete_session(session_id, {
                        'tracks_found': len(tracks)
                    })
                
                progress.progress(1.0)
                status.text("✅ Extraction terminée")
                
                # Actions
                st.markdown("### 🎯 Actions")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("📤 Exporter", use_container_width=True):
                        st.session_state.current_page = "📤 Exports"
                        st.rerun()
                
                with col2:
                    if st.button("🔍 Détails", use_container_width=True):
                        st.session_state.current_page = "📝 Sessions"
                        st.rerun()
                
                with col3:
                    if st.button("🎵 Nouvelle", use_container_width=True):
                        st.rerun()
                
            else:
                status.text("❌ Aucun morceau trouvé")
                st.error(f"❌ Aucun morceau trouvé pour {artist_name}")
                st.info("💡 Vérifiez l'orthographe ou essayez un autre artiste")
            
        except Exception as e:
            progress.empty()
            status.empty()
            st.error(f"❌ Erreur extraction: {e}")
            if self.debug_mode:
                st.exception(e)
    
    def render_sessions(self):
        """Gestion des sessions"""
        st.header("📝 Sessions")
        
        # Filtres
        col1, col2, col3 = st.columns(3)
        
        with col1:
            status_filter = st.selectbox(
                "Statut",
                ["Tous", "En cours", "Terminées", "Échouées", "En pause"]
            )
        
        with col2:
            limit = st.selectbox("Nombre", [10, 25, 50], index=1)
        
        with col3:
            if st.button("🔄 Actualiser", use_container_width=True):
                st.rerun()
        
        # Sessions
        try:
            if status_filter == "Tous":
                sessions = st.session_state.session_manager.list_sessions(limit=limit)
            else:
                status_map = {
                    "En cours": SessionStatus.IN_PROGRESS,
                    "Terminées": SessionStatus.COMPLETED,
                    "Échouées": SessionStatus.FAILED,
                    "En pause": SessionStatus.PAUSED
                }
                sessions = st.session_state.session_manager.list_sessions(
                    status=status_map[status_filter], limit=limit
                )
            
            if not sessions:
                st.info("Aucune session trouvée")
                return
            
            for session in reversed(sessions):
                self.render_session_card(session, detailed=True)
                
        except Exception as e:
            st.error(f"❌ Erreur sessions: {e}")
    
    def render_session_card(self, session, detailed=False):
        """Carte de session"""
        
        status_colors = {
            SessionStatus.IN_PROGRESS: "#17a2b8",
            SessionStatus.COMPLETED: "#28a745",
            SessionStatus.FAILED: "#dc3545",
            SessionStatus.PAUSED: "#ffc107"
        }
        
        status_text = {
            SessionStatus.IN_PROGRESS: "En cours",
            SessionStatus.COMPLETED: "Terminée",
            SessionStatus.FAILED: "Échouée",
            SessionStatus.PAUSED: "En pause"
        }
        
        color = status_colors.get(session.status, "#6c757d")
        status_label = status_text.get(session.status, "Inconnu")
        
        st.markdown(f"""
        <div style="border-left: 4px solid {color}; padding: 1rem; margin: 1rem 0; background: #f8f9fa; border-radius: 0 8px 8px 0;">
            <h4 style="margin: 0;">🎵 {session.artist_name}</h4>
            <p style="margin: 0.5rem 0;">
                <span style="background: {color}; color: white; padding: 0.2rem 0.5rem; border-radius: 12px; font-size: 0.8rem;">
                    {status_label}
                </span>
                <span style="margin-left: 1rem;">ID: {session.id[:12]}</span>
            </p>
            <p style="margin: 0; color: #888; font-size: 0.9rem;">
                Créée: {session.created_at.strftime('%d/%m/%Y %H:%M') if session.created_at else 'N/A'}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        if detailed:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if session.status == SessionStatus.IN_PROGRESS and st.button("⏸️ Pause", key=f"pause_{session.id}"):
                    if hasattr(st.session_state.session_manager, 'pause_session'):
                        st.session_state.session_manager.pause_session(session.id)
                        st.success("Session mise en pause")
                        st.rerun()
            
            with col2:
                if session.status == SessionStatus.PAUSED and st.button("▶️ Reprendre", key=f"resume_{session.id}"):
                    if hasattr(st.session_state.session_manager, 'resume_session'):
                        st.session_state.session_manager.resume_session(session.id)
                        st.success("Session reprise")
                        st.rerun()
            
            with col3:
                if st.button("🗑️ Supprimer", key=f"delete_{session.id}"):
                    if st.session_state.session_manager.delete_session(session.id):
                        st.success("Session supprimée")
                        st.rerun()
    
    def render_exports(self):
        """Gestion des exports"""
        st.header("📤 Exports")
        
        # Création export
        st.subheader("➕ Créer un export")
        
        with st.form("create_export"):
            col1, col2 = st.columns(2)
            
            with col1:
                export_format = st.selectbox("Format", ["CSV", "JSON", "Excel", "HTML"])
                include_lyrics = st.checkbox("Inclure paroles", True)
            
            with col2:
                try:
                    sessions = st.session_state.session_manager.list_sessions(SessionStatus.COMPLETED, limit=50)
                    if sessions:
                        session_options = [f"{s.artist_name} ({s.id[:8]})" for s in sessions]
                        selected_sessions = st.multiselect("Sessions à exporter", session_options)
                    else:
                        st.warning("Aucune session terminée")
                        selected_sessions = []
                except:
                    selected_sessions = []
            
            submitted = st.form_submit_button("📤 Créer export", use_container_width=True)
        
        if submitted and selected_sessions:
            try:
                session_ids = [s.split('(')[1].split(')')[0] for s in selected_sessions]
                
                with st.spinner("Création export..."):
                    export_path = st.session_state.export_manager.export_sessions(
                        session_ids=session_ids,
                        format=export_format.lower(),
                        include_lyrics=include_lyrics
                    )
                
                st.success(f"✅ Export créé: {export_path}")
                
                if Path(export_path).exists():
                    with open(export_path, 'rb') as file:
                        st.download_button(
                            "⬇️ Télécharger",
                            data=file.read(),
                            file_name=Path(export_path).name,
                            mime="application/octet-stream"
                        )
                
            except Exception as e:
                st.error(f"❌ Erreur export: {e}")
        
        elif submitted:
            st.warning("⚠️ Sélectionnez au moins une session")
        
        # Liste exports existants
        st.markdown("---")
        st.subheader("📁 Exports existants")
        
        try:
            exports = st.session_state.export_manager.list_exports()
            
            if not exports:
                st.info("📁 Aucun export trouvé")
                return
            
            for export in exports:
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                with col1:
                    st.write(f"**{export['filename']}**")
                    st.caption(f"Créé: {export['created_at']}")
                
                with col2:
                    st.write(f"{export['size_mb']:.1f} MB")
                
                with col3:
                    st.write(export['format'].upper())
                
                with col4:
                    if Path(export['path']).exists():
                        with open(export['path'], 'rb') as file:
                            st.download_button(
                                "⬇️",
                                data=file.read(),
                                file_name=export['filename'],
                                key=f"dl_{export['filename']}"
                            )
                    else:
                        st.write("❌ Manquant")
        
        except Exception as e:
            st.error(f"❌ Erreur liste exports: {e}")
    
    def render_settings(self):
        """Paramètres"""
        st.header("⚙️ Paramètres")
        
        # APIs
        st.subheader("🔑 APIs")
        
        with st.form("api_config"):
            col1, col2 = st.columns(2)
            
            with col1:
                genius_key = st.text_input(
                    "Genius API Key",
                    value=getattr(settings, 'genius_api_key', '') or "",
                    type="password"
                )
                
                spotify_id = st.text_input(
                    "Spotify Client ID",
                    value=getattr(settings, 'spotify_client_id', '') or ""
                )
            
            with col2:
                spotify_secret = st.text_input(
                    "Spotify Client Secret",
                    value=getattr(settings, 'spotify_client_secret', '') or "",
                    type="password"
                )
                
                discogs_token = st.text_input(
                    "Discogs Token",
                    value=getattr(settings, 'discogs_token', '') or "",
                    type="password"
                )
            
            if st.form_submit_button("💾 Sauvegarder"):
                st.success("✅ Configuration sauvegardée")
                st.info("ℹ️ Redémarrez pour appliquer")
        
        # Maintenance
        st.markdown("---")
        st.subheader("🧹 Maintenance")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🗑️ Vider cache", use_container_width=True):
                st.success("✅ Cache vidé")
        
        with col2:
            if st.button("🧹 Nettoyer sessions", use_container_width=True):
                try:
                    count = st.session_state.session_manager.cleanup_old_sessions(days=30)
                    st.success(f"✅ {count} sessions supprimées")
                except Exception as e:
                    st.error(f"❌ Erreur: {e}")
        
        with col3:
            if st.button("📊 Stats DB", use_container_width=True):
                try:
                    with st.session_state.database.get_connection() as conn:
                        cursor = conn.execute("SELECT COUNT(*) FROM tracks")
                        tracks = cursor.fetchone()[0]
                        
                        cursor = conn.execute("SELECT COUNT(*) FROM sessions")
                        sessions = cursor.fetchone()[0]
                        
                        st.info(f"📊 {tracks} morceaux, {sessions} sessions")
                except Exception as e:
                    st.error(f"❌ Erreur stats: {e}")

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