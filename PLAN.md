# Evolution plan — Wiki Archive → NotebookLM

> Document meant to be executed by Sonnet in **two phases: AUDIT then EXECUTION**.
> For each work item: Sonnet **diagnoses first** (reproduces, reads the code/logs,
> confirms the cause), **presents its conclusion**, **only then implements**.
> Project principles to respect (see README §"Code quality principles"): DRY / no
> hardcoded values (everything in an env variable or at the top of a script), KISS/YAGNI, SOLID
> (one script per responsibility), Fail Fast, and **zero raw jargon on screen** (clear
> errors).

## Technical context (current state, already audited)

5-step pipeline driven by `scripts/run.sh`, orchestrated by `server.py` (FastAPI + embedded web UI), running in Docker (Linux) via `docker-compose.yml`:

1. **Dump** (`wikiteam3`) → `dump/wiki.xml`
2. **HTML extraction** (`scripts/extract.py`, MediaWiki `action=parse` API) → `html/*.html` + `categories.json` (page → direct categories)
3. **PDF conversion** (`scripts/convert.py`, WeasyPrint) — skipped if PDF not requested
4. **Category hierarchy** (`scripts/build_categories.py`, BFS API) → `category_groups.json` (category → pages, hierarchy propagated)
5. **File production**: `scripts/merge_pdf.py` (PDF) and `scripts/export_categories.py` (txt/md) → **one file per category**

Important facts noted during the initial audit:
- `build_categories.py` **already computes the parent→subcategory tree** (`direct_subcats`) but **discards it**: only the flattened, propagated mapping is saved. → The tree needed for the selection UI (work item D) already exists, it just needs to be persisted.
- Pause/Stop rely on `os.killpg` / `SIGSTOP` / `SIGCONT` / `SIGTERM` on the process group (`preexec_fn=os.setsid`). This is POSIX-only → only works inside the Linux container, not if `server.py` is run natively on Windows.
- `export_categories.py` does a **homegrown** HTML→text conversion (hand-rolled parser), with no MediaWiki noise filtering.
- Generation (steps 4–5) isn't reusable on its own: to regenerate with different options you have to rerun the whole pipeline (the `RERENDER` option needlessly re-extracts).

---

## Work item A — Reliable Pause / Stop

**User symptom:** "I can't pause or stop."

### A.1 Audit (mandatory before any code)
- Determine **where `server.py` actually runs**: inside the Docker container (POSIX signals OK) or natively on Windows (signals absent → `AttributeError`/silent failure). Check `docker-compose.yml`, how the user launches the app, and test an actual Pause by reading the logs.
- Check the **Pause → Stop** sequence: a process stopped by `SIGSTOP` ignores `SIGTERM` until it has received `SIGCONT`. `_kill()` sends `SIGTERM` without a prior `SIGCONT` → **stop-after-pause may never kill the process**. Confirm.
- Check that the **children** of `bash` (notably `wikiteam3dumpgenerator` and its Python sub-processes) are indeed in the **same group** and receive the signal. Confirm that no child does its own `setsid`.
- Check the **reader thread**: `for line in iter(proc.stdout.readline, "")` blocks on `readline()`. On Stop, as long as no line arrives, the loop doesn't see `status=="stopped"`. Confirm whether this leaves the UI **stuck**.

### A.2 Fixes (based on the diagnosis)
- In `_kill()`: send `SIGCONT` **before** `SIGTERM`, then, after a short delay with no death, `SIGKILL` to the group (escalation ladder). Idempotent, without exceptions surfaced on screen.
- If the app can run **outside Docker (Windows)**: make Pause/Stop **cross-platform**. Recommended approach: use `psutil` to suspend/resume/terminate the **process tree** (`proc.children(recursive=True)` + `suspend()`/`resume()`/`terminate()`/`kill()`), with a POSIX `killpg` fallback where available. No POSIX-only code path should break on Windows.
- Reader loop: make sure Stop **unblocks** the read (the process dying via SIGTERM/Kill makes `readline()` return ""), and guarantee `status` cleanly goes back to `stopped` + `__END__` pushed exactly once.
- **Verify clean resume**: after Stop, the "Resume" button must restart from existing data (dump/html already there) without redoing everything — already handled by the step-skip logic, needs re-testing.

### A.3 Success criteria
Pause genuinely brings CPU to zero (verifiable: no more progress in the logs); Resume picks back up; Stop kills the whole tree in < 5s **and** from the paused state. No raw technical trace displayed.

---

## Work item B — File count cap + smart grouping (NotebookLM)

**User symptom:** "TONS of text files, I can't choose the max number; it should adapt and group intelligently."

### B.1 Product target
- NotebookLM has a **source-per-notebook limit** (50 on free, 300 on Plus) and a **per-source limit** (~500,000 words). Expose a **`MAX_FILES`** parameter (default **50**, configurable via env + UI field) and a per-file limit **`NOTEBOOKLM_MAX_WORDS`** (default 500000, env). **No hardcoded value** scattered around.
- Goal: produce **at most `MAX_FILES` files**, by **grouping categories in a semantically coherent way** (not an arbitrary split), without exceeding the per-file limit.

### B.2 Grouping algorithm (new script `scripts/pack_files.py`, isolated responsibility — SOLID)
Inputs: the category tree (work item D persists `category_tree.json`), the size of each page (word count, measurable from the HTML), and the user's selection.

Recommended logic (KISS, deterministic):
1. Measure the **weight** (words) of each category = sum of its pages (deduplicating — see B.3).
2. **Bottom-up merge guided by the tree**: walk the hierarchy; fold subcategories into their parent as long as the resulting file stays under `NOTEBOOKLM_MAX_WORDS`. This keeps **thematic** groupings (e.g. all "Pistols" + "Rifles" under a single "Weapons" if it fits).
3. If the file count still exceeds `MAX_FILES`: **bin-packing** of the smallest categories/branches together (merge the closest neighbors in the tree first, never unrelated themes at random), until `≤ MAX_FILES`.
4. If a single category exceeds `NOTEBOOKLM_MAX_WORDS`: **split** it into `Name (part 1).md`, `Name (part 2).md`… (split at page boundaries, never mid-article).
5. Produce a **grouping plan** `packing_plan.json`: `{ output_file → [pages], readable_title, word_count }`. Step 5 (txt/md/pdf export) **consumes this plan** instead of the raw `category_groups.json`.

### B.3 Deduplication (important under the cap constraint)
- Today a page in N categories is copied N times → blows up volume and wastes NotebookLM quota.
- Add a **`DEDUP`** option (enabled by default when `MAX_FILES` is set): each page is assigned to **a single** file (its **most specific** category in the tree). Keep the ability to disable it (current "intentional duplication" behavior).

### B.4 UI
- **"Max file count"** field (numeric, default 50) next to the formats.
- After the scan phase, show a **live preview**: "Current selection → ~X files generated" (recalculated when `MAX_FILES` or the selection changes). Indicate if a category will be split.

### B.5 Success criteria
For a wiki with 300 categories and `MAX_FILES=50`, we get ≤ 50 coherent files, none over the per-source limit, readable groupings (meaningful names), no page lost.

---

## Work item C — Clean Markdown for NotebookLM (eliminate noise)

**User symptom:** "properly convert to markdown so the page is organized, but eliminate the noise."

### C.1 Audit
- Examine the actual HTML produced by `extract.py` (`action=parse` API) on 2–3 varied pages: identify typical MediaWiki noise — `.mw-editsection` / "[edit]", `.reference` / citation superscripts, `.navbox`, `.toc`, `.mw-jump-link`, `.noprint`, hatnotes/`.ambox`, "Retrieved from", coordinates, category footers, layout tables.
- Evaluate the current conversion (`export_categories.py`, homegrown parser): what it over-keeps / breaks.

### C.2 Implementation
- **Deterministic, offline HTML cleanup** step (operates on the already-downloaded HTML): remove the noise selectors above via a **configurable** list (constant at the top of the script or a file, not scattered). Use a robust HTML parser (`selectolax` or `lxml`/`BeautifulSoup`, already available).
- **HTML→Markdown conversion** via a proven library (`markdownify` or `html2text`) **instead of the homegrown parser**, tuned to: keep headings/lists/**tables in Markdown**/link text, discard the rest. `.txt` remains a readable rendering derived from the same cleanup.
- **Per-page structure** so NotebookLM can navigate it: title as `#`, clean separator between articles, optionally a short front-matter (title, source category). Compact blank lines.
- Keep `export_categories.py` as the entry point but **delegate** cleanup/conversion to a dedicated module (`scripts/clean_html.py` + `scripts/to_markdown.py`) — SOLID, reusable by the future packing.

### C.3 Success criteria
An opened `.md` shows a clean article: no "[edit]", no orphaned references, readable tables, hierarchical headings. Before/after comparison on 3 pages provided in the audit.

---

## Work item D — Scan the wiki and deselect (ergonomic UI by categories/subcategories)

**User symptom:** "be able to scan the wiki to deselect what I don't want, practical and ergonomic, organized into categories and subcategories, without spending ten years on it."

### D.1 Persist the tree (back-end)
- Modify `build_categories.py` to **also write `category_tree.json`**: nodes `{ category, parents, children (subcats), direct_pages, total_page_count, total_word_count }`. The info already exists (`direct_subcats` / `direct_pages`), it just needs to be exported. Handle multiple roots and cycles (already handled by `collect()`).
- Measure the **word weight** per page (reused by work item B) and aggregate it into the tree.

### D.2 Split the pipeline into two phases (SOLID, reusability)
- **SCAN phase** = steps 1→2→4 (dump + extraction + tree), **stops before** producing the files. Job status `scanned`.
- **GENERATE phase** = step 5 only (export per selection + `MAX_FILES` + formats), **no network**, reusable as many times as needed without re-downloading. New button/route `POST /api/jobs/{id}/generate` receiving `{ selection, max_files, formats, dedup }`.

### D.3 Selection UI (front-end, in `server.py`'s `_HTML`)
- **Collapsible tree** categories → subcategories → (optional) pages, with **tri-state checkboxes** (checked / unchecked / partial) that propagate to children and parents.
- For each node: **page count and estimated word/size counter**.
- Anti-"ten years of selection" tools:
  - **Select all / Deselect all** + select/deselect **by branch**.
  - **Instant search/filter** (hides non-matching nodes).
  - **Collapse / expand all**.
  - Sort (by name / by size).
  - **Live preview** of the resulting file count (linked to work item B).
- **Persistence** of the selection in `jobs.json` (key `selection`) → survives reloads and feeds regeneration.
- Ergonomics consistent with the existing dark theme (CSS variables already defined, no new visual identity).

### D.4 Success criteria
On a real wiki: the user expands the tree, unchecks 2 entire branches in 2 clicks, filters by keyword, sees "→ 34 files", clicks Generate, gets exactly the selection without re-downloading.

---

## Recommended execution order

1. **Work item A** (Pause/Stop) — independent, unblocks immediate use, small scope.
2. **Work item C** (Clean Markdown) — independent, improves output right away.
3. **Work item D** (tree persistence + scan/generate split + selection UI) — lays the infrastructure.
4. **Work item B** (cap + packing) — builds on D's tree and selection.

For each work item: **separate commit**, audit written before code, test on a small real wiki (e.g. a modest Fandom) before closing.

## Cross-cutting guardrails
- Every new parameter goes through `DEFAULTS` (server.py) + an env variable in `run.sh`/`docker-compose.yml` — **nothing hardcoded**.
- No regression on the existing PDF format.
- Error messages **clear, actionable**; never a raw traceback on screen.
- Don't reintroduce duplication between `merge_pdf.py` and `export_categories.py`: the **grouping plan** (B.2) becomes the single source consumed by both.
