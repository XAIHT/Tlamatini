# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Ephemeral encrypted tracker/web-seed lists. Only an opaque ID enters a flow."""

import json
import time
import uuid
from urllib.parse import urlsplit

if __package__:
    from .client import installation, known_folder
    from .contract import ID, TorrentError
else:
    from client import installation, known_folder
    from contract import ID, TorrentError


def directory(profile):
    return (
        known_folder(28)
        / "XAIHT/Tlamatini/Torrenter"
        / installation()
        / str(uuid.UUID(profile))
    )


def stage(profile, kind, text):
    if kind == "magnet":
        if not text.startswith("magnet:?") or len(text) > 8192:
            raise TorrentError("Enter a magnet link of up to 8192 characters.")
        return save(profile, kind, text)
    links = [line.strip() for line in text.splitlines() if line.strip()]
    allowed = ("http", "https", "udp") if kind == "trackers" else ("http", "https")
    if kind not in ("trackers", "web_seeds") or len(links) > 32:
        raise TorrentError("Choose up to 32 endpoints.")
    for link in links:
        try:
            parsed = urlsplit(link)
            valid = parsed.scheme in allowed and parsed.hostname and len(link) <= 2048
        except ValueError:
            valid = False
        if not valid:
            raise TorrentError("One of the endpoints is invalid.")
    return save(profile, kind, links)


def save(profile, kind, payload):
    import win32crypt

    folder = directory(profile)
    folder.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for item in folder.glob("*.source"):
        if item.stat().st_mtime < now - 900:
            item.unlink(missing_ok=True)
    if sum(1 for _ in folder.glob("*.source")) >= 32:
        raise TorrentError(
            "Source limit reached. Unused references expire in 15 minutes."
        )
    key = uuid.uuid4().hex
    payload = json.dumps([kind, payload, now + 900]).encode()
    data = win32crypt.CryptProtectData(
        payload, "Torrenter source", str(folder).encode(), None, None, 1
    )
    with (folder / (key + ".source")).open("xb") as stream:
        stream.write(data)
    return key


def resolve(profile, kind, key):
    import win32crypt

    if not ID.fullmatch(key):
        raise TorrentError("Invalid source reference.")
    folder = directory(profile)
    try:
        _, plain = win32crypt.CryptUnprotectData(
            (folder / (key + ".source")).read_bytes(),
            str(folder).encode(),
            None,
            None,
            1,
        )
        expected, links, expires = json.loads(plain)
        if expected == kind and expires >= time.time():
            return links
    except Exception:
        pass
    raise TorrentError(
        "This source reference is unavailable, expired or belongs to a different account."
    )
