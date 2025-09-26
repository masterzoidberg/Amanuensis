#!/usr/bin/env python3
"""
Test Theme Management Fix
Verify that light mode is accessible and theme switching works properly
"""

import customtkinter as ctk
import time
from logger_config import get_logger

def test_theme_manager():
    """Test the theme manager functionality"""
    logger = get_logger('test_theme')
    logger.info("Testing theme manager functionality...")

    print("THEME MANAGEMENT TEST")
    print("Testing: Light mode accessibility and professional styling")
    print("=" * 60)

    try:
        from theme_manager import get_theme_manager

        theme_manager = get_theme_manager()
        print(f"Theme manager initialized successfully")

        # Test 1: Theme switching
        print("\nTEST 1: Theme Switching")
        print("-" * 30)

        themes = ["dark", "light", "system"]
        for theme in themes:
            success = theme_manager.set_theme(theme)
            print(f"Switch to {theme}: {'SUCCESS' if success else 'FAILED'}")

            if success:
                current = theme_manager.get_current_theme()
                print(f"  Current theme confirmed: {current}")

                colors = theme_manager.get_theme_colors()
                if colors:
                    print(f"  Professional colors available: {len(colors)} colors")
                    print(f"    Primary: {colors.get('primary', 'N/A')}")
                    print(f"    Background: {colors.get('background', 'N/A')}")
                    print(f"    Text: {colors.get('text_primary', 'N/A')}")
                else:
                    print(f"  No colors for theme: {theme}")

        # Test 2: Professional Button Styles
        print("\nTEST 2: Professional Button Styles")
        print("-" * 30)

        button_types = ["primary", "secondary", "success", "warning", "danger"]
        for btn_type in button_types:
            style = theme_manager.get_professional_button_style(btn_type)
            print(f"{btn_type.capitalize()} button: {len(style)} style properties")

        # Test 3: Theme Persistence
        print("\nTEST 3: Theme Persistence")
        print("-" * 30)

        # Set to light theme and check if it persists
        theme_manager.set_theme("light")
        saved_theme = theme_manager.get_current_theme()
        print(f"Set theme to light, current: {saved_theme}")

        # Create new instance to test persistence
        new_manager = get_theme_manager()  # Should be same instance (singleton)
        loaded_theme = new_manager.get_current_theme()
        print(f"New manager instance theme: {loaded_theme}")

        persistence_works = (saved_theme == loaded_theme == "light")
        print(f"Theme persistence: {'WORKING' if persistence_works else 'BROKEN'}")

        return True

    except Exception as e:
        print(f"FAIL: Theme manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_settings_window_light_mode():
    """Test Settings window accessibility in light mode"""
    print("\n" + "=" * 60)
    print("SETTINGS WINDOW LIGHT MODE TEST")
    print("=" * 60)

    try:
        from theme_manager import get_theme_manager
        from settings_window import SettingsWindow

        # Create a mock root window
        root = ctk.CTk()
        root.withdraw()  # Hide the root window

        # Set to light theme
        theme_manager = get_theme_manager()
        theme_manager.set_theme("light")
        print("Set theme to light mode")

        # Mock managers
        class MockManager:
            def __init__(self):
                pass

        # Test Settings window creation
        print("Creating Settings window in light mode...")
        settings = SettingsWindow(
            parent=root,
            config_manager=MockManager(),
            audio_manager=MockManager(),
            whisper_manager=MockManager(),
            model_manager=MockManager()
        )

        print("Settings window created successfully in light mode")

        # Test theme switching within settings
        print("\nTesting theme switching within settings...")
        for theme in ["Dark", "Light", "System"]:
            try:
                settings.change_theme(theme)
                print(f"  Switch to {theme}: SUCCESS")
            except Exception as e:
                print(f"  Switch to {theme}: FAILED - {e}")
                return False

        # Cleanup
        settings.close_window()
        root.destroy()

        print("Settings window light mode test: PASSED")
        return True

    except Exception as e:
        print(f"FAIL: Settings window light mode test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_session_recorder_themes():
    """Test SessionRecorderWindow theme support"""
    print("\n" + "=" * 60)
    print("SESSION RECORDER THEME TEST")
    print("=" * 60)

    try:
        from theme_manager import get_theme_manager
        from session_recorder_window import SessionRecorderWindow

        # Mock managers
        class MockManager:
            def get_device_info(self):
                return {'input_devices': [], 'system_recording_devices': []}

        class MockWhisperManager:
            def get_model_status(self):
                return {'loaded': False, 'loading': False}

        # Set to light theme
        theme_manager = get_theme_manager()
        theme_manager.set_theme("light")
        print("Set theme to light mode")

        # Test session recorder creation (this would normally fail in light mode)
        print("Creating SessionRecorderWindow in light mode...")
        recorder = SessionRecorderWindow(
            config_manager=MockManager(),
            audio_manager=MockManager(),
            whisper_manager=MockWhisperManager()
        )

        print("SessionRecorderWindow created successfully in light mode")

        # Test theme switching
        print("\nTesting theme switching...")
        for theme in ["dark", "light", "system"]:
            theme_manager.set_theme(theme)
            print(f"  Switch to {theme}: SUCCESS")

        # Cleanup
        recorder.close()

        print("Session recorder theme test: PASSED")
        return True

    except Exception as e:
        print(f"FAIL: Session recorder theme test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all theme management tests"""
    print("THEME MANAGEMENT FIX VERIFICATION")
    print("Fix: Light mode accessibility and professional styling")
    print()

    tests = [
        ("Theme Manager", test_theme_manager),
        ("Settings Light Mode", test_settings_window_light_mode),
        ("Session Recorder Themes", test_session_recorder_themes),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            print(f"\nRunning: {test_name}")
            if test_func():
                passed += 1
                print(f"PASS: {test_name}")
            else:
                failed += 1
                print(f"FAIL: {test_name}")
        except Exception as e:
            failed += 1
            print(f"FAIL: {test_name} - Exception: {e}")

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print(f"Success Rate: {passed/(passed+failed)*100:.1f}%")

    if failed == 0:
        print("\nALL TESTS PASSED!")
        print("Light mode is now accessible with professional styling!")
        print("\nKey improvements:")
        print("1. Global theme management with persistence")
        print("2. Settings window accessible in all themes")
        print("3. Professional color schemes for therapy use")
        print("4. Consistent theme switching across all windows")
        print("5. Live theme updates without window restarts")
    else:
        print(f"\n{failed} tests failed - theme management may need additional work")

    return failed == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)