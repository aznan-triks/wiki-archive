"""Integration tests for scripts/run.py -- pipeline fail-fast behavior.

Regression: a crashed text export was caught and only logged as a warning,
so the run printed "PIPELINE COMPLETE" and exited 0 -- the UI then marked the
job as done while the requested .md/.txt files did not exist.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN  = ROOT / "scripts" / "run.py"


def _env(tmp_path: Path, **over) -> dict:
    env = {
        **os.environ,
        "WIKI_API": "https://wiki.test/wiki/Main_Page",
        "JOB_DIR":  str(tmp_path / "job"),
        "DATA_DIR": str(tmp_path / "data"),
        "EXPORT_FORMATS": over.get("formats", "txt"),
        "PHASE": "generate",          # steps 1-4 are skipped (no network)
        "MAX_FILES": "0",
        "DEDUP": "false",
        "PYTHONPATH": str(ROOT / "scripts"),
    }
    env.pop("MISC_CATEGORY", None)
    for k, v in over.items():
        if k != "formats":
            env[k] = str(v)
    return env


def test_export_failure_fails_the_pipeline(tmp_path):
    """No html dir -> export_categories.py exits non-zero -> run.py must exit
    non-zero too (previously: swallowed, exit 0, 'PIPELINE COMPLETE')."""
    r = subprocess.run([sys.executable, str(RUN)], env=_env(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode != 0, "a failed export must crash the pipeline (Fail Fast)"
    assert "PIPELINE COMPLETE" not in r.stdout
    assert "FAILURE" in r.stdout


def test_generate_produces_files_and_exits_zero(tmp_path):
    pytest.importorskip("bs4")
    pytest.importorskip("markdownify")
    job = tmp_path / "job"
    html = job / "html"
    html.mkdir(parents=True)
    (html / "Pistol.html").write_text(
        "<html><body><h1>Pistol</h1><p>A handgun.</p></body></html>",
        encoding="utf-8")
    (job / "category_groups.json").write_text(
        json.dumps({"Weapons": ["Pistol"]}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(RUN)], env=_env(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PIPELINE COMPLETE" in r.stdout
    out = tmp_path / "data" / "output" / "wiki.test"
    assert (out / "Weapons.txt").exists()


def test_zero_output_files_is_a_failure(tmp_path):
    """The output folder is wiped in step 5; producing nothing afterwards
    must not be reported as a success."""
    job = tmp_path / "job"
    html = job / "html"
    html.mkdir(parents=True)
    (html / "Empty.html").write_text("<html><body></body></html>", encoding="utf-8")
    groups = job / "category_groups.json"
    # Selection active -> ADD_DIVERS disabled -> empty selection matches no
    # category -> zero files exported (user error, must be a hard failure)
    groups.write_text(json.dumps({}), encoding="utf-8")
    (job / "selection.json").write_text(json.dumps(["NoSuchCategory"]), encoding="utf-8")
    r = subprocess.run([sys.executable, str(RUN)], env=_env(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode != 0, "zero generated files must fail, not 'COMPLETE'"
    assert "0 output files" in r.stdout


def test_static_fail_fast_guards():
    """Static guard on run.py: the old catch-and-continue patterns must not
    come back (they marked failed jobs as 'done')."""
    src = (ROOT / "scripts" / "run.py").read_text(encoding="utf-8")
    assert "Text export failed (PDFs unaffected)" not in src
    assert "weights shown as 0" not in src
    # The documented default (README config table) is 500 pages, not 100
    assert 'env("MAX_PDF", "500")' in src


def test_run_sh_and_legacy_duplicates_are_gone():
    """The dead bash twins of the Python pipeline were removed (DRY): they
    were nothing run.py didn't do, and only invited drift."""
    assert not (ROOT / "run.sh").exists()
    assert not (ROOT / "scripts" / "run.sh").exists()
    assert not (ROOT / "scripts" / "run.sh.txt").exists()
    assert not (ROOT / "scripts" / "flatten.sh").exists()
    assert not (ROOT / "extract.py").exists()   # old duplicate of scripts/extract.py
