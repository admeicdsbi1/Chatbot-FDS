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

# NOTE: gemini-2.5-flash 404s ("no longer available to new users") on keys
# created after its sunset — verify with ListModels before changing this.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# OpenAI-compatible free fallback providers, tried in order AFTER Gemini. Each is
# skipped unless its API key is set, so behaviour is unchanged until a key is
# added — and every provider is a SEPARATE free-quota pool, so the chain both adds
# resilience and multiplies effective free capacity. Answer text is provider-
# agnostic, so this never affects retrieval accuracy.
_OPENAI_PROVIDERS = [
    {"name": "Groq", "key": os.environ.get("GROQ_API_KEY"),
     "url": "https://api.groq.com/openai/v1/chat/completions",
     "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")},
    # Same Groq key, smaller model — its per-day token limit is far higher
    # (~500k vs the 70b's 100k TPD) and is a SEPARATE per-model pool, so it keeps
    # answering after the 70b pool 429s. Lower quality, but a good last resort.
    {"name": "Groq-8b", "key": os.environ.get("GROQ_API_KEY"),
     "url": "https://api.groq.com/openai/v1/chat/completions",
     "model": os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")},
    {"name": "OpenRouter", "key": os.environ.get("OPENROUTER_API_KEY"),
     "url": "https://openrouter.ai/api/v1/chat/completions",
     "model": os.environ.get("OPENROUTER_MODEL",
                             "meta-llama/llama-3.3-70b-instruct:free")},
    {"name": "Cerebras", "key": os.environ.get("CEREBRAS_API_KEY"),
     "url": "https://api.cerebras.ai/v1/chat/completions",
     "model": os.environ.get("CEREBRAS_MODEL", "llama-3.3-70b")},
]

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
5. ONE coach type and ONE OEM per answer. Each CONTEXT source is tagged with "Coach:" and "OEM:". NEVER blend values across different coach types (LHB/ICF/Vande Bharat/Amrit Bharat) or OEMs (Faiveley/KNORR BREMSE/Escorts Kubota). If the question does not say which coach/OEM AND the sources give different values, ASK a short clarifying question instead of guessing.
6. For WSP, specify OEM and system model (AEF G2, SWKP, MGS2) when relevant.
7. For WSP fault codes, always mention: display code number, what it means in plain language, which component is affected, and exact corrective steps.
8. Explain WHERE each component is physically located on the coach (e.g. "WSP control panel in power panel of coach", "speed sensor on axle box cover").
9. For procedures, give NUMBERED STEPS with specific button names (S1/S2/S3), expected display readings, and what to do if reading is abnormal.
10. Always mention SAFETY warnings: "Remove fuse before card removal", "Power OFF before disconnecting" etc.
11. CITE PRECISELY. Use the clause number, page, and — for a circular/instruction letter — the exact letter no. and date shown in that source's "Ref:" tag. Do not paraphrase or invent a reference.
12. SUPERSESSION: if two sources give different values for the same thing, the NEWEST instruction letter / circular (latest "Ref:" date) governs. State that value, and explicitly note it supersedes the older manual, citing BOTH dates.

FORMAT:
**Direct Answer:** [Clear 2-3 sentence summary a beginner can understand]
**Step-by-step Action:** [Numbered steps with exact values, button names, expected readings]
**Safety Caution:** [Always include if any safety info exists in context]
**Reference:** [Document name — Clause X.Y, p.N; for a circular/instruction letter add its letter no. and date exactly as in the source 'Ref:' tag]"""


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


def _openai_chat(cfg, question, context, lang_code, history):
    """Call any OpenAI-compatible chat endpoint (Groq / OpenRouter / Cerebras)."""
    if not cfg["key"]:
        return None
    messages = [{"role": "system", "content": _system_prompt(lang_code)}]
    for m in _recent_history(history):
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({
        "role": "user",
        "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}",
    })
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "stream": False,
    }
    try:
        r = requests.post(
            cfg["url"],
            headers={
                "Authorization": f"Bearer {cfg['key']}",
                "Content-Type": "application/json",
            },
            json=payload, timeout=60,
        )
        if r.status_code != 200:
            print(f"{cfg['name']} {r.status_code}: {r.text[:200]}")
            return None
        choices = r.json().get("choices", [])
        if not choices:
            return None
        return choices[0]["message"]["content"].strip() or None
    except Exception as e:
        print(f"{cfg['name']} error: {e}")
        return None


def generate_answer(question, context, lang_code="en", history=None):
    """Generate an answer. Tries Gemini first, then each configured OpenAI-
    compatible fallback provider (Groq → OpenRouter → Cerebras) in turn."""
    if not GEMINI_API_KEY and not any(p["key"] for p in _OPENAI_PROVIDERS):
        return ("⚠️ No LLM configured. Set GEMINI_API_KEY or a fallback provider "
                "key (GROQ_API_KEY / OPENROUTER_API_KEY / CEREBRAS_API_KEY).")

    ans = _gemini(question, context, lang_code, history)
    if ans:
        return ans
    for cfg in _OPENAI_PROVIDERS:
        if not cfg["key"]:
            continue
        print(f"Gemini unavailable — falling back to {cfg['name']}")
        ans = _openai_chat(cfg, question, context, lang_code, history)
        if ans:
            return ans
    return "⚠️ AI summary unavailable right now. Please rely on the source text below."
