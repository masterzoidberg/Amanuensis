"""
Online Speaker Diarization Utilities

Provides consistent speaker tracking across audio windows using
embedding-based similarity matching.

Author: Senior Engineer (PATCH_3)
Date: 2025-10-05

Reasoning:
    - Prevents speaker drift across windows
    - Uses configurable similarity threshold (default 0.65)
    - Smooths speaker assignments with confidence scores
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import deque


class OnlineDiarizer:
    """
    Online speaker diarization with embedding-based consistency.

    Maintains running speaker embeddings and assigns new segments
    via cosine similarity threshold matching.

    Usage:
        diarizer = OnlineDiarizer(similarity_threshold=0.65)
        speaker_id, confidence = diarizer.assign_speaker(embedding)
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
            embedding_dim: Dimension of speaker embeddings (pyannote default: 512, can be 192)
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

    def get_speaker_count(self) -> int:
        """Get number of unique speakers identified."""
        return len(self.speaker_embeddings)

    def get_speaker_stats(self) -> Dict[int, int]:
        """Get assignment counts per speaker."""
        from collections import Counter
        return dict(Counter(self.assignment_history))


# Integration example for main.py:
#
# In __init__:
#     from diarization_utils import OnlineDiarizer
#     self.online_diarizer = OnlineDiarizer(similarity_threshold=0.65)
#
# In process_audio_buffer_with_vad or align_whisper_with_pyannote:
#     for segment in diarized_segments:
#         embedding = segment.get('embedding')  # from pyannote
#         speaker_id, confidence = self.online_diarizer.assign_speaker(embedding)
#         segment['speaker_id'] = speaker_id
#         segment['speaker_confidence'] = confidence
