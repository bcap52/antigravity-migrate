"""
process_guard.py - Process Safety Guard
Detects and safely manages running Antigravity and language_server processes
to prevent in-memory cache overwriting disk writes on shutdown.
"""

import os
import sys
import subprocess
from typing import List, Dict, Any

def get_running_antigravity_processes() -> List[Dict[str, Any]]:
    """Returns a list of running Antigravity or language_server processes."""
    running = []
    
    # 1. Linux /proc inspection
    if os.path.exists("/proc"):
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                cmd_path = os.path.join("/proc", pid, "cmdline")
                if os.path.exists(cmd_path):
                    with open(cmd_path, "rb") as f:
                        cmd = f.read().lower()
                        if (b"language_server" in cmd or 
                            b"antigravity" in cmd or 
                            b"language_server_linux" in cmd):
                            running.append({
                                "pid": int(pid),
                                "name": "language_server/antigravity (linux)",
                                "raw_cmd": cmd.decode("utf-8", errors="ignore")[:60]
                            })
            except (IOError, OSError):
                pass
        return running
        
    # 2. Windows tasklist check
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"], 
                capture_output=True, 
                text=True, 
                errors="ignore"
            )
            for line in out.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 2:
                    pname = parts[0].lower()
                    pid = parts[1]
                    if ("antigravity" in pname or 
                        "language_server" in pname):
                        running.append({
                            "pid": int(pid) if pid.isdigit() else 0,
                            "name": parts[0],
                            "raw_cmd": parts[0]
                        })
        except Exception:
            pass
            
    return running

def kill_antigravity_processes(procs: List[Dict[str, Any]]) -> bool:
    """Attempts to kill running Antigravity processes."""
    if not procs:
        return True
        
    if os.name == "posix":
        try:
            subprocess.run(["killall", "-9", "language_server", "Antigravity"], capture_output=True)
            for p in procs:
                try:
                    os.kill(p["pid"], 9)
                except Exception:
                    pass
            return True
        except Exception:
            pass
    elif sys.platform == "win32":
        for p in procs:
            pname = p.get("name")
            if pname:
                try:
                    subprocess.run(["taskkill", "/F", "/IM", pname], capture_output=True)
                except Exception:
                    pass
        return True
        
    return False

def ensure_safe_to_modify(interactive: bool = True) -> bool:
    """
    Ensures that Antigravity is not currently running before disk modifications.
    Blocks interactively or kills on user request.
    """
    procs = get_running_antigravity_processes()
    if not procs:
        return True
        
    print("\n" + "!" * 75)
    print(" [CRITICAL WARNING] Antigravity or language_server is currently running!")
    print("!" * 75)
    print(" Antigravity caches conversations in memory. Modifying database and")
    print(" protobuf files while running WILL cause changes to be overwritten on exit.\n")
    print(f" Detected {len(procs)} active process(es):")
    for p in procs:
        print(f"  - PID {p['pid']}: {p['name']}")
    print("-" * 75)
    
    if not interactive:
        return False
        
    while True:
        print("\n Options:")
        print("   [1] Automatically terminate these processes now [Recommended]")
        print("   [2] I have closed Antigravity manually; check again")
        print("   [Q] Abort migration")
        
        choice = input("\nSelect an option [1/2/Q, default 1]: ").strip().lower()
        if choice in ("", "1"):
            print(" Terminating processes...")
            kill_antigravity_processes(procs)
            # Re-verify
            procs = get_running_antigravity_processes()
            if not procs:
                print(" [OK] All Antigravity processes stopped safely.")
                return True
            else:
                print(f" [!] Some processes could not be terminated. {len(procs)} remaining.")
        elif choice == "2":
            procs = get_running_antigravity_processes()
            if not procs:
                print(" [OK] Verified: No Antigravity processes running.")
                return True
            else:
                print(f" [!] {len(procs)} process(es) still detected.")
        elif choice in ("q", "quit", "exit"):
            print(" Migration aborted by user.")
            sys.exit(0)
