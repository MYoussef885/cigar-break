"""Opt-in sharing (FR-S1 to FR-S4, D-015, architecture §10).

`build_payload`, `problems` and `issue_url` are pure. `run` is the flow: show
the exact payload, ask, then open a prefilled GitHub issue in the browser.
Cigar itself makes no network call: nothing leaves the machine until the
developer submits the issue on github.com.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cigar import __version__, config, defaults
from cigar.knee import Fit

SCHEMA_VERSION = 1
REPO = "MYoussef885/cigar-break"
NEW_ISSUE = f"https://github.com/{REPO}/issues/new"
MAX_URL = 7_500
PENDING_MAX_AGE = 3600  # a payload shown by /cigar:share stays confirmable this long

KEYS = {
    "schema_version",
    "cigar_version",
    "harness",
    "model",
    "window",
    "sessions",
    "events",
    "buckets",
    "knee",
    "confidence",
    "default_knee",
}
BUCKET_KEYS = {"lo", "hi", "events", "weight"}
HARNESSES = ("claude-code", "simulated", "other")
CONFIDENCE = ("low", "medium", "high")
# A model ID, not a path: no leading "/", "~" or ".", no "\\", no "//", no spaces.
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@\[\]/-]{0,79}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+[0-9A-Za-z.+-]*$")


def harness_label(harnesses: Sequence[str]) -> str:
    """Only these labels are shared; a custom harness name could identify someone."""
    names = set(harnesses) - {""}
    if names == {"claude-code"}:
        return "claude-code"
    if names == {"simulated"}:
        return "simulated"
    return "other"


def build_payload(fit: Fit, harnesses: Sequence[str], version: str = __version__) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "cigar_version": version,
        "harness": harness_label(harnesses),
        "model": fit.model,
        "window": fit.window,
        "sessions": fit.sessions,
        "events": fit.events,
        "buckets": [
            {"lo": b.lo, "hi": b.hi, "events": b.events, "weight": round(b.weight, 2)}
            for b in fit.buckets
        ],
        "knee": fit.knee,
        "confidence": fit.confidence,
        "default_knee": fit.default_knee,
    }


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10**9


def problems(payload: Any) -> list[str]:
    """Everything wrong with a payload; empty means it is safe and well formed.

    This is an allowlist: exact keys, typed values, and the only strings allowed
    are a model ID, a version and fixed labels. Used before sharing and by the
    maintainer's ingest script.
    """
    if not isinstance(payload, dict):
        return ["the payload is not an object"]
    out = []
    if set(payload) != KEYS:
        extra, missing = set(payload) - KEYS, KEYS - set(payload)
        out.append(f"keys differ (extra: {sorted(extra)}, missing: {sorted(missing)})")
    if payload.get("schema_version") != SCHEMA_VERSION:
        out.append("unknown schema_version")
    if not isinstance(payload.get("cigar_version"), str) or not VERSION_RE.match(
        payload["cigar_version"]
    ):
        out.append("cigar_version is not a version")
    if payload.get("harness") not in HARNESSES:
        out.append(f"harness must be one of {HARNESSES}")
    model = payload.get("model")
    if not isinstance(model, str) or not MODEL_RE.match(model) or "//" in model:
        out.append("model is not a plain model ID")
    elif model.startswith("ft:") or model.count(":") > 1:
        out.append("model looks like a fine-tune ID, which can name an organization")
    if payload.get("window") not in defaults.WINDOWS:
        out.append(f"window must be one of {sorted(defaults.WINDOWS)}")
    if payload.get("confidence") not in CONFIDENCE:
        out.append(f"confidence must be one of {CONFIDENCE}")
    for key in ("sessions", "events", "default_knee"):
        if not _count(payload.get(key)):
            out.append(f"{key} must be a non-negative integer")
    if payload.get("knee") is not None and not _count(payload.get("knee")):
        out.append("knee must be an integer or null")
    buckets = payload.get("buckets")
    if not isinstance(buckets, list) or not buckets:
        out.append("buckets must be a non-empty list")
    else:
        step = defaults.KNEE_BUCKET_TOKENS
        for b in buckets:
            if not isinstance(b, dict) or set(b) != BUCKET_KEYS:
                out.append("each bucket has exactly lo, hi, events, weight")
                break
            weight = b.get("weight")
            if (
                not all(_count(b.get(k)) for k in ("lo", "hi", "events"))
                or b["lo"] % step
                or b["hi"] != b["lo"] + step
                or not isinstance(weight, int | float)
                or isinstance(weight, bool)
                or weight < 0
            ):
                out.append(f"bucket {b} is malformed")
                break
    return out


def issue_url(payload: dict, limit: int = MAX_URL) -> tuple[str, dict]:
    """The prefilled issue URL, and the payload it carries.

    If the URL is too long, buckets with the fewest events are dropped until it fits.
    """
    payload = {**payload, "buckets": list(payload["buckets"])}
    while True:
        title = (
            f"Curve: {payload['model']} ({payload['window']}), "
            + (f"knee {round(payload['knee'] / 1000)}k" if payload["knee"] else "no knee")
            + f", {payload['confidence']} confidence"
        )
        query = urllib.parse.urlencode(
            {
                "template": "curve.yml",
                "title": title,
                "payload": json.dumps(payload, separators=(",", ":")),
            },
            quote_via=urllib.parse.quote,
        )
        url = f"{NEW_ISSUE}?{query}"
        if len(url) <= limit or len(payload["buckets"]) <= 1:
            return url, payload
        smallest = min(payload["buckets"], key=lambda b: (b["events"], -b["lo"]))
        payload["buckets"].remove(smallest)


def choose(fits: Sequence[Fit], model: str | None, window: str | None) -> Fit | None:
    for f in fits:
        if (model is None or f.model == model) and (window is None or f.window == window):
            return f
    return None


# --- the flow ------------------------------------------------------------------------
PREAMBLE = (
    "This is everything `cigar share` would publish, as a GitHub issue on {repo}:\n"
    "aggregate counts per 10k-token bucket for one model. No paths, project names, code, "
    "prompts or user identifiers.\nThe model ID is sent as written."
)
OPENING = (
    "Opening a prefilled GitHub issue in your browser. Nothing is sent until you press "
    "Submit there."
)


def _pending_path(cfg: config.Config) -> Path:
    return cfg.home / "share-pending.json"


def _open(url: str) -> bool:
    import webbrowser

    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def _publish(payload: dict, out: Any) -> int:
    url, sent = issue_url(payload)
    if sent != payload:
        dropped = len(payload["buckets"]) - len(sent["buckets"])
        print(f"(The URL was too long; dropped the {dropped} smallest buckets.)", file=out)
    print(OPENING, file=out)
    if not _open(url):
        print("No browser opened. Open this URL to review and submit:", file=out)
    print(url, file=out)
    return 0


def run(
    cfg: config.Config,
    fits: Sequence[Fit],
    harnesses: dict[tuple[str, str], list[str]],
    model: str | None = None,
    window: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    skill: str | None = None,
    out: Any = None,
) -> int:
    out = out or sys.stdout
    pending = _pending_path(cfg)
    if skill is not None and skill.strip().lower() == "confirm":
        try:
            saved = json.loads(pending.read_text())
        except (OSError, ValueError):
            saved = None
        if not saved or time.time() - saved.get("ts", 0) > PENDING_MAX_AGE:
            print("Nothing to confirm. Run /cigar:share first to see the payload.", file=out)
            return 1
        pending.unlink(missing_ok=True)
        if problems(saved["payload"]):
            print("The saved payload failed its check; nothing was shared.", file=out)
            return 1
        print("Sharing the payload shown before:", file=out)
        print(json.dumps(saved["payload"], indent=2), file=out)
        return _publish(saved["payload"], out)

    fit = choose(fits, model, window)
    if fit is None:
        if not fits:
            print("Nothing to share yet: Cigar has no recorded sessions with a model.", file=out)
        else:
            print(f"No curve for model={model} window={window}.", file=out)
        return 1
    payload = build_payload(fit, harnesses.get((fit.model, fit.window), []))
    issues = problems(payload)
    if issues:
        print("This curve can't be shared safely: " + "; ".join(issues) + ".", file=out)
        return 1
    print(PREAMBLE.format(repo=REPO), file=out)
    print(json.dumps(payload, indent=2), file=out)
    others = [f for f in fits if f is not fit]
    if others:
        names = ", ".join(f"--model {f.model} --window {f.window}" for f in others)
        print(f"Other curves you can share instead: {names}", file=out)
    if fit.confidence == "low":
        print("Note: this curve is low confidence; it's still useful in aggregate.", file=out)

    if dry_run:
        print("Dry run: nothing was opened or sent.", file=out)
        return 0
    if skill is not None:
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text(json.dumps({"ts": time.time(), "payload": payload}))
        print("To share exactly this, type: /cigar:share confirm", file=out)
        return 0
    if not yes:
        if not sys.stdin.isatty():
            print("Not shared. To share it, run: cigar share --yes", file=out)
            return 0
        answer = input("Open the prefilled GitHub issue? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Not shared.", file=out)
            return 0
    return _publish(payload, out)
