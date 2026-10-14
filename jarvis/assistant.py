"""The assistant orchestrator.

States
------
idle        -> waiting for the wake word (only the small wake-word grammar runs)
listening   -> wake word heard; the full recogniser captures one command
processing  -> command is executed in a worker thread; microphone input is ignored
(speaking)  -> while TTS is talking the microphone is muted, so the assistant does not hear itself
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable

from .audio import Microphone, NoiseFilter, pcm_level, play_chime
from .commands import CommandResult, Router
from .stt import SpeechEngine, contains_wake_word, recognized_text
from .events import EventBus

log = logging.getLogger("jarvis.assistant")

STATES = ("idle", "listening", "processing", "error")


class Assistant:
    def __init__(
        self,
        settings: dict[str, Any],
        bus: EventBus,
        router: Router,
        speaker: Any,
        speech: SpeechEngine | None = None,
        mic_factory: Callable[[], Any] | None = None,
        chime: Callable[[], None] = play_chime,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.settings = settings
        self.bus = bus
        self.router = router
        self.speaker = speaker
        self.speech = speech
        self._mic_factory = mic_factory or self._default_mic
        self._chime = chime
        self._clock = clock

        self._state = "idle"
        self._errors: dict[str, str | None] = {"mic": None, "model": None}
        self._mic_active = False
        self._stop = threading.Event()
        self._audio_restart = threading.Event()
        self._need_reset = False
        self._thread: threading.Thread | None = None
        self._wake: Any = None
        self._cmd: Any = None
        self._deadline = 0.0
        self._last_level_pub = 0.0
        self._last_speaking: bool | None = None
        self._recent: deque[CommandResult] = deque(maxlen=50)
        self._lock = threading.Lock()

    # ----- public API -----------------------------------------------------
    def _default_mic(self) -> Microphone:
        a = self.settings["audio"]
        return Microphone(sample_rate=a["sample_rate"], block_ms=a["block_ms"], device=a["input_device"])

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="assistant", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def restart_audio(self) -> None:
        """Re-open the microphone and rebuild the noise filter after audio settings changed."""
        self._audio_restart.set()

    def reload_recognizers(self) -> None:
        """Rebuild Vosk recognizers (e.g. after wake words or models changed)."""
        self._need_reset = True

    def set_language(self, language: str) -> None:
        self.router.set_language(language)
        self._need_reset = True
        self._set_error(None)
        self.bus.publish("status", **self.status())

    def submit_text(self, text: str, source: str = "text") -> CommandResult:
        """Run a typed command (GUI chat / console) through the same pipeline as voice."""
        result = self.router.execute(text)
        self._recent.append(result)
        self.bus.publish(
            "history",
            source=source,
            input=result.input,
            reply=result.text,
            ok=result.ok,
            recognized=result.recognized,
            intent=result.intent_id,
            action=result.action,
        )
        if result.text:
            self.speaker.say(result.text)
        return result

    def status(self) -> dict[str, Any]:
        lang = self.router.language
        models = {}
        if self.speech is not None:
            models = {code: self.speech.is_model_available(code) for code in self.settings["models"]}
        return {
            "state": self._state,
            "language": lang,
            "speaking": bool(self.speaker.busy) if self.speaker else False,
            "mic_active": self._mic_active,
            "error": self.error,
            "wake_words": self.settings["wake_words"].get(lang, []),
            "models": models,
            "tts_available": bool(getattr(self.speaker, "available", False)),
            "tts_error": getattr(self.speaker, "error", None),
        }

    # ----- internals ------------------------------------------------------
    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.bus.publish("status", **self.status())

    @property
    def error(self) -> str | None:
        return self._errors["mic"] or self._errors["model"]

    def _set_error(self, message: str | None, kind: str = "model") -> None:
        if message != self._errors[kind]:
            self._errors[kind] = message
            if message:
                log.error(message)
            self.bus.publish("status", **self.status())

    def _load_recognizers(self) -> bool:
        self._wake = self._cmd = None
        if self.speech is None:
            self._set_error("Распознавание речи не настроено", "model")
            return False
        lang = self.router.language
        self.speech.configure(self.settings["models"], self.settings["wake_words"], self.settings["audio"]["sample_rate"])
        try:
            self._wake = self.speech.wake_recognizer(lang)
            self._cmd = self.speech.command_recognizer(lang)
        except Exception as exc:  # e.g. model folder missing
            self._set_error(str(exc), "model")
            return False
        self._set_error(None, "model")
        log.info("Распознавание готово (язык: %s)", lang)
        return True

    def _open_audio(self):
        audio = self.settings["audio"]
        noise = NoiseFilter(
            sample_rate=audio["sample_rate"],
            highpass_hz=audio["highpass_hz"],
            gate_margin_db=audio["gate_margin_db"],
            enabled=audio["noise_filter"],
        )
        mic = self._mic_factory()
        try:
            mic.start()
            self._mic_active = True
            self._set_error(None, "mic")
        except Exception as exc:
            self._mic_active = False
            self._set_error(str(exc), "mic")
            mic = None
        return mic, noise

    def _run(self) -> None:
        mic, noise = self._open_audio()
        loaded = self._load_recognizers()
        self._set_state("idle" if (mic is not None and loaded) else "error")
        try:
            while not self._stop.is_set():
                if self._audio_restart.is_set():
                    self._audio_restart.clear()
                    if mic is not None:
                        mic.stop()
                    mic, noise = self._open_audio()
                if self._need_reset:
                    self._need_reset = False
                    loaded = self._load_recognizers()
                    self._set_state("idle" if loaded else "error")

                data = mic.read(0.2) if mic is not None else None
                if data is None:
                    if mic is None or self._wake is None:
                        time.sleep(0.2)  # waiting for a microphone or model; retry later
                    self._tick_status()
                    continue

                now = self._clock()
                if now - self._last_level_pub >= 0.1:
                    self._last_level_pub = now
                    self.bus.publish("level", value=round(pcm_level(data), 3))
                self._tick_status()

                if self._wake is None:
                    continue
                if self.speaker.busy:  # mute the microphone while talking
                    self._flush()
                    self._deadline = now + self.settings["listen_timeout_sec"]
                    continue
                if self._state == "processing":
                    continue

                clean = noise.process(data)
                if self._state == "idle":
                    self._idle_step(clean)
                elif self._state == "listening":
                    self._listen_step(clean, now)
        finally:
            if mic is not None:
                mic.stop()
            self._mic_active = False

    def _tick_status(self) -> None:
        speaking = bool(self.speaker.busy) if self.speaker else False
        if speaking != self._last_speaking:
            self._last_speaking = speaking
            self.bus.publish("status", **self.status())

    def _flush(self) -> None:
        if self._wake is not None:
            self._wake.Reset()
        if self._cmd is not None:
            self._cmd.Reset()

    def _idle_step(self, clean: bytes) -> None:
        rec = self._wake
        if rec.AcceptWaveform(clean):
            text = recognized_text(rec.Result(), "text")
        else:
            text = recognized_text(rec.PartialResult(), "partial")
        if not text:
            return
        wake_words = self.settings["wake_words"][self.router.language]
        if contains_wake_word(text, wake_words):
            log.info("Wake word detected: %s", text)
            self._flush()
            self._deadline = self._clock() + self.settings["listen_timeout_sec"]
            self._set_state("listening")
            self._chime()
            wake_reply = self.router.packs[self.router.language].message("wake")
            if wake_reply:
                self.speaker.say(wake_reply)

    def _listen_step(self, clean: bytes, now: float) -> None:
        rec = self._cmd
        if rec.AcceptWaveform(clean):
            text = recognized_text(rec.Result(), "text")
            if text:
                self._set_state("processing")
                threading.Thread(target=self._process, args=(text,), name="command", daemon=True).start()
                return
        else:
            if recognized_text(rec.PartialResult(), "partial"):
                self._deadline = now + self.settings["listen_timeout_sec"]  # user is still talking
        if now >= self._deadline:
            log.info("Тайм-аут ожидания команды")
            self._flush()
            self._set_state("idle")

    def _process(self, text: str) -> None:
        try:
            self.submit_text(text, source="voice")
        except Exception:
            log.exception("Сбой при обработке команды")
        finally:
            self._need_reset = True
            self._set_state("idle")
