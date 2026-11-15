# Tlamatini — Created by Angela López Mendoza · @angelahack1
"""Account-bound downloads of the exact artifacts linked by a saved reply.

Tickets carry no file bytes. Every redemption rechecks consent, the owning
message, the exact reference and the original content digest. No caller path,
URL, database row or executable is accepted as download authority.
"""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from io import BytesIO
import hashlib
import ipaddress
import mimetypes
import os
from pathlib import Path
import re
import secrets
import stat
from urllib.parse import unquote, urlsplit

from django.core import signing
from django.http import FileResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TICKET_SECONDS = 30 * 60
SALT = "tlamatini.rc.response-file.v1"
CONTENT_SALT = "tlamatini.rc.response-content.v1"
_SIGNING_KEY = secrets.token_hex(32)
MAX_CONTENT_BYTES = 8 * 1024 * 1024
_CANVAS = re.compile(r'''\A\s*loadCanvas\(\s*(["'])([^"'\r\n]{1,240})\1\s*\)\s*;?\s*\Z''')
_EXTENSIONS = {"python": ".py", "py": ".py", "javascript": ".js", "js": ".js",
               "typescript": ".ts", "ts": ".ts", "html": ".html", "css": ".css",
               "json": ".json", "markdown": ".md", "md": ".md", "xml": ".xml",
               "sql": ".sql", "csv": ".csv", "yaml": ".yaml", "yml": ".yml",
               "powershell": ".ps1", "ps1": ".ps1", "bash": ".sh", "sh": ".sh",
               "c": ".c", "cpp": ".cpp", "c++": ".cpp", "csharp": ".cs",
               "java": ".java", "text": ".txt", "plaintext": ".txt"}


class FileFault(Exception):
    def __init__(self, code, status=403):
        self.code, self.status = code, status
        super().__init__(code)


def _filename(name, language="", *, infer_extension=True):
    name = str(name)
    if not name or len(name) > 240 or name in {".", ".."} or any(ord(c) < 32 or c in '/\\<>:"|?*' for c in name):
        raise FileFault("invalid_filename")
    if infer_extension and not Path(name).suffix:
        name += _EXTENSIONS.get(str(language).strip().lower(), ".txt")
    if len(name) > 240:
        raise FileFault("invalid_filename")
    return name


def _reference(attrs):
    attrs = dict(attrs)
    action = attrs.get("onclick") or ""
    match = _CANVAS.fullmatch(action)
    if match:
        return {"kind": "canvas", "value": match[2]}
    href = attrs.get("href") or ""
    if href.lower().startswith("file:"):
        parsed = urlsplit(href)
        if parsed.netloc not in {"", "localhost"} or parsed.query or parsed.fragment:
            return None
        path = unquote(parsed.path)
        if re.match(r"^/[a-zA-Z]:/", path):
            path = path[1:]
        if not path or len(path) > 4096 or "\x00" in path or not os.path.isabs(path):
            return None
        return {"kind": "file", "value": path}
    return None


class _References(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.references = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and (reference := _reference(attrs)) is not None:
            self.references.append(reference)


def _references(html):
    parser = _References()
    parser.feed(html)
    parser.close()
    return parser.references


def _profile(user_id):
    from .models import RemoteControllerProfile
    profile = RemoteControllerProfile.objects.select_related("user").filter(user_id=user_id).first()
    if not profile or not profile.enabled or not profile.binding_id or not profile.user.is_active:
        raise FileFault("account_unavailable")
    return profile


def _message(user_id, message_id):
    from .models import AgentMessage
    row = AgentMessage.objects.filter(pk=message_id, conversation_user_id=user_id,
                                      user__username="Tlamatini").first()
    if row is None:
        raise FileFault("message_unavailable", 404)
    return row


def _check_file_path(value):
    from . import path_guard
    raw = Path(os.path.abspath(value))
    # Reject every reparse component before resolving; realpath alone would
    # erase evidence of a junction/symlink selected in the response.
    for component in (raw, *raw.parents):
        try:
            item = component.lstat()
        except OSError as exc:
            raise FileFault("file_unavailable", 404) from exc
        if stat.S_ISLNK(item.st_mode) or getattr(item, "st_file_attributes", 0) & 0x400:
            raise FileFault("file_forbidden")
    resolved = path_guard.resolve_runtime_agent_path(str(raw), must_exist=True, expect_file=True)
    if not resolved or os.path.normcase(os.path.abspath(resolved)) != os.path.normcase(str(raw)):
        raise FileFault("file_forbidden")
    return raw


def _artifact(reference, expected=None):
    if reference["kind"] == "canvas":
        from .models import LLMProgram, LLMSnippet
        name = reference["value"]
        if expected is not None:
            key = expected.get("key", "")
            match = re.fullmatch(r"(program|snippet):([1-9][0-9]*)", key)
            if match is None:
                raise FileFault("invalid_ticket")
            if match[1] == "program":
                row = LLMProgram.objects.filter(pk=int(match[2]), programName=name).first()
                if row is None:
                    raise FileFault("file_unavailable", 404)
                content, language = row.programContent, row.programLanguage
            else:
                row = LLMSnippet.objects.filter(pk=int(match[2]), snippetName=name).first()
                if row is None:
                    raise FileFault("file_unavailable", 404)
                content, language = row.snippetContent, row.snippetLanguage
        else:
            row = LLMProgram.objects.filter(programName=name).order_by("-idProgram").first()
            if row is not None:
                key, content, language = "program:" + str(row.pk), row.programContent, row.programLanguage
            else:
                row = LLMSnippet.objects.filter(snippetName=name).order_by("-idSnippet").first()
                if row is None:
                    raise FileFault("file_unavailable", 404)
                key, content, language = "snippet:" + str(row.pk), row.snippetContent, row.snippetLanguage
        data = content.encode("utf-8")
        filename = _filename(name, language)
    elif reference["kind"] == "file":
        path = _check_file_path(reference["value"])
        filename, key = _filename(path.name, infer_extension=False), str(path)
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise FileFault("file_forbidden")
            if before.st_size > MAX_FILE_BYTES:
                raise FileFault("file_too_large", 413)
            data = stream.read(MAX_FILE_BYTES + 1)
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise FileFault("file_changed", 409)
        _check_file_path(reference["value"])
    else:
        raise FileFault("invalid_ticket")
    if len(data) > MAX_FILE_BYTES:
        raise FileFault("file_too_large", 413)
    digest = hashlib.sha256(data).hexdigest()
    metadata = {"key": key, "name": filename, "size": len(data), "sha256": digest}
    if expected is not None and metadata != expected:
        raise FileFault("file_changed", 409)
    return metadata, data


def _owned_artifact(row, reference):
    # Only the real parser/tool pipeline can write this persisted manifest.
    # Model-authored HTML, a guessed global artifact name and a file: URL
    # are display content and never create read authority.
    for item in row.response_files or []:
        if isinstance(item, dict) and item.get("reference") == reference:
            artifact = item.get("artifact")
            if (isinstance(artifact, dict) and set(artifact) == {"key", "name", "size", "sha256"}
                    and isinstance(artifact["key"], str) and isinstance(artifact["name"], str)
                    and type(artifact["size"]) is int and 0 <= artifact["size"] < 2 ** 63
                    and isinstance(artifact["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])):
                return artifact
            raise FileFault("artifact_unavailable")
    raise FileFault("artifact_not_owned")


def _issue(profile, row, reference):
    expected = _owned_artifact(row, reference)
    metadata, _ = _artifact(reference, expected)
    ticket = signing.dumps({"v": 1, "user": profile.user_id, "account": profile.account.hex,
                            "binding": profile.binding_id, "message": row.pk,
                            "reference": reference, "artifact": metadata}, key=_SIGNING_KEY, salt=SALT, compress=True)
    if len(ticket) > 4096:
        raise FileFault("invalid_ticket")
    return ticket, metadata["name"]


class _DownloadLinks(HTMLParser):
    def __init__(self, issue, spanish):
        super().__init__(convert_charrefs=False)
        self.issue = issue
        self.spanish = spanish
        self.parts = []
        self.skipping = False

    def handle_starttag(self, tag, attrs):
        if self.skipping:
            return
        reference = _reference(attrs) if tag == "a" else None
        if reference is None:
            self.parts.append(self.get_starttag_text())
            return
        try:
            token, name = self.issue(reference)
            label = ("Guardar archivo: " if self.spanish else "Save file: ") + name
            self.parts.append('<a href="#" data-rc-file="' + escape(token, quote=True)
                              + '" data-rc-filename="' + escape(name, quote=True)
                              + '">' + escape(label) + '</a>')
        except (FileFault, OSError, ValueError):
            label = "Archivo no disponible: vuelve a pedir a Tlamatini que lo genere" if self.spanish else "File unavailable: ask Tlamatini to generate it again"
            self.parts.append('<span class="rc-file-unavailable">' + label + '</span>')
        self.skipping = True

    def handle_endtag(self, tag):
        if self.skipping:
            if tag == "a":
                self.skipping = False
            return
        self.parts.append("</" + tag + ">")

    def handle_startendtag(self, tag, attrs):
        if not self.skipping:
            self.parts.append(self.get_starttag_text())

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)

    def handle_entityref(self, name):
        self.handle_data("&" + name + ";")

    def handle_charref(self, name):
        self.handle_data("&#" + name + ";")

    def handle_comment(self, data):
        self.handle_data("<!--" + data + "-->")

    def handle_decl(self, decl):
        self.handle_data("<!" + decl + ">")


def render_response(user_id, message_id, html, *, row=None, profile=None):
    """Keep canonical HTML and add downloads only from its trusted manifest."""
    from .remote_controller_bridge import EDITION
    references = _references(html)
    if not message_id and not references:
        return html
    manifest = []
    try:
        profile = profile or _profile(user_id)
        row = row or _message(user_id, message_id)
        if row.message != html or row.conversation_user_id != user_id:
            raise FileFault("message_mismatch")
        manifest = row.response_files or []
        issue = lambda reference: _issue(profile, row, reference)
    except FileFault:
        def issue(_reference):
            raise FileFault("message_unavailable")
    parser = _DownloadLinks(issue, EDITION == "spanish")
    parser.feed(html)
    parser.close()
    rendered = "".join(parser.parts)
    # Actual successful tool outputs need a discoverable download even when
    # the prose mentions a path without producing an HTML link.
    additions = []
    for item in manifest:
        reference = item.get("reference") if isinstance(item, dict) else None
        if not reference or reference in references:
            continue
        try:
            token, name = issue(reference)
            label = ("Guardar archivo: " if EDITION == "spanish" else "Save file: ") + name
            additions.append('<a href="#" data-rc-file="' + escape(token, quote=True)
                             + '" data-rc-filename="' + escape(name, quote=True)
                             + '">' + escape(label) + '</a>')
        except (FileFault, OSError, ValueError):
            continue
    if additions:
        rendered += '<div class="rc-response-files">' + '<br>'.join(additions) + '</div>'
    return rendered


@never_cache
@require_http_methods(["GET"])
def download(request):
    """Redeem an account-scoped file capability through the RC loopback proxy."""
    try:
        try:
            local = ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")).is_loopback
        except ValueError:
            local = False
        if not local or request.META.get("HTTP_SEC_FETCH_SITE") == "cross-site":
            raise FileFault("file_forbidden")
        ticket = request.GET.get("ticket", "")
        if set(request.GET) != {"ticket"} or len(request.GET.getlist("ticket")) != 1 or not 1 <= len(ticket) <= 4096:
            raise FileFault("invalid_ticket", 400)
        try:
            grant = signing.loads(ticket, key=_SIGNING_KEY, salt=SALT, max_age=MAX_TICKET_SECONDS, fallback_keys=[])
        except signing.SignatureExpired as exc:
            raise FileFault("download_expired", 410) from exc
        except signing.BadSignature as exc:
            raise FileFault("invalid_ticket") from exc
        if not isinstance(grant, dict) or grant.get("v") != 1:
            raise FileFault("invalid_ticket")
        profile = _profile(grant["user"])
        if (profile.account.hex != grant["account"] or profile.binding_id != grant["binding"]
                or request.META.get("HTTP_X_TLACHIHUANI_BINDING") != profile.binding_id):
            raise FileFault("account_mismatch")
        row = _message(profile.user_id, grant["message"])
        expected = _owned_artifact(row, grant["reference"])
        if expected != grant["artifact"]:
            raise FileFault("file_changed", 409)
        metadata, data = _artifact(grant["reference"], expected)
        response = FileResponse(BytesIO(data), as_attachment=True, filename=metadata["name"],
                                content_type=mimetypes.guess_type(metadata["name"])[0] or "application/octet-stream")
        response["Content-Length"] = str(len(data))
        response["X-Content-SHA256"] = metadata["sha256"]
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "no-store, private"
        return response
    except FileFault as error:
        return JsonResponse({"error": {"code": error.code,
                            "message": "This file cannot be downloaded. Reload the conversation and try again."}}, status=error.status)
    except (KeyError, TypeError, ValueError, OSError):
        return JsonResponse({"error": {"code": "file_unavailable", "message": "This file is no longer available."}}, status=404)


@never_cache
@require_http_methods(["GET"])
def mobile_download(request):
    """Save a canvas artifact linked in this signed-in account's saved reply."""
    try:
        try:
            local = ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")).is_loopback
        except ValueError:
            local = False
        if not local or not request.user.is_authenticated or not request.user.is_active:
            raise FileFault("file_forbidden")
        if set(request.GET) != {"message_id", "name"} or any(len(request.GET.getlist(key)) != 1 for key in request.GET):
            raise FileFault("invalid_request", 400)
        name = request.GET.get("name", "")
        if not name or len(name) > 240:
            raise FileFault("invalid_request", 400)
        message_id = int(request.GET.get("message_id", ""))
        profile = _profile(request.user.pk)
        row = _message(profile.user_id, message_id)
        reference = {"kind": "canvas", "value": name}
        expected = _owned_artifact(row, reference)
        metadata, data = _artifact(reference, expected)
        response = FileResponse(BytesIO(data), as_attachment=True, filename=metadata["name"],
                                content_type=mimetypes.guess_type(metadata["name"])[0] or "application/octet-stream")
        response["Content-Length"] = str(len(data))
        response["X-Content-SHA256"] = metadata["sha256"]
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "no-store, private"
        return response
    except FileFault as error:
        return JsonResponse({"error": {"code": error.code, "message": "This file cannot be downloaded."}}, status=error.status)
    except (ValueError, OSError):
        return JsonResponse({"error": {"code": "file_unavailable", "message": "This file is no longer available."}}, status=404)


def content_ticket(user_id, message_id, html, *, profile=None):
    """A bounded reference to a saved response; redemption rechecks ownership.

    Signing uses a fresh private process key, never a shipped/default Django
    SECRET_KEY. Restarting the application invalidates outstanding tickets.
    """
    if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
        return None
    profile = profile or _profile(user_id)
    return signing.dumps({"v": 1, "user": user_id, "message": message_id,
                          "account": profile.account.hex, "binding": profile.binding_id,
                          "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest()},
                         key=_SIGNING_KEY, salt=CONTENT_SALT, compress=True)


@never_cache
@require_http_methods(["GET"])
def response_content(request):
    """Deliver complete saved HTML when it is too large for native receipts."""
    try:
        try:
            local = ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")).is_loopback
        except ValueError:
            local = False
        if not local or request.META.get("HTTP_SEC_FETCH_SITE") == "cross-site":
            raise FileFault("file_forbidden")
        ticket = request.GET.get("ticket", "")
        if set(request.GET) != {"ticket"} or len(request.GET.getlist("ticket")) != 1 or not 1 <= len(ticket) <= 4096:
            raise FileFault("invalid_ticket", 400)
        try:
            grant = signing.loads(ticket, key=_SIGNING_KEY, salt=CONTENT_SALT,
                                  max_age=MAX_TICKET_SECONDS, fallback_keys=[])
        except signing.SignatureExpired as exc:
            raise FileFault("download_expired", 410) from exc
        except signing.BadSignature as exc:
            raise FileFault("invalid_ticket") from exc
        if not isinstance(grant, dict) or grant.get("v") != 1:
            raise FileFault("invalid_ticket")
        profile = _profile(grant["user"])
        if (request.META.get("HTTP_X_TLACHIHUANI_BINDING") != profile.binding_id
                or grant.get("account") != profile.account.hex
                or grant.get("binding") != profile.binding_id):
            raise FileFault("account_mismatch")
        row = _message(profile.user_id, grant["message"])
        if hashlib.sha256(row.message.encode("utf-8")).hexdigest() != grant["sha256"]:
            raise FileFault("response_changed", 409)
        if len(row.message.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise FileFault("response_too_large", 413)
        html = render_response(profile.user_id, row.pk, row.message, row=row, profile=profile)
        response = JsonResponse({"html": html, "format": "html", "truncated": False,
                                 "message_id": row.pk}, json_dumps_params={"ensure_ascii": False})
        if len(response.content) > MAX_CONTENT_BYTES:
            raise FileFault("response_too_large", 413)
        response["Content-Length"] = str(len(response.content))
        response["Cache-Control"] = "no-store, private"
        response["X-Content-Type-Options"] = "nosniff"
        return response
    except FileFault as error:
        return JsonResponse({"error": {"code": error.code,
                             "message": "This response cannot be loaded. Reload the conversation and try again."}}, status=error.status)
    except (KeyError, TypeError, ValueError, OSError):
        return JsonResponse({"error": {"code": "response_unavailable", "message": "This response is no longer available."}}, status=404)


_TOOL_FILES = {
    "pdfer": ("output_path",), "latexer": ("output_path", "tex_path"),
    "pptxer": ("output_path",), "shoter": ("output_path",),
    "camcorder": ("output_path",), "recorder": ("output_path",),
    "talker": ("output_path",), "whisperer": ("transcript_path",),
    "video_analyzer": ("transcript_path", "segments_path", "report_path", "analysis_path"),
    "netspeed_calculator": ("json_path",), "file_creator": ("output_path",),
}


def capture_tool_files(tool_name, result):
    """Snapshot only declared output fields of an actually successful tool.

    Called by the executor with the tool's parsed result, never with browser
    parameters, model HTML, a prompt, arbitrary *_path fields or a log string.
    """
    kind = str(tool_name).lower().removeprefix("chat_agent_").replace("-", "_")
    if (kind not in _TOOL_FILES or not isinstance(result, dict)
            or result.get("status") != "completed"):
        return []
    if kind == "file_creator" and (result.get("agent_status") not in {"created", "appended"}
                                   or not isinstance(result.get("output_sha256"), str)):
        return []
    snapshots = []
    for field in _TOOL_FILES[kind]:
        value = result.get(field)
        if not isinstance(value, str) or not value or len(value) > 4096 or not os.path.isabs(value):
            continue
        reference = {"kind": "file", "value": str(Path(value)).replace("\\", "/")}
        try:
            metadata, _ = _artifact(reference)
        except (FileFault, OSError, ValueError):
            continue
        expected_hash = result.get("output_sha256") if field == "output_path" else None
        if expected_hash is not None and expected_hash != metadata["sha256"]:
            continue
        snapshots.append({"reference": reference, "artifact": metadata})
    return snapshots


def record_artifacts(sources):
    """Resolve only artifacts freshly saved by the parser or trusted executor."""
    from .models import LLMProgram, LLMSnippet
    snapshots = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source.get("kind") in {"program", "snippet"}:
            kind, name, content = source["kind"], source.get("name"), source.get("content")
            if not isinstance(name, str) or not isinstance(content, str):
                continue
            if kind == "program":
                row = LLMProgram.objects.filter(programName=name, programContent=content).order_by("-idProgram").first()
                language = row.programLanguage if row else ""
            else:
                row = LLMSnippet.objects.filter(snippetName=name, snippetContent=content).order_by("-idSnippet").first()
                language = row.snippetLanguage if row else ""
            if row is None:
                continue
            data = content.encode("utf-8")
            if len(data) > MAX_FILE_BYTES:
                continue
            try:
                filename = _filename(name, language)
            except FileFault:
                continue
            item = {"reference": {"kind": "canvas", "value": name},
                    "artifact": {"key": kind + ":" + str(row.pk), "name": filename,
                                 "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}}
        elif (isinstance(source.get("reference"), dict) and source["reference"].get("kind") == "file"
              and isinstance(source.get("artifact"), dict)):
            # The executor already pinned this successful output. Revalidate
            # its exact snapshot before adding it to the durable reply.
            try:
                _artifact(source["reference"], source["artifact"])
            except (FileFault, OSError, ValueError, KeyError):
                continue
            item = source
        else:
            continue
        if item not in snapshots:
            snapshots.append(item)
    return snapshots
