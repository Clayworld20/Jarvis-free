"""Rule-based natural language understanding.

An intent has one or more *patterns*. A pattern is plain text (matched exactly,
or fuzzily when nothing matches exactly) or may contain ``{placeholders}`` that
capture the rest of the utterance, e.g. ``"открой {app}"``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from .text import normalize, strip_fillers

PLACEHOLDER = re.compile(r"\{(\w+)\}")
FUZZY_THRESHOLD = 0.85


@dataclass(frozen=True)
class Intent:
    id: str
    action: str | None
    patterns: tuple[str, ...]
    responses: tuple[str, ...] = ()
    args: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)


@dataclass
class Match:
    intent: Intent
    params: dict[str, str]
    score: float


@dataclass
class LanguagePack:
    language: str
    intents: list[Intent]
    fillers: tuple[str, ...]
    messages: dict[str, str]

    def message(self, key: str) -> str:
        return self.messages.get(key, self.messages.get("unknown", ""))


def load_pack(language: str, directory: Path) -> LanguagePack:
    data = json.loads((directory / f"{language}.json").read_text(encoding="utf-8"))
    intents = [
        Intent(
            id=item["id"],
            action=item.get("action"),
            patterns=tuple(item["patterns"]),
            responses=tuple(item.get("responses", ())),
        )
        for item in data["intents"]
    ]
    fillers = tuple(normalize(w) for w in data.get("fillers", []))
    return LanguagePack(language, intents, fillers, dict(data.get("messages", {})))


def _compile_pattern(pattern: str) -> tuple[str, re.Pattern | None]:
    """Return (normalised literal text, compiled regex or None if the pattern has no placeholders)."""
    tokens = pattern.split()
    if not any(PLACEHOLDER.fullmatch(t) for t in tokens):
        return " ".join(normalize(pattern).split()), None
    parts = []
    for tok in tokens:
        m = PLACEHOLDER.fullmatch(tok)
        if m:
            parts.append(f"(?P<{m.group(1)}>.+?)")
        else:
            parts.append(re.escape(normalize(tok)))
    regex = re.compile(r"^\s*" + r"\s+".join(parts) + r"\s*$")
    return pattern, regex


class IntentMatcher:
    def __init__(self, intents: Iterable[Intent], fillers: Iterable[str] = (), fuzzy_threshold: float = FUZZY_THRESHOLD):
        self.fillers = tuple(fillers)
        self.fuzzy_threshold = fuzzy_threshold
        self._entries: list[tuple[Intent, str, re.Pattern | None]] = []
        for intent in intents:
            for pattern in intent.patterns:
                literal, regex = _compile_pattern(pattern)
                self._entries.append((intent, literal, regex))

    def match(self, text: str) -> Match | None:
        norm = strip_fillers(normalize(text), self.fillers)
        if not norm:
            return None
        for intent, literal, regex in self._entries:
            if regex is not None:
                m = regex.match(norm)
                if m:
                    params = {k: v.strip() for k, v in m.groupdict().items()}
                    if all(params.values()):
                        return Match(intent, params, 1.0)
            elif literal == norm:
                return Match(intent, {}, 1.0)

        best: Match | None = None
        for intent, literal, regex in self._entries:
            if regex is not None:
                continue
            ratio = SequenceMatcher(None, literal, norm).ratio()
            if ratio >= self.fuzzy_threshold and (best is None or ratio > best.score):
                best = Match(intent, {}, ratio)
        return best
