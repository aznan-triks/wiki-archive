"""Tests for scripts/extract.py -- API/text fallback logging.

Regression: after 5 consecutive API failures the extraction silently switched
to text mode for every remaining page -- the user only noticed degraded
output later (README troubleshooting: "PDFs nearly empty -- Text mode active").
The switch and the first failure must now be visible in the log.
"""
import runpy
import sys
from pathlib import Path

import pytest

pytest.importorskip("requests")
mwph = pytest.importorskip("mwparserfromhell")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "extract.py"

NS = "http://www.mediawiki.org/xml/export-0.11/"


def _xml(tmp_path: Path, n: int) -> Path:
    pages = "".join(
        f'<page><title>Page {i}</title><ns>0</ns><revision>'
        f'<text>== T{i} ==\nBody text {i}.</text></revision></page>'
        for i in range(n)
    )
    f = tmp_path / "wiki.xml"
    f.write_text(f'<?xml version="1.0"?><mediawiki xmlns="{NS}">{pages}</mediawiki>',
                 encoding="utf-8")
    return f


def test_dead_api_is_logged_then_text_mode(tmp_path, monkeypatch, capsys):
    import requests
    xml = _xml(tmp_path, 8)
    html = tmp_path / "html"

    def boom(self, url, params=None, **kw):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(requests.Session, "get", boom)
    monkeypatch.setattr(sys, "argv", ["extract.py", str(xml), str(html),
                                      "http://dead.test/api.php", "0",
                                      str(tmp_path / "categories.json")])
    runpy.run_path(str(SCRIPT), run_name="__main__")
    out = capsys.readouterr().out

    assert "API call failed" in out, "first API error must be logged"
    assert "switching to text mode" in out, "the fallback must be announced"
    # ...and the extraction itself still completes (documented fallback mode)
    assert len(list(html.glob("*.html"))) == 8


def test_working_api_is_used_and_resumed(tmp_path, monkeypatch, capsys):
    xml = _xml(tmp_path, 2)
    html = tmp_path / "html"
    html.mkdir()
    # One page already rendered -> resume path must be logged, API still used
    (html / "Page 0.html").write_text("<html></html>", encoding="utf-8")

    calls = []

    class Resp:
        def json(self):
            return {"parse": {
                "text": {"*": '<div class="mw-parser-output"><p>ok</p>'
                              '<span class="mw-editsection">[edit]</span></div>'},
                "categories": [{"*": "Weapons"}],
            }}

    def fake_get(self, url, params=None, **kw):
        calls.append(params["page"])
        return Resp()

    import requests
    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(sys, "argv", ["extract.py", str(xml), str(html),
                                      "http://wiki.test/api.php", "0",
                                      str(tmp_path / "categories.json")])
    runpy.run_path(str(SCRIPT), run_name="__main__")
    # Page 0 resumed + its missing categories backfilled; Page 1 rendered fresh
    assert "Page 0" in calls and "Page 1" in calls
    assert (html / "Page 1.html").exists()   # page_stem keeps spaces
    cats = tmp_path / "categories.json"
    data = __import__("json").loads(cats.read_text(encoding="utf-8"))
    assert data.get("Page 0") == ["Weapons"]  # backfilled during resume
    assert data.get("Page 1") == ["Weapons"]
