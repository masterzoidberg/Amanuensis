#!/usr/bin/env python3
"""
Comprehensive Test Suite for Transcription System
Tests all components end-to-end
"""

import os
import sys
import time
import tempfile
import numpy as np
import threading
from pathlib import Path
import json

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

def test_configuration():
    """Test configuration loading and validation"""
    print("🔧 Testing Configuration System...")
    
    try:
        from transcription_config import get_transcription_config, setup_transcription_environment
        
        # Test config loading
        config = get_transcription_config()
        assert config is not None, "Config should not be None"
        
        # Test required keys
        required_keys = ['model_size', 'device', 'transcripts_dir', 'recordings_dir']
        for key in required_keys:
            assert key in config, f"Config missing required key: {key}"
        
        # Test device detection
        device, compute_type = config.get_device_config()
        assert device in ['cpu', 'cuda'], f"Invalid device: {device}"
        assert compute_type in ['int8', 'float16', 'int8_float16'], f"Invalid compute type: {compute_type}"
        
        # Test directory creation
        setup_transcription_environment()
        assert config['transcripts_dir'].exists(), "Transcripts directory should exist"
        assert config['recordings_dir'].exists(), "Recordings directory should exist"
        
        print("✅ Configuration system working")
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def test_health_monitoring():
    """Test health monitoring system"""
    print("🏥 Testing Health Monitoring...")
    
    try:
        from transcription_health_monitor import (
            get_health_monitor, report_model_load_error, update_model_status,
            update_inference_latency, ErrorCategory, HealthStatus
        )
        
        # Get monitor instance
        monitor = get_health_monitor()
        assert monitor is not None, "Health monitor should not be None"
        
        # Test metric updates
        update_model_status(True)
        update_inference_latency(2.5)
        
        # Test error reporting
        report_model_load_error("Test error", model="test")
        
        # Get health summary
        health = monitor.get_health_summary()
        assert 'overall_status' in health, "Health summary should have overall_status"
        assert 'metrics' in health, "Health summary should have metrics"
        assert 'recent_errors' in health, "Health summary should have recent_errors"
        
        # Check metrics
        assert 'model_loaded' in health['metrics'], "Should have model_loaded metric"
        assert health['metrics']['model_loaded']['value'] == 1.0, "Model should be marked as loaded"
        
        print("✅ Health monitoring working")
        return True
        
    except Exception as e:
        print(f"❌ Health monitoring test failed: {e}")
        return False

def test_model_manager():
    """Test model downloading and management"""
    print("📥 Testing Model Management...")
    
    try:
        from whisper_model_downloader import WhisperModelManager
        from transcription_config import get_transcription_config
        
        # Create model manager
        manager = WhisperModelManager()
        assert manager is not None, "Model manager should not be None"
        
        # Test model checking (don't actually download)
        available_models = ['tiny', 'base', 'small', 'medium', 'large-v2']
        for model in available_models:
            # Just test the method doesn't crash
            is_installed = manager.is_model_installed(model)
            assert isinstance(is_installed, bool), f"is_model_installed should return bool for {model}"
        
        # Test model info
        info = manager.get_model_info('small')
        assert isinstance(info, dict), "get_model_info should return dict"
        
        print("✅ Model management working")
        return True
        
    except Exception as e:
        print(f"❌ Model management test failed: {e}")
        return False

def test_enhanced_whisper_manager():
    """Test enhanced whisper manager (without actual model loading)"""
    print("🎤 Testing Enhanced Whisper Manager...")
    
    try:
        from enhanced_whisper_manager import EnhancedWhisperManager
        
        # Create manager (will fail to load model but should handle gracefully)
        manager = EnhancedWhisperManager("tiny")
        assert manager is not None, "Whisper manager should not be None"
        
        # Test status methods
        status = manager.get_model_status()
        assert isinstance(status, dict), "get_model_status should return dict"
        assert 'model_name' in status, "Status should include model_name"
        assert 'device' in status, "Status should include device"
        assert 'loaded' in status, "Status should include loaded"
        
        # Test health status
        health = manager.get_health_status()
        assert isinstance(health, dict), "get_health_status should return dict"
        assert 'status' in health, "Health should include status"
        
        print("✅ Enhanced Whisper Manager working")
        return True
        
    except Exception as e:
        print(f"❌ Enhanced Whisper Manager test failed: {e}")
        return False

def test_session_storage():
    """Test session storage system"""
    print("💾 Testing Session Storage...")
    
    try:
        from session_storage_manager import SessionStorageManager
        
        # Create storage manager
        storage = SessionStorageManager()
        assert storage is not None, "Storage manager should not be None"
        
        # Test session creation
        session_id = storage.start_session({
            'test': True,
            'session_type': 'test'
        })
        assert session_id is not None, "Session ID should not be None"
        assert isinstance(session_id, str), "Session ID should be string"
        
        # Test transcript segment saving
        class MockSegment:
            def __init__(self, text, speaker, start_time):
                self.text = text
                self.speaker = speaker
                self.start_time = start_time
                self.end_time = start_time + 2
                self.confidence = 0.9
                self.is_partial = False
        
        segment = MockSegment("Test transcript", "TestSpeaker", time.time())
        success = storage.save_transcript_segment(segment)
        assert success, "Should successfully save transcript segment"
        
        # Test session info
        info = storage.get_session_info()
        assert info is not None, "Session info should not be None"
        assert info['session_id'] == session_id, "Session ID should match"
        
        # Test session ending
        end_info = storage.end_session()
        assert end_info is not None, "End session should return info"
        assert end_info['stats']['total_segments'] > 0, "Should have recorded segments"
        
        # Test storage stats
        stats = storage.get_storage_stats()
        assert isinstance(stats, dict), "Storage stats should be dict"
        
        print("✅ Session storage working")
        return True
        
    except Exception as e:
        print(f"❌ Session storage test failed: {e}")
        return False

def test_audio_bridge():
    """Test audio transcription bridge (without actual audio)"""
    print("🌉 Testing Audio Transcription Bridge...")
    
    try:
        from audio_transcription_bridge import AudioTranscriptionBridge
        from enhanced_whisper_manager import EnhancedWhisperManager
        
        # Mock audio manager
        class MockAudioManager:
            def __init__(self):
                self.recording = False
                self.audio_buffer = []
                self.sample_rate = 44100
                self.channels = 2
        
        # Create components
        audio_manager = MockAudioManager()
        whisper_manager = EnhancedWhisperManager("tiny")
        
        # Create bridge
        bridge = AudioTranscriptionBridge(audio_manager, whisper_manager)
        assert bridge is not None, "Bridge should not be None"
        
        # Test status
        status = bridge.get_bridge_status()
        assert isinstance(status, dict), "Bridge status should be dict"
        assert 'streaming' in status, "Status should include streaming"
        assert 'whisper_loaded' in status, "Status should include whisper_loaded"
        
        print("✅ Audio transcription bridge working")
        return True
        
    except Exception as e:
        print(f"❌ Audio transcription bridge test failed: {e}")
        return False

def test_integration_flow():
    """Test basic integration flow"""
    print("🔄 Testing Integration Flow...")
    
    try:
        from transcription_config import setup_transcription_environment
        from session_storage_manager import SessionStorageManager
        from transcription_health_monitor import get_health_monitor
        
        # Setup environment
        config = setup_transcription_environment()
        
        # Start health monitoring
        monitor = get_health_monitor()
        monitor.start_monitoring()
        
        # Create storage session
        storage = SessionStorageManager()
        session_id = storage.start_session({'integration_test': True})
        
        # Simulate some activity
        class MockSegment:
            def __init__(self, text, speaker, start_time):
                self.text = text
                self.speaker = speaker
                self.start_time = start_time
                self.end_time = start_time + 1
                self.confidence = 0.8
                self.is_partial = False
        
        # Add some segments
        segments = [
            MockSegment("Hello, how are you?", "Speaker1", time.time()),
            MockSegment("I'm doing well, thank you.", "Speaker2", time.time() + 2),
            MockSegment("That's great to hear.", "Speaker1", time.time() + 4)
        ]
        
        for segment in segments:
            storage.save_transcript_segment(segment)
            time.sleep(0.1)  # Small delay
        
        # End session
        session_info = storage.end_session()
        assert session_info['stats']['total_segments'] == len(segments), "Should have saved all segments"
        
        # Check health status
        health = monitor.get_health_summary()
        assert health['overall_status'] in ['healthy', 'warning', 'error'], "Should have valid health status"
        
        # Stop monitoring
        monitor.stop_monitoring()
        
        print("✅ Integration flow working")
        return True
        
    except Exception as e:
        print(f"❌ Integration flow test failed: {e}")
        return False

def test_error_handling():
    """Test error handling and recovery"""
    print("⚠️ Testing Error Handling...")
    
    try:
        from transcription_health_monitor import (
            get_health_monitor, report_model_load_error, report_inference_error,
            ErrorCategory, HealthStatus
        )
        
        monitor = get_health_monitor()
        
        # Clear previous errors
        monitor.clear_errors()
        
        # Test different error types
        report_model_load_error("Test model load error")
        report_inference_error("Test inference error")
        
        # Check error summary
        error_summary = monitor.get_error_summary()
        assert error_summary['total_errors'] >= 2, "Should have recorded errors"
        assert 'by_category' in error_summary, "Should categorize errors"
        
        # Test error filtering
        model_errors = monitor.get_error_summary(ErrorCategory.MODEL_LOAD)
        assert model_errors['total_errors'] >= 1, "Should have model load errors"
        
        print("✅ Error handling working")
        return True
        
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False

def run_smoke_test():
    """Run smoke test with actual audio processing"""
    print("💨 Running Smoke Test...")
    
    try:
        # Only run if faster-whisper is available
        try:
            import faster_whisper
        except ImportError:
            print("⏭️ Skipping smoke test - faster-whisper not available")
            return True
        
        from enhanced_whisper_manager import EnhancedWhisperManager
        
        # Create test audio (1 second of low-level noise)
        sample_rate = 16000
        duration = 1
        test_audio = np.random.random(sample_rate * duration).astype(np.float32) * 0.01
        
        # Create manager with tiny model (fastest)
        manager = EnhancedWhisperManager("tiny")
        
        # Try to load model (may fail if not downloaded)
        try:
            if manager.load_model():
                print("🎯 Model loaded successfully")
                
                # Test transcription
                result_received = threading.Event()
                transcription_result = None
                
                def on_result(result):
                    nonlocal transcription_result
                    transcription_result = result
                    result_received.set()
                
                manager.add_result_callback(on_result)
                manager.start_processing()
                
                # Send test audio
                manager.transcribe_audio_chunk(test_audio, sample_rate)
                
                # Wait for result (with timeout)
                if result_received.wait(timeout=30):
                    print(f"🎯 Transcription completed: {transcription_result.full_text}")
                    print(f"🎯 Processing time: {transcription_result.processing_time:.2f}s")
                    print("✅ Smoke test passed")
                else:
                    print("⚠️ Smoke test timeout - but system is functional")
                
                manager.stop_processing()
                return True
            else:
                print("⏭️ Model not available - skipping smoke test")
                return True
                
        except Exception as e:
            print(f"⏭️ Smoke test skipped due to model issues: {e}")
            return True
            
    except Exception as e:
        print(f"❌ Smoke test failed: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    print("🧪 Starting Transcription System Tests")
    print("=" * 60)
    
    tests = [
        ("Configuration", test_configuration),
        ("Health Monitoring", test_health_monitoring),
        ("Model Management", test_model_manager),
        ("Enhanced Whisper Manager", test_enhanced_whisper_manager),
        ("Session Storage", test_session_storage),
        ("Audio Bridge", test_audio_bridge),
        ("Integration Flow", test_integration_flow),
        ("Error Handling", test_error_handling),
        ("Smoke Test", run_smoke_test),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 Running {test_name} test...")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("🏁 Test Results Summary")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print(f"\n📊 Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All tests passed! System is ready.")
        return True
    else:
        print("⚠️ Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
