# core/database.py - Version corrigée et complétée
import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from contextlib import contextmanager

from config.settings import settings
from models.entities import Artist, Album, Track, Credit, Session, QualityReport
from models.enums import AlbumType, CreditCategory, SessionStatus, DataSource

class Database:
    """Gestionnaire de base de données SQLite avec migrations"""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(settings.data_dir / "music_data.db")
        self.migrations_dir = Path(__file__).parent / "migrations"
        self._init_database()
    
    def _init_database(self):
        """Initialise la base de données et exécute les migrations"""
        with self.get_connection() as conn:
            self._create_migration_table(conn)
            self._run_migrations(conn)
    
    @contextmanager
    def get_connection(self):
        """Context manager pour les connexions à la base"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Pour accéder aux colonnes par nom
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _create_migration_table(self, conn: sqlite3.Connection):
        """Crée la table des migrations si elle n'existe pas"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    def _run_migrations(self, conn: sqlite3.Connection):
        """Exécute les migrations SQL"""
        migrations = self._get_migration_files()
        executed_migrations = self._get_executed_migrations(conn)
        
        for migration_file in migrations:
            if migration_file not in executed_migrations:
                print(f"Exécution de la migration: {migration_file}")
                self._execute_migration(conn, migration_file)
    
    def _get_migration_files(self) -> List[str]:
        """Récupère la liste des fichiers de migration"""
        return ["001_initial_schema.sql"]
    
    def _get_executed_migrations(self, conn: sqlite3.Connection) -> List[str]:
        """Récupère la liste des migrations déjà exécutées"""
        cursor = conn.execute("SELECT filename FROM migrations")
        return [row[0] for row in cursor.fetchall()]
    
    def _execute_migration(self, conn: sqlite3.Connection, migration_file: str):
        """Exécute une migration spécifique"""
        if migration_file == "001_initial_schema.sql":
            self._create_initial_schema(conn)
        
        # Marquer la migration comme exécutée
        conn.execute(
            "INSERT INTO migrations (filename) VALUES (?",
            (migration_file,)
        )
    
    def _create_initial_schema(self, conn: sqlite3.Connection):
        """Crée le schéma initial de la base"""
        
        # Table des sessions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                artist_name TEXT NOT NULL,
                status TEXT DEFAULT 'in_progress',
                current_step TEXT,
                total_tracks_found INTEGER DEFAULT 0,
                tracks_processed INTEGER DEFAULT 0,
                tracks_with_credits INTEGER DEFAULT 0,
                tracks_with_albums INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT -- JSON
            )
        """)
        
        # Table des checkpoints
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                step_name TEXT,
                data TEXT, -- JSON
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        """)
        
        # Table des artistes
        conn.execute("""
            CREATE TABLE IF NOT EXISTS artists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                genius_id INTEGER UNIQUE,
                spotify_id TEXT UNIQUE,
                discogs_id INTEGER UNIQUE,
                genre TEXT,
                country TEXT,
                active_years TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table des albums - VERSION COMPLÈTE
        conn.execute("""
            CREATE TABLE IF NOT EXISTS albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                artist_id INTEGER,
                release_date TEXT,
                release_year INTEGER,
                album_type TEXT DEFAULT 'album',
                genre TEXT,
                label TEXT,
                spotify_id TEXT,
                discogs_id INTEGER,
                genius_id TEXT,
                track_count INTEGER,
                total_duration INTEGER, -- en secondes
                cover_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (artist_id) REFERENCES artists (id)
            )
        """)
        
        # Table des tracks
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                artist_id INTEGER,
                artist_name TEXT,
                album_id INTEGER,
                album_title TEXT,
                track_number INTEGER,
                disc_number INTEGER DEFAULT 1,
                genius_id INTEGER UNIQUE,
                spotify_id TEXT,
                genius_url TEXT,
                duration_seconds INTEGER,
                bpm INTEGER,
                key TEXT,
                has_lyrics BOOLEAN DEFAULT 0,
                lyrics TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (artist_id) REFERENCES artists (id),
                FOREIGN KEY (album_id) REFERENCES albums (id)
            )
        """)
        
        # Table des crédits
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                credit_category TEXT NOT NULL,
                credit_type TEXT NOT NULL,
                person_name TEXT NOT NULL,
                instrument_detail TEXT,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES tracks (id)
            )
        """)
        
        # Table des features (collaborations)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS track_features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                featured_artist TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES tracks (id)
            )
        """)
        
        # Table des rapports qualité
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quality_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                issues TEXT, -- JSON array
                quality_score REAL DEFAULT 0.0,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES tracks (id)
            )
        """)
        
        # Table de cache
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT UNIQUE NOT NULL,
                data TEXT, -- JSON
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Index pour les performances
        self._create_indexes(conn)
    
    def _create_indexes(self, conn: sqlite3.Connection):
        """Crée les index pour optimiser les performances"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist_id)",
            "CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id)",
            "CREATE INDEX IF NOT EXISTS idx_tracks_genius ON tracks(genius_id)",
            "CREATE INDEX IF NOT EXISTS idx_credits_track ON credits(track_id)",
            "CREATE INDEX IF NOT EXISTS idx_credits_category ON credits(credit_category)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)",
            "CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist_id)",
            "CREATE INDEX IF NOT EXISTS idx_cache_key ON cache(cache_key)",
            "CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at)"
        ]
        
        for index_sql in indexes:
            conn.execute(index_sql)
    
    # ==================== SESSIONS ====================
    
    def create_session(self, session: Session) -> str:
        """Crée une nouvelle session"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO sessions (id, artist_name, status, current_step, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session.id,
                session.artist_name,
                session.status.value,
                session.current_step,
                json.dumps(session.metadata)
            ))
        return session.id
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Récupère une session par son ID"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return Session(
                    id=row['id'],
                    artist_name=row['artist_name'],
                    status=SessionStatus(row['status']),
                    current_step=row['current_step'],
                    total_tracks_found=row['total_tracks_found'],
                    tracks_processed=row['tracks_processed'],
                    tracks_with_credits=row['tracks_with_credits'],
                    tracks_with_albums=row['tracks_with_albums'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                    metadata=json.loads(row['metadata']) if row['metadata'] else {}
                )
        return None
    
    def update_session(self, session: Session):
        """Met à jour une session"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE sessions SET
                    status = ?,
                    current_step = ?,
                    total_tracks_found = ?,
                    tracks_processed = ?,
                    tracks_with_credits = ?,
                    tracks_with_albums = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    metadata = ?
                WHERE id = ?
            """, (
                session.status.value,
                session.current_step,
                session.total_tracks_found,
                session.tracks_processed,
                session.tracks_with_credits,
                session.tracks_with_albums,
                json.dumps(session.metadata),
                session.id
            ))
    
    def list_sessions(self, status: Optional[SessionStatus] = None, limit: Optional[int] = None) -> List[Session]:
        """Liste les sessions, optionnellement filtrées par statut et limitées en nombre"""
        with self.get_connection() as conn:
            if status:
                if limit:
                    cursor = conn.execute(
                        "SELECT * FROM sessions WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                        (status.value, limit)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM sessions WHERE status = ? ORDER BY created_at DESC",
                        (status.value,)
                    )
            else:
                if limit:
                    cursor = conn.execute(
                        "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?",
                        (limit,)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM sessions ORDER BY created_at DESC"
                    )
            
            sessions = []
            for row in cursor.fetchall():
                sessions.append(Session(
                    id=row['id'],
                    artist_name=row['artist_name'],
                    status=SessionStatus(row['status']),
                    current_step=row['current_step'],
                    total_tracks_found=row['total_tracks_found'],
                    tracks_processed=row['tracks_processed'],
                    tracks_with_credits=row['tracks_with_credits'],
                    tracks_with_albums=row['tracks_with_albums'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                    metadata=json.loads(row['metadata']) if row['metadata'] else {}
                ))
            
            return sessions
    
    # ==================== ARTISTS ====================
    
    def create_artist(self, artist: Artist) -> int:
        """Crée un nouvel artiste"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO artists (name, genius_id, spotify_id, discogs_id, genre, country, active_years)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                artist.name,
                artist.genius_id,
                artist.spotify_id,
                artist.discogs_id,
                artist.genre.value if artist.genre else None,
                artist.country,
                artist.active_years
            ))
            return cursor.lastrowid
    
    def get_artist_by_name(self, name: str) -> Optional[Artist]:
        """Récupère un artiste par son nom"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM artists WHERE name = ? COLLATE NOCASE",
                (name,)
            )
            row = cursor.fetchone()
            
            if row:
                return Artist(
                    id=row['id'],
                    name=row['name'],
                    genius_id=row['genius_id'],
                    spotify_id=row['spotify_id'],
                    discogs_id=row['discogs_id'],
                    genre=row['genre'],
                    country=row['country'],
                    active_years=row['active_years']
                )
        return None
    
    def get_artist_by_id(self, artist_id: int) -> Optional[Artist]:
        """Récupère un artiste par son ID"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM artists WHERE id = ?",
                (artist_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return Artist(
                    id=row['id'],
                    name=row['name'],
                    genius_id=row['genius_id'],
                    spotify_id=row['spotify_id'],
                    discogs_id=row['discogs_id'],
                    genre=row['genre'],
                    country=row['country'],
                    active_years=row['active_years']
                )
        return None
    
    def update_artist(self, artist: Artist):
        """Met à jour un artiste"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE artists SET
                    name = ?,
                    genius_id = ?,
                    spotify_id = ?,
                    discogs_id = ?,
                    genre = ?,
                    country = ?,
                    active_years = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                artist.name,
                artist.genius_id,
                artist.spotify_id,
                artist.discogs_id,
                artist.genre.value if artist.genre else None,
                artist.country,
                artist.active_years,
                artist.id
            ))
    
    def list_artists(self, limit: Optional[int] = None) -> List[Artist]:
        """Liste tous les artistes"""
        with self.get_connection() as conn:
            if limit:
                cursor = conn.execute(
                    "SELECT * FROM artists ORDER BY name LIMIT ?",
                    (limit,)
                )
            else:
                cursor = conn.execute("SELECT * FROM artists ORDER BY name")
            
            artists = []
            for row in cursor.fetchall():
                artists.append(Artist(
                    id=row['id'],
                    name=row['name'],
                    genius_id=row['genius_id'],
                    spotify_id=row['spotify_id'],
                    discogs_id=row['discogs_id'],
                    genre=row['genre'],
                    country=row['country'],
                    active_years=row['active_years']
                ))
            
            return artists
    
    def delete_artist(self, artist_id: int) -> bool:
        """Supprime un artiste et toutes ses données associées"""
        with self.get_connection() as conn:
            try:
                # Supprimer en cascade (crédits -> tracks -> albums -> artiste)
                conn.execute("""
                    DELETE FROM credits WHERE track_id IN (
                        SELECT id FROM tracks WHERE artist_id = ?
                    )
                """, (artist_id,))
                
                conn.execute("DELETE FROM tracks WHERE artist_id = ?", (artist_id,))
                conn.execute("DELETE FROM albums WHERE artist_id = ?", (artist_id,))
                conn.execute("DELETE FROM artists WHERE id = ?", (artist_id,))
                
                return True
            except Exception as e:
                print(f"Erreur suppression artiste: {e}")
                return False
    
    # ==================== TRACKS ====================
    
    def create_track(self, track: Track) -> int:
        """Crée un nouveau track"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO tracks (
                    title, artist_id, artist_name, album_id, album_title,
                    track_number, disc_number, genius_id, spotify_id, genius_url,
                    duration_seconds, bpm, key, has_lyrics, lyrics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                track.title,
                track.artist_id,
                track.artist_name,
                track.album_id,
                track.album_title,
                track.track_number,
                track.disc_number,
                track.genius_id,
                track.spotify_id,
                track.genius_url,
                track.duration_seconds,
                track.bpm,
                track.key,
                track.has_lyrics,
                track.lyrics
            ))
            return cursor.lastrowid
    
    def get_track_by_id(self, track_id: int) -> Optional[Track]:
        """Récupère un track par son ID"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM tracks WHERE id = ?",
                (track_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return self._row_to_track(row)
        return None
    
    def get_tracks_by_artist(self, artist_id: int, limit: Optional[int] = None) -> List[Track]:
        """Récupère tous les tracks d'un artiste"""
        with self.get_connection() as conn:
            if limit:
                cursor = conn.execute(
                    "SELECT * FROM tracks WHERE artist_id = ? ORDER BY title LIMIT ?",
                    (artist_id, limit)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM tracks WHERE artist_id = ? ORDER BY title",
                    (artist_id,)
                )
            
            tracks = []
            for row in cursor.fetchall():
                tracks.append(self._row_to_track(row))
            
            return tracks
    
    def update_track(self, track: Track):
        """Met à jour un track"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE tracks SET
                    title = ?,
                    artist_id = ?,
                    artist_name = ?,
                    album_id = ?,
                    album_title = ?,
                    track_number = ?,
                    disc_number = ?,
                    genius_id = ?,
                    spotify_id = ?,
                    genius_url = ?,
                    duration_seconds = ?,
                    bpm = ?,
                    key = ?,
                    has_lyrics = ?,
                    lyrics = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                track.title,
                track.artist_id,
                track.artist_name,
                track.album_id,
                track.album_title,
                track.track_number,
                track.disc_number,
                track.genius_id,
                track.spotify_id,
                track.genius_url,
                track.duration_seconds,
                track.bpm,
                track.key,
                track.has_lyrics,
                track.lyrics,
                track.id
            ))
    
    def _row_to_track(self, row) -> Track:
        """Convertit une ligne de base en objet Track"""
        return Track(
            id=row['id'],
            title=row['title'],
            artist_id=row['artist_id'],
            artist_name=row['artist_name'],
            album_id=row['album_id'],
            album_title=row['album_title'],
            track_number=row['track_number'],
            disc_number=row['disc_number'],
            genius_id=row['genius_id'],
            spotify_id=row['spotify_id'],
            genius_url=row['genius_url'],
            duration_seconds=row['duration_seconds'],
            bpm=row['bpm'],
            key=row['key'],
            has_lyrics=bool(row['has_lyrics']),
            lyrics=row['lyrics']
        )
    
    # ==================== STATS ====================
    
    def get_stats(self, artist_id: Optional[int] = None) -> Dict[str, Any]:
        """Récupère les statistiques"""
        with self.get_connection() as conn:
            stats = {}
            
            if artist_id:
                # Stats pour un artiste spécifique
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_tracks,
                        COUNT(CASE WHEN has_lyrics = 1 THEN 1 END) as tracks_with_lyrics,
                        AVG(duration_seconds) as avg_duration
                    FROM tracks WHERE artist_id = ?
                """, (artist_id,))
                row = cursor.fetchone()
                stats.update(dict(row))
                
                # Crédits pour cet artiste
                cursor = conn.execute("""
                    SELECT COUNT(*) as total_credits
                    FROM credits c
                    JOIN tracks t ON c.track_id = t.id
                    WHERE t.artist_id = ?
                """, (artist_id,))
                row = cursor.fetchone()
                stats['total_credits'] = row['total_credits']
                
            else:
                # Stats générales
                cursor = conn.execute("SELECT COUNT(*) as total_artists FROM artists")
                stats['total_artists'] = cursor.fetchone()['total_artists']
                
                cursor = conn.execute("SELECT COUNT(*) as total_tracks FROM tracks")
                stats['total_tracks'] = cursor.fetchone()['total_tracks']
                
                cursor = conn.execute("SELECT COUNT(*) as total_credits FROM credits")
                stats['total_credits'] = cursor.fetchone()['total_credits']
            
            return stats
    
    def get_database_size(self) -> float:
        """Retourne la taille de la base en MB"""
        try:
            size_bytes = Path(self.db_path).stat().st_size
            return size_bytes / (1024 * 1024)  # Conversion en MB
        except:
            return 0.0
    
    def get_artist_count(self) -> int:
        """Retourne le nombre total d'artistes"""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as count FROM artists")
            return cursor.fetchone()['count']
    
    def get_track_count(self) -> int:
        """Retourne le nombre total de tracks"""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as count FROM tracks")
            return cursor.fetchone()['count']