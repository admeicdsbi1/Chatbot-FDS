"""
llm.py — Answer generation with conversation memory.

Primary:  Google Gemini 2.0 Flash (free tier)
Fallback: Groq Llama-3.3-70B  (free tier)

Both called over plain REST (requests) — no SDK version churn, consistent with
the rest of the backend. Conversation history is included so follow-up questions
stay coherent (fixes the original "loss of clarity after multiple questions").
"""
import os
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# NOTE: gemini-2.5-flash 404s ("no longer available to new users") on keys
# created after its sunset — verify with ListModels before changing this.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "1500"))
TEMPERATURE = 0.1
HISTORY_TURNS = 4  # how many prior turns to feed back for context


def _system_prompt(lang_code):
    lang_label = "Hindi" if lang_code == "hi" else "English"
    return f"""You are Western Railway ICD/Sabarmati's maintenance assistant for FSDS, FDSS, and WSP systems on LHB & Vande Bharat coaches.
You are helping NEW TRAINEE maintenance staff who may not know technical jargon. Be DETAILED and CLEAR.

STRICT RULES:
1. Answer ONLY from CONTEXT. NEVER invent information.
2. Quote exact values: thresholds, voltages, part numbers, error codes, air gaps, activation temperatures, choke timings, torque values.
3. If info missing say: "Not fully covered. Refer to manual or supervisor."
4. Respond in {lang_label}. If the user spoke Hinglish, respond in simple Hinglish with technical terms in English.
5. For WSP, specify OEM (Faiveley/KNORR BREMSE/Escorts Kubota) and system model (AEF G2, SWKP, MGS2) when relevant.
6. For Vande Bharat/Amrit Bharat coaches, specify coach type and OEM when relevant.
7. For WSP fault codes, always mention: display code number, what it means in plain language, which component is affected, and exact corrective steps.
8. Explain WHERE each component is physically located on the coach (e.g. "WSP control panel in power panel of coach", "speed sensor on axle box cover").
9. For procedures, give NUMBERED STEPS with specific button names (S1/S2/S3), expected display readings, and what to do if reading is abnormal.
10. Always mention SAFETY warnings: "Remove fuse before card removal", "Power OFF before disconnecting" etc.

FORMAT:
**Direct Answer:** [Clear 2-3 sentence summary a beginner can understand]
**Step-by-step Action:** [Numbered steps with exact values, button names, expected readings]
**Safety Caution:** [Always include if any safety info exists in context]
**Reference:** [Document name, section, page]"""


def _recent_history(history):
    """Return the last HISTORY_TURNS user/assistant pairs as a clean list."""
    if not history:
        return []
    cleaned = [
        m for m in history
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    ]
    return cleaned[-(HISTORY_TURNS * 2):]


def _gemini(question, context, lang_code, history):
    if not GEMINI_API_KEY:
        return None
    contents = []
    for m in _recent_history(history):
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    contents.append({
        "role": "user",
        "parts": [{"text": f"CONTEXT:\n{context}\n\nQUESTION: {question}"}],
    })
    payload = {
        "system_instruction": {"parts": [{"text": _system_prompt(lang_code)}]},
        "contents": contents,
        "generationConfig": {
            "temperature": TEMPERATURE,
            "maxOutputTokens": MAX_TOKENS,
            # 2.5 models spend the output budget on thinking tokens by default,
            # which can consume ALL of MAX_TOKENS and return an empty candidate
            # (silently degrading every request to the Groq fallback).
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    try:
        r = requests.post(
            GEMINI_URL, params={"key": GEMINI_API_KEY},
            json=payload, timeout=60,
        )
        if r.status_code != 200:
            print(f"Gemini {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        cands = data.get("candidates", [])
        if not cands:
            return None
        parts = cands[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text and cands[0].get("finishReason") == "MAX_TOKENS":
            print("Gemini returned empty text with finishReason=MAX_TOKENS "
                  "(thinking consumed the budget?) — falling back")
        return text or None
    except Exception as e:
        print(f"Gemini error: {e}")
        return None


def _groq(question, context, lang_code, history):
    if not GROQ_API_KEY:
        return None
    messages = [{"role": "system", "content": _system_prompt(lang_code)}]
    for m in _recent_history(history):
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({
        "role": "user",
        "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}",
    })
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "stream": False,
    }
    try:
        r = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload, timeout=60,
        )
        if r.status_code != 200:
            print(f"Groq {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        choices = data.get("choices", [])
        if not choices:
            return None
        return choices[0]["message"]["content"].strip() or None
    except Exception as e:
        print(f"Groq error: {e}")
        return None


def generate_answer(question, context, lang_code="en", history=None):
    """Generate an answer. Tries Gemini first, falls back to Groq."""
    if not GEMINI_API_KEY and not GROQ_API_KEY:
        return "⚠️ No LLM configured. Set GEMINI_API_KEY or GROQ_API_KEY."

    ans = _gemini(question, context, lang_code, history)
    if ans:
        return ans
    print("Gemini unavailable — falling back to Groq")
    ans = _groq(question, context, lang_code, history)
    if ans:
        return ans
    return "⚠️ AI summary unavailable right now. Please rely on the source text below."
