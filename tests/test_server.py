#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_server.py — Unit tests for CloudMirror REST API & web server.
"""

import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import HTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from server import CloudMirrorHandler, datastore, s3_manager
import bw_sync


class TestServerAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ["BW_SYNC_MOCK_ONLY"] = "1"
        # 1. 物理备份现有配置文件与存储文件，绝不让测试覆盖真实数据
        cls._saved_config_json = (REPO_ROOT / "config.json").read_bytes() if (REPO_ROOT / "config.json").exists() else None
        cls._saved_config_prod = (REPO_ROOT / "config.prod.json").read_bytes() if (REPO_ROOT / "config.prod.json").exists() else None
        cls._saved_config_dev = (REPO_ROOT / "config.dev.json").read_bytes() if (REPO_ROOT / "config.dev.json").exists() else None
        cls._saved_sources = (REPO_ROOT / "data" / "sources.json").read_bytes() if (REPO_ROOT / "data" / "sources.json").exists() else None

        # Start server on ephemeral port for tests
        cls.server = HTTPServer(("127.0.0.1", 0), CloudMirrorHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        import os
        os.environ.pop("BW_SYNC_MOCK_ONLY", None)
        cls.server.shutdown()
        cls.server.server_close()
        # 2. 无论测试成功或失败，强制 100% 完整恢复用户配置与存储数据
        if cls._saved_config_json is not None:
            (REPO_ROOT / "config.json").write_bytes(cls._saved_config_json)
        if cls._saved_config_prod is not None:
            (REPO_ROOT / "config.prod.json").write_bytes(cls._saved_config_prod)
        if cls._saved_config_dev is not None:
            (REPO_ROOT / "config.dev.json").write_bytes(cls._saved_config_dev)
        if cls._saved_sources is not None:
            (REPO_ROOT / "data" / "sources.json").write_bytes(cls._saved_sources)
        test_file = REPO_ROOT / "config.test.json"
        if test_file.exists():
            try:
                test_file.unlink()
            except Exception:
                pass

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def test_static_index(self):
        """Web root / should serve HTML with CloudMirror in title."""
        req = urllib.request.Request(self._url("/"))
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn("CloudMirror", content)
            self.assertIn("多云数据双向对比与同步备份控制台", content)

    def test_static_css_and_js(self):
        """CSS and JS assets must be accessible."""
        with urllib.request.urlopen(self._url("/style.css")) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/css", resp.headers.get("Content-Type", ""))

        with urllib.request.urlopen(self._url("/app.js")) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("javascript", resp.headers.get("Content-Type", ""))

    def test_api_status(self):
        """API /api/status returns app info and strategy."""
        with urllib.request.urlopen(self._url("/api/status")) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("app"), "CloudMirror")
            self.assertIn("只增不改不删", data.get("strategy", ""))

    def test_api_bitwarden_sources(self):
        """API /api/bitwarden/sources returns Bitwarden source list."""
        with urllib.request.urlopen(self._url("/api/bitwarden/sources")) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertGreaterEqual(len(data.get("sources", [])), 2)

    def test_api_s3_sources(self):
        """API /api/s3/sources returns S3 source list and note tags."""
        with urllib.request.urlopen(self._url("/api/s3/sources")) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertGreaterEqual(len(data.get("sources", [])), 2)
            # Verify note software tags exist
            sources = data.get("sources", [])
            all_tags = [t for s in sources for t in s.get("tags", [])]
            self.assertTrue(any("Obsidian" in t or "Joplin" in t for t in all_tags))

    def test_api_bitwarden_sync(self):
        """API /api/bitwarden/sync executes dry-run sync."""
        sources = datastore.list_bw_sources()
        self.assertGreaterEqual(len(sources), 2)
        payload = json.dumps({
            "source_a": sources[0]["id"],
            "source_b": sources[1]["id"],
            "apply": False
        }).encode("utf-8")
        req = urllib.request.Request(self._url("/api/bitwarden/sync"), data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("mode"), "dry-run")
            self.assertIn("report", data)

    def test_api_bitwarden_sync_async(self):
        """API /api/bitwarden/sync with async=True and /api/bitwarden/sync/status."""
        sources = datastore.list_bw_sources()
        self.assertGreaterEqual(len(sources), 2)
        payload = json.dumps({
            "source_a": sources[0]["id"],
            "source_b": sources[1]["id"],
            "apply": False,
            "async": True
        }).encode("utf-8")
        req = urllib.request.Request(self._url("/api/bitwarden/sync"), data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertTrue(data.get("async"))
            job_id = data.get("job_id")
            self.assertTrue(job_id)

        # Query status with job_id
        finished = False
        for _ in range(50):
            req_status = urllib.request.Request(self._url(f"/api/bitwarden/sync/status?job_id={job_id}"))
            with urllib.request.urlopen(req_status) as resp:
                self.assertEqual(resp.status, 200)
                status_data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(status_data.get("success"))
                job = status_data.get("job")
                self.assertIsNotNone(job)
                if job.get("status") in ("success", "error"):
                    self.assertEqual(job.get("status"), "success")
                    self.assertIn("report", job)
                    finished = True
                    break
            time.sleep(0.05)
        self.assertTrue(finished)

    def test_api_s3_sync_multiple(self):
        """API /api/s3/sync executes multi-S3 source mirror sync."""
        sources = s3_manager.list_sources()
        self.assertGreaterEqual(len(sources), 2)
        payload = json.dumps({
            "sources": [sources[0]["id"], sources[1]["id"]],
            "mode": "mirror"
        }).encode("utf-8")
        req = urllib.request.Request(self._url("/api/s3/sync"), data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertGreaterEqual(data.get("synced_objects", 0), 0)

    def test_api_s3_tags_duplicate_protection(self):
        """API /api/s3/tags must reject duplicate tag names with HTTP 400."""
        import uuid
        unique_name = f"唯一标签测试_{uuid.uuid4().hex[:6]}"
        # Add tag
        payload = json.dumps({"name": unique_name, "color": "#10b981"}).encode("utf-8")
        req = urllib.request.Request(self._url("/api/s3/tags"), data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 201)

        # Try duplicate
        req_dup = urllib.request.Request(self._url("/api/s3/tags"), data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req_dup) as resp:
                self.fail("Duplicate tag should return HTTP 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_api_s3_pair_compare_and_sync(self):
        """API /api/s3/pair/compare and sync between primary and backup bucket."""
        obsidian_buckets = s3_manager.get_sources_by_tag("Obsidian")
        self.assertGreaterEqual(len(obsidian_buckets), 2)
        primary_id = obsidian_buckets[0]["id"]
        backup_id = obsidian_buckets[1]["id"]

        # Compare
        payload_cmp = json.dumps({
            "primary_id": primary_id,
            "backup_id": backup_id,
            "tag": "Obsidian"
        }).encode("utf-8")
        req = urllib.request.Request(self._url("/api/s3/pair/compare"), data=payload_cmp, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("primary", {}).get("id"), primary_id)

        # Sync
        payload_sync = json.dumps({
            "primary_id": primary_id,
            "backup_id": backup_id,
            "tag": "Obsidian",
            "apply": True
        }).encode("utf-8")
        req_sync = urllib.request.Request(self._url("/api/s3/pair/sync"), data=payload_sync, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req_sync) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("mode"), "apply")

    def test_api_schedules(self):
        """API /api/schedules lists schedules and triggers execution."""
        with urllib.request.urlopen(self._url("/api/schedules")) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            schedules = data.get("schedules", [])
            self.assertGreaterEqual(len(schedules), 1)

        # Trigger schedule run
        sched_id = schedules[0]["id"]
        payload = json.dumps({"id": sched_id}).encode("utf-8")
        req = urllib.request.Request(self._url("/api/schedules/run"), data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res.get("success"))

    def test_api_config_get_and_post(self):
        """API /api/config gets and posts config to config.json."""
        # GET config
        with urllib.request.urlopen(self._url("/api/config")) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("config", data)

        # POST config
        test_cfg = {
            "config": {
                "bw": "",
                "sides": {
                    "node": {
                        "label": "Test NodeWarden",
                        "server": "https://test-node.com",
                        "email": "test@example.com",
                        "password_env": "TEST_PW_ENV"
                    },
                    "vault": {
                        "label": "Test Vaultwarden",
                        "server": "https://test-vault.com",
                        "email": "test@example.com",
                        "password_env": "TEST_VAULT_PW_ENV"
                    }
                }
            }
        }
        payload = json.dumps(test_cfg).encode("utf-8")
        req = urllib.request.Request(self._url("/api/config"), data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res.get("success"))

    def test_api_update_bitwarden_and_s3_sources(self):
        """API PUT /api/bitwarden/sources/:id and /api/s3/sources/:id updates existing sources."""
        # Update Bitwarden source
        bw_sources = datastore.list_bw_sources()
        target_bw_id = bw_sources[0]["id"]
        update_bw_payload = json.dumps({"name": "Updated BW Name", "email": "new_email@example.com"}).encode("utf-8")
        req = urllib.request.Request(self._url(f"/api/bitwarden/sources/{target_bw_id}"), data=update_bw_payload, headers={"Content-Type": "application/json"}, method="PUT")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("source", {}).get("name"), "Updated BW Name")

        # Update S3 source
        s3_sources = s3_manager.list_sources()
        target_s3_id = s3_sources[0]["id"]
        update_s3_payload = json.dumps({"name": "Updated S3 Name", "prefix": "new-prefix/"}).encode("utf-8")
        req_s3 = urllib.request.Request(self._url(f"/api/s3/sources/{target_s3_id}"), data=update_s3_payload, headers={"Content-Type": "application/json"}, method="PUT")
        with urllib.request.urlopen(req_s3) as resp:
            self.assertEqual(resp.status, 200)
            res_s3 = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res_s3.get("success"))
            self.assertEqual(res_s3.get("source", {}).get("name"), "Updated S3 Name")

    def test_password_change_detection_preserves_timestamp_when_unchanged(self):
        """Updating name/email/endpoint without changing password MUST preserve password_updated_at."""
        # 1. Test Bitwarden Source
        bw_sources = datastore.list_bw_sources()
        target_bw = bw_sources[0]
        bw_id = target_bw["id"]
        orig_pw = target_bw.get("password_env", "")
        orig_ts = target_bw.get("password_updated_at")

        # PUT update without changing password
        payload_unchanged = json.dumps({
            "name": "BW Same PW",
            "password_env": orig_pw
        }).encode("utf-8")
        req1 = urllib.request.Request(self._url(f"/api/bitwarden/sources/{bw_id}"), data=payload_unchanged, headers={"Content-Type": "application/json"}, method="PUT")
        with urllib.request.urlopen(req1) as resp1:
            data1 = json.loads(resp1.read().decode("utf-8"))
            self.assertTrue(data1.get("success"))
            self.assertFalse(data1.get("password_changed"), "Password was unchanged, password_changed must be False")
            self.assertEqual(data1.get("source", {}).get("password_updated_at"), orig_ts, "Timestamp must NOT change if password not modified")

        # PUT update WITH modified password
        new_pw = f"{orig_pw}_rot_{time.time()}"
        payload_changed = json.dumps({
            "name": "BW Changed PW",
            "password_env": new_pw
        }).encode("utf-8")
        req2 = urllib.request.Request(self._url(f"/api/bitwarden/sources/{bw_id}"), data=payload_changed, headers={"Content-Type": "application/json"}, method="PUT")
        with urllib.request.urlopen(req2) as resp2:
            data2 = json.loads(resp2.read().decode("utf-8"))
            self.assertTrue(data2.get("success"))
            self.assertTrue(data2.get("password_changed"), "Password was changed, password_changed must be True")
            self.assertNotEqual(data2.get("source", {}).get("password_updated_at"), orig_ts, "Timestamp must update when password is changed")

        # 2. Test S3 Source
        s3_sources = s3_manager.list_sources()
        target_s3 = s3_sources[0]
        s3_id = target_s3["id"]
        orig_s3_sk = target_s3.get("secret_key", "")
        orig_s3_ts = target_s3.get("password_updated_at")

        # PUT update with unchanged secret key (or masked)
        payload_s3_unchanged = json.dumps({
            "name": "S3 Same Key",
            "secret_key": orig_s3_sk
        }).encode("utf-8")
        req3 = urllib.request.Request(self._url(f"/api/s3/sources/{s3_id}"), data=payload_s3_unchanged, headers={"Content-Type": "application/json"}, method="PUT")
        with urllib.request.urlopen(req3) as resp3:
            data3 = json.loads(resp3.read().decode("utf-8"))
            self.assertTrue(data3.get("success"))
            self.assertFalse(data3.get("password_changed"), "S3 key unchanged, password_changed must be False")
            self.assertEqual(data3.get("source", {}).get("password_updated_at"), orig_s3_ts, "S3 timestamp must NOT change if key not modified")

        # PUT update with CHANGED secret key
        new_s3_sk = f"s3_key_rot_{time.time()}"
        payload_s3_changed = json.dumps({
            "name": "S3 Changed Key",
            "secret_key": new_s3_sk
        }).encode("utf-8")
        req4 = urllib.request.Request(self._url(f"/api/s3/sources/{s3_id}"), data=payload_s3_changed, headers={"Content-Type": "application/json"}, method="PUT")
        with urllib.request.urlopen(req4) as resp4:
            data4 = json.loads(resp4.read().decode("utf-8"))
            self.assertTrue(data4.get("success"))
            self.assertTrue(data4.get("password_changed"), "S3 key was changed, password_changed must be True")
            self.assertNotEqual(data4.get("source", {}).get("password_updated_at"), orig_s3_ts, "S3 timestamp must update when key is changed")

    def test_config_file_multi_sources_lifecycle(self):
        """API /api/config supports arbitrary N sides, additions, deletions, and validation."""
        import urllib.error

        # 1. Fetch current config
        with urllib.request.urlopen(self._url("/api/config")) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("config", data)

        # 2. Try saving config with < 2 sides -> must fail with 400
        invalid_cfg = {
            "bw": "",
            "sides": {
                "single_node": {
                    "label": "Only One",
                    "server": "https://vault.example.com",
                    "email": "user@example.com",
                    "password_env": "BW_PW_ONE"
                }
            }
        }
        req_bad = urllib.request.Request(
            self._url("/api/config"),
            data=json.dumps({"config": invalid_cfg}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req_bad) as resp_bad:
                self.assertNotEqual(resp_bad.status, 200)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

        # 3. Save config with 3 sides (multi-source addition)
        multi_cfg = {
            "bw": "",
            "sides": {
                "node": {
                    "label": "NodeWarden Primary",
                    "server": "https://node.example.com",
                    "email": "node@example.com",
                    "password_env": "BW_SYNC_NODE_PASSWORD"
                },
                "vault": {
                    "label": "Vaultwarden Secondary",
                    "server": "https://vault.example.com",
                    "email": "vault@example.com",
                    "password_env": "BW_SYNC_VAULT_PASSWORD"
                },
                "third_party": {
                    "label": "Third Party Cloud",
                    "server": "https://vault.bitwarden.com",
                    "email": "cloud@example.com",
                    "password_env": "BW_SYNC_CLOUD_PASSWORD"
                }
            }
        }
        req_multi = urllib.request.Request(
            self._url("/api/config"),
            data=json.dumps({"config": multi_cfg}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_multi) as resp_multi:
            self.assertEqual(resp_multi.status, 200)
            res_data = json.loads(resp_multi.read().decode("utf-8"))
            self.assertTrue(res_data.get("success"))

        # Verify datastore has 3 sources and includes third_party
        all_bw = datastore.list_bw_sources()
        self.assertGreaterEqual(len(all_bw), 3)
        self.assertTrue(any(s.get("name") == "Third Party Cloud" for s in all_bw))

    def test_config_profiles_management(self):
        """API /api/config/profiles lists profiles and supports profile switching."""
        # 1. List profiles
        with urllib.request.urlopen(self._url("/api/config/profiles")) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            profiles = data.get("profiles", [])
            p_ids = [p["id"] for p in profiles]
            self.assertIn("prod", p_ids)
            self.assertIn("dev", p_ids)

        # 2. Switch to dev profile
        payload_sw = json.dumps({"profile": "dev"}).encode("utf-8")
        req_sw = urllib.request.Request(self._url("/api/config/switch"), data=payload_sw, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req_sw) as resp_sw:
            self.assertEqual(resp_sw.status, 200)
            data_sw = json.loads(resp_sw.read().decode("utf-8"))
            self.assertTrue(data_sw.get("success"))
            self.assertEqual(data_sw.get("active_profile"), "dev")

        # 3. Switch back to prod profile
        payload_prod = json.dumps({"profile": "prod"}).encode("utf-8")
        req_prod = urllib.request.Request(self._url("/api/config/switch"), data=payload_prod, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req_prod) as resp_prod:
            self.assertEqual(resp_prod.status, 200)
            data_prod = json.loads(resp_prod.read().decode("utf-8"))
            self.assertTrue(data_prod.get("success"))
            self.assertEqual(data_prod.get("active_profile"), "prod")

    def test_bitwarden_duplicates_scan_and_clean(self):
        """API /api/bitwarden/duplicates/scan and clean accurately detects and cleans duplicate entries."""
        bw_sources = datastore.list_bw_sources()
        target_id = bw_sources[0]["id"]

        # 1. Scan for duplicates
        scan_payload = json.dumps({"source_id": target_id}).encode("utf-8")
        req_scan = urllib.request.Request(self._url("/api/bitwarden/duplicates/scan"), data=scan_payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req_scan) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("result", data)
            res = data["result"]
            self.assertIn("duplicate_groups_count", res)
            self.assertIn("duplicate_items_count", res)

        # 2. Clean duplicates
        dup_ids = ["mock-dup-1", "mock-dup-2"]
        clean_payload = json.dumps({"source_id": target_id, "duplicate_ids": dup_ids, "apply": True}).encode("utf-8")
        req_clean = urllib.request.Request(self._url("/api/bitwarden/duplicates/clean"), data=clean_payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req_clean) as resp:
            self.assertEqual(resp.status, 200)
            data_clean = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data_clean.get("success"))
            self.assertEqual(data_clean.get("cleaned_count"), len(dup_ids))


    def test_bitwarden_sync_concurrency_lock_409(self):
        """API /api/bitwarden/sync rejects duplicate concurrent execution with HTTP 409."""
        from server import ACTIVE_SYNC_PAIRS_LOCK, ACTIVE_SYNC_PAIRS, get_pair_key_for_sources
        sources = datastore.list_bw_sources()
        self.assertGreaterEqual(len(sources), 2)
        pair_key = get_pair_key_for_sources(sources[0], sources[1])

        # Manually lock the pair
        with ACTIVE_SYNC_PAIRS_LOCK:
            ACTIVE_SYNC_PAIRS.add(pair_key)

        try:
            payload = json.dumps({
                "source_a": sources[0]["id"],
                "source_b": sources[1]["id"],
                "apply": False
            }).encode("utf-8")
            req = urllib.request.Request(self._url("/api/bitwarden/sync"), data=payload, headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req)
                self.fail("Expected HTTP 409 Conflict, but request succeeded")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 409)
                body = json.loads(e.read().decode("utf-8"))
                self.assertFalse(body.get("success"))
                self.assertEqual(body.get("error"), "conflict")
                self.assertIn("已有正在执行的同步任务", body.get("message", ""))
        finally:
            with ACTIVE_SYNC_PAIRS_LOCK:
                ACTIVE_SYNC_PAIRS.discard(pair_key)

    def test_pair_state_isolation_and_inheritance(self):
        """Test resolve_pair_state_file isolates state per pair and smoothly inherits baseline."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            legacy = tmp_path / "bw-sync-state.json"
            legacy.write_text(json.dumps({"pairs": {"a1": "b1"}, "tombstones": {}}), encoding="utf-8")

            # Resolve state for pair (node, vault)
            pair_file = bw_sync.resolve_pair_state_file(tmp_path, "node", "vault")
            expected_name = f"bw-sync-state-{bw_sync.get_pair_key('node', 'vault')}.json"
            self.assertEqual(pair_file.name, expected_name)
            self.assertTrue(pair_file.exists())

            # Verify baseline was inherited
            data = json.loads(pair_file.read_text(encoding="utf-8"))
            self.assertEqual(data.get("pairs", {}).get("a1"), "b1")

    def test_api_token_auth_protection(self):
        """API endpoints require valid token when API_TOKEN is configured."""
        import server
        orig_token = server.API_TOKEN
        server.API_TOKEN = "secret-token-12345"
        try:
            # 1. Without token -> 401 Unauthorized
            try:
                urllib.request.urlopen(self._url("/api/status"))
                self.fail("Expected HTTP 401 Unauthorized")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 401)
                body = json.loads(e.read().decode("utf-8"))
                self.assertFalse(body.get("success"))
                self.assertIn("Unauthorized", body.get("error", ""))

            # 2. With Bearer token -> 200 OK
            req_bearer = urllib.request.Request(self._url("/api/status"), headers={"Authorization": "Bearer secret-token-12345"})
            with urllib.request.urlopen(req_bearer) as resp:
                self.assertEqual(resp.status, 200)

            # 3. With X-API-Token header -> 200 OK
            req_xtoken = urllib.request.Request(self._url("/api/status"), headers={"X-API-Token": "secret-token-12345"})
            with urllib.request.urlopen(req_xtoken) as resp:
                self.assertEqual(resp.status, 200)

            # 4. Static UI files remain accessible without token
            req_static = urllib.request.Request(self._url("/"))
            with urllib.request.urlopen(req_static) as resp:
                self.assertEqual(resp.status, 200)
        finally:
            server.API_TOKEN = orig_token


if __name__ == "__main__":
    unittest.main()

