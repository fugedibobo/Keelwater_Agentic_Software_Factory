/* Signal Board, shared part: tabs, filters, keyboard, copy, audit table. No network calls here (the live script adds them), so the static page runs from file://. */
(function () {
  const $ = (s, r) => (r || document).querySelector(s), $$ = (s, r) => [...(r || document).querySelectorAll(s)];
  const Board = (window.Board = { flag: "", loadAudit: null });
  const DATA = (() => { try { return JSON.parse($("#board-data").textContent); } catch (e) { return { audit: {} }; } })();

  function showTab() {
    const id = location.hash.slice(1);
    const hit = id && document.getElementById(id), tab = id ? (hit && hit.classList.contains("tab") ? hit : null) : $("#opportunities");
    if (!tab) return;  // a hash that is not a tab (for example a raw record) leaves the current tab alone
    $$(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    $$("[role=tab]").forEach((a) => a.setAttribute("aria-selected", a.dataset.tab === tab.id ? "true" : "false"));
  }

  function applyFilters() {
    const f = { bucket: $("#f-bucket").value, status: $("#f-status").value, squad: $("#f-squad").value };
    $$(".opp").forEach((o) => {
      const show = (!f.bucket || o.dataset.bucket === f.bucket) && (!f.status || o.dataset.status === f.status) && (!f.squad || o.dataset.squad === f.squad) &&
        (!Board.flag || o.dataset.flags.split(" ").includes(Board.flag));
      o.hidden = !show;
    });
    $$(".count").forEach((c) => c.setAttribute("aria-pressed", String(!!Board.flag && c.dataset.filter === Board.flag)));
    $("#clear-filter").hidden = !Board.flag;
  }
  Board.applyFilters = applyFilters;
  Board.showTab = showTab;

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function renderAudit(table, rows, chain, total) {
    $("#audit-head").innerHTML = table === "model_call"
      ? "<tr><th scope=col>Stage</th><th scope=col>Model</th><th scope=col>In / out hash</th><th scope=col>Latency ms</th><th scope=col>Cost USD</th><th scope=col>Detail</th></tr>"
      : "<tr><th scope=col>When</th><th scope=col>Actor</th><th scope=col>Action</th><th scope=col>Target</th><th scope=col>Detail</th></tr>";
    $("#audit-body").innerHTML = rows.slice(0, 100).map((r) => "<tr>" + (table === "model_call"
      ? `<td>${esc(r.stage)}</td><td>${esc(r.model)}</td><td>${esc(r.input_hash)} / ${esc(r.output_hash)}</td><td>${esc(r.latency_ms)}</td><td>${esc(r.cost_usd)}</td>`
      : `<td>${esc(String(r.at).slice(0, 19))}</td><td>${esc(r.actor)}</td><td>${esc(r.action)}</td><td>${esc(r.target_type)}#${esc(r.target_id)}</td>`) +
      `<td><details><summary>row</summary><pre>${esc(JSON.stringify(r, null, 1))}</pre></details></td></tr>`).join("");
    $("#audit-count").textContent = `${total == null ? rows.length : total} ${table} rows match; first 100 shown.`;
    if (chain) { $("#chain").textContent = "Hash chain: " + chain.text; $("#chain").className = "chain " + (chain.ok ? "ok" : "bad"); }
  }
  async function runAudit() {
    const f = new FormData($("#audit-filters")), table = f.get("table");
    if (Board.loadAudit) { const r = await Board.loadAudit(new URLSearchParams(f)); return renderAudit(table, r.rows, r.chain, r.total); }
    const v = (k) => (f.get(k) || "").toLowerCase();
    const rows = (DATA.audit[table] || []).filter((r) => table === "model_call"
      ? (!v("stage") || r.stage.toLowerCase() === v("stage")) && (!v("model") || r.model.toLowerCase().includes(v("model"))) && (!f.get("cached") || r.cached)
      : (!v("actor") || r.actor.toLowerCase().includes(v("actor"))) && (!f.get("from") || r.at.slice(0, 10) >= f.get("from")) && (!f.get("to") || r.at.slice(0, 10) <= f.get("to")));
    renderAudit(table, rows, null, null);
  }

  function copy(id) {
    const el = document.getElementById(id), text = el.textContent;
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove();
  }

  let cur = -1;
  const rows = () => $$(".opp").filter((o) => !o.hidden);
  function move(d) {
    const r = rows(); if (!r.length) return;
    cur = Math.max(0, Math.min(r.length - 1, cur + d));
    $("summary", r[cur]).focus();
  }
  const here = () => { const a = document.activeElement && document.activeElement.closest(".opp"); return a || rows()[Math.max(cur, 0)]; };
  function field(sel, open) { const o = here(); if (!o) return; const d = $("details", o); if (open) d.open = true; const el = $(sel, o); if (el) el.focus(); }

  document.addEventListener("keydown", (e) => {
    const tag = (e.target.tagName || "").toLowerCase();
    if (e.key === "Escape") { $$(".opp details[open]").forEach((d) => (d.open = false)); return; }
    if (tag === "input" || tag === "textarea" || tag === "select" || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key;
    if (k === "j") move(1); else if (k === "k") move(-1);
    else if (k === "m") field("[data-field=target]", true);
    else if (k === "r") field("[data-field=reason]", true);
    else if (k === "p") field("[data-field=pnote]", true);
    else if (k === "s") field("[data-field=squad]", true);
    else if (k === "e") field("[data-field=etitle]", true);
    else if (k === "a") { const o = here(); if (o) { $("details", o).open = true; const b = $("[data-act=accept]", o); if (b && !b.disabled) b.click(); } }
    else if (k === "u") { if (Board.undo) Board.undo(); }
    else if (k === "l") { location.hash = "#opportunities"; const l = $("#labels"); l.open = !l.open; if (l.open) l.scrollIntoView(); }
    else if (k === "?") $("#keys").showModal();
    else return;
    e.preventDefault();
  });
  document.addEventListener("click", (e) => {
    const c = e.target.closest(".count");
    if (c) { Board.flag = Board.flag === c.dataset.filter ? "" : c.dataset.filter; applyFilters(); }
    const cp = e.target.closest("[data-copy]");
    if (cp) copy(cp.dataset.copy);
    if (e.target.id === "audit-apply") runAudit();
  });
  document.addEventListener("change", (e) => { if (e.target.matches("#f-bucket,#f-status,#f-squad")) applyFilters(); });
  window.addEventListener("hashchange", showTab);
  showTab();
  applyFilters();
})();
