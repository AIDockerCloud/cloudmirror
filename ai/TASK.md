---
pcmp_version: "2.2"
revision: 13
updated: 2026-10-26
---

# 当前唯一活动任务 (TASK.md)

## 当前任务与核心目标 (Current Task & Objective)
- **任务名称**：P0-P2 阶段化改进落地：P0（S3 DEMO 显式标识、Bitwarden 同步互斥锁 409、State 物理隔离）、P1（冲突副本防膨胀、多线程 Web 容器、调度器审计与周期修复、废弃明文密码）、P2（真实 SigV4 S3 客户端与思源 Mirror）。
- **核心目标**：
  1. **P0 (已完成并推送到远程)**：
     - S3 模块全链路显式标 DEMO，移除虚假成功与连通状态，阻断虚假信心；
     - Bitwarden 同步互斥锁（`ACTIVE_SYNC_PAIRS`）拦截重复并发触发（HTTP 409 Conflict）；
     - State 文件按 Pair 物理隔离（`bw-sync-state-{pair_slug}.json`），平滑继承既有基线。
  2. **P1 (已完成并推送到远程)**：
     - 冲突副本重试去重（在 `plan_sync` 中检测目标端是否已存在同版本未裁决冲突副本，避免重试时指数膨胀）；
     - `ThreadingHTTPServer` 替换单线程 `HTTPServer` 解除请求排队阻塞；
     - 调度器失败留痕（移除 `except: pass`，记录审计日志）并以 `compute_next_run` 修正 `daily_2am` 为真实的每日凌晨 02:00；
     - 彻底删除 `_password_once` 中回退使用配置明文字符串的旁路分支。
  3. **P2 (已完成待推送)**：
     - 原生标准库实现真 S3 客户端（AWS SigV4 认证、ListObjectsV2 ContinuationToken 分页、GetObject、PutObject、HeadObject）；
     - 思源笔记单向不可变块 Mirror 特殊处理（同大小跳过、零硬删除保留孤立块）；
     - S3 凭据环境变量化（`access_key_env` / `secret_key_env`、`.env.example` 扩展与 Web 交互联动）。

## 背景与范围 (Why & Scope)
- **背景**：代码深度审查指出系统成熟度断层：Bitwarden 线是真引擎，S3 线是原型演示壳。人类开发者明确指示：“请完成P0后提交推送到远程再完成P1推送到远程，再做P2”。
- **范围**：

## 关联关键文件 (Relevant Files)
- `s3_sync.py`（RealS3Client AWS SigV4 认证、ListObjectsV2、思源笔记镜像、环境变量凭据解析）
- `bw_sync.py`（冲突副本重试去重、_password_once 严格环境变量判定）
- `server.py`（ThreadingHTTPServer 多线程、调度器失败审计）
- `web/index.html` / `web/app.js`（S3 环境变量输入配置与状态指示器）
- `.env.example`（S3 环境变量配置模板）
- `tests/test_s3_sync.py`（SigV4、XML解析、Mock HTTP、思源笔记比对单元测试套件）
- `ai/DECISIONS.md`（DEC-011 架构决策）

## 约束与非目标 (Constraints & Non-Goals)
- **硬约束**：
  - 遵循 STC（Simplified Technical Chinese）规范；
  - 严格分步：完成 P0 -> 提交推送 -> 完成 P1 -> 提交推送 -> 完成 P2；
  - 核心安全哲学：“只增不改不删”，单侧删除记入墓碑绝不抹除另一侧；
  - 零外部 pip 依赖（仅依赖 Python 3 标准库）；
  - PCMP v2.2 合规检查 0 错误 0 警告。

## 验收结果 (Acceptance Result)
- [x] **P0 阶段完成并推送到远程**：
  - [x] S3 种子数据与持久化 JSON 统一打上 `[DEMO]` 标识，状态设为 `demo`，上次同步标记为 `未同步 (DEMO演示)`；
  - [x] S3 差异对比与同步返回注入 `is_demo: True` 与醒目警告日志，阻断虚假信心；
  - [x] 前端导航 Tab 3、S3 页面顶部、主备同步控制面板顶部全面展示 DEMO 原型警示横幅与胶囊；
  - [x] Bitwarden `/api/bitwarden/sync` 并发互斥锁落地，同一配对重复请求返回 HTTP 409 Conflict；
  - [x] State 文件按 Pair 物理隔离（`bw-sync-state-{pair_slug}.json`），自动平滑继承旧 `bw-sync-state.json`；
  - [x] 远程已包含 P0 提交 `66ae038`。
- [x] **P1 阶段完成并推送到远程**：
  - [x] 冲突副本重试去重：`plan_sync` 生成冲突副本规划前自动检测目标端是否已有相同账号/密码/内容的冲突副本，即使状态丢失重复运行亦零增殖；
  - [x] Web 容器多线程化：`ThreadingHTTPServer` 替换单线程 `HTTPServer`，慢请求不再阻塞整体 API；
  - [x] 后台调度器异常记录进 `datastore.add_task` 审计流水，移除 `except: pass`；`compute_next_run` 修正 `daily_2am` 为真实的每日凌晨 02:00；
  - [x] 彻底删除 `_password_once` 中将配置字符串回退当明文密码使用的后门；
  - [x] 单元测试扩充至 36 项全部 PASS，自测 12/12 组全部 PASS；
  - [x] 远程已包含 P1 提交 `b5a98e6`。
- [x] **P2 阶段完成**：
  - [x] 原生 Python 3 标准库实现 `RealS3Client`，包含完整的 AWS SigV4 签名计算、`ListObjectsV2` 翻页、`GetObject`、`PutObject`、`HeadObject` 与 XML 错误解析；
  - [x] 思源笔记单向不可变块镜像模式：相同大小哈希块跳过覆写、增量补齐缺失/修改块、备桶单边孤立块安全保留（零硬删除）；
  - [x] S3 凭据环境变量注入：支持 `access_key_env` 与 `secret_key_env`，`.env.example` 扩展模板，前端界面与配置表单无缝联动；
  - [x] 单元测试扩充至 43 项且全部 PASS，自测 12/12 全部 PASS。

## 即时动作 (Immediate Next Action)
- [x] 完成 P2 阶段代码实现与测试；
- [ ] 提交 P2 阶段修改至 Git，生成 STC 任务回执通知人类开发者推送到远程。
