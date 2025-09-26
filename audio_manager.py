import wave
import threading
import time
import numpy as np
from collections import deque
import os
import queue
from logger_config import get_logger, log_function_call

# Import python-soundcard for unified audio capture
try:
    import soundcard as sc
    SOUNDCARD_AVAILABLE = True
except ImportError:
    SOUNDCARD_AVAILABLE = False
    sc = None
    raise ImportError("python-soundcard is required for audio capture. Install with: pip install soundcard")

class AudioManager:
    def __init__(self, buffer_duration=180):  # 3 minutes buffer
        self.logger = get_logger('audio_manager')
        self.logger.info("Initializing AudioManager")

        if not SOUNDCARD_AVAILABLE:
            raise RuntimeError("python-soundcard is required for audio capture. Install with: pip install soundcard")

        try:
            self.buffer_duration = buffer_duration
            self.sample_rate = 44100
            self.channels = 2  # Stereo for dual-channel
            self.chunk_size = 1024

            # Audio buffers - using deque for efficient circular buffer
            self.audio_buffer = deque()
            self.recording = False
            self.recording_thread = None

            # Thread-safe communication
            self.status_queue = queue.Queue()  # For sending status updates to GUI
            self.command_queue = queue.Queue()  # For receiving commands from GUI
            self._thread_running = False
            self._shutdown_event = threading.Event()

            # Soundcard device references
            self.microphone_device = None
            self.system_audio_device = None  # For loopback
            self.microphone_recorder = None
            self.loopback_recorder = None

            # Volume monitoring (thread-safe)
            self._levels_lock = threading.Lock()
            self._mic_level = 0.0
            self._system_level = 0.0

            # Audio callback system for real-time transcription
            self.audio_callbacks = []
            self.callback_lock = threading.Lock()
            self._buffer_duration = 0.0

            # Create temp directory for audio files
            os.makedirs("temp_recordings", exist_ok=True)

            self.logger.info(f"AudioManager initialized - Buffer: {buffer_duration}s, Sample Rate: {self.sample_rate}, Chunk Size: {self.chunk_size}")

        except Exception as e:
            self.logger.error(f"Failed to initialize AudioManager: {e}")
            raise

    def add_audio_data_callback(self, callback):
        """Add callback for real-time audio data"""
        with self.callback_lock:
            self.audio_callbacks.append(callback)
            self.logger.debug(f"Added audio data callback, total callbacks: {len(self.audio_callbacks)}")

    def remove_audio_data_callback(self, callback):
        """Remove callback for real-time audio data"""
        with self.callback_lock:
            if callback in self.audio_callbacks:
                self.audio_callbacks.remove(callback)
                self.logger.debug(f"Removed audio data callback, total callbacks: {len(self.audio_callbacks)}")

    def _call_audio_callbacks(self, audio_data, sample_rate):
        """Call all registered audio callbacks with new audio data"""
        with self.callback_lock:
            callbacks_to_call = self.audio_callbacks.copy()  # Copy to avoid lock during callback calls

        for callback in callbacks_to_call:
            try:
                callback(audio_data, sample_rate)
            except Exception as e:
                self.logger.warning(f"Audio callback error: {e}")

    @log_function_call('audio_manager')
    def get_audio_devices(self):
        """Get list of available audio devices using python-soundcard"""
        self.logger.debug("Scanning for audio devices using python-soundcard...")

        input_devices = []
        output_devices = []
        system_recording_devices = []

        try:
            # Get microphones
            microphones = sc.all_microphones(include_loopback=False)
            self.logger.info(f"Found {len(microphones)} microphone devices")

            for i, mic in enumerate(microphones):
                input_devices.append({
                    'index': i,
                    'name': mic.name,
                    'raw_name': mic.name,
                    'channels': mic.channels if hasattr(mic, 'channels') else 1,
                    'sample_rate': 44100,  # Default for soundcard
                    'type': 'input',
                    'soundcard_device': mic
                })
                self.logger.debug(f"  -> Added microphone: {mic.name}")

            # Get speakers (for loopback)
            speakers = sc.all_speakers()
            self.logger.info(f"Found {len(speakers)} speaker devices")

            for i, spk in enumerate(speakers):
                output_devices.append({
                    'index': i,
                    'name': spk.name,
                    'raw_name': spk.name,
                    'channels': spk.channels if hasattr(spk, 'channels') else 2,
                    'sample_rate': 44100,  # Default for soundcard
                    'type': 'output',
                    'soundcard_device': spk
                })
                self.logger.debug(f"  -> Added speaker: {spk.name}")

                # Add as system recording device (loopback)
                system_recording_devices.append({
                    'index': f"loopback_{i}",
                    'name': f"{spk.name} (System Audio Loopback)",
                    'raw_name': spk.name,
                    'channels': 2,  # Loopback is typically stereo
                    'sample_rate': 44100,
                    'type': 'system_loopback',
                    'soundcard_device': spk
                })
                self.logger.debug(f"  -> Added loopback for: {spk.name}")

            self.logger.info(f"Device scan complete: {len(input_devices)} microphones, {len(output_devices)} speakers, {len(system_recording_devices)} loopback devices")

            return {
                'input_devices': input_devices,
                'output_devices': output_devices,
                'system_recording_devices': system_recording_devices
            }

        except Exception as e:
            self.logger.error(f"Failed to get audio devices: {e}")
            return {
                'input_devices': [],
                'output_devices': [],
                'system_recording_devices': []
            }

    def _clean_device_name(self, name):
        """Clean up device name for better display"""
        # Remove common technical prefixes/suffixes
        name = name.replace(" (MME)", "")
        name = name.replace(" (WDM-KS)", "")
        name = name.replace(" (DirectSound)", "")
        name = name.replace("Microsoft Sound Mapper - ", "")

        # Standardize common names
        if "Microsoft Sound Mapper" in name:
            if "Input" in name or "Microphone" in name:
                return "Default Microphone"
            elif "Output" in name or "Playback" in name:
                return "Default Speakers"

        return name

    def supports_wasapi_loopback(self):
        """Check if WASAPI is supported (deprecated - use soundcard instead)"""
        # WASAPI loopback is deprecated in favor of soundcard loopback
        self.logger.debug("WASAPI loopback deprecated - use soundcard_loopback instead")
        return False

    def open_system_loopback_stream(self):
        """Open a system loopback stream (deprecated - use soundcard instead)"""
        # WASAPI loopback is deprecated in favor of soundcard loopback
        self.logger.debug("WASAPI loopback deprecated - use soundcard_loopback instead")
        return None

    def supports_soundcard_loopback(self):
        """Check if soundcard module is available for loopback capture"""
        return SOUNDCARD_AVAILABLE

    def open_soundcard_loopback_stream(self):
        """Open a soundcard loopback stream for system audio capture"""
        try:
            if not self.supports_soundcard_loopback():
                self.logger.debug("Soundcard loopback not available")
                return None
            
            # Get default speaker
            default_speaker = sc.default_speaker()
            self.logger.debug(f"Default speaker: {default_speaker.name}")
            
            # Get loopback microphone for the speaker
            loopback_mic = sc.get_microphone(id=default_speaker.name, include_loopback=True)
            
            self.logger.info(f"Soundcard loopback stream opened successfully for device: {default_speaker.name}")
            return loopback_mic
            
        except Exception as e:
            self.logger.warning(f"Soundcard loopback stream failed: {e}")
            return None

    def _is_system_recording_device(self, name):
        """Check if device is a system recording device (like Stereo Mix)"""
        system_keywords = [
            # Windows Stereo Mix variants
            "stereo mix", "stereomix", "wave out mix", "what u hear",
            "what you hear", "rec. playback", "recording control",

            # Generic loopback/monitor devices
            "loopback", "monitor", "capture", "system audio",

            # Hardware-specific patterns
            "realtek", "conexant", "via", "idt",  # Common audio drivers

            # Additional patterns found in real systems
            "mix", "output", "playback", "desktop audio",
            "speakers", "headphones"
        ]
        name_lower = name.lower()

        # First check for explicit system recording device names
        explicit_matches = [
            "stereo mix", "stereomix", "wave out mix", "what u hear",
            "what you hear", "rec. playback", "recording control", "loopback"
        ]

        if any(keyword in name_lower for keyword in explicit_matches):
            return True

        # Then check for potential system audio devices
        # Look for devices that mention common audio hardware + mix/monitor
        hardware_keywords = ["realtek", "conexant", "via", "idt", "nvidia", "amd"]
        monitor_keywords = ["mix", "monitor", "capture", "loopback"]

        has_hardware = any(hw in name_lower for hw in hardware_keywords)
        has_monitor = any(mon in name_lower for mon in monitor_keywords)

        return has_hardware and has_monitor

    def get_input_devices(self):
        """Get filtered input devices for microphone selection"""
        devices = self.get_audio_devices()
        return devices['input_devices']

    def get_system_audio_devices(self):
        """Get devices capable of recording system audio"""
        devices = self.get_audio_devices()
        # Return only actual system recording devices (like Stereo Mix)
        # These are input devices that can capture system audio
        system_devices = devices['system_recording_devices'].copy()

        # If no dedicated system recording devices found, look for alternatives
        if not system_devices:
            self.logger.debug("No dedicated system recording devices found, searching for alternatives...")

            # Look for input devices that might capture system audio
            for input_device in devices['input_devices']:
                device_name = input_device['name'].lower()

                # Check for broader system audio patterns
                system_patterns = ['mix', 'loopback', 'monitor', 'rec', 'capture', 'desktop']
                hardware_patterns = ['realtek', 'conexant', 'via', 'idt', 'nvidia', 'amd', 'audio']

                has_system_pattern = any(pattern in device_name for pattern in system_patterns)
                has_hardware_pattern = any(pattern in device_name for pattern in hardware_patterns)

                # Include devices with system patterns or hardware + reasonable channel count
                if has_system_pattern or (has_hardware_pattern and input_device['channels'] >= 2):
                    system_devices.append({
                        **input_device,
                        'type': 'input_as_system',
                        'name': f"{input_device['name']} (Alternative System Audio)"
                    })
                    self.logger.debug(f"Added alternative system device: {input_device['name']}")

            # If still no system devices found, check for reasonable input devices
            if not system_devices:
                self.logger.info("Searching for any viable input devices for system audio capture...")

                # Look for any input device with stereo capability that isn't clearly a microphone
                for input_device in devices['input_devices']:
                    device_name = input_device['name'].lower()

                    # Skip obvious microphones
                    mic_patterns = ['microphone', 'mic', 'webcam', 'camera', 'headset']
                    is_microphone = any(pattern in device_name for pattern in mic_patterns)

                    if not is_microphone and input_device['channels'] >= 2:
                        system_devices.append({
                            **input_device,
                            'type': 'fallback_system',
                            'name': f"{input_device['name']} (Fallback - May Not Capture System Audio)"
                        })
                        self.logger.debug(f"Added fallback system device: {input_device['name']}")

            # Final fallback: warn user and add placeholder
            if not system_devices:
                self.logger.warning("No system audio recording devices found. Stereo Mix may be disabled in Windows Sound settings.")
                # Add helpful placeholder
                system_devices.append({
                    'index': -1,
                    'name': 'No System Audio Device Available - Enable Stereo Mix in Windows Sound Settings',
                    'raw_name': 'placeholder',
                    'channels': 0,
                    'sample_rate': 44100,
                    'type': 'placeholder'
                })

        return system_devices

    def test_device(self, device_index, device_type='input', duration=2):
        """Test a specific audio device using soundcard"""
        try:
            if device_type == 'input':
                microphones = sc.all_microphones(include_loopback=False)
                if not (0 <= device_index < len(microphones)):
                    return False, f"Device index {device_index} out of range"

                mic = microphones[device_index]
                self.logger.info(f"Testing microphone '{mic.name}' for {duration} seconds...")

                max_level = 0
                test_frames = int(duration * self.sample_rate)

                with mic.recorder(samplerate=self.sample_rate, channels=1) as recorder:
                    # Record in chunks to monitor progress
                    chunk_duration = 0.25  # 250ms chunks
                    chunk_frames = int(chunk_duration * self.sample_rate)
                    chunks = int(test_frames / chunk_frames)

                    for i in range(chunks):
                        try:
                            audio_data = recorder.record(numframes=chunk_frames)
                            level = np.sqrt(np.mean(audio_data**2))
                            max_level = max(max_level, level)

                            if i % 4 == 0:  # Print every ~1 second
                                print(f"Level: {level:.4f}")
                        except Exception as e:
                            print(f"Read error: {e}")
                            continue

                return True, f"Test completed. Max level: {max_level:.4f}"

            else:
                return False, "Output device testing not supported"

        except Exception as e:
            return False, f"Device test failed: {str(e)}"

    def get_device_info(self, device_index):
        """Get detailed information about a specific device using soundcard"""
        try:
            # Get microphones and speakers
            microphones = sc.all_microphones(include_loopback=False)
            speakers = sc.all_speakers()

            # Check microphones first
            if 0 <= device_index < len(microphones):
                mic = microphones[device_index]
                return {
                    'name': mic.name,
                    'max_input_channels': getattr(mic, 'channels', 1),
                    'max_output_channels': 0,
                    'default_sample_rate': 44100,
                    'type': 'microphone'
                }

            # Check speakers (offset by microphone count)
            speaker_index = device_index - len(microphones)
            if 0 <= speaker_index < len(speakers):
                spk = speakers[speaker_index]
                return {
                    'name': spk.name,
                    'max_input_channels': 0,
                    'max_output_channels': getattr(spk, 'channels', 2),
                    'default_sample_rate': 44100,
                    'type': 'speaker'
                }

            return {'error': f'Device index {device_index} out of range'}

        except Exception as e:
            return {'error': str(e)}

    def set_input_device(self, device_index):
        """Set the microphone input device (deprecated - use set_microphone_device)"""
        self.logger.info(f"Deprecated method set_input_device called with index {device_index}")
        self.logger.info("Use set_microphone_device instead for python-soundcard compatibility")

        # Try to find the device by index in available microphones
        try:
            microphones = sc.all_microphones(include_loopback=False)
            if 0 <= device_index < len(microphones):
                return self.set_microphone_device(device_index)
            else:
                error_msg = f"Device index {device_index} out of range (0-{len(microphones)-1})"
                self.logger.error(error_msg)
                return False, error_msg
        except Exception as e:
            error_msg = f"Failed to set input device {device_index}: {e}"
            self.logger.error(error_msg)
            return False, error_msg

    def set_microphone_device(self, device_name_or_index):
        """Set the microphone device using soundcard"""
        self.logger.info(f"Setting microphone device: {device_name_or_index}")

        try:
            microphones = sc.all_microphones(include_loopback=False)

            # Handle selection by name (preferred) or index
            target_mic = None
            if isinstance(device_name_or_index, str):
                # Search by name (case insensitive, partial match)
                for mic in microphones:
                    if device_name_or_index.lower() in mic.name.lower():
                        target_mic = mic
                        break
                if not target_mic:
                    # Try exact match
                    for mic in microphones:
                        if mic.name == device_name_or_index:
                            target_mic = mic
                            break
            else:
                # Selection by index
                if 0 <= device_name_or_index < len(microphones):
                    target_mic = microphones[device_name_or_index]

            if not target_mic:
                available = [mic.name for mic in microphones]
                error_msg = f"Microphone '{device_name_or_index}' not found. Available: {available}"
                self.logger.error(error_msg)
                return False, error_msg

            self.microphone_device = target_mic
            self.logger.info(f"Microphone device set: '{target_mic.name}'")
            return True, f"Microphone device set: {target_mic.name}"

        except Exception as e:
            error_msg = f"Failed to set microphone device: {e}"
            self.logger.error(error_msg)
            return False, error_msg

    def set_system_audio_device(self, speaker_name_or_index):
        """Set the system audio device (speaker for loopback) using soundcard"""
        self.logger.info(f"Setting system audio device (speaker loopback): {speaker_name_or_index}")

        try:
            speakers = sc.all_speakers()

            # Handle selection by name (preferred) or index
            target_speaker = None
            if isinstance(speaker_name_or_index, str):
                # Search by name (case insensitive, partial match)
                for spk in speakers:
                    if speaker_name_or_index.lower() in spk.name.lower():
                        target_speaker = spk
                        break
                if not target_speaker:
                    # Try exact match
                    for spk in speakers:
                        if spk.name == speaker_name_or_index:
                            target_speaker = spk
                            break
            else:
                # Selection by index
                if 0 <= speaker_name_or_index < len(speakers):
                    target_speaker = speakers[speaker_name_or_index]

            if not target_speaker:
                available = [spk.name for spk in speakers]
                error_msg = f"Speaker '{speaker_name_or_index}' not found. Available: {available}"
                self.logger.error(error_msg)
                return False, error_msg

            self.system_audio_device = target_speaker
            self.logger.info(f"System audio device (loopback) set: '{target_speaker.name}'")
            return True, f"System audio device set: {target_speaker.name}"

        except Exception as e:
            error_msg = f"Failed to set system audio device: {e}"
            self.logger.error(error_msg)
            return False, error_msg

    def set_system_audio_mode(self, mode):
        """Set system audio capture mode (wasapi_loopback, mic_only, or device)"""
        self.logger.info(f"Setting system audio mode to: {mode}")
        
        valid_modes = ['soundcard_loopback', 'wasapi_loopback', 'mic_only', 'device']
        if mode not in valid_modes:
            error_msg = f"Invalid system audio mode: {mode}. Valid modes: {valid_modes}"
            self.logger.error(error_msg)
            return False, error_msg
        
        self.system_audio_mode = mode
        # Clear device only for modes that don't need device reference
        if mode in ['wasapi_loopback', 'mic_only']:
            self.system_audio_device = None
        # Note: soundcard_loopback mode KEEPS the system_audio_device for loopback microphone creation
        
        self.logger.info(f"System audio mode set to: {mode}")
        return True, f"System audio mode set to: {mode}"

    def preflight_open(self, device_id):
        """Non-blocking preflight test for device availability
        
        Args:
            device_id: Device index or special mode identifier
            
        Returns:
            bool: True if device opens successfully, False otherwise
        """
        try:
            self.logger.debug(f"Preflight testing device: {device_id}")
            
            # Handle special modes
            if device_id == "soundcard_loopback":
                loopback_mic = self.open_soundcard_loopback_stream()
                if loopback_mic:
                    # Test the loopback microphone with a brief recording
                    try:
                        samplerate = 44100
                        test_frames = int(samplerate * 0.25)  # 250ms test
                        with loopback_mic.recorder(samplerate=samplerate) as rec:
                            _ = rec.record(numframes=test_frames)
                        self.logger.debug("Soundcard loopback preflight: SUCCESS")
                        return True
                    except Exception as e:
                        self.logger.debug(f"Soundcard loopback preflight test failed: {e}")
                        return False
                else:
                    self.logger.debug("Soundcard loopback preflight: FAILED")
                    return False
            
            elif device_id == "wasapi_loopback":
                stream = self.open_system_loopback_stream()
                if stream:
                    stream.close()
                    self.logger.debug("WASAPI loopback preflight: SUCCESS")
                    return True
                else:
                    self.logger.debug("WASAPI loopback preflight: FAILED")
                    return False
            
            elif device_id == "mic_only":
                # Mic-only mode always succeeds (no system audio device needed)
                self.logger.debug("Mic-only preflight: SUCCESS (no system audio)")
                return True
            
            # Handle device index - assume it's a microphone index
            try:
                microphones = sc.all_microphones(include_loopback=False)
                if not (0 <= device_id < len(microphones)):
                    self.logger.debug(f"Preflight failed: Device index {device_id} out of range")
                    return False

                mic = microphones[device_id]
                device_name = mic.name

                # Try to open the device briefly
                try:
                    test_frames = int(self.sample_rate * 0.1)  # 100ms test
                    with mic.recorder(samplerate=self.sample_rate, channels=1) as recorder:
                        _ = recorder.record(numframes=test_frames)

                    self.logger.debug(f"Preflight SUCCESS: Device '{device_name}' (index {device_id})")
                    return True
                except Exception as e:
                    self.logger.debug(f"Preflight FAILED: Device '{device_name}' - {str(e)}")
                    return False

            except Exception as e:
                self.logger.debug(f"Preflight FAILED: Device {device_id} - {str(e)}")
                return False
                
        except Exception as e:
            self.logger.error(f"Preflight test error for device {device_id}: {e}")
            return False

    def test_audio_levels(self, duration=5):
        """Test audio levels for both input sources using soundcard"""
        if self.microphone_device is None or self.system_audio_device is None:
            return False, "Devices not configured"

        try:
            # Get loopback microphone for system audio
            loopback_mic = sc.get_microphone(id=self.system_audio_device.name, include_loopback=True)

            print(f"Testing audio levels for {duration} seconds...")
            chunk_duration = 0.25  # 250ms chunks
            chunk_frames = int(chunk_duration * self.sample_rate)
            total_chunks = int(duration / chunk_duration)

            with self.microphone_device.recorder(samplerate=self.sample_rate, channels=1) as mic_rec:
                with loopback_mic.recorder(samplerate=self.sample_rate, channels=2) as sys_rec:
                    for i in range(total_chunks):
                        # Read from microphone
                        mic_data = mic_rec.record(numframes=chunk_frames)
                        mic_level = np.sqrt(np.mean(mic_data**2))

                        # Read from system audio (take left channel for level calculation)
                        system_data = sys_rec.record(numframes=chunk_frames)
                        sys_level = np.sqrt(np.mean(system_data[:, 0]**2))

                        # Update thread-safe levels
                        self._update_levels_thread_safe(mic_level, sys_level, i * chunk_duration)

                        if i % 4 == 0:  # Print every ~1 second
                            print(f"Mic: {mic_level:.4f} | System: {sys_level:.4f}")

            return True, "Audio test completed"

        except Exception as e:
            return False, f"Audio test failed: {str(e)}"

    @log_function_call('audio_manager')
    def start_recording(self):
        """Start concurrent dual-channel audio recording using python-soundcard"""
        self.logger.info("Starting concurrent audio recording with python-soundcard...")

        if self.recording:
            self.logger.warning("Recording already in progress")
            return False, "Already recording"

        # Validate devices are configured
        if self.microphone_device is None:
            self.logger.error("Microphone device not configured")
            return False, "Microphone device not configured"

        # Check system audio device based on mode
        system_audio_mode = getattr(self, 'system_audio_mode', 'soundcard_loopback')
        if system_audio_mode == 'mic_only':
            # Mic-only mode doesn't need system audio device
            self.logger.debug("Mic-only mode: system audio device not required")
        elif system_audio_mode in ['soundcard_loopback', 'wasapi_loopback']:
            # Loopback modes need a configured device
            if self.system_audio_device is None:
                self.logger.error(f"System audio device required for {system_audio_mode} mode but not configured")
                return False, f"System audio device not configured for {system_audio_mode} mode"
            self.logger.debug(f"System audio device configured for {system_audio_mode}: {self.system_audio_device.name}")
        else:
            # Traditional device mode
            if self.system_audio_device is None:
                self.logger.error("System audio device (speaker for loopback) not configured")
                return False, "System audio device not configured"

        # Test devices using soundcard
        try:
            self.logger.debug("Testing soundcard devices...")

            # Test microphone
            try:
                # Brief test recording
                with self.microphone_device.recorder(samplerate=self.sample_rate, channels=1) as mic_rec:
                    _ = mic_rec.record(numframes=int(self.sample_rate * 0.1))  # 100ms test
                self.logger.debug(f"Microphone test passed: {self.microphone_device.name}")
            except Exception as mic_error:
                self.logger.error(f"Microphone test failed: {mic_error}")
                return False, f"Microphone '{self.microphone_device.name}' test failed: {str(mic_error)}"

            # Test system audio (loopback) if needed based on mode
            if system_audio_mode == 'mic_only':
                self.logger.debug("Mic-only mode: skipping system audio test")
                validation_msg = f"Device validation passed - Mic: {self.microphone_device.name} (mic-only mode)"
            else:
                try:
                    # Get loopback microphone for the speaker
                    loopback_mic = sc.get_microphone(id=self.system_audio_device.name, include_loopback=True)
                    # Brief test recording
                    with loopback_mic.recorder(samplerate=self.sample_rate, channels=2) as sys_rec:
                        _ = sys_rec.record(numframes=int(self.sample_rate * 0.1))  # 100ms test
                    self.logger.debug(f"System audio loopback test passed: {self.system_audio_device.name}")
                except Exception as sys_error:
                    self.logger.error(f"System audio test failed: {sys_error}")
                    return False, f"System audio loopback '{self.system_audio_device.name}' test failed: {str(sys_error)}"

                validation_msg = f"Device validation passed - Mic: {self.microphone_device.name}, Loopback: {self.system_audio_device.name}"

            self.logger.debug(validation_msg)

        except Exception as e:
            self.logger.error(f"Device validation failed: {e}")
            return False, f"Device validation error: {str(e)}"

        try:
            self.recording = True
            self.audio_buffer.clear()

            # Initialize soundcard recorders
            self.logger.debug("Creating concurrent soundcard recorders...")
            self.microphone_recorder = self.microphone_device.recorder(samplerate=self.sample_rate, channels=1)

            # Initialize system audio recorder based on mode
            if system_audio_mode == 'mic_only':
                self.logger.debug("Mic-only mode: no system audio recorder needed")
                self.loopback_recorder = None
            else:
                # Get loopback microphone for system audio
                loopback_mic = sc.get_microphone(id=self.system_audio_device.name, include_loopback=True)
                self.loopback_recorder = loopback_mic.recorder(samplerate=self.sample_rate, channels=2)
                self.logger.debug(f"Loopback recorder created for: {self.system_audio_device.name}")

            self.logger.debug("Starting concurrent recording threads...")
            self.recording_thread = threading.Thread(target=self._concurrent_recording_loop)
            self.recording_thread.daemon = True
            self.recording_thread.start()

            self.logger.info("Concurrent soundcard recording started successfully")
            return True, "Recording started"

        except Exception as e:
            self.logger.error(f"Failed to start recording: {e}")
            self.recording = False
            return False, f"Recording start failed: {str(e)}"

    def _concurrent_recording_loop(self):
        """Concurrent recording loop using python-soundcard for both mic and system audio"""
        self.logger.debug("Concurrent recording loop thread started")
        self._thread_running = True

        try:
            # Notify GUI that thread is starting
            self.status_queue.put({
                'type': 'thread_status',
                'status': 'starting',
                'message': 'Recording thread initializing...'
            })

            # Check for shutdown before starting
            if self._shutdown_event.is_set():
                self.logger.info("Shutdown requested before recording start")
                return

            # Get system audio mode for recording loop
            system_audio_mode = getattr(self, 'system_audio_mode', 'soundcard_loopback')

            # Setup loopback microphone based on mode
            if system_audio_mode == 'mic_only':
                loopback_mic = None
                self.logger.debug("Mic-only mode: no system audio capture")
            else:
                # Get loopback microphone for system audio
                loopback_mic = sc.get_microphone(id=self.system_audio_device.name, include_loopback=True)
                self.logger.debug(f"Loopback microphone ready for: {self.system_audio_device.name}")

            buffer_max_size = int(self.buffer_duration * self.sample_rate / self.chunk_size)
            self.logger.info(f"Recording loop ready - Buffer max size: {buffer_max_size} chunks ({self.buffer_duration}s)")

            chunk_count = 0
            last_level_log = 0

            # Notify GUI that recording is ready
            self.status_queue.put({
                'type': 'thread_status',
                'status': 'running',
                'message': 'Recording loop active'
            })

            # Open recorders based on mode
            with self.microphone_device.recorder(samplerate=self.sample_rate, channels=1) as mic_rec:
                if loopback_mic is not None:
                    # Dual-stream mode (mic + loopback)
                    with loopback_mic.recorder(samplerate=self.sample_rate, channels=2) as sys_rec:
                        self.logger.debug("Both soundcard recorders opened successfully")
                        self._recording_loop_dual_stream(mic_rec, sys_rec)
                else:
                    # Mic-only mode
                    self.logger.debug("Microphone recorder opened (mic-only mode)")
                    self._recording_loop_mic_only(mic_rec)

            self.logger.info("Recording loop ended")

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Recording loop initialization error: {e}")
            self.recording = False

            # Provide specific guidance for common errors
            user_message = f"Recording error: {error_msg}"
            if "Unanticipated host error" in error_msg:
                user_message = "Audio device error: The selected audio device may not be available or properly configured. Try selecting a different microphone or system audio device."
            elif "Invalid sample rate" in error_msg:
                user_message = "Audio format error: The selected device doesn't support the required audio format. Try a different device."
            elif "Device unavailable" in error_msg:
                user_message = "Device unavailable: The selected audio device is being used by another application."

            # Notify GUI of error
            try:
                self.status_queue.put({
                    'type': 'error',
                    'message': user_message,
                    'error_code': 'recording_loop_error',
                    'technical_details': error_msg
                })
            except:
                pass  # Don't let notification errors affect cleanup

        finally:
            # Thread cleanup
            self._thread_running = False

            # Notify GUI that thread is stopping
            try:
                self.status_queue.put({
                    'type': 'thread_status',
                    'status': 'stopping',
                    'message': 'Recording thread cleaning up...'
                })
            except:
                pass  # Don't let notification errors affect cleanup

            # Final status notification
            try:
                self.status_queue.put({
                    'type': 'thread_status',
                    'status': 'stopped',
                    'message': 'Recording thread finished'
                })
            except:
                pass  # Don't let notification errors affect cleanup

            self.logger.debug("Recording loop thread finished")

    def _recording_loop_dual_stream(self, mic_rec, sys_rec):
        """Recording loop for dual-stream mode (microphone + system audio)"""
        buffer_max_size = int(self.buffer_duration * self.sample_rate / self.chunk_size)
        chunk_count = 0
        last_level_log = 0

        while self.recording and not self._shutdown_event.is_set():
            try:
                # Check for commands from GUI
                try:
                    command = self.command_queue.get_nowait()
                    if command['command'] == 'stop':
                        self.logger.debug("Stop command received from GUI")
                        break
                except queue.Empty:
                    pass

                # Read from both sources simultaneously
                mic_data = mic_rec.record(numframes=self.chunk_size)
                system_data = sys_rec.record(numframes=self.chunk_size)

                # Calculate audio levels
                mic_level = np.sqrt(np.mean(mic_data**2))
                sys_level = np.sqrt(np.mean(system_data**2))

                # Convert to int16 format for consistency
                mic_audio = (mic_data.flatten() * 32767).astype(np.int16)
                system_audio = (np.mean(system_data, axis=1) * 32767).astype(np.int16)

                # Update volume levels (thread-safe)
                buffer_duration = self.get_recording_duration()
                self._update_levels_thread_safe(mic_level, sys_level, buffer_duration)

                # Log audio levels every 5 seconds
                if chunk_count - last_level_log >= (5 * self.sample_rate // self.chunk_size):
                    from logger_config import AmanuensisLogger
                    AmanuensisLogger()._instance.log_audio_levels(mic_level, sys_level)
                    last_level_log = chunk_count

                # Combine into stereo (mic=left, system=right)
                stereo_data = np.empty((len(mic_audio) * 2,), dtype=np.int16)
                stereo_data[0::2] = mic_audio  # Left channel
                stereo_data[1::2] = system_audio  # Right channel

                # Send audio data to callbacks for real-time transcription
                stereo_float = stereo_data.astype(np.float32) / 32768.0
                self._call_audio_callbacks(stereo_float, self.sample_rate)

                # Add to circular buffer
                self.audio_buffer.append(stereo_data.tobytes())
                while len(self.audio_buffer) > buffer_max_size:
                    self.audio_buffer.popleft()

                chunk_count += 1

                # Log buffer status every 30 seconds
                if chunk_count % (30 * self.sample_rate // self.chunk_size) == 0:
                    duration = self.get_recording_duration()
                    self.logger.debug(f"Recording status: {chunk_count} chunks, {duration:.1f}s buffered, Mic:{mic_level:.4f}, Sys:{sys_level:.4f}")

                # Send status update to GUI thread
                try:
                    self.status_queue.put({
                        'type': 'levels',
                        'mic_level': mic_level,
                        'sys_level': sys_level,
                        'buffer_duration': buffer_duration,
                        'chunk_count': chunk_count
                    }, block=False)
                except queue.Full:
                    pass  # Skip if queue is full

            except Exception as e:
                self.logger.error(f"Recording error in dual-stream loop: {e}")
                continue

        self.logger.info(f"Dual-stream recording loop ended after {chunk_count} chunks")

    def _recording_loop_mic_only(self, mic_rec):
        """Recording loop for mic-only mode (no system audio)"""
        buffer_max_size = int(self.buffer_duration * self.sample_rate / self.chunk_size)
        chunk_count = 0
        last_level_log = 0

        while self.recording and not self._shutdown_event.is_set():
            try:
                # Check for commands from GUI
                try:
                    command = self.command_queue.get_nowait()
                    if command['command'] == 'stop':
                        self.logger.debug("Stop command received from GUI")
                        break
                except queue.Empty:
                    pass

                # Read from microphone only
                mic_data = mic_rec.record(numframes=self.chunk_size)

                # Calculate audio levels (mic only, no system audio)
                mic_level = np.sqrt(np.mean(mic_data**2))
                sys_level = 0.0  # No system audio in mic-only mode

                # Convert to int16 format
                mic_audio = (mic_data.flatten() * 32767).astype(np.int16)
                # Create silent system audio channel
                system_audio = np.zeros_like(mic_audio)

                # Update volume levels (thread-safe)
                buffer_duration = self.get_recording_duration()
                self._update_levels_thread_safe(mic_level, sys_level, buffer_duration)

                # Log audio levels every 5 seconds
                if chunk_count - last_level_log >= (5 * self.sample_rate // self.chunk_size):
                    from logger_config import AmanuensisLogger
                    AmanuensisLogger()._instance.log_audio_levels(mic_level, sys_level)
                    last_level_log = chunk_count

                # Combine into stereo (mic=left, silent=right)
                stereo_data = np.empty((len(mic_audio) * 2,), dtype=np.int16)
                stereo_data[0::2] = mic_audio  # Left channel
                stereo_data[1::2] = system_audio  # Right channel (silent)

                # Send audio data to callbacks for real-time transcription
                stereo_float = stereo_data.astype(np.float32) / 32768.0
                self._call_audio_callbacks(stereo_float, self.sample_rate)

                # Add to circular buffer
                self.audio_buffer.append(stereo_data.tobytes())
                while len(self.audio_buffer) > buffer_max_size:
                    self.audio_buffer.popleft()

                chunk_count += 1

                # Log buffer status every 30 seconds
                if chunk_count % (30 * self.sample_rate // self.chunk_size) == 0:
                    duration = self.get_recording_duration()
                    self.logger.debug(f"Recording status: {chunk_count} chunks, {duration:.1f}s buffered, Mic:{mic_level:.4f} (mic-only mode)")

                # Send status update to GUI thread
                try:
                    self.status_queue.put({
                        'type': 'levels',
                        'mic_level': mic_level,
                        'sys_level': sys_level,
                        'buffer_duration': buffer_duration,
                        'chunk_count': chunk_count
                    }, block=False)
                except queue.Full:
                    pass  # Skip if queue is full

            except Exception as e:
                self.logger.error(f"Recording error in mic-only loop: {e}")
                continue

        self.logger.info(f"Mic-only recording loop ended after {chunk_count} chunks")

    @log_function_call('audio_manager')
    def stop_recording(self):
        """Stop audio recording with clean shutdown sequence"""
        self.logger.info("Stopping audio recording...")

        # Step 1: Signal recording thread to stop
        self.recording = False
        self._shutdown_event.set()

        # Step 2: Send stop command to thread (if it's checking commands)
        try:
            self.send_command('stop')
        except:
            pass  # Don't fail if command queue has issues

        # Step 3: Wait for thread to finish gracefully
        if self.recording_thread and self.recording_thread.is_alive():
            self.logger.debug("Waiting for recording thread to finish...")
            self.recording_thread.join(timeout=5.0)  # Increased timeout

            if self.recording_thread.is_alive():
                self.logger.warning("Recording thread did not finish within timeout - this may cause issues")
            else:
                self.logger.debug("Recording thread finished cleanly")

        # Step 4: Clear shutdown event for next recording
        self._shutdown_event.clear()

        # Step 5: Log final status
        duration = self.get_recording_duration()
        buffer_size = len(self.audio_buffer)
        self.logger.info(f"Recording stopped - Buffer contains {duration:.1f}s ({buffer_size} chunks)")

    def get_recording_duration(self):
        """Get current buffer duration in seconds"""
        if not self.audio_buffer:
            return 0
        return len(self.audio_buffer) * self.chunk_size / self.sample_rate

    @log_function_call('audio_manager')
    def export_last_minutes(self, minutes=3, filename=None):
        """Export the last N minutes of audio to WAV files"""
        self.logger.info(f"Exporting last {minutes} minutes of audio...")

        if not self.audio_buffer:
            self.logger.warning("No audio data available for export")
            return False, "No audio data available"

        if filename is None:
            timestamp = int(time.time())
            filename = f"temp_recordings/session_{timestamp}"

        self.logger.debug(f"Export filename base: {filename}")

        # Calculate samples needed
        samples_needed = int(minutes * 60 * self.sample_rate / self.chunk_size)
        samples_available = len(self.audio_buffer)

        # Get the last N minutes (or all available data)
        samples_to_export = min(samples_needed, samples_available)
        export_buffer = list(self.audio_buffer)[-samples_to_export:]

        self.logger.info(f"Export details: {samples_needed} samples needed, {samples_available} available, {samples_to_export} to export")

        try:
            start_time = time.time()

            # Combine all chunks
            all_data = b''.join(export_buffer)
            self.logger.debug(f"Combined {len(export_buffer)} chunks into {len(all_data)} bytes")

            # Convert back to numpy for channel separation
            stereo_array = np.frombuffer(all_data, dtype=np.int16)
            stereo_array = stereo_array.reshape(-1, 2)

            # Separate channels
            mic_channel = stereo_array[:, 0]  # Left channel
            system_channel = stereo_array[:, 1]  # Right channel

            self.logger.debug(f"Separated channels: {len(mic_channel)} samples each")

            # Save therapist microphone (Channel 1)
            mic_filename = f"{filename}_therapist.wav"
            self._save_wav_file(mic_filename, mic_channel, 1)
            self.logger.debug(f"Saved therapist audio: {mic_filename}")

            # Save system audio (Channel 2)
            system_filename = f"{filename}_client.wav"
            self._save_wav_file(system_filename, system_channel, 1)
            self.logger.debug(f"Saved client audio: {system_filename}")

            duration = len(stereo_array) / self.sample_rate
            export_time = time.time() - start_time

            self.logger.info(f"Export completed in {export_time:.2f}s - Duration: {duration:.1f}s")

            return True, {
                'therapist_file': mic_filename,
                'client_file': system_filename,
                'duration': duration
            }

        except Exception as e:
            self.logger.error(f"Export failed: {e}")
            return False, f"Export failed: {str(e)}"

    def _save_wav_file(self, filename, audio_data, channels):
        """Save audio data to WAV file"""
        wf = wave.open(filename, 'wb')
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit audio (2 bytes per sample)
        wf.setframerate(self.sample_rate)
        wf.writeframes(audio_data.tobytes())
        wf.close()

    def get_volume_levels(self):
        """Get current volume levels for UI display (thread-safe)"""
        with self._levels_lock:
            return {
                'microphone': self._mic_level,
                'system_audio': self._system_level,
                'recording': self.recording,
                'buffer_duration': self._buffer_duration
            }

    def _update_levels_thread_safe(self, mic_level, sys_level, buffer_duration):
        """Update volume levels from recording thread (thread-safe)"""
        with self._levels_lock:
            self._mic_level = mic_level
            self._system_level = sys_level
            self._buffer_duration = buffer_duration

    def get_status_updates(self):
        """Get any pending status updates from the audio thread"""
        updates = []
        try:
            while True:
                update = self.status_queue.get_nowait()
                updates.append(update)
        except queue.Empty:
            pass
        return updates

    def send_command(self, command, data=None):
        """Send command to audio thread"""
        self.command_queue.put({'command': command, 'data': data})

    def get_levels(self):
        """Get current audio levels (thread-safe)"""
        with self._levels_lock:
            return {
                'mic': self._mic_level,
                'system': self._system_level
            }

    def get_buffer_status(self):
        """Get current buffer status"""
        return {
            'buffer_size': len(self.audio_buffer),
            'buffer_duration': self._buffer_duration,
            'recording': self.recording
        }

    def cleanup(self):
        """Clean up resources"""
        self.stop_recording()
        # No PyAudio cleanup needed - soundcard handles cleanup automatically

        # Clean up temp files
        try:
            import glob
            temp_files = glob.glob("temp_recordings/*.wav")
            for file in temp_files:
                try:
                    os.remove(file)
                except:
                    pass
        except:
            pass