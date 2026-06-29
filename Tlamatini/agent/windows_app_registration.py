# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Register Tlamatini in Windows "Installed apps" / "Programs and Features".

Why this exists
---------------
Tlamatini installs **per-user, non-elevated** (the installer ships an
``asInvoker`` manifest and writes only HKCU). A per-user install that wants to
appear in Settings ▸ Apps ▸ *Installed apps* (and the legacy *Programs and
Features* list) must write an **Add/Remove Programs (ARP)** entry under::

    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\<AppKey>

Before this module, Tlamatini created Desktop/Start-Menu shortcuts and a
``.flw`` file association but **no ARP entry**, so it never showed up in the
Windows "uninstall a program" UI even though ``Uninstaller.exe`` shipped next
to the executable.

Two write paths use these helpers:
  * ``install.py``   — writes the entry at install time (authoritative paths).
  * ``apps.AgentConfig.ready()`` — **self-heals** the entry on every frozen
    launch, so installs made before this change retroactively appear in the
    list. Source-mode launches no-op (there is no ``Uninstaller.exe`` next to a
    ``python.exe``).

ADMIN / SAFETY CONTRACT (do NOT break): HKCU only (never HKLM), no admin, and
every public function is **fail-open** — a registry hiccup must never crash
Django startup or the installer.
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

# The registry sub-key name under ...\\CurrentVersion\\Uninstall\\.
ARP_KEY_NAME = "Tlamatini"
ARP_UNINSTALL_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
DISPLAY_NAME = "Tlamatini"
PUBLISHER = "XAIHT"
ABOUT_URL = "https://github.com/XAIHT/Tlamatini"


def is_supported() -> bool:
    """True only on Windows (the ARP registry surface is Windows-only)."""
    return os.name == "nt"


def _dir_size_kb(path: str, *, cap_files: int = 60000) -> int:
    """Best-effort total size of *path* in KB (for ``EstimatedSize``).

    Capped at ``cap_files`` entries so a huge tree can't stall startup; returns
    0 on any error (the field is optional and Windows tolerates its absence).
    """
    total = 0
    seen = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                seen += 1
                if seen > cap_files:
                    raise StopIteration
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except StopIteration:
        pass
    except Exception:  # noqa: BLE001 — fail-open
        return 0
    return total // 1024


def register_uninstall_entry(
    install_dir: str,
    *,
    version: str = "",
    uninstaller_name: str = "Uninstaller.exe",
    compute_size: bool = True,
) -> bool:
    """Write the per-user ARP entry so Tlamatini shows in "Installed apps".

    ``install_dir`` is the folder containing ``Tlamatini.exe`` /
    ``Tlamatini.ico`` / ``Uninstaller.exe``. The entry is written only when an
    ``Uninstaller.exe`` is actually present there (so Windows' Uninstall button
    has something to launch); otherwise this is a no-op returning False.

    Idempotent (re-writes the same values) and fail-open. HKCU, no admin.
    """
    if not is_supported():
        return False
    try:
        import winreg

        install_dir = os.path.abspath(install_dir)
        uninstaller = os.path.join(install_dir, uninstaller_name)
        if not os.path.isfile(uninstaller):
            # No uninstaller to point at — don't advertise an uninstall entry
            # whose button would do nothing.
            return False

        icon = os.path.join(install_dir, "Tlamatini.ico")
        exe = os.path.join(install_dir, "Tlamatini.exe")
        display_icon = icon if os.path.isfile(icon) else (
            f"{exe},0" if os.path.isfile(exe) else uninstaller
        )
        quoted_uninstaller = f'"{uninstaller}"'

        key_path = rf"{ARP_UNINSTALL_ROOT}\{ARP_KEY_NAME}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, DISPLAY_NAME)
            if version:
                winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, display_icon)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, quoted_uninstaller)
            winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, quoted_uninstaller)
            winreg.SetValueEx(key, "URLInfoAbout", 0, winreg.REG_SZ, ABOUT_URL)
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
            # EstimatedSize (KB) — only (re)compute when asked and not already
            # present, so the per-launch self-heal stays cheap.
            if compute_size and not _has_value(key, "EstimatedSize"):
                size_kb = _dir_size_kb(install_dir)
                if size_kb > 0:
                    winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        return True
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("[app_registration] register_uninstall_entry failed: %s", exc)
        return False


def _has_value(key, name: str) -> bool:
    """True if an open registry *key* already has a value named *name*."""
    try:
        import winreg
        winreg.QueryValueEx(key, name)
        return True
    except OSError:
        return False


def unregister_uninstall_entry() -> bool:
    """Delete the per-user ARP entry. Idempotent and fail-open. HKCU, no admin."""
    if not is_supported():
        return False
    try:
        import winreg
        key_path = rf"{ARP_UNINSTALL_ROOT}\{ARP_KEY_NAME}"
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        except FileNotFoundError:
            return True  # already gone — success
        return True
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("[app_registration] unregister_uninstall_entry failed: %s", exc)
        return False


def self_heal_for_frozen(version: str = "") -> bool:
    """Refresh the ARP entry for a frozen install on app startup.

    No-ops unless running frozen (``sys.frozen``) with an ``Uninstaller.exe``
    sitting next to the executable — i.e. a real install, not source mode.
    Lets installs made before this feature appear in "Installed apps" on the
    next launch. Fail-open.
    """
    if not is_supported() or not getattr(sys, "frozen", False):
        return False
    try:
        install_dir = os.path.dirname(sys.executable)
        if not os.path.isfile(os.path.join(install_dir, "Uninstaller.exe")):
            return False
        return register_uninstall_entry(install_dir, version=version)
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("[app_registration] self_heal_for_frozen failed: %s", exc)
        return False
