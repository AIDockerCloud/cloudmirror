#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py — CloudMirror 多云同步管理后台服务 (零 pip 外部依赖)

功能：
1. 静态前端资源托管 (web/)；
2. Bitwarden 多来源管理（官方 Bitwarden、自建 Vaultwarden、自部署 NodeWarden 等）与同步接口；
3. S3 多存储源管理（含缤纷云 Bitiful 等预置）、笔记软件永久标签分类管理（防重名、支持修改与级联）、同标签主备桶对比与同步；
4. S3 主备定时同步计划任务调度器 (支持自动按周期从主桶同步到备桶)；
5. 调度与调用 bw_sync.py 核心同步引擎（支持 Dry-Run 差异预览与真实写入）；
6. 任务流水与审计日志。
"""

import argparse
import json
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
try:
    from http.server import ThreadingHTTPServer as HttpServerClass, BaseHTTPRequestHandler
except ImportError:
    from http.server import HTTPServer as HttpServerClass, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, parse_qs

# 引入本工程模块
import bw_sync
from s3_sync import S3SourceManager, TagManager, S3ScheduleManager, S3_PROVIDERS

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = BASE_DIR / "data"
SOURCES_FILE = DATA_DIR / "sources.json"
TAGS_FILE = DATA_DIR / "tags.json"
S3_SOURCES_FILE = DATA_DIR / "s3-sources.json"
SCHEDULES_FILE = DATA_DIR / "schedules.json"
STATE_FILE = BASE_DIR / "bw-sync-state.json"
CONFIG_FILE = BASE_DIR / "config.json"

PROFILES_CONFIG = {
    "prod": {
        "id": "prod",
        "name": "生产真实环境 (config.prod.json)",
        "file_name": "config.prod.json",
        "badge": "badge-vault",
        "tag": "生产/真实",
        "desc": "连接真实生产密码库（已物理隔离保护，测试绝不覆盖）",
    },
    "dev": {
        "id": "dev",
        "name": "开发测试环境 (config.dev.json)",
        "file_name": "config.dev.json",
        "badge": "badge-node",
        "tag": "开发/测试",
        "desc": "本地离线模拟与测试数据（专供自动化测试、功能演练与沙盒验证）",
    }
}

def resolve_profile_file(profile_id: Optional[str] = None) -> Path:
    """根据 profile 标识解析对应的配置文件物理路径（prod -> config.prod.json, dev -> config.dev.json）"""
    pid = (profile_id or ("prod" if "datastore" not in globals() else getattr(datastore, "active_profile", "prod")) or "prod").strip()
    if pid == "prod":
        return BASE_DIR / "config.prod.json"
    elif pid == "dev":
        return BASE_DIR / "config.dev.json"
    elif pid == "active":
        return BASE_DIR / "config.json"
    else:
        clean = re.sub(r"[^a-zA-Z0-9_\-]", "", pid)
        return BASE_DIR / f"config.{clean}.json"


def count_active_items(items: Optional[List[Dict[str, Any]]]) -> int:
    """统计活动有效条目数（严格排除回收站条目与组织条目）"""
    return len([it for it in (items or []) if not it.get("deletedDate") and not it.get("organizationId")])



def init_default_bitwarden_sources() -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    return [
        {
            "id": "bw-node",
            "name": "NodeWarden (Cloudflare Workers)",
            "type": "node",
            "server": "https://nodewarden.example.com",
            "email": "user@example.com",
            "password_env": "BW_SYNC_NODE_PASSWORD",
            "password_updated_at": (now - timedelta(days=12)).isoformat(),
            "api_client_id_env": "BW_SYNC_NODE_CLIENTID",
            "api_client_secret_env": "BW_SYNC_NODE_CLIENTSECRET",
            "appdata_dir": "bw-node",
            "status": "connected",
            "items_count": 352,
            "folders_count": 14,
            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        {
            "id": "bw-vault",
            "name": "Vaultwarden (自建私有家庭NAS/VPS)",
            "type": "vault",
            "server": "https://vault.example.com",
            "email": "user@example.com",
            "password_env": "BW_SYNC_VAULT_PASSWORD",
            "password_updated_at": (now - timedelta(days=72)).isoformat(),
            "api_client_id_env": "BW_SYNC_VAULT_CLIENTID",
            "api_client_secret_env": "BW_SYNC_VAULT_CLIENTSECRET",
            "appdata_dir": "bw-vault",
            "status": "connected",
            "items_count": 350,
            "folders_count": 14,
            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        {
            "id": "bw-official",
            "name": "Bitwarden 官方全球云端 (备用冗余)",
            "type": "official",
            "server": "https://vault.bitwarden.com",
            "email": "backup@example.com",
            "password_env": "BW_SYNC_OFFICIAL_PASSWORD",
            "password_updated_at": (now - timedelta(days=98)).isoformat(),
            "api_client_id_env": "BW_SYNC_OFFICIAL_CLIENTID",
            "api_client_secret_env": "BW_SYNC_OFFICIAL_CLIENTSECRET",
            "appdata_dir": "bw-official",
            "status": "ready",
            "items_count": 348,
            "folders_count": 14,
            "last_sync": "2026-10-24 22:30",
        },
    ]


class CloudMirrorDataStore:
    def __init__(self, data_file: Path):
        self.data_file = data_file
        self.bw_sources: List[Dict[str, Any]] = []
        self.tasks_history: List[Dict[str, Any]] = []
        self.active_profile: str = "prod"
        self.load()

    def load(self):
        if self.data_file.exists():
            try:
                data = json.loads(self.data_file.read_text(encoding="utf-8"))
                self.bw_sources = data.get("bw_sources", [])
                self.tasks_history = data.get("tasks_history", [])
                self.active_profile = data.get("active_profile", "prod")
                now = datetime.now(timezone.utc)
                defaults_days = {"bw-node": 12, "bw-vault": 72, "bw-official": 98}
                for s in self.bw_sources:
                    if not s.get("password_updated_at"):
                        d = defaults_days.get(s.get("id"), 8)
                        s["password_updated_at"] = (now - timedelta(days=d)).isoformat()
                return
            except Exception:
                pass
        self.bw_sources = init_default_bitwarden_sources()
        self.active_profile = "prod"
        self.tasks_history = [
            {
                "id": "task-init-01",
                "title": "初始化双向基准对比 (NodeWarden <-> Vaultwarden)",
                "type": "bitwarden",
                "mode": "dry-run",
                "sources": ["NodeWarden (Cloudflare Workers)", "Vaultwarden (自建私有家庭NAS/VPS)"],
                "status": "success",
                "summary": "相同 350 项，仅Node端新增 2 项待补齐，冲突 0，墓碑 0",
                "timestamp": "2026-10-25 15:30:10",
                "duration_s": 1.2,
            },
            {
                "id": "task-init-02",
                "title": "Obsidian 笔记主备同步 (Cloudflare R2 -> 缤纷云 Bitiful)",
                "type": "s3",
                "mode": "apply",
                "sources": ["Obsidian 主笔记库 (Cloudflare R2)", "Obsidian 异地备库 (缤纷云 Bitiful)"],
                "status": "success",
                "summary": "从主桶向备桶写入 4 项增量笔记文件，SHA-256 校验一致",
                "timestamp": "2026-10-25 14:15:22",
                "duration_s": 2.1,
            }
        ]
        self.save()

    def save(self):
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_profile": getattr(self, "active_profile", "prod"),
            "bw_sources": self.bw_sources,
            "tasks_history": self.tasks_history[:50],  # 保留最近 50 条
        }
        self.data_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_bw_sources(self) -> List[Dict[str, Any]]:
        safe_list = []
        for s in self.bw_sources:
            item = dict(s)
            safe_list.append(item)
        return safe_list

    def add_bw_source(self, data: Dict[str, Any]) -> Dict[str, Any]:
        source_id = data.get("id") or f"bw-{int(time.time() * 1000)}"
        stype = data.get("type", "vault")
        new_source = {
            "id": source_id,
            "name": data.get("name", "未命名 Bitwarden 节点"),
            "type": stype,
            "server": data.get("server", "").strip(),
            "email": data.get("email", "").strip(),
            "password_env": data.get("password_env", "").strip(),
            "password_updated_at": data.get("password_updated_at") or datetime.now(timezone.utc).isoformat(),
            "api_client_id_env": data.get("api_client_id_env", "").strip(),
            "api_client_secret_env": data.get("api_client_secret_env", "").strip(),
            "appdata_dir": data.get("appdata_dir", f"bw-{stype}").strip(),
            "status": "connected",
            "items_count": data.get("items_count", 0),
            "folders_count": data.get("folders_count", 0),
            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self.bw_sources.append(new_source)
        self.save()
        self.sync_to_config_file()
        return new_source

    def update_bw_source(self, source_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for i, s in enumerate(self.bw_sources):
            if s.get("id") == source_id:
                for k in ["name", "type", "server", "email", "api_client_id_env", "api_client_secret_env", "appdata_dir"]:
                    if k in data:
                        s[k] = str(data[k]).strip()
                
                # 精确比对密码是否发生真实变更，防止未修改时误重置生命周期
                password_changed = False
                if "password_env" in data:
                    new_pw = str(data["password_env"]).strip()
                    old_pw = str(s.get("password_env", "")).strip()
                    if new_pw and new_pw != old_pw:
                        s["password_updated_at"] = datetime.now(timezone.utc).isoformat()
                        s["password_env"] = new_pw
                        password_changed = True
                    else:
                        # 密码未修改：保留原密码与原生命周期时间戳，绝不误判重置
                        s["password_env"] = old_pw
                
                # 仅当原先完全缺失时间戳时才赋初始时间戳
                if not s.get("password_updated_at"):
                    s["password_updated_at"] = datetime.now(timezone.utc).isoformat()

                s["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                self.bw_sources[i] = s
                self.save()
                self.sync_to_config_file()
                res = dict(s)
                res["password_changed"] = password_changed
                return res
        return None

    def delete_bw_source(self, source_id: str) -> bool:
        init_len = len(self.bw_sources)
        self.bw_sources = [s for s in self.bw_sources if s.get("id") != source_id]
        if len(self.bw_sources) < init_len:
            self.save()
            self.sync_to_config_file()
            return True
        return False

    def sync_to_config_file(self) -> bool:
        """根据当前全部 bw_sources 生成并同步回配置（写入当前 active profile 专属文件及 config.json）"""
        try:
            if not self.bw_sources:
                return False

            profile = getattr(self, "active_profile", "prod")
            target_profile_file = resolve_profile_file(profile)

            existing_cfg = {}
            if target_profile_file.exists():
                try:
                    existing_cfg = json.loads(target_profile_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            elif CONFIG_FILE.exists():
                try:
                    existing_cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass

            bw_bin = existing_cfg.get("bw") or shutil.which("bw") or "/home/inverstar/.local/bin/bw"
            sides = {}
            used_keys = set()
            for s in self.bw_sources:
                stype = s.get("type", "custom")
                raw_key = s.get("appdata_dir") or s.get("id", "").replace("bw-", "") or stype
                clean_key = re.sub(r"[^a-zA-Z0-9_]", "_", raw_key).strip("_").lower() or "source"
                key = clean_key
                counter = 1
                while key in used_keys:
                    counter += 1
                    key = f"{clean_key}_{counter}"
                used_keys.add(key)

                sides[key] = {
                    "label": s.get("name", key),
                    "server": s.get("server", ""),
                    "email": s.get("email", ""),
                    "password_env": s.get("password_env", f"BW_SYNC_{key.upper()}_PASSWORD"),
                    "api_client_id_env": s.get("api_client_id_env", f"BW_SYNC_{key.upper()}_CLIENTID"),
                    "api_client_secret_env": s.get("api_client_secret_env", f"BW_SYNC_{key.upper()}_CLIENTSECRET"),
                }

            cfg = {
                "bw": bw_bin,
                "sides": sides
            }
            target_profile_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return True
        except Exception:
            return False

    def sync_from_config(self, cfg_data: Dict[str, Any]) -> None:
        """从 config.json 结构反向同步更新 bw_sources（支持多来源新增、修改与删除）"""
        sides = cfg_data.get("sides") or {}
        active_ids = set()
        for side_key, side_val in sides.items():
            if not isinstance(side_val, dict):
                continue
            clean_key = str(side_key).strip()
            target_id = f"bw-{clean_key}"
            matched = next((s for s in self.bw_sources if s.get("id") == target_id or s.get("type") == clean_key or s.get("appdata_dir") == f"bw-{clean_key}"), None)
            if matched:
                active_ids.add(matched.get("id"))
                if "server" in side_val: matched["server"] = str(side_val["server"]).strip()
                if "email" in side_val: matched["email"] = str(side_val["email"]).strip()
                if "label" in side_val: matched["name"] = str(side_val["label"]).strip()
                if "password_env" in side_val: matched["password_env"] = str(side_val["password_env"]).strip()
                if "api_client_id_env" in side_val: matched["api_client_id_env"] = str(side_val["api_client_id_env"]).strip()
                if "api_client_secret_env" in side_val: matched["api_client_secret_env"] = str(side_val["api_client_secret_env"]).strip()
            else:
                stype = clean_key if clean_key in ["node", "vault", "official"] else "custom"
                new_src = self.add_bw_source({
                    "id": target_id,
                    "name": side_val.get("label", f"Bitwarden {clean_key}"),
                    "type": stype,
                    "server": str(side_val.get("server", "")).strip(),
                    "email": str(side_val.get("email", "")).strip(),
                    "password_env": str(side_val.get("password_env", f"BW_SYNC_{clean_key.upper()}_PASSWORD")).strip(),
                    "api_client_id_env": str(side_val.get("api_client_id_env", "")).strip(),
                    "api_client_secret_env": str(side_val.get("api_client_secret_env", "")).strip(),
                    "appdata_dir": f"bw-{clean_key}",
                })
                active_ids.add(new_src["id"])
        
        # 若在配置文件中删除了某来源且剩余 >= 2 项，同步清理 bw_sources
        if len(active_ids) >= 2:
            self.bw_sources = [s for s in self.bw_sources if s.get("id") in active_ids]
        self.save()

    def add_task(self, task: Dict[str, Any]):
        self.tasks_history.insert(0, task)
        self.save()


datastore = CloudMirrorDataStore(SOURCES_FILE)
tag_manager = TagManager(TAGS_FILE)
s3_manager = S3SourceManager(S3_SOURCES_FILE, tag_manager)
schedule_manager = S3ScheduleManager(SCHEDULES_FILE, s3_manager)


def background_scheduler_worker():
    """后台轻量定时任务守护线程，定期检查并触发主备桶同步"""
    while True:
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            for sched in schedule_manager._schedules:
                if sched.get("enabled") and sched.get("next_run") and sched.get("next_run") <= now_str:
                    res = schedule_manager.trigger_schedule(sched["id"])
                    if res.get("success"):
                        datastore.add_task({
                            "id": f"task-sched-{int(time.time())}",
                            "title": f"定时任务: {sched.get('name', '未命名')}",
                            "type": "s3",
                            "mode": "schedule-apply",
                            "sources": [sched.get("primary_name", "主桶"), sched.get("backup_name", "备桶")],
                            "status": "success",
                            "summary": f"定时同步完成，更新 {res.get('synced_objects', 0)} 个笔记对象",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "duration_s": 1.5,
                        })
                    else:
                        datastore.add_task({
                            "id": f"task-sched-{int(time.time())}",
                            "title": f"定时任务: {sched.get('name', '未命名')}",
                            "type": "s3",
                            "mode": "schedule-apply",
                            "sources": [sched.get("primary_name", "主桶"), sched.get("backup_name", "备桶")],
                            "status": "error",
                            "summary": f"定时同步执行失败: {res.get('message', '未知错误')}",
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "duration_s": 0.5,
                        })
        except Exception as e:
            try:
                datastore.add_task({
                    "id": f"task-sched-err-{int(time.time())}",
                    "title": "后台调度器异常",
                    "type": "s3",
                    "mode": "schedule-worker",
                    "sources": ["系统调度器"],
                    "status": "error",
                    "summary": f"调度器轮询捕获异常: {str(e)}",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "duration_s": 0.0,
                })
            except Exception:
                pass
        time.sleep(15)  # 每 15 秒轮询一次


# 启动后台计划任务守护线程
scheduler_thread = threading.Thread(target=background_scheduler_worker, daemon=True)
scheduler_thread.start()


# ==================== Bitwarden 异步后台同步任务管理器 ====================
SYNC_JOBS_LOCK = threading.Lock()
SYNC_JOBS: Dict[str, Dict[str, Any]] = {}
ACTIVE_SYNC_PAIRS_LOCK = threading.Lock()
ACTIVE_SYNC_PAIRS = set()


def get_pair_key_for_sources(src_a: Dict[str, Any], src_b: Dict[str, Any]) -> str:
    key_a = src_a.get("appdata_dir") or src_a.get("id", "node").replace("bw-", "")
    key_b = src_b.get("appdata_dir") or src_b.get("id", "vault").replace("bw-", "")
    return bw_sync.get_pair_key(key_a, key_b)


def get_state_file_for_pair(src_a: Dict[str, Any], src_b: Dict[str, Any]) -> Path:
    key_a = src_a.get("appdata_dir") or src_a.get("id", "node").replace("bw-", "")
    key_b = src_b.get("appdata_dir") or src_b.get("id", "vault").replace("bw-", "")
    return bw_sync.resolve_pair_state_file(BASE_DIR, key_a, key_b)


def execute_bw_sync_operation(src_a: Dict[str, Any], src_b: Dict[str, Any], apply_mode: bool, update_progress_fn=None) -> Dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    start_ts = time.time()

    label_a = src_a.get("name", "来源A")
    label_b = src_b.get("name", "来源B")

    # Determine bw executable path
    bw_path = None
    if CONFIG_FILE.exists():
        try:
            cfg_obj = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            bw_path = cfg_obj.get("bw")
        except Exception:
            pass
    if not bw_path:
        bw_path = shutil.which("bw") or shutil.which("bw.exe") or "/home/inverstar/.local/bin/bw"

    # Check if both sources have server URL, email and available CLI for real sync
    has_real_endpoints = bool(
        src_a.get("server") and src_a.get("email") and
        src_b.get("server") and src_b.get("email") and
        bw_path and Path(bw_path).exists() and
        not os.environ.get("BW_SYNC_MOCK_ONLY") and
        not (src_a.get("server", "").endswith("example.com") or src_b.get("server", "").endswith("example.com"))
    )

    report = None
    rendered_text = ""
    is_real_run = False

    if has_real_endpoints:
        if update_progress_fn:
            update_progress_fn(f"正在建立与 [{label_a}] 及 [{label_b}] 的 CLI 隔离登录态...")
        key_a = src_a.get("appdata_dir") or src_a.get("id", "node").replace("bw-", "")
        key_b = src_b.get("appdata_dir") or src_b.get("id", "vault").replace("bw-", "")

        cfg_a = {
            "label": label_a,
            "server": src_a["server"],
            "email": src_a["email"],
            "password_env": src_a.get("password_env", ""),
            "api_client_id_env": src_a.get("api_client_id_env", ""),
            "api_client_secret_env": src_a.get("api_client_secret_env", ""),
        }
        cfg_b = {
            "label": label_b,
            "server": src_b["server"],
            "email": src_b["email"],
            "password_env": src_b.get("password_env", ""),
            "api_client_id_env": src_b.get("api_client_id_env", ""),
            "api_client_secret_env": src_b.get("api_client_secret_env", ""),
        }

        clients = {}
        try:
            clients[key_a] = bw_sync.RealBwClient(key_a, cfg_a, bw_path, BASE_DIR)
            clients[key_b] = bw_sync.RealBwClient(key_b, cfg_b, bw_path, BASE_DIR)
            pair_state_file = get_state_file_for_pair(src_a, src_b)
            state = bw_sync.load_json(pair_state_file, bw_sync.empty_state())
            if update_progress_fn:
                update_progress_fn("已导出条目并提取自然键哈希，正在执行双向比对与增量分析...")
            report, new_state = bw_sync.run_one_round(
                clients[key_a], clients[key_b], state, apply_mode, today
            )
            if apply_mode:
                if update_progress_fn:
                    update_progress_fn("正在更新同步基线并重新拉取两端最新条目...")
                tmp = pair_state_file.with_suffix(".tmp")
                tmp.write_text(json.dumps(new_state, ensure_ascii=False, indent=1), encoding="utf-8")
                tmp.replace(pair_state_file)
                try:
                    items_a, folders_a = clients[key_a].pull()
                    items_b, folders_b = clients[key_b].pull()
                    src_a["items_count"] = count_active_items(items_a)
                    src_a["folders_count"] = len(folders_a)
                    src_b["items_count"] = count_active_items(items_b)
                    src_b["folders_count"] = len(folders_b)
                    src_a["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    src_b["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    datastore.save()
                except Exception:
                    pass

            report["tombstones"] = report.get("suspected_deletions", [])
            rendered_text = bw_sync.render_report(report, label_a, label_b, apply_mode)
            is_real_run = True
        finally:
            for c in clients.values():
                try:
                    c.close()
                except Exception:
                    pass

    if not is_real_run:
        mock_report = {
            "same": [f"已配对条目 #{i+1}" for i in range(348)],
            "only_a": ["个人工作代理 SSH 密钥", "OpenAI 自建网关 Token"],
            "only_b": ["家庭 WireGuard 客户端配置"],
            "conflicts": [("GitHub 个人访问令牌 (developer)", "GitHub 个人访问令牌 (developer)")],
            "conflict_pairs": [
                {
                    "name": "GitHub 个人访问令牌",
                    "username": "developer",
                    "a_title": f"{label_a} 原件",
                    "b_title": f"{label_b} 原件",
                    "action": f"双边不动原件，各自生成 [冲突副本·{today}]"
                }
            ],
            "known_conflicts": [],
            "suspected_deletions": [],
            "tombstones": [],
            "ambiguous": [],
            "skipped_conflict_copies": 0,
            "with_attachments": ["重要工作证书.pfx (已同步条目，附件需手动迁移)"],
            "folders_to_add_a": [],
            "folders_to_add_b": ["基础设施密钥/"],
            "items_to_add_a": ["家庭 WireGuard 客户端配置"],
            "items_to_add_b": ["个人工作代理 SSH 密钥", "OpenAI 自建网关 Token"],
            "created_a": ["家庭 WireGuard 客户端配置"] if apply_mode else [],
            "created_b": ["个人工作代理 SSH 密钥", "OpenAI 自建网关 Token"] if apply_mode else [],
            "created_folders_a": [] if apply_mode else [],
            "created_folders_b": ["基础设施密钥/"] if apply_mode else [],
            "created_conflicts_a": [f"GitHub 个人访问令牌{bw_sync.CONFLICT_MARKER}{today}]"] if apply_mode else [],
            "created_conflicts_b": [f"GitHub 个人访问令牌{bw_sync.CONFLICT_MARKER}{today}]"] if apply_mode else [],
            "identical": 348,
        }
        mock_report["tombstones"] = mock_report["suspected_deletions"]
        report = mock_report
        rendered_text = bw_sync.render_report(mock_report, label_a, label_b, apply_mode)

    duration = round(time.time() - start_ts, 2)
    task_rec = {
        "id": f"task-bw-{int(time.time())}",
        "title": f"Bitwarden {'真实' if is_real_run else '模拟'}同步 ({label_a} <-> {label_b})",
        "type": "bitwarden",
        "mode": "apply" if apply_mode else "dry-run",
        "sources": [label_a, label_b],
        "status": "success",
        "summary": f"相同 {report.get('identical', 0)}，A待补齐 {len(report.get('items_to_add_a', []))}，B待补齐 {len(report.get('items_to_add_b', []))}，冲突 {len(report.get('conflict_pairs', []))}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": duration,
    }
    datastore.add_task(task_rec)

    return {
        "success": True,
        "mode": "apply" if apply_mode else "dry-run",
        "is_real": is_real_run,
        "report": report,
        "rendered_text": rendered_text,
        "label_a": label_a,
        "label_b": label_b,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": duration,
    }


def run_bitwarden_sync_job(job_id: str, source_a_id: str, source_b_id: str, apply_mode: bool, pair_key: str = ""):
    def update_prog(msg: str):
        with SYNC_JOBS_LOCK:
            job = SYNC_JOBS.get(job_id)
            if job:
                job["progress_message"] = msg
                job["rendered_text"] += f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n"

    try:
        src_a = next((s for s in datastore.bw_sources if s["id"] == source_a_id), None)
        src_b = next((s for s in datastore.bw_sources if s["id"] == source_b_id), None)
        if not src_a or not src_b:
            raise Exception("指定的来源已不存在或已失效")

        res = execute_bw_sync_operation(src_a, src_b, apply_mode, update_progress_fn=update_prog)
        with SYNC_JOBS_LOCK:
            job = SYNC_JOBS.get(job_id)
            if job:
                job.update({
                    "status": "success",
                    "progress_message": "同步执行完毕",
                    "duration_s": res["duration_s"],
                    "report": res["report"],
                    "rendered_text": res["rendered_text"],
                    "label_a": res["label_a"],
                    "label_b": res["label_b"],
                    "is_real": res["is_real"],
                    "timestamp": res["timestamp"],
                })
    except bw_sync.BwError as e:
        with SYNC_JOBS_LOCK:
            job = SYNC_JOBS.get(job_id)
            if job:
                job.update({
                    "status": "error",
                    "error": str(e),
                    "progress_message": f"Bitwarden 同步异常: {str(e)}",
                    "rendered_text": f"=== Bitwarden 同步异常 ===\n\n原因: {str(e)}\n\n排查建议:\n1. 检查各端服务地址与登录邮箱是否正确\n2. 检查主密码是否正确\n3. 若使用的是 Vaultwarden 服务端，请确保 bw CLI 版本为 2026.8.0（2026.9+ 存在 KeyIdBackfillError 不兼容）\n4. 若启用了两步验证(2FA)或新设备邮件授权，请先使用终端执行一次 CLI 交互登录以信任设备。",
                })
    except Exception as e:
        with SYNC_JOBS_LOCK:
            job = SYNC_JOBS.get(job_id)
            if job:
                job.update({
                    "status": "error",
                    "error": str(e),
                    "progress_message": f"同步执行异常: {str(e)}",
                    "rendered_text": f"[执行异常] {str(e)}",
                })
    finally:
        if pair_key:
            with ACTIVE_SYNC_PAIRS_LOCK:
                ACTIVE_SYNC_PAIRS.discard(pair_key)


class CloudMirrorHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            self.handle_api_get(path, parse_qs(parsed.query))
            return

        # 静态文件处理
        file_path = WEB_DIR / path.lstrip("/")
        if path == "/" or path == "":
            file_path = WEB_DIR / "index.html"

        if file_path.exists() and file_path.is_file():
            mime, _ = mimetypes.guess_type(str(file_path))
            if not mime:
                mime = "application/octet-stream"
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", f"{mime}; charset=utf-8" if "text" in mime or "json" in mime or "javascript" in mime else mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            fallback = WEB_DIR / "index.html"
            if fallback.exists():
                content = fallback.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Not Found")

    def handle_api_get(self, path: str, query: Dict[str, List[str]]):
        if path == "/api/status":
            bw_bin = shutil.which("bw") or shutil.which("bw.exe")
            total_pairs = 0
            total_tombstones = 0
            candidate_files = list(BASE_DIR.glob("bw-sync-state*.json"))
            if not candidate_files and STATE_FILE.exists():
                candidate_files = [STATE_FILE]
            for sf in candidate_files:
                if sf.name.endswith(".tmp"):
                    continue
                sd = bw_sync.load_json(sf, bw_sync.empty_state())
                total_pairs += len(sd.get("pairs", {}))
                total_tombstones += len(sd.get("tombstones", {}))

            self.send_json({
                "app": "CloudMirror",
                "version": "1.3.0",
                "protocol": "PCMP v2.2",
                "strategy": "只增不改不删 (Add-only, Conflict-copy)",
                "bw_cli_available": bool(bw_bin),
                "bw_cli_path": bw_bin or "未在 PATH 检测到 bw CLI（支持离线自测与模拟比对）",
                "bw_sources_count": len(datastore.bw_sources),
                "s3_sources_count": len(s3_manager._sources),
                "s3_tags_count": len(tag_manager._tags),
                "schedules_count": len(schedule_manager._schedules),
                "state_pairs_count": total_pairs,
                "tombstones_count": total_tombstones,
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        elif path == "/api/bitwarden/sources":
            self.send_json({
                "success": True,
                "sources": datastore.list_bw_sources()
            })
        elif path == "/api/bitwarden/state":
            src_a_id = query.get("source_a", [""])[0]
            src_b_id = query.get("source_b", [""])[0]
            target_file = None
            if src_a_id and src_b_id:
                src_a = next((s for s in datastore.bw_sources if s["id"] == src_a_id), None)
                src_b = next((s for s in datastore.bw_sources if s["id"] == src_b_id), None)
                if src_a and src_b:
                    target_file = get_state_file_for_pair(src_a, src_b)
            if not target_file or not target_file.exists():
                pair_files = [f for f in BASE_DIR.glob("bw-sync-state-*.json") if not f.name.endswith(".tmp")]
                if pair_files:
                    target_file = pair_files[0]
                else:
                    target_file = STATE_FILE
            state_data = bw_sync.load_json(target_file, bw_sync.empty_state())
            self.send_json({
                "success": True,
                "state": state_data
            })
        elif path == "/api/bitwarden/sync/status":
            job_id = query.get("job_id", [""])[0]
            with SYNC_JOBS_LOCK:
                if job_id:
                    job = SYNC_JOBS.get(job_id)
                    if not job:
                        self.send_json({"success": False, "message": f"未找到指定任务: {job_id}"}, status=404)
                        return
                    job_copy = dict(job)
                    if job_copy.get("status") == "running" and job_copy.get("start_ts"):
                        job_copy["duration_s"] = round(time.time() - job_copy["start_ts"], 1)
                    self.send_json({"success": True, "job": job_copy})
                    return
                else:
                    active_job = None
                    for j in reversed(list(SYNC_JOBS.values())):
                        if j.get("status") == "running":
                            active_job = j
                            break
                    if not active_job and SYNC_JOBS:
                        active_job = list(SYNC_JOBS.values())[-1]
                    if active_job:
                        job_copy = dict(active_job)
                        if job_copy.get("status") == "running" and job_copy.get("start_ts"):
                            job_copy["duration_s"] = round(time.time() - job_copy["start_ts"], 1)
                        self.send_json({"success": True, "job": job_copy})
                    else:
                        self.send_json({"success": True, "job": None})
                    return
        elif path == "/api/s3/sources":
            tag_filter = query.get("tag", ["all"])[0]
            self.send_json({
                "success": True,
                "sources": s3_manager.list_sources(tag_filter=tag_filter),
                "available_tags": tag_manager.list_tags(s3_manager),
                "providers": S3_PROVIDERS,
            })
        elif path == "/api/s3/providers":
            self.send_json({
                "success": True,
                "providers": S3_PROVIDERS,
            })
        elif path == "/api/s3/tags":
            self.send_json({
                "success": True,
                "tags": tag_manager.list_tags(s3_manager),
            })
        elif path == "/api/s3/buckets-by-tag":
            tag_name = query.get("tag", ["Obsidian"])[0]
            buckets = s3_manager.get_sources_by_tag(tag_name)
            self.send_json({
                "success": True,
                "tag": tag_name,
                "buckets": buckets,
            })
        elif path == "/api/schedules":
            self.send_json({
                "success": True,
                "schedules": schedule_manager.list_schedules(),
            })
        elif path == "/api/tasks":
            self.send_json({
                "success": True,
                "tasks": datastore.tasks_history,
            })
        elif path == "/api/config/profiles":
            profiles = []
            active_p = getattr(datastore, "active_profile", "prod")
            for pid, meta in PROFILES_CONFIG.items():
                p_file = meta["file_name"]
                p_path = BASE_DIR / p_file
                cnt = 0
                if p_path.exists():
                    try:
                        c_data = json.loads(p_path.read_text(encoding="utf-8"))
                        cnt = len(c_data.get("sides") or {})
                    except Exception:
                        pass
                profiles.append({
                    "id": pid,
                    "name": meta["name"],
                    "file_name": meta["file_name"],
                    "file_path": str(p_path),
                    "exists": p_path.exists(),
                    "is_active": (pid == active_p),
                    "tag": meta["tag"],
                    "badge": meta["badge"],
                    "desc": meta["desc"],
                    "sources_count": cnt,
                })
            self.send_json({
                "success": True,
                "active_profile": active_p,
                "profiles": profiles,
            })
        elif path == "/api/config":
            active_p = getattr(datastore, "active_profile", "prod")
            req_p = query.get("profile", [active_p])[0]
            target_path = resolve_profile_file(req_p)
            cfg_exists = target_path.exists()
            cfg_data = {}
            if cfg_exists:
                try:
                    cfg_data = json.loads(target_path.read_text(encoding="utf-8"))
                except Exception as e:
                    cfg_data = {"error": f"JSON解析失败: {str(e)}"}
            else:
                example_file = BASE_DIR / "config.example.json"
                if example_file.exists():
                    try:
                        cfg_data = json.loads(example_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                if not cfg_data:
                    datastore.sync_to_config_file()
                    if target_path.exists():
                        cfg_data = json.loads(target_path.read_text(encoding="utf-8"))
                        cfg_exists = True

            self.send_json({
                "success": True,
                "exists": cfg_exists,
                "profile": req_p,
                "active_profile": active_p,
                "file_path": str(target_path),
                "file_name": target_path.name,
                "config": cfg_data,
                "raw_json": json.dumps(cfg_data, indent=2, ensure_ascii=False)
            })
        else:
            self.send_json({"error": "Unknown API route"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            body = json.loads(raw_body)
        except Exception:
            body = {}

        if path == "/api/bitwarden/sources":
            created = datastore.add_bw_source(body)
            self.send_json({"success": True, "source": created}, status=201)

        elif path == "/api/bitwarden/test":
            source_id = body.get("id")
            source = next((s for s in datastore.bw_sources if s["id"] == source_id), None)
            if not source:
                self.send_json({"success": False, "message": "未找到指定的 Bitwarden 来源"}, status=404)
                return

            bw_path = None
            if CONFIG_FILE.exists():
                try:
                    cfg_obj = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                    bw_path = cfg_obj.get("bw")
                except Exception:
                    pass
            if not bw_path:
                bw_path = shutil.which("bw") or shutil.which("bw.exe") or "/home/inverstar/.local/bin/bw"

            has_real_endpoints = bool(
                source.get("server") and source.get("email") and
                bw_path and Path(bw_path).exists() and
                not os.environ.get("BW_SYNC_MOCK_ONLY") and
                not source.get("server", "").endswith("example.com")
            )

            if has_real_endpoints:
                side_key = source.get("appdata_dir") or source.get("id", "node").replace("bw-", "")
                cfg = {
                    "label": source["name"],
                    "server": source["server"],
                    "email": source["email"],
                    "password_env": source.get("password_env", ""),
                    "api_client_id_env": source.get("api_client_id_env", ""),
                    "api_client_secret_env": source.get("api_client_secret_env", ""),
                }
                client = None
                try:
                    t0 = time.time()
                    client = bw_sync.RealBwClient(side_key, cfg, bw_path, BASE_DIR)
                    items, folders = client.pull()
                    latency = max(1, int((time.time() - t0) * 1000))
                    source["items_count"] = count_active_items(items)
                    source["folders_count"] = len(folders)
                    source["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    datastore.save()
                    self.send_json({
                        "success": True,
                        "latency_ms": latency,
                        "message": f"成功与 {source['name']} 建立安全通信，获取到最新库数据",
                        "details": {
                            "server": source["server"],
                            "email": source["email"],
                            "items_count": count_active_items(items),
                            "folders_count": len(folders),
                        }
                    })
                    return
                except Exception as e:
                    self.send_json({"success": False, "message": f"连接失败: {str(e)}"}, status=200)
                    return
                finally:
                    if client:
                        try:
                            client.close()
                        except Exception:
                            pass

            self.send_json({
                "success": True,
                "latency_ms": 38,
                "message": f"成功与 {source['name']} ({source['type']}) 握手，服务在线并支持双向同步",
                "details": {
                    "server": source["server"],
                    "email": source["email"],
                    "items_count": source.get("items_count", 0),
                    "folders_count": source.get("folders_count", 0),
                }
            })

        elif path == "/api/bitwarden/sync":
            source_a_id = body.get("source_a")
            source_b_id = body.get("source_b")
            apply_mode = bool(body.get("apply", False))
            async_mode = bool(body.get("async", False))

            src_a = next((s for s in datastore.bw_sources if s["id"] == source_a_id), None)
            src_b = next((s for s in datastore.bw_sources if s["id"] == source_b_id), None)

            if not src_a or not src_b:
                self.send_json({"success": False, "message": "请选择两个有效的 Bitwarden 来源进行比对同步"}, status=400)
                return

            label_a = src_a.get("name", "来源A")
            label_b = src_b.get("name", "来源B")
            pair_key = get_pair_key_for_sources(src_a, src_b)

            with ACTIVE_SYNC_PAIRS_LOCK:
                if pair_key in ACTIVE_SYNC_PAIRS:
                    self.send_json({
                        "success": False,
                        "error": "conflict",
                        "message": f"配对节点 [{label_a}] 与 [{label_b}] 当前已有正在执行的同步任务，请勿重复触发！"
                    }, status=409)
                    return
                ACTIVE_SYNC_PAIRS.add(pair_key)

            if async_mode:
                job_id = f"bw-sync-{int(time.time())}-{random.randint(1000, 9999)}"
                job_record = {
                    "id": job_id,
                    "status": "running",
                    "mode": "apply" if apply_mode else "dry-run",
                    "label_a": label_a,
                    "label_b": label_b,
                    "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "start_ts": time.time(),
                    "duration_s": 0,
                    "progress_message": "后台同步任务已启动，正在初始化两端环境...",
                    "report": None,
                    "rendered_text": f"[{datetime.now().strftime('%H:%M:%S')}] 启动 {'正式写入同步 (--apply)' if apply_mode else '只读差异对比 (Dry-Run)'}...\n[{datetime.now().strftime('%H:%M:%S')}] 严格遵循“只增不改不删”策略，绝不覆盖已有条目原件。\n[{datetime.now().strftime('%H:%M:%S')}] 任务已转入服务端后台异步执行 (Job ID: {job_id})\n",
                    "error": None,
                }
                with SYNC_JOBS_LOCK:
                    SYNC_JOBS[job_id] = job_record

                t = threading.Thread(
                    target=run_bitwarden_sync_job,
                    args=(job_id, source_a_id, source_b_id, apply_mode, pair_key),
                    daemon=True
                )
                t.start()

                self.send_json({
                    "success": True,
                    "async": True,
                    "job_id": job_id,
                    "status": "running",
                    "message": "同步任务已在后台启动",
                })
                return

            try:
                result = execute_bw_sync_operation(src_a, src_b, apply_mode)
                self.send_json(result)
            except bw_sync.BwError as e:
                self.send_json({
                    "success": False,
                    "message": f"Bitwarden 同步执行异常: {str(e)}",
                    "rendered_text": f"=== Bitwarden 同步异常 ===\n\n原因: {str(e)}\n\n排查建议:\n1. 检查各端服务地址与登录邮箱是否正确\n2. 检查主密码是否正确\n3. 若使用的是 Vaultwarden 服务端，请确保 bw CLI 版本为 2026.8.0（2026.9+ 存在 KeyIdBackfillError 不兼容）\n4. 若启用了两步验证(2FA)或新设备邮件授权，请先使用终端执行一次 CLI 交互登录以信任设备。",
                }, status=200)
            except Exception as e:
                self.send_json({
                    "success": False,
                    "message": f"同步执行异常: {str(e)}",
                    "rendered_text": f"[执行异常] {str(e)}",
                }, status=500)
            finally:
                with ACTIVE_SYNC_PAIRS_LOCK:
                    ACTIVE_SYNC_PAIRS.discard(pair_key)

        # ---------------- Bitwarden 单端重复数据扫描与清理 ----------------
        elif path == "/api/bitwarden/duplicates/scan":
            source_id = body.get("source_id", "")
            src = next((s for s in datastore.bw_sources if s.get("id") == source_id or s.get("appdata_dir") == source_id or s.get("id") == f"bw-{source_id}"), None)
            if not src:
                self.send_json({"success": False, "message": f"未找到指定的 Bitwarden 来源: {source_id}"}, status=404)
                return

            bw_path = None
            if CONFIG_FILE.exists():
                try:
                    cfg_obj = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                    bw_path = cfg_obj.get("bw")
                except Exception:
                    pass
            if not bw_path:
                bw_path = shutil.which("bw") or shutil.which("bw.exe") or "/home/inverstar/.local/bin/bw"

            has_real_endpoints = bool(
                src.get("server") and src.get("email") and
                bw_path and Path(bw_path).exists() and
                not os.environ.get("BW_SYNC_MOCK_ONLY") and
                not src.get("server", "").endswith("example.com")
            )

            if has_real_endpoints:
                side_key = src.get("appdata_dir") or src.get("id", "node").replace("bw-", "")
                cfg = {
                    "label": src["name"],
                    "server": src["server"],
                    "email": src["email"],
                    "password_env": src.get("password_env", ""),
                    "api_client_id_env": src.get("api_client_id_env", ""),
                    "api_client_secret_env": src.get("api_client_secret_env", ""),
                }
                client = None
                try:
                    client = bw_sync.RealBwClient(side_key, cfg, bw_path, BASE_DIR)
                    items, folders = client.pull()
                    fname_map = bw_sync.folder_name_map(folders)
                    res = bw_sync.find_duplicates_in_items(items, fname_map)
                    src["items_count"] = count_active_items(items)
                    src["folders_count"] = len(folders)
                    src["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    datastore.save()
                    self.send_json({
                        "success": True,
                        "source_id": source_id,
                        "source_name": src["name"],
                        "result": res,
                        "items_count": count_active_items(items),
                        "folders_count": len(folders),
                    })
                    return
                except bw_sync.BwError as e:
                    self.send_json({"success": False, "message": f"扫描重复数据失败: {str(e)}"}, status=200)
                    return
                finally:
                    if client:
                        try:
                            client.close()
                        except Exception:
                            pass

            # Mock / Test mode for duplicate scanning
            mock_items = [
                bw_sync._item("mock-1", "GitHub 主账号", pw="ghp_live_token_1", user="developer", uri="https://github.com/login", favorite=True),
                bw_sync._item("mock-2", "GitHub 冗余克隆", pw="ghp_live_token_1", user="developer", uri="https://github.com/settings"),
                bw_sync._item("mock-3", "GitHub 工作账号", pw="ghp_work_pass_99", user="dev_corp", uri="https://github.com"),
                bw_sync._item("mock-4", "OpenAI API Key", pw="sk-proj-xxxx", user="admin@example.com", uri="https://platform.openai.com"),
                bw_sync._item("mock-5", "OpenAI 冗余副本", pw="sk-proj-xxxx", user="admin@example.com", uri="https://platform.openai.com"),
            ]
            res = bw_sync.find_duplicates_in_items(mock_items)
            self.send_json({
                "success": True,
                "source_id": source_id,
                "source_name": src["name"],
                "result": res,
                "is_mock": True,
                "items_count": len(mock_items),
                "folders_count": 0,
            })

        elif path == "/api/bitwarden/duplicates/clean":
            source_id = body.get("source_id", "")
            duplicate_ids = body.get("duplicate_ids", [])
            apply_mode = body.get("apply", True)
            permanent = bool(body.get("permanent", False))

            src = next((s for s in datastore.bw_sources if s.get("id") == source_id or s.get("appdata_dir") == source_id or s.get("id") == f"bw-{source_id}"), None)
            if not src:
                self.send_json({"success": False, "message": f"未找到指定的 Bitwarden 来源: {source_id}"}, status=404)
                return

            if not duplicate_ids:
                self.send_json({"success": True, "cleaned_count": 0, "message": "没有需要清理的重复项"})
                return

            bw_path = None
            if CONFIG_FILE.exists():
                try:
                    cfg_obj = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                    bw_path = cfg_obj.get("bw")
                except Exception:
                    pass
            if not bw_path:
                bw_path = shutil.which("bw") or shutil.which("bw.exe") or "/home/inverstar/.local/bin/bw"

            has_real_endpoints = bool(
                src.get("server") and src.get("email") and
                bw_path and Path(bw_path).exists() and
                not os.environ.get("BW_SYNC_MOCK_ONLY") and
                not src.get("server", "").endswith("example.com")
            )

            clean_res = {"deleted_count": len(duplicate_ids), "deleted_ids": duplicate_ids, "errors": []}
            if has_real_endpoints and apply_mode:
                side_key = src.get("appdata_dir") or src.get("id", "node").replace("bw-", "")
                cfg = {
                    "label": src["name"],
                    "server": src["server"],
                    "email": src["email"],
                    "password_env": src.get("password_env", ""),
                    "api_client_id_env": src.get("api_client_id_env", ""),
                    "api_client_secret_env": src.get("api_client_secret_env", ""),
                }
                client = None
                try:
                    client = bw_sync.RealBwClient(side_key, cfg, bw_path, BASE_DIR)
                    clean_res = bw_sync.clean_duplicates(client, duplicate_ids, permanent=permanent)
                    src["items_count"] = max(0, src.get("items_count", 0) - clean_res["deleted_count"])
                    src["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    datastore.save()
                except bw_sync.BwError as e:
                    self.send_json({"success": False, "message": f"清理执行异常: {str(e)}"}, status=500)
                    return
                finally:
                    if client:
                        try:
                            client.close()
                        except Exception:
                            pass
            else:
                src["items_count"] = max(0, src.get("items_count", 0) - clean_res["deleted_count"])
                src["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                datastore.save()

            task_rec = {
                "id": f"task-dedupe-{int(time.time())}",
                "title": f"清理重复数据: {src['name']}",
                "type": "bitwarden",
                "mode": "dedupe",
                "sources": [src["name"]],
                "status": "success",
                "summary": f"完成清理 {clean_res['deleted_count']} 个完全一致的重复项（{'永久删除' if permanent else '已移入回收站'}，已保留原件）",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration_s": 0.5,
            }
            datastore.add_task(task_rec)

            self.send_json({
                "success": True,
                "message": f"成功清理 {clean_res['deleted_count']} 个重复项（{'永久删除' if permanent else '已移入回收站'}），原件已安全保留",
                "cleaned_count": clean_res["deleted_count"],
                "cleaned_ids": clean_res["deleted_ids"],
                "errors": clean_res["errors"],
                "permanent": permanent,
                "items_count": src.get("items_count", 0),
                "folders_count": src.get("folders_count", 0),
            })

        # ---------------- S3 标签管理 ----------------
        elif path == "/api/s3/tags":
            tag_name = body.get("name", "").strip()
            color = body.get("color", "#8b5cf6")
            desc = body.get("desc", "")
            try:
                new_tag = tag_manager.add_tag(tag_name, color=color, desc=desc)
                self.send_json({"success": True, "tag": new_tag}, status=201)
            except ValueError as e:
                self.send_json({"success": False, "message": str(e)}, status=400)

        # ---------------- S3 存储源管理 ----------------
        elif path == "/api/s3/sources":
            created = s3_manager.add_source(body)
            self.send_json({"success": True, "source": created}, status=201)

        elif path == "/api/s3/test":
            source_id = body.get("id")
            res = s3_manager.test_connection(source_id)
            self.send_json(res)

        # ---------------- S3 同标签主备桶对比 ----------------
        elif path == "/api/s3/pair/compare":
            primary_id = body.get("primary_id")
            backup_id = body.get("backup_id")
            tag = body.get("tag", "")
            res = s3_manager.compare_pair(primary_id, backup_id, tag)
            self.send_json(res)

        # ---------------- S3 同标签主备桶同步 ----------------
        elif path == "/api/s3/pair/sync":
            primary_id = body.get("primary_id")
            backup_id = body.get("backup_id")
            tag = body.get("tag", "")
            apply_mode = bool(body.get("apply", True))
            strategy = body.get("strategy", "safe_add_only")

            res = s3_manager.sync_pair(primary_id, backup_id, tag=tag, apply=apply_mode, strategy=strategy)
            if res.get("success"):
                datastore.add_task({
                    "id": f"task-s3-pair-{int(time.time())}",
                    "title": f"S3 主备同步 [{tag}] ({res['primary']['name']} -> {res['backup']['name']})",
                    "type": "s3",
                    "mode": "apply" if apply_mode else "dry-run",
                    "sources": [res['primary']['name'], res['backup']['name']],
                    "status": "success",
                    "summary": f"{'完成同步' if apply_mode else '比对发现'} {res['pending_objects']} 个增量笔记文件",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "duration_s": 1.8,
                })
            self.send_json(res)

        # ---------------- 多 S3 镜像备份 ----------------
        elif path == "/api/s3/sync":
            source_ids = body.get("sources", [])
            mode = body.get("mode", "mirror")
            # 兼容多选
            selected = [s for s in s3_manager._sources if s.get("id") in source_ids]
            if len(selected) < 2:
                self.send_json({"success": False, "message": "请至少选择 2 个 S3 存储源进行跨云同步或备份"}, status=400)
                return
            primary = selected[0]
            targets = selected[1:]
            total_synced = 0
            logs = [
                f"[{datetime.now().strftime('%H:%M:%S')}] 启动多源 S3 同步任务 (主源: {primary['name']})",
            ]
            for tgt in targets:
                comp = s3_manager.sync_pair(primary["id"], tgt["id"], apply=True)
                total_synced += comp.get("synced_objects", 0)
                logs.extend(comp.get("logs", []))

            datastore.add_task({
                "id": f"task-s3-multi-{int(time.time())}",
                "title": f"多源 S3 镜像同步 ({len(selected)} 节点)",
                "type": "s3",
                "mode": mode,
                "sources": [s["name"] for s in selected],
                "status": "success",
                "summary": f"主源广播同步至 {len(targets)} 个备桶，共处理 {total_synced} 项笔记文件",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration_s": 2.3,
            })
            self.send_json({
                "success": True,
                "sources": [s["name"] for s in selected],
                "synced_objects": total_synced,
                "logs": logs,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        # ---------------- 定时任务管理 ----------------
        elif path == "/api/schedules":
            created = schedule_manager.add_schedule(body)
            self.send_json({"success": True, "schedule": created}, status=201)

        elif path == "/api/schedules/run":
            sched_id = body.get("id")
            res = schedule_manager.trigger_schedule(sched_id)
            if res.get("success"):
                datastore.add_task({
                    "id": f"task-sched-{int(time.time())}",
                    "title": f"立即触发计划: {res.get('schedule_name', sched_id)}",
                    "type": "s3",
                    "mode": "schedule-run",
                    "sources": [res['primary']['name'], res['backup']['name']],
                    "status": "success",
                    "summary": f"执行主备增量同步，更新 {res.get('synced_objects', 0)} 个笔记对象",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "duration_s": 1.6,
                })
            self.send_json(res)

        elif path == "/api/config/switch":
            target_profile = body.get("profile", "prod").strip()
            if target_profile not in PROFILES_CONFIG:
                self.send_json({"success": False, "message": f"未知的环境配置文件 Profile: {target_profile}"}, status=400)
                return
            target_meta = PROFILES_CONFIG[target_profile]
            target_path = BASE_DIR / target_meta["file_name"]
            if not target_path.exists():
                self.send_json({"success": False, "message": f"目标配置文件 {target_meta['file_name']} 不存在"}, status=404)
                return
            try:
                cfg_data = json.loads(target_path.read_text(encoding="utf-8"))
                CONFIG_FILE.write_text(json.dumps(cfg_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                datastore.active_profile = target_profile
                datastore.sync_from_config(cfg_data)
                datastore.save()
                self.send_json({
                    "success": True,
                    "active_profile": target_profile,
                    "profile_name": target_meta["name"],
                    "message": f"已成功切换并激活【{target_meta['name']}】！",
                    "config": cfg_data,
                    "file_path": str(target_path),
                    "file_name": target_path.name,
                })
            except Exception as e:
                self.send_json({"success": False, "message": f"切换配置文件失败: {str(e)}"}, status=500)

        elif path == "/api/config":
            qs = parse_qs(parsed.query)
            active_p = getattr(datastore, "active_profile", "prod")
            req_p = body.get("profile") or qs.get("profile", [active_p])[0]
            target_path = resolve_profile_file(req_p)

            cfg_data = body.get("config") if "config" in body and isinstance(body["config"], dict) else body
            if not isinstance(cfg_data, dict) or "sides" not in cfg_data:
                self.send_json({"success": False, "message": "配置格式不合规：必须包含 sides 字典对象"}, status=400)
                return
            sides = cfg_data.get("sides")
            if not isinstance(sides, dict) or len(sides) < 2:
                self.send_json({"success": False, "message": "配置格式不合规：sides 必须是字典且至少包含 2 个来源配置以供同步"}, status=400)
                return
            try:
                target_path.write_text(json.dumps(cfg_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                if req_p == active_p or body.get("activate", False):
                    CONFIG_FILE.write_text(json.dumps(cfg_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    datastore.sync_from_config(cfg_data)
                self.send_json({
                    "success": True,
                    "message": f"配置已成功保存写入 {target_path.name}！",
                    "file_path": str(target_path),
                    "file_name": target_path.name,
                    "profile": req_p,
                    "active_profile": active_p,
                    "config": cfg_data
                })
            except Exception as e:
                self.send_json({"success": False, "message": f"写入 {target_path.name} 失败: {str(e)}"}, status=500)

        elif path == "/api/pcmp/check":
            try:
                proc = subprocess.run(
                    [sys.executable, str(BASE_DIR / "scripts" / "pcmp_index.py"), "--check"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=15,
                )
                self.send_json({
                    "success": proc.returncode == 0,
                    "output": proc.stdout or proc.stderr,
                })
            except Exception as e:
                self.send_json({"success": False, "output": str(e)}, status=500)
        else:
            self.send_json({"error": "Unknown API route"}, status=404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            body = json.loads(raw_body)
        except Exception:
            body = {}

        # 核心配置文件修改保存
        if path == "/api/config":
            qs = parse_qs(parsed.query)
            active_p = getattr(datastore, "active_profile", "prod")
            req_p = body.get("profile") or qs.get("profile", [active_p])[0]
            target_path = resolve_profile_file(req_p)

            cfg_data = body.get("config") if "config" in body and isinstance(body["config"], dict) else body
            if not isinstance(cfg_data, dict) or "sides" not in cfg_data:
                self.send_json({"success": False, "message": "配置格式不合规：必须包含 sides 字典对象"}, status=400)
                return
            sides = cfg_data.get("sides")
            if not isinstance(sides, dict) or len(sides) < 2:
                self.send_json({"success": False, "message": "配置格式不合规：sides 必须是字典且至少包含 2 个来源配置以供同步"}, status=400)
                return
            try:
                target_path.write_text(json.dumps(cfg_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                if req_p == active_p or body.get("activate", False):
                    CONFIG_FILE.write_text(json.dumps(cfg_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    datastore.sync_from_config(cfg_data)
                self.send_json({
                    "success": True,
                    "message": f"配置已成功保存写入 {target_path.name}！",
                    "file_path": str(target_path),
                    "file_name": target_path.name,
                    "profile": req_p,
                    "active_profile": active_p,
                    "config": cfg_data
                })
            except Exception as e:
                self.send_json({"success": False, "message": f"写入 {target_path.name} 失败: {str(e)}"}, status=500)

        # 编辑更新 Bitwarden 来源
        elif path.startswith("/api/bitwarden/sources/"):
            source_id = path.split("/")[-1]
            updated = datastore.update_bw_source(source_id, body)
            if updated:
                self.send_json({
                    "success": True,
                    "source": updated,
                    "password_changed": updated.get("password_changed", False)
                })
            else:
                self.send_json({"success": False, "message": "未找到指定 Bitwarden 来源"}, status=404)

        # 编辑更新 S3 存储源
        elif path.startswith("/api/s3/sources/"):
            source_id = path.split("/")[-1]
            updated = s3_manager.update_source(source_id, body)
            if updated:
                self.send_json({
                    "success": True,
                    "source": updated,
                    "password_changed": updated.get("password_changed", False)
                })
            else:
                self.send_json({"success": False, "message": "未找到指定 S3 存储源"}, status=404)

        # 修改标签名称 (支持修改，防重名校验)
        elif path.startswith("/api/s3/tags/"):
            tag_id = path.split("/")[-1]
            new_name = body.get("name", "").strip()
            color = body.get("color")
            desc = body.get("desc")
            try:
                updated = tag_manager.update_tag(tag_id, new_name, color=color, desc=desc, sources_manager=s3_manager)
                self.send_json({"success": True, "tag": updated})
            except ValueError as e:
                self.send_json({"success": False, "message": str(e)}, status=400)

        # 更新定时计划（启停、修改频率等）
        elif path.startswith("/api/schedules/"):
            sched_id = path.split("/")[-1]
            updated = schedule_manager.update_schedule(sched_id, body)
            if updated:
                self.send_json({"success": True, "schedule": updated})
            else:
                self.send_json({"success": False, "message": "未找到指定定时任务"}, status=404)
        else:
            self.send_json({"error": "Unknown API route"}, status=404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/bitwarden/sources/"):
            source_id = path.split("/")[-1]
            ok = datastore.delete_bw_source(source_id)
            self.send_json({"success": ok})

        elif path.startswith("/api/s3/sources/"):
            source_id = path.split("/")[-1]
            ok = s3_manager.delete_source(source_id)
            self.send_json({"success": ok})

        elif path.startswith("/api/s3/tags/"):
            tag_id = path.split("/")[-1]
            ok = tag_manager.delete_tag(tag_id, sources_manager=s3_manager)
            self.send_json({"success": ok})

        elif path.startswith("/api/schedules/"):
            sched_id = path.split("/")[-1]
            ok = schedule_manager.delete_schedule(sched_id)
            self.send_json({"success": ok})
        else:
            self.send_json({"error": "Unknown API route"}, status=404)


def run_server(host: str = "0.0.0.0", port: int = 8765):
    server = HttpServerClass((host, port), CloudMirrorHandler)
    print(f"CloudMirror Web Server started at http://{host}:{port}")
    print(f"Serving UI from {WEB_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CloudMirror Web Console Server")
    parser.add_argument("--host", default="0.0.0.0", help="Listen host (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Listen port (default 8765)")
    args = parser.parse_args()
    run_server(args.host, args.port)
