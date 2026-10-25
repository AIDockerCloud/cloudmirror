---
pcmp_version: "2.2"
revision: 10
updated: 2026-10-26
---

# 当前唯一活动任务 (TASK.md)

## 当前任务与核心目标 (Current Task & Objective)
- **任务名称**：独立条目判定（项目名称+账号）、多自动填充选项规范化、哈希优先 1-to-1 配对与回收站联动感知防复活机制。
- **核心目标**：
  1. **独立条目判定**：严格遵循用户要求，以项目名称与账号共同构成独立条目标识，相同项目名称不同账号独立存在不冲突；
  2. **自动填充选项 (URIs) 规范化**：多 URI 排序保证数组乱序哈希确定性，去除多余空白，全面支持密码与自动填充多项的稳健对比；
  3. **哈希优先 1-to-1 精确配对**：同名同账号多条目场景下，通过精确哈希 1-to-1 优先建立配对，彻底消除假重名歧义组；
  4. **回收站联动感知与防复活墓碑**：引入 `pull_trash()`，若单端条目在对端回收站中存在相同哈希，精准识别为“在对端已删除”并沉淀墓碑，绝不误报重名，绝不错误复活；全链路条目计数严格排除回收站条目；
  5. **轮询调优与手动刷新**：前端轮询间隔设为 20 秒倒计时，并提供手动立即刷新按钮。

## 背景与范围 (Why & Scope)
- **背景**：此前真实生产库比对时出现 4 组歧义重名假报警（`iforgot.apple.com`、`login.live.com`、`www.qianglie.com`、`xn--2os8j.us.ci`）。经实测核查，前 3 组各 2 条条目的密码与自动填充选项完全一致；而第 4 组在 Vaultwarden 端是被用户主动放进了回收站。旧引擎未感知回收站且多候选直接弃权报歧义，导致用户困惑。
- **范围**：
  - 核心引擎：`bw_sync.py`（`normalize_item_name`、`normalize_item` 多 URI 排序、`natural_key` 重构、`RealBwClient.pull_trash`、`FakeBwClient.pull_trash`、`plan_sync` 哈希优先配对与回收站墓碑感知、自测扩充至 12 组场景）；
  - 后端服务：`server.py`（`count_active_items` 排除回收站与组织条目，更新数据源与连接测试中的条目统计）；
  - 前端界面：`web/app.js`（20 秒倒计时轮询与手动刷新按钮）；
  - 文档与决策：`ai/DECISIONS.md`（DEC-008）、`ai/STATE.md`、`ai/TASK.md`。

## 约束与非目标 (Constraints & Non-Goals)
- **硬约束**：
  - 遵循 STC（Simplified Technical Chinese）规范；
  - 核心安全哲学：“只增不改不删”，单侧删除记入墓碑绝不抹除另一侧，亦绝不违背意愿复活已进回收站的条目；
  - 零外部 pip 依赖（仅依赖 Python 3 标准库）；
  - PCMP v2.2 合规检查 0 错误 0 警告。

## 关联关键文件 (Relevant Files)
- `bw_sync.py`：核心对比算法、自然键、哈希优先配对与回收站感知
- `server.py`：活动条目统计与后台异步执行
- `web/app.js`：前端 20 秒轮询与手动刷新
- `ai/DECISIONS.md`：记录 DEC-008

## 验收结果 (Acceptance Result)
- [x] **独立条目判定与自动填充选项多 URI 规范化**：
  - 项目名称规范化去除空白与小写，与账号组合判定；
  - 登录项 `uris` 数组自动规范化并按字典序排序，杜绝顺序不一致引发的假哈希差异；
- [x] **哈希优先 1-to-1 精确配对**：
  - 面对多重同名条目，优先建立密码与填充选项完全一致的配对；
  - 真实数据实测：`iforgot.apple.com`、`login.live.com`、`www.qianglie.com` 全部 1-to-1 配对成功；
- [x] **回收站联动感知与防复活墓碑**：
  - 对端回收站中的条目被精准识别为单边删除，沉淀墓碑，绝不误复活；
  - 真实数据实测：`xn--2os8j.us.ci` 正确识别为在 Vaultwarden 端已删除并记入墓碑；
  - 真实生产库比对中，**4 组歧义重名彻底清零（0 歧义）**；
- [x] **条目计数全链路排除回收站**：
  - NodeWarden 真实活动条目：326 条（排除 25 条回收站）；
  - Vaultwarden 真实活动条目：325 条（排除 26 条回收站）；
- [x] 运行 `python3 bw_sync.py --selftest`，12 组场景离线自测全部 PASS；
- [x] 运行 `python3 -m unittest discover tests`，31 项单元测试全部 PASS；
- [x] 运行 `python3 scripts/pcmp_index.py --check`，0 错误 0 警告。

## 即时动作 (Immediate Next Action)
- 向人类开发者提交 STC 规范交付回执。

