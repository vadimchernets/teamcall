#!/usr/bin/env python3
"""teamcall: move a company's people from the chat window to a terminal agent in 30 days, and measure it.

    teamcall.py plan      --company NAME [--people 5] [--target 30] [--start DATE] [--champion WHO] [--sponsor WHO]
    teamcall.py fast      --person WHO [--os mac|windows|linux] [--task TEXT] [--seat TEXT]
    teamcall.py champion  --person WHO
    teamcall.py boost     --name NAME --task TEXT          (termboost: the same task in the app and in the terminal,
                                                            then again with one command)
    teamcall.py claudemd  FILE                             (a CLAUDE.md the agent reads at every start: <= 100 lines)
    teamcall.py log       add --person WHO --stage STAGE [--minutes N] [--help-minutes N] [--blocker TEXT]
                              [--artifact TEXT] [--date DATE]
    teamcall.py log       show
    teamcall.py measure   --person WHO --task TEXT [--before-min N] [--after-min N] [--quality TEXT]
                          [--coverage-before N] [--coverage-after N] [--repeatable] [--capability TEXT] [--risk TEXT]
    teamcall.py report    [--days 30]                       (the pilot report, no personal names in it)
    teamcall.py decide    [--days 30] [--max-help 60]       (one page: scale, fix and repeat, or stop)
    teamcall.py move      [--start DATE]                    (the 30-day plan of moving people, program by program)
    teamcall.py agents    [--seat TEXT]                     (which seat already pays for which terminal agent)
    teamcall.py detect                                      (which of those agents are on this computer)
    teamcall.py lesson    card | invite | send | pull | serve | template | schedule
                          (one short card a day in Telegram or WhatsApp: how to lead an agent and approve its steps;
                           the buttons done / show me / skip go into the journal and the report)

Common options: --folder DIR (the company's folder, default the current one), --lang en|es|pt|ru|uk, --print
(print instead of writing a file). Every file it writes goes into --folder; the journal is
teamcall-journal.jsonl there. Python standard library only. Only `lesson` talks to the network, and only to the
Telegram Bot API and the WhatsApp Cloud API, with the company's own token; everything else stays on this computer.
"""
import argparse
import datetime
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
LANG_DIR = os.path.join(ROOT, "lang")
AGENTS = os.path.join(ROOT, "data", "agents.json")
LANGS = ("en", "es", "pt", "ru", "uk")
JOURNAL = "teamcall-journal.jsonl"
POLICY_NAME = "company-ai-policy.json"

# The stages of one person's move, in order. A person's stage is the furthest one the journal holds for them.
STAGES = ("invited", "installed", "signed_in", "first_task", "first_artifact", "weekly", "champion", "stopped")
SUCCESS = ("first_artifact", "weekly", "champion")
# The six measurements of a pilot (the owner's pilot plan of 19.09.2026, "the format of the result").
MEASURES = ("time", "quality", "coverage", "repeatable", "capability", "risk")
# The 20-minute fast path and the 5-hour champion path: (step key, minutes).
FAST_STEPS = (("fast_install", 3), ("fast_sign_in", 2), ("fast_first_task", 7), ("fast_claudemd", 4), ("fast_repeat", 4))
CHAMPION_STEPS = (("ch_plan_mode", 45), ("ch_claudemd", 45), ("ch_skills", 60), ("ch_second_opinion", 45),
                  ("ch_remote", 30), ("ch_unblock", 45), ("ch_measure", 30))
CLAUDEMD_MAX = 100
INSTALL = {
    "mac": "curl -fsSL https://claude.ai/install.sh | bash",
    "linux": "curl -fsSL https://claude.ai/install.sh | bash",
    "windows": "irm https://claude.ai/install.ps1 | iex",
}
# Per-program rules (gatecall enforces them; teamcall says them when it lists the program).
RULES = ("copy_only_prepaid", "training_only", "no_blanket_permission")
# Pilot sizes: one champion for every this many people after the first five.
PEOPLE_PER_CHAMPION = 8
MANAGED_DIRS = {
    "darwin": "/Library/Application Support/ClaudeCode",
    "linux": "/etc/claude-code",
    "win32": "C:\\Program Files\\ClaudeCode",
}


class Problem(Exception):
    """Input teamcall cannot use. Printed as one line; exit 2."""


# ---------------------------------------------------------------- words ------------------------

def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        raise Problem("cannot read %s %s: %s" % (what, path, exc.strerror))
    except ValueError as exc:
        raise Problem("%s %s is not JSON: %s" % (what, path, exc))


def lang_words(code):
    words = load_json(os.path.join(LANG_DIR, "en.json"), "the dictionary")
    if code != "en":
        words = dict(words, **load_json(os.path.join(LANG_DIR, "%s.json" % code), "the dictionary"))
    return words


def policy_paths(cwd):
    """company-ai-policy.json, the binding copy first (the same order as gatecall and billcall)."""
    out = []
    managed = MANAGED_DIRS.get(sys.platform)
    if managed:
        out.append(os.path.join(managed, POLICY_NAME))
    if os.environ.get("COMPANY_AI_POLICY"):
        out.append(os.environ["COMPANY_AI_POLICY"])
    out += [os.path.join(cwd, POLICY_NAME), os.path.join(cwd, ".claude", POLICY_NAME),
            os.path.join(os.path.expanduser("~"), ".claude", POLICY_NAME)]
    return out


def read_policy(cwd):
    for path in policy_paths(cwd):
        if os.path.isfile(path):
            data = load_json(path, "the company policy")
            if not isinstance(data, dict):
                raise Problem("%s must hold one JSON object" % path)
            return data
    return {}


def pick_lang(asked, policy, env=None):
    env = os.environ if env is None else env
    for code in (asked, (policy or {}).get("language"), env.get("TEAMCALL_LANG")):
        if code in LANGS:
            return code
    return "en"


def say(words, key, **values):
    text = words.get(key, key)
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        return text


# ---------------------------------------------------------------- dates and names --------------

def parse_date(text, what="date"):
    if text is None:
        return datetime.date.today()
    try:
        return datetime.date.fromisoformat(str(text))
    except ValueError:
        raise Problem("%s must be YYYY-MM-DD, not %r" % (what, text))


def slug(text):
    """A file-name part from a person's or a task's name: letters of any script, digits and dashes."""
    out = re.sub(r"[^\w]+", "-", str(text).strip().lower(), flags=re.UNICODE).strip("-_")
    return out[:40] or "x"


def write_out(args, words, file_key, text, **name_values):
    if args.print:
        sys.stdout.write(text)
        return None
    os.makedirs(args.folder, exist_ok=True)
    path = os.path.join(args.folder, say(words, file_key, **name_values))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(say(words, "wrote", path=path))
    return path


# ---------------------------------------------------------------- plan: the pilot charter ------

def waves(people, target):
    """Pilot waves from the first people to the target: 5 -> about 15 -> target, each wave led by champions.

    -> list of (week, people at the end of that week, champions needed)."""
    if people < 1 or target < people:
        raise Problem("--people must be at least 1 and --target at least --people")
    middle = min(target, max(people, (people + target) // 2))
    plan = [(1, people), (2, people), (3, middle), (4, target)]
    return [(week, n, max(1, -(-(n - people) // PEOPLE_PER_CHAMPION)) if n > people else 1) for week, n in plan]


def charter_text(words, company, people, target, start, champion, sponsor, policy):
    end = start + datetime.timedelta(days=30)
    lines = ["# %s" % say(words, "charter_title", company=company), ""]
    lines += [say(words, "charter_promise", people=people, target=target), ""]
    lines += ["## %s" % say(words, "charter_dates"), "",
              "- %s: %s" % (say(words, "charter_start"), start.isoformat()),
              "- %s: %s" % (say(words, "charter_end"), end.isoformat()),
              "- %s: %s" % (say(words, "charter_sponsor"), sponsor or say(words, "to_name")),
              "- %s: %s" % (say(words, "charter_champion"), champion or say(words, "to_name")), ""]
    lines += ["## %s" % say(words, "charter_waves"), "",
              "| %s | %s | %s |" % (say(words, "col_week"), say(words, "col_people"), say(words, "col_champions")),
              "|---|---|---|"]
    for week, n, champs in waves(people, target):
        lines.append("| %d | %d | %d |" % (week, n, champs))
    lines += ["", say(words, "charter_waves_how", per=PEOPLE_PER_CHAMPION), ""]
    lines += ["## %s" % say(words, "charter_goal"), "",
              say(words, "charter_goal_text", goal=max(1, (people * 3 + 4) // 5), people=people), "",
              say(words, "charter_key_metric"), ""]
    lines += ["## %s" % say(words, "charter_measures"), ""]
    for m in MEASURES:
        lines.append("- **%s** — %s" % (say(words, "m_" + m), say(words, "m_%s_example" % m)))
    lines += ["", "## %s" % say(words, "charter_setup"), ""]
    red = (policy or {}).get("red_paths") or []
    allowed = (policy or {}).get("allowed_providers") or []
    for key in ("setup_devices", "setup_accounts", "setup_data", "setup_folders", "setup_review",
                "setup_install", "setup_contact", "setup_actions", "setup_retention", "setup_lessons"):
        lines.append("- %s" % say(words, key))
    if red:
        lines.append("- %s %s" % (say(words, "setup_red_from_policy"), ", ".join("`%s`" % p for p in red)))
    if allowed:
        lines.append("- %s %s" % (say(words, "setup_providers_from_policy"), ", ".join(allowed)))
    lines += ["", "## %s" % say(words, "charter_company_gives"), ""]
    for key in ("gives_sponsor", "gives_people", "gives_devices", "gives_payer", "gives_measure", "gives_case"):
        lines.append("- %s" % say(words, key))
    lines += ["", say(words, "charter_next"), ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- the fast path and the champion --

def fast_text(words, person, os_name, task, seat):
    total = sum(m for _, m in FAST_STEPS)
    lines = ["# %s" % say(words, "fast_title", person=person, minutes=total), "",
             say(words, "fast_intro", seat=seat or say(words, "fast_seat_default")), ""]
    for n, (key, minutes) in enumerate(FAST_STEPS, 1):
        lines.append("## %d. %s (%s)" % (n, say(words, key), say(words, "minutes", n=minutes)))
        lines.append("")
        lines.append(say(words, key + "_how", install=INSTALL[os_name], task=task or say(words, "fast_task_default"),
                         max=CLAUDEMD_MAX))
        lines.append("")
    lines += [say(words, "fast_log", person=person), ""]
    return "\n".join(lines)


def champion_text(words, person):
    total = sum(m for _, m in CHAMPION_STEPS)
    lines = ["# %s" % say(words, "champion_title", person=person, hours=total // 60), "",
             say(words, "champion_intro", per=PEOPLE_PER_CHAMPION), ""]
    for n, (key, minutes) in enumerate(CHAMPION_STEPS, 1):
        lines += ["## %d. %s (%s)" % (n, say(words, key), say(words, "minutes", n=minutes)), "",
                  say(words, key + "_how"), ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- termboost ------------------------

def boost_files(words, name, task):
    """termboost: the same task once in the app and once in the terminal, then again with one command.

    -> {relative path: text}: a project skill the person repeats as /<name> (or `claude "/<name>"` on a schedule),
    and a side-by-side card."""
    name = slug(name)
    skill = "\n".join([
        "---",
        "name: %s" % name,
        "description: %s" % say(words, "boost_skill_description", task=task.replace("\n", " ")),
        "---",
        "",
        say(words, "boost_skill_body", task=task),
        "",
    ])
    card = "\n".join([
        "# %s" % say(words, "boost_title", name=name), "",
        "| %s | %s |" % (say(words, "boost_in_app"), say(words, "boost_in_terminal")),
        "|---|---|",
        "| %s | `claude` → %s |" % (say(words, "boost_app_1"), say(words, "boost_term_1")),
        "| %s | %s |" % (say(words, "boost_app_2", task=task), say(words, "boost_term_2", task=task)),
        "| %s | `/%s` |" % (say(words, "boost_app_3"), name),
        "", say(words, "boost_schedule", name=name), "",
    ])
    return {os.path.join(".claude", "skills", name, "SKILL.md"): skill,
            say(words, "boost_file", name=name): card}


def claudemd_problems(text):
    """A CLAUDE.md the agent reads at every start: short direct instructions, at most CLAUDEMD_MAX lines."""
    lines = text.splitlines()
    out = []
    if len(lines) > CLAUDEMD_MAX:
        out.append(("too_long", len(lines)))
    if not text.strip():
        out.append(("empty", 0))
    return out


# ---------------------------------------------------------------- the journal --------------------

def journal_path(folder):
    return os.path.join(folder, JOURNAL)


def read_journal(folder):
    path = journal_path(folder)
    out = []
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                raise Problem("%s, line %d is not JSON" % (path, number))
            if isinstance(entry, dict):
                out.append(entry)
    return out


def add_entry(folder, entry):
    os.makedirs(folder, exist_ok=True)
    with open(journal_path(folder), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def people_state(entries, until=None):
    """-> {person: {"stage", "first", "artifact_day", "minutes", "help", "blockers", "artifacts"}}."""
    out = {}
    for e in entries:
        if e.get("kind") != "step":
            continue
        day = parse_date(e.get("date"), "journal date")
        if until and day > until:
            continue
        who = e.get("person")
        p = out.setdefault(who, {"stage": "invited", "first": day, "artifact_day": None, "minutes": 0,
                                 "help": 0, "blockers": [], "artifacts": []})
        p["first"] = min(p["first"], day)
        stage = e.get("stage")
        if stage not in STAGES:
            raise Problem("journal stage %r is not one of %s" % (stage, ", ".join(STAGES)))
        # the furthest stage reached; "stopped" holds until a later step shows the person went on
        if stage == "stopped":
            p["stage"] = "stopped"
        else:
            p["best"] = max(p.get("best", 0), STAGES.index(stage))
            p["stage"] = STAGES[p["best"]]
        if stage in SUCCESS and (p["artifact_day"] is None or day < p["artifact_day"]):
            p["artifact_day"] = day
        p["minutes"] += int(e.get("minutes") or 0)
        p["help"] += int(e.get("help_minutes") or 0)
        if e.get("blocker"):
            p["blockers"].append(e["blocker"])
        if e.get("artifact"):
            p["artifacts"].append(e["artifact"])
    return out


def pseudonyms(people):
    """Person names never enter the report: P1, P2, ... in the order they first appear."""
    return {who: "P%d" % n for n, who in enumerate(sorted(people, key=lambda w: (people[w]["first"], str(w))), 1)}


def summary(entries, until=None):
    people = people_state(entries, until)
    succeeded = [w for w, p in people.items() if p["artifact_day"] is not None]
    help_total = sum(p["help"] for p in people.values())
    days = sorted((p["artifact_day"] - p["first"]).days for p in people.values() if p["artifact_day"] is not None)
    return {
        "people": people,
        "count": len(people),
        "succeeded": len(succeeded),
        "stopped": sum(1 for p in people.values() if p["stage"] == "stopped"),
        "champions": sum(1 for p in people.values() if p["stage"] == "champion"),
        "help_total": help_total,
        # the key metric of the pilot: human-support minutes per successful first artifact
        "help_per_artifact": (help_total / len(succeeded)) if succeeded else None,
        "median_days": days[len(days) // 2] if days else None,
    }


def decision(s, max_help):
    """scale / repeat / stop, from the journal alone.

    scale: at least 3 of every 5 people reached a first artifact, the support it took stays within max_help minutes
    per artifact, and someone is a champion. stop: nobody reached a first artifact. Anything else: fix and repeat."""
    if s["count"] == 0 or s["succeeded"] == 0:
        return "stop"
    if s["succeeded"] * 5 >= s["count"] * 3 and s["help_per_artifact"] <= max_help and s["champions"] >= 1:
        return "scale"
    return "repeat"


def report_text(words, entries, until, max_help=60):
    s = summary(entries, until)
    names = pseudonyms(s["people"])
    lines = ["# %s" % say(words, "report_title"), "", say(words, "report_no_names"), "",
             "## %s" % say(words, "report_numbers"), "",
             "- %s: %d" % (say(words, "report_people"), s["count"]),
             "- %s: %d" % (say(words, "report_succeeded"), s["succeeded"]),
             "- %s: %d" % (say(words, "report_stopped"), s["stopped"]),
             "- %s: %d" % (say(words, "report_champions"), s["champions"]),
             "- **%s**: %s" % (say(words, "report_key_metric"),
                               "%.0f" % s["help_per_artifact"] if s["help_per_artifact"] is not None else "—"),
             "- %s: %s" % (say(words, "report_median_days"),
                           s["median_days"] if s["median_days"] is not None else "—"), "",
             "## %s" % say(words, "report_funnel"), "",
             "| %s | %s |" % (say(words, "col_stage"), say(words, "col_people")), "|---|---|"]
    for stage in STAGES:
        n = sum(1 for p in s["people"].values() if p["stage"] == stage)
        lines.append("| %s | %d |" % (say(words, "stage_" + stage), n))
    lines += ["", "## %s" % say(words, "report_people_table"), "",
              "| %s | %s | %s | %s | %s |" % (say(words, "col_who"), say(words, "col_stage"), say(words, "col_minutes"),
                                              say(words, "col_help"), say(words, "col_blockers")),
              "|---|---|---|---|---|"]
    for who in sorted(s["people"], key=lambda w: names[w]):
        p = s["people"][who]
        lines.append("| %s | %s | %d | %d | %s |" % (names[who], say(words, "stage_" + p["stage"]), p["minutes"],
                                                     p["help"], "; ".join(p["blockers"]) or "—"))
    lines += ["", "## %s" % say(words, "report_measures"), "",
              "| %s | %s | %s |" % (say(words, "col_who"), say(words, "col_task"), " | ".join(say(words, "m_" + m)
                                                                                           for m in MEASURES)),
              "|---|---|" + "---|" * len(MEASURES)]
    measured = [e for e in entries if e.get("kind") == "measure"]
    for e in measured:
        cells = [measure_cell(words, e, m) for m in MEASURES]
        lines.append("| %s | %s | %s |" % (names.get(e.get("person"), "—"), e.get("task", ""), " | ".join(cells)))
    if not measured:
        lines.append("| — | %s |%s" % (say(words, "report_no_measures"), " — |" * len(MEASURES)))
    # the daily cards; a person who only takes the cards gets the next pseudonym after the people of the journal
    cards, lesson_people, first = lessons_summary(entries, until)
    for who in sorted((w for w in lesson_people if w not in names), key=lambda w: (first[w], str(w))):
        names[who] = "P%d" % (len(names) + 1)
    lines += [""] + lessons_text(words, cards, lesson_people, names)
    lines += [say(words, "report_decision", decision=say(words, "decision_" + decision(s, max_help))), ""]
    return "\n".join(lines)


def measure_cell(words, e, m):
    if m == "time":
        b, a = e.get("before_min"), e.get("after_min")
        return say(words, "cell_time", before=b, after=a) if b is not None and a is not None else "—"
    if m == "coverage":
        b, a = e.get("coverage_before"), e.get("coverage_after")
        return say(words, "cell_coverage", before=b, after=a) if b is not None and a is not None else "—"
    if m == "repeatable":
        return say(words, "yes") if e.get("repeatable") else say(words, "no")
    return e.get(m) or "—"


def decide_text(words, entries, until, max_help):
    s = summary(entries, until)
    d = decision(s, max_help)
    lines = ["# %s" % say(words, "decide_title"), "",
             "**%s**" % say(words, "decision_" + d), "",
             say(words, "decide_why_" + d, succeeded=s["succeeded"], count=s["count"], champions=s["champions"],
                 help="%.0f" % s["help_per_artifact"] if s["help_per_artifact"] is not None else "—", max=max_help), "",
             "## %s" % say(words, "decide_next"), "", say(words, "decide_next_" + d), ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- agents and detect -------------

def load_agents(path=AGENTS):
    doc = load_json(path, "the agents table")
    rows = doc.get("agents") if isinstance(doc, dict) else None
    if not isinstance(rows, list) or not rows:
        raise Problem("%s holds no agents" % path)
    return rows


def agents_problems(rows):
    """Every row names its page (https) and its day, and a rule from the known list."""
    out = []
    seen = set()
    for r in rows:
        rid = r.get("id")
        if not rid or rid in seen:
            out.append("%r: no id or a repeated id" % rid)
        seen.add(rid)
        if not str(r.get("url", "")).startswith("https://"):
            out.append("%s: no https url" % rid)
        try:
            datetime.date.fromisoformat(str(r.get("checked")))
        except ValueError:
            out.append("%s: checked is not a date" % rid)
        if r.get("status") not in ("official", "secondary"):
            out.append("%s: status %r" % (rid, r.get("status")))
        if r.get("rule") and r["rule"] not in RULES:
            out.append("%s: unknown rule %r" % (rid, r["rule"]))
        if not r.get("included_in"):
            out.append("%s: says nothing about what pays for it" % rid)
    return out


def agents_text(words, rows, seat=None):
    lines = ["# %s" % say(words, "agents_title"), "",
             "| %s | %s | %s | %s | %s |" % (say(words, "col_agent"), say(words, "col_paid_by"),
                                             say(words, "col_free"), say(words, "col_rule"), say(words, "col_source")),
             "|---|---|---|---|---|"]
    for r in rows:
        if seat and seat.lower() not in (r.get("included_in", "") + " " + r.get("company_seat", "")).lower():
            continue
        rule = say(words, "rule_" + r["rule"]) if r.get("rule") else "—"
        source = "%s (%s%s)" % (r["url"], r["checked"], ", " + say(words, "secondary") if r["status"] == "secondary" else "")
        lines.append("| %s | %s | %s | %s | %s |" % (r["name"], r["included_in"], r.get("free_path") or "—", rule, source))
    lines.append("")
    return "\n".join(lines)


def detect(rows, env=None, which=shutil.which, home=None):
    """-> list of (id, name, path or None), plus the sign-in note for Claude Code. Local only."""
    env = os.environ if env is None else env
    found = []
    for r in rows:
        path = None
        for b in r.get("binaries") or []:
            path = which(b)
            if path:
                break
        if r.get("binaries"):
            found.append((r["id"], r["name"], path))
    notes = []
    if env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_AUTH_TOKEN"):
        notes.append("api_key")
    base = env.get("ANTHROPIC_BASE_URL", "")
    if base and "api.anthropic.com" not in base:
        notes.append("base_url")
    for name in ("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "DISABLE_GROWTHBOOK"):
        if env.get(name):
            notes.append("traffic")
            break
    cfg = os.path.join(home or os.path.expanduser("~"), ".claude.json")
    try:
        with open(cfg, encoding="utf-8") as fh:
            signed = "oauthAccount" in json.load(fh)
    except (OSError, ValueError):
        signed = False
    if signed:
        notes.append("signed_in")
    return found, notes


# ---------------------------------------------------------------- move: 30 days -----------------

def move_text(words, rows, start, found_ids):
    lines = ["# %s" % say(words, "move_title"), "", say(words, "move_intro"), ""]
    for week, key in ((1, "move_w1"), (2, "move_w2"), (3, "move_w3"), (4, "move_w4")):
        day = start + datetime.timedelta(days=7 * (week - 1))
        lines.append("- **%s** (%s): %s" % (say(words, "col_week") + " %d" % week, day.isoformat(), say(words, key)))
    lines += ["", "## %s" % say(words, "move_programs"), ""]
    for r in rows:
        mark = say(words, "installed_here") if r["id"] in found_ids else ""
        rule = (" — " + say(words, "rule_" + r["rule"])) if r.get("rule") else ""
        lines.append("- **%s** %s: %s%s" % (r["name"], mark, r["included_in"], rule))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- lesson: one card a day --------

# One short card on each working day, in the messenger the person already has: how to lead an agent and approve its
# steps. The company's own bot sends it, so the person installs nothing; the three buttons - done, show me, skip -
# come back into the journal, and the report counts them without names. Each chat goes through the cards at its own
# pace: card 1 on its first working day, then one a day, so a person who joins in week 3 or after the pilot still
# gets all of them in order, and a day the computer was off moves a card, never loses it.
CARDS = 20                                     # the pilot's four weeks of working days
ANSWERS = ("done", "show", "skip")
CHANNELS = ("telegram", "whatsapp")
LESSON_ACTIONS = ("card", "invite", "send", "pull", "serve", "template", "schedule", "webhook")
# Every journal entry about the cards carries one of these kinds; lesson_note writes no other.
LESSON_KINDS = ("plan", "lesson_invite", "lesson_chat", "lesson_sent", "lesson_answer", "lesson_seen", "lesson_stop",
                "lesson_offset", "lesson_undelivered", "lesson_webhook")
LESSON_COUNTS = ("sent", "done", "show", "skip", "silent")
# What one `lesson send` counts in each messenger.
SEND_COUNTS = ("sent", "had", "finished", "waiting", "failed")
# The only hosts teamcall ever sends to; the door (post_json) refuses any other.
SEND_HOSTS = ("api.telegram.org", "graph.facebook.com")
TELEGRAM_API = "https://api.telegram.org/bot"
WHATSAPP_API = "https://graph.facebook.com/"
WHATSAPP_VERSION = "v25.0"                     # the Graph API version of Meta's own examples, read on 2026-10-03
WHATSAPP_TEMPLATE = "teamcall_card"
WHATSAPP_LANGS = {"en": "en", "es": "es", "pt": "pt_BR", "ru": "ru", "uk": "uk"}
# WhatsApp takes free-form messages, buttons included, for 24 hours after the person's last message; five minutes are
# kept in hand. After them the company's approved template goes: a short note that the person's own card is ready,
# with one button that opens it. A note about the person's own subscription is utility in Meta's rules; lesson text in
# a template would make it marketing, which costs more and never reaches a +1 number. The tap opens the 24 hours, and
# the card follows with its three buttons.
WINDOW_SECONDS = 24 * 3600 - 300
BUTTON = re.compile(r"tc1:(\d{1,2}):(%s|open)" % "|".join(ANSWERS))
START = re.compile(r"/?start(?:\s+([A-Za-z0-9_-]{8,64}))?", re.I)
STOP = re.compile(r"/?stop", re.I)
CARD = re.compile(r"/?card", re.I)
# A person's business-scoped user id in WhatsApp: their country, a dot, then letters and digits (a parent id has one
# more part). Meta sends it with every message - and alone, without the number, for a person with a username whom the
# company has neither written to nor heard from for 30 days.
USER_ID = re.compile(r"[A-Z]{2}(?:\.[A-Za-z0-9]{1,128}){1,2}")
ENV_FILE = ".teamcall.env"
# A scheduled send gives cards from --at until this hour; a computer that wakes later leaves that card to the next
# working day, where it goes first.
LAST_HOUR = 20
# What `lesson schedule` writes into the company's folder: the launcher every schedule line names, and what its runs
# say. The two receivers keep a lock there each, so a schedule that starts them every 5 minutes runs one of each.
LAUNCHER = {"mac": "teamcall-run.sh", "linux": "teamcall-run.sh", "windows": "teamcall-run.py"}
RUN_LOG = "teamcall-schedule.log"
LOCKS = {"pull": "teamcall-pull.lock", "serve": "teamcall-serve.lock"}
# The system's list of certificates on a Mac and on most Linux systems: HTTPS uses it when Python has none of its own.
SYSTEM_CERTS = "/etc/ssl/cert.pem"


def card_day(start, day):
    """The card for `day`: its number among the pilot's working days, 1..CARDS; None on a weekend, before the start
    and after the last card."""
    if day < start or day.weekday() >= 5:
        return None
    n = sum(1 for i in range((day - start).days + 1) if (start + datetime.timedelta(days=i)).weekday() < 5)
    return n if n <= CARDS else None


def plan_start(entries):
    """The start of the latest `teamcall plan` in the journal, or None."""
    for e in reversed(entries):
        if e.get("kind") == "plan" and e.get("start"):
            return parse_date(e["start"], "the plan's start")
    return None


def pilot_start(entries, asked=None):
    """--start, else the start of the latest `teamcall plan` in the journal."""
    if asked:
        return parse_date(asked, "--start")
    start = plan_start(entries)
    if start is None:
        raise Problem("no pilot start: run `teamcall plan --start YYYY-MM-DD` first, or pass --start")
    return start


def card_parts(words, n):
    """-> (head, text, example) of card n; the example is what "show me" sends."""
    head = say(words, "lesson_head", n=n, total=CARDS, title=say(words, "card_%d_title" % n))
    return head, say(words, "card_%d_text" % n), say(words, "card_%d_show" % n)


def card_page(words, n):
    """Card n as the person sees it, to read it first (`lesson card`)."""
    head, text, example = card_parts(words, n)
    buttons = "   ".join("[%s]" % say(words, "lesson_" + a) for a in ANSWERS)
    return "\n".join(["# " + head, "", text, "", buttons, "", "> " + example, ""])


def digits(text):
    return re.sub(r"[^0-9]", "", str(text or ""))


def env_file(env):
    return env.get("TEAMCALL_ENV_FILE") or os.path.join(os.path.expanduser("~"), ENV_FILE)


def env_text(raw, path):
    """The settings file as text, in whatever a text editor or a shell wrote: UTF-8 with or without its mark, or the
    UTF-16 that `>` writes in Windows PowerShell 5.1."""
    try:
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16")
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Problem("%s is not UTF-8 or UTF-16 text: save it again as UTF-8" % path)


def lesson_env(env=None):
    """The company's messenger settings: TEAMCALL_* from the environment, else from ~/.teamcall.env (one
    TEAMCALL_NAME=value per line; the file stays readable by its owner only). teamcall never prints or writes a token."""
    env = os.environ if env is None else env
    path = env_file(env)
    out = {}
    if os.path.isfile(path):
        try:
            with open(path, "rb") as fh:
                lines = env_text(fh.read(), path).splitlines()
        except OSError as exc:
            raise Problem("cannot read %s: %s" % (path, exc.strerror))
        for line in lines:
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):].strip()
            key, sep, value = line.partition("=")
            if sep and key.strip().startswith("TEAMCALL_"):
                out[key.strip()] = value.strip().strip("\"'")
    out.update((k, v) for k, v in env.items() if k.startswith("TEAMCALL_") and v)
    return out


def need(conf, key, what):
    if not conf.get(key):
        raise Problem("%s needs %s: put it into ~/%s or the environment (`teamcall lesson schedule` shows the lines)"
                      % (what, key, ENV_FILE))
    return conf[key]


def telegram_token(conf):
    token = need(conf, "TEAMCALL_TELEGRAM_TOKEN", "Telegram")
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token):
        raise Problem("TEAMCALL_TELEGRAM_TOKEN is not a bot token: BotFather gives it as digits:letters")
    return token


def whatsapp_phone_id(conf):
    phone_id = need(conf, "TEAMCALL_WHATSAPP_PHONE_ID", "WhatsApp")
    if not re.fullmatch(r"[0-9]+", phone_id):
        raise Problem("TEAMCALL_WHATSAPP_PHONE_ID is the id of the company's number in Meta's app: digits")
    return phone_id


def missing_setting(conf, channel):
    """What a card in `channel` still needs - the setting and where it goes, in one line - or "" when it can go."""
    try:
        if channel == "telegram":
            telegram_token(conf)
        else:
            whatsapp_phone_id(conf)
            need(conf, "TEAMCALL_WHATSAPP_TOKEN", "WhatsApp")
    except Problem as exc:
        return str(exc)
    return ""


def post_json(url, payload, headers=None, timeout=30):
    """The one door to the network: an HTTPS POST of JSON to the Telegram Bot API or the WhatsApp Cloud API.

    -> (HTTP status, the answer as a dict). The URL never goes into a message: a Telegram URL holds the token.
    The certificate is always checked. Python from python.org on a Mac has no list of certificates of its own until
    its Install Certificates step runs; then the system's list (SYSTEM_CERTS) checks it, so the cards go either way."""
    host = re.match(r"https://([a-z0-9.-]+)/", url)
    if not host or host.group(1) not in SEND_HOSTS:
        raise Problem("teamcall sends only to %s" % " and ".join(SEND_HOSTS))
    import ssl
    import urllib.error
    import urllib.request
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                     headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        paths = ssl.get_default_verify_paths()
        context = None
        if not paths.cafile and not paths.capath and os.path.isfile(SYSTEM_CERTS):
            context = ssl.create_default_context(cafile=SYSTEM_CERTS)
        with urllib.request.urlopen(request, timeout=timeout, context=context) as answer:
            return answer.status, json_answer(answer.read())
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:
            body = b""
        return exc.code, json_answer(body)
    except Exception as exc:                   # no answer at all: no connection, refused, timed out
        reason = str(getattr(exc, "reason", exc)).replace(url, host.group(1))
        raise Problem("cannot reach %s: %s" % (host.group(1), reason))


def json_answer(raw):
    """The messenger's answer as a dict; anything else becomes its first 200 characters."""
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        data = None
    return data if isinstance(data, dict) else {"description": raw[:200].decode("utf-8", "replace")}


def telegram(post, token, method, params, timeout=30):
    """One Bot API method -> (ok, its result or the error text, HTTP status)."""
    status, data = post(TELEGRAM_API + token + "/" + method, params, None, timeout)
    if data.get("ok"):
        return True, data.get("result"), status
    return False, str(data.get("description") or "HTTP %s" % status), status


def whatsapp(post, conf, path, payload):
    """One Cloud API request -> (ok, the answer, or the error text)."""
    version = conf.get("TEAMCALL_WHATSAPP_VERSION") or WHATSAPP_VERSION
    if not re.fullmatch(r"v\d+\.\d+", version):
        raise Problem("TEAMCALL_WHATSAPP_VERSION must look like %s" % WHATSAPP_VERSION)
    token = need(conf, "TEAMCALL_WHATSAPP_TOKEN", "WhatsApp")
    status, data = post(WHATSAPP_API + version + "/" + path, payload, {"Authorization": "Bearer " + token}, 30)
    error = data.get("error")
    if 200 <= status < 300 and not error:
        return True, data
    error = error if isinstance(error, dict) else {}
    return False, "%s%s" % (error.get("message") or data.get("description") or "HTTP %s" % status,
                            " (%s)" % error["code"] if error.get("code") else "")


def telegram_card(words, chat, n):
    """The card as a Bot API sendMessage: the text and three buttons under it."""
    head, text, _example = card_parts(words, n)
    buttons = [{"text": say(words, "lesson_" + a), "callback_data": "tc1:%d:%s" % (n, a)} for a in ANSWERS]
    return {"chat_id": chat, "text": "<b>%s</b>\n\n%s" % (html.escape(head, False), html.escape(text, False)),
            "parse_mode": "HTML", "reply_markup": {"inline_keyboard": [buttons]}}


def telegram_example(words, chat, n):
    head, _text, example = card_parts(words, n)
    return {"chat_id": chat, "text": "<b>%s</b>\n\n%s" % (html.escape(head, False), html.escape(example, False)),
            "parse_mode": "HTML"}


def whatsapp_to(chat):
    """Where a WhatsApp message goes: `to` the person's number, or `recipient` their user id - the chat of a person
    Meta named without a number (the Cloud API takes a user id as the address since July 2026)."""
    chat = str(chat)
    return {"to": chat} if chat.isdigit() else {"recipient": chat}


def whatsapp_card(words, lang, to, n, window_open, template):
    """Inside the 24 hours: the card with three reply buttons. After them: the company's approved template - the note
    that card n is ready, its one button carrying tc1:<n>:open, which brings the card itself."""
    head, text, _example = card_parts(words, n)
    message = dict({"messaging_product": "whatsapp", "recipient_type": "individual"}, **whatsapp_to(to))
    if window_open:
        buttons = [{"type": "reply", "reply": {"id": "tc1:%d:%s" % (n, a), "title": say(words, "lesson_" + a)}}
                   for a in ANSWERS]
        message.update(type="interactive", interactive={"type": "button", "body": {"text": "*%s*\n\n%s" % (head, text)},
                                                        "action": {"buttons": buttons}})
        return message
    components = [{"type": "body", "parameters": [{"type": "text", "text": "%d/%d" % (n, CARDS)}]},
                  {"type": "button", "sub_type": "quick_reply", "index": "0",
                   "parameters": [{"type": "payload", "payload": "tc1:%d:open" % n}]}]
    message.update(type="template", template={"name": template, "language": {"code": WHATSAPP_LANGS[lang]},
                                              "components": components})
    return message


def whatsapp_text(to, text):
    return dict({"messaging_product": "whatsapp", "recipient_type": "individual", "type": "text",
                 "text": {"body": text}}, **whatsapp_to(to))


def whatsapp_example(words, to, n):
    head, _text, example = card_parts(words, n)
    return whatsapp_text(to, "*%s*\n\n%s" % (head, example))


def whatsapp_templates(name=WHATSAPP_TEMPLATE):
    """The template in the five languages, as Meta takes it (POST /<business account id>/message_templates): created
    once, approved by Meta, then used for every card after the 24 hours. It is the short note that the person's own
    card {{1}} (3/20) is ready, with one button that opens it - no lesson text, so its content is plain to Meta and
    stays a note about the person's own subscription (utility); the card itself follows the tap."""
    out = []
    for code in LANGS:
        words = lang_words(code)
        out.append({"name": name, "language": WHATSAPP_LANGS[code], "category": "UTILITY", "components": [
            {"type": "BODY", "text": say(words, "lesson_template", n="{{1}}"),
             "example": {"body_text": [["1/%d" % CARDS]]}},
            {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": say(words, "lesson_open")}]}]})
    return out


def lesson_note(folder, entries, entry):
    """Into the journal, and into the entries already read, so the next message sees it. Only the kinds of
    LESSON_KINDS: the report and the cards read nothing else."""
    if entry.get("kind") not in LESSON_KINDS:
        raise Problem("teamcall writes no %r entry: the kinds are %s" % (entry.get("kind"), ", ".join(LESSON_KINDS)))
    add_entry(folder, entry)
    entries.append(entry)


def lesson_chats(entries):
    """-> {(channel, chat): {"person", "lang", "active", "at", "user_id"}}: who is behind each chat. The latest join or
    stop of a chat wins; "at" is the person's last message (WhatsApp's 24 hours run from it); "user_id" is the
    person's WhatsApp user id, once a message of theirs brought it."""
    out = {}
    for e in entries:
        kind = e.get("kind")
        key = (e.get("channel"), str(e.get("chat")))
        if kind == "lesson_chat":
            had = out.get(key, {})
            out[key] = {"person": e.get("person"), "lang": e.get("lang") if e.get("lang") in LANGS else None,
                        "active": True, "at": had.get("at", 0), "user_id": had.get("user_id", "")}
        if key in out and kind in ("lesson_chat", "lesson_answer", "lesson_seen", "lesson_stop"):
            out[key]["at"] = max(out[key]["at"], int(e.get("at") or 0))
            out[key]["user_id"] = str(e.get("user_id") or out[key]["user_id"])
            if kind == "lesson_stop":
                out[key]["active"] = False
    return out


def whatsapp_chat(entries, number, user_id):
    """The chat a WhatsApp message belongs to: the one that knows the person's user id, else the one of their number,
    else a new one - named by the number, or by the user id when Meta left the number out. A message that carries
    both links them: its entry keeps the user id, so the same person without the number later finds the same chat."""
    if user_id:
        for (channel, chat), state in lesson_chats(entries).items():
            if channel == "whatsapp" and user_id in (chat, state["user_id"]):
                return chat
    return number or user_id


def chat_progress(entries, channel, chat, today):
    """One chat's own way through the cards. -> (the cards that reached it, whether a card of the day went to it
    today, the card of the day that reached it today or None). A card sent again on request ("again") is no card of
    the day; a WhatsApp card Meta reported as undelivered did not reach the chat, so it is the chat's next card."""
    lost = {e.get("msg") for e in entries if e.get("kind") == "lesson_undelivered" and e.get("msg")}
    have, tried, today_card = set(), False, None
    for e in entries:
        if e.get("kind") != "lesson_sent" or (e.get("channel"), str(e.get("chat"))) != (channel, chat):
            continue
        card = int(e.get("card") or 0)
        reached = 1 <= card <= CARDS and not (e.get("msg") and e["msg"] in lost)
        if reached:
            have.add(card)
        if e.get("date") == today.isoformat() and not e.get("again"):
            tried = True
            today_card = card if reached else today_card
    return have, tried, today_card


def next_card(have):
    """The first card a chat lacks; None once it has them all."""
    return next((n for n in range(1, CARDS + 1) if n not in have), None)


def not_joined(entries):
    """The people whose invite link has not been tapped yet in its messenger."""
    joined = {(e.get("person"), e.get("channel")) for e in entries if e.get("kind") == "lesson_chat"}
    return sorted({str(e.get("person")) for e in entries
                   if e.get("kind") == "lesson_invite" and (e.get("person"), e.get("channel")) not in joined})


def take_text(folder, entries, channel, chat, text, at, msg, today, user_id=""):
    """A typed message: `start <code>` joins with an invite link, `start` alone comes back after a stop, `stop` ends
    the cards, `card` asks for the card of the day. -> (the word key to answer with or None, the person's language,
    "joined" / "stopped" / "card" / "wrote" - anything else from a person who takes the cards - / None). The entry it
    writes keeps the person's WhatsApp user id when the message carried one."""
    known = lesson_chats(entries).get((channel, chat))
    note = {"user_id": user_id} if user_id else {}
    lang = known["lang"] if known else None
    text = str(text or "").strip()
    start = START.fullmatch(text)
    if start:
        code = start.group(1)
        invite = None
        if code:
            invite = next((e for e in reversed(entries) if e.get("kind") == "lesson_invite"
                           and e.get("channel") == channel and e.get("code") == code), None)
            taken = any(e.get("kind") == "lesson_chat" and e.get("code") == code and str(e.get("chat")) != chat
                        for e in entries)
            if invite is None or taken:
                return "lesson_unknown_link", lang, None
        elif known is None:
            return "lesson_unknown_link", lang, None
        who = invite or known
        entry = dict({"kind": "lesson_chat", "person": who["person"], "channel": channel, "chat": chat,
                      "lang": who.get("lang"), "date": today.isoformat(), "at": at, "msg": msg}, **note)
        if code:
            entry["code"] = code
        lesson_note(folder, entries, entry)
        return "lesson_welcome", entry["lang"], "joined"
    if known and STOP.fullmatch(text):
        lesson_note(folder, entries, dict({"kind": "lesson_stop", "person": known["person"], "channel": channel,
                                           "chat": chat, "why": "asked", "date": today.isoformat(), "at": at,
                                           "msg": msg}, **note))
        return "lesson_bye", lang, "stopped"
    if known and channel == "whatsapp":        # any message opens WhatsApp's 24 hours again
        lesson_note(folder, entries, dict({"kind": "lesson_seen", "person": known["person"], "channel": channel,
                                           "chat": chat, "date": today.isoformat(), "at": at, "msg": msg}, **note))
    if known and known["active"]:
        return None, lang, "card" if CARD.fullmatch(text) else "wrote"
    return None, lang, None


def take_button(folder, entries, channel, chat, data, at, msg, today, user_id=""):
    """A card's button. -> (what was pressed - done, show or skip, or open: the button of the WhatsApp note, which
    brings the card itself -, the card, the person's language), or None for a press teamcall does not take: an
    unknown chat, a button that is none of these, or a press already in the journal. An answer goes into the journal
    and counts; open is kept as the person's message, which opens WhatsApp's 24 hours. Either keeps the person's
    WhatsApp user id when the press carried one."""
    button = BUTTON.fullmatch(str(data or ""))
    known = lesson_chats(entries).get((channel, chat))
    if not button or not known or not 1 <= int(button.group(1)) <= CARDS:
        return None
    if msg and any(e.get("kind") in ("lesson_answer", "lesson_seen") and e.get("msg") == msg for e in entries):
        return None
    card, answer = int(button.group(1)), button.group(2)
    entry = {"kind": "lesson_seen", "person": known["person"], "channel": channel, "chat": chat,
             "date": today.isoformat(), "at": at, "msg": msg}
    if user_id:
        entry["user_id"] = user_id
    if answer in ANSWERS:
        entry.update(kind="lesson_answer", card=card, answer=answer)
    lesson_note(folder, entries, entry)
    return answer, card, known["lang"]


def deliver(post, conf, channel, chat, words, lang, n, window_open):
    """Card n to one chat: in Telegram with its three buttons; in WhatsApp with them inside the 24 hours, else as the
    note that opens it. -> (ok, the answer or the error text, HTTP status, message id, "buttons" or "template").
    No connection, or a setting its messenger lacks, counts as not delivered - with the setting named: the card stays
    the chat's next one, and the chats of the other messenger still get theirs."""
    status, how, msg = 0, "buttons", ""
    try:
        if channel == "telegram":
            ok, result, status = telegram(post, telegram_token(conf), "sendMessage", telegram_card(words, chat, n))
            if ok and isinstance(result, dict):
                msg = str(result.get("message_id", ""))
        else:
            how = "buttons" if window_open else "template"
            template = conf.get("TEAMCALL_WHATSAPP_TEMPLATE") or WHATSAPP_TEMPLATE
            ok, result = whatsapp(post, conf, whatsapp_phone_id(conf) + "/messages",
                                  whatsapp_card(words, lang, chat, n, window_open, template))
            if ok:
                msg = str(((result.get("messages") or [{}])[0] or {}).get("id", ""))
    except Problem as exc:                     # no connection or no setting: this chat is not delivered, the others go
        ok, result = False, str(exc)
    return ok, result, status, msg, how


def note_sent(folder, entries, state, channel, chat, n, how, msg, today, again=False):
    entry = {"kind": "lesson_sent", "person": state["person"], "channel": channel, "chat": chat, "card": n, "as": how,
             "date": today.isoformat(), "msg": msg}
    if again:
        entry["again"] = True
    lesson_note(folder, entries, entry)


def not_delivered(folder, entries, state, channel, chat, status, today):
    """After a card that did not go. Telegram's 403: the person blocked the bot - no cards to that chat until /start."""
    if status == 403:
        lesson_note(folder, entries, {"kind": "lesson_stop", "person": state["person"], "channel": channel,
                                      "chat": chat, "why": "blocked", "date": today.isoformat()})


def send_card(post, conf, folder, entries, channel, chat, n, today, words_for, again):
    """Card n with its buttons to a chat whose person has just written: on WhatsApp their message opened the 24
    hours. A failure is printed, never raised. -> True when it went."""
    state = lesson_chats(entries).get((channel, chat))
    if not state or not state["active"]:
        return False
    code = state["lang"]
    ok, result, status, msg, how = deliver(post, conf, channel, chat, words_for(code), code or "en", n, True)
    if ok:
        note_sent(folder, entries, state, channel, chat, n, how, msg, today, again)
        return True
    print(say(words_for(None), "lesson_failed", channel=channel, person=state["person"], why=result))
    not_delivered(folder, entries, state, channel, chat, status, today)
    return False


def card_now(post, conf, folder, entries, channel, chat, today, words_for, asked, start=None):
    """The person wrote in the chat, so their card goes now. `card` (asked) brings the card of the day again, or the
    next one when none came today; any other message brings the next card on a working day when none reached the
    chat today - so a WhatsApp card whose note never arrived comes the moment the person writes. -> the card sent,
    or None."""
    have, _tried, today_card = chat_progress(entries, channel, chat, today)
    n = next_card(have)
    if asked:
        again = today_card is not None or n is None
        n = today_card or n or CARDS
    elif today_card or n is None or today.weekday() >= 5 or (start and not have and today < start):
        return None
    else:
        again = False
    return n if send_card(post, conf, folder, entries, channel, chat, n, today, words_for, again) else None


def telegram_update(post, conf, folder, entries, token, update, now, today, words_for, counts):
    """One update from Telegram - a press under a card, or a message in a private chat - into the journal and
    answered; `counts` ({"answers", "joined", "stopped"}) goes up by what it was."""
    press, message = update.get("callback_query"), update.get("message")
    if isinstance(press, dict):
        chat = str(((press.get("message") or {}).get("chat") or {}).get("id") or (press.get("from") or {}).get("id"))
        got = take_button(folder, entries, "telegram", chat, press.get("data"), now, "tg:%s" % press.get("id"), today)
        got = got if got and got[0] in ANSWERS else None
        words = words_for(got[2] if got else None)
        telegram(post, token, "answerCallbackQuery",
                 {"callback_query_id": press.get("id"), "text": say(words, "lesson_ack_" + got[0]) if got else ""})
        if got:
            counts["answers"] += 1
            if got[0] == "show":
                telegram(post, token, "sendMessage", telegram_example(words, chat, got[1]))
    elif isinstance(message, dict) and (message.get("chat") or {}).get("type", "private") == "private":
        chat = str((message.get("chat") or {}).get("id"))
        key, lang, change = take_text(folder, entries, "telegram", chat, message.get("text"),
                                      int(message.get("date") or now), "tg:u%s" % update.get("update_id"), today)
        if change in counts:
            counts[change] += 1
        if key:
            telegram(post, token, "sendMessage", {"chat_id": chat, "text": say(words_for(lang), key, stop="/stop",
                                                                               start="/start", card="/card")})
        if change == "card":
            card_now(post, conf, folder, entries, "telegram", chat, today, words_for, True)


def telegram_secret(token):
    """What Telegram puts into X-Telegram-Bot-Api-Secret-Token of every request it brings to `lesson serve`: made
    from the bot's token, so it needs no setting of its own and changes with the token."""
    return hmac.new(token.encode("utf-8"), b"teamcall telegram webhook", hashlib.sha256).hexdigest()


def telegram_hooked(entries):
    """Whether Telegram brings the presses to `lesson serve` (the latest `lesson webhook` set an address)."""
    hooks = [e for e in entries if e.get("kind") == "lesson_webhook" and e.get("channel") == "telegram"]
    return bool(hooks and hooks[-1].get("url"))


def telegram_webhook(headers, body, folder, conf, post, words_for, now=None, today=None):
    """One request from Telegram to `lesson serve` -> (HTTP status, text). Only a request carrying the bot's secret
    reaches the journal; an update Telegram brings again is taken once. Telegram keeps nothing waiting this way: a
    press on a weekend with the champion's computer off is counted the moment it is made."""
    token = conf.get("TEAMCALL_TELEGRAM_TOKEN", "")
    given = {str(k).lower(): str(v) for k, v in headers.items()}.get("x-telegram-bot-api-secret-token", "")
    if not token or not hmac.compare_digest(telegram_secret(token).encode("utf-8"), given.encode("utf-8")):
        return 403, "forbidden"
    try:
        update = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        update = None
    if not isinstance(update, dict):
        return 400, "not a Telegram update"
    entries = read_journal(folder)
    press = update.get("callback_query")
    msg = "tg:%s" % press.get("id") if isinstance(press, dict) else "tg:u%s" % update.get("update_id")
    if msg not in {e.get("msg") for e in entries if e.get("msg")}:
        telegram_update(post, conf, folder, entries, telegram_token(conf), update,
                        int(time.time()) if now is None else now, today or datetime.date.today(), words_for,
                        {"answers": 0, "joined": 0, "stopped": 0})
    return 200, "ok"


def telegram_pull(post, conf, folder, entries, wait, now, today, words_for):
    """The bot's updates since the last pull - joins, stops, `card` and the buttons pressed. With --wait the line
    stays open that many seconds (long polling), so "show me" is answered at once.
    -> {"answers", "joined", "stopped"}."""
    token = telegram_token(conf)
    wait = max(0, int(wait or 0))
    offset = max([int(e.get("offset") or 0) for e in entries
                  if e.get("kind") == "lesson_offset" and e.get("channel") == "telegram"] or [0])
    params = {"timeout": wait, "allowed_updates": ["message", "callback_query"]}
    if offset:
        params["offset"] = offset
    ok, updates, _status = telegram(post, token, "getUpdates", params, wait + 15)
    if not ok:
        raise Problem("telegram: %s" % updates)
    counts = {"answers": 0, "joined": 0, "stopped": 0}
    last = offset
    for update in updates if isinstance(updates, list) else []:
        if not isinstance(update, dict):
            continue
        last = max(last, int(update.get("update_id") or 0) + 1)
        telegram_update(post, conf, folder, entries, token, update, now, today, words_for, counts)
    if last != offset:
        lesson_note(folder, entries, {"kind": "lesson_offset", "channel": "telegram", "offset": last,
                                      "date": today.isoformat()})
    return counts


def hold_lock(folder, name):
    """One receiver per company folder. -> the lock file while this process holds it, or None when another process
    does. The system lets go of it when the process ends, so a crash leaves no lock behind."""
    os.makedirs(folder, exist_ok=True)
    fh = open(os.path.join(folder, name), "a+")
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def telegram_loop(post, settings, folder, wait, words_for, date=None, rounds=None, pause=time.sleep):
    """`lesson pull --loop`: the Telegram receiver that stays on - one long poll after another, the journal and the
    settings read anew each round, so a press is answered within seconds. A lost connection or a refused request is
    one line, then the next round after 5 seconds, up to 5 minutes. -> the rounds done; it runs until stopped,
    unless `rounds` is given."""
    wait = max(int(wait or 50), 10)
    done, delay = 0, 5
    try:
        while rounds is None or done < rounds:
            entries = read_journal(folder)
            if telegram_hooked(entries):       # `lesson webhook` handed the presses to `lesson serve`
                break
            done += 1
            try:
                counts = telegram_pull(post, settings(), folder, entries, wait, int(time.time()),
                                       parse_date(date, "--date"), words_for)
                delay = 5
                if any(counts.values()):
                    print(say(words_for(None), "lesson_pulled", **counts))
            except Problem as exc:
                print("teamcall: %s" % exc)
                pause(delay)
                delay = min(delay * 2, 300)
            if sys.stdout:
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    return done


def whatsapp_events(doc):
    """-> [(the person's number or "", their user id or "", message id, unix time, "text" or "button", the text or the
    button's id)] from one webhook payload. Meta leaves the number out for a person with a username the company has
    not been in touch with for 30 days; the user id (from_user_id) names them then. A message of another type (a
    photo, a voice note) counts as text: it opens the 24 hours too."""
    out = []
    for entry in doc.get("entry") or []:
        for change in entry.get("changes") or []:
            for m in (change.get("value") or {}).get("messages") or []:
                kind, value = "text", ""
                if m.get("type") == "text":
                    value = (m.get("text") or {}).get("body", "")
                elif m.get("type") == "interactive":
                    kind, value = "button", ((m.get("interactive") or {}).get("button_reply") or {}).get("id", "")
                elif m.get("type") == "button":
                    kind, value = "button", (m.get("button") or {}).get("payload", "")
                user_id = str(m.get("from_user_id") or "")
                out.append((digits(m.get("from")), user_id if USER_ID.fullmatch(user_id) else "",
                            str(m.get("id") or ""), int(m.get("timestamp") or 0), kind, value))
    return out


def whatsapp_statuses(doc):
    """-> [(message id, status: sent / delivered / read / failed, error code, error title)] from one webhook payload:
    what became of the messages the company sent."""
    out = []
    for entry in doc.get("entry") or []:
        for change in entry.get("changes") or []:
            for s in (change.get("value") or {}).get("statuses") or []:
                error = (s.get("errors") or [{}])[0] or {}
                out.append((str(s.get("id") or ""), str(s.get("status") or ""), error.get("code"),
                            str(error.get("title") or error.get("message") or "")))
    return out


def whatsapp_template_moves(doc):
    """-> [(template name, its language, the category, unix time or 0)] from one webhook payload: Meta's word that it
    files an approved template under another category - in 24 hours (correct_category, with the time) or done
    (new_category, time 0). Subscribe the app to template_category_update to get it."""
    out = []
    for entry in doc.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            if change.get("field") != "template_category_update" or not isinstance(value, dict):
                continue
            category = value.get("correct_category") or value.get("new_category")
            if category:
                out.append((str(value.get("message_template_name") or ""),
                            str(value.get("message_template_language") or ""), str(category),
                            int(value.get("category_update_timestamp") or 0) if value.get("correct_category") else 0))
    return out


def template_moved(words, moves):
    """Each category move in one line for the champion; a move away from utility comes with the way to a review."""
    for name, lang, category, when in moves:
        if when:
            date = datetime.datetime.fromtimestamp(when, datetime.timezone.utc).date().isoformat()
            print(say(words, "lesson_template_moving", lang=lang, name=name, category=category, date=date))
        elif category == "UTILITY":
            print(say(words, "lesson_template_moved", lang=lang, name=name, category=category))
        if category != "UTILITY":
            print(say(words, "lesson_template_review", lang=lang, category=category))


def undelivered(folder, entries, statuses, today, words_for):
    """Meta's word that a card did not arrive (status failed - for one, a template filed as marketing never reaches a
    +1 number, error 131049): the journal marks that card undelivered, so it stays the person's next card and comes
    the moment they write, and the receiver says it in one line."""
    sent = {e.get("msg"): e for e in entries
            if e.get("kind") == "lesson_sent" and e.get("channel") == "whatsapp" and e.get("msg")}
    marked = {e.get("msg") for e in entries if e.get("kind") == "lesson_undelivered"}
    for msg, status, code, why in statuses:
        e = sent.get(msg)
        if status != "failed" or e is None or msg in marked:
            continue
        marked.add(msg)
        lesson_note(folder, entries, {"kind": "lesson_undelivered", "person": e.get("person"), "channel": "whatsapp",
                                      "chat": e.get("chat"), "card": e.get("card"), "msg": msg, "code": code,
                                      "date": today.isoformat()})
        print(say(words_for(None), "lesson_failed", channel="whatsapp", person=e.get("person"),
                  why="%s (%s)" % (why, code) if code else why))


def whatsapp_reply(post, conf, message):
    """An answer inside the 24 hours the person's own message opened; a failure is printed, never raised."""
    try:
        ok, result = whatsapp(post, conf, whatsapp_phone_id(conf) + "/messages", message)
    except Problem as exc:
        ok, result = False, str(exc)
    if not ok:
        print("whatsapp: %s" % result)


def whatsapp_webhook(method, target, headers, body, folder, conf, post, words_for, now=None, today=None):
    """One request from Meta -> (HTTP status, text). GET is the subscription check with the verify token; POST brings
    the people's messages, what became of the cards and Meta's moves of the template, signed with the app secret -
    nothing unsigned reaches the journal. Done and skip get the short reply that they counted, show me the example,
    open the card; `card` brings the card of the day, any other message the next card when none came today. Each
    answer goes inside the 24 hours the person's own press or message has just opened. A person Meta names by their
    user id alone has a chat of their own, and the answers go to that id."""
    if method == "GET":
        query = dict(urllib.parse.parse_qsl(str(target).partition("?")[2]))
        expected = conf.get("TEAMCALL_WHATSAPP_VERIFY_TOKEN", "")
        if (query.get("hub.mode") == "subscribe" and expected
                and hmac.compare_digest(query.get("hub.verify_token", "").encode("utf-8"), expected.encode("utf-8"))):
            return 200, query.get("hub.challenge", "")
        return 403, "forbidden"
    secret = conf.get("TEAMCALL_WHATSAPP_APP_SECRET", "")
    given = {str(k).lower(): str(v) for k, v in headers.items()}.get("x-hub-signature-256", "")
    signed = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(signed.encode("utf-8"), given.encode("utf-8")):
        return 403, "bad signature"
    try:
        doc = json.loads(body.decode("utf-8"))
        events, statuses, moves = whatsapp_events(doc), whatsapp_statuses(doc), whatsapp_template_moves(doc)
    except (ValueError, TypeError, AttributeError, IndexError):
        return 400, "not a WhatsApp webhook"
    now = int(time.time()) if now is None else now
    today = today or datetime.date.today()
    entries = read_journal(folder)
    start = plan_start(entries)
    seen = {e.get("msg") for e in entries if e.get("msg")}
    for number, user_id, msg, at, kind, value in events:
        chat = whatsapp_chat(entries, number, user_id)
        if not chat:                           # neither a number nor a user id: nobody to answer
            continue
        if msg:
            if msg in seen:                    # Meta delivers again what was not confirmed in time
                continue
            seen.add(msg)
        if kind == "button":
            got = take_button(folder, entries, "whatsapp", chat, value, at or now, msg, today, user_id)
            if got and got[0] == "show":
                whatsapp_reply(post, conf, whatsapp_example(words_for(got[2]), chat, got[1]))
            elif got and got[0] == "open":
                send_card(post, conf, folder, entries, "whatsapp", chat, got[1], today, words_for, True)
            elif got:
                whatsapp_reply(post, conf, whatsapp_text(chat, say(words_for(got[2]), "lesson_ack_" + got[0])))
            continue
        key, lang, change = take_text(folder, entries, "whatsapp", chat, value, at or now, msg, today, user_id)
        if key:
            whatsapp_reply(post, conf, whatsapp_text(chat, say(words_for(lang), key, stop="stop", start="start",
                                                               card="card")))
        if change in ("card", "wrote"):
            card_now(post, conf, folder, entries, "whatsapp", chat, today, words_for, change == "card", start)
    undelivered(folder, entries, statuses, today, words_for)
    template_moved(words_for(None), moves)
    return 200, "ok"


def webhook_handler(folder, conf, post, words_for):
    """The HTTP side of `lesson serve`: a request to .../telegram goes to telegram_webhook, any other to
    whatsapp_webhook, one at a time, since each writes the journal; the connections themselves, a TLS handshake
    included, run each in its own thread under a time limit."""
    import http.server
    journal = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        timeout = 30                           # a silent connection ends after 30 seconds, its TLS handshake included

        def setup(self):
            super().setup()
            handshake = getattr(self.connection, "do_handshake", None)
            if handshake:                      # TLS: here, in this connection's own thread, under the limit above
                handshake()

        def do_GET(self):
            self.reply(*whatsapp_webhook("GET", self.path, self.headers, b"", folder, conf, post, words_for))

        def do_POST(self):
            try:
                size = min(max(int(self.headers.get("Content-Length") or 0), 0), 1 << 20)
            except ValueError:
                size = 0
            body = self.rfile.read(size)
            try:
                with journal:
                    if str(self.path).partition("?")[0].rstrip("/").endswith("/telegram"):
                        status, text = telegram_webhook(self.headers, body, folder, conf, post, words_for)
                    else:
                        status, text = whatsapp_webhook("POST", self.path, self.headers, body, folder, conf, post,
                                                        words_for)
            except Problem as exc:
                status, text = 500, str(exc)
            self.reply(status, text)

        def reply(self, status, text):
            data = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):         # no access log: the journal is the record, without the numbers
            pass

    return Handler


def serve_webhook(folder, host, port, conf, post, words_for, cert=None, cert_key=None, ready=None):
    """`lesson serve`: the address Meta brings the WhatsApp buttons to; HTTPS itself with --cert (then on every
    address of this computer), or behind the company's HTTPS. Each connection is served in a thread of its own, its
    TLS handshake too, so a silent or broken one holds up nothing else. Runs until stopped (Ctrl+C); `ready` gets the
    listening server first (the tests stop it with its shutdown)."""
    import http.server
    import ssl

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):     # one bad connection is one line, not a traceback
            print("teamcall serve: %s" % (sys.exc_info()[1],))

    try:
        server = Server((host, port), webhook_handler(folder, conf, post, words_for))
        if cert:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, cert_key)
            server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    except OSError as exc:
        raise Problem("cannot listen on %s:%d: %s" % (host, port, exc))
    try:
        if ready:
            ready(server)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def lesson_send(post, conf, folder, entries, channels, now, today, lang, words_for, day=None, start=None):
    """Each chat that joined and has not stopped gets its own next card, one a day: card 1 on its first working
    day, then the next one on the first run of each new day - a person who joins in week 3, or after the pilot,
    still gets all of them in order, and a day nobody sent moves the cards by a day without skipping one. Before the
    pilot's start nobody begins. `day` sends that one card to every chat that lacks it. A messenger without its
    settings holds up no other: its chats are not delivered, with the missing setting named, and the rest go.

    -> ({channel: {"sent", "had", "finished", "waiting", "failed"}}, [(channel, person, why)])."""
    chats = sorted((key, state) for key, state in lesson_chats(entries).items()
                   if key[0] in channels and state["active"])
    counts, failed = {}, []
    for (channel, chat), state in chats:
        row = counts.setdefault(channel, dict.fromkeys(SEND_COUNTS, 0))
        have, tried, _today_card = chat_progress(entries, channel, chat, today)
        n = day or next_card(have)
        if (day and day in have) or (not day and tried):
            row["had"] += 1
            continue
        if n is None:
            row["finished"] += 1
            continue
        if not day and start and not have and today < start:
            row["waiting"] += 1
            continue
        code = state["lang"] or lang
        how = "buttons" if now - state["at"] < WINDOW_SECONDS else "template"
        ok, result, status, msg, how = deliver(post, conf, channel, chat, words_for(code), code, n, how == "buttons")
        if ok:
            note_sent(folder, entries, state, channel, chat, n, how, msg, today)
            row["sent"] += 1
            continue
        row["failed"] += 1
        failed.append((channel, state["person"], result))
        not_delivered(folder, entries, state, channel, chat, status, today)
    return counts, failed


def lessons_summary(entries, until=None):
    """The cards in numbers, one count per person and card: sent (the card reached the person; one Meta reported
    undelivered did not), done, show, skip (the buttons pressed; done wins over skip), silent (no button at all).

    -> ({card: counts}, {person: counts}, {person: the day of their first card})."""
    reached, pressed, first = set(), {}, {}
    lost = {e.get("msg") for e in entries if e.get("kind") == "lesson_undelivered" and e.get("msg")}
    for e in entries:
        if e.get("kind") not in ("lesson_sent", "lesson_answer"):
            continue
        if e["kind"] == "lesson_sent" and e.get("msg") and e["msg"] in lost:
            continue
        day = parse_date(e.get("date"), "journal date")
        card = int(e.get("card") or 0)
        if (until and day > until) or not 1 <= card <= CARDS:
            continue
        key = (e.get("person"), card)
        reached.add(key)
        first[key[0]] = min(first.get(key[0], day), day)
        if e["kind"] == "lesson_answer" and e.get("answer") in ANSWERS:
            pressed.setdefault(key, set()).add(e["answer"])
    cards, people = {}, {}
    for key in reached:
        got = pressed.get(key, set())
        row = {"sent": 1, "done": "done" in got, "show": "show" in got, "skip": "skip" in got and "done" not in got,
               "silent": not got}
        for table, at in ((cards, key[1]), (people, key[0])):
            counts = table.setdefault(at, dict.fromkeys(LESSON_COUNTS, 0))
            for k in LESSON_COUNTS:
                counts[k] += int(row[k])
    return cards, people, first


def lessons_text(words, cards, people, names):
    """The report's part on the daily cards: per card and per person (P1, P2, ...), never a name, a chat or a number."""
    lines = ["## %s" % say(words, "report_lessons"), ""]
    if not cards:
        return lines + [say(words, "report_lessons_none"), ""]
    total = {k: sum(c[k] for c in cards.values()) for k in LESSON_COUNTS}
    columns = " | ".join((say(words, "col_sent"), say(words, "lesson_done"), say(words, "lesson_show"),
                          say(words, "lesson_skip"), say(words, "col_silent")))
    rule = "|---|" + "---|" * len(LESSON_COUNTS)
    lines += [say(words, "report_lessons_sum", people=len(people), **total), "",
              "| %s | %s |" % (say(words, "col_card"), columns), rule]
    for n in sorted(cards):
        lines.append("| %d. %s | %s |" % (n, say(words, "card_%d_title" % n),
                                          " | ".join(str(cards[n][k]) for k in LESSON_COUNTS)))
    lines += ["", "| %s | %s |" % (say(words, "col_who"), columns), rule]
    for who in sorted(people, key=lambda w: int(names[w][1:])):
        lines.append("| %s | %s |" % (names[who], " | ".join(str(people[who][k]) for k in LESSON_COUNTS)))
    return lines + [""]


def parse_at(text):
    at = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", str(text))
    if not at:
        raise Problem("--at must be HH:MM, not %r" % text)
    return int(at.group(1)), int(at.group(2))


def card_hours(at):
    """The hours of a scheduled send: from `at` (hour, minute) to LAST_HOUR, or to midnight when `at` is later."""
    return at, ((LAST_HOUR, 0) if at < (LAST_HOUR, 0) else (24, 0))


def plugin_home(root=ROOT):
    """Where Claude Code keeps this teamcall. -> (its plugin cache, the catalogue, the plugin's name) when this copy
    is a version folder <plugins>/cache/<catalogue>/<name>/<version>/, else (None, None, None): a folder that stays
    where it is."""
    version = os.path.abspath(root)
    plugin = os.path.dirname(version)
    market = os.path.dirname(plugin)
    cache = os.path.dirname(market)
    if os.path.basename(cache) == "cache" and os.path.basename(plugin) and os.path.basename(market):
        return cache, os.path.basename(market), os.path.basename(plugin)
    return None, None, None


# The launcher `lesson schedule` writes into the company's folder, for cron (sh) and for Task Scheduler (Python).
SH_LAUNCHER = r'''#!/bin/sh
# teamcall's schedule runs this file; `teamcall lesson schedule` wrote it. Claude Code keeps each version of a plugin
# in a folder of its own and removes the old one 14 days after an update, so on every run this file finds the
# newest version installed now - by its numbers, so 0.1.10 comes after 0.1.9 - and runs it. What a run says goes
# into @LOGNAME@ beside this file, under the run's time; a run with nothing to say leaves no line.
cache=@CACHE@
market=@MARKET@
name=@NAME@
fallback=@ROOT@
here=$(cd "$(dirname "$0")" && pwd)
root=
best=
if [ -n "$cache" ]; then
  for r in "$cache/$market/$name/"*/ "$cache/"*/"$name"/*/; do
    [ -f "${r}skills/teamcall/scripts/teamcall.py" ] && [ ! -e "${r}.orphaned_at" ] || continue
    key=$(basename "$r" | awk -F. '{ k = ""; for (i = 1; i <= NF; i++) k = k sprintf("%09d.", $i + 0); print k }')
    if [ -z "$root" ] || [ "$(printf '%s\n%s\n' "$best" "$key" | sort | tail -n 1)" != "$best" ]; then
      root=${r%/}
      best=$key
    fi
  done
fi
[ -n "$root" ] || root=$fallback
PYTHONUNBUFFERED=1 sh "$root/hooks/python.sh" teamcall say "$root/skills/teamcall/scripts/teamcall.py" "$@" 2>&1 |
  awk -v head="--- $(date '+%Y-%m-%d %H:%M') $1 $2" -v file="$here/@LOGNAME@" \
    'NR == 1 { print head >> file } { print >> file; fflush(file) }'
'''

PY_LAUNCHER = r'''"""teamcall's schedule runs this file with the Python that opens no window; `teamcall lesson schedule` wrote it.
Claude Code keeps each version of a plugin in a folder of its own and removes the old one 14 days after an update, so
on every run this file finds the newest version installed now - by its numbers, so 0.1.10 comes after 0.1.9 - and
runs it. What a run says goes into @LOGNAME@ beside this file, under the run's time; a run with nothing to say
leaves no line."""
import datetime
import glob
import os
import re
import runpy
import sys

CACHE = @CACHE@
MARKET = @MARKET@
NAME = @NAME@
FALLBACK = @ROOT@
SCRIPT = os.path.join("skills", "teamcall", "scripts", "teamcall.py")


def version(root):
    return [int(part) if part.isdigit() else 0 for part in re.split(r"[.]", os.path.basename(root))]


def installed():
    found = set()
    if CACHE:
        for market in (glob.escape(MARKET), "*"):
            for root in glob.glob(os.path.join(glob.escape(CACHE), market, glob.escape(NAME), "*")):
                if os.path.isfile(os.path.join(root, SCRIPT)) and not os.path.exists(os.path.join(root, ".orphaned_at")):
                    found.add(root)
    return max(found, key=version) if found else FALLBACK


class Log:
    """The run's output into the log, its time line first - only once the run has something to say."""

    def __init__(self, path, head):
        self.path, self.head, self.fh = path, head, None

    def write(self, text):
        if text and self.fh is None:
            self.fh = open(self.path, "a", encoding="utf-8", buffering=1)
            self.fh.write(self.head + "\n")
        return self.fh.write(text) if text else 0

    def flush(self):
        if self.fh is not None:
            self.fh.flush()


here = os.path.dirname(os.path.abspath(__file__))
sys.stdout = sys.stderr = Log(os.path.join(here, "@LOGNAME@"), "--- %s %s" % (
    datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), " ".join(sys.argv[1:3])))
script = os.path.join(installed(), SCRIPT)
sys.argv = [script] + sys.argv[1:]
runpy.run_path(script, run_name="__main__")
'''


def launcher_text(os_name, root=ROOT):
    """The launcher every schedule line names, kept in the company's folder: on each run it finds the teamcall Claude
    Code has installed now - its folder carries the version and goes 14 days after an update - and runs it, with the
    output going into RUN_LOG beside it."""
    cache, market, name = plugin_home(root)
    values = (cache, market, name, os.path.abspath(root))
    if os_name == "windows":
        text, form = PY_LAUNCHER, repr
    else:
        text, form = SH_LAUNCHER, lambda v: "''" if v is None else "'%s'" % v.replace("'", "'\\''")
    for key, value in zip(("@CACHE@", "@MARKET@", "@NAME@", "@ROOT@"), values):
        text = text.replace(key, form(value))
    return text.replace("@LOGNAME@", RUN_LOG)


def windowless_python(env=None, executable=None, isfile=os.path.isfile, which=shutil.which):
    """The Python that runs a Windows task without a window: the launcher pyw.exe, which takes the newest Python 3 on
    every run, else pythonw.exe beside this Python. -> (program, its arguments before the script)."""
    env = os.environ if env is None else env
    places = [which("pyw")]
    if env.get("LOCALAPPDATA"):
        places.append(os.path.join(env["LOCALAPPDATA"], "Programs", "Python", "Launcher", "pyw.exe"))
    if env.get("SystemRoot"):
        places.append(os.path.join(env["SystemRoot"], "pyw.exe"))
    for path in places:
        if path and isfile(path):
            return path, ["-3"]
    executable = executable or sys.executable
    windowless = os.path.join(os.path.dirname(executable), "pythonw.exe")
    return (windowless, []) if isfile(windowless) else (executable, [])


def cron_times(begin, end):
    """cron's times for every 15 minutes of each working day from `begin` (hour, minute) until `end`: the first hour
    from its minute (08:30 -> 30-59/15 8), then the whole hours."""
    (hour, minute), last = begin, end[0] - 1

    def span(first, final):
        return "%d" % first if first == final else "%d-%d" % (first, final)
    if not minute:
        return ["*/15 %s * * 1-5" % span(hour, last)]
    return ["%d-59/15 %d * * 1-5" % (minute, hour)] + (["*/15 %s * * 1-5" % span(hour + 1, last)]
                                                         if hour < last else [])


def schedule_text(words, os_name, folder, at, env_path, launcher, program=None):
    """The lines that run the cards on this computer, each through `launcher` (launcher_text), so no line names the
    plugin's version folder: the cards every 15 minutes of each working day from `at` to LAST_HOUR - each person's
    next card, once a day, so a computer asleep at `at` sends it when it wakes -, and the Telegram and WhatsApp
    receivers every 5 minutes, each starting only when it is not running yet and its messenger's settings are in
    place (--if-set), so a company with one messenger gets no error lines from the other. cron on Mac and Linux;
    Task Scheduler on Windows, through a Python that opens no window (program), on battery too, catching up a run it
    missed."""
    begin, end = card_hours(at)
    hours = {"at": "%02d:%02d" % begin, "until": "%02d:%02d" % end}
    lines = ["# " + say(words, "lesson_schedule_env", file=env_path),
             "# " + say(words, "lesson_schedule_launcher", file=launcher, log=os.path.join(folder, RUN_LOG))]
    card = "# " + say(words, "lesson_schedule_card", **hours)
    send = "send --at %s" % hours["at"]
    pull, serve = "pull --loop --if-set", "serve --port 8080 --if-set"
    if os_name == "windows":
        program, before = program or (sys.executable, [])

        def task(name, args):
            argument = ('%s"%s" lesson %s --folder "%s"' % ("".join(a + " " for a in before), launcher, args, folder))
            return ("Register-ScheduledTask -TaskName '%s' -Action (New-ScheduledTaskAction -Execute '%s' "
                    "-Argument '%s') -Trigger $t -Settings $s" % (name, program.replace("'", "''"),
                                                                 argument.replace("'", "''")))
        minutes = end[0] * 60 + end[1] - begin[0] * 60 - begin[1]
        lines += ["# " + say(words, "lesson_schedule_windows"),
                  "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
                  "-StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)",
                  card,
                  "$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At %s"
                  % hours["at"],
                  "$t.Repetition = (New-ScheduledTaskTrigger -Once -At %s -RepetitionInterval (New-TimeSpan -Minutes 15) "
                  "-RepetitionDuration (New-TimeSpan -Minutes %d)).Repetition" % (hours["at"], minutes),
                  task("teamcall card", send),
                  "# " + say(words, "lesson_schedule_answers"),
                  "$t = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)",
                  task("teamcall answers", pull),
                  "# " + say(words, "lesson_schedule_serve"),
                  task("teamcall whatsapp", serve)]
    else:
        def line(when, args):
            return '%s sh "%s" lesson %s --folder "%s"' % (when, launcher, args, folder)
        lines = ["PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"] + lines + [card] + [
            line(when, send) for when in cron_times(begin, end)] + [
            "# " + say(words, "lesson_schedule_answers"),
            line("*/5 * * * *", pull),
            "# " + say(words, "lesson_schedule_serve"),
            line("*/5 * * * *", serve)]
        if os_name == "mac":
            lines.append("# " + say(words, "lesson_schedule_mac"))
    return "\n".join(lines) + "\n"


def lesson_invite(args, words, lang, conf, post, entries, today):
    """A link for one person: one tap in the messenger and the cards start. WhatsApp with --phone puts the number on
    the list at once. A setting the messenger still lacks is named in one line; the invite stands, and its cards go
    once the setting is in."""
    if not args.person:
        raise Problem("lesson invite needs --person")
    channel = args.channel if args.channel in CHANNELS else "telegram"
    missing = missing_setting(conf, channel)
    if channel == "whatsapp" and args.phone:
        phone = digits(args.phone)
        if len(phone) < 8:
            raise Problem("--phone is the person's WhatsApp number with the country code")
        lesson_note(args.folder, entries, {"kind": "lesson_chat", "person": args.person, "channel": channel,
                                           "chat": phone, "lang": lang, "date": today.isoformat(), "at": 0})
        print(say(words, "lesson_joined_phone", person=args.person))
        if missing:
            print("teamcall: %s" % missing)
        return 0
    code = secrets.token_urlsafe(12)
    if channel == "telegram":
        bot = (args.bot or conf.get("TEAMCALL_TELEGRAM_BOT") or "").lstrip("@")
        if not bot:
            ok, me, _status = telegram(post, telegram_token(conf), "getMe", {})
            if not ok or not isinstance(me, dict) or not me.get("username"):
                raise Problem("telegram: %s" % (me if not ok else "getMe gave no username"))
            bot = str(me["username"])
        if not re.fullmatch(r"[A-Za-z0-9_]{3,64}", bot):
            raise Problem("%r is not a bot's name" % bot)
        link = "https://t.me/%s?start=%s" % (bot, code)
    else:
        number = digits(args.number or conf.get("TEAMCALL_WHATSAPP_NUMBER"))
        if len(number) < 8:
            raise Problem("a WhatsApp invite needs the company's WhatsApp number: --number or TEAMCALL_WHATSAPP_NUMBER")
        link = "https://wa.me/%s?text=%s" % (number, urllib.parse.quote("start " + code))
    lesson_note(args.folder, entries, {"kind": "lesson_invite", "person": args.person, "channel": channel,
                                       "code": code, "lang": lang, "date": today.isoformat()})
    print(say(words, "lesson_invite", person=args.person, link=link))
    if missing:
        print("teamcall: %s" % missing)
    return 0


def lesson_webhook(args, words, conf, post, entries, today):
    """`lesson webhook --url https://<the company's address>/telegram`: Telegram brings every press and message to
    `lesson serve` the moment it is made, with the bot's secret in each request, and keeps none waiting on this
    computer. `--off` hands them back to `lesson pull`."""
    token = telegram_token(conf)
    if args.off:
        ok, result, _status = telegram(post, token, "deleteWebhook", {})
        url = ""
    else:
        url = str(args.url or "")
        if not re.fullmatch(r"https://[A-Za-z0-9.-]+(:\d+)?(/[^\s?#]*)?/telegram/?", url):
            raise Problem("--url is the HTTPS address of `teamcall lesson serve` ending in /telegram, like "
                          "https://cards.example.com/telegram")
        ok, result, _status = telegram(post, token, "setWebhook", {"url": url, "secret_token": telegram_secret(token),
                                                                     "allowed_updates": ["message", "callback_query"]})
    if not ok:
        raise Problem("telegram: %s" % result)
    lesson_note(args.folder, entries, {"kind": "lesson_webhook", "channel": "telegram", "url": url,
                                       "date": today.isoformat()})
    print(say(words, "lesson_webhook_on", url=url) if url else say(words, "lesson_webhook_off"))
    return 0


def lesson_templates(args, words, conf, post):
    """The WhatsApp template in five languages - the note that opens the card: printed for WhatsApp Manager, or with
    --create sent to Meta for approval, once. Meta's answer names the category it filed the template under; anything
    but utility is said with the way to ask Meta for a review."""
    name = conf.get("TEAMCALL_WHATSAPP_TEMPLATE") or WHATSAPP_TEMPLATE
    if not re.fullmatch(r"[a-z0-9_]{1,512}", name):
        raise Problem("TEAMCALL_WHATSAPP_TEMPLATE takes small letters, digits and _")
    templates = whatsapp_templates(name)
    if not args.create:
        sys.stdout.write(json.dumps(templates, ensure_ascii=False, indent=2) + "\n")
        return 0
    account = need(conf, "TEAMCALL_WHATSAPP_WABA_ID", "WhatsApp templates")
    if not re.fullmatch(r"[0-9]+", account):
        raise Problem("TEAMCALL_WHATSAPP_WABA_ID is the WhatsApp Business account id: digits")
    bad = 0
    for template in templates:
        ok, result = whatsapp(post, conf, account + "/message_templates", template)
        category = str(result.get("category") or "") if ok else ""
        print(say(words, "lesson_template_sent", lang=template["language"],
                  status=result.get("status", "") if ok else result, category=category or "-"))
        if category and category != "UTILITY":
            print(say(words, "lesson_template_review", lang=template["language"], category=category))
        bad += 0 if ok else 1
    return 1 if bad else 0


def lesson_run(args, words, lang, post, env, now):
    """`teamcall lesson ...`: the card of the day, the people who take it, its buttons and its schedule."""
    env = os.environ if env is None else env
    conf = lesson_env(env)
    entries = read_journal(args.folder)
    today = parse_date(args.date, "--date")
    now = int(time.time()) if now is None else now
    cache = {lang: words}

    def words_for(code):
        code = code if code in LANGS else lang
        if code not in cache:
            cache[code] = lang_words(code)
        return cache[code]

    if args.action == "schedule":
        launcher = os.path.join(args.folder, LAUNCHER[args.os])
        text = launcher_text(args.os)
        if args.print:
            sys.stdout.write("--- %s\n%s" % (launcher, text))
        else:
            os.makedirs(args.folder, exist_ok=True)
            with open(launcher, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print(say(words, "wrote", path=launcher))
        program = windowless_python(env) if args.os == "windows" else None
        sys.stdout.write(schedule_text(words, args.os, args.folder, parse_at(args.at or "09:00"), env_file(env),
                                       launcher, program))
        return 0
    if args.action == "template":
        return lesson_templates(args, words, conf, post)
    whatsapp_on = all(conf.get(key) for key in ("TEAMCALL_WHATSAPP_APP_SECRET", "TEAMCALL_WHATSAPP_VERIFY_TOKEN"))
    hooked = bool(conf.get("TEAMCALL_TELEGRAM_TOKEN")) and telegram_hooked(entries)
    ready = {"serve": whatsapp_on or hooked, "pull": bool(conf.get("TEAMCALL_TELEGRAM_TOKEN")) and not hooked}
    if args.if_set and not ready.get(args.action, True):
        return 0                               # the schedule's receiver of a messenger this company does not use here
    if args.action == "webhook":
        return lesson_webhook(args, words, conf, post, entries, today)
    if args.action == "serve":
        if not hooked:
            for key in ("TEAMCALL_WHATSAPP_APP_SECRET", "TEAMCALL_WHATSAPP_VERIFY_TOKEN"):
                need(conf, key, "WhatsApp answers")
        lock = hold_lock(args.folder, LOCKS["serve"])
        if lock is None:                       # it runs already for this folder: the schedule starts it every 5 minutes
            return 0
        host = args.host or ("0.0.0.0" if args.cert else "127.0.0.1")
        address = "%s://%s:%d" % ("https" if args.cert else "http", host, args.port)
        if whatsapp_on:
            print(say(words, "lesson_serving", address=address))
        if hooked:
            print(say(words, "lesson_serving_telegram", address=address))
        if sys.stdout:
            sys.stdout.flush()
        try:
            serve_webhook(args.folder, host, args.port, conf, post, words_for, args.cert, args.cert_key)
        finally:
            lock.close()
        return 0
    if args.action == "invite":
        return lesson_invite(args, words, lang, conf, post, entries, today)
    if args.action == "pull":
        if args.channel == "whatsapp":
            raise Problem("WhatsApp brings its buttons to `teamcall lesson serve`; `pull` reads Telegram")
        if hooked:
            raise Problem("Telegram brings the presses to `teamcall lesson serve` now; `lesson webhook --off` hands "
                          "them back to `pull`")
        if args.loop:
            lock = hold_lock(args.folder, LOCKS["pull"])
            if lock is None:                   # one receiver per folder: Telegram answers one long poll at a time
                return 0
            try:
                telegram_loop(post, lambda: lesson_env(env), args.folder, args.wait, words_for, args.date)
            finally:
                lock.close()
            return 0
        counts = telegram_pull(post, conf, args.folder, entries, args.wait, now, today, words_for)
        print(say(words, "lesson_pulled", **counts))
        return 0
    if args.day is not None and not 1 <= args.day <= CARDS:
        raise Problem("--day must be 1 to %d" % CARDS)
    if args.action == "card":
        n = args.day or card_day(pilot_start(entries, args.start), today)
        if n is None:
            print(say(words, "lesson_no_card", date=today.isoformat(), total=CARDS))
            return 0
        sys.stdout.write(card_page(words, n))
        return 0
    if args.day is None and today.weekday() >= 5:
        print(say(words, "lesson_weekend", date=today.isoformat()))
        return 0
    first_run = False                          # a scheduled run within 15 minutes of --at: the first one of the day
    if args.at:
        begin, end = card_hours(parse_at(args.at))
        clock = datetime.datetime.fromtimestamp(now)
        if not begin <= (clock.hour, clock.minute) < end:
            print(say(words, "lesson_not_now", time=clock.strftime("%H:%M"), at="%02d:%02d" % begin,
                      until="%02d:%02d" % end))
            return 0
        first_run = clock.hour * 60 + clock.minute < begin[0] * 60 + begin[1] + 15
    start = parse_date(args.start, "--start") if args.start else plan_start(entries)
    channels = CHANNELS if args.channel in (None, "all") else (args.channel,)
    counts, failed = lesson_send(post, conf, args.folder, entries, channels, now, today, lang, words_for, args.day,
                                 start)
    missing = not_joined(entries)
    if args.at and not any(row["sent"] or row["failed"] for row in counts.values()):
        # a scheduled run that sent nothing leaves the log alone; its first run of the day still says who is missing
        if first_run and not counts:
            print(say(words, "lesson_nobody"))
        if first_run and missing:
            print(say(words, "lesson_not_joined", people=", ".join(missing)))
        return 0
    for channel, person, why in failed:
        print(say(words, "lesson_failed", channel=channel, person=person, why=why))
    for channel in sorted(counts):
        if args.day:
            print(say(words, "lesson_sent_day", channel=channel, n=args.day, total=CARDS, **counts[channel]))
        else:
            print(say(words, "lesson_sent", channel=channel, total=CARDS, **counts[channel]))
    waiting = sum(row["waiting"] for row in counts.values())
    if waiting:
        print(say(words, "lesson_waiting", count=waiting, date=start.isoformat()))
    if not counts:
        print(say(words, "lesson_nobody"))
    if missing:
        print(say(words, "lesson_not_joined", people=", ".join(missing)))
    return 1 if failed else 0


# ---------------------------------------------------------------- the command line --------------

def parser():
    p = argparse.ArgumentParser(prog="teamcall", description=__doc__.split("\n\n")[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--folder", default=os.getcwd())
    common.add_argument("--lang", choices=LANGS)
    common.add_argument("--print", action="store_true")
    this_os = {"darwin": "mac", "win32": "windows"}.get(sys.platform, "linux")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("plan", parents=[common])
    s.add_argument("--company", required=True)
    s.add_argument("--people", type=int, default=5)
    s.add_argument("--target", type=int, default=30)
    s.add_argument("--start")
    s.add_argument("--champion")
    s.add_argument("--sponsor")
    s = sub.add_parser("fast", parents=[common])
    s.add_argument("--person", required=True)
    s.add_argument("--os", choices=sorted(INSTALL), default=this_os)
    s.add_argument("--task")
    s.add_argument("--seat")
    s = sub.add_parser("champion", parents=[common])
    s.add_argument("--person", required=True)
    s = sub.add_parser("boost", parents=[common])
    s.add_argument("--name", required=True)
    s.add_argument("--task", required=True)
    s = sub.add_parser("claudemd", parents=[common])
    s.add_argument("file")
    s = sub.add_parser("log", parents=[common])
    s.add_argument("action", choices=("add", "show"))
    s.add_argument("--person")
    s.add_argument("--stage", choices=STAGES)
    s.add_argument("--minutes", type=int, default=0)
    s.add_argument("--help-minutes", type=int, default=0)
    s.add_argument("--blocker")
    s.add_argument("--artifact")
    s.add_argument("--date")
    s = sub.add_parser("measure", parents=[common])
    s.add_argument("--person", required=True)
    s.add_argument("--task", required=True)
    s.add_argument("--before-min", type=float)
    s.add_argument("--after-min", type=float)
    s.add_argument("--quality")
    s.add_argument("--coverage-before", type=int)
    s.add_argument("--coverage-after", type=int)
    s.add_argument("--repeatable", action="store_true")
    s.add_argument("--capability")
    s.add_argument("--risk")
    s.add_argument("--date")
    for name in ("report", "decide"):
        s = sub.add_parser(name, parents=[common])
        s.add_argument("--until")
        s.add_argument("--max-help", type=int, default=60)
    s = sub.add_parser("move", parents=[common])
    s.add_argument("--start")
    s = sub.add_parser("agents", parents=[common])
    s.add_argument("--seat")
    sub.add_parser("detect", parents=[common])
    s = sub.add_parser("lesson", parents=[common])
    s.add_argument("action", choices=LESSON_ACTIONS)
    s.add_argument("--person")
    s.add_argument("--channel", choices=CHANNELS + ("all",))
    s.add_argument("--day", type=int)
    s.add_argument("--date")
    s.add_argument("--start")
    s.add_argument("--bot")
    s.add_argument("--number")
    s.add_argument("--phone")
    s.add_argument("--wait", type=int, default=0)
    s.add_argument("--loop", action="store_true")
    s.add_argument("--url")                    # webhook: the HTTPS address of `lesson serve`, ending in /telegram
    s.add_argument("--off", action="store_true")
    s.add_argument("--if-set", action="store_true")     # pull, serve: start only when the messenger's settings are in
    s.add_argument("--host")                   # 127.0.0.1, or every address (0.0.0.0) with --cert
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--cert")
    s.add_argument("--cert-key")
    s.add_argument("--create", action="store_true")
    s.add_argument("--at")                     # schedule: 09:00 unless given; send: no card before it, nor after 20:00
    s.add_argument("--os", choices=sorted(INSTALL), default=this_os)
    return p


def run(argv, post=None, env=None, now=None):
    """post: the door to the messengers (post_json; the tests give a fake one); env: where TEAMCALL_* settings are
    read; now: the unix time for WhatsApp's 24 hours."""
    args = parser().parse_args(argv)
    args.folder = os.path.abspath(os.path.expanduser(args.folder))
    policy = read_policy(args.folder)
    lang = pick_lang(args.lang, policy)
    words = lang_words(lang)

    if args.cmd == "plan":
        # a plan written again (another language, another sponsor) keeps the pilot's start unless --start moves it
        start = (parse_date(args.start, "--start") if args.start
                 else plan_start(read_journal(args.folder)) or datetime.date.today())
        text = charter_text(words, args.company, args.people, args.target, start, args.champion, args.sponsor, policy)
        if write_out(args, words, "charter_file", text):
            # the daily cards count the pilot's working days from this start (`teamcall lesson`)
            add_entry(args.folder, {"kind": "plan", "start": start.isoformat(), "people": args.people,
                                    "target": args.target, "date": datetime.date.today().isoformat()})
    elif args.cmd == "fast":
        write_out(args, words, "fast_file", fast_text(words, args.person, args.os, args.task, args.seat),
                  who=slug(args.person))
    elif args.cmd == "champion":
        write_out(args, words, "champion_file", champion_text(words, args.person), who=slug(args.person))
    elif args.cmd == "boost":
        files = boost_files(words, args.name, args.task)
        for rel, text in files.items():
            if args.print:
                sys.stdout.write("--- %s\n%s" % (rel, text))
                continue
            path = os.path.join(args.folder, rel)
            if os.path.exists(path):
                print(say(words, "kept", path=path))
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(say(words, "wrote", path=path))
    elif args.cmd == "claudemd":
        try:
            with open(args.file, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            raise Problem("cannot read %s: %s" % (args.file, exc.strerror))
        found = claudemd_problems(text)
        for kind, n in found:
            print(say(words, "claudemd_" + kind, n=n, max=CLAUDEMD_MAX))
        if not found:
            print(say(words, "claudemd_ok", n=len(text.splitlines()), max=CLAUDEMD_MAX))
        return 1 if found else 0
    elif args.cmd == "log":
        if args.action == "show":
            for e in read_journal(args.folder):
                print(json.dumps(e, ensure_ascii=False, sort_keys=True))
            return 0
        if not args.person or not args.stage:
            raise Problem("log add needs --person and --stage")
        add_entry(args.folder, {"kind": "step", "person": args.person, "stage": args.stage,
                                "date": parse_date(args.date).isoformat(), "minutes": args.minutes,
                                "help_minutes": args.help_minutes, "blocker": args.blocker or "",
                                "artifact": args.artifact or ""})
        print(say(words, "logged", person=args.person, stage=say(words, "stage_" + args.stage)))
    elif args.cmd == "measure":
        entry = {"kind": "measure", "person": args.person, "task": args.task,
                 "date": parse_date(args.date).isoformat(), "repeatable": bool(args.repeatable)}
        for key in ("before_min", "after_min", "quality", "coverage_before", "coverage_after", "capability", "risk"):
            value = getattr(args, key)
            if value is not None:
                entry[key] = value
        add_entry(args.folder, entry)
        print(say(words, "measured", person=args.person))
    elif args.cmd == "report":
        write_out(args, words, "report_file", report_text(words, read_journal(args.folder),
                                                          parse_date(args.until, "--until"), args.max_help))
    elif args.cmd == "decide":
        write_out(args, words, "decide_file", decide_text(words, read_journal(args.folder),
                                                          parse_date(args.until, "--until"), args.max_help))
    elif args.cmd == "move":
        rows = load_agents()
        found, _notes = detect(rows)
        write_out(args, words, "move_file", move_text(words, rows, parse_date(args.start, "--start"),
                                                      {i for i, _n, path in found if path}))
    elif args.cmd == "agents":
        sys.stdout.write(agents_text(words, load_agents(), args.seat))
    elif args.cmd == "detect":
        found, notes = detect(load_agents())
        for _id, name, path in found:
            print("%s: %s" % (name, path or say(words, "not_installed")))
        for n in notes:
            print(say(words, "note_" + n))
    elif args.cmd == "lesson":
        # post_json is looked up here, at the call: a test that replaces it is sure no lesson reaches the network
        return lesson_run(args, words, lang, post or post_json, env, now)
    return 0


def main(argv=None, post=None, env=None, now=None):
    try:
        return run(sys.argv[1:] if argv is None else argv, post, env, now)
    except Problem as exc:
        print("teamcall: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
