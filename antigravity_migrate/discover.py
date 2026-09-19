"""
discover.py - Host System Discovery Engine
Discovers all Antigravity chats, project mappings, global configurations, and MCP servers.
"""

import os
import sys
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

from .proto_engine import extract_summary_metadata
from .path_mapper import uri_to_path
from .mcp_auditor import audit_mcp_config

def get_default_paths() -> Dict[str, Path]:
    """Returns standard Antigravity paths on host machine."""
    home = Path.home()
    gemini = home / ".gemini"
    return {
        "gemini": gemini,
        "antigravity": gemini / "antigravity",
        "config": gemini / "config",
        "conversations": gemini / "antigravity" / "conversations",
        "brain": gemini / "antigravity" / "brain",
        "annotations": gemini / "antigravity" / "annotations",
        "summaries_db": gemini / "antigravity" / "conversation_summaries.db",
        "agyhub_pb": gemini / "antigravity" / "agyhub_summaries_proto.pb",
        "projects": gemini / "config" / "projects",
        "skills": gemini / "config" / "skills",
        "plugins": gemini / "config" / "plugins",
        "rules": gemini / "config" / "rules",
        "sidecars": gemini / "config" / "sidecars",
        "mcp_config": gemini / "config" / "mcp_config.json",
        "user_config": gemini / "config" / "config.json"
    }

def get_git_remote(repo_path: str) -> Optional[str]:
    """Attempts to retrieve git remote URL for a workspace."""
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.isdir(git_dir):
        return None
    try:
        out = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=3
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None

def discover_all(custom_gemini_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Scans host system and returns comprehensive discovery manifest.
    """
    paths = get_default_paths()
    if custom_gemini_path:
        gemini = Path(custom_gemini_path).resolve()
        paths["gemini"] = gemini
        paths["antigravity"] = gemini / "antigravity"
        paths["config"] = gemini / "config"
        paths["conversations"] = gemini / "antigravity" / "conversations"
        paths["brain"] = gemini / "antigravity" / "brain"
        paths["annotations"] = gemini / "antigravity" / "annotations"
        paths["summaries_db"] = gemini / "antigravity" / "conversation_summaries.db"
        paths["agyhub_pb"] = gemini / "antigravity" / "agyhub_summaries_proto.pb"
        paths["projects"] = gemini / "config" / "projects"
        paths["skills"] = gemini / "config" / "skills"
        paths["plugins"] = gemini / "config" / "plugins"
        paths["rules"] = gemini / "config" / "rules"
        paths["sidecars"] = gemini / "config" / "sidecars"
        paths["mcp_config"] = gemini / "config" / "mcp_config.json"
        paths["user_config"] = gemini / "config" / "config.json"

    result = {
        "paths": {k: str(v) for k, v in paths.items()},
        "conversations": {},
        "projects": {},
        "global_configs": {
            "skills": [],
            "plugins": [],
            "rules": [],
            "sidecars": [],
            "has_config_json": False,
            "has_mcp_config": False,
            "mcp_audit": {}
        }
    }

    # 1. Discover Projects
    projects_dir = paths["projects"]
    if projects_dir.exists():
        for pfile in projects_dir.glob("*.json"):
            try:
                with open(pfile, "r", encoding="utf-8") as f:
                    pdata = json.load(f)
                    pid = pdata.get("id") or pfile.stem
                    pname = pdata.get("name", pfile.stem)
                    resources = pdata.get("projectResources", {}).get("resources", [])
                    furi = None
                    if resources and "gitFolder" in resources[0]:
                        furi = resources[0]["gitFolder"].get("folderUri")
                    
                    loc_path = uri_to_path(furi) if furi else ""
                    exists = os.path.exists(loc_path) if loc_path else False
                    is_git = os.path.isdir(os.path.join(loc_path, ".git")) if exists else False
                    remote = get_git_remote(loc_path) if is_git else None
                    
                    result["projects"][pid] = {
                        "id": pid,
                        "name": pname,
                        "folder_uri": furi,
                        "local_path": loc_path,
                        "exists_on_disk": exists,
                        "is_git_repo": is_git,
                        "git_remote": remote,
                        "chats": []
                    }
            except Exception:
                pass

    # 2. Discover Conversations
    sum_db = paths["summaries_db"]
    if sum_db.exists():
        try:
            conn = sqlite3.connect(sum_db)
            c = conn.cursor()
            c.execute("""
                SELECT conversation_id, title, preview, step_count, 
                       workspace_uris, project_id, raw_summary 
                FROM conversation_summaries
            """)
            rows = c.fetchall()
            for r in rows:
                cid, title, preview, step_count, ws_uris_str, pid, raw_bytes = r
                
                # If title is blank, parse raw_summary protobuf or check annotation
                if not title and raw_bytes:
                    parsed_meta = extract_summary_metadata(raw_bytes)
                    title = parsed_meta.get("title") or title
                    if not pid:
                        pid = parsed_meta.get("project_id") or pid
                    if not step_count:
                        step_count = parsed_meta.get("step_count") or step_count
                        
                if not title:
                    annot_file = paths["annotations"] / f"{cid}.pbtxt"
                    if annot_file.exists():
                        try:
                            with open(annot_file, "r", encoding="utf-8") as af:
                                for line in af:
                                    if 'title:"' in line:
                                        t_part = line.split('title:"', 1)[1]
                                        title = t_part.split('"', 1)[0]
                                        break
                        except Exception:
                            pass
                            
                if not title:
                    title = preview or f"Conversation {cid[:8]}"
                    
                ws_uris = []
                if ws_uris_str:
                    try:
                        ws_uris = json.loads(ws_uris_str)
                    except Exception:
                        ws_uris = [ws_uris_str]
                        
                db_exists = (paths["conversations"] / f"{cid}.db").exists()
                brain_exists = (paths["brain"] / cid).exists()
                annot_exists = (paths["annotations"] / f"{cid}.pbtxt").exists()
                
                convo_info = {
                    "id": cid,
                    "title": title,
                    "step_count": step_count,
                    "project_id": pid or "",
                    "workspace_uris": ws_uris,
                    "has_db": db_exists,
                    "has_brain": brain_exists,
                    "has_annot": annot_exists,
                    "raw_summary_len": len(raw_bytes) if raw_bytes else 0
                }
                
                result["conversations"][cid] = convo_info
                
                # Bind chat to project
                if pid and pid in result["projects"]:
                    result["projects"][pid]["chats"].append(cid)
                elif ws_uris:
                    # Match by URI
                    for p_id, p_info in result["projects"].items():
                        if p_info.get("folder_uri") in ws_uris:
                            result["projects"][p_id]["chats"].append(cid)
                            convo_info["project_id"] = p_id
                            break
                            
            conn.close()
        except Exception as e:
            result["db_error"] = str(e)

    # Also discover any orphaned conversations present on disk but not in DB
    conv_dir = paths["conversations"]
    if conv_dir.exists():
        for db_file in conv_dir.glob("*.db"):
            cid = db_file.stem
            if cid not in result["conversations"]:
                brain_exists = (paths["brain"] / cid).exists()
                annot_exists = (paths["annotations"] / f"{cid}.pbtxt").exists()
                result["conversations"][cid] = {
                    "id": cid,
                    "title": f"Unindexed Chat ({cid[:8]})",
                    "step_count": 0,
                    "project_id": "",
                    "workspace_uris": [],
                    "has_db": True,
                    "has_brain": brain_exists,
                    "has_annot": annot_exists,
                    "raw_summary_len": 0
                }

    # 3. Discover Global Configurations
    for key, path in [("skills", paths["skills"]), ("plugins", paths["plugins"]), 
                      ("rules", paths["rules"]), ("sidecars", paths["sidecars"])]:
        if path.exists() and path.is_dir():
            result["global_configs"][key] = [item.name for item in path.iterdir()]
            
    result["global_configs"]["has_config_json"] = paths["user_config"].exists()
    result["global_configs"]["has_mcp_config"] = paths["mcp_config"].exists()
    
    if paths["mcp_config"].exists():
        result["global_configs"]["mcp_audit"] = audit_mcp_config(str(paths["mcp_config"]))

    return result
