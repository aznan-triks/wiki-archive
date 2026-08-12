#!/bin/bash
set -euo pipefail

# ── parameters ───────────────────────────────────────────────────────────────
: "${WIKI_API:?WIKI_API variable missing}"
: "${JOB_DIR:?JOB_DIR variable missing}"
NAMESPACES="${NAMESPACES:-0}"
DELAY="${DELAY:-0.5}"
MAX_PDF="${MAX_PDF:-100}"
IMAGES="${IMAGES:-true}"
CLEAN="${CLEAN:-false}"
WORKERS="${WORKERS:-4}"
FORCE="${FORCE:-true}"
PHASE="${PHASE:-all}"           # all | scan | generate
MAX_FILES="${MAX_FILES:-0}"     # 0 = no cap
NOTEBOOKLM_MAX_WORDS="${NOTEBOOKLM_MAX_WORDS:-500000}"   # per-file limit (words)
DEDUP="${DEDUP:-false}"         # each page in a single category
CAT_WORKERS="${CAT_WORKERS:-8}" # category scan parallelism
SELECTION_FILE="${SELECTION_FILE:-${JOB_DIR}/selection.json}"

# ── requested export formats ────────────────────────────────────────────────
EXPORT_FORMATS="${EXPORT_FORMATS:-pdf}"
[[ "${EXPORT_FORMATS}" == "all" ]] && EXPORT_FORMATS="pdf,md,txt"
has_fmt() { [[ ",${EXPORT_FORMATS}," == *",$1,"* ]]; }

WANT_PDF=false;  has_fmt pdf && WANT_PDF=true
DOC_FORMATS=$(echo "${EXPORT_FORMATS}" | tr ',' '\n' | grep -vx 'pdf' | paste -sd, - || true)
WANT_DOCS=false; [[ -n "${DOC_FORMATS}" ]] && WANT_DOCS=true

DUMP_DIR="${JOB_DIR}/dump"
HTML_DIR="${JOB_DIR}/html"
PDF_DIR="${JOB_DIR}/pdf"
FLAT_DIR="${JOB_DIR}/flat"

WIKI_SLUG=$(python3 -c "
from urllib.parse import urlparse; import re, sys
url = sys.argv[1]
host = urlparse(url).hostname or url
print(re.sub(r'[^\w.-]', '_', host))
" "${WIKI_API}" 2>/dev/null || echo "wiki")
OUT_DIR="/data/output/${WIKI_SLUG}"

log()  { echo "[$(date '+%H:%M:%S')] $*"; }

_step_start=0
begin_step() { _step_start=$(date +%s); }
end_step()   {
    local elapsed=$(( $(date +%s) - _step_start ))
    log "✓ Done in ${elapsed}s"
}
skip_step() { log "↩ Step already complete -- skipped ($*)"; }

# ── startup info ─────────────────────────────────────────────────────────────
echo "════════════════════════════════════════"
echo "  Wiki Archive Pipeline"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════"
log "Wiki URL    : ${WIKI_API}"
log "Output      : ${OUT_DIR}"
log "Job dir     : ${JOB_DIR}"
log "Phase       : ${PHASE}"
log "Namespaces  : ${NAMESPACES} | Delay: ${DELAY}s | Images: ${IMAGES}"
log "PDF workers : ${WORKERS} | Max PDF : ${MAX_PDF} | Force : ${FORCE}"
log "Formats     : ${EXPORT_FORMATS} | Max files : ${MAX_FILES} | Dedup : ${DEDUP}"
DISK=$(df -h "${JOB_DIR}" 2>/dev/null | awk 'NR==2 {print $4 " free"}' || echo "unknown")
log "Disk        : ${DISK}"
echo ""

# ── cleanup depending on mode (skipped for generate) ─────────────────────────
if [[ "${PHASE}" != "generate" ]]; then
    if [[ "${CLEAN}" == "true" ]]; then
        log "⚠ Full cleanup -- removing all previous data"
        rm -rf "${DUMP_DIR}" "${HTML_DIR}" "${PDF_DIR}" "${FLAT_DIR}" "${OUT_DIR}"
    elif [[ "${RERENDER:-false}" == "true" ]]; then
        log "♻ Re-rendering -- removing HTML/PDF (dump kept)"
        rm -rf "${HTML_DIR}" "${PDF_DIR}" "${FLAT_DIR}" "${OUT_DIR}"
    fi
fi

# ── 1. dump ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━ [1/5] WIKI DUMP ━━━"

if [[ "${PHASE}" == "generate" ]]; then
    log "↩ Skipped (generate phase)"
else
    XML_FILE=$(find "${DUMP_DIR}" -maxdepth 2 -name "*.xml" ! -name "*.7z" 2>/dev/null | head -1 || true)

    if [[ -n "${XML_FILE}" ]] && [[ -f "${DUMP_DIR}/config.json" ]]; then
        XML_SIZE=$(du -sh "${XML_FILE}" | awk '{print $1}')
        skip_step "XML found: ${XML_FILE} (${XML_SIZE})"
    else
        begin_step

        log "Detecting MediaWiki access type..."
        WIKI_FLAGS=$(python3 /scripts/detect_wiki.py "${WIKI_API}")
        ACCESS_FLAG=$(echo "${WIKI_FLAGS}" | awk '{print $1}')
        WIKI_URL=$(echo "${WIKI_FLAGS}"   | awk '{print $2}')
        log "Access detected: ${ACCESS_FLAG} ${WIKI_URL}"

        DUMP_ARGS=(
            "${ACCESS_FLAG}" "${WIKI_URL}"
            --xml
            --curonly
            --namespaces "${NAMESPACES}"
            --delay "${DELAY}"
            --retries 5
            --path "${DUMP_DIR}"
        )
        [[ "${IMAGES}" == "true" ]] && DUMP_ARGS+=(--images)
        [[ "${FORCE}"  == "true" ]] && DUMP_ARGS+=(--force)

        if [[ -f "${DUMP_DIR}/config.json" ]]; then
            SAVED_URL=$(python3 -c "
import json
try:
    d = json.load(open('${DUMP_DIR}/config.json'))
    print(d.get('api') or d.get('index') or '')
except Exception:
    print('')
" 2>/dev/null || echo "")
            if [[ "${SAVED_URL}" == "${WIKI_URL}" ]]; then
                log "Valid resume (${WIKI_URL})"
                DUMP_ARGS+=(--resume)
            else
                log "Stale config (${SAVED_URL} != ${WIKI_URL}) -> new dump"
                rm -rf "${DUMP_DIR}"
            fi
        fi

        log "Running: wikiteam3dumpgenerator ${DUMP_ARGS[*]}"
        wikiteam3dumpgenerator "${DUMP_ARGS[@]}"

        log "Contents of ${DUMP_DIR}:"
        find "${DUMP_DIR}" -maxdepth 2 2>/dev/null | sort | while read -r f; do
            [[ -f "$f" ]] && log "  [$(du -sh "$f" 2>/dev/null | awk '{print $1}')] $f" || log "  $f/"
        done

        XML_FILE=$(find "${DUMP_DIR}" -maxdepth 2 -name "*.xml" ! -name "*.7z" 2>/dev/null | head -1 || true)
        if [[ -z "${XML_FILE}" ]]; then
            log "⚠ No .xml file found in ${DUMP_DIR}"
            exit 1
        fi
        XML_SIZE=$(du -sh "${XML_FILE}" | awk '{print $1}')
        log "XML file: ${XML_FILE} (${XML_SIZE})"
        end_step
    fi
fi

# ── 2. HTML extraction ────────────────────────────────────────────────────────
echo ""
echo "━━━ [2/5] HTML EXTRACTION ━━━"

API_URL=$(python3 -c "
import json
try:
    d = json.load(open('${DUMP_DIR}/config.json'))
    u = d.get('api') or ''
    if not u and d.get('index'):
        u = d['index'].replace('index.php', 'api.php')
    print(u)
except Exception:
    print('')
" 2>/dev/null || echo "")
CATEGORIES="${JOB_DIR}/categories.json"

if [[ "${PHASE}" == "generate" ]]; then
    log "↩ Skipped (generate phase)"
    HTML_COUNT=$(find "${HTML_DIR}" -name "*.html" 2>/dev/null | wc -l || echo 0)
else
    HTML_COUNT=$(find "${HTML_DIR}" -name "*.html" 2>/dev/null | wc -l || echo 0)
    if [[ "${HTML_COUNT}" -gt 0 ]]; then
        skip_step "${HTML_COUNT} HTML files already present"
    else
        begin_step
        if [[ -n "${API_URL}" ]]; then
            log "Render API: ${API_URL}"
        else
            log "⚠ API not found in config.json -- basic rendering (no templates)"
        fi
        log "Source: ${XML_FILE} -> ${HTML_DIR}"
        python3 /scripts/extract.py "${XML_FILE}" "${HTML_DIR}" "${API_URL}" "${DELAY}" "${CATEGORIES}"
        HTML_COUNT=$(find "${HTML_DIR}" -name "*.html" 2>/dev/null | wc -l || echo 0)
        log "${HTML_COUNT} HTML files generated"
        end_step
    fi
fi

# ── 3. PDF conversion (skipped for scan and generate) ─────────────────────────
echo ""
echo "━━━ [3/5] PDF CONVERSION ━━━"

if [[ "${PHASE}" == "scan" ]] || [[ "${PHASE}" == "generate" ]]; then
    log "↩ Skipped (phase ${PHASE})"
    PDF_COUNT=$(find "${PDF_DIR}" -name "*.pdf" 2>/dev/null | wc -l || echo 0)
elif [[ "${WANT_PDF}" != "true" ]]; then
    log "Skipped -- PDF format not requested"
else
    PDF_COUNT=$(find "${PDF_DIR}" -name "*.pdf" 2>/dev/null | wc -l || echo 0)
    if [[ "${PDF_COUNT}" -ge "${HTML_COUNT}" ]] && [[ "${PDF_COUNT}" -gt 0 ]]; then
        PDF_SIZE=$(du -sh "${PDF_DIR}" 2>/dev/null | awk '{print $1}' || echo "?")
        skip_step "${PDF_COUNT} PDFs already present (${PDF_SIZE})"
    else
        begin_step
        log "Source: ${HTML_DIR} -> ${PDF_DIR} (${WORKERS} workers)"
        python3 /scripts/convert.py "${HTML_DIR}" "${PDF_DIR}" "${WORKERS}"
        PDF_COUNT=$(find "${PDF_DIR}" -name "*.pdf" 2>/dev/null | wc -l || echo 0)
        PDF_SIZE=$(du -sh "${PDF_DIR}" 2>/dev/null | awk '{print $1}' || echo "?")
        log "${PDF_COUNT} PDFs -- total size: ${PDF_SIZE}"
        end_step
    fi
fi

# ── 4. category hierarchy ─────────────────────────────────────────────────────
echo ""
echo "━━━ [4/5] CATEGORY HIERARCHY ━━━"

CAT_GROUPS="${JOB_DIR}/category_groups.json"

if [[ "${PHASE}" == "generate" ]]; then
    log "↩ Skipped (generate phase)"
else
    begin_step
    # Measure the word weight of each page (feeds the tree and the grouping)
    PAGE_WORDS="${JOB_DIR}/page_words.json"
    if [[ -d "${HTML_DIR}" ]]; then
        log "Measuring page word counts..."
        python3 /scripts/measure_words.py "${HTML_DIR}" "${PAGE_WORDS}" \
            || log "⚠ Word count measurement failed (weights shown as 0)"
    fi
    if [[ -n "${API_URL:-}" ]] && [[ -f "${CATEGORIES}" ]]; then
        log "Building hierarchy via API (${CAT_WORKERS} in parallel)..."
        CAT_WORKERS="${CAT_WORKERS}" python3 /scripts/build_categories.py "${API_URL}" "${CATEGORIES}" "${CAT_GROUPS}"
    else
        log "⚠ No API or categories.json missing -- direct grouping without hierarchy"
        python3 -c "
import json, re
from collections import defaultdict
with open('${CATEGORIES}') as f:
    page_cats = json.load(f)
groups = defaultdict(list)
for stem, cats in page_cats.items():
    for cat in (cats or ['Divers']):
        groups[cat].append(stem)
with open('${CAT_GROUPS}', 'w') as f:
    json.dump({k: sorted(v) for k,v in groups.items()}, f, ensure_ascii=False, indent=2)
print(f'  {len(groups)} categories')
"
    fi
    end_step
fi

# ── Stop after scan ────────────────────────────────────────────────────────────
if [[ "${PHASE}" == "scan" ]]; then
    echo ""
    echo "════════════════════════════════════════"
    echo "  ✓ SCAN COMPLETE -- $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  Tree in ${JOB_DIR}/category_tree.json"
    echo "════════════════════════════════════════"
    exit 0
fi

# ── 4.5 Preparing groups: selection THEN grouping ──────────────────────────────
# Order matters: first filter by the user's selection, then group the
# retained subset. This way the grouping (which can rename/
# merge categories) operates only on what the user wants, and the number of
# files produced matches the preview exactly.
TREE_FILE="${JOB_DIR}/category_tree.json"
ADD_DIVERS="true"   # add pages without a category; disabled if a selection is active

# 1) Filter by selection -- only in the generate phase (a full run = the whole wiki)
if [[ "${PHASE}" == "generate" ]] && [[ -s "${SELECTION_FILE}" ]]; then
    SELECTED_GROUPS="${JOB_DIR}/category_groups_selected.json"
    python3 -c "
import json, sys
groups = json.load(open('${CAT_GROUPS}', encoding='utf-8'))
sel    = json.load(open('${SELECTION_FILE}', encoding='utf-8')) or []
sel    = set(sel)
out    = {k: v for k, v in groups.items() if k in sel} if sel else groups
json.dump(out, open('${SELECTED_GROUPS}', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'  Selection: {len(out)}/{len(groups)} categories kept', flush=True)
" && CAT_GROUPS="${SELECTED_GROUPS}" && ADD_DIVERS="false"
fi

# 2) Group / deduplicate (if a cap OR deduplication is requested)
if [[ -f "${TREE_FILE}" ]] && { [[ "${MAX_FILES}" -gt 0 ]] || [[ "${DEDUP}" == "true" ]]; }; then
    echo ""
    echo "━━━ [4.5] GROUPING (MAX_FILES=${MAX_FILES}, DEDUP=${DEDUP}) ━━━"
    begin_step
    PACKED_GROUPS="${JOB_DIR}/category_groups_packed.json"
    MAX_FILES="${MAX_FILES}" NOTEBOOKLM_MAX_WORDS="${NOTEBOOKLM_MAX_WORDS:-500000}" DEDUP="${DEDUP}" \
        python3 /scripts/pack_files.py \
        "${CAT_GROUPS}" "${TREE_FILE}" "${PACKED_GROUPS}" "${MAX_FILES}"
    CAT_GROUPS="${PACKED_GROUPS}"
    end_step
fi

# ── 5. per-category file production ────────────────────────────────────────────
echo ""
echo "━━━ [5/5] PER-CATEGORY FILE PRODUCTION ━━━"
begin_step
log "Cleaning previous output: ${OUT_DIR}"
rm -rf "${FLAT_DIR}" "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

if [[ "${WANT_PDF}" == "true" ]]; then
    log "PDF: one file per category (max ${MAX_PDF} pages)"
    bash /scripts/flatten.sh "${PDF_DIR}" "${FLAT_DIR}" .pdf
    ADD_DIVERS="${ADD_DIVERS}" \
        python3 /scripts/merge_pdf.py "${FLAT_DIR}" "${OUT_DIR}" "${MAX_PDF}" "${CAT_GROUPS}"
fi

if [[ "${WANT_DOCS}" == "true" ]]; then
    log "Text (${DOC_FORMATS}): one file per category"
    ADD_DIVERS="${ADD_DIVERS}" \
        python3 /scripts/export_categories.py \
            "${HTML_DIR}" "${CAT_GROUPS}" "${OUT_DIR}" "${DOC_FORMATS}" \
        || log "⚠ Text export failed (PDFs unaffected)"
fi
end_step

echo ""
echo "════════════════════════════════════════"
echo "  ✓ PIPELINE COMPLETE -- $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Files in ${OUT_DIR}"
echo "════════════════════════════════════════"
ls -lh "${OUT_DIR}"/* 2>/dev/null | awk '{print "  " $5 "  " $9}' || echo "  (no files generated)"
true
