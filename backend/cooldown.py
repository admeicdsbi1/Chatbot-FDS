"""
cooldown.py — skip a provider that just told us it is out of quota.

Every free LLM pool here is rate-capped, and a capped pool answers a 429 in about
a second — but the chain paid that round trip on EVERY request, and a hung
provider paid its full timeout. Once a pool has said "no", later requests should
go straight to one that can answer; the pool is retried after the cooldown.

In-process state: Render runs one worker, and a restart simply forgets — which
costs one failed call per pool, the same as having no cooldown at all.
"""
import time

# A per-day limit will not lift for hours; re-probe hourly rather than computing
# the provider's reset time. A per-minute limit lifts in well under two.
_DAILY_S = 3600
_MINUTE_S = 90
# Wrong key / retired model: will not fix itself, but re-probe hourly so a key
# rotated on the dashboard is picked up without a redeploy.
_BROKEN_S = 3600

_DAILY_MARKERS = ("perday", "tpd", "rpd", "daily")

_until = {}      # name -> monotonic deadline
_why = {}        # name -> short reason, for /api/health


def cooling(name):
    """True while `name` is cooling down (it should be skipped)."""
    t = _until.get(name)
    if t is None:
        return False
    if time.monotonic() >= t:
        _until.pop(name, None)
        _why.pop(name, None)
        return False
    return True


def record(name, status, body=""):
    """Put `name` in cooldown if `status` says retrying soon is pointless.

    Returns the cooldown length in seconds (0 if none was applied)."""
    # "GenerateRequestsPerDayPerProject…" (Gemini), "tokens per day (TPD)"
    # (Groq): compare with spaces and underscores removed so both match.
    flat = (body or "").lower().replace("_", "").replace(" ", "")
    if status == 429:
        secs = _DAILY_S if any(m in flat for m in _DAILY_MARKERS) else _MINUTE_S
    elif status in (401, 403, 404):
        secs = _BROKEN_S
    else:
        return 0
    _until[name] = time.monotonic() + secs
    _why[name] = f"{status}"
    return secs


def status():
    """{name: {"reason": "429", "seconds_left": 1234}} for pools cooling now."""
    now = time.monotonic()
    return {n: {"reason": _why.get(n, ""), "seconds_left": int(t - now)}
            for n, t in list(_until.items()) if t > now}


def reset():
    """Test hook."""
    _until.clear()
    _why.clear()
