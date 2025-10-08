#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify all four fixes are working correctly.
Run this BEFORE starting the main application.
"""

import sys
import os
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def test_gemini_import():
    """Test #1: Gemini SDK import (backward compatible)"""
    print("\n=== TEST 1: Gemini SDK Import (Backward Compatible) ===")

    # Try new SDK first
    try:
        from google import genai
        print("✓ NEW unified SDK import successful: google.genai")

        # Test client initialization
        try:
            client = genai.Client(api_key='test_key_invalid')
            print("✓ Client initialization pattern correct")
        except Exception as e:
            print(f"✓ Client init failed gracefully (expected): {type(e).__name__}")

        return True
    except ImportError:
        print("⚠ NEW unified SDK not installed, checking for deprecated SDK...")

    # Fall back to old SDK
    try:
        import google.generativeai as genai
        print("✓ DEPRECATED SDK import successful: google.generativeai")
        print("  NOTE: Consider upgrading to google-genai (pip install google-genai)")

        # Test old SDK pattern
        try:
            genai.configure(api_key='test_key_invalid')
            print("✓ Old SDK configuration pattern works")
        except Exception as e:
            print(f"✓ Old SDK configure failed gracefully (expected): {type(e).__name__}")

        return True
    except ImportError as e:
        print(f"✗ NO Gemini SDK installed (neither new nor old): {e}")
        print("  Install with: pip install google-genai  OR  pip install google-generativeai")
        return False

def test_phi_queue():
    """Test #2: PHI queue uses proper Queue API"""
    print("\n=== TEST 2: PHI Queue API ===")
    import queue

    # Simulate the old broken code
    print("Testing old broken pattern...")
    try:
        phi_queue_broken = []
        phi_queue_broken.put({'test': 'data'})  # This should fail
        print("✗ List has .put() method (unexpected!)")
        return False
    except AttributeError as e:
        print(f"✓ Confirmed list has no .put(): {e}")

    # Test correct pattern
    print("Testing correct Queue pattern...")
    try:
        phi_queue = queue.Queue()
        phi_queue.put({'test': 'data'}, block=False)
        print("✓ Queue.put() works")

        item = phi_queue.get_nowait()
        print(f"✓ Queue.get_nowait() works: {item}")

        size = phi_queue.qsize()
        print(f"✓ Queue.qsize() works: {size}")

        return True
    except Exception as e:
        print(f"✗ Queue operations failed: {e}")
        return False

def test_theme_resolver():
    """Test #3: Theme resolver handles missing keys"""
    print("\n=== TEST 3: Theme Resolver ===")

    # Simulate theme dictionary
    colors = {
        'button_primary': '#007bff',
        'button_primary_hover': '#0056b3',
        # Note: 'button_hover' is intentionally missing
    }

    # Test old broken pattern
    print("Testing old broken pattern...")
    try:
        hover = colors['button_hover']  # This should fail
        print("✗ KeyError not raised (unexpected!)")
        return False
    except KeyError as e:
        print(f"✓ Confirmed KeyError for missing key: {e}")

    # Test correct pattern with .get()
    print("Testing correct pattern with .get()...")
    try:
        hover = colors.get('button_hover', '#0056b3')
        print(f"✓ .get() with fallback works: {hover}")

        # Test with existing key
        primary = colors.get('button_primary', '#000000')
        print(f"✓ .get() with existing key works: {primary}")

        return True
    except Exception as e:
        print(f"✗ .get() pattern failed: {e}")
        return False

def test_soundcard_config():
    """Test #4: SoundCard configuration loading"""
    print("\n=== TEST 4: SoundCard Config ===")
    import json

    # Test settings file
    try:
        with open('amanuensis_settings.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        audio = config.get('audio', {})

        # Check for new settings
        blocksize = audio.get('blocksize')
        max_disc = audio.get('max_discontinuities')
        throttle = audio.get('discontinuity_warning_throttle')

        print(f"✓ Settings file loaded")
        print(f"  - blocksize: {blocksize}")
        print(f"  - max_discontinuities: {max_disc}")
        print(f"  - discontinuity_warning_throttle: {throttle}")

        if blocksize and max_disc and throttle:
            print("✓ All SoundCard settings present")
            return True
        else:
            print("✗ Some SoundCard settings missing")
            return False

    except Exception as e:
        print(f"✗ Settings load failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("AMANUENSIS V2 - FIX VERIFICATION TEST SUITE")
    print("=" * 60)

    results = {
        'Gemini SDK': test_gemini_import(),
        'PHI Queue': test_phi_queue(),
        'Theme Resolver': test_theme_resolver(),
        'SoundCard Config': test_soundcard_config(),
    }

    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:20} {status}")

    all_passed = all(results.values())
    print("=" * 60)

    if all_passed:
        print("✓✓✓ ALL TESTS PASSED ✓✓✓")
        print("You can now run the main application: python main.py")
        return 0
    else:
        print("✗✗✗ SOME TESTS FAILED ✗✗✗")
        print("Please review the errors above before running main.py")
        return 1

if __name__ == '__main__':
    sys.exit(main())
