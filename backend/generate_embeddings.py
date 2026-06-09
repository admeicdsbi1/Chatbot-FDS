"""
One-time helper: pre-compute data/embeddings.npy with the Gemini Embedding API
so the server doesn't have to build it on first boot. Run locally with your
GEMINI_API_KEY set, then commit the regenerated embeddings.npy.

    set GEMINI_API_KEY=...        (Windows)   /   export GEMINI_API_KEY=...
    pip install numpy requests
    python generate_embeddings.py

NOTE: This replaces the old local MiniLM embeddings. Query embedding at runtime
uses the SAME Gemini model (see embed.py), so the vector spaces match.
"""
import os, json
import numpy as np
import embed

DATA = os.path.join(os.path.dirname(__file__), "data")
JSONL = os.path.join(DATA, "chunks_merged.jsonl")
EMB_CACHE = os.path.join(DATA, "embeddings.npy")

if not embed.available():
    raise SystemExit("GEMINI_API_KEY not set — required to build embeddings.")

with open(JSONL, encoding="utf-8") as f:
    chunks = [json.loads(l) for l in f if l.strip()]
print(f"Loaded {len(chunks)} chunks; embedding with {embed.current_model()}...")

texts = [c.get("text", "") for c in chunks]
emb = embed.embed_documents(texts)          # normalized (N, D)
np.save(EMB_CACHE, emb)
print(f"Saved {EMB_CACHE}  shape={emb.shape}  ({emb.nbytes/1024/1024:.1f} MB)")
