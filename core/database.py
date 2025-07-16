# core/database.py - Version corrigée et complétée
import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from contextlib import contextmanager

from config.settings import settings
from models.entities import Artist, Album, Track, Credit, Session
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
            "INSERT INTO migrations (filename) VALUES (?)",
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
        
        # Table des albums
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
                total_duration INTEGER,
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
                track_id INTEGER,
                credit_category TEXT,
                credit_type TEXT,
                person_name TEXT,
                role_detail TEXT,
                instrument TEXT,
                is_primary BOOLEAN DEFAULT 0,
                is_featuring BOOLEAN DEFAULT 0,
                is_uncredited BOOLEAN DEFAULT 0,
                data_source TEXT,
                extraction_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES tracks (id)
            )
        """)
        
        # Table de cache
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT UNIQUE NOT NULL,
                data TEXT,
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
                    artist_name = ?,
                    status = ?,
                    current_step = ?,
                    total_tracks_found = ?,
                    tracks_processed = ?,
                    tracks_with_credits = ?,
                    tracks_with_albums = ?,
                    metadata = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                session.artist_name,
                session.status.value,
                session.current_step,
                session.total_tracks_found,
                session.tracks_processed,
                session.tracks_with_credits,
                session.tracks_with_albums,
                json.dumps(session.metadata),
                session.id
            ))
    
    def list_sessions(self, status: Optional[SessionStatus] = None, 
                     limit: Optional[int] = None) -> List[Session]:
        """Liste les sessions avec filtres optionnels"""
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
    
    def save_artist(self, artist: Artist) -> Artist:
        """
        Sauvegarde un artiste (création ou mise à jour).
        
        Args:
            artist: L'objet Artist à sauvegarder
            
        Returns:
            Artist: L'artiste sauvegardé avec son ID
        """
        if artist.id:
            # L'artiste existe déjà, on fait une mise à jour
            self.update_artist(artist)
            return artist
        else:
            # Nouvel artiste, on le crée
            artist_id = self.create_artist(artist)
            # Créer un nouvel objet Artist avec l'ID généré
            artist.id = artist_id
            return artist
    
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
                    active_years=row['active_years'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
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
                    active_years=row['active_years'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
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
                    active_years=row['active_years'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
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
                track.duration,
                track.bpm,
                track.key,
                track.has_lyrics,
                track.lyrics
            ))
            return cursor.lastrowid
    
    def save_track(self, track: Track) -> Track:
        """Sauvegarde un track (création ou mise à jour)"""
        if track.id:
            self.update_track(track)
            return track
        else:
            track_id = self.create_track(track)
            track.id = track_id
            return track
    
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
                track.duration,
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
            album_name=row['album_title'],
            track_number=row['track_number'],
            disc_number=row['disc_number'],
            genius_id=row['genius_id'],
            spotify_id=row['spotify_id'],
            genius_url=row['genius_url'],
            duration=row['duration_seconds'],
            bpm=row['bpm'],
            key=row['key'],
            has_lyrics=bool(row['has_lyrics']),
            lyrics=row['lyrics']
        )
    
    # ==================== ALBUMS ====================
    
    def create_album(self, album: Album) -> int:
        """Crée un nouvel album"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO albums (
                    title, artist_id, release_date, release_year, album_type,
                    genre, label, spotify_id, discogs_id, genius_id,
                    track_count, total_duration, cover_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                album.title,
                album.artist_id,
                album.release_date,
                album.release_year,
                album.album_type.value if album.album_type else None,
                album.genre.value if album.genre else None,
                album.label,
                album.spotify_id,
                album.discogs_id,
                album.genius_id,
                album.total_tracks,
                0,  # total_duration
                None  # cover_url
            ))
            return cursor.lastrowid
    
    def save_album(self, album: Album) -> Album:
        """Sauvegarde un album (création ou mise à jour)"""
        if album.id:
            self.update_album(album)
            return album
        else:
            album_id = self.create_album(album)
            album.id = album_id
            return album
    
    def get_album_by_id(self, album_id: int) -> Optional[Album]:
        """Récupère un album par son ID"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM albums WHERE id = ?",
                (album_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return self._row_to_album(row)
        return None
    
    def get_albums_by_artist(self, artist_id: int) -> List[Album]:
        """Récupère tous les albums d'un artiste"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM albums WHERE artist_id = ? ORDER BY release_year DESC, title",
                (artist_id,)
            )
            
            albums = []
            for row in cursor.fetchall():
                albums.append(self._row_to_album(row))
            
            return albums
    
    def update_album(self, album: Album):
        """Met à jour un album"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE albums SET
                    title = ?,
                    artist_id = ?,
                    release_date = ?,
                    release_year = ?,
                    album_type = ?,
                    genre = ?,
                    label = ?,
                    spotify_id = ?,
                    discogs_id = ?,
                    genius_id = ?,
                    track_count = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                album.title,
                album.artist_id,
                album.release_date,
                album.release_year,
                album.album_type.value if album.album_type else None,
                album.genre.value if album.genre else None,
                album.label,
                album.spotify_id,
                album.discogs_id,
                album.genius_id,
                album.total_tracks,
                album.id
            ))
    
    def _row_to_album(self, row) -> Album:
        """Convertit une ligne de base en objet Album"""
        return Album(
            id=row['id'],
            title=row['title'],
            artist_id=row['artist_id'],
            release_date=row['release_date'],
            release_year=row['release_year'],
            album_type=AlbumType(row['album_type']) if row['album_type'] else AlbumType.ALBUM,
            label=row['label'],
            spotify_id=row['spotify_id'],
            discogs_id=row['discogs_id'],
            genius_id=row['genius_id'],
            total_tracks=row['track_count'] or 0
        )
    
    # ==================== CREDITS ====================
    
    def create_credit(self, credit: Credit) -> int:
        """Crée un nouveau crédit"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO credits (
                    track_id, credit_category, credit_type, person_name,
                    role_detail, instrument, is_primary, is_featuring,
                    is_uncredited, data_source, extraction_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                credit.track_id,
                credit.credit_category.value if credit.credit_category else None,
                credit.credit_type.value,
                credit.person_name,
                credit.role_detail,
                credit.instrument,
                credit.is_primary,
                credit.is_featuring,
                credit.is_uncredited,
                credit.data_source.value,
                credit.extraction_date.isoformat() if credit.extraction_date else None
            ))
            return cursor.lastrowid
    
    def save_credit(self, credit: Credit) -> Credit:
        """Sauvegarde un crédit (création ou mise à jour)"""
        if credit.id:
            self.update_credit(credit)
            return credit
        else:
            credit_id = self.create_credit(credit)
            credit.id = credit_id
            return credit
    
    def get_credits_by_track(self, track_id: int) -> List[Credit]:
        """Récupère tous les crédits d'un track"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM credits WHERE track_id = ? ORDER BY credit_category, person_name",
                (track_id,)
            )
            
            credits = []
            for row in cursor.fetchall():
                credits.append(self._row_to_credit(row))
            
            return credits
    
    def update_credit(self, credit: Credit):
        """Met à jour un crédit"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE credits SET
                    track_id = ?,
                    credit_category = ?,
                    credit_type = ?,
                    person_name = ?,
                    role_detail = ?,
                    instrument = ?,
                    is_primary = ?,
                    is_featuring = ?,
                    is_uncredited = ?,
                    data_source = ?,
                    extraction_date = ?
                WHERE id = ?
            """, (
                credit.track_id,
                credit.credit_category.value if credit.credit_category else None,
                credit.credit_type.value,
                credit.person_name,
                credit.role_detail,
                credit.instrument,
                credit.is_primary,
                credit.is_featuring,
                credit.is_uncredited,
                credit.data_source.value,
                credit.extraction_date.isoformat() if credit.extraction_date else None,
                credit.id
            ))
    
    def _row_to_credit(self, row) -> Credit:
        """Convertit une ligne de base en objet Credit"""
        from models.enums import CreditType
        
        return Credit(
            id=row['id'],
            track_id=row['track_id'],
            credit_category=CreditCategory(row['credit_category']) if row['credit_category'] else None,
            credit_type=CreditType(row['credit_type']),
            person_name=row['person_name'],
            role_detail=row['role_detail'],
            instrument=row['instrument'],
            is_primary=bool(row['is_primary']),
            is_featuring=bool(row['is_featuring']),
            is_uncredited=bool(row['is_uncredited']),
            data_source=DataSource(row['data_source']),
            extraction_date=datetime.fromisoformat(row['extraction_date']) if row['extraction_date'] else None,
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
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
                stats.update(dict(row))
                
                # Albums pour cet artiste
                cursor = conn.execute("""
                    SELECT COUNT(*) as total_albums
                    FROM albums WHERE artist_id = ?
                """, (artist_id,))
                row = cursor.fetchone()
                stats.update(dict(row))
                
            else:
                # Stats globales
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_artists
                    FROM artists
                """)
                row = cursor.fetchone()
                stats.update(dict(row))
                
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_tracks,
                        COUNT(CASE WHEN has_lyrics = 1 THEN 1 END) as tracks_with_lyrics
                    FROM tracks
                """)
                row = cursor.fetchone()
                stats.update(dict(row))
                
                cursor = conn.execute("""
                    SELECT COUNT(*) as total_credits
                    FROM credits
                """)
                row = cursor.fetchone()
                stats.update(dict(row))
                
                cursor = conn.execute("""
                    SELECT COUNT(*) as total_albums
                    FROM albums
                """)
                row = cursor.fetchone()
                stats.update(dict(row))
                
                cursor = conn.execute("""
                    SELECT COUNT(*) as total_sessions
                    FROM sessions
                """)
                row = cursor.fetchone()
                stats.update(dict(row))
            
            return stats
    
    # ==================== CACHE ====================
    
    def get_cache(self, cache_key: str) -> Optional[Any]:
        """Récupère une valeur du cache"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT data, expires_at FROM cache 
                WHERE cache_key = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """, (cache_key,))
            row = cursor.fetchone()
            
            if row:
                return json.loads(row['data'])
        return None
    
    def set_cache(self, cache_key: str, data: Any, expires_at: Optional[datetime] = None):
        """Stocke une valeur dans le cache"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cache (cache_key, data, expires_at)
                VALUES (?, ?, ?)
            """, (
                cache_key,
                json.dumps(data),
                expires_at.isoformat() if expires_at else None
            ))
    
    def clear_cache(self, pattern: Optional[str] = None):
        """Vide le cache (optionnellement avec un pattern)"""
        with self.get_connection() as conn:
            if pattern:
                conn.execute(
                    "DELETE FROM cache WHERE cache_key LIKE ?",
                    (f"%{pattern}%",)
                )
            else:
                conn.execute("DELETE FROM cache")
    
    def cleanup_expired_cache(self):
        """Supprime les entrées de cache expirées"""
        with self.get_connection() as conn:
            conn.execute("""
                DELETE FROM cache 
                WHERE expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP
            """)
    
    # ==================== CHECKPOINTS ====================
    
    def save_checkpoint(self, session_id: str, step_name: str, data: Dict[str, Any]):
        """Sauvegarde un checkpoint"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO checkpoints (session_id, step_name, data)
                VALUES (?, ?, ?)
            """, (
                session_id,
                step_name,
                json.dumps(data)
            ))
    
    def get_checkpoint(self, session_id: str, step_name: str) -> Optional[Dict[str, Any]]:
        """Récupère un checkpoint"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT data FROM checkpoints 
                WHERE session_id = ? AND step_name = ?
                ORDER BY created_at DESC LIMIT 1
            """, (session_id, step_name))
            row = cursor.fetchone()
            
            if row:
                return json.loads(row['data'])
        return None
    
    def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        """Liste tous les checkpoints d'une session"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT step_name, data, created_at FROM checkpoints 
                WHERE session_id = ?
                ORDER BY created_at DESC
            """, (session_id,))
            
            checkpoints = []
            for row in cursor.fetchall():
                checkpoints.append({
                    'step_name': row['step_name'],
                    'data': json.loads(row['data']),
                    'created_at': row['created_at']
                })
            
            return checkpoints
    
    # ==================== SEARCH ====================
    
    def search_tracks(self, query: str, artist_id: Optional[int] = None, 
                     limit: int = 50) -> List[Track]:
        """Recherche de tracks par titre"""
        with self.get_connection() as conn:
            if artist_id:
                cursor = conn.execute("""
                    SELECT * FROM tracks 
                    WHERE artist_id = ? AND title LIKE ?
                    ORDER BY title LIMIT ?
                """, (artist_id, f"%{query}%", limit))
            else:
                cursor = conn.execute("""
                    SELECT * FROM tracks 
                    WHERE title LIKE ? OR artist_name LIKE ?
                    ORDER BY title LIMIT ?
                """, (f"%{query}%", f"%{query}%", limit))
            
            tracks = []
            for row in cursor.fetchall():
                tracks.append(self._row_to_track(row))
            
            return tracks
    
    def search_artists(self, query: str, limit: int = 20) -> List[Artist]:
        """Recherche d'artistes par nom"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM artists 
                WHERE name LIKE ?
                ORDER BY name LIMIT ?
            """, (f"%{query}%", limit))
            
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
                    active_years=row['active_years'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
                ))
            
            return artists
    
    # ==================== UTILITIES ====================
    
    def vacuum_database(self):
        """Optimise la base de données"""
        with self.get_connection() as conn:
            conn.execute("VACUUM")
    
    def get_database_size(self) -> Dict[str, Any]:
        """Retourne des informations sur la taille de la base"""
        db_path = Path(self.db_path)
        
        if not db_path.exists():
            return {'size_bytes': 0, 'size_mb': 0}
        
        size_bytes = db_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        
        with self.get_connection() as conn:
            # Compter les enregistrements
            tables_info = {}
            for table in ['artists', 'albums', 'tracks', 'credits', 'sessions']:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                tables_info[table] = count
        
        return {
            'size_bytes': size_bytes,
            'size_mb': round(size_mb, 2),
            'tables': tables_info
        }
    
    def backup_database(self, backup_path: str):
        """Crée une sauvegarde de la base de données"""
        import shutil
        
        backup_path = Path(backup_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(self.db_path, backup_path)
        
        return backup_path
    
    def export_to_json(self, output_path: str, artist_id: Optional[int] = None):
        """Exporte les données en JSON"""
        data = {
            'export_date': datetime.now().isoformat(),
            'artists': [],
            'albums': [],
            'tracks': [],
            'credits': []
        }
        
        if artist_id:
            # Export pour un artiste spécifique
            artist = self.get_artist_by_id(artist_id)
            if artist:
                data['artists'] = [artist.to_dict()]
                data['albums'] = [album.to_dict() for album in self.get_albums_by_artist(artist_id)]
                data['tracks'] = [track.to_dict() for track in self.get_tracks_by_artist(artist_id)]
                
                # Crédits pour tous les tracks de cet artiste
                for track in data['tracks']:
                    track_credits = self.get_credits_by_track(track['id'])
                    data['credits'].extend([credit.to_dict() for credit in track_credits])
        else:
            # Export complet
            data['artists'] = [artist.to_dict() for artist in self.list_artists()]
            
            with self.get_connection() as conn:
                # Albums
                cursor = conn.execute("SELECT * FROM albums")
                for row in cursor.fetchall():
                    album = self._row_to_album(row)
                    data['albums'].append(album.to_dict())
                
                # Tracks
                cursor = conn.execute("SELECT * FROM tracks")
                for row in cursor.fetchall():
                    track = self._row_to_track(row)
                    data['tracks'].append(track.to_dict())
                
                # Credits
                cursor = conn.execute("SELECT * FROM credits")
                for row in cursor.fetchall():
                    credit = self._row_to_credit(row)
                    data['credits'].append(credit.to_dict())
        
        # Sauvegarder le JSON
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return output_path