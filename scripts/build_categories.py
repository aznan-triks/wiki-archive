#!/usr/bin/env python3
"""
Builds the full category hierarchy via the MediaWiki API.

Strategy:
  1. BFS over all known categories -> discover direct pages + subcategories
  2. Propagate upward: a page in Pistols also appears in Weapons
  3. Write category_groups.json: { "Weapons": ["C96", ...], "Pistols": [...] }

Usage: build_categories.py <api_url> <categories.json> <category_groups.json>
"""
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests

from category_tree import write_outputs
from wiki_names import page_stem  # scripts/ dir is on sys.path (run as a script)

API_URL   = sys.argv[1].strip()
CATS_FILE = sys.argv[2]
OUT_FILE  = sys.argv[3]

# Number of categories queried in parallel (configurable). Scanning a large
# wiki (thousands of categories) drops from ~20 min to ~1-2 min.
CAT_WORKERS = max(1, int(os.getenv("CAT_WORKERS", "8")))

# ── load direct categories ─────────────────────────────────────────────────────
with open(CATS_FILE, encoding="utf-8") as f:
    page_cats: dict[str, list[str]] = json.load(f)   # stem -> [cat, ...]

all_known_cats: set[str] = {c for cats in page_cats.values() for c in cats}
print(f"  {len(page_cats)} pages - {len(all_known_cats)} starting categories", flush=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "wikiteam3/4.4.8 (https://github.com/saveweb/wikiteam3)"})

# ── parallel BFS: discover the whole tree ──────────────────────────────────────
# direct_pages[cat]  = stems of pages directly in cat
# direct_subcats[cat] = names of direct subcategories of cat
direct_pages:  dict[str, set[str]]  = defaultdict(set)
direct_subcats: dict[str, set[str]] = defaultdict(set)


def fetch_category(cat: str) -> tuple[str, set[str], set[str], str | None]:
    """Queries the API for a category. Returns (cat, pages, subcats, error)."""
    pages: set[str]  = set()
    subs:  set[str]  = set()
    params = {
        "action":  "query",
        "list":    "categorymembers",
        "cmtitle": f"Category:{cat}",
        "cmtype":  "page|subcat",
        "cmlimit": "500",
        "format":  "json",
    }
    try:
        while True:
            r    = SESSION.get(API_URL, params=params, timeout=20)
            data = r.json()
            for m in data.get("query", {}).get("categorymembers", []):
                if m["ns"] == 0:
                    pages.add(page_stem(m["title"]))
                elif m["ns"] == 14:
                    subs.add(m["title"].split(":", 1)[-1])
            if "continue" not in data:
                break
            params.update(data["continue"])
    except Exception as e:
        # The error is returned, not swallowed: the caller fails the whole
        # step -- a partially-read category silently drops pages from the
        # generated files (data corruption, per Fail Fast rule).
        return cat, pages, subs, str(e)
    return cat, pages, subs, None


explored: set[str] = set()
frontier: set[str] = set(all_known_cats)
done   = 0
failed: dict[str, str] = {}

with ThreadPoolExecutor(max_workers=CAT_WORKERS) as pool:
    while frontier:
        todo = [c for c in frontier if c not in explored]
        explored.update(todo)
        frontier = set()
        for cat, pages, subs, err in pool.map(fetch_category, todo):
            if err:
                failed[cat] = err
            direct_pages[cat]  |= pages
            direct_subcats[cat] |= subs
            for sub in subs:
                if sub not in explored:
                    frontier.add(sub)
        done += len(todo)
        print(f"  ... {done} categories explored ({len(frontier)} pending)", flush=True)

if failed:
    for cat, err in list(failed.items())[:10]:
        print(f"  ✗ {cat}: {err}", flush=True)
    more = f" (+{len(failed) - 10} more)" if len(failed) > 10 else ""
    print(f"✗ Category hierarchy scan failed: {len(failed)} categories could not be "
          f"read{more}.\n  The grouping would be silently incomplete -- fix the "
          f"wiki access and re-run the job (Fail Fast).", flush=True)
    sys.exit(1)

# Add pages from categories.json (consistency with what we extracted)
for stem, cats in page_cats.items():
    for cat in cats:
        direct_pages[cat].add(stem)

write_outputs(direct_pages, direct_subcats, explored, OUT_FILE)
