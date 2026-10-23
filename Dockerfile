# bw_sync 容器镜像：python + 官方 bw CLI（固定版本、二进制直装，不走 npm）
# bw 版本与 sha256 钉死在下面，升级时改这两处并重新核对哈希。
# 哈希为从 GitHub 官方 release 下载后本地计算所得（官方未随 release 附校验文件）。
FROM python:3.12-slim

ARG BW_VERSION=2026.10.0
ARG TARGETARCH
# TARGETARCH=amd64 时用 x64 包，arm64 时用 arm64 包
ARG BW_SHA256_AMD64=a300959a347bd71ff571da75687c8388da2ecd747a20f0abddd18643eb9466ba
ARG BW_SHA256_ARM64=ea6203a565c48d3107bb8511221bb1e436e06c9bc07d05ba679d8921648e83c9

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

# config.json、bw-sync-state.json、bw-node/、bw-vault/ 都通过 volume 挂进 /app
# 主密码与（可选的）API key 只从环境变量注入，绝不写进镜像
ENTRYPOINT ["python3", "/app/bw_sync.py"]
CMD ["--apply"]
