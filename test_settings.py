#!/usr/bin/env python3
"""
Test the Settings Window functionality
"""

import customtkinter as ctk
from settings_window import SettingsWindow
from whisper_model_downloader import WhisperModelManager
from audio_manager import AudioManager
from config_manager import SecureConfigManager


def main():
    """Test the settings window"""
    # Set appearance
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # Create root window
    root = ctk.CTk()
    root.title("Settings Test")
    root.geometry("300x200")

    # Create managers
    config_manager = SecureConfigManager()
    audio_manager = AudioManager()
    model_manager = WhisperModelManager()

    def show_settings():
        """Show the settings window"""
        settings = SettingsWindow(
            parent=root,
            config_manager=config_manager,
            audio_manager=audio_manager,
            whisper_manager=None,  # No whisper manager for test
            model_manager=model_manager
        )

    # Test button
    button = ctk.CTkButton(
        root,
        text="Open Settings",
        command=show_settings,
        width=200,
        height=40
    )
    button.pack(expand=True)

    # Test model download functionality
    def test_download():
        """Test model download"""
        success = model_manager.download_model("tiny")
        print(f"Download test result: {success}")

        # List installed models
        installed = model_manager.get_installed_models()
        print(f"Installed models: {installed}")

    download_btn = ctk.CTkButton(
        root,
        text="Test Download",
        command=test_download,
        width=200,
        height=30
    )
    download_btn.pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    main()