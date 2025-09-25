#!/usr/bin/env python3
"""
Test script to verify the SessionStorageManager assertions pass
"""

import time

def test_session_storage_assertions():
    """Test session storage with assertions like the main test"""
    print("Testing Session Storage with assertions...")

    try:
        from session_storage_manager import SessionStorageManager

        # Create storage manager
        storage = SessionStorageManager()
        assert storage is not None, "Storage manager should not be None"
        print("PASS: Storage manager created")

        # Test session creation
        session_id = storage.start_session({
            'test': True,
            'session_type': 'test'
        })
        assert session_id is not None, "Session ID should not be None"
        assert isinstance(session_id, str), "Session ID should be string"
        print(f"PASS: Session created with ID: {session_id}")

        # Test transcript segment saving - THIS IS THE CRITICAL TEST
        class MockSegment:
            def __init__(self, text, speaker, start_time):
                self.text = text
                self.speaker = speaker
                self.start_time = start_time
                self.end_time = start_time + 2
                self.confidence = 0.9
                self.is_partial = False

        segment = MockSegment("Test transcript", "TestSpeaker", time.time())
        success = storage.save_transcript_segment(segment)
        assert success, "Should successfully save transcript segment"
        print("PASS: Transcript segment saved successfully (bug fixed!)")

        # Test session info - THIS WAS ANOTHER PLACE WITH THE BUG
        info = storage.get_session_info()
        assert info is not None, "Session info should not be None"
        assert info['session_id'] == session_id, "Session ID should match"
        print("PASS: Session info retrieved successfully")

        # Test session ending
        end_info = storage.end_session()
        assert end_info is not None, "End session should return info"
        assert end_info['stats']['total_segments'] > 0, "Should have recorded segments"
        print("PASS: Session ended successfully")

        # Test storage stats
        stats = storage.get_storage_stats()
        assert isinstance(stats, dict), "Storage stats should be dict"
        print("PASS: Storage stats retrieved")

        print("SUCCESS: All session storage tests passed!")
        return True

    except Exception as e:
        print(f"FAILED: Session storage test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_session_storage_assertions()