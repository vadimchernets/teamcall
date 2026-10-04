# teamcall

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23116725.svg)](https://doi.org/10.5281/zenodo.23116725)

A company's people, from the chat window to a terminal agent in 30 days — and the numbers to show it worked. A
[Claude Code](https://claude.com/claude-code) plugin of Poly A1, for the person in a company who brings colleagues
onto AI agents. Repository: [github.com/vadimchernets/teamcall](https://github.com/vadimchernets/teamcall).

**teamcall plans, keeps the journal and counts; it buys nothing.**
Seats are counted with [billcall](https://github.com/vadimchernets/billcall); the person responsible for the
company's accounts buys.

## What it does

| Command | What the company gets |
|---|---|
| `plan` | The pilot charter: 5 people growing to 30–50 through champions, week by week; the aim (3 working results of 5); the key number — minutes of human help per successful first result; the six measurements; one page for IT (devices, accounts, data, folders, review, install and remove, contact, retention), with red folders and vendors from `company-ai-policy.json`. |
| `fast` | A 20-minute card for one person: install, sign in with the work seat, the first real task with a plan first, a CLAUDE.md of at most 100 lines, the same task again as one command. |
| `champion` | A 5-hour path for the person who helps about eight colleagues: plan mode and permissions, the team's CLAUDE.md, the company's skills and plugin, a second opinion and other agents, the phone remote, unblocking from the journal, measuring. |
| `boost` | termboost: a task the person already does in the app or in Cowork, done once in the terminal and left as a project skill `/<name>` (or `claude -p "/<name>"` on a schedule), with a side-by-side card. |
| `claudemd` | Checks a CLAUDE.md: short direct instructions, at most 100 lines. |
| `log`, `measure` | The transition journal `teamcall-journal.jsonl` in the company's folder: each person's stage, own minutes, help minutes, blocker, artifact; before-and-after on one real task. |
| `report` | The pilot report without names (P1, P2, …): where each person is, the help it took, the blockers, the six measurements — time, quality, coverage, repeatability, new capability, what a person checks — and the key number. |
| `decide` | One page: scale to the next wave, fix and repeat, or stop and change the route — from the journal alone, with the next step. |
| `move` | The 30-day plan of moving people, week by week, with each program and the seat that pays for it. |
| `agents`, `detect` | Which seat already pays for which terminal agent (Claude Code, Codex CLI, Antigravity and Gemini CLI, Copilot CLI, Grok Build, Muse Code, Kiro, Cursor; OpenCode, Qwen Code, Kimi Code, Goose, aider with Groq; sidecall, roundcall), each with its page and day, and the company's rule for the program; which of them are on this computer and how Claude Code is signed in here. |
| `lesson` | One short card on each working day of the pilot in Telegram or WhatsApp, from the company's own bot: how to lead an agent and approve its steps (20 cards for the 4 weeks), with three buttons — done, show me, skip. The employee installs nothing; the answers go into the journal, and `report` counts them without names. |

Every file it writes has its name and headings in the person's language: English, Español, Português, Русский,
Українська (`--lang`, or `language` in the company policy). The daily cards come in each person's own language.

## Daily cards in Telegram and WhatsApp

The employee already has the messenger on the phone, and the company has a bot of its own. One card a day teaches
leading an agent, not chatting: a result instead of a question, the plan first, one approved step at a time, a copy,
the list of changes, stop and steer, the rules the agent reads, checks, one command for a weekly task, permissions,
the outside buttons, a second opinion, approving from the phone, measuring, the champion. Under each card: **Done**,
**Show me** (the bot answers with the exact words to type) and **Skip**.

**Once, for the company.**

1. Telegram: create the bot with @BotFather and put its token into `~/.teamcall.env` — one `TEAMCALL_NAME=value` per
   line, readable only by you, in UTF-8 or the UTF-16 Windows PowerShell writes; teamcall reads it on every run and
   never prints it: `TEAMCALL_TELEGRAM_TOKEN=…`.
2. WhatsApp, the second channel: from the Meta app of the company's WhatsApp Business number, add
   `TEAMCALL_WHATSAPP_TOKEN`, `TEAMCALL_WHATSAPP_PHONE_ID`, `TEAMCALL_WHATSAPP_NUMBER`, `TEAMCALL_WHATSAPP_WABA_ID`,
   `TEAMCALL_WHATSAPP_APP_SECRET` and a `TEAMCALL_WHATSAPP_VERIFY_TOKEN` of your choice. Run
   `teamcall lesson template --create` once — the note "your card 3/20 is ready" with its one button, Open the card,
   goes to Meta for approval in five languages, and the category Meta gives it is printed — and keep
   `teamcall lesson serve` running on a computer that stays on, behind the company's HTTPS address (or HTTPS itself
   with `--cert` and `--cert-key`, then on every address of that computer). That address and the verify token go into
   the app's Webhooks, subscribed to `messages` and `template_category_update`.
3. Telegram with nothing waiting on any computer: where `lesson serve` runs behind the company's HTTPS anyway,
   `teamcall lesson webhook --url https://<that address>/telegram` has Telegram bring each Start and press there the
   moment it is made, every request carrying a secret made from the bot's token (Telegram calls ports 443, 80, 88 and
   8443). Telegram keeps an update for 24 hours, so this way a weekend with the champion's computer off loses no Start
   and no press. `--off` hands them back to `lesson pull`.

**For each person.** `teamcall lesson invite --person "Ann" --lang es` prints a link: one tap on the phone, Start, and
the cards come. `--channel whatsapp` gives a wa.me link to the company's number; `--phone` puts a number on the list
at once. A setting the messenger still lacks is named in one line, and the invite stands: its cards go once the
setting is in. In the chat `card` brings the card of the day again, `stop` ends the cards, `start` brings them back.

**Every day.**

```
teamcall lesson card                  # the card of the pilot's day, to read it first
teamcall lesson send                  # each person's own next card, one a day
teamcall lesson pull --loop           # the Telegram receiver: buttons and "show me" answered within seconds
teamcall lesson schedule --at 09:00   # writes the launcher into the company's folder and prints the lines below
```

What `lesson schedule` prints on a Mac or Linux, for `crontab -e`:

```
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
# Every working day from 09:00 to 20:00, every 15 minutes while this computer is on: each person's next card, one a day
*/15 9-19 * * 1-5 sh "<company folder>/teamcall-run.sh" lesson send --at 09:00 --folder "<company folder>"
# The Telegram buttons and "Show me": one receiver that stays on; every 5 minutes it starts again if it stopped
*/5 * * * * sh "<company folder>/teamcall-run.sh" lesson pull --loop --if-set --folder "<company folder>"
# WhatsApp: the receiver of the buttons, kept running the same way
*/5 * * * * sh "<company folder>/teamcall-run.sh" lesson serve --port 8080 --if-set --folder "<company folder>"
```

On Windows it prints the same three as `Register-ScheduledTask` lines: run by `pyw.exe` or `pythonw.exe`, so no window
opens, with `New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
-MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)`: on battery too, a run missed while the computer
was off comes when it is on again, and the receivers have no time limit. A later `--at` such as 08:30 starts the first
hour at its minute (`30-59/15 8 * * 1-5`).

Each person goes through the 20 cards at their own pace: card 1 on their first working day, then one a day. A person
who joins in week 3, or after the pilot, still gets every card in order; a day the computer was off moves the cards
by a day and loses none; a second run the same day sends nothing and leaves no line in the log. Nobody begins before
the pilot's start that `teamcall plan --start` writes into the journal; a plan written again without `--start` keeps
it. `send` also names the people who were invited and have not joined yet. A messenger whose setting is missing holds
up no other: its chats are named as not delivered, with the setting and where it goes, and stay due, while the
other messenger's chats get their cards.

The schedule's lines name the launcher `teamcall-run.sh` (Windows: `teamcall-run.py`) in the company's folder, never
the plugin's own folder: Claude Code keeps each version of a plugin in a folder of its own and removes the old one 14
days after an update, so on every run the launcher finds the newest teamcall installed now and runs it. What a run
says goes into `teamcall-schedule.log` beside it, under the run's time. Each receiver starts only when its
messenger's settings are in place (`--if-set`), so a company with one messenger gets no errors from the other.

WhatsApp takes free-form messages for 24 hours after the person's last message: inside them the card goes with its
three reply buttons. After them goes the company's approved template — the short note that the person's own card is
ready, with one button, Open the card. It holds no lesson text, so Meta files it as utility, and the tap opens the 24
hours: the card itself follows with its buttons. Any message from the person brings their next card too. A person
with a WhatsApp username may come without a number — Meta leaves it out when the company has not been in touch with
them for 30 days — and is then named by their business-scoped user id: they get a chat of their own, and every card
and answer goes to that id; a later message carrying both the number and the id stays in the same chat. A card Meta
reports as not delivered (a `failed` status, such as a marketing template to a +1 number) is not counted as sent and
stays the person's next card; when Meta moves the template to another category, `serve` says so in one line with
the way to ask for a review. The report adds a part on the cards: per card and per person (P1, P2, …) — sent, done,
show me, skipped, no answer.

## Installing

From the Poly A1 catalogue, by its link — no git and no account needed:

```
/plugin marketplace add https://raw.githubusercontent.com/vadimchernets/poly-a1-plugins/main/.claude-plugin/marketplace.json
/plugin install teamcall@poly-a1
```

Then say what you want: "we want to bring our five marketers onto Claude Code", "write the pilot charter", "what
does Copilot Business already include", "send the team one short card a day in Telegram", "report on our pilot".

## What it needs

Python 3.8+ and its standard library — no dependencies. Only `lesson` talks to the network: HTTPS to
`api.telegram.org` and `graph.facebook.com` with the company's own token, and the receiver `lesson serve` (WhatsApp,
and Telegram after `lesson webhook`); everything else stays on this computer. The skill runs its script through `hooks/python.sh` (PowerShell:
`hooks/python.ps1`), which finds a real Python and never starts the Apple or Microsoft Store stub.

## Checks

`python3 -m pytest -q tests` — the charter's waves add up to the target, the fast path is 20 minutes and the champion
path 5 hours, a CLAUDE.md over 100 lines is red, the report never carries a name, the decision turns on its three
rules, every agents row names its https page and day and a known rule, every dictionary has every word, and network
code sits only in the two doors of `lesson` — the one that sends and the receiver `lesson serve`, three functions in
all (the test finds each of them and reddens on any other). The daily cards are tested on a fake transport, with the
real door shut: each person's own next card (a late joiner starts at card 1, a missed day moves the cards, a second
run the same day sends nothing, a plan written again keeps its start), its three buttons, a press from a stranger or
off the card left uncounted, stop and start, a blocked bot, WhatsApp's 24 hours, its note without lesson text and the
card after the tap, a failed delivery left uncounted, Meta's category move said, the signed WhatsApp webhook, a
person Meta names by the user id alone (a chat of their own, every card to that id, two such people kept apart, the
number and the id kept in one chat), a messenger without its settings holding up no other,
Telegram's webhook only with the bot's secret and each update taken once, a TLS handshake in the connection's own
thread, the report without names, chats or numbers, a token never printed; the schedule's lines through the launcher
and cron's hours from `--at` to the minute; the launcher, run for real on a made-up plugin cache, choosing the newest
version without Claude Code's orphan mark; a settings file from Windows PowerShell; a Python without certificates of
its own. `python3 tools/mutate_code.py` breaks teamcall's own rules one by one in a copy and expects the tests to go
red; its last line counts the mutations that misbehaved.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
