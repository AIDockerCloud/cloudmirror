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


if __name__ == "__main__":
    unittest.main()
