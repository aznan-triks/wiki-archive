#!/usr/bin/env python3
"""
Merges per-page PDFs into one PDF per MediaWiki category.

Reads category_groups.json : { "Category": ["page_stem", ...], ... }
Pages without a category go into MISC_CATEGORY ("Misc" by default).
A page in multiple categories appears in each of the corresponding PDFs.
Categories larger than <max_pages_per_pdf> pages are split into
"<Category>_part1.pdf", "<Category>_part2.pdf", ...

Usage: merge_pdf.py <flat_dir> <out_dir> [max_pages_per_pdf] [category_groups.json]
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import pikepdf

from wiki_names import MISC_CATEGORY, cat_stem  # same dir, on sys.path

# Selection and grouping are applied upstream (run.py): this script consumes
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
    except Exception as e:
        # Fail Fast: continuing would silently replace the per-category PDFs
        # with one giant "everything" PDF.
        print(f"✗ {groups_file} unreadable: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    print(f"  category_groups.json loaded -- {len(groups)} categories", flush=True)
    for cat, stems in groups.items():
        for stem in stems:
            if stem in available:
                cat_groups[cat].append(available[stem])
else:
    print(f"  ⚠ category_groups.json not found -- everything goes into "
          f"'{MISC_CATEGORY}'", flush=True)

# Pages without a category -> MISC_CATEGORY (skipped when a selection is active:
# ADD_DIVERS=false, so the export matches the user's selection exactly)
if ADD_DIVERS:
    categorized = {p for paths in cat_groups.values() for p in paths}
    for pdf in available.values():
        if pdf not in categorized:
            cat_groups[MISC_CATEGORY].append(pdf)

print(f"  {len(cat_groups)} category(ies) found", flush=True)

# -- output naming ---------------------------------------------------------------


def output_name(cat: str, idx: int, total: int) -> str:
    """File name of chunk `idx` (0-based) when `cat` is split in `total` PDFs.

    Regression: the merge loop used to reassign the output path per chunk, so
    part 2+ chained suffixes ("X_part1_part2.pdf"). The base name is now fixed.
    """
    stem = cat_stem(cat)
    return f"{stem}.pdf" if total <= 1 else f"{stem}_part{idx + 1}.pdf"

# -- merge ----------------------------------------------------------------------
ok = errors = 0

for cat, files in sorted(cat_groups.items()):
    files    = sorted(set(files))   # deduplicate (a page can point to it twice)

    # Split if too many pages (NotebookLM safety limit)
    chunks = [files[i:i+max_pages] for i in range(0, len(files), max_pages)]
    for idx, chunk in enumerate(chunks):
        out_path = out_dir / output_name(cat, idx, len(chunks))
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
            print(f"  ✗ {cat}: {e}", file=sys.stderr, flush=True)
            errors += 1

print(f"\n✓ {ok} PDF(s) in {out_dir}" + (f" -- {errors} error(s)" if errors else ""), flush=True)
if errors:
    sys.exit(1)
