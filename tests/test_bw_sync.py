#!/usr/bin/env python3
"""
Unit test wrapper for bw_sync offline selftest suite.
Ensures python3 -m unittest discover tests validates core sync logic alongside PCMP.
"""

import sys
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
        """RealBwClient._password_once must never treat config value as plaintext password."""
        import os
        from unittest.mock import patch
        cfg = {
            "label": "TestNode",
            "server": "https://example.com",
            "email": "test@example.com",
            "password_env": "PlaintextPasswordNotInEnv123",
        }
        # Ensure not in env
        os.environ.pop("PlaintextPasswordNotInEnv123", None)
        client = bw_sync.RealBwClient("test", cfg, "/bin/bw", REPO_ROOT)
        with patch.object(sys.stdin, "isatty", return_value=False):
            with self.assertRaises(bw_sync.BwError):
                client._password_once()


if __name__ == "__main__":
    unittest.main()
