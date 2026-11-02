"""Category selection (PLAN-UX-03): a partially checked parent must keep its own
pages, "everything selected" must behave like "generate everything" (Misc kept),
and the live preview must count the files that are really produced."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from helpers import pipeline_env

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pack_files import OWN_PREFIX, select_groups  # noqa: E402

GROUPS = {"Weapons": ["AK", "C96", "M4", "Overview"], "Pistols": ["C96"],
          "Rifles": ["AK", "M4"], "Cities": ["Paris"]}
TREE = {"roots": ["Cities", "Weapons"], "nodes": {
    "Weapons": {"children": ["Pistols", "Rifles"], "pages": ["Overview"], "total_pages": 4},
    "Pistols": {"children": [], "pages": ["C96"], "total_pages": 1},
    "Rifles":  {"children": [], "pages": ["AK", "M4"], "total_pages": 2},
    "Cities":  {"children": [], "pages": ["Paris"], "total_pages": 1}}}


# ── select_groups (single source for run.py and the preview) ──────────────────
def test_no_selection_means_everything():
    out, covers_all = select_groups(GROUPS, TREE, None)
    assert out == GROUPS and covers_all


def test_whole_categories_are_selected_with_their_descendants():
    out, covers_all = select_groups(GROUPS, TREE, ["Weapons"])
    assert out == {"Weapons": GROUPS["Weapons"]} and not covers_all


def test_partial_parent_keeps_only_its_own_pages():
    out, covers_all = select_groups(GROUPS, TREE, [OWN_PREFIX + "Weapons", "Pistols", "Cities"])
    assert out == {"Pistols": ["C96"], "Cities": ["Paris"], "Weapons": ["Overview"]}
    assert not covers_all, "categories were left out: Misc must be dropped"


def test_own_entry_is_ignored_when_the_whole_category_is_selected():
    out, _ = select_groups(GROUPS, TREE, ["Weapons", OWN_PREFIX + "Weapons"])
    assert out["Weapons"] == GROUPS["Weapons"]


def test_selecting_every_category_covers_all():
    _, covers_all = select_groups(GROUPS, TREE, list(GROUPS))
    assert covers_all


def test_unknown_selection_selects_nothing():
    out, covers_all = select_groups(GROUPS, TREE, ["NoSuchCategory"])
    assert out == {} and not covers_all


# ── generation end to end ─────────────────────────────────────────────────────
def _make_job(data: Path, job_id="20261101-000000-test", cycle=False, tree=True) -> str:
    job = data / "jobs" / job_id
    (job / "html").mkdir(parents=True)
    pages = {"Overview": "overview text", "C96": "c96 pistol", "AK": "ak rifle",
             "M4": "m4 rifle", "Paris": "paris city", "Intro": "intro page"}
    for title, text in pages.items():
        (job / "html" / f"{title}.html").write_text(
            f"<html><body><h1>{title}</h1><p>{text}</p></body></html>", encoding="utf-8")
    (job / "html" / ".extraction_complete").write_text("ok")
    groups, tree_data = GROUPS, TREE
    if cycle:   # A -> B -> A : no root at all
        groups = {"A": ["AK", "M4"], "B": ["AK", "M4"]}
        tree_data = {"roots": [], "nodes": {
            "A": {"children": ["B"], "pages": ["AK"], "total_pages": 2},
            "B": {"children": ["A"], "pages": ["M4"], "total_pages": 2}}}
    if not tree:   # a job that was never scanned
        (data / "jobs.json").write_text(json.dumps([{
            "id": job_id, "wiki_url": "https://wiki.test/api.php", "status": "pending",
            "params": {}, "created_at": "2026-11-01T00:00:00"}]))
        return job_id
    (job / "category_groups.json").write_text(json.dumps(groups))
    (job / "category_tree.json").write_text(json.dumps(tree_data))
    (job / "page_words.json").write_text(json.dumps({t: len(v.split()) for t, v in pages.items()}))
    (data / "jobs.json").write_text(json.dumps([{
        "id": job_id, "wiki_url": "https://wiki.test/api.php", "status": "scanned",
        "params": {"export_formats": "txt", "max_files": 50, "dedup": True,
                   "notebooklm_max_words": 500000},
        "created_at": "2026-11-01T00:00:00"}]))
    return job_id


def _generate(tmp_path, selection, **over):
    pytest.importorskip("bs4"); pytest.importorskip("markdownify")
    job_id = _make_job(tmp_path / "data")
    sel = tmp_path / "data" / "jobs" / job_id / "selection.json"
    sel.write_text(json.dumps(selection))
    env = pipeline_env(tmp_path, JOB_DIR=sel.parent, MAX_FILES=50, DEDUP="true", **over)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run.py")], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return tmp_path / "data" / "output" / "wiki.test"


def test_generation_keeps_the_parents_own_pages(tmp_path):
    out = _generate(tmp_path, [OWN_PREFIX + "Weapons", "Pistols", "Cities"])
    assert sorted(p.name for p in out.iterdir()) == ["Cities.txt", "Pistols.txt", "Weapons.txt"]
    weapons = (out / "Weapons.txt").read_text(encoding="utf-8")
    assert "overview text" in weapons and "ak rifle" not in weapons


def test_selecting_everything_keeps_uncategorized_pages(tmp_path):
    out = _generate(tmp_path, list(GROUPS))
    assert "Misc.txt" in {p.name for p in out.iterdir()}


def test_partial_selection_drops_uncategorized_pages(tmp_path):
    out = _generate(tmp_path, ["Cities"])
    assert sorted(p.name for p in out.iterdir()) == ["Cities.txt"]


def test_preview_counts_the_files_that_are_really_produced(tmp_path):
    out = _generate(tmp_path, list(GROUPS))
    code = ("import json, sys; sys.path.insert(0, %r)\nimport server\n"
            "job = server.mgr.get('20261101-000000-test')\n"
            "print('RESULT:' + json.dumps(server._packing_preview(job, %r, 50)))"
            % (str(ROOT), list(GROUPS)))
    pytest.importorskip("fastapi"); pytest.importorskip("psutil")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True,
                       env={**os.environ, "DATA_DIR": str(tmp_path / "data"),
                            "SCRIPTS_DIR": str(ROOT / "scripts")})
    assert r.returncode == 0, r.stderr
    preview = json.loads(r.stdout.split("RESULT:", 1)[1])
    assert preview["file_count"] == len(list(out.iterdir()))


# ── the real UI in a browser ──────────────────────────────────────────────────
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def browser_page(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("fastapi"); pytest.importorskip("psutil")
    procs = []

    def start(cycle=False, tree=True):
        data = tmp_path / "data_ui"
        data.mkdir()
        _make_job(data, cycle=cycle, tree=tree)
        port = _free_port()
        proc = subprocess.Popen([sys.executable, str(ROOT / "server.py")],
                                env={**os.environ, "DATA_DIR": str(data), "PORT": str(port),
                                     "SCRIPTS_DIR": str(ROOT / "scripts")},
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(proc)
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs", timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        pw = sync_api.sync_playwright().start()
        procs.append(pw)
        try:
            browser = pw.chromium.launch()
        except Exception as exc:  # no browser installed
            pytest.skip(f"chromium unavailable: {exc}")
        procs.append(browser)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/")
        page.wait_for_function("typeof allJobs !== 'undefined' && !!allJobs['20261101-000000-test']")
        page.evaluate("selectJob('20261101-000000-test')")
        page.wait_for_selector("#tree-body .tree-row, #tree-body .l-dim", state="attached")
        return page, errors

    yield start
    for p in reversed(procs):
        try:
            p.terminate() if isinstance(p, subprocess.Popen) else (p.close() if hasattr(p, "close") else p.stop())
        except Exception:
            pass


def _rows(page):
    return page.evaluate("""() => [...document.querySelectorAll('#tree-body .tree-row')].map(r => {
        const cb = r.querySelector('.tree-cb');
        return r.querySelector('.tree-lbl').textContent + ':' + (cb.indeterminate ? 'partial' : cb.checked ? 'on' : 'off'); })""")


def test_ui_unchecking_a_subcategory_keeps_the_parents_pages(browser_page):
    page, errors = browser_page()
    assert sorted(_rows(page)) == ["Cities:on", "Weapons:on"]
    page.click('.tree-row:has(.tree-lbl[title="Weapons"]) .tree-lbl')        # expand
    page.wait_for_selector('.tree-lbl[title="Rifles"]')
    page.click('.tree-row:has(.tree-lbl[title="Rifles"]) .tree-cb')           # uncheck
    assert "Weapons:partial" in _rows(page)
    assert page.evaluate("selectedCats()") == [OWN_PREFIX + "Weapons", "Pistols", "Cities"]
    page.evaluate("treeSelectNone()")
    page.click('.tree-row:has(.tree-lbl[title="Pistols"]) .tree-cb')
    assert page.evaluate("selectedCats()") == ["Pistols"], "own pages must not appear unasked"
    page.evaluate("treeSelectAll()")
    assert sorted(page.evaluate("selectedCats()")) == sorted(GROUPS)
    assert errors == []


def test_ui_categories_in_a_cycle_are_still_reachable(browser_page):
    page, errors = browser_page(cycle=True)
    rows = _rows(page)
    assert rows and rows[0].startswith("A:"), f"cycle hid every category: {rows}"
    assert errors == []


def test_ui_launch_buttons_come_back_after_an_error(browser_page):
    """The launch form was only drawn when the job was opened: a job that failed
    or was stopped while on screen left the user with no button at all."""
    page, errors = browser_page(tree=False)
    page.evaluate("""() => { const j = allJobs['20261101-000000-test'];
        j.status = 'running'; renderFullDetail(j); }""")
    assert page.locator("#d-form button").count() == 0
    for status in ("error", "stopped"):
        page.evaluate("(st) => updateDetail({...allJobs['20261101-000000-test'], status: st})", status)
        assert "Scan the wiki" in page.inner_text("#d-form"), status
    page.evaluate("() => updateDetail({...allJobs['20261101-000000-test'], status: 'running'})")
    assert page.locator("#d-form button").count() == 0, "form must go away while running"
    assert errors == []


def test_ui_form_exposes_the_new_options(browser_page):
    page, errors = browser_page(tree=False)
    assert page.locator("#f-perjob").count() == 1 and page.locator("#f-unique").count() == 1
    page.check("#f-perjob")
    params = page.evaluate("collectParams()")
    assert params["output_per_job"] is True and params["unique_names"] is False
    assert errors == []


def test_ui_shows_why_the_server_refused_a_value(browser_page):
    """A refused value used to leave a dead button: no message, scan not started."""
    page, errors = browser_page(tree=False)
    page.fill("#f-maxfiles", "-5")
    page.evaluate("ensureJob('20261101-000000-test')")
    page.wait_for_selector("text=max_files")
    assert page.evaluate("fetch('/api/jobs').then(r => r.json())")[0]["params"].get("max_files") != -5
    assert errors == []
