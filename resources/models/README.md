# Speech models

Vosk models live in this folder. They are **not** committed to Git (they are large).

Run `python tools/download_models.py` (or `START_JARVIS.bat`, which runs it automatically)
to download the default English and Russian small models. You can also unzip any other
Vosk model here and point `models.ru` / `models.en` in `config/settings.json` to its folder name.

Expected layout:

    resources/models/vosk-model-small-ru-0.22/
    resources/models/vosk-model-small-en-us-0.15/
