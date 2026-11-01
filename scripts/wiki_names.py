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

import hashlib
import os
import re
from urllib.parse import urlparse

# Folder/file prefix for pages without a category (README: "Misc.{ext}").
# Configurable via the MISC_CATEGORY environment variable.
MISC_CATEGORY = os.getenv("MISC_CATEGORY", "Misc")


# Titles whose characters get replaced ("A/B", "A:B" -> "A_B") can collide. With
# UNIQUE_NAMES=true those titles (only those) get a short hash of the exact
# title appended, so no page is lost. Off by default: file names stay as before.
UNIQUE_NAMES = os.getenv("UNIQUE_NAMES", "false").lower() == "true"
_STEM_MAX = 120
_HASH_LEN = 8


def page_stem(title: str) -> str:
    """MediaWiki page title -> HTML/PDF file stem (extract.py writes,
    build_categories.py + exporters read)."""
    safe = re.sub(r"[^\w\s\-]", "_", title)
    if UNIQUE_NAMES and (safe != title or len(title) > _STEM_MAX):
        digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:_HASH_LEN]
        return f"{safe[:_STEM_MAX - _HASH_LEN - 1]}~{digest}"
    return safe[:_STEM_MAX]


def cat_stem(cat: str) -> str:
    """Category name -> output file base name (no extension)."""
    safe = re.sub(r"[^\w\s\-]", "_", cat).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe[:80]


def output_folder(url: str, job_id: str, per_job: bool) -> str:
    """Name of the folder under data/output/ that receives a job's final files:
    shared by all jobs of a wiki by default, or private to the job."""
    slug = wiki_slug(url)
    return f"{slug}--{job_id}" if per_job else slug


def wiki_slug(url: str) -> str:
    """Any wiki URL -> data/output/<slug> folder name (hostname, sanitized)."""
    host = urlparse(url).hostname or url
    return re.sub(r"[^\w.-]", "_", host)
