#!/usr/bin/env python3
"""
Generates, for each category, ONE file per requested format (.txt and/or .md).

Text source: HTML files rendered by extract.py.
Grouping comes from category_groups.json.

HTML cleanup: clean_html.py (removes MediaWiki noise).
md conversion : markdownify (proven library).
txt conversion: custom ArticleParser (readable structure).

Selection filter: if SELECTION_FILE points to a JSON (list of categories),
only those categories are exported.

Usage:
  export_categories.py <html_dir> <category_groups.json> <out_dir> <formats>
  formats = comma-separated list among: txt, md
"""
from __future__ import annotations

import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import clean_html as _ch
from markdownify import markdownify as _md

VALID_FORMATS = {"txt", "md"}
EXT = {"txt": ".txt", "md": ".md"}

# Selection and grouping are applied upstream (run.sh): this script
# consumes the provided groups directly. ADD_DIVERS controls whether
# uncategorized pages are added (disabled when a selection is active).
ADD_DIVERS = os.getenv("ADD_DIVERS", "true").lower() != "false"


class ExportError(Exception):
    pass


# ── txt parser (kept for the plain text format) ────────────────────────────────
class ArticleParser(HTMLParser):
    _SKIP    = {"style", "script"}
    _HEADERS = {"h2", "h3", "h4", "h5", "h6"}
    _BLOCKS  = {"p", "div", "tr", "section", "blockquote", "ul", "ol", "table", "figcaption"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title  = ""
        self.blocks: list[tuple] = []
        self._skip  = 0
        self._mode  = None
        self._level = 0
        self._buf: list[str] = []

    def _flush(self) -> None:
        text = " ".join("".join(self._buf).split())
        self._buf = []
        if not text:
            return
        if self._mode == "title":
            if not self.title:
                self.title = text
        elif self._mode == "h":
            self.blocks.append(("h", self._level, text))
        elif self._mode == "li":
            self.blocks.append(("li", text))
        else:
            self.blocks.append(("p", text))

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "h1":
            self._flush(); self._mode = "title"
        elif tag in self._HEADERS:
            self._flush(); self._mode = "h"; self._level = int(tag[1])
        elif tag == "li":
            self._flush(); self._mode = "li"
        elif tag in self._BLOCKS:
            self._flush(); self._mode = "p"
        elif tag in ("td", "th"):
            self._buf.append(" | ")
        elif tag == "br":
            self._buf.append(" ")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li",
                   "div", "tr", "section", "blockquote"):
            self._flush(); self._mode = None

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def _parse_txt(html: str) -> tuple[str, list[tuple]]:
    p = ArticleParser()
    p.feed(html)
    p.close()
    return p.title or "(untitled)", p.blocks


def _render_txt(title: str, blocks: list[tuple]) -> str:
    lines: list[str] = []
    bar = "=" * 70
    lines += [bar, f"  {title}", bar, ""]
    for b in blocks:
        if b[0] == "h":
            lines += ["", f"--- {b[2]} ---", ""]
        elif b[0] == "li":
            lines.append(f"  • {b[1]}")
        else:
            lines += [b[1], ""]
    out, blank = [], False
    for ln in lines:
        if ln == "":
            if blank:
                continue
            blank = True
        else:
            blank = False
        out.append(ln)
    return "\n".join(out).strip()


def _render_md(title: str, body: str) -> str:
    """Converts the cleaned HTML to Markdown via markdownify."""
    content = _md(body, heading_style="ATX", bullets="-")
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    return f"# {title}\n\n{content}"


# ── file name ────────────────────────────────────────────────────────────────
def cat_to_stem(cat: str) -> str:
    safe = re.sub(r"[^\w\s\-]", "_", cat).strip()
    safe = re.sub(r"\s+", "_", safe)
    return safe[:80]


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("Usage: export_categories.py <html_dir> <category_groups.json> "
              "<out_dir> <formats>", file=sys.stderr)
        return 1

    html_dir    = Path(argv[0])
    groups_file = Path(argv[1])
    out_dir     = Path(argv[2])
    formats     = [f.strip() for f in argv[3].split(",") if f.strip()]

    bad = [f for f in formats if f not in VALID_FORMATS]
    if bad:
        print(f"✗ Unknown format(s): {', '.join(bad)} (expected: txt, md)",
              file=sys.stderr)
        return 1
    if not html_dir.exists():
        print(f"✗ HTML directory not found: {html_dir}", file=sys.stderr)
        return 1

    # ── category -> stems grouping ──
    groups: dict[str, list[str]] = {}
    if groups_file.exists():
        try:
            groups = json.loads(groups_file.read_text(encoding="utf-8"))
        except Exception:
            print(f"⚠ {groups_file} unreadable - everything will go into 'Divers'", flush=True)

    all_stems = {f.stem for f in html_dir.glob("*.html")}
    if not all_stems:
        print(f"✗ No HTML files in {html_dir}", file=sys.stderr)
        return 1
    if ADD_DIVERS:
        categorized = {s for stems in groups.values() for s in stems}
        divers = sorted(all_stems - categorized)
        if divers:
            groups = {**groups, "Divers": divers}

    out_dir.mkdir(parents=True, exist_ok=True)

    # Cache (title, txt_blocks, body_html) per stem - parsed only once
    cache: dict[str, tuple[str, list[tuple], str] | None] = {}

    def get_article(stem: str):
        if stem not in cache:
            f = html_dir / f"{stem}.html"
            if not f.exists():
                cache[stem] = None
            else:
                raw_html = f.read_text(encoding="utf-8")
                soup  = _ch.clean(raw_html)
                title = _ch.title_text(soup, stem.replace("_", " "))
                body  = _ch.body_html(soup)
                _, blocks = _parse_txt(body)
                cache[stem] = (title, blocks, body)
        return cache[stem]

    total = 0
    for cat, stems in sorted(groups.items()):
        articles = [a for a in (get_article(s) for s in sorted(set(stems))) if a]
        if not articles:
            continue
        stem_name = cat_to_stem(cat)
        sep_md  = "\n\n---\n\n"
        sep_txt = "\n\n\n"
        for fmt in formats:
            if fmt == "md":
                body = sep_md.join(_render_md(t, bh) for t, _, bh in articles)
            else:
                body = sep_txt.join(_render_txt(t, bl) for t, bl, _ in articles)
            path = out_dir / f"{stem_name}{EXT[fmt]}"
            path.write_text(body + "\n", encoding="utf-8")
        total += 1
        print(f"  ✓ {stem_name} ({len(articles)} articles) -> {', '.join(formats)}", flush=True)

    print(f"✓ {total} categories exported as {', '.join(formats)} -> {out_dir}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
