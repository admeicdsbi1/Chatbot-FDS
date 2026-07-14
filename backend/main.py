"""
main.py — FastAPI backend for the Maintenance Assistant.

Endpoints:
  GET  /api/health           keep-alive / readiness
  POST /api/chat             {question, history[]} -> {answer, sources, retrieval_count, lang}
  POST /api/transcribe       multipart audio       -> {text, lang, confidence, alternatives[]}
  POST /api/tts              {text, lang}           -> audio/mpeg (only if browser TTS off)

The RAG brain lives in rag.py / voice_text.py (ported from the original Gradio
app). I/O edges (LLM, STT, TTS) are reliable free providers — see llm.py / stt.py.
"""
import os, json
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import rag
import llm
import stt
import tts
from voice_text import detect_language

# CORS: comma-separated origins via env, default allow-all for easy local dev.
_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",")] if _origins_env else ["*"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    rag.init_kb()
    yield


app = FastAPI(title="Maintenance Assistant API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- usage logging (stdout — Render disk is ephemeral) ----
def log_usage(**entry):
    entry["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print("USAGE " + json.dumps(entry, ensure_ascii=False))
    except Exception:
        pass


# ================================================================
# Schemas
# ================================================================
class Turn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[Turn] = []


class TTSRequest(BaseModel):
    text: str
    lang: str = "en"


# ================================================================
# Routes
# ================================================================
@app.get("/api/health")
def health():
    import embed
    return {
        "status": "ok",
        "chunks": len(rag.chunks),
        "retrieval_mode": rag.retrieval_mode(),
        "embedding_shape": rag.embedding_shape(),
        "embedding_model": embed.current_model() if embed.available() else None,
        "gemini_model": llm.GEMINI_MODEL,
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    question = (req.question or "").strip()
    if not question:
        return JSONResponse({"error": "empty question"}, status_code=400)

    lang = detect_language(question)
    excerpts = rag.retrieve(question)
    if not excerpts:
        log_usage(type="chat", question=question, retrieval_count=0, lang=lang)
        return {
            "answer": "No relevant content found. Rephrase or consult supervisor.",
            "sources": "", "retrieval_count": 0, "lang": lang,
            "retrieval_mode": rag.retrieval_mode(),
        }

    ctx = rag.build_context(excerpts)
    history = [t.model_dump() for t in req.history]
    answer = llm.generate_answer(question, ctx, lang, history)
    sources = rag.build_sources(excerpts)

    log_usage(type="chat", question=question,
              retrieval_count=len(excerpts), lang=lang,
              response_length=len(answer))
    return {
        "answer": answer,
        "sources": sources,
        "retrieval_count": len(excerpts),
        "lang": lang,
        "retrieval_mode": rag.retrieval_mode(),
    }


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    result = stt.transcribe(audio_bytes, filename)
    log_usage(type="transcribe", text=result.get("text", ""),
              confidence=result.get("confidence"), lang=result.get("lang"))
    return result


@app.post("/api/tts")
def text_to_speech(req: TTSRequest):
    path = tts.synthesize(req.text, req.lang)
    if not path:
        return JSONResponse({"error": "tts unavailable"}, status_code=204)
    media = "audio/wav" if path.endswith(".wav") else "audio/mpeg"
    return FileResponse(path, media_type=media, filename=os.path.basename(path))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
