"""teamcall lesson: one card a day in Telegram or WhatsApp, its buttons counted into the journal, the report without
names. No test here reaches the network: every messenger call goes to a fake transport (Wire) that records it and
answers the way the Bot API and the Cloud API do, and the real door (post_json) is shut for every test - a call to it
fails the test. The door itself is tested with urlopen replaced."""
import contextlib
import datetime
import hashlib
import hmac
import html
import http.client
import importlib.util
import io
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import types
import urllib.error
import urllib.request
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("teamcall", ROOT / "skills" / "teamcall" / "scripts" / "teamcall.py")
tc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tc)

REAL_DOOR = tc.post_json
EN = tc.lang_words("en")
D = datetime.date
DOT = "·"
TOKEN = "123456:ABC-def_ghi"
WA_TOKEN = "wa-token-1"
PHONE_ID = "1098765"
APP_SECRET = "app-secret-1"
VERIFY = "verify-1"
MONDAY = "2026-10-05"
NUMBER = "34600111222"
USER = "US.13491208655302741918"            # Meta's own example of a WhatsApp business-scoped user id
OTHER_USER = "US.20511344117890034512"
NOW = int(datetime.datetime(2026, 10, 7, 9, 0, tzinfo=datetime.timezone.utc).timestamp())


@pytest.fixture(autouse=True)
def door_shut(monkeypatch):
    def shut(*_args, **_kwargs):
        raise AssertionError("a test reached the real network door")
    monkeypatch.setattr(tc, "post_json", shut)


class Wire:
    """The messengers as a test sees them: every request recorded; the answer to a method comes from a list (one per
    call), a fixed (status, body), or a plain success shaped like the real one."""

    def __init__(self, **answers):
        self.calls = []
        self.answers = answers

    def __call__(self, url, payload, headers=None, timeout=30):
        method = url.rsplit("/", 1)[-1]
        self.calls.append({"url": url, "method": method, "payload": payload, "headers": headers or {},
                           "timeout": timeout})
        answer = self.answers.get(method)
        if isinstance(answer, list) and answer:
            return answer.pop(0)
        if isinstance(answer, tuple):
            return answer
        if url.startswith(tc.WHATSAPP_API):
            return 200, {"messaging_product": "whatsapp", "messages": [{"id": "wamid.out%d" % len(self.calls)}]}
        if method == "getUpdates":
            return 200, {"ok": True, "result": []}
        return 200, {"ok": True, "result": {"message_id": len(self.calls)}}

    def sent(self, method):
        return [c["payload"] for c in self.calls if c["method"] == method]


def settings(folder, **more):
    conf = {"TEAMCALL_ENV_FILE": str(Path(folder) / "no.env"), "TEAMCALL_TELEGRAM_TOKEN": TOKEN,
            "TEAMCALL_WHATSAPP_TOKEN": WA_TOKEN, "TEAMCALL_WHATSAPP_PHONE_ID": PHONE_ID,
            "TEAMCALL_WHATSAPP_APP_SECRET": APP_SECRET, "TEAMCALL_WHATSAPP_VERIFY_TOKEN": VERIFY}
    conf.update(more)
    return conf


def lesson(folder, *argv, wire=None, env=None, now=NOW):
    """`teamcall lesson ...` in `folder`, through the fake wire. -> (exit code, what it printed)."""
    argv = [str(a) for a in argv]
    if "--lang" not in argv:
        argv += ["--lang", "en"]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = tc.main(["lesson"] + argv + ["--folder", str(folder)], post=wire if wire is not None else Wire(),
                       env=settings(folder, **(env or {})), now=now)
    return code, out.getvalue()


def cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = tc.main(list(argv))
    return code, out.getvalue()


def kinds(folder, kind):
    return [e for e in tc.read_journal(str(folder)) if e.get("kind") == kind]


def updates(*items):
    return Wire(getUpdates=[(200, {"ok": True, "result": list(items)})])


def tg_message(update_id, chat, text):
    return {"update_id": update_id, "message": {"message_id": update_id, "date": NOW, "text": text,
                                                 "chat": {"id": chat, "type": "private"}, "from": {"id": chat}}}


def tg_press(update_id, chat, data):
    return {"update_id": update_id, "callback_query": {"id": "cq%d" % update_id, "data": data, "from": {"id": chat},
                                                         "message": {"message_id": 1,
                                                                     "chat": {"id": chat, "type": "private"}}}}


def join(folder, person, chat, lang="en"):
    """A person joins the Telegram cards: the invite link, then /start <code> from their own chat."""
    code, out = lesson(folder, "invite", "--person", person, "--bot", "acme_bot", "--lang", lang)
    assert code == 0, out
    start = re.search(r"https://t\.me/acme_bot\?start=([A-Za-z0-9_-]{8,64})", out)
    assert start, out
    lesson(folder, "pull", wire=updates(tg_message(chat, chat, "/start " + start.group(1))))
    return start.group(1)


def wa_message(number, msg_id, kind, value, ts=NOW, user_id=None):
    """One message as Meta's webhook brings it. With user_id it carries the person's business-scoped user id too
    (from_user_id); with number None it is Meta's own example of a person with a username: the user id alone."""
    m = {"id": msg_id, "timestamp": str(ts), "type": kind}
    contact = {"profile": {"name": "B"}}
    if number:
        m["from"] = contact["wa_id"] = number
    if user_id:
        m["from_user_id"] = contact["user_id"] = user_id
    if kind == "text":
        m["text"] = {"body": value}
    elif kind == "interactive":
        m["interactive"] = {"type": "button_reply", "button_reply": {"id": value, "title": "x"}}
    elif kind == "button":
        m["button"] = {"payload": value, "text": "x"}
    value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": PHONE_ID}, "contacts": [contact],
             "messages": [m]}
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages",
                                                                                         "value": value}]}]}


def words_for(code):
    return tc.lang_words(code if code in tc.LANGS else "en")


def wa_post(folder, payload, secret=APP_SECRET, wire=None):
    """One webhook POST from Meta, signed with `secret`. -> ((status, text), the wire)."""
    body = json.dumps(payload).encode("utf-8")
    signature = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    wire = wire if wire is not None else Wire()
    answer = tc.whatsapp_webhook("POST", "/", {"X-Hub-Signature-256": signature}, body, str(folder),
                                 settings(folder), wire, words_for, now=NOW, today=D(2026, 10, 7))
    return answer, wire


def wa_join(folder, lang="en"):
    code, out = lesson(folder, "invite", "--person", "Bea Diaz", "--channel", "whatsapp", "--phone", "+34 600 111 222",
                       "--lang", lang)
    assert code == 0, out


def tg_cards(wire):
    """The cards a wire carried to Telegram, by number."""
    return [int(c["payload"]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[1])
            for c in wire.calls if c["method"] == "sendMessage" and "reply_markup" in c["payload"]]


def plan(folder, *more):
    code, out = cli("plan", "--company", "Acme", "--folder", str(folder), "--lang", "en", *more)
    assert code == 0, out


def wa_statuses(*statuses):
    value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": PHONE_ID}, "statuses": list(statuses)}
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages",
                                                                                         "value": value}]}]}


class TestCards:
    def test_one_card_per_working_day_for_four_weeks(self):
        start = D(2026, 10, 5)                                  # a Monday
        assert tc.card_day(start, start) == 1
        assert tc.card_day(start, D(2026, 10, 9)) == 5          # Friday
        assert tc.card_day(start, D(2026, 10, 10)) is None      # Saturday
        assert tc.card_day(start, D(2026, 10, 12)) == 6
        assert tc.card_day(start, D(2026, 10, 30)) == 20        # the last Friday of week 4
        assert tc.card_day(start, D(2026, 11, 2)) is None       # after the last card
        assert tc.card_day(start, D(2026, 10, 2)) is None       # before the start
        assert tc.card_day(D(2026, 10, 3), D(2026, 10, 5)) == 1   # a Saturday start begins on Monday

    def test_every_card_is_in_every_language_and_fits_the_messengers(self):
        for code in tc.LANGS:
            own = json.loads((ROOT / "lang" / ("%s.json" % code)).read_text(encoding="utf-8"))
            words = tc.lang_words(code)
            for a in tc.ANSWERS:
                assert 0 < len(own["lesson_" + a]) <= 20, (code, a)     # WhatsApp: a reply button's title
            for n in range(1, tc.CARDS + 1):
                for part in ("title", "text", "show"):
                    assert own.get("card_%d_%s" % (n, part)), (code, n, part)
                head, text, example = tc.card_parts(words, n)
                assert len("*%s*\n\n%s" % (head, text)) <= 1024, (code, n)   # WhatsApp: an interactive body
                assert len(head) <= 60 and len(example) <= 1024, (code, n)
            assert 0 < len(own["lesson_open"]) <= 20, code                 # WhatsApp: a quick reply's title
            assert len(tc.say(words, "lesson_template", n="%d/%d" % (tc.CARDS, tc.CARDS))) <= 1024, code

    def test_the_translations_keep_the_numbers_of_the_base(self):
        """A number in an English card is in each translation too; a difference is a warning, not a failure."""
        for code in tc.LANGS[1:]:
            words = tc.lang_words(code)
            for key, text in EN.items():
                if key.startswith("card_") and isinstance(text, str):
                    if sorted(re.findall(r"\d+", text)) != sorted(re.findall(r"\d+", words[key])):
                        warnings.warn("%s %s: the numbers differ from English" % (code, key))

    def test_the_card_of_the_day_follows_the_plan(self, tmp_path):
        code, _ = cli("plan", "--company", "Acme", "--start", MONDAY, "--folder", str(tmp_path), "--lang", "en")
        assert code == 0
        assert [e["start"] for e in kinds(tmp_path, "plan")] == [MONDAY]
        code, out = lesson(tmp_path, "card", "--date", "2026-10-07")
        assert code == 0
        assert tc.card_parts(EN, 3)[0] in out and EN["card_3_text"] in out and EN["card_3_show"] in out
        code, out = lesson(tmp_path, "card", "--date", "2026-10-10")
        assert (code, out.strip()) == (0, tc.say(EN, "lesson_no_card", date="2026-10-10", total=tc.CARDS))

    def test_a_printed_plan_leaves_the_journal_alone(self, tmp_path):
        cli("plan", "--company", "Acme", "--print", "--folder", str(tmp_path))
        assert tc.read_journal(str(tmp_path)) == []

    def test_no_start_is_said_in_one_line(self, tmp_path):
        code, out = lesson(tmp_path, "card")
        assert code == 2 and "teamcall plan --start" in out

    def test_the_cards_go_without_a_plan_too(self, tmp_path):
        """Each person's own way through the cards needs no pilot start: card 1 goes on their first working day."""
        join(tmp_path, "Ann Lee", 111)
        wire = Wire()
        code, out = lesson(tmp_path, "send", "--date", "2026-10-07", wire=wire)
        assert code == 0 and tg_cards(wire) == [1], out


class TestTelegram:
    def test_an_invite_link_then_start_joins_the_chat(self, tmp_path):
        code, out = lesson(tmp_path, "invite", "--person", "Ann Lee", "--bot", "@acme_bot")
        assert code == 0
        start = re.search(r"https://t\.me/acme_bot\?start=([A-Za-z0-9_-]{8,64})", out)
        assert start, out
        wire = updates(tg_message(10, 111, "/start " + start.group(1)))
        code, out = lesson(tmp_path, "pull", wire=wire)
        assert code == 0
        assert [(c["person"], c["chat"]) for c in kinds(tmp_path, "lesson_chat")] == [("Ann Lee", "111")]
        assert wire.calls[0]["url"] == "https://api.telegram.org/bot%s/getUpdates" % TOKEN
        welcome = tc.say(EN, "lesson_welcome", stop="/stop", start="/start", card="/card")
        assert "/card" in welcome and "/stop" in welcome
        assert wire.sent("sendMessage") == [{"chat_id": "111", "text": welcome}]
        assert kinds(tmp_path, "lesson_offset")[-1]["offset"] == 11
        assert tc.say(EN, "lesson_pulled", answers=0, joined=1, stopped=0) in out

    def test_invite_asks_the_bot_its_name_when_none_is_given(self, tmp_path):
        wire = Wire(getMe=(200, {"ok": True, "result": {"id": 1, "is_bot": True, "username": "acme_cards_bot"}}))
        code, out = lesson(tmp_path, "invite", "--person", "Ann Lee", wire=wire)
        assert code == 0 and "https://t.me/acme_cards_bot?start=" in out
        assert [c["method"] for c in wire.calls] == ["getMe"]

    def test_a_used_link_does_not_join_a_second_chat(self, tmp_path):
        start = join(tmp_path, "Ann Lee", 111)
        wire = updates(tg_message(300, 222, "/start " + start))
        lesson(tmp_path, "pull", wire=wire)
        assert [c["chat"] for c in kinds(tmp_path, "lesson_chat")] == ["111"]
        assert wire.sent("sendMessage") == [{"chat_id": "222", "text": EN["lesson_unknown_link"]}]

    def test_send_puts_the_persons_next_card_with_its_three_buttons(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        wire = Wire()
        code, out = lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-07", wire=wire)
        assert code == 0
        [call] = wire.calls
        assert call["url"] == "https://api.telegram.org/bot%s/sendMessage" % TOKEN
        message = call["payload"]
        head, text, _example = tc.card_parts(EN, 1)                 # her first card, whatever the pilot's day
        assert message["chat_id"] == "111" and message["parse_mode"] == "HTML"
        assert message["text"] == "<b>%s</b>\n\n%s" % (html.escape(head, False), html.escape(text, False))
        assert message["reply_markup"] == {"inline_keyboard": [[
            {"text": "Done", "callback_data": "tc1:1:done"}, {"text": "Show me", "callback_data": "tc1:1:show"},
            {"text": "Skip", "callback_data": "tc1:1:skip"}]]}
        assert [(e["person"], e["card"]) for e in kinds(tmp_path, "lesson_sent")] == [("Ann Lee", 1)]
        assert tc.say(EN, "lesson_sent", channel="telegram", total=20, sent=1, had=0, finished=0, failed=0) in out

    def test_the_same_card_goes_once_a_day(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-07")
        wire = Wire()
        code, out = lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-07", wire=wire)
        assert code == 0 and wire.calls == []
        assert tc.say(EN, "lesson_sent", channel="telegram", total=20, sent=0, had=1, finished=0, failed=0) in out

    def test_the_buttons_are_counted_and_show_me_sends_the_example(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-07")
        wire = updates(tg_press(500, 111, "tc1:3:show"), tg_press(501, 111, "tc1:3:done"))
        code, out = lesson(tmp_path, "pull", "--wait", "50", "--date", "2026-10-07", wire=wire)
        assert code == 0
        assert wire.calls[0]["payload"]["timeout"] == 50 and wire.calls[0]["payload"]["offset"] == 112
        assert [(e["card"], e["answer"]) for e in kinds(tmp_path, "lesson_answer")] == [(3, "show"), (3, "done")]
        assert wire.sent("answerCallbackQuery") == [{"callback_query_id": "cq500", "text": EN["lesson_ack_show"]},
                                                    {"callback_query_id": "cq501", "text": EN["lesson_ack_done"]}]
        head, _text, example = tc.card_parts(EN, 3)
        assert wire.sent("sendMessage") == [{"chat_id": "111", "parse_mode": "HTML", "text": "<b>%s</b>\n\n%s" % (
            html.escape(head, False), html.escape(example, False))}]
        assert tc.say(EN, "lesson_pulled", answers=2, joined=0, stopped=0) in out
        assert kinds(tmp_path, "lesson_offset")[-1]["offset"] == 502

    def test_a_press_from_a_stranger_or_off_the_card_is_not_counted(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        wire = updates(tg_press(600, 999, "tc1:3:done"), tg_press(601, 111, "tc1:3:maybe"),
                       tg_press(602, 111, "tc1:21:done"), tg_press(603, 111, "tc1:0:done"))
        lesson(tmp_path, "pull", wire=wire)
        assert kinds(tmp_path, "lesson_answer") == []
        assert [a["text"] for a in wire.sent("answerCallbackQuery")] == ["", "", "", ""]   # the spinner still stops

    def test_stop_ends_the_cards_and_start_brings_them_back(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        wire = updates(tg_message(700, 111, "/stop"))
        code, out = lesson(tmp_path, "pull", wire=wire)
        assert wire.sent("sendMessage") == [{"chat_id": "111", "text": tc.say(EN, "lesson_bye", start="/start")}]
        assert tc.say(EN, "lesson_pulled", answers=0, joined=0, stopped=1) in out
        wire = Wire()
        lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-07", wire=wire)
        assert wire.calls == []
        lesson(tmp_path, "pull", wire=updates(tg_message(701, 111, "/start")))
        wire = Wire()
        lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-08", wire=wire)
        assert [c["payload"]["chat_id"] for c in wire.calls] == ["111"]

    def test_a_blocked_bot_stops_the_cards_to_that_chat_and_never_shows_the_token(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        blocked = (403, {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"})
        code, out = lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-07", wire=Wire(sendMessage=blocked))
        assert code == 1
        assert "Forbidden: bot was blocked by the user" in out and TOKEN not in out
        assert [e["why"] for e in kinds(tmp_path, "lesson_stop")] == ["blocked"]
        wire = Wire()
        lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-08", wire=wire)
        assert wire.calls == []

    def test_no_connection_counts_as_not_delivered_and_the_others_still_go(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        join(tmp_path, "Cy Doe", 333)
        answers = [tc.Problem("cannot reach api.telegram.org: timed out"), None]

        def flaky(url, payload, headers=None, timeout=30):
            answer = answers.pop(0)
            if answer:
                raise answer
            return 200, {"ok": True, "result": {"message_id": 9}}
        code, out = lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-07", wire=flaky)
        assert code == 1 and "timed out" in out
        assert len(kinds(tmp_path, "lesson_sent")) == 1

    def test_the_card_goes_in_the_persons_language(self, tmp_path):
        join(tmp_path, "Olena", 333, lang="uk")
        wire = Wire()
        lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-07", wire=wire)
        uk = tc.lang_words("uk")
        message = wire.calls[0]["payload"]
        assert html.escape(uk["card_1_text"], False) in message["text"]
        assert [b["text"] for b in message["reply_markup"]["inline_keyboard"][0]] == [uk["lesson_" + a]
                                                                                     for a in tc.ANSWERS]

    def test_html_in_a_card_is_escaped_for_telegram(self):
        words = dict(EN, card_1_title="a <b> & c", card_1_text="x < y")
        message = tc.telegram_card(words, "1", 1)
        assert message["text"] == "<b>1/20 %s a &lt;b&gt; &amp; c</b>\n\nx &lt; y" % DOT


class TestTelegramWebhook:
    """With `lesson webhook` Telegram brings each Start and press to `lesson serve` the moment it is made, so nothing
    waits on the champion's computer: Telegram keeps an update only 24 hours, and a weekend with it off loses none."""

    URL = "https://cards.acme.example/telegram"

    def hook(self, folder, wire=None):
        wire = wire if wire is not None else Wire()
        code, out = lesson(folder, "webhook", "--url", self.URL, wire=wire)
        assert code == 0, out
        return wire, out

    def post(self, folder, update, secret=None):
        body = json.dumps(update).encode("utf-8")
        wire = Wire()
        headers = {"X-Telegram-Bot-Api-Secret-Token": tc.telegram_secret(TOKEN) if secret is None else secret}
        return tc.telegram_webhook(headers, body, str(folder), settings(folder), wire, words_for, now=NOW,
                                   today=D(2026, 10, 7)), wire

    def test_webhook_gives_telegram_the_address_and_the_bots_secret(self, tmp_path):
        wire, out = self.hook(tmp_path)
        secret = tc.telegram_secret(TOKEN)
        assert re.fullmatch(r"[0-9a-f]{64}", secret) and TOKEN.split(":")[1] not in secret
        assert wire.sent("setWebhook") == [{"url": self.URL, "secret_token": secret,
                                            "allowed_updates": ["message", "callback_query"]}]
        assert tc.say(EN, "lesson_webhook_on", url=self.URL) in out and TOKEN not in out
        for bad in ("http://cards.acme.example/telegram", "https://cards.acme.example/whatsapp"):
            code, out = lesson(tmp_path, "webhook", "--url", bad)
            assert code == 2 and "/telegram" in out

    def test_a_start_and_a_press_through_the_webhook_count_at_once_and_once(self, tmp_path):
        _code, out = lesson(tmp_path, "invite", "--person", "Ann Lee", "--bot", "acme_bot")
        start = re.search(r"start=([A-Za-z0-9_-]{8,64})", out).group(1)
        self.hook(tmp_path)
        answer, wire = self.post(tmp_path, tg_message(10, 111, "/start " + start))
        assert answer == (200, "ok") and [c["chat"] for c in kinds(tmp_path, "lesson_chat")] == ["111"]
        assert wire.sent("sendMessage") == [{"chat_id": "111", "text": tc.say(
            EN, "lesson_welcome", stop="/stop", start="/start", card="/card")}]
        answer, wire = self.post(tmp_path, tg_message(10, 111, "/start " + start))      # Telegram brings it again
        assert answer == (200, "ok") and wire.calls == [] and len(kinds(tmp_path, "lesson_chat")) == 1
        for _again in range(2):
            answer, wire = self.post(tmp_path, tg_press(11, 111, "tc1:1:done"))
            assert answer == (200, "ok")
        assert [(e["card"], e["answer"]) for e in kinds(tmp_path, "lesson_answer")] == [(1, "done")]

    def test_a_request_without_the_bots_secret_writes_nothing(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        self.hook(tmp_path)
        before = tc.read_journal(str(tmp_path))
        for secret in ("", "guess", TOKEN):
            answer, wire = self.post(tmp_path, tg_press(12, 111, "tc1:1:done"), secret=secret)
            assert answer == (403, "forbidden") and wire.calls == []
        assert tc.read_journal(str(tmp_path)) == before

    def test_serve_takes_telegram_and_pull_stands_down_until_webhook_off(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        self.hook(tmp_path)
        wire = Wire()
        code, out = lesson(tmp_path, "pull", wire=wire)                  # by hand it says where the presses go
        assert code == 2 and "lesson webhook --off" in out and wire.calls == []
        assert lesson(tmp_path, "pull", "--loop", "--if-set", wire=wire) == (0, "") and wire.calls == []
        handler = tc.webhook_handler(str(tmp_path), settings(tmp_path), Wire(), words_for)
        h = handler.__new__(handler)
        body = json.dumps(tg_press(13, 111, "tc1:1:skip")).encode("utf-8")
        h.path, h.rfile, h.wfile, h.command = "/telegram", io.BytesIO(body), io.BytesIO(), "POST"
        h.headers = {"Content-Length": str(len(body)), "X-Telegram-Bot-Api-Secret-Token": tc.telegram_secret(TOKEN)}
        h.request_version, h.requestline, h.client_address = "HTTP/1.1", "x", ("127.0.0.1", 0)
        h.do_POST()
        assert h.wfile.getvalue().split(b" ", 2)[1] == b"200"
        assert [(e["card"], e["answer"]) for e in kinds(tmp_path, "lesson_answer")] == [(1, "skip")]
        no_whatsapp = {"TEAMCALL_WHATSAPP_APP_SECRET": "", "TEAMCALL_WHATSAPP_VERIFY_TOKEN": ""}
        code, out = lesson(tmp_path, "serve", "--host", "256.0.0.1", env=no_whatsapp)   # Telegram alone is enough
        assert code == 2 and "cannot listen on 256.0.0.1:8080" in out and "TEAMCALL_WHATSAPP" not in out
        assert tc.say(EN, "lesson_serving_telegram", address="http://256.0.0.1:8080") in out
        wire = Wire()
        code, out = lesson(tmp_path, "webhook", "--off", wire=wire)
        assert code == 0 and [c["method"] for c in wire.calls] == ["deleteWebhook"]
        assert tc.say(EN, "lesson_webhook_off") in out
        wire = updates()
        assert lesson(tmp_path, "pull", wire=wire)[0] == 0 and [c["method"] for c in wire.calls] == ["getUpdates"]


class TestOwnPace:
    """Each chat goes through the 20 cards at its own pace, one a day from its first working day: a late joiner gets
    card 1, a missed day moves the cards, a second run the same day sends nothing."""

    def test_a_person_who_joins_in_week_3_starts_at_card_1(self, tmp_path):
        plan(tmp_path, "--start", MONDAY)
        join(tmp_path, "Ann Lee", 111)
        for day, card in (("2026-10-19", 1), ("2026-10-20", 2)):
            wire = Wire()
            code, out = lesson(tmp_path, "send", "--date", day, wire=wire)
            assert code == 0 and tg_cards(wire) == [card], (day, out)

    def test_a_person_who_joins_after_the_20th_working_day_still_gets_card_1(self, tmp_path):
        plan(tmp_path, "--start", MONDAY)
        assert tc.card_day(D(2026, 10, 5), D(2026, 11, 9)) is None             # the pilot's cards are over
        join(tmp_path, "Cy Doe", 333)
        wire = Wire()
        lesson(tmp_path, "send", "--date", "2026-11-09", wire=wire)
        assert tg_cards(wire) == [1]

    def test_a_second_run_the_same_day_sends_nothing(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        lesson(tmp_path, "send", "--date", "2026-10-05")
        for _run in range(3):                   # the schedule runs every 15 minutes
            wire = Wire()
            lesson(tmp_path, "send", "--date", "2026-10-05", wire=wire)
            assert wire.calls == []
        assert [e["card"] for e in kinds(tmp_path, "lesson_sent")] == [1]

    def test_a_day_nobody_sent_moves_the_cards_and_loses_none(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        got = []
        for day in ("2026-10-05", "2026-10-07", "2026-10-08"):        # Tuesday the computer stayed off
            wire = Wire()
            lesson(tmp_path, "send", "--date", day, wire=wire)
            got += tg_cards(wire)
        assert got == [1, 2, 3]

    def test_nobody_begins_before_the_pilots_start(self, tmp_path):
        plan(tmp_path, "--start", "2026-10-12")
        join(tmp_path, "Ann Lee", 111)
        wire = Wire()
        code, out = lesson(tmp_path, "send", "--date", "2026-10-07", wire=wire)
        assert code == 0 and wire.calls == []
        assert tc.say(EN, "lesson_waiting", count=1, date="2026-10-12") in out
        lesson(tmp_path, "send", "--date", "2026-10-12", wire=wire)
        assert tg_cards(wire) == [1]

    def test_a_chat_that_has_all_20_is_finished(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        for n in range(1, tc.CARDS + 1):
            tc.add_entry(str(tmp_path), {"kind": "lesson_sent", "person": "Ann Lee", "channel": "telegram",
                                         "chat": "111", "card": n, "as": "buttons", "date": "2026-09-%02d" % n,
                                         "msg": str(n)})
        wire = Wire()
        code, out = lesson(tmp_path, "send", "--date", "2026-10-07", wire=wire)
        assert code == 0 and wire.calls == []
        assert tc.say(EN, "lesson_sent", channel="telegram", total=20, sent=0, had=0, finished=1, failed=0) in out

    def test_a_plan_written_again_keeps_the_start_and_each_persons_next_card(self, tmp_path):
        plan(tmp_path, "--start", "2026-09-21")
        join(tmp_path, "Ann Lee", 111)
        for day in ("2026-09-21", "2026-09-22"):
            lesson(tmp_path, "send", "--date", day)
        code, out = cli("plan", "--company", "Acme", "--lang", "es", "--folder", str(tmp_path))   # no --start
        assert code == 0, out
        assert [e["start"] for e in kinds(tmp_path, "plan")] == ["2026-09-21", "2026-09-21"]
        wire = Wire()
        lesson(tmp_path, "send", "--date", "2026-10-05", wire=wire)
        assert tg_cards(wire) == [3]
        plan(tmp_path, "--start", "2026-10-12")                              # --start still moves it
        assert kinds(tmp_path, "plan")[-1]["start"] == "2026-10-12"

    def test_card_brings_the_card_of_the_day_again_and_any_message_nothing_more_on_telegram(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        lesson(tmp_path, "send", "--date", "2026-10-07")
        wire = updates(tg_message(800, 111, "/card"))
        lesson(tmp_path, "pull", "--date", "2026-10-07", wire=wire)
        assert tg_cards(wire) == [1]
        sent = kinds(tmp_path, "lesson_sent")
        assert [(e["card"], e.get("again", False)) for e in sent] == [(1, False), (1, True)]
        wire = Wire()                            # the card sent again is no card of the day: the next day brings 2
        lesson(tmp_path, "send", "--date", "2026-10-08", wire=wire)
        assert tg_cards(wire) == [2]

    def test_a_scheduled_run_that_sends_nothing_says_nothing(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        at = int(datetime.datetime(2026, 10, 7, 9, 30).timestamp())       # the computer's own clock
        code, out = lesson(tmp_path, "send", "--date", "2026-10-07", "--at", "09:00", now=at)
        assert code == 0 and tc.say(EN, "lesson_sent", channel="telegram", total=20, sent=1, had=0, finished=0,
                                    failed=0) in out
        code, out = lesson(tmp_path, "send", "--date", "2026-10-07", "--at", "09:00", now=at + 900)
        assert (code, out) == (0, "")
        early = int(datetime.datetime(2026, 10, 8, 8, 59).timestamp())
        code, out = lesson(tmp_path, "send", "--date", "2026-10-08", "--at", "09:00", now=early)
        assert code == 0 and out.strip() == tc.say(EN, "lesson_not_now", time="08:59", at="09:00", until="20:00")

    def test_the_first_scheduled_run_of_the_day_names_who_has_not_joined(self, tmp_path):
        """A Start pressed while the computer was off for more than a day never reaches teamcall (Telegram keeps an
        update 24 hours): the person stays invited, and the log says so every working morning."""
        lesson(tmp_path, "invite", "--person", "Dee Fox", "--bot", "acme_bot")
        not_joined = tc.say(EN, "lesson_not_joined", people="Dee Fox")
        first = int(datetime.datetime(2026, 10, 7, 9, 0).timestamp())
        code, out = lesson(tmp_path, "send", "--date", "2026-10-07", "--at", "09:00", now=first)
        assert code == 0 and out.splitlines() == [EN["lesson_nobody"], not_joined]
        code, out = lesson(tmp_path, "send", "--date", "2026-10-07", "--at", "09:00", now=first + 900)
        assert (code, out) == (0, "")                                    # later runs of the day stay quiet
        join(tmp_path, "Ann Lee", 111)
        code, out = lesson(tmp_path, "send", "--date", "2026-10-08", "--at", "09:00", now=first + 86400 + 600)
        assert not_joined in out and tc.say(EN, "lesson_sent", channel="telegram", total=20, sent=1, had=0,
                                            finished=0, failed=0) in out


class TestWhatsApp:
    def test_after_24_hours_the_card_goes_as_the_template(self, tmp_path):
        wa_join(tmp_path, lang="pt")
        wire = Wire()
        code, out = lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-07", wire=wire)
        assert code == 0, out
        [call] = wire.calls
        assert call["url"] == "https://graph.facebook.com/%s/%s/messages" % (tc.WHATSAPP_VERSION, PHONE_ID)
        assert call["headers"] == {"Authorization": "Bearer " + WA_TOKEN}
        message = call["payload"]
        assert message["to"] == NUMBER and message["type"] == "template"
        template = message["template"]
        assert template["name"] == "teamcall_card" and template["language"] == {"code": "pt_BR"}
        body, button = template["components"]
        assert body == {"type": "body", "parameters": [{"type": "text", "text": "1/20"}]}
        assert button == {"type": "button", "sub_type": "quick_reply", "index": "0",
                          "parameters": [{"type": "payload", "payload": "tc1:1:open"}]}
        pt = tc.lang_words("pt")                 # the note carries no lesson text: the card follows the tap
        assert pt["card_1_text"] not in json.dumps(message, ensure_ascii=False)
        assert kinds(tmp_path, "lesson_sent")[0]["as"] == "template"
        assert WA_TOKEN not in out

    def test_inside_24_hours_the_card_goes_with_reply_buttons(self, tmp_path):
        wa_join(tmp_path)
        answer, wire = wa_post(tmp_path, wa_message(NUMBER, "wamid.A", "text", "hello", ts=NOW - 3600))
        assert answer == (200, "ok")
        [message] = wire.sent("messages")      # the person wrote: their next card comes at once, with its buttons
        assert message["type"] == "interactive" and message["interactive"]["type"] == "button"
        head, text, _example = tc.card_parts(EN, 1)
        assert message["interactive"]["body"] == {"text": "*%s*\n\n%s" % (head, text)}
        assert message["interactive"]["action"]["buttons"] == [
            {"type": "reply", "reply": {"id": "tc1:1:%s" % a, "title": EN["lesson_" + a]}} for a in tc.ANSWERS]
        assert kinds(tmp_path, "lesson_sent")[0]["as"] == "buttons"
        wire = Wire()                          # the next day, still inside the 24 hours of that message
        lesson(tmp_path, "send", "--date", "2026-10-08", wire=wire, now=NOW + 20 * 3600)
        [message] = wire.sent("messages")
        assert message["type"] == "interactive" and message["interactive"]["action"]["buttons"][0]["reply"]["id"] == (
            "tc1:2:done")
        assert kinds(tmp_path, "lesson_sent")[-1]["as"] == "buttons"

    def test_the_notes_button_brings_the_card_itself(self, tmp_path):
        wa_join(tmp_path)
        lesson(tmp_path, "send", "--date", "2026-10-07")                       # the note, after the 24 hours
        answer, wire = wa_post(tmp_path, wa_message(NUMBER, "wamid.O", "button", "tc1:1:open"))
        assert answer == (200, "ok")
        [message] = wire.sent("messages")
        assert message["type"] == "interactive" and EN["card_1_text"] in message["interactive"]["body"]["text"]
        assert kinds(tmp_path, "lesson_answer") == []                           # open is no answer
        assert [(e["as"], e.get("again", False)) for e in kinds(tmp_path, "lesson_sent")] == [
            ("template", False), ("buttons", True)]

    def test_a_card_meta_did_not_deliver_is_not_counted_and_comes_when_the_person_writes(self, tmp_path):
        wa_join(tmp_path)
        sent = Wire(messages=(200, {"messaging_product": "whatsapp", "messages": [{"id": "wamid.T1"}]}))
        lesson(tmp_path, "send", "--date", "2026-10-07", wire=sent)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            answer, _wire = wa_post(tmp_path, wa_statuses({
                "id": "wamid.T1", "status": "failed", "timestamp": str(NOW), "recipient_id": NUMBER,
                "errors": [{"code": 131049, "title": "This message was not delivered to maintain healthy ecosystem "
                                                      "engagement."}]}))
        assert answer == (200, "ok") and "131049" in out.getvalue()
        assert [(e["msg"], e["card"]) for e in kinds(tmp_path, "lesson_undelivered")] == [("wamid.T1", 1)]
        text = tc.report_text(EN, tc.read_journal(str(tmp_path)), D(2026, 10, 30))
        assert EN["report_lessons_none"] in text                                # not delivered is not sent
        answer, wire = wa_post(tmp_path, wa_message(NUMBER, "wamid.W", "text", "hi"))
        [message] = wire.sent("messages")       # their message opened the 24 hours: the card comes now
        assert message["type"] == "interactive" and message["interactive"]["action"]["buttons"][0]["reply"]["id"] == (
            "tc1:1:done")
        cards, _people, _first = tc.lessons_summary(tc.read_journal(str(tmp_path)))
        assert sorted(cards) == [1] and cards[1]["sent"] == 1

    def test_a_delivered_status_changes_nothing(self, tmp_path):
        wa_join(tmp_path)
        lesson(tmp_path, "send", "--date", "2026-10-07",
               wire=Wire(messages=(200, {"messaging_product": "whatsapp", "messages": [{"id": "wamid.T2"}]})))
        for status in ("sent", "delivered", "read"):
            wa_post(tmp_path, wa_statuses({"id": "wamid.T2", "status": status, "recipient_id": NUMBER}))
        assert kinds(tmp_path, "lesson_undelivered") == []

    def test_metas_move_of_the_template_is_said_with_the_way_to_a_review(self, tmp_path):
        when = int(datetime.datetime(2026, 10, 8, 12, 0, tzinfo=datetime.timezone.utc).timestamp())
        moving = {"object": "whatsapp_business_account", "entry": [{"id": "1", "time": 1, "changes": [
            {"field": "template_category_update", "value": {
                "message_template_id": 278077987957091, "message_template_name": "teamcall_card",
                "message_template_language": "en", "new_category": "UTILITY", "correct_category": "MARKETING",
                "category_update_timestamp": when}}]}]}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert wa_post(tmp_path, moving)[0] == (200, "ok")
        assert tc.say(EN, "lesson_template_moving", lang="en", name="teamcall_card", category="MARKETING",
                      date="2026-10-08") in out.getvalue()
        assert tc.say(EN, "lesson_template_review", lang="en", category="MARKETING") in out.getvalue()
        back = {"object": "whatsapp_business_account", "entry": [{"id": "1", "time": 2, "changes": [
            {"field": "template_category_update", "value": {
                "message_template_id": 278077987957091, "message_template_name": "teamcall_card",
                "message_template_language": "en", "previous_category": "MARKETING", "new_category": "UTILITY"}}]}]}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            wa_post(tmp_path, back)
        assert out.getvalue().strip() == tc.say(EN, "lesson_template_moved", lang="en", name="teamcall_card",
                                                category="UTILITY")

    def test_the_webhook_answers_meta_only_with_the_verify_token(self, tmp_path):
        conf = settings(tmp_path)
        good = "/?hub.mode=subscribe&hub.verify_token=%s&hub.challenge=1158201444" % VERIFY
        assert tc.whatsapp_webhook("GET", good, {}, b"", str(tmp_path), conf, Wire(), words_for) == (200, "1158201444")
        bad = "/?hub.mode=subscribe&hub.verify_token=guess&hub.challenge=1"
        assert tc.whatsapp_webhook("GET", bad, {}, b"", str(tmp_path), conf, Wire(), words_for)[0] == 403

    def test_an_unsigned_or_wrongly_signed_post_writes_nothing(self, tmp_path):
        wa_join(tmp_path)
        before = tc.read_journal(str(tmp_path))
        payload = wa_message(NUMBER, "wamid.B", "interactive", "tc1:3:done")
        answer, wire = wa_post(tmp_path, payload, secret="not-the-app-secret")
        assert answer[0] == 403 and wire.calls == []
        body = json.dumps(payload).encode("utf-8")
        assert tc.whatsapp_webhook("POST", "/", {}, body, str(tmp_path), settings(tmp_path), Wire(),
                                   words_for)[0] == 403
        assert tc.read_journal(str(tmp_path)) == before

    def test_a_signed_button_is_counted_and_show_me_answers_with_the_example(self, tmp_path):
        wa_join(tmp_path)
        answer, wire = wa_post(tmp_path, wa_message(NUMBER, "wamid.C", "interactive", "tc1:3:show"))
        assert answer == (200, "ok")
        assert [(e["person"], e["card"], e["answer"]) for e in kinds(tmp_path, "lesson_answer")] == [
            ("Bea Diaz", 3, "show")]
        head, _text, example = tc.card_parts(EN, 3)
        assert wire.sent("messages") == [tc.whatsapp_text(NUMBER, "*%s*\n\n%s" % (head, example))]

    def test_a_template_quick_reply_counts_too_and_a_retry_counts_once(self, tmp_path):
        wa_join(tmp_path)
        payload = wa_message(NUMBER, "wamid.D", "button", "tc1:4:done")
        _answer, wire = wa_post(tmp_path, payload)
        assert wire.sent("messages") == [tc.whatsapp_text(NUMBER, EN["lesson_ack_done"])]
        answer, wire = wa_post(tmp_path, payload)                   # Meta delivers it again
        assert answer == (200, "ok") and wire.calls == []
        assert [(e["card"], e["answer"]) for e in kinds(tmp_path, "lesson_answer")] == [(4, "done")]

    def test_start_with_the_code_from_the_link_joins_the_number(self, tmp_path):
        code, out = lesson(tmp_path, "invite", "--person", "Bea Diaz", "--channel", "whatsapp",
                           "--number", "+1 555 010 0199")
        assert code == 0
        link = re.search(r"https://wa\.me/15550100199\?text=start%20([A-Za-z0-9_-]{8,64})", out)
        assert link, out
        answer, wire = wa_post(tmp_path, wa_message(NUMBER, "wamid.E", "text", "start " + link.group(1)))
        assert answer == (200, "ok")
        assert [(c["person"], c["chat"]) for c in kinds(tmp_path, "lesson_chat")] == [("Bea Diaz", NUMBER)]
        assert wire.sent("messages") == [tc.whatsapp_text(NUMBER, tc.say(EN, "lesson_welcome", stop="stop",
                                                                          start="start", card="card"))]

    @staticmethod
    def link_code(folder, person):
        code, out = lesson(folder, "invite", "--person", person, "--channel", "whatsapp", "--number", "+1 555 010 0199")
        assert code == 0, out
        return re.search(r"text=start%20([A-Za-z0-9_-]{8,64})", out).group(1)

    def test_a_person_meta_names_by_the_user_id_alone_has_a_chat_of_their_own(self, tmp_path):
        """Meta leaves the number out for a person with a username the company has not been in touch with for 30
        days: the user id names the chat, the welcome and every card go to it as `recipient`, and two such people
        stay two people - each press counts for its own."""
        welcome = tc.say(EN, "lesson_welcome", stop="stop", start="start", card="card")
        for person, user, msg in (("Bea Diaz", USER, "wamid.U1"), ("Cy Doe", OTHER_USER, "wamid.U2")):
            start = "start " + self.link_code(tmp_path, person)
            answer, wire = wa_post(tmp_path, wa_message(None, msg, "text", start, user_id=user))
            assert answer == (200, "ok")
            assert wire.sent("messages") == [tc.whatsapp_text(user, welcome)]
            assert wire.sent("messages")[0]["recipient"] == user and "to" not in wire.sent("messages")[0]
        assert [(c["person"], c["chat"], c["user_id"]) for c in kinds(tmp_path, "lesson_chat")] == [
            ("Bea Diaz", USER, USER), ("Cy Doe", OTHER_USER, OTHER_USER)]
        wire = Wire()                          # their messages opened the 24 hours: the cards with their buttons
        assert lesson(tmp_path, "send", "--date", "2026-10-07", wire=wire)[0] == 0
        assert [(m.get("recipient"), m.get("to"), m["type"]) for m in wire.sent("messages")] == [
            (USER, None, "interactive"), (OTHER_USER, None, "interactive")]
        wire = Wire()                          # a day later, after the 24 hours: the note, to the same ids
        assert lesson(tmp_path, "send", "--date", "2026-10-08", wire=wire, now=NOW + 30 * 3600)[0] == 0
        assert [(m.get("recipient"), m.get("to"), m["type"]) for m in wire.sent("messages")] == [
            (USER, None, "template"), (OTHER_USER, None, "template")]
        for user, msg, data in ((USER, "wamid.P1", "tc1:1:done"), (OTHER_USER, "wamid.P2", "tc1:1:skip")):
            wa_post(tmp_path, wa_message(None, msg, "interactive", data, user_id=user))
        assert [(e["person"], e["answer"]) for e in kinds(tmp_path, "lesson_answer")] == [
            ("Bea Diaz", "done"), ("Cy Doe", "skip")]

    def test_the_same_person_with_the_number_and_the_user_id_stays_in_one_chat(self, tmp_path):
        """A message that carries both links them, and afterwards the user id alone finds the same chat - whichever
        came first: the number (an invite with --phone) or the user id (a link tapped without the number)."""
        wa_join(tmp_path)                                                   # the number first
        wa_post(tmp_path, wa_message(NUMBER, "wamid.L1", "text", "hello", user_id=USER))
        answer, wire = wa_post(tmp_path, wa_message(None, "wamid.L2", "text", "card", user_id=USER))
        assert answer == (200, "ok")
        [card] = wire.sent("messages")
        assert (card.get("to"), card.get("recipient"), card["type"]) == (NUMBER, None, "interactive")
        assert {e["chat"] for e in tc.read_journal(str(tmp_path)) if e.get("channel") == "whatsapp"} == {NUMBER}
        other = tmp_path / "other"                                          # the user id first
        start = "start " + self.link_code(other, "Cy Doe")
        wa_post(other, wa_message(None, "wamid.M1", "text", start, user_id=OTHER_USER))
        answer, wire = wa_post(other, wa_message("15550001111", "wamid.M2", "interactive", "tc1:2:done",
                                                 user_id=OTHER_USER))
        assert answer == (200, "ok")
        assert [(e["person"], e["chat"], e["card"]) for e in kinds(other, "lesson_answer")] == [
            ("Cy Doe", OTHER_USER, 2)]
        assert [c["chat"] for c in kinds(other, "lesson_chat")] == [OTHER_USER]
        assert wire.sent("messages") == [tc.whatsapp_text(OTHER_USER, EN["lesson_ack_done"])]

    def test_a_message_naming_nobody_is_left_alone(self, tmp_path):
        wa_join(tmp_path)
        before = tc.read_journal(str(tmp_path))
        answer, wire = wa_post(tmp_path, wa_message(None, "wamid.N", "text", "hello"))
        assert answer == (200, "ok") and wire.calls == [] and tc.read_journal(str(tmp_path)) == before

    def test_the_template_in_five_languages_and_its_creation(self, tmp_path):
        templates = tc.whatsapp_templates()
        assert [t["language"] for t in templates] == ["en", "es", "pt_BR", "ru", "uk"]
        for code, t in zip(tc.LANGS, templates):
            words = tc.lang_words(code)
            body, buttons = t["components"]
            assert body["text"].count("{{") == 1 and "{{1}}" in body["text"]
            assert not body["text"].startswith("{{") and not body["text"].endswith("}}")   # no value at either end
            assert body["example"] == {"body_text": [["1/20"]]}
            assert buttons["buttons"] == [{"type": "QUICK_REPLY", "text": words["lesson_open"]}]
            for n in range(1, tc.CARDS + 1):    # a note about the person's own card, no lesson text: utility
                assert words["card_%d_text" % n] not in body["text"], (code, n)
                assert words["card_%d_title" % n] not in body["text"], (code, n)
            assert (t["name"], t["category"]) == ("teamcall_card", "UTILITY")
        code, out = lesson(tmp_path, "template")
        assert code == 0 and json.loads(out) == templates
        wire = Wire(message_templates=(200, {"id": "77", "status": "PENDING", "category": "UTILITY"}))
        code, out = lesson(tmp_path, "template", "--create", wire=wire, env={"TEAMCALL_WHATSAPP_WABA_ID": "555000"})
        assert code == 0 and out.count("PENDING") == 5 and out.count("UTILITY") == 5
        assert "Request review" not in out
        assert [c["url"] for c in wire.calls] == [
            "https://graph.facebook.com/%s/555000/message_templates" % tc.WHATSAPP_VERSION] * 5
        assert [c["payload"] for c in wire.calls] == templates
        wire = Wire(message_templates=(200, {"id": "78", "status": "APPROVED", "category": "MARKETING"}))
        code, out = lesson(tmp_path, "template", "--create", wire=wire, env={"TEAMCALL_WHATSAPP_WABA_ID": "555000"})
        assert code == 0 and tc.say(EN, "lesson_template_review", lang="en", category="MARKETING") in out
        assert out.count("Request review") == 5

    def test_the_receiver_hands_metas_requests_to_the_webhook(self, tmp_path):
        handler = tc.webhook_handler(str(tmp_path), settings(tmp_path), Wire(), words_for)

        def request(path, headers, body=b""):
            h = handler.__new__(handler)
            h.path, h.headers, h.rfile, h.wfile = path, headers, io.BytesIO(body), io.BytesIO()
            h.request_version, h.requestline, h.client_address = "HTTP/1.1", "x", ("127.0.0.1", 0)
            h.command = "POST" if body else "GET"
            (h.do_POST if body else h.do_GET)()
            return h.wfile.getvalue()
        reply = request("/?hub.mode=subscribe&hub.verify_token=%s&hub.challenge=77" % VERIFY, {})
        assert reply.split(b" ", 2)[1] == b"200" and reply.endswith(b"\r\n\r\n77")
        body = json.dumps(wa_message(NUMBER, "wamid.F", "text", "hello")).encode("utf-8")
        reply = request("/", {"Content-Length": str(len(body)), "X-Hub-Signature-256": "sha256=0"}, body)
        assert reply.split(b" ", 2)[1] == b"403"

    def test_a_tls_handshake_runs_in_the_connections_own_thread_under_its_time_limit(self):
        """The listening socket takes connections without their handshake (do_handshake_on_connect=False); each
        connection's thread does it in setup(), after the 30 seconds are set - so a silent one holds up only itself."""
        handler = tc.webhook_handler("unused", {}, Wire(), words_for)
        steps = []

        class Connection:
            def settimeout(self, seconds):
                steps.append(("timeout", seconds))

            def do_handshake(self):
                steps.append(("handshake",))

            def makefile(self, *_args, **_kwargs):
                return io.BytesIO()

        h = handler.__new__(handler)
        h.request, h.client_address, h.server = Connection(), ("127.0.0.1", 0), None
        h.setup()
        assert steps == [("timeout", 30), ("handshake",)]

    def test_serve_with_its_own_certificate_listens_on_every_address(self, tmp_path, monkeypatch):
        """With --cert, `serve` is the HTTPS end itself, so Meta's requests come from the internet: it listens on
        every address of the computer. Behind the company's HTTPS it listens on 127.0.0.1, where that front hands the
        requests on; --host says otherwise for either."""
        heard = []
        monkeypatch.setattr(tc, "serve_webhook", lambda folder, host, port, *rest: heard.append((host, port)))
        code, out = lesson(tmp_path, "serve", "--cert", "cert.pem", "--cert-key", "key.pem")
        assert code == 0 and "https://0.0.0.0:8080" in out
        assert lesson(tmp_path, "serve")[0] == 0
        assert lesson(tmp_path, "serve", "--cert", "cert.pem", "--host", "10.0.0.5", "--port", "8443")[0] == 0
        assert heard == [("0.0.0.0", 8080), ("127.0.0.1", 8080), ("10.0.0.5", 8443)]

    def test_a_silent_connection_holds_up_no_other_request(self, tmp_path):
        try:
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            probe.close()
        except OSError as exc:
            pytest.skip("this computer lets no test listen on a local port: %s" % exc)
        servers, ready = [], threading.Event()

        def up(server):
            servers.append(server)
            ready.set()
        thread = threading.Thread(target=tc.serve_webhook, args=(str(tmp_path), "127.0.0.1", 0, settings(tmp_path),
                                                                Wire(), words_for), kwargs={"ready": up}, daemon=True)
        thread.start()
        assert ready.wait(10)
        host, port = servers[0].server_address[:2]
        silent = socket.create_connection((host, port), timeout=5)            # connects and says nothing
        try:
            ask = http.client.HTTPConnection(host, port, timeout=5)
            ask.request("GET", "/?hub.mode=subscribe&hub.verify_token=%s&hub.challenge=42" % VERIFY)
            answer = ask.getresponse()
            assert (answer.status, answer.read()) == (200, b"42")
            ask.close()
        finally:
            silent.close()
            servers[0].shutdown()
            thread.join(10)


class TestReport:
    def test_the_report_counts_the_buttons_without_names_chats_or_numbers(self, tmp_path):
        for person in ("Ann Lee", "Bob Roe"):                       # in the transition journal
            tc.add_entry(str(tmp_path), {"kind": "step", "person": person, "stage": "installed", "date": "2026-10-05",
                                          "minutes": 10, "help_minutes": 5, "blocker": "", "artifact": ""})
        join(tmp_path, "Ann Lee", 111)
        join(tmp_path, "Cy Doe", 333)                               # takes the cards only
        lesson(tmp_path, "invite", "--person", "Bob Roe", "--channel", "whatsapp", "--phone", "+34 600 111 222")
        for day in ("2026-10-05", "2026-10-06", "2026-10-07"):
            lesson(tmp_path, "send", "--start", MONDAY, "--date", day)
        lesson(tmp_path, "pull", "--date", "2026-10-07", wire=updates(
            tg_press(900, 111, "tc1:1:done"), tg_press(901, 111, "tc1:1:show"), tg_press(902, 111, "tc1:2:skip"),
            tg_press(903, 333, "tc1:1:skip"), tg_press(904, 333, "tc1:1:done")))
        wa_post(tmp_path, wa_message(NUMBER, "wamid.R", "button", "tc1:2:show"))
        text = tc.report_text(EN, tc.read_journal(str(tmp_path)), D(2026, 10, 30))
        for private in ("Ann", "Bob", "Cy", "111", "333", NUMBER, TOKEN):
            assert private not in text, private
        assert "## " + EN["report_lessons"] in text
        assert tc.say(EN, "report_lessons_sum", sent=9, people=3, done=2, show=2, skip=1, silent=5) in text
        for row in ("| 1. %s | 3 | 2 | 1 | 0 | 1 |" % EN["card_1_title"],      # Cy: skip, then done - done counts
                    "| 2. %s | 3 | 0 | 1 | 1 | 1 |" % EN["card_2_title"],
                    "| 3. %s | 3 | 0 | 0 | 0 | 3 |" % EN["card_3_title"],
                    "| P1 | 3 | 1 | 1 | 1 | 1 |", "| P2 | 3 | 0 | 1 | 0 | 2 |", "| P3 | 3 | 1 | 0 | 0 | 2 |"):
            assert row in text, row

    def test_no_cards_yet_is_said_and_until_leaves_later_answers_out(self):
        text = tc.report_text(EN, [], D(2026, 10, 30))
        assert "## " + EN["report_lessons"] in text and EN["report_lessons_none"] in text
        entries = [{"kind": "lesson_sent", "person": "A", "card": 1, "date": "2026-10-05"},
                   {"kind": "lesson_sent", "person": "A", "card": 2, "date": "2026-10-06"},
                   {"kind": "lesson_answer", "person": "A", "card": 1, "answer": "done", "date": "2026-10-07"}]
        cards, people, _first = tc.lessons_summary(entries, D(2026, 10, 6))
        assert sorted(cards) == [1, 2] and (cards[1]["done"], cards[1]["silent"]) == (0, 1)
        assert people["A"]["sent"] == 2


class TestDoor:
    """The one door to the network, tested without it: urlopen is replaced, so nothing leaves this computer."""

    def test_the_door_opens_only_to_the_two_messenger_hosts(self, monkeypatch):
        opened = []                     # recorded, not raised: the door turns any exception into a Problem
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda request, timeout=None, context=None: opened.append(request.full_url))
        for url in ("https://example.com/x", "http://api.telegram.org/bot1:a/getMe",
                    "https://api.telegram.org.evil.example/x", "https://api.telegram.org@evil.example/x"):
            with pytest.raises(tc.Problem):
                REAL_DOOR(url, {})
        assert opened == []

    def test_an_answer_and_an_error_answer_come_back_as_they_are(self, monkeypatch):
        seen = {}

        class Answer(io.BytesIO):
            status = 200

        def fake_urlopen(request, timeout=None, context=None):
            seen.update(url=request.full_url, data=request.data, timeout=timeout, headers=dict(request.header_items()))
            return Answer(b'{"ok": true, "result": {"message_id": 5}}')
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
        assert REAL_DOOR(url, {"chat_id": "1", "text": "hi"}, None, 7) == (200, {"ok": True,
                                                                               "result": {"message_id": 5}})
        assert json.loads(seen["data"]) == {"chat_id": "1", "text": "hi"} and seen["timeout"] == 7
        assert seen["headers"]["Content-type"] == "application/json"

        def refusing(request, timeout=None, context=None):
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(
                b'{"ok": false, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}'))
        monkeypatch.setattr(urllib.request, "urlopen", refusing)
        status, data = REAL_DOOR(url, {})
        assert status == 403 and data["description"] == "Forbidden: bot was blocked by the user"

    def test_no_answer_at_all_is_one_line_without_the_token(self, monkeypatch):
        url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN

        def down(request, timeout=None, context=None):
            raise urllib.error.URLError("no route to %s" % request.full_url)
        monkeypatch.setattr(urllib.request, "urlopen", down)
        with pytest.raises(tc.Problem) as caught:
            REAL_DOOR(url, {})
        assert str(caught.value) == "cannot reach api.telegram.org: no route to api.telegram.org"

    def test_a_python_without_certificates_checks_with_the_systems(self, monkeypatch, tmp_path):
        """python.org's Python on a Mac has no list of certificates until its Install Certificates step: the door
        then checks the messenger's certificate with the system's list; a Python with a list of its own keeps it."""
        certs = tmp_path / "cert.pem"
        certs.write_text("the system's list", encoding="utf-8")
        monkeypatch.setattr(tc, "SYSTEM_CERTS", str(certs))
        made, used = [], []

        class Answer(io.BytesIO):
            status = 200

        def fake_urlopen(request, timeout=None, context=None):
            used.append(context)
            return Answer(b'{"ok": true, "result": {}}')
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(ssl, "create_default_context", lambda cafile=None: made.append(cafile) or "the context")
        url = "https://api.telegram.org/bot%s/getMe" % TOKEN
        monkeypatch.setattr(ssl, "get_default_verify_paths", lambda: types.SimpleNamespace(cafile=None, capath=None))
        assert REAL_DOOR(url, {})[0] == 200
        monkeypatch.setattr(ssl, "get_default_verify_paths",
                            lambda: types.SimpleNamespace(cafile="/its/own/cert.pem", capath=None))
        assert REAL_DOOR(url, {})[0] == 200
        assert (made, used) == ([str(certs)], ["the context", None])


class TestSettingsAndSchedule:
    def test_the_env_file_is_read_and_the_environment_wins(self, tmp_path):
        path = tmp_path / "company.env"
        path.write_text('# the company bot\nexport TEAMCALL_TELEGRAM_TOKEN="111:from_file"\n'
                        "TEAMCALL_WHATSAPP_PHONE_ID=42\nOTHER=x\n", encoding="utf-8")
        conf = tc.lesson_env({"TEAMCALL_ENV_FILE": str(path), "TEAMCALL_WHATSAPP_PHONE_ID": "43"})
        assert conf["TEAMCALL_TELEGRAM_TOKEN"] == "111:from_file"
        assert conf["TEAMCALL_WHATSAPP_PHONE_ID"] == "43" and "OTHER" not in conf

    def test_a_missing_token_is_said_and_nothing_is_sent(self, tmp_path):
        join(tmp_path, "Ann Lee", 111)
        wire = Wire()
        code, out = lesson(tmp_path, "send", "--start", MONDAY, "--date", "2026-10-07", wire=wire,
                           env={"TEAMCALL_TELEGRAM_TOKEN": ""})
        assert code == 1 and "TEAMCALL_TELEGRAM_TOKEN" in out and wire.calls == []
        assert kinds(tmp_path, "lesson_sent") == []                         # the card stays Ann's next one

    def test_a_messenger_without_its_settings_holds_up_no_other(self, tmp_path):
        """A company on Telegram puts one person on WhatsApp while Meta still checks its business: the Telegram cards
        go, the WhatsApp chat is not delivered with the missing setting named, and once the setting is in, its card
        goes the same day. And the other way round: no Telegram token stops no WhatsApp card."""
        join(tmp_path, "Ann Lee", 111)
        wa_join(tmp_path)
        wire = Wire()
        code, out = lesson(tmp_path, "send", "--date", "2026-10-07", wire=wire, env={"TEAMCALL_WHATSAPP_PHONE_ID": ""})
        assert code == 1 and tg_cards(wire) == [1] and wire.sent("messages") == []
        assert tc.say(EN, "lesson_failed", channel="whatsapp", person="Bea Diaz",
                      why="WhatsApp needs TEAMCALL_WHATSAPP_PHONE_ID") in out
        assert tc.say(EN, "lesson_sent", channel="telegram", total=tc.CARDS, sent=1, had=0, finished=0, failed=0,
                      waiting=0) in out
        assert [(e["channel"], e["card"]) for e in kinds(tmp_path, "lesson_sent")] == [("telegram", 1)]
        wire = Wire()
        assert lesson(tmp_path, "send", "--date", "2026-10-07", wire=wire)[0] == 0
        [card] = wire.sent("messages")
        assert tg_cards(wire) == [] and card["template"]["components"][1]["parameters"][0]["payload"] == "tc1:1:open"
        other = tmp_path / "other"
        join(other, "Ann Lee", 111)
        wa_join(other)
        wire = Wire()
        code, out = lesson(other, "send", "--date", "2026-10-07", wire=wire, env={"TEAMCALL_TELEGRAM_TOKEN": ""})
        assert code == 1 and tg_cards(wire) == [] and len(wire.sent("messages")) == 1
        assert tc.say(EN, "lesson_failed", channel="telegram", person="Ann Lee",
                      why="Telegram needs TEAMCALL_TELEGRAM_TOKEN") in out

    def test_a_number_goes_on_the_list_before_the_whatsapp_settings_and_what_is_missing_is_said(self, tmp_path):
        code, out = lesson(tmp_path, "invite", "--person", "Bea Diaz", "--channel", "whatsapp", "--phone",
                           "+34 600 111 222", env={"TEAMCALL_WHATSAPP_PHONE_ID": "", "TEAMCALL_WHATSAPP_TOKEN": ""})
        assert code == 0 and tc.say(EN, "lesson_joined_phone", person="Bea Diaz") in out
        assert "teamcall: WhatsApp needs TEAMCALL_WHATSAPP_PHONE_ID" in out
        assert [(c["person"], c["chat"]) for c in kinds(tmp_path, "lesson_chat")] == [("Bea Diaz", NUMBER)]
        code, out = lesson(tmp_path, "invite", "--person", "Ann Lee", "--bot", "acme_bot",
                           env={"TEAMCALL_TELEGRAM_TOKEN": ""})
        assert code == 0 and "t.me/acme_bot?start=" in out and "teamcall: Telegram needs TEAMCALL_TELEGRAM_TOKEN" in out
        code, out = lesson(tmp_path, "invite", "--person", "Cy Doe", "--channel", "whatsapp", "--phone",
                           "+34 600 333 444")
        assert code == 0 and "teamcall:" not in out                       # with the settings in, nothing more

    def test_an_env_file_written_by_windows_powershell_is_read(self, tmp_path):
        path = tmp_path / "company.env"
        line = "TEAMCALL_TELEGRAM_TOKEN=111:from_windows\r\n"
        for raw in (b"\xef\xbb\xbf" + line.encode("utf-8"),             # Out-File -Encoding utf8 in PowerShell 5.1
                    b"\xff\xfe" + line.encode("utf-16-le")):           # `>` in PowerShell 5.1
            path.write_bytes(raw)
            assert tc.lesson_env({"TEAMCALL_ENV_FILE": str(path)})["TEAMCALL_TELEGRAM_TOKEN"] == "111:from_windows"
        path.write_bytes(b"TEAMCALL_TELEGRAM_TOKEN=\xff\xfe\xfd\n")
        with pytest.raises(tc.Problem) as caught:
            tc.lesson_env({"TEAMCALL_ENV_FILE": str(path)})
        assert "save it again as UTF-8" in str(caught.value)

    def schedule_lines(self, out):
        return [line for line in out.splitlines() if line and not line.startswith(("#", "PATH=", "written", "$"))]

    def test_the_schedule_on_mac_and_linux_is_cron(self, tmp_path):
        code, out = lesson(tmp_path, "schedule", "--os", "linux", "--at", "08:30")
        assert code == 0
        launcher = tmp_path / "teamcall-run.sh"
        assert launcher.is_file() and tc.say(EN, "wrote", path=str(launcher)) in out
        line = 'sh "%s" lesson %%s --folder "%s"' % (launcher, tmp_path)
        assert self.schedule_lines(out) == [
            "30-59/15 8 * * 1-5 " + line % "send --at 08:30",           # 08:30, 08:45, then every 15 minutes
            "*/15 9-19 * * 1-5 " + line % "send --at 08:30",           # until 19:45
            "*/5 * * * * " + line % "pull --loop --if-set",
            "*/5 * * * * " + line % "serve --port 8080 --if-set"]
        assert str(ROOT) not in "\n".join(self.schedule_lines(out))  # no line names the plugin's version folder
        assert tc.say(EN, "lesson_schedule_env", file=str(tmp_path / "no.env")) in out
        assert EN["lesson_schedule_mac"] not in out
        assert EN["lesson_schedule_mac"] in lesson(tmp_path, "schedule", "--os", "mac")[1]

    def test_the_cards_hours_in_cron_follow_at_to_the_minute(self):
        assert tc.cron_times((9, 0), (20, 0)) == ["*/15 9-19 * * 1-5"]
        assert tc.cron_times((19, 46), (20, 0)) == ["46-59/15 19 * * 1-5"]           # one run, at 19:46
        assert tc.cron_times((18, 50), (20, 0)) == ["50-59/15 18 * * 1-5", "*/15 19 * * 1-5"]
        assert tc.cron_times((21, 30), (24, 0)) == ["30-59/15 21 * * 1-5", "*/15 22-23 * * 1-5"]
        for at in ((9, 0), (19, 46), (21, 30), (7, 5)):
            begin, end = tc.card_hours(at)
            runs = [(h, m) for h in range(24) for m in range(60) if self.cron_fires(tc.cron_times(begin, end), h, m)]
            assert runs[0] == at and all(begin <= r < end for r in runs), at  # the first run is at --at, all inside

    @staticmethod
    def cron_fires(times, hour, minute):
        def field(spec, value):
            for part in spec.split(","):
                part, _sep, step = part.partition("/")
                low, high = (0, 59) if part == "*" else (int(part.split("-")[0]), int(part.split("-")[-1]))
                if low <= value <= high and (value - low) % int(step or 1) == 0:
                    return True
            return False
        return any(field(t.split()[0], minute) and field(t.split()[1], hour) for t in times)

    def test_the_schedule_on_windows_is_task_scheduler(self, tmp_path):
        code, out = lesson(tmp_path, "schedule", "--os", "windows")
        assert code == 0
        assert (tmp_path / "teamcall-run.py").is_file()
        assert "powershell.exe" not in out and "python.ps1" not in out          # no window, no console
        assert ("$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
                "-StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)") in out
        assert out.count("-Settings $s") == 3
        assert "Register-ScheduledTask -TaskName 'teamcall card'" in out
        assert "-DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 09:00" in out
        assert "-RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Minutes 660)" in out
        assert "lesson send --at 09:00" in out
        assert "lesson pull --loop --if-set" in out and "lesson serve --port 8080 --if-set" in out
        assert str(ROOT) not in out

    def test_windows_tasks_run_a_python_that_opens_no_window(self):
        local = os.path.join("C:", "Users", "a", "AppData", "Local")
        launcher = os.path.join(local, "Programs", "Python", "Launcher", "pyw.exe")
        assert tc.windowless_python({"LOCALAPPDATA": local}, "python.exe", isfile=lambda p: p == launcher,
                                    which=lambda name: None) == (launcher, ["-3"])
        beside = os.path.join("py", "pythonw.exe")
        assert tc.windowless_python({}, os.path.join("py", "python.exe"), isfile=lambda p: p == beside,
                                    which=lambda name: None) == (beside, [])

    def test_a_receiver_without_its_messengers_settings_stays_quiet_when_scheduled(self, tmp_path):
        no_whatsapp = {"TEAMCALL_WHATSAPP_APP_SECRET": "", "TEAMCALL_WHATSAPP_VERIFY_TOKEN": ""}
        assert lesson(tmp_path, "serve", "--if-set", env=no_whatsapp) == (0, "")
        assert lesson(tmp_path, "pull", "--loop", "--if-set", env={"TEAMCALL_TELEGRAM_TOKEN": ""}) == (0, "")
        code, out = lesson(tmp_path, "serve", env=no_whatsapp)                   # by hand it is said
        assert code == 2 and "TEAMCALL_WHATSAPP_APP_SECRET" in out


class TestLauncher:
    """The launcher in the company's folder runs the newest teamcall Claude Code has installed now: an update moves
    the plugin to a new version folder and removes the old one 14 days later, and the schedule keeps working."""

    def version(self, cache, number, orphaned=False):
        root = cache / "poly-a1" / "teamcall" / number
        (root / "skills" / "teamcall" / "scripts").mkdir(parents=True)
        (root / "hooks").mkdir()
        (root / "skills" / "teamcall" / "scripts" / "teamcall.py").write_text(
            "import sys\nif sys.argv[1:2] != ['quiet']:\n    print('ran %s', ' '.join(sys.argv[1:]))\n" % number)
        (root / "hooks" / "python.sh").write_text('script=$3\nshift 3\nexec "%s" "$script" "$@"\n' % sys.executable)
        if orphaned:
            (root / ".orphaned_at").write_text("1767225600000")
        return root

    def run(self, os_name, root, folder, *args):
        launcher = folder / tc.LAUNCHER[os_name]
        launcher.write_text(tc.launcher_text(os_name, str(root)), encoding="utf-8")
        program = ["sh"] if os_name == "mac" else [sys.executable]
        subprocess.run(program + [str(launcher)] + list(args), check=True, timeout=60)
        log = folder / tc.RUN_LOG
        return log.read_text(encoding="utf-8") if log.exists() else ""

    @pytest.mark.parametrize("os_name", ["mac", "windows"])
    def test_the_newest_version_without_the_orphan_mark_runs(self, tmp_path, os_name):
        cache = tmp_path / "plugins" / "cache"
        self.version(cache, "0.0.9")                                  # by the alphabet the first, 0.1.9 the last:
        first = self.version(cache, "0.1.9")                          # neither is the newest
        self.version(cache, "0.1.10")
        self.version(cache, "0.1.11", orphaned=True)                  # an update or uninstall left it
        folder = tmp_path / "company"
        folder.mkdir()
        log = self.run(os_name, first, folder, "lesson", "send", "--at", "09:00")
        assert log.startswith("--- ") and log.splitlines()[0].endswith(" lesson send")
        assert "ran 0.1.10 lesson send --at 09:00" in log and "ran 0.1.9" not in log and "ran 0.0.9" not in log

    @pytest.mark.parametrize("os_name", ["mac", "windows"])
    def test_with_every_version_gone_the_folder_schedule_ran_from_runs(self, tmp_path, os_name):
        cache = tmp_path / "plugins" / "cache"
        first = self.version(cache, "0.1.9", orphaned=True)
        folder = tmp_path / "company"
        folder.mkdir()
        assert "ran 0.1.9 lesson send" in self.run(os_name, first, folder, "lesson", "send")
        plain = self.version(tmp_path / "kept" / "cache-less", "0.2.0")   # a teamcall outside Claude Code's cache
        assert tc.plugin_home(str(plain)) == (None, None, None)
        assert "ran 0.2.0 lesson pull" in self.run(os_name, plain, folder, "lesson", "pull")

    @pytest.mark.parametrize("os_name", ["mac", "windows"])
    def test_a_run_with_nothing_to_say_leaves_no_line(self, tmp_path, os_name):
        first = self.version(tmp_path / "plugins" / "cache", "0.1.9")
        folder = tmp_path / "company"
        folder.mkdir()
        assert self.run(os_name, first, folder, "quiet") == ""
        assert not (folder / tc.RUN_LOG).exists()
