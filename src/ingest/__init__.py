"""AI Asset Cockpit — ingest layer.

Public surface lives in :mod:`ingest.normalize`; byte-stability helpers live in
:mod:`ingest.canonical`.
"""

from .canonical import canonical_json, record_hash
from .normalize import call_id, ingest, session_id

__all__ = ["canonical_json", "record_hash", "call_id", "session_id", "ingest"]
__version__ = "0.0.1"
