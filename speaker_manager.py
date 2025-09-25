import sqlite3
import json
import time
from typing import Dict, List, Optional

class SpeakerManager:
    def __init__(self, db_file="session_data.db"):
        self.db_file = db_file
        self.init_database()
        self.current_session_speakers = {}
        self.speaker_profiles = {}

    def init_database(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        # Speaker profiles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS speaker_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                voice_characteristics TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                client_count INTEGER NOT NULL,
                session_type TEXT DEFAULT 'individual',
                notes TEXT,
                duration_minutes REAL,
                status TEXT DEFAULT 'active'
            )
        ''')

        # Session speakers table (many-to-many relationship)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS session_speakers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                speaker_name TEXT NOT NULL,
                speaker_role TEXT NOT NULL,
                audio_channel INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')

        # Transcripts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp REAL NOT NULL,
                speaker_name TEXT NOT NULL,
                speaker_role TEXT NOT NULL,
                text TEXT NOT NULL,
                confidence REAL DEFAULT 0.0,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')

        conn.commit()
        conn.close()

    def create_session(self, client_count: int, session_type: str = "individual") -> int:
        """Create a new therapy session"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO sessions (client_count, session_type, status)
            VALUES (?, ?, 'active')
        ''', (client_count, session_type))

        session_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self.current_session_id = session_id
        self.current_session_speakers = {}

        return session_id

    def setup_session_speakers(self, session_id: int, client_count: int, speaker_names: List[str] = None):
        """Setup speakers for the current session"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        # Always add therapist
        cursor.execute('''
            INSERT INTO session_speakers (session_id, speaker_name, speaker_role, audio_channel)
            VALUES (?, 'THERAPIST', 'therapist', 0)
        ''', (session_id,))

        self.current_session_speakers['THERAPIST'] = {
            'role': 'therapist',
            'channel': 0,
            'name': 'THERAPIST'
        }

        # Add clients
        if speaker_names and len(speaker_names) >= client_count:
            for i, name in enumerate(speaker_names[:client_count]):
                cursor.execute('''
                    INSERT INTO session_speakers (session_id, speaker_name, speaker_role, audio_channel)
                    VALUES (?, ?, 'client', 1)
                ''', (session_id, name))

                self.current_session_speakers[name] = {
                    'role': 'client',
                    'channel': 1,
                    'name': name
                }
        else:
            # Default client naming
            for i in range(client_count):
                client_name = f"CLIENT_{i+1}" if client_count > 1 else "CLIENT"
                cursor.execute('''
                    INSERT INTO session_speakers (session_id, speaker_name, speaker_role, audio_channel)
                    VALUES (?, ?, 'client', 1)
                ''', (session_id, client_name))

                self.current_session_speakers[client_name] = {
                    'role': 'client',
                    'channel': 1,
                    'name': client_name
                }

        conn.commit()
        conn.close()

    def add_speaker_profile(self, name: str, characteristics: Dict = None):
        """Add or update a speaker profile"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        characteristics_json = json.dumps(characteristics) if characteristics else None

        cursor.execute('''
            INSERT OR REPLACE INTO speaker_profiles
            (name, voice_characteristics, last_used)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (name, characteristics_json))

        conn.commit()
        conn.close()

        self.speaker_profiles[name] = characteristics or {}

    def get_speaker_profiles(self) -> Dict:
        """Get all stored speaker profiles"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT name, voice_characteristics, last_used
            FROM speaker_profiles
            ORDER BY last_used DESC
        ''')

        profiles = {}
        for row in cursor.fetchall():
            name, characteristics_json, last_used = row
            characteristics = json.loads(characteristics_json) if characteristics_json else {}
            profiles[name] = {
                'characteristics': characteristics,
                'last_used': last_used
            }

        conn.close()
        return profiles

    def identify_speaker_from_transcript(self, text: str, audio_channel: int) -> str:
        """
        Identify speaker based on transcript text and audio channel.
        This is a simplified implementation - in production, you'd use
        voice recognition or more sophisticated speaker diarization.
        """
        # Channel 0 = Therapist microphone
        if audio_channel == 0:
            return "THERAPIST"

        # Channel 1 = System audio (clients)
        # Simple heuristic: look for therapeutic language patterns
        therapeutic_phrases = [
            "how does that make you feel",
            "let's explore that",
            "what comes up for you",
            "can you tell me more",
            "i'm hearing",
            "it sounds like"
        ]

        text_lower = text.lower()
        if any(phrase in text_lower for phrase in therapeutic_phrases):
            return "THERAPIST"

        # Default to first client for system audio channel
        client_speakers = [name for name, info in self.current_session_speakers.items()
                         if info['role'] == 'client']
        return client_speakers[0] if client_speakers else "CLIENT"

    def manual_speaker_correction(self, transcript_id: int, correct_speaker: str):
        """Manually correct speaker identification"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE transcripts
            SET speaker_name = ?, speaker_role = ?
            WHERE id = ?
        ''', (correct_speaker,
              self.current_session_speakers.get(correct_speaker, {}).get('role', 'unknown'),
              transcript_id))

        conn.commit()
        conn.close()

    def add_transcript_segment(self, session_id: int, text: str, speaker: str,
                             timestamp: float, confidence: float = 0.0):
        """Add a transcript segment to the database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        speaker_info = self.current_session_speakers.get(speaker, {})
        speaker_role = speaker_info.get('role', 'unknown')

        cursor.execute('''
            INSERT INTO transcripts
            (session_id, timestamp, speaker_name, speaker_role, text, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, timestamp, speaker, speaker_role, text, confidence))

        transcript_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return transcript_id

    def get_session_transcript(self, session_id: int) -> List[Dict]:
        """Get complete transcript for a session"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, timestamp, speaker_name, speaker_role, text, confidence
            FROM transcripts
            WHERE session_id = ?
            ORDER BY timestamp ASC
        ''', (session_id,))

        transcript = []
        for row in cursor.fetchall():
            transcript.append({
                'id': row[0],
                'timestamp': row[1],
                'speaker': row[2],
                'role': row[3],
                'text': row[4],
                'confidence': row[5]
            })

        conn.close()
        return transcript

    def format_transcript_for_analysis(self, session_id: int, last_minutes: int = None) -> str:
        """Format transcript for AI analysis"""
        transcript = self.get_session_transcript(session_id)

        if last_minutes:
            # Filter to last N minutes
            current_time = time.time()
            cutoff_time = current_time - (last_minutes * 60)
            transcript = [t for t in transcript if t['timestamp'] >= cutoff_time]

        formatted_lines = []
        for segment in transcript:
            speaker_tag = f"[{segment['speaker']}]"
            formatted_lines.append(f"{speaker_tag}: {segment['text']}")

        return "\n".join(formatted_lines)

    def get_session_summary(self, session_id: int) -> Dict:
        """Get summary statistics for a session"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        # Get session info
        cursor.execute('''
            SELECT session_date, client_count, session_type, duration_minutes, status
            FROM sessions WHERE id = ?
        ''', (session_id,))

        session_info = cursor.fetchone()

        # Get speaker participation
        cursor.execute('''
            SELECT speaker_name, COUNT(*) as segment_count,
                   SUM(LENGTH(text)) as total_characters
            FROM transcripts
            WHERE session_id = ?
            GROUP BY speaker_name
        ''', (session_id,))

        speaker_stats = {}
        for row in cursor.fetchall():
            speaker_stats[row[0]] = {
                'segments': row[1],
                'characters': row[2]
            }

        conn.close()

        return {
            'session_info': session_info,
            'speaker_participation': speaker_stats,
            'total_speakers': len(self.current_session_speakers)
        }

    def end_session(self, session_id: int, notes: str = ""):
        """End a therapy session"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        # Calculate session duration
        cursor.execute('''
            SELECT MIN(timestamp), MAX(timestamp)
            FROM transcripts WHERE session_id = ?
        ''', (session_id,))

        result = cursor.fetchone()
        duration = 0
        if result[0] and result[1]:
            duration = (result[1] - result[0]) / 60  # Convert to minutes

        cursor.execute('''
            UPDATE sessions
            SET status = 'completed', notes = ?, duration_minutes = ?
            WHERE id = ?
        ''', (notes, duration, session_id))

        conn.commit()
        conn.close()

        self.current_session_speakers = {}

    def get_recent_sessions(self, limit: int = 10) -> List[Dict]:
        """Get recent therapy sessions"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, session_date, client_count, session_type,
                   duration_minutes, status, notes
            FROM sessions
            ORDER BY session_date DESC
            LIMIT ?
        ''', (limit,))

        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                'id': row[0],
                'date': row[1],
                'client_count': row[2],
                'type': row[3],
                'duration': row[4],
                'status': row[5],
                'notes': row[6]
            })

        conn.close()
        return sessions