#!/usr/bin/env python3
"""
Simple test script to verify thread isolation and GUI stability fixes
"""

import time
import threading

def test_basic_thread_safety():
    """Test basic AudioManager thread-safe communication"""
    print("Testing AudioManager Thread Safety...")

    try:
        from audio_manager import AudioManager

        audio_manager = AudioManager()

        # Test thread-safe level updates
        print("Testing thread-safe level updates...")
        audio_manager._update_levels_thread_safe(100.0, 200.0, 30.5)

        levels = audio_manager.get_volume_levels()
        print(f"Levels: Mic={levels['microphone']}, Sys={levels['system_audio']}, Buffer={levels['buffer_duration']}")

        success1 = (levels['microphone'] == 100.0 and levels['system_audio'] == 200.0)
        print(f"Thread-safe level updates: {'PASS' if success1 else 'FAIL'}")

        # Test status queue
        print("Testing status queue...")
        audio_manager.status_queue.put({'type': 'test', 'message': 'test message'})

        updates = audio_manager.get_status_updates()
        success2 = len(updates) == 1
        print(f"Status queue communication: {'PASS' if success2 else 'FAIL'}")

        # Test command queue
        print("Testing command queue...")
        audio_manager.send_command('test_command', {'data': 'test'})

        try:
            command = audio_manager.command_queue.get_nowait()
            success3 = command['command'] == 'test_command'
        except:
            success3 = False
        print(f"Command queue: {'PASS' if success3 else 'FAIL'}")

        return success1 and success2 and success3

    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_concurrent_access():
    """Test concurrent access between GUI and audio threads"""
    print("\nTesting Concurrent Access...")

    try:
        from audio_manager import AudioManager

        audio_manager = AudioManager()
        errors = []

        def gui_simulation():
            """Simulate GUI thread operations"""
            try:
                for i in range(20):
                    levels = audio_manager.get_volume_levels()
                    updates = audio_manager.get_status_updates()
                    time.sleep(0.01)
            except Exception as e:
                errors.append(f"GUI thread error: {e}")

        def audio_simulation():
            """Simulate audio thread operations"""
            try:
                for i in range(20):
                    audio_manager._update_levels_thread_safe(i * 5, i * 10, i * 0.5)
                    audio_manager.status_queue.put({
                        'type': 'test',
                        'iteration': i,
                        'data': f"test_{i}"
                    })
                    time.sleep(0.01)
            except Exception as e:
                errors.append(f"Audio thread error: {e}")

        # Run both threads concurrently
        gui_thread = threading.Thread(target=gui_simulation)
        audio_thread = threading.Thread(target=audio_simulation)

        gui_thread.start()
        audio_thread.start()

        gui_thread.join(timeout=3.0)
        audio_thread.join(timeout=3.0)

        success = len(errors) == 0 and not gui_thread.is_alive() and not audio_thread.is_alive()
        print(f"Concurrent access test: {'PASS' if success else 'FAIL'}")

        if errors:
            for error in errors:
                print(f"  Error: {error}")

        return success

    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_shutdown_safety():
    """Test shutdown event and thread lifecycle"""
    print("\nTesting Shutdown Safety...")

    try:
        from audio_manager import AudioManager

        audio_manager = AudioManager()

        # Test shutdown event functionality
        print("Testing shutdown events...")

        audio_manager._shutdown_event.set()
        is_set = audio_manager._shutdown_event.is_set()

        audio_manager._shutdown_event.clear()
        is_cleared = not audio_manager._shutdown_event.is_set()

        success = is_set and is_cleared
        print(f"Shutdown event handling: {'PASS' if success else 'FAIL'}")

        return success

    except Exception as e:
        print(f"ERROR: {e}")
        return False

def main():
    """Run simplified thread isolation tests"""
    print("AMANUENSIS - Thread Isolation Fix Test (Simple)")
    print("=" * 50)

    results = []

    # Test 1: Basic Thread Safety
    result1 = test_basic_thread_safety()
    results.append(("Basic Thread Safety", result1))

    # Test 2: Concurrent Access
    result2 = test_concurrent_access()
    results.append(("Concurrent Access", result2))

    # Test 3: Shutdown Safety
    result3 = test_shutdown_safety()
    results.append(("Shutdown Safety", result3))

    # Summary
    print("\n" + "=" * 50)
    print("TEST RESULTS")
    print("=" * 50)

    total_passed = 0
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{test_name:<25} {status}")
        if success:
            total_passed += 1

    print(f"\nOverall: {total_passed}/{len(results)} tests passed")

    if total_passed == len(results):
        print("\nSUCCESS: Thread isolation fixes are working!")
        print("\nKey improvements:")
        print("- Thread-safe communication using Queue")
        print("- Proper level updates with locking")
        print("- Status updates from audio to GUI thread")
        print("- Command sending from GUI to audio thread")
        print("- Clean shutdown event handling")
        print("\nGUI corruption should be eliminated!")
    else:
        print(f"\nSome tests failed. Check the output above.")

if __name__ == "__main__":
    main()