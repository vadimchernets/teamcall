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

Common options: --folder DIR (the company's folder, default the current one), --lang en|es|pt|ru|uk, --print
(print instead of writing a file). Every file it writes goes into --folder; the journal is
teamcall-journal.jsonl there. Python standard library only; nothing goes to the network.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

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
                "setup_install", "setup_contact", "setup_actions", "setup_retention"):
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
    lines += ["", say(words, "report_decision", decision=say(words, "decision_" + decision(s, max_help))), ""]
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


# ---------------------------------------------------------------- the command line --------------

def parser():
    p = argparse.ArgumentParser(prog="teamcall", description=__doc__.split("\n\n")[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--folder", default=os.getcwd())
    common.add_argument("--lang", choices=LANGS)
    common.add_argument("--print", action="store_true")
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
    s.add_argument("--os", choices=sorted(INSTALL), default={"darwin": "mac", "win32": "windows"}.get(sys.platform, "linux"))
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
    return p


def run(argv):
    args = parser().parse_args(argv)
    args.folder = os.path.abspath(os.path.expanduser(args.folder))
    policy = read_policy(args.folder)
    words = lang_words(pick_lang(args.lang, policy))

    if args.cmd == "plan":
        text = charter_text(words, args.company, args.people, args.target, parse_date(args.start, "--start"),
                            args.champion, args.sponsor, policy)
        write_out(args, words, "charter_file", text)
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
    return 0


def main(argv=None):
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except Problem as exc:
        print("teamcall: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
