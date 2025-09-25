#!/usr/bin/env python3
"""
Local Whisper Transcription Manager
Handles local Whisper transcription with speaker diarization
"""

import numpy as np
import threading
import time
import os
import tempfile
import wave
from typing import Dict, List, Callable, Optional, Tuple
from dataclasses import dataclass
from queue import Queue, Empty
import logging

# Try to import faster-whisper
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    print("Warning: faster-whisper not available, using fallback")

@dataclass
class TranscriptionSegment:
    """Single transcription segment with speaker info"""
    start_time: float
    end_time: float
    text: str
    speaker: str = "Unknown"
    confidence: float = 0.0

@dataclass
class TranscriptionResult:
    """Complete transcription result"""
    segments: List[TranscriptionSegment]
    full_text: str
    processing_time: float
    model_used: str

class LocalWhisperManager:
    """Manages local Whisper transcription with real-time processing"""

    def __init__(self, model_name: str = "small", device: str = "auto"):
        self.model_name = model_name
        self.device = self._detect_device() if device == "auto" else device
        self.model = None
        self.processing_queue = Queue()
        self.result_callbacks = []
        self.is_processing = False
        self.worker_thread = None
        self.speaker_tracker = SpeakerTracker()

        # Setup logging
        from logger_config import get_logger
        self.logger = get_logger('local_whisper')

        # Import model manager for path resolution
        from whisper_model_downloader import WhisperModelManager
        self.model_manager = WhisperModelManager()

        # Load model
        self.load_model()

    def _detect_device(self) -> str:
        """Detect best available device for inference"""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    def load_model(self) -> bool:
        """Load the Whisper model from downloaded HuggingFace cache"""
        try:
            self.logger.debug(f"Loading Whisper model: {self.model_name}")

            # Check if model is installed
            if not self.model_manager.is_model_installed(self.model_name):
                self.logger.error(f"Model '{self.model_name}' is not installed. Please download it first.")
                return False

            # Get model path from model manager
            model_path = self.model_manager.get_model_path(self.model_name)
            if not model_path:
                self.logger.error(f"Could not locate model path for '{self.model_name}'")
                return False

            self.logger.debug(f"Model path resolved to: {model_path}")

            if FASTER_WHISPER_AVAILABLE:
                # Use faster-whisper with HuggingFace model path
                compute_type = "float16" if self.device == "cuda" else "int8"

                # For HuggingFace models, we can use the model name or path
                self.model = WhisperModel(
                    model_size_or_path=model_path,
                    device=self.device,
                    compute_type=compute_type,
                    local_files_only=True  # Use downloaded cache
                )
                self.logger.info(f"Loaded faster-whisper model: {self.model_name} on {self.device}")
            else:
                # Fallback to basic implementation
                self.model = FallbackWhisperModel(model_path, self.device)
                self.logger.info(f"Loaded fallback Whisper model: {self.model_name}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to load model '{self.model_name}': {e}")
            return False

    def add_result_callback(self, callback: Callable[[TranscriptionResult], None]):
        """Add callback for transcription results"""
        self.result_callbacks.append(callback)

    def start_processing(self):
        """Start background processing thread"""
        if self.worker_thread and self.worker_thread.is_alive():
            return

        self.is_processing = True
        self.worker_thread = threading.Thread(target=self._process_queue)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def stop_processing(self):
        """Stop background processing"""
        self.is_processing = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)

    def transcribe_audio(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Optional[TranscriptionResult]:
        """Queue audio for transcription"""
        if not self.model:
            self.logger.error("Model not loaded")
            return None

        # Add to processing queue
        audio_item = {
            'audio': audio_data,
            'sample_rate': sample_rate,
            'timestamp': time.time()
        }

        self.processing_queue.put(audio_item)
        return None  # Results come via callbacks

    def _process_queue(self):
        """Background processing worker"""
        while self.is_processing:
            try:
                # Get audio from queue with timeout
                audio_item = self.processing_queue.get(timeout=1)

                # Process the audio
                result = self._transcribe_audio_sync(
                    audio_item['audio'],
                    audio_item['sample_rate']
                )

                # Send results to callbacks
                if result:
                    for callback in self.result_callbacks:
                        try:
                            callback(result)
                        except Exception as e:
                            self.logger.error(f"Callback error: {e}")

                self.processing_queue.task_done()

            except Empty:
                continue
            except Exception as e:
                self.logger.error(f"Processing error: {e}")

    def _transcribe_audio_sync(self, audio_data: np.ndarray, sample_rate: int) -> Optional[TranscriptionResult]:
        """Synchronously transcribe audio data"""
        start_time = time.time()

        try:
            # Save audio to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name

            # Convert audio to wav format
            self._save_audio_as_wav(audio_data, sample_rate, temp_path)

            if FASTER_WHISPER_AVAILABLE and hasattr(self.model, 'transcribe'):
                # Use faster-whisper
                segments, info = self.model.transcribe(
                    temp_path,
                    language="en",  # Could be made configurable
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500)
                )

                transcription_segments = []
                full_text = ""

                for segment in segments:
                    # Determine speaker (simplified approach)
                    speaker = self.speaker_tracker.identify_speaker(
                        segment.start,
                        segment.end,
                        segment.text
                    )

                    trans_segment = TranscriptionSegment(
                        start_time=segment.start,
                        end_time=segment.end,
                        text=segment.text.strip(),
                        speaker=speaker,
                        confidence=getattr(segment, 'avg_logprob', 0.0)
                    )

                    transcription_segments.append(trans_segment)
                    full_text += segment.text.strip() + " "

                result = TranscriptionResult(
                    segments=transcription_segments,
                    full_text=full_text.strip(),
                    processing_time=time.time() - start_time,
                    model_used=f"faster-whisper-{self.model_name}"
                )

            else:
                # Use fallback implementation
                result = self.model.transcribe(temp_path)

            # Cleanup temp file
            try:
                os.unlink(temp_path)
            except:
                pass

            return result

        except Exception as e:
            self.logger.error(f"Transcription error: {e}")
            return None

    def _save_audio_as_wav(self, audio_data: np.ndarray, sample_rate: int, filepath: str):
        """Save numpy audio data as WAV file"""
        # Ensure audio is in correct format
        if audio_data.dtype != np.int16:
            # Convert float to int16
            if audio_data.dtype in [np.float32, np.float64]:
                audio_data = (audio_data * 32767).astype(np.int16)

        with wave.open(filepath, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes per sample (16-bit)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())

class SpeakerTracker:
    """Simple speaker identification and tracking"""

    def __init__(self):
        self.speakers = {}
        self.current_speaker = "Therapist"
        self.last_switch_time = 0
        self.min_switch_interval = 2.0  # Minimum seconds between speaker switches

    def identify_speaker(self, start_time: float, end_time: float, text: str) -> str:
        """Identify speaker based on audio characteristics and content"""
        # Simple heuristic-based approach
        # In a real implementation, this would use audio features

        # Check for speaker indicators in text
        text_lower = text.lower()

        # Common therapist phrases
        therapist_indicators = [
            "how do you feel", "tell me about", "what do you think",
            "can you describe", "i understand", "let's explore",
            "it sounds like", "help me understand"
        ]

        # Common client responses
        client_indicators = [
            "i feel", "i think", "i don't know", "maybe", "i guess",
            "it's hard", "i can't", "i want", "i need"
        ]

        # Check for indicators
        therapist_score = sum(1 for indicator in therapist_indicators if indicator in text_lower)
        client_score = sum(1 for indicator in client_indicators if indicator in text_lower)

        # Time-based switching logic
        time_since_switch = start_time - self.last_switch_time

        if time_since_switch > self.min_switch_interval:
            if therapist_score > client_score and therapist_score > 0:
                new_speaker = "Therapist"
            elif client_score > therapist_score and client_score > 0:
                new_speaker = "Client"
            else:
                # Default to alternating if no clear indicators
                new_speaker = "Client" if self.current_speaker == "Therapist" else "Therapist"

            if new_speaker != self.current_speaker:
                self.current_speaker = new_speaker
                self.last_switch_time = start_time

        return self.current_speaker

class FallbackWhisperModel:
    """Fallback Whisper implementation when faster-whisper is not available"""

    def __init__(self, model_path: str, device: str):
        self.model_path = model_path
        self.device = device
        self.logger = logging.getLogger(__name__)

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """Transcribe audio file (fallback implementation)"""
        start_time = time.time()

        # This is a placeholder - in reality you'd implement
        # basic Whisper functionality or use OpenAI's whisper library

        # For now, return dummy data
        segments = [
            TranscriptionSegment(
                start_time=0.0,
                end_time=3.0,
                text="Fallback transcription - please install faster-whisper for full functionality",
                speaker="Unknown",
                confidence=0.5
            )
        ]

        return TranscriptionResult(
            segments=segments,
            full_text=segments[0].text,
            processing_time=time.time() - start_time,
            model_used="fallback"
        )

def test_local_whisper():
    """Test the local Whisper manager"""
    print("Testing Local Whisper Manager")
    print("=" * 40)

    # Create dummy audio data
    sample_rate = 16000
    duration = 3  # 3 seconds
    audio_data = np.random.randint(-1000, 1000, sample_rate * duration, dtype=np.int16)

    def on_result(result: TranscriptionResult):
        print(f"\nTranscription Result:")
        print(f"Model: {result.model_used}")
        print(f"Processing time: {result.processing_time:.2f}s")
        print(f"Full text: {result.full_text}")
        print(f"Segments: {len(result.segments)}")
        for i, segment in enumerate(result.segments):
            print(f"  {i+1}. [{segment.start_time:.1f}s-{segment.end_time:.1f}s] {segment.speaker}: {segment.text}")

    # Test with small model
    manager = LocalWhisperManager("small")

    if not manager.model:
        print("Model not loaded - run model download first")
        return

    manager.add_result_callback(on_result)
    manager.start_processing()

    print("Sending test audio for transcription...")
    manager.transcribe_audio(audio_data, sample_rate)

    # Wait for processing
    time.sleep(5)
    manager.stop_processing()
    print("Test completed")

if __name__ == "__main__":
    test_local_whisper()