#!/usr/bin/env python3
"""
Whisper Model Download Dialog and Management System
"""

import customtkinter as ctk
import threading
import os
import hashlib
import requests
import time
from typing import Dict, Callable, Optional
from hardware_detector import HardwareDetector
import tempfile
import platform

class ModelDownloadDialog:
    """CustomTkinter dialog for downloading Whisper models"""

    def __init__(self, parent=None, on_complete: Optional[Callable] = None):
        self.parent = parent
        self.on_complete = on_complete
        self.hardware_detector = HardwareDetector()
        self.download_thread = None
        self.download_cancelled = False
        self.download_paused = False

        # Model download URLs (Hugging Face)
        self.model_urls = {
            'tiny': 'https://huggingface.co/openai/whisper-tiny/resolve/main/pytorch_model.bin',
            'base': 'https://huggingface.co/openai/whisper-base/resolve/main/pytorch_model.bin',
            'small': 'https://huggingface.co/openai/whisper-small/resolve/main/pytorch_model.bin',
            'medium': 'https://huggingface.co/openai/whisper-medium/resolve/main/pytorch_model.bin',
            'large': 'https://huggingface.co/openai/whisper-large-v3/resolve/main/pytorch_model.bin'
        }

        self.selected_model = self.hardware_detector.get_model_recommendation()
        self.setup_ui()

    def setup_ui(self):
        """Setup the download dialog UI"""
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Amanuensis - Whisper Model Setup")
        self.window.geometry("500x600")
        self.window.resizable(False, False)

        # Make dialog modal
        self.window.transient(self.parent)
        self.window.grab_set()

        # Center the window
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.window.winfo_screenheight() // 2) - (600 // 2)
        self.window.geometry(f"500x600+{x}+{y}")

        # Main container
        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Header
        header_label = ctk.CTkLabel(
            main_frame,
            text="🎤 Welcome to Amanuensis!",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        header_label.pack(pady=(20, 10))

        desc_label = ctk.CTkLabel(
            main_frame,
            text="First, let's download a Whisper model for local\ntranscription to protect your client privacy.",
            font=ctk.CTkFont(size=14),
            justify="center"
        )
        desc_label.pack(pady=(0, 20))

        # Hardware info frame
        hw_frame = ctk.CTkFrame(main_frame)
        hw_frame.pack(fill="x", padx=20, pady=(0, 20))

        hw_title = ctk.CTkLabel(
            hw_frame,
            text="Hardware Detected:",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        hw_title.pack(pady=(15, 5))

        # Get hardware summary and display
        hw_summary = self.hardware_detector.get_hardware_summary()
        hw_text = ctk.CTkTextbox(hw_frame, height=80, font=ctk.CTkFont(size=12))
        hw_text.pack(fill="x", padx=15, pady=(0, 15))
        hw_text.insert("0.0", hw_summary)
        hw_text.configure(state="disabled")

        # Model selection frame
        model_frame = ctk.CTkFrame(main_frame)
        model_frame.pack(fill="x", padx=20, pady=(0, 20))

        model_title = ctk.CTkLabel(
            model_frame,
            text="Select Whisper Model",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        model_title.pack(pady=(15, 10))

        # Model radio buttons
        self.model_var = ctk.StringVar(value=self.selected_model)
        self.model_radios = {}

        models_info = self.hardware_detector.get_all_models_info()
        for model in models_info:
            radio_frame = ctk.CTkFrame(model_frame)
            radio_frame.pack(fill="x", padx=15, pady=2)

            # Radio button with model info
            model_text = f"{model['name']} ({model['size_mb']} MB) - {model['description']}"
            if model['recommended']:
                model_text += " [RECOMMENDED]"

            radio = ctk.CTkRadioButton(
                radio_frame,
                text=model_text,
                variable=self.model_var,
                value=model['name'],
                font=ctk.CTkFont(size=12),
                command=self.on_model_selected
            )
            radio.pack(side="left", padx=10, pady=8)

            # Compatibility indicator
            if not model['compatible']:
                warning = ctk.CTkLabel(
                    radio_frame,
                    text="⚠️",
                    font=ctk.CTkFont(size=14),
                    text_color="#FF6B35"
                )
                warning.pack(side="right", padx=10)

            self.model_radios[model['name']] = radio

        model_frame.pack_configure(pady=(0, 10))

        # Model details frame
        details_frame = ctk.CTkFrame(main_frame)
        details_frame.pack(fill="x", padx=20, pady=(0, 20))

        details_title = ctk.CTkLabel(
            details_frame,
            text="Model Details:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        details_title.pack(pady=(10, 5))

        self.details_text = ctk.CTkTextbox(details_frame, height=100, font=ctk.CTkFont(size=11))
        self.details_text.pack(fill="x", padx=15, pady=(0, 15))

        self.update_model_details()

        # Download progress frame
        self.progress_frame = ctk.CTkFrame(main_frame)
        self.progress_frame.pack(fill="x", padx=20, pady=(0, 20))

        progress_title = ctk.CTkLabel(
            self.progress_frame,
            text="Download Progress",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        progress_title.pack(pady=(10, 5))

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 5))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="Ready to download",
            font=ctk.CTkFont(size=11)
        )
        self.progress_label.pack(pady=(0, 5))

        self.speed_label = ctk.CTkLabel(
            self.progress_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.speed_label.pack(pady=(0, 15))

        # Buttons frame
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.cancel_button = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self.on_cancel,
            width=100,
            fg_color=("gray70", "gray30")
        )
        self.cancel_button.pack(side="left", padx=(0, 10))

        self.download_button = ctk.CTkButton(
            button_frame,
            text="Download & Continue",
            command=self.start_download,
            width=200,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#2CC985", "#2FA572")
        )
        self.download_button.pack(side="right")

        # Handle window close
        self.window.protocol("WM_DELETE_WINDOW", self.on_cancel)

    def on_model_selected(self):
        """Handle model selection change"""
        self.selected_model = self.model_var.get()
        self.update_model_details()

    def update_model_details(self):
        """Update the model details display"""
        models_info = self.hardware_detector.get_all_models_info()
        selected_info = next((m for m in models_info if m['name'] == self.selected_model), None)

        if not selected_info:
            return

        details = f"Model: {selected_info['name']}\n"
        details += f"• Size: {selected_info['size_mb']} MB\n"
        details += f"• Speed: {selected_info['speed']}\n"
        details += f"• Use case: {selected_info['use_case']}\n"
        details += f"• Languages: 99 languages supported\n"
        details += f"• Privacy: 100% local processing\n"

        if not selected_info['compatible']:
            details += f"\n⚠️ Compatibility Issues:\n"
            for issue in selected_info['issues']:
                details += f"• {issue}\n"

        self.details_text.configure(state="normal")
        self.details_text.delete("0.0", "end")
        self.details_text.insert("0.0", details)
        self.details_text.configure(state="disabled")

    def start_download(self):
        """Start the model download"""
        if self.download_thread and self.download_thread.is_alive():
            return

        self.download_cancelled = False
        self.download_paused = False

        # Update UI for download state
        self.download_button.configure(text="Downloading...", state="disabled")
        self.cancel_button.configure(text="Cancel")

        # Start download thread
        self.download_thread = threading.Thread(target=self._download_model)
        self.download_thread.daemon = True
        self.download_thread.start()

    def _download_model(self):
        """Download the selected model (runs in background thread)"""
        try:
            model_name = self.selected_model
            url = self.model_urls.get(model_name)

            if not url:
                self._update_progress("Error: Unknown model", 0, "")
                return

            # Create models directory
            models_dir = os.path.join(os.path.dirname(__file__), "whisper_models")
            os.makedirs(models_dir, exist_ok=True)

            # Download file
            model_path = os.path.join(models_dir, f"{model_name}.bin")

            # Start download with progress tracking
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            start_time = time.time()

            with open(model_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.download_cancelled:
                        f.close()
                        try:
                            os.remove(model_path)
                        except:
                            pass
                        self._update_progress("Download cancelled", 0, "")
                        return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Update progress
                        if total_size > 0:
                            progress = downloaded / total_size
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                speed = downloaded / elapsed / 1024 / 1024  # MB/s
                                eta = (total_size - downloaded) / (downloaded / elapsed) if downloaded > 0 else 0

                                progress_text = f"Downloading... {downloaded // 1024 // 1024}MB / {total_size // 1024 // 1024}MB"
                                speed_text = f"Speed: {speed:.1f} MB/s    ETA: {int(eta)} seconds"

                                self._update_progress(progress_text, progress, speed_text)

            # Download complete
            self._update_progress("Download completed successfully!", 1.0, "")

            # Wait a moment then close
            time.sleep(1)
            self.window.after(0, self._download_complete)

        except Exception as e:
            error_msg = f"Download failed: {str(e)}"
            self._update_progress(error_msg, 0, "")
            self.window.after(0, self._download_failed)

    def _update_progress(self, message: str, progress: float, speed: str):
        """Update progress display (thread-safe)"""
        def update():
            self.progress_label.configure(text=message)
            self.progress_bar.set(progress)
            self.speed_label.configure(text=speed)

        self.window.after(0, update)

    def _download_complete(self):
        """Handle download completion"""
        if self.on_complete:
            self.on_complete(self.selected_model)
        self.window.destroy()

    def _download_failed(self):
        """Handle download failure"""
        self.download_button.configure(text="Retry Download", state="normal")
        self.cancel_button.configure(text="Cancel")

    def on_cancel(self):
        """Handle cancel/close"""
        if self.download_thread and self.download_thread.is_alive():
            self.download_cancelled = True
            # Wait briefly for thread to cleanup
            self.window.after(1000, self.window.destroy)
        else:
            self.window.destroy()

class WhisperModelManager:
    """Manages Whisper models and their installation"""

    def __init__(self):
        from logger_config import get_logger
        self.logger = get_logger('whisper_model_manager')

        self.models_dir = os.path.join(os.path.dirname(__file__), "whisper_models")
        os.makedirs(self.models_dir, exist_ok=True)

        self.logger.info(f"WhisperModelManager initialized with models dir: {self.models_dir}")

    def is_model_installed(self, model_name: str) -> bool:
        """Check if a model is installed by attempting to load it"""
        try:
            from faster_whisper import WhisperModel
            from transcription_config import get_transcription_config

            config = get_transcription_config()
            device, compute_type = config.get_device_config()

            # For model checking, use CPU to avoid GPU memory allocation during checks
            # This prevents CUDA memory issues when just verifying model existence
            check_device = "cpu"
            check_compute_type = "int8"  # Fastest for CPU checking

            self.logger.debug(f"Checking if model '{model_name}' is installed (using {check_device})")

            # First try with local_files_only=True to check if already downloaded
            # Try both our custom download_root AND default HuggingFace cache location
            try:
                # Method 1: Check in our custom models directory
                model = WhisperModel(
                    model_name,
                    device=check_device,
                    compute_type=check_compute_type,
                    download_root=self.models_dir,
                    local_files_only=True  # Don't download, just check if exists
                )
                # If we get here, model is installed in our directory
                del model  # Free memory
                self.logger.debug(f"Model {model_name} found in custom models directory")
                return True
            except Exception as custom_check_error:
                self.logger.debug(f"Model {model_name} not found in custom directory: {custom_check_error}")

                # Method 2: Check in default HuggingFace cache (where download_model actually stores files)
                try:
                    model = WhisperModel(
                        model_name,
                        device=check_device,
                        compute_type=check_compute_type,
                        # No download_root specified - use default HF cache
                        local_files_only=True  # Don't download, just check if exists
                    )
                    # If we get here, model is installed in HF cache
                    del model  # Free memory
                    self.logger.debug(f"Model {model_name} found in HuggingFace cache")
                    return True
                except Exception as hf_check_error:
                    self.logger.debug(f"Model {model_name} not found in HF cache: {hf_check_error}")
                    return False

        except Exception as e:
            self.logger.debug(f"Model {model_name} availability check failed: {e}")
            return False

    def get_installed_models(self) -> list:
        """Get list of installed models"""
        installed = []
        for model_name in ['tiny', 'base', 'small', 'medium', 'large']:
            if self.is_model_installed(model_name):
                installed.append(model_name)

        self.logger.debug(f"Installed models: {installed}")
        return installed

    def needs_initial_setup(self) -> bool:
        """Check if initial model setup is needed"""
        needs_setup = len(self.get_installed_models()) == 0
        self.logger.debug(f"Needs initial setup: {needs_setup}")
        return needs_setup

    def get_model_path(self, model_name: str) -> str:
        """Get model identifier for faster-whisper (model name, not path)"""
        # For faster-whisper, we just return the model name
        # The library handles the path resolution internally
        if self.is_model_installed(model_name):
            return model_name
        return None

    def delete_model(self, model_name: str) -> bool:
        """Delete a model file"""
        try:
            model_path = self.get_model_path(model_name)
            if os.path.exists(model_path):
                os.remove(model_path)
                self.logger.info(f"Deleted model: {model_name}")
                return True
            else:
                self.logger.warning(f"Model {model_name} not found for deletion")
                return False
        except Exception as e:
            self.logger.error(f"Failed to delete model {model_name}: {e}")
            return False

    def get_model_info(self, model_name: str) -> dict:
        """Get information about a model"""
        model_path = self.get_model_path(model_name)
        info = {
            'name': model_name,
            'installed': self.is_model_installed(model_name),
            'path': model_path
        }

        if info['installed']:
            info['size_bytes'] = os.path.getsize(model_path)
            info['size_mb'] = info['size_bytes'] / (1024 * 1024)
            info['modified'] = os.path.getmtime(model_path)

        return info

    def download_model(self, model_name: str, progress_callback=None) -> bool:
        """Download a model using faster-whisper's built-in download mechanism"""
        self.logger.info(f"Starting download of model: {model_name}")

        try:
            # Check if faster-whisper is available
            try:
                from faster_whisper import WhisperModel
                import torch
            except ImportError as e:
                self.logger.error(f"Required packages not available for download: {e}")
                return False

            # Valid model names for faster-whisper
            valid_models = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']
            if model_name not in valid_models:
                self.logger.error(f"Unknown model: {model_name}. Valid models: {valid_models}")
                return False

            # Determine device and compute type
            from transcription_config import get_transcription_config
            config = get_transcription_config()
            device, compute_type = config.get_device_config()

            # Log detailed device information for debugging
            self.logger.info(f"Downloading {model_name} model for device: {device}, compute_type: {compute_type}")

            # Additional CUDA verification for debugging
            try:
                import torch
                if torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
                    vram_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                    self.logger.info(f"CUDA GPU detected: {gpu_name} ({vram_total:.1f}GB VRAM)")
                else:
                    self.logger.warning("PyTorch reports CUDA not available")
            except Exception as e:
                self.logger.warning(f"Error checking CUDA: {e}")

            # Create model directory
            model_dir = os.path.join(self.models_dir, model_name)
            os.makedirs(model_dir, exist_ok=True)

            # Use faster-whisper's built-in download by trying to load the model
            # This will automatically download and cache the model
            try:
                # Set up environment for HuggingFace downloads
                original_hf_home = os.environ.get('HF_HOME')
                os.environ['HF_HOME'] = self.models_dir

                # Ensure network access is available
                os.environ['HF_HUB_OFFLINE'] = '0'  # Enable online access

                if progress_callback:
                    progress_callback("Downloading model...", 10, "")

                self.logger.info(f"Downloading model '{model_name}' with network access enabled")

                # This will trigger download if model doesn't exist
                model = WhisperModel(
                    model_name,
                    device=device,
                    compute_type=compute_type,
                    download_root=self.models_dir,
                    local_files_only=False  # Enable network downloads
                )

                if progress_callback:
                    progress_callback("Verifying model...", 90, "")

                # Test transcription to verify model works
                import numpy as np
                import soundfile as sf

                # Create a short test audio file
                sample_rate = 16000
                duration = 1  # 1 second
                test_audio = np.random.random(sample_rate * duration).astype(np.float32) * 0.1

                temp_file_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                        temp_file_path = temp_file.name
                        sf.write(temp_file_path, test_audio, sample_rate)

                    # Test transcription
                    segments, info = model.transcribe(temp_file_path, beam_size=1)
                    list(segments)  # Consume generator to verify it works

                finally:
                    # Clean up with Windows-compatible retry logic
                    if temp_file_path:
                        self._safe_cleanup_temp_file(temp_file_path)

                    # Clean up model from memory
                    try:
                        if 'model' in locals():
                            del model
                            import gc
                            gc.collect()
                    except Exception as cleanup_e:
                        self.logger.debug(f"Model cleanup warning: {cleanup_e}")

                    # Restore original environment if it existed
                    if original_hf_home is not None:
                        os.environ['HF_HOME'] = original_hf_home
                    elif 'HF_HOME' in os.environ:
                        del os.environ['HF_HOME']

                self.logger.info(f"Model {model_name} downloaded and verified successfully")

                if progress_callback:
                    progress_callback("Download complete!", 100, f"Model {model_name} ready")

                return True

            except Exception as e:
                self.logger.error(f"Model download/verification failed: {e}")
                # Clean up temp file on error too
                if 'temp_file_path' in locals() and temp_file_path:
                    self._safe_cleanup_temp_file(temp_file_path)

                # Clean up environment on error too
                try:
                    if 'original_hf_home' in locals():
                        if original_hf_home is not None:
                            os.environ['HF_HOME'] = original_hf_home
                        elif 'HF_HOME' in os.environ:
                            del os.environ['HF_HOME']
                except Exception as env_cleanup_e:
                    self.logger.debug(f"Environment cleanup warning: {env_cleanup_e}")

                return False

        except Exception as e:
            self.logger.error(f"Failed to download model {model_name}: {e}")
            return False

    def download_model_with_progress(self, model_name: str, progress_callback=None) -> bool:
        """Download model with progress tracking using threading"""
        import threading

        def download_worker():
            return self.download_model(model_name, progress_callback)

        download_thread = threading.Thread(target=download_worker)
        download_thread.start()
        download_thread.join()

        return self.is_model_installed(model_name)

    def show_download_dialog(self, parent=None, on_complete=None) -> ModelDownloadDialog:
        """Show the model download dialog"""
        return ModelDownloadDialog(parent, on_complete)

    def _safe_cleanup_temp_file(self, file_path: str, max_retries: int = 3):
        """Safely cleanup temporary file with Windows-compatible retry logic"""
        import time
        import gc

        for attempt in range(max_retries):
            try:
                # Force garbage collection to release any file handles
                gc.collect()

                # Ensure file exists before trying to delete
                if os.path.exists(file_path):
                    # On Windows, sometimes we need to wait a bit for handles to release
                    if platform.system() == "Windows" and attempt > 0:
                        time.sleep(0.1 * attempt)  # Progressive delay

                    os.unlink(file_path)
                    self.logger.debug(f"Successfully cleaned up temp file: {file_path}")
                    return
                else:
                    # File doesn't exist, cleanup successful
                    return

            except PermissionError as e:
                self.logger.warning(f"Attempt {attempt + 1}: Cannot delete temp file {file_path}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(0.2 * (attempt + 1))  # Wait longer each time
                else:
                    self.logger.error(f"Failed to cleanup temp file after {max_retries} attempts: {file_path}")
            except FileNotFoundError:
                # File already deleted, that's fine
                return
            except Exception as e:
                self.logger.error(f"Unexpected error cleaning up temp file {file_path}: {e}")
                return

def test_model_download():
    """Test the model download dialog"""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("Test Model Download")
    root.geometry("300x200")

    def show_dialog():
        dialog = ModelDownloadDialog(root, lambda model: print(f"Downloaded: {model}"))

    button = ctk.CTkButton(root, text="Show Download Dialog", command=show_dialog)
    button.pack(expand=True)

    root.mainloop()

if __name__ == "__main__":
    test_model_download()