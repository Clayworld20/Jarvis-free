"""Application entry point: ``python -m jarvis``."""
from __future__ import annotations

import argparse
import logging
import sys
import time
import webbrowser

from . import __version__, config, paths
from .actions import Actions
from .assistant import Assistant
from .commands import Router
from .events import EventBus
from .gui_server import AppContext, create_server, serve_in_background
from .logsetup import setup_logging
from .nlu import load_pack
from .scripts import load_scripts
from .stt import SpeechEngine
from .tts import Speaker

log = logging.getLogger("jarvis")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="jarvis", description="JARVIS-free: офлайн голосовой ассистент")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--language", choices=config.LANGUAGES, help="язык распознавания и ответов")
    p.add_argument("--host", help="адрес веб-интерфейса (по умолчанию 127.0.0.1)")
    p.add_argument("--port", type=int, help="порт веб-интерфейса (по умолчанию 8765)")
    p.add_argument("--no-gui", action="store_true", help="не запускать веб-интерфейс")
    p.add_argument("--no-window", action="store_true", help="не открывать окно, только сервер/браузер")
    p.add_argument("--text", action="store_true", help="консольный режим: команды вводятся с клавиатуры, микрофон не используется")
    p.add_argument("--debug", action="store_true", help="подробный журнал")
    return p.parse_args(argv)


def run_window(url: str) -> bool:
    """Open a native window (WebView2 on Windows). Returns False if pywebview is unavailable."""
    try:
        import webview  # pywebview
    except ImportError:
        return False
    try:
        webview.create_window("JARVIS", url, width=535, height=714, min_size=(420, 520), background_color="#050a0f")
        webview.start()
    except Exception as exc:  # e.g. WebView2 runtime missing -> use the default browser instead
        log.warning("Окно приложения не открылось (%s)", exc)
        return False
    return True


def repl(assistant: Assistant) -> None:
    print("Консольный режим. Введите команду (например: «который час»), «exit» — выход.")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if line.lower() in {"exit", "quit", "выход"}:
            return
        if line:
            result = assistant.submit_text(line, source="console")
            print(result.text)


def build(args: argparse.Namespace) -> AppContext:
    paths.ensure_dirs()
    settings = config.load()
    if args.language:
        settings["language"] = args.language
    if args.host:
        settings["ui"]["host"] = args.host
    if args.port:
        settings["ui"]["port"] = args.port
    settings = config.validate(settings)

    bus = EventBus()
    setup_logging(bus, console=True, debug=args.debug)
    packs = {lang: load_pack(lang, paths.INTENTS_DIR) for lang in config.LANGUAGES}
    scripts, script_errors = load_scripts(paths.SCRIPTS_DIR)
    speaker = Speaker(settings)
    actions = Actions(settings, speaker, scripts)
    router = Router(settings, actions, packs, scripts)
    speech = SpeechEngine(paths.MODELS_DIR, settings["models"], settings["wake_words"], settings["audio"]["sample_rate"])
    assistant = Assistant(settings, bus, router, speaker, speech)
    return AppContext(
        settings=settings,
        bus=bus,
        assistant=assistant,
        router=router,
        speaker=speaker,
        scripts=scripts,
        script_errors=script_errors,
        packs=packs,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app = build(args)
    log.info("JARVIS-free %s запускается (язык: %s)", __version__, app.settings["language"])

    if not args.text:
        app.assistant.start()

    server = None
    url = ""
    if not args.no_gui:
        host, port = app.settings["ui"]["host"], app.settings["ui"]["port"]
        server = create_server(app, host, port)
        serve_in_background(server)
        local_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
        url = f"http://{local_host}:{server.server_address[1]}/"
        log.info("Веб-интерфейс: %s", url)

    try:
        if args.text:
            repl(app.assistant)
        elif server is not None and app.settings["ui"]["window"] and not args.no_window:
            if not run_window(url):
                log.info("pywebview не установлен, открываю браузер")
                webbrowser.open(url)
                _wait_forever()
        else:
            if url:
                log.info("Откройте интерфейс в браузере: %s", url)
            _wait_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.assistant.stop()
        if server is not None:
            server.shutdown()
            server.server_close()
        log.info("JARVIS остановлен")
    return 0


def _wait_forever() -> None:
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    sys.exit(main())
