"""The acceptance surface.

Three tests are green today and must stay green: they pin the invariants of the
canonical layer, which is the part that has already been decided.

Three tests are red on purpose. They are the definition of done for the ingest
layer, not bugs:

    test_openai_tool_call_arguments_become_object
    test_truncated_stream_marks_incomplete_instead_of_raising
    test_providers_converge_on_one_shape

``make accept`` runs exactly this file. If you find yourself editing a test to make
it pass, you have found the wrong fix.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.canonical import canonical_json, record_hash
from ingest.normalize import call_id, ingest, session_id

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load(relative: str) -> dict:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Green: invariants of the canonical layer
# ---------------------------------------------------------------------------


def test_canonical_json_ignores_key_order() -> None:
    a = {"b": 1, "a": {"y": 2, "x": [3, 4]}}
    b = {"a": {"x": [3, 4], "y": 2}, "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert record_hash(a) == record_hash(b)


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(ValueError):
        canonical_json({"value": float("nan")})


def test_identifiers_are_derived_not_random() -> None:
    assert call_id("s_abc123def456", 0) == call_id("s_abc123def456", 0)
    assert call_id("s_abc123def456", 0) != call_id("s_abc123def456", 1)
    assert session_id("hello") == session_id("hello")
    assert session_id("hello") != session_id("hello ")


# ---------------------------------------------------------------------------
# Red: the work
# ---------------------------------------------------------------------------


def test_openai_tool_call_arguments_become_object() -> None:
    events = ingest("openai", load("openai/chat_tool_call.json"))
    call = next(event["call"] for event in events if "call" in event)

    assert call["parse_status"] == "ok"
    assert call["args"] == {"path": "src/ingest/canonical.py", "revision": "HEAD"}
    assert json.loads(call["args_raw"]) == call["args"]


def test_truncated_stream_marks_incomplete_instead_of_raising() -> None:
    events = ingest("openai", load("openai/stream_truncated.json"))
    call = next(event["call"] for event in events if "call" in event)

    assert call["parse_status"] == "incomplete"
    assert call["args"] is None
    assert call["args_raw"].startswith('{"path"')


def test_providers_converge_on_one_shape() -> None:
    openai_events = ingest("openai", load("openai/chat_tool_call.json"))
    anthropic_events = ingest("anthropic", load("anthropic/messages_tool_use.json"))

    def strip(events: list[dict]) -> list[dict]:
        return [
            {key: value for key, value in event.items() if key != "provider"}
            for event in events
        ]

    assert strip(openai_events) == strip(anthropic_events)
