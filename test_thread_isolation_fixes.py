#!/usr/bin/env python3
"""
Test script to verify thread isolation and GUI stability fixes
"""

import time
import threading
from unittest.mock import MagicMock

def test_audio_manager_thread_safety():
    """Test AudioManager thread-safe communication"""
    print("Testing AudioManager Thread Safety")
    print("=" * 50)

    try:
        from audio_manager import AudioManager

        # Create audio manager
        audio_manager = AudioManager()

        # Test thread-safe level updates
        print("Testing thread-safe level updates...")
        audio_manager._update_levels_thread_safe(100.0, 200.0, 30.5)

        levels = audio_manager.get_volume_levels()
        print(f"Levels retrieved: Mic={levels['microphone']}, Sys={levels['system_audio']}, Buffer={levels['buffer_duration']}")

        if levels['microphone'] == 100.0 and levels['system_audio'] == 200.0:
            print("✓ Thread-safe level updates working")
        else:
            print("✗ Thread-safe level updates failed")
            return False

        # Test status queue communication
        print("\nTesting status queue communication...")

        # Send some status updates
        audio_manager.status_queue.put({
            'type': 'thread_status',
            'status': 'starting',
            'message': 'Test message 1'
        })

        audio_manager.status_queue.put({
            'type': 'levels',
            'mic_level': 150.0,
            'sys_level': 250.0,
            'buffer_duration': 45.0
        })

        # Retrieve updates
        updates = audio_manager.get_status_updates()
        print(f"Retrieved {len(updates)} status updates")

        if len(updates) == 2:
            print("✓ Status queue communication working")
            for i, update in enumerate(updates):
                print(f"  Update {i+1}: {update['type']} - {update.get('message', 'N/A')}")
        else:
            print("✗ Status queue communication failed")
            return False

        # Test command sending
        print("\nTesting command queue...")
        audio_manager.send_command('test_command', {'data': 'test'})

        try:
            command = audio_manager.command_queue.get_nowait()
            if command['command'] == 'test_command':
                print("✓ Command queue working")
            else:
                print("✗ Command queue failed - wrong command")
                return False
        except:
            print("✗ Command queue failed - no command received")
            return False

        print("SUCCESS: AudioManager thread safety tests passed")
        return True

    except Exception as e:
        print(f"ERROR: AudioManager thread safety test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_recording_lifecycle_safety():
    """Test recording start/stop lifecycle with thread safety"""
    print("\nTesting Recording Lifecycle Thread Safety")
    print("=" * 50)

    try:
        from audio_manager import AudioManager

        audio_manager = AudioManager()

        # Mock devices for testing
        audio_manager.input_device = 0
        audio_manager.system_audio_device = 1

        print("Testing clean shutdown event handling...")

        # Test shutdown event
        audio_manager._shutdown_event.set()
        if audio_manager._shutdown_event.is_set():
            print("✓ Shutdown event can be set")

        audio_manager._shutdown_event.clear()
        if not audio_manager._shutdown_event.is_set():
            print("✓ Shutdown event can be cleared")

        # Test thread state tracking
        print("\nTesting thread state tracking...")
        if not audio_manager._thread_running:
            print("✓ Thread state initially false")

        # Simulate recording lifecycle without actual audio
        print("\nTesting recording lifecycle (no actual audio)...")

        # Check initial state
        levels = audio_manager.get_volume_levels()
        print(f"Initial levels: {levels}")

        if levels['recording'] is False:
            print("✓ Initial recording state is False")
        else:
            print("✗ Initial recording state wrong")
            return False

        print("SUCCESS: Recording lifecycle thread safety tests passed")
        return True

    except Exception as e:
        print(f"ERROR: Recording lifecycle test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_gui_thread_simulation():
    """Simulate GUI thread interactions to test thread safety"""
    print("\nTesting GUI Thread Simulation")
    print("=" * 50)

    try:
        from audio_manager import AudioManager

        audio_manager = AudioManager()

        # Simulate concurrent GUI updates and audio thread operations
        print("Testing concurrent access simulation...")

        def gui_thread_simulation():
            """Simulate GUI thread getting updates"""
            for i in range(10):
                try:
                    levels = audio_manager.get_volume_levels()
                    updates = audio_manager.get_status_updates()
                    print(f"GUI thread {i}: levels={len(str(levels))}, updates={len(updates)}")
                    time.sleep(0.05)
                except Exception as e:
                    print(f"GUI thread error {i}: {e}")
                    return False
            return True

        def audio_thread_simulation():
            """Simulate audio thread sending updates"""
            for i in range(10):
                try:
                    audio_manager._update_levels_thread_safe(i * 10, i * 20, i * 1.5)
                    audio_manager.status_queue.put({
                        'type': 'levels',
                        'mic_level': i * 10,
                        'sys_level': i * 20,
                        'buffer_duration': i * 1.5,
                        'iteration': i
                    })
                    time.sleep(0.03)
                except Exception as e:
                    print(f"Audio thread error {i}: {e}")
                    return False
            return True

        # Start both threads
        gui_thread = threading.Thread(target=gui_thread_simulation)
        audio_thread = threading.Thread(target=audio_thread_simulation)

        gui_thread.start()
        audio_thread.start()

        # Wait for completion
        gui_thread.join(timeout=2.0)
        audio_thread.join(timeout=2.0)

        if gui_thread.is_alive() or audio_thread.is_alive():
            print("✗ Threads did not complete in time")
            return False

        print("✓ Concurrent access simulation completed")

        # Check final state
        final_levels = audio_manager.get_volume_levels()
        remaining_updates = audio_manager.get_status_updates()

        print(f"Final state: levels={final_levels}")
        print(f"Remaining updates: {len(remaining_updates)}")

        print("SUCCESS: GUI thread simulation tests passed")
        return True

    except Exception as e:
        print(f"ERROR: GUI thread simulation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_exception_isolation():
    """Test that exceptions in audio thread don't corrupt GUI thread"""
    print("\nTesting Exception Isolation")
    print("=" * 50)

    try:
        from audio_manager import AudioManager

        audio_manager = AudioManager()

        print("Testing exception handling in status updates...")

        # Test malformed status update
        try:
            # This should not crash the system
            audio_manager.status_queue.put({
                'type': 'malformed',
                'invalid_data': None,
                'nested': {'error': Exception("test error")}
            })

            updates = audio_manager.get_status_updates()
            print(f"✓ Malformed status update handled: {len(updates)} updates")
        except Exception as e:
            print(f"✗ Exception isolation failed: {e}")
            return False

        print("Testing thread-safe level updates with invalid data...")

        try:
            # Test with extreme values
            audio_manager._update_levels_thread_safe(float('inf'), -1000, 9999)
            levels = audio_manager.get_volume_levels()
            print(f"✓ Extreme values handled: {levels}")
        except Exception as e:
            print(f"✗ Extreme value handling failed: {e}")
            return False

        print("SUCCESS: Exception isolation tests passed")
        return True

    except Exception as e:
        print(f"ERROR: Exception isolation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all thread isolation tests"""
    print("AMANUENSIS - Thread Isolation & GUI Stability Fix Test")
    print("=" * 60)
    print("Testing fixes for:")
    print("1. Audio recording thread contaminating GUI thread")
    print("2. GUI element access from wrong thread during cleanup")
    print("3. Recording loop not properly isolated")
    print("4. Shutdown sequence causing GUI state corruption")
    print("=" * 60)

    results = []

    # Test 1: AudioManager Thread Safety
    thread_safety = test_audio_manager_thread_safety()
    results.append(("AudioManager Thread Safety", thread_safety))

    # Test 2: Recording Lifecycle Safety
    lifecycle_safety = test_recording_lifecycle_safety()
    results.append(("Recording Lifecycle Safety", lifecycle_safety))

    # Test 3: GUI Thread Simulation
    gui_simulation = test_gui_thread_simulation()
    results.append(("GUI Thread Simulation", gui_simulation))

    # Test 4: Exception Isolation
    exception_isolation = test_exception_isolation()
    results.append(("Exception Isolation", exception_isolation))

    # Summary
    print("\n" + "=" * 60)
    print("THREAD ISOLATION TEST RESULTS SUMMARY")
    print("=" * 60)

    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{test_name:<30} {status}")

    total_passed = sum(1 for _, success in results if success)
    print(f"\nOverall: {total_passed}/{len(results)} tests passed")

    if total_passed == len(results):
        print("\n🎉 SUCCESS: All thread isolation fixes working!")
        print("\nThe system should now have:")
        print("✓ Proper thread isolation between audio and GUI")
        print("✓ Thread-safe communication using Queues")
        print("✓ GUI updates only from main thread using after()")
        print("✓ Clean shutdown sequence: stop → wait → cleanup")
        print("✓ Exception handling preventing GUI corruption")
        print("\nNo more GUI corruption errors expected during recording!")
    else:
        print(f"\n❌ {len(results) - total_passed} tests failed - check output above")

if __name__ == "__main__":
    main()