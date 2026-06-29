# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
ACP session store — Python port of OpenClaw's createFileSessionStore() +
createResetAwareSessionStore() in extensions/acpx/src/runtime.ts.

A "session" here is a long-lived ACP child-process binding that survives
across multiple turns. The store persists the binding so that, on Tlamatini
restart, an outstanding session can be re-bound to a fresh child process
(at the user's discretion — we do NOT auto-resurrect the child, but we
do remember the metadata).

Each session is a single JSON file under <state_dir>/<session_id>.json.
The "reset-aware" wrapper ignores stale on-disk records when the
caller has called mark_fresh(session_id) — this prevents a freshly-spawned
session from inheriting the previous session's transcript.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class AcpSessionRecord:
    """One row in the session store."""
    session_id: str           # uuid4 hex
    name: str                 # human-readable label
    agent_id: str             # registry key (claude, cursor, codex, ...)
    cwd: str                  # working directory the child was spawned in
    state_path: str           # absolute path to this record's JSON file
    transcript_path: str      # absolute path to the transcript .ndjson file
    pid: Optional[int]        # last-known child PID (None if never spawned or already exited)
    created_at: float         # epoch seconds
    last_active_at: float     # epoch seconds
    closed: bool = False      # True after acp_kill() or natural exit
    tags: List[str] = field(default_factory=list)


class FileSessionStore:
    """
    File-backed session store. Reset-aware: mark_fresh(session_id) makes
    load(session_id) return None until the next save() lands.

    Thread safety
    -------------
    Operations on this store are atomic at the file-system level (write
    via temp file + os.replace). Cross-process consistency is best-effort;
    this is a single-user local tool, not a multi-tenant database.
    """

    def __init__(self, state_dir: Path | str):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._fresh: Set[str] = set()

    # ── Reset-aware semantics ─────────────────────────────────────────
    def mark_fresh(self, session_id: str) -> None:
        sid = (session_id or "").strip()
        if sid:
            self._fresh.add(sid)

    def _consume_fresh(self, session_id: str) -> bool:
        return session_id in self._fresh

    # ── CRUD ──────────────────────────────────────────────────────────
    def _path_for(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        if not safe:
            raise ValueError("invalid session id")
        return self.state_dir / f"{safe}.json"

    def load(self, session_id: str) -> Optional[AcpSessionRecord]:
        sid = (session_id or "").strip()
        if not sid:
            return None
        if self._consume_fresh(sid):
            # Reset-aware: ignore any stale on-disk record for this id.
            return None
        try:
            path = self._path_for(sid)
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            return AcpSessionRecord(**data)
        except Exception:
            logger.exception("[ACPX session_store] failed to load %s", sid)
            return None

    def save(self, record: AcpSessionRecord) -> None:
        try:
            path = self._path_for(record.session_id)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
            os.replace(tmp, path)
            sid = record.session_id.strip()
            if record.name and sid in self._fresh:
                # Once a fresh session has been saved, drop the fresh marker.
                self._fresh.discard(sid)
        except Exception:
            logger.exception("[ACPX session_store] failed to save %s", record.session_id)

    def delete(self, session_id: str) -> None:
        try:
            path = self._path_for(session_id)
            if path.exists():
                path.unlink()
        except Exception:
            logger.exception("[ACPX session_store] failed to delete %s", session_id)

    def list_all(self) -> List[AcpSessionRecord]:
        out: List[AcpSessionRecord] = []
        try:
            for entry in sorted(self.state_dir.glob("*.json")):
                try:
                    data = json.loads(entry.read_text(encoding="utf-8"))
                    out.append(AcpSessionRecord(**data))
                except Exception:
                    logger.warning("[ACPX session_store] skip malformed %s", entry)
        except Exception:
            logger.exception("[ACPX session_store] list_all failed")
        return out


def make_session_id() -> str:
    import uuid
    return uuid.uuid4().hex


def now_epoch() -> float:
    return time.time()
