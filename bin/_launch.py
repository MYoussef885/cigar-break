"""Shared launcher logic for bin/cigar, bin/cigar-hook and bin/cigar-mcp.

Claude Code runs these with whatever `python3` is on PATH, which can be older
than 3.11 (macOS ships 3.9). This file therefore uses only Python 3.8 syntax.
It re-execs the newest python3.11+ it can find, puts src/ on sys.path and runs
the entry point. The hook launcher never fails loudly (NFR-1).
"""

import glob
import json
import os
import sys
import time

MIN_VERSION = (3, 11)
CANDIDATES = ("python3.14", "python3.13", "python3.12", "python3.11")
EXTRA_DIRS = ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")
UV_GLOB = "~/.local/share/uv/python/cpython-3.1[1-4]*/bin/python3.1[1-4]"
REEXEC_FLAG = "CIGAR_REEXEC"


def _home():
    return os.path.expanduser(os.environ.get("CIGAR_HOME") or "~/.cigar")


def _find_python():
    cache = os.path.join(_home(), "python")
    try:
        with open(cache) as f:
            cached = f.read().strip()
        if cached and os.access(cached, os.X_OK):
            return cached
    except OSError:
        pass
    found = None
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    dirs = path_dirs + [os.path.expanduser(d) for d in EXTRA_DIRS]
    for name in CANDIDATES:
        for d in dirs:
            p = os.path.join(d, name)
            if d and os.access(p, os.X_OK):
                found = p
                break
        if found:
            break
    if not found:
        uv = sorted(glob.glob(os.path.expanduser(UV_GLOB)), reverse=True)
        found = uv[0] if uv else None
    if found:
        try:
            os.makedirs(_home(), exist_ok=True)
            with open(cache, "w") as f:
                f.write(found)
        except OSError:
            pass
    return found


def _stub_mcp():
    """Answer MCP with no tools, so an old Python shows one warning and no failed server."""
    for line in iter(sys.stdin.readline, ""):
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict) or "id" not in msg:
            continue
        method = msg.get("method")
        if method == "initialize":
            params = msg.get("params") or {}
            result = {
                "protocolVersion": params.get("protocolVersion") or "2025-11-25",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "cigar", "version": "inactive (needs Python 3.11+)"},
            }
        elif method == "tools/list":
            result = {"tools": []}
        elif method == "ping":
            result = {}
        else:
            reply = {"code": -32601, "message": "Method not found"}
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "error": reply}))
            sys.stdout.write("\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}) + "\n")
        sys.stdout.flush()
    sys.exit(0)


def _too_old(kind, argv):
    version = "%d.%d" % sys.version_info[:2]
    msg = (
        "Cigar is inactive: it needs Python 3.11 or newer, and python3 here is %s. "
        "Install one (for example `uv python install 3.12`) and Cigar will find it." % version
    )
    if kind == "mcp":
        _stub_mcp()
    if kind != "hook":
        sys.stderr.write(msg + "\n")
        sys.exit(1)
    if argv[:1] != ["session_start"]:
        sys.exit(0)
    marker = os.path.join(_home(), "python-warned")
    try:
        if time.time() - os.path.getmtime(marker) < 86400:
            sys.exit(0)
    except OSError:
        pass
    try:
        os.makedirs(_home(), exist_ok=True)
        open(marker, "w").close()
    except OSError:
        pass
    sys.stdout.write(json.dumps({"systemMessage": msg}) + "\n")
    sys.exit(0)


def run(kind, module, script):
    argv = sys.argv[1:]
    try:
        if sys.version_info < MIN_VERSION:
            exe = None if os.environ.get(REEXEC_FLAG) else _find_python()
            if exe:
                os.environ[REEXEC_FLAG] = "1"
                os.execv(exe, [exe, "-I", "-S", script, *argv])
            _too_old(kind, argv)
        root = os.path.dirname(os.path.dirname(os.path.abspath(script)))
        sys.path.insert(0, os.path.join(root, "src"))
        import importlib

        entry = importlib.import_module(module)
    except SystemExit:
        raise
    except BaseException:
        if kind == "hook":
            sys.exit(0)
        raise
    sys.exit(entry.main(argv))
