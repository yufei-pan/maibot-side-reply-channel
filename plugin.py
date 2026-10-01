"""恕我直言（Side Reply Channel）插件。

为 Maisaka 规划器提供 side_reply 工具：绕过回复生成器，把规划器写好的文字直接发到当前聊天，
用于 reply 工具失败时的故障告知、调试与旁路说明。
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Field, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

CURRENT_CONFIG_VERSION = "1.0.0"
SHIPPED_CONFIG_TEMPLATE_NAME = "config.default.toml"

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
        self.ctx.logger.info("恕我直言已加载：旁路发言工具 %s 已注册", SIDE_REPLY_TOOL_NAME)

    async def on_unload(self) -> None:
        self.ctx.logger.info("恕我直言已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        del config_data
        if scope == CONFIG_RELOAD_SCOPE_SELF:
            self.ctx.logger.info("恕我直言配置已更新: version=%s", version)

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
                # Host 重启时会把库中麦麦发出的消息恢复为 guided_reply（正常回复），故不入库
                storage_message=False,
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


def create_plugin() -> SideReplyChannelPlugin:
    """创建插件实例。"""

    _ensure_shipped_config_present(Path(__file__).resolve().parent)
    return SideReplyChannelPlugin()
