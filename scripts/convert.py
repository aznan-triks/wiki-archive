#!/usr/bin/env python3
"""
Converts each HTML file to PDF via WeasyPrint, in parallel.
Usage: convert.py <src_dir> <out_dir> [workers]
"""
import sys
import time
import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


def convert_one(args: tuple[str, str]) -> tuple[str, str | None]:
    """Runs in a separate subprocess (WeasyPrint is not thread-safe)."""
    src, out = args
    try:
        from weasyprint import HTML
        HTML(filename=src).write_pdf(out)
        return Path(src).stem, None
    except Exception as exc:
        return Path(src).stem, str(exc)


def main() -> None:
    src_dir  = Path(sys.argv[1])
    out_dir  = Path(sys.argv[2])
    workers  = int(sys.argv[3]) if len(sys.argv) > 3 else min(os.cpu_count() or 2, 4)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(src_dir.glob("*.html"))
    total = len(files)
    if total == 0:
        print("⚠ No HTML files found", flush=True)
        return

    print(f"  {total} files -> {workers} workers", flush=True)

    all_jobs = [(str(f), str(out_dir / f.with_suffix(".pdf").name)) for f in files]
    pending  = [(s, o) for s, o in all_jobs if not Path(o).exists()]
    resumed  = len(all_jobs) - len(pending)

    if resumed:
        print(f"  Resuming: {resumed}/{total} already converted -- {len(pending)} remaining", flush=True)

    if not pending:
        print("✓ All PDFs already exist, nothing to do", flush=True)
        return

    done    = 0
    errors  = 0
    t0      = time.time()

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(convert_one, job): job for job in pending}
        for future in as_completed(futures):
            stem, err = future.result()
            done += 1
            elapsed   = time.time() - t0
            rate      = done / elapsed if elapsed > 0 else 0
            remaining = len(pending) - done
            eta       = remaining / rate if rate > 0 else 0
            eta_str   = f"{int(eta // 60)}m{int(eta % 60):02d}s" if eta >= 60 else f"{int(eta)}s"
            pct       = int((done + resumed) / total * 100)

            if err:
                errors += 1
                print(f"  ⚠ [{done+resumed}/{total}] {stem}: {err}", flush=True)
            else:
                print(f"  ✓ [{done+resumed}/{total}] {pct}% — {stem} — {rate:.1f} p/s — ETA {eta_str}", flush=True)

    elapsed = time.time() - t0
    ok      = done - errors
    print(f"✓ {ok} new + {resumed} resumed in {elapsed:.1f}s"
          + (f" -- {errors} errors" if errors else ""), flush=True)


if __name__ == "__main__":
    main()
