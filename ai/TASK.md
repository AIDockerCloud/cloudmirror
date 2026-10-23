---
pcmp_version: "2.2"
revision: 1
updated: 2026-10-24
---

# 当前唯一活动任务 (TASK.md)

## 当前任务与核心目标 (Current Task & Objective)
- **任务名称**：cloudmirror 项目 PCMP v2.2 工程上下文治理体系初始化。
- **核心目标**：参考 `AIDockerCloud/PCMP` 协议与工具链规范，建立完备的 PCMP Full 档位管理架构，补齐 `.gitignore`、样板配置（`config.example.json`、`.env.example`）、测试套件（`tests/`），并通过合规性自动化检查与单元测试验证。

## 背景与范围 (Why & Scope)
- **背景**：当前项目已实现核心同步脚本 `bw_sync.py` 与容器化方案，但缺乏标准化的工程上下文治理、敏感信息隔离忽略规则、测试接入与持续合规校验能力。
- **范围**：
  - 协议原版与派生工具：`PROJECT_CONTEXT_ZH.md`、`PROJECT_CONTEXT.md`、`scripts/pcmp_index.py`、`skills/pcmp/`；
  - 规范文件与安全规则：`AGENTS.md`、`.gitignore`、`config.example.json`、`.env.example`；
  - 上下文真源：`ai/PROJECT.md`、`ai/ARCHITECTURE.md`、`ai/STATE.md`、`ai/TASK.md`、`ai/DECISIONS.md`、`ai/ISSUES.md` 与 `ai/sessions/`；
  - 测试套件：`tests/test_pcmp_index.py` 与 `tests/test_bw_sync.py`。

## 约束与非目标 (Constraints & Non-Goals)
- **硬约束**：
  - 遵循 STC（Simplified Technical Chinese）规范；
  - 严禁修改通用协议规范原版；
  - 严禁在任何提交文件或缓存中泄露真实密码与敏感凭证；
  - 派生工具与测试仅依赖 Python 3 标准库，零 pip 外部依赖。
- **非目标**：
  - 本任务不连接真机服务端执行写入同步；
  - 暂不扩展 v2 复杂特性（如附件同步或 Passkey 凭据迁移）。

## 关联关键文件 (Relevant Files)
- `AGENTS.md`：协同与智能体规范
- `PROJECT_CONTEXT_ZH.md` & `PROJECT_CONTEXT.md`：核心协议中英文原版
- `ai/PROJECT.md`、`ai/ARCHITECTURE.md`、`ai/STATE.md`、`ai/DECISIONS.md`、`ai/ISSUES.md`：上下文真源
- `scripts/pcmp_index.py` & `skills/pcmp/scripts/pcmp_index.py`：派生索引与合规检查器
- `tests/test_pcmp_index.py` & `tests/test_bw_sync.py`：测试套件
- `.gitignore`、`config.example.json`、`.env.example`：安全隔离与样板配置

## 验收结果 (Acceptance Result)
- [x] 引入中英双语 PCMP 核心规范原版并校验结构对称；
- [x] 建立 `AGENTS.md` 并遵循 STC 规范，定义项目定位、关键索引与红线禁区；
- [x] 建立 `.gitignore` 排除敏感配置文件、状态文件、临时会话与 PCMP 派生缓存；
- [x] 补全 `config.example.json` 与 `.env.example` 配置示例文件；
- [x] 构建完整的 `ai/` 上下文真源文件，登记首批 3 项已确认 ADR（DEC-001、DEC-002、DEC-003）；
- [x] 运行 `python3 scripts/pcmp_index.py --rebuild` 成功生成 SQLite 派生索引；
- [x] 运行 `python3 scripts/pcmp_index.py --check` 自动化合规检查 0 错误 0 警告；
- [x] 运行 `python3 -m unittest discover tests` 单元测试全部通过。

## 即时动作 (Immediate Next Action)
- 向人类开发者提交初始化完成报告，等待确认 Git 提交。

