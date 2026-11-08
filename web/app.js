// Red Flag Club — community site (specs 006, 007). Static, no dependencies, no tracking.
import { answer, HELP, LINKS } from "./assistant.js";
import { loadStories, storiesFor, viewShare, viewStocks, viewStories, viewStory } from "./stories.js";
import { viewQuiz } from "./quiz.js";

const $ = (sel, el = document) => el.querySelector(sel);
const main = $("#main");
const esc = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 0) => (x == null ? "n/a" : `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(d)}%`);
const SYM = /^[A-Z][A-Z0-9.\-]{0,9}$/;

// ---------------------------------------------------------------- data
const cache = {};
async function load(name) {
  if (!cache[name]) cache[name] = fetch(`data/${name}.json`, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  return cache[name];
}
async function symbols() {
  if (!cache._sym) {
    cache._sym = load("symbols").then((d) => {
      const m = new Map();
      if (!d) return m;
      for (const row of d.rows) {
        const o = {};
        d.fields.forEach((f, i) => (o[f] = row[i]));
        m.set(o.s, o);
      }
      return m;
    });
  }
  return cache._sym;
}
async function all() {
  const [meta, movers, scan, outcomes, syms] = await Promise.all([load("meta"), load("movers"), load("scan"), load("outcomes"), symbols()]);
  return { meta, movers, scan, outcomes, symbols: syms };
}

// ---------------------------------------------------------------- pieces
const badge = (v) => (v ? `<span class="badge b-${esc(v.replace(/\s/g, ""))}">${esc(v)}</span>` : `<span class="muted small">not checked</span>`);
const symLink = (s) => `<a class="sym" href="#/t/${encodeURIComponent(s)}">${esc(s)}</a>`;

function spark(values, w = 96, h = 26) {
  if (!values || values.length < 2) return `<span class="muted small">—</span>`;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => `${(2 + (i * (w - 4)) / (values.length - 1)).toFixed(1)},${(h - 3 - ((v - lo) / span) * (h - 6)).toFixed(1)}`).join(" ");
  const last = pts.split(" ").pop().split(",");
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="shape of the last ${values.length} closes, indexed to 100: ends at ${values.at(-1)}">` +
    `<title>${values.length} sessions, indexed to 100 at the start: low ${lo}, high ${hi}, last ${values.at(-1)}</title>` +
    `<polyline points="${pts}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>` +
    `<circle cx="${last[0]}" cy="${last[1]}" r="3.5" fill="var(--series-1)" stroke="var(--surface-1)" stroke-width="2"/></svg>`;
}

function riskBanner(meta) {
  const b = meta?.base_rates?.bracket, c = meta?.base_rates?.collapse;
  if (!b) return "";
  return `<div class="banner" role="note"><b>These are the riskiest stocks, not picks.</b>
    In this project's backtest, buying the next open after a pump trigger and exiting at +20% or −10% won
    ${(b.win * 100).toFixed(1)}% of ${b.n.toLocaleString()} trades — below the ${b.breakeven * 100}% needed to break even —
    and lost ${Math.abs(b.per_trade * 100).toFixed(1)}% per trade on average. ${c ? `Of ${c.n_runs.toLocaleString()} runs of 100%+ in 10 sessions, ${c.n_collapsed} fell 70% or more within 20 sessions.` : ""}</div>`;
}

function flagsCell(flags, why) {
  if (!flags?.length) return why && why !== "no rule fired" ? `<span class="muted">${esc(why)}</span>` : `<span class="muted">—</span>`;
  const more = flags.length > 2 ? ` <span class="muted">+${flags.length - 2}</span>` : "";
  return esc(flags.slice(0, 2).join("; ")) + more;
}

function sortable(table, rows, cols, render) {
  let key = null, dir = -1;
  const head = table.querySelector("thead tr");
  head.innerHTML = cols.map((c, i) => `<th class="${c.num ? "num" : ""}">${c.sort ? `<button data-i="${i}" aria-label="Sort by ${esc(c.label)}">${esc(c.label)}</button>` : esc(c.label)}</th>`).join("");
  const body = table.querySelector("tbody");
  const draw = () => {
    const list = key == null ? rows : [...rows].sort((a, b) => {
      const x = cols[key].sort(a), y = cols[key].sort(b);
      return (x == null) - (y == null) || (x < y ? -dir : x > y ? dir : 0);
    });
    body.innerHTML = list.length ? list.map(render).join("") : `<tr><td colspan="${cols.length}" class="muted">Nothing to show.</td></tr>`;
  };
  head.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]");
    if (!b) return;
    const i = +b.dataset.i;
    dir = key === i ? -dir : -1;
    key = i;
    draw();
  });
  draw();
}

function noData(what) {
  return `<div class="card"><h2>No data yet</h2><p class="muted">${esc(what)} appears after the first scan has run.</p></div>`;
}

// ---------------------------------------------------------------- views
async function viewToday() {
  const d = await all();
  const m = d.meta;
  if (!m) return (main.innerHTML = noData("This page"));
  const latest = d.scan?.sessions?.[0];
  const veto = latest?.hits?.filter((h) => h.verdict === "VETO").length ?? 0;
  const week = d.movers?.lists?.week ?? [];
  main.innerHTML = `
    <h1>The investment club that tells you when to walk away.</h1>
    <p class="lead">A free risk check for US penny and small-cap stocks. If someone in a group chat, an ad or a
      "teacher" is pushing a stock, look it up here first. Data from the close of <b>${esc(m.data_session ?? "—")}</b>.</p>
    <div class="grid">
      <a class="card tile" href="#/top/day" style="text-decoration:none;color:inherit"><div class="n">${m.counts.risk_list.day}</div><div class="l">penny stocks up most today</div></a>
      <a class="card tile" href="#/scan" style="text-decoration:none;color:inherit"><div class="n">${latest?.hits?.length ?? 0}</div><div class="l">on the risk scan (${esc(latest?.session ?? "—")})</div></a>
      <a class="card tile" href="#/scan" style="text-decoration:none;color:inherit"><div class="n">${veto}</div><div class="l">of them with a Layer 1 VETO</div></a>
      <a class="card tile" href="#/track" style="text-decoration:none;color:inherit"><div class="n">${(d.outcomes?.forward?.episodes ?? 0) + (d.outcomes?.backfilled?.episodes ?? 0)}</div><div class="l">past episodes tracked to their outcome</div></a>
    </div>
    ${riskBanner(m)}
    <section class="card"><h2>Biggest run-ups this week</h2>
      <div class="scroll"><table><thead><tr><th>Symbol</th><th class="num">5 sessions</th><th>Layer 1</th><th class="hide-sm">Shape</th><th>Red flags</th></tr></thead><tbody>
      ${week.slice(0, 10).map((r) => `<tr><td>${symLink(r.s)}</td><td class="num">${pct(r.chg)}</td><td>${badge(r.verdict)}</td><td class="hide-sm">${spark(r.spark)}</td><td class="wrap-cell">${flagsCell(r.flags, r.why)}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">No list yet.</td></tr>`}
      </tbody></table></div>
      <p class="small"><a href="#/top/week">All 100 for the week →</a></p></section>
    ${await storiesTeaser()}
    <section class="grid">
      <div class="card"><h2>Being pitched a stock?</h2><p>Type the ticker in the box at the top, or ask the <a href="#/assistant">assistant</a>. Share the link with your group: every ticker has its own page.</p></div>
      <div class="card"><h2>Already lost money?</h2><p>You're not alone. See <a href="#/help">what to do now</a> — and don't pay anyone who offers to get it back.</p></div>
      <div class="card"><h2>Run a group?</h2><p>Every list is downloadable as <a href="data/movers_day.csv">CSV</a> or <a href="data/movers.json">JSON</a> for your bot. See <a href="#/about">About</a> for the format.</p></div>
    </section>`;
}

async function storiesTeaser() {
  const d = await loadStories();
  const top = d.stories.slice(0, 3);
  return `<section class="card"><h2>Real stories from the community</h2>
    ${top.length ? `<ul>${top.map((x) => `<li><a href="#/s/${encodeURIComponent(x.id)}">${esc(x.title)}</a> <span class="muted small">${esc((x.stocks ?? []).join(", "))}</span></li>`).join("")}</ul>
      <p class="small"><a href="#/stories">All ${d.count} stories →</a> · <a href="#/quiz">Can you spot the red flags? (2 min) →</a></p>`
    : `<p>Were you pushed into a stock that collapsed? <a href="#/share">Share your story</a> by voice or text — it is anonymised before anyone sees it.
      Or test yourself: <a href="#/quiz">spot the red flags (2 min)</a>.</p>`}</section>`;
}

async function viewTop(win = "day") {
  const d = await all();
  const lists = d.movers?.lists;
  if (!lists) return (main.innerHTML = noData("The top 100"));
  const names = { day: "Today", week: "This week (5 sessions)", month: "This month (21 sessions)" };
  if (!lists[win]) win = "day";
  const rows = lists[win];
  main.innerHTML = `
    <h1>Top 100 penny-stock run-ups</h1>
    <p class="lead">US stocks closing under $5 with at least $${(d.movers.min_value / 1000).toFixed(0)}k traded a day, ranked by price change.
      Data from the close of <b>${esc(d.movers.session)}</b>. ${rows.length} listed.</p>
    ${riskBanner(d.meta)}
    <nav class="tabs" aria-label="Period">${Object.keys(names).map((k) => `<a href="#/top/${k}" aria-current="${k === win}">${names[k]}</a>`).join("")}</nav>
    <label class="small"><input type="checkbox" id="only-veto"> Only Layer 1 VETO</label>
    <div class="card scroll" style="margin-top:10px"><table id="t"><thead><tr></tr></thead><tbody></tbody></table></div>
    <p class="small"><a href="data/movers_${win}.csv" download>Download CSV</a> · <a href="data/movers.json">JSON</a></p>`;
  const cols = [
    { label: "#", num: true }, { label: "Symbol", sort: (r) => r.s }, { label: "Price band", sort: (r) => r.band },
    { label: "Change", num: true, sort: (r) => r.chg }, { label: "Volume ×", num: true, sort: (r) => r.rv },
    { label: "Layer 1", sort: (r) => ({ VETO: 0, CAUTION: 1, "INSUFFICIENT DATA": 2, "NO FLAGS": 3 })[r.verdict] ?? 9 },
    { label: "Shape" }, { label: "Red flags", sort: (r) => -(r.flags?.length ?? 0) }, { label: "Days on scan", num: true, sort: (r) => r.scan_days },
  ];
  const render = (r) => `<tr><td class="num muted">${r._rank}</td><td>${symLink(r.s)}</td><td>${esc(r.band)}</td><td class="num">${pct(r.chg)}</td>
    <td class="num">${r.rv == null ? "n/a" : r.rv + "×"}</td><td>${badge(r.verdict)}</td><td>${spark(r.spark)}</td>
    <td class="wrap-cell">${flagsCell(r.flags, r.why)}</td><td class="num">${r.scan_days || ""}</td></tr>`;
  const ranked = rows.map((r, i) => ({ ...r, _rank: i + 1 }));
  const draw = () => sortable($("#t"), $("#only-veto").checked ? ranked.filter((r) => r.verdict === "VETO") : ranked, cols, render);
  $("#only-veto").addEventListener("change", draw);
  draw();
}

async function viewScan() {
  const d = await all();
  const sessions = d.scan?.sessions ?? [];
  if (!sessions.length) return (main.innerHTML = noData("The risk scan"));
  main.innerHTML = `
    <h1>Risk scan</h1>
    <p class="lead">Every US stock closing $1–$30 that rose 50% or more over 5 or 21 sessions, with this tool's
      Layer 1 verdict on that day. Logged once and never edited, so you can see what it said before the outcome was known.</p>
    ${riskBanner(d.meta)}
    <label class="field" style="max-width:240px">Session <select id="sess">${sessions.map((s) => `<option>${esc(s.session)}</option>`).join("")}</select></label>
    <div class="card scroll" style="margin-top:12px"><table id="t"><thead><tr></tr></thead><tbody></tbody></table></div>`;
  const cols = [{ label: "Symbol", sort: (r) => r.s }, { label: "Layer 1", sort: (r) => (r.verdict === "VETO" ? 0 : 1) },
    { label: "5 sessions", num: true, sort: (r) => r.r5 }, { label: "21 sessions", num: true, sort: (r) => r.r21 },
    { label: "Why logged", sort: (r) => r.reason }, { label: "Main reason" }];
  const render = (r) => `<tr><td>${symLink(r.s)}</td><td>${badge(r.verdict)}</td><td class="num">${pct(r.r5)}</td><td class="num">${pct(r.r21)}</td>
    <td>${esc(r.reason)}${r.flags.length ? ` <span class="muted small">(${esc(r.flags.join(", "))})</span>` : ""}</td><td class="wrap-cell">${esc(r.why)}</td></tr>`;
  const draw = () => sortable($("#t"), sessions.find((s) => s.session === $("#sess").value)?.hits ?? [], cols, render);
  $("#sess").addEventListener("change", draw);
  draw();
}

function tickerStories(sym, data) {
  const list = storiesFor(data, sym);
  if (!list.length) return "";
  return `<div class="card"><h2>${list.length} ${list.length === 1 ? "person has" : "people have"} shared a story about ${esc(sym)}</h2>
    <ul>${list.slice(0, 5).map((x) => `<li><a href="#/s/${encodeURIComponent(x.id)}">${esc(x.title)}</a></li>`).join("")}</ul>
    <p class="small muted">Self-reported accounts, anonymised before publishing. <a href="#/stories?stock=${encodeURIComponent(sym)}">All of them →</a></p></div>`;
}

async function viewTicker(sym) {
  const d = await all();
  const r = d.symbols.get(sym);
  const share = `${location.origin}${location.pathname}#/t/${encodeURIComponent(sym)}`;
  const eps = (d.outcomes?.episodes ?? []).filter((e) => e.s === sym);
  const hist = (d.scan?.sessions ?? []).flatMap((s) => s.hits.filter((h) => h.s === sym).map((h) => ({ ...h, session: s.session })));
  const lists = Object.entries(d.movers?.lists ?? {}).filter(([, rows]) => rows.some((x) => x.s === sym)).map(([k]) => k);
  const listRow = Object.values(d.movers?.lists ?? {}).flat().find((x) => x.s === sym);
  if (!r) {
    main.innerHTML = `<h1>${esc(sym)}</h1>
      <div class="card"><p><b>Not in today's small-cap set.</b> ${esc(sym)} did not close at $30 or less on ${esc(d.meta?.data_session ?? "the last session")}
      in the data this site has. It may be a larger company, not US-listed, delisted, or mistyped.</p>
      <p>If someone is pushing it to you, the warning signs still apply: <a href="#/help">check the red flags</a>.</p></div>
      ${tickerStories(sym, await loadStories())}`;
    return;
  }
  main.innerHTML = `
    <h1>${esc(sym)} <span class="muted small">${esc(r.band ?? "")}</span></h1>
    <p class="lead">Data from the close of ${esc(d.meta?.data_session ?? "—")}. A risk check, not advice to buy or sell.</p>
    <div class="card">
      <div class="verdict-big b-${esc((r.verdict ?? "").replace(/\s/g, ""))}">${r.verdict ? `Layer 1: ${esc(r.verdict)}` : "Not on today's risk lists"}</div>
      ${listRow?.why && !(r.flags ?? []).includes(listRow.why) ? `<p>${esc(listRow.why)}</p>` : ""}
      ${r.flags?.length ? `<h3>Red flags</h3><ul class="flags">${r.flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : `<p class="muted">No red flags computed for it today${r.verdict ? "" : " (only risk-list stocks are fully checked)"}.</p>`}
      ${listRow?.spark?.length ? `<h3>Last ${listRow.spark.length} sessions (indexed to 100)</h3>${spark(listRow.spark, 280, 70)}` : ""}
    </div>
    <div class="grid">
      <div class="card tile"><div class="n">${pct(r.r1)}</div><div class="l">on the day</div></div>
      <div class="card tile"><div class="n">${pct(r.r5)}</div><div class="l">over 5 sessions</div></div>
      <div class="card tile"><div class="n">${pct(r.r21)}</div><div class="l">over 21 sessions</div></div>
      <div class="card tile"><div class="n">${r.rv == null ? "n/a" : r.rv + "×"}</div><div class="l">volume vs its 30-session average</div></div>
    </div>
    <div class="card"><h2>History on this site</h2>
      <p>${lists.length ? `On today's top-100 list for: ${lists.join(", ")}. ` : ""}${r.scan_days ? `On the risk scan ${r.scan_days} of the last 20 sessions; first seen ${esc(r.first_seen)}.` : "Not on the risk scan in the last 20 sessions."}</p>
      ${hist.length ? `<div class="scroll"><table><thead><tr><th>Session</th><th>Layer 1</th><th class="num">5 sessions</th><th class="num">21 sessions</th></tr></thead><tbody>${hist.map((h) => `<tr><td>${esc(h.session)}</td><td>${badge(h.verdict)}</td><td class="num">${pct(h.r5)}</td><td class="num">${pct(h.r21)}</td></tr>`).join("")}</tbody></table></div>` : ""}
      ${eps.length ? `<h3>How earlier episodes ended</h3><ul>${eps.map((e) => `<li>Logged ${esc(e.first_logged)}: ${e.label === "collapsed" ? `<b>collapsed</b>, ${pct(-(e.drawdown ?? 0))} from its peak (${esc(e.peak_date)})` : e.label === "pending" ? "still pending (needs 30 sessions)" : "did not collapse 70%"}${e.vetoed ? (e.label === "collapsed" ? " — a VETO was logged before the peak" : e.label === "pending" ? " — VETO logged" : " — a VETO was logged (a false alarm by this definition)") : ""}</li>`).join("")}</ul>` : ""}
    </div>
    ${tickerStories(sym, await loadStories())}
    <div class="card"><h2>Share</h2><p class="small">Paste this link in your group chat:</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><input class="field" style="flex:1;min-width:0;padding:7px 10px;border:1px solid var(--border);border-radius:8px;background:var(--surface-0);color:var(--text-primary)" readonly value="${esc(share)}" id="share"><button id="copy">Copy</button></div></div>
    <div class="card"><h2>If someone is pushing ${esc(sym)} to you</h2><ul class="flags">${HELP.redFlags.slice(0, 4).map((f) => `<li>${esc(f)}</li>`).join("")}</ul><p><a href="#/help">All red flags and what to do →</a></p></div>`;
  $("#copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(share); $("#copy").textContent = "Copied"; } catch { $("#share").select(); }
  });
}

async function viewLookup() {
  main.innerHTML = `<h1>Look up a ticker</h1><p class="lead">Every US stock that closed at $30 or less on the last session.</p>
    <form class="card" id="lf" style="display:flex;gap:8px"><label class="sr" for="li">Ticker</label>
    <input id="li" class="field" style="flex:1;padding:9px 12px;border:1px solid var(--border);border-radius:8px;background:var(--surface-0);color:var(--text-primary);text-transform:uppercase" placeholder="Ticker" maxlength="10" autofocus>
    <button class="primary">Check</button></form>`;
  $("#lf").addEventListener("submit", (e) => { e.preventDefault(); go($("#li").value); });
}

async function viewAnalytics() {
  const d = await all();
  const rows = [...d.symbols.values()];
  if (!rows.length) return (main.innerHTML = noData("Analytics"));
  main.innerHTML = `
    <h1>Analytics</h1>
    <p class="lead">Filter all ${rows.length.toLocaleString()} US stocks that closed at $30 or less on ${esc(d.meta?.data_session)}.
      Layer 1 verdicts exist only for stocks on a risk list or the scan.</p>
    <form class="card filters" id="ff">
      <label class="field">Price band<select name="band"><option value="">any</option><option>under $1</option><option>$1-5</option><option>$5-30</option></select></label>
      <label class="field">Change over<select name="win"><option value="r1">1 session</option><option value="r5" selected>5 sessions</option><option value="r21">21 sessions</option></select></label>
      <label class="field">At least (%)<input name="min" type="number" value="20" step="5"></label>
      <label class="field">Volume × at least<input name="rv" type="number" value="0" step="0.5" min="0"></label>
      <label class="field">Layer 1<select name="verdict"><option value="">any</option><option>VETO</option><option>CAUTION</option><option>NO FLAGS</option><option value="none">not checked</option></select></label>
      <label class="field">Days on scan ≥<input name="scan" type="number" value="0" min="0" max="20"></label>
      <label class="field"><span><input type="checkbox" name="flags"> has red flags</span></label>
    </form>
    <p id="n" class="small"></p>
    <div class="card scroll"><table id="t"><thead><tr></tr></thead><tbody></tbody></table></div>
    <p class="small"><button id="dl">Download these rows (CSV)</button></p>`;
  const cols = [{ label: "Symbol", sort: (r) => r.s }, { label: "Band", sort: (r) => r.band },
    { label: "1 session", num: true, sort: (r) => r.r1 }, { label: "5 sessions", num: true, sort: (r) => r.r5 },
    { label: "21 sessions", num: true, sort: (r) => r.r21 }, { label: "Volume ×", num: true, sort: (r) => r.rv },
    { label: "Layer 1", sort: (r) => r.verdict ?? "~" }, { label: "Scan days", num: true, sort: (r) => r.scan_days }, { label: "Red flags" }];
  const render = (r) => `<tr><td>${symLink(r.s)}</td><td>${esc(r.band)}</td><td class="num">${pct(r.r1)}</td><td class="num">${pct(r.r5)}</td><td class="num">${pct(r.r21)}</td>
    <td class="num">${r.rv == null ? "n/a" : r.rv + "×"}</td><td>${badge(r.verdict)}</td><td class="num">${r.scan_days || ""}</td><td class="wrap-cell">${flagsCell(r.flags, r.why)}</td></tr>`;
  let current = [];
  const apply = () => {
    const f = new FormData($("#ff"));
    const min = (+f.get("min") || 0) / 100, win = f.get("win"), rv = +f.get("rv") || 0, v = f.get("verdict"), sc = +f.get("scan") || 0;
    current = rows.filter((r) => (!f.get("band") || r.band === f.get("band")) && (r[win] ?? -Infinity) >= min && (rv === 0 || (r.rv ?? 0) >= rv)
      && (!v || (v === "none" ? !r.verdict : r.verdict === v)) && (r.scan_days ?? 0) >= sc && (!f.get("flags") || r.flags?.length))
      .sort((a, b) => (b[win] ?? 0) - (a[win] ?? 0));
    $("#n").textContent = `N = ${current.length.toLocaleString()} of ${rows.length.toLocaleString()}${current.length > 500 ? " (showing the first 500)" : ""}`;
    sortable($("#t"), current.slice(0, 500), cols, render);
  };
  $("#ff").addEventListener("input", apply);
  $("#dl").addEventListener("click", () => {
    const head = ["symbol", "band", "chg_1", "chg_5", "chg_21", "volume_x", "verdict", "scan_days", "flags"];
    const q = (x) => `"${String(x ?? "").replace(/"/g, '""')}"`;
    const csv = [head.join(",")].concat(current.map((r) => [r.s, r.band, r.r1, r.r5, r.r21, r.rv, r.verdict, r.scan_days, (r.flags ?? []).join("; ")].map(q).join(","))).join("\n");
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: `red-flag-club-${d.meta?.data_session}.csv` });
    a.click();
    URL.revokeObjectURL(a.href);
  });
  apply();
}

async function viewTrack() {
  const d = await all();
  const o = d.outcomes;
  if (!o) return (main.innerHTML = noData("The track record"));
  const row = (name, m) => `<tr><td>${name}</td><td class="num">${m.episodes}</td><td class="num">${m.collapsed}</td><td class="num">${m.no_collapse}</td><td class="num">${m.pending}</td>
    <td class="num">${m.recall == null ? "n/a" : `${Math.round(m.recall * 100)}% (${m.veto_collapsed}/${m.collapsed})`}</td>
    <td class="num">${m.fp_rate == null ? "n/a" : `${Math.round(m.fp_rate * 100)}% (${m.veto_no_collapse}/${m.no_collapse})`}</td>
    <td class="small muted">${m.enough ? "enough to judge" : "too few to judge (needs 30+ each)"}</td></tr>`;
  main.innerHTML = `
    <h1>Track record</h1>
    <p class="lead">Every stock the risk scan logs is followed for 30 sessions. <b>Collapsed</b> means it rose 100%+ within 10
      sessions and then fell 70%+ within 20. This is how we check whether the tool is right — including when it isn't.</p>
    <div class="card scroll"><table><thead><tr><th></th><th class="num">Episodes</th><th class="num">Collapsed</th><th class="num">Didn't</th><th class="num">Pending</th>
      <th class="num">Caught (VETO by the peak)</th><th class="num">False alarms</th><th></th></tr></thead>
      <tbody>${row("Logged live", o.forward)}${row("Backfilled", o.backfilled)}</tbody></table>
      <p class="small muted">"Logged live" rows were written before the outcome existed and are the honest test. "Backfilled" rows were scanned later from history.
      ${esc(d.meta?.gate ?? "")}</p></div>
    <div class="card scroll"><h2>Recent episodes</h2><table id="t"><thead><tr></tr></thead><tbody></tbody></table></div>`;
  const cols = [{ label: "Symbol", sort: (r) => r.s }, { label: "First logged", sort: (r) => r.first_logged }, { label: "Outcome", sort: (r) => r.label },
    { label: "Fall from peak", num: true, sort: (r) => r.drawdown }, { label: "VETO in time", sort: (r) => r.vetoed }, { label: "Live", sort: (r) => !r.backfilled }];
  sortable($("#t"), o.episodes, cols, (r) => `<tr><td>${symLink(r.s)}</td><td>${esc(r.first_logged)}</td><td>${esc(r.label.replace("_", " "))}</td>
    <td class="num">${r.drawdown == null ? "—" : pct(-r.drawdown)}</td><td>${r.vetoed ? "yes" : "no"}</td><td>${r.backfilled ? "no" : "yes"}</td></tr>`);
}

async function viewAssistant() {
  const d = { ...(await all()), stories: await loadStories() };
  main.innerHTML = `
    <h1>Assistant</h1>
    <p class="lead">Answers come only from this site's data and help pages. It never gives buy advice, and nothing you type leaves your browser.</p>
    <div class="card chat">
      <div class="log" id="log" aria-live="polite"></div>
      <div class="chips">${[`Is $${d.movers?.lists?.week?.[0]?.s ?? "ABCD"} a pump?`, "What's pumping this week?", "Red flags", "I lost money", "How do I report it?", "Someone offers to recover my money", "Share my story", "Quiz me"].map((q) => `<button type="button">${esc(q)}</button>`).join("")}</div>
      <form id="cf"><label class="sr" for="ci">Your question</label><input id="ci" placeholder="Ask about a ticker or what to do…" autocomplete="off"><button class="primary">Ask</button></form>
    </div>`;
  const log = $("#log");
  const say = (who, text, links = []) => {
    const el = document.createElement("div");
    el.className = `msg ${who}`;
    el.textContent = text;
    if (links.length) {
      const l = document.createElement("div");
      l.className = "links";
      for (const k of links) {
        const a = Object.assign(document.createElement("a"), { href: k.href, textContent: k.label });
        if (/^https?:/.test(k.href)) Object.assign(a, { target: "_blank", rel: "noopener noreferrer" });
        l.append(a);
      }
      el.append(l);
    }
    log.append(el);
    log.scrollTop = log.scrollHeight;
  };
  const ask = (q) => { say("me", q); const a = answer(q, d); say("bot", a.text, a.links); };
  say("bot", answer("help", d).text);
  $(".chips").addEventListener("click", (e) => { if (e.target.tagName === "BUTTON") ask(e.target.textContent); });
  $("#cf").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#ci").value.trim(); if (q) { ask(q); $("#ci").value = ""; } });
}

async function viewHelp() {
  const m = await load("meta");
  const disc = m?.discussions_url;
  main.innerHTML = `
    <h1>Got pumped? What to do now</h1>
    <p class="lead">If you bought a stock that ran up and then collapsed, you are not alone — by mid-2025 the FBI had seen complaints about these
      schemes rise more than 300% over 2024. Here is what helps, in order.</p>
    <div class="card"><h2>1. Don't pay anyone to get it back</h2><p>${esc(HELP.recovery)}</p>
      <p class="small"><a href="${LINKS.recoveryAlert}" rel="noopener noreferrer" target="_blank">SEC investor alert on asset-recovery firms</a></p></div>
    <div class="card"><h2>2. Report it — it's free</h2><ul>${HELP.report.map(([n, u]) => `<li>${u ? `<a href="${u}" target="_blank" rel="noopener noreferrer">${esc(n)}</a>` : esc(n)}</li>`).join("")}</ul>
      <p class="small">Keep trade confirmations, screenshots of the chat or ads, the group's name and the phone numbers or accounts that contacted you.</p></div>
    <div class="card"><h2>3. Taxes</h2><p>${esc(HELP.tax)}</p><p class="small"><a href="${LINKS.irsLosses}" target="_blank" rel="noopener noreferrer">IRS Topic 409 — capital gains and losses</a></p></div>
    <div class="card"><h2>4. Warn others — safely</h2><p>${esc(HELP.story)}</p>
      ${disc ? `<p><a class="btn" href="${esc(disc)}" target="_blank" rel="noopener noreferrer">Community stories (GitHub Discussions)</a></p>` : `<p class="muted small">Community stories open when the site's discussion board is set up.</p>`}</div>
    <div class="card"><h2>Red flags of a pump in a group chat</h2><ul class="flags">${HELP.redFlags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>
      <p class="small"><a href="${LINKS.ic3Ramp}" target="_blank" rel="noopener noreferrer">FBI public service announcement on ramp-and-dump schemes (July 2025)</a></p></div>
    <div class="card"><h2>What is a pump-and-dump?</h2><p>${esc(HELP.what)}</p></div>`;
}

async function viewAbout() {
  const m = await load("meta");
  main.innerHTML = `
    <h1>About this site</h1>
    <div class="card"><h2>What it does</h2>
      <p>After each US market close it looks at every US stock and builds <b>risk lists</b>: the penny stocks (under $${m?.rules?.penny_max ?? 5})
      that rose most over a day, a week and a month, and a <b>risk scan</b> of stocks $1–$30 up 50% or more. Each gets a Layer 1 check:
      <b>VETO</b> (a pump-profile run-up, a frozen "ghost" quote, or 4+ of 6 structural red flags from FINRA Regulatory Notice 22-25),
      <b>CAUTION</b>, or <b>NO FLAGS</b>. Then it follows each scanned stock for 30 sessions to see what happened.</p>
      <p>${esc(m?.gate ?? "")}</p></div>
    <div class="card"><h2>Limits</h2><ul>
      <li>End-of-day data from free sources; it can be late or wrong. Float and market cap are unknown for most small caps and are treated as red flags, so it errs toward warning you.</li>
      <li>A listed stock has <b>not</b> been found to be a fraud. These are risk patterns, not accusations.</li>
      <li>${m?.prices ? "Prices are shown." : "Exact prices are not republished (data licences); you see percentages, price bands and shapes indexed to 100."}</li>
      <li>${esc(m?.retention ?? "")}.</li></ul></div>
    <div class="card"><h2>For community bots</h2><p>All data is static JSON and CSV, rebuilt after each refresh:</p>
      <ul><li><a href="data/meta.json">meta.json</a> — data date, counts, rules, base rates</li>
      <li><a href="data/movers.json">movers.json</a> — top 100 by day / week / month (<a href="data/movers_day.csv">CSV</a>, <a href="data/movers_week.csv">week</a>, <a href="data/movers_month.csv">month</a>)</li>
      <li><a href="data/symbols.json">symbols.json</a> — every small cap: changes, volume ratio, verdict, flags (<a href="data/symbols.csv">CSV</a>)</li>
      <li><a href="data/scan.json">scan.json</a> — the last 20 scanned sessions</li><li><a href="data/outcomes.json">outcomes.json</a> — the track record</li></ul>
      <p class="small">Percentages are fractions (0.5 = +50%). Please link back and keep the "not investment advice" note.</p></div>
    <div class="card"><h2>Independence</h2><p>Red Flag Club is independent and community-run. It is not affiliated with, endorsed by or sponsored by any brokerage (including Robinhood), data provider or company named on this site, and it is paid by no one. Company and product names belong to their owners and are used only to describe them.</p></div>
    <div class="card"><h2>Privacy</h2><p>No cookies, no tracking, no accounts. The assistant runs in your browser.</p></div>
    <p class="small muted">Built ${esc(m?.built_at ?? "")} · version ${esc(m?.version ?? "")}</p>`;
}

// ---------------------------------------------------------------- router
function go(sym) {
  const s = String(sym || "").trim().replace(/^\$/, "").toUpperCase();
  if (SYM.test(s)) location.hash = `#/t/${encodeURIComponent(s)}`;
}

const routes = [
  [/^#?\/?$/, () => viewToday(), "#/"],
  [/^#\/top\/(day|week|month)$/, (m) => viewTop(m[1]), "#/top/day"],
  [/^#\/scan$/, () => viewScan(), "#/scan"],
  [/^#\/t\/([A-Za-z0-9.\-]{1,10})$/, (m) => viewTicker(decodeURIComponent(m[1]).toUpperCase()), "#/lookup"],
  [/^#\/lookup$/, () => viewLookup(), "#/lookup"],
  [/^#\/analytics$/, () => viewAnalytics(), "#/analytics"],
  [/^#\/track$/, () => viewTrack(), "#/track"],
  [/^#\/assistant$/, () => viewAssistant(), "#/assistant"],
  [/^#\/help$/, () => viewHelp(), "#/help"],
  [/^#\/about$/, () => viewAbout(), "#/about"],
  [/^#\/stories$/, (m, q) => viewStories(main, q), "#/stories"],
  [/^#\/s\/([A-Za-z0-9\-]{1,40})$/, async (m) => viewStory(main, m[1], await symbols()), "#/stories"],
  [/^#\/stocks$/, async () => viewStocks(main, await symbols()), "#/stories"],
  [/^#\/share$/, async () => viewShare(main, await load("meta"), (await loadStories()).vocab), "#/share"],
  [/^#\/quiz$/, () => viewQuiz(main), "#/quiz"],
];

async function route() {
  const full = location.hash || "#/";
  const [h, qs] = full.split("?");
  const query = new URLSearchParams(qs || "");
  const hit = routes.find(([re]) => re.test(h)) ?? routes[0];
  document.querySelectorAll(".menu a").forEach((a) => a.toggleAttribute("aria-current", a.getAttribute("href") === hit[2] || (hit[2] === "#/top/day" && a.getAttribute("href") === "#/top/day")));
  document.querySelectorAll('.menu a[aria-current]').forEach((a) => a.setAttribute("aria-current", "page"));
  try {
    await hit[1](h.match(hit[0]), query);
  } catch (e) {
    main.innerHTML = `<div class="card"><h2>Something went wrong</h2><p class="muted">${esc(e.message)}</p></div>`;
  }
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

document.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => navigator.clipboard?.writeText(location.href)));
$("#quick").addEventListener("submit", (e) => { e.preventDefault(); go($("#quick-in").value); $("#quick-in").value = ""; });
window.addEventListener("hashchange", route);
load("meta").then((m) => {
  if (m) $("#foot-data").textContent = `Data from the close of ${m.data_session ?? "—"} · built ${m.built_at}`;
});
route();
