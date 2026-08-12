#!/usr/bin/env python3
"""
Measures the word weight of each page (workstream B/D).

Reads html/*.html, extracts the visible text (quick regex strip -- no need
for perfect cleanup for a simple word count), counts words, and writes
page_words.json : { "safe_stem": word_count, ... }

Reused by:
  - build_categories.py -> total_words per category in category_tree.json
  - pack_files.py        -> grouping under the NotebookLM limit (words)

Usage: measure_words.py <html_dir> <page_words.json>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HTML_DIR = Path(sys.argv[1])
OUT_FILE = Path(sys.argv[2])

if not HTML_DIR.exists():
    print(f"✗ HTML directory not found: {HTML_DIR}", file=sys.stderr)
    sys.exit(1)

# Quick strip: remove scripts/styles, then all tags, then count.
_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAGS         = re.compile(r"<[^>]+>")
_WORD         = re.compile(r"\w+", re.UNICODE)


def count_words(html: str) -> int:
    text = _SCRIPT_STYLE.sub(" ", html)
    text = _TAGS.sub(" ", text)
    return len(_WORD.findall(text))


page_words: dict[str, int] = {}
files = sorted(HTML_DIR.glob("*.html"))
for i, f in enumerate(files, 1):
    try:
        page_words[f.stem] = count_words(f.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠ {f.name}: {e}", flush=True)
        page_words[f.stem] = 0
    if i % 500 == 0:
        print(f"  ... {i}/{len(files)} pages measured", flush=True)

OUT_FILE.write_text(json.dumps(page_words, ensure_ascii=False), encoding="utf-8")

total = sum(page_words.values())
print(f"✓ {len(page_words)} pages measured -- {total} words total -> {OUT_FILE}", flush=True)
