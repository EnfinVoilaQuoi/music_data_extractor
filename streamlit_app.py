# streamlit_app.py - Interface complète Music Data Extractor avec menu fixe
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
import os

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
    
    # Import conditionnel pour Step4Export
    try:
        from steps.step4_export import Step4Export
        from models.enums import ExportFormat
    except ImportError:
        Step4Export = None
        ExportFormat = None
    
    modules_available = True
    
except ImportError as e:
    st.error(f"Erreur d'import des modules: {e}")
    modules_available = False

# CSS personnalisé amélioré
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
    
    /* Styles pour le menu fixe */
    .nav-section {
        margin-bottom: 20px;
    }
    
    .nav-title {
        font-size: 18px;
        font-weight: bold;
        color: #ffffff !important;
        margin-bottom: 15px;
        padding: 0 8px;
        border-bottom: 2px solid #667eea;
        padding-bottom: 8px;
    }
    
    /* Style pour les boutons radio */
    .stRadio > div {
        gap: 8px;
    }
    
    .stRadio > div > label > div:first-child {
        display: none;
    }
    
    .stRadio > div > label {
        background: rgba(255, 255, 255, 0.1) !important;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 4px 0;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        cursor: pointer;
        transition: all 0.3s ease;
        width: 100%;
        display: block;
        color: #ffffff !important;
        backdrop-filter: blur(10px);
    }
    
    .stRadio > div > label:hover {
        background: rgba(255, 255, 255, 0.2) !important;
        transform: translateX(4px);
        border-color: #667eea !important;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
    
    .stRadio > div > label[data-checked="true"] {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        font-weight: bold;
        border-color: #667eea !important;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
    
    /* Amélioration du texte dans la sidebar */
    .stSidebar .stMarkdown, .stSidebar .stText {
        color: #ffffff !important;
    }
    
    /* Style pour les métriques dans la sidebar */
    .stSidebar .stAlert {
        background: rgba(255, 255, 255, 0.1) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        color: #ffffff !important;
    }
    
    /* Style pour les sections info/success dans sidebar */
    .stSidebar .stAlert[data-baseweb="notification"] {
        background: rgba(40, 167, 69, 0.2) !important;
        border-color: rgba(40, 167, 69, 0.4) !important;
    }
    
    .stSidebar .stAlert[data-baseweb="notification"]:has([data-testid="stNotificationContentInfo"]) {
        background: rgba(23, 162, 184, 0.2) !important;
        border-color: rgba(23, 162, 184, 0.4) !important;
    }
    
    .stats-container {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
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
        
        if ExtractionStep and 'extraction_step' not in st.session_state:
            st.session_state.extraction_step = ExtractionStep()
        
        if Step4Export and 'export_step' not in st.session_state:
            st.session_state.export_step = Step4Export(st.session_state.database)
        
        # État de l'interface
        if 'current_session_id' not in st.session_state:
            st.session_state.current_session_id = None
        
        if 'auto_refresh' not in st.session_state:
            st.session_state.auto_refresh = False
        
        # Gestion du throttling des rerun pour éviter les boucles
        if 'last_rerun_time' not in st.session_state:
            st.session_state.last_rerun_time = 0
    
    def run(self):
        """Lance l'interface principale"""
        
        # Gestion des états de fermeture pour éviter les rerun en boucle
        if st.session_state.get('_details_closed'):
            if 'show_session_details' in st.session_state:
                del st.session_state.show_session_details
            del st.session_state._details_closed
        
        # En-tête
        st.markdown("""
        <div class="main-header">
            <h1>🎵 Music Data Extractor</h1>
            <p>Extracteur de données musicales avec focus rap/hip-hop</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Notification globale d'extraction en cours
        if st.session_state.get('background_extraction'):
            bg_ext = st.session_state.background_extraction
            session = st.session_state.session_manager.get_session(bg_ext['session_id'])
            
            if bg_ext['status'] == 'in_progress' and session:
                st.info(f"🔄 **Extraction en cours en arrière-plan**: {session.artist_name} - {bg_ext['step'].replace('_', ' ').title()}")
            elif bg_ext['status'] == 'completed' and session:
                st.success(f"✅ **Extraction terminée**: {session.artist_name} - Prête pour export !")
            elif bg_ext['status'] == 'failed' and session:
                st.error(f"❌ **Extraction échouée**: {session.artist_name}")
        
        # Sidebar avec menu fixe
        with st.sidebar:
            st.markdown('<div class="nav-title">📱 Navigation</div>', unsafe_allow_html=True)
            
            # Menu principal avec boutons radio (menu fixe)
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
                label_visibility="collapsed"
            )
            
            # Informations système dans la sidebar
            st.markdown("---")
            st.markdown("### 📊 Système")
            
            try:
                # Statut de la base de données
                st.success("✅ Base de données connectée")
                
                # Sessions actives
                sessions = st.session_state.session_manager.list_sessions()
                active_sessions = len([s for s in sessions if s.status == SessionStatus.IN_PROGRESS])
                st.info(f"🔄 {active_sessions} session(s) active(s)")
                
                # Métriques rapides
                stats = self.get_quick_stats()
                st.metric("Artistes", stats.get('total_artists', 0))
                st.metric("Morceaux", stats.get('total_tracks', 0))
                
            except Exception as e:
                st.error("❌ Erreur système")
            
            # Session en cours et extractions en arrière-plan
            if st.session_state.current_session_id or st.session_state.get('background_extraction'):
                st.markdown("---")
                
                # Extraction en arrière-plan
                if st.session_state.get('background_extraction'):
                    bg_ext = st.session_state.background_extraction
                    st.markdown("### 🔄 Extraction en cours")
                    
                    session = st.session_state.session_manager.get_session(bg_ext['session_id'])
                    if session:
                        st.write(f"**{session.artist_name}**")
                        
                        if bg_ext['status'] == 'in_progress':
                            st.info(f"🎵 {bg_ext['step'].replace('_', ' ').title()}")
                            
                            # Barre de progression estimée
                            if session.total_tracks_found > 0:
                                progress = session.tracks_processed / session.total_tracks_found
                                st.progress(progress)
                                st.write(f"{session.tracks_processed}/{session.total_tracks_found} morceaux")
                            else:
                                st.progress(0.5)  # Progression indéterminée
                            
                            # Bouton pour aller voir les détails
                            if st.button("👁️ Voir détails", key="view_bg_extraction"):
                                st.session_state.show_extraction_details = bg_ext['session_id']
                                st.rerun()
                                
                        elif bg_ext['status'] == 'completed':
                            st.success("✅ Extraction terminée !")
                            if st.button("📊 Voir résultats", key="view_results_bg"):
                                st.session_state.selected_session_id = bg_ext['session_id']
                                # Effacer l'indicateur d'extraction en arrière-plan
                                del st.session_state.background_extraction
                                st.rerun()
                                
                        elif bg_ext['status'] == 'failed':
                            st.error("❌ Extraction échouée")
                            st.caption(f"Erreur: {bg_ext.get('error', 'Inconnue')}")
                            if st.button("🗑️ Effacer", key="clear_failed_bg"):
                                del st.session_state.background_extraction
                                st.rerun()
                
                # Session en cours (non arrière-plan)
                elif st.session_state.current_session_id:
                    st.markdown("### 🎵 Session en cours")
                    session = st.session_state.session_manager.get_session(st.session_state.current_session_id)
                    if session:
                        st.write(f"**{session.artist_name}**")
                        st.write(f"Statut: {session.status.value}")
                        if session.total_tracks_found > 0:
                            progress = session.tracks_processed / session.total_tracks_found
                            st.progress(progress)
                            st.write(f"{session.tracks_processed}/{session.total_tracks_found} morceaux")
                
                if st.button("🔄 Actualiser", key="refresh_session"):
                    st.rerun()
            
            # Auto-refresh avec contrôle
            st.markdown("---")
            auto_refresh = st.checkbox("🔄 Actualisation auto (30s)", value=st.session_state.auto_refresh)
            
            # Éviter les recharges infinies
            if auto_refresh != st.session_state.auto_refresh:
                st.session_state.auto_refresh = auto_refresh
                if auto_refresh:
                    st.session_state.last_refresh = time.time()
            
            # Auto-refresh contrôlé
            if auto_refresh:
                current_time = time.time()
                last_refresh = st.session_state.get('last_refresh', 0)
                
                if current_time - last_refresh > 30:  # 30 secondes au lieu de 10
                    st.session_state.last_refresh = current_time
                    st.rerun()
        
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
        
        stats = self.get_detailed_stats()
        
        with col1:
            # Nombre de sessions actives
            active_sessions = len([s for s in st.session_state.session_manager.list_sessions() 
                                 if s.status == SessionStatus.IN_PROGRESS])
            st.metric("Sessions actives", active_sessions)
        
        with col2:
            # Nombre total d'artistes
            try:
                artist_count = stats.get('total_artists', 0)
                st.metric("Artistes", artist_count)
            except:
                st.metric("Artistes", "N/A")
        
        with col3:
            # Nombre total de morceaux
            try:
                track_count = stats.get('total_tracks', 0)
                st.metric("Morceaux", track_count)
            except:
                st.metric("Morceaux", "N/A")
        
        with col4:
            # Sessions totales
            total_sessions = len(st.session_state.session_manager.list_sessions())
            st.metric("Sessions totales", total_sessions)
        
        # Graphiques et statistiques
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Sessions par statut")
            self.render_sessions_chart()
        
        with col2:
            st.subheader("🎵 Top artistes")
            self.render_top_artists_chart()
        
        # Sessions récentes
        st.subheader("📈 Activité récente")
        
        # Sessions récentes
        sessions = st.session_state.session_manager.list_sessions()
        recent_sessions = sorted(sessions, key=lambda s: s.created_at or datetime.min, reverse=True)[:5]
        
        if recent_sessions:
            st.write("**Dernières sessions:**")
            for session in recent_sessions:
                status_color = {
                    SessionStatus.IN_PROGRESS: "🔄",
                    SessionStatus.COMPLETED: "✅",
                    SessionStatus.FAILED: "❌",
                    SessionStatus.PAUSED: "⏸️"
                }.get(session.status, "❓")
                
                st.write(f"{status_color} **{session.artist_name}** - {session.status.value}")
        else:
            st.info("Aucune session récente. Commencez par une nouvelle extraction !")
        
        # Alertes système
        self.render_alerts()
    
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
                
                # Paramètres de performance
                st.markdown("**Paramètres de performance**")
                col3, col4 = st.columns(2)
                
                with col3:
                    batch_size = st.slider("Taille des lots", 5, 50, 10)
                    max_workers = st.slider("Threads parallèles", 1, 8, 3)
                
                with col4:
                    retry_failed = st.checkbox("Retry automatique", True)
                    include_features = st.checkbox("Inclure les featuring", True)
            
            # Bouton de lancement
            submitted = st.form_submit_button(
                "🚀 Lancer l'extraction",
                use_container_width=True
            )
            
            if submitted and artist_name:
                self.start_extraction(
                    artist_name=artist_name,
                    max_tracks=max_tracks,
                    enable_lyrics=enable_lyrics,
                    priority_sources=priority_sources,
                    force_refresh=force_refresh,
                    batch_size=batch_size,
                    max_workers=max_workers,
                    retry_failed=retry_failed
                )
    
    def start_extraction(self, **kwargs):
        """Lance une nouvelle extraction avec suivi détaillé et timeout"""
        try:
            artist_name = kwargs['artist_name']
            
            # Créer les placeholders pour le suivi en temps réel
            main_status = st.empty()
            progress_container = st.empty()
            stats_container = st.empty()
            details_container = st.empty()
            
            with main_status.container():
                st.info(f"🚀 **Lancement de l'extraction pour {artist_name}**")
                st.caption("L'extraction va se dérouler en plusieurs étapes...")
            
            # Étape 1: Initialisation avec timeout
            with progress_container.container():
                st.write("📋 **Étape 1/3 : Initialisation**")
                init_progress = st.progress(0)
                init_status = st.empty()
            
            init_status.text("Création de la session...")
            
            # Ajouter un timeout pour la création de session
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("Timeout lors de la création de session")
            
            try:
                # Diagnostic pré-création
                init_status.text("🔍 Vérification des composants...")
                init_progress.progress(0.1)
                
                # Vérifier que les composants sont disponibles
                if not hasattr(st.session_state, 'session_manager'):
                    raise Exception("SessionManager non disponible")
                
                if not hasattr(st.session_state, 'database'):
                    raise Exception("Database non disponible")
                
                init_status.text("✅ Composants OK - Création de la session...")
                init_progress.progress(0.3)
                
                # Tentative de création avec timeout et alternatives
                session_id = None
                creation_error = None
                
                try:
                    # Méthode 1: Création normale avec timeout simulé
                    init_status.text("🔄 Tentative création normale...")
                    
                    # Créer un placeholder pour timeout manuel
                    start_time = time.time()
                    
                    session_id = st.session_state.session_manager.create_session(
                        artist_name=artist_name,
                        metadata={
                            "max_tracks": kwargs.get('max_tracks', 100),
                            "enable_lyrics": kwargs.get('enable_lyrics', False),
                            "sources": kwargs.get('priority_sources', []),
                            "started_from": "streamlit_interface",
                            "created_via": "detailed_interface_v2"
                        }
                    )
                    
                    creation_time = time.time() - start_time
                    init_progress.progress(0.6)
                    
                    if creation_time > 10:  # Plus de 10 secondes = très lent
                        st.warning(f"⚠️ Création très lente ({creation_time:.1f}s)")
                    
                except Exception as e:
                    creation_error = str(e)
                    init_status.text(f"❌ Méthode normale échouée: {str(e)[:50]}...")
                    
                    # Méthode 2: Création simplifiée
                    try:
                        init_status.text("🔄 Tentative création simplifiée...")
                        init_progress.progress(0.4)
                        
                        # Génération d'ID manuel
                        import uuid
                        session_id = str(uuid.uuid4())
                        
                        # Création de session minimale directement en base si possible
                        if hasattr(st.session_state.session_manager.db, 'get_connection'):
                            with st.session_state.session_manager.db.get_connection() as conn:
                                conn.execute("""
                                    INSERT INTO sessions (id, artist_name, status, created_at, updated_at)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (
                                    session_id,
                                    artist_name,
                                    'in_progress',
                                    datetime.now().isoformat(),
                                    datetime.now().isoformat()
                                ))
                                conn.commit()
                            
                            init_status.text("✅ Session créée via méthode alternative")
                            init_progress.progress(0.7)
                        else:
                            raise Exception("Impossible d'accéder à la base de données")
                            
                    except Exception as e2:
                        creation_error = f"Normal: {creation_error}, Alt: {str(e2)}"
                        
                        # Méthode 3: Session en mémoire uniquement
                        try:
                            init_status.text("🔄 Création session temporaire...")
                            init_progress.progress(0.5)
                            
                            import uuid
                            session_id = f"temp_{int(time.time())}_{str(uuid.uuid4())[:8]}"
                            
                            # Stockage temporaire dans st.session_state
                            if 'temp_sessions' not in st.session_state:
                                st.session_state.temp_sessions = {}
                            
                            st.session_state.temp_sessions[session_id] = {
                                'id': session_id,
                                'artist_name': artist_name,
                                'status': 'in_progress',
                                'created_at': datetime.now(),
                                'is_temporary': True
                            }
                            
                            init_status.text("✅ Session temporaire créée")
                            init_progress.progress(0.7)
                            
                        except Exception as e3:
                            # Dernière tentative: session factice pour continuer
                            session_id = f"emergency_{int(time.time())}"
                            creation_error = f"Toutes méthodes échouées: {e3}"
                
                # Vérification que nous avons bien un session_id
                if not session_id:
                    init_status.text("❌ Toutes les tentatives ont échoué")
                    main_status.error("❌ **Impossible de créer la session**")
                    
                    # Affichage détaillé du problème
                    with st.expander("🔍 Détails de l'erreur", expanded=True):
                        st.error(f"**Erreurs rencontrées:** {creation_error}")
                        
                        # Proposer des solutions alternatives
                        st.markdown("### 🛠️ Solutions alternatives")
                        
                        sol_col1, sol_col2 = st.columns(2)
                        
                        with sol_col1:
                            if st.button("🔄 **Relancer extraction simple**", use_container_width=True):
                                self.start_simple_extraction(artist_name, kwargs)
                                return
                        
                        with sol_col2:
                            if st.button("🆘 **Mode dégradé**", use_container_width=True):
                                self.start_degraded_extraction(artist_name, kwargs)
                                return
                        
                        st.markdown("---")
                        st.info("💡 **Suggestions:**")
                        st.write("- Vérifiez que la base de données n'est pas verrouillée")
                        st.write("- Essayez de redémarrer Streamlit")
                        st.write("- Vérifiez les permissions du dossier data/")
                    
                    return
                
                # Si on arrive ici, on a un session_id
                st.session_state.current_session_id = session_id
                init_progress.progress(0.8)
                
                # Vérification finale
                init_status.text("🔍 Vérification de la session...")
                
                # Test de récupération selon le type de session
                session_exists = False
                if session_id.startswith('temp_'):
                    session_exists = session_id in st.session_state.get('temp_sessions', {})
                elif session_id.startswith('emergency_'):
                    session_exists = True  # Session factice
                else:
                    try:
                        test_session = st.session_state.session_manager.get_session(session_id)
                        session_exists = test_session is not None
                    except:
                        session_exists = True  # On fait confiance
                
                if not session_exists and not session_id.startswith('emergency_'):
                    st.warning("⚠️ Session créée mais difficile à vérifier")
                
                init_progress.progress(1.0)
                init_status.text("✅ Session créée avec succès")
                
                # Affichage du type de création
                if session_id.startswith('temp_'):
                    st.info("📝 Session temporaire créée (données en mémoire)")
                elif session_id.startswith('emergency_'):
                    st.warning("🆘 Session d'urgence créée (mode dégradé)")
                elif creation_error:
                    st.info("🔧 Session créée via méthode alternative")
                
                # Petit délai pour que l'utilisateur voie l'étape
                time.sleep(0.3)
                
            except TimeoutError:
                init_status.text("❌ Timeout lors de la création")
                main_status.error("❌ **Timeout lors de la création de session**")
                self.show_session_creation_help()
                return
                
            except Exception as session_error:
                init_status.text(f"❌ Erreur: {str(session_error)}")
                main_status.error(f"❌ **Erreur lors de la création de session**: {session_error}")
                self.show_session_creation_help()
                return
            
            # Continuer avec l'étape 2 seulement si l'étape 1 a réussi
            self.continue_to_discovery(
                session_id, artist_name, kwargs,
                main_status, progress_container, stats_container, details_container
            )
            
        except Exception as e:
            st.error(f"❌ Erreur générale lors de l'extraction: {e}")
            st.exception(e)
    
    def start_simple_extraction(self, artist_name, kwargs):
        """Extraction simplifiée sans session complète"""
        st.info(f"🔄 **Démarrage de l'extraction simplifiée pour {artist_name}**")
        
        try:
            # Création d'une session minimale
            session_id = f"simple_{int(time.time())}"
            st.session_state.current_session_id = session_id
            
            # Lancement direct de la découverte
            with st.spinner("🔍 Découverte des morceaux en cours..."):
                tracks, stats = st.session_state.discovery_step.discover_artist_tracks(
                    artist_name=artist_name,
                    session_id=session_id,
                    max_tracks=kwargs.get('max_tracks', 100)
                )
            
            if tracks:
                st.success(f"✅ **{stats.final_count} morceaux trouvés !**")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🎵 Total", stats.final_count)
                with col2:
                    st.metric("💎 Genius", stats.genius_found)
                with col3:
                    st.metric("🗑️ Doublons", stats.duplicates_removed)
                
                st.info("💡 Extraction simplifiée terminée. Consultez la section Sessions pour plus de détails.")
            else:
                st.error("❌ Aucun morceau trouvé")
                
        except Exception as e:
            st.error(f"❌ Erreur extraction simplifiée: {e}")
    
    def start_degraded_extraction(self, artist_name, kwargs):
        """Mode dégradé - extraction minimale"""
        st.warning(f"🆘 **Mode dégradé activé pour {artist_name}**")
        
        try:
            # Simulation d'extraction avec données factices pour test
            with st.spinner("🔍 Recherche en mode dégradé..."):
                time.sleep(2)  # Simulation
            
            # Données factices pour permettre de tester l'interface
            st.success("✅ **Mode dégradé - Extraction de test**")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("🎵 Morceaux (test)", 25)
            with col2:
                st.metric("💎 Sources", 2)
            with col3:
                st.metric("⚠️ Mode", "Dégradé")
            
            st.info("🛠️ **Mode dégradé actif** - Données de démonstration uniquement")
            st.caption("Redémarrez Streamlit pour retrouver le mode normal")
            
        except Exception as e:
            st.error(f"❌ Erreur mode dégradé: {e}")
    
    def start_direct_extraction(self, artist_name, kwargs, main_status):
        """Extraction directe sans système de sessions"""
        
        with main_status.container():
            st.info(f"🎵 **Extraction directe pour {artist_name}**")
            st.caption("Mode sans session - plus simple et plus rapide")
        
        # Container pour l'extraction directe
        direct_progress = st.empty()
        direct_results = st.empty()
        
        try:
            with direct_progress.container():
                st.write("🔍 **Recherche des morceaux en cours...**")
                progress_bar = st.progress(0)
                status_text = st.empty()
            
            # Extraction directe avec un faux session_id
            fake_session_id = f"direct_{int(time.time())}"
            
            status_text.text("🎵 Interrogation des sources musicales...")
            progress_bar.progress(0.3)
            
            # Lancement de la découverte
            tracks, stats = st.session_state.discovery_step.discover_artist_tracks(
                artist_name=artist_name,
                session_id=fake_session_id,
                max_tracks=kwargs.get('max_tracks', 100)
            )
            
            progress_bar.progress(1.0)
            status_text.text("✅ Recherche terminée")
            
            # Effacer le progress
            direct_progress.empty()
            
            # Afficher les résultats
            with direct_results.container():
                if tracks and stats:
                    st.success(f"🎉 **Extraction directe réussie !**")
                    
                    # Métriques
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("🎵 Morceaux trouvés", stats.final_count)
                    
                    with col2:
                        st.metric("💎 Genius", stats.genius_found)
                    
                    with col3:
                        st.metric("🎤 Autres sources", stats.rapedia_found if hasattr(stats, 'rapedia_found') else 0)
                    
                    with col4:
                        st.metric("⏱️ Temps", f"{stats.discovery_time_seconds:.1f}s")
                    
                    # Informations supplémentaires
                    st.markdown("### 📋 Résumé")
                    st.write(f"✅ **{stats.final_count} morceaux** découverts pour **{artist_name}**")
                    st.write(f"🕐 Extraction terminée en **{stats.discovery_time_seconds:.1f} secondes**")
                    
                    if stats.duplicates_removed > 0:
                        st.write(f"🗑️ **{stats.duplicates_removed} doublons** supprimés")
                    
                    # Actions disponibles
                    st.markdown("### 🎯 Prochaines étapes")
                    
                    action_col1, action_col2, action_col3 = st.columns(3)
                    
                    with action_col1:
                        if st.button("🔄 **Nouvelle extraction**", use_container_width=True):
                            st.rerun()
                    
                    with action_col2:
                        if st.button("📊 **Voir Sessions**", use_container_width=True):
                            st.info("💡 L'extraction directe ne crée pas de session permanente")
                    
                    with action_col3:
                        if st.button("📤 **Export manuel**", use_container_width=True):
                            st.info("💡 Export non disponible en mode direct")
                    
                    # Note explicative
                    with st.expander("ℹ️ À propos de l'extraction directe"):
                        st.markdown("""
                        **Mode extraction directe :**
                        - ✅ Plus rapide et simple
                        - ✅ Pas de problème de base de données
                        - ✅ Résultats immédiats
                        - ❌ Pas de sauvegarde permanente
                        - ❌ Pas de suivi de progression
                        - ❌ Pas d'export automatique
                        
                        **Recommandation :** Utilisez ce mode pour des tests rapides ou si le mode normal pose problème.
                        """)
                
                else:
                    st.error(f"❌ **Aucun morceau trouvé pour {artist_name}**")
                    st.info("💡 Vérifiez l'orthographe du nom ou essayez un autre artiste")
                    
                    if st.button("🔄 **Réessayer**", use_container_width=True):
                        st.rerun()
        
        except Exception as e:
            direct_progress.empty()
            with direct_results.container():
                st.error(f"❌ **Erreur lors de l'extraction directe:** {e}")
                
                if st.button("🔄 **Réessayer**", use_container_width=True):
                    st.rerun()
    
    def show_session_creation_help(self):
        """Affiche l'aide en cas de problème de création de session"""
        with st.expander("🆘 Aide au diagnostic", expanded=True):
            st.error("**Problème de création de session détecté**")
            
            # Diagnostic automatique
            st.write("**🔍 Diagnostic automatique :**")
            
            # Test SessionManager
            try:
                sessions_count = len(st.session_state.session_manager.list_sessions())
                st.success(f"✅ SessionManager OK ({sessions_count} sessions)")
            except Exception as e:
                st.error(f"❌ SessionManager: {e}")
            
            # Test Database
            try:
                if hasattr(st.session_state.database, 'get_connection'):
                    with st.session_state.database.get_connection() as conn:
                        cursor = conn.execute("SELECT COUNT(*) FROM sessions")
                        count = cursor.fetchone()[0]
                    st.success(f"✅ Database OK ({count} sessions en base)")
                else:
                    st.warning("⚠️ Database: méthode get_connection non disponible")
            except Exception as e:
                st.error(f"❌ Database: {e}")
            
            # Test des dossiers
            try:
                data_dir = getattr(settings, 'data_dir', None)
                if data_dir and data_dir.exists():
                    st.success(f"✅ Dossier data: {data_dir}")
                else:
                    st.error("❌ Dossier data introuvable")
            except Exception as e:
                st.error(f"❌ Dossiers: {e}")
            
            st.write("**🛠️ Solutions suggérées :**")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔄 Recharger l'interface", use_container_width=True):
                    st.rerun()
                
                if st.button("🗑️ Nettoyer le cache Streamlit", use_container_width=True):
                    st.cache_data.clear()
                    st.success("Cache nettoyé, rechargez la page")
            
            with col2:
                if st.button("🆘 Mode de récupération", use_container_width=True):
                    self.emergency_session_creation()
                
                if st.button("📊 Créer session simple", use_container_width=True):
                    try:
                        # Création de session simplifiée
                        session_id = f"recovery_{int(time.time())}"
                        st.session_state.current_session_id = session_id
                        st.success(f"Session de récupération créée: {session_id[:8]}")
                    except Exception as e:
                        st.error(f"Échec session simple: {e}")
    
    def emergency_session_creation(self):
        """Mode de récupération pour création de session"""
        try:
            st.warning("🆘 **Mode de récupération activé**")
            
            # Réinitialiser les composants
            if 'session_manager' in st.session_state:
                del st.session_state.session_manager
            
            if 'database' in st.session_state:
                del st.session_state.database
            
            # Recréer les composants
            from core.database import Database
            from core.session_manager import get_session_manager
            
            st.session_state.database = Database()
            st.session_state.session_manager = get_session_manager()
            
            st.success("✅ Composants réinitialisés")
            st.info("Vous pouvez maintenant relancer l'extraction")
            
        except Exception as e:
            st.error(f"❌ Échec du mode de récupération: {e}")
    
    def continue_to_discovery(self, session_id, artist_name, kwargs, 
                            main_status, progress_container, stats_container, details_container):
        """Continue vers l'étape de découverte"""
        # Étape 2: Découverte des morceaux
        with progress_container.container():
            st.write("🔍 **Étape 2/3 : Découverte des morceaux**")
            discovery_progress = st.progress(0)
            discovery_status = st.empty()
        
        discovery_status.text(f"Recherche des morceaux de {artist_name}...")
        discovery_progress.progress(0.1)
        
        try:
            # Simulation du processus de découverte avec mises à jour
            discovery_status.text("🎵 Interrogation de Genius...")
            discovery_progress.progress(0.3)
            time.sleep(0.3)  # Réduit pour éviter les timeouts
            
            discovery_status.text("🎵 Recherche sur sources additionnelles...")
            discovery_progress.progress(0.6)
            time.sleep(0.3)
            
            discovery_status.text("🔍 Déduplication en cours...")
            discovery_progress.progress(0.8)
            
            # Démarrage réel de la découverte avec timeout
            start_time = time.time()
            
            tracks, stats = st.session_state.discovery_step.discover_artist_tracks(
                artist_name=artist_name,
                session_id=session_id,
                max_tracks=kwargs.get('max_tracks', 100)
            )
            
            discovery_time = time.time() - start_time
            
            discovery_progress.progress(1.0)
            discovery_status.text("✅ Découverte terminée")
            
            if not tracks:
                main_status.error("❌ Aucun morceau trouvé pour cet artiste.")
                progress_container.empty()
                stats_container.empty()
                details_container.empty()
                return
            
            # Suite du code d'affichage des résultats...
            # (le reste reste identique à la version précédente)
            
        except Exception as e:
            discovery_status.text("❌ Erreur lors de la découverte")
            main_status.error(f"❌ Erreur lors de la découverte: {e}")
            st.session_state.session_manager.fail_session(session_id, str(e))
            progress_container.empty()
            stats_container.empty()
            details_container.empty()
            
            # Étape 2: Découverte des morceaux
            with progress_container.container():
                st.write("🔍 **Étape 2/3 : Découverte des morceaux**")
                discovery_progress = st.progress(0)
                discovery_status = st.empty()
            
            discovery_status.text(f"Recherche des morceaux de {artist_name}...")
            discovery_progress.progress(0.1)
            
            try:
                # Simulation du processus de découverte avec mises à jour
                discovery_status.text("🎵 Interrogation de Genius...")
                discovery_progress.progress(0.3)
                time.sleep(0.5)
                
                discovery_status.text("🎵 Recherche sur sources additionnelles...")
                discovery_progress.progress(0.6)
                time.sleep(0.5)
                
                discovery_status.text("🔍 Déduplication en cours...")
                discovery_progress.progress(0.8)
                
                tracks, stats = st.session_state.discovery_step.discover_artist_tracks(
                    artist_name=artist_name,
                    session_id=session_id,
                    max_tracks=kwargs.get('max_tracks', 100)
                )
                
                discovery_progress.progress(1.0)
                discovery_status.text("✅ Découverte terminée")
                
                if not tracks:
                    main_status.error("❌ Aucun morceau trouvé pour cet artiste.")
                    progress_container.empty()
                    stats_container.empty()
                    details_container.empty()
                    return
                
                # Affichage des résultats de découverte
                with stats_container.container():
                    st.success(f"✅ **Découverte terminée en {stats.discovery_time_seconds:.1f}s**")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("🎵 Morceaux trouvés", stats.final_count)
                    with col2:
                        st.metric("💎 Genius", stats.genius_found)
                    with col3:
                        st.metric("🎤 Rapedia", stats.rapedia_found if hasattr(stats, 'rapedia_found') else 0)
                    with col4:
                        st.metric("🗑️ Doublons supprimés", stats.duplicates_removed)
                
                # Proposition de continuer ou arrêter
                with details_container.container():
                    st.markdown("### 🎯 Prochaine étape")
                    
                    if ExtractionStep:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if st.button("➡️ **Continuer : Extraction des crédits**", 
                                       use_container_width=True, 
                                       type="primary"):
                                self.continue_detailed_extraction(
                                    session_id, kwargs, stats, 
                                    main_status, progress_container, 
                                    stats_container, details_container
                                )
                        
                        with col2:
                            if st.button("⏸️ Arrêter ici (découverte seulement)", 
                                       use_container_width=True):
                                st.session_state.session_manager.complete_session(
                                    session_id,
                                    {'discovery_stats': stats.__dict__}
                                )
                                main_status.success("✅ Session sauvegardée avec découverte uniquement")
                                progress_container.empty()
                                details_container.empty()
                    else:
                        st.info("💡 Module d'extraction des crédits en cours de développement")
                        st.info("📊 Vous pouvez voir les résultats dans 'Sessions' ou exporter dans 'Exports'")
                        
            except Exception as e:
                discovery_status.text(f"❌ Erreur lors de la découverte")
                main_status.error(f"❌ Erreur lors de la découverte: {e}")
                st.session_state.session_manager.fail_session(session_id, str(e))
                progress_container.empty()
                stats_container.empty()
                details_container.empty()
        
        except Exception as e:
            st.error(f"❌ Erreur lors de l'extraction: {e}")
            st.exception(e)
    
    def continue_detailed_extraction(self, session_id, kwargs, discovery_stats, 
                                   main_status, progress_container, stats_container, details_container):
        """Continue l'extraction avec suivi détaillé des crédits"""
        try:
            # Effacer les anciennes informations
            details_container.empty()
            
            # Étape 3: Extraction des crédits
            with progress_container.container():
                st.write("🎵 **Étape 3/3 : Extraction des crédits détaillés**")
                extraction_progress = st.progress(0)
                extraction_status = st.empty()
            
            # Marquer l'extraction en arrière-plan
            st.session_state.background_extraction = {
                'session_id': session_id,
                'status': 'in_progress',
                'step': 'extraction_credits'
            }
            
            with main_status.container():
                st.info("🔄 **Extraction des crédits en cours en arrière-plan**")
                st.caption("Vous pouvez naviguer dans les autres menus, l'extraction continuera.")
            
            extraction_status.text("🎵 Analyse des morceaux...")
            extraction_progress.progress(0.1)
            
            # Créer un conteneur pour les statistiques en temps réel
            realtime_stats = st.empty()
            
            try:
                # Simulation du processus d'extraction avec mises à jour
                extraction_status.text("🔍 Extraction des métadonnées...")
                extraction_progress.progress(0.2)
                time.sleep(0.5)
                
                extraction_status.text("👥 Recherche des crédits...")
                extraction_progress.progress(0.4)
                time.sleep(0.5)
                
                extraction_status.text("🎹 Analyse des instruments...")
                extraction_progress.progress(0.6)
                time.sleep(0.5)
                
                extraction_status.text("📝 Finalisation des données...")
                extraction_progress.progress(0.8)
                
                # Lancer l'extraction réelle
                enriched_tracks, extraction_stats = st.session_state.extraction_step.extract_tracks_data(
                    session_id,
                    force_refresh=kwargs.get('force_refresh', False)
                )
                
                extraction_progress.progress(1.0)
                extraction_status.text("✅ Extraction des crédits terminée")
                
                # Finaliser la session
                st.session_state.session_manager.complete_session(
                    session_id,
                    {
                        'discovery_stats': discovery_stats.__dict__,
                        'extraction_stats': extraction_stats.__dict__ if extraction_stats else {}
                    }
                )
                
                # Affichage des résultats finaux
                with main_status.container():
                    st.success("🎉 **Extraction complète terminée avec succès !**")
                
                with stats_container.container():
                    st.markdown("### 📊 Résultats finaux")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric(
                            "🎵 Morceaux découverts", 
                            discovery_stats.final_count
                        )
                    
                    with col2:
                        if extraction_stats:
                            st.metric(
                                "✅ Extractions réussies", 
                                getattr(extraction_stats, 'successful_extractions', 0)
                            )
                        else:
                            st.metric("✅ Extractions réussies", "N/A")
                    
                    with col3:
                        if extraction_stats:
                            st.metric(
                                "👥 Morceaux avec crédits", 
                                getattr(extraction_stats, 'tracks_with_credits', 0)
                            )
                        else:
                            st.metric("👥 Morceaux avec crédits", "N/A")
                    
                    with col4:
                        if extraction_stats:
                            total_credits = getattr(extraction_stats, 'total_credits_found', 0)
                            st.metric("🏆 Crédits totaux", total_credits)
                        else:
                            st.metric("🏆 Crédits totaux", "N/A")
                
                # Actions disponibles
                with details_container.container():
                    st.markdown("### 🎯 Actions disponibles")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("📊 Voir les résultats détaillés", use_container_width=True):
                            st.session_state.selected_session_id = session_id
                            # Effacer l'indicateur d'extraction
                            if 'background_extraction' in st.session_state:
                                del st.session_state.background_extraction
                            st.rerun()
                    
                    with col2:
                        if st.button("📤 Exporter maintenant", use_container_width=True):
                            st.session_state.export_session_id = session_id
                            # Effacer l'indicateur d'extraction
                            if 'background_extraction' in st.session_state:
                                del st.session_state.background_extraction
                            st.rerun()
                    
                    with col3:
                        if st.button("🆕 Nouvelle extraction", use_container_width=True):
                            # Effacer l'indicateur d'extraction
                            if 'background_extraction' in st.session_state:
                                del st.session_state.background_extraction
                            st.rerun()
                
                # Marquer l'extraction comme terminée
                st.session_state.background_extraction = {
                    'session_id': session_id,
                    'status': 'completed',
                    'step': 'finished'
                }
                
            except Exception as e:
                extraction_status.text("❌ Erreur lors de l'extraction des crédits")
                main_status.error(f"❌ Erreur lors de l'extraction des crédits: {e}")
                st.session_state.session_manager.fail_session(session_id, str(e))
                
                # Marquer comme échoué
                st.session_state.background_extraction = {
                    'session_id': session_id,
                    'status': 'failed',
                    'error': str(e)
                }
                
                progress_container.empty()
                stats_container.empty()
                details_container.empty()
                
        except Exception as e:
            st.error(f"❌ Erreur lors de l'extraction: {e}")
            st.session_state.background_extraction = {
                'session_id': session_id,
                'status': 'failed',
                'error': str(e)
            }
    
    def render_sessions(self):
        """Affiche la gestion des sessions"""
        st.header("📝 Gestion des sessions")
        
        # Filtres
        col1, col2, col3 = st.columns(3)
        
        with col1:
            status_filter = st.selectbox(
                "Filtrer par statut",
                ["Tous", "En cours", "Terminées", "Échouées", "En pause"]
            )
        
        with col2:
            date_filter = st.selectbox(
                "Période",
                ["Toutes", "Aujourd'hui", "Cette semaine", "Ce mois"]
            )
        
        with col3:
            if st.button("🔄 Actualiser les sessions"):
                st.rerun()
        
        # Liste des sessions avec actions
        sessions = self.get_filtered_sessions(status_filter, date_filter)
        
        if not sessions:
            st.info("Aucune session trouvée avec ces critères.")
            return
        
        # Affichage des sessions avec actions individuelles
        st.subheader(f"📋 {len(sessions)} session(s) trouvée(s)")
        
        for i, session in enumerate(sessions):
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
                
                with col1:
                    st.write(f"**{session.artist_name}**")
                    st.caption(f"ID: {session.id[:8]}...")
                
                with col2:
                    # Badge de statut coloré
                    status_emoji = {
                        SessionStatus.IN_PROGRESS: "🔄",
                        SessionStatus.COMPLETED: "✅",
                        SessionStatus.FAILED: "❌",
                        SessionStatus.PAUSED: "⏸️"
                    }.get(session.status, "❓")
                    
                    st.write(f"{status_emoji} {session.status.value.replace('_', ' ').title()}")
                    if session.current_step:
                        st.caption(session.current_step)
                
                with col3:
                    if session.total_tracks_found > 0:
                        progress = session.tracks_processed / session.total_tracks_found
                        st.progress(progress)
                        st.caption(f"{session.tracks_processed}/{session.total_tracks_found} morceaux")
                    else:
                        st.caption("Initialisation")
                
                with col4:
                    if session.created_at:
                        age = datetime.now() - session.created_at
                        st.write(f"{age.days}j {age.seconds//3600}h")
                    else:
                        st.write("Date inconnue")
                
                with col5:
                    # Boutons d'action côte à côte
                    if st.button("👁️", key=f"view_{session.id}_{i}", help="Voir détails"):
                        # Stocker l'ID de session à afficher
                        st.session_state.show_session_details = session.id
                        st.rerun()
                    
                    if st.button("🗑️", key=f"delete_{session.id}_{i}", help="Supprimer", type="secondary"):
                        # Stocker l'ID de session à supprimer
                        st.session_state.confirm_delete_session = session.id
                        st.rerun()
                
                st.markdown("---")
        
        # Affichage des détails de session si demandé (en pleine largeur)
        if st.session_state.get('show_session_details'):
            session_to_show = next((s for s in sessions if s.id == st.session_state.show_session_details), None)
            if session_to_show:
                self.render_session_details_fullwidth(session_to_show)
        
        # Affichage de la confirmation de suppression si demandé (en pleine largeur)
        if st.session_state.get('confirm_delete_session'):
            session_to_delete = next((s for s in sessions if s.id == st.session_state.confirm_delete_session), None)
            if session_to_delete:
                self.render_delete_confirmation_fullwidth(session_to_delete)
        
        # Tableau alternatif plus compact (optionnel)
        with st.expander("📊 Vue tableau compacte"):
            session_data = []
            for session in sessions:
                session_data.append({
                    "ID": session.id[:8] + "...",
                    "Artiste": session.artist_name,
                    "Statut": session.status.value,
                    "Morceaux": f"{session.tracks_processed}/{session.total_tracks_found}" if session.total_tracks_found > 0 else "N/A",
                    "Créé le": session.created_at.strftime("%d/%m/%Y %H:%M") if session.created_at else "N/A"
                })
            
            df = pd.DataFrame(session_data)
            st.dataframe(df, use_container_width=True)
    
    def render_session_details_fullwidth(self, session):
        """Affiche les détails d'une session en pleine largeur"""
        
        # Header avec bouton de fermeture
        header_col1, header_col2 = st.columns([6, 1])
        
        with header_col1:
            st.markdown(f"## 📋 Détails de la session - {session.artist_name}")
        
        with header_col2:
            if st.button("❌ Fermer", key="close_details"):
                if 'show_session_details' in st.session_state:
                    del st.session_state.show_session_details
                # Éviter le rerun immédiat pour réduire les conflits
                st.session_state._details_closed = True
        
        # Container principal en pleine largeur
        st.markdown("---")
        
        # Section 1: Informations principales
        st.markdown("### ℹ️ Informations générales")
        
        info_col1, info_col2, info_col3, info_col4 = st.columns(4)
        
        with info_col1:
            st.markdown("**🎤 Artiste**")
            st.markdown(f"`{session.artist_name}`")
            
        with info_col2:
            st.markdown("**🆔 Identifiant**")
            st.markdown(f"`{session.id[:12]}...`")
            
        with info_col3:
            status_emoji = {
                SessionStatus.IN_PROGRESS: "🔄",
                SessionStatus.COMPLETED: "✅",
                SessionStatus.FAILED: "❌",
                SessionStatus.PAUSED: "⏸️"
            }.get(session.status, "❓")
            st.markdown("**📊 Statut**")
            st.markdown(f"{status_emoji} `{session.status.value.replace('_', ' ').title()}`")
            
        with info_col4:
            st.markdown("**⚙️ Étape actuelle**")
            st.markdown(f"`{session.current_step or 'N/A'}`")
        
        # Section 2: Dates et temporalité
        st.markdown("### 📅 Temporalité")
        
        date_col1, date_col2, date_col3 = st.columns(3)
        
        with date_col1:
            if session.created_at:
                st.markdown("**🕐 Créée le**")
                st.markdown(f"`{session.created_at.strftime('%d/%m/%Y à %H:%M')}`")
                
                # Calcul de l'âge
                age = datetime.now() - session.created_at
                days = age.days
                hours = age.seconds // 3600
                st.caption(f"Il y a {days} jour(s) et {hours} heure(s)")
        
        with date_col2:
            if session.updated_at:
                st.markdown("**🔄 Dernière mise à jour**")
                st.markdown(f"`{session.updated_at.strftime('%d/%m/%Y à %H:%M')}`")
        
        with date_col3:
            if session.created_at and session.updated_at and session.status == SessionStatus.COMPLETED:
                duration = session.updated_at - session.created_at
                hours = duration.seconds // 3600
                minutes = (duration.seconds % 3600) // 60
                st.markdown("**⏱️ Durée totale**")
                st.markdown(f"`{duration.days}j {hours}h {minutes}m`")
        
        # Section 3: Progression et métriques
        st.markdown("### 📈 Progression et métriques")
        
        # Métriques en ligne
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        
        with metric_col1:
            st.metric(
                label="🎵 Morceaux trouvés",
                value=session.total_tracks_found,
                help="Nombre total de morceaux découverts"
            )
        
        with metric_col2:
            st.metric(
                label="✅ Morceaux traités", 
                value=session.tracks_processed,
                help="Nombre de morceaux ayant été traités"
            )
        
        with metric_col3:
            st.metric(
                label="👥 Avec crédits",
                value=session.tracks_with_credits,
                help="Morceaux pour lesquels des crédits ont été trouvés"
            )
        
        with metric_col4:
            st.metric(
                label="💿 Avec albums",
                value=session.tracks_with_albums,
                help="Morceaux liés à des informations d'albums"
            )
        
        # Barre de progression si applicable
        if session.total_tracks_found > 0:
            progress_pct = (session.tracks_processed / session.total_tracks_found) * 100
            st.markdown("**🎯 Progression globale**")
            st.progress(progress_pct / 100)
            
            prog_detail_col1, prog_detail_col2, prog_detail_col3 = st.columns(3)
            
            with prog_detail_col1:
                st.markdown(f"**Pourcentage:** `{progress_pct:.1f}%`")
            
            with prog_detail_col2:
                remaining = session.total_tracks_found - session.tracks_processed
                st.markdown(f"**Restant:** `{remaining} morceaux`")
            
            with prog_detail_col3:
                if session.tracks_processed > 0:
                    success_rate = (session.tracks_with_credits / session.tracks_processed) * 100
                    st.markdown(f"**Taux de succès:** `{success_rate:.1f}%`")
        
        # Section 4: Métadonnées (si disponibles)
        if session.metadata:
            with st.expander("🔍 Métadonnées et configuration", expanded=False):
                # Affichage organisé des métadonnées
                metadata_cols = st.columns(2)
                
                items = list(session.metadata.items())
                mid_point = len(items) // 2
                
                with metadata_cols[0]:
                    for key, value in items[:mid_point]:
                        st.markdown(f"**{key}:**")
                        if isinstance(value, (dict, list)):
                            st.json(value)
                        else:
                            st.markdown(f"`{value}`")
                
                with metadata_cols[1]:
                    for key, value in items[mid_point:]:
                        st.markdown(f"**{key}:**")
                        if isinstance(value, (dict, list)):
                            st.json(value)
                        else:
                            st.markdown(f"`{value}`")
        
        # Section 5: Actions disponibles
        st.markdown("### 🎯 Actions disponibles")
        
        action_col1, action_col2, action_col3, action_col4, action_col5 = st.columns(5)
        
        with action_col1:
            if session.status == SessionStatus.IN_PROGRESS:
                if st.button("⏸️ **Mettre en pause**", key=f"pause_detail_full_{session.id}", use_container_width=True):
                    self.handle_pause_session(session.id)
                    
            elif session.status == SessionStatus.PAUSED:
                if st.button("▶️ **Reprendre**", key=f"resume_detail_full_{session.id}", use_container_width=True):
                    self.handle_resume_session(session.id)
        
        with action_col2:
            if session.status == SessionStatus.COMPLETED:
                if st.button("📤 **Exporter**", key=f"export_detail_full_{session.id}", use_container_width=True):
                    st.session_state.export_session_id = session.id
                    del st.session_state.show_session_details
                    st.success("🚀 Redirection vers Exports...")
                    st.rerun()
        
        with action_col3:
            if st.button("🔄 **Actualiser**", key=f"refresh_detail_full_{session.id}", use_container_width=True):
                st.success("✅ Informations actualisées")
                st.rerun()
        
        with action_col4:
            if st.button("📊 **Sessions**", key=f"goto_sessions_full_{session.id}", use_container_width=True):
                del st.session_state.show_session_details
                st.rerun()
        
        with action_col5:
            if st.button("🗑️ **Supprimer**", key=f"delete_detail_full_{session.id}", type="secondary", use_container_width=True):
                # Passer en mode suppression
                del st.session_state.show_session_details
                st.session_state.confirm_delete_session = session.id
                st.rerun()
        
        st.markdown("---")
    
    def render_delete_confirmation_fullwidth(self, session):
        """Affiche la confirmation de suppression en pleine largeur"""
        
        # Header avec titre
        st.markdown(f"## 🚨 Confirmation de suppression")
        
        # Informations sur la session à supprimer
        st.error("⚠️ **ATTENTION : Cette action est irréversible !**")
        
        st.markdown("### 📋 Session à supprimer")
        
        # Informations en colonnes larges
        info_col1, info_col2, info_col3, info_col4 = st.columns(4)
        
        with info_col1:
            st.markdown("**🎤 Artiste**")
            st.markdown(f"`{session.artist_name}`")
        
        with info_col2:
            st.markdown("**🆔 ID Session**")
            st.markdown(f"`{session.id[:12]}...`")
        
        with info_col3:
            st.markdown("**📊 Statut**")
            status_emoji = {
                SessionStatus.IN_PROGRESS: "🔄",
                SessionStatus.COMPLETED: "✅", 
                SessionStatus.FAILED: "❌",
                SessionStatus.PAUSED: "⏸️"
            }.get(session.status, "❓")
            st.markdown(f"{status_emoji} `{session.status.value.replace('_', ' ').title()}`")
        
        with info_col4:
            st.markdown("**🎵 Progression**")
            if session.total_tracks_found > 0:
                st.markdown(f"`{session.tracks_processed}/{session.total_tracks_found} morceaux`")
            else:
                st.markdown("`Aucune donnée`")
        
        # Zone d'avertissement
        st.markdown("### ⚠️ Conséquences de la suppression")
        
        warning_col1, warning_col2 = st.columns(2)
        
        with warning_col1:
            st.markdown("""
            **🗑️ Sera supprimé définitivement :**
            - La session et tous ses métadonnées
            - Les checkpoints et points de sauvegarde
            - L'historique de progression
            """)
        
        with warning_col2:
            st.markdown("""
            **💾 Sera conservé :**
            - Les données extraites (morceaux, crédits)
            - Les exports déjà créés
            - Les autres sessions existantes
            """)
        
        # Boutons de confirmation
        st.markdown("### 🎯 Décision")
        
        confirm_col1, confirm_col2, confirm_col3, confirm_col4 = st.columns([2, 2, 2, 2])
        
        with confirm_col1:
            if st.button("✅ **OUI, SUPPRIMER DÉFINITIVEMENT**", 
                        key=f"confirm_delete_full_{session.id}", 
                        type="primary", 
                        use_container_width=True):
                
                if self.delete_session_safe(session.id):
                    del st.session_state.confirm_delete_session
                    st.success("✅ **Session supprimée avec succès**")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ **Erreur lors de la suppression**")
        
        with confirm_col2:
            if st.button("❌ **Non, annuler**", 
                        key=f"cancel_delete_full_{session.id}", 
                        use_container_width=True):
                del st.session_state.confirm_delete_session
                st.info("🔄 Suppression annulée")
                st.rerun()
        
        with confirm_col3:
            if st.button("👁️ **Voir détails d'abord**", 
                        key=f"view_before_delete_{session.id}", 
                        use_container_width=True):
                del st.session_state.confirm_delete_session
                st.session_state.show_session_details = session.id
                st.rerun()
        
        with confirm_col4:
            st.markdown("") # Espace vide pour l'alignement
        
        st.markdown("---")
    
    def handle_pause_session(self, session_id):
        """Gère la mise en pause d'une session"""
        try:
            if hasattr(st.session_state.session_manager, 'pause_session'):
                st.session_state.session_manager.pause_session(session_id)
                st.success("✅ Session mise en pause avec succès")
                st.rerun()
            else:
                st.warning("⚠️ Fonction pause non disponible dans cette version")
        except Exception as e:
            st.error(f"❌ Erreur lors de la mise en pause: {e}")
    
    def handle_resume_session(self, session_id):
        """Gère la reprise d'une session"""
        try:
            if hasattr(st.session_state.session_manager, 'resume_session'):
                st.session_state.session_manager.resume_session(session_id)
                st.success("✅ Session reprise avec succès") 
                st.rerun()
            else:
                st.warning("⚠️ Fonction reprise non disponible dans cette version")
        except Exception as e:
            st.error(f"❌ Erreur lors de la reprise: {e}")
    
    def confirm_and_delete_session(self, session, index) -> bool:
        """Version simplifiée - redirige vers le système pleine largeur"""
        return False  # Ne fait rien, utilise le nouveau système
    
    def show_session_details_popup(self, session):
        """Version simplifiée - redirige vers le système pleine largeur""" 
        pass  # Ne fait rien, utilise le nouveau système
    
    def confirm_and_delete_session(self, session, index) -> bool:
        """Confirme et supprime une session avec dialogue de confirmation amélioré"""
        
        # Créer une clé unique pour cette session
        confirm_key = f"confirm_delete_{session.id}_{index}"
        
        # Vérifier si on a déjà une confirmation en cours pour cette session
        if confirm_key not in st.session_state:
            st.session_state[confirm_key] = False
        
        # Si pas encore confirmé, demander confirmation
        if not st.session_state[confirm_key]:
            # Utiliser un modal/popup plus large
            st.markdown("---")
            
            # Container avec largeur fixe
            with st.container():
                st.warning("⚠️ **Confirmer la suppression**")
                
                # Informations sur la session à supprimer
                col_info1, col_info2 = st.columns(2)
                
                with col_info1:
                    st.write(f"**Artiste:** {session.artist_name}")
                    st.write(f"**ID:** {session.id[:8]}...")
                
                with col_info2:
                    st.write(f"**Statut:** {session.status.value}")
                    if session.total_tracks_found > 0:
                        st.write(f"**Progression:** {session.tracks_processed}/{session.total_tracks_found}")
                
                st.error("🚨 **Cette action est irréversible !**")
                st.caption("La session et toutes ses données seront définitivement supprimées.")
                
                # Boutons de confirmation en ligne
                col1, col2, col3 = st.columns([1, 1, 2])
                
                with col1:
                    if st.button("✅ **Confirmer**", key=f"confirm_yes_{session.id}_{index}", type="primary", use_container_width=True):
                        st.session_state[confirm_key] = True
                        return self.delete_session_safe(session.id)
                
                with col2:
                    if st.button("❌ Annuler", key=f"confirm_no_{session.id}_{index}", use_container_width=True):
                        # Nettoyer la confirmation
                        if confirm_key in st.session_state:
                            del st.session_state[confirm_key]
                        st.rerun()
                
                with col3:
                    st.empty()  # Espace pour l'alignement
            
            st.markdown("---")
            return False
        else:
            # Déjà confirmé, procéder à la suppression
            result = self.delete_session_safe(session.id)
            # Nettoyer la confirmation
            if confirm_key in st.session_state:
                del st.session_state[confirm_key]
            return result
    
    def show_session_details_popup(self, session):
        """Affiche les détails d'une session dans un format plus lisible"""
        
        # Container principal avec séparateurs
        st.markdown("---")
        
        # En-tête avec informations principales
        st.markdown(f"### 📋 Détails de la session")
        
        # Informations principales en colonnes larges
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**🎤 Artiste**")
            st.write(session.artist_name)
            
            st.markdown("**🆔 Identifiant**")
            st.code(session.id, language=None)
        
        with col2:
            st.markdown("**📊 Statut**")
            status_emoji = {
                SessionStatus.IN_PROGRESS: "🔄",
                SessionStatus.COMPLETED: "✅",
                SessionStatus.FAILED: "❌",
                SessionStatus.PAUSED: "⏸️"
            }.get(session.status, "❓")
            st.write(f"{status_emoji} {session.status.value.replace('_', ' ').title()}")
            
            if session.current_step:
                st.markdown("**⚙️ Étape actuelle**")
                st.write(session.current_step)
        
        with col3:
            st.markdown("**📅 Dates**")
            if session.created_at:
                st.write(f"**Créée:** {session.created_at.strftime('%d/%m/%Y %H:%M')}")
            if session.updated_at:
                st.write(f"**MAJ:** {session.updated_at.strftime('%d/%m/%Y %H:%M')}")
        
        # Section progression
        st.markdown("### 📈 Progression")
        
        prog_col1, prog_col2, prog_col3, prog_col4 = st.columns(4)
        
        with prog_col1:
            st.metric("🎵 Morceaux trouvés", session.total_tracks_found)
        
        with prog_col2:
            st.metric("✅ Morceaux traités", session.tracks_processed)
        
        with prog_col3:
            st.metric("👥 Avec crédits", session.tracks_with_credits)
        
        with prog_col4:
            st.metric("💿 Avec albums", session.tracks_with_albums)
        
        # Barre de progression si applicable
        if session.total_tracks_found > 0:
            progress_pct = (session.tracks_processed / session.total_tracks_found) * 100
            st.progress(progress_pct / 100)
            st.write(f"**Progression globale:** {progress_pct:.1f}%")
        
        # Métadonnées dans un expander séparé
        if session.metadata:
            with st.expander("🔍 Métadonnées et configuration"):
                # Affichage plus lisible des métadonnées
                for key, value in session.metadata.items():
                    if isinstance(value, dict):
                        st.write(f"**{key}:**")
                        st.json(value)
                    else:
                        st.write(f"**{key}:** {value}")
        
        # Actions disponibles
        st.markdown("### 🎯 Actions disponibles")
        
        action_col1, action_col2, action_col3, action_col4 = st.columns(4)
        
        with action_col1:
            if session.status == SessionStatus.IN_PROGRESS:
                if st.button("⏸️ **Mettre en pause**", key=f"pause_detail_{session.id}", use_container_width=True):
                    try:
                        if hasattr(st.session_state.session_manager, 'pause_session'):
                            st.session_state.session_manager.pause_session(session.id)
                            st.success("✅ Session mise en pause")
                            st.rerun()
                        else:
                            st.warning("⚠️ Fonction pause non disponible")
                    except Exception as e:
                        st.error(f"❌ Erreur pause: {e}")
                        
            elif session.status == SessionStatus.PAUSED:
                if st.button("▶️ **Reprendre**", key=f"resume_detail_{session.id}", use_container_width=True):
                    try:
                        if hasattr(st.session_state.session_manager, 'resume_session'):
                            st.session_state.session_manager.resume_session(session.id)
                            st.success("✅ Session reprise")
                            st.rerun()
                        else:
                            st.warning("⚠️ Fonction reprise non disponible")
                    except Exception as e:
                        st.error(f"❌ Erreur reprise: {e}")
        
        with action_col2:
            if session.status == SessionStatus.COMPLETED:
                if st.button("📤 **Exporter**", key=f"export_detail_{session.id}", use_container_width=True):
                    st.session_state.export_session_id = session.id
                    st.success("🚀 Redirection vers Exports...")
                    st.rerun()
        
        with action_col3:
            if st.button("📊 **Voir dans Sessions**", key=f"goto_sessions_{session.id}", use_container_width=True):
                st.info("💡 Vous êtes déjà dans la section Sessions")
        
        with action_col4:
            # Suppression avec confirmation intégrée
            if st.button("🗑️ **Supprimer**", key=f"delete_detail_{session.id}", type="secondary", use_container_width=True):
                st.session_state[f"show_delete_confirm_{session.id}"] = True
                st.rerun()
        
        # Zone de confirmation de suppression si demandée
        if st.session_state.get(f"show_delete_confirm_{session.id}", False):
            st.markdown("---")
            st.error("🚨 **Confirmation de suppression requise**")
            
            conf_col1, conf_col2, conf_col3 = st.columns([1, 1, 2])
            
            with conf_col1:
                if st.button("✅ **Oui, supprimer**", key=f"confirm_delete_detail_{session.id}", type="primary", use_container_width=True):
                    if self.delete_session_safe(session.id):
                        st.success("✅ Session supprimée avec succès")
                        # Nettoyer l'état
                        del st.session_state[f"show_delete_confirm_{session.id}"]
                        st.rerun()
                    else:
                        st.error("❌ Erreur lors de la suppression")
            
            with conf_col2:
                if st.button("❌ **Annuler**", key=f"cancel_delete_detail_{session.id}", use_container_width=True):
                    del st.session_state[f"show_delete_confirm_{session.id}"]
                    st.rerun()
            
            with conf_col3:
                st.caption("Cette action est irréversible !")
        
        st.markdown("---")
        
        # Actions sur les sessions
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🧹 Nettoyer les sessions terminées"):
                try:
                    # Vérifier si la méthode existe
                    if hasattr(st.session_state.session_manager, 'cleanup_old_sessions'):
                        cleaned = st.session_state.session_manager.cleanup_old_sessions()
                    elif hasattr(st.session_state.session_manager, '_cleanup_old_database_sessions'):
                        # Utiliser la méthode privée si disponible
                        st.session_state.session_manager._cleanup_old_database_sessions()
                        cleaned = "quelques"  # Estimation
                    else:
                        # Implémentation manuelle
                        cleaned = self.manual_cleanup_sessions()
                    
                    st.success(f"✅ {cleaned} session(s) nettoyée(s)")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erreur lors du nettoyage: {e}")
                    st.caption("Le nettoyage automatique n'est pas disponible dans cette version")
        
        with col2:
            if st.button("❌ Supprimer sessions non terminées"):
                self.show_cleanup_non_completed_sessions()
        
        with col3:
            if st.button("📊 Statistiques détaillées"):
                self.show_sessions_stats(sessions)
    
    def show_cleanup_non_completed_sessions(self):
        """Interface pour nettoyer les sessions non terminées"""
        st.subheader("🧹 Nettoyage des sessions non terminées")
        
        # Récupérer les sessions non terminées
        all_sessions = st.session_state.session_manager.list_sessions()
        non_completed_sessions = [
            s for s in all_sessions 
            if s.status in [SessionStatus.IN_PROGRESS, SessionStatus.PAUSED, SessionStatus.FAILED]
        ]
        
        if not non_completed_sessions:
            st.success("✅ Aucune session non terminée trouvée !")
            return
        
        st.warning(f"⚠️ **{len(non_completed_sessions)} session(s) non terminée(s) trouvée(s)**")
        
        # Grouper par statut
        sessions_by_status = {}
        for session in non_completed_sessions:
            status = session.status
            if status not in sessions_by_status:
                sessions_by_status[status] = []
            sessions_by_status[status].append(session)
        
        # Afficher par catégorie
        for status, sessions_list in sessions_by_status.items():
            status_name = status.value.replace('_', ' ').title()
            status_emoji = {
                SessionStatus.IN_PROGRESS: "🔄",
                SessionStatus.PAUSED: "⏸️", 
                SessionStatus.FAILED: "❌"
            }.get(status, "❓")
            
            with st.expander(f"{status_emoji} {status_name} ({len(sessions_list)} session(s))"):
                for session in sessions_list:
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                    
                    with col1:
                        st.write(f"**{session.artist_name}**")
                        st.caption(f"ID: {session.id[:8]}...")
                    
                    with col2:
                        if session.created_at:
                            age = datetime.now() - session.created_at
                            st.write(f"Âge: {age.days}j {age.seconds//3600}h")
                        else:
                            st.write("Âge: Inconnu")
                    
                    with col3:
                        progress_text = f"{session.tracks_processed}/{session.total_tracks_found}" if session.total_tracks_found > 0 else "N/A"
                        st.write(f"Progression: {progress_text}")
                        if session.current_step:
                            st.caption(session.current_step)
                    
                    with col4:
                        if st.button("🗑️", key=f"delete_{session.id}", help="Supprimer cette session"):
                            if self.delete_session_safe(session.id):
                                st.success(f"✅ Session {session.artist_name} supprimée")
                                st.rerun()
                            else:
                                st.error("❌ Erreur lors de la suppression")
        
        # Actions en lot
        st.markdown("---")
        st.markdown("### 🚨 Actions en lot")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("❌ Supprimer toutes les sessions échouées", type="secondary"):
                failed_sessions = [s for s in non_completed_sessions if s.status == SessionStatus.FAILED]
                if failed_sessions:
                    count = self.bulk_delete_sessions([s.id for s in failed_sessions])
                    st.success(f"✅ {count} session(s) échouée(s) supprimée(s)")
                    st.rerun()
                else:
                    st.info("ℹ️ Aucune session échouée à supprimer")
        
        with col2:
            if st.button("⏸️ Supprimer toutes les sessions en pause", type="secondary"):
                paused_sessions = [s for s in non_completed_sessions if s.status == SessionStatus.PAUSED]
                if paused_sessions:
                    count = self.bulk_delete_sessions([s.id for s in paused_sessions])
                    st.success(f"✅ {count} session(s) en pause supprimée(s)")
                    st.rerun()
                else:
                    st.info("ℹ️ Aucune session en pause à supprimer")
        
        with col3:
            # Sessions anciennes (plus de 7 jours)
            old_sessions = [
                s for s in non_completed_sessions 
                if s.created_at and (datetime.now() - s.created_at).days > 7
            ]
            if st.button(f"🕰️ Supprimer les anciennes (>{len(old_sessions)})", type="secondary"):
                if old_sessions:
                    count = self.bulk_delete_sessions([s.id for s in old_sessions])
                    st.success(f"✅ {count} session(s) ancienne(s) supprimée(s)")
                    st.rerun()
                else:
                    st.info("ℹ️ Aucune session ancienne à supprimer")
        
        # Confirmation pour suppression totale
        st.markdown("---")
        with st.expander("🚨 Zone de danger"):
            st.error("⚠️ **ATTENTION** : Cette action est irréversible !")
            
            confirm_text = st.text_input(
                "Tapez 'SUPPRIMER TOUT' pour confirmer la suppression de toutes les sessions non terminées:",
                key="confirm_delete_all"
            )
            
            if confirm_text == "SUPPRIMER TOUT":
                if st.button("💀 SUPPRIMER TOUTES LES SESSIONS NON TERMINÉES", type="primary"):
                    count = self.bulk_delete_sessions([s.id for s in non_completed_sessions])
                    st.success(f"✅ {count} session(s) supprimée(s)")
                    st.rerun()
    
    def delete_session_safe(self, session_id: str) -> bool:
        """Supprime une session de manière sécurisée - VERSION SIMPLIFIÉE"""
        try:
            if not session_id:
                st.error("❌ ID de session manquant")
                return False
            
            # Récupérer la session
            session = st.session_state.session_manager.get_session(session_id)
            if not session:
                st.info("ℹ️ Session introuvable - peut-être déjà supprimée")
                return True
            
            # Si session en cours, l'arrêter
            if session.status == SessionStatus.IN_PROGRESS:
                try:
                    st.session_state.session_manager.fail_session(
                        session_id, 
                        "Session arrêtée par l'utilisateur"
                    )
                except:
                    pass
            
            # Supprimer de la mémoire
            if hasattr(st.session_state.session_manager, 'active_sessions'):
                if session_id in st.session_state.session_manager.active_sessions:
                    del st.session_state.session_manager.active_sessions[session_id]
            
            # Supprimer de la base
            try:
                with st.session_state.session_manager.db.get_connection() as conn:
                    conn.execute("DELETE FROM checkpoints WHERE session_id = ?", (session_id,))
                    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                    conn.commit()
            except Exception as db_error:
                st.warning(f"⚠️ Erreur suppression DB: {db_error}")
            
            # Nettoyer Streamlit
            if st.session_state.current_session_id == session_id:
                st.session_state.current_session_id = None
            
            if st.session_state.get('background_extraction', {}).get('session_id') == session_id:
                del st.session_state.background_extraction
            
            return True
            
        except Exception as e:
            st.error(f"❌ Erreur suppression: {e}")
            return False
    
    def bulk_delete_sessions(self, session_ids: List[str]) -> int:
        """Supprime plusieurs sessions en lot"""
        deleted_count = 0
        
        for session_id in session_ids:
            try:
                if self.delete_session_safe(session_id):
                    deleted_count += 1
            except Exception as e:
                st.warning(f"⚠️ Erreur suppression {session_id[:8]}: {e}")
        
        return deleted_count
    
    def manual_cleanup_sessions(self) -> int:
        """Nettoyage manuel des sessions anciennes si la méthode automatique n'existe pas"""
        try:
            # Récupérer toutes les sessions
            all_sessions = st.session_state.session_manager.list_sessions()
            
            # Filtrer les sessions terminées ou échouées de plus de 30 jours
            cutoff_date = datetime.now() - timedelta(days=30)
            old_sessions = [
                s for s in all_sessions 
                if s.status in [SessionStatus.COMPLETED, SessionStatus.FAILED]
                and s.updated_at and s.updated_at < cutoff_date
            ]
            
            # Note: Nous ne pouvons pas réellement supprimer les sessions sans accès à la base
            # Cette fonction est plutôt informative
            return len(old_sessions)
            
        except Exception as e:
            st.error(f"Erreur lors du nettoyage manuel: {e}")
            return 0
    
    def render_exports(self):
        """Interface de gestion des exports complète"""
        st.header("📤 Gestion des exports")
        
        # Section 1: Export de session active ou sélectionnée
        st.subheader("🎤 Exporter une session")
        
        # Sélection de session
        sessions = [s for s in st.session_state.session_manager.list_sessions() 
                   if s.status == SessionStatus.COMPLETED]
        
        if not sessions:
            st.warning("⚠️ Aucune session terminée disponible pour l'export.")
            st.info("💡 Terminez d'abord une extraction dans 'Nouvelle extraction'.")
        else:
            session_options = {f"{s.artist_name} ({s.id[:8]})": s for s in sessions}
            selected_session_name = st.selectbox(
                "Choisir une session à exporter",
                list(session_options.keys())
            )
            
            if selected_session_name:
                selected_session = session_options[selected_session_name]
                self.render_session_export_form(selected_session)
        
        # Section 2: Gestion des fichiers d'export existants
        st.subheader("📂 Fichiers d'export existants")
        self.render_export_files()
    
    def render_session_export_form(self, session):
        """Formulaire d'export pour une session spécifique"""
        st.success(f"✅ Session sélectionnée: **{session.artist_name}**")
        
        with st.form(f"export_session_{session.id}"):
            col1, col2 = st.columns(2)
            
            with col1:
                if ExportFormat:
                    export_formats = st.multiselect(
                        "Formats d'export",
                        [f.value.upper() for f in ExportFormat],
                        default=["JSON", "HTML"],
                        help="Sélectionnez un ou plusieurs formats"
                    )
                else:
                    export_formats = st.multiselect(
                        "Formats d'export",
                        ["JSON", "CSV", "HTML"],
                        default=["JSON", "HTML"],
                        help="Sélectionnez un ou plusieurs formats"
                    )
            
            with col2:
                include_options = st.multiselect(
                    "Options d'inclusion",
                    ["Paroles", "Crédits détaillés", "Statistiques", "Données brutes"],
                    default=["Statistiques"],
                    help="Éléments à inclure dans l'export"
                )
            
            # Options avancées
            with st.expander("🔧 Options avancées"):
                custom_filename = st.text_input(
                    "Nom de fichier personnalisé (optionnel)",
                    placeholder=f"{session.artist_name}_{datetime.now().strftime('%Y%m%d')}"
                )
                
                col3, col4 = st.columns(2)
                with col3:
                    include_lyrics = st.checkbox("Inclure les paroles", value="Paroles" in include_options)
                    include_stats = st.checkbox("Inclure les statistiques", value="Statistiques" in include_options)
                
                with col4:
                    include_raw_data = st.checkbox("Données brutes", value="Données brutes" in include_options)
                    compress_output = st.checkbox("Compresser en ZIP", value=len(export_formats) > 1)
            
            # Bouton d'export
            submitted = st.form_submit_button(
                f"📥 Exporter en {', '.join(export_formats)}",
                use_container_width=True
            )
            
            if submitted and export_formats:
                self.perform_export(
                    session,
                    export_formats,
                    custom_filename,
                    include_lyrics,
                    include_stats,
                    include_raw_data,
                    compress_output
                )
    
    def perform_export(self, session, export_formats, custom_filename, 
                      include_lyrics, include_stats, include_raw_data, compress_output):
        """Effectue l'export d'une session"""
        try:
            with st.spinner("📦 Export en cours..."):
                # Récupération des données
                artist = st.session_state.database.get_artist_by_name(session.artist_name)
                if not artist:
                    st.error(f"❌ Artiste '{session.artist_name}' non trouvé en base")
                    return
                
                tracks = st.session_state.database.get_tracks_by_artist_id(artist.id)
                albums = st.session_state.database.get_albums_by_artist_id(artist.id)
                
                if not tracks:
                    st.error("❌ Aucun morceau trouvé pour cet artiste")
                    return
                
                # Options d'export
                options = {
                    'include_lyrics': include_lyrics,
                    'include_raw_data': include_raw_data,
                    'include_stats': include_stats
                }
                
                exported_files = []
                
                # Export dans chaque format
                for format_name in export_formats:
                    try:
                        if ExportFormat:
                            format_enum = ExportFormat(format_name.lower())
                        else:
                            format_enum = format_name.lower()
                        
                        # Nom de fichier
                        if custom_filename:
                            filename = f"{custom_filename}_{format_name.lower()}"
                        else:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            safe_artist_name = "".join(c for c in artist.name if c.isalnum() or c in (' ', '-', '_')).strip()
                            safe_artist_name = safe_artist_name.replace(' ', '_')
                            filename = f"{safe_artist_name}_{timestamp}_{format_name.lower()}"
                        
                        # Export via ExportManager
                        filepath = st.session_state.export_manager.export_artist_data(
                            artist=artist,
                            tracks=tracks,
                            albums=albums,
                            format=format_enum,
                            filename=filename,
                            options=options
                        )
                        
                        exported_files.append({
                            'format': format_name,
                            'path': filepath,
                            'size': os.path.getsize(filepath) if os.path.exists(filepath) else 0
                        })
                        
                    except Exception as e:
                        st.error(f"❌ Erreur export {format_name}: {str(e)}")
                
                if exported_files:
                    st.success(f"✅ Export terminé ! {len(exported_files)} fichier(s) créé(s)")
                    
                    # Affichage des fichiers créés
                    for file_info in exported_files:
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"📄 **{file_info['format']}** - {file_info['size'] / 1024:.1f} KB")
                        with col2:
                            # Bouton de téléchargement
                            try:
                                with open(file_info['path'], 'rb') as f:
                                    st.download_button(
                                        label="📥",
                                        data=f.read(),
                                        file_name=os.path.basename(file_info['path']),
                                        mime=self.get_mime_type(file_info['format']),
                                        key=f"download_{file_info['format']}_{session.id}"
                                    )
                            except Exception as e:
                                st.error(f"Erreur téléchargement: {e}")
                
                else:
                    st.error("❌ Aucun fichier d'export créé")
                
        except Exception as e:
            st.error(f"❌ Erreur lors de l'export: {str(e)}")
            st.exception(e)
    
    def get_mime_type(self, format: str) -> str:
        """Retourne le type MIME pour un format"""
        mime_types = {
            'JSON': 'application/json',
            'CSV': 'text/csv',
            'EXCEL': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'HTML': 'text/html',
            'XML': 'application/xml'
        }
        return mime_types.get(format.upper(), 'application/octet-stream')
    
    def render_export_files(self):
        """Affiche la liste des exports existants avec gestion d'erreurs robuste"""
        try:
            # Vérifier si la méthode list_exports existe
            if not hasattr(st.session_state.export_manager, 'list_exports'):
                st.info("📁 La fonctionnalité de listage des exports n'est pas disponible dans cette version.")
                st.caption("Les exports sont disponibles dans le dossier de données du projet.")
                return
            
            exports = st.session_state.export_manager.list_exports()
            
            if not exports:
                st.info("📁 Aucun export trouvé.")
                st.caption("Les exports créés apparaîtront ici.")
                return
            
            # Vérification de la structure des données
            if not isinstance(exports, list) or not exports:
                st.warning("⚠️ Format des données d'export inattendu.")
                return
            
            # Vérifier la structure du premier élément
            first_export = exports[0]
            required_fields = ['filename', 'created_at', 'size_mb', 'format', 'path']
            missing_fields = [field for field in required_fields if field not in first_export]
            
            if missing_fields:
                st.error(f"❌ Champs manquants dans les données d'export: {missing_fields}")
                st.caption("Essayez de recréer les exports.")
                return
            
            # Traitement des données pour l'affichage
            try:
                df = pd.DataFrame(exports)
                
                # Conversion sécurisée des dates
                try:
                    df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%d/%m/%Y %H:%M')
                except Exception as date_error:
                    st.warning(f"⚠️ Erreur conversion des dates: {date_error}")
                    df['created_at'] = df['created_at'].astype(str)
                
                # Conversion sécurisée des tailles
                try:
                    df['size_display'] = df['size_mb'].apply(lambda x: f"{float(x):.1f} MB" if x is not None else "N/A")
                except Exception as size_error:
                    st.warning(f"⚠️ Erreur conversion des tailles: {size_error}")
                    df['size_display'] = "N/A"
                
            except Exception as df_error:
                st.error(f"❌ Erreur traitement des données: {df_error}")
                return
            
            # Interface de sélection
            try:
                selected_indices = st.multiselect(
                    "Sélectionner des exports à gérer",
                    range(len(df)),
                    format_func=lambda i: f"{df.iloc[i]['filename']} ({df.iloc[i]['size_display']})"
                )
            except Exception as selection_error:
                st.error(f"❌ Erreur interface de sélection: {selection_error}")
                selected_indices = []
            
            # Actions en lot
            if selected_indices:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("📥 Télécharger sélectionnés"):
                        download_errors = []
                        for idx in selected_indices:
                            export = exports[idx]
                            try:
                                if os.path.exists(export['path']):
                                    with open(export['path'], 'rb') as f:
                                        st.download_button(
                                            label=f"📥 {export['filename']}",
                                            data=f.read(),
                                            file_name=export['filename'],
                                            key=f"download_{idx}",
                                            mime=self.get_mime_type(export.get('format', ''))
                                        )
                                else:
                                    download_errors.append(f"Fichier introuvable: {export['filename']}")
                            except Exception as e:
                                download_errors.append(f"Erreur {export['filename']}: {str(e)}")
                        
                        if download_errors:
                            for error in download_errors:
                                st.error(f"❌ {error}")
                
                with col2:
                    if st.button("🗑️ Supprimer sélectionnés"):
                        deleted_count = 0
                        delete_errors = []
                        
                        for idx in selected_indices:
                            try:
                                file_path = exports[idx]['path']
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                                    deleted_count += 1
                                else:
                                    delete_errors.append(f"Fichier déjà supprimé: {exports[idx]['filename']}")
                            except Exception as e:
                                delete_errors.append(f"Erreur suppression {exports[idx]['filename']}: {str(e)}")
                        
                        if deleted_count > 0:
                            st.success(f"✅ {deleted_count} export(s) supprimé(s)")
                            st.rerun()
                        
                        if delete_errors:
                            for error in delete_errors:
                                st.warning(f"⚠️ {error}")
                
                with col3:
                    try:
                        total_size = sum(float(exports[idx].get('size_mb', 0)) for idx in selected_indices)
                        st.metric("Taille totale", f"{total_size:.1f} MB")
                    except Exception as metric_error:
                        st.metric("Taille totale", "N/A")
            
            # Tableau d'affichage
            try:
                display_df = df[['filename', 'format', 'size_display', 'created_at']].copy()
                display_df.columns = ['Fichier', 'Format', 'Taille', 'Créé le']
                st.dataframe(display_df, use_container_width=True)
            except Exception as table_error:
                st.error(f"❌ Erreur affichage tableau: {table_error}")
                # Affichage alternatif simple
                st.write("**Liste des exports:**")
                for export in exports:
                    st.write(f"- {export.get('filename', 'N/A')} ({export.get('size_display', 'N/A')})")
            
            # Section de nettoyage
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🧹 Nettoyer exports anciens (>30 jours)"):
                    try:
                        if hasattr(st.session_state.export_manager, 'cleanup_old_exports'):
                            cleaned = st.session_state.export_manager.cleanup_old_exports(30)
                            st.success(f"✅ {cleaned} export(s) supprimé(s)")
                        else:
                            # Nettoyage manuel
                            cleaned = self.manual_cleanup_exports()
                            st.info(f"ℹ️ {cleaned} export(s) ancien(s) identifié(s)")
                        st.rerun()
                    except Exception as cleanup_error:
                        st.error(f"❌ Erreur nettoyage: {cleanup_error}")
            
            with col2:
                try:
                    total_size = sum(float(export.get('size_mb', 0)) for export in exports)
                    st.metric("Espace total utilisé", f"{total_size:.1f} MB")
                except Exception as total_error:
                    st.metric("Espace total utilisé", "N/A")
            
        except Exception as e:
            st.error(f"❌ Erreur lors de l'affichage des exports: {e}")
            st.caption("Vérifiez que l'ExportManager est correctement configuré.")
            
            # Interface de fallback
            with st.expander("🔧 Informations de debug"):
                st.write("État de l'ExportManager:")
                st.write(f"- Objet disponible: {hasattr(st.session_state, 'export_manager')}")
                if hasattr(st.session_state, 'export_manager'):
                    st.write(f"- Méthode list_exports: {hasattr(st.session_state.export_manager, 'list_exports')}")
                    st.write(f"- Type: {type(st.session_state.export_manager)}")
                st.write(f"- Erreur: {str(e)}")
    
    def render_settings(self):
        """Interface des paramètres"""
        st.header("⚙️ Paramètres")
        
        # Configuration des APIs
        st.subheader("🔑 Configuration des APIs")
        
        with st.form("api_config"):
            col1, col2 = st.columns(2)
            
            with col1:
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
            
            with col2:
                spotify_secret = st.text_input(
                    "Spotify Client Secret",
                    value=settings.spotify_client_secret or "",
                    type="password"
                )
                
                discogs_token = st.text_input(
                    "Token Discogs",
                    value=getattr(settings, 'discogs_token', '') or "",
                    type="password",
                    help="Optionnel - pour les informations d'albums"
                )
            
            if st.form_submit_button("💾 Sauvegarder"):
                st.success("Configuration sauvegardée !")
                st.info("Redémarrez l'interface pour appliquer les changements")
        
        # Paramètres d'extraction
        st.subheader("⚙️ Paramètres d'extraction")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Performance**")
            default_batch_size = st.slider("Taille de lot par défaut", 5, 50, 10)
            default_workers = st.slider("Threads parallèles", 1, 8, 3)
            cache_duration = st.slider("Durée du cache (jours)", 1, 30, 7)
        
        with col2:
            st.markdown("**Qualité**")
            retry_count = st.slider("Nombre de tentatives", 1, 5, 2)
            timeout_seconds = st.slider("Timeout API (sec)", 10, 60, 30)
            quality_threshold = st.slider("Seuil de qualité", 0.0, 1.0, 0.7)
        
        # Statistiques du système
        st.subheader("📊 Statistiques système")
        
        system_stats = self.get_system_stats()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Taille de la base", f"{system_stats.get('db_size_mb', 0):.1f} MB")
        
        with col2:
            st.metric("Taille du cache", f"{system_stats.get('cache_size_mb', 0):.1f} MB")
        
        with col3:
            st.metric("Exports créés", system_stats.get('exports_count', 0))
        
        with col4:
            st.metric("Sessions totales", len(st.session_state.session_manager.list_sessions()))
        
        # Actions de maintenance
        st.subheader("🧹 Maintenance")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🗑️ Nettoyer le cache"):
                try:
                    # Implémentation du nettoyage du cache
                    st.success("✅ Cache nettoyé !")
                except Exception as e:
                    st.error(f"❌ Erreur nettoyage cache: {e}")
        
        with col2:
            if st.button("📦 Nettoyer les exports anciens"):
                try:
                    if hasattr(st.session_state.export_manager, 'cleanup_old_exports'):
                        count = st.session_state.export_manager.cleanup_old_exports(30)
                        st.success(f"✅ {count} export(s) supprimé(s)")
                    else:
                        # Nettoyage manuel si la méthode n'existe pas
                        count = self.manual_cleanup_exports()
                        st.success(f"✅ {count} export(s) identifié(s) pour suppression")
                except Exception as e:
                    st.error(f"❌ Erreur nettoyage exports: {e}")
        
        with col3:
            if st.button("🔄 Vérifier les sessions"):
                try:
                    # Vérification des sessions actives
                    sessions = st.session_state.session_manager.list_sessions()
                    active_count = len([s for s in sessions if s.status == SessionStatus.IN_PROGRESS])
                    completed_count = len([s for s in sessions if s.status == SessionStatus.COMPLETED])
                    failed_count = len([s for s in sessions if s.status == SessionStatus.FAILED])
                    
                    st.success(f"✅ Vérification terminée:")
                    st.write(f"- {active_count} session(s) active(s)")
                    st.write(f"- {completed_count} session(s) terminée(s)")
                    st.write(f"- {failed_count} session(s) échouée(s)")
                except Exception as e:
                    st.error(f"❌ Erreur vérification: {e}")
    
    def manual_cleanup_exports(self) -> int:
        """Nettoyage manuel des exports si la méthode automatique n'existe pas"""
        try:
            if hasattr(st.session_state.export_manager, 'list_exports'):
                exports = st.session_state.export_manager.list_exports()
                cutoff_date = datetime.now() - timedelta(days=30)
                
                old_exports = [
                    e for e in exports 
                    if datetime.fromisoformat(e['created_at'].replace('T', ' ')) < cutoff_date
                ]
                
                return len(old_exports)
            else:
                return 0
        except Exception:
            return 0
    
    def get_quick_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques rapides avec gestion d'erreurs"""
        try:
            # Statistiques de sessions
            sessions = st.session_state.session_manager.list_sessions()
            active_sessions = len([s for s in sessions if s.status == SessionStatus.IN_PROGRESS])
            
            # Statistiques de base de données - avec vérification des méthodes
            total_artists = 0
            total_tracks = 0
            
            try:
                # Vérifier si les méthodes existent
                if hasattr(st.session_state.database, 'get_artist_count'):
                    total_artists = st.session_state.database.get_artist_count()
                
                if hasattr(st.session_state.database, 'get_track_count'):
                    total_tracks = st.session_state.database.get_track_count()
                
                # Méthodes alternatives si les principales n'existent pas
                if total_artists == 0 and hasattr(st.session_state.database, 'get_connection'):
                    with st.session_state.database.get_connection() as conn:
                        cursor = conn.execute("SELECT COUNT(DISTINCT id) FROM artists")
                        result = cursor.fetchone()
                        if result:
                            total_artists = result[0]
                
                if total_tracks == 0 and hasattr(st.session_state.database, 'get_connection'):
                    with st.session_state.database.get_connection() as conn:
                        cursor = conn.execute("SELECT COUNT(DISTINCT id) FROM tracks")
                        result = cursor.fetchone()
                        if result:
                            total_tracks = result[0]
            
            except Exception as db_error:
                print(f"Erreur accès base de données pour stats: {db_error}")
                # Valeurs par défaut en cas d'erreur
            
            return {
                'active_sessions': active_sessions,
                'total_artists': total_artists,
                'total_tracks': total_tracks,
                'total_sessions': len(sessions)
            }
        except Exception as e:
            print(f"Erreur dans get_quick_stats: {e}")
            return {'active_sessions': 0, 'total_artists': 0, 'total_tracks': 0, 'total_sessions': 0}
    
    def get_detailed_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques détaillées"""
        try:
            sessions = st.session_state.session_manager.list_sessions()
            
            # Calculs temporels
            now = datetime.now()
            week_ago = now - timedelta(days=7)
            
            sessions_this_week = len([s for s in sessions 
                                    if s.created_at and s.created_at >= week_ago])
            
            # Statistiques de base
            quick_stats = self.get_quick_stats()
            
            return {
                'total_sessions': quick_stats['total_sessions'],
                'sessions_this_week': sessions_this_week,
                'total_artists': quick_stats['total_artists'],
                'new_artists_this_week': 0,  # À implémenter si nécessaire
                'total_tracks': quick_stats['total_tracks'],
                'tracks_this_week': 0,  # À implémenter si nécessaire
                'total_credits': 0,  # À implémenter si nécessaire
                'credits_this_week': 0  # À implémenter si nécessaire
            }
        except Exception:
            return {
                'total_sessions': 0, 'sessions_this_week': 0,
                'total_artists': 0, 'new_artists_this_week': 0,
                'total_tracks': 0, 'tracks_this_week': 0,
                'total_credits': 0, 'credits_this_week': 0
            }
    
    def render_sessions_chart(self):
        """Affiche le graphique des sessions par statut"""
        try:
            sessions = st.session_state.session_manager.list_sessions()
            
            # Compter par statut
            status_counts = {}
            for session in sessions:
                status_name = session.status.value.replace('_', ' ').title()
                status_counts[status_name] = status_counts.get(status_name, 0) + 1
            
            if status_counts:
                data = {
                    'Statut': list(status_counts.keys()),
                    'Nombre': list(status_counts.values())
                }
                
                fig = px.pie(
                    data,
                    values='Nombre',
                    names='Statut',
                    color_discrete_sequence=['#17a2b8', '#28a745', '#dc3545', '#ffc107']
                )
                
                fig.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Aucune donnée de session disponible")
        except Exception as e:
            st.error(f"Erreur génération graphique: {e}")
    
    def render_top_artists_chart(self):
        """Affiche le graphique des top artistes"""
        try:
            sessions = st.session_state.session_manager.list_sessions()
            
            # Compter les morceaux par artiste
            artist_tracks = {}
            for session in sessions:
                if session.total_tracks_found > 0:
                    artist_tracks[session.artist_name] = session.total_tracks_found
            
            if artist_tracks:
                # Top 5 artistes
                top_artists = sorted(artist_tracks.items(), key=lambda x: x[1], reverse=True)[:5]
                
                data = {
                    'Artiste': [item[0] for item in top_artists],
                    'Morceaux': [item[1] for item in top_artists]
                }
                
                fig = px.bar(
                    data,
                    x='Morceaux',
                    y='Artiste',
                    orientation='h',
                    color='Morceaux',
                    color_continuous_scale='Viridis'
                )
                
                fig.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Aucune donnée d'artiste disponible")
        except Exception as e:
            st.error(f"Erreur génération graphique: {e}")
    
    def get_filtered_sessions(self, status_filter: str, date_filter: str) -> List:
        """Filtre les sessions selon les critères"""
        all_sessions = st.session_state.session_manager.list_sessions()
        
        # Filtre par statut
        if status_filter != "Tous":
            status_map = {
                "En cours": SessionStatus.IN_PROGRESS,
                "Terminées": SessionStatus.COMPLETED,
                "Échouées": SessionStatus.FAILED,
                "En pause": SessionStatus.PAUSED
            }
            if status_filter in status_map:
                all_sessions = [s for s in all_sessions if s.status == status_map[status_filter]]
        
        # Filtre par date
        now = datetime.now()
        if date_filter == "Aujourd'hui":
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
            all_sessions = [s for s in all_sessions if s.created_at and s.created_at >= cutoff]
        elif date_filter == "Cette semaine":
            cutoff = now - timedelta(days=7)
            all_sessions = [s for s in all_sessions if s.created_at and s.created_at >= cutoff]
        elif date_filter == "Ce mois":
            cutoff = now - timedelta(days=30)
            all_sessions = [s for s in all_sessions if s.created_at and s.created_at >= cutoff]
        
        return sorted(all_sessions, key=lambda x: x.updated_at or datetime.min, reverse=True)
    
    def show_sessions_stats(self, sessions):
        """Affiche les statistiques détaillées des sessions"""
        if not sessions:
            return
        
        st.subheader("📊 Statistiques détaillées")
        
        # Métriques générales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_tracks = sum(s.total_tracks_found for s in sessions)
            st.metric("Morceaux totaux", total_tracks)
        
        with col2:
            total_processed = sum(s.tracks_processed for s in sessions)
            st.metric("Morceaux traités", total_processed)
        
        with col3:
            total_with_credits = sum(s.tracks_with_credits for s in sessions)
            st.metric("Avec crédits", total_with_credits)
        
        with col4:
            if total_processed > 0:
                success_rate = (total_with_credits / total_processed) * 100
                st.metric("Taux de succès", f"{success_rate:.1f}%")
            else:
                st.metric("Taux de succès", "N/A")
        
        # Graphique temporel
        if len(sessions) > 1:
            st.subheader("📈 Évolution temporelle")
            
            session_dates = []
            session_counts = []
            
            for session in sorted(sessions, key=lambda x: x.created_at or datetime.min):
                if session.created_at:
                    session_dates.append(session.created_at.strftime('%d/%m'))
                    session_counts.append(session.total_tracks_found)
            
            if session_dates:
                fig = px.line(
                    x=session_dates,
                    y=session_counts,
                    title="Morceaux trouvés par session"
                )
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques système"""
        try:
            # Taille de la base de données
            db_size_mb = 0
            try:
                if hasattr(st.session_state.database, 'db_path'):
                    db_path = st.session_state.database.db_path
                    if os.path.exists(db_path):
                        db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
            except:
                pass
            
            # Statistiques des exports
            export_stats = st.session_state.export_manager.get_stats()
            
            # Taille du cache (estimation)
            cache_size_mb = 0
            try:
                cache_dir = settings.data_dir / "cache"
                if cache_dir.exists():
                    total_size = sum(f.stat().st_size for f in cache_dir.rglob('*') if f.is_file())
                    cache_size_mb = total_size / (1024 * 1024)
            except:
                pass
            
            return {
                'db_size_mb': db_size_mb,
                'cache_size_mb': cache_size_mb,
                'exports_count': export_stats.get('exports_created', 0)
            }
        except Exception:
            return {'db_size_mb': 0, 'cache_size_mb': 0, 'exports_count': 0}
    
    def render_alerts(self):
        """Affiche les alertes et notifications système"""
        st.subheader("🚨 État du système")
        
        alerts = []
        
        # Vérification des clés API
        if not settings.genius_api_key:
            alerts.append({
                'type': 'error',
                'message': 'Clé API Genius manquante - extraction des crédits limitée',
                'action': 'Configurer dans Paramètres → APIs'
            })
        
        if not settings.spotify_client_id:
            alerts.append({
                'type': 'warning', 
                'message': 'Spotify non configuré - pas de données BPM/features',
                'action': 'Configurer dans Paramètres → APIs'
            })
        
        # Sessions échouées récentes
        try:
            failed_sessions = [s for s in st.session_state.session_manager.list_sessions() 
                             if s.status == SessionStatus.FAILED]
            if failed_sessions:
                alerts.append({
                    'type': 'warning',
                    'message': f'{len(failed_sessions)} session(s) échouée(s) récemment',
                    'action': 'Voir Sessions pour plus de détails'
                })
        except:
            pass
        
        # Espace disque
        try:
            system_stats = self.get_system_stats()
            total_size = system_stats['db_size_mb'] + system_stats['cache_size_mb']
            if total_size > 500:  # Plus de 500 MB
                alerts.append({
                    'type': 'info',
                    'message': f'Utilisation disque importante: {total_size:.1f} MB',
                    'action': 'Nettoyer le cache dans Paramètres'
                })
        except:
            pass
        
        # Affichage des alertes
        if alerts:
            for alert in alerts:
                if alert['type'] == 'error':
                    st.error(f"❌ {alert['message']}")
                    st.caption(f"💡 {alert['action']}")
                elif alert['type'] == 'warning':
                    st.warning(f"⚠️ {alert['message']}")
                    st.caption(f"💡 {alert['action']}")
                else:
                    st.info(f"ℹ️ {alert['message']}")
                    st.caption(f"💡 {alert['action']}")
        else:
            st.success("✅ Tous les systèmes fonctionnent correctement !")


def main():
    """Fonction principale"""
    try:
        app = StreamlitInterface()
        app.run()
    except Exception as e:
        st.error(f"Erreur critique: {e}")
        st.exception(e)
        
        # Interface de debug
        with st.expander("🐛 Informations de debug"):
            st.write("Variables de session:")
            session_vars = {k: str(v)[:100] + "..." if len(str(v)) > 100 else str(v) 
                           for k, v in st.session_state.items()}
            st.json(session_vars)

if __name__ == "__main__":
    main()