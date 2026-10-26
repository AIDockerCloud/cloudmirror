---
pcmp_version: "2.2"
revision: 11
updated: 2026-10-26
---

# 当前唯一活动任务 (TASK.md)

## 当前任务与核心目标 (Current Task & Objective)
- **任务名称**：P0-P2 阶段化改进落地：P0（S3 DEMO 显式标识、Bitwarden 同步互斥锁 409、State 物理隔离）、P1（冲突副本防膨胀、多线程 Web 容器、调度器审计与周期修复、废弃明文密码）、P2（真实 SigV4 S3 客户端与思源 Mirror）。
- **核心目标**：
  1. **P0 (已完成)**：
     - S3 模块全链路显式标 DEMO，移除虚假成功与连通状态，阻断虚假信心；
     - Bitwarden 同步互斥锁（`ACTIVE_SYNC_PAIRS`）拦截重复并发触发（HTTP 409 Conflict）；
     - State 文件按 Pair 物理隔离（`bw-sync-state-{pair_slug}.json`），平滑继承既有基线。
  2. **P1 (当前推进)**：
     - 冲突副本重试去重（检测目标端是否已有相同 marker 副本，避免失败重试时冲突副本指数膨胀）；
     - `ThreadingHTTPServer` 替换单线程 `HTTPServer` 解除阻塞；
     - 调度器失败留痕（移除 `except: pass`，记录审计日志）并修正 `daily_2am` 为真实的周期；
     - 彻底删除 `password_env` 明文回退分支。
  3. **P2 (后续推进)**：
     - 原生标准库实现真 S3 客户端（AWS SigV4 签名、ListObjectsV2 分页、ETag 与分片上传适配）；
     - 思源笔记单向 Mirror 特殊处理；
     - S3 凭据 env 环境变量化。

## 背景与范围 (Why & Scope)
- **背景**：代码深度审查指出系统成熟度断层：Bitwarden 线是真引擎，S3 线是原型演示壳。人类开发者明确指示：“请完成P0后提交推送到远程再完成P1推送到远程，再做P2”。
- **范围**：
## 关联关键文件 (Relevant Files)
- `s3_sync.py` / `data/s3-sources.json` / `web/index.html` / `web/app.js`（S3 DEMO 标记与警告）
- `server.py`（互斥锁、409 响应、Pair State 隔离、ThreadingHTTPServer、调度器留痕）
- `bw_sync.py`（State 物理隔离解析、冲突副本防膨胀）
- `tests/test_server.py`（互斥锁与隔离测试套件）

## 约束与非目标 (Constraints & Non-Goals)
- **硬约束**：
  - 遵循 STC（Simplified Technical Chinese）规范；
  - 严格分步：完成 P0 -> 提交推送 -> 完成 P1 -> 提交推送 -> 完成 P2；
  - 核心安全哲学：“只增不改不删”，单侧删除记入墓碑绝不抹除另一侧；
  - 零外部 pip 依赖（仅依赖 Python 3 标准库）；
  - PCMP v2.2 合规检查 0 错误 0 警告。

## 验收结果 (Acceptance Result)
- [x] **P0 阶段完成**：
  - [x] S3 种子数据与持久化 JSON 统一打上 `[DEMO]` 标识，状态设为 `demo`，上次同步标记为 `未同步 (DEMO演示)`；
  - [x] S3 差异对比与同步返回注入 `is_demo: True` 与醒目警告日志，阻断虚假信心；
  - [x] 前端导航 Tab 3、S3 页面顶部、主备同步控制面板顶部全面展示 DEMO 原型警示横幅与胶囊；
  - [x] Bitwarden `/api/bitwarden/sync` 并发互斥锁落地，同一配对重复请求返回 HTTP 409 Conflict；
  - [x] State 文件按 Pair 物理隔离（`bw-sync-state-{pair_slug}.json`），自动平滑继承旧 `bw-sync-state.json`；
  - [x] 单元测试扩充至 33 项（新增互斥锁 409 与 State 隔离测试），全部 PASS；
  - [x] 离线自测 12/12 组全部 PASS；
  - [x] PCMP 合规检查通过。

## 即时动作 (Immediate Next Action)
- 提交 P0 改动并尝试推送到远程仓库，随后启动 P1 任务实施。
