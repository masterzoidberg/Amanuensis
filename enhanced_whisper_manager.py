#!/usr/bin/env python3
"""
Enhanced Local Whisper Transcription Manager
Real faster-whisper integration with live audio streaming
"""

import numpy as np
import threading
import time
import os
import tempfile
import wave
from typing import Dict, List, Callable, Optional, Tuple, Generator
from dataclasses import dataclass
from queue import Queue, Empty
import logging
import json
from pathlib import Path
import queue
import shutil

# Try to import faster-whisper
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    print("Warning: faster-whisper not available")

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# Deterministic model loading functions
def decide_device():
    """Decide which device to use for model loading."""
    from transcription_config import MODEL_DEVICE

    if MODEL_DEVICE in ["auto", "cuda"] and TORCH_AVAILABLE and torch.cuda.is_available():
        return "cuda"
    else:
        return "cpu"

def decide_compute(device):
    """Decide compute type based on device and configuration."""
    from transcription_config import MODEL_COMPUTE

    if MODEL_COMPUTE not in ("auto", "float16", "int8_float16", "int8"):
        return "int8"

    if MODEL_COMPUTE != "auto":
        return MODEL_COMPUTE

    # Auto-selection based on device
    return "float16" if device == "cuda" else "int8"

def load_whisper_model():
    """Load whisper model with deterministic settings."""
    from transcription_config import MODEL_SIZE, MODEL_CACHE_DIR
    from logger_config import get_logger

    logger = get_logger('model_loader')

    dev = decide_device()
    comp = decide_compute(dev)
    cache = os.path.expandvars(MODEL_CACHE_DIR) if MODEL_CACHE_DIR else None

    logger.info(f"Loading model: {MODEL_SIZE} • {dev} • {comp}")

    try:
        model = WhisperModel(
            MODEL_SIZE,
            device=dev,
            compute_type=comp,
            download_root=cache
        )
        logger.info(f"Model ready: {MODEL_SIZE} • {dev} • {comp}")
        return model
    except Exception as e:
        logger.error(f"Model load failed: {e}\nCache: {cache}\nTry: Settings → Reset model cache.")
        raise

def reset_model_cache(model_size=None):
    """Reset model cache by deleting only the selected model directory."""
    from transcription_config import MODEL_SIZE, MODEL_CACHE_DIR
    from logger_config import get_logger

    logger = get_logger('cache_reset')

    if model_size is None:
        model_size = MODEL_SIZE

    cache_dir = os.path.expandvars(MODEL_CACHE_DIR) if MODEL_CACHE_DIR else None
    if not cache_dir:
        logger.warning("No cache directory configured")
        return False

    # Find model directory pattern
    cache_path = Path(cache_dir)
    model_patterns = [
        f"models--Systran--faster-whisper-{model_size}",
        f"faster-whisper-{model_size}",
        model_size
    ]

    deleted = False
    for pattern in model_patterns:
        model_dir = cache_path / pattern
        if model_dir.exists():
            try:
                shutil.rmtree(model_dir)
                logger.info(f"Deleted model cache: {model_dir}")
                deleted = True
            except Exception as e:
                logger.error(f"Failed to delete model cache {model_dir}: {e}")

    if not deleted:
        logger.warning(f"No cache found for model {model_size} in {cache_dir}")

    return deleted

@dataclass
class TranscriptionSegment:
    """Single transcription segment with speaker info"""
    start_time: float
    end_time: float
    text: str
    speaker: str = "Unknown"
    confidence: float = 0.0
    is_partial: bool = False

@dataclass
class TranscriptionResult:
    """Complete transcription result"""
    segments: List[TranscriptionSegment]
    full_text: str
    processing_time: float
    model_used: str
    language: str = "en"

class ModelLoadError(Exception):
    """Raised when model loading fails"""
    pass

class AudioFormatError(Exception):
    """Raised when audio format is invalid"""
    pass

class InferenceError(Exception):
    """Raised when transcription inference fails"""
    pass

class EnhancedWhisperManager:
    """Enhanced Whisper transcription manager with real-time streaming"""

    def __init__(self, model_name: str = None, device: str = None):
        # Setup logging
        from logger_config import get_logger
        self.logger = get_logger('enhanced_whisper')
        
        # Load configuration
        from transcription_config import get_transcription_config
        self.config = get_transcription_config()
        
        # Model configuration
        self.model_name = model_name or self.config['model_size']
        self.device, self.compute_type = self.config.get_device_config() if device is None else (device, 'auto')
        if device is not None:
            self.device = device
            self.compute_type = 'float16' if device == 'cuda' else 'int8'
        
        # Model state
        self.model = None
        self.model_loaded = False
        self.model_loading = False
        
        # Processing state
        self.processing_queue = Queue(maxsize=10)  # Limit queue size
        self.result_callbacks = []
        self.is_processing = False
        self.worker_thread = None
        
        # Real-time streaming
        self.audio_buffer = []
        self.last_transcription_time = 0
        self.chunk_duration = self.config['chunk_duration']
        self.chunk_overlap = self.config['chunk_overlap']
        
        # Speaker tracking
        self.speaker_tracker = EnhancedSpeakerTracker()
        
        # Statistics
        self.stats = {
            'total_segments': 0,
            'total_processing_time': 0,
            'average_latency': 0,
            'errors': 0
        }
        
        # Health monitoring
        try:
            from transcription_health_monitor import get_health_monitor, update_model_status
            self.health_monitor = get_health_monitor()
            self.health_monitor.start_monitoring()
        except Exception as e:
            self.logger.warning(f"Health monitoring not available: {e}")
            self.health_monitor = None
        
        self.logger.info(f"Enhanced Whisper Manager initialized: model={self.model_name}, device={self.device}")
        
        # Transcriber worker state
        self.transcriber_running = False
        self.transcriber_thread = None
        self.sliding_window = []  # For rolling chunk inference
        self.window_duration = 5.0  # seconds
        self.window_overlap = 1.0  # seconds

    def ensure_mono_and_resample(self, audio_data: np.ndarray, source_sr: int, target_sr: int = 16000) -> np.ndarray:
        """Convert audio to mono and resample to target sample rate."""
        try:
            # Convert to mono if stereo
            if len(audio_data.shape) > 1 and audio_data.shape[1] > 1:
                audio_data = np.mean(audio_data, axis=1)
            
            # Resample if needed
            if source_sr != target_sr:
                # Simple linear interpolation resampling
                ratio = target_sr / source_sr
                new_length = int(len(audio_data) * ratio)
                audio_data = np.interp(
                    np.linspace(0, len(audio_data), new_length),
                    np.arange(len(audio_data)),
                    audio_data
                )
            
            return audio_data.astype(np.float32)
            
        except Exception as e:
            self.logger.error(f"Resampling error: {e}")
            return audio_data.astype(np.float32)

    def transcriber_worker(self):
        """Worker thread that consumes audio packets from the global queue."""
        self.logger.info("Transcriber worker started")
        
        # Import the global audio queue
        try:
            from audio_transcription_bridge import audio_q
        except ImportError:
            self.logger.error("Could not import audio queue from audio_transcription_bridge")
            return
        
        while self.transcriber_running:
            try:
                # Get audio packet with timeout
                pkt = audio_q.get(timeout=1.0)
                
                # Process the audio packet
                audio = self.ensure_mono_and_resample(pkt["data"], pkt["sr"], target_sr=16000)
                
                # Add to sliding window
                self.sliding_window.append({
                    'audio': audio,
                    'timestamp': pkt["t"],
                    'duration': len(audio) / 16000.0
                })
                
                # Maintain sliding window size
                total_duration = sum(item['duration'] for item in self.sliding_window)
                while total_duration > self.window_duration:
                    self.sliding_window.pop(0)
                    total_duration = sum(item['duration'] for item in self.sliding_window)
                
                # Run inference on rolling chunks
                if len(self.sliding_window) > 0:
                    self._process_sliding_window()
                    
            except queue.Empty:
                # Timeout - continue
                continue
            except Exception as e:
                self.logger.error(f"Transcriber worker error: {e}")
                time.sleep(0.1)
        
        self.logger.info("Transcriber worker stopped")

    def reset_cache_and_reload(self) -> bool:
        """Reset model cache and reload the model."""
        try:
            # Stop processing if running
            was_processing = self.is_processing
            if was_processing:
                self.stop_processing()

            # Reset model state
            self.model = None
            self.model_loaded = False

            # Reset cache
            success = reset_model_cache(self.model_name)
            if success:
                self.logger.info(f"Model cache reset for {self.model_name}")

            # Reload model
            if self.load_model():
                self.logger.info("Model reloaded successfully after cache reset")
                # Restart processing if it was running
                if was_processing:
                    self.start_processing()
                return True
            else:
                self.logger.error("Failed to reload model after cache reset")
                return False

        except Exception as e:
            self.logger.error(f"Error during cache reset and reload: {e}")
            return False

    def _process_sliding_window(self):
        """Process the sliding window for rolling chunk inference."""
        if not self.model_loaded or len(self.sliding_window) == 0:
            return
        
        try:
            # Concatenate audio from sliding window
            audio_chunks = [item['audio'] for item in self.sliding_window]
            combined_audio = np.concatenate(audio_chunks)
            
            # Only process if we have enough audio (at least 1 second)
            if len(combined_audio) < 16000:
                return
            
            # Get base timestamp from first chunk
            base_timestamp = self.sliding_window[0]['timestamp']
            
            # Run transcription
            start_time = time.time()
            segments, info = self.model.transcribe(
                combined_audio,
                beam_size=1,
                language="en",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Convert segments to our format
            transcription_segments = []
            for segment in segments:
                # Adjust timestamps to absolute time
                abs_start = base_timestamp + segment.start
                abs_end = base_timestamp + segment.end
                
                transcription_segments.append(TranscriptionSegment(
                    start_time=abs_start,
                    end_time=abs_end,
                    text=segment.text.strip(),
                    speaker=self.speaker_tracker.assign_speaker(segment.text),
                    confidence=getattr(segment, 'avg_logprob', 0.0),
                    is_partial=False
                ))
            
            # Create result
            if transcription_segments:
                result = TranscriptionResult(
                    segments=transcription_segments,
                    full_text=" ".join([seg.text for seg in transcription_segments]),
                    processing_time=time.time() - start_time,
                    model_used=self.model_name,
                    language=info.language if hasattr(info, 'language') else "en"
                )
                
                # Send to callbacks
                for callback in self.result_callbacks:
                    try:
                        callback(result)
                    except Exception as e:
                        self.logger.error(f"Callback error: {e}")
                
                # Update statistics
                self.stats['total_segments'] += len(transcription_segments)
                self.stats['total_processing_time'] += result.processing_time
                self.stats['average_latency'] = self.stats['total_processing_time'] / max(1, self.stats['total_segments'])
                
        except Exception as e:
            self.logger.error(f"Sliding window processing error: {e}")
            self.stats['errors'] += 1

    def start_transcriber_worker(self):
        """Start the transcriber worker thread."""
        if self.transcriber_running:
            self.logger.debug("Transcriber worker already running")
            return
        
        if not self.model_loaded:
            if not self.load_model():
                raise ModelLoadError("Cannot start transcriber: model not loaded")
        
        self.transcriber_running = True
        self.transcriber_thread = threading.Thread(target=self.transcriber_worker, daemon=True)
        self.transcriber_thread.start()
        self.logger.info("Transcriber worker started")

    def stop_transcriber_worker(self):
        """Stop the transcriber worker thread."""
        if not self.transcriber_running:
            return
        
        self.transcriber_running = False
        if self.transcriber_thread:
            self.transcriber_thread.join(timeout=5)
            if self.transcriber_thread.is_alive():
                self.logger.warning("Transcriber worker thread did not stop gracefully")
        
        self.logger.info("Transcriber worker stopped")

    def get_model_status(self) -> Dict[str, any]:
        """Get current model status including availability of downloaded models"""
        # Check if the current model is available for loading (downloaded)
        model_available = False
        try:
            # Check if model is already loaded
            if self.model_loaded:
                model_available = True
            else:
                # Check if model is downloaded and available for loading
                from whisper_model_downloader import WhisperModelManager
                model_manager = WhisperModelManager()
                model_available = model_manager.is_model_installed(self.model_name)
        except Exception as e:
            self.logger.debug(f"Error checking model availability: {e}")
            model_available = False

        return {
            'model_name': self.model_name,
            'device': self.device,
            'compute_type': self.compute_type,
            'loaded': self.model_loaded,
            'loading': self.model_loading,
            'available': FASTER_WHISPER_AVAILABLE,
            'model_downloaded': model_available,  # NEW: indicates if model files are available
            'stats': self.stats.copy()
        }

    def load_model(self) -> bool:
        """Load the Whisper model using deterministic loading"""
        if self.model_loaded:
            return True

        if self.model_loading:
            return False

        self.model_loading = True

        try:
            if not FASTER_WHISPER_AVAILABLE:
                raise ModelLoadError("faster-whisper not available")

            # Use deterministic model loading
            self.model = load_whisper_model()

            # Update our device/compute info from the deterministic function
            self.device = decide_device()
            self.compute_type = decide_compute(self.device)
            
            # Test the model with a small audio sample
            self._test_model()
            
            self.model_loaded = True
            self.logger.info(f"Model {self.model_name} loaded successfully on {self.device}")
            
            # Report health status
            if self.health_monitor:
                from transcription_health_monitor import update_model_status
                update_model_status(True)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")
            self.model = None
            self.model_loaded = False
            
            # Report health status
            if self.health_monitor:
                from transcription_health_monitor import report_model_load_error, update_model_status
                report_model_load_error(f"Failed to load model: {e}", model=self.model_name, device=self.device)
                update_model_status(False)
            
            raise ModelLoadError(f"Failed to load model: {e}")
        finally:
            self.model_loading = False

    def _test_model(self):
        """Test the model with a small audio sample"""
        temp_file_path = None
        try:
            # Create a short test audio (1 second of silence)
            sample_rate = 16000
            test_audio = np.zeros(sample_rate, dtype=np.float32)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file_path = temp_file.name
                if SOUNDFILE_AVAILABLE:
                    sf.write(temp_file_path, test_audio, sample_rate)
                else:
                    self._save_audio_as_wav(test_audio, sample_rate, temp_file_path)

            # Test transcription (file is now closed)
            segments, info = self.model.transcribe(
                temp_file_path,
                beam_size=1,
                language="en"
            )

            # Consume generator to test
            list(segments)
                
        except Exception as e:
            raise ModelLoadError(f"Model test failed: {e}")
        finally:
            # Clean up temp file with Windows-compatible retry logic
            if temp_file_path:
                self._safe_cleanup_temp_file(temp_file_path)

    def _safe_cleanup_temp_file(self, file_path: str, max_retries: int = 3):
        """Safely cleanup temporary file with Windows-compatible retry logic"""
        import gc
        for attempt in range(max_retries):
            try:
                # Force garbage collection to release any file handles
                gc.collect()

                if os.path.exists(file_path):
                    # On Windows, wait a bit for handles to release
                    if attempt > 0:
                        time.sleep(0.1 * attempt)
                    os.unlink(file_path)
                    self.logger.debug(f"Successfully cleaned up temp file: {file_path}")
                return

            except PermissionError as e:
                if attempt < max_retries - 1:
                    self.logger.debug(f"Temp file cleanup attempt {attempt + 1} failed, retrying...")
                    time.sleep(0.2 * (attempt + 1))
                else:
                    self.logger.warning(f"Failed to cleanup temp file after {max_retries} attempts: {file_path}")
            except FileNotFoundError:
                # File already deleted
                return
            except Exception as e:
                self.logger.warning(f"Unexpected error cleaning up temp file: {e}")
                return

    def add_result_callback(self, callback: Callable[[TranscriptionResult], None]):
        """Add callback for transcription results"""
        self.result_callbacks.append(callback)
        self.logger.debug(f"Added result callback, total: {len(self.result_callbacks)}")

    def start_processing(self):
        """Start background processing thread"""
        if not self.model_loaded:
            if not self.load_model():
                raise ModelLoadError("Cannot start processing: model not loaded")
        
        if self.worker_thread and self.worker_thread.is_alive():
            self.logger.debug("Processing already running")
            return
        
        self.is_processing = True
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()
        
        # Also start the transcriber worker for the hardened audio bridge
        self.start_transcriber_worker()
        
        self.logger.info("Started background transcription processing")

    def stop_processing(self):
        """Stop background processing"""
        self.is_processing = False
        
        # Stop transcriber worker first
        self.stop_transcriber_worker()
        
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
            if self.worker_thread.is_alive():
                self.logger.warning("Processing thread did not stop gracefully")
        self.logger.info("Stopped background transcription processing")

    def transcribe_audio_chunk(self, audio_data: np.ndarray, sample_rate: int = 16000, timestamp: float = None) -> None:
        """Queue audio chunk for real-time transcription"""
        if not self.model_loaded:
            self.logger.warning("Model not loaded, cannot transcribe")
            return
        
        if timestamp is None:
            timestamp = time.time()
        
        # Validate audio data
        if len(audio_data) == 0:
            return
        
        # Add to processing queue (non-blocking)
        audio_item = {
            'audio': audio_data.copy(),
            'sample_rate': sample_rate,
            'timestamp': timestamp,
            'chunk_id': int(timestamp * 1000)  # Unique ID based on timestamp
        }
        
        try:
            self.processing_queue.put_nowait(audio_item)
        except:
            # Queue full - drop oldest item and add new one
            try:
                self.processing_queue.get_nowait()
                self.processing_queue.put_nowait(audio_item)
                self.logger.debug("Dropped audio chunk due to queue overflow")
            except:
                pass

    def _process_queue(self):
        """Background processing worker"""
        self.logger.debug("Started processing queue worker")
        
        while self.is_processing:
            try:
                # Get audio from queue with timeout
                audio_item = self.processing_queue.get(timeout=1)
                
                # Process the audio
                start_time = time.time()
                result = self._transcribe_audio_sync(
                    audio_item['audio'],
                    audio_item['sample_rate'],
                    audio_item['timestamp']
                )
                
                processing_time = time.time() - start_time
                
                # Update statistics and health metrics
                if result:
                    self.stats['total_segments'] += len(result.segments)
                    self.stats['total_processing_time'] += processing_time
                    self.stats['average_latency'] = self.stats['total_processing_time'] / max(1, self.stats['total_segments'])
                    
                    # Update health metrics
                    if self.health_monitor:
                        from transcription_health_monitor import update_inference_latency, update_queue_size, increment_segments_processed
                        update_inference_latency(processing_time)
                        update_queue_size(self.processing_queue.qsize())
                        for _ in result.segments:
                            increment_segments_processed()
                    
                    # Send results to callbacks
                    for callback in self.result_callbacks:
                        try:
                            callback(result)
                        except Exception as e:
                            self.logger.error(f"Callback error: {e}")
                else:
                    self.stats['errors'] += 1
                    if self.health_monitor:
                        from transcription_health_monitor import report_inference_error
                        report_inference_error("Transcription returned no result", processing_time=processing_time)
                
                self.processing_queue.task_done()
                
            except Empty:
                continue
            except Exception as e:
                self.logger.error(f"Processing error: {e}")
                self.stats['errors'] += 1

    def _transcribe_audio_sync(self, audio_data: np.ndarray, sample_rate: int, timestamp: float) -> Optional[TranscriptionResult]:
        """Synchronously transcribe audio data"""
        try:
            start_time = time.time()
            
            # Validate audio format
            if audio_data.dtype not in [np.float32, np.int16]:
                raise AudioFormatError(f"Unsupported audio format: {audio_data.dtype}")
            
            # Convert to float32 if needed
            if audio_data.dtype == np.int16:
                audio_data = audio_data.astype(np.float32) / 32768.0
            
            # Save audio to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                if SOUNDFILE_AVAILABLE:
                    sf.write(temp_path, audio_data, sample_rate)
                else:
                    self._save_audio_as_wav(audio_data, sample_rate, temp_path)
                
                # Transcribe with faster-whisper
                segments, info = self.model.transcribe(
                    temp_path,
                    language="en",
                    beam_size=1,  # Faster for real-time
                    vad_filter=self.config['vad_enabled'],
                    vad_parameters=dict(
                        min_silence_duration_ms=self.config['vad_min_silence']
                    ) if self.config['vad_enabled'] else None
                )
                
                # Process segments
                transcription_segments = []
                full_text_parts = []
                
                for segment in segments:
                    # Determine speaker
                    speaker = self.speaker_tracker.identify_speaker(
                        segment.start + timestamp,
                        segment.end + timestamp,
                        segment.text
                    )
                    
                    trans_segment = TranscriptionSegment(
                        start_time=segment.start + timestamp,
                        end_time=segment.end + timestamp,
                        text=segment.text.strip(),
                        speaker=speaker,
                        confidence=getattr(segment, 'avg_logprob', 0.0),
                        is_partial=False
                    )
                    
                    transcription_segments.append(trans_segment)
                    full_text_parts.append(segment.text.strip())
                
                # Create result
                result = TranscriptionResult(
                    segments=transcription_segments,
                    full_text=" ".join(full_text_parts),
                    processing_time=time.time() - start_time,
                    model_used=f"faster-whisper-{self.model_name}",
                    language=info.language
                )
                
                return result
                
            finally:
                # Cleanup temp file
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            self.logger.error(f"Transcription error: {e}")
            
            # Report health status
            if self.health_monitor:
                from transcription_health_monitor import report_inference_error
                if "audio format" in str(e).lower():
                    from transcription_health_monitor import report_audio_error
                    report_audio_error(f"Audio format error: {e}", audio_dtype=str(audio_data.dtype))
                else:
                    report_inference_error(f"Transcription failed: {e}", audio_length=len(audio_data))
            
            raise InferenceError(f"Transcription failed: {e}")

    def _save_audio_as_wav(self, audio_data: np.ndarray, sample_rate: int, filepath: str):
        """Save numpy audio data as WAV file (fallback when soundfile not available)"""
        # Ensure audio is in correct format for wave module
        if audio_data.dtype == np.float32:
            # Convert float32 to int16
            audio_data = (audio_data * 32767).astype(np.int16)
        
        with wave.open(filepath, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes per sample (16-bit)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())

    def get_health_status(self) -> Dict[str, any]:
        """Get health status for monitoring"""
        return {
            'status': 'ready' if self.model_loaded else 'not_ready',
            'model': self.model_name,
            'device': self.device,
            'processing': self.is_processing,
            'queue_size': self.processing_queue.qsize(),
            'stats': self.stats.copy(),
            'faster_whisper_available': FASTER_WHISPER_AVAILABLE
        }

class EnhancedSpeakerTracker:
    """Enhanced speaker identification with better heuristics"""
    
    def __init__(self):
        self.speakers = {}
        self.current_speaker = "Therapist"
        self.last_switch_time = 0
        self.min_switch_interval = 3.0  # Minimum seconds between switches
        self.speaker_history = []
        
    def identify_speaker(self, start_time: float, end_time: float, text: str) -> str:
        """Identify speaker using enhanced heuristics"""
        text_lower = text.lower().strip()
        
        if len(text_lower) < 3:  # Too short to analyze
            return self.current_speaker
        
        # Enhanced therapist indicators
        therapist_indicators = [
            "how do you feel", "how are you feeling", "tell me about", "what do you think",
            "can you describe", "i understand", "let's explore", "help me understand",
            "it sounds like", "what i'm hearing", "from my perspective", "in my experience",
            "let's work on", "what would happen if", "have you considered", "what comes up"
        ]
        
        # Enhanced client indicators  
        client_indicators = [
            "i feel", "i think", "i don't know", "i'm not sure", "maybe", "i guess",
            "it's hard", "i can't", "i want", "i need", "i wish", "i hope",
            "my family", "my friend", "at work", "at home", "yesterday", "last week"
        ]
        
        # Question patterns (more likely therapist)
        question_patterns = ["?", "what", "how", "why", "when", "where", "who"]
        
        # Calculate scores
        therapist_score = sum(2 if indicator in text_lower else 0 for indicator in therapist_indicators)
        client_score = sum(2 if indicator in text_lower else 0 for indicator in client_indicators)
        
        # Bonus for question patterns
        question_score = sum(1 for pattern in question_patterns if pattern in text_lower)
        therapist_score += question_score
        
        # Time-based switching logic
        time_since_switch = start_time - self.last_switch_time
        
        # Determine speaker
        if time_since_switch > self.min_switch_interval:
            if therapist_score > client_score and therapist_score > 2:
                new_speaker = "Therapist"
            elif client_score > therapist_score and client_score > 2:
                new_speaker = "Client"
            else:
                # No clear indicators - use context
                new_speaker = self._get_contextual_speaker(text_lower)
            
            # Update if speaker changed
            if new_speaker != self.current_speaker:
                self.current_speaker = new_speaker
                self.last_switch_time = start_time
                
        # Track history
        self.speaker_history.append({
            'speaker': self.current_speaker,
            'start_time': start_time,
            'text': text[:50]  # First 50 chars for debugging
        })
        
        # Keep history manageable
        if len(self.speaker_history) > 100:
            self.speaker_history = self.speaker_history[-50:]
            
        return self.current_speaker
    
    def _get_contextual_speaker(self, text_lower: str) -> str:
        """Use context and patterns to determine speaker when unclear"""
        # Look at recent history
        if len(self.speaker_history) > 0:
            recent_speaker = self.speaker_history[-1]['speaker']
            
            # If very short utterance, likely same speaker
            if len(text_lower) < 10:
                return recent_speaker
            
            # Alternate if no clear indicators
            return "Client" if recent_speaker == "Therapist" else "Therapist"
        
        return self.current_speaker

def test_enhanced_whisper():
    """Test the enhanced whisper manager"""
    print("Testing Enhanced Whisper Manager")
    print("=" * 50)
    
    def on_result(result: TranscriptionResult):
        print(f"\n📝 Transcription Result:")
        print(f"   Model: {result.model_used}")
        print(f"   Language: {result.language}")
        print(f"   Processing time: {result.processing_time:.2f}s")
        print(f"   Full text: {result.full_text}")
        print(f"   Segments: {len(result.segments)}")
        for i, segment in enumerate(result.segments):
            print(f"     {i+1}. [{segment.start_time:.1f}s-{segment.end_time:.1f}s] {segment.speaker}: {segment.text}")
    
    try:
        # Initialize manager
        manager = EnhancedWhisperManager("small")
        
        # Check status
        status = manager.get_model_status()
        print(f"Model Status: {status}")
        
        if not status['available']:
            print("❌ faster-whisper not available")
            return
        
        # Load model
        if not manager.load_model():
            print("❌ Model loading failed")
            return
            
        print("✅ Model loaded successfully")
        
        # Add callback
        manager.add_result_callback(on_result)
        
        # Start processing
        manager.start_processing()
        print("✅ Processing started")
        
        # Create test audio (3 seconds of noise)
        sample_rate = 16000
        duration = 3
        test_audio = np.random.random(sample_rate * duration).astype(np.float32) * 0.1
        
        print("🎵 Sending test audio for transcription...")
        manager.transcribe_audio_chunk(test_audio, sample_rate)
        
        # Wait for processing
        time.sleep(5)
        
        # Get health status
        health = manager.get_health_status()
        print(f"\n📊 Health Status: {health}")
        
        # Stop processing
        manager.stop_processing()
        print("✅ Test completed")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_enhanced_whisper()
