/* Signal Board, live part: actions, undo toast, labels. Only served by the local server, never inlined in the static page. */
(function () {
  const $ = (s, r) => (r || document).querySelector(s), $$ = (s, r) => [...(r || document).querySelectorAll(s)];
  let actor = "", lastEvent = null, timer = null;
  fetch("/api/me").then((r) => r.json()).then((d) => { actor = d.actor; });

  const post = async (url, body) => {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Actor": actor }, body: JSON.stringify(body || {}) });
    return { ok: r.ok, data: await r.json().catch(() => ({})) };
  };
  Board.loadAudit = async (p) => (await fetch("/api/audit?" + p.toString())).json();

  function toast(text, undoable) {
    const t = $("#toast"); clearInterval(timer);
    t.innerHTML = "";
    t.append(text + " ");
    if (undoable) {
      const b = document.createElement("button"); b.type = "button"; b.className = "btn"; b.id = "undo-btn";
      let left = 10; b.textContent = `Undo (${left}s)`; b.onclick = () => Board.undo();
      t.append(b);
      timer = setInterval(() => { left -= 1; if (left <= 0) { clearInterval(timer); lastEvent = null; t.textContent = ""; } else b.textContent = `Undo (${left}s)`; }, 1000);
    }
    t.hidden = false;
  }

  async function refresh() {
    const open = $$(".opp details[open]").map((d) => d.closest(".opp").dataset.id), lab = $("#labels") && $("#labels").open;
    const doc = new DOMParser().parseFromString(await (await fetch("/")).text(), "text/html");
    $("main").replaceWith($("main", doc));
    open.forEach((id) => { const o = $(`.opp[data-id="${id}"] details`); if (o) o.open = true; });
    if (lab) $("#labels").open = true;
    Board.applyFilters(); Board.showTab();
  }

  async function send(url, body, label, undoable = true) {
    const r = await post(url, body);
    if (!r.ok) return toast("Not done: " + (typeof r.data.detail === "string" ? r.data.detail : JSON.stringify(r.data.detail)));
    lastEvent = r.data.audit_event_id;
    toast(label, undoable);
    await refresh();
    return r.data;
  }

  Board.undo = async () => {
    if (!lastEvent) return;
    const r = await post("/api/undo", { audit_event_id: lastEvent });
    clearInterval(timer); lastEvent = null;
    toast(r.ok ? "Undone." : "Could not undo: " + (r.data.detail || "unknown"));
    if (r.ok) await refresh();
  };

  document.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-act]");
    if (!b || b.disabled) return;
    const act = b.dataset.act, id = b.dataset.id, scope = b.closest(".act") || b.closest(".actions") || b.parentElement;
    const val = (f) => { const el = $(`[data-field=${f}]`, scope); return el ? (el.type === "checkbox" ? el.checked : el.value.trim()) : ""; };
    const base = `/api/opportunities/${id}/`;
    if (act === "accept") {
      const a = b.closest(".actions");
      $("#confirm-text").textContent = `${a.dataset.title} (${a.dataset.evidence} evidence items)`;
      const dlg = $("#confirm"); dlg.returnValue = "";
      dlg.onclose = () => { if (dlg.returnValue === "ok") send(base + "accept", { confirmed: true }, "Accepted: " + a.dataset.title + ". Queued: drafted on the next run or by keelwater handoff."); else b.focus(); };
      dlg.showModal();
    } else if (act === "merge") { if (!val("target")) return toast("Pick a merge target first."); send(base + "merge", { target_id: val("target") }, "Merged."); }
    else if (act === "reject") { if (!val("reason")) return toast("Pick a reason code first."); send(base + "reject", { reason_code: val("reason"), note: val("rnote") || null }, "Rejected."); }
    else if (act === "park") send(base + "park", { note: val("pnote") || null }, "Parked.");
    else if (act === "reassign") { if (!val("squad")) return toast("Pick a squad first."); send(base + "reassign", { squad: val("squad") }, "Sent to " + val("squad") + "."); }
    else if (act === "edit") send(base + "edit", { title: val("etitle"), problem_statement: val("eprob"), original_wrong: val("ewrong") }, "Edited.");
    else if (act === "confirm_tag" || act === "remove_tag") send(base + act, {}, act === "confirm_tag" ? "Tag confirmed." : "Tag removed.");
    else if (act.startsWith("outtake_")) {
      const n = $(`[data-for="${id}"]`);
      send(`/api/outtakes/${id}/${act.slice(8)}`, { note: n && n.value.trim() || null }, "Draft " + act.slice(8) + "ed.");
    } else if (act === "label") {
      const w = b.closest(".lblbtns"), r = await post("/api/labels", { target_type: w.dataset.tt, target_id: w.dataset.tid, judge: w.dataset.judge, verdict: b.dataset.verdict, critique: null });
      if (!r.ok) return toast("Not saved: " + (r.data.detail || "error"));
      $$("button", w).forEach((x) => (x.disabled = true));
      const v = r.data.revealed;
      $(".revealed", w).textContent = v ? ` Saved. Judge said ${v.verdict}: ${v.critique}` : " Saved.";
      toast("Label saved.");
    }
  });
})();
