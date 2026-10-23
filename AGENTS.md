<!-- stc:start -->
<!-- stc:mode=default -->
## 中文写作：STC（Simplified Technical Chinese）

写中文时必须遵循 STC 规范：自然、简短、准确，任务回执必须分为“做完了”“需要你”“知会”。
<!-- stc:end -->

## 项目宗旨与定位
cloudmirror (核心组件 `bw_sync`) 是面向自托管环境的 NodeWarden ↔ Vaultwarden 个人保险库双向对比与同步系统。核心安全哲学为：**“只增不改不删”**——新增单边补齐、内容差异各存冲突副本交由人工裁决、单边消失判定疑似删除记入墓碑绝不自动抹除另一侧。

工程遵循 **PCMP (Project Context Management Protocol v2.2)** 规范进行人机协同工程上下文管理：**纯 Markdown 权威驱动、单文档开箱自举、派生索引可随意删除重建**。

## 关键路径索引
- 项目需求与说明：[README.md](README.md)
- 核心同步脚本：[bw_sync.py](bw_sync.py)
- 容器镜像与编排：[Dockerfile](Dockerfile) / [docker-compose.yml](docker-compose.yml)
- 配置与环境变量模板：[config.example.json](config.example.json) / [.env.example](.env.example)
- 协同管理协议：[PROJECT_CONTEXT_ZH.md](PROJECT_CONTEXT_ZH.md) / [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
- 项目状态真源：[ai/PROJECT.md](ai/PROJECT.md)（硬约束与范围）、[ai/ARCHITECTURE.md](ai/ARCHITECTURE.md)（系统架构）、[ai/STATE.md](ai/STATE.md)（全局状态）、[ai/TASK.md](ai/TASK.md)（当前活动任务）、[ai/DECISIONS.md](ai/DECISIONS.md)（ADR 决策）、[ai/ISSUES.md](ai/ISSUES.md)（已知风险与问题）
- 派生工具与技能：[scripts/pcmp_index.py](scripts/pcmp_index.py)、[skills/pcmp/SKILL.md](skills/pcmp/SKILL.md)

## 常用工程命令
- **自动化合规检查**：`python3 scripts/pcmp_index.py --check`
- **运行单元测试套件**：`python3 -m unittest discover tests`
- **离线同步逻辑自测**：`python3 bw_sync.py --selftest`
- **只读预览同步报告**：`python3 bw_sync.py`
- **真正执行双向同步**：`python3 bw_sync.py --apply`
- **增量刷新派生索引**：`python3 scripts/pcmp_index.py --update`
- **全量重建派生索引**：`python3 scripts/pcmp_index.py --rebuild`
- **检索决策与标签**：`python3 scripts/pcmp_index.py --query-decisions` / `--query-tags`

## 核心设计与开发规范
1. **只增不改不删策略**：
   - 两端皆有且规范化内容哈希一致：跳过；
   - 仅单侧存在：在对侧新建；
   - 两端皆有但内容不同且有新变更：保留各自原件，各建一条“`[冲突副本·YYYY-MM-DD]`”交由人工裁决；
   - 历史已配对条目在单侧消失：标记为疑似删除并记入墓碑，绝不自动硬删对侧，亦不复活。
2. **凭据安全与隔离**：
   - 主密码与 API Key 仅通过终端非回显输入或环境变量注入，绝不硬编码，绝不写入代码、配置、报告、镜像或状态文件；
   - 两个实例的 Bitwarden CLI 登录态严格按目录物理隔离（`BITWARDENCLI_APPDATA_DIR`）。
3. **零外部依赖约定**：
   - 同步脚本 `bw_sync.py` 与派生工具 `scripts/pcmp_index.py` 严格仅依赖 Python 3 原生标准库，零 pip 依赖；保持单文件自足；遵循 PEP 8 规范。
4. **离线自测优先**：
   - 任何改动必须能通过 `python3 bw_sync.py --selftest` 离线覆盖所有冲突、删除、重名、跳过逻辑；单元测试必须通过 `python3 -m unittest discover tests`。

## 红线与禁区 (Hard Boundaries)
1. **明文凭据绝不上盘**：严禁在代码、日志、提交历史、文档或镜像中硬编码或回显主密码及解密后的条目明文；
2. **严禁自动硬删除与覆盖**：严禁跨端自动抹除任何条目；严禁在未获人类明确操作裁决前直接覆盖改写已有条目原件；
3. **协议原版保护**：严禁未经人类授权直接修改根目录通用协议原版（`PROJECT_CONTEXT_ZH.md` / `PROJECT_CONTEXT.md`）；
4. **决策链条完整**：严禁隐式推翻已 Accepted 决策；新方案必须记录 `Supersedes` 并附带确认来源；
5. **协议产品解耦**：PCMP 仅为协同管理协议，严禁作为业务代码逻辑或运行依赖硬编码进产品源码；
6. **材料审阅授权**：审阅、审计或样式检查的材料由人类指定或显式授权挑选，未获许可前不得擅自扫描全工程扩大审阅范围。
