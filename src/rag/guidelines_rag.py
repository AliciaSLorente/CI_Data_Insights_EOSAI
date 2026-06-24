"""
RAG for Zurich UW Guidelines.

Embeds the Zurich underwriting guideline PDFs using the LiteLLM proxy
(text-embedding-3-large available on the Zurich endpoint).

Stores embeddings as numpy arrays + text chunks in data/parsed/uw_guidelines_index.json.
Retrieval: cosine similarity — no external vector DB required.

Usage:
    # Build index once:
    python -m src.rag.guidelines_rag --build

    # Query:
    from src.rag.guidelines_rag import query_guidelines
    results = query_guidelines("What controls are required for companies with PHI?")
"""

import os
import json
import re
import sys
import numpy as np
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv(override=True)

GUIDELINES_DIR = Path("data/raw/uw_guidelines")
INDEX_PATH      = Path("data/parsed/uw_guidelines_index.json")
CHUNK_SIZE      = 400    # words per chunk
CHUNK_OVERLAP   = 80     # words overlap between chunks
EMBEDDING_MODEL = "text-embedding-3-large-1-standard"  # available on Zurich proxy


# ── Text extraction ────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        parts = []
        for page in reader.pages:
            try:
                text = page.extract_text()
                if text:
                    parts.append(text)
            except Exception:
                pass
        return "\n".join(parts)
    except Exception as e:
        print(f"  Failed to extract {pdf_path.name}: {e}")
        return ""


def chunk_text(text: str, source: str, chunk_size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> List[Dict]:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    i = 0
    chunk_num = 0
    while i < len(words):
        chunk_words = words[i: i + chunk_size]
        chunk_text = " ".join(chunk_words)
        # Clean whitespace
        chunk_text = re.sub(r"\s+", " ", chunk_text).strip()
        if len(chunk_text) > 50:  # skip tiny chunks
            chunks.append({
                "id":     f"{source}_{chunk_num}",
                "source": source,
                "text":   chunk_text,
                "chars":  len(chunk_text),
            })
            chunk_num += 1
        i += chunk_size - overlap
    return chunks


# ── Embeddings ─────────────────────────────────────────────────────────────────

def embed_texts(texts: List[str]) -> np.ndarray:
    """Embed a list of texts using the LiteLLM proxy."""
    api_key  = os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("ANTHROPIC_BASE_URL")

    if not api_key or not base_url:
        raise ValueError("ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL must be set in .env")

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=f"{base_url}/v1")

    # Batch in groups of 100 to avoid API limits
    all_embeddings = []
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch = texts[i: i + batch_size]
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
        print(f"  Embedded {min(i+batch_size, len(texts))}/{len(texts)} chunks")

    return np.array(all_embeddings, dtype=np.float32)


# ── Index build ────────────────────────────────────────────────────────────────

def build_index(force: bool = False) -> bool:
    """
    Build the RAG index from guideline PDFs.
    Saves to data/parsed/uw_guidelines_index.json.
    Returns True if successful.
    """
    if INDEX_PATH.exists() and not force:
        print(f"Index already exists at {INDEX_PATH}. Use --force to rebuild.")
        return True

    if not GUIDELINES_DIR.exists():
        print(f"Guidelines directory not found: {GUIDELINES_DIR}")
        print("Copy UW guideline PDFs to data/raw/uw_guidelines/")
        return False

    pdf_files = list(GUIDELINES_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {GUIDELINES_DIR}")
        return False

    print(f"Building RAG index from {len(pdf_files)} PDF(s)...")
    all_chunks = []

    for pdf_path in pdf_files:
        print(f"\n  Extracting: {pdf_path.name}")
        text = extract_text_from_pdf(pdf_path)
        if not text:
            continue
        chunks = chunk_text(text, source=pdf_path.stem)
        print(f"  -> {len(chunks)} chunks ({len(text):,} chars)")
        all_chunks.extend(chunks)

    if not all_chunks:
        print("No text extracted from any PDF.")
        return False

    print(f"\n  Total chunks: {len(all_chunks)}")
    print(f"  Embedding with {EMBEDDING_MODEL}...")

    texts = [c["text"] for c in all_chunks]
    try:
        embeddings = embed_texts(texts)
    except Exception as e:
        print(f"  Embedding failed: {e}")
        print("  Saving index without embeddings (keyword search fallback).")
        embeddings = None

    # Save index
    index = {
        "chunks":     all_chunks,
        "embeddings": embeddings.tolist() if embeddings is not None else None,
        "model":      EMBEDDING_MODEL,
        "n_chunks":   len(all_chunks),
        "sources":    [p.stem for p in pdf_files],
    }
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f)

    size_kb = INDEX_PATH.stat().st_size / 1024
    print(f"\n  Saved index: {INDEX_PATH} ({size_kb:.0f} KB)")
    print(f"  {len(all_chunks)} chunks from {len(pdf_files)} documents")
    return True


# ── Query ──────────────────────────────────────────────────────────────────────

_INDEX_CACHE = None


def _load_index() -> Dict:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        if not INDEX_PATH.exists():
            return {}
        with open(INDEX_PATH) as f:
            data = json.load(f)
        if data.get("embeddings"):
            data["embeddings_np"] = np.array(data["embeddings"], dtype=np.float32)
        _INDEX_CACHE = data
    return _INDEX_CACHE


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity between vector a and matrix b."""
    a_norm = a / (np.linalg.norm(a) + 1e-9)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    return b_norm @ a_norm


def _keyword_search(query: str, chunks: List[Dict], top_k: int) -> List[Dict]:
    """Fallback keyword search when embeddings not available."""
    query_words = set(query.lower().split())
    scored = []
    for chunk in chunks:
        text_words = set(chunk["text"].lower().split())
        score = len(query_words & text_words) / max(len(query_words), 1)
        scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k] if _ > 0]


def query_guidelines(question: str, top_k: int = 3) -> List[Dict]:
    """
    Retrieve the most relevant passages from UW guidelines for a question.
    Returns list of {source, text, score, citation} dicts.

    If embeddings not available, falls back to keyword search.
    """
    index = _load_index()
    if not index:
        return []

    chunks = index.get("chunks", [])
    embeddings_np = index.get("embeddings_np")

    if embeddings_np is not None:
        # Semantic search
        try:
            api_key  = os.getenv("ANTHROPIC_API_KEY")
            base_url = os.getenv("ANTHROPIC_BASE_URL")
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=f"{base_url}/v1")
            resp = client.embeddings.create(model=EMBEDDING_MODEL, input=[question])
            q_emb = np.array(resp.data[0].embedding, dtype=np.float32)
            scores = _cosine_similarity(q_emb, embeddings_np)
            top_idx = np.argsort(scores)[::-1][:top_k]
            results = []
            for idx in top_idx:
                if scores[idx] > 0.3:  # relevance threshold
                    chunk = chunks[idx]
                    results.append({
                        "source":   chunk["source"],
                        "text":     chunk["text"],
                        "score":    float(scores[idx]),
                        "citation": f"Source: {chunk['source']} (chunk {idx})",
                    })
            return results
        except Exception:
            pass  # fall through to keyword search

    # Keyword fallback
    results = _keyword_search(question, chunks, top_k)
    return [{"source": c["source"], "text": c["text"],
             "score": 0.0, "citation": f"Source: {c['source']}"} for c in results]


def index_available() -> bool:
    """True if the index has been built."""
    return INDEX_PATH.exists() and INDEX_PATH.stat().st_size > 1000


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="Build index from PDFs")
    parser.add_argument("--force", action="store_true", help="Force rebuild")
    parser.add_argument("--query", type=str, help="Test a query")
    args = parser.parse_args()

    if args.build or args.force:
        build_index(force=args.force)

    if args.query:
        if not index_available():
            print("Index not built. Run with --build first.")
            sys.exit(1)
        results = query_guidelines(args.query, top_k=3)
        for i, r in enumerate(results, 1):
            print(f"\n--- Result {i} (score={r['score']:.3f}) ---")
            print(f"Source: {r['source']}")
            print(r["text"][:300])
