#!/usr/bin/env python3
"""
Merges PDFs by MediaWiki category.

Reads categories.json : { "safe_filename": ["Cat1", "Cat2", ...] }
Creates one PDF per category containing all the pages in that category.
Pages without a category go into "Divers".
A page in multiple categories appears in each of the corresponding PDFs.

Usage: merge_pdf.py <flat_dir> <out_dir> <max_pages_per_pdf> [categories.json]
"""
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pikepdf

# Selection and grouping are applied upstream (run.sh): this script consumes
# the provided groups directly. ADD_DIVERS controls whether pages without a
# category are added (disabled when a selection is active).
ADD_DIVERS = os.getenv("ADD_DIVERS", "true").lower() != "false"

src_dir    = Path(sys.argv[1])   # /data/jobs/.../flat
out_dir    = Path(sys.argv[2])   # /data/output/wiki.hostname
max_pages  = int(sys.argv[3]) if len(sys.argv) > 3 else 500
groups_file = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(sys.argv[1]).parent / "category_groups.json"

out_dir.mkdir(parents=True, exist_ok=True)

# -- index available PDFs -----------------------------------------------------
available: dict[str, Path] = {}   # safe_stem -> Path
for pdf in sorted(src_dir.glob("*.pdf")):
    available[pdf.stem] = pdf

print(f"  {len(available)} PDFs in {src_dir}", flush=True)

# -- load category groups (full hierarchy) ------------------------------------
cat_groups: dict[str, list[Path]] = defaultdict(list)

if groups_file.exists():
    try:
        groups: dict[str, list[str]] = json.loads(groups_file.read_text(encoding="utf-8"))
        print(f"  category_groups.json loaded -- {len(groups)} categories", flush=True)
        for cat, stems in groups.items():
            for stem in stems:
                if stem in available:
                    cat_groups[cat].append(available[stem])
    except Exception as e:
        print(f"  ⚠ Could not read category_groups.json: {e}", flush=True)
else:
    print(f"  ⚠ category_groups.json not found -- everything goes into 'Divers'", flush=True)

# Pages without a category -> Divers (unless a selection is active: ADD_DIVERS=false)
if ADD_DIVERS:
    categorized = {p for paths in cat_groups.values() for p in paths}
    for pdf in available.values():
        if pdf not in categorized:
            cat_groups["Divers"].append(pdf)

print(f"  {len(cat_groups)} category(ies) found", flush=True)

# -- name the output files -----------------------------------------------------
def cat_to_filename(cat: str) -> str:
    safe = re.sub(r"[^\w\s\-]", "_", cat).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe[:80] + ".pdf"

# -- merge ----------------------------------------------------------------------
ok = errors = 0

for cat, files in sorted(cat_groups.items()):
    out_path = out_dir / cat_to_filename(cat)
    files    = sorted(set(files))   # deduplicate (a page can point to it twice)

    # Split if too many pages (NotebookLM safety limit)
    chunks = [files[i:i+max_pages] for i in range(0, len(files), max_pages)]
    for idx, chunk in enumerate(chunks):
        if len(chunks) > 1:
            stem     = out_path.stem
            out_path = out_dir / f"{stem}_part{idx+1}.pdf"

        try:
            merged = pikepdf.Pdf.new()
            page_count = 0
            for p in chunk:
                try:
                    src = pikepdf.Pdf.open(p)
                    merged.pages.extend(src.pages)
                    page_count += len(src.pages)
                except Exception as e:
                    print(f"    ⚠ skipped {p.name}: {e}", flush=True)
            merged.save(out_path)
            size_mb = round(out_path.stat().st_size / 1_048_576, 2)
            print(f"  ✓ {out_path.name}  ({len(chunk)} articles, {page_count} pages, {size_mb} MB)", flush=True)
            ok += 1
        except Exception as e:
            print(f"  ✗ {cat}: {e}", flush=True)
            errors += 1

print(f"\n✓ {ok} PDF(s) in {out_dir}" + (f" -- {errors} error(s)" if errors else ""), flush=True)
