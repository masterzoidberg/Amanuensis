#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify transcript stitcher integration.
Tests the 5 fixes without requiring full app startup.
"""

import sys
import io
import time
from transcript_stitch import TranscriptStitcher, align_with_intersection_gate

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Mock pyannote Annotation for testing
class MockTurn:
    def __init__(self, start, end):
        self.start = start
        self.end = end

class MockAnnotation:
    def __init__(self, turns):
        self.turns = turns

    def itertracks(self, yield_label=True):
        for turn, label in self.turns:
            yield (turn, "track_0", label)

def test_fix_1_absolute_timestamps():
    """Test Fix #1: Per-segment absolute timestamps"""
    print("\n=== TEST FIX #1: Absolute Timestamps ===")

    config = {
        'overlap_seconds': 5.0,
        'min_turn_seconds': 0.5,
        'min_turn_chars': 5,
        'coalesce_gap_seconds': 0.30,
        'dup_text_similarity': 0.95
    }

    stitcher = TranscriptStitcher(config)
    stitcher.set_session_start(time.time())

    # Simulate segments at different times within buffer
    segments = [
        {'start': 0.0, 'end': 2.0, 'text': 'First segment', 'speaker_id': 'SPEAKER_00', 'speaker_label': 'Speaker 1', 'confidence': 0.9},
        {'start': 2.5, 'end': 4.5, 'text': 'Second segment', 'speaker_id': 'SPEAKER_01', 'speaker_label': 'Speaker 2', 'confidence': 0.85},
        {'start': 5.0, 'end': 7.0, 'text': 'Third segment', 'speaker_id': 'SPEAKER_00', 'speaker_label': 'Speaker 1', 'confidence': 0.9}
    ]

    buffer_window_start = 10.0  # 10 seconds into session

    result = stitcher.stitch_and_emit_segments(segments, buffer_window_start)

    print(f"Input: 3 segments at buffer offset {buffer_window_start}s")
    print(f"Output: {len(result)} segments")

    for seg in result:
        print(f"  [{seg['abs_start']:.2f} - {seg['abs_end']:.2f}] {seg.get('speaker_label', 'UNKNOWN')}: {seg['text'][:30]}...")

    # Verify absolute timestamps are different
    if len(result) >= 2:
        assert result[0]['abs_start'] != result[1]['abs_start'], "Timestamps should be different!"
        print("✓ PASS: Each segment has unique absolute timestamp")
        return True
    else:
        print("✗ FAIL: Not enough segments emitted")
        return False

def test_fix_2_overlap_deduplication():
    """Test Fix #2: Overlap de-duplication"""
    print("\n=== TEST FIX #2: Overlap De-duplication ===")

    config = {
        'overlap_seconds': 5.0,
        'min_turn_seconds': 0.5,
        'min_turn_chars': 5,
        'coalesce_gap_seconds': 0.30,
        'dup_text_similarity': 0.95
    }

    stitcher = TranscriptStitcher(config)
    stitcher.set_session_start(time.time())

    # First buffer (0-10s)
    segments1 = [
        {'start': 5.0, 'end': 8.0, 'text': 'Overlapping text', 'speaker_id': 'SPEAKER_00', 'speaker_label': 'Speaker 1', 'confidence': 0.9}
    ]
    result1 = stitcher.stitch_and_emit_segments(segments1, 0.0)
    watermark_after_buf1 = stitcher.last_committed_end_time

    # Second buffer (5-15s) - has 5s overlap
    # Realistic scenario: Whisper re-transcribes the overlap region
    segments2 = [
        {'start': 2.5, 'end': 5.5, 'text': 'Overlapping text', 'speaker_id': 'SPEAKER_00', 'speaker_label': 'Speaker 1', 'confidence': 0.9},  # This is 7.5-10.5s absolute, starts BEFORE watermark (8s)
        {'start': 7.0, 'end': 10.0, 'text': 'New text', 'speaker_id': 'SPEAKER_00', 'speaker_label': 'Speaker 1', 'confidence': 0.9}  # This is 12-15s, should be kept
    ]
    drops_before = stitcher.stats.get('dropped_overlap', 0)
    result2 = stitcher.stitch_and_emit_segments(segments2, 5.0)
    drops_in_buf2 = stitcher.stats['dropped_overlap']

    print(f"Buffer 1 (0-10s): {len(result1)} segments emitted")
    if result1:
        print(f"  First segment abs times: {result1[0]['abs_start']:.2f} - {result1[0]['abs_end']:.2f}")
    print(f"  Watermark after buf1: {watermark_after_buf1:.2f}s")
    print(f"Buffer 2 (5-15s): {len(result2)} segments emitted (after dedup)")
    print(f"  Dropped overlap in buf2: {drops_in_buf2}")
    print(f"  Final watermark: {stitcher.last_committed_end_time:.2f}s")

    if stitcher.stats['dropped_overlap'] > 0:
        print("✓ PASS: Overlapping segments were deduplicated")
        return True
    else:
        print("✗ FAIL: No overlap deduplication occurred")
        return False

def test_fix_3_intersection_gate():
    """Test Fix #3: ASR-Diarization intersection gate"""
    print("\n=== TEST FIX #3: Intersection Gate ===")

    # Whisper segments
    whisper_segments = [
        {'start': 0.0, 'end': 2.0, 'text': 'Hello there'},
        {'start': 3.0, 'end': 5.0, 'text': 'How are you'},
        {'start': 8.0, 'end': 10.0, 'text': 'Silence segment'}  # No speaker here
    ]

    # Diarization (only covers 0-6s, nothing at 8-10s)
    diarization = MockAnnotation([
        (MockTurn(0.0, 3.0), 'SPEAKER_00'),
        (MockTurn(3.0, 6.0), 'SPEAKER_01')
    ])

    result = align_with_intersection_gate(whisper_segments, diarization, min_confidence=0.1)

    print(f"Input: 3 Whisper segments")
    print(f"Diarization: Only 0-6s has speakers")
    print(f"Output: {len(result)} aligned segments")

    for seg in result:
        print(f"  [{seg['start']:.1f}-{seg['end']:.1f}] {seg['speaker_id']}: {seg['text']}")

    # Should drop the segment at 8-10s
    if len(result) == 2:
        print("✓ PASS: Segment with no speaker overlap was dropped")
        return True
    else:
        print(f"✗ FAIL: Expected 2 segments, got {len(result)}")
        return False

def test_fix_4_coalescing():
    """Test Fix #4: Turn coalescing"""
    print("\n=== TEST FIX #4: Turn Coalescing ===")

    config = {
        'overlap_seconds': 5.0,
        'min_turn_seconds': 0.5,
        'min_turn_chars': 5,
        'coalesce_gap_seconds': 0.30,
        'dup_text_similarity': 0.95
    }

    stitcher = TranscriptStitcher(config)
    stitcher.set_session_start(time.time())

    # Simulate fragmented utterances: "No," "no," "no."
    segments = [
        {'start': 0.0, 'end': 0.5, 'text': 'No,', 'speaker_id': 'SPEAKER_00', 'speaker_label': 'Speaker 1', 'confidence': 0.9},
        {'start': 0.6, 'end': 1.0, 'text': 'no,', 'speaker_id': 'SPEAKER_00', 'speaker_label': 'Speaker 1', 'confidence': 0.9},  # Gap: 0.1s
        {'start': 1.15, 'end': 1.5, 'text': 'no.', 'speaker_id': 'SPEAKER_00', 'speaker_label': 'Speaker 1', 'confidence': 0.9},  # Gap: 0.15s
        {'start': 3.0, 'end': 5.0, 'text': 'Different turn', 'speaker_id': 'SPEAKER_01', 'speaker_label': 'Speaker 2', 'confidence': 0.85}
    ]

    result = stitcher.stitch_and_emit_segments(segments, 0.0)

    print(f"Input: 4 segments (3 rapid same-speaker + 1 different)")
    print(f"Output: {len(result)} segments")
    print(f"Coalesced: {stitcher.stats['coalesced']}")

    for seg in result:
        print(f"  [{seg['abs_start']:.2f}-{seg['abs_end']:.2f}] {seg.get('speaker_label', 'UNKNOWN')}: {seg['text']}")

    if stitcher.stats['coalesced'] >= 2 and len(result) == 2:
        print("✓ PASS: Rapid same-speaker segments were coalesced")
        return True
    else:
        print(f"✗ FAIL: Expected coalescing, got {stitcher.stats['coalesced']} coalesces and {len(result)} segments")
        return False

def test_fix_5_idempotent_updates():
    """Test Fix #5: Idempotent UI updates"""
    print("\n=== TEST FIX #5: Idempotent Updates ===")

    config = {
        'overlap_seconds': 5.0,
        'min_turn_seconds': 0.5,
        'min_turn_chars': 5,
        'coalesce_gap_seconds': 0.30,
        'dup_text_similarity': 0.95
    }

    stitcher = TranscriptStitcher(config)
    stitcher.set_session_start(time.time())

    segment = {
        'start': 0.0,
        'end': 2.0,
        'text': 'Test segment',
        'speaker_id': 'SPEAKER_00',
        'speaker_label': 'Speaker 1',
        'confidence': 0.9
    }

    # Emit same segment twice
    result1 = stitcher.stitch_and_emit_segments([segment], 0.0)
    result2 = stitcher.stitch_and_emit_segments([segment], 0.0)  # Duplicate

    print(f"First emission: {len(result1)} segments")
    print(f"Second emission (duplicate): {len(result2)} segments")
    print(f"Dropped duplicates: {stitcher.stats['dropped_duplicate']}")

    if len(result1) == 1 and len(result2) == 0:
        print("✓ PASS: Duplicate segment was rejected")
        return True
    else:
        print(f"✗ FAIL: Expected 1 then 0, got {len(result1)} then {len(result2)}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("TRANSCRIPT STITCHER INTEGRATION TEST SUITE")
    print("=" * 60)

    results = {
        'Fix #1: Absolute Timestamps': test_fix_1_absolute_timestamps(),
        'Fix #2: Overlap Deduplication': test_fix_2_overlap_deduplication(),
        'Fix #3: Intersection Gate': test_fix_3_intersection_gate(),
        'Fix #4: Turn Coalescing': test_fix_4_coalescing(),
        'Fix #5: Idempotent Updates': test_fix_5_idempotent_updates()
    }

    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:35} {status}")

    all_passed = all(results.values())
    print("=" * 60)

    if all_passed:
        print("✓✓✓ ALL INTEGRATION TESTS PASSED ✓✓✓")
        print("Transcript stitcher is ready for production use")
        return 0
    else:
        print("✗✗✗ SOME TESTS FAILED ✗✗✗")
        print("Review the errors above before deploying")
        return 1

if __name__ == '__main__':
    sys.exit(main())
