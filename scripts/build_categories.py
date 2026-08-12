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
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests

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

def title_to_stem(title: str) -> str:
    return re.sub(r"[^\w\s\-]", "_", title)[:120]

# ── parallel BFS: discover the whole tree ──────────────────────────────────────
# direct_pages[cat]  = stems of pages directly in cat
# direct_subcats[cat] = names of direct subcategories of cat
direct_pages:  dict[str, set[str]]  = defaultdict(set)
direct_subcats: dict[str, set[str]] = defaultdict(set)


def fetch_category(cat: str) -> tuple[str, set[str], set[str]]:
    """Queries the API for a category. Returns (cat, pages, subcats)."""
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
                    pages.add(title_to_stem(m["title"]))
                elif m["ns"] == 14:
                    subs.add(m["title"].split(":", 1)[-1])
            if "continue" not in data:
                break
            params.update(data["continue"])
    except Exception as e:
        print(f"  ⚠ {cat}: {e}", flush=True)
    return cat, pages, subs


explored: set[str] = set()
frontier: set[str] = set(all_known_cats)
done = 0

with ThreadPoolExecutor(max_workers=CAT_WORKERS) as pool:
    while frontier:
        todo = [c for c in frontier if c not in explored]
        explored.update(todo)
        frontier = set()
        for cat, pages, subs in pool.map(fetch_category, todo):
            direct_pages[cat]  |= pages
            direct_subcats[cat] |= subs
            for sub in subs:
                if sub not in explored:
                    frontier.add(sub)
        done += len(todo)
        print(f"  ... {done} categories explored ({len(frontier)} pending)", flush=True)

# Add pages from categories.json (consistency with what we extracted)
for stem, cats in page_cats.items():
    for cat in cats:
        direct_pages[cat].add(stem)

# ── propagation: all_pages(cat) = direct pages + all_pages(subcat) ────────────
all_cats = list(explored)
full_pages: dict[str, set[str]] = {}

def collect(cat: str, seen: set[str]) -> set[str]:
    """Returns all pages in cat and its descendants (no loops)."""
    if cat in full_pages:
        return full_pages[cat]
    if cat in seen:
        return set()   # cycle detected
    seen = seen | {cat}
    result = set(direct_pages.get(cat, set()))
    for sub in direct_subcats.get(cat, set()):
        result |= collect(sub, seen)
    full_pages[cat] = result
    return result

print("  Propagating hierarchy...", flush=True)
for cat in all_cats:
    collect(cat, set())

# ── write category_groups.json ──────────────────────────────────────────────
result = {cat: sorted(stems) for cat, stems in full_pages.items() if stems}

with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

total_entries = sum(len(v) for v in result.values())
print(f"✓ {len(result)} categories - {total_entries} total entries -> {OUT_FILE}", flush=True)

# Readable summary
for cat, stems in sorted(result.items(), key=lambda x: -len(x[1]))[:15]:
    print(f"  {cat}: {len(stems)} pages", flush=True)
if len(result) > 15:
    print(f"  ... ({len(result) - 15} more categories)", flush=True)

# ── write category_tree.json (workstream D) ────────────────────────────────────
from pathlib import Path as _Path

tree_file = _Path(OUT_FILE).parent / "category_tree.json"

# Word weight per page (measured by measure_words.py; absent = 0)
words_file = _Path(OUT_FILE).parent / "page_words.json"
page_words: dict[str, int] = {}
if words_file.exists():
    try:
        page_words = json.loads(words_file.read_text(encoding="utf-8"))
    except Exception:
        page_words = {}

def words_of(stems) -> int:
    return sum(page_words.get(s, 0) for s in stems)

# Roots = categories that are not a subcategory of any other
all_child_cats: set[str] = set()
for subs in direct_subcats.values():
    all_child_cats.update(subs)
roots = sorted(c for c in all_cats if c not in all_child_cats and c in full_pages)

tree_nodes: dict[str, dict] = {}
for cat in all_cats:
    if cat not in full_pages:
        continue
    pages_all = full_pages.get(cat, set())
    tree_nodes[cat] = {
        "children":    sorted(direct_subcats.get(cat, set())),
        "pages":       sorted(direct_pages.get(cat, set())),
        "total_pages": len(pages_all),
        "total_words": words_of(pages_all),
    }

tree = {"roots": roots, "nodes": tree_nodes}
with open(tree_file, "w", encoding="utf-8") as f:
    json.dump(tree, f, ensure_ascii=False, indent=2)

print(f"✓ Tree: {len(tree_nodes)} nodes, {len(roots)} root(s) -> {tree_file}", flush=True)
