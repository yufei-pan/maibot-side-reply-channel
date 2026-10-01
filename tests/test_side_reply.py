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
            "storage_message": False,
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
