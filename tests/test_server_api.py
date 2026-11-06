"""HTTP surface added with the website mode and the new interface: file and zip
downloads (path safety), source detection, validation of the new options, and the
static interface. Runs the real server in a subprocess, like the browser tests."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psutil")
requests = pytest.importorskip("requests")

from site_fixtures import HTML, docusaurus_routes, serve  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WIKI = "https://wiki.test/api.php"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def api(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    port = _free_port()
    proc = subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=str(ROOT),
                            env={**os.environ, "DATA_DIR": str(data), "PORT": str(port),
                                 "SCRIPTS_DIR": str(ROOT / "scripts")},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            urllib.request.urlopen(base + "/api/jobs", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    yield base, data
    proc.terminate()


def _job_with_files(base: str, data: Path, files: dict) -> str:
    job = requests.post(base + "/api/jobs", json={"wiki_url": WIKI}).json()
    out = data / "output" / "wiki.test"
    out.mkdir(parents=True)
    for name, content in files.items():
        (out / name).write_bytes(content)
    return job["id"]


def test_download_serves_a_generated_file_and_refuses_path_tricks(api):
    base, data = api
    jid = _job_with_files(base, data, {"Basics.txt": b"hello"})
    (data / "secret.txt").write_text("not for download")
    ok = requests.get(f"{base}/api/jobs/{jid}/files/Basics.txt")
    assert ok.status_code == 200 and ok.content == b"hello"
    for bad in ("..%2Fsecret.txt", "nothing.txt", "%2Fetc%2Fpasswd"):
        assert requests.get(f"{base}/api/jobs/{jid}/files/{bad}").status_code == 404, bad
    assert requests.get(f"{base}/api/jobs/unknown/files/Basics.txt").status_code == 404


def test_zip_holds_every_output_file_and_404s_when_there_is_none(api):
    base, data = api
    empty = requests.post(base + "/api/jobs", json={"wiki_url": WIKI}).json()["id"]
    assert requests.get(f"{base}/api/jobs/{empty}/download.zip").status_code == 404
    jid = _job_with_files(base, data, {"A.txt": b"a", "B.md": b"b"})
    r = requests.get(f"{base}/api/jobs/{jid}/download.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    import io, zipfile
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert sorted(z.namelist()) == ["A.txt", "B.md"]
    for _ in range(40):      # removed by a background task that runs just after the response
        if not list(data.glob("*.zip")):
            break
        time.sleep(0.1)
    assert not list(data.glob("*.zip")), "the temporary zip must be removed after the download"


def test_detect_tells_a_website_from_a_mediawiki_and_survives_bad_input(api):
    base, _ = api
    wiki_page = ('<html><head><meta name="generator" content="MediaWiki 1.41"></head>'
                 "<body>" + "x" * 3_000_000 + "</body></html>")      # big body: only the head is read

    def routes(b):
        return {**docusaurus_routes(b), "/wiki": (200, HTML, wiki_page)}

    with serve(routes) as (site, _seen):
        site_kind = requests.post(base + "/api/detect", json={"url": site + "/"}).json()
        assert site_kind["kind"] == "site" and site_kind["generator"].startswith("Docusaurus")
        assert requests.post(base + "/api/detect", json={"url": site + "/wiki"}).json()["kind"] == "mediawiki"
    dead = requests.post(base + "/api/detect", json={"url": f"http://127.0.0.1:{_free_port()}/"}).json()
    assert dead["kind"] == "unknown" and "Cannot reach" in dead["error"]
    for bad in ("", "ftp://x.test/", "not a url"):
        assert requests.post(base + "/api/detect", json={"url": bad}).status_code == 400, bad


@pytest.mark.parametrize("field,value", [("source", "ftp"), ("site_max_pages", 0), ("site_max_pages", "many"),
                                          ("site_include", ["/docs/*"]), ("site_exclude", "x" * 2001)])
def test_new_options_are_validated_for_jobs_and_settings(api, field, value):
    base, _ = api
    r = requests.post(base + "/api/jobs", json={"wiki_url": WIKI, field: value})
    assert r.status_code == 400 and field in r.json()["error"]
    assert requests.put(base + "/api/settings", json={field: value}).status_code == 400
    assert requests.get(base + "/api/jobs").json() == [], "a refused job must not be created"


def test_new_options_are_accepted_and_reach_the_job(api):
    base, _ = api
    r = requests.post(base + "/api/jobs", json={"wiki_url": "https://docs.test/", "source": "site",
                                                "site_max_pages": 12, "site_include": "/docs/*"})
    assert r.status_code == 200
    params = r.json()["params"]
    assert (params["source"], params["site_max_pages"], params["site_include"]) == ("site", 12, "/docs/*")
    assert r.json()["source_kind"] == "site"


def test_interface_is_served_with_a_cache_busting_version(api):
    base, _ = api
    page = requests.get(base + "/").text
    assert "{{v}}" not in page and "/ui/app.js?v=" in page
    for asset in ("app.js", "tree.js", "util.js", "styles.css"):
        assert requests.get(f"{base}/ui/{asset}").status_code == 200, asset
    assert requests.get(base + "/ui/../server.py").status_code in (400, 404)


def test_cross_site_writes_are_refused(api):
    base, _ = api
    r = requests.post(base + "/api/jobs", json={"wiki_url": WIKI}, headers={"Origin": "https://evil.test"})
    assert r.status_code == 403
