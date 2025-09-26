#!/usr/bin/env python3
"""
Test WASAPI COM Initialization Fix
Verify that the 0x800401f0 error is resolved with proper COM initialization
"""

import sys
import threading
import time
from logger_config import get_logger

def test_com_initialization():
    """Test COM initialization functionality"""
    logger = get_logger('test_com_fix')
    logger.info("Testing COM initialization fix for WASAPI loopback...")

    print("=" * 60)
    print("TEST: COM Initialization")
    print("=" * 60)

    try:
        from com_initializer import initialize_com_for_audio, is_com_initialized, com_context

        print(f"Platform: {sys.platform}")
        print(f"Initial COM state: {is_com_initialized()}")

        # Test 1: Direct COM initialization
        success = initialize_com_for_audio()
        print(f"COM initialization result: {success}")
        print(f"COM initialized after init: {is_com_initialized()}")

        # Test 2: Context manager
        with com_context() as com_ok:
            print(f"COM context manager result: {com_ok}")
            print(f"COM state inside context: {is_com_initialized()}")

        print(f"COM state after context: {is_com_initialized()}")
        print("PASS: COM initialization tests passed")
        return True

    except Exception as e:
        print(f"FAIL: COM initialization test failed: {e}")
        return False

def test_loopback_with_com():
    """Test loopback functionality with COM initialization"""
    logger = get_logger('test_com_fix')
    logger.info("Testing loopback functionality with COM fix...")

    print("\n" + "=" * 60)
    print("TEST: WASAPI Loopback with COM Fix")
    print("=" * 60)

    try:
        # Initialize COM first
        from com_initializer import initialize_com_for_audio
        if not initialize_com_for_audio():
            print("FAIL: Failed to initialize COM")
            return False

        print("PASS: COM initialized successfully")

        # Test loopback device resolution
        from audio_transcription_bridge import resolve_loopback_mic, preflight_loopback
        print("Resolving loopback microphone...")

        mic, spk = resolve_loopback_mic()
        print(f"PASS: Loopback mic resolved: {spk.name}")

        # Test preflight (250ms recording test)
        print("Testing loopback preflight...")
        preflight_loopback(mic)
        print("PASS: Loopback preflight successful")

        return True

    except Exception as e:
        error_str = str(e)
        print(f"FAIL: Loopback test failed: {error_str}")

        # Check for specific error patterns
        if "0x800401f0" in error_str:
            print("  → This is the COM initialization error (should be fixed)")
            print("  → Try running as administrator if the error persists")
        elif "0x80070005" in error_str:
            print("  → This is an access denied error")
            print("  → Check audio device permissions or try different device")
        elif "device not found" in error_str.lower():
            print("  → Audio device not accessible")
            print("  → Ensure audio device is not exclusively used by another app")

        return False

def test_threading_com():
    """Test COM initialization across multiple threads"""
    logger = get_logger('test_com_fix')
    logger.info("Testing COM initialization across threads...")

    print("\n" + "=" * 60)
    print("TEST: Multi-Thread COM Initialization")
    print("=" * 60)

    results = []

    def thread_worker(thread_id):
        """Worker function for thread testing"""
        try:
            from com_initializer import initialize_com_for_audio, is_com_initialized

            print(f"Thread {thread_id}: Starting")
            initial_state = is_com_initialized()

            success = initialize_com_for_audio()
            final_state = is_com_initialized()

            print(f"Thread {thread_id}: COM init {success}, state {initial_state}->{final_state}")

            # Try to use loopback (this is where COM errors typically occur)
            from audio_transcription_bridge import resolve_loopback_mic
            mic, spk = resolve_loopback_mic()
            print(f"Thread {thread_id}: PASS Loopback successful")

            results.append(True)
        except Exception as e:
            print(f"Thread {thread_id}: FAIL Failed - {e}")
            results.append(False)

    # Start multiple threads
    threads = []
    for i in range(3):
        t = threading.Thread(target=thread_worker, args=(i,), daemon=True)
        threads.append(t)
        t.start()

    # Wait for all threads
    for t in threads:
        t.join(timeout=10)

    success_count = sum(results)
    print(f"Thread test results: {success_count}/{len(results)} threads succeeded")

    return success_count == len(results)

def main():
    """Run all COM initialization tests"""
    print("WASAPI COM INITIALIZATION FIX TEST")
    print("Testing fix for Windows COM error 0x800401f0")
    print()

    tests = [
        ("COM Initialization", test_com_initialization),
        ("WASAPI Loopback", test_loopback_with_com),
        ("Multi-Thread COM", test_threading_com),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            print(f"\nRunning: {test_name}")
            if test_func():
                passed += 1
                print(f"PASS {test_name}: PASSED")
            else:
                failed += 1
                print(f"FAIL {test_name}: FAILED")
        except Exception as e:
            failed += 1
            print(f"FAIL {test_name}: FAILED with exception: {e}")

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print(f"Success Rate: {passed/(passed+failed)*100:.1f}%")

    if failed == 0:
        print("\nALL TESTS PASSED!")
        print("The COM initialization fix should resolve WASAPI loopback issues.")
        print("\nNext steps:")
        print("1. Test device buttons in Settings -> Audio Devices")
        print("2. Verify loopback capture works in main recording interface")
        print("3. Test with different audio output devices")
    else:
        print(f"\n{failed} tests failed.")
        if sys.platform != "win32":
            print("Note: Some failures expected on non-Windows platforms.")
        else:
            print("Try running as administrator if COM initialization fails.")

    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)