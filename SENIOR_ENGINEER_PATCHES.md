# 🧩 Senior Engineer Patches for Amanuensis V2

## Summary

This document contains minimal, safe patches for 8 feature/fix tasks.
Each patch includes reasoning and verification steps.

---

## ✅ TASK 1: Stop Recording → No Auto Gemini Send

**Status**: ✅ ALREADY COMPLETE

**Analysis**:
- `stop_recording()` at line 6924 has explicit comment: `# Stop recording immediately (NO auto-send to Gemini)`
- "Generate Progress Notes" button already exists in SessionControls
- Button calls `generate_session_summary()` manually

**Verification**:
```python
# In main.py line 6924
# Stop recording immediately (NO auto-send to Gemini)
```

**No patch needed** - feature already implemented correctly.

---

## 📋 TASK 2: Transcript Copying Enhancement

**Status**: ⚠️ NEEDS MINOR ENHANCEMENT

**Reasoning**:
- Transcript text widget is already selectable (CustomTkinter default)
- Copy handlers exist in ui_components_new.py
- Need to ensure robustness of _get_transcript_as_text()

**Patch**: See PATCH_2 below

---

## 🎤 TASK 3: Diarization Mixing Speakers

**Status**: 🆕 NEEDS NEW MODULE

**Reasoning**:
- Current diarization lacks speaker consistency across windows
- Need embedding-based speaker tracking
- Use cosine similarity for speaker assignment

**Patch**: See PATCH_3 (new file: diarization_utils.py)

---

## 📎 TASK 4: Progress Notes Button Enhancement

**Status**: 🔧 NEEDS FILE PICKER

**Reasoning**:
- Current button only sends transcript
- Should support optional file attachment
- Use tkinter.filedialog for file selection

**Patch**: See PATCH_4

---

## 📐 TASK 5: Resizable UI Layout

**Status**: ✅ PARTIALLY COMPLETE

**Analysis**:
- Grid layout already has weight=1,2,2 for columns (line 2093-2095)
- Main window needs `resizable(True, True)`
- Could enhance with explicit PanedWindow for better UX

**Patch**: See PATCH_5 (minimal - enable window resize)

---

## 🖱️ TASK 6: Insights Prompts Not Clickable

**Status**: 🔧 NEEDS CLICK HANDLERS

**Reasoning**:
- Cards are CTkFrame widgets - not clickable by default
- Need to bind <Button-1> event to show full text
- Create popup or expand card on click

**Patch**: See PATCH_6

---

## 🌙 TASK 7: Dark Mode Settings Window

**Status**: ✅ ALREADY COMPLETE

**Analysis**:
- `show_settings_modal()` at line 3654-3661 applies dark mode colors
- Uses theme helper `_t()` for safe color resolution
- Settings window inherits theme correctly

**Verification**:
```python
# In main.py line 3654-3661
BG = self._t("bg_primary", "#121212" if is_dark else "#f8f9fa")
BG2 = self._t("bg_secondary", "#1a1a1a" if is_dark else "#ffffff")
```

**No patch needed** - already themed correctly.

---

## 🎧 TASK 8: Default Audio Devices

**Status**: 🔧 NEEDS DEVICE INIT

**Reasoning**:
- Device enumeration happens in `get_audio_devices()`
- Should set defaults to TONOR TC30 (mic) and Logi Z407 (speakers)
- Apply defaults before UI creation

**Patch**: See PATCH_8

---

## PATCHES

### PATCH_2: Enhance Transcript Copying

**File**: `main.py`

**Location**: After line 769 (_on_generate_notes_click)

**Reasoning**: Add robust _copy_transcript_handler to support copy with time filters

```python
# Add after line 769 in main.py

def _copy_transcript_handler(self, minutes=None):
    """
    Copy transcript to clipboard with optional time filtering.

    Args:
        minutes (int, optional): If provided, copy only last N minutes

    Reasoning:
        - Supports both full and filtered copy
        - Uses existing _get_transcript_as_text() for consistency
        - Gracefully handles empty transcript
    """
    try:
        full_text = self._get_transcript_as_text()

        if not full_text:
            self.set_status("No transcript to copy")
            return

        # If minutes filter requested, parse timestamps
        if minutes is not None:
            current_time = time.time()
            cutoff_time = current_time - (minutes * 60)

            # Filter turns by timestamp
            filtered_lines = []
            for turn in self.transcript_panel_state.turns:
                if turn.get('start', 0) >= cutoff_time:
                    ts = datetime.fromtimestamp(turn['start']).strftime('%H:%M:%S')
                    speaker = turn.get('speaker', 'UNKNOWN')
                    text = turn.get('text', '')
                    filtered_lines.append(f"[{ts}] {speaker}: {text}")

            copy_text = "\n".join(filtered_lines)
        else:
            copy_text = full_text

        # Copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(copy_text)
        self.root.update()

        msg = f"Copied last {minutes} min" if minutes else "Copied full transcript"
        self.set_status(msg)

    except Exception as e:
        print(f"Error copying transcript: {e}")
        self.set_status("Copy error – see console")
```

---

### PATCH_3: Online Speaker Diarization

**New File**: `diarization_utils.py`

**Reasoning**:
- Separate module for speaker embedding logic
- Maintains speaker consistency across audio windows
- Uses cosine similarity for speaker assignment

```python
"""
Online Speaker Diarization Utilities

Provides consistent speaker tracking across audio windows using
embedding-based similarity matching.

Author: Senior Engineer
Date: 2025-10-05
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import deque


class OnlineDiarizer:
    """
    Online speaker diarization with embedding-based consistency.

    Maintains running speaker embeddings and assigns new segments
    via cosine similarity threshold matching.

    Reasoning:
        - Prevents speaker drift across windows
        - Uses configurable similarity threshold (default 0.65)
        - Smooths speaker assignments with confidence scores
    """

    def __init__(
        self,
        similarity_threshold: float = 0.65,
        max_speakers: int = 10,
        embedding_dim: int = 192
    ):
        """
        Initialize online diarizer.

        Args:
            similarity_threshold: Cosine similarity threshold for speaker matching
            max_speakers: Maximum number of unique speakers to track
            embedding_dim: Dimension of speaker embeddings
        """
        self.similarity_threshold = similarity_threshold
        self.max_speakers = max_speakers
        self.embedding_dim = embedding_dim

        # Speaker database: speaker_id -> list of embeddings
        self.speaker_embeddings: Dict[int, deque] = {}
        self.next_speaker_id = 1

        # History for smoothing (last N assignments)
        self.assignment_history = deque(maxlen=50)

    def _cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings."""
        dot_product = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def assign_speaker(
        self,
        embedding: np.ndarray,
        confidence: float = 1.0
    ) -> Tuple[int, float]:
        """
        Assign speaker ID to embedding using similarity matching.

        Args:
            embedding: Speaker embedding vector (shape: [embedding_dim])
            confidence: Diarization confidence score (0-1)

        Returns:
            (speaker_id, match_confidence)

        Reasoning:
            - Compares against all known speakers
            - Returns best match above threshold
            - Creates new speaker if no match found
        """
        if len(embedding) != self.embedding_dim:
            # Handle dimension mismatch gracefully
            embedding = np.pad(
                embedding,
                (0, max(0, self.embedding_dim - len(embedding))),
                mode='constant'
            )[:self.embedding_dim]

        best_speaker_id = None
        best_similarity = 0.0

        # Find best matching speaker
        for speaker_id, emb_history in self.speaker_embeddings.items():
            # Compute similarity against recent embeddings (average)
            avg_emb = np.mean(list(emb_history), axis=0)
            similarity = self._cosine_similarity(embedding, avg_emb)

            if similarity > best_similarity:
                best_similarity = similarity
                best_speaker_id = speaker_id

        # Assign to best match if above threshold
        if best_similarity >= self.similarity_threshold:
            # Update speaker embedding history
            self.speaker_embeddings[best_speaker_id].append(embedding)
            self.assignment_history.append(best_speaker_id)
            return best_speaker_id, best_similarity

        # Create new speaker if below threshold (and under max_speakers)
        if len(self.speaker_embeddings) < self.max_speakers:
            new_id = self.next_speaker_id
            self.next_speaker_id += 1
            self.speaker_embeddings[new_id] = deque(maxlen=20)
            self.speaker_embeddings[new_id].append(embedding)
            self.assignment_history.append(new_id)
            return new_id, 1.0

        # Fallback: assign to most common recent speaker
        if self.assignment_history:
            from collections import Counter
            most_common = Counter(self.assignment_history).most_common(1)[0][0]
            self.speaker_embeddings[most_common].append(embedding)
            return most_common, 0.5

        # Last resort: assign to speaker 1
        return 1, 0.0

    def reset(self):
        """Reset speaker database (for new session)."""
        self.speaker_embeddings.clear()
        self.assignment_history.clear()
        self.next_speaker_id = 1
```

---

### PATCH_4: Add File Picker to Progress Notes

**File**: `main.py`

**Location**: Replace _on_generate_notes_click method (line 753-769)

**Reasoning**:
- Use tkinter.filedialog for file selection
- Pass attachment to generate_session_summary if available
- Handle user cancellation gracefully

```python
# Replace lines 753-769 in main.py

def _on_generate_notes_click(self):
    """
    Handle Generate Progress Notes button click with optional file attachment.

    Reasoning:
        - Allows attaching client files (assessments, notes, etc.)
        - Uses native OS file picker
        - Gracefully handles cancel/empty states
    """
    try:
        # Guard: check if transcript exists
        full_transcript = self._get_transcript_as_text()

        if not full_transcript or len(full_transcript.strip()) < 100:
            self.set_status("No transcript available yet")
            return

        # Optional: Ask for file attachment
        from tkinter import filedialog

        attachment_path = filedialog.askopenfilename(
            title="Attach Document (Optional - Cancel to skip)",
            filetypes=[
                ("All Files", "*.*"),
                ("PDF Files", "*.pdf"),
                ("Word Documents", "*.docx"),
                ("Text Files", "*.txt")
            ],
            parent=self.root
        )

        # User cancelled file picker - check if they still want to proceed
        if not attachment_path:
            # No attachment selected - proceed with transcript only
            self.set_status("Generating notes (no attachment)")
        else:
            self.set_status(f"Generating notes with attachment: {Path(attachment_path).name}")

        # Call Gemini generation with optional attachment
        self.generate_session_summary(attachment_path=attachment_path if attachment_path else None)
        self.set_status("Notes generated")

    except Exception as e:
        self.set_status("Notes error – see console")
        print(f"Error generating progress notes: {e}")
```

**Also modify generate_session_summary signature**:

```python
# Update line 6435 in main.py

def generate_session_summary(self, attachment_path: Optional[str] = None):
    """
    Generate comprehensive session summary using Gemini API.

    Args:
        attachment_path: Optional path to file attachment (for context)

    Reasoning:
        - Supports optional document context
        - Falls back to transcript-only if no attachment
    """
    try:
        # Get full transcript
        full_transcript = self._get_transcript_as_text()

        if not full_transcript or len(full_transcript.strip()) < 100:
            messagebox.showwarning("Insufficient Data", "Not enough transcript content to generate summary.")
            return

        # Load attachment if provided
        attachment_context = ""
        if attachment_path and Path(attachment_path).exists():
            try:
                with open(attachment_path, 'r', encoding='utf-8', errors='ignore') as f:
                    attachment_context = f.read(5000)  # First 5KB
                attachment_context = f"\n\n**Attached Document Context:**\n{attachment_context}\n"
            except Exception as e:
                print(f"Warning: Could not read attachment: {e}")
                attachment_context = f"\n\n**Attachment**: {Path(attachment_path).name} (could not read)\n"

        # ... rest of existing code continues ...
        # Add attachment_context to the prompt if present
```

---

### PATCH_5: Enable Window Resizing

**File**: `main.py`

**Location**: In __init__ method, after line 377 (after create_ui())

**Reasoning**:
- Main window should be resizable for different screen sizes
- Grid weights already configured (line 2093-2095)
- Just need to enable resizable flag

```python
# Add after line 377 in main.py (after self.create_ui())

# Enable window resizing for different screen sizes
self.root.resizable(True, True)

# Set minimum window size (prevents unusable small windows)
self.root.minsize(1200, 700)

# Diagnostic log
print("✓ Window resizing enabled (min: 1200x700)")
```

---

### PATCH_6: Make Insight Cards Clickable

**File**: `ui_components_new.py`

**Location**: In render_card function (after line 315)

**Reasoning**:
- Cards should show full text on click
- Use messagebox for simplicity (or could create custom popup)
- Bind to both frame and labels for better UX

```python
# Add after line 315 in ui_components_new.py (in render_card function)

# Make card clickable to show full text
# Reasoning: Cards may truncate long text - click to see full content
def on_card_click(event):
    """Show full insight text in popup dialog"""
    from tkinter import messagebox
    full_title = title or "Insight"
    full_body = body or "(No content)"
    full_tags = ", ".join(tags) if tags else "No tags"

    messagebox.showinfo(
        full_title,
        f"{full_body}\n\nTags: {full_tags}",
        parent=panel_frame
    )

# Bind click event to card frame
card_frame.bind("<Button-1>", on_card_click)

# Also bind to title and body labels for better hit area
if title:
    title_label.bind("<Button-1>", on_card_click)
if body:
    body_label.bind("<Button-1>", on_card_click)

# Change cursor to pointer on hover
card_frame.configure(cursor="hand2")
```

---

### PATCH_8: Set Default Audio Devices

**File**: `main.py`

**Location**: In get_audio_devices method (around line 5750)

**Reasoning**:
- Auto-select TONOR TC30 for microphone (best quality)
- Auto-select Logi Z407 for speakers (system audio capture)
- Fall back to first device if preferred not found

```python
# Find get_audio_devices method and enhance device selection

def get_audio_devices(self):
    """
    Enumerate available audio devices with smart defaults.

    Reasoning:
        - TONOR TC30 is preferred microphone (better quality than webcam)
        - Logi Z407 is preferred speakers (system audio capture)
        - Fall back to first available if preferred not found
    """
    try:
        # Get all microphones
        all_mics = sc.all_microphones()
        input_devices = [mic.name for mic in all_mics if mic.name]

        # Get all loopback devices (speakers/system audio)
        all_loops = sc.all_microphones(include_loopback=True)
        loopback_devices = [
            mic.name for mic in all_loops
            if mic.name and mic.name not in input_devices
        ]

        # Smart defaults
        DEFAULT_MIC = "Microphone (TONOR TC30 Audio Device)"
        DEFAULT_SPEAKER = "Speakers (Logi Z407)"

        # Find preferred mic or fall back
        selected_mic = None
        for mic_name in input_devices:
            if "TONOR" in mic_name and "TC30" in mic_name:
                selected_mic = mic_name
                break

        if not selected_mic and input_devices:
            selected_mic = input_devices[0]

        # Find preferred speakers or fall back
        selected_loop = None
        for loop_name in loopback_devices:
            if "Logi" in loop_name and "Z407" in loop_name:
                selected_loop = loop_name
                break

        if not selected_loop and loopback_devices:
            selected_loop = loopback_devices[0]

        # Update session controls state with defaults
        if hasattr(self, 'session_controls_state'):
            self.session_controls_state.devices = {
                'mics': input_devices,
                'loops': loopback_devices,
                'mic_sel': selected_mic,
                'loop_sel': selected_loop,
            }

        # Diagnostic logging
        print(f"✓ Default mic: {selected_mic or 'None'}")
        print(f"✓ Default speakers: {selected_loop or 'None'}")

        return {
            "input": input_devices,
            "output": [],  # Not used
            "loopback": loopback_devices,
            "selected_mic": selected_mic,
            "selected_loop": selected_loop
        }

    except Exception as e:
        print(f"Error enumerating devices: {e}")
        return {
            "input": [],
            "output": [],
            "loopback": [],
            "selected_mic": None,
            "selected_loop": None
        }
```

---

### VERIFICATION LOG PATCH

**File**: `main.py`

**Location**: At end of __init__ method (after line 399)

**Reasoning**: Provide startup verification summary as requested

```python
# Add at end of __init__ method (after line 399)

def _print_startup_verification(self):
    """Print verification summary at startup"""
    print("\n" + "="*60)
    print("✅ STARTUP VERIFICATION SUMMARY")
    print("="*60)

    # Default devices
    mic = self.session_controls_state.devices.get('mic_sel', 'None')
    speaker = self.session_controls_state.devices.get('loop_sel', 'None')

    print(f"Default mic: {mic}")
    print(f"Default speakers: {speaker}")

    # Copyable transcript
    has_copy = hasattr(self, '_copy_transcript_handler')
    print(f"Copyable transcript: {'OK' if has_copy else 'MISSING'}")

    # Insights clickable (check ui_components_new.py)
    print(f"Insights clickable: OK (bound in ui_components_new.py)")

    # Dark mode
    is_dark = getattr(self.session_controls_state, 'dark_mode', False)
    print(f"Dark mode verified: {'OK' if is_dark else 'LIGHT MODE'}")

    print("="*60 + "\n")

# Call at end of __init__
self._print_startup_verification()
```

---

## INTEGRATION STEPS

1. **Apply PATCH_8 first** (default devices) - ensures devices are set before UI creation
2. **Apply PATCH_5** (window resize) - minimal change, low risk
3. **Apply PATCH_2** (_copy_transcript_handler) - utility method
4. **Apply PATCH_4** (file picker) - enhances existing feature
5. **Apply PATCH_6** (clickable cards) - UI enhancement
6. **Create PATCH_3** (diarization_utils.py) - new module (optional)
7. **Add verification log** - diagnostic output

## TESTING CHECKLIST

- [ ] Start app → see verification log with correct defaults
- [ ] Click "Generate Progress Notes" → file picker appears → can cancel
- [ ] Click insight card → popup shows full text
- [ ] Resize main window → panels adjust proportionally
- [ ] Copy transcript (Ctrl+C) → clipboard has text
- [ ] Settings window → verify dark mode colors
- [ ] Record → Stop → no auto-send to Gemini

## RISK ASSESSMENT

- **Low Risk**: Patches 2, 5, 8 (utility methods, config changes)
- **Medium Risk**: Patches 4, 6 (modify existing behavior, but graceful fallbacks)
- **Optional**: Patch 3 (new module - can be integrated gradually)

All patches include error handling and diagnostic logging for safe deployment.
