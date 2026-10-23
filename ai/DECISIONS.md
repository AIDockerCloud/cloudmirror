---
pcmp_version: "2.2"
revision: 1
updated: 2026-10-24
---

# 架构与技术决策记录 (DECISIONS.md)

## DEC-001 — 采纳 PCMP v2.2 作为工程上下文管理协议
日期: 2026-10-24 | 状态: Accepted
- 确认来源: 人类开发者明确指令“参考 AIDockerCloud/PCMP 对本项目做个初始化”
- Supersedes: 无
- Superseded-by: 无
- 复审触发条件 (Review Trigger): 当协作模式发生根本性改变或 PCMP 推出重大主版本升级时复审
- 背景 (Context): 在长周期与跨会话的 AI 辅助协同开发中，极易发生上下文爆炸、进度失忆、代码与文档不一致等问题，需要规范化的工程状态跟踪体系。
- 决策 (Decision): 采纳 PCMP v2.2 Full 档位规范，在工程中设立 `ai/` 状态真源，引入零外部依赖的 Python 派生索引与合规检查工具 (`scripts/pcmp_index.py`)。
- 理由 (Reason): 纯 Markdown 权威驱动，对 Git 友好，零外部依赖，派生索引可随意删除重建，具备跨模型和跨 IDE 的极致通用性。
- 备选方案 (Alternatives): 依赖单一系统提示词或专有 IDE 插件。放弃理由：缺乏机器级合规自检与长期演进版本跟踪。
- 影响 (Consequences): 团队与智能体遵循统一的接管与收尾协议，每次任务沉淀审计会话并递增 `revision`。

---

## DEC-002 — 确立“只增不改不删”与双向冲突副本的同步安全策略
日期: 2026-10-24 | 状态: Accepted
- 确认来源: README.md 策略规范与 bw_sync.py 核心设计实现
- Supersedes: 无
- Superseded-by: 无
- 复审触发条件 (Review Trigger): 当需要支持受控的主动双向覆盖或更精细的字段级三向合并算法时复审
- 背景 (Context): 密码保险库属于个人极高价值安全资产。双向同步过程中若采用基于时钟或先后顺序的自动覆盖机制，极易因网络延迟、时钟偏差或并发修改造成有效密码被覆灭；误删自动传播则可能引发全量清空灾难。
- 决策 (Decision): 系统确立“只增不改不删”核心安全铁律：① 两侧均有时仅对比哈希，相同跳过；② 仅一侧有时在对侧新建；③ 两侧均有但内容不同且发生新变动时，两端均不动原件，各自为对方版本新建一条带有日期标识的“冲突副本”（如 `[冲突副本·YYYY-MM-DD]`），交由人工最终裁决；④ 历史配对条目在单侧消失时，仅记录墓碑并在报告中警示，绝不自动抹除另一侧，亦不复活。
- 理由 (Reason): 将数据破坏与误操作传播风险彻底降至零，宁可保留两份交由人工确认，绝不自动冒进删除或覆盖。
- 备选方案 (Alternatives): 基于 Last-Write-Wins (LWW) 的最后修改时间戳自动覆盖。放弃理由：时间戳不可信且无法表达合并语义，存在严重丢失密码数据的风险。
- 影响 (Consequences): 当发生内容冲突时，需要人类在 Bitwarden 客户端中人工核对并删除多余的冲突副本；系统逻辑高度稳健且具备确定性。

---

## DEC-003 — 采用官方 Bitwarden CLI 二进制直装与环境变量凭据隔离运行模式
日期: 2026-10-24 | 状态: Accepted
- 确认来源: Dockerfile 与 bw_sync.py 核心运行设计实现
- Supersedes: 无
- Superseded-by: 无
- 复审触发条件 (Review Trigger): 当 Bitwarden 官方推出专有原生 SDK 或 NodeWarden 协议产生不兼容分歧时复审
- 背景 (Context): 脚本需要通过官方协议与两端自托管服务端通信。若通过 npm 安装 Bitwarden CLI，曾发生过恶意包投毒事件且依赖体积庞大；若两端 CLI 共享默认配置目录，容易产生 session 混淆与登录态冲突；若密码写入配置文件或参数，有泄露风险。
- 决策 (Decision): 容器镜像直接从 GitHub 官方 release 下载固定版本（钉死 2026.10.0）并核对 SHA-256 哈希；脚本通过 `BITWARDENCLI_APPDATA_DIR` 为两端分配独立的配置目录（`bw-node/` 与 `bw-vault/`）；主密码与 API Key 仅经由终端安全输入或环境变量注入，禁止写入配置与持久化文件。
- 理由 (Reason): 保证环境纯净、构建确定可复现并消除 npm 供应链隐患；实现两端登录态与 session 的严格物理隔离；保障凭据生命周期安全。
- 备选方案 (Alternatives): 使用 npm install -g @bitwarden/cli，或在 config.json 中明文配置密码。放弃理由：存在安全漏洞与供应链投毒风险。
- 影响 (Consequences): 容器升级 Bitwarden CLI 时需在 Dockerfile 中显式更新版本号与两端架构哈希；部署需要通过环境变量传递密码。
