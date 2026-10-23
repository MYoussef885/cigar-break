"""Session status, shared by the MCP `status` tool and `cigar status` (FR-C1, FR-H4)."""

from __future__ import annotations

from typing import Any

from cigar import config, defaults, score
from cigar.store import Store


def collect(
    store: Store, cfg: config.Config, session_id: str | None = None, project: str | None = None
) -> dict[str, Any]:
    session = store.get_session(session_id) if session_id else store.latest_session(project)
    info: dict[str, Any] = {"mode": cfg.mode, "session": None}
    if project:
        latest = store.latest_handoff(project)
        info["latest_handoff"] = latest["path"] if latest else None
        pending = store.pending_handoff(project, defaults.HANDOFF_MAX_AGE_SECONDS)
        info["pending_handoff"] = pending["path"] if pending else None
    if not session:
        return info
    tokens = session.get("context_tokens") or 0
    model = session.get("model_last")
    knee = score.default_knee(model, tokens, cfg.knee_tokens)
    events = store.recent_events(session["id"], defaults.WINDOW_EVENTS)
    result = score.evaluate([e.signals for e in events], tokens, knee, min_tokens=cfg.min_tokens)
    info["session"] = {
        "id": session["id"],
        "model": model,
        "context_tokens": session.get("context_tokens"),
        "knee": knee,
        "knee_source": "override" if cfg.knee_tokens else "default",
        "pressure": result.pressure,
        "behavior": result.behavior,
        "fatigue": result.fatigue,
        "events": result.events,
        "signals": result.counts,
        "nudges": session.get("nudges") or 0,
        "max_nudges": cfg.max_nudges,
        "breaks": session.get("breaks") or 0,
        "started_at": session.get("started_at"),
    }
    return info


def render(info: dict[str, Any]) -> str:
    lines = []
    s = info.get("session")
    if not s:
        lines.append(f"Cigar status · no session recorded yet · mode {info['mode']}")
    else:
        lines.append(f"Cigar status · session {s['id'][:8]} · mode {info['mode']}")
        if s["context_tokens"]:
            tokens, knee = round(s["context_tokens"] / 1000), round(s["knee"] / 1000)
            model = s["model"] or "unknown model"
            lines.append(
                f"Context: {tokens}k tokens · knee ~{knee}k ({model}, {s['knee_source']}) "
                f"· pressure {s['pressure']:.2f}"
            )
        else:
            lines.append("Context: not measured yet (no tool calls in this session)")
        lines.append(
            f"Fatigue: {s['fatigue']:.2f} (behavior {s['behavior']:.2f} over {s['events']} calls)"
        )
        lines.append(score.evidence(s["signals"], s["events"]))
        lines.append(f"Nudges: {s['nudges']} of {s['max_nudges']} · breaks: {s['breaks']}")
    if "pending_handoff" in info:
        lines.append(f"Pending handoff: {info['pending_handoff'] or 'none'}")
    if info["mode"] == "auto":
        lines.append("Auto mode: after a handoff is saved, the context is cleared at turn end.")
    return "\n".join(lines)
