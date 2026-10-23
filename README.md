# bw_sync — NodeWarden ↔ Vaultwarden 双向同步脚本

把 Cloudflare 上的 NodeWarden 和 Olares 上的 Vaultwarden 两边保险库拉下来对比，
新增的互相补齐，不同的保留两份（冲突副本），不覆盖、不删除。
及时性要求不高时在 Win11 本地手动跑即可；逻辑成熟后再打包容器搬到服务器定时跑。

## 策略（只增不改不删）

| 情况 | 动作 |
| --- | --- |
| 两边都有、内容相同 | 跳过 |
| 只在一边有 | 在另一边新建 |
| 两边都有、内容不同、且上次同步后又变过 | 两边不动原件，各把对方版本建一条「冲突副本」，人工裁决 |
| 两边都有、内容不同、但已保留过副本且没再改 | 跳过（不会每跑一次多一对副本） |
| 已配对的条目在一边消失 | 判为疑似删除：只报告、不删另一边、也不会把存活的那条当新增补回去（墓碑机制） |
| 同名同用户名重名多条、配不准 | 进「歧义」清单，人工处理，脚本不碰 |

## 前置条件

1. Python 3.8+（只用标准库）。Win11 自检：`python --version`
2. 官方 Bitwarden CLI：到 bitwarden.com 下载 CLI 版（Windows），
   把 `bw.exe` 放到任意目录，并：
   - 要么把该目录加进 PATH，
   - 要么在本目录 `config.json` 的 `"bw"` 里写 `bw.exe` 的完整路径。
   自检：`bw --version`
3. 两边各有一个账号（建议同邮箱、同主密码，日常切换客户端时省事；
   脚本本身不要求两边密码相同）。

## 使用

```bat
copy config.example.json config.json
notepad config.json        :: 填两边的 server 地址和邮箱

python bw_sync.py          :: 只读预览：拉取+对比+出报告，不写任何数据
python bw_sync.py --apply  :: 确认报告无误后，真正执行补齐/冲突副本，并保存 state
```

运行时会用 getpass 分别提示输入两边主密码（不回显、不落盘）。
想免交互，可以先在当前终端里设置环境变量（名字见 config.json 的 `password_env`）：

```bat
set BW_SYNC_NODE_PASSWORD=******
set BW_SYNC_VAULT_PASSWORD=******
python bw_sync.py --apply
```

注意别把带密码的命令写进 .bat 文件存着。

## 文件说明

- `bw_sync.py` — 脚本本体
- `config.json` — 你的配置（从 example 复制；只有地址和邮箱，没有密码）
- `bw-sync-state.json` — 同步状态（配对表、内容哈希基线、墓碑），`--apply` 后自动生成。
  **别随便删**：删了等于失忆，脚本会重新靠「类型+名称+用户名」配对，
  内容不同的同名条目会被当成新冲突再保留一轮副本。换电脑时把这个文件一起带走。
- `bw-node/`、`bw-vault/` — bw CLI 各自的独立配置目录
  （脚本用 `BITWARDENCLI_APPDATA_DIR` 隔离两边登录态，不影响你自己日常用的 bw）。

## v1 不处理的东西

- **附件**：条目本身会同步，附件不搬，报告里会点名哪些条目带附件，自己手动搬或等 v2。
- **passkey（FIDO2 凭证）**：条目会同步，但登录项里的 passkey 不带过去——passkey 本来就绑账号密钥，两边各存一份独立的才对。
- **密码历史、Send、组织/集合条目**：不同步；组织条目会跳过（NodeWarden 本来也不支持组织）。
- **删除传播**：永远不自动删。要真删一条，两边都手动删。
- 条目里 URI、自定义字段的**顺序**变了也会被判为「内容不同」而产生冲突副本，属已知误报来源。

## 安全说明

- 脚本运行时内存里会同时有两边的主密码和解密后的保险库（经 bw CLI），
  跑的时候别在不可信的机器上跑；跑完它会 `bw lock` 两边。
- 报告只含条目名称和数量，不含密码；state 文件只存哈希和 id，不存明文。

## 离线自测（不用连服务器）

```bat
python bw_sync.py --selftest
```

用内置假数据把相同/新增/冲突/删除/重名/回收站/只读等分支都跑一遍，全 PASS 才算逻辑正常。

## 已知待实测点（第一次连真机时留意）

- 实测发现：真 bw 连一个不可达地址时自己会长时间重试（60 秒都不返回），
  所以脚本给每条 bw 命令加了超时（一般命令 120 秒、sync/list 300 秒），
  一边服务器宕机时脚本会明确报「超时——服务器可能不可达」并退出，不会挂死；
  云上定时跑时这点尤其重要，别把超时去掉。

- NodeWarden 对官方 bw CLI 的兼容程度：它宣称兼容官方客户端，
  但 CLI 未见单独声明。第一次先跑只读模式，若 NodeWarden 那边 `bw login/list` 报错，
  把报错原文留着——可能要改走邮箱密码登录的具体参数或换它的 Web 导出兜底。
- 若某边开了登录 2FA 且 CLI 登录被拦，同样先保留报错再调整（API key 登录是备选路径）。

## 上云 / 打包容器（已备好 Dockerfile 与 compose）

思路就一句话：**bw 跟脚本一起打进镜像，不在运行时现装。**

- `Dockerfile`：基于 `python:3.12-slim`，从 GitHub 官方 release 下载 bw 二进制
  （当前钉死 **2026.10.0**，含 amd64/arm64 两份 sha256 校验，构建时校验不过就失败），
  不用 npm 装 bw（避开 2026.4.0 那次 npm 投毒的同类风险），版本不浮动、要升手动改。
- 运行时数据全靠 volume（见 `docker-compose.yml`）：`config.json`、
  `bw-sync-state.json`、两边登录态目录 `bw-node/`、`bw-vault/` 挂在宿主机，
  容器重建/升级都不丢。注意 bw 的登录态能持久化、但 session 不能——脚本每次跑都会
  用主密码重新 unlock，所以无人值守时主密码必须从环境注入。
- 密钥只走环境变量：把 `.env.example` 复制为 `.env` 填两边主密码（`chmod 600`、别进仓库），
  compose 用 `env_file` 注入；镜像和 config 里永远不出现密码。
- 无人值守登录：除了主密码，还可以给每边填个人 API key
  （环境变量 `BW_SYNC_NODE_CLIENTID/CLIENTSECRET`、`BW_SYNC_VAULT_*`，Web 端
  设置→安全→API 密钥里查），脚本检测到就优先用 `bw login --apikey` 登录、
  再用主密码 unlock。第一次在云上跑仍建议先只读模式人工盯一遍，
  若被新设备验证/2FA 拦下，先在本地同账号完成一次登录再回来。
- 部署位置：这是个跑完就退的一次性任务容器，宿主机 crontab 定时
  `docker compose run --rm bw-sync` 即可；放 Olares（当普通容器应用跑）或任意 VPS 都行。
  它没法跑在 Cloudflare Workers 上（Workers 里没有能跑 bw 二进制的环境），
  云端那份 NodeWarden 只是被同步的对象，不影响。

构建与首跑：

```bash
docker compose build
docker compose run --rm --entrypoint python3 bw-sync /app/bw_sync.py   # 只读首跑
docker compose run --rm bw-sync                                        # 正式同步
```

注：这份 Dockerfile 在交付环境里没法实际 build（无 Docker），但 bw 2026.10.0 的
Linux 二进制已在同版本环境实测可运行、下载哈希已核对；首次 build 请留意 sha 校验输出。
