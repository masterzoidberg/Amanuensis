import pyaudio
import wave
import threading
import time
import numpy as np
from collections import deque
import os
import queue
from logger_config import get_logger, log_function_call

# Import soundcard for loopback capture
try:
    import soundcard as sc
    SOUNDCARD_AVAILABLE = True
except ImportError:
    SOUNDCARD_AVAILABLE = False
    sc = None

class AudioManager:
    def __init__(self, buffer_duration=180):  # 3 minutes buffer
        self.logger = get_logger('audio_manager')
        self.logger.info("Initializing AudioManager")

        try:
            self.pa = pyaudio.PyAudio()
            self.buffer_duration = buffer_duration
            self.sample_rate = 44100
            self.channels = 2  # Stereo for dual-channel
            self.chunk_size = 1024
            self.format = pyaudio.paInt16

            # Audio buffers - using deque for efficient circular buffer
            self.audio_buffer = deque()
            self.recording = False
            self.recording_thread = None

            # Thread-safe communication
            self.status_queue = queue.Queue()  # For sending status updates to GUI
            self.command_queue = queue.Queue()  # For receiving commands from GUI
            self._thread_running = False
            self._shutdown_event = threading.Event()

            # Device settings
            self.input_device = None
            self.system_audio_device = None

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
        """Get list of available audio devices with enhanced filtering"""
        self.logger.debug("Scanning for audio devices...")

        input_devices = []
        output_devices = []
        system_recording_devices = []

        try:
            device_count = self.pa.get_device_count()
            self.logger.info(f"Found {device_count} audio devices")

            for i in range(device_count):
                try:
                    device_info = self.pa.get_device_info_by_index(i)
                    device_name = device_info['name']

                    # Clean up device name for better display
                    clean_name = self._clean_device_name(device_name)

                    self.logger.debug(f"Device {i}: '{clean_name}' (raw: '{device_name}') - In:{device_info['maxInputChannels']} Out:{device_info['maxOutputChannels']}")

                    # Input devices (microphones)
                    if device_info['maxInputChannels'] > 0:
                        # Check for system recording devices
                        if self._is_system_recording_device(device_name):
                            system_recording_devices.append({
                                'index': i,
                                'name': clean_name,
                                'raw_name': device_name,
                                'channels': device_info['maxInputChannels'],
                                'sample_rate': device_info['defaultSampleRate'],
                                'type': 'system_recording'
                            })
                            self.logger.debug(f"  -> Added as SYSTEM RECORDING device")
                        else:
                            input_devices.append({
                                'index': i,
                                'name': clean_name,
                                'raw_name': device_name,
                                'channels': device_info['maxInputChannels'],
                                'sample_rate': device_info['defaultSampleRate'],
                                'type': 'input'
                            })
                            self.logger.debug(f"  -> Added as INPUT device")

                    # Output devices (speakers/headphones)
                    if device_info['maxOutputChannels'] > 0:
                        output_devices.append({
                            'index': i,
                            'name': clean_name,
                            'raw_name': device_name,
                            'channels': device_info['maxOutputChannels'],
                            'sample_rate': device_info['defaultSampleRate'],
                            'type': 'output'
                        })
                        self.logger.debug(f"  -> Added as OUTPUT device")

                except Exception as e:
                    self.logger.warning(f"Error reading device {i}: {e}")
                    continue

            self.logger.info(f"Device scan complete: {len(input_devices)} input, {len(output_devices)} output, {len(system_recording_devices)} system recording")

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
        """Check if WASAPI host API is available for loopback capture"""
        try:
            # Check if we're on Windows
            import platform
            if platform.system() != 'Windows':
                self.logger.debug("WASAPI loopback not supported on non-Windows systems")
                return False
            
            # Check if PyAudio has WASAPI support
            host_api_count = self.pa.get_host_api_count()
            for i in range(host_api_count):
                try:
                    host_api_info = self.pa.get_host_api_info_by_index(i)
                    if host_api_info['name'].lower() == 'wasapi':
                        self.logger.debug(f"WASAPI host API found: {host_api_info['name']}")
                        return True
                except Exception as e:
                    self.logger.debug(f"Error checking host API {i}: {e}")
                    continue
            
            self.logger.debug("WASAPI host API not found")
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking WASAPI support: {e}")
            return False

    def open_system_loopback_stream(self):
        """Open a WASAPI output device in loopback mode for system audio capture"""
        try:
            if not self.supports_wasapi_loopback():
                self.logger.debug("WASAPI loopback not supported")
                return None
            
            # Find WASAPI host API
            host_api_count = self.pa.get_host_api_count()
            wasapi_host_api = None
            
            for i in range(host_api_count):
                try:
                    host_api_info = self.pa.get_host_api_info_by_index(i)
                    if host_api_info['name'].lower() == 'wasapi':
                        wasapi_host_api = i
                        break
                except Exception as e:
                    self.logger.debug(f"Error checking host API {i}: {e}")
                    continue
            
            if wasapi_host_api is None:
                self.logger.debug("WASAPI host API not found")
                return None
            
            # Find default output device for WASAPI
            default_output = self.pa.get_default_output_device_info()
            self.logger.debug(f"Default output device: {default_output['name']}")
            
            # Open stream in loopback mode
            stream = self.pa.open(
                format=self.format,
                channels=2,  # Stereo
                rate=44100,  # 44.1kHz
                input=True,
                input_device_index=default_output['index'],
                frames_per_buffer=1024,
                stream_callback=None,
                host_api_specific_stream_info={
                    'host_api': wasapi_host_api,
                    'flags': 0x00000001  # paWinWasapiLoopback flag
                }
            )
            
            self.logger.info(f"WASAPI loopback stream opened successfully for device: {default_output['name']}")
            return stream
            
        except OSError as e:
            self.logger.warning(f"WASAPI loopback stream failed (OSError): {e}")
            return None
        except Exception as e:
            self.logger.warning(f"WASAPI loopback stream failed: {e}")
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
        """Test a specific audio device"""
        try:
            if device_type == 'input':
                stream = self.pa.open(
                    format=self.format,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=self.chunk_size
                )

                print(f"Testing device {device_index} for {duration} seconds...")
                max_level = 0
                total_samples = int(duration * self.sample_rate / self.chunk_size)

                for i in range(total_samples):
                    try:
                        data = stream.read(self.chunk_size, exception_on_overflow=False)
                        audio_data = np.frombuffer(data, dtype=np.int16)
                        level = np.sqrt(np.mean(audio_data**2))
                        max_level = max(max_level, level)

                        if i % 10 == 0:  # Print progress
                            print(f"Level: {level:.0f}")
                    except Exception as e:
                        print(f"Read error: {e}")
                        continue

                stream.stop_stream()
                stream.close()

                return True, f"Test completed. Max level: {max_level:.0f}"

            else:
                return False, "Output device testing not supported"

        except Exception as e:
            return False, f"Device test failed: {str(e)}"

    def get_device_info(self, device_index):
        """Get detailed information about a specific device"""
        try:
            info = self.pa.get_device_info_by_index(device_index)
            return {
                'name': info['name'],
                'max_input_channels': info['maxInputChannels'],
                'max_output_channels': info['maxOutputChannels'],
                'default_sample_rate': info['defaultSampleRate'],
                'default_low_input_latency': info['defaultLowInputLatency'],
                'default_low_output_latency': info['defaultLowOutputLatency'],
                'default_high_input_latency': info['defaultHighInputLatency'],
                'default_high_output_latency': info['defaultHighOutputLatency']
            }
        except Exception as e:
            return {'error': str(e)}

    def set_input_device(self, device_index):
        """Set the microphone input device"""
        self.logger.info(f"Setting input device to index {device_index}")
        try:
            device_info = self.pa.get_device_info_by_index(device_index)
            input_channels = device_info['maxInputChannels']

            # Validate that this device can actually record
            if input_channels == 0:
                error_msg = f"Device '{device_info['name']}' has 0 input channels - cannot be used for recording"
                self.logger.error(error_msg)
                self.logger.error("This appears to be an output device. Please select a microphone or input device.")
                self.input_device = None
                return False, error_msg

            self.logger.info(f"Input device set: '{device_info['name']}' (channels: {input_channels})")
            self.input_device = device_index
            return True, f"Input device set: {device_info['name']}"

        except Exception as e:
            error_msg = f"Failed to set input device {device_index}: {e}"
            self.logger.error(error_msg)
            self.input_device = None
            return False, error_msg

    def set_system_audio_device(self, device_index):
        """Set the system audio input device (e.g., Stereo Mix)"""
        self.logger.info(f"Setting system audio device to index {device_index}")

        # Handle placeholder device
        if device_index == -1:
            error_msg = "Cannot set placeholder system audio device. Please enable Stereo Mix in Windows."
            self.logger.warning(error_msg)
            self.system_audio_device = None
            return False, error_msg

        try:
            device_info = self.pa.get_device_info_by_index(device_index)
            input_channels = device_info['maxInputChannels']

            # Validate that this device can actually record
            if input_channels == 0:
                error_msg = f"Device '{device_info['name']}' has 0 input channels - cannot be used for recording"
                self.logger.error(error_msg)
                self.logger.error("This appears to be an output device. System audio requires an input device like Stereo Mix.")
                self.system_audio_device = None
                return False, error_msg

            self.logger.info(f"System audio device set: '{device_info['name']}' (channels: {input_channels})")
            self.system_audio_device = device_index
            # Clear any special mode when setting a device
            if hasattr(self, 'system_audio_mode'):
                delattr(self, 'system_audio_mode')
            return True, f"System audio device set: {device_info['name']}"

        except Exception as e:
            error_msg = f"Failed to set system audio device {device_index}: {e}"
            self.logger.error(error_msg)
            self.system_audio_device = None
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
        # Clear device index when using special modes
        if mode in ['soundcard_loopback', 'wasapi_loopback', 'mic_only']:
            self.system_audio_device = None
        
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
            
            # Handle device index
            try:
                device_info = self.pa.get_device_info_by_index(device_id)
                device_name = device_info['name']
                
                # Check if device has input channels
                if device_info['maxInputChannels'] == 0:
                    self.logger.debug(f"Preflight failed: Device '{device_name}' has no input channels")
                    return False
                
                # Try to open the device briefly
                test_stream = self.pa.open(
                    format=self.format,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=device_id,
                    frames_per_buffer=self.chunk_size
                )
                
                # Close immediately
                test_stream.close()
                
                self.logger.debug(f"Preflight SUCCESS: Device '{device_name}' (index {device_id})")
                return True
                
            except Exception as e:
                self.logger.debug(f"Preflight FAILED: Device {device_id} - {str(e)}")
                return False
                
        except Exception as e:
            self.logger.error(f"Preflight test error for device {device_id}: {e}")
            return False

    def test_audio_levels(self, duration=5):
        """Test audio levels for both input sources"""
        if self.input_device is None or self.system_audio_device is None:
            return False, "Devices not configured"

        try:
            # Test microphone
            mic_stream = self.pa.open(
                format=self.format,
                channels=1,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.input_device,
                frames_per_buffer=self.chunk_size
            )

            # Test system audio
            system_stream = self.pa.open(
                format=self.format,
                channels=1,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.system_audio_device,
                frames_per_buffer=self.chunk_size
            )

            print("Testing audio levels for 5 seconds...")
            for i in range(int(duration * self.sample_rate / self.chunk_size)):
                # Read from microphone
                mic_data = mic_stream.read(self.chunk_size)
                mic_audio = np.frombuffer(mic_data, dtype=np.int16)
                self.mic_level = np.sqrt(np.mean(mic_audio**2))

                # Read from system audio
                system_data = system_stream.read(self.chunk_size)
                system_audio = np.frombuffer(system_data, dtype=np.int16)
                self.system_level = np.sqrt(np.mean(system_audio**2))

                if i % 10 == 0:  # Print every ~0.25 seconds
                    print(f"Mic: {self.mic_level:.0f} | System: {self.system_level:.0f}")

            mic_stream.stop_stream()
            mic_stream.close()
            system_stream.stop_stream()
            system_stream.close()

            return True, "Audio test completed"

        except Exception as e:
            return False, f"Audio test failed: {str(e)}"

    @log_function_call('audio_manager')
    def start_recording(self):
        """Start dual-channel audio recording"""
        self.logger.info("Starting audio recording...")

        if self.recording:
            self.logger.warning("Recording already in progress")
            return False, "Already recording"

        if self.input_device is None:
            self.logger.error(f"Input device not configured - Input: {self.input_device}")
            return False, "Input device not configured"
        
        # Check if we have a system audio device or special mode
        has_system_audio = (self.system_audio_device is not None or 
                          hasattr(self, 'system_audio_mode') and self.system_audio_mode in ['wasapi_loopback', 'mic_only'])
        
        if not has_system_audio:
            self.logger.error(f"System audio not configured - Device: {self.system_audio_device}, Mode: {getattr(self, 'system_audio_mode', None)}")
            return False, "System audio not configured"

        # Validate device capabilities before attempting recording
        try:
            # Check microphone device
            mic_info = self.pa.get_device_info_by_index(self.input_device)
            if mic_info['maxInputChannels'] == 0:
                self.logger.error(f"Microphone device {self.input_device} ({mic_info['name']}) has no input channels")
                return False, f"Invalid microphone device: {mic_info['name']} (0 input channels)"

            # Test device compatibility by attempting to open streams briefly
            self.logger.debug("Testing device compatibility...")
            
            # Test microphone device
            try:
                test_mic_stream = self.pa.open(
                    format=self.format,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=self.input_device,
                    frames_per_buffer=self.chunk_size
                )
                test_mic_stream.close()
                self.logger.debug(f"Microphone device test passed: {mic_info['name']}")
            except Exception as mic_test_error:
                self.logger.error(f"Microphone device test failed: {mic_test_error}")
                return False, f"Microphone device '{mic_info['name']}' is not compatible: {str(mic_test_error)}"

            # Test system audio based on mode
            system_audio_mode = getattr(self, 'system_audio_mode', 'device')
            
            if system_audio_mode == 'wasapi_loopback':
                # Test WASAPI loopback
                try:
                    test_loopback_stream = self.open_system_loopback_stream()
                    if test_loopback_stream:
                        test_loopback_stream.close()
                        self.logger.debug("WASAPI loopback test passed")
                    else:
                        self.logger.error("WASAPI loopback test failed")
                        return False, "WASAPI loopback is not available"
                except Exception as loopback_test_error:
                    self.logger.error(f"WASAPI loopback test failed: {loopback_test_error}")
                    return False, f"WASAPI loopback test failed: {str(loopback_test_error)}"
                    
            elif system_audio_mode == 'mic_only':
                # Mic-only mode - no system audio testing needed
                self.logger.debug("Mic-only mode - skipping system audio test")
                
            else:
                # Traditional device-based system audio
                sys_info = self.pa.get_device_info_by_index(self.system_audio_device)
                if sys_info['maxInputChannels'] == 0:
                    self.logger.error(f"System audio device {self.system_audio_device} ({sys_info['name']}) has no input channels")
                    return False, f"Invalid system audio device: {sys_info['name']} (0 input channels)"

                try:
                    test_sys_stream = self.pa.open(
                        format=self.format,
                        channels=1,
                        rate=self.sample_rate,
                        input=True,
                        input_device_index=self.system_audio_device,
                        frames_per_buffer=self.chunk_size
                    )
                    test_sys_stream.close()
                    self.logger.debug(f"System audio device test passed: {sys_info['name']}")
                except Exception as sys_test_error:
                    self.logger.error(f"System audio device test failed: {sys_test_error}")
                    # Provide specific guidance for Stereo Mix issues
                    error_guidance = f"System audio device '{sys_info['name']}' is not compatible: {str(sys_test_error)}"
                    if "Stereo Mix" in sys_info['name'] or "Unanticipated host error" in str(sys_test_error):
                        error_guidance += "\n\nTip: Stereo Mix may be disabled in Windows. Try:\n1. Right-click sound icon → Sounds → Recording tab\n2. Right-click empty space → Show Disabled Devices\n3. Enable Stereo Mix if available\n4. Or select a different system audio device"
                    return False, error_guidance

            self.logger.debug(f"Device validation passed - Mic: {mic_info['name']} ({mic_info['maxInputChannels']} ch), System mode: {system_audio_mode}")

        except Exception as e:
            self.logger.error(f"Device validation failed: {e}")
            return False, f"Device validation error: {str(e)}"

        try:
            self.recording = True
            self.audio_buffer.clear()

            self.logger.debug("Creating recording thread...")
            self.recording_thread = threading.Thread(target=self._recording_loop)
            self.recording_thread.daemon = True
            self.recording_thread.start()

            self.logger.info("Audio recording started successfully")
            return True, "Recording started"

        except Exception as e:
            self.logger.error(f"Failed to start recording: {e}")
            self.recording = False
            return False, f"Recording start failed: {str(e)}"

    def _recording_loop(self):
        """Main recording loop running in separate thread with full exception isolation"""
        self.logger.debug("Recording loop thread started")
        self._thread_running = True

        mic_stream = None
        system_stream = None

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
            # Open microphone stream
            self.logger.debug(f"Opening microphone stream (device {self.input_device})")
            mic_stream = self.pa.open(
                format=self.format,
                channels=1,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.input_device,
                frames_per_buffer=self.chunk_size
            )

            # Open system audio stream based on mode
            system_audio_mode = getattr(self, 'system_audio_mode', 'device')
            
            if system_audio_mode == 'soundcard_loopback':
                self.logger.debug("Opening soundcard loopback stream")
                self.soundcard_loopback_mic = self.open_soundcard_loopback_stream()
                if not self.soundcard_loopback_mic:
                    self.logger.error("Failed to open soundcard loopback stream")
                    return
                system_stream = None  # Will be handled by soundcard thread
            elif system_audio_mode == 'wasapi_loopback':
                self.logger.debug("Opening WASAPI loopback stream")
                system_stream = self.open_system_loopback_stream()
                if not system_stream:
                    self.logger.error("Failed to open WASAPI loopback stream")
                    return
            elif system_audio_mode == 'mic_only':
                self.logger.debug("Mic-only mode - no system audio stream")
                system_stream = None
            else:
                # Traditional device-based system audio
                self.logger.debug(f"Opening system audio stream (device {self.system_audio_device})")
                system_stream = self.pa.open(
                    format=self.format,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=self.system_audio_device,
                    frames_per_buffer=self.chunk_size
                )

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
                    # Read from microphone
                    mic_data = mic_stream.read(self.chunk_size, exception_on_overflow=False)
                    mic_audio = np.frombuffer(mic_data, dtype=np.int16)
                    mic_level = np.sqrt(np.mean(mic_audio**2))

                    # Read from system audio based on mode
                    if system_audio_mode == 'soundcard_loopback':
                        # Soundcard loopback is handled by separate thread
                        # For now, create silent system audio (would be replaced by actual soundcard data)
                        system_audio = np.zeros_like(mic_audio)
                        sys_level = 0.0
                    elif system_stream is not None:
                        system_data = system_stream.read(self.chunk_size, exception_on_overflow=False)
                        system_audio = np.frombuffer(system_data, dtype=np.int16)
                        sys_level = np.sqrt(np.mean(system_audio**2))
                    else:
                        # Mic-only mode - create silent system audio
                        system_audio = np.zeros_like(mic_audio)
                        sys_level = 0.0

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

                    # Send audio data to registered callbacks for real-time transcription
                    # Convert to float32 format for transcription (same as transcription bridge expects)
                    stereo_float = stereo_data.astype(np.float32) / 32768.0
                    self._call_audio_callbacks(stereo_float, self.sample_rate)

                    # Add to circular buffer
                    self.audio_buffer.append(stereo_data.tobytes())

                    # Maintain buffer size
                    while len(self.audio_buffer) > buffer_max_size:
                        self.audio_buffer.popleft()

                    chunk_count += 1

                    # Log buffer status every 30 seconds
                    if chunk_count % (30 * self.sample_rate // self.chunk_size) == 0:
                        duration = self.get_recording_duration()
                        self.logger.debug(f"Recording status: {chunk_count} chunks, {duration:.1f}s buffered, Mic:{mic_level:.1f}, Sys:{sys_level:.1f}")

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
                        pass  # Skip if queue is full to avoid blocking

                except Exception as e:
                    self.logger.error(f"Recording error in loop: {e}")
                    continue

            self.logger.info(f"Recording loop ended after {chunk_count} chunks")

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

            # Clean up streams with full error isolation
            if mic_stream:
                try:
                    mic_stream.stop_stream()
                    mic_stream.close()
                    self.logger.debug("Microphone stream closed")
                except Exception as e:
                    self.logger.warning(f"Error closing mic stream: {e}")

            if system_stream:
                try:
                    system_stream.stop_stream()
                    system_stream.close()
                    self.logger.debug("System audio stream closed")
                except Exception as e:
                    self.logger.warning(f"Error closing system stream: {e}")
            
            # Clean up soundcard loopback if used
            if hasattr(self, 'soundcard_loopback_mic') and self.soundcard_loopback_mic:
                try:
                    # Soundcard cleanup is handled by the context manager
                    self.soundcard_loopback_mic = None
                    self.logger.debug("Soundcard loopback cleaned up")
                except Exception as e:
                    self.logger.warning(f"Error cleaning up soundcard loopback: {e}")

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
        wf.setsampwidth(self.pa.get_sample_size(self.format))
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

    def cleanup(self):
        """Clean up resources"""
        self.stop_recording()
        self.pa.terminate()

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