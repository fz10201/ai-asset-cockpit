# Fixtures

Frozen inputs. Never edited to make a test pass — that is the whole point of
freezing them.

| File | Provider | What it pins |
|---|---|---|
| `openai/chat_tool_call.json` | OpenAI | `function.arguments` arrives as a JSON **string** |
| `openai/stream_truncated.json` | OpenAI | a stream cut mid-argument, must degrade to `incomplete` |
| `anthropic/messages_tool_use.json` | Anthropic | `tool_use.input` arrives as an **object**; `tool_result` arrives inside a user message |

The two non-truncated files describe **the same logical turn**. That is deliberate:
`test_providers_converge_on_one_shape` asserts that both normalize to byte-identical
events once the `provider` field is removed.

## Shape fidelity

These files are trimmed to the fields this repo consumes, but they keep the real
field names and nesting (`tool_calls[].function.arguments`,
`content[].type == "tool_use"`, `content[].type == "tool_result"`). A real export
carries a lot more; that is what `provider_ext` is for.

## Adding a fixture

1. Drop the raw payload in, unmodified.
2. Add a test that names the behaviour it pins.
3. Never regenerate an existing fixture to fix a red test. Fix the code.
