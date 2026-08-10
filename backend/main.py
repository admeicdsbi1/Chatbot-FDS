"""
main.py — FastAPI backend for the Maintenance Assistant.

Endpoints:
  GET  /api/health           keep-alive / readiness
  GET  /api/systems          maintenance areas + live chunk/doc counts (nav)
  GET  /api/documents        the reference shelf — one row per source PDF
  POST /api/chat             {question, history[], coach?} -> {answer, sources, ...}
  POST /api/transcribe       multipart audio       -> {text, lang, confidence, alternatives[]}
  POST /api/tts              {text, lang}           -> audio/mpeg (only if browser TTS off)
  POST /api/feedback         {message_id, rating, question?, note?} -> logged to stdout

The RAG brain lives in rag.py / voice_text.py (ported from the original Gradio
app). I/O edges (LLM, STT, TTS) are reliable free providers — see llm.py / stt.py.
"""
import load_env  # noqa: F401  — must precede the imports below (env read at import time)

import os, json
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import rag
import catalog
import llm
import stt
import tts
import verify
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
    # Optional coach scope set in the UI ("LHB" / "ICF" / "Vande Bharat" /
    # "Amrit Bharat"). Absent or empty means today's exact behaviour.
    coach: str | None = None


class TTSRequest(BaseModel):
    text: str
    lang: str = "en"


class FeedbackRequest(BaseModel):
    message_id: str
    rating: str            # "up" | "down"
    question: str = ""
    answer_preview: str = ""
    note: str = ""


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
        "documents": len({c.get("doc_id") for c in rag.chunks}),
    }


@app.get("/api/systems")
def systems():
    """Maintenance areas with live counts — drives the nav and the empty state.
    Derived from the loaded KB, so an ingest updates it with no code change."""
    return {"systems": catalog.systems()}


@app.get("/api/documents")
def documents():
    """The reference shelf: every source document with its R2 PDF link."""
    docs = catalog.documents()
    return {"count": len(docs), "documents": docs}


# Marker that the previous assistant turn was our clarification prompt (see
# rag.clarification_needed) — used to detect a coach/OEM follow-up answer.
_CLARIFY_MARKER = "please tell me the"


def _apply_coach_scope(query, coach):
    """Fold the UI's coach-scope selection into the retrieval query.

    The scope chip exists so a technician working on a Vande Bharat rake does
    not have to answer 'which coach type?' on every vague symptom query — each
    of those clarifications costs a full round trip on Render's free tier.

    Naming the coach in the query is all that is needed: rag.detect_query_coach
    picks it up and _coach_factor boosts that coach's chunks while leaving
    IR-wide ('common') documents at 1.0. An explicit coach in the question
    always wins, so the chip can never override what the user actually typed.
    """
    if not coach:
        return query
    coach = coach.strip()
    if not coach or coach.lower() in ("all", "any"):
        return query
    if rag.detect_query_coach(query):
        return query
    if not rag.detect_query_coach(coach):
        return query          # unrecognised value — ignore rather than pollute
    return f"{coach} {query}"


def _retrieval_query(question, history):
    """Refold the original question into a terse clarify answer.

    After the bot asks 'which coach type?', the user replies just 'LHB'. Run
    verbatim, retrieval collapses onto the bare word 'LHB' and coach-boosts every
    LHB doc (including all WSP manuals) — the cross-system contamination users
    saw. When the previous turn was our clarify prompt, or the message is a short
    bare coach/OEM answer, prepend the last real user question so retrieval keeps
    the actual subject."""
    if not history:
        return question
    prev = history[-1]
    prev_clarify = (getattr(prev, "role", "") == "assistant"
                    and _CLARIFY_MARKER in (prev.content or "").lower())
    bare_answer = (len(question.split()) <= 4
                   and bool(rag.detect_query_coach(question)
                            or rag.detect_query_oem(question)))
    if not (prev_clarify or bare_answer):
        return question
    prior_user = [t.content for t in history
                  if getattr(t, "role", "") == "user" and (t.content or "").strip()]
    if not prior_user:
        return question
    return f"{prior_user[-1]} {question}"


@app.post("/api/chat")
def chat(req: ChatRequest):
    question = (req.question or "").strip()
    if not question:
        return JSONResponse({"error": "empty question"}, status_code=400)

    lang = detect_language(question)
    rquery = _apply_coach_scope(_retrieval_query(question, req.history), req.coach)
    excerpts = rag.retrieve(rquery)
    if not excerpts:
        log_usage(type="chat", question=question, retrieval_count=0, lang=lang,
                  coach=req.coach or None)
        return {
            "answer": "No relevant content found. Rephrase or consult supervisor.",
            "sources": "", "sources_list": [], "retrieval_count": 0, "lang": lang,
            "retrieval_mode": rag.retrieval_mode(),
        }

    # Symptoms-only query that would blend specs across coaches/OEMs → ask first.
    # Use the refolded query so a just-answered clarify isn't asked again.
    clarify = rag.clarification_needed(rquery, excerpts)
    if clarify:
        log_usage(type="chat", question=question,
                  retrieval_count=len(excerpts), lang=lang, clarify=True)
        return {
            "answer": clarify,
            "sources": rag.build_sources(excerpts),
            "sources_list": rag.build_sources_list(excerpts),
            "retrieval_count": len(excerpts),
            "lang": lang,
            "retrieval_mode": rag.retrieval_mode(),
            "clarify": True,
        }

    ctx = rag.build_context(excerpts)
    history = [t.model_dump() for t in req.history]
    answer = llm.generate_answer(question, ctx, lang, history)
    # Numeric-fidelity hard guard: suppress any technical value the answer states
    # that is not present verbatim in the retrieved source (fail closed).
    answer, suppressed = verify.guard_answer(answer, ctx)
    sources = rag.build_sources(excerpts)

    log_usage(type="chat", question=question,
              retrieval_count=len(excerpts), lang=lang,
              coach=req.coach or None,
              response_length=len(answer),
              values_suppressed=len(suppressed),
              suppressed=[t for _, t in suppressed] or None)
    return {
        "answer": answer,
        "sources": sources,
        "sources_list": rag.build_sources_list(excerpts),
        "retrieval_count": len(excerpts),
        "lang": lang,
        "retrieval_mode": rag.retrieval_mode(),
        # The guard withheld these values because they were not present verbatim
        # in the retrieved source. Surfaced so the user knows something was held
        # back rather than silently absent — a maintenance user needs to know to
        # go and check the manual.
        "values_suppressed": len(suppressed),
    }


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    filename = audio.filename or "audio.webm"
    result = stt.transcribe(audio_bytes, filename)
    log_usage(type="transcribe", text=result.get("text", ""),
              confidence=result.get("confidence"), lang=result.get("lang"))
    return result


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    """Thumbs up/down on an answer, logged to stdout alongside usage.

    Render's disk is ephemeral, so there is deliberately no store — with ~20-30
    users the log stream is enough, and it is the only channel that will surface
    a wrong answer that the numeric guard could not catch."""
    rating = req.rating if req.rating in ("up", "down") else "unknown"
    log_usage(type="feedback", rating=rating, message_id=req.message_id,
              question=req.question[:300], answer_preview=req.answer_preview[:300],
              note=req.note[:500] or None)
    return {"ok": True}


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
