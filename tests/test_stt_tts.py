import json
from pathlib import Path

from jarvis.stt import ModelMissingError, SpeechEngine, contains_wake_word, recognized_text
from jarvis.tts import Speaker, pick_voice


def test_contains_wake_word_whole_words_only():
    assert contains_wake_word("Джарвис, который час", ["джарвис"])
    assert contains_wake_word("hey jarvis", ["jarvis"])
    assert not contains_wake_word("джарвисовский", ["джарвис"])
    assert not contains_wake_word("", ["jarvis"])


def test_recognized_text_parses_vosk_payloads():
    assert recognized_text(json.dumps({"text": " привет "}), "text") == "привет"
    assert recognized_text(json.dumps({"partial": "джар"}), "partial") == "джар"
    assert recognized_text("not json", "text") == ""


class _FakeRec:
    def __init__(self, model, rate, grammar):
        self.model, self.rate, self.grammar = model, rate, grammar


def test_speech_engine_uses_grammar_for_wake_and_full_for_commands(tmp_path):
    (tmp_path / "ru-model").mkdir()
    engine = SpeechEngine(
        tmp_path,
        {"ru": "ru-model"},
        {"ru": ["Джарвис", "джервис"]},
        16000,
        model_factory=lambda path: f"MODEL:{Path(path).name}",
        recognizer_factory=_FakeRec,
    )
    wake = engine.wake_recognizer("ru")
    assert wake.grammar == ["джарвис", "джервис", "[unk]"]
    cmd = engine.command_recognizer("ru")
    assert cmd.grammar is None and cmd.model == "MODEL:ru-model"


def test_missing_model_gives_actionable_error(tmp_path):
    engine = SpeechEngine(tmp_path, {"en": "absent"}, {"en": ["jarvis"]}, 16000, recognizer_factory=_FakeRec)
    try:
        engine.wake_recognizer("en")
    except ModelMissingError as exc:
        assert "download_models" in str(exc)
    else:
        raise AssertionError("expected ModelMissingError")


class _Voice:
    def __init__(self, id, name, languages=()):
        self.id, self.name, self.languages = id, name, list(languages)


def test_pick_voice_prefers_language_and_user_hint():
    voices = [_Voice("v1", "Microsoft David", ["en-US"]), _Voice("v2", "Microsoft Irina", ["ru-RU"])]
    assert pick_voice(voices, "ru") == "v2"
    assert pick_voice(voices, "en") == "v1"
    assert pick_voice(voices, "en", preferred="irina") == "v2"
    assert pick_voice([], "ru") is None


class _FakeEngine:
    def __init__(self):
        self.said = []
        self.props = {}

    def setProperty(self, k, v):
        self.props[k] = v

    def getProperty(self, k):
        return []

    def say(self, text):
        self.said.append(text)

    def runAndWait(self):
        pass

    def stop(self):
        pass


def test_speaker_speaks_queue_and_reports_busy():
    import time

    from jarvis.config import DEFAULT_SETTINGS
    import copy

    engine = _FakeEngine()
    speaker = Speaker(copy.deepcopy(DEFAULT_SETTINGS), engine_factory=lambda: engine)
    speaker.say("привет")
    speaker.say("мир")
    for _ in range(100):
        if len(engine.said) == 2 and not speaker.busy:
            break
        time.sleep(0.01)
    assert engine.said == ["привет", "мир"]
    assert not speaker.busy
    assert engine.props["rate"] == 180


def test_configure_takes_effect_for_new_recognizers(tmp_path):
    (tmp_path / "ru-a").mkdir()
    (tmp_path / "ru-b").mkdir()
    engine = SpeechEngine(tmp_path, {"ru": "ru-a"}, {"ru": ["джарвис"]}, 16000,
                          model_factory=lambda p: p, recognizer_factory=_FakeRec)
    assert engine.wake_recognizer("ru").grammar == ["джарвис", "[unk]"]
    engine.configure({"ru": "ru-b"}, {"ru": ["жарвис"]}, 16000)
    rec = engine.wake_recognizer("ru")
    assert rec.grammar == ["жарвис", "[unk]"]
    assert rec.model.endswith("ru-b")
