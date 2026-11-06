"""Browser smoke test of the interface (Playwright + Chromium; skipped when missing):
detect a site, scan it, pick categories, generate, download, in light, dark and phone width."""
import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from site_fixtures import docusaurus_routes, serve  # noqa: E402
from test_server_api import api  # noqa: E402,F401  (fixture: real server on a temp data dir)


@pytest.fixture()
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:        # no Chromium installed: not a failure of the project
            pytest.skip(f"Chromium unavailable: {exc}")
        yield b
        b.close()


def test_scan_choose_generate_download_without_errors(api, browser):
    base, _data = api
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    problems = []
    page.on("pageerror", lambda e: problems.append(str(e)))
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
    with serve(docusaurus_routes) as (site, _seen):
        page.goto(base + "/")
        page.click("#new-btn")
        page.fill("#f-url", site + "/")
        page.wait_for_selector("#f-detect:has-text('website')")
        page.click('[data-act="scan"]')
        page.wait_for_selector("#tree-body .tree-cb", timeout=60_000)
        assert page.locator("#tree-body .tree-lbl", has_text="Basics").count() == 1
        page.click('[data-act="tree-all"]')
        page.wait_for_selector("#gen-info:has-text('files from')")
        page.click('[data-act="generate"]')
        page.wait_for_selector("#files-body a[href*='/files/']", timeout=120_000)
        assert page.locator("#files-body", has_text="Basics.pdf").count() == 1
        with page.expect_download() as dl:
            page.click("#files-body a[href*='download.zip']")
        assert dl.value.suggested_filename.endswith(".zip")
        assert page.locator("#d-banner .note", has_text="ready").count() == 1
        # dark theme and phone width: no horizontal scroll, still usable
        page.click("#theme-btn")
        for width in (390, 768):
            page.set_viewport_size({"width": width, "height": 800})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), width
    assert problems == []
