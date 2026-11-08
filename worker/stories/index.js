// Red Flag Club — story intake (specs/007-community-stories).
// A Cloudflare Worker: validates a submission, encrypts it with the owner's
// public key (RSA-OAEP-256 + AES-256-GCM) and writes the ciphertext to a
// private inbox repository. It stores no IP address, user agent or time of day.
//
// Env: STORIES_PUBLIC_KEY (base64 SPKI), GITHUB_TOKEN (fine-grained, contents
// read/write on the inbox repo only), INBOX_REPO ("owner/repo"),
// ALLOWED_ORIGIN ("https://<you>.github.io"), TURNSTILE_SECRET (optional).

const MAX_BODY = 30_000;
const MIN_TEXT = 50, MAX_TEXT = 20_000;
const SYMBOL = /^[A-Z][A-Z0-9.\-]{0,9}$/;
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const CHANNELS = ["whatsapp", "telegram", "discord", "facebook", "instagram", "x-twitter", "tiktok", "youtube", "reddit",
  "stocktwits", "text-message", "phone-call", "email", "dating-app", "friend-or-family", "other"];
const LOSS = ["under-1k", "1k-10k", "10k-50k", "50k-plus", "prefer-not-to-say"];

function b64(buf) {
  // chunked: a spread over a 60 KB story (multibyte scripts) can overflow the call stack
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}
const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const utf8b64 = (s) => b64(new TextEncoder().encode(s));

export function validate(body) {
  if (!body || typeof body !== "object") return { error: "expected a JSON object" };
  if (body.website) return { spam: true };                                  // honeypot field
  if (body.consent !== true) return { error: "consent is required" };
  const text = typeof body.text === "string" ? body.text.trim() : "";
  if (text.length < MIN_TEXT) return { error: `please write at least ${MIN_TEXT} characters` };
  if (text.length > MAX_TEXT) return { error: `please keep it under ${MAX_TEXT} characters` };
  const stocks = Array.isArray(body.stocks) ? body.stocks.map((s) => String(s).trim().replace(/^\$/, "").toUpperCase()) : [];
  if (stocks.length > 5 || stocks.some((s) => !SYMBOL.test(s))) return { error: "stocks must be up to 5 tickers" };
  const clean = { text, stocks: [...new Set(stocks)], consent: true, contact_ok: false };
  if (body.channel != null && body.channel !== "") {
    if (!CHANNELS.includes(body.channel)) return { error: "unknown channel" };
    clean.channel = body.channel;
  }
  if (body.loss_range != null && body.loss_range !== "") {
    if (!LOSS.includes(body.loss_range)) return { error: "unknown loss range" };
    clean.loss_range = body.loss_range;
  }
  for (const f of ["month_from", "month_to"]) {
    if (body[f]) {
      if (!MONTH.test(body[f])) return { error: `${f} must be YYYY-MM` };
      clean[f] = body[f];
    }
  }
  if (typeof body.language === "string" && /^[a-z]{2}(-[A-Z]{2})?$/.test(body.language)) clean.language = body.language;
  if (body.voice === true) clean.voice = true;
  return { clean };
}

export async function encrypt(obj, publicKeyB64) {
  const pub = await crypto.subtle.importKey("spki", unb64(publicKeyB64), { name: "RSA-OAEP", hash: "SHA-256" }, false, ["encrypt"]);
  const aes = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, aes, new TextEncoder().encode(JSON.stringify(obj)));
  const raw = await crypto.subtle.exportKey("raw", aes);
  const key = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, pub, raw);
  return { alg: "RSA-OAEP-256+A256GCM", key: b64(key), iv: b64(iv), data: b64(data) };
}

export function newId() {
  const a = crypto.getRandomValues(new Uint8Array(8));
  return "s" + [...a].map((x) => "abcdefghjkmnpqrstuvwxyz23456789"[x % 31]).join("");
}

function cors(env, req) {
  const origin = req.headers.get("Origin") || "";
  const ok = env.ALLOWED_ORIGIN && origin === env.ALLOWED_ORIGIN;
  return ok ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "POST, OPTIONS",
               "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400", Vary: "Origin" } : null;
}

const json = (status, obj, headers = {}) =>
  new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...headers } });

async function turnstileOk(env, token) {
  if (!env.TURNSTILE_SECRET) return true;
  if (!token) return false;
  const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST", body: new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: token }),
  });
  return r.ok && (await r.json()).success === true;
}

export default {
  async fetch(req, env) {
    const h = cors(env, req);
    if (!h) return json(403, { error: "origin not allowed" });
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: h });
    if (req.method !== "POST") return json(405, { error: "POST only" }, h);
    if (!env.STORIES_PUBLIC_KEY || !env.GITHUB_TOKEN || !env.INBOX_REPO) return json(503, { error: "story intake is not configured" }, h);
    const len = +(req.headers.get("Content-Length") || 0);
    if (len > MAX_BODY) return json(413, { error: "too large" }, h);
    const text = await req.text();
    if (text.length > MAX_BODY) return json(413, { error: "too large" }, h);
    let body;
    try { body = JSON.parse(text); } catch { return json(400, { error: "invalid JSON" }, h); }
    const v = validate(body);
    if (v.spam) return json(201, { id: "ok" }, h);                          // don't tell bots
    if (v.error) return json(400, { error: v.error }, h);
    if (!(await turnstileOk(env, body.turnstile))) return json(400, { error: "verification failed, please retry" }, h);

    const id = newId();
    const day = new Date().toISOString().slice(0, 10);
    const envelope = { v: 1, id, received: day, ...(await encrypt(v.clean, env.STORIES_PUBLIC_KEY)) };
    const path = `inbox/${day.slice(0, 4)}/${day.slice(5, 7)}/${id}.json`;
    const r = await fetch(`https://api.github.com/repos/${env.INBOX_REPO}/contents/${path}`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${env.GITHUB_TOKEN}`, Accept: "application/vnd.github+json",
                 "User-Agent": "red-flag-club-stories", "X-GitHub-Api-Version": "2022-11-28" },
      body: JSON.stringify({ message: `story ${id}`, content: utf8b64(JSON.stringify(envelope)) }),
    });
    if (!r.ok) return json(502, { error: "could not save right now, please try again later" }, h);
    return json(201, { id }, h);
  },
};
