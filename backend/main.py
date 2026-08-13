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

import os, json, re
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

# The answer LLM sometimes formats a unit as LaTeX ("DFT of $125\,\mu m$"). The
# frontend renders markdown with remark-gfm and no math plugin, so the delimiters
# and control sequences reach the technician verbatim. Unwrap inline math and drop
# the backslash commands rather than leave "$125\" on screen.
_LATEX_INLINE = re.compile(r"\$\$?(?P<inner>[^$\n]{1,120}?)\$\$?")
# \text{Nm} / \mathrm{V} — unwrap to the braced content
_LATEX_WRAP = re.compile(r"\\(?:text|mathrm|mathit|mathbf|mathsf)\s*\{([^}]*)\}")
# whatever is left: spacing commands, sub/superscript markers, stray braces
_LATEX_RESIDUE = re.compile(r"\\[,;:!> ]|\\[a-zA-Z]+|[\^_{}]")
_GREEK = {"mu": "µ", "Omega": "Ω", "omega": "ω", "deg": "°", "circ": "°",
          "times": "×", "cdot": "·", "pm": "±", "approx": "≈",
          "leq": "≤", "geq": "≥", "le": "≤", "ge": "≥"}


def _strip_latex(text):
    """Turn inline LaTeX math into the plain text a maintenance answer should use.

    The model occasionally formats a unit as math ("DFT of $125\\,\\mu m$"); the
    frontend renders markdown with remark-gfm and no math plugin, so a technician
    saw the literal "$125\\". Three ordered passes — order matters, because each
    one would otherwise consume what the next needs."""
    if not text or "$" not in text:
        return text

    def _unwrap(m):
        inner = m.group("inner")
        # Only treat this as math if it carries a control sequence or is a bare
        # token — otherwise two currency amounts ("$5 and $10") read as one span.
        if "\\" not in inner and " " in inner:
            return m.group(0)
        inner = _LATEX_WRAP.sub(lambda g: g.group(1), inner)     # 1. \text{Nm} -> Nm
        inner = re.sub(r"\\([a-zA-Z]+)",                         # 2. \mu -> µ
                       lambda g: _GREEK.get(g.group(1), "\\" + g.group(1)), inner)
        inner = _LATEX_RESIDUE.sub("", inner)                    # 3. \, ^ _ { }
        inner = re.sub(r"\s+", " ", inner).strip()
        # a removed control sequence leaves "125µ m" — close the gap it made
        return re.sub(r"(?<=[µΩ°×·±])\s+(?=[A-Za-z])", "", inner)

    return _LATEX_INLINE.sub(_unwrap, text)


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


def _retrieval_trace(rquery, question, excerpts, trace, provider=None):
    """The retrieval decisions behind one answer, for the usage log.

    Without this an answer cannot be explained after the fact: the log recorded
    how many chunks came back but never which ones, so diagnosing a wrong answer
    meant re-running retrieval locally and hoping the KB and flags matched prod.
    Kept compact — 8 short rows per query at ~30 users."""
    entry = {
        "retrieved": [
            {"c": c.get("chunk_id"), "d": c.get("doc_id"),
             "p": c.get("page_num"), "s": round(float(s), 4)}
            for s, c in excerpts
        ],
        "llm_provider": provider,
    }
    if rquery != question:          # coach scope or clarify-refold rewrote it
        entry["rquery"] = rquery
    # Drop unset routing signals (coach/oem/system are None when not detected),
    # but keep rerank_fired even when False — "the rerank did not run" is the
    # answer to half the ranking questions this log exists to settle.
    entry.update({k: v for k, v in trace.items()
                  if v or k == "rerank_fired"})
    return entry


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
    trace = {}
    excerpts = rag.retrieve(rquery, trace=trace)
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
                  retrieval_count=len(excerpts), lang=lang, clarify=True,
                  **_retrieval_trace(rquery, question, excerpts, trace))
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
    answer, provider = llm.generate_answer(question, ctx, lang, history)
    answer = _strip_latex(answer)
    # Numeric-fidelity hard guard: suppress any technical value the answer states
    # that is not present verbatim in the retrieved source (fail closed).
    answer, suppressed = verify.guard_answer(answer, ctx)
    sources = rag.build_sources(excerpts)

    log_usage(type="chat", question=question,
              retrieval_count=len(excerpts), lang=lang,
              coach=req.coach or None,
              response_length=len(answer),
              values_suppressed=len(suppressed),
              suppressed=[t for _, t in suppressed] or None,
              **_retrieval_trace(rquery, question, excerpts, trace, provider))
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
