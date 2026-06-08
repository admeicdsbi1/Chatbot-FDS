"""
One-time helper: pre-compute data/embeddings.npy so the server starts fast on
Render (no embedding step on boot). Run locally, then commit embeddings.npy.

    pip install sentence-transformers numpy
    python generate_embeddings.py
"""
import os, json
import numpy as np

DATA = os.path.join(os.path.dirname(__file__), "data")
JSONL = os.path.join(DATA, "chunks_merged.jsonl")
EMB_CACHE = os.path.join(DATA, "embeddings.npy")
EMB_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

with open(JSONL, encoding="utf-8") as f:
    chunks = [json.loads(l) for l in f if l.strip()]
print(f"Loaded {len(chunks)} chunks")

from sentence_transformers import SentenceTransformer

model = SentenceTransformer(EMB_MODEL)
texts = [c.get("text", "") for c in chunks]
emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
np.save(EMB_CACHE, emb)
print(f"Saved {EMB_CACHE}  shape={emb.shape}  ({emb.nbytes/1024/1024:.1f} MB)")
