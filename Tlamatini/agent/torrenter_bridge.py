# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Only authenticated server launch sites can bind a Jobs profile to a pool."""

import re
from django.core.exceptions import PermissionDenied
import json
from pathlib import Path

from .agents.torrenter.client import scope_grant
from .agents.torrenter.contract import TorrentError
from .models import TorrenterProfile


def profile_for(user_id):
    if not user_id:
        raise TorrentError("Sign in to Tlamatini to use Torrenter.")
    profile, _ = TorrenterProfile.objects.get_or_create(user_id=user_id)
    return str(profile.account)


def canvas_config(config):
    from .agents.torrenter.contract import validated

    if set(config) - {"action", "arguments", "wait_for_completion", "source_agents", "target_agents"}:
        raise TorrentError(
            "Torrenter accepts action, arguments and canvas connections only."
        )
    raw = config.get("arguments", {})
    if type(config.setdefault("wait_for_completion", False)) is not bool:
        raise TorrentError("Wait for complete download must be Yes or No.")
    args = json.loads(raw) if isinstance(raw, str) else raw
    config["arguments"] = json.dumps(
        validated(config["action"], args), separators=(",", ":")
    )
    return config


_MAGNET = re.compile(r"""magnet:\?[^\s<>"'\x60]+""", re.IGNORECASE)


def stage_chat_magnets(user_id, message):
    from .agents.torrenter.sources import stage

    profile = profile_for(user_id)
    matches = list(_MAGNET.finditer(message))
    if len(matches) > 8:
        raise TorrentError("Use up to eight magnets in one message.")

    def replace(match):
        ref = stage(profile, "magnet", match.group())
        return "[Torrenter source_ref=" + ref + " for action inspect]"

    return _MAGNET.sub(replace, message)


def stage_search_magnet(user_id, result, *, supervisor=False):
    """Keep the discovery hints from a get_torrent result out of the model context."""
    from .agents.torrenter.sources import stage

    if not isinstance(result, str) or "magnet:?" not in result.lower():
        return result
    text = result
    if supervisor:
        envelope = json.loads(text)
        if not envelope.get("ok"):
            raise TorrentError("Torrent search did not return a usable source.")
        text = envelope.get("result")
    # FastMCP can return the same URI twice: once as text and once as JSON
    # structuredContent. Stage one full URI, including all trackers and web seeds.
    if isinstance(text, str):
        plain, _, structured = text.partition("structuredContent:\n")
        magnet = plain.strip() or json.loads(structured)
        if isinstance(magnet, str) and magnet.startswith("magnet:?") and _MAGNET.fullmatch(magnet):
            ref = stage(profile_for(user_id), "magnet", magnet)
            return json.dumps({
                "torrenter_request": {"action": "inspect", "arguments": {"source_ref": ref}},
                "next_step": "Call chat_agent_torrenter with torrenter_request. Poll inspection until ready, "
                             "then submit only file IDs from its reviewed file list.",
            })
    raise TorrentError("Torrent search did not return a usable source.")


def protect_pool(request, pool, *, claim=False):
    """Bind a canvas containing Torrenter to its authenticated creator until the pool is cleared."""
    path = Path(pool)
    marker = path / ".torrenter-owner"
    user_id = (
        str(request.user.pk)
        if getattr(getattr(request, "user", None), "is_authenticated", False)
        else ""
    )
    if claim:
        if not user_id:
            raise PermissionDenied("Sign in to use Torrenter.")
        path.mkdir(parents=True, exist_ok=True)
        try:
            with marker.open("x", encoding="ascii") as out:
                out.write(user_id)
        except FileExistsError:
            pass
    try:
        owner = marker.read_text(encoding="ascii")
    except FileNotFoundError:
        return
    if not user_id or owner != user_id:
        raise PermissionDenied("This flow belongs to another Tlamatini account.")


def flow_env(request, pool, env):
    env.pop("TLAMATINI_TORRENTER_GRANT", None)
    if request.user.is_authenticated and any(
        Path(pool).glob("torrenter_*/torrenter.py")
    ):
        protect_pool(request, pool, claim=True)
        env["TLAMATINI_TORRENTER_GRANT"] = scope_grant(profile_for(request.user.pk), pool)
    return env
