"""Provider payloads -> NormalizedEvent.

Two of the three public functions are deliberately unimplemented. They are the
acceptance surface: ``tests/test_ingest.py`` states what "done" means, and
``docs/spec.md`` states the rules that get you there. Do not change the tests to
match an implementation; change the implementation to match the tests.

Design note: ``call_id`` is derived from ``(session_id, index)`` and *not* from the
provider's own tool-call id, because providers regenerate those ids when a
conversation is exported again. Identity comes from position inside a session.
Provider is deliberately absent from the hash so that the same logical turn
normalizes identically no matter which provider produced it.
"""

from __future__ import annotations

import hashlib
from typing import Any

__all__ = ["call_id", "session_id", "ingest"]


def session_id(first_user_text: str) -> str:
    """Derive a session id from content, not from a provider-assigned id.

    ``path/to/module.py:31`` R9. Same opening message means same session, which is
    what makes cross-provider convergence in the tests possible at all.
    """
    digest = hashlib.sha256(first_user_text.encode("utf-8")).hexdigest()
    return f"s_{digest[:12]}"


def call_id(session: str, index: int) -> str:
    """Deterministic tool-call id: ``c_`` plus the first 16 hex chars of a SHA-256."""
    digest = hashlib.sha256(f"{session}:{index}".encode("utf-8")).hexdigest()
    return f"c_{digest[:16]}"


def ingest_openai(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize an OpenAI conversation export.

    Not implemented yet. Expected to satisfy
    ``test_openai_tool_call_arguments_become_object`` and
    ``test_truncated_stream_marks_incomplete_instead_of_raising``.
    """
    raise NotImplementedError(
        "R1-R5 in docs/spec.md; see tests/test_ingest.py for the acceptance shape"
    )


def ingest_anthropic(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize an Anthropic conversation export.

    Not implemented yet. Expected to satisfy
    ``test_providers_converge_on_one_shape`` against the OpenAI fixture.
    """
    raise NotImplementedError(
        "R1-R5 in docs/spec.md; see tests/test_ingest.py for the acceptance shape"
    )


def ingest(provider: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Dispatch by provider name. Unknown providers fail loudly, not silently."""
    if provider == "openai":
        return ingest_openai(payload)
    if provider == "anthropic":
        return ingest_anthropic(payload)
    raise ValueError(f"unsupported provider: {provider!r}")
