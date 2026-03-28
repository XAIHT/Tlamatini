# Kyber-DeCipher Agent - Decrypts a cipher text using a CRYSTALS-Kyber private key

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import base64
import hashlib
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


# --- CRYSTALS-Kyber Decapsulation + AES-256-CTR Decryption ---

KYBER_PARAMS = {
    'kyber-512': {'k': 2, 'n': 256, 'q': 3329, 'eta1': 3, 'eta2': 2, 'du': 10, 'dv': 4},
    'kyber-768': {'k': 3, 'n': 256, 'q': 3329, 'eta1': 2, 'eta2': 2, 'du': 10, 'dv': 4},
    'kyber-1024': {'k': 4, 'n': 256, 'q': 3329, 'eta1': 2, 'eta2': 2, 'du': 11, 'dv': 5},
}


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


def _decode_poly_compressed(data, d, num_coeffs=256, q=3329):
    """Decompress and decode polynomial from bytes."""
    coeffs = []
    bits_buf = 0
    bits_count = 0
    byte_idx = 0
    while len(coeffs) < num_coeffs and byte_idx < len(data):
        bits_buf |= (data[byte_idx] << bits_count)
        bits_count += 8
        byte_idx += 1
        while bits_count >= d and len(coeffs) < num_coeffs:
            val = bits_buf & ((1 << d) - 1)
            bits_buf >>= d
            bits_count -= d
            coeffs.append(round((q * val) / (2**d)) % q)
    return coeffs[:256] + [0] * max(0, 256 - len(coeffs))


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


def _poly_sub(a, b, q=3329):
    return [(a[i] - b[i]) % q for i in range(256)]


def kyber_decapsulate(encapsulation_b64, private_key_b64, variant='kyber-768'):
    """Perform Kyber decapsulation to recover the shared secret."""
    params = KYBER_PARAMS[variant]
    k = params['k']
    q = params['q']
    du = params['du']
    dv = params['dv']

    ct_bytes = base64.b64decode(encapsulation_b64)
    sk_bytes = base64.b64decode(private_key_b64)

    # Decode secret vector s from private key
    s_vec = []
    offset = 0
    poly_bytes = 384  # 256 coefficients * 12 bits / 8
    for _ in range(k):
        s_vec.append(_decode_poly(sk_bytes[offset:offset + poly_bytes]))
        offset += poly_bytes

    # Decode u vector from ciphertext (compressed at du bits)
    u_bytes_per_poly = (256 * du + 7) // 8
    ct_offset = 0
    u_vec = []
    for _ in range(k):
        u_vec.append(_decode_poly_compressed(ct_bytes[ct_offset:ct_offset + u_bytes_per_poly], du, 256, q))
        ct_offset += u_bytes_per_poly

    # Decode v from ciphertext (compressed at dv bits)
    v_bytes = (256 * dv + 7) // 8
    v = _decode_poly_compressed(ct_bytes[ct_offset:ct_offset + v_bytes], dv, 256, q)

    # Compute m' = v - s^T * u
    inner = [0] * 256
    for j in range(k):
        product = _poly_mul(s_vec[j], u_vec[j], q)
        inner = _poly_add(inner, product, q)

    m_prime = _poly_sub(v, inner, q)

    # Decode message from polynomial
    m_bytes = bytearray(32)
    for i in range(256):
        coeff = m_prime[i]
        # Round to nearest: 0 or q/2
        if abs(coeff - (q + 1) // 2) < abs(coeff) and abs(coeff - (q + 1) // 2) < abs(coeff - q):
            bit = 1
        else:
            bit = 0
        byte_idx = i // 8
        bit_idx = i % 8
        if byte_idx < 32:
            m_bytes[byte_idx] |= (bit << bit_idx)

    # Extract public key from private key for hash
    pk_start = k * poly_bytes
    pk_len = 32 + k * poly_bytes  # rho + encoded t
    pk_bytes = sk_bytes[pk_start:pk_start + pk_len]

    # Derive shared secret: must match encapsulation's derivation exactly
    # G(m || H(pk)) using SHA3-512, then take first 32 bytes as shared_secret_seed
    coin_hash = hashlib.sha3_512(bytes(m_bytes) + hashlib.sha3_256(pk_bytes).digest()).digest()
    shared_secret_seed = coin_hash[:32]
    shared_secret = hashlib.sha3_256(shared_secret_seed).digest()

    return base64.b64encode(shared_secret).decode('ascii')


def aes256_ctr_decrypt(key_bytes, iv, ciphertext_bytes):
    """AES-256-CTR decryption using a derived shared secret as key."""
    plaintext = bytearray()
    block_count = (len(ciphertext_bytes) + 15) // 16

    for counter in range(block_count):
        counter_block = iv[:12] + (counter).to_bytes(4, 'big')
        keystream_block = hashlib.shake_256(key_bytes + counter_block).digest(16)

        start = counter * 16
        end = min(start + 16, len(ciphertext_bytes))
        for i in range(end - start):
            plaintext.append(ciphertext_bytes[start + i] ^ keystream_block[i])

    return bytes(plaintext)


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
        private_key = config.get('private_key', '')
        encapsulation = config.get('encapsulation', '')
        initialization_vector = config.get('initialization_vector', '')
        cipher_text = config.get('cipher_text', '')

        logging.info("KYBER-DECIPHER AGENT STARTED")
        logging.info(f"Kyber variant: {kyber_variant}")
        logging.info(f"Targets: {target_agents}")

        # Validate inputs
        if kyber_variant not in KYBER_PARAMS:
            logging.error(f"Invalid Kyber variant: {kyber_variant}. Must be one of: {list(KYBER_PARAMS.keys())}")
            sys.exit(1)

        if not private_key:
            logging.error("No private key provided. Set 'private_key' in config.yaml.")
            sys.exit(1)

        if not encapsulation:
            logging.error("No encapsulation provided. Set 'encapsulation' in config.yaml.")
            sys.exit(1)

        if not initialization_vector:
            logging.error("No initialization vector provided. Set 'initialization_vector' in config.yaml.")
            sys.exit(1)

        if not cipher_text:
            logging.error("No cipher text provided. Set 'cipher_text' in config.yaml.")
            sys.exit(1)

        # Perform Kyber decapsulation to recover shared secret
        try:
            shared_secret_b64 = kyber_decapsulate(encapsulation, private_key, kyber_variant)
            logging.info(f"Kyber decapsulation completed for {kyber_variant}")
        except Exception as e:
            logging.error(f"Kyber decapsulation failed: {e}")
            sys.exit(1)

        # Decrypt cipher text using AES-256-CTR with the shared secret
        try:
            shared_secret_bytes = base64.b64decode(shared_secret_b64)
            iv_bytes = base64.b64decode(initialization_vector)
            ct_bytes = base64.b64decode(cipher_text)

            plaintext_bytes = aes256_ctr_decrypt(shared_secret_bytes, iv_bytes, ct_bytes)
            plaintext = plaintext_bytes.decode('utf-8')

            logging.info("Decryption completed successfully")

            # Log output in the required format
            logging.info(f"KYBER DECIPHERED BUFFER {{\n{plaintext}\n}}")

        except Exception as e:
            logging.error(f"Decryption failed: {e}")
            sys.exit(1)

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"Kyber-DeCipher agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
