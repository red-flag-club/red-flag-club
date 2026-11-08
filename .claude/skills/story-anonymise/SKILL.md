---
name: "story-anonymise"
description: "Anonymise community stories for Red Flag Club: read decrypted submissions in community/inbox/, write anonymised drafts with tags to community/stories/drafts/ without changing the storyline, and run the checker. Never approves or publishes."
argument-hint: "Optional story id; default: every submission without a draft"
user-invocable: true
disable-model-invocation: false
---

# Anonymise community stories (specs/007-community-stories)

You turn a person's true story into one that is safe to publish, **without
changing what happened**. The goal is that other people recognise the same
scheme and avoid it. You never approve or publish; the owner does, after
reading your draft.

## Steps

1. `python3 scripts/stories.py list` — find submissions waiting for
   anonymisation (or use the id in the argument).
2. For each id, read `community/inbox/<id>.json` (fields: `text`, `stocks`,
   `channel`, `loss_range`, `month_from`, `month_to`, `language`, `received`,
   `consent`). If `consent` is not true, stop and tell the owner.
3. Write `community/stories/drafts/<id>.json` with the schema below.
4. Run `python3 scripts/stories.py check <id>`. Fix every ERROR by editing the
   draft (never by weakening the story). Repeat until it says OK.
5. Report to the owner: the id, the title, anything you removed that might
   matter (e.g. "removed the name of the brokerage the scammers impersonated"),
   and any concern (duplicate, possibly not a pump-and-dump, abusive content,
   self-harm). Then stop. The owner runs `stories.py approve <id>` or `reject`.

## Rules for the body

Keep:
- The storyline in the author's order and voice (first person stays first
  person), including feelings, mistakes and what they wish they had known.
- Stock tickers and company names of the **stocks** involved.
- The channel and app names (WhatsApp, Telegram, Facebook ad, …), group-chat
  tactics, what was promised, how the price moved, what happened after.
- Month and year (e.g. "in September 2024").

Remove or replace:
- **People's names** (the author, family, the "professor", "assistant",
  brokers, anyone) → a role in quotes: "the 'professor'", "his 'assistant'",
  "my brother". Do this even for names that sound fake.
- **Real firms that were impersonated** (a bank, brokerage, research house) →
  "[a well-known brokerage]" / "[a large bank]". Keep the stock's company name.
- Phone numbers, emails, @handles, links (except sec.gov, finra.org, ic3.gov,
  investor.gov), group invite links, account/order/case numbers, addresses,
  employer, school, city if smaller than a large metro, age, exact dates
  (keep month and year), exact amounts (use the range or a round figure:
  "around $20,000"), screenshots descriptions with personal details.
- Accusations against named individuals or companies other than the stock's
  price behaviour; describe what happened, not who is guilty.

Do **not**: summarise, shorten for style, add advice, add facts, change
numbers other than rounding amounts, translate unless the owner asks (keep
`language`), or fix grammar beyond obvious typos. The checker fails a body
under 60% of the original length.

## Draft schema (`community/stories/drafts/<id>.json`)

```json
{
  "id": "<same id>",
  "title": "≤ 90 chars, specific, no names — e.g. \"A Facebook ad, a WhatsApp 'professor' and RYDE\"",
  "summary": "≤ 280 chars, what happened and the lesson, in plain words",
  "body": "the anonymised story",
  "stocks": ["RYDE"],
  "month_from": "2024-09", "month_to": "2024-09",
  "submitted": "<received date>",
  "channel": "whatsapp",
  "tactics": ["investment-club", "teacher-or-professor", "urgency"],
  "outcome": ["sold-at-loss"],
  "loss_range": "10k-50k",
  "language": "en",
  "redactions": 7,
  "status": "draft"
}
```

Tags must come from `VOCAB` in `scripts/stories.py` (channel, tactics,
outcome, loss_range). Add every tag the story supports; none it doesn't.
Keep the author's tickers; add a ticker only if the story clearly names it.
