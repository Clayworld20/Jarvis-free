"""Text normalisation shared by the intent matcher and the wake-word detector."""
import re

_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize(text: str) -> str:
    """Lower-case, map «ё» to «е», drop punctuation and collapse whitespace."""
    text = (text or "").lower().replace("ё", "е")
    text = _PUNCT.sub(" ", text)
    return " ".join(text.split())


def strip_fillers(text: str, fillers) -> str:
    """Remove filler words (e.g. the wake word or «пожалуйста») from an already normalised text."""
    if not fillers:
        return text
    return " ".join(w for w in text.split() if w not in fillers)
