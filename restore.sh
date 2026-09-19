#!/usr/bin/env bash
# Antigravity Migrate - One-Click Linux/POSIX Restorer Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================================================"
echo "          Starting Antigravity Restoration on Linux / Target System             "
echo "================================================================================"

if command -v python3 >/dev/null 2>&1; then
    python3 restore.py "$@"
elif command -v python >/dev/null 2>&1; then
    python restore.py "$@"
else
    echo ""
    echo "[ERROR] Python 3 is required to restore Antigravity, but was not found."
    echo "Please install Python using your distribution package manager:"
    echo "  Arch/CachyOS: sudo pacman -S python"
    echo "  Debian/Ubuntu: sudo apt install python3"
    echo "  Fedora: sudo dnf install python3"
    exit 1
fi
