# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Binary-content detection for the RAG context-loading pipeline.

WHY THIS EXISTS
---------------
Before this module, the ONLY way to keep a file out of the embedding chain was
to name it (or its extension) in **Context ▸ Set file type omissions**. That is
a manual allow/deny list: it cannot know about the ``.bin`` blob, the stray
``.pyc``, the vendored ``.so``, or the screenshot someone dropped into a project
folder. Those files were happily read as "text", decoded into mojibake, split
into chunks and embedded — poisoning the FAISS/BM25 index with megabytes of
noise, burning embedding VRAM and wall-clock, and diluting real retrieval hits.

``binary_guard`` closes that hole: it detects binary CONTENT (not just names)
and drops those files from the chain exactly the way a user-configured omission
does — and says so, loudly, in ``tlamatini.log``.

DESIGN — a short-circuiting cascade, cheapest test first
--------------------------------------------------------
The detector is built for throughput: a directory load can sweep tens of
thousands of files across 12 worker threads, so per-file cost is the whole
game. Every stage that can answer without I/O runs before any stage that
touches the disk, and **at most ONE read of ONE block** ever happens.

    Stage 1  EXTENSION      O(1) frozenset lookup, ZERO I/O. A ``.exe`` never
                            gets opened at all.
    Stage 2  SAMPLE         ONE open(), ONE read() of ``sample_bytes``. Every
                            remaining stage reuses this single buffer.
    Stage 3  EMPTY          A zero-byte file carries no content to embed and no
                            evidence of being binary -> TEXT (harmless).
    Stage 4  BOM            A UTF-8/16/32 byte-order mark proves TEXT.
                            *** THIS MUST PRECEDE THE NUL TEST ***  UTF-16 text
                            is full of legitimate 0x00 bytes; testing NUL first
                            would misclassify every UTF-16 document on the disk.
    Stage 5  SIGNATURE      Magic numbers (PE/ELF/Mach-O/ZIP/PNG/PDF/SQLite...)
                            prove BINARY even when the extension lies.
    Stage 6  NUL            A NUL byte in the sample -> BINARY. This is the
                            classic git/``file(1)`` heuristic and it catches the
                            long tail no signature list can enumerate.
    Stage 7  CONTROL RATIO  Share of non-text control bytes over the sample,
                            computed with ``bytes.translate`` (C speed, single
                            pass). Above the threshold -> BINARY.
    Stage 8  UTF-8 DECODE   Last resort for high-byte-heavy samples: undecodable
                            AND control-dirty -> BINARY. Legacy single-byte
                            encodings (cp1252/latin-1) still pass, on purpose.
    default  TEXT

FAIL-OPEN CONTRACT (do NOT weaken)
----------------------------------
A detector that crashes, or that guesses "binary" when unsure, is WORSE than no
detector: it silently deletes the user's real context. So every failure path in
this module resolves to **TEXT** (i.e. "load it"), every external call is
wrapped, and the module imports nothing outside the standard library. An
unreadable file, a permission error, a race with a deleted file — all load-as-
before. The guard may only ever remove a file it is confident about.

Self-contained + stdlib-only so it behaves identically in source and frozen
(PyInstaller) mode.
"""

from __future__ import annotations

import os
import threading

# ---------------------------------------------------------------------------
# Tunables (overridable from config.json — see resolve_settings())
# ---------------------------------------------------------------------------

#: How many bytes to sample from the head of each file. 8 KiB is the sweet
#: spot: one filesystem block on virtually every platform, big enough that a
#: text file's character distribution is statistically meaningful, small enough
#: that sampling a 4 GB video costs the same as sampling a README.
DEFAULT_SAMPLE_BYTES = 8192

#: Fraction of the sample that may be non-text control bytes before the file is
#: ruled binary. 0.30 is deliberately permissive — minified JS, CSV exports with
#: odd separators and log files with ANSI escapes must all still load.
DEFAULT_CONTROL_RATIO = 0.30

#: Minimum sample size for the ratio test to be meaningful. Below this a single
#: stray byte would blow past any percentage, so the ratio stage is skipped.
MIN_RATIO_SAMPLE = 32

# ---------------------------------------------------------------------------
# Stage 1 — extension tables (zero I/O)
# ---------------------------------------------------------------------------

#: Extensions whose content is binary by definition. Hitting this set skips the
#: read entirely — the single biggest performance win in the whole module.
BINARY_EXTENSIONS = frozenset({
    # executables / objects / debug
    '.exe', '.dll', '.so', '.dylib', '.bin', '.obj', '.o', '.a', '.lib',
    '.pyc', '.pyo', '.pyd', '.class', '.jar', '.war', '.ear', '.msi',
    '.pdb', '.ilk', '.exp', '.elf', '.axf', '.efi', '.ko', '.sys',
    '.wasm', '.nupkg', '.whl', '.egg', '.apk', '.aab', '.ipa', '.dex',
    # archives / compression
    '.zip', '.gz', '.bz2', '.xz', '.7z', '.rar', '.tar', '.tgz', '.tbz',
    '.zst', '.lz', '.lz4', '.cab', '.iso', '.dmg', '.pkg', '.deb', '.rpm',
    # images
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.tif', '.tiff',
    '.webp', '.avif', '.heic', '.heif', '.psd', '.xcf', '.raw', '.cr2',
    '.nef', '.dds', '.tga', '.jfif',
    # audio / video
    '.mp3', '.wav', '.flac', '.ogg', '.oga', '.opus', '.m4a', '.aac', '.wma',
    '.mid', '.midi', '.aiff', '.au',
    '.mp4', '.m4v', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mpg',
    '.mpeg', '.3gp', '.vob', '.ogv',
    # documents that are containers, not text
    '.pdf', '.doc', '.xls', '.ppt', '.docx', '.xlsx', '.pptx', '.odt',
    '.ods', '.odp', '.rtf', '.chm', '.epub', '.mobi', '.azw3', '.djvu',
    # fonts
    '.ttf', '.otf', '.woff', '.woff2', '.eot', '.fon', '.pfb',
    # databases / indexes / caches
    '.db', '.sqlite', '.sqlite3', '.mdb', '.accdb', '.dbf', '.frm', '.myd',
    '.myi', '.ibd', '.faiss', '.idx', '.pack', '.bak', '.dat',
    # ML / scientific blobs
    '.pt', '.pth', '.ckpt', '.safetensors', '.onnx', '.pb', '.tflite', '.h5',
    '.hdf5', '.npy', '.npz', '.pkl', '.pickle', '.joblib', '.gguf', '.ggml',
    '.bin_model', '.mlmodel', '.caffemodel', '.parquet', '.feather', '.arrow',
    '.orc', '.avro',
    # 3D / game / design assets
    '.blend', '.fbx', '.obj3d', '.glb', '.gltf', '.stl', '.3ds', '.max',
    '.uasset', '.umap', '.pak', '.unity', '.assets', '.bundle', '.sketch',
    '.fig', '.xd', '.ai', '.indd',
    # certificates / keystores / signed blobs
    '.p12', '.pfx', '.jks', '.keystore', '.der', '.crl',
    # misc
    '.swf', '.pyz', '.rdb', '.lock_bin', '.crash', '.dmp', '.mdmp', '.etl',
})

#: Extensions we KNOW are text. These skip the extension-denylist stage; the
#: content sniff still runs (a ``.txt`` can still hold a binary blob), but a
#: name collision with the denylist can never strip a real source file.
TEXT_EXTENSIONS = frozenset({
    '.txt', '.md', '.markdown', '.rst', '.adoc', '.org', '.tex', '.log',
    '.py', '.pyi', '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx', '.vue',
    '.java', '.kt', '.kts', '.scala', '.groovy', '.c', '.h', '.cc', '.cpp',
    '.cxx', '.hpp', '.hh', '.hxx', '.cs', '.go', '.rs', '.rb', '.php',
    '.pl', '.pm', '.lua', '.r', '.jl', '.swift', '.m', '.mm', '.dart',
    '.sh', '.bash', '.zsh', '.fish', '.ps1', '.psm1', '.psd1', '.bat',
    '.cmd', '.vbs', '.awk', '.sed', '.make', '.mk', '.cmake', '.gradle',
    '.json', '.jsonl', '.ndjson', '.yaml', '.yml', '.toml', '.ini', '.cfg',
    '.conf', '.properties', '.env', '.editorconfig', '.gitignore',
    '.gitattributes', '.dockerignore',
    '.html', '.htm', '.xhtml', '.xml', '.xsl', '.xsd', '.svg', '.css',
    '.scss', '.sass', '.less', '.styl',
    '.csv', '.tsv', '.sql', '.graphql', '.gql', '.proto', '.thrift',
    '.pmt', '.flw', '.skill', '.patch', '.diff', '.srt', '.vtt', '.ino',
    '.s', '.asm', '.ld', '.dts', '.dtsi', '.kconfig', '.pem', '.crt',
    '.cer', '.key', '.pub', '.csr',
})

# ---------------------------------------------------------------------------
# Stage 4 — byte-order marks (these PROVE text; must be tested before NUL)
# ---------------------------------------------------------------------------

BOM_SIGNATURES = (
    (b'\xef\xbb\xbf', 'UTF-8'),
    (b'\xff\xfe\x00\x00', 'UTF-32-LE'),   # longer BOMs first — \xff\xfe is a prefix
    (b'\x00\x00\xfe\xff', 'UTF-32-BE'),
    (b'\xff\xfe', 'UTF-16-LE'),
    (b'\xfe\xff', 'UTF-16-BE'),
)

# ---------------------------------------------------------------------------
# Stage 5 — magic numbers (these PROVE binary even when the extension lies)
# ---------------------------------------------------------------------------

MAGIC_SIGNATURES = (
    (b'MZ', 'DOS/PE executable'),
    (b'\x7fELF', 'ELF executable'),
    (b'\xca\xfe\xba\xbe', 'Java class / Mach-O fat binary'),
    (b'\xfe\xed\xfa\xce', 'Mach-O 32-bit'),
    (b'\xfe\xed\xfa\xcf', 'Mach-O 64-bit'),
    (b'PK\x03\x04', 'ZIP container'),
    (b'PK\x05\x06', 'ZIP container (empty)'),
    (b'PK\x07\x08', 'ZIP container (spanned)'),
    (b'Rar!\x1a\x07', 'RAR archive'),
    (b'7z\xbc\xaf\x27\x1c', '7-Zip archive'),
    (b'\x1f\x8b', 'gzip stream'),
    (b'BZh', 'bzip2 stream'),
    (b'\xfd7zXZ\x00', 'xz stream'),
    (b'\x28\xb5\x2f\xfd', 'zstd stream'),
    (b'%PDF-', 'PDF document'),
    (b'\x89PNG\r\n\x1a\n', 'PNG image'),
    (b'\xff\xd8\xff', 'JPEG image'),
    (b'GIF87a', 'GIF image'),
    (b'GIF89a', 'GIF image'),
    (b'BM', 'BMP image'),
    (b'II*\x00', 'TIFF image (LE)'),
    (b'MM\x00*', 'TIFF image (BE)'),
    (b'RIFF', 'RIFF container (WAV/AVI/WEBP)'),
    (b'OggS', 'Ogg container'),
    (b'fLaC', 'FLAC audio'),
    (b'\x1aE\xdf\xa3', 'Matroska/WebM container'),
    (b'ID3', 'MP3 with ID3 tag'),
    (b'SQLite format 3\x00', 'SQLite database'),
    (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 'MS Office (OLE2) document'),
    (b'\x00asm', 'WebAssembly module'),
    (b'\x93NUMPY', 'NumPy array'),
    (b'\x80\x02', 'Python pickle (proto 2)'),
    (b'\x80\x03', 'Python pickle (proto 3)'),
    (b'\x80\x04', 'Python pickle (proto 4)'),
    (b'GGUF', 'GGUF model'),
    (b'wOFF', 'WOFF font'),
    (b'wOF2', 'WOFF2 font'),
    (b'\x00\x01\x00\x00\x00', 'TrueType font'),
    (b'OTTO', 'OpenType font'),
    (b'ISc(', 'InstallShield cabinet'),
    (b'MSCF', 'Microsoft cabinet'),
    (b'\xed\xab\xee\xdb', 'RPM package'),
    (b'!<arch>', 'ar/deb archive'),
    (b'\xd4\xc3\xb2\xa1', 'pcap capture'),
    (b'\x0a\x0d\x0d\x0a', 'pcapng capture'),
)

#: Longest signature we need to compare — the sample is always at least this
#: long unless the file itself is shorter.
_MAX_SIGNATURE_LEN = max(len(sig) for sig, _ in MAGIC_SIGNATURES)

# ---------------------------------------------------------------------------
# Stage 7 — the control-byte table
# ---------------------------------------------------------------------------
#
# Everything NOT in this table counts as a "non-text" byte. We keep the usual
# whitespace/formatting controls (BEL, BS, TAB, LF, VT, FF, CR, ESC) plus all
# printable ASCII plus every high byte (0x80-0xFF) — high bytes are legitimate
# UTF-8 continuation bytes and legacy-encoding accented characters, so counting
# them as "binary evidence" would wrongly strip every Spanish source file
# Angela writes. This is the same table ``file(1)`` and git use.
_TEXT_BYTES = bytes(
    {7, 8, 9, 10, 11, 12, 13, 27}
    | set(range(0x20, 0x7F))
    | set(range(0x80, 0x100))
)


class BinaryVerdict:
    """Result of one classification. Truthy iff the file should be DROPPED."""

    __slots__ = ('is_binary', 'stage', 'reason', 'path')

    def __init__(self, is_binary, stage, reason, path=''):
        self.is_binary = bool(is_binary)
        self.stage = stage
        self.reason = reason
        self.path = path

    def __bool__(self):
        return self.is_binary

    def __repr__(self):
        verdict = 'BINARY' if self.is_binary else 'TEXT'
        return f'<BinaryVerdict {verdict} stage={self.stage} reason={self.reason!r}>'


def _normalized_extension(file_path):
    """Lower-cased extension including the leading dot ('' when there is none)."""
    try:
        return os.path.splitext(file_path)[1].lower()
    except Exception:
        return ''


def _decodes_as_utf8(sample, complete):
    """Does the sample decode as strict UTF-8?

    When the sample is a *truncated* head of a larger file its last character
    may be chopped mid-sequence, which would raise a bogus UnicodeDecodeError.
    We therefore retry while shaving up to 3 trailing bytes — the maximum
    length of a UTF-8 continuation run.
    """
    attempts = 1 if complete else 4
    for shave in range(attempts):
        candidate = sample if shave == 0 else sample[:-shave]
        if not candidate:
            return True
        try:
            candidate.decode('utf-8')
            return True
        except UnicodeDecodeError:
            continue
        except Exception:
            return True  # fail-open
    return False


def classify_bytes(sample, complete=True, control_ratio=DEFAULT_CONTROL_RATIO,
                   path=''):
    """Run stages 3-8 over an already-read sample. Pure, no I/O, unit-testable.

    ``complete`` says whether the sample is the ENTIRE file (True) or just its
    head (False); it only affects the UTF-8 truncation tolerance.
    """
    # Stage 3 — empty file: no content to embed, no evidence of binary.
    if not sample:
        return BinaryVerdict(False, 'empty', 'empty file', path)

    # Stage 4 — BOM proves text. MUST run before the NUL test (UTF-16/32 text
    # is legitimately full of 0x00 bytes).
    for bom, label in BOM_SIGNATURES:
        if sample.startswith(bom):
            return BinaryVerdict(False, 'bom', f'{label} BOM', path)

    # Stage 5 — magic number proves binary regardless of the extension.
    head = sample[:_MAX_SIGNATURE_LEN]
    for signature, label in MAGIC_SIGNATURES:
        if head.startswith(signature):
            return BinaryVerdict(True, 'signature', label, path)

    # Stage 6 — the classic NUL heuristic: real text does not contain NUL.
    if b'\x00' in sample:
        return BinaryVerdict(True, 'nul-byte', 'NUL byte in sampled block', path)

    # Stage 7 — control-byte density, single C-speed pass.
    if len(sample) >= MIN_RATIO_SAMPLE:
        non_text = sample.translate(None, _TEXT_BYTES)
        ratio = len(non_text) / len(sample)
        if ratio > control_ratio:
            return BinaryVerdict(
                True, 'control-ratio',
                f'{ratio:.0%} non-text control bytes (limit {control_ratio:.0%})',
                path,
            )
    else:
        ratio = 0.0

    # Stage 8 — last resort. Undecodable UTF-8 *and* already control-dirty is
    # binary; undecodable but clean is almost certainly legacy cp1252/latin-1
    # text, which we deliberately keep.
    if not _decodes_as_utf8(sample, complete) and ratio > (control_ratio / 3.0):
        return BinaryVerdict(
            True, 'encoding',
            'undecodable as UTF-8 with elevated control-byte density', path,
        )

    return BinaryVerdict(False, 'text', 'passed all binary probes', path)


def classify_file(file_path, sample_bytes=DEFAULT_SAMPLE_BYTES,
                  control_ratio=DEFAULT_CONTROL_RATIO,
                  extra_binary_extensions=(), force_text_extensions=()):
    """Classify ONE file. At most one open() and one read().

    Never raises: any error resolves to a TEXT verdict (fail-open).
    """
    extension = _normalized_extension(file_path)

    # Stage 1 — extension, zero I/O. force_text wins over every deny entry so a
    # user can always rescue a file the tables get wrong.
    if extension and extension not in force_text_extensions:
        if extension in BINARY_EXTENSIONS or extension in extra_binary_extensions:
            return BinaryVerdict(
                True, 'extension', f'known binary extension {extension}', file_path,
            )

    # Stage 2 — the single read.
    try:
        size = os.path.getsize(file_path)
        with open(file_path, 'rb') as handle:
            sample = handle.read(sample_bytes)
    except Exception as exc:  # unreadable / vanished / permission -> fail-open
        return BinaryVerdict(False, 'unreadable', f'probe skipped ({exc})', file_path)

    complete = size <= sample_bytes
    return classify_bytes(sample, complete=complete, control_ratio=control_ratio,
                          path=file_path)


def looks_binary(file_path, **kwargs):
    """Convenience boolean wrapper around :func:`classify_file`."""
    return bool(classify_file(file_path, **kwargs))


# ---------------------------------------------------------------------------
# Settings resolution (config.json -> kwargs)
# ---------------------------------------------------------------------------

def _as_extension_set(raw):
    """Normalize a config list/string of extensions into a lower-cased set."""
    if not raw:
        return frozenset()
    if isinstance(raw, str):
        parts = raw.replace(',', ' ').split()
    else:
        try:
            parts = list(raw)
        except Exception:
            return frozenset()
    cleaned = set()
    for part in parts:
        try:
            token = str(part).strip().lower()
        except Exception:
            continue
        if not token:
            continue
        token = token.lstrip('*')
        if not token.startswith('.'):
            token = '.' + token
        cleaned.add(token)
    return frozenset(cleaned)


def resolve_settings(config):
    """Read the ``binary_detection_*`` knobs out of config.json, fail-open."""
    config = config if isinstance(config, dict) else {}

    def _flag(key, default):
        value = config.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() not in ('false', '0', 'no', 'off', '')
        return bool(value)

    def _number(key, default, cast, low, high):
        try:
            value = cast(config.get(key, default))
        except Exception:
            return default
        if value < low or value > high:
            return default
        return value

    return {
        'enabled': _flag('binary_context_detection', True),
        'log_each_file': _flag('binary_detection_log_each_file', True),
        'sample_bytes': _number('binary_detection_sample_bytes',
                                DEFAULT_SAMPLE_BYTES, int, 64, 1 << 20),
        'control_ratio': _number('binary_detection_control_ratio',
                                 DEFAULT_CONTROL_RATIO, float, 0.01, 1.0),
        'extra_binary_extensions': _as_extension_set(
            config.get('binary_detection_extra_binary_extensions')),
        'force_text_extensions': _as_extension_set(
            config.get('binary_detection_force_text_extensions')),
    }


# ---------------------------------------------------------------------------
# Thread-safe omission recorder
# ---------------------------------------------------------------------------
#
# DirectoryLoader fans out across up to 12 worker threads, so the loader hook
# cannot simply print as it goes without interleaving mid-line. Each drop is
# recorded here and the call site prints one coherent block afterwards.

class BinaryOmissionRecorder:
    """Collects every binary omission of one context-load, thread-safely."""

    def __init__(self):
        self._lock = threading.Lock()
        self._entries = []

    def record(self, verdict):
        with self._lock:
            self._entries.append((verdict.path, verdict.stage, verdict.reason))

    def reset(self):
        with self._lock:
            self._entries = []

    def snapshot(self):
        with self._lock:
            return list(self._entries)

    def __len__(self):
        with self._lock:
            return len(self._entries)

    def format_report(self, max_listed=200):
        """Render the block that lands in ``tlamatini.log``.

        Returns ``''`` when nothing was dropped, so the caller can stay silent
        on the (common) clean load.
        """
        entries = self.snapshot()
        if not entries:
            return ''

        by_stage = {}
        for _, stage, _ in entries:
            by_stage[stage] = by_stage.get(stage, 0) + 1
        breakdown = ', '.join(
            f'{stage}={count}' for stage, count in sorted(by_stage.items())
        )

        lines = [
            '--- [BINARY-GUARD] ══════════════════════════════════════════════',
            f'--- [BINARY-GUARD] {len(entries)} binary file(s) OMITTED from the '
            'context / embedding chain',
            f'--- [BINARY-GUARD] Detected by: {breakdown}',
        ]
        for path, stage, reason in entries[:max_listed]:
            lines.append(f'--- [BINARY-GUARD]   ✗ OMITTED {path}  [{stage}: {reason}]')
        remaining = len(entries) - max_listed
        if remaining > 0:
            lines.append(
                f'--- [BINARY-GUARD]   … and {remaining} more (listing capped at '
                f'{max_listed})'
            )
        lines.append('--- [BINARY-GUARD] ══════════════════════════════════════════════')
        return '\n'.join(lines)


#: Process-wide recorder. One context load runs at a time (the chain is rebuilt
#: synchronously), so a module-level instance is safe and keeps the loader hook
#: free of plumbing.
omission_recorder = BinaryOmissionRecorder()
