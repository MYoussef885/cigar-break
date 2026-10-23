from __future__ import annotations

from cigar import signals
from cigar.signals import Event, detect, extract


def read(path: str, **extra: object) -> Event:
    return extract("Read", {"file_path": path, **extra})


def edit(path: str, old: str, new: str) -> Event:
    return extract("Edit", {"file_path": path, "old_string": old, "new_string": new})


def test_extract_read_records_path_and_hash() -> None:
    e = read("/p/a.py")
    assert (e.kind, e.path, e.failed) == ("read", "/p/a.py", False)
    assert e.args_hash and len(e.args_hash) == 16


def test_extract_bash_failure_parses_exit_code_and_check() -> None:
    e = extract(
        "Bash",
        {"command": "uv run pytest -q", "description": "Run tests"},
        error="Exit code 3\nfailing",
        failed=True,
    )
    assert (e.kind, e.exit_code, e.is_check, e.failed) == ("shell", 3, True, True)


def test_extract_bash_success_has_exit_zero() -> None:
    e = extract("Bash", {"command": "ls"}, {"stdout": "a", "stderr": "", "interrupted": False})
    assert (e.exit_code, e.is_check, e.failed) == (0, False, False)


def test_description_does_not_change_args_hash() -> None:
    a = extract("Bash", {"command": "ls", "description": "List files"})
    b = extract("Bash", {"command": "ls", "description": "Show the directory"})
    assert a.args_hash == b.args_hash


def test_tool_error_in_response_counts_as_failure() -> None:
    e = extract("mcp__x__y", {}, {"isError": True})
    assert e.failed


def test_write_hashes_original_and_new_content() -> None:
    e = extract("Write", {"file_path": "/p/a", "content": "new"}, {"originalFile": "old"})
    assert e.edit_old_hash == signals.short_hash("old")
    assert e.edit_new_hash == signals.short_hash("new")


def test_multiedit_is_still_parsed() -> None:
    e = extract(
        "MultiEdit",
        {"file_path": "/p/a", "edits": [{"old_string": "a", "new_string": "b"}]},
    )
    assert e.kind == "edit" and e.edit_new_hash


def test_failure_signal() -> None:
    e = extract("Bash", {"command": "false"}, error="Exit code 1", failed=True)
    assert detect(e, []) == ("failure",)


def test_repeat_within_window_only() -> None:
    grep = extract("Grep", {"pattern": "x"})
    assert detect(grep, [grep]) == ("repeat",)
    filler = [extract("Bash", {"command": f"ls {i}"}) for i in range(19)]
    assert detect(grep, [grep, *filler]) == ()


def test_reread_needs_same_range_and_no_edit_since() -> None:
    first = read("/p/a.py")
    assert detect(first, [], []) == ()
    assert detect(read("/p/a.py"), [first], [first]) == ("reread",)
    # Paging through a file is not a re-read.
    page = read("/p/a.py", offset=200, limit=100)
    assert detect(page, [first], [first]) == ()
    # An edit in between resets it.
    change = edit("/p/a.py", "x", "y")
    assert detect(read("/p/a.py"), [first, change], [first, change]) == ()


def test_reread_is_not_also_counted_as_repeat() -> None:
    first = read("/p/a.py")
    assert detect(read("/p/a.py"), [first], [first]) == ("reread",)


def test_undo_detects_reversal_of_recent_edit() -> None:
    forward = edit("/p/a.py", "x = 1", "x = 2")
    back = edit("/p/a.py", "x = 2", "x = 1")
    assert detect(back, [forward]) == ("undo",)
    assert detect(back, [edit("/p/other.py", "x = 1", "x = 2")]) == ()


def test_undo_respects_lookback() -> None:
    forward = edit("/p/a.py", "x = 1", "x = 2")
    filler = [extract("Bash", {"command": f"echo {i}"}) for i in range(50)]
    assert detect(edit("/p/a.py", "x = 2", "x = 1"), [forward, *filler]) == ()


def test_check_fail_needs_check_command_and_nonzero_exit() -> None:
    check = extract("Bash", {"command": "npm run build"}, error="Exit code 2", failed=True)
    assert detect(check, []) == ("failure", "check_fail")
    plain = extract("Bash", {"command": "cat x"}, error="Exit code 1", failed=True)
    assert detect(plain, []) == ("failure",)


def test_custom_check_patterns() -> None:
    checks = signals.compile_checks([r"\bmycheck\b"])
    e = extract("Bash", {"command": "mycheck all"}, error="Exit code 1", failed=True, checks=checks)
    assert e.is_check
    assert not extract("Bash", {"command": "pytest"}, checks=checks).is_check


def test_weight() -> None:
    assert signals.weight(("failure", "check_fail")) == 1.7
