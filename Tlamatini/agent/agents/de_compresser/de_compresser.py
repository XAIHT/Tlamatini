# De-Compresser Agent - Deterministic compression / decompression
#
# DECOMPRESS: input=<archive .gz|.7z|.zip|.tar.gz|.gz.tar>, output=<dir>
# COMPRESS:   input=<file or directory>,                    output=<archive .gz|.7z|.zip|.tar.gz>
#
# Password handling:
#   passwordless=true  -> no password
#   passwordless=false -> read password from environment variable DE_COMPRESSER_PWD
#                         (fail fast to end-stage if the env var is undefined)

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import gzip
import shutil
import tarfile
import tempfile
import time
import yaml
import zipfile
import logging
import subprocess
from typing import Dict, List, Optional, Tuple

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)


# ---------------------------------------------------------------------------
# Standard pool helpers (copied verbatim from shoter.py — DO NOT MODIFY)
# ---------------------------------------------------------------------------

def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logging.error(f"❌ Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"❌ Error parsing {path}: {e}")
        sys.exit(1)


def get_python_command() -> list:
    if not getattr(sys, 'frozen', False):
        return [sys.executable]

    python_home = get_user_python_home()
    if python_home:
        python_exe = os.path.join(python_home, 'python.exe' if sys.platform.startswith('win') else 'python3')
        if os.path.exists(python_exe):
            return [python_exe]

    if sys.platform.startswith('win'):
        bundled_python = os.path.join(os.path.dirname(sys.executable), 'python.exe')
        if os.path.exists(bundled_python):
            return [bundled_python]
        return ['python']

    return ['python3']


def get_user_python_home() -> str:
    """Read PYTHON_HOME exclusively from USER environment variables (Windows registry)."""
    if not sys.platform.startswith('win'):
        return os.environ.get('PYTHON_HOME', '')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment') as key:
            value, _ = winreg.QueryValueEx(key, 'PYTHON_HOME')
            return str(value) if value else ''
    except (FileNotFoundError, OSError):
        return ''


def get_agent_env() -> dict:
    """Build environment for child processes with PYTHON_HOME from USER env vars on PATH."""
    env = os.environ.copy()

    if sys.platform.startswith('win'):
        try:
            import ctypes
            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        meipass = getattr(sys, '_MEIPASS')
        if meipass:
            path_parts = env.get('PATH', '').split(os.pathsep)
            path_parts = [p for p in path_parts if os.path.normpath(p) != os.path.normpath(meipass)]
            env['PATH'] = os.pathsep.join(path_parts)

    python_home = get_user_python_home()
    if not python_home:
        return env

    env['PYTHON_HOME'] = python_home
    scripts_dir = os.path.join(python_home, 'Scripts')
    current_path = env.get('PATH', '')
    env['PATH'] = f"{python_home};{scripts_dir};{current_path}"
    return env


def get_pool_path() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)

    if os.path.basename(grandparent) == 'pools':
        return parent
    if os.path.basename(parent) == 'pools':
        return parent

    return os.path.join(os.path.dirname(current_dir), 'pools')


def get_agent_directory(agent_name: str) -> str:
    return os.path.join(get_pool_path(), agent_name)


def get_agent_script_path(agent_name: str) -> str:
    agent_dir = get_agent_directory(agent_name)
    if os.path.exists(os.path.join(agent_dir, f"{agent_name}.py")):
        return os.path.join(agent_dir, f"{agent_name}.py")

    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        base = parts[0]
        if os.path.exists(os.path.join(agent_dir, f"{base}.py")):
            return os.path.join(agent_dir, f"{base}.py")

    return os.path.join(agent_dir, f"{agent_name}.py")


def is_agent_running(agent_name: str) -> bool:
    agent_dir = get_agent_directory(agent_name)
    pid_path = os.path.join(agent_dir, "agent.pid")

    if not os.path.exists(pid_path):
        return False

    try:
        with open(pid_path, "r") as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        return False

    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
        return True
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def wait_for_agents_to_stop(agent_names: list):
    if not agent_names:
        return

    waited = 0.0
    poll_interval = 0.5

    while True:
        still_running = [name for name in agent_names if is_agent_running(name)]
        if not still_running:
            return

        if waited >= 10.0:
            logging.error(
                f"❌ WAITING FOR AGENTS TO STOP: {still_running} still running "
                f"after {int(waited)}s. Will keep waiting..."
            )
            waited = 0.0

        time.sleep(poll_interval)
        waited += poll_interval


def start_agent(agent_name: str) -> bool:
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)

    if not os.path.exists(script_path):
        logging.error(f"❌ Agent script not found: {script_path}")
        return False

    try:
        cmd = get_python_command() + [script_path]
        logging.info(f"   Command: {cmd}")

        process = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            env=get_agent_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )

        try:
            pid_path = os.path.join(agent_dir, "agent.pid")
            with open(pid_path, "w") as f:
                f.write(str(process.pid))
        except Exception as pid_err:
            logging.error(f"⚠️ Failed to write PID file for target {agent_name}: {pid_err}")

        logging.info(f"✅ Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to start agent '{agent_name}': {e}")
        return False


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")


def remove_pid_file():
    for _ in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"❌ Failed to remove PID file: {e}")
            return


# ---------------------------------------------------------------------------
# DE-COMPRESSER CORE
# ---------------------------------------------------------------------------

SUPPORTED_DECOMPRESS_EXTS = ('.gz.tar', '.tar.gz', '.gz', '.7z', '.zip')
SUPPORTED_COMPRESS_EXTS = ('.gz.tar', '.tar.gz', '.gz', '.7z', '.zip')
PWD_ENV_VAR = 'DE_COMPRESSER_PWD'


def detect_extension(path: str) -> str:
    """Return the longest recognized extension for `path`.

    The order in SUPPORTED_DECOMPRESS_EXTS deliberately puts compound
    extensions (.gz.tar / .tar.gz) before the single .gz suffix so that
    'archive.tar.gz' resolves to '.tar.gz' and not '.gz'.
    """
    lower = path.lower()
    for ext in SUPPORTED_DECOMPRESS_EXTS:
        if lower.endswith(ext):
            return ext
    return ''


def resolve_password(passwordless: bool) -> Tuple[Optional[str], Optional[str]]:
    """Return (password, error_message).

    - If passwordless is True the password is None and there is no error.
    - If passwordless is False the password is read from DE_COMPRESSER_PWD.
      A missing env var produces (None, error_message).
    """
    if passwordless:
        return None, None
    password = os.environ.get(PWD_ENV_VAR)
    if not password:
        return None, (
            f"Environment variable '{PWD_ENV_VAR}' is not defined; cannot "
            f"obtain password (passwordless=false)."
        )
    return password, None


def ensure_writable_directory(path: str) -> Optional[str]:
    """Validate that `path` is a directory that exists and is writable."""
    if not path:
        return "'output' is empty; expected a directory path."
    if os.path.exists(path):
        if not os.path.isdir(path):
            return f"'output' exists but is not a directory: {path}"
    else:
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as exc:
            return f"Failed to create output directory '{path}': {exc}"
    if not os.access(path, os.W_OK):
        return f"No write permission on output directory: {path}"
    return None


def ensure_input_exists(path: str) -> Optional[str]:
    if not path:
        return "'input' is empty; expected a file or directory path."
    if not os.path.exists(path):
        return f"'input' does not exist: {path}"
    return None


# ---------- Decompression primitives ------------------------------------------------

def decompress_gz(src_file: str, dest_dir: str, password: Optional[str]) -> str:
    """Decompress a single .gz file into dest_dir. .gz has no native password.

    If a password is supplied (passwordless=false) we honor it by treating
    the .gz file as PASSWORD-WRAPPED: the agent expects the .gz body to be
    a gzip stream itself. Standard GNU Zip has no native encryption layer,
    so when a password is supplied we route through 7-Zip's `7z` CLI when
    available (it can handle gzip + password-wrapped archives). When 7z is
    not on PATH we fall back to the standard gzip module and log a warning
    so the operator knows the password was ignored.
    """
    base = os.path.basename(src_file)
    if base.lower().endswith('.gz'):
        target_name = base[:-3]
    else:
        target_name = base + '.out'
    dest_path = os.path.join(dest_dir, target_name)

    if password:
        if _seven_zip_available():
            _seven_zip_extract(src_file, dest_dir, password)
            return dest_path
        logging.warning(
            "⚠️ Password supplied for .gz but the GNU Zip format has no native "
            "encryption and the 7z CLI is unavailable; decompressing without a "
            "password using the gzip module."
        )

    with gzip.open(src_file, 'rb') as src, open(dest_path, 'wb') as dst:
        shutil.copyfileobj(src, dst)
    return dest_path


def decompress_zip(src_file: str, dest_dir: str, password: Optional[str]) -> List[str]:
    """Universal ZIP decompression using the stdlib zipfile module."""
    extracted: List[str] = []
    pwd_bytes = password.encode('utf-8') if password else None
    with zipfile.ZipFile(src_file, 'r') as zf:
        for info in zf.infolist():
            target = zf.extract(info, path=dest_dir, pwd=pwd_bytes)
            extracted.append(target)
    return extracted


def decompress_seven_zip(src_file: str, dest_dir: str, password: Optional[str]) -> List[str]:
    """Decompress .7z using the 7z CLI (preferred) or py7zr (fallback)."""
    if _seven_zip_available():
        _seven_zip_extract(src_file, dest_dir, password)
        # Best-effort listing of what was emitted into dest_dir
        return [os.path.join(dest_dir, name) for name in os.listdir(dest_dir)]

    try:
        import py7zr  # type: ignore
    except ImportError:
        raise RuntimeError(
            "Neither the 7z CLI nor the 'py7zr' Python module is available; "
            "cannot decompress .7z archives."
        )
    with py7zr.SevenZipFile(src_file, mode='r', password=password) as archive:
        archive.extractall(path=dest_dir)
        return [os.path.join(dest_dir, n) for n in archive.getnames()]


def decompress_tar_gz(src_file: str, dest_dir: str, password: Optional[str]) -> List[str]:
    """For .tar.gz / .gz.tar: first decompress the gz stream into a temp .tar,
    then untar into dest_dir. tar itself has no native password layer; a
    supplied password is honored by routing through 7z when available.
    """
    if password and _seven_zip_available():
        _seven_zip_extract(src_file, dest_dir, password)
        return [os.path.join(dest_dir, name) for name in os.listdir(dest_dir)]

    with tempfile.NamedTemporaryFile(suffix='.tar', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with gzip.open(src_file, 'rb') as src, open(tmp_path, 'wb') as dst:
            shutil.copyfileobj(src, dst)

        extracted: List[str] = []
        with tarfile.open(tmp_path, 'r:') as tar:
            tar.extractall(path=dest_dir)
            extracted = [os.path.join(dest_dir, m.name) for m in tar.getmembers()]
        return extracted
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _seven_zip_available() -> bool:
    return shutil.which('7z') is not None or shutil.which('7z.exe') is not None


def _seven_zip_extract(src_file: str, dest_dir: str, password: Optional[str]) -> None:
    cmd = ['7z', 'x', src_file, f'-o{dest_dir}', '-y']
    if password:
        cmd.append(f'-p{password}')
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr or result.stdout
        raise RuntimeError(f"7z extraction failed: {err.strip()}")


def _seven_zip_create(src_path: str, dest_file: str, password: Optional[str], archive_type: str) -> None:
    """Use the 7z CLI to CREATE an archive. archive_type ∈ {7z, zip, gzip, tar}."""
    cmd = ['7z', 'a', f'-t{archive_type}', dest_file, src_path, '-y']
    if password:
        cmd.append(f'-p{password}')
        if archive_type in ('7z', 'zip'):
            cmd.append('-mhe=on')
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr or result.stdout
        raise RuntimeError(f"7z archive creation failed: {err.strip()}")


# ---------- Compression primitives --------------------------------------------------

def compress_gz(src_path: str, dest_file: str, password: Optional[str]) -> None:
    """Compress a single FILE into a gzip stream. .gz has no native password.

    If a password is provided we route through 7z when available; otherwise
    we use the stdlib gzip module and log that the password was ignored.
    """
    if not os.path.isfile(src_path):
        raise RuntimeError(f".gz output requires `input` to be a FILE (got: {src_path})")

    if password:
        if _seven_zip_available():
            _seven_zip_create(src_path, dest_file, password, 'gzip')
            return
        logging.warning(
            "⚠️ Password supplied for .gz output but GNU Zip has no native "
            "encryption and the 7z CLI is unavailable; compressing without "
            "a password using the gzip module."
        )

    with open(src_path, 'rb') as src, gzip.open(dest_file, 'wb') as dst:
        shutil.copyfileobj(src, dst)


def compress_zip(src_path: str, dest_file: str, password: Optional[str]) -> None:
    """Universal ZIP creation. Password-protected ZIP is delegated to 7z so
    we get AES-encrypted entries; without 7z we fall back to a plain
    (unencrypted) ZIP via the stdlib zipfile module.
    """
    if password and _seven_zip_available():
        _seven_zip_create(src_path, dest_file, password, 'zip')
        return

    if password:
        logging.warning(
            "⚠️ Password supplied for .zip output but the 7z CLI is unavailable; "
            "the stdlib zipfile module cannot write encrypted entries. Creating "
            "an UNENCRYPTED zip."
        )

    with zipfile.ZipFile(dest_file, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        if os.path.isfile(src_path):
            zf.write(src_path, arcname=os.path.basename(src_path))
        else:
            base = os.path.basename(os.path.normpath(src_path))
            for root, _dirs, files in os.walk(src_path):
                for name in files:
                    abs_path = os.path.join(root, name)
                    rel_path = os.path.relpath(abs_path, src_path)
                    zf.write(abs_path, arcname=os.path.join(base, rel_path))


def compress_seven_zip(src_path: str, dest_file: str, password: Optional[str]) -> None:
    """Create a .7z archive. Prefer the 7z CLI; fall back to py7zr."""
    if _seven_zip_available():
        _seven_zip_create(src_path, dest_file, password, '7z')
        return

    try:
        import py7zr  # type: ignore
    except ImportError:
        raise RuntimeError(
            "Neither the 7z CLI nor the 'py7zr' Python module is available; "
            "cannot create .7z archives."
        )
    with py7zr.SevenZipFile(dest_file, mode='w', password=password) as archive:
        if os.path.isfile(src_path):
            archive.write(src_path, arcname=os.path.basename(src_path))
        else:
            archive.writeall(src_path, arcname=os.path.basename(os.path.normpath(src_path)))


def compress_tar_gz(src_path: str, dest_file: str, password: Optional[str]) -> None:
    """Create a .tar.gz (or .gz.tar) archive. Password handling via 7z when
    available; otherwise an unencrypted .tar.gz via the stdlib tarfile.
    """
    if password and _seven_zip_available():
        # 7z does not write .tar.gz in a single shot — we build the .tar
        # first and let 7z gzip it with the password.
        with tempfile.NamedTemporaryFile(suffix='.tar', delete=False) as tmp:
            tmp_tar = tmp.name
        try:
            with tarfile.open(tmp_tar, 'w:') as tar:
                arcname = os.path.basename(os.path.normpath(src_path))
                tar.add(src_path, arcname=arcname)
            _seven_zip_create(tmp_tar, dest_file, password, 'gzip')
        finally:
            try:
                os.remove(tmp_tar)
            except OSError:
                pass
        return

    if password:
        logging.warning(
            "⚠️ Password supplied for .tar.gz output but the 7z CLI is "
            "unavailable; tar/gz has no native encryption layer in the "
            "stdlib. Creating an UNENCRYPTED .tar.gz."
        )

    with tarfile.open(dest_file, 'w:gz') as tar:
        arcname = os.path.basename(os.path.normpath(src_path))
        tar.add(src_path, arcname=arcname)


# ---------- Stage dispatcher --------------------------------------------------------

def run_decompression(input_path: str, output_dir: str, ext: str, password: Optional[str]) -> Tuple[bool, str]:
    try:
        if ext == '.gz':
            dest_path = decompress_gz(input_path, output_dir, password)
            return True, f"Decompressed (.gz) to {dest_path}"
        if ext == '.7z':
            files = decompress_seven_zip(input_path, output_dir, password)
            return True, f"Decompressed (.7z) {len(files)} entries to {output_dir}"
        if ext == '.zip':
            files = decompress_zip(input_path, output_dir, password)
            return True, f"Decompressed (.zip) {len(files)} entries to {output_dir}"
        if ext in ('.tar.gz', '.gz.tar'):
            files = decompress_tar_gz(input_path, output_dir, password)
            return True, f"Decompressed ({ext}) {len(files)} entries to {output_dir}"
    except Exception as exc:
        return False, f"Decompression failure ({ext}): {exc}"
    return False, f"Unsupported decompression extension: {ext}"


def run_compression(input_path: str, output_file: str, ext: str, password: Optional[str]) -> Tuple[bool, str]:
    try:
        if ext == '.gz':
            compress_gz(input_path, output_file, password)
            return True, f"Compressed (.gz) to {output_file}"
        if ext == '.7z':
            compress_seven_zip(input_path, output_file, password)
            return True, f"Compressed (.7z) to {output_file}"
        if ext == '.zip':
            compress_zip(input_path, output_file, password)
            return True, f"Compressed (.zip) to {output_file}"
        if ext in ('.tar.gz', '.gz.tar'):
            compress_tar_gz(input_path, output_file, password)
            return True, f"Compressed ({ext}) to {output_file}"
    except Exception as exc:
        return False, f"Compression failure ({ext}): {exc}"
    return False, f"Unsupported compression extension: {ext}"


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        input_path = str(config.get('input') or '').strip()
        output_path = str(config.get('output') or '').strip()
        passwordless = bool(config.get('passwordless', True))
        target_agents = config.get('target_agents', []) or []

        logging.info("📦 DE-COMPRESSER AGENT STARTED")
        logging.info(f"📥 Input:        {input_path or '<empty>'}")
        logging.info(f"📤 Output:       {output_path or '<empty>'}")
        logging.info(f"🔑 Passwordless: {passwordless}")
        logging.info(f"🎯 Targets:      {target_agents}")

        operation = ''
        ext = ''
        success = False
        message = ''

        # ── Stage A: classify input + extension ─────────────────────────────
        input_err = ensure_input_exists(input_path)
        if input_err:
            logging.error(f"❌ {input_err}")
        else:
            input_ext = detect_extension(input_path)
            output_ext = detect_extension(output_path)

            if os.path.isfile(input_path) and input_ext in SUPPORTED_DECOMPRESS_EXTS:
                operation = 'decompress'
                ext = input_ext
            elif output_ext in SUPPORTED_COMPRESS_EXTS:
                operation = 'compress'
                ext = output_ext
            else:
                logging.error(
                    "❌ Cannot determine operation: input extension "
                    f"'{input_ext or '<none>'}' is not a recognized archive type "
                    f"and output extension '{output_ext or '<none>'}' is not "
                    "either. Supported: .gz, .7z, .zip, .tar.gz, .gz.tar."
                )

            if operation:
                # ── Stage B: password resolution ────────────────────────────
                password, pw_err = resolve_password(passwordless)
                if pw_err:
                    logging.error(f"❌ {pw_err}")
                else:
                    # ── Stage C: output validation ──────────────────────────
                    if operation == 'decompress':
                        output_err = ensure_writable_directory(output_path)
                        if output_err:
                            logging.error(f"❌ {output_err}")
                        else:
                            logging.info(
                                f"➡️  Decompressing '{input_path}' ({ext}) into "
                                f"'{output_path}'..."
                            )
                            success, message = run_decompression(
                                input_path, output_path, ext, password
                            )
                    else:  # compress
                        # The output is a FILE; the PARENT directory must be writable.
                        parent_dir = os.path.dirname(os.path.abspath(output_path))
                        output_err = ensure_writable_directory(parent_dir)
                        if output_err:
                            logging.error(f"❌ {output_err}")
                        else:
                            logging.info(
                                f"➡️  Compressing '{input_path}' into "
                                f"'{output_path}' ({ext})..."
                            )
                            success, message = run_compression(
                                input_path, output_path, ext, password
                            )

                    if success:
                        logging.info(f"✅ {message}")
                    else:
                        logging.error(f"❌ {message}")

        # Emit one Parametrizer-compatible block so downstream agents and the
        # Multi-Turn LLM can consume the outcome verbatim. Single atomic
        # logging.info() call — never split.
        logging.info(
            "INI_SECTION_DE_COMPRESSER<<<\n"
            f"operation: {operation or 'none'}\n"
            f"extension: {ext or 'none'}\n"
            f"input: {input_path}\n"
            f"output: {output_path}\n"
            f"passwordless: {str(passwordless).lower()}\n"
            f"success: {str(success).lower()}\n\n"
            f"{message or 'No operation performed.'}\n"
            ">>>END_SECTION_DE_COMPRESSER"
        )

        # ── End stage: always trigger target_agents ─────────────────────────
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 De-Compresser agent finished. Triggered "
            f"{total_triggered}/{len(target_agents)} agents."
        )

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
