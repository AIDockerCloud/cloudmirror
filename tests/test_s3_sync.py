#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_s3_sync.py — Unit tests for S3 storage manager, Bitiful provider,
persistent TagManager (uniqueness validation), same-tag primary/backup sync, and scheduled jobs.
"""

import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from s3_sync import S3SourceManager, TagManager, S3ScheduleManager, S3_PROVIDERS


class TestS3SyncManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tag_file = Path(self.tmp_dir.name) / "test_tags.json"
        self.src_file = Path(self.tmp_dir.name) / "test_s3_sources.json"
        self.sched_file = Path(self.tmp_dir.name) / "test_schedules.json"

        self.tag_mgr = TagManager(self.tag_file)
        self.src_mgr = S3SourceManager(self.src_file, self.tag_mgr)
        self.sched_mgr = S3ScheduleManager(self.sched_file, self.src_mgr)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_bitiful_provider_exists(self):
        """S3_PROVIDERS must include 缤纷云 (Bitiful)."""
        providers = [p["name"] for p in S3_PROVIDERS]
        self.assertTrue(any("缤纷云" in p or "Bitiful" in p for p in providers))

        # Check default seed sources include Bitiful
        sources = self.src_mgr.list_sources()
        bitiful_sources = [s for s in sources if "缤纷云" in s.get("provider", "") or "Bitiful" in s.get("provider", "")]
        self.assertGreaterEqual(len(bitiful_sources), 1, "Should have Bitiful in initial seed sources")

    def test_tag_uniqueness_and_rename(self):
        """TagManager must prevent duplicate tag names and support renaming with cascade."""
        # Add new tag
        tag1 = self.tag_mgr.add_tag("测试笔记A", color="#123456")
        self.assertEqual(tag1["name"], "测试笔记A")

        # Try to add duplicate tag name (case-insensitive) -> must fail
        with self.assertRaises(ValueError):
            self.tag_mgr.add_tag("测试笔记A")
        with self.assertRaises(ValueError):
            self.tag_mgr.add_tag("  测试笔记a  ")

        # Add tag2
        tag2 = self.tag_mgr.add_tag("测试笔记B")

        # Try to rename tag2 to existing tag1's name -> must fail
        with self.assertRaises(ValueError):
            self.tag_mgr.update_tag(tag2["id"], "测试笔记A", sources_manager=self.src_mgr)

        # Successful rename
        updated = self.tag_mgr.update_tag(tag2["id"], "测试笔记B-改名", sources_manager=self.src_mgr)
        self.assertEqual(updated["name"], "测试笔记B-改名")

    def test_tag_cascade_rename_sources(self):
        """Renaming a tag should automatically update S3 sources referencing it."""
        # Add a source with tag 'CascadeTag'
        self.tag_mgr.add_tag("CascadeTag")
        src = self.src_mgr.add_source({
            "name": "Cascade Test S3",
            "bucket": "test-bucket",
            "tags": ["CascadeTag"]
        })
        self.assertIn("CascadeTag", src["tags"])

        # Rename tag
        tag_obj = self.tag_mgr.get_tag_by_name("CascadeTag")
        self.assertIsNotNone(tag_obj)
        self.tag_mgr.update_tag(tag_obj["id"], "NewCascadeTag", sources_manager=self.src_mgr)

        # Verify source now has 'NewCascadeTag'
        reloaded = self.src_mgr.get_source(src["id"])
        self.assertIn("NewCascadeTag", reloaded["tags"])
        self.assertNotIn("CascadeTag", reloaded["tags"])

    def test_same_tag_primary_backup_sync(self):
        """Same tag buckets must support primary and backup comparison & synchronization."""
        obsidian_sources = self.src_mgr.get_sources_by_tag("Obsidian")
        self.assertGreaterEqual(len(obsidian_sources), 2, "Must have at least 2 Obsidian buckets for primary/backup pairing")

        primary = obsidian_sources[0]
        backup = obsidian_sources[1]

        # Dry-run compare
        diff = self.src_mgr.compare_pair(primary["id"], backup["id"], tag="Obsidian")
        self.assertTrue(diff["success"])
        self.assertEqual(diff["primary"]["id"], primary["id"])
        self.assertEqual(diff["backup"]["id"], backup["id"])

        # Execute sync (apply)
        res = self.src_mgr.sync_pair(primary["id"], backup["id"], tag="Obsidian", apply=True)
        self.assertTrue(res["success"])
        self.assertEqual(res["mode"], "apply")
        self.assertIn("logs", res)

    def test_scheduled_sync_manager(self):
        """S3ScheduleManager supports creating, listing, and triggering scheduled jobs."""
        schedules = self.sched_mgr.list_schedules()
        self.assertGreaterEqual(len(schedules), 1)

        # Trigger schedule
        sched_id = schedules[0]["id"]
        res = self.sched_mgr.trigger_schedule(sched_id)
        self.assertTrue(res["success"])

        # Check updated status
        updated_schedules = self.sched_mgr.list_schedules()
        target = next(s for s in updated_schedules if s["id"] == sched_id)
        self.assertEqual(target["last_status"], "success")

    def test_compute_next_run_daily_2am(self):
        """compute_next_run accurately schedules next run at 02:00 AM."""
        from datetime import datetime
        from s3_sync import compute_next_run

        # Case 1: Base time is 01:30 AM -> should be today at 02:00 AM
        base_1 = datetime(2026, 10, 26, 1, 30, 0)
        next_1 = compute_next_run("daily_2am", 1440, base_1)
        self.assertEqual(next_1, datetime(2026, 10, 26, 2, 0, 0))

        # Case 2: Base time is 02:15 AM -> should be tomorrow at 02:00 AM
        base_2 = datetime(2026, 10, 26, 2, 15, 0)
        next_2 = compute_next_run("daily_2am", 1440, base_2)
        self.assertEqual(next_2, datetime(2026, 10, 27, 2, 0, 0))


class TestRealS3ClientAndSigV4(unittest.TestCase):
    def setUp(self):
        from s3_sync import RealS3Client
        self.client = RealS3Client(
            endpoint="https://s3.bitiful.net",
            bucket="test-bucket",
            access_key="test_access_key_12345",
            secret_key="test_secret_key_67890",
            region="cn-east-1"
        )

    def test_client_is_configured(self):
        """is_configured validates credentials completeness and excludes dummy keys."""
        from s3_sync import RealS3Client
        self.assertTrue(self.client.is_configured())

        # Missing keys
        unconf = RealS3Client(endpoint="https://s3.bitiful.net", bucket="b", access_key="", secret_key="")
        self.assertFalse(unconf.is_configured())

        # Dummy / demo mask
        demo_client = RealS3Client(endpoint="https://s3.bitiful.net", bucket="b", access_key="AKIA...", secret_key="••••••••")
        self.assertFalse(demo_client.is_configured())

        # Example key
        example_client = RealS3Client(endpoint="https://s3.bitiful.net", bucket="b", access_key="AKIA2EXAMPLEKEY999", secret_key="real_sk")
        self.assertFalse(example_client.is_configured())

    def test_sigv4_headers_generation(self):
        """_sign_headers produces valid AWS SigV4 authorization headers."""
        headers = self.client._sign_headers(
            method="GET",
            path="/test-bucket",
            query_params={"list-type": "2", "prefix": "data/"},
            payload=b""
        )
        self.assertIn("Host", headers)
        self.assertEqual(headers["Host"], "s3.bitiful.net")
        self.assertIn("x-amz-date", headers)
        self.assertIn("x-amz-content-sha256", headers)
        # Empty payload sha256
        self.assertEqual(headers["x-amz-content-sha256"], "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

        auth = headers.get("Authorization", "")
        self.assertTrue(auth.startswith("AWS4-HMAC-SHA256 Credential=test_access_key_12345/"))
        self.assertIn("/cn-east-1/s3/aws4_request", auth)
        self.assertIn("SignedHeaders=host;x-amz-content-sha256;x-amz-date", auth)
        self.assertIn("Signature=", auth)

    def test_list_objects_v2_xml_parsing(self):
        """list_objects parses AWS ListObjectsV2 XML response and handles pagination."""
        import xml.etree.ElementTree as ET
        from unittest.mock import patch

        xml_page1 = b"""<?xml version="1.0" encoding="UTF-8"?>
        <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
            <Name>test-bucket</Name>
            <Prefix></Prefix>
            <KeyCount>2</KeyCount>
            <MaxKeys>2</MaxKeys>
            <IsTruncated>true</IsTruncated>
            <NextContinuationToken>token_page_2</NextContinuationToken>
            <Contents>
                <Key>notes/2026-10-01.md</Key>
                <LastModified>2026-10-01T12:00:00.000Z</LastModified>
                <ETag>"abc123etag"</ETag>
                <Size>1024</Size>
            </Contents>
            <Contents>
                <Key>notes/2026-10-02.md</Key>
                <LastModified>2026-10-02T12:00:00.000Z</LastModified>
                <ETag>"def456etag"</ETag>
                <Size>2048</Size>
            </Contents>
        </ListBucketResult>"""

        xml_page2 = b"""<?xml version="1.0" encoding="UTF-8"?>
        <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
            <Name>test-bucket</Name>
            <Prefix></Prefix>
            <KeyCount>1</KeyCount>
            <MaxKeys>2</MaxKeys>
            <IsTruncated>false</IsTruncated>
            <Contents>
                <Key>notes/2026-10-03.md</Key>
                <LastModified>2026-10-03T12:00:00.000Z</LastModified>
                <ETag>"ghi789etag"</ETag>
                <Size>4096</Size>
            </Contents>
        </ListBucketResult>"""

        responses = [
            (200, xml_page1, {"content-type": "application/xml"}),
            (200, xml_page2, {"content-type": "application/xml"}),
        ]

        with patch.object(self.client, "_request", side_effect=responses):
            objects = self.client.list_objects(paginate=True)
            self.assertEqual(len(objects), 3)
            self.assertEqual(objects[0]["key"], "notes/2026-10-01.md")
            self.assertEqual(objects[0]["size"], 1024)
            self.assertEqual(objects[0]["etag"], "abc123etag")
            self.assertEqual(objects[2]["key"], "notes/2026-10-03.md")
            self.assertEqual(objects[2]["size"], 4096)

    def test_s3_error_xml_parsing(self):
        """_parse_s3_error_xml extracts Code and Message from S3 error XML."""
        from s3_sync import _parse_s3_error_xml
        err_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <Error>
            <Code>NoSuchBucket</Code>
            <Message>The specified bucket does not exist</Message>
            <BucketName>test-bucket</BucketName>
            <RequestId>REQ123</RequestId>
        </Error>"""
        code, msg = _parse_s3_error_xml(err_xml)
        self.assertEqual(code, "NoSuchBucket")
        self.assertEqual(msg, "The specified bucket does not exist")


class TestS3EnvCredentialsAndSiYuan(unittest.TestCase):
    def setUp(self):
        import os
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tag_file = Path(self.tmp_dir.name) / "test_tags.json"
        self.src_file = Path(self.tmp_dir.name) / "test_s3_sources.json"

        self.tag_mgr = TagManager(self.tag_file)
        self.src_mgr = S3SourceManager(self.src_file, self.tag_mgr)

        # Set test environment credentials
        os.environ["TEST_R2_AK"] = "real_ak_from_env_999"
        os.environ["TEST_R2_SK"] = "real_sk_from_env_secret888"

    def tearDown(self):
        import os
        self.tmp_dir.cleanup()
        os.environ.pop("TEST_R2_AK", None)
        os.environ.pop("TEST_R2_SK", None)

    def test_env_credentials_resolution(self):
        """S3SourceManager resolves credentials from access_key_env / secret_key_env."""
        src = self.src_mgr.add_source({
            "name": "Env Source Test",
            "endpoint": "https://s3.bitiful.net",
            "bucket": "env-bucket",
            "access_key_env": "TEST_R2_AK",
            "secret_key_env": "TEST_R2_SK",
            "tags": ["Obsidian"]
        })

        ak, sk = self.src_mgr.get_credentials(src)
        self.assertEqual(ak, "real_ak_from_env_999")
        self.assertEqual(sk, "real_sk_from_env_secret888")
        self.assertTrue(self.src_mgr.is_real_configured(src))

        # Check list_sources safe representation
        sources = self.src_mgr.list_sources()
        target = next(s for s in sources if s["id"] == src["id"])
        self.assertTrue(target["has_env_credentials"])
        self.assertIn("ENV: TEST_R2_AK", target["access_key"])
        self.assertIn("ENV: TEST_R2_SK", target["secret_key"])

    def test_siyuan_block_mirror_comparison(self):
        """SiYuan block mirror skips identical-size blocks, marks missing blocks, and retains orphans."""
        from unittest.mock import patch, MagicMock

        pri = self.src_mgr.add_source({
            "name": "SiYuan Primary",
            "endpoint": "https://s3.bitiful.net",
            "bucket": "siyuan-pri",
            "access_key_env": "TEST_R2_AK",
            "secret_key_env": "TEST_R2_SK",
            "prefix": "data/",
            "tags": ["思源笔记"]
        })

        bak = self.src_mgr.add_source({
            "name": "SiYuan Backup",
            "endpoint": "https://s3.bitiful.net",
            "bucket": "siyuan-bak",
            "access_key_env": "TEST_R2_AK",
            "secret_key_env": "TEST_R2_SK",
            "prefix": "backup-data/",
            "tags": ["思源笔记"]
        })

        # Mock primary objects: 3 blocks
        pri_objs = [
            {"key": "data/20261026-block1.sy", "size": 1024, "etag": "etag1"},
            {"key": "data/20261026-block2.sy", "size": 2048, "etag": "etag2"},
            {"key": "data/assets/image-1.png", "size": 51200, "etag": "etag3"},
        ]

        # Mock backup objects: block1 exists with same size, image-1 exists with same size, orphan exists
        bak_objs = [
            {"key": "backup-data/20261026-block1.sy", "size": 1024, "etag": "etag1"},
            {"key": "backup-data/assets/image-1.png", "size": 51200, "etag": "etag3"},
            {"key": "backup-data/deleted-old-block.sy", "size": 500, "etag": "oldetag"},
        ]

        mock_pri_client = MagicMock()
        mock_pri_client.is_configured.return_value = True
        mock_pri_client.list_objects.return_value = pri_objs

        mock_bak_client = MagicMock()
        mock_bak_client.is_configured.return_value = True
        mock_bak_client.list_objects.return_value = bak_objs

        def fake_get_client(src_obj):
            if src_obj["id"] == pri["id"]:
                return mock_pri_client
            return mock_bak_client

        with patch.object(self.src_mgr, "get_client", side_effect=fake_get_client):
            diff = self.src_mgr.compare_pair(pri["id"], bak["id"], tag="思源笔记")

            self.assertTrue(diff["success"])
            self.assertFalse(diff["is_demo"])
            self.assertEqual(diff["strategy"], "siyuan_block_mirror")
            self.assertEqual(diff["identical_count"], 2) # block1 and image-1
            self.assertEqual(diff["to_sync_count"], 1)   # block2 is missing on backup
            self.assertEqual(diff["retained_count"], 1)  # deleted-old-block.sy preserved (zero delete)
            self.assertEqual(diff["sample_pending_files"], ["20261026-block2.sy"])

    def test_sync_pair_partial_failure_semantics(self):
        """sync_pair must report partial status on partial failure, record failed objects, and not overwrite objects_count."""
        pri = self.src_mgr.add_source({
            "name": "PriPartial",
            "provider": "Bitiful",
            "endpoint": "https://s3.bitiful.net",
            "bucket": "pri-partial-bucket",
            "access_key_env": "TEST_R2_AK",
            "secret_key_env": "TEST_R2_SK",
            "tags": ["通用笔记"]
        })
        bak = self.src_mgr.add_source({
            "name": "BakPartial",
            "provider": "Bitiful",
            "endpoint": "https://s3.bitiful.net",
            "bucket": "bak-partial-bucket",
            "access_key_env": "TEST_R2_AK",
            "secret_key_env": "TEST_R2_SK",
            "tags": ["通用笔记"]
        })
        bak_before_count = bak.get("objects_count", 0)

        # Primary has 2 objects missing on backup
        pri_objs = [
            {"key": "file1.txt", "size": 100, "etag": "e1"},
            {"key": "file2.txt", "size": 200, "etag": "e2"},
        ]
        mock_pri_client = MagicMock()
        mock_pri_client.is_configured.return_value = True
        mock_pri_client.list_objects.return_value = pri_objs

        mock_bak_client = MagicMock()
        mock_bak_client.is_configured.return_value = True
        mock_bak_client.list_objects.return_value = []

        # Make file1 succeed and file2 fail
        def fake_transfer(pri_k, bak_client, bak_k, max_retries=3):
            if "file2" in pri_k:
                raise IOError("Simulated network drop on file2")
            return 100, "etag1"

        mock_pri_client.transfer_to.side_effect = fake_transfer

        with patch.object(self.src_mgr, "get_client", side_effect=lambda s: mock_pri_client if s["id"] == pri["id"] else mock_bak_client):
            res = self.src_mgr.sync_pair(pri["id"], bak["id"], tag="通用笔记", apply=True)

            self.assertFalse(res["success"], "Partial failure must not return success=True")
            self.assertEqual(res["status"], "partial")
            self.assertEqual(res["synced_objects"], 1)
            self.assertEqual(res["failed_count"], 1)
            self.assertEqual(len(res["failed_objects"]), 1)
            self.assertEqual(res["failed_objects"][0]["rel_path"], "file2.txt")

            # Check that backup source objects_count was NOT updated to primary's count
            bak_after = self.src_mgr.get_source(bak["id"])
            self.assertEqual(bak_after.get("objects_count", 0), bak_before_count)

    def test_siyuan_pointer_sorted_last(self):
        """Pointer files like 'latest' and manifests must be sorted after chunk files in to_sync list."""
        pri = self.src_mgr.add_source({
            "name": "PriSiYuan",
            "provider": "Bitiful",
            "endpoint": "https://s3.bitiful.net",
            "bucket": "pri-siyuan-bucket",
            "access_key_env": "TEST_R2_AK",
            "secret_key_env": "TEST_R2_SK",
            "tags": ["思源笔记"]
        })
        bak = self.src_mgr.add_source({
            "name": "BakSiYuan",
            "provider": "Bitiful",
            "endpoint": "https://s3.bitiful.net",
            "bucket": "bak-siyuan-bucket",
            "access_key_env": "TEST_R2_AK",
            "secret_key_env": "TEST_R2_SK",
            "tags": ["思源笔记"]
        })

        pri_objs = [
            {"key": "latest", "size": 32, "etag": "e_latest"},
            {"key": "data/20261027-block1.sy", "size": 1024, "etag": "e_b1"},
            {"key": "manifest.json", "size": 64, "etag": "e_manifest"},
            {"key": "data/20261027-block2.sy", "size": 2048, "etag": "e_b2"},
        ]

        mock_pri_client = MagicMock()
        mock_pri_client.is_configured.return_value = True
        mock_pri_client.list_objects.return_value = pri_objs

        mock_bak_client = MagicMock()
        mock_bak_client.is_configured.return_value = True
        mock_bak_client.list_objects.return_value = []

        with patch.object(self.src_mgr, "get_client", side_effect=lambda s: mock_pri_client if s["id"] == pri["id"] else mock_bak_client):
            diff = self.src_mgr.compare_pair(pri["id"], bak["id"], tag="思源笔记")
            self.assertTrue(diff["success"])
            pending = [item["rel_path"] for item in diff["pending_details"]]
            # Data blocks must appear before pointer files
            self.assertIn(pending[-2], ("latest", "manifest.json"))
            self.assertIn(pending[-1], ("latest", "manifest.json"))
            self.assertTrue(pending[0].startswith("data/"))
            self.assertTrue(pending[1].startswith("data/"))

    def test_siyuan_non_chunk_requires_etag_match(self):
        """Non-chunk paths in SiYuan (assets, latest) must compare both size and ETag, not size alone."""
        pri = self.src_mgr.add_source({
            "name": "PriSiYuanETag",
            "provider": "Bitiful",
            "endpoint": "https://s3.bitiful.net",
            "bucket": "pri-sy-etag",
            "access_key_env": "TEST_R2_AK",
            "secret_key_env": "TEST_R2_SK",
            "tags": ["思源笔记"]
        })
        bak = self.src_mgr.add_source({
            "name": "BakSiYuanETag",
            "provider": "Bitiful",
            "endpoint": "https://s3.bitiful.net",
            "bucket": "bak-sy-etag",
            "access_key_env": "TEST_R2_AK",
            "secret_key_env": "TEST_R2_SK",
            "tags": ["思源笔记"]
        })

        pri_objs = [
            {"key": "data/chunk.sy", "size": 100, "etag": "e_chunk_pri"},
            {"key": "assets/photo.jpg", "size": 500, "etag": "e_photo_pri"},
        ]
        bak_objs = [
            # chunk has same size, different etag -> should be identical (content-hash addressed)
            {"key": "data/chunk.sy", "size": 100, "etag": "e_chunk_bak"},
            # photo has same size, different etag -> MUST be detected as modified (non-chunk)
            {"key": "assets/photo.jpg", "size": 500, "etag": "e_photo_bak"},
        ]

        mock_pri_client = MagicMock()
        mock_pri_client.is_configured.return_value = True
        mock_pri_client.list_objects.return_value = pri_objs

        mock_bak_client = MagicMock()
        mock_bak_client.is_configured.return_value = True
        mock_bak_client.list_objects.return_value = bak_objs

        with patch.object(self.src_mgr, "get_client", side_effect=lambda s: mock_pri_client if s["id"] == pri["id"] else mock_bak_client):
            diff = self.src_mgr.compare_pair(pri["id"], bak["id"], tag="思源笔记")
            self.assertTrue(diff["success"])
            self.assertEqual(diff["identical_count"], 1) # only data/chunk.sy
            self.assertEqual(diff["to_sync_count"], 1)   # assets/photo.jpg needs sync
            self.assertEqual(diff["pending_details"][0]["rel_path"], "assets/photo.jpg")


class TestRealS3ClientMockHttp(unittest.TestCase):
    """Test RealS3Client against local HTTP server without external dependencies."""

    @classmethod
    def setUpClass(cls):
        import http.server
        import threading

        class MockS3Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass # suppress stderr logs

            def do_GET(self):
                if "list-type=2" in self.path:
                    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
                    <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
                        <Name>mock-bucket</Name>
                        <Contents>
                            <Key>test.txt</Key>
                            <Size>12</Size>
                            <ETag>"mock-etag-1"</ETag>
                        </Contents>
                    </ListBucketResult>"""
                    self.send_response(200)
                    self.send_header("Content-Type", "application/xml")
                    self.send_header("Content-Length", str(len(xml)))
                    self.end_headers()
                    self.wfile.write(xml)
                else:
                    data = b"Hello S3 Mock"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("ETag", '"mock-etag-get"')
                    self.end_headers()
                    self.wfile.write(data)

            def do_PUT(self):
                content_len = int(self.headers.get("Content-Length", 0))
                _ = self.rfile.read(content_len)
                self.send_response(200)
                self.send_header("ETag", '"mock-etag-put"')
                self.end_headers()

            def do_HEAD(self):
                self.send_response(200)
                self.send_header("Content-Length", "42")
                self.send_header("ETag", '"mock-etag-head"')
                self.send_header("Content-Type", "text/plain")
                self.end_headers()

        cls.server = http.server.HTTPServer(("127.0.0.1", 0), MockS3Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_mock_s3_get_put_head_and_test_connection(self):
        from s3_sync import RealS3Client
        client = RealS3Client(
            endpoint=f"http://127.0.0.1:{self.port}",
            bucket="mock-bucket",
            access_key="mock_ak",
            secret_key="mock_sk",
            region="us-east-1"
        )

        # test_connection
        conn = client.test_connection()
        self.assertTrue(conn["connected"])
        self.assertEqual(conn["objects_count"], 1)

        # get_object
        data, ctype = client.get_object("test.txt")
        self.assertEqual(data, b"Hello S3 Mock")
        self.assertEqual(ctype, "text/plain")

        # put_object
        etag = client.put_object("upload.txt", b"New content", content_type="text/plain")
        self.assertEqual(etag, "mock-etag-put")

        # head_object
        meta = client.head_object("test.txt")
        self.assertEqual(meta["size"], 42)
        self.assertEqual(meta["etag"], "mock-etag-head")

    def test_mock_s3_transfer_to_streaming(self):
        from s3_sync import RealS3Client
        client = RealS3Client(
            endpoint=f"http://127.0.0.1:{self.port}",
            bucket="mock-bucket",
            access_key="mock_ak",
            secret_key="mock_sk",
            region="us-east-1"
        )
        total_bytes, etag = client.transfer_to("test.txt", client, "copy.txt", max_retries=2)
        self.assertEqual(total_bytes, len(b"Hello S3 Mock"))
        self.assertEqual(etag, "mock-etag-put")


if __name__ == "__main__":
    unittest.main()

