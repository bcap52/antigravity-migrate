"""
mcp_auditor.py - MCP Configuration Auditor & Environment Variable Injector
Audits MCP servers for hardcoded keys vs environment variables, and enables interactive
injection on target systems.
"""

import os
import re
import json
from typing import Dict, List, Any, Tuple, Optional

PLACEHOLDER_PATTERNS = [
    r"^YOUR_.*_HERE$",
    r"^<.*>$",
    r"^\$\{.*\}$",
    r"^%[A-Z0-9_]+%$",
    r"^insert_.*_here$"
]

def is_placeholder(val: str) -> bool:
    """Check if a string looks like a template placeholder."""
    val = val.strip()
    if not val:
        return True
    for pat in PLACEHOLDER_PATTERNS:
        if re.match(pat, val, re.IGNORECASE):
            return True
    return False

def mask_secret(val: str) -> str:
    """Masks secret values for display (e.g. ghp_****...1234)."""
    if not val or is_placeholder(val):
        return "[Not set / Placeholder]"
    if len(val) <= 8:
        return "****"
    return f"{val[:4]}****{val[-4:]}"

def audit_mcp_config(mcp_config_path: str) -> Dict[str, Any]:
    """
    Audits mcp_config.json.
    Returns:
      {
        "servers": { server_name: server_def },
        "detected_env_vars": [
           {
             "name": "GITHUB_PERSONAL_ACCESS_TOKEN",
             "server": "github-mcp-server",
             "has_hardcoded_value": True,
             "masked_preview": "ghp_****UWiM",
             "raw_value": "..."
           }
        ]
      }
    """
    result = {
        "servers": {},
        "detected_env_vars": []
    }
    
    if not os.path.exists(mcp_config_path):
        return result
        
    try:
        with open(mcp_config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return result
        
    servers = data.get("mcpServers", {})
    result["servers"] = servers
    
    seen_vars = set()
    
    for sname, sdef in servers.items():
        env = sdef.get("env", {})
        args = sdef.get("args", [])
        
        # 1. Inspect env dictionary
        for k, v in env.items():
            if k not in seen_vars:
                seen_vars.add(k)
                result["detected_env_vars"].append({
                    "name": k,
                    "server": sname,
                    "has_hardcoded_value": not is_placeholder(str(v)),
                    "masked_preview": mask_secret(str(v)),
                    "raw_value": str(v)
                })
                
        # 2. Inspect command args for env flags (e.g., -e GITHUB_TOKEN)
        for i, arg in enumerate(args):
            if arg in ("-e", "--env") and i + 1 < len(args):
                var_candidate = args[i + 1]
                if "=" in var_candidate:
                    var_name, var_val = var_candidate.split("=", 1)
                else:
                    var_name = var_candidate
                    var_val = os.environ.get(var_name, "")
                    
                if var_name not in seen_vars:
                    seen_vars.add(var_name)
                    result["detected_env_vars"].append({
                        "name": var_name,
                        "server": sname,
                        "has_hardcoded_value": not is_placeholder(var_val),
                        "masked_preview": mask_secret(var_val),
                        "raw_value": var_val
                    })
                    
    return result

def prompt_env_variables_interactive(
    detected_vars: List[Dict[str, Any]], 
    target_env: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Prompts user interactively on target machine to enter values for detected variables.
    User can enter values or press Enter to skip.
    """
    if not detected_vars:
        return {}
        
    if target_env is None:
        target_env = dict(os.environ)
        
    print("\n" + "-" * 75)
    print(" ENVIRONMENT VARIABLES AUDIT (FROM HOST MCP CONFIG)")
    print("-" * 75)
    print(" The host configuration references the following variables.")
    print(" You can enter values now to inject them directly into target configs,")
    print(" or press Enter / [S] to skip.\n")
    
    injected_values: Dict[str, str] = {}
    
    for i, item in enumerate(detected_vars, 1):
        vname = item["name"]
        sname = item["server"]
        cur_target = target_env.get(vname, "")
        host_preview = item["masked_preview"]
        
        status_info = []
        if cur_target:
            status_info.append(f"already in target env: {mask_secret(cur_target)}")
        if item["has_hardcoded_value"]:
            status_info.append(f"host config value: {host_preview}")
        else:
            status_info.append("no host value")
            
        status_str = f" ({', '.join(status_info)})" if status_info else ""
        
        print(f" [{i}/{len(detected_vars)}] {vname} (used by: {sname}){status_str}")
        
        # If already set in target env, offer to use it
        default_prompt = f" [{cur_target[:6]}...]" if cur_target else ""
        prompt = f"     Enter value (or press Enter to skip){default_prompt}: "
        
        try:
            val = input(prompt).strip()
            if val:
                injected_values[vname] = val
                print(f"     [OK] Captured {vname}.")
            elif cur_target:
                injected_values[vname] = cur_target
                print(f"     [OK] Keeping existing target env value.")
            else:
                print("     [SKIPPED]")
        except (KeyboardInterrupt, EOFError):
            print("\n     [Skipping remaining environment prompts]")
            break
            
    return injected_values

def inject_env_into_mcp_config(
    mcp_config_path: str, 
    injected_vars: Dict[str, str]
) -> bool:
    """Injects user-provided environment values into target mcp_config.json."""
    if not os.path.exists(mcp_config_path) or not injected_vars:
        return False
        
    try:
        with open(mcp_config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        servers = data.get("mcpServers", {})
        modified = False
        
        for sname, sdef in servers.items():
            env = sdef.get("env", {})
            for k in list(env.keys()):
                if k in injected_vars:
                    env[k] = injected_vars[k]
                    modified = True
            sdef["env"] = env
            
        if modified:
            with open(mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
    except Exception:
        pass
        
    return False

def generate_env_shell_script(
    injected_vars: Dict[str, str], 
    output_path: str, 
    is_posix: bool
) -> bool:
    """Generates an environment source script (.sh or .bat) on target machine."""
    if not injected_vars:
        return False
        
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            if is_posix:
                f.write("#!/usr/bin/env bash\n# Antigravity Environment Variables\n")
                for k, v in injected_vars.items():
                    f.write(f'export {k}="{v}"\n')
            else:
                f.write("@echo off\nREM Antigravity Environment Variables\n")
                for k, v in injected_vars.items():
                    f.write(f'set "{k}={v}"\n')
        return True
    except Exception:
        return False
