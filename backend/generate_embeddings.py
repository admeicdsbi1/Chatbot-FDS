"""
One-time helper: pre-compute data/embeddings.npy with the Gemini Embedding API
so the server doesn't have to build it on first boot. Run locally with your
GEMINI_API_KEY set, then commit the regenerated embeddings.npy TOGETHER with
chunks_merged.jsonl in the same commit — rag.init_kb() requires their row
counts to match, so they must always move as a pair.

    set GEMINI_API_KEY=...        (Windows)   /   export GEMINI_API_KEY=...
    set GEMINI_EMBED_SLEEP=8      (free tier: avoids 429 storms on large KBs)
    python generate_embeddings.py

Vectors are 768-dim (GEMINI_EMBED_DIM, see embed.py — must match at runtime)
and stored as float16 (~4 MB for 3000 chunks; rag.py casts to float32 on load).
Progress is checkpointed to data/embeddings.partial.npy every batch, so an
interrupted run resumes where it left off instead of restarting from zero.
"""
import os, json
import numpy as np
import embed

DATA = os.path.join(os.path.dirname(__file__), "data")
JSONL = os.path.join(DATA, "chunks_merged.jsonl")
EMB_CACHE = os.path.join(DATA, "embeddings.npy")
CHECKPOINT = os.path.join(DATA, "embeddings.partial.npy")

CHECKPOINT_EVERY = 5  # batches

if not embed.available():
    raise SystemExit("GEMINI_API_KEY not set — required to build embeddings.")

with open(JSONL, encoding="utf-8") as f:
    chunks = [json.loads(l) for l in f if l.strip()]
texts = [c.get("text", "") for c in chunks]
print(f"Loaded {len(chunks)} chunks; embedding with {embed.current_model()} "
      f"(dim={embed.EMBED_DIM}, batch={embed.BATCH_SIZE}, sleep={embed.INTER_BATCH_SLEEP}s)...")

done = []
if os.path.exists(CHECKPOINT):
    try:
        prev = np.load(CHECKPOINT)
        if prev.ndim == 2 and prev.shape[0] <= len(texts):
            done = [prev[i] for i in range(prev.shape[0])]
            print(f"Resuming from checkpoint: {len(done)}/{len(texts)} already embedded")
    except Exception as e:
        print(f"Ignoring unreadable checkpoint: {e}")

batch_size = embed.BATCH_SIZE
batches_since_ckpt = 0
while len(done) < len(texts):
    start = len(done)
    batch = texts[start:start + batch_size]
    vecs = embed.embed_documents(batch)  # normalized (n, D), handles retries
    done.extend(np.asarray(vecs))
    batches_since_ckpt += 1
    print(f"progress: {len(done)}/{len(texts)}")
    if batches_since_ckpt >= CHECKPOINT_EVERY:
        np.save(CHECKPOINT, np.vstack(done).astype(np.float16))
        batches_since_ckpt = 0

emb = np.vstack(done).astype(np.float16)
if emb.shape[0] != len(chunks):
    raise SystemExit(f"row mismatch: {emb.shape[0]} vectors vs {len(chunks)} chunks — not saving")
np.save(EMB_CACHE, emb)
if os.path.exists(CHECKPOINT):
    os.remove(CHECKPOINT)
size_mb = os.path.getsize(EMB_CACHE) / 1024 / 1024
print(f"Saved {EMB_CACHE}  shape={emb.shape}  dtype={emb.dtype}  ({size_mb:.1f} MB)")
print("Commit chunks_merged.jsonl and embeddings.npy together.")
