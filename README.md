# AI Asset Cockpit

A local-first dashboard for the prompts, conversations and spend you accumulate
across AI providers — because right now all of it belongs to whichever chat window
you happened to open.

**Status: skeleton.** The canonical layer works. The ingest layer does not exist yet,
and that is visible on purpose: three tests are red, and they are the specification
for whoever writes it.

```
$ python -m pytest -q
3 passed, 3 failed
```

A red CI badge here means the acceptance surface is honest, not that the project is
broken.

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

## What "done" means

`make accept` is green. Specifically:

- `test_openai_tool_call_arguments_become_object` — a JSON **string** of arguments
  becomes an object, with the original text preserved in `args_raw`
- `test_truncated_stream_marks_incomplete_instead_of_raising` — a stream cut
  mid-argument degrades to `parse_status: "incomplete"` instead of throwing
- `test_providers_converge_on_one_shape` — the OpenAI and Anthropic fixtures
  normalize to byte-identical events

The three green tests pin invariants that must not move while those are fixed:
canonical form ignores key order, rejects `NaN`, and identifiers are derived rather
than random.

## Roadmap

- [x] Canonical serialization and per-record hashing
- [x] Closed event schema + written contract
- [ ] OpenAI / Anthropic ingest (the three red tests)
- [ ] Gemini and DeepSeek exports
- [ ] Encrypted local store with forward + rollback migrations
- [ ] Hybrid BM25 + vector retrieval, recall@10 measured against a labelled set
- [ ] Per-model token accounting against a versioned price table
- [ ] Provider-neutral export

## License

MIT. See [LICENSE](LICENSE).
