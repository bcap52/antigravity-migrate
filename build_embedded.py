import zipfile
import io
import base64
from pathlib import Path

root = Path(__file__).resolve().parent

files_to_bundle = [
    "restore.sh",
    "restore.bat",
    "restore.desktop",
    "restore.py",
    "antigravity_migrate/__init__.py",
    "antigravity_migrate/__main__.py",
    "antigravity_migrate/restorer.py",
    "antigravity_migrate/proto_engine.py",
    "antigravity_migrate/path_mapper.py",
    "antigravity_migrate/os_detector.py",
    "antigravity_migrate/mcp_auditor.py",
    "antigravity_migrate/process_guard.py",
    "antigravity_migrate/validator.py",
    "antigravity_migrate/discover.py",
]

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for rel in files_to_bundle:
        p = root / rel
        if not p.exists():
            raise FileNotFoundError(f"Missing required restorer file: {p}")
        z.writestr(rel, p.read_bytes())

b64_data = base64.b64encode(buf.getvalue()).decode("ascii")

target_file = root / "antigravity_migrate" / "embedded_restorer.py"
content = f'''"""
embedded_restorer.py - Embedded Self-Contained Restorer Archive
Contains the byte-exact payload of all restorer scripts and modules.
Guarantees that export bundles ALWAYS include restore.sh, restore.bat,
restore.desktop, restore.py, and the antigravity_migrate runtime,
even when executed from a standalone PyInstaller executable.
"""

import io
import base64
import zipfile
from datetime import datetime
from pathlib import Path

RESTORER_BUNDLE_B64 = {repr(b64_data)}

def inject_restorer_files(target_zip: zipfile.ZipFile, root_dir_fallback: Path = None):
    """
    Injects all restore scripts and runtime modules into the migration zip archive.
    """
    raw_bytes = base64.b64decode(RESTORER_BUNDLE_B64)
    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as src_zip:
        for info in src_zip.infolist():
            arcname = info.filename
            data = None
            if root_dir_fallback:
                local_p = root_dir_fallback / arcname
                if local_p.exists() and local_p.is_file():
                    try:
                        data = local_p.read_bytes()
                    except Exception:
                        pass
            if data is None:
                data = src_zip.read(arcname)
                
            zinfo = zipfile.ZipInfo(arcname)
            zinfo.date_time = datetime.now().timetuple()[:6]
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            # Make restore.sh executable on Linux
            if arcname.endswith(".sh"):
                zinfo.external_attr = 0o755 << 16
            else:
                zinfo.external_attr = 0o644 << 16
                
            target_zip.writestr(zinfo, data)
'''

target_file.write_text(content, encoding="utf-8")
print(f"Successfully wrote {target_file} (Payload size: {len(b64_data)} chars)")
