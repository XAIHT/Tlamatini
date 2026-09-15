# ══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
#
# pptxer_media.py — MEDIA ACQUISITION AND PREPARATION.
#
# Images, video and audio: fetched (local path OR http/https URL), VERIFIED by
# their actual bytes, converted to what PowerPoint really accepts, downscaled,
# and handed to the builder with honest metadata.
#
# Sibling module of pptxer.py. Stdlib urllib + Pillow (+ OpenCV, lazily, only
# to read a video's real dimensions). Imports nothing from agent.*.
#
# ═════════════════════════════════════════════════════════════════════════════
#  THE RULE THAT SHAPES THIS WHOLE MODULE
# ═════════════════════════════════════════════════════════════════════════════
#      A SERVER'S Content-Type HEADER IS NOT EVIDENCE. THE BYTES ARE.
#
# Half the images on the internet are served as application/octet-stream, and
# a cheerful `image/jpeg` is routinely attached to an HTML error page. Trusting
# the header means embedding a 404 page into a slide as if it were a
# photograph — python-pptx will accept it, PowerPoint will show a broken frame,
# and nothing in the chain will have reported a problem. That is precisely the
# silent-plausible-WRONG class PDFer's missing-images bug belonged to.
#
# So every fetched file is identified by MAGIC NUMBER and, for images, opened
# and verified by Pillow before it is allowed anywhere near the deck.
#
# ═════════════════════════════════════════════════════════════════════════════
#  SAFETY (this module makes outbound network requests on the user's behalf)
# ═════════════════════════════════════════════════════════════════════════════
#  · only http/https — no file://, ftp://, data:, or anything else;
#  · private, loopback, link-local and reserved address space is REFUSED by
#    default (`allow_private_hosts`), so a deck built from a model-suggested
#    URL cannot be used to probe the machine's own network;
#  · a hard byte cap, enforced WHILE streaming, not after;
#  · a connect/read timeout on every request;
#  · a bounded redirect chain, with every hop re-validated — a public URL that
#    redirects to 169.254.169.254 is the classic bypass;
#  · everything lands under <app>/Temp per the Tlamatini directory policy.
#
# Downloading a file does not make it licensed for use. PPTXer records the
# source URL for every fetched asset so the deck can be attributed, and says so
# in its report — the agent finds images, the human clears rights.

import hashlib
import ipaddress
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

__all__ = [
    "MediaAsset", "fetch_media", "prepare_image", "prepare_video",
    "prepare_audio", "probe_image", "probe_video", "sniff_kind",
    "IMAGE_EXTS", "VIDEO_EXTS", "AUDIO_EXTS",
    "PPTX_SAFE_IMAGE_EXTS", "PPTX_SAFE_VIDEO_EXTS", "PPTX_SAFE_AUDIO_EXTS",
]

# What python-pptx / PowerPoint reliably accept when EMBEDDED.
# WEBP and AVIF are deliberately absent: modern PowerPoint can often display
# them, but embedding them produces decks that fail to render on Office 2016,
# on Mac, and in the web viewer — so PPTXer converts them to PNG instead.
PPTX_SAFE_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".emf", ".wmf"})
PPTX_SAFE_VIDEO_EXTS = frozenset({".mp4", ".m4v", ".mov", ".wmv", ".avi"})
PPTX_SAFE_AUDIO_EXTS = frozenset({".mp3", ".wav", ".m4a", ".wma"})

IMAGE_EXTS = PPTX_SAFE_IMAGE_EXTS | {".webp", ".avif", ".jfif", ".ico", ".heic"}
VIDEO_EXTS = PPTX_SAFE_VIDEO_EXTS | {".mkv", ".webm", ".flv", ".mpg", ".mpeg", ".m2v"}
AUDIO_EXTS = PPTX_SAFE_AUDIO_EXTS | {".ogg", ".flac", ".aac", ".opus"}

# Magic numbers. (offset, signature, kind, extension)
_SIGNATURES = (
    (0, b"\x89PNG\r\n\x1a\n", "image", ".png"),
    (0, b"\xff\xd8\xff", "image", ".jpg"),
    (0, b"GIF87a", "image", ".gif"),
    (0, b"GIF89a", "image", ".gif"),
    (0, b"BM", "image", ".bmp"),
    (0, b"II*\x00", "image", ".tiff"),
    (0, b"MM\x00*", "image", ".tiff"),
    (0, b"\x00\x00\x01\x00", "image", ".ico"),
    (8, b"WEBP", "image", ".webp"),
    (4, b"ftypavif", "image", ".avif"),
    (4, b"ftypheic", "image", ".heic"),
    (4, b"ftypmif1", "image", ".heic"),
    (0, b"\x01\x00\x00\x00", "image", ".emf"),
    (4, b"ftypisom", "video", ".mp4"),
    (4, b"ftypmp4", "video", ".mp4"),
    (4, b"ftypM4V", "video", ".m4v"),
    (4, b"ftypqt", "video", ".mov"),
    (4, b"ftypiso2", "video", ".mp4"),
    (4, b"ftypavc1", "video", ".mp4"),
    (4, b"ftypmmp4", "video", ".mp4"),
    (0, b"\x1aE\xdf\xa3", "video", ".mkv"),        # Matroska / WebM
    (0, b"RIFF", "video", ".avi"),                 # refined below by the AVI/WAVE tag
    (0, b"\x30\x26\xb2\x75", "video", ".wmv"),     # ASF
    (0, b"FLV\x01", "video", ".flv"),
    (0, b"\x00\x00\x01\xba", "video", ".mpg"),
    (0, b"ID3", "audio", ".mp3"),
    (0, b"\xff\xfb", "audio", ".mp3"),
    (0, b"\xff\xf3", "audio", ".mp3"),
    (0, b"\xff\xf2", "audio", ".mp3"),
    (0, b"OggS", "audio", ".ogg"),
    (0, b"fLaC", "audio", ".flac"),
    (4, b"ftypM4A", "audio", ".m4a"),
)

_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "Tlamatini-PPTXer/1.0 (+https://github.com/XAIHT/Tlamatini)")

DEFAULT_MAX_BYTES = 64 * 1024 * 1024        # 64 MiB — a generous hero video
DEFAULT_TIMEOUT = 25
MAX_REDIRECTS = 5


class MediaAsset:
    """One prepared asset, with honest provenance and measured properties."""

    __slots__ = ("path", "kind", "ext", "width", "height", "bytes",
                 "source", "original_ext", "converted", "downscaled",
                 "duration", "ok", "error", "sha256", "note")

    def __init__(self, path="", kind="", ext="", width=0, height=0, size=0,
                 source="", original_ext="", converted=False, downscaled=False,
                 duration=0.0, ok=True, error="", sha256="", note=""):
        self.path = path
        self.kind = kind
        self.ext = ext
        self.width = int(width or 0)
        self.height = int(height or 0)
        self.bytes = int(size or 0)
        self.source = source
        self.original_ext = original_ext
        self.converted = bool(converted)
        self.downscaled = bool(downscaled)
        self.duration = float(duration or 0.0)
        self.ok = bool(ok)
        self.error = error
        self.sha256 = sha256
        self.note = note

    @property
    def aspect(self) -> float:
        return (self.width / self.height) if self.height else 0.0

    @property
    def is_remote(self) -> bool:
        return self.source.lower().startswith(("http://", "https://"))

    def as_dict(self) -> dict:
        return {
            "path": self.path, "kind": self.kind, "ext": self.ext,
            "width": self.width, "height": self.height, "bytes": self.bytes,
            "source": self.source, "converted": self.converted,
            "downscaled": self.downscaled, "duration": self.duration,
            "ok": self.ok, "error": self.error, "note": self.note,
        }

    def __repr__(self) -> str:
        if not self.ok:
            return f"MediaAsset(FAILED {self.source!r}: {self.error})"
        return (f"MediaAsset({self.kind} {self.width}x{self.height} "
                f"{self.bytes // 1024}KB {os.path.basename(self.path)})")


# ─────────────────────────────────────────────────────────────────────────────
# Identification — bytes, never headers
# ─────────────────────────────────────────────────────────────────────────────

def sniff_kind(path_or_bytes) -> tuple:
    """Identify a file from its MAGIC NUMBER. → (kind, ext) or ('', '').

    kind ∈ 'image' | 'video' | 'audio' | ''.
    Never raises, never guesses from the file name.
    """
    try:
        if isinstance(path_or_bytes, (bytes, bytearray)):
            head = bytes(path_or_bytes[:64])
        else:
            with open(path_or_bytes, "rb") as fh:
                head = fh.read(64)
    except Exception:                                             # noqa: BLE001
        return ("", "")

    if not head:
        return ("", "")

    # RIFF is shared by AVI, WAVE and WEBP — the sub-tag at offset 8 decides.
    if head[:4] == b"RIFF" and len(head) >= 12:
        tag = head[8:12]
        if tag == b"AVI ":
            return ("video", ".avi")
        if tag == b"WAVE":
            return ("audio", ".wav")
        if tag == b"WEBP":
            return ("image", ".webp")

    for offset, sig, kind, ext in _SIGNATURES:
        if head[offset:offset + len(sig)] == sig:
            return (kind, ext)

    return ("", "")


def probe_image(path) -> tuple:
    """(width, height, format) by actually OPENING the image. (0,0,'') on failure."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()                     # catches truncation and corruption
        with Image.open(path) as img:        # verify() invalidates the handle
            return (int(img.width), int(img.height), (img.format or "").upper())
    except Exception:                                             # noqa: BLE001
        return (0, 0, "")


def probe_video(path) -> tuple:
    """(width, height, duration_s, fps) via OpenCV. All zeros if unavailable.

    OpenCV already ships with Tlamatini (the media agents use it), so this adds
    no dependency. A failure here is NOT fatal: the video can still be embedded,
    it just gets a default frame size, and the caller is told.
    """
    try:
        import cv2
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return (0, 0, 0.0, 0.0)
        try:
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
            duration = (frames / fps) if fps > 0 else 0.0
            return (w, h, duration, fps)
        finally:
            cap.release()
    except Exception:                                             # noqa: BLE001
        return (0, 0, 0.0, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Network safety
# ─────────────────────────────────────────────────────────────────────────────

def _host_is_private(host: str) -> bool:
    """True when `host` resolves to space the agent must not reach.

    Resolves the NAME, because `internal.example.com` pointing at 10.0.0.5 is
    exactly the case a string check misses. A resolution failure returns True
    (fail-CLOSED) — the one place in PPTXer that does not fail open, because
    failing open here means making the request anyway.
    """
    if not host:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:                                             # noqa: BLE001
        return True

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return True
    return False


def _validate_url(url: str, allow_private: bool) -> tuple:
    """(ok, reason). Scheme + host policy."""
    try:
        parts = urllib.parse.urlparse(url)
    except Exception:                                             # noqa: BLE001
        return (False, "the URL could not be parsed")

    if parts.scheme.lower() not in ("http", "https"):
        return (False, f"only http/https are fetched; got {parts.scheme!r}")
    if not parts.netloc:
        return (False, "the URL has no host")
    if not allow_private and _host_is_private(parts.hostname or ""):
        return (False,
                f"{parts.hostname!r} resolves to a private, loopback or reserved "
                f"address and was refused (set allow_private_hosts to override)")
    return (True, "")


def _download(url, dest_dir, max_bytes=DEFAULT_MAX_BYTES,
              timeout=DEFAULT_TIMEOUT, allow_private=False) -> tuple:
    """Stream a URL to disk with every guard enforced. → (path, error)."""
    ok, reason = _validate_url(url, allow_private)
    if not ok:
        return ("", reason)

    current = url
    for hop in range(MAX_REDIRECTS + 1):
        req = urllib.request.Request(current, headers={
            "User-Agent": _USER_AGENT,
            "Accept": "image/*,video/*,audio/*,*/*;q=0.8",
        })
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            resp = opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and hop < MAX_REDIRECTS:
                target = exc.headers.get("Location") or ""
                if not target:
                    return ("", f"HTTP {exc.code} with no Location header")
                current = urllib.parse.urljoin(current, target)
                # EVERY hop is re-validated: a public URL redirecting into
                # private space is the classic bypass.
                ok, reason = _validate_url(current, allow_private)
                if not ok:
                    return ("", f"redirect refused — {reason}")
                continue
            return ("", f"HTTP {exc.code} {exc.reason}")
        except urllib.error.URLError as exc:
            return ("", f"could not reach the host: {exc.reason}")
        except Exception as exc:                                  # noqa: BLE001
            return ("", f"request failed: {exc}")

        with resp:
            declared = resp.headers.get("Content-Length")
            if declared:
                try:
                    if int(declared) > max_bytes:
                        return ("", f"the file declares {int(declared):,} bytes, "
                                    f"over the {max_bytes:,}-byte cap")
                except ValueError:
                    pass

            digest = hashlib.sha256()
            chunks = []
            total = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    # Enforced WHILE streaming: a server that lies about
                    # Content-Length (or omits it) cannot fill the disk.
                    return ("", f"the download exceeded the {max_bytes:,}-byte cap")
                digest.update(chunk)
                chunks.append(chunk)

        if total == 0:
            return ("", "the server returned an empty body")

        payload = b"".join(chunks)
        kind, ext = sniff_kind(payload)
        if not kind:
            head = payload[:180].decode("utf-8", errors="replace").strip()
            looks_html = head[:80].lower().lstrip().startswith(("<!doctype", "<html"))
            return ("", ("the downloaded bytes are an HTML page, not media "
                         "(the URL probably needs a login or is a viewer page, "
                         "not the file itself)")
                    if looks_html else
                    "the downloaded bytes match no known image, video or audio format")

        name = f"fetch_{digest.hexdigest()[:16]}{ext}"
        try:
            os.makedirs(dest_dir, exist_ok=True)
            path = os.path.join(dest_dir, name)
            with open(path, "wb") as fh:
                fh.write(payload)
            return (path, "")
        except Exception as exc:                                  # noqa: BLE001
            return ("", f"could not write the downloaded file: {exc}")

    return ("", f"more than {MAX_REDIRECTS} redirects")


def _looks_like_foreign_scheme(src: str) -> bool:
    """True when `src` is clearly a URL, but not one PPTXer will fetch.

    Deliberately narrow: a Windows path starts 'C:\\', which IS 'scheme-like'
    to a naive parser, so single-letter schemes are excluded.
    """
    head = src.split(":", 1)[0].lower()
    if len(head) < 2 or ":" not in src:
        return False
    return head.isalnum() and head not in ("http", "https")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface redirects as HTTPError so each hop can be re-validated."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Preparation
# ─────────────────────────────────────────────────────────────────────────────

def _temp_dir(subdir="media") -> str:
    root = (os.environ.get("TLAMATINI_TEMP") or "").strip() or os.getcwd()
    target = os.path.join(root, "PPTXer", subdir)
    try:
        os.makedirs(target, exist_ok=True)
        return target
    except Exception:                                             # noqa: BLE001
        return root


def fetch_media(source, dest_dir=None, max_bytes=DEFAULT_MAX_BYTES,
                timeout=DEFAULT_TIMEOUT, allow_private=False) -> MediaAsset:
    """Resolve a local path OR a URL to a verified local file.

    Returns a MediaAsset whose ``ok`` says whether it may be used. A failed
    fetch NEVER raises — the deck is built without that asset and the reason is
    reported, because one dead image URL must not cost the whole presentation.
    """
    src = str(source or "").strip()
    if not src:
        return MediaAsset(ok=False, error="no source given", source=src)

    dest = dest_dir or _temp_dir("media")

    if src.lower().startswith(("http://", "https://")):
        path, err = _download(src, dest, max_bytes, timeout, allow_private)
        if err:
            return MediaAsset(ok=False, error=err, source=src)
    elif _looks_like_foreign_scheme(src):
        # Say WHY rather than falling through to the local-path branch, which
        # would report the useless "the file does not exist" for a ftp:// or
        # data: URL the user plainly meant as a URL.
        scheme = src.split(":", 1)[0]
        return MediaAsset(
            ok=False, source=src,
            error=(f"{scheme}:// is not fetched — PPTXer downloads over http/https "
                   f"only. Save the file locally and pass its path instead."))
    else:
        path = os.path.abspath(os.path.expandvars(os.path.expanduser(src)))
        if not os.path.isfile(path):
            return MediaAsset(ok=False, error="the file does not exist", source=src)
        try:
            if os.path.getsize(path) > max_bytes:
                return MediaAsset(
                    ok=False, source=src,
                    error=f"the file is larger than the {max_bytes:,}-byte cap")
        except OSError as exc:
            return MediaAsset(ok=False, error=f"could not stat the file: {exc}",
                              source=src)

    kind, ext = sniff_kind(path)
    if not kind:
        return MediaAsset(
            ok=False, source=src, path=path,
            error="the bytes match no known image, video or audio format")

    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0

    return MediaAsset(path=path, kind=kind, ext=ext, size=size, source=src,
                      original_ext=ext, ok=True)


def prepare_image(source, max_px=1920, dest_dir=None, allow_private=False,
                  max_bytes=DEFAULT_MAX_BYTES, timeout=DEFAULT_TIMEOUT,
                  force_png=False) -> MediaAsset:
    """Fetch → verify → convert if needed → downscale. Ready to embed.

    Conversions performed, and why:
      · WEBP / AVIF / HEIC → PNG, because embedding them produces decks that
        will not render on older Office, on Mac, or in the web viewer;
      · RGBA/P → RGB for JPEG output, because JPEG has no alpha and Pillow
        would otherwise raise at save time;
      · anything above `max_px` on its longest edge is downscaled with LANCZOS.

    Downscaling matters more than it looks: a 6000px hero photo dropped into a
    13.3-inch slide is ~8 MB of pixels the projector will never resolve, and
    twenty of them make a 160 MB file that will not open over email.
    """
    asset = fetch_media(source, dest_dir, max_bytes, timeout, allow_private)
    if not asset.ok:
        return asset

    if asset.kind != "image":
        asset.ok = False
        asset.error = f"expected an image but the bytes are {asset.kind}"
        return asset

    width, height, fmt = probe_image(asset.path)
    if width <= 0 or height <= 0:
        asset.ok = False
        asset.error = ("the file has an image signature but could not be opened "
                       "— it is truncated or corrupt")
        return asset

    asset.width, asset.height = width, height

    needs_convert = force_png or asset.ext not in PPTX_SAFE_IMAGE_EXTS
    needs_resize = max_px and max(width, height) > int(max_px)

    if not needs_convert and not needs_resize:
        return asset

    try:
        from PIL import Image

        with Image.open(asset.path) as img:
            img.load()
            new_ext = ".png"
            has_alpha = img.mode in ("RGBA", "LA", "P")

            if needs_resize:
                scale = float(max_px) / max(width, height)
                new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                img = img.resize(new_size, Image.LANCZOS)
                asset.downscaled = True

            if has_alpha:
                out = img.convert("RGBA")
            else:
                out = img.convert("RGB")
                new_ext = ".jpg"

            base = os.path.splitext(os.path.basename(asset.path))[0]
            out_dir = dest_dir or _temp_dir("media")
            out_path = os.path.join(out_dir, f"{base}_prepared{new_ext}")

            if new_ext == ".jpg":
                out.save(out_path, "JPEG", quality=92, optimize=True,
                         progressive=True)
            else:
                out.save(out_path, "PNG", optimize=True)

            asset.converted = needs_convert
            asset.path = out_path
            asset.ext = new_ext
            asset.width, asset.height = out.size
            asset.bytes = os.path.getsize(out_path)
            if needs_convert:
                asset.note = (f"converted from {asset.original_ext} to {new_ext} "
                              f"for PowerPoint compatibility")
            if asset.downscaled:
                note = f"downscaled from {width}x{height} to {out.size[0]}x{out.size[1]}"
                asset.note = f"{asset.note}; {note}" if asset.note else note
        return asset
    except Exception as exc:                                      # noqa: BLE001
        asset.ok = False
        asset.error = f"the image could not be prepared: {exc}"
        return asset


def prepare_video(source, dest_dir=None, allow_private=False,
                  max_bytes=DEFAULT_MAX_BYTES, timeout=DEFAULT_TIMEOUT,
                  poster_dir=None) -> MediaAsset:
    """Fetch → verify → measure → extract a POSTER FRAME.

    ⚠️ PPTXer does NOT transcode. Re-encoding video needs ffmpeg, which
    Tlamatini does not ship, and a silent "conversion" that actually just
    renames a container is the kind of lie this codebase exists to avoid.
    Instead: a container PowerPoint cannot embed (.webm, .mkv, .flv) is
    REFUSED with the exact reason and the exact remedy.

    A poster frame IS extracted (OpenCV, already present), because a video
    with no poster shows as a black rectangle in the deck until it is played —
    and in an exported PDF, forever.
    """
    asset = fetch_media(source, dest_dir, max_bytes, timeout, allow_private)
    if not asset.ok:
        return asset

    if asset.kind != "video":
        asset.ok = False
        asset.error = f"expected a video but the bytes are {asset.kind}"
        return asset

    if asset.ext not in PPTX_SAFE_VIDEO_EXTS:
        asset.ok = False
        asset.error = (
            f"{asset.ext} cannot be embedded in a .pptx. PowerPoint accepts "
            f"{', '.join(sorted(PPTX_SAFE_VIDEO_EXTS))}. Convert it to MP4 "
            f"(H.264 + AAC) first — PPTXer does not transcode, because it ships "
            f"no encoder and will not rename a container and call it a conversion."
        )
        return asset

    w, h, duration, fps = probe_video(asset.path)
    asset.width, asset.height = w, h
    asset.duration = duration
    if w <= 0 or h <= 0:
        asset.note = ("the video's dimensions could not be read; the slide will "
                      "use a 16:9 frame")
        asset.width, asset.height = 1920, 1080

    poster = _extract_poster(asset.path, poster_dir or _temp_dir("posters"))
    if poster:
        asset.note = ((asset.note + "; ") if asset.note else "") + "poster frame extracted"
        asset.sha256 = poster          # carried for the builder; see build module
    return asset


def _extract_poster(video_path, dest_dir):
    """Grab a representative frame ~12% in, as a PNG. None on any failure.

    12% rather than frame 0 on purpose: the first frames of a trailer or a
    screen capture are very often black, a fade-in, or a logo card, which makes
    the worst possible poster.
    """
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        try:
            frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
            if frames > 10:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(frames * 0.12))
            ok, frame = cap.read()
            if not ok or frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = cap.read()
            if not ok or frame is None:
                return None
            os.makedirs(dest_dir, exist_ok=True)
            base = os.path.splitext(os.path.basename(video_path))[0]
            out = os.path.join(dest_dir, f"{base}_poster.png")
            cv2.imwrite(out, frame)
            return out if os.path.isfile(out) else None
        finally:
            cap.release()
    except Exception:                                             # noqa: BLE001
        return None


def prepare_audio(source, dest_dir=None, allow_private=False,
                  max_bytes=DEFAULT_MAX_BYTES, timeout=DEFAULT_TIMEOUT) -> MediaAsset:
    """Fetch → verify → check the container is embeddable."""
    asset = fetch_media(source, dest_dir, max_bytes, timeout, allow_private)
    if not asset.ok:
        return asset

    if asset.kind != "audio":
        asset.ok = False
        asset.error = f"expected audio but the bytes are {asset.kind}"
        return asset

    if asset.ext not in PPTX_SAFE_AUDIO_EXTS:
        asset.ok = False
        asset.error = (
            f"{asset.ext} cannot be embedded in a .pptx. PowerPoint accepts "
            f"{', '.join(sorted(PPTX_SAFE_AUDIO_EXTS))}. Convert it to MP3 or "
            f"WAV first — PPTXer ships no encoder and will not pretend to transcode."
        )
        return asset

    try:
        import wave
        if asset.ext == ".wav":
            with wave.open(asset.path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate() or 1
                asset.duration = frames / float(rate)
    except Exception:                                             # noqa: BLE001
        pass

    return asset


def prepare_many(sources, kind="image", **kwargs) -> list:
    """Prepare a list, keeping order and keeping the failures.

    Failures are RETURNED, not dropped, so the builder can decide (skip the
    slide, use a placeholder) and the agent can report exactly which URL died
    and why. Silently shortening the list is how a 12-image gallery becomes a
    9-image gallery with nobody noticing.
    """
    fn = {"image": prepare_image, "video": prepare_video,
          "audio": prepare_audio}.get(kind, prepare_image)
    out = []
    for src in (sources or []):
        try:
            out.append(fn(src, **kwargs))
        except Exception as exc:                                  # noqa: BLE001
            out.append(MediaAsset(ok=False, source=str(src),
                                  error=f"unexpected failure: {exc}"))
    return out
