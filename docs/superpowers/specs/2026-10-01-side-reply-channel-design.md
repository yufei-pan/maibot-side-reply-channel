# maibot-side-reply-channel — Design Spec

**Date:** 2026-10-01  
**Status:** Approved (brainstorming), pending written-spec review  
**Plugin directory:** `maibot-side-reply-channel/`  
**Display name:** 恕我直言（Side Reply Channel）  
**Architecture:** Single always-visible `@Tool`, prompt-only gating, direct `ctx.send.text`

## Summary

A MaiBot first-party plugin that gives the Maisaka planner a `side_reply` tool. The tool sends the planner's own
text straight to the current chat via `ctx.send.text`, bypassing the replyer stack entirely. It exists so Mai can
still say something — report an error, give debugging info, briefly pass on what it meant to say — when the normal
`reply` tool fails (replyer down, generation failure, send failure). Every side-channel message carries a fixed
`※ ` prefix so readers can tell it is not a normal reply.

## Problem

The built-in `reply` tool always routes through the Maisaka replyer: replyer model request, expression selection
sub-agent, `maisaka.replyer.*` and `maisaka.reply.before_post_process` hooks, splitter and typo post-processing.
When any of that is broken, `reply` returns a failure result (e.g. `Maisaka 回复生成器当前不可用。`,
`生成可见回复失败。`, `生成可见回复时发生异常。`) and the planner loops again — with no way to tell anyone in the chat
what is going on.

## Goals

- Give the planner one tool that sends verbatim text to the current chat without touching the replyer stack
- Make the tool always visible to the planner (no `tool_search` discovery step while things are broken)
- Instruct the planner, via the tool description, to use it only after `reply` fails
- Mark every side-channel message with a fixed `※ ` prefix
- Record sent messages in planner history and the database, without feeding expression / behavior / jargon learners
- Plugin-only; no Host/SDK source changes

## Non-goals (v1)

- Hard gating (only exposing the tool after a detected `reply` failure)
- Rate limiting, cooldowns, or length limits
- Operator slash command for testing the channel
- `maisaka.planner.before_request` nudges / reminders
- Quoting a target message, mentions, images, emoji
- Mirroring side-channel messages to an admin chat
- Working when the platform adapter / gateway itself is down (out of reach for a plugin)

## Decisions (from brainstorming)

| Topic | Choice |
|---|---|
| Gating | Prompt only; tool always visible, description carries the rule |
| Marker | Fixed, hard-coded `※ ` prefix (U+203B + space); not configurable; never the plugin name |
| Category / footer | None; single `text` parameter |
| History & storage | Sync into planner history under `side_reply_channel` source kind **and** store in DB |
| Length limit | None; send whatever the planner writes |
| Plugin shape | Single `@Tool`; no hooks, no commands |
| Tool name | `side_reply` |

## Reference plugins / Host code

| Source | Patterns reused |
|---|---|
| `maibot-fetch-url-plugin` | `get_components()` override setting `metadata.visibility = "visible"` + `core_tool` |
| `maibot-world-clock` | Repo layout, manifest shape, `config.default.toml`, config normalize pattern, offline tests |
| Host `src/maisaka/builtin_tool/reply.py` | Failure results the planner sees when `reply` breaks |
| Host `src/maisaka/reasoning_engine.py` `_build_action_tool_definitions` | Plugin tools are deferred unless `metadata.visibility == "visible"` |
| Host `src/plugin_runtime/capabilities/core.py` `_cap_send_text` | Accepts `sync_to_maisaka_history`, `maisaka_source_kind`, `storage_message`, `return_details` |
| Host `src/maisaka/runtime.py` `append_sent_message_to_chat_history` | How synced messages enter planner history; `is_self_message` only for `guided_reply` |
| Host `src/maisaka/builtin_tool/send_image.py` | Precedent for a custom `maisaka_source_kind` (`send_image`) |
| Host `src/learners/*` | Learners only read `user` / `guided_reply` / `outbound_send`, so a custom kind is skipped |

---

## Architecture

### Tool contract (planner-facing)

**Name:** `side_reply`

**Visibility:** always visible. `get_components()` finds the `side_reply` component and sets
`metadata["visibility"] = "visible"` and `metadata["core_tool"] = True`, exactly like fetch-url's
`always_visible_for_planner` path (but unconditional).

**Brief description** (shown every planner turn; carries the gating rule):

> 旁路发言：绕过回复生成器，把你写好的文字原样发到当前聊天。仅在 reply 工具失败时使用（如回复生成器不可用、生成失败、发送失败）；正常情况下必须使用 reply。

**Detailed description:**

- 消息会自动加上 `※ ` 前缀，表明这不是正常回复。
- 用途：告知大家回复功能出了问题、报告错误、调试信息，必要时简短转述你本想说的话。
- 不要用它代替 reply 进行日常聊天；reply 成功后也不要用它重复发言。
- 你写的文字会原样发送，不经过表达方式选择、分段、错别字等处理，请直接写最终要发出的话。

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `text` | string | yes | 要发送的正文，无需自己添加 `※` 前缀。 |

**Results returned to the planner** (`{"success": bool, "content": str}`; Host maps `content` to the tool result /
error message):

- Success: `已通过旁路通道发送："<规划器给出的 text（去除首尾空白）>"。这不是正常回复；回复功能恢复后请继续使用 reply。`
  The result echoes the planner's own text only; it does not mention or include the `※ ` prefix.
- Failure: `success: false` with a reason; nothing reaches the chat. Reasons:
  - empty / whitespace-only `text`
  - missing `stream_id` in the invocation
  - platform send reported failure (include Host `error` if present)
  - exception raised by the send RPC (include exception message)

### Data flow

1. Planner calls `side_reply(text=...)`. Host forwards the invocation through `plugin.invoke_tool`, injecting
   `stream_id` / `chat_id` into kwargs. Plugin reads `kwargs["stream_id"]`, falling back to `kwargs["chat_id"]`
   (Host sets both to the same value); neither present → failure result, no send.
2. Plugin normalizes the text: `strip()`; empty → failure result, no send.
3. Plugin builds the outgoing text: if the stripped text already starts with `※`, use it as-is; otherwise prepend
   `※ `.
4. Plugin calls:

   ```python
   await self.ctx.send.text(
       outgoing_text,
       stream_id,
       return_details=True,
       storage_message=True,
       sync_to_maisaka_history=True,
       maisaka_source_kind="side_reply_channel",
   )
   ```

   No `set_reply`, no `typing`.
5. Plugin interprets the result: `sent` true → success; otherwise failure with Host `error` if provided.
6. Plugin logs (zh-CN): stream_id, text length, platform message_id on success; warning with reason on failure;
   `logger.exception`-style traceback on exceptions.

### What is bypassed vs. still traversed

| Bypassed | Still traversed |
|---|---|
| Replyer model request | Host send service (`send_service._send_to_target_with_message`) |
| Expression selection sub-agent | Platform IO / message gateway / adapter (e.g. NapCat) |
| `maisaka.replyer.*` hooks | DB storage of the sent message |
| `maisaka.reply.before_post_process` hook | Maisaka history sync |
| Splitter, Chinese typo post-process | |
| Reply-effect tracking | |

### Error handling

- No retries and no silent fallback: a fallback channel should fail fast and say why.
- Every failure path returns `success: false` with a zh-CN reason so the planner sees it in the next loop.
- Exceptions from the send RPC are caught, logged with traceback, and reported as failure.

---

## Repository layout

```
maibot-side-reply-channel/
  _manifest.json
  plugin.py
  config.default.toml
  README.md            # zh-CN: purpose, when Mai uses it, install, testing
  CHANGELOG.md
  LICENSE              # MIT
  .gitignore           # same as world-clock (config.toml, config.local.toml, caches)
  tests/
    smoke_test.py
    test_side_reply.py
  docs/superpowers/specs/2026-10-01-side-reply-channel-design.md
```

### Manifest

| Field | Value |
|---|---|
| `manifest_version` | `2` |
| `id` | `com.0-hz.side-reply-channel` |
| `version` | `0.1.0` |
| `name` | `恕我直言（Side Reply Channel）` |
| `author` | `{"name": "kes", "url": "https://github.com/yufei-pan"}` |
| `license` | `MIT` |
| `urls.repository` / `homepage` / `documentation` / `issues` | `https://github.com/yufei-pan/maibot-side-reply-channel` (+ README / issues paths) |
| `host_application` | `1.2.0` – `1.99.99` (first Host tag with `send.*` `return_details`) |
| `sdk` | `2.8.0` – `2.99.99` (first SDK release with `return_details`) |
| `dependencies` | `[]` |
| `capabilities` | `["send.text"]` |
| `i18n.default_locale` | `zh-CN` |

### Config

```toml
[plugin]
enabled = true
config_version = "1.0.0"
```

- Declared via a `PluginConfigBase` model with a `plugin` section (`enabled`, `config_version`) and
  `json_schema_extra` labels in zh-CN.
- `CURRENT_CONFIG_VERSION = "1.0.0"` plus a `_normalize_side_reply_config` routine using the SDK helpers
  (`merge_plugin_config_data`, `extract_plugin_config_version`, `validate_plugin_config`) so future schema changes
  have a migration path.
- `config.default.toml` is the shipped template; live `config.toml` is gitignored.

### Plugin code

- One `MaiBotPlugin` subclass with:
  - `side_reply` `@Tool` handler (`async def handle_side_reply(self, text: str = "", **kwargs)`)
  - `get_components()` override marking `side_reply` visible
  - Thin `on_load` / `on_unload` / `on_config_update` with zh-CN log lines
- Module-level `SIDE_REPLY_PREFIX = "※ "` and `SIDE_REPLY_SOURCE_KIND = "side_reply_channel"` constants
- Module-level `create_plugin()` factory

---

## Testing

Offline, no Host required, SDK located via sibling `../maibot-plugin-sdk` (same as world-clock).

`tests/test_side_reply.py` (fake `ctx.send.text` capturing calls):

- Prefix: `"hello"` → sent as `"※ hello"`
- No double prefix: `"※ hello"` and `"※hello"` sent unchanged
- Whitespace is stripped before prefixing
- Empty / whitespace-only text → `success: false`, send not called
- Missing `stream_id` → `success: false`, send not called
- Exact send kwargs: `return_details=True`, `storage_message=True`, `sync_to_maisaka_history=True`,
  `maisaka_source_kind="side_reply_channel"`
- Send returns `{"sent": False, ...}` (with and without `error`) → `success: false` with reason
- Send raises → `success: false` with exception message
- Success content echoes the planner's stripped text without the `※ ` prefix, plus the "继续使用 reply" reminder
- `get_components()` marks `side_reply` with `visibility == "visible"`

`tests/smoke_test.py`:

- `_manifest.json` parses and has required fields / version ranges
- `create_plugin()` builds the plugin; required lifecycle methods exist
- Default config validates

Commands (inside the plugin dir):

```bash
PYTHONPATH=../maibot-plugin-sdk python tests/smoke_test.py
PYTHONPATH=.:../maibot-plugin-sdk pytest -v
```

## Verify during implementation

- **Planner rendering of the custom source kind:** synced messages with a non-`guided_reply` kind are not flagged
  `is_self_message`; confirm in a live chat that the planner sees them under the bot's nickname (same as
  `send_image`) and does not treat them as someone else speaking.
- **CLI platform:** built-in `reply` special-cases the CLI platform (`render_cli_message`). Check whether
  `send.text` works for CLI chats; if not, document CLI as unsupported in the README.
- **SDK result shape:** confirm the SDK returns the full `{"success", "sent", "message_id", "error"}` dict for
  `return_details=True` (multi-field result, so not unwrapped) and handle it accordingly.
- **Capability declaration:** confirm whether Host enforces `capabilities` in the manifest; keep `send.text`
  declared either way.

## Deployment

After tests pass, copy the plugin into the live instance's plugin directory under `/mnt/klein/mein`. Do **not**
restart the Host; the user restarts when there is no activity.
