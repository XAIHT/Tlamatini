# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Host files are opened only by the model's scoped tool, never a browser path frame."""
import base64
import re
import secrets
from pathlib import Path

from .. import canvas_file_views as saves
from ..path_guard import get_app_temp_root, validate_tool_path
from .protocol import InteractorError, MAX_UNITS


def prepare_file(request, action, filename, path):
    if path:
        destination = Path(path)
        if not destination.is_absolute():
            raise InteractorError("Supply an absolute file path, or omit path to create the file in Tlamatini Temp.")
        # Use the same allowed-path policy as the other model-facing file tools.
        rejection = validate_tool_path(str(destination))
        if rejection:
            raise InteractorError(rejection, "path_not_allowed")
    elif action == "new":
        if not filename or len(filename) > 200 or re.search(r'[\\/\x00-\x1f<>:"|?*]', filename) or filename.endswith((".", " ")):
            raise InteractorError("Provide a plain filename such as Dockerfile, without a path.")
        if filename in {".", ".."} or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", filename):
            raise InteractorError("This filename is reserved by Windows.")
        destination = Path(get_app_temp_root()) / "interactor" / request.owner[0] / secrets.token_hex(8) / filename
    else:
        raise InteractorError("Opening an existing file requires its absolute path. Use read for the currently open file.")
    destination = destination.absolute()
    if destination.is_symlink() or destination.resolve() != destination:
        raise InteractorError("Choose a normal file path without symbolic links or junction redirection.")
    if action == "new":
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("xb"):
                pass
        except FileExistsError as exc:
            raise InteractorError("That file already exists. Open it instead; new never overwrites.") from exc
    with saves._IO_LOCK:
        data, revision = saves._snapshot(destination)
        if data is None:
            raise InteractorError("The requested file does not exist.")
        if len(data) > MAX_UNITS * 2:
            raise InteractorError("This file is too large for live tutoring. Open it manually to edit it.", "too_large")
        token = saves._grant(destination, request.owner)
    return {"name": destination.name, "path": str(destination),
            "bytes": base64.b64encode(data).decode("ascii"),
            "native": {"token": token, "revision": revision}}
