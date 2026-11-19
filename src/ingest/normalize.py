"""Provider payloads -> NormalizedEvent.

Spec: ``docs/spec.md`` (R1-R12). Acceptance surface: ``tests/test_ingest.py``.

Design notes that are not in the spec because they are implementation choices:

* ``call_id`` is derived from ``(session_id, seq)`` and not from the provider's own
  tool-call id, because providers regenerate those ids on re-export. Provider is
  absent from the hash so the same logical turn normalizes identically no matter
  who produced it. See ADR 0001.
* A message carrying several tool calls keeps the first on its own event and parks
  the rest in ``provider_ext["extra_calls"]``. One event per logical message (R2)
  wins over one event per call; v2 can split them if that stops being true.
* A truncated argument payload is data, not an exception. ``json.loads`` cannot
  distinguish "cut mid-flight" from "genuinely malformed", so :func:`_looks_truncated`
  makes that judgement and the two get different ``parse_status`` values.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .canonical import canonical_json

__all__ = ["call_id", "session_id", "ingest", "ingest_openai", "ingest_anthropic"]

SCHEMA_VERSION = 1

# Partial tokens that can only exist at the tail of an interrupted stream.
_PARTIAL_LITERALS = {"t", "tr", "tru", "f", "fa", "fal", "fals", "n", "nu", "nul"}

# "\u12" at the very end: a unicode escape that never got its four digits.
_HEX_ESCAPE_TAIL = re.compile(r"\\u[0-9a-fA-F]{0,3}$")

# A number that ends where it cannot legitimately end.
_PARTIAL_NUMBER_TAIL = re.compile(r"^-?$|^-?\d+\.$|^-?\d+[eE][+-]?$|^-?\.$")


# ---------------------------------------------------------------------------
# identifiers
# ---------------------------------------------------------------------------


def session_id(first_user_text: str) -> str:
    """R9: identity comes from content, not from a provider-assigned id."""
    digest = hashlib.sha256(first_user_text.encode("utf-8")).hexdigest()
    return f"s_{digest[:12]}"


def call_id(session: str, index: int) -> str:
    """R10: deterministic; provider is deliberately not part of the hash."""
    digest = hashlib.sha256(f"{session}:{index}".encode("utf-8")).hexdigest()
    return f"c_{digest[:16]}"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _text_parts(value: Any) -> list[dict[str, Any]]:
    """Coerce a provider content field into a list of ContentPart (R6)."""
    if value is None:
        return []
    if isinstance(value, str):
        return [{"type": "text", "text": value}] if value else []
    parts: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                parts.append({"type": "text", "text": item})
            elif isinstance(item, dict):
                kind = item.get("type")
                if kind in ("text", "input_text", "output_text"):
                    parts.append({"type": "text", "text": item.get("text", "")})
                elif kind in ("image_url", "image"):
                    url = item.get("image_url") or item.get("url") or ""
                    if isinstance(url, dict):
                        url = url.get("url", "")
                    parts.append({"type": "image", "url": url})
    return parts


def _first_user_text(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if message.get("role") == "user":
            parts = _text_parts(message.get("content"))
            return "".join(part.get("text", "") for part in parts)
    return ""


def _looks_truncated(raw: str) -> bool:
    """Decide whether a parse failure is a cut stream or genuine corruption.

    Everything checked here can only sit at the *tail* of the payload, which is
    exactly the damage a mid-flight cut produces.
    """
    text = raw.rstrip()
    if not text:
        return True

    if text[-1] in ",:[{":
        return True
    if text.endswith("\\"):
        return True
    if _HEX_ESCAPE_TAIL.search(text):
        return True

    # An odd number of unescaped quotes means a string was never closed.
    quotes = 0
    escaped = False
    for char in text:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            quotes += 1
    if quotes % 2 == 1:
        return True

    tail = re.split(r"[\s{}\[\],:]", text)[-1]
    if tail in _PARTIAL_LITERALS:
        return True
    if _PARTIAL_NUMBER_TAIL.match(tail):
        return True

    return False


def _parse_args(raw: str) -> tuple[dict[str, Any] | None, str, str]:
    """R4: return ``(args, args_raw, parse_status)``.

    On success ``args_raw`` is the *canonical* re-serialization, so one provider's
    whitespace never leaks into a cross-provider comparison. On a cut stream it is
    the original text, byte for byte, because there is nothing to canonicalize.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        status = "incomplete" if _looks_truncated(raw) else "invalid"
        return None, raw, status

    if not isinstance(parsed, dict):
        return None, raw, "invalid"
    return parsed, canonical_json(parsed), "ok"


def _event(
    provider: str,
    session: str,
    seq: int,
    role: str,
    content: list[dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "session_id": session,
        "seq": seq,
        "role": role,
        "content": content,
        "provider_ext": {},
    }
    event.update(extra)
    return event


def _extras(message: dict[str, Any], known: set[str]) -> dict[str, Any]:
    """R12: anything not modelled is parked, never dropped silently."""
    return {key: value for key, value in message.items() if key not in known}


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

_OPENAI_KNOWN = {"role", "content", "tool_calls", "tool_call_id", "name"}


def ingest_openai(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize an OpenAI conversation export."""
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise ValueError("openai payload has no messages array (R1)")

    session = session_id(_first_user_text(messages))
    events: list[dict[str, Any]] = []
    # provider tool-call id -> our deterministic id
    pending: dict[str, str] = {}

    for message in messages:
        role = message.get("role")
        seq = len(events)

        if role in ("system", "user"):
            events.append(
                _event(
                    "openai", session, seq, role,
                    _text_parts(message.get("content")),
                    provider_ext=_extras(message, _OPENAI_KNOWN),
                )
            )
            continue

        if role == "assistant":
            calls = message.get("tool_calls") or []
            call: dict[str, Any] | None = None
            ext = _extras(message, _OPENAI_KNOWN)

            if calls:
                first = calls[0]
                function = first.get("function") or {}
                raw = function.get("arguments", "")
                if not isinstance(raw, str):
                    raw = canonical_json(raw)
                args, args_raw, status = _parse_args(raw)
                our_id = call_id(session, seq)
                if first.get("id"):
                    pending[first["id"]] = our_id
                call = {
                    "call_id": our_id,
                    "name": function.get("name", ""),
                    "args": args,
                    "args_raw": args_raw,
                    "parse_status": status,
                }
                if len(calls) > 1:
                    ext["extra_calls"] = calls[1:]

            event = _event(
                "openai", session, seq, "assistant",
                _text_parts(message.get("content")),
                provider_ext=ext,
            )
            if call is not None:
                event["call"] = call
            events.append(event)
            continue

        if role == "tool":
            our_id = pending.get(message.get("tool_call_id", ""), call_id(session, seq))
            events.append(
                _event(
                    "openai", session, seq, "tool", [],
                    result={
                        "call_id": our_id,
                        "content": _text_parts(message.get("content")),
                        "is_error": bool(message.get("is_error", False)),
                    },
                    provider_ext=_extras(message, _OPENAI_KNOWN),
                )
            )
            continue

        raise ValueError(f"unsupported openai role: {role!r}")

    return events


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

_ANTHROPIC_KNOWN = {"role", "content"}


def ingest_anthropic(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize an Anthropic conversation export.

    Two shapes have to collapse onto the same events as OpenAI: ``tool_use`` lives
    inside assistant content as an object, and ``tool_result`` arrives wrapped in a
    *user* message rather than as its own role (R5).
    """
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise ValueError("anthropic payload has no messages array (R1)")

    session = session_id(_first_user_text(messages))
    events: list[dict[str, Any]] = []
    pending: dict[str, str] = {}

    for message in messages:
        role = message.get("role")
        blocks = message.get("content")
        blocks = blocks if isinstance(blocks, list) else _text_parts(blocks)

        tool_results = [
            block for block in blocks
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        if tool_results:
            prose = [
                block for block in blocks
                if isinstance(block, dict) and block.get("type") in ("text", "input_text")
            ]
            if prose:
                raise ValueError(
                    "user message mixes prose and tool_result; out of scope for v1 (R5)"
                )
            seq = len(events)
            for block in tool_results:
                our_id = pending.get(block.get("tool_use_id", ""), call_id(session, seq))
                events.append(
                    _event(
                        "anthropic", session, len(events), "tool", [],
                        result={
                            "call_id": our_id,
                            "content": _text_parts(block.get("content")),
                            "is_error": bool(block.get("is_error", False)),
                        },
                        provider_ext={},
                    )
                )
            continue

        if role == "user":
            events.append(
                _event(
                    "anthropic", session, len(events), "user",
                    _text_parts(blocks),
                    provider_ext=_extras(message, _ANTHROPIC_KNOWN),
                )
            )
            continue

        if role == "assistant":
            seq = len(events)
            tool_uses = [
                block for block in blocks
                if isinstance(block, dict) and block.get("type") == "tool_use"
            ]
            call: dict[str, Any] | None = None
            ext = _extras(message, _ANTHROPIC_KNOWN)

            if tool_uses:
                first = tool_uses[0]
                raw_input = first.get("input")
                if isinstance(raw_input, str):
                    args, args_raw, status = _parse_args(raw_input)
                elif isinstance(raw_input, dict):
                    args, args_raw, status = raw_input, canonical_json(raw_input), "ok"
                else:
                    args, args_raw, status = None, "", "invalid"

                our_id = call_id(session, seq)
                if first.get("id"):
                    pending[first["id"]] = our_id
                call = {
                    "call_id": our_id,
                    "name": first.get("name", ""),
                    "args": args,
                    "args_raw": args_raw,
                    "parse_status": status,
                }
                if len(tool_uses) > 1:
                    ext["extra_calls"] = tool_uses[1:]

            event = _event(
                "anthropic", session, seq, "assistant",
                _text_parts(
                    [block for block in blocks
                     if not (isinstance(block, dict) and block.get("type") == "tool_use")]
                ),
                provider_ext=ext,
            )
            if call is not None:
                event["call"] = call
            events.append(event)
            continue

        raise ValueError(f"unsupported anthropic role: {role!r}")

    return events


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


def ingest(provider: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Dispatch by provider name. Unknown providers fail loudly, not silently."""
    if provider == "openai":
        return ingest_openai(payload)
    if provider == "anthropic":
        return ingest_anthropic(payload)
    raise ValueError(f"unsupported provider: {provider!r}")
