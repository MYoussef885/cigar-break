"""The report: text and self-contained HTML, from simulated data (FR-L4)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from helpers import ROOT

from cigar import cli, config, report, track
from cigar.store import Store

sys.path.insert(0, str(ROOT / "scripts"))
import simulate


@pytest.fixture
def simulated(cigar_home: Path) -> Path:
    with Store.open(config.load().db_path) as store:
        for i, (model, window, knee, sessions) in enumerate(simulate.PROFILES):
            simulate.simulate(store, model, window, knee, sessions, seed=11 + i)
    return cigar_home


def test_text_report_marks_both_knees(simulated: Path) -> None:
    with Store.open(config.load().db_path) as store:
        fits = track.fits(store)
        text = report.render_text(fits, store.compaction_tokens(), today="2026-10-26")
    assert text.startswith("Cigar report · where my agent gets tired · 2026-10-26")
    assert "claude-sonnet-5-5 · 200k window · 120 sessions" in text
    assert "claude-opus-5-5 · 1M window · 80 sessions" in text
    assert text.count("◀ learned knee") == 2 and text.count("◀ default knee") == 2
    assert "replaces the default 100k" in text
    assert "Compactions:" in text


def test_html_report_is_self_contained(simulated: Path) -> None:
    with Store.open(config.load().db_path) as store:
        page = report.render_html(track.fits(store), store.compaction_tokens())
    assert "<title>Where my agent gets tired</title>" in page
    assert page.count('<section class="panel"') == 2
    assert not re.search(r"""(src|href)=["']?(https?:)?//""", page)  # no external assets
    assert "@import" not in page and "<link" not in page
    assert "prefers-color-scheme:dark" in page and "Table view" in page


def test_report_holds_no_paths_or_projects(simulated: Path, tmp_path: Path) -> None:
    with Store.open(config.load().db_path) as store:
        fits = track.fits(store)
        compactions = store.compaction_tokens()
    for text in (report.render_text(fits, compactions), report.render_html(fits, compactions)):
        assert str(Path.home()) not in text and str(tmp_path) not in text
        assert "simproject" not in text  # the simulated project hashes


def test_empty_report() -> None:
    assert "No data yet" in report.render_text([])
    assert "No data yet" in report.render_html([])


def test_cli_report_writes_html_and_refreshes_knees(
    simulated: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["report", "--html"]) == 0
    out = capsys.readouterr().out
    page = Path(out.strip().splitlines()[-1].removeprefix("HTML report: "))
    assert page.parent == simulated / "reports" and page.read_text().startswith("<!doctype html>")
    cfg = config.load()
    with Store.open(cfg.db_path) as store:
        assert track.knee_for(store, cfg, "claude-sonnet-5-5", "200k")[1].startswith("learned")
