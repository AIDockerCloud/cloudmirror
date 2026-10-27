#!/usr/bin/env python3
"""
Unit test wrapper for bw_sync offline selftest suite.
Ensures python3 -m unittest discover tests validates core sync logic alongside PCMP.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure root directory is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import bw_sync


class TestBwSync(unittest.TestCase):
    def test_offline_selftest(self):
        """bw_sync --selftest built-in test suite must pass with 0 exit code."""
        result = bw_sync.selftest()
        self.assertEqual(result, 0, "bw_sync offline selftest failed")

    def test_conflict_copy_deduplication_on_retry(self):
        """Conflict copies must not proliferate across retries even if state was lost."""
        ca = bw_sync.FakeBwClient("A", [bw_sync._item("a1", "邮箱", pw="old")], [])
        cb = bw_sync.FakeBwClient("B", [bw_sync._item("b1", "邮箱", pw="new")], [])

        # Round 1: conflict created
        rep1, st1 = bw_sync.run_one_round(ca, cb, bw_sync.empty_state(), True, "2026-10-26")
        self.assertEqual(len(rep1["conflicts"]), 1)
        count_a_1 = len(ca.items)
        count_b_1 = len(cb.items)
        self.assertEqual(count_a_1, 2)  # original + copy of b
        self.assertEqual(count_b_1, 2)  # original + copy of a

        # Round 2: retry with empty state (simulating uncommitted state failure)
        rep2, st2 = bw_sync.run_one_round(ca, cb, bw_sync.empty_state(), True, "2026-10-26")
        self.assertEqual(len(ca.items), count_a_1, "Conflict copies must not duplicate on A")
        self.assertEqual(len(cb.items), count_b_1, "Conflict copies must not duplicate on B")

    def test_password_once_does_not_treat_config_as_plaintext(self):
        """RealBwClient._password_once must never treat config value as plaintext password or leak invalid strings."""
        import os
        from unittest.mock import patch
        # 1. Valid env name format missing in env
        cfg_valid = {
            "label": "TestNode",
            "server": "https://example.com",
            "email": "test@example.com",
            "password_env": "BW_SYNC_TEST_VALID_ENV_NAME_123"
        }
        os.environ.pop("BW_SYNC_TEST_VALID_ENV_NAME_123", None)
        client_valid = bw_sync.RealBwClient("test", cfg_valid, "/bin/bw", REPO_ROOT)
        with patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaises(bw_sync.BwError) as cm:
                client_valid._password_once()
            self.assertIn("BW_SYNC_TEST_VALID_ENV_NAME_123", str(cm.exception))

        # 2. Invalid env name format (e.g. user inadvertently provided raw plaintext password with symbols)
        secret_raw_pw = "&Secret*Pw]999|^"
        cfg_invalid = {
            "label": "TestNode",
            "server": "https://example.com",
            "email": "test@example.com",
            "password_env": secret_raw_pw
        }
        client_invalid = bw_sync.RealBwClient("test", cfg_invalid, "/bin/bw", REPO_ROOT)
        with patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaises(bw_sync.BwError) as cm:
                client_invalid._password_once()
            # MUST NOT echo the raw password/string under any circumstances!
            self.assertNotIn(secret_raw_pw, str(cm.exception), "Plaintext password must NEVER be reflected in error message")
            self.assertIn("BW_SYNC_PASSWORD", str(cm.exception))

    def test_load_dotenv_support(self):
        """Native load_dotenv loads .env variables and enforces OS Environment > .env priority."""
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as tf:
            tf.write("# Comment\nBW_SYNC_DOTENV_TEST_VAR=my_test_val_888\nOS_EXPORTED_KEY=value_from_dotenv\n")
            tf.flush()
            tpath = Path(tf.name)
        try:
            # 1. Normal missing variable is loaded
            os.environ.pop("BW_SYNC_DOTENV_TEST_VAR", None)
            bw_sync.load_dotenv(tpath, force=True)
            self.assertEqual(os.environ.get("BW_SYNC_DOTENV_TEST_VAR"), "my_test_val_888")

            # 2. Strict OS Environment > .env priority:
            # If a variable is in _INITIAL_OS_ENV_KEYS, .env MUST NEVER overwrite it
            bw_sync._INITIAL_OS_ENV_KEYS.add("OS_EXPORTED_KEY")
            os.environ["OS_EXPORTED_KEY"] = "original_shell_value"
            bw_sync.load_dotenv(tpath, force=True)
            self.assertEqual(
                os.environ.get("OS_EXPORTED_KEY"),
                "original_shell_value",
                "OS Environment variable must never be overwritten by .env"
            )
        finally:
            bw_sync._INITIAL_OS_ENV_KEYS.discard("OS_EXPORTED_KEY")
            os.environ.pop("BW_SYNC_DOTENV_TEST_VAR", None)
            os.environ.pop("OS_EXPORTED_KEY", None)
            if tpath.exists():
                tpath.unlink()


    def test_duplicates_isolated_by_folder(self):
        """Identical credentials in different folders must not be reported as duplicates."""
        fnames = {"f1": "工作", "f2": "个人"}
        # Two items with same domain, username, password but in different folders
        item_work = bw_sync._item("i1", "GitHub", user="alice", pw="secret", uri="https://github.com", folder_id="f1", creationDate="2022-01-01T00:00:00Z")
        item_personal = bw_sync._item("i2", "GitHub", user="alice", pw="secret", uri="https://github.com", folder_id="f2", creationDate="2022-02-01T00:00:00Z")
        dup_res = bw_sync.find_duplicates_in_items([item_work, item_personal], fnames)
        self.assertEqual(dup_res["duplicate_groups_count"], 0, "Different folders must not be grouped as duplicates")
        self.assertEqual(dup_res["duplicate_items_count"], 0)

        # Same credentials in same folder must be detected as duplicate, keeping earliest
        item_work_clone = bw_sync._item("i3", "GitHub Clone", user="alice", pw="secret", uri="https://github.com", folder_id="f1", creationDate="2023-01-01T00:00:00Z")
        dup_res_same = bw_sync.find_duplicates_in_items([item_work, item_personal, item_work_clone], fnames)
        self.assertEqual(dup_res_same["duplicate_groups_count"], 1)
        self.assertEqual(dup_res_same["duplicate_items_count"], 1)
        self.assertEqual(dup_res_same["groups"][0]["keep"]["id"], "i1")

    def test_duplicates_ignore_name_and_favorite_keep_earliest(self):
        """Duplicate detection ignores name and favorite, strictly checks all other content, and preserves earliest creationDate."""
        fnames = {"f1": "开发"}
        # 3 items in same folder:
        # e1: created 2021-01-01, favorite=False, name="GitLab"
        # e2: created 2022-06-01, favorite=True,  name="GitLab 冗余备份" (same content)
        # e3: created 2022-08-01, favorite=False, name="GitLab 生产" (notes different -> not duplicate)
        e1 = bw_sync._item("e1", "GitLab", user="dev", pw="p99", uri="https://gitlab.com", folder_id="f1", notes="dev notes", creationDate="2021-01-01T00:00:00Z", favorite=False)
        e2 = bw_sync._item("e2", "GitLab 冗余备份", user="dev", pw="p99", uri="https://gitlab.com", folder_id="f1", notes="dev notes", creationDate="2022-06-01T00:00:00Z", favorite=True)
        e3 = bw_sync._item("e3", "GitLab 生产", user="dev", pw="p99", uri="https://gitlab.com", folder_id="f1", notes="prod notes", creationDate="2022-08-01T00:00:00Z", favorite=False)

        res = bw_sync.find_duplicates_in_items([e1, e2, e3], fnames)
        self.assertEqual(res["duplicate_groups_count"], 1)
        self.assertEqual(res["duplicate_items_count"], 1)
        # e1 should be kept because its creationDate (2021) is earlier than e2 (2022)
        group = res["groups"][0]
        self.assertEqual(group["keep"]["id"], "e1")
        self.assertEqual(group["keep"]["name"], "GitLab")
        self.assertEqual(group["duplicates"][0]["id"], "e2")
        self.assertEqual(group["duplicates"][0]["name"], "GitLab 冗余备份")

    def test_duplicates_distinguish_autofill_uris(self):
        """Autofill URIs and match modes must be strictly checked to prevent deleting credentials of different websites."""
        fnames = {"f1": "开发"}
        # Same user and same password, but different website URIs (e.g. GitHub vs GitLab)
        gh_item = bw_sync._item("gh1", "GitHub", user="common_user", pw="SecretPass999", uri="https://github.com/login", folder_id="f1")
        gl_item = bw_sync._item("gl1", "GitLab", user="common_user", pw="SecretPass999", uri="https://gitlab.com/login", folder_id="f1")

        res = bw_sync.find_duplicates_in_items([gh_item, gl_item], fnames)
        self.assertEqual(res["duplicate_groups_count"], 0, "Different website URIs must never be grouped as duplicates")
        self.assertEqual(res["duplicate_items_count"], 0)

        # Clone with identical website URI is correctly detected
        gh_clone = bw_sync._item("gh2", "GitHub 冗余", user="common_user", pw="SecretPass999", uri="https://github.com/login", folder_id="f1")
        res2 = bw_sync.find_duplicates_in_items([gh_item, gl_item, gh_clone], fnames)
        self.assertEqual(res2["duplicate_groups_count"], 1)
        self.assertEqual(res2["duplicate_items_count"], 1)
        self.assertEqual(res2["groups"][0]["keep"]["id"], "gh1")
        self.assertEqual(res2["groups"][0]["duplicates"][0]["id"], "gh2")

    def test_natural_key_includes_folder(self):
        """Natural key must incorporate folder name to prevent cross-folder clashing."""
        fnames = {"f1": "工作", "f2": "个人"}
        i1 = bw_sync.normalize_item(bw_sync._item("1", "GitHub", user="u", uri="https://github.com", folder_id="f1"), fnames)
        i2 = bw_sync.normalize_item(bw_sync._item("2", "GitHub", user="u", uri="https://github.com", folder_id="f2"), fnames)
        k1 = bw_sync.natural_key(i1)
        k2 = bw_sync.natural_key(i2)
        self.assertNotEqual(k1, k2, "Items in different folders must have distinct natural keys")
        self.assertEqual(k1[-1], "工作")
        self.assertEqual(k2[-1], "个人")

    def test_conflict_copy_exact_marker_matching(self):
        """Conflict copy detection must match full marker prefix, not prefix overlap like GitHub vs GitHub 备用."""
        fnames = {}
        source_rec = bw_sync.Rec(bw_sync._item("src1", "GitHub", user="alice", pw="p1"), fnames)
        # Target has a conflict copy of "GitHub 备用"
        conflict_item_other = bw_sync._item(
            "c1",
            f"GitHub 备用{bw_sync.CONFLICT_MARKER}Node 2026-10-27]",
            user="alice",
            pw="p1"
        )
        # Should NOT match because source is "GitHub", not "GitHub 备用"
        self.assertFalse(bw_sync.has_existing_conflict_copy([conflict_item_other], source_rec))

        # Target has genuine conflict copy of "GitHub"
        conflict_item_exact = bw_sync._item(
            "c2",
            f"GitHub{bw_sync.CONFLICT_MARKER}Node 2026-10-27]",
            user="alice",
            pw="p1"
        )
        self.assertTrue(bw_sync.has_existing_conflict_copy([conflict_item_exact], source_rec))


if __name__ == "__main__":
    unittest.main()

