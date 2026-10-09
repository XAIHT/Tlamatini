# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Complete project dossier: facts, orchestration and verification.

Run through ``refresh_project_docs.py``. This module gathers every fact the
dossier states from Git and from the source tree, then hands them to the PDF
(``dossier_pdf``) and deck (``dossier_pptx``) renderers, which share one
content model (``dossier_content``) and one visual identity
(``dossier_theme``). ``dossier_verify`` then re-opens both files and proves
that nothing overflows, clips or goes missing.

Nothing here reads configuration values, credentials or private addresses.
The only files opened for their content are source files and documentation.
"""
from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import re
import subprocess
import tokenize
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[3]
AGENT_DIR = REPO_ROOT / "Tlamatini" / "agent"
BUILD_DIR = REPO_ROOT / "build" / "documentation_refresh"

PDF_OUTPUT = REPO_ROOT / "tlamatini_app_summary.pdf"
PPT_OUTPUT = REPO_ROOT / "Tlamatini_eXtended_Artificial_Intelligence_Humanly_Tempered.pptx"
CONTEXT_OUTPUT = BUILD_DIR / "complete_project_dossier_context.json"
TREE_OUTPUT = BUILD_DIR / "complete_tracked_file_tree.txt"
VERIFY_OUTPUT = BUILD_DIR / "dossier_verification.json"

VENDOR_PREFIX = "Tlamatini/agent/static/agent/vendor/"

BINARY_EXTENSIONS = {
    ".7z", ".bcmap", ".dll", ".exe", ".gif", ".icc", ".ico", ".jar", ".jpeg", ".jpg", ".mp3",
    ".mp4", ".pdf", ".pfb", ".png", ".pptx", ".pyc", ".sqlite3", ".ttf", ".wasm", ".wav",
    ".woff", ".woff2", ".zip",
}

LANGUAGE_BY_EXTENSION = {
    ".bat": "Batch",
    ".cjs": "JavaScript",
    ".cpp": "C++",
    ".css": "CSS",
    ".flw": "Tlamatini Flow",
    ".fpmt": "Prompt flow",
    ".html": "HTML",
    ".ini": "INI",
    ".js": "JavaScript",
    ".json": "JSON",
    ".md": "Markdown",
    ".mjs": "JavaScript module",
    ".pmt": "Prompt template",
    ".proto": "Protocol Buffers",
    ".ps1": "PowerShell",
    ".py": "Python",
    ".svg": "SVG",
    ".txt": "Text",
    ".yaml": "YAML",
    ".yml": "YAML",
}

CORE_PYTHON_TOOLS = 20
DOCUMENT_TIMEZONE = ZoneInfo("America/Mexico_City")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


@dataclass
class LineStats:
    language: str
    files: int = 0
    total_lines: int = 0
    effective_lines: int = 0


@dataclass
class FileStats:
    path: str
    language: str
    total_lines: int
    effective_lines: int


# ── Git ─────────────────────────────────────────────────────────────
def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=check)
    return result.stdout.strip()


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True).returncode == 0


def document_datetime(iso_value: str) -> datetime:
    """Render timestamp dates in Angela's timezone; preserve date-only values."""
    moment = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    return moment.astimezone(DOCUMENT_TIMEZONE) if moment.tzinfo is not None else moment


def long_date(iso_value: str) -> str:
    moment = document_datetime(iso_value)
    return f"{MONTHS[moment.month - 1]} {moment.day}, {moment.year}"


def short_date(iso_value: str) -> str:
    return document_datetime(iso_value).strftime("%Y-%m-%d")


def _github_releases() -> dict:
    """The releases actually PUBLISHED on GitHub; fail-open to an empty mapping.

    A tag is not a release: a repository can carry a newer tag with nothing
    published for it, so the tag alone never states "the current release".
    """
    try:
        listing = subprocess.run(
            ["gh", "release", "list", "--limit", "30", "--json",
             "tagName,isLatest,isDraft,isPrerelease,publishedAt"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=90, check=True).stdout.strip()
        rows = json.loads(listing) if listing else []
    except Exception:
        return {}
    if not isinstance(rows, list):
        return {}
    live = [row for row in rows if isinstance(row, dict) and not row.get("isDraft")]
    latest = next((row for row in live if row.get("isLatest")), None)
    return {
        "latest_tag": str((latest or {}).get("tagName", "")),
        "latest_published_at": str((latest or {}).get("publishedAt", "")),
        "published_tags": [str(row.get("tagName", "")) for row in live],
    }


def published_releases() -> dict:
    """The release this dossier states as current.

    Normally GitHub's own answer (_github_releases). TLAMATINI_RELEASE_TAG names
    the release the dossier is prepared FOR: Angela publishes a release as the
    very last step, after the documentation and this dossier are regenerated, so
    GitHub cannot list it yet. When that tag exists in this repository, the
    dossier states it as the current release, dated today, and the console says
    so. A tag that does not exist is ignored with a warning.
    """
    found = _github_releases()
    planned = os.environ.get("TLAMATINI_RELEASE_TAG", "").strip()
    if not planned or planned == found.get("latest_tag"):
        return found
    if not git_ok("rev-parse", "-q", "--verify", f"refs/tags/{planned}"):
        print(f"WARNING: TLAMATINI_RELEASE_TAG={planned} is not a tag in this repository; "
              "using GitHub's answer instead.", flush=True)
        return found
    print(f"Release prepared for: {planned} (GitHub lists "
          f"{found.get('latest_tag') or 'no release'} as Latest until it is published).", flush=True)
    tags = [planned] + [tag for tag in found.get("published_tags", []) if tag != planned]
    return {"latest_tag": planned,
            "latest_published_at": datetime.now(DOCUMENT_TIMEZONE).isoformat(),
            "published_tags": tags, "prepared": True}


# ── Inventory and effective lines ───────────────────────────────────
def tracked_paths() -> list[str]:
    return [line for line in git("ls-files").splitlines() if line.strip()]


def untracked_paths() -> list[str]:
    return [line for line in git("ls-files", "--others", "--exclude-standard").splitlines() if line.strip()]


def build_tree(paths: list[str]) -> str:
    """Box-drawn tree of the given paths; directories end with a slash."""
    root: dict[str, dict] = {}
    for raw_path in sorted(paths):
        node = root
        for part in raw_path.replace("\\", "/").split("/"):
            node = node.setdefault(part, {})

    def walk(node: dict, prefix: str) -> list[str]:
        lines: list[str] = []
        entries = sorted(node.items(), key=lambda item: (bool(item[1]), item[0].lower()))
        for index, (name, child) in enumerate(entries):
            last = index == len(entries) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{name}{'/' if child else ''}")
            if child:
                lines.extend(walk(child, prefix + ("    " if last else "│   ")))
        return lines

    return "Tlamatini/\n" + "\n".join(walk(root, ""))


def parse_tree(lines: list[str]) -> list[str]:
    """Rebuild the file paths from a box-drawn tree (the inverse of build_tree)."""
    stack: list[str] = []
    files: list[str] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        marker = max(line.find("├── "), line.find("└── "))
        if marker < 0:
            raise ValueError(f"Unparseable tree line: {line!r}")
        depth = marker // 4
        name = line[marker + 4:]
        del stack[depth:]
        if name.endswith("/"):
            stack.append(name[:-1])
        else:
            files.append("/".join([*stack, name]))
    return files


def looks_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        return b"\x00" in path.read_bytes()[:2048]
    except OSError:
        return True


def read_text(path: Path) -> str | None:
    if looks_binary(path):
        return None
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None


def python_docstring_lines(text: str) -> set[int]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    lines: set[int] = set()
    owners = [tree, *[node for node in ast.walk(tree)
                      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]]
    for node in owners:
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) \
                and isinstance(node.body[0].value.value, str):
            first = node.body[0]
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def count_python_effective(text: str) -> int:
    doc_lines = python_docstring_lines(text)
    source = text.splitlines()
    effective: set[int] = set()
    skip = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.ENCODING, tokenize.ENDMARKER,
            tokenize.INDENT, tokenize.DEDENT}
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in skip:
                continue
            # Multiline strings (SQL, prompts, embedded JS) span several authored lines.
            for number in range(token.start[0], token.end[0] + 1):
                if number not in doc_lines and number <= len(source) and source[number - 1].strip():
                    effective.add(number)
    except tokenize.TokenError:
        return count_generic_effective(text, ".py")
    return len(effective)


def count_generic_effective(text: str, suffix: str) -> int:
    if suffix in {".js", ".cjs", ".mjs", ".css", ".proto", ".cpp"}:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    elif suffix in {".html", ".md", ".svg"}:
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    elif suffix == ".ps1":
        text = re.sub(r"<#.*?#>", "", text, flags=re.DOTALL)
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if suffix in {".yaml", ".yml", ".ps1"} and stripped.startswith("#"):
            continue
        if suffix in {".js", ".cjs", ".mjs", ".css", ".proto", ".cpp"} and stripped.startswith("//"):
            continue
        if suffix == ".ini" and stripped.startswith((";", "#")):
            continue
        if suffix == ".bat" and (stripped.lower().startswith("rem ") or stripped.startswith("::")):
            continue
        count += 1
    return count


def line_inventory(paths: list[str]) -> tuple[list[LineStats], list[FileStats], int, list[str]]:
    by_language: dict[str, LineStats] = {}
    files: list[FileStats] = []
    binary = 0
    missing: list[str] = []
    for rel in paths:
        absolute = REPO_ROOT / rel
        if not absolute.is_file():
            missing.append(rel)
            continue
        text = read_text(absolute)
        if text is None:
            binary += 1
            continue
        suffix = absolute.suffix.lower()
        language = LANGUAGE_BY_EXTENSION.get(suffix, "Other text")
        total = len(text.splitlines())
        effective = count_python_effective(text) if suffix == ".py" else count_generic_effective(text, suffix)
        stats = by_language.setdefault(language, LineStats(language))
        stats.files += 1
        stats.total_lines += total
        stats.effective_lines += effective
        files.append(FileStats(rel, language, total, effective))
    languages = sorted(by_language.values(), key=lambda row: row.effective_lines, reverse=True)
    files.sort(key=lambda row: row.effective_lines, reverse=True)
    return languages, files, binary, missing


# ── Source-derived product facts ────────────────────────────────────
def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workflow_agents() -> list[str]:
    root = AGENT_DIR / "agents"
    return sorted(entry.name for entry in root.iterdir()
                  if entry.is_dir() and entry.name != "pools" and (entry / "config.yaml").exists())


def display_names(agents: list[str]) -> dict[str, str]:
    """The exact designed display names, from the one function the app itself uses."""
    module = _load_module("dossier_agent_paths", AGENT_DIR / "services" / "agent_paths.py")
    return {name: module.display_name_from_agent_type(name) for name in agents}


def wrapped_tool_names() -> list[str]:
    text = (AGENT_DIR / "chat_agent_registry.py").read_text(encoding="utf-8")
    return re.findall(r'tool_name\s*=\s*"(chat_agent_[a-z0-9_]+)"', text)


def skills() -> list[str]:
    root = AGENT_DIR / "skills_pkg"
    return sorted(entry.name for entry in root.iterdir() if (entry / "SKILL.md").is_file())


def _assigned_literal(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return node.value
    raise RuntimeError(f"{name} not found in {path}")


def acpx_tool_names() -> list[str]:
    value = _assigned_literal(AGENT_DIR / "acpx" / "__init__.py", "ACPX_TOOL_NAMES")
    if isinstance(value, ast.Call) and value.args:
        value = value.args[0]
    return sorted(item.value for item in value.elts if isinstance(item, ast.Constant))


def supervisor_tool_names() -> list[str]:
    value = _assigned_literal(AGENT_DIR / "external_mcp_manager.py", "_SUPERVISOR_TOOL_NAMES")
    if isinstance(value, ast.Call) and value.args:
        value = value.args[0]
    return sorted(item.value for item in value.elts if isinstance(item, ast.Constant))


def parametrizer_sources() -> int:
    value = _assigned_literal(AGENT_DIR / "services" / "agent_contracts.py", "_PARAMETRIZER_OUTPUT_FIELDS")
    return len(value.keys) if isinstance(value, ast.Dict) else 0


def catalog_sections() -> list[tuple[str, str]]:
    text = (AGENT_DIR / "views.py").read_text(encoding="utf-8")
    block = re.search(r"PROMPT_CATEGORY_ORDER\s*=\s*\[(.*?)\n\]", text, re.S)
    if not block:
        raise RuntimeError("PROMPT_CATEGORY_ORDER not found")
    return re.findall(r"\('([a-z0-9_]+)',\s*'([^']+)'\)", block.group(1))


def acpx_peers() -> list[str]:
    text = (AGENT_DIR / "acpx" / "agent_registry.py").read_text(encoding="utf-8")
    peers = re.findall(r'^\s{4}"([a-z0-9_]+)":\s*AcpAgentSpec', text, re.M)
    return peers or sorted(set(re.findall(r'agent_id="([a-z0-9_]+)"', text)))


def model_settings() -> tuple[int, list[tuple[str, int]], int]:
    module = _load_module("dossier_model_settings", AGENT_DIR / "agents" / "model_settings.py")
    groups: dict[str, int] = {}
    for field in module.FIELDS:
        groups[field["group"]] = groups.get(field["group"], 0) + 1
    return len(module.FIELDS), list(groups.items()), len(module.AGENTS)


def requirements_count() -> int:
    return sum(1 for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.strip().startswith("#"))


def version_info() -> dict:
    override = os.environ.get("TLAMATINI_VERSION", "").strip()
    if override:
        return {"version": override, "source": "TLAMATINI_VERSION override"}
    try:
        info = _load_module("dossier_version", AGENT_DIR / "version.py").get_version_info()
        return {"version": str(info.get("version", "0.0.0")), "source": str(info.get("source", "git"))}
    except Exception:
        return {"version": "0.0.0", "source": "unresolved"}


def tag_timeline(limit: int = 12) -> list[dict]:
    raw = git("for-each-ref", "--sort=creatordate", "--format=%(refname:short)\x1f%(creatordate:iso-strict)"
              "\x1f%(contents:subject)", "refs/tags/v*")
    rows = []
    for line in raw.splitlines():
        name, created, subject = line.split("\x1f", 2)
        rows.append({"tag": name, "date": short_date(created), "subject": subject})
    return rows[-limit:]


def release_facts(published: dict, head_short: str) -> dict:
    tag = git("describe", "--tags", "--abbrev=0", "HEAD")
    tag_commit = git("rev-parse", "--short", f"{tag}^{{commit}}")
    tag_date = git("for-each-ref", "--format=%(creatordate:iso-strict)", f"refs/tags/{tag}")
    distance = int(git("rev-list", "--count", f"{tag}..HEAD") or 0)
    on_origin = bool(git("ls-remote", "--tags", "origin", f"refs/tags/{tag}", check=False))
    after = git("log", "--format=%h\x1f%s", f"{tag}..HEAD").splitlines()
    pfp_path = "Tlamatini/agent/templates/agent/prompt_flow_panel.html"
    pfp_in_tag = git_ok("cat-file", "-e", f"{tag}:{pfp_path}")
    pfp_commit = git("log", "--diff-filter=A", "--format=%h", "-1", "--", pfp_path)
    latest = published.get("latest_tag", "")
    return {
        "tag": tag, "tag_commit": tag_commit, "tag_date": short_date(tag_date) if tag_date else "",
        "distance": distance, "on_origin": on_origin, "after": [row.split("\x1f", 1) for row in after],
        "pfp_in_tag": pfp_in_tag, "pfp_commit": pfp_commit, "latest_published": latest,
        "latest_published_at": short_date(published["latest_published_at"])
        if published.get("latest_published_at") else "",
        "head_short": head_short, "prepared": bool(published.get("prepared")),
    }


def release_statements(rel: dict, version: str) -> tuple[list[str], list[list[str]], list[tuple[str, str]]]:
    statements = [
        f"The annotated tag **{rel['tag']}** was created on {rel['tag_date']} and resolves to commit "
        f"`{rel['tag_commit']}`" + (", and the remote advertises it." if rel["on_origin"] else
                                     "; it has not been pushed to the remote.")
    ]
    if rel["distance"]:
        listed = ", ".join(f"`{sha}`" for sha, _ in rel["after"])
        statements.append(
            f"Since the tag, {rel['distance']} more commit(s) went into main ({listed}). A build of main "
            f"still reports version {version}, because the version always carries the tag's number and "
            f"nothing more.")
    if rel["pfp_commit"] and not rel["pfp_in_tag"]:
        statements.append(
            f"The Prompt Flow Panel itself first appears in commit `{rel['pfp_commit']}`, after the tag. The "
            f"tagged tree therefore does not contain it, while a build from the current source does.")
    if rel["latest_published"]:
        same = rel["latest_published"] == rel["tag"]
        if rel.get("prepared"):
            statements.append(
                f"The current release is **{rel['latest_published']}**, published "
                f"{rel['latest_published_at']} together with this dossier.")
        else:
            statements.append(
                f"The newest release published on GitHub is **{rel['latest_published']}**"
                + (f", published {rel['latest_published_at']}." if rel["latest_published_at"] else ".")
                + ("" if same else f" Self-update offers only published releases, so installations are "
                                   f"offered {rel['tag']} once it is published."))
    else:
        statements.append("GitHub publication status could not be read, so only Git facts are stated here.")
    points = [("The tag", f"{rel['tag']} resolves to `{rel['tag_commit']}`, created {rel['tag_date']}.")]
    if rel["distance"]:
        points.append(("Since the tag", f"{rel['distance']} newer commit(s); a build of main still reports "
                                    f"{version}."))
    if rel["pfp_commit"] and not rel["pfp_in_tag"]:
        points.append(("Prompt Flow Panel", f"First appears in `{rel['pfp_commit']}`, after the tag."))
    points.append(("Published", f"The current release is {rel['latest_published']}." if rel.get("prepared")
                   else f"The newest release on GitHub is {rel['latest_published'] or 'unknown'}."))
    rows = [
        ["Version", version],
        ["Nearest tag", f"{rel['tag']} → {rel['tag_commit']} ({rel['tag_date']})"],
        ["Newest commit on main", f"{rel['head_short']} ({rel['distance']} commit(s) after the tag)"],
        ["Tag on remote", "Yes" if rel["on_origin"] else "No"],
        ["Latest published release", rel["latest_published"] or "Unknown"],
    ]
    return statements, rows, points


def collect_facts() -> dict:
    tracked = tracked_paths()
    untracked = untracked_paths()
    inventory = sorted(set(tracked) | set(untracked))
    languages, files, binary, missing = line_inventory(inventory)
    agents = workflow_agents()
    names = display_names(agents)
    wrapped = wrapped_tool_names()
    acpx_tools = acpx_tool_names()
    supervisors = supervisor_tool_names()
    skill_list = skills()
    fields, groups, model_agents = model_settings()
    version = version_info()
    head_short = git("rev-parse", "--short", "HEAD")
    published = published_releases()
    rel = release_facts(published, head_short)
    statements, rel_rows, rel_points = release_statements(rel, version["version"])
    js = sorted((AGENT_DIR / "static" / "agent" / "js").glob("*.js"))
    total_effective = sum(row.effective_lines for row in languages)
    total_physical = sum(row.total_lines for row in languages)
    vendored = [row for row in files if row.path.startswith(VENDOR_PREFIX)]
    vendored_effective = sum(row.effective_lines for row in vendored)
    tools = CORE_PYTHON_TOOLS + len(wrapped) + len(acpx_tools) + len(supervisors)
    now = datetime.now(DOCUMENT_TIMEZONE)
    commits = []
    for line in git("log", "-12", "--format=%h\x1f%cI\x1f%s").splitlines():
        sha, when, subject = line.split("\x1f", 2)
        commits.append([sha, short_date(when), subject])

    facts = {
        "generated_at": f"{MONTHS[now.month - 1]} {now.day}, {now.year} at {now.strftime('%H:%M')} "
                        f"(UTC{now.strftime('%z')[:3]}:{now.strftime('%z')[3:]})",
        "generated_date": f"{MONTHS[now.month - 1]} {now.day}, {now.year}",
        "head_short": head_short,
        "head_full": git("rev-parse", "HEAD"),
        "head_subject": git("show", "-s", "--format=%s", "HEAD"),
        "head_date": short_date(git("show", "-s", "--format=%cI", "HEAD")),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "version": version["version"],
        "version_source": version["source"],
        "release": rel,
        "release_tag": rel["tag"],
        "release_statements": statements,
        "release_rows": rel_rows,
        "release_points": rel_points,
        "timeline": tag_timeline(),
        "tracked": tracked,
        "tracked_count": len(tracked),
        "untracked": untracked,
        "inventory": inventory,
        "missing_paths": missing,
        "tree_text": build_tree(tracked),
        "languages": languages,
        "files": files,
        "binary_count": binary,
        "text_files": len(files),
        "total_effective": total_effective,
        "total_physical": total_physical,
        "agents_list": agents,
        "agents": len(agents),
        "display_names": names,
        "wrapped": len(wrapped),
        "core": CORE_PYTHON_TOOLS,
        "acpx_tools": len(acpx_tools),
        "acpx_tool_names": acpx_tools,
        "supervisors": len(supervisors),
        "supervisor_names": supervisors,
        "tools": tools,
        "skills": len(skill_list),
        "skill_names": skill_list,
        "acpx_peers": acpx_peers(),
        "catalog_sections": catalog_sections(),
        "parametrizer_sources": parametrizer_sources(),
        "model_fields": fields,
        "model_groups": groups,
        "model_agents": model_agents,
        "js": len(js),
        "css": len(list((AGENT_DIR / "static" / "agent" / "css").glob("*.css"))),
        "templates": len(list((AGENT_DIR / "templates" / "agent").glob("*.html"))),
        "migrations": len(list((AGENT_DIR / "migrations").glob("0*.py"))),
        "requirements": requirements_count(),
        "vendored_files": len(vendored),
        "vendored_effective": vendored_effective,
    }
    facts["fact_rows"] = [
        ["Inspected commit", f"{head_short} · {facts['head_date']} · branch {facts['branch']}"],
        ["Version", facts['version']],
        ["Tracked files", f"{len(tracked):,}"],
        ["Unignored working-tree additions", f"{len(untracked):,}"],
        ["Text files counted", f"{len(files):,}"],
        ["Binary assets (counted, not measured)", f"{binary:,}"],
        ["Physical text lines", f"{total_physical:,}"],
        ["Effective lines", f"{total_effective:,}"],
        ["Workflow agent types", f"{len(agents)}"],
        ["Wrapped chat-agent tools", f"{len(wrapped)}"],
        ["Built-in Multi-Turn tools", f"{tools} = {CORE_PYTHON_TOOLS} core + {len(wrapped)} wrapped + "
                                      f"{len(acpx_tools)} ACPX/Skill + {len(supervisors)} supervisors"],
        ["Skills", f"{len(skill_list)}"],
        ["ACPX peers", f"{len(facts['acpx_peers'])}"],
        ["Database migrations", f"{facts['migrations']}"],
        ["JavaScript modules · stylesheets · templates",
         f"{facts['js']} · {facts['css']} · {facts['templates']}"],
        ["Pinned Python requirements", f"{facts['requirements']}"],
        ["Catalog sections", f"{len(facts['catalog_sections'])}"],
        ["Central model settings", f"{fields} for {model_agents} model-backed agents"],
    ]
    facts["language_rows"] = [
        [row.language, f"{row.files:,}", f"{row.total_lines:,}", f"{row.effective_lines:,}",
         f"{row.effective_lines / total_effective:.1%}" if total_effective else "0%"]
        for row in languages
    ] + [["Total", f"{len(files):,}", f"{total_physical:,}", f"{total_effective:,}", "100.0%"]]
    authored_files = len(files) - len(vendored)
    facts["provenance_rows"] = [
        ["Tlamatini-authored text (application, agents, docs, tests)", f"{authored_files:,}",
         f"{total_effective - vendored_effective:,}"],
        ["Vendored frontend libraries (PDF.js, Bootstrap, jQuery …)", f"{len(vendored):,}",
         f"{vendored_effective:,}"],
        ["All text files", f"{len(files):,}", f"{total_effective:,}"],
    ]
    facts["largest_rows"] = [[row.path, row.language, f"{row.effective_lines:,}"]
                             for row in [r for r in files if not r.path.startswith(VENDOR_PREFIX)][:18]]
    facts["commit_rows"] = commits
    return facts


def serialize(facts: dict) -> dict:
    skip = {"languages", "files", "tree_text", "tracked", "inventory"}
    data = {key: value for key, value in facts.items() if key not in skip}
    data["languages"] = [row.__dict__ for row in facts["languages"]]
    data["largest_files"] = [row.__dict__ for row in facts["files"][:60]]
    data["tracked_paths"] = facts["tracked"]
    return data


def main() -> None:
    from dossier_content import build_chapters, validate_families
    from dossier_pdf import build_pdf
    from dossier_pptx import build_pptx
    from dossier_verify import verify_all

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    print("Collecting source, Git, release and line-count facts...", flush=True)
    facts = collect_facts()
    validate_families(facts["agents_list"])
    chapters = build_chapters(facts)
    TREE_OUTPUT.write_text(facts["tree_text"], encoding="utf-8")
    CONTEXT_OUTPUT.write_text(json.dumps(serialize(facts), indent=2, default=str), encoding="utf-8")
    print("Rendering the complete PDF dossier...", flush=True)
    pdf_pages = build_pdf(facts, chapters, PDF_OUTPUT)
    print(f"PDF written: {PDF_OUTPUT} ({pdf_pages} pages)")
    print("Rendering the complete PowerPoint dossier...", flush=True)
    slides = build_pptx(facts, chapters, PPT_OUTPUT)
    print(f"PPTX written: {PPT_OUTPUT} ({slides} slides)")
    report = verify_all(facts, PDF_OUTPUT, PPT_OUTPUT)
    VERIFY_OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Verification report: {VERIFY_OUTPUT}")
    if not report.get("clean"):
        raise SystemExit("Dossier verification FAILED; see the report above.")
    print("Dossier verification PASSED: no overflow, no clipping, complete tree parity.")


if __name__ == "__main__":
    main()
