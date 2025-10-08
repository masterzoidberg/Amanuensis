#!/usr/bin/env python3
"""
Test script to verify HuggingFace token authentication for pyannote.audio
Run this before launching the full application to verify your token works.
"""

import sys

# Your HuggingFace token (replace with actual token)
HF_TOKEN = "YOUR_HUGGING_FACE_TOKEN_HERE"

def test_pyannote_import():
    """Test if pyannote.audio is installed"""
    print("Testing pyannote.audio installation...")
    try:
        from pyannote.audio import Pipeline
        print("[OK] pyannote.audio is installed")
        return True
    except ImportError as e:
        print(f"[FAIL] pyannote.audio not found: {e}")
        print("  Install with: pip install pyannote.audio")
        return False

def test_token_authentication():
    """Test if the HuggingFace token is valid"""
    print(f"\nTesting HuggingFace token authentication...")
    print(f"Token: {HF_TOKEN[:10]}..." if HF_TOKEN else "No token provided")

    if not HF_TOKEN:
        print("[FAIL] No token configured")
        print("  Please set HF_TOKEN variable in this script")
        return False

    if not HF_TOKEN.startswith("hf_"):
        print("[FAIL] Token should start with 'hf_'")
        return False

    try:
        from pyannote.audio import Pipeline
        print("  Attempting to load model (may download ~500MB on first run)...")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=HF_TOKEN
        )
        print("[OK] Authentication successful!")
        print("[OK] Model loaded successfully")
        print(f"  Pipeline: {pipeline}")
        return True

    except Exception as e:
        error_msg = str(e)
        print(f"[FAIL] Authentication failed: {error_msg}")

        if "401" in error_msg or "authentication" in error_msg.lower():
            print("\n  Possible causes:")
            print("  1. Token is invalid or expired")
            print("  2. You haven't accepted the model conditions")
            print("\n  Steps to fix:")
            print("  - Visit https://huggingface.co/pyannote/speaker-diarization-3.1")
            print("  - Click 'Agree and access repository'")
            print("  - Visit https://huggingface.co/pyannote/segmentation-3.0")
            print("  - Accept conditions there as well")
            print("  - Create a new token at https://huggingface.co/settings/tokens")

        elif "404" in error_msg:
            print("\n  The model was not found. Check your token permissions.")

        elif "offline" in error_msg.lower() or "connection" in error_msg.lower():
            print("\n  Network error. Check your internet connection.")

        return False

def test_gpu_availability():
    """Test if GPU is available for acceleration"""
    print("\nTesting GPU availability...")
    try:
        import torch
        if torch.cuda.is_available():
            print(f"[OK] GPU available: {torch.cuda.get_device_name(0)}")
            print(f"  CUDA version: {torch.version.cuda}")
            memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"  Total VRAM: {memory:.1f} GB")
            return True
        else:
            print("[WARN] No GPU detected - will use CPU (slower)")
            return False
    except Exception as e:
        print(f"[FAIL] Error checking GPU: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("HuggingFace Token Test for Pyannote Speaker Diarization")
    print("=" * 60)

    # Test 1: Check installation
    if not test_pyannote_import():
        sys.exit(1)

    # Test 2: Check GPU
    test_gpu_availability()

    # Test 3: Test authentication
    if not test_token_authentication():
        sys.exit(1)

    print("\n" + "=" * 60)
    print("[SUCCESS] All tests passed!")
    print("=" * 60)
    print("\nYour HuggingFace token is working correctly.")
    print("You can now use speaker diarization in Amanuensis V2.")
    print("\nNext steps:")
    print("1. Open Amanuensis V2")
    print("2. Go to Settings > Audio")
    print("3. Enable 'pyannote.audio speaker diarization'")
    print("4. Paste your token and click 'Validate Token'")
    print("5. Click 'Apply' to save")

if __name__ == "__main__":
    main()
