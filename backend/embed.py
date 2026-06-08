"""
embed.py — Gemini Embedding API helpers (no local model → tiny RAM footprint).

Used by rag.py (query embedding at runtime) and generate_embeddings.py
(chunk embedding offline). Replaces the local sentence-transformers/torch stack
that exceeded Render's 512MB free tier.

Model: text-embedding-004 (768-dim, free tier). Vectors are L2-normalized so a
plain dot product == cosine similarity.
"""
import os
import time
import numpy as np
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "text-embedding-004")

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
EMBED_URL = f"{_BASE}/{EMBED_MODEL}:embedContent"
BATCH_URL = f"{_BASE}/{EMBED_MODEL}:batchEmbedContents"

# text-embedding-004 allows up to 100 inputs per batch request.
BATCH_SIZE = 100


def available():
    return bool(GEMINI_API_KEY)


def _normalize(vec):
    v = np.asarray(vec, dtype=np.float32)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def embed_query(text, task_type="RETRIEVAL_QUERY"):
    """Embed one query string → normalized (D,) float32 vector, or None."""
    if not GEMINI_API_KEY or not text:
        return None
    payload = {
        "model": f"models/{EMBED_MODEL}",
        "content": {"parts": [{"text": text}]},
        "taskType": task_type,
    }
    try:
        r = requests.post(EMBED_URL, params={"key": GEMINI_API_KEY},
                          json=payload, timeout=30)
        if r.status_code != 200:
            print(f"Embed query {r.status_code}: {r.text[:160]}")
            return None
        vals = r.json().get("embedding", {}).get("values")
        return _normalize(vals) if vals else None
    except Exception as e:
        print(f"Embed query error: {e}")
        return None


def embed_documents(texts, task_type="RETRIEVAL_DOCUMENT"):
    """Embed many chunk texts → normalized (N, D) float32 matrix.
    Raises on failure (used offline / at startup where we need all of them)."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set — cannot embed documents.")
    out = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        payload = {
            "requests": [
                {
                    "model": f"models/{EMBED_MODEL}",
                    "content": {"parts": [{"text": t or " "}]},
                    "taskType": task_type,
                }
                for t in batch
            ]
        }
        for attempt in range(4):
            r = requests.post(BATCH_URL, params={"key": GEMINI_API_KEY},
                              json=payload, timeout=60)
            if r.status_code == 200:
                embs = r.json().get("embeddings", [])
                out.extend(_normalize(e["values"]) for e in embs)
                break
            if r.status_code in (429, 503):
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"batchEmbed {r.status_code}: {r.text[:200]}")
        else:
            raise RuntimeError("batchEmbed failed after retries")
        print(f"  embedded {min(start + BATCH_SIZE, len(texts))}/{len(texts)}")
    return np.vstack(out).astype(np.float32)


def probe_dim():
    """Return the embedding dimension for the current model, or None."""
    v = embed_query("test", task_type="RETRIEVAL_QUERY")
    return int(v.shape[0]) if v is not None else None
