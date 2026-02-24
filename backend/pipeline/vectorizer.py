"""
pipeline/vectorizer.py

Converts segment text into embeddings and stores them in ChromaDB.

Model: sentence-transformers/all-MiniLM-L6-v2 (~80 MB, CPU-friendly, cross-platform)
Lazy loading: model loads on first call, cached in module-level variable.

Collection: chroma/text (one per project, stored on disk in projects/{id}/chroma/text/)
"""

from __future__ import annotations

from pathlib import Path
from timeline.models import Segment

# Module-level model cache (lazy loaded on first use)
_sentence_model = None


def _get_model():
    global _sentence_model
    if _sentence_model is None:
        from sentence_transformers import SentenceTransformer
        print("Loading sentence-transformers model (first use)...")
        _sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
        print("sentence-transformers model loaded.")
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
    print("=" * 70)
    print("🔤 VECTORIZATION START")
    print(f"  Segments to vectorize: {len(segments)}")
    print("=" * 70)
    
    if not segments:
        print("⚠️  No segments provided for vectorization")
        return segments

    # Get or create ChromaDB collection
    collection = _get_collection(state)
    
    # Log collection status BEFORE adding
    existing_count = collection.count()
    print("📊 ChromaDB collection status BEFORE:")
    print(f"  Existing vectors: {existing_count}")
    print(f"  Collection path: {state.chroma_dir / 'text'}")

    model = _get_model()

    # Encode all texts in one batch (efficient)
    texts = [seg.text for seg in segments]
    ids = [seg.id for seg in segments]
    
    # Log first 3 segments for debugging
    print("📝 Sample segments to vectorize:")
    for i, seg in enumerate(segments[:3], 1):
        print(f"  [{i}] ID={seg.id}, text='{seg.text[:100]}'")

    print(f"🧮 Generating embeddings for {len(segments)} segments...")
    embeddings = model.encode(texts, show_progress_bar=False).tolist()
    print(f"✓ Generated {len(embeddings)} embeddings (dim={len(embeddings[0]) if embeddings else 0})")

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
    print(f"💾 Upserting {len(ids)} vectors to ChromaDB...")
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    
    # Verify storage
    new_count = collection.count()
    print("✓ ChromaDB upsert complete")
    print("📊 ChromaDB collection status AFTER:")
    print(f"  Total vectors: {new_count}")
    print(f"  Vectors added/updated: {new_count - existing_count}")

    # Write chroma_id back to segment_pool
    for seg in segments:
        seg.chroma_id = seg.id  # chroma_id == segment_id in the text collection
        state.update_segment_chroma_id(seg.id, seg.id)

    print("=" * 70)
    print("✅ VECTORIZATION COMPLETE")
    print(f"  Total segments vectorized: {len(segments)}")
    print(f"  ChromaDB total vectors: {new_count}")
    print("=" * 70)

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
    print("=" * 70)
    print("🔍 SIMILARITY SEARCH START")
    print(f"  Query: '{query}'")
    print(f"  Requested results: {n_results}")
    print("=" * 70)
    
    collection = _get_collection(state)
    
    # Check collection status
    collection_count = collection.count()
    print("📊 ChromaDB collection status:")
    print(f"  Total vectors in collection: {collection_count}")
    print(f"  Collection path: {state.chroma_dir / 'text'}")
    
    if collection_count == 0:
        print("❌ ChromaDB collection is EMPTY!")
        print("  No vectors to search. Vectorization may have failed.")
        return []
    
    model = _get_model()

    print("🧮 Encoding query...")
    query_embedding = model.encode([query], show_progress_bar=False).tolist()
    print(f"✓ Query encoded (dim={len(query_embedding[0]) if query_embedding and len(query_embedding) > 0 else 0})")
    
    actual_n_results = min(n_results, collection_count)
    print(f"🔎 Querying ChromaDB for top {actual_n_results} results...")

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=actual_n_results,
        include=["documents", "metadatas", "distances"],
    )

    # Flatten ChromaDB's nested result structure
    flat: list[dict] = []
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    print(f"📥 ChromaDB returned {len(ids)} results")
    
    for i, seg_id in enumerate(ids):
        flat.append({
            "id": seg_id,
            "document": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
            "distance": dists[i] if i < len(dists) else 1.0,
        })
    
    # Log top 3 results
    if flat:
        print(f"🎯 Top {min(3, len(flat))} results:")
        for i, result in enumerate(flat[:3], 1):
            print(f"  [{i}] ID={result['id']}, distance={result['distance']:.4f}, text='{result['document'][:100]}'")
    
    print("=" * 70)
    print("✅ SIMILARITY SEARCH COMPLETE")
    print(f"  Results found: {len(flat)}")
    print("=" * 70)

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
