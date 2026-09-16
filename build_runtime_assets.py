# Tlamatini Author Banner — Angela López Mendoza
"""Fail-closed runtime asset inventory shared by the application/installer builds.

Only filesystem/ZIP inspection: no Django startup, tests, browsers, or downloads.
The manifest records payload-relative paths, sizes and SHA-256 hashes, not source
paths or configuration values. It is a completeness receipt, NOT a signature.
"""

import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import zipfile


MANIFEST_NAME = "runtime-assets.json"
MAX_RELEASE_ZIP_BYTES = 1_990_000_000  # decimal GB, not GiB; user release ceiling
STATIC_SOURCE = "Tlamatini/agent/static"
PDFJS = "agent/vendor/pdfjs/"
REQUIRED_STATIC = (
    "agent/js/avatar.js", "agent/css/avatar.css",
    "agent/img/avatar/eo_mc.jpg", "agent/img/avatar/ec_mc.jpg",
    "agent/img/avatar/eo_mo.jpg", "agent/img/avatar/ec_mo.jpg",
    "agent/pdf/canvas.html", "agent/js/agent_page_pdf.js",
    "agent/js/pdf_canvas_viewer.js", "agent/js/pdf_context_progress.js",
    "agent/css/pdf_canvas.css", "agent/css/pdf_context_progress.css",
    *(PDFJS + name for name in (
        "build/pdf.mjs", "build/pdf.worker.mjs", "web/pdf_viewer.mjs",
        "web/pdf_viewer.css", "LICENSE", "VERSION", "cmaps/LICENSE",
        "standard_fonts/LICENSE_FOXIT", "standard_fonts/LICENSE_LIBERATION",
        "standard_fonts/LiberationSans-Regular.ttf", "iccs/CGATS001Compat-v2-micro.icc",
        "wasm/jbig2.wasm", "wasm/openjpeg.wasm", "wasm/qcms_bg.wasm",
    )),
)
SOURCE_TREES = (
    (STATIC_SOURCE, "_internal/agent/static"),
    ("Tlamatini/staticfiles", "_internal/staticfiles"),
    ("Tlamatini/agent/templates", "_internal/agent/templates"),
    ("Tlamatini/agent/agents", "agents"),
    ("Tlamatini/agent/skills_pkg", "agent/skills_pkg"),
    ("Tlamatini/agent/skills_pkg", "_internal/agent/skills_pkg"),
    ("Tlamatini/jd-cli", "jd-cli"),
    ("security", "security"),
)
ROOT_SOURCES = {
    "build_runtime_assets.py": "build_runtime_assets.py",
    "Tlamatini/agent/config.json": "config.json",
    "Tlamatini/agent/prompt.pmt": "prompt.pmt",
    "README.md": "README.md",
    "agents_descriptions.md": "agents_descriptions.md",
    "apply_update.ps1": "apply_update.ps1",
    "preserved_user_state.json": "preserved_user_state.json",
    "Tlamatini/agent/sqlite_copy.py": "sqlite_copy.py",
    "Tlamatini/cat_art.py": "cat_art.py",
    **{name: name for name in (
        "register_flw.ps1", "unregister_flw.ps1", "Tlamatini.ps1", "Tlamatini.ico",
        "CreateShortcut.ps1", "RemoveShortcut.ps1", "CreateShortcut.json",
        "freeingport8000.ps1",
    )},
}
RUNTIME_SKIP_NAMES = {
    "__pycache__", "pools", ".tlamatini", ".git", "security_logs",
    "_tlamatini_agents_manifest.json",  # generated anew with installed paths/version
}
STATIC_TAG = re.compile(r"\{%\s*static\s+(['\"])(.*?)\1", re.DOTALL)
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
REMOTE_RESOURCE = re.compile(r"<(?:script|link)\b[^>]*\b(?:src|href)\s*=\s*['\"](?:https?:)?//", re.IGNORECASE)


def ignore_runtime_state(_directory, names):
    """Pool/browser sessions, caches and logs are not agent/skill templates."""
    return [name for name in names if name in RUNTIME_SKIP_NAMES
            or name.lower().endswith((".pyc", ".pyo", ".log"))]


def tree_files(root, *, source=False):
    root = Path(root)
    if not root.is_dir():
        raise RuntimeError(f"Required runtime tree is missing: {root}")
    for current, dirs, files in os.walk(root):
        if source:
            skipped = set(ignore_runtime_state(current, dirs + files))
            dirs[:] = [name for name in dirs if name not in skipped]
            files = [name for name in files if name not in skipped]
        dirs.sort()
        for name in sorted(files):
            path = Path(current) / name
            if not path.resolve().is_relative_to(root.resolve()):
                raise RuntimeError(f"Runtime asset escapes its source tree: {path}")
            yield path


def digest_stream(stream):
    digest = hashlib.sha256()
    size = 0
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        size += len(block)
        digest.update(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def file_record(path):
    with Path(path).open("rb") as stream:
        return digest_stream(stream)


def require_file(path):
    path = Path(path)
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError(f"Required runtime asset missing or empty: {path}")


def validate_preservation_contract(repo):
    """Source-only guard: swapping, reinstall and documented state must agree."""
    repo = Path(repo)
    names = json.loads((repo / "preserved_user_state.json").read_text(encoding="utf-8"))["preserve"]
    expected = {name.casefold() for name in names}
    if len(expected) != len(names) or any(
        not name or name in {".", ".."} or any(c in name for c in "/\\:") for name in names
    ):
        raise RuntimeError("Invalid top-level preserved-user-state contract")
    app_code = {"_internal", "agents", "agent", "python", "jre", "git", "ms-playwright",
                "images", "security", "tlamatinisourcecode", "tlamatini.md", "tlamatini.exe",
                "build_runtime_assets.py", "apply_update.ps1", MANIFEST_NAME}
    if expected & app_code:
        raise RuntimeError("Preservation contract pins application code: " + ", ".join(expected & app_code))
    ps = (repo / "apply_update.ps1").read_text(encoding="utf-8")
    block = re.search(r"\$Preserve\s*=\s*@\((.*?)\)", ps, re.DOTALL)
    actual = set(re.findall(r"'([^']+)'", re.sub(r"#[^\n]*", "", block[1]))) if block else set()
    if {name.casefold() for name in actual} != expected:
        raise RuntimeError("apply_update.ps1 preservation differs from preserved_user_state.json")
    installer = ast.parse((repo / "install.py").read_text(encoding="utf-8"))
    fallback = next((ast.literal_eval(node.value) for node in ast.walk(installer)
                     if isinstance(node, ast.Assign) and any(
                         isinstance(t, ast.Name) and t.id == "_PRESERVE_FALLBACK" for t in node.targets)), ())
    if {name.casefold() for name in fallback} != expected:
        raise RuntimeError("Installer preservation fallback differs from the shared contract")
    updater = ast.get_docstring(ast.parse((repo / "Tlamatini/agent/self_update.py").read_text(encoding="utf-8"))) or ""
    block = re.search(r"Preserved across the swap[^\n]*\n\s*\n(.*?)(?:\n\s*\n)", updater, re.DOTALL)
    if not block or {name.casefold() for name in block[1].split()} != expected:
        raise RuntimeError("Updater documentation differs from the preservation contract")
    build_tree = ast.parse((repo / "build.py").read_text(encoding="utf-8"))
    empty_dirs = next((ast.literal_eval(node.value) for node in ast.walk(build_tree)
                       if isinstance(node, ast.Assign) and any(
                           isinstance(t, ast.Name) and t.id == "empty_dirs" for t in node.targets)), ())
    state_dirs = {name.replace("\\", "/").split("/")[0].casefold() for name in empty_dirs}
    if not state_dirs or not state_dirs.issubset(expected):
        raise RuntimeError("Runtime-state directories are not covered by the preservation contract")
    return names


def validate_source_assets(repo):
    """Catch missing inputs BEFORE dependency installs, DB removal or freezing."""
    repo = Path(repo)
    validate_preservation_contract(repo)
    for name in ROOT_SOURCES:
        require_file(repo / name)
    for src, _ in SOURCE_TREES:
        if src == "Tlamatini/staticfiles":  # generated by collectstatic below
            continue
        if not any(tree_files(repo / src, source=True)):
            raise RuntimeError(f"Required runtime source tree is empty: {src}")
    for name in REQUIRED_STATIC:
        require_file(repo / STATIC_SOURCE / name)
    # Locally vendored dependencies must match the pinned download receipt.
    frontend = repo / STATIC_SOURCE / "agent/vendor/frontend"
    require_file(frontend / "manifest.json")
    manifest = json.loads((frontend / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or not manifest.get("files"):
        raise RuntimeError("Missing/invalid frontend vendor manifest; run scripts/vendor_frontend.py")
    for name, record in manifest["files"].items():
        target = (frontend / name).resolve()
        if not target.is_relative_to(frontend.resolve()):
            raise RuntimeError(f"Unsafe frontend manifest path: {name}")
        if not target.is_file() or file_record(target) != record:
            raise RuntimeError(f"Frontend vendor asset missing/modified: {name}; run scripts/vendor_frontend.py")
    # A tracked vendor font, map or asset deleted locally must not disappear from
    # the baseline merely because rglob no longer sees it. Snapshots have no Git.
    if (repo / ".git").exists():
        paths = [src for src, _ in SOURCE_TREES if src != "Tlamatini/staticfiles"]
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", *paths], cwd=repo,
            capture_output=True, check=True,
        )
        missing = [name for name in result.stdout.decode("utf-8").split("\0")
                   if name and not (repo / name).is_file()]
        if missing:
            raise RuntimeError("Tracked runtime source files are missing: " + ", ".join(missing))


def verify_collected_static(repo):
    """Require every source byte and literal static reference in STATIC_ROOT."""
    repo = Path(repo)
    source, collected = repo / STATIC_SOURCE, repo / "Tlamatini/staticfiles"
    count = 0
    for path in tree_files(source, source=True):
        target = collected / path.relative_to(source)
        if not target.is_file() or file_record(path) != file_record(target):
            raise RuntimeError(f"collectstatic omitted or changed a source asset: {target}")
        count += 1
    for template in tree_files(repo / "Tlamatini/agent/templates", source=True):
        if template.suffix == ".html":
            text = template.read_text(encoding="utf-8")
            if REMOTE_RESOURCE.search(text) or re.search(r"\{%\s*bootstrap_(css|javascript)\b", text):
                raise RuntimeError(f"Template depends on remote frontend resources: {template}")
            for _, name in STATIC_TAG.findall(text):
                require_file(collected / name)
    # Local font/icon references are just as essential as the CSS itself.
    for css in collected.rglob("*.css"):
        text = re.sub(r"/\*.*?\*/", "", css.read_text(encoding="utf-8"), flags=re.DOTALL)
        if re.search(r"@import\s+['\"](?:https?:)?//", text, re.IGNORECASE):
            raise RuntimeError(f"Stylesheet imports a remote dependency: {css}")
        for _, value in CSS_URL.findall(text):
            value = value.strip()
            if value.startswith("//") or re.match(r"^https?:", value, re.IGNORECASE):
                raise RuntimeError(f"Stylesheet depends on a remote resource: {css}")
            if not value or value.startswith("#") or re.match(r"^[a-z]+:", value, re.I):
                continue
            value = value.split("?", 1)[0].split("#", 1)[0]
            target = collected / value.removeprefix("/static/") if value.startswith("/static/") else css.parent / value
            require_file(target)
    print(f"Static carriage: {count} source files match collected bytes; literal references resolved.")


def capture_source_payload(repo, *, self_modify=False):
    """Freeze the expected source-to-install mapping before PyInstaller runs."""
    repo = Path(repo)
    expected = {}
    for src, dst in SOURCE_TREES:
        source = repo / src
        for path in tree_files(source, source=True):
            expected[dst + "/" + path.relative_to(source).as_posix()] = file_record(path)
    for src, dst in ROOT_SOURCES.items():
        expected[dst] = file_record(repo / src)
    if self_modify:
        expected["Tlamatini.md"] = file_record(repo / "Tlamatini/agent/Tlamatini.md")
    return expected


def write_runtime_manifest(dist_root, expected, *, version, self_modify):
    """Check all source carriers and record EVERY resulting payload file."""
    root = Path(dist_root)
    for name, record in expected.items():
        target = root / name
        if not target.is_file() or file_record(target) != record:
            raise RuntimeError(f"Frozen release lost or changed a required source asset: {name}")
    for name in ("Tlamatini.exe", "python/python.exe", "jre/bin/java.exe",
                 "git/cmd/git.exe", "jd-cli/jd-cli.jar", "_internal/db.sqlite3",
                 "_internal/pymupdf/_mupdf.pyd", "_internal/pymupdf/_extra.pyd",
                 "_internal/pymupdf/mupdfcpp64.dll"):
        require_file(root / name)
    for patterns in (
        ("chromium-*/**/chrome.exe",),
        ("chromium_headless_shell-*/**/chrome-headless-shell.exe",
         "chromium_headless_shell-*/**/headless_shell.exe"),
    ):
        matches = (path for pattern in patterns for path in (root / "ms-playwright").glob(pattern))
        if not any(path.is_file() and path.stat().st_size for path in matches):
            raise RuntimeError(f"Required Playwright browser payload is missing: {patterns}")
    if self_modify:
        require_file(root / "TlamatiniSourceCode/_SOURCE_SNAPSHOT_MANIFEST.json")
        require_file(root / "TlamatiniSourceCode/build_runtime_assets.py")
    files = {p.relative_to(root).as_posix(): file_record(p)
             for p in tree_files(root) if p.relative_to(root).as_posix() != MANIFEST_NAME}
    document = {"schema": 1, "version": version, "self_modify": self_modify,
                "source_assets_verified": len(expected), "files": files}
    validate_runtime_document(document)
    (root / MANIFEST_NAME).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Runtime manifest: {len(expected)} source mappings, {len(files)} payload files.")


def validate_archive_members(archive):
    """Reject paths that Windows would alias, sanitize or extract outside staging."""
    seen = set()
    files = set()
    parents = set()
    devices = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
               *(f"lpt{i}" for i in range(1, 10))}
    for item in archive.infolist():
        name = item.filename.rstrip("/") if item.is_dir() else item.filename
        path = PurePosixPath(name)
        invalid = (not name or path.is_absolute() or any(c in name for c in '\\:<>"|?*')
                   or any(ord(c) < 32 for c in name)
                   or path.as_posix() != name or any(part in {".", ".."}
                       or part.rstrip(" .") != part for part in path.parts))
        if invalid or any(part.split(".")[0].casefold() in devices for part in path.parts):
            raise RuntimeError(f"Unsafe release ZIP member: {item.filename}")
        if name.casefold() in seen or stat.S_ISLNK(item.external_attr >> 16):
            raise RuntimeError(f"Duplicate/case-colliding or symlink ZIP member: {item.filename}")
        seen.add(name.casefold())
        if not item.is_dir():
            files.add(name.casefold())
        parents.update(p.as_posix().casefold() for p in path.parents if p.as_posix() != ".")
    if files & parents:
        raise RuntimeError("Release ZIP uses a file as a parent directory")


def validate_runtime_document(document, *, expected_version=None):
    files = document.get("files")
    if document.get("schema") != 1 or not isinstance(files, dict) or not files:
        raise RuntimeError("Invalid or empty runtime asset manifest")
    if expected_version is not None and document.get("version") != expected_version:
        raise RuntimeError("Runtime package version differs from the requested release; rebuild it")
    floor = {"Tlamatini.exe", "python/python.exe", "config.json", "prompt.pmt",
             "apply_update.ps1", "sqlite_copy.py", "preserved_user_state.json",
             "build_runtime_assets.py", "jre/bin/java.exe", "git/cmd/git.exe",
             "jd-cli/jd-cli.jar", "_internal/db.sqlite3",
             "_internal/pymupdf/_mupdf.pyd", "_internal/pymupdf/_extra.pyd",
             "_internal/pymupdf/mupdfcpp64.dll",
             "_internal/staticfiles/agent/vendor/frontend/manifest.json",
             *("_internal/staticfiles/" + name for name in REQUIRED_STATIC)}
    if not floor.issubset(files):
        raise RuntimeError("Runtime manifest omits mandatory files: " + ", ".join(sorted(floor - set(files))))
    tree = any(name.startswith("TlamatiniSourceCode/") for name in files)
    identity = "Tlamatini.md" in files and "_internal/agent/Tlamatini.md" in files
    if document.get("self_modify") is True:
        required = {"TlamatiniSourceCode/" + name for name in (
            "build.py", "build_runtime_assets.py", "copy_source_assets.py",
            "_SOURCE_SNAPSHOT_MANIFEST.json", "_REBUILD_INSTRUCTIONS.md")}
        if not tree or not identity or not required.issubset(files):
            raise RuntimeError("Self-modify package is missing its source snapshot or identity")
    elif document.get("self_modify") is not False or tree or any(
        name.rsplit("/", 1)[-1] == "Tlamatini.md" for name in files
    ):
        raise RuntimeError("Default package unexpectedly carries self-modify source/identity")
    return files


def verify_package(package, *, expected_version=None):
    """Require exact ZIP membership and streamed SHA-256/CRC for every file.

    Used before publishing pkg.zip and again before assembling an installer.
    Old packages without a receipt must be rebuilt, never silently accepted.
    """
    with zipfile.ZipFile(package) as archive:
        validate_archive_members(archive)
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        folded = [name.casefold() for name in names]
        if len(set(folded)) != len(names):
            raise RuntimeError("Duplicate/case-colliding files in runtime ZIP")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise RuntimeError(f"Unsafe runtime ZIP member: {name}")
        if MANIFEST_NAME not in names:
            raise RuntimeError("pkg.zip has no runtime-assets.json; rebuild with the current build.py")
        document = json.loads(archive.read(MANIFEST_NAME))
        files = validate_runtime_document(document, expected_version=expected_version)
        if set(names) != set(files) | {MANIFEST_NAME}:
            raise RuntimeError("Runtime ZIP membership differs from its completeness manifest")
        for name, record in files.items():
            with archive.open(name) as stream:
                if digest_stream(stream) != record:
                    raise RuntimeError(f"Runtime ZIP file differs from its SHA-256 receipt: {name}")
    print(f"Runtime ZIP verified: {len(files)} files, version {document['version']}.")
    return document


def verify_staged_payload(directory, *, expected_version=None):
    """Recheck extracted bytes BEFORE shutdown; never run on a live install."""
    root = Path(directory).resolve()
    document = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    files = validate_runtime_document(document, expected_version=expected_version)
    actual = {p.relative_to(root).as_posix() for p in tree_files(root)}
    if actual != set(files) | {MANIFEST_NAME}:
        raise RuntimeError("Staged payload membership differs from its runtime receipt")
    for name, record in files.items():
        target = (root / name).resolve()
        if not target.is_relative_to(root) or file_record(target) != record:
            raise RuntimeError(f"Staged runtime file differs from its receipt: {name}")
    print(f"Staged payload verified: {len(files)} files.")
    return document


def create_release_archive(output_base, *, root_dir, base_dir):
    """Publish the final distributable only within the 1.99 decimal GB budget.

    This covers the OUTER ZIP (installer, its runtime, uninstaller and pkg.zip),
    not just the inner application package. Oversized output is kept as pending
    for inspection; required assets are never automatically pruned to shrink it.
    """
    output = Path(str(output_base) + ".zip")
    pending = shutil.make_archive(str(output_base) + ".pending", "zip",
                                  root_dir=str(root_dir), base_dir=base_dir)
    size = Path(pending).stat().st_size
    if size > MAX_RELEASE_ZIP_BYTES:
        raise RuntimeError(
            f"Final release is {size:,} bytes; limit is {MAX_RELEASE_ZIP_BYTES:,}. "
            f"Oversized archive retained at {pending}; nothing published."
        )
    os.replace(pending, output)
    print(f"Final release size: {size:,} / {MAX_RELEASE_ZIP_BYTES:,} bytes.")
    return str(output)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Read-only release integrity inspection")
    parser.add_argument("--verify-tree", required=True, help="Unmodified extracted staging directory")
    args = parser.parse_args()
    verify_staged_payload(args.verify_tree)
