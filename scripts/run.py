#!/usr/bin/env python3
"""
Wiki Archive pipeline orchestrator (native port of run.sh, no bash/coreutils).

Driven entirely by environment variables -- same interface as the old
run.sh -- to remain a drop-in replacement for server.py, both natively
(Windows/Linux/macOS) and in Docker.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

PY = sys.executable
SCRIPTS_DIR = Path(__file__).resolve().parent


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool) -> bool:
    return env(name, "true" if default else "false").lower() == "true"


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


class Step:
    """Replaces bash's begin_step/end_step -- measures and prints the duration."""
    def __enter__(self):
        self._t0 = time.time()
        return self

    def __exit__(self, *exc):
        log(f"✓ Done in {int(time.time() - self._t0)}s")
        return False


def skip_step(msg: str) -> None:
    log(f"↩ Step already complete -- skipped ({msg})")


def human_size(path: Path) -> str:
    total = 0
    if path.is_file():
        total = path.stat().st_size
    elif path.is_dir():
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if total < 1024:
            return f"{total:.0f}{unit}" if unit == "o" else f"{total:.1f}{unit}"
        total /= 1024
    return f"{total:.1f}Po"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """subprocess.run with live (inherited) output, failure = CalledProcessError."""
    log(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kw)


def flatten(src: Path, dest: Path, ext: str) -> int:
    """
    Python port of flatten.sh: flat-copies every *ext* file from src to dest,
    flattening subfolders into the filename and normalizing to ASCII
    (replaces the bash script's iconv//TRANSLIT + sed + cut).
    """
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in sorted(src.rglob(f"*{ext}")):
        if not f.is_file():
            continue
        rel = f.relative_to(src).as_posix()
        ascii_name = unicodedata.normalize("NFKD", rel).encode("ascii", "ignore").decode("ascii")
        flat = ascii_name.replace("/", "__")
        flat = re.sub(r"[^A-Za-z0-9._-]", "_", flat)[:180]
        target = dest / flat
        if target.exists():
            stem, suffix = target.stem, target.suffix
            i = 1
            while (dest / f"{stem}_{i}{suffix}").exists():
                i += 1
            target = dest / f"{stem}_{i}{suffix}"
        shutil.copy2(f, target)
        count += 1
    log(f"✓ Flattened: {count} files")
    return count


def wiki_slug(url: str) -> str:
    host = urlparse(url).hostname or url
    return re.sub(r"[^\w.-]", "_", host)


def config_field(config_json: Path, *keys: str) -> str:
    try:
        data = json.loads(config_json.read_text(encoding="utf-8"))
    except Exception:
        return ""
    for k in keys:
        v = data.get(k)
        if v:
            return v
    return ""


def api_url_from_config(config_json: Path) -> str:
    try:
        data = json.loads(config_json.read_text(encoding="utf-8"))
    except Exception:
        return ""
    api = data.get("api") or ""
    if not api and data.get("index"):
        api = data["index"].replace("index.php", "api.php")
    return api


def main() -> int:
    wiki_api = env("WIKI_API")
    job_dir_s = env("JOB_DIR")
    if not wiki_api:
        log("ERROR: WIKI_API variable missing")
        return 1
    if not job_dir_s:
        log("ERROR: JOB_DIR variable missing")
        return 1
    job_dir = Path(job_dir_s)

    namespaces = env("NAMESPACES", "0")
    delay = env("DELAY", "0.5")
    max_pdf = env("MAX_PDF", "100")
    images = env_bool("IMAGES", True)
    clean = env_bool("CLEAN", False)
    rerender = env_bool("RERENDER", False)
    workers = env("WORKERS", "4")
    force = env_bool("FORCE", True)
    phase = env("PHASE", "all")               # all | scan | generate
    max_files = env("MAX_FILES", "0")
    notebooklm_max_words = env("NOTEBOOKLM_MAX_WORDS", "500000")
    dedup = env_bool("DEDUP", False)
    cat_workers = env("CAT_WORKERS", "8")
    selection_file = Path(env("SELECTION_FILE", str(job_dir / "selection.json")))
    data_dir = Path(env("DATA_DIR", "/data"))

    export_formats = env("EXPORT_FORMATS", "pdf")
    if export_formats == "all":
        export_formats = "pdf,md,txt"
    formats_list = [f for f in export_formats.split(",") if f]
    want_pdf = "pdf" in formats_list
    doc_formats = ",".join(f for f in formats_list if f != "pdf")
    want_docs = bool(doc_formats)

    dump_dir = job_dir / "dump"
    html_dir = job_dir / "html"
    pdf_dir = job_dir / "pdf"
    flat_dir = job_dir / "flat"

    slug = wiki_slug(wiki_api)
    out_dir = data_dir / "output" / slug

    print("=" * 44)
    print("  Wiki Archive Pipeline")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 44)
    log(f"Wiki URL    : {wiki_api}")
    log(f"Output      : {out_dir}")
    log(f"Job dir     : {job_dir}")
    log(f"Phase       : {phase}")
    log(f"Namespaces  : {namespaces} | Delay: {delay}s | Images: {images}")
    log(f"PDF workers : {workers} | Max PDF : {max_pdf} | Force : {force}")
    log(f"Formats     : {export_formats} | Max files : {max_files} | Dedup : {dedup}")
    try:
        free = shutil.disk_usage(job_dir if job_dir.exists() else job_dir.parent).free
        log(f"Disk        : {free / (1024**3):.1f} GB free")
    except Exception:
        log("Disk        : unknown")
    print()

    # ── cleanup depending on mode (skipped for generate) ────────────────────────
    if phase != "generate":
        if clean:
            log("⚠ Full cleanup -- removing all previous data")
            for d in (dump_dir, html_dir, pdf_dir, flat_dir, out_dir):
                shutil.rmtree(d, ignore_errors=True)
        elif rerender:
            log("♻ Re-rendering -- removing HTML/PDF (dump kept)")
            for d in (html_dir, pdf_dir, flat_dir, out_dir):
                shutil.rmtree(d, ignore_errors=True)

    # ── 1. dump ──────────────────────────────────────────────────────────────────
    print()
    print("━━━ [1/5] WIKI DUMP ━━━")

    xml_file = None
    config_json = dump_dir / "config.json"
    if phase == "generate":
        log("↩ Skipped (generate phase)")
    else:
        existing_xml = sorted(p for p in dump_dir.glob("*.xml") if not p.name.endswith(".7z")) if dump_dir.exists() else []
        if existing_xml and config_json.exists():
            xml_file = existing_xml[0]
            skip_step(f"XML found: {xml_file} ({human_size(xml_file)})")
        else:
            with Step():
                log("Detecting MediaWiki access type...")
                detect = subprocess.run(
                    [PY, str(SCRIPTS_DIR / "detect_wiki.py"), wiki_api],
                    capture_output=True, text=True,
                )
                if detect.stderr:
                    for line in detect.stderr.splitlines():
                        log(line)
                if detect.returncode != 0 or not detect.stdout.strip():
                    log("⚠ Wiki detection failed")
                    return 1
                access_flag, wiki_url = detect.stdout.strip().split(maxsplit=1)
                log(f"Access detected: {access_flag} {wiki_url}")

                if not shutil.which("wikiteam3dumpgenerator"):
                    log("ERROR: wikiteam3dumpgenerator not found in PATH (pip install wikiteam3?)")
                    return 1

                dump_args = [
                    "wikiteam3dumpgenerator",
                    access_flag, wiki_url,
                    "--xml", "--curonly",
                    "--namespaces", namespaces,
                    "--delay", delay,
                    "--retries", "5",
                    "--path", str(dump_dir),
                ]
                if images:
                    dump_args.append("--images")
                if force:
                    dump_args.append("--force")

                if config_json.exists():
                    saved_url = config_field(config_json, "api", "index")
                    if saved_url == wiki_url:
                        log(f"Valid resume ({wiki_url})")
                        dump_args.append("--resume")
                    else:
                        log(f"Stale config ({saved_url} != {wiki_url}) -> new dump")
                        shutil.rmtree(dump_dir, ignore_errors=True)

                run(dump_args)

                log(f"Contents of {dump_dir}:")
                if dump_dir.exists():
                    for f in sorted(dump_dir.rglob("*")):
                        if f.is_file():
                            log(f"  [{human_size(f)}] {f}")

                existing_xml = sorted(p for p in dump_dir.glob("*.xml") if not p.name.endswith(".7z"))
                if not existing_xml:
                    log(f"⚠ No .xml file found in {dump_dir}")
                    return 1
                xml_file = existing_xml[0]
                log(f"XML file: {xml_file} ({human_size(xml_file)})")

    # ── 2. HTML extraction ──────────────────────────────────────────────────────
    print()
    print("━━━ [2/5] HTML EXTRACTION ━━━")

    api_url = api_url_from_config(config_json) if config_json.exists() else ""
    categories_file = job_dir / "categories.json"

    html_count = len(list(html_dir.glob("*.html"))) if html_dir.exists() else 0
    if phase == "generate":
        log("↩ Skipped (generate phase)")
    elif html_count > 0:
        skip_step(f"{html_count} HTML files already present")
    else:
        with Step():
            if api_url:
                log(f"Render API: {api_url}")
            else:
                log("⚠ API not found in config.json -- basic rendering (no templates)")
            log(f"Source: {xml_file} -> {html_dir}")
            run([PY, str(SCRIPTS_DIR / "extract.py"), str(xml_file), str(html_dir), api_url, delay, str(categories_file)])
            html_count = len(list(html_dir.glob("*.html")))
            log(f"{html_count} HTML files generated")

    # ── 3. PDF conversion ────────────────────────────────────────────────────────
    print()
    print("━━━ [3/5] PDF CONVERSION ━━━")

    pdf_count = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0
    if phase in ("scan", "generate"):
        log(f"↩ Skipped (phase {phase})")
    elif not want_pdf:
        log("Skipped -- PDF format not requested")
    elif pdf_count >= html_count and pdf_count > 0:
        skip_step(f"{pdf_count} PDFs already present ({human_size(pdf_dir)})")
    else:
        with Step():
            log(f"Source: {html_dir} -> {pdf_dir} ({workers} workers)")
            run([PY, str(SCRIPTS_DIR / "convert.py"), str(html_dir), str(pdf_dir), workers])
            pdf_count = len(list(pdf_dir.glob("*.pdf")))
            log(f"{pdf_count} PDFs -- total size: {human_size(pdf_dir)}")

    # ── 4. category hierarchy ───────────────────────────────────────────────────
    print()
    print("━━━ [4/5] CATEGORY HIERARCHY ━━━")

    cat_groups = job_dir / "category_groups.json"
    tree_file = job_dir / "category_tree.json"

    if phase == "generate":
        log("↩ Skipped (generate phase)")
    else:
        with Step():
            page_words = job_dir / "page_words.json"
            if html_dir.exists():
                log("Measuring page word counts...")
                try:
                    run([PY, str(SCRIPTS_DIR / "measure_words.py"), str(html_dir), str(page_words)])
                except subprocess.CalledProcessError:
                    log("⚠ Word count measurement failed (weights shown as 0)")

            if api_url and categories_file.exists():
                log(f"Building hierarchy via API ({cat_workers} in parallel)...")
                os.environ["CAT_WORKERS"] = cat_workers
                run([PY, str(SCRIPTS_DIR / "build_categories.py"), api_url, str(categories_file), str(cat_groups)])
            else:
                log("⚠ No API or categories.json missing -- direct grouping without hierarchy")
                page_cats = json.loads(categories_file.read_text(encoding="utf-8"))
                groups = defaultdict(list)
                for stem, cats in page_cats.items():
                    for cat in (cats or ["Divers"]):
                        groups[cat].append(stem)
                cat_groups.write_text(
                    json.dumps({k: sorted(v) for k, v in groups.items()}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                log(f"  {len(groups)} categories")

    # ── stop after scan ──────────────────────────────────────────────────────────
    if phase == "scan":
        print()
        print("=" * 44)
        print(f"  ✓ SCAN COMPLETE -- {datetime.now():%Y-%m-%d %H:%M:%S}")
        print(f"  Tree in {tree_file}")
        print("=" * 44)
        return 0

    # ── 4.5 selection then grouping ─────────────────────────────────────────────
    add_divers = True

    if phase == "generate" and selection_file.exists() and selection_file.stat().st_size > 0:
        selected_groups = job_dir / "category_groups_selected.json"
        groups = json.loads(cat_groups.read_text(encoding="utf-8"))
        sel = set(json.loads(selection_file.read_text(encoding="utf-8")) or [])
        out = {k: v for k, v in groups.items() if k in sel} if sel else groups
        selected_groups.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"  Selection: {len(out)}/{len(groups)} categories kept")
        cat_groups = selected_groups
        add_divers = False

    if tree_file.exists() and (int(max_files) > 0 or dedup):
        print()
        print(f"━━━ [4.5] GROUPING (MAX_FILES={max_files}, DEDUP={dedup}) ━━━")
        with Step():
            packed_groups = job_dir / "category_groups_packed.json"
            os.environ["MAX_FILES"] = max_files
            os.environ["NOTEBOOKLM_MAX_WORDS"] = notebooklm_max_words
            os.environ["DEDUP"] = "true" if dedup else "false"
            run([PY, str(SCRIPTS_DIR / "pack_files.py"), str(cat_groups), str(tree_file), str(packed_groups), max_files])
            cat_groups = packed_groups

    # ── 5. per-category file production ─────────────────────────────────────────
    print()
    print("━━━ [5/5] PER-CATEGORY FILE PRODUCTION ━━━")
    with Step():
        log(f"Cleaning previous output: {out_dir}")
        shutil.rmtree(flat_dir, ignore_errors=True)
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        os.environ["ADD_DIVERS"] = "true" if add_divers else "false"

        if want_pdf:
            log(f"PDF: one file per category (max {max_pdf} pages)")
            flatten(pdf_dir, flat_dir, ".pdf")
            run([PY, str(SCRIPTS_DIR / "merge_pdf.py"), str(flat_dir), str(out_dir), max_pdf, str(cat_groups)])

        if want_docs:
            log(f"Text ({doc_formats}): one file per category")
            try:
                run([PY, str(SCRIPTS_DIR / "export_categories.py"), str(html_dir), str(cat_groups), str(out_dir), doc_formats])
            except subprocess.CalledProcessError:
                log("⚠ Text export failed (PDFs unaffected)")

    print()
    print("=" * 44)
    print(f"  ✓ PIPELINE COMPLETE -- {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Files in {out_dir}")
    print("=" * 44)
    produced = sorted(out_dir.glob("*")) if out_dir.exists() else []
    if produced:
        for f in produced:
            if f.is_file():
                print(f"  {human_size(f):>8}  {f.name}")
    else:
        print("  (no files generated)")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        log(f"⚠ Failure in {exc.cmd[0] if exc.cmd else '?'} (code {exc.returncode})")
        sys.exit(exc.returncode or 1)
