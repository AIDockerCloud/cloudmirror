#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s3_sync.py — 多云 S3 存储与笔记数据同步备份管理器 (零 pip 外部依赖)

功能：
1. S3 兼容对象存储配置管理（含 缤纷云 Bitiful, Cloudflare R2, MinIO, AWS S3, 阿里云 OSS, 腾讯云 COS 等）；
2. 永久持久化笔记标签库管理（支持重命名、唯一性防重名校验、桶关联统计）；
3. 同标签双桶对比与同步：支持选择“主桶 (Primary)”与“备桶 (Backup)”，执行差异比对与只增安全同步；
4. 定时任务调度器：定时自动从主桶同步增量数据到备桶，支持按需触发与启停。
"""

import hmac
import hashlib
import json
import os
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

S3_PROVIDERS = [
    {"id": "Bitiful", "name": "缤纷云 (Bitiful)", "default_endpoint": "https://s3.bitiful.net", "region": "cn-east-1"},
    {"id": "Cloudflare R2", "name": "Cloudflare R2", "default_endpoint": "https://<account_id>.r2.cloudflarestorage.com", "region": "auto"},
    {"id": "MinIO", "name": "MinIO (私有 NAS / Docker)", "default_endpoint": "http://192.168.1.100:9000", "region": "us-east-1"},
    {"id": "AWS S3", "name": "AWS S3", "default_endpoint": "https://s3.amazonaws.com", "region": "us-east-1"},
    {"id": "Tencent COS", "name": "腾讯云 COS", "default_endpoint": "https://cos.ap-guangzhou.myqcloud.com", "region": "ap-guangzhou"},
    {"id": "Aliyun OSS", "name": "阿里云 OSS", "default_endpoint": "https://oss-cn-hangzhou.aliyuncs.com", "region": "oss-cn-hangzhou"},
    {"id": "Backblaze B2", "name": "Backblaze B2", "default_endpoint": "https://s3.us-west-000.backblazeb2.com", "region": "us-west-000"},
    {"id": "Custom S3", "name": "自建 / 其他 S3 兼容服务", "default_endpoint": "https://s3.example.com", "region": "auto"},
]

DEFAULT_NOTE_TAGS = [
    {"id": "tag-obsidian", "name": "Obsidian", "color": "#8b5cf6", "desc": "Remotely Save / LiveSync S3 存储"},
    {"id": "tag-joplin", "name": "Joplin", "color": "#06b6d4", "desc": "Joplin 内置 S3 同步库"},
    {"id": "tag-logseq", "name": "Logseq", "color": "#10b981", "desc": "Logseq 本地图谱 S3 灾备"},
    {"id": "tag-siyuan", "name": "思源笔记", "color": "#f59e0b", "desc": "SiYuan Data/Assets 资产块"},
    {"id": "tag-trilium", "name": "Trilium", "color": "#ec4899", "desc": "Trilium Notes 历史快照"},
    {"id": "tag-notion", "name": "Notion 导出", "color": "#6366f1", "desc": "Notion Markdown/HTML 归档"},
    {"id": "tag-anytype", "name": "Anytype", "color": "#14b8a6", "desc": "Anytype 块存储备份"},
    {"id": "tag-markdown", "name": "通用笔记", "color": "#64748b", "desc": "通用 Markdown 笔记库"},
]


class S3Error(Exception):
    """S3 协议请求异常（包含 HTTP 状态码与远端 XML 错误信息）"""
    def __init__(self, message: str, status_code: Optional[int] = None, error_code: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


def _clean_xml_tag(tag: str) -> str:
    """去除 XML 标签的命名空间前缀"""
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_s3_error_xml(xml_bytes: bytes) -> Tuple[str, str]:
    """从 S3 错误 XML 响应中解析 Code 与 Message"""
    code = ""
    message = ""
    try:
        root = ET.fromstring(xml_bytes)
        for elem in root.iter():
            name = _clean_xml_tag(elem.tag)
            if name == "Code":
                code = (elem.text or "").strip()
            elif name == "Message":
                message = (elem.text or "").strip()
    except Exception:
        pass
    return code, message


class RealS3Client:
    """
    基于 Python 3 原生标准库实现的轻量级 S3 客户端 (零 pip 外部依赖)
    严格遵循 AWS SigV4 认证规范，支持 ListObjectsV2 分页遍历、GetObject、PutObject、HeadObject
    """
    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str = "",
        secret_key: str = "",
        region: str = "us-east-1",
        ssl_verify: bool = True,
        timeout: int = 30
    ):
        self.endpoint = endpoint.strip().rstrip("/")
        self.bucket = bucket.strip().strip("/")
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()
        reg = (region.strip() or "us-east-1").lower()
        self.region = reg
        self.ssl_verify = ssl_verify
        self.timeout = timeout

    def is_configured(self) -> bool:
        """检查凭据与存储桶是否完整配置且非演示掩码"""
        if not self.endpoint or not self.bucket or not self.access_key or not self.secret_key:
            return False
        if "••••" in self.secret_key or "••••" in self.access_key:
            return False
        # 排除演示假 Key
        if "example" in self.access_key.lower() or "admin_user" in self.access_key.lower():
            return False
        return True

    def _sign_headers(
        self,
        method: str,
        path: str,
        query_params: Optional[Dict[str, str]] = None,
        payload: bytes = b"",
        extra_headers: Optional[Dict[str, str]] = None,
        payload_hash_override: Optional[str] = None
    ) -> Dict[str, str]:
        """
        按照 AWS Signature Version 4 (SigV4) 规范计算生成认证请求头
        """
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        parsed = urllib.parse.urlsplit(self.endpoint)
        host = parsed.netloc

        if payload_hash_override:
            payload_hash = payload_hash_override
        else:
            payload_hash = hashlib.sha256(payload).hexdigest()

        # 1. Canonical URI
        clean_path = path.strip("/")
        if clean_path:
            encoded_segments = [urllib.parse.quote(seg, safe="") for seg in clean_path.split("/")]
            canonical_uri = "/" + "/".join(encoded_segments)
        else:
            canonical_uri = "/"

        # 2. Canonical Query String (ASCII 字典序排序)
        if query_params:
            sorted_items = sorted(
                (urllib.parse.quote(k, safe="~"), urllib.parse.quote(str(v), safe="~"))
                for k, v in query_params.items()
            )
            canonical_querystring = "&".join(f"{k}={v}" for k, v in sorted_items)
        else:
            canonical_querystring = ""

        # 3. Canonical Headers 与 Signed Headers
        headers = {
            "host": host,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if extra_headers:
            for k, v in extra_headers.items():
                headers[k.lower().strip()] = str(v).strip()

        sorted_headers = sorted(headers.items())
        canonical_headers = "".join(f"{k}:{v}\n" for k, v in sorted_headers)
        signed_headers = ";".join(k for k, _ in sorted_headers)

        # 4. Canonical Request
        canonical_request = (
            f"{method.upper()}\n"
            f"{canonical_uri}\n"
            f"{canonical_querystring}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{payload_hash}"
        )

        # 5. String to Sign
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = (
            f"{algorithm}\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

        # 6. 派生 HMAC 签名密钥
        def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
            return hmac.new(key, msg, hashlib.sha256).digest()

        k_date = _hmac_sha256(b"AWS4" + self.secret_key.encode("utf-8"), date_stamp.encode("utf-8"))
        k_region = _hmac_sha256(k_date, self.region.encode("utf-8"))
        k_service = _hmac_sha256(k_region, b"s3")
        k_signing = _hmac_sha256(k_service, b"aws4_request")

        # 7. 计算 Signature
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        # 8. 构造 Authorization 报头
        auth_header = (
            f"{algorithm} "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        out_headers = {
            "Host": host,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
            "Authorization": auth_header,
        }
        if extra_headers:
            for k, v in extra_headers.items():
                out_headers[k] = str(v)

        return out_headers

    def _build_url_and_path(self, path_suffix: str = "", query_params: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
        parsed = urllib.parse.urlsplit(self.endpoint)
        base_path = parsed.path.rstrip("/")
        if path_suffix:
            full_path = f"{base_path}/{self.bucket}/{path_suffix.lstrip('/')}"
        else:
            full_path = f"{base_path}/{self.bucket}"

        query_str = ""
        if query_params:
            sorted_items = sorted(
                (urllib.parse.quote(k, safe="~"), urllib.parse.quote(str(v), safe="~"))
                for k, v in query_params.items()
            )
            query_str = "?" + "&".join(f"{k}={v}" for k, v in sorted_items)

        url = f"{parsed.scheme}://{parsed.netloc}{full_path}{query_str}"
        return url, full_path

    def _request(
        self,
        method: str,
        path_suffix: str = "",
        query_params: Optional[Dict[str, str]] = None,
        payload: bytes = b"",
        extra_headers: Optional[Dict[str, str]] = None
    ) -> Tuple[int, bytes, Dict[str, str]]:
        if not self.is_configured():
            raise S3Error("S3 客户端未配置有效凭据或存储桶")

        url, req_path = self._build_url_and_path(path_suffix, query_params)
        headers = self._sign_headers(method, req_path, query_params, payload, extra_headers)

        req = urllib.request.Request(
            url=url,
            data=payload if method.upper() in ("PUT", "POST") else None,
            headers=headers,
            method=method.upper()
        )

        ctx = None
        if url.startswith("https://") and not self.ssl_verify:
            ctx = ssl._create_unverified_context()

        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                status = resp.status
                body = resp.read()
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return status, body, resp_headers
        except urllib.error.HTTPError as e:
            err_body = e.read()
            code, msg = _parse_s3_error_xml(err_body)
            err_text = f"HTTP {e.code} ({code or e.reason}): {msg or err_body.decode('utf-8', errors='replace')[:200]}"
            raise S3Error(err_text, status_code=e.code, error_code=code)
        except urllib.error.URLError as e:
            raise S3Error(f"网络连接失败: {e.reason}")
        except Exception as e:
            raise S3Error(f"请求发生异常: {str(e)}")

    def test_connection(self) -> Dict[str, Any]:
        """连通性与权限探测：列出首批对象并统计容量"""
        objects = self.list_objects(max_keys=100, paginate=False)
        total_size = sum(o["size"] for o in objects)
        return {
            "connected": True,
            "objects_count": len(objects),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }

    def list_objects(self, prefix: str = "", max_keys: int = 1000, paginate: bool = True) -> List[Dict[str, Any]]:
        """
        基于 ListObjectsV2 协议遍历存储桶对象，支持 ContinuationToken 翻页
        """
        all_objects = []
        continuation_token = None

        while True:
            query = {
                "list-type": "2",
                "max-keys": str(max_keys)
            }
            if prefix:
                query["prefix"] = prefix
            if continuation_token:
                query["continuation-token"] = continuation_token

            status, body, headers = self._request("GET", path_suffix="", query_params=query)

            root = ET.fromstring(body)
            is_truncated = False
            next_token = None

            for child in root:
                name = _clean_xml_tag(child.tag)
                if name == "IsTruncated":
                    is_truncated = (child.text or "").strip().lower() == "true"
                elif name == "NextContinuationToken":
                    next_token = (child.text or "").strip()
                elif name == "Contents":
                    obj = {"key": "", "size": 0, "etag": "", "last_modified": ""}
                    for prop in child:
                        pname = _clean_xml_tag(prop.tag)
                        if pname == "Key":
                            obj["key"] = prop.text or ""
                        elif pname == "Size":
                            try:
                                obj["size"] = int(prop.text or 0)
                            except ValueError:
                                obj["size"] = 0
                        elif pname == "ETag":
                            obj["etag"] = (prop.text or "").strip('"')
                        elif pname == "LastModified":
                            obj["last_modified"] = prop.text or ""
                    if obj["key"]:
                        all_objects.append(obj)

            if not paginate or not is_truncated or not next_token:
                break
            continuation_token = next_token

        return all_objects

    def get_object(self, key: str) -> Tuple[bytes, str]:
        """获取对象二进制数据与 Content-Type"""
        status, body, headers = self._request("GET", path_suffix=key)
        content_type = headers.get("content-type", "application/octet-stream")
        return body, content_type

    def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """上传对象二进制数据，返回 ETag"""
        extra = {"content-type": content_type}
        status, body, headers = self._request("PUT", path_suffix=key, payload=data, extra_headers=extra)
        etag = headers.get("etag", "").strip('"')
        return etag

    def head_object(self, key: str) -> Dict[str, Any]:
        """获取对象元数据（大小、ETag 等）"""
        status, body, headers = self._request("HEAD", path_suffix=key)
        return {
            "size": int(headers.get("content-length", 0)),
            "etag": headers.get("etag", "").strip('"'),
            "content_type": headers.get("content-type", "application/octet-stream"),
            "last_modified": headers.get("last-modified", ""),
        }

    def transfer_to(
        self,
        key: str,
        target_client: "RealS3Client",
        target_key: str,
        max_retries: int = 3,
        chunk_size: int = 64 * 1024
    ) -> Tuple[int, str]:
        """
        流式对象直传（带 8MB 内存缓冲区/溢出临时文件落盘与指数退避重试）：
        避免整包 bytearray 暴涨引发 OOM，抗网络抖动。
        返回 (transferred_bytes, target_etag)。
        """
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                # 1. 发起 GET 请求
                get_url, get_path = self._build_url_and_path(path_suffix=key)
                get_headers = self._sign_headers("GET", get_path)
                get_req = urllib.request.Request(url=get_url, headers=get_headers, method="GET")
                get_ctx = ssl._create_unverified_context() if (get_url.startswith("https://") and not self.ssl_verify) else None

                with urllib.request.urlopen(get_req, timeout=self.timeout, context=get_ctx) as resp:
                    content_type = resp.headers.get("content-type", "application/octet-stream")
                    # 使用 SpooledTemporaryFile，8MB 以内驻留内存，超 8MB 自动缓冲落盘
                    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as spool:
                        hasher = hashlib.sha256()
                        total_bytes = 0
                        while True:
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            spool.write(chunk)
                            hasher.update(chunk)
                            total_bytes += len(chunk)

                        spool.seek(0)
                        sha256_hex = hasher.hexdigest()

                        # 2. 上传至目标端
                        target_url, target_path = target_client._build_url_and_path(path_suffix=target_key)
                        extra = {
                            "content-type": content_type,
                            "content-length": str(total_bytes)
                        }
                        target_headers = target_client._sign_headers(
                            "PUT",
                            target_path,
                            payload=b"",
                            extra_headers=extra,
                            payload_hash_override=sha256_hex
                        )
                        put_req = urllib.request.Request(
                            url=target_url,
                            data=spool,
                            headers=target_headers,
                            method="PUT"
                        )
                        put_ctx = ssl._create_unverified_context() if (target_url.startswith("https://") and not target_client.ssl_verify) else None
                        with urllib.request.urlopen(put_req, timeout=target_client.timeout, context=put_ctx) as put_resp:
                            etag = put_resp.headers.get("etag", "").strip('"')
                            return total_bytes, etag
            except urllib.error.HTTPError as e:
                err_body = e.read()
                code, msg = _parse_s3_error_xml(err_body)
                last_exc = S3Error(f"HTTP {e.code} ({code or e.reason}): {msg or err_body.decode('utf-8', errors='replace')[:200]}", status_code=e.code, error_code=code)
            except urllib.error.URLError as e:
                last_exc = S3Error(f"网络连接失败: {e.reason}")
            except Exception as e:
                last_exc = S3Error(f"传输异常: {str(e)}")

            if attempt < max_retries:
                time.sleep(0.5 * (2 ** (attempt - 1)))

        raise last_exc or S3Error("传输失败且达到最大重试次数")




class TagManager:
    """永久管理笔记软件标签，支持修改名称、防重名校验"""

    def __init__(self, storage_file: Path):
        self.storage_file = storage_file
        self._tags: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if self.storage_file.exists():
            try:
                data = json.loads(self.storage_file.read_text(encoding="utf-8"))
                self._tags = data.get("tags", [])
                return
            except Exception:
                pass
        self._tags = list(DEFAULT_NOTE_TAGS)
        self.save()

    def save(self) -> None:
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"tags": self._tags}
        self.storage_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_tags(self, sources_manager=None) -> List[Dict[str, Any]]:
        result = []
        for t in self._tags:
            tag_copy = dict(t)
            if sources_manager:
                tag_name = tag_copy["name"]
                count = sum(1 for s in sources_manager._sources if tag_name in s.get("tags", []))
                tag_copy["bucket_count"] = count
            else:
                tag_copy["bucket_count"] = 0
            result.append(tag_copy)
        return result

    def get_tag_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        clean = name.strip().casefold()
        for t in self._tags:
            if t["name"].strip().casefold() == clean:
                return dict(t)
        return None

    def add_tag(self, name: str, color: str = "#8b5cf6", desc: str = "") -> Dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("标签名称不能为空")

        # 重名校验
        if self.get_tag_by_name(clean_name):
            raise ValueError(f"标签名称 [{clean_name}] 已存在，不能重名")

        tag_id = f"tag-{uuid.uuid4().hex[:8]}"
        new_tag = {
            "id": tag_id,
            "name": clean_name,
            "color": color or "#8b5cf6",
            "desc": desc.strip(),
        }
        self._tags.append(new_tag)
        self.save()
        return new_tag

    def update_tag(self, tag_id: str, new_name: str, color: Optional[str] = None, desc: Optional[str] = None, sources_manager=None) -> Dict[str, Any]:
        clean_name = new_name.strip()
        if not clean_name:
            raise ValueError("标签名称不能为空")

        target = None
        for t in self._tags:
            if t["id"] == tag_id:
                target = t
                break
        if not target:
            raise ValueError(f"未找到标签 ID: {tag_id}")

        # 检查是否与其他标签重名
        for t in self._tags:
            if t["id"] != tag_id and t["name"].strip().casefold() == clean_name.casefold():
                raise ValueError(f"标签名称 [{clean_name}] 已存在，不能重名")

        old_name = target["name"]
        target["name"] = clean_name
        if color:
            target["color"] = color
        if desc is not None:
            target["desc"] = desc.strip()
        self.save()

        # 级联更新所有引用了此标签的 S3 桶
        if sources_manager and old_name != clean_name:
            sources_manager.cascade_rename_tag(old_name, clean_name)

        return target

    def delete_tag(self, tag_id: str, sources_manager=None) -> bool:
        target = next((t for t in self._tags if t["id"] == tag_id), None)
        if not target:
            return False
        tag_name = target["name"]
        self._tags = [t for t in self._tags if t["id"] != tag_id]
        self.save()
        if sources_manager:
            sources_manager.cascade_remove_tag(tag_name)
        return True


class S3SourceManager:
    """管理 S3 数据源与同标签主备桶同步"""

    def __init__(self, storage_file: Path, tag_manager: TagManager):
        self.storage_file = storage_file
        self.tag_manager = tag_manager
        self._sources: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if self.storage_file.exists():
            try:
                data = json.loads(self.storage_file.read_text(encoding="utf-8"))
                sources = data.get("s3_sources", [])
                # Ensure Bitiful seed sources are merged if not present
                if not any("Bitiful" in s.get("provider", "") or "缤纷云" in s.get("provider", "") for s in sources):
                    seed = self._get_initial_seed()
                    sources.extend([s for s in seed if "缤纷云" in s.get("provider", "")])
                    data["s3_sources"] = sources
                    self.storage_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                now = datetime.now(timezone.utc)
                defaults_days = {
                    "s3-obsidian-r2": 15,
                    "s3-obsidian-bitiful": 68,
                    "s3-joplin-minio": 105,
                    "s3-joplin-bitiful": 10,
                    "s3-logseq-aws": 40,
                    "s3-siyuan-cos": 25,
                }
                for s in sources:
                    if not s.get("password_updated_at"):
                        d = defaults_days.get(s.get("id"), 15)
                        s["password_updated_at"] = (now - timedelta(days=d)).isoformat()
                self._sources = sources
                return
            except Exception:
                pass
        self._sources = self._get_initial_seed()
        self.save()

    def save(self) -> None:
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"s3_sources": self._sources}
        self.storage_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _get_initial_seed(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "s3-obsidian-r2",
                "name": "Obsidian 主笔记库 (Cloudflare R2) [DEMO]",
                "provider": "Cloudflare R2",
                "endpoint": "https://a1b2c3d4e5.r2.cloudflarestorage.com",
                "region": "auto",
                "bucket": "my-obsidian-vault",
                "prefix": "vaults/main/",
                "access_key": "248a8f902b934c890123",
                "secret_key": "••••••••••••••••••••••••••••••••",
                "tags": ["Obsidian"],
                "status": "demo",
                "objects_count": 1842,
                "total_size_mb": 348.6,
                "last_sync": "未同步 (DEMO演示)",
                "ssl": True,
            },
            {
                "id": "s3-obsidian-bitiful",
                "name": "Obsidian 异地备库 (缤纷云 Bitiful) [DEMO]",
                "provider": "缤纷云 (Bitiful)",
                "endpoint": "https://s3.bitiful.net",
                "region": "cn-east-1",
                "bucket": "obsidian-backup-vault",
                "prefix": "vaults/main/",
                "access_key": "btf_ak_981240182",
                "secret_key": "••••••••••••••••••••••••••••••••",
                "tags": ["Obsidian"],
                "status": "demo",
                "objects_count": 1838,
                "total_size_mb": 346.2,
                "last_sync": "未同步 (DEMO演示)",
                "ssl": True,
            },
            {
                "id": "s3-joplin-minio",
                "name": "Joplin 私有NAS主库 (MinIO) [DEMO]",
                "provider": "MinIO",
                "endpoint": "http://192.168.1.120:9000",
                "region": "us-east-1",
                "bucket": "joplin-sync",
                "prefix": "joplin/",
                "access_key": "minio_admin_user",
                "secret_key": "••••••••••••••••••••••••••••••••",
                "tags": ["Joplin"],
                "status": "demo",
                "objects_count": 3290,
                "total_size_mb": 912.4,
                "last_sync": "未同步 (DEMO演示)",
                "ssl": False,
            },
            {
                "id": "s3-joplin-bitiful",
                "name": "Joplin 云端冷备桶 (缤纷云 Bitiful) [DEMO]",
                "provider": "缤纷云 (Bitiful)",
                "endpoint": "https://s3.bitiful.net",
                "region": "cn-east-1",
                "bucket": "joplin-cold-replica",
                "prefix": "joplin/",
                "access_key": "btf_ak_981240182",
                "secret_key": "••••••••••••••••••••••••••••••••",
                "tags": ["Joplin"],
                "status": "demo",
                "objects_count": 3285,
                "total_size_mb": 910.1,
                "last_sync": "未同步 (DEMO演示)",
                "ssl": True,
            },
            {
                "id": "s3-logseq-aws",
                "name": "Logseq 异地容灾冷备 (AWS S3) [DEMO]",
                "provider": "AWS S3",
                "endpoint": "https://s3.ap-northeast-1.amazonaws.com",
                "region": "ap-northeast-1",
                "bucket": "personal-logseq-coldbackup",
                "prefix": "logseq-graph/",
                "access_key": "AKIA2EXAMPLEKEY999",
                "secret_key": "••••••••••••••••••••••••••••••••",
                "tags": ["Logseq"],
                "status": "demo",
                "objects_count": 765,
                "total_size_mb": 154.2,
                "last_sync": "未同步 (DEMO演示)",
                "ssl": True,
            },
            {
                "id": "s3-siyuan-cos",
                "name": "思源笔记多端块存储 (腾讯云 COS) [DEMO]",
                "provider": "Tencent COS",
                "endpoint": "https://cos.ap-guangzhou.myqcloud.com",
                "region": "ap-guangzhou",
                "bucket": "siyuan-blocks-1250000000",
                "prefix": "data/",
                "access_key": "AKID9examplecoskey01",
                "secret_key": "••••••••••••••••••••••••••••••••",
                "tags": ["思源笔记"],
                "status": "demo",
                "objects_count": 4890,
                "total_size_mb": 1420.0,
                "last_sync": "未同步 (DEMO演示)",
                "ssl": True,
            },
        ]

    def get_credentials(self, src: Dict[str, Any]) -> Tuple[str, str]:
        """解析存储源凭据，优先从环境变量读取"""
        ak = ""
        sk = ""
        ak_env = src.get("access_key_env")
        sk_env = src.get("secret_key_env")
        if ak_env and os.environ.get(ak_env):
            ak = os.environ[ak_env].strip()
        if sk_env and os.environ.get(sk_env):
            sk = os.environ[sk_env].strip()

        if not ak:
            ak = str(src.get("access_key", "")).strip()
        if not sk:
            sk = str(src.get("secret_key", "")).strip()
        return ak, sk

    def get_client(self, src: Dict[str, Any]) -> RealS3Client:
        """根据数据源配置构造原生 S3 客户端"""
        ak, sk = self.get_credentials(src)
        return RealS3Client(
            endpoint=src.get("endpoint", ""),
            bucket=src.get("bucket", ""),
            access_key=ak,
            secret_key=sk,
            region=src.get("region", "us-east-1"),
            ssl_verify=bool(src.get("ssl", True)),
        )

    def is_real_configured(self, src: Dict[str, Any]) -> bool:
        """检查数据源是否已配置真实有效凭据"""
        client = self.get_client(src)
        return client.is_configured()

    def list_sources(self, tag_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        sources = self._sources
        if tag_filter and tag_filter != "all":
            sources = [s for s in sources if tag_filter.lower() in [t.lower() for t in s.get("tags", [])]]
        safe_sources = []
        for s in sources:
            item = dict(s)
            ak_env = item.get("access_key_env")
            sk_env = item.get("secret_key_env")
            has_env = bool(ak_env and os.environ.get(ak_env) and sk_env and os.environ.get(sk_env))
            item["has_env_credentials"] = has_env
            item["is_real_configured"] = self.is_real_configured(s)

            sk = item.get("secret_key", "")
            if has_env:
                item["access_key"] = f"[ENV: {ak_env}]"
                item["secret_key"] = f"•••••••• [ENV: {sk_env}]"
            elif sk and not sk.startswith("••"):
                item["secret_key"] = f"••••••••••••{sk[-4:] if len(sk) >= 4 else '****'}"
            safe_sources.append(item)
        return safe_sources

    def get_sources_by_tag(self, tag_name: str) -> List[Dict[str, Any]]:
        clean = tag_name.strip().casefold()
        return [
            s for s in self.list_sources()
            if any(t.strip().casefold() == clean for t in s.get("tags", []))
        ]

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        for s in self._sources:
            if s.get("id") == source_id:
                return dict(s)
        return None

    def add_source(self, data: Dict[str, Any]) -> Dict[str, Any]:
        source_id = data.get("id") or f"s3-{uuid.uuid4().hex[:12]}"
        tags = data.get("tags", ["Obsidian"])
        new_source = {
            "id": source_id,
            "name": data.get("name", "未命名 S3 存储"),
            "provider": data.get("provider", "缤纷云 (Bitiful)"),
            "endpoint": data.get("endpoint", "").strip(),
            "region": data.get("region", "auto").strip(),
            "bucket": data.get("bucket", "").strip(),
            "prefix": data.get("prefix", "").strip(),
            "access_key": data.get("access_key", "").strip(),
            "secret_key": data.get("secret_key", "").strip(),
            "access_key_env": data.get("access_key_env", "").strip(),
            "secret_key_env": data.get("secret_key_env", "").strip(),
            "password_updated_at": data.get("password_updated_at") or datetime.now(timezone.utc).isoformat(),
            "tags": tags,
            "status": "connected" if self.is_real_configured(data) else "demo",
            "objects_count": data.get("objects_count", 0),
            "total_size_mb": data.get("total_size_mb", 0.0),
            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "ssl": bool(data.get("ssl", True)),
        }
        self._sources.append(new_source)
        self.save()
        return new_source

    def update_source(self, source_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for i, s in enumerate(self._sources):
            if s.get("id") == source_id:
                sk = data.get("secret_key")
                old_sk = str(s.get("secret_key", "")).strip()
                password_changed = False

                # 精确比对 S3 密钥是否被真实改动，避免掩码或未改动时误重置生命周期
                if sk and not str(sk).strip().startswith("••") and str(sk).strip() != old_sk:
                    data["secret_key"] = str(sk).strip()
                    data["password_updated_at"] = datetime.now(timezone.utc).isoformat()
                    password_changed = True
                else:
                    data["secret_key"] = old_sk
                    # 密钥未变更：保留原时间戳，绝不误判重置
                    data["password_updated_at"] = s.get("password_updated_at") or datetime.now(timezone.utc).isoformat()

                if "access_key_env" in data:
                    data["access_key_env"] = data["access_key_env"].strip()
                if "secret_key_env" in data:
                    data["secret_key_env"] = data["secret_key_env"].strip()

                self._sources[i].update(data)
                if self.is_real_configured(self._sources[i]):
                    self._sources[i]["status"] = "connected"
                self.save()
                res = dict(self._sources[i])
                res["password_changed"] = password_changed
                return res
        return None

    def delete_source(self, source_id: str) -> bool:
        init_len = len(self._sources)
        self._sources = [s for s in self._sources if s.get("id") != source_id]
        if len(self._sources) < init_len:
            self.save()
            return True
        return False

    def cascade_rename_tag(self, old_name: str, new_name: str) -> None:
        changed = False
        for s in self._sources:
            tags = s.get("tags", [])
            new_tags = []
            for t in tags:
                if t.strip().casefold() == old_name.strip().casefold():
                    new_tags.append(new_name)
                    changed = True
                else:
                    new_tags.append(t)
            s["tags"] = new_tags
        if changed:
            self.save()

    def cascade_remove_tag(self, tag_name: str) -> None:
        changed = False
        for s in self._sources:
            tags = s.get("tags", [])
            filtered = [t for t in tags if t.strip().casefold() != tag_name.strip().casefold()]
            if len(filtered) != len(tags):
                s["tags"] = filtered
                changed = True
        if changed:
            self.save()

    def test_connection(self, source_id: str) -> Dict[str, Any]:
        src = self.get_source(source_id)
        if not src:
            return {"success": False, "is_demo": True, "message": f"未找到 S3 数据源 {source_id}"}
        endpoint = src.get("endpoint", "")
        bucket = src.get("bucket", "")
        if not endpoint or not bucket:
            return {"success": False, "is_demo": True, "message": "Endpoint 或 Bucket 为空"}

        if not self.is_real_configured(src):
            return {
                "success": True,
                "is_demo": True,
                "latency_ms": 36,
                "message": f"【DEMO 演示模式】已模拟连通响应（注意：当前 S3 模块处于原型演示阶段，底层尚未配置有效真实密钥，未发起实际 SigV4 网络请求）",
                "bucket_info": {
                    "name": bucket,
                    "objects": src.get("objects_count", 1024),
                    "size_mb": src.get("total_size_mb", 256.0),
                    "tags": src.get("tags", []),
                }
            }

        client = self.get_client(src)
        start_t = time.time()
        try:
            info = client.test_connection()
            latency = int((time.time() - start_t) * 1000)
            for s in self._sources:
                if s.get("id") == source_id:
                    s["status"] = "connected"
                    s["objects_count"] = info["objects_count"]
                    s["total_size_mb"] = info["total_size_mb"]
                    s["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.save()
            return {
                "success": True,
                "is_demo": False,
                "latency_ms": latency,
                "message": f"真实 S3 连通成功 ({src.get('provider')})，共探测到 {info['objects_count']} 个对象",
                "bucket_info": {
                    "name": bucket,
                    "objects": info["objects_count"],
                    "size_mb": info["total_size_mb"],
                    "tags": src.get("tags", []),
                }
            }
        except Exception as e:
            latency = int((time.time() - start_t) * 1000)
            return {
                "success": False,
                "is_demo": False,
                "latency_ms": latency,
                "message": f"S3 真实连通探测失败: {str(e)}"
            }

    def compare_pair(self, primary_id: str, backup_id: str, tag: str = "") -> Dict[str, Any]:
        """同标签下对主桶与备桶进行数据差异比对"""
        pri = self.get_source(primary_id)
        bak = self.get_source(backup_id)
        if not pri or not bak:
            return {"success": False, "is_demo": True, "message": "主桶或备桶不存在"}

        # 如果主桶与备桶未同时配置真实有效密钥，回退至 DEMO 演算模式
        if not (self.is_real_configured(pri) and self.is_real_configured(bak)):
            pri_count = pri.get("objects_count", 1842)
            bak_count = bak.get("objects_count", 1838)
            diff_count = max(0, pri_count - bak_count)
            if diff_count == 0:
                diff_count = 4

            mock_diff = {
                "success": True,
                "is_demo": True,
                "demo_warning": "⚠️ 警告：当前 S3 差异对比处于 DEMO 演算模式，未遍历真实远程 S3 存储桶！",
                "tag": tag or (pri.get("tags", ["未命名"])[0]),
                "strategy": "safe_add_only (DEMO)",
                "primary": {"id": pri["id"], "name": pri["name"], "bucket": pri["bucket"], "objects_count": pri_count},
                "backup": {"id": bak["id"], "name": bak["name"], "bucket": bak["bucket"], "objects_count": bak_count},
                "identical_count": min(pri_count, bak_count),
                "to_sync_count": diff_count,
                "retained_count": 0,
                "conflict_count": 0,
                "tombstone_count": 0,
                "sample_pending_files": [
                    f"{pri.get('prefix', '')}2026/10/今日工作日志.md (新增待同步·演示)",
                    f"{pri.get('prefix', '')}assets/架构拓扑图-v2.png (增量资产·演示)",
                    f"{pri.get('prefix', '')}kanban/项目迭代进度.md (主桶已更新·演示)",
                    f"{pri.get('prefix', '')}templates/周报模板.md (待补齐到备桶·演示)",
                ][:diff_count],
                "pending_details": [],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            return mock_diff

        # 真实跨桶 S3 比对
        try:
            pri_client = self.get_client(pri)
            bak_client = self.get_client(bak)

            pri_prefix = pri.get("prefix", "").strip().lstrip("/")
            bak_prefix = bak.get("prefix", "").strip().lstrip("/")

            pri_objects = pri_client.list_objects(prefix=pri_prefix)
            bak_objects = bak_client.list_objects(prefix=bak_prefix)

            # 以相对路径建索引映射
            pri_map = {}
            for o in pri_objects:
                key = o["key"]
                if pri_prefix and key.startswith(pri_prefix):
                    rel = key[len(pri_prefix):].lstrip("/")
                else:
                    rel = key
                if rel:
                    pri_map[rel] = o

            bak_map = {}
            for o in bak_objects:
                key = o["key"]
                if bak_prefix and key.startswith(bak_prefix):
                    rel = key[len(bak_prefix):].lstrip("/")
                else:
                    rel = key
                if rel:
                    bak_map[rel] = o

            def _build_bak_key(rel_path: str) -> str:
                if bak_prefix:
                    return f"{bak_prefix.rstrip('/')}/{rel_path}"
                return rel_path

            # 判定是否为思源笔记标签
            target_tag = tag or (pri.get("tags", [""])[0])
            is_siyuan = ("思源" in target_tag or "siyuan" in target_tag.lower())

            def is_siyuan_chunk(rel_path: str) -> bool:
                """思源笔记仅 data/ 目录下的 .sy 块文件为不可变哈希寻址块"""
                clean = rel_path.strip().lower()
                return clean.startswith("data/") and clean.endswith(".sy")

            def is_siyuan_pointer(rel_path: str) -> bool:
                """思源笔记指针、清单与快照类关键引用文件"""
                name = rel_path.rsplit("/", 1)[-1].lower()
                return name in ("latest", "manifest.json", "index.json", "sync.json") or name.endswith(".pointer") or "/conf/" in rel_path

            identical = []
            to_sync = []
            retained = [] # 仅在备桶存在的孤立对象（零硬删除，冷备安全保留）

            for rel, pri_item in pri_map.items():
                target_key = _build_bak_key(rel)
                bak_item = bak_map.get(rel)
                if not bak_item:
                    to_sync.append({
                        "rel_path": rel,
                        "pri_key": pri_item["key"],
                        "bak_key": target_key,
                        "reason": "missing_on_backup",
                        "size": pri_item["size"],
                    })
                elif is_siyuan:
                    # 思源笔记不可变块存储逻辑：
                    # 1) 仅 data/ 下的 .sy 哈希块享受“同大小即相同”不可变优化；
                    # 2) 其余非块路径（latest、assets/ 附件、manifest、conf 等）必须通过大小 + ETag 校验！
                    if is_siyuan_chunk(rel):
                        if pri_item["size"] == bak_item["size"]:
                            identical.append(rel)
                        else:
                            to_sync.append({
                                "rel_path": rel,
                                "pri_key": pri_item["key"],
                                "bak_key": target_key,
                                "reason": "modified_size_mismatch",
                                "size": pri_item["size"],
                            })
                    else:
                        if pri_item["size"] == bak_item["size"] and (not pri_item.get("etag") or not bak_item.get("etag") or pri_item["etag"] == bak_item["etag"]):
                            identical.append(rel)
                        else:
                            to_sync.append({
                                "rel_path": rel,
                                "pri_key": pri_item["key"],
                                "bak_key": target_key,
                                "reason": "modified_non_chunk",
                                "size": pri_item["size"],
                            })
                else:
                    # 通用文件比对：大小与 ETag 一致跳过；否则待同步
                    if pri_item["size"] == bak_item["size"] and (not pri_item.get("etag") or not bak_item.get("etag") or pri_item["etag"] == bak_item["etag"]):
                        identical.append(rel)
                    else:
                        to_sync.append({
                            "rel_path": rel,
                            "pri_key": pri_item["key"],
                            "bak_key": target_key,
                            "reason": "modified",
                            "size": pri_item["size"],
                        })

            for rel in bak_map:
                if rel not in pri_map:
                    retained.append(rel)

            if is_siyuan:
                # 关键排序保证：数据块排在最前面传输，指针与清单文件（如 latest, manifest）强制排在最后传输！
                to_sync.sort(key=lambda x: (1 if is_siyuan_pointer(x["rel_path"]) else 0, x["rel_path"]))

            strategy_name = "siyuan_block_mirror" if is_siyuan else "safe_add_only"

            return {
                "success": True,
                "is_demo": False,
                "tag": target_tag,
                "strategy": strategy_name,
                "is_siyuan": is_siyuan,
                "primary": {"id": pri["id"], "name": pri["name"], "bucket": pri["bucket"], "objects_count": len(pri_objects)},
                "backup": {"id": bak["id"], "name": bak["name"], "bucket": bak["bucket"], "objects_count": len(bak_objects)},
                "identical_count": len(identical),
                "to_sync_count": len(to_sync),
                "retained_count": len(retained),
                "conflict_count": 0,
                "tombstone_count": 0,
                "sample_pending_files": [item["rel_path"] for item in to_sync[:20]],
                "pending_details": to_sync,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            return {
                "success": False,
                "is_demo": False,
                "message": f"真实 S3 比对失败: {str(e)}"
            }

    def sync_pair(self, primary_id: str, backup_id: str, tag: str = "", apply: bool = True, strategy: str = "safe_add_only") -> Dict[str, Any]:
        """从主桶向备桶执行数据同步"""
        comp = self.compare_pair(primary_id, backup_id, tag)
        if not comp.get("success"):
            return comp

        pri = comp["primary"]
        bak = comp["backup"]
        to_sync = comp["to_sync_count"]

        # DEMO 模式分支
        if comp.get("is_demo"):
            logs = [
                f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️【DEMO 演示模式警告】当前 S3 模块处于原型演示阶段，未建立真实网络连接，未同步任何实际远端对象！严禁视作真实备份依据！",
                f"[{datetime.now().strftime('%H:%M:%S')}] 启动同标签主备桶演示同步 (标签: {comp['tag']})",
                f"[{datetime.now().strftime('%H:%M:%S')}] 主桶 (Source): {pri['name']} ({pri['bucket']})",
                f"[{datetime.now().strftime('%H:%M:%S')}] 备桶 (Target): {bak['name']} ({bak['bucket']})",
                f"[{datetime.now().strftime('%H:%M:%S')}] 策略: {strategy} (演示模式严格只增不改不删)",
                f"[{datetime.now().strftime('%H:%M:%S')}] 模拟扫描对象: 相同对象 {comp['identical_count']} 个，待同步增量 {to_sync} 个",
            ]
            if apply:
                for f in comp["sample_pending_files"]:
                    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] -> 模拟写入备桶: {f}")
                logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ℹ️ [DEMO 演算完成] 模拟写入流程已结束（未发生实际远程对象传输）。")
                for s in self._sources:
                    if s["id"] == backup_id:
                        s["objects_count"] = pri["objects_count"]
                        s["last_sync"] = "未同步 (DEMO演示)"
                    elif s["id"] == primary_id:
                        s["last_sync"] = "未同步 (DEMO演示)"
                self.save()
            else:
                logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] （DEMO 只读演算预览模式，未发生任何写入）")

            return {
                "success": True,
                "status": "success",
                "is_demo": True,
                "mode": "apply" if apply else "dry-run",
                "tag": comp["tag"],
                "strategy": comp.get("strategy", strategy),
                "primary": pri,
                "backup": bak,
                "synced_objects": to_sync if apply else 0,
                "synced_bytes": 0,
                "failed_count": 0,
                "failed_objects": [],
                "pending_objects": to_sync,
                "logs": logs,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        # 真实 S3 跨桶同步分支
        pri_src = self.get_source(primary_id)
        bak_src = self.get_source(backup_id)
        pri_client = self.get_client(pri_src)
        bak_client = self.get_client(bak_src)

        is_siyuan = comp.get("is_siyuan", False)
        actual_strategy = comp.get("strategy", strategy)

        logs = [
            f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 启动真实 S3 主备同步任务 (标签: {comp['tag']})",
            f"[{datetime.now().strftime('%H:%M:%S')}] 主桶 (Source): {pri['name']} ({pri['bucket']})",
            f"[{datetime.now().strftime('%H:%M:%S')}] 备桶 (Target): {bak['name']} ({bak['bucket']})",
            f"[{datetime.now().strftime('%H:%M:%S')}] 策略: {actual_strategy} {'(思源笔记块存储不可变镜像：零覆写同大小块、零硬删除)' if is_siyuan else '(只增不改不删，单边孤立块安全保留)'}",
            f"[{datetime.now().strftime('%H:%M:%S')}] 扫描结果: 相同对象 {comp['identical_count']} 个，待同步增量 {to_sync} 个，备桶保留孤立对象 {comp.get('retained_count', 0)} 个",
        ]

        synced_count = 0
        synced_bytes = 0
        failed_objects = []
        pending_details = comp.get("pending_details", [])

        if apply:
            for item in pending_details:
                rel = item["rel_path"]
                pri_k = item["pri_key"]
                bak_k = item["bak_key"]
                try:
                    if hasattr(pri_client, "transfer_to"):
                        nbytes, _ = pri_client.transfer_to(pri_k, bak_client, bak_k, max_retries=3)
                    else:
                        data, ctype = pri_client.get_object(pri_k)
                        bak_client.put_object(bak_k, data, content_type=ctype)
                        nbytes = len(data)
                    synced_count += 1
                    synced_bytes += nbytes
                    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] -> 写入成功: {rel} ({nbytes} 字节)")
                except Exception as e:
                    failed_objects.append({
                        "rel_path": rel,
                        "pri_key": pri_k,
                        "bak_key": bak_k,
                        "error": str(e)
                    })
                    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 写入失败: {rel} - {str(e)}")

            is_all_success = (len(failed_objects) == 0)
            status = "success" if is_all_success else ("partial" if synced_count > 0 else "error")

            if is_all_success:
                logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 跨桶数据同步完成，成功传输 {synced_count}/{len(pending_details)} 个对象，共 {round(synced_bytes / 1024 / 1024, 2)} MB。")
                # 仅在全量成功时更新数据源对象计数与同步时间
                for s in self._sources:
                    if s["id"] == backup_id:
                        s["objects_count"] = pri["objects_count"]
                        s["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    elif s["id"] == primary_id:
                        s["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.save()
            else:
                logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ 跨桶数据同步未完全成功：成功传输 {synced_count}/{len(pending_details)} 个对象，失败 {len(failed_objects)} 个。备桶状态保留，请检查网络或配置后重试。")
        else:
            logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] （只读预览模式，未发生任何实际数据写入）")
            for rel in comp.get("sample_pending_files", []):
                logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] -> 待同步预览: {rel}")

        is_all_success = (len(failed_objects) == 0) if apply else True
        status = "success" if is_all_success else ("partial" if synced_count > 0 else "error")

        return {
            "success": is_all_success,
            "status": status,
            "is_demo": False,
            "mode": "apply" if apply else "dry-run",
            "tag": comp["tag"],
            "strategy": actual_strategy,
            "primary": pri,
            "backup": bak,
            "synced_objects": synced_count if apply else 0,
            "synced_bytes": synced_bytes,
            "failed_count": len(failed_objects),
            "failed_objects": failed_objects,
            "pending_objects": to_sync,
            "logs": logs,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


def compute_next_run(interval_type: str, interval_minutes: int = 60, base_time: Optional[datetime] = None) -> datetime:
    """计算下一次调度的真实绝对时间戳（特别修正 daily_2am 为真实凌晨 02:00）"""
    base = base_time or datetime.now()
    if interval_type == "daily_2am":
        target = base.replace(hour=2, minute=0, second=0, microsecond=0)
        if target <= base:
            target += timedelta(days=1)
        return target
    else:
        mins = interval_minutes if interval_minutes > 0 else 60
        return base + timedelta(minutes=mins)


class S3ScheduleManager:
    """管理主桶到备桶的定时同步计划任务"""

    def __init__(self, storage_file: Path, source_manager: S3SourceManager):
        self.storage_file = storage_file
        self.source_manager = source_manager
        self._schedules: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if self.storage_file.exists():
            try:
                data = json.loads(self.storage_file.read_text(encoding="utf-8"))
                self._schedules = data.get("schedules", [])
                return
            except Exception:
                pass
        self._schedules = self._get_initial_seed()
        self.save()

    def save(self) -> None:
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"schedules": self._schedules}
        self.storage_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _get_initial_seed(self) -> List[Dict[str, Any]]:
        now = datetime.now()
        next_run = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        return [
            {
                "id": "sched-obsidian-auto",
                "name": "Obsidian 笔记主备定时同步 (R2 -> 缤纷云)",
                "tag": "Obsidian",
                "primary_id": "s3-obsidian-r2",
                "backup_id": "s3-obsidian-bitiful",
                "interval_type": "every_hour",
                "interval_minutes": 60,
                "interval_label": "每 1 小时自动同步",
                "enabled": True,
                "strategy": "safe_add_only",
                "last_run": now.strftime("%Y-%m-%d %H:%M"),
                "next_run": next_run,
                "last_status": "success",
            },
            {
                "id": "sched-joplin-daily",
                "name": "Joplin 每日异地灾备同步 (MinIO -> 缤纷云)",
                "tag": "Joplin",
                "primary_id": "s3-joplin-minio",
                "backup_id": "s3-joplin-bitiful",
                "interval_type": "daily_2am",
                "interval_minutes": 1440,
                "interval_label": "每天凌晨 02:00 同步",
                "enabled": True,
                "strategy": "safe_add_only",
                "last_run": (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"),
                "next_run": compute_next_run("daily_2am", 1440, now).strftime("%Y-%m-%d %H:%M"),
                "last_status": "success",
            }
        ]

    def list_schedules(self) -> List[Dict[str, Any]]:
        # 补全主备桶名称等元信息
        enriched = []
        for s in self._schedules:
            item = dict(s)
            pri = self.source_manager.get_source(item.get("primary_id", ""))
            bak = self.source_manager.get_source(item.get("backup_id", ""))
            item["primary_name"] = pri["name"] if pri else "已删除的主桶"
            item["backup_name"] = bak["name"] if bak else "已删除的备桶"
            enriched.append(item)
        return enriched

    def add_schedule(self, data: Dict[str, Any]) -> Dict[str, Any]:
        sched_id = data.get("id") or f"sched-{uuid.uuid4().hex[:12]}"
        interval_min = int(data.get("interval_minutes", 60))
        interval_type = data.get("interval_type", "every_hour")
        now = datetime.now()
        next_run = compute_next_run(interval_type, interval_min, now).strftime("%Y-%m-%d %H:%M")

        new_sched = {
            "id": sched_id,
            "name": data.get("name", "未命名定时同步计划"),
            "tag": data.get("tag", "Obsidian"),
            "primary_id": data.get("primary_id", ""),
            "backup_id": data.get("backup_id", ""),
            "interval_type": interval_type,
            "interval_minutes": interval_min,
            "interval_label": data.get("interval_label", f"每 {interval_min} 分钟同步"),
            "enabled": bool(data.get("enabled", True)),
            "strategy": data.get("strategy", "safe_add_only"),
            "last_run": "尚未执行",
            "next_run": next_run,
            "last_status": "pending",
        }
        self._schedules.append(new_sched)
        self.save()
        return new_sched

    def update_schedule(self, sched_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for i, s in enumerate(self._schedules):
            if s.get("id") == sched_id:
                self._schedules[i].update(data)
                self.save()
                return self._schedules[i]
        return None

    def delete_schedule(self, sched_id: str) -> bool:
        init_len = len(self._schedules)
        self._schedules = [s for s in self._schedules if s.get("id") != sched_id]
        if len(self._schedules) < init_len:
            self.save()
            return True
        return False

    def trigger_schedule(self, sched_id: str) -> Dict[str, Any]:
        """按计划执行一次主桶同步到备桶"""
        sched = next((s for s in self._schedules if s["id"] == sched_id), None)
        if not sched:
            return {"success": False, "message": f"未找到定时任务 {sched_id}"}

        res = self.source_manager.sync_pair(
            sched["primary_id"], sched["backup_id"],
            tag=sched.get("tag", ""), apply=True, strategy=sched.get("strategy", "safe_add_only")
        )

        now = datetime.now()
        sched["last_run"] = now.strftime("%Y-%m-%d %H:%M")
        sched["next_run"] = compute_next_run(
            sched.get("interval_type", "every_hour"),
            sched.get("interval_minutes", 60),
            now
        ).strftime("%Y-%m-%d %H:%M")
        sched["last_status"] = "success" if res.get("success") else "error"
        self.save()

        res["schedule_id"] = sched_id
        res["schedule_name"] = sched["name"]
        return res
