#!/usr/bin/env python3
"""HTML cleanup for MediaWiki before text/Markdown conversion."""
from __future__ import annotations
from bs4 import BeautifulSoup

# CSS selectors for MediaWiki noise (configurable list at the top of the script)
NOISE_SELECTORS = [
    ".mw-editsection",
    "sup.reference", ".reference", ".references", ".reflist",
    ".navbox", ".navbox-inner", ".navbox-subgroup", ".navbox-list",
    ".toc", "#toc",
    ".mw-jump-link",
    ".noprint",
    ".ambox", ".tmbox", ".cmbox", ".ombox",
    ".hatnote", ".hatnotes",
    ".catlinks", "#catlinks",
    ".mw-indicators",
    ".sistersitebox",
    ".thumbcaption .magnify",
    "noscript",
    "#coordinates",
    ".printfooter",
]


def clean(html: str) -> BeautifulSoup:
    """Parse the HTML and strip MediaWiki noise. Returns a BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    for sel in NOISE_SELECTORS:
        for el in soup.select(sel):
            el.decompose()
    return soup


def body_html(soup: BeautifulSoup) -> str:
    """Return the <body> content as HTML (or the whole document if missing)."""
    body = soup.find("body")
    return str(body) if body else str(soup)


def title_text(soup: BeautifulSoup, fallback: str = "") -> str:
    """Text of the first <h1> tag."""
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else fallback
