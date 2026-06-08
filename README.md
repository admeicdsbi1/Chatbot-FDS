# Maintenance Assistant — Standalone App (Next.js + FastAPI)

AI maintenance assistant for **FSDS, FDSS & WSP** systems on LHB and Vande Bharat
coaches. Voice + text, Hindi & English. This is the standalone rebuild that
replaces the original Hugging Face Spaces / Gradio app.

```
chatbot/
  backend/     FastAPI — RAG brain (FAISS + local MiniLM), LLM, STT, TTS
  frontend/    Next.js PWA — futuristic, mobile-first chat UI
  gradio/      (legacy) original Gradio app — kept for reference
```

## Why it changed

| Old (HF Spaces / Gradio) | New (this repo) |
|---|---|
| Hugging Face Inference Whisper (throttled, 503s) | **Groq Whisper** — free, fast, reliable |
| HF Router open-model fallback chain | **Gemini 2.0 Flash** → **Groq Llama-3.3-70B** fallback |
| Query embedded via HF Inference API | **Local MiniLM** embedding in the backend |
| No conversation memory (follow-ups lost context) | Recent turns sent to the LLM |
| Gradio fixed-height chat, autoplay hacks | React state, scrollable chat, browser TTS |
| Single Gradio process | Stateless API + static PWA, deployable separately |

All hosting/inference is **free** at ~20–30 concurrent users.

---

## Free stack & accounts needed

1. **Gemini API key** (free) — https://aistudio.google.com/apikey
2. **Groq API key** (free) — https://console.groq.com/keys (powers the LLM fallback **and** voice STT)
3. **Render** account (free) — backend hosting
4. **Vercel** account (free) — frontend hosting
5. (optional) **cron-job.org** (free) — keep the Render service warm

---

## Local development

### Backend
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
copy .env.example .env                              # then fill GEMINI_API_KEY / GROQ_API_KEY
python generate_embeddings.py                       # one-time: builds data/embeddings.npy
uvicorn main:app --reload --port 8000
```
Test: `GET http://localhost:8000/api/health` → `{"status":"ok","chunks":257}`

### Frontend
```bash
cd frontend
npm install
copy .env.local.example .env.local                  # NEXT_PUBLIC_API_BASE=http://localhost:8000
npm run dev                                          # http://localhost:3000
```

---

## Deploy (free)

### 1. Backend → Render
- Push this repo to GitHub.
- Render → **New → Web Service** (or **Blueprint** using `backend/render.yaml`).
  - Root dir: `backend`
  - Build: `pip install -r requirements.txt`
  - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
  - Health check path: `/api/health`
- Env vars: `GEMINI_API_KEY`, `GROQ_API_KEY`, and `ALLOWED_ORIGINS=https://<your-app>.vercel.app`
- Commit `backend/data/embeddings.npy` first (run `generate_embeddings.py` locally) so boot is fast.

### 2. Frontend → Vercel
- Vercel → **New Project** → import repo → set **Root Directory = `frontend`**.
- Env var: `NEXT_PUBLIC_API_BASE=https://<your-backend>.onrender.com`
- Deploy. Note the URL and put it in the backend's `ALLOWED_ORIGINS`.

### 3. Keep-alive (avoid cold starts)
- cron-job.org → new job hitting `https://<your-backend>.onrender.com/api/health` every 10 min.

### 4. On-site QR
- Update `gradio/files wsp/qr_code.html` (or host a new QR page) to point at the Vercel URL.

---

## Updating the knowledge base
1. Edit/replace `backend/data/chunks_merged.jsonl`.
2. Run `python backend/generate_embeddings.py` to rebuild `embeddings.npy`.
3. Commit both files and redeploy the backend.

## Notes
- Voice replies use the **browser's** speech engine by default (free, no server load).
  The `/api/tts` (gTTS) endpoint exists as a fallback; set `SARVAM_API_KEY` for nicer Hindi.
- Usage is logged to stdout (`USAGE {...}`); view in Render logs. Add a free Postgres later if you want persistence.
