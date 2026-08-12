# Wiki Archive → NotebookLM

Archive any MediaWiki site into **one file per category**, in the format(s) of
your choice: **PDF**, **Markdown**, or **text** — ready for
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
  category and per format), ready to import into NotebookLM.
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

### Create a job
1. Click **"+ New"**
2. Enter the wiki URL (any page)
3. Adjust options (optional):
   - **Namespaces**: `0` = main articles (default)
   - **Delay**: seconds between requests (0.5s = respectful)
   - **Images**: download the wiki's images
   - **New dump**: wipe everything and start from scratch
   - **Regenerate rendering**: re-extracts HTML/PDF without re-downloading the dump (~3x faster)
   - **Skip Internet Archive**: don't look for the wiki on Archive.org
4. Click **"Create and run"**

### Manage a job
- **▶ Run**: starts a pending job
- **⏸ Pause**: suspends the process (and its children) in memory, without killing it
- **▶ Resume**: continues from where it left off (or restarts if fully stopped)
- **⏹ Stop**: stops without losing data
- **↩ Restart**: starts over from the existing dump
- **🗑 Delete**: fully erases (data + logs)

### Sidebar
- Status of each job (colors = state)
- Relative date ("2h", "yesterday")
- Click to see details + live logs

### Job details
- **Configuration**: view/edit parameters before restarting
- **Progress**: visual bar of the 5 steps
- **Log**: real-time logs (SSE streaming)
- **Files**: lists the final PDFs with sizes, path `data/output/{wiki}/`

---

## Configuration options

| Option | Default | Effect |
|--------|--------|-------|
| **Namespaces** | `0` | Which namespaces to fetch (0=articles, 10=templates, 14=categories) |
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
│   │   ├── category_groups.json       # Category → [pages with hierarchy]
│   │   ├── 20260507-194427-ab55.log   # Raw logs
│   │   └── ...
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

---

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
- **MediaWiki API**: page rendering

---

**Made with ❤️ for archiving the internet.**
