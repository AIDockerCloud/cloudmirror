#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_s3_sync.py — Unit tests for S3 storage manager, Bitiful provider,
persistent TagManager (uniqueness validation), same-tag primary/backup sync, and scheduled jobs.
"""

import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
