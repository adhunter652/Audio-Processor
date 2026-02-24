"""RAG: index transcript segments and meeting topics; search with local embeddings."""
from .store import (
    index_transcript_segments,
    index_meeting,
    search_transcript_segments,
    search_meetings,
)

__all__ = [
    "index_transcript_segments",
    "index_meeting",
    "search_transcript_segments",
    "search_meetings",
]
