# 0001 — Two layers: raw blobs and normalized events

- **Status:** accepted
- **Date:** 2026-11-20

## Context

Every provider ships a different conversation export, and every one of them changes
shape without warning. A normalizer that only keeps the normalized form loses the
ability to re-normalize after a schema change, and loses every field we did not
think to model. A normalizer that only keeps raw payloads cannot answer a single
question without re-parsing.

## Decision

Two layers, and they never mix.

1. **Raw layer.** Every provider payload is stored byte-for-byte as a
   content-addressed blob, pinned by its SHA-256. Fixtures in this repo are those
   blobs. Nothing rewrites them, ever.
2. **Normalized layer.** A closed event schema (`schema/event.schema.json`),
   produced by `src/ingest`. Anything unmodelled is parked in `provider_ext` and
   excluded from every comparison.

Consequences:

- Re-normalizing after a schema change is free: the raw layer still has everything.
- Normalization is lossy by design, and the loss is visible, because it is exactly
  what `provider_ext` contains.
- Storage grows once per export, not once per schema version.

## Second decision — `call_id` does not include the provider

The first draft derived `call_id` from `hash(provider, session, index)`. That makes
ids stable per provider but makes the same logical turn normalize differently
depending on who produced it, which breaks the one property this layer exists for:
cross-provider comparability.

`call_id` is now `hash(session, seq)` — see R10 of `docs/spec.md`. Provider is still
carried on the event itself, so nothing is lost except global uniqueness of call
ids, which we do not need: a call id is only ever resolved inside its session.

## Rejected alternatives

- **Normalize on read.** Cheap to start, but every reader re-implements the mapping
  and they drift. Divergence between two readers is worse than a slow ingest.
- **Trust provider-assigned ids.** They are regenerated on re-export, so the same
  conversation produces different ids on the second import and every fixture
  comparison fails for no real reason.
- **Diff whole files.** One added field invalidates the corpus. Per-record hashes
  point at the record that actually changed.
