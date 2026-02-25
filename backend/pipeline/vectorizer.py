"""
pipeline/vectorizer.py

Converts segment text into embeddings and stores them in ChromaDB.

Model: sentence-transformers/all-MiniLM-L6-v2 (~80 MB) via ONNX Runtime
Lazy loading: model loads on first call, cached in module-level variable.

Collection: chroma/text (one per project, stored on disk in projects/{id}/chroma/text/)
"""

from __future__ import annotations

import logging
import numpy as np
from pathlib import Path
from timeline.models import Segment

logger = logging.getLogger(__name__)

# Module-level model cache (lazy loaded on first use)
_embedding_model = None
_tokenizer = None


def _get_model():
    """
    Load sentence embedding model via ONNX Runtime (cross-platform).
    
    Uses optimum.onnxruntime like Whisper for consistent device handling.
    """
    global _embedding_model, _tokenizer
    
    if _embedding_model is None:
        from optimum.onnxruntime import ORTModelForFeatureExtraction
        from transformers import AutoTokenizer
        from utils.device import detect_device
        
        model_id = "sentence-transformers/all-MiniLM-L6-v2"
        device_config = detect_device()
        providers = device_config.onnx_providers
        
        logger.info("Loading sentence embedding model via ONNX Runtime...")
        logger.info("  Model: %s", model_id)
        logger.info("  Providers: %s", providers)
        logger.info("  Note: Will auto-convert to ONNX on first use (~2 sec, then cached)")
        
        try:
            # Load ONNX model (auto-converts and caches on first use)
            _embedding_model = ORTModelForFeatureExtraction.from_pretrained(
                model_id,
                export=True,  # Convert to ONNX (fast, ~2 sec) - caches for future runs
                provider=providers[0] if providers else "CPUExecutionProvider",
            )
            
            # Load tokenizer
            _tokenizer = AutoTokenizer.from_pretrained(model_id)
            
            logger.info("✓ Sentence embedding model loaded via ONNX Runtime")
            logger.info("  Active provider: %s", providers[0] if providers else "CPU")
            
        except Exception as e:
            logger.error("Failed to load embedding model via ONNX, trying CPU fallback: %s", e)
            try:
                # Fallback to CPU
                _embedding_model = ORTModelForFeatureExtraction.from_pretrained(
                    model_id,
                    export=True,
                    provider="CPUExecutionProvider",
                )
                _tokenizer = AutoTokenizer.from_pretrained(model_id)
                logger.info("✓ Loaded embedding model on CPU (fallback)")
            except Exception as e2:
                logger.exception("Failed to load embedding model even on CPU: %s", e2)
                raise
    
    return _embedding_model, _tokenizer


def _encode_texts(texts: list[str]) -> list[list[float]]:
    """
    Encode texts to embeddings using ONNX model.
    
    Returns list of embeddings (each embedding is a list of floats).
    """
    import torch
    
    model, tokenizer = _get_model()
    
    # Tokenize
    inputs = tokenizer(
        texts,
        padding=True,
        truncation=True,
        return_tensors="pt",
        max_length=512,
    )
    
    # Get embeddings from ONNX model
    with torch.no_grad():
        outputs = model(**inputs)
    
    # Mean pooling (same as sentence-transformers)
    # Take mean of all token embeddings (excluding padding)
    attention_mask = inputs["attention_mask"]
    token_embeddings = outputs.last_hidden_state
    
    # Expand attention mask to match token_embeddings dimensions
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    
    # Sum embeddings and divide by number of tokens (mean pooling)
    sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
    sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    embeddings = sum_embeddings / sum_mask
    
    # Normalize embeddings (L2 norm)
    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
    
    # Convert to list
    return embeddings.cpu().numpy().tolist()


def _encode_texts_cpu(texts: list[str]) -> list[list[float]]:
    """
    Encode texts to embeddings using CPU-only ONNX model (fallback for GPU errors).
    
    Returns list of embeddings (each embedding is a list of floats).
    """
    import torch
    from optimum.onnxruntime import ORTModelForFeatureExtraction
    from transformers import AutoTokenizer
    
    model_id = "sentence-transformers/all-MiniLM-L6-v2"
    
    # Load model on CPU
    model = ORTModelForFeatureExtraction.from_pretrained(
        model_id,
        export=True,
        provider="CPUExecutionProvider",
    )
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    
    # Tokenize
    inputs = tokenizer(
        texts,
        padding=True,
        truncation=True,
        return_tensors="pt",
        max_length=512,
    )
    
    # Get embeddings
    with torch.no_grad():
        outputs = model(**inputs)
    
    # Mean pooling
    attention_mask = inputs["attention_mask"]
    token_embeddings = outputs.last_hidden_state
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
    sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    embeddings = sum_embeddings / sum_mask
    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
    
    return embeddings.cpu().numpy().tolist()


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

    # Encode all texts in one batch (efficient)
    texts = [seg.text for seg in segments]
    ids = [seg.id for seg in segments]
    
    # Log first 3 segments for debugging
    print("📝 Sample segments to vectorize:")
    for i, seg in enumerate(segments[:3], 1):
        print(f"  [{i}] ID={seg.id}, text='{seg.text[:100]}'")

    print(f"🧮 Generating embeddings for {len(segments)} segments via ONNX...")
    print(f"  Using batch processing (16 segments at a time) to avoid GPU memory issues...")
    
    # Process in batches to avoid CUDA memory errors
    embeddings = []
    batch_size = 16
    total_batches = (len(texts) + batch_size - 1) // batch_size
    
    for batch_idx in range(0, len(texts), batch_size):
        batch_texts = texts[batch_idx:batch_idx + batch_size]
        batch_num = (batch_idx // batch_size) + 1
        
        try:
            print(f"  Processing batch {batch_num}/{total_batches} ({len(batch_texts)} segments)...")
            batch_embeddings = _encode_texts(batch_texts)
            embeddings.extend(batch_embeddings)
        except RuntimeError as e:
            if "CUDA" in str(e) or "illegal memory" in str(e):
                logger.warning("CUDA error in batch %d, retrying on CPU...", batch_num)
                print(f"  ⚠️  GPU error in batch {batch_num}, falling back to CPU...")
                try:
                    # Force CPU for this batch
                    batch_embeddings = _encode_texts_cpu(batch_texts)
                    embeddings.extend(batch_embeddings)
                    print(f"  ✓ Batch {batch_num} completed on CPU")
                except Exception as cpu_err:
                    logger.error("CPU fallback also failed for batch %d: %s", batch_num, cpu_err)
                    raise
            else:
                raise
    
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

    print("🧮 Encoding query via ONNX...")
    query_embedding = _encode_texts([query])
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


def clear_collection(state):
    """
    Clear the ChromaDB collection for this project.
    
    Called when re-transcribing to remove old embeddings.
    Deletes and recreates the collection.
    """
    import chromadb
    
    chroma_path = str(state.chroma_dir / "text")
    
    # Skip if chroma directory doesn't exist
    if not Path(chroma_path).exists():
        logger.info("ChromaDB directory doesn't exist, nothing to clear")
        return
    
    try:
        client = chromadb.PersistentClient(path=chroma_path)
        
        # Check if collection exists
        try:
            collection = client.get_collection(name="text")
            count = collection.count()
            logger.info("Deleting ChromaDB collection (had %d vectors)", count)
            client.delete_collection(name="text")
        except Exception:
            # Collection doesn't exist, that's fine
            logger.info("ChromaDB collection doesn't exist, nothing to delete")
        
        # Recreate empty collection
        client.get_or_create_collection(
            name="text",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("✓ ChromaDB collection cleared and recreated")
        
    except Exception as e:
        logger.warning("Failed to clear ChromaDB collection: %s", e)
        # Non-fatal - continue with transcription
