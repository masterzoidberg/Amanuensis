#!/usr/bin/env python3
"""
🎤 AMANUENSIS - Therapy Session Assistant

OFFICIAL MAIN LAUNCHER - Use this to start the application
Three-Window Architecture with Real-Time Local Transcription

Privacy-First • GPU Accelerated • HIPAA Ready
Powered by Faster-Whisper for local speech recognition

To start the application:
  1. Double-click startup.bat, or
  2. Run: python amanuensis_new.py
"""

import customtkinter as ctk
import sys
import os
import threading
import time
from typing import Optional
from logger_config import get_logger, AmanuensisLogger

# Import our modules
from config_manager import SecureConfigManager
from audio_manager import AudioManager
from local_whisper_manager import LocalWhisperManager
from hardware_detector import HardwareDetector
from whisper_model_downloader import WhisperModelManager, ModelDownloadDialog
from session_recorder_window import SessionRecorderWindow
from insights_dashboard import InsightsDashboard
from api_manager import APIManager

class AmanuensisApplication:
    """Main application orchestrating the three-window architecture"""

    def __init__(self):
        # Initialize logging first
        self.logger = get_logger('amanuensis_main')
        self.logger.info("="*60)
        self.logger.info("AMANUENSIS APPLICATION STARTING")
        self.logger.info("="*60)

        # Core managers
        self.config_manager = None
        self.audio_manager = None
        self.whisper_manager = None
        self.api_manager = None
        self.model_manager = None

        # Windows
        self.session_recorder = None
        self.insights_dashboard = None

        # State
        self.app_initialized = False
        self.whisper_model_ready = False

        # Log system information
        AmanuensisLogger().log_system_info()

        # Initialize the application
        self.logger.info("Starting application initialization...")
        self.initialize_app()

    def initialize_app(self):
        """Initialize the application components"""
        self.logger.info("Initializing Amanuensis core components...")

        try:
            # Initialize core managers
            self.logger.debug("Creating SecureConfigManager...")
            start_time = time.time()
            self.config_manager = SecureConfigManager()
            AmanuensisLogger().log_performance('amanuensis_main', 'SecureConfigManager init', time.time() - start_time)

            self.logger.debug("Creating AudioManager...")
            start_time = time.time()
            self.audio_manager = AudioManager()
            AmanuensisLogger().log_performance('amanuensis_main', 'AudioManager init', time.time() - start_time)

            self.logger.debug("Creating APIManager...")
            start_time = time.time()
            self.api_manager = APIManager(self.config_manager)
            AmanuensisLogger().log_performance('amanuensis_main', 'APIManager init', time.time() - start_time)

            self.logger.debug("Creating WhisperModelManager...")
            start_time = time.time()
            self.model_manager = WhisperModelManager()
            AmanuensisLogger().log_performance('amanuensis_main', 'WhisperModelManager init', time.time() - start_time)

            self.logger.info("Core managers initialized successfully")

            # Check for Whisper model installation
            self.logger.debug("Checking Whisper model availability...")
            if self.model_manager.needs_initial_setup():
                self.logger.warning("Whisper model setup required - proceeding without transcription")
                # Skip Whisper setup and proceed with creating windows
                self.create_windows()
            else:
                self.logger.info("Whisper model found - setting up transcription")
                self.setup_whisper_manager()
                self.create_windows()

        except Exception as e:
            self.logger.error(f"Application initialization failed: {e}")
            AmanuensisLogger().log_exception('amanuensis_main', e, "initialize_app")
            self.show_error_dialog("Initialization Error", str(e))

    def show_model_download_dialog(self):
        """Show the model download dialog for first-run setup"""
        print("DEBUG: Opening Whisper model download dialog...")

        # Create a temporary root window for the dialog
        print("DEBUG: Creating temporary root window...")
        temp_root = ctk.CTk()
        temp_root.withdraw()  # Hide the temporary root

        print("DEBUG: Creating ModelDownloadDialog...")
        dialog = ModelDownloadDialog(
            parent=temp_root,
            on_complete=self.on_model_download_complete
        )

        print("DEBUG: Starting dialog mainloop...")
        temp_root.mainloop()
        print("DEBUG: Dialog mainloop ended")

    def on_model_download_complete(self, model_name: str):
        """Handle completion of model download"""
        print(f"OK Model '{model_name}' downloaded successfully")
        self.whisper_model_ready = True

        # Initialize Whisper manager with downloaded model
        self.setup_whisper_manager(model_name)

        # Create the main application windows
        self.create_windows()

    def setup_whisper_manager(self, model_name: str = None):
        """Setup the Whisper manager with the specified or best available model"""
        try:
            if not model_name:
                # Find the best available model
                installed_models = self.model_manager.get_installed_models()
                if not installed_models:
                    raise Exception("No Whisper models available")

                # Use hardware detector to recommend best model
                detector = HardwareDetector()
                recommended = detector.get_model_recommendation()
                model_name = recommended if recommended in installed_models else installed_models[0]

            print(f"Setting up Whisper manager with model: {model_name}")
            self.whisper_manager = LocalWhisperManager(model_name=model_name)

            if self.whisper_manager.model:
                print("OK Whisper manager initialized")
                self.whisper_model_ready = True
            else:
                raise Exception("Failed to load Whisper model")

        except Exception as e:
            print(f"ERROR Whisper setup failed: {e}")
            self.whisper_manager = None
            self.whisper_model_ready = False

    def create_windows(self):
        """Create the main application windows"""
        self.logger.info("Creating application windows...")

        try:
            # Create Session Recorder Window (compact, always visible)
            self.logger.debug("Creating SessionRecorderWindow...")
            start_time = time.time()
            self.session_recorder = SessionRecorderWindow(
                config_manager=self.config_manager,
                audio_manager=self.audio_manager,
                whisper_manager=self.whisper_manager,
                on_insights_request=self.handle_insights_request
            )
            # Pass model_manager to session recorder for settings
            self.session_recorder.model_manager = self.model_manager
            AmanuensisLogger().log_performance('amanuensis_main', 'SessionRecorderWindow init', time.time() - start_time)

            # Create Insights Dashboard (hidden initially)
            self.logger.debug("Creating InsightsDashboard...")
            start_time = time.time()
            self.insights_dashboard = InsightsDashboard(
                config_manager=self.config_manager,
                api_manager=self.api_manager,
                on_close=self.on_insights_dashboard_close
            )
            AmanuensisLogger().log_performance('amanuensis_main', 'InsightsDashboard init', time.time() - start_time)

            # Hide dashboard initially
            self.logger.debug("Hiding dashboard initially...")
            self.insights_dashboard.window.withdraw()

            self.logger.info("Application windows created successfully")
            self.app_initialized = True

            # Start the session recorder window
            self.logger.info("Starting main application loop...")
            self.run()

        except Exception as e:
            self.logger.error(f"Window creation failed: {e}")
            AmanuensisLogger().log_exception('amanuensis_main', e, "create_windows")
            self.show_error_dialog("Window Creation Error", str(e))

    def handle_insights_request(self, transcript: Optional[str], prompt: Optional[str], analysis_type: str):
        """Handle insights request from session recorder"""
        if analysis_type == "show_dashboard":
            # Show the insights dashboard
            self.show_insights_dashboard()
        else:
            # Show dashboard and start analysis
            self.show_insights_dashboard()

            if transcript and prompt:
                # Update dashboard with transcript and start analysis
                self.insights_dashboard.update_transcript(transcript)
                self.insights_dashboard.current_transcript = transcript

                # Simulate starting analysis
                threading.Thread(
                    target=self.run_background_analysis,
                    args=(transcript, prompt, analysis_type),
                    daemon=True
                ).start()

    def run_background_analysis(self, transcript: str, prompt: str, analysis_type: str):
        """Run analysis in background thread"""
        try:
            print(f"Running {analysis_type} analysis...")

            # Call Claude API for analysis
            full_prompt = f"{prompt}\n\nSession Transcript:\n{transcript}"
            response = self.api_manager.get_claude_analysis(full_prompt)

            # Update dashboard with results
            self.insights_dashboard.window.after(0, lambda: self.insights_dashboard.analysis_complete(response, analysis_type))

        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            print(f"ERROR {error_msg}")
            self.insights_dashboard.window.after(0, lambda: self.insights_dashboard.analysis_failed(error_msg))

    def show_insights_dashboard(self):
        """Show the insights dashboard window"""
        if self.insights_dashboard:
            self.insights_dashboard.show()
            # Update session info
            session_info = f"Active session - {time.strftime('%Y-%m-%d %H:%M')}"
            self.insights_dashboard.update_session_info(session_info)

    def on_insights_dashboard_close(self):
        """Handle insights dashboard close"""
        if self.insights_dashboard:
            self.insights_dashboard.window.withdraw()

    def show_error_dialog(self, title: str, message: str):
        """Show an error dialog"""
        root = ctk.CTk()
        root.title(title)
        root.geometry("400x200")

        frame = ctk.CTkFrame(root)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 20))
        ctk.CTkLabel(frame, text=message, wraplength=350).pack(pady=(0, 20))

        def close_app():
            root.destroy()
            sys.exit(1)

        ctk.CTkButton(frame, text="Exit", command=close_app).pack(pady=10)

        root.mainloop()

    def run(self):
        """Run the main application"""
        if not self.app_initialized:
            print("ERROR Application not properly initialized")
            return

        print("Amanuensis started successfully!")
        print("=" * 50)
        print("Session Recorder window is now active.")
        print("Click 'Insights' to open the analysis dashboard.")
        print("Use preset analysis buttons for quick insights.")
        print("=" * 50)

        try:
            # Start Whisper processing if available
            if self.whisper_manager:
                self.whisper_manager.start_processing()
                print("OK Whisper transcription ready")

            # Run the session recorder (main window)
            self.session_recorder.run()

        except KeyboardInterrupt:
            print("\nApplication interrupted by user")
        except Exception as e:
            print(f"ERROR Application error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup application resources"""
        print("Cleaning up application resources...")

        try:
            # Stop Whisper processing
            if self.whisper_manager:
                self.whisper_manager.stop_processing()
                print("OK Whisper manager cleaned up")

            # Stop audio recording
            if self.audio_manager:
                self.audio_manager.cleanup()
                print("OK Audio manager cleaned up")

            # Close windows
            if self.insights_dashboard:
                try:
                    self.insights_dashboard.window.destroy()
                except:
                    pass

            if self.session_recorder:
                try:
                    self.session_recorder.close()
                except:
                    pass

            print("OK Application cleanup completed")

        except Exception as e:
            print(f"WARNING Cleanup error: {e}")

class SplashScreen:
    """Splash screen shown during application startup"""

    def __init__(self):
        self.window = ctk.CTk()
        self.setup_ui()

    def setup_ui(self):
        """Setup splash screen UI"""
        self.window.title("Amanuensis")
        self.window.geometry("400x300")
        self.window.resizable(False, False)

        # Center the window
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.window.winfo_screenheight() // 2) - (300 // 2)
        self.window.geometry(f"400x300+{x}+{y}")

        # Main frame
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Logo/Title
        ctk.CTkLabel(
            main_frame,
            text="[MIC]",
            font=ctk.CTkFont(size=48)
        ).pack(pady=(30, 10))

        ctk.CTkLabel(
            main_frame,
            text="Amanuensis",
            font=ctk.CTkFont(size=28, weight="bold")
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            main_frame,
            text="Therapy Session Assistant",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        ).pack(pady=(0, 30))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(main_frame)
        self.progress_bar.pack(pady=(20, 10))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Initializing...",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(pady=(0, 20))

    def update_progress(self, progress: float, status: str):
        """Update progress and status"""
        self.progress_bar.set(progress)
        self.status_label.configure(text=status)
        self.window.update()

    def close(self):
        """Close the splash screen"""
        self.window.destroy()

def check_dependencies():
    """Check if all required dependencies are available"""
    missing_deps = []

    try:
        import customtkinter
    except ImportError:
        missing_deps.append("customtkinter")

    try:
        import pyaudio
    except ImportError:
        missing_deps.append("pyaudio")

    try:
        import anthropic
    except ImportError:
        missing_deps.append("anthropic")

    try:
        import cryptography
    except ImportError:
        missing_deps.append("cryptography")

    try:
        import faster_whisper
    except ImportError:
        missing_deps.append("faster-whisper")

    return missing_deps

def main():
    """Main entry point"""
    # Initialize logging first
    logger = get_logger('main')

    logger.info("="*60)
    logger.info("AMANUENSIS MAIN ENTRY POINT")
    logger.info("Therapy Session Assistant - Three-Window Architecture")
    logger.info("="*60)

    # Check dependencies
    logger.debug("Checking dependencies...")
    missing = check_dependencies()
    if missing:
        logger.error(f"Missing dependencies: {', '.join(missing)}")
        logger.info(f"Please install: pip install {' '.join(missing)}")
        return 1

    logger.info("All dependencies satisfied")

    # Set CustomTkinter appearance
    logger.debug("Setting CustomTkinter appearance...")
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    try:
        logger.info("Starting Amanuensis application...")
        start_time = time.time()

        # Start main application
        app = AmanuensisApplication()

        total_time = time.time() - start_time
        AmanuensisLogger().log_performance('main', 'Full application startup', total_time)

        return 0

    except KeyboardInterrupt:
        logger.info("Startup interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        AmanuensisLogger().log_exception('main', e, "main function")
        return 1

if __name__ == "__main__":
    sys.exit(main())