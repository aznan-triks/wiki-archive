#!/usr/bin/env python3
"""
Groups categories into at most MAX_FILES coherent files (workstream B).

Deterministic logic, guided by the tree:
  1. Split any group that exceeds the limit (words or pages) into numbered parts.
  2. Merge parent->child if the result fits under the limit (semantic).
  3. If too many files remain: merge the two smallest until
     <= MAX_FILES or blocked (per-file limit cannot be satisfied).

The `pack()` function is reused by server.py (live preview) AND by the CLI
(actual generation) -> single source, no drift between preview and result.

Output: { filename -> [stems] }  (same format as category_groups.json)

Usage CLI: pack_files.py <category_groups.json> <category_tree.json> <out.json> [max_files]
  env: MAX_FILES, NOTEBOOKLM_MAX_WORDS, MAX_PAGES_PER_FILE
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _words_of(stems, page_words: dict[str, int]) -> int:
    return sum(page_words.get(s, 0) for s in stems)


def dedup_groups(groups: dict[str, list[str]], tree: dict) -> dict[str, list[str]]:
    """Assigns each page to ONE single category: the most specific one.

    "Most specific" = the one containing the fewest pages overall (the tree
    leaves). Avoids duplicating a page across all its parent categories ->
    saves the NotebookLM quota. Deterministic (ties broken by name).
    """
    from collections import defaultdict
    nodes = tree.get("nodes", {})

    def specificity(cat: str) -> int:
        # total_pages from the tree; falls back to the current group's size
        return nodes.get(cat, {}).get("total_pages", len(groups.get(cat, [])))

    page_cats: dict[str, list[str]] = defaultdict(list)
    for cat, pages in groups.items():
        for p in pages:
            page_cats[p].append(cat)

    out: dict[str, list[str]] = defaultdict(list)
    for page, cats in page_cats.items():
        best = min(cats, key=lambda c: (specificity(c), c))
        out[best].append(page)
    return {c: sorted(set(ps)) for c, ps in out.items()}


def _exceeds(stems, page_words, max_words: int, max_pages: int) -> bool:
    if max_words and _words_of(stems, page_words) > max_words:
        return True
    if max_pages and len(stems) > max_pages:
        return True
    return False


def _split_large(name: str, pages: list[str], page_words, max_words: int,
                 max_pages: int) -> dict[str, list[str]]:
    """Splits an oversized group into parts, at page boundaries."""
    if not _exceeds(pages, page_words, max_words, max_pages):
        return {name: pages}
    parts: list[list[str]] = []
    cur: list[str] = []
    cur_words = 0
    for stem in pages:
        w = page_words.get(stem, 0)
        over_words = max_words and cur and (cur_words + w) > max_words
        over_pages = max_pages and cur and (len(cur) + 1) > max_pages
        if over_words or over_pages:
            parts.append(cur)
            cur, cur_words = [], 0
        cur.append(stem)
        cur_words += w
    if cur:
        parts.append(cur)
    if len(parts) == 1:
        return {name: parts[0]}
    return {f"{name} (part {i + 1})": part for i, part in enumerate(parts)}


def pack(groups: dict[str, list[str]],
         tree: dict,
         page_words: dict[str, int],
         max_files: int,
         max_words: int = 500_000,
         max_pages: int = 0,
         dedup: bool = False,
         log=lambda *a, **k: None) -> dict[str, list[str]]:
    """Groups `groups` into <= max_files files. Returns { name -> [stems] }."""
    nodes: dict[str, dict] = tree.get("nodes", {})

    # 0. Deduplication: each page in a single category (the most specific one)
    if dedup:
        before = sum(len(v) for v in groups.values())
        groups = dedup_groups(groups, tree)
        after = sum(len(v) for v in groups.values())
        log(f"  Deduplication: {before} -> {after} page assignments")

    # 1. Split oversized groups
    packed: dict[str, list[str]] = {}
    for cat, stems in groups.items():
        packed.update(_split_large(cat, sorted(set(stems)), page_words,
                                   max_words, max_pages))

    if max_files <= 0:
        return packed

    # 2. Tree-guided merging (parent absorbs child if it fits)
    changed = True
    while changed and len(packed) > max_files:
        changed = False
        for parent, node in nodes.items():
            if parent not in packed:
                continue
            for child in node.get("children", []):
                if child not in packed or child == parent:
                    continue
                merged = sorted(set(packed[parent]) | set(packed[child]))
                if not _exceeds(merged, page_words, max_words, max_pages):
                    packed[parent] = merged
                    del packed[child]
                    log(f"  ^ {child!r} merged into {parent!r} ({len(merged)} pages)")
                    changed = True
                    break
            if changed:
                break

    # 3. Greedy merging of the smallest ones
    while len(packed) > max_files:
        by_size = sorted(packed.items(), key=lambda x: _words_of(x[1], page_words) or len(x[1]))
        n1, p1 = by_size[0]
        n2, p2 = by_size[1]
        merged = sorted(set(p1) | set(p2))
        if _exceeds(merged, page_words, max_words, max_pages):
            log(f"  ⚠ Cannot go below {len(packed)} groups "
                f"(merging {n1!r}+{n2!r} would exceed the per-file limit)")
            break
        del packed[n1]
        del packed[n2]
        merged_name = n1
        for cat, node in nodes.items():
            kids = node.get("children", [])
            if n1 in kids and n2 in kids:
                merged_name = cat
                break
        if merged_name == n1:
            merged_name = f"{n1}+{n2}"
        packed[merged_name] = merged
        log(f"  <- {n1!r} + {n2!r} -> {merged_name!r} ({len(merged)} pages)")

    return packed


def main(argv: list[str]) -> int:
    groups_file = Path(argv[0])
    tree_file   = Path(argv[1])
    out_file    = Path(argv[2])
    max_files   = int(os.getenv("MAX_FILES", argv[3] if len(argv) > 3 else "50"))
    max_words   = int(os.getenv("NOTEBOOKLM_MAX_WORDS", "500000"))
    max_pages   = int(os.getenv("MAX_PAGES_PER_FILE", "0"))
    dedup       = os.getenv("DEDUP", "false").lower() == "true"

    groups = json.loads(groups_file.read_text(encoding="utf-8"))
    tree   = json.loads(tree_file.read_text(encoding="utf-8")) if tree_file.exists() else {}

    words_path = groups_file.parent / "page_words.json"
    page_words = json.loads(words_path.read_text(encoding="utf-8")) if words_path.exists() else {}

    print(f"  Input: {len(groups)} groups, MAX_FILES={max_files}, "
          f"MAX_WORDS={max_words}, MAX_PAGES={max_pages or 'unlimited'}, DEDUP={dedup}", flush=True)

    packed = pack(groups, tree, page_words, max_files, max_words, max_pages,
                  dedup=dedup, log=lambda m: print(m, flush=True))

    out_file.write_text(json.dumps(packed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {len(packed)} group(s) -> {out_file}", flush=True)
    for name, stems in sorted(packed.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {name}: {len(stems)} pages, {_words_of(stems, page_words)} words", flush=True)
    if len(packed) > 10:
        print(f"  ... ({len(packed) - 10} more)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
