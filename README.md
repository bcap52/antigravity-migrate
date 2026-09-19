# Antigravity Migrate 🚀

> **Lightweight, zero-dependency, open-source CLI tool to migrate Google Antigravity chat histories, full user configurations, MCP servers, and project workspaces across PCs and operating systems.**

Supports **Windows $\leftrightarrow$ Linux**, **Windows $\leftrightarrow$ Windows**, and **Linux $\leftrightarrow$ Linux** with native distribution family detection (Arch, CachyOS, Omarchy, Debian, Ubuntu, Fedora, openSUSE).

---

## ✨ Features

- **Zero Bloat & Zero External Dependencies**: Powered purely by Python 3.8+ standard library. No `pip install` or C compilers required.
- **1:1 Chat & Config Fidelity**: Migrates every conversation turn, brain artifact, tool output, prompt, plan, and annotation losslessly.
- **Deep System Synchronization**:
  - Automatically translates filesystem paths and file URIs (`file:///C:/...` $\leftrightarrow$ `file:///home/...`).
  - Synchronizes both `conversation_summaries.db` and binary `agyhub_summaries_proto.pb` so chats immediately register under projects in the sidebar.
  - Updates embedded `TrajectoryMetadata` protobuf blobs inside SQLite.
- **Automated & Manual Modes**:
  - **Automated**: Bundles complete project codebases alongside chats, preserving `.git/`, `.agent/`, `.gemini/`, and local project rules intact.
  - **Manual**: Bundles only chats, metadata, and configs, letting you clone or copy your repositories separately.
- **Interactive Workspace Resolution**:
  - **Bulk Base Directory Mapping**: Map all projects into a single folder (e.g. `~/Projects/<Name>`) in one click.
  - **Individual Mapping**: Specify exact custom locations for each project independently.
- **Environment & MCP Variable Injection**:
  - Audits MCP servers for referenced environment variables.
  - Interactively prompts for variable values on target restoration or generates a helper environment shell script.
- **Process Safety Guard**:
  - Detects background `language_server` or `Antigravity` instances to prevent in-memory caches from overwriting disk changes.
- **10-Gate Self-Test & Auto-Repair**:
  - Validates SQLite integrity (`PRAGMA integrity_check`), step counts, brain folders, git repositories, and protobuf consistency.
  - Automatically fixes detected discrepancies on the fly.

---

## 📦 Quick Start

### 1. Source Machine: Exporting

Run the tool on your source PC:

```bash
# Clone or navigate to antigravity-migrate
cd antigravity-migrate

# Run the interactive wizard
python3 -m antigravity_migrate
```

Follow the interactive prompts:
1. Select your intended target operating system (e.g., Linux Arch family).
2. Choose **Full Migration** or **Selective Migration**.
3. Choose **Automated** (bundles codebases) or **Manual** mode.
4. Specify output zip path (default is in your `Downloads` folder).

### 2. Target Machine: Restoring

Transfer the generated `.zip` to your target PC, extract it, and launch:

**On Linux (Arch / CachyOS / Ubuntu / Fedora):**
```bash
unzip antigravity_migration_*.zip -d migration_bundle
cd migration_bundle
./restore.sh
```

**On Windows:**
```cmd
tar -xf antigravity_migration_*.zip
cd migration_bundle
restore.bat
```

The restorer will:
1. Check that Antigravity is not currently running.
2. Confirm OS and distribution compatibility.
3. Restore global configs, skills, rules, and MCP servers.
4. Prompt for detected environment variables (optional).
5. Map project workspaces (Bulk single-directory or individual).
6. Restore conversation databases, brain artifacts, and protobuf indexes.
7. Run the 10-gate verification and auto-repair suite.

---

## 🛠️ CLI Reference

```text
usage: antigravity-migrate [-h] {export,restore,check} ...

Commands:
  export     Export Antigravity chats, configs, and workspaces
  restore    Restore Antigravity bundle on target machine
  check      Run health check and verification on local Antigravity store

Options:
  -h, --help  show this help message and exit
```

### Export Options:
```bash
python3 -m antigravity_migrate export -o ~/backup.zip -m automated
python3 -m antigravity_migrate export -o ~/chats_only.zip -m manual
```

### Restore Options:
```bash
python3 -m antigravity_migrate restore -a /path/to/extracted_bundle
```

### Local Health Check & Auto-Repair:
```bash
python3 -m antigravity_migrate check --repair
```

---

## 📄 License

MIT License. Designed and maintained for the Google Antigravity developer community.
