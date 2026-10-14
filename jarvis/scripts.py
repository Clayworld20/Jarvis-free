"""User automation scripts.

A script is a JSON file in ``resources/scripts``::

    {
      "name": "work_mode",
      "description": "Open the work tools",
      "triggers": {"ru": ["режим работы"], "en": ["work mode"]},
      "steps": [
        {"type": "speak", "text": "Включаю режим работы."},
        {"type": "open", "target": "браузер"},
        {"type": "wait", "seconds": 2},
        {"type": "run", "command": ["notepad.exe", "todo.txt"]}
      ]
    }

Steps are a fixed, validated set (no arbitrary code). ``run`` takes an argument
list and is executed without a shell.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("jarvis.scripts")

NAME_RE = re.compile(r"^[a-z0-9_\-]{1,40}$")
MAX_STEPS = 50
MAX_WAIT_SEC = 30
STEP_FIELDS = {
    "speak": {"text": str},
    "open": {"target": str},
    "search": {"query": str},
    "wait": {"seconds": (int, float)},
    "note": {"text": str},
    "run": {"command": list},
}


class ScriptError(ValueError):
    pass


@dataclass
class Script:
    name: str
    steps: list[dict[str, Any]]
    triggers: dict[str, list[str]] = field(default_factory=dict)
    description: str = ""
    path: Path | None = None


def validate_script(data: Any, default_name: str, path: Path | None = None) -> Script:
    if not isinstance(data, dict):
        raise ScriptError("корень файла должен быть объектом")
    name = str(data.get("name", default_name))
    if not NAME_RE.match(name):
        raise ScriptError(f"недопустимое имя сценария {name!r} (допустимы a-z, 0-9, _ и -)")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ScriptError("поле steps должно быть непустым списком")
    if len(steps) > MAX_STEPS:
        raise ScriptError(f"в сценарии не более {MAX_STEPS} шагов")
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or step.get("type") not in STEP_FIELDS:
            raise ScriptError(f"шаг {i}: неизвестный тип (допустимы {', '.join(STEP_FIELDS)})")
        for key, kind in STEP_FIELDS[step["type"]].items():
            if key not in step or not isinstance(step[key], kind):
                raise ScriptError(f"шаг {i} ({step['type']}): поле {key!r} обязательно и имеет неверный тип")
        if step["type"] == "run" and (not step["command"] or not all(isinstance(a, str) for a in step["command"])):
            raise ScriptError(f"шаг {i}: command должен быть непустым списком строк")
        if step["type"] == "wait" and not (0 <= step["seconds"] <= MAX_WAIT_SEC):
            raise ScriptError(f"шаг {i}: seconds должен быть от 0 до {MAX_WAIT_SEC}")

    triggers = data.get("triggers", {})
    if not isinstance(triggers, dict) or not all(
        isinstance(v, list) and all(isinstance(t, str) for t in v) for v in triggers.values()
    ):
        raise ScriptError("triggers должен быть объектом {язык: [фразы]}")
    return Script(name=name, steps=steps, triggers=triggers, description=str(data.get("description", "")), path=path)


def load_scripts(directory: Path) -> tuple[list[Script], list[str]]:
    scripts: list[Script] = []
    errors: list[str] = []
    if not directory.exists():
        return scripts, errors
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            scripts.append(validate_script(data, path.stem, path))
        except (json.JSONDecodeError, OSError, ScriptError) as exc:
            errors.append(f"{path.name}: {exc}")
            log.error("Сценарий %s пропущен: %s", path.name, exc)
    return scripts, errors


class ScriptRunner:
    """Executes a script's steps through the action layer (see commands.Actions)."""

    def __init__(
        self,
        say: Callable[[str], None],
        open_target: Callable[[str], bool],
        search: Callable[[str], None],
        add_note: Callable[[str], None],
        allow_run: bool = True,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.say = say
        self.open_target = open_target
        self.search = search
        self.add_note = add_note
        self.allow_run = allow_run
        self.sleep = sleep

    def run(self, script: Script) -> None:
        log.info("Запуск сценария %s (%d шагов)", script.name, len(script.steps))
        for step in script.steps[:MAX_STEPS]:
            kind = step["type"]
            if kind == "speak":
                self.say(step["text"])
            elif kind == "open":
                if not self.open_target(step["target"]):
                    log.warning("Сценарий %s: не удалось открыть %s", script.name, step["target"])
            elif kind == "search":
                self.search(step["query"])
            elif kind == "wait":
                self.sleep(min(float(step["seconds"]), MAX_WAIT_SEC))
            elif kind == "note":
                self.add_note(step["text"])
            elif kind == "run":
                if not self.allow_run:
                    log.warning("Сценарий %s: шаг run запрещён настройкой allow_script_run_steps", script.name)
                    continue
                log.info("Сценарий %s: запуск %s", script.name, step["command"][0])
                subprocess.Popen(step["command"], shell=False)  # noqa: S603 - argv list, no shell
