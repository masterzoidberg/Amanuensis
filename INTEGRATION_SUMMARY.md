# Transcript Stitching Integration Summary

## Implementation Complete ✓

All 5 fixes for transcript alignment have been successfully integrated into Amanuensis V2.

---

## Files Modified

### 1. **main.py** (4 locations)
- **Line 91**: Added import for `TranscriptStitcher` and `align_with_intersection_gate`
- **Lines 258-270**: Initialize TranscriptStitcher with config after settings load
- **Lines 3968-3979**: Load stitching config from settings file
- **Lines 5805-5807**: Set absolute session start time when recording begins
- **Lines 6366-6406**: Complete replacement of alignment pipeline with all 5 fixes

### 2. **transcript_stitch.py** (NEW)
- Complete implementation of all 5 fixes
- TranscriptStitcher class with state management
- align_with_intersection_gate function for Fix #3

### 3. **amanuensis_settings.json** (already exists)
- Stitching configuration section already present at lines 51-57

### 4. **test_stitcher_integration.py** (NEW)
- Comprehensive test suite for all 5 fixes
- All tests passing ✓

---

## Integration Points

### A. Initialization Flow

```python
# __init__ (line 269)
self.transcript_stitcher = TranscriptStitcher(self.stitching_config)
self.absolute_session_start_time = None
```

### B. Session Start

```python
# start_recording() (lines 5805-5807)
self.absolute_session_start_time = time.time()
self.transcript_stitcher.set_session_start(self.absolute_session_start_time)
```

### C. Diarization Pipeline

```python
# process_advanced_diarization() (lines 6366-6406)

# Fix #3: Intersection gate
aligned_segments = align_with_intersection_gate(whisper_segments, diarization, min_confidence=0.1)

# Map to speaker labels
labeled_segments = self.map_speakers_to_labels(aligned_segments)

# Fix #1: Calculate buffer window start
buffer_window_start = time.time() - self.absolute_session_start_time

# Fix #1-5: Stitch with all fixes
emittable_segments = self.transcript_stitcher.stitch_and_emit_segments(
    labeled_segments,
    buffer_window_start
)

# Format with absolute timestamps
for segment in emittable_segments:
    abs_time = self.absolute_session_start_time + segment['abs_start']
    timestamp = datetime.fromtimestamp(abs_time).strftime("%H:%M:%S")
    speaker_label = segment.get('speaker_label', segment.get('speaker', 'UNKNOWN'))
    formatted_text = f"[{timestamp}] {speaker_label}: {segment['text']}\n"
    self.process_transcription_with_phi(formatted_text)
```

### D. Updated Logging

```python
# Lines 6401-6406
stats_summary = self.transcript_stitcher.get_stats_summary(buffer_window_start, buffer_window_end)
print(f"Advanced diarization completed: {processing_time:.1f}s (RTF: {rtf:.2f}x)")
print(f"Stage-1 VAD/ASR: {len(whisper_segments)} segments (diarization may split speakers later)")
print(f"Stage-3 Stitching: {stats_summary}")
```

---

## Verification

### Integration Tests (test_stitcher_integration.py)

All tests **PASSED** ✓

1. **Fix #1: Absolute Timestamps** ✓
   - Each segment has unique per-segment timestamp
   - No more timestamp pile-up

2. **Fix #2: Overlap Deduplication** ✓
   - Segments from overlapping buffers are deduplicated
   - Watermark prevents re-processing

3. **Fix #3: Intersection Gate** ✓
   - Segments with no diarization match are dropped
   - No more "Speaker 2: No speech detected" contradictions

4. **Fix #4: Turn Coalescing** ✓
   - Rapid same-speaker segments merged (gap < 300ms)
   - "No, no, no." now appears as single line

5. **Fix #5: Idempotent Updates** ✓
   - Duplicate segments rejected via UID tracking
   - No duplicate appends to UI

---

## Configuration

### Settings File (amanuensis_settings.json)

```json
{
  "stitch": {
    "overlap_seconds": 5.0,
    "min_turn_seconds": 1.0,
    "min_turn_chars": 15,
    "coalesce_gap_seconds": 0.30,
    "dup_text_similarity": 0.95
  }
}
```

**Tunable Parameters**:
- `overlap_seconds`: Buffer overlap duration (default 5.0s)
- `min_turn_seconds`: Minimum turn duration (default 1.0s)
- `min_turn_chars`: Minimum character count (default 15)
- `coalesce_gap_seconds`: Max gap for merging (default 0.30s)
- `dup_text_similarity`: Jaccard threshold for dedup (default 0.95)

---

## Expected Behavior Changes

### Before Integration
- ❌ Many lines share timestamp (e.g., all "16:16:56")
- ❌ Duplicate segments from buffer overlap
- ❌ "Speaker 2: No speech detected" contradictions
- ❌ Fragmented micro-turns ("No," "no," "no.")
- ❌ Duplicate UI appends

### After Integration
- ✅ Each segment has unique absolute timestamp
- ✅ No duplicates from overlapping buffers
- ✅ Segments only emitted where ASR overlaps diarization
- ✅ Rapid same-speaker segments coalesced
- ✅ Idempotent UI updates with deduplication

---

## Next Steps

### For Testing
1. Run `python test_stitcher_integration.py` - Should see all PASS ✓
2. Start application: `python main.py`
3. Enable advanced diarization in settings
4. Record a test session with 2 speakers
5. Verify transcript has:
   - Unique timestamps per segment
   - No duplicates from buffer overlap
   - No ASR/diarization contradictions
   - Coalesced rapid utterances
   - Clean UI without duplicates

### For Monitoring
Watch console output for Stage-3 stitching stats:
```
Stage-1 VAD/ASR: 12 segments (diarization may split speakers later)
Stage-3 Stitching: Emitted: 8, DroppedOverlap: 3, DroppedShort: 0,
  DroppedDuplicate: 1, Coalesced: 2, UniqueSpeakers: 2, Window: [30.00, 60.00]
```

---

## Technical Notes

### Context7 Documentation Used
- `/systran/faster-whisper` (Trust: 6.8) - Segment timestamp handling
- `/pyannote/pyannote-audio` (Trust: 9.1) - Diarization alignment
- `/tomschimansky/customtkinter` (Trust: 8.7) - Thread-safe UI updates

### Key Implementation Details

**Fix #1**: Absolute timestamps from `buffer_window_start + segment.start`

**Fix #2**: Watermark pattern - segments with `abs_start < last_committed_end_time` are dropped

**Fix #3**: Intersection gate - only emit segments where ASR overlaps diarization turns

**Fix #4**: Coalesce if same speaker, gap < 300ms, combined duration ≤ 6s

**Fix #5**: Stable UID = `f"{int(abs_start*1000)}-{int(abs_end*1000)}-{speaker}"` with LRU deque

---

## Status: READY FOR PRODUCTION ✓

All integration tests pass. The transcript stitching module is fully integrated and operational.
