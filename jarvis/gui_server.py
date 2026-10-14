"""Local web dashboard: static files, JSON API and a Server-Sent Events stream.

It binds to 127.0.0.1 by default. When bound to a loopback address only requests
whose Host header is localhost/127.0.0.1 are accepted (protects against DNS rebinding).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import mimetypes
import queue
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import __version__, config, paths
from .audio import list_input_devices

log = logging.getLogger("jarvis.gui")
MAX_BODY = 64 * 1024
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass
class AppContext:
    settings: dict[str, Any]
    bus: Any
    assistant: Any
    router: Any
    speaker: Any
    scripts: list = field(default_factory=list)
    script_errors: list[str] = field(default_factory=list)
    packs: dict[str, Any] = field(default_factory=dict)
    settings_path: Path = paths.SETTINGS_FILE

    def apply_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Validate and apply a partial settings update. Returns flags describing what must be reloaded."""
        old = config.validate(self.settings)
        new = config.validate(config.merge(old, patch))
        changes = {
            "ui": old["ui"] != new["ui"],
            "audio": old["audio"] != new["audio"],
            "recognizers": old["wake_words"] != new["wake_words"] or old["models"] != new["models"],
            "language": old["language"] != new["language"],
        }
        # update the shared dict in place so Router/Actions/Speaker keep seeing the same object
        for key, value in new.items():  # key-by-key: the key set never changes, so readers never see a partial dict
            self.settings[key] = value
        config.save(self.settings, self.settings_path)
        if changes["language"]:
            self.assistant.set_language(new["language"])
        if changes["audio"]:
            self.assistant.restart_audio()
        if changes["recognizers"]:
            self.assistant.reload_recognizers()
        self.bus.publish("settings", settings=self.settings)
        return changes

    def commands_overview(self) -> dict[str, Any]:
        lang = self.router.language
        pack = self.packs[lang]
        return {
            "language": lang,
            "intents": [
                {"id": i.id, "action": i.action, "patterns": list(i.patterns), "responses": list(i.responses)}
                for i in pack.intents
            ],
            "scripts": [
                {
                    "name": s.name,
                    "description": s.description,
                    "triggers": s.triggers.get(lang, []),
                    "steps": len(s.steps),
                }
                for s in self.scripts
            ],
            "script_errors": self.script_errors,
        }


def make_handler(app: AppContext, loopback_only: bool) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"JARVIS-free/{__version__}"

        def log_message(self, fmt: str, *args: Any) -> None:  # keep the console quiet
            log.debug("HTTP " + fmt, *args)

        # ----- helpers ---------------------------------------------------
        def _host_ok(self) -> bool:
            if not loopback_only:
                return True
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            return host in LOOPBACK_HOSTS

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: Any, status: int = 200) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _error(self, status: int, message: str) -> None:
            self._json({"ok": False, "error": message}, status)

        def _body(self) -> dict[str, Any] | None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._error(413, "слишком большой запрос")
                return None
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._error(400, "некорректный JSON")
                return None
            if not isinstance(data, dict):
                self._error(400, "ожидается JSON-объект")
                return None
            return data

        # ----- routing ---------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802
            if not self._host_ok():
                return self._error(403, "forbidden host")
            path = urlsplit(self.path).path
            if path == "/api/events":
                return self._sse()
            if path.startswith("/api/"):
                return self._api_get(path)
            return self._static(path)

        def do_POST(self) -> None:  # noqa: N802
            if not self._host_ok():
                return self._error(403, "forbidden host")
            path = urlsplit(self.path).path
            data = self._body()
            if data is None:
                return
            try:
                return self._api_post(path, data)
            except config.SettingsError as exc:
                return self._error(400, str(exc))
            except Exception as exc:
                log.exception("Ошибка API %s", path)
                return self._error(500, str(exc))

        def _api_get(self, path: str) -> None:
            if path == "/api/status":
                return self._json({**app.assistant.status(), "version": __version__})
            if path == "/api/settings":
                return self._json(app.settings)
            if path == "/api/history":
                return self._json(app.bus.recent("history", 200))
            if path == "/api/logs":
                return self._json(app.bus.recent("log", 300))
            if path == "/api/commands":
                return self._json(app.commands_overview())
            if path == "/api/devices":
                return self._json(list_input_devices())
            if path == "/api/health":
                return self._json({"ok": True})
            return self._error(404, "not found")

        def _api_post(self, path: str, data: dict[str, Any]) -> None:
            if path == "/api/command":
                text = str(data.get("text", "")).strip()
                if not text:
                    return self._error(400, "пустая команда")
                result = app.assistant.submit_text(text, source="gui")
                return self._json({"ok": result.ok, "reply": result.text, "recognized": result.recognized, "intent": result.intent_id})
            if path == "/api/settings":
                patch = data.get("settings", data)
                if not isinstance(patch, dict):
                    return self._error(400, "settings должен быть объектом")
                changes = app.apply_settings(patch)
                return self._json({"ok": True, "settings": app.settings, "restart_required": changes["ui"]})
            if path == "/api/stop":
                app.speaker.stop()
                return self._json({"ok": True})
            if path == "/api/scripts/reload":
                from .scripts import load_scripts

                app.scripts, app.script_errors = load_scripts(paths.SCRIPTS_DIR)
                app.router.set_scripts(app.scripts)
                return self._json({"ok": True, "scripts": len(app.scripts), "errors": app.script_errors})
            return self._error(404, "not found")

        def _static(self, path: str) -> None:
            name = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (paths.WEB_DIR / name).resolve()
            if paths.WEB_DIR.resolve() not in target.parents or not target.is_file():
                return self._error(404, "not found")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith(("javascript", "json")):
                ctype += "; charset=utf-8"
            self._send(200, target.read_bytes(), ctype)

        def _sse(self) -> None:
            q = app.bus.subscribe()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                # initial snapshot so a freshly opened window is in sync
                snapshot = {"type": "status", "time": 0, **app.assistant.status()}
                self.wfile.write(f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n".encode("utf-8"))
                self.wfile.flush()
                while True:
                    try:
                        event = q.get(timeout=15)
                        payload = f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
                    except queue.Empty:
                        payload = ": ping\n\n"
                    self.wfile.write(payload.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                app.bus.unsubscribe(q)

    return Handler


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server(app: AppContext, host: str, port: int, max_tries: int = 10) -> _Server:
    """Bind the server, trying successive ports if *port* is taken."""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host in LOOPBACK_HOSTS
    last_error: OSError | None = None
    for offset in range(max_tries):
        try:
            server = _Server((host, port + offset), make_handler(app, loopback))
            if offset:
                log.warning("Порт %d занят, используется %d", port, port + offset)
            return server
        except OSError as exc:
            last_error = exc
    raise OSError(f"Не удалось открыть порт {port}-{port + max_tries - 1}: {last_error}")


def serve_in_background(server: _Server) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, name="gui-http", daemon=True)
    thread.start()
    return thread
