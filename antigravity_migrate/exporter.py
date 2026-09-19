"""
exporter.py - Migration Archive Packager
Packages selected chats, configurations, MCP servers, and project workspaces into a
portable, self-contained migration archive with zero external dependencies.
"""

import os
import sys
import json
import shutil
import zipfile
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable

from .discover import discover_all, get_default_paths
from .os_detector import detect_system, TARGET_OS_OPTIONS
from .mcp_auditor import audit_mcp_config

MODULE_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODULE_DIR.parent

def build_export_manifest(
    source_sys: Dict[str, Any],
    target_intent: Dict[str, Any],
    mode: str,
    selected_cids: List[str],
    selected_pids: List[str],
    discovery: Dict[str, Any]
) -> Dict[str, Any]:
    """Constructs the migration_manifest.json object."""
    convs = []
    for cid in selected_cids:
        if cid in discovery["conversations"]:
            cinfo = discovery["conversations"][cid]
            convs.append(cinfo)
            
    projs = []
    for pid in selected_pids:
        if pid in discovery["projects"]:
            pinfo = dict(discovery["projects"][pid])
            pinfo["is_bundled"] = (mode == "automated" and pinfo.get("exists_on_disk", False))
            projs.append(pinfo)
            
    return {
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_system": source_sys,
        "target_intent": target_intent,
        "mode": mode,
        "conversations": convs,
        "projects": projs,
        "global_configs": discovery["global_configs"],
        "mcp_env_vars": discovery["global_configs"].get("mcp_audit", {}).get("detected_env_vars", [])
    }

def export_migration_bundle(
    output_zip_path: str,
    mode: str = "automated",
    target_intent: Optional[Dict[str, Any]] = None,
    selected_cids: Optional[List[str]] = None,
    selected_pids: Optional[List[str]] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None
) -> Dict[str, Any]:
    """
    Exports Antigravity chats, configs, and workspaces into a zip archive.
    Modes:
      - 'automated': Workspaces bundled + Chats + Configs
      - 'manual': Chats + Configs + Manifest only
      - 'config_only': Configs + MCPs only
    """
    def report(msg: str, pct: float = 0.0):
        if progress_cb:
            progress_cb(msg, pct)

    report("Discovering host Antigravity environment...", 0.05)
    discovery = discover_all()
    source_sys = detect_system()
    
    if target_intent is None:
        target_intent = TARGET_OS_OPTIONS[0] # Default to Linux Arch family
        
    all_cids = list(discovery["conversations"].keys())
    all_pids = list(discovery["projects"].keys())
    
    if mode == "config_only":
        cids_to_export = []
        pids_to_export = []
    else:
        cids_to_export = selected_cids if selected_cids is not None else all_cids
        pids_to_export = selected_pids if selected_pids is not None else all_pids
        
    manifest = build_export_manifest(
        source_sys=source_sys,
        target_intent=target_intent,
        mode=mode,
        selected_cids=cids_to_export,
        selected_pids=pids_to_export,
        discovery=discovery
    )
    
    paths = discovery["paths"]
    sum_db_path = paths["summaries_db"]
    raw_summaries: Dict[str, bytes] = {}
    
    # Read raw_summary blobs for selected chats from SQLite
    if os.path.exists(sum_db_path) and cids_to_export:
        try:
            conn = sqlite3.connect(sum_db_path)
            c = conn.cursor()
            for cid in cids_to_export:
                c.execute("SELECT raw_summary FROM conversation_summaries WHERE conversation_id=?", (cid,))
                row = c.fetchone()
                if row and row[0]:
                    raw_summaries[cid] = row[0]
            conn.close()
        except Exception:
            pass

    out_path = Path(output_zip_path).expanduser().resolve()
    if out_path.is_dir() or str(output_zip_path).rstrip().endswith(("/", "\\")):
        out_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_path / f"antigravity_migration_{ts}.zip"
    elif not out_path.name.lower().endswith(".zip"):
        out_path = out_path.with_name(out_path.name + ".zip")
        
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    report(f"Packaging archive to {out_path.name}...", 0.15)
    
    total_items = (
        len(cids_to_export) * 2 + 
        (len(pids_to_export) if mode == "automated" else 0) + 
        10
    )
    completed = 0
    
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # 1. Write migration_manifest.json
        manifest_str = json.dumps(manifest, indent=2)
        zipf.writestr("migration_manifest.json", manifest_str)
        
        # 2. Bundle Restorer Code into zip root
        report("Bundling portable self-contained restorer...", 0.20)
        
        # Copy antigravity_migrate module package files
        for root, dirs, files in os.walk(MODULE_DIR):
            for file in files:
                if file.endswith((".py", ".md", ".json")) and "__pycache__" not in root:
                    src_file = os.path.join(root, file)
                    rel_to_module = os.path.relpath(src_file, ROOT_DIR)
                    try:
                        zipf.write(src_file, rel_to_module)
                    except Exception:
                        pass
                    
        # Write root launchers
        restore_py_path = ROOT_DIR / "restore.py"
        if restore_py_path.exists():
            try:
                zipf.write(restore_py_path, "restore.py")
            except Exception:
                pass
            
        restore_sh_path = ROOT_DIR / "restore.sh"
        if restore_sh_path.exists():
            try:
                zipf.write(restore_sh_path, "restore.sh")
            except Exception:
                pass
            
        restore_bat_path = ROOT_DIR / "restore.bat"
        if restore_bat_path.exists():
            try:
                zipf.write(restore_bat_path, "restore.bat")
            except Exception:
                pass
            
        restore_desktop_path = ROOT_DIR / "restore.desktop"
        if restore_desktop_path.exists():
            try:
                zipf.write(restore_desktop_path, "restore.desktop")
            except Exception:
                pass
            
        restore_exe_path = ROOT_DIR / "dist" / "restore.exe"
        if restore_exe_path.exists():
            try:
                zipf.write(restore_exe_path, "restore.exe")
            except Exception:
                pass
            
        # 3. Package Global Configurations
        report("Packaging global configurations & rules...", 0.30)
        config_dir = Path(paths["config"])
        if config_dir.exists():
            for root, dirs, files in os.walk(config_dir):
                # Don't bundle projects folder here; projects are packaged explicitly
                rel = os.path.relpath(root, config_dir)
                if rel.startswith("projects") or rel == "projects":
                    continue
                for f in files:
                    full_p = os.path.join(root, f)
                    try:
                        zipf.write(full_p, os.path.join("config", rel, f) if rel != "." else os.path.join("config", f))
                    except Exception:
                        pass
                    
        # Package MCP schemas if present in antigravity/mcp
        mcp_dir = Path(paths["antigravity"]) / "mcp"
        if mcp_dir.exists() and mcp_dir.is_dir():
            for root, dirs, files in os.walk(mcp_dir):
                rel = os.path.relpath(root, mcp_dir)
                for f in files:
                    full_p = os.path.join(root, f)
                    try:
                        zipf.write(full_p, os.path.join("mcp", rel, f) if rel != "." else os.path.join("mcp", f))
                    except Exception:
                        pass
                    
        # 4. Package Project JSON definitions
        for pid in pids_to_export:
            pjson_path = Path(paths["projects"]) / f"{pid}.json"
            if pjson_path.exists():
                try:
                    zipf.write(pjson_path, f"projects/{pid}.json")
                except Exception:
                    pass
                
        # 5. Package Conversations
        report(f"Packaging {len(cids_to_export)} conversation histories...", 0.40)
        for i, cid in enumerate(cids_to_export, 1):
            pct = 0.40 + (0.35 * (i / max(len(cids_to_export), 1)))
            report(f"Exporting chat: {cid[:8]}...", pct)
            
            # Database
            db_file = Path(paths["conversations"]) / f"{cid}.db"
            if db_file.exists():
                try:
                    zipf.write(db_file, f"chats/conversations/{cid}.db")
                except Exception:
                    pass
                
            # Annotation
            annot_file = Path(paths["annotations"]) / f"{cid}.pbtxt"
            if annot_file.exists():
                try:
                    zipf.write(annot_file, f"chats/annotations/{cid}.pbtxt")
                except Exception:
                    pass
                
            # Raw summary binary blob
            if cid in raw_summaries:
                try:
                    zipf.writestr(f"chats/raw_summaries/{cid}.bin", raw_summaries[cid])
                except Exception:
                    pass
                
            # Brain folder
            brain_dir = Path(paths["brain"]) / cid
            if brain_dir.exists() and brain_dir.is_dir():
                for root, dirs, files in os.walk(brain_dir):
                    rel = os.path.relpath(root, brain_dir)
                    for f in files:
                        full_p = os.path.join(root, f)
                        zip_rel = os.path.join(f"chats/brain/{cid}", rel, f) if rel != "." else os.path.join(f"chats/brain/{cid}", f)
                        try:
                            zipf.write(full_p, zip_rel)
                        except Exception:
                            pass

        # 6. Package Workspaces & Local Project Configs
        if mode == "automated":
            report("Packaging project workspaces (.git and local configs preserved)...", 0.75)
            for j, pid in enumerate(pids_to_export, 1):
                pinfo = discovery["projects"].get(pid, {})
                loc_path = pinfo.get("local_path")
                pname = pinfo.get("name", pid)
                if loc_path and os.path.exists(loc_path) and os.path.isdir(loc_path):
                    report(f"Bundling workspace: {pname}...", 0.75 + (0.20 * (j / max(len(pids_to_export), 1))))
                    for root, dirs, files in os.walk(loc_path):
                        # Always include .git, .agent, .gemini
                        rel = os.path.relpath(root, loc_path)
                        for f in files:
                            full_p = os.path.join(root, f)
                            zip_rel = os.path.join(f"workspaces/{pid}", rel, f) if rel != "." else os.path.join(f"workspaces/{pid}", f)
                            try:
                                zipf.write(full_p, zip_rel)
                            except Exception:
                                pass
        elif mode == "manual":
            report("Packaging local project configs (.agent, .gemini, local skills & rules)...", 0.75)
            for j, pid in enumerate(pids_to_export, 1):
                pinfo = discovery["projects"].get(pid, {})
                loc_path = pinfo.get("local_path")
                if loc_path and os.path.exists(loc_path) and os.path.isdir(loc_path):
                    for cfg_name in [".agent", ".gemini", ".mcp.json", "mcp.json", "AGENTS.md", "GEMINI.md"]:
                        cfg_target = os.path.join(loc_path, cfg_name)
                        if os.path.exists(cfg_target):
                            if os.path.isdir(cfg_target):
                                for root, dirs, files in os.walk(cfg_target):
                                    rel = os.path.relpath(root, loc_path)
                                    for f in files:
                                        full_p = os.path.join(root, f)
                                        zip_rel = os.path.join(f"project_configs/{pid}", rel, f)
                                        try:
                                            zipf.write(full_p, zip_rel)
                                        except Exception:
                                            pass
                            else:
                                zipf.write(cfg_target, f"project_configs/{pid}/{cfg_name}")

    report(f"Export completed: {out_path.stat().st_size / 1024 / 1024:.2f} MB", 1.0)
    
    return {
        "success": True,
        "archive_path": str(out_path),
        "archive_size_mb": out_path.stat().st_size / 1024 / 1024,
        "conversations_count": len(cids_to_export),
        "projects_count": len(pids_to_export),
        "manifest": manifest
    }
