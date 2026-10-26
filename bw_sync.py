#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bw_sync.py — NodeWarden <-> Vaultwarden 双向对比同步脚本（个人保险库）

思路（只增不改不删）：
  1. 通过官方 bw CLI 分别登录两边（各自独立的 BITWARDENCLI_APPDATA_DIR），
     bw sync + bw list，把两边保险库以“解密后”的形式拉下来；
  2. 对比：条目靠映射表(state 文件) + 自然键(类型+名称+用户名)配对，
     内容靠规范化后的 SHA-256 哈希判等；
  3. 新增的 -> 在另一边新建；配对但内容不同的 -> 两边都不动原件，
     各把对方版本建一条“冲突副本”保留两份，人工裁决；
  4. 删除不自动传播、也不会被复活：疑似删除只报告 + 记墓碑。

默认只读（dry-run）：只拉取、对比、出报告，不写任何数据、不更新 state。
加 --apply 才真正执行新建，并保存 state 文件。

v1 范围：只同步个人保险库条目与文件夹。不处理：附件（只警告）、
passkey/FIDO2 凭证（条目会同步，但 fido2Credentials 字段不带过去）、
Send、组织/集合条目（跳过并报告）、密码历史。

依赖：Python 3.8+（仅标准库）+ 官方 Bitwarden CLI (bw)。
在 Win11 上：python bw_sync.py            # 只读报告
            python bw_sync.py --apply    # 执行同步
            python bw_sync.py --selftest # 离线自测对比逻辑（不需要 bw）
"""

import argparse
import copy
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

CONFLICT_MARKER = " [冲突副本·"
STRIP_ON_CREATE = (
    "id", "revisionDate", "creationDate", "deletedDate",
    "passwordHistory", "attachments", "collectionIds", "organizationId",
    "object", "key",
)


class BwError(Exception):
    pass


# ---------------------------------------------------------------------------
# 条目规范化与哈希
# ---------------------------------------------------------------------------

def folder_name_map(folders):
    return {f.get("id"): f.get("name") for f in folders or []}


def normalize_item_name(name):
    if not name or not isinstance(name, str):
        return ""
    return name.strip().casefold()


def normalize_item(item, fname_by_id):
    """把 bw list 输出的一条条目规范化成可哈希、可跨实例比较的字典。"""
    n = {
        "type": item.get("type"),
        "name": (item.get("name") or "").strip(),
        "folder": fname_by_id.get(item.get("folderId")),
        "favorite": bool(item.get("favorite")),
        "reprompt": item.get("reprompt", 0),
        "notes": item.get("notes"),
        "fields": [
            {"name": f.get("name"), "value": f.get("value"), "type": f.get("type")}
            for f in sorted(item.get("fields") or [], key=lambda x: str(x.get("name") or ""))
        ],
    }
    for section in ("login", "secureNote", "card", "identity", "sshKey"):
        if item.get(section) is not None:
            sec = copy.deepcopy(item[section])
            if section == "login":
                sec.pop("fido2Credentials", None)      # v1 不同步 passkey
                sec.pop("passwordRevisionDate", None)
                # 规范化自动填充选项 (uris)：支持多个自动填充，忽略数组顺序与多余空白
                uris = sec.get("uris")
                if isinstance(uris, list):
                    norm_uris = []
                    for u in uris:
                        if isinstance(u, dict):
                            u_str = (u.get("uri") or "").strip()
                            if u_str:
                                norm_uris.append({
                                    "uri": u_str,
                                    "match": u.get("match"),
                                })
                        elif isinstance(u, str) and u.strip():
                            norm_uris.append({"uri": u.strip(), "match": None})
                    # 排序保证多个自动填充选项时哈希确定性不受数组顺序影响
                    norm_uris.sort(key=lambda x: (x["uri"], str(x.get("match") if x.get("match") is not None else "")))
                    sec["uris"] = norm_uris
            n[section] = sec
    return n


def content_hash(norm):
    blob = json.dumps(norm, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def extract_domain_from_uri(uri_str):
    if not uri_str or not isinstance(uri_str, str):
        return ""
    uri_str = uri_str.strip()
    if not uri_str:
        return ""
    if "://" not in uri_str and not uri_str.startswith("//"):
        uri_str = "http://" + uri_str
    try:
        parsed = urlparse(uri_str)
        host = (parsed.hostname or parsed.netloc or "").strip().lower()
        if host.startswith("www."):
            host = host[4:]
        if parsed.port and parsed.port not in (80, 443):
            host = f"{host}:{parsed.port}"
        return host
    except Exception:
        return ""


def extract_item_domain(norm):
    login = norm.get("login") if isinstance(norm.get("login"), dict) else {}
    uris = login.get("uris") or []
    for u in uris:
        u_str = u.get("uri") if isinstance(u, dict) else str(u)
        d = extract_domain_from_uri(u_str)
        if d:
            return d
    if login.get("uri"):
        d = extract_domain_from_uri(login.get("uri"))
        if d:
            return d
    name = (norm.get("name") or "").strip()
    d = extract_domain_from_uri(name)
    if d and "." in d and not any(c in d for c in (" ", "\t", "/", "\\")):
        return d
    return name.casefold()


def extract_item_username(norm):
    if isinstance(norm.get("login"), dict):
        return (norm["login"].get("username") or "").strip().casefold()
    return ""


def natural_key(norm):
    """
    条目自然键判定：
    - 严格遵循：项目名称/域名标识 (Item Identifier) + 账号 (Username) 共同构成独立条目标识；
    - 类型一致的前提下，域名标识与账号均相同判定为同一数据条目；
    - 允许同一项目名/域名下注册不同账号（不同账号不混淆、不冲突）；
    - 若无域名或非登录条目降级退回规范化项目名称 + 账号。
    """
    itype = norm.get("type")
    ident = extract_item_domain(norm)
    if not ident:
        ident = normalize_item_name(norm.get("name"))
    username = extract_item_username(norm)
    return (itype, ident, username)



def find_duplicates_in_items(items, fname_by_id=None):
    """
    在单端保险库数据源内部查找完全重复的数据。
    严格判定标准：必须是域名 (Domain) + 账号 (Username) + 密码 (Password) 完全一致。
    返回重复分组清单与可清理的副本条目列表（每组安全保留 1 份原件）。
    """
    if fname_by_id is None:
        fname_by_id = {}

    groups_map = {}
    for item in items:
        if item.get("deletedDate") or item.get("organizationId"):
            continue
        norm = normalize_item(item, fname_by_id)
        itype = norm.get("type", 1)
        domain = extract_item_domain(norm)
        username = extract_item_username(norm)
        login = item.get("login") or {}
        password = login.get("password") or ""

        # 仅针对具有域名且具备有效账号或密码的凭据进行去重分组
        if not domain or (not username and not password):
            continue

        key = (itype, domain, username, password)
        groups_map.setdefault(key, []).append((item, norm))

    duplicate_groups = []
    total_duplicate_copies = 0

    for (itype, domain, username, password), item_tuples in groups_map.items():
        if len(item_tuples) > 1:
            # 排序规则确定保留原件：优先保留收藏（favorite）、带有较多 fields/notes 的项
            def sort_key(t):
                raw_it, _ = t
                fav = 1 if raw_it.get("favorite") else 0
                fields_cnt = len(raw_it.get("fields") or [])
                notes_len = len(raw_it.get("notes") or "")
                return (fav, fields_cnt, notes_len)

            sorted_items = sorted(item_tuples, key=sort_key, reverse=True)
            keep_raw, keep_norm = sorted_items[0]
            dup_raws = [t[0] for t in sorted_items[1:]]

            total_duplicate_copies += len(dup_raws)
            duplicate_groups.append({
                "domain": domain,
                "username": username,
                "password": password,
                "type": itype,
                "total_count": len(sorted_items),
                "keep": {
                    "id": keep_raw.get("id"),
                    "name": keep_raw.get("name") or "(无名)",
                    "folder": fname_by_id.get(keep_raw.get("folderId")),
                    "favorite": bool(keep_raw.get("favorite")),
                    "revisionDate": keep_raw.get("revisionDate"),
                },
                "duplicates": [
                    {
                        "id": d.get("id"),
                        "name": d.get("name") or "(无名)",
                        "folder": fname_by_id.get(d.get("folderId")),
                        "favorite": bool(d.get("favorite")),
                        "revisionDate": d.get("revisionDate"),
                    }
                    for d in dup_raws
                ]
            })

    return {
        "total_items": len(items),
        "duplicate_groups_count": len(duplicate_groups),
        "duplicate_items_count": total_duplicate_copies,
        "groups": duplicate_groups,
    }


def clean_duplicates(client, duplicate_ids, permanent=False):
    """
    调用 client.delete_item 逐个删除指定的重复条目 ID。
    当 permanent=True 时彻底永久硬删除，否则放入回收站（支持30天安全恢复）。
    返回已删除的 ID 列表与错误列表。
    """
    deleted = []
    errors = []
    for item_id in duplicate_ids:
        try:
            client.delete_item(item_id, permanent=permanent)
            deleted.append(item_id)
        except Exception as e:
            errors.append({"id": item_id, "error": str(e)})
    return {
        "success": len(errors) == 0,
        "deleted_count": len(deleted),
        "deleted_ids": deleted,
        "errors": errors,
        "permanent": permanent,
    }


class Rec:
    """一条条目在某边的记录：原始数据 + 规范化 + 哈希。"""

    def __init__(self, raw, fname_by_id):
        self.raw = raw
        self.id = raw.get("id")
        self.norm = normalize_item(raw, fname_by_id)
        self.hash = content_hash(self.norm)
        self.nkey = natural_key(self.norm)
        self.name = raw.get("name") or "(无名)"


def is_conflict_copy(raw):
    return CONFLICT_MARKER in (raw.get("name") or "")


def build_create_payload(rec, target_folder_id, new_name=None):
    obj = copy.deepcopy(rec.raw)
    for k in STRIP_ON_CREATE:
        obj.pop(k, None)
    if isinstance(obj.get("login"), dict):
        obj["login"].pop("fido2Credentials", None)
        obj["login"].pop("passwordRevisionDate", None)
    obj["folderId"] = target_folder_id
    if new_name:
        obj["name"] = new_name
    return obj


# ---------------------------------------------------------------------------
# 客户端接口：真实 bw CLI 与自测用 Fake 共用同一套方法
# ---------------------------------------------------------------------------

class RealBwClient:
    def __init__(self, side_key, cfg, bw_path, base_dir):
        self.side_key = side_key
        self.label = cfg.get("label", side_key)
        self.server = cfg["server"]
        self.email = cfg["email"]
        self.bw = bw_path
        self.appdata = Path(base_dir) / f"bw-{side_key}"
        self.appdata.mkdir(parents=True, exist_ok=True)
        self._password = None
        self._session = None
        pw_env = cfg.get("password_env") or f"BW_SYNC_{side_key.upper()}_PASSWORD"
        self._pw_env_name = pw_env
        self._cid_env = cfg.get("api_client_id_env") or \
            f"BW_SYNC_{side_key.upper()}_CLIENTID"
        self._csec_env = cfg.get("api_client_secret_env") or \
            f"BW_SYNC_{side_key.upper()}_CLIENTSECRET"

    def _api_key(self):
        cid = os.environ.get(self._cid_env)
        csec = os.environ.get(self._csec_env)
        return (cid, csec) if cid and csec else None

    # -- 内部工具 -----------------------------------------------------------
    def _env(self):
        env = dict(os.environ)
        env["BITWARDENCLI_APPDATA_DIR"] = str(self.appdata)
        env["BW_NOINTERACTION"] = "true"
        if self._session:
            env["BW_SESSION"] = self._session
        if self._password:
            env["BW_PASSWORD"] = self._password
        ak = self._api_key()
        if ak:
            env["BW_CLIENTID"], env["BW_CLIENTSECRET"] = ak
        return env

    def _run(self, args, stdin_text=None, timeout=120):
        try:
            p = subprocess.run(
                [self.bw] + args,
                input=stdin_text, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                env=self._env(), timeout=timeout,
            )
        except FileNotFoundError:
            raise BwError(f"找不到 bw 可执行文件：{self.bw}")
        except subprocess.TimeoutExpired:
            raise BwError(
                f"[{self.label}] bw {' '.join(args[:2])} 超时（{timeout}s）"
                "——服务器可能不可达或网络不通")
        if p.returncode != 0:
            msg = (p.stderr or p.stdout or "").strip().splitlines()
            tail = msg[-1] if msg else f"exit code {p.returncode}"
            raise BwError(f"[{self.label}] bw {' '.join(args[:2])} 失败：{tail}")
        return (p.stdout or "").strip()

    def _password_once(self):
        if self._password is None:
            from_env = os.environ.get(self._pw_env_name) if self._pw_env_name else None
            if from_env:
                self._password = from_env
            elif not os.environ.get("BW_SYNC_HEADLESS") and sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
                self._password = getpass.getpass(
                    f"输入 {self.label} 的主密码（不会保存）：")
            else:
                env_hint = self._pw_env_name or "BW_SYNC_PASSWORD"
                raise BwError(f"[{self.label}] 未检测到主密码环境变量 {env_hint}，且处于非交互/无头运行模式")
        return self._password

    # -- 对外接口 -----------------------------------------------------------
    def ensure_session(self):
        if self._session:
            return
        self._password_once()
        status = json.loads(self._run(["status"])).get("status")
        if status == "unauthenticated":
            self._run(["config", "server", self.server])
            if self._api_key():
                # 云上无人值守优先走 API key 登录（仍需主密码 unlock，见下）
                self._run(["login", "--apikey"])
            else:
                out = self._run(
                    ["login", self.email, "--passwordenv", "BW_PASSWORD", "--raw"])
                if out:
                    self._session = out.splitlines()[-1].strip()
        if not self._session:
            out = self._run(["unlock", "--passwordenv", "BW_PASSWORD", "--raw"])
            self._session = out.splitlines()[-1].strip()
        if not self._session:
            raise BwError(f"[{self.label}] 未能取得 BW_SESSION，登录失败")

    def pull(self):
        self.ensure_session()
        self._run(["sync"], timeout=300)
        items = json.loads(self._run(["list", "items"], timeout=300) or "[]")
        folders = json.loads(self._run(["list", "folders"], timeout=300) or "[]")
        return items, folders

    def pull_trash(self):
        self.ensure_session()
        try:
            items = json.loads(self._run(["list", "items", "--trash"], timeout=300) or "[]")
            return items
        except Exception:
            return []

    def create_folder(self, name):
        self.ensure_session()
        enc = self._run(["encode"], stdin_text=json.dumps({"name": name}))
        out = self._run(["create", "folder", enc])
        return json.loads(out).get("id")

    def create_item(self, payload):
        self.ensure_session()
        enc = self._run(["encode"], stdin_text=json.dumps(payload, ensure_ascii=False))
        out = self._run(["create", "item", enc])
        return json.loads(out).get("id")

    def delete_item(self, item_id, permanent=False):
        self.ensure_session()
        args = ["delete", "item", item_id]
        if permanent:
            args.append("--permanent")
        return self._run(args)

    def close(self):
        try:
            if self._session:
                self._run(["lock"])
        except BwError:
            pass
        self._session = None


class FakeBwClient:
    """自测用：全内存假客户端，create 直接往自己的列表里加，支持回收站模拟。"""

    def __init__(self, label, items, folders, trash=None):
        self.label = label
        self.items = copy.deepcopy(items)
        self.folders = copy.deepcopy(folders)
        self.trash = copy.deepcopy(trash or [])
        self._seq = 0

    def _new_id(self):
        self._seq += 1
        return f"fake-{self.label}-{self._seq}"

    def pull(self):
        return copy.deepcopy(self.items), copy.deepcopy(self.folders)

    def pull_trash(self):
        return copy.deepcopy(self.trash)

    def create_folder(self, name):
        fid = self._new_id()
        self.folders.append({"id": fid, "name": name})
        return fid

    def create_item(self, payload):
        obj = copy.deepcopy(payload)
        obj["id"] = self._new_id()
        self.items.append(obj)
        return obj["id"]

    def delete_item(self, item_id, permanent=False):
        to_del = [i for i in self.items if i.get("id") == item_id]
        self.items = [i for i in self.items if i.get("id") != item_id]
        if not permanent:
            for it in to_del:
                it_trash = copy.deepcopy(it)
                it_trash["deletedDate"] = datetime.now().isoformat()
                self.trash.append(it_trash)
        return True

    def close(self):
        pass


# ---------------------------------------------------------------------------
# 对比引擎：产出计划（actions / 报告 / 新 state 骨架），本身不做写入
# ---------------------------------------------------------------------------

def empty_state():
    return {"pairs": {}, "hashes": {"a": {}, "b": {}}, "tombstones": {}}


def has_existing_conflict_copy(target_conflict_copies, source_rec):
    """检测目标端是否已存在一条由 source_rec 产生的冲突副本（阻断失败重试时的增殖）"""
    if not target_conflict_copies or not source_rec:
        return False
    src_uname = extract_item_username(source_rec.norm)
    src_pw = (source_rec.raw.get("login") or {}).get("password")
    src_notes = source_rec.raw.get("notes")
    src_base_name = source_rec.name.strip()
    for it in target_conflict_copies:
        it_name = (it.get("name") or "").strip()
        if CONFLICT_MARKER in it_name and it_name.startswith(src_base_name):
            it_login = it.get("login") or {}
            it_uname = it_login.get("username")
            it_pw = it_login.get("password")
            it_notes = it.get("notes")
            if source_rec.raw.get("type") == 1:
                if (it_uname or "") == (src_uname or "") and (it_pw or "") == (src_pw or ""):
                    return True
            else:
                if (it_notes or "") == (src_notes or ""):
                    return True
    return False


def plan_sync(a_recs, b_recs, state, label_a, label_b, today,
              trash_a_recs=None, trash_b_recs=None,
              conflict_copies_a=None, conflict_copies_b=None):
    report = {
        "same": [], "conflicts": [], "known_conflicts": [],
        "only_a": [], "only_b": [],
        "suspected_deletions": [], "ambiguous": [],
        "skipped_conflict_copies": 0, "with_attachments": [],
    }
    actions = []          # {"kind","from","to","rec","new_name"}
    discovered_pairs = {} # a_id -> b_id（本次新配对成功、id 都已知）
    pair_hashes = {}      # a_id -> (hash_a, hash_b) 已知配对的最新基线

    trash_a_recs = trash_a_recs or []
    trash_b_recs = trash_b_recs or []
    trash_a_hashes = {r.hash: r for r in trash_a_recs}
    trash_b_hashes = {r.hash: r for r in trash_b_recs}

    a_by_id = {r.id: r for r in a_recs}
    b_by_id = {r.id: r for r in b_recs}
    consumed_a, consumed_b = set(), set()

    def note_pair(ra, rb):
        pair_hashes[ra.id] = (ra.hash, rb.hash)
        consumed_a.add(ra.id)
        consumed_b.add(rb.id)

    # 1) state 里已有的配对
    old_pairs = dict(state.get("pairs") or {})
    new_tombstones = dict(state.get("tombstones") or {})
    for aid, bid in old_pairs.items():
        ra, rb = a_by_id.get(aid), b_by_id.get(bid)
        if ra is not None and rb is not None:
            prev = ((state.get("hashes") or {}).get("a", {}).get(aid),
                    (state.get("hashes") or {}).get("b", {}).get(bid))
            if ra.hash == rb.hash:
                report["same"].append(ra.name)
            elif prev == (ra.hash, rb.hash):
                # 这对内容在上次同步时已经保留过冲突副本、之后两边都没再改
                report["known_conflicts"].append(ra.name)
            else:
                report["conflicts"].append((ra.name, rb.name))
                if not has_existing_conflict_copy(conflict_copies_b, ra):
                    actions.append({"kind": "conflict", "from": "a", "to": "b",
                                    "rec": ra, "peer_name": rb.name,
                                    "new_name": f"{ra.name}{CONFLICT_MARKER}{label_a} {today}]"})
                if not has_existing_conflict_copy(conflict_copies_a, rb):
                    actions.append({"kind": "conflict", "from": "b", "to": "a",
                                    "rec": rb, "peer_name": ra.name,
                                    "new_name": f"{rb.name}{CONFLICT_MARKER}{label_b} {today}]"})
            note_pair(ra, rb)
        elif ra is not None or rb is not None:
            # 一边消失：疑似删除。存活方记墓碑、不补回、不删除，只报告。
            survivor, sside = (ra, "a") if ra is not None else (rb, "b")
            gone_label = label_b if sside == "a" else label_a
            report["suspected_deletions"].append((survivor.name, gone_label))
            tkey = json.dumps(list(survivor.nkey) + [survivor.hash],
                              ensure_ascii=False)
            new_tombstones[tkey] = {"name": survivor.name, "date": today}
            if sside == "a":
                consumed_a.add(survivor.id)
            else:
                consumed_b.add(survivor.id)
        # 两边都没了：配对自然消亡，什么都不做

    # 2) 未配对的条目用自然键分组
    rem_a = [r for r in a_recs if r.id not in consumed_a]
    rem_b = [r for r in b_recs if r.id not in consumed_b]
    ga, gb = {}, {}
    for r in rem_a:
        ga.setdefault(r.nkey, []).append(r)
    for r in rem_b:
        gb.setdefault(r.nkey, []).append(r)

    for key in sorted(set(ga) & set(gb), key=str):
        la = [r for r in ga[key] if r.id not in consumed_a]
        lb = [r for r in gb[key] if r.id not in consumed_b]
        if not la or not lb:
            continue

        # 阶段 2.1：精确哈希 1-to-1 优先配对（密码与自动填充选项完全一致）
        matched_pairs_in_group = []
        unmatched_a = []
        unmatched_b = list(lb)

        for ra in la:
            matching_b = [rb for rb in unmatched_b if rb.hash == ra.hash]
            if matching_b:
                matched_b = matching_b[0]
                unmatched_b.remove(matched_b)
                matched_pairs_in_group.append((ra, matched_b))
            else:
                unmatched_a.append(ra)

        for ra, rb in matched_pairs_in_group:
            discovered_pairs[ra.id] = rb.id
            report["same"].append(ra.name)
            note_pair(ra, rb)

        # 阶段 2.2：检查剩余未匹配项是否在对侧回收站中（感知对侧已删除入回收站）
        final_unmatched_a = []
        for ra in unmatched_a:
            if ra.hash in trash_b_hashes:
                # 对侧回收站中存在完全相同哈希条目 -> 判定为在对侧已删除，记入墓碑绝不复活
                report["suspected_deletions"].append((ra.name, label_b))
                tkey = json.dumps(list(ra.nkey) + [ra.hash], ensure_ascii=False)
                new_tombstones[tkey] = {"name": ra.name, "date": today}
                consumed_a.add(ra.id)
            else:
                final_unmatched_a.append(ra)

        final_unmatched_b = []
        for rb in unmatched_b:
            if rb.hash in trash_a_hashes:
                # 对侧回收站中存在完全相同哈希条目 -> 判定为在对侧已删除，记入墓碑绝不复活
                report["suspected_deletions"].append((rb.name, label_a))
                tkey = json.dumps(list(rb.nkey) + [rb.hash], ensure_ascii=False)
                new_tombstones[tkey] = {"name": rb.name, "date": today}
                consumed_b.add(rb.id)
            else:
                final_unmatched_b.append(rb)

        # 阶段 2.3：若两端各剩 1 条，建立冲突配对；若仍多对多，记入歧义
        if len(final_unmatched_a) == 1 and len(final_unmatched_b) == 1:
            ra, rb = final_unmatched_a[0], final_unmatched_b[0]
            discovered_pairs[ra.id] = rb.id
            report["conflicts"].append((ra.name, rb.name))
            if not has_existing_conflict_copy(conflict_copies_b, ra):
                actions.append({"kind": "conflict", "from": "a", "to": "b",
                                "rec": ra, "peer_name": rb.name,
                                "new_name": f"{ra.name}{CONFLICT_MARKER}{label_a} {today}]"})
            if not has_existing_conflict_copy(conflict_copies_a, rb):
                actions.append({"kind": "conflict", "from": "b", "to": "a",
                                "rec": rb, "peer_name": ra.name,
                                "new_name": f"{rb.name}{CONFLICT_MARKER}{label_b} {today}]"})
            note_pair(ra, rb)
        elif final_unmatched_a and final_unmatched_b:
            uname = extract_item_username(final_unmatched_a[0].norm)
            report["ambiguous"].append(
                (final_unmatched_a[0].name, len(final_unmatched_a), len(final_unmatched_b), uname)
            )
            for r in final_unmatched_a:
                consumed_a.add(r.id)
            for r in final_unmatched_b:
                consumed_b.add(r.id)

    # 3) 剩下的单边条目：先查对侧回收站，再查墓碑，没中墓碑的就是真正新增 -> 补到另一边
    for r in a_recs:
        if r.id in consumed_a:
            continue
        if r.hash in trash_b_hashes:
            report["suspected_deletions"].append((r.name, label_b))
            tkey = json.dumps(list(r.nkey) + [r.hash], ensure_ascii=False)
            new_tombstones[tkey] = {"name": r.name, "date": today}
            consumed_a.add(r.id)
            continue
        tkey = json.dumps(list(r.nkey) + [r.hash], ensure_ascii=False)
        if tkey in new_tombstones:
            consumed_a.add(r.id)
            continue
        report["only_a"].append(r.name)
        actions.append({"kind": "create", "from": "a", "to": "b",
                        "rec": r, "new_name": None})

    for r in b_recs:
        if r.id in consumed_b:
            continue
        if r.hash in trash_a_hashes:
            report["suspected_deletions"].append((r.name, label_a))
            tkey = json.dumps(list(r.nkey) + [r.hash], ensure_ascii=False)
            new_tombstones[tkey] = {"name": r.name, "date": today}
            consumed_b.add(r.id)
            continue
        tkey = json.dumps(list(r.nkey) + [r.hash], ensure_ascii=False)
        if tkey in new_tombstones:
            consumed_b.add(r.id)
            continue
        report["only_b"].append(r.name)
        actions.append({"kind": "create", "from": "b", "to": "a",
                        "rec": r, "new_name": None})

    for r in list(a_recs) + list(b_recs):
        if r.raw.get("attachments"):
            report["with_attachments"].append(r.name)

    new_state = {
        "pairs": {},  # apply 后由主流程回填（含 discovered 与新建产生的配对）
        "hashes": {"a": {}, "b": {}},
        "tombstones": new_tombstones,
        "_discovered_pairs": discovered_pairs,
        "_pair_hashes": {k: list(v) for k, v in pair_hashes.items()},
        "_all_hashes": {
            "a": {r.id: r.hash for r in a_recs},
            "b": {r.id: r.hash for r in b_recs},
        },
    }
    return report, actions, new_state


def finalize_state(old_state, skeleton, created_pairs):
    """created_pairs: {(from_side, from_id): new_id}（仅 create 动作产生）。"""
    pairs = {}
    hashes = {"a": {}, "b": {}}
    # 旧配对里两边都还在的已在 plan 阶段处理；这里收：已发现配对 + 已知基线
    for aid, (ha, hb) in skeleton["_pair_hashes"].items():
        bid = (old_state.get("pairs") or {}).get(aid) or \
            skeleton["_discovered_pairs"].get(aid)
        if bid:
            pairs[aid] = bid
            hashes["a"][aid] = ha
            hashes["b"][bid] = hb
    for aid, bid in skeleton["_discovered_pairs"].items():
        pairs.setdefault(aid, bid)
    for (from_side, from_id), new_id in created_pairs.items():
        if from_side == "a":
            pairs[from_id] = new_id
            h = skeleton["_all_hashes"]["a"].get(from_id)
        else:
            pairs[new_id] = from_id
            h = skeleton["_all_hashes"]["b"].get(from_id)
        if h:  # 新建条目两边内容一致，基线哈希相同
            aid = from_id if from_side == "a" else new_id
            bid = new_id if from_side == "a" else from_id
            hashes["a"][aid] = h
            hashes["b"][bid] = h
    return {"pairs": pairs, "hashes": hashes,
            "tombstones": skeleton["tombstones"]}


# ---------------------------------------------------------------------------
# 执行计划（仅 --apply 时）
# ---------------------------------------------------------------------------

def execute_actions(actions, clients, folder_maps, logger=None):
    """
    clients/folder_maps 以 'a'/'b' 为键。返回 created_pairs。
    分阶段有序执行：
    【阶段一】：先对主库 (Side A) 执行写入 (act['to'] == 'a')；
    【阶段二】：主库写入全部完成后，再对备库 (Side B) 执行写入 (act['to'] == 'b')。
    若某阶段出错，能精准定位具体是哪一端（主库或备库）出现问题。
    """
    created_pairs = {}
    actions_to_a = [act for act in actions if act.get("to") == "a"]
    actions_to_b = [act for act in actions if act.get("to") == "b"]

    def _run_stage(stage_actions, target_side, stage_label):
        if not stage_actions:
            return
        dst = clients[target_side]
        side_label = getattr(dst, "label", target_side)
        if logger:
            logger(f"--- 阶段开始：同步写入{stage_label} [{side_label}] (共 {len(stage_actions)} 项) ---")
        for idx, act in enumerate(stage_actions, 1):
            rec = act["rec"]
            fname = rec.norm.get("folder")
            target_fid = None
            if fname:
                fmap = folder_maps[target_side]
                if fname not in fmap:
                    try:
                        fmap[fname] = dst.create_folder(fname)
                    except Exception as e:
                        raise BwError(f"[{stage_label} {side_label}] 创建文件夹 [{fname}] 失败：{str(e)}")
                target_fid = fmap[fname]
            payload = build_create_payload(rec, target_fid, act.get("new_name"))
            try:
                new_id = dst.create_item(payload)
            except Exception as e:
                raise BwError(f"[{stage_label} {side_label}] 创建条目 [{act.get('new_name') or rec.name}] 失败：{str(e)}")
            if act["kind"] == "create" and new_id:
                created_pairs[(act["from"], rec.id)] = new_id
            if logger:
                logger(f"  [{idx}/{len(stage_actions)}] 已写入 [{act.get('new_name') or rec.name}] -> {side_label}")

    # 阶段一：先对主库 (Side A) 执行同步写入
    _run_stage(actions_to_a, "a", "主库(A)")
    # 阶段二：完成后再对备库 (Side B) 执行同步写入
    _run_stage(actions_to_b, "b", "备库(B)")

    return created_pairs


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

def render_report(report, label_a, label_b, applied):
    L = []
    L.append(f"=== bw_sync 报告（{'已执行写入' if applied else '只读预览，未写入'}）===")
    L.append(f"相同（跳过）：{len(report['same'])} 条")
    L.append(f"仅 {label_a} 有 -> 将补到 {label_b}：{len(report['only_a'])} 条"
             + (("：" + "、".join(report["only_a"])) if report["only_a"] else ""))
    L.append(f"仅 {label_b} 有 -> 将补到 {label_a}：{len(report['only_b'])} 条"
             + (("：" + "、".join(report["only_b"])) if report["only_b"] else ""))
    L.append(f"配对但内容不同（保留两份冲突副本）：{len(report['conflicts'])} 对")
    for a_name, b_name in report["conflicts"]:
        L.append(f"  - {a_name}  <->  {b_name}")
    if report.get("known_conflicts"):
        L.append(f"已保留过冲突副本、本次两边均未再改（跳过）："
                 f"{len(report['known_conflicts'])} 对")
    L.append(f"疑似单边删除（不处理、只报告）：{len(report['suspected_deletions'])} 条")
    for name, gone in report["suspected_deletions"]:
        L.append(f"  - {name}（在 {gone} 已不见）")
    if report["ambiguous"]:
        L.append(f"自然键重名、无法自动配对（人工处理）：{len(report['ambiguous'])} 组")
        for item in report["ambiguous"]:
            if len(item) == 4:
                name, na, nb, uname = item
                user_info = f"，账号: {uname}" if uname else ""
                L.append(f"  - {name}{user_info}（{label_a} {na} 条 / {label_b} {nb} 条）")
            else:
                name, na, nb = item
                L.append(f"  - {name}（{label_a} {na} 条 / {label_b} {nb} 条）")
    if report["skipped_conflict_copies"]:
        L.append(f"已存在的冲突副本（跳过）：{report['skipped_conflict_copies']} 条")
    if report["with_attachments"]:
        L.append("注意：以下条目带附件，v1 只同步条目本身、不搬附件："
                 + "、".join(sorted(set(report["with_attachments"]))))
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 一轮同步的主流程（真实与自测共用）
# ---------------------------------------------------------------------------

def prepare_recs(items, folders, is_trash=False):
    fmap = folder_name_map(folders)
    recs, conflict_copies = [], []
    for it in items or []:
        if not is_trash and it.get("deletedDate"):
            continue                      # 正常库过滤回收站
        if it.get("organizationId"):
            continue                      # 组织条目不在 v1 范围
        if is_conflict_copy(it):
            conflict_copies.append(it)
            continue                      # 冲突副本是终点，不再参与同步
        recs.append(Rec(it, fmap))
    return recs, conflict_copies


def run_one_round(client_a, client_b, state, apply, today, logger=None):
    items_a, folders_a = client_a.pull()
    items_b, folders_b = client_b.pull()
    trash_a = client_a.pull_trash() if hasattr(client_a, "pull_trash") else []
    trash_b = client_b.pull_trash() if hasattr(client_b, "pull_trash") else []
    a_recs, cc_a = prepare_recs(items_a, folders_a, is_trash=False)
    b_recs, cc_b = prepare_recs(items_b, folders_b, is_trash=False)
    trash_a_recs, _ = prepare_recs(trash_a, folders_a, is_trash=True)
    trash_b_recs, _ = prepare_recs(trash_b, folders_b, is_trash=True)
    report, actions, skeleton = plan_sync(
        a_recs, b_recs, state, client_a.label, client_b.label, today,
        trash_a_recs=trash_a_recs, trash_b_recs=trash_b_recs,
        conflict_copies_a=cc_a, conflict_copies_b=cc_b
    )
    report["skipped_conflict_copies"] = len(cc_a) + len(cc_b)
    created_pairs = {}
    if apply and actions:
        folder_maps = {
            "a": {f.get("name"): f.get("id") for f in folders_a or []},
            "b": {f.get("name"): f.get("id") for f in folders_b or []},
        }
        created_pairs = execute_actions(
            actions, {"a": client_a, "b": client_b}, folder_maps, logger=logger)
    new_state = finalize_state(state, skeleton, created_pairs) if apply else state
    return report, new_state


# ---------------------------------------------------------------------------
# 自测：用 Fake 客户端把正常/异常分支都实际跑一遍
# ---------------------------------------------------------------------------

def _item(id_, name, pw="pw", user="u@x", folder_id=None, uri=None, **kw):
    actual_uri = uri if uri is not None else f"https://{name.lower()}.example"
    it = {"id": id_, "type": 1, "name": name, "folderId": folder_id,
          "favorite": False, "reprompt": 0, "notes": None, "fields": [],
          "login": {"username": user, "password": pw,
                    "uris": [{"uri": actual_uri, "match": None}],
                    "totp": None}}
    it.update(kw)
    return it


def selftest():
    today = "2026-10-23"
    fails = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    # 场景1：两边相同（id 不同）-> 配对、无动作；apply 后重跑仍无动作
    ca = FakeBwClient("A", [_item("a1", "GitHub")], [])
    cb = FakeBwClient("B", [_item("b1", "GitHub")], [])
    rep, st = run_one_round(ca, cb, empty_state(), True, today)
    check("相同条目无补齐无冲突",
          not rep["only_a"] and not rep["only_b"] and not rep["conflicts"])
    check("相同条目已配对", st["pairs"].get("a1") == "b1")
    rep2, _ = run_one_round(ca, cb, st, True, today)
    check("相同条目重跑幂等",
          not rep2["only_a"] and not rep2["only_b"] and not rep2["conflicts"])

    # 场景2：仅 A 有（含文件夹）-> 补到 B，文件夹一并建；重跑幂等
    ca = FakeBwClient("A", [_item("a1", "银行", folder_id="fa1")],
                      [{"id": "fa1", "name": "财务"}])
    cb = FakeBwClient("B", [], [])
    rep, st = run_one_round(ca, cb, empty_state(), True, today)
    names_b = [i["name"] for i in cb.items]
    folders_b = [f["name"] for f in cb.folders]
    check("仅A有补到B", rep["only_a"] == ["银行"] and names_b == ["银行"])
    check("文件夹同步创建", folders_b == ["财务"])
    rep2, _ = run_one_round(ca, cb, st, True, today)
    check("补齐后重跑幂等", not rep2["only_a"] and not rep2["only_b"])

    # 场景3：配对但密码不同 -> 两边各多一条对方的冲突副本；重跑不再增殖
    ca = FakeBwClient("A", [_item("a1", "邮箱", pw="old")], [])
    cb = FakeBwClient("B", [_item("b1", "邮箱", pw="new")], [])
    rep, st = run_one_round(ca, cb, empty_state(), True, today)
    check("冲突判定", len(rep["conflicts"]) == 1)
    check("A侧收到B版冲突副本",
          any(CONFLICT_MARKER in i["name"] and i["login"]["password"] == "new"
              for i in ca.items))
    check("B侧收到A版冲突副本",
          any(CONFLICT_MARKER in i["name"] and i["login"]["password"] == "old"
              for i in cb.items))
    n_a, n_b = len(ca.items), len(cb.items)
    rep2, st2 = run_one_round(ca, cb, st, True, today)
    check("冲突副本不增殖", len(ca.items) == n_a and len(cb.items) == n_b
          and not rep2["conflicts"])
    rep3, st3 = run_one_round(ca, cb, empty_state(), True, today)
    check("即便state丢失重跑冲突副本亦不增殖", len(ca.items) == n_a and len(cb.items) == n_b)

    # 场景4：已配对条目在 B 被删 -> 疑似删除报告、不复活；再跑仍不复活
    ca = FakeBwClient("A", [_item("a1", "论坛")], [])
    cb = FakeBwClient("B", [_item("b1", "论坛")], [])
    _, st = run_one_round(ca, cb, empty_state(), True, today)
    cb.items = []  # 模拟在 B 删除
    rep, st = run_one_round(ca, cb, st, True, today)
    check("删除被识别为疑似删除", len(rep["suspected_deletions"]) == 1)
    check("删除不复活", len(cb.items) == 0)
    rep, st = run_one_round(ca, cb, st, True, today)
    check("墓碑持续生效", len(cb.items) == 0 and not rep["only_a"])

    # 场景5：自然键重名且内容皆不同（A 两条、B 两条均无法自动决断）-> 歧义，交由人工处理
    ca = FakeBwClient("A", [_item("a1", "同名", pw="p1", uri="https://example.com/1"),
                            _item("a2", "同名", pw="p2", uri="https://example.com/2")], [])
    cb = FakeBwClient("B", [_item("b1", "同名", pw="p3", uri="https://example.com/3"),
                            _item("b2", "同名", pw="p4", uri="https://example.com/4")], [])
    rep, _ = run_one_round(ca, cb, empty_state(), True, today)
    check("多对多内容皆不同进歧义清单且不写入",
          len(rep["ambiguous"]) == 1 and len(cb.items) == 2 and len(ca.items) == 2)

    # 场景6：回收站条目与组织条目被忽略；带附件条目同步但被警告
    ca = FakeBwClient("A", [
        _item("a1", "已删", deletedDate="2026-10-01T00:00:00Z"),
        _item("a2", "组织条目", organizationId="org-1"),
        _item("a3", "带附件", attachments=[{"id": "x", "fileName": "k.txt"}]),
    ], [])
    cb = FakeBwClient("B", [], [])
    rep, _ = run_one_round(ca, cb, empty_state(), True, today)
    names_b = [i["name"] for i in cb.items]
    check("回收站/组织条目不同步，附件条目同步且警告",
          names_b == ["带附件"] and rep["with_attachments"] == ["带附件"])

    # 场景7：只读模式绝不写入、不改 state
    ca = FakeBwClient("A", [_item("a1", "只读测试")], [])
    cb = FakeBwClient("B", [], [])
    st0 = empty_state()
    rep, st1 = run_one_round(ca, cb, st0, False, today)
    check("只读模式不写入不改state",
          rep["only_a"] == ["只读测试"] and len(cb.items) == 0 and st1 is st0)

    # 场景8：同一网站注册不同账号不冲突（域名相同、账号不同分别独立配对）
    ca = FakeBwClient("A", [
        _item("a_gh1", "GitHub 主账号", user="alice", uri="https://github.com/login"),
        _item("a_gh2", "GitHub 备用账号", user="bob", uri="https://github.com/login"),
    ], [])
    cb = FakeBwClient("B", [
        _item("b_gh1", "GitHub 官网 (alice)", user="alice", uri="https://www.github.com"),
    ], [])
    rep, st = run_one_round(ca, cb, empty_state(), True, today)
    check("同一域名不同账号不冲突且各自配对",
          st["pairs"].get("a_gh1") == "b_gh1" and rep["only_a"] == ["GitHub 备用账号"])

    # 场景9：单端数据源内部完全重复数据检测与清理（域名+账号+密码完全一致）
    dup_items = [
        _item("d1", "V2EX", pw="p123", user="dev", uri="https://v2ex.com", favorite=True),
        _item("d2", "V2EX 副本", pw="p123", user="dev", uri="https://v2ex.com"),
        _item("d3", "V2EX 另一账号", pw="p456", user="tester", uri="https://v2ex.com"),
    ]
    ca_dup = FakeBwClient("A", dup_items, [])
    dup_res = find_duplicates_in_items(ca_dup.items)
    check("重复数据识别准确（域名+账号+密码完全一致）",
          dup_res["duplicate_groups_count"] == 1 and dup_res["duplicate_items_count"] == 1
          and dup_res["groups"][0]["keep"]["id"] == "d1"
          and dup_res["groups"][0]["duplicates"][0]["id"] == "d2")

    clean_res = clean_duplicates(ca_dup, [dup_res["groups"][0]["duplicates"][0]["id"]])
    check("重复副本安全清理且保留原件",
          clean_res["deleted_count"] == 1 and len(ca_dup.items) == 2
          and {i["id"] for i in ca_dup.items} == {"d1", "d3"})

    # 场景10：同域名同账号多条目，通过精确哈希 1-to-1 优先配对成功（自动消除假重名）
    ca_m = FakeBwClient("A", [
        _item("a_m1", "AppleID", pw="pass1", user="my@apple.com", uri="https://iforgot.apple.com/login"),
        _item("a_m2", "AppleID", pw="pass2", user="my@apple.com", uri="https://iforgot.apple.com/reset"),
    ], [])
    cb_m = FakeBwClient("B", [
        _item("b_m2", "AppleID", pw="pass2", user="my@apple.com", uri="https://iforgot.apple.com/reset"),
        _item("b_m1", "AppleID", pw="pass1", user="my@apple.com", uri="https://iforgot.apple.com/login"),
    ], [])
    rep_m, st_m = run_one_round(ca_m, cb_m, empty_state(), True, today)
    check("多重条目哈希优先精确配对成功无歧义",
          len(rep_m["same"]) == 2 and not rep_m["ambiguous"]
          and st_m["pairs"].get("a_m1") == "b_m1"
          and st_m["pairs"].get("a_m2") == "b_m2")

    # 场景11：回收站联动感知与防复活墓碑（一端删入回收站，对端不复活并记入墓碑）
    trash_item = _item("b_trash", "xn--2os8j.us.ci", pw="pw1", user="lnq1208@163.com",
                       uri="https://xn--2os8j.us.ci/login", deletedDate="2026-10-25T17:00:00Z")
    ca_t = FakeBwClient("A", [
        _item("a_reg", "xn--2os8j.us.ci", pw="p_reg", user="lnq1208@163.com", uri="https://xn--2os8j.us.ci/register"),
        _item("a_log", "xn--2os8j.us.ci", pw="pw1", user="lnq1208@163.com", uri="https://xn--2os8j.us.ci/login"),
    ], [])
    cb_t = FakeBwClient("B", [
        _item("b_reg", "xn--2os8j.us.ci", pw="p_reg", user="lnq1208@163.com", uri="https://xn--2os8j.us.ci/register"),
    ], [], trash=[trash_item])
    rep_t, st_t = run_one_round(ca_t, cb_t, empty_state(), True, today)
    check("回收站感知阻断复活并精准识别为删除",
          st_t["pairs"].get("a_reg") == "b_reg"
          and len(rep_t["suspected_deletions"]) == 1
          and not rep_t["only_a"]
          and not rep_t["ambiguous"])

    # 场景12：自动填充选项多 URI 顺序无关性
    item_uri1 = _item("u1", "站点", uri="https://a.com")
    item_uri1["login"]["uris"] = [{"uri": "https://a.com/login"}, {"uri": "https://a.com/sso"}]
    item_uri2 = _item("u2", "站点", uri="https://a.com")
    item_uri2["login"]["uris"] = [{"uri": "https://a.com/sso"}, {"uri": "https://a.com/login"}]
    norm1 = normalize_item(item_uri1, {})
    norm2 = normalize_item(item_uri2, {})
    check("自动填充多URI乱序规范化哈希一致", content_hash(norm1) == content_hash(norm2))

    total_scenarios = 12
    print(f"\n自测完成：{total_scenarios - len(fails)}/{total_scenarios} 组通过" if not fails
          else f"\n自测有失败：{fails}")
    return 1 if fails else 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def get_pair_key(side_a, side_b):
    ca = re.sub(r"[^a-zA-Z0-9_\-]", "", str(side_a)).strip()
    cb = re.sub(r"[^a-zA-Z0-9_\-]", "", str(side_b)).strip()
    return "__".join(sorted([ca, cb]))


def resolve_pair_state_file(base_dir, side_a, side_b, custom_state_arg=None):
    if custom_state_arg and Path(custom_state_arg).name != "bw-sync-state.json":
        return Path(custom_state_arg)
    pair_slug = get_pair_key(side_a, side_b)
    target = Path(base_dir) / f"bw-sync-state-{pair_slug}.json"
    legacy = Path(base_dir) / "bw-sync-state.json"
    if not target.exists() and legacy.exists():
        try:
            shutil.copyfile(legacy, target)
        except Exception:
            pass
    return target


def main(argv=None):
    ap = argparse.ArgumentParser(description="多端 Bitwarden / Vaultwarden 双向同步")
    ap.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    ap.add_argument("--state", default=str(Path(__file__).with_name("bw-sync-state.json")))
    ap.add_argument("--side-a", default=None, help="指定要同步的来源 A 键名（若 sides 有多个来源时可选）")
    ap.add_argument("--side-b", default=None, help="指定要同步的来源 B 键名（若 sides 有多个来源时可选）")
    ap.add_argument("--apply", action="store_true", help="真正执行写入（默认只读）")
    ap.add_argument("--selftest", action="store_true", help="离线自测对比逻辑")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"找不到配置文件 {cfg_path}\n"
              "先把 config.example.json 复制为 config.json 并填好各来源的地址和邮箱。",
              file=sys.stderr)
        return 2
    cfg = load_json(cfg_path)
    sides = cfg.get("sides") or {}
    if len(sides) < 2:
        print("config.json 的 sides 至少需要配置两个来源以进行同步。", file=sys.stderr)
        return 2

    all_keys = list(sides.keys())
    side_a_key = args.side_a
    side_b_key = args.side_b

    if not side_a_key or not side_b_key:
        if len(all_keys) == 2:
            side_a_key, side_b_key = all_keys[0], all_keys[1]
        else:
            side_a_key, side_b_key = all_keys[0], all_keys[1]
            print(f"提示：检测到配置文件中包含 {len(all_keys)} 个来源 ({', '.join(all_keys)})，"
                  f"本次默认对比同步前两端 [{side_a_key} ↔ {side_b_key}]。"
                  f"可通过 --side-a 与 --side-b 参数指定任意两端进行配对同步。", file=sys.stderr)

    if side_a_key not in sides:
        print(f"错误：来源 A [{side_a_key}] 不存在于 config.json 中。可选来源：{', '.join(all_keys)}", file=sys.stderr)
        return 2
    if side_b_key not in sides:
        print(f"错误：来源 B [{side_b_key}] 不存在于 config.json 中。可选来源：{', '.join(all_keys)}", file=sys.stderr)
        return 2
    if side_a_key == side_b_key:
        print(f"错误：来源 A 与来源 B 不能为同一来源 [{side_a_key}]。", file=sys.stderr)
        return 2

    bw_path = cfg.get("bw") or shutil.which("bw") or shutil.which("bw.exe")
    if not bw_path:
        print("找不到 bw CLI。请先安装官方 Bitwarden CLI，"
              "或在 config.json 里用 \"bw\" 写 bw.exe 的完整路径。", file=sys.stderr)
        return 2

    target_state_path = resolve_pair_state_file(
        Path(__file__).parent, side_a_key, side_b_key, args.state
    )
    state = load_json(target_state_path, empty_state())
    today = datetime.now().strftime("%Y-%m-%d")
    keys = [side_a_key, side_b_key]
    clients = {}
    try:
        for k in keys:
            clients[k] = RealBwClient(k, sides[k], bw_path, Path(__file__).parent)
        report, new_state = run_one_round(
            clients[keys[0]], clients[keys[1]], state, args.apply, today)
    except BwError as e:
        print(f"出错：{e}", file=sys.stderr)
        return 2
    finally:
        for c in clients.values():
            c.close()

    label_a = sides[keys[0]].get("label", keys[0])
    label_b = sides[keys[1]].get("label", keys[1])
    # plan_sync 用的是客户端 label，这里报告已在 run_one_round 内生成好文本所需数据
    print(render_report(report, label_a, label_b, args.apply))
    if args.apply:
        tmp = target_state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(new_state, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(target_state_path)
        print(f"state 已保存：{target_state_path}")
    else:
        print("（只读模式：没有写入任何数据，state 未更新。确认无误后加 --apply 执行。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
