"use strict";
// Small helpers shared by tree.js and app.js (plain scripts, no build step).

const EXPORT_FORMATS = [
  { id: "pdf", label: "PDF",      ext: ".pdf", pdf: true },
  { id: "md",  label: "Markdown", ext: ".md" },
  { id: "txt", label: "Text",     ext: ".txt" },
];
const ALL_FORMAT_IDS = EXPORT_FORMATS.map(f => f.id);

const STATUS_LABEL = {
  pending: "Pending", running: "Running", paused: "Paused", stopped: "Stopped",
  scanned: "Scanned", done: "Done", error: "Error",
};
const KIND_LABEL = { mediawiki: "MediaWiki wiki", site: "Website" };   // auto: not known before the first scan

// First matching rule colours a log line.
const LOG_RULES = [
  [t => t.includes("━━━") || t.includes("════"),                     "l-sep"],
  [t => t.startsWith("✓") || t.includes("PIPELINE COMPLETE"),         "l-ok"],
  [t => t.startsWith("✗") || /(ERROR|Traceback|Error:)/i.test(t),     "l-err"],
  [t => t.startsWith("⚠") || /warning/i.test(t),                     "l-warn"],
  [t => t.startsWith("⏸") || t.startsWith("⏹") || t.startsWith("🧹"), "l-dim"],
];

const $ = (id) => document.getElementById(id);

// The page is polled every 2 s: rewriting an unchanged block would drop the focus,
// the text selection and clicks that are in progress (button replaced mid-click).
const _lastHtml = new WeakMap();
function setHtml(el, html) {
  if (!el || _lastHtml.get(el) === html) return;
  el.innerHTML = html; _lastHtml.set(el, html);
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
                  .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
const nPages = (n) => n + (n === 1 ? " page" : " pages");
function fmtWords(n) {
  if (!n) return "0 words";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M words";
  if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1) + "k words";
  return n + " word" + (n === 1 ? "" : "s");
}
function jobName(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url.slice(0, 25); }
}
function relDate(iso) {
  const sec = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (sec < 60)    return "just now";
  if (sec < 3600)  return Math.floor(sec / 60) + " min ago";
  if (sec < 86400) return Math.floor(sec / 3600) + " h ago";
  return Math.floor(sec / 86400) + " d ago";
}
function parseFormats(str) {
  const s = (str || "pdf").trim();
  if (s === "all") return new Set(ALL_FORMAT_IDS);
  if (s === "none" || s === "") return new Set();
  return new Set(s.split(",").map(x => x.trim()).filter(Boolean));
}
function numOr(v, fallback) { const n = parseFloat(v); return Number.isFinite(n) && n >= 0 ? n : fallback; }

async function api(path, opts) {
  opts = opts || {};
  const init = { method: opts.method || "GET", headers: {} };
  if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
  try {
    const r = await fetch(path, init);
    return await r.json();
  } catch { return { error: "Cannot reach the server." }; }
}

// ── toasts ────────────────────────────────────────────────────────────────────
function showToast(msg, opts) {
  opts = opts || {};
  const el = document.createElement("div");
  el.className = "toast " + (opts.type || "");
  const span = document.createElement("span");
  span.className = "msg"; span.textContent = msg;
  el.appendChild(span);
  let timer = null;
  const close = () => { if (timer) clearTimeout(timer); el.remove(); };
  if (opts.action) {
    const b = document.createElement("button");
    b.textContent = opts.action;
    b.onclick = () => { close(); if (opts.onAction) opts.onAction(); };
    el.appendChild(b);
  }
  $("toasts").appendChild(el);
  timer = setTimeout(() => { el.remove(); if (opts.onTimeout) opts.onTimeout(); }, opts.timeout || 3500);
  return close;
}

// ── theme: automatic (system), light, dark -- remembered when storage allows it ──
const THEMES = ["auto", "light", "dark"];
function currentTheme() { return document.documentElement.dataset.theme || "auto"; }
function applyTheme(t) {
  if (t === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  try { t === "auto" ? localStorage.removeItem("wa-theme") : localStorage.setItem("wa-theme", t); } catch {}
  const b = $("theme-btn");
  if (b) { const label = "Theme: " + t + " (click to change)"; b.title = label; b.setAttribute("aria-label", label); }
}
function cycleTheme() {
  const next = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length];
  applyTheme(next);
  showToast("Theme: " + next, { timeout: 1500 });
}
