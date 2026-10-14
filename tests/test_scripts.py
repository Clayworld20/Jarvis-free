import json

import pytest

from jarvis.scripts import ScriptError, ScriptRunner, load_scripts, validate_script
from jarvis import paths


def _valid():
    return {"name": "demo", "steps": [{"type": "speak", "text": "hi"}]}


def test_bundled_scripts_are_valid():
    scripts, errors = load_scripts(paths.SCRIPTS_DIR)
    assert errors == []
    assert {s.name for s in scripts} >= {"work_mode", "morning_briefing"}


def test_invalid_scripts_are_reported_not_loaded(tmp_path):
    (tmp_path / "good.json").write_text(json.dumps(_valid()), encoding="utf-8")
    (tmp_path / "bad.json").write_text(json.dumps({"steps": [{"type": "exec", "cmd": "rm -rf /"}]}), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    scripts, errors = load_scripts(tmp_path)
    assert [s.name for s in scripts] == ["demo"]  # name comes from the "name" field
    assert len(errors) == 2


@pytest.mark.parametrize(
    "data",
    [
        {"name": "Bad Name!", "steps": [{"type": "speak", "text": "x"}]},
        {"name": "x", "steps": []},
        {"name": "x", "steps": [{"type": "run", "command": "notepad"}]},  # command must be a list
        {"name": "x", "steps": [{"type": "wait", "seconds": 999}]},
        {"name": "x", "steps": [{"type": "speak"}]},
    ],
)
def test_validation_errors(data):
    with pytest.raises(ScriptError):
        validate_script(data, "x")


def test_runner_executes_steps_in_order():
    log = []
    script = validate_script(
        {
            "name": "seq",
            "steps": [
                {"type": "speak", "text": "one"},
                {"type": "open", "target": "браузер"},
                {"type": "wait", "seconds": 2},
                {"type": "search", "query": "news"},
                {"type": "note", "text": "memo"},
            ],
        },
        "seq",
    )
    runner = ScriptRunner(
        say=lambda t: log.append(("say", t)),
        open_target=lambda t: log.append(("open", t)) or True,
        search=lambda q: log.append(("search", q)),
        add_note=lambda t: log.append(("note", t)),
        sleep=lambda s: log.append(("sleep", s)),
    )
    runner.run(script)
    assert log == [("say", "one"), ("open", "браузер"), ("sleep", 2.0), ("search", "news"), ("note", "memo")]


def test_run_step_can_be_disabled():
    called = []
    script = validate_script({"name": "r", "steps": [{"type": "run", "command": ["calc.exe"]}]}, "r")
    runner = ScriptRunner(lambda t: None, lambda t: True, lambda q: None, lambda t: None, allow_run=False)
    import jarvis.scripts as mod

    original = mod.subprocess.Popen
    mod.subprocess.Popen = lambda *a, **k: called.append(a)
    try:
        runner.run(script)
    finally:
        mod.subprocess.Popen = original
    assert called == []
