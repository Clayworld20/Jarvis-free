"""End-to-end state machine with a fake microphone and fake recognizers."""
import json
import time

from jarvis.assistant import Assistant
from jarvis.events import EventBus
from jarvis.stt import SpeechEngine
from tests.helpers import FakeSpeaker, make_router, make_settings


class FakeMic:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def read(self, timeout=0.2):
        if self._chunks:
            return self._chunks.pop(0)
        time.sleep(0.01)
        return None

    def stop(self):
        self.stopped = True


class ScriptedRec:
    """Each AcceptWaveform call pops one scripted item: (is_final, text)."""

    def __init__(self, script):
        self.script = list(script)
        self.current = ("", False)

    def AcceptWaveform(self, data):
        if not self.script:
            self.current = ("", False)
            return False
        final, text = self.script.pop(0)
        self.current = (text, final)
        return final

    def Result(self):
        return json.dumps({"text": self.current[0]})

    def PartialResult(self):
        return json.dumps({"partial": self.current[0]})

    def Reset(self):
        pass


def _wait_for(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_wake_word_then_command_is_executed_and_spoken(tmp_path):
    settings = make_settings(listen_timeout_sec=5)
    bus = EventBus()
    speaker = FakeSpeaker()
    router = make_router(settings, speaker=speaker, tmp_path=tmp_path)
    chunk = b"\x00" * 320
    mic = FakeMic([chunk] * 6)
    wake_rec = ScriptedRec([(True, "привет"), (True, "джарвис")])
    cmd_rec = ScriptedRec([(True, "который час")])
    chimes = []

    speech = SpeechEngine.__new__(SpeechEngine)  # bypass model loading
    speech.models_dir = tmp_path
    speech.model_names = settings["models"]
    speech.wake_words = settings["wake_words"]
    speech.sample_rate = 16000
    speech.is_model_available = lambda lang: True
    speech.wake_recognizer = lambda lang: wake_rec
    speech.command_recognizer = lambda lang: cmd_rec

    assistant = Assistant(settings, bus, router, speaker, speech, mic_factory=lambda: mic, chime=lambda: chimes.append(1))
    assistant.start()
    try:
        assert _wait_for(lambda: "Сейчас 14:05." in speaker.said)
    finally:
        assistant.stop()

    assert mic.started and mic.stopped
    assert chimes == [1]
    assert "Слушаю." in speaker.said
    history = bus.recent("history")
    assert history and history[-1]["input"] == "который час" and history[-1]["source"] == "voice"
    assert assistant.status()["state"] in ("idle", "listening")


def test_status_reports_missing_models_and_mic_error():
    settings = make_settings()
    bus = EventBus()
    speaker = FakeSpeaker()
    router = make_router(settings, speaker=speaker)

    class BrokenMic(FakeMic):
        def start(self):
            raise RuntimeError("микрофон занят")

    assistant = Assistant(settings, bus, router, speaker, None, mic_factory=lambda: BrokenMic([]))
    assistant.start()
    try:
        assert _wait_for(lambda: assistant.status()["state"] == "error")
    finally:
        assistant.stop()
    assert "микрофон занят" in assistant.status()["error"]


def test_submit_text_works_without_microphone(tmp_path):
    settings = make_settings()
    bus = EventBus()
    speaker = FakeSpeaker()
    router = make_router(settings, speaker=speaker, tmp_path=tmp_path)
    assistant = Assistant(settings, bus, router, speaker, None)
    result = assistant.submit_text("привет", source="gui")
    assert result.ok and speaker.said[-1] == result.text
    assert bus.recent("history")[-1]["source"] == "gui"
