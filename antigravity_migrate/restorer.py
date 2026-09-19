"""
restorer.py - Target System Restoration Engine
Restores chats, global configurations, MCP servers, and workspaces on target machine
with full path rewrites, protobuf updates, environment variable injection, and self-tests.
"""

import os
import sys
import json
import shutil
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from .os_detector import detect_system, cross_reference_target
from .process_guard import ensure_safe_to_modify
from .path_mapper import path_to_uri, uri_to_path, resolve_bulk_mappings, find_candidate_project_dir, sanitize_filename
from .proto_engine import update_trajectory_metadata_bytes, update_raw_summary, update_agyhub_pb
from .mcp_auditor import prompt_env_variables_interactive, inject_env_into_mcp_config, generate_env_shell_script
from .validator import run_validation_suite

def load_manifest(archive_dir: Path) -> Dict[str, Any]:
    """Loads migration_manifest.json from the unzipped bundle directory."""
    manifest_path = archive_dir / "migration_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"migration_manifest.json not found in {archive_dir}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_restoration(
    archive_dir_str: str,
    target_gemini_path: Optional[str] = None,
    interactive: bool = True,
    auto_repair: bool = True,
    skip_process_check: bool = False
) -> Dict[str, Any]:
    """
    Executes end-to-end restoration on target system.
    """
    archive_dir = Path(archive_dir_str).resolve()
    manifest = load_manifest(archive_dir)
    
    # Target system paths
    home = Path.home()
    gemini_dir = Path(target_gemini_path).resolve() if target_gemini_path else (home / ".gemini")
    antigravity_dir = gemini_dir / "antigravity"
    config_dir = gemini_dir / "config"
    conv_dir = antigravity_dir / "conversations"
    brain_dir = antigravity_dir / "brain"
    annot_dir = antigravity_dir / "annotations"
    proj_dir = config_dir / "projects"
    sum_db = antigravity_dir / "conversation_summaries.db"
    agy_pb = antigravity_dir / "agyhub_summaries_proto.pb"
    
    # 1. Process Safety Guard
    if interactive and not skip_process_check:
        ensure_safe_to_modify(interactive=True)
        
    # 2. OS & Distro Detection
    target_sys = detect_system()
    source_sys = manifest.get("source_system", {})
    target_intent = manifest.get("target_intent", {})
    
    print("\n" + "=" * 75)
    print(" ANTIGRAVITY RESTORATION ENGINE")
    print("=" * 75)
    print(f" Source OS: {source_sys.get('distro_name', source_sys.get('os', 'Unknown'))}")
    print(f" Target OS: {target_sys.get('distro_name', target_sys.get('os', 'Unknown'))}")
    
    xref = cross_reference_target(target_intent, target_sys)
    print(f" OS Compatibility: [{xref['status'].upper()}] {xref['message']}")
    print("-" * 75)

    # 3. Restore Global Configurations & MCPs
    print("\n [1/5] Restoring Global Configurations & Rules...")
    config_dir.mkdir(parents=True, exist_ok=True)
    src_config = archive_dir / "config"
    if src_config.exists():
        # Copy skills, rules, plugins, sidecars, config.json, mcp_config.json
        for item in src_config.iterdir():
            target_item = config_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target_item, dirs_exist_ok=True)
            else:
                if not target_item.exists() or item.name != "config.json":
                    shutil.copy2(item, target_item)
        print("       [OK] Global skills, plugins, rules, and configs restored.")

    # Copy MCP tool definitions if present
    src_mcp = archive_dir / "mcp"
    if src_mcp.exists():
        dst_mcp = antigravity_dir / "mcp"
        dst_mcp.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_mcp, dst_mcp, dirs_exist_ok=True)
        print("       [OK] MCP tool definitions restored.")

    # 4. Interactive Environment Variable Injection (User Requirement #1)
    detected_env_vars = manifest.get("mcp_env_vars", [])
    injected_vars: Dict[str, str] = {}
    if detected_env_vars and interactive:
        injected_vars = prompt_env_variables_interactive(detected_env_vars)
        if injected_vars:
            target_mcp_config = config_dir / "mcp_config.json"
            inject_env_into_mcp_config(str(target_mcp_config), injected_vars)
            
            env_script_name = "antigravity_env.sh" if target_sys["is_posix"] else "antigravity_env.bat"
            env_script_path = antigravity_dir / env_script_name
            generate_env_shell_script(injected_vars, str(env_script_path), target_sys["is_posix"])
            print(f"       [OK] Injected {len(injected_vars)} variables into MCP config and {env_script_name}.")

    # 5. Workspace Path Resolution (User Requirement #2: Bulk vs Individual)
    projects = manifest.get("projects", [])
    project_mappings: Dict[str, Tuple[str, str]] = {} # pid -> (target_path, target_uri)
    
    print("\n [2/5] Resolving Project Workspace Paths...")
    if projects and interactive:
        print("\n How would you like to map the project workspaces on this machine?")
        print("   [1] Auto-map all projects into a single base directory [Recommended]")
        if target_sys["is_posix"]:
            print("       (e.g., /home/<user>/Projects/<ProjectName>)")
        else:
            print("       (e.g., C:\\Users\\<user>\\Projects\\<ProjectName>)")
        print("   [2] Map each project path individually")
        
        map_choice = input("\nChoose mapping method [1/2, default 1]: ").strip()
        if map_choice in ("", "1"):
            # Bulk Mapping Mode
            default_base = str(home / "Projects") if target_sys["is_posix"] else str(home / "Projects")
            base_dir_input = input(f"Enter base directory [{default_base}]: ").strip()
            base_dir_str = base_dir_input if base_dir_input else default_base
            
            project_mappings = resolve_bulk_mappings(
                projects, 
                base_dir_str, 
                is_target_posix=target_sys["is_posix"]
            )
            print(f"\n Mapped {len(projects)} projects under: {base_dir_str}")
            for p in projects:
                pid = p["id"]
                pname = p.get("name", pid)
                print(f"   - {pname:25} -> {project_mappings[pid][0]}")
        else:
            # Individual Mapping Mode
            for i, p in enumerate(projects, 1):
                pid = p["id"]
                pname = p.get("name", pid)
                clean_name = sanitize_filename(pname)
                
                # Try candidate auto-detect
                cand = find_candidate_project_dir(pname)
                if not cand:
                    cand = str(home / "Projects" / clean_name)
                    
                print(f"\n [{i}/{len(projects)}] Project: \"{pname}\"")
                print(f"       Source Path: {p.get('local_path', 'N/A')}")
                target_p_input = input(f"       Target Path [{cand}]: ").strip()
                target_p = target_p_input if target_p_input else cand
                
                t_uri = path_to_uri(target_p, is_posix=target_sys["is_posix"])
                project_mappings[pid] = (target_p, t_uri)
    else:
        # Non-interactive fallback
        default_base = str(home / "Projects")
        project_mappings = resolve_bulk_mappings(projects, default_base, is_target_posix=target_sys["is_posix"])

    # 6. Extract Workspaces & Write Project JSONs
    print("\n [3/5] Configuring Projects and Extracting Workspaces...")
    proj_dir.mkdir(parents=True, exist_ok=True)
    is_automated = manifest.get("mode") == "automated"
    
    for p in projects:
        pid = p["id"]
        pname = p.get("name", pid)
        if pid not in project_mappings:
            continue
            
        target_path, target_uri = project_mappings[pid]
        target_p_obj = Path(target_path)
        target_p_obj.mkdir(parents=True, exist_ok=True)
        
        # If automated, extract bundled workspace directory
        src_ws = archive_dir / "workspaces" / pid
        if is_automated and src_ws.exists():
            shutil.copytree(src_ws, target_p_obj, dirs_exist_ok=True)
            print(f"       [OK] Extracted workspace: {pname} (.git preserved)")

        # If manual mode bundled local project configs (.agent, .gemini, local skills), extract them
        src_pcfg = archive_dir / "project_configs" / pid
        if src_pcfg.exists():
            shutil.copytree(src_pcfg, target_p_obj, dirs_exist_ok=True)
            print(f"       [OK] Restored local project configs for: {pname} (.agent, .gemini, local skills)")
            
        # Write project JSON
        pjson_data = {
            "id": pid,
            "name": pname,
            "projectResources": {
                "resources": [
                    {
                        "gitFolder": {
                            "folderUri": target_uri,
                            "allowWrite": True
                        }
                    }
                ]
            }
        }
        with open(proj_dir / f"{pid}.json", "w", encoding="utf-8") as pf:
            json.dump(pjson_data, pf, indent=2)

    # 7. Restore Conversations & Sync Protobufs
    print("\n [4/5] Restoring Conversations and Synchronizing Data Store...")
    conv_dir.mkdir(parents=True, exist_ok=True)
    brain_dir.mkdir(parents=True, exist_ok=True)
    annot_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize / connect SQLite conversation_summaries.db
    if sum_db.exists():
        shutil.copy2(sum_db, str(sum_db) + ".bak")
        
    conn = sqlite3.connect(sum_db)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS conversation_summaries (
        conversation_id TEXT PRIMARY KEY,
        title TEXT DEFAULT "",
        preview TEXT DEFAULT "",
        step_count INTEGER DEFAULT 0,
        last_modified_time datetime,
        workspace_uris TEXT,
        status TEXT DEFAULT "",
        source TEXT DEFAULT "",
        project_id TEXT DEFAULT "",
        agent_name TEXT DEFAULT "",
        parent_conversation_id TEXT DEFAULT "",
        nesting_depth INTEGER DEFAULT 0,
        battle_id TEXT DEFAULT "",
        winning_conversation_id TEXT DEFAULT "",
        not_fully_idle numeric DEFAULT false,
        killed numeric DEFAULT false,
        last_user_input_time datetime,
        last_user_input_step_index INTEGER DEFAULT -1,
        app_data_dir TEXT DEFAULT "",
        raw_summary BLOB,
        group_id TEXT DEFAULT ""
    )
    """)
    
    # Read or initialize agyhub_summaries_proto.pb
    pb_data = b""
    if agy_pb.exists():
        shutil.copy2(agy_pb, str(agy_pb) + ".bak")
        with open(agy_pb, "rb") as f:
            pb_data = f.read()

    conversations = manifest.get("conversations", [])
    restored_chats = 0
    
    for cinfo in conversations:
        cid = cinfo["id"]
        pid = cinfo.get("project_id", "")
        title = cinfo.get("title", f"Chat {cid[:8]}")
        step_count = cinfo.get("step_count", 0)
        
        # Determine target URI
        target_uri = ""
        if pid in project_mappings:
            target_uri = project_mappings[pid][1]
        elif cinfo.get("workspace_uris"):
            # Fallback
            target_uri = cinfo["workspace_uris"][0]
            
        # Copy DB
        src_db = archive_dir / "chats" / "conversations" / f"{cid}.db"
        dst_db = conv_dir / f"{cid}.db"
        if src_db.exists():
            shutil.copy2(src_db, dst_db)
            
            # Update trajectory_metadata_blob inside <cid>.db
            try:
                cconn = sqlite3.connect(dst_db)
                cc = cconn.cursor()
                cc.execute("SELECT data FROM trajectory_metadata_blob WHERE id='main'")
                brow = cc.fetchone()
                if brow and brow[0]:
                    new_blob = update_trajectory_metadata_bytes(brow[0], target_uri, pid)
                    cc.execute("UPDATE trajectory_metadata_blob SET data=? WHERE id='main'", (new_blob,))
                    cconn.commit()
                cconn.close()
            except Exception:
                pass

        # Copy Brain folder
        src_brain = archive_dir / "chats" / "brain" / cid
        if src_brain.exists():
            shutil.copytree(src_brain, brain_dir / cid, dirs_exist_ok=True)
            
        # Copy Annotation
        src_annot = archive_dir / "chats" / "annotations" / f"{cid}.pbtxt"
        if src_annot.exists():
            shutil.copy2(src_annot, annot_dir / f"{cid}.pbtxt")
            
        # Read raw summary blob and patch
        src_raw = archive_dir / "chats" / "raw_summaries" / f"{cid}.bin"
        raw_bytes = None
        if src_raw.exists():
            with open(src_raw, "rb") as f:
                raw_bytes = f.read()
                
        if raw_bytes:
            new_raw_summary = update_raw_summary(raw_bytes, target_uri, pid)
        else:
            new_raw_summary = b""

        # Ingest into conversation_summaries.db
        ws_uris_json = json.dumps([target_uri]) if target_uri else "[]"
        c.execute("""
        INSERT INTO conversation_summaries (
            conversation_id, title, preview, step_count, last_modified_time,
            workspace_uris, status, source, project_id, agent_name,
            parent_conversation_id, nesting_depth, battle_id, winning_conversation_id,
            not_fully_idle, killed, last_user_input_time, last_user_input_step_index,
            app_data_dir, raw_summary, group_id
        ) VALUES (?, ?, ?, ?, datetime('now'), ?, 'CASCADE_RUN_STATUS_IDLE', '', ?, '', '', 0, '', '', 0, 0, datetime('now'), ?, 'antigravity', ?, '')
        ON CONFLICT(conversation_id) DO UPDATE SET
            title = excluded.title,
            preview = excluded.preview,
            step_count = excluded.step_count,
            workspace_uris = excluded.workspace_uris,
            project_id = excluded.project_id,
            raw_summary = excluded.raw_summary
        """, (cid, title, title, step_count, ws_uris_json, pid, max(0, step_count - 1), new_raw_summary))

        # Update agyhub_summaries_proto.pb
        if new_raw_summary:
            pb_data = update_agyhub_pb(pb_data, cid, new_raw_summary)
            
        restored_chats += 1

    conn.commit()
    conn.close()
    
    # Write back agyhub_summaries_proto.pb
    if pb_data:
        with open(agy_pb, "wb") as f:
            f.write(pb_data)
            
    print(f"       [OK] Synchronized {restored_chats} conversation records.")

    # 8. Post-Migration Verification & Self-Test Suite
    print("\n [5/5] Running Automated Post-Migration Verification Suite...")
    val_report = run_validation_suite(
        gemini_dir_str=str(gemini_dir), 
        manifest=manifest, 
        auto_repair=auto_repair,
        skip_process_check=skip_process_check
    )
    
    print("\n" + "=" * 75)
    print(" POST-MIGRATION VERIFICATION AUDIT")
    print("=" * 75)
    for g in val_report["gates"]:
        st = "[PASS]" if g["passed"] else "[FAIL]"
        rep_tag = " (AUTO-REPAIRED)" if g.get("repaired") else ""
        print(f" {st}{rep_tag} {g['name']:28}: {g['message']}")
    print("-" * 75)
    print(f" RESULT: {val_report['passed_gates']}/{val_report['total_gates']} Gates Passed.")
    
    if val_report["success"]:
        print("\n [SUCCESS] Migration complete! All chats, configs, and projects are active.")
        print(" Launch Google Antigravity now to resume your pair programming.")
    else:
        print("\n [!] Some validation gates reported warnings. Review details above.")
    print("=" * 75)
    
    if interactive:
        try:
            input("\nPress Enter to exit...")
        except Exception:
            pass
            
    return {
        "success": val_report["success"],
        "restored_chats": restored_chats,
        "restored_projects": len(projects),
        "validation": val_report
    }
