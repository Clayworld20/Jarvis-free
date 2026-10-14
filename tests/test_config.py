import json

import pytest

from jarvis import config


def test_merge_is_recursive_and_does_not_mutate_base():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    patch = {"a": {"y": 5}}
    merged = config.merge(base, patch)
    assert merged == {"a": {"x": 1, "y": 5}, "b": 3}
    assert base["a"]["y"] == 2


def test_validate_accepts_defaults():
    config.validate(config.DEFAULT_SETTINGS)


@pytest.mark.parametrize(
    "patch",
    [
        {"language": "de"},
        {"audio": {"sample_rate": 12345}},
        {"tts": {"rate": 9999}},
        {"listen_timeout_sec": 0},
        {"wake_words": {"ru": []}},
        {"search_url": "https://example.com"},
        {"apps": {"x": 1}},
    ],
)
def test_validate_rejects_bad_values(patch):
    with pytest.raises(config.SettingsError):
        config.validate(config.merge(config.DEFAULT_SETTINGS, patch))


def test_load_missing_file_returns_defaults(tmp_path):
    assert config.load(tmp_path / "nope.json") == config.DEFAULT_SETTINGS


def test_load_merges_user_file_and_ignores_broken_json(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"language": "en", "tts": {"rate": 220}}), encoding="utf-8")
    loaded = config.load(path)
    assert loaded["language"] == "en" and loaded["tts"]["rate"] == 220 and loaded["tts"]["volume"] == 1.0
    path.write_text("{not json", encoding="utf-8")
    assert config.load(path) == config.DEFAULT_SETTINGS


def test_save_roundtrip_keeps_unicode(tmp_path):
    path = tmp_path / "s.json"
    settings = config.merge(config.DEFAULT_SETTINGS, {"apps": {"блокнот": "notepad"}})
    config.save(settings, path)
    assert "блокнот" in path.read_text(encoding="utf-8")
    assert config.load(path)["apps"]["блокнот"] == "notepad"
