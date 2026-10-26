---
pcmp_version: "2.2"
revision: 16
updated: 2026-10-27
---

# 当前唯一活动任务 (TASK.md)

## 当前任务与核心目标 (Current Task & Objective)
- **任务名称**：Bitwarden 文件夹维度去重隔离、单端重复项除名称外全等精细化判重与最早录入项保留、前端 API Token 闭环、S3 部分失败真实语义修复、大对象流式重试与前端 Dry-Run 控制落地。
- **核心目标**：
  1. **Bitwarden 文件夹维度判重与自然键隔离**：在判重键中加入所属文件夹（`folder`），使不同文件夹下的相同密码视为独立有效凭据不报重复；自然键纳入文件夹消除跨目录错配；修复 `has_existing_conflict_copy` 消除前缀重叠误判；
  2. **单端重复数据检测精细化与时序保留**：重复判定在同文件夹下除名称与收藏外严格比对其余全部内容（账号、密码、URIs、TOTP、备注、自定义字段等），严格保留最早录入（以 creationDate 优先，缺失降级 revisionDate）原件；前端展示录入时序；测试覆盖自动填充选项（URIs 列表及 match 规则）防止跨站点误判；
  3. **前端 API Token 鉴权闭环**：全局 fetch 自动挂载 `Authorization: Bearer <token>`，遇到 401 自动唤起设置弹窗；顶栏增加 Token 配置入口与状态指示；
  4. **S3 部分失败真实语义 (`status: partial`) 与状态保护**：逐对象传输统计 `failed_objects`，仅全成功时 `success: True`；部分失败返回 `status: partial` 且严禁覆盖备桶对象数目与时间；
  5. **大对象流式传输与指数退避重试**：基于 `tempfile.SpooledTemporaryFile(max_size=8MB)` 与分块流式传输直连目标端，防 OOM；集成 3 次失败指数退避重试；
  6. **思源笔记镜像精细化**：仅 `data/*.sy` 走纯大小判定，`latest`、`assets/` 附件与元数据走大小 + ETag 复合校验；待传输对象强制先数据块后关键引用指针；文档记录单 PUT 5GB 上限与快照一致性已知限制；
  7. **前端 Dry-Run 开关与真实/模拟角标**：S3 面板增加只读预览复选框；任务列表与仪表盘显式渲染 `🟢 真实` 与 `🟡 模拟` 角标；
  8. **服务端安全加固与实测耗时**：`server.py` 支持 `CLOUDMIRROR_API_TOKEN` / `--token` 鉴权与指定 host 绑定，清理与计划触发记录实测秒级 `duration_s`。

## 关联关键文件 (Relevant Files)
- `bw_sync.py`（文件夹维度判重、除名称与收藏外全等判定、最早录入保留、自然键隔离）
- `s3_sync.py`（RealS3Client.transfer_to 流式重试、部分失败跟踪、思源指针后置与块判定收窄）
- `server.py`（API Token 鉴权、精确计时 duration_s、实测任务流水审计）
- `web/index.html` / `web/app.js`（API Token 顶栏入口与 401 弹窗、S3 Dry-Run 复选框、真实/模拟角标、去重录入时序呈现与部分失败展示）
- `tests/test_bw_sync.py` / `tests/test_s3_sync.py` / `tests/test_server.py`
- `ai/ARCHITECTURE.md` / `ai/ISSUES.md`（已知限制记录）
- `ai/DECISIONS.md`（DEC-012 架构决策）

## 约束与非目标 (Constraints & Non-Goals)
- 遵循 STC 规范；
- 核心安全哲学：“只增不改不删”，单侧删除记入墓碑绝不抹除另一侧；
- 零外部 pip 依赖（仅依赖 Python 3 标准库）；
- PCMP v2.2 合规检查 0 错误 0 警告。

## 验收结果 (Acceptance Result)
- [x] **Bitwarden 文件夹维度去重与隔离**：
  - [x] `find_duplicates_in_items` 判定键扩充为 `(itype, domain, username, password, folder)`，不同文件夹相同密码不再报重复；
  - [x] `natural_key` 包含 `folder`，同域名同账号在不同文件夹下各自独立配对；
  - [x] `has_existing_conflict_copy` 修正为全 marker 前缀精确匹配，消除 "GitHub" 与 "GitHub 备用" 前缀重叠误杀；
  - [x] `resolve_pair_state_file` 后续配对安全继承全局墓碑，杜绝已裁决冲突与已删除条目复活。
- [x] **单端重复项识别精细化与时序保留**：
  - [x] 基于 `dedupe_content_hash`，在同文件夹内除名称与收藏外严格比对全部载荷内容（账号、密码、URIs、TOTP、备注、自定义字段等）；
  - [x] 自动填充选项（URIs 列表及 match 规则）严格参与判重，不同站点同密码绝不误判；
  - [x] 严格保留最早录入（以 `creationDate` 优先，缺失时降级 `revisionDate`）的原件；
  - [x] 前端展示保留项与待清理副本录入时间，单元测试与 selftest 场景 9 验证通过。
- [x] **S3 同步健壮性与流式重试**：
  - [x] `sync_pair` 引入 `failed_objects` 记录，部分失败返回 `status: partial`、`success: False`，备桶 `objects_count` 绝不虚报覆盖；
  - [x] `RealS3Client.transfer_to` 基于 8MB 内存/临时文件分块直传，集成 3 次失败指数退避重试（0.5s, 1s, 2s）；
  - [x] 思源笔记仅 `data/*.sy` 走大小判定，`assets/` 附件与指针文件必须大小+ETag 一致；`latest` 与元数据强制排在数据块后传输；
  - [x] 在 `ai/ARCHITECTURE.md` 与 `ai/ISSUES.md` 中完整登记 S3 单 PUT 5GB 上限与思源笔记并发写快照混合已知限制。
- [x] **前端交互与安全管理**：
  - [x] S3 控制台增加只读预览 (Dry-Run) 复选框并传递 `apply` 参数；
  - [x] 任务表格与看板显式渲染 `🟢 真实` 与 `🟡 模拟` 角标；
  - [x] 前端全局 fetch 自动挂载 `Authorization: Bearer <token>`，遇到 401 自动唤起 Token 弹窗；
  - [x] 服务端支持 `CLOUDMIRROR_API_TOKEN` / `--token` 鉴权与指定 host 绑定；
  - [x] 调度器、S3 同步任务与去重清理任务记录精确测量的 `duration_s`。
- [x] 单元测试扩充至 53 项且全部 PASS，自测 12/12 组全部 PASS，PCMP 检查 0 错误 0 警告。

## 即时动作 (Immediate Next Action)
- [x] 完成代码实现与全量自动化测试验证；
- [ ] 输出 STC 规范汇报供人类开发者确认。

