# Story contracts

## 1. Browser → Worker: POST {submit_url}
`application/json`, ≤ 30 KB:
`{text (50..20000 chars), stocks [≤5 tickers], channel?, loss_range?, language?,
  month_from? (YYYY-MM), month_to?, consent: true, contact_ok: false,
  website: "" (honeypot), turnstile?: token}`
→ `201 {id}` | `400 {error}` | `429` | `503` (not configured).
CORS: only the configured site origin.

## 2. Worker → inbox repo: `inbox/YYYY/MM/<id>.json`
`{v:1, id, received (YYYY-MM-DD), alg:"RSA-OAEP-256+A256GCM", key (b64, RSA-wrapped
AES key), iv (b64), data (b64 AES-GCM ciphertext of the JSON in §1 minus
turnstile/website)}`. No IP address, no user agent, no time of day.

## 3. Draft / approved story (`community/stories/{drafts,approved}/<id>.json`)
`{id, title (≤ 90), summary (≤ 280), body (anonymised, storyline intact),
  stocks [], month_from, month_to, submitted (YYYY-MM-DD), channel,
  tactics [], outcome [], loss_range, language, read_minutes,
  source_chars (original length), redactions (count), status, featured?}`

Vocabulary (`scripts/stories.py` `VOCAB`):
- channel: whatsapp, telegram, discord, facebook, instagram, x-twitter, tiktok,
  youtube, reddit, stocktwits, text-message, phone-call, email, dating-app,
  friend-or-family, other
- tactics: investment-club, fake-adviser, teacher-or-professor, insider-tip,
  urgency, screenshots-of-gains, fake-news, ipo-allocation, vip-group,
  small-new-listing, foreign-issuer, move-to-private-chat, buy-signal-time
- outcome: sold-at-loss, still-holding, account-restricted,
  recovery-scam-attempt, reported-to-regulator, broker-helped
- loss_range: under-1k, 1k-10k, 10k-50k, 50k-plus, prefer-not-to-say

## 4. Public export `data/stories.json`
`{built, count, stories: [approved fields minus source_chars/redactions/status],
  stocks: [{s, people, first_month, last_month}], tags: {tactics:{tag:n}, channel:{…}}}`
