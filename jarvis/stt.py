"""Speech recognition with Vosk: wake-word spotting and full command recognition."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from .text import normalize

log = logging.getLogger("jarvis.stt")


class ModelMissingError(RuntimeError):
    pass


def contains_wake_word(text: str, wake_words: list[str]) -> bool:
    """True if any wake word (a word or phrase) occurs as whole words in *text*."""
    tokens = f" {normalize(text)} "
    return any(f" {normalize(w)} " in tokens for w in wake_words if normalize(w))


def recognized_text(payload: str, key: str) -> str:
    """Extract ``text`` (final) or ``partial`` from a Vosk JSON result string."""
    try:
        return str(json.loads(payload).get(key, "")).strip()
    except (json.JSONDecodeError, AttributeError):
        return ""


class SpeechEngine:
    """Owns Vosk models (loaded lazily, one per language) and creates recognizers.

    ``recognizer_factory`` / ``model_factory`` are injectable so the logic can be
    tested without real models.
    """

    def __init__(
        self,
        models_dir: Path,
        model_names: dict[str, str],
        wake_words: dict[str, list[str]],
        sample_rate: int = 16000,
        model_factory: Callable[[str], Any] | None = None,
        recognizer_factory: Callable[..., Any] | None = None,
    ):
        self.models_dir = models_dir
        self.model_names = model_names
        self.wake_words = wake_words
        self.sample_rate = sample_rate
        self._model_factory = model_factory
        self._recognizer_factory = recognizer_factory
        self._models: dict[str, Any] = {}

    def configure(self, model_names: dict[str, str], wake_words: dict[str, list[str]], sample_rate: int) -> None:
        """Refresh configuration (called before recognizers are rebuilt, so setting changes take effect)."""
        self.model_names = dict(model_names)
        self.wake_words = {k: list(v) for k, v in wake_words.items()}
        self.sample_rate = sample_rate

    def model_path(self, language: str) -> Path:
        return self.models_dir / self.model_names[language]

    def is_model_available(self, language: str) -> bool:
        return self.model_path(language).is_dir()

    def _model(self, language: str) -> Any:
        path = self.model_path(language)
        key = str(path)  # cache by path, so changing the model folder in settings loads the new model
        if key not in self._models:
            if not path.is_dir():
                raise ModelMissingError(
                    f"Модель распознавания для «{language}» не найдена: {path}. "
                    "Запустите tools/download_models.py или START_JARVIS.bat."
                )
            log.info("Загрузка модели распознавания %s...", path.name)
            if self._model_factory is not None:
                self._models[key] = self._model_factory(key)
            else:
                from vosk import Model, SetLogLevel

                SetLogLevel(-1)
                self._models[key] = Model(key)
        return self._models[key]

    def _new_recognizer(self, language: str, grammar: list[str] | None = None) -> Any:
        model = self._model(language)
        if self._recognizer_factory is not None:
            return self._recognizer_factory(model, self.sample_rate, grammar)
        from vosk import KaldiRecognizer

        if grammar:
            return KaldiRecognizer(model, self.sample_rate, json.dumps(grammar, ensure_ascii=False))
        return KaldiRecognizer(model, self.sample_rate)

    def wake_recognizer(self, language: str) -> Any:
        """Recognizer restricted to the wake words (+ [unk]) — cheap and robust to background speech."""
        grammar = [normalize(w) for w in self.wake_words[language]] + ["[unk]"]
        return self._new_recognizer(language, grammar)

    def command_recognizer(self, language: str) -> Any:
        return self._new_recognizer(language, None)
