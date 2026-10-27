---
pcmp_version: "2.2"
revision: 18
updated: 2026-10-27
---

# 项目当前状态快照 (STATE.md)

- **Last Updated**: 2026-10-27
- **Overall Status**: cloudmirror 已圆满完成服务端安全默认策略 (Fail-Secure) 与环境变量绝对优先层级确立（DEC-014）、主密码回显防护与本地明文凭据清除（DEC-013）、Bitwarden 文件夹维度去重判重与自然键隔离、单端重复项全等精细化判重与最早录入原件保留、自动填充选项严谨防误删校验、前端 API Token 拦截与 401 自动弹窗闭环、S3 流式重试与部分失败真实语义修复（DEC-012）。自测 12/12 组全部通过，单元测试扩充至 55 项全部通过，PCMP 合规自检 0 错误 0 警告。

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
- [已确认] 完成单端重复项识别精细化：除名称与收藏状态外全等判定，严格保留最早录入（creationDate 优先、降级 revisionDate）原件，同文件夹下独立判断。前端展示录入时序。
- [已确认] 闭环前端 API Token 鉴权（全局 fetch 拦截自动附加 Bearer Token、401 自动唤起设置弹窗、顶栏 Token 状态指示与持久化存储）；
- [已确认] 确认重复项判重严格比对自动填充选项（URIs 列表及 match 规则确定性排序），不同网站凭据绝不误杀（测试用例覆盖）；
- [已确认] 修复 dedupe clean 与 schedule run 剩余硬编码 duration_s，改为实测耗时；在 ARCHITECTURE.md 与 ISSUES.md 登记 S3 单 PUT 5GB 上限与思源笔记快照一致性已知限制。
- [已确认] 修复凭据环境变量回显泄露风险（DEC-013）：彻底擦除本地配置文件的明文凭据残留；RealBwClient 严格校验环境变量格式，严禁将非法标识或疑似明文密码作为变量名回显；前端表单 placeholder 修正为安全指引并增加提交正则校验；bw_sync 与 server 原生支持 .env 自动加载。
- [已确认] 确立服务端安全默认策略与环境变量绝对优先层级（DEC-014）：
  - `server.py` 默认绑定地址改为 `127.0.0.1`，仅在显式指定时对外监听；
  - 启动未配置 Token 时自动生成强随机 Token 并显著打印，前端支持 `?token=...` 直达免输，消灭未授权访问；
  - 确立 `OS Environment > .env` 绝对优先级，记录 `_INITIAL_OS_ENV_KEYS` 杜绝 .env 逆向覆盖系统环境，基于 `st_mtime` 实现高效安全热重载。
- [已确认] 自动化测试套件扩充至 55 项（`tests/test_pcmp_index.py`、`tests/test_bw_sync.py`、`tests/test_s3_sync.py`、`tests/test_server.py`），100% 通过。
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

