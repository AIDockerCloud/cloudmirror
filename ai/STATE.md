---
pcmp_version: "2.2"
revision: 14
updated: 2026-10-27
---

# 项目当前状态快照 (STATE.md)

- **Last Updated**: 2026-10-27
- **Overall Status**: cloudmirror 已圆满完成 Bitwarden 文件夹维度去重判重与自然键隔离、S3 部分失败真实语义修复、大对象流式传输与指数退避重试、思源笔记指针后置与块判定收窄、前端 Dry-Run 只读开关与真实/模拟角标、API Token 服务端鉴权与精确实测计时（DEC-012）。自测 12/12 组、单元测试扩充至 51 项全过，PCMP 合规自检 0 错误 0 警告。

## 已完成 (Completed)
- [已确认] 完成核心同步脚本 `bw_sync.py` 编写，实现条目规范化、SHA-256 哈希判等、自然键配对与“只增不改不删”状态机。
- [已确认] 实现基于 Fake 客户端的内置离线自测套件（12 组用例覆盖相同/新增/冲突/删除/真重名/回收站/只读/同域不同账号/单端完全去重/哈希优先配对/回收站感知墓碑/多URI乱序规范化/冲突副本防增殖）。
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
- [已确认] [DEC-009] 确立 S3 模块全链路显式标 DEMO、Bitwarden 同步互斥锁 (409) 与 State 文件物理隔离机制（P0 已推送到远程）。
- [已确认] [DEC-010] 确立冲突副本重试去重、多线程 Web 容器、调度器审计留痕与密码环境变量严格化（P1 已推送到远程）。
- [已确认] [DEC-011] 确立原生 AWS SigV4 S3 客户端、思源笔记不可变镜像与环境变量凭据注入（P2 全部完成）。
- [已确认] [DEC-012] 确立 Bitwarden 文件夹维度去重与自然键隔离、S3 部分失败真实语义、流式重试与前端 Dry-Run 控制：
  - Bitwarden 去重判重键与自然键纳入 `folder`，消除跨工作/个人文件夹同密码误报重复与错配；`has_existing_conflict_copy` 修正为全 marker 前缀精确匹配；
  - `s3_sync.py:sync_pair` 部分失败返回 `status: "partial"` 且 `success: False`，严禁虚报覆盖备桶对象数目；
  - `RealS3Client.transfer_to` 基于 8MB 内存/临时文件分块流式直传，防 OOM，集成 3 次失败指数退避重试；
  - 思源笔记仅 `data/*.sy` 走大小判定，`latest` 与 `assets/` 等走大小+ETag 复合校验；对象传输先数据块后引用指针；
  - 前端 S3 控制台增加只读预览 (Dry-Run) 复选框并传递 `apply` 参数；任务列表与仪表盘显式渲染 `🟢 真实` 与 `🟡 模拟` 角标；
  - 服务端支持 `CLOUDMIRROR_API_TOKEN` / `--token` 鉴权与指定 host 绑定，记录实测秒级 `duration_s`。
- [已确认] 自动化测试套件扩充至 51 项（`tests/test_pcmp_index.py`、`tests/test_bw_sync.py`、`tests/test_s3_sync.py`、`tests/test_server.py`），100% 通过。
- [已确认] 运行 `python3 bw_sync.py --selftest`，12 组场景离线自测全部通过。
- [已确认] 运行 `python3 scripts/pcmp_index.py --check` 与 `--update`，0 错误 0 警告，派生索引已同步。

## 进行中 (In Progress)
- [代码与测试完成] 待人类开发者核对并提交推送至远程。

## 阻塞项 (Blocked)
- 无

## 当前风险与焦点 (Current Risks & Focus)
- **Git 远程推送认证**：环境需用户交互凭据推送。

## 下一步即时动作 (Immediate Next Action)
- 输出 STC 规范汇报供人类开发者确认。

