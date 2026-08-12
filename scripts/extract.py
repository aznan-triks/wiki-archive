#!/usr/bin/env python3
"""
Extracts each article from the MediaWiki XML into HTML.

API mode  : calls action=parse on the wiki -> faithful rendering (tables, templates,
            Lua modules, infoboxes...) + category retrieval.
Text mode : fallback if the API is unavailable - basic wikitext->HTML conversion.

Writes categories.json : { "safe_filename": ["Cat1", "Cat2", ...], ... }
"""
import json
import re
import sys
import time
import pathlib
import xml.etree.ElementTree as ET

import mwparserfromhell
import requests

# ── args ──────────────────────────────────────────────────────────────────────
XML_FILE    = sys.argv[1]
DEST        = pathlib.Path(sys.argv[2])
API_URL     = sys.argv[3].strip() if len(sys.argv) > 3 else ""
DELAY       = float(sys.argv[4])  if len(sys.argv) > 4 else 0.5
CATS_FILE   = pathlib.Path(sys.argv[5]) if len(sys.argv) > 5 else DEST.parent / "categories.json"

DEST.mkdir(parents=True, exist_ok=True)

NS_MW   = "http://www.mediawiki.org/xml/export-0.11/"
KEEP_NS = {"0"}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "wikiteam3/4.4.8 (https://github.com/saveweb/wikiteam3)",
})

# ── load existing categories (resume) ──────────────────────────────────────────
categories: dict[str, list[str]] = {}
if CATS_FILE.exists():
    try:
        categories = json.loads(CATS_FILE.read_text(encoding="utf-8"))
        print(f"  Categories loaded from {CATS_FILE} ({len(categories)} pages)", flush=True)
    except Exception:
        pass

def save_categories() -> None:
    CATS_FILE.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")

# ── embedded CSS ─────────────────────────────────────────────────────────────
CSS = """
body { font-family: Arial, sans-serif; max-width: 960px; margin: 2rem auto;
       padding: 0 1.2rem; color: #222; line-height: 1.6; }
h1   { font-size: 1.8rem; border-bottom: 2px solid #ccc; padding-bottom: .4rem; }
h2   { font-size: 1.35rem; border-bottom: 1px solid #ddd; margin-top: 1.6rem; }
h3   { font-size: 1.1rem; margin-top: 1.2rem; }
table { border-collapse: collapse; width: 100%; margin: .8rem 0; font-size: .92rem; }
th, td { border: 1px solid #bbb; padding: .35rem .6rem; text-align: left; vertical-align: top; }
th { background: #f0f2f4; font-weight: 600; }
tr:nth-child(even) td { background: #fafafa; }
ul, ol { padding-left: 1.6rem; }
li { margin: .2rem 0; }
pre { background: #f6f8fa; padding: .8rem; border-radius: 4px;
      white-space: pre-wrap; word-break: break-word; font-size: .85rem; }
img { max-width: 100%; height: auto; }
.navbox, .mw-editsection, .noprint, .toc, #toc { display: none !important; }
"""

# ── rendering via API ──────────────────────────────────────────────────────────
_api_failures = 0
_API_FAIL_LIMIT = 5

def render_via_api(title: str) -> tuple[str | None, list[str]]:
    """Returns (html_content, [categories]). html=None if the API call fails."""
    global _api_failures
    if not API_URL or _api_failures >= _API_FAIL_LIMIT:
        return None, []
    try:
        r = SESSION.get(API_URL, params={
            "action":             "parse",
            "page":               title,
            "prop":               "text|categories",
            "disableeditsection": "1",
            "disabletoc":         "1",
            "format":             "json",
        }, timeout=20)
        data = r.json()
        if "error" in data:
            return None, []

        parse = data.get("parse", {})

        # ── HTML ──
        raw = parse.get("text", {}).get("*", "")
        if not raw:
            return None, []

        m = re.search(
            r'<div class="mw-parser-output">(.*?)'
            r'(?=<div[^>]+class="[^"]*(?:catlinks|printfooter|mw-fr-|visualClear)[^"]*")',
            raw, re.DOTALL
        )
        content = m.group(1) if m else raw
        content = re.sub(r'<span[^>]*class="[^"]*mw-editsection[^"]*".*?</span>', '', content, flags=re.DOTALL)
        content = re.sub(r'<sup[^>]*class="[^"]*reference[^"]*"[^>]*>.*?</sup>', '', content, flags=re.DOTALL)
        content = re.sub(r'<div[^>]*class="[^"]*(?:navbox|vertical-navbox|noprint)[^"]*".*?</div>', '', content, flags=re.DOTALL)

        # ── categories ──
        cats = [
            c["*"].replace("_", " ")
            for c in parse.get("categories", [])
            if not c.get("hidden")   # ignore hidden (maintenance) categories
        ]

        _api_failures = 0
        return content.strip(), cats

    except Exception:
        _api_failures += 1
        return None, []

# ── text rendering (fallback) ──────────────────────────────────────────────────
def _extract_categories_from_wikitext(text: str) -> list[str]:
    parsed = mwparserfromhell.parse(text)
    cats = []
    for wl in parsed.filter_wikilinks():
        title_str = str(wl.title)
        if title_str.lower().startswith("category:"):
            cat = title_str.split(":", 1)[1].split("|")[0].strip().replace("_", " ")
            if cat:
                cats.append(cat)
    return cats

def _wikitext_to_html(text: str) -> str:
    lines    = text.split("\n")
    out      = []
    in_table = False
    in_ul = in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul: out.append("</ul>"); in_ul = False
        if in_ol: out.append("</ol>"); in_ol = False

    for line in lines:
        if re.match(r"^={2,6}", line):
            m = re.match(r"^(={2,6})\s*(.*?)\s*\1\s*$", line)
            if m:
                close_lists()
                level = len(m.group(1))
                out.append(f"<h{level}>{m.group(2)}</h{level}>")
            continue
        if line.startswith("{|"):
            close_lists(); in_table = True; out.append("<table>"); continue
        if in_table:
            if line.startswith("|}"):   out.append("</table>"); in_table = False
            elif line.startswith("|-"): out.append("<tr>")
            elif line.startswith("!"):
                for c in line[1:].split("!!"): out.append(f"<th>{c.split('|')[-1].strip()}</th>")
            elif line.startswith("|"):
                for c in line[1:].split("||"): out.append(f"<td>{c.split('|')[-1].strip()}</td>")
            continue
        if line.startswith("*"):
            if not in_ul: close_lists(); out.append("<ul>"); in_ul = True
            out.append(f"<li>{line.lstrip('* ').strip()}</li>"); continue
        if line.startswith("#"):
            if not in_ol: close_lists(); out.append("<ol>"); in_ol = True
            out.append(f"<li>{line.lstrip('# ').strip()}</li>"); continue
        close_lists()
        if not line.strip(): out.append("<p>"); continue
        line = re.sub(r"'''(.+?)'''", r"<b>\1</b>", line)
        line = re.sub(r"''(.+?)''",   r"<i>\1</i>", line)
        line = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", line)
        line = re.sub(r"\[\[([^\]]+)\]\]",             r"\1", line)
        line = re.sub(r"\[https?://\S+ ([^\]]+)\]",    r"\1", line)
        out.append(line)

    close_lists()
    if in_table: out.append("</table>")
    return "\n".join(out)

def render_fallback(wikitext: str) -> tuple[str, list[str]]:
    cats    = _extract_categories_from_wikitext(wikitext)
    parsed  = mwparserfromhell.parse(wikitext)
    content = _wikitext_to_html(str(parsed))
    return content, cats

# ── wrap HTML ─────────────────────────────────────────────────────────────────
def wrap_html(title: str, body: str, cats: list[str]) -> str:
    cats_html = ""
    if cats:
        cats_html = (
            '<div style="margin-top:2rem;padding-top:.6rem;border-top:1px solid #ddd;'
            'font-size:.8rem;color:#666">Categories: '
            + " | ".join(cats) + "</div>"
        )
    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<title>{title}</title>'
        f'<style>{CSS}</style></head><body>'
        f'<h1>{title}</h1>{body}{cats_html}</body></html>'
    )

# ── pipeline ──────────────────────────────────────────────────────────────────
count = resumed = skipped = api_ok = fallback_ok = 0
t0 = time.time()
_title = _ns = _text = None
SAVE_EVERY = 50   # save categories.json every N articles

for event, elem in ET.iterparse(XML_FILE, events=("end",)):
    tag = elem.tag
    if   tag == f"{{{NS_MW}}}title": _title = elem.text or ""
    elif tag == f"{{{NS_MW}}}ns":    _ns    = elem.text or "0"
    elif tag == f"{{{NS_MW}}}text":  _text  = elem.text or ""
    elif tag == f"{{{NS_MW}}}page":
        if _ns in KEEP_NS and _title:
            safe    = re.sub(r"[^\w\s\-]", "_", _title)[:120]
            outfile = DEST / f"{safe}.html"

            if outfile.exists():
                resumed += 1
                # Fetch categories if missing for this page (partial resume)
                if safe not in categories and API_URL:
                    _, cats = render_via_api(_title)
                    if cats:
                        categories[safe] = cats
            else:
                content, cats = render_via_api(_title)
                if content is not None:
                    method = "api"; api_ok += 1
                    time.sleep(DELAY)
                else:
                    content, cats = render_fallback(_text or "")
                    method = "txt"; fallback_ok += 1

                categories[safe] = cats
                outfile.write_text(wrap_html(_title, content, cats), encoding="utf-8")
                count += 1

                elapsed = time.time() - t0
                rate    = count / elapsed if elapsed > 0 else 0
                cats_str = ", ".join(cats[:3]) + ("..." if len(cats) > 3 else "") if cats else "-"
                print(f"  [{count+resumed}] [{method}] {_title[:55]}  cats:[{cats_str}]  ({rate:.1f}/s)", flush=True)

            if (count + resumed) % SAVE_EVERY == 0:
                save_categories()
        else:
            skipped += 1

        elem.clear()
        _title = _ns = _text = None

save_categories()
elapsed = time.time() - t0
rate    = count / elapsed if elapsed > 0 else 0
print(f"✓ {count} new ({api_ok} api / {fallback_ok} txt) + {resumed} resumed"
      f" in {elapsed:.1f}s ({rate:.1f}/s) - {skipped} skipped", flush=True)
print(f"  categories.json: {len(categories)} pages indexed -> {CATS_FILE}", flush=True)
