#!/usr/bin/env python3
"""
Amanuensis Launcher

Simple launcher script for the CustomTkinter version of Amanuensis.
This script provides error handling and helps with common startup issues.
"""

import sys
import os

def check_dependencies():
    """Check if required dependencies are installed"""
    missing_deps = []

    # Core UI dependencies
    try:
        import customtkinter
    except ImportError:
        missing_deps.append("customtkinter")

    try:
        import pyaudio
    except ImportError:
        missing_deps.append("pyaudio")

    try:
        import numpy
    except ImportError:
        missing_deps.append("numpy")

    # Enhanced transcription dependencies
    try:
        import faster_whisper
    except ImportError:
        missing_deps.append("faster-whisper")

    try:
        import torch
    except ImportError:
        missing_deps.append("torch")

    try:
        import soundfile
    except ImportError:
        missing_deps.append("soundfile")

    # Optional API dependencies
    try:
        import openai
    except ImportError:
        pass  # Optional for analysis features

    try:
        import anthropic
    except ImportError:
        pass  # Optional for analysis features

    try:
        import cryptography
    except ImportError:
        missing_deps.append("cryptography")

    return missing_deps

def main():
    """Main launcher function"""
    print("Amanuensis - Enhanced Therapy Session Assistant")
    print("===============================================")
    print("CustomTkinter Version with Real-Time Local Transcription")
    print("Powered by Faster-Whisper • Privacy-First • GPU Accelerated")
    print()

    # Check for dependencies
    print("Checking dependencies...")
    missing = check_dependencies()

    if missing:
        print("ERROR: Missing required dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print()
        print("Please install missing dependencies with:")
        print("  pip install -r requirements.txt")
        print()
        input("Press Enter to exit...")
        return 1

    print("All dependencies found!")
    print()

    # Show system information
    print("System Information:")
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print(f"  GPU: {gpu_name} (CUDA Available)")
        else:
            print("  GPU: Not available (CPU mode)")
    except:
        print("  GPU: Could not detect")

    try:
        import psutil
        memory_gb = psutil.virtual_memory().total / (1024**3)
        print(f"  Memory: {memory_gb:.1f} GB")
    except:
        print("  Memory: Could not detect")

    print()

    # Try to import and run the application
    try:
        print("Starting Enhanced Amanuensis...")

        # Initialize transcription environment
        try:
            from transcription_config import setup_transcription_environment
            config = setup_transcription_environment()
            device, compute_type = config.get_device_config()
            print(f"Transcription: {config['model_size']} model on {device}")
        except Exception as e:
            print(f"Transcription setup warning: {e}")

        print()

        # Import the CustomTkinter version
        from amanuensis_ctk import AmanuensisApp

        # Create and run the application
        app = AmanuensisApp()
        app.run()

    except ImportError as e:
        print(f"ERROR: Failed to import application modules: {e}")
        print("Please ensure all application files are present:")
        required_files = [
            "amanuensis_ctk.py",
            "config_manager.py",
            "audio_manager.py",
            "speaker_manager.py",
            "api_manager.py"
        ]

        for file in required_files:
            if os.path.exists(file):
                print(f"  ✓ {file}")
            else:
                print(f"  ✗ {file} (MISSING)")

        print()
        input("Press Enter to exit...")
        return 1

    except Exception as e:
        print(f"ERROR: Application failed to start: {e}")
        print()
        print("Common solutions:")
        print("1. Check that your audio devices are working")
        print("2. Verify Windows audio permissions")
        print("3. Ensure no other applications are using audio devices")
        print("4. Check SETUP_INSTRUCTIONS.md for detailed troubleshooting")
        print()
        input("Press Enter to exit...")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())