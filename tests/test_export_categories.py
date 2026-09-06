"""Tests for scripts/export_categories.py -- per-category text/Markdown export.

Covers the "Misc" naming fix (uncategorized pages land in Misc.<ext> as the
README documents, not in the old French 'Divers' label) and the fail-fast fix
(corrupt grouping file must abort, not dump everything into one file).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("bs4")
pytest.importorskip("markdownify")

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

HTML_A = """<!DOCTYPE html><html><head><title>Pistol</title></head><body>
<h1>Pistol</h1><p>A handgun of choice.</p>
<span class="mw-editsection">[edit]</span></body></html>"""
HTML_B = """<!DOCTYPE html><html><head><title>Orphan</title></head><body>
<h1>Orphan</h1><p>No category here.</p></body></html>"""


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    html = tmp_path / "html"
    html.mkdir()
    (html / "Pistol.html").write_text(HTML_A, encoding="utf-8")
    (html / "Orphan.html").write_text(HTML_B, encoding="utf-8")
    groups = tmp_path / "category_groups.json"
    groups.write_text(json.dumps({"Weapons": ["Pistol"]}), encoding="utf-8")
    return html, groups


def _run(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / "export_categories.py"),
                           *args], capture_output=True, text=True, env=env)


def test_one_file_per_category_and_misc_for_uncategorized(tmp_path):
    html, groups = _fixture(tmp_path)
    out = tmp_path / "out"
    r = _run([str(html), str(groups), str(out), "txt,md"])
    assert r.returncode == 0, r.stdout + r.stderr
    names = sorted(f.name for f in out.iterdir())
    # README: "Uncategorized pages -> Misc.{ext}"
    assert names == ["Misc.md", "Misc.txt", "Weapons.md", "Weapons.txt"]
    assert "Pistol" in (out / "Weapons.md").read_text(encoding="utf-8")
    assert "Orphan" in (out / "Misc.txt").read_text(encoding="utf-8")
    # Noise filtering must carry over to the output (regression, unchanged)
    assert "[edit]" not in (out / "Weapons.txt").read_text(encoding="utf-8")


def test_misc_category_env_override(tmp_path):
    html, groups = _fixture(tmp_path)
    out = tmp_path / "out"
    import os
    env = {**os.environ, "MISC_CATEGORY": "Uncategorized"}
    r = _run([str(html), str(groups), str(out), "txt"], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (out / "Uncategorized.txt").exists()
    assert not (out / "Misc.txt").exists()


def test_corrupt_groups_file_fails_fast(tmp_path):
    html, groups = _fixture(tmp_path)
    groups.write_text("{not json", encoding="utf-8")
    out = tmp_path / "out"
    r = _run([str(html), str(groups), str(out), "txt"])
    assert r.returncode == 1, "corrupt grouping file must abort the export"
    assert "unreadable" in r.stderr


def test_unknown_format_rejected(tmp_path):
    html, groups = _fixture(tmp_path)
    r = _run([str(html), str(groups), str(tmp_path / "out"), "docx"])
    assert r.returncode == 1
    assert "docx" in r.stderr
