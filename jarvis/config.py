"""User settings: defaults, JSON persistence, merging and validation."""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger("jarvis.config")

LANGUAGES = ("ru", "en")

DEFAULT_SETTINGS: dict[str, Any] = {
    "language": "ru",
    "ui": {"host": "127.0.0.1", "port": 8765, "window": True},
    "audio": {
        "input_device": None,        # None = system default microphone; otherwise device index or name
        "sample_rate": 16000,        # Vosk models expect 16 kHz
        "block_ms": 50,
        "noise_filter": True,        # high-pass + adaptive noise gate
        "highpass_hz": 80,
        "gate_margin_db": 9.0,       # how far above the estimated noise floor speech must be
    },
    "wake_words": {"ru": ["джарвис", "джервис", "жарвис"], "en": ["jarvis"]},
    "listen_timeout_sec": 8,
    "tts": {"enabled": True, "rate": 180, "volume": 1.0, "voice": ""},
    "models": {"ru": "vosk-model-small-ru-0.22", "en": "vosk-model-small-en-us-0.15"},
    "apps": {
        "блокнот": "notepad", "notepad": "notepad",
        "калькулятор": "calc", "calculator": "calc",
        "проводник": "explorer", "explorer": "explorer",
        "браузер": "https://duckduckgo.com", "browser": "https://duckduckgo.com",
        "ютуб": "https://www.youtube.com", "youtube": "https://www.youtube.com",
    },
    "allow_any_app": False,
    "search_url": "https://duckduckgo.com/?q={query}",
    "confirm_power_actions": True,
    "power_delay_sec": 30,
    "notes_file": "data/notes.txt",
    "allow_script_run_steps": True,
}


class SettingsError(ValueError):
    pass


def merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *patch* into a copy of *base*. Non-dict values replace the old value."""
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _check_range(name: str, value: Any, lo: float, hi: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (lo <= value <= hi):
        raise SettingsError(f"{name} должен быть числом от {lo} до {hi} (получено {value!r})")


def validate(settings: dict[str, Any]) -> dict[str, Any]:
    """Return a validated copy of *settings*; raise SettingsError on invalid values."""
    s = copy.deepcopy(settings)
    if s.get("language") not in LANGUAGES:
        raise SettingsError(f"language должен быть одним из {LANGUAGES}")

    audio = s["audio"]
    if audio.get("input_device") is not None and not isinstance(audio["input_device"], (int, str)):
        raise SettingsError("audio.input_device должен быть null, номером или именем устройства")
    if audio.get("sample_rate") not in (8000, 16000, 22050, 32000, 44100, 48000):
        raise SettingsError("audio.sample_rate должен быть 8000, 16000, 22050, 32000, 44100 или 48000")
    _check_range("audio.block_ms", audio.get("block_ms"), 10, 200)
    _check_range("audio.highpass_hz", audio.get("highpass_hz"), 0, 500)
    _check_range("audio.gate_margin_db", audio.get("gate_margin_db"), 0, 40)

    for lang in LANGUAGES:
        words = s["wake_words"].get(lang)
        if not isinstance(words, list) or not words or not all(isinstance(w, str) and w.strip() for w in words):
            raise SettingsError(f"wake_words.{lang} должен быть непустым списком строк")
        if not isinstance(s["models"].get(lang), str) or not s["models"][lang].strip():
            raise SettingsError(f"models.{lang} должен быть именем папки модели")

    _check_range("listen_timeout_sec", s["listen_timeout_sec"], 2, 60)
    _check_range("tts.rate", s["tts"]["rate"], 50, 400)
    _check_range("tts.volume", s["tts"]["volume"], 0, 1)
    if not isinstance(s["tts"]["voice"], str):
        raise SettingsError("tts.voice должен быть строкой")
    _check_range("ui.port", s["ui"]["port"], 1, 65535)
    _check_range("power_delay_sec", s["power_delay_sec"], 5, 600)

    if not isinstance(s["apps"], dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in s["apps"].items()):
        raise SettingsError("apps должен быть объектом {имя: команда или URL}")
    if "{query}" not in s["search_url"]:
        raise SettingsError("search_url должен содержать {query}")
    return s


def load(path: Path = paths.SETTINGS_FILE) -> dict[str, Any]:
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            settings = merge(settings, stored)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Не удалось прочитать %s (%s), используются значения по умолчанию", path, exc)
    try:
        return validate(settings)
    except SettingsError as exc:
        log.warning("Некорректные настройки (%s), используются значения по умолчанию", exc)
        return copy.deepcopy(DEFAULT_SETTINGS)


def save(settings: dict[str, Any], path: Path = paths.SETTINGS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
