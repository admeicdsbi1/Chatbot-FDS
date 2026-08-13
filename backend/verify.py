"""
verify.py — numeric-fidelity hard guard.

After the LLM drafts an answer, every safety-critical *value* it states must be
present verbatim in the retrieved source context, or it is suppressed. This is
the last line of defence against a hallucinated torque / voltage / air-gap /
fault-code / part-number reaching a maintenance technician.

Design principle: **fail CLOSED**. A value the guard cannot confirm is replaced
with a "refer to manual/supervisor" marker. A false suppression is safe (the
technician consults the manual); a false pass — a confident wrong number — is a
safety defect, so any ambiguity resolves to suppression.

What is checked (answer BODY only; the trailing "**Reference:**" citation block
with its page/clause numbers and letter dates is left untouched):
  - numbers carrying a unit           e.g. 110 V, 0.8 mm, 3.8 bar, 68 °C, 90 Nm
  - tolerances / ranges               e.g. 0.8–1.5 mm, ±0.5 mm
  - fault / error / trip codes         e.g. "fault code 4.3", "error code E12"
  - part / model designations          e.g. FT0027800-003, MB04, MGS2, DV12

Verification is unit-normalized: "2A" ≡ "2 A", "3.8bar" ≡ "3.8 bar". A value is
confirmed when its whitespace-stripped form (or, for a range, either endpoint
with its unit) is a substring of the whitespace-stripped context.

Known limitation: a value whose unit lives in a *separate table cell* from its
number (header "(mm)" far from the cell "0.8") cannot be confirmed by adjacency
and will be suppressed — safe, but over-cautious. The accuracy eval (ingest/eval)
measures this false-suppression rate so the patterns can be tuned.
"""
import re

PLACEHOLDER = "[value not confirmed in source — refer to manual/supervisor]"

# Units seen across FSDS/FDSS/WSP and general mechanical maintenance. Longer
# tokens must precede their prefixes in the alternation so "Vdc" beats "V",
# "Nm" beats "N", "kHz" beats "Hz", "mm" beats "m".
_UNITS = [
    "vdc", "vac", "kv", "mv", "va", "v",
    "ma", "ka", "a",
    "kw", "w",
    "mpa", "kpa", "psi", "bar",
    "knm", "nm", "n",
    "khz", "mhz", "hz",
    "kohm", "mohm", "ohm", "Ω",       # Ω
    "mm²", "sqmm", "µm", "um", "mm", "cm", "km", "m",
    "kg", "g", "t",
    "°c", "℃", "degc",            # °C, ℃
    "ms", "µs", "sec", "s", "min", "hr", "h",
    "rpm", "%", "lpm",
]
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(_UNITS, key=len, reverse=True))

_NUM = r"\d+(?:[.,]\d+)?"

# A value: optional ± sign, a number, an optional range/tolerance partner, a unit.
# The trailing lookahead stops a unit letter from being glued onto a following
# word (so "12 Valve" does NOT read as 12 V).
_VALUE_RE = re.compile(
    r"(?P<val>(?:±\s*)?" + _NUM
    + r"(?:\s*(?:±|\+/-|to|–|—|~|-)\s*" + _NUM + r")?"
    + r"\s*(?:" + _UNIT_ALT + r"))(?![A-Za-z0-9µ])",
    re.IGNORECASE,
)

# Fault/error/trip/alarm/display codes — only when a keyword makes intent explicit,
# to avoid stripping ordinary numbers or button names (S1/S2).
_FAULT_RE = re.compile(
    r"(?:fault|error|failure|trip|alarm|display)\s*code[s]?\s*"
    r"(?:no\.?|number|[:#\-])?\s*(?P<code>[A-Za-z]?\d{1,4}(?:\.\d+)?)",
    re.IGNORECASE,
)

# Part / model designations: a token >=4 chars mixing letters and digits, e.g.
# FT0027800-003, MB04, EB01, DV12, MGS2. Pure numbers (dates, clause nums) and
# short button names (S1) are excluded by the letter+digit+length requirements.
_PART_RE = re.compile(
    r"\b(?=[A-Za-z0-9][A-Za-z0-9/\-]{3,})(?=[A-Za-z0-9/\-]*[A-Za-z])"
    r"(?=[A-Za-z0-9/\-]*\d)[A-Za-z0-9]+(?:[/\-][A-Za-z0-9]+)*\b"
)

# Schedule, examination and interval names are shaped exactly like part numbers
# (letters + digits + a hyphen) but designate a maintenance occasion, not a
# component. Guarding them was a live defect: the corpus writes "SS 1" / "SS-II"
# / "2 pack" and an answer writing "SS-1" / "SS-2" / "2-pack" had the token
# replaced by the placeholder MID-SENTENCE, so a correct answer read as a
# withheld value. They carry no safety-critical magnitude, so exclude them.
_SCHEDULE_TOKENS = re.compile(
    r"^(?:ss[-\s]?(?:1|2|3|i{1,3})|poh|ioh|aoh|toh|d[-\s]?[123](?:[-\s]?d?[123])?"
    r"|\d{1,2}[-\s]?m(?:onthly)?|ss\d?/\d+m?)$",
    re.IGNORECASE,
)

# Where the citation block starts; everything from here on is not guarded.
_REF_SPLIT = re.compile(r"\*\*\s*reference\s*:?\s*\*\*|(?:^|\n)\s*reference\s*:",
                        re.IGNORECASE)


def _compact(s):
    """Lowercase, unify dashes, drop ± and whitespace so unit spacing/commas
    don't defeat a match. Commas in decimals are also normalized to dots."""
    s = s.lower()
    s = (s.replace("–", "-").replace("—", "-").replace("~", "-")
           .replace("±", ""))
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)   # 3,8 -> 3.8
    s = re.sub(r"\s+", "", s)
    return s


def _compact_sep(s):
    """_compact, plus separators dropped — for part/model designations only.

    A designation's separators are formatting, not identity: the same part is
    written FT0027800-003 / FT0027800/003 / "FT0027800 003" across manuals, and
    _compact removes the spacing but NOT the hyphen, so the three forms did not
    match each other. Never used for values or ranges, where '-' means 'to'."""
    return _compact(s).replace("-", "").replace("/", "")


def _value_targets(val):
    """Compact strings, any of which appearing in the compacted context confirms
    the value. For a range, either endpoint carrying the unit also confirms it."""
    t = _compact(val)
    targets = {t}
    m = re.match(r"^([\d.]+)-([\d.]+)([a-zµ°℃%²Ω]+)$", t)
    if m:
        a, b, unit = m.groups()
        targets.add(a + unit)
        targets.add(b + unit)
    return targets


def _spans(answer):
    """All (start, end, kind, verify_targets) value spans in the answer body,
    de-overlapped with priority value > fault-code > part-number."""
    found = []
    for m in _VALUE_RE.finditer(answer):
        found.append((m.start("val"), m.end("val"), "value",
                      _value_targets(m.group("val"))))
    for m in _FAULT_RE.finditer(answer):
        found.append((m.start("code"), m.end("code"), "fault-code",
                      {_compact(m.group("code"))}))
    for m in _PART_RE.finditer(answer):
        tok = m.group(0)
        if _SCHEDULE_TOKENS.match(tok):
            continue                     # SS-2 / POH / 9M name an occasion, not a part
        # matched against the separator-stripped context (see _compact_sep)
        found.append((m.start(), m.end(), "part-number", {_compact_sep(tok)}))

    found.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    out, last_end = [], -1
    for start, end, kind, targets in found:
        if start >= last_end:            # keep first / longest, drop overlaps
            out.append((start, end, kind, targets))
            last_end = end
    return out


def guard_answer(answer, context):
    """Return (clean_answer, stripped) where every unconfirmed value in the
    answer body has been replaced by PLACEHOLDER. `stripped` lists the
    (kind, text) of each suppressed value for logging."""
    if not answer or not context:
        return answer, []

    split = _REF_SPLIT.search(answer)
    body_end = split.start() if split else len(answer)
    body, tail = answer[:body_end], answer[body_end:]

    ctx = _compact(context)
    ctx_sep = _compact_sep(context)      # part/model designations only
    stripped = []
    pieces, cursor = [], 0
    for start, end, kind, targets in _spans(body):
        haystack = ctx_sep if kind == "part-number" else ctx
        if any(t and t in haystack for t in targets):
            continue                     # confirmed verbatim in source
        pieces.append(body[cursor:start])
        pieces.append(PLACEHOLDER)
        stripped.append((kind, body[start:end]))
        cursor = end
    pieces.append(body[cursor:])
    return "".join(pieces) + tail, stripped
