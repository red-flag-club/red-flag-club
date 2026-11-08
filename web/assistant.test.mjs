// node --test web/assistant.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { answer, findTicker } from "./assistant.js";

const data = {
  meta: { data_session: "2024-09-06", base_rates: { bracket: { n: 61129, win: 0.301, breakeven: 0.4 } } },
  symbols: new Map([["RYDE", { s: "RYDE", band: "$5-30", r1: 0.43, r5: 1.49, r21: 1.49, rv: 3.9, verdict: "VETO",
                                flags: ["up 149% in <= 10 sessions (pump profile)"], scan_days: 2, first_seen: "2024-09-05" }]]),
  movers: { lists: { day: [{ s: "RYDE", chg: 0.43, verdict: "VETO" }], week: [], month: [] } },
  scan: { sessions: [{ session: "2024-09-06", hits: [{ s: "RYDE", verdict: "VETO" }] }] },
};

test("finds tickers in common phrasings", () => {
  assert.equal(findTicker("is $ryde a pump?"), "RYDE");
  assert.equal(findTicker("check RYDE please"), "RYDE");
  assert.equal(findTicker("I bought ryde last week", new Set(["RYDE"])), "RYDE");
  assert.equal(findTicker("what are the red flags"), null);
  assert.equal(findTicker("I lost money"), null);
});

test("ticker answer uses the data and links to the lookup", () => {
  const a = answer("is $RYDE a pump?", data);
  assert.match(a.text, /VETO/);
  assert.match(a.text, /\+149%/);
  assert.equal(a.links[0].href, "#/t/RYDE");
});

test("unknown ticker says so instead of inventing a verdict", () => {
  const a = answer("check $ZZZZ", data);
  assert.match(a.text, /not in today's small-cap set/);
  assert.doesNotMatch(a.text, /VETO|NO FLAGS|CAUTION/);
});

test("recovery offers are warned about before anything else", () => {
  const a = answer("someone says they can recover my money from RYDE", data);
  assert.match(a.text, /fee up front|recover/i);
});

test("never recommends buying", () => {
  for (const q of ["should I buy RYDE?", "is RYDE worth buying", "what's pumping today", "top movers this week",
                   "hello", "RYDE", "price target for RYDE"]) {
    const t = answer(q, data).text.toLowerCase();
    assert.doesNotMatch(t, /\byou should buy\b|\bgood buy\b|\bbuy now\b|\bstrong buy\b/);
  }
  assert.match(answer("should I buy RYDE?", data).text, /can't tell you to buy/);
});

test("lost money gives the steps and the ticker check", () => {
  const a = answer("I lost money on RYDE", data);
  assert.match(a.text, /report/i);
  assert.match(a.text, /VETO/);
});

test("lists and fallback", () => {
  assert.match(answer("what's pumping today?", data).text, /RYDE \+43% \(VETO\)/);
  assert.match(answer("blah blah", data).text, /didn't understand/);
});

test("stories, sharing and quiz intents", () => {
  const d = { ...data, stories: { count: 4 } };
  assert.equal(answer("I want to share my story", d).links[0].href, "#/share");
  assert.match(answer("are there stories about RYDE", d).text, /4 people/);
  assert.equal(answer("are there stories about RYDE", d).links[0].href, "#/stories?stock=RYDE");
  assert.equal(answer("quiz me", d).links[0].href, "#/quiz");
});
