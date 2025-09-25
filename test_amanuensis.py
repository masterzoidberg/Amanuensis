#!/usr/bin/env python3
"""
Test Amanuensis CustomTkinter app initialization
"""

import sys
import traceback

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")

    try:
        import customtkinter as ctk
        print("SUCCESS: CustomTkinter imported successfully")
    except ImportError as e:
        print(f"✗ CustomTkinter import failed: {e}")
        return False

    try:
        from config_manager import SecureConfigManager
        print("✓ config_manager imported successfully")
    except ImportError as e:
        print(f"✗ config_manager import failed: {e}")
        return False

    try:
        from audio_manager import AudioManager
        print("✓ audio_manager imported successfully")
    except ImportError as e:
        print(f"✗ audio_manager import failed: {e}")
        return False

    try:
        from speaker_manager import SpeakerManager
        print("✓ speaker_manager imported successfully")
    except ImportError as e:
        print(f"✗ speaker_manager import failed: {e}")
        return False

    try:
        from api_manager import APIManager
        print("✓ api_manager imported successfully")
    except ImportError as e:
        print(f"✗ api_manager import failed: {e}")
        return False

    return True

def test_app_creation():
    """Test that the app can be created"""
    print("\nTesting app creation...")

    try:
        from amanuensis_ctk import AmanuensisApp
        print("✓ AmanuensisApp imported successfully")

        # Try to create the app object (but don't run it)
        app = AmanuensisApp()
        print("✓ AmanuensisApp created successfully")

        return True

    except Exception as e:
        print(f"✗ AmanuensisApp creation failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("Amanuensis CustomTkinter Test")
    print("=" * 40)

    if not test_imports():
        print("\n✗ Import test failed")
        return False

    if not test_app_creation():
        print("\n✗ App creation test failed")
        return False

    print("\n✓ All tests passed! The app should run correctly.")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)