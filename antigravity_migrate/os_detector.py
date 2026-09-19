"""
os_detector.py - OS & Linux Distribution Family Detector
Supports Windows and Linux (Arch, CachyOS, Omarchy, Debian/Ubuntu, Fedora/RHEL, openSUSE).
"""

import os
import sys
import platform
from typing import Dict, Any, Optional

ARCH_FLAVORS = {"arch", "cachyos", "omarchy", "manjaro", "endeavouros", "garuda", "artix", "parabola"}
DEBIAN_FLAVORS = {"debian", "ubuntu", "pop", "linuxmint", "elementary", "zorin", "kali", "raspbian", "deepin"}
FEDORA_FLAVORS = {"fedora", "rhel", "centos", "rocky", "alma", "amzn"}
SUSE_FLAVORS = {"opensuse", "opensuse-tumbleweed", "opensuse-leap", "sles", "sled"}

def parse_os_release() -> Dict[str, str]:
    """Parse /etc/os-release or /usr/lib/os-release on Linux systems."""
    info = {}
    candidates = ["/etc/os-release", "/usr/lib/os-release"]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            v = v.strip("\"'")
                            info[k] = v
                if info:
                    break
            except Exception:
                pass
    return info

def detect_system() -> Dict[str, Any]:
    """Detect current system OS, distribution, family, and path characteristics."""
    sys_name = platform.system().lower()
    
    if sys_name == "windows":
        release = platform.release()
        ver = platform.version()
        return {
            "os": "windows",
            "family": "windows",
            "distro_id": "windows",
            "distro_name": f"Windows {release}",
            "version": ver,
            "path_sep": "\\",
            "uri_prefix": "file:///",
            "is_posix": False
        }
    
    if sys_name == "linux":
        os_rel = parse_os_release()
        distro_id = os_rel.get("ID", "").lower()
        id_like = [x.lower() for x in os_rel.get("ID_LIKE", "").split()]
        pretty_name = os_rel.get("PRETTY_NAME", "") or os_rel.get("NAME", "Linux")
        version_id = os_rel.get("VERSION_ID", "")
        
        # Determine Linux family
        family = "generic_linux"
        all_identifiers = {distro_id} | set(id_like)
        
        if all_identifiers & ARCH_FLAVORS:
            family = "arch"
        elif all_identifiers & DEBIAN_FLAVORS:
            family = "debian"
        elif all_identifiers & FEDORA_FLAVORS:
            family = "fedora"
        elif all_identifiers & SUSE_FLAVORS:
            family = "suse"
            
        return {
            "os": "linux",
            "family": family,
            "distro_id": distro_id or "linux",
            "distro_name": pretty_name,
            "version": version_id,
            "id_like": id_like,
            "path_sep": "/",
            "uri_prefix": "file://",
            "is_posix": True
        }
        
    return {
        "os": sys_name,
        "family": sys_name,
        "distro_id": sys_name,
        "distro_name": platform.platform(),
        "version": platform.version(),
        "path_sep": os.sep,
        "uri_prefix": "file://",
        "is_posix": os.name == "posix"
    }

TARGET_OS_OPTIONS = [
    {
        "id": "linux_arch",
        "os": "linux",
        "family": "arch",
        "label": "Linux (Arch family: Arch, CachyOS, Omarchy, Manjaro, EndeavourOS)"
    },
    {
        "id": "linux_debian",
        "os": "linux",
        "family": "debian",
        "label": "Linux (Debian / Ubuntu family: Ubuntu, Debian, Pop!_OS, Mint)"
    },
    {
        "id": "linux_fedora",
        "os": "linux",
        "family": "fedora",
        "label": "Linux (Fedora / RHEL family: Fedora, CentOS, Rocky Linux)"
    },
    {
        "id": "linux_generic",
        "os": "linux",
        "family": "generic_linux",
        "label": "Linux (Other / Generic Distro)"
    },
    {
        "id": "windows",
        "os": "windows",
        "family": "windows",
        "label": "Windows (10 / 11 / Server)"
    }
]

def cross_reference_target(manifest_target: Dict[str, Any], current_target: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cross-references actual target OS with what was expected in the migration manifest.
    Returns status: 'match', 'compatible', or 'mismatch', with a clear explanation.
    """
    exp_os = manifest_target.get("os")
    cur_os = current_target.get("os")
    
    exp_family = manifest_target.get("family")
    cur_family = current_target.get("family")
    
    cur_name = current_target.get("distro_name", cur_os)
    
    if exp_os != cur_os:
        return {
            "status": "mismatch",
            "compatible": False,
            "message": f"Source expected target OS '{exp_os}', but running on '{cur_os}' ({cur_name}). Path rewrites may need manual review."
        }
        
    if exp_os == "linux":
        if exp_family == cur_family:
            return {
                "status": "match",
                "compatible": True,
                "message": f"Target matches intended distribution family '{exp_family.upper()}' (Detected: {cur_name})."
            }
        else:
            return {
                "status": "compatible",
                "compatible": True,
                "message": f"Target is Linux ({cur_name}), but family differs (Expected {exp_family}, got {cur_family}). Migration will proceed smoothly using standard POSIX paths."
            }
            
    return {
        "status": "match",
        "compatible": True,
        "message": f"Target OS matches '{cur_name}'."
    }
