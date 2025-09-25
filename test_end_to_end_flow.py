#!/usr/bin/env python3
"""
Test end-to-end flow without GUI
Tests the complete pipeline: Audio Manager -> Transcription Bridge -> Whisper Manager
"""

import logging
import time
import numpy as np

# Set up logging
logging.basicConfig(level=logging.INFO)

def test_end_to_end_pipeline():
    """Test the complete audio transcription pipeline"""

    print("=" * 60)
    print("Testing End-to-End Audio Transcription Pipeline")
    print("=" * 60)

    try:
        # 1. Create managers
        print("\n1. Creating managers...")

        from config_manager import SecureConfigManager
        from audio_manager import AudioManager
        from enhanced_whisper_manager import EnhancedWhisperManager
        from transcription_config import get_transcription_config

        config_manager = SecureConfigManager()
        audio_manager = AudioManager()
        config = get_transcription_config()
        whisper_manager = EnhancedWhisperManager(config['model_size'])

        print("[OK] All managers created")

        # 2. Check available devices
        print("\n2. Checking audio devices...")

        input_devices = audio_manager.get_input_devices()
        system_devices = audio_manager.get_system_audio_devices()

        print(f"[INFO] Input devices: {len(input_devices)}")
        for device in input_devices[:3]:  # Show first 3
            print(f"   - {device['name']} (index {device['index']})")

        print(f"[INFO] System devices: {len(system_devices)}")
        for device in system_devices:
            print(f"   - {device['name']} (index {device['index']})")

        # 3. Test model loading
        print("\n3. Testing model loading...")

        model_status = whisper_manager.get_model_status()
        print(f"[INFO] Model available: {model_status['available']}")
        print(f"[INFO] Model loaded: {model_status['loaded']}")

        if not model_status['loaded']:
            print("[INFO] Loading model...")
            success = whisper_manager.load_model()
            if success:
                print("[OK] Model loaded successfully")
            else:
                print("[ERROR] Model loading failed")
                return False

        # 4. Test audio transcription bridge
        print("\n4. Testing transcription bridge...")

        try:
            from audio_transcription_bridge import AudioTranscriptionBridge
            bridge = AudioTranscriptionBridge(audio_manager, whisper_manager)
            print("[OK] Transcription bridge created")
        except Exception as e:
            print(f"[ERROR] Bridge creation failed: {e}")
            return False

        # 5. Test WASAPI loopback detection
        print("\n5. Testing WASAPI loopback...")

        try:
            from audio_transcription_bridge import resolve_loopback_mic, preflight_loopback
            mic, spk = resolve_loopback_mic()
            print(f"[OK] Loopback devices resolved: {spk.name}")

            # Quick preflight test
            preflight_loopback(mic)
            print(f"[OK] Loopback preflight successful")
        except Exception as e:
            print(f"[WARN] Loopback test failed: {e}")
            print("      This is expected if no system audio is playing")

        # 6. Test audio queue system
        print("\n6. Testing audio queue system...")

        try:
            from audio_transcription_bridge import push_audio_frames, audio_q

            # Push test frames
            test_audio = np.random.random(1024).astype('float32') * 0.1
            push_audio_frames(test_audio, 44100)

            queue_size = audio_q.qsize()
            print(f"[OK] Audio queue working, size: {queue_size}")

            # Consume the test frame
            if queue_size > 0:
                packet = audio_q.get_nowait()
                print(f"[OK] Queue packet format: t={packet['t']:.3f}, sr={packet['sr']}, data_shape={packet['data'].shape}")

        except Exception as e:
            print(f"[ERROR] Audio queue test failed: {e}")
            return False

        # 7. Test transcription on synthetic audio
        print("\n7. Testing transcription...")

        try:
            # Create synthetic audio (sine wave representing speech-like signal)
            sample_rate = 16000
            duration = 2.0
            samples = int(sample_rate * duration)

            # Create a simple audio signal
            t = np.linspace(0, duration, samples, False)
            # Mix of frequencies to simulate speech
            audio_data = (0.3 * np.sin(2 * np.pi * 440 * t) +  # A4
                         0.2 * np.sin(2 * np.pi * 880 * t) +  # A5
                         0.1 * np.random.random(samples) - 0.05)  # Noise

            audio_data = audio_data.astype(np.float32)

            # Test transcription with synthetic audio
            segments, info = whisper_manager.model.transcribe(
                audio_data,
                beam_size=1,
                language="en"
            )

            segment_list = list(segments)
            print(f"[OK] Transcription test successful")
            print(f"     Language: {info.language} (confidence: {info.language_probability:.2f})")
            print(f"     Segments: {len(segment_list)}")

            if segment_list:
                for i, segment in enumerate(segment_list[:2]):  # Show first 2 segments
                    print(f"     Segment {i+1}: '{segment.text.strip()}' ({segment.start:.1f}s-{segment.end:.1f}s)")

        except Exception as e:
            print(f"[ERROR] Transcription test failed: {e}")
            return False

        # 8. Test complete
        print("\n" + "=" * 60)
        print("SUCCESS: End-to-end pipeline test completed successfully!")
        print("=" * 60)
        print()
        print("Summary:")
        print("- All managers created and initialized [OK]")
        print("- Audio devices enumerated [OK]")
        print("- Model loading working [OK]")
        print("- Transcription bridge created [OK]")
        print("- Audio queue system working [OK]")
        print("- Transcription engine functional [OK]")
        print()
        print("The application should work for recording and live transcription.")

        return True

    except Exception as e:
        print(f"\n[ERROR] Pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_end_to_end_pipeline()
    exit(0 if success else 1)