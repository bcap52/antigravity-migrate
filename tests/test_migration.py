"""
test_migration.py - Automated End-to-End Migration Test Suite
Tests export, packaging, extraction, restoration, protobuf patching, and validation.
"""

import os
import sys
import json
import shutil
import sqlite3
import zipfile
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from antigravity_migrate.os_detector import detect_system, cross_reference_target
from antigravity_migrate.proto_engine import (
    encode_varint, decode_varint, update_trajectory_metadata_bytes,
    update_raw_summary, update_agyhub_pb, extract_summary_metadata
)
from antigravity_migrate.path_mapper import path_to_uri, uri_to_path, resolve_bulk_mappings
from antigravity_migrate.mcp_auditor import audit_mcp_config, inject_env_into_mcp_config
from antigravity_migrate.exporter import export_migration_bundle
from antigravity_migrate.restorer import run_restoration
from antigravity_migrate.validator import run_validation_suite

class TestAntigravityMigrate(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="agy_test_")
        self.source_gemini = Path(self.temp_dir) / "source_gemini"
        self.target_gemini = Path(self.temp_dir) / "target_gemini"
        self.workspaces_dir = Path(self.temp_dir) / "source_workspaces"
        
        # Setup source structure
        self._setup_mock_source()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _setup_mock_source(self):
        # 1. Directories
        for p in [
            self.source_gemini / "antigravity" / "conversations",
            self.source_gemini / "antigravity" / "brain",
            self.source_gemini / "antigravity" / "annotations",
            self.source_gemini / "config" / "projects",
            self.source_gemini / "config" / "skills" / "test_skill",
            self.source_gemini / "config" / "rules",
            self.workspaces_dir / "test_project" / ".git"
        ]:
            p.mkdir(parents=True, exist_ok=True)
            
        # 2. Workspace files & git repository
        proj_dir = self.workspaces_dir / "test_project"
        ws_file = proj_dir / "main.py"
        ws_file.write_text("print('hello antigravity')\n", encoding="utf-8")
        
        import subprocess
        subprocess.run(["git", "init", str(proj_dir)], capture_output=True)
        subprocess.run(["git", "-C", str(proj_dir), "config", "user.name", "Test"], capture_output=True)
        subprocess.run(["git", "-C", str(proj_dir), "config", "user.email", "test@example.com"], capture_output=True)
        subprocess.run(["git", "-C", str(proj_dir), "add", "."], capture_output=True)
        subprocess.run(["git", "-C", str(proj_dir), "commit", "-m", "init"], capture_output=True)
        
        # 3. Project JSON
        pid = "test-project-uuid-1234"
        ws_uri = path_to_uri(str(self.workspaces_dir / "test_project"))
        pjson = {
            "id": pid,
            "name": "Test Project",
            "projectResources": {
                "resources": [
                    {
                        "gitFolder": {
                            "folderUri": ws_uri,
                            "allowWrite": True
                        }
                    }
                ]
            }
        }
        with open(self.source_gemini / "config" / "projects" / f"{pid}.json", "w") as f:
            json.dump(pjson, f)
            
        # 4. Global config & MCP
        skill_file = self.source_gemini / "config" / "skills" / "test_skill" / "SKILL.md"
        skill_file.write_text("---\nname: test_skill\n---\nTest skill content", encoding="utf-8")
        
        mcp_data = {
            "mcpServers": {
                "mock-server": {
                    "command": "npx",
                    "args": ["-y", "mock-server"],
                    "env": {
                        "TEST_API_KEY": "YOUR_API_KEY_HERE"
                    }
                }
            }
        }
        with open(self.source_gemini / "config" / "mcp_config.json", "w") as f:
            json.dump(mcp_data, f)
            
        # 5. Conversation DB
        cid = "test-convo-uuid-5678"
        db_path = self.source_gemini / "antigravity" / "conversations" / f"{cid}.db"
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("CREATE TABLE steps (step_id INTEGER PRIMARY KEY, content TEXT)")
        c.execute("INSERT INTO steps VALUES (1, 'turn 1'), (2, 'turn 2'), (3, 'turn 3')")
        
        c.execute("CREATE TABLE trajectory_metadata_blob (id TEXT PRIMARY KEY, data BLOB)")
        # Create a mock TrajectoryMetadata blob: tag 18 = pid
        t18_tag = encode_varint((18 << 3) | 2)
        p_bytes = pid.encode("utf-8")
        t7_tag = encode_varint((7 << 3) | 2)
        u_bytes = ws_uri.encode("utf-8")
        mock_blob = t7_tag + encode_varint(len(u_bytes)) + u_bytes + t18_tag + encode_varint(len(p_bytes)) + p_bytes
        c.execute("INSERT INTO trajectory_metadata_blob VALUES ('main', ?)", (mock_blob,))
        conn.commit()
        conn.close()
        
        # 6. Brain and Annotation
        (self.source_gemini / "antigravity" / "brain" / cid).mkdir(parents=True, exist_ok=True)
        (self.source_gemini / "antigravity" / "brain" / cid / "artifact.md").write_text("# Plan", encoding="utf-8")
        (self.source_gemini / "antigravity" / "annotations" / f"{cid}.pbtxt").write_text(f'title:"Test Conversation"\n', encoding="utf-8")
        
        # 7. Raw summary & conversation_summaries.db
        # Construct raw_summary protobuf: tag 1 = title, tag 2 = step_count (3), tag 17 = mock_blob
        t1_tag = encode_varint((1 << 3) | 2)
        title_b = b"Test Conversation"
        t2_tag = encode_varint((2 << 3) | 0)
        t17_tag = encode_varint((17 << 3) | 2)
        raw_summary = (
            t1_tag + encode_varint(len(title_b)) + title_b +
            t2_tag + encode_varint(3) +
            t17_tag + encode_varint(len(mock_blob)) + mock_blob
        )
        
        sum_db_path = self.source_gemini / "antigravity" / "conversation_summaries.db"
        s_conn = sqlite3.connect(sum_db_path)
        sc = s_conn.cursor()
        sc.execute("""
        CREATE TABLE conversation_summaries (
            conversation_id TEXT PRIMARY KEY,
            title TEXT, preview TEXT, step_count INTEGER,
            last_modified_time datetime, workspace_uris TEXT,
            status TEXT, source TEXT, project_id TEXT,
            agent_name TEXT, parent_conversation_id TEXT,
            nesting_depth INTEGER, battle_id TEXT,
            winning_conversation_id TEXT, not_fully_idle numeric,
            killed numeric, last_user_input_time datetime,
            last_user_input_step_index INTEGER, app_data_dir TEXT,
            raw_summary BLOB, group_id TEXT
        )
        """)
        sc.execute("""
        INSERT INTO conversation_summaries VALUES (
            ?, 'Test Conversation', 'Test Conversation', 3,
            datetime('now'), ?, 'CASCADE_RUN_STATUS_IDLE', '',
            ?, '', '', 0, '', '', 0, 0, datetime('now'), 2, 'antigravity', ?, ''
        )
        """, (cid, json.dumps([ws_uri]), pid, raw_summary))
        s_conn.commit()
        s_conn.close()
        
        # 8. agyhub_summaries_proto.pb
        pb_path = self.source_gemini / "antigravity" / "agyhub_summaries_proto.pb"
        pb_data = update_agyhub_pb(b"", cid, raw_summary)
        with open(pb_path, "wb") as f:
            f.write(pb_data)

    def test_proto_engine(self):
        """Verify varint encoding and protobuf summary metadata extraction."""
        n = 123456
        enc = encode_varint(n)
        val, pos = decode_varint(enc, 0)
        self.assertEqual(val, n)
        
        # Test update_trajectory_metadata_bytes
        orig_bytes = encode_varint((18 << 3) | 2) + encode_varint(4) + b"old1"
        new_bytes = update_trajectory_metadata_bytes(orig_bytes, "file:///new/uri", "new_project_id")
        self.assertIn(b"new_project_id", new_bytes)
        self.assertIn(b"file:///new/uri", new_bytes)

    def test_export_and_restore_cycle(self):
        """Tests full end-to-end export and restoration with validation gates."""
        zip_path = os.path.join(self.temp_dir, "test_bundle.zip")
        
        # 1. Export using mock source paths
        # Monkeypatch discover_all to point to our mock source
        import antigravity_migrate.exporter as exp_mod
        orig_discover = exp_mod.discover_all
        
        from antigravity_migrate.discover import discover_all
        exp_mod.discover_all = lambda: discover_all(custom_gemini_path=str(self.source_gemini))
        
        try:
            curr_sys = detect_system()
            res = exp_mod.export_migration_bundle(
                output_zip_path=zip_path,
                mode="automated",
                target_intent=curr_sys,
                selected_cids=["test-convo-uuid-5678"],
                selected_pids=["test-project-uuid-1234"]
            )
            self.assertTrue(res["success"])
            self.assertTrue(os.path.exists(zip_path))
            
            # Verify zip contents
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                self.assertIn("migration_manifest.json", names)
                self.assertIn("restore.py", names)
                self.assertIn("chats/conversations/test-convo-uuid-5678.db", names)
                self.assertIn("workspaces/test-project-uuid-1234/main.py", names)
        finally:
            exp_mod.discover_all = orig_discover

        # 2. Extract into temporary extraction dir
        extract_dir = Path(self.temp_dir) / "extracted_bundle"
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        # 3. Restore into mock target gemini
        restore_res = run_restoration(
            archive_dir_str=str(extract_dir),
            target_gemini_path=str(self.target_gemini),
            interactive=False,
            auto_repair=True,
            skip_process_check=True
        )
        self.assertTrue(restore_res["success"])
        self.assertEqual(restore_res["restored_chats"], 1)

        # 4. Verify target databases and files
        target_db = self.target_gemini / "antigravity" / "conversations" / "test-convo-uuid-5678.db"
        self.assertTrue(target_db.exists())
        
        target_sum_db = self.target_gemini / "antigravity" / "conversation_summaries.db"
        self.assertTrue(target_sum_db.exists())
        
        conn = sqlite3.connect(target_sum_db)
        c = conn.cursor()
        c.execute("SELECT step_count, project_id FROM conversation_summaries WHERE conversation_id='test-convo-uuid-5678'")
        row = c.fetchone()
        conn.close()
        self.assertEqual(row[0], 3)
        self.assertEqual(row[1], "test-project-uuid-1234")

        # 5. Run validation suite on target
        val = run_validation_suite(gemini_dir_str=str(self.target_gemini), auto_repair=True, skip_process_check=True)
        # Check SQLite integrity, step counts, brain artifacts
        passed_names = {g["name"] for g in val["gates"] if g["passed"]}
        self.assertIn("SQLite Integrity", passed_names)
        self.assertIn("Step Count Verification", passed_names)
        self.assertIn("Protobuf Registration", passed_names)
        self.assertIn("Brain Artifacts Check", passed_names)

    def test_os_distro_detection_and_cross_reference(self):
        """Test recognition of Linux distros (Arch, CachyOS, Omarchy, Ubuntu, Fedora) and cross-referencing."""
        # 1. CachyOS (Arch family)
        cachyos_sys = {
            "os": "linux",
            "family": "arch",
            "distro_id": "cachyos",
            "distro_name": "CachyOS Linux",
            "is_posix": True
        }
        arch_manifest_target = {
            "os": "linux",
            "family": "arch",
            "label": "Linux (Arch family)"
        }
        res = cross_reference_target(arch_manifest_target, cachyos_sys)
        self.assertEqual(res["status"], "match")
        self.assertTrue(res["compatible"])

        # 2. Omarchy (Arch family)
        omarchy_sys = {
            "os": "linux",
            "family": "arch",
            "distro_id": "omarchy",
            "distro_name": "Omarchy Linux",
            "is_posix": True
        }
        res2 = cross_reference_target(arch_manifest_target, omarchy_sys)
        self.assertEqual(res2["status"], "match")
        self.assertTrue(res2["compatible"])

        # 3. Pop!_OS vs Debian/Ubuntu family
        pop_sys = {
            "os": "linux",
            "family": "debian",
            "distro_id": "pop",
            "distro_name": "Pop!_OS",
            "is_posix": True
        }
        deb_manifest_target = {
            "os": "linux",
            "family": "debian"
        }
        res3 = cross_reference_target(deb_manifest_target, pop_sys)
        self.assertEqual(res3["status"], "match")

        # 4. Incompatible OS (e.g. Windows target when Linux expected)
        win_sys = {
            "os": "windows",
            "family": "windows",
            "distro_name": "Windows 11"
        }
        res4 = cross_reference_target(arch_manifest_target, win_sys)
        self.assertEqual(res4["status"], "mismatch")
        self.assertFalse(res4["compatible"])

    def test_path_and_uri_mapping(self):
        """Test path-to-URI and URI-to-path conversions on Windows and POSIX."""
        # POSIX
        posix_uri = path_to_uri("/home/abdul/Projects/Unnamed App", is_posix=True)
        self.assertEqual(posix_uri, "file:///home/abdul/Projects/Unnamed%20App")
        posix_path = uri_to_path(posix_uri)
        self.assertEqual(posix_path, "/home/abdul/Projects/Unnamed App")

        # Windows
        win_uri = path_to_uri("E:\\Unnamed App", is_posix=False)
        self.assertIn("file:///e:/Unnamed%20App", win_uri)
        win_path = uri_to_path(win_uri)
        self.assertEqual(win_path.lower(), "e:\\unnamed app")

        # Bulk mappings
        projects = [
            {"id": "p1", "name": "App One"},
            {"id": "p2", "name": "App Two"}
        ]
        bulk = resolve_bulk_mappings(projects, "/home/user/Projects", is_target_posix=True)
        self.assertEqual(bulk["p1"][0].replace("\\", "/"), "/home/user/Projects/App One")
        self.assertEqual(bulk["p1"][1], "file:///home/user/Projects/App%20One")
        self.assertEqual(bulk["p2"][0].replace("\\", "/"), "/home/user/Projects/App Two")

    def test_mcp_auditor_and_injection(self):
        """Test MCP config auditing and interactive variable injection."""
        mcp_path = self.source_gemini / "config" / "mcp_config.json"
        audit = audit_mcp_config(str(mcp_path))
        self.assertIn("mock-server", audit["servers"])
        self.assertEqual(len(audit["detected_env_vars"]), 1)
        self.assertEqual(audit["detected_env_vars"][0]["name"], "TEST_API_KEY")

        # Inject real key
        injected = {"TEST_API_KEY": "sk_test_123456789"}
        success = inject_env_into_mcp_config(str(mcp_path), injected)
        self.assertTrue(success)

        with open(mcp_path, "r", encoding="utf-8") as f:
            updated_data = json.load(f)
        self.assertEqual(
            updated_data["mcpServers"]["mock-server"]["env"]["TEST_API_KEY"],
            "sk_test_123456789"
        )

    def test_manual_mode_export(self):
        """Test manual mode: bundles chats and configs, leaves workspaces unbundled."""
        zip_path = os.path.join(self.temp_dir, "manual_bundle.zip")
        
        import antigravity_migrate.exporter as exp_mod
        orig_discover = exp_mod.discover_all
        from antigravity_migrate.discover import discover_all
        exp_mod.discover_all = lambda: discover_all(custom_gemini_path=str(self.source_gemini))
        
        try:
            res = exp_mod.export_migration_bundle(
                output_zip_path=zip_path,
                mode="manual",
                selected_cids=["test-convo-uuid-5678"],
                selected_pids=["test-project-uuid-1234"]
            )
            self.assertTrue(res["success"])
            
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                self.assertIn("migration_manifest.json", names)
                self.assertIn("chats/conversations/test-convo-uuid-5678.db", names)
                # Ensure workspaces/ is NOT bundled in manual mode
                ws_entries = [n for n in names if n.startswith("workspaces/")]
                self.assertEqual(len(ws_entries), 0)
        finally:
            exp_mod.discover_all = orig_discover

if __name__ == "__main__":
    unittest.main()

