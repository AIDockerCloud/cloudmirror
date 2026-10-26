---
pcmp_version: "2.2"
revision: 11
updated: 2026-10-26
---

# 项目当前状态快照 (STATE.md)

- **Last Updated**: 2026-10-26
- **Overall Status**: cloudmirror 已完成 P0 阶段核心整改：S3 模块全链路显式标 DEMO 并移除伪造连接与成功状态、Bitwarden 同步互斥锁（409 Conflict）拦截重复并发、State 文件按 Pair 物理隔离（`bw-sync-state-{pair_slug}.json`）且平滑继承旧基线。自测 12/12、测试套件 33 项全过，PCMP 检查 0 错误 0 警告。现已完成 P0 准备提交推送到远程，并即将推进 P1 实施。

## 已完成 (Completed)
- [已确认] 完成核心同步脚本 `bw_sync.py` 编写，实现条目规范化、SHA-256 哈希判等、自然键配对与“只增不改不删”状态机。
- [已确认] 实现基于 Fake 客户端的内置离线自测套件（12 组用例覆盖相同/新增/冲突/删除/真重名/回收站/只读/同域不同账号/单端完全去重/哈希优先配对/回收站感知墓碑/多URI乱序规范化）。
- [已确认] 编写基于官方 release 固定 SHA-256 二进制的 `Dockerfile` 与持久化目录挂载 `docker-compose.yml`。
- [已确认] 建立 `README.md`，详细说明前置条件、策略、离线测试与上云配置。
- [已确认] [DEC-001] 采纳 PCMP v2.2 Full 档位作为本工程的上下文管理规范，引入双语协议原版。
- [已确认] [DEC-002] 确立“只增不改不删”与双向冲突副本的同步安全策略。
- [已确认] [DEC-003] 确立基于官方 Bitwarden CLI 二进制固定版本直装与环境变量凭据隔离运行模式。
- [已确认] [DEC-004] 确立 S3 与 Bitwarden 同级归集至统一同步控制台与防重名标签持久化架构。
- [已确认] [DEC-005] 确立凭据生命周期跟踪（90天安全周期，绿/黄/红三阶展示）、前端小眼睛防窥探开关机制及密码变更真实性判定防误判机制。
- [已确认] [DEC-006] 确立生产环境与开发测试环境配置物理隔离（`config.prod.json` 与 `config.dev.json`）、自动化测试快照自愈隔离与前端 Profile Switcher 快速环境切换机制。
- [已确认] [DEC-007] 确立域名+账号自然键判定规则、单端完全重复项（域名+账号+密码完全一致）安全清理机制与前端任务执行防重触状态机。
- [已确认] [DEC-008] 确立项目名称+账号独立条目判定、自动填充选项多URI顺序无关规范化、哈希优先1-to-1精确配对与回收站联动感知防复活机制，真实生产库歧义组成功清零。
- [已确认] [DEC-009] 确立 S3 模块全链路显式标 DEMO、Bitwarden 同步互斥锁 (409) 与 State 文件物理隔离机制：
  - S3 种子数据与持久化配置全部打上 `[DEMO]` 标识，状态统一置为 `demo`，连通测试与主备同步返回及前端界面全面注入黄色警示横幅与标记，移除伪造的连通与成功感；
  - 后端 `/api/bitwarden/sync` 引入 `ACTIVE_SYNC_PAIRS` 线程互斥锁，拦截重复并发请求并返回 HTTP 409 Conflict；
  - State 文件按 Pair 物理隔离（`bw-sync-state-{pair_slug}.json`），平滑继承旧基线，杜绝多源轮流同步相互覆盖配对基线。
- [已确认] 编写自动化测试套件（`tests/test_pcmp_index.py`、`tests/test_bw_sync.py`、`tests/test_s3_sync.py`、`tests/test_server.py`），33 项单元测试 100% 通过。
- [已确认] 运行 `python3 bw_sync.py --selftest`，12 组场景离线自测全部通过。
- [已确认] 运行 `python3 scripts/pcmp_index.py --check` 与 `--update`，0 错误 0 警告，派生索引已同步。

## 进行中 (In Progress)
- [P1] 冲突副本重试去重、ThreadingHTTPServer 多线程 Web 容器、调度器审计留痕与周期修正、删除明文密码回退分支。

## 阻塞项 (Blocked)
- 无

## 当前风险与焦点 (Current Risks & Focus)
- **Git 远程推送认证**：环境若缺少预置 GitHub Token 或 SSH 密钥，执行非交互 push 时需明确给出终端命令知会用户。

## 下一步即时动作 (Immediate Next Action)
- 提交 P0 改动并尝试推送到远程仓库，随后启动 P1 阶段任务落地。
