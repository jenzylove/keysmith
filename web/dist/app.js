/* Keysmith web app — a dependency-free SPA served from web/dist.
 * Drives the recovery flow against the API in docs/ARCHITECTURE.md:
 *   landing -> start -> interview -> plan -> wallet -> live run -> result -> proof
 * Never stores or re-displays the found password; it is shown once, from the
 * live SSE stream, and copying is the user's choice. */

"use strict";

const app = document.getElementById("app");
const state = { walletTypes: null, demos: null, job: null };

/* ---------- tiny helpers ---------- */
const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  let body = null;
  try { body = await res.json(); } catch (_) { /* non-json */ }
  if (!res.ok) {
    const msg = (body && (body.detail || body.error)) || `request failed (${res.status})`;
    throw new Error(msg);
  }
  return body;
}

function toast(msg) {
  const el = h(`<div class="toast">${esc(msg)}</div>`);
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function humanDuration(sec) {
  sec = Number(sec);
  if (!isFinite(sec) || sec < 1) return "under a second";
  const units = [["day", 86400], ["hour", 3600], ["minute", 60], ["second", 1]];
  for (const [name, size] of units) {
    if (sec >= size) { const n = Math.round(sec / size); return `${n} ${name}${n !== 1 ? "s" : ""}`; }
  }
  return "under a second";
}
const rangeText = (pair) => `${humanDuration(pair[0])} – ${humanDuration(pair[1])}`;
const fmtInt = (n) => Number(n).toLocaleString("en-US");

function render(node) { app.innerHTML = ""; app.appendChild(node); window.scrollTo(0, 0); }
function errorScreen(msg) {
  render(h(`<div class="panel error-box"><h2>Something went wrong</h2>
    <p class="sub">${esc(msg)}</p>
    <a class="btn secondary" href="#/" data-nav>Back to start</a></div>`));
}

/* ---------- footer status ---------- */
async function refreshStatus() {
  const el = document.getElementById("footer-status");
  try {
    const hres = await api("/api/health");
    const runner = hres.runner === "vm" ? "sealed per-job VM" : "runner not configured (demo build)";
    const model = hres.model ? `· model ${hres.model}` : "· inference not configured";
    el.innerHTML = `<span class="pulse"></span>box runner: ${esc(runner)} ${esc(model)}`;
  } catch (_) { el.textContent = "backend unreachable"; }
}

/* ---------- landing ---------- */
const ICON = {
  lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="10.5" width="16" height="9.5" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/><circle cx="12" cy="15" r="1.3"/></svg>',
  list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1.1"/><circle cx="4.5" cy="12" r="1.1"/><circle cx="4.5" cy="18" r="1.1"/></svg>',
  shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.6-3 7.8-7 9-4-1.2-7-4.4-7-9V6z"/><path d="M9 12l2 2 4-4"/></svg>',
};

function viewLanding() {
  render(h(`<section>
    <div class="hero">
      <div class="eyebrow">Non-custodial wallet-password recovery · runs on Vultr</div>
      <h1>Your old wallet is still there.<br/><span class="accent">Let's remember the password.</span></h1>
      <p class="lede">Tell Keysmith what you half-remember — a name, a year, the way you swap
        letters for numbers. It turns your memories into targeted guesses and tries them inside
        a sealed box that can't send your wallet anywhere. Not even to us.</p>
      <div class="cta-row">
        <a class="btn" href="#/start" data-nav>Start a recovery</a>
        <a class="btn secondary" href="#/start?demo=1" data-nav>Watch a demo wallet open ↗</a>
      </div>
    </div>
    <div class="features">
      <div class="feature"><span class="feat-ico">${ICON.lock}</span>
        <div><div class="title">Sealed, every job</div>
        <div class="meta">A fresh VM per recovery — no network, wallet mounted read-only, destroyed after. A teardown receipt proves it.</div></div></div>
      <div class="feature"><span class="feat-ico">${ICON.list}</span>
        <div><div class="title">Smart guesses, not brute force</div>
        <div class="meta">You see the exact list before anything runs. No hidden expansion — honest odds, and honest misses.</div></div></div>
      <div class="feature"><span class="feat-ico">${ICON.shield}</span>
        <div><div class="title">Break-in test, on camera</div>
        <div class="meta">A poisoned hint that tells the agent to read and upload your wallet — watch it get denied, live.</div></div></div>
    </div>
  </section>`));
}

/* ---------- start ---------- */
async function viewStart(showDemo) {
  render(h(`<section><div class="panel"><h2>Loading…</h2></div></section>`));
  try {
    if (!state.walletTypes) state.walletTypes = await api("/api/wallet-types");
    if (!state.demos) state.demos = await api("/api/demo");
  } catch (e) { return errorScreen(e.message); }

  const demoCards = state.demos.map((d) => `
    <button class="choice" data-demo="${esc(d.id)}">
      <div class="title">${esc(d.wallet_type)} · test wallet</div>
      <div class="meta">${esc(d.owner_story || "")}</div>
      <div class="speed">hints: ${esc(d.notes || "")}</div>
    </button>`).join("");

  const typeCards = state.walletTypes.map((w) => `
    <button class="choice" data-type="${esc(w.id)}">
      <div class="title">${esc(w.label)}</div>
      <div class="meta">${esc(w.notes)}</div>
      <div class="speed">~${fmtInt(w.speed_pw_s)} guesses/sec · ${w.input === "seed" ? "seed phrase" : "wallet file"}</div>
    </button>`).join("");

  const node = h(`<section>
    <div class="panel">
      <h2>Watch a demo wallet open</h2>
      <p class="sub">Public test wallets with no funds. You play the owner: answer the interview and watch it open end to end.</p>
      <div class="grid">${demoCards || '<p class="note">No demo wallets loaded on this build yet.</p>'}</div>
    </div>
    <div class="panel">
      <h2>Recover your own wallet</h2>
      <p class="sub">Pick your wallet type. You'll see every guess before anything runs, and nothing is uploaded until you accept the plan.</p>
      <div class="grid">${typeCards}</div>
    </div>
  </section>`);

  $$("[data-type]", node).forEach((b) => b.onclick = () => beginJob({ wallet_type: b.dataset.type }));
  $$("[data-demo]", node).forEach((b) => b.onclick = () => beginJob({ demo_id: b.dataset.demo }));
  render(node);
  if (showDemo) document.querySelector(".panel").scrollIntoView({ behavior: "smooth" });
}

async function beginJob(payload) {
  try {
    const res = await api("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const wt = payload.wallet_type || (state.demos.find((d) => d.id === payload.demo_id) || {}).wallet_type;
    state.job = {
      id: res.job_id, wallet_type: wt, demo_id: res.demo_id || null,
      prefill: res.prefill_answers || {}, walletLoaded: !!res.demo_id,
    };
    viewInterview();
  } catch (e) { toast(e.message); }
}

/* ---------- interview ---------- */
const INTERVIEW_FIELDS = [
  ["names", "Names, pets, places, teams", "Your dog, a child, a street, a football club — whatever you'd reach for."],
  ["years", "Years", "A year or a rough range. “late 90s” is fine."],
  ["numbers", "Numbers you tend to use", "A lucky number, a house number, a short run of digits."],
  ["symbols", "Symbols you add", "e.g. ! or !! or $ — usually at the end."],
  ["swaps", "Letter-for-symbol habits", "e.g. you always wrote s as $, or o as 0."],
  ["old_passwords", "Old passwords you remember", "A password you used elsewhere around then — we vary it."],
  ["notes", "Anything else", "Length, capitalisation, how you usually built passwords."],
];

function viewInterview() {
  const j = state.job;
  const pre = j.prefill || {};
  const seed = j.wallet_type === "bip39_seed";
  const fields = INTERVIEW_FIELDS.map(([k, lab, hint]) => `
    <label class="field">
      <span class="lab">${esc(lab)}</span>
      <span class="hint">${esc(hint)}</span>
      <input type="text" data-k="${k}" value="${esc(pre[k] || "")}" autocomplete="off" />
    </label>`).join("");

  const seedNote = seed ? `<div class="odds">This is a seed-phrase wallet. The interview is optional —
    recovery searches the missing words against your known address. You can skip straight to the seed.</div>` : "";

  const node = h(`<section>
    <div class="panel">
      <div class="row-between"><h2>Tell me what you remember</h2>
        <span class="note">${j.demo_id ? "demo wallet (prefilled — edit freely)" : "wallet type: " + esc(j.wallet_type)}</span></div>
      <p class="sub">Only what you actually remember. Blank is better than a guess — the plan stays small and honest.
        Your notes are treated as data: if they contain instructions, they're ignored.</p>
      ${seedNote}
      ${fields}
      <div class="cta-row">
        <button class="btn" id="build-plan">Build the plan</button>
        ${seed ? '<button class="btn ghost" id="skip-seed">Skip to the seed</button>' : ""}
      </div>
    </div>
  </section>`);

  $("#build-plan", node).onclick = async () => {
    const answers = {};
    $$("[data-k]", node).forEach((i) => answers[i.dataset.k] = i.value);
    $("#build-plan", node).disabled = true; $("#build-plan", node).textContent = "Thinking…";
    try {
      const plan = await api(`/api/jobs/${j.id}/hints`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers }),
      });
      j.plan = plan; viewPlan();
    } catch (e) { toast(e.message); $("#build-plan", node).disabled = false; $("#build-plan", node).textContent = "Build the plan"; }
  };
  if (seed) $("#skip-seed", node).onclick = async () => {
    try { j.plan = await api(`/api/jobs/${j.id}/hints`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers: {} }) }); viewPlan(); }
    catch (e) { toast(e.message); }
  };
  render(node);
}

/* ---------- plan ---------- */
function planWords(profile) {
  if (!profile) return "";
  const bits = [];
  if (profile.words && profile.words.length) bits.push(`base words <b>${profile.words.map(esc).join(", ")}</b>`);
  if (profile.old_passwords && profile.old_passwords.length) bits.push(`old passwords <b>${profile.old_passwords.map(esc).join(", ")}</b>`);
  if (profile.years && profile.years.length) bits.push(`years ${profile.years.map(esc).join(", ")}`);
  if (profile.numbers && profile.numbers.length) bits.push(`numbers ${profile.numbers.map(esc).join(", ")}`);
  if (profile.symbols && profile.symbols.length) bits.push(`symbols ${profile.symbols.map(esc).join(", ")}`);
  if (profile.use_leet) bits.push(`letter swaps ${esc(JSON.stringify(profile.leet_map || {}))}`);
  if (profile.separators && profile.separators.length) bits.push(`separators ${profile.separators.map(esc).join(" ")}`);
  if (profile.missing_words) bits.push(`<b>${profile.missing_words}</b> missing seed word(s)`);
  return bits.join("; ");
}

function viewPlan() {
  const j = state.job, p = j.plan, est = p.estimate || {};
  const sample = (p.sample || []).map(esc).join("\n");
  const node = h(`<section>
    <div class="panel">
      <div class="row-between"><h2>The plan</h2>
        ${p.model ? `<span class="note">written by ${esc(p.model)} · ${fmtInt(p.llm_ms)} ms</span>` : '<span class="note">computed from the seed</span>'}</div>
      <p class="sub">In plain words: ${planWords(p.profile) || "your remembered details"}.</p>
      <div class="stat-row">
        <div class="stat"><div class="n">${fmtInt(p.candidate_count)}</div><div class="k">guesses, in order</div></div>
        <div class="stat"><div class="n">${est.pw_per_sec ? fmtInt(est.pw_per_sec) : "—"}</div><div class="k">guesses/sec on the box</div></div>
      </div>
      <div class="odds">
        <div><b>Expected</b> (found about halfway): ${est.expected_s ? esc(rangeText(est.expected_s)) : "—"}.</div>
        <div><b>Worst case</b> (full scan): ${est.worst_case_s ? esc(rangeText(est.worst_case_s)) : "—"}.</div>
        <div style="margin-top:6px" class="note">${esc(est.reasoning || "")}</div>
      </div>
      <details class="raw"><summary>Show the raw guesses we'll try (first ${(p.sample || []).length})</summary>
        <div class="codelist">${sample || "(none)"}</div>
        <p class="note">This is literally what runs — no hidden expansion.</p>
      </details>
      <div class="cta-row">
        <button class="btn" id="accept-plan">Accept &amp; ${j.walletLoaded ? "open the box" : "continue"}</button>
        <button class="btn ghost" id="redo">Change my hints</button>
      </div>
    </div>
  </section>`);
  $("#redo", node).onclick = () => viewInterview();
  $("#accept-plan", node).onclick = () => (j.walletLoaded ? startRun() : viewWallet());
  render(node);
}

/* ---------- wallet upload ---------- */
function viewWallet() {
  const j = state.job;
  const seed = j.wallet_type === "bip39_seed";
  const body = seed ? `
    <label class="field"><span class="lab">Your seed words</span>
      <span class="hint">Space-separated. Write <b>?</b> for any word you've lost or aren't sure of (up to 2).</span>
      <textarea data-seed rows="3" placeholder="legal winner thank ? zebra ? ..."></textarea></label>
    <label class="field"><span class="lab">One address from this wallet</span>
      <span class="hint">Any address you know belongs to it — recovery checks guesses against it.</span>
      <input type="text" data-addr placeholder="bc1q… or 0x…" /></label>`
    : `
    <label class="field"><span class="lab">Your wallet file</span>
      <span class="hint">It goes straight into the sealed box over an inbound-only channel. Max 5 MB. Never stored.</span>
      <input type="file" data-file /></label>`;

  const node = h(`<section>
    <div class="panel">
      <h2>${seed ? "Enter your seed" : "Upload your wallet"}</h2>
      <p class="sub">Only now, after you've accepted the plan. ${seed ? "" : "The file never touches our database and never leaves the box."}</p>
      ${body}
      <div class="odds">Only run this on a wallet you own. We have no way to verify ownership, and we say so plainly.</div>
      <button class="btn" id="to-run">Seal the box &amp; begin</button>
    </div>
  </section>`);

  $("#to-run", node).onclick = async () => {
    try {
      if (seed) {
        const words = ($("[data-seed]", node).value || "").trim().split(/\s+/).filter(Boolean);
        const address = ($("[data-addr]", node).value || "").trim();
        if (!words.length) return toast("enter your seed words");
        if (!address) return toast("enter one known address");
        await api(`/api/jobs/${j.id}/wallet`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ seed_words: words, address }) });
      } else {
        const f = $("[data-file]", node).files[0];
        if (!f) return toast("choose your wallet file");
        const fd = new FormData(); fd.append("file", f);
        await api(`/api/jobs/${j.id}/wallet`, { method: "POST", body: fd });
      }
      startRun();
    } catch (e) { toast(e.message); }
  };
  render(node);
}

/* ---------- live run ---------- */
const STAGE_ORDER = ["queued", "creating_box", "sealing", "uploading", "running", "found", "destroying", "destroyed"];
const STAGE_LABEL = {
  queued: "queued", creating_box: "creating box", sealing: "sealing", uploading: "uploading",
  running: "running", found: "found", not_found: "not found", destroying: "destroying",
  destroyed: "destroyed", error: "error",
};

async function startRun() {
  const j = state.job;
  const node = h(`<section>
    <div class="row-between"><h2>Live recovery</h2><span class="note" id="box-label">opening the box…</span></div>
    <div class="stages" id="stages"></div>
    <div class="run-grid">
      <div>
        <div class="panel"><h2>Progress</h2>
          <div class="bar"><i id="bar"></i></div>
          <div class="progress-meta" id="pmeta">waiting…</div>
          <div class="spacer"></div>
          <div class="log" id="log"></div>
        </div>
        <div class="panel" id="result-panel" style="display:none"></div>
      </div>
      <div>
        <div class="panel"><h2>Containment</h2>
          <ul class="seal" id="seal"><li><span>waiting for seal…</span></li></ul>
          <div class="spacer"></div>
          <button class="btn danger" id="attack-btn" disabled>Run the break-in test</button>
          <div id="attacks" style="margin-top:12px"></div>
        </div>
        <div class="panel" id="receipt-panel" style="display:none"></div>
      </div>
    </div>
  </section>`);
  render(node);
  renderStages(node, null);

  try {
    await api(`/api/jobs/${j.id}/start`, { method: "POST" });
  } catch (e) { return errorScreen(e.message); }

  const es = new EventSource(`/api/jobs/${j.id}/events`);
  const logEl = $("#log", node);
  const attackBtn = $("#attack-btn", node);
  let attackRun = false;

  attackBtn.onclick = async () => {
    attackBtn.disabled = true; attackRun = true;
    try { await api(`/api/jobs/${j.id}/attack`, { method: "POST" }); }
    catch (e) { toast(e.message); attackBtn.disabled = false; }
  };

  es.onmessage = (msg) => {
    let ev; try { ev = JSON.parse(msg.data); } catch (_) { return; }
    handleEvent(node, ev, { logEl, attackBtn, j });
    if (ev.type === "receipt") { es.close(); }
  };
  es.onerror = () => { /* keepalive gaps are normal; browser retries */ };
}

function renderStages(node, current) {
  const el = $("#stages", node);
  const idx = current ? STAGE_ORDER.indexOf(current === "not_found" ? "found" : current) : -1;
  el.innerHTML = STAGE_ORDER.map((s, i) => {
    let cls = "stage-pill";
    if (current === "error") cls += i === 0 ? " err" : "";
    else if (i < idx) cls += " done";
    else if (i === idx) cls += " active";
    return `<span class="${cls}">${esc(STAGE_LABEL[s])}</span>`;
  }).join("");
}

function handleEvent(node, ev, ctx) {
  const { logEl, attackBtn } = ctx;
  switch (ev.type) {
    case "stage":
      renderStages(node, ev.stage);
      if (ev.stage === "error") { $("#box-label", node).textContent = "stopped"; }
      break;
    case "box":
      $("#box-label", node).innerHTML = `<span class="pulse"></span>box ${esc(ev.vm_id)} · ${esc(ev.region)} · ${esc(ev.plan)} · ip hidden`;
      break;
    case "seal": {
      const ok = (v) => /none|read only|blocked|runsc/i.test(v);
      $("#seal", node).innerHTML = (ev.checks || []).map((c) =>
        `<li><span>${esc(c.name.replace(/_/g, " "))}</span>
          <span class="v">${esc(c.value)} <span class="badge ${ok(c.value) ? "ok" : "no"}">${ok(c.value) ? "held" : "check"}</span></span></li>`).join("");
      attackBtn.disabled = false;
      break;
    }
    case "progress": {
      const pct = ev.total ? Math.min(100, Math.round((ev.tried / ev.total) * 100)) : 0;
      $("#bar", node).style.width = pct + "%";
      $("#pmeta", node).textContent = `${fmtInt(ev.tried)} / ${fmtInt(ev.total)} guesses · ${fmtInt(ev.rate)} /sec`;
      break;
    }
    case "log":
      logEl.textContent += ev.line + "\n"; logEl.scrollTop = logEl.scrollHeight; break;
    case "attack": {
      const held = ev.held;
      $("#attacks", node).appendChild(h(`<div class="attack-item">
        <div><b>${esc(ev.step)}</b> <span class="badge ${held ? "ok" : "no"}">${held ? "blocked" : "GOT THROUGH"}</span></div>
        <div class="cmd">$ ${esc(ev.command)}</div>
        <div class="res">→ ${esc(ev.result)}</div></div>`));
      break;
    }
    case "result":
      showResult(node, ev); break;
    case "receipt":
      showReceipt(node, ev.receipt); break;
    case "error":
      $("#result-panel", node).style.display = "block";
      $("#result-panel", node).className = "panel error-box";
      $("#result-panel", node).innerHTML = `<h2>Couldn't finish</h2><p class="sub">${esc(ev.message)}</p>`;
      break;
  }
}

function showResult(node, ev) {
  const panel = $("#result-panel", node);
  panel.style.display = "block";
  if (ev.found) {
    panel.innerHTML = `<h2>Found it 🗝️</h2>
      <div class="reveal" id="pw">${esc(ev.password)}</div>
      <div class="once">Shown once. Copy it now — it is never stored and the box is being destroyed.</div>
      <div class="cta-row" style="margin-top:12px"><button class="btn" id="copy">Copy password</button></div>`;
    $("#copy", panel).onclick = () => { navigator.clipboard?.writeText(ev.password).then(() => toast("copied")); };
  } else {
    panel.innerHTML = `<h2>No match in this plan</h2>
      <p class="sub">An honest miss. The guesses you approved didn't include it. Try again with more detail —
      a different year, a symbol, an old password — and we'll build a new plan.</p>
      <a class="btn secondary" href="#/start" data-nav>Try again</a>`;
  }
}

function showReceipt(node, r) {
  if (!r) return;
  const panel = $("#receipt-panel", node);
  panel.style.display = "block";
  const row = (k, v) => `<div class="row"><span>${esc(k)}</span><span>${esc(v)}</span></div>`;
  panel.innerHTML = `<h2>Teardown receipt</h2>
    <div class="center" style="margin:6px 0 12px">
      <span class="badge ${r.containment_held ? "ok" : "no"}">${r.containment_held ? "containment held" : "containment check"}</span>
    </div>
    <div class="receipt">
      ${row("job", r.job_id)}
      ${row("mode", r.mode)}
      ${row("outcome", r.outcome)}
      ${row("vm id", r.vm_id)}
      ${row("created", r.created_at)}
      ${row("destroyed", r.destroyed_at)}
      ${row("guesses tried", fmtInt(r.guesses_tried))}
      ${row("wallet bytes egressed", r.bytes_egressed_wallet)}
      ${row("cracker network", r.network_mode)}
      ${row("agent wallet mounts", r.agent_wallet_mounts)}
      ${row("api delete", r.api_delete_status || "—")}
    </div>`;
}

/* ---------- proof ---------- */
async function viewProof() {
  render(h(`<section><div class="panel"><h2>Loading proof…</h2></div></section>`));
  let data; try { data = await api("/api/proof"); } catch (e) { return errorScreen(e.message); }
  if (!data || data.status === "not run") {
    return render(h(`<section><div class="panel">
      <h2>Proof page</h2>
      <p class="sub">The answer key of 20 test wallets is written blind (15 derivable, 5 honest misses) and lives at
      <code>data/proof/cases.json</code>. Results appear here after the full set runs on Vultr —
      agent rules vs plain btcrecover defaults, same time budget, misses published with the fix.</p>
      <div class="odds">Status: not run yet on this deployment. We publish the misses, not just the wins.</div>
    </div></section>`));
  }
  const rows = (data.cases || data.results || []).map((c) => `
    <tr><td>${esc(c.id)}</td><td>${esc(c.wallet_type)}</td>
      <td><span class="tag ${c.found ? "found" : "miss"}">${c.found ? "recovered" : "miss"}</span></td>
      <td>${c.guesses != null ? fmtInt(c.guesses) : "—"}</td>
      <td>${esc(c.note || c.why || "")}</td></tr>`).join("");
  render(h(`<section><div class="panel">
    <h2>Proof: agent rules vs plain defaults</h2>
    <p class="sub">${esc(data.summary || "20 test wallets, hints written before any run.")}</p>
    <table class="proof"><thead><tr><th>case</th><th>type</th><th>result</th><th>guesses</th><th>note</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="5">no rows</td></tr>'}</tbody></table>
  </div></section>`));
}

/* ---------- router ---------- */
function route() {
  const hash = location.hash || "#/";
  const [path, query] = hash.split("?");
  if (path === "#/" || path === "") viewLanding();
  else if (path === "#/start") viewStart(query && query.includes("demo=1"));
  else if (path === "#/proof") viewProof();
  else viewLanding();
}

document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-nav]");
  if (a) { /* allow default hash nav */ }
});
window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", () => { route(); refreshStatus(); });
route(); refreshStatus();
