# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Closed action vocabulary shared by the typed tool, flow nodes and Jobs adapter."""

import re
from urllib.parse import urlencode


class TorrentError(ValueError):
    pass


TRANSITIONS = "pause resume stop start cancel recheck reseed move".split()
DETAILS = "files peers trackers web_seeds statistics manifest".split()
OPTIONS = "category tags download_limit upload_limit queue_position resume_on_boot seed_after_completion".split()
READ = {
    "capabilities": "capabilities",
    "list": "torrents",
    "settings": "settings",
    "categories": "categories",
    "tags": "tags",
    "events": "events",
    "totals": "statistics",
}
# Required and optional action arguments. No transport, account, path or approval override.
FIELDS = {name: ("", "") for name in READ}
FIELDS.update(
    {
        "list": (
            "",
            "limit cursor phase desired search category tag tracker sort direction",
        ),
        "events": ("", "after"),
        "inspect": ("", "info_hash source_ref"),
        "inspection": ("inspection_id", ""),
        "download": (
            "inspection_id metadata_revision selected_file_ids destination_root_id",
            "priorities resume_on_boot seed_after_completion",
        ),
        "status": ("job_id", ""),
        "wait": ("job_id", "wait_seconds"),
        "operation": ("operation_id", ""),
        "remove_job": ("job_id revision", ""),
        "delete_preview": ("job_id revision", ""),
        "delete_content": ("preview_id revision", ""),
        "set_trackers": ("job_id revision source_ref", ""),
        "set_web_seeds": ("job_id revision source_ref", ""),
        "select": ("job_id revision selected_file_ids", "priorities"),
        "update": ("job_id revision", " ".join(OPTIONS)),
        "update_settings": (
            "revision",
            "download_limit upload_limit resume_on_boot seed_after_completion",
        ),
        "batch": ("transition jobs", ""),
        "label": ("collection change name", "new_name"),
    }
)
FIELDS.update({name: ("job_id revision", "") for name in TRANSITIONS})
FIELDS["move"] = ("job_id revision destination_root_id", "")
FIELDS.update({name: ("job_id", "") for name in DETAILS})
DURABLE = set(TRANSITIONS) | {
    "download",
    "select",
    "update",
    "update_settings",
    "label",
    "batch",
    "remove_job",
    "delete_content",
    "set_trackers",
    "set_web_seeds",
}
ID = re.compile(r"[0-9a-f]{32}")


def check(ok, message):
    if not ok:
        raise TorrentError(message)


def validated(action, arguments):
    check(
        isinstance(action, str) and action in FIELDS,
        "Choose a documented Torrenter action.",
    )
    check(isinstance(arguments, dict), "Arguments must be a JSON object.")
    req, opt = (set(v.split()) for v in FIELDS[action])
    allowed = req | opt | ({"operation_key"} if action in DURABLE else set())
    check(
        set(arguments) <= allowed and req <= set(arguments),
        "Fields for "
        + action
        + ": required ["
        + ", ".join(sorted(req))
        + "], optional ["
        + ", ".join(sorted(allowed - req))
        + "].",
    )
    a = dict(arguments)
    for k, v in a.items():
        if k in (
            "job_id",
            "inspection_id",
            "operation_id",
            "preview_id",
            "operation_key",
            "source_ref",
        ):
            check(
                isinstance(v, str) and ID.fullmatch(v),
                k + " must be 32 lowercase hex digits.",
            )
        elif k == "info_hash":
            check(
                isinstance(v, str) and re.fullmatch(r"[a-fA-F0-9]{40}", v),
                "Use a v1 info hash or stage the magnet in Torrenter Sources.",
            )
        elif k in ("resume_on_boot", "seed_after_completion"):
            check(type(v) is bool, k + " must be true or false.")
        elif k == "selected_file_ids":
            check(
                isinstance(v, list)
                and 0 < len(v) <= 4096
                and all(type(i) is int and 0 <= i < 4096 for i in v)
                and len(v) == len(set(v)),
                "Select unique reviewed file IDs.",
            )
        elif k == "priorities":
            selection = a.get("selected_file_ids")
            check(
                isinstance(selection, list),
                "Select file IDs before assigning priorities.",
            )
            selected_keys = {str(n) for n in selection}
            check(
                isinstance(v, dict)
                and all(
                    str(i) in selected_keys and type(p) is int and 1 <= p <= 7
                    for i, p in v.items()
                ),
                "Priorities must be 1–7 for selected files.",
            )
        elif k == "jobs":
            check(isinstance(v, list) and 0 < len(v) <= 100, "Select 1–100 jobs.")
            for entry in v:
                check(
                    isinstance(entry, dict) and set(entry) == {"job_id", "revision"},
                    "Batch items require a job_id and revision.",
                )
                validated("stop", entry)
            check(
                len({item["job_id"] for item in v}) == len(v),
                "Use each job ID once per batch.",
            )
        elif k == "tags":
            check(
                isinstance(v, list)
                and len(v) <= 16
                and all(isinstance(t, str) and len(t) <= 80 for t in v),
                "Invalid tags.",
            )
        elif k in (
            "limit",
            "cursor",
            "after",
            "wait_seconds",
            "revision",
            "metadata_revision",
            "queue_position",
            "download_limit",
            "upload_limit",
        ):
            lower = 1 if k in ("limit", "revision", "metadata_revision") else 0
            upper = {
                "limit": 250,
                "wait_seconds": 30,
                "queue_position": 9999,
                "download_limit": 2**30,
                "upload_limit": 2**30,
            }.get(k, 2**53 - 1)
            check(type(v) is int and lower <= v <= upper, "Invalid " + k + ".")
        else:
            check(
                isinstance(v, str)
                and len(v) <= (80 if k in ("category", "name", "new_name") else 160)
                and (len(v) > 0 or k == "category")
                and all(ord(c) >= 32 for c in v),
                "Invalid " + k + ".",
            )
    if any(
        isinstance(v, str) and ("magnet:?" in v.lower() or "://" in v)
        for v in a.values()
    ):
        raise TorrentError("Use an opaque source reference for network addresses.")
    choices = {
        "destination_root_id": ("downloads", "archive"),
        "direction": ("asc", "desc"),
        "sort": (
            "name",
            "phase",
            "selected_bytes",
            "verified_bytes",
            "download_rate_bps",
            "upload_rate_bps",
            "queue_position",
        ),
        "collection": ("categories", "tags"),
        "change": ("create", "rename", "remove"),
        "transition": ("pause", "resume", "start", "stop"),
    }
    for k, values in choices.items():
        check(k not in a or a[k] in values, "Unsupported " + k + ".")
    if action == "inspect":
        check(
            ("info_hash" in a) != ("source_ref" in a),
            "Choose either info_hash or a staged source_ref.",
        )
    if action == "label":
        check(
            ("new_name" in a) == (a["change"] == "rename"),
            "Only a rename requires new_name.",
        )
    if action in ("update", "update_settings"):
        check(bool(opt & set(a)), "Choose at least one setting to update.")
    return a


def route(action, a):
    body = {
        k: v for k, v in a.items() if k not in ("operation_key", "revision", "job_id")
    }
    job = "torrents/" + a.get("job_id", "")
    if action in READ:
        return "GET", READ[action] + ("?" + urlencode(body) if body else ""), None
    if action == "inspect":
        return (
            "POST",
            "inspections",
            {"magnet": "magnet:?xt=urn:btih:" + a["info_hash"]}
            if "info_hash" in a
            else {},
        )
    if action in ("operation", "inspection"):
        return "GET", action + "s/" + a[action + "_id"], None
    if action == "download":
        return "POST", "torrents", body
    if action in ("status", "wait"):
        return "GET", job, None
    if action in DETAILS:
        return "GET", job + "/" + action.replace("_", "-"), None
    if action in TRANSITIONS:
        return "POST", job + "/actions", dict(body, action=action)
    if action in ("select", "update", "update_settings"):
        return (
            "PATCH",
            {"select": job + "/files", "update": job, "update_settings": "settings"}[
                action
            ],
            body,
        )
    if action in ("set_trackers", "set_web_seeds"):
        return "PATCH", job + "/" + action[4:].replace("_", "-"), body
    if action == "remove_job":
        return "DELETE", job, None
    if action == "delete_preview":
        return "POST", "content-deletion-previews", {"job_id": a["job_id"]}
    if action == "delete_content":
        return "POST", "content-deletions", body
    if action == "batch":
        return (
            "POST",
            "batch-operations",
            {"action": a["transition"], "jobs": a["jobs"]},
        )
    if action == "label":
        return (
            {"create": "POST", "rename": "PATCH", "remove": "DELETE"}[a["change"]],
            a["collection"],
            {k: a[k] for k in ("name", "new_name") if k in a},
        )
    raise TorrentError("Unknown action.")
