"""The report (FR-L4, architecture §10): a text chart and a self-contained HTML page.

`render_text` and `render_html` are pure: knee fits and compactions in, text
out. `write_html` saves the page to ~/.cigar/reports/<date>.html. Nothing here
contains paths, project names or anything but models and counts.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import statistics
from collections.abc import Sequence
from pathlib import Path

from cigar import __version__, defaults
from cigar.knee import Bucket, Fit

TITLE = "Where my agent gets tired"
BAR_WIDTH = 30
RATE_MEANING = (
    "Signal rate = failures, repeated calls, re-reads, undone edits and failed checks per "
    "tool call, weighted as in Cigar's score."
)


def _k(tokens: float) -> str:
    return f"{round(tokens / 1000)}k"


def _range(b: Bucket) -> str:
    return f"{_k(b.lo)}–{_k(b.hi)}"  # noqa: RUF001 - an en dash for ranges


def knee_line(f: Fit) -> str:
    if f.knee is None:
        if not f.counting or f.confidence == "low":
            why = "not enough data yet"
        else:
            why = "no sustained rise above the baseline"
        return f"No learned knee ({why}); the default {_k(f.default_knee)} is in use."
    use = (
        f"replaces the default {_k(f.default_knee)}"
        if f.trusted
        else f"too early to trust; the default {_k(f.default_knee)} stays in use"
    )
    return f"Learned knee ~{_k(f.knee)} ({f.confidence} confidence; {use})."


def _compactions_for(f: Fit, compactions: Sequence[tuple[str, str, int]]) -> list[int]:
    return sorted(t for m, w, t in compactions if (m, w) == (f.model, f.window))


def window_name(window: str) -> str:
    return "1M" if window == "1m" else window


def _header(f: Fit) -> str:
    return (
        f"{f.model} · {window_name(f.window)} window · {f.sessions} sessions · "
        f"{f.events:,} tool calls"
    )


# --- text ---------------------------------------------------------------------------
def render_text(
    fits: Sequence[Fit], compactions: Sequence[tuple[str, str, int]] = (), today: str = ""
) -> str:
    today = today or dt.date.today().isoformat()
    lines = [f"Cigar report · {TITLE.lower()} · {today}"]
    if not fits:
        lines.append(
            "No data yet. Cigar learns from your own sessions as you work; a knee needs at "
            f"least {defaults.KNEE_MEDIUM[0]} sessions to be trusted."
        )
        return "\n".join(lines)
    for f in fits:
        lines += ["", _header(f), knee_line(f)]
        if f.baseline is not None:
            lines.append(f"Baseline: {f.baseline:.3f} signal weight per tool call.")
        top = max((b.rate for b in f.buckets), default=0.0) or 1.0
        width = max(len(_range(b)) for b in f.buckets)
        for b in f.buckets:
            cells = round(b.rate / top * BAR_WIDTH)
            bar = ("█" if b.counts else "░") * cells
            marks = []
            if f.knee is not None and b.lo == f.knee:
                marks.append("◀ learned knee")
            if b.lo <= f.default_knee < b.hi:
                marks.append("◀ default knee")
            row = f"  {_range(b):>{width}}  {b.rate:5.3f} {bar:<{BAR_WIDTH}} {b.events:>5}"
            lines.append((row + "  " + " ".join(marks)).rstrip())
        tokens = _compactions_for(f, compactions)
        if tokens:
            lines.append(
                f"Compactions: {len(tokens)} (median at {_k(statistics.median(tokens))}; "
                "shown, not used in the fit)."
            )
        lines.append(
            f"░ rows have fewer than {defaults.KNEE_MIN_BUCKET_EVENTS} calls or "
            f"{defaults.KNEE_MIN_BUCKET_SESSIONS} sessions and don't count. "
            "The last column is tool calls."
        )
    lines += ["", RATE_MEANING]
    return "\n".join(lines)


# --- HTML ---------------------------------------------------------------------------
CSS = """
:root{color-scheme:light;--surface:#fcfcfb;--panel:#ffffff;--border:#e4e3df;
--text-primary:#0b0b0b;--text-secondary:#52514e;--text-muted:#7a7974;--grid:#ecebe7;
--series-1:#2a78d6;--series-1-faint:#bcd6f5;--series-2:#eb6834;--accent:#0b0b0b}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
--surface:#141413;--panel:#1a1a19;--border:#2e2e2b;--text-primary:#f0efec;
--text-secondary:#c3c2b7;--text-muted:#8f8e86;--grid:#2a2a27;--series-1:#3987e5;
--series-1-faint:#26405f;--series-2:#d95926;--accent:#f0efec}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#141413;--panel:#1a1a19;
--border:#2e2e2b;--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#8f8e86;
--grid:#2a2a27;--series-1:#3987e5;--series-1-faint:#26405f;--series-2:#d95926;
--accent:#f0efec}
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--text-primary);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:1080px;margin:0 auto;padding:40px 16px 48px}
h1{font-size:32px;line-height:1.15;margin:0 0 6px;letter-spacing:-0.01em}
.lede{color:var(--text-secondary);margin:0 0 28px;max-width:720px}
.tabs>input{position:absolute;opacity:0;pointer-events:none}
.tabbar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.tabbar label{border:1px solid var(--border);border-radius:999px;padding:6px 14px;
cursor:pointer;color:var(--text-secondary);background:var(--panel);font-size:14px}
.panel{display:none;background:var(--panel);border:1px solid var(--border);
border-radius:14px;padding:24px}
.kpis{display:flex;flex-wrap:wrap;gap:12px 36px;margin:0 0 6px}
.kpi .v{font-size:28px;font-weight:650;line-height:1.1}
.kpi .l{color:var(--text-muted);font-size:13px}
.note{color:var(--text-secondary);margin:6px 0 16px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--text-secondary);font-size:13px;
margin:0 0 6px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;
vertical-align:-1px}
.chart{position:relative}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{fill:var(--text-secondary);font-size:12px}
svg .ref{font-size:12px;fill:var(--text-primary);font-weight:600}
.bar{fill:var(--series-1)} .bar.faint{fill:var(--series-1-faint)}
.hit:hover+.bar,.hit:focus+.bar{opacity:.75}
.tip{position:absolute;pointer-events:none;background:var(--panel);color:var(--text-primary);
border:1px solid var(--border);border-radius:8px;padding:6px 10px;font-size:13px;
box-shadow:0 4px 14px rgba(0,0,0,.12);white-space:nowrap;display:none}
details{margin-top:18px;color:var(--text-secondary)}
summary{cursor:pointer}
table{border-collapse:collapse;margin-top:8px;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:3px 14px 3px 0;text-align:right}
th:first-child,td:first-child{text-align:left}
footer{color:var(--text-muted);font-size:13px;margin-top:22px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
"""

TIP_JS = """
document.querySelectorAll('.chart').forEach(function(chart){
  var tip=chart.querySelector('.tip');
  chart.querySelectorAll('.hit').forEach(function(hit){
    function show(){tip.textContent=hit.getAttribute('data-tip');tip.style.display='block';
      var r=hit.getBoundingClientRect(),c=chart.getBoundingClientRect();
      var x=r.left-c.left+r.width/2-tip.offsetWidth/2;
      tip.style.left=Math.max(0,Math.min(x,c.width-tip.offsetWidth))+'px';
      tip.style.top=Math.max(0,r.top-c.top+parseFloat(hit.getAttribute('data-top'))-
        tip.offsetHeight-8)+'px';}
    hit.addEventListener('mouseenter',show);hit.addEventListener('focus',show);
    hit.addEventListener('mouseleave',function(){tip.style.display='none'});
    hit.addEventListener('blur',function(){tip.style.display='none'});
  });
});
"""


def _axis(value: float) -> tuple[float, float]:
    """(top, step) of a y-axis with at most 5 steps of a round size."""
    for step in (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1.0):
        top = step * math.ceil(value / step)
        if top / step <= 5:
            return top, step
    return value, value / 4


def _svg(f: Fit, compactions: Sequence[int]) -> str:
    width, height = 1000, 360
    left, right, top_pad, bottom = 52, 16, 28, 58
    plot_w, plot_h = width - left - right, height - top_pad - bottom
    lo = min(b.lo for b in f.buckets)
    hi = max(b.hi for b in f.buckets)
    for marker in (f.knee, f.default_knee):
        if marker is not None:
            lo, hi = min(lo, marker), max(hi, marker + defaults.KNEE_BUCKET_TOKENS)
    span = hi - lo

    def x(tokens: float) -> float:
        return left + (tokens - lo) / span * plot_w

    y_top, y_step = _axis(max(b.rate for b in f.buckets) * 1.12 or 0.1)

    def y(rate: float) -> float:
        return top_pad + plot_h - rate / y_top * plot_h

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Signal rate by context size for {html.escape(f.model)}">'
    ]
    for t in (round(y_step * i, 4) for i in range(round(y_top / y_step) + 1)):
        parts.append(
            f'<line x1="{left}" x2="{width - right}" y1="{y(t):.1f}" y2="{y(t):.1f}" '
            f'stroke="var(--grid)" stroke-width="1"/>'
            f'<text x="{left - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{t:g}</text>'
        )
    band = defaults.KNEE_BUCKET_TOKENS / span * plot_w
    bar_w = min(24.0, max(2.0, band - 2))
    label_every = max(1, round(len(range(lo, hi, defaults.KNEE_BUCKET_TOKENS)) / 12))
    for i, t in enumerate(range(lo, hi + 1, defaults.KNEE_BUCKET_TOKENS)):
        if i % label_every == 0:
            parts.append(
                f'<text x="{x(t):.1f}" y="{top_pad + plot_h + 18}" '
                f'text-anchor="middle">{_k(t)}</text>'
            )
    parts.append(
        f'<text x="{left + plot_w / 2}" y="{height - 6}" text-anchor="middle">'
        "context size (tokens)</text>"
    )
    for b in f.buckets:
        cx = x(b.lo) + band / 2
        bx, by = cx - bar_w / 2, y(b.rate)
        h = max(0.0, top_pad + plot_h - by)
        r = min(4.0, bar_w / 2, h)
        path = (
            f"M{bx:.1f},{by + h:.1f} V{by + r:.1f} Q{bx:.1f},{by:.1f} {bx + r:.1f},{by:.1f} "
            f"H{bx + bar_w - r:.1f} Q{bx + bar_w:.1f},{by:.1f} {bx + bar_w:.1f},{by + r:.1f} "
            f"V{by + h:.1f} Z"
        )
        tip = f"{_range(b)}: rate {b.rate:.3f} · {b.events} calls · {b.sessions} sessions" + (
            "" if b.counts else " · too few to count"
        )
        parts.append(
            f'<rect class="hit" x="{x(b.lo):.1f}" y="{top_pad}" width="{band:.1f}" '
            f'height="{plot_h}" fill="transparent" tabindex="0" data-top="{by - top_pad:.1f}" '
            f'data-tip="{html.escape(tip)}"><title>{html.escape(tip)}</title></rect>'
            f'<path class="bar{"" if b.counts else " faint"}" d="{path}"/>'
        )
    if f.baseline is not None:
        yb = y(f.baseline)
        parts.append(
            f'<line x1="{left}" x2="{width - right}" y1="{yb:.1f}" y2="{yb:.1f}" '
            'stroke="var(--text-secondary)" stroke-width="1.5" stroke-dasharray="2 4"/>'
            f'<text x="{width - right}" y="{yb - 6:.1f}" text-anchor="end">'
            f"baseline {f.baseline:.3f}</text>"
        )
    refs = [(f.default_knee, f"default {_k(f.default_knee)}", "6 5", "var(--text-secondary)")]
    if f.knee == f.default_knee:
        refs = [(f.knee, f"learned knee = default {_k(f.knee)}", "", "var(--accent)")]
    elif f.knee is not None:
        refs.append((f.knee, f"learned knee {_k(f.knee)}", "", "var(--accent)"))
    refs.sort(key=lambda ref: ref[0])
    for i, (tokens, label, dash, color) in enumerate(refs):
        xr = x(tokens)
        # Two lines: the left one is labelled on its left, the right one on its right.
        if len(refs) == 2:
            anchor = "end" if i == 0 else "start"
        else:
            anchor = "start" if xr < left + plot_w * 0.8 else "end"
        dx = 6 if anchor == "start" else -6
        parts.append(
            f'<line x1="{xr:.1f}" x2="{xr:.1f}" y1="{top_pad - 6}" y2="{top_pad + plot_h}" '
            f'stroke="{color}" stroke-width="2"'
            + (f' stroke-dasharray="{dash}"' if dash else "")
            + "/>"
            f'<text class="ref" x="{xr + dx:.1f}" y="{top_pad + 8 + i * 16}" '
            f'text-anchor="{anchor}">{html.escape(label)}</text>'
        )
    base_y = top_pad + plot_h
    for t in compactions:
        if lo <= t <= hi:
            cx = x(t)
            parts.append(
                f'<path d="M{cx:.1f},{base_y + 2} l-4,7 h8 z" fill="var(--series-2)" '
                'stroke="var(--panel)" stroke-width="1"/>'
            )
    parts.append(
        f'<line x1="{left}" x2="{width - right}" y1="{base_y}" y2="{base_y}" '
        'stroke="var(--text-muted)" stroke-width="1"/></svg>'
    )
    return "".join(parts)


def _panel(f: Fit, compactions: Sequence[int]) -> str:
    knee_value = _k(f.knee) if f.knee is not None else "none yet"
    kpis = [
        (knee_value, "learned knee"),
        (f.confidence, "confidence"),
        (_k(f.default_knee), "default knee"),
        (f"{f.sessions}", "sessions"),
        (f"{f.events:,}", "tool calls"),
    ]
    rows = "".join(
        f"<tr><td>{_range(b)}</td><td>{b.rate:.3f}</td><td>{b.events}</td>"
        f"<td>{b.sessions}</td><td>{'yes' if b.counts else 'no'}</td></tr>"
        for b in f.buckets
    )
    legend = (
        '<div class="legend"><span><i style="background:var(--series-1)"></i>signal rate per '
        'bucket</span><span><i style="background:var(--series-1-faint)"></i>too few calls to '
        'count</span><span><i style="background:var(--series-2)"></i>compaction</span></div>'
    )
    return (
        '<div class="kpis">'
        + "".join(
            f'<div class="kpi"><div class="v">{v}</div><div class="l">{lab}</div></div>'
            for v, lab in kpis
        )
        + f'</div><p class="note">{html.escape(knee_line(f))}</p>{legend}'
        f'<div class="chart">{_svg(f, compactions)}<div class="tip"></div></div>'
        f"<details><summary>Table view</summary><table><tr><th>tokens</th><th>rate</th>"
        f"<th>calls</th><th>sessions</th><th>counts</th></tr>{rows}</table></details>"
    )


def render_html(
    fits: Sequence[Fit], compactions: Sequence[tuple[str, str, int]] = (), today: str = ""
) -> str:
    today = today or dt.date.today().isoformat()
    radios, labels, rules = [], [], []
    for i, f in enumerate(fits):
        tab_id = f"t{i}"
        checked = " checked" if i == 0 else ""
        radios.append(f'<input type="radio" name="model" id="{tab_id}"{checked}>')
        name = f"{html.escape(f.model)} · {window_name(f.window)}"
        labels.append(f'<label for="{tab_id}">{name}</label>')
        rules.append(
            f"#{tab_id}:checked~.tabbar label[for={tab_id}]{{background:var(--text-primary);"
            f"color:var(--surface);border-color:var(--text-primary)}}"
            f"#{tab_id}:checked~#p{i}{{display:block}}"
            f"#{tab_id}:focus-visible~.tabbar label[for={tab_id}]"
            "{outline:2px solid var(--series-1);outline-offset:2px}"
        )
    body_panels = "".join(
        f'<section class="panel" id="p{i}"><h2 style="margin:0 0 14px;font-size:18px">'
        f"{html.escape(_header(f))}</h2>{_panel(f, _compactions_for(f, compactions))}</section>"
        for i, f in enumerate(fits)
    )
    if not fits:
        body = (
            '<section class="panel" style="display:block"><p>No data yet. Cigar learns from '
            "your own sessions as you work.</p></section>"
        )
    else:
        body = (
            f'<div class="tabs">{"".join(radios)}<div class="tabbar">{"".join(labels)}</div>'
            f"{body_panels}</div>"
        )
    data = json.dumps(
        [{"model": f.model, "window": f.window, "knee": f.knee} for f in fits]
    ).replace("</", "<\\/")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{TITLE}</title><style>{CSS}{''.join(rules)}</style></head><body><main>"
        f'<h1>{TITLE}</h1><p class="lede">How often my coding agent stumbles as its context '
        "fills up, from my own sessions, per model. The knee is where the rate rises clearly "
        f"above the model's own baseline. {html.escape(RATE_MEANING)}</p>{body}"
        f"<footer>Cigar {__version__} · generated {today} · local data only, nothing was sent. "
        "Share an anonymous curve with <code>cigar share</code>.</footer></main>"
        f'<script type="application/json" id="cigar-fits">{data}</script>'
        f"<script>{TIP_JS}</script></body></html>"
    )


def write_html(home: Path, page: str, today: str = "") -> Path:
    today = today or dt.date.today().isoformat()
    folder = home / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{today}.html"
    tmp = path.with_suffix(".html.tmp")
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(path)
    return path
