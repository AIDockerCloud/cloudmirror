# bw_sync 容器镜像：python + 官方 bw CLI（固定版本、二进制直装，不走 npm）
# bw 版本与 sha256 钉死在下面，升级时改这两处并重新核对哈希。
# 哈希为从 GitHub 官方 release 下载后本地计算所得（官方未随 release 附校验文件）。
FROM python:3.12-slim

ARG BW_VERSION=2026.8.0
ARG TARGETARCH
# TARGETARCH=amd64 时用 x64 包，arm64 时用 arm64 包
# 经实测，2026.9.0+ 在 Vaultwarden 上因缺失 key-management 接口触发 KeyIdBackfillError，2026.8.0 兼容性最佳
ARG BW_SHA256_AMD64=d8bbc213d3dbdb701709386af6ea3bd763482f922ae0b538fdc3fdb88b1b1704
ARG BW_SHA256_ARM64=1ad51c5f3c5b597140e6cbbfeff529c2112ce8e3f9a72ad4ef76451be6cb77fe

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && case "$TARGETARCH" in \
         arm64) ASSET="bw-oss-linux-arm64-${BW_VERSION}.zip"; SHA="$BW_SHA256_ARM64" ;; \
         *)     ASSET="bw-oss-linux-${BW_VERSION}.zip";       SHA="$BW_SHA256_AMD64" ;; \
       esac \
    && curl -fsSL -o /tmp/bw.zip \
         "https://github.com/bitwarden/clients/releases/download/cli-v${BW_VERSION}/${ASSET}" \
    && echo "${SHA}  /tmp/bw.zip" | sha256sum -c - \
    && unzip -q /tmp/bw.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/bw \
    && rm /tmp/bw.zip \
    && bw --version

WORKDIR /app
COPY bw_sync.py /app/bw_sync.py
COPY s3_sync.py /app/s3_sync.py
COPY server.py /app/server.py
COPY web /app/web

# config.json、bw-sync-state.json、bw-node/、bw-vault/ 都通过 volume 挂进 /app
# 主密码与（可选的）API key 只从环境变量注入，绝不写进镜像
ENTRYPOINT ["python3", "/app/bw_sync.py"]
CMD ["--apply"]
