#!/usr/bin/env python3
"""Extracts each article from the MediaWiki XML into a standalone HTML file."""
import sys, re, pathlib, xml.etree.ElementTree as ET
import mwparserfromhell

src  = sys.argv[1]  # /data/dump/wiki.xml
dest = pathlib.Path(sys.argv[2])  # /data/html
dest.mkdir(parents=True, exist_ok=True)

NS = "http://www.mediawiki.org/xml/export-0.11/"
tree = ET.parse(src)

for page in tree.getroot().findall(f".//{{{NS}}}page"):
    title = page.findtext(f"{{{NS}}}title") or "untitled"
    ns_id = page.findtext(f"{{{NS}}}ns") or "0"
    # Ignore non-content namespaces (User, Talk, Special...)
    if ns_id not in ("0", "4", "10", "14"): continue
    wikitext = page.findtext(f".//{{{NS}}}text") or ""
    parsed   = mwparserfromhell.parse(wikitext)
    plain    = parsed.strip_code()
    safe     = re.sub(r'[^\w\s\-]', '_', title)[:120]
    # Minimal HTML with an H1 title so Pandoc generates bookmarks
    html = f"<!DOCTYPE html><html><head><meta charset='utf-8'>" \
           f"<title>{title}</title></head><body>" \
           f"<h1>{title}</h1><pre>{plain}</pre></body></html>"
    (dest / f"{safe}.html").write_text(html, encoding="utf-8")
    print(f"  ✓ {title}")

print(f"-> {len(list(dest.glob('*.html')))} articles extracted")
