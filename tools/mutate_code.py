#!/usr/bin/env python3
"""Break teamcall's own rules on purpose, in a copy, and watch the tests redden.

Each mutation copies the plugin folder to a temporary place, changes one exact text in one file of the
copy (the text must be there exactly once, or the mutation itself is reported as broken), runs the named
tests in the copy, and expects them red. The control mutation changes a comment and expects green. After
every run the sha256 of every original file is compared with the one taken at the start: the plugin itself
is never touched. The last line counts the mutations that misbehaved; anything but 0 is a failure.

  python3 tools/mutate_code.py            (about a minute; needs pytest, like the tests themselves)

"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = "skills/teamcall/scripts/teamcall.py"
TESTS = "tests/test_teamcall.py"
LESSONS = "tests/test_lessons.py"
SKIP = (".git", "__pycache__", ".pytest_cache", "dist")

# (what is broken, file, exact text, replacement, tests to run, expected outcome)
MUTATIONS = (
    ("control: a comment reworded", SCRIPT,
     "# the key metric of the pilot: human-support minutes per successful first artifact",
     "# the key number of the pilot: human-support minutes per successful first artifact",
     TESTS + "::TestReport", "green"),
    ("a person's name goes into the report", SCRIPT,
     'lines.append("| %s | %s | %d | %d | %s |" % (names[who],', 'lines.append("| %s | %s | %d | %d | %s |" % (who,',
     TESTS + "::TestReport", "red"),
    ("a pilot scales without a champion", SCRIPT,
     'and s["champions"] >= 1:', ":",
     TESTS + "::TestDecision", "red"),
    ("a pilot scales with 2 of 5", SCRIPT,
     'if s["succeeded"] * 5 >= s["count"] * 3', 'if s["succeeded"] * 5 >= s["count"] * 2',
     TESTS + "::TestDecision", "red"),
    ("a CLAUDE.md of any length passes", SCRIPT,
     "if len(lines) > CLAUDEMD_MAX:", "if False:",
     TESTS + "::TestPaths", "red"),
    ("boost overwrites the person's own skill", SCRIPT,
     "            if os.path.exists(path):\n                print(say(words, \"kept\", path=path))\n                continue\n",
     "",
     TESTS + "::TestBoost", "red"),
    ("an agents row without an https page passes", SCRIPT,
     'if not str(r.get("url", "")).startswith("https://"):', "if False:",
     TESTS + "::TestAgents", "red"),
    ("an API key goes unnoticed by detect", SCRIPT,
     'notes.append("api_key")', "pass",
     TESTS + "::TestAgents", "red"),
    ("a stopped person counts as further along", SCRIPT,
     '            p["stage"] = "stopped"\n', '            pass\n',
     TESTS + "::TestJournal", "red"),
    # the daily cards (teamcall lesson)
    ("control: a lesson comment reworded", SCRIPT,
     "# the pilot's four weeks of working days", "# four weeks of the pilot's working days",
     LESSONS + "::TestCards", "green"),
    ("the door opens to any host", SCRIPT,
     "if not host or host.group(1) not in SEND_HOSTS:", "if not host:",
     LESSONS + "::TestDoor", "red"),
    ("a network error carries the token", SCRIPT,
     'reason = str(getattr(exc, "reason", exc)).replace(url, host.group(1))', 'reason = str(getattr(exc, "reason", exc))',
     LESSONS + "::TestDoor", "red"),
    ("an unsigned WhatsApp request reaches the journal", SCRIPT,
     'if not secret or not hmac.compare_digest(signed.encode("utf-8"), given.encode("utf-8")):', "if not secret:",
     LESSONS + "::TestWhatsApp", "red"),
    ("a press off the card is counted", SCRIPT,
     "if not button or not known or not 1 <= int(button.group(1)) <= CARDS:", "if not button or not known:",
     LESSONS + "::TestTelegram", "red"),
    ("a person who said stop still gets cards", SCRIPT,
     'if key[0] in channels and state["active"])', "if key[0] in channels)",
     LESSONS + "::TestTelegram", "red"),
    ("the same card goes twice a day", SCRIPT,
     "if (day and day in have) or (not day and tried):", "if day and day in have:",
     LESSONS + "::TestOwnPace", "red"),
    ("a late joiner gets the pilot's card of the day", SCRIPT,
     "n = day or next_card(have)", "n = day or (card_day(start, today) if start else next_card(have))",
     LESSONS + "::TestOwnPace", "red"),
    ("a plan written again restarts the pilot", SCRIPT,
     "else plan_start(read_journal(args.folder)) or datetime.date.today())", "else datetime.date.today())",
     LESSONS + "::TestOwnPace", "red"),
    ("the first scheduled run of the day keeps quiet about who has not joined", SCRIPT,
     "        if first_run and missing:\n", "        if False:\n",
     LESSONS + "::TestOwnPace", "red"),
    ("a scheduled run that sent nothing fills the log", SCRIPT,
     'if args.at and not any(row["sent"] or row["failed"] for row in counts.values()):', "if False:",
     LESSONS + "::TestOwnPace", "red"),
    ("a blocked bot keeps getting cards", SCRIPT,
     "if status == 403:", "if False:",
     LESSONS + "::TestTelegram", "red"),
    ("WhatsApp gets free-form buttons after the 24 hours", SCRIPT,
     'how = "buttons" if now - state["at"] < WINDOW_SECONDS else "template"', 'how = "buttons"',
     LESSONS + "::TestWhatsApp", "red"),
    ("a name goes into the cards' part of the report", SCRIPT,
     'lines.append("| %s | %s |" % (names[who],', 'lines.append("| %s | %s |" % (who,',
     LESSONS + "::TestReport", "red"),
    ("skip counts over done", SCRIPT,
     '"skip": "skip" in got and "done" not in got,', '"skip": "skip" in got,',
     LESSONS + "::TestReport", "red"),
    ("the plan's start is not written for the cards", SCRIPT,
     'if write_out(args, words, "charter_file", text):', "if False:",
     LESSONS + "::TestCards", "red"),
    ("the WhatsApp note carries the lesson text", SCRIPT,
     '[{"type": "text", "text": "%d/%d" % (n, CARDS)}]', '[{"type": "text", "text": text}]',
     LESSONS + "::TestWhatsApp", "red"),
    ("a card Meta did not deliver counts as sent", SCRIPT,
     'if e["kind"] == "lesson_sent" and e.get("msg") and e["msg"] in lost:', "if False:",
     LESSONS + "::TestWhatsApp", "red"),
    ("Meta's failed status is not read", SCRIPT,
     'if status != "failed" or e is None or msg in marked:', "if True:",
     LESSONS + "::TestWhatsApp", "red"),
    ("done on WhatsApp gets no reply", SCRIPT,
     '                whatsapp_reply(post, conf, whatsapp_text(chat, say(words_for(got[2]), "lesson_ack_" + got[0])))\n',
     "                pass\n",
     LESSONS + "::TestWhatsApp", "red"),
    ("Meta's move of the template is not said", SCRIPT,
     "template_moved(words_for(None), moves)", "None",
     LESSONS + "::TestWhatsApp", "red"),
    ("the TLS handshake is left out of the connection's thread", SCRIPT,
     "                handshake()\n", "                pass\n",
     LESSONS + "::TestWhatsApp", "red"),
    ("a Python without certificates fails the messengers", SCRIPT,
     "if not paths.cafile and not paths.capath and os.path.isfile(SYSTEM_CERTS):", "if False:",
     LESSONS + "::TestDoor", "red"),
    ("a settings file from Windows PowerShell is not read", SCRIPT,
     r'if raw.startswith((b"\xff\xfe", b"\xfe\xff")):', "if False:",
     LESSONS + "::TestSettingsAndSchedule", "red"),
    ("cron starts the cards on the hour, not at --at", SCRIPT,
     "    if not minute:\n", "    if True:\n",
     LESSONS + "::TestSettingsAndSchedule", "red"),
    ("a receiver of an unused messenger writes an error every 5 minutes", SCRIPT,
     "if args.if_set and not ready.get(args.action, True):", "if False:",
     LESSONS + "::TestSettingsAndSchedule", "red"),
    ("a Telegram request without the bot's secret reaches the journal", SCRIPT,
     'if not token or not hmac.compare_digest(telegram_secret(token).encode("utf-8"), given.encode("utf-8")):',
     "if not token:",
     LESSONS + "::TestTelegramWebhook", "red"),
    ("an update Telegram brings again is taken twice", SCRIPT,
     'if msg not in {e.get("msg") for e in entries if e.get("msg")}:', "if True:",
     LESSONS + "::TestTelegramWebhook", "red"),
    ("pull asks Telegram while the webhook has the presses", SCRIPT,
     "        if hooked:\n            raise Problem(", "        if False:\n            raise Problem(",
     LESSONS + "::TestTelegramWebhook", "red"),
    ("serve for Telegram alone still demands the WhatsApp settings", SCRIPT,
     "        if not hooked:\n            for key in", "        if True:\n            for key in",
     LESSONS + "::TestTelegramWebhook", "red"),
    ("the launcher (sh) takes the first version folder, not the newest", SCRIPT,
     """ || [ "$(printf '%s\\n%s\\n' "$best" "$key" | sort | tail -n 1)" != "$best" ]""", "",
     LESSONS + "::TestLauncher", "red"),
    ("the launcher (sh) runs a version Claude Code has orphaned", SCRIPT,
     ' && [ ! -e "${r}.orphaned_at" ] || continue', " || continue",
     LESSONS + "::TestLauncher", "red"),
    ("the launcher (Python) takes the oldest version", SCRIPT,
     "return max(found, key=version) if found else FALLBACK", "return min(found, key=version) if found else FALLBACK",
     LESSONS + "::TestLauncher", "red"),
    ("the launcher (Python) runs a version Claude Code has orphaned", SCRIPT,
     ' and not os.path.exists(os.path.join(root, ".orphaned_at")):', ":",
     LESSONS + "::TestLauncher", "red"),
    ("the launcher (Python) opens the log for a run that says nothing", SCRIPT,
     "self.path, self.head, self.fh = path, head, None",
     'self.path, self.head, self.fh = path, head, open(path, "a", encoding="utf-8")',
     LESSONS + "::TestLauncher", "red"),
    ("the launcher (sh) writes no time line", SCRIPT,
     "'NR == 1 { print head >> file } { print >> file; fflush(file) }'", "'{ print >> file; fflush(file) }'",
     LESSONS + "::TestLauncher", "red"),
    ("a WhatsApp user id goes out as a number", SCRIPT,
     'return {"to": chat} if chat.isdigit() else {"recipient": chat}', 'return {"to": chat}',
     LESSONS + "::TestWhatsApp", "red"),
    ("a message without the number is read without its user id", SCRIPT,
     'user_id if USER_ID.fullmatch(user_id) else ""', '""',
     LESSONS + "::TestWhatsApp", "red"),
    ("the user id alone does not find the person's chat", SCRIPT,
     "            if channel == \"whatsapp\" and user_id in (chat, state[\"user_id\"]):\n",
     "            if False:\n",
     LESSONS + "::TestWhatsApp", "red"),
    ("a message that carries both does not keep the user id", SCRIPT,
     'note = {"user_id": user_id} if user_id else {}', "note = {}",
     LESSONS + "::TestWhatsApp", "red"),
    ("a messenger without its settings stops every card", SCRIPT,
     "    counts, failed = {}, []\n    for (channel, chat), state in chats:\n",
     "    counts, failed = {}, []\n    for channel in sorted({key[0] for key, _state in chats}):\n"
     "        if missing_setting(conf, channel):\n            raise Problem(missing_setting(conf, channel))\n"
     "    for (channel, chat), state in chats:\n",
     LESSONS + "::TestSettingsAndSchedule", "red"),
    ("an invite says nothing of a missing setting", SCRIPT,
     "    missing = missing_setting(conf, channel)\n", '    missing = ""\n',
     LESSONS + "::TestSettingsAndSchedule", "red"),
    ("serve with its own certificate listens only on 127.0.0.1", SCRIPT,
     'host = args.host or ("0.0.0.0" if args.cert else "127.0.0.1")', 'host = args.host or "127.0.0.1"',
     LESSONS + "::TestWhatsApp", "red"),
)


def digest(root):
    """sha256 of every file under root (junk folders left out), keyed by relative path."""
    out = {}
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in names:
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                out[os.path.relpath(path, root)] = hashlib.sha256(handle.read()).hexdigest()
    return out


def run_one(tmp, n, mutation):
    """-> ("red" | "green" | "error", detail)."""
    _name, rel, old, new, tests, _expect = mutation
    copy = os.path.join(tmp, "m%02d" % n)
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(*SKIP))
    target = os.path.join(copy, rel)
    with open(target, encoding="utf-8") as handle:
        text = handle.read()
    if text.count(old) != 1:
        return "error", "%r is in %s %d times, not once" % (old, rel, text.count(old))
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(text.replace(old, new, 1))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", tests],
                              cwd=copy, env=env, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "error", repr(exc)
    last = (done.stdout.strip().splitlines() or [""])[-1]
    if done.returncode == 0:
        return "green", last
    if done.returncode == 1:
        return "red", last
    return "error", "pytest exit %d: %s" % (done.returncode, (done.stdout + done.stderr).strip()[-300:])


def main():
    before = digest(ROOT)
    bad = 0
    tmp = tempfile.mkdtemp(prefix="teamcall-mutate-")
    try:
        for n, mutation in enumerate(MUTATIONS):
            name, expect = mutation[0], mutation[5]
            outcome, detail = run_one(tmp, n, mutation)
            if outcome == expect:
                print("ok   %s: %s as expected (%s)" % (name, expect, detail))
            else:
                print("BAD  %s: expected %s, got %s (%s)" % (name, expect, outcome, detail))
                bad += 1
            after = digest(ROOT)
            if after != before:
                print("BAD  the plugin's own files changed during '%s'" % name)
                bad += 1
                before = after
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("misbehaving: %d" % bad)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
