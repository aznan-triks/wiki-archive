"""Tests for server.py -- configuration wiring and route surface.

Regression 1: NOTEBOOKLM_MAX_WORDS / MAX_FILES were read from the environment
at module level, but every job's params are seeded from DEFAULTS -- and the
job env is then rebuilt from params, so the .env value was silently discarded
by the pipeline it was meant to configure ("no hardcode" rule).
Regression 2: a corrupt settings.json was ignored with `except: pass`.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psutil")

ROOT = Path(__file__).resolve().parents[1]


def _import_server(tmp_path: Path, env_over: dict) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "DATA_DIR":    str(tmp_path / "data"),
        "SCRIPTS_DIR": str(ROOT / "scripts"),
        **{k: str(v) for k, v in env_over.items()},
    }
    code = (
        "import json, server; "
        "print('RESULT:' + json.dumps({"
        "  'defaults': server.DEFAULTS,"
        "  'notebooklm_env_attr_removed': not hasattr(server, 'NOTEBOOKLM_MAX_WORDS'),"
        "  'routes': sorted({(r.path, m) for r in server.app.routes"
        "                     for m in getattr(r, 'methods', set())}),"
        "}))"
    )
    return subprocess.run([sys.executable, "-c", code], env=env, cwd=str(ROOT),
                          capture_output=True, text=True)


def test_env_configures_job_defaults(tmp_path):
    r = _import_server(tmp_path, {"NOTEBOOKLM_MAX_WORDS": 123456, "MAX_FILES": 7})
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout.split("RESULT:", 1)[1])
    assert res["defaults"]["notebooklm_max_words"] == 123456, \
        "NOTEBOOKLM_MAX_WORDS env must flow into job defaults (and thus the pipeline)"
    assert res["defaults"]["max_files"] == 7, "MAX_FILES env must flow into job defaults"
    assert res["notebooklm_env_attr_removed"], "single source: no duplicate module constant"


def test_settings_file_corruption_is_reported(tmp_path):
    """The user's settings must not vanish with a silent `except: pass`."""
    r = _import_server(tmp_path, {})
    assert r.returncode == 0, r.stderr
    # Now corrupt the settings file and re-import: the warning must appear.
    settings = tmp_path / "data" / "settings.json"
    r2 = subprocess.run(
        [sys.executable, "-c",
         "import json, sys, server;"
         "s = server.SETTINGS_FILE; s.write_text('{broken', encoding='utf-8');"
         "d = server.load_settings();"
         "print('RESULT:' + json.dumps({'ok': d['max_files'] is not None}))"],
        env={**os.environ, "DATA_DIR": str(tmp_path / "data"),
             "SCRIPTS_DIR": str(ROOT / "scripts")},
        cwd=str(ROOT), capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert "unreadable" in r2.stderr, "corrupt settings.json must be logged, not swallowed"
    assert json.loads(r2.stdout.split("RESULT:", 1)[1])["ok"] is True


def test_no_duplicate_single_delete_route(tmp_path):
    """The dead DELETE /api/jobs/{job_id} route was removed; deletion goes
    through the one path the UI actually uses (bulk_delete)."""
    r = _import_server(tmp_path, {})
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout.split("RESULT:", 1)[1])
    routes = {tuple(x) for x in res["routes"]}
    assert ("/api/jobs/{job_id}", "DELETE") not in routes
    assert ("/api/jobs/bulk_delete", "POST") in routes
    # Every lifecycle route the UI calls still exists
    for path in ("/api/jobs", "/api/settings", "/api/jobs/{job_id}/start",
                 "/api/jobs/{job_id}/pause", "/api/jobs/{job_id}/stop",
                 "/api/jobs/{job_id}/resume", "/api/jobs/{job_id}/scan",
                 "/api/jobs/{job_id}/generate", "/api/jobs/{job_id}/logs"):
        assert any(p == path for p, _ in routes), f"route {path} disappeared"


def test_host_path_and_human_size(tmp_path):
    """_host_path / _human_size sanity (UI display helpers)."""
    r = subprocess.run(
        [sys.executable, "-c",
         "import json, server;"
         "print('RESULT:' + json.dumps({"
         "'h': server._human_size(1500),"
         "'z': server._human_size(0),"
         "'big': server._human_size(3 * 1024**3)}))"],
        env={**os.environ, "DATA_DIR": str(tmp_path / "data"),
             "SCRIPTS_DIR": str(ROOT / "scripts")},
        cwd=str(ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout.split("RESULT:", 1)[1])
    assert res["h"] == "1.5 KB" and res["z"] == "0 KB" and res["big"] == "3.0 GB"
