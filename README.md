# AI Asset Cockpit

A local-first dashboard for the prompts, conversations and spend you accumulate
across AI providers — because right now all of it belongs to whichever chat window
you happened to open.

**Status: ingest layer landed.** Both providers normalize to the same events, and the
three acceptance tests that opened this repo are green:

```
$ python -m pytest -q
6 passed
```

They were written before the code, on purpose, and they did not move to meet it. The
commit that added them (`f675e23`) is still in the history — that is the point of
writing them down first.

---

## The problem

A knowledge worker now talks to three or four models a day, and that work evaporates.
Prompts drown in chat history. The same question gets answered five times across five
tools because comparing means copy-pasting by hand. Monthly spend is invisible.
Switching providers means abandoning your own history.

## The design: two layers, and they never mix

1. **Raw layer** — every provider payload stored byte-for-byte as a
   content-addressed blob, pinned by SHA-256. Nothing rewrites it. This is what makes
   re-normalizing after a schema change free.
2. **Normalized layer** — a closed event schema, one shape per logical turn,
   regardless of which provider produced it. Anything unmodelled is parked in
   `provider_ext` and excluded from every comparison.

Byte-stability is a property of the canonical form, not of the parser: sorted keys,
NFC strings, no insignificant whitespace, and a SHA-256 **per record** instead of a
whole-file diff, so one added field cannot churn the corpus.

Full rules: [`docs/spec.md`](docs/spec.md). Why it is built this way:
[`docs/adr/0001-two-layer-model.md`](docs/adr/0001-two-layer-model.md).

## Layout

```
schema/event.schema.json     the closed event shape
docs/spec.md                 normalization contract, R1-R12
docs/adr/                    decisions, with the reasoning
src/ingest/canonical.py      canonical serialization + per-record hash   [works]
src/ingest/normalize.py      provider ingest                             [stubs]
fixtures/                    frozen raw payloads, never edited to pass
tests/test_ingest.py         the acceptance surface
```

## Run it

```bash
python -m pip install -e ".[dev]"
python -m pytest -q          # or: make accept
```

## What the acceptance suite pins

`make accept` is green. Each test names a behaviour, not an implementation:

- `test_canonical_json_ignores_key_order` — key order is never information
- `test_canonical_json_rejects_nan` — a NaN in a fixture is a bug, not a value
- `test_identifiers_are_derived_not_random` — same session, same ids, every run
- `test_openai_tool_call_arguments_become_object` — a JSON **string** of arguments
  becomes an object, with the original text preserved in `args_raw`
- `test_truncated_stream_marks_incomplete_instead_of_raising` — a stream cut
  mid-argument degrades to `parse_status: "incomplete"` instead of throwing
- `test_providers_converge_on_one_shape` — the OpenAI and Anthropic fixtures
  normalize to byte-identical events

## Roadmap

- [x] Canonical serialization and per-record hashing
- [x] Closed event schema + written contract
- [x] OpenAI / Anthropic ingest — truncated streams degrade to `incomplete`, not throw
- [ ] Gemini and DeepSeek exports
- [ ] Encrypted local store with forward + rollback migrations
- [ ] Hybrid BM25 + vector retrieval, recall@10 measured against a labelled set
- [ ] Per-model token accounting against a versioned price table
- [ ] Provider-neutral export

## License

MIT. See [LICENSE](LICENSE).
