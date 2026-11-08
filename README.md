# Wiki Archive → NotebookLM

Archive any MediaWiki site **or documentation website** (Docusaurus, MkDocs,
VitePress, Sphinx, …) into **one file per category**, in the format(s) of your
choice: **PDF**, **Markdown**, or **text** — ready for
[NotebookLM](https://notebooklm.google.com).

## What is it?

A **plug & play** Docker pipeline that downloads an entire wiki, **groups it by
category**, and produces **one file per category** in each checked format
(`Weapons.pdf`, `Weapons.md`, `Weapons.txt`…):

1. **Downloads** the raw wiki content (XML)
2. **Renders** each page to HTML (templates, tables, infoboxes resolved)
3. *(if PDF)* **Converts** each page to PDF via WeasyPrint
4. **Groups** pages by MediaWiki category (full hierarchy)
5. **Produces one file per category** in each checked format

Only step 3 (PDF rendering) depends on the format: if you do **not** check PDF, it
is skipped and only text files are produced (much faster). The rest of the
pipeline doesn't change — it's always "one file per category".

Result: `data/output/{wiki-hostname}/` contains one file per category and per
format, ready to import into NotebookLM.

---

## Documentation websites (website mode)

Paste any page of a documentation site, for example
`https://www.source2.wiki/Basics/working-on-content?game=cs2`. The kind of site is
detected from the address ("Type of site" lets you force it). In website mode the
first two steps are replaced; **everything after them is identical** (selection, PDF /
Markdown / text, file packing).

1. **Download**: starts from the page you gave, adds the sitemap, then follows the
   links (menus included). Same site only, other languages and tag/search pages are
   skipped, `robots.txt` is respected, requests are rate-limited (`Delay`) and run in
   parallel (`Parallel requests`). It is **resumable**: a rerun reads what is already on
   disk and fetches only what is missing. Dead links (404/410) are remembered and
   skipped; any other failure stops the run so a rerun can finish the job.
2. **Extraction**: keeps the main content only (menus, footers, "edit this page" and
   "last updated" lines removed), flattens tabs, turns admonitions into quotes, keeps code
   blocks with their language, makes links absolute. Query parameters of your start
   address (`?game=cs2`) are kept on every page.
3. **Categories**: taken from the breadcrumb, else the structured breadcrumb data, else
   the sidebar, else the URL path. Files are numbered in sidebar order, so a merged PDF
   reads like the site.

| Option | Default | Effect |
|--------|---------|--------|
| **Type of site** | auto | `auto`, MediaWiki wiki or documentation website |
| **Max pages (website)** | 0 (no limit) | Discovery stops after this many pages; 0 means no limit |
| **Only these paths** | all | Comma-separated patterns on the URL path, e.g. `/docs/*, /guide/*` |
| **Skip these paths** | – | Same syntax, e.g. `/blog/*` |

Advanced (environment variables): `SITE_RESPECT_ROBOTS` (default `true`), `SITE_TIMEOUT`,
`SITE_RETRIES`, `SITE_BACKOFF`, `SITE_MAX_BYTES`, `SITE_USER_AGENT`, `SITE_DEFAULT_EXCLUDE`,
`SITE_ASSET_EXT`, `SITE_MIN_TEXT_CHARS`. Pages that need JavaScript to show their content
are not supported (the page is read as the server sends it).

---

## 5-step pipeline

### 1️⃣ WIKI DUMP
Downloads the raw content via **wikiteam3**. Creates an XML file containing all articles.

- **Resumes automatically** if the dump is incomplete
- **Forces Internet Archive** by default (faster if the wiki is on it) — can be disabled
- Creates `{job_dir}/dump/wiki.xml` (~1–50 MB depending on wiki size)

### 2️⃣ HTML EXTRACTION
Parses the XML and generates HTML for each page.

- **API mode** (recommended): calls the MediaWiki `action=parse` API → faithful rendering
  - Tables, infoboxes, Lua templates, MediaWiki modules → all rendered correctly
  - Also fetches each page's direct categories
  - Throughput: ~0.5–1 page/second (compatible with the configured 0.5s delay)

- **Text mode** (fallback if API unavailable): basic wikitext extraction
  - Simple conversion to HTML (tables, lists, headings)
  - No templates or modules

Creates `{job_dir}/html/*.html` + `{job_dir}/categories.json` (page → categories).

### 3️⃣ PDF CONVERSION
Converts each HTML page to PDF in parallel via **WeasyPrint**.

- **Parallelization**: 4 workers by default (configurable)
- **Resume**: skips already-generated PDFs
- Creates `{job_dir}/pdf/*.pdf`

### 4️⃣ CATEGORY HIERARCHY
Builds the full MediaWiki category tree.

- Queries the `categorymembers` API for each category
- **Propagates recursively**: if "Pistols" ⊂ "Weapons", Pistols' pages also appear in Weapons
- Handles complex hierarchies (nested categories)
- Produces `{job_dir}/category_groups.json` (category → pages)

### 5️⃣ PER-CATEGORY FILE PRODUCTION
For **each category**, a file is written **in each checked format**. It's the
same grouping regardless of format — only the extension changes.

| Format | Output | Content |
|--------|--------|---------|
| `pdf` | `Weapons.pdf` | Category pages merged into a PDF (max ~500 pages) |
| `md`  | `Weapons.md`  | Category pages in Markdown (headings, lists) |
| `txt` | `Weapons.txt` | Category pages in readable plain text |

- **Format selection in the UI**: `PDF` / `Markdown` / `Text` checkboxes.
  PDF isn't mandatory — you can check only `.md` and/or `.txt`.
- **Pages in multiple categories**: present in every relevant file (intended for NotebookLM).
- **Uncategorized pages** → `Misc.{ext}`.
- **Everything goes into the same folder**: `data/output/{wiki-hostname}/` (one file per
  category and per format), ready to import into NotebookLM. A new generation replaces
  that folder only once it succeeded. Tick **Separate output folder** to give a job its
  own `data/output/{wiki-hostname}--{job}/` instead.
- Step 3 (PDF rendering) and its "Workers / Max pages" options only apply to the PDF format.
- After the job, the UI lists the files plus a **"📂 Copy path"** button
  (to paste into File Explorer). For a **full Windows path**, set
  `HOST_PROJECT_DIR` in `.env` then run `docker compose up -d`.

**Regenerate text files only** (no network, from an already-extracted job):
```bash
docker compose exec wiki-archive \
  python3 /scripts/export_categories.py \
    /data/jobs/<job-id>/html \
    /data/jobs/<job-id>/category_groups.json \
    /data/output/<wiki> \
    txt,md
```

---

## Web interface

Go to **http://localhost:8080** after `docker compose up -d`.

The interface has no password, so the port is published on this machine only
(`127.0.0.1`). To open it to other devices on your network, put
`PUBLISH_HOST=0.0.0.0` in `.env` -- only on a network you trust.
When running `python server.py` yourself, the server listens on `127.0.0.1`
only; set `BIND_HOST=0.0.0.0` (and `PORT`) in the environment to change that.

### Create a job
1. Click **New job** and paste the address of the wiki or site (any page). A line under
   the field tells what was detected.
2. Adjust the options if needed (all under **More options**, except the file count and formats):
   - **Namespaces** (MediaWiki): `0` = main articles (default), `0,14` adds category pages,
     `all` = everything. Changing it on an existing job needs a **New full download**
   - **Delay**: seconds between requests (0.5s = respectful)
   - **Include images**, **Separate output folder**, **Unique file names** (MediaWiki)
   - **New full download**: wipe everything and start from scratch
   - **Re-render output**: rebuild the PDFs without downloading again
   - **Skip Internet Archive** (MediaWiki)
   - **Max pages / Only these paths / Skip these paths** (website)
3. Click **Scan**: it lists the categories. Then pick what to keep and click
   **Generate selection** (or **Generate all**). **Do everything at once** runs both.

### Choose what to keep
- Tree of categories (lazy, safe with cycles); a category includes its sub-categories.
- Each bar shows the category's share of the per-file word limit.
- A live gauge shows how many files the selection will produce against the NotebookLM
  limit, the largest file, and the list of files that will be created.
- **All / None / Collapse / Sort** and a filter box. The selection is remembered.

### Manage a job
- **Pause** suspends the process (and its children) in memory, **Resume** continues,
  **Stop** stops without losing data.
- **Delete** (with a few seconds to undo). **Manage** in the sidebar selects several jobs
  at once, and cleans up stopped or failed ones.
- **Storage**: shows the disk space used, clears the PDF cache or frees the downloaded data.

### Job page
- **Stages** (Source, Scan, Choose, Generate, Files) and the status of the job.
- **Progress** and **Log** (real-time, with warnings-only filter, copy, download).
- **Generated files**: each file can be downloaded, or all of them as one `.zip`; the
  folder path can be copied (`data/output/{wiki}/`).
- **Settings** (gear icon): defaults applied to new jobs. Light / dark / automatic theme.

---

## Configuration options

| Option | Default | Effect |
|--------|--------|-------|
| **Type of site** | auto | MediaWiki wiki or documentation website (see above) |
| **Namespaces** | `0` | Which namespaces to archive (0=articles, 1=talk, 10=templates, 14=categories, `all`) |
| **Separate output folder** | ✗ | The job writes to `data/output/<wiki>--<job>` and never overwrites another job's files |
| **Unique file names** | ✗ | Titles with special characters (`A/B` vs `A:B`) get a short hash so no page is lost; needs a new dump |
| **Delay** | 0.5s | Pause between wikiteam3 API calls (respects rate limit) |
| **Images** | ✓ | Download the wiki's images |
| **New dump** | ✗ | Wipes everything → starts from scratch (~25 min for medium wikis) |
| **Regenerate** | ✗ | Keeps the dump, re-extracts HTML/PDF (~5 min) |
| **Skip Internet Archive** | ✓ | Goes straight to the wiki, doesn't check Archive.org |
| **PDF workers** | 4 | Number of parallel workers for WeasyPrint |
| **Max pages per PDF** | 500 | Page limit per merged PDF (NotebookLM safety) |

---

## Data structure

```
data/
├── jobs/
│   ├── 20260507-194427-ab55/          # Job ID (timestamp + UUID)
│   │   ├── dump/
│   │   │   ├── wiki.xml               # Raw dump (can be very large)
│   │   │   ├── config.json            # wikiteam3 metadata
│   │   │   ├── site.json              # Website mode: pages, skipped, failed
│   │   │   ├── pages/<hash>.html      # Website mode: downloaded pages
│   │   │   └── ...
│   │   ├── html/
│   │   │   ├── SCAR-H.html
│   │   │   ├── Pistol.html
│   │   │   └── ...
│   │   ├── pdf/
│   │   │   ├── SCAR-H.pdf
│   │   │   ├── Pistol.pdf
│   │   │   └── ...
│   │   ├── flat/
│   │   │   └── (flat copy for merging)
│   │   ├── categories.json            # Page → [direct categories]
│   │   ├── site_hierarchy.json        # Website mode: category tree before propagation
│   │   ├── category_groups.json       # Category → [pages with hierarchy]
│   │   ├── category_tree.json         # Category tree (selection UI + packing)
│   │   ├── page_words.json            # Word weight per page
│   │   └── ...
│   ├── 20260507-194427-ab55.log       # Raw logs (one file per job)
│   └── jobs.json                      # Metadata for all jobs
│
└── output/
    └── wiki.play.eco/                 # Named after the hostname
        ├── Weapons.pdf                # All weapons
        ├── Pistols.pdf                # Just the pistols
        ├── Melee_Weapons.pdf
        └── Misc.pdf                   # Uncategorized
```

---

## Wiki examples

### ✅ Fandom (example: Final Stand Two)
```
URL: https://finalstandtwo.fandom.com/wiki/Weapons
```
- 200+ pages = ~50 min (5 min dump + 45 min processing)
- Result: 10 PDFs per category (Weapons, Pistols, Rifles, etc.)

### ✅ Standalone MediaWiki wikis (Eco Wiki)
```
URL: https://wiki.play.eco/en/Eco_Wiki
```
- Auto-detects access type (API vs index.php)
- Full hierarchy preserved

### ⚠️ Wikipedia
- **Feasible but huge**: 6M+ articles = days of computation
- For a specific topic: use a partial category dump

---

## Troubleshooting

| Problem | Cause | Solution |
|----------|-------|----------|
| "ERROR: wiki unreachable from..." | URL badly detected | Check the URL (must point to a wiki page) |
| "wiki.xml not found" | Dump failed before completion | Check "New dump" and restart |
| PDFs nearly empty (plain text) | Text mode active | Check that the wiki's API is reachable |
| Duplicates in PDFs | Bug fixed | Restart with "Regenerate rendering" |
| Many uncategorized files → huge `Misc.pdf` | Poorly categorized wiki | Normal, accept it or adjust in NotebookLM |

---

## Native install (no Docker, recommended)

Requirements: Python 3.11 or 3.12.

Double-click `run.bat` — creates the venv, installs dependencies, starts the server on
http://127.0.0.1:8080 and opens the browser. `data/` is created automatically next to the
project (dump, HTML, PDF, outputs).

The pipeline (`scripts/run.py`) and pause/resume (`psutil`) are 100% Python — no
dependency on bash/coreutils/POSIX signals, runs natively on Windows/Linux/macOS.

### PDF export on Windows

PDF export depends on [WeasyPrint](https://weasyprint.org/), which requires the GTK3 runtime
(pango/cairo/gdk-pixbuf), not installable via pip on Windows. Without this runtime, each
PDF conversion fails individually with a clear message in the logs — the rest of the
pipeline (dump, extraction, Markdown/text export) continues normally. To enable it,
install the
[GTK3 Runtime Environment](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases).

## Docker install (optional)

```bash
# 1. Clone and enter the directory
git clone <repo> && cd wiki-archive

# 2. Start the container
docker compose up -d

# 3. Open the browser
http://localhost:8080
```

**Persistent volumes:**
- `./data/` → `/data` — PDF and log storage
- `./scripts/` → `/scripts:ro` — scripts (read-only, rebuilt on every startup to fix Windows line endings)
- `./ui/` → `/app/ui:ro` — the web interface (static files)

---

## Tests

```bash
pip install -r requirements-dev.txt   # adds pytest (runtime deps: requirements.txt)
python -m pytest
```

Tests live in `tests/`, need no internet (website mode is tested against small local
sites shaped like Docusaurus and MkDocs), and only touch a temporary data dir
(`DATA_DIR` env is honored). Tests that exercise optional libraries
(`requests`, `beautifulsoup4`, `markdownify`, `pikepdf` — all already listed in
`requirements.txt`) auto-skip when the library is missing. The interface tests drive a
real browser and auto-skip unless `playwright` and Chromium are installed
(`pip install playwright && playwright install chromium`).

## Limitations & notes

- **No wiki modifications**: this is an archiver, not a full replica
- **Lost metadata**: history, discussions, permissions → not archived
- **Internal links**: kept but point to nothing in NotebookLM (acceptable)
- **Large files**: 10,000+ pages = 2–4 hours
- **Updates**: rerun the job to re-download (fast resume with the existing dump)

---

## Code quality principles

All code in this project follows these principles. Please respect them for any contribution.

- **DRY & No Hardcode** — No duplication. Zero hardcoded values. Every constant goes into an environment variable (`docker-compose.yml` / `.env`) or the top of a script, never scattered through the code.

- **KISS & YAGNI** — Simplest solution first. No feature added "just in case": code what's needed now, not a speculative architecture.

- **SOLID** — Strict architecture, isolated responsibilities: each step is a dedicated script (`extract.py`, `convert.py`, `merge_pdf.py`, `export_categories.py`). Adding an output format = adding a case in step 5, without touching the rest of the pipeline.

- **Fail Fast** — An error or corrupted data = immediate, explicit stop. No dubious intermediate state tolerated.

- **Technical ergonomics** — Zero raw technical jargon on screen (no Python traceback thrown at the user). Errors are **clear and actionable**.

---

## Credits & technologies

- **wikiteam3**: wiki download
- **WeasyPrint**: HTML → PDF
- **mwparserfromhell**: wikitext parsing
- **pikepdf**: PDF merging
- **FastAPI**: web server + API
- **Beautiful Soup**: page extraction in website mode
- **MediaWiki API**: page rendering

---

**Made with ❤️ for archiving the internet.**
