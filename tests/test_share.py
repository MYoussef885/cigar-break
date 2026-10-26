"""Sharing (FR-S, DR-4): the payload is an allowlist of aggregates, shown before it goes."""

from __future__ import annotations

import io
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import pytest
from helpers import ROOT, assistant, run_hook, write_jsonl

from cigar import cli, config, share, track
from cigar.store import Store

sys.path.insert(0, str(ROOT / "scripts"))
import ingest_curves
import simulate

SECRET_PROJECT = "acme-secret-billing"


@pytest.fixture
def real_looking(cigar_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Simulated history relabelled as Claude Code, plus live hook events with real paths."""
    project = tmp_path / SECRET_PROJECT
    project.mkdir()
    with Store.open(config.load().db_path) as store:
        simulate.simulate(store, "claude-sonnet-5-5", "200k", 110_000, sessions=40, seed=5)
        store.conn.execute("UPDATE sessions SET harness = 'claude-code'")
    transcript = write_jsonl(tmp_path / "t.jsonl", [assistant(60_000, "claude-sonnet-5-5")])
    for i in range(30):
        payload = {
            "session_id": f"live-session-{i % 3}",
            "cwd": str(project),
            "transcript_path": str(transcript),
            "tool_name": "Read",
            "tool_input": {"file_path": str(project / "src" / f"invoice_{i % 4}.py")},
            "tool_response": {},
        }
        run_hook("post_tool_use", payload)
    return project


def payload_now() -> dict[str, Any]:
    with Store.open(config.load().db_path) as store:
        (fit,) = track.fits(store)
        return share.build_payload(fit, track.harnesses(store)[(fit.model, fit.window)])


def test_payload_contains_no_paths_projects_or_ids(real_looking: Path, tmp_path: Path) -> None:
    payload = payload_now()
    assert share.problems(payload) == []
    assert set(payload) == share.KEYS and payload["harness"] == "claude-code"
    with Store.open(config.load().db_path) as store:
        sessions = [r[0] for r in store.conn.execute("SELECT id FROM sessions")]
        projects = [r[0] for r in store.conn.execute("SELECT DISTINCT project_hash FROM sessions")]
        paths = [r[0] for r in store.conn.execute("SELECT DISTINCT path FROM events") if r[0]]
    url, _ = share.issue_url(payload)
    for text in (json.dumps(payload), urllib.parse.unquote(url)):
        forbidden = [
            str(Path.home()),
            str(tmp_path),
            SECRET_PROJECT,
            "invoice_",
            *sessions,
            *projects,
            *paths,
        ]
        leaks = [f for f in forbidden if f in text]
        assert leaks == []
    # Only fixed labels, a version and the model ID are strings.
    strings = {k: v for k, v in payload.items() if isinstance(v, str)}
    assert set(strings) == {"cigar_version", "harness", "model", "window", "confidence"}


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"model": "/Users/me/models/llama.gguf"}, "model is not a plain model ID"),
        ({"model": "ft:gpt-4o:acme-corp:custom:abc"}, "fine-tune ID"),
        ({"model": "anthropic//x"}, "model is not a plain model ID"),
        ({"harness": "acme-internal-agent"}, "harness must be one of"),
        ({"window": "1000000"}, "window must be one of"),
        ({"project": "x"}, "keys differ"),
        ({"sessions": -1}, "sessions must be"),
        ({"buckets": [{"lo": 1, "hi": 10001, "events": 3, "weight": 1.0}]}, "malformed"),
        ({"buckets": [{"lo": 0, "hi": 10000, "events": 3, "weight": 1, "path": "/x"}]}, "exactly"),
    ],
)
def test_problems_rejects_anything_off_the_allowlist(change: dict, reason: str) -> None:
    good = {
        "schema_version": 1,
        "cigar_version": "0.1.0",
        "harness": "claude-code",
        "model": "anthropic/claude-sonnet-5-5",
        "window": "200k",
        "sessions": 3,
        "events": 120,
        "buckets": [{"lo": 30_000, "hi": 40_000, "events": 120, "weight": 9.5}],
        "knee": None,
        "confidence": "low",
        "default_knee": 100_000,
    }
    assert share.problems(good) == []
    found = share.problems(good | change)
    assert found and any(reason in p for p in found), found


def test_custom_harness_names_are_not_shared() -> None:
    assert share.harness_label(["claude-code"]) == "claude-code"
    assert share.harness_label(["acme-agent"]) == "other"
    assert share.harness_label(["claude-code", "python"]) == "other"


def test_long_payloads_drop_the_smallest_buckets() -> None:
    buckets = [
        {"lo": i * 10_000, "hi": (i + 1) * 10_000, "events": 1000 - i, "weight": 1.5}
        for i in range(200)
    ]
    payload = {"model": "m", "window": "1m", "knee": None, "confidence": "low", "buckets": buckets}
    url, sent = share.issue_url(payload)
    assert len(url) <= share.MAX_URL and 0 < len(sent["buckets"]) < 200
    kept = {b["lo"] for b in sent["buckets"]}
    assert 0 in kept and 199 * 10_000 not in kept  # the biggest buckets stay
    assert url.startswith(
        "https://github.com/MYoussef885/cigar-break/issues/new?template=curve.yml"
    )


def test_dry_run_prints_the_payload_and_opens_nothing(
    real_looking: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(share, "_open", lambda url: opened.append(url) or True)
    assert cli.main(["share", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert '"model": "claude-sonnet-5-5"' in out and "Dry run: nothing was opened" in out
    assert opened == []


def test_skill_flow_shares_exactly_what_was_shown(
    real_looking: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(share, "_open", lambda url: opened.append(url) or True)
    assert cli.main(["share", "--skill", ""]) == 0
    shown = capsys.readouterr().out
    assert "type: /cigar:share confirm" in shown and opened == []
    payload = json.loads(shown[shown.index("{") : shown.rindex("}") + 1].split("\nOther")[0])

    # More work happens between the two steps; the confirmed payload must not change.
    t = write_jsonl(real_looking.parent / "t2.jsonl", [assistant(95_000, "claude-sonnet-5-5")])
    run_hook(
        "post_tool_use",
        {"session_id": "late", "cwd": str(real_looking), "transcript_path": str(t),
         "tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": {}},
    )  # fmt: skip
    assert cli.main(["share", "--skill", "confirm"]) == 0
    (url,) = opened
    sent = json.loads(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["payload"][0])
    assert sent == payload
    assert cli.main(["share", "--skill", "confirm"]) == 1  # one confirm per showing


def test_cli_without_a_terminal_never_shares(
    real_looking: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(share, "_open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    assert cli.main(["share"]) == 0
    assert "cigar share --yes" in capsys.readouterr().out and opened == []
    assert cli.main(["share", "--yes"]) == 0 and len(opened) == 1


def test_nothing_to_share(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["share", "--dry-run"]) == 1
    assert "Nothing to share yet" in capsys.readouterr().out


def test_ingest_round_trip(real_looking: Path, tmp_path: Path) -> None:
    payload = payload_now()
    _, sent = share.issue_url(payload)
    body = f"### Payload\n\n```json\n{json.dumps(sent, indent=2)}\n```\n\n### Consent\n\n- [X] ok"
    simulated = payload | {"harness": "simulated"}
    issues = [
        {"number": 7, "title": "Curve", "body": body},
        {"number": 8, "title": "bad", "body": "no json here"},
        {"number": 9, "title": "sim", "body": f"```json\n{json.dumps(simulated)}\n```"},
        {"number": 10, "title": "leak", "body": "```json\n" + json.dumps(payload | {"path": "/x"})
         + "\n```"},
    ]  # fmt: skip
    written, skipped = ingest_curves.ingest(issues, tmp_path / "curves")
    assert [p.relative_to(tmp_path / "curves").as_posix() for p in written] == [
        "claude-sonnet-5-5/7.json"
    ]
    assert json.loads(written[0].read_text()) == sent
    assert [s.split(":")[0] for s in skipped] == ["#8", "#9", "#10"]


def test_pretty_is_the_same_json(real_looking: Path) -> None:
    payload = payload_now()
    text = share.pretty(payload)
    assert json.loads(text) == payload
    bucket_lines = [ln for ln in text.splitlines() if ln.strip().startswith('{"lo"')]
    assert len(bucket_lines) == len(payload["buckets"])
