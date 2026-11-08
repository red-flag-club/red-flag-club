// node --test worker/stories/index.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { encrypt, validate, newId } from "./index.js";

const ORIGIN = "https://example.github.io";
const kp = await crypto.subtle.generateKey({ name: "RSA-OAEP", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["encrypt", "decrypt"]);
const pubB64 = Buffer.from(await crypto.subtle.exportKey("spki", kp.publicKey)).toString("base64");
const env = { STORIES_PUBLIC_KEY: pubB64, GITHUB_TOKEN: "t", INBOX_REPO: "me/inbox", ALLOWED_ORIGIN: ORIGIN };
const TEXT = "I joined a WhatsApp investment club after an ad. The 'professor' told us to buy RYDE and it collapsed two days later.";

async function decrypt(env) {
  const raw = await crypto.subtle.decrypt({ name: "RSA-OAEP" }, kp.privateKey, Buffer.from(env.key, "base64"));
  const aes = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: Buffer.from(env.iv, "base64") }, aes, Buffer.from(env.data, "base64"));
  return JSON.parse(new TextDecoder().decode(plain));
}

function req(body, { origin = ORIGIN, method = "POST" } = {}) {
  return new Request("https://w.example/", { method, headers: { Origin: origin, "Content-Type": "application/json" },
    body: method === "POST" ? JSON.stringify(body) : undefined });
}

function mockGitHub() {
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url, init }); return new Response("{}", { status: 201 }); };
  return calls;
}

test("validation", () => {
  assert.equal(validate({ text: TEXT }).error, "consent is required");
  assert.match(validate({ text: "short", consent: true }).error, /at least/);
  assert.equal(validate({ text: TEXT, consent: true, website: "x" }).spam, true);
  assert.match(validate({ text: TEXT, consent: true, stocks: ["not a ticker!"] }).error, /tickers/);
  const ok = validate({ text: TEXT, consent: true, stocks: ["$ryde"], channel: "whatsapp", loss_range: "10k-50k", ip: "1.2.3.4" });
  assert.deepEqual(ok.clean.stocks, ["RYDE"]);
  assert.equal(ok.clean.ip, undefined);                                   // unknown fields dropped
});

test("stores only ciphertext, without IP or time of day", async () => {
  const calls = mockGitHub();
  const r = await worker.fetch(req({ text: TEXT, consent: true, stocks: ["RYDE"], channel: "whatsapp" }), env);
  assert.equal(r.status, 201);
  const { id } = await r.json();
  assert.match(id, /^s[a-z2-9]{8}$/);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/repos\/me\/inbox\/contents\/inbox\/\d{4}\/\d{2}\/s[a-z2-9]{8}\.json$/);
  const put = JSON.parse(calls[0].init.body);
  const envelope = JSON.parse(Buffer.from(put.content, "base64").toString());
  assert.equal(envelope.alg, "RSA-OAEP-256+A256GCM");
  assert.match(envelope.received, /^\d{4}-\d{2}-\d{2}$/);
  const all = JSON.stringify(envelope);
  assert.ok(!all.includes("WhatsApp") && !all.includes("RYDE"));         // plaintext never stored
  const story = await decrypt(envelope);
  assert.equal(story.text, TEXT);
  assert.deepEqual(story.stocks, ["RYDE"]);
});

test("refuses other origins, bad methods, missing config", async () => {
  mockGitHub();
  assert.equal((await worker.fetch(req({}, { origin: "https://evil.example" }), env)).status, 403);
  assert.equal((await worker.fetch(req(null, { method: "GET" }), env)).status, 405);
  assert.equal((await worker.fetch(req({ text: TEXT, consent: true }), { ALLOWED_ORIGIN: ORIGIN })).status, 503);
  const pre = await worker.fetch(new Request("https://w.example/", { method: "OPTIONS", headers: { Origin: ORIGIN } }), env);
  assert.equal(pre.status, 204);
  assert.equal(pre.headers.get("Access-Control-Allow-Origin"), ORIGIN);
});

test("honeypot gets a fake success and writes nothing", async () => {
  const calls = mockGitHub();
  const r = await worker.fetch(req({ text: TEXT, consent: true, website: "http://spam" }), env);
  assert.equal(r.status, 201);
  assert.equal(calls.length, 0);
});

test("GitHub failure is reported, not swallowed", async () => {
  globalThis.fetch = async () => new Response("{}", { status: 500 });
  assert.equal((await worker.fetch(req({ text: TEXT, consent: true }), env)).status, 502);
});

test("turnstile is enforced when configured", async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push(url);
    return url.includes("turnstile") ? new Response(JSON.stringify({ success: false })) : new Response("{}", { status: 201 });
  };
  const r = await worker.fetch(req({ text: TEXT, consent: true, turnstile: "bad" }), { ...env, TURNSTILE_SECRET: "s" });
  assert.equal(r.status, 400);
  assert.equal(calls.filter((u) => u.includes("api.github.com")).length, 0);
});

test("ids are unique enough", () => {
  const ids = new Set(Array.from({ length: 2000 }, newId));
  assert.equal(ids.size, 2000);
});

test("a long story in a multibyte script survives encryption", async () => {
  const calls = mockGitHub();
  const long = "पम्प एंड डंप ".repeat(1500).slice(0, 19000);
  const r = await worker.fetch(req({ text: long, consent: true, language: "hi-IN" }), env);
  assert.equal(r.status, 201);
  const envelope = JSON.parse(Buffer.from(JSON.parse(calls[0].init.body).content, "base64").toString());
  assert.equal((await decrypt(envelope)).text, long.trim());
});
