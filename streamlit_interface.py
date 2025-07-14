# streamlit_app.py - Interface graphique pour Music Data Extractor
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

# Imports des modules du projet (à adapter selon votre structure)
try:
    from config.settings import settings
    from core.database import Database
    from core.session_manager import get_session_manager
    from steps.step1_discover import DiscoveryStep
    from steps.step2_extract import ExtractionStep
    from utils.export_utils import ExportManager, ExportFormat
    from models.enums import SessionStatus, ExtractionStatus
except ImportError as e:
    st.error(f"Erreur d'import des modules: {e}")
    st.stop()

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
    
    .stButton > button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500;
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
    """Interface Streamlit pour Music Data Extractor"""
    
    def __init__(self):
        # Initialisation des composants
        if 'database' not in st.session_state:
            st.session_state.database = Database()
        
        if 'session_manager' not in st.session_state:
            st.session_state.session_manager = get_session_manager()
        
        if 'discovery_step' not in st.session_state:
            st.session_state.discovery_step = DiscoveryStep()
        
        if 'extraction_step' not in st.session_state:
            st.session_state.extraction_step = ExtractionStep()
        
        if 'export_manager' not in st.session_state:
            st.session_state.export_manager = ExportManager()
        
        # État de l'interface
        if 'current_session_id' not in st.session_state:
            st.session_state.current_session_id = None
        
        if 'auto_refresh' not in st.session_state:
            st.session_state.auto_refresh = False
    
    def run(self):
        """Lance l'interface principale"""
        # Header
        st.markdown("""
        <div class="main-header">
            <h1>🎵 Music Data Extractor</h1>
            <p>Extraction complète de données musicales avec crédits détaillés</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Sidebar pour la navigation
        self.render_sidebar()
        
        # Page principale selon la sélection
        page = st.session_state.get('current_page', 'dashboard')
        
        if page == 'dashboard':
            self.render_dashboard()
        elif page == 'new_extraction':
            self.render_new_extraction()
        elif page == 'sessions':
            self.render_sessions()
        elif page == 'exports':
            self.render_exports()
        elif page == 'settings':
            self.render_settings()
    
    def render_sidebar(self):
        """Affiche la sidebar de navigation"""
        with st.sidebar:
            st.image("https://via.placeholder.com/200x100/667eea/white?text=Music+Data", width=200)
            
            st.markdown("### Navigation")
            
            # Menu principal
            pages = {
                'dashboard': '📊 Tableau de bord',
                'new_extraction': '🆕 Nouvelle extraction',
                'sessions': '📝 Sessions',
                'exports': '📤 Exports',
                'settings': '⚙️ Paramètres'
            }
            
            for page_key, page_name in pages.items():
                if st.button(page_name, key=f"nav_{page_key}"):
                    st.session_state.current_page = page_key
                    st.rerun()
            
            st.markdown("---")
            
            # Statistiques rapides
            st.markdown("### Statistiques rapides")
            stats = self.get_quick_stats()
            
            st.metric("Sessions actives", stats.get('active_sessions', 0))
            st.metric("Artistes traités", stats.get('total_artists', 0))
            st.metric("Morceaux extraits", stats.get('total_tracks', 0))
            
            st.markdown("---")
            
            # Session en cours
            if st.session_state.current_session_id:
                st.markdown("### Session en cours")
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
            
            # Auto-refresh
            st.markdown("---")
            auto_refresh = st.checkbox("🔄 Actualisation auto (10s)", value=st.session_state.auto_refresh)
            st.session_state.auto_refresh = auto_refresh
            
            if auto_refresh:
                time.sleep(10)
                st.rerun()
    
    def render_dashboard(self):
        """Affiche le tableau de bord principal"""
        st.markdown("## 📊 Tableau de bord")
        
        # Métriques principales
        col1, col2, col3, col4 = st.columns(4)
        
        stats = self.get_detailed_stats()
        
        with col1:
            st.metric(
                "Sessions totales",
                stats.get('total_sessions', 0),
                delta=stats.get('sessions_this_week', 0)
            )
        
        with col2:
            st.metric(
                "Artistes traités",
                stats.get('total_artists', 0),
                delta=stats.get('new_artists_this_week', 0)
            )
        
        with col3:
            st.metric(
                "Morceaux extraits",
                stats.get('total_tracks', 0),
                delta=stats.get('tracks_this_week', 0)
            )
        
        with col4:
            st.metric(
                "Crédits collectés",
                stats.get('total_credits', 0),
                delta=stats.get('credits_this_week', 0)
            )
        
        # Graphiques
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📈 Sessions par statut")
            self.render_sessions_chart()
        
        with col2:
            st.markdown("### 🎵 Top artistes")
            self.render_top_artists_chart()
        
        # Sessions récentes
        st.markdown("### 🕒 Sessions récentes")
        self.render_recent_sessions()
        
        # Alertes et notifications
        self.render_alerts()
    
    def render_new_extraction(self):
        """Interface pour créer une nouvelle extraction"""
        st.markdown("## 🆕 Nouvelle extraction")
        
        with st.form("new_extraction_form"):
            st.markdown("### Configuration de l'extraction")
            
            # Saisie de l'artiste
            artist_name = st.text_input(
                "Nom de l'artiste",
                placeholder="Ex: Nekfeu, Orelsan, PNL...",
                help="Nom de l'artiste rap/hip-hop à analyser"
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                max_tracks = st.number_input(
                    "Nombre maximum de morceaux",
                    min_value=10,
                    max_value=500,
                    value=200,
                    step=10,
                    help="Limite le nombre de morceaux à traiter"
                )
                
                enable_lyrics = st.checkbox(
                    "Extraire les paroles",
                    value=False,
                    help="Ajoute l'extraction des paroles (plus lent)"
                )
            
            with col2:
                priority_sources = st.multiselect(
                    "Sources prioritaires",
                    ["Genius", "Spotify", "Discogs", "Rapedia"],
                    default=["Genius", "Spotify"],
                    help="Sources de données à utiliser en priorité"
                )
                
                force_refresh = st.checkbox(
                    "Forcer le rafraîchissement",
                    value=False,
                    help="Ignore le cache et relance tout"
                )
            
            st.markdown("### Options avancées")
            
            with st.expander("⚙️ Paramètres détaillés"):
                col1, col2 = st.columns(2)
                
                with col1:
                    batch_size = st.slider("Taille des lots", 5, 50, 10)
                    max_workers = st.slider("Threads parallèles", 1, 8, 3)
                
                with col2:
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
    
    def render_sessions(self):
        """Affiche la gestion des sessions"""
        st.markdown("## 📝 Gestion des sessions")
        
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
        
        # Liste des sessions
        sessions = self.get_filtered_sessions(status_filter, date_filter)
        
        if not sessions:
            st.info("Aucune session trouvée avec ces critères.")
            return
        
        for session in sessions:
            self.render_session_card(session)
    
    def render_exports(self):
        """Interface pour gérer les exports"""
        st.markdown("## 📤 Gestion des exports")
        
        # Export d'une session existante
        st.markdown("### Exporter une session")
        
        # Sélection de session
        sessions = st.session_state.session_manager.list_sessions(SessionStatus.COMPLETED)
        
        if not sessions:
            st.warning("Aucune session terminée disponible pour l'export.")
            return
        
        session_options = {f"{s.artist_name} ({s.id[:8]})": s.id for s in sessions}
        selected_session_name = st.selectbox("Choisir une session", list(session_options.keys()))
        
        if selected_session_name:
            selected_session_id = session_options[selected_session_name]
            session = st.session_state.session_manager.get_session(selected_session_id)
            
            col1, col2 = st.columns(2)
            
            with col1:
                export_format = st.selectbox(
                    "Format d'export",
                    ["JSON", "CSV", "Excel", "HTML", "XML"]
                )
                
                include_lyrics = st.checkbox("Inclure les paroles", True)
                include_raw_data = st.checkbox("Inclure les données brutes", False)
            
            with col2:
                custom_filename = st.text_input(
                    "Nom de fichier personnalisé (optionnel)",
                    placeholder=f"{session.artist_name}_export"
                )
                
                if st.button(f"📥 Exporter en {export_format}", use_container_width=True):
                    self.perform_export(
                        selected_session_id,
                        export_format,
                        custom_filename,
                        include_lyrics,
                        include_raw_data
                    )
        
        st.markdown("---")
        
        # Liste des exports existants
        st.markdown("### 📁 Exports existants")
        self.render_exports_list()
    
    def render_settings(self):
        """Interface des paramètres"""
        st.markdown("## ⚙️ Paramètres")
        
        # Configuration des APIs
        st.markdown("### 🔑 Clés API")
        
        with st.expander("Configuration des APIs"):
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
            
            discogs_token = st.text_input(
                "Token Discogs",
                value=settings.discogs_token or "",
                type="password",
                help="Optionnel - pour les informations d'albums"
            )
        
        # Paramètres d'extraction
        st.markdown("### ⚙️ Paramètres d'extraction")
        
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
        
        # Bouton de sauvegarde
        if st.button("💾 Sauvegarder les paramètres", use_container_width=True):
            st.success("Paramètres sauvegardés !")
            # Ici vous pourriez implémenter la sauvegarde réelle
        
        # Statistiques du système
        st.markdown("### 📊 Statistiques système")
        
        system_stats = self.get_system_stats()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Taille de la base", f"{system_stats.get('db_size_mb', 0):.1f} MB")
        
        with col2:
            st.metric("Taille du cache", f"{system_stats.get('cache_size_mb', 0):.1f} MB")
        
        with col3:
            st.metric("Exports créés", system_stats.get('exports_count', 0))
        
        # Actions de maintenance
        st.markdown("### 🧹 Maintenance")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🗑️ Nettoyer le cache"):
                # Implémentation du nettoyage
                st.success("Cache nettoyé !")
        
        with col2:
            if st.button("📦 Nettoyer les exports anciens"):
                count = st.session_state.export_manager.cleanup_old_exports(30)
                st.success(f"{count} export(s) supprimé(s)")
        
        with col3:
            if st.button("🔄 Vérifier les sessions"):
                # Implémentation de la vérification
                st.success("Sessions vérifiées !")
    
    def start_extraction(self, **kwargs):
        """Lance une nouvelle extraction"""
        try:
            artist_name = kwargs['artist_name']
            
            # Création de la session
            session_id = st.session_state.session_manager.create_session(
                artist_name,
                metadata={
                    'max_tracks': kwargs.get('max_tracks', 200),
                    'enable_lyrics': kwargs.get('enable_lyrics', False),
                    'sources': kwargs.get('priority_sources', []),
                    'started_from': 'streamlit_interface'
                }
            )
            
            st.session_state.current_session_id = session_id
            
            # Progression avec placeholder
            progress_placeholder = st.empty()
            status_placeholder = st.empty()
            
            with progress_placeholder.container():
                st.info(f"🚀 Extraction lancée pour {artist_name}")
                progress_bar = st.progress(0)
                status_text = st.empty()
            
            # Étape 1: Découverte
            status_text.text("🔍 Découverte des morceaux...")
            
            tracks, discovery_stats = st.session_state.discovery_step.discover_artist_tracks(
                artist_name,
                session_id=session_id,
                max_tracks=kwargs.get('max_tracks', 200)
            )
            
            progress_bar.progress(0.3)
            
            if not tracks:
                st.error("Aucun morceau trouvé pour cet artiste.")
                return
            
            # Étape 2: Extraction
            status_text.text("🎵 Extraction des données détaillées...")
            
            enriched_tracks, extraction_stats = st.session_state.extraction_step.extract_tracks_data(
                session_id,
                force_refresh=kwargs.get('force_refresh', False)
            )
            
            progress_bar.progress(1.0)
            
            # Fin de session
            st.session_state.session_manager.complete_session(
                session_id,
                {
                    'discovery_stats': discovery_stats.__dict__,
                    'extraction_stats': extraction_stats.__dict__
                }
            )
            
            # Affichage des résultats
            progress_placeholder.empty()
            
            st.success(f"✅ Extraction terminée pour {artist_name} !")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Morceaux trouvés", discovery_stats.final_count)
            
            with col2:
                st.metric("Extractions réussies", extraction_stats.successful_extractions)
            
            with col3:
                st.metric("Morceaux avec crédits", extraction_stats.tracks_with_credits)
            
            # Bouton pour voir les résultats
            if st.button("📊 Voir les résultats détaillés"):
                st.session_state.current_page = 'sessions'
                st.rerun()
        
        except Exception as e:
            st.error(f"Erreur lors de l'extraction: {str(e)}")
            if st.session_state.current_session_id:
                st.session_state.session_manager.fail_session(
                    st.session_state.current_session_id,
                    str(e)
                )
    
    def get_quick_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques rapides"""
        try:
            active_sessions = len(st.session_state.session_manager.get_active_sessions())
            db_stats = st.session_state.database.get_stats()
            
            return {
                'active_sessions': active_sessions,
                'total_artists': db_stats.get('total_artists', 0),
                'total_tracks': db_stats.get('total_tracks', 0)
            }
        except Exception:
            return {'active_sessions': 0, 'total_artists': 0, 'total_tracks': 0}
    
    def get_detailed_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques détaillées"""
        # Implémentation simplifiée - à adapter selon vos besoins
        return {
            'total_sessions': 0,
            'sessions_this_week': 0,
            'total_artists': 0,
            'new_artists_this_week': 0,
            'total_tracks': 0,
            'tracks_this_week': 0,
            'total_credits': 0,
            'credits_this_week': 0
        }
    
    def render_sessions_chart(self):
        """Affiche le graphique des sessions par statut"""
        # Données d'exemple - à remplacer par de vraies données
        data = {
            'Statut': ['En cours', 'Terminées', 'Échouées', 'En pause'],
            'Nombre': [2, 15, 3, 1]
        }
        
        fig = px.pie(
            data,
            values='Nombre',
            names='Statut',
            color_discrete_sequence=['#17a2b8', '#28a745', '#dc3545', '#ffc107']
        )
        
        fig.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)
    
    def render_top_artists_chart(self):
        """Affiche le graphique des top artistes"""
        # Données d'exemple - à remplacer par de vraies données
        data = {
            'Artiste': ['Nekfeu', 'Orelsan', 'PNL', 'Damso', 'Ninho'],
            'Morceaux': [45, 38, 32, 28, 25]
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
    
    def render_recent_sessions(self):
        """Affiche les sessions récentes"""
        sessions = st.session_state.session_manager.list_sessions()[:5]
        
        if not sessions:
            st.info("Aucune session récente.")
            return
        
        for session in sessions:
            self.render_session_card(session)
    
    def render_session_card(self, session):
        """Affiche une carte de session"""
        status_class = f"status-{session.status.value.replace('_', '-')}"
        
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                st.markdown(f"**{session.artist_name}**")
                st.caption(f"ID: {session.id[:8]}")
            
            with col2:
                st.markdown(f'<span class="status-badge {status_class}">{session.status.value}</span>', 
                           unsafe_allow_html=True)
                if session.current_step:
                    st.caption(session.current_step)
            
            with col3:
                if session.total_tracks_found > 0:
                    progress = session.tracks_processed / session.total_tracks_found
                    st.progress(progress)
                    st.caption(f"{session.tracks_processed}/{session.total_tracks_found}")
                else:
                    st.caption("En initialisation")
            
            with col4:
                if st.button("👁️", key=f"view_{session.id}", help="Voir détails"):
                    self.show_session_details(session)
        
        st.markdown("---")
    
    def show_session_details(self, session):
        """Affiche les détails d'une session dans un modal"""
        with st.expander(f"📋 Détails - {session.artist_name}", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Informations générales**")
                st.write(f"ID: {session.id}")
                st.write(f"Artiste: {session.artist_name}")
                st.write(f"Statut: {session.status.value}")
                st.write(f"Étape: {session.current_step or 'N/A'}")
                
                if session.created_at:
                    st.write(f"Créée: {session.created_at.strftime('%d/%m/%Y %H:%M')}")
                if session.updated_at:
                    st.write(f"Mise à jour: {session.updated_at.strftime('%d/%m/%Y %H:%M')}")
            
            with col2:
                st.markdown("**Progression**")
                st.write(f"Morceaux trouvés: {session.total_tracks_found}")
                st.write(f"Morceaux traités: {session.tracks_processed}")
                st.write(f"Avec crédits: {session.tracks_with_credits}")
                st.write(f"Avec albums: {session.tracks_with_albums}")
                
                if session.total_tracks_found > 0:
                    progress_pct = (session.tracks_processed / session.total_tracks_found) * 100
                    st.progress(progress_pct / 100)
                    st.write(f"Progression: {progress_pct:.1f}%")
            
            # Actions disponibles
            st.markdown("**Actions**")
            action_col1, action_col2, action_col3 = st.columns(3)
            
            with action_col1:
                if session.status == SessionStatus.IN_PROGRESS:
                    if st.button("⏸️ Pause", key=f"pause_{session.id}"):
                        st.session_state.session_manager.pause_session(session.id)
                        st.rerun()
                elif session.status == SessionStatus.PAUSED:
                    if st.button("▶️ Reprendre", key=f"resume_{session.id}"):
                        st.session_state.session_manager.resume_session(session.id)
                        st.rerun()
            
            with action_col2:
                if session.status == SessionStatus.COMPLETED:
                    if st.button("📤 Exporter", key=f"export_{session.id}"):
                        st.session_state.export_session_id = session.id
                        st.session_state.current_page = 'exports'
                        st.rerun()
            
            with action_col3:
                if st.button("🗑️ Supprimer", key=f"delete_{session.id}"):
                    # Confirmation avant suppression
                    if st.checkbox(f"Confirmer suppression {session.id[:8]}", key=f"confirm_{session.id}"):
                        # Implémentation de la suppression
                        st.success("Session supprimée")
                        st.rerun()
    
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
    
    def perform_export(self, session_id: str, export_format: str, filename: str, include_lyrics: bool, include_raw_data: bool):
        """Effectue l'export d'une session"""
        try:
            # Récupération des données
            session = st.session_state.session_manager.get_session(session_id)
            artist = st.session_state.database.get_artist_by_name(session.artist_name)
            tracks = st.session_state.database.get_tracks_by_artist_id(artist.id)
            
            # Options d'export
            options = {
                'include_lyrics': include_lyrics,
                'include_raw_data': include_raw_data
            }
            
            # Export
            export_format_enum = ExportFormat(export_format.lower())
            filepath = st.session_state.export_manager.export_artist_data(
                artist=artist,
                tracks=tracks,
                format=export_format_enum,
                filename=filename or None,
                options=options
            )
            
            st.success(f"✅ Export créé: {filepath}")
            
            # Bouton de téléchargement
            with open(filepath, 'rb') as f:
                st.download_button(
                    label=f"📥 Télécharger {export_format}",
                    data=f.read(),
                    file_name=filepath.split('/')[-1],
                    mime=self.get_mime_type(export_format)
                )
                
        except Exception as e:
            st.error(f"Erreur lors de l'export: {str(e)}")
    
    def get_mime_type(self, format: str) -> str:
        """Retourne le type MIME pour un format"""
        mime_types = {
            'JSON': 'application/json',
            'CSV': 'text/csv',
            'Excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'HTML': 'text/html',
            'XML': 'application/xml'
        }
        return mime_types.get(format, 'application/octet-stream')
    
    def render_exports_list(self):
        """Affiche la liste des exports existants"""
        try:
            exports = st.session_state.export_manager.list_exports()
            
            if not exports:
                st.info("Aucun export trouvé.")
                return
            
            # Tableau des exports
            df = pd.DataFrame(exports)
            df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%d/%m/%Y %H:%M')
            df['size_display'] = df['size_mb'].apply(lambda x: f"{x:.1f} MB")
            
            # Affichage avec sélection
            selected_indices = st.multiselect(
                "Sélectionner des exports",
                range(len(df)),
                format_func=lambda i: f"{df.iloc[i]['filename']} ({df.iloc[i]['size_display']})"
            )
            
            # Actions en lot
            if selected_indices:
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("📥 Télécharger sélectionnés"):
                        for idx in selected_indices:
                            export = exports[idx]
                            with open(export['path'], 'rb') as f:
                                st.download_button(
                                    label=f"📥 {export['filename']}",
                                    data=f.read(),
                                    file_name=export['filename'],
                                    key=f"download_{idx}"
                                )
                
                with col2:
                    if st.button("🗑️ Supprimer sélectionnés"):
                        for idx in selected_indices:
                            try:
                                import os
                                os.remove(exports[idx]['path'])
                            except Exception as e:
                                st.error(f"Erreur suppression: {e}")
                        st.success(f"{len(selected_indices)} export(s) supprimé(s)")
                        st.rerun()
            
            # Tableau d'affichage
            display_df = df[['filename', 'format', 'size_display', 'created_at']].copy()
            display_df.columns = ['Fichier', 'Format', 'Taille', 'Créé le']
            
            st.dataframe(display_df, use_container_width=True)
            
        except Exception as e:
            st.error(f"Erreur lors de l'affichage des exports: {e}")
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques système"""
        try:
            # Taille de la base de données
            db_path = st.session_state.database.db_path
            import os
            db_size_mb = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0
            
            # Statistiques des exports
            export_stats = st.session_state.export_manager.get_stats()
            
            return {
                'db_size_mb': db_size_mb,
                'cache_size_mb': 0,  # À implémenter selon votre cache
                'exports_count': export_stats.get('exports_created', 0)
            }
        except Exception:
            return {'db_size_mb': 0, 'cache_size_mb': 0, 'exports_count': 0}
    
    def render_alerts(self):
        """Affiche les alertes et notifications"""
        st.markdown("### 🚨 Alertes")
        
        # Vérification des clés API
        alerts = []
        
        if not settings.genius_api_key:
            alerts.append({
                'type': 'error',
                'message': 'Clé API Genius manquante - extraction limitée',
                'action': 'Configurer dans Paramètres'
            })
        
        if not settings.spotify_client_id:
            alerts.append({
                'type': 'warning', 
                'message': 'Spotify non configuré - pas de données BPM',
                'action': 'Configurer dans Paramètres'
            })
        
        # Sessions échouées récentes
        failed_sessions = [s for s in st.session_state.session_manager.list_sessions(SessionStatus.FAILED)]
        if failed_sessions:
            alerts.append({
                'type': 'warning',
                'message': f'{len(failed_sessions)} session(s) échouée(s) récemment',
                'action': 'Voir Sessions'
            })
        
        # Affichage des alertes
        if alerts:
            for alert in alerts:
                if alert['type'] == 'error':
                    st.error(f"❌ {alert['message']} - {alert['action']}")
                elif alert['type'] == 'warning':
                    st.warning(f"⚠️ {alert['message']} - {alert['action']}")
                else:
                    st.info(f"ℹ️ {alert['message']} - {alert['action']}")
        else:
            st.success("✅ Tout fonctionne correctement !")


# Interface de progression en temps réel
class ProgressTracker:
    """Suivi de progression en temps réel"""
    
    def __init__(self):
        self.placeholder = st.empty()
        self.last_update = time.time()
    
    def update(self, session_id: str, force: bool = False):
        """Met à jour l'affichage de progression"""
        now = time.time()
        if not force and now - self.last_update < 2:  # Limite à une mise à jour toutes les 2 secondes
            return
        
        try:
            session = st.session_state.session_manager.get_session(session_id)
            if not session:
                return
            
            with self.placeholder.container():
                st.markdown(f"### 🎵 Extraction en cours - {session.artist_name}")
                
                # Barre de progression principale
                if session.total_tracks_found > 0:
                    progress = session.tracks_processed / session.total_tracks_found
                    st.progress(progress)
                    st.write(f"Progression: {session.tracks_processed}/{session.total_tracks_found} morceaux ({progress*100:.1f}%)")
                
                # Détails par étape
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("🔍 Découverts", session.total_tracks_found)
                
                with col2:
                    st.metric("✅ Traités", session.tracks_processed)
                
                with col3:
                    st.metric("🎵 Avec crédits", session.tracks_with_credits)
                
                # Statut actuel
                if session.current_step:
                    st.info(f"📍 Étape actuelle: {session.current_step}")
                
                # Temps écoulé
                if session.created_at:
                    elapsed = datetime.now() - session.created_at
                    st.caption(f"⏱️ Temps écoulé: {str(elapsed).split('.')[0]}")
                
                # Estimation du temps restant
                if session.total_tracks_found > 0 and session.tracks_processed > 0:
                    remaining_tracks = session.total_tracks_found - session.tracks_processed
                    if remaining_tracks > 0 and elapsed.total_seconds() > 0:
                        avg_time_per_track = elapsed.total_seconds() / session.tracks_processed
                        eta_seconds = remaining_tracks * avg_time_per_track
                        eta = timedelta(seconds=int(eta_seconds))
                        st.caption(f"⏳ Temps estimé restant: {str(eta)}")
                
                self.last_update = now
                
        except Exception as e:
            st.error(f"Erreur mise à jour progression: {e}")


def main():
    """Fonction principale de l'application Streamlit"""
    try:
        # Initialisation de l'interface
        app = StreamlitInterface()
        
        # Lancement de l'interface
        app.run()
        
        # Suivi automatique de la progression si session active
        if (st.session_state.get('current_session_id') and 
            st.session_state.get('auto_refresh', False)):
            
            session = st.session_state.session_manager.get_session(st.session_state.current_session_id)
            if session and session.status == SessionStatus.IN_PROGRESS:
                progress_tracker = ProgressTracker()
                progress_tracker.update(st.session_state.current_session_id, force=True)
        
    except Exception as e:
        st.error(f"Erreur critique de l'application: {e}")
        st.exception(e)
        
        # Interface de debug
        with st.expander("🐛 Informations de debug"):
            st.write("Variables de session:")
            st.json(dict(st.session_state))
            
            st.write("Configuration:")
            try:
                st.json({
                    'genius_key_present': bool(settings.genius_api_key),
                    'spotify_configured': bool(settings.spotify_client_id),
                    'data_dir': str(settings.data_dir)
                })
            except Exception as debug_e:
                st.error(f"Erreur debug config: {debug_e}")


if __name__ == "__main__":
    main()