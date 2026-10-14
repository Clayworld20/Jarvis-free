"""Command router: text -> intent -> action -> reply text."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Iterable

from .actions import Actions
from .nlu import Intent, IntentMatcher, LanguagePack
from .scripts import Script

log = logging.getLogger("jarvis.commands")


@dataclass
class CommandResult:
    text: str
    ok: bool
    recognized: bool
    input: str = ""
    intent_id: str | None = None
    action: str | None = None


class _SafeVars(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _safe_format(template: str, variables: dict[str, Any]) -> str:
    try:
        return template.format_map(_SafeVars({k: str(v) for k, v in variables.items()}))
    except (ValueError, IndexError):
        return template


class Router:
    def __init__(
        self,
        settings: dict[str, Any],
        actions: Actions,
        packs: dict[str, LanguagePack],
        scripts: Iterable[Script] = (),
        language: str | None = None,
    ):
        self.settings = settings
        self.actions = actions
        self.packs = packs
        self.scripts: list[Script] = list(scripts)
        self.actions.set_scripts(self.scripts)
        self.language = ""
        self.matcher: IntentMatcher | None = None
        self.set_language(language or settings.get("language", "ru"))

    def set_language(self, language: str) -> None:
        if language not in self.packs:
            raise ValueError(f"нет языкового пакета {language!r}")
        self.language = language
        self.actions.language = language
        self._rebuild()

    def set_scripts(self, scripts: Iterable[Script]) -> None:
        self.scripts = list(scripts)
        self.actions.set_scripts(self.scripts)
        self._rebuild()

    def _script_intents(self) -> list[Intent]:
        result = []
        for script in self.scripts:
            phrases = script.triggers.get(self.language) or []
            if phrases:
                result.append(Intent(id=f"script:{script.name}", action="script", patterns=tuple(phrases), args={"name": script.name}))
        return result

    def _rebuild(self) -> None:
        pack = self.packs[self.language]
        self.matcher = IntentMatcher(list(pack.intents) + self._script_intents(), pack.fillers)

    def execute(self, text: str) -> CommandResult:
        pack = self.packs[self.language]
        text = (text or "").strip()
        match = self.matcher.match(text) if text else None
        if match is None:
            return CommandResult(text=pack.message("unknown"), ok=False, recognized=False, input=text)

        intent = match.intent
        params = {**intent.args, **match.params}
        try:
            out = self.actions.run(intent.action, params) if intent.action else None
            reply, ok = self._render(pack, intent, out, params)
        except Exception:  # a failing command must never kill the assistant
            log.exception("Ошибка выполнения команды %s", intent.id)
            reply, ok = pack.message("error"), False
        return CommandResult(text=reply, ok=ok, recognized=True, input=text, intent_id=intent.id, action=intent.action)

    @staticmethod
    def _render(pack: LanguagePack, intent: Intent, out: Any, params: dict[str, str]) -> tuple[str, bool]:
        if isinstance(out, str):
            return out, True
        data = dict(out or {})
        ok = bool(data.pop("ok", True))
        msg = data.pop("msg", None)
        variables = {**params, **data}
        if msg:
            template = pack.message(msg)
        elif intent.responses:
            template = random.choice(intent.responses)
        else:
            template = pack.message("done")
        return _safe_format(template, variables), ok
