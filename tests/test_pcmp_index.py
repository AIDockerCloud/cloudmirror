#!/usr/bin/env python3
"""
Unit tests for PCMP SQLite Derivative Indexer and Compliance Checker (scripts/pcmp_index.py).
Uses Python standard library unittest (zero external dependencies).
"""

import sys
import unittest
from pathlib import Path
import tempfile
import shutil

# Ensure scripts directory is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pcmp_index import PCMPIndex, TAG_NORMALIZATION


class TestPCMPIndex(unittest.TestCase):
    def setUp(self):
        self.repo_root = REPO_ROOT
        self.indexer = PCMPIndex(self.repo_root)

    def test_compute_sha256(self):
        h1 = PCMPIndex.compute_sha256("hello world")
        h2 = PCMPIndex.compute_sha256("hello world")
        h3 = PCMPIndex.compute_sha256("different content")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_parse_frontmatter(self):
        text = """---
pcmp_version: "2.2"
revision: 5
updated: 2026-10-24
---

# Title
Body text
"""
        fm, body = self.indexer.parse_frontmatter(text)
        self.assertEqual(fm.get("pcmp_version"), "2.2")
        self.assertEqual(fm.get("revision"), "5")
        self.assertEqual(fm.get("updated"), "2026-10-24")
        self.assertIn("# Title", body)

    def test_tag_normalization(self):
        self.assertEqual(TAG_NORMALIZATION["事实"], "fact")
        self.assertEqual(TAG_NORMALIZATION["假设"], "assumption")
        self.assertEqual(TAG_NORMALIZATION["提议"], "proposal")
        self.assertEqual(TAG_NORMALIZATION["已确认"], "accepted")
        self.assertEqual(TAG_NORMALIZATION["未决"], "open")

    def test_compliance_check_on_current_repo(self):
        """Current repository must pass compliance check without errors or warnings."""
        errors, warnings = self.indexer.check_compliance()
        self.assertEqual(errors, [], f"Repository compliance check failed with errors: {errors}")
        self.assertEqual(warnings, [], f"Repository compliance check failed with warnings: {warnings}")

    def test_compliance_check_detects_unconfirmed_accepted_adr(self):
        """Verify that an Accepted ADR without confirmation source triggers error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ai_dir = tmp_path / "ai"
            ai_dir.mkdir(parents=True)

            (ai_dir / "STATE.md").write_text("""---
pcmp_version: "2.2"
revision: 1
updated: 2026-10-24
---
# State
""", encoding="utf-8")

            (ai_dir / "DECISIONS.md").write_text("""---
pcmp_version: "2.2"
revision: 1
updated: 2026-10-24
---
## DEC-999 — Bad Decision
日期: 2026-10-24 | 状态: Accepted
- 决策: Do something risky
""", encoding="utf-8")

            tmp_indexer = PCMPIndex(tmp_path)
            errors, _ = tmp_indexer.check_compliance()
            self.assertTrue(any("DEC-999 is marked 'Accepted' but lacks valid '确认来源" in e for e in errors),
                            f"Expected missing confirmation source error, got: {errors}")

    def test_compliance_check_detects_missing_adr_fields(self):
        """Verify that an Accepted ADR lacking Supersedes or Review Trigger triggers error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ai_dir = tmp_path / "ai"
            ai_dir.mkdir(parents=True)

            (ai_dir / "DECISIONS.md").write_text("""---
pcmp_version: "2.2"
revision: 1
updated: 2026-10-24
---
## DEC-998 — Incomplete ADR
日期: 2026-10-24 | 状态: Accepted
- 确认来源: User approval
- 决策: Some plan
""", encoding="utf-8")

            tmp_indexer = PCMPIndex(tmp_path)
            errors, _ = tmp_indexer.check_compliance()
            self.assertTrue(any("lacks 'Supersedes' field" in e for e in errors))
            self.assertTrue(any("lacks valid '复审触发条件" in e for e in errors))

    def test_compliance_check_detects_task_missing_mandatory_sections(self):
        """Verify that TASK.md lacking Constraints or Relevant Files triggers error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            ai_dir = tmp_path / "ai"
            ai_dir.mkdir(parents=True)

            (ai_dir / "TASK.md").write_text("""---
pcmp_version: "2.2"
revision: 1
updated: 2026-10-24
---
# Task
Only simple description without constraints or files.
""", encoding="utf-8")

            tmp_indexer = PCMPIndex(tmp_path)
            errors, _ = tmp_indexer.check_compliance()
            self.assertTrue(any("Constraints & Non-Goals" in e for e in errors))
            self.assertTrue(any("Relevant Files" in e for e in errors))

    def test_compliance_check_detects_script_mirror_inconsistency(self):
        """Verify that scripts/pcmp_index.py differing from skills/pcmp/scripts/pcmp_index.py triggers error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            s1 = tmp_path / "scripts"
            s2 = tmp_path / "skills/pcmp/scripts"
            s1.mkdir(parents=True)
            s2.mkdir(parents=True)

            (s1 / "pcmp_index.py").write_text("# version 1", encoding="utf-8")
            (s2 / "pcmp_index.py").write_text("# version 2 (modified)", encoding="utf-8")

            tmp_indexer = PCMPIndex(tmp_path)
            errors, _ = tmp_indexer.check_compliance()
            self.assertTrue(any("Script mirror inconsistency" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
