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
