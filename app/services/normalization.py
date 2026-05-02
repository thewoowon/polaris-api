import re
import unicodedata


_WS_RE = re.compile(r"\s+")


def normalize_text(raw: str) -> str:
    """Cheap deterministic pre-processing before classification / search.

    Intentionally boring: NFKC, collapse whitespace, strip. No stemming or
    language-specific steps yet — classifier-first strategy (blueprint §3, §17)
    leans on the LLM / model for semantics.
    """
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", raw)
    text = _WS_RE.sub(" ", text).strip()
    return text
