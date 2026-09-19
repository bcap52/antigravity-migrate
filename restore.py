#!/usr/bin/env python3
"""
restore.py - Standalone Target Machine Restoration Entrypoint
Runs immediately upon extracting the migration archive on any target PC.
"""

import sys
from pathlib import Path

# Add bundle directory to sys.path
BUNDLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BUNDLE_DIR))

from antigravity_migrate.restorer import run_restoration

def main():
    archive_dir = str(BUNDLE_DIR)
    interactive = "--non-interactive" not in sys.argv
    run_restoration(archive_dir_str=archive_dir, interactive=interactive)

if __name__ == "__main__":
    main()
