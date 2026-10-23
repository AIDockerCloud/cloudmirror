---
pcmp_version: "2.2"
updated: 2026-10-20
---

# Project Context Management Protocol (PCMP)

- **Version**: **2.2** (2026-10-20)
- **Document Role**: This file is the **original generic protocol template**, containing no project-specific state or private details.
- **Chinese Version**: [PROJECT_CONTEXT_ZH.md](PROJECT_CONTEXT_ZH.md) (Content is bidirectionally aligned; discrepancies are treated as translation synchronization tasks).
- **Resolution Rule**: If `ai/PROJECT_CONTEXT.md` (project instance) exists, it takes precedence; otherwise, this root original is authoritative (see §3.1).

---

## 1. Capability Boundaries

PCMP explicitly **does not promise** the following:
1. **Does not promise complete preservation of entire chat dialogues**: Only preserves necessary context required for work resumption, handover, and decision traceability.
2. **Does not promise automatic discovery by all AI platforms**: Automatic file discovery relies on platform/IDE adapter configurations (e.g., `.cursorrules`, `AGENTS.md`, `CLAUDE.md`).
3. **Does not promise that `revision` acts as a distributed atomic lock**: It is a change-detection marker; concurrency safety relies on serialized write-back or a single merger workflow.

---

## 2. Core Principles

1. **Current State First, Including Definitions**  
   AI takeover mandatory sequence = **This protocol + `ai/PROJECT.md` (goals & hard constraints) + `ai/STATE.md` + `ai/TASK.md`**. Never assume constraints from status summaries alone; never reconstruct current state by traversing entire chat histories.
2. **Tiered Conflict Verification, No Absolute Priority**  
   Code and tests prove the "current physical implementation," but do not automatically override user requirements, security constraints, or accepted decisions. On discrepancy: **Flag difference ➔ Verify evidence (requirements/ADR/tests) ➔ Decide whether to fix code or update documentation**.
3. **Minimal Effective Context**  
   Maintain only decision-relevant and actionable information; historical sessions are periodically compressed into summaries to prevent unbounded context growth.
4. **AI- and Platform-Agnostic**  
   Independent of any specific model, IDE, CLI, or cloud platform; operates entirely via local filesystem and Markdown.
5. **Information Layering**  
   All critical information is labeled with explicit state tags: `[fact]` / `[assumption]` / `[proposal]` / `[accepted]` / `[open]`. AI suggestions must not be recorded as accepted without human confirmation.
6. **Decoupling Protocol from Product Code**  
   PCMP is strictly a human-AI collaborative engineering convention. It must NEVER be hardcoded into product source code as a business or runtime dependency.
7. **Markdown as Authority, Derivatives Fully Rebuildable**  
   All authoritative facts and decisions live solely in Markdown files. Indexes and caches (e.g., SQLite) are transient derivatives; humans and AI can fully understand and take over projects without any derivatives.

---

## 3. Directory Structure & File Roles

```text
Project Root/
├── PROJECT_CONTEXT.md        # English full protocol (Original template)
├── PROJECT_CONTEXT_ZH.md     # Chinese full protocol (Original template)
├── .gitignore                # Ignored paths: Must include node_modules/ and ai/.cache/
└── ai/
    ├── PROJECT.md            # Identity, purpose, goals, scope & hard constraints (Long-lived)
    ├── ARCHITECTURE.md       # Tech stack, architecture, modules, data flow & constraints (Long-lived)
    ├── STATE.md              # Global project state snapshot (Dynamic)
    ├── TASK.md               # Active single task & acceptance criteria (Dynamic)
    ├── PLAN.md               # Roadmap & milestone planning (Dynamic)
    ├── DECISIONS.md          # Architecture Decision Records (ADR, Long-lived)
    ├── ISSUES.md             # Known issues & risk tracking (Dynamic)
    ├── sessions/             # Session records (Append-only, periodically compressed)
    ├── proposals/            # Protocol improvement proposals (Append-only)
    ├── .cache/               # (Optional) Rebuildable index & cache (git-ignored)
    └── PROJECT_CONTEXT.md / PROJECT_CONTEXT_ZH.md   # (Optional) Project instance (Precedes if present)
```

> **Minimal Usable Set**: The two root originals constitute the minimal set. New projects start with just the originals; missing `ai/` files trigger the initialization flow (§5.1). All paths resolve relative to the **project root**.

### File Responsibilities Table

| File / Directory | Responsibility | Update Nature | Authority Level |
| :--- | :--- | :--- | :--- |
| `ai/PROJECT.md` | Identity, mission, target users, scope, non-goals & hard constraints | Long-lived | Strong constraint |
| `ai/ARCHITECTURE.md`| Architecture, module relationships, data flow & conventions | Long-lived | Strong guideline |
| `ai/STATE.md` | Current state snapshot: completed, active, blocked, risks, next action | Dynamic | Real-time baseline |
| `ai/TASK.md` | Single active task: objective, why, scope, criteria, immediate action | Dynamic | Execution focus |
| `ai/PLAN.md` | Current phase, milestones, near-term & long-term roadmap | Dynamic | Directional guidance |
| `ai/DECISIONS.md` | ADR logs: context, decision, reason, alternatives, confirmation source | Long-lived | Authoritative policy |
| `ai/ISSUES.md` | Issue tracking: ID, status, description, impact, workaround | Dynamic | Fact log |
| `ai/sessions/` | Structured session records (`SESSION-YYYY-MM-DD-NNN.md`) | Append-only | Audit evidence |
| `ai/proposals/` | Protocol enhancement suggestions and RFC proposals | Append-only | Proposal record |

### 3.1 Originals, Project Instances, and General Improvement Flow

- **Originals**: Root `PROJECT_CONTEXT.md` / `PROJECT_CONTEXT_ZH.md`. Generic templates containing no private project state or temporary IDs.
- **Project Instance**: When a project requires customizations, copy the full original to `ai/PROJECT_CONTEXT.md` to evolve locally. Projects without customizations use the root original directly.
- **Bilingual Alignment**: Rules in Chinese and English must remain identical; discrepancies must be resolved by synchronization.
- **General Improvement Flow**: If a project instance produces cross-project protocol enhancements, do not overwrite originals directly. Generate root candidate files (`PROJECT_CONTEXT.optimized-<id>.md`, `PROJECT_CONTEXT_ZH.optimized-<id>.md` and patch note `PCMP-PATCH-<id>.md`). Candidates take effect only upon human confirmation.

### 3.2 PCMP Tiers: Lite vs Full

To prevent "Governance Inflation" in small or single-developer workflows, PCMP specifies two practical tiers:

#### 1. PCMP Lite (Minimal 4-Piece Set)
- **Use Cases**: Single-developer projects, rapid prototyping, scripts/utility libraries, legacy maintenance.
- **Core Composition (Only 4 files)**:
  1. `AGENTS.md` (or platform config like `.cursorrules` / `CLAUDE.md`): Hard engineering facts, commands, boundaries;
  2. `ai/PROJECT.md`: Purpose, mission, non-goals & hard constraints;
  3. `ai/STATE.md`: **Consolidates global state and active task** (includes current task objective, criteria, and next action; eliminates standalone `TASK.md`);
  4. `ai/DECISIONS.md`: Logs architectural decisions and confirmation sources.
- **Excluded**: No requirement for `PLAN.md`, `ISSUES.md`, `sessions/` (tracked via git commits or inside `STATE.md`), or derivative index.
- **Smooth Upgrade**: When complexity grows, split out `TASK.md` and `sessions/` to upgrade smoothly to Full tier.

#### 2. PCMP Full (Complete Governance Suite)
- **Use Cases**: Team collaboration, multi-phase systems, enterprise-scale products.
- **Core Composition**: Complete set of `PROJECT.md`, `ARCHITECTURE.md`, `STATE.md`, `TASK.md`, `PLAN.md`, `DECISIONS.md`, `ISSUES.md`, and `sessions/` archives.
- **Tooling Support**: Recommended SQLite derivative index (`scripts/pcmp_index.py`) and automated compliance check (`--check`).

---

## 4. File Schema Specifications

### 4.1 Frontmatter (Dynamic Files)
All dynamically updated files (`STATE.md`, `TASK.md`, etc.) must include a standard Frontmatter:
```yaml
---
pcmp_version: "2.2"
revision: 1
updated: 2026-10-20
---
```
> **Rule**: Read `revision` before writing; increment `revision + 1` upon meaningful changes. Merge on top of newer versions; never overwrite silently.

### 4.2 Architecture Decision Records (ADR — `DECISIONS.md`)
```markdown
## DEC-NNN — Decision Title
Date: YYYY-MM-DD | Status: Accepted / Proposed / Deprecated / Superseded
- Confirmation Source: <Who confirmed, when, with session/approval link> (Missing = always Proposed)
- Supersedes: <Previous DEC replaced, e.g. DEC-002, or None>
- Superseded-by: <Subsequent DEC replacing this, or None>
- Review Trigger: <Conditions or events triggering re-evaluation>
- Context: Current situation and problem
- Decision: Chosen technical or architectural solution
- Reason: Why this solution was chosen
- Alternatives: Evaluated alternatives and reasons for rejection
- Consequences: Positive outcomes, trade-offs, and constraints
```
> **Rule**: Silently reversing accepted decisions is prohibited; new decisions must explicitly reference and supersede previous records.

### 4.3 `STATE.md` / `TASK.md` / Session Records
- **`STATE.md`**: Kept concise for instant ingestion: `Last Updated` / `Overall Status` / `Completed` / `In Progress` / `Blocked` / `Current Risks & Focus` / `Immediate Next Action`. In Lite tier, directly embeds active task details.
- **`TASK.md`** (Full Tier): **Tracks only the single currently active task**:
  - `Current Task & Objective`
  - `Why & Scope`
  - `Constraints & Non-Goals` (Hard constraints and explicit non-goals to prevent scope creep)
  - `Relevant Files` (Key paths, configs, tests)
  - `Acceptance Criteria` (Verifiable criteria with checkboxes)
  - `Immediate Next Action`
- **`sessions/SESSION-YYYY-MM-DD-NNN.md`**: Metadata (date/agent/task/status) / `Goal & Why` / `What` (actual code/config changes) / `Result` (tests/state) / `Issues & Decisions` / `Next`.

### 4.4 Information Layering Labels
All `ai/` records should use explicit status tags:
- `[fact]` (`[事实]`): Objective, verified code, config, or test behavior.
- `[assumption]` (`[假设]`): Deduced assumption awaiting empirical proof.
- `[proposal]` (`[提议]`): Proposal by AI or member, not yet accepted.
- `[accepted]` (`[已确认]`): Explicitly approved by user or tech lead.
- `[open]` (`[未决]`): Unresolved question, blocker, or open issue.

---

## 5. Standard Workflows

### 5.1 AI Takeover Flow
```text
1. Determine effective protocol: Use ai/ instance if present, else root original
   ↓
2. Mandatory reading: Read ai/PROJECT.md (system mission, goals & constraints)
   ↓
3. Grasp status & task: ai/STATE.md + ai/TASK.md (current location & focus)
   ↓
4. Retrieve decisions: Search ai/DECISIONS.md for relevant Accepted decisions
   ↓
5. Supplement as needed: Inspect ARCHITECTURE.md / PLAN.md; enter sessions/ only for evidence
   ↓
6. Inspect deliverables: Verify source code & tests → Determine Immediate Next Action → Execute
```
> **Self-Correction**: Missing mandatory files triggers the initialization flow; never guess project state.

### 5.2 Session Completion Flow
```text
1. Verify deliverables & compliance: Run tests and static analysis; run python3 scripts/pcmp_index.py --check if tooling is present
   ↓
2. Review changes: Run git status / diff to ensure bounded scope
   ↓
3. Record session: Write ai/sessions/SESSION-YYYY-MM-DD-NNN.md (Full tier) or merge into STATE (Lite tier)
   ↓
4. Update state: Refresh ai/STATE.md & ai/TASK.md (increment revision & date)
   ↓
5. Register decisions: Log any architectural change in DECISIONS.md (unconfirmed = Proposed)
   ↓
6. (Optional) Refresh index: Update SQLite cache (python3 scripts/pcmp_index.py --update)
   ↓
7. Persist & commit: Execute git commit or persistence step
```

### 5.3 Conflict Resolution
Following Principle 2: Merge on newer revision; verify evidence chains for code-doc discrepancies. Pause and request human clarification when unresolvable.

---

## 6. SQLite Derivative Index Layer (Optional)

1. **Role**: Rebuildable full-text search and structured query layer (`ai/.cache/index.sqlite`).
2. **Derivative Nature**: Markdown is the sole authority. Deleting the database has zero negative impact on human/AI ability to take over.
3. **Staleness Check**: Uses file path + content hash rather than timestamps alone.
4. **Git Policy**: Projects enabling the index MUST include in `.gitignore`:
   ```gitignore
   ai/.cache/
   ```

---

## 7. Development Extensions (Optional)

For large software engineering workflows (not part of the minimal universal core):
- **Phase Technical Documentation**: Maintain 4+1 views (`4_plus_1_view.md`) and requirements-features-methods traceability matrices (`requirements_traceability.md`) under `docs/S{N}-{short_name}/`.
- **Dual-Track Directory Management**:
  - Phase standalone projects (`phases/S{N}-{short_name}/`): Self-contained code scoped strictly to milestone goals.
  - Continuous evolution project (`continuous/`): Mainline codebase integrating verified phase code.

---

## 8. Recovery Test Acceptance Criteria

A new AI agent with no prior conversational memory following §5.1 must accurately answer:
1. **What are the core project goals and acceptance criteria?**
2. **What are the non-negotiable hard constraints and safety boundaries?**
3. **What Accepted architectural decisions exist, why, and confirmed by whom?**
4. **What is the current development progress and are there any blockers?**
5. **What is the exact Immediate Next Action?**

> Inability to answer any item reveals missing context in `STATE` / `TASK` / `DECISIONS`, which must be filled immediately.

---

## 9. Governance & Approval Boundaries

### 9.1 AI Permissions
- **Allowed**: Update `ai/` state, task, plan, sessions, issues; compress old history; propose ADRs (`[proposal]`).
- **Prohibited**: Scope creep; silently overturning decisions; modifying this protocol without human approval.

### 9.2 Human Approval Required
- Modifying core identity, project goals, and product scope.
- Reversing key architectural decisions or Accepted ADRs.
- Changing security policies, permission boundaries, or privacy rules.
- Upgrading or changing protocol originals.

---

## 10. Standard Human Prompts

Human developers can copy these standardized prompts across any AI coding agent:

> [!TIP]
> **Initialize Context**  
> `Read PROJECT_CONTEXT.md (or Chinese PROJECT_CONTEXT_ZH.md), initialize this project's ai/ context management system, and assess the current project state.`

> [!TIP]
> **Takeover & Continue**  
> `Read PROJECT_CONTEXT.md and take over the project. Follow the mandatory reading sequence: ai/PROJECT.md, ai/STATE.md, and ai/TASK.md. List open questions, then proceed with the active task.`

> [!TIP]
> **Read-Only Assessment**  
> `Read PROJECT_CONTEXT.md and assess the current project status and architectural consistency. Check for documentation-code drift. Do not modify any code.`

> [!TIP]
> **Planning & Decision Proposal**  
> `Read PROJECT_CONTEXT.md, review ai/PLAN.md, and propose the next development roadmap or architectural decisions. Do not modify code.`

> [!TIP]
> **Finalize Session**  
> `Finalize this session per PCMP: verify deliverables and tests, record the session under ai/sessions/, update ai/STATE.md and ai/TASK.md, and log any new decision in ai/DECISIONS.md (unconfirmed = Proposed).`

---

## 11. Checklist & Recommended Best Practices

- [ ] **Pre-Session**: Read effective protocol; grasp system boundaries via `PROJECT.md`, `STATE.md`, and `TASK.md`.
- [ ] **Review Material Authorization (Recommended Practice)**: **Materials for review, audit, or stylistic checks must be explicitly specified or authorized by humans**; AI must not scan the full workspace or expand review scope without permission.
- [ ] **Scope Control**: Stay focused strictly within task scope; propose ADRs for architectural deviations.
- [ ] **Decision Validity**: All Accepted ADRs include a verified `- Confirmation Source`.
- [ ] **Post-Session**: Tests passed, `--check` passed cleanly (if tooling is active), session logged under `sessions/`, `STATE.md` and `TASK.md` updated with incremented `revision`.
