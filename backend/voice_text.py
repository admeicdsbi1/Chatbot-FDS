"""
voice_text.py — Domain dictionaries + Hindi/Hinglish voice helpers.

Ported verbatim from the original Gradio app.py (the domain-tuned brain).
Used by stt.py (transcription correction/confidence) and rag.py (query expansion).
"""
import re
from difflib import SequenceMatcher

# ================================================================
# ABBREVIATIONS — expanded for retrieval
# ================================================================
ABBREVIATIONS = {
    # K-designations from panel wiring schematics (IEC: K = relay). The manuals'
    # parts lists name these by function, not designation — map the common ones
    # staff search by so retrieval finds the functional entry.
    "k05": "timer relay off delay brake module panel",
    "fsds": "fire smoke detection system aspiration",
    "fdss": "fire detection suppression system aerosol water mist",
    "fds": "fire detection system",
    "mcb": "miniature circuit breaker 2A",
    "lhb": "linke hofmann busch coach",
    "icf": "integral coach factory coach",
    "vesda": "very early smoke detection apparatus xtrailis",
    "lhd": "linear heat detection cable",
    "oem": "original equipment manufacturer vendor",
    "asd": "aspiration smoke detector",
    "sbc": "switch board cabinet",
    "poh": "periodic overhaul",
    "ioh": "intermediate overhaul",
    "ss1": "shop schedule 1 maintenance",
    "ss2": "shop schedule 2 maintenance",
    "ss3": "shop schedule 3 maintenance",
    "bta": "bulb thermal actuator activation device firepro",
    "hasp": "heat activated sampling point pantry",
    "tcms": "train control management system display driver",
    "mcp": "master control panel driver desk",
    "ecc": "electrical control cabinet panel",
    "rmpu": "relay module power unit panel",
    "crw": "cab rear wall panel",
    "dtc": "driving trailer coach",
    "ndtc": "non driving trailer coach",
    "tc": "trailer coach",
    "mc": "motor coach",
    "acu": "auxiliary converter unit",
    "ltc": "line transformer cubicle",
    "rtc": "real time clock battery",
    "firelink": "hochiki firelink 25 aspiration detection unit",
    "led": "light emitting diode indication panel",
    "pcb": "printed circuit board fire panel",
    "d1": "depot schedule 1 maintenance amrit bharat",
    "d2": "depot schedule 2 maintenance amrit bharat",
    "d3": "depot schedule 3 maintenance amrit bharat",
    # WSP abbreviations
    "wsp": "wheel slide protection anti-skid braking",
    "wspcu": "wheel slide protection control unit electronic box",
    "mgs2": "knorr bremse MGS2 WSP system control unit",
    "swkp": "faiveley SWKP AS 20 R WSP system",
    "aef": "faiveley AEF G2 WSP electronic unit",
    "dv12": "dump valve DV12 anti-skid solenoid valve",
    "wbi": "wheel brake interface board WBI_1 WBI_2",
    "mmi": "man machine interface display push button WSP",
    "wspmon": "WSP monitoring diagnostic software RS232",
    "kb": "knorr bremse OEM manufacturer",
    "ekl": "escorts kubota limited WSP OEM",
    "ir": "indian railways",
    "rdso": "research designs standards organisation",
    "camtech": "centre advanced maintenance technology IRCAMTECH",
    "esra": "electronic system railway applications KNORR BREMSE",
    "uic": "union internationale chemins fer international railways",
    "jop": "escorts kubota JOP card dump valve output board",
    "jfp": "escorts kubota JFP card speed sensor input board",
    "jio": "escorts kubota JIO card relay output board",
    "gui": "graphical user interface WSP diagnostic application",
}

PROCEDURAL_SIGNALS = [
    "how to", "procedure", "steps", "test", "testing", "check",
    "troubleshoot", "troubleshooting", "fix", "repair", "replace",
    "diagnose", "fault", "error", "schedule", "maintenance",
    "install", "installation", "activate", "activation", "reset",
    "clean", "cleaning", "download", "service", "inspect",
    "post fire", "recommission", "ventilate",
    "kaise", "karna", "tarika",
    # WSP procedural signals
    "overhaul", "self test", "self-test", "manual test", "system test",
    "air gap", "gap setting", "shim", "choke setting",
    "dump valve", "speed sensor", "phonic wheel",
    "error code", "fault code", "defect code", "display code",
    "wsp test", "brake test", "s1 button", "s2 button", "s3 button",
    "checking procedure", "spare parts",
]

# ================================================================
# HINDI / HINGLISH VOICE SUPPORT
# ================================================================
KNOWN_DOMAIN_TERMS = [
    "fsds", "fdss", "fds", "mcb", "lhb", "icf", "vesda", "lhd",
    "oem", "asd", "sbc", "poh", "ioh", "ss1", "ss2", "ss3",
    "bta", "hasp", "tcms", "mcp", "ecc", "rmpu", "crw",
    "dtc", "ndtc", "acu", "ltc", "rtc",
    "firelink", "led", "pcb", "d1", "d2", "d3",
    "smoke test", "fire test", "error code", "fault code",
    "troubleshoot", "maintenance", "schedule", "procedure",
    "aerosol", "suppression", "detection", "aspiration",
    "hochiki", "firepro", "pyrogen", "stat-x",
    "vande bharat", "amrit bharat",
    "smoke detector", "heat detector", "fire panel",
    "circuit breaker", "relay module", "control panel",
    "fsds ka smoke test kaise kare",
    "error code kya hai", "fault aa raha hai",
    "kaam nahi kar raha", "power nahi aa raha",
    "testing kaise kare", "check kaise kare",
    "repair kaise kare", "procedure batao",
    "mcb trip ho raha hai", "alarm aa raha hai",
    "aerosol generator", "bta safety pin",
    # WSP domain terms
    "wsp", "wspcu", "wheel slide protection",
    "dump valve", "anti skid valve", "dv12", "solenoid valve",
    "speed sensor", "phonic wheel", "air gap", "toothed wheel",
    "brake cylinder", "pressure switch",
    "mmi", "mmi display", "man machine interface",
    "faiveley", "wabtec", "knorr bremse", "mgs2",
    "swkp", "aef g2", "aef",
    "escorts kubota", "ekl", "jop card", "jfp card", "jio card",
    "wbi board", "wbi", "digital output board",
    "self test", "manual test", "system test",
    "wspmon", "diagnostic software", "gui application",
    "choke setting", "exhaust time", "fill time",
    "watchdog", "cpu board", "power board",
    "mb04", "pb03", "eb01", "esra",
    "speed threshold", "standby mode",
    "wsp error code", "wsp fault code", "display 99", "display 95",
    "code 7201", "code 7301", "code 8888", "code 89",
    "wsp kaise test kare", "dump valve kaise check kare",
    "speed sensor change karna", "air gap kitna hona chahiye",
    "wsp fault aa raha hai", "wsp kaam nahi kar raha",
    "phonic wheel check kare", "brake cylinder pressure",
    "wsp self test", "wsp manual test",
    "fuse 63", "fuse 65", "s1 button", "s2 button", "s3 button",
    "cut off valve", "exhaust valve",
]

HINDI_CORRECTIONS = {
    "f s d s": "fsds", "f.s.d.s": "fsds", "f-s-d-s": "fsds",
    "f d s s": "fdss", "f.d.s.s": "fdss",
    "f d s": "fds", "m c b": "mcb", "m.c.b": "mcb",
    "l h b": "lhb", "b t a": "bta", "p c b": "pcb",
    "l e d": "led", "s s 1": "ss1", "s s 2": "ss2", "s s 3": "ss3",
    "vesta": "vesda", "westa": "vesda", "wesda": "vesda",
    "vanda bharat": "vande bharat", "vanday bharat": "vande bharat",
    "wande bharat": "vande bharat",
    "amrut bharat": "amrit bharat",
    "hoshiki": "hochiki", "ho chiki": "hochiki",
    "fire pro": "firepro", "fyre pro": "firepro",
    "pirogen": "pyrogen", "pyrrogen": "pyrogen",
    "stat x": "stat-x", "stats x": "stat-x",
    "fire link": "firelink",
    "kaise karen": "kaise kare", "kayse kare": "kaise kare",
    "kaise karain": "kaise kare",
    "kya karein": "kya kare",
    "tareeka": "tarika", "tareeqa": "tarika",
    # WSP Hindi/Whisper corrections
    "w s p": "wsp", "w.s.p": "wsp", "w-s-p": "wsp",
    "double u s p": "wsp", "double you s p": "wsp",
    "doubleyousp": "wsp",
    "wheel slide": "wheel slide protection",
    "wheel slid": "wheel slide protection",
    "wheel slight": "wheel slide protection",
    "will slide": "wheel slide protection",
    "dump wall": "dump valve", "damp valve": "dump valve",
    "dump well": "dump valve", "dump valv": "dump valve",
    "anti skid wall": "anti skid valve",
    "d v 12": "dv12", "dv 12": "dv12",
    "speed censor": "speed sensor", "speed senser": "speed sensor",
    "speed sensar": "speed sensor",
    "phonic will": "phonic wheel", "fonic wheel": "phonic wheel",
    "fonic will": "phonic wheel", "phonik wheel": "phonic wheel",
    "air gup": "air gap", "air gep": "air gap",
    "brake celinder": "brake cylinder", "break cylinder": "brake cylinder",
    "pressure svitch": "pressure switch",
    "m m i": "mmi", "m.m.i": "mmi",
    "faivley": "faiveley", "faively": "faiveley",
    "favaley": "faiveley", "fively": "faiveley",
    "nor bremse": "knorr bremse", "nor brems": "knorr bremse",
    "nor brams": "knorr bremse", "knor bremse": "knorr bremse",
    "m g s 2": "mgs2", "mgs 2": "mgs2",
    "a e f": "aef", "a.e.f": "aef", "aef g 2": "aef g2",
    "w b i": "wbi", "w.b.i": "wbi",
    "watch dog": "watchdog",
    "self test": "self-test",
    "chok setting": "choke setting", "chalk setting": "choke setting",
    "wsp mon": "wspmon",
    "escort": "escorts kubota", "escord": "escorts kubota",
    "kubota wsp": "escorts kubota wsp",
    "e k l": "ekl", "e.k.l": "ekl",
    "m b 04": "mb04", "mb 04": "mb04",
    "p b 03": "pb03", "pb 03": "pb03",
    "e b 01": "eb01", "eb 01": "eb01",
    # Common Hinglish field queries — Whisper mangling corrections
    "dam valve": "dump valve",
    "dan valve": "dump valve", "dum valve": "dump valve",
    "dump walw": "dump valve", "dump valw": "dump valve",
    "don valve": "dump valve",
    "fionic wheel": "phonic wheel",
    "spid sensor": "speed sensor",
    "anti skid": "WSP anti-skid", "antiskid": "WSP anti-skid",
    "selft test": "self test",
    "kya kam": "kya kaam",
    "kaise kam": "kaise kaam",
    "eror code": "error code",
    "folt code": "fault code",
}

WHISPER_HALLUCINATIONS = [
    "thank you for watching", "thanks for watching",
    "please subscribe", "like and subscribe",
    "subscribe to my channel", "thank you.", "thanks.", "bye.", "you.",
    # Common Whisper hallucinations on short/unclear Hindi audio
    "that was the best part of this", "that was the best part of this.",
    "the best part of this", "this is the best",
    "i don't know what to say", "i don't know",
    "so", "so.", "okay.", "okay", "yes.", "no.", "hmm.",
    "and that's it", "and that's it.", "that's it.",
    "what do you think", "what do you think?",
    "i'm not sure", "i'm not sure.",
    "the end", "the end.",
    "music", "music.", "[music]", "(music)",
    "silence", "silence.", "[silence]",
    "applause", "[applause]",
    "you", "you.", "i", "i.",
    "subtitles by", "subtitles",
    "this is a test", "testing testing",
    "one two three",
]


# ================================================================
# HINGLISH → ENGLISH normalization for retrieval
# ================================================================
HINGLISH_TO_ENGLISH = {
    "mein": "", "me": "", "ka": "", "ki": "", "ke": "", "hai": "",
    "kya": "what", "kaise": "how", "kare": "do", "karna": "do",
    "chahiye": "should", "batao": "tell explain",
    "kab": "when", "kahan": "where", "kaun": "which",
    "kyu": "why", "kyun": "why", "kyon": "why",
    "aa": "showing coming", "aaraha": "showing coming",
    "aa raha": "showing coming", "aarhi": "showing coming",
    "dikhara": "showing displaying", "dikhra": "showing displaying",
    "dikha": "showing display", "show": "showing display",
    "matlab": "meaning means", "iska": "this",
    "ye": "this", "wo": "that", "yeh": "this", "woh": "that",
    "nahi": "not no failure", "nhi": "not no failure",
    "kaam": "work working function", "kam": "work working",
    "chalu": "start working running", "band": "stop off not working",
    "theek": "fix repair correct ok", "thik": "fix repair correct ok",
    "sahi": "correct proper ok", "galat": "wrong incorrect fault",
    "badal": "replace change", "badalna": "replace change",
    "nikal": "remove", "lagao": "install fit apply",
    "check": "check test verify inspect", "dekho": "check see inspect",
    "problem": "fault error problem issue", "dikkat": "fault error problem issue",
    "kharab": "faulty damaged defective failure", "tut": "broken damaged",
    "toota": "broken damaged", "gaya": "", "gaye": "",
    "wala": "", "wali": "", "wale": "",
    "abhi": "current now", "pehle": "previous before",
    "baad": "after", "pura": "full complete all",
    "kitna": "how much value",
    "tarika": "procedure method steps how to",
    "code": "code display fault error",
    "error": "error fault code display",
    "fault": "fault error code defect",
    "display": "display code showing mmi",
    "sensor": "sensor speed sensor",
    "valve": "valve dump valve anti skid",
    "gap": "gap air gap clearance",
    "pressure": "pressure brake cylinder",
    "board": "board card circuit mb04 pb03 eb01",
    "test": "test self-test testing procedure",
}


# ================================================================
# Transcription cleanup + confidence
# ================================================================
def correct_transcription(text):
    if not text:
        return ""
    corrected = text.lower().strip()

    # Full-string hallucination check (before corrections).
    # Exact match always rejects. startswith() only for MULTI-WORD phrases,
    # so a real query like "so dump valve test" isn't killed by the token "so".
    corrected_clean = re.sub(r'[.,!?\s]+', ' ', corrected).strip()
    for h in WHISPER_HALLUCINATIONS:
        h_clean = re.sub(r'[.,!?\s]+', ' ', h.lower()).strip()
        if not h_clean:
            continue
        if corrected_clean == h_clean:
            return ""
        if " " in h_clean and corrected_clean.startswith(h_clean):
            return ""

    # Remove hallucinations. Multi-word phrases are stripped as substrings;
    # short/single-word ones ONLY as whole words (word boundaries), otherwise
    # "i"/"so"/"you" would gut valid words like "nahi" -> "nah".
    for h in WHISPER_HALLUCINATIONS:
        hl = h.lower().strip()
        if not hl:
            continue
        if " " in hl:
            corrected = corrected.replace(hl, " ")
        else:
            corrected = re.sub(rf'\b{re.escape(hl)}\b', ' ', corrected)

    # Apply domain corrections as WHOLE-WORD/PHRASE matches. Raw substring
    # replace double-applies when `wrong` is a prefix of `right`
    # (e.g. "dump valv"->"dump valve" turned "dump valve" into "dump valvee").
    for wrong, right in HINDI_CORRECTIONS.items():
        corrected = re.sub(rf'\b{re.escape(wrong)}\b', right, corrected)

    corrected = re.sub(r'\s+', ' ', corrected).strip()
    corrected = re.sub(r'^[.,!?\s]+', '', corrected)

    if len(corrected.strip()) < 2:
        return ""
    return corrected


def compute_voice_confidence(original, corrected):
    if not corrected or len(corrected.strip()) < 2:
        return 0.0
    word_count = len(corrected.split())
    if word_count <= 1:
        return 0.3
    words = set(corrected.lower().split())
    domain_hits = sum(1 for t in KNOWN_DOMAIN_TERMS if set(t.split()) & words)

    # Reject generic English with ZERO domain relevance (likely hallucination)
    hindi_markers = {"kaise", "kare", "kya", "hai", "nahi", "batao",
                     "tarika", "raha", "rahi", "karna", "hota", "karo",
                     "mein", "ka", "ki", "ke", "chahiye", "kab", "kahan"}
    has_hindi = bool(words & hindi_markers)
    has_devanagari = any('ऀ' <= c <= 'ॿ' for c in corrected)

    if domain_hits == 0 and not has_hindi and not has_devanagari:
        filler_words = {"the", "a", "an", "is", "was", "that", "this", "of",
                        "it", "in", "to", "and", "for", "with", "on", "at",
                        "but", "or", "not", "do", "did", "will", "can",
                        "best", "part", "good", "bad", "know", "think",
                        "say", "said", "don't", "i'm", "what", "how"}
        filler_ratio = len(words & filler_words) / max(len(words), 1)
        if filler_ratio > 0.5:
            return 0.1
        if filler_ratio > 0.3:
            return 0.25

    sim = SequenceMatcher(None, original.lower(), corrected.lower()).ratio()
    length_factor = min(word_count / 4.0, 1.0)
    conf = 0.3 * sim + 0.40 * min(domain_hits / 2.0, 1.0) + 0.30 * length_factor
    return round(min(conf, 1.0), 2)


def generate_alternatives(text, n=3):
    text_lower = text.lower().strip()
    words = text_lower.split()
    alts = []
    for i, w in enumerate(words):
        cl = re.sub(r'[^\w]', '', w)
        if cl in ABBREVIATIONS:
            aw = words.copy()
            aw[i] = ABBREVIATIONS[cl].split()[0]
            a = " ".join(aw)
            if a != text_lower:
                alts.append(a)
    for term in KNOWN_DOMAIN_TERMS:
        sim = SequenceMatcher(None, text_lower, term).ratio()
        if 0.40 < sim < 0.95:
            alts.append(term)
    seen = {text_lower}
    ranked = []
    for a in alts:
        ac = a.strip().lower()
        if ac not in seen and ac and len(ac) > 1:
            seen.add(ac)
            sim = SequenceMatcher(None, text_lower, ac).ratio()
            ranked.append((sim, ac))
    ranked.sort(key=lambda x: -x[0])
    results = []
    for _, a in ranked[:n]:
        display = []
        for w in a.split():
            if re.match(r'^[a-z]{1,5}$', w) and w in ABBREVIATIONS:
                display.append(w.upper())
            else:
                display.append(w.capitalize() if w.isascii() else w)
        results.append(" ".join(display))
    return results


# ================================================================
# Language detection
# ================================================================
def _has_urdu_arabic_script(text):
    """Detect if Whisper mistakenly output Urdu/Arabic script for a Hindi query."""
    return any('؀' <= c <= 'ۿ' or 'ﭐ' <= c <= '﷿' for c in text)


def detect_language(text):
    if not text:
        return "en"
    d = sum(1 for c in text if 'ऀ' <= c <= 'ॿ')
    if d > len(text) * 0.10:
        return "hi"
    if _has_urdu_arabic_script(text):
        return "hi"
    hindi_markers = {
        "kaise", "kare", "kya", "hai", "nahi", "batao", "tarika",
        "raha", "rahi", "karna", "hota", "karo", "ka", "ki", "ke",
        "kab", "kahan", "kitna", "wala", "wali", "lagao", "dekho",
        "kaam", "kam", "karta", "karti", "karte", "hain", "tha",
        "thi", "ho", "bhi", "par", "se", "mein", "aur", "yeh",
        "woh", "isko", "uska", "hamara", "bataye", "samjhao",
        "theek", "band", "chalu", "check", "kholo", "lagana",
    }
    words = set(text.lower().split())
    strong_markers = {"kaise", "kya", "hota", "karna", "batao", "tarika",
                      "kaam", "karta", "samjhao", "bataye"}
    if words & strong_markers:
        return "hi"
    if len(words & hindi_markers) >= 2:
        return "hi"
    return "en"
