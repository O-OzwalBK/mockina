"""Turn a model-written question into the text a person would actually hear."""

import re

LEADING_PREAMBLE = re.compile(
    r"^(?:sure[!,.]?\s*)?(?:here(?:'s| is)\s+(?:a|the)\s+question\s*[:\-]\s*)?",
    re.IGNORECASE,
)
LEADING_LABEL = re.compile(r"^(?:question|q)\s*\d*\s*[:.)-]\s*", re.IGNORECASE)
BOLD_PATTERN = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
ITALIC_PATTERN = re.compile(r"(?<!\*)\*(?=\S)(.+?)(?<=\S)\*(?!\*)")
WRAPPING_QUOTES = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"))


def sanitize_question(text: str) -> str:
    """Remove speakable wrappers while leaving technical symbols in place.

    Wrapping quotes, a leading ``Question 1:``/``Q1:`` label, a short preamble, code
    backticks, emphasis markers, and surrounding whitespace are removed. Symbols such
    as ``C#``, ``*args``, ``**kwargs``, ``items[0]`` and backslashes are content, not
    markdown, and stay.
    """
    cleaned = text.strip()
    for _ in range(2):
        cleaned = LEADING_PREAMBLE.sub("", cleaned, count=1).strip()
        cleaned = LEADING_LABEL.sub("", cleaned, count=1).strip()
    while len(cleaned) >= 2 and (cleaned[0], cleaned[-1]) in WRAPPING_QUOTES:
        cleaned = cleaned[1:-1].strip()
    cleaned = cleaned.replace("`", "")
    cleaned = BOLD_PATTERN.sub(r"\1", cleaned)
    cleaned = ITALIC_PATTERN.sub(r"\1", cleaned)
    return cleaned.strip()
