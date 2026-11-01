# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — 2026-11-01

Audit follow-up. Only findings reproduced on the code were fixed; each has a
regression test in `tests/test_audit_fixes.py`.

### Fixed

- PDF: the default Scan -> Generate path ended with "0 output files" because
  PDFs were converted in neither phase. Generation now converts missing PDFs.
- PDF: pages with a space or accent in their title (`Assault Rifle`, `Épée`)
  were renamed to ASCII before the merge and all fell into `Misc.pdf`. PDFs are
  now merged in place under their real names (`flatten()` removed).
- No-API fallback: the per-category grouping was dead code after a `return 1`;
  the job produced a single `Misc` file and reported success.
- A failed or invalid generation no longer wipes the previous output: files are
  built in `<slug>.partial` and swapped in only on success. An empty or unknown
  export format now fails before touching anything.
- Resume: `clean` / `rerender` are one-shot (they stayed on and erased the data
  of every later Resume); an interrupted HTML extraction is resumed instead of
  being treated as complete (`html/.extraction_complete` marks a finished one).
- Deleting a job no longer deletes `data/output/<wiki>` while another job of the
  same wiki exists.
- `extract.py` reports pages whose file name collides with another page
  (`A/B` vs `A:B`) instead of dropping them silently (fix of the naming itself
  is still open).

- Category selection: unchecking a subcategory no longer drops its parent's own
  pages (partial parents emit `own:<Category>`); selecting every category keeps
  uncategorized pages like "generate everything"; categories that only form a
  cycle are reachable in the tree; the preview now counts the `Misc` file.
- UI: the launch buttons come back when a job ends in error/stopped/purged while
  open (the log promised a "Resume" that did not exist); the generation panel
  hides once its data was freed; Scan refuses an empty format choice.
- API: create/patch reject invalid numbers, booleans and formats with a 400
  instead of persisting them.

### Security

- Cross-site writes are refused (`Origin` must match `Host`): a web page could
  delete every job through the user's browser.
- The server listens on `127.0.0.1` by default (`BIND_HOST`); `docker-compose.yml`
  publishes the port on `127.0.0.1` (`PUBLISH_HOST=0.0.0.0` in `.env` to open it).

## [Earlier] — 2026-09-06

Audit + fixes pass (pipeline stages fail fast, no duplicate conversion logic,
no hardcoded naming rules).

### Fixed

- `scripts/merge_pdf.py`: split categories produced chained part names
  (`Weapons_part1_part2.pdf`, `Weapons_part1_part2_part3.pdf`, ...) because
  the loop reassigned the output path before naming the next chunk. Names are
  now computed from a fixed base: `Weapons_part1.pdf`, `Weapons_part2.pdf`, ...
- `scripts/merge_pdf.py`: exit with code 1 when any category merge failed
  (previously the script always exited 0, so a merge crash never failed the job).
- Fail Fast across the pipeline (failed steps now abort explicitly instead of
  completing with silently corrupt/missing output):
  - `scripts/run.py` step 5: a crashed text export (`.md`/`.txt`) is fatal
    instead of a `⚠ Text export failed (PDFs unaffected)` warning + success.
  - `scripts/run.py` step 4: word-count measurement failure is fatal instead
    of continuing with all weights at 0 (which defeats the NotebookLM
    per-file limits).
  - `scripts/run.py`: abort when extraction produced 0 HTML pages, and when
    the pipeline produced 0 output files (instead of a `PIPELINE COMPLETE`
    banner over an empty folder).
  - `scripts/build_categories.py`: category API errors no longer degrade to a
    silently incomplete grouping; failed reads are collected and the scan exits 1.
  - `scripts/export_categories.py` / `scripts/merge_pdf.py`: an unreadable
    (corrupt) `category_groups.json` is fatal instead of dumping every page
    into one giant "everything" file.
- Uncategorized pages: code emitted the French `Divers` while the README
  documents `Misc.{ext}`; both now use a single English, env-configurable
  constant `MISC_CATEGORY` (default `Misc`) from `scripts/wiki_names.py`.
- `server.py`: `NOTEBOOKLM_MAX_WORDS` / `MAX_FILES` set in `.env` /
  docker-compose were read but then overridden by hardcoded `DEFAULTS`, so the
  pipeline never saw them. `DEFAULTS` now sources both from the environment,
  and every job inherits them (single source: `server.py` → job env →
  `run.py` → `pack_files.py`).
- `server.py`: corrupt `data/settings.json` was ignored with `except: pass`
  (saved settings vanished on every restart, unexplained); it is now logged.
  A failed `pack_files` import is likewise logged instead of silently skewing
  the packing preview.
- `server.py` `_packing_preview()`: unreadable `category_tree.json` /
  `page_words.json` silently fell back to `{}` and could preview different
  results than the actual generation; the preview now returns a clear error.
- `scripts/extract.py`: the switch to text mode after 5 consecutive API
  failures was completely silent; the first API error and the mode switch are
  now logged (the README troubleshooting table points users at exactly this).
- `scripts/extract.py`: the resume path back-fetched missing categories
  without the configured `DELAY` (ignored the polite rate limit) and could
  keep hammering a dead API; it now honors the delay and the failure cap.
- `scripts/run.py`: standalone `MAX_PDF` fallback was 100 while the README
  config table (and `server.py` `DEFAULTS`) documents 500 — aligned to 500;
  the UI form in `server.py` had the same stale `|| 100` fallback.
- `scripts/run.py`: a failing pipeline step logged
  `Failure in <python-interpreter>` (cmd[0]) — it now logs the full failing
  command, so the log says *which* step died.
- `scripts/run.py` `human_size()`: printed French units (`Ko`/`Mo`/`Go`/`To`)
  in job logs while the UI showed KB/MB/GB — unified to English units.
- `scripts/export_categories.py` / `scripts/merge_pdf.py`: stale comments and
  docstrings referring to `run.sh` (removed) and to `categories.json` (the
  argument is actually `category_groups.json`) corrected.
- `README.md`: data-layout fixed — job logs live next to the job folder
  (`jobs/<id>.log`, not inside it); `category_tree.json` and
  `page_words.json` added to the documented job layout.

### Added

- `scripts/wiki_names.py`: single source of truth for the naming rules that
  were duplicated in 6 places (`page_stem`, `cat_stem`, `wiki_slug`,
  `MISC_CATEGORY`). Used by `extract.py`, `build_categories.py`,
  `export_categories.py`, `merge_pdf.py`, `run.py` and `server.py` — drift
  between these silently broke grouping and output paths.
- `tests/` + `pytest.ini` + `requirements-dev.txt`: 28 automated tests
  covering every behavior fixed above (no network required; run with
  `python -m pytest`).
- `Dockerfile`: `dos2unix`/`chmod` steps now target only `*.py` (the shell
  scripts they referenced no longer exist — they would have broken the build).

### Removed

- `extract.py` (repo root): stale duplicate of `scripts/extract.py` with a
  different, older extraction logic — referenced nowhere.
- `scripts/run.sh`: the 328-line bash twin of `scripts/run.py`, kept alive
  next to the Python pipeline that actually runs (DRY violation, guaranteed
  drift). `scripts/run.sh.txt` (stale 4-step draft) and `scripts/flatten.sh`
  (already ported to `run.py::flatten()`) went with it.
- Dead code: unused `import time` / `import urlparse` in `server.py`, unused
  `ExportError` class in `export_categories.py`, unused `re`/`time` imports in
  `build_categories.py`, duplicate local `wiki_slug()` in `run.py`, duplicate
  `title_to_stem()` in `build_categories.py`, duplicate `cat_to_stem()` /
  `cat_to_filename()` in the exporters.
- `DELETE /api/jobs/{job_id}` route in `server.py`: never called (the UI and
  any external caller delete via `POST /api/jobs/bulk_delete`).

### Security audit

- No `.env` value is referenced or leaked anywhere in code, logs or docs;
  only variable *names* (`HOST_PROJECT_DIR`, `NOTEBOOKLM_MAX_WORDS`,
  `MAX_FILES`) appear in `docker-compose.yml` / code. `.env` stays ignored
  (`.gitignore`) and is not committed.
