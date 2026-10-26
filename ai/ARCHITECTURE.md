---
pcmp_version: "2.2"
revision: 2
updated: 2026-10-27
---

# 系统架构与技术约定 (ARCHITECTURE.md)

## 1. 系统总体架构

cloudmirror 采用“客户端单中心调度、两端隔离拉取、单向新增写入”的双向同步架构：

```text
┌──────────────────────────────┐              ┌──────────────────────────────┐
│          NodeWarden          │              │         Vaultwarden          │
│     (Cloudflare Workers)     │              │     (Olares / Home / VPS)    │
└──────────────▲───────────────┘              └──────────────▲───────────────┘
               │                                             │
               │ HTTPS (bw CLI)                              │ HTTPS (bw CLI)
               ▼                                             ▼
┌──────────────────────────────┐              ┌──────────────────────────────┐
│  BITWARDENCLI_APPDATA_DIR    │              │  BITWARDENCLI_APPDATA_DIR    │
│          (bw-node/)          │              │         (bw-vault/)          │
└──────────────▲───────────────┘              └──────────────▲───────────────┘
               │                                             │
               └──────────────────────┬──────────────────────┘
                                      │
                         ┌────────────┴────────────┐
                         │   bw_sync.py 核心引擎   │
                         │   - RealBwClient        │
                         │   - normalize_item()    │
                         │   - content_hash()      │
                         │   - plan_sync()         │
                         │   - execute_sync()      │
                         └────────────┬────────────┘
                                      │ 维护配对与墓碑
                                      ▼
                         ┌─────────────────────────┐
                         │   bw-sync-state.json    │
                         │   (pairs, hashes, dead) │
                         └─────────────────────────┘
```

## 2. 核心模块与数据流

### 2.1 客户端抽象层
- **`RealBwClient`**：负责调度官方 `bw` CLI 执行登录 (`bw login`)、解锁 (`bw unlock`)、同步 (`bw sync`)、导出 (`bw list items`)、创建 (`bw create`) 与加锁 (`bw lock`)。
  - 通过环境变量 `BITWARDENCLI_APPDATA_DIR` 隔离两端本地登录态目录 (`bw-node/` 与 `bw-vault/`)；
  - 超时保护机制：常规操作 120 秒，list/sync 300 秒，防止连网超时死锁；
  - 销毁机制：退出时自动触发 `close()` 执行双端 `bw lock`。
- **`FakeBwClient`**：内存模拟客户端，用于脱机离线测试，支持完备的增删改查动作校验。

### 2.2 规范化与等价性判别
- **条目规范化 (`normalize_item`)**：
  - 提取关键字段：`type`, `name`, `folder`, `favorite`, `reprompt`, `notes`, `fields` 以及各特定区段 (`login`, `secureNote`, `card`, `identity`, `sshKey`)；
  - 剥离不可比及易变元数据：剔除 `id`, `revisionDate`, `creationDate`, `deletedDate`, `passwordHistory`, `attachments`, `collectionIds`, `organizationId`；
  - 剥离 Passkey：针对 `login` 区段自动剔除 `fido2Credentials` 与 `passwordRevisionDate`。
- **哈希判等 (`content_hash`)**：将规范化后的字典按键升序序列化为 JSON 字符串，计算 SHA-256 哈希作为条目内容指纹。
- **自然键标识 (`natural_key`)**：`(type, name.strip().casefold(), username.strip().casefold())`，在 state 映射表未匹配时作为第二配对依据。

### 2.3 状态与同步决策状态机
状态文件 `bw-sync-state.json` 包含三部分：
1. `pairs`：双端条目 ID 配对字典；
2. `hashes`：上次同步完成时的双端条目内容基线哈希；
3. `tombstones`：已被确认为“疑似删除”的墓碑条目 ID 集合。

决策逻辑矩阵：
| 场景 | 状态判断依据 | 处置方案 |
| :--- | :--- | :--- |
| **内容一致** | 两侧均存在且内容哈希等于上次基线或相互相等 | 跳过 |
| **单侧新增** | 仅单侧存在，且不属于墓碑 | 在对侧使用剥离元数据后的模板执行新建 |
| **内容冲突** | 两侧已配对，但哈希不同且发生了新修改 | 双方保留原件不变，各生成带有日期标识的冲突副本条目（如 `[冲突副本·2026-10-24]`） |
| **已处理冲突** | 两侧哈希不同但已建立过副本且未再发生变动 | 跳过，防止每次同步生成重复冲突副本 |
| **疑似删除** | 历史已配对条目在其中一端消失 | 绝不删除另一侧；将该条目记入墓碑 (`tombstones`) 并报警 |
| **重名歧义** | 同类型、同名称、同用户名出现多条 | 不可信配对，直接加入歧义清单供人工裁决，脚本跳过不处理 |

## 3. 容器与交付架构

- **镜像构建 (`Dockerfile`)**：
  - 基础镜像：`python:3.12-slim`；
  - 二进制分发：直接下载官方 release 钉死版本（当前为 **2026.10.0**），分别核对 amd64 与 arm64 的 SHA-256 校验和，坚决不走 npm 安装避免包供应链风险；
  - 容器形态：非后台常驻进程，作为一次性作业容器 (`docker compose run --rm bw-sync`) 运行，跑完立即退出。
- **持久化与安全挂载 (`docker-compose.yml`)**：
  - 配置文件只读挂载：`./config.json:/app/config.json:ro`；
  - 状态文件可读写挂载：`./bw-sync-state.json:/app/bw-sync-state.json`；
  - 凭证隔离目录挂载：`./bw-node:/app/bw-node` 与 `./bw-vault:/app/bw-vault`；
  - 密码注入：通过 `.env`（`chmod 600`，被 `.gitignore` 排除）经由 `env_file` 注入。

## 4. PCMP 协同与工程上下文管理

遵循 PCMP v2.2 Full 档位标准，设立 Markdown 权威真源与 Python 原生派生索引层：
- **真源目录**：`ai/`（`PROJECT.md`, `ARCHITECTURE.md`, `STATE.md`, `TASK.md`, `DECISIONS.md`, `ISSUES.md`, `sessions/`）；
- **派生缓存**：`ai/.cache/index.sqlite`（提供 FTS5 全文搜索、ADR 结构化查询）；
- **检查脚本**：`scripts/pcmp_index.py`，单文件零外部依赖，提供持续合规性自检与单测守护。

## 5. S3 增量同步与对象存储架构 (S3 Engine Architecture)

### 5.1 原生 SigV4 传输与内存保护
- 基于 Python 标准库 `urllib.request` 与 `hashlib` 原生实现 AWS SigV4 签名机制，零 boto3 依赖；
- 传输使用 `tempfile.SpooledTemporaryFile(max_size=8MB)`：小于 8MB 的小对象纯内存转发，超过 8MB 的大对象自动流式缓存至磁盘临时文件，直传目标端 S3，有效杜绝传输几百兆附件时的 OOM 风险；
- 单对象网络抖动提供 3 次指数退避重试（0.5s, 1s, 2s）。

### 5.2 失败状态语义与状态保护
- 严格遵循 `failed_count == 0` 判定 `success: True`；
- 单个对象传输异常立即标记 `status: "partial"` 并回传 `failed_objects` 清单；
- 备桶元数据中的 `objects_count` 与 `last_sync` 仅在 100% 全量成功时更新，避免任何由于网络抖动导致的误报与伪造完成。

### 5.3 思源笔记不可变镜像约定与已知限制
- **块与非块分流比对**：仅 `data/*.sy` 内容块路径走大小判定；`latest`、`assets/` 附件、`conf/` 配置等非块路径严格走 大小 + ETag 复合比对，防止同大小非内容寻址文件被漏传；
- **指针后置传输**：排序阶段将 `latest`、`manifest.json`、`index.json`、`sync.json` 等关键指针对象强制排在数据块之后传输，确保中途断网或部分失败时备桶绝不留下指向缺失块的悬空坏指针；
- **已知限制与操作建议**：当前单 PUT 传输上限为 5GB（后续版本演进 S3 Multipart Upload 分片断点续传）；同步期间若源桶同时发生并发写，备桶可能拿到跨版本混合快照，生产环境建议仅在思源笔记客户端处于空闲状态时运行增量 Mirror。

