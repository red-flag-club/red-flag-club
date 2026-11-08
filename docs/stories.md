# Community stories — how they flow and how to run it

Spec: `specs/007-community-stories/`. People share what happened to them, by
voice or text, on the site's **Share yours** page. Nothing is published until
you have anonymised it with Claude and approved it.

```
browser (voice → text, or typing)
   │  POST, consent required
   ▼
Cloudflare Worker  worker/stories/        free tier; checks size, consent, honeypot, optional Turnstile
   │  encrypts with YOUR public key (RSA-OAEP-256 + AES-256-GCM)
   ▼
private inbox repo  inbox/YYYY/MM/<id>.json   ciphertext only — no IP, no user agent, no time of day
   │  ./run.sh stories pull --inbox <clone> --git-pull    (decrypts on your machine only)
   ▼
community/inbox/<id>.json            git-ignored plaintext
   │  Claude Code: /story-anonymise
   ▼
community/stories/drafts/<id>.json   git-ignored; names → roles, personal data removed, tags added
   │  ./run.sh stories check <id>     (PII, names, storyline length, tickers, tags)
   │  ./run.sh stories approve <id>   (you read it first)
   ▼
community/stories/approved/<id>.json   committed; the only thing ever published
   │  site workflow: stories.py export → data/stories.json
   ▼
Stories · story pages · Stocks (people who shared, first/last month) · assistant · ticker pages
```

## One-time setup

1. **Keys** (on your machine): `./run.sh stories keygen`. The private key goes
   to `~/.config/pd-defence/stories_key.pem` (mode 600). **Back it up offline**:
   without it, stories in the inbox can't be read. The printed public key is
   safe to share.
2. **Inbox repo**: create a *private* repo, e.g. `red-flag-club/stories-inbox`
   (with a README). Clone it somewhere on your laptop.
3. **GitHub token for the Worker**: Settings → Developer settings →
   Fine-grained tokens → only `red-flag-club/stories-inbox` (resource owner: the organisation) → Repository
   permissions → Contents: Read and write. Nothing else.
4. **Worker** (needs a free Cloudflare account; you already have one for
   cloudflared):
   ```bash
   cd worker/stories
   cp wrangler.toml.example wrangler.toml      # git-ignored; fill INBOX_REPO, ALLOWED_ORIGIN, STORIES_PUBLIC_KEY
   npx wrangler login
   npx wrangler secret put GITHUB_TOKEN
   npx wrangler deploy                          # prints https://red-flag-club-stories.<you>.workers.dev
   ```
   Optional bot protection: create a Turnstile widget (free) in the Cloudflare
   dashboard, `npx wrangler secret put TURNSTILE_SECRET`, and set the site key
   below. Optional: a Cloudflare rate-limiting rule on the Worker route.
5. **Site settings** (repo variables, or `.env`): `PD_STORIES_SUBMIT_URL` = the
   Worker URL, `PD_SITE_URL` = `https://red-flag-club.github.io`,
   optional `PD_TURNSTILE_SITEKEY`. Redeploy (merge to `main`).

Until `PD_STORIES_SUBMIT_URL` is set, the share page lets people write and save
a copy but sends nothing.

## Weekly routine (about 10 minutes)

```bash
./run.sh stories pull --inbox ~/src/stories-inbox --git-pull
./run.sh stories list
```

In Claude Code in this repo: `/story-anonymise` (or "anonymise the new
stories"). Claude writes drafts and runs the checker. Then for each one:

```bash
cat community/stories/drafts/<id>.json        # read it — you are the last check
./run.sh stories check <id>
./run.sh stories approve <id>                 # or: reject <id> --reason "not a pump-and-dump"
./run.sh stories purge                        # delete decrypted originals you no longer need
git add community/stories/approved && git commit -m "Stories" && git push
```

The next site publish (four times a market day, or Actions → site → Run)
includes them.

## Your own story

A draft built only from facts already in this repo is at
`community/stories/owner-ryde-2024.draft.json`. It has two
`[In your own words: …]` gaps the checker refuses to publish. Either fill them
in and run `./run.sh stories stage community/stories/owner-ryde-2024.draft.json`
then `approve owner-ryde-2024 --featured`, or record it on the Share page like
anyone else. No name is used; the loss is shown as a range.

## What the checker enforces

Blocks: emails, links (except sec.gov, finra.org, ic3.gov, investor.gov,
irs.gov, ftc.gov), @handles, phone numbers, 7+ digit numbers, exact dollar
amounts (round figures like "$10,000" are fine), exact dates (month and year
are fine), name-like word pairs from the original, a body under 60% of the
original length, dropped tickers, tags outside the vocabulary, missing consent,
placeholder text, and mentions of self-harm (contact the person first). It
cannot recognise every name or impersonated firm, so it lists capitalised words
for you to scan — that is why approval is manual.

## Privacy notes for the site

- Voice typing uses the browser's speech service; in Chrome that is Google.
  The page says so. No audio is recorded or sent to this project.
- The inbox repo holds only ciphertext. If the token or the repo leaked, the
  stories stay unreadable without your private key.
- Git history in the inbox repo is permanent; that's acceptable because it is
  encrypted. Your decrypted copies are deleted by `stories purge`.
