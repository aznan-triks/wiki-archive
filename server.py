#!/usr/bin/env python3
"""
Wiki Archive -> NotebookLM
Persistent job manager with pause/resume.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile

import psutil
import requests
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

# -- configuration --------------------------------------------------------------
# In Docker, SCRIPTS_DIR/DATA_DIR are fixed by the mount (/scripts, /data) --
# see docker-compose.yml. In native mode, default relative to the project (double-click
# without config). Both paths remain configurable via env variable in either case.
_PROJECT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = Path(os.getenv("SCRIPTS_DIR", str(_PROJECT_DIR / "scripts")))
DATA_DIR    = Path(os.getenv("DATA_DIR", str(_PROJECT_DIR / "data")))
JOBS_DIR    = DATA_DIR / "jobs"
JOBS_FILE   = DATA_DIR / "jobs.json"
PIPELINE    = SCRIPTS_DIR / "run.py"
UI_DIR      = Path(os.getenv("UI_DIR", str(_PROJECT_DIR / "ui")))
PORT        = int(os.getenv("PORT", 8080))
# Local tool without authentication: listen on this machine only by default.
# Docker sets BIND_HOST=0.0.0.0 (container side; the host port stays on
# 127.0.0.1 unless PUBLISH_HOST is changed in docker-compose.yml).
BIND_HOST   = os.getenv("BIND_HOST", "127.0.0.1")
HOST_PROJECT_DIR = os.getenv("HOST_PROJECT_DIR", "").strip()

# Shared naming rules (same module as the pipeline scripts -- the output
# folder name must match what run.py actually writes, see wiki_names.py).
sys.path.insert(0, str(SCRIPTS_DIR))
import wiki_names  # noqa: E402  (scripts/ must be importable; if it is not,
                   # the pipeline cannot run either -- fail fast at startup)

# Grouping logic shared with generation (single source -- no gap
# between the preview and the actual result).
try:
    import pack_files
except Exception as _exc:  # preview degrades to unpacked groups -- say so loudly
    pack_files = None
    print(f"WARNING: could not import {SCRIPTS_DIR / 'pack_files.py'} ({_exc}); "
          f"the packing preview will NOT reflect MAX_FILES/dedup grouping.",
          file=sys.stderr, flush=True)

# Notebook caps come from the environment (docker-compose.yml / .env) so the
# whole pipeline honors them; the job params inherit these defaults.
DEFAULTS = {
    "namespaces":           "0",
    "delay":                0.5,
    "max_pdf":              500,
    "images":               True,
    "clean":                False,
    "rerender":             False,
    "workers":              4,
    "force":                True,
    "export_formats":       "pdf",
    "max_files":            int(os.getenv("MAX_FILES", "50")),
    "notebooklm_max_words": int(os.getenv("NOTEBOOKLM_MAX_WORDS", "500000")),
    "dedup":                True,
    "cat_workers":          8,
    "output_per_job":       False,   # True: data/output/<wiki>--<job> instead of one folder per wiki
    "unique_names":         False,   # True: titles with special characters get a hash (no collisions)
    "source":               "auto",  # auto | mediawiki | site (documentation website)
    "site_max_pages":       5000,    # website mode: stop discovering after this many pages
    "site_include":         "",      # website mode: only URL paths matching these patterns (e.g. /docs/*)
    "site_exclude":         "",      # website mode: skip URL paths matching these patterns
}
SOURCES = {
    "auto":      "Detect automatically",
    "mediawiki": "MediaWiki wiki",
    "site":      "Documentation website",
}

# NotebookLM presets: sources (= files) per notebook. The word limit
# per source (500,000) is the same across all plans.
NOTEBOOKLM_PLANS = {
    "free":  {"label": "Free",             "sources": 50},
    "plus":  {"label": "Plus",             "sources": 100},
    "pro":   {"label": "Pro (Google AI Pro)", "sources": 300},
    "ultra": {"label": "Ultra",            "sources": 600},
}

SETTINGS_FILE = DATA_DIR / "settings.json"


def load_settings() -> dict:
    """Default settings (used to pre-fill new jobs)."""
    base = {**DEFAULTS, "notebooklm_plan": "plus"}
    if SETTINGS_FILE.exists():
        try:
            base.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except Exception as exc:
            # Do not swallow silently: without a warning the user's saved
            # settings vanish on every restart with no explanation.
            print(f"WARNING: {SETTINGS_FILE} is unreadable ({exc}); "
                  f"using built-in defaults.", file=sys.stderr, flush=True)
    return base


def save_settings(data: dict) -> dict:
    cur = load_settings()
    allowed = set(DEFAULTS) | {"notebooklm_plan"}
    for k, v in data.items():
        if k in allowed:
            cur[k] = v
    SETTINGS_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return cur

STEPS = [
    {"id": "dump",       "label": "Dump",        "marker": "[1/5]"},
    {"id": "extract",    "label": "Extraction",  "marker": "[2/5]"},
    {"id": "convert",    "label": "Conversion",  "marker": "[3/5]"},
    {"id": "categories", "label": "Categories",  "marker": "[4/5]"},
    {"id": "package",    "label": "Files",       "marker": "[5/5]"},
]


def _human_size(n: int) -> str:
    """Human-readable size (KB / MB / GB)."""
    if n <= 0:
        return "0 KB"
    for unit, div in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= div:
            val = n / div
            return f"{val:.1f} {unit}" if val < 100 else f"{val:.0f} {unit}"
    return "1 KB"


def _host_path(rel: str) -> str:
    if not HOST_PROJECT_DIR:
        return rel
    if "\\" in HOST_PROJECT_DIR or re.match(r"^[A-Za-z]:", HOST_PROJECT_DIR):
        base = HOST_PROJECT_DIR.rstrip("\\/")
        return base + "\\" + rel.replace("/", "\\")
    return HOST_PROJECT_DIR.rstrip("/") + "/" + rel


# -- model -----------------------------------------------------------------------
@dataclass
class Job:
    id:         str
    wiki_url:   str
    params:     dict
    status:     str          # pending|running|paused|stopped|scanned|done|error
    created_at: str
    logs:       list[str] = field(default_factory=list, repr=False)
    _proc:      Optional[subprocess.Popen] = field(default=None, repr=False)

    def job_dir(self)            -> Path: return JOBS_DIR / self.id
    def log_file(self)           -> Path: return JOBS_DIR / f"{self.id}.log"
    def category_tree_file(self) -> Path: return self.job_dir() / "category_tree.json"
    def category_groups_file(self) -> Path: return self.job_dir() / "category_groups.json"
    def page_words_file(self)    -> Path: return self.job_dir() / "page_words.json"
    def selection_file(self)     -> Path: return self.job_dir() / "selection.json"
    def html_dir(self)           -> Path: return self.job_dir() / "html"

    def selection(self) -> Optional[list[str]]:
        """Saved category selection (None = everything)."""
        f = self.selection_file()
        if not f.exists():
            return None
        try:
            sel = json.loads(f.read_text(encoding="utf-8"))
            return sel or None
        except Exception:
            return None

    def wiki_slug(self) -> str:
        # Same rule as run.py (wiki_names) -- the folder listed here must be
        # the one the pipeline actually writes to.
        try:
            return wiki_names.wiki_slug(self.wiki_url)
        except Exception:
            return self.id

    def source_kind(self) -> str:
        """What the job really downloaded (auto is resolved once the download exists)."""
        dump = self.job_dir() / "dump"
        if (dump / "site.json").exists():
            return "site"
        if dump.exists() and any(dump.glob("*.xml")):
            return "mediawiki"
        return str(self.params.get("source", DEFAULTS["source"]))

    def merged_dir(self) -> Path:
        return DATA_DIR / "output" / wiki_names.output_folder(
            self.wiki_url, self.id, bool(self.params.get("output_per_job")))

    def _has_files(self, d: Path) -> bool:
        """True if the folder exists and contains at least one file (lightweight check)."""
        try:
            return d.exists() and any(d.iterdir())
        except Exception:
            return False

    def disk_usage(self) -> dict:
        """Job disk footprint. data_bytes = regenerable, output_bytes = final files."""
        def tree_size(d: Path) -> int:
            if not d.exists():
                return 0
            total = 0
            for p in d.rglob("*"):
                try:
                    if p.is_file():
                        total += p.stat().st_size
                except OSError:
                    pass
            return total
        data_bytes   = tree_size(self.job_dir())
        output_bytes = tree_size(self.merged_dir())
        total = data_bytes + output_bytes
        return {
            "data_bytes":   data_bytes,
            "output_bytes": output_bytes,
            "bytes":        total,
            "data_human":   _human_size(data_bytes),
            "output_human": _human_size(output_bytes),
            "human":        _human_size(total),
        }

    def push(self, line: str) -> None:
        self.logs.append(line)
        with open(self.log_file(), "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def slice(self, pos: int) -> list[str]:
        return self.logs[pos:]

    def meta(self) -> dict:
        return {
            "id":          self.id,
            "wiki_url":    self.wiki_url,
            "wiki_slug":   self.wiki_slug(),
            "params":      self.params,
            "status":      self.status,
            "created_at":  self.created_at,
            "log_count":   len(self.logs),
            "files":       self._files_meta(),
            "out_path":    _host_path(f"data/output/{self.merged_dir().name}"),
            "steps":       STEPS,
            "has_tree":    self.category_tree_file().exists(),
            "data_present": self._has_files(self.html_dir()),
            "has_output":   self._has_files(self.merged_dir()),
            "selection":    self.selection(),
            "source_kind":  self.source_kind(),
        }

    def _files_meta(self) -> list[dict]:
        out = self.merged_dir()
        if not out.exists():
            return []
        files = []
        for f in sorted(out.glob("*")):
            if f.is_file():
                files.append({"name": f.name,
                              "ext":  f.suffix.lstrip(".").lower(),
                              "size": _human_size(f.stat().st_size)})
        return files


# -- process control (psutil, cross-platform -- replaces killpg/SIGSTOP/SIGCONT) --
def _proc_tree(pid: int) -> list[psutil.Process]:
    """Root process + all its descendants (equivalent of a POSIX process group)."""
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return []
    try:
        return [root] + root.children(recursive=True)
    except psutil.NoSuchProcess:
        return [root]


def _suspend_tree(pid: int) -> None:
    for p in _proc_tree(pid):
        try:
            p.suspend()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def _resume_tree(pid: int) -> None:
    for p in _proc_tree(pid):
        try:
            p.resume()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def _terminate_tree(pid: int, timeout: float = 4.0) -> None:
    """Resume (in case suspended) -> terminate -> (timeout) -> kill on the whole tree."""
    procs = _proc_tree(pid)
    if not procs:
        return
    _resume_tree(pid)  # a suspended process may ignore terminate() on POSIX
    for p in procs:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, alive = psutil.wait_procs(procs, timeout=timeout)
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


# -- job manager -------------------------------------------------------------
class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    # -- persistence --
    def _save(self) -> None:
        with self._lock:
            data = [
                {"id": j.id, "wiki_url": j.wiki_url, "params": j.params,
                 "status": j.status, "created_at": j.created_at}
                for j in self._jobs.values()
            ]
            JOBS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _load(self) -> None:
        if not JOBS_FILE.exists():
            return
        for item in json.loads(JOBS_FILE.read_text()):
            job = Job(**{k: item[k] for k in ("id", "wiki_url", "params", "status", "created_at")})
            if job.status in ("running", "paused"):
                job.status = "stopped"
            if job.log_file().exists():
                job.logs = job.log_file().read_text(encoding="utf-8").splitlines()
                if job.logs and job.logs[-1] != "__END__" and job.status in ("done", "error", "stopped", "scanned"):
                    job.logs.append("__END__")
            self._jobs[job.id] = job
        self._save()

    # -- CRUD --
    def create(self, wiki_url: str, params: dict) -> Job:
        job_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        job = Job(id=job_id, wiki_url=wiki_url, params=params,
                  status="pending", created_at=datetime.now().isoformat())
        job.job_dir().mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._jobs[job_id] = job
        self._save()
        return job

    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        return job

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def delete(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.status in ("running", "paused"):
            self._kill(job)
        if job.job_dir().exists():
            shutil.rmtree(job.job_dir())
        if job.log_file().exists():
            job.log_file().unlink()
        with self._lock:
            del self._jobs[job_id]
        # The final output is shared by every job of the same wiki
        # (data/output/<slug>): remove it only with the wiki's last job, so
        # deleting a failed job cannot destroy another job's finished files.
        out = job.merged_dir()
        shared = any(j.merged_dir() == out for j in self._jobs.values())
        if out.exists() and not shared:
            shutil.rmtree(out, ignore_errors=True)
        self._save()

    def bulk_delete(self, ids: list[str]) -> int:
        """Delete multiple jobs. Returns the number actually deleted."""
        done = 0
        for jid in ids:
            try:
                self.delete(jid)
                done += 1
            except KeyError:
                pass
        return done

    def purge(self, job_id: str, scope: str) -> dict:
        """Free disk space. scope = 'pdf' | 'intermediate'. Keeps the final files."""
        job = self.get(job_id)
        if job.status in ("running", "paused"):
            return {"error": "Job is running -- stop it before freeing space."}
        before = job.disk_usage()["bytes"]
        jd = job.job_dir()
        if scope == "pdf":
            targets = [jd / "pdf"]
        elif scope == "intermediate":
            targets = [jd / "dump", jd / "html", jd / "pdf"]
        else:
            return {"error": f"Unknown scope: {scope}"}
        for t in targets:
            if t.exists():
                shutil.rmtree(t, ignore_errors=True)
        after = job.disk_usage()["bytes"]
        freed = max(before - after, 0)
        job.push(f"Freed {_human_size(freed)} ({scope}).")
        self._save()
        return {"ok": True, "freed_human": _human_size(freed),
                "data_present": job._has_files(job.html_dir())}

    # -- lifecycle --
    def start(self, job_id: str, phase: str = "all") -> None:
        job = self.get(job_id)
        if job.status == "running":
            return
        job.logs.clear()
        if job.log_file().exists():
            job.log_file().unlink()
        job.status = "running"
        self._save()
        threading.Thread(target=self._run, args=(job, phase), daemon=True).start()

    def scan(self, job_id: str) -> None:
        """Runs only steps 1-4 (download + category tree)."""
        self.start(job_id, phase="scan")

    def generate(self, job_id: str, selection: list[str] | None, formats: str | None = None) -> None:
        """Runs only step 5, with the provided category selection."""
        job = self.get(job_id)
        if job.status == "running":
            return
        # Write the selection to disk
        sel_file = job.selection_file()
        if selection is not None:
            sel_file.write_text(json.dumps(selection, ensure_ascii=False), encoding="utf-8")
        elif sel_file.exists():
            sel_file.unlink()
        if formats is not None:
            job.params = {**job.params, "export_formats": formats}
        self._save()
        self.start(job_id, phase="generate")

    def pause(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.status != "running" or not job._proc:
            return
        if not psutil.pid_exists(job._proc.pid):
            return
        _suspend_tree(job._proc.pid)
        job.status = "paused"
        job.push("Pipeline paused.")
        self._save()

    def resume(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.status == "paused" and job._proc:
            if psutil.pid_exists(job._proc.pid):
                _resume_tree(job._proc.pid)
                job.status = "running"
                job.push("Pipeline resumed.")
                self._save()
            else:
                job.status = "stopped"
                self._save()
        elif job.status in ("stopped", "error", "pending", "done", "scanned"):
            self.start(job_id)

    def stop(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.status not in ("running", "paused"):
            return
        job.status = "stopped"
        job.push("Stopping...")
        self._save()
        # Non-blocking kill -- _run()'s finally block pushes __END__ when the process dies
        threading.Thread(target=self._kill, args=(job,), daemon=True).start()

    def _kill(self, job: Job) -> None:
        proc = job._proc
        if not proc or proc.poll() is not None:
            return
        _terminate_tree(proc.pid)

    def _run(self, job: Job, phase: str = "all") -> None:
        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8":       "1",  # avoids UnicodeEncodeError on Windows console (checkmarks, warnings, etc.)
            "WIKI_API":         job.wiki_url,
            "JOB_DIR":          str(job.job_dir()),
            "NAMESPACES":       str(job.params.get("namespaces", DEFAULTS["namespaces"])),
            "DELAY":            str(job.params.get("delay",      DEFAULTS["delay"])),
            "MAX_PDF":          str(job.params.get("max_pdf",    DEFAULTS["max_pdf"])),
            "IMAGES":           "true" if job.params.get("images", DEFAULTS["images"]) else "false",
            "CLEAN":            "true" if job.params.get("clean",    DEFAULTS["clean"])    else "false",
            "RERENDER":         "true" if job.params.get("rerender", DEFAULTS["rerender"]) else "false",
            "WORKERS":          str(job.params.get("workers",   DEFAULTS["workers"])),
            "FORCE":            "true" if job.params.get("force", DEFAULTS["force"]) else "false",
            "EXPORT_FORMATS":   str(job.params.get("export_formats", DEFAULTS["export_formats"])),
            "MAX_FILES":        str(job.params.get("max_files",  DEFAULTS["max_files"])),
            "NOTEBOOKLM_MAX_WORDS": str(job.params.get("notebooklm_max_words", DEFAULTS["notebooklm_max_words"])),
            "DEDUP":            "true" if job.params.get("dedup", DEFAULTS["dedup"]) else "false",
            "CAT_WORKERS":      str(job.params.get("cat_workers", DEFAULTS["cat_workers"])),
            "OUTPUT_PER_JOB":   "true" if job.params.get("output_per_job", DEFAULTS["output_per_job"]) else "false",
            "UNIQUE_NAMES":     "true" if job.params.get("unique_names", DEFAULTS["unique_names"]) else "false",
            "SOURCE":           str(job.params.get("source", DEFAULTS["source"])),
            "SITE_MAX_PAGES":   str(job.params.get("site_max_pages", DEFAULTS["site_max_pages"])),
            "SITE_INCLUDE":     str(job.params.get("site_include", DEFAULTS["site_include"])),
            "SITE_EXCLUDE":     str(job.params.get("site_exclude", DEFAULTS["site_exclude"])),
            "PHASE":            phase,
            "SELECTION_FILE":   str(job.selection_file()),
            "DATA_DIR":         str(DATA_DIR),
        }
        # clean / rerender are one-shot: left on, every later Resume would wipe
        # the data it is meant to continue from. (Generation ignores them, so
        # they are kept for the next scan.)
        if phase != "generate" and (job.params.get("clean") or job.params.get("rerender")):
            job.params = {**job.params, "clean": False, "rerender": False}
            self._save()
        try:
            proc = subprocess.Popen(
                [sys.executable, str(PIPELINE)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=env, text=True, bufsize=1,
                encoding="utf-8", errors="replace",
            )
            job._proc = proc
            for line in iter(proc.stdout.readline, ""):
                if job.status == "stopped":
                    break
                job.push(line.rstrip())
            proc.wait()
            if job.status not in ("stopped", "paused"):
                if proc.returncode == 0:
                    job.status = "scanned" if phase == "scan" else "done"
                else:
                    job.status = "error"
        except Exception as exc:
            job.push(f"ERROR: {exc}")
            job.status = "error"
        finally:
            job._proc = None
            if job.status == "stopped":
                job.push("Stopped. Start the scan again to continue where it left off.")
            if not job.logs or job.logs[-1] != "__END__":
                job.push("__END__")
            self._save()


mgr = JobManager()


# -- grouping preview (same logic as generation) ------------------------------
def _packing_preview(job: Job, selection: Optional[list[str]], max_files: int) -> dict:
    """Computes, without writing anything, how many files the selection will produce."""
    groups_file = job.category_groups_file()
    if not groups_file.exists():
        return {"error": "Run a scan first to compute the preview."}
    try:
        groups = json.loads(groups_file.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "Unreadable category data."}

    # Tree/word counts must load or the preview says so -- degrading silently
    # to {} would show a preview that disagrees with the actual packing.
    tree = {}
    if job.category_tree_file().exists():
        try:
            tree = json.loads(job.category_tree_file().read_text(encoding="utf-8"))
        except Exception:
            return {"error": "Unreadable category tree -- re-run the scan."}
    page_words = {}
    if job.page_words_file().exists():
        try:
            page_words = json.loads(job.page_words_file().read_text(encoding="utf-8"))
        except Exception:
            return {"error": "Unreadable page word counts -- re-run the scan."}

    all_groups = groups
    groups, covers_all = (pack_files.select_groups(groups, tree, selection)
                          if pack_files is not None else (groups, True))

    max_words = int(job.params.get("notebooklm_max_words", DEFAULTS["notebooklm_max_words"]))
    dedup     = bool(job.params.get("dedup", DEFAULTS["dedup"]))
    if pack_files is not None:
        packed = pack_files.pack(groups, tree, page_words, max_files or 0,
                                 max_words, dedup=dedup)
    else:
        packed = groups   # fallback if the module can't be imported

    def words_of(stems):
        return sum(page_words.get(s, 0) for s in stems)

    # Pages without a category become one extra "Misc" file at export time
    # (after packing, not counted in max_files) -- show it in the preview too.
    all_groups_pages = {s for v in all_groups.values() for s in v}
    misc = set(page_words) - all_groups_pages if covers_all else set()
    if misc:
        packed = {**packed, wiki_names.MISC_CATEGORY: sorted(misc)}

    out_groups = [
        {"name": n, "pages": len(s), "words": words_of(s)}
        for n, s in sorted(packed.items(), key=lambda x: -len(x[1]))
    ]
    splits = sorted({n.split(" (part", 1)[0] for n in packed if "(part" in n})
    return {"file_count": len(packed), "splits": splits, "groups": out_groups}


# -- app & routes ---------------------------------------------------------------
app = FastAPI(title="Wiki Archive")

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    """CSRF guard: a page on another site must not be able to drive this app
    (create/delete jobs...) through the user's browser. Browsers always send
    `Origin` on cross-origin writes; it must match the Host being called.
    Requests without Origin (curl, scripts) are not browser-driven -- allowed."""
    if request.method in _UNSAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None:
            origin_host = urlparse(origin).netloc
            if origin_host != request.headers.get("host", ""):
                return JSONResponse({"error": "Cross-site request refused."}, status_code=403)
    return await call_next(request)


@app.get("/api/jobs")
async def list_jobs():
    return [j.meta() for j in mgr.list()]


_INT_PARAMS = {"max_pdf": 1, "workers": 1, "max_files": 0, "notebooklm_max_words": 0, "cat_workers": 1,
               "site_max_pages": 1}
_TEXT_PARAMS = ("site_include", "site_exclude")
_BOOL_PARAMS = {k for k, v in DEFAULTS.items() if isinstance(v, bool)}


def _validate_params(params: dict, keys) -> Optional[str]:
    """Returns a clear message for the first invalid value among `keys` (the
    ones the caller actually sent), else None; numbers are normalized in place.
    (A string like "abc" used to be persisted, then crashed every later call.)"""
    for key in keys:
        v = params.get(key)
        if key in _INT_PARAMS:
            minimum = _INT_PARAMS[key]
            try:
                if isinstance(v, bool):
                    raise ValueError
                n = int(float(v))
                if n != float(v):
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                return f"{key} must be a whole number >= {minimum}."
            if n < minimum:
                return f"{key} must be a whole number >= {minimum}."
            params[key] = n
        elif key == "delay":
            try:
                params[key] = float(v)
            except (TypeError, ValueError):
                return "delay must be a number >= 0."
            if params[key] < 0:
                return "delay must be a number >= 0."
        elif key in _BOOL_PARAMS:
            if not isinstance(v, bool):
                return f"{key} must be true or false."
        elif key == "source":
            if v not in SOURCES:
                return f"source must be one of: {', '.join(SOURCES)}."
        elif key in _TEXT_PARAMS:
            if not isinstance(v, str) or len(v) > 2000:
                return f"{key} must be text (2000 characters at most)."
        elif key == "export_formats":
            fmts = str(v or "")
            if fmts != "all" and (not fmts or not set(fmts.split(",")) <= {"pdf", "md", "txt"}):
                return "export_formats must be 'all' or a comma list of pdf, md, txt."
    return None


@app.post("/api/jobs")
async def create_job(req: Request):
    body    = await req.json()
    url     = (body.get("wiki_url") or "").strip()
    if not url:
        return {"error": "Missing URL"}
    # Base = global settings; the request body can override
    settings = load_settings()
    params   = {k: body.get(k, settings.get(k, DEFAULTS[k])) for k in DEFAULTS}
    problem  = _validate_params(params, set(body) & set(DEFAULTS))
    if problem:
        return JSONResponse({"error": problem}, status_code=400)
    job      = mgr.create(url, params)
    return job.meta()


@app.get("/api/settings")
async def get_settings():
    return {"settings": load_settings(), "plans": NOTEBOOKLM_PLANS, "defaults": DEFAULTS,
            "steps": STEPS, "sources": SOURCES}


@app.put("/api/settings")
async def put_settings(req: Request):
    body = await req.json()
    problem = _validate_params(body, set(body) & set(DEFAULTS))
    if problem:
        return JSONResponse({"error": problem}, status_code=400)
    return {"settings": save_settings(body)}


@app.patch("/api/jobs/{job_id}")
async def patch_job(job_id: str, req: Request):
    try:
        job  = mgr.get(job_id)
        body = await req.json()
        url = body["wiki_url"].strip() if body.get("wiki_url") else job.wiki_url
        params = job.params
        if "params" in body:
            params = {k: body["params"].get(k, v) for k, v in DEFAULTS.items()}
            problem = _validate_params(params, set(body["params"]) & set(DEFAULTS))
            if problem:
                return JSONResponse({"error": problem}, status_code=400)
        # The output folder follows the wiki and the "separate folder" choice:
        # moving it under existing files would orphan them (hidden in the UI, never deleted).
        new_folder = wiki_names.output_folder(url, job.id, bool(params.get("output_per_job")))
        if new_folder != job.merged_dir().name and job._has_files(job.merged_dir()):
            return JSONResponse({"error": "Files were already generated for this job: delete "
                                 "them (or create a new job) to change the wiki or the output folder."},
                                status_code=400)
        job.wiki_url, job.params = url, params
        mgr._save()
        return job.meta()
    except KeyError:
        raise HTTPException(404)


@app.post("/api/jobs/{job_id}/start")
async def start_job(job_id: str):
    try:
        mgr.start(job_id)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404)


@app.post("/api/jobs/{job_id}/scan")
async def scan_job(job_id: str):
    try:
        mgr.scan(job_id)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404)


@app.post("/api/jobs/{job_id}/generate")
async def generate_job(job_id: str, req: Request):
    try:
        body      = await req.json()
        selection = body.get("selection")   # None = everything, list = selected categories
        formats   = body.get("formats")
        mgr.generate(job_id, selection=selection, formats=formats)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404)


@app.post("/api/jobs/{job_id}/pause")
async def pause_job(job_id: str):
    try:
        mgr.pause(job_id)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404)


@app.post("/api/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    try:
        mgr.resume(job_id)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404)


@app.post("/api/jobs/{job_id}/stop")
async def stop_job(job_id: str):
    try:
        mgr.stop(job_id)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404)


# Note: single-job deletion is intentionally not exposed as its own route --
# the UI (and external callers) delete via POST /api/jobs/bulk_delete, which
# covers the single-id case too.

@app.get("/api/jobs/{job_id}/category_tree")
async def get_category_tree(job_id: str):
    try:
        job = mgr.get(job_id)
    except KeyError:
        raise HTTPException(404)
    tf = job.category_tree_file()
    if not tf.exists():
        return {"error": "Tree not found -- run a scan first."}
    tree = json.loads(tf.read_text(encoding="utf-8"))
    # Lighten the payload: the UI doesn't need the page list per node (large
    # wikis) -- only whether the category has pages of its own.
    for node in tree.get("nodes", {}).values():
        node["own_pages"] = len(node.pop("pages", None) or [])
    return {**tree, "own_prefix": pack_files.OWN_PREFIX if pack_files else "own:"}


@app.post("/api/jobs/{job_id}/preview_packing")
async def preview_packing(job_id: str, req: Request):
    try:
        job = mgr.get(job_id)
    except KeyError:
        raise HTTPException(404)
    body      = await req.json()
    selection = body.get("selection")
    max_files = int(body.get("max_files") or 0)
    return await asyncio.to_thread(_packing_preview, job, selection, max_files)


@app.put("/api/jobs/{job_id}/selection")
async def save_selection(job_id: str, req: Request):
    try:
        job = mgr.get(job_id)
    except KeyError:
        raise HTTPException(404)
    body = await req.json()
    selection = body.get("selection")
    sel_file = job.selection_file()
    if selection:
        sel_file.write_text(json.dumps(selection, ensure_ascii=False), encoding="utf-8")
    elif sel_file.exists():
        sel_file.unlink()
    return {"ok": True}


@app.get("/api/jobs/{job_id}/disk")
async def get_disk(job_id: str):
    try:
        job = mgr.get(job_id)
    except KeyError:
        raise HTTPException(404)
    return await asyncio.to_thread(job.disk_usage)


@app.post("/api/jobs/{job_id}/purge")
async def purge_job(job_id: str, req: Request):
    try:
        body  = await req.json()
        scope = body.get("scope", "")
        return await asyncio.to_thread(mgr.purge, job_id, scope)
    except KeyError:
        raise HTTPException(404)


@app.post("/api/jobs/bulk_delete")
async def bulk_delete_jobs(req: Request):
    body = await req.json()
    ids  = body.get("ids") or []
    n    = await asyncio.to_thread(mgr.bulk_delete, ids)
    return {"ok": True, "deleted": n}


@app.get("/api/jobs/{job_id}/logs")
async def stream_logs(job_id: str, from_pos: int = 0):
    try:
        job = mgr.get(job_id)
    except KeyError:
        raise HTTPException(404)

    async def _stream():
        pos = from_pos
        while True:
            chunk = job.slice(pos)
            for line in chunk:
                pos += 1
                yield ("data: __END__\n\n" if line == "__END__" else f"data: {line}\n\n")
                if line == "__END__":
                    return
            if not chunk:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# -- files, download, source detection --------------------------------------------
@app.get("/api/jobs/{job_id}/files/{name}")
async def download_file(job_id: str, name: str):
    try:
        out = mgr.get(job_id).merged_dir().resolve()
    except KeyError:
        raise HTTPException(404)
    f = (out / name).resolve()
    if f.parent != out or not f.is_file():   # no path tricks: only files of the output folder
        raise HTTPException(404)
    return FileResponse(f, filename=f.name)


def _zip_output(out: Path) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=DATA_DIR)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for f in sorted(out.glob("*")):
            if f.is_file():
                z.write(f, f.name)
    return tmp.name


@app.get("/api/jobs/{job_id}/download.zip")
async def download_zip(job_id: str):
    try:
        job = mgr.get(job_id)
    except KeyError:
        raise HTTPException(404)
    out = job.merged_dir()
    if not job._has_files(out):
        raise HTTPException(404)
    path = await asyncio.to_thread(_zip_output, out)
    return FileResponse(path, filename=f"{job.wiki_slug()}.zip", media_type="application/zip",
                        background=BackgroundTask(os.unlink, path))


_GENERATOR = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]*content=["\']([^"\']+)', re.I)
DETECT_TIMEOUT = float(os.getenv("DETECT_TIMEOUT", "8"))
DETECT_MAX_BYTES = int(os.getenv("DETECT_MAX_BYTES", str(512 * 1024)))   # the markers sit in the page head


def _detect(url: str) -> dict:
    """One quick request: does this address look like a MediaWiki wiki or a website?"""
    try:
        with requests.get(url, timeout=DETECT_TIMEOUT, stream=True,
                          headers={"User-Agent": "wiki-archive"}) as r:
            head = next(r.iter_content(DETECT_MAX_BYTES), b"")   # never the whole body: it may be huge
            text, status = head.decode(r.encoding or "utf-8", "replace"), r.status_code
    except requests.RequestException as exc:
        return {"kind": "unknown", "error": f"Cannot reach this address ({type(exc).__name__})."}
    m = _GENERATOR.search(text)
    generator = m.group(1) if m else ""
    low = text.lower()
    mediawiki = "mediawiki" in generator.lower() or "wgpagename" in low or "mw-content-text" in low
    return {"kind": "mediawiki" if mediawiki else "site", "generator": generator, "status": status}


@app.post("/api/detect")
async def detect_source(req: Request):
    body = await req.json()
    url = str(body.get("url") or "").strip()
    if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
        return JSONResponse({"error": "Enter a full address starting with http:// or https://."}, status_code=400)
    return await asyncio.to_thread(_detect, url)


# -- interface (static files in ui/) -----------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index():
    page = (UI_DIR / "index.html").read_text(encoding="utf-8")
    version = int(max((f.stat().st_mtime for f in UI_DIR.glob("*") if f.is_file()), default=0))
    return HTMLResponse(page.replace("{{v}}", str(version)), headers={"Cache-Control": "no-cache"})


if not (UI_DIR / "index.html").exists():   # Fail Fast: a server without its interface is useless
    raise SystemExit(f"Interface files not found in {UI_DIR} (set UI_DIR or restore the ui/ folder).")
app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=BIND_HOST, port=PORT)
