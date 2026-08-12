#!/usr/bin/env python3
"""
Detects the right wikiteam3 flag (--api or --index) from any wiki URL.
Stdout output: "--api <url>"  or  "--index <url>"
Exit code 1 if the wiki is unreachable.
"""
import sys
import json

import requests

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "wikiteam3/4.4.8 (https://github.com/saveweb/wikiteam3)",
})


# Markers present on any page rendered by MediaWiki (but absent from a
# "showcase" site / SPA that would respond 200 to any URL).
_MW_MARKERS = (
    "mediawiki",            # class <body class="mediawiki ...">
    "wgpagename",           # JS variable mw.config (RLCONF)
    "mw-content-text",      # main article container
    "powered by mediawiki",
    'content="mediawiki',   # <meta name="generator" content="MediaWiki ...">
)


def _looks_like_mediawiki(html: str) -> bool:
    """True if the HTML contains at least one MediaWiki-specific marker."""
    low = html.lower()
    return any(marker in low for marker in _MW_MARKERS)


def probe_api(url: str, timeout: int = 8) -> bool:
    """Returns True if the URL responds with valid MediaWiki JSON."""
    try:
        r = SESSION.get(
            url,
            params={"action": "query", "format": "json", "meta": "siteinfo"},
            timeout=timeout,
        )
        # A non-MediaWiki site (SPA) returns HTML -> r.json() raises, or
        # returns JSON without the "query" key. Both cases are rejected.
        return "query" in r.json()
    except Exception:
        return False


def probe_index(url: str, timeout: int = 8) -> bool:
    """
    Returns True only if index.php responds AND the page really looks
    like MediaWiki.

    A plain 200 status code isn't enough: "showcase" sites / SPAs (e.g.
    React apps behind Cloudflare) respond 200 to any URL by always
    returning their homepage. So we require a MediaWiki marker.
    """
    try:
        r = SESSION.get(url, params={"title": "Special:Random"}, timeout=timeout)
        return r.status_code == 200 and _looks_like_mediawiki(r.text)
    except Exception:
        return False


# Common MediaWiki article path prefixes (to strip from the base)
_ARTICLE_PREFIXES = {"wiki", "w", "index.php", "api.php"}

def extract_base(url: str) -> str:
    """
    Extracts the base URL of the MediaWiki script from any URL.

    https://finalstandtwo.fandom.com/wiki          -> https://finalstandtwo.fandom.com
    https://finalstandtwo.fandom.com/wiki/Page      -> https://finalstandtwo.fandom.com
    https://wiki.play.eco/en/Eco_Wiki               -> https://wiki.play.eco/en
    https://en.wikipedia.org/wiki/Main_Page         -> https://en.wikipedia.org
    """
    url   = url.split("?")[0].split("#")[0].rstrip("/")
    parts = url.split("/")

    if len(parts) <= 3:   # just https://hostname
        return url

    last = parts[-1]

    # 1. Strip a page title (starts with uppercase, contains _ or :)
    if last and not last.endswith(".php") and (last[0].isupper() or "_" in last or ":" in last):
        parts = parts[:-1]
        last  = parts[-1] if len(parts) > 3 else ""

    # 2. Strip a known article prefix (wiki, w, ...)
    if last in _ARTICLE_PREFIXES:
        parts = parts[:-1]

    return "/".join(parts)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: detect_wiki.py <wiki_url>", file=sys.stderr)
        sys.exit(1)

    raw = sys.argv[1].strip()

    # Direct case: URL ends with api.php
    if raw.endswith("api.php"):
        print(f"--api {raw}")
        return

    # Direct case: URL ends with index.php
    if raw.endswith("index.php"):
        print(f"--index {raw}")
        return

    # General case: build candidate URLs. Many wikis place the script under
    # /w/ or /wiki/ rather than at the root -> we test these variants.
    base = extract_base(raw)
    print(f"  Detection: base={base}", file=sys.stderr)

    candidates = [base] + [base + sub for sub in ("/w", "/wiki")]

    # 1. API (recommended mode) - across all candidate locations
    for root in candidates:
        api_url = root + "/api.php"
        if probe_api(api_url):
            print(f"  -> API available: {api_url}", file=sys.stderr)
            print(f"--api {api_url}")
            return

    # 2. index.php (fallback) - only if the page really looks like MediaWiki
    for root in candidates:
        index_url = root + "/index.php"
        if probe_index(index_url):
            print(f"  -> index.php available: {index_url}", file=sys.stderr)
            print(f"--index {index_url}")
            return

    # Failure: neither a valid API nor a valid MediaWiki index.php. Clear,
    # actionable message (Fail Fast) rather than letting wikiteam3 fail
    # with an obscure error.
    print(
        "ERROR: this site does not appear to be a MediaWiki wiki.\n"
        f"       Address tested: {base}\n"
        "       No valid MediaWiki API or index.php page was found.\n"
        "       Likely cause: the site is a modern web application (SPA)\n"
        "       or a custom site - despite having a '.wiki' domain name.\n"
        "       This pipeline can only archive real MediaWiki wikis\n"
        "       (Fandom, Miraheze, standalone MediaWiki wikis, etc.).",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
