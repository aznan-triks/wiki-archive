#!/usr/bin/env python3
"""
Website mode, step 2: turns the downloaded pages into clean articles.

For every page: finds the article, removes the site's menus and widgets, and
writes  <html_dir>/<NNNN>_<name>.html  -- NNNN is the reading order of the
site (sidebar order), so sorted names = reading order everywhere downstream.
Also works out which category each page belongs to (breadcrumb, sidebar, or
URL path) and writes:
  categories.json   { page stem: [category] }
  hierarchy.json    { "children": { category: [sub-categories] } }

Offline and repeatable. Pages whose text did not change keep their PDF;
the PDF of a changed page is deleted so it is converted again.

Usage: site_extract.py <dump_dir> <html_dir> <categories.json> <hierarchy.json> [pdf_dir]
  env: IMAGES (true/false)
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from html import escape
from pathlib import Path

import site_common as sc
from urllib.parse import urlsplit

from page_style import wrap_page


def log(msg: str) -> None:
    print(msg, flush=True)


def survey(index: dict, pages_dir: Path) -> tuple[dict[str, dict], list[str], str]:
    """First pass: per page title, text, category trail, plus the reading order
    and the site name. Returns (info by url, reading order, site name)."""
    files = {p["final"]: p["file"] for p in index["pages"].values()}
    start = index.get("start_final") or index["start_url"]
    urls = [start] * (start in files) + sorted(u for u in files if u != start)
    info: dict[str, dict] = {}
    order, seen = [], set()
    site_name = ""
    for url in urls:
        soup = sc.parse((pages_dir / files[url]).read_bytes())
        main, how = sc.find_main(soup)
        title = sc.page_title(soup, main, url, "")
        chain, src = sc.breadcrumb_chain(soup, url, title), "breadcrumb"
        if chain is None:
            chain, src = sc.sidebar_chain(soup, url), "sidebar"
        info[url] = {"file": files[url], "has_text": main is not None, "how": how,
                     "title_tag": sc.clean_text(soup.title.get_text()) if soup.title else "",
                     "chain": chain, "src": src if chain is not None else ""}
        for link in sc.sidebar_links(soup, url):
            if link in files and link not in seen:
                seen.add(link)
                order.append(link)
        if url == start:
            site_name = sc.meta_content(soup, "og:site_name")
    order += sorted(u for u in files if u not in seen)
    if not site_name:
        site_name = sc.common_suffix([i["title_tag"] for i in info.values()]) \
            or sc.host_key(urlsplit(start).hostname)
    return info, order, site_name


def path_chain(url: str, index_paths: set[str]) -> list[str]:
    """Categories read from the URL ('/a/b/c' -> a, b; c too when it has sub-pages)."""
    segments = [s for s in sc.url_path(url).split("/") if s]
    if segments and sc.url_path(url) not in index_paths:
        segments = segments[:-1]
    return [sc.humanize(s) for s in segments]


def assign_categories(info: dict[str, dict], site_name: str) -> dict[str, tuple[str, ...]]:
    """url -> category trail (tuple of labels; () = loose top-level page)."""
    paths: dict[str, tuple[str, ...]] = {}
    category_link: dict[str, tuple[str, ...]] = {}
    for url, i in info.items():
        if i["chain"] is not None:
            labels = tuple(label for label, _ in i["chain"])
            paths[url] = labels
            for n, (_, href) in enumerate(i["chain"]):
                if href:
                    category_link[href] = labels[: n + 1]
    if not paths:                                            # no page tells: use the URLs
        all_paths = [sc.url_path(u) for u in info]
        index_paths = {"/".join(p.split("/")[:k]) for p in all_paths for k in range(2, len(p.split("/")))}
        return {url: tuple(path_chain(url, index_paths)) for url in info}
    for url in info:
        if url in category_link:                             # a category's own index page
            paths[url] = category_link[url]
    for url in info:                                         # pages the menus do not list
        if url in paths:
            continue
        prefix = sc.url_path(url).rsplit("/", 1)[0]
        paths[url] = ()
        while prefix:
            sibling = Counter(p for u, p in paths.items() if u != url and p and sc.url_path(u).startswith(prefix + "/")
                              and info[u]["chain"] is not None)
            if sibling:
                paths[url] = sibling.most_common(1)[0][0]
                break
            prefix = prefix.rsplit("/", 1)[0]
    return paths


def name_categories(paths: dict[str, tuple[str, ...]], site_name: str) -> tuple[dict[tuple, str], dict[str, set[str]]]:
    """Unique name for every category trail + the parent -> children map."""
    trails = {t[:n] for t in paths.values() for n in range(1, len(t) + 1)}
    names: dict[tuple, str] = {}
    used: set[str] = set()
    for trail in sorted(trails, key=lambda t: (len(t), t)):
        base = cand = trail[-1]
        if cand in used and len(trail) > 1:
            base = cand = f"{trail[-1]} ({trail[-2]})"
        n = 2
        while cand in used:
            cand, n = f"{base} {n}", n + 1
        names[trail] = cand
        used.add(cand)
    root = site_name
    n = 2
    while root in used:
        root, n = f"{site_name} ({'home' if n == 2 else n})", n + 1
    names[()] = root
    children: dict[str, set[str]] = defaultdict(set)
    for trail, name in names.items():
        if len(trail) > 1:
            children[names[trail[:-1]]].add(name)
    return names, children


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("Usage: site_extract.py <dump_dir> <html_dir> <categories.json> <hierarchy.json> [pdf_dir]",
              file=sys.stderr)
        return 1
    dump, html_dir, cats_file, hier_file = (Path(a) for a in argv[:4])
    pdf_dir = Path(argv[4]) if len(argv) > 4 else None
    keep_images = os.getenv("IMAGES", "true").lower() != "false"
    try:
        index = json.loads((dump / "site.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log(f"✗ {dump / 'site.json'} unreadable ({exc}) -- download the site first")
        return 1

    info, order, site_name = survey(index, dump / "pages")
    suffix = sc.common_suffix([i["title_tag"] for i in info.values()])
    paths = assign_categories(info, site_name)
    names, children = name_categories(paths, site_name)
    by_source = Counter(i["src"] or "url path" for i in info.values())
    log("  Categories from: " + ", ".join(f"{n} page(s) by {s}" for s, n in by_source.most_common()))

    html_dir.mkdir(parents=True, exist_ok=True)
    categories: dict[str, list[str]] = {}
    written: set[str] = set()
    empty = changed = 0
    for pos, url in enumerate(order):
        i = info[url]
        soup = sc.parse((dump / "pages" / i["file"]).read_bytes())
        main_el, _ = sc.find_main(soup)
        title = sc.page_title(soup, main_el, url, suffix)
        body = sc.drop_title_heading(sc.clean_main(main_el, url, keep_images), title) if main_el is not None else ""
        text = sc.clean_text(sc.parse(body).get_text(" "))
        if len(text) < sc.MIN_TEXT_CHARS:
            empty += 1
            log(f"  ⚠ no readable text, skipped: {sc.url_path(url)}")
            continue
        stem = f"{pos:04d}_{sc.slug_of(url)}"
        page = wrap_page(title, body, f'<p class="source">Source: <a href="{escape(url)}">{escape(url)}</a></p>')
        target = html_dir / f"{stem}.html"
        if not target.exists() or target.read_text(encoding="utf-8") != page:
            target.write_text(page, encoding="utf-8")
            changed += 1
            if pdf_dir is not None:
                (pdf_dir / f"{stem}.pdf").unlink(missing_ok=True)
        written.add(stem)
        categories[stem] = [names[paths[url]]]
        log(f"  [{len(written)}/{len(order)}] {title[:60]}  cats:[{categories[stem][0]}]")

    if not written:
        log(f"✗ No page had readable text ({empty} empty). The site is probably built with "
            f"JavaScript only, which this mode cannot read.")
        return 1
    for old in html_dir.glob("*.html"):                      # pages that vanished from the site
        if old.stem not in written:
            old.unlink()
            if pdf_dir is not None:
                (pdf_dir / f"{old.stem}.pdf").unlink(missing_ok=True)

    cats_file.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")
    hier_file.write_text(json.dumps({"children": {k: sorted(v) for k, v in children.items()}},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✓ {len(written)} article(s) ({changed} new or changed), {empty} empty skipped -> {html_dir}")
    log(f"  {len(set(c for v in categories.values() for c in v))} categories -> {cats_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
