# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""One isolated activation. The service owns all peer connections and durable files."""

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml

# Carried Python can have an isolated ._pth file.
HERE = Path(__file__).resolve().parent
if __package__:
    from .activity import ActivityLog
    from .client import compact, installation, read_grant, request, session
    from .contract import DURABLE, ID, TorrentError, route, validated
    from .sources import resolve
else:
    sys.path.insert(0, str(HERE))
    from activity import ActivityLog
    from client import compact, installation, read_grant, request, session
    from contract import DURABLE, ID, TorrentError, route, validated
    from sources import resolve


def safe(value):
    return compact(value).replace("<", "\\u003c").replace(">", "\\u003e")


def emit(result):
    fields = {k: v for k, v in result.items() if k != "response_body"}
    body = safe(result.get("response_body", {}))
    lines = [
        k + ": " + (str(v) if isinstance(v, (int, bool)) else safe(str(v))[1:-1])
        for k, v in fields.items()
    ]
    logging.info(
        "INI_SECTION_TORRENTER<<<\n%s\n\n%s\n>>>END_SECTION_TORRENTER",
        "\n".join(lines),
        body,
    )
    # The chat result reader consumes the atomic result even if a log excerpt was truncated.
    tmp = HERE / ("result." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(safe(result), encoding="utf-8")
    tmp.replace(HERE / "torrenter-result.json")


def report_selected_bytes(snapshot):
    """A boundary piece can contain bytes belonging to unselected neighbouring files."""
    piece_bytes = snapshot.get("verified_bytes")
    selected = snapshot.get("selected_bytes")
    if (
        isinstance(piece_bytes, int)
        and isinstance(selected, int)
        and piece_bytes > selected
    ):
        snapshot["engine_verified_bytes"] = piece_bytes
        snapshot["verified_bytes"] = selected if snapshot.get("completed_at") else None


def save_receipt(path, record):
    tmp = path.with_suffix("." + uuid.uuid4().hex)
    tmp.write_text(compact(record), encoding="utf-8")
    tmp.replace(path)


def execute(action, params, profile):
    p = validated(action, params)
    key = p.get("operation_key")
    admitted = None
    if action in DURABLE:
        receipt = HERE / ".torrenter-receipt"
        fingerprint = hashlib.sha256(
            json.dumps(
                [installation(), profile, action, p],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if os.environ.get("AGENT_REANIMATED") == "1" and receipt.exists():
            previous = json.loads(receipt.read_text(encoding="utf-8"))
            if previous["fingerprint"] != fingerprint:
                raise TorrentError(
                    "The interrupted activation changed. Review and start a new action."
                )
            key = previous["key"]
            admitted = previous.get("operation_id")
        else:
            key = key or uuid.uuid4().hex
            save_receipt(receipt, {"fingerprint": fingerprint, "key": key})
    token = session(profile)
    method, path, body = route(action, p)
    if admitted:
        if not isinstance(admitted, str) or not ID.fullmatch(admitted):
            raise TorrentError("The saved operation receipt is invalid.")
        method, path, body = "GET", "operations/" + admitted, None
    elif action == "inspect" and "source_ref" in p:
        body = {"magnet": resolve(profile, "magnet", p["source_ref"])}
    elif action in ("set_trackers", "set_web_seeds"):
        body = {"urls": resolve(profile, action[4:], p["source_ref"])}
    deadline = time.monotonic() + p.get("wait_seconds", 10)
    try:
        while True:
            code, data = request(
                method, path, body, bearer=token, key=key, revision=p.get("revision")
            )
            if (
                action != "wait"
                or data.get("phase")
                in (
                    "completed",
                    "seeding",
                    "cancelled",
                    "failed",
                    "error",
                    "stopped",
                    "paused",
                )
                or time.monotonic() >= deadline
            ):
                break
            time.sleep(1)
    except TorrentError as exc:
        if key:
            raise TorrentError(str(exc) + " Operation key: " + key) from exc
        raise
    if key and code == 202:
        save_receipt(
            receipt,
            {
                "fingerprint": fingerprint,
                "key": key,
                "operation_id": data["operation_id"],
            },
        )
    if action in ("status", "wait", "statistics"):
        report_selected_bytes(data)
    elif action == "list":
        for snapshot in data.get("items", []):
            report_selected_bytes(snapshot)
    observed = "accepted" if code == 202 else "observed"
    result = {
        "action": action,
        "status": observed,
        "success": True,
        "response_body": data,
    }
    for name in (
        "job_id",
        "inspection_id",
        "operation_id",
        "preview_id",
        "revision",
        "phase",
        "lookup_state",
        "verified",
        "selected_bytes",
        "verified_bytes",
    ):
        if name in data or name in p:
            result[name] = data.get(name, p.get(name))
    if key:
        result["operation_key"] = key
    return result


def trigger_targets(names):
    import psutil

    for name in dict.fromkeys(names):
        if not isinstance(name, str) or not re.fullmatch(
            r"[a-z][a-z0-9_]*_[0-9]+", name
        ):
            raise TorrentError("Invalid downstream agent name.")
        directory = (HERE.parent / name).resolve()
        script = directory / (name.rsplit("_", 1)[0] + ".py")
        if directory.parent != HERE.parent or not script.is_file():
            raise TorrentError("Downstream agent is unavailable.")
        pid = directory / "agent.pid"
        while pid.exists():
            try:
                proc = psutil.Process(int(pid.read_text().strip()))
                if Path(proc.cwd()).resolve() != directory:
                    break
            except (ValueError, OSError, psutil.Error):
                break
            time.sleep(0.5)
        subprocess.Popen([sys.executable, str(script)], cwd=directory)


def describe_assets(profile, route, log, response=None):
    try:
        token = session(profile)
    except TorrentError as exc:
        if response and response.get("verified") and response.get("output_root"):
            log.publication(response)
        log.write(str(exc))
        return
    def read(path):
        try:
            return request("GET", path, bearer=token)[1]
        except TorrentError:
            return {}
    details = read(route + "/activity")
    if route.startswith("inspections/"):
        log.assets(details or response or read(route))
        return
    state = read(route)
    report_selected_bytes(state)
    publication = (response if response and "output_root" in response else None) or details.get("publication") or read(route + "/manifest")
    if not details:
        files = read(route + "/files").get("items", []) or publication.get("files", [])
        details = {"name":state.get("name"), "files":files, "publication":publication}
    log.assets(details)
    if not details.get("magnet"):
        log.write("The running Jobs version did not supply the full source magnet.")
    log.swarm(state, read(route + "/trackers").get("items"), read(route + "/web-seeds").get("items"),
              read(route + "/peers").get("items"))


def wait_for_publication(profile, result, log):
    job = result["job_id"]
    path = "torrents/" + job
    last = None
    token = session(profile)
    renewal = time.monotonic() + 220
    log.write("Waiting for verified output", "job_id: " + job)
    while True:
        if time.monotonic() >= renewal:
            token = session(profile)
            renewal = time.monotonic() + 220
        _, state = request("GET", path, bearer=token)
        report_selected_bytes(state)
        progress = (state["phase"], state.get("verified_bytes"), state.get("selected_bytes"))
        if progress != last:
            log.write(f"{log.now()}  {progress[0]}  {progress[1]} / {progress[2]} bytes"
                      f'  |  seeds={state.get("seeds")}  peers={state.get("peers")}  down={state.get("download_rate_bps")} B/s')
            last = progress
        if state.get("completed_at"):
            _, manifest = request("GET", path + "/manifest", bearer=token)
            if manifest.get("delivery_state") in ("failed", "unavailable"):
                raise TorrentError("The download is verified, but saving to Windows Downloads failed: "
                                   + str(manifest.get("delivery_error", "Unknown delivery error.")))
            if manifest.get("verified"):
                log.publication(manifest)
                result.update(status="completed", phase=state["phase"], verified=True)
                result["response_body"] = {**result["response_body"], "manifest": manifest}
                return
        if state["phase"] in {"cancelled", "stopped", "error", "failed"}:
            raise TorrentError("Download ended before verified publication. " + state["phase"] + " · " + job)
        time.sleep(2)


def main():
    logging.basicConfig(
        filename=HERE / (HERE.name + ".log"),
        level=logging.INFO,
        encoding="utf-8",
        format="%(asctime)s %(levelname)s %(message)s",
        filemode="a" if os.environ.get("AGENT_REANIMATED") == "1" else "w",
    )
    pid = HERE / "agent.pid"
    pid.write_text(str(os.getpid()))
    action, targets, wait, audit, result = "", [], False, None, {}
    try:
        config = yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8-sig"))
        targets = config.get("target_agents") or []
        action = config["action"]
        wait = action == "download" and config.get("wait_for_completion", False) is True
        profile = read_grant(HERE)
        audit = ActivityLog(HERE, action, wait, profile)
        params = config.get("arguments", {})
        if isinstance(params, str):
            params = json.loads(params)
        if action == "remove_job" and ID.fullmatch(str(params.get("job_id", ""))):
            describe_assets(profile, "torrents/" + params["job_id"], audit)
        try:
            result = execute(action, params, profile)
        except TorrentError:
            # Admission can be refused while the magnet is still finding peers.
            # Report its original source and any files already known without
            # resubmitting the mutation or hiding the reason Jobs refused it.
            if action == "download" and ID.fullmatch(str(params.get("inspection_id", ""))):
                describe_assets(profile, "inspections/" + params["inspection_id"], audit)
            raise
        if action != "remove_job" and result.get("job_id"):
            describe_assets(profile, "torrents/" + result["job_id"], audit, result.get("response_body"))
        elif result.get("inspection_id"):
            describe_assets(profile, "inspections/" + result["inspection_id"], audit, result.get("response_body"))
        if wait:
            wait_for_publication(profile, result, audit)
        elif action != "manifest" or not result.get("job_id"):
            audit.response(result.get("response_body", {}))
    except Exception as exc:
        message = (
            str(exc)
            if isinstance(exc, TorrentError)
            else "Invalid configuration or unavailable Windows integration."
        )
        result = {**result,
            "action": action
            if isinstance(action, str) and action.isidentifier()
            else "",
            "status": "failed",
            "success": False,
            "message": message,
        }
    try:
        if audit:
            audit.receipt(result)
        emit(result)
        if not wait or result["success"]:
            trigger_targets(targets)
        return 0 if result["success"] else 1
    finally:
        if pid.exists() and pid.read_text() == str(os.getpid()):
            pid.unlink()


if __name__ == "__main__":
    sys.exit(main())
