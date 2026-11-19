"""Canonical serialization.

Byte-stability has exactly one home, and this is it. Anything that will be hashed
or compared goes through :func:`canonical_json` first, so a fixture comparison can
never depend on key order, insignificant whitespace, or Unicode normalization form.

The rules implemented here are R6-R8 of ``docs/spec.md``.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

_SEPARATORS = (",", ":")


def _normalize(value: Any) -> Any:
    """Recursively NFC-normalize every string, including dict keys."""
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {
            unicodedata.normalize("NFC", str(key)): _normalize(val)
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Return the canonical text form of ``value``.

    - keys sorted, so insertion order is irrelevant
    - no insignificant whitespace (``,`` and ``:`` as separators)
    - Unicode preserved, not escaped, after NFC normalization
    - ``NaN`` / ``Infinity`` rejected rather than silently serialized

    Floats are *not* coerced to ints: ``1.0`` and ``1`` are different values and
    collapsing them would throw away information the caller chose to express.
    """
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=_SEPARATORS,
        allow_nan=False,
    )


def record_hash(value: Any) -> str:
    """SHA-256 of the canonical form. One hash per record, never per file."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
