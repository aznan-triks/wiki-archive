"""Website mode: download -> clean articles -> categories, on local demo sites
shaped like Docusaurus and MkDocs Material (no network needed)."""
import json
from pathlib import Path

import pytest

pytest.importorskip("requests")
pytest.importorskip("bs4")

import site_common as sc          # noqa: E402  (scripts/ is on sys.path, see conftest)
import site_extract               # noqa: E402
import site_fetch                 # noqa: E402
from site_fixtures import docusaurus_routes, mkdocs_routes, serve, HTML  # noqa: E402


@pytest.fixture(autouse=True)
def fast_crawler(monkeypatch):
    monkeypatch.setattr(site_fetch, "BACKOFF", 0)
    monkeypatch.setenv("DELAY", "0")
    monkeypatch.setenv("CAT_WORKERS", "4")


def crawl(tmp_path, url, **env):
    dump = tmp_path / "dump"
    code = site_fetch.main([url, str(dump)])
    return code, dump


def extract(tmp_path, dump):
    html, cats, hier = tmp_path / "html", tmp_path / "categories.json", tmp_path / "hierarchy.json"
    code = site_extract.main([str(dump), str(html), str(cats), str(hier)])
    return code, html, cats, hier


def titles_by_stem(html: Path) -> dict[str, str]:
    return {f.stem: sc.parse(f.read_text(encoding="utf-8")).h1.get_text() for f in sorted(html.glob("*.html"))}


# ── Docusaurus ───────────────────────────────────────────────────────────────
def test_docusaurus_download_scope(tmp_path):
    with serve(docusaurus_routes) as (base, seen):
        code, dump = crawl(tmp_path, f"{base}/Basics/working-on-content?game=cs2")
    assert code == 0
    index = json.loads((dump / "site.json").read_text(encoding="utf-8"))
    paths = {sc.url_path(p["final"]) for p in index["pages"].values()}
    assert len(paths) == 10 and "/Basics/hidden-doc" in paths          # sitemap-only page found
    assert not {"/fr/entity-list", "/blog/tags/news", "/files/guide.pdf"} & paths   # other language, tags, files
    assert any("dead link" in why for why in index["skipped"].values())
    assert index["generator"].startswith("Docusaurus")
    pages_seen = [s for s in seen if not s.startswith(("/robots", "/sitemap"))]
    assert pages_seen and all(s.endswith("?game=cs2") for s in pages_seen)   # the start URL's query is kept


def test_docusaurus_articles_and_categories(tmp_path):
    with serve(docusaurus_routes) as (base, _):
        _, dump = crawl(tmp_path, f"{base}/Basics/working-on-content?game=cs2")
    code, html, cats, hier = extract(tmp_path, dump)
    assert code == 0
    titles = titles_by_stem(html)
    # reading order = sidebar order, pages the sidebar does not list come last
    assert list(titles.values()) == ["Welcome", "Basics", "What is Source 2", "Working on content", "Addons",
                                     "Directory layout", "Asset Browser", "Hammer Level Editor", "Entity List",
                                     "Hidden doc"]
    by_title = {t: s for s, t in titles.items()}
    categories = json.loads(cats.read_text(encoding="utf-8"))
    cat = lambda title: categories[by_title[title]]            # noqa: E731
    assert cat("Addons") == cat("Directory layout") == cat("Working on content") == ["Working on content"]
    assert cat("What is Source 2") == cat("Basics") == cat("Hidden doc") == ["Basics"]
    assert cat("Asset Browser") == ["Editor Tools"]
    assert cat("Welcome") == cat("Entity List") == ["Source 2 Wiki"]       # loose pages -> site name
    assert json.loads(hier.read_text(encoding="utf-8"))["children"] == {"Basics": ["Working on content"]}

    page = (html / f"{by_title['Working on content']}.html").read_text(encoding="utf-8")
    text = sc.parse(page).get_text("\n")
    assert "content/\n  game/" in text or "content/\n  game/" in sc.parse(page).pre.get_text()
    assert "Copy" not in text and "Edit this page" not in text and "Direct link" not in text
    assert page.count("<h1>") == 1 and "Warning" in text and "<blockquote>" in page
    assert "On this page" not in text and "Previous" not in text and "Copyright" not in text
    tabs = (html / f"{by_title['Addons']}.html").read_text(encoding="utf-8")
    assert "Windows" in tabs and "Linux" in tabs and "shell script on Linux" in tabs   # hidden tab kept
    assert "Source: " in page and "/Basics/working-on-content" in page


def test_second_run_resumes_without_downloading(tmp_path):
    with serve(docusaurus_routes) as (base, seen):
        url = f"{base}/Basics/working-on-content"
        crawl(tmp_path, url)
        before = len(seen)
        code, _ = crawl(tmp_path, url)
        again = [s for s in seen[before:] if not s.startswith(("/robots", "/sitemap"))]
    assert code == 0 and not again       # every page was re-read from disk


def test_failed_pages_stop_the_step_then_resume(tmp_path):
    state = {"broken": True}

    def routes(base):
        r = docusaurus_routes(base)
        good = r["/entity-list"]
        r["/entity-list"] = type("Flaky", (), {"__iter__": lambda self: iter(
            (500, HTML, "boom") if state["broken"] else good)})()
        return r

    with serve(routes) as (base, _):
        code, dump = crawl(tmp_path, f"{base}/")
        assert code == 1                                  # incomplete archive = failure, not a silent hole
        assert json.loads((dump / "site.json").read_text(encoding="utf-8"))["failed"]
        state["broken"] = False
        code, _ = crawl(tmp_path, f"{base}/")
    assert code == 0


def test_include_exclude_and_page_limit(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SITE_INCLUDE", "/Basics/*")
    monkeypatch.setenv("SITE_EXCLUDE", "*/addons")
    with serve(docusaurus_routes) as (base, _):
        # the start page is always read; only the patterns decide about the others
        code, dump = crawl(tmp_path, f"{base}/Basics/what-is-source-2")
    paths = {sc.url_path(p["final"]) for p in json.loads((dump / "site.json").read_text())["pages"].values()}
    assert code == 0 and "/Basics/working-on-content/addons" not in paths and "/entity-list" not in paths
    assert "/Basics/hidden-doc" in paths

    monkeypatch.setenv("SITE_INCLUDE", "")
    monkeypatch.setenv("SITE_EXCLUDE", "")
    monkeypatch.delenv("SITE_MAX_PAGES", raising=False)
    with serve(docusaurus_routes) as (base, _):
        crawl(tmp_path / "nolimit", f"{base}/")
    assert "Page limit reached" not in capsys.readouterr().out
    monkeypatch.setenv("SITE_MAX_PAGES", "3")
    with serve(docusaurus_routes) as (base, _):
        code, dump = crawl(tmp_path / "limit", f"{base}/")
    assert "Page limit reached" in capsys.readouterr().out
    assert len({p["final"] for p in json.loads((dump / "site.json").read_text())["pages"].values()}) == 3


def test_robots_txt_is_respected(tmp_path):
    def routes(base):
        page = lambda body: (200, HTML, f"<html><body><main><p>{body} with enough words to count</p>" \
                                         '<a href="/secret">s</a><a href="/open">o</a></main></body></html>')  # noqa: E731
        return {"/": page("home"), "/open": page("open"), "/secret": page("secret"),
                "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /secret\n")}

    with serve(routes) as (base, seen):
        code, dump = crawl(tmp_path, f"{base}/")
    assert code == 0 and "/secret" not in seen
    assert "blocked by robots.txt" in json.loads((dump / "site.json").read_text())["skipped"].popitem()[1]


# ── MkDocs Material ─────────────────────────────────────────────────────────
def test_mkdocs_without_sitemap_or_breadcrumbs(tmp_path):
    with serve(mkdocs_routes) as (base, _):
        code, dump = crawl(tmp_path, f"{base}/guide/usage")        # not the home page: links lead to the rest
    assert code == 0
    code, html, cats, _ = extract(tmp_path, dump)
    assert code == 0
    titles = titles_by_stem(html)
    assert list(titles.values()) == ["Home", "Install", "Usage", "Reference"]      # menu order
    by_title = {t: s for s, t in titles.items()}
    categories = json.loads(cats.read_text(encoding="utf-8"))
    assert categories[by_title["Install"]] == categories[by_title["Usage"]] == ["User guide"]   # from the menu
    assert categories[by_title["Reference"]] == ["Demo docs"]
    install = (html / f"{by_title['Install']}.html").read_text(encoding="utf-8")
    assert "pip install demo\ndemo --help" in sc.parse(install).pre.get_text()
    assert 'data-lang="bash"' in install and "¶" not in install and "Python 3.11 is required" in install


def test_site_without_any_trail_uses_url_paths(tmp_path):
    def routes(base):
        body = ('<html><body><main><h1>{t}</h1><p>' + "words " * 12 + '</p>'
                '<a href="/a/b/c">c</a><a href="/a/d">d</a><a href="/">h</a></main></body></html>')
        return {p: (200, HTML, body.format(t=t)) for p, t in
                {"/": "Home", "/a/b/c": "Deep page", "/a/d": "Shallow page"}.items()}

    with serve(routes) as (base, _):
        _, dump = crawl(tmp_path, f"{base}/")
    _, html, cats, hier = extract(tmp_path, dump)
    categories = json.loads(cats.read_text(encoding="utf-8"))
    by_title = {t: s for s, t in titles_by_stem(html).items()}
    assert categories[by_title["Deep page"]] == ["B"] and categories[by_title["Shallow page"]] == ["A"]
    assert json.loads(hier.read_text(encoding="utf-8"))["children"] == {"A": ["B"]}


def test_javascript_only_site_is_reported(tmp_path, capsys):
    def routes(base):
        return {"/": (200, HTML, '<html><body><div id="root"></div><script src="/app.js"></script></body></html>')}

    with serve(routes) as (base, _):
        _, dump = crawl(tmp_path, f"{base}/")
    assert extract(tmp_path, dump)[0] == 1
    assert "JavaScript" in capsys.readouterr().out


# ── whole pipeline (run.py) ──────────────────────────────────────────────────
def test_pipeline_auto_detects_a_website(tmp_path):
    import subprocess, sys
    from helpers import RUN, pipeline_env

    def run(phase, **over):
        env = pipeline_env(tmp_path, WIKI_API=url, PHASE=phase, DELAY="0", CAT_WORKERS="4",
                           SITE_BACKOFF="0", **over)
        return subprocess.run([sys.executable, str(RUN)], env=env, capture_output=True, text=True)

    out = tmp_path / "data" / "output" / "127.0.0.1"
    with serve(docusaurus_routes) as (base, _):
        url = f"{base}/Basics/working-on-content?game=cs2"
        scan = run("scan", EXPORT_FORMATS="md,txt")
        assert scan.returncode == 0, scan.stdout + scan.stderr
        assert "reading it as a documentation website" in scan.stdout
        tree = json.loads((tmp_path / "job" / "category_tree.json").read_text(encoding="utf-8"))
        assert set(tree["roots"]) == {"Basics", "Editor Tools", "Source 2 Wiki"}
        assert tree["nodes"]["Basics"]["children"] == ["Working on content"]
        assert tree["nodes"]["Basics"]["total_pages"] == 6 and tree["nodes"]["Basics"]["total_words"] > 0

        (tmp_path / "job" / "selection.json").write_text('["Editor Tools"]', encoding="utf-8")
        done = run("generate", EXPORT_FORMATS="md,pdf")
        assert done.returncode == 0, done.stdout + done.stderr
    assert sorted(f.name for f in out.iterdir()) == ["Editor_Tools.md", "Editor_Tools.pdf"]

    # everything, grouped by category, pages in reading order, no duplicates when dedup is on
    (tmp_path / "job" / "selection.json").unlink()
    with serve(docusaurus_routes) as (base, _):
        url = f"{base}/Basics/working-on-content?game=cs2"
        done = run("generate", EXPORT_FORMATS="md", DEDUP="true", MAX_FILES="0")
    assert done.returncode == 0, done.stdout + done.stderr
    basics = (out / "Basics.md").read_text(encoding="utf-8")
    assert basics.index("# What is Source 2") < basics.index("# Hidden doc")
    working = (out / "Working_on_content.md").read_text(encoding="utf-8")
    assert working.index("# Working on content") < working.index("# Addons") < working.index("# Directory layout")
    assert "# Addons" not in basics                       # dedup: one page, one file
    assert "```\ncontent/\n  game/\n```" in working and working.count("# Working on content") == 1
