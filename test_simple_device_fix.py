#!/usr/bin/env python3
"""
Simple Device Test - No Emojis
Test the COM fix for device testing
"""

def test_single_device():
    """Test a single device with COM initialization"""
    print("Testing single device with COM fix...")

    try:
        # Initialize COM first
        from com_initializer import initialize_com_for_audio
        if not initialize_com_for_audio():
            print("FAIL: COM initialization failed")
            return False

        print("PASS: COM initialized successfully")

        # Test loopback device access
        from audio_transcription_bridge import resolve_loopback_mic, preflight_loopback

        print("Resolving loopback device...")
        mic, spk = resolve_loopback_mic()
        print(f"PASS: Device resolved: {spk.name}")

        print("Testing device preflight (250ms recording)...")
        preflight_loopback(mic)
        print("PASS: Device preflight successful")

        return True

    except Exception as e:
        error_str = str(e)
        print(f"FAIL: Device test failed: {error_str}")

        # Check for the specific COM error we were fixing
        if "0x800401f0" in error_str:
            print("ERROR: COM error 0x800401f0 still occurring - fix incomplete")
            return False
        elif "COM initialization failed" in error_str:
            print("ERROR: COM initialization issue")
            return False
        else:
            print(f"ERROR: Different issue: {error_str}")
            return False

if __name__ == "__main__":
    print("SIMPLE DEVICE TEST - COM FIX VERIFICATION")
    print("=" * 50)

    success = test_single_device()

    print("\n" + "=" * 50)
    if success:
        print("RESULT: SUCCESS")
        print("The COM error 0x800401f0 has been RESOLVED!")
        print("Device testing buttons should now work in Settings.")
    else:
        print("RESULT: FAILED")
        print("The COM fix may need additional work.")

    exit(0 if success else 1)