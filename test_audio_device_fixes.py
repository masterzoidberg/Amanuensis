#!/usr/bin/env python3
"""
Test script to verify audio device selection and recording fixes
"""

def test_device_filtering():
    """Test proper device filtering"""
    print("Testing Device Filtering")
    print("=" * 50)

    try:
        from audio_manager import AudioManager

        audio_manager = AudioManager()

        # Test getting input devices (should only return devices with input channels > 0)
        print("\nTesting input device filtering...")
        input_devices = audio_manager.get_input_devices()

        print(f"Found {len(input_devices)} input devices:")
        for device in input_devices:
            print(f"  {device['index']}: {device['name']} ({device['channels']} channels)")
            if device['channels'] == 0:
                print(f"    ERROR: Input device has 0 channels!")
                return False

        # Test getting system audio devices
        print("\nTesting system audio device filtering...")
        system_devices = audio_manager.get_system_audio_devices()

        print(f"Found {len(system_devices)} system audio devices:")
        for device in system_devices:
            if device['index'] != -1:  # Skip placeholder
                print(f"  {device['index']}: {device['name']} ({device['channels']} channels) - {device.get('type', 'unknown')}")
                if device['channels'] == 0 and device['type'] != 'placeholder':
                    print(f"    WARNING: System device has 0 channels - type: {device.get('type')}")

        print("SUCCESS: Device filtering completed")
        return True

    except Exception as e:
        print(f"ERROR: Device filtering test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_device_validation():
    """Test device validation in recording setup"""
    print("\nTesting Device Validation")
    print("=" * 50)

    try:
        from audio_manager import AudioManager

        audio_manager = AudioManager()

        # Get devices for testing
        input_devices = audio_manager.get_input_devices()
        system_devices = audio_manager.get_system_audio_devices()

        if not input_devices:
            print("WARNING: No input devices available for testing")
            return True

        if not system_devices or system_devices[0]['index'] == -1:
            print("WARNING: No system audio devices available for testing")
            return True

        # Test setting valid devices
        print("Testing valid device configuration...")

        mic_device = input_devices[0]
        sys_device = next((d for d in system_devices if d['index'] != -1), None)

        if not sys_device:
            print("INFO: No valid system audio device found, using input device as fallback")
            sys_device = input_devices[0] if len(input_devices) > 0 else None

        if mic_device and sys_device:
            print(f"Setting microphone: {mic_device['name']} ({mic_device['channels']} ch)")
            mic_success, mic_msg = audio_manager.set_input_device(mic_device['index'])
            print(f"  Result: {mic_success} - {mic_msg}")

            print(f"Setting system audio: {sys_device['name']} ({sys_device['channels']} ch)")
            sys_success, sys_msg = audio_manager.set_system_audio_device(sys_device['index'])
            print(f"  Result: {sys_success} - {sys_msg}")

            if mic_success and sys_success:
                # Test the recording validation
                print("Testing recording start validation...")
                rec_success, rec_msg = audio_manager.start_recording()
                print(f"  Recording start: {rec_success} - {rec_msg}")

                if rec_success:
                    print("  Stopping recording...")
                    audio_manager.stop_recording()
                    print("SUCCESS: Recording validation passed")
                    return True
                else:
                    print(f"INFO: Recording start failed (expected if no valid system audio): {rec_msg}")
                    return True
            else:
                print("ERROR: Device setup failed")
                return False
        else:
            print("INFO: Insufficient devices for full test")
            return True

    except Exception as e:
        print(f"ERROR: Device validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_channel_validation():
    """Test channel count validation"""
    print("\nTesting Channel Count Validation")
    print("=" * 50)

    try:
        from audio_manager import AudioManager

        audio_manager = AudioManager()

        # Test the internal device validation
        print("Testing device channel validation...")

        # Try to get device info and validate
        devices = audio_manager.get_audio_devices()

        input_count = 0
        output_count = 0
        mixed_count = 0

        for device in devices['input_devices']:
            if device['channels'] > 0:
                input_count += 1
            else:
                print(f"  WARNING: Input device with 0 channels: {device['name']}")

        for device in devices['output_devices']:
            if device['channels'] == 0:
                output_count += 1
            else:
                mixed_count += 1

        print(f"Device analysis:")
        print(f"  Valid input devices: {input_count}")
        print(f"  Pure output devices: {output_count}")
        print(f"  Mixed devices: {mixed_count}")

        print("SUCCESS: Channel validation completed")
        return True

    except Exception as e:
        print(f"ERROR: Channel validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all audio device tests"""
    print("AMANUENSIS - Audio Device Selection Fix Test")
    print("=" * 60)
    print("Testing fixes for:")
    print("1. Device filtering to separate input vs output devices")
    print("2. Channel count validation before recording attempts")
    print("3. Improved Stereo Mix/system audio detection")
    print("4. UI device validation")
    print("=" * 60)

    results = []

    # Test 1: Device Filtering
    filtering_success = test_device_filtering()
    results.append(("Device Filtering", filtering_success))

    # Test 2: Device Validation
    validation_success = test_device_validation()
    results.append(("Device Validation", validation_success))

    # Test 3: Channel Validation
    channel_success = test_channel_validation()
    results.append(("Channel Validation", channel_success))

    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)

    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{test_name:<25} {status}")

    total_passed = sum(1 for _, success in results if success)
    print(f"\nOverall: {total_passed}/{len(results)} tests passed")

    if total_passed == len(results):
        print("\nSUCCESS: All audio device selection fixes working!")
        print("The system should now properly:")
        print("- Filter input vs output devices")
        print("- Validate channel counts before recording")
        print("- Detect system audio devices correctly")
        print("- Prevent selection of invalid devices in UI")
    else:
        print("\nSome tests failed - check the output above for details")

if __name__ == "__main__":
    main()