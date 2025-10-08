# Transcript Stitching - Code Changes Diff

## Summary of Changes

**Files Modified**: 1 (main.py)
**Files Created**: 3 (transcript_stitch.py, test_stitcher_integration.py, INTEGRATION_SUMMARY.md)
**Total Lines Changed**: ~520 lines

---

## 1. main.py - Import Addition

**Location**: Line 90-91

```diff
 # Pyannote.audio imports for advanced speaker diarization
 try:
     from pyannote.audio import Pipeline
     import librosa
     PYANNOTE_AVAILABLE = True
 except ImportError:
     PYANNOTE_AVAILABLE = False
     print("WARNING: Pyannote.audio not available. Install pyannote.audio for advanced speaker diarization.")

+# Transcript stitching module - Fix #1-5 for alignment issues
+from transcript_stitch import TranscriptStitcher, align_with_intersection_gate
+
 class AmanuensisApp:
     def __init__(self):
```

**Why**: Import the new transcript stitching module with all 5 fixes.

---

## 2. main.py - TranscriptStitcher Initialization

**Location**: Lines 255-270

```diff
         # Load user settings from config file
         self.load_settings_from_config()

+        # Initialize transcript stitcher - Fix #1-5
+        # Must be after load_settings_from_config() to have stitching_config available
+        if not hasattr(self, 'stitching_config'):
+            # Fallback if config loading failed
+            self.stitching_config = {
+                'overlap_seconds': 5.0,
+                'min_turn_seconds': 1.0,
+                'min_turn_chars': 15,
+                'coalesce_gap_seconds': 0.30,
+                'dup_text_similarity': 0.95
+            }
+        self.transcript_stitcher = TranscriptStitcher(self.stitching_config)
+        self.absolute_session_start_time = None  # Set when recording starts
+
         # Verify all required attributes are initialized
         self.verify_attribute_initialization()
```

**Why**: Create stitcher instance with configuration. Fallback ensures robustness if config load fails.

---

## 3. main.py - Load Stitching Config

**Location**: Lines 3965-3979

```diff
                         if 'discontinuity_warning_throttle' in audio and isinstance(audio['discontinuity_warning_throttle'], int):
                             self.discontinuity_warning_throttle = max(1, audio['discontinuity_warning_throttle'])

+                    # Stitching settings - Fix #1-5 configuration
+                    if 'stitch' in config and isinstance(config['stitch'], dict):
+                        self.stitching_config = config['stitch']
+                    else:
+                        # Default stitching configuration
+                        self.stitching_config = {
+                            'overlap_seconds': 5.0,
+                            'min_turn_seconds': 1.0,
+                            'min_turn_chars': 15,
+                            'coalesce_gap_seconds': 0.30,
+                            'dup_text_similarity': 0.95
+                        }
+
                     print("Settings loaded successfully from amanuensis_settings.json")
                 else:
                     print("Invalid configuration file format, using defaults")
```

**Why**: Load stitching parameters from settings file with safe defaults.

---

## 4. main.py - Set Session Start Time

**Location**: Lines 5799-5807

```diff
             # Create session info
             self.current_session = datetime.now()
             self.session_start_time = time.time()  # Initialize for dashboard metrics
             session_name = self.current_session.strftime("%Y-%m-%d_%H-%M-%S")
             self.session_info_label.configure(text=f"Session: {session_name}")

+            # Fix #1: Set absolute session start time for transcript stitcher
+            self.absolute_session_start_time = time.time()
+            self.transcript_stitcher.set_session_start(self.absolute_session_start_time)
+
             # Clear placeholder and prepare transcript area
             self.clear_transcript_placeholder()
             self.transcript_text.delete("1.0", "end")
```

**Why**: Fix #1 requires absolute session start time to compute per-segment timestamps.

---

## 5. main.py - Alignment Pipeline Replacement

**Location**: Lines 6366-6406 (Major Change)

```diff
             # Stage 3: Align Whisper text with pyannote speakers
-            print("Stage 3: Aligning text with speakers...")
-            aligned_segments = self.align_whisper_with_pyannote(whisper_segments, diarization)
+            # Fix #3: Use intersection gate to prevent ASR/diarization contradictions
+            print("Stage 3: Aligning text with speakers (intersection gate)...")
+            aligned_segments = align_with_intersection_gate(whisper_segments, diarization, min_confidence=0.1)

             # Stage 4: Map speakers to Speaker 1/Speaker 2 labels
             labeled_segments = self.map_speakers_to_labels(aligned_segments)

-            # Add to transcript with advanced diarization indicator
-            for segment in labeled_segments:
-                timestamp = datetime.now().strftime("%H:%M:%S")
-                speaker_label = segment['speaker']
+            # Fix #1: Calculate buffer window start time for absolute timestamps
+            buffer_window_start = time.time() - self.absolute_session_start_time if self.absolute_session_start_time else 0.0
+
+            # Stage 5: Stitch segments with all fixes applied (dedupe, coalesce, timestamps)
+            # Fix #1-5: Per-segment timestamps, overlap dedup, coalescing, idempotent UI
+            emittable_segments = self.transcript_stitcher.stitch_and_emit_segments(
+                labeled_segments,
+                buffer_window_start
+            )
+
+            # Add to transcript with absolute timestamps
+            for segment in emittable_segments:
+                # Format absolute timestamp from session start
+                abs_time = self.absolute_session_start_time + segment['abs_start'] if self.absolute_session_start_time else segment['abs_start']
+                timestamp = datetime.fromtimestamp(abs_time).strftime("%H:%M:%S")
+                speaker_label = segment.get('speaker_label', segment.get('speaker', 'UNKNOWN'))
                 text = segment['text']

-                # Add indicator for advanced diarization
                 formatted_text = f"[{timestamp}] {speaker_label}: {text}\n"

                 # Process through PHI detection and analysis pipeline
                 self.process_transcription_with_phi(formatted_text)

             # Performance tracking
             processing_time = time.time() - start_time
             rtf = processing_time / audio_duration

-            print(f"Advanced diarization completed: {processing_time:.1f}s (RTF: {rtf:.2f}x)")
+            # Fix: Updated logging with stitcher statistics
+            buffer_window_end = buffer_window_start + audio_duration
+            stats_summary = self.transcript_stitcher.get_stats_summary(buffer_window_start, buffer_window_end)
+            print(f"Advanced diarization completed: {processing_time:.1f}s (RTF: {rtf:.2f}x)")
+            print(f"Stage-1 VAD/ASR: {len(whisper_segments)} segments (diarization may split speakers later)")
+            print(f"Stage-3 Stitching: {stats_summary}")

             # Update performance stats
             self.performance_stats['rtf_values'].append(rtf)
```

**Why**: Complete replacement of alignment logic with all 5 fixes:
- **Fix #1**: Absolute timestamps from buffer_window_start + segment offset
- **Fix #2**: Handled in stitcher (overlap dedup)
- **Fix #3**: Intersection gate drops segments with no diarization match
- **Fix #4**: Coalescing handled in stitcher
- **Fix #5**: Idempotent updates handled in stitcher

---

## 6. main.py - Speaker Mapping Update

**Location**: Lines 6552-6561

```diff
             labeled_segments.append({
                 'start': segment['start'],
                 'end': segment['end'],
                 'text': segment['text'],
                 'speaker': speaker_label,
+                'speaker_label': speaker_label,  # For stitcher compatibility
+                'speaker_id': speaker_id,  # Keep original ID for stitcher
                 'confidence': segment['confidence'],
                 'original_speaker_id': speaker_id
             })
```

**Why**: Add speaker_label field for stitcher compatibility (Fix #4 needs speaker info for coalescing).

---

## 7. transcript_stitch.py - NEW FILE

**Complete Implementation**: 369 lines

### Key Components

**TranscriptStitcher Class**:
```python
class TranscriptStitcher:
    def __init__(self, config: Dict):
        # Fix #2: Overlap de-dup watermark
        self.last_committed_end_time = 0.0

        # Fix #5: Idempotent UI updates
        self.emitted_segment_uids = deque(maxlen=200)
        self.last_segment_by_speaker = {}
```

**Core Methods**:
1. `stitch_and_emit_segments()` - Main stitching with Fixes #1, #2, #4, #5
2. `_coalesce_turns()` - Fix #4 implementation
3. `_compute_segment_uid()` - Fix #5 stable UID generation
4. `_compute_text_similarity()` - Fix #5 Jaccard similarity
5. `get_stats_summary()` - Formatted statistics for logging

**align_with_intersection_gate()** - Fix #3 standalone function:
```python
def align_with_intersection_gate(
    whisper_segments: List[Dict],
    diarization,
    min_confidence: float = 0.1
) -> List[Dict]:
    # Only emit segments where ASR overlaps diarization
    if not speaker_durations:
        continue  # DROP segment with no speaker match
```

---

## 8. test_stitcher_integration.py - NEW FILE

**Test Coverage**: 258 lines, 5 test functions

All tests **PASSING** ✓:
- `test_fix_1_absolute_timestamps()` ✓
- `test_fix_2_overlap_deduplication()` ✓
- `test_fix_3_intersection_gate()` ✓
- `test_fix_4_coalescing()` ✓
- `test_fix_5_idempotent_updates()` ✓

---

## 9. amanuensis_settings.json - Already Exists

**Config Section** (Lines 51-57):
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

**Why**: Already present in settings file, no changes needed.

---

## Testing Verification

### Pre-Integration Issues
❌ Timestamp pile-up (all segments same time)
❌ Duplicate segments from overlap
❌ ASR/diarization contradictions
❌ Fragmented micro-turns
❌ Duplicate UI appends

### Post-Integration Status
✅ Unique per-segment timestamps
✅ Overlap deduplication working
✅ Intersection gate prevents contradictions
✅ Turn coalescing functional
✅ Idempotent UI updates

**Test Command**: `python test_stitcher_integration.py`
**Result**: All 5 tests PASS ✓

---

## Context7 Documentation References

Per user requirements, all implementation based on authoritative docs:

1. **faster-whisper** (`/systran/faster-whisper`, Trust: 6.8)
   - Segment timestamps are relative to audio buffer
   - Word-level timestamps available
   - Generator pattern requires iteration

2. **pyannote.audio** (`/pyannote/pyannote-audio`, Trust: 9.1)
   - Diarization returns Annotation with `.itertracks(yield_label=True)`
   - Turn timestamps relative to audio start
   - Alignment via overlap computation

3. **CustomTkinter** (`/tomschimansky/customtkinter`, Trust: 8.7)
   - Thread-safe updates via `root.after()`
   - Widget existence check with `winfo_exists()`
   - Text widget operations for UI updates

---

## Deployment Checklist

- [✓] All syntax checks pass
- [✓] Integration tests pass (5/5)
- [✓] Configuration loaded from settings
- [✓] Backwards compatible (fallback defaults)
- [✓] Documentation complete
- [✓] No breaking API changes
- [✓] Python 3.10 compatible

**Status**: READY FOR PRODUCTION ✓
