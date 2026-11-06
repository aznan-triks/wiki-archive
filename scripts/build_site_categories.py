#!/usr/bin/env python3
"""
Website mode, step 4: category_groups.json + category_tree.json from the
hierarchy found by site_extract.py (same outputs as build_categories.py).

Usage: build_site_categories.py <categories.json> <hierarchy.json> <category_groups.json>
"""
import json
import sys
from collections import defaultdict

from category_tree import write_outputs

page_cats = json.load(open(sys.argv[1], encoding="utf-8"))          # stem -> [category]
children = json.load(open(sys.argv[2], encoding="utf-8"))["children"]  # category -> [sub-categories]

direct_pages: dict[str, set[str]] = defaultdict(set)
for stem, cats in page_cats.items():
    for cat in cats:
        direct_pages[cat].add(stem)
direct_subcats = {cat: set(subs) for cat, subs in children.items()}
explored = set(direct_pages) | set(direct_subcats) | {s for subs in direct_subcats.values() for s in subs}

print(f"  {len(page_cats)} pages - {len(explored)} categories", flush=True)
write_outputs(direct_pages, direct_subcats, explored, sys.argv[3])
