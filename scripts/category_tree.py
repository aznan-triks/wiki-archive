#!/usr/bin/env python3
"""
Category hierarchy -> category_groups.json + category_tree.json.

Shared by build_categories.py (MediaWiki, hierarchy read from the API) and
build_site_categories.py (website mode, hierarchy read from the pages), so
both sources feed the selection screen and the file packing the same way.
"""
from __future__ import annotations

import json
from pathlib import Path


def write_outputs(direct_pages: dict[str, set[str]],
                  direct_subcats: dict[str, set[str]],
                  explored: set[str], out_file: str | Path) -> None:
    """Propagates pages up the hierarchy (a page in Pistols also appears in
    Weapons), then writes `out_file` (category -> pages) and, next to it,
    category_tree.json (roots + per-category children/pages/word weight)."""
    out_file = Path(out_file)

    # ── propagation: all_pages(cat) = direct pages + all_pages(subcat) ────────
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

    # ── write category_groups.json ──────────────────────────────────────────
    result = {cat: sorted(stems) for cat, stems in full_pages.items() if stems}

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total_entries = sum(len(v) for v in result.values())
    print(f"✓ {len(result)} categories - {total_entries} total entries -> {out_file}", flush=True)

    # Readable summary
    for cat, stems in sorted(result.items(), key=lambda x: -len(x[1]))[:15]:
        print(f"  {cat}: {len(stems)} pages", flush=True)
    if len(result) > 15:
        print(f"  ... ({len(result) - 15} more categories)", flush=True)

    # ── write category_tree.json (workstream D) ─────────────────────────────
    tree_file = out_file.parent / "category_tree.json"

    # Word weight per page (measured by measure_words.py; absent = 0)
    words_file = out_file.parent / "page_words.json"
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
