#!/usr/bin/env python3
"""
Test UI/Backend Model Status Synchronization
Verify that downloaded models show as "Installed" and "Ready to Load" in the UI
"""

import time
from logger_config import get_logger

def test_model_status_sync():
    """Test model download -> UI status synchronization"""
    logger = get_logger('test_model_sync')
    logger.info("Testing UI/backend model status synchronization...")

    try:
        # Test 1: WhisperModelManager installation detection
        print("=" * 60)
        print("TEST 1: WhisperModelManager Model Detection")
        print("=" * 60)

        from whisper_model_downloader import WhisperModelManager
        model_manager = WhisperModelManager()

        test_models = ['tiny', 'base', 'small']
        for model in test_models:
            is_installed = model_manager.is_model_installed(model)
            print(f"Model '{model}': {'INSTALLED' if is_installed else 'NOT INSTALLED'}")

        print()

        # Test 2: EnhancedWhisperManager status integration
        print("=" * 60)
        print("TEST 2: EnhancedWhisperManager Status Integration")
        print("=" * 60)

        from enhanced_whisper_manager import EnhancedWhisperManager
        from transcription_config import get_transcription_config

        trans_config = get_transcription_config()
        whisper_manager = EnhancedWhisperManager(trans_config['model_size'])

        status = whisper_manager.get_model_status()
        print(f"Current model: {status['model_name']}")
        print(f"Model loaded: {status['loaded']}")
        print(f"Model downloading: {status['loading']}")
        print(f"Model downloaded: {status.get('model_downloaded', False)}")
        print(f"Device: {status['device']}")

        print()

        # Test 3: Settings Window Model List (mock test)
        print("=" * 60)
        print("TEST 3: Settings Window Model Status Display")
        print("=" * 60)

        # Simulate what Settings window would show for each model
        models_info = {
            'tiny': {'name': 'Tiny (39 MB)', 'description': 'Fastest, least accurate'},
            'base': {'name': 'Base (74 MB)', 'description': 'Balanced speed and accuracy'},
            'small': {'name': 'Small (244 MB)', 'description': 'Good balance for most users'}
        }

        for model_id, info in models_info.items():
            is_installed = model_manager.is_model_installed(model_id)
            ui_status = "Installed" if is_installed else "Not Installed"
            ui_color = "GREEN" if is_installed else "RED"
            button_text = "Load" if is_installed else "Download"

            print(f"Model Card: {info['name']}")
            print(f"  Status: {ui_status} ({ui_color})")
            print(f"  Button: {button_text}")
            print()

        # Test 4: SessionRecorderWindow Status Display
        print("=" * 60)
        print("TEST 4: SessionRecorderWindow Model Status")
        print("=" * 60)

        current_model = status['model_name']
        is_current_installed = model_manager.is_model_installed(current_model)

        if status['loaded']:
            recorder_status = f"Model: {current_model} • {status['device']}"
            recorder_color = "GREEN"
        elif status['loading']:
            recorder_status = "Loading model..."
            recorder_color = "ORANGE"
        elif is_current_installed:
            recorder_status = f"Model: {current_model} (ready to load)"
            recorder_color = "ORANGE"
        else:
            recorder_status = f"Model: {current_model} (not downloaded)"
            recorder_color = "RED"

        print(f"SessionRecorder Status: {recorder_status} ({recorder_color})")
        print()

        # Test 5: End-to-End Workflow Status
        print("=" * 60)
        print("TEST 5: End-to-End Workflow Status")
        print("=" * 60)

        print("Current Workflow State:")
        print(f"1. Model Manager Detection: {'PASS' if is_current_installed else 'FAIL'}")
        print(f"2. Whisper Manager Integration: {'PASS' if status.get('model_downloaded') else 'FAIL'}")
        print(f"3. Settings UI Would Show: {'Installed/Load' if is_current_installed else 'Not Installed/Download'}")
        print(f"4. Recorder UI Shows: {recorder_status}")

        workflow_working = (
            is_current_installed == status.get('model_downloaded', False) and
            (recorder_status != f"Model: {current_model} (not downloaded)" if is_current_installed else True)
        )

        print()
        print("=" * 60)
        print(f"UI/BACKEND SYNC STATUS: {'WORKING' if workflow_working else 'BROKEN'}")
        print("=" * 60)

        if workflow_working:
            print("SUCCESS: Model status synchronization is working correctly!")
            print("  - WhisperModelManager properly detects downloaded models")
            print("  - EnhancedWhisperManager integrates with model detection")
            print("  - UI components should display accurate status")
        else:
            print("ERROR: Model status synchronization issues detected:")
            print(f"  - Model Manager says installed: {is_current_installed}")
            print(f"  - Whisper Manager says available: {status.get('model_downloaded', False)}")
            print("  - UI may show incorrect status")

        return workflow_working

    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_model_status_sync()
    print(f"\nModel Status Sync Test: {'PASSED' if success else 'FAILED'}")
    exit(0 if success else 1)