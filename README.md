# teamcall

A company's people, from the chat window to a terminal agent in 30 days — and the numbers to show it worked. A
[Claude Code](https://claude.com/claude-code) plugin of Poly A1, for the person in a company who brings colleagues
onto AI agents. Repository: [github.com/vadimchernets/teamcall](https://github.com/vadimchernets/teamcall).

**teamcall plans, keeps the journal and counts; it buys nothing, opens no checkout and never asks for a card.**
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

Every file it writes has its name and headings in the person's language: English, Español, Português, Русский,
Українська (`--lang`, or `language` in the company policy).

## Installing

From the Poly A1 catalogue, by its link — no git and no account needed:

```
/plugin marketplace add https://raw.githubusercontent.com/vadimchernets/poly-a1-plugins/main/.claude-plugin/marketplace.json
/plugin install teamcall@poly-a1
```

Then say what you want: "we want to bring our five marketers onto Claude Code", "write the pilot charter", "what
does Copilot Business already include", "report on our pilot".

## What it needs

Python 3.8+ and its standard library — no dependencies, no network module. The skill runs its script through
`hooks/python.sh` (PowerShell: `hooks/python.ps1`), which finds a real Python and never starts the Apple or
Microsoft Store stub.

## Checks

`python3 -m pytest -q tests` — the charter's waves add up to the target, the fast path is 20 minutes and the champion
path 5 hours, a CLAUDE.md over 100 lines is red, the report never carries a name, the decision turns on its three
rules, every agents row names its https page and day and a known rule, every dictionary has every word, and no
network code is present. `python3 tools/mutate_code.py` breaks teamcall's own rules one by one in a copy and expects
the tests to go red; its last line counts the mutations that misbehaved.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
