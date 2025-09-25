#!/usr/bin/env python3
"""
Amanuensis - Therapy Session Assistant Desktop App (CustomTkinter Version)

A secure desktop application for therapists to record, transcribe, and analyze
therapy sessions with AI assistance, supporting multi-speaker environments.
"""

import os
import sys
import time
import threading
from typing import Optional, Dict, List
import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk

# Import our custom modules
from config_manager import SecureConfigManager
from audio_manager import AudioManager
from speaker_manager import SpeakerManager
from api_manager import APIManager
from enhanced_whisper_manager import EnhancedWhisperManager
from whisper_model_downloader import WhisperModelManager
from settings_window import SettingsWindow

class AmanuensisApp:
    """Main Amanuensis application with CustomTkinter GUI"""

    def __init__(self):
        # Initialize managers
        self.config_manager = SecureConfigManager()
        self.audio_manager = AudioManager()
        self.speaker_manager = SpeakerManager()
        self.api_manager = APIManager(self.config_manager)
        self.whisper_manager = EnhancedWhisperManager('small')
        self.model_manager = WhisperModelManager()

        # Application state
        self.current_session_id = None
        self.recording_active = False
        self.analysis_in_progress = False

        # UI components will be created in setup_ui
        self.root = None
        self.settings_window = None

        # Set CustomTkinter appearance
        ctk.set_appearance_mode("dark")  # Professional dark theme
        ctk.set_default_color_theme("blue")

    def run(self):
        """Run the application"""
        try:
            self.create_main_window()
            self.setup_ui()
            self.load_configuration()
            self.start_ui_updates()
            self.root.mainloop()
        except Exception as e:
            print(f"Application failed to start: {e}")
            sys.exit(1)

    def create_main_window(self):
        """Create the main application window"""
        self.root = ctk.CTk()
        self.root.title("Amanuensis - Therapy Session Assistant")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)

        # Center window on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (1200 // 2)
        y = (self.root.winfo_screenheight() // 2) - (800 // 2)
        self.root.geometry(f"1200x800+{x}+{y}")

        # Handle window closing
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        """Set up the user interface"""
        # Create main header
        self.create_header()

        # Create main content area
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Create left and right panels
        content_frame = ctk.CTkFrame(main_frame)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Left panel (40% width)
        left_frame = ctk.CTkFrame(content_frame)
        left_frame.pack(side="left", fill="both", expand=False, padx=(0, 10))
        left_frame.configure(width=450)

        # Right panel (60% width)
        right_frame = ctk.CTkFrame(content_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(10, 0))

        # Setup left panel contents
        self.create_session_setup(left_frame)
        self.create_recording_controls(left_frame)

        # Setup right panel contents
        self.create_insights_panel(right_frame)

        # Create footer
        self.create_footer()

        # Create notes section at bottom
        self.create_notes_section()

    def create_header(self):
        """Create application header with title and controls"""
        header_frame = ctk.CTkFrame(self.root)
        header_frame.pack(fill="x", padx=20, pady=20)

        # Title and status
        title_frame = ctk.CTkFrame(header_frame)
        title_frame.pack(side="left", fill="both", expand=True, padx=20, pady=15)

        title_label = ctk.CTkLabel(
            title_frame,
            text="Amanuensis - Therapy Session Assistant",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(side="left")

        self.status_label = ctk.CTkLabel(
            title_frame,
            text="[*] Ready",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#2CC985"
        )
        self.status_label.pack(side="right", padx=(20, 0))

        # Control buttons
        button_frame = ctk.CTkFrame(header_frame)
        button_frame.pack(side="right", padx=20, pady=15)

        self.settings_button = ctk.CTkButton(
            button_frame,
            text="Settings",
            command=self.show_settings,
            width=100,
            height=35,
            font=ctk.CTkFont(size=14)
        )
        self.settings_button.pack(side="left", padx=5)

        help_button = ctk.CTkButton(
            button_frame,
            text="Help",
            command=self.show_help,
            width=80,
            height=35,
            font=ctk.CTkFont(size=14)
        )
        help_button.pack(side="left", padx=5)

    def create_session_setup(self, parent):
        """Create session setup section"""
        setup_frame = ctk.CTkFrame(parent)
        setup_frame.pack(fill="x", padx=20, pady=20)

        # Section title
        title_label = ctk.CTkLabel(
            setup_frame,
            text="Session Setup",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(anchor="w", padx=20, pady=(20, 10))

        # Client count selection
        client_frame = ctk.CTkFrame(setup_frame)
        client_frame.pack(fill="x", padx=20, pady=(0, 10))

        client_label = ctk.CTkLabel(
            client_frame,
            text="Number of Clients:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        client_label.pack(side="left", padx=20, pady=15)

        self.client_count_var = tk.StringVar(value="1")
        self.client_count_combo = ctk.CTkComboBox(
            client_frame,
            values=["1", "2", "3", "4", "5", "6"],
            variable=self.client_count_var,
            state="readonly",
            width=80,
            height=35,
            font=ctk.CTkFont(size=14),
            command=self.on_client_count_changed
        )
        self.client_count_combo.pack(side="right", padx=20, pady=15)

        # Audio devices section
        audio_frame = ctk.CTkFrame(setup_frame)
        audio_frame.pack(fill="x", padx=20, pady=(0, 20))

        audio_title = ctk.CTkLabel(
            audio_frame,
            text="Audio Devices",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        audio_title.pack(anchor="w", padx=20, pady=(15, 10))

        # Microphone selection
        mic_frame = ctk.CTkFrame(audio_frame)
        mic_frame.pack(fill="x", padx=20, pady=5)

        mic_label = ctk.CTkLabel(
            mic_frame,
            text="Therapist Mic:",
            font=ctk.CTkFont(size=12)
        )
        mic_label.pack(side="left", padx=15, pady=10)

        self.mic_var = tk.StringVar(value="Select Microphone...")
        self.mic_combo = ctk.CTkComboBox(
            mic_frame,
            variable=self.mic_var,
            state="readonly",
            width=250,
            height=30,
            font=ctk.CTkFont(size=11)
        )
        self.mic_combo.pack(side="right", padx=15, pady=10)

        # System audio selection
        sys_frame = ctk.CTkFrame(audio_frame)
        sys_frame.pack(fill="x", padx=20, pady=5)

        sys_label = ctk.CTkLabel(
            sys_frame,
            text="System Audio:",
            font=ctk.CTkFont(size=12)
        )
        sys_label.pack(side="left", padx=15, pady=10)

        self.sys_var = tk.StringVar(value="Select System Audio...")
        self.sys_combo = ctk.CTkComboBox(
            sys_frame,
            variable=self.sys_var,
            state="readonly",
            width=250,
            height=30,
            font=ctk.CTkFont(size=11)
        )
        self.sys_combo.pack(side="right", padx=15, pady=10)

        # Test audio button
        test_button = ctk.CTkButton(
            audio_frame,
            text="Test Audio Levels",
            command=self.test_audio_levels,
            width=200,
            height=35,
            font=ctk.CTkFont(size=14),
            fg_color=("#3B8ED0", "#1F6AA5")
        )
        test_button.pack(pady=15)

        # Load audio devices
        self.load_audio_devices()

    def create_recording_controls(self, parent):
        """Create recording control section"""
        control_frame = ctk.CTkFrame(parent)
        control_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Section title
        title_label = ctk.CTkLabel(
            control_frame,
            text="Recording Controls",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(anchor="w", padx=20, pady=(20, 10))

        # Recording status
        status_frame = ctk.CTkFrame(control_frame)
        status_frame.pack(fill="x", padx=20, pady=(0, 15))

        self.recording_status_label = ctk.CTkLabel(
            status_frame,
            text="[*] Ready to Record",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#2CC985"
        )
        self.recording_status_label.pack(side="left", padx=20, pady=15)

        self.buffer_status_label = ctk.CTkLabel(
            status_frame,
            text="Buffer: 0:00",
            font=ctk.CTkFont(size=14)
        )
        self.buffer_status_label.pack(side="right", padx=20, pady=15)

        # Volume indicators
        volume_frame = ctk.CTkFrame(control_frame)
        volume_frame.pack(fill="x", padx=20, pady=(0, 15))

        vol_title = ctk.CTkLabel(
            volume_frame,
            text="Audio Levels",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        vol_title.pack(anchor="w", padx=15, pady=(15, 5))

        # Microphone level
        mic_vol_frame = ctk.CTkFrame(volume_frame)
        mic_vol_frame.pack(fill="x", padx=15, pady=5)

        mic_vol_label = ctk.CTkLabel(
            mic_vol_frame,
            text="Mic:",
            font=ctk.CTkFont(size=12),
            width=50
        )
        mic_vol_label.pack(side="left", padx=10, pady=8)

        self.mic_progress = ctk.CTkProgressBar(
            mic_vol_frame,
            height=15,
            progress_color="#2CC985"
        )
        self.mic_progress.pack(side="left", fill="x", expand=True, padx=(5, 10), pady=8)
        self.mic_progress.set(0)

        # System audio level
        sys_vol_frame = ctk.CTkFrame(volume_frame)
        sys_vol_frame.pack(fill="x", padx=15, pady=(0, 15))

        sys_vol_label = ctk.CTkLabel(
            sys_vol_frame,
            text="System:",
            font=ctk.CTkFont(size=12),
            width=50
        )
        sys_vol_label.pack(side="left", padx=10, pady=8)

        self.sys_progress = ctk.CTkProgressBar(
            sys_vol_frame,
            height=15,
            progress_color="#3B8ED0"
        )
        self.sys_progress.pack(side="left", fill="x", expand=True, padx=(5, 10), pady=8)
        self.sys_progress.set(0)

        # Control buttons
        button_frame = ctk.CTkFrame(control_frame)
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.record_button = ctk.CTkButton(
            button_frame,
            text="Start Recording",
            command=self.toggle_recording,
            width=200,
            height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=("#2CC985", "#2FA572")
        )
        self.record_button.pack(pady=15)

        self.analyze_button = ctk.CTkButton(
            button_frame,
            text="Analyze Last 3 Minutes",
            command=self.analyze_session,
            width=200,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#FF6B35", "#E8590C"),
            state="disabled"
        )
        self.analyze_button.pack(pady=(0, 15))

    def create_insights_panel(self, parent):
        """Create AI insights display panel"""
        insights_frame = ctk.CTkFrame(parent)
        insights_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Header
        header_frame = ctk.CTkFrame(insights_frame)
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        title_label = ctk.CTkLabel(
            header_frame,
            text="AI Insights",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(side="left", padx=20, pady=15)

        # Analysis controls
        controls_frame = ctk.CTkFrame(insights_frame)
        controls_frame.pack(fill="x", padx=20, pady=(0, 10))

        export_button = ctk.CTkButton(
            controls_frame,
            text="Export Session",
            command=self.export_session,
            width=120,
            height=35,
            font=ctk.CTkFont(size=12)
        )
        export_button.pack(side="left", padx=20, pady=10)

        save_button = ctk.CTkButton(
            controls_frame,
            text="Save Session",
            command=self.save_session,
            width=120,
            height=35,
            font=ctk.CTkFont(size=12),
            fg_color=("#2CC985", "#2FA572")
        )
        save_button.pack(side="right", padx=20, pady=10)

        # Insights display
        self.insights_text = ctk.CTkTextbox(
            insights_frame,
            font=ctk.CTkFont(size=13),
            wrap="word"
        )
        self.insights_text.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Set initial text
        initial_text = """Waiting for analysis...

Click "Analyze Last 3 Minutes" to get AI insights including:

• Key emotional themes per speaker
• Communication dynamics and patterns
• Suggested follow-up questions
• Therapeutic opportunities
• Session progress notes

AI analysis will provide speaker-specific observations to enhance your therapeutic practice."""

        self.insights_text.insert("0.0", initial_text)
        self.insights_text.configure(state="disabled")

    def create_notes_section(self):
        """Create session notes section"""
        notes_frame = ctk.CTkFrame(self.root)
        notes_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Section title
        title_label = ctk.CTkLabel(
            notes_frame,
            text="Session Notes",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(anchor="w", padx=20, pady=(15, 5))

        # Notes text area
        self.notes_text = ctk.CTkTextbox(
            notes_frame,
            height=120,
            font=ctk.CTkFont(size=12)
        )
        # Set placeholder text manually
        self.notes_text.insert("0.0", "Enter session notes here...")
        self.notes_text.bind("<FocusIn>", self._clear_notes_placeholder)
        self.notes_placeholder_active = True
        self.notes_text.pack(fill="x", padx=20, pady=(0, 20))

    def create_footer(self):
        """Create application footer"""
        footer_frame = ctk.CTkFrame(self.root)
        footer_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.connection_status_label = ctk.CTkLabel(
            footer_frame,
            text="API: Disconnected",
            font=ctk.CTkFont(size=12),
            text_color="#FA5252"
        )
        self.connection_status_label.pack(side="left", padx=20, pady=10)

        version_label = ctk.CTkLabel(
            footer_frame,
            text="Amanuensis v2.0 - CustomTkinter",
            font=ctk.CTkFont(size=11)
        )
        version_label.pack(side="right", padx=20, pady=10)

    def _clear_notes_placeholder(self, event):
        """Clear placeholder text when notes field is focused"""
        if self.notes_placeholder_active:
            self.notes_text.delete("0.0", "end")
            self.notes_placeholder_active = False

    def load_configuration(self):
        """Load application configuration"""
        try:
            config = self.config_manager.load_config()
            if config:
                print("Configuration loaded successfully")

                # Initialize API clients
                success, message = self.api_manager.initialize_clients()
                if success:
                    print("API clients initialized")
                    self.connection_status_label.configure(
                        text="API: Connected",
                        text_color="#2CC985"
                    )
                else:
                    print(f"API initialization warning: {message}")
                    self.connection_status_label.configure(
                        text="API: Partial Connection",
                        text_color="#FFD43B"
                    )
            else:
                print("No existing configuration found")
                self.show_initial_setup()

        except Exception as e:
            print(f"Configuration loading failed: {e}")
            messagebox.showerror("Configuration Error", str(e))

    def show_initial_setup(self):
        """Show initial setup dialog"""
        self.show_settings(setup_mode=True)

    def show_settings(self, setup_mode=False):
        """Show settings window"""
        if not self.settings_window:
            self.settings_window = SettingsWindow(
                parent=self.root,
                config_manager=self.config_manager,
                api_manager=self.api_manager,
                audio_manager=self.audio_manager,
                whisper_manager=self.whisper_manager,
                model_manager=self.model_manager,
                setup_mode=setup_mode
            )
        else:
            self.settings_window.window.lift()
            self.settings_window.window.focus()

    def show_help(self):
        """Show help information"""
        help_text = """Amanuensis - Therapy Session Assistant

Quick Start:
1. Configure API keys in Settings
2. Select audio devices
3. Choose number of clients
4. Start recording
5. Click 'Analyze' for AI insights

Support:
• Review SETUP_INSTRUCTIONS.md for detailed setup
• Check audio device configuration for Zoom
• Ensure API keys are properly configured

Security:
• All data stored locally
• API keys encrypted
• No cloud synchronization"""

        messagebox.showinfo("Help - Amanuensis", help_text)

    def load_audio_devices(self):
        """Load available audio devices with proper filtering"""
        try:
            # Get properly filtered input devices for microphones
            input_devices = self.audio_manager.get_input_devices()
            mic_device_list = [f"{d['index']}: {d['name']} ({d['channels']} ch)" for d in input_devices]

            # Get system audio devices (with fallbacks and validation)
            system_devices = self.audio_manager.get_system_audio_devices()
            sys_device_list = [f"{d['index']}: {d['name']} ({d['channels']} ch)" for d in system_devices if d['index'] != -1]

            # Add placeholder devices for empty lists
            if not mic_device_list:
                mic_device_list = ["No input devices found"]
            if not sys_device_list:
                sys_device_list = ["No system audio devices found - Enable Stereo Mix"]

            # Configure combo boxes with filtered devices
            self.mic_combo.configure(values=mic_device_list)
            self.sys_combo.configure(values=sys_device_list)

            # Set default selections
            if mic_device_list and not mic_device_list[0].startswith("No"):
                self.mic_combo.set(mic_device_list[0])
            else:
                self.mic_combo.set("Select Microphone...")

            if sys_device_list and not sys_device_list[0].startswith("No"):
                self.sys_combo.set(sys_device_list[0])
            else:
                self.sys_combo.set("Select System Audio...")

            # Log device loading results
            print(f"Loaded {len(mic_device_list)} microphone devices, {len(sys_device_list)} system audio devices")

        except Exception as e:
            print(f"Error loading audio devices: {e}")
            messagebox.showerror("Audio Device Error", f"Failed to load audio devices: {e}")
            # Set fallback values
            self.mic_combo.configure(values=["Error loading devices"])
            self.sys_combo.configure(values=["Error loading devices"])
            self.mic_combo.set("Select Microphone...")
            self.sys_combo.set("Select System Audio...")

    def on_client_count_changed(self, value):
        """Handle client count change"""
        try:
            count = int(value)
            print(f"Client count changed to: {count}")
        except ValueError:
            print(f"Invalid client count: {value}")

    def test_audio_levels(self):
        """Test audio levels for selected devices with validation"""
        try:
            # Validate selections
            mic_selection = self.mic_var.get()
            sys_selection = self.sys_var.get()

            if (mic_selection.startswith("Select") or mic_selection.startswith("No") or
                sys_selection.startswith("Select") or sys_selection.startswith("No")):
                messagebox.showerror("Selection Required", "Please select valid audio devices first.")
                return

            # Extract device indices with validation
            try:
                mic_index = int(mic_selection.split(':')[0])
                sys_index = int(sys_selection.split(':')[0])
            except (ValueError, IndexError):
                messagebox.showerror("Invalid Selection", "Selected devices are invalid. Please choose valid devices.")
                return

            # Validate channel counts before testing
            mic_channels = 0
            sys_channels = 0
            try:
                # Extract channel info from selection text (format: "index: name (X ch)")
                mic_channels = int(mic_selection.split('(')[1].split(' ch')[0])
                sys_channels = int(sys_selection.split('(')[1].split(' ch')[0])
            except (ValueError, IndexError):
                print("Warning: Could not parse channel information from selection")

            if mic_channels == 0:
                messagebox.showerror("Invalid Microphone", f"Selected microphone has 0 input channels and cannot be used for recording.")
                return

            if sys_channels == 0:
                messagebox.showerror("Invalid System Audio", f"Selected system audio device has 0 input channels and cannot be used for recording.")
                return

            # Set devices with validation
            mic_success, mic_msg = self.audio_manager.set_input_device(mic_index)
            if not mic_success:
                messagebox.showerror("Microphone Error", f"Failed to set microphone: {mic_msg}")
                return

            sys_success, sys_msg = self.audio_manager.set_system_audio_device(sys_index)
            if not sys_success:
                messagebox.showerror("System Audio Error", f"Failed to set system audio: {sys_msg}")
                return

            # Test audio with validated devices
            success, message = self.audio_manager.test_audio_levels()
            if success:
                messagebox.showinfo("Audio Test", "Audio test completed successfully. Check console for audio levels.")
            else:
                messagebox.showerror("Audio Test Failed", f"Audio test failed: {message}")

        except Exception as e:
            messagebox.showerror("Audio Test Error", f"Unexpected error during audio test: {str(e)}")

    def toggle_recording(self):
        """Toggle recording on/off"""
        if not self.recording_active:
            # Start recording
            if self.mic_var.get().startswith("Select") or self.sys_var.get().startswith("Select"):
                messagebox.showerror("Device Selection Required", "Please select audio devices first.")
                return

            success, message = self.audio_manager.start_recording()
            if success:
                self.recording_active = True
                self.record_button.configure(
                    text="Stop Recording",
                    fg_color=("#FA5252", "#E03131")
                )
                self.recording_status_label.configure(
                    text="[REC] Recording",
                    text_color="#FA5252"
                )
                self.status_label.configure(
                    text="[REC] Recording",
                    text_color="#FA5252"
                )
                self.analyze_button.configure(state="normal")

                # Create new session
                client_count = int(self.client_count_var.get())
                self.current_session_id = self.speaker_manager.create_session(client_count)
                self.speaker_manager.setup_session_speakers(self.current_session_id, client_count)

                print(f"Recording started - Session ID: {self.current_session_id}")
            else:
                messagebox.showerror("Recording Error", message)
        else:
            # Stop recording - let audio thread handle cleanup
            print("Requesting recording stop...")
            self.audio_manager.stop_recording()

            # Don't immediately update GUI state - let thread status updates handle it
            # This prevents GUI corruption from premature state changes
            self.record_button.configure(text="Stopping...", state="disabled")
            self.status_label.configure(text="Stopping recording...", text_color="#FFA500")

            # Re-enable button after a delay (thread status will update GUI properly)
            self.root.after(2000, lambda: self.record_button.configure(state="normal"))
            print("Recording stopped")

    def analyze_session(self):
        """Analyze the last 3 minutes of audio"""
        if self.analysis_in_progress:
            return

        self.analysis_in_progress = True
        self.analyze_button.configure(
            text="Analyzing...",
            state="disabled"
        )

        # Update insights display
        self.insights_text.configure(state="normal")
        self.insights_text.delete("0.0", "end")
        self.insights_text.insert("0.0", "Analyzing session...\n\nPlease wait while we:\n• Export audio segments\n• Transcribe with speaker identification\n• Generate therapeutic insights\n\nThis may take 30-60 seconds...")
        self.insights_text.configure(state="disabled")

        # Run analysis in background thread
        analysis_thread = threading.Thread(target=self._analyze_audio_background)
        analysis_thread.daemon = True
        analysis_thread.start()

    def _analyze_audio_background(self):
        """Background thread for audio analysis"""
        try:
            # Export audio files
            success, result = self.audio_manager.export_last_minutes(minutes=3)
            if not success:
                self.root.after(0, lambda: self._analysis_complete(False, result))
                return

            # Transcribe audio
            success, transcripts = self.api_manager.transcribe_audio_files(
                result['therapist_file'],
                result['client_file']
            )

            if not success:
                error_msg = transcripts.get('error', 'Transcription failed') if isinstance(transcripts, dict) else 'Transcription failed'
                self.root.after(0, lambda: self._analysis_complete(False, error_msg))
                return

            # Merge transcripts
            segments = self.api_manager.merge_and_sort_transcripts(transcripts)
            formatted_transcript = self.api_manager.format_transcript_for_analysis(segments)

            # Store transcript segments
            for segment in segments:
                self.speaker_manager.add_transcript_segment(
                    self.current_session_id,
                    segment['text'],
                    segment['speaker'],
                    segment['start']
                )

            # Analyze with Claude
            session_context = {
                'client_count': int(self.client_count_var.get()),
                'session_type': 'individual' if int(self.client_count_var.get()) == 1 else 'multi-client'
            }

            success, analysis = self.api_manager.analyze_therapy_session(formatted_transcript, session_context)

            if success:
                self.root.after(0, lambda: self._analysis_complete(True, analysis))
            else:
                error_msg = analysis.get('error', 'Analysis failed') if isinstance(analysis, dict) else 'Analysis failed'
                self.root.after(0, lambda: self._analysis_complete(False, error_msg))

        except Exception as e:
            self.root.after(0, lambda: self._analysis_complete(False, str(e)))

    def _analysis_complete(self, success, result):
        """Handle analysis completion (called from main thread)"""
        self.analysis_in_progress = False
        self.analyze_button.configure(
            text="Analyze Last 3 Minutes",
            state="normal"
        )

        if success:
            # Format analysis for display
            display_text = self._format_analysis_display(result)
            self.insights_text.configure(state="normal")
            self.insights_text.delete("0.0", "end")
            self.insights_text.insert("0.0", display_text)
            self.insights_text.configure(state="disabled")
        else:
            messagebox.showerror("Analysis Error", result)
            self.insights_text.configure(state="normal")
            self.insights_text.delete("0.0", "end")
            self.insights_text.insert("0.0", f"Analysis failed: {result}\n\nPlease check your API configuration and try again.")
            self.insights_text.configure(state="disabled")

    def _format_analysis_display(self, analysis):
        """Format analysis results for UI display"""
        formatted = "AI ANALYSIS RESULTS\n" + "="*50 + "\n\n"

        if 'themes' in analysis and analysis['themes']:
            formatted += "KEY THEMES PER SPEAKER:\n"
            formatted += "-" * 25 + "\n"
            formatted += analysis['themes'] + "\n\n"

        if 'dynamics' in analysis and analysis['dynamics']:
            formatted += "RELATIONSHIP DYNAMICS:\n"
            formatted += "-" * 25 + "\n"
            formatted += analysis['dynamics'] + "\n\n"

        if 'follow_up_questions' in analysis and analysis['follow_up_questions']:
            formatted += "FOLLOW-UP QUESTIONS:\n"
            formatted += "-" * 25 + "\n"
            formatted += analysis['follow_up_questions'] + "\n\n"

        if 'opportunities' in analysis and analysis['opportunities']:
            formatted += "THERAPEUTIC OPPORTUNITIES:\n"
            formatted += "-" * 25 + "\n"
            formatted += analysis['opportunities'] + "\n\n"

        if 'session_notes' in analysis and analysis['session_notes']:
            formatted += "SESSION NOTES:\n"
            formatted += "-" * 25 + "\n"
            formatted += analysis['session_notes']

        return formatted

    def save_session(self):
        """Save current session"""
        if self.current_session_id:
            notes = self.notes_text.get("0.0", "end-1c")
            # Don't save placeholder text
            if self.notes_placeholder_active or notes.strip() == "Enter session notes here...":
                notes = ""
            self.speaker_manager.end_session(self.current_session_id, notes)
            messagebox.showinfo("Session Saved", "Session has been saved successfully.")
        else:
            messagebox.showwarning("No Session", "No active session to save.")

    def export_session(self):
        """Export session data"""
        if self.current_session_id:
            try:
                transcript = self.speaker_manager.format_transcript_for_analysis(self.current_session_id)
                if transcript:
                    # Simple text export for now
                    filename = f"session_{self.current_session_id}_{int(time.time())}.txt"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(f"Amanuensis Session Export\n")
                        f.write(f"Session ID: {self.current_session_id}\n")
                        f.write(f"Export Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                        f.write("TRANSCRIPT:\n")
                        f.write("=" * 50 + "\n")
                        f.write(transcript)
                        f.write("\n\n")
                        f.write("SESSION NOTES:\n")
                        f.write("=" * 50 + "\n")
                        notes = self.notes_text.get("0.0", "end-1c")
                        # Don't export placeholder text
                        if self.notes_placeholder_active or notes.strip() == "Enter session notes here...":
                            notes = "No notes entered."
                        f.write(notes)
                    messagebox.showinfo("Export Complete", f"Session exported to {filename}")
                else:
                    messagebox.showwarning("No Data", "No transcript data to export.")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export session: {e}")
        else:
            messagebox.showwarning("No Session", "No active session to export.")

    def start_ui_updates(self):
        """Start periodic UI updates using thread-safe communication"""
        self.update_ui()
        self.root.after(200, self.start_ui_updates)  # Update more frequently (200ms)

    def update_ui(self):
        """Update UI elements periodically using thread-safe data"""
        try:
            # Process any status updates from audio thread
            self._process_audio_status_updates()

            if self.recording_active:
                # Get thread-safe volume levels
                levels = self.audio_manager.get_volume_levels()

                # Update volume bars (normalize to 0-1 range)
                mic_level = min(levels['microphone'] / 1000.0, 1.0)
                sys_level = min(levels['system_audio'] / 1000.0, 1.0)

                self.mic_progress.set(mic_level)
                self.sys_progress.set(sys_level)

                # Update buffer status
                duration = levels['buffer_duration']
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                self.buffer_status_label.configure(text=f"Buffer: {minutes}:{seconds:02d}")

        except Exception as e:
            print(f"UI update error: {e}")
            # Don't update GUI elements if there's an error to prevent corruption
            if hasattr(self, 'buffer_status_label'):
                try:
                    self.buffer_status_label.configure(text="Buffer: Error")
                except:
                    pass  # Prevent cascade failures

    def _process_audio_status_updates(self):
        """Process status updates from audio thread (runs in main GUI thread)"""
        try:
            updates = self.audio_manager.get_status_updates()
            for update in updates:
                self._handle_audio_status_update(update)
        except Exception as e:
            print(f"Error processing audio status updates: {e}")

    def _handle_audio_status_update(self, update):
        """Handle a single status update from audio thread"""
        try:
            update_type = update.get('type')

            if update_type == 'thread_status':
                status = update.get('status')
                message = update.get('message', '')
                print(f"Audio thread status: {status} - {message}")

                if status == 'stopped':
                    # Audio thread has fully stopped, safe to update GUI
                    self._handle_recording_stopped_safely()

            elif update_type == 'error':
                error_msg = update.get('message', 'Unknown audio error')
                error_code = update.get('error_code', 'unknown')
                print(f"Audio thread error [{error_code}]: {error_msg}")

                # Handle error in GUI
                self._handle_audio_error(error_msg, error_code)

            elif update_type == 'levels':
                # Level updates are handled in update_ui() method
                pass

        except Exception as e:
            print(f"Error handling audio status update: {e}")

    def _handle_recording_stopped_safely(self):
        """Handle recording stopped notification safely in GUI thread"""
        try:
            if self.recording_active:
                self.recording_active = False
                self.record_button.configure(
                    text="Start Recording",
                    fg_color=("#2CC985", "#2FA572")
                )
                self.recording_status_label.configure(
                    text="[*] Ready to Record",
                    text_color="#2CC985"
                )
                self.status_label.configure(text="Recording stopped successfully")
        except Exception as e:
            print(f"Error updating GUI after recording stop: {e}")

    def _handle_audio_error(self, error_msg, error_code):
        """Handle audio error safely in GUI thread"""
        try:
            # Update GUI to reflect error state
            if self.recording_active:
                self.recording_active = False
                self.record_button.configure(
                    text="Start Recording",
                    fg_color=("#2CC985", "#2FA572")
                )
                self.recording_status_label.configure(
                    text="[!] Recording Error",
                    text_color="#FA5252"
                )
            self.status_label.configure(text=f"Error: {error_msg}")
        except Exception as e:
            print(f"Error updating GUI for audio error: {e}")

    def on_closing(self):
        """Handle application closing"""
        try:
            print("Shutting down Amanuensis...")

            if self.recording_active:
                self.audio_manager.stop_recording()

            if self.current_session_id:
                notes = self.notes_text.get("0.0", "end-1c")
                # Don't save placeholder text
                if self.notes_placeholder_active or notes.strip() == "Enter session notes here...":
                    notes = ""
                self.speaker_manager.end_session(self.current_session_id, notes)

            # Close settings window if open
            if self.settings_window and self.settings_window.window:
                self.settings_window.close_window()

            self.audio_manager.cleanup()
            self.api_manager.cleanup()
            self.config_manager.clear_memory()

            print("Cleanup completed")

        except Exception as e:
            print(f"Cleanup error: {e}")
        finally:
            self.root.destroy()

if __name__ == '__main__':
    try:
        app = AmanuensisApp()
        app.run()
    except Exception as e:
        print(f"Application failed to start: {e}")
        messagebox.showerror("Startup Error", f"Application failed to start: {e}")
        sys.exit(1)