"""Download the Vosk speech models used by JARVIS-free into resources/models.

    python tools/download_models.py            # ru + en (small models, ~90 MB total)
    python tools/download_models.py --lang ru  # only Russian
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis import config, paths  # noqa: E402

# Official Vosk model archives (https://alphacephei.com/vosk/models).
MODEL_URLS = {
    "ru": "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
    "en": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
}


def _progress(block: int, block_size: int, total: int) -> None:
    if total > 0:
        done = min(100, block * block_size * 100 // total)
        print(f"\r  {done:3d}%", end="", flush=True)


def download(lang: str, url: str, force: bool = False) -> Path:
    settings = config.load()
    folder = paths.MODELS_DIR / settings["models"][lang]
    if folder.is_dir() and not force:
        print(f"[{lang}] уже установлена: {folder.name}")
        return folder
    paths.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[{lang}] скачивание {url}")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "model.zip"
        urllib.request.urlretrieve(url, archive, reporthook=_progress)  # noqa: S310 - fixed https URL
        print()
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(Path(tmp) / "extract")
        extracted = [p for p in (Path(tmp) / "extract").iterdir() if p.is_dir()]
        if not extracted:
            raise RuntimeError("архив модели пуст")
        if folder.exists():
            shutil.rmtree(folder)
        shutil.move(str(extracted[0]), str(folder))
    print(f"[{lang}] готово: {folder}")
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", choices=sorted(MODEL_URLS), action="append", help="язык (можно несколько раз)")
    parser.add_argument("--force", action="store_true", help="переустановить даже если папка есть")
    args = parser.parse_args()
    langs = args.lang or sorted(MODEL_URLS)
    failures = 0
    for lang in langs:
        try:
            download(lang, MODEL_URLS[lang], args.force)
        except Exception as exc:  # network errors, bad archive...
            failures += 1
            print(f"[{lang}] ошибка: {exc}\n"
                  f"  Скачайте модель вручную с https://alphacephei.com/vosk/models, распакуйте в {paths.MODELS_DIR}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
