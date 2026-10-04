---
name: teamcall
description: Move a company's people from the chat window to a terminal agent in 30 days, and measure it. Use it when someone sets up AI for a team or company and asks how to get colleagues working in Claude Code (or Codex, Antigravity, Copilot CLI and the others), how to run a pilot of 5 people and grow it to 30-50, who should be the champion, what a 20-minute first session looks like, how to keep a journal of who got stuck where, how to report time, quality, coverage, repeatability, new capability and risk, whether to scale or stop, which seat already pays for which terminal agent, how to turn a task done in the app into one command in the terminal, or how to send the employees one short lesson card a day in Telegram or WhatsApp on leading an agent and approving its steps.
argument-hint: "[plan | fast | champion | boost | log | measure | report | decide | move | agents | detect | lesson] [what for]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py *) PowerShell(${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 teamcall say skills/teamcall/scripts/teamcall.py *) Read Write
---

# teamcall: the company's people, from chat to the terminal in 30 days

## Running teamcall's scripts (Mac, Linux, Windows)

Every script command on this page is written for the **Bash** tool and starts with
`sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/…`. If your shell tool is
**PowerShell** (Windows without Git Bash), only the start changes: write the launcher's path bare, with no quotes
and no `&` — `${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1 teamcall say skills/teamcall/scripts/…` — and keep the rest,
on one line; that is the form this skill's permission covers. Only if that path has a space in it, write
`& "${CLAUDE_PLUGIN_ROOT}/hooks/python.ps1" …` instead (the person is then asked once). Never call `python3`,
`python` or `py` yourself: the launcher finds a real Python 3.8+ and never starts the Microsoft Store or Apple stub.
If it answers with one line saying teamcall "is paused" until this computer has Python 3, tell the
person that in one plain line and write the same documents by hand from the steps below.

The user said: $ARGUMENTS

Answer in the person's language and pass `--lang` with its code (en, es, pt, ru, uk) when it is one of them; the
files teamcall writes then carry names and headings in that language. Everything goes into the company's folder
(`--folder`, the current one by default). teamcall counts and writes plans; it buys nothing — seats are counted
with billcall, and the person responsible for the accounts buys.

## 1. The pilot charter (step K3)

Ask, one at a time: the company's name; how many people start (5 is the size a team lead decides alone); how many
it should reach (30–50); the start date; who sponsors it; who is the first champion. Then:

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py plan --company "<name>" --people 5 --target 30 --start <YYYY-MM-DD> --sponsor "<who>" --champion "<who>" --lang <code>
```

It writes the charter: the promise, the waves week by week, the aim (3 working results of 5), the key number
(minutes of human help per successful first result), the six measurements, the one page for IT (devices, accounts,
data, folders, review, install and remove, contact, retention) with the red folders and vendors from
`company-ai-policy.json` when the company has one, and what the company gives. Show it and offer to adjust.

## 2. The fast path, 20 minutes per person

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py fast --person "<name>" --os mac --task "<a real task of this week>" --lang <code>
```

Five steps with minutes: install (the official one-line installer for the person's system), sign in with the work
seat on claude.ai (so the phone remote works later), the first real task in a copy of the folder with a plan first,
a CLAUDE.md of at most 100 lines, and the same task again as one command. Check a CLAUDE.md with
`… teamcall.py claudemd CLAUDE.md`.

## 3. The champion, 5 hours

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py champion --person "<name>" --lang <code>
```

Seven blocks: plan first and permissions, the team's CLAUDE.md, the company's skills and plugin (firmcall), a
second opinion and other agents (duocall, sidecall), the phone remote (pocketcall), unblocking colleagues from the
journal, measuring. One champion for about eight people.

## 4. The same task, then one command (termboost)

When a person already does a task in the chat app or in Cowork, do it once more in the terminal and leave them a
command for next time:

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py boost --name <short-name> --task "<the task in their words>" --lang <code>
```

It writes the project skill `.claude/skills/<short-name>/SKILL.md` (the person types `/<short-name>`) and a
side-by-side card of the app and the terminal. A skill already there is left as it is.

If the person or the company does not want the terminal, branch B is the same work in Cowork or in the Code tab of
the Claude app: the same charter, the same journal, the same measurements.

## 5. The journal and the measurements

After every step of every person:

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py log add --person "<name>" --stage <invited|installed|signed_in|first_task|first_artifact|weekly|champion|stopped> --minutes <own> --help-minutes <help> --blocker "<where it got stuck>" --artifact "<what was made>"
```

Before and after on one real task:

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py measure --person "<name>" --task "<task>" --before-min 90 --after-min 27 --quality "<what was found>" --coverage-before 10 --coverage-after 40 --repeatable --capability "<new>" --risk "<what a person still checks>"
```

The journal `teamcall-journal.jsonl` stays in the company's folder with the names; reports never carry them.

## 6. The report and the decision (step K4)

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py report --lang <code>
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py decide --max-help 60 --lang <code>
```

The report: people as P1, P2, …, where each one is, help minutes, blockers, the six measurements, and the key
number. The decision page: scale (3 of every 5 reached a working result, a champion, help within the limit), fix
and repeat, or stop and change the route — with the next step.

## 7. Moving people in 30 days, program by program (step B13)

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py move --start <YYYY-MM-DD> --lang <code>
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py agents --lang <code>
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py detect --lang <code>
```

`agents` lists which seat already pays for each terminal agent (Claude Code, Codex CLI, Antigravity and Gemini CLI,
Copilot CLI, Grok Build, Muse Code, Kiro, Cursor; OpenCode, Qwen Code, Kimi Code, Goose, aider with Groq; sidecall
and roundcall), each with its source page and the day it was read, and the company's rule for the program: Grok on
a cleaned copy with a prepaid balance, Kimi in a training folder, Antigravity and Gemini CLI with permissions one by
one. gatecall enforces those rules. `detect` says which of them are on this computer and how Claude Code is signed
in here (an API key or a custom `ANTHROPIC_BASE_URL` turns the phone remote off).

## 8. One card a day in Telegram or WhatsApp

Short daily lessons where the person already is — the messenger on their phone, nothing to install. One card a
working day on leading an agent and approving its steps (20 cards), with three buttons: done, show me (the bot answers
with the exact words to type), skip. Each person goes through the cards at their own pace, from card 1 on their first
working day, so whoever joins later still gets all 20 in order. The company's own bot sends them; the answers go
into the journal, and `report` counts them without names. Each person gets the cards in their own language.

The bot is the company's: the person responsible creates it (Telegram: @BotFather) and puts its token into
`~/.teamcall.env` themselves (`TEAMCALL_TELEGRAM_TOKEN=…`, one `TEAMCALL_NAME=value` per line). Never ask for a token
in the conversation and never write one into a file yourself; `teamcall lesson schedule` shows the names it reads.

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py lesson invite --person "<name>" --lang <code>
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py lesson card --lang <code>
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py lesson send
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py lesson pull
sh "${CLAUDE_PLUGIN_ROOT}/hooks/python.sh" teamcall say skills/teamcall/scripts/teamcall.py lesson schedule --at 09:00 --folder "<company folder>"
```

`lesson pull` reads the presses and messages since the last run, once, and ends. The receiver that stays on is
`pull --loop`, and the schedule starts it: it runs until stopped, so never start it from the conversation.

`invite` prints a link for that person: one tap on the phone, Start, and the cards come (`card` in the chat brings
the card of the day again, `stop` ends them, `start` brings them back). `card` shows the card of the pilot's day;
`send` gives each person who joined their own next card, one a day — a second run the same day sends nothing, a day
nobody sent moves the cards and loses none, and nobody begins before the start `plan` wrote into the journal (a plan
written again without `--start` keeps it). `send` also names who was invited and has not joined yet; a messenger
whose setting is missing holds up no other — its chats are named as not delivered, with the setting, and the rest
get their cards. `pull --loop` is the Telegram receiver that stays on and answers "show me" with the card's example.
`schedule` writes the launcher
`teamcall-run.sh` (Windows: `teamcall-run.py`) into the company's folder and prints the lines for cron (Mac, Linux)
or Task Scheduler (Windows): the cards every 15 minutes of each working day from `--at` to 20:00, so a computer that
was asleep sends when it wakes, and the two receivers every 5 minutes, each only once and only when its messenger's
settings are in place. The lines name the launcher, never the plugin's version folder: on every run it finds the
newest teamcall installed now, so an update of the plugin keeps the schedule working. On Windows the tasks run without
a window, on battery too, and catch up a run missed while the computer was off.

WhatsApp is the second channel: `lesson invite --channel whatsapp` gives a wa.me link to the company's number (or
`--phone` puts a number on the list at once, even before the WhatsApp settings are in — the missing one is named). A
person with a WhatsApp username may come without a number: Meta names them by their user id, and the cards go to
that id. `lesson template --create` sends the note template in five languages to
Meta for approval, once, and prints the category Meta gives it; `lesson serve` is the receiver Meta brings the buttons
to, behind the company's HTTPS (or with `--cert` and `--cert-key`, then on every address of the computer). Inside 24
hours after the person's last message the card goes with reply buttons; after them goes the approved note that the
person's own card is ready, with one button, Open the card — no lesson text, so it stays utility — and the tap brings
the card. Any message from the person brings their next card. A card Meta reports as not delivered is not counted
and stays the person's next card; a move of the template to another category is said with the way to a review.

Where `lesson serve` runs behind the company's HTTPS, `lesson webhook --url https://<that address>/telegram` has
Telegram bring each Start and press there at once, so none waits on a computer that is off (Telegram keeps an update
24 hours); the receiver takes only requests carrying the secret made from the bot's token. `--off` hands them back to
`pull`.
