# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Human-readable operator log. Its private source URIs never enter the model result."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import uuid


def record_directory(profile, pool, node):
    if __package__:
        from .client import private_directory
    else:
        from client import private_directory
    # Pool folders are disposable. Their identity, scoped by the Django account,
    # identifies the canvas node without accepting a browser-supplied file path.
    key = hashlib.sha256((Path(pool).name + "/" + node).encode()).hexdigest()
    return private_directory(profile) / "activity" / key


def latest_record(profile, pool, node):
    folder = record_directory(profile, pool, node)
    try:
        ident = (folder / "latest").read_text(encoding="ascii")
        return folder / (uuid.UUID(hex=ident).hex + ".log")
    except (FileNotFoundError, ValueError):
        return None


class ActivityLog:
    def __init__(self, directory, action, wait, profile=None):
        self.path = directory / (directory.name + ".activity.log")
        folder = None
        if profile and directory.parent.name != "_chat_runs_":
            folder = record_directory(profile, directory.parent, directory.name)
            folder.mkdir(parents=True, exist_ok=True)
            self.path = folder / (uuid.uuid4().hex + ".log")
        self.path.write_text("", encoding="utf-8")
        self.write("TORRENTER", f"Action: {action}", "Started (UTC): " + self.now(),
                   "Wait for complete download: " + ("Yes" if wait else "No"))
        if folder:
            pointer = self.path.with_suffix(".pointer")
            pointer.write_text(self.path.stem, encoding="ascii")
            pointer.replace(folder / "latest")

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def write(self, *lines):
        with self.path.open("a", encoding="utf-8") as stream:
            for line in lines:
                print(line, file=stream)

    def assets(self, details):
        self.write("", "TORRENT", details.get("name") or "Waiting for metadata")
        files = details.get("files") or []
        published = details.get("publication", {})
        if published.get("delivery_state"):
            self.write("Delivery: " + published["delivery_state"])
            if published.get("saved_to"):
                label = "content_generated: " if published.get("delivery_location") == "content_generated" else "Windows Downloads destination: "
                self.write(label + published["saved_to"])
            if published.get("downloads_error"):
                self.write("Windows Downloads: " + published["downloads_error"])
            if published.get("delivery_error"):
                self.write("Delivery error: " + published["delivery_error"])
        verified = {f["id"]: f for f in published.get("files", [])}
        self.write("FILES", f"Files in metadata: {len(files)}")
        for item in files:
            state = ("selected" if item["selected"] else "excluded") if "selected" in item else "available for selection"
            self.write(f'[{item["id"]}] {item["path"]}', f'    {item["size"]:,} bytes · {state}')
            verified_file = verified.get(item["id"])
            if verified_file and published.get("output_root") and published.get("verified"):
                self.write("    Saved file: " + str(Path(published["output_root"]) / verified_file["path"]),
                           "    SHA-256: " + verified_file["sha256"])
        if details.get("magnet"):
            title = "Original magnet link" if details["source_kind"] == "magnet" else "Magnet generated from the uploaded .torrent"
            self.write("", title, details["magnet"])
        self.write("")

    def publication(self, manifest):
        if not manifest.get("verified"):
            self.write("", "OUTPUT NOT YET SAVED", manifest.get("delivery_error") or "Waiting for verified delivery.")
            return
        self.write("", "VERIFIED OUTPUT")
        for item in manifest["files"]:
            self.write(str(Path(manifest["output_root"]) / item["path"]),
                       f'    {item["size"]:,} bytes', "    SHA-256: " + item["sha256"])

    def swarm(self, state, trackers, web_seeds, peers):
        def value(key, unit=""):
            raw = state.get(key)
            return "not reported" if raw is None else f"{raw}{unit}"

        self.write("", "TRANSFER / SWARM", "Observed (UTC): " + self.now(),
                   "Job: " + value("job_id"), "Info hash: " + value("info_hash"),
                   "State: " + value("phase") + " / " + value("desired_state"),
                   "Seeds connected: " + value("seeds"), "Seeds reported by swarm: " + value("known_seeds"),
                   "Peers connected: " + value("peers"), "Leechers reported by swarm: " + value("known_peers"),
                   "Availability: " + value("availability"), "Share ratio: " + value("ratio"),
                   "Download rate: " + value("download_rate_bps", " B/s"), "Upload rate: " + value("upload_rate_bps", " B/s"),
                   "Total size: " + value("total_bytes", " bytes"), "Selected: " + value("selected_bytes", " bytes"),
                   "Verified: " + value("verified_bytes", " bytes"), "ETA: " + value("eta_seconds", " s"),
                   "Destination: " + value("destination_root_id"))
        if state.get("completed_at"):
            stamp = datetime.fromtimestamp(state["completed_at"], timezone.utc)
            self.write("Completed (UTC): " + stamp.isoformat(timespec="seconds"))
        for heading, entries in (("Trackers", trackers), ("HTTP seeds", web_seeds), ("Connected peers (up to 100)", peers)):
            if entries is None:
                self.write(heading + ": not reported")
            else:
                self.write(f"{heading}: {len(entries)}")
                for entry in entries:
                    self.write("    " + " · ".join(f"{key}={val}" for key, val in entry.items()))

    def receipt(self, result):
        self.write("", "RESULT", "Status: " + str(result["status"]))
        for key in ("job_id", "operation_id", "inspection_id", "operation_key", "phase", "lookup_state", "message"):
            if key in result:
                self.write(f"{key}: {result[key]}")
        self.write("Finished (UTC): " + self.now())

    def response(self, data):
        self.write(json.dumps(data, indent=2, ensure_ascii=False))

