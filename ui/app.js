"use strict";
// Wiki Archive interface: jobs list, new-job form, settings, job page
// (stages, category selection, progress and log, files, storage).
// Depends on util.js and tree.js.

const STAGES = ["Source", "Scan", "Choose", "Generate", "Files"];
const WORD_LIMIT_FALLBACK = 500000;

// ── state ─────────────────────────────────────────────────────────────────────
let CFG = { steps: [], plans: {}, sources: {}, defaults: {} };
let settings = null;                 // default settings (pre-fill new jobs)
const S = {
  jobs: {}, selectedId: null, creatingNew: false, settingsOpen: false,
  manage: false, picked: new Set(), sizes: {}, pendingDel: new Set(),
  currentStep: -1, counter: null, follow: true, onlyIssues: false,
  logLines: [], detected: null, detectSeq: 0,
};
let logStream = null, streamToken = 0, logBuffer = [], flushScheduled = false;
let previewTimer = null, selTimer = null, detectTimer = null;

// ── polling ───────────────────────────────────────────────────────────────────
async function refresh() {
  const list = await api("/api/jobs");
  if (!Array.isArray(list)) return;
  S.jobs = Object.fromEntries(list.map(j => [j.id, j]));
  renderRail();
  if (S.selectedId && S.jobs[S.selectedId]) updateDetail(S.jobs[S.selectedId]);
}

// ── rail: job list, manage mode ───────────────────────────────────────────────
function renderRail() {
  const el = $("job-list");
  const jobs = Object.values(S.jobs).filter(j => !S.pendingDel.has(j.id));
  if (!jobs.length) {
    setHtml(el, '<div class="job-empty">No jobs yet.</div>');
    renderBulkBar();
    return;
  }
  setHtml(el, jobs.map(j => {
    const cb = S.manage
      ? `<input type="checkbox" class="job-cb" data-act="toggle-pick" data-id="${j.id}" ${S.picked.has(j.id) ? "checked" : ""} aria-label="Select ${esc(jobName(j.wiki_url))}">`
      : "";
    const size = (S.manage && S.sizes[j.id]) ? `<span class="job-size">${S.sizes[j.id]}</span>` : "";
    return `<div class="job-item st-${j.status}${j.id === S.selectedId ? " active" : ""}" data-act="select-job" data-id="${j.id}" role="button" tabindex="0">
      ${cb}
      <div class="job-main">
        <div class="job-name" title="${esc(j.wiki_url)}">${esc(jobName(j.wiki_url))}</div>
        <div class="job-meta"><span>${STATUS_LABEL[j.status] || j.status}</span><span>${relDate(j.created_at)}</span></div>
      </div>${size}
    </div>`;
  }).join(""));
  renderBulkBar();
}

function renderBulkBar() {
  const bar = $("bulk-bar");
  if (!S.manage) { setHtml(bar, ""); bar.className = ""; return; }
  const n = S.picked.size;
  const cleanable = Object.values(S.jobs).filter(j => ["stopped", "error"].includes(j.status)).length;
  bar.className = "bulk-bar";
  setHtml(bar, `
    <button class="btn btn-danger btn-sm" data-act="bulk-delete" ${n ? "" : "disabled"}>Delete selection (${n})</button>
    <button class="btn btn-line btn-sm" data-act="cleanup" ${cleanable ? "" : "disabled"}>Clean up stopped and failed jobs (${cleanable})</button>`);
}

function toggleManage() {
  S.manage = !S.manage;
  S.picked.clear();
  const b = $("manage-btn");
  b.setAttribute("aria-pressed", String(S.manage));
  b.classList.toggle("btn-line", S.manage);
  renderRail();
  if (S.manage) {            // sizes are loaded once, outside of the polling
    for (const id of Object.keys(S.jobs))
      api(`/api/jobs/${id}/disk`).then(d => { if (d.human) { S.sizes[id] = d.human; renderRail(); } });
  }
}

// ── deletion with undo ─────────────────────────────────────────────────────────
function requestDelete(ids) {
  if (!ids.length) return;
  ids.forEach(id => S.pendingDel.add(id));
  if (S.selectedId && ids.includes(S.selectedId)) { S.selectedId = null; showEmpty(); stopLogStream(); }
  renderRail();
  const label = ids.length === 1 ? "Job deleted" : ids.length + " jobs deleted";
  const cancel = () => { ids.forEach(id => S.pendingDel.delete(id)); renderRail(); };
  const commit = async () => {
    const live = ids.filter(id => S.pendingDel.has(id));
    if (!live.length) return;
    await api("/api/jobs/bulk_delete", { method: "POST", body: { ids: live } });
    live.forEach(id => S.pendingDel.delete(id));
    refresh();
  };
  showToast(label + ". You can undo for a few seconds.", {
    action: "Undo", timeout: 5000,
    onAction: () => { cancel(); showToast("Deletion cancelled", { type: "ok" }); },
    onTimeout: commit,
  });
}

// ── empty state, new job, settings ──────────────────────────────────────────────
function showEmpty() {
  $("detail").innerHTML = `<div class="empty-state"><h2>No job selected</h2>
    <p>Create a new job or select one from the list.</p></div>`;
}
function newJob() {
  S.creatingNew = true; S.settingsOpen = false; S.selectedId = null; S.detected = null;
  stopLogStream(); renderRail(); closeRail();
  $("detail").innerHTML = buildForm(null);
  syncKind(); togglePdfOpts();
  $("f-url")?.focus();
}
function cancelNew() { S.creatingNew = false; showEmpty(); }
function closeRail() { $("app").classList.remove("rail-open"); }

async function openSettings() {
  S.creatingNew = false; S.settingsOpen = true; S.selectedId = null;
  stopLogStream(); renderRail(); closeRail();
  const d = await api("/api/settings");
  if (d.settings) { settings = d.settings; CFG.plans = d.plans || {}; }
  $("detail").innerHTML = buildSettingsPage(settings || CFG.defaults);
}
function closeSettings() { S.settingsOpen = false; showEmpty(); }

function checkbox(id, checked, label, hint, extra) {
  return `<label class="check"><input type="checkbox" id="${id}" ${checked ? "checked" : ""} ${extra || ""}><span>${label}${hint ? `<small>${hint}</small>` : ""}</span></label>`;
}
function numberField(id, label, value, attrs, hint) {
  return `<div class="field"><label for="${id}">${label}</label><input type="number" id="${id}" value="${value}" ${attrs || ""}>${hint ? `<small>${hint}</small>` : ""}</div>`;
}
function textField(id, label, value, placeholder, hint) {
  return `<div class="field"><label for="${id}">${label}</label><input type="text" class="mono" id="${id}" value="${esc(value)}" placeholder="${esc(placeholder || "")}">${hint ? `<small>${hint}</small>` : ""}</div>`;
}
function formatChecks(prefix, set, onPdf) {
  return EXPORT_FORMATS.map(f => `<label class="check"><input type="checkbox" id="${prefix}-fmt-${f.id}" ${set.has(f.id) ? "checked" : ""} ${f.pdf && onPdf ? 'data-pdf-toggle="1"' : ""}>
    <span class="fmt-chip ${f.id}">${f.ext}</span><span>${f.label}</span></label>`).join("");
}

function buildSettingsPage(s) {
  const fmtSet = parseFormats(s.export_formats);
  const planOpts = Object.entries(CFG.plans).map(([k, v]) =>
      `<option value="${k}" ${s.notebooklm_plan === k ? "selected" : ""}>${esc(v.label)}: ${v.sources} sources</option>`).join("")
    + `<option value="custom" ${!CFG.plans[s.notebooklm_plan] ? "selected" : ""}>Custom</option>`;
  return `
  <section class="job-head">
    <div class="job-title-row"><h2 class="job-title">Default settings</h2>
      <button class="btn btn-quiet btn-sm" data-act="close-settings">Close</button></div>
    <p class="muted">These values pre-fill every new job. You can still change them per job.</p>
  </section>

  <section class="panel"><h3>NotebookLM</h3>
    <div class="fields">
      <div class="field"><label for="s-plan">NotebookLM plan</label><select id="s-plan">${planOpts}</select></div>
      ${numberField("s-maxfiles", "Max files (sources) per notebook", s.max_files, 'min="0" max="600"', "0 means no cap")}
      ${numberField("s-maxwords", "Max words per file", s.notebooklm_max_words, 'min="10000" step="10000"')}
      ${checkbox("s-dedup", s.dedup !== false, "Avoid duplicates", "One page goes into one file only")}
    </div>
    <p class="hint">NotebookLM accepts 500,000 words per source on every plan. Only the number of sources changes: Free 50, Plus 100, Pro 300, Ultra 600.</p>
  </section>

  <section class="panel"><h3>Default formats</h3>
    <div class="formats">${formatChecks("s", fmtSet, false)}</div>
  </section>

  <section class="panel"><h3>Download</h3>
    <div class="fields">
      ${numberField("s-delay", "Delay between requests (seconds)", s.delay, 'min="0" step="0.1"')}
      ${numberField("s-catworkers", "Parallel requests", s.cat_workers, 'min="1" max="32"', "Faster, but puts more load on the site")}
      ${checkbox("s-images", s.images, "Include images")}
      ${checkbox("s-perjob", s.output_per_job, "Separate output folder per job")}
    </div>
    <details class="adv"><summary>MediaWiki wikis</summary><div class="fields">
      ${textField("s-ns", "Namespaces", s.namespaces, "0", "0 = articles, 0,14 adds categories, all = everything")}
      ${checkbox("s-force", s.force !== false, "Skip Internet Archive")}
      ${checkbox("s-unique", s.unique_names, "Unique file names", "Needs a new dump")}
    </div></details>
    <details class="adv"><summary>Documentation websites</summary><div class="fields">
      ${numberField("s-sitemax", "Max pages", s.site_max_pages, 'min="0"', "0 = no limit; otherwise discovery stops after this many pages")}
    </div></details>
  </section>

  <section class="panel"><h3>PDF</h3>
    <div class="fields">
      ${numberField("s-maxpdf", "Max pages per merged PDF", s.max_pdf, 'min="1" max="2000"')}
      ${numberField("s-workers", "PDF workers", s.workers, 'min="1" max="16"')}
    </div>
  </section>

  <div class="actions">
    <button class="btn btn-primary" data-act="save-settings">Save settings</button>
    <button class="btn btn-line" data-act="close-settings">Close</button>
  </div>`;
}

function onPlanChange() {
  const plan = $("s-plan").value;
  if (CFG.plans[plan]) $("s-maxfiles").value = CFG.plans[plan].sources;
}
function onMaxFilesInput() {
  const v = parseInt($("s-maxfiles").value);
  const match = Object.entries(CFG.plans).find(([, p]) => p.sources === v);
  $("s-plan").value = match ? match[0] : "custom";
}
async function saveSettings() {
  const fmt = ALL_FORMAT_IDS.filter(id => $("s-fmt-" + id)?.checked);
  if (!fmt.length) { showToast("Choose at least one default format.", { type: "err" }); return; }
  const body = {
    notebooklm_plan:      $("s-plan").value,
    max_files:            parseInt($("s-maxfiles").value) || 0,
    notebooklm_max_words: parseInt($("s-maxwords").value) || WORD_LIMIT_FALLBACK,
    dedup:                $("s-dedup").checked,
    export_formats:       fmt.length === ALL_FORMAT_IDS.length ? "all" : fmt.join(","),
    namespaces:           $("s-ns").value.trim() || "0",
    delay:                numOr($("s-delay").value, 0.5),
    output_per_job:       $("s-perjob").checked,
    unique_names:         $("s-unique").checked,
    cat_workers:          parseInt($("s-catworkers").value) || 8,
    images:               $("s-images").checked,
    force:                $("s-force").checked,
    max_pdf:              parseInt($("s-maxpdf").value) || 500,
    workers:              parseInt($("s-workers").value) || 4,
    site_max_pages:       numOr($("s-sitemax").value, 0),
  };
  const r = await api("/api/settings", { method: "PUT", body });
  if (r.error) { showToast(r.error, { type: "err" }); return; }
  if (r.settings) { settings = r.settings; showToast("Settings saved", { type: "ok" }); }
  else showToast("Could not save the settings.", { type: "err" });
}

// ── new job / reconfigure form ──────────────────────────────────────────────────
function buildForm(job) {
  const p = job ? job.params : (settings || CFG.defaults);
  const fmtSet = parseFormats(p.export_formats);
  const sourceOpts = Object.entries(CFG.sources).map(([k, label]) =>
    `<option value="${k}" ${p.source === k ? "selected" : ""}>${esc(label)}</option>`).join("");
  const jobArg = job ? job.id : "";
  return `
  <section class="panel" id="job-form">
    <h3>${job ? "Settings of this job" : "New job"}</h3>
    <div class="field">
      <label for="f-url">Address of the wiki or website</label>
      <div class="url-row"><input id="f-url" type="text" value="${esc(job ? job.wiki_url : "")}" placeholder="Paste any page of the wiki or site" autocomplete="off" spellcheck="false"></div>
      <div id="f-detect" class="hint"></div>
    </div>
    <div class="fields">
      <div class="field"><label for="f-source">Type of site</label><select id="f-source">${sourceOpts}</select></div>
      ${numberField("f-maxfiles", "Max files (NotebookLM)", p.max_files ?? 50, 'min="0" max="600"', "0 means no cap")}
      ${checkbox("f-dedup", p.dedup !== false, "Avoid duplicates", "One page goes into one file only")}
    </div>
    <div class="formats" role="group" aria-label="Formats to generate">${formatChecks("f", fmtSet, true)}</div>

    <details class="adv"><summary>More options</summary>
      <div class="fields">
        ${numberField("f-delay", "Delay between requests (seconds)", p.delay, 'min="0" step="0.5"')}
        <div class="field pdf-opt">${numberField("f-maxpdf", "Max pages per merged PDF", p.max_pdf, 'min="1" max="2000"').replace('<div class="field">', "<div>")}</div>
        <div class="field pdf-opt">${numberField("f-workers", "PDF workers", p.workers, 'min="1" max="16"').replace('<div class="field">', "<div>")}</div>
        ${checkbox("f-images", p.images, "Include images")}
        ${checkbox("f-perjob", p.output_per_job, "Separate output folder", "This job will not overwrite another job's files", job?.has_output ? "disabled" : "")}
        ${checkbox("f-clean", p.clean, "New full download", '<span class="danger">Wipes everything this job downloaded</span>')}
        <div class="pdf-opt">${checkbox("f-rerender", p.rerender, "Re-render output", "Rebuilds the PDFs without downloading again")}</div>
      </div>
      <div class="only-mw" data-kinds="mediawiki"><div class="fields">
        ${textField("f-ns", "Namespaces (MediaWiki)", p.namespaces, "0", "0 = articles, 0,14 adds categories, all = everything")}
        ${checkbox("f-unique", p.unique_names, "Unique file names", "No page is lost when two titles look alike; needs a new download")}
        ${checkbox("f-force", p.force !== false, "Skip Internet Archive")}
      </div></div>
      <div class="only-site" data-kinds="site"><div class="fields">
        ${numberField("f-sitemax", "Max pages (website)", p.site_max_pages, 'min="0"', "0 = no limit; otherwise discovery stops after this many pages")}
        ${textField("f-include", "Only these paths (website)", p.site_include, "/docs/*, /guide/*", "Comma-separated; empty means the whole site")}
        ${textField("f-exclude", "Skip these paths (website)", p.site_exclude, "/blog/*", "Tags, search and other languages are skipped already")}
      </div></div>
    </details>

    <div class="actions" style="margin-top:1.1rem">
      <button class="btn btn-primary" data-act="scan" data-id="${jobArg}">Scan</button>
      <button class="btn-link" data-act="full" data-id="${jobArg}">Do everything at once</button>
      ${job ? "" : '<button class="btn-link" data-act="cancel-new">Cancel</button>'}
    </div>
  </section>`;
}

// Shows the options that belong to the kind of site (chosen, else detected).
function syncKind() {
  const chosen = $("f-source")?.value || "auto";
  const kind = chosen !== "auto" ? chosen : (S.detected?.kind === "unknown" ? "auto" : S.detected?.kind || "auto");
  document.querySelectorAll("#job-form [data-kinds]").forEach(el => {
    el.hidden = kind !== "auto" && el.dataset.kinds !== kind;
  });
}
function togglePdfOpts() {
  const on = $("f-fmt-pdf")?.checked;
  document.querySelectorAll("#job-form .pdf-opt").forEach(el => { el.hidden = !on; });
}
function scheduleDetect() {
  clearTimeout(detectTimer);
  const url = $("f-url")?.value.trim() || "";
  const hint = $("f-detect");
  if (!hint) return;
  if (!/^https?:\/\/\S+\.\S+/.test(url)) { S.detected = null; hint.textContent = ""; hint.className = "hint"; syncKind(); return; }
  hint.className = "hint"; hint.textContent = "Checking the address…";
  detectTimer = setTimeout(async () => {
    const seq = ++S.detectSeq;
    const r = await api("/api/detect", { method: "POST", body: { url } });
    if (seq !== S.detectSeq || !$("f-detect")) return;
    S.detected = r.error ? null : r;
    if (r.error || r.kind === "unknown") { hint.className = "hint bad"; hint.textContent = r.error || "Cannot reach this address."; }
    else {
      hint.className = "hint ok";
      hint.textContent = r.kind === "mediawiki" ? "This is a MediaWiki wiki."
        : "This is a website" + (r.generator ? ` (${r.generator})` : "") + ": it will be read page by page.";
    }
    syncKind();
  }, 600);
}

function collectFormats() {
  const picked = ALL_FORMAT_IDS.filter(id => $("f-fmt-" + id)?.checked);
  if (picked.length === 0) return "none";
  if (picked.length === ALL_FORMAT_IDS.length) return "all";
  return picked.join(",");
}
function collectParams(base) {
  base = base || settings || CFG.defaults;
  const mf = parseInt($("f-maxfiles")?.value);
  return {
    ...base,   // inherits keys the form does not show (notebooklm_max_words, cat_workers...)
    source:         $("f-source")?.value ?? base.source ?? "auto",
    namespaces:     $("f-ns")?.value?.trim() ?? base.namespaces,
    delay:          numOr($("f-delay")?.value, 0.5),
    max_pdf:        parseInt($("f-maxpdf")?.value) || 500,
    workers:        parseInt($("f-workers")?.value) || 4,
    max_files:      Number.isFinite(mf) ? mf : (base.max_files ?? 50),
    dedup:          $("f-dedup")?.checked ?? base.dedup ?? true,
    images:         $("f-images")?.checked ?? true,
    output_per_job: $("f-perjob")?.checked ?? base.output_per_job ?? false,
    unique_names:   $("f-unique")?.checked ?? base.unique_names ?? false,
    clean:          $("f-clean")?.checked ?? false,
    rerender:       $("f-rerender")?.checked ?? false,
    force:          $("f-force")?.checked ?? true,
    site_max_pages: numOr($("f-sitemax")?.value, base.site_max_pages ?? 0),
    site_include:   $("f-include")?.value?.trim() ?? base.site_include ?? "",
    site_exclude:   $("f-exclude")?.value?.trim() ?? base.site_exclude ?? "",
    export_formats: collectFormats(),
  };
}
async function ensureJob(existingId) {
  const url = $("f-url")?.value?.trim();
  const params = collectParams(existingId ? S.jobs[existingId]?.params : settings);
  if (existingId) {
    const r = await api(`/api/jobs/${existingId}`, { method: "PATCH", body: { wiki_url: url || undefined, params } });
    if (r.error) { showToast(r.error, { type: "err" }); return null; }
    return existingId;
  }
  if (!url) { showToast("Paste the address of the wiki or site first.", { type: "err" }); return null; }
  const job = await api("/api/jobs", { method: "POST", body: { wiki_url: url, ...params } });
  if (job.error) { showToast(job.error, { type: "err" }); return null; }
  S.jobs[job.id] = job;
  return job.id;
}
async function scanFromForm(existingId) {
  if (collectFormats() === "none") { showToast("Choose at least one format.", { type: "err" }); return; }
  const id = await ensureJob(existingId);
  if (!id) return;
  Tree.reset();
  S.creatingNew = false;
  await api(`/api/jobs/${id}/scan`, { method: "POST" });
  await refresh();
  selectJob(id);
}
async function submitFull(existingId) {
  if (collectFormats() === "none") { showToast("Choose at least one format.", { type: "err" }); return; }
  const id = await ensureJob(existingId);
  if (!id) return;
  S.creatingNew = false;
  await api(`/api/jobs/${id}/${existingId ? "resume" : "start"}`, { method: "POST" });
  await refresh();
  selectJob(id);
}

// ── job page ─────────────────────────────────────────────────────────────────────
function canGenerate(job) { return job.has_tree && job.data_present; }

function stageOf(job) {
  const s = job.status, tree = canGenerate(job);
  if (s === "running" || s === "paused") return { current: S.currentStep >= 4 ? 3 : 1 };
  if (s === "error")   return { current: job.has_tree ? 3 : 1, error: true };
  if (s === "scanned") return { current: 2 };
  if (s === "done")    return job.has_output ? { current: 5 } : { current: tree ? 2 : 0 };
  if (s === "stopped") return { current: tree ? 2 : 0 };
  return { current: 0 };
}
function stagesHtml(job) {
  const { current, error } = stageOf(job);
  return STAGES.map((name, i) => {
    const cls = i < current ? "done" : i === current ? (error ? "error" : "current") : "";
    const mark = cls === "done" ? "✓" : cls === "error" ? "!" : i + 1;
    return `<li class="stage ${cls}" ${cls === "current" ? 'aria-current="step"' : ""}><span class="mark">${mark}</span><span class="name">${name}</span></li>`;
  }).join("");
}

function selectJob(id) {
  S.selectedId = id; S.currentStep = -1; S.creatingNew = false; S.settingsOpen = false; S.counter = null;
  Tree.reset();
  stopLogStream();
  const job = S.jobs[id];
  if (!job) return;
  closeRail();
  renderFullDetail(job);
  renderRail();
  startLogStream(id, 0);
  if (canGenerate(job)) loadTree(id);
}

function renderFullDetail(job) {
  const showForm = ["pending", "stopped", "done", "error", "scanned"].includes(job.status);
  const showGen = canGenerate(job);
  $("detail").innerHTML = `
  <section class="job-head">
    <div class="job-title-row">
      <h2 class="job-title">${esc(jobName(job.wiki_url))}</h2>
      <span id="d-badge" class="badge st-${job.status}">${badgeHtml(job.status)}</span>
      <span id="d-kind" class="kind">${KIND_LABEL[job.source_kind] || ""}</span>
      <button class="btn btn-quiet btn-sm" data-act="delete-job" data-id="${job.id}">Delete</button>
    </div>
    <div class="job-url" title="${esc(job.wiki_url)}">${esc(job.wiki_url)}</div>
  </section>
  <ol id="d-stages" class="stages" aria-label="Stages">${stagesHtml(job)}</ol>
  <div id="d-banner">${buildBanner(job)}</div>
  <div id="d-actions" class="actions">${buildActions(job)}</div>
  <section id="d-gen" class="panel" ${showGen ? "" : "hidden"}>${showGen ? buildGenPanel(job) : ""}</section>
  <section id="d-files" class="panel" ${job.files && job.files.length ? "" : "hidden"}>
    <h3>Generated files</h3><div id="files-body">${buildFiles(job)}</div>
  </section>
  <div id="d-form" data-shown="${showForm && !showGen ? 1 : 0}">${showForm && !showGen ? buildForm(job) : ""}</div>
  <section id="d-log" class="panel">
    <div class="panel-head"><h3>Progress</h3></div>
    <div id="d-steps" class="pipeline">${buildSteps()}</div>
    <div id="d-counter" class="counter" hidden><span id="d-counter-text"></span><div class="bar"><i style="width:0"></i></div></div>
    <div class="log-tools">
      <strong>Log</strong><span class="spacer"></span>
      <label class="check"><input type="checkbox" id="log-issues" data-act="log-issues"><span>Warnings and errors only</span></label>
      <label class="check"><input type="checkbox" id="log-follow" data-act="log-follow" checked><span>Follow</span></label>
      <button class="btn btn-quiet btn-sm" data-act="log-copy">Copy</button>
      <button class="btn btn-quiet btn-sm" data-act="log-download">Download</button>
      <button class="btn btn-quiet btn-sm" data-act="log-clear">Clear</button>
    </div>
    <div id="terminal" tabindex="0" aria-label="Log"><span class="l-dim">Loading logs…</span></div>
  </section>
  <section id="d-storage" class="panel">
    <h3>Storage</h3>
    <div id="storage-body"><button class="btn btn-line btn-sm" data-act="load-storage" data-id="${job.id}">Show disk space used</button></div>
  </section>`;
  if (showForm && !showGen) formShown(job);
}
// Options that belong to the kind of site: known from the job, else from the detection.
function formShown(job) {
  S.detected = job && job.source_kind !== "auto" ? { kind: job.source_kind } : null;
  syncKind(); togglePdfOpts();
}

function buildBanner(job) {
  if (job.status === "scanned")
    return `<div class="note">Choose the categories to keep, then generate your files.</div>`;
  if (job.status === "done" && canGenerate(job))
    return `<div class="note">Your files are ready below. Change the selection and generate again if you want a different set.</div>`;
  if (job.status === "error")
    return `<div class="note warn">The run stopped on an error: read the end of the log below, then change the settings if needed and try again.</div>`;
  if (job.status === "pending")
    return `<div class="note">Scan first: it lists the categories (sections) of the site so you can pick what to keep.</div>`;
  if (job.status === "done" && !job.data_present)
    return `<div class="note warn">The downloaded data was freed. Scan again to generate new files.</div>`;
  return "";
}
function buildActions(job) {
  const s = job.status, id = job.id;
  if (s === "running") return `
    <button class="btn btn-warn" data-act="pause" data-id="${id}">Pause</button>
    <button class="btn btn-danger" data-act="stop" data-id="${id}">Stop</button>`;
  if (s === "paused") return `
    <button class="btn btn-primary" data-act="resume" data-id="${id}">Resume</button>
    <button class="btn btn-danger" data-act="stop" data-id="${id}">Stop</button>`;
  return "";   // the other states are driven by the selection panel and the form
}
function badgeHtml(status) {
  return (status === "running" ? '<span class="spin"></span>' : "") + (STATUS_LABEL[status] || status);
}
function buildSteps() {
  return CFG.steps.map((s, i) => `<div class="pstep" id="step-${i}"><span class="dot">${i + 1}</span><span>${esc(s.label)}</span></div>`).join("");
}

function buildGenPanel(job) {
  return `
    <div class="panel-head"><h3>Choose what to keep</h3>
      <button class="btn-link" data-act="reconfigure" data-id="${job.id}">Change settings and scan again</button></div>
    <p class="muted">A category includes its sub-categories. Each bar shows its share of the per-file word limit.</p>
    <div class="tree-toolbar">
      <button class="btn btn-line btn-sm" data-act="tree-all">All</button>
      <button class="btn btn-line btn-sm" data-act="tree-none">None</button>
      <button class="btn btn-line btn-sm" data-act="tree-collapse">Collapse</button>
      <button class="btn btn-line btn-sm" data-act="tree-sort" id="sort-btn">Sort: size</button>
      <input type="text" class="tree-search" id="tree-search" placeholder="Filter categories…" aria-label="Filter categories" autocomplete="off">
    </div>
    <div class="tree-body" id="tree-body"><div class="tree-hint">Loading categories…</div></div>
    <div class="budget">
      <div class="budget-line">
        <div class="budget-main" id="gen-info">—</div>
        <div class="actions">
          <button class="btn btn-line" data-act="generate-all" data-id="${job.id}">Generate all</button>
          <button class="btn btn-primary" data-act="generate" data-id="${job.id}">Generate selection</button>
        </div>
      </div>
      <div class="gauge" id="gen-gauge" hidden><i></i></div>
      <div class="budget-sub" id="gen-sub"></div>
      <details class="plan" id="gen-plan" hidden><summary id="gen-plan-title">Files that will be created</summary>
        <div class="plan-scroll"><table><tbody id="gen-plan-rows"></tbody></table></div></details>
    </div>`;
}

function buildFiles(job) {
  if (!job.files || !job.files.length) return "";
  const rows = job.files.map(f => `
    <div class="file"><span class="fmt-chip ${esc(f.ext)}">.${esc(f.ext)}</span>
      <span class="name" title="${esc(f.name)}">${esc(f.name)}</span>
      <span class="size">${esc(f.size)}</span>
      <a href="/api/jobs/${job.id}/files/${encodeURIComponent(f.name)}" download>Download</a></div>`).join("");
  return `
    <div class="path-row">
      <code id="kb-path-text">${esc(job.out_path)}</code>
      <button class="btn btn-line btn-sm" data-act="copy-path">Copy path</button>
      <a class="btn btn-line btn-sm" href="/api/jobs/${job.id}/download.zip" download>Download all (.zip)</a>
    </div>
    <p class="hint">${job.files.length} file(s). Paste the path into File Explorer, then import the folder into NotebookLM, or download the files here.</p>
    <div class="files">${rows}</div>`;
}

async function copyPath(btn) {
  const el = $("kb-path-text");
  if (!el) return;
  const label = btn.textContent;
  try { await navigator.clipboard.writeText(el.textContent); btn.textContent = "Copied"; }
  catch {
    const r = document.createRange(); r.selectNode(el);
    getSelection().removeAllRanges(); getSelection().addRange(r);
    btn.textContent = "Selected: press Ctrl+C";
  }
  setTimeout(() => { btn.textContent = label; }, 1800);
}

function updateDetail(job) {
  if (!S.selectedId || S.selectedId !== job.id) return;
  const badge = $("d-badge");
  if (badge) { badge.className = `badge st-${job.status}`; setHtml(badge, badgeHtml(job.status)); }
  const kind = $("d-kind"); if (kind) kind.textContent = KIND_LABEL[job.source_kind] || "";
  setHtml($("d-stages"), stagesHtml(job));
  setHtml($("d-actions"), buildActions(job));
  setHtml($("d-banner"), buildBanner(job));

  // The selection panel appears once the tree exists, and goes away when its data was freed.
  const gen = $("d-gen");
  if (gen && canGenerate(job) && gen.hidden) { gen.hidden = false; gen.innerHTML = buildGenPanel(job); loadTree(job.id); }
  if (gen && !canGenerate(job) && !gen.hidden) { gen.hidden = true; gen.innerHTML = ""; Tree.reset(); }

  // The launch form follows the state: after an error, stop or purge the buttons must come back.
  const form = $("d-form");
  if (form) {
    const want = ["pending", "stopped", "done", "error", "scanned"].includes(job.status) && !canGenerate(job);
    const shown = form.dataset.shown === "1";
    if (want && !shown) { form.innerHTML = buildForm(job); form.dataset.shown = "1"; formShown(job); }
    else if (!want && shown) { form.innerHTML = ""; form.dataset.shown = "0"; }
  }
  if (job.status === "error" && S.currentStep >= 0) setStep(S.currentStep, "error");
  const files = $("d-files");
  if (files && job.files && job.files.length) { files.hidden = false; setHtml($("files-body"), buildFiles(job)); }
}

function toggleReconfigure(jobId) {
  const form = $("d-form");
  if (!form) return;
  if (form.querySelector(".panel")) { form.innerHTML = ""; form.dataset.shown = "0"; return; }
  form.innerHTML = buildForm(S.jobs[jobId]);
  form.dataset.shown = "1";
  formShown(S.jobs[jobId]);
}

// ── category selection ──────────────────────────────────────────────────────────
async function loadTree(jobId) {
  const body = $("tree-body");
  if (body) body.innerHTML = '<div class="tree-hint">Loading categories…</div>';
  const data = await api(`/api/jobs/${jobId}/category_tree`);
  if (data.error) { if ($("tree-body")) $("tree-body").innerHTML = `<div class="tree-hint danger">${esc(data.error)}</div>`; return; }
  const job = S.jobs[jobId];
  Tree.load(data, job?.selection, job?.params?.notebooklm_max_words || WORD_LIMIT_FALLBACK);
}

function updateGenInfo(preview) {
  const info = $("gen-info"); if (!info) return;
  const n = Tree.selected().length, total = Tree.total;
  const job = S.jobs[S.selectedId];
  const maxFiles = job?.params?.max_files ?? 0;
  const maxWords = job?.params?.notebooklm_max_words || WORD_LIMIT_FALLBACK;
  const gauge = $("gen-gauge"), sub = $("gen-sub"), plan = $("gen-plan");
  let main = `${n} of ${total} categories selected`;
  let subHtml = "";
  if (preview && preview.error) subHtml = `<span class="warn">${esc(preview.error)}</span>`;
  if (preview && !preview.error) {
    main = `${preview.file_count} file${preview.file_count === 1 ? "" : "s"} from ${n} of ${total} categories`;
    const totalPages = preview.groups.reduce((a, g) => a + g.pages, 0);
    const words = preview.groups.reduce((a, g) => a + g.words, 0);
    const biggest = preview.groups.reduce((a, g) => Math.max(a, g.words), 0);
    if (maxFiles > 0) {
      const over = preview.file_count > maxFiles;
      gauge.hidden = false; gauge.classList.toggle("over", over);
      gauge.firstElementChild.style.width = Math.min(100, preview.file_count / maxFiles * 100) + "%";
      subHtml += `<span>${preview.file_count} of ${maxFiles} files allowed</span>`;
      if (over) subHtml += `<span class="warn">Over the limit: a notebook takes ${maxFiles} sources</span>`;
    } else gauge.hidden = true;
    subHtml += `<span>${totalPages.toLocaleString()} pages, ${fmtWords(words)}</span><span>Largest file: ${fmtWords(biggest)} of ${maxWords.toLocaleString()}</span>`;
    if (preview.splits && preview.splits.length) {
      const CAP = 6;
      const shown = preview.splits.slice(0, CAP).map(esc).join(", ");
      const extra = preview.splits.length > CAP ? ` and ${preview.splits.length - CAP} more` : "";
      subHtml += `<span class="warn">${preview.splits.length} categories are too large and are split: ${shown}${extra}</span>`;
    }
    plan.hidden = !preview.groups.length;
    $("gen-plan-title").textContent = `Files that will be created (${preview.groups.length})`;
    $("gen-plan-rows").innerHTML = preview.groups.map(g =>
      `<tr><td>${esc(g.name)}</td><td class="num">${nPages(g.pages)}</td><td class="num">${fmtWords(g.words)}</td></tr>`).join("");
  }
  info.textContent = main;
  sub.innerHTML = subHtml;
}
function schedulePreview() {
  if (!S.selectedId) return;
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 350);
}
async function runPreview() {
  if (!S.selectedId || !Tree.loaded) return;
  const sel = Tree.selected();
  if (!sel.length) { updateGenInfo({ file_count: 0, splits: [], groups: [] }); return; }
  const maxFiles = S.jobs[S.selectedId]?.params?.max_files ?? 50;
  const id = S.selectedId;
  const preview = await api(`/api/jobs/${id}/preview_packing`, { method: "POST", body: { selection: sel, max_files: maxFiles } });
  if (id === S.selectedId) updateGenInfo(preview);
}
function scheduleSaveSelection() {
  if (!S.selectedId) return;
  clearTimeout(selTimer);
  const id = S.selectedId;
  selTimer = setTimeout(() => api(`/api/jobs/${id}/selection`, { method: "PUT", body: { selection: Tree.selected() } }), 800);
}
Tree.onChange = () => { updateGenInfo(); schedulePreview(); };

async function doGenerate(jobId) {
  const sel = Tree.selected();
  if (!sel.length) { showToast("Select at least one category.", { type: "err" }); return; }
  await api(`/api/jobs/${jobId}/generate`, { method: "POST", body: { selection: sel, formats: null } });
  showToast("Generating the selected categories…", { type: "ok" });
  afterLaunch(jobId);
}
async function doGenerateAll(jobId) {
  await api(`/api/jobs/${jobId}/generate`, { method: "POST", body: { selection: null, formats: null } });
  showToast("Generating everything…", { type: "ok" });
  afterLaunch(jobId);
}
function afterLaunch(jobId) {
  stopLogStream(); S.currentStep = -1; S.counter = null;
  const term = $("terminal"); if (term) term.innerHTML = "";
  startLogStream(jobId, 0);
  refresh();
}

// ── storage ────────────────────────────────────────────────────────────────────
async function loadStorage(jobId) {
  const body = $("storage-body");
  if (body) body.innerHTML = '<span class="muted">Calculating…</span>';
  const d = await api(`/api/jobs/${jobId}/disk`);
  if (d.error || !body) { if (body) body.innerHTML = '<span class="danger">Calculation failed.</span>'; return; }
  S.sizes[jobId] = d.human;
  body.innerHTML = `
    <dl class="storage-rows">
      <dt>Data that can be rebuilt</dt><dd>${d.data_human}</dd>
      <dt>Final files</dt><dd>${d.output_human}</dd>
      <dt>Total</dt><dd>${d.human}</dd>
    </dl>
    <div class="actions">
      <button class="btn btn-line btn-sm" data-act="purge" data-id="${jobId}" data-scope="pdf">Clear PDF cache</button>
      <button class="btn btn-line btn-sm" data-act="purge" data-id="${jobId}" data-scope="intermediate">Free up space, keep final files</button>
    </div>
    <p class="hint">Freeing up space deletes the downloaded data; scan again to generate new files.</p>`;
}
async function purge(jobId, scope) {
  const r = await api(`/api/jobs/${jobId}/purge`, { method: "POST", body: { scope } });
  if (r.error) { showToast(r.error, { type: "err" }); return; }
  showToast(`${r.freed_human} freed`, { type: "ok" });
  loadStorage(jobId);
  refresh();
}

async function jobAction(id, action) {
  await api(`/api/jobs/${id}/${action}`, { method: "POST" });
  if (action === "resume") afterLaunch(id);
  refresh();
}

// ── log stream ────────────────────────────────────────────────────────────────────
function startLogStream(jobId, fromPos) {
  stopLogStream();
  const token = ++streamToken;
  const term = $("terminal");
  if (!term) return;
  if (fromPos === 0) { term.innerHTML = ""; S.logLines = []; }
  logBuffer = [];
  logStream = new EventSource(`/api/jobs/${jobId}/logs?from_pos=${fromPos}`);
  logStream.onmessage = (e) => {
    if (token !== streamToken) return;
    if (e.data === "__END__") { logStream.close(); flushLogs(); endCounter(); return; }
    if (e.data) queueLog(e.data);
  };
  logStream.onerror = () => logStream.close();
}
function stopLogStream() {
  streamToken++;
  if (logStream) { logStream.close(); logStream = null; }
  logBuffer = [];
}
function queueLog(text) {
  logBuffer.push(text);
  if (!flushScheduled) { flushScheduled = true; requestAnimationFrame(flushLogs); }
}
function flushLogs() {
  flushScheduled = false;
  const term = $("terminal");
  if (!term || !logBuffer.length) return;
  const batch = logBuffer; logBuffer = [];
  const frag = document.createDocumentFragment();
  let lastStep = -1, sawEnd = false;
  for (const text of batch) {
    const div = document.createElement("div");
    for (const [test, cls] of LOG_RULES) if (test(text)) { div.className = cls; break; }
    div.textContent = text || " ";
    frag.appendChild(div);
    S.logLines.push(text);
    const idx = CFG.steps.findIndex(s => text.includes(s.marker));
    if (idx !== -1) { lastStep = idx; S.counter = null; }
    else if (!text.includes("━━━")) {
      const m = text.match(/\[(\d+)\/(\d+)\]/);        // "[12/340]" lines of the download, extraction and PDF steps
      if (m && +m[2] > 0) S.counter = { n: +m[1], m: +m[2] };
    }
    if (text.includes("PIPELINE COMPLETE")) sawEnd = true;
  }
  term.appendChild(frag);
  if (S.follow) term.scrollTop = term.scrollHeight;
  if (lastStep !== -1) {
    S.currentStep = lastStep; setStep(lastStep - 1, "done"); setStep(lastStep, "active");
    const job = S.jobs[S.selectedId]; if (job) setHtml($("d-stages"), stagesHtml(job));
  }
  if (sawEnd) { setStep(CFG.steps.length, "done"); endCounter(); } else showCounter();
}
function showCounter() {
  const box = $("d-counter"); if (!box) return;
  if (!S.counter) { box.hidden = true; return; }
  const label = CFG.steps[S.currentStep]?.label || "Progress";
  box.hidden = false;
  $("d-counter-text").textContent = `${label}: ${S.counter.n} of ${S.counter.m}`;
  box.querySelector(".bar > i").style.width = Math.min(100, S.counter.n / S.counter.m * 100) + "%";
}
function endCounter() { S.counter = null; const box = $("d-counter"); if (box) box.hidden = true; }
function setStep(active, state) {
  CFG.steps.forEach((_, i) => {
    const el = $(`step-${i}`); if (!el) return;
    el.classList.remove("active", "done", "error");
    if (i < active) el.classList.add("done");
    else if (i === active) el.classList.add(state);
  });
}
async function copyLog(btn) {
  const label = btn.textContent;
  try { await navigator.clipboard.writeText(S.logLines.join("\n")); btn.textContent = "Copied"; }
  catch { btn.textContent = "Copy failed"; }
  setTimeout(() => { btn.textContent = label; }, 1500);
}
function downloadLog() {
  const job = S.jobs[S.selectedId];
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([S.logLines.join("\n") + "\n"], { type: "text/plain" }));
  a.download = `${job ? jobName(job.wiki_url) : "job"}-log.txt`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ── events (one listener per kind, driven by data-act) ───────────────────────────
const ACTIONS = {
  theme: () => cycleTheme(),
  settings: () => openSettings(),
  new: () => newJob(),
  manage: () => toggleManage(),
  rail: () => $("app").classList.toggle("rail-open"),
  "select-job": (el) => selectJob(el.dataset.id),
  "toggle-pick": (el) => { el.checked ? S.picked.add(el.dataset.id) : S.picked.delete(el.dataset.id); renderBulkBar(); },
  "bulk-delete": () => { requestDelete([...S.picked]); S.picked.clear(); },
  cleanup: () => requestDelete(Object.values(S.jobs).filter(j => ["stopped", "error"].includes(j.status)).map(j => j.id)),
  "delete-job": (el) => requestDelete([el.dataset.id]),
  scan: (el) => scanFromForm(el.dataset.id || null),
  full: (el) => submitFull(el.dataset.id || null),
  "cancel-new": () => cancelNew(),
  reconfigure: (el) => toggleReconfigure(el.dataset.id),
  pause: (el) => jobAction(el.dataset.id, "pause"),
  resume: (el) => jobAction(el.dataset.id, "resume"),
  stop: (el) => jobAction(el.dataset.id, "stop"),
  "tree-all": () => { Tree.selectAll(); scheduleSaveSelection(); },
  "tree-none": () => { Tree.selectNone(); scheduleSaveSelection(); },
  "tree-collapse": () => Tree.collapseAll(),
  "tree-sort": () => {
    const by = Tree.toggleSort();
    $("sort-btn").textContent = "Sort: " + by;
    const f = $("tree-search");
    Tree.filter(f && f.value.trim() ? f.value : "");
  },
  generate: (el) => doGenerate(el.dataset.id),
  "generate-all": (el) => doGenerateAll(el.dataset.id),
  "copy-path": (el) => copyPath(el),
  "load-storage": (el) => loadStorage(el.dataset.id),
  purge: (el) => purge(el.dataset.id, el.dataset.scope),
  "save-settings": () => saveSettings(),
  "close-settings": () => closeSettings(),
  "log-clear": () => { const t = $("terminal"); if (t) t.innerHTML = ""; S.logLines = []; },
  "log-copy": (el) => copyLog(el),
  "log-download": () => downloadLog(),
  "log-issues": (el) => { S.onlyIssues = el.checked; $("terminal")?.classList.toggle("only-issues", el.checked); },
  "log-follow": (el) => { S.follow = el.checked; if (S.follow) { const t = $("terminal"); if (t) t.scrollTop = t.scrollHeight; } },
};

document.addEventListener("click", (e) => {
  if (e.target.closest("#tree-body")) { Tree.click(e); return; }
  const el = e.target.closest("[data-act]");
  if (!el || el.matches("input[type=checkbox]")) return;      // checkboxes act on "change"
  const run = ACTIONS[el.dataset.act];
  if (run) run(el, e);
});
document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.closest("#tree-body")) { if (Tree.change(e)) scheduleSaveSelection(); return; }
  if (t.matches("input[type=checkbox][data-act]")) { ACTIONS[t.dataset.act]?.(t, e); return; }
  if (t.id === "f-source") syncKind();
  else if (t.id === "f-fmt-pdf") togglePdfOpts();
  else if (t.id === "s-plan") onPlanChange();
});
document.addEventListener("input", (e) => {
  const t = e.target;
  if (t.id === "f-url") scheduleDetect();
  else if (t.id === "tree-search") Tree.filter(t.value);
  else if (t.id === "s-maxfiles") onMaxFilesInput();
});
document.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && e.target.matches(".job-item")) { e.preventDefault(); e.target.click(); }
  if (e.key === "Enter" && e.target.id === "f-url") { e.preventDefault(); document.querySelector('[data-act="scan"]')?.click(); }
});

// ── boot ──────────────────────────────────────────────────────────────────────────
async function boot() {
  applyTheme(currentTheme());
  const d = await api("/api/settings");
  if (d.settings) {
    settings = d.settings;
    CFG = { steps: d.steps || [], plans: d.plans || {}, sources: d.sources || {}, defaults: d.defaults || {} };
  } else { settings = {}; showToast("Cannot reach the server: reload the page once it runs.", { type: "err", timeout: 8000 }); }
  refresh();
  setInterval(refresh, 2000);
}
boot();
