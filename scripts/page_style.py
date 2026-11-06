#!/usr/bin/env python3
"""Page look shared by every extractor (MediaWiki and website mode): one CSS,
one HTML wrapper -- so PDFs look the same whatever the source."""
from __future__ import annotations

from html import escape

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
blockquote { margin: .8rem 0; padding: .1rem .9rem; border-left: 4px solid #bbb; background: #f6f8fa; }
.navbox, .mw-editsection, .noprint, .toc, #toc { display: none !important; }
"""


def wrap_page(title: str, body: str, footer_html: str = "") -> str:
    """Complete HTML document: <h1> title, the body, an optional footer."""
    return (
        f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<title>{escape(title)}</title>'
        f'<style>{CSS}</style></head><body>'
        f'<h1>{escape(title)}</h1>{body}{footer_html}</body></html>'
    )
