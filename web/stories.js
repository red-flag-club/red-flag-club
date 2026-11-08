// Community stories (spec 007): read, browse by tag or stock, and share by voice or text.
// Stories are published only after the owner anonymises and approves them.

const esc = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (sel, el = document) => el.querySelector(sel);
const TURNSTILE = "https://challenges.cloudflare.com/turnstile/v0/api.js";

export const LABELS = {
  "whatsapp": "WhatsApp", "telegram": "Telegram", "discord": "Discord", "facebook": "Facebook", "instagram": "Instagram",
  "x-twitter": "X / Twitter", "tiktok": "TikTok", "youtube": "YouTube", "reddit": "Reddit", "stocktwits": "Stocktwits",
  "text-message": "Text message", "phone-call": "Phone call", "email": "Email", "dating-app": "Dating app",
  "friend-or-family": "Friend or family", "other": "Other",
  "investment-club": "\"Investment club\"", "fake-adviser": "Fake adviser", "teacher-or-professor": "\"Teacher\" / \"professor\"",
  "insider-tip": "\"Insider\" tip", "urgency": "Pressure to act now", "screenshots-of-gains": "Screenshots of gains",
  "fake-news": "Fake news or hype", "ipo-allocation": "Fake IPO allocation", "vip-group": "VIP group",
  "small-new-listing": "Small, new listing", "foreign-issuer": "Foreign issuer", "move-to-private-chat": "Moved to private chat",
  "buy-signal-time": "Told exactly when to buy",
  "sold-at-loss": "Sold at a loss", "still-holding": "Still holding", "account-restricted": "Account restricted",
  "recovery-scam-attempt": "Targeted by a recovery scam", "reported-to-regulator": "Reported it", "broker-helped": "Broker helped",
  "under-1k": "under $1k", "1k-10k": "$1k–10k", "10k-50k": "$10k–50k", "50k-plus": "$50k+", "prefer-not-to-say": "not said",
};
const label = (t) => LABELS[t] ?? t;

// What each tactic teaches — shown under a story so every read ends with a lesson.
export const LESSONS = {
  "investment-club": "Free \"investment clubs\" that find you through ads or random messages are the most common start of a ramp-and-dump.",
  "fake-adviser": "Real advisers are registered: check the name on FINRA BrokerCheck or the SEC's adviser search before trusting a pick.",
  "teacher-or-professor": "A \"teacher\" giving free picks in a group chat is the classic role in these schemes; their profit comes from your buying.",
  "insider-tip": "If it were truly inside information, trading on it would be illegal; it is almost always bait.",
  "urgency": "Pressure to buy before a deadline is designed to stop you checking. Real opportunities survive a day of research.",
  "screenshots-of-gains": "Screenshots of other members' gains are easy to fake — and in these groups many members are bots or accomplices.",
  "fake-news": "A sudden \"big announcement\" story from an unknown site is a common accelerant. Check the company's own SEC filings.",
  "ipo-allocation": "No one can sell you a guaranteed IPO allocation through a chat app.",
  "vip-group": "Being moved to a \"VIP\" group usually means you are being prepared to buy the dump.",
  "small-new-listing": "Tiny, recently listed companies with few tradable shares are the easiest to push up — and to crash.",
  "foreign-issuer": "Foreign issuers file less often with the SEC; long gaps without filings during a run-up are a warning sign.",
  "move-to-private-chat": "Being moved from a public platform to WhatsApp or Telegram takes you away from moderation and records.",
  "buy-signal-time": "You were told exactly when to buy but never when to sell — because the sellers were the people giving the signal.",
  "recovery-scam-attempt": "Anyone offering to recover your money for a fee is running a second scam. Reporting to regulators is free.",
};

let cache = null;
export async function loadStories() {
  if (!cache) {
    cache = fetch("data/stories.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)
      .then((d) => d ?? { stories: [], stocks: [], tags: { tactics: {}, channel: {} }, count: 0, vocab: {} });
  }
  return cache;
}

export function storiesFor(data, sym) {
  return data.stories.filter((s) => (s.stocks ?? []).includes(sym));
}

export function related(data, story, n = 3) {
  const score = (o) => (o.stocks ?? []).filter((x) => story.stocks?.includes(x)).length * 3 +
    (o.tactics ?? []).filter((x) => story.tactics?.includes(x)).length + (o.channel === story.channel ? 1 : 0);
  return data.stories.filter((o) => o.id !== story.id).map((o) => [score(o), o]).filter(([s]) => s > 0)
    .sort((a, b) => b[0] - a[0]).slice(0, n).map(([, o]) => o);
}

export function filterStories(stories, { tag, stock, channel, q } = {}) {
  const needle = (q ?? "").trim().toLowerCase();
  return stories.filter((s) => (!tag || (s.tactics ?? []).includes(tag) || (s.outcome ?? []).includes(tag))
    && (!stock || (s.stocks ?? []).includes(stock)) && (!channel || s.channel === channel)
    && (!needle || `${s.title} ${s.summary} ${s.body} ${(s.stocks ?? []).join(" ")}`.toLowerCase().includes(needle)));
}

const monthName = (m) => {
  if (!m) return "";
  const [y, mo] = m.split("-").map(Number);
  return new Date(Date.UTC(y, mo - 1, 1)).toLocaleString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
};
const period = (s) => (s.month_from && s.month_to && s.month_from !== s.month_to ? `${monthName(s.month_from)} – ${monthName(s.month_to)}` : monthName(s.month_from || s.month_to));
const chips = (tags, base = "#/stories?tag=") => (tags ?? []).map((t) => `<a class="chip" href="${base}${encodeURIComponent(t)}">${esc(label(t))}</a>`).join("");

function card(s) {
  return `<article class="card story-card">
    <a class="story-link" href="#/s/${encodeURIComponent(s.id)}"><h3>${esc(s.title)}</h3></a>
    <p class="small muted">${(s.stocks ?? []).map((x) => `<b>${esc(x)}</b>`).join(", ")} · ${esc(period(s))} · ${esc(label(s.channel))} · ${s.read_minutes ?? 1} min read${s.featured ? " · <b>featured</b>" : ""}</p>
    <p>${esc(s.summary)}</p><div class="chips">${chips(s.tactics)}</div></article>`;
}

function bars(counts, max = 8) {
  const rows = Object.entries(counts ?? {}).sort((a, b) => b[1] - a[1]).slice(0, max);
  if (!rows.length) return "";
  const top = rows[0][1];
  return `<div class="hbars" role="list">${rows.map(([t, n]) => `<a role="listitem" class="hbar" href="#/stories?tag=${encodeURIComponent(t)}" title="${esc(label(t))}: ${n} ${n === 1 ? "story" : "stories"}">
    <span class="hbar-label">${esc(label(t))}</span><span class="hbar-track"><span class="hbar-fill" style="width:${Math.max(4, (n / top) * 100)}%"></span></span><span class="hbar-n">${n}</span></a>`).join("")}</div>`;
}

export async function viewStories(main, params) {
  const data = await loadStories();
  const f = { tag: params.get("tag") || "", stock: params.get("stock") || "", channel: params.get("channel") || "", q: params.get("q") || "" };
  const stocks = data.stocks.map((e) => e.s);
  const channels = Object.keys(data.tags?.channel ?? {});
  main.innerHTML = `
    <h1>Real stories</h1>
    <p class="lead">True stories from people who were pushed into a pump-and-dump, shared so the next person recognises it sooner.
      Names and personal details are removed before anything is published; the story itself is not changed.</p>
    <div class="grid">
      <div class="card tile"><div class="n">${data.count}</div><div class="l">stories shared</div></div>
      <a class="card tile plain" href="#/stocks"><div class="n">${data.stocks.length}</div><div class="l">stocks named in them →</div></a>
      <a class="card tile plain" href="#/share"><div class="n">＋</div><div class="l">share yours — speak or type</div></a>
      <a class="card tile plain" href="#/quiz"><div class="n">10</div><div class="l">questions: can you spot the red flags? →</div></a>
    </div>
    ${data.count ? `<section class="card"><h2>How people were drawn in</h2>${bars(data.tags.tactics)}<p class="small muted">Tap a bar to read those stories. N = ${data.count} stories.</p></section>` : ""}
    <form class="card filters" id="sf" role="search">
      <label class="field">Search<input name="q" value="${esc(f.q)}" placeholder="words, ticker…"></label>
      <label class="field">Stock<select name="stock"><option value="">any</option>${stocks.map((s) => `<option ${s === f.stock ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></label>
      <label class="field">Where it started<select name="channel"><option value="">any</option>${channels.map((c) => `<option value="${esc(c)}" ${c === f.channel ? "selected" : ""}>${esc(label(c))}</option>`).join("")}</select></label>
      <label class="field">Tactic<select name="tag"><option value="">any</option>${Object.keys(data.tags?.tactics ?? {}).map((t) => `<option value="${esc(t)}" ${t === f.tag ? "selected" : ""}>${esc(label(t))}</option>`).join("")}</select></label>
    </form>
    <p class="small" id="sn"></p>
    <div id="list" class="story-list"></div>`;
  const draw = () => {
    const fd = Object.fromEntries(new FormData($("#sf")));
    const list = filterStories(data.stories, fd);
    $("#sn").textContent = data.count ? `${list.length} of ${data.count} stories` : "";
    $("#list").innerHTML = list.map(card).join("") || (data.count
      ? `<div class="card muted">No stories match. Try clearing a filter.</div>`
      : `<div class="card"><h2>Be the first</h2><p>No stories are published yet. If this happened to you, <a href="#/share">share it</a> — by voice or text. It is read and anonymised before anything appears here.</p></div>`);
  };
  $("#sf").addEventListener("input", draw);
  draw();
}

export async function viewStory(main, id, symbols) {
  const data = await loadStories();
  const s = data.stories.find((x) => x.id === id);
  if (!s) {
    main.innerHTML = `<div class="card"><h1>Story not found</h1><p><a href="#/stories">All stories →</a></p></div>`;
    return;
  }
  const lessons = (s.tactics ?? []).concat(s.outcome ?? []).map((t) => LESSONS[t]).filter(Boolean);
  const next = related(data, s);
  const share = `${location.origin}${location.pathname}#/s/${encodeURIComponent(s.id)}`;
  const checks = (s.stocks ?? []).map((x) => {
    const r = symbols?.get(x);
    return `<a class="btn" href="#/t/${encodeURIComponent(x)}">${esc(x)} today${r?.verdict ? `: ${esc(r.verdict)}` : ""} →</a>`;
  }).join(" ");
  main.innerHTML = `
    <article class="story">
      <p class="small"><a href="#/stories">← All stories</a></p>
      <h1>${esc(s.title)}</h1>
      <p class="small muted">${(s.stocks ?? []).map((x) => `<a href="#/stories?stock=${encodeURIComponent(x)}"><b>${esc(x)}</b></a>`).join(", ")} ·
        ${esc(period(s))} · started on ${esc(label(s.channel))} · loss ${esc(label(s.loss_range))} · ${s.read_minutes ?? 1} min read · shared ${esc(s.submitted)}</p>
      <div class="card story-body">${String(s.body).split(/\n{2,}/).map((p) => `<p>${esc(p)}</p>`).join("")}</div>
      <div class="chips">${chips(s.tactics)}${chips(s.outcome)}</div>
    </article>
    ${lessons.length ? `<section class="card"><h2>What to take from this</h2><ul class="flags">${lessons.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></section>` : ""}
    <section class="card"><h2>Check the stock today</h2><p>${checks}</p></section>
    ${next.length ? `<section><h2>Read next</h2><div class="story-list">${next.map(card).join("")}</div></section>` : ""}
    <section class="card"><h2>Has this happened to you?</h2><p>Your story could stop the next person. <a class="btn primary-link" href="#/share">Share it — speak or type</a></p>
      <p class="small">Share this story: <input class="share-in" readonly value="${esc(share)}" aria-label="Link to this story"> <button type="button" id="cp">Copy link</button></p></section>
    <p class="small muted">Shared by a member of the community and anonymised before publishing. It is one person's account, not a finding about any company.</p>`;
  $("#cp").addEventListener("click", async () => { try { await navigator.clipboard.writeText(share); $("#cp").textContent = "Copied"; } catch { /* select fallback */ } });
}

export async function viewStocks(main, symbols) {
  const data = await loadStories();
  main.innerHTML = `
    <h1>Stocks in the stories</h1>
    <p class="lead">How many people shared a story naming each stock, and when. These are self-reported accounts, not verified
      counts of victims and not findings about the companies.</p>
    <div class="card scroll"><table><thead><tr><th>Stock</th><th class="num">People who shared</th><th>First</th><th>Latest</th><th>Today's check</th><th></th></tr></thead>
    <tbody>${data.stocks.map((e) => {
      const r = symbols?.get(e.s);
      return `<tr><td><a class="sym" href="#/t/${encodeURIComponent(e.s)}">${esc(e.s)}</a></td><td class="num">${e.people}</td><td>${esc(monthName(e.first_month))}</td><td>${esc(monthName(e.last_month))}</td>
        <td>${r?.verdict ? esc(r.verdict) : `<span class="muted small">not on today's lists</span>`}</td><td><a href="#/stories?stock=${encodeURIComponent(e.s)}">Read ${e.people === 1 ? "the story" : "the stories"} →</a></td></tr>`;
    }).join("") || `<tr><td colspan="6" class="muted">No stories published yet.</td></tr>`}</tbody></table></div>`;
}

// ---------------------------------------------------------------- share
export function speechSupported(w = globalThis) {
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export function buildSubmission(fd) {
  const stocks = String(fd.get("stocks") || "").split(/[\s,;]+/).map((s) => s.replace(/^\$/, "").toUpperCase()).filter(Boolean).slice(0, 5);
  const out = { text: String(fd.get("text") || "").trim(), stocks, consent: fd.get("consent") === "on", website: String(fd.get("website") || "") };
  for (const k of ["channel", "loss_range", "month_from", "month_to", "language"]) if (fd.get(k)) out[k] = String(fd.get(k));
  if (fd.get("voice") === "1") out.voice = true;
  return out;
}

export async function viewShare(main, meta, vocab) {
  const url = meta?.stories_submit_url;
  const sitekey = meta?.turnstile_sitekey;
  const opts = (k) => (vocab?.[k] ?? []).map((v) => `<option value="${esc(v)}">${esc(label(v))}</option>`).join("");
  main.innerHTML = `
    <h1>Share your story</h1>
    <p class="lead">Tell it the way it happened — speak or type. Before anything is published, your name and personal details are removed
      and the story is read by a person. Your words and the sequence of events stay as you told them.</p>
    <div class="card note"><b>Please don't include</b> account numbers, passwords, your address or phone number, or anyone's full name.
      We remove anything that slips through, but it's safest never to send it.</div>
    <form class="card share" id="share" novalidate>
      <div class="field"><span>Your story</span>
        <div class="mic-row">${speechSupported(window) ? `<button type="button" id="mic" class="mic" aria-pressed="false">🎙 Start speaking</button>
          <label class="small">Language <select id="lang" name="language">
            <option value="en-US">English (US)</option><option value="en-GB">English (UK)</option><option value="en-IN">English (India)</option>
            <option value="hi-IN">हिन्दी</option><option value="es-US">Español</option><option value="zh-CN">中文</option>
            <option value="vi-VN">Tiếng Việt</option><option value="ko-KR">한국어</option></select></label>` : `<span class="small muted">Voice typing isn't available in this browser — try Chrome, Edge or Safari, or type below.</span>`}</div>
        <p class="small muted" id="mic-note">${speechSupported(window) ? "Voice is turned into text by your browser's speech service (in Chrome that is Google). No recording is stored or sent to us — only the text you submit." : ""}</p>
        <textarea name="text" id="text" rows="12" minlength="50" maxlength="20000" required placeholder="How were you first contacted? What were you told? What happened to the price, and to you?"></textarea>
        <span class="small muted" id="count">0 / 20,000</span></div>
      <div class="filters">
        <label class="field">Stock ticker(s)<input name="stocks" placeholder="e.g. RYDE, ABCD" autocapitalize="characters"></label>
        <label class="field">Where did it start?<select name="channel"><option value="">choose…</option>${opts("channel")}</select></label>
        <label class="field">From (month)<input type="month" name="month_from"></label>
        <label class="field">To (month)<input type="month" name="month_to"></label>
        <label class="field">Roughly how much was lost?<select name="loss_range"><option value="">choose…</option>${opts("loss_range")}</select></label>
      </div>
      <input type="hidden" name="voice" id="voice" value="0">
      <label class="hp" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label>
      <label class="consent"><input type="checkbox" name="consent" required> I agree that this story may be published here after names and personal details are removed. It is true to the best of my knowledge.</label>
      ${sitekey ? `<div class="cf-turnstile" data-sitekey="${esc(sitekey)}"></div>` : ""}
      <div class="actions"><button class="primary" type="submit" ${url ? "" : "disabled"}>Send my story</button>
        <button type="button" id="save">Save a copy for myself</button></div>
      <p id="status" role="status" class="small"></p>
      ${url ? "" : `<p class="small muted">Story sharing isn't switched on yet on this site. You can still write it here and save a copy.</p>`}
    </form>
    <p class="small muted">Already lost money? See <a href="#/help">what to do now</a> — and never pay anyone who offers to get it back.</p>`;
  const text = $("#text");
  const count = () => ($("#count").textContent = `${text.value.length.toLocaleString()} / 20,000`);
  text.addEventListener("input", count);
  if (sitekey && !document.querySelector(`script[src^="${TURNSTILE}"]`)) {
    const s = Object.assign(document.createElement("script"), { src: TURNSTILE, async: true, defer: true });
    document.head.append(s);
  }
  // voice → text
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Rec) {
    let rec = null;
    const mic = $("#mic");
    const stop = () => { rec?.stop(); rec = null; mic.textContent = "🎙 Start speaking"; mic.setAttribute("aria-pressed", "false"); };
    mic.addEventListener("click", () => {
      if (rec) return stop();
      rec = new Rec();
      rec.lang = $("#lang").value;
      rec.continuous = true;
      rec.interimResults = true;
      const base = text.value ? text.value.replace(/\s*$/, " ") : "";
      let finalText = "";
      rec.onresult = (e) => {
        let interim = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const t = e.results[i][0].transcript;
          if (e.results[i].isFinal) finalText += t.trim() + " ";
          else interim += t;
        }
        text.value = (base + finalText + interim).slice(0, 20000);
        count();
      };
      rec.onerror = (e) => { $("#status").textContent = e.error === "not-allowed" ? "Microphone permission was refused — you can type instead." : `Voice stopped (${e.error}).`; stop(); };
      rec.onend = () => { if (rec) stop(); };
      rec.start();
      $("#voice").value = "1";
      mic.textContent = "■ Stop";
      mic.setAttribute("aria-pressed", "true");
    });
  }
  $("#save").addEventListener("click", () => {
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([text.value], { type: "text/plain" })), download: "my-story.txt" });
    a.click();
    URL.revokeObjectURL(a.href);
  });
  $("#share").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = buildSubmission(fd);
    const st = $("#status");
    if (body.text.length < 50) return (st.textContent = "Please write (or say) at least a few sentences.");
    if (!body.consent) return (st.textContent = "Please tick the box to agree to publication after anonymisation.");
    const token = document.querySelector('[name="cf-turnstile-response"]')?.value;
    if (token) body.turnstile = token;
    st.textContent = "Sending…";
    try {
      const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || `error ${r.status}`);
      main.innerHTML = `<div class="card"><h1>Thank you</h1><p>Your story arrived safely (reference <b>${esc(j.id)}</b>). It is encrypted until it is read.
        A person will remove names and personal details and publish it — usually within a few days. Nothing is published before that.</p>
        <p><a href="#/stories">Read other stories →</a> · <a href="#/quiz">Take the red-flag quiz →</a></p></div>`;
    } catch (err) {
      st.textContent = `Couldn't send right now (${err.message}). Your text is still here — try again, or save a copy.`;
    }
  });
}
