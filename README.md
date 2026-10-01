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
