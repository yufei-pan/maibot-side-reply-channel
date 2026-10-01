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
