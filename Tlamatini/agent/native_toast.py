"""Native Windows toast notifications for Tlamatini.

What this is
------------
Tlamatini's only notification surface used to be an *in-browser* DOM popup:
the Notifier agent wrote ``notification.json`` and the web frontend polled it.
That popup only exists while the Tlamatini tab is focused. This module adds a
**real Windows toast** — the OS banner that slides up from the bottom-right and
persists in the Action Center — so the user is notified even when the browser
is minimized or in the background (exactly like a Chrome/YouTube toast).

How it works (and the hard-won facts that shape it)
---------------------------------------------------
The toast is shown through the WinRT ``Windows.UI.Notifications`` API. We drive
it by shelling out to **Windows PowerShell 5.1** (``powershell.exe``), NOT
``pwsh`` (PowerShell 7+): PowerShell 7 cannot resolve the WinRT type
projections (``[Class, Assembly, ContentType=WindowsRuntime]`` fails), so a
toast script run under pwsh dies with "Unable to find type". This was proven
live on a dev box before this module was written — do NOT switch to pwsh.

For Windows to show the toast **with Tlamatini's name + icon and keep it in the
Action Center**, the toast's AppUserModelID (AUMID) must be *registered*. We
reuse the same AUMID ``manage.py`` already sets for taskbar identity
(``XAIHT.Tlamatini.Server``) and register a per-user identity under
``HKCU\\Software\\Classes\\AppUserModelId\\<AUMID>`` (DisplayName + IconUri).

ADMIN CONTRACT (do NOT break): everything here is **per-user, non-elevated**.
All registry writes go to **HKCU** (never HKLM/HKCR). A toast fired from an
*elevated* process is frequently suppressed by the notification platform, and
the AttachThreadInput focus dance fails across integrity levels — so running
non-admin is both the user's requirement and the only mode that works.

Click-to-focus (no new tab/window — a hard requirement)
-------------------------------------------------------
The toast carries ``activationType="protocol" launch="tlamatini:focus"``. We
register a per-user ``tlamatini:`` URL protocol whose handler is a tiny
PowerShell window-focus helper. It finds the *already-open* browser window
showing Tlamatini (page ``<title>`` is "Tlamatini") and brings it to the
foreground via the Win32 AttachThreadInput dance — it navigates **no** URL, so
it can never open a new browser/window/tab. (A plain ``http://127.0.0.1:8000/``
launch was rejected precisely because browsers often open a new tab.)

Safety contract (mirrors the orphan reaper / native_dialogs.py): every public
function is **fail-open** — it must never raise into the caller. A toast that
fails to show is a missed notification; a toast helper that crashes the Notifier
agent or Django startup is worse.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from typing import Optional
from xml.sax.saxutils import escape as _xml_text_escape

logger = logging.getLogger(__name__)

# The SAME AUMID manage.py sets for taskbar identity — reused so the toast,
# the taskbar, and "pin to taskbar" all share one Tlamatini identity.
AUMID = "XAIHT.Tlamatini.Server"
DISPLAY_NAME = "Tlamatini"

# Custom per-user URL protocol used for click-to-focus.
PROTOCOL = "tlamatini"
FOCUS_LAUNCH_ARG = "tlamatini:focus"

CREATE_NO_WINDOW = 0x08000000  # subprocess flag (Windows) — no console flash


def is_supported() -> bool:
    """True only on Windows (the WinRT toast API is Windows-only)."""
    return os.name == "nt"


# ---------------------------------------------------------------------------
# powershell.exe (v5.1) resolution — NEVER pwsh (it can't load WinRT types)
# ---------------------------------------------------------------------------

def resolve_powershell() -> Optional[str]:
    """Absolute path to Windows PowerShell 5.1, or None if unavailable.

    Deliberately resolves the in-box ``powershell.exe`` and NOT ``pwsh`` —
    PowerShell 7 cannot project the WinRT toast types.
    """
    if not is_supported():
        return None
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidate = os.path.join(windir, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if os.path.exists(candidate):
        return candidate
    # Fall back to PATH lookup (still resolves Windows PowerShell, not pwsh,
    # because we ask for "powershell" specifically).
    try:
        import shutil
        found = shutil.which("powershell")
        return found
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Icon resolution (PNG — .ico often renders blank as a toast appLogoOverride)
# ---------------------------------------------------------------------------

def resolve_toast_icon() -> Optional[str]:
    """Absolute path to the toast logo PNG, resolved for source AND frozen.

    Toast ``appLogoOverride`` officially supports PNG/JPG; ``.ico`` commonly
    renders blank, so we ship a PNG (``Tlamatini.png``). Returns None if the
    asset cannot be found (the toast still shows, just without a logo).
    """
    candidates = []
    if getattr(sys, "frozen", False):
        # Frozen: bundled next to the executable by build.py (optional_file_copies).
        candidates.append(os.path.join(os.path.dirname(sys.executable), "Tlamatini.png"))
    # Source mode: agent/static/agent/img/Tlamatini.png (this file is agent/native_toast.py).
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "static", "agent", "img", "Tlamatini.png"))
    candidates.append(os.path.join(here, "static", "agent", "img", "Tlamatini.ico"))  # last-resort
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


# ---------------------------------------------------------------------------
# Toast XML
# ---------------------------------------------------------------------------

def build_toast_xml(
    title: str,
    body: str,
    image_path: Optional[str] = None,
    sound: bool = True,
    launch_arg: Optional[str] = FOCUS_LAUNCH_ARG,
) -> str:
    """Build the ToastGeneric XML. All text is XML-escaped.

    ``launch_arg`` (when set) wires click-activation through the ``tlamatini:``
    protocol so a click focuses the existing browser tab.
    """
    safe_title = _xml_text_escape(title or DISPLAY_NAME)
    safe_body = _xml_text_escape(body or "")
    # Attribute value: escape quotes too. launch_arg is our own constant, but
    # escape defensively in case a caller passes something custom.
    activation_attrs = ""
    if launch_arg:
        safe_launch = _xml_text_escape(launch_arg, {'"': "&quot;"})
        activation_attrs = f' activationType="protocol" launch="{safe_launch}"'

    image_el = ""
    if image_path and os.path.exists(image_path):
        safe_img = _xml_text_escape(image_path, {'"': "&quot;"})
        image_el = f'<image placement="appLogoOverride" src="{safe_img}"/>'

    audio_el = (
        '<audio src="ms-winsoundevent:Notification.Default"/>'
        if sound
        else '<audio silent="true"/>'
    )

    return (
        f'<toast{activation_attrs}>'
        f'<visual><binding template="ToastGeneric">'
        f'{image_el}'
        f'<text>{safe_title}</text>'
        f'<text>{safe_body}</text>'
        f'</binding></visual>'
        f'{audio_el}'
        f'</toast>'
    )


def _build_toast_script(toast_xml: str, aumid: str = AUMID) -> str:
    """Wrap toast XML in a Windows PowerShell 5.1 script that shows it.

    The XML is embedded in a single-quoted here-string (``@'...'@``) so no
    PowerShell ``$``/backtick interpolation can corrupt it.
    """
    return (
        "$ErrorActionPreference = 'Stop'\n"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null\n"
        "[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null\n"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null\n"
        "$xml = @'\n"
        f"{toast_xml}\n"
        "'@\n"
        "$doc = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
        "$doc.LoadXml($xml)\n"
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $doc\n"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{aumid}').Show($toast)\n"
    )


# ---------------------------------------------------------------------------
# Show a toast (fail-open)
# ---------------------------------------------------------------------------

def show_toast(
    title: str,
    body: str,
    *,
    image_path: Optional[str] = None,
    sound: bool = True,
    clickable: bool = True,
    aumid: str = AUMID,
    timeout: float = 15.0,
) -> bool:
    """Show a Windows toast. Returns True on success, False otherwise.

    Never raises — a missed toast must never break the caller (Notifier agent
    or Django). On non-Windows hosts this is a silent no-op returning False.
    """
    if not is_supported():
        return False
    powershell = resolve_powershell()
    if not powershell:
        logger.info("[native_toast] Windows PowerShell 5.1 not found; skipping toast.")
        return False

    if image_path is None:
        image_path = resolve_toast_icon()

    toast_xml = build_toast_xml(
        title, body,
        image_path=image_path,
        sound=sound,
        launch_arg=FOCUS_LAUNCH_ARG if clickable else None,
    )
    script = _build_toast_script(toast_xml, aumid=aumid)

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".ps1", prefix="tlam_toast_")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(script)
        completed = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", tmp_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        if completed.returncode != 0:
            err = (completed.stderr or b"").decode("utf-8", "replace").strip()
            logger.warning("[native_toast] powershell exited %s: %s", completed.returncode, err[:500])
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("[native_toast] show_toast failed: %s", exc)
        return False
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Per-user identity + click-to-focus protocol registration (HKCU, no admin)
# ---------------------------------------------------------------------------

# PowerShell window-focus helper. Finds the already-open browser window showing
# Tlamatini and brings it to the foreground via the AttachThreadInput dance
# (ported from agent/agents/windower/windower.py::bring_to_front). Navigates no
# URL, so it can NEVER open a new tab/window. Prefers a browser process so it
# doesn't grab the Tlamatini *console* window (which manage.py titles
# "Tlamatini" too). ``$pid`` is a PowerShell automatic var — we use ``$wpid``.
FOCUS_HELPER_PS1 = r'''$ErrorActionPreference = 'SilentlyContinue'
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class TlamWin {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int pid);
}
"@
$found = New-Object System.Collections.ArrayList
$cb = [TlamWin+EnumProc]{
  param($h, $l)
  if ([TlamWin]::IsWindowVisible($h)) {
    $len = [TlamWin]::GetWindowTextLength($h)
    if ($len -gt 0) {
      $sb = New-Object System.Text.StringBuilder ($len + 1)
      [TlamWin]::GetWindowText($h, $sb, $sb.Capacity) | Out-Null
      $t = $sb.ToString()
      if ($t -match 'Tlamatini') {
        $wpid = 0
        [TlamWin]::GetWindowThreadProcessId($h, [ref]$wpid) | Out-Null
        $pname = ''
        try { $pname = (Get-Process -Id $wpid -ErrorAction Stop).ProcessName.ToLower() } catch {}
        [void]$found.Add([pscustomobject]@{ H = $h; PName = $pname })
      }
    }
  }
  return $true
}
[TlamWin]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null

$browsers = @('chrome','msedge','firefox','brave','opera','vivaldi','iexplore','arc','chromium','chrome_proxy')
$shells = @('python','pythonw','conhost','cmd','powershell','pwsh','windowsterminal','tlamatini','openconsole','explorer')
$target = $found | Where-Object { $browsers -contains $_.PName } | Select-Object -First 1
if (-not $target) { $target = $found | Where-Object { $shells -notcontains $_.PName } | Select-Object -First 1 }
if (-not $target) { $target = $found | Select-Object -First 1 }
if ($target) {
  $h = $target.H
  if ([TlamWin]::IsIconic($h)) { [TlamWin]::ShowWindow($h, 9) | Out-Null }  # SW_RESTORE
  $fg = [TlamWin]::GetForegroundWindow()
  $cur = [TlamWin]::GetCurrentThreadId()
  $fgt = 0; $tgt = 0
  [TlamWin]::GetWindowThreadProcessId($fg, [ref]$fgt) | Out-Null
  [TlamWin]::GetWindowThreadProcessId($h, [ref]$tgt) | Out-Null
  [TlamWin]::AllowSetForegroundWindow(-1) | Out-Null
  $att = @()
  foreach ($th in @($fgt, $tgt)) { if ($th -ne 0 -and $th -ne $cur) { if ([TlamWin]::AttachThreadInput($cur, $th, $true)) { $att += $th } } }
  [TlamWin]::SetForegroundWindow($h) | Out-Null
  [TlamWin]::BringWindowToTop($h) | Out-Null
  foreach ($th in $att) { [TlamWin]::AttachThreadInput($cur, $th, $false) | Out-Null }
}
'''


def _focus_helper_dir() -> str:
    """Per-user dir for the generated focus helper (no admin needed)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Tlamatini")


def register_toast_identity(icon_path: Optional[str] = None) -> bool:
    """Register the per-user AUMID identity so toasts show "Tlamatini" + icon
    and persist in the Action Center. HKCU only — never needs admin. Idempotent
    and fail-open. Returns True on success."""
    if not is_supported():
        return False
    try:
        import winreg
        if icon_path is None:
            icon_path = resolve_toast_icon()
        key_path = rf"Software\Classes\AppUserModelId\{AUMID}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, DISPLAY_NAME)
            if icon_path:
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon_path)
                # IconBackgroundColor improves contrast on some themes.
                winreg.SetValueEx(key, "IconBackgroundColor", 0, winreg.REG_SZ, "FF2D2D30")
        return True
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("[native_toast] register_toast_identity failed: %s", exc)
        return False


def register_focus_protocol() -> bool:
    """Write the focus-helper script and register the per-user ``tlamatini:``
    URL protocol that runs it on toast click. HKCU only — never needs admin.
    Idempotent (rewrites the script each call so updates land) and fail-open."""
    if not is_supported():
        return False
    powershell = resolve_powershell()
    if not powershell:
        return False
    try:
        import winreg
        helper_dir = _focus_helper_dir()
        os.makedirs(helper_dir, exist_ok=True)
        helper_path = os.path.join(helper_dir, "focus_window.ps1")
        with open(helper_path, "w", encoding="utf-8") as fh:
            fh.write(FOCUS_HELPER_PS1)

        command = (
            f'"{powershell}" -NoProfile -NonInteractive -WindowStyle Hidden '
            f'-ExecutionPolicy Bypass -File "{helper_path}" "%1"'
        )
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROTOCOL}") as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "URL:Tlamatini Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROTOCOL}\shell\open\command"
        ) as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, command)
        return True
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("[native_toast] register_focus_protocol failed: %s", exc)
        return False


def register_all() -> None:
    """Register identity + focus protocol. Best-effort; called once at Django
    startup. Both pieces are independent and fail-open."""
    register_toast_identity()
    register_focus_protocol()
