#!/usr/bin/env python3
"""
PCMP (Project Context Management Protocol) SQLite Derivative Indexer & Compliance Checker
Plan A: Zero-dependency implementation using Python 3 standard library.
Generates and maintains a rebuildable index cache at ai/.cache/index.sqlite.
Includes automated --check command to enforce schema, revision, and ADR confirmation rules.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

# Mapping for information layering tags
TAG_NORMALIZATION = {
    "事实": "fact",
    "fact": "fact",
    "假设": "assumption",
    "assumption": "assumption",
    "提议": "proposal",
    "proposal": "proposal",
    "已确认": "accepted",
    "accepted": "accepted",
    "未决": "open",
    "open": "open",
}


def find_project_root() -> Path:
    """Locate project root by searching upwards for PROJECT_CONTEXT_ZH.md, PROJECT_CONTEXT.md, or .git."""
    curr = Path.cwd().resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / "PROJECT_CONTEXT_ZH.md").exists() or (parent / "PROJECT_CONTEXT.md").exists():
            return parent
        if (parent / ".git").exists():
            return parent
    return curr


class PCMPIndex:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.ai_dir = root_dir / "ai"
        self.cache_dir = self.ai_dir / ".cache"
        self.db_path = self.cache_dir / "index.sqlite"

    def init_db(self, reset: bool = False):
        """Initialize or reset the SQLite database schema."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if reset and self.db_path.exists():
            self.db_path.unlink()

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # 1. File metadata
        cur.execute("""
            CREATE TABLE IF NOT EXISTS file_meta (
                file_path TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                revision INTEGER DEFAULT 1,
                pcmp_version TEXT,
                updated_at TEXT,
                last_indexed_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Decisions (ADR)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                date TEXT,
                status TEXT NOT NULL,
                confirmation_source TEXT,
                supersedes TEXT,
                superseded_by TEXT,
                review_trigger TEXT,
                context TEXT,
                decision TEXT,
                reason TEXT,
                alternatives TEXT,
                consequences TEXT,
                raw_markdown TEXT
            );
        """)

        # Ensure schema migrations for existing decisions table
        cur.execute("PRAGMA table_info(decisions)")
        existing_dec_cols = {row[1] for row in cur.fetchall()}
        for col in ["supersedes", "superseded_by", "review_trigger"]:
            if col not in existing_dec_cols:
                cur.execute(f"ALTER TABLE decisions ADD COLUMN {col} TEXT")

        # 3. Issues
        cur.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                description TEXT,
                impact TEXT,
                workaround TEXT,
                component TEXT,
                raw_markdown TEXT
            );
        """)

        # 4. Sessions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                date TEXT,
                agent TEXT,
                task TEXT,
                status TEXT,
                goal TEXT,
                what TEXT,
                result TEXT,
                next_action TEXT,
                raw_markdown TEXT
            );
        """)

        # 5. Tagged Items
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tagged_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                line_number INTEGER,
                tag TEXT NOT NULL,
                normalized_tag TEXT NOT NULL,
                content TEXT NOT NULL
            );
        """)

        # 6. FTS5 Virtual Table for full-text search
        try:
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_content USING fts5(
                    file_path UNINDEXED,
                    section_title,
                    body_text
                );
            """)
        except sqlite3.OperationalError:
            pass

        conn.commit()
        conn.close()

    def get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    @staticmethod
    def compute_sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def parse_frontmatter(self, text: str) -> tuple[dict, str]:
        """Extract YAML-like frontmatter between leading --- delimiters."""
        metadata = {}
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                fm_text = parts[1]
                body = parts[2]
                for line in fm_text.strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        val = v.strip().strip('"').strip("'")
                        metadata[k.strip()] = val
        return metadata, body

    def extract_tags(self, file_path_rel: str, text: str, cur: sqlite3.Cursor):
        """Extract information layering tags [事实], [假设], [提议], [已确认], [未决] etc."""
        cur.execute("DELETE FROM tagged_items WHERE file_path = ?", (file_path_rel,))
        tag_regex = re.compile(r"\[(事实|假设|提议|已确认|未决|fact|assumption|proposal|accepted|open)\]", re.IGNORECASE)

        for line_no, line in enumerate(text.splitlines(), start=1):
            matches = tag_regex.findall(line)
            if matches:
                content = line.strip()
                for match in set(matches):
                    norm = TAG_NORMALIZATION.get(match.lower(), match.lower())
                    cur.execute("""
                        INSERT INTO tagged_items (file_path, line_number, tag, normalized_tag, content)
                        VALUES (?, ?, ?, ?, ?)
                    """, (file_path_rel, line_no, match, norm, content))

    def index_decisions(self, text: str, cur: sqlite3.Cursor):
        """Parse ADRs from DECISIONS.md."""
        cur.execute("DELETE FROM decisions")
        pattern = re.compile(r"^##\s+(DEC-\d+)\s+[—\-]\s+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(text))

        for i, match in enumerate(matches):
            dec_id = match.group(1).strip()
            title = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            block = text[start:end].strip()

            date_val = ""
            status_val = "Proposed"
            conf_source = ""
            supersedes_val = ""
            superseded_by_val = ""
            review_trigger_val = ""
            context_val = ""
            decision_val = ""
            reason_val = ""
            alt_val = ""
            conseq_val = ""

            for line in block.splitlines():
                line_s = line.strip()
                if line_s.startswith("日期:") or line_s.startswith("Date:"):
                    if "|" in line_s:
                        parts = line_s.split("|")
                        date_val = parts[0].split(":", 1)[1].strip()
                        status_val = parts[1].split(":", 1)[1].strip()
                    else:
                        date_val = line_s.split(":", 1)[1].strip()
                elif line_s.startswith("- 确认来源:") or line_s.startswith("- Confirmation Source:"):
                    conf_source = line_s.split(":", 1)[1].strip()
                elif line_s.startswith("- Supersedes:") or line_s.startswith("- 取代决策:"):
                    supersedes_val = line_s.split(":", 1)[1].strip()
                elif line_s.startswith("- Superseded-by:") or line_s.startswith("- 被取代:"):
                    superseded_by_val = line_s.split(":", 1)[1].strip()
                elif line_s.startswith("- 复审触发条件") or line_s.startswith("- Review Trigger"):
                    review_trigger_val = line_s.split(":", 1)[1].strip()
                elif line_s.startswith("- 背景") or line_s.startswith("- Context:"):
                    context_val = line_s.split(":", 1)[1].strip()
                elif line_s.startswith("- 决策") or line_s.startswith("- Decision:"):
                    decision_val = line_s.split(":", 1)[1].strip()
                elif line_s.startswith("- 理由") or line_s.startswith("- Reason:"):
                    reason_val = line_s.split(":", 1)[1].strip()
                elif line_s.startswith("- 备选方案") or line_s.startswith("- Alternatives:"):
                    alt_val = line_s.split(":", 1)[1].strip()
                elif line_s.startswith("- 影响") or line_s.startswith("- Consequences:"):
                    conseq_val = line_s.split(":", 1)[1].strip()

            cur.execute("""
                INSERT OR REPLACE INTO decisions (
                    id, title, date, status, confirmation_source, supersedes, superseded_by, review_trigger,
                    context, decision, reason, alternatives, consequences, raw_markdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (dec_id, title, date_val, status_val, conf_source, supersedes_val, superseded_by_val, review_trigger_val,
                  context_val, decision_val, reason_val, alt_val, conseq_val, block))

    def index_issues(self, text: str, cur: sqlite3.Cursor):
        """Parse ISSUES.md tables or lists."""
        cur.execute("DELETE FROM issues")
        for line in text.splitlines():
            if "|" in line and "ISS-" in line:
                cols = [c.strip() for c in line.split("|") if c.strip()]
                if len(cols) >= 3 and cols[0].startswith("ISS-"):
                    iss_id = cols[0]
                    status = cols[1]
                    desc = cols[2]
                    impact = cols[3] if len(cols) > 3 else ""
                    comp = cols[4] if len(cols) > 4 else ""
                    workaround = cols[5] if len(cols) > 5 else ""
                    cur.execute("""
                        INSERT OR REPLACE INTO issues (
                            id, status, description, impact, workaround, component, raw_markdown
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (iss_id, status, desc, impact, workaround, comp, line.strip()))

    def index_fts(self, file_path_rel: str, text: str, cur: sqlite3.Cursor):
        """Split document by markdown headers and index into FTS5."""
        try:
            cur.execute("DELETE FROM fts_content WHERE file_path = ?", (file_path_rel,))
            sections = re.split(r"\n(?=#{1,4}\s+)", text)
            for sec in sections:
                sec = sec.strip()
                if not sec:
                    continue
                first_line, *rest = sec.splitlines()
                title = first_line.lstrip("#").strip()
                body = "\n".join(rest).strip()
                cur.execute("""
                    INSERT INTO fts_content (file_path, section_title, body_text)
                    VALUES (?, ?, ?)
                """, (file_path_rel, title, body))
        except sqlite3.OperationalError:
            pass

    def index_file(self, file_path: Path, cur: sqlite3.Cursor) -> bool:
        """Parse and index a single Markdown file."""
        if not file_path.exists() or not file_path.is_file():
            return False

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)
            return False

        rel_path = str(file_path.relative_to(self.root_dir))
        content_hash = self.compute_sha256(content)

        # Check existing hash
        cur.execute("SELECT content_hash FROM file_meta WHERE file_path = ?", (rel_path,))
        row = cur.fetchone()
        if row and row[0] == content_hash:
            return False  # Up to date

        # Parse Frontmatter
        fm, body = self.parse_frontmatter(content)
        rev = int(fm.get("revision", 1))
        pcmp_v = fm.get("pcmp_version", "2.1")
        updated_at = fm.get("updated", "")

        # Save meta
        cur.execute("""
            INSERT OR REPLACE INTO file_meta (file_path, content_hash, revision, pcmp_version, updated_at, last_indexed_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (rel_path, content_hash, rev, pcmp_v, updated_at))

        # Tags extraction
        self.extract_tags(rel_path, content, cur)

        # FTS indexing
        self.index_fts(rel_path, content, cur)

        # Specific file parsers
        filename = file_path.name
        if filename == "DECISIONS.md":
            self.index_decisions(content, cur)
        elif filename == "ISSUES.md":
            self.index_issues(content, cur)

        return True

    def scan_and_index(self, rebuild: bool = False) -> tuple[int, int]:
        """Index all markdown files under ai/ directory and root protocol files."""
        self.init_db(reset=rebuild)
        conn = self.get_conn()
        cur = conn.cursor()

        target_files = []
        for root_file in ["PROJECT_CONTEXT_ZH.md", "PROJECT_CONTEXT.md", "README.md", "AGENTS.md"]:
            p = self.root_dir / root_file
            if p.exists():
                target_files.append(p)

        if self.ai_dir.exists():
            for p in self.ai_dir.rglob("*.md"):
                if ".cache" not in p.parts:
                    target_files.append(p)

        indexed_count = 0
        total_files = len(target_files)

        for p in target_files:
            if self.index_file(p, cur):
                indexed_count += 1

        conn.commit()
        conn.close()
        return indexed_count, total_files

    def check_compliance(self) -> tuple[list[str], list[str]]:
        """
        Automated compliance and sanity check for PCMP repository:
        1. Frontmatter check on dynamic files (ai/STATE.md, ai/TASK.md).
        2. TASK schema check: Constraints & Non-Goals and Relevant Files are mandatory.
        3. ADR check on ai/DECISIONS.md: Accepted decisions MUST have confirmation_source,
           supersedes, superseded_by, and review_trigger.
        4. Freshness check: warn if STATE.md updated_at is older than 14 days.
        5. Bilingual check: ensure versions and section skeleton (## N.) match between ZH and EN.
        6. Script mirror check: ensure scripts/pcmp_index.py and skills/pcmp/scripts/pcmp_index.py are identical.
        """
        errors = []
        warnings = []

        # 1. Frontmatter check on dynamic files
        for rel_file in ["ai/STATE.md", "ai/TASK.md"]:
            p = self.root_dir / rel_file
            if p.exists():
                content = p.read_text(encoding="utf-8")
                fm, _ = self.parse_frontmatter(content)
                if not fm:
                    errors.append(f"[{rel_file}] Missing YAML Frontmatter (---)")
                else:
                    if "pcmp_version" not in fm:
                        errors.append(f"[{rel_file}] Frontmatter missing 'pcmp_version'")
                    if "revision" not in fm:
                        errors.append(f"[{rel_file}] Frontmatter missing 'revision'")
                    else:
                        try:
                            rev = int(fm["revision"])
                            if rev < 1:
                                errors.append(f"[{rel_file}] 'revision' must be >= 1, got {rev}")
                        except ValueError:
                            errors.append(f"[{rel_file}] 'revision' must be an integer, got: '{fm['revision']}'")
                    if "updated" not in fm:
                        errors.append(f"[{rel_file}] Frontmatter missing 'updated' date")
                    else:
                        try:
                            updated_dt = datetime.datetime.strptime(fm["updated"], "%Y-%m-%d").date()
                            days_old = (datetime.date.today() - updated_dt).days
                            if days_old > 14:
                                warnings.append(f"[{rel_file}] 'updated' date ({fm['updated']}) is {days_old} days old. State may be stale.")
                        except ValueError:
                            errors.append(f"[{rel_file}] 'updated' format invalid, expected YYYY-MM-DD, got: '{fm['updated']}'")

        # 1b. Schema check for ai/TASK.md if present
        task_p = self.root_dir / "ai/TASK.md"
        if task_p.exists():
            task_txt = task_p.read_text(encoding="utf-8")
            if not any(k in task_txt for k in ["Constraints", "Non-Goals", "约束", "非目标"]):
                errors.append("[ai/TASK.md] Missing mandatory 'Constraints & Non-Goals (约束与非目标)' section")
            if not any(k in task_txt for k in ["Relevant Files", "关联文件", "关键文件"]):
                errors.append("[ai/TASK.md] Missing mandatory 'Relevant Files (关联关键文件)' section")

        # 2. ADR check
        dec_file = self.root_dir / "ai/DECISIONS.md"
        if dec_file.exists():
            content = dec_file.read_text(encoding="utf-8")
            pattern = re.compile(r"^##\s+(DEC-\d+)\s+[—\-]\s+(.+)$", re.MULTILINE)
            matches = list(pattern.finditer(content))
            all_dec_ids = set()
            dec_entries = []

            for i, match in enumerate(matches):
                dec_id = match.group(1).strip()
                all_dec_ids.add(dec_id)
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                block = content[start:end].strip()

                status_val = "Proposed"
                conf_source = None
                supersedes_val = None
                superseded_by_val = None
                review_trigger_val = None

                for line in block.splitlines():
                    ls = line.strip()
                    if ls.startswith("日期:") or ls.startswith("Date:"):
                        if "|" in ls:
                            status_val = ls.split("|")[1].split(":", 1)[1].strip()
                    elif ls.startswith("- 确认来源:") or ls.startswith("- Confirmation Source:"):
                        conf_source = ls.split(":", 1)[1].strip()
                    elif ls.startswith("- Supersedes:") or ls.startswith("- 取代决策:"):
                        supersedes_val = ls.split(":", 1)[1].strip()
                    elif ls.startswith("- Superseded-by:") or ls.startswith("- 被取代:"):
                        superseded_by_val = ls.split(":", 1)[1].strip()
                    elif ls.startswith("- 复审触发条件") or ls.startswith("- Review Trigger"):
                        review_trigger_val = ls.split(":", 1)[1].strip()

                dec_entries.append((dec_id, status_val, conf_source, supersedes_val, superseded_by_val, review_trigger_val))

            for dec_id, status_val, conf_source, supersedes_val, superseded_by_val, review_trigger_val in dec_entries:
                if status_val.lower() == "accepted":
                    if not conf_source or conf_source.lower() in ["none", "待确认", "无", "todo"]:
                        errors.append(f"[DECISIONS.md] {dec_id} is marked 'Accepted' but lacks valid '确认来源 (Confirmation Source)'")
                    if supersedes_val is None:
                        errors.append(f"[DECISIONS.md] {dec_id} is marked 'Accepted' but lacks 'Supersedes' field")
                    if superseded_by_val is None:
                        errors.append(f"[DECISIONS.md] {dec_id} is marked 'Accepted' but lacks 'Superseded-by' field")
                    if not review_trigger_val or review_trigger_val.lower() in ["none", "待确认", "无", "todo"]:
                        errors.append(f"[DECISIONS.md] {dec_id} is marked 'Accepted' but lacks valid '复审触发条件 (Review Trigger)'")

                if supersedes_val and supersedes_val.strip().lower() not in ["无", "none", "n/a", "-", "nil"]:
                    if supersedes_val not in all_dec_ids:
                        errors.append(f"[DECISIONS.md] {dec_id} cites non-existent Supersedes target: '{supersedes_val}'")

        # 3. Bilingual version & structure parity check
        zh_path = self.root_dir / "PROJECT_CONTEXT_ZH.md"
        en_path = self.root_dir / "PROJECT_CONTEXT.md"
        if zh_path.exists() and en_path.exists():
            zh_raw = zh_path.read_text(encoding="utf-8")
            en_raw = en_path.read_text(encoding="utf-8")
            fm_zh, _ = self.parse_frontmatter(zh_raw)
            fm_en, _ = self.parse_frontmatter(en_raw)
            ver_zh = fm_zh.get("pcmp_version")
            ver_en = fm_en.get("pcmp_version")
            if ver_zh and ver_en and ver_zh != ver_en:
                errors.append(f"Bilingual version parity mismatch: ZH is {ver_zh}, EN is {ver_en}")

            def extract_sections(text: str) -> list[int]:
                secs = []
                in_fence = False
                for line in text.splitlines():
                    ls = line.strip()
                    if ls.startswith("```"):
                        in_fence = not in_fence
                        continue
                    if not in_fence and ls.startswith("## "):
                        m = re.match(r"^##\s+(\d+)\.", ls)
                        if m:
                            secs.append(int(m.group(1)))
                return secs

            sec_zh = extract_sections(zh_raw)
            sec_en = extract_sections(en_raw)
            if sec_zh != sec_en:
                errors.append(f"Bilingual section symmetry mismatch: ZH sections {sec_zh} != EN sections {sec_en}")

        # 4. Script mirror consistency check
        root_script = self.root_dir / "scripts/pcmp_index.py"
        skill_script = self.root_dir / "skills/pcmp/scripts/pcmp_index.py"
        if root_script.exists() and skill_script.exists():
            h_root = self.compute_sha256(root_script.read_text(encoding="utf-8"))
            h_skill = self.compute_sha256(skill_script.read_text(encoding="utf-8"))
            if h_root != h_skill:
                errors.append("Script mirror inconsistency: 'scripts/pcmp_index.py' does not match 'skills/pcmp/scripts/pcmp_index.py'")

        return errors, warnings

    def get_stats(self) -> dict:
        if not self.db_path.exists():
            return {"status": "Database not initialized. Run --rebuild first."}

        conn = self.get_conn()
        cur = conn.cursor()

        stats = {
            "database_path": str(self.db_path.relative_to(self.root_dir)),
            "database_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
        }

        for table in ["file_meta", "decisions", "issues", "sessions", "tagged_items"]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            stats[table + "_count"] = cur.fetchone()[0]

        cur.execute("SELECT normalized_tag, COUNT(*) FROM tagged_items GROUP BY normalized_tag")
        stats["tags_breakdown"] = {row[0]: row[1] for row in cur.fetchall()}

        conn.close()
        return stats

    def query_decisions(self, status: str = None) -> list[dict]:
        conn = self.get_conn()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if status:
            cur.execute("SELECT * FROM decisions WHERE LOWER(status) = LOWER(?) ORDER BY id", (status,))
        else:
            cur.execute("SELECT * FROM decisions ORDER BY id")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def query_tags(self, tag: str = None) -> list[dict]:
        conn = self.get_conn()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if tag:
            norm = TAG_NORMALIZATION.get(tag.lower(), tag.lower())
            cur.execute("SELECT * FROM tagged_items WHERE normalized_tag = ? ORDER BY file_path, line_number", (norm,))
        else:
            cur.execute("SELECT * FROM tagged_items ORDER BY normalized_tag, file_path, line_number")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def search_fts(self, query: str) -> list[dict]:
        conn = self.get_conn()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        results = []
        try:
            cur.execute("""
                SELECT file_path, section_title, snippet(fts_content, 2, '<b>', '</b>', '...', 20) as snippet
                FROM fts_content
                WHERE fts_content MATCH ?
                LIMIT 20
            """, (query,))
            results = [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError:
            pass

        if not results:
            cur.execute("""
                SELECT file_path, section_title, body_text
                FROM fts_content
                WHERE body_text LIKE ? OR section_title LIKE ?
                LIMIT 20
            """, (f"%{query}%", f"%{query}%"))
            for r in cur.fetchall():
                body = r["body_text"]
                pos = body.find(query)
                if pos != -1:
                    start = max(0, pos - 40)
                    end = min(len(body), pos + len(query) + 40)
                    snippet = ("..." if start > 0 else "") + body[start:pos] + f"<b>{query}</b>" + body[pos+len(query):end] + ("..." if end < len(body) else "")
                else:
                    snippet = body[:120] + ("..." if len(body) > 120 else "")
                results.append({
                    "file_path": r["file_path"],
                    "section_title": r["section_title"],
                    "snippet": snippet
                })

        conn.close()
        return results


def main():
    parser = argparse.ArgumentParser(description="PCMP SQLite Derivative Indexer & Compliance Checker")
    parser.add_argument("--rebuild", action="store_true", help="Full rebuild of SQLite database")
    parser.add_argument("--update", action="store_true", help="Incremental index of modified files")
    parser.add_argument("--check", action="store_true", help="Automated compliance check for schema, revisions & ADR rules")
    parser.add_argument("--status", action="store_true", help="Display index cache statistics")
    parser.add_argument("--query-decisions", action="store_true", help="List architectural decision records (ADRs)")
    parser.add_argument("--query-tags", action="store_true", help="List information layering tagged items")
    parser.add_argument("--status-filter", type=str, default=None, help="Filter status for decisions or issues")
    parser.add_argument("--tag-filter", type=str, default=None, help="Filter by tag (fact/assumption/proposal/accepted/open)")
    parser.add_argument("--search", type=str, default=None, help="Full-text search across all documents")
    parser.add_argument("--json", action="store_true", help="Format output as JSON")

    args = parser.parse_args()
    root = find_project_root()
    index = PCMPIndex(root)

    if args.check:
        errors, warnings = index.check_compliance()
        if warnings:
            print(f"⚠️  {len(warnings)} warning(s) found:")
            for w in warnings:
                print(f"  - {w}")
        if errors:
            print(f"❌ {len(errors)} error(s) found in PCMP compliance check:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("✅ PCMP compliance check passed! All schemas, revisions and ADR confirmations are valid.")
            sys.exit(0)

    if args.rebuild:
        indexed, total = index.scan_and_index(rebuild=True)
        print(f"Index fully rebuilt: {indexed}/{total} files indexed at {index.db_path}")
        return

    if args.update:
        indexed, total = index.scan_and_index(rebuild=False)
        print(f"Incremental update complete: {indexed} updated out of {total} files.")
        return

    if args.status:
        stats = index.get_stats()
        if args.json:
            print(json.dumps(stats, indent=2, ensure_ascii=False))
        else:
            print("=== PCMP SQLite Derivative Index Status ===")
            for k, v in stats.items():
                print(f"  {k}: {v}")
        return

    if args.query_decisions:
        decisions = index.query_decisions(status=args.status_filter)
        if args.json:
            print(json.dumps(decisions, indent=2, ensure_ascii=False))
        else:
            print(f"Found {len(decisions)} decision(s):")
            for d in decisions:
                print(f"  [{d['id']}] {d['title']} (Status: {d['status']}, Date: {d['date']})")
                if d.get("confirmation_source"):
                    print(f"    - Source: {d['confirmation_source']}")
                if d.get("supersedes"):
                    print(f"    - Supersedes: {d['supersedes']}")
                if d.get("review_trigger"):
                    print(f"    - Review Trigger: {d['review_trigger']}")
                if d.get("decision"):
                    print(f"    - Decision: {d['decision']}")
        return

    if args.query_tags:
        tags = index.query_tags(tag=args.tag_filter)
        if args.json:
            print(json.dumps(tags, indent=2, ensure_ascii=False))
        else:
            print(f"Found {len(tags)} tagged item(s):")
            for t in tags:
                print(f"  [{t['normalized_tag'].upper()}] {t['file_path']}:{t['line_number']} — {t['content']}")
        return

    if args.search:
        results = index.search_fts(args.search)
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(f"Search results for '{args.search}':")
            for r in results:
                print(f"  [{r['file_path']}] {r['section_title']}")
                print(f"    {r['snippet']}\n")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
