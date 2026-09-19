"""
cli.py - Interactive Terminal Command Line Interface for Antigravity Migrate
Provides an intuitive, zero-dependency terminal wizard with ASCII screens,
progress reporting, and selective migration menus.
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .os_detector import detect_system, TARGET_OS_OPTIONS
from .discover import discover_all
from .exporter import export_migration_bundle
from .restorer import run_restoration
from .validator import run_validation_suite

BANNER = """
================================================================================
                    ANTIGRAVITY MIGRATION TOOL (v1.0.0)                         
               Cross-Platform Chat, Config & Workspace Porter                   
================================================================================
"""

def print_header(title: str):
    print("\n" + "=" * 80)
    print(f" {title.center(78)}")
    print("=" * 80)

def prompt_target_os() -> Dict[str, Any]:
    print("\n Select Intended Target Operating System:")
    for i, opt in enumerate(TARGET_OS_OPTIONS, 1):
        def_mark = " [Default]" if i == 1 else ""
        print(f"   [{i}] {opt['label']}{def_mark}")
        
    choice = input("\nTarget OS [1-5, default 1]: ").strip()
    idx = 0
    if choice.isdigit() and 1 <= int(choice) <= len(TARGET_OS_OPTIONS):
        idx = int(choice) - 1
    return TARGET_OS_OPTIONS[idx]

def prompt_migration_mode() -> str:
    print("\n" + "-" * 80)
    print(" SELECT MIGRATION MODE")
    print("-" * 80)
    print(" [1] Automated (Bundle Project Workspaces + Chats + Configs)")
    print("     -> Bundles full source directories (.git, .agent, .gemini preserved)")
    print("     -> Best for moving to a clean machine without re-cloning\n")
    print(" [2] Manual (Bundle Chats + Configs + Manifest Only)")
    print("     -> Leaves codebases on disk; you clone or copy repos separately")
    print("     -> Best for large repos or bandwidth-constrained transfers\n")
    
    choice = input("Choose mode [1/2, default 1]: ").strip()
    return "manual" if choice == "2" else "automated"

def prompt_selective_migration(discovery: Dict[str, Any]) -> tuple:
    projects = discovery["projects"]
    conversations = discovery["conversations"]
    
    print("\n" + "-" * 80)
    print(" SELECTIVE PROJECT & CHAT MIGRATION")
    print("-" * 80)
    print(" Available Projects:")
    
    proj_list = list(projects.values())
    for i, p in enumerate(proj_list, 1):
        c_count = len(p["chats"])
        print(f"   [{i}] {p['name']:30} ({c_count} chats linked)")
        
    print(f"   [A] Select All Projects ({len(proj_list)})")
    
    choice = input("\nEnter project numbers to include (comma-separated, or 'A' for all) [A]: ").strip()
    selected_pids = []
    if not choice or choice.lower() == "a":
        selected_pids = [p["id"] for p in proj_list]
    else:
        for num in choice.split(","):
            num = num.strip()
            if num.isdigit() and 1 <= int(num) <= len(proj_list):
                selected_pids.append(proj_list[int(num) - 1]["id"])
                
    # Gather chats linked to selected projects
    selected_cids = []
    for pid in selected_pids:
        if pid in projects:
            selected_cids.extend(projects[pid]["chats"])
            
    # Also ask if unassigned chats should be included
    unassigned = [cid for cid, c in conversations.items() if not c.get("project_id")]
    if unassigned:
        inc_unassigned = input(f"\nInclude {len(unassigned)} standalone / unassigned chats? [Y/n]: ").strip().lower()
        if inc_unassigned not in ("n", "no"):
            selected_cids.extend(unassigned)
            
    return selected_pids, selected_cids

def run_export_wizard():
    print(BANNER)
    host_sys = detect_system()
    discovery = discover_all()
    
    num_chats = len(discovery["conversations"])
    num_projs = len(discovery["projects"])
    num_skills = len(discovery["global_configs"]["skills"])
    num_mcps = len(discovery["global_configs"].get("mcp_audit", {}).get("servers", {}))
    
    print(f" Host System: {host_sys.get('distro_name', host_sys['os'])} ({platform.machine()})")
    print(f" Detected   : {num_chats} Chats | {num_projs} Projects | {num_skills} Skills | {num_mcps} MCP Servers")
    print("-" * 80)
    
    # 1. Target OS Intent
    target_intent = prompt_target_os()
    print(f" Selected Target: {target_intent['label']}")
    
    # 2. Scope Selection
    print("\n Select Migration Scope:")
    print("   [1] Full Migration (All chats, projects, configs & MCPs) [Recommended]")
    print("   [2] Selective Migration (Choose projects or specific chats)")
    print("   [3] Config & MCP Migration Only (No chat histories or codebases)")
    print("   [Q] Quit")
    
    scope_choice = input("\nSelect an option [1-3, Q, default 1]: ").strip().lower()
    if scope_choice in ("q", "quit", "exit"):
        print(" Exiting.")
        sys.exit(0)
        
    selected_pids = None
    selected_cids = None
    mode = "automated"
    
    if scope_choice == "3":
        mode = "config_only"
    else:
        if scope_choice == "2":
            selected_pids, selected_cids = prompt_selective_migration(discovery)
        mode = prompt_migration_mode()

    # 3. Output Path
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_zip_name = f"antigravity_migration_{ts}.zip"
    default_zip_path = str(Path.home() / "Downloads" / default_zip_name) if (Path.home() / "Downloads").exists() else str(Path.cwd() / default_zip_name)
    
    zip_path_input = input(f"\nOutput zip path [{default_zip_path}]: ").strip()
    zip_path = zip_path_input if zip_path_input else default_zip_path
    
    print("\n" + "=" * 80)
    print(" PACKAGING MIGRATION ARCHIVE")
    print("=" * 80)
    
    def on_progress(msg: str, pct: float):
        bar_len = 30
        filled = int(bar_len * pct)
        bar = "=" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r [{bar}] {pct*100:5.1f}% | {msg[:35]:35}")
        sys.stdout.flush()
        if pct >= 1.0:
            sys.stdout.write("\n")
            
    res = export_migration_bundle(
        output_zip_path=zip_path,
        mode=mode,
        target_intent=target_intent,
        selected_cids=selected_cids,
        selected_pids=selected_pids,
        progress_cb=on_progress
    )
    
    print("-" * 80)
    print(f" [SUCCESS] Migration archive created successfully!")
    print(f" File Location : {res['archive_path']}")
    print(f" Archive Size  : {res['archive_size_mb']:.2f} MB")
    print(f" Included      : {res['conversations_count']} Chats, {res['projects_count']} Projects, Configs & Restorer")
    print("\n Transfer this .zip to your target machine, extract it, and run:")
    print("   ./restore.sh    (on Linux)")
    print("   restore.bat     (on Windows)")
    print("=" * 80)

def main():
    parser = argparse.ArgumentParser(
        description="Antigravity Migrate: Cross-Platform Chat, Config & Workspace Porter"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Export subparser
    exp_parser = subparsers.add_parser("export", help="Export Antigravity chats, configs, and workspaces")
    exp_parser.add_argument("-o", "--output", help="Output .zip path")
    exp_parser.add_argument("-m", "--mode", choices=["automated", "manual", "config_only"], default=None)
    
    # Restore subparser
    res_parser = subparsers.add_parser("restore", help="Restore Antigravity bundle on target machine")
    res_parser.add_argument("-a", "--archive-dir", default=".", help="Directory of unzipped bundle")
    res_parser.add_argument("--non-interactive", action="store_true", help="Run without interactive prompts")
    
    # Check subparser
    chk_parser = subparsers.add_parser("check", help="Run health check and verification on local Antigravity store")
    chk_parser.add_argument("--repair", action="store_true", help="Auto-repair detected discrepancies")
    
    args = parser.parse_args()
    
    if args.command == "export":
        if args.output:
            export_migration_bundle(output_zip_path=args.output, mode=args.mode or "automated")
        else:
            run_export_wizard()
    elif args.command == "restore":
        run_restoration(archive_dir_str=args.archive_dir, interactive=not args.non_interactive)
    elif args.command == "check":
        print(BANNER)
        print(" Running local Antigravity integrity verification...")
        res = run_validation_suite(gemini_dir_str=str(Path.home() / ".gemini"), auto_repair=args.repair)
        for g in res["gates"]:
            st = "[PASS]" if g["passed"] else "[FAIL]"
            rep = " (AUTO-REPAIRED)" if g.get("repaired") else ""
            print(f"  {st}{rep} {g['name']:25}: {g['message']}")
        print(f"\n Score: {res['passed_gates']}/{res['total_gates']} passed.")
    else:
        # Default interactive menu
        run_export_wizard()

if __name__ == "__main__":
    main()
