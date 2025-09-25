#!/usr/bin/env python3
"""
Transcription Configuration Management
Handles environment variables and configuration for the transcription system
"""

import os
from pathlib import Path
from typing import Dict, Any
import logging

# Global constants for deterministic model loading
MODEL_SIZE = "small"           # tiny|base|base.en|small|medium|large-v3
MODEL_DEVICE = "auto"          # auto|cuda|cpu
MODEL_COMPUTE = "auto"         # auto|float16|int8_float16|int8
MODEL_CACHE_DIR = r"%LOCALAPPDATA%\faster-whisper"

AUDIO_CAPTURE_MODE = "auto"    # auto|loopback|stereo_mix|mic_only
LOOPBACK_DEVICE_NAME = None    # e.g., "Speakers (Logi Z407)"; None => default
CAPTURE_SAMPLERATE = 44100
CAPTURE_CHANNELS = 2
CAPTURE_FRAMES = 1024
AUDIO_Q_MAX = 32

class TranscriptionConfig:
    """Configuration management for transcription system"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._config = self._load_config()
        self._validate_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables with defaults"""
        config = {
            # Model Settings - Enhanced for deterministic loading
            'model_size': os.getenv('ASR_MODEL_SIZE', 'small'),  # Changed default to small
            'device': os.getenv('ASR_DEVICE', 'auto'),
            'compute_type': os.getenv('ASR_COMPUTE_TYPE', 'auto'),
            'model_cache_dir': os.path.expandvars(os.getenv('MODEL_CACHE_DIR', r'%LOCALAPPDATA%\faster-whisper')),

            # Storage Settings
            'transcripts_dir': Path(os.getenv('TRANSCRIPTS_DIR', './data/transcripts')),
            'recordings_dir': Path(os.getenv('RECORDINGS_DIR', './data/recordings')),
            'cache_dir': Path(os.getenv('WHISPER_CACHE_DIR', './whisper_models')),
            
            # Real-time Settings
            'chunk_duration': float(os.getenv('TRANSCRIPTION_CHUNK_DURATION', '5')),
            'chunk_overlap': float(os.getenv('TRANSCRIPTION_OVERLAP', '1')),
            
            # VAD Settings
            'vad_enabled': os.getenv('VAD_ENABLED', 'true').lower() == 'true',
            'vad_min_silence': int(os.getenv('VAD_MIN_SILENCE_DURATION', '500')),
            
            # UI Settings
            'ui_update_throttle': float(os.getenv('UI_UPDATE_THROTTLE', '3')),
            
            # Performance Settings
            'max_concurrent': int(os.getenv('MAX_CONCURRENT_TRANSCRIPTIONS', '2')),
            
            # Audio Capture Settings - Enhanced for WASAPI loopback
            'audio_capture_mode': os.getenv('AUDIO_CAPTURE_MODE', 'auto'),  # auto|loopback|stereo_mix|mic_only
            'loopback_device_name': os.getenv('LOOPBACK_DEVICE_NAME', None),  # e.g., "Speakers (Logi Z407)"; None => default
            'capture_samplerate': int(os.getenv('CAPTURE_SAMPLERATE', '44100')),
            'capture_channels': int(os.getenv('CAPTURE_CHANNELS', '2')),
            'capture_frames': int(os.getenv('CAPTURE_FRAMES', '1024')),
            'audio_q_max': int(os.getenv('AUDIO_Q_MAX', '32')),  # Bounded queue size
            
            # Debug Settings
            'debug_audio': os.getenv('DEBUG_AUDIO_EXPORT', 'false').lower() == 'true',
            'debug_timing': os.getenv('DEBUG_TRANSCRIPTION_TIMING', 'false').lower() == 'true',
        }
        
        return config
    
    def _validate_config(self):
        """Validate configuration values"""
        valid_models = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']
        if self._config['model_size'] not in valid_models:
            self.logger.warning(f"Invalid model size '{self._config['model_size']}', using 'medium'")
            self._config['model_size'] = 'medium'
        
        valid_devices = ['auto', 'cpu', 'cuda']
        if self._config['device'] not in valid_devices:
            self.logger.warning(f"Invalid device '{self._config['device']}', using 'auto'")
            self._config['device'] = 'auto'
        
        valid_compute = ['auto', 'float16', 'int8', 'int8_float16']
        if self._config['compute_type'] not in valid_compute:
            self.logger.warning(f"Invalid compute type '{self._config['compute_type']}', using 'auto'")
            self._config['compute_type'] = 'auto'
        
        valid_capture_modes = ['auto', 'loopback', 'stereo_mix', 'mic_only']
        if self._config['audio_capture_mode'] not in valid_capture_modes:
            self.logger.warning(f"Invalid audio capture mode '{self._config['audio_capture_mode']}', using 'auto'")
            self._config['audio_capture_mode'] = 'auto'
    
    def ensure_directories(self):
        """Create necessary directories if they don't exist"""
        for dir_key in ['transcripts_dir', 'recordings_dir', 'cache_dir']:
            directory = self._config[dir_key]
            directory.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Ensured directory exists: {directory}")
    
    def get_device_config(self) -> tuple[str, str]:
        """Get resolved device and compute type configuration"""
        device = self._config['device']
        compute_type = self._config['compute_type']
        
        # Auto-detect device if needed
        if device == 'auto':
            try:
                import torch
                if torch.cuda.is_available():
                    device = 'cuda'
                    gpu_name = torch.cuda.get_device_name()
                    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                    self.logger.info(f"CUDA detected: {gpu_name} ({vram_gb:.1f}GB VRAM) - Using GPU acceleration")
                else:
                    device = 'cpu'
                    self.logger.info("CUDA not available, using CPU")
            except ImportError:
                device = 'cpu'
                self.logger.info("PyTorch not available, using CPU")
        
        # Auto-select compute type based on device
        if compute_type == 'auto':
            if device == 'cuda':
                compute_type = 'float16'
            else:
                compute_type = 'int8'
        
        return device, compute_type
    
    def get_session_storage_path(self, session_id: str) -> Dict[str, Path]:
        """Get storage paths for a session"""
        from datetime import datetime
        
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        session_dir = self._config['recordings_dir'] / date_str / session_id
        transcript_dir = self._config['transcripts_dir'] / date_str / session_id
        
        # Ensure directories exist
        session_dir.mkdir(parents=True, exist_ok=True)
        transcript_dir.mkdir(parents=True, exist_ok=True)
        
        return {
            'session_dir': session_dir,
            'transcript_dir': transcript_dir,
            'audio_file': session_dir / 'audio.wav',
            'transcript_jsonl': transcript_dir / 'transcript.jsonl',
            'transcript_txt': transcript_dir / 'transcript.txt'
        }
    
    def get_model_recommendation(self) -> str:
        """Get model recommendation based on hardware"""
        try:
            import psutil
            import torch
            
            # Check available memory
            memory_gb = psutil.virtual_memory().total / (1024**3)
            
            # Check if CUDA is available
            has_cuda = torch.cuda.is_available()
            
            if has_cuda:
                # GPU available - can handle larger models
                if memory_gb >= 16:
                    return 'large-v3'
                elif memory_gb >= 8:
                    return 'medium'
                else:
                    return 'small'
            else:
                # CPU only - be more conservative
                if memory_gb >= 16:
                    return 'medium'
                elif memory_gb >= 8:
                    return 'small'
                else:
                    return 'tiny'
                    
        except ImportError:
            # Fallback if dependencies not available
            return self._config['model_size']
    
    def __getitem__(self, key: str) -> Any:
        """Allow dict-like access to config values"""
        return self._config[key]
    
    def __contains__(self, key: str) -> bool:
        """Allow 'in' operator for config keys"""
        return key in self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value with optional default"""
        return self._config.get(key, default)
    
    def log_config(self):
        """Log current configuration for debugging"""
        device, compute_type = self.get_device_config()
        
        self.logger.info("Transcription Configuration:")
        self.logger.info(f"  Model: {self._config['model_size']}")
        self.logger.info(f"  Device: {device}")
        self.logger.info(f"  Compute Type: {compute_type}")
        self.logger.info(f"  Chunk Duration: {self._config['chunk_duration']}s")
        self.logger.info(f"  VAD Enabled: {self._config['vad_enabled']}")
        self.logger.info(f"  Audio Capture Mode: {self._config['audio_capture_mode']}")
        self.logger.info(f"  Loopback Device: {self._config['loopback_device_name'] or 'default'}")
        self.logger.info(f"  Capture Format: {self._config['capture_samplerate']}Hz, {self._config['capture_channels']}ch, {self._config['capture_frames']} frames")
        self.logger.info(f"  Recordings Dir: {self._config['recordings_dir']}")
        self.logger.info(f"  Transcripts Dir: {self._config['transcripts_dir']}")

# Global configuration instance
_config_instance = None

def get_transcription_config() -> TranscriptionConfig:
    """Get global transcription configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = TranscriptionConfig()
    return _config_instance

def setup_transcription_environment():
    """Setup transcription environment and validate configuration"""
    config = get_transcription_config()
    config.ensure_directories()
    config.log_config()
    return config

if __name__ == "__main__":
    # Test configuration
    config = setup_transcription_environment()
    print("Configuration loaded successfully!")
