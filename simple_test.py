#!/usr/bin/env python3
"""
Simple test of Amanuensis components
"""

import sys
import traceback

def main():
    """Test basic functionality"""
    print("Testing Amanuensis components...")

    # Test CustomTkinter
    try:
        import customtkinter as ctk
        print("CustomTkinter: OK")
    except Exception as e:
        print(f"CustomTkinter: ERROR - {e}")
        return False

    # Test config manager
    try:
        from config_manager import SecureConfigManager
        config = SecureConfigManager()
        print("ConfigManager: OK")
    except Exception as e:
        print(f"ConfigManager: ERROR - {e}")
        return False

    # Test audio manager
    try:
        from audio_manager import AudioManager
        audio = AudioManager()
        print("AudioManager: OK")
    except Exception as e:
        print(f"AudioManager: ERROR - {e}")
        return False

    # Test speaker manager
    try:
        from speaker_manager import SpeakerManager
        speaker = SpeakerManager()
        print("SpeakerManager: OK")
    except Exception as e:
        print(f"SpeakerManager: ERROR - {e}")
        return False

    # Test API manager
    try:
        from api_manager import APIManager
        api = APIManager(config)
        print("APIManager: OK")
    except Exception as e:
        print(f"APIManager: ERROR - {e}")
        return False

    # Test main app
    try:
        from amanuensis_ctk import AmanuensisApp
        app = AmanuensisApp()
        print("AmanuensisApp: OK")
        print("All components loaded successfully!")
        return True
    except Exception as e:
        print(f"AmanuensisApp: ERROR - {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\nTest PASSED - App should run correctly")
    else:
        print("\nTest FAILED - Check errors above")
    sys.exit(0 if success else 1)