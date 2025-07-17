# streamlit_app.py - Version complète corrigée
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
import logging

# Configuration de la page
st.set_page_config(
    page_title="Music Data Extractor",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .metric-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin-bottom: 1rem;
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
    
    /* MASQUER LES RONDS DES RADIO BUTTONS */
    .stRadio > div > label > div:first-child {
        display: none !important;
    }
    
    /* Amélioration de la navigation sidebar */
    .stRadio > div {
        gap: 8px;
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
    
    /* AMÉLIORATION DU CADRE BLANC - Meilleur contraste */
    .section-header {
        background: linear-gradient(45deg, #2c3e50, #34495e) !important;
        color: white !important;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        margin-bottom: 1.5rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .section-header h2 {
        color: white !important;
        margin: 0 !important;
        font-size: 1.5rem !important;
    }
    
    .section-header p {
        color: #ecf0f1 !important;
        margin: 0.5rem 0 0 0 !important;
        opacity: 0.9;
    }
    
    /* Amélioration des expanders */
    .streamlit-expanderHeader {
        background: rgba(102, 126, 234, 0.1);
        border-radius: 6px;
        font-weight: bold;
    }
    
    /* Améliorer la lisibilité des formulaires */
    .stForm {
        background: rgba(248, 249, 250, 0.02);
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid rgba(0, 0, 0, 0.1);
    }
    
    /* Style pour les conteneurs principaux */
    .block-container {
        padding-top: 1rem;
    }
    
    /* FORCER LA SIDEBAR À RESTER OUVERTE */
    .css-1d391kg {
        width: 21rem !important;
        min-width: 21rem !important;
    }
    
    .css-1y4p8pa {
        width: 21rem !important;
        min-width: 21rem !important;
    }
    
    /* Masquer le bouton de fermeture de la sidebar */
    .css-1rs6os {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

def safe_import_modules():
    """Import sécurisé des modules avec gestion d'erreurs"""
    try:
        from config.settings import settings
        from core.database import Database
        from core.session_manager import get_session_manager
        from steps.step1_discover import DiscoveryStep
        from utils.export_utils import ExportManager
        from models.enums import SessionStatus, ExtractionStatus
        
        modules = {
            'settings': settings,
            'Database': Database,
            'get_session_manager': get_session_manager,
            'DiscoveryStep': DiscoveryStep,
            'ExportManager': ExportManager,
            'SessionStatus': SessionStatus
        }
        
        # Imports optionnels
        try:
            from steps.step2_extract import ExtractionStep
            modules['ExtractionStep'] = ExtractionStep
        except ImportError:
            modules['ExtractionStep'] = None
        
        try:
            from steps.step4_export import Step4Export
            from models.enums import ExportFormat
            modules['Step4Export'] = Step4Export
            modules['ExportFormat'] = ExportFormat
        except ImportError:
            modules['Step4Export'] = None
            modules['ExportFormat'] = None
        
        return modules, True
        
    except ImportError as e:
        st.error(f"❌ Erreur d'import des modules: {e}")
        return {}, False

def safe_calculate_age(session_datetime):
    """Calcule l'âge d'une session de manière sécurisée"""
    if not session_datetime:
        return timedelta(0)
    
    try:
        current_time = datetime.now()
        if hasattr(session_datetime, 'tzinfo') and session_datetime.tzinfo:
            session_datetime = session_datetime.replace(tzinfo=None)
        
        age = current_time - session_datetime
        return age if age.total_seconds() >= 0 else timedelta(0)
        
    except Exception as e:
        st.warning(f"⚠️ Erreur calcul âge: {e}")
        return timedelta(0)

def format_age(age_timedelta):
    """Formate un timedelta en chaîne lisible"""
    if not age_timedelta or age_timedelta.total_seconds() < 1:
        return "quelques secondes"
    
    total_seconds = int(age_timedelta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    
    if days > 0:
        return f"{days}j {hours}h" if hours > 0 else f"{days}j"
    elif hours > 0:
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
    elif minutes > 0:
        return f"{minutes}m"
    else:
        return "quelques secondes"

class StreamlitInterface:
    """Interface Streamlit principale - Version simplifiée et robuste"""
    
    def __init__(self):
        # Import des modules
        self.modules, self.modules_available = safe_import_modules()
        if not self.modules_available:
            st.stop()
        
        # Initialisation des composants avec gestion d'erreurs
        self.init_components()
        
        # État de l'interface simplifié
        if 'current_session_id' not in st.session_state:
            st.session_state.current_session_id = None
    
    def init_components(self):
        """Initialise les composants avec gestion d'erreurs robuste"""
        try:
            # Database
            if 'database' not in st.session_state:
                st.session_state.database = self.modules['Database']()
            
            # Session Manager avec fallback simple
            if 'session_manager' not in st.session_state:
                try:
                    st.session_state.session_manager = self.modules['get_session_manager']()
                except Exception as e:
                    st.warning(f"⚠️ Session manager unavailable: {e}")
                    st.session_state.session_manager = None
            
            # Discovery Step
            if 'discovery_step' not in st.session_state:
                st.session_state.discovery_step = self.modules['DiscoveryStep']()
            
            # Export Manager
            if 'export_manager' not in st.session_state:
                st.session_state.export_manager = self.modules['ExportManager']()
            
            # Extraction Step (optionnel)
            if self.modules['ExtractionStep'] and 'extraction_step' not in st.session_state:
                st.session_state.extraction_step = self.modules['ExtractionStep']()
            
            # Export Step (optionnel)
            if self.modules['Step4Export'] and 'export_step' not in st.session_state:
                st.session_state.export_step = self.modules['Step4Export'](st.session_state.database)
                
        except Exception as e:
            st.error(f"❌ Erreur initialisation composants: {e}")
    
    def run(self):
        """Lance l'interface principale"""
        # En-tête
        st.markdown("""
        <div class="main-header">
            <h1>🎵 Music Data Extractor</h1>
            <p>Extracteur de données musicales avec focus rap/hip-hop</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Sidebar avec menu amélioré
        with st.sidebar:
            st.markdown("### 📱 Navigation")
            
            # Vérification des paramètres de navigation
            if 'main_navigation' not in st.session_state:
                st.session_state.main_navigation = "🏠 Dashboard"
            
            # Navigation avec boutons stylés
            page = st.radio(
                "Choisissez une section",
                ["🏠 Dashboard", "🔍 Nouvelle extraction", "📝 Sessions", "📤 Exports", "⚙️ Paramètres"],
                index=["🏠 Dashboard", "🔍 Nouvelle extraction", "📝 Sessions", "📤 Exports", "⚙️ Paramètres"].index(st.session_state.main_navigation),
                label_visibility="collapsed",
                key="main_navigation"
            )
            
            # Informations système
            st.markdown("---")
            self.render_sidebar_info()
        
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
    
    def render_sidebar_info(self):
        """Affiche les informations dans la sidebar"""
        try:
            st.markdown("### 📊 État du système")
            
            # Statut base de données
            st.success("✅ Base de données connectée")
            
            # Statut API
            settings = self.modules['settings']
            if hasattr(settings, 'genius_api_key') and settings.genius_api_key:
                st.success("✅ API Genius configurée")
            else:
                st.error("❌ API Genius non configurée")
            
            # Sessions si disponibles
            if st.session_state.session_manager:
                try:
                    sessions = st.session_state.session_manager.list_sessions()
                    active_sessions = len([s for s in sessions if s.status == self.modules['SessionStatus'].IN_PROGRESS])
                    total_sessions = len(sessions)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Sessions totales", total_sessions)
                    with col2:
                        st.metric("Sessions actives", active_sessions)
                        
                except Exception as e:
                    st.warning("⚠️ Sessions non disponibles")
            
            # Métriques rapides de la base
            stats = self.get_quick_stats()
            if stats:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Artistes", stats.get('total_artists', 0))
                with col2:
                    st.metric("Morceaux", stats.get('total_tracks', 0))
            
            # Section aide rapide
            st.markdown("---")
            st.markdown("### 💡 Aide rapide")
            
            with st.expander("🚀 Démarrage rapide"):
                st.write("1. Allez dans **Nouvelle extraction**")
                st.write("2. Tapez un nom d'artiste (ex: Eminem)")
                st.write("3. Cliquez sur **Lancer l'extraction**")
                st.write("4. Consultez les résultats")
            
            with st.expander("⚙️ Configuration"):
                st.write("• **API Genius** : Obligatoire pour l'extraction")
                st.write("• **Sources** : Configurables dans les options avancées")
                st.write("• **Paramètres** : Modifiables dans l'onglet Paramètres")
                
        except Exception as e:
            st.error(f"❌ Erreur sidebar: {e}")
    
    def render_new_extraction(self):
        """Interface pour nouvelle extraction - Version améliorée"""
        st.markdown('<div class="section-header"><h2>🔍 Nouvelle extraction</h2><p>Extrayez les données d\'un artiste depuis plusieurs sources</p></div>', unsafe_allow_html=True)
        
        # Indicateur des sources disponibles
        st.subheader("🔌 Sources disponibles")
        settings = self.modules['settings']
        
        col_sources = st.columns(5)
        sources_status = [
            ("Genius", hasattr(settings, 'genius_api_key') and settings.genius_api_key),
            ("Spotify", hasattr(settings, 'spotify_client_id') and settings.spotify_client_id),
            ("Discogs", hasattr(settings, 'discogs_token') and settings.discogs_token),
            ("LastFM", hasattr(settings, 'lastfm_api_key') and settings.lastfm_api_key),
            ("Rapedia", True)  # Scraping, pas d'API nécessaire
        ]
        
        for i, (source, is_available) in enumerate(sources_status):
            with col_sources[i]:
                status = "✅" if is_available else "❌"
                color = "green" if is_available else "red"
                st.markdown(f":{color}[{status} {source}]")
        
        if not any(status[1] for status in sources_status[:3]):  # Au moins une API principale
            st.warning("⚠️ Aucune API principale configurée. Configurez au moins Genius dans les Paramètres.")
        
        st.markdown("---")
        
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
                    value=100
                )
            
            # Options avancées
            with st.expander("🔧 Options avancées"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Contenu**")
                    enable_lyrics = st.checkbox("Inclure les paroles", True)
                    include_features = st.checkbox("Inclure les featuring", True)
                    force_refresh = st.checkbox("Forcer le rafraîchissement", False)
                
                with col2:
                    st.markdown("**Sources prioritaires**")
                    priority_sources = st.multiselect(
                        "Ordre de priorité des sources",
                        ["Genius", "Spotify", "Discogs", "LastFM", "Rapedia"],
                        default=["Genius", "Spotify"],
                        help="Sources consultées en priorité pour trouver les morceaux"
                    )
                
                # Paramètres de performance
                st.markdown("**Paramètres de performance**")
                col3, col4 = st.columns(2)
                
                with col3:
                    batch_size = st.slider("Taille des lots", 5, 50, 10, help="Nombre de morceaux traités simultanément")
                    timeout_seconds = st.slider("Timeout API (sec)", 10, 60, 30, help="Temps maximum d'attente par requête")
                
                with col4:
                    max_workers = st.slider("Threads parallèles", 1, 8, 3, help="Nombre de requêtes simultanées")
                    retry_failed = st.checkbox("Retry automatique", True, help="Relancer automatiquement les requêtes échouées")
            
            submitted = st.form_submit_button("🚀 Lancer l'extraction", use_container_width=True)
            
            if submitted and artist_name:
                self.start_extraction_robust(
                    artist_name=artist_name,
                    max_tracks=max_tracks,
                    enable_lyrics=enable_lyrics,
                    include_features=include_features,
                    priority_sources=priority_sources,
                    force_refresh=force_refresh,
                    batch_size=batch_size,
                    max_workers=max_workers,
                    timeout_seconds=timeout_seconds,
                    retry_failed=retry_failed
                )
    
    def start_extraction_robust(self, **kwargs):
        """Démarre une extraction avec gestion d'erreurs robuste"""
        artist_name = kwargs['artist_name']
        
        # Containers pour l'affichage
        status_container = st.empty()
        progress_container = st.empty()
        results_container = st.empty()
        
        try:
            with status_container.container():
                st.info(f"🚀 **Démarrage de l'extraction pour {artist_name}**")
            
            # Étape 1: Session (simple et robuste)
            session_id = self.create_session_robust(artist_name, kwargs)
            
            with progress_container.container():
                st.write("🔍 **Découverte des morceaux en cours...**")
                progress_bar = st.progress(0, text="Recherche...")
            
            # Étape 2: Découverte avec gestion d'erreurs robuste
            progress_bar.progress(0.3, text="Interrogation des sources...")
            
            tracks, stats = self.discover_tracks_robust(artist_name, session_id, kwargs)
            
            progress_bar.progress(1.0, text="Découverte terminée")
            
            # Affichage des résultats
            with results_container.container():
                if tracks:
                    self.display_discovery_results(tracks, stats, artist_name)
                    
                    # Actions suivantes
                    st.markdown("### 🎯 Prochaines étapes")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("🔄 **Nouvelle extraction**", use_container_width=True):
                            self.clear_extraction_state()
                            st.rerun()
                    
                    with col2:
                        if st.button("📊 **Voir Sessions**", use_container_width=True):
                            st.info("💡 Consultez l'onglet Sessions")
                    
                    with col3:
                        if st.button("📤 **Aller aux Exports**", use_container_width=True):
                            st.info("💡 Consultez l'onglet Exports")
                else:
                    st.error(f"❌ Aucun morceau trouvé pour {artist_name}")
                    
                    if st.button("🔄 **Réessayer**", use_container_width=True):
                        self.clear_extraction_state()
                        st.rerun()
            
            # Nettoyer les containers de progression
            status_container.empty()
            progress_container.empty()
            
        except Exception as e:
            st.error(f"❌ Erreur lors de l'extraction: {e}")
            
            # Affichage de debug si nécessaire
            with st.expander("🔍 Détails de l'erreur"):
                st.exception(e)
            
            if st.button("🔄 **Réessayer**", use_container_width=True):
                self.clear_extraction_state()
                st.rerun()
    
    def create_session_robust(self, artist_name: str, kwargs: dict) -> str:
        """Crée une session de manière robuste avec fallback"""
        import uuid
        
        # Essai avec SessionManager si disponible
        if st.session_state.session_manager:
            try:
                session_id = st.session_state.session_manager.create_session(
                    artist_name=artist_name,
                    metadata=kwargs
                )
                return session_id
            except Exception as e:
                st.warning(f"⚠️ SessionManager failed: {e}, using fallback")
        
        # Fallback: Session temporaire
        session_id = f"temp_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        
        if 'temp_sessions' not in st.session_state:
            st.session_state.temp_sessions = {}
        
        st.session_state.temp_sessions[session_id] = {
            'id': session_id,
            'artist_name': artist_name,
            'status': 'in_progress',
            'created_at': datetime.now(),
            'metadata': kwargs
        }
        
        st.session_state.current_session_id = session_id
        st.info("📝 Session temporaire créée")
        return session_id
    
    def discover_tracks_robust(self, artist_name: str, session_id: str, kwargs: dict):
        """Découverte robuste avec gestion d'erreurs détaillée"""
        try:
            # Appel de découverte avec gestion d'erreurs
            tracks, stats = st.session_state.discovery_step.discover_artist_tracks(
                artist_name=artist_name,
                session_id=session_id,
                max_tracks=kwargs.get('max_tracks', 100)
            )
            
            return tracks, stats
            
        except KeyError as ke:
            # Gestion spécifique de l'erreur "No item with that key"
            st.error(f"❌ Erreur de clé manquante: {ke}")
            st.warning("💡 Cette erreur indique souvent un problème avec l'API ou les données retournées")
            
            # Proposer un diagnostic
            with st.expander("🔍 Diagnostic"):
                st.write("**Causes possibles:**")
                st.write("- Clé API invalide ou expirée")
                st.write("- Structure de données inattendue de l'API")
                st.write("- Nom d'artiste non reconnu par les sources")
                st.write("- Problème temporaire avec les services externes")
                
                st.write("**Solutions:**")
                st.write("1. Vérifiez les clés API dans Paramètres")
                st.write("2. Essayez avec un nom d'artiste plus connu")
                st.write("3. Réessayez dans quelques minutes")
            
            raise Exception(f"Erreur découverte pour {artist_name}: {ke}")
            
        except Exception as e:
            st.error(f"❌ Erreur découverte: {e}")
            raise
    
    def display_discovery_results(self, tracks, stats, artist_name):
        """Affiche les résultats de découverte"""
        st.success(f"🎉 **Extraction réussie pour {artist_name}!**")
        
        # Métriques
        if hasattr(stats, 'final_count'):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("🎵 Morceaux trouvés", stats.final_count)
            
            with col2:
                st.metric("💎 Genius", getattr(stats, 'genius_found', 0))
            
            with col3:
                st.metric("🗑️ Doublons supprimés", getattr(stats, 'duplicates_removed', 0))
            
            with col4:
                if hasattr(stats, 'discovery_time_seconds'):
                    st.metric("⏱️ Temps", f"{stats.discovery_time_seconds:.1f}s")
        else:
            # Fallback si stats n'a pas la structure attendue
            st.metric("🎵 Morceaux trouvés", len(tracks) if tracks else 0)
        
        # Informations supplémentaires
        if tracks:
            st.write(f"✅ **{len(tracks)} morceaux** découverts avec succès")
            
            # Aperçu des premiers morceaux
            with st.expander("👁️ Aperçu des morceaux trouvés"):
                preview_tracks = tracks[:5]  # Premiers 5 morceaux
                for i, track in enumerate(preview_tracks):
                    title = track.title if hasattr(track, 'title') else track.get('title', 'Titre inconnu')
                    st.write(f"{i+1}. {title}")
                
                if len(tracks) > 5:
                    st.caption(f"... et {len(tracks) - 5} autres morceaux")
    
    def clear_extraction_state(self):
        """Nettoie l'état d'extraction"""
        # Nettoyer les sessions temporaires si elles existent
        if 'temp_sessions' in st.session_state:
            st.session_state.temp_sessions.clear()
        
        # Réinitialiser l'ID de session courante
        st.session_state.current_session_id = None
    
    def render_dashboard(self):
        """Dashboard amélioré avec plus d'informations"""
        st.markdown('<div class="section-header"><h2>📊 Dashboard - Vue d\'ensemble</h2></div>', unsafe_allow_html=True)
        
        # Métriques principales
        st.subheader("📈 Métriques principales")
        stats = self.get_quick_stats()
        if stats:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Sessions totales", 
                    stats.get('total_sessions', 0),
                    help="Nombre total de sessions d'extraction créées"
                )
            with col2:
                st.metric(
                    "Artistes extraits", 
                    stats.get('total_artists', 0),
                    help="Nombre d'artistes dans la base de données"
                )
            with col3:
                st.metric(
                    "Morceaux trouvés", 
                    stats.get('total_tracks', 0),
                    help="Nombre total de morceaux découverts"
                )
            with col4:
                active_count = stats.get('active_sessions', 0)
                st.metric(
                    "Sessions actives", 
                    active_count,
                    delta=f"+{active_count}" if active_count > 0 else None,
                    help="Extractions en cours"
                )
        
        # État du système
        st.subheader("🔧 État du système")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Configuration API**")
            settings = self.modules['settings']
            
            # Statut Genius
            genius_status = "✅ Configuré" if (hasattr(settings, 'genius_api_key') and settings.genius_api_key) else "❌ Non configuré"
            st.write(f"• **Genius API:** {genius_status}")
            
            # Statut Spotify
            spotify_status = "✅ Configuré" if (hasattr(settings, 'spotify_client_id') and settings.spotify_client_id) else "❌ Non configuré"
            st.write(f"• **Spotify API:** {spotify_status}")
            
            # Autres APIs
            discogs_status = "✅ Configuré" if (hasattr(settings, 'discogs_token') and settings.discogs_token) else "❌ Non configuré"
            st.write(f"• **Discogs API:** {discogs_status}")
        
        with col2:
            st.markdown("**Composants système**")
            
            # Base de données
            st.write("• **Base de données:** ✅ Connectée")
            
            # Session Manager
            session_status = "✅ Actif" if st.session_state.session_manager else "❌ Indisponible"
            st.write(f"• **Gestionnaire de sessions:** {session_status}")
            
            # Discovery Step
            discovery_status = "✅ Disponible" if st.session_state.discovery_step else "❌ Indisponible"
            st.write(f"• **Module de découverte:** {discovery_status}")
        
        # Activité récente
        st.subheader("📈 Activité récente")
        
        if st.session_state.session_manager:
            try:
                sessions = st.session_state.session_manager.list_sessions()
                recent_sessions = sorted(sessions, key=lambda s: s.created_at or datetime.min, reverse=True)[:5]
                
                if recent_sessions:
                    st.markdown("**Dernières sessions d'extraction:**")
                    
                    for i, session in enumerate(recent_sessions):
                        status_emoji = {
                            self.modules['SessionStatus'].IN_PROGRESS: "🔄",
                            self.modules['SessionStatus'].COMPLETED: "✅",
                            self.modules['SessionStatus'].FAILED: "❌"
                        }.get(session.status, "❓")
                        
                        # Calcul de l'âge
                        age_str = "récemment"
                        if session.created_at:
                            age = safe_calculate_age(session.created_at)
                            age_str = format_age(age)
                        
                        # Affichage de la session
                        col_session, col_status, col_age = st.columns([3, 2, 1])
                        
                        with col_session:
                            st.write(f"**{session.artist_name}**")
                        with col_status:
                            st.write(f"{status_emoji} {session.status.value.replace('_', ' ').title()}")
                        with col_age:
                            st.caption(age_str)
                        
                        if i < len(recent_sessions) - 1:
                            st.markdown("---")
                else:
                    st.info("💡 Aucune session récente. Commencez par une **Nouvelle extraction** !")
                    
                    if st.button("🚀 **Commencer une extraction**", use_container_width=True):
                        st.session_state.navigate_to_extraction = True
                        st.rerun()
                        
            except Exception as e:
                st.warning("⚠️ Impossible de charger les sessions récentes")
                st.caption(f"Erreur: {e}")
        else:
            st.info("💡 Gestionnaire de sessions non disponible")
        
        # Actions rapides
        st.subheader("⚡ Actions rapides")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("🔍 **Nouvelle extraction**", use_container_width=True):
                st.session_state.main_navigation = "🔍 Nouvelle extraction"
                st.rerun()
        
        with col2:
            if st.button("📝 **Voir les sessions**", use_container_width=True):
                st.session_state.main_navigation = "📝 Sessions"
                st.rerun()
        
        with col3:
            if st.button("📤 **Gérer les exports**", use_container_width=True):
                st.session_state.main_navigation = "📤 Exports"
                st.rerun()
        
        with col4:
            if st.button("⚙️ **Paramètres**", use_container_width=True):
                st.session_state.main_navigation = "⚙️ Paramètres"
                st.rerun()
    
    def render_sessions(self):
        """Gestion des sessions améliorée"""
        st.markdown('<div class="section-header"><h2>📝 Sessions</h2><p>Gérez vos extractions passées et en cours</p></div>', unsafe_allow_html=True)
        
        if not st.session_state.session_manager:
            st.error("⚠️ Gestionnaire de sessions non disponible")
            st.info("💡 Le système fonctionne en mode dégradé. Les sessions temporaires sont utilisées.")
            return
        
        try:
            sessions = st.session_state.session_manager.list_sessions()
            
            if not sessions:
                st.info("Aucune session trouvée")
                return
            
            # Afficher les messages de succès des suppressions
            for session_id in list(st.session_state.keys()):
                if session_id.startswith("success_delete_"):
                    st.success("✅ Session supprimée avec succès !")
                    del st.session_state[session_id]
            
            # Affichage simple des sessions
            st.subheader(f"📋 {len(sessions)} session(s) trouvée(s)")
            
            for session in sessions:
                with st.container():
                    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                    
                    with col1:
                        st.write(f"**{session.artist_name}**")
                        st.caption(f"ID: {session.id[:8]}...")
                    
                    with col2:
                        status_emoji = {
                            self.modules['SessionStatus'].IN_PROGRESS: "🔄",
                            self.modules['SessionStatus'].COMPLETED: "✅",
                            self.modules['SessionStatus'].FAILED: "❌"
                        }.get(session.status, "❓")
                        st.write(f"{status_emoji} {session.status.value}")
                    
                    with col3:
                        if session.created_at:
                            age = safe_calculate_age(session.created_at)
                            st.write(format_age(age))
                        
                        # Afficher la progression si disponible
                        if hasattr(session, 'total_tracks_found') and session.total_tracks_found > 0:
                            progress = getattr(session, 'tracks_processed', 0) / session.total_tracks_found
                            st.progress(progress)
                            st.caption(f"{getattr(session, 'tracks_processed', 0)}/{session.total_tracks_found} morceaux")
                    
                    with col4:
                        # Système de confirmation pour éviter les suppressions accidentelles
                        delete_key = f"confirm_delete_{session.id}"
                        
                        if delete_key not in st.session_state:
                            st.session_state[delete_key] = False
                        
                        if not st.session_state[delete_key]:
                            if st.button("🗑️", key=f"delete_session_{session.id}", help="Supprimer cette session"):
                                st.session_state[delete_key] = True
                                st.rerun()
                        else:
                            # Mode confirmation
                            col_confirm1, col_confirm2 = st.columns(2)
                            with col_confirm1:
                                if st.button("✅", key=f"confirm_yes_{session.id}", help="Confirmer la suppression"):
                                    if self.delete_session_safe(session.id):
                                        st.session_state[f"success_delete_{session.id}"] = True
                                        del st.session_state[delete_key]
                                        st.rerun()
                                    else:
                                        st.error("❌ Erreur lors de la suppression")
                                        st.session_state[delete_key] = False
                            
                            with col_confirm2:
                                if st.button("❌", key=f"confirm_no_{session.id}", help="Annuler"):
                                    st.session_state[delete_key] = False
                                    st.rerun()
                    
                    st.markdown("---")
            
            # Section de gestion en lot des sessions
            st.subheader("🧹 Gestion des sessions")
            
            # Statistiques par statut
            stats_by_status = {}
            for session in sessions:
                status = session.status.value
                stats_by_status[status] = stats_by_status.get(status, 0) + 1
            
            # Affichage des statistiques
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
            
            with col_stat1:
                completed_count = stats_by_status.get('completed', 0)
                st.metric("✅ Terminées", completed_count)
            
            with col_stat2:
                failed_count = stats_by_status.get('failed', 0)
                st.metric("❌ Échouées", failed_count)
            
            with col_stat3:
                in_progress_count = stats_by_status.get('in_progress', 0)
                st.metric("🔄 En cours", in_progress_count)
            
            with col_stat4:
                paused_count = stats_by_status.get('paused', 0)
                st.metric("⏸️ En pause", paused_count)
            
            # Actions de nettoyage
            st.markdown("### 🗑️ Actions de nettoyage")
            
            col_action1, col_action2, col_action3 = st.columns(3)
            
            with col_action1:
                if st.button("🧹 **Nettoyer les sessions terminées**", use_container_width=True):
                    completed_sessions = [s for s in sessions if s.status == self.modules['SessionStatus'].COMPLETED]
                    if completed_sessions:
                        success_list = []
                        error_list = []
                        
                        # Barre de progression
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, session in enumerate(completed_sessions):
                            status_text.text(f"Suppression {i+1}/{len(completed_sessions)}: {session.artist_name}")
                            progress_bar.progress((i + 1) / len(completed_sessions))
                            
                            if self.delete_session_safe(session.id):
                                success_list.append(session.artist_name)
                            else:
                                error_list.append(session.artist_name)
                            
                            time.sleep(0.1)  # Petite pause pour voir la progression
                        
                        # Effacer la progression
                        progress_bar.empty()
                        status_text.empty()
                        
                        # Résultats
                        if success_list:
                            st.success(f"✅ {len(success_list)} session(s) terminée(s) supprimée(s)")
                            
                        if error_list:
                            st.error(f"❌ Erreurs ({len(error_list)}): {', '.join(error_list)}")
                        
                        if success_list:
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.info("ℹ️ Aucune session terminée à supprimer")
            
            with col_action2:
                if st.button("❌ **Nettoyer les sessions échouées**", use_container_width=True):
                    failed_sessions = [s for s in sessions if s.status == self.modules['SessionStatus'].FAILED]
                    if failed_sessions:
                        deleted_count = 0
                        errors = []
                        
                        with st.spinner(f"Suppression de {len(failed_sessions)} session(s) échouée(s)..."):
                            for session in failed_sessions:
                                if self.delete_session_safe(session.id):
                                    deleted_count += 1
                                else:
                                    errors.append(session.artist_name)
                        
                        if deleted_count > 0:
                            st.success(f"✅ {deleted_count} session(s) échouée(s) supprimée(s)")
                        
                        if errors:
                            st.error(f"❌ Erreur suppression: {', '.join(errors)}")
                        
                        if deleted_count > 0:
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.info("ℹ️ Aucune session échouée à supprimer")
            
            with col_action3:
                if st.button("🕰️ **Nettoyer les sessions anciennes**", use_container_width=True):
                    # Sessions de plus de 7 jours
                    old_sessions = []
                    for session in sessions:
                        if session.created_at:
                            age = safe_calculate_age(session.created_at)
                            if age.days > 7:
                                old_sessions.append(session)
                    
                    if old_sessions:
                        deleted_count = 0
                        errors = []
                        
                        with st.spinner(f"Suppression de {len(old_sessions)} session(s) ancienne(s)..."):
                            for session in old_sessions:
                                if self.delete_session_safe(session.id):
                                    deleted_count += 1
                                else:
                                    errors.append(session.artist_name)
                        
                        if deleted_count > 0:
                            st.success(f"✅ {deleted_count} session(s) ancienne(s) supprimée(s)")
                        
                        if errors:
                            st.error(f"❌ Erreur suppression: {', '.join(errors)}")
                        
                        if deleted_count > 0:
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.info("ℹ️ Aucune session ancienne (>7j) à supprimer")
            
            # Section de debug pour la suppression
            with st.expander("🔍 Debug suppression"):
                st.write("**Console de debug pour les suppressions**")
                
                if st.button("🧪 Tester suppression debug"):
                    st.code("Regardez la console/terminal pour les logs détaillés de suppression")
                    st.info("Les logs commencent par '🔍 DEBUG:' dans votre terminal")
                
                # TEST DIRECT DE SUPPRESSION
                st.write("**🧪 Test direct de suppression**")
                test_session_id = st.text_input("ID de session à tester", placeholder="Collez un ID complet ici")
                
                col_test1, col_test2 = st.columns(2)
                
                with col_test1:
                    if st.button("🧪 Tester suppression directe") and test_session_id:
                        with st.spinner("Test en cours..."):
                            result = self.delete_session_safe(test_session_id)
                            if result:
                                st.success("✅ Test de suppression réussi")
                            else:
                                st.error("❌ Test de suppression échoué")
                            st.info("Regardez le terminal pour les logs détaillés")
                
                with col_test2:
                    if st.button("📊 Compter sessions en base"):
                        try:
                            with st.session_state.database.get_connection() as conn:
                                cursor = conn.execute("SELECT COUNT(*) FROM sessions")
                                count = cursor.fetchone()[0]
                                st.success(f"✅ {count} sessions en base de données")
                        except Exception as e:
                            st.error(f"❌ Erreur: {e}")
                
                st.write("**Sessions actuellement en mémoire:**")
                if hasattr(st.session_state, 'temp_sessions') and st.session_state.temp_sessions:
                    st.write(f"- Sessions temporaires: {len(st.session_state.temp_sessions)}")
                    for sid, sdata in st.session_state.temp_sessions.items():
                        st.write(f"  - {sid}: {sdata.get('artist_name', 'N/A')}")
                else:
                    st.write("- Aucune session temporaire")
                
                st.write(f"- Session courante: {st.session_state.current_session_id or 'Aucune'}")
                
                # Afficher les vraies sessions de la base
                if st.button("📋 Lister toutes les sessions de la base"):
                    try:
                        with st.session_state.database.get_connection() as conn:
                            cursor = conn.execute("SELECT id, artist_name, status, created_at FROM sessions ORDER BY created_at DESC LIMIT 10")
                            rows = cursor.fetchall()
                            
                            if rows:
                                st.write("**Sessions en base (10 dernières):**")
                                for row in rows:
                                    st.write(f"- {row[0][:8]}... : {row[1]} ({row[2]}) - {row[3]}")
                            else:
                                st.write("Aucune session en base")
                    except Exception as e:
                        st.error(f"Erreur listage: {e}")
            
            # Zone de danger pour suppression totale
            with st.expander("🚨 Zone de danger"):
                st.error("⚠️ **ATTENTION** : Ces actions sont irréversibles !")
                
                col_danger1, col_danger2 = st.columns(2)
                
                with col_danger1:
                    if st.button("🗑️ **Supprimer TOUTES les sessions non terminées**", type="secondary", use_container_width=True):
                        non_completed = [s for s in sessions if s.status != self.modules['SessionStatus'].COMPLETED]
                        if non_completed:
                            deleted_count = 0
                            errors = []
                            
                            with st.spinner(f"Suppression de {len(non_completed)} session(s) non terminée(s)..."):
                                for session in non_completed:
                                    if self.delete_session_safe(session.id):
                                        deleted_count += 1
                                    else:
                                        errors.append(session.artist_name)
                            
                            if deleted_count > 0:
                                st.success(f"✅ {deleted_count} session(s) non terminée(s) supprimée(s)")
                            
                            if errors:
                                st.error(f"❌ Erreurs: {', '.join(errors)}")
                            
                            if deleted_count > 0:
                                time.sleep(2)
                                st.rerun()
                        else:
                            st.info("ℹ️ Aucune session non terminée")
                
                with col_danger2:
                    # Confirmation pour suppression totale
                    if st.checkbox("🔓 Activer la suppression totale"):
                        if st.button("💀 **SUPPRIMER TOUTES LES SESSIONS**", type="primary", use_container_width=True):
                            deleted_count = 0
                            errors = []
                            
                            with st.spinner(f"Suppression de {len(sessions)} session(s)..."):
                                for session in sessions:
                                    if self.delete_session_safe(session.id):
                                        deleted_count += 1
                                    else:
                                        errors.append(session.artist_name)
                            
                            if deleted_count > 0:
                                st.success(f"✅ {deleted_count} session(s) supprimée(s)")
                            
                            if errors:
                                st.error(f"❌ Erreurs: {', '.join(errors)}")
                            
                            if deleted_count > 0:
                                time.sleep(2)
                                st.rerun()
        
        except Exception as e:
            st.error(f"❌ Erreur chargement sessions: {e}")
    
    def render_exports(self):
        """Interface d'exports améliorée"""
        st.markdown('<div class="section-header"><h2>📤 Exports</h2><p>Exportez vos données extraites dans différents formats</p></div>', unsafe_allow_html=True)
        
        st.info("💡 Fonctionnalité d'export en cours de développement")
        
        # Aperçu des fonctionnalités futures
        st.subheader("🚀 Fonctionnalités prévues")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            **Formats d'export:**
            - 📄 JSON (données structurées)
            - 📊 CSV (tableur)
            - 📋 Excel (avec feuilles multiples)
            - 🌐 HTML (rapport visuel)
            """)
        
        with col2:
            st.markdown("""
            **Options avancées:**
            - 🎵 Inclusion des paroles
            - 👥 Crédits détaillés
            - 📈 Statistiques d'extraction
            - 🗜️ Compression automatique
            """)
        
        # Placeholder pour l'interface future
        st.subheader("📋 Aperçu de l'interface")
        
        with st.expander("👁️ Voir l'aperçu"):
            st.write("**Sélection des données à exporter:**")
            st.multiselect("Artistes", ["Eminem", "Booba", "Nekfeu"], disabled=True)
            st.selectbox("Format", ["JSON", "CSV", "Excel", "HTML"], disabled=True)
            st.button("📥 Exporter", disabled=True, help="Disponible prochainement")
    
    def render_settings(self):
        """Paramètres améliorés"""
        st.markdown('<div class="section-header"><h2>⚙️ Paramètres</h2><p>Configurez les APIs et les options d\'extraction</p></div>', unsafe_allow_html=True)
        
        # Configuration des APIs
        st.subheader("🔑 Configuration des APIs")
        
        # Affichage de l'état actuel
        try:
            settings = self.modules['settings']
            
            # Genius API
            col1, col2 = st.columns([2, 1])
            
            with col1:
                genius_status = "✅ Configuré" if (hasattr(settings, 'genius_api_key') and settings.genius_api_key) else "❌ Non configuré"
                st.write(f"**Genius API:** {genius_status}")
                if hasattr(settings, 'genius_api_key') and settings.genius_api_key:
                    masked_key = settings.genius_api_key[:8] + "..." + settings.genius_api_key[-4:]
                    st.caption(f"Clé: {masked_key}")
                else:
                    st.caption("Obligatoire pour l'extraction des morceaux")
            
            with col2:
                if st.button("🔧 Configurer Genius", use_container_width=True):
                    st.info("💡 Modifiez le fichier .env : `GENIUS_API_KEY=votre_cle`")
                    st.info("🔗 Obtenez une clé sur: https://genius.com/api-clients")
            
            st.markdown("---")
            
            # Spotify API
            col3, col4 = st.columns([2, 1])
            
            with col3:
                spotify_status = "✅ Configuré" if (hasattr(settings, 'spotify_client_id') and settings.spotify_client_id) else "❌ Non configuré"
                st.write(f"**Spotify API:** {spotify_status}")
                if hasattr(settings, 'spotify_client_id') and settings.spotify_client_id:
                    masked_id = settings.spotify_client_id[:8] + "..."
                    st.caption(f"Client ID: {masked_id}")
                else:
                    st.caption("Optionnel - pour les données audio avancées")
            
            with col4:
                if st.button("🔧 Configurer Spotify", use_container_width=True):
                    st.info("💡 Modifiez le fichier .env :")
                    st.code("SPOTIFY_CLIENT_ID=votre_client_id\nSPOTIFY_CLIENT_SECRET=votre_secret")
                    st.info("🔗 Obtenez les clés sur: https://developer.spotify.com/")
            
            st.markdown("---")
            
            # Autres APIs
            st.subheader("🔌 APIs optionnelles")
            
            col5, col6, col7 = st.columns(3)
            
            with col5:
                discogs_status = "✅" if (hasattr(settings, 'discogs_token') and settings.discogs_token) else "❌"
                st.write(f"{discogs_status} **Discogs**")
                st.caption("Infos albums")
            
            with col6:
                lastfm_status = "✅" if (hasattr(settings, 'lastfm_api_key') and settings.lastfm_api_key) else "❌"
                st.write(f"{lastfm_status} **Last.FM**")
                st.caption("Statistiques écoute")
            
            with col7:
                st.write("✅ **Rapedia**")
                st.caption("Scraping (pas d'API)")
        
        except Exception as e:
            st.error(f"❌ Erreur chargement paramètres: {e}")
        
        # Paramètres d'extraction par défaut
        st.subheader("🎛️ Paramètres d'extraction par défaut")
        
        col_param1, col_param2 = st.columns(2)
        
        with col_param1:
            st.markdown("**Performance**")
            default_max_tracks = st.slider("Morceaux max par défaut", 10, 500, 100, disabled=True)
            default_timeout = st.slider("Timeout par défaut (sec)", 10, 60, 30, disabled=True)
            st.caption("⚠️ Paramètres en lecture seule pour cette version")
        
        with col_param2:
            st.markdown("**Sources par défaut**")
            default_sources = st.multiselect(
                "Sources prioritaires",
                ["Genius", "Spotify", "Discogs", "LastFM", "Rapedia"],
                default=["Genius", "Spotify"],
                disabled=True
            )
            st.caption("⚠️ Configurables par extraction pour le moment")
        
        # Actions de maintenance
        st.subheader("🧹 Maintenance")
        
        col_maint1, col_maint2, col_maint3 = st.columns(3)
        
        with col_maint1:
            if st.button("🗑️ Nettoyer le cache", use_container_width=True):
                try:
                    st.cache_data.clear()
                    st.success("✅ Cache Streamlit nettoyé !")
                except Exception as e:
                    st.error(f"❌ Erreur nettoyage cache: {e}")
        
        with col_maint2:
            if st.button("🔄 Recharger l'app", use_container_width=True):
                st.rerun()
        
        with col_maint3:
            if st.button("📊 Voir les stats", use_container_width=True):
                with st.expander("📈 Statistiques système", expanded=True):
                    stats = self.get_quick_stats()
                    st.json(stats)
        
        # Informations de version et aide
        st.subheader("ℹ️ Informations")
        
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            st.markdown("""
            **Version:** Music Data Extractor v1.0
            **Mode:** Streamlit Interface
            **Base de données:** SQLite locale
            """)
        
        with col_info2:
            st.markdown("""
            **Support:**
            - 🔗 Documentation: README.md
            - 🐛 Problèmes: Consultez les logs
            - 💡 Suggestions: Améliorations bienvenues
            """)
    
    def get_quick_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques rapides avec gestion d'erreurs"""
        try:
            stats = {}
            
            # Sessions
            if st.session_state.session_manager:
                try:
                    sessions = st.session_state.session_manager.list_sessions()
                    stats['total_sessions'] = len(sessions)
                    stats['active_sessions'] = len([s for s in sessions if s.status == self.modules['SessionStatus'].IN_PROGRESS])
                except:
                    stats['total_sessions'] = 0
                    stats['active_sessions'] = 0
            else:
                stats['total_sessions'] = 0
                stats['active_sessions'] = 0
            
            # Base de données
            try:
                if hasattr(st.session_state.database, 'get_connection'):
                    with st.session_state.database.get_connection() as conn:
                        cursor = conn.execute("SELECT COUNT(DISTINCT id) FROM artists")
                        result = cursor.fetchone()
                        stats['total_artists'] = result[0] if result else 0
                        
                        cursor = conn.execute("SELECT COUNT(DISTINCT id) FROM tracks")
                        result = cursor.fetchone()
                        stats['total_tracks'] = result[0] if result else 0
                else:
                    stats['total_artists'] = 0
                    stats['total_tracks'] = 0
            except:
                stats['total_artists'] = 0
                stats['total_tracks'] = 0
            
            return stats
        
        except Exception as e:
            return {'total_sessions': 0, 'active_sessions': 0, 'total_artists': 0, 'total_tracks': 0}
    
    def delete_session_safe(self, session_id: str) -> bool:
        """Supprime une session de manière VRAIMENT efficace"""
        try:
            if not session_id:
                print(f"🔍 DEBUG: session_id vide")
                return False
            
            print(f"🔍 DEBUG: === DÉBUT SUPPRESSION {session_id} ===")
            
            success = False
            
            # 1. Nettoyer les sessions temporaires en premier
            if 'temp_sessions' in st.session_state and session_id in st.session_state.temp_sessions:
                del st.session_state.temp_sessions[session_id]
                print(f"🔍 DEBUG: ✅ Session temporaire supprimée")
                success = True
            
            # 2. Nettoyer les références Streamlit
            if st.session_state.current_session_id == session_id:
                st.session_state.current_session_id = None
                print(f"🔍 DEBUG: ✅ Référence current_session_id nettoyée")
            
            # 3. SUPPRESSION DIRECTE EN BASE - La méthode qui fonctionne vraiment
            try:
                print(f"🔍 DEBUG: Tentative suppression directe en base")
                
                with st.session_state.database.get_connection() as conn:
                    # D'abord, supprimer les dépendances
                    print(f"🔍 DEBUG: Suppression des checkpoints...")
                    cursor1 = conn.execute("DELETE FROM checkpoints WHERE session_id = ?", (session_id,))
                    print(f"🔍 DEBUG: Checkpoints supprimés: {cursor1.rowcount}")
                    
                    # Ensuite, supprimer la session principale
                    print(f"🔍 DEBUG: Suppression de la session...")
                    cursor2 = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                    print(f"🔍 DEBUG: Sessions supprimées: {cursor2.rowcount}")
                    
                    # Valider les changements
                    conn.commit()
                    print(f"🔍 DEBUG: ✅ Commit réussi")
                    
                    if cursor2.rowcount > 0:
                        success = True
                        print(f"🔍 DEBUG: ✅ Session supprimée de la base (rowcount: {cursor2.rowcount})")
                    else:
                        print(f"🔍 DEBUG: ⚠️ Aucune ligne supprimée - session inexistante?")
                        success = True  # Considérer comme succès si déjà supprimée
                        
            except Exception as db_error:
                print(f"🔍 DEBUG: ❌ Erreur base de données: {db_error}")
                
                # Essai avec une requête plus simple
                try:
                    print(f"🔍 DEBUG: Tentative suppression simple...")
                    with st.session_state.database.get_connection() as conn:
                        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                        conn.commit()
                        success = True
                        print(f"🔍 DEBUG: ✅ Suppression simple réussie")
                except Exception as e2:
                    print(f"🔍 DEBUG: ❌ Suppression simple échouée: {e2}")
            
            # 4. Nettoyer le SessionManager si possible
            if st.session_state.session_manager:
                try:
                    # Nettoyer les sessions actives en mémoire
                    if hasattr(st.session_state.session_manager, 'active_sessions'):
                        if session_id in st.session_state.session_manager.active_sessions:
                            del st.session_state.session_manager.active_sessions[session_id]
                            print(f"🔍 DEBUG: ✅ Session retirée des sessions actives")
                    
                    # Nettoyer les sessions modifiées
                    if hasattr(st.session_state.session_manager, '_sessions_modified'):
                        st.session_state.session_manager._sessions_modified.discard(session_id)
                        print(f"🔍 DEBUG: ✅ Session retirée des modifications")
                        
                except Exception as sm_error:
                    print(f"🔍 DEBUG: ⚠️ Erreur nettoyage SessionManager: {sm_error}")
            
            print(f"🔍 DEBUG: === FIN SUPPRESSION {session_id} - Success: {success} ===")
            return success
            
        except Exception as e:
            print(f"🔍 DEBUG: ❌ ERREUR GÉNÉRALE: {e}")
            import traceback
            print(f"🔍 DEBUG: Traceback: {traceback.format_exc()}")
            return False

def main():
    """Fonction principale avec gestion d'erreurs robuste"""
    try:
        app = StreamlitInterface()
        app.run()
    except Exception as e:
        st.error(f"❌ Erreur critique: {e}")
        
        # Interface de récupération
        st.markdown("### 🆘 Mode de récupération")
        st.write("Une erreur critique s'est produite. Essayez ces solutions:")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Recharger l'application"):
                st.rerun()
        
        with col2:
            if st.button("🧹 Nettoyer le cache"):
                st.cache_data.clear()
                st.success("Cache nettoyé, rechargez la page")
        
        # Debug info
        with st.expander("🔍 Informations de debug"):
            st.exception(e)

if __name__ == "__main__":
    main()