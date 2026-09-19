#!/usr/bin/env bash
# Antigravity Migrate - One-Click Linux/POSIX Restorer Launcher
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# If double-clicked in a GUI file manager (no TTY), auto-spawn in user's terminal
if [ ! -t 0 ] && [ -z "$AGY_SPAWNED" ]; then
    export AGY_SPAWNED=1
    for term in x-terminal-emulator konsole gnome-terminal alacritty kitty ghostty xfce4-terminal terminator urxvt xterm; do
        if command -v "$term" >/dev/null 2>&1; then
            case "$term" in
                gnome-terminal) exec gnome-terminal -- "$0" "$@" ;;
                konsole) exec konsole -e "$0" "$@" ;;
                xfce4-terminal) exec xfce4-terminal -e "$0" "$@" ;;
                *) exec "$term" -e "$0" "$@" ;;
            esac
        fi
    done
fi

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
    read -p "Press Enter to exit..."
    exit 1
fi
