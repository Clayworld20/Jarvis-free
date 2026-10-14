"""Filesystem layout. Everything is relative to the repository root."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESOURCES_DIR = ROOT / "resources"
MODELS_DIR = RESOURCES_DIR / "models"
SCRIPTS_DIR = RESOURCES_DIR / "scripts"
INTENTS_DIR = RESOURCES_DIR / "intents"
WEB_DIR = Path(__file__).resolve().parent / "web"
CONFIG_DIR = ROOT / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, DATA_DIR, LOG_DIR, MODELS_DIR, SCRIPTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
