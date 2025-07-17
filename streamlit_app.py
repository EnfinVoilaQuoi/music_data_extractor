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

# CSS personnalisé simplifié
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
        
        # Sidebar avec menu
        with st.sidebar:
            st.markdown("### 📱 Navigation")
            page = st.radio(
                "Menu",
                ["🏠 Dashboard", "🔍 Nouvelle extraction", "📝 Sessions", "📤 Exports", "⚙️ Paramètres"],
                label_visibility="collapsed"
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
            st.markdown("### 📊 Système")
            st.success("✅ Base de données connectée")
            
            # Sessions si disponibles
            if st.session_state.session_manager:
                try:
                    sessions = st.session_state.session_manager.list_sessions()
                    active_sessions = len([s for s in sessions if s.status == self.modules['SessionStatus'].IN_PROGRESS])
                    st.info(f"🔄 {active_sessions} session(s) active(s)")
                except Exception as e:
                    st.warning("⚠️ Sessions non disponibles")
            
            # Métriques rapides
            stats = self.get_quick_stats()
            if stats:
                st.metric("Artistes", stats.get('total_artists', 0))
                st.metric("Morceaux", stats.get('total_tracks', 0))
                
        except Exception as e:
            st.error(f"❌ Erreur sidebar: {e}")
    
    def render_new_extraction(self):
        """Interface pour nouvelle extraction - Version simplifiée"""
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
                    value=100
                )
            
            # Options simples
            with st.expander("🔧 Options"):
                enable_lyrics = st.checkbox("Inclure les paroles", True)
                include_features = st.checkbox("Inclure les featuring", True)
            
            submitted = st.form_submit_button("🚀 Lancer l'extraction", use_container_width=True)
            
            if submitted and artist_name:
                self.start_extraction_robust(
                    artist_name=artist_name,
                    max_tracks=max_tracks,
                    enable_lyrics=enable_lyrics,
                    include_features=include_features
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
        """Dashboard simplifié"""
        st.header("📊 Dashboard")
        
        # Métriques rapides
        stats = self.get_quick_stats()
        if stats:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Sessions", stats.get('total_sessions', 0))
            with col2:
                st.metric("Artistes", stats.get('total_artists', 0))
            with col3:
                st.metric("Morceaux", stats.get('total_tracks', 0))
            with col4:
                st.metric("Actives", stats.get('active_sessions', 0))
        
        # Informations récentes
        st.subheader("📈 Activité récente")
        
        if st.session_state.session_manager:
            try:
                sessions = st.session_state.session_manager.list_sessions()
                recent_sessions = sorted(sessions, key=lambda s: s.created_at or datetime.min, reverse=True)[:3]
                
                if recent_sessions:
                    for session in recent_sessions:
                        status_emoji = {
                            self.modules['SessionStatus'].IN_PROGRESS: "🔄",
                            self.modules['SessionStatus'].COMPLETED: "✅",
                            self.modules['SessionStatus'].FAILED: "❌"
                        }.get(session.status, "❓")
                        
                        st.write(f"{status_emoji} **{session.artist_name}** - {session.status.value}")
                else:
                    st.info("Aucune session récente")
            except Exception as e:
                st.warning("⚠️ Impossible de charger les sessions récentes")
        else:
            st.info("Aucune session disponible")
    
    def render_sessions(self):
        """Gestion des sessions simplifiée"""
        st.header("📝 Sessions")
        
        if not st.session_state.session_manager:
            st.warning("⚠️ Gestionnaire de sessions non disponible")
            return
        
        try:
            sessions = st.session_state.session_manager.list_sessions()
            
            if not sessions:
                st.info("Aucune session trouvée")
                return
            
            # Affichage simple des sessions
            for session in sessions:
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
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
                    
                    st.markdown("---")
        
        except Exception as e:
            st.error(f"❌ Erreur chargement sessions: {e}")
    
    def render_exports(self):
        """Interface d'exports simplifiée"""
        st.header("📤 Exports")
        st.info("💡 Fonctionnalité d'export en cours de développement")
        
        # Placeholder pour les fonctionnalités futures
        st.markdown("""
        **Fonctionnalités prévues:**
        - Export JSON
        - Export CSV
        - Export Excel
        - Export HTML
        """)
    
    def render_settings(self):
        """Paramètres simplifiés"""
        st.header("⚙️ Paramètres")
        
        # Configuration des APIs
        st.subheader("🔑 Configuration des APIs")
        
        # Affichage de l'état actuel
        try:
            settings = self.modules['settings']
            
            col1, col2 = st.columns(2)
            
            with col1:
                genius_status = "✅ Configuré" if settings.genius_api_key else "❌ Non configuré"
                st.write(f"**Genius API:** {genius_status}")
                
                if st.button("🔧 Configurer Genius"):
                    st.info("💡 Modifiez le fichier .env pour configurer les APIs")
            
            with col2:
                spotify_status = "✅ Configuré" if settings.spotify_client_id else "❌ Non configuré"
                st.write(f"**Spotify API:** {spotify_status}")
                
                if st.button("🔧 Configurer Spotify"):
                    st.info("💡 Modifiez le fichier .env pour configurer les APIs")
        
        except Exception as e:
            st.error(f"❌ Erreur chargement paramètres: {e}")
    
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