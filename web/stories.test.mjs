// node --test web/stories.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildSubmission, filterStories, related, storiesFor, speechSupported, LABELS, LESSONS } from "./stories.js";
import { QUESTIONS, score } from "./quiz.js";

const S = [
  { id: "a", title: "WhatsApp professor", summary: "", body: "group chat", stocks: ["RYDE"], channel: "whatsapp", tactics: ["investment-club", "urgency"], outcome: ["sold-at-loss"] },
  { id: "b", title: "Telegram VIP", summary: "", body: "vip", stocks: ["ABCD"], channel: "telegram", tactics: ["vip-group"], outcome: [] },
  { id: "c", title: "Another RYDE", summary: "", body: "x", stocks: ["RYDE"], channel: "facebook", tactics: ["urgency"], outcome: ["recovery-scam-attempt"] },
];

test("filters by tag, stock, channel and text", () => {
  assert.deepEqual(filterStories(S, { tag: "urgency" }).map((s) => s.id), ["a", "c"]);
  assert.deepEqual(filterStories(S, { tag: "recovery-scam-attempt" }).map((s) => s.id), ["c"]);
  assert.deepEqual(filterStories(S, { stock: "ABCD" }).map((s) => s.id), ["b"]);
  assert.deepEqual(filterStories(S, { channel: "whatsapp" }).map((s) => s.id), ["a"]);
  assert.deepEqual(filterStories(S, { q: "vip" }).map((s) => s.id), ["b"]);
  assert.equal(filterStories(S, {}).length, 3);
});

test("read-next prefers the same stock, then shared tactics", () => {
  assert.equal(related({ stories: S }, S[0])[0].id, "c");
  assert.deepEqual(storiesFor({ stories: S }, "RYDE").map((s) => s.id), ["a", "c"]);
});

test("submission builder keeps only form fields and normalises tickers", () => {
  const fd = new Map(Object.entries({ text: "  my story  ", stocks: "$ryde, abcd efgh ijkl mnop qrst", consent: "on", website: "", channel: "whatsapp", voice: "1" }));
  const s = buildSubmission({ get: (k) => fd.get(k) ?? null });
  assert.equal(s.text, "my story");
  assert.deepEqual(s.stocks, ["RYDE", "ABCD", "EFGH", "IJKL", "MNOP"]);
  assert.equal(s.consent, true);
  assert.equal(s.voice, true);
  assert.equal(s.loss_range, undefined);
});

test("voice support is detected, not assumed", () => {
  assert.equal(speechSupported({}), false);
  assert.equal(speechSupported({ webkitSpeechRecognition: function () {} }), true);
});

test("every vocabulary tag has a label and every tactic a lesson", () => {
  const tactics = ["investment-club", "fake-adviser", "teacher-or-professor", "insider-tip", "urgency", "screenshots-of-gains", "fake-news",
    "ipo-allocation", "vip-group", "small-new-listing", "foreign-issuer", "move-to-private-chat", "buy-signal-time"];
  for (const t of tactics) { assert.ok(LABELS[t], t); assert.ok(LESSONS[t], t); }
});

test("quiz scoring", () => {
  assert.equal(QUESTIONS.length, 10);
  assert.equal(score(QUESTIONS.map((q) => q.red)), 10);
  assert.equal(score(QUESTIONS.map(() => true)), QUESTIONS.filter((q) => q.red).length);
});
