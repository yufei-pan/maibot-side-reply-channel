# 恕我直言（Side Reply Channel）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a MaiBot plugin that gives the Maisaka planner an always-visible `side_reply` tool which sends the planner's own text straight to the current chat (prefixed `※ `), bypassing the replyer stack, for use only when `reply` fails.

**Architecture:** One `plugin.py` with a `MaiBotPlugin` subclass exposing a single `@Tool("side_reply", ..., visibility="visible")`. The handler validates input, adds the hard-coded `※ ` prefix, and calls `self.ctx.send.text(...)` with history sync under source kind `side_reply_channel` and DB storage. Config holds only `[plugin] enabled` / `config_version`, with a migration hook for future schema changes.

**Tech Stack:** Python ≥ 3.10 (tests use `tomllib`, so run them on ≥ 3.11), `maibot-plugin-sdk` (sibling checkout `../maibot-plugin-sdk`), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-01-side-reply-channel-design.md` (same repo). Read it before starting; this plan argues from it.

## Global Constraints

- Repo root: `/mnt/klein/work/maibot-plugins/maibot-side-reply-channel/` (its own git repo, branch `main`). Run every command from there.
- Manifest: `manifest_version` `2`, `id` `com.0-hz.side-reply-channel`, `version` `0.1.0`, `name` `恕我直言（Side Reply Channel）`.
- Version ranges: `host_application` `1.2.0`–`1.99.99`; `sdk` `2.8.0`–`2.99.99`.
- `capabilities` is exactly `["send.text"]` (Host enforces it); `dependencies` is `[]`.
- Tool name `side_reply`; history source kind `side_reply_channel`; prefix `※ ` (U+203B + space), hard-coded, not configurable.
- No planner-facing string (tool description, parameter description, success/failure content) may contain `※`.
- The tool description is the only planner-facing guidance (Host ignores `detailed_description`).
- No length limit on `text`. No quoting, mentions, images, emoji.
- No silent fallback: every failure returns `{"success": False, "content": "旁路发送失败：<reason>"}` and nothing is sent.
- Logs, comments, README, WebUI labels: Simplified Chinese.
- Do not modify `MaiBot/` or `maibot-plugin-sdk/`.
- ruff line length 120.
- Deploy target `/mnt/klein/mein/plugins/com_0-hz_side-reply-channel/`. **Never restart the Host** (`maim-bot-core`, `docker compose restart`, etc.); the user restarts.

## Review Focus

- Planner sends only the marker (`"※"`, `" ※  "`) → treated as empty: failure "text 为空", nothing sent.
- Planner omits `text` or passes `null` → failure "text 为空", nothing sent.
- Host supplies only `chat_id` (no `stream_id`) → still sends to that chat.
- Multi-line text (e.g. a stack trace) → inner newlines preserved; only outer whitespace stripped.
- Planner passes a non-string `text` (e.g. `404`) → coerced with `str()` and sent as `※ 404`.

Each of these has a pinned test in Task 2.

---

## File Structure

| File | Responsibility |
|---|---|
| `_manifest.json` | Static metadata, version ranges, `send.text` capability |
| `config.default.toml` | Shipped config template (copied to `config.toml` on first load) |
| `.gitignore` | Ignore live config, caches |
| `LICENSE` | MIT |
| `plugin.py` | Config model + migration, plugin class, lifecycle, `side_reply` tool, `create_plugin()` |
| `tests/smoke_test.py` | Manifest, template, factory, config normalization (runs as script and under pytest) |
| `tests/test_side_reply.py` | Tool behavior with a fake `ctx.send` |
| `README.md` | zh-CN user docs |
| `CHANGELOG.md` | Release notes |

---

### Task 1: Plugin scaffold, config, lifecycle

**Files:**
- Create: `.gitignore`, `LICENSE`, `_manifest.json`, `config.default.toml`, `plugin.py`
- Test: `tests/smoke_test.py`

**Interfaces:**
- Consumes: SDK `maibot_sdk.MaiBotPlugin`, `PluginConfigBase`, `Field`, `CONFIG_RELOAD_SCOPE_SELF`.
- Produces (module `plugin`):
  - `CURRENT_CONFIG_VERSION: str` = `"1.0.0"`
  - `class SideReplyConfig(PluginConfigBase)` with `plugin: PluginSectionConfig` (`enabled: bool`, `config_version: str`)
  - `class SideReplyChannelPlugin(MaiBotPlugin)` with `normalize_plugin_config(config_data: Mapping[str, Any] | None) -> tuple[dict[str, Any], bool]`, `async on_load()`, `async on_unload()`, `async on_config_update(scope: str, config_data: dict[str, Any], version: str)`
  - `def create_plugin() -> SideReplyChannelPlugin`

- [ ] **Step 1: Write the failing smoke test**

Create `tests/smoke_test.py`:

```python
"""离线冒烟测试：不依赖 MaiBot Host。

运行方式（在插件根目录）：
    PYTHONPATH=../maibot-plugin-sdk python tests/smoke_test.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import tomllib

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))
sys.path.insert(0, str(PLUGIN_DIR.parent / "maibot-plugin-sdk"))

import plugin as side_reply_plugin


def test_manifest() -> None:
    manifest = json.loads((PLUGIN_DIR / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 2
    assert manifest["id"] == "com.0-hz.side-reply-channel"
    assert manifest["version"] == "0.1.0"
    assert manifest["name"] == "恕我直言（Side Reply Channel）"
    assert manifest["host_application"] == {"min_version": "1.2.0", "max_version": "1.99.99"}
    assert manifest["sdk"] == {"min_version": "2.8.0", "max_version": "2.99.99"}
    assert manifest["capabilities"] == ["send.text"]
    assert manifest["dependencies"] == []
    print("ok: manifest")


def test_default_toml_matches_model() -> None:
    data = tomllib.loads((PLUGIN_DIR / "config.default.toml").read_text(encoding="utf-8"))
    assert data == {"plugin": {"enabled": True, "config_version": side_reply_plugin.CURRENT_CONFIG_VERSION}}
    print("ok: config.default.toml")


def test_create_plugin_and_lifecycle() -> None:
    instance = side_reply_plugin.create_plugin()
    assert isinstance(instance, side_reply_plugin.SideReplyChannelPlugin)
    for name in ("on_load", "on_unload", "on_config_update"):
        assert callable(getattr(instance, name))
    print("ok: create_plugin")


def test_config_normalization() -> None:
    instance = side_reply_plugin.SideReplyChannelPlugin()

    normalized, changed = instance.normalize_plugin_config({})
    assert normalized == {"plugin": {"enabled": True, "config_version": "1.0.0"}}
    assert changed is True

    normalized, changed = instance.normalize_plugin_config({"plugin": {"enabled": False, "config_version": "0.0.1"}})
    assert normalized == {"plugin": {"enabled": False, "config_version": "1.0.0"}}
    assert changed is True

    normalized, changed = instance.normalize_plugin_config({"plugin": {"enabled": True, "config_version": "1.0.0"}})
    assert normalized == {"plugin": {"enabled": True, "config_version": "1.0.0"}}
    assert changed is False
    print("ok: config normalization")


if __name__ == "__main__":
    test_manifest()
    test_default_toml_matches_model()
    test_create_plugin_and_lifecycle()
    test_config_normalization()
    print("all smoke tests passed")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONPATH=../maibot-plugin-sdk python3 tests/smoke_test.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'plugin'`.

- [ ] **Step 3: Add the static files**

`.gitignore`:

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.venv/
.pytest_cache/
.ruff_cache/

# 本地配置
config.local.toml

# 运行期配置（由 Host/WebUI 写回；模板见 config.default.toml）
config.toml
```

`LICENSE`: copy the sibling plugin's MIT license verbatim (same copyright holder, `kes`, 2026):

```bash
cp ../maibot-world-clock/LICENSE LICENSE
```

`_manifest.json`:

```json
{
  "manifest_version": 2,
  "id": "com.0-hz.side-reply-channel",
  "version": "0.1.0",
  "name": "恕我直言（Side Reply Channel）",
  "description": "为 Maisaka 规划器提供常驻的 side_reply 旁路发言工具：绕过回复生成器，把规划器写好的文字直接发到当前聊天，并以 ※ 前缀标记。仅供 reply 工具失败时告知故障、报告错误与调试使用。",
  "author": {
    "name": "kes",
    "url": "https://github.com/yufei-pan"
  },
  "license": "MIT",
  "urls": {
    "repository": "https://github.com/yufei-pan/maibot-side-reply-channel",
    "homepage": "https://github.com/yufei-pan/maibot-side-reply-channel",
    "documentation": "https://github.com/yufei-pan/maibot-side-reply-channel/blob/main/README.md",
    "issues": "https://github.com/yufei-pan/maibot-side-reply-channel/issues"
  },
  "host_application": {
    "min_version": "1.2.0",
    "max_version": "1.99.99"
  },
  "sdk": {
    "min_version": "2.8.0",
    "max_version": "2.99.99"
  },
  "dependencies": [],
  "capabilities": [
    "send.text"
  ],
  "i18n": {
    "default_locale": "zh-CN"
  }
}
```

`config.default.toml`:

```toml
# 恕我直言（Side Reply Channel）插件配置
#
# 本插件没有可调参数；关闭后 Host 不会加载插件，规划器也就看不到 side_reply 工具。

[plugin]
# 是否启用插件
enabled = true
# 配置版本
config_version = "1.0.0"
```

- [ ] **Step 4: Write `plugin.py`**

```python
"""恕我直言（Side Reply Channel）插件。

为 Maisaka 规划器提供 side_reply 工具：绕过回复生成器，把规划器写好的文字直接发到当前聊天，
用于 reply 工具失败时的故障告知、调试与旁路说明。
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Field, MaiBotPlugin, PluginConfigBase

CURRENT_CONFIG_VERSION = "1.0.0"
SHIPPED_CONFIG_TEMPLATE_NAME = "config.default.toml"


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(
        default=True,
        description="是否启用插件",
        json_schema_extra={"label": "启用插件", "i18n": {"zh-CN": {"label": "启用插件"}}},
    )
    config_version: str = Field(
        default=CURRENT_CONFIG_VERSION,
        description="配置版本",
        json_schema_extra={"label": "配置版本", "i18n": {"zh-CN": {"label": "配置版本"}}},
    )


class SideReplyConfig(PluginConfigBase):
    """插件根配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)


def _migrate_side_reply_config(config_data: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    """把配置迁移到当前 config_version。

    目前只有 1.0.0，迁移只需对齐版本号；SDK 基类负责补齐默认值与校验，但不会改写版本号。
    """

    migrated = dict(config_data)
    raw_plugin_section = migrated.get("plugin")
    plugin_section = dict(raw_plugin_section) if isinstance(raw_plugin_section, Mapping) else {}
    changed = plugin_section.get("config_version") != CURRENT_CONFIG_VERSION
    plugin_section["config_version"] = CURRENT_CONFIG_VERSION
    migrated["plugin"] = plugin_section
    return migrated, changed


def _ensure_shipped_config_present(plugin_dir: Path) -> bool:
    """若缺少运行期 config.toml，从模板复制。"""

    config_path = plugin_dir / "config.toml"
    template_path = plugin_dir / SHIPPED_CONFIG_TEMPLATE_NAME
    if config_path.exists() or not template_path.exists():
        return False
    shutil.copy2(template_path, config_path)
    return True


class SideReplyChannelPlugin(MaiBotPlugin):
    """恕我直言插件主体。"""

    config_model = SideReplyConfig

    def normalize_plugin_config(self, config_data: Mapping[str, Any] | None) -> tuple[dict[str, Any], bool]:
        migrated, migrated_changed = _migrate_side_reply_config(dict(config_data or {}))
        normalized, sdk_changed = super().normalize_plugin_config(migrated)
        return normalized, migrated_changed or sdk_changed

    async def on_load(self) -> None:
        self.ctx.logger.info("恕我直言已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("恕我直言已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        del config_data
        if scope == CONFIG_RELOAD_SCOPE_SELF:
            self.ctx.logger.info("恕我直言配置已更新: version=%s", version)


def create_plugin() -> SideReplyChannelPlugin:
    """创建插件实例。"""

    _ensure_shipped_config_present(Path(__file__).resolve().parent)
    return SideReplyChannelPlugin()
```

- [ ] **Step 5: Run the smoke test to verify it passes**

Run: `PYTHONPATH=../maibot-plugin-sdk python3 tests/smoke_test.py`
Expected: four `ok:` lines then `all smoke tests passed`.

Run: `PYTHONPATH=.:../maibot-plugin-sdk python3 -m pytest -v`
Expected: 4 passed (pytest collects `smoke_test.py` via the `*_test.py` pattern).

`create_plugin()` copies `config.default.toml` to `config.toml`; that file is gitignored — confirm with `git status --short` that it does not show up.

- [ ] **Step 6: Lint**

Run: `ruff check --line-length 120 . && ruff format --check --line-length 120 .`
Expected: no errors. If `format --check` reports files, run `ruff format --line-length 120 .` and re-run the tests.

- [ ] **Step 7: Commit**

```bash
git add .gitignore LICENSE _manifest.json config.default.toml plugin.py tests/smoke_test.py
git commit -m "feat: scaffold 恕我直言 plugin (manifest, config, lifecycle)"
```

---

### Task 2: `side_reply` tool

**Files:**
- Modify: `plugin.py` (imports, new constants/helpers after `SHIPPED_CONFIG_TEMPLATE_NAME`, new method on `SideReplyChannelPlugin`)
- Test: `tests/test_side_reply.py`

**Interfaces:**
- Consumes: `plugin.SideReplyChannelPlugin` from Task 1; SDK `Tool`, `maibot_sdk.types.ToolParameterInfo`, `ToolParamType`; `MaiBotPlugin._set_context(ctx)` (used by tests to inject a fake context).
- Produces (module `plugin`):
  - `SIDE_REPLY_TOOL_NAME = "side_reply"`
  - `SIDE_REPLY_PREFIX_MARK = "※"`, `SIDE_REPLY_PREFIX = "※ "`
  - `SIDE_REPLY_SOURCE_KIND = "side_reply_channel"`
  - `SIDE_REPLY_DESCRIPTION: str` (exact text below)
  - `def build_outgoing_text(body: str) -> str`
  - `async SideReplyChannelPlugin.handle_side_reply(self, text: Any = "", **kwargs: Any) -> dict[str, Any]` returning `{"success": bool, "content": str}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_side_reply.py`:

```python
"""side_reply 工具单测（离线，不依赖 Host）。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))
sys.path.insert(0, str(PLUGIN_DIR.parent / "maibot-plugin-sdk"))

import plugin as side_reply

STREAM_ID = "stream-abc"
PREFIX_MARK = "※"
CONFIRMED = {"sent": True, "message_id": "platform-1"}


class FakeSend:
    """记录 send.text 调用的假发送能力。"""

    def __init__(self, result: Any, exc: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result
        self.exc = exc

    async def text(self, text: str, stream_id: str, **kwargs: Any) -> Any:
        self.calls.append({"text": text, "stream_id": stream_id, **kwargs})
        if self.exc is not None:
            raise self.exc
        return self.result


class FakeCtx:
    def __init__(self, send: FakeSend) -> None:
        self.send = send
        self.logger = MagicMock()


def make_plugin(send: FakeSend | None = None) -> tuple[side_reply.SideReplyChannelPlugin, FakeSend]:
    fake_send = send if send is not None else FakeSend(CONFIRMED)
    instance = side_reply.SideReplyChannelPlugin()
    instance._set_context(FakeCtx(fake_send))  # type: ignore[arg-type]
    return instance, fake_send


def call(instance: side_reply.SideReplyChannelPlugin, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(instance.handle_side_reply(**kwargs))


def side_reply_component() -> dict[str, Any]:
    components = side_reply.SideReplyChannelPlugin().get_components()
    return next(component for component in components if component["name"] == "side_reply")


def test_prefixes_plain_text() -> None:
    instance, fake_send = make_plugin()
    result = call(instance, text="回复模块挂了", stream_id=STREAM_ID)
    assert result["success"] is True
    assert fake_send.calls[0]["text"] == "※ 回复模块挂了"
    assert fake_send.calls[0]["stream_id"] == STREAM_ID


def test_does_not_double_prefix() -> None:
    for text in ("※ 已有前缀", "※已有前缀", "  ※ 已有前缀  "):
        instance, fake_send = make_plugin()
        call(instance, text=text, stream_id=STREAM_ID)
        assert fake_send.calls[0]["text"] == text.strip()


def test_strips_outer_whitespace_but_keeps_inner_newlines() -> None:
    instance, fake_send = make_plugin()
    call(instance, text="  第一行\n  第二行  \n", stream_id=STREAM_ID)
    assert fake_send.calls[0]["text"] == "※ 第一行\n  第二行"


def test_non_string_text_is_coerced() -> None:
    instance, fake_send = make_plugin()
    call(instance, text=404, stream_id=STREAM_ID)
    assert fake_send.calls[0]["text"] == "※ 404"


def test_send_kwargs_are_exact() -> None:
    instance, fake_send = make_plugin()
    call(instance, text="hi", stream_id=STREAM_ID)
    assert fake_send.calls == [
        {
            "text": "※ hi",
            "stream_id": STREAM_ID,
            "return_details": True,
            "storage_message": True,
            "sync_to_maisaka_history": True,
            "maisaka_source_kind": "side_reply_channel",
        }
    ]


def test_success_content_echoes_text_without_prefix() -> None:
    instance, _ = make_plugin()
    result = call(instance, text="  回复模块挂了 ", stream_id=STREAM_ID)
    assert result == {
        "success": True,
        "content": '已通过旁路通道发送："回复模块挂了"。这不是正常回复；回复功能恢复后请继续使用 reply。',
    }


def test_success_with_missing_message_id() -> None:
    instance, _ = make_plugin(FakeSend({"sent": True, "message_id": None}))
    result = call(instance, text="hi", stream_id=STREAM_ID)
    assert result["success"] is True


def test_empty_text_fails_without_sending() -> None:
    for kwargs in ({"text": ""}, {"text": "   \n "}, {"text": None}, {"text": "※"}, {"text": " ※  "}, {}):
        instance, fake_send = make_plugin()
        result = call(instance, stream_id=STREAM_ID, **kwargs)
        assert result["success"] is False, kwargs
        assert result["content"] == "旁路发送失败：text 为空，没有可发送的内容。"
        assert fake_send.calls == []


def test_missing_stream_id_fails_without_sending() -> None:
    instance, fake_send = make_plugin()
    result = call(instance, text="hi")
    assert result == {"success": False, "content": "旁路发送失败：缺少当前聊天的 stream_id，无法发送。"}
    assert fake_send.calls == []


def test_falls_back_to_chat_id() -> None:
    instance, fake_send = make_plugin()
    result = call(instance, text="hi", chat_id=STREAM_ID)
    assert result["success"] is True
    assert fake_send.calls[0]["stream_id"] == STREAM_ID


def test_unconfirmed_send_fails() -> None:
    for send_result in ({"sent": False, "message_id": None}, {}, False, "ok"):
        instance, _ = make_plugin(FakeSend(send_result))
        result = call(instance, text="hi", stream_id=STREAM_ID)
        assert result == {"success": False, "content": "旁路发送失败：平台未确认发送，消息可能没有发出。"}, send_result


def test_send_exception_fails_with_message() -> None:
    instance, _ = make_plugin(FakeSend(CONFIRMED, exc=RuntimeError("rpc 断开")))
    result = call(instance, text="hi", stream_id=STREAM_ID)
    assert result == {"success": False, "content": "旁路发送失败：发送时发生异常：rpc 断开"}


def test_tool_is_visible_to_planner() -> None:
    component = side_reply_component()
    assert component["type"] == "TOOL"
    assert component["metadata"]["visibility"] == "visible"
    assert component["metadata"]["description"] == side_reply.SIDE_REPLY_DESCRIPTION
    assert "仅在 reply 工具失败时使用" in side_reply.SIDE_REPLY_DESCRIPTION
    assert [parameter["name"] for parameter in component["metadata"]["parameters"]] == ["text"]
    assert component["metadata"]["parameters"][0]["required"] is True


def test_planner_facing_strings_never_mention_prefix() -> None:
    assert PREFIX_MARK not in json.dumps(side_reply_component()["metadata"], ensure_ascii=False)
    outcomes = [
        call(make_plugin()[0], text="hi", stream_id=STREAM_ID),
        call(make_plugin()[0], text="", stream_id=STREAM_ID),
        call(make_plugin()[0], text="hi"),
        call(make_plugin(FakeSend({"sent": False}))[0], text="hi", stream_id=STREAM_ID),
        call(make_plugin(FakeSend(CONFIRMED, exc=RuntimeError("boom")))[0], text="hi", stream_id=STREAM_ID),
    ]
    for outcome in outcomes:
        assert PREFIX_MARK not in outcome["content"], outcome
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=.:../maibot-plugin-sdk python3 -m pytest tests/test_side_reply.py -v`
Expected: FAIL — `AttributeError: 'SideReplyChannelPlugin' object has no attribute 'handle_side_reply'` (and `StopIteration` / missing `SIDE_REPLY_DESCRIPTION` in the component tests).

- [ ] **Step 3: Implement the tool**

In `plugin.py`, replace the SDK import line:

```python
from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Field, MaiBotPlugin, PluginConfigBase
```

with:

```python
from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Field, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType
```

Directly after `SHIPPED_CONFIG_TEMPLATE_NAME = "config.default.toml"`, add:

```python

SIDE_REPLY_TOOL_NAME = "side_reply"
SIDE_REPLY_PREFIX_MARK = "※"
SIDE_REPLY_PREFIX = f"{SIDE_REPLY_PREFIX_MARK} "
SIDE_REPLY_SOURCE_KIND = "side_reply_channel"
SIDE_REPLY_DESCRIPTION = (
    "旁路发言：绕过回复生成器，把你写好的文字原样发到当前聊天。"
    "仅在 reply 工具失败时使用（如回复生成器不可用、生成失败、发送失败）；正常情况下必须使用 reply。"
    "可用于告知大家回复功能出了问题、报告错误、提供调试信息，必要时简短转述你本想说的话；"
    "不要用它代替 reply 日常聊天，reply 成功后也不要用它重复发言。"
    "文字会原样发送，不经过表达方式选择、分段、错别字等处理，请直接写最终要发出的话。"
)
SIDE_REPLY_TEXT_DESCRIPTION = "要发送的正文。"
SIDE_REPLY_SUCCESS_TEMPLATE = '已通过旁路通道发送："{text}"。这不是正常回复；回复功能恢复后请继续使用 reply。'
SIDE_REPLY_FAILURE_PREFIX = "旁路发送失败："


def build_outgoing_text(body: str) -> str:
    """给规划器正文加上旁路标记；正文已以标记开头时保持原样。"""

    if body.startswith(SIDE_REPLY_PREFIX_MARK):
        return body
    return f"{SIDE_REPLY_PREFIX}{body}"


def _failure(reason: str) -> dict[str, Any]:
    return {"success": False, "content": f"{SIDE_REPLY_FAILURE_PREFIX}{reason}"}
```

Add this method to `SideReplyChannelPlugin`, after `on_config_update`:

```python
    @Tool(
        SIDE_REPLY_TOOL_NAME,
        description=SIDE_REPLY_DESCRIPTION,
        parameters=[
            ToolParameterInfo(
                name="text",
                param_type=ToolParamType.STRING,
                description=SIDE_REPLY_TEXT_DESCRIPTION,
                required=True,
            ),
        ],
        visibility="visible",
    )
    async def handle_side_reply(self, text: Any = "", **kwargs: Any) -> dict[str, Any]:
        """把规划器写好的文字加上旁路标记后直接发到当前聊天。"""

        stream_id = str(kwargs.get("stream_id") or kwargs.get("chat_id") or "").strip()
        if not stream_id:
            return _failure("缺少当前聊天的 stream_id，无法发送。")

        body = "" if text is None else str(text).strip()
        if not body.lstrip(SIDE_REPLY_PREFIX_MARK).strip():
            return _failure("text 为空，没有可发送的内容。")

        outgoing_text = build_outgoing_text(body)
        try:
            result = await self.ctx.send.text(
                outgoing_text,
                stream_id,
                return_details=True,
                storage_message=True,
                sync_to_maisaka_history=True,
                maisaka_source_kind=SIDE_REPLY_SOURCE_KIND,
            )
        except Exception as exc:
            self.ctx.logger.exception("旁路发送异常: stream_id=%s", stream_id)
            return _failure(f"发送时发生异常：{exc}")

        if not isinstance(result, Mapping) or not result.get("sent"):
            self.ctx.logger.warning("旁路发送未被平台确认: stream_id=%s result=%r", stream_id, result)
            return _failure("平台未确认发送，消息可能没有发出。")

        self.ctx.logger.info(
            "旁路发送成功: stream_id=%s length=%d message_id=%s",
            stream_id,
            len(outgoing_text),
            result.get("message_id") or "",
        )
        return {"success": True, "content": SIDE_REPLY_SUCCESS_TEMPLATE.format(text=body)}
```

Update `on_load` to name the tool:

```python
    async def on_load(self) -> None:
        self.ctx.logger.info("恕我直言已加载：旁路发言工具 %s 已注册", SIDE_REPLY_TOOL_NAME)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=.:../maibot-plugin-sdk python3 -m pytest -v`
Expected: all tests in `tests/test_side_reply.py` and `tests/smoke_test.py` pass (18 total).

Run: `PYTHONPATH=../maibot-plugin-sdk python3 tests/smoke_test.py`
Expected: `all smoke tests passed`.

- [ ] **Step 5: Lint**

Run: `ruff check --line-length 120 . && ruff format --check --line-length 120 .`
Expected: no errors (format with `ruff format --line-length 120 .` if needed, then re-run tests).

- [ ] **Step 6: Commit**

```bash
git add plugin.py tests/test_side_reply.py
git commit -m "feat: add side_reply tool that bypasses the replyer"
```

---

### Task 3: Docs and deploy (no restart)

**Files:**
- Create: `README.md`, `CHANGELOG.md`
- Deploy: copy repo contents to `/mnt/klein/mein/plugins/com_0-hz_side-reply-channel/`

**Interfaces:**
- Consumes: everything from Tasks 1–2; constants `SIDE_REPLY_TOOL_NAME`, `SIDE_REPLY_SOURCE_KIND` (documented by value).
- Produces: user-facing docs and a deployed copy awaiting a user-initiated restart.

- [ ] **Step 1: Write `README.md`**

````markdown
# 恕我直言（Side Reply Channel）

MaiBot 插件：给 Maisaka 规划器一条**旁路发言**通道。

当正常的 `reply` 工具失败（回复生成器不可用、生成失败、发送失败）时，规划器可以调用 `side_reply`，把自己写好的文字直接发到当前聊天——不经过回复生成器、表达方式选择、回复相关 Hook、分段与错别字处理。

## 怎么认出旁路消息

旁路消息以 `※ ` 开头。这个标记只给知道约定的人看：规划器并不知道前缀的存在，工具描述和工具结果里都不会提到它。

## 什么时候会用

工具描述要求规划器**仅在 reply 失败时**使用，用于：

- 告知大家回复功能出了问题
- 报告错误、提供调试信息
- 必要时简短转述本想说的话

插件不做硬性拦截，完全依靠工具描述约束规划器。

## 行为细节

- 工具常驻规划器工具列表，无需先调用 `tool_search`。
- 文字原样发送，只在开头加 `※ `（已以 `※` 开头时不重复添加），不限长度。
- 发送的消息会写入数据库，并以 `side_reply_channel` 来源同步进 Maisaka 历史；表达方式、行为与黑话学习器不会从中学习。
- 不支持引用回复、@、图片、表情。
- 仍然经过 Host 发送服务与平台适配器：如果适配器（如 NapCat）本身不可用，旁路也发不出去，规划器会收到失败结果。
- 不支持 CLI 聊天（Host 发送服务没有 CLI 通道），在 CLI 中调用会返回失败。

## 安装

将本目录复制到 MaiBot 的 `plugins/` 下（例如 `plugins/com_0-hz_side-reply-channel/`），然后重启 Host。首次加载时会从 `config.default.toml` 生成 `config.toml`。

要求：MaiBot Host ≥ 1.2.0，maibot-plugin-sdk ≥ 2.8.0。

## 配置

| 键 | 默认值 | 说明 |
|---|---|---|
| `plugin.enabled` | `true` | 关闭后 Host 不加载插件，规划器看不到 `side_reply` |
| `plugin.config_version` | `1.0.0` | 配置版本，由插件自动维护 |

## 测试

在插件目录下运行：

```bash
PYTHONPATH=../maibot-plugin-sdk python tests/smoke_test.py
PYTHONPATH=.:../maibot-plugin-sdk pytest -v
```

## 许可

MIT
````

- [ ] **Step 2: Write `CHANGELOG.md`**

```markdown
# Changelog

本文件记录 maibot-side-reply-channel（恕我直言）的版本变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-10-01

### 新增

- 首次发布：为 Maisaka 规划器提供常驻的 `side_reply` 旁路发言工具，绕过回复生成器直接发送文字，并以 `※ ` 前缀标记
```

- [ ] **Step 3: Full test run before deploy**

Run: `PYTHONPATH=.:../maibot-plugin-sdk python3 -m pytest -v && PYTHONPATH=../maibot-plugin-sdk python3 tests/smoke_test.py`
Expected: 18 passed, then `all smoke tests passed`.

- [ ] **Step 4: Commit docs**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: add README and CHANGELOG for 0.1.0"
```

- [ ] **Step 5: Deploy to the live plugin directory (no restart)**

First check the destination is new:

```bash
test -e /mnt/klein/mein/plugins/com_0-hz_side-reply-channel && echo "目标已存在"
```

Expected: no output. If it prints `目标已存在`, stop and ask the user before overwriting anything.

Then copy:

```bash
DEST=/mnt/klein/mein/plugins/com_0-hz_side-reply-channel
mkdir -p "$DEST"
rsync -a --exclude '.git' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.ruff_cache' \
  --exclude 'config.toml' --exclude 'config.local.toml' ./ "$DEST"/
```

Do **not** run `docker compose restart`, `docker restart maim-bot-core`, or anything that bounces the Host.

- [ ] **Step 6: Verify the deployed copy matches the repo**

Run:

```bash
diff -r --exclude .git --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
  --exclude config.toml --exclude config.local.toml . /mnt/klein/mein/plugins/com_0-hz_side-reply-channel
```

Expected: no output. Also confirm `config.toml` is **absent** in the destination (the Host creates it from the template on first load): `test ! -e /mnt/klein/mein/plugins/com_0-hz_side-reply-channel/config.toml && echo ok`.

- [ ] **Step 7: Hand off to the user**

Tell the user the deploy is ready and that **they** restart the Host when the chat is quiet. Give them this post-restart checklist (from the spec's "Verify during implementation"):

1. Load: `docker logs maim-bot-core 2>&1 | grep -E "恕我直言|side-reply-channel"` shows `恕我直言已加载：旁路发言工具 side_reply 已注册` and no load errors.
2. Visibility: in the planner prompt preview / monitor, `side_reply` is in the tool list without a `tool_search` step.
3. Live call: in a test chat, explicitly ask Mai to use `side_reply` for a test message; confirm the chat shows `※ <text>` and the log shows `旁路发送成功`.
4. Rendering: on the next planner turns, the `※ …` message appears in history under the bot's nickname and Mai does not treat it as another person speaking.
5. Imitation: over the following normal replies, Mai's regular `reply` output does not start copying the `※` marker. If it does, raise it before relying on the plugin.
