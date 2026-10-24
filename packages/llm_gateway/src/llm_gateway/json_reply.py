"""Read JSON values from replies that may include fences or explanatory prose."""

import json
import re
from typing import Any

FENCED_BLOCK = re.compile(r"```[^\r\n`]*\r?\n(.*?)```", re.DOTALL)
OPEN_TO_CLOSE = {"{": "}", "[": "]"}
CLOSE_TO_OPEN = {closing: opening for opening, closing in OPEN_TO_CLOSE.items()}
INVALID_JSON = object()


class ReplyNotJsonError(ValueError):
    """A model reply did not contain a usable JSON value."""


def _balanced_values(text: str) -> list[tuple[int, str]]:
    """Return balanced object and array candidates, ordered by their starting positions."""

    openings: list[tuple[str, int]] = []
    candidates: list[tuple[int, str]] = []
    in_string = False
    escaped = False

    for index, character in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character in OPEN_TO_CLOSE:
            openings.append((character, index))
        elif character in CLOSE_TO_OPEN:
            if not openings or openings[-1][0] != CLOSE_TO_OPEN[character]:
                openings.clear()
                continue
            _, start = openings.pop()
            candidates.append((start, text[start : index + 1]))

    return sorted(candidates, key=lambda candidate: candidate[0])


def _parse_first_candidate(text: str) -> Any:
    """Parse the first complete candidate in text or return a private sentinel."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        pass

    for _, candidate in _balanced_values(text):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, RecursionError):
            continue
    return INVALID_JSON


def parse_json_reply(text: str) -> Any:
    """Return the first JSON value in a reply, without imposing its expected shape.

    The whole reply is tried first, then fenced blocks, then balanced objects and
    arrays in surrounding prose. Parsing failures never repeat any reply text.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        pass

    fenced_ranges: list[tuple[int, int]] = []
    for match in FENCED_BLOCK.finditer(text):
        fenced_ranges.append(match.span())
        parsed = _parse_first_candidate(match.group(1))
        if parsed is not INVALID_JSON:
            return parsed

    surrounding_text = text
    for start, end in reversed(fenced_ranges):
        surrounding_text = surrounding_text[:start] + (" " * (end - start)) + surrounding_text[end:]
    parsed = _parse_first_candidate(surrounding_text)
    if parsed is not INVALID_JSON:
        return parsed
    raise ReplyNotJsonError("The reply did not contain a usable JSON value.")
