"""
embed.py — Gemini Embedding API helpers (no local model → tiny RAM footprint).

Used by rag.py (query embedding at runtime) and generate_embeddings.py
(chunk embedding offline). Replaces the local sentence-transformers/torch stack
that exceeded Render's 512MB free tier.

The embedding model is auto-discovered from the key via ListModels (model
availability differs by key / API version), preferring the current GA models.
Vectors are L2-normalized so a plain dot product == cosine similarity.
"""
import os
import time
import numpy as np
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Preferred embedding models, best first. Whichever the key actually exposes wins.
_PREFERRED = [
    "gemini-embedding-001",
    "text-embedding-004",
    "embedding-001",
]
# Explicit override wins over discovery.
_OVERRIDE = os.environ.get("GEMINI_EMBED_MODEL")

# text-embedding-004 allows up to 100 inputs per batch request.
BATCH_SIZE = 100

_resolved_model = None        # cached resolved model name (no "models/" prefix)
_batch_supported = True       # flipped off if batchEmbedContents 404s


def available():
    return bool(GEMINI_API_KEY)


def _resolve_model():
    """Pick an embedding model this key actually supports (cached)."""
    global _resolved_model
    if _resolved_model:
        return _resolved_model
    if _OVERRIDE:
        _resolved_model = _OVERRIDE.split("/")[-1]
        print(f"Embedding model (override): {_resolved_model}")
        return _resolved_model
    try:
        r = requests.get(_BASE, params={"key": GEMINI_API_KEY}, timeout=20)
        if r.status_code == 200:
            usable = []
            for m in r.json().get("models", []):
                methods = m.get("supportedGenerationMethods", []) or \
                          m.get("supportedActions", [])
                if "embedContent" in methods:
                    usable.append(m["name"].split("/")[-1])
            for p in _PREFERRED:
                if p in usable:
                    _resolved_model = p
                    break
            if not _resolved_model and usable:
                _resolved_model = usable[0]
            if usable:
                print(f"Embedding models available: {usable} → using {_resolved_model}")
        else:
            print(f"ListModels {r.status_code}: {r.text[:160]}")
    except Exception as e:
        print(f"ListModels error: {e}")
    if not _resolved_model:
        _resolved_model = _PREFERRED[0]
        print(f"Embedding model (fallback default): {_resolved_model}")
    return _resolved_model


def _normalize(vec):
    v = np.asarray(vec, dtype=np.float32)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def embed_query(text, task_type="RETRIEVAL_QUERY"):
    """Embed one query string → normalized (D,) float32 vector, or None."""
    if not GEMINI_API_KEY or not text:
        return None
    model = _resolve_model()
    payload = {
        "model": f"models/{model}",
        "content": {"parts": [{"text": text}]},
        "taskType": task_type,
    }
    try:
        r = requests.post(f"{_BASE}/{model}:embedContent",
                          params={"key": GEMINI_API_KEY}, json=payload, timeout=30)
        if r.status_code != 200:
            print(f"embedContent {r.status_code}: {r.text[:160]}")
            return None
        vals = r.json().get("embedding", {}).get("values")
        return _normalize(vals) if vals else None
    except Exception as e:
        print(f"Embed query error: {e}")
        return None


def _embed_batch_request(model, batch, task_type):
    """One batchEmbedContents call → list of normalized vectors. Returns None on 404."""
    global _batch_supported
    payload = {
        "requests": [
            {
                "model": f"models/{model}",
                "content": {"parts": [{"text": t or " "}]},
                "taskType": task_type,
            }
            for t in batch
        ]
    }
    for attempt in range(4):
        r = requests.post(f"{_BASE}/{model}:batchEmbedContents",
                          params={"key": GEMINI_API_KEY}, json=payload, timeout=60)
        if r.status_code == 200:
            return [_normalize(e["values"]) for e in r.json().get("embeddings", [])]
        if r.status_code == 404:
            _batch_supported = False
            return None
        if r.status_code in (429, 503):
            time.sleep(2 * (attempt + 1))
            continue
        raise RuntimeError(f"batchEmbed {r.status_code}: {r.text[:200]}")
    raise RuntimeError("batchEmbed failed after retries")


def embed_documents(texts, task_type="RETRIEVAL_DOCUMENT"):
    """Embed many chunk texts → normalized (N, D) float32 matrix.
    Uses batchEmbedContents; falls back to per-item embedContent if unsupported."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set — cannot embed documents.")
    model = _resolve_model()
    out = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        vecs = _embed_batch_request(model, batch, task_type) if _batch_supported else None
        if vecs is None:  # batch unsupported → sequential
            vecs = []
            for t in batch:
                v = embed_query(t, task_type=task_type)
                if v is None:
                    raise RuntimeError("embedContent failed during document embedding")
                vecs.append(v)
        out.extend(vecs)
        print(f"  embedded {min(start + BATCH_SIZE, len(texts))}/{len(texts)}")
    return np.vstack(out).astype(np.float32)


def probe_dim():
    """Return the embedding dimension for the resolved model, or None."""
    v = embed_query("test", task_type="RETRIEVAL_QUERY")
    return int(v.shape[0]) if v is not None else None


def current_model():
    """Resolved embedding model name (for logging)."""
    return _resolve_model()
