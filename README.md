# antigravity-migrate

Tool to migrate Google Antigravity chat histories, configurations, skills (global, plugin, and project-level), MCP servers, and project workspaces between machines and operating systems (Windows and Linux — Arch, CachyOS, Debian/Ubuntu, Fedora, etc.).

It automatically handles path translations (`file:///C:/...` ↔ `file:///home/...`), syncs binary protobuf summaries (`agyhub_summaries_proto.pb`) with SQLite databases so chats immediately appear in sidebar projects, audits MCP environment variables, and validates migration integrity with zero external Python dependencies.

---

## How to Run

### Step 1: Export (Source Machine)

**One-Click (Windows):**
Double-click `antigravity-migrate.exe` or `export.bat`.

**Terminal (Windows or Linux):**
```bash
python3 -m antigravity_migrate
```

Follow the prompts:
1. **Target OS**: Choose your target OS/distro family (e.g. Linux Arch/CachyOS).
2. **Mode**:
   - **Automated**: Bundles complete project codebases alongside chats.
   - **Manual**: Bundles chats, metadata, and local configs (`.agent/`, `.gemini/`, skills). You clone or copy project codebases separately.
3. **Output**: Choose where to save the `.zip` migration archive (default: `Downloads`).

---

### Step 2: Transfer

Copy the generated `.zip` bundle to the target machine via USB, cloud drive, or network share.

---

### Step 3: Restore (Target Machine)

Extract the `.zip` archive on the target machine, then run the restorer:

**One-Click (Linux — CachyOS / Arch / Ubuntu / Fedora):**
- Double-click `restore.sh` (automatically spawns a terminal window), or
- Double-click `restore.desktop`.

**One-Click (Windows):**
- Double-click `restore.bat` or `restore.exe`.

**Terminal (Any OS):**
```bash
python3 restore.py
```

The restore wizard handles:
- **Process Check**: Ensures Antigravity is closed so memory caches don't overwrite changes.
- **MCP Env Variables**: Detects required API keys/env vars and lets you enter them or skip.
- **Workspace Mapping**: Choose between:
  - *Bulk*: Select one base directory (e.g., `~/Projects`) and all projects map automatically.
  - *Individual*: Pick custom paths for each project.
- **Verification**: Automatically runs a 10-gate integrity check and repairs any discrepancies.

---

## CLI Options (Optional / Headless)

```bash
# Export
python3 -m antigravity_migrate export -o ~/backup.zip -m automated
python3 -m antigravity_migrate export -o ~/backup.zip -m manual

# Restore from extracted folder
python3 -m antigravity_migrate restore -a /path/to/extracted_bundle

# Health check and auto-repair existing Antigravity install
python3 -m antigravity_migrate check --repair
```

---

## License

MIT
