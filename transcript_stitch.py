"""
Transcript Stitching/Alignment Module for Amanuensis V2

Implements 5 critical fixes for transcript alignment:
1. Per-segment absolute timestamps
2. Overlap de-duplication watermark
3. ASR-Diarization intersection gate
4. Turn coalescing + min duration
5. Idempotent UI updates with stable IDs

Author: Claude Code
Date: 2025-10-02
Context7 Documentation Used:
- /systran/faster-whisper (Trust: 6.8) - Segment timestamp handling
- /pyannote/pyannote-audio (Trust: 9.1) - Diarization alignment
- /tomschimansky/customtkinter (Trust: 8.7) - Thread-safe UI updates
"""

import time
from collections import deque, defaultdict
from typing import List, Dict, Optional, Tuple


class TranscriptStitcher:
    """
    Manages transcript stitching with deduplication and alignment.

    Per Context7 docs:
    - faster-whisper segments have .start/.end in seconds (relative to buffer)
    - pyannote turns have .start/.end in seconds (relative to buffer)
    - Must compute absolute timestamps from session start + buffer offset
    """

    def __init__(self, config: Dict):
        """
        Initialize stitcher with configuration.

        Args:
            config: Dict with keys:
                - overlap_seconds: float (default 5.0)
                - min_turn_seconds: float (default 1.0)
                - min_turn_chars: int (default 15)
                - coalesce_gap_seconds: float (default 0.30)
                - dup_text_similarity: float (default 0.95)
        """
        self.config = config

        # Fix #2: Overlap de-dup watermark
        # Tracks the latest absolute end time we've committed to avoid re-processing
        self.last_committed_end_time = 0.0

        # Fix #5: Idempotent UI updates
        # LRU cache of emitted segment UIDs to prevent duplicates
        self.emitted_segment_uids = deque(maxlen=200)

        # Track last segment per speaker for similarity checking
        self.last_segment_by_speaker = {}

        # Session timing reference
        self.absolute_session_start_time = None

        # Statistics for logging
        self.stats = {
            'emitted': 0,
            'dropped_overlap': 0,
            'dropped_short': 0,
            'dropped_duplicate': 0,
            'coalesced': 0
        }

    def set_session_start(self, start_time: float):
        """Set absolute session start time for timestamp calculations."""
        self.absolute_session_start_time = start_time

    def reset_stats(self):
        """Reset statistics counters."""
        for key in self.stats:
            self.stats[key] = 0

    def stitch_and_emit_segments(
        self,
        aligned_segments: List[Dict],
        buffer_window_start: float
    ) -> List[Dict]:
        """
        Process aligned segments with all 5 fixes applied.

        Args:
            aligned_segments: List of dicts with keys:
                - start: float (relative to buffer)
                - end: float (relative to buffer)
                - text: str
                - speaker_id: str
                - confidence: float
            buffer_window_start: float (absolute time in seconds from session start)

        Returns:
            List of segments ready for emission with absolute timestamps

        Implements:
        - Fix #1: Compute absolute timestamps
        - Fix #2: Drop overlapping segments
        - Fix #3: Already handled by caller (intersection gate)
        - Fix #4: Coalesce adjacent same-speaker segments
        - Fix #5: Deduplicate using stable UIDs
        """
        if not aligned_segments:
            return []

        self.reset_stats()

        # Fix #1: Convert to absolute timestamps
        abs_segments = []
        for seg in aligned_segments:
            abs_start = buffer_window_start + seg['start']
            abs_end = buffer_window_start + seg['end']

            abs_segments.append({
                'abs_start': abs_start,
                'abs_end': abs_end,
                'start': seg['start'],  # Keep relative for logging
                'end': seg['end'],
                'text': seg['text'].strip(),
                'speaker': seg.get('speaker_label', 'UNKNOWN'),
                'speaker_id': seg['speaker_id'],
                'confidence': seg['confidence']
            })

        # Fix #2: Drop segments that overlap with already-committed time
        # A segment overlaps if its START is before or at the last committed END time
        # Using < instead of <= to allow exact boundary segments (edge case handling)
        # But segments starting exactly at watermark may indicate buffer boundary issues
        filtered_segments = []
        for seg in abs_segments:
            # Drop if segment starts strictly before committed end time
            if seg['abs_start'] < self.last_committed_end_time:
                self.stats['dropped_overlap'] += 1
                continue  # Skip overlapping segment
            filtered_segments.append(seg)

        if not filtered_segments:
            return []

        # Fix #4: Coalesce adjacent same-speaker segments
        coalesced_segments = self._coalesce_turns(filtered_segments)

        # Apply minimum duration/character filters
        final_segments = []
        for seg in coalesced_segments:
            duration = seg['abs_end'] - seg['abs_start']
            text_len = len(seg['text'])

            min_dur = self.config.get('min_turn_seconds', 1.0)
            min_chars = self.config.get('min_turn_chars', 15)

            if duration < min_dur and text_len < min_chars:
                self.stats['dropped_short'] += 1
                continue  # Too short

            final_segments.append(seg)

        # Fix #5: Deduplicate using stable UIDs
        emittable_segments = []
        for seg in final_segments:
            # Generate stable UID
            uid = self._compute_segment_uid(seg)

            # Check if already emitted
            if uid in self.emitted_segment_uids:
                self.stats['dropped_duplicate'] += 1
                continue

            # Check text similarity with last segment for same speaker
            if seg['speaker'] in self.last_segment_by_speaker:
                similarity = self._compute_text_similarity(
                    seg['text'],
                    self.last_segment_by_speaker[seg['speaker']]['text']
                )
                if similarity > self.config.get('dup_text_similarity', 0.95):
                    self.stats['dropped_duplicate'] += 1
                    continue  # Near-duplicate

            # Mark as emitted
            self.emitted_segment_uids.append(uid)
            self.last_segment_by_speaker[seg['speaker']] = seg
            emittable_segments.append(seg)
            self.stats['emitted'] += 1

        # Update watermark
        if emittable_segments:
            max_end = max(seg['abs_end'] for seg in emittable_segments)
            self.last_committed_end_time = max(self.last_committed_end_time, max_end)

        return emittable_segments

    def _coalesce_turns(self, segments: List[Dict]) -> List[Dict]:
        """
        Fix #4: Merge adjacent same-speaker segments within gap threshold.

        Per analysis of bug reports: "No, no, no." appearing as separate lines.
        Solution: Coalesce if same speaker, gap < 300ms, combined ≤ 6s.

        Args:
            segments: List of absolute-timestamped segments

        Returns:
            Coalesced segments
        """
        if not segments:
            return []

        gap_threshold = self.config.get('coalesce_gap_seconds', 0.30)
        max_duration = 6.0  # Hard limit for combined turn

        # Sort by start time
        sorted_segs = sorted(segments, key=lambda x: x['abs_start'])

        coalesced = []
        current = None

        for seg in sorted_segs:
            if current and current['speaker'] == seg['speaker']:
                # Same speaker - check if we should merge
                gap = seg['abs_start'] - current['abs_end']
                combined_duration = seg['abs_end'] - current['abs_start']

                if gap < gap_threshold and combined_duration <= max_duration:
                    # Merge segments
                    current['abs_end'] = seg['abs_end']
                    current['end'] = seg['end']  # Update relative end
                    current['text'] += " " + seg['text']
                    current['confidence'] = min(current['confidence'], seg['confidence'])
                    self.stats['coalesced'] += 1
                    continue  # Don't add seg separately

            # Finalize previous segment
            if current:
                coalesced.append(current)

            # Start new segment
            current = seg.copy()

        # Add final segment
        if current:
            coalesced.append(current)

        return coalesced

    def _compute_segment_uid(self, segment: Dict) -> str:
        """
        Fix #5: Generate stable UID for deduplication.

        Format: "{start_ms}-{end_ms}-{speaker}"
        Where times are in milliseconds for precision.
        """
        start_ms = int(segment['abs_start'] * 1000)
        end_ms = int(segment['abs_end'] * 1000)
        speaker = segment['speaker']
        return f"{start_ms}-{end_ms}-{speaker}"

    def _compute_text_similarity(self, text1: str, text2: str) -> float:
        """
        Fix #5: Compute Jaccard similarity for near-duplicate detection.

        Returns similarity score [0.0, 1.0] where 1.0 = identical.
        Uses word-level Jaccard: |A ∩ B| / |A ∪ B|
        """
        # Normalize whitespace
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 and not words2:
            return 1.0  # Both empty

        if not words1 or not words2:
            return 0.0  # One empty

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union) if union else 0.0

    def get_stats_summary(self, buffer_window_start: float, buffer_window_end: float) -> str:
        """
        Generate statistics summary for logging.

        Returns:
            Formatted string with Stage-3 summary
        """
        unique_speakers = len(self.last_segment_by_speaker)

        return (
            f"Emitted: {self.stats['emitted']}, "
            f"DroppedOverlap: {self.stats['dropped_overlap']}, "
            f"DroppedShort: {self.stats['dropped_short']}, "
            f"DroppedDuplicate: {self.stats['dropped_duplicate']}, "
            f"Coalesced: {self.stats['coalesced']}, "
            f"UniqueSpeakers: {unique_speakers}, "
            f"Window: [{buffer_window_start:.2f}, {buffer_window_end:.2f}]"
        )


def align_with_intersection_gate(
    whisper_segments: List[Dict],
    diarization,
    min_confidence: float = 0.1
) -> List[Dict]:
    """
    Fix #3: Intersection gate between ASR and diarization.

    Only emit segments where ASR words fall inside diarized speaker regions.
    DO NOT emit pure diarization segments with zero ASR words.

    Per Context7 pyannote docs: diarization.itertracks(yield_label=True)
    returns (turn, track, speaker) where turn has .start and .end in seconds.

    Args:
        whisper_segments: List of dicts with 'start', 'end', 'text'
        diarization: pyannote Annotation object
        min_confidence: Minimum overlap confidence to emit (default 0.1)

    Returns:
        List of aligned segments with speaker labels (only where overlap exists)
    """
    aligned_segments = []

    for whisper_seg in whisper_segments:
        start_time = whisper_seg['start']
        end_time = whisper_seg['end']
        text = whisper_seg['text'].strip()

        if not text or len(text) < 3:
            continue  # Skip very short/empty segments

        # Find overlapping speakers
        segment_duration = end_time - start_time
        speaker_durations = {}

        # Per Context7 pyannote docs: iterate diarization turns
        for turn, track, speaker in diarization.itertracks(yield_label=True):
            overlap_start = max(start_time, turn.start)
            overlap_end = min(end_time, turn.end)

            if overlap_start < overlap_end:  # There is overlap
                overlap_duration = overlap_end - overlap_start
                if speaker not in speaker_durations:
                    speaker_durations[speaker] = 0.0
                speaker_durations[speaker] += overlap_duration

        # Fix #3: Only emit if there's a diarization match
        if not speaker_durations:
            # No speaker overlap - DROP this segment
            # This prevents "Speaker 2: No speech detected" contradictions
            continue

        # Assign to speaker with most overlap
        dominant_speaker = max(speaker_durations, key=speaker_durations.get)
        confidence = speaker_durations[dominant_speaker] / segment_duration

        if confidence < min_confidence:
            # Insufficient overlap confidence - DROP
            continue

        aligned_segments.append({
            'start': start_time,
            'end': end_time,
            'text': text,
            'speaker_id': dominant_speaker,
            'confidence': confidence
        })

    return aligned_segments
