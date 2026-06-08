"""
tts.py — Text-to-speech.

Default: gTTS (free). The frontend prefers the browser's on-device
SpeechSynthesis (zero server load), so this server-side path is a fallback /
optional. Sarvam AI stays optional behind SARVAM_API_KEY for nicer Hinglish.
"""
import os, re, base64, tempfile
import requests
from gtts import gTTS

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY")
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"


def clean_for_tts(text):
    """Strip markdown and pull the most important part for speech."""
    tts_text = text
    da = re.search(r'\*\*Direct Answer:\*\*\s*(.*?)(?:\*\*Step|$)', text, re.DOTALL)
    if da:
        tts_text = da.group(1).strip()
    if len(tts_text) < 50:
        st = re.search(r'\*\*Step-by-step Action:\*\*\s*(.*?)(?:\*\*Safety|\*\*Reference|---|\n📚|$)',
                       text, re.DOTALL)
        if st:
            tts_text += ". " + st.group(1).strip()
    c = re.sub(r'\*\*([^*]+)\*\*', r'\1', tts_text)
    c = re.sub(r'#{1,3}\s*', '', c)
    c = re.sub(r'\[Source.*?\]', '', c)
    c = re.sub(r'---.*$', '', c, flags=re.DOTALL)
    c = re.sub(r'📚.*$', '', c, flags=re.DOTALL)
    c = re.sub(r'\n\s*\d+\.\s*', '. ', c)
    c = re.sub(r'\n\s*[-→✔]\s*', '. ', c)
    c = re.sub(r'[*_`~]', '', c)
    c = re.sub(r'\s+', ' ', c).strip()
    if len(c) > 800:
        c = c[:800] + ". Screen par poori detail dekhein."
    return c


def _sarvam_split(text, limit=450):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    parts, current = [], ""
    for sent in sentences:
        if len(current) + len(sent) + 1 <= limit:
            current = (current + " " + sent).strip() if current else sent
        else:
            if current:
                parts.append(current)
            if len(sent) > limit:
                for i in range(0, len(sent), limit):
                    parts.append(sent[i:i + limit])
            else:
                current = sent
    if current:
        parts.append(current)
    return parts or [text[:limit]]


def _sarvam_tts(text):
    try:
        parts = _sarvam_split(text, limit=450)
        audio_chunks = []
        for part in parts:
            r = requests.post(
                SARVAM_TTS_URL,
                headers={"api-subscription-key": SARVAM_API_KEY,
                         "Content-Type": "application/json"},
                json={"inputs": [part], "target_language_code": "hi-IN",
                      "speaker": "meera", "pace": 0.9, "loudness": 1.5,
                      "speech_sample_rate": 22050, "enable_preprocessing": True,
                      "model": "bulbul:v1"},
                timeout=30,
            )
            if r.status_code == 200:
                audios = r.json().get("audios", [])
                if audios:
                    audio_chunks.append(base64.b64decode(audios[0]))
            else:
                print(f"Sarvam TTS {r.status_code}: {r.text[:150]}")
                return None
        if not audio_chunks:
            return None
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        for chunk in audio_chunks:
            tmp.write(chunk)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"Sarvam TTS exception: {e}")
        return None


def synthesize(text, lang="en"):
    """Return a path to an audio file, or None. Caller streams/removes it."""
    if not text or text.startswith(("⚠️", "⏱️")) or len(text.strip()) < 10:
        return None
    c = clean_for_tts(text)
    if len(c) < 10:
        return None

    if lang == "hi" and SARVAM_API_KEY:
        result = _sarvam_tts(c)
        if result:
            return result

    # gTTS fallback — English voice for Hinglish keeps technical terms intelligible
    gtts_lang = "hi" if (lang == "hi" and not SARVAM_API_KEY) else "en"
    try:
        tts = gTTS(text=c, lang=gtts_lang, slow=False)
    except Exception:
        tts = gTTS(text=c, lang="en", slow=False)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tts.save(tmp.name)
    return tmp.name
