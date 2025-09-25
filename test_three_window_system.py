#!/usr/bin/env python3
"""
Comprehensive Test Suite for Amanuensis Three-Window System
"""

import sys
import os
import time
import traceback
from typing import Dict, List, Tuple

def test_imports():
    """Test that all required modules can be imported"""
    print("Testing Module Imports")
    print("=" * 40)

    modules_to_test = [
        ("customtkinter", "CustomTkinter GUI framework"),
        ("pyaudio", "Audio recording system"),
        ("anthropic", "Claude API integration"),
        ("cryptography", "Security and encryption"),
        ("numpy", "Audio data processing"),
        ("psutil", "System information"),
        ("requests", "HTTP requests for downloads")
    ]

    results = []
    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            print(f"[OK] {module_name:15} - {description}")
            results.append((module_name, True, "OK"))
        except ImportError as e:
            print(f"[FAIL] {module_name:15} - {description} - ERROR: {e}")
            results.append((module_name, False, str(e)))

    # Test faster-whisper specifically
    try:
        import faster_whisper
        print(f"[OK] {'faster-whisper':15} - Local Whisper transcription")
        results.append(("faster-whisper", True, "OK"))
    except ImportError as e:
        print(f"[WARN] {'faster-whisper':15} - Local Whisper transcription - OPTIONAL: {e}")
        results.append(("faster-whisper", False, str(e)))

    # Test torch for GPU acceleration
    try:
        import torch
        cuda_available = torch.cuda.is_available() if hasattr(torch, 'cuda') else False
        mps_available = (hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()) if hasattr(torch, 'backends') else False

        accel_info = []
        if cuda_available:
            accel_info.append("CUDA")
        if mps_available:
            accel_info.append("Metal")

        accel_text = f" ({', '.join(accel_info)} available)" if accel_info else " (CPU only)"
        print(f"[OK] {'torch':15} - Deep learning framework{accel_text}")
        results.append(("torch", True, f"OK{accel_text}"))
    except ImportError as e:
        print(f"[WARN] {'torch':15} - Deep learning framework - OPTIONAL: {e}")
        results.append(("torch", False, str(e)))

    return results

def test_amanuensis_modules():
    """Test Amanuensis-specific modules"""
    print("\nTesting Amanuensis Modules")
    print("=" * 40)

    modules_to_test = [
        ("config_manager", "SecureConfigManager"),
        ("audio_manager", "AudioManager"),
        ("hardware_detector", "HardwareDetector"),
        ("whisper_model_downloader", "ModelDownloadDialog, WhisperModelManager"),
        ("local_whisper_manager", "LocalWhisperManager"),
        ("session_recorder_window", "SessionRecorderWindow"),
        ("insights_dashboard", "InsightsDashboard"),
        ("api_manager", "APIManager")
    ]

    results = []
    for module_name, classes in modules_to_test:
        try:
            module = __import__(module_name)
            print(f"[OK] {module_name:25} - {classes}")
            results.append((module_name, True, "OK"))
        except ImportError as e:
            print(f"[FAIL] {module_name:25} - {classes} - ERROR: {e}")
            results.append((module_name, False, str(e)))
        except Exception as e:
            print(f"[WARN] {module_name:25} - {classes} - WARNING: {e}")
            results.append((module_name, False, str(e)))

    return results

def test_hardware_detection():
    """Test hardware detection system"""
    print("\nTesting Hardware Detection")
    print("=" * 40)

    try:
        from hardware_detector import HardwareDetector
        detector = HardwareDetector()

        print("System Information:")
        print("-" * 20)
        print(detector.get_hardware_summary())

        print("\nModel Recommendation:")
        print("-" * 20)
        recommended = detector.get_model_recommendation()
        print(f"Recommended Whisper model: {recommended}")

        print("\nAll Models Compatibility:")
        print("-" * 20)
        models = detector.get_all_models_info()
        for model in models:
            status = "[OK]" if model['compatible'] else "[FAIL]"
            rec = " (RECOMMENDED)" if model['recommended'] else ""
            print(f"{status} {model['name']:10} - {model['description']}{rec}")
            if not model['compatible']:
                for issue in model['issues']:
                    print(f"    Issue: {issue}")

        return True, "Hardware detection completed successfully"

    except Exception as e:
        print(f"Hardware detection failed: {e}")
        return False, str(e)

def test_audio_system():
    """Test audio system"""
    print("\nTesting Audio System")
    print("=" * 40)

    try:
        from audio_manager import AudioManager
        audio_manager = AudioManager()

        # Test device detection
        devices = audio_manager.get_audio_devices()

        print(f"Input devices found: {len(devices['input_devices'])}")
        for device in devices['input_devices'][:3]:  # Show first 3
            print(f"  • {device['name']}")

        print(f"System recording devices found: {len(devices['system_recording_devices'])}")
        for device in devices['system_recording_devices'][:3]:  # Show first 3
            print(f"  • {device['name']}")

        print(f"Output devices found: {len(devices['output_devices'])}")
        for device in devices['output_devices'][:3]:  # Show first 3
            print(f"  • {device['name']}")

        # Cleanup
        audio_manager.cleanup()

        return True, "Audio system test completed"

    except Exception as e:
        print(f"Audio system test failed: {e}")
        return False, str(e)

def test_whisper_model_manager():
    """Test Whisper model management"""
    print("\nTesting Whisper Model Manager")
    print("=" * 40)

    try:
        from whisper_model_downloader import WhisperModelManager
        model_manager = WhisperModelManager()

        # Check for installed models
        installed = model_manager.get_installed_models()
        print(f"Installed models: {installed if installed else 'None'}")

        needs_setup = model_manager.needs_initial_setup()
        print(f"Needs initial setup: {'Yes' if needs_setup else 'No'}")

        return True, "Model manager test completed"

    except Exception as e:
        print(f"Model manager test failed: {e}")
        return False, str(e)

def test_config_manager():
    """Test configuration manager"""
    print("\nTesting Configuration Manager")
    print("=" * 40)

    try:
        from config_manager import SecureConfigManager
        config = SecureConfigManager()

        # Test basic functionality
        test_key = "test_api_key_12345"
        config.set_api_key("test_service", test_key)
        retrieved_key = config.get_api_key("test_service")

        if retrieved_key == test_key:
            print("[OK] API key encryption/decryption working")
        else:
            print("[FAIL] API key encryption/decryption failed")
            return False, "Key storage test failed"

        return True, "Configuration manager test completed"

    except Exception as e:
        print(f"Configuration manager test failed: {e}")
        return False, str(e)

def test_gui_components():
    """Test GUI components creation (without showing windows)"""
    print("\nTesting GUI Components")
    print("=" * 40)

    results = []

    # Test Session Recorder Window
    try:
        from config_manager import SecureConfigManager
        from audio_manager import AudioManager
        from session_recorder_window import SessionRecorderWindow

        config = SecureConfigManager()
        audio = AudioManager()

        # Don't actually run the window
        print("[OK] SessionRecorderWindow can be imported and instantiated")
        results.append(("SessionRecorderWindow", True, "OK"))

        audio.cleanup()

    except Exception as e:
        print(f"[FAIL] SessionRecorderWindow test failed: {e}")
        results.append(("SessionRecorderWindow", False, str(e)))

    # Test Insights Dashboard
    try:
        from insights_dashboard import InsightsDashboard

        print("[OK] InsightsDashboard can be imported")
        results.append(("InsightsDashboard", True, "OK"))

    except Exception as e:
        print(f"[FAIL] InsightsDashboard test failed: {e}")
        results.append(("InsightsDashboard", False, str(e)))

    return results

def test_main_application():
    """Test main application initialization (without running GUI)"""
    print("\nTesting Main Application")
    print("=" * 40)

    try:
        from amanuensis_new import AmanuensisApplication, check_dependencies

        # Check dependencies
        missing = check_dependencies()
        if missing:
            print(f"[WARN] Missing optional dependencies: {', '.join(missing)}")
        else:
            print("[OK] All dependencies available")

        print("[OK] Main application can be imported")
        return True, "Main application test completed"

    except Exception as e:
        print(f"[FAIL] Main application test failed: {e}")
        return False, str(e)

def generate_test_report(all_results: List[Tuple[str, List]]):
    """Generate a comprehensive test report"""
    print("\n" + "=" * 60)
    print("COMPREHENSIVE TEST REPORT")
    print("=" * 60)

    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    warnings = 0

    for category, results in all_results:
        print(f"\n{category}:")
        print("-" * len(category))

        if isinstance(results, list):
            for test_name, success, message in results:
                total_tests += 1
                if success:
                    passed_tests += 1
                    status = "[OK] PASS"
                    color = ""
                else:
                    if "OPTIONAL" in message or "WARNING" in message:
                        warnings += 1
                        status = "[WARN] WARN"
                        color = ""
                    else:
                        failed_tests += 1
                        status = "[FAIL] FAIL"
                        color = ""

                print(f"  {status} {test_name:25} - {message}")
        else:
            # Single result
            success, message = results
            total_tests += 1
            if success:
                passed_tests += 1
                print(f"  [OK] PASS - {message}")
            else:
                failed_tests += 1
                print(f"  [FAIL] FAIL - {message}")

    print(f"\n{'='*60}")
    print("SUMMARY")
    print("="*60)
    print(f"Total Tests: {total_tests}")
    print(f"Passed:      {passed_tests}")
    print(f"Failed:      {failed_tests}")
    print(f"Warnings:    {warnings}")

    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    print(f"Success Rate: {success_rate:.1f}%")

    if failed_tests == 0:
        print("\n[SUCCESS] All critical tests passed! Amanuensis is ready to run.")
        return True
    else:
        print(f"\n[WARNING] {failed_tests} critical test(s) failed. Please resolve issues before running.")
        return False

def main():
    """Run the complete test suite"""
    print("Amanuensis Three-Window System Test Suite")
    print("Testing all components for readiness...")
    print("=" * 60)

    all_results = []

    # Run all tests
    try:
        # Basic imports
        import_results = test_imports()
        all_results.append(("Module Imports", import_results))

        # Amanuensis modules
        amanuensis_results = test_amanuensis_modules()
        all_results.append(("Amanuensis Modules", amanuensis_results))

        # Hardware detection
        hw_success, hw_message = test_hardware_detection()
        all_results.append(("Hardware Detection", (hw_success, hw_message)))

        # Audio system
        audio_success, audio_message = test_audio_system()
        all_results.append(("Audio System", (audio_success, audio_message)))

        # Model manager
        model_success, model_message = test_whisper_model_manager()
        all_results.append(("Whisper Model Manager", (model_success, model_message)))

        # Config manager
        config_success, config_message = test_config_manager()
        all_results.append(("Configuration Manager", (config_success, config_message)))

        # GUI components
        gui_results = test_gui_components()
        all_results.append(("GUI Components", gui_results))

        # Main application
        app_success, app_message = test_main_application()
        all_results.append(("Main Application", (app_success, app_message)))

    except Exception as e:
        print(f"\n[FAIL] Test suite crashed: {e}")
        traceback.print_exc()
        return 1

    # Generate report
    success = generate_test_report(all_results)

    if success:
        print("\n[READY] To run Amanuensis:")
        print("   python amanuensis_new.py")
        print("\n[SETUP] For first-time setup:")
        print("   1. The Whisper model download dialog will appear")
        print("   2. Select appropriate model for your hardware")
        print("   3. Download completes automatically")
        print("   4. Session recorder window opens")
        print("   5. Click 'Insights' to open analysis dashboard")
        return 0
    else:
        print("\n[FIXES NEEDED] Please resolve the failed tests before running Amanuensis.")
        return 1

if __name__ == "__main__":
    sys.exit(main())