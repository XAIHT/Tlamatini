# Kyber-KeyGen Agent - Generates CRYSTALS-Kyber public/private key pairs

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import base64
import hashlib
import secrets
import time
import yaml
import logging
import subprocess

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


def load_config(path="config.yaml"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error parsing {path}: {e}")
        sys.exit(1)


def get_python_command():
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


def get_user_python_home():
    if not sys.platform.startswith('win'):
        return os.environ.get('PYTHON_HOME', '')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment') as key:
            value, _ = winreg.QueryValueEx(key, 'PYTHON_HOME')
            return str(value) if value else ''
    except (FileNotFoundError, OSError):
        return ''


def get_agent_env():
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


def get_pool_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)
    if os.path.basename(grandparent) == 'pools':
        return parent
    if os.path.basename(parent) == 'pools':
        return parent
    return os.path.join(os.path.dirname(current_dir), 'pools')


def get_agent_directory(agent_name):
    return os.path.join(get_pool_path(), agent_name)


def get_agent_script_path(agent_name):
    agent_dir = get_agent_directory(agent_name)
    if os.path.exists(os.path.join(agent_dir, f"{agent_name}.py")):
        return os.path.join(agent_dir, f"{agent_name}.py")
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        base = parts[0]
        if os.path.exists(os.path.join(agent_dir, f"{base}.py")):
            return os.path.join(agent_dir, f"{base}.py")
    return os.path.join(agent_dir, f"{agent_name}.py")


def is_agent_running(agent_name):
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


def wait_for_agents_to_stop(agent_names):
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
                f"WAITING FOR AGENTS TO STOP: {still_running} still running "
                f"after {int(waited)}s. Will keep waiting..."
            )
            waited = 0.0
        time.sleep(poll_interval)
        waited += poll_interval


def start_agent(agent_name):
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)
    if not os.path.exists(script_path):
        logging.error(f"Agent script not found: {script_path}")
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
            logging.error(f"Failed to write PID file for target {agent_name}: {pid_err}")
        logging.info(f"Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"Failed to start agent '{agent_name}': {e}")
        return False


# --- CRYSTALS-Kyber Key Generation ---

# Kyber parameters per variant
KYBER_PARAMS = {
    'kyber-512': {'k': 2, 'n': 256, 'q': 3329, 'eta1': 3, 'eta2': 2},
    'kyber-768': {'k': 3, 'n': 256, 'q': 3329, 'eta1': 2, 'eta2': 2},
    'kyber-1024': {'k': 4, 'n': 256, 'q': 3329, 'eta1': 2, 'eta2': 2},
}


def _cbd(eta, noise_bytes):
    """Centered binomial distribution sampling for Kyber.
    Consumes exactly 2*eta bits per coefficient (512*eta bits total = 64*eta bytes)."""
    coeffs = []
    bit_idx = 0
    for _ in range(256):
        a_sum = 0
        for _ in range(eta):
            byte_pos = bit_idx // 8
            bit_pos = bit_idx % 8
            if byte_pos < len(noise_bytes):
                a_sum += (noise_bytes[byte_pos] >> bit_pos) & 1
            bit_idx += 1
        b_sum = 0
        for _ in range(eta):
            byte_pos = bit_idx // 8
            bit_pos = bit_idx % 8
            if byte_pos < len(noise_bytes):
                b_sum += (noise_bytes[byte_pos] >> bit_pos) & 1
            bit_idx += 1
        coeffs.append((a_sum - b_sum) % 3329)
    return coeffs


def _ntt_multiply_poly(a, b, q=3329):
    """Simple polynomial multiplication mod x^256 + 1 mod q."""
    n = 256
    c = [0] * n
    for i in range(n):
        for j in range(n):
            idx = i + j
            if idx < n:
                c[idx] = (c[idx] + a[i] * b[j]) % q
            else:
                c[idx - n] = (c[idx - n] - a[i] * b[j]) % q
    return c


def _poly_add(a, b, q=3329):
    """Add two polynomials mod q."""
    return [(a[i] + b[i]) % q for i in range(256)]


def _encode_poly(poly, bits=12):
    """Encode polynomial coefficients to bytes."""
    result = bytearray()
    if bits == 12:
        for i in range(0, 256, 2):
            c0 = poly[i] % 3329
            c1 = poly[i + 1] % 3329
            result.append(c0 & 0xFF)
            result.append(((c0 >> 8) & 0x0F) | ((c1 & 0x0F) << 4))
            result.append((c1 >> 4) & 0xFF)
    return bytes(result)


def generate_kyber_keypair(variant='kyber-768'):
    """Generate a CRYSTALS-Kyber key pair."""
    params = KYBER_PARAMS[variant]
    k = params['k']
    q = params['q']
    eta1 = params['eta1']

    # Generate random seed
    d = secrets.token_bytes(32)
    seed_hash = hashlib.sha3_512(d).digest()
    rho = seed_hash[:32]  # public seed
    sigma = seed_hash[32:]  # secret seed

    # Generate matrix A from rho (simplified: use SHAKE-128 expansion)
    a_matrix = []
    for i in range(k):
        row = []
        for j in range(k):
            seed = rho + bytes([j, i])
            expanded = hashlib.shake_128(seed).digest(768)
            poly = []
            idx = 0
            while len(poly) < 256 and idx + 1 < len(expanded):
                d1 = expanded[idx] + 256 * (expanded[idx + 1] % 16)
                d2 = (expanded[idx + 1] // 16) + 16 * expanded[min(idx + 2, len(expanded) - 1)]
                if d1 < q:
                    poly.append(d1)
                if d2 < q and len(poly) < 256:
                    poly.append(d2)
                idx += 3
            poly = poly[:256] + [0] * max(0, 256 - len(poly))
            row.append(poly)
        a_matrix.append(row)

    # Generate secret vector s
    s_vec = []
    for i in range(k):
        noise_seed = sigma + bytes([i])
        noise_bytes = hashlib.shake_256(noise_seed).digest(eta1 * 64 + 32)
        s_vec.append(_cbd(eta1, noise_bytes))

    # Generate error vector e
    e_vec = []
    for i in range(k):
        noise_seed = sigma + bytes([k + i])
        noise_bytes = hashlib.shake_256(noise_seed).digest(eta1 * 64 + 32)
        e_vec.append(_cbd(eta1, noise_bytes))

    # Compute t = A*s + e
    t_vec = []
    for i in range(k):
        t_i = [0] * 256
        for j in range(k):
            product = _ntt_multiply_poly(a_matrix[i][j], s_vec[j], q)
            t_i = _poly_add(t_i, product, q)
        t_i = _poly_add(t_i, e_vec[i], q)
        t_vec.append(t_i)

    # Encode public key: rho || encode(t)
    pk_bytes = bytearray(rho)
    for i in range(k):
        pk_bytes.extend(_encode_poly(t_vec[i]))

    # Encode secret key: encode(s) || pk || H(pk) || z
    sk_bytes = bytearray()
    for i in range(k):
        sk_bytes.extend(_encode_poly(s_vec[i]))
    pk_final = bytes(pk_bytes)
    sk_bytes.extend(pk_final)
    sk_bytes.extend(hashlib.sha3_256(pk_final).digest())
    sk_bytes.extend(secrets.token_bytes(32))  # z for implicit rejection

    return base64.b64encode(pk_final).decode('ascii'), base64.b64encode(bytes(sk_bytes)).decode('ascii')


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write PID file: {e}")


def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"Failed to remove PID file: {e}")
            return


def main():
    config = load_config()
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', [])
        kyber_variant = config.get('kyber_variant', 'kyber-768')

        logging.info("KYBER-KEYGEN AGENT STARTED")
        logging.info(f"Kyber variant: {kyber_variant}")
        logging.info(f"Targets: {target_agents}")

        # Validate variant
        if kyber_variant not in KYBER_PARAMS:
            logging.error(f"Invalid Kyber variant: {kyber_variant}. Must be one of: {list(KYBER_PARAMS.keys())}")
            sys.exit(1)

        # Generate key pair
        try:
            public_key_b64, private_key_b64 = generate_kyber_keypair(kyber_variant)
            logging.info(f"Key pair generated successfully for {kyber_variant}")

            # Log keys in the required format
            logging.info(
                f"INI_SECTION_KYBER_KEYGEN<<<\n"
                f"public_key: {public_key_b64}\n"
                f"private_key: {private_key_b64}\n"
                f">>>END_SECTION_KYBER_KEYGEN"
            )

        except Exception as e:
            logging.error(f"Key generation failed: {e}")
            sys.exit(1)

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"Kyber-KeyGen agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
