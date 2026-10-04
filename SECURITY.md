# Security

## What teamcall touches

- **The company's folder** (`--folder`, the current one by default): it writes the charter, the fast-path and
  champion cards, the report, the decision page, the 30-day plan, and appends to `teamcall-journal.jsonl`.
  `boost` writes one project skill under `.claude/skills/<name>/` and never overwrites one that is there.
- **The company policy file** `company-ai-policy.json`, read-only: red folders, allowed vendors, language.
- **`detect`** looks up program names on PATH and reads only whether `~/.claude.json` holds a claude.ai sign-in
  (the key name, never its value); it reads the names of a few environment variables, never their values.
- **`lesson`**, the daily cards, is the one part that talks to the network, and only through two doors: it sends
  HTTPS requests to `api.telegram.org` (the Bot API) and `graph.facebook.com` (the WhatsApp Cloud API) and refuses
  any other host; `lesson serve` receives the WhatsApp buttons and takes only requests signed with the company's app
  secret (`X-Hub-Signature-256`), answering Meta's subscription check only with the company's verify token, and,
  after `lesson webhook`, the Telegram presses carrying the secret made from the bot's token
  (`X-Telegram-Bot-Api-Secret-Token`). `network.json` in the plugin's root declares these doors and the two hosts;
  a test fails the build if a network module appears anywhere else.
- **The company's messenger settings**: `TEAMCALL_*` from the environment or `~/.teamcall.env`. The bot token is the
  company's own; teamcall never prints it, never writes it to a file and never puts it into a message.
- **The chats**: who joined the cards, by Telegram chat id, WhatsApp number or WhatsApp user id (the id Meta gives a
  person with a username in place of the number), stays in the journal in the company's folder, like the names; the
  report never carries them.
- **The schedule**: `lesson schedule` writes one launcher into the company's folder (`teamcall-run.sh`, on Windows
  `teamcall-run.py`); the scheduled runs write `teamcall-schedule.log` and two lock files beside it. On each run the
  launcher lists the folder names under Claude Code's plugin cache to find the teamcall installed now, and reads
  nothing else there.

## What it never does

- Never buys, subscribes, opens a checkout or asks for a card number or a password. The person responsible for the
  company's bot puts its token into `~/.teamcall.env` themselves; the skill never asks for it in the conversation.
- Never sends to any host but the Telegram Bot API and the WhatsApp Cloud API; what goes there is the cards, the bot's
  short answers, the WhatsApp template and the requests that read the buttons pressed.
- Never puts a person's name, chat or number in a report: people are P1, P2, ...; names stay in the journal in the
  company's folder.

## Reporting

Open an issue on github.com/vadimchernets/teamcall, or write to the author through the Poly A1 support address.
