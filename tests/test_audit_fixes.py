"""Regression tests for the findings of the November 2026 audits that were
reproduced before being fixed (see CHANGELOG, "Audit follow-up").

Each test fails on the pre-fix code.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "scripts" / "run.py"
EXTRACT = ROOT / "scripts" / "extract.py"


def _env(tmp_path: Path, **over) -> dict:
    env = {
        **os.environ,
        "WIKI_API": "https://wiki.test/api.php",
        "JOB_DIR": str(tmp_path / "job"),
        "DATA_DIR": str(tmp_path / "data"),
        "EXPORT_FORMATS": "txt",
        "PHASE": "generate",
        "MAX_FILES": "0",
        "DEDUP": "false",
        "PYTHONPATH": str(ROOT / "scripts"),
    }
    env.pop("MISC_CATEGORY", None)
    env.update({k: str(v) for k, v in over.items()})
    return env


def _run(tmp_path, **over):
    return subprocess.run([sys.executable, str(RUN)], env=_env(tmp_path, **over),
                          capture_output=True, text=True)


def _page(title: str) -> str:
    return f"<html><body><h1>{title}</h1><p>Body of {title}.</p></body></html>"


def _xml(*titles: str) -> str:
    pages = "".join(
        f"<page><title>{t}</title><ns>0</ns><revision><text>Text of {t}</text></revision></page>"
        for t in titles)
    return ('<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">'
            f"{pages}</mediawiki>")


# ── PDF generation (PLAN-UX-01 / PLAN-UX-02) ──────────────────────────────────
def test_pdf_titles_with_spaces_and_accents_stay_in_their_category(tmp_path):
    """Pages were renamed to ASCII before the merge, so every multi-word or
    accented title missed its category and fell into Misc.pdf."""
    pikepdf = pytest.importorskip("pikepdf")
    job = tmp_path / "job"
    (job / "pdf").mkdir(parents=True)
    (job / "html").mkdir()
    stems = ["Assault Rifle", "Épée", "Pistol"]
    for stem in stems:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page()
        pdf.save(job / "pdf" / f"{stem}.pdf")
    (job / "category_groups.json").write_text(json.dumps({"Weapons": stems}), encoding="utf-8")

    r = _run(tmp_path, EXPORT_FORMATS="pdf")
    assert r.returncode == 0, r.stdout + r.stderr
    out = tmp_path / "data" / "output" / "wiki.test"
    assert not (out / "Misc.pdf").exists(), "categorized pages leaked into Misc"
    with pikepdf.Pdf.open(out / "Weapons.pdf") as merged:
        assert len(merged.pages) == 3


def test_generate_phase_converts_html_to_pdf(tmp_path):
    """Scan skips the conversion and Generate skipped it too: the default
    Scan -> Generate path in PDF ended with '0 output files'."""
    try:
        from weasyprint import HTML  # noqa: F401  (needs pango at import time)
    except (ImportError, OSError):
        pytest.skip("WeasyPrint/pango unavailable")
    job = tmp_path / "job"
    (job / "html").mkdir(parents=True)
    (job / "html" / "Pistol.html").write_text(_page("Pistol"), encoding="utf-8")
    (job / "category_groups.json").write_text(json.dumps({"Weapons": ["Pistol"]}), encoding="utf-8")

    r = _run(tmp_path, EXPORT_FORMATS="pdf")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "data" / "output" / "wiki.test" / "Weapons.pdf").exists()


# ── no-API mode (D01) ─────────────────────────────────────────────────────────
def test_no_api_mode_writes_one_file_per_category(tmp_path):
    """The grouping code sat after a `return 1`: the fallback produced a single
    Misc file and the job was reported as successful."""
    pytest.importorskip("bs4")
    pytest.importorskip("markdownify")
    job = tmp_path / "job"
    (job / "dump").mkdir(parents=True)
    (job / "dump" / "wiki.xml").write_text(_xml("Pistol"), encoding="utf-8")
    (job / "dump" / "config.json").write_text("{}", encoding="utf-8")   # no API
    (job / "html").mkdir()
    for t in ("Pistol", "Rifle", "Lore"):
        (job / "html" / f"{t}.html").write_text(_page(t), encoding="utf-8")
    (job / "html" / ".extraction_complete").write_text("ok", encoding="utf-8")
    (job / "categories.json").write_text(
        json.dumps({"Pistol": ["Weapons"], "Rifle": ["Weapons"], "Lore": []}), encoding="utf-8")

    r = _run(tmp_path, PHASE="all", EXPORT_FORMATS="md")
    assert r.returncode == 0, r.stdout + r.stderr
    out = tmp_path / "data" / "output" / "wiki.test"
    assert sorted(p.name for p in out.glob("*.md")) == ["Misc.md", "Weapons.md"]


# ── previous output must survive a failed run (D04 / PLAN-UX-04) ───────────────
def _seed_previous_output(tmp_path) -> Path:
    out = tmp_path / "data" / "output" / "wiki.test"
    out.mkdir(parents=True)
    (out / "Old.txt").write_text("keep me", encoding="utf-8")
    return out


@pytest.mark.parametrize("formats", ["", "docx", "pdf,bogus"])
def test_invalid_format_fails_fast_and_keeps_previous_output(tmp_path, formats):
    out = _seed_previous_output(tmp_path)
    job = tmp_path / "job"
    (job / "html").mkdir(parents=True)
    r = _run(tmp_path, EXPORT_FORMATS=formats)
    assert r.returncode != 0
    assert "invalid export format" in r.stdout
    assert (out / "Old.txt").read_text(encoding="utf-8") == "keep me"


def test_failed_generation_keeps_previous_output(tmp_path):
    out = _seed_previous_output(tmp_path)
    job = tmp_path / "job"
    (job / "html").mkdir(parents=True)
    (job / "html" / "Empty.html").write_text(_page("Empty"), encoding="utf-8")
    (job / "category_groups.json").write_text("{}", encoding="utf-8")
    (job / "selection.json").write_text(json.dumps(["NoSuchCategory"]), encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode != 0
    assert (out / "Old.txt").read_text(encoding="utf-8") == "keep me"
    assert not (out.parent / "wiki.test.partial").exists(), "staging folder leaked"


def test_successful_generation_replaces_previous_output(tmp_path):
    pytest.importorskip("bs4")
    pytest.importorskip("markdownify")
    out = _seed_previous_output(tmp_path)
    job = tmp_path / "job"
    (job / "html").mkdir(parents=True)
    (job / "html" / "Pistol.html").write_text(_page("Pistol"), encoding="utf-8")
    (job / "category_groups.json").write_text(json.dumps({"Weapons": ["Pistol"]}), encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(p.name for p in out.iterdir()) == ["Weapons.txt"]
    assert not (out.parent / "wiki.test.partial").exists()


# ── extraction resume (PLAN-UX-06 / D44) ──────────────────────────────────────
def _extraction_job(tmp_path, marker: bool):
    job = tmp_path / "job"
    (job / "dump").mkdir(parents=True)
    (job / "dump" / "wiki.xml").write_text(_xml("Alpha", "Beta"), encoding="utf-8")
    (job / "dump" / "config.json").write_text("{}", encoding="utf-8")
    (job / "html").mkdir()
    (job / "html" / "Alpha.html").write_text(_page("Alpha"), encoding="utf-8")   # interrupted run
    if marker:
        (job / "html" / ".extraction_complete").write_text("ok", encoding="utf-8")
    return job


def test_interrupted_extraction_is_resumed_not_skipped(tmp_path):
    pytest.importorskip("mwparserfromhell")
    pytest.importorskip("bs4")
    pytest.importorskip("markdownify")
    job = _extraction_job(tmp_path, marker=False)
    r = _run(tmp_path, PHASE="scan", EXPORT_FORMATS="md")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "resuming" in r.stdout
    assert (job / "html" / "Beta.html").exists(), "the missing page was never extracted"
    assert (job / "html" / ".extraction_complete").exists()


def test_complete_extraction_is_still_skipped(tmp_path):
    job = _extraction_job(tmp_path, marker=True)
    r = _run(tmp_path, PHASE="scan", EXPORT_FORMATS="md")
    assert "1 HTML files already present" in r.stdout, r.stdout + r.stderr
    assert not (job / "html" / "Beta.html").exists()


def test_title_collision_is_reported_not_silent(tmp_path):
    pytest.importorskip("mwparserfromhell")
    xml = tmp_path / "wiki.xml"
    xml.write_text(_xml("A/B", "A:B"), encoding="utf-8")
    dest = tmp_path / "html"
    r = subprocess.run([sys.executable, str(EXTRACT), str(xml), str(dest), "", "0",
                        str(tmp_path / "categories.json")],
                       env={**os.environ, "PYTHONPATH": str(ROOT / "scripts")},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "NAME COLLISION" in r.stdout
    assert len(list(dest.glob("*.html"))) == 1


# ── server: CSRF, shared output, one-shot flags, bind address ─────────────────
def _server_snippet(tmp_path: Path, body: str, **env_over) -> dict:
    pytest.importorskip("fastapi")
    pytest.importorskip("psutil")
    pytest.importorskip("httpx")
    env = {**os.environ, "DATA_DIR": str(tmp_path / "data"),
           "SCRIPTS_DIR": str(ROOT / "scripts"),
           **{k: str(v) for k, v in env_over.items()}}
    env.pop("BIND_HOST", None) if "BIND_HOST" not in env_over else None
    code = ("import json, sys; sys.path.insert(0, %r)\nimport server\n" % str(ROOT)
            + textwrap.dedent(body) + "\nprint('RESULT:' + json.dumps(result))")
    r = subprocess.run([sys.executable, "-c", code], env=env, cwd=str(ROOT),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.split("RESULT:", 1)[1])


def test_cross_site_writes_are_refused(tmp_path):
    res = _server_snippet(tmp_path, """
        from fastapi.testclient import TestClient
        c = TestClient(server.app)
        job = c.post("/api/jobs", json={"wiki_url": "https://x.test/api.php"}).json()
        body = json.dumps({"ids": [job["id"]]})
        evil = c.post("/api/jobs/bulk_delete", content=body,
                      headers={"Content-Type": "text/plain", "Origin": "https://evil.example"})
        still = len(c.get("/api/jobs").json())
        same = c.post("/api/jobs/bulk_delete", content=body,
                      headers={"Origin": "http://testserver"})
        result = {"evil": evil.status_code, "still_there": still, "same": same.status_code,
                  "left": len(c.get("/api/jobs").json())}
    """)
    assert res == {"evil": 403, "still_there": 1, "same": 200, "left": 0}


def test_requests_without_origin_still_work(tmp_path):
    res = _server_snippet(tmp_path, """
        from fastapi.testclient import TestClient
        r = TestClient(server.app).post("/api/jobs", json={"wiki_url": "https://x.test/api.php"})
        result = {"status": r.status_code}
    """)
    assert res["status"] == 200


def test_deleting_a_job_keeps_output_shared_with_another_job(tmp_path):
    res = _server_snippet(tmp_path, """
        a = server.mgr.create("https://same.test/api.php", dict(server.DEFAULTS))
        b = server.mgr.create("https://same.test/api.php", dict(server.DEFAULTS))
        out = a.merged_dir(); out.mkdir(parents=True); (out / "Final.pdf").write_text("x")
        server.mgr.delete(b.id)
        after_first = (out / "Final.pdf").exists()
        server.mgr.delete(a.id)
        result = {"after_first": after_first, "after_last": out.exists()}
    """)
    assert res == {"after_first": True, "after_last": False}


def test_clean_and_rerender_are_one_shot(tmp_path):
    res = _server_snippet(tmp_path, """
        import io
        class FakeProc:
            def __init__(self, *a, **k):
                self.stdout, self.returncode, self.pid = io.StringIO(""), 0, 1
            def wait(self): pass
        server.subprocess.Popen = FakeProc
        job = server.mgr.create("https://x.test/api.php", {**server.DEFAULTS, "clean": True, "rerender": True})
        server.mgr._run(job, "generate")
        kept_on_generate = [job.params["clean"], job.params["rerender"]]
        server.mgr._run(job, "scan")
        result = {"generate": kept_on_generate, "scan": [job.params["clean"], job.params["rerender"]]}
    """)
    assert res == {"generate": [True, True], "scan": [False, False]}


def test_server_listens_locally_unless_told_otherwise(tmp_path):
    default = _server_snippet(tmp_path, "result = server.BIND_HOST")
    docker = _server_snippet(tmp_path, "result = server.BIND_HOST", BIND_HOST="0.0.0.0")
    assert (default, docker) == ("127.0.0.1", "0.0.0.0")


def test_invalid_job_parameters_are_refused_not_persisted(tmp_path):
    res = _server_snippet(tmp_path, """
        from fastapi.testclient import TestClient
        c = TestClient(server.app)
        url = "https://x.test/api.php"
        bad = {k: c.post("/api/jobs", json={"wiki_url": url, k: v}).status_code
               for k, v in [("max_files", "abc"), ("max_files", -1), ("workers", 0),
                            ("delay", "slow"), ("dedup", "yes"), ("export_formats", "none")]}
        ok = c.post("/api/jobs", json={"wiki_url": url, "max_files": "25", "delay": 0,
                                       "export_formats": "md,txt"})
        result = {"bad": bad, "ok": ok.status_code, "max_files": ok.json()["params"]["max_files"],
                  "jobs": len(c.get("/api/jobs").json())}
    """)
    assert set(res["bad"].values()) == {400}
    assert (res["ok"], res["max_files"], res["jobs"]) == (200, 25, 1)
