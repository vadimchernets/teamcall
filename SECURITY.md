# Security

## What teamcall touches

- **The company's folder** (`--folder`, the current one by default): it writes the charter, the fast-path and
  champion cards, the report, the decision page, the 30-day plan, and appends to `teamcall-journal.jsonl`.
  `boost` writes one project skill under `.claude/skills/<name>/` and never overwrites one that is there.
- **The company policy file** `company-ai-policy.json`, read-only: red folders, allowed vendors, language.
- **`detect`** looks up program names on PATH and reads only whether `~/.claude.json` holds a claude.ai sign-in
  (the key name, never its value); it reads the names of a few environment variables, never their values.

## What it never does

- Never buys, subscribes, opens a checkout or asks for a card number, a password or an API key.
- Never goes to the network: Python's standard library only, and no network module is imported (a test fails the
  build if one appears).
- Never puts a person's name in a report: people are P1, P2, ...; names stay in the journal in the company's folder.

## Reporting

Open an issue on github.com/vadimchernets/teamcall, or write to the author through the Poly A1 support address.
