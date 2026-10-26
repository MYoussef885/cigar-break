"""Fail-open (NFR-1): the real launcher, run the way hooks.json runs it.

Every broken input must exit 0, print nothing, and leave a log line.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import BIN, assistant, hook_python3, write_jsonl

PYTHON3 = hook_python3()


def run_hook(event: str, stdin: bytes, home: Path) -> subprocess.CompletedProcess[bytes]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CIGAR_", "CLAUDE_"))}
    env["CIGAR_HOME"] = str(home)
    return subprocess.run(
        [PYTHON3, "-I", "-S", str(BIN / "cigar-hook"), event],
        input=stdin,
        capture_output=True,
        env=env,
        timeout=30,
    )


def log_text(home: Path) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in (home / "logs").glob("*.log"))


def valid_payload(project: Path, transcript: Path | str) -> bytes:
    return json.dumps(
        {
            "session_id": "s-fail",
            "cwd": str(project),
            "transcript_path": str(transcript),
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {},
        }
    ).encode()


@pytest.mark.parametrize(
    "stdin",
    [b"", b"\x00\xffnot json{{", b"[1, 2, 3]", b'{"no_session": true}', b"{" * 10_000],
    ids=["empty", "binary-garbage", "not-an-object", "no-session-id", "deep-nesting"],
)
@pytest.mark.parametrize("event", ["post_tool_use", "session_start", "stop", "pre_compact"])
def test_garbage_stdin(event: str, stdin: bytes, cigar_home: Path) -> None:
    result = run_hook(event, stdin, cigar_home)
    assert (result.returncode, result.stdout) == (0, b"")
    assert f"ERROR hook {event}" in log_text(cigar_home)


def test_unknown_event(cigar_home: Path) -> None:
    result = run_hook("not_an_event", b"{}", cigar_home)
    assert (result.returncode, result.stdout) == (0, b"")
    assert "unknown hook event" in log_text(cigar_home)


@pytest.mark.parametrize("event", ["post_tool_use", "session_start", "session_end"])
def test_corrupt_database(event: str, cigar_home: Path, project: Path, tmp_path: Path) -> None:
    cigar_home.mkdir(parents=True)
    (cigar_home / "cigar.db").write_bytes(b"definitely not sqlite " * 500)
    transcript = write_jsonl(tmp_path / "t.jsonl", [assistant(150_000)])
    payload = json.loads(valid_payload(project, transcript)) | {"source": "clear"}
    result = run_hook(event, json.dumps(payload).encode(), cigar_home)
    assert (result.returncode, result.stdout) == (0, b"")
    assert "DatabaseError" in log_text(cigar_home)


@pytest.mark.parametrize("kind", ["binary", "directory", "unreadable", "missing", "huge-line"])
def test_bad_transcript(kind: str, cigar_home: Path, project: Path, tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    if kind == "binary":
        path.write_bytes(os.urandom(200_000))
    elif kind == "directory":
        path.mkdir()
    elif kind == "unreadable":
        write_jsonl(path, [assistant(150_000)])
        path.chmod(0)
    elif kind == "huge-line":
        path.write_text('{"type": "assistant", "usage": ' + "9" * 3_000_000)
    result = run_hook("post_tool_use", valid_payload(project, path), cigar_home)
    assert (result.returncode, result.stdout) == (0, b"")
    assert "transcript: no usage in tail" in log_text(cigar_home)


def test_never_exits_2_or_writes_stderr_noise(cigar_home: Path) -> None:
    result = run_hook("post_tool_use", b"\xff" * 100, cigar_home)
    assert result.returncode == 0
    assert result.stderr == b""


def load_launch():
    sys.path.insert(0, str(BIN))
    try:
        import _launch

        return _launch
    finally:
        sys.path.remove(str(BIN))


def test_too_old_python_warns_once_on_session_start(
    cigar_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch = load_launch()
    monkeypatch.setattr(sys, "version_info", (3, 9, 6, "final", 0))
    monkeypatch.setattr(launch, "_find_python", lambda: None)
    for argv, expected in (
        (["session_start"], "Cigar is inactive"),
        (["session_start"], ""),  # once a day
        (["post_tool_use"], ""),
    ):
        monkeypatch.setattr(sys, "argv", ["cigar-hook", *argv])
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        with pytest.raises(SystemExit) as exit_info:
            launch.run("hook", "cigar.hook", str(BIN / "cigar-hook"))
        assert exit_info.value.code == 0
        if expected:
            assert json.loads(out.getvalue())["systemMessage"].startswith(expected)
        else:
            assert out.getvalue() == ""


def test_launcher_runs_under_the_python3_on_path(cigar_home: Path, project: Path) -> None:
    """On this machine python3 may be 3.9; the launcher must re-exec a 3.11+."""
    payload = {"session_id": "s-launch", "source": "startup", "cwd": str(project)}
    result = run_hook("session_start", json.dumps(payload).encode(), cigar_home)
    assert (result.returncode, result.stdout) == (0, b"")
    assert "hook session_start ok" in log_text(cigar_home)


def test_too_old_python_mcp_answers_with_no_tools(
    cigar_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch = load_launch()
    monkeypatch.setattr(sys, "version_info", (3, 9, 6, "final", 0))
    monkeypatch.setattr(launch, "_find_python", lambda: None)
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "x"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "status"}},
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(json.dumps(r) + "\n" for r in requests)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "argv", ["cigar-mcp"])
    with pytest.raises(SystemExit) as exit_info:
        launch.run("mcp", "cigar.mcp_server", str(BIN / "cigar-mcp"))
    assert exit_info.value.code == 0
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3]
    assert replies[0]["result"]["protocolVersion"] == "x"
    assert replies[1]["result"] == {"tools": []}
    assert replies[2]["error"]["code"] == -32601


OLD_PYTHON = Path("/usr/bin/python3")


def _old_python() -> bool:
    if not OLD_PYTHON.exists():
        return False
    out = subprocess.run(
        [str(OLD_PYTHON), "-c", "import sys; print(sys.version_info < (3, 11))"],
        capture_output=True,
        text=True,
    )
    return out.stdout.strip() == "True"


def _newer_python_outside_home() -> bool:
    """The launcher also searches fixed folders (GitHub's macOS runners have Homebrew's)."""
    launch = load_launch()
    dirs = ["/usr/bin", "/bin", *(d for d in launch.EXTRA_DIRS if not d.startswith("~"))]
    return any(os.access(os.path.join(d, n), os.X_OK) for d in dirs for n in launch.CANDIDATES)


@pytest.mark.skipif(
    not _old_python() or _newer_python_outside_home(),
    reason="needs a machine whose only python3 outside HOME is older than 3.11",
)
def test_machine_with_only_an_old_python3(tmp_path: Path, project: Path) -> None:
    """D-026: exactly one clear SessionStart warning, and no errors anywhere."""
    home = tmp_path / "home"  # hides ~/.local/bin and uv's Pythons
    home.mkdir()
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home)}

    def launch(name: str, arg: str | None, stdin: bytes) -> subprocess.CompletedProcess[bytes]:
        args = [str(OLD_PYTHON), "-I", "-S", str(BIN / name), *([arg] if arg else [])]
        return subprocess.run(args, input=stdin, capture_output=True, env=env, timeout=30)

    start = json.dumps({"session_id": "s", "source": "startup", "cwd": str(project)}).encode()
    first, second = (
        launch("cigar-hook", "session_start", start),
        launch("cigar-hook", "session_start", start),
    )
    tool = launch("cigar-hook", "post_tool_use", valid_payload(project, "/nope"))
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    mcp = launch("cigar-mcp", None, (json.dumps(init) + "\n").encode())
    for result in (first, second, tool, mcp):
        assert (result.returncode, result.stderr) == (0, b"")
    warning = json.loads(first.stdout)["systemMessage"]
    assert warning.startswith("Cigar is inactive: it needs Python 3.11 or newer")
    assert (second.stdout, tool.stdout) == (b"", b"")
    assert json.loads(mcp.stdout)["result"]["serverInfo"]["name"] == "cigar"
