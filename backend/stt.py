"""
stt.py — Speech-to-text via Groq Whisper (whisper-large-v3-turbo).

Replaces the original Hugging Face Inference Whisper, which throttled (503/429)
and cold-started — the root cause of "poor response to audio". Groq Whisper is
free, fast and reliable. The Hindi/Hinglish correction + confidence logic from
voice_text.py is preserved.
"""
import os
import requests

from voice_text import (
    correct_transcription, compute_voice_confidence, generate_alternatives,
    detect_language, _has_urdu_arabic_script,
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
STT_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")


def _groq_transcribe(audio_bytes, filename, language=None):
    """Single Groq Whisper attempt. language=None auto-detects; 'hi' forces Hindi."""
    if not GROQ_API_KEY:
        return None
    files = {"file": (filename, audio_bytes)}
    data = {"model": STT_MODEL, "response_format": "json", "temperature": "0"}
    if language:
        data["language"] = language
    try:
        r = requests.post(
            GROQ_STT_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files=files, data=data, timeout=60,
        )
        if r.status_code == 200:
            return (r.json().get("text") or "").strip()
        print(f"Groq STT {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        print(f"Groq STT error: {e}")
        return None


def transcribe(audio_bytes, filename="audio.webm"):
    """
    Returns dict: {text, lang, confidence, alternatives}.
    Mirrors the original two-pass flow: auto-detect first, then retry with a
    Hindi hint if Urdu script appears or confidence is low.
    """
    if not GROQ_API_KEY:
        return {"text": "", "lang": "en", "confidence": 0.0,
                "alternatives": [], "error": "GROQ_API_KEY not set"}
    if not audio_bytes or len(audio_bytes) < 100:
        return {"text": "", "lang": "en", "confidence": 0.0, "alternatives": []}

    # Pass 1: auto-detect
    raw = _groq_transcribe(audio_bytes, filename, language=None)

    # Pass 2: force Hindi if Whisper emitted Urdu/Arabic script (Hinglish mis-detect)
    if raw and _has_urdu_arabic_script(raw):
        raw_hi = _groq_transcribe(audio_bytes, filename, language="hi")
        if raw_hi:
            raw = raw_hi

    if not raw:
        return {"text": "", "lang": "en", "confidence": 0.0, "alternatives": []}

    corrected = correct_transcription(raw)
    if not corrected:
        return {"text": "", "lang": "en", "confidence": 0.0, "alternatives": []}

    lang = detect_language(corrected)
    confidence = compute_voice_confidence(raw, corrected)

    # Low confidence + not already Urdu-retried → try Hindi hint
    if confidence < 0.65 and not _has_urdu_arabic_script(raw):
        raw_hi = _groq_transcribe(audio_bytes, filename, language="hi")
        if raw_hi:
            corr_hi = correct_transcription(raw_hi)
            conf_hi = compute_voice_confidence(raw_hi, corr_hi) if corr_hi else 0
            if conf_hi > confidence:
                corrected, lang, confidence = corr_hi, detect_language(corr_hi), conf_hi

    alternatives = generate_alternatives(corrected, n=3) if confidence < 0.55 else []
    return {
        "text": corrected,
        "lang": lang,
        "confidence": confidence,
        "alternatives": alternatives,
    }
