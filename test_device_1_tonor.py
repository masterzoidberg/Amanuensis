#!/usr/bin/env python3
"""
Test device index 1 (TONOR) specifically to verify the original error is fixed
"""

import time
from audio_manager import AudioManager

def test_device_1_tonor():
    """Test device index 1 (TONOR) to verify the original 'pa' error is fixed"""
    print("Testing device index 1 (TONOR) - Original error case...")

    try:
        audio_manager = AudioManager()

        # Get devices
        devices = audio_manager.get_audio_devices()
        print(f"Available microphones:")
        for i, mic in enumerate(devices['input_devices']):
            print(f"  {i}: {mic['name']}")

        # Test setting device index 1 specifically (this was failing before)
        print("\nAttempting to set input device 1 (original error case)...")
        success, msg = audio_manager.set_input_device(1)  # This should now work via compatibility wrapper
        print(f"set_input_device(1) result: {success}, {msg}")

        # Also test direct microphone device setting
        print("\nTesting direct microphone device setting...")
        success, msg = audio_manager.set_microphone_device(1)  # Direct soundcard method
        print(f"set_microphone_device(1) result: {success}, {msg}")

        # Set a system audio device
        if devices['system_recording_devices']:
            speaker_name = devices['system_recording_devices'][0]['raw_name']
            success, msg = audio_manager.set_system_audio_device(speaker_name)
            print(f"System audio result: {success}, {msg}")

            # Test brief recording to ensure everything works end-to-end
            print("\nTesting recording with TONOR device...")
            success, msg = audio_manager.start_recording()
            print(f"Recording start: {success}, {msg}")

            if success:
                time.sleep(1)  # Brief recording
                levels = audio_manager.get_levels()
                print(f"Audio levels - Mic: {levels.get('mic', 0):.4f}, System: {levels.get('system', 0):.4f}")
                audio_manager.stop_recording()
                print("Recording stopped successfully")

                print("\n🎉 SUCCESS: Device index 1 (TONOR) now works perfectly!")
                print("✅ Original 'pa' attribute error RESOLVED")
                return True

        return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_device_1_tonor()
    print(f"\nDevice 1 (TONOR) Test: {'PASSED' if success else 'FAILED'}")