#!/usr/bin/env python3
"""
Shared helpers of the website mode (site_fetch.py downloads, site_extract.py
turns the pages into clean articles). Pure functions, no network.

Targets documentation sites that send their text in the HTML (Docusaurus,
MkDocs, Sphinx, VitePress, Starlight, Hugo, GitBook...). Sites that build
their pages with JavaScript only are not supported.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, NavigableString, Tag

# ── settings (environment overrides keep them out of the code) ───────────────
# URLs whose path ends like this are files, not pages.
ASSET_EXT = frozenset(os.getenv("SITE_ASSET_EXT", (
    "png jpg jpeg gif svg webp ico bmp avif pdf zip gz tgz tar 7z rar exe msi dmg "
    "mp3 mp4 webm ogg wav mov avi css js mjs json xml txt rss atom woff woff2 ttf eot "
    "map csv xls xlsx doc docx ppt pptx")).split())
# Never worth archiving: tag clouds, blog pagination, search, framework internals.
DEFAULT_EXCLUDE = tuple(os.getenv("SITE_DEFAULT_EXCLUDE", (
    "*/tags/* */tags */tag/* */page/[0-9]* */search */search/* */__docusaurus/* "
    "*/cdn-cgi/* */wp-admin/* */wp-json/* */feed */feed/* */login */logout */print/*")).split())
# A page with less text than this is not an article (redirect stub, empty shell).
MIN_TEXT_CHARS = int(os.getenv("SITE_MIN_TEXT_CHARS", "20"))
# Home breadcrumb labels (any language is guessed from the link, this is the fallback).
HOME_LABELS = {"home", "accueil", "start", "inicio", "startseite", "docs", "documentation"}

SEPARATORS = (" | ", " – ", " — ", " · ", " - ")


# ── URLs ──────────────────────────────────────────────────────────────────────
def host_key(host: str) -> str:
    """'www.example.com' and 'example.com' are the same site."""
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def norm_url(url: str, base: str | None = None) -> str | None:
    """Absolute http(s) URL without fragment, query or trailing slash; None for
    anything else (mailto:, javascript:, tel:...). The query is dropped on
    purpose: a page is identified by its path (the start URL's own query, like
    ?game=cs2, is re-applied by the fetcher to every request)."""
    try:
        full = urljoin(base, url.strip()) if base else url.strip()
        parts = urlsplit(full)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    path = re.sub(r"/index\.html?$", "", parts.path) or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, "", ""))


def url_path(url: str) -> str:
    return urlsplit(url).path or "/"


def matches_any(path: str, patterns) -> bool:
    return any(fnmatch.fnmatchcase(path, p) for p in patterns if p)


def split_patterns(text: str) -> list[str]:
    """'/api/*, /v1/*' -> ['/api/*', '/v1/*'] (comma or space separated)."""
    return [p for p in re.split(r"[,\s]+", text or "") if p]


def in_scope(url: str, start_url: str, include: list[str], exclude: list[str],
             exclude_prefixes: list[str] = ()) -> bool:
    """Same site, a page (not a file), not excluded, and inside `include` when given."""
    parts, start = urlsplit(url), urlsplit(start_url)
    if host_key(parts.hostname) != host_key(start.hostname):
        return False
    path = parts.path or "/"
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    if ext in ASSET_EXT:
        return False
    if any(path == p or path.startswith(p.rstrip("/") + "/") for p in exclude_prefixes):
        return False
    if matches_any(path, list(DEFAULT_EXCLUDE) + list(exclude)):
        return False
    return not include or matches_any(path, include)


def locale_prefixes(soup: BeautifulSoup, page_url: str) -> list[str]:
    """Path prefixes of the OTHER languages of the site (from hreflang links),
    so a translated copy of every page is not archived along with the original."""
    own = url_path(page_url)
    prefixes = set()
    for link in soup.select('link[rel="alternate"][hreflang]'):
        if link.get("hreflang", "").lower() == "x-default":
            continue
        alt = norm_url(link.get("href", ""), page_url)
        if not alt:
            continue
        path = url_path(alt)
        if path != own and own != "/" and path.endswith(own):
            prefixes.add(path[: -len(own)])
        elif own == "/" and path != "/":
            prefixes.add(path)
    return sorted(p for p in prefixes if p and p != "/")


def parse_sitemap(xml_bytes: bytes) -> tuple[str, list[str]]:
    """('index'|'urls', locs) of a sitemap; ('', []) when it is not one."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return "", []
    kind = {"sitemapindex": "index", "urlset": "urls"}.get(root.tag.rsplit("}", 1)[-1], "")
    locs = [(e.text or "").strip() for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "loc"]
    return kind, [u for u in locs if u]


def slug_of(url: str, limit: int = 100) -> str:
    """Readable file-name part of a URL path ('/Basics/a-b' -> 'Basics__a-b')."""
    path = url_path(url).strip("/")
    return (re.sub(r"[^\w\-]+", "_", path.replace("/", "__")) or "index")[:limit]


def humanize(segment: str) -> str:
    """'working-on-content' -> 'Working on content'."""
    text = re.sub(r"[-_]+", " ", segment).strip()
    return text[:1].upper() + text[1:] if text.islower() else text


def clean_text(text: str) -> str:
    return " ".join(text.replace("​", "").split())


# ── page-level facts ──────────────────────────────────────────────────────────
def parse(html: bytes | str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def meta_content(soup: BeautifulSoup, *names: str) -> str:
    for n in names:
        tag = soup.find("meta", attrs={"name": n}) or soup.find("meta", attrs={"property": n})
        if tag and tag.get("content"):
            return clean_text(tag["content"])
    return ""


def title_suffix(title: str) -> str:
    """'Page | Site' -> 'Site' ('' when the title has no separator)."""
    for sep in SEPARATORS:
        if sep in title:
            return title.rsplit(sep, 1)[-1].strip()
    return ""


def strip_suffix(title: str, suffix: str) -> str:
    if suffix:
        for sep in SEPARATORS:
            if title.endswith(sep + suffix):
                return title[: -len(sep + suffix)].strip()
    return title


def common_suffix(titles: list[str]) -> str:
    """The site name every title ends with ('' unless it is clearly shared)."""
    if len(titles) < 3:
        return ""
    top = Counter(title_suffix(t) for t in titles).most_common(1)[0]
    return top[0] if top[0] and top[1] >= 0.8 * len(titles) else ""


# ── main content ──────────────────────────────────────────────────────────────
# Most specific first: the first one with some text wins.
MAIN_SELECTORS = [
    "article .theme-doc-markdown", ".theme-doc-markdown",                 # Docusaurus docs
    "article.md-content__inner", "[data-md-component=content] article",    # MkDocs Material
    ".vp-doc", ".sl-markdown-content", ".markdown-body", ".td-content",    # VitePress, Starlight, GitHub-like, Docsy
    "div[role=main]", "main article", "article", "main", "[role=main]",
    "#content", "#main-content", ".content",
]
NOISE = [
    "script", "style", "noscript", "template", "form", "button", "input", "select",
    "textarea", "nav", "footer", "iframe", "object", "embed", "video", "audio", "canvas",
    ".theme-doc-breadcrumbs", ".breadcrumbs", ".pagination-nav", ".theme-doc-footer",
    ".theme-doc-toc-mobile", ".theme-doc-toc-desktop", ".table-of-contents",
    ".hash-link", ".headerlink", ".theme-edit-this-page", ".theme-last-updated",
    ".md-source-file", ".md-content__button", ".md-footer", ".md-nav", ".md-sidebar",
    ".feedback", ".docs-feedback", "[class*=editThisPage]", "[class*=lastUpdated]",
    "[class*=breadcrumb]", "[hidden]", "[style*='display:none']", "[style*='display: none']",
]
ADMONITIONS = ".theme-admonition, .admonition, .custom-block, .starlight-aside, .callout, .markdown-alert"
ADMONITION_TITLES = (".admonition-title, [class*=admonitionHeading], .custom-block-title, "
                     ".starlight-aside__title, .markdown-alert-title, .callout-title")
LINE_CLASSES = ("token-line", "line", "ec-line", "code-line")
KEEP_ATTRS = {"href", "src", "alt", "colspan", "rowspan", "start", "data-lang"}


def _text_len(el: Tag) -> int:
    return len(clean_text(el.get_text(" ")))


def find_main(soup: BeautifulSoup) -> tuple[Tag | None, str]:
    """(content element, how it was found)."""
    for sel in MAIN_SELECTORS:
        el = soup.select_one(sel)
        if el is not None and _text_len(el) >= MIN_TEXT_CHARS:
            return el, sel
    # Last resort: the block with the most prose (links count against it, so the
    # menus lose to the article).
    best, best_score = None, 0.0
    for el in soup.find_all(["div", "section", "main", "article"]):
        links = sum(len(a.get_text()) for a in el.find_all("a"))
        score = _text_len(el) - 1.5 * links
        if score > best_score:
            best, best_score = el, score
    return (best, "density") if best is not None and best_score >= MIN_TEXT_CHARS else (None, "")


def _language(el: Tag) -> str:
    """Programming language of a code block, from the classes around it."""
    node = el
    for _ in range(4):
        if node is None or not isinstance(node, Tag):
            break
        classes = " ".join(node.get("class", []))
        m = re.search(r"(?:language|lang|highlight-|brush:\s*)-?([\w+#]+)", classes)
        if m and m.group(1) not in ("none", "text", "plain", "highlight"):
            return m.group(1)
        if node.get("data-language"):
            return node["data-language"]
        node = node.parent
    return ""


def _is_line(classes) -> bool:
    return bool(classes) and any(c in LINE_CLASSES for c in classes)


def _code_text(pre: Tag) -> str:
    for br in pre.find_all("br"):
        br.replace_with("\n")
    lines = []
    for el in pre.find_all(class_=_is_line):
        for parent in el.parents:
            if parent is pre:
                lines.append(el)
                break
            if _is_line(parent.get("class")):   # nested piece of a line already taken
                break
    if lines:
        return "\n".join(el.get_text().rstrip("\n") for el in lines)
    return pre.get_text()


def _normalize_code(main: Tag) -> None:
    for pre in main.find_all("pre"):
        for junk in pre.find_all(["button", "svg"]):
            junk.decompose()
        lang = _language(pre)
        text = _code_text(pre).replace("​", "").rstrip("\n")
        pre.clear()
        code = main.new_tag("code")
        code.string = text
        pre.append(code)
        if lang:
            pre["data-lang"] = lang


def _flatten_tabs(main: Tag) -> None:
    """Every tab panel is in the HTML, only one is shown: keep all, under their label."""
    for tablist in main.select("[role=tablist]"):
        container = tablist.parent
        while container is not None and not container.select("[role=tabpanel]"):
            container = container.parent
        if container is None or container is main:
            continue
        labels = [clean_text(t.get_text(" ")) for t in tablist.select("[role=tab]")]
        panels = container.select("[role=tabpanel]")
        out = main.new_tag("div")
        for label, panel in zip(labels + [""] * len(panels), panels):
            if label:
                p = main.new_tag("p"); b = main.new_tag("strong"); b.string = label
                p.append(b); out.append(p)
            panel.attrs.pop("hidden", None)
            out.append(panel.extract())
        container.replace_with(out)
    for group in main.select(".tabbed-set"):          # MkDocs Material content tabs
        labels = [clean_text(t.get_text(" ")) for t in group.select(".tabbed-labels > label")]
        out = main.new_tag("div")
        for label, block in zip(labels + [""] * 99, group.select(".tabbed-content > .tabbed-block")):
            if label:
                p = main.new_tag("p"); b = main.new_tag("strong"); b.string = label
                p.append(b); out.append(p)
            out.append(block.extract())
        group.replace_with(out)


def _admonitions_to_quotes(main: Tag) -> None:
    for box in reversed(main.select(ADMONITIONS)):
        title = box.select_one(ADMONITION_TITLES)
        label = clean_text(title.get_text(" ")).capitalize() if title else ""
        if title:
            title.decompose()
        quote = main.new_tag("blockquote")
        if label:
            p = main.new_tag("p"); b = main.new_tag("strong"); b.string = label
            p.append(b); quote.append(p)
        for child in list(box.children):
            quote.append(child.extract())
        box.replace_with(quote)


def _drop_icons(main: Tag) -> None:
    for svg in main.find_all("svg"):
        if svg.get("aria-hidden") == "true" or svg.find_parent(["a", "button", "h1", "h2", "h3", "h4", "h5", "h6"]) \
                or any("icon" in c for c in svg.get("class", [])) or not clean_text(svg.get_text(" ")):
            svg.decompose()


def clean_main(main: Tag, page_url: str, keep_images: bool) -> str:
    """The article as plain, absolute-linked HTML (no framework markup)."""
    main = BeautifulSoup(str(main), "html.parser")           # work on a copy
    _flatten_tabs(main)
    _admonitions_to_quotes(main)
    for sel in NOISE:
        for el in main.select(sel):
            el.decompose()
    _normalize_code(main)
    _drop_icons(main)
    for img in main.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not keep_images or not src or src.startswith("data:"):
            img.decompose()
        else:
            img["src"] = urljoin(page_url, src)
    for src in main.find_all("source"):
        src.decompose()
    for a in main.find_all("a"):
        href = a.get("href", "")
        if not href or href.startswith("#"):
            a.unwrap()                                       # points nowhere in the archive
        else:
            a["href"] = urljoin(page_url, href)
    for el in main.find_all(True):
        el.attrs = {k: v for k, v in el.attrs.items() if k in KEEP_ATTRS}
    for h in main.find_all(re.compile(r"^h[1-6]$")):
        if not clean_text(h.get_text(" ")):
            h.decompose()
    return str(main).replace("​", "")


def heading_text(h: Tag) -> str:
    """Text of a heading without its anchor link ('Install ¶' -> 'Install')."""
    copy = BeautifulSoup(str(h), "html.parser")
    for junk in copy.select(".hash-link, .headerlink, .anchor-link, button, svg"):
        junk.decompose()
    return clean_text(copy.get_text(" "))


def page_title(soup: BeautifulSoup, main: Tag | None, url: str, suffix: str) -> str:
    h1 = (main.find("h1") if main is not None else None) or soup.find("h1")
    if h1 is not None and heading_text(h1):
        return heading_text(h1)
    raw = meta_content(soup, "og:title") or (clean_text(soup.title.get_text()) if soup.title else "")
    raw = strip_suffix(raw, suffix)
    return raw or humanize(url_path(url).rstrip("/").rsplit("/", 1)[-1]) or "Home"


def drop_title_heading(body_html: str, title: str) -> str:
    """The wrapper adds the <h1>: remove the article's own copy of it."""
    soup = BeautifulSoup(body_html, "html.parser")
    h1 = soup.find("h1")
    if h1 is not None and heading_text(h1) == title:
        parent = h1.parent
        h1.decompose()
        if parent is not None and parent.name == "header" and not clean_text(parent.get_text(" ")):
            parent.decompose()
    return str(soup)


# ── where a page sits: breadcrumbs, JSON-LD, sidebar ──────────────────────────
BREADCRUMB_SEL = ('nav[aria-label*="readcrumb" i], [itemtype*="BreadcrumbList"], '
                  "ul.breadcrumbs, ol.breadcrumb, .breadcrumb, nav.md-path")


def _trim_chain(items: list[tuple[str, str | None]], page_url: str, title: str,
                site_root: str) -> list[tuple[str, str | None]]:
    """Drops the home entry and the current page from a breadcrumb trail."""
    if items:
        label, href = items[0]
        if (href and href == site_root) or label.lower() in HOME_LABELS or not label:
            items = items[1:]
    if items:
        label, href = items[-1]
        if href is None or href == page_url or label.lower() == title.lower():
            items = items[:-1]
    return [(label, href) for label, href in items if label]


def breadcrumb_chain(soup: BeautifulSoup, page_url: str, title: str) -> list[tuple[str, str | None]] | None:
    """[(label, link|None)] of the categories above the page; None = no breadcrumb found."""
    root = norm_url("/", page_url)
    nav = soup.select_one(BREADCRUMB_SEL)
    if nav is not None:
        items = []
        for li in nav.find_all("li"):
            a = li.find("a", href=True)
            items.append((clean_text(li.get_text(" ")), norm_url(a["href"], page_url) if a else None))
        if items:
            return _trim_chain(items, page_url, title, root)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        for node in (data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []):
            if isinstance(node, dict) and node.get("@type") == "BreadcrumbList":
                elems = sorted(node.get("itemListElement", []), key=lambda e: e.get("position", 0))
                items = []
                for e in elems:
                    item = e.get("item")
                    href = item.get("@id") if isinstance(item, dict) else item
                    name = e.get("name") or (item.get("name") if isinstance(item, dict) else "")
                    items.append((clean_text(str(name or "")), norm_url(href, page_url) if href else None))
                if items:
                    return _trim_chain(items, page_url, title, root)
    return None


SIDEBAR_SEL = ["nav.menu", ".theme-doc-sidebar-menu", "nav.md-nav--primary", ".md-sidebar--primary nav",
               ".wy-menu-vertical", ".sphinxsidebar", ".bd-sidebar-primary", ".book-menu nav",
               ".td-sidebar-nav", "nav.sidebar", ".sidebar nav", "#sidebar", "aside nav",
               'nav[aria-label*="idebar" i]', 'nav[aria-label*="ocs" i]']


def find_sidebar(soup: BeautifulSoup) -> Tag | None:
    for sel in SIDEBAR_SEL:
        el = soup.select_one(sel)
        if el is not None and len(el.find_all("a", href=True)) >= 3:
            return el
    best = max((n for n in soup.find_all(["nav", "aside"]) if not n.find_parent(["header", "footer"])),
               key=lambda n: len(n.find_all("a", href=True)), default=None)
    return best if best is not None and len(best.find_all("a", href=True)) >= 5 else None


def sidebar_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    """Pages listed in the sidebar, in reading order."""
    side = find_sidebar(soup)
    if side is None:
        return []
    seen, out = set(), []
    for a in side.find_all("a", href=True):
        u = norm_url(a["href"], page_url)
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _own_label(li: Tag) -> str:
    for child in li.children:
        if isinstance(child, Tag) and child.name in ("ul", "ol", "nav"):
            continue
        text = clean_text(child.get_text(" ") if isinstance(child, Tag) else str(child))
        if text:
            return text
    return ""


def _own_link(li: Tag) -> str | None:
    """Target of the category's own header link (None when the header is not a link)."""
    for child in li.children:
        if not isinstance(child, Tag) or child.name in ("ul", "ol", "nav"):
            continue
        a = child if child.name == "a" else child.find("a")
        if a is not None:
            return a.get("href")
    return None


def sidebar_chain(soup: BeautifulSoup, page_url: str) -> list[tuple[str, str | None]] | None:
    """Categories above the page read from the sidebar entry that links to it."""
    side = find_sidebar(soup)
    if side is None:
        return None
    link = next((a for a in side.find_all("a", href=True) if norm_url(a["href"], page_url) == page_url), None)
    if link is None:
        return None
    chain, li = [], link.find_parent("li")
    own = True
    while li is not None and side in li.parents:
        nested = li.find(["ul", "ol", "nav"]) is not None
        if not own or nested:                  # a page that has children is its own category
            own_href = _own_link(li)
            href = norm_url(own_href, page_url) if own_href else None
            label = _own_label(li)
            if label:
                chain.append((label, href))
        own, li = False, li.find_parent("li")
    return chain[::-1]
