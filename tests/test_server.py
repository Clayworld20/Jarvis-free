import http.client
import json
import threading

import pytest

from jarvis import paths
from jarvis.assistant import Assistant
from jarvis.events import EventBus
from jarvis.gui_server import AppContext, create_server, serve_in_background
from jarvis.scripts import load_scripts
from tests.helpers import FakeSpeaker, make_packs, make_router, make_settings


@pytest.fixture()
def app(tmp_path):
    settings = make_settings()
    settings["notes_file"] = str(tmp_path / "notes.txt")
    bus = EventBus()
    speaker = FakeSpeaker()
    router = make_router(settings, speaker=speaker, tmp_path=tmp_path)
    assistant = Assistant(settings, bus, router, speaker, None)
    scripts, errors = load_scripts(paths.SCRIPTS_DIR)
    ctx = AppContext(
        settings=settings,
        bus=bus,
        assistant=assistant,
        router=router,
        speaker=speaker,
        scripts=scripts,
        script_errors=errors,
        packs=make_packs(),
        settings_path=tmp_path / "settings.json",
    )
    server = create_server(ctx, "127.0.0.1", 0)
    serve_in_background(server)
    yield ctx, server.server_address[1]
    server.shutdown()
    server.server_close()


def _request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    payload = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    conn.request(method, path, body=payload, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_status_and_settings(app):
    ctx, port = app
    status, data = _request(port, "GET", "/api/status")
    assert status == 200 and json.loads(data)["language"] == "ru"
    status, data = _request(port, "GET", "/api/settings")
    assert json.loads(data)["ui"]["port"] == 8765


def test_command_endpoint_runs_router(app):
    ctx, port = app
    status, data = _request(port, "POST", "/api/command", {"text": "который час"})
    body = json.loads(data)
    assert status == 200 and body["ok"] and body["reply"] == "Сейчас 14:05."
    status, data = _request(port, "POST", "/api/command", {"text": "   "})
    assert status == 400


def test_settings_update_is_validated_saved_and_applied(app):
    ctx, port = app
    status, data = _request(port, "POST", "/api/settings", {"settings": {"language": "en", "tts": {"rate": 200}}})
    body = json.loads(data)
    assert status == 200 and body["settings"]["language"] == "en"
    assert ctx.router.language == "en"           # applied live
    assert ctx.settings["tts"]["rate"] == 200    # shared dict updated in place
    assert (ctx.settings_path).exists()          # persisted

    status, data = _request(port, "POST", "/api/settings", {"settings": {"language": "xx"}})
    assert status == 400 and "language" in json.loads(data)["error"]


def test_settings_port_change_requires_restart(app):
    ctx, port = app
    status, data = _request(port, "POST", "/api/settings", {"settings": {"ui": {"port": 9000}}})
    assert json.loads(data)["restart_required"] is True


def test_static_files_and_traversal_protection(app):
    ctx, port = app
    status, data = _request(port, "GET", "/")
    assert status == 200 and b"JARVIS" in data
    status, _ = _request(port, "GET", "/app.js")
    assert status == 200
    status, _ = _request(port, "GET", "/../../config/settings.json")
    assert status == 404


def test_loopback_host_guard(app):
    ctx, port = app
    status, _ = _request(port, "GET", "/api/status", headers={"Host": "evil.example.com"})
    assert status == 403
    status, _ = _request(port, "GET", "/api/status", headers={"Host": f"localhost:{port}"})
    assert status == 200


def test_invalid_json_and_unknown_route(app):
    ctx, port = app
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/api/command", body=b"{oops", headers={"Content-Type": "application/json"})
    assert conn.getresponse().status == 400
    conn.close()
    status, _ = _request(port, "GET", "/api/unknown")
    assert status == 404


def test_sse_stream_sends_snapshot_and_live_events(app):
    ctx, port = app
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/api/events")
    resp = conn.getresponse()
    assert resp.status == 200 and "text/event-stream" in resp.getheader("Content-Type")
    first = resp.fp.readline()
    assert first.startswith(b": connected")
    data_line = b""
    while not data_line.startswith(b"data:"):
        data_line = resp.fp.readline()
    assert json.loads(data_line[5:])["type"] == "status"

    threading.Thread(target=lambda: _request(port, "POST", "/api/command", {"text": "который час"}), daemon=True).start()
    seen = []
    for _ in range(50):
        line = resp.fp.readline()
        if line.startswith(b"data:"):
            seen.append(json.loads(line[5:]))
            if any(e["type"] == "history" for e in seen):
                break
    conn.close()
    assert any(e["type"] == "history" and e["reply"] == "Сейчас 14:05." for e in seen)


def test_commands_overview(app):
    ctx, port = app
    status, data = _request(port, "GET", "/api/commands")
    body = json.loads(data)
    assert body["language"] == "ru"
    assert any(s["name"] == "work_mode" for s in body["scripts"])
    assert any(i["id"] == "time" for i in body["intents"])
