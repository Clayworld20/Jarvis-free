# Jarvis-free

A free, open-source, **offline** voice assistant for Windows 10/11 (x64) that works like JARVIS:
say the wake word, give a command, get a spoken answer. It supports **Russian and English**, has a
dark dashboard with live status, a chat, a log, a command list and settings, and it can run your own
automation scripts.

Cleanroom analog of the JARVIS voice assistant. It does not reuse any JARVIS binaries, models or code.

```
 ┌──────────── dashboard (pywebview / browser) ────────────┐
 │ Home · Chat · Log · Commands · Settings                 │
 └────────────▲───────────────────────────┬────────────────┘
        SSE events                   JSON API (127.0.0.1)
 ┌────────────┴───────────────────────────▼────────────────┐
 │ Assistant (state machine)                               │
 │  idle ──wake word──▶ listening ──utterance──▶ processing │
 │   ▲  mic muted while speaking                  │        │
 │   └────────────────────────────── reply (TTS) ◀┘        │
 │ Mic → noise filter → Vosk (wake grammar / full model)   │
 │ Router: text → intent (ru/en, fuzzy) → Actions/Scripts  │
 │ TTS: pyttsx3 (SAPI5 on Windows)                         │
 └─────────────────────────────────────────────────────────┘
```

## Features

| Area | What you get |
|---|---|
| Wake word | "джарвис" / "jarvis" (configurable). Uses a restricted Vosk grammar, so it is cheap and does not fire on background speech. |
| Speech-to-text | [Vosk](https://alphacephei.com/vosk/) small models for Russian and English, fully offline. |
| Noise handling | Per-microphone high-pass filter plus an adaptive noise gate (tracks the noise floor, attenuates hiss, passes speech). Can be disabled. |
| Commands | Time, date, open apps and websites, web search, notes, lock the PC, shut down / restart (with confirmation and cancel), system info, stop, help. |
| Fuzzy matching | Small recognition errors still match ("который чачс" → time). Placeholders capture arguments ("открой {app}"). |
| Scripts | JSON macros in `resources/scripts/` with their own trigger phrases: speak, open, search, wait, note, run. |
| Dashboard | Dotted-sphere home screen (animates while listening and speaking), chat with history, live log, command/script browser, settings form with microphone picker. |
| Config | `config/settings.json`, managed from the Settings page or edited by hand. Validated on load and on save. |
| Install | `START_JARVIS.bat` creates a venv, installs dependencies, downloads models and starts the app. |

Wake word: the choice is Vosk grammar spotting rather than Porcupine, because Porcupine needs an account
access key. Vosk is fully open source and needs no keys.

## Quick start (Windows 10/11 x64)

1. Install **Python 3.10+** from python.org and tick *Add python.exe to PATH*.
2. Double-click **`START_JARVIS.bat`**. The first run:
   - creates `.venv` and installs `requirements.txt`,
   - downloads the Russian and English speech models (~90 MB, one time) into `resources/models/`,
   - opens the dashboard window (WebView2; falls back to your browser).
3. Say **«джарвис»**, wait for «Слушаю», then speak a command, for example *«который час»*.

Console mode (shows the full log): `python -m jarvis` from the project folder, or `START_JARVIS.bat` in a terminal.

### Linux / macOS (best effort)

```sh
./start_jarvis.sh          # installs into .venv and starts; needs PortAudio and eSpeak-ng for audio/TTS
```

### Command-line options

```
python -m jarvis [--language ru|en] [--host ADDR] [--port N]
                 [--no-gui] [--no-window] [--text] [--debug]
```

`--text` runs without a microphone: type commands in the console (useful for testing scripts and phrases).

## Example commands

| Russian | English | Action |
|---|---|---|
| «джарвис, который час» | "jarvis, what time is it" | Time |
| «какое сегодня число» | "what is the date" | Date |
| «открой блокнот» / «открой ютуб» | "open notepad" / "open youtube" | Open an app or site from the apps list |
| «найди в интернете погода» | "search for weather" | Web search |
| «запиши купить молоко» | "take a note buy milk" | Appends to `data/notes.txt` |
| «заблокируй компьютер» | "lock the computer" | Locks Windows |
| «выключи компьютер» → «подтверждаю» / «отмени» | "shut down" → "confirm" / "cancel" | Shutdown after a delay, confirmed first |
| «режим работы» | "work mode" | Runs the `work_mode` script |
| «стоп» | "stop" | Stops speaking, cancels pending actions |
| «что ты умеешь» | "what can you do" | Lists capabilities |

The full list of phrases is on the **Commands** page of the dashboard. Click a phrase to put it in the chat.

## Configuration

Settings are saved to `config/settings.json` (created on first save; defaults are in `jarvis/config.py`).
The most useful keys:

| Key | Meaning |
|---|---|
| `language` | `ru` or `en`. Switches recognition, wake words, and reply language. |
| `wake_words` | Per language list, e.g. `{"ru": ["джарвис", "джервис"], "en": ["jarvis"]}`. |
| `listen_timeout_sec` | How long to wait for the command after the wake word. |
| `audio.input_device` | `null` (system default) or a device index from the Settings page. |
| `audio.noise_filter`, `audio.highpass_hz`, `audio.gate_margin_db` | Noise filter tuning. Raise the gate margin if background noise is transcribed. |
| `tts.enabled`, `tts.rate`, `tts.volume`, `tts.voice` | Speech output. `voice` is a fragment of a voice name, e.g. "Irina". |
| `models` | Folder names of the Vosk models in `resources/models/`. |
| `apps` | Name → program or URL, e.g. `"блокнот": "notepad"`. |
| `allow_any_app` | If true, "открой X" starts any program named X. Off by default. |
| `search_url` | Must contain `{query}`. |
| `confirm_power_actions`, `power_delay_sec` | Shutdown/restart safety. |
| `allow_script_run_steps` | Allows `run` steps in scripts (default true). |
| `ui.host`, `ui.port`, `ui.window` | Dashboard address (keep `127.0.0.1`), port (8765), native window or browser. |

## Writing scripts

Put a `.json` file in `resources/scripts/` (or click *Reload scripts* on the Commands page):

```json
{
  "name": "work_mode",
  "description": "Opens the browser and notes",
  "triggers": {"ru": ["режим работы"], "en": ["work mode"]},
  "steps": [
    {"type": "speak",  "text": "Включаю режим работы."},
    {"type": "open",   "target": "браузер"},
    {"type": "wait",   "seconds": 1},
    {"type": "search", "query": "новости"},
    {"type": "note",   "text": "Начало рабочей сессии"},
    {"type": "run",    "command": ["notepad.exe", "todo.txt"]}
  ]
}
```

Step types: `speak` (text), `open` (app name from `apps`, or a URL), `search` (query), `wait` (0–30 s),
`note` (text), `run` (argument list, **never** a shell string; can be disabled). Invalid scripts are
skipped and listed in the Commands page with the reason. At most 50 steps per script.

## Speech models

`tools/download_models.py` downloads the official Vosk small models:

- `vosk-model-small-ru-0.22` (Russian)
- `vosk-model-small-en-us-0.15` (English)

To use a different model, unzip it into `resources/models/` and set its folder name under `models` in settings.
Wake words must exist in the model's vocabulary to be recognized reliably. If "джарвис" is not
recognized, try a phonetic variant such as "джервис" or "жарвис".

## Project layout

```
START_JARVIS.bat          Windows launcher (venv, deps, models, run)
start_jarvis.sh           Linux/macOS launcher
requirements.txt          runtime dependencies
jarvis/
  __main__.py, main.py    entry point, CLI, window/browser/console modes
  assistant.py            state machine: wake → listen → process → speak
  audio.py                microphone, noise filter, level meter, chime
  stt.py                  Vosk wrapper, wake-word detection
  tts.py                  pyttsx3 speaker thread, voice selection
  nlu.py                  intents, placeholders, fuzzy matching, language packs
  commands.py             router: text → intent → action → reply
  actions.py              system actions (apps, web, lock, power, notes, scripts)
  scripts.py              script validation and step runner
  config.py               settings defaults, merge, validation, JSON storage
  gui_server.py           HTTP API, SSE events, static files
  events.py, logsetup.py  event bus and logging
  web/                    dashboard (index.html, style.css, app.js)
resources/
  intents/ru.json, en.json  phrases, responses, UI messages per language
  scripts/*.json            example automation scripts
  models/                   Vosk models (not committed)
tools/download_models.py  model downloader
tests/                    pytest suite (no microphone or models needed)
```

## Development

```sh
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest
```

The tests run without audio hardware, models or speech synthesis: they use fake microphones,
recognizers and speakers. They cover intent matching, config validation, script validation,
routing and power confirmation, the noise filter, wake-word detection, the assistant state machine,
and the HTTP API.

## Privacy and security

- Recognition and synthesis run locally. Audio never leaves your machine.
- The web dashboard listens on `127.0.0.1` only. When bound to loopback, requests with a non-local
  `Host` header are rejected (DNS-rebinding protection). Static file access is restricted to `jarvis/web/`.
- Programs are started with an argument list and no shell. Unknown program names are refused unless
  `allow_any_app` is enabled. Shutdown and restart require confirmation by default.
- Only the `Host` header is checked. Do not bind to `0.0.0.0` on an untrusted network.

## Limitations

- Command phrases are matched by rules, not by an LLM. Unknown phrases get a polite "I didn't understand".
- Vosk small models are less accurate than large models or Whisper. Use a bigger Vosk model for
  better accuracy at the cost of memory.
- Windows is the primary target. Power actions, lock, and the default app list are Windows-specific.
  Linux and macOS run the core features with some commands unavailable.
- The sandbox where this project was developed could not download the speech models or use a
  real microphone, so the audio path and the Vosk integration have been checked against the Vosk API
  and with fakes, not end-to-end with real speech. Please report recognition issues.

## License

No license file has been added yet. Choose one before publishing the repository.
The dependencies (Vosk, pyttsx3, sounddevice, numpy, pywebview) and the speech models each have their own
licenses; check them on their project pages.
