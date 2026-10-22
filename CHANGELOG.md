# Changelog

本文件记录 maibot-side-reply-channel（恕我直言）的版本变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 变更

- manifest 兼容上限改为实际验证过的范围：宿主 `max_version` 1.99.99 → **1.3.99**，SDK `max_version` 2.99.99 → **2.14.99**（宿主 1.3.8 + SDK 2.12.0 上实际运行，SDK 2.14.0 上测试通过）。插件仓库审核不再接受「永远兼容」式的上限
- SDK 兼容上限 `max_version` 2.14.99 → **2.16.99**：宿主 1.3.14 + SDK 2.16.0 上测试通过（SDK 2.15 / 2.16 只新增能力，无破坏性变更）

## [0.2.0] - 2026-10-02

### 新增

- 旁路发送增加全局冷却，默认 60 秒。冷却未结束时拒绝发送，并把剩余等待秒数返回给规划器。可在 `channel.cooldown_seconds` 调整，设为 `0` 则关闭冷却

## [0.1.0] - 2026-10-01

### 新增

- 首次发布：为 Maisaka 规划器提供常驻的 `side_reply` 旁路发言工具，绕过回复生成器直接发送文字，并以 `※ ` 前缀标记；消息只同步进当前 Maisaka 历史，不写入数据库
