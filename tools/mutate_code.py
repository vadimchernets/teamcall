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
