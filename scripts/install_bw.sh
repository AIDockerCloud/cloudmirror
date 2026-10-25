#!/usr/bin/env bash
# scripts/install_bw.sh: 安全安装官方 Bitwarden CLI 二进制文件
# 原则：坚决不使用 npm 安装（杜绝 preinstall 供应链投毒风险）；
# 强校验官方 Release SHA-256 指纹；免 root 安装至 ~/.local/bin/bw。

set -euo pipefail

# 经实测，2026.9.0+ 在 Vaultwarden 上会触发 KeyIdBackfillError (404)，2026.8.0 为当前最稳且兼容官方与自建的最佳版本
BW_VERSION="2026.8.0"
BW_SHA256_AMD64="d8bbc213d3dbdb701709386af6ea3bd763482f922ae0b538fdc3fdb88b1b1704"
BW_SHA256_ARM64="1ad51c5f3c5b597140e6cbbfeff529c2112ce8e3f9a72ad4ef76451be6cb77fe"

ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64)
    ASSET="bw-oss-linux-${BW_VERSION}.zip"
    EXPECTED_SHA="$BW_SHA256_AMD64"
    ;;
  aarch64|arm64)
    ASSET="bw-oss-linux-arm64-${BW_VERSION}.zip"
    EXPECTED_SHA="$BW_SHA256_ARM64"
    ;;
  *)
    echo "❌ 不支持的系统架构: $ARCH"
    exit 1
    ;;
esac

DEST_DIR="${HOME}/.local/bin"
mkdir -p "$DEST_DIR"

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

DOWNLOAD_URL="https://github.com/bitwarden/clients/releases/download/cli-v${BW_VERSION}/${ASSET}"

echo "========================================================"
echo "🔒 CloudMirror 安全二进制安装器 (Bitwarden CLI v${BW_VERSION})"
echo "   架构: ${ARCH}"
echo "   来源: GitHub 官方 Release (纯二进制单文件)"
echo "   防投毒策略: 强制校验 SHA-256，跳过 npm 供应链风险"
echo "========================================================"

echo "📥 正在下载官方归档包..."
curl -fsSL -o "${TMP_DIR}/${ASSET}" "$DOWNLOAD_URL"

echo "🔍 正在核对官方 SHA-256 完整性哈希..."
echo "${EXPECTED_SHA}  ${TMP_DIR}/${ASSET}" | sha256sum -c -

echo "📦 正在解压至 ${DEST_DIR}/bw..."
unzip -q -o "${TMP_DIR}/${ASSET}" -d "$DEST_DIR"
chmod +x "${DEST_DIR}/bw"

echo "--------------------------------------------------------"
echo "✅ 安装成功！二进制文件路径: ${DEST_DIR}/bw"
"${DEST_DIR}/bw" --version
echo "========================================================"
