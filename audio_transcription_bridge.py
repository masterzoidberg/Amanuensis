#!/usr/bin/env python3
"""
Audio Transcription Bridge
Connects AudioManager's raw audio output to EnhancedWhisperManager's input.
Handles audio chunking, format conversion, and manages the streaming process.
"""

import threading
import time
import numpy as np
import queue
from typing import Callable, Optional, Dict, Any
from collections import deque
import logging

# Import soundcard for loopback capture
try:
    import soundcard as sc
    SOUNDCARD_AVAILABLE = True
except ImportError:
    SOUNDCARD_AVAILABLE = False
    sc = None

# Import COM initialization helper for Windows WASAPI
try:
    from com_initializer import com_audio_safe, initialize_com_for_audio, com_context
    COM_HELPER_AVAILABLE = True
except ImportError:
    COM_HELPER_AVAILABLE = False
    # Fallback decorators that do nothing on non-Windows systems
    def com_audio_safe(func):
        return func
    def initialize_com_for_audio():
        return True

# Import project modules
try:
    from audio_manager import AudioManager
    from enhanced_whisper_manager import EnhancedWhisperManager, TranscriptionResult
    from logger_config import get_logger
except ImportError as e:
    print(f"Warning: Could not import required modules: {e}")
    # Fallback for testing
    logging.basicConfig(level=logging.INFO)
    def get_logger(name):
        return logging.getLogger(name)

# Import configuration
try:
    from transcription_config import (
        get_transcription_config,
        LOOPBACK_DEVICE_NAME,
        CAPTURE_SAMPLERATE,
        CAPTURE_CHANNELS,
        CAPTURE_FRAMES,
        AUDIO_CAPTURE_MODE
    )
    config = get_transcription_config()
except ImportError:
    # Fallback configuration using constants
    LOOPBACK_DEVICE_NAME = None
    CAPTURE_SAMPLERATE = 44100
    CAPTURE_CHANNELS = 2
    CAPTURE_FRAMES = 1024
    AUDIO_CAPTURE_MODE = "auto"

    class FallbackConfig:
        def get(self, key, default=None):
            defaults = {
                'loopback_device_name': LOOPBACK_DEVICE_NAME,
                'capture_samplerate': CAPTURE_SAMPLERATE,
                'capture_channels': CAPTURE_CHANNELS,
                'capture_frames': CAPTURE_FRAMES,
                'audio_capture_mode': AUDIO_CAPTURE_MODE
            }
            return defaults.get(key, default)
    config = FallbackConfig()

# Import bounded queue size from config
try:
    from transcription_config import AUDIO_Q_MAX
except ImportError:
    AUDIO_Q_MAX = 32

# Global audio queue for reliable frame delivery
audio_q = queue.Queue(maxsize=AUDIO_Q_MAX)
_last_drop_log = 0.0

def push_audio_frames(frames: np.ndarray, samplerate: int):
    """Push audio frames to the bounded queue with overflow handling."""
    global _last_drop_log
    
    # Create audio packet with timestamp
    pkt = {
        "t": time.time(),  # timestamp
        "sr": samplerate,  # sample rate
        "data": frames.astype("float32", copy=False)  # audio data
    }
    
    try:
        audio_q.put_nowait(pkt)
    except queue.Full:
        # Queue is full - drop oldest packet and add new one
        try:
            audio_q.get_nowait()  # drop oldest
        except queue.Empty:
            pass
        audio_q.put_nowait(pkt)
        
        # Log overflow (throttled to once per second)
        if time.time() - _last_drop_log > 1.0:
            logger = get_logger('audio_bridge')
            logger.debug("audio_q overflow: dropping oldest frame")
            _last_drop_log = time.time()

@com_audio_safe
def resolve_loopback_mic():
    """Resolve the loopback microphone for the specified speaker device."""
    if not SOUNDCARD_AVAILABLE:
        raise ImportError("soundcard module not available")

    device_name = config.get('loopback_device_name')
    if device_name:
        spk = sc.get_speaker(device_name)
    else:
        spk = sc.default_speaker()

    mic = sc.get_microphone(id=spk.name, include_loopback=True)
    return mic, spk

@com_audio_safe
def preflight_loopback(mic):
    """Preflight test for loopback microphone (250ms test)."""
    samplerate = config.get('capture_samplerate', 44100)
    test_frames = int(samplerate * 0.25)  # 250ms test

    with mic.recorder(samplerate=samplerate) as rec:
        _ = rec.record(numframes=test_frames)

class LoopbackCaptureSoundcard:
    """Soundcard-based loopback capture for system audio."""
    
    def __init__(self, mic, audio_callback=None):
        self.mic = mic
        self.audio_callback = audio_callback
        self._stop = threading.Event()
        self._th = None
        self.logger = get_logger('loopback_capture')
        
        self.samplerate = config.get('capture_samplerate', 44100)
        self.channels = config.get('capture_channels', 2)
        self.frames = config.get('capture_frames', 1024)
    
    def start(self):
        """Start the loopback capture thread."""
        if self._th and self._th.is_alive():
            self.logger.warning("Loopback capture already running")
            return
        
        def run():
            # Initialize COM for WASAPI in this thread
            if not initialize_com_for_audio():
                self.logger.error("Failed to initialize COM for WASAPI loopback")
                return

            try:
                with self.mic.recorder(samplerate=self.samplerate) as rec:
                    self.logger.info(f"Loopback capture started: {self.samplerate}Hz, {self.channels}ch, {self.frames} frames")

                    while not self._stop.is_set():
                        frames = rec.record(numframes=self.frames)
                        audio_data = np.asarray(frames, dtype="float32")
                        
                        # Push audio frames to the bounded queue
                        push_audio_frames(audio_data, self.samplerate)
                        
                        # Also call audio callback if provided (for backward compatibility)
                        if self.audio_callback:
                            audio_int16 = (audio_data * 32767).astype(np.int16)
                            self.audio_callback(audio_int16.tobytes())
                            
            except Exception as e:
                self.logger.error(f"Loopback capture error: {e}")
        
        self._th = threading.Thread(target=run, daemon=True)
        self._th.start()
    
    def stop(self):
        """Stop the loopback capture thread."""
        self._stop.set()
        if self._th:
            self._th.join(timeout=2)
            if self._th.is_alive():
                self.logger.warning("Loopback capture thread did not terminate gracefully")

class AudioTranscriptionBridge:
    """
    Connects AudioManager's raw audio output to EnhancedWhisperManager's input.
    Handles audio chunking, format conversion, and manages the streaming process.
    """
    
    def __init__(self, audio_manager: 'AudioManager', whisper_manager: 'EnhancedWhisperManager'):
        self.logger = get_logger('audio_transcription_bridge')
        self.audio_manager = audio_manager
        self.whisper_manager = whisper_manager
        self.transcription_callbacks = []

        self.is_streaming = False
        self.stream_thread: Optional[threading.Thread] = None
        self.audio_buffer_queue = deque()  # Buffer for raw audio chunks from AudioManager

        # Parameters for chunking audio to send to Whisper
        # Whisper models are typically trained on 30-second audio segments.
        # We'll process in smaller chunks for real-time, but keep context.
        self.whisper_chunk_size_seconds = 5  # Process audio in 5-second chunks
        self.sample_rate = getattr(audio_manager, 'sample_rate', 44100)  # Default to 44100
        self.channels = getattr(audio_manager, 'channels', 2)  # Default to stereo
        
        # Calculate frames per chunk
        self.chunk_frames = int(self.whisper_chunk_size_seconds * self.sample_rate)
        self.current_audio_chunk = np.empty(0, dtype=np.int16)  # Buffer for accumulating audio

        self.logger.info(f"AudioTranscriptionBridge initialized. Whisper chunk size: {self.whisper_chunk_size_seconds}s")

        # Register self as a callback for AudioManager to receive raw audio
        if hasattr(audio_manager, 'add_audio_data_callback'):
            self.audio_manager.add_audio_data_callback(self._on_audio_data_received)
            self.logger.info("Audio callback registered successfully with AudioManager")
        else:
            self.logger.error("AudioManager doesn't support audio data callbacks - transcription won't work")
            
        # Register whisper manager's callback to receive transcription results
        if hasattr(whisper_manager, 'add_result_callback'):
            self.whisper_manager.add_result_callback(self._on_transcription_result)
        else:
            self.logger.warning("WhisperManager doesn't support result callbacks")

    def add_transcription_callback(self, callback: Callable[[TranscriptionResult], None]):
        """Add a callback to receive transcription results."""
        self.transcription_callbacks.append(callback)
        self.logger.debug(f"Added transcription callback. Total callbacks: {len(self.transcription_callbacks)}")

    def _on_audio_data_received(self, audio_data: np.ndarray, sample_rate: int):
        """Callback from AudioManager when new audio data is available."""
        if self.is_streaming:
            # AudioManager now sends float32 audio data directly
            push_audio_frames(audio_data, sample_rate)

            # Keep old buffer for backward compatibility (convert back to bytes)
            audio_bytes = (audio_data * 32768.0).astype(np.int16).tobytes()
            self.audio_buffer_queue.append(audio_bytes)
            # Limit buffer size to prevent memory issues
            if len(self.audio_buffer_queue) > 100:  # Keep last 100 chunks
                self.audio_buffer_queue.popleft()

    def _on_transcription_result(self, result):
        """Callback from EnhancedWhisperManager when a transcription result is ready."""
        self.logger.debug(f"Received transcription result with {len(result.segments) if hasattr(result, 'segments') else 0} segments")
        
        for callback in self.transcription_callbacks:
            try:
                callback(result)
            except Exception as e:
                self.logger.error(f"Error in transcription callback: {e}")

    def start_streaming(self) -> bool:
        """Starts the audio processing and transcription streaming."""
        if self.is_streaming:
            self.logger.info("Transcription streaming already active.")
            return True

        # Check if whisper manager is ready
        if not hasattr(self.whisper_manager, 'model_loaded') or not self.whisper_manager.model_loaded:
            self.logger.warning("Whisper model not loaded. Attempting to load...")
            try:
                if hasattr(self.whisper_manager, 'load_model'):
                    if not self.whisper_manager.load_model():
                        self.logger.error("Failed to load Whisper model, cannot start streaming.")
                        return False
                else:
                    self.logger.error("WhisperManager doesn't support model loading.")
                    return False
            except Exception as e:
                self.logger.error(f"Error loading Whisper model: {e}")
                return False

        self.is_streaming = True
        
        # Ensure whisper manager is processing
        if hasattr(self.whisper_manager, 'start_processing'):
            self.whisper_manager.start_processing()
            
        self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.stream_thread.start()
        self.logger.info("Audio transcription streaming started.")
        return True

    def stop_streaming(self):
        """Stops the audio processing and transcription streaming."""
        if not self.is_streaming:
            self.logger.info("Transcription streaming not active.")
            return

        self.is_streaming = False
        if self.stream_thread:
            self.stream_thread.join(timeout=2)  # Give thread a moment to finish
            if self.stream_thread.is_alive():
                self.logger.warning("Transcription stream thread did not terminate gracefully.")
                
        # Stop whisper processing
        if hasattr(self.whisper_manager, 'stop_processing'):
            self.whisper_manager.stop_processing()
        
        # Stop loopback capture if running
        if hasattr(self, 'loopback_capture') and self.loopback_capture:
            self.loopback_capture.stop()
            self.loopback_capture = None
            
        self.audio_buffer_queue.clear()
        self.current_audio_chunk = np.empty(0, dtype=np.int16)
        self.logger.info("Audio transcription streaming stopped.")

    def start_recording_with_soundcard(self, ui_callback=None, toast_callback=None) -> bool:
        """Start recording with soundcard loopback capture and fallback system."""
        capture_mode = config.get('audio_capture_mode', 'auto')

        # Try soundcard loopback first if enabled
        if capture_mode in ("auto", "loopback") and SOUNDCARD_AVAILABLE:
            try:
                self.logger.info("Attempting soundcard loopback capture...")
                mic, spk = resolve_loopback_mic()
                preflight_loopback(mic)

                # Start loopback capture
                self.loopback_capture = LoopbackCaptureSoundcard(mic, self._on_audio_data_received)
                self.loopback_capture.start()

                self.logger.info(f"System audio path = loopback (Device: {spk.name})")
                return True

            except Exception as e:
                self.logger.warning(f"Loopback failed: {e} → trying Stereo Mix")
                if ui_callback:
                    ui_callback("Loopback failed, trying Stereo Mix...", "warning")

        # Fallback to Stereo Mix
        if capture_mode in ("auto", "stereo_mix"):
            try:
                self.logger.info("Attempting Stereo Mix capture...")
                success = self._start_stereo_mix()
                if success:
                    self.logger.info("System audio path = stereo_mix")
                    return True
                else:
                    raise Exception("Stereo Mix initialization failed")

            except Exception as e:
                self.logger.warning(f"Stereo Mix failed: {e} → mic-only")
                if ui_callback:
                    ui_callback("System audio unavailable → recording mic-only.", "warning")

        # Final fallback: mic-only
        self.logger.info("Using mic-only mode")
        success = self._start_mic_only()
        if not success and toast_callback:
            toast_callback("System audio unavailable → recording mic-only.")
        return success

    def _start_stereo_mix(self) -> bool:
        """Start stereo mix capture (integrate with existing AudioManager)."""
        # This should integrate with the existing AudioManager's stereo mix functionality
        # For now, return False to indicate not implemented
        self.logger.info("Stereo Mix capture integration not implemented")
        return False

    def _start_mic_only(self) -> bool:
        """Start microphone-only capture (integrate with existing AudioManager)."""
        # This should integrate with the existing AudioManager's mic functionality
        # For now, return False to indicate not implemented
        self.logger.info("Microphone-only capture integration not implemented")
        return False

    def _stream_loop(self):
        """Main loop for processing audio chunks and sending to Whisper."""
        self.logger.debug("Transcription stream loop started.")
        
        while self.is_streaming:
            try:
                # Accumulate audio from the buffer queue
                chunks_processed = 0
                while self.audio_buffer_queue and chunks_processed < 10:  # Process up to 10 chunks per iteration
                    raw_bytes = self.audio_buffer_queue.popleft()
                    new_audio = np.frombuffer(raw_bytes, dtype=np.int16)
                    self.current_audio_chunk = np.concatenate((self.current_audio_chunk, new_audio))
                    chunks_processed += 1

                # Process accumulated audio if enough is available
                if len(self.current_audio_chunk) >= self.chunk_frames * self.channels:
                    # Take a chunk for processing
                    process_chunk_stereo = self.current_audio_chunk[:self.chunk_frames * self.channels]
                    
                    # Convert to mono float32 for Whisper
                    # Assuming stereo data is interleaved (LRLR...)
                    if self.channels == 2:
                        # Take left channel (every other sample starting from 0)
                        process_chunk_mono_int16 = process_chunk_stereo[0::2]
                    else:
                        # Already mono
                        process_chunk_mono_int16 = process_chunk_stereo
                    
                    # Convert to float32 normalized to [-1, 1]
                    process_chunk_float32 = process_chunk_mono_int16.astype(np.float32) / 32768.0

                    # Send to Whisper manager
                    if hasattr(self.whisper_manager, 'transcribe_audio_chunk'):
                        self.whisper_manager.transcribe_audio_chunk(process_chunk_float32, self.sample_rate)
                    else:
                        self.logger.error("WhisperManager doesn't support audio chunk transcription")

                    # Remove processed chunk from buffer
                    self.current_audio_chunk = self.current_audio_chunk[self.chunk_frames * self.channels:]
                    
                    self.logger.debug(f"Processed audio chunk: {len(process_chunk_float32)} samples")
                else:
                    # Not enough audio, wait a bit
                    time.sleep(0.05)
                    
            except Exception as e:
                self.logger.error(f"Error in transcription stream loop: {e}")
                # Attempt to continue or stop based on error severity
                time.sleep(1)  # Prevent busy-loop on continuous errors
                
        self.logger.debug("Transcription stream loop ended.")

    def get_status(self) -> Dict[str, Any]:
        """Get current bridge status for debugging"""
        return {
            'streaming': self.is_streaming,
            'audio_buffer_size': len(self.audio_buffer_queue),
            'current_chunk_size': len(self.current_audio_chunk),
            'callbacks_registered': len(self.transcription_callbacks),
            'whisper_model_loaded': getattr(self.whisper_manager, 'model_loaded', False) if self.whisper_manager else False
        }

def test_audio_transcription_bridge():
    """Test the audio transcription bridge (mock test)"""
    print("Testing Audio Transcription Bridge")
    print("=" * 40)
    
    # This would require actual AudioManager and WhisperManager instances
    print("Note: This test requires actual AudioManager and EnhancedWhisperManager instances")
    print("Bridge module loaded successfully!")

if __name__ == "__main__":
    test_audio_transcription_bridge()