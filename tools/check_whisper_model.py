#!/usr/bin/env python3
"""
Diagnostic tool to check Whisper model loading
Tests model loading with current configuration and reports status
"""

import sys
import os
import traceback

# Add parent directory to path to import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    """Test Whisper model loading with current configuration"""
    print("=" * 60)
    print("Amanuensis Whisper Model Diagnostic Tool")
    print("=" * 60)

    try:
        # Import configuration
        from transcription_config import get_transcription_config, MODEL_SIZE, MODEL_DEVICE, MODEL_COMPUTE
        from enhanced_whisper_manager import load_whisper_model, decide_device, decide_compute

        print(f"Configuration loaded:")
        print(f"  Model Size: {MODEL_SIZE}")
        print(f"  Device: {MODEL_DEVICE}")
        print(f"  Compute: {MODEL_COMPUTE}")
        print()

        # Check resolved configuration
        device = decide_device()
        compute = decide_compute(device)

        print(f"Resolved configuration:")
        print(f"  Device: {device}")
        print(f"  Compute: {compute}")
        print()

        # Test model loading
        print("Testing model loading...")
        model = load_whisper_model()

        print("[OK] SUCCESS: Model loaded successfully!")
        print(f"   Model: {MODEL_SIZE}")
        print(f"   Device: {device}")
        print(f"   Compute: {compute}")

        # Test model with a small inference
        print("\nTesting inference...")
        import numpy as np

        # Create 1 second of silence
        test_audio = np.zeros(16000, dtype=np.float32)

        segments, info = model.transcribe(
            test_audio,
            beam_size=1,
            language="en"
        )

        # Consume segments
        segment_list = list(segments)

        print("[OK] SUCCESS: Model inference test passed!")
        print(f"   Language detected: {info.language}")
        print(f"   Segments processed: {len(segment_list)}")

        print("\n" + "=" * 60)
        print("SUCCESS: All tests passed! Whisper model is working correctly.")
        print("=" * 60)

        return 0

    except ImportError as e:
        print(f"[ERROR] IMPORT ERROR: {e}")
        print("   Make sure all required dependencies are installed:")
        print("   pip install -r requirements.txt")
        return 1

    except Exception as e:
        print(f"[ERROR] {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())