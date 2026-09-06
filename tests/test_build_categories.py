"""Tests for scripts/build_categories.py -- hierarchy scan behavior.

Regression: a category whose API call failed was logged with a warning and
then SKIPPED -- the job continued with a silently incomplete grouping, and the
generated files were missing pages while the log claimed success. Fail Fast
now aborts the scan instead.
"""
import json
import runpy
import sys
from pathlib import Path

import pytest

requests = pytest.importorskip("requests")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_categories.py"


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _members(*entries):
    return {"query": {"categorymembers": list(entries)}}


def _job(tmp_path: Path):
    cats = tmp_path / "categories.json"
    cats.write_text(json.dumps({"P1": ["Weapons"], "P2": ["Pistols"]}),
                    encoding="utf-8")
    return cats


def test_api_error_aborts_the_scan(tmp_path, monkeypatch, capsys):
    cats = _job(tmp_path)
    groups = tmp_path / "category_groups.json"

    def boom(self, url, params=None, **kw):
        raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(requests.Session, "get", boom)
    monkeypatch.setattr(sys, "argv", ["build_categories.py", "http://x/api.php",
                                      str(cats), str(groups)])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Category hierarchy scan failed" in out
    assert not groups.exists(), "must not write a half-built grouping file"


def test_hierarchy_propagation_and_tree(tmp_path, monkeypatch, capsys):
    """Weapons ⊃ Pistols: a page in Pistols must appear in Weapons too, and
    the tree (feeds server preview + packing) must be persisted."""
    cats = _job(tmp_path)
    groups = tmp_path / "category_groups.json"
    payloads = {
        "Category:Weapons": _members(
            {"ns": 0, "title": "P1"}, {"ns": 14, "title": "Category:Pistols"}),
        "Category:Pistols": _members({"ns": 0, "title": "P2"}),
    }

    def fake_get(self, url, params=None, **kw):
        return FakeResp(payloads[params["cmtitle"]])

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(sys, "argv", ["build_categories.py", "http://x/api.php",
                                      str(cats), str(groups)])
    runpy.run_path(str(SCRIPT), run_name="__main__")

    result = json.loads(groups.read_text(encoding="utf-8"))
    assert result["Weapons"] == ["P1", "P2"]     # propagated from subcategory
    assert result["Pistols"] == ["P2"]
    tree = json.loads((tmp_path / "category_tree.json").read_text(encoding="utf-8"))
    assert tree["roots"] == ["Weapons"]
    assert tree["nodes"]["Weapons"]["children"] == ["Pistols"]
