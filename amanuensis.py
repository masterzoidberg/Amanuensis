#!/usr/bin/env python3
"""
Amanuensis - Therapy Session Assistant Desktop App

A secure desktop application for therapists to record, transcribe, and analyze
therapy sessions with AI assistance, supporting multi-speaker environments.
"""

import os
import sys
import time
import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle

# Import our custom modules
from config_manager import SecureConfigManager
from audio_manager import AudioManager
from speaker_manager import SpeakerManager
from api_manager import APIManager

class AmanuensisApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "Amanuensis - Therapy Session Assistant"

        # Initialize managers
        self.config_manager = SecureConfigManager()
        self.audio_manager = AudioManager()
        self.speaker_manager = SpeakerManager()
        self.api_manager = APIManager(self.config_manager)

        # Application state
        self.current_session_id = None
        self.recording_active = False
        self.analysis_in_progress = False
        self.current_popup = None

        # UI components
        self.status_label = None
        self.record_button = None
        self.analyze_button = None
        self.client_count_spinner = None
        self.notes_input = None
        self.insights_display = None
        self.volume_bars = {}

        # Bind keyboard events for ESC handling
        Window.bind(on_key_down=self._on_key_down)

    def build(self):
        """Build the main UI"""
        try:
            # Load configuration
            self.load_configuration()

            # Create main layout
            main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

            # Add header
            header = self.create_header()
            main_layout.add_widget(header)

            # Add main content area
            content_layout = BoxLayout(orientation='horizontal', spacing=10)

            # Left panel - Session controls
            left_panel = self.create_left_panel()
            content_layout.add_widget(left_panel)

            # Right panel - Analysis and insights
            right_panel = self.create_right_panel()
            content_layout.add_widget(right_panel)

            main_layout.add_widget(content_layout)

            # Add footer
            footer = self.create_footer()
            main_layout.add_widget(footer)

            # Start UI updates
            Clock.schedule_interval(self.update_ui, 0.5)

            return main_layout

        except Exception as e:
            Logger.error(f"Failed to build UI: {e}")
            return Label(text=f"Application Error: {e}")

    def create_header(self):
        """Create the application header"""
        header_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)

        # App title
        title_label = Label(
            text="Amanuensis - Therapy Session Assistant",
            font_size='18sp',
            bold=True,
            size_hint_x=0.7
        )
        header_layout.add_widget(title_label)

        # Status indicator
        self.status_label = Label(
            text="● Ready",
            color=(0, 1, 0, 1),  # Green
            size_hint_x=0.3,
            halign='right'
        )
        header_layout.add_widget(self.status_label)

        return header_layout

    def create_left_panel(self):
        """Create the left control panel"""
        left_layout = BoxLayout(orientation='vertical', size_hint_x=0.5, spacing=10)

        # Session setup section
        session_box = BoxLayout(orientation='vertical', size_hint_y=None, height=200, spacing=5)
        session_box.add_widget(Label(text="Session Setup", font_size='16sp', bold=True, size_hint_y=None, height=30))

        # Client count selector
        client_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=40)
        client_layout.add_widget(Label(text="Number of Clients:", size_hint_x=0.6))

        self.client_count_spinner = Spinner(
            text='1',
            values=[str(i) for i in range(1, 7)],
            size_hint_x=0.4,
            size_hint_y=None,
            height=40
        )
        self.client_count_spinner.bind(text=self.on_client_count_changed)
        client_layout.add_widget(self.client_count_spinner)
        session_box.add_widget(client_layout)

        # Audio device selection
        device_button = Button(
            text="Select Audio Devices",
            size_hint_y=None,
            height=40
        )
        device_button.bind(on_press=self.show_device_selection)
        session_box.add_widget(device_button)

        # Volume level indicators
        volume_layout = self.create_volume_indicators()
        session_box.add_widget(volume_layout)

        left_layout.add_widget(session_box)

        # Recording controls
        controls_box = BoxLayout(orientation='vertical', spacing=10)
        controls_box.add_widget(Label(text="Recording Controls", font_size='16sp', bold=True, size_hint_y=None, height=30))

        # Start/Stop recording button
        self.record_button = Button(
            text="Start Recording",
            size_hint_y=None,
            height=50,
            background_color=(0, 0.7, 0, 1)  # Green
        )
        self.record_button.bind(on_press=self.toggle_recording)
        controls_box.add_widget(self.record_button)

        # Analyze button
        self.analyze_button = Button(
            text="Analyze Last 3 Minutes",
            size_hint_y=None,
            height=50,
            background_color=(0, 0.5, 1, 1),  # Blue
            disabled=True
        )
        self.analyze_button.bind(on_press=self.analyze_session)
        controls_box.add_widget(self.analyze_button)

        left_layout.add_widget(controls_box)

        # Notes section
        notes_box = BoxLayout(orientation='vertical')
        notes_box.add_widget(Label(text="Session Notes", font_size='16sp', bold=True, size_hint_y=None, height=30))

        self.notes_input = TextInput(
            text="",
            multiline=True,
            hint_text="Enter session notes here..."
        )
        notes_box.add_widget(self.notes_input)

        left_layout.add_widget(notes_box)

        return left_layout

    def create_right_panel(self):
        """Create the right analysis panel"""
        right_layout = BoxLayout(orientation='vertical', size_hint_x=0.5)

        # Insights header
        insights_header = BoxLayout(orientation='horizontal', size_hint_y=None, height=40)
        insights_header.add_widget(Label(text="AI Insights", font_size='16sp', bold=True))

        # Settings button
        settings_btn = Button(
            text="Settings",
            size_hint=(None, None),
            size=(80, 30)
        )
        settings_btn.bind(on_press=self.show_settings)
        insights_header.add_widget(settings_btn)

        right_layout.add_widget(insights_header)

        # Insights display area
        scroll = ScrollView()
        self.insights_display = Label(
            text="Waiting for analysis...\n\nClick 'Analyze Last 3 Minutes' to get AI insights.",
            text_size=(None, None),
            halign='left',
            valign='top',
            markup=True
        )
        scroll.add_widget(self.insights_display)
        right_layout.add_widget(scroll)

        return right_layout

    def create_volume_indicators(self):
        """Create volume level indicators"""
        volume_layout = BoxLayout(orientation='vertical', size_hint_y=None, height=80)

        # Microphone level
        mic_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=30)
        mic_layout.add_widget(Label(text="Mic:", size_hint_x=0.2))

        mic_bar = ProgressBar(max=1000, size_hint_x=0.8)
        self.volume_bars['microphone'] = mic_bar
        mic_layout.add_widget(mic_bar)
        volume_layout.add_widget(mic_layout)

        # System audio level
        sys_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=30)
        sys_layout.add_widget(Label(text="System:", size_hint_x=0.2))

        sys_bar = ProgressBar(max=1000, size_hint_x=0.8)
        self.volume_bars['system'] = sys_bar
        sys_layout.add_widget(sys_bar)
        volume_layout.add_widget(sys_layout)

        return volume_layout

    def create_footer(self):
        """Create the application footer"""
        footer_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=30)

        # Connection status
        self.connection_status = Label(
            text="API: Disconnected",
            color=(1, 0.5, 0, 1),  # Orange
            size_hint_x=0.5
        )
        footer_layout.add_widget(self.connection_status)

        # Buffer duration
        self.buffer_status = Label(
            text="Buffer: 0:00",
            size_hint_x=0.5,
            halign='right'
        )
        footer_layout.add_widget(self.buffer_status)

        return footer_layout

    def load_configuration(self):
        """Load application configuration"""
        try:
            config = self.config_manager.load_config()
            if config:
                Logger.info("Configuration loaded successfully")

                # Initialize API clients
                success, message = self.api_manager.initialize_clients()
                if success:
                    Logger.info("API clients initialized")
                else:
                    Logger.warning(f"API initialization warning: {message}")
            else:
                Logger.info("No existing configuration found")
                self.show_initial_setup()

        except Exception as e:
            Logger.error(f"Configuration loading failed: {e}")
            self.show_error_popup("Configuration Error", str(e))

    def show_initial_setup(self):
        """Show initial setup dialog"""
        self.show_settings(setup_mode=True)

    def show_settings(self, instance=None, setup_mode=False):
        """Show settings/configuration popup"""
        # Create modal view for better control
        modal = ModalView(
            size_hint=(0.8, 0.8),
            auto_dismiss=True,
            background_color=(0, 0, 0, 0.7)  # Semi-transparent background
        )

        # Main container with background
        main_container = BoxLayout(orientation='vertical', padding=20, spacing=10)

        # Add background color
        with main_container.canvas.before:
            Color(0.9, 0.9, 0.9, 1)  # Light gray background
            self.bg_rect = Rectangle()

        def update_bg(*args):
            self.bg_rect.pos = main_container.pos
            self.bg_rect.size = main_container.size

        main_container.bind(pos=update_bg, size=update_bg)

        # Title header
        header_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)
        title_label = Label(
            text="Settings - API Configuration",
            font_size='18sp',
            bold=True,
            color=(0.2, 0.2, 0.2, 1),
            size_hint_x=0.8
        )
        header_layout.add_widget(title_label)

        # Close button (X)
        close_btn = Button(
            text="✕",
            size_hint=(None, None),
            size=(40, 40),
            font_size='18sp',
            background_color=(0.8, 0.2, 0.2, 1)
        )
        close_btn.bind(on_press=lambda x: self._dismiss_modal(modal))
        header_layout.add_widget(close_btn)

        main_container.add_widget(header_layout)

        # Content area with scroll
        scroll = ScrollView()
        content_layout = BoxLayout(orientation='vertical', spacing=15, size_hint_y=None)
        content_layout.bind(minimum_height=content_layout.setter('height'))

        if setup_mode:
            welcome_label = Label(
                text="Welcome to Amanuensis!\nPlease configure your API keys to continue.",
                size_hint_y=None,
                height=80,
                color=(0.2, 0.2, 0.2, 1),
                font_size='14sp'
            )
            content_layout.add_widget(welcome_label)

        # OpenAI API Key section
        openai_label = Label(
            text="OpenAI API Key:",
            size_hint_y=None,
            height=35,
            color=(0.2, 0.2, 0.2, 1),
            font_size='14sp',
            bold=True
        )
        content_layout.add_widget(openai_label)

        openai_input = TextInput(
            password=True,
            multiline=False,
            size_hint_y=None,
            height=45,
            hint_text="sk-...",
            background_color=(1, 1, 1, 1),
            foreground_color=(0, 0, 0, 1)
        )
        content_layout.add_widget(openai_input)

        # Anthropic API Key section
        anthropic_label = Label(
            text="Anthropic API Key:",
            size_hint_y=None,
            height=35,
            color=(0.2, 0.2, 0.2, 1),
            font_size='14sp',
            bold=True
        )
        content_layout.add_widget(anthropic_label)

        anthropic_input = TextInput(
            password=True,
            multiline=False,
            size_hint_y=None,
            height=45,
            hint_text="sk-ant-...",
            background_color=(1, 1, 1, 1),
            foreground_color=(0, 0, 0, 1)
        )
        content_layout.add_widget(anthropic_input)

        scroll.add_widget(content_layout)
        main_container.add_widget(scroll)

        # Button layout
        button_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=60,
            spacing=15,
            padding=[0, 10, 0, 0]
        )

        save_btn = Button(
            text="Save & Test",
            background_color=(0.2, 0.7, 0.2, 1),
            font_size='14sp'
        )

        cancel_btn = Button(
            text="Cancel",
            background_color=(0.6, 0.6, 0.6, 1),
            font_size='14sp'
        )

        button_layout.add_widget(save_btn)
        if not setup_mode:
            button_layout.add_widget(cancel_btn)
        else:
            # Add spacer for better centering in setup mode
            button_layout.add_widget(Widget())

        main_container.add_widget(button_layout)
        modal.add_widget(main_container)

        def save_settings(instance):
            try:
                # Set up encryption if needed
                if not hasattr(self.config_manager, 'key') or not self.config_manager.key:
                    self.config_manager.setup_encryption()

                # Save API keys
                if openai_input.text.strip():
                    self.config_manager.set_api_key('openai', openai_input.text.strip())
                if anthropic_input.text.strip():
                    self.config_manager.set_api_key('anthropic', anthropic_input.text.strip())

                # Test connections
                success, message = self.api_manager.initialize_clients()
                if success:
                    self.show_info_popup("Success", "API keys saved and tested successfully!")
                    self._dismiss_modal(modal)
                else:
                    self.show_error_popup("API Test Failed", message)

            except Exception as e:
                self.show_error_popup("Configuration Error", str(e))

        def cancel_settings(instance):
            self._dismiss_modal(modal)

        save_btn.bind(on_press=save_settings)
        cancel_btn.bind(on_press=cancel_settings)

        # Store reference to current modal
        self.current_popup = modal
        modal.open()

    def show_device_selection(self, instance):
        """Show audio device selection popup"""
        devices = self.audio_manager.get_audio_devices()

        # Create modal view
        modal = ModalView(
            size_hint=(0.8, 0.85),
            auto_dismiss=True,
            background_color=(0, 0, 0, 0.7)
        )

        # Main container
        main_container = BoxLayout(orientation='vertical', padding=20, spacing=10)

        # Add background
        with main_container.canvas.before:
            Color(0.9, 0.9, 0.9, 1)
            self.device_bg_rect = Rectangle()

        def update_device_bg(*args):
            self.device_bg_rect.pos = main_container.pos
            self.device_bg_rect.size = main_container.size

        main_container.bind(pos=update_device_bg, size=update_device_bg)

        # Header with close button
        header_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)
        title_label = Label(
            text="Audio Device Configuration",
            font_size='18sp',
            bold=True,
            color=(0.2, 0.2, 0.2, 1),
            size_hint_x=0.8
        )
        header_layout.add_widget(title_label)

        close_btn = Button(
            text="✕",
            size_hint=(None, None),
            size=(40, 40),
            font_size='18sp',
            background_color=(0.8, 0.2, 0.2, 1)
        )
        close_btn.bind(on_press=lambda x: self._dismiss_modal(modal))
        header_layout.add_widget(close_btn)

        main_container.add_widget(header_layout)

        # Content with scroll
        scroll = ScrollView()
        content_layout = BoxLayout(orientation='vertical', spacing=15, size_hint_y=None)
        content_layout.bind(minimum_height=content_layout.setter('height'))

        # Microphone selection
        mic_label = Label(
            text="Therapist Microphone:",
            size_hint_y=None,
            height=35,
            color=(0.2, 0.2, 0.2, 1),
            font_size='14sp',
            bold=True
        )
        content_layout.add_widget(mic_label)

        mic_spinner = Spinner(
            text="Select Microphone...",
            values=[f"{d['index']}: {d['name']}" for d in devices],
            size_hint_y=None,
            height=45,
            background_color=(1, 1, 1, 1)
        )
        content_layout.add_widget(mic_spinner)

        # System audio selection
        sys_label = Label(
            text="System Audio (Stereo Mix):",
            size_hint_y=None,
            height=35,
            color=(0.2, 0.2, 0.2, 1),
            font_size='14sp',
            bold=True
        )
        content_layout.add_widget(sys_label)

        sys_spinner = Spinner(
            text="Select System Audio...",
            values=[f"{d['index']}: {d['name']}" for d in devices],
            size_hint_y=None,
            height=45,
            background_color=(1, 1, 1, 1)
        )
        content_layout.add_widget(sys_spinner)

        # Test button
        test_btn = Button(
            text="Test Audio Levels",
            size_hint_y=None,
            height=45,
            background_color=(0.2, 0.5, 0.8, 1)
        )
        content_layout.add_widget(test_btn)

        scroll.add_widget(content_layout)
        main_container.add_widget(scroll)

        # Button layout
        button_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=60,
            spacing=15,
            padding=[0, 10, 0, 0]
        )

        save_btn = Button(
            text="Save Configuration",
            background_color=(0.2, 0.7, 0.2, 1),
            font_size='14sp'
        )

        cancel_btn = Button(
            text="Cancel",
            background_color=(0.6, 0.6, 0.6, 1),
            font_size='14sp'
        )

        button_layout.add_widget(save_btn)
        button_layout.add_widget(cancel_btn)
        main_container.add_widget(button_layout)
        modal.add_widget(main_container)

        def test_audio(instance):
            try:
                if mic_spinner.text.startswith("Select") or sys_spinner.text.startswith("Select"):
                    self.show_error_popup("Selection Required", "Please select both audio devices first.")
                    return

                mic_index = int(mic_spinner.text.split(':')[0])
                sys_index = int(sys_spinner.text.split(':')[0])

                self.audio_manager.set_input_device(mic_index)
                self.audio_manager.set_system_audio_device(sys_index)

                success, message = self.audio_manager.test_audio_levels()
                if success:
                    self.show_info_popup("Audio Test", "Audio test completed. Check console for levels.")
                else:
                    self.show_error_popup("Audio Test Failed", message)

            except Exception as e:
                self.show_error_popup("Audio Test Error", str(e))

        def save_devices(instance):
            try:
                if not mic_spinner.text.startswith("Select") and not sys_spinner.text.startswith("Select"):
                    mic_index = int(mic_spinner.text.split(':')[0])
                    sys_index = int(sys_spinner.text.split(':')[0])

                    self.audio_manager.set_input_device(mic_index)
                    self.audio_manager.set_system_audio_device(sys_index)

                    self.show_info_popup("Devices Saved", "Audio devices configured successfully!")
                    self._dismiss_modal(modal)
                else:
                    self.show_error_popup("Selection Required", "Please select both audio devices.")
            except Exception as e:
                self.show_error_popup("Device Configuration Error", str(e))

        def cancel_device_selection(instance):
            self._dismiss_modal(modal)

        test_btn.bind(on_press=test_audio)
        save_btn.bind(on_press=save_devices)
        cancel_btn.bind(on_press=cancel_device_selection)

        # Store reference and open
        self.current_popup = modal
        modal.open()

    def on_client_count_changed(self, spinner, text):
        """Handle client count change"""
        try:
            count = int(text)
            Logger.info(f"Client count changed to: {count}")
        except ValueError:
            Logger.error(f"Invalid client count: {text}")

    def toggle_recording(self, instance):
        """Toggle recording on/off"""
        if not self.recording_active:
            # Start recording
            success, message = self.audio_manager.start_recording()
            if success:
                self.recording_active = True
                self.record_button.text = "Stop Recording"
                self.record_button.background_color = (1, 0, 0, 1)  # Red
                self.analyze_button.disabled = False

                # Create new session
                client_count = int(self.client_count_spinner.text)
                self.current_session_id = self.speaker_manager.create_session(client_count)
                self.speaker_manager.setup_session_speakers(self.current_session_id, client_count)

                Logger.info(f"Recording started - Session ID: {self.current_session_id}")
            else:
                self.show_error_popup("Recording Error", message)
        else:
            # Stop recording
            self.audio_manager.stop_recording()
            self.recording_active = False
            self.record_button.text = "Start Recording"
            self.record_button.background_color = (0, 0.7, 0, 1)  # Green
            Logger.info("Recording stopped")

    def analyze_session(self, instance):
        """Analyze the last 3 minutes of audio"""
        if self.analysis_in_progress:
            return

        self.analysis_in_progress = True
        self.analyze_button.text = "Analyzing..."
        self.analyze_button.disabled = True

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
                Clock.schedule_once(lambda dt: self._analysis_complete(False, result))
                return

            # Transcribe audio
            success, transcripts = self.api_manager.transcribe_audio_files(
                result['therapist_file'],
                result['client_file']
            )

            if not success:
                Clock.schedule_once(lambda dt: self._analysis_complete(False, transcripts.get('error', 'Transcription failed')))
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
                'client_count': int(self.client_count_spinner.text),
                'session_type': 'individual' if int(self.client_count_spinner.text) == 1 else 'multi-client'
            }

            success, analysis = self.api_manager.analyze_therapy_session(formatted_transcript, session_context)

            if success:
                Clock.schedule_once(lambda dt: self._analysis_complete(True, analysis))
            else:
                Clock.schedule_once(lambda dt: self._analysis_complete(False, analysis.get('error', 'Analysis failed')))

        except Exception as e:
            Clock.schedule_once(lambda dt: self._analysis_complete(False, str(e)))

    def _analysis_complete(self, success, result):
        """Handle analysis completion (called from main thread)"""
        self.analysis_in_progress = False
        self.analyze_button.text = "Analyze Last 3 Minutes"
        self.analyze_button.disabled = False

        if success:
            # Format analysis for display
            display_text = self._format_analysis_display(result)
            self.insights_display.text = display_text
            self.insights_display.text_size = (self.insights_display.parent.width - 20, None)
        else:
            self.show_error_popup("Analysis Error", result)
            self.insights_display.text = f"Analysis failed: {result}"

    def _format_analysis_display(self, analysis):
        """Format analysis results for UI display"""
        formatted = "[b]AI Analysis Results[/b]\n\n"

        if 'themes' in analysis and analysis['themes']:
            formatted += "[b]Key Themes per Speaker:[/b]\n"
            formatted += analysis['themes'] + "\n\n"

        if 'dynamics' in analysis and analysis['dynamics']:
            formatted += "[b]Relationship Dynamics:[/b]\n"
            formatted += analysis['dynamics'] + "\n\n"

        if 'follow_up_questions' in analysis and analysis['follow_up_questions']:
            formatted += "[b]Follow-up Questions:[/b]\n"
            formatted += analysis['follow_up_questions'] + "\n\n"

        if 'opportunities' in analysis and analysis['opportunities']:
            formatted += "[b]Therapeutic Opportunities:[/b]\n"
            formatted += analysis['opportunities'] + "\n\n"

        if 'session_notes' in analysis and analysis['session_notes']:
            formatted += "[b]Session Notes:[/b]\n"
            formatted += analysis['session_notes']

        return formatted

    def update_ui(self, dt):
        """Update UI elements periodically"""
        try:
            # Update volume levels
            if self.recording_active:
                levels = self.audio_manager.get_volume_levels()

                if 'microphone' in self.volume_bars:
                    self.volume_bars['microphone'].value = min(levels['microphone'], 1000)
                if 'system' in self.volume_bars:
                    self.volume_bars['system'].value = min(levels['system_audio'], 1000)

                # Update buffer status
                duration = levels['buffer_duration']
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                self.buffer_status.text = f"Buffer: {minutes}:{seconds:02d}"

                # Update status
                self.status_label.text = "● Recording"
                self.status_label.color = (1, 0, 0, 1)  # Red
            else:
                self.status_label.text = "● Ready"
                self.status_label.color = (0, 1, 0, 1)  # Green

        except Exception as e:
            Logger.error(f"UI update error: {e}")

    def _dismiss_modal(self, modal):
        """Safely dismiss a modal and clear reference"""
        if modal and hasattr(modal, 'dismiss'):
            modal.dismiss()
        if self.current_popup == modal:
            self.current_popup = None

    def _on_key_down(self, window, keycode, *args):
        """Handle keyboard events, especially ESC for modal dismissal"""
        if keycode == 27:  # ESC key
            if self.current_popup:
                self._dismiss_modal(self.current_popup)
                return True
        return False

    def show_error_popup(self, title, message):
        """Show error popup with improved styling"""
        modal = ModalView(
            size_hint=(0.7, 0.5),
            auto_dismiss=True,
            background_color=(0, 0, 0, 0.7)
        )

        main_container = BoxLayout(orientation='vertical', padding=20, spacing=15)

        # Background
        with main_container.canvas.before:
            Color(0.95, 0.85, 0.85, 1)  # Light red background
            self.error_bg_rect = Rectangle()

        def update_error_bg(*args):
            self.error_bg_rect.pos = main_container.pos
            self.error_bg_rect.size = main_container.size

        main_container.bind(pos=update_error_bg, size=update_error_bg)

        # Header
        header_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)
        title_label = Label(
            text=f"⚠ {title}",
            font_size='16sp',
            bold=True,
            color=(0.8, 0.1, 0.1, 1),
            size_hint_x=0.8
        )
        header_layout.add_widget(title_label)

        close_btn = Button(
            text="✕",
            size_hint=(None, None),
            size=(35, 35),
            font_size='16sp',
            background_color=(0.8, 0.2, 0.2, 1)
        )
        close_btn.bind(on_press=lambda x: self._dismiss_modal(modal))
        header_layout.add_widget(close_btn)
        main_container.add_widget(header_layout)

        # Message
        message_label = Label(
            text=str(message),
            color=(0.2, 0.2, 0.2, 1),
            text_size=(None, None),
            font_size='13sp'
        )
        main_container.add_widget(message_label)

        # OK button
        ok_btn = Button(
            text="OK",
            size_hint_y=None,
            height=45,
            background_color=(0.8, 0.2, 0.2, 1)
        )
        ok_btn.bind(on_press=lambda x: self._dismiss_modal(modal))
        main_container.add_widget(ok_btn)

        modal.add_widget(main_container)
        modal.open()

    def show_info_popup(self, title, message):
        """Show info popup with improved styling"""
        modal = ModalView(
            size_hint=(0.7, 0.5),
            auto_dismiss=True,
            background_color=(0, 0, 0, 0.7)
        )

        main_container = BoxLayout(orientation='vertical', padding=20, spacing=15)

        # Background
        with main_container.canvas.before:
            Color(0.85, 0.95, 0.85, 1)  # Light green background
            self.info_bg_rect = Rectangle()

        def update_info_bg(*args):
            self.info_bg_rect.pos = main_container.pos
            self.info_bg_rect.size = main_container.size

        main_container.bind(pos=update_info_bg, size=update_info_bg)

        # Header
        header_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)
        title_label = Label(
            text=f"✓ {title}",
            font_size='16sp',
            bold=True,
            color=(0.1, 0.6, 0.1, 1),
            size_hint_x=0.8
        )
        header_layout.add_widget(title_label)

        close_btn = Button(
            text="✕",
            size_hint=(None, None),
            size=(35, 35),
            font_size='16sp',
            background_color=(0.2, 0.7, 0.2, 1)
        )
        close_btn.bind(on_press=lambda x: self._dismiss_modal(modal))
        header_layout.add_widget(close_btn)
        main_container.add_widget(header_layout)

        # Message
        message_label = Label(
            text=str(message),
            color=(0.2, 0.2, 0.2, 1),
            text_size=(None, None),
            font_size='13sp'
        )
        main_container.add_widget(message_label)

        # OK button
        ok_btn = Button(
            text="OK",
            size_hint_y=None,
            height=45,
            background_color=(0.2, 0.7, 0.2, 1)
        )
        ok_btn.bind(on_press=lambda x: self._dismiss_modal(modal))
        main_container.add_widget(ok_btn)

        modal.add_widget(main_container)
        modal.open()

    def on_stop(self):
        """Clean up when app is closing"""
        try:
            Logger.info("Shutting down Amanuensis...")

            # Close any open modals
            if self.current_popup:
                self._dismiss_modal(self.current_popup)

            if self.recording_active:
                self.audio_manager.stop_recording()

            if self.current_session_id:
                notes = self.notes_input.text if self.notes_input else ""
                self.speaker_manager.end_session(self.current_session_id, notes)

            self.audio_manager.cleanup()
            self.api_manager.cleanup()
            self.config_manager.clear_memory()

            # Unbind keyboard events
            Window.unbind(on_key_down=self._on_key_down)

            Logger.info("Cleanup completed")

        except Exception as e:
            Logger.error(f"Cleanup error: {e}")

if __name__ == '__main__':
    try:
        app = AmanuensisApp()
        app.run()
    except Exception as e:
        print(f"Application failed to start: {e}")
        sys.exit(1)