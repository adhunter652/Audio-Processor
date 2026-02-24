"""ChromaDB + sentence-transformers for transcript and meeting RAG. All local."""
from pathlib import Path
import sys

# Project root for config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import RAG_DIR, RAG_EMBEDDING_MODEL, RAG_SEARCH_LIMIT

RAG_DIR.mkdir(parents=True, exist_ok=True)

_COLLECTION_TRANSCRIPTS = "transcript_segments"
_COLLECTION_MEETINGS = "meetings"

_embedding_model = None
_chroma_client = None
_chroma_transcripts = None
_chroma_meetings = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(RAG_EMBEDDING_MODEL)
    return _embedding_model


def _embed(texts: list[str]) -> list[list[float]]:
    model = _get_embedding_model()
    return model.encode(texts, convert_to_numpy=True).tolist()


def _get_chroma():
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        from chromadb.config import Settings
        _chroma_client = chromadb.PersistentClient(
            path=str(RAG_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
    return _chroma_client


def _get_transcripts_collection():
    global _chroma_transcripts
    if _chroma_transcripts is None:
        client = _get_chroma()
        _chroma_transcripts = client.get_or_create_collection(
            _COLLECTION_TRANSCRIPTS,
            metadata={"description": "Transcript segments with timestamps and job_id"},
        )
    return _chroma_transcripts


def _get_meetings_collection():
    global _chroma_meetings
    if _chroma_meetings is None:
        client = _get_chroma()
        _chroma_meetings = client.get_or_create_collection(
            _COLLECTION_MEETINGS,
            metadata={"description": "Meeting main topics and metadata"},
        )
    return _chroma_meetings


def index_transcript_segments(
    job_id: str,
    timestamps: list[dict],
    original_filename: str = "",
    folder_id: int | None = None,
) -> None:
    """
    Index each transcript segment (with start/end/text) into the transcript RAG.
    Each segment is stored with job_id and folder_id so search can filter by folder.
    """
    if not timestamps:
        return
    coll = _get_transcripts_collection()
    texts = []
    metadatas = []
    ids = []
    folder_str = str(folder_id) if folder_id is not None else ""
    for i, seg in enumerate(timestamps):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        seg_id = f"{job_id}_{i}"
        texts.append(text)
        meta = {
            "job_id": job_id,
            "start": float(start),
            "end": float(end),
            "original_filename": original_filename or job_id,
        }
        if folder_str:
            meta["folder_id"] = folder_str
        metadatas.append(meta)
        ids.append(seg_id)
    if not texts:
        return
    embeddings = _embed(texts)
    coll.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


def index_meeting(
    job_id: str,
    original_filename: str,
    main_topic: str,
    subtopics: list[str],
    folder_id: int | None = None,
) -> None:
    """
    Index one meeting's main topic (and subtopics as searchable text) into the meetings RAG.
    """
    coll = _get_meetings_collection()
    doc = main_topic
    if subtopics:
        doc = main_topic + "\n" + "\n".join(subtopics)
    doc = (doc or "").strip()
    if not doc:
        doc = "(No topic)"
    embedding = _embed([doc])[0]
    meta = {
        "job_id": job_id,
        "original_filename": original_filename or job_id,
        "main_topic": main_topic or "",
    }
    if folder_id is not None:
        meta["folder_id"] = str(folder_id)
    coll.upsert(
        ids=[job_id],
        embeddings=[embedding],
        documents=[doc],
        metadatas=[meta],
    )


def search_transcript_segments(
    query: str,
    limit: int | None = None,
    folder_ids: list[int] | None = None,
) -> list[dict]:
    """
    Search transcript segments by semantic similarity. Returns list of
    { text, job_id, start, end, original_filename, distance }.
    If folder_ids is provided, only segments in those folders are returned.
    """
    limit = limit or RAG_SEARCH_LIMIT
    coll = _get_transcripts_collection()
    if coll.count() == 0:
        return []
    q_emb = _embed([query])[0]
    where = None
    if folder_ids:
        # Chroma metadata filter: folder_id in list (store as string in metadata)
        where = {"folder_id": {"$in": [str(fid) for fid in folder_ids]}}
    kwargs = {
        "query_embeddings": [q_emb],
        "n_results": min(limit, coll.count()),
        "include": ["documents", "metadatas", "distances"],
    }
    if where is not None:
        kwargs["where"] = where
    results = coll.query(**kwargs)
    out = []
    docs = results.get("documents") or [[]]
    metas = results.get("metadatas") or [[]]
    dists = results.get("distances") or [[]]
    for i in range(len(docs[0])):
        meta = metas[0][i] if i < len(metas[0]) else {}
        out.append({
            "text": (docs[0][i] if i < len(docs[0]) else ""),
            "job_id": meta.get("job_id", ""),
            "start": meta.get("start", 0),
            "end": meta.get("end", 0),
            "original_filename": meta.get("original_filename", ""),
            "distance": dists[0][i] if i < len(dists[0]) else 0,
        })
    return out


def search_meetings(
    query: str,
    limit: int | None = None,
    folder_ids: list[int] | None = None,
) -> list[dict]:
    """
    Search meetings by main topic / subtopics. Returns list of
    { job_id, original_filename, main_topic, document, distance }.
    If folder_ids is provided, only meetings in those folders are returned.
    """
    limit = limit or RAG_SEARCH_LIMIT
    coll = _get_meetings_collection()
    if coll.count() == 0:
        return []
    q_emb = _embed([query])[0]
    where = None
    if folder_ids:
        where = {"folder_id": {"$in": [str(fid) for fid in folder_ids]}}
    kwargs = {
        "query_embeddings": [q_emb],
        "n_results": min(limit, coll.count()),
        "include": ["documents", "metadatas", "distances"],
    }
    if where is not None:
        kwargs["where"] = where
    results = coll.query(**kwargs)
    out = []
    docs = results.get("documents") or [[]]
    metas = results.get("metadatas") or [[]]
    dists = results.get("distances") or [[]]
    for i in range(len(docs[0])):
        meta = metas[0][i] if i < len(metas[0]) else {}
        out.append({
            "job_id": meta.get("job_id", ""),
            "original_filename": meta.get("original_filename", ""),
            "main_topic": meta.get("main_topic", ""),
            "document": (docs[0][i] if i < len(docs[0]) else ""),
            "distance": dists[0][i] if i < len(dists[0]) else 0,
        })
    return out
