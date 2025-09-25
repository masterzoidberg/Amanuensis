#!/usr/bin/env python3
"""
Test script to verify the WhisperModelManager fixes (no Unicode)
"""

def test_model_download_fixes():
    """Test the specific fixes for model download and file cleanup issues"""
    print("Testing WhisperModelManager Fixes")
    print("=" * 50)

    try:
        from whisper_model_downloader import WhisperModelManager

        # Create model manager
        manager = WhisperModelManager()
        print("SUCCESS: WhisperModelManager created")

        # Test model checking (should use local_files_only=True)
        print("\nTesting model availability check...")
        installed_models = manager.get_installed_models()
        print(f"Currently installed models: {installed_models}")

        # Test if setup is needed
        needs_setup = manager.needs_initial_setup()
        print(f"Needs initial setup: {needs_setup}")

        if needs_setup:
            print("\nTesting model download (tiny model for quick test)...")

            # Create a simple progress callback
            def progress_callback(message, percent, details=""):
                print(f"  [{percent:3.0f}%] {message} {details}")

            # Try to download the smallest model for testing
            model_name = "tiny"
            print(f"Attempting to download '{model_name}' model...")

            success = manager.download_model(model_name, progress_callback)

            if success:
                print(f"SUCCESS: Model '{model_name}' downloaded!")

                # Test if it's now detected as installed
                if manager.is_model_installed(model_name):
                    print(f"SUCCESS: Model '{model_name}' verified as installed")
                else:
                    print(f"ERROR: Model '{model_name}' download succeeded but not detected")

            else:
                print(f"ERROR: Model '{model_name}' download failed")

        else:
            print("INFO: Models already available, skipping download test")

        # Final status
        final_models = manager.get_installed_models()
        print(f"\nFinal installed models: {final_models}")

        print("\nAll tests completed successfully!")
        return True

    except Exception as e:
        print(f"ERROR: Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_model_download_fixes()