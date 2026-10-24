import pytest
from llm_gateway import ReplyNotJsonError, parse_json_reply


def test_parse_json_reply_accepts_a_complete_json_value():
    """A reply that is already valid JSON is returned as its decoded value."""
    assert parse_json_reply('{"skills": []}') == {"skills": []}


def test_parse_json_reply_prefers_a_fenced_json_value_over_surrounding_examples():
    """A JSON code block is selected before JSON-looking examples in prose."""
    reply = 'Example: {"example": true}\n```json\n{"answer": 42}\n```'
    assert parse_json_reply(reply) == {"answer": 42}


def test_parse_json_reply_scans_each_balanced_value_until_one_parses():
    """An invalid balanced candidate does not hide a later valid JSON value."""
    assert parse_json_reply('Reasoning {not JSON}; answer: {"answer": 42}') == {"answer": 42}


def test_parse_json_reply_accepts_arrays_and_non_object_values():
    """The helper returns parsed JSON without imposing the caller's expected shape."""
    assert parse_json_reply("The answer is [1, 2, 3].") == [1, 2, 3]
    assert parse_json_reply('"not an object"') == "not an object"


def test_parse_json_reply_handles_braces_inside_strings():
    """Balanced-value scanning ignores braces and escaped quotes inside JSON strings."""
    reply = 'Result: {"text": "brace } and quote \\" here", "ok": true}'
    assert parse_json_reply(reply) == {"text": 'brace } and quote " here', "ok": True}


def test_parse_json_reply_raises_a_safe_error_when_no_candidate_parses():
    """Unusable or truncated JSON raises a named error without repeating model text."""
    private_text = "PRIVATE-ANSWER-123"
    with pytest.raises(ReplyNotJsonError) as caught:
        parse_json_reply(f'{private_text}: {{"incomplete":')
    assert private_text not in str(caught.value)
