#!/usr/bin/env python3
"""
Test script to verify the critical fixes for the transcription system
"""

import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_imports():
    """Test that all required modules can be imported"""
    print("=" * 50)
    print("Testing Module Imports")
    print("=" * 50)
    
    try:
        # Test core modules
        import transcription_config
        print("✓ transcription_config imported successfully")
        
        import enhanced_whisper_manager
        print("✓ enhanced_whisper_manager imported successfully")
        
        import audio_transcription_bridge
        print("✓ audio_transcription_bridge imported successfully")
        
        import session_storage_manager
        print("✓ session_storage_manager imported successfully")
        
        import whisper_model_downloader
        print("✓ whisper_model_downloader imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_transcription_config():
    """Test transcription configuration"""
    print("\n" + "=" * 50)
    print("Testing Transcription Configuration")
    print("=" * 50)
    
    try:
        from transcription_config import get_transcription_config, setup_transcription_environment
        
        # Test configuration loading
        config = get_transcription_config()
        print(f"✓ Configuration loaded: model={config['model_size']}, device={config['device']}")
        
        # Test device detection
        device, compute_type = config.get_device_config()
        print(f"✓ Device configuration: device={device}, compute_type={compute_type}")
        
        # Test environment setup
        setup_transcription_environment()
        print("✓ Environment setup completed")
        
        return True
        
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return False

def test_model_manager():
    """Test model manager with improved download logic"""
    print("\n" + "=" * 50)
    print("Testing Model Manager")
    print("=" * 50)
    
    try:
        from whisper_model_downloader import WhisperModelManager
        
        manager = WhisperModelManager()
        print("✓ Model manager initialized")
        
        # Test model checking (should not try to download)
        is_tiny_installed = manager.is_model_installed('tiny')
        print(f"✓ Model check completed: tiny model installed = {is_tiny_installed}")
        
        # Test installed models list
        installed_models = manager.get_installed_models()
        print(f"✓ Installed models retrieved: {len(installed_models)} models installed")
        
        return True
        
    except Exception as e:
        print(f"✗ Model manager error: {e}")
        return False

def test_storage_manager():
    """Test session storage manager"""
    print("\n" + "=" * 50)
    print("Testing Session Storage Manager")
    print("=" * 50)
    
    try:
        from session_storage_manager import SessionStorageManager, TranscriptionSegment
        import time
        
        manager = SessionStorageManager()
        print("✓ Storage manager initialized")
        
        # Test session creation
        session_id = manager.start_session({'test': True})
        print(f"✓ Test session started: {session_id}")
        
        # Test segment saving
        test_segment = TranscriptionSegment(
            start_time=time.time(),
            end_time=time.time() + 2,
            text="This is a test segment",
            speaker="TestSpeaker",
            confidence=0.95
        )
        manager.save_transcript_segment(test_segment)
        print("✓ Test segment saved")
        
        # Test session ending
        summary = manager.end_session()
        print(f"✓ Session ended: {summary['stats']['total_segments']} segments")
        
        return True
        
    except Exception as e:
        print(f"✗ Storage manager error: {e}")
        return False

def test_audio_bridge():
    """Test audio transcription bridge (basic functionality)"""
    print("\n" + "=" * 50)
    print("Testing Audio Transcription Bridge")
    print("=" * 50)
    
    try:
        from audio_transcription_bridge import AudioTranscriptionBridge
        
        # Mock audio manager and whisper manager for testing
        class MockAudioManager:
            def __init__(self):
                self.sample_rate = 44100
                self.channels = 2
            def add_audio_data_callback(self, callback):
                pass
        
        class MockWhisperManager:
            def __init__(self):
                self.model_loaded = False
            def add_result_callback(self, callback):
                pass
        
        mock_audio = MockAudioManager()
        mock_whisper = MockWhisperManager()
        
        bridge = AudioTranscriptionBridge(mock_audio, mock_whisper)
        print("✓ Audio bridge initialized")
        
        status = bridge.get_status()
        print(f"✓ Bridge status: streaming={status['streaming']}, callbacks={status['callbacks_registered']}")
        
        return True
        
    except Exception as e:
        print(f"✗ Audio bridge error: {e}")
        return False

def test_faster_whisper_availability():
    """Test if faster-whisper is properly installed"""
    print("\n" + "=" * 50)
    print("Testing Faster-Whisper Availability")
    print("=" * 50)
    
    try:
        import faster_whisper
        print(f"✓ faster-whisper imported: version {getattr(faster_whisper, '__version__', 'unknown')}")
        
        # Test model availability without downloading
        from faster_whisper import WhisperModel
        print("✓ WhisperModel class available")
        
        return True
        
    except ImportError as e:
        print(f"✗ faster-whisper not available: {e}")
        print("  Install with: pip install faster-whisper>=1.0.0")
        return False
    except Exception as e:
        print(f"✗ faster-whisper error: {e}")
        return False

def main():
    """Run all tests"""
    print("🔧 AMANUENSIS TRANSCRIPTION SYSTEM - FIX VERIFICATION")
    print("Testing critical fixes for model downloads, imports, and audio handling")
    
    tests = [
        ("Module Imports", test_imports),
        ("Transcription Config", test_transcription_config),
        ("Faster-Whisper", test_faster_whisper_availability),
        ("Model Manager", test_model_manager),
        ("Storage Manager", test_storage_manager),
        ("Audio Bridge", test_audio_bridge),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"\n✅ {test_name}: PASSED")
            else:
                failed += 1
                print(f"\n❌ {test_name}: FAILED")
        except Exception as e:
            failed += 1
            print(f"\n❌ {test_name}: FAILED with exception: {e}")
    
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Success Rate: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! The critical fixes appear to be working correctly.")
        print("\nNext steps:")
        print("1. Run: python run_enhanced_amanuensis.py")
        print("2. Test model download from the GUI")
        print("3. Test audio recording with different devices")
    else:
        print(f"\n⚠️  {failed} tests failed. Please review the errors above.")
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
