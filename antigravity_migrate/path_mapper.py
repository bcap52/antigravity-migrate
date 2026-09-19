"""
path_mapper.py - Cross-Platform Path and URI Mapper
Handles Windows <-> Linux, Windows <-> Windows, Linux <-> Linux path & URI translations.
Supports both Bulk Base-Directory mapping and Individual Project mapping.
"""

import os
import sys
import re
import urllib.parse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

def path_to_uri(path_str: str, is_posix: Optional[bool] = None) -> str:
    """
    Converts a filesystem path string to a file:// URI compatible with Antigravity.
    """
    if is_posix is None:
        is_posix = os.name == "posix"
        
    path_norm = str(path_str).replace("\\", "/")
    
    if is_posix:
        if path_norm.startswith("/"):
            posix_path = path_norm
        else:
            p = Path(path_str).expanduser().resolve()
            posix_path = str(p).replace("\\", "/")
            m = re.match(r"^[a-zA-Z]:(.*)", posix_path)
            if m:
                posix_path = m.group(1)
                
        encoded_path = urllib.parse.quote(posix_path, safe="/")
        if not encoded_path.startswith("/"):
            encoded_path = "/" + encoded_path
        return f"file://{encoded_path}"
    else:
        # Windows: file:///C:/Users/... or file:///c%3A/...
        p = Path(path_str).expanduser().resolve()
        win_path = str(p).replace("\\", "/")
        m = re.match(r"^([a-zA-Z]):/(.*)", win_path)
        if m:
            drive = m.group(1).lower()
            rest = urllib.parse.quote(m.group(2), safe="/")
            return f"file:///{drive}:/{rest}"
        else:
            return f"file://{urllib.parse.quote(win_path, safe='/')}"

def uri_to_path(uri: str) -> str:
    """
    Converts a file:// URI back to a local filesystem path.
    """
    if not uri.startswith("file://"):
        return uri
        
    parsed = urllib.parse.urlparse(uri)
    raw_path = urllib.parse.unquote(parsed.path)
    
    # Handle Windows drive letters in URIs (e.g. /C:/path or /c:/path or /c%3A/path)
    raw_path = raw_path.replace("%3A", ":").replace("%3a", ":")
    
    m = re.match(r"^/([a-zA-Z]:.*)", raw_path)
    if m:
        return m.group(1).replace("/", "\\")
        
    return raw_path

def sanitize_filename(name: str) -> str:
    """Sanitize project name for directory creation."""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def resolve_bulk_mappings(
    projects: List[Dict[str, Any]], 
    base_dir_str: str, 
    is_target_posix: bool
) -> Dict[str, Tuple[str, str]]:
    """
    Resolves all project paths into a single base directory.
    Returns mapping: { project_id: (target_path, target_uri) }
    """
    clean_base = base_dir_str.replace("\\", "/")
    mappings = {}
    
    for proj in projects:
        pid = proj.get("id")
        name = proj.get("name", "Unnamed Project")
        clean_name = sanitize_filename(name)
        
        if is_target_posix:
            target_proj_path = clean_base.rstrip("/") + "/" + clean_name
        else:
            target_proj_path = str(Path(base_dir_str).expanduser().resolve() / clean_name)
            
        target_uri = path_to_uri(target_proj_path, is_posix=is_target_posix)
        mappings[pid] = (target_proj_path, target_uri)
        
    return mappings

def find_candidate_project_dir(proj_name: str, search_roots: Optional[List[str]] = None) -> Optional[str]:
    """
    Checks common directories on target system to see if project folder already exists.
    """
    if search_roots is None:
        home = Path.home()
        search_roots = [
            str(home),
            str(home / "Projects"),
            str(home / "Documents"),
            str(home / "workspace"),
            str(home / "repos"),
            os.getcwd()
        ]
        
    clean_name = sanitize_filename(proj_name)
    for root in search_roots:
        if not os.path.exists(root):
            continue
        try:
            cand = os.path.join(root, clean_name)
            if os.path.isdir(cand):
                return str(Path(cand).resolve())
        except Exception:
            pass
            
    return None
