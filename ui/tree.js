"use strict";
// Category tree of the selection screen.
//
// Rendering is LAZY: only the roots are drawn, sub-categories are built when a
// row is opened. Essential for big wikis (thousands of categories) and safe
// against cycles (A -> B -> A). Every drawn row is an "ik" (rendered instance),
// because one category can appear under several parents.
//
// State per category: 0 = none, 1 = partly, 2 = all. A partly selected parent
// keeps its OWN pages (not in a sub-category) only if `ownState` says so --
// the selection then carries "own:<Category>" for it.

const Tree = (() => {
  let data = null;
  let nodeState = {}, ownState = {}, parentMap = {};
  let ikCat = {}, ikAnc = {}, ikOpen = {}, ikPop = {}, ikCtr = 0;
  let sortBy = "size";
  let maxWords = 500000;
  let onChange = () => {};

  const nodes = () => data?.nodes || {};

  function buildParentMap() {
    parentMap = {};
    for (const [cat, node] of Object.entries(nodes()))
      for (const child of (node.children || [])) (parentMap[child] ||= []).push(cat);
  }
  function initState(checked) {
    nodeState = {}; ownState = {};
    for (const cat of Object.keys(nodes())) { nodeState[cat] = checked ? 2 : 0; ownState[cat] = checked ? 2 : 0; }
  }
  const hasOwnPages = (cat) => (nodes()[cat]?.own_pages || 0) > 0;

  function setDescendants(cat, state, seen) {
    if (seen.has(cat)) return; seen.add(cat);
    nodeState[cat] = state; ownState[cat] = state;
    for (const c of (nodes()[cat]?.children || [])) setDescendants(c, state, seen);
  }
  // Fully checked only when its own pages AND all existing sub-categories are;
  // unchecked only when none is; otherwise partial.
  function derivedState(cat) {
    const parts = (nodes()[cat]?.children || []).filter(c => nodes()[c]).map(c => nodeState[c] ?? 0);
    if (hasOwnPages(cat)) parts.push(ownState[cat] ?? 0);
    if (!parts.length) return nodeState[cat] ?? 0;
    return parts.every(s => s === 2) ? 2 : parts.every(s => s === 0) ? 0 : 1;
  }
  function recomputeAncestors(cat, seen) {
    if (seen.has(cat)) return; seen.add(cat);
    for (const parent of (parentMap[cat] || [])) {
      nodeState[parent] = derivedState(parent);
      recomputeAncestors(parent, seen);
    }
  }
  function recomputeAll() {   // after restoring a saved selection (bounded: cycles)
    const cats = Object.keys(nodes());
    for (let i = 0; i < 64; i++) {
      let changed = false;
      for (const c of cats) { const st = derivedState(c); if (st !== nodeState[c]) { nodeState[c] = st; changed = true; } }
      if (!changed) break;
    }
  }
  // The server's roots, plus one entry point for every category that is otherwise
  // unreachable (a cycle A -> B -> A has no root at all).
  function roots() {
    const ns = nodes();
    const out = (data.roots || []).filter(c => ns[c]);
    const seen = new Set();
    const walk = start => {
      const stack = [start];
      while (stack.length) {
        const x = stack.pop(); if (seen.has(x)) continue; seen.add(x);
        for (const k of (ns[x]?.children || [])) if (ns[k]) stack.push(k);
      }
    };
    out.forEach(walk);
    for (const c of Object.keys(ns).sort()) if (!seen.has(c)) { out.push(c); walk(c); }
    return out;
  }
  function sorted(cats) {
    const arr = [...cats];
    if (sortBy === "name") arr.sort((a, b) => a.localeCompare(b));
    else arr.sort((a, b) => (nodes()[b]?.total_words || 0) - (nodes()[a]?.total_words || 0));
    return arr;
  }
  // existing children, excluding cycles (an ancestor cannot become a descendant again)
  const realChildren = (cat, anc) =>
    (nodes()[cat]?.children || []).filter(c => nodes()[c] && c !== cat && !anc.has(c));

  function rowHtml(cat, ik, withToggle) {
    const node = nodes()[cat];
    const words = node.total_words || 0;
    const over = maxWords && words > maxWords;
    const fill = maxWords ? Math.min(100, Math.round(words / maxWords * 100)) : 0;
    return `<div class="tree-row" data-key="${ik}">
        ${withToggle ? `<button type="button" class="tree-toggle" aria-label="Expand ${esc(cat)}" aria-expanded="false">▸</button>` : '<span class="tree-toggle"></span>'}
        <input type="checkbox" class="tree-cb" data-key="${ik}" aria-label="Select ${esc(cat)}">
        <span class="tree-lbl" title="${esc(cat)}">${esc(cat)}</span>
        <span class="tree-bar${over ? " over" : ""}" title="${over ? "Over the per-file word limit: this category is split in several files" : "Share of the per-file word limit"}"><i style="width:${fill}%"></i></span>
        <span class="tree-cnt">${nPages(node.total_pages)}, ${fmtWords(words)}</span>
      </div>`;
  }
  function nodeHtml(cat, anc) {
    if (!nodes()[cat]) return "";
    const ik = ikCtr++;
    ikCat[ik] = cat; ikAnc[ik] = anc; ikOpen[ik] = false; ikPop[ik] = false;
    const hasKids = realChildren(cat, anc).length > 0;
    return `<div class="tree-node" data-key="${ik}">${rowHtml(cat, ik, hasKids)}
      <div class="tree-children" data-childkey="${ik}" hidden></div></div>`;
  }
  function expandNode(ik) {
    if (ikPop[ik]) return;            // already built
    ikPop[ik] = true;
    const cat = ikCat[ik];
    const anc = new Set(ikAnc[ik]); anc.add(cat);
    const kids = sorted(realChildren(cat, anc));
    const div = document.querySelector(`.tree-children[data-childkey="${ik}"]`);
    if (div) div.innerHTML = kids.map(c => nodeHtml(c, anc)).join("");
    paint();
  }
  function renderRoots() {
    ikCat = {}; ikAnc = {}; ikOpen = {}; ikPop = {}; ikCtr = 0;
    const body = $("tree-body"); if (!body) return;
    const list = sorted(roots());
    body.innerHTML = list.length ? list.map(c => nodeHtml(c, new Set())).join("")
                                 : '<div class="tree-hint">No categories found.</div>';
    paint();
  }
  function paint() {
    document.querySelectorAll("#tree-body .tree-cb").forEach(cb => {
      const st = nodeState[ikCat[cb.dataset.key]] ?? 0;
      cb.checked = st === 2; cb.indeterminate = st === 1;
    });
  }
  // The selection itself changed (not just what is drawn): the caller must know.
  function changed() { paint(); onChange(); }

  // ── public API ──
  function load(tree, saved, maxWordsPerFile) {
    data = tree; maxWords = maxWordsPerFile || 0;
    buildParentMap();
    if (saved && saved.length) {   // restore: only what was ticked
      initState(false);
      const pre = data.own_prefix || "own:";
      const seen = new Set();
      for (const entry of saved) {
        if (nodes()[entry]) setDescendants(entry, 2, seen);
        else if (entry.startsWith(pre) && nodes()[entry.slice(pre.length)]) ownState[entry.slice(pre.length)] = 2;
      }
      recomputeAll();
    } else initState(true);
    renderRoots();
    onChange();
  }
  function click(e) {       // expand / collapse a row
    if (e.target.closest(".tree-cb")) return;
    const row = e.target.closest(".tree-row"); if (!row) return;
    const t = row.querySelector("button.tree-toggle"); if (!t) return;     // no children
    const ik = row.dataset.key;
    const div = document.querySelector(`.tree-children[data-childkey="${ik}"]`); if (!div) return;
    ikOpen[ik] = !ikOpen[ik];
    if (ikOpen[ik]) expandNode(ik);
    div.hidden = !ikOpen[ik];
    t.textContent = ikOpen[ik] ? "▾" : "▸";
    t.setAttribute("aria-expanded", String(ikOpen[ik]));
  }
  function change(e) {      // a checkbox was (un)ticked
    const cb = e.target.closest(".tree-cb"); if (!cb) return false;
    const cat = ikCat[cb.dataset.key];
    setDescendants(cat, cb.checked ? 2 : 0, new Set());
    recomputeAncestors(cat, new Set());
    changed();
    return true;
  }
  function selectAll()  { initState(true);  changed(); }
  function selectNone() { initState(false); changed(); }
  function collapseAll() {
    document.querySelectorAll("#tree-body .tree-children").forEach(d => { d.hidden = true; ikOpen[d.dataset.childkey] = false; });
    document.querySelectorAll("#tree-body button.tree-toggle").forEach(t => { t.textContent = "▸"; t.setAttribute("aria-expanded", "false"); });
  }
  function toggleSort() { sortBy = sortBy === "size" ? "name" : "size"; return sortBy; }
  // Search shows a FLAT list of matching categories (no deep tree).
  function filter(term) {
    const q = term.toLowerCase().trim();
    const body = $("tree-body"); if (!body || !data) return;
    if (!q) { renderRoots(); return; }
    ikCat = {}; ikAnc = {}; ikOpen = {}; ikPop = {}; ikCtr = 0;
    const matches = sorted(Object.keys(nodes()).filter(c => c.toLowerCase().includes(q)));
    const CAP = 300;
    let html = matches.slice(0, CAP).map(cat => {
      const ik = ikCtr++; ikCat[ik] = cat;
      return `<div class="tree-node" data-key="${ik}">${rowHtml(cat, ik, false)}</div>`;
    }).join("");
    if (!matches.length) html = '<div class="tree-hint">No matching category.</div>';
    else if (matches.length > CAP) html += `<div class="tree-hint">… ${matches.length - CAP} more -- refine the filter</div>`;
    body.innerHTML = html;
    paint();
  }
  // Whole categories (state 2) + "own:<Cat>" for a partly ticked category that
  // keeps its own pages (otherwise they would silently vanish).
  function selected() {
    const pre = data?.own_prefix || "own:";
    const out = [];
    for (const [c, s] of Object.entries(nodeState)) {
      if (s === 2) out.push(c);
      else if (s === 1 && hasOwnPages(c) && ownState[c] === 2) out.push(pre + c);
    }
    return out;
  }
  return {
    load, click, change, selectAll, selectNone, collapseAll, toggleSort, filter, selected,
    get loaded() { return !!data; },
    get sortBy() { return sortBy; },
    get total() { return Object.keys(nodeState).length; },
    reset() { data = null; nodeState = {}; ownState = {}; },
    set onChange(fn) { onChange = fn; },
  };
})();
