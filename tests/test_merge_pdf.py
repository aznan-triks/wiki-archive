"""Tests for scripts/merge_pdf.py -- per-category PDF merging.

Regression: category splits used to chain suffixes ("X_part1_part2.pdf")
because the loop reassigned the output path before computing the next name.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pikepdf")

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _blank_pdf(path: Path):
    import pikepdf
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    pdf.save(path)


def _flat(tmp_path: Path, names: list[str]) -> Path:
    flat = tmp_path / "flat"
    flat.mkdir()
    for n in names:
        _blank_pdf(flat / f"{n}.pdf")
    return flat


def _run(flat: Path, out: Path, max_pages: int, groups: Path | None) -> subprocess.CompletedProcess:
    args = [str(flat), str(out), str(max_pages)]
    if groups:
        args.append(str(groups))
    return subprocess.run([sys.executable, str(SCRIPTS / "merge_pdf.py"), *args],
                          capture_output=True, text=True)


def test_split_parts_have_clean_names(tmp_path):
    flat = _flat(tmp_path, ["P1", "P2", "P3", "P4", "P5"])
    groups = tmp_path / "groups.json"
    groups.write_text(json.dumps({"Weapons": ["P1", "P2", "P3", "P4", "P5"]}),
                      encoding="utf-8")
    out = tmp_path / "out"
    r = _run(flat, out, 2, groups)
    assert r.returncode == 0, r.stdout + r.stderr
    names = sorted(p.name for p in out.iterdir())
    # 5 articles / max 2 pages -> 3 parts, each with ONE suffix (never chained)
    assert names == ["Weapons_part1.pdf", "Weapons_part2.pdf", "Weapons_part3.pdf"]


def test_single_chunk_keeps_plain_category_name(tmp_path):
    flat = _flat(tmp_path, ["P1", "P2"])
    groups = tmp_path / "groups.json"
    groups.write_text(json.dumps({"Weapons": ["P1", "P2"]}), encoding="utf-8")
    out = tmp_path / "out"
    r = _run(flat, out, 500, groups)
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(p.name for p in out.iterdir()) == ["Weapons.pdf"]


def test_uncategorized_pages_go_to_misc(tmp_path):
    flat = _flat(tmp_path, ["P1", "Orphan"])
    groups = tmp_path / "groups.json"
    groups.write_text(json.dumps({"Weapons": ["P1"]}), encoding="utf-8")
    out = tmp_path / "out"
    r = _run(flat, out, 500, groups)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (out / "Misc.pdf").exists()          # README-documented name
    assert not (out / "Divers.pdf").exists()     # old French label is gone


def test_corrupt_groups_file_fails_fast(tmp_path):
    flat = _flat(tmp_path, ["P1"])
    groups = tmp_path / "groups.json"
    groups.write_text("{oops", encoding="utf-8")
    out = tmp_path / "out"
    r = _run(flat, out, 500, groups)
    assert r.returncode == 1, "corrupt grouping file must abort, not dump into Misc"
    assert "unreadable" in r.stderr
