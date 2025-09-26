#!/usr/bin/env python3
"""
Debug test for AudioManager without emojis to avoid Unicode issues
"""

import time
import numpy as np
from logger_config import get_logger

def debug_audio_manager():
    """Debug test without emojis"""
    logger = get_logger('debug_audio')
    print("Testing AudioManager debug...")

    try:
        from audio_manager import AudioManager
        print("AudioManager imported successfully")

        # Initialize AudioManager
        audio_manager = AudioManager()
        print("AudioManager initialized successfully")

        # Test device enumeration
        devices = audio_manager.get_audio_devices()
        print(f"Devices found:")
        print(f"  - Microphones: {len(devices['input_devices'])}")
        for i, mic in enumerate(devices['input_devices']):
            print(f"    {i}: {mic['name']}")
        print(f"  - System audio devices: {len(devices['system_recording_devices'])}")
        for i, spk in enumerate(devices['system_recording_devices']):
            print(f"    {i}: {spk['name']}")

        # Set devices
        if devices['input_devices']:
            print(f"Setting microphone to: {devices['input_devices'][0]['name']}")
            success, msg = audio_manager.set_microphone_device(0)  # Use index
            print(f"Microphone result: {success}, {msg}")

        if devices['system_recording_devices']:
            # Find raw speaker name
            speaker_name = devices['system_recording_devices'][0]['raw_name']
            print(f"Setting system audio to: {speaker_name}")
            success, msg = audio_manager.set_system_audio_device(speaker_name)
            print(f"System audio result: {success}, {msg}")

        # Test callback system
        callback_data = {'count': 0}
        def test_callback(audio_data, sample_rate):
            callback_data['count'] += 1
            print(f"Callback {callback_data['count']}: {len(audio_data)} samples at {sample_rate}Hz")

        audio_manager.add_audio_data_callback(test_callback)
        print("Audio callback registered")

        # Test recording
        print("Starting recording...")
        success, msg = audio_manager.start_recording()
        print(f"Recording start result: {success}, {msg}")

        if success:
            print("Recording for 3 seconds...")
            time.sleep(3)

            levels = audio_manager.get_levels()
            print(f"Audio levels - Mic: {levels.get('mic', 0):.4f}, System: {levels.get('system', 0):.4f}")

            print("Stopping recording...")
            audio_manager.stop_recording()

            print(f"Total callbacks received: {callback_data['count']}")

        return True

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = debug_audio_manager()
    print(f"Debug test: {'PASSED' if success else 'FAILED'}")