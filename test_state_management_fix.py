#!/usr/bin/env python3
"""
Test State Management Fix
Verify that device configuration persists from preflight testing to recording initialization
"""

import time
from logger_config import get_logger

def test_state_persistence():
    """Test that device state persists from preflight to recording"""
    logger = get_logger('test_state_fix')
    logger.info("Testing state management fix...")

    print("DEVICE STATE PERSISTENCE TEST")
    print("Testing: Preflight success -> Recording initialization")
    print("=" * 60)

    try:
        from audio_manager import AudioManager
        audio_manager = AudioManager()

        # Phase 1: Device Configuration (simulate Settings window workflow)
        print("PHASE 1: Device Configuration")
        print("-" * 30)

        # Set microphone device
        success, msg = audio_manager.set_microphone_device(0)
        print(f"Set microphone: {success} - {msg}")
        if not success:
            return False

        # Set system audio device (this is where state was getting lost)
        success, msg = audio_manager.set_system_audio_device("Speakers (Logi Z407)")
        print(f"Set system audio: {success} - {msg}")
        if not success:
            return False

        # Set system audio mode (this was clearing the device!)
        success, msg = audio_manager.set_system_audio_mode("soundcard_loopback")
        print(f"Set system mode: {success} - {msg}")
        if not success:
            return False

        # Check state after configuration
        print(f"Device state after config:")
        print(f"  Microphone: {audio_manager.microphone_device.name if audio_manager.microphone_device else 'None'}")
        print(f"  System Audio: {audio_manager.system_audio_device.name if audio_manager.system_audio_device else 'None'}")
        print(f"  System Mode: {getattr(audio_manager, 'system_audio_mode', 'None')}")

        # This should now pass (previously failed with "System audio device not configured")
        if audio_manager.system_audio_device is None:
            print("FAIL: System audio device cleared by mode setting (OLD BUG)")
            return False
        else:
            print("PASS: System audio device preserved after mode setting (FIXED)")

        # Phase 2: Preflight Testing
        print("\nPHASE 2: Preflight Testing")
        print("-" * 30)

        # Simulate preflight test (from Settings window)
        try:
            from audio_transcription_bridge import resolve_loopback_mic, preflight_loopback
            mic, spk = resolve_loopback_mic()
            preflight_loopback(mic)
            print(f"PASS: Preflight successful for: {spk.name}")
        except Exception as e:
            print(f"FAIL: Preflight failed: {e}")
            return False

        # Check state persistence after preflight
        print(f"Device state after preflight:")
        print(f"  Microphone: {audio_manager.microphone_device.name if audio_manager.microphone_device else 'None'}")
        print(f"  System Audio: {audio_manager.system_audio_device.name if audio_manager.system_audio_device else 'None'}")
        print(f"  System Mode: {getattr(audio_manager, 'system_audio_mode', 'None')}")

        # Phase 3: Recording Initialization (the critical test)
        print("\nPHASE 3: Recording Initialization")
        print("-" * 30)

        # This is where the original error occurred
        success, msg = audio_manager.start_recording()
        print(f"Start recording: {success} - {msg}")

        if not success:
            if "System audio device not configured" in msg:
                print("FAIL: Original state management bug still present")
                return False
            else:
                print(f"Different issue: {msg}")
                return False

        print("PASS: Recording started successfully - state was preserved!")

        # Let it run briefly then stop
        time.sleep(1)
        audio_manager.stop_recording()
        print("Recording stopped successfully")

        return True

    except Exception as e:
        print(f"FAIL: Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_mode_specific_validation():
    """Test that validation works properly for different modes"""
    print("\n" + "=" * 60)
    print("MODE-SPECIFIC VALIDATION TEST")
    print("=" * 60)

    try:
        from audio_manager import AudioManager
        audio_manager = AudioManager()

        # Test 1: soundcard_loopback mode (should require device)
        print("\nTest 1: soundcard_loopback mode")
        audio_manager.set_microphone_device(0)
        audio_manager.set_system_audio_device("Speakers (Logi Z407)")
        audio_manager.set_system_audio_mode("soundcard_loopback")

        success, msg = audio_manager.start_recording()
        if success:
            audio_manager.stop_recording()
            print("PASS: soundcard_loopback mode accepts configured device")
        else:
            print(f"FAIL: soundcard_loopback mode rejected configured device: {msg}")
            return False

        # Test 2: mic_only mode (should not require system audio device)
        print("\nTest 2: mic_only mode")
        audio_manager.set_system_audio_mode("mic_only")
        # Note: system_audio_device should be None for mic_only

        success, msg = audio_manager.start_recording()
        if success:
            audio_manager.stop_recording()
            print("PASS: mic_only mode works without system audio device")
        else:
            print(f"FAIL: mic_only mode failed: {msg}")
            return False

        return True

    except Exception as e:
        print(f"FAIL: Mode validation test failed: {e}")
        return False

def main():
    """Run all state management tests"""
    print("STATE MANAGEMENT FIX VERIFICATION")
    print("Fix: Device configuration persists from preflight to recording")
    print()

    tests = [
        ("State Persistence", test_state_persistence),
        ("Mode-Specific Validation", test_mode_specific_validation),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            print(f"\nRunning: {test_name}")
            if test_func():
                passed += 1
                print(f"PASS: {test_name}")
            else:
                failed += 1
                print(f"FAIL: {test_name}")
        except Exception as e:
            failed += 1
            print(f"FAIL: {test_name} - Exception: {e}")

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print(f"Success Rate: {passed/(passed+failed)*100:.1f}%")

    if failed == 0:
        print("\nALL TESTS PASSED!")
        print("The state management issue has been RESOLVED!")
        print("\nFix Summary:")
        print("1. soundcard_loopback mode no longer clears system_audio_device")
        print("2. Mode-aware validation handles different audio modes properly")
        print("3. Preflight device configuration persists to recording phase")
        print("4. Dual recording loops handle both mic+loopback and mic-only modes")
    else:
        print(f"\n{failed} tests failed - state management may need additional work")

    return failed == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)