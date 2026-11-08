# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

**Plain words:**
One command, `python scripts/verify.py`, now runs every check before a change is called done, and a git hook runs it before each push.

**Plain words:**
Website downloads no longer stop at 5000 pages: the "Max pages" option now defaults to 0, meaning no limit (type a number to cap it).

**Technical:**
- `SITE_MAX_PAGES` / `site_max_pages`: 0 is accepted and is the default (was 5000, minimum 1); the interface sends 0 instead of falling back to 5000.
- `scripts/verify.py` (tests, hard-coded URL search, layer violations) and `scripts/githooks/pre-push` (also requires `gh` logged in as `aznan-triks`; enable with `git config core.hooksPath scripts/githooks`).

## [1.2.0] - 2026-11-04

### Added

**Plain words:**
Wiki Archive now also reads documentation websites (such as `source2.wiki`, and sites built with Docusaurus, MkDocs, VitePress or Sphinx), not only MediaWiki wikis. Paste any page of the site: its pages are downloaded, sorted into categories following the site's own menus, and turned into the same PDF, Markdown or text files as before. The web interface was rebuilt: it detects the kind of site as you type, shows live how many files your selection will produce, lets you download the files (or all of them as one zip), and has a dark theme and a phone layout.

**Technical:**
- New website mode, chosen by `source` (`auto`, `mediawiki`, `site`; `auto` falls back to a website when no MediaWiki API answers). Steps 1 and 2 are `site_fetch.py` (sitemap plus link crawl, same site, hreflang language exclusion, `robots.txt`, global rate limit, parallel workers, retries with `Retry-After`, resumable through `dump/site.json`, sticky start-URL query parameters) and `site_extract.py` (main-content cascade for Docusaurus, MkDocs Material, VitePress, Starlight, Sphinx and generic pages; tab flattening; admonitions to quotes; code language kept). `build_site_categories.py` replaces the MediaWiki category step. Category placement uses the breadcrumb, JSON-LD `BreadcrumbList`, sidebar chain, then the URL path.
- Files are named `NNNN_slug` in sidebar order, so alphabetical order is reading order for packing, export and merged PDFs; changed or removed pages delete their stale PDFs.
- New options `source`, `site_max_pages`, `site_include`, `site_exclude` (validated for jobs and settings); advanced `SITE_*` environment variables.
- New endpoints: `GET /api/jobs/{id}/files/{name}`, `GET /api/jobs/{id}/download.zip`, `POST /api/detect` (reads at most `DETECT_MAX_BYTES`). Job metadata exposes `source_kind`.
- Interface moved from a string inside `server.py` to static files in `ui/` (`index.html`, `styles.css`, `util.js`, `tree.js`, `app.js`; no build step), served with a cache-busting version. Docker image and compose mount `ui/`.
- Shared modules `scripts/category_tree.py` (hierarchy propagation, used by both modes) and `scripts/page_style.py` (page CSS and wrapper).

### Changed

**Plain words:**
A job that ends in an error now says so on its page, and Markdown files no longer repeat each page's title twice at the top.

**Technical:**
- `export_categories.get_article` drops the page's `<h1>` after reading the title (it was repeated by the Markdown heading); code blocks use the language recorded by the extractor (`data-lang`).
- `detect_wiki.py` failure message no longer assumes a MediaWiki.
- Interface test hooks renamed (`allJobs` to `S.jobs`, `selectedCats()` to `Tree.selected()`, "Scan the wiki" button text to `[data-act=scan]`); the behaviour assertions are unchanged.

## [1.1.1] - 2026-11-02

### Changed

**Plain words:**
Grouping categories into a limited number of files is much faster on large wikis, and so is the live file-count preview in the interface. The files produced are exactly the same.

**Technical:**
- `pack_files.pack()`: step 3 (greedy merge of the smallest groups) now caches each group's word count in a dictionary updated on each merge iteration instead of re-summing word counts repeatedly. Output is identical; about 8x faster on large wikis.

## [1.1.0] - 2026-11-02

### Added

**Plain words:**
New optional settings allow jobs to output to isolated folders, assign collision-proof filenames for pages with special characters, and filter extracted content by MediaWiki namespaces.

**Technical:**
- Add "Separate output folder" toggle (`output_per_job`) writing output under `data/output/<wiki>--<job>`.
- Add "Unique file names" option (`unique_names`) using hashes to prevent special characters and slash collisions.
- Add working namespace selection (`namespaces`) supporting `0`, `0,14`, and `all`, triggering re-extraction when modified.

### Changed

**Plain words:**
PDF generation is now targeted only to pages included in the selected export categories instead of converting the entire wiki, and file output updates are atomic.

**Technical:**
- Selective PDF conversion: only pages targeted by active category exports are converted to PDF.
- Support arbitrary MediaWiki export schema versions beyond `export-0.11`.
- Safe output swap: staging folders are isolated per job, and existing outputs are safely renamed aside before replacement.

### Fixed

**Plain words:**
Fixed several pipeline bugs where PDF generation yielded empty output files, category selection dropped parent page content, and interrupted extractions failed to resume properly.

**Technical:**
- Convert missing PDFs during generation when skipped during initial scanning.
- Preserve multi-word and accented page titles (`Assault Rifle`, `Épée`) without flattening to ASCII, ensuring proper category assignment.
- Fix dead code in the no-API category grouping fallback that produced empty or generic Misc outputs.
- Category tree selection retains direct pages of partially selected parents using `own:<Category>` tags.
- Generation failures no longer erase existing outputs; builds take place in `<slug>.partial` and commit only on success.
- Resume mode no longer persists one-shot `clean` and `rerender` flags across subsequent runs.
- Prevent job deletion from removing outputs shared by concurrent jobs of the same wiki.
- API validation rejects invalid numeric, boolean, or format settings with HTTP 400 instead of crashing or persisting bad state.

### Security

**Plain words:**
Hardened the local web server against unauthorized cross-site requests and restricted external network exposure by default.

**Technical:**
- Refuse cross-origin mutation requests by verifying the `Origin` header matches `Host`.
- Bind server and Docker port publishing to `127.0.0.1` by default (`BIND_HOST` / `PUBLISH_HOST`).

## [1.0.0] - 2026-09-06

### Fixed

**Plain words:**
Unified pipeline naming rules, fixed split-part PDF naming, and enforced strict fail-fast behavior so errors stop the process instead of producing silently corrupt files.

**Technical:**
- `scripts/merge_pdf.py`: compute split part names from a fixed base (`Weapons_part1.pdf`, `Weapons_part2.pdf`) instead of chained prefixes; exit with code 1 on merge failure.
- Fail Fast across pipeline: abort on crashed text exports, word-count failures, 0 extracted pages, 0 produced files, or corrupt category grouping.
- Uncategorized pages: unify French `Divers` to English, env-configurable `MISC_CATEGORY` (default `Misc`).
- `server.py`: pass `NOTEBOOKLM_MAX_WORDS` and `MAX_FILES` from environment down to pipeline; log corrupt `settings.json` and failed imports.
- `scripts/extract.py`: log API text-mode fallback and honor rate limits (`DELAY`) during resume backfill.
- Align `MAX_PDF` fallback to 500 across UI, server, and scripts; log full failing command on step failures; unify sizes to English units (KB/MB/GB).

### Added

**Plain words:**
Introduced a centralized naming helper and a comprehensive automated test suite.

**Technical:**
- `scripts/wiki_names.py`: single source of truth for `page_stem`, `cat_stem`, `wiki_slug`, and `MISC_CATEGORY`.
- `tests/` + `pytest.ini` + `requirements-dev.txt`: 28 automated tests covering pipeline stages and naming rules.
- `Dockerfile`: target `*.py` scripts exclusively for dos2unix and executable permissions.

### Removed

**Plain words:**
Removed obsolete bash scripts, unreferenced files, and duplicate code.

**Technical:**
- Remove root `extract.py`, legacy `scripts/run.sh`, `scripts/run.sh.txt`, and `scripts/flatten.sh`.
- Remove dead imports, unused `ExportError` class, duplicate local naming helpers, and unused `DELETE /api/jobs/{job_id}` route.

### Security

**Plain words:**
Audited codebase to guarantee that local secret environment configurations are never leaked or referenced in source files.

**Technical:**
- Verified `.env` variables and secrets remain unreferenced in commits, logs, and docs.
