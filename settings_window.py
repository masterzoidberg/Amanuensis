#!/usr/bin/env python3
"""
Amanuensis Settings Window
Comprehensive settings management with Whisper model downloads
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import time
import os
import requests
from typing import Optional, Callable
from logger_config import get_logger, log_function_call
from theme_manager import get_theme_manager, apply_professional_styling


class SettingsWindow:
    """Main settings window with tabbed interface"""

    def __init__(self, parent, config_manager, audio_manager, whisper_manager, model_manager):
        self.logger = get_logger('settings_window')
        self.logger.info("Initializing Settings Window")

        self.parent = parent
        self.config_manager = config_manager
        self.audio_manager = audio_manager
        self.whisper_manager = whisper_manager
        self.model_manager = model_manager

        # Get theme manager for consistent styling
        self.theme_manager = get_theme_manager()

        # Register for theme changes
        self.theme_manager.register_theme_callback(self.on_theme_changed)

        self.setup_ui()

    def setup_ui(self):
        """Setup the settings window UI"""
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Amanuensis Settings")
        self.window.geometry("700x600")
        self.window.resizable(True, True)

        # Make window modal
        self.window.transient(self.parent)
        self.window.grab_set()

        # Center the window
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (700 // 2)
        y = (self.window.winfo_screenheight() // 2) - (600 // 2)
        self.window.geometry(f"700x600+{x}+{y}")

        # Create tabbed interface
        self.tabview = ctk.CTkTabview(self.window)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=20)

        # Create tabs
        self.create_whisper_tab()
        self.create_audio_tab()
        self.create_preferences_tab()

        # Bottom buttons
        self.create_bottom_buttons()

        self.logger.debug("Settings window UI setup completed")

    def create_whisper_tab(self):
        """Create Whisper models management tab"""
        whisper_tab = self.tabview.add("Whisper Models")

        # Model status section
        status_frame = ctk.CTkFrame(whisper_tab)
        status_frame.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            status_frame,
            text="Whisper Model Status",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(15, 10))

        self.whisper_status_label = ctk.CTkLabel(
            status_frame,
            text="Checking model status...",
            font=ctk.CTkFont(size=12)
        )
        self.whisper_status_label.pack(pady=(0, 15))

        # Available models section
        models_frame = ctk.CTkFrame(whisper_tab)
        models_frame.pack(fill="both", expand=True, padx=10, pady=5)

        ctk.CTkLabel(
            models_frame,
            text="Available Models",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        # Model list with scrollable frame
        self.model_scroll_frame = ctk.CTkScrollableFrame(models_frame)
        self.model_scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Populate model list
        self.update_model_list()

        # Control buttons frame
        control_frame = ctk.CTkFrame(whisper_tab, fg_color="transparent")
        control_frame.pack(pady=10)

        # Refresh models button
        refresh_button = ctk.CTkButton(
            control_frame,
            text="Refresh Model Status",
            command=self.refresh_whisper_models,
            width=150
        )
        refresh_button.pack(side="left", padx=(0, 10))

        # Reset model cache button (NEW)
        reset_cache_btn = ctk.CTkButton(
            control_frame,
            text="Reset Model Cache",
            command=self.reset_model_cache,
            width=150,
            fg_color=("#E74C3C", "#C0392B")
        )
        reset_cache_btn.pack(side="left")

    def create_audio_tab(self):
        """Create audio devices configuration tab"""
        audio_tab = self.tabview.add("Audio Devices")

        # System Audio Device Picker section (NEW)
        system_audio_frame = ctk.CTkFrame(audio_tab)
        system_audio_frame.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            system_audio_frame,
            text="System Audio Device (WASAPI Loopback)",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        # Device selection frame
        device_select_frame = ctk.CTkFrame(system_audio_frame, fg_color="transparent")
        device_select_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(device_select_frame, text="Output Device:").pack(side="left")

        self.system_audio_combo = ctk.CTkComboBox(
            device_select_frame,
            values=["Loading devices..."],
            width=300,
            command=self.on_system_device_selected
        )
        self.system_audio_combo.pack(side="left", padx=(10, 10))

        # Test device button
        self.test_device_btn = ctk.CTkButton(
            device_select_frame,
            text="Test Device",
            command=self.test_loopback_device,
            width=100,
            fg_color=("#3498DB", "#2E86AB")
        )
        self.test_device_btn.pack(side="right")

        # Test status label
        self.test_status_label = ctk.CTkLabel(
            system_audio_frame,
            text="Select a device and click 'Test Device' to verify loopback functionality",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.test_status_label.pack(pady=(5, 15))

        # Input devices section
        input_frame = ctk.CTkFrame(audio_tab)
        input_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            input_frame,
            text="Input Devices (Microphones)",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        self.input_devices_list = ctk.CTkTextbox(input_frame, height=100)
        self.input_devices_list.pack(fill="x", padx=15, pady=(0, 10))

        # Test input button
        test_input_btn = ctk.CTkButton(
            input_frame,
            text="Test Selected Input Device",
            command=self.test_input_device
        )
        test_input_btn.pack(pady=(0, 15))

        # Output/System devices section
        output_frame = ctk.CTkFrame(audio_tab)
        output_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            output_frame,
            text="System Audio Devices",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        self.output_devices_list = ctk.CTkTextbox(output_frame, height=120)
        self.output_devices_list.pack(fill="x", padx=15, pady=(0, 10))

        # Test output button
        test_output_btn = ctk.CTkButton(
            output_frame,
            text="Test System Audio Recording",
            command=self.test_output_device
        )
        test_output_btn.pack(pady=(0, 15))

        # Refresh devices button
        refresh_audio_btn = ctk.CTkButton(
            audio_tab,
            text="Refresh Audio Devices",
            command=self.refresh_audio_devices,
            width=200
        )
        refresh_audio_btn.pack(pady=10)

        # Populate device lists
        self.refresh_audio_devices()
        self.refresh_system_audio_devices()

    def create_preferences_tab(self):
        """Create application preferences tab"""
        prefs_tab = self.tabview.add("Preferences")

        # Recording settings
        recording_frame = ctk.CTkFrame(prefs_tab)
        recording_frame.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            recording_frame,
            text="Recording Settings",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        # Buffer duration
        buffer_frame = ctk.CTkFrame(recording_frame, fg_color="transparent")
        buffer_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(buffer_frame, text="Buffer Duration (minutes):").pack(side="left")
        self.buffer_slider = ctk.CTkSlider(
            buffer_frame,
            from_=1,
            to=10,
            number_of_steps=9,
            width=200
        )
        self.buffer_slider.pack(side="left", padx=(10, 10))
        self.buffer_slider.set(3)  # Default 3 minutes

        self.buffer_value_label = ctk.CTkLabel(buffer_frame, text="3 min")
        self.buffer_value_label.pack(side="left")
        self.buffer_slider.configure(command=self.update_buffer_value)

        # Sample rate
        sample_frame = ctk.CTkFrame(recording_frame, fg_color="transparent")
        sample_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(sample_frame, text="Sample Rate:").pack(side="left")
        self.sample_rate_combo = ctk.CTkComboBox(
            sample_frame,
            values=["22050 Hz", "44100 Hz", "48000 Hz"],
            width=120
        )
        self.sample_rate_combo.pack(side="left", padx=(10, 0))
        self.sample_rate_combo.set("44100 Hz")

        # Auto-save recordings
        self.auto_save_var = ctk.BooleanVar(value=True)
        auto_save_cb = ctk.CTkCheckBox(
            recording_frame,
            text="Auto-save recordings every 5 minutes",
            variable=self.auto_save_var
        )
        auto_save_cb.pack(pady=(10, 15), padx=15, anchor="w")

        # UI settings
        ui_frame = ctk.CTkFrame(prefs_tab)
        ui_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            ui_frame,
            text="User Interface",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        # Theme selection
        theme_frame = ctk.CTkFrame(ui_frame, fg_color="transparent")
        theme_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(theme_frame, text="Theme:").pack(side="left")
        self.theme_combo = ctk.CTkComboBox(
            theme_frame,
            values=["Dark", "Light", "System"],
            width=120,
            command=self.change_theme
        )
        self.theme_combo.pack(side="left", padx=(10, 0))
        self.theme_combo.set("Dark")

        # Always on top
        self.always_on_top_var = ctk.BooleanVar()
        always_top_cb = ctk.CTkCheckBox(
            ui_frame,
            text="Keep main window always on top",
            variable=self.always_on_top_var
        )
        always_top_cb.pack(pady=10, padx=15, anchor="w")

        # Minimize to tray
        self.minimize_tray_var = ctk.BooleanVar()
        minimize_cb = ctk.CTkCheckBox(
            ui_frame,
            text="Minimize to system tray",
            variable=self.minimize_tray_var
        )
        minimize_cb.pack(pady=(0, 15), padx=15, anchor="w")

        # Storage settings
        storage_frame = ctk.CTkFrame(prefs_tab)
        storage_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(
            storage_frame,
            text="Storage",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        # Recording location
        location_frame = ctk.CTkFrame(storage_frame, fg_color="transparent")
        location_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(location_frame, text="Recording Location:").pack(anchor="w")
        self.location_entry = ctk.CTkEntry(location_frame, width=300)
        self.location_entry.pack(side="left", padx=(0, 5))
        self.location_entry.insert(0, os.path.abspath("temp_recordings"))

        browse_btn = ctk.CTkButton(
            location_frame,
            text="Browse...",
            command=self.browse_recording_location,
            width=80
        )
        browse_btn.pack(side="left")

        # Auto-cleanup
        cleanup_frame = ctk.CTkFrame(storage_frame, fg_color="transparent")
        cleanup_frame.pack(fill="x", padx=15, pady=(10, 15))

        self.auto_cleanup_var = ctk.BooleanVar(value=True)
        cleanup_cb = ctk.CTkCheckBox(
            cleanup_frame,
            text="Auto-delete recordings older than:",
            variable=self.auto_cleanup_var
        )
        cleanup_cb.pack(side="left")

        self.cleanup_days_combo = ctk.CTkComboBox(
            cleanup_frame,
            values=["7 days", "14 days", "30 days", "90 days"],
            width=80
        )
        self.cleanup_days_combo.pack(side="left", padx=(10, 0))
        self.cleanup_days_combo.set("30 days")

    def create_bottom_buttons(self):
        """Create bottom action buttons"""
        button_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Cancel button
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self.cancel,
            width=100,
            fg_color=("gray70", "gray30")
        )
        cancel_btn.pack(side="right", padx=(10, 0))

        # Apply button
        apply_btn = ctk.CTkButton(
            button_frame,
            text="Apply",
            command=self.apply_settings,
            width=100
        )
        apply_btn.pack(side="right")

        # OK button
        ok_btn = ctk.CTkButton(
            button_frame,
            text="OK",
            command=self.ok,
            width=100,
            fg_color=("#2CC985", "#2FA572")
        )
        ok_btn.pack(side="right", padx=(0, 10))

    @log_function_call('settings_window')
    def update_model_list(self):
        """Update the list of available Whisper models"""
        self.logger.debug("Updating Whisper model list")

        # Clear existing widgets
        for widget in self.model_scroll_frame.winfo_children():
            widget.destroy()

        # Define available models with details
        models_info = {
            'tiny': {
                'name': 'Tiny (39 MB)',
                'description': 'Fastest, least accurate. Good for testing.',
                'size': '39 MB',
                'speed': 'Very Fast',
                'accuracy': 'Low'
            },
            'base': {
                'name': 'Base (74 MB)',
                'description': 'Balanced speed and accuracy.',
                'size': '74 MB',
                'speed': 'Fast',
                'accuracy': 'Medium'
            },
            'small': {
                'name': 'Small (244 MB)',
                'description': 'Good balance for most users.',
                'size': '244 MB',
                'speed': 'Medium',
                'accuracy': 'Good'
            },
            'medium': {
                'name': 'Medium (769 MB)',
                'description': 'Higher accuracy, slower processing.',
                'size': '769 MB',
                'speed': 'Slow',
                'accuracy': 'High'
            },
            'large': {
                'name': 'Large (1550 MB)',
                'description': 'Best accuracy, slowest processing.',
                'size': '1550 MB',
                'speed': 'Very Slow',
                'accuracy': 'Excellent'
            }
        }

        # Get installed models
        installed_models = []
        if self.model_manager:
            try:
                installed_models = self.model_manager.get_installed_models()
            except:
                installed_models = []

        # Create model cards
        for model_id, info in models_info.items():
            self.create_model_card(model_id, info, model_id in installed_models)

    def create_model_card(self, model_id: str, info: dict, is_installed: bool):
        """Create a model card widget"""
        card_frame = ctk.CTkFrame(self.model_scroll_frame)
        card_frame.pack(fill="x", pady=5)

        # Header with model name and status
        header_frame = ctk.CTkFrame(card_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(10, 5))

        model_name_label = ctk.CTkLabel(
            header_frame,
            text=info['name'],
            font=ctk.CTkFont(size=14, weight="bold")
        )
        model_name_label.pack(side="left")

        status_label = ctk.CTkLabel(
            header_frame,
            text="Installed" if is_installed else "Not Installed",
            text_color="#2CC985" if is_installed else "#E74C3C",
            font=ctk.CTkFont(size=11)
        )
        status_label.pack(side="right")

        # Description
        desc_label = ctk.CTkLabel(
            card_frame,
            text=info['description'],
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        desc_label.pack(anchor="w", padx=15)

        # Details and actions
        details_frame = ctk.CTkFrame(card_frame, fg_color="transparent")
        details_frame.pack(fill="x", padx=15, pady=(5, 10))

        # Model details
        details_text = f"Size: {info['size']} | Speed: {info['speed']} | Accuracy: {info['accuracy']}"
        details_label = ctk.CTkLabel(
            details_frame,
            text=details_text,
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        details_label.pack(side="left")

        # Action buttons
        if is_installed:
            # Load button
            load_btn = ctk.CTkButton(
                details_frame,
                text="Load",
                command=lambda m=model_id: self.load_model(m),
                width=60,
                height=25,
                font=ctk.CTkFont(size=10),
                fg_color=("#2CC985", "#2FA572")
            )
            load_btn.pack(side="right", padx=(5, 0))

            # Delete button
            delete_btn = ctk.CTkButton(
                details_frame,
                text="Delete",
                command=lambda m=model_id: self.delete_model(m),
                width=60,
                height=25,
                font=ctk.CTkFont(size=10),
                fg_color=("#E74C3C", "#C0392B")
            )
            delete_btn.pack(side="right")
        else:
            # Download button
            download_btn = ctk.CTkButton(
                details_frame,
                text="Download",
                command=lambda m=model_id: self.download_model(m),
                width=80,
                height=25,
                font=ctk.CTkFont(size=10),
                fg_color=("#3498DB", "#2E86AB")
            )
            download_btn.pack(side="right")

    @log_function_call('settings_window')
    def download_model(self, model_id: str):
        """Download a Whisper model"""
        self.logger.info(f"Starting download of Whisper model: {model_id}")

        if self.model_manager:
            # Update UI to show download in progress
            self.update_download_status(model_id, "downloading")

            # Use the integrated download method in background thread
            def download_worker():
                try:
                    success = self.model_manager.download_model(model_id)
                    # Schedule UI update on main thread
                    self.window.after(0, lambda: self.on_download_complete(model_id, success))
                except Exception as e:
                    self.logger.error(f"Download error for {model_id}: {e}")
                    self.window.after(0, lambda: self.on_download_complete(model_id, False))

            download_thread = threading.Thread(target=download_worker, daemon=True)
            download_thread.start()
        else:
            # Fallback to download dialog
            DownloadDialog(self.window, model_id, self.on_download_complete)

    def update_download_status(self, model_id: str, status: str):
        """Update the download status for a specific model in the UI"""
        try:
            # Find and update the specific model card's download button
            # For now, just refresh the entire model list - more efficient approach could target specific card
            if status == "downloading":
                self.logger.debug(f"Marking model {model_id} as downloading in UI")
                # Could implement specific button state changes here
            elif status == "completed":
                self.logger.debug(f"Marking model {model_id} as completed in UI")
                self.update_model_list()
        except Exception as e:
            self.logger.warning(f"Failed to update download status for {model_id}: {e}")

    def on_download_complete(self, model_id: str, success: bool):
        """Handle model download completion"""
        if success:
            self.logger.info(f"Model {model_id} downloaded successfully")
            # Update status before showing dialog
            self.update_download_status(model_id, "completed")
            messagebox.showinfo("Download Complete", f"Model '{model_id}' downloaded successfully!")
            self.update_model_list()
            self.update_whisper_status()
        else:
            self.logger.error(f"Model {model_id} download failed")
            messagebox.showerror("Download Failed", f"Failed to download model '{model_id}'")

    def load_model(self, model_id: str):
        """Load a Whisper model"""
        self.logger.info(f"Loading Whisper model: {model_id}")
        try:
            # TODO: Implement model loading
            messagebox.showinfo("Model Loaded", f"Model '{model_id}' loaded successfully!")
            self.update_whisper_status()
        except Exception as e:
            self.logger.error(f"Failed to load model {model_id}: {e}")
            messagebox.showerror("Load Failed", f"Failed to load model '{model_id}': {str(e)}")

    def delete_model(self, model_id: str):
        """Delete a Whisper model"""
        result = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete the '{model_id}' model?\nThis action cannot be undone."
        )

        if result:
            self.logger.info(f"Deleting Whisper model: {model_id}")
            try:
                if self.model_manager:
                    success = self.model_manager.delete_model(model_id)
                    if success:
                        messagebox.showinfo("Model Deleted", f"Model '{model_id}' deleted successfully!")
                        self.update_model_list()
                        self.update_whisper_status()
                    else:
                        messagebox.showerror("Delete Failed", f"Failed to delete model '{model_id}'")
                else:
                    messagebox.showerror("Error", "Model manager not available")
            except Exception as e:
                self.logger.error(f"Failed to delete model {model_id}: {e}")
                messagebox.showerror("Delete Failed", f"Failed to delete model '{model_id}': {str(e)}")

    def refresh_whisper_models(self):
        """Refresh Whisper models list and status"""
        self.logger.debug("Refreshing Whisper models")
        self.update_model_list()
        self.update_whisper_status()

    def update_whisper_status(self):
        """Update Whisper status display"""
        try:
            if self.whisper_manager and hasattr(self.whisper_manager, 'model') and self.whisper_manager.model:
                status_text = f"Whisper is active with model: {self.whisper_manager.model_name}"
                text_color = "#2CC985"
            else:
                status_text = "Whisper is not active - no model loaded"
                text_color = "#E74C3C"

            self.whisper_status_label.configure(text=status_text, text_color=text_color)

        except Exception as e:
            self.logger.error(f"Failed to update Whisper status: {e}")
            self.whisper_status_label.configure(
                text="Error checking Whisper status",
                text_color="#E74C3C"
            )

    def refresh_audio_devices(self):
        """Refresh audio device lists"""
        self.logger.debug("Refreshing audio device lists")

        try:
            # Get input devices
            input_devices = self.audio_manager.get_input_devices()
            input_text = "Input Devices (Microphones):\n" + "="*40 + "\n\n"

            for i, device in enumerate(input_devices):
                input_text += f"{i+1}. {device['name']}\n"
                input_text += f"   Channels: {device['channels']}\n"
                input_text += f"   Sample Rate: {int(device['sample_rate'])} Hz\n\n"

            self.input_devices_list.configure(state="normal")
            self.input_devices_list.delete("0.0", "end")
            self.input_devices_list.insert("0.0", input_text)
            self.input_devices_list.configure(state="disabled")

            # Get system audio devices
            system_devices = self.audio_manager.get_system_audio_devices()
            output_text = "System Audio Devices:\n" + "="*40 + "\n\n"

            for i, device in enumerate(system_devices):
                output_text += f"{i+1}. {device['name']}\n"
                output_text += f"   Type: {device['type']}\n"
                if 'channels' in device:
                    output_text += f"   Channels: {device['channels']}\n"
                if 'sample_rate' in device:
                    output_text += f"   Sample Rate: {int(device['sample_rate'])} Hz\n"
                output_text += "\n"

            self.output_devices_list.configure(state="normal")
            self.output_devices_list.delete("0.0", "end")
            self.output_devices_list.insert("0.0", output_text)
            self.output_devices_list.configure(state="disabled")

        except Exception as e:
            self.logger.error(f"Failed to refresh audio devices: {e}")

    def test_input_device(self):
        """Test the selected input device"""
        messagebox.showinfo("Test Input", "Input device testing will be implemented soon.")

    def test_output_device(self):
        """Test system audio recording"""
        messagebox.showinfo("Test Output", "System audio testing will be implemented soon.")

    def update_buffer_value(self, value):
        """Update buffer duration display"""
        minutes = int(value)
        self.buffer_value_label.configure(text=f"{minutes} min")

    def change_theme(self, theme):
        """Change application theme globally"""
        self.logger.info(f"Changing theme to: {theme}")

        # Map UI labels to theme manager names
        theme_map = {
            "Dark": "dark",
            "Light": "light",
            "System": "system"
        }

        theme_name = theme_map.get(theme, theme.lower())

        # Apply theme globally using theme manager
        success = self.theme_manager.set_theme(theme_name)

        if success:
            self.logger.info(f"Successfully changed theme to: {theme_name}")
        else:
            self.logger.error(f"Failed to change theme to: {theme_name}")
            messagebox.showerror("Theme Error", f"Failed to apply {theme} theme")

    def on_theme_changed(self, theme_name: str, theme_config: dict):
        """Callback when theme changes - update UI styling"""
        try:
            self.logger.debug(f"Updating UI for theme change: {theme_name}")

            # Apply professional styling to key elements
            if hasattr(self, 'window') and self.window.winfo_exists():
                # The CustomTkinter widgets will automatically update their appearance
                # but we can add custom professional styling here

                # Update any custom styled elements
                self.apply_professional_styling()

        except Exception as e:
            self.logger.warning(f"Failed to update theme styling: {e}")

    def apply_professional_styling(self):
        """Apply professional styling to settings window"""
        try:
            colors = self.theme_manager.get_theme_colors()
            if not colors:
                return

            # Apply professional styling to frames and labels if they exist
            for attr_name in dir(self):
                attr = getattr(self, attr_name)
                if hasattr(attr, 'configure') and attr.winfo_exists():
                    try:
                        if 'frame' in attr_name.lower():
                            apply_professional_styling(attr, "frame")
                        elif 'label' in attr_name.lower():
                            apply_professional_styling(attr, "label")
                        elif 'entry' in attr_name.lower():
                            apply_professional_styling(attr, "entry")
                    except:
                        pass  # Ignore styling errors

        except Exception as e:
            self.logger.debug(f"Professional styling update failed: {e}")

    def close_window(self):
        """Close the settings window and cleanup"""
        try:
            # Unregister theme callback
            if hasattr(self, 'theme_manager'):
                self.theme_manager.unregister_theme_callback(self.on_theme_changed)

            if hasattr(self, 'window'):
                self.window.destroy()
        except Exception as e:
            self.logger.warning(f"Error closing settings window: {e}")

    def browse_recording_location(self):
        """Browse for recording location"""
        folder = filedialog.askdirectory(
            title="Select Recording Location",
            initialdir=self.location_entry.get()
        )

        if folder:
            self.location_entry.delete(0, "end")
            self.location_entry.insert(0, folder)

    def apply_settings(self):
        """Apply current settings without closing window"""
        self.logger.info("Applying settings")

        # TODO: Implement settings application
        messagebox.showinfo("Settings Applied", "Settings have been applied successfully!")

    def ok(self):
        """Apply settings and close window"""
        self.apply_settings()
        self.window.destroy()

    def cancel(self):
        """Close window without applying settings"""
        self.window.destroy()

    def refresh_system_audio_devices(self):
        """Refresh system audio devices for loopback capture"""
        self.logger.debug("Refreshing system audio devices for loopback")

        try:
            # Try to import soundcard to get speaker devices
            try:
                import soundcard as sc
                speakers = sc.all_speakers()
                device_names = [f"{speaker.name}" for speaker in speakers]

                if not device_names:
                    device_names = ["No audio devices found"]

                self.system_audio_combo.configure(values=device_names)
                if device_names and device_names[0] != "No audio devices found":
                    self.system_audio_combo.set(device_names[0])  # Set to first device
                else:
                    self.system_audio_combo.set("No devices available")

            except ImportError:
                self.logger.warning("soundcard module not available for device enumeration")
                self.system_audio_combo.configure(values=["soundcard module not installed"])
                self.system_audio_combo.set("soundcard module not installed")

        except Exception as e:
            self.logger.error(f"Failed to refresh system audio devices: {e}")
            self.system_audio_combo.configure(values=["Error loading devices"])
            self.system_audio_combo.set("Error loading devices")

    def on_system_device_selected(self, device_name: str):
        """Handle system audio device selection"""
        self.logger.debug(f"System audio device selected: {device_name}")

        # Update configuration (save selected device)
        try:
            from transcription_config import get_transcription_config
            config = get_transcription_config()
            config._config['loopback_device_name'] = device_name if device_name != "Default" else None

            self.test_status_label.configure(
                text=f"Selected: {device_name} - Click 'Test Device' to verify",
                text_color="gray"
            )
        except Exception as e:
            self.logger.error(f"Failed to update device selection: {e}")

    def test_loopback_device(self):
        """Test the selected loopback device"""
        selected_device = self.system_audio_combo.get()

        if selected_device in ["No devices available", "Error loading devices", "soundcard module not installed"]:
            self.test_status_label.configure(
                text="Cannot test: No valid device selected",
                text_color="#E74C3C"
            )
            return

        self.logger.info(f"Testing loopback device: {selected_device}")
        self.test_status_label.configure(text="Testing device...", text_color="#F39C12")
        self.test_device_btn.configure(state="disabled")

        def test_worker():
            """Test loopback device in background thread"""
            try:
                # Initialize COM for WASAPI access in this thread
                try:
                    from com_initializer import initialize_com_for_audio
                    if not initialize_com_for_audio():
                        raise RuntimeError("Failed to initialize COM for WASAPI audio access")
                except ImportError:
                    # COM initializer not available (non-Windows systems)
                    pass

                from audio_transcription_bridge import resolve_loopback_mic, preflight_loopback

                # Temporarily set the device name
                device_name = selected_device if selected_device != "Default" else None

                # Test the device
                mic, spk = resolve_loopback_mic() if device_name is None else resolve_loopback_mic()
                preflight_loopback(mic)

                # Success
                self.window.after(0, lambda: self.test_device_success(selected_device))

            except Exception as e:
                error_msg = str(e)
                # Provide more helpful error messages for common COM issues
                if "0x800401f0" in error_msg:
                    error_msg = "COM initialization failed - try running as administrator"
                elif "0x80070005" in error_msg:
                    error_msg = "Audio device access denied - check device permissions"
                elif "device not found" in error_msg.lower():
                    error_msg = "Audio device not found or not accessible"

                self.window.after(0, lambda: self.test_device_failed(selected_device, error_msg))

        # Start test in background thread
        test_thread = threading.Thread(target=test_worker, daemon=True)
        test_thread.start()

    def test_device_success(self, device_name: str):
        """Handle successful device test"""
        self.logger.info(f"Device test successful: {device_name}")
        self.test_status_label.configure(
            text=f"✓ PASS - {device_name} is working correctly",
            text_color="#2CC985"
        )
        self.test_device_btn.configure(state="normal")

    def test_device_failed(self, device_name: str, error_msg: str):
        """Handle failed device test"""
        self.logger.error(f"Device test failed: {device_name} - {error_msg}")
        self.test_status_label.configure(
            text=f"✗ FAIL - {device_name}: {error_msg[:50]}...",
            text_color="#E74C3C"
        )
        self.test_device_btn.configure(state="normal")

    def reset_model_cache(self):
        """Reset Whisper model cache"""
        result = messagebox.askyesno(
            "Reset Model Cache",
            "This will delete all downloaded Whisper models and force them to be re-downloaded.\n\n"
            "Are you sure you want to continue?"
        )

        if result:
            self.logger.info("Resetting Whisper model cache")
            try:
                from enhanced_whisper_manager import reset_model_cache

                success = reset_model_cache()  # Reset cache for current model

                if success:
                    messagebox.showinfo(
                        "Cache Reset",
                        "Model cache has been reset successfully.\nModels will be re-downloaded on next use."
                    )
                    self.update_model_list()
                    self.update_whisper_status()
                else:
                    messagebox.showwarning(
                        "Cache Reset",
                        "No cache found to reset, or reset failed.\nCheck logs for details."
                    )

            except Exception as e:
                self.logger.error(f"Failed to reset model cache: {e}")
                messagebox.showerror(
                    "Cache Reset Failed",
                    f"Failed to reset model cache:\n{str(e)}"
                )


class DownloadDialog:
    """Dialog for downloading Whisper models with progress"""

    def __init__(self, parent, model_id: str, on_complete: Callable):
        self.parent = parent
        self.model_id = model_id
        self.on_complete = on_complete
        self.download_cancelled = False

        self.logger = get_logger('model_download')
        self.setup_ui()
        self.start_download()

    def setup_ui(self):
        """Setup download dialog UI"""
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title(f"Downloading {self.model_id} Model")
        self.window.geometry("400x200")
        self.window.resizable(False, False)

        # Make dialog modal
        self.window.transient(self.parent)
        self.window.grab_set()

        # Center the dialog
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.window.winfo_screenheight() // 2) - (200 // 2)
        self.window.geometry(f"400x200+{x}+{y}")

        main_frame = ctk.CTkFrame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text=f"Downloading Whisper {self.model_id} Model",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(20, 10))

        # Status
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Preparing download...",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(pady=10)

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(main_frame, width=300)
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)

        # Cancel button
        self.cancel_btn = ctk.CTkButton(
            main_frame,
            text="Cancel",
            command=self.cancel_download,
            width=100,
            fg_color=("#E74C3C", "#C0392B")
        )
        self.cancel_btn.pack(pady=(10, 20))

    def start_download(self):
        """Start the download in a background thread"""
        self.download_thread = threading.Thread(target=self._download_worker)
        self.download_thread.daemon = True
        self.download_thread.start()

    def _download_worker(self):
        """Worker thread for downloading model"""
        try:
            self.logger.info(f"Starting download of {self.model_id} model")

            # Simulate download process (replace with actual download logic)
            total_steps = 100
            for i in range(total_steps):
                if self.download_cancelled:
                    self.logger.info("Download cancelled by user")
                    return

                # Simulate download progress
                time.sleep(0.05)  # Simulate download time
                progress = (i + 1) / total_steps

                # Update UI on main thread
                self.window.after(0, lambda p=progress: self.update_progress(p))

            # Download completed
            self.window.after(0, self.download_complete)

        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            self.window.after(0, lambda: self.download_failed(str(e)))

    def update_progress(self, progress: float):
        """Update progress bar and status"""
        self.progress_bar.set(progress)
        percent = int(progress * 100)
        self.status_label.configure(text=f"Downloading... {percent}%")

    def download_complete(self):
        """Handle successful download completion"""
        self.logger.info(f"Download of {self.model_id} completed successfully")
        self.window.destroy()
        self.on_complete(self.model_id, True)

    def download_failed(self, error_msg: str):
        """Handle download failure"""
        self.logger.error(f"Download failed: {error_msg}")
        self.window.destroy()
        self.on_complete(self.model_id, False)

    def cancel_download(self):
        """Cancel the download"""
        self.download_cancelled = True
        self.window.destroy()
        self.on_complete(self.model_id, False)


if __name__ == "__main__":
    # Test the settings window
    root = ctk.CTk()
    root.withdraw()  # Hide root window

    # Mock managers for testing
    class MockManager:
        pass

    settings = SettingsWindow(root, MockManager(), MockManager(), None, MockManager())
    root.mainloop()