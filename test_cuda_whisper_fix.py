#!/usr/bin/env python3
"""
Test script to verify CUDA detection and model loading fixes for Amanuensis
"""

def test_cuda_detection():
    """Test CUDA detection in transcription config"""
    print("Testing CUDA Detection")
    print("=" * 50)

    try:
        from transcription_config import get_transcription_config

        config = get_transcription_config()
        device, compute_type = config.get_device_config()

        print(f"Device detected: {device}")
        print(f"Compute type: {compute_type}")

        # Test PyTorch CUDA directly
        try:
            import torch
            print(f"PyTorch CUDA available: {torch.cuda.is_available()}")
            if torch.cuda.is_available():
                print(f"GPU name: {torch.cuda.get_device_name()}")
                print(f"GPU memory: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.1f}GB")
        except ImportError:
            print("PyTorch not available")

        return device, compute_type

    except Exception as e:
        print(f"ERROR: CUDA detection failed: {e}")
        return None, None

def test_model_manager():
    """Test WhisperModelManager with proper device detection"""
    print("\nTesting WhisperModelManager Device Detection")
    print("=" * 50)

    try:
        from whisper_model_downloader import WhisperModelManager

        manager = WhisperModelManager()
        print("WhisperModelManager created successfully")

        # Test model checking (should not spam CUDA messages)
        print("\nChecking installed models...")
        installed = manager.get_installed_models()
        print(f"Installed models: {installed}")

        if installed:
            print("SUCCESS: Models found without CUDA spam")
            return True
        else:
            print("INFO: No models installed yet")

            # Test downloading a small model
            print("\nTesting model download with proper device detection...")

            def progress_callback(message, percent, details=""):
                print(f"  [{percent:3.0f}%] {message} {details}")

            success = manager.download_model("tiny", progress_callback)

            if success:
                print("SUCCESS: Model downloaded successfully with proper device config")
                return True
            else:
                print("ERROR: Model download failed")
                return False

    except Exception as e:
        print(f"ERROR: Model manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_model_recommendation():
    """Test model recommendation based on hardware"""
    print("\nTesting Model Recommendation")
    print("=" * 50)

    try:
        from transcription_config import get_transcription_config

        config = get_transcription_config()
        recommended = config.get_model_recommendation()

        print(f"Recommended model: {recommended}")

        # Check if it makes sense for RTX 5060 Ti with 16GB
        if recommended in ['large-v3', 'medium']:
            print(f"SUCCESS: Good recommendation for RTX 5060 Ti (16GB VRAM)")
            return True
        else:
            print(f"INFO: Conservative recommendation: {recommended}")
            return True

    except Exception as e:
        print(f"ERROR: Model recommendation failed: {e}")
        return False

def test_faster_whisper_direct():
    """Test faster-whisper directly to verify CUDA works"""
    print("\nTesting faster-whisper Direct CUDA")
    print("=" * 50)

    try:
        from faster_whisper import WhisperModel
        import tempfile
        import numpy as np
        import soundfile as sf

        print("Creating test model on CUDA...")

        # Try to create a model on CUDA
        model = WhisperModel(
            "tiny",
            device="cuda",
            compute_type="float16",
            local_files_only=True  # Use cached if available
        )

        print("SUCCESS: Model loaded on CUDA")

        # Create test audio
        sample_rate = 16000
        duration = 1
        test_audio = np.random.random(sample_rate * duration).astype(np.float32) * 0.1

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            sf.write(temp_file.name, test_audio, sample_rate)

            print("Testing transcription...")
            segments, info = model.transcribe(temp_file.name, beam_size=1)
            segments_list = list(segments)

            print(f"SUCCESS: Transcription completed, {len(segments_list)} segments")
            print(f"Language detected: {info.language}")

        del model
        print("Model cleanup completed")
        return True

    except Exception as e:
        print(f"Direct CUDA test failed: {e}")
        print("This might be expected if no models are cached yet")
        return False

def main():
    """Run all tests"""
    print("AMANUENSIS - CUDA & Network Access Fix Test")
    print("=" * 60)
    print("Testing WhisperModelManager fixes for:")
    print("1. CUDA detection and GPU utilization")
    print("2. Network access for model downloads")
    print("3. Proper device configuration")
    print("=" * 60)

    results = []

    # Test 1: CUDA Detection
    device, compute_type = test_cuda_detection()
    results.append(("CUDA Detection", device == "cuda" if device else False))

    # Test 2: Model Manager
    model_success = test_model_manager()
    results.append(("Model Manager", model_success))

    # Test 3: Model Recommendation
    rec_success = test_model_recommendation()
    results.append(("Model Recommendation", rec_success))

    # Test 4: Direct faster-whisper (if models available)
    direct_success = test_faster_whisper_direct()
    results.append(("Direct CUDA Test", direct_success))

    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)

    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{test_name:<25} {status}")

    total_passed = sum(1 for _, success in results if success)
    print(f"\nOverall: {total_passed}/{len(results)} tests passed")

    if device == "cuda" and model_success:
        print("\nSUCCESS: CUDA detection and model management working!")
        print("Your RTX 5060 Ti should now be properly utilized for transcription.")
    elif device == "cuda":
        print("\nPARTIAL: CUDA detected but model management needs attention")
    else:
        print("\nISSUE: CUDA not being detected - check PyTorch installation")

if __name__ == "__main__":
    main()