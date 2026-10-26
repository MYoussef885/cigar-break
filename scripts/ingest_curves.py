"""Maintainer script: turn accepted curve issues into data/curves/ files (FR-S4, D-015).

    python3 scripts/ingest_curves.py                  # uses `gh` (logged in)
    python3 scripts/ingest_curves.py --from-json issues.json --out /tmp/curves

It lists issues labelled `curve-accepted`, takes the JSON payload from each
body, checks it with the same allowlist `cigar share` uses, and writes
data/curves/<model>/<issue number>.json. Simulated curves and anything that
fails the check are skipped with the reason.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cigar import share  # noqa: E402

FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def payload_from_body(body: str) -> Any:
    match = FENCE_RE.search(body or "")
    if not match:
        raise ValueError("no JSON code block in the issue body")
    return json.loads(match.group(1))


def model_dir(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", model)


def ingest(issues: list[dict[str, Any]], out: Path) -> tuple[list[Path], list[str]]:
    written, skipped = [], []
    for issue in issues:
        number = issue.get("number")
        try:
            payload = payload_from_body(issue.get("body", ""))
        except ValueError as exc:
            skipped.append(f"#{number}: {exc}")
            continue
        issues_found = share.problems(payload)
        if not issues_found and payload["harness"] == "simulated":
            issues_found = ["simulated data"]
        if issues_found:
            skipped.append(f"#{number}: " + "; ".join(issues_found))
            continue
        path = out / model_dir(payload["model"]) / f"{int(number)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written, skipped


def gh_issues(repo: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "gh", "issue", "list", "--repo", repo, "--label", "curve-accepted",
            "--state", "all", "--limit", "1000", "--json", "number,title,body",
        ],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return json.loads(result.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=share.REPO)
    parser.add_argument("--from-json", type=Path, help="issues as `gh issue list --json` prints")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "curves")
    args = parser.parse_args(argv)
    issues = json.loads(args.from_json.read_text()) if args.from_json else gh_issues(args.repo)
    written, skipped = ingest(issues, args.out)
    for path in written:
        print(f"wrote {path.relative_to(args.out)}")
    for reason in skipped:
        print(f"skipped {reason}")
    print(f"{len(written)} written, {len(skipped)} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
