---
name: teamcall
description: Move a company's people from the chat window to a terminal agent in 30 days, and measure it. Use it when someone sets up AI for a team or company and asks how to get colleagues working in Claude Code (or Codex, Antigravity, Copilot CLI and the others), how to run a pilot of 5 people and grow it to 30-50, who should be the champion, what a 20-minute first session looks like, how to keep a journal of who got stuck where, how to report time, quality, coverage, repeatability, new capability and risk, whether to scale or stop, which seat already pays for which terminal agent, or how to turn a task done in the app into one command in the terminal.
argument-hint: "[plan | fast | champion | boost | log | measure | report | decide | move | agents | detect] [what for]"
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
If it answers with one line saying teamcall "is paused" because this computer has no working Python 3 yet, tell the
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
