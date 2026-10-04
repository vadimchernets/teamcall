# Changelog

## 0.1.4 — 2026-10-03

- `lesson`: one short card a working day, in the messenger the employee already has — Telegram first (Bot API
  `sendMessage` with three inline buttons: done, show me, skip), WhatsApp second (Cloud API: reply buttons inside the
  24 hours after the person's last message; after them the company's approved note that the person's own card is
  ready, with one button that brings it — no lesson text in it, so Meta files it as utility). Twenty cards for the four weeks teach leading an agent and approving its steps — a
  result instead of a question, plan first, one step at a time, a copy, the list of changes, stop and steer, rules,
  checks, one command, permissions, the outside buttons, a second opinion, the phone, measuring, the champion.
  English, Spanish, Portuguese, Russian, Ukrainian; each person gets the cards in their own language.
- The company's own bot and token (`~/.teamcall.env` or the environment, never printed or written); the employee
  installs nothing: one tap on an invite link joins, `stop` ends, `start` comes back.
- `lesson send` gives each person their own next card, one a day: card 1 on their first working day, so whoever joins
  in week 3 or after the pilot still gets all 20 in order; a day nobody sent moves the cards and loses none; a second
  run the same day sends nothing; nobody begins before the start `plan` now writes into the journal, and a plan
  written again without `--start` keeps it. `send` names who was invited and has not joined yet. `lesson pull
  --loop` is the Telegram receiver that stays on and answers "show me" with the card's example; `card` in the chat
  brings the card of the day again. `lesson serve` is the receiver WhatsApp brings its buttons to (verify token,
  `X-Hub-Signature-256` signed with the app secret), each connection and its TLS handshake in a thread of its own;
  any message from the person brings their next card, a card Meta reports as `failed` stays their next card and is
  not counted, and a `template_category_update` is said in one line with the way to a review. `lesson template`
  gives or creates the WhatsApp note in five languages and prints Meta's category. `lesson card` shows the card of
  the pilot's day.
- WhatsApp usernames: a person Meta names by the business-scoped user id alone (`from_user_id`, no `from`) gets a chat
  of their own, and the welcome, the cards and the answers go to that id as `recipient`; two such people stay two, and
  a message carrying both the number and the id keeps the person in one chat.
- A messenger without its settings holds up no other: `lesson send` names its chats as not delivered, with the
  missing setting, and the other messenger's chats get their cards; `lesson invite` names a setting still missing
  and keeps the invite.
- `lesson webhook --url https://<address>/telegram`: Telegram brings each Start and press to `lesson serve` the moment
  it is made (`setWebhook` with a secret made from the bot's token, checked on every request; an update brought again
  is taken once), so a weekend with the champion's computer off loses none — Telegram keeps an update 24 hours.
  `pull --loop` stands down while it is on; `--off` hands the presses back to it.
- `lesson schedule` writes a launcher into the company's folder and prints the lines for cron or Task Scheduler that
  run it: the cards every 15 minutes of each working day from `--at` to 20:00, so a computer asleep at 09:00 sends
  when it wakes, and the two receivers every 5 minutes, each held by a lock and started only when its messenger's
  settings are in place (`--if-set`). The launcher finds the newest teamcall Claude Code has installed on every run,
  so an update of the plugin, whose old version folder goes 14 days later, keeps the schedule working; a run with
  nothing to say leaves no line in `teamcall-schedule.log`. On Windows the tasks run through `pyw.exe` or
  `pythonw.exe` — no window — on battery too, catching up a run missed while the computer was off.
- `~/.teamcall.env` is read in UTF-8 with or without its mark and in the UTF-16 that Windows PowerShell 5.1 writes;
  a Python without certificates of its own (python.org's on a Mac before Install Certificates) checks the
  messengers with the system's list.
- `report`: a new part on the daily cards — per card and per person (P1, P2, …): sent, done, show me, skipped, no
  answer. No name, chat or number goes into it.
- The charter's page for IT names the daily cards.
- Network: only `lesson` talks to it, and only to `api.telegram.org` and `graph.facebook.com`; one door sends, one
  receiver listens. The test that forbade any network module now proves the exact places of these doors and reddens
  on any other.
- Tests: every messenger call goes to a fake transport, the real door is shut during the tests; the launchers run for
  real on a made-up plugin cache; mutations for the lessons, the schedule and the launchers in `tools/mutate_code.py`.

## 0.1.3 — 2026-10-03

- Wording: no disclaimers. README's opening says what teamcall does, once.
- Tests: a tone check reddens on disclaimers, excuses and apologies in what people read (five languages).

## 0.1.2 — 2026-10-03

- README: the Zenodo DOI badge (the concept DOI always points to the latest version).

## 0.1.1 — 2026-10-03

- Zenodo DOI: the repository is archived on Zenodo; this release is the first one it records (same content as 0.1.0).

## 0.1.0 — 2026-10-02

- First release: `plan`, `fast`, `champion`, `boost`, `claudemd`, `log`, `measure`, `report`, `decide`, `move`,
  `agents` and `detect`, one skill, no hooks.
- `data/agents.json`: sixteen terminal agents and plugins with the seat that already pays for each, its source page
  and the day it was read, and the per-program rules gatecall enforces (Grok on a cleaned copy with a prepaid
  balance, Kimi in a training folder, Antigravity and Gemini CLI with permissions one by one).
- Dictionaries in English, Spanish, Portuguese, Russian and Ukrainian: file names and headings the person sees.
