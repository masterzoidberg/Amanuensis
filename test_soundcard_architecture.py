#!/usr/bin/env python3
"""
Test script for the new unified python-soundcard architecture
This verifies that concurrent mic + loopback capture works properly
"""

import time
import numpy as np
import threading
import soundcard as sc
from logger_config import get_logger

def test_concurrent_soundcard_capture():
    """Test concurrent microphone and loopback capture using python-soundcard"""
    logger = get_logger('test_soundcard')
    logger.info("Testing concurrent soundcard capture...")

    try:
        # Find devices
        microphones = sc.all_microphones(include_loopback=False)
        speakers = sc.all_speakers()

        if not microphones:
            logger.error("No microphones found")
            return False

        if not speakers:
            logger.error("No speakers found")
            return False

        # Select devices (prefer "TONOR" for mic, "Logi" for speakers)
        target_mic = None
        for mic in microphones:
            if "TONOR" in mic.name.upper():
                target_mic = mic
                break
        if not target_mic:
            target_mic = microphones[0]  # Fallback to first

        target_speaker = None
        for spk in speakers:
            if "LOGI" in spk.name.upper():
                target_speaker = spk
                break
        if not target_speaker:
            target_speaker = speakers[0]  # Fallback to default

        logger.info(f"Selected microphone: {target_mic.name}")
        logger.info(f"Selected speaker (for loopback): {target_speaker.name}")

        # Test configuration
        sample_rate = 44100
        chunk_size = 1024
        test_duration = 5.0  # seconds

        # Get loopback microphone
        loopback_mic = sc.get_microphone(id=target_speaker.name, include_loopback=True)

        # Results storage
        results = {
            'mic_chunks': 0,
            'sys_chunks': 0,
            'mic_levels': [],
            'sys_levels': [],
            'errors': []
        }

        # Recording flag
        recording = True

        def record_microphone():
            """Record from microphone"""
            try:
                with target_mic.recorder(samplerate=sample_rate, channels=1) as rec:
                    logger.debug("Microphone recording started")
                    while recording:
                        try:
                            data = rec.record(numframes=chunk_size)
                            # Convert to int16 for level calculation
                            audio_int16 = (data * 32767).astype(np.int16)
                            level = np.sqrt(np.mean(audio_int16.astype(float)**2))
                            results['mic_chunks'] += 1
                            results['mic_levels'].append(level)
                        except Exception as e:
                            results['errors'].append(f"Mic error: {e}")
                            break
            except Exception as e:
                results['errors'].append(f"Mic setup error: {e}")

        def record_system():
            """Record from system audio (loopback)"""
            try:
                with loopback_mic.recorder(samplerate=sample_rate, channels=2) as rec:
                    logger.debug("System loopback recording started")
                    while recording:
                        try:
                            data = rec.record(numframes=chunk_size)
                            # Convert stereo to mono, then to int16 for level calculation
                            if data.ndim == 2:
                                mono_data = np.mean(data, axis=1)
                            else:
                                mono_data = data
                            audio_int16 = (mono_data * 32767).astype(np.int16)
                            level = np.sqrt(np.mean(audio_int16.astype(float)**2))
                            results['sys_chunks'] += 1
                            results['sys_levels'].append(level)
                        except Exception as e:
                            results['errors'].append(f"System error: {e}")
                            break
            except Exception as e:
                results['errors'].append(f"System setup error: {e}")

        # Start concurrent threads
        mic_thread = threading.Thread(target=record_microphone, daemon=True)
        sys_thread = threading.Thread(target=record_system, daemon=True)

        logger.info(f"Starting concurrent recording for {test_duration} seconds...")
        start_time = time.time()

        mic_thread.start()
        sys_thread.start()

        # Let it run for the test duration
        time.sleep(test_duration)

        # Stop recording
        recording = False
        elapsed = time.time() - start_time

        # Wait for threads to finish
        mic_thread.join(timeout=2)
        sys_thread.join(timeout=2)

        # Analyze results
        logger.info("=== CONCURRENT CAPTURE TEST RESULTS ===")
        logger.info(f"Test duration: {elapsed:.2f}s")
        logger.info(f"Microphone chunks: {results['mic_chunks']}")
        logger.info(f"System chunks: {results['sys_chunks']}")

        if results['mic_levels']:
            avg_mic_level = np.mean(results['mic_levels'])
            max_mic_level = np.max(results['mic_levels'])
            logger.info(f"Mic levels - Avg: {avg_mic_level:.0f}, Max: {max_mic_level:.0f}")

        if results['sys_levels']:
            avg_sys_level = np.mean(results['sys_levels'])
            max_sys_level = np.max(results['sys_levels'])
            logger.info(f"System levels - Avg: {avg_sys_level:.0f}, Max: {max_sys_level:.0f}")

        if results['errors']:
            logger.error(f"Errors encountered: {len(results['errors'])}")
            for error in results['errors']:
                logger.error(f"  - {error}")

        # Success criteria
        expected_chunks = int(elapsed * sample_rate / chunk_size)
        mic_success = results['mic_chunks'] >= expected_chunks * 0.8  # Allow 20% tolerance
        sys_success = results['sys_chunks'] >= expected_chunks * 0.8
        no_errors = len(results['errors']) == 0

        success = mic_success and sys_success and no_errors

        if success:
            logger.info("✅ CONCURRENT CAPTURE TEST PASSED")
            logger.info("  - Both microphone and system audio captured successfully")
            logger.info("  - No errors encountered")
            logger.info("  - Ready for integration into AudioManager")
        else:
            logger.error("❌ CONCURRENT CAPTURE TEST FAILED")
            if not mic_success:
                logger.error(f"  - Microphone capture insufficient: {results['mic_chunks']}/{expected_chunks}")
            if not sys_success:
                logger.error(f"  - System audio capture insufficient: {results['sys_chunks']}/{expected_chunks}")
            if not no_errors:
                logger.error(f"  - {len(results['errors'])} errors encountered")

        return success

    except Exception as e:
        logger.error(f"Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_concurrent_soundcard_capture()
    print(f"\nTest result: {'PASSED' if success else 'FAILED'}")
    exit(0 if success else 1)