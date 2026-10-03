"""teamcall: the charter, the paths, termboost, the journal, the report, the decision and the agents table."""
import datetime
import importlib.util
import io
import json
import os
import re
import contextlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("teamcall", ROOT / "skills" / "teamcall" / "scripts" / "teamcall.py")
tc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tc)

EN = tc.lang_words("en")
D = datetime.date


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = tc.main(list(argv))
    return code, out.getvalue()


def journal(tmp_path, steps):
    for person, stage, day, help_minutes in steps:
        tc.add_entry(str(tmp_path), {"kind": "step", "person": person, "stage": stage, "date": day,
                                      "minutes": 10, "help_minutes": help_minutes, "blocker": "", "artifact": ""})
    return tc.read_journal(str(tmp_path))


class TestCharter:
    def test_waves_grow_from_the_first_people_to_the_target(self):
        w = tc.waves(5, 30)
        assert [n for _, n, _ in w] == [5, 5, 17, 30]
        assert w[-1][2] == 4          # 25 more people, one champion per 8 -> 4

    def test_waves_refuse_a_target_below_the_start(self):
        with pytest.raises(tc.Problem):
            tc.waves(10, 5)

    def test_charter_names_the_six_measurements_the_key_number_and_the_policy(self):
        text = tc.charter_text(EN, "Acme", 5, 30, D(2026, 10, 5), "Bea", "Sam",
                               {"red_paths": ["~/Company/HR"], "allowed_providers": ["anthropic"]})
        for m in tc.MEASURES:
            assert EN["m_" + m] in text
        assert EN["charter_key_metric"] in text
        assert "2026-11-04" in text
        assert "`~/Company/HR`" in text and "anthropic" in text
        assert "At least 3 working results" in text

    def test_plan_writes_the_file_named_in_the_persons_language(self, tmp_path):
        code, _ = run("plan", "--company", "Acme", "--start", "2026-10-05", "--folder", str(tmp_path), "--lang", "ru")
        assert code == 0
        name = tc.lang_words("ru")["charter_file"]
        assert (tmp_path / name).is_file()

    def test_the_policy_language_is_used_when_none_is_asked(self, tmp_path):
        (tmp_path / "company-ai-policy.json").write_text(json.dumps({"language": "es"}))
        run("plan", "--company", "Acme", "--folder", str(tmp_path))
        assert (tmp_path / tc.lang_words("es")["charter_file"]).is_file()


class TestPaths:
    def test_the_fast_path_is_20_minutes(self):
        assert sum(m for _, m in tc.FAST_STEPS) == 20

    def test_the_champion_path_is_5_hours(self):
        assert sum(m for _, m in tc.CHAMPION_STEPS) == 300

    def test_the_fast_card_carries_the_install_line_of_the_system(self):
        assert tc.INSTALL["windows"] in tc.fast_text(EN, "Ann", "windows", "a report", None)
        assert tc.INSTALL["mac"] in tc.fast_text(EN, "Ann", "mac", None, None)

    def test_a_claudemd_over_100_lines_is_red(self, tmp_path):
        long = tmp_path / "CLAUDE.md"
        long.write_text("rule\n" * 101)
        assert run("claudemd", str(long))[0] == 1
        long.write_text("rule\n" * 100)
        assert run("claudemd", str(long))[0] == 0
        long.write_text("")
        assert run("claudemd", str(long))[0] == 1


class TestBoost:
    def test_boost_writes_a_project_skill_and_a_card(self, tmp_path):
        code, _ = run("boost", "--name", "Weekly Report", "--task", "the weekly report", "--folder", str(tmp_path))
        assert code == 0
        skill = tmp_path / ".claude" / "skills" / "weekly-report" / "SKILL.md"
        text = skill.read_text()
        assert text.startswith("---\nname: weekly-report\n")
        assert "the weekly report" in text
        assert (tmp_path / EN["boost_file"].format(name="weekly-report")).is_file()

    def test_boost_never_overwrites_a_skill_that_is_there(self, tmp_path):
        skill = tmp_path / ".claude" / "skills" / "x" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("mine")
        run("boost", "--name", "x", "--task", "t", "--folder", str(tmp_path))
        assert skill.read_text() == "mine"


class TestJournal:
    def test_the_furthest_stage_counts_and_stopped_holds_until_a_later_step(self, tmp_path):
        entries = journal(tmp_path, [("A", "installed", "2026-10-05", 0), ("A", "first_artifact", "2026-10-07", 15),
                                     ("A", "installed", "2026-10-08", 0),
                                     ("B", "installed", "2026-10-05", 0), ("B", "stopped", "2026-10-06", 5)])
        people = tc.people_state(entries)
        assert people["A"]["stage"] == "first_artifact"
        assert people["B"]["stage"] == "stopped"
        entries = journal(tmp_path, [("B", "first_task", "2026-10-09", 0)])
        assert tc.people_state(entries)["B"]["stage"] == "first_task"

    def test_an_unknown_stage_in_the_journal_is_a_problem(self, tmp_path):
        tc.add_entry(str(tmp_path), {"kind": "step", "person": "A", "stage": "maybe", "date": "2026-10-05"})
        with pytest.raises(tc.Problem):
            tc.people_state(tc.read_journal(str(tmp_path)))

    def test_log_add_from_the_command_line(self, tmp_path):
        code, _ = run("log", "add", "--person", "Ann", "--stage", "installed", "--folder", str(tmp_path))
        assert code == 0
        assert tc.read_journal(str(tmp_path))[0]["stage"] == "installed"


class TestReport:
    STEPS = [("Ann Lee", "first_artifact", "2026-10-07", 20), ("Bob Roe", "champion", "2026-10-08", 30),
             ("Cy Doe", "first_artifact", "2026-10-09", 40), ("Di Poe", "stopped", "2026-10-09", 0),
             ("Ed Moe", "installed", "2026-10-05", 0)]

    def test_the_key_number_is_help_minutes_per_successful_first_result(self, tmp_path):
        s = tc.summary(journal(tmp_path, self.STEPS))
        assert (s["count"], s["succeeded"], s["champions"], s["stopped"]) == (5, 3, 1, 1)
        assert s["help_per_artifact"] == pytest.approx(30)

    def test_the_report_never_carries_a_name(self, tmp_path):
        entries = journal(tmp_path, self.STEPS)
        tc.add_entry(str(tmp_path), {"kind": "measure", "person": "Ann Lee", "task": "report", "date": "2026-10-07",
                                      "before_min": 90, "after_min": 27, "repeatable": True})
        text = tc.report_text(EN, tc.read_journal(str(tmp_path)), D(2026, 10, 30))
        for name in ("Ann", "Bob", "Cy", "Di", "Ed"):
            assert name not in text
        assert "P1" in text and "90 -> 27 min" in text
        for m in tc.MEASURES:
            assert EN["m_" + m] in text

    def test_until_leaves_later_steps_out(self, tmp_path):
        s = tc.summary(journal(tmp_path, self.STEPS), D(2026, 10, 7))
        assert s["succeeded"] == 1


class TestDecision:
    def base(self, **kw):
        s = {"count": 5, "succeeded": 3, "champions": 1, "help_per_artifact": 30.0}
        s.update(kw)
        return s

    def test_three_of_five_with_a_champion_within_the_limit_scales(self):
        assert tc.decision(self.base(), 60) == "scale"

    def test_two_of_five_is_fix_and_repeat(self):
        assert tc.decision(self.base(succeeded=2), 60) == "repeat"

    def test_no_champion_is_fix_and_repeat(self):
        assert tc.decision(self.base(champions=0), 60) == "repeat"

    def test_too_much_help_is_fix_and_repeat(self):
        assert tc.decision(self.base(help_per_artifact=61.0), 60) == "repeat"

    def test_no_working_result_stops(self):
        assert tc.decision(self.base(succeeded=0, help_per_artifact=None), 60) == "stop"
        assert tc.decision(self.base(count=0, succeeded=0, help_per_artifact=None), 60) == "stop"

    def test_decide_writes_its_page(self, tmp_path):
        journal(tmp_path, TestReport.STEPS)
        code, _ = run("decide", "--until", "2026-10-30", "--folder", str(tmp_path))
        assert code == 0
        assert EN["decision_scale"] in (tmp_path / EN["decide_file"]).read_text()


class TestAgents:
    def test_every_row_names_its_page_its_day_and_a_known_rule(self):
        assert tc.agents_problems(tc.load_agents()) == []

    def test_the_rules_of_the_plan_are_in_the_table(self):
        rules = {r["id"]: r.get("rule") for r in tc.load_agents()}
        assert rules["grok-build"] == "copy_only_prepaid"
        assert rules["kimi-code"] == "training_only"
        assert rules["antigravity"] == "no_blanket_permission"

    def test_the_agents_the_plan_names_are_all_there(self):
        ids = {r["id"] for r in tc.load_agents()}
        assert {"claude-code", "codex", "antigravity", "gemini-cli", "copilot-cli", "grok-build", "muse-code", "kiro",
                "cursor-cli", "opencode", "qwen-code", "kimi-code", "goose", "aider", "sidecall",
                "roundcall"} <= ids

    def test_a_row_without_a_page_or_with_an_unknown_rule_is_red(self):
        rows = [dict(tc.load_agents()[0])]
        rows[0]["url"] = "http://x"
        rows.append(dict(tc.load_agents()[1], id="other", rule="anything"))
        assert len(tc.agents_problems(rows)) == 2

    def test_detect_finds_programs_and_names_what_turns_the_remote_off(self, tmp_path):
        rows = [{"id": "claude-code", "name": "Claude Code", "binaries": ["claude"]},
                {"id": "kimi-code", "name": "Kimi", "binaries": ["kimi"]}]
        (tmp_path / ".claude.json").write_text(json.dumps({"oauthAccount": {"x": 1}}))
        found, notes = tc.detect(rows, env={"ANTHROPIC_API_KEY": "k", "ANTHROPIC_BASE_URL": "http://localhost:4000"},
                                 which=lambda b: "/bin/claude" if b == "claude" else None, home=str(tmp_path))
        assert found == [("claude-code", "Claude Code", "/bin/claude"), ("kimi-code", "Kimi", None)]
        assert notes == ["api_key", "base_url", "signed_in"]

    def test_the_agents_table_prints(self):
        code, out = run("agents", "--seat", "Copilot")
        assert code == 0 and "GitHub Copilot CLI" in out and "Codex CLI" not in out


class TestWords:
    def keys_used(self):
        src = (ROOT / "skills" / "teamcall" / "scripts" / "teamcall.py").read_text()
        keys = set(re.findall(r'say\(words, "([a-z_0-9]+)"', src))
        keys = {k for k in keys if not k.endswith("_")}
        keys |= {"charter_file", "fast_file", "champion_file", "report_file", "decide_file", "move_file"}
        keys |= {k for k, _ in tc.FAST_STEPS} | {k + "_how" for k, _ in tc.FAST_STEPS}
        keys |= {k for k, _ in tc.CHAMPION_STEPS} | {k + "_how" for k, _ in tc.CHAMPION_STEPS}
        keys |= {"m_" + m for m in tc.MEASURES} | {"m_%s_example" % m for m in tc.MEASURES}
        keys |= {"stage_" + s for s in tc.STAGES} | {"rule_" + r for r in tc.RULES}
        for d in ("scale", "repeat", "stop"):
            keys |= {"decision_" + d, "decide_why_" + d, "decide_next_" + d}
        keys |= {"note_" + n for n in ("api_key", "base_url", "traffic", "signed_in")}
        keys |= {"claudemd_too_long", "claudemd_empty"} | {"move_w%d" % n for n in range(1, 5)}
        keys |= set(re.findall(r'"((?:setup|gives)_[a-z_]+)"', src))
        return keys

    @pytest.mark.parametrize("code", tc.LANGS)
    def test_every_dictionary_has_every_word(self, code):
        own = json.loads((ROOT / "lang" / ("%s.json" % code)).read_text(encoding="utf-8"))
        missing = sorted(k for k in self.keys_used() if k not in own)
        assert missing == []

    @pytest.mark.parametrize("code", tc.LANGS)
    def test_placeholders_match_english(self, code):
        own = json.loads((ROOT / "lang" / ("%s.json" % code)).read_text(encoding="utf-8"))
        for key, text in EN.items():
            if isinstance(text, str) and key in own:
                assert set(re.findall(r"\{\w+\}", text)) == set(re.findall(r"\{\w+\}", own[key])), (code, key)

    def test_file_names_have_no_path_separator(self):
        for code in tc.LANGS:
            words = tc.lang_words(code)
            for key in ("charter_file", "fast_file", "champion_file", "report_file", "decide_file", "move_file",
                        "boost_file"):
                assert "/" not in words[key] and words[key].endswith(".md")


class TestRules:
    def test_no_network_module(self):
        net = re.compile(r"^\s*(?:import|from)\s+(urllib|http\.client|socket|requests|httpx|ftplib|smtplib)\b", re.M)
        for path in ROOT.rglob("*.py"):
            if "tests" in path.parts:
                continue
            assert not net.search(path.read_text(encoding="utf-8")), path

    def test_no_bin_folder_and_the_common_files(self):
        assert not (ROOT / "bin").exists()
        for name in ("LICENSE", "NOTICE", "SECURITY.md", ".zenodo.json", "CHANGELOG.md"):
            assert (ROOT / name).is_file(), name
        readme = (ROOT / "README.md").read_text()
        assert "github.com/vadimchernets/teamcall" in readme and "buys nothing" in readme

    def test_manifest_and_catalogue_agree(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        assert plugin["name"] == "teamcall" and plugin["license"] == "Apache-2.0"
        assert market["plugins"][0]["version"] == plugin["version"] == market["metadata"]["version"]
        assert "## %s" % plugin["version"] in (ROOT / "CHANGELOG.md").read_text()
