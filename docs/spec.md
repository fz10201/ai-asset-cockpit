# Normalization contract v1

This document, plus `schema/event.schema.json`, is the whole specification. If an
implementation disagrees with a rule here, the implementation is wrong.

## R1 — Input

Both ingesters accept a conversation-shaped object with a top-level `messages`
array. Real exports are messier; this repo trims them to the fields we consume and
keeps the real field names and nesting. See `fixtures/README.md`.

## R2 — Output

A list of `NormalizedEvent`, ordered by `seq`, starting at `0`, one per logical
message, with no gaps.

## R3 — Event shape

Exactly these keys, no others:

```
schema_version  int, constant 1
provider        "openai" | "anthropic"
session_id      "s_" + 12 hex chars
seq             int >= 0
role            "system" | "user" | "assistant" | "tool"
content         list of ContentPart; MUST be [] when role is "tool"
call            optional ToolCall; only when role is "assistant"
result          optional ToolResult; only when role is "tool"
provider_ext    object, always present, {} when there is nothing to park
```

## R4 — `args_raw`

`args_raw` is the argument payload **as text**, and it is canonicalized when it can be:

1. Provider sent a JSON string that parses (OpenAI `function.arguments`): parse it,
   then re-serialize with `canonical_json`. Re-serializing is deliberate; otherwise
   one provider's whitespace leaks into cross-provider comparisons.
2. Provider sent an object (Anthropic `tool_use.input`): `args_raw = canonical_json(input)`.
3. The string does **not** parse, because a stream was cut mid-flight: keep the
   original text verbatim, set `args = null`, `parse_status = "incomplete"`.

`parse_status` is one of `ok`, `incomplete`, `invalid`. Never raise on a malformed
argument payload; a broken stream is data, not an exception.

## R5 — Tool results

Two provider shapes collapse into one event:

- OpenAI: `{"role": "tool", "tool_call_id": ..., "content": "<string>"}`
- Anthropic: a **user** message whose content parts are `tool_result` blocks

Both become a single `role: "tool"` event with `content: []` and
`result: {call_id, content: [ContentPart], is_error: bool}`. The wrapping user
message in the Anthropic shape does not produce an event of its own. If a user
message mixes prose and a `tool_result`, that is out of scope for v1 and must raise
`ValueError` rather than silently dropping the prose.

## R6 — Content normalization

`content` is always a list. A bare string becomes `[{"type": "text", "text": s}]`.
Text is NFC-normalized, never trimmed: leading and trailing whitespace is
information the user typed.

## R7 — Canonical form

Every string is NFC. Keys are sorted. Separators are `,` and `:`. No trailing
newline. `NaN` and `Infinity` raise instead of serializing. Floats are not coerced
to ints. See `src/ingest/canonical.py`.

## R8 — Comparison

Comparisons are **per record**, on `sha256(canonical_json(record))`. There is no
whole-file diff anywhere in this repo, because one new field would otherwise churn
every fixture and teach nothing.

## R9 — `session_id`

`"s_" + sha256(first_user_text)[:12]`. Identity comes from content, not from a
provider-assigned conversation id: providers regenerate those ids on re-export, and
two exports of the same chat must hash the same.

## R10 — `call_id`

`"c_" + sha256(f"{session_id}:{seq}")[:16]`.

Provider is **not** in the hash. That is what lets the same logical turn normalize
identically from OpenAI and Anthropic. The trade-off, accepted knowingly: call ids
are unique within a session, not globally.

## R11 — Timestamps

`created_at` is `null` in v1. Converting provider epochs to ISO-8601 is a separate
decision with its own timezone question, and guessing now would bake a bug into
every fixture.

## R12 — Unmodelled fields

Anything not in R3 goes into `provider_ext` and is excluded from every comparison.
It exists so the raw layer does not have to be consulted for small questions, and
so that a new provider field shows up as drift rather than as a red build.
