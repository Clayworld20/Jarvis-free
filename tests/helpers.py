"""Fakes shared by the tests: no audio hardware, no Vosk models, no speech synthesis."""
import copy
from datetime import datetime

from jarvis import config, paths
from jarvis.actions import Actions
from jarvis.commands import Router
from jarvis.nlu import load_pack
from jarvis.scripts import load_scripts


class FakeSpeaker:
    def __init__(self):
        self.said = []
        self.busy = False
        self.available = True
        self.error = None
        self.stopped = 0

    def say(self, text, language=None):
        self.said.append(text)

    def stop(self):
        self.stopped += 1


class FakePopen:
    def __init__(self):
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        return None


def make_settings(**overrides):
    settings = copy.deepcopy(config.DEFAULT_SETTINGS)
    for key, value in overrides.items():
        settings[key] = value
    return config.validate(settings)


def make_packs():
    return {lang: load_pack(lang, paths.INTENTS_DIR) for lang in config.LANGUAGES}


def make_router(settings=None, speaker=None, scripts=None, now=None, platform="win32", tmp_path=None):
    settings = settings or make_settings()
    if tmp_path is not None:
        settings["notes_file"] = str(tmp_path / "notes.txt")
    scripts = scripts if scripts is not None else load_scripts(paths.SCRIPTS_DIR)[0]
    popen = FakePopen()
    opened = []
    actions = Actions(
        settings,
        speaker=speaker,
        scripts=scripts,
        now=now or (lambda: datetime(2026, 10, 14, 14, 5)),
        opener=lambda url: opened.append(url),
        platform=platform,
        popen=popen,
        which=lambda name: None,
        sleep=lambda s: None,
    )
    router = Router(settings, actions, make_packs(), scripts)
    router.popen = popen
    router.opened = opened
    return router
