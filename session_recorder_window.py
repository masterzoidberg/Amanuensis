#!/usr/bin/env python3
"""
Compact Session Recording Window (400x300)
Main recording interface for therapists during live sessions
"""

import customtkinter as ctk
import threading
import time
from typing import Callable, Optional
from datetime import datetime, timedelta
import pyaudio
import numpy as np
from logger_config import get_logger, log_function_call
from theme_manager import get_theme_manager, apply_professional_styling

class SessionRecorderWindow:
    """Compact session recording window for live therapy sessions"""

    def __init__(self, config_manager, audio_manager, whisper_manager, on_insights_request: Optional[Callable] = None):
        self.logger = get_logger('session_recorder')
        self.logger.info("Initializing Session Recorder Window")

        self.config_manager = config_manager
        self.audio_manager = audio_manager
        self.whisper_manager = whisper_manager
        self.on_insights_request = on_insights_request

        # Recording state
        self.is_recording = False
        self.session_start_time = None
        self.current_transcript = []
        self.always_on_top = False
        self.audio_level_monitoring = False

        # Transcription bridge
        self.transcription_bridge = None
        if self.whisper_manager:
            try:
                from audio_transcription_bridge import AudioTranscriptionBridge
                self.transcription_bridge = AudioTranscriptionBridge(audio_manager, whisper_manager)
                self.logger.info("Audio transcription bridge initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize transcription bridge: {e}")

        # Model status tracking
        self.model_status = {
            'loaded': False,
            'loading': False,
            'error': None
        }

        # Session storage
        self.storage_manager = None
        try:
            from session_storage_manager import SessionStorageManager
            self.storage_manager = SessionStorageManager()
            self.logger.info("Session storage manager initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize storage manager: {e}")

        # UI update thread
        self.ui_thread = None
        self.ui_update_running = False

        self.logger.debug("Setting up UI components...")
        self.setup_ui()

        self.logger.debug("Setting up transcription callback...")
        self.setup_transcription_callback()

        # Update model status
        self.update_model_status()

        self.logger.info("Session Recorder Window initialized successfully")

    def update_model_status(self):
        """Update model status display"""
        try:
            if self.whisper_manager:
                if hasattr(self.whisper_manager, 'get_model_status'):
                    status = self.whisper_manager.get_model_status()
                    self.model_status.update({
                        'loaded': status.get('loaded', False),
                        'loading': status.get('loading', False),
                        'error': None
                    })
                    
                    # Update model status label if available
                    if hasattr(self, 'model_status_label'):
                        if status.get('loaded'):
                            model_name = status.get('model_name', 'unknown')
                            device = status.get('device', 'unknown')
                            stats = status.get('stats', {})
                            latency = stats.get('average_latency', 0)

                            status_text = f"Model: {model_name} • {device}"
                            if latency > 0:
                                status_text += f" • {latency:.1f}ms"

                            self.model_status_label.configure(
                                text=status_text,
                                text_color="#2CC985"
                            )
                        elif status.get('loading'):
                            self.model_status_label.configure(
                                text="Loading model...",
                                text_color="#F39C12"
                            )
                        elif status.get('model_downloaded'):
                            # Model is downloaded but not loaded - show load option
                            model_name = status.get('model_name', 'unknown')
                            self.model_status_label.configure(
                                text=f"Model: {model_name} (ready to load)",
                                text_color="#F39C12"
                            )
                        else:
                            # No model downloaded
                            model_name = status.get('model_name', 'unknown')
                            self.model_status_label.configure(
                                text=f"Model: {model_name} (not downloaded)",
                                text_color="#E74C3C"
                            )
                else:
                    self.model_status['loaded'] = False
                    self.model_status['error'] = "Whisper manager not compatible"
            else:
                self.model_status['loaded'] = False
                self.model_status['error'] = "No whisper manager available"
                
        except Exception as e:
            self.logger.error(f"Error updating model status: {e}")
            self.model_status['error'] = str(e)

    def setup_ui(self):
        """Setup the compact recording interface"""
        self.window = ctk.CTk()
        self.window.title("Amanuensis - Session Recorder")
        self.window.geometry("400x600")
        self.window.resizable(True, True)
        self.window.minsize(400, 500)  # Minimum size to keep UI functional

        # Use theme manager for consistent appearance
        self.theme_manager = get_theme_manager()

        # Apply current theme (don't force dark mode)
        current_theme = self.theme_manager.get_current_theme()
        self.logger.debug(f"Using theme: {current_theme}")

        # Register for theme changes
        self.theme_manager.register_theme_callback(self.on_theme_changed)

        # Create menu bar
        self.create_menu_bar()

        # Main container
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Header
        header_frame = ctk.CTkFrame(main_frame)
        header_frame.pack(fill="x", pady=(0, 15))

        title_label = ctk.CTkLabel(
            header_frame,
            text="Amanuensis Session Recorder",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=15)

        # Session info
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(fill="x", pady=(0, 15))

        # Client count selection
        client_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        client_frame.pack(pady=(10, 5))

        ctk.CTkLabel(
            client_frame,
            text="Session Type:",
            font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=(0, 10))

        self.client_count = ctk.CTkComboBox(
            client_frame,
            values=["Individual (1 client)", "Couple (2 clients)", "Family (3+ clients)", "Group Session"],
            width=180,
            height=25,
            font=ctk.CTkFont(size=11)
        )
        self.client_count.pack(side="left")
        self.client_count.set("Individual (1 client)")

        # Session timer
        self.timer_label = ctk.CTkLabel(
            info_frame,
            text="00:00:00",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#2CC985"
        )
        self.timer_label.pack(pady=(10, 5))

        # Status indicator
        self.status_label = ctk.CTkLabel(
            info_frame,
            text="[*] Ready",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.status_label.pack(pady=(0, 5))

        # Audio level indicators
        level_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        level_frame.pack(pady=(0, 10))

        # Microphone level
        mic_level_frame = ctk.CTkFrame(level_frame, fg_color="transparent")
        mic_level_frame.pack(fill="x", pady=2)

        ctk.CTkLabel(mic_level_frame, text="Mic:", font=ctk.CTkFont(size=10)).pack(side="left")
        self.mic_level_bar = ctk.CTkProgressBar(mic_level_frame, width=100, height=8)
        self.mic_level_bar.pack(side="left", padx=(5, 5))
        self.mic_level_bar.set(0)

        self.mic_level_label = ctk.CTkLabel(mic_level_frame, text="0", font=ctk.CTkFont(size=10))
        self.mic_level_label.pack(side="left")

        # System audio level
        sys_level_frame = ctk.CTkFrame(level_frame, fg_color="transparent")
        sys_level_frame.pack(fill="x", pady=2)

        ctk.CTkLabel(sys_level_frame, text="Sys:", font=ctk.CTkFont(size=10)).pack(side="left")
        self.sys_level_bar = ctk.CTkProgressBar(sys_level_frame, width=100, height=8)
        self.sys_level_bar.pack(side="left", padx=(5, 5))
        self.sys_level_bar.set(0)

        self.sys_level_label = ctk.CTkLabel(sys_level_frame, text="0", font=ctk.CTkFont(size=10))
        self.sys_level_label.pack(side="left")

        # Audio devices frame
        devices_frame = ctk.CTkFrame(main_frame)
        devices_frame.pack(fill="x", pady=(0, 15))

        devices_title = ctk.CTkLabel(
            devices_frame,
            text="Audio Setup",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        devices_title.pack(pady=(10, 5))

        # Therapist mic
        mic_frame = ctk.CTkFrame(devices_frame, fg_color="transparent")
        mic_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(mic_frame, text="Therapist Mic:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.mic_combo = ctk.CTkComboBox(
            mic_frame,
            values=self.get_input_devices(),
            width=250,
            height=25,
            font=ctk.CTkFont(size=10)
        )
        self.mic_combo.pack(fill="x", pady=(2, 0))

        # System audio
        sys_frame = ctk.CTkFrame(devices_frame, fg_color="transparent")
        sys_frame.pack(fill="x", padx=15, pady=(5, 15))

        ctk.CTkLabel(sys_frame, text="System Audio:", font=ctk.CTkFont(size=11)).pack(anchor="w")
        self.sys_combo = ctk.CTkComboBox(
            sys_frame,
            values=self.get_output_devices(),
            width=250,
            height=25,
            font=ctk.CTkFont(size=10)
        )
        self.sys_combo.pack(fill="x", pady=(2, 0))

        # Recording controls
        controls_frame = ctk.CTkFrame(main_frame)
        controls_frame.pack(fill="x", pady=(0, 15))

        # Start/Stop recording button
        self.record_button = ctk.CTkButton(
            controls_frame,
            text="Start Recording",
            command=self.toggle_recording,
            width=300,
            height=45,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=("#2CC985", "#2FA572")
        )
        self.record_button.pack(pady=15)

        # Transcription display
        transcript_frame = ctk.CTkFrame(main_frame)
        transcript_frame.pack(fill="both", expand=True, pady=(0, 15))

        # Transcript header with status
        transcript_header = ctk.CTkFrame(transcript_frame, fg_color="transparent")
        transcript_header.pack(fill="x", padx=10, pady=(10, 5))

        transcript_title = ctk.CTkLabel(
            transcript_header,
            text="Live Transcript",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        transcript_title.pack(side="left")

        # Model status indicator
        self.model_status_label = ctk.CTkLabel(
            transcript_header,
            text="Model not loaded",
            font=ctk.CTkFont(size=9),
            text_color="#E74C3C"
        )
        self.model_status_label.pack(side="right")

        self.transcript_display = ctk.CTkTextbox(
            transcript_frame,
            height=80,
            font=ctk.CTkFont(size=10),
            wrap="word"
        )
        self.transcript_display.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Session Notes
        notes_frame = ctk.CTkFrame(main_frame)
        notes_frame.pack(fill="x", pady=(0, 15))

        notes_title = ctk.CTkLabel(
            notes_frame,
            text="Session Notes",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        notes_title.pack(pady=(10, 5))

        self.session_notes = ctk.CTkTextbox(
            notes_frame,
            height=60,
            font=ctk.CTkFont(size=10),
            wrap="word"
        )
        self.session_notes.pack(fill="x", padx=10, pady=(0, 10))
        # Insert placeholder text for session notes
        self.session_notes.insert("0.0", "Add your session observations and notes here...")

        # Analysis buttons
        analysis_frame = ctk.CTkFrame(main_frame)
        analysis_frame.pack(fill="x", pady=(0, 10))

        # Create preset analysis buttons in a grid
        self.create_analysis_buttons(analysis_frame)

        # File info frame
        file_info_frame = ctk.CTkFrame(main_frame)
        file_info_frame.pack(fill="x", pady=(0, 10))

        file_info_title = ctk.CTkLabel(
            file_info_frame,
            text="Recording Location",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        file_info_title.pack(pady=(10, 5))

        # Get absolute path for temp_recordings
        import os
        temp_dir = os.path.abspath("temp_recordings")
        self.save_location_label = ctk.CTkLabel(
            file_info_frame,
            text=temp_dir,
            font=ctk.CTkFont(size=9),
            text_color="gray"
        )
        self.save_location_label.pack(pady=(0, 10))

        # Options frame
        options_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        options_frame.pack(fill="x")

        # Always on top toggle
        self.always_on_top_var = ctk.BooleanVar()
        always_on_top_cb = ctk.CTkCheckBox(
            options_frame,
            text="Always on top",
            variable=self.always_on_top_var,
            command=self.toggle_always_on_top,
            font=ctk.CTkFont(size=11)
        )
        always_on_top_cb.pack(side="left", padx=(10, 0))

        # Export button
        export_button = ctk.CTkButton(
            options_frame,
            text="Export",
            command=self.export_recording,
            width=60,
            height=25,
            font=ctk.CTkFont(size=11),
            fg_color=("#2CC985", "#2FA572")
        )
        export_button.pack(side="right", padx=(5, 10))

        # Insights button
        insights_button = ctk.CTkButton(
            options_frame,
            text="Insights",
            command=self.show_insights,
            width=60,
            height=25,
            font=ctk.CTkFont(size=11),
            fg_color=("#FF6B35", "#E8590C")
        )
        insights_button.pack(side="right")

        # Start UI updates
        self.start_ui_updates()

    def create_menu_bar(self):
        """Create menu bar for the application"""
        try:
            # Create menu bar using tkinter (CustomTkinter doesn't have native menu support)
            import tkinter as tk

            menubar = tk.Menu(self.window)
            self.window.configure(menu=menubar)

            # File menu
            file_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="File", menu=file_menu)
            file_menu.add_command(label="Export Recording...", command=self.export_recording)
            file_menu.add_separator()
            file_menu.add_command(label="Exit", command=self.close)

            # Settings menu
            settings_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="Settings", menu=settings_menu)
            settings_menu.add_command(label="Preferences...", command=self.show_settings)
            settings_menu.add_command(label="Audio Devices...", command=self.show_audio_settings)
            settings_menu.add_command(label="Whisper Models...", command=self.show_whisper_settings)

            # Tools menu
            tools_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="Tools", menu=tools_menu)
            tools_menu.add_command(label="Test Audio Devices", command=self.test_audio_devices)
            tools_menu.add_command(label="View Logs", command=self.view_logs)

            # Help menu
            help_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="Help", menu=help_menu)
            help_menu.add_command(label="About", command=self.show_about)

            self.logger.debug("Menu bar created successfully")

        except Exception as e:
            self.logger.error(f"Failed to create menu bar: {e}")

    def show_settings(self):
        """Show general settings window"""
        self.logger.info("Opening settings window...")
        from settings_window import SettingsWindow

        if not hasattr(self, 'settings_window') or not self.settings_window.window.winfo_exists():
            self.settings_window = SettingsWindow(
                parent=self.window,
                config_manager=self.config_manager,
                audio_manager=self.audio_manager,
                whisper_manager=self.whisper_manager,
                model_manager=getattr(self, 'model_manager', None)
            )
        else:
            self.settings_window.window.lift()
            self.settings_window.window.focus()

    def show_audio_settings(self):
        """Show audio settings window"""
        self.show_settings()
        # Switch to audio tab if possible

    def show_whisper_settings(self):
        """Show Whisper model settings window"""
        self.show_settings()
        # Switch to whisper tab if possible

    def test_audio_devices(self):
        """Test audio device functionality"""
        self.logger.info("Testing audio devices...")
        # TODO: Implement audio device testing

    def view_logs(self):
        """Open log viewer"""
        self.logger.info("Opening log viewer...")
        import subprocess
        import sys
        try:
            subprocess.Popen([sys.executable, "view_logs.py", "--lines", "100"])
        except Exception as e:
            self.logger.error(f"Failed to open log viewer: {e}")

    def show_about(self):
        """Show about dialog"""
        from tkinter import messagebox
        messagebox.showinfo(
            "About Amanuensis",
            "Amanuensis v1.0\n"
            "Therapy Session Assistant\n\n"
            "A privacy-focused therapy transcription and analysis tool\n"
            "with local Whisper AI integration."
        )

    def create_analysis_buttons(self, parent):
        """Create preset analysis buttons"""
        analysis_buttons = [
            ("Themes", self.analyze_themes, "#8E44AD"),
            ("Progress", self.analyze_progress, "#3498DB"),
            ("Risk", self.analyze_risk, "#E74C3C"),
            ("Dynamics", self.analyze_dynamics, "#F39C12")
        ]

        # Create grid layout
        button_width = 80
        button_height = 30

        # Top row
        top_frame = ctk.CTkFrame(parent, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=5)

        themes_btn = ctk.CTkButton(
            top_frame,
            text="Themes",
            command=self.analyze_themes,
            width=button_width,
            height=button_height,
            font=ctk.CTkFont(size=10),
            fg_color="#8E44AD"
        )
        themes_btn.pack(side="left", padx=(0, 5))

        progress_btn = ctk.CTkButton(
            top_frame,
            text="Progress",
            command=self.analyze_progress,
            width=button_width,
            height=button_height,
            font=ctk.CTkFont(size=10),
            fg_color="#3498DB"
        )
        progress_btn.pack(side="left", padx=5)

        risk_btn = ctk.CTkButton(
            top_frame,
            text="Risk",
            command=self.analyze_risk,
            width=button_width,
            height=button_height,
            font=ctk.CTkFont(size=10),
            fg_color="#E74C3C"
        )
        risk_btn.pack(side="left", padx=5)

        dynamics_btn = ctk.CTkButton(
            top_frame,
            text="Dynamics",
            command=self.analyze_dynamics,
            width=button_width,
            height=button_height,
            font=ctk.CTkFont(size=10),
            fg_color="#F39C12"
        )
        dynamics_btn.pack(side="left", padx=(5, 0))

        # Custom analysis button
        custom_btn = ctk.CTkButton(
            parent,
            text="Custom Analysis",
            command=self.custom_analysis,
            width=200,
            height=25,
            font=ctk.CTkFont(size=10),
            fg_color=("gray60", "gray40")
        )
        custom_btn.pack(pady=(5, 10))

    def get_input_devices(self):
        """Get available input audio devices"""
        try:
            input_devices = self.audio_manager.get_input_devices()
            return [device['name'] for device in input_devices] if input_devices else ["Default Microphone"]
        except Exception as e:
            print(f"Error getting input devices: {e}")
            return ["Default Microphone"]

    def get_output_devices(self):
        """Get available output/recording audio devices"""
        try:
            system_devices = self.audio_manager.get_system_audio_devices()
            return [device['name'] for device in system_devices] if system_devices else ["Default Speakers"]
        except Exception as e:
            print(f"Error getting output devices: {e}")
            return ["Default Speakers"]

    def toggle_recording(self):
        """Toggle recording state"""
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    @log_function_call('session_recorder')
    def start_recording(self):
        """Start recording session with improved device selection and fallbacks"""
        self.logger.info("Starting recording session...")

        try:
            # Get configuration for audio capture mode
            from transcription_config import get_transcription_config
            config = get_transcription_config()
            capture_mode = config.get('audio_capture_mode', 'auto')
            
            self.logger.info(f"Audio capture mode: {capture_mode}")

            # Set microphone device from UI selection
            input_devices = self.audio_manager.get_input_devices()
            mic_selection = self.mic_combo.get()
            
            mic_index = None
            for i, device in enumerate(input_devices):
                if device['name'] in mic_selection:
                    mic_index = device['index']
                    self.logger.debug(f"Found microphone device: {device['name']} (index {mic_index})")
                    break

            if mic_index is None:
                self.logger.error(f"Microphone device not found: '{mic_selection}'")
                self.status_label.configure(text="[!] Microphone device not found", text_color="#E74C3C")
                return

            # Set microphone device
            self.audio_manager.set_input_device(mic_index)

            # System audio device selection with preflight testing and fallback order
            system_audio_path = None
            sys_index = None
            fallback_reason = None
            
            # Define fallback order based on capture mode
            fallback_options = []
            
            if capture_mode in ['auto', 'loopback']:
                # Try soundcard loopback first (most reliable)
                fallback_options.append(("soundcard_loopback", "Soundcard loopback"))
                # Then WASAPI loopback as fallback
                fallback_options.append(("wasapi_loopback", "WASAPI loopback"))
            
            if capture_mode in ['auto', 'stereo_mix']:
                # Add Stereo Mix devices
                system_devices = self.audio_manager.get_system_audio_devices()
                sys_selection = self.sys_combo.get()
                
                for i, device in enumerate(system_devices):
                    if device['name'] in sys_selection:
                        fallback_options.append((device['index'], f"Stereo Mix (Device: {device['name']})"))
                        break
            
            if capture_mode in ['auto', 'mic_only']:
                fallback_options.append(("mic_only", "mic-only"))
            
            # Test each option with preflight
            self.logger.info("Starting system audio preflight testing...")
            
            for device_id, device_description in fallback_options:
                self.logger.info(f"Preflight testing: {device_description}")
                
                if self.audio_manager.preflight_open(device_id):
                    sys_index = device_id
                    system_audio_path = device_description
                    self.logger.info(f"Preflight SUCCESS: {device_description}")
                    break
                else:
                    error_msg = f"Device preflight failed: {device_description} — falling back."
                    self.logger.warning(error_msg)
                    fallback_reason = error_msg
            
            if sys_index is None:
                self.logger.error("All system audio capture methods failed preflight testing")
                self.status_label.configure(text="[!] No system audio capture available", text_color="#E74C3C")
                return

            # Set system audio device (or special mode)
            if sys_index == "soundcard_loopback":
                # Set soundcard loopback mode
                success, message = self.audio_manager.set_system_audio_mode("soundcard_loopback")
                if not success:
                    self.logger.error(f"Failed to set soundcard loopback mode: {message}")
                    self.status_label.configure(text="[!] Soundcard loopback setup failed", text_color="#E74C3C")
                    return
                self.logger.info("System audio mode set to soundcard loopback")
            elif sys_index == "wasapi_loopback":
                # Set WASAPI loopback mode
                success, message = self.audio_manager.set_system_audio_mode("wasapi_loopback")
                if not success:
                    self.logger.error(f"Failed to set WASAPI loopback mode: {message}")
                    self.status_label.configure(text="[!] WASAPI loopback setup failed", text_color="#E74C3C")
                    return
                self.logger.info("System audio mode set to WASAPI loopback")
            elif sys_index == "mic_only":
                # Set mic-only mode
                success, message = self.audio_manager.set_system_audio_mode("mic_only")
                if not success:
                    self.logger.error(f"Failed to set mic-only mode: {message}")
                    self.status_label.configure(text="[!] Mic-only mode setup failed", text_color="#E74C3C")
                    return
                self.logger.info("System audio mode set to mic-only")
            else:
                # Traditional device-based system audio
                success, message = self.audio_manager.set_system_audio_device(sys_index)
                if not success:
                    self.logger.error(f"Failed to set system audio device: {message}")
                    self.status_label.configure(text="[!] System audio device setup failed", text_color="#E74C3C")
                    return
                self.logger.info(f"System audio device set to index {sys_index}")

            # Log the chosen audio path
            self.logger.info(f"System audio path = {system_audio_path}")
            
            # Show UI toast if fallback occurred
            if fallback_reason and sys_index == "mic_only":
                self.show_toast("System audio unavailable → recording mic-only.", "warning")

            # Start audio recording
            success, message = self.audio_manager.start_recording()
            if success:
                self.is_recording = True
                self.session_start_time = datetime.now()

                # Start storage session
                if self.storage_manager:
                    try:
                        session_metadata = {
                            'session_type': 'therapy',
                            'client_count': 1,  # Could be made configurable
                            'start_timestamp': self.session_start_time.isoformat(),
                            'audio_devices': {
                                'microphone': self.mic_combo.get(),
                                'system_audio': self.sys_combo.get()
                            }
                        }
                        session_id = self.storage_manager.start_session(session_metadata)
                        self.logger.info(f"Started storage session: {session_id}")
                    except Exception as e:
                        self.logger.error(f"Failed to start storage session: {e}")

                self.logger.info(f"Recording session started at {self.session_start_time}")

                # Update UI
                self.record_button.configure(
                    text="Stop Recording",
                    fg_color=("#E74C3C", "#C0392B")
                )

                # Start audio level monitoring
                self.start_audio_level_monitoring()

                # Start transcription if available
                transcription_started = False
                if self.transcription_bridge:
                    try:
                        if self.transcription_bridge.start_streaming():
                            transcription_started = True
                            self.status_label.configure(text="[REC] Recording + Transcribing", text_color="#E74C3C")
                            self.logger.info("Real-time transcription started")
                        else:
                            self.logger.warning("Failed to start transcription bridge")
                    except Exception as e:
                        self.logger.error(f"Transcription bridge start failed: {e}")
                
                if not transcription_started:
                    # Fallback to direct whisper manager
                    if self.whisper_manager:
                        try:
                            self.whisper_manager.start_processing()
                            self.status_label.configure(text="[REC] Recording + Transcribing", text_color="#E74C3C")
                            self.logger.info("Direct whisper transcription started")
                            transcription_started = True
                        except Exception as e:
                            self.logger.warning(f"Direct whisper start failed: {e}")
                
                if not transcription_started:
                    self.status_label.configure(text="[REC] Recording (no transcription)", text_color="#F39C12")
                    self.logger.info("No transcription available - recording audio only")
                    
                    # Add mock transcription for testing when no real transcription
                    self.start_mock_transcription()
            else:
                self.logger.error(f"Recording start failed: {message}")
                self.status_label.configure(text=f"[!] {message}", text_color="#E74C3C")

        except Exception as e:
            self.logger.error(f"Error starting recording: {e}")
            self.status_label.configure(text="[!] Recording error", text_color="#E74C3C")

    def stop_recording(self):
        """Stop recording session"""
        try:
            self.audio_manager.stop_recording()
            self.is_recording = False

            # Stop audio level monitoring
            self.stop_audio_level_monitoring()

            # Stop mock transcription
            if hasattr(self, 'mock_transcription_running'):
                self.mock_transcription_running = False

            # Stop transcription
            if self.transcription_bridge:
                try:
                    self.transcription_bridge.stop_streaming()
                    self.logger.info("Transcription bridge stopped")
                except Exception as e:
                    self.logger.error(f"Error stopping transcription bridge: {e}")
            
            # Stop whisper processing if available
            if self.whisper_manager:
                try:
                    self.whisper_manager.stop_processing()
                except Exception as e:
                    print(f"Whisper stop failed: {e}")

            # Save session data
            if self.storage_manager:
                try:
                    # Save full session audio
                    self.storage_manager.save_full_session_audio(self.audio_manager)
                    
                    # End storage session
                    session_info = self.storage_manager.end_session()
                    if session_info:
                        self.logger.info(f"Session saved: {session_info['session_id']}")
                        self.logger.info(f"  Segments: {session_info['stats']['total_segments']}")
                        self.logger.info(f"  Duration: {session_info['stats']['total_duration']:.1f}s")
                        
                        # Update status with session info
                        self.status_label.configure(
                            text=f"Session saved: {session_info['stats']['total_segments']} segments",
                            text_color="#2CC985"
                        )
                    else:
                        self.status_label.configure(text="Session ended", text_color="#2CC985")
                        
                except Exception as e:
                    self.logger.error(f"Error saving session: {e}")
                    self.status_label.configure(text="Session ended (save error)", text_color="#F39C12")

            # Update UI
            self.record_button.configure(
                text="Start Recording",
                fg_color=("#2CC985", "#2FA572")
            )
            self.status_label.configure(text="[*] Ready", text_color="gray")

            # Reset audio level indicators
            self.mic_level_bar.set(0)
            self.sys_level_bar.set(0)
            self.mic_level_label.configure(text="0")
            self.sys_level_label.configure(text="0")

            print("Recording stopped")

        except Exception as e:
            print(f"Error stopping recording: {e}")

    def start_audio_level_monitoring(self):
        """Start monitoring audio levels for visual feedback"""
        self.audio_level_monitoring = True

    def stop_audio_level_monitoring(self):
        """Stop monitoring audio levels"""
        self.audio_level_monitoring = False

    def export_recording(self):
        """Export the last 3 minutes of recording"""
        if not self.is_recording:
            self.status_label.configure(text="[!] No active recording to export", text_color="#E74C3C")
            return

        try:
            success, result = self.audio_manager.export_last_minutes(minutes=3)
            if success:
                # Update status with file locations
                self.status_label.configure(
                    text=f"[OK] Exported: {result['duration']:.1f}s",
                    text_color="#2CC985"
                )
                print(f"Exported files:")
                print(f"Therapist: {result['therapist_file']}")
                print(f"Client: {result['client_file']}")
            else:
                self.status_label.configure(text=f"[!] Export failed: {result}", text_color="#E74C3C")

        except Exception as e:
            print(f"Export error: {e}")
            self.status_label.configure(text="[!] Export error", text_color="#E74C3C")

    def setup_transcription_callback(self):
        """Setup callback for transcription results"""
        if self.transcription_bridge:
            try:
                self.transcription_bridge.add_transcription_callback(self.on_transcription_result)
                self.logger.info("Transcription callback setup successful")
            except Exception as e:
                self.logger.error(f"Transcription callback setup failed: {e}")
        elif self.whisper_manager:
            try:
                self.whisper_manager.add_result_callback(self.on_transcription_result)
                self.logger.info("Direct whisper callback setup successful")
            except Exception as e:
                self.logger.error(f"Whisper callback setup failed: {e}")
                self.whisper_manager = None

    def on_transcription_result(self, result):
        """Handle new transcription results"""
        # Add to current transcript
        for segment in result.segments:
            self.current_transcript.append(segment)
            
            # Save to storage if available
            if self.storage_manager and self.is_recording:
                try:
                    self.storage_manager.save_transcript_segment(segment)
                except Exception as e:
                    self.logger.error(f"Error saving transcript segment: {e}")

        # Update display (keep last 3 minutes)
        self.update_transcript_display()

    def update_transcript_display(self):
        """Update the live transcript display with enhanced formatting"""
        try:
            # Keep only last 3 minutes of transcript
            current_time = time.time()
            cutoff_time = current_time - 180  # 3 minutes

            # Filter recent segments
            recent_segments = [
                seg for seg in self.current_transcript
                if hasattr(seg, 'start_time') and seg.start_time > cutoff_time
            ]

            # Build display text with better formatting
            display_lines = []
            
            # Show last 15 segments for better context
            for segment in recent_segments[-15:]:
                try:
                    # Format timestamp
                    if hasattr(segment, 'start_time'):
                        timestamp = time.strftime("%H:%M:%S", time.localtime(segment.start_time))
                    else:
                        timestamp = "??:??:??"
                    
                    # Get speaker and text
                    speaker = getattr(segment, 'speaker', 'Unknown')
                    text = getattr(segment, 'text', '').strip()
                    
                    if not text:
                        continue
                    
                    # Format based on segment type
                    if hasattr(segment, 'is_partial') and segment.is_partial:
                        # Partial segments in italic/faded style
                        line = f"[{timestamp}] {speaker}: {text} ..."
                        display_lines.append(('partial', line))
                    else:
                        # Final segments in normal style
                        line = f"[{timestamp}] {speaker}: {text}"
                        display_lines.append(('final', line))
                        
                except Exception as e:
                    self.logger.debug(f"Error formatting segment: {e}")
                    continue
            
            # Combine all lines
            display_text = ""
            for segment_type, line in display_lines:
                display_text += line + "\n"
            
            # Add status information if no segments
            if not display_lines:
                if self.is_recording:
                    display_text = "🎤 Recording... waiting for speech\n"
                else:
                    display_text = "Press 'Start Recording' to begin transcription\n"
            
            # Update display on UI thread
            self.window.after(0, lambda: self._update_transcript_text(display_text))
            
            # Update model status periodically
            if hasattr(self, 'model_status_label'):
                self.window.after(0, lambda: self.update_model_status())
                
        except Exception as e:
            self.logger.error(f"Error updating transcript display: {e}")

    def _update_transcript_text(self, text):
        """Update transcript text box (must be called from main thread)"""
        self.transcript_display.configure(state="normal")
        self.transcript_display.delete("0.0", "end")
        self.transcript_display.insert("0.0", text)
        self.transcript_display.configure(state="disabled")
        # Scroll to bottom
        self.transcript_display.see("end")

    def analyze_themes(self):
        """Analyze emotional themes and behavioral patterns"""
        prompt = "Identify key emotional themes and behavioral patterns from the recent transcript"
        self.request_analysis(prompt, "Themes Analysis")

    def analyze_progress(self):
        """Assess therapeutic progress and breakthroughs"""
        prompt = "Assess therapeutic progress, breakthroughs, and client growth from the recent session"
        self.request_analysis(prompt, "Progress Analysis")

    def analyze_risk(self):
        """Identify safety concerns and crisis indicators"""
        prompt = "Identify safety concerns, crisis indicators, or urgent issues requiring immediate attention"
        self.request_analysis(prompt, "Risk Assessment")

    def analyze_dynamics(self):
        """Analyze relationship dynamics and communication patterns"""
        prompt = "Analyze relationship dynamics and communication patterns in the recent transcript"
        self.request_analysis(prompt, "Dynamics Analysis")

    def custom_analysis(self):
        """Show custom analysis prompt dialog"""
        dialog = CustomAnalysisDialog(self.window, self.request_analysis)

    def request_analysis(self, prompt: str, analysis_type: str):
        """Request analysis of recent transcript"""
        # Get recent transcript (last 3 minutes)
        recent_text = self.get_recent_transcript_text()

        if not recent_text.strip():
            self.status_label.configure(text="[!] No recent transcript for analysis", text_color="#E74C3C")
            return

        if self.on_insights_request:
            self.on_insights_request(recent_text, prompt, analysis_type)
        else:
            print(f"Analysis requested: {analysis_type}")
            print(f"Prompt: {prompt}")
            print(f"Transcript: {recent_text[:200]}...")

    def get_recent_transcript_text(self) -> str:
        """Get recent transcript as text"""
        current_time = time.time()
        cutoff_time = current_time - 180  # 3 minutes

        recent_segments = [
            seg for seg in self.current_transcript
            if seg.start_time > cutoff_time
        ]

        text = ""
        for segment in recent_segments:
            text += f"{segment.speaker}: {segment.text}\n"

        return text

    def get_session_notes(self) -> str:
        """Get current session notes"""
        return self.session_notes.get("0.0", "end").strip()

    def get_session_type(self) -> str:
        """Get selected session type"""
        return self.client_count.get()

    def show_insights(self):
        """Show the insights dashboard"""
        if self.on_insights_request:
            self.on_insights_request(None, None, "show_dashboard")

    def toggle_always_on_top(self):
        """Toggle always on top window setting"""
        self.always_on_top = self.always_on_top_var.get()
        self.window.attributes("-topmost", self.always_on_top)

    def show_toast(self, message, toast_type="info"):
        """Show a toast notification to the user
        
        Args:
            message: The message to display
            toast_type: Type of toast ("info", "warning", "error", "success")
        """
        try:
            # Create toast window
            toast_window = ctk.CTkToplevel(self.window)
            toast_window.title("")
            toast_window.geometry("300x80")
            toast_window.resizable(False, False)
            toast_window.transient(self.window)
            
            # Remove window decorations
            toast_window.overrideredirect(True)
            
            # Position toast in top-right corner
            screen_width = toast_window.winfo_screenwidth()
            screen_height = toast_window.winfo_screenheight()
            x = screen_width - 320  # 300px width + 20px margin
            y = 20  # Top margin
            toast_window.geometry(f"300x80+{x}+{y}")
            
            # Set appearance based on type
            if toast_type == "warning":
                bg_color = "#F39C12"
                text_color = "#FFFFFF"
            elif toast_type == "error":
                bg_color = "#E74C3C"
                text_color = "#FFFFFF"
            elif toast_type == "success":
                bg_color = "#2CC985"
                text_color = "#FFFFFF"
            else:  # info
                bg_color = "#3498DB"
                text_color = "#FFFFFF"
            
            # Create toast frame
            toast_frame = ctk.CTkFrame(
                toast_window,
                fg_color=bg_color,
                corner_radius=8
            )
            toast_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            # Add message label
            message_label = ctk.CTkLabel(
                toast_frame,
                text=message,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=text_color,
                wraplength=280
            )
            message_label.pack(expand=True, fill="both", padx=10, pady=10)
            
            # Auto-close after 3 seconds
            toast_window.after(3000, toast_window.destroy)
            
            # Bring to front
            toast_window.lift()
            toast_window.attributes("-topmost", True)
            toast_window.after(100, lambda: toast_window.attributes("-topmost", False))
            
            self.logger.debug(f"Toast shown: {message} ({toast_type})")
            
        except Exception as e:
            self.logger.error(f"Failed to show toast: {e}")
            # Fallback to status label update
            self.status_label.configure(text=f"[!] {message}", text_color="#F39C12")

    def start_ui_updates(self):
        """Start UI update thread"""
        self.ui_update_running = True
        self.ui_thread = threading.Thread(target=self._ui_update_loop)
        self.ui_thread.daemon = True
        self.ui_thread.start()

    def _ui_update_loop(self):
        """Background thread for UI updates"""
        while self.ui_update_running:
            try:
                if self.is_recording and self.session_start_time:
                    # Update timer
                    elapsed = datetime.now() - self.session_start_time
                    timer_text = str(elapsed).split('.')[0]  # Remove microseconds
                    self.window.after(0, lambda t=timer_text: self.timer_label.configure(text=t))

                    # Update audio levels
                    if hasattr(self, 'audio_level_monitoring') and self.audio_level_monitoring:
                        levels = self.audio_manager.get_volume_levels()

                        # Normalize levels to 0-1 range (assuming max level ~3000)
                        mic_normalized = min(levels['microphone'] / 3000.0, 1.0)
                        sys_normalized = min(levels['system_audio'] / 3000.0, 1.0)

                        # Update UI on main thread
                        self.window.after(0, lambda: self._update_audio_levels(
                            mic_normalized, sys_normalized, levels
                        ))

                time.sleep(0.1)  # Update more frequently for audio levels
            except Exception as e:
                print(f"UI update error: {e}")

    def _update_audio_levels(self, mic_level, sys_level, raw_levels):
        """Update audio level indicators (called from main thread)"""
        try:
            # Update progress bars
            self.mic_level_bar.set(mic_level)
            self.sys_level_bar.set(sys_level)

            # Update level text
            self.mic_level_label.configure(text=f"{int(raw_levels['microphone'])}")
            self.sys_level_label.configure(text=f"{int(raw_levels['system_audio'])}")

            # Change color based on level
            if mic_level > 0.8:
                self.mic_level_bar.configure(progress_color="#E74C3C")  # Red for too loud
            elif mic_level > 0.3:
                self.mic_level_bar.configure(progress_color="#2CC985")  # Green for good level
            else:
                self.mic_level_bar.configure(progress_color="#F39C12")  # Orange for low

            if sys_level > 0.8:
                self.sys_level_bar.configure(progress_color="#E74C3C")
            elif sys_level > 0.3:
                self.sys_level_bar.configure(progress_color="#2CC985")
            else:
                self.sys_level_bar.configure(progress_color="#F39C12")

        except Exception as e:
            print(f"Audio level update error: {e}")

    def start_mock_transcription(self):
        """Start mock transcription for testing purposes"""
        self.mock_transcription_running = True
        mock_thread = threading.Thread(target=self._mock_transcription_loop)
        mock_thread.daemon = True
        mock_thread.start()

    def _mock_transcription_loop(self):
        """Generate mock transcription data for testing"""
        mock_phrases = [
            "How are you feeling today?",
            "That's interesting, can you tell me more about that?",
            "I understand what you're saying.",
            "Let's explore that feeling further.",
            "What comes to mind when you think about that?"
        ]

        speaker_count = 0
        while self.is_recording and hasattr(self, 'mock_transcription_running'):
            try:
                import random
                time.sleep(random.randint(5, 15))  # Random intervals

                # Create mock segment
                speaker = "Therapist" if speaker_count % 2 == 0 else "Client"
                phrase = random.choice(mock_phrases)
                current_time = time.time()

                # Create mock segment object
                class MockSegment:
                    def __init__(self, text, speaker, start_time):
                        self.text = text
                        self.speaker = speaker
                        self.start_time = start_time

                mock_segment = MockSegment(phrase, speaker, current_time)
                self.current_transcript.append(mock_segment)

                # Update display
                self.update_transcript_display()

                speaker_count += 1

            except Exception as e:
                print(f"Mock transcription error: {e}")
                break

    def on_theme_changed(self, theme_name: str, theme_config: dict):
        """Callback when theme changes - update UI styling for professional appearance"""
        try:
            self.logger.debug(f"Updating main window for theme change: {theme_name}")

            # Apply professional styling to key elements
            if hasattr(self, 'window') and self.window.winfo_exists():
                self.apply_professional_styling()

        except Exception as e:
            self.logger.warning(f"Failed to update theme styling: {e}")

    def apply_professional_styling(self):
        """Apply professional styling for therapy use"""
        try:
            colors = self.theme_manager.get_theme_colors()
            if not colors:
                return

            # Apply professional button styling
            button_style = self.theme_manager.get_professional_button_style("primary")

            # Update record button with professional styling
            if hasattr(self, 'record_button'):
                try:
                    if not self.is_recording:
                        success_style = self.theme_manager.get_professional_button_style("success")
                        self.record_button.configure(**success_style)
                    else:
                        danger_style = self.theme_manager.get_professional_button_style("danger")
                        self.record_button.configure(**danger_style)
                except Exception as e:
                    pass  # Ignore styling errors

            # Apply professional styling to frames and other elements
            for attr_name in ['main_frame', 'header_frame', 'controls_frame', 'status_frame']:
                if hasattr(self, attr_name):
                    try:
                        frame = getattr(self, attr_name)
                        apply_professional_styling(frame, "frame")
                    except:
                        pass

            # Update status colors for better visibility in both themes
            self.update_status_colors()

        except Exception as e:
            self.logger.debug(f"Professional styling update failed: {e}")

    def update_status_colors(self):
        """Update status indicator colors based on theme"""
        try:
            colors = self.theme_manager.get_theme_colors()
            if not colors:
                return

            # Use theme-appropriate colors for status indicators
            if hasattr(self, 'status_label'):
                if self.is_recording:
                    self.status_label.configure(
                        text_color=colors.get("accent", "#28A745")  # Success green
                    )
                else:
                    self.status_label.configure(
                        text_color=colors.get("text_primary", "#212529")
                    )

            # Update model status colors
            if hasattr(self, 'model_status_label'):
                if self.model_status.get('loaded'):
                    self.model_status_label.configure(
                        text_color=colors.get("accent", "#28A745")
                    )
                else:
                    self.model_status_label.configure(
                        text_color=colors.get("warning", "#FFC107")
                    )

        except Exception as e:
            self.logger.debug(f"Status color update failed: {e}")

    def run(self):
        """Run the session recorder window"""
        self.window.mainloop()

    def close(self):
        """Close the window and cleanup"""
        self.ui_update_running = False
        if self.is_recording:
            self.stop_recording()

        # Unregister theme callback
        if hasattr(self, 'theme_manager'):
            self.theme_manager.unregister_theme_callback(self.on_theme_changed)

        self.window.destroy()

class CustomAnalysisDialog:
    """Dialog for custom analysis prompts"""

    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self.setup_ui()

    def setup_ui(self):
        """Setup the custom analysis dialog"""
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Custom Analysis")
        self.window.geometry("400x250")
        self.window.resizable(False, False)
        self.window.transient(self.parent)
        self.window.grab_set()

        # Center the dialog
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.window.winfo_screenheight() // 2) - (250 // 2)
        self.window.geometry(f"400x250+{x}+{y}")

        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title = ctk.CTkLabel(
            main_frame,
            text="Custom Analysis Prompt",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title.pack(pady=(10, 20))

        # Text input
        self.prompt_text = ctk.CTkTextbox(
            main_frame,
            height=100,
            font=ctk.CTkFont(size=12)
        )
        # Insert placeholder text manually since placeholder_text isn't supported
        self.prompt_text.insert("0.0", "Enter your custom analysis prompt here...")
        self.prompt_text.pack(fill="both", expand=True, pady=(0, 20))

        # Buttons
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self.cancel,
            width=80,
            fg_color=("gray70", "gray30")
        )
        cancel_btn.pack(side="left")

        analyze_btn = ctk.CTkButton(
            button_frame,
            text="Analyze",
            command=self.analyze,
            width=100,
            fg_color=("#2CC985", "#2FA572")
        )
        analyze_btn.pack(side="right")

    def analyze(self):
        """Execute the custom analysis"""
        prompt = self.prompt_text.get("0.0", "end").strip()
        if prompt:
            self.callback(prompt, "Custom Analysis")
        self.window.destroy()

    def cancel(self):
        """Cancel the dialog"""
        self.window.destroy()

def test_session_recorder():
    """Test the session recorder window"""
    from config_manager import SecureConfigManager
    from audio_manager import AudioManager
    from local_whisper_manager import LocalWhisperManager

    # Create dummy managers for testing
    config = SecureConfigManager()
    audio = AudioManager()
    whisper = None  # Would be LocalWhisperManager() if model is available

    def on_insights(transcript, prompt, analysis_type):
        print(f"Insights requested: {analysis_type}")
        if prompt:
            print(f"Prompt: {prompt}")
        if transcript:
            print(f"Transcript: {transcript[:100]}...")

    recorder = SessionRecorderWindow(config, audio, whisper, on_insights)
    recorder.run()

if __name__ == "__main__":
    test_session_recorder()