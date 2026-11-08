#!/usr/bin/env python3
"""
Website mode, step 1: downloads the pages of a documentation site.

Starts from the given page, adds the pages listed by the sitemap, then follows
the links of every page (menus included) -- always on the same site, politely
(delay between requests, retries, robots.txt) and resumably: pages already on
disk are re-read, not downloaded again.

Writes  <dump_dir>/pages/<hash>.html  and  <dump_dir>/site.json.

Usage: site_fetch.py <start_url> <dump_dir>
  env: DELAY, CAT_WORKERS (parallel requests), SITE_MAX_PAGES, SITE_INCLUDE,
       SITE_EXCLUDE, SITE_RESPECT_ROBOTS, SITE_TIMEOUT, SITE_RETRIES,
       SITE_BACKOFF, SITE_MAX_BYTES, SITE_USER_AGENT
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests

import site_common as sc

USER_AGENT  = os.getenv("SITE_USER_AGENT", "wiki-archive (+https://github.com/aznan-triks/wiki-archive)")
TIMEOUT     = float(os.getenv("SITE_TIMEOUT", "20"))
RETRIES     = int(os.getenv("SITE_RETRIES", "3"))
BACKOFF     = float(os.getenv("SITE_BACKOFF", "1.5"))
MAX_BYTES   = int(os.getenv("SITE_MAX_BYTES", str(15 * 1024 * 1024)))
RETRY_CODES = {429, 500, 502, 503, 504}
DEAD_CODES  = {404, 410}
SAVE_EVERY  = 100
SITEMAP_DEPTH, SITEMAP_FILES = 3, 200
ROBOTS_TOKEN = "wiki-archive"


def log(msg: str) -> None:
    print(msg, flush=True)


class Limiter:
    """Spaces the start of every request by `delay` seconds, whatever the workers."""
    def __init__(self, delay: float) -> None:
        self.delay, self.next, self.lock = delay, 0.0, threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next)
            self.next = slot + self.delay
        if slot > now:
            time.sleep(slot - now)


class Fetcher:
    def __init__(self, delay: float, sticky: dict[str, str]) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.limiter, self.sticky = Limiter(delay), sticky

    def get(self, url: str, sticky: bool = True) -> requests.Response:
        """GET with retries; raises requests.RequestException when all attempts fail."""
        last: Exception | None = None
        for attempt in range(RETRIES + 1):
            self.limiter.wait()
            try:
                r = self.session.get(url, params=(self.sticky or None) if sticky else None, timeout=TIMEOUT)
            except requests.RequestException as exc:
                last = exc
            else:
                if r.status_code not in RETRY_CODES:
                    return r
                last = requests.HTTPError(f"HTTP {r.status_code}")
                retry_after = r.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    time.sleep(min(int(retry_after), 60))
                    continue
            time.sleep(BACKOFF * 2 ** attempt)
        raise last or requests.RequestException("request failed")


def load_robots(fetcher: Fetcher, start: str, respect: bool) -> tuple[RobotFileParser | None, list[str]]:
    """(robots rules or None, sitemap URLs declared in robots.txt)."""
    parts = urlsplit(start)
    try:
        r = fetcher.get(urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", "")), sticky=False)
    except requests.RequestException:
        return None, []
    if r.status_code != 200:
        return None, []
    lines = r.text.splitlines()
    sitemaps = [ln.split(":", 1)[1].strip() for ln in lines if ln.lower().startswith("sitemap:")]
    rp = RobotFileParser()
    rp.parse(lines)
    return (rp if respect else None), sitemaps


def sitemap_urls(fetcher: Fetcher, start: str, declared: list[str]) -> list[str]:
    """Every page URL the site's sitemap(s) list (empty when there is none)."""
    parts = urlsplit(start)
    root = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    todo = [(u, 0) for u in (declared or [root + "/sitemap.xml", root + "/sitemap_index.xml"])]
    seen, urls = set(), []
    while todo and len(seen) < SITEMAP_FILES:
        url, depth = todo.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            r = fetcher.get(url, sticky=False)
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        body = r.content
        if body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except OSError:
                continue
        kind, locs = sc.parse_sitemap(body)
        if kind == "index" and depth < SITEMAP_DEPTH:
            todo += [(u, depth + 1) for u in locs]
        elif kind == "urls":
            urls += locs
    return urls


class Crawl:
    def __init__(self, start_url: str, dump_dir: Path) -> None:
        self.start = sc.norm_url(start_url)
        self.dump = dump_dir
        self.pages_dir = dump_dir / "pages"
        self.index_file = dump_dir / "site.json"
        self.include = sc.split_patterns(os.getenv("SITE_INCLUDE", ""))
        self.exclude = sc.split_patterns(os.getenv("SITE_EXCLUDE", ""))
        self.max_pages = max(0, int(os.getenv("SITE_MAX_PAGES", "0")))   # 0 = no limit
        self.respect_robots = os.getenv("SITE_RESPECT_ROBOTS", "true").lower() != "false"
        self.prefixes: list[str] = []
        self.pages: dict[str, dict] = {}       # url -> {"file", "final"}
        self.skipped: dict[str, str] = {}
        self.failed: dict[str, str] = {}
        self.queued: set[str] = set()
        self.dropped = 0                       # discovered but over the page limit
        self.generator = ""
        self.start_final = self.start
        self.lock = threading.Lock()
        self.robots: RobotFileParser | None = None

    # -- helpers --
    def canon(self, url: str) -> str:
        """Same page under 'www.' and without it is ONE page."""
        parts = urlsplit(url)
        if sc.host_key(parts.hostname) == sc.host_key(urlsplit(self.start).hostname):
            return urlunsplit((parts.scheme, urlsplit(self.start).netloc, parts.path, "", ""))
        return url

    def wanted(self, url: str) -> bool:
        return sc.in_scope(url, self.start, self.include, self.exclude, self.prefixes)

    def file_for(self, url: str) -> Path:
        return self.pages_dir / (hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".html")

    def load_previous(self) -> None:
        """Resume: keep the pages of an earlier run on the same start URL."""
        try:
            old = json.loads(self.index_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if old.get("start_url") != self.start:
            return
        self.pages = {u: p for u, p in old.get("pages", {}).items() if (self.pages_dir / p["file"]).exists()}
        # dead links and non-pages stay decided (no request); robots rules are re-checked
        self.skipped = {u: why for u, why in old.get("skipped", {}).items() if not why.startswith("blocked")}
        self.generator = old.get("generator", "")
        self.start_final = old.get("start_final", self.start)
        if self.pages:
            log(f"↻ Resuming: {len(self.pages)} page(s) already downloaded")

    def save(self, done: bool = False) -> None:
        self.dump.mkdir(parents=True, exist_ok=True)
        data = {
            "start_url": self.start, "start_final": self.start_final, "query": self.fetcher.sticky, "generator": self.generator,
            "updated_at": datetime.now().isoformat(timespec="seconds"), "complete": done and not self.failed,
            "limit_reached": bool(self.dropped), "pages": self.pages,
            "skipped": self.skipped, "failed": self.failed,
        }
        tmp = self.index_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.index_file)

    # -- one page --
    def fetch_one(self, url: str) -> tuple[str, bytes | None]:
        """(final url, html) -- or (url, None) after recording why there is none."""
        known = self.pages.get(url)
        if known:
            return known["final"], (self.pages_dir / known["file"]).read_bytes()
        if url in self.skipped:
            return url, None
        if self.robots is not None and not self.robots.can_fetch(ROBOTS_TOKEN, url):
            self.skipped[url] = "blocked by robots.txt"
            return url, None
        try:
            r = self.fetcher.get(url)
        except requests.RequestException as exc:
            self.failed[url] = str(exc)[:200]
            return url, None
        if r.status_code in DEAD_CODES:
            self.skipped[url] = f"dead link (HTTP {r.status_code})"
            return url, None
        if r.status_code != 200:
            self.failed[url] = f"HTTP {r.status_code}"
            return url, None
        ctype = r.headers.get("Content-Type", "").lower()
        if ctype and "html" not in ctype:
            self.skipped[url] = f"not a web page ({ctype.split(';')[0]})"
            return url, None
        if len(r.content) > MAX_BYTES:
            self.skipped[url] = "page too large"
            return url, None
        final = self.canon(sc.norm_url(r.url) or url)
        if not self.wanted(final):
            self.skipped[url] = "redirects outside the scope"
            return url, None
        with self.lock:
            if final != url and final in self.pages:
                self.skipped[url] = f"same page as {final}"
                return final, None
            name = self.file_for(final)
            name.parent.mkdir(parents=True, exist_ok=True)
            name.write_bytes(r.content)
            self.pages[final] = {"file": name.name, "final": final}
            if url != final:
                self.pages[url] = self.pages[final]
        return final, r.content

    def links_of(self, html: bytes, page_url: str) -> list[str]:
        soup = sc.parse(html)
        out = []
        for a in soup.find_all("a", href=True):
            u = sc.norm_url(a["href"], page_url)
            if u:
                u = self.canon(u)
                if self.wanted(u):
                    out.append(u)
        return out

    # -- whole crawl --
    def run(self, delay: float, workers: int, sticky: dict[str, str]) -> int:
        self.fetcher = Fetcher(delay, sticky)
        self.load_previous()
        self.robots, declared = load_robots(self.fetcher, self.start, self.respect_robots)

        # 1. the start page alone: it tells which other languages to leave out
        self.queued.add(self.start)
        final, html = self.fetch_one(self.start)
        if html is None:
            reason = self.failed.get(self.start) or self.skipped.get(self.start) or "no answer"
            log(f"✗ Cannot read {self.start}: {reason}")
            self.save()
            return 1
        self.start_final = final
        soup = sc.parse(html)
        self.generator = sc.meta_content(soup, "generator")
        self.prefixes = sc.locale_prefixes(soup, final)
        if sc.find_main(soup)[0] is None:
            log("⚠ The first page has no readable text: the site is probably built with "
                "JavaScript, which this mode cannot read (pages will come out empty).")
        log(f"  Site: {urlsplit(final).netloc}" + (f" ({self.generator})" if self.generator else ""))
        if self.prefixes:
            log(f"  Other languages left out: {', '.join(self.prefixes)}")

        # 2. sitemap + links of the start page
        wave: list[str] = []
        sitemap = sitemap_urls(self.fetcher, self.start, declared)
        log(f"  Sitemap: {len(sitemap)} URL(s)" if sitemap else "  No sitemap: following links only")
        for raw in sitemap + self.links_of(html, final):
            self.enqueue(raw, wave)

        # 3. breadth-first, one wave at a time, `workers` requests in parallel
        done = 1
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            while wave:
                futures = {pool.submit(self.fetch_one, u): u for u in wave}
                wave = []
                for fut in as_completed(futures):
                    url = futures[fut]
                    done += 1
                    page_final, content = fut.result()
                    if content is not None:
                        log(f"  [{done}/{len(self.queued)}] {sc.url_path(page_final)}")
                        for link in self.links_of(content, page_final):
                            self.enqueue(link, wave)
                    else:
                        why = self.failed.get(url) or self.skipped.get(url, "")
                        log(f"  [{done}/{len(self.queued)}] ⚠ {sc.url_path(url)} -- {why}")
                    if done % SAVE_EVERY == 0:
                        self.save()
        # what an earlier run found but today's scope or limit no longer wants is dropped
        self.pages = {u: p for u, p in self.pages.items() if u in self.queued or p["final"] in self.queued}
        self.save(done=True)
        return self.report()

    def enqueue(self, raw: str, wave: list[str]) -> None:
        url = sc.norm_url(raw)
        if not url:
            return
        url = self.canon(url)
        if url in self.queued or not self.wanted(url):
            return
        if self.max_pages and len(self.queued) >= self.max_pages:
            self.dropped += 1
            return
        self.queued.add(url)
        wave.append(url)

    def report(self) -> int:
        unique = {p["final"] for p in self.pages.values()}
        log(f"✓ {len(unique)} page(s) downloaded, {len(self.skipped)} skipped -> {self.dump}")
        if self.dropped:
            log(f"⚠ Page limit reached ({self.max_pages}): {self.dropped} more page(s) were found "
                f"but not downloaded -- raise 'Max pages' to get them.")
        if self.failed:
            for url, err in list(self.failed.items())[:10]:
                log(f"  ✗ {url}: {err}")
            log(f"✗ {len(self.failed)} page(s) could not be downloaded. The archive would be "
                f"incomplete: run the job again to retry them (downloaded pages are kept).")
            return 1
        return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: site_fetch.py <start_url> <dump_dir>", file=sys.stderr)
        return 1
    start_url, dump_dir = argv[0], Path(argv[1])
    if not sc.norm_url(start_url):
        log(f"✗ Not a web address: {start_url!r} (it must start with http:// or https://)")
        return 1
    sticky = dict(parse_qsl(urlsplit(start_url).query))
    crawl = Crawl(start_url, dump_dir)
    return crawl.run(float(os.getenv("DELAY", "0.5")), int(os.getenv("CAT_WORKERS", "8")), sticky)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
