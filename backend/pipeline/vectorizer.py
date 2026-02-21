"""
pipeline/vectorizer.py

Converts segment text into embeddings and stores them in ChromaDB.

Model: sentence-transformers/all-MiniLM-L6-v2 (~80 MB, CPU-friendly, cross-platform)
Lazy loading: model loads on first call, cached in module-level variable.

Collection: chroma/text (one per project, stored on disk in projects/{id}/chroma/text/)
"""

from __future__ import annotations

import logging
from pathlib import Path
from timeline.models import Segment

logger = logging.getLogger(__name__)

# Module-level model cache (lazy loaded on first use)
_sentence_model = None


def _get_model():
    global _sentence_model
    if _sentence_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading sentence-transformers model (first use)...")
        _sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("sentence-transformers model loaded.")
    return _sentence_model


def vectorize_segments(
    segments: list[Segment],
    state,
) -> list[Segment]:
    """
    Generate embeddings for all segments and store in ChromaDB chroma/text.

    Updates each segment's chroma_id in the state's segment_pool.
    Returns the same segments list with chroma_id populated.

    The ChromaDB collection is keyed by segment_id, so cross-agent queries
    (visual, audio) can join on the same key.
    """
    if not segments:
        return segments

    # Get or create ChromaDB collection
    collection = _get_collection(state)

    model = _get_model()

    # Encode all texts in one batch (efficient)
    texts = [seg.text for seg in segments]
    ids = [seg.id for seg in segments]

    logger.info("Generating embeddings for %d segments...", len(segments))
    embeddings = model.encode(texts, show_progress_bar=False).tolist()

    # Build metadata for ChromaDB
    metadatas = [
        {
            "start": seg.start,
            "end": seg.end,
            "duration": seg.duration,
            "source": seg.source,
            "speaker": seg.speaker or "",
        }
        for seg in segments
    ]

    # Upsert into ChromaDB (handles re-runs gracefully)
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    logger.info("Stored %d embeddings in chroma/text.", len(segments))

    # Write chroma_id back to segment_pool
    for seg in segments:
        seg.chroma_id = seg.id  # chroma_id == segment_id in the text collection
        state.update_segment_chroma_id(seg.id, seg.id)

    return segments


def similarity_search(
    query: str,
    state,
    n_results: int = 10,
) -> list[dict]:
    """
    Search chroma/text for segments semantically similar to the query.

    Returns a list of dicts: [{id, document, metadata, distance}, ...]
    ordered by similarity (most similar first).
    """
    collection = _get_collection(state)
    model = _get_model()

    query_embedding = model.encode([query], show_progress_bar=False).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    # Flatten ChromaDB's nested result structure
    flat: list[dict] = []
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for i, seg_id in enumerate(ids):
        flat.append({
            "id": seg_id,
            "document": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
            "distance": dists[i] if i < len(dists) else 1.0,
        })

    return flat


def _get_collection(state):
    """Return (creating if needed) the chroma/text collection for this project."""
    import chromadb

    chroma_path = str(state.chroma_dir / "text")
    Path(chroma_path).mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection(
        name="text",
        metadata={"hnsw:space": "cosine"},
    )
    return collection
