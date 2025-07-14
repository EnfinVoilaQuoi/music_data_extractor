# Interface Streamlit - Music Data Extractor

## 🚀 Lancement rapide

### 1. Installation des dépendances
```bash
# Dépendances principales (si pas déjà installées)
pip install -r requirements.txt

# Dépendances pour l'interface
pip install streamlit plotly pandas pillow
```

### 2. Configuration des clés API
Créez un fichier `.env` dans le répertoire racine :
```env
GENIUS_API_KEY=votre_clé_genius
SPOTIFY_CLIENT_ID=votre_client_id_spotify  
SPOTIFY_CLIENT_SECRET=votre_client_secret_spotify
DISCOGS_TOKEN=votre_token_discogs
LAST_FM_API_KEY=votre_clé_lastfm
```

### 3. Lancement de l'interface
```bash
# Option 1: Script de lancement automatique
python run_interface.py

# Option 2: Lancement direct Streamlit
streamlit run streamlit_app.py
```

L'interface sera accessible sur `http://localhost:8501`

## 📊 Fonctionnalités de l'interface

### Dashboard Principal
- **Métriques en temps réel** : Sessions actives, artistes traités, morceaux extraits
- **Graphiques interactifs** : Répartition des sessions, top artistes
- **Sessions récentes** : Vue d'ensemble des dernières extractions
- **Alertes système** : Notifications des problèmes de configuration

### Nouvelle Extraction
- **Configuration intuitive** : Saisie artiste, options d'extraction
- **Paramètres avancés** : Taille des lots, threads parallèles, sources prioritaires
- **Suivi en temps réel** : Barre de progression, étapes actuelles
- **Estimation de temps** : Temps restant basé sur la performance

### Gestion des Sessions
- **Vue d'ensemble** : Toutes les sessions avec filtres
- **Actions en lot** : Pause, reprise, suppression
- **Détails complets** : Progression, métadonnées, checkpoints
- **Historique** : Traçabilité complète des extractions

### Exports Multi-formats
- **Formats supportés** : JSON, CSV, Excel, HTML, XML
- **Options personnalisables** : Inclusion paroles, données brutes
- **Téléchargement direct** : Depuis l'interface
- **Gestion des fichiers** : Liste, suppression, nettoyage automatique

### Paramètres Système
- **Configuration API** : Clés d'accès, timeouts
- **Performance** : Threads, cache, batch size
- **Maintenance** : Nettoyage cache, statistiques système
- **Monitoring** : Taille base, exports créés

## 🎛️ Guide d'utilisation

### Première utilisation
1. **Configurer les APIs** : Allez dans Paramètres → Clés API
2. **Tester la connexion** : Vérifiez que les clés fonctionnent
3. **Lancer une extraction test** : Choisissez un artiste avec peu de morceaux

### Extraction standard
1. **Nouvelle extraction** → Saisir le nom d'artiste
2. **Ajuster les paramètres** selon vos besoins :
   - Max 50 morceaux pour un test
   - Max 200+ pour une extraction complète
3. **Lancer l'extraction** et suivre la progression
4. **Exporter les résultats** une fois terminé

### Optimisations recommandées
- **Batch size** : 10-15 pour un bon équilibre vitesse/stabilité
- **Workers** : 3-5 selon votre connexion internet
- **Cache** : Garder 7 jours pour éviter les re-téléchargements
- **Retry** : Activer pour les artistes avec beaucoup de morceaux

## 🔧 Personnalisation

### Thèmes et styles
Les styles CSS sont dans `streamlit_app.py` et peuvent être modifiés :
```python
# Couleurs principales
primary_color = "#667eea"
secondary_color = "#764ba2"
```

### Ajout de nouvelles pages
1. Créer une nouvelle méthode `render_ma_page()`
2. Ajouter l'entrée dans le menu sidebar
3. Ajouter le cas dans la méthode `run()`

### Métriques personnalisées
Modifier `get_detailed_stats()` pour ajouter vos propres calculs.

## 🐛 Dépannage

### L'interface ne se lance pas
```bash
# Vérifier l'installation de Streamlit
streamlit --version

# Réinstaller si nécessaire
pip install --upgrade streamlit
```

### Erreurs d'import
```bash
# Vérifier que vous êtes dans le bon répertoire
pwd

# Vérifier les modules Python
python -c "import music_data_extractor"
```

### Performance lente
- Réduire le nombre de workers parallèles
- Augmenter le délai entre les batches
- Vérifier la connexion internet
- Désactiver l'auto-refresh si activé

### Base de données corrompue
```bash
# Sauvegarder l'ancienne base
mv data/music_data.db data/music_data.db.backup

# Relancer l'interface (nouvelle base créée automatiquement)
python run_interface.py
```

## 📈 Conseils d'utilisation

### Pour de gros volumes
- Lancer les extractions pendant les heures creuses
- Utiliser la pause/reprise pour les longues sessions
- Surveiller les logs pour détecter les problèmes
- Exporter régulièrement pour éviter les pertes

### Pour la qualité des données
- Privilégier Genius + Spotify comme sources
- Activer Rapedia pour le rap français
- Vérifier les résultats dans la section Sessions
- Utiliser les exports HTML pour des rapports visuels

### Pour les performances
- Garder max 3-5 workers selon votre machine
- Surveiller l'utilisation mémoire/CPU
- Nettoyer le cache régulièrement
- Supprimer les anciennes sessions inutiles

## 🔗 Intégration

L'interface utilise votre architecture existante :
- `core/database.py` : Stockage des données
- `core/session_manager.py` : Gestion des sessions  
- `steps/` : Pipeline d'extraction
- `utils/export_utils.py` : Génération des exports

Toutes les données sont compatibles avec votre code CLI existant.
