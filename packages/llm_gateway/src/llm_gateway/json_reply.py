"""Read the final JSON value from replies that may include fences or explanatory prose."""

import json
from typing import Any

OPEN_TO_CLOSE = {"{": "}", "[": "]"}
CLOSE_TO_OPEN = {closing: opening for opening, closing in OPEN_TO_CLOSE.items()}
INVALID_JSON = object()


class ReplyNotJsonError(ValueError):
    """A model reply did not contain a usable JSON value."""


def _balanced_values(text: str) -> list[tuple[int, str]]:
    """Return every balanced object and array candidate, ordered by starting position."""

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


def _top_level_values(text: str) -> list[str]:
    """Keep only values not nested inside an earlier value, such as inner objects of the answer."""
    values: list[str] = []
    last_end = -1
    for start, value in _balanced_values(text):
        end = start + len(value) - 1
        if start > last_end:
            values.append(value)
            last_end = end
    return values


def parse_json_reply(text: str) -> Any:
    """Return the last valid JSON value in a reply, without imposing its expected shape.

    The whole reply is tried first. Otherwise the reply is scanned for top-level
    objects and arrays, and the last one that parses is returned: a model usually
    reasons or shows a shape example before it writes the real answer. Nested values
    inside that answer are not treated as separate answers. Parsing failures never
    repeat any reply text.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        pass

    for candidate in reversed(_top_level_values(text)):
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, RecursionError):
            continue
    raise ReplyNotJsonError("The reply did not contain a usable JSON value.")
