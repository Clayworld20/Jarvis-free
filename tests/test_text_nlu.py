from jarvis import paths
from jarvis.nlu import IntentMatcher, load_pack
from jarvis.text import normalize, strip_fillers


def test_normalize_yo_punctuation_and_case():
    assert normalize("  Ёлка, ВЫКЛЮЧИ!!  компьютер ") == "елка выключи компьютер"


def test_strip_fillers():
    assert strip_fillers("джарвис который час пожалуйста", ("джарвис", "пожалуйста")) == "который час"


def test_russian_pack_exact_and_placeholder():
    pack = load_pack("ru", paths.INTENTS_DIR)
    m = IntentMatcher(pack.intents, pack.fillers)
    assert m.match("Который час?").intent.id == "time"
    match = m.match("открой Блокнот")
    assert match.intent.action == "open_app" and match.params == {"app": "блокнот"}
    match = m.match("Джарвис, найди в интернете погода в Таллинне")
    assert match.intent.id == "search" and match.params["query"] == "погода в таллинне"


def test_placeholder_needs_a_value():
    pack = load_pack("ru", paths.INTENTS_DIR)
    m = IntentMatcher(pack.intents, pack.fillers)
    assert m.match("открой") is None or m.match("открой").intent.id != "open_app"


def test_fuzzy_match_tolerates_small_errors():
    pack = load_pack("ru", paths.INTENTS_DIR)
    m = IntentMatcher(pack.intents, pack.fillers)
    match = m.match("который чачс")
    assert match is not None and match.intent.id == "time" and match.score < 1.0


def test_unknown_text_returns_none():
    pack = load_pack("en", paths.INTENTS_DIR)
    m = IntentMatcher(pack.intents, pack.fillers)
    assert m.match("blorp frizzle quux") is None
    assert m.match("") is None


def test_english_pack():
    pack = load_pack("en", paths.INTENTS_DIR)
    m = IntentMatcher(pack.intents, pack.fillers)
    assert m.match("Jarvis, what time is it?").intent.id == "time"
    assert m.match("search for cats").params == {"query": "cats"}
    assert m.match("lock the computer").intent.action == "lock"
