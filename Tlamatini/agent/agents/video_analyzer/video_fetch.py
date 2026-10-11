"""Video-Analyzer URL intake: turn a web video link into a local media file.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.

Stdlib only, and imports nothing from ``agent.*``: a pool copy has no path back
into Django, and this module must behave the same from source and frozen builds.

WHY IT EXISTS (2026-10-11). Asked to transcribe a YouTube video, Video-Analyzer
answered "No video resolved from 'https://youtu.be/...'" three times, and the
chat then spent seven tool calls installing yt-dlp by hand -- one of them into
the user's personal Python folder -- before Whisperer could run at all. A web
link is now a first-class input: Video-Analyzer downloads it itself, into app
Temp, and analyzes the local copy.

WHERE yt-dlp COMES FROM, in this order:
  1. Tlamatini's PRIVATE copy, ``<runtimes>/yt-dlp-py<XY>`` (beside the private
     Node of runtime_provisioner). It exists only after an install or an update,
     so it is the newest copy on this machine.
  2. The yt-dlp shipped inside Tlamatini's own Python (requirements.txt).
  3. Installed on demand into (1) with ``pip install --target`` -- no admin,
     never the user's own site-packages.
Sites such as YouTube change often and an old yt-dlp stops working, so a
download that fails the way a site change fails (not a private or removed
video, not a network fault) updates (1) ONCE and retries.

OTHER FALLBACKS:
  * A JavaScript runtime (deno, Tlamatini's private Node, a system Node or bun)
    is handed to yt-dlp; YouTube without one is deprecated and loses formats.
    None found is not fatal -- the download is still attempted.
  * No ffmpeg (most machines): YouTube no longer serves one file with sound and
    picture, so the two streams are fetched apart and joined by PyAV (already
    shipped with Tlamatini) without re-encoding. Audio downloads never convert.
  * yt-dlp unavailable AND the link points straight at a media file: the file
    is downloaded with urllib.
  * A failure always carries a NAMED cause (``FetchError.code``) and a message a
    person can act on. A silent or invented success is never returned: the
    downloaded file is checked on disk before its path is handed back.
"""
import glob
import hashlib
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request


FETCH_INFO_MARKER = 'TLM_FETCH_INFO='
FETCH_PATH_MARKER = 'TLM_FETCH_PATH='
_INFO_FIELDS = ('id,title,uploader,channel,duration,webpage_url,extractor_key,'
                'format_id,ext,upload_date,live_status')

AUDIO_EXTENSIONS = frozenset({
    '.m4a', '.mp3', '.wav', '.ogg', '.oga', '.opus', '.flac', '.aac', '.weba', '.wma', '.mka',
})
VIDEO_EXTENSIONS = frozenset({
    '.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.wmv', '.flv', '.mpg', '.mpeg', '.ts',
})
DIRECT_MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

_URL_START = re.compile(r'^(?:https?://|www\.|m\.youtube\.com/|youtube\.com/|youtu\.be/)', re.IGNORECASE)
_URL_IN_TEXT = re.compile(r'(?:https?://|www\.|youtu\.be/)[^\s\'"<>`]+', re.IGNORECASE)
_TRAILING_PUNCTUATION = '.,;:!?)]}>\'"'
_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
_UPDATE_COOLDOWN_SECONDS = 6 * 3600
_LOCK_STALE_SECONDS = 15 * 60

# Ordered: the first family whose phrase appears in the failure names the cause.
# Only the LAST family (and anything unrecognised) is worth updating yt-dlp for.
_FAILURE_FAMILIES = (
    ('video_unavailable', (
        'private video', 'video unavailable', 'this video is unavailable', 'has been removed',
        'is not available in your country', 'video is not available', 'no longer available',
        'copyright', 'members-only', 'join this channel', 'premieres in', 'live event will begin',
        'this live event', 'http error 404', 'http error 410', 'does not exist',
    )),
    ('login_required', (
        'sign in to confirm', 'confirm your age', 'age-restricted', 'age restricted',
        'login required', 'requires authentication', 'use --cookies', 'cookies-from-browser',
        'not a bot', 'account required', 'http error 401',
    )),
    ('network', (
        'getaddrinfo failed', 'name or service not known', 'temporary failure in name resolution',
        'nodename nor servname', 'timed out', 'connection refused', 'connection reset',
        'network is unreachable', 'unable to connect', 'no route to host',
        'certificate verify failed', 'urlopen error', 'remote end closed connection',
    )),
    ('unsupported_url', ('unsupported url',)),
)
_UPDATABLE_CODES = frozenset({'unsupported_url', 'download_failed'})

_MESSAGES = {
    'disabled': 'Downloading web videos is turned off (download.enabled is false), so {url} was not fetched.',
    'ytdlp_unavailable': ('The video downloader (yt-dlp) is not available here and could not be installed, '
                          'so {url} was not fetched. Check the internet connection and try again; '
                          'Tlamatini installs it by itself on the next attempt.'),
    'video_unavailable': ('The video at {url} cannot be downloaded: the site reports it as private, removed, '
                          'region-locked or not live yet.'),
    'login_required': ("The site wants a signed-in user before it serves {url} (an age or 'not a bot' check). "
                       "Set download.cookies_from_browser='firefox' (or 'edge' / 'chrome') or "
                       "download.cookies_file='<path to a cookies.txt>' and try again."),
    'network': 'Tlamatini could not reach {url}: the network or the site did not answer.',
    'unsupported_url': ("yt-dlp does not know how to download {url}. Give a direct link to the media file, "
                        'or download it yourself and pass its local path in video_pathfilenames.'),
    'timeout': 'Downloading {url} took longer than download.timeout_seconds ({timeout} s) and was stopped.',
    'download_failed': 'yt-dlp could not download {url}.',
    'empty_file': 'The download of {url} finished, but the file on disk is missing or empty.',
}


class FetchError(RuntimeError):
    """A download that did not happen, with a NAMED cause in ``code``."""

    def __init__(self, code, message, detail=''):
        super().__init__(message)
        self.code = code
        self.detail = detail


# ───────────────────────────── link recognition ─────────────────────────────

def is_url(value):
    """True for a web link (``https://``, ``www.``, ``youtu.be/`` ...)."""
    text = str(value or '').strip().strip('"\'<>`')
    return bool(_URL_START.match(text))


def normalize_url(value):
    """Strip quotes and trailing punctuation; add ``https://`` when missing."""
    text = str(value or '').strip().strip('"\'<>`').rstrip(_TRAILING_PUNCTUATION)
    if not re.match(r'^[a-z][a-z0-9+.-]*://', text, re.IGNORECASE):
        text = 'https://' + text
    return text


def find_url(text):
    """The first web link written inside free text, or ''."""
    match = _URL_IN_TEXT.search(str(text or ''))
    return normalize_url(match.group(0)) if match else ''


def media_kind(analysis_type):
    """Transcription needs only the sound; summary and robotics need the picture."""
    return 'audio' if str(analysis_type or '').strip().lower() == 'transcription' else 'video'


def _looks_direct(url):
    path = urllib.parse.urlparse(url).path or ''
    return os.path.splitext(path)[1].lower() in DIRECT_MEDIA_EXTENSIONS


def _boolean(value, default):
    if value is None or value == '':
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ('false', 'off', 'no', '0', 'none', 'disabled')
    return bool(value)


def _integer(value, default, low, high):
    try:
        return max(low, min(high, int(float(value))))
    except (TypeError, ValueError, OverflowError):
        return default


# ───────────────────────────── where things live ─────────────────────────────

def runtimes_root():
    """Tlamatini's private per-user runtime root -- the same place
    runtime_provisioner keeps Node and uv. Never the install dir (a self-update
    replaces it) and never a system dir (that would need admin)."""
    override = (os.environ.get('TLAMATINI_RUNTIMES') or '').strip()
    if override:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(override)))
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(base, 'Tlamatini', 'runtimes')


def private_dir():
    """Private yt-dlp, per Python minor version (``pip --target`` output is
    version-specific in general, so two Pythons never share one copy)."""
    return os.path.join(runtimes_root(), 'yt-dlp-py%d%d' % sys.version_info[:2])


def _app_temp_root():
    temp = (os.environ.get('TLAMATINI_TEMP') or '').strip()
    if temp:
        return temp
    here = os.path.dirname(os.path.abspath(__file__))
    agents = ''
    probe = here
    while True:
        if os.path.basename(probe).lower() == 'agents':
            agents = probe
            break
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    app = os.path.dirname(agents) if agents else here
    if agents and os.path.isfile(os.path.join(app, 'path_guard.py')) \
            and os.path.isfile(os.path.join(os.path.dirname(app), 'manage.py')):
        app = os.path.dirname(os.path.dirname(app))  # source: <repo>/Tlamatini/agent/agents
    return os.path.join(app, 'Temp')


def downloads_directory(settings):
    """``download.download_dir`` when set, else ``<app Temp>/video-analysis/downloads``.
    (Not called ``output_dir``: Video-Analyzer already has a top-level key of
    that name, and one leaf name per meaning keeps the chat's key=value
    assignments unambiguous.)"""
    explicit = str((settings or {}).get('download_dir') or '').strip()
    directory = os.path.abspath(os.path.expandvars(os.path.expanduser(explicit))) if explicit \
        else os.path.join(_app_temp_root(), 'video-analysis', 'downloads')
    os.makedirs(directory, exist_ok=True)
    return directory


def _child_env(extra_path=''):
    env = dict(os.environ)
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    if extra_path:
        current = env.get('PYTHONPATH', '')
        env['PYTHONPATH'] = extra_path + (os.pathsep + current if current else '')
    return env


# ───────────────────────────── yt-dlp on this machine ─────────────────────────────

def _probe_version(env, timeout=90):
    try:
        proc = subprocess.run([sys.executable, '-m', 'yt_dlp', '--version'], capture_output=True,
                              text=True, encoding='utf-8', errors='replace', env=env,
                              timeout=timeout, creationflags=_NO_WINDOW)
    except Exception:
        return ''
    if proc.returncode != 0:
        return ''
    lines = [line.strip() for line in (proc.stdout or '').splitlines() if line.strip()]
    return lines[-1] if lines else ''


def _private_is_present():
    return os.path.isfile(os.path.join(private_dir(), 'yt_dlp', '__init__.py'))


def _bundled_is_present():
    try:
        return importlib.util.find_spec('yt_dlp') is not None
    except Exception:
        return False


class _InstallLock:
    """One installer at a time across every Tlamatini process on this machine."""

    def __init__(self, path, wait_seconds=300):
        self.path = path
        self.wait_seconds = wait_seconds
        self.held = False

    def __enter__(self):
        deadline = time.monotonic() + self.wait_seconds
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        while True:
            try:
                handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(handle, str(os.getpid()).encode('ascii'))
                os.close(handle)
                self.held = True
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > _LOCK_STALE_SECONDS:
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise FetchError('ytdlp_unavailable',
                                     'Another Tlamatini run is still installing yt-dlp; try again in a minute.')
                time.sleep(1.0)

    def __exit__(self, *exc):
        if self.held:
            try:
                os.remove(self.path)
            except OSError:
                pass
        return False


def _stamp_path():
    return private_dir() + '.update.json'


def _update_allowed():
    try:
        with open(_stamp_path(), 'r', encoding='utf-8') as handle:
            stamp = json.load(handle)
        return time.time() - float(stamp.get('attempted_at', 0)) > _UPDATE_COOLDOWN_SECONDS
    except Exception:
        return True


def _write_stamp(version, ok):
    try:
        with open(_stamp_path(), 'w', encoding='utf-8') as handle:
            json.dump({'attempted_at': time.time(), 'version': version, 'ok': bool(ok)}, handle)
    except Exception:
        pass


def install_private(log=logging, timeout=900):
    """Install (or update) yt-dlp into the private directory, atomically:
    pip writes a staging copy, the copy must START before it replaces the old
    one, and a failure leaves the old copy exactly as it was."""
    final = private_dir()
    os.makedirs(os.path.dirname(final), exist_ok=True)
    with _InstallLock(final + '.lock'):
        staging = '%s.partial-%d' % (final, os.getpid())
        shutil.rmtree(staging, ignore_errors=True)
        command = [sys.executable, '-m', 'pip', 'install', '--upgrade', '--no-input',
                   '--disable-pip-version-check', '--no-warn-script-location',
                   '--target', staging, 'yt-dlp']
        log.info('VIDEO-FETCH: installing yt-dlp into %s ...', final)
        try:
            proc = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                  errors='replace', env=_child_env(), timeout=timeout,
                                  creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired:
            shutil.rmtree(staging, ignore_errors=True)
            _write_stamp('', False)
            raise FetchError('ytdlp_unavailable', 'Installing yt-dlp did not finish in time.')
        except Exception as exc:
            shutil.rmtree(staging, ignore_errors=True)
            _write_stamp('', False)
            raise FetchError('ytdlp_unavailable', 'Could not run pip to install yt-dlp: %s' % exc)
        output = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
        if proc.returncode != 0:
            shutil.rmtree(staging, ignore_errors=True)
            _write_stamp('', False)
            raise FetchError('ytdlp_unavailable', 'pip could not install yt-dlp.', output[-800:])
        version = _probe_version(_child_env(staging))
        if not version:
            shutil.rmtree(staging, ignore_errors=True)
            _write_stamp('', False)
            raise FetchError('ytdlp_unavailable', 'The freshly installed yt-dlp does not start.', output[-800:])
        old = ''
        if os.path.isdir(final):
            old = '%s.old-%d' % (final, os.getpid())
            os.replace(final, old)
        try:
            os.replace(staging, final)
        except OSError:
            if old:
                os.replace(old, final)  # put the previous copy back untouched
            shutil.rmtree(staging, ignore_errors=True)
            raise
        if old:
            shutil.rmtree(old, ignore_errors=True)
        _write_stamp(version, True)
        log.info('VIDEO-FETCH: yt-dlp %s installed in %s', version, final)
        return version


def resolve_downloader(settings, log=logging):
    """Return ``{'source', 'env', 'version'}`` for a yt-dlp that really starts."""
    if _private_is_present():
        env = _child_env(private_dir())
        version = _probe_version(env)
        if version:
            return {'source': 'private', 'env': env, 'version': version}
        log.warning('VIDEO-FETCH: the private yt-dlp in %s does not start; it will be reinstalled', private_dir())
    elif _bundled_is_present():
        env = _child_env()
        version = _probe_version(env)
        if version:
            return {'source': 'bundled', 'env': env, 'version': version}
        log.warning('VIDEO-FETCH: the bundled yt-dlp does not start; installing a private copy')
    if not _boolean((settings or {}).get('auto_install'), True):
        raise FetchError('ytdlp_unavailable',
                         'yt-dlp is not available and download.auto_install is false.')
    version = install_private(log)
    return {'source': 'private', 'env': _child_env(private_dir()), 'version': version}


# ───────────────────────────── helpers yt-dlp may use ─────────────────────────────

def _private_node():
    root = os.path.join(runtimes_root(), 'node')
    if not os.path.isdir(root):
        return ''
    try:
        candidates = [root] + [os.path.join(root, name) for name in sorted(os.listdir(root))]
    except OSError:
        return ''
    executable = 'node.exe' if os.name == 'nt' else os.path.join('bin', 'node')
    for candidate in candidates:
        path = os.path.join(candidate, executable)
        if os.path.isfile(path):
            return path
    return ''


def find_js_runtime(settings):
    """``RUNTIME:PATH`` for yt-dlp's ``--js-runtimes``, or '' when none exists.

    YouTube needs a JavaScript runtime to solve its download challenges; only
    deno is enabled by default inside yt-dlp, so Tlamatini's own Node (or a
    system one) is handed over explicitly."""
    explicit = str((settings or {}).get('js_runtime') or '').strip()
    if explicit.lower() in ('none', 'off', 'false', 'disabled'):
        return ''
    if explicit:
        name = explicit.split(':', 1)[0].lower()
        if name in ('deno', 'node', 'bun', 'quickjs'):
            return explicit
        stem = os.path.splitext(os.path.basename(explicit))[0].lower()
        kind = {'qjs': 'quickjs'}.get(stem, stem)
        return '%s:%s' % (kind if kind in ('deno', 'node', 'bun', 'quickjs') else 'node', explicit)
    for kind, path in (('deno', shutil.which('deno') or ''),
                       ('node', _private_node()),
                       ('node', shutil.which('node') or ''),
                       ('bun', shutil.which('bun') or '')):
        if path:
            return '%s:%s' % (kind, path)
    return ''


def find_ffmpeg(settings):
    """An ffmpeg yt-dlp may use to MERGE separate sound and picture streams, or
    ''. Never required: without one, video downloads pick a single file that
    already carries both (see format_selector)."""
    explicit = str((settings or {}).get('ffmpeg_location') or '').strip()
    if explicit and os.path.exists(explicit):
        return explicit
    return shutil.which('ffmpeg') or ''


def format_selector(kind, max_height, have_ffmpeg, need_audio=True):
    """yt-dlp ``-f`` for one download.

    Audio: the best sound stream as-is (PyAV decodes any container, so no
    conversion and no ffmpeg). Video: H.264 up to ``max_height`` first, so
    OpenCV can read every frame, never AV1 when anything else exists.

    WITHOUT ffmpeg (most machines) YouTube offers NO single file with sound and
    picture any more -- measured 2026-10-11, "Requested format is not
    available". So picture and sound are fetched as TWO files (the ``,``
    operator) and :func:`combine_streams` joins them with PyAV, which Tlamatini
    already ships; nothing is re-encoded and no ffmpeg program is needed."""
    if kind == 'audio':
        return 'bestaudio/best'
    height = int(max_height)
    picture = ('bv*[height<=%d][vcodec^=avc1]/bv*[height<=%d][vcodec!^=av01]/bv*[height<=%d]'
               % (height, height, height))
    single = ('b[height<=%d][vcodec^=avc1][acodec!=none]/b[height<=%d][vcodec!=none][acodec!=none]/'
              'b[vcodec!=none][acodec!=none]/b') % (height, height)
    if not need_audio:  # robotics judges motion only
        return picture + '/' + single
    if have_ffmpeg:
        return ('bv*[height<=%d][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=%d][vcodec^=avc1]+ba/'
                'bv*[height<=%d][vcodec!^=av01]+ba/bv*[height<=%d]+ba/' % (height, height, height, height)) + single
    return picture + '/' + single + ',ba[ext=m4a]/ba/b'


def combine_streams(paths, log=logging):
    """Turn what a separate-streams download produced into ONE playable file.

    A file that already holds both sound and picture is used as it is. Otherwise
    the picture file and the sound file are re-muxed (packets copied, never
    re-encoded) into ``<name>.mp4`` (H.264 + AAC/MP3) or ``<name>.mkv`` (any
    other pair), interleaved by timestamp, written to a temporary name first and
    renamed only when complete."""
    import heapq

    import av

    described = []
    for path in paths:
        with av.open(path, metadata_errors='ignore') as media:
            video = media.streams.video[0].codec_context.name if media.streams.video else ''
            audio = media.streams.audio[0].codec_context.name if media.streams.audio else ''
        described.append({'path': path, 'video': video, 'audio': audio})
    for item in described:
        if item['video'] and item['audio']:
            return item['path']
    picture = next((item for item in described if item['video']), None)
    sound = next((item for item in described if item['audio']), None)
    if picture is None:
        raise FetchError('download_failed', 'The download produced no picture stream.')
    if sound is None:
        log.warning('VIDEO-FETCH: the page offers no sound stream; analysing the picture alone')
        return picture['path']
    container = 'mp4' if picture['video'] == 'h264' and sound['audio'] in ('aac', 'mp3') else 'matroska'
    stem = re.sub(r'-f[^-.\\/]+$', '', os.path.splitext(picture['path'])[0])
    target = stem + ('.mp4' if container == 'mp4' else '.mkv')
    partial = target + '.joining'
    with av.open(picture['path'], metadata_errors='ignore') as video_in, \
            av.open(sound['path'], metadata_errors='ignore') as audio_in, \
            av.open(partial, 'w', format=container) as output:
        video_stream, audio_stream = video_in.streams.video[0], audio_in.streams.audio[0]
        video_out = output.add_stream_from_template(video_stream)
        audio_out = output.add_stream_from_template(audio_stream)

        def timed(source, stream, destination):
            for packet in source.demux(stream):
                if packet.dts is None:
                    continue  # the demuxer's final flush packet
                moment = float(packet.dts * packet.time_base)
                packet.stream = destination
                yield moment, packet

        for _, packet in heapq.merge(timed(video_in, video_stream, video_out),
                                     timed(audio_in, audio_stream, audio_out), key=lambda item: item[0]):
            output.mux(packet)
    os.replace(partial, target)
    log.info('VIDEO-FETCH: joined picture (%s) and sound (%s) without ffmpeg -> %s',
             picture['video'], sound['audio'], target)
    return target


def separate_streams(kind, ffmpeg, need_audio):
    """True when picture and sound are fetched as two files for PyAV to join."""
    return kind == 'video' and need_audio and not ffmpeg


def build_command(url, kind, directory, settings, js_runtime='', ffmpeg='', need_audio=True):
    settings = settings or {}
    max_height = _integer(settings.get('max_height'), 720, 144, 4320)
    # Separate streams need one file NAME per format, joined afterwards.
    template = ('%%(extractor_key)s_%%(id)s_%s-f%%(format_id)s.%%(ext)s' % kind
                if separate_streams(kind, ffmpeg, need_audio) else '%%(extractor_key)s_%%(id)s_%s.%%(ext)s' % kind)
    command = [
        sys.executable, '-m', 'yt_dlp',
        '--no-playlist', '--playlist-items', '1', '--no-simulate', '--newline', '--progress',
        '--no-mtime', '--restrict-filenames', '--trim-filenames', '120', '--no-colors',
        '--retries', '5', '--fragment-retries', '5', '--socket-timeout', '30',
        '-f', format_selector(kind, max_height, bool(ffmpeg), need_audio),
        '-P', directory,
        '-o', template,
        '--print', 'before_dl:%s%%(.{%s})j' % (FETCH_INFO_MARKER, _INFO_FIELDS),
        '--print', 'after_move:%s%%(filepath)s' % FETCH_PATH_MARKER,
    ]
    if kind == 'video' and ffmpeg and need_audio:
        command += ['--merge-output-format', 'mp4', '--ffmpeg-location', ffmpeg]
    if js_runtime:
        command += ['--js-runtimes', js_runtime]
    browser = str(settings.get('cookies_from_browser') or '').strip()
    if browser:
        command += ['--cookies-from-browser', browser]
    cookies = str(settings.get('cookies_file') or '').strip()
    if cookies:
        command += ['--cookies', cookies]
    max_mb = _integer(settings.get('max_filesize_mb'), 0, 0, 1024 * 1024)
    if max_mb:
        command += ['--max-filesize', '%dM' % max_mb]
    command += ['--', url]
    return command


# ───────────────────────────── running yt-dlp ─────────────────────────────

def _kill(proc):
    try:
        import psutil  # optional: also stops an ffmpeg merge child
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _run(command, env, timeout, log):
    """Run yt-dlp, streaming its output into the agent log (progress throttled)."""
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, text=True, encoding='utf-8',
                            errors='replace', env=env, creationflags=_NO_WINDOW, bufsize=1)
    lines = []
    state = {'percent': -10.0, 'at': 0.0}

    def reader():
        for raw in proc.stdout:
            line = raw.rstrip('\r\n')
            lines.append(line)
            if not line.strip():
                continue
            if line.startswith('[download]') and '%' in line:
                match = re.search(r'(\d+(?:\.\d+)?)%', line)
                percent = float(match.group(1)) if match else 0.0
                now = time.monotonic()
                if percent - state['percent'] < 10 and now - state['at'] < 15 and percent < 100:
                    continue
                state['percent'], state['at'] = percent, now
            if line.startswith(FETCH_INFO_MARKER):
                continue  # parsed and summarised by the caller
            log.info('VIDEO-FETCH: %s', line[:400])

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout
    timed_out = False
    while proc.poll() is None:
        if time.monotonic() > deadline:
            timed_out = True
            _kill(proc)
            break
        time.sleep(0.25)
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    thread.join(10)
    return (None if timed_out else proc.returncode), lines


def classify_failure(text):
    """Name the cause of a failed download from yt-dlp's own words."""
    lowered = str(text or '').lower()
    for code, phrases in _FAILURE_FAMILIES:
        if any(phrase in lowered for phrase in phrases):
            return code
    return 'download_failed'


def _error_detail(lines):
    errors = [line.strip() for line in lines if line.strip().startswith('ERROR')]
    if errors:
        return errors[-1][:600]
    tail = [line.strip() for line in lines if line.strip()]
    return (tail[-1] if tail else 'yt-dlp printed nothing')[:600]


def _parse_markers(lines):
    """The INFO json (last one wins) and EVERY final path, in print order --
    a separate-streams download prints one path per format."""
    info, paths = {}, []
    for line in lines:
        if line.startswith(FETCH_INFO_MARKER):
            try:
                parsed = json.loads(line[len(FETCH_INFO_MARKER):])
                if isinstance(parsed, dict):
                    info = parsed
            except ValueError:
                pass
        elif line.startswith(FETCH_PATH_MARKER):
            path = line[len(FETCH_PATH_MARKER):].strip()
            if path and path not in paths:
                paths.append(path)
    return info, paths


def _locate_downloads(directory, info, kind):
    """Fallback when yt-dlp did not print the final path (an old build, a
    post-processor that swallowed the print): find the files by their id."""
    video_id = str(info.get('id') or '').strip()
    if not video_id:
        return []
    pattern = os.path.join(glob.escape(directory), '*_%s_%s*.*' % (glob.escape(video_id), kind))
    candidates = [path for path in glob.glob(pattern)
                  if not path.endswith(('.part', '.ytdl', '.temp', '.json', '.joining')) and os.path.isfile(path)]
    return sorted(candidates, key=os.path.getmtime, reverse=True)


def _attempt(url, kind, directory, settings, downloader, js_runtime, ffmpeg, timeout, log, need_audio=True):
    command = build_command(url, kind, directory, settings, js_runtime, ffmpeg, need_audio)
    begun = time.time()
    returncode, lines = _run(command, downloader['env'], timeout, log)
    info, paths = _parse_markers(lines)
    if returncode is None:
        return {'ok': False, 'code': 'timeout', 'detail': _error_detail(lines), 'info': info}
    if returncode != 0:
        detail = _error_detail(lines)
        return {'ok': False, 'code': classify_failure('\n'.join(lines)), 'detail': detail, 'info': info}
    paths = [path for path in paths if os.path.isfile(path)] or _locate_downloads(directory, info, kind)[:1]
    paths = [path for path in paths if os.path.getsize(path) > 0]
    if not paths:
        return {'ok': False, 'code': 'empty_file', 'detail': _error_detail(lines), 'info': info}
    path = paths[0]
    if separate_streams(kind, ffmpeg, need_audio):
        try:
            path = combine_streams(paths, log)
        except FetchError as exc:
            return {'ok': False, 'code': exc.code, 'detail': str(exc), 'info': info}
        except Exception as exc:  # a container PyAV cannot re-mux is a named failure, never a crash
            return {'ok': False, 'code': 'download_failed',
                    'detail': 'sound and picture could not be joined without ffmpeg: %s' % exc, 'info': info}
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            return {'ok': False, 'code': 'empty_file', 'detail': 'joined file is empty', 'info': info}
    # --print makes yt-dlp quiet, so its "has already been downloaded" line may
    # never appear; a file older than this attempt (--no-mtime keeps the real
    # write time) is the reliable sign of a re-used earlier download.
    cached = any('has already been downloaded' in line for line in lines) \
        or all(os.path.getmtime(part) < begun - 1 for part in paths)
    return {'ok': True, 'path': os.path.abspath(path), 'info': info, 'cached': cached}


def _download_direct(url, directory, settings, timeout, log):
    """Plain HTTP download of a link that points straight at a media file --
    the fallback when yt-dlp itself cannot be had."""
    suffix = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or '.mp4'
    name = 'direct_%s%s' % (hashlib.sha1(url.encode('utf-8')).hexdigest()[:16], suffix)
    target = os.path.join(directory, name)
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        log.info('VIDEO-FETCH: reusing the earlier download %s', target)
        return target
    limit = _integer((settings or {}).get('max_filesize_mb'), 0, 0, 1024 * 1024) * 1024 * 1024
    partial = target + '.part'
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Tlamatini Video-Analyzer)'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(partial, 'wb') as handle:
            started = time.monotonic()
            total = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if limit and total > limit:
                    raise FetchError('download_failed', 'The file at %s is larger than download.max_filesize_mb.' % url)
                if time.monotonic() - started > timeout:
                    raise FetchError('timeout', _MESSAGES['timeout'].format(url=url, timeout=timeout))
                handle.write(block)
        if total <= 0:
            raise FetchError('empty_file', _MESSAGES['empty_file'].format(url=url))
        os.replace(partial, target)
    except FetchError:
        _remove_quietly(partial)
        raise
    except Exception as exc:
        _remove_quietly(partial)
        code = classify_failure(str(exc))
        raise FetchError(code if code != 'download_failed' else 'network',
                         _MESSAGES['network'].format(url=url), str(exc)[:600])
    log.info('VIDEO-FETCH: downloaded %s (%d bytes) without yt-dlp', target, os.path.getsize(target))
    return target


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _fail(code, url, detail, timeout=0):
    message = _MESSAGES.get(code, _MESSAGES['download_failed']).format(url=url, timeout=timeout)
    if detail:
        message += ' Details: ' + detail
    raise FetchError(code, message, detail)


# ───────────────────────────── the one entry point ─────────────────────────────

def fetch(url, analysis_type, config, log=logging):
    """Download ``url`` for ``analysis_type`` and return a description of the
    local file. Raises :class:`FetchError` with a named ``code`` otherwise."""
    config = config if isinstance(config, dict) else {}
    settings = config.get('download') if isinstance(config.get('download'), dict) else {}
    url = normalize_url(url)
    if not _boolean(settings.get('enabled'), True):
        _fail('disabled', url, '')
    kind = media_kind(analysis_type)
    need_audio = str(analysis_type or '').strip().lower() != 'robotics'  # robotics judges motion only
    directory = downloads_directory(settings)
    timeout = _integer(settings.get('timeout_seconds'), 1800, 60, 6 * 3600)
    started = time.monotonic()

    try:
        downloader = resolve_downloader(settings, log)
    except FetchError as exc:
        if _looks_direct(url):
            log.warning('VIDEO-FETCH: %s; the link points straight at a media file, downloading it directly', exc)
            path = _download_direct(url, directory, settings, timeout, log)
            return _result(url, kind, path, {}, {'source': 'urllib', 'version': ''}, '', False, started)
        _fail(exc.code, url, exc.detail or str(exc))

    js_runtime = find_js_runtime(settings)
    ffmpeg = find_ffmpeg(settings) if kind == 'video' else ''
    log.info('VIDEO-FETCH: %s -> %s download with yt-dlp %s (%s); JavaScript runtime: %s; ffmpeg: %s; into %s',
             url, kind, downloader['version'], downloader['source'], js_runtime or 'none',
             'not needed' if kind != 'video' else (
                 ffmpeg or ('none - picture and sound are fetched apart and joined with PyAV' if need_audio
                            else 'not needed (picture only)')), directory)

    attempt = _attempt(url, kind, directory, settings, downloader, js_runtime, ffmpeg, timeout, log, need_audio)
    if not attempt['ok'] and attempt['code'] in _UPDATABLE_CODES \
            and _boolean(settings.get('auto_update'), True) and _update_allowed():
        log.warning('VIDEO-FETCH: download failed (%s: %s); updating yt-dlp and trying once more',
                    attempt['code'], attempt['detail'])
        try:
            install_private(log)
            downloader = {'source': 'private', 'env': _child_env(private_dir()),
                          'version': _probe_version(_child_env(private_dir()))}
        except FetchError as exc:
            log.warning('VIDEO-FETCH: yt-dlp could not be updated (%s); keeping the first failure', exc)
        else:
            attempt = _attempt(url, kind, directory, settings, downloader, js_runtime, ffmpeg, timeout, log,
                               need_audio)

    if not attempt['ok'] and _looks_direct(url) and attempt['code'] in _UPDATABLE_CODES:
        log.warning('VIDEO-FETCH: yt-dlp failed (%s); the link points at a media file, downloading it directly',
                    attempt['code'])
        path = _download_direct(url, directory, settings, timeout, log)
        return _result(url, kind, path, attempt.get('info') or {}, downloader, js_runtime, False, started)

    if not attempt['ok']:
        _fail(attempt['code'], url, attempt['detail'], timeout)
    return _result(url, kind, attempt['path'], attempt['info'], downloader, js_runtime,
                   attempt['cached'], started)


def _result(url, kind, path, info, downloader, js_runtime, cached, started):
    info = info if isinstance(info, dict) else {}
    duration = info.get('duration')
    return {
        'source_url': url,
        'webpage_url': str(info.get('webpage_url') or url),
        'title': str(info.get('title') or ''),
        'uploader': str(info.get('uploader') or info.get('channel') or ''),
        'duration_seconds': duration if isinstance(duration, (int, float)) else None,
        'upload_date': str(info.get('upload_date') or ''),
        'extractor': str(info.get('extractor_key') or ('direct' if downloader.get('source') == 'urllib' else '')),
        'video_id': str(info.get('id') or ''),
        'format_id': str(info.get('format_id') or ''),
        'kind': kind,
        'path': path,
        'bytes': os.path.getsize(path),
        'cached': bool(cached),
        'downloader': downloader.get('source', ''),
        'downloader_version': downloader.get('version', ''),
        'js_runtime': js_runtime.split(':', 1)[0] if js_runtime else '',
        'seconds': round(time.monotonic() - started, 1),
    }
