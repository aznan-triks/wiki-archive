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
import threading
import time
import uuid

import psutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

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
PORT        = int(os.getenv("PORT", 8080))
HOST_PROJECT_DIR = os.getenv("HOST_PROJECT_DIR", "").strip()
NOTEBOOKLM_MAX_WORDS = int(os.getenv("NOTEBOOKLM_MAX_WORDS", "500000"))

# Grouping logic shared with generation (single source -- no gap
# between the preview and the actual result).
sys.path.insert(0, str(SCRIPTS_DIR))
try:
    import pack_files
except Exception:
    pack_files = None

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
    "max_files":            50,
    "notebooklm_max_words": 500000,
    "dedup":                True,
    "cat_workers":          8,
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
        except Exception:
            pass
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
        try:
            host = urlparse(self.wiki_url).hostname or self.wiki_url
            return re.sub(r"[^\w.-]", "_", host)
        except Exception:
            return self.id

    def merged_dir(self) -> Path: return DATA_DIR / "output" / self.wiki_slug()

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
            "out_path":    _host_path(f"data/output/{self.wiki_slug()}"),
            "steps":       STEPS,
            "has_tree":    self.category_tree_file().exists(),
            "data_present": self._has_files(self.html_dir()),
            "has_output":   self._has_files(self.merged_dir()),
            "selection":    self.selection(),
        }

    def _files_meta(self) -> list[dict]:
        out = self.merged_dir()
        if not out.exists():
            return []
        files = []
        for f in sorted(out.glob("*")):
            if f.is_file():
                ko = f.stat().st_size / 1024
                size = f"{ko/1024:.1f} MB" if ko >= 1024 else f"{max(ko, 1):.0f} KB"
                files.append({"name": f.name,
                              "ext":  f.suffix.lstrip(".").lower(),
                              "size": size})
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
        # Also delete the final output (one per wiki_slug)
        out = job.merged_dir()
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        with self._lock:
            del self._jobs[job_id]
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
            targets = [jd / "pdf", jd / "flat"]
        elif scope == "intermediate":
            targets = [jd / "dump", jd / "html", jd / "pdf", jd / "flat"]
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
            "PHASE":            phase,
            "SELECTION_FILE":   str(job.selection_file()),
            "DATA_DIR":         str(DATA_DIR),
        }
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
                job.push("Stopped. You can restart it via Resume.")
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

    tree = {}
    if job.category_tree_file().exists():
        try:
            tree = json.loads(job.category_tree_file().read_text(encoding="utf-8"))
        except Exception:
            tree = {}
    page_words = {}
    if job.page_words_file().exists():
        try:
            page_words = json.loads(job.page_words_file().read_text(encoding="utf-8"))
        except Exception:
            page_words = {}

    sel = set(selection) if selection else None
    if sel is not None:
        groups = {k: v for k, v in groups.items() if k in sel}

    max_words = int(job.params.get("notebooklm_max_words", NOTEBOOKLM_MAX_WORDS))
    dedup     = bool(job.params.get("dedup", DEFAULTS["dedup"]))
    if pack_files is not None:
        packed = pack_files.pack(groups, tree, page_words, max_files or 0,
                                 max_words, dedup=dedup)
    else:
        packed = groups   # fallback if the module can't be imported

    def words_of(stems):
        return sum(page_words.get(s, 0) for s in stems)

    out_groups = [
        {"name": n, "pages": len(s), "words": words_of(s)}
        for n, s in sorted(packed.items(), key=lambda x: -len(x[1]))
    ]
    splits = sorted({n.split(" (part", 1)[0] for n in packed if "(part" in n})
    return {"file_count": len(packed), "splits": splits, "groups": out_groups}


# -- app & routes ---------------------------------------------------------------
app = FastAPI(title="Wiki Archive")


@app.get("/api/jobs")
async def list_jobs():
    return [j.meta() for j in mgr.list()]


@app.post("/api/jobs")
async def create_job(req: Request):
    body    = await req.json()
    url     = (body.get("wiki_url") or "").strip()
    if not url:
        return {"error": "Missing URL"}
    # Base = global settings; the request body can override
    settings = load_settings()
    params   = {k: body.get(k, settings.get(k, DEFAULTS[k])) for k in DEFAULTS}
    job      = mgr.create(url, params)
    return job.meta()


@app.get("/api/settings")
async def get_settings():
    return {"settings": load_settings(), "plans": NOTEBOOKLM_PLANS, "defaults": DEFAULTS}


@app.put("/api/settings")
async def put_settings(req: Request):
    body = await req.json()
    return {"settings": save_settings(body)}


@app.patch("/api/jobs/{job_id}")
async def patch_job(job_id: str, req: Request):
    try:
        job  = mgr.get(job_id)
        body = await req.json()
        if "wiki_url" in body:
            job.wiki_url = body["wiki_url"].strip()
        if "params" in body:
            job.params = {k: body["params"].get(k, v) for k, v in DEFAULTS.items()}
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


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    try:
        await asyncio.to_thread(mgr.delete, job_id)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404)


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
    # Lighten the payload: the UI doesn't need the page list per node (large wikis)
    for node in tree.get("nodes", {}).values():
        node.pop("pages", None)
    return tree


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


@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML


# -- embedded UI ------------------------------------------------------------------
_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wiki Archive</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:      #0d1117; --surface: #161b22; --surface2: #21262d;
  --border:  #30363d; --text: #e6edf3; --muted: #7d8590;
  --accent:  #388bfd; --green: #3fb950; --red: #f85149;
  --yellow:  #d29922; --orange: #f0883e; --term: #010409;
  --r: 8px;
}
html, body { height: 100%; background: var(--bg); color: var(--text); font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }

.app { display: flex; height: 100vh; overflow: hidden; }

.sidebar { width: 270px; flex-shrink: 0; border-right: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
.sidebar-head { padding: .9rem 1rem; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: .5rem; }
.sidebar-head h1 { font-size: .95rem; font-weight: 700; flex: 1; }
.btn-new { background: var(--accent); color: #fff; border: none; border-radius: 6px; padding: .35rem .7rem; font-size: .76rem; font-weight: 600; cursor: pointer; white-space: nowrap; }
.btn-new:hover { opacity: .85; }
.icon-btn { background: transparent; border: 1px solid var(--border); color: var(--muted); border-radius: 6px; padding: .3rem .5rem; font-size: .72rem; cursor: pointer; }
.icon-btn:hover { color: var(--text); }
.icon-btn.on { color: var(--accent); border-color: var(--accent); }

.job-list { flex: 1; overflow-y: auto; padding: .5rem 0; }
.job-item { padding: .6rem 1rem; cursor: pointer; border-left: 3px solid transparent; display: flex; align-items: center; gap: .55rem; transition: background .1s; }
.job-item:hover { background: var(--surface2); }
.job-item.active { background: var(--surface); border-left-color: var(--accent); }
.job-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: .2rem; }
.job-item-top { display: flex; align-items: center; gap: .5rem; }
.job-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.job-name { font-size: .82rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.job-meta { font-size: .7rem; color: var(--muted); padding-left: 1rem; }
.job-size { font-size: .68rem; color: var(--muted); flex-shrink: 0; }
.job-cb { width: 14px; height: 14px; accent-color: var(--accent); flex-shrink: 0; }

.bulk-bar { border-top: 1px solid var(--border); padding: .6rem .8rem; display: flex; flex-direction: column; gap: .4rem; background: var(--surface); }
.bulk-bar .btn { width: 100%; }

.detail { flex: 1; overflow-y: auto; padding: 1.5rem; display: flex; flex-direction: column; gap: 1.1rem; }
.empty-state { margin: auto; text-align: center; color: var(--muted); }
.empty-state h2 { font-size: 1rem; margin-bottom: .5rem; }
.empty-state p  { font-size: .85rem; }

.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: 1.1rem; }
.card-title { font-size: .68rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; margin-bottom: .9rem; }

.step-banner { display: flex; align-items: center; gap: .6rem; padding: .7rem 1rem; border-radius: var(--r); background: #15233a; border: 1px solid #388bfd44; font-size: .85rem; }
.step-banner .num { background: var(--accent); color: #fff; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: .75rem; flex-shrink: 0; }

.badge { padding: 2px 10px; border-radius: 20px; font-size: .68rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; display: inline-flex; align-items: center; gap: 5px; }
.st-pending  { background:#21262d; color:var(--muted);   border:1px solid var(--border); }
.st-running  { background:#1f3a5f; color:#79c0ff;        border:1px solid #388bfd44; }
.st-paused   { background:#3a2d00; color:var(--yellow);  border:1px solid #d2992244; }
.st-stopped  { background:#3a1f0d; color:var(--orange);  border:1px solid #f0883e44; }
.st-scanned  { background:#1a3040; color:#79d4ff;        border:1px solid #79d4ff44; }
.st-done     { background:#14301d; color:var(--green);   border:1px solid #3fb95044; }
.st-error    { background:#3a1b1b; color:var(--red);     border:1px solid #f8514944; }

.dot-pending  { background: var(--muted); }
.dot-running  { background: #79c0ff; animation: pulse 1.5s infinite; }
.dot-paused   { background: var(--yellow); }
.dot-stopped  { background: var(--orange); }
.dot-scanned  { background: #79d4ff; }
.dot-done     { background: var(--green); }
.dot-error    { background: var(--red); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

.url-row { display: flex; gap: .6rem; margin-bottom: .75rem; }
input[type=text], input[type=number] { background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 6px; outline: none; padding: .52rem .8rem; font-size: .85rem; transition: border-color .15s; }
input[type=text] { flex: 1; font-family: monospace; }
input[type=text]:focus, input[type=number]:focus { border-color: var(--accent); }
input[type=text]::placeholder { color: var(--muted); opacity:.6; }
input[type=number] { width: 80px; }

.opts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: .65rem; margin-top: .75rem; padding-top: .75rem; border-top: 1px solid var(--border); }
.opt-group label { display: block; font-size: .72rem; color: var(--muted); margin-bottom: .3rem; }
.opt-group input[type=number] { width: 100%; }
.opt-group select { width:100%; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:6px; padding:.5rem .6rem; font-size:.85rem; outline:none; }
.opt-group select:focus { border-color:var(--accent); }
.opt-check { display: flex; align-items: center; gap: .45rem; padding-top: 1.3rem; }
.opt-check input[type=checkbox] { width: 14px; height: 14px; accent-color: var(--accent); }
.opt-check span { font-size: .82rem; }
small.danger { color: var(--red); }

.fmt-block { margin-top: .75rem; padding-top: .75rem; border-top: 1px solid var(--border); }
.fmt-title { display:block; font-size:.72rem; color:var(--muted); margin-bottom:.5rem; }
.fmt-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:.45rem .8rem; }
.fmt-check { display:flex; align-items:center; gap:.4rem; cursor:pointer; }
.fmt-check input { width:14px; height:14px; accent-color:var(--accent); }
.fmt-check span { font-size:.8rem; }

.actions { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
.btn { padding: .5rem 1.1rem; border: none; border-radius: 6px; font-size: .85rem; font-weight: 600; cursor: pointer; transition: opacity .15s; }
.btn:disabled { opacity:.35; cursor:not-allowed; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-danger  { background: var(--red);    color: #fff; }
.btn-warn    { background: var(--yellow); color: #000; }
.btn-ghost   { background: transparent; color: var(--muted); border: 1px solid var(--border); }
.btn:hover:not(:disabled) { opacity: .82; }
.btn-link { background:none; border:none; color:var(--muted); font-size:.78rem; cursor:pointer; text-decoration:underline; }
.btn-link:hover { color: var(--text); }

.steps { display: flex; }
.step { display: flex; flex-direction: column; align-items: center; flex: 1; gap: .4rem; position: relative; }
.step:not(:last-child)::after { content:''; position:absolute; top:11px; left:50%; width:100%; height:2px; background:var(--border); z-index:0; transition:background .4s; }
.step.done:not(:last-child)::after   { background:var(--green); }
.step.active:not(:last-child)::after { background:var(--accent); }
.step-dot { width:22px; height:22px; border-radius:50%; z-index:1; position:relative; border:2px solid var(--border); background:var(--bg); display:flex; align-items:center; justify-content:center; font-size:.6rem; font-weight:700; transition:all .3s; }
.step.done   .step-dot { border-color:var(--green);  background:var(--green);  color:#000; }
.step.active .step-dot { border-color:var(--accent); background:var(--accent); color:#fff; box-shadow:0 0 0 3px #388bfd22; }
.step.error  .step-dot { border-color:var(--red);    background:var(--red);    color:#fff; }
.step-lbl { font-size:.65rem; color:var(--muted); text-align:center; }
.step.active .step-lbl { color:var(--text); }
.step.done   .step-lbl { color:var(--green); }

.term-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:.7rem; }
.btn-sm { padding:.22rem .6rem; font-size:.7rem; }
#terminal { background:var(--term); border:1px solid var(--border); border-radius:6px; height:300px; overflow-y:auto; padding:.8rem .9rem; font-family:"Consolas","SF Mono","Courier New",monospace; font-size:.78rem; line-height:1.65; color:#adbac7; }
#terminal .l-sep  { color:var(--accent); font-weight:bold; }
#terminal .l-ok   { color:var(--green); }
#terminal .l-err  { color:var(--red); }
#terminal .l-warn { color:var(--yellow); }
#terminal .l-dim  { color:#666; font-style:italic; }

.files-grid { display:flex; flex-direction:column; gap:.4rem; }
.file-row { display:flex; align-items:center; gap:.6rem; padding:.5rem .8rem; background:var(--bg); border:1px solid var(--border); border-radius:6px; }
.file-name { flex:1; font-family:monospace; font-size:.8rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.file-size { font-size:.73rem; color:var(--muted); flex-shrink:0; }

.kb-path { display:flex; align-items:center; gap:.6rem; margin-bottom:.4rem; flex-wrap:wrap; }
.kb-path code { flex:1; min-width:200px; background:var(--bg); border:1px solid var(--border); border-radius:6px; padding:.45rem .7rem; font-size:.78rem; color:var(--accent); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.kb-hint { font-size:.72rem; color:var(--muted); margin-bottom:.6rem; }

.spin { display:inline-block; width:9px; height:9px; border:2px solid #79c0ff44; border-top-color:#79c0ff; border-radius:50%; animation:rot .7s linear infinite; }
@keyframes rot { to { transform:rotate(360deg); } }

.detail-head { display:flex; align-items:flex-start; gap:.75rem; margin-bottom:.25rem; }
.detail-url { font-family:monospace; font-size:.8rem; color:var(--muted); margin-top:.2rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:500px; }

/* tree */
.tree-toolbar { display:flex; gap:.4rem; align-items:center; flex-wrap:wrap; margin-bottom:.7rem; }
.tree-search { flex:1; min-width:140px; }
.tree-body { max-height:380px; overflow-y:auto; border:1px solid var(--border); border-radius:6px; padding:.4rem; }
.tree-node.t-hidden { display:none; }
.tree-row { display:flex; align-items:center; gap:.35rem; padding:.2rem .35rem; border-radius:4px; cursor:pointer; user-select:none; }
.tree-row:hover { background:var(--surface2); }
.tree-toggle { width:14px; text-align:center; font-size:.62rem; color:var(--muted); flex-shrink:0; }
.tree-cb { width:13px; height:13px; accent-color:var(--accent); flex-shrink:0; cursor:pointer; }
.tree-lbl { flex:1; font-size:.82rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tree-cnt { font-size:.66rem; color:var(--muted); flex-shrink:0; }
.tree-children { padding-left:18px; }

.gen-bar { display:flex; align-items:center; gap:.6rem; margin-top:.8rem; padding-top:.75rem; border-top:1px solid var(--border); flex-wrap:wrap; }
.gen-info { font-size:.82rem; color:var(--text); flex:1; min-width:160px; }
.gen-info .warn { color:var(--yellow); display:block; font-size:.74rem; margin-top:.2rem; }

/* storage */
.storage-bars { display:flex; flex-direction:column; gap:.5rem; margin-bottom:.7rem; }
.storage-row { display:flex; align-items:center; gap:.6rem; font-size:.8rem; }
.storage-row .lbl { width:150px; color:var(--muted); flex-shrink:0; }
.storage-row .val { font-weight:600; }

/* toasts */
#toasts { position:fixed; right:1rem; bottom:1rem; display:flex; flex-direction:column; gap:.5rem; z-index:1000; max-width:340px; }
.toast { background:var(--surface2); border:1px solid var(--border); border-left:3px solid var(--accent); border-radius:8px; padding:.7rem .9rem; font-size:.82rem; display:flex; align-items:center; gap:.7rem; box-shadow:0 6px 20px #0008; animation:slidein .2s ease; }
.toast.ok   { border-left-color:var(--green); }
.toast.err  { border-left-color:var(--red); }
.toast.warn { border-left-color:var(--yellow); }
.toast .msg { flex:1; }
.toast button { background:var(--accent); color:#fff; border:none; border-radius:5px; padding:.25rem .6rem; font-size:.74rem; font-weight:600; cursor:pointer; white-space:nowrap; }
@keyframes slidein { from { transform:translateX(20px); opacity:0; } to { transform:none; opacity:1; } }
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="sidebar-head">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <rect width="24" height="24" rx="5" fill="#388bfd" opacity=".18"/>
        <path d="M6 7h12M6 12h8M6 17h6" stroke="#388bfd" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <h1>Wiki Archive</h1>
      <button class="icon-btn" onclick="openSettings()" title="Settings">⚙</button>
      <button id="manage-btn" class="icon-btn" onclick="toggleManage()" title="Manage / select multiple jobs">Manage</button>
      <button class="btn-new" onclick="newJob()">+ New</button>
    </div>
    <div id="job-list" class="job-list"></div>
    <div id="bulk-bar"></div>
  </aside>

  <main id="detail" class="detail">
    <div class="empty-state">
      <h2>No job selected</h2>
      <p>Create a new job or select one from the list.</p>
    </div>
  </main>
</div>
<div id="toasts"></div>

<script>
// ── config ─────────────────────────────────────────────────────────────────
const STEPS    = """ + json.dumps(STEPS) + """;
const DEFAULTS = """ + json.dumps(DEFAULTS) + """;

const EXPORT_FORMATS = [
  { id: "pdf", label: "PDF (.pdf)", pdf: true },
  { id: "md",  label: "Markdown (.md)" },
  { id: "txt", label: "Text (.txt)" },
];
const ALL_FORMAT_IDS = EXPORT_FORMATS.map(f => f.id);

const STATUS_LABEL = {
  pending: "Pending",   running: "Running",   paused:  "Paused",
  stopped: "Stopped",   scanned: "Scanned",   done:    "Done",
  error:   "Error",
};

const LOG_RULES = [
  [t => t.includes("━━━") || t.includes("════"),         "l-sep"],
  [t => t.startsWith("✓") || t.includes("PIPELINE COMPLETE"),     "l-ok"],
  [t => t.startsWith("✗") || /(ERROR|Traceback|Error:)/i.test(t), "l-err"],
  [t => t.startsWith("⚠") || /warning/i.test(t),        "l-warn"],
  [t => t.startsWith("⏸") || t.startsWith("⏹") || t.startsWith("🧹"), "l-dim"],
];

// ── helpers ──────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
                  .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function fmtWords(n) {
  if (!n) return "0 words";
  if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1) + "k words";
  return n + " word" + (n === 1 ? "" : "s");
}
function jobName(url) {
  try { return new URL(url).hostname.replace("www.", ""); } catch { return url.slice(0, 25); }
}
function relDate(iso) {
  const sec = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (sec < 60)    return "just now";
  if (sec < 3600)  return Math.floor(sec / 60) + "min";
  if (sec < 86400) return Math.floor(sec / 3600) + "h";
  return Math.floor(sec / 86400) + "d";
}
function parseFormats(str) {
  const s = (str || "pdf").trim();
  if (s === "all")  return new Set(ALL_FORMAT_IDS);
  if (s === "none" || s === "") return new Set();
  return new Set(s.split(",").map(x => x.trim()).filter(Boolean));
}
function collectFormats() {
  const picked = ALL_FORMAT_IDS.filter(id => document.getElementById("f-fmt-" + id)?.checked);
  if (picked.length === 0)                     return "none";
  if (picked.length === ALL_FORMAT_IDS.length) return "all";
  return picked.join(",");
}
function togglePdfOpts() {
  const on = document.getElementById("f-fmt-pdf")?.checked;
  document.querySelectorAll(".pdf-opt").forEach(el => { el.style.display = on ? "" : "none"; });
}
function loadPrefs() {
  try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem("wiki-archive-prefs") || "{}") }; }
  catch { return { ...DEFAULTS }; }
}
function savePrefs(p) { try { localStorage.setItem("wiki-archive-prefs", JSON.stringify(p)); } catch {} }

// ── toasts ───────────────────────────────────────────────────────────────────
function showToast(msg, opts) {
  opts = opts || {};
  const box = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = "toast " + (opts.type || "");
  const span = document.createElement("span");
  span.className = "msg"; span.textContent = msg;
  el.appendChild(span);
  let timer = null;
  const close = () => { if (timer) clearTimeout(timer); el.remove(); };
  if (opts.action) {
    const b = document.createElement("button");
    b.textContent = opts.action;
    b.onclick = () => { close(); if (opts.onAction) opts.onAction(); };
    el.appendChild(b);
  }
  box.appendChild(el);
  timer = setTimeout(() => { el.remove(); if (opts.onTimeout) opts.onTimeout(); },
                     opts.timeout || 3500);
  return close;
}

// ── state ──────────────────────────────────────────────────────────────────
let allJobs    = {};
let globalSettings = null;   // default settings (pre-fill new jobs)
let NLM_PLANS  = {};         // NotebookLM presets (plan -> sources)
let selectedId = null;
let logStream  = null;
let currentStep = -1;
let creatingNew = false;
let manageMode  = false;
let sidebarSel  = new Set();   // jobs checked in manage mode
let sizeCache   = {};          // id -> human-readable size (loaded on demand)
let pendingDel  = new Set();   // jobs pending deletion (undoable)

// tree (lazy render -- an "ik" = rendered instance of a category)
let treeData   = null;
let nodeState  = {};   // cat -> 0 | 1 | 2
let parentMap  = {};   // cat -> [parents]
let ikCat      = {};   // ik -> cat
let ikAnc      = {};   // ik -> Set(ancestors) to cut cycles
let ikOpen     = {};   // ik -> expanded?
let ikPop      = {};   // ik -> children already built?
let ikCtr      = 0;
let treeSort   = "size";
let previewTimer = null, selTimer = null;

// ── polling ────────────────────────────────────────────────────────────────
async function refresh() {
  const list = await fetch("/api/jobs").then(r => r.json()).catch(() => []);
  allJobs = Object.fromEntries(list.map(j => [j.id, j]));
  renderSidebar();
  if (selectedId && allJobs[selectedId]) updateDetail(allJobs[selectedId]);
}
setInterval(refresh, 2000);

// ── sidebar ────────────────────────────────────────────────────────────────
function renderSidebar() {
  const el = document.getElementById("job-list");
  const jobs = Object.values(allJobs).filter(j => !pendingDel.has(j.id));
  if (!jobs.length && !creatingNew) {
    el.innerHTML = '<div style="padding:.75rem 1rem;font-size:.78rem;color:var(--muted)">No jobs</div>';
    renderBulkBar();
    return;
  }
  el.innerHTML = jobs.map(j => {
    const cb = manageMode
      ? `<input type="checkbox" class="job-cb" ${sidebarSel.has(j.id) ? "checked" : ""}
                onclick="event.stopPropagation();toggleSidebarSel('${j.id}')">`
      : "";
    const size = (manageMode && sizeCache[j.id]) ? `<span class="job-size">${sizeCache[j.id]}</span>` : "";
    return `<div class="job-item${j.id === selectedId ? " active" : ""}" onclick="selectJob('${j.id}')">
      ${cb}
      <div class="job-main">
        <div class="job-item-top">
          <div class="job-dot dot-${j.status}"></div>
          <div class="job-name" title="${esc(j.wiki_url)}">${esc(jobName(j.wiki_url))}</div>
          ${size}
        </div>
        <div class="job-meta">${STATUS_LABEL[j.status] || j.status} · ${relDate(j.created_at)}</div>
      </div>
    </div>`;
  }).join("");
  renderBulkBar();
}

function renderBulkBar() {
  const bar = document.getElementById("bulk-bar");
  if (!manageMode) { bar.innerHTML = ""; return; }
  const n = sidebarSel.size;
  const cleanable = Object.values(allJobs).filter(j => ["stopped","error"].includes(j.status)).length;
  bar.className = "bulk-bar";
  bar.innerHTML = `
    <button class="btn btn-danger btn-sm" ${n ? "" : "disabled"} onclick="bulkDeleteSelected()">
      🗑 Delete selection (${n})
    </button>
    <button class="btn btn-ghost btn-sm" ${cleanable ? "" : "disabled"} onclick="cleanupStoppedErrored()">
      🧹 Clean up stopped/errored (${cleanable})
    </button>`;
}

async function toggleManage() {
  manageMode = !manageMode;
  sidebarSel.clear();
  document.getElementById("manage-btn").classList.toggle("on", manageMode);
  renderSidebar();
  if (manageMode) {
    // Load sizes once (outside of polling)
    for (const id of Object.keys(allJobs)) {
      fetch(`/api/jobs/${id}/disk`).then(r => r.json()).then(d => {
        sizeCache[id] = d.human; renderSidebar();
      }).catch(() => {});
    }
  }
}

function toggleSidebarSel(id) {
  if (sidebarSel.has(id)) sidebarSel.delete(id); else sidebarSel.add(id);
  renderBulkBar();
}

function bulkDeleteSelected() {
  requestDelete([...sidebarSel]);
  sidebarSel.clear();
}
function cleanupStoppedErrored() {
  const ids = Object.values(allJobs)
    .filter(j => ["stopped","error"].includes(j.status)).map(j => j.id);
  requestDelete(ids);
}

// ── deletion with undo (toast) ────────────────────────────────────────────────
function requestDelete(ids) {
  if (!ids.length) return;
  ids.forEach(id => pendingDel.add(id));
  if (selectedId && ids.includes(selectedId)) { selectedId = null; showEmpty(); stopLogStream(); }
  renderSidebar();
  const label = ids.length === 1 ? "Job deleted" : ids.length + " jobs deleted";
  const cancel = () => { ids.forEach(id => pendingDel.delete(id)); renderSidebar(); };
  const commit = async () => {
    const live = ids.filter(id => pendingDel.has(id));
    if (!live.length) return;
    await fetch("/api/jobs/bulk_delete", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ ids: live }),
    }).catch(() => {});
    live.forEach(id => pendingDel.delete(id));
    refresh();
  };
  showToast(label + " -- undo available", {
    action: "Undo", timeout: 5000,
    onAction: () => { cancel(); showToast("Deletion cancelled", {type:"ok"}); },
    onTimeout: commit,
  });
}

// ── new job / form ─────────────────────────────────────────────────────────
function showEmpty() {
  document.getElementById("detail").innerHTML = `
    <div class="empty-state"><h2>No job selected</h2>
    <p>Create a new job or select one from the list.</p></div>`;
}
function newJob() {
  creatingNew = true; selectedId = null;
  renderSidebar();
  document.getElementById("detail").innerHTML = buildForm(null);
}
function cancelNew() { creatingNew = false; showEmpty(); }

// ── settings page ─────────────────────────────────────────────────────────
async function openSettings() {
  creatingNew = false; selectedId = null; stopLogStream(); renderSidebar();
  const d = await fetch("/api/settings").then(r => r.json()).catch(() => null);
  if (d) { globalSettings = d.settings; NLM_PLANS = d.plans || {}; }
  document.getElementById("detail").innerHTML = buildSettingsPage(globalSettings || DEFAULTS);
}
function closeSettings() { showEmpty(); }

function buildSettingsPage(s) {
  const fmtSet = parseFormats(s.export_formats);
  const planOpts = Object.entries(NLM_PLANS).map(([k, v]) =>
      `<option value="${k}" ${s.notebooklm_plan === k ? "selected" : ""}>${esc(v.label)} — ${v.sources} sources</option>`).join("")
    + `<option value="custom" ${!NLM_PLANS[s.notebooklm_plan] ? "selected" : ""}>Custom</option>`;
  return `
  <div class="detail-head"><div style="flex:1">
    <div style="display:flex;align-items:center;gap:.6rem">
      <span style="font-weight:700;font-size:1.1rem">⚙ Default settings</span>
      <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="closeSettings()">Close</button>
    </div>
    <div class="kb-hint" style="margin-top:.4rem">These values pre-fill every new job. You can always adjust them per job.</div>
  </div></div>

  <div class="card">
    <div class="card-title">NotebookLM</div>
    <div class="opts-grid">
      <div class="opt-group"><label>NotebookLM plan</label>
        <select id="s-plan" onchange="onPlanChange()">${planOpts}</select></div>
      <div class="opt-group"><label>Max files (sources) per notebook</label>
        <input type="number" id="s-maxfiles" value="${s.max_files}" min="0" max="600" oninput="onMaxFilesInput()" style="width:100%" title="0 = no cap"/></div>
      <div class="opt-group"><label>Max words per file</label>
        <input type="number" id="s-maxwords" value="${s.notebooklm_max_words}" min="10000" step="10000" style="width:100%"/></div>
      <div class="opt-group opt-check"><input type="checkbox" id="s-dedup" ${s.dedup !== false ? "checked" : ""}/><span>Avoid duplicates (1 page = 1 file)</span></div>
    </div>
    <div class="kb-hint" style="margin-top:.6rem">NotebookLM limit: <b>500,000 words per source</b>, the same across all plans. Only the number of sources changes — Free 50 · Plus 100 · Pro 300 · Ultra 600.</div>
  </div>

  <div class="card">
    <div class="card-title">Default formats</div>
    <div class="fmt-grid">
      ${EXPORT_FORMATS.map(f => `<label class="fmt-check"><input type="checkbox" id="s-fmt-${f.id}" ${fmtSet.has(f.id) ? "checked" : ""}/><span>${f.label}</span></label>`).join("")}
    </div>
  </div>

  <div class="card">
    <div class="card-title">Download</div>
    <div class="opts-grid">
      <div class="opt-group"><label>Namespaces</label>
        <input type="text" id="s-ns" value="${esc(s.namespaces)}" style="width:100%;font-family:monospace;font-size:.82rem"/></div>
      <div class="opt-group"><label>Delay between requests (s)</label>
        <input type="number" id="s-delay" value="${s.delay}" min="0" step="0.1" style="width:100%"/></div>
      <div class="opt-group"><label>Parallel scan (categories)</label>
        <input type="number" id="s-catworkers" value="${s.cat_workers}" min="1" max="32" style="width:100%" title="Faster, but puts more load on the wiki"/></div>
      <div class="opt-group opt-check"><input type="checkbox" id="s-images" ${s.images ? "checked" : ""}/><span>Include images</span></div>
      <div class="opt-group opt-check"><input type="checkbox" id="s-force" ${s.force !== false ? "checked" : ""}/><span>Skip Internet Archive</span></div>
    </div>
  </div>

  <div class="card">
    <div class="card-title">PDF</div>
    <div class="opts-grid">
      <div class="opt-group"><label>Max pages per merged PDF</label>
        <input type="number" id="s-maxpdf" value="${s.max_pdf}" min="1" max="2000" style="width:100%"/></div>
      <div class="opt-group"><label>PDF workers</label>
        <input type="number" id="s-workers" value="${s.workers}" min="1" max="16" style="width:100%"/></div>
    </div>
  </div>

  <div class="actions">
    <button class="btn btn-primary" onclick="saveSettings()">💾 Save</button>
    <button class="btn btn-ghost" onclick="closeSettings()">Close</button>
  </div>`;
}
function onPlanChange() {
  const plan = document.getElementById("s-plan").value;
  if (NLM_PLANS[plan]) document.getElementById("s-maxfiles").value = NLM_PLANS[plan].sources;
}
function onMaxFilesInput() {
  const v = parseInt(document.getElementById("s-maxfiles").value);
  const match = Object.entries(NLM_PLANS).find(([, p]) => p.sources === v);
  document.getElementById("s-plan").value = match ? match[0] : "custom";
}
async function saveSettings() {
  const fmt = ALL_FORMAT_IDS.filter(id => document.getElementById("s-fmt-" + id)?.checked);
  const body = {
    notebooklm_plan:      document.getElementById("s-plan").value,
    max_files:            parseInt(document.getElementById("s-maxfiles").value) || 0,
    notebooklm_max_words: parseInt(document.getElementById("s-maxwords").value) || 500000,
    dedup:                document.getElementById("s-dedup").checked,
    export_formats:       fmt.length ? (fmt.length === ALL_FORMAT_IDS.length ? "all" : fmt.join(",")) : "none",
    namespaces:           document.getElementById("s-ns").value.trim(),
    delay:                parseFloat(document.getElementById("s-delay").value) || 0.5,
    cat_workers:          parseInt(document.getElementById("s-catworkers").value) || 8,
    images:               document.getElementById("s-images").checked,
    force:                document.getElementById("s-force").checked,
    max_pdf:              parseInt(document.getElementById("s-maxpdf").value) || 500,
    workers:              parseInt(document.getElementById("s-workers").value) || 4,
  };
  const r = await fetch("/api/settings", {
    method: "PUT", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body),
  }).then(r => r.json()).catch(() => null);
  if (r && r.settings) { globalSettings = r.settings; showToast("Settings saved ✓", {type:"ok"}); }
  else showToast("Failed to save settings", {type:"err"});
}

function buildForm(job) {
  const p = job ? job.params : (globalSettings || DEFAULTS);
  const url = job ? job.wiki_url : "";
  const fmtSet = parseFormats(p.export_formats);
  const pdfStyle = fmtSet.has("pdf") ? "" : "display:none";
  const isNew = !job;
  return `
  <div class="card">
    <div class="card-title">${job ? "Reconfigure" : "New job — Step 1"}</div>
    <div class="url-row">
      <input id="f-url" type="text" value="${esc(url)}" placeholder="Paste any URL from the wiki"/>
    </div>
    <div class="fmt-block">
      <label class="fmt-title">Formats to generate</label>
      <div class="fmt-grid">
        ${EXPORT_FORMATS.map(f => `
          <label class="fmt-check">
            <input type="checkbox" id="f-fmt-${f.id}" ${fmtSet.has(f.id) ? "checked" : ""}
                   ${f.pdf ? 'onchange="togglePdfOpts()"' : ""}/>
            <span>${f.label}</span>
          </label>`).join("")}
      </div>
    </div>
    <div class="opts-grid">
      <div class="opt-group"><label>Namespaces</label>
        <input type="text" id="f-ns" value="${esc(p.namespaces)}" style="width:100%;font-family:monospace;font-size:.82rem"/></div>
      <div class="opt-group"><label>Delay (s)</label>
        <input type="number" id="f-delay" value="${p.delay}" min="0" step="0.5" style="width:100%"/></div>
      <div class="opt-group pdf-opt" style="${pdfStyle}"><label>Max pages / merged PDF</label>
        <input type="number" id="f-maxpdf" value="${p.max_pdf}" min="1" max="2000" style="width:100%"/></div>
      <div class="opt-group pdf-opt" style="${pdfStyle}"><label>PDF workers</label>
        <input type="number" id="f-workers" value="${p.workers}" min="1" max="16" style="width:100%"/></div>
      <div class="opt-group"><label>Max files (NotebookLM)</label>
        <input type="number" id="f-maxfiles" value="${p.max_files ?? 50}" min="0" max="600" style="width:100%" title="0 = no cap"/></div>
      <div class="opt-group opt-check">
        <input type="checkbox" id="f-dedup" ${p.dedup !== false ? "checked" : ""}/><span>Avoid duplicates <small style="color:var(--muted)">(1 page = 1 file)</small></span></div>
      <div class="opt-group opt-check">
        <input type="checkbox" id="f-images" ${p.images ? "checked" : ""}/><span>Include images</span></div>
      <div class="opt-group opt-check">
        <input type="checkbox" id="f-clean" ${p.clean ? "checked" : ""}/><span>New full dump <small class="danger">(wipes everything)</small></span></div>
      <div class="opt-group opt-check pdf-opt" style="${pdfStyle}">
        <input type="checkbox" id="f-rerender" ${p.rerender ? "checked" : ""}/><span>Re-render output</span></div>
      <div class="opt-group opt-check">
        <input type="checkbox" id="f-force" ${p.force !== false ? "checked" : ""}/><span>Skip Internet Archive</span></div>
    </div>
    <div class="actions" style="margin-top:1rem">
      <button class="btn btn-primary" onclick="scanFromForm(${job ? `'${job.id}'` : "null"})">🔍 Step 1 — Scan the wiki</button>
      <button class="btn-link" onclick="submitFull(${job ? `'${job.id}'` : "null"})">Do everything at once</button>
      ${isNew ? `<button class="btn-link" onclick="cancelNew()">Cancel</button>` : ""}
    </div>
  </div>`;
}

function collectParams(base) {
  base = base || globalSettings || DEFAULTS;
  const mf = parseInt(document.getElementById("f-maxfiles")?.value);
  return {
    ...base,   // inherits keys not shown in the form (notebooklm_max_words, cat_workers…)
    namespaces: document.getElementById("f-ns")?.value?.trim() ?? base.namespaces,
    delay:      parseFloat(document.getElementById("f-delay")?.value) || 0.5,
    max_pdf:    parseInt(document.getElementById("f-maxpdf")?.value)  || 100,
    workers:    parseInt(document.getElementById("f-workers")?.value) || 4,
    max_files:  Number.isFinite(mf) ? mf : (base.max_files ?? 50),
    dedup:      document.getElementById("f-dedup")?.checked ?? base.dedup ?? true,
    images:     document.getElementById("f-images")?.checked ?? true,
    clean:      document.getElementById("f-clean")?.checked ?? false,
    rerender:   document.getElementById("f-rerender")?.checked ?? false,
    force:      document.getElementById("f-force")?.checked ?? true,
    export_formats: collectFormats(),
  };
}

async function ensureJob(existingId) {
  const url = document.getElementById("f-url")?.value?.trim();
  const base = existingId ? allJobs[existingId]?.params : globalSettings;
  const params = collectParams(base);
  if (existingId) {
    await fetch(`/api/jobs/${existingId}`, {
      method: "PATCH", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ wiki_url: url || undefined, params }),
    });
    return existingId;
  }
  if (!url) { showToast("Paste the wiki URL first.", {type:"err"}); return null; }
  const job = await fetch("/api/jobs", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ wiki_url: url, ...params }),
  }).then(r => r.json());
  allJobs[job.id] = job;
  return job.id;
}

async function scanFromForm(existingId) {
  const id = await ensureJob(existingId);
  if (!id) return;
  treeData = null; nodeState = {};
  creatingNew = false;
  selectedId = id;
  await fetch(`/api/jobs/${id}/scan`, { method: "POST" });
  selectJob(id);
  refresh();
}

async function submitFull(existingId) {
  if (collectFormats() === "none") { showToast("Choose at least one format.", {type:"err"}); return; }
  const id = await ensureJob(existingId);
  if (!id) return;
  creatingNew = false;
  selectedId = id;
  await fetch(`/api/jobs/${id}/${existingId ? "resume" : "start"}`, { method: "POST" });
  selectJob(id);
  refresh();
}

// ── selection & detail rendering ─────────────────────────────────────────────
function selectJob(id) {
  selectedId = id; currentStep = -1; creatingNew = false;
  treeData = null; nodeState = {};
  stopLogStream();
  const job = allJobs[id];
  if (!job) return;
  renderFullDetail(job);
  renderSidebar();
  startLogStream(id, 0);
  // Automatically load the tree if generation is possible
  if (canGenerate(job)) loadTree(id);
}

function canGenerate(job) { return job.has_tree && job.data_present; }

function renderFullDetail(job) {
  const showForm = ["pending","stopped","done","error","scanned"].includes(job.status);
  const showGen  = canGenerate(job);
  document.getElementById("detail").innerHTML = `
  <div class="detail-head">
    <div style="flex:1">
      <div style="display:flex;align-items:center;gap:.6rem;margin-bottom:.35rem">
        <span style="font-weight:700;font-size:1rem">${esc(jobName(job.wiki_url))}</span>
        <span id="d-badge" class="badge st-${job.status}">${badgeHtml(job.status)}</span>
        <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="requestDelete(['${job.id}'])" title="Delete">🗑</button>
      </div>
      <div class="detail-url">${esc(job.wiki_url)}</div>
    </div>
  </div>
  <div id="d-banner">${buildBanner(job)}</div>
  <div id="d-actions" class="actions">${buildActions(job)}</div>
  <div id="d-gen" class="card" style="${showGen ? "" : "display:none"}">${buildGenPanel(job)}</div>
  <div id="d-form">${showForm && !showGen ? buildForm(job) : ""}</div>
  <div class="card">
    <div class="card-title">Progress</div>
    <div id="d-steps" class="steps">${buildSteps()}</div>
  </div>
  <div class="card">
    <div class="term-head">
      <div class="card-title" style="margin:0">Log</div>
      <button class="btn btn-ghost btn-sm" onclick="document.getElementById('terminal').innerHTML=''">Clear</button>
    </div>
    <div id="terminal"><span class="l-dim">Loading logs…</span></div>
  </div>
  <div id="d-storage" class="card">
    <div class="card-title">Storage</div>
    <div id="storage-body"><button class="btn btn-ghost btn-sm" onclick="loadStorage('${job.id}')">View disk space used</button></div>
  </div>
  <div id="d-files" class="card" style="${job.files && job.files.length ? "" : "display:none"}">
    <div class="card-title">Generated files</div>
    <div class="files-grid">${buildFiles(job)}</div>
  </div>`;
}

function buildBanner(job) {
  if (job.status === "scanned" || (job.status === "done" && canGenerate(job)))
    return `<div class="step-banner"><span class="num">2</span>
      <span>Step 2 — Choose which categories to keep, then generate your files.</span></div>`;
  if (["pending"].includes(job.status))
    return `<div class="step-banner"><span class="num">1</span>
      <span>Step 1 — Scan the wiki to discover its categories.</span></div>`;
  if (job.status === "done" && !job.data_present)
    return `<div class="step-banner" style="background:#2a2410;border-color:#d2992244">
      <span>ℹ️ The downloaded data was freed. Run a new scan to regenerate.</span></div>`;
  return "";
}

function buildActions(job) {
  const s = job.status, id = job.id;
  if (s === "running") return `
    <button class="btn btn-warn"   onclick="jobAction('${id}','pause')">⏸ Pause</button>
    <button class="btn btn-danger" onclick="jobAction('${id}','stop')">⏹ Stop</button>`;
  if (s === "paused") return `
    <button class="btn btn-primary" onclick="jobAction('${id}','resume')">▶ Resume</button>
    <button class="btn btn-danger"  onclick="jobAction('${id}','stop')">⏹ Stop</button>`;
  return "";   // other states are driven via the generation panel / form
}

function buildGenPanel(job) {
  return `
    <div class="card-title">Choose categories</div>
    <div class="tree-toolbar">
      <button class="btn btn-ghost btn-sm" onclick="treeSelectAll()">All</button>
      <button class="btn btn-ghost btn-sm" onclick="treeSelectNone()">None</button>
      <button class="btn btn-ghost btn-sm" onclick="treeCollapseAll()">Collapse</button>
      <button class="btn btn-ghost btn-sm" onclick="toggleSort()" id="sort-btn">Sort: size</button>
      <input type="text" class="tree-search" placeholder="Filter categories…" oninput="filterTree(this.value)"/>
    </div>
    <div class="tree-body" id="tree-body" onclick="treeClick(event)" onchange="treeChange(event)">
      <span class="l-dim">Loading tree…</span>
    </div>
    <div class="gen-bar">
      <span class="gen-info" id="gen-info">—</span>
      <button class="btn-link" onclick="toggleReconfigure('${job.id}')">Reconfigure / re-scan</button>
      <button class="btn btn-ghost" onclick="doGenerateAll('${job.id}')">Generate all</button>
      <button class="btn btn-primary" onclick="doGenerate('${job.id}')">▶ Generate selection</button>
    </div>`;
}

function toggleReconfigure(jobId) {
  const form = document.getElementById("d-form");
  if (!form) return;
  if (form.querySelector(".card")) { form.innerHTML = ""; return; }
  form.innerHTML = buildForm(allJobs[jobId]);
}

function buildSteps() {
  return STEPS.map((s, i) => `
    <div class="step" id="step-${i}"><div class="step-dot">${i + 1}</div>
      <div class="step-lbl">${s.label}</div></div>`).join("");
}

function buildFiles(job) {
  if (!job.files || !job.files.length) return "";
  const icon = e => ({ pdf:"📕", md:"📘", txt:"📄" }[e] || "📄");
  const rows = job.files.map(f => `
    <div class="file-row"><span>${icon(f.ext)}</span>
      <span class="file-name" title="${esc(f.name)}">${esc(f.name)}</span>
      <span class="file-size">${f.size}</span></div>`).join("");
  return `
    <div class="kb-path">
      <code id="kb-path-text">${esc(job.out_path)}</code>
      <button class="btn btn-ghost btn-sm" onclick="copyPath(this)">📂 Copy path</button>
    </div>
    <div class="kb-hint">${job.files.length} file(s). Paste this path into File Explorer, then import the folder into NotebookLM.</div>
    ${rows}`;
}

function badgeHtml(status) {
  const spin = status === "running" ? '<span class="spin"></span> ' : "";
  return spin + (STATUS_LABEL[status] || status);
}

async function copyPath(btn) {
  const el = document.getElementById("kb-path-text");
  if (!el) return;
  const path = el.textContent, label = btn.textContent;
  try { await navigator.clipboard.writeText(path); btn.textContent = "✓ Copied!"; }
  catch {
    const r = document.createRange(); r.selectNode(el);
    getSelection().removeAllRanges(); getSelection().addRange(r);
    btn.textContent = "Selected — Ctrl+C";
  }
  setTimeout(() => { btn.textContent = label; }, 1800);
}

function updateDetail(job) {
  if (!selectedId || selectedId !== job.id) return;
  const badge = document.getElementById("d-badge");
  if (badge) { badge.className = `badge st-${job.status}`; badge.innerHTML = badgeHtml(job.status); }
  const actions = document.getElementById("d-actions");
  if (actions) actions.innerHTML = buildActions(job);
  const banner = document.getElementById("d-banner");
  if (banner) banner.innerHTML = buildBanner(job);

  // Show the generation panel once the tree becomes available
  const gen = document.getElementById("d-gen");
  if (gen && canGenerate(job) && gen.style.display === "none") {
    gen.style.display = ""; gen.innerHTML = buildGenPanel(job);
    const form = document.getElementById("d-form"); if (form) form.innerHTML = "";
    loadTree(job.id);
  }
  if (job.status === "error" && currentStep >= 0) setStep(currentStep, "error");
  const filesEl = document.getElementById("d-files");
  if (filesEl && job.files && job.files.length) {
    filesEl.style.display = "";
    filesEl.querySelector(".files-grid").innerHTML = buildFiles(job);
  }
}

// ── category tree ─────────────────────────────────────────────────────────
function buildParentMap() {
  parentMap = {};
  for (const [cat, node] of Object.entries(treeData.nodes || {}))
    for (const child of (node.children || [])) (parentMap[child] ||= []).push(cat);
}
function initTreeState(checked) {
  nodeState = {};
  for (const cat of Object.keys(treeData?.nodes || {})) nodeState[cat] = checked ? 2 : 0;
}
function setDescendants(cat, state, seen) {
  if (seen.has(cat)) return; seen.add(cat);
  nodeState[cat] = state;
  for (const c of (treeData?.nodes?.[cat]?.children || [])) setDescendants(c, state, seen);
}
function recomputeAncestors(cat, seen) {
  if (seen.has(cat)) return; seen.add(cat);
  for (const parent of (parentMap[cat] || [])) {
    const kids = treeData?.nodes?.[parent]?.children || [];
    const st = kids.map(c => nodeState[c] ?? 0);
    nodeState[parent] = st.every(s => s === 2) ? 2 : st.every(s => s === 0) ? 0 : 1;
    recomputeAncestors(parent, seen);
  }
}
function sortCats(cats) {
  const arr = [...cats];
  if (treeSort === "name") arr.sort((a, b) => a.localeCompare(b));
  else arr.sort((a, b) => (treeData.nodes[b]?.total_words || 0) - (treeData.nodes[a]?.total_words || 0));
  return arr;
}
// LAZY rendering: only the roots are displayed; sub-categories
// are built on first expand. Essential for large wikis
// (Minecraft = 3600+ categories) and safe against cycles (A→B→A).
function realChildren(cat, anc) {
  // existing children, excluding cycles (an ancestor cannot become a descendant again)
  return (treeData.nodes[cat]?.children || [])
    .filter(c => treeData.nodes[c] && c !== cat && !anc.has(c));
}
function nodeHtml(cat, anc) {
  const node = treeData.nodes[cat]; if (!node) return "";
  const ik = ikCtr++;
  ikCat[ik] = cat; ikAnc[ik] = anc; ikOpen[ik] = false; ikPop[ik] = false;
  const hasKids = realChildren(cat, anc).length > 0;
  return `<div class="tree-node" data-key="${ik}">
      <div class="tree-row" data-key="${ik}">
        <span class="tree-toggle">${hasKids ? "▶" : ""}</span>
        <input type="checkbox" class="tree-cb" data-key="${ik}">
        <span class="tree-lbl" title="${esc(cat)}">${esc(cat)}</span>
        <span class="tree-cnt">${node.total_pages}p · ${fmtWords(node.total_words || 0)}</span>
      </div>
      <div class="tree-children" data-childkey="${ik}" style="display:none"></div>
    </div>`;
}
function expandNode(ik) {
  if (ikPop[ik]) return;            // already built
  ikPop[ik] = true;
  const cat = ikCat[ik];
  const anc = new Set(ikAnc[ik]); anc.add(cat);
  const kids = sortCats(realChildren(cat, anc));
  const div = document.querySelector(`.tree-children[data-childkey="${ik}"]`);
  if (div) div.innerHTML = kids.map(c => nodeHtml(c, anc)).join("");
  applyCheckboxStates();
}
function renderRoots() {
  ikCat = {}; ikAnc = {}; ikOpen = {}; ikPop = {}; ikCtr = 0;
  const body = document.getElementById("tree-body");
  if (!body) return;
  const roots = sortCats(treeData.roots || []);
  body.innerHTML = roots.length
    ? roots.map(c => nodeHtml(c, new Set())).join("")
    : '<span class="l-dim">No root category.</span>';
  applyCheckboxStates();
}
async function loadTree(jobId) {
  const body = document.getElementById("tree-body");
  if (body) body.innerHTML = '<span class="l-dim">Loading tree…</span>';
  const data = await fetch(`/api/jobs/${jobId}/category_tree`).then(r => r.json()).catch(() => ({error:"Network error"}));
  if (data.error) { if (body) body.innerHTML = `<span class="l-err">${esc(data.error)}</span>`; return; }
  treeData = data;
  buildParentMap();
  // Pre-check from the saved selection, otherwise everything
  const saved = allJobs[jobId]?.selection;
  if (saved && saved.length) {
    initTreeState(false);
    const seen = new Set();
    saved.forEach(c => setDescendants(c, 2, seen));
    saved.forEach(c => recomputeAncestors(c, new Set()));
  } else {
    initTreeState(true);
  }
  renderRoots();
}
function applyCheckboxStates() {
  document.querySelectorAll("#tree-body .tree-cb").forEach(cb => {
    const cat = ikCat[cb.dataset.key]; const st = nodeState[cat] ?? 0;
    cb.checked = st === 2; cb.indeterminate = st === 1;
  });
  updateGenInfo(); schedulePreview();
}
function treeClick(e) {
  if (e.target.closest(".tree-cb")) return;
  const row = e.target.closest(".tree-row"); if (!row) return;
  const ik = row.dataset.key;
  const t = row.querySelector(".tree-toggle");
  if (!t || !t.textContent) return;        // no children
  const div = document.querySelector(`.tree-children[data-childkey="${ik}"]`);
  if (!div) return;
  ikOpen[ik] = !ikOpen[ik];
  if (ikOpen[ik]) { expandNode(ik); div.style.display = ""; t.textContent = "▾"; }
  else            { div.style.display = "none"; t.textContent = "▶"; }
}
function treeChange(e) {
  const cb = e.target.closest(".tree-cb"); if (!cb) return;
  const cat = ikCat[cb.dataset.key];
  setDescendants(cat, cb.checked ? 2 : 0, new Set());
  recomputeAncestors(cat, new Set());
  applyCheckboxStates();
  scheduleSaveSelection();
}
function treeSelectAll()  { initTreeState(true);  applyCheckboxStates(); scheduleSaveSelection(); }
function treeSelectNone() { initTreeState(false); applyCheckboxStates(); scheduleSaveSelection(); }
function treeCollapseAll() {
  document.querySelectorAll("#tree-body .tree-children").forEach(d => { d.style.display = "none"; ikOpen[d.dataset.childkey] = false; });
  document.querySelectorAll("#tree-body .tree-toggle").forEach(t => { if (t.textContent) t.textContent = "▶"; });
}
function toggleSort() {
  treeSort = treeSort === "size" ? "name" : "size";
  const b = document.getElementById("sort-btn");
  if (b) b.textContent = "Sort: " + (treeSort === "size" ? "size" : "name");
  const f = document.querySelector(".tree-search");
  if (f && f.value.trim()) filterTree(f.value); else renderRoots();
}
// Search: FLAT list of matching categories (no deep tree)
function filterTree(term) {
  const q = term.toLowerCase().trim();
  const body = document.getElementById("tree-body");
  if (!body) return;
  if (!q) { renderRoots(); return; }
  ikCat = {}; ikAnc = {}; ikOpen = {}; ikPop = {}; ikCtr = 0;
  const matches = sortCats(Object.keys(treeData.nodes).filter(c => c.toLowerCase().includes(q)));
  const CAP = 300;
  const shown = matches.slice(0, CAP);
  let html = shown.map(cat => {
    const node = treeData.nodes[cat]; const ik = ikCtr++; ikCat[ik] = cat;
    return `<div class="tree-node" data-key="${ik}"><div class="tree-row" data-key="${ik}">
        <span class="tree-toggle"></span>
        <input type="checkbox" class="tree-cb" data-key="${ik}">
        <span class="tree-lbl" title="${esc(cat)}">${esc(cat)}</span>
        <span class="tree-cnt">${node.total_pages}p · ${fmtWords(node.total_words || 0)}</span>
      </div></div>`;
  }).join("");
  if (!shown.length) html = '<span class="l-dim">No matching category.</span>';
  else if (matches.length > CAP) html += `<div class="l-dim" style="padding:.4rem">… ${matches.length - CAP} more — refine the filter</div>`;
  body.innerHTML = html;
  applyCheckboxStates();
}
function selectedCats() {
  return Object.entries(nodeState).filter(([, s]) => s === 2).map(([c]) => c);
}
function updateGenInfo(preview) {
  const el = document.getElementById("gen-info"); if (!el) return;
  const n = selectedCats().length;
  const total = Object.keys(nodeState).length;
  let html = `${n} / ${total} categories selected`;
  if (preview && !preview.error) {
    html += ` → <b>≈ ${preview.file_count} file(s)</b>`;
    if (preview.splits && preview.splits.length) {
      const CAP = 6;
      const shown = preview.splits.slice(0, CAP).map(esc).join(", ");
      const extra = preview.splits.length > CAP ? ` +${preview.splits.length - CAP} more` : "";
      html += `<span class="warn">⚠ ${preview.splits.length} categories too large, split: ${shown}${extra}</span>`;
    }
  }
  el.innerHTML = html;
}
function schedulePreview() {
  if (!selectedId) return;
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 350);
}
async function runPreview() {
  if (!selectedId) return;
  const sel = selectedCats();
  if (!sel.length) { updateGenInfo({ file_count: 0, splits: [] }); return; }
  const maxFiles = allJobs[selectedId]?.params?.max_files ?? 50;
  const preview = await fetch(`/api/jobs/${selectedId}/preview_packing`, {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ selection: sel, max_files: maxFiles }),
  }).then(r => r.json()).catch(() => null);
  updateGenInfo(preview);
}
function scheduleSaveSelection() {
  if (!selectedId) return;
  clearTimeout(selTimer);
  selTimer = setTimeout(async () => {
    await fetch(`/api/jobs/${selectedId}/selection`, {
      method: "PUT", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ selection: selectedCats() }),
    }).catch(() => {});
  }, 800);
}

async function doGenerate(jobId) {
  const sel = selectedCats();
  if (!sel.length) { showToast("Select at least one category.", {type:"err"}); return; }
  await fetch(`/api/jobs/${jobId}/generate`, {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ selection: sel, formats: null }),
  });
  showToast("Generation started…", {type:"ok"});
  afterLaunch(jobId);
}
async function doGenerateAll(jobId) {
  await fetch(`/api/jobs/${jobId}/generate`, {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ selection: null, formats: null }),
  });
  showToast("Generating the whole wiki…", {type:"ok"});
  afterLaunch(jobId);
}
function afterLaunch(jobId) {
  stopLogStream(); currentStep = -1;
  const term = document.getElementById("terminal"); if (term) term.innerHTML = "";
  startLogStream(jobId, 0);
  refresh();
}

// ── storage ──────────────────────────────────────────────────────────────────
async function loadStorage(jobId) {
  const body = document.getElementById("storage-body");
  if (body) body.innerHTML = '<span class="l-dim">Calculating…</span>';
  const d = await fetch(`/api/jobs/${jobId}/disk`).then(r => r.json()).catch(() => null);
  if (!d || !body) { if (body) body.innerHTML = '<span class="l-err">Calculation failed.</span>'; return; }
  sizeCache[jobId] = d.human;
  body.innerHTML = `
    <div class="storage-bars">
      <div class="storage-row"><span class="lbl">Regenerable data</span><span class="val">${d.data_human}</span></div>
      <div class="storage-row"><span class="lbl">Final files</span><span class="val">${d.output_human}</span></div>
      <div class="storage-row"><span class="lbl">Total</span><span class="val">${d.human}</span></div>
    </div>
    <div class="actions">
      <button class="btn btn-ghost btn-sm" onclick="purge('${jobId}','pdf')">Clear PDF cache</button>
      <button class="btn btn-ghost btn-sm" onclick="purge('${jobId}','intermediate')">Free up space (keep final files)</button>
    </div>
    <div class="kb-hint" style="margin-top:.5rem">"Free up space" deletes the downloaded data; you will need to re-scan to regenerate.</div>`;
}
async function purge(jobId, scope) {
  const r = await fetch(`/api/jobs/${jobId}/purge`, {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ scope }),
  }).then(r => r.json()).catch(() => ({error:"Failed"}));
  if (r.error) { showToast(r.error, {type:"err"}); return; }
  showToast(`${r.freed_human} freed`, {type:"ok"});
  loadStorage(jobId);
  refresh();
}

// ── lifecycle actions ─────────────────────────────────────────────────────────
async function jobAction(id, action) {
  await fetch(`/api/jobs/${id}/${action}`, { method: "POST" });
  if (action === "resume") afterLaunch(id);
  refresh();
}

// ── log stream ─────────────────────────────────────────────────────────────
let streamToken = 0, logBuffer = [], flushScheduled = false;
function startLogStream(jobId, fromPos) {
  stopLogStream();
  const token = ++streamToken;
  const term = document.getElementById("terminal");
  if (!term) return;
  if (fromPos === 0) term.innerHTML = "";
  logBuffer = [];
  logStream = new EventSource(`/api/jobs/${jobId}/logs?from_pos=${fromPos}`);
  logStream.onmessage = (e) => {
    if (token !== streamToken) return;
    if (e.data === "__END__") { logStream.close(); flushLogs(); return; }
    if (e.data) queueLog(e.data);
  };
  logStream.onerror = () => logStream.close();
}
function stopLogStream() {
  streamToken++;
  if (logStream) { logStream.close(); logStream = null; }
  logBuffer = [];
}
function queueLog(text) {
  logBuffer.push(text);
  if (!flushScheduled) { flushScheduled = true; requestAnimationFrame(flushLogs); }
}
function flushLogs() {
  flushScheduled = false;
  const term = document.getElementById("terminal");
  if (!term || !logBuffer.length) return;
  const batch = logBuffer; logBuffer = [];
  const frag = document.createDocumentFragment();
  let lastStep = -1, sawEnd = false;
  for (const text of batch) {
    const div = document.createElement("div");
    for (const [test, cls] of LOG_RULES) if (test(text)) { div.className = cls; break; }
    div.textContent = text || " ";
    frag.appendChild(div);
    const idx = STEPS.findIndex(s => text.includes(s.marker));
    if (idx !== -1) lastStep = idx;
    if (text.includes("PIPELINE COMPLETE")) sawEnd = true;
  }
  term.appendChild(frag);
  term.scrollTop = term.scrollHeight;
  if (lastStep !== -1) { currentStep = lastStep; setStep(lastStep - 1, "done"); setStep(lastStep, "active"); }
  if (sawEnd) setStep(STEPS.length, "done");
}
function setStep(active, state) {
  STEPS.forEach((_, i) => {
    const el = document.getElementById(`step-${i}`); if (!el) return;
    el.classList.remove("active", "done", "error");
    if (i < active) el.classList.add("done");
    else if (i === active) el.classList.add(state);
  });
}

// ── boot ─────────────────────────────────────────────────────────────────────
async function boot() {
  try {
    const d = await fetch("/api/settings").then(r => r.json());
    globalSettings = d.settings; NLM_PLANS = d.plans || {};
  } catch { globalSettings = { ...DEFAULTS }; }
  refresh();
}
boot();
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
