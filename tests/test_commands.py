from jarvis.scripts import validate_script
from tests.helpers import FakeSpeaker, make_router, make_settings


def test_time_and_date_templates():
    router = make_router()
    assert router.execute("который час").text == "Сейчас 14:05."
    assert router.execute("какое сегодня число").text == "Сегодня 14.10.2026."
    router.set_language("en")
    assert router.execute("what time is it").text == "It is 14:05."


def test_unknown_command_is_reported():
    result = make_router().execute("абракадабра фризл")
    assert result.recognized is False and result.ok is False
    assert "не понял" in result.text


def test_open_known_app_runs_program_without_shell():
    router = make_router()
    result = router.execute("открой блокнот")
    assert result.ok and result.text == "Открываю блокнот."
    assert router.popen.calls[0][0] == ["notepad"]
    assert router.popen.calls[0][1]["shell"] is False


def test_open_site_uses_browser():
    router = make_router()
    router.execute("открой ютуб")
    assert router.opened == ["https://www.youtube.com"]


def test_unknown_app_is_refused_unless_allowed():
    router = make_router()
    result = router.execute("открой фотошоп")
    assert result.ok is False and "фотошоп" in result.text
    assert router.popen.calls == []

    router = make_router(make_settings(allow_any_app=True))
    assert router.execute("открой фотошоп").ok is True
    assert router.popen.calls[0][0] == ["фотошоп"]


def test_search_is_url_encoded():
    router = make_router()
    router.execute("найди в интернете погода Таллинн")
    assert router.opened[0].startswith("https://duckduckgo.com/?q=")
    assert " " not in router.opened[0]


def test_power_off_requires_confirmation_on_windows():
    router = make_router()
    assert "подтвердите" in router.execute("выключи компьютер").text.lower()
    assert router.popen.calls == []
    result = router.execute("подтверждаю")
    assert result.ok
    args = router.popen.calls[-1][0]
    assert args[:2] == ["shutdown", "/s"] and "/t" in args


def test_confirm_without_pending_action():
    result = make_router().execute("подтверждаю")
    assert result.ok is False and "нечего" in result.text.lower()


def test_power_commands_are_refused_off_windows():
    router = make_router(platform="linux")
    result = router.execute("выключи компьютер")
    assert result.ok is False
    assert router.popen.calls == []


def test_cancel_power_clears_pending_and_calls_shutdown_abort():
    router = make_router(make_settings(confirm_power_actions=True))
    router.execute("перезагрузи компьютер")
    router.execute("отмени")
    assert router.actions.pending is None
    assert router.popen.calls[-1][0] == ["shutdown", "/a"]


def test_note_is_saved(tmp_path):
    router = make_router(tmp_path=tmp_path)
    assert router.execute("запиши купить молоко").ok
    content = (tmp_path / "notes.txt").read_text(encoding="utf-8")
    assert "купить молоко" in content and "2026-10-14 14:05" in content


def test_stop_clears_speech_and_pending():
    speaker = FakeSpeaker()
    router = make_router(speaker=speaker)
    router.execute("выключи компьютер")
    router.execute("стоп")
    assert speaker.stopped == 1
    assert router.actions.pending is None


def test_bundled_script_is_triggered_by_phrase():
    speaker = FakeSpeaker()
    router = make_router(speaker=speaker)
    result = router.execute("режим работы")
    assert result.intent_id == "script:work_mode"
    assert result.text == "Сценарий выполнен."
    assert speaker.said == ["Включаю режим работы."]
    assert router.opened == ["https://duckduckgo.com"]          # "браузер" is a URL in the default apps
    assert router.popen.calls[0][0] == ["notepad"]              # "блокнот" is a program, started without a shell


def test_script_missing_is_reported():
    router = make_router()
    result = router.actions.run("script", {"name": "nope"})
    assert result["ok"] is False


def test_action_exception_is_caught():
    router = make_router()

    def boom(params):
        raise RuntimeError("disk full")

    router.actions.do_time = boom
    result = router.execute("который час")
    assert result.ok is False and "ошибка" in result.text.lower()


def test_script_intent_only_for_matching_language():
    script = validate_script({"name": "x", "triggers": {"en": ["make coffee"]}, "steps": [{"type": "speak", "text": "ok"}]}, "x")
    router = make_router(scripts=[script])
    router.set_language("en")
    assert router.execute("make coffee").intent_id == "script:x"
    router.set_language("ru")
    assert router.execute("make coffee").recognized is False
