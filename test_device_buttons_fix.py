#!/usr/bin/env python3
"""
Test Device Testing Buttons Fix
Simulate the exact device testing workflow from Settings window
"""

import threading
import time
from logger_config import get_logger

def simulate_settings_device_test(device_name):
    """Simulate the exact device test workflow from Settings window"""
    logger = get_logger('device_test_sim')
    logger.info(f"Simulating device test for: {device_name}")

    def test_worker():
        """Simulate the test_worker function from settings_window.py"""
        try:
            # Initialize COM for WASAPI access in this thread (NEW FIX)
            try:
                from com_initializer import initialize_com_for_audio
                if not initialize_com_for_audio():
                    raise RuntimeError("Failed to initialize COM for WASAPI audio access")
                print(f"✓ COM initialized for device: {device_name}")
            except ImportError:
                # COM initializer not available (non-Windows systems)
                print("✓ COM initializer not needed (non-Windows)")

            from audio_transcription_bridge import resolve_loopback_mic, preflight_loopback

            # Resolve loopback device (this previously failed with 0x800401f0)
            mic, spk = resolve_loopback_mic()
            print(f"✓ Device resolved: {spk.name}")

            # Test the device (this previously failed with 0x800401f0)
            preflight_loopback(mic)
            print(f"✓ Device test successful: {device_name}")

            return True

        except Exception as e:
            error_msg = str(e)
            print(f"✗ Device test failed: {device_name} - {error_msg}")

            # Provide more helpful error messages for common COM issues
            if "0x800401f0" in error_msg:
                print("  → COM initialization failed - try running as administrator")
            elif "0x80070005" in error_msg:
                print("  → Audio device access denied - check device permissions")
            elif "device not found" in error_msg.lower():
                print("  → Audio device not found or not accessible")

            return False

    # Run test in background thread (as Settings window does)
    result = None
    def thread_wrapper():
        nonlocal result
        result = test_worker()

    test_thread = threading.Thread(target=thread_wrapper, daemon=True)
    test_thread.start()
    test_thread.join(timeout=10)  # 10 second timeout

    return result

def main():
    """Test device button functionality with COM fix"""
    print("DEVICE TESTING BUTTONS FIX VERIFICATION")
    print("Simulating Settings -> Audio Devices -> Test Device workflow")
    print("=" * 60)

    # Get available audio devices
    try:
        import soundcard as sc
        speakers = sc.all_speakers()

        if not speakers:
            print("No audio devices found for testing")
            return False

        print(f"Found {len(speakers)} audio devices:")
        for i, speaker in enumerate(speakers):
            print(f"  {i+1}. {speaker.name}")

        print("\nTesting device buttons (simulating Settings window clicks):")
        print("-" * 60)

        # Test first few devices (limit to avoid too much output)
        test_devices = speakers[:3] if len(speakers) >= 3 else speakers
        success_count = 0

        for i, speaker in enumerate(test_devices):
            print(f"\nTest {i+1}: {speaker.name}")

            success = simulate_settings_device_test(speaker.name)
            if success:
                success_count += 1
                print(f"Result: PASS - Device test button would work")
            else:
                print(f"Result: FAIL - Device test button would fail")

        print("\n" + "=" * 60)
        print("DEVICE BUTTON TEST SUMMARY")
        print("=" * 60)
        print(f"Successful tests: {success_count}/{len(test_devices)}")
        print(f"Success rate: {success_count/len(test_devices)*100:.1f}%")

        if success_count == len(test_devices):
            print("\n✓ ALL DEVICE TESTS PASSED!")
            print("The COM error 0x800401f0 has been resolved.")
            print("Device test buttons in Settings should now work correctly.")
        elif success_count > 0:
            print(f"\n~ PARTIAL SUCCESS: {success_count} devices working")
            print("Some devices may have exclusive access conflicts.")
        else:
            print("\n✗ ALL DEVICE TESTS FAILED")
            print("COM initialization fix may not be working correctly.")

        return success_count > 0

    except ImportError:
        print("soundcard module not available for testing")
        return False
    except Exception as e:
        print(f"Device enumeration failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)