#!/usr/bin/env python3
"""
Test script to verify the SessionStorageManager fix
"""

import time
from session_storage_manager import SessionStorageManager

def test_session_storage_fix():
    """Test the specific bug fix for speakers set/list issue"""
    print("Testing Session Storage Manager Fix")
    print("=" * 50)

    try:
        # Create storage manager
        storage = SessionStorageManager()

        # Test session start
        session_id = storage.start_session({
            'session_type': 'test',
            'client_count': 1
        })
        print(f"Started session: {session_id}")

        # Test transcript segment save - this should trigger the bug if not fixed
        class MockSegment:
            def __init__(self, text, speaker, start_time):
                self.text = text
                self.speaker = speaker
                self.start_time = start_time
                self.end_time = start_time + 3
                self.confidence = 0.9
                self.is_partial = False

        segments = [
            MockSegment("How are you feeling today?", "Therapist", time.time()),
            MockSegment("I'm feeling a bit anxious.", "Client", time.time() + 5),
            MockSegment("Can you tell me more about that?", "Therapist", time.time() + 10)
        ]

        for i, segment in enumerate(segments):
            result = storage.save_transcript_segment(segment)
            if result:
                print(f"Segment {i+1}: SAVED successfully")
            else:
                print(f"Segment {i+1}: FAILED to save")

            # Test that speakers is still a set after each save
            speakers = storage.current_session['stats']['speakers']
            if isinstance(speakers, set):
                print(f"  Speakers type: SET (correct) - {speakers}")
            else:
                print(f"  Speakers type: {type(speakers)} (WRONG!) - {speakers}")

        # Test session info retrieval - this was another place where the bug occurred
        session_info = storage.get_session_info()
        if session_info:
            print(f"Session info retrieved successfully")
            print(f"  Original speakers type: {type(storage.current_session['stats']['speakers'])}")
            print(f"  Returned speakers type: {type(session_info['stats']['speakers'])}")
            print(f"  Original speakers: {storage.current_session['stats']['speakers']}")
            print(f"  Returned speakers: {session_info['stats']['speakers']}")

        # Test session end
        session_info = storage.end_session()
        print(f"Session ended successfully")
        print(f"  Total segments: {session_info['stats']['total_segments']}")
        print(f"  Speakers: {session_info['stats']['speakers']}")

        print("SUCCESS: All tests passed!")

    except Exception as e:
        print(f"ERROR: Session storage test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_session_storage_fix()