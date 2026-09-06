#!/usr/bin/env python3
"""
Shared naming rules for the whole pipeline -- single source of truth (DRY).

Used by extract.py (page files), build_categories.py (API titles -> stems),
export_categories.py / merge_pdf.py (output file names), run.py (output
folder) and server.py (the folder it shows/lists in the UI). A divergence
between these is silent data corruption: categories referencing filenames
that do not exist, or a UI pointing at the wrong output folder.

Pure stdlib so it can be imported from both server.py and the scripts.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

# Folder/file prefix for pages without a category (README: "Misc.{ext}").
# Configurable via the MISC_CATEGORY environment variable.
MISC_CATEGORY = os.getenv("MISC_CATEGORY", "Misc")


def page_stem(title: str) -> str:
    """MediaWiki page title -> HTML/PDF file stem (extract.py writes,
    build_categories.py + exporters read)."""
    return re.sub(r"[^\w\s\-]", "_", title)[:120]


def cat_stem(cat: str) -> str:
    """Category name -> output file base name (no extension)."""
    safe = re.sub(r"[^\w\s\-]", "_", cat).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe[:80]


def wiki_slug(url: str) -> str:
    """Any wiki URL -> data/output/<slug> folder name (hostname, sanitized)."""
    host = urlparse(url).hostname or url
    return re.sub(r"[^\w.-]", "_", host)
