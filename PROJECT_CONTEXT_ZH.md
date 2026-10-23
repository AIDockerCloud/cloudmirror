---
pcmp_version: "2.2"
updated: 2026-10-20
---

# 项目上下文管理协议 (PCMP — Project Context Management Protocol)

- **版本**：**2.2** (2026-10-20)
- **文档性质**：本文档为**通用协议原版（模板）**，不包含任何特定项目的业务状态信息。
- **英文对应**：[PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)（中英文内容对齐，若有表述差异以核对后的最新版为准）。
- **生效规则**：若当前工程存在 `ai/PROJECT_CONTEXT_ZH.md`（项目使用版），以使用版为准；否则以根目录本原版为准（见 §3.1）。

---

## 1. 能力边界 (Capability Boundaries)

PCMP 明确**不承诺**以下事项：
1. **不承诺完整保留全部对话过程**：仅记录支持工作恢复、上下文交接和决策追溯所需的必要信息。
2. **不承诺所有 AI 平台自动感知本协议**：文件的自动发现由各个平台/IDE 的配置适配层（如 `.cursorrules`、`AGENTS.md`、`CLAUDE.md` 等）负责。
3. **不承诺 `revision` 提供分布式原子锁**：版本号属于防脏写变更标记，并发安全依赖串行写回或单一合并者机制。

---

## 2. 核心原则 (Core Principles)

1. **当前状态优先，但必读含定义 (Current State First)**  
   AI 接管必读顺序 = **本协议 + `ai/PROJECT.md`（目标与硬约束） + `ai/STATE.md` + `ai/TASK.md`**。严禁仅凭状态摘要推测系统约束，严禁通读全部历史会话反推现状。
2. **冲突分级核实，不设绝对优先 (Tiered Conflict Verification)**  
   代码与测试证明的是“当前物理实现”，但不自动推翻用户原始需求、安全约束或已确立的 ADR 决策。发现代码与文档不一致时：**标记差异 ➔ 核实依据（用户需求/ADR/测试） ➔ 决定修正实现还是更新文档**。
3. **最小有效上下文 (Minimal Effective Context)**  
   仅维护开发决策和推进任务必需的高价值信息；历史会话记录定期压缩摘要，防止上下文膨胀。
4. **AI 与平台无关 (AI- & Platform-Agnostic)**  
   不绑定任何特定模型、IDE、CLI 或云端平台，完全依赖本地文件系统与 Markdown 运作。
5. **信息分层标注 (Information Layering)**  
   所有关键信息显式标注状态：`[事实]` / `[假设]` / `[提议]` / `[已确认]` / `[未决]`。AI 的建议未经人类确认不得记为已决定。
6. **协议与产品代码严格解耦 (Decoupling Protocol from Product Code)**  
   PCMP 仅为指导人机协同的工程管理规范，严禁将其作为业务逻辑或运行时依赖硬编码进产品源码。
7. **Markdown 权威，派生可全量重建 (Markdown as Authority)**  
   一切权威事实与决策均存在于 Markdown 文件中；索引与缓存（如 SQLite）均为可随时删除重建的派生工具。即便删除所有派生产物，人类与 AI 仍能完整接管项目。

---

## 3. 目录结构与职责 (Directory Structure)

```text
项目根目录/
├── PROJECT_CONTEXT.md        # 英文完整通用协议 (原版)
├── PROJECT_CONTEXT_ZH.md     # 中文完整通用协议 (原版)
├── .gitignore                # 忽略项: 须包含 node_modules/ 与 ai/.cache/
└── ai/
    ├── PROJECT.md            # 项目定位、宗旨、核心目标、边界与硬约束 (长期稳定)
    ├── ARCHITECTURE.md       # 系统架构、模块设计、数据流与技术约定 (长期稳定)
    ├── STATE.md              # 项目全局当前状态快照 (动态更新)
    ├── TASK.md               # 当前唯一活动任务与验收指标 (动态更新)
    ├── PLAN.md               # 高阶路线图与里程碑规划 (动态更新)
    ├── DECISIONS.md          # 架构决策记录 (ADR, 长期累积)
    ├── ISSUES.md             # 已知缺陷与技术风险跟踪 (动态更新)
    ├── sessions/             # 结构化会话沉淀记录 (追加模式, 定期压缩)
    ├── proposals/            # 协议改进提案 (追加模式)
    ├── .cache/               # (可选) 派生索引与缓存目录 (git 忽略)
    └── PROJECT_CONTEXT.md / PROJECT_CONTEXT_ZH.md   # (可选) 项目使用版 (存在时优先)
```

> **最小可用集**：根目录下两份原版协议即为最小集。新项目引入协议无需预先建全文件，接管流程遇缺失文件时自动进入初始化流程（§5.1）。所有 `ai/` 路径均相对于**项目根目录**解析。

### 文件职责与性质对照表

| 文件 / 目录 | 核心职责 | 更新性质 | 权威等级 |
| :--- | :--- | :--- | :--- |
| `ai/PROJECT.md` | 项目定位、宗旨、核心目标、Scope、Non-Goals 与硬约束 | 长期稳定 | 强约束 |
| `ai/ARCHITECTURE.md`| 技术栈选型、架构分层、模块依赖、数据流与核心规范 | 长期稳定 | 强指导 |
| `ai/STATE.md` | 当前状态快照：已完成、进行中、阻塞项、风险、Next Action | 动态更新 | 实时基准 |
| `ai/TASK.md` | 当前唯一活动任务：目标、范围、验收标准、即时动作 | 动态更新 | 执行焦点 |
| `ai/PLAN.md` | 当前阶段、里程碑、近期与中远期演进规划 | 动态更新 | 参考指导 |
| `ai/DECISIONS.md` | ADR 决策日志：背景、决策、理由、替代方案、确认来源 | 长期累积 | 权威准则 |
| `ai/ISSUES.md` | 缺陷与风险跟踪：ID、状态、影响、规避方案、关联模块 | 动态更新 | 事实记录 |
| `ai/sessions/` | 结构化会话沉淀 (`SESSION-YYYY-MM-DD-NNN.md`) | 追加归档 | 审计证据 |
| `ai/proposals/` | 协议改进建议与演进草案 | 追加记录 | 提案讨论 |

### 3.1 原版、项目使用版与通用回流

- **协议原版 (Originals)**：根目录 `PROJECT_CONTEXT.md` / `PROJECT_CONTEXT_ZH.md`。为通用中立模板，严禁写入项目专有状态、私有链接或临时编号。
- **项目使用版 (Instance)**：当项目对协议有定制需求时，从原版复制完整副本至 `ai/PROJECT_CONTEXT_ZH.md` 并在其上修改演进。无定制要求的项目直接使用根目录原版。
- **双语对齐**：使用版的中英文规则须保持一致，发现冲突核实后同步修订，严禁隐式单边合并。
- **通用改进回流机制**：使用版演进中若产生具备跨项目通用价值的规则改进，不得直接回写根目录原版；应在根目录生成候选补丁文件：`PROJECT_CONTEXT.optimized-<编号>.md`、`PROJECT_CONTEXT_ZH.optimized-<编号>.md` 与补丁说明 `PCMP-PATCH-<编号>.md`。由人类确认后再统一晋升为新原版。

### 3.2 档位划分：Lite 与 Full (Tiers)

为了避免在小型项目或单人研发中产生“治理通胀 (Governance Inflation)”，PCMP 区分两种应用档位：

#### 1. PCMP Lite (极简 4 件套)
- **适用场景**：单人独立项目、原型验证、小型脚本/工具库、维护期老项目。
- **核心构成（仅需 4 个文件）**：
  1. `AGENTS.md` (或平台规则文件如 `.cursorrules` / `CLAUDE.md`)：定义硬事实、常用命令与禁区；
  2. `ai/PROJECT.md`：记录项目宗旨、范围与硬约束；
  3. `ai/STATE.md`：**将全局状态与当前唯一活动任务合并**（包含当前任务目标、验收指标与 Next Action，无需单独建立 `TASK.md`）；
  4. `ai/DECISIONS.md`：记录重大技术方案与确认来源。
- **免建内容**：无需建立 `PLAN.md`、`ISSUES.md`、`sessions/`（通过 Git 提交或合并于 `STATE.md` 追踪）及派生索引。
- **平滑升级**：当项目进入多人协作或多阶段复杂开发时，可平滑分立出 `TASK.md` 与 `sessions/` 晋升为 Full 档位。

#### 2. PCMP Full (完整治理套件)
- **适用场景**：团队协作、中大型系统、多阶段交付、长期演进项目。
- **核心构成**：包含完整的 `PROJECT.md`、`ARCHITECTURE.md`、`STATE.md`、`TASK.md`、`PLAN.md`、`DECISIONS.md`、`ISSUES.md` 与 `sessions/` 归档。
- **配套赋能**：推荐启用 SQLite 派生索引层 (`scripts/pcmp_index.py`) 与自动化合规检查 (`--check`)。

---

## 4. 文件 Schema 规范

### 4.1 统一 Frontmatter (动态文件)
所有动态更新文件（`STATE.md`、`TASK.md` 等）必须包含统一 Frontmatter 头：
```yaml
---
pcmp_version: "2.2"
revision: 1
updated: 2026-10-20
---
```
> **规则**：写入前先读取当前 `revision`；文件发生实质变更时 `revision + 1`。若发现版本落后，须基于最新内容合并，严禁静默覆盖。

### 4.2 架构决策记录 (ADR — `DECISIONS.md`)
```markdown
## DEC-NNN — 决策标题
日期: YYYY-MM-DD | 状态: Accepted / Proposed / Deprecated / Superseded
- 确认来源: <谁在何时确认,附会话/审批链接> (缺失此字段一律视为 Proposed)
- Supersedes: <取代的旧 DEC 编号，如 DEC-002，若无填 无>
- Superseded-by: <被哪个后续 DEC 取代，若无填 无>
- 复审触发条件 (Review Trigger): <何时或满足什么条件须重新评估此决策>
- 背景 (Context): 现状与痛点
- 决策 (Decision): 采纳的技术或架构方案
- 理由 (Reason): 选择该方案的核心原因
- 备选方案 (Alternatives): 评估过但放弃的选项及放弃理由
- 影响 (Consequences): 积极收益、约束代价与潜在风险
```
> **规则**：严禁隐式推翻已 Accepted 的决策；新方案必须提出新 DEC 并明确标记取代关系。

### 4.3 `STATE.md` / `TASK.md` / 会话记录
- **`STATE.md`**：保持极高信息密度供 AI 毫秒级摄入：`Last Updated` / `Overall Status` / `Completed` / `In Progress` / `Blocked` / `Current Risks & Focus` / `Immediate Next Action`。在 Lite 档位下，直接内嵌活动任务字段。
- **`TASK.md`**（Full 档位）：**仅维护当前唯一的活动任务**：
  - `Current Task & Objective` (当前任务与核心目标)
  - `Why & Scope` (背景动机与涉及范围)
  - `Constraints & Non-Goals` (硬约束与明确的非目标，防止范围蔓延)
  - `Relevant Files` (关联的关键源码、配置或文档路径)
  - `Acceptance Criteria` (可客观核验的验收标准与完成勾选)
  - `Immediate Next Action` (即时下一步动作)
- **`sessions/SESSION-YYYY-MM-DD-NNN.md`**：元数据（日期/Agent/任务/状态） / `Goal & Why` / `What`（实际变更代码与配置） / `Result`（测试与状态） / `Issues & Decisions` / `Next`。

### 4.4 信息分层标注规范
所有 `ai/` 记录推荐使用中英对照的分层状态标签：
- `[事实]` (`[fact]`)：客观存在、已验证的代码、配置或测试现象。
- `[假设]` (`[assumption]`)：基于推论得出的推测，待进一步求证。
- `[提议]` (`[proposal]`)：AI 或成员给出的方案建议，尚未通过审批。
- `[已确认]` (`[accepted]`)：人类用户或技术负责人已明确批准的结论。
- `[未决]` (`[open]`)：尚无定论、阻塞中或待讨论的问题。

---

## 5. 标准工作流 (Workflows)

### 5.1 AI 接管流程 (Takeover Flow)
```text
1. 确定生效协议: 若 ai/ 存在项目使用版则优先使用，否则读取根目录原版
   ↓
2. 必读输入: 读取 ai/PROJECT.md (掌握系统定位、目标与硬约束)
   ↓
3. 读取状态与任务: ai/STATE.md + ai/TASK.md (明确当前位置与焦点)
   ↓
4. 检索决策: 按当前任务检索 ai/DECISIONS.md 中相关 Accepted 决策
   ↓
5. 按需补充: 查阅 ARCHITECTURE.md / PLAN.md；仅在需要佐证时进入 sessions/
   ↓
6. 核验产物: 审阅相关源码与测试 → 确定 Immediate Next Action → 开始执行
```
> **自检机制**：若必读文件缺失，自动转入初始化流程，列出缺失清单，严禁擅自猜测项目状态。

### 5.2 会话收尾工作流 (Session Completion Flow)
```text
1. 产物与合规验证: 运行自动化测试与静态检查；若存在派生工具，执行 python3 scripts/pcmp_index.py --check 验证状态与决策完整性
   ↓
2. 变更审查: 执行 git status / diff，确认变更范围未超出任务定义
   ↓
3. 沉淀会话: 编写 ai/sessions/SESSION-YYYY-MM-DD-NNN.md 会话记录 (Full 档位) 或合并记录于 STATE (Lite 档位)
   ↓
4. 更新状态: 刷新 ai/STATE.md 与 ai/TASK.md (更新 revision 与日期)
   ↓
5. 登记决策: 若涉及架构/规则变动，在 DECISIONS.md 追加 ADR (未确认标 Proposed)
   ↓
6. (可选) 刷新派生索引: 若启用了 SQLite 索引则更新缓存 (python3 scripts/pcmp_index.py --update)
   ↓
7. 持久化归档: 进行 Git 提交或持久化保存
```

### 5.3 冲突处理准则 (Conflict Resolution)
遵循原则 2：`revision` 冲突时以较新版本合并；文档与实现冲突时，核验证据链并确认取代关系。无法断定时记录冲突并请求人工裁决。

---

## 6. SQLite 派生索引层 (可选机制)

1. **定位与边界**：作为从 Markdown 派生的**可选全文检索与结构化查询加速层**（生成于 `ai/.cache/index.sqlite`）。
2. **纯派生性**：Markdown 是唯一法定权威。删除索引文件后，人类与 AI 仍可不受任何影响地理解与接管项目。
3. **失效检测**：基于文件路径与内容 Hash 校验过期状态，不单纯依赖文件时间戳。
4. **Git 忽略规范**：启用了索引的项目，必须在 `.gitignore` 中显式添加：
   ```gitignore
   ai/.cache/
   ```

---

## 7. 开发扩展规范 (可选模块)

针对大型或特定研发流程，可按需启用以下扩展（不属于通用最小核心）：
- **阶段独立技术文档**：在 `docs/S{N}-{short_name}/` 维护阶段专属的 4+1 架构视图 (`4_plus_1_view.md`) 与需求-功能-方法追踪矩阵 (`requirements_traceability.md`)。
- **双轨工程目录管理**：
  - 分阶段工程 (`phases/S{N}-{short_name}/`)：自包含、专一实现该阶段目标，利于代码回溯复盘；
  - 持续演进主工程 (`continuous/`)：集成已验证成果的主干仓库。

---

## 8. 恢复测试验收标准 (Recovery Test)

对一个完全没有会话历史记忆的新 AI 智能体，按照 §5.1 接管流程执行，能够准确无误地回答以下 5 个核心问题即视为上下文完整恢复：
1. **项目核心目标与验收指标是什么？**
2. **有哪些不得突破的硬约束与安全边界？**
3. **有哪些已确认 (Accepted) 的重大决定、理由及其确认来源？**
4. **当前开发进度为何？是否存在阻塞问题？**
5. **下一步即时动作 (Immediate Next Action) 是什么？**

> 若有任何一项无法准确回答，即表明 `STATE` / `TASK` / `DECISIONS` 存在上下文缺失，需立即补全。

---

## 9. 治理与权限边界

### 9.1 AI 权限范围
- **允许**：更新 `ai/` 状态快照、任务单、计划、会话记录、问题登记；压缩归档旧历史；提出 ADR 提议 (`[提议]`)。
- **禁止**：擅自越权扩大任务范围；隐式推翻已确认决策；未经人类批准修改协议本身。

### 9.2 人类批准边界 (须明确授权)
- 变更项目宗旨、核心目标与产品定位。
- 变更关键架构原则或推翻已定 Accepted 决策。
- 变更安全策略、权限边界或隐私保护规则。
- 协议原版规范的升级与变更。

---

## 10. 标准人类交互指令 (Standard Prompts)

人类开发者可直接复制以下标准化提示词驱动任意 AI 智能体：

> [!TIP]
> **项目初始化 (Initialize Context)**  
> `请读取 PROJECT_CONTEXT_ZH.md（或英文版 PROJECT_CONTEXT.md），初始化本项目的 ai/ 上下文管理体系并评估当前项目状态。`

> [!TIP]
> **跨会话 / 换新 AI 接管 (Takeover & Continue)**  
> `请读取 PROJECT_CONTEXT_ZH.md 接管项目，按必读顺序查阅 ai/PROJECT.md、ai/STATE.md 和 ai/TASK.md，列出未决问题后继续推进当前任务。`

> [!TIP]
> **只读状态与一致性诊断 (Read-Only Assessment)**  
> `请读取 PROJECT_CONTEXT_ZH.md，评估项目当前状态与架构一致性，分析代码与文档是否存在脱节。不要修改代码。`

> [!TIP]
> **方案规划与 ADR 决策提议 (Planning & Proposal)**  
> `请读取 PROJECT_CONTEXT_ZH.md，结合 ai/PLAN.md 提出下一步开发计划或架构方案建议。不要修改代码。`

> [!TIP]
> **会话收尾与上下文沉淀 (Finalize Session)**  
> `请按照 PCMP 协议规范收尾当前会话：验证产物，在 ai/sessions/ 沉淀会话记录，更新 ai/STATE.md 和 ai/TASK.md，新决定登记到 ai/DECISIONS.md（未确认标 Proposed）。`

---

## 11. 推荐实践与合规自检清单 (Checklist & Best Practices)

- [ ] **启动前检查**：已阅读生效协议，通过 `PROJECT.md`、`STATE.md` 和 `TASK.md` 明确当前状态与焦点。
- [ ] **材料审阅授权（推荐实践）**：**审阅、审计或格式检查的材料由人类指定或显式授权挑选**；未获用户明确许可前，AI 不得擅自扫描全工程扩大审阅范围。
- [ ] **过程中控制**：严格专注当前任务范围，未盲目引入无关重构；重大架构设计已登记为 ADR 提议 (`[提议]`)。
- [ ] **决策真实性**：已确认的 ADR 均具备可靠的 `- 确认来源` 记录。
- [ ] **收尾前自检**：实现与测试已通过，执行 `--check` 无错误（若启用派生工具），会话已沉淀至 `sessions/`，`STATE.md` 与 `TASK.md` 已同步更新并递增 `revision`。
