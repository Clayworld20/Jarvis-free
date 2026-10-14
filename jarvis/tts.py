"""Text-to-speech using pyttsx3 (SAPI5 on Windows, eSpeak on Linux, NSSpeech on macOS)."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable

log = logging.getLogger("jarvis.tts")

VOICE_HINTS = {"ru": ("russian", "ru-ru", "ru_ru", "irina", "pavel", "ru"), "en": ("english", "en-us", "en_us", "david", "zira", "en")}


def pick_voice(voices: list[Any], language: str, preferred: str = "") -> str | None:
    """Return the id of the best matching voice. Pure function for easy testing."""
    def haystack(v: Any) -> str:
        langs = " ".join(str(x) for x in (getattr(v, "languages", []) or []))
        return f"{getattr(v, 'id', '')} {getattr(v, 'name', '')} {langs}".lower()

    if preferred:
        for v in voices:
            if preferred.lower() in haystack(v):
                return v.id
    for hint in VOICE_HINTS.get(language, ()):
        for v in voices:
            if hint in haystack(v):
                return v.id
    return None


class Speaker:
    """Speaks queued phrases on a background thread. ``busy`` is True while talking."""

    def __init__(self, settings: dict[str, Any], engine_factory: Callable[[], Any] | None = None):
        self.settings = settings
        self._engine_factory = engine_factory
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._speaking = False
        self._engine: Any = None
        self._lock = threading.Lock()
        self.available = True
        self.error: str | None = None
        self._thread = threading.Thread(target=self._worker, name="tts", daemon=True)
        self._thread.start()

    @property
    def busy(self) -> bool:
        return self._speaking or not self._queue.empty()

    def say(self, text: str, language: str | None = None) -> None:
        if text and text.strip():
            self._queue.put((text, language or self.settings.get("language", "ru")))

    def stop(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.stop()
                except Exception:
                    pass

    def _create_engine(self) -> Any:
        if self._engine_factory is not None:
            return self._engine_factory()
        import pyttsx3

        return pyttsx3.init()

    def _configure(self, engine: Any, language: str) -> None:
        tts = self.settings.get("tts", {})
        engine.setProperty("rate", int(tts.get("rate", 180)))
        engine.setProperty("volume", float(tts.get("volume", 1.0)))
        voice_id = pick_voice(engine.getProperty("voices") or [], language, tts.get("voice", ""))
        if voice_id:
            engine.setProperty("voice", voice_id)

    def _worker(self) -> None:
        while True:
            text, language = self._queue.get()
            self._speaking = True  # set before doing anything so `busy` never has a gap
            try:
                if not self.settings.get("tts", {}).get("enabled", True):
                    log.info("(речь отключена) %s", text)
                    continue
                with self._lock:
                    if self._engine is None:
                        self._engine = self._create_engine()
                    engine = self._engine
                self._configure(engine, language)
                log.info("Говорю: %s", text)
                engine.say(text)
                engine.runAndWait()
                self.available = True
                self.error = None
            except Exception as exc:
                self.available = False
                self.error = str(exc)
                log.error("Синтез речи недоступен: %s (текст: %s)", exc, text)
                with self._lock:
                    self._engine = None
            finally:
                self._speaking = False
