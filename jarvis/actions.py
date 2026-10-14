"""System actions the assistant can perform (open apps/sites, search, lock, power, notes...).

Every ``do_<name>`` method returns either ``None``, a ``str`` (final reply) or a
``dict`` with optional keys: ``msg`` (message key from the language pack),
``ok`` (bool) and any template variables.
"""
from __future__ import annotations

import logging
import platform as pyplatform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote_plus
import webbrowser

from . import paths
from .scripts import Script, ScriptRunner
from .text import normalize

log = logging.getLogger("jarvis.actions")

DATE_FORMATS = {"ru": "%d.%m.%Y", "en": "%B %d, %Y"}
POWER_WORDS = {
    "ru": {"shutdown": "выключение", "restart": "перезагрузку"},
    "en": {"shutdown": "shutdown", "restart": "restart"},
}


class Actions:
    def __init__(
        self,
        settings: dict[str, Any],
        speaker: Any = None,
        scripts: Iterable[Script] = (),
        *,
        now: Callable[[], datetime] = datetime.now,
        opener: Callable[[str], Any] = webbrowser.open,
        platform: str = sys.platform,
        popen: Callable[..., Any] = subprocess.Popen,
        which: Callable[[str], str | None] = shutil.which,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings  # shared dict; the GUI updates it in place
        self.speaker = speaker
        self.language = settings.get("language", "ru")
        self.now = now
        self.opener = opener
        self.platform = platform
        self.popen = popen
        self.which = which
        self.sleep = sleep
        self.pending: tuple[str, str] | None = None
        self.set_scripts(scripts)

    # ----- helpers -------------------------------------------------------
    def set_scripts(self, scripts: Iterable[Script]) -> None:
        self.scripts = {s.name: s for s in scripts}

    def is_windows(self) -> bool:
        return self.platform.startswith("win")

    def resolve_app(self, name: str) -> str | None:
        wanted = normalize(name)
        for key, target in self.settings.get("apps", {}).items():
            if normalize(key) == wanted:
                return target
        return None

    def open_target(self, name: str) -> bool:
        """Open a known app/site name, a URL, or (if allowed) any program name."""
        target = self.resolve_app(name)
        if target is None:
            if name.startswith(("http://", "https://")):
                target = name
            elif self.settings.get("allow_any_app"):
                target = name
            else:
                return False
        if target.startswith(("http://", "https://")):
            self.opener(target)
            return True
        try:
            self.popen([target], shell=False)  # noqa: S603 - argv list, no shell
            return True
        except OSError as exc:
            log.warning("Не удалось запустить %s: %s", target, exc)
            return False

    def add_note(self, text: str) -> None:
        path = Path(self.settings.get("notes_file", "data/notes.txt"))
        if not path.is_absolute():
            path = paths.ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{self.now():%Y-%m-%d %H:%M} {text}\n")

    def _say(self, text: str) -> None:
        if self.speaker is not None:
            self.speaker.say(text)
        else:
            log.info("(речь) %s", text)

    # ----- dispatch ------------------------------------------------------
    def run(self, action: str, params: dict[str, str]) -> Any:
        handler = getattr(self, f"do_{action}", None)
        if handler is None:
            raise KeyError(f"неизвестное действие {action!r}")
        return handler(params)

    # ----- actions -------------------------------------------------------
    def do_time(self, params: dict[str, str]) -> dict[str, Any]:
        return {"time": self.now().strftime("%H:%M")}

    def do_date(self, params: dict[str, str]) -> dict[str, Any]:
        return {"date": self.now().strftime(DATE_FORMATS.get(self.language, "%Y-%m-%d"))}

    def do_open_app(self, params: dict[str, str]) -> dict[str, Any]:
        app = params.get("app", "").strip()
        if app and self.open_target(app):
            return {"msg": "opened", "app": app}
        return {"msg": "unknown_app", "app": app, "ok": False}

    def do_search_web(self, params: dict[str, str]) -> dict[str, Any]:
        query = params.get("query", "").strip()
        if not query:
            return {"msg": "nothing_to_search", "ok": False}
        self.opener(self.settings["search_url"].format(query=quote_plus(query)))
        return {"msg": "searching", "query": query}

    def do_lock(self, params: dict[str, str]) -> dict[str, Any]:
        try:
            if self.is_windows():
                import ctypes  # Windows only

                ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
            elif self.platform == "darwin":
                self.popen(["pmset", "displaysleepnow"])
            else:
                self.popen(["loginctl", "lock-session"])
        except OSError as exc:
            log.error("Блокировка не удалась: %s", exc)
            return {"msg": "error", "ok": False}
        return {"msg": "locked"}

    def do_power_off(self, params: dict[str, str]) -> dict[str, Any]:
        return self._request_power("shutdown")

    def do_reboot(self, params: dict[str, str]) -> dict[str, Any]:
        return self._request_power("restart")

    def _request_power(self, kind: str) -> dict[str, Any]:
        if not self.is_windows():
            return {"msg": "power_unsupported", "ok": False}
        if self.settings.get("confirm_power_actions", True):
            self.pending = ("power", kind)
            return {"msg": "confirm_power"}
        return self._do_power(kind)

    def _do_power(self, kind: str) -> dict[str, Any]:
        delay = int(self.settings.get("power_delay_sec", 30))
        flag = "/s" if kind == "shutdown" else "/r"
        self.popen(["shutdown", flag, "/t", str(delay)], shell=False)
        word = POWER_WORDS.get(self.language, POWER_WORDS["en"])[kind]
        return {"msg": "power_scheduled", "kind": word, "delay": delay}

    def do_confirm(self, params: dict[str, str]) -> dict[str, Any]:
        if not self.pending:
            return {"msg": "nothing_to_confirm", "ok": False}
        _, kind = self.pending
        self.pending = None
        if not self.is_windows():
            return {"msg": "power_unsupported", "ok": False}
        return self._do_power(kind)

    def do_cancel_power(self, params: dict[str, str]) -> dict[str, Any]:
        self.pending = None
        if self.is_windows():
            try:
                self.popen(["shutdown", "/a"], shell=False)
            except OSError:
                pass
        return {"msg": "power_cancelled"}

    def do_stop(self, params: dict[str, str]) -> dict[str, Any]:
        self.pending = None
        if self.speaker is not None:
            self.speaker.stop()
        return {"msg": "stopped"}

    def do_note(self, params: dict[str, str]) -> dict[str, Any]:
        text = params.get("text", "").strip()
        if not text:
            return {"msg": "note_empty", "ok": False}
        self.add_note(text)
        return {"msg": "note_saved"}

    def do_system_info(self, params: dict[str, str]) -> dict[str, Any]:
        return {"msg": "system_info", "info": f"{pyplatform.system()} {pyplatform.release()}"}

    def do_help(self, params: dict[str, str]) -> dict[str, Any]:
        return {"msg": "help"}

    def do_script(self, params: dict[str, str]) -> dict[str, Any]:
        name = params.get("name", "")
        script = self.scripts.get(name)
        if script is None:
            return {"msg": "script_missing", "name": name, "ok": False}
        runner = ScriptRunner(
            say=self._say,
            open_target=self.open_target,
            search=lambda q: self.do_search_web({"query": q}),
            add_note=self.add_note,
            allow_run=bool(self.settings.get("allow_script_run_steps", True)),
            sleep=self.sleep,
        )
        runner.run(script)
        return {"msg": "script_done"}
