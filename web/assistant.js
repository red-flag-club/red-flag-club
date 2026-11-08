// pd-defence assistant (spec 006): deterministic, offline, no API key.
// It answers only from the site's own data and help text, never invents a
// verdict, and never recommends buying.

export const LINKS = {
  secTips: "https://www.sec.gov/tcr",
  ic3: "https://www.ic3.gov",
  ic3Ramp: "https://www.ic3.gov/PSA/2025/PSA250703",
  finraComplaint: "https://www.finra.org/investors/have-problem/file-complaint",
  recoveryAlert: "https://www.investor.gov/additional-resources/news-alerts/alerts-bulletins/investor-alert-what-you-should-know-about-asset",
  irsLosses: "https://www.irs.gov/taxtopics/tc409",
};

export const HELP = {
  what: "A pump-and-dump (a \"ramp-and-dump\" when it runs over weeks) is when people who control a lot of a " +
    "low-priced stock push its price up — through group chats, ads, fake \"advisers\" or social media — then sell " +
    "into the buying they created. The price usually collapses and the late buyers are left with the loss.",
  redFlags: [
    "An unsolicited message or ad invites you to an \"investment club\" on WhatsApp, Telegram or similar.",
    "A \"teacher\", \"professor\" or famous analyst gives exclusive picks — real advisers don't do this in group chats.",
    "Urgency: buy now, before \"the news\" or \"the institutions\" — and screenshots of other members' gains.",
    "A low-priced stock of a new or obscure company, often recently listed or foreign, with little trading before.",
    "The price has already run up a lot in days, on volume many times its normal.",
    "You are told when to buy but never when to sell.",
    "The company has filed little or nothing with the SEC recently.",
  ],
  report: [
    ["SEC tips, complaints and referrals", "https://www.sec.gov/tcr"],
    ["FBI Internet Crime Complaint Center (IC3)", "https://www.ic3.gov"],
    ["FINRA investor complaint", "https://www.finra.org/investors/have-problem/file-complaint"],
    ["Your broker's fraud or compliance team", null],
  ],
  recovery: "Be very careful of anyone who contacts you offering to get your money back — \"asset recovery\" " +
    "firms, lawyers you didn't contact, or people claiming to be regulators. People who already lost money are " +
    "targeted again, and they ask for a fee up front. Filing a complaint with the SEC, FINRA or IC3 is free and " +
    "you can do it yourself. Regulators never ask you for money to recover losses.",
  tax: "A loss on a stock you sold is a capital loss. In the US it can offset capital gains and up to $3,000 a " +
    "year of other income, with the rest carried forward (IRS Topic 409). Ask a tax professional about your case.",
  story: "You can share what happened in the community stories section. Never post account numbers, order " +
    "screenshots with personal details, or anyone's private information.",
};

const STOP = new Set(("I A AN AND ARE AS AT BE BUT BY CAN DO FOR FROM HOW IF IN IS IT ITS ME MY NO NOT OF ON OR " +
  "OUT SO THE THIS TO UP US WAS WE WHAT WHEN WHO WHY WILL WITH YOU YOUR OK HI HEY SEC FBI IC3 FINRA IRS USA US " +
  "ETF IPO CEO VETO DAY WEEK TODAY TOP BUY SELL LOST HELP PUMP DUMP SCAM RISK").split(" "));

export function findTicker(text, known = null) {
  const dollar = text.match(/\$([A-Za-z][A-Za-z0-9.\-]{0,9})\b/);
  if (dollar) return dollar[1].toUpperCase();
  const after = text.match(/\b(?:check|about|on|ticker|symbol|is|for|bought|own|holding|hold|in|lookup|look up)\s+([A-Za-z][A-Za-z0-9.\-]{0,5})\b/i);
  if (after && !STOP.has(after[1].toUpperCase())) {
    const t = after[1].toUpperCase();
    if (!known || known.has(t) || after[1] === after[1].toUpperCase()) return t;
  }
  for (const w of text.split(/[^A-Za-z0-9.\-$]+/)) {
    if (/^[A-Z][A-Z0-9]{1,4}$/.test(w) && !STOP.has(w)) return w;
  }
  return null;
}

const has = (t, ...words) => words.some((w) => t.includes(w));
const pct = (x) => (x == null ? "n/a" : `${x >= 0 ? "+" : ""}${Math.round(x * 100)}%`);

function tickerAnswer(sym, data) {
  const r = data.symbols?.get(sym);
  const link = { label: `Open ${sym}`, href: `#/t/${sym}` };
  if (!r) {
    return {
      text: `${sym} is not in today's small-cap set (US stocks closing at $30 or less on ${data.meta?.data_session ?? "the last session"}). ` +
        "It may be larger, not US-listed, delisted, or the ticker may be mistyped. Check the red flags by hand before acting.",
      links: [{ label: "Red flags", href: "#/help" }],
    };
  }
  const parts = [`${sym} (${r.band}): ${pct(r.r1)} on the day, ${pct(r.r5)} over 5 sessions, ${pct(r.r21)} over 21.`];
  if (r.rv != null) parts.push(`Volume was ${r.rv}× its 30-session average.`);
  if (r.verdict) parts.push(`Layer 1 check: ${r.verdict}.`);
  else parts.push("It is not on today's risk lists, so no Layer 1 check was run for it today.");
  if (r.flags?.length) parts.push(`Red flags: ${r.flags.slice(0, 3).join("; ")}.`);
  if (r.scan_days) parts.push(`On the risk scan ${r.scan_days} of the last 20 sessions (first seen ${r.first_seen}).`);
  parts.push("This is a risk check, not advice to buy or sell.");
  return { text: parts.join(" "), links: [link] };
}

function listAnswer(window, data) {
  const rows = data.movers?.lists?.[window] ?? [];
  if (!rows.length) return { text: "No risk list is available yet.", links: [] };
  const veto = rows.filter((r) => r.verdict === "VETO").length;
  const top = rows.slice(0, 5).map((r) => `${r.s} ${pct(r.chg)}${r.verdict ? ` (${r.verdict})` : ""}`).join(", ");
  return {
    text: `Biggest ${window} run-ups among penny stocks (${rows.length} listed, ${veto} with a Layer 1 VETO): ${top}. ` +
      "These are the riskiest, not recommendations — most runs like these do not end well for late buyers.",
    links: [{ label: `Top 100 — ${window}`, href: `#/top/${window}` }],
  };
}

export function answer(input, data = {}) {
  const raw = (input || "").trim();
  const t = raw.toLowerCase();
  if (!raw) return { text: "Ask me about a ticker (e.g. \"is $ABC a pump?\"), this week's run-ups, or what to do if you lost money.", links: [] };
  const sym = findTicker(raw, data.symbols ? new Set(data.symbols.keys()) : null);
  const br = data.meta?.base_rates?.bracket;

  if (has(t, "share my story", "tell my story", "my story", "record my story", "share what happened")) {
    return { text: "Thank you — your story can stop the next person. You can speak or type it; names and personal details are removed before anything is published, and a person reads it first.",
             links: [{ label: "Share your story", href: "#/share" }, { label: "Read others' stories", href: "#/stories" }] };
  }
  if (has(t, "stories", "story", "other people", "anyone else")) {
    const n = data.stories?.count;
    return { text: n ? `${n} people have shared what happened to them. You can browse by stock or by how they were drawn in.` : "Stories from the community will appear here once they are shared and anonymised.",
             links: [{ label: "Read stories", href: sym ? `#/stories?stock=${sym}` : "#/stories" }, { label: "Share yours", href: "#/share" }] };
  }
  if (has(t, "quiz", "test myself", "test me")) return { text: "Ten real-world situations — can you spot the red flags? Takes about two minutes.", links: [{ label: "Take the quiz", href: "#/quiz" }] };
  if (has(t, "recover", "get my money back", "refund", "recovery")) {
    return { text: HELP.recovery, links: [{ label: "SEC alert on recovery firms", href: LINKS.recoveryAlert }, { label: "Got pumped? guide", href: "#/help" }] };
  }
  if (has(t, "report", "complain", "complaint", "tip", "regulator")) {
    return { text: "You can report it yourself, for free: " + HELP.report.map(([n]) => n).join("; ") + ". Keep your trade confirmations, the chat messages and the names or numbers that contacted you.",
             links: HELP.report.filter(([, u]) => u).map(([n, u]) => ({ label: n, href: u })) };
  }
  if (has(t, "tax")) return { text: HELP.tax, links: [{ label: "IRS Topic 409", href: LINKS.irsLosses }] };
  if (has(t, "should i buy", "buy it", "worth buying", "invest in", "good buy", "should i invest", "price target", "will it go up")) {
    return {
      text: "I can't tell you to buy anything, and this site never does. " + (sym ? "Here is what the risk check shows. " : "") +
        (br ? `For context: in this project's backtest of ${br.n.toLocaleString()} trades buying after a pump trigger, ${Math.round(br.win * 1000) / 10}% reached +20% before −10%, below the ${br.breakeven * 100}% needed to break even.` : ""),
      links: sym ? [{ label: `Open ${sym}`, href: `#/t/${sym}` }] : [{ label: "Red flags", href: "#/help" }],
    };
  }
  if (has(t, "lost", "lose", "loss", "bag", "down ", "crashed", "collapsed", "scammed", "got pumped", "was i pumped")) {
    const base = { text: "I'm sorry — this happens to many careful people. Three things now: (1) don't pay anyone who offers to recover it; (2) report it, free, to the SEC, FINRA and the FBI's IC3; (3) keep records for taxes. ", links: [{ label: "Got pumped? guide", href: "#/help" }] };
    if (sym) {
      const a = tickerAnswer(sym, data);
      return { text: base.text + a.text, links: [...a.links, ...base.links] };
    }
    return base;
  }
  if (has(t, "red flag", "warning sign", "spot", "how do i know", "how to tell", "signs")) {
    return { text: "Common signs: " + HELP.redFlags.join(" "), links: [{ label: "Full checklist", href: "#/help" }] };
  }
  if (has(t, "what is", "what's a", "explain", "meaning") && has(t, "pump", "ramp", "dump")) {
    return { text: HELP.what, links: [{ label: "FBI warning (2025)", href: LINKS.ic3Ramp }] };
  }
  if (sym && !has(t, "today", "this week", "this month")) return tickerAnswer(sym, data);
  if (has(t, "month")) return listAnswer("month", data);
  if (has(t, "week")) return listAnswer("week", data);
  if (has(t, "today", "top", "movers", "pumping", "gainers", "running", "hot")) return listAnswer("day", data);
  if (has(t, "scan", "veto", "flagged")) {
    const s = data.scan?.sessions?.[0];
    const n = s?.hits?.length ?? 0;
    return { text: s ? `The last risk scan (${s.session}) found ${n} small caps up 50% or more over 5 or 21 sessions; ${s.hits.filter((h) => h.verdict === "VETO").length} got a VETO.` : "The risk scan has not run yet.",
             links: [{ label: "Risk scan", href: "#/scan" }] };
  }
  if (has(t, "hello", "hi", "hey", "help", "what can you")) {
    return { text: "I can: check a ticker (\"is $ABC a pump?\"), list this day's/week's/month's biggest penny-stock run-ups, explain red flags, and tell you what to do if you lost money. I only use this site's data and never give buy advice.", links: [] };
  }
  return {
    text: "I didn't understand that. Try: \"is $ABC a pump?\", \"what's pumping this week?\", \"red flags\", \"I lost money on ABC\", or \"how do I report it?\"",
    links: [],
  };
}
