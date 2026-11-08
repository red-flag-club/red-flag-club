# Red Flag Club: stories

True, first-person accounts from people who lost money to pump-and-dump
schemes, shared so the next person recognises the script in time.
Read them on the site: https://red-flag-club.github.io/#/stories

## What

Each story is in `stories/<id>.md` (readable here) and in `data/stories.json`
(what the site uses). Every story has the stock(s), the months, the channel
(WhatsApp, Facebook ad, ...), the tactics used and a loss range.

## Why

Warnings about "investment scams" in general rarely change what people do.
Recognising *your* situation in someone else's story does: the free
"professor", the months of safe tips, the "rocket plan", the screenshots for
"approval", the "compensation trade" after the crash. People who were hurt
usually stay silent out of shame. These stories end that silence.

## How a story gets here

1. Someone shares it on the site, by voice or text. It goes over HTTPS to a
   small worker that **encrypts it immediately** with the reviewer's public
   key; only the ciphertext is stored, in a private inbox. Nobody else can
   read it, and no IP address or browser details are kept.
2. A reviewer decrypts it on their own machine and anonymises it: names become
   roles ("the 'professor'"), and exact dates, amounts, phone numbers, links and
   anything identifying are removed. **The storyline is not changed.**
3. A script checks for personal data that slipped through.
4. A human approves it, and only then is it published here and on the site.

Spec: [specs/007-community-stories](https://github.com/red-flag-club/red-flag-club/tree/main/specs/007-community-stories).
Code: [scripts/stories.py](https://github.com/red-flag-club/red-flag-club/blob/main/scripts/stories.py),
[worker/stories](https://github.com/red-flag-club/red-flag-club/tree/main/worker/stories).

## Corrections and takedowns

If you wrote a story and want it changed or removed, or you think a story
identifies someone, [open a correction request](https://github.com/red-flag-club/stories/issues/new/choose).
Don't prove who you are in public; a maintainer will reply privately.

## Rules

- Stories describe what happened to the author. They are not findings about
  any company, and they don't say a company or person committed fraud.
- Allegations in court cases are labelled as allegations.
- No financial advice, and nothing here says "buy".

## Licence

Stories: [CC BY-NC-ND 4.0](LICENSE). Share them with credit to
"Red Flag Club", without changing them and not for commercial use.

*This repository is written by the publishing bot after a human approves each
story. Pull requests aren't accepted; use an issue.*
