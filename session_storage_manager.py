#!/usr/bin/env python3
"""
Session Storage Manager
Handles durable file storage for recordings and transcripts with date-stamped organization.
"""

import os
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
import numpy as np
import copy

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False
    import wave

# Import project modules
try:
    from enhanced_whisper_manager import TranscriptionSegment
    from transcription_config import get_transcription_config
    from logger_config import get_logger
except ImportError as e:
    print(f"Warning: Could not import some modules: {e}")
    # Fallback for testing
    logging.basicConfig(level=logging.INFO)
    def get_logger(name):
        return logging.getLogger(name)
    
    # Mock TranscriptionSegment for testing
    class TranscriptionSegment:
        def __init__(self, start_time=0, end_time=0, text="", speaker="Unknown", confidence=0.0, is_partial=False):
            self.start_time = start_time
            self.end_time = end_time
            self.text = text
            self.speaker = speaker
            self.confidence = confidence
            self.is_partial = is_partial

class SessionStorageManager:
    """
    Manages durable file storage for recording sessions with the following structure:
    
    data/
    ├── recordings/
    │   └── YYYY-MM-DD/
    │       └── session_id/
    │           ├── audio.wav
    │           └── metadata.json
    └── transcripts/
        └── YYYY-MM-DD/
            └── session_id/
                ├── transcript.txt
                ├── transcript.jsonl
                └── segments.json
    """
    
    def __init__(self):
        self.logger = get_logger('session_storage')
        
        # Get configuration
        try:
            self.config = get_transcription_config()
            self.recordings_dir = Path(self.config['recordings_dir'])
            self.transcripts_dir = Path(self.config['transcripts_dir'])
        except:
            # Fallback directories
            self.recordings_dir = Path('./data/recordings')
            self.transcripts_dir = Path('./data/transcripts')
        
        # Ensure base directories exist
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        
        # Current session state
        self.current_session: Optional[Dict[str, Any]] = None
        self.session_segments: List[TranscriptionSegment] = []
        
        self.logger.info(f"SessionStorageManager initialized")
        self.logger.info(f"  Recordings: {self.recordings_dir}")
        self.logger.info(f"  Transcripts: {self.transcripts_dir}")

    def start_session(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Start a new recording session with date-stamped storage.
        
        Args:
            metadata: Optional session metadata (client info, session type, etc.)
            
        Returns:
            session_id: Unique identifier for this session
        """
        if self.current_session:
            self.logger.warning("Starting new session while previous session is active")
            self.end_session()
        
        # Generate session ID and date
        session_id = f"session_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        # Create session directories
        session_recording_dir = self.recordings_dir / date_str / session_id
        session_transcript_dir = self.transcripts_dir / date_str / session_id
        
        session_recording_dir.mkdir(parents=True, exist_ok=True)
        session_transcript_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize session state
        self.current_session = {
            'session_id': session_id,
            'date': date_str,
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'recording_dir': session_recording_dir,
            'transcript_dir': session_transcript_dir,
            'metadata': metadata or {},
            'stats': {
                'total_segments': 0,
                'total_duration': 0.0,
                'speakers': set(),
                'start_timestamp': time.time()
            }
        }
        
        self.session_segments = []
        
        self.logger.info(f"Started session: {session_id}")
        self.logger.info(f"  Recording dir: {session_recording_dir}")
        self.logger.info(f"  Transcript dir: {session_transcript_dir}")
        
        return session_id

    def save_transcript_segment(self, segment: TranscriptionSegment):
        """
        Save a transcription segment to the current session.
        
        Args:
            segment: TranscriptionSegment to save
        """
        if not self.current_session:
            self.logger.error("No active session to save segment to")
            return
        
        # Add to session segments
        self.session_segments.append(segment)
        
        # Update session stats
        self.current_session['stats']['total_segments'] += 1
        self.current_session['stats']['speakers'].add(segment.speaker)
        
        # Calculate duration
        if hasattr(segment, 'end_time') and hasattr(segment, 'start_time'):
            duration = segment.end_time - segment.start_time
            self.current_session['stats']['total_duration'] += max(0, duration)
        
        # Save incrementally (every 10 segments or if it's been 30 seconds)
        should_save = (
            self.current_session['stats']['total_segments'] % 10 == 0 or
            time.time() - self.current_session['stats']['start_timestamp'] > 30
        )
        
        if should_save:
            self._save_transcript_files()
            
        self.logger.debug(f"Saved segment: {segment.speaker}: {segment.text[:50]}...")

    def save_full_session_audio(self, audio_manager):
        """
        Save the complete session audio from AudioManager.
        
        Args:
            audio_manager: AudioManager instance with recorded audio
        """
        if not self.current_session:
            self.logger.error("No active session to save audio to")
            return
            
        try:
            # Get audio buffer from AudioManager
            if hasattr(audio_manager, 'get_full_audio_buffer'):
                audio_data = audio_manager.get_full_audio_buffer()
            elif hasattr(audio_manager, 'audio_buffer') and audio_manager.audio_buffer:
                # Fallback: try to get buffer directly
                audio_data = audio_manager.audio_buffer
            else:
                self.logger.warning("No audio buffer available")
                return
            
            if not audio_data or len(audio_data) == 0:
                self.logger.warning("Audio buffer is empty")
                return
            
            # Convert to numpy array if needed
            if isinstance(audio_data, list):
                audio_data = np.concatenate(audio_data)
            
            # Save audio file
            audio_file = self.current_session['recording_dir'] / 'audio.wav'
            
            if SOUNDFILE_AVAILABLE:
                # Use soundfile for better format support
                sample_rate = getattr(audio_manager, 'sample_rate', 44100)
                sf.write(str(audio_file), audio_data, sample_rate)
            else:
                # Fallback to wave module
                self._save_audio_with_wave(audio_data, str(audio_file), 
                                         getattr(audio_manager, 'sample_rate', 44100))
            
            file_size = audio_file.stat().st_size / (1024 * 1024)  # MB
            duration = len(audio_data) / getattr(audio_manager, 'sample_rate', 44100)
            
            self.logger.info(f"Saved session audio: {file_size:.1f}MB, {duration:.1f}s")
            
        except Exception as e:
            self.logger.error(f"Error saving session audio: {e}")

    def _save_audio_with_wave(self, audio_data: np.ndarray, filepath: str, sample_rate: int):
        """Fallback method to save audio using wave module"""
        # Ensure audio is in correct format
        if audio_data.dtype == np.float32:
            audio_data = (audio_data * 32767).astype(np.int16)
        elif audio_data.dtype != np.int16:
            audio_data = audio_data.astype(np.int16)
        
        with wave.open(filepath, 'wb') as wav_file:
            wav_file.setnchannels(1 if len(audio_data.shape) == 1 else audio_data.shape[1])
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())

    def _save_transcript_files(self):
        """Save transcript files in multiple formats"""
        if not self.current_session or not self.session_segments:
            return
            
        try:
            transcript_dir = self.current_session['transcript_dir']
            
            # Save as plain text
            txt_file = transcript_dir / 'transcript.txt'
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.write(f"Session: {self.current_session['session_id']}\n")
                f.write(f"Date: {self.current_session['date']}\n")
                f.write(f"Started: {self.current_session['start_time']}\n")
                f.write("-" * 50 + "\n\n")
                
                for segment in self.session_segments:
                    timestamp = time.strftime("%H:%M:%S", time.localtime(segment.start_time))
                    f.write(f"[{timestamp}] {segment.speaker}: {segment.text}\n")
            
            # Save as JSONL (one JSON object per line)
            jsonl_file = transcript_dir / 'transcript.jsonl'
            with open(jsonl_file, 'w', encoding='utf-8') as f:
                for segment in self.session_segments:
                    segment_data = {
                        'timestamp': segment.start_time,
                        'end_time': segment.end_time,
                        'speaker': segment.speaker,
                        'text': segment.text,
                        'confidence': getattr(segment, 'confidence', 0.0),
                        'is_partial': getattr(segment, 'is_partial', False)
                    }
                    f.write(json.dumps(segment_data) + '\n')
            
            # Save complete segments as JSON
            segments_file = transcript_dir / 'segments.json'
            segments_data = []
            for segment in self.session_segments:
                segments_data.append({
                    'start_time': segment.start_time,
                    'end_time': segment.end_time,
                    'speaker': segment.speaker,
                    'text': segment.text,
                    'confidence': getattr(segment, 'confidence', 0.0),
                    'is_partial': getattr(segment, 'is_partial', False)
                })
            
            with open(segments_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'session_id': self.current_session['session_id'],
                    'segments': segments_data,
                    'stats': {
                        'total_segments': len(segments_data),
                        'speakers': list(self.current_session['stats']['speakers']),
                        'total_duration': self.current_session['stats']['total_duration']
                    }
                }, f, indent=2)
                
            self.logger.debug(f"Saved transcript files: {len(self.session_segments)} segments")
            
        except Exception as e:
            self.logger.error(f"Error saving transcript files: {e}")

    def end_session(self) -> Optional[Dict[str, Any]]:
        """
        End the current session and save final files.
        
        Returns:
            Session summary information
        """
        if not self.current_session:
            self.logger.warning("No active session to end")
            return None
        
        try:
            # Update end time
            self.current_session['end_time'] = datetime.now().isoformat()
            
            # Save final transcript files
            self._save_transcript_files()
            
            # Save session metadata
            metadata_file = self.current_session['recording_dir'] / 'metadata.json'
            
            # Prepare metadata for JSON serialization
            metadata = copy.deepcopy(self.current_session)
            metadata['stats']['speakers'] = list(metadata['stats']['speakers'])  # Convert set to list
            
            # Remove non-serializable fields
            metadata.pop('recording_dir', None)
            metadata.pop('transcript_dir', None)
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            session_summary = {
                'session_id': self.current_session['session_id'],
                'date': self.current_session['date'],
                'duration': time.time() - self.current_session['stats']['start_timestamp'],
                'stats': {
                    'total_segments': len(self.session_segments),
                    'speakers': list(self.current_session['stats']['speakers']),
                    'total_duration': self.current_session['stats']['total_duration']
                }
            }
            
            self.logger.info(f"Session ended: {self.current_session['session_id']}")
            self.logger.info(f"  Segments: {len(self.session_segments)}")
            self.logger.info(f"  Duration: {session_summary['duration']:.1f}s")
            self.logger.info(f"  Speakers: {len(self.current_session['stats']['speakers'])}")
            
            # Clear current session
            self.current_session = None
            self.session_segments = []
            
            return session_summary
            
        except Exception as e:
            self.logger.error(f"Error ending session: {e}")
            return None

    def get_session_info(self) -> Optional[Dict[str, Any]]:
        """Get current session information"""
        if self.current_session:
            info = copy.deepcopy(self.current_session)
            info['stats']['speakers'] = list(info['stats']['speakers'])
            return info
        return None

    def list_sessions(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List stored sessions, optionally filtered by date.
        
        Args:
            date: Date string in YYYY-MM-DD format, or None for all dates
            
        Returns:
            List of session information dictionaries
        """
        sessions = []
        
        try:
            if date:
                search_dirs = [self.recordings_dir / date]
            else:
                search_dirs = [d for d in self.recordings_dir.iterdir() if d.is_dir()]
            
            for date_dir in search_dirs:
                if not date_dir.is_dir():
                    continue
                    
                for session_dir in date_dir.iterdir():
                    if not session_dir.is_dir():
                        continue
                    
                    metadata_file = session_dir / 'metadata.json'
                    if metadata_file.exists():
                        try:
                            with open(metadata_file, 'r', encoding='utf-8') as f:
                                session_info = json.load(f)
                                sessions.append(session_info)
                        except Exception as e:
                            self.logger.warning(f"Error reading session metadata {metadata_file}: {e}")
            
            # Sort by start time
            sessions.sort(key=lambda x: x.get('start_time', ''))
            
        except Exception as e:
            self.logger.error(f"Error listing sessions: {e}")
        
        return sessions

    def get_session_files(self, session_id: str, date: Optional[str] = None) -> Optional[Dict[str, Path]]:
        """
        Get file paths for a specific session.
        
        Args:
            session_id: Session identifier
            date: Date string, or None to search all dates
            
        Returns:
            Dictionary of file paths or None if session not found
        """
        try:
            if date:
                search_dirs = [self.recordings_dir / date]
            else:
                search_dirs = [d for d in self.recordings_dir.iterdir() if d.is_dir()]
            
            for date_dir in search_dirs:
                session_dir = date_dir / session_id
                if session_dir.exists():
                    transcript_dir = self.transcripts_dir / date_dir.name / session_id
                    
                    return {
                        'recording_dir': session_dir,
                        'transcript_dir': transcript_dir,
                        'audio_file': session_dir / 'audio.wav',
                        'metadata_file': session_dir / 'metadata.json',
                        'transcript_txt': transcript_dir / 'transcript.txt',
                        'transcript_jsonl': transcript_dir / 'transcript.jsonl',
                        'segments_json': transcript_dir / 'segments.json'
                    }
        except Exception as e:
            self.logger.error(f"Error getting session files for {session_id}: {e}")
        
        return None

def test_session_storage_manager():
    """Test the session storage manager"""
    print("Testing Session Storage Manager")
    print("=" * 40)
    
    # Create test manager
    manager = SessionStorageManager()
    
    # Start test session
    session_id = manager.start_session({
        'session_type': 'therapy',
        'client_count': 1,
        'test': True
    })
    print(f"Started session: {session_id}")
    
    # Add test segments
    test_segments = [
        TranscriptionSegment(
            start_time=time.time(),
            end_time=time.time() + 2,
            text="Hello, how are you feeling today?",
            speaker="Therapist",
            confidence=0.95
        ),
        TranscriptionSegment(
            start_time=time.time() + 3,
            end_time=time.time() + 6,
            text="I'm feeling a bit anxious about work.",
            speaker="Client",
            confidence=0.92
        )
    ]
    
    for segment in test_segments:
        manager.save_transcript_segment(segment)
        print(f"Added segment: {segment.speaker}: {segment.text}")
    
    # End session
    summary = manager.end_session()
    print(f"Session ended: {summary}")
    
    # List sessions
    sessions = manager.list_sessions()
    print(f"Found {len(sessions)} sessions")
    
    print("Test completed successfully!")

if __name__ == "__main__":
    test_session_storage_manager()