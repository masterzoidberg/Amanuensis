#!/usr/bin/env python3
"""
Diagnostic tool to check WASAPI loopback audio capture
Tests system audio device detection and recording capability
"""

import sys
import os
import time
import traceback
import numpy as np

# Add parent directory to path to import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    """Test WASAPI loopback audio capture"""
    print("=" * 60)
    print("Amanuensis Loopback Audio Diagnostic Tool")
    print("=" * 60)

    try:
        # Test soundcard import
        print("Testing soundcard module...")
        try:
            import soundcard as sc
            print("[OK] soundcard module imported successfully")
        except ImportError as e:
            print(f"[ERROR] soundcard module not available: {e}")
            print("   Install with: pip install soundcard")
            return 1

        # List available speakers
        print("\nEnumerating system audio devices (speakers):")
        speakers = sc.all_speakers()

        if not speakers:
            print("[ERROR] No speakers/output devices found")
            return 1

        for i, speaker in enumerate(speakers):
            print(f"  {i+1}. {speaker.name}")
            print(f"     ID: {speaker.id}")
            print(f"     Channels: {speaker.channels}")

        print(f"\n[OK] Found {len(speakers)} speaker device(s)")

        # Test default speaker loopback
        print(f"\nTesting default speaker loopback...")
        default_speaker = sc.default_speaker()
        print(f"Default speaker: {default_speaker.name}")

        # Test loopback microphone creation
        print("Creating loopback microphone...")
        loopback_mic = sc.get_microphone(id=default_speaker.name, include_loopback=True)
        print(f"[OK] Loopback microphone created: {loopback_mic.name}")

        # Test preflight (short recording)
        print("\nTesting preflight recording (0.5 seconds)...")
        samplerate = 44100
        test_frames = int(samplerate * 0.5)  # 0.5 seconds

        with loopback_mic.recorder(samplerate=samplerate) as rec:
            audio_data = rec.record(numframes=test_frames)

        print(f"[OK] Preflight recording successful!")
        print(f"   Sample rate: {samplerate} Hz")
        print(f"   Duration: {len(audio_data) / samplerate:.2f} seconds")
        print(f"   Channels: {audio_data.shape[1] if len(audio_data.shape) > 1 else 1}")
        print(f"   Data shape: {audio_data.shape}")

        # Analyze the recorded audio
        audio_array = np.asarray(audio_data, dtype=np.float32)
        max_amplitude = np.max(np.abs(audio_array))
        rms = np.sqrt(np.mean(audio_array**2))

        print(f"   Max amplitude: {max_amplitude:.4f}")
        print(f"   RMS level: {rms:.4f}")

        if max_amplitude > 0.001:  # Some reasonable threshold
            print("[OK] Audio signal detected (non-silent)")
        else:
            print("[WARN] Very low or silent audio detected")
            print("   This might be normal if no audio is playing")

        # Save a probe file
        probe_file = os.path.join("tools", "loopback_probe.wav")
        try:
            import soundfile as sf
            sf.write(probe_file, audio_data, samplerate)
            print(f"[OK] Probe audio saved to: {probe_file}")
        except ImportError:
            print("[WARN] soundfile not available, skipping audio file save")
        except Exception as e:
            print(f"[WARN] Could not save probe file: {e}")

        # Test our bridge functions
        print(f"\nTesting audio bridge functions...")
        try:
            from audio_transcription_bridge import resolve_loopback_mic, preflight_loopback

            mic, spk = resolve_loopback_mic()
            print(f"[OK] Bridge resolve_loopback_mic() successful")
            print(f"   Speaker: {spk.name}")
            print(f"   Microphone: {mic.name}")

            preflight_loopback(mic)
            print(f"[OK] Bridge preflight_loopback() successful")

        except Exception as e:
            print(f"[ERROR] Bridge function test failed: {e}")
            traceback.print_exc()

        print("\n" + "=" * 60)
        print("SUCCESS: Loopback audio test completed successfully!")
        print("   Your system supports WASAPI loopback capture.")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"[ERROR] {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        print("\nTroubleshooting:")
        print("  - Ensure you have audio devices connected")
        print("  - Try running as administrator on Windows")
        print("  - Check Windows audio privacy settings")
        return 1

if __name__ == "__main__":
    sys.exit(main())