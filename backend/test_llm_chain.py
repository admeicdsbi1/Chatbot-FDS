"""
Tests for the answer fallback chain's deadline, cooldown and 8b size limit
(llm.generate_answer, cooldown.py). No network: requests.post is replaced.
Run:  python backend/test_llm_chain.py    (no pytest needed)
"""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.update(GEMINI_API_KEY="g", GROQ_API_KEY="q",
                  OPENROUTER_API_KEY="", CEREBRAS_API_KEY="")
import cooldown  # noqa: E402
import llm       # noqa: E402

_fails = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fails.append(name)


class Resp:
    def __init__(self, status, body="", text=None):
        self.status_code = status
        self.text = body
        self._text = text

    def json(self):
        if "generativelanguage" in self._url:
            return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}
        return {"choices": [{"message": {"content": self._text}}]}


def fake(plan, sent=None):
    """plan: list of (url-substring, Resp) consumed in order per match."""
    def post(url, *a, **kw):
        if sent is not None:
            sent.append((url, kw.get("json"), kw.get("timeout")))
        for i, (frag, r) in enumerate(plan):
            if frag in url or frag in str(kw.get("json", {}).get("model", "")):
                plan.pop(i)
                r._url = url
                return r
        raise AssertionError(f"unexpected call {url}")
    llm.requests.post = post


def run(**kw):
    att = []
    ans, prov = llm.generate_answer("q", "[Source 1: d]\nx", "en", [], attempts=att, **kw)
    return ans, prov, att


# -- Gemini daily 429 -> falls to Groq, and the next request skips Gemini ------
cooldown.reset()
fake([("generativelanguage", Resp(429, "GenerateRequestsPerDayPerProjectPerModel-FreeTier")),
      ("gpt-oss-120b", Resp(200, text="groq answer"))])
ans, prov, att = run()
check("429 falls through to Groq", ans == "groq answer" and prov == "Groq")
check("Gemini put in cooldown", cooldown.cooling(f"gemini:{llm.GEMINI_MODEL}"))
check("daily 429 cools for an hour",
      cooldown.status()[f"gemini:{llm.GEMINI_MODEL}"]["seconds_left"] > 3000)
fake([("gpt-oss-120b", Resp(200, text="groq again"))])
ans, prov, att = run()
check("cooled Gemini skipped, no call made", att[0] == {"p": "Gemini", "st": "cool", "ms": 0}
      and ans == "groq again")

# -- per-minute 429 cools briefly -------------------------------------------
cooldown.reset()
cooldown.record("x", 429, "Rate limit reached: requests per minute")
check("per-minute 429 cools < 2 min", 0 < cooldown.status()["x"]["seconds_left"] <= 90)
check("500 does not cool", cooldown.record("y", 500, "") == 0 and not cooldown.cooling("y"))

# -- 503 is retried once ------------------------------------------------------
cooldown.reset()
llm.time.sleep = lambda s: None
fake([("generativelanguage", Resp(503, "overloaded")),
      ("generativelanguage", Resp(200, text="second try"))])
ans, prov, att = run()
check("503 retried once on Gemini", ans == "second try" and len(att) == 2)

# -- deadline: nothing starts once the budget is spent -----------------------
cooldown.reset()
saved = llm.LLM_DEADLINE_S
llm.LLM_DEADLINE_S = 0.0
fake([])
ans, prov, att = run()
check("spent budget -> no calls, all 'late'",
      prov == "none" and att and all(a["st"] == "late" for a in att))
llm.LLM_DEADLINE_S = saved

# -- per-call timeout never exceeds its cap ---------------------------------
cooldown.reset()
sent = []
fake([("generativelanguage", Resp(200, text="ok"))], sent)
run()
check("Gemini timeout capped", sent[0][2] <= llm.GEMINI_TIMEOUT_S)

# -- 8b tier: trimmed context, no history, capped output ----------------------
cooldown.reset()
big = "\n\n".join(f"[Source {i}: d]\n" + "x" * 3000 for i in range(1, 9))
sent = []
fake([("generativelanguage", Resp(429, "PerDay")),
      ("gpt-oss-120b", Resp(429, "tokens per day (TPD)")),
      ("gpt-oss-20b", Resp(200, text="small"))], sent)
hist = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "a" * 5000}]
ans, prov = llm.generate_answer("q", big, "en", hist, max_tokens=3000)
body = sent[-1][1]
check("8b answered", prov == "Groq-8b" and ans == "small")
check("8b gets no history", len(body["messages"]) == 2)
check("8b output capped", body["max_tokens"] == 1024)
check("gpt-oss reasoning kept short", body.get("reasoning_effort") == "low")
check("non-gpt-oss model gets no reasoning param",
      llm._reasoning_opts("google/gemma-4-31b-it:free") == {})
user = body["messages"][-1]["content"]
check("8b context trimmed at a source boundary",
      len(user) < 7000 + 200 and user.count("[Source ") == 2)

# -- trim keeps a facts block and at least one source ------------------------
t = llm._trim_context("[Corpus facts] 27 CAIs\n\n[Source 1: d]\n" + "y" * 500, 100)
check("facts + first source survive a tiny budget",
      t.startswith("[Corpus facts]") and "[Source 1:" in t and len(t) == 100)
check("short context untouched", llm._trim_context("abc", 7000) == "abc")

print(f"\n{len(_fails)} failure(s)")
sys.exit(1 if _fails else 0)
