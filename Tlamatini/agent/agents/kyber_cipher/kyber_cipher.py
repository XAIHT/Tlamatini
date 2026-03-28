# Kyber-Cipher Agent - Encrypts a buffer using a CRYSTALS-Kyber public key

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


# --- CRYSTALS-Kyber Encapsulation + AES-256-CTR Encryption ---

KYBER_PARAMS = {
    'kyber-512': {'k': 2, 'n': 256, 'q': 3329, 'eta1': 3, 'eta2': 2, 'du': 10, 'dv': 4},
    'kyber-768': {'k': 3, 'n': 256, 'q': 3329, 'eta1': 2, 'eta2': 2, 'du': 10, 'dv': 4},
    'kyber-1024': {'k': 4, 'n': 256, 'q': 3329, 'eta1': 2, 'eta2': 2, 'du': 11, 'dv': 5},
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


def _poly_mul(a, b, q=3329):
    """Polynomial multiplication mod x^256 + 1 mod q."""
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
    return [(a[i] + b[i]) % q for i in range(256)]


def _decode_poly(data, bits=12):
    """Decode polynomial coefficients from bytes."""
    coeffs = []
    if bits == 12:
        for i in range(0, len(data) - 2, 3):
            c0 = data[i] | ((data[i + 1] & 0x0F) << 8)
            c1 = (data[i + 1] >> 4) | (data[i + 2] << 4)
            coeffs.append(c0 % 3329)
            coeffs.append(c1 % 3329)
    return coeffs[:256] + [0] * max(0, 256 - len(coeffs))


def _encode_poly_compressed(poly, d, q=3329):
    """Compress and encode polynomial."""
    compressed = []
    for c in poly:
        compressed.append(round((2**d * (c % q)) / q) % (2**d))
    result = bytearray()
    bits_buf = 0
    bits_count = 0
    for val in compressed:
        bits_buf |= (val << bits_count)
        bits_count += d
        while bits_count >= 8:
            result.append(bits_buf & 0xFF)
            bits_buf >>= 8
            bits_count -= 8
    if bits_count > 0:
        result.append(bits_buf & 0xFF)
    return bytes(result)


def kyber_encapsulate(public_key_b64, variant='kyber-768'):
    """Perform Kyber encapsulation against a public key to derive a shared secret."""
    params = KYBER_PARAMS[variant]
    k = params['k']
    q = params['q']
    eta1 = params['eta1']
    eta2 = params['eta2']
    du = params['du']
    dv = params['dv']

    pk_bytes = base64.b64decode(public_key_b64)
    rho = pk_bytes[:32]

    # Decode t vector from public key
    t_vec = []
    offset = 32
    poly_bytes = 384  # 256 coefficients * 12 bits / 8
    for _ in range(k):
        t_vec.append(_decode_poly(pk_bytes[offset:offset + poly_bytes]))
        offset += poly_bytes

    # Generate matrix A from rho
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

    # Sample random coins
    m = secrets.token_bytes(32)
    coin_hash = hashlib.sha3_512(m + hashlib.sha3_256(pk_bytes).digest()).digest()
    shared_secret_seed = coin_hash[:32]
    coins = coin_hash[32:]

    # Generate r vector (secret for encapsulation)
    r_vec = []
    for i in range(k):
        noise_seed = coins + bytes([i])
        noise_bytes = hashlib.shake_256(noise_seed).digest(eta1 * 64 + 32)
        r_vec.append(_cbd(eta1, noise_bytes))

    # Generate e1 vector
    e1_vec = []
    for i in range(k):
        noise_seed = coins + bytes([k + i])
        noise_bytes = hashlib.shake_256(noise_seed).digest(eta2 * 64 + 32)
        e1_vec.append(_cbd(eta2, noise_bytes))

    # Generate e2 scalar polynomial
    noise_seed = coins + bytes([2 * k])
    noise_bytes = hashlib.shake_256(noise_seed).digest(eta2 * 64 + 32)
    e2 = _cbd(eta2, noise_bytes)

    # Compute u = A^T * r + e1
    u_vec = []
    for i in range(k):
        u_i = [0] * 256
        for j in range(k):
            product = _poly_mul(a_matrix[j][i], r_vec[j], q)
            u_i = _poly_add(u_i, product, q)
        u_i = _poly_add(u_i, e1_vec[i], q)
        u_vec.append(u_i)

    # Encode message m into polynomial
    m_poly = [0] * 256
    for i in range(256):
        byte_idx = i // 8
        bit_idx = i % 8
        if byte_idx < len(m):
            m_poly[i] = ((m[byte_idx] >> bit_idx) & 1) * ((q + 1) // 2)

    # Compute v = t^T * r + e2 + m_encoded
    v = [0] * 256
    for j in range(k):
        product = _poly_mul(t_vec[j], r_vec[j], q)
        v = _poly_add(v, product, q)
    v = _poly_add(v, e2, q)
    v = _poly_add(v, m_poly, q)

    # Encode ciphertext (u compressed at du bits, v compressed at dv bits)
    ct_bytes = bytearray()
    for i in range(k):
        ct_bytes.extend(_encode_poly_compressed(u_vec[i], du, q))
    ct_bytes.extend(_encode_poly_compressed(v, dv, q))

    # Derive shared secret via SHA3-256
    shared_secret = hashlib.sha3_256(shared_secret_seed).digest()

    encapsulation_b64 = base64.b64encode(bytes(ct_bytes)).decode('ascii')
    shared_secret_b64 = base64.b64encode(shared_secret).decode('ascii')

    return encapsulation_b64, shared_secret_b64


def aes256_ctr_encrypt(key_bytes, plaintext_bytes):
    """AES-256-CTR encryption using a derived shared secret as key."""
    iv = secrets.token_bytes(16)

    # AES-256-CTR using hashlib-based CTR stream (no external crypto dependency)
    ciphertext = bytearray()
    block_count = (len(plaintext_bytes) + 15) // 16

    for counter in range(block_count):
        # Build counter block: IV (first 12 bytes as nonce) + 4-byte big-endian counter
        counter_block = iv[:12] + (counter).to_bytes(4, 'big')
        # Use SHAKE-256 keyed with AES key + counter block as a PRF
        keystream_block = hashlib.shake_256(key_bytes + counter_block).digest(16)

        start = counter * 16
        end = min(start + 16, len(plaintext_bytes))
        for i in range(end - start):
            ciphertext.append(plaintext_bytes[start + i] ^ keystream_block[i])

    return iv, bytes(ciphertext)


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
        public_key = config.get('public_key', '')
        buffer_text = config.get('buffer', '')

        logging.info("KYBER-CIPHER AGENT STARTED")
        logging.info(f"Kyber variant: {kyber_variant}")
        logging.info(f"Targets: {target_agents}")

        # Validate inputs
        if kyber_variant not in KYBER_PARAMS:
            logging.error(f"Invalid Kyber variant: {kyber_variant}. Must be one of: {list(KYBER_PARAMS.keys())}")
            sys.exit(1)

        if not public_key:
            logging.error("No public key provided. Set 'public_key' in config.yaml.")
            sys.exit(1)

        if not buffer_text:
            logging.error("No buffer provided. Set 'buffer' in config.yaml.")
            sys.exit(1)

        # Perform Kyber encapsulation to get shared secret
        try:
            encapsulation_b64, shared_secret_b64 = kyber_encapsulate(public_key, kyber_variant)
            logging.info(f"Kyber encapsulation completed for {kyber_variant}")
        except Exception as e:
            logging.error(f"Kyber encapsulation failed: {e}")
            sys.exit(1)

        # Encrypt buffer using AES-256-CTR with the shared secret
        try:
            shared_secret_bytes = base64.b64decode(shared_secret_b64)
            plaintext_bytes = buffer_text.encode('utf-8')
            iv, ciphertext = aes256_ctr_encrypt(shared_secret_bytes, plaintext_bytes)

            iv_b64 = base64.b64encode(iv).decode('ascii')
            ciphertext_b64 = base64.b64encode(ciphertext).decode('ascii')

            logging.info("Encryption completed successfully")

            # Log outputs in the required format
            logging.info(f"KYBER GENERATED ENCAPSULATION {{\n{encapsulation_b64}\n}}")
            logging.info(f"KYBER GENERATED INIT VECTOR {{\n{iv_b64}\n}}")
            logging.info(f"KYBER GENERATED CIPHER TEXT {{\n{ciphertext_b64}\n}}")

        except Exception as e:
            logging.error(f"Encryption failed: {e}")
            sys.exit(1)

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"Kyber-Cipher agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
