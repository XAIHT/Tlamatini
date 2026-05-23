from __future__ import annotations

import ast
import io
import importlib.util
import json
import re
import subprocess
import tokenize
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Inches, Pt

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


SCRIPT_PATH = Path(__file__).resolve()
DOC_DIR = SCRIPT_PATH.parent
PROJECT_DIR = SCRIPT_PATH.parents[2]
REPO_ROOT = SCRIPT_PATH.parents[3]
BUILD_DIR = REPO_ROOT / "build" / "documentation_refresh"
REFERENCE_MEDIA_DIR = BUILD_DIR / "reference_ppt_media"

PDF_OUTPUT = REPO_ROOT / "tlamatini_app_summary.pdf"
PPT_OUTPUT = REPO_ROOT / "Tlamatini_eXtended_Artificial_Intelligence_Humanly_Tempered.pptx"
CONTEXT_OUTPUT = BUILD_DIR / "complete_project_dossier_context.json"
TREE_OUTPUT = BUILD_DIR / "complete_tracked_file_tree.txt"

BINARY_EXTENSIONS = {
    ".7z",
    ".dll",
    ".exe",
    ".flw",
    ".ico",
    ".jar",
    ".jpg",
    ".jpeg",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".pptx",
    ".pyc",
    ".wav",
    ".zip",
}

LANGUAGE_BY_EXTENSION = {
    ".bat": ("Batch", "Batch"),
    ".css": ("CSS", "CSS"),
    ".html": ("HTML", "HTML"),
    ".js": ("JavaScript", "JS"),
    ".json": ("JSON", "JSON"),
    ".md": ("Markdown", "MD"),
    ".mjs": ("JavaScript module", "MJS"),
    ".pmt": ("Prompt template", "Prompt"),
    ".proto": ("Protocol Buffers", "Proto"),
    ".ps1": ("PowerShell", "PowerShell"),
    ".py": ("Python", "Python"),
    ".txt": ("Text", "Text"),
    ".yaml": ("YAML", "YAML"),
    ".yml": ("YAML", "YAML"),
}

THEME = {
    "obsidian": RGBColor(8, 13, 13),
    "void": RGBColor(13, 18, 19),
    "stone": RGBColor(32, 35, 34),
    "panel": RGBColor(22, 26, 25),
    "panel2": RGBColor(34, 39, 36),
    "white": RGBColor(232, 232, 222),
    "muted": RGBColor(180, 186, 174),
    "copper": RGBColor(196, 128, 82),
    "copper2": RGBColor(142, 89, 52),
    "jade": RGBColor(72, 191, 143),
    "jade2": RGBColor(33, 127, 98),
    "amber": RGBColor(224, 171, 93),
    "line": RGBColor(89, 95, 86),
}

SLIDE_W = 13.333
SLIDE_H = 7.5
RECENT_GIT_WINDOW_DAYS = 1
RECENT_GIT_WINDOW_LABEL = "today"
RECENT_GIT_WINDOW_TITLE = "Today In Git"
RECENT_GIT_HIGHLIGHT_TITLE = "today's highlights"
RECENT_GIT_APPENDIX_SUBTITLE = "all commits from today according to git"


@dataclass
class LineStats:
    language: str
    short: str
    files: int = 0
    total_lines: int = 0
    effective_lines: int = 0


@dataclass
class FileStats:
    path: str
    language: str
    total_lines: int
    effective_lines: int


@dataclass
class CommitInfo:
    short_hash: str
    committed_at: str
    subject: str


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def local_stamp() -> str:
    return datetime.now().astimezone().strftime("%B %d, %Y %I:%M %p UTC%z")


def iso_date(iso_value: str) -> str:
    return datetime.fromisoformat(iso_value.replace("Z", "+00:00")).strftime("%Y-%m-%d")


def discover_reference_deck() -> Path | None:
    desktop = Path.home() / "OneDrive" / "Desktop"
    if not desktop.exists():
        desktop = Path.home() / "Desktop"
    matches = sorted(desktop.glob("TLAMATINI_ El Saber*.pptx"))
    return matches[0] if matches else None


def extract_reference_media() -> list[Path]:
    deck = discover_reference_deck()
    if deck is None or not deck.exists():
        return []
    REFERENCE_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    try:
        with ZipFile(deck) as archive:
            for name in archive.namelist():
                if not name.startswith("ppt/media/"):
                    continue
                suffix = Path(name).suffix.lower()
                if suffix not in {".png", ".jpg", ".jpeg"}:
                    continue
                target = REFERENCE_MEDIA_DIR / Path(name).name
                target.write_bytes(archive.read(name))
                extracted.append(target)
    except Exception:
        return []
    return extracted


def tracked_paths() -> list[str]:
    return [line for line in git("ls-files").splitlines() if line.strip()]


def build_tree(paths: list[str]) -> str:
    root: dict[str, dict] = {}
    for raw_path in sorted(paths):
        parts = raw_path.replace("\\", "/").split("/")
        node = root
        for part in parts:
            node = node.setdefault(part, {})

    def walk(node: dict, prefix: str = "") -> list[str]:
        lines: list[str] = []
        entries = sorted(node.items(), key=lambda item: (bool(item[1]), item[0].lower()))
        for index, (name, child) in enumerate(entries):
            last = index == len(entries) - 1
            connector = "`-- " if last else "|-- "
            suffix = "/" if child else ""
            lines.append(f"{prefix}{connector}{name}{suffix}")
            if child:
                extension = "    " if last else "|   "
                lines.extend(walk(child, prefix + extension))
        return lines

    return "Tlamatini/\n" + "\n".join(walk(root))


def detect_language(path: str) -> tuple[str, str]:
    suffix = Path(path).suffix.lower()
    return LANGUAGE_BY_EXTENSION.get(suffix, ("Other text", "Other"))


def looks_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        chunk = path.read_bytes()[:2048]
    except OSError:
        return True
    return b"\x00" in chunk


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
    doc_lines: set[int] = set()
    candidates = [tree, *[node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]]
    for node in candidates:
        if not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            start = getattr(first, "lineno", None)
            end = getattr(first, "end_lineno", start)
            if start and end:
                doc_lines.update(range(start, end + 1))
    return doc_lines


def count_python_effective(text: str) -> int:
    doc_lines = python_docstring_lines(text)
    effective_lines: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type in {
                tokenize.COMMENT,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.ENCODING,
                tokenize.ENDMARKER,
                tokenize.INDENT,
                tokenize.DEDENT,
            }:
                continue
            line_number = token.start[0]
            if line_number not in doc_lines:
                effective_lines.add(line_number)
    except tokenize.TokenError:
        return count_generic_effective(text, ".py")
    return len(effective_lines)


def remove_block_comments(text: str, suffix: str) -> str:
    if suffix in {".js", ".mjs", ".css", ".proto"}:
        return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    if suffix == ".html" or suffix == ".md":
        return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    if suffix == ".ps1":
        return re.sub(r"<#.*?#>", "", text, flags=re.DOTALL)
    return text


def strip_inline_comment(line: str, suffix: str) -> str:
    stripped = line.strip()
    if suffix in {".yaml", ".yml", ".ps1"}:
        return "" if stripped.startswith("#") else line
    if suffix in {".js", ".mjs", ".css", ".proto"}:
        return "" if stripped.startswith("//") else line
    if suffix == ".bat":
        lowered = stripped.lower()
        return "" if lowered.startswith("rem ") or stripped.startswith("::") else line
    return line


def count_generic_effective(text: str, suffix: str) -> int:
    text = remove_block_comments(text, suffix)
    count = 0
    for raw_line in text.splitlines():
        line = strip_inline_comment(raw_line, suffix)
        if line.strip():
            count += 1
    return count


def line_stats_for_paths(paths: list[str]) -> tuple[list[LineStats], list[FileStats], int, int]:
    by_language: dict[str, LineStats] = {}
    file_rows: list[FileStats] = []
    binary_count = 0
    skipped_count = 0

    for rel_path in paths:
        absolute = REPO_ROOT / rel_path
        text = read_text(absolute)
        if text is None:
            if absolute.suffix.lower() in BINARY_EXTENSIONS:
                binary_count += 1
            else:
                skipped_count += 1
            continue

        language, short = detect_language(rel_path)
        total = len(text.splitlines())
        suffix = absolute.suffix.lower()
        effective = count_python_effective(text) if suffix == ".py" else count_generic_effective(text, suffix)

        stats = by_language.setdefault(language, LineStats(language=language, short=short))
        stats.files += 1
        stats.total_lines += total
        stats.effective_lines += effective
        file_rows.append(FileStats(rel_path, language, total, effective))

    language_rows = sorted(by_language.values(), key=lambda item: item.effective_lines, reverse=True)
    file_rows.sort(key=lambda item: item.effective_lines, reverse=True)
    return language_rows, file_rows, binary_count, skipped_count


def recent_commits(limit: int = 10) -> list[CommitInfo]:
    raw = git("log", f"-n{limit}", "--format=%h%x1f%cI%x1f%s")
    commits: list[CommitInfo] = []
    for line in raw.splitlines():
        short_hash, committed_at, subject = line.split("\x1f", 2)
        commits.append(CommitInfo(short_hash, committed_at, subject))
    return commits


def recent_week_commits(days: int = RECENT_GIT_WINDOW_DAYS) -> list[CommitInfo]:
    now = datetime.now().astimezone()
    if RECENT_GIT_WINDOW_LABEL == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    else:
        since = (now - timedelta(days=days)).isoformat()
    raw = git("log", f"--since={since}", "--format=%h%x1f%cI%x1f%s")
    commits: list[CommitInfo] = []
    for line in raw.splitlines():
        short_hash, committed_at, subject = line.split("\x1f", 2)
        commits.append(CommitInfo(short_hash, committed_at, subject))
    return commits


def weekly_highlights(commits: list[CommitInfo]) -> list[str]:
    subjects = [commit.subject.lower() for commit in commits]
    highlights: list[str] = []
    if any("kalier" in subject or "kali" in subject or "pentest" in subject for subject in subjects):
        highlights.append(
            "Today’s headline change is the new Kalier agent in `v1.7.0`: Tlamatini now reaches 67 workflow agents and adds a direct bridge into Kali Linux offensive-security tooling through MCP-Kali-Server, available from both Multi-Turn chat and the visual canvas."
        )
    if any("windower" in subject or "window manager" in subject or "window" in subject and "multi-turn" in subject for subject in subjects):
        highlights.append(
            "Today’s headline change is the new Windower agent: Tlamatini now reaches 66 workflow agents and adds a deterministic Win32 window-manager surface for focusing, tiling, resizing, listing, and closing windows from both Multi-Turn chat and the visual canvas."
        )
    if any("playwrighter" in subject or "playwright" in subject for subject in subjects):
        highlights.append(
            "Today’s headline change is the new Playwrighter agent in `v1.5.0`: Tlamatini now adds its 65th workflow agent and a real-browser automation surface for scripted Playwright flows from both Multi-Turn chat and the visual canvas."
        )
    if any("tkinter" in subject or "unstable" in subject or "native dialog" in subject for subject in subjects):
        highlights.append(
            "The immediately previous stability pass is still visible in Git too: Tkinter was removed from the unstable runtime-facing dialog path in favor of native Windows dialog helpers, reducing UI instability around file and folder picking while keeping the browser/operator flow intact."
        )
    if any("reporting tables" in subject or "widths" in subject for subject in subjects):
        highlights.append(
            "Reporting-table layout was also tightened during the same window, improving readability of generated execution/reporting surfaces without changing the underlying operational data."
        )
    if any(("reviewer" in subject and "state" in subject) or ("reviewer" in subject and "handling" in subject) for subject in subjects):
        highlights.append(
            "Today’s reviewer follow-up is a behavioral-accuracy patch: the review prompt now distinguishes uncommitted working-tree diffs from committed history and teaches the model Tlamatini’s managed-secret scrub convention, reducing false positives around local credentials in config files."
        )
    if any("reviewer" in subject or "analyzer" in subject or "security audit" in subject or "code review" in subject for subject in subjects):
        highlights.append(
            "Today’s headline change is the new Reviewer and Analyzer surfaces: the workflow-agent catalog now reaches 64 templates, the seed-skill catalog reaches 23 packages, and code review plus deterministic security scanning are now available from both the canvas and the skill layer."
        )
    if any("number and descriptions of agents" in subject or "markdowns" in subject or "agentic_skill" in subject for subject in subjects):
        highlights.append(
            "Today’s headline change is agent-catalog consistency: the live count, the markdown bestiaries, the flow-creator skill catalog, and the sidebar-description source were brought back into alignment around one shared workflow-agent inventory."
        )
    if any("unreal" in subject or "unreal-engine mcp" in subject or "unreal engine enabled" in subject for subject in subjects):
        highlights.append(
            "Today’s headline change is Unreal MCP support: the new Unrealer agent, a chat-wrapped `chat_agent_unrealer` tool, canvas wiring, a seeded end-to-end demo prompt, and a direct TCP bridge into a live Unreal Engine 5 editor."
        )
    if any("orphan" in subject or "cleanup" in subject or "sec/perf" in subject for subject in subjects):
        highlights.append(
            "Today’s headline change is orphan-process cleanup on Windows: a three-tier reaper, hardened detached spawn sites, ACPX process-tree termination, and user-visible survivor reporting when anything truly refuses to die."
        )
    if any("de-compresser" in subject or "de compresser" in subject for subject in subjects):
        highlights.append(
            "Today’s headline change is the new De-Compresser agent: deterministic archive compression/decompression, Multi-Turn exposure, ACP canvas wiring, and a requirements patch that adds the `py7zr` fallback path."
        )
    if any("version" in subject or "worldwide system" in subject for subject in subjects):
        highlights.append(
            "Today’s headline change is the new versioning system: SemVer policy, git-tag sourcing, runtime version surfaces, and build-time embedding across the Windows artefacts."
        )
    if any("menu db" in subject or "database" in subject or "browse buttons" in subject for subject in subjects):
        highlights.append(
            "Today’s operator-facing work is dominated by the new DB dropdown: backup, Set DB staging for the next start-up, startup swap-in/rollback mechanics, and native Browse buttons on both dialogs."
        )
    if any("gpu" in subject or "autoload" in subject or "spining" in subject for subject in subjects):
        highlights.append(
            f"GPU-host behavior changed during the {RECENT_GIT_WINDOW_LABEL}: performance hooks, model-pinning startup behavior, and autoload-at-restart reliability were all touched."
        )
    if any("reconnection" in subject or ("config" in subject and "dialog" in subject) for subject in subjects):
        highlights.append(
            "The config-plane UI grew another safety layer: when model/URL dialog saves materially change live runtime inputs, the chat now prompts the operator to reconnect before trusting the current session state."
        )
    if any("acpx" in subject for subject in subjects):
        highlights.append(
            f"ACPX-related work remained visible during the {RECENT_GIT_WINDOW_LABEL}: runtime, documentation, or operator-surface changes were still part of the active maintenance stream."
        )
    if any("shortcut" in subject or "restrictive" in subject or "policy" in subject for subject in subjects):
        highlights.append(
            "Windows deployment hardening continued with CreateShortcut fixes and improved behavior on restricted-policy machines."
        )
    if any("teletlamatini" in subject for subject in subjects):
        highlights.append(
            "TeleTlamatini grew throughout the window, including agent/runtime updates, config movement, FlowCreator/ACPX integration, and related documentation changes."
        )
    if any("compiler" in subject or "contract" in subject for subject in subjects):
        highlights.append(
            "The current Git window still shows the flow compiler / agent-contract direction influencing how chat-created and ACP-created workflows converge."
        )
    if any("multi-turn" in subject or "multi turn" in subject or "tool quota" in subject for subject in subjects):
        highlights.append(
            "Multi-Turn behavior kept evolving across the period through quota tuning, execution-table persistence, autonomous-action improvements, and broader tool enablement."
        )
    if any("scroll" in subject or "icon" in subject or "web page" in subject or "scheme" in subject for subject in subjects):
        highlights.append(
            "The operator surface evolved too: ACP/ACPX visual mechanics, canvas scrolling, icons, and page framing all received polish."
        )
    if any("persistent" in subject or "execution table" in subject or "summarizer" in subject for subject in subjects):
        highlights.append(
            "Execution observability improved through persistent execution tables, summarizer work, and the broader reportability push around agent runs."
        )
    if any("document" in subject or "docs" in subject or "framing" in subject for subject in subjects):
        highlights.append(
            "Documentation itself changed today, so the regenerated dossier is part of the tracked operator surface rather than an external afterthought."
        )
    if highlights:
        return highlights
    if RECENT_GIT_WINDOW_LABEL == "today":
        return ["Git history today shows focused maintenance across the operator surface, release mechanics, and runtime behavior."]
    return [f"Git history shows focused maintenance across the operator surface, release mechanics, and runtime behavior during {RECENT_GIT_WINDOW_LABEL}."]


def _load_module_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_version_info() -> dict[str, str]:
    version_module_path = PROJECT_DIR / "agent" / "version.py"
    try:
        module = _load_module_from_path("tlamatini_agent_version", version_module_path)
        info = module.get_version_info()
        if isinstance(info, dict):
            return {
                "version": str(info.get("version", "0.0.0+unknown")),
                "build": str(info.get("build", "0.0.0+unknown")),
                "commit": str(info.get("commit", "unknown")),
                "date": str(info.get("date", "")),
                "source": str(info.get("source", "unknown")),
            }
    except Exception:
        pass
    return {
        "version": "0.0.0+unknown",
        "build": "0.0.0+unknown",
        "commit": "unknown",
        "date": "",
        "source": "unknown",
    }


def workflow_agents() -> list[str]:
    agents_root = PROJECT_DIR / "agent" / "agents"
    names = []
    for entry in agents_root.iterdir():
        if entry.is_dir() and (entry / "config.yaml").exists() and entry.name != "pools":
            names.append(entry.name)
    return sorted(names)


def count_requirements() -> int:
    count = 0
    for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def count_agent_description_rows() -> int:
    path = REPO_ROOT / "agents_descriptions.md"
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("| **") and "| Agent |" not in stripped and "| Purpose |" not in stripped:
            count += 1
    return count


def count_wrapped_chat_agent_tools() -> int:
    path = PROJECT_DIR / "agent" / "chat_agent_registry.py"
    text = path.read_text(encoding="utf-8")
    return len(re.findall(r'tool_name\s*=\s*"([^"]+)"', text))


def count_skills() -> int:
    skills_root = PROJECT_DIR / "agent" / "skills_pkg"
    return sum(1 for entry in skills_root.iterdir() if entry.is_dir() and (entry / "SKILL.md").exists())


def collect_context() -> dict:
    paths = tracked_paths()
    tree_text = build_tree(paths)
    language_rows, file_rows, binary_count, skipped_count = line_stats_for_paths(paths)
    total_effective = sum(row.effective_lines for row in language_rows)
    total_lines = sum(row.total_lines for row in language_rows)
    agents = workflow_agents()
    wrapped_chat_tools = count_wrapped_chat_agent_tools()
    skills_count = count_skills()
    reference_media = extract_reference_media()
    weekly = recent_week_commits()
    version_info = resolve_version_info()

    context = {
        "generated_at": local_stamp(),
        "head_short": git("rev-parse", "--short", "HEAD"),
        "head_full": git("rev-parse", "HEAD"),
        "head_subject": git("show", "-s", "--format=%s", "HEAD"),
        "head_date": git("show", "-s", "--format=%cI", "HEAD"),
        "tracked_files": len(paths),
        "tracked_paths": paths,
        "tree_text": tree_text,
        "language_rows": language_rows,
        "file_rows": file_rows,
        "binary_count": binary_count,
        "skipped_count": skipped_count,
        "total_effective_lines": total_effective,
        "total_lines": total_lines,
        "workflow_agents": agents,
        "workflow_agent_count": len(agents),
        "agent_description_rows": count_agent_description_rows(),
        "wrapped_chat_agent_count": wrapped_chat_tools,
        "core_python_tool_count": 20,
        "acpx_tool_count": 12,
        "total_multi_turn_tools": 20 + wrapped_chat_tools + 12,
        "skills_count": skills_count,
        "requirements_count": count_requirements(),
        "js_modules": len(list((PROJECT_DIR / "agent" / "static" / "agent" / "js").glob("*.js"))),
        "css_files": len(list((PROJECT_DIR / "agent" / "static" / "agent" / "css").glob("*.css"))),
        "html_templates": len(list((PROJECT_DIR / "agent" / "templates" / "agent").glob("*.html"))),
        "migrations": len(list((PROJECT_DIR / "agent" / "migrations").glob("*.py"))) - 1,
        "recent_commits": recent_commits(),
        "weekly_commits": weekly,
        "weekly_highlights": weekly_highlights(weekly),
        "reference_media": reference_media,
        "version_info": version_info,
    }
    return context


SYSTEM_OVERVIEW = [
    "Tlamatini is a local-first AI developer assistant built with Django, Django Channels, LangChain, LangGraph, FAISS/BM25 retrieval, and a large in-repository agent application.",
    "It combines a browser chat surface, a Retrieval-Augmented Generation stack, a Multi-Turn tool executor, MCP-backed context providers, wrapped chat-agent runtimes, and a visual Agentic Control Panel for workflow design.",
    "The platform is designed for development operations: codebase analysis, file and directory context, command execution, Python execution, screenshots, web/search helpers, notifications, DevOps tools, local model operation, and Windows packaging.",
]

WHAT_IT_DOES = [
    "Answers codebase questions with loaded file or directory context.",
    "Uses hybrid retrieval to extract metadata, split content, rank source chunks, and respect context budgets.",
    "Gives operators GUI-first database maintenance through the new DB dropdown for backup and staged database replacement.",
    "Warns GPU-host operators before a directory-context load is likely to saturate VRAM and degrade embedding throughput.",
    "Exposes a coherent versioning surface across builds, runtime UI, logs, and an open health-check endpoint.",
    "Can command Kali Linux offensive-security tooling through MCP-Kali-Server for authorized recon, enumeration, web scanning, and assessment workflows.",
    "Can manage real desktop windows by title: focus them, tile them, resize them, list them, and close them deterministically through Win32 calls.",
    "Can drive a real Playwright browser through scripted interactive steps for logins, forms, assertions, downloads, extraction, and end-to-end UI checks.",
    "Can drive a live Unreal Engine 5 editor through the Unreal MCP plugin, from either Multi-Turn chat or the visual workflow canvas.",
    "Actively reaps orphaned Windows console-host and pool-child processes so long Multi-Turn or ACPX sessions do not leave misleading Tlamatini-icon ghosts in Task Manager.",
    "Runs checked Multi-Turn requests through request-scoped planning, capability selection, tool calls, observations, monitoring, and final synthesis.",
    "Launches wrapped copies of selected workflow agents in isolated runtime folders without mutating templates.",
    "Lets users design, validate, save, pause, resume, and stop visual workflows through the Agentic Control Panel.",
    "Turns successful Multi-Turn tool executions into starter `.flw` workflows that can be inspected and validated in ACP.",
    "Packages the project into a distributable Windows release with installer and uninstaller tooling.",
]

HOW_IT_WORKS = [
    "Browser UI sends chat and workflow requests through Django views and Channels WebSockets.",
    "RAG chains load selected file/directory context, retrieve relevant chunks, and build answer prompts.",
    "DB-menu actions validate directories or SQLite files in the browser, then call Django views that either copy the live database out or stage a replacement into `DB/ToLoad/db.sqlite3`.",
    "Before a heavy directory embedding run on supported NVIDIA hosts, a fail-open pre-flight guard can estimate VRAM pressure and surface a non-blocking warning in chat.",
    "Version resolution now flows through git tags, a runtime resolver module, generated build artefacts, and an open `/agent/version/` endpoint.",
    "When Multi-Turn is enabled, the global planner selects context and tool stages before the executor binds only the relevant tools, including wrapped deterministic agents such as De-Compresser.",
    "The Kalier path talks directly to the MCP-Kali-Server Flask API over HTTP with Python-stdlib `urllib`, choosing one offensive-security capability per call and capturing the result in one atomic `INI_SECTION_KALIER` block.",
    "The Windower path uses Win32 APIs plus the cross-process `AttachThreadInput` focus-transfer dance to locate windows by title and apply one lifecycle action while still returning structured geometry/state fields.",
    "The Playwrighter path loads a declarative step list, drives Playwright against Chromium/Firefox/WebKit, and emits one atomic `INI_SECTION_PLAYWRIGHTER` block with status, assertions, extracted values, and the final URL.",
    "The Unrealer path opens a TCP socket to the Unreal MCP plugin, sends one `{\"type\": command, \"params\": {...}}` payload, captures the JSON reply, and emits one `INI_SECTION_UNREALER` block for downstream logic.",
    "After spawn-capable tool calls and again after the final answer, the orphan reaper can sweep dead descendants, orphaned `conhost.exe` companions, and stale pool-linked processes without ever raising into the chat path.",
    "Tool calls execute in the backend, append observations, and may create wrapped runtime copies under `agent/agents/pools/_chat_runs_/`.",
    "On the next full start-up, `manage.py` can swap a staged database into place before Django imports, while archiving the previous live database under `DB/Older/<timestamp>/`.",
    "ACP flows deploy session-scoped pool instances, wire config values, validate NxN graph rules, and execute through Starter-driven flow semantics.",
    "Build scripts collect static assets, bundle Django/Python resources, add agent templates, and assemble `pkg.zip`, `Uninstaller.exe`, and `dist/Tlamatini_Release/`.",
]

HOW_TO_USE = [
    "Run from source: create a virtual environment, install requirements, migrate, create a superuser, collect static files, and start Django.",
    "Open `/agent/` for chat. Load a file or directory context before asking codebase-specific questions.",
    "Keep Multi-Turn unchecked for direct Q&A; enable Multi-Turn for tasks that need tools, wrapped agents, monitoring, or workflow seeding.",
    "For authorized Kali Linux assessments, run MCP-Kali-Server on the Kali box, expose it locally or through an SSH tunnel, and call `chat_agent_kalier` from Multi-Turn with the desired `action`, `target`, and `server_url`.",
    "For desktop-window control, call `chat_agent_windower` from Multi-Turn to focus, tile, resize, list, or close a window by title, or model the same action in ACP with the Windower node.",
    "For interactive web automation, call `chat_agent_playwrighter` from Multi-Turn with a `steps_json` script, or author the same step list visually with the Playwrighter node on the canvas.",
    "For Unreal Engine work, enable the Unreal MCP plugin inside a live UE5 project first, then call `chat_agent_unrealer` from Multi-Turn or use the visual Unrealer node on the canvas.",
    "Archive jobs can now be described directly in Multi-Turn or modeled visually in ACP: De-Compresser infers compress vs decompress from the `input` or `output` extension.",
    "If a second post-answer warning bubble ever lists surviving `name + PID` entries, treat it as an honest cleanup report and end the listed processes manually from Task Manager if needed.",
    "Use the `ACPX-Skills` navbar menu when you need to browse, enable/disable, diagnose, or reload the shipped SKILL.md catalog without asking the LLM to be your admin surface.",
    "Use the DB dropdown when you need a safe database snapshot or want to stage a different `db.sqlite3` for the next start-up without hot-swapping the live SQLite file.",
    "Open `/agentic_control_panel/` to drag agents, connect them, configure each node, validate, start, pause/resume, stop, and save `.flw` workflows.",
    "Use `python build.py`, `python build_uninstaller.py`, and `python build_installer.py` only when producing a packaged Windows release.",
]

AGENT_DESCRIPTION_GUIDE = [
    "The authoritative human-readable source for workflow-agent descriptions is `agents_descriptions.md` at the repo root, not an embedded JavaScript map or a hard-coded Django list.",
    "Current validation compares live template directories, `agents_descriptions.md` rows, and the README / Book bestiary counts so the generated dossier stays aligned with the running product.",
    "The ACP sidebar hover tooltip and the right-click Description dialog both resolve through that markdown file first; `README.md` is only a legacy fallback when the dedicated description file is absent.",
]

AGENT_RUNTIME_GUIDE = [
    "Every workflow agent follows the same operational skeleton: template directory, `config.yaml`, a session-scoped pool copy, PID/status/log files, and explicit source/target wiring.",
    "Chat-wrapped tool calls launch isolated runtime copies under `agent/agents/pools/_chat_runs_/`, while ACP uses named pool folders such as `starter_1` or `unrealer_1`.",
    "Specialized agents now stretch the platform in different directions: ACPXer drives external coding-agent CLIs, Kalier drives a remote or tunneled Kali Linux tool server, Unrealer drives a live UE5 editor, and TeleTlamatini / WhatsTlamatini bridge full Tlamatini conversations into messaging platforms.",
]

ACPX_SKILLS_GUIDE = [
    "The new `ACPX-Skills` navbar menu gives operators four direct actions over the skill catalog: Browse Skills, Configure Skills, Diagnostics, and Reload Registry.",
    "`Configure Skills` flips `Skill.enabled` exactly the way MCPs and Tools are toggled, so disabled skills disappear from `list_skills` and reject `invoke_skill` with `SKILL_DISABLED` instead of silently half-working.",
    "The diagnostics view cross-checks skill dependencies against disabled tools, disabled MCPs, missing ACPX agents, and orphan database rows whose SKILL.md disappeared from disk.",
]

OPERATOR_SURFACE_COUNTS_GUIDE = [
    "The live operator surface now stands at 67 workflow agents, 74 Multi-Turn tools, 12 ACPX tools, and 24 skills.",
    "Source inspection confirms the newer total: 42 wrapped chat-agent tools in `chat_agent_registry.py`, which combines with 20 core Python tools and 12 ACPX/Skill tools for 74 Multi-Turn tools overall.",
    "Some README lines still show the pre-Kalier 73-tool figure, so this dossier prefers the newer Book/git/live-registry state while preserving the rest of the README operator guidance.",
    "This matters operationally because the planner never binds everything at once: the documented default `max_selected_tools` cap stays at 20, so breadth of capability does not mean uncontrolled tool sprawl per turn.",
]

PROMPT_CATALOG_GUIDE = [
    "Version `1.3.2` tightened the HTML answer contract with a Prime Directive on visual readability: explicit background and text color, no grey-on-dark body text, and safer table-body defaults.",
    "The seeded `Prompts` dropdown was also re-sorted into a learner path: context-only Q&A first, then metrics, files search, shell, code generation, vision, specialized single-tool actions, agent control, Unrealer, and heavier Multi-Turn/ACPX demos last.",
    "Those readability rules remain in force in the current documentation set, and the newer `v1.7.0` release state keeps the version badge, runtime surfaces, and operator handbook aligned.",
]

REVIEWER_ANALYZER_GUIDE = [
    "The workflow catalog now includes two new high-value specialists: Reviewer and Analyzer, lifting the canvas inventory to 64 agents and the seed-skill catalog to 23 SKILL.md packages.",
    "Reviewer is LLM-powered: it resolves a git diff for `repo_path`, reviews it with a senior-engineer prompt, and emits an `INI_SECTION_REVIEWER` block whose first routable field is `verdict = APPROVE | REQUEST_CHANGES | COMMENT`.",
    "Analyzer is deterministic and scanner-driven: it runs whichever of `bandit`, `semgrep`, `ruff`, `eslint`, `gitleaks`, and `pip-audit` are installed on PATH over `target_path`, then emits an `INI_SECTION_ANALYZER` block with `status` and `total_findings` for downstream routing.",
]

REVIEWER_ANALYZER_SURFACES = [
    "Both agents always trigger `target_agents`, so a downstream Forker can branch on `{verdict}`, `{status}`, or `{total_findings}` instead of scraping prose.",
    "They are intentionally canvas-only workflow agents: there is no wrapped `chat_agent_reviewer` or `chat_agent_analyzer`, and therefore no duplicate Exec Report row family for those names.",
    "The chat-side counterparts live in the ACPX skill catalog instead: `code-review` exposes senior-engineer git-diff review, while `security-audit` exposes the deterministic multi-scanner sweep.",
]

REVIEWER_PRECISION_GUIDE = [
    "The `v1.4.1` Reviewer refinement tightened accuracy rather than adding a new surface: when `diff_ref` is empty, the review prompt labels the diff as the uncommitted working tree plus staged area, so the model must not describe those findings as already committed or pushed.",
    "The same patch teaches the model Tlamatini’s managed-secret convention: `agent/config.json` and selected `agent/agents/*/config.yaml` files can hold live local credentials in a keyed working copy, while `regen_secrets.py --mode push-able` scrubs them back to placeholders before commit.",
    "That guidance is mirrored into the `code-review` SKILL.md package too, keeping the chat-surface review behavior and the canvas Reviewer agent aligned on commit-state wording and secret-severity expectations.",
]

NATIVE_DIALOGS_GUIDE = [
    "The current tagged release `v1.4.2` removes Tkinter from the unstable runtime-facing dialog path and replaces it with `Tlamatini/agent/native_dialogs.py`, a native Windows dialog bridge used by browser-triggered pickers.",
    "This change pairs with the existing DB and operator dialogs: file and folder selection still feels local and GUI-first, but the fragile Tkinter dependency is no longer part of the interactive runtime path that users trigger from chat or ACP surfaces.",
    "The patch arrived with dedicated tests (`test_native_dialogs.py`) and with follow-up orphan-reaper/runtime adjustments, so the release reads as a stability pass rather than a cosmetic refactor.",
]

PLAYWRIGHTER_GUIDE = [
    "Playwrighter is the new 65th workflow agent in `v1.5.0`: a deterministic Playwright-powered browser automator for Chromium, Firefox, or WebKit that executes ordered interactive steps instead of static fetches.",
    "It covers the gap between Crawler and Googler: logins, multi-step forms, wizard clicks, JS-rendered SPA scraping, screenshots after interaction, assertions, downloads, and authenticated end-to-end UI checks.",
    "The agent emits `INI_SECTION_PLAYWRIGHTER` with `start_url`, `final_url`, `status`, `steps_run`, `assert_result`, and extracted values so downstream Forker or Parametrizer logic can branch on pass/fail or reuse scraped data.",
]

PLAYWRIGHTER_SURFACES_GUIDE = [
    "Two operator surfaces ship in lock-step: the wrapped Multi-Turn tool `chat_agent_playwrighter` takes the whole script as `steps_json`, while the visual Playwrighter canvas node stores the same declarative step list in YAML.",
    "Session continuity is built in: `headless: false` lets operators watch it drive, and `storage_state_in` / `storage_state_out` carry login state across runs without forcing a manual browser setup each time.",
    "Because Playwrighter is state-changing, its executions appear in Exec Report and it always triggers `target_agents` whether the run succeeds or fails.",
]

WINDOWER_GUIDE = [
    "Windower is the new 66th workflow agent: a deterministic Win32 window manager that finds an application window by title and performs one lifecycle operation on the window itself instead of clicking inside it.",
    "It supports `focus`, `minimize`, `maximize`, `restore`, `move`, `resize`, `move_resize`, `close`, `topmost`, `untopmost`, `arrange`, and `list`, with `substring`, `exact`, or `regex` title matching plus `match_index` for duplicate titles.",
    "The agent emits `INI_SECTION_WINDOWER` with `action`, `window_title`, `matched`, `match_count`, `state`, `left`, `top`, `width`, and `height`, so downstream Forker or Parametrizer logic can branch on presence, state, or geometry.",
]

WINDOWER_SURFACES_GUIDE = [
    "Two operator surfaces ship in lock-step: the wrapped Multi-Turn tool `chat_agent_windower` accepts free-form key=value requests, while the visual Windower canvas node stores the same operation fields in YAML.",
    "Windower is the desktop-window sibling of Mouser and Keyboarder: use Windower when the goal is the window as a whole, Mouser for controls inside it, and Keyboarder for text entry into it.",
    "Because Windower changes real window state, its executions appear in Exec Report and it always triggers `target_agents` whether the action succeeds or fails.",
]

KALIER_GUIDE = [
    "Kalier is the new 67th workflow agent in `v1.7.0`: a deterministic bridge from Tlamatini into Kali Linux offensive-security tooling through MCP-Kali-Server.",
    "It can issue one capability per run, including `nmap`, `gobuster`, `dirb`, `nikto`, `sqlmap`, `metasploit`, `hydra`, `john`, `wpscan`, `enum4linux`, arbitrary `command`, or a safe `health` probe of the remote server.",
    "The agent emits `INI_SECTION_KALIER` with `action`, `endpoint`, `subject`, `return_code`, `success`, `timed_out`, and `server_url`, so downstream Forker or Parametrizer logic can branch on results without scraping prose.",
]

KALIER_SURFACES_GUIDE = [
    "Two operator surfaces ship in lock-step: the wrapped Multi-Turn tool `chat_agent_kalier` accepts free-form key=value requests, while the visual Kalier canvas node stores the same operation fields in YAML.",
    "Kalier talks straight to the Kali-side Flask API over HTTP using Python-stdlib `urllib`, so it stays self-contained in the pool subprocess and works the same in source or frozen builds.",
    "Authorized use only: the intended operator flow is an in-scope lab, CTF, or permitted engagement, often with `ssh -L 5000:localhost:5000 user@KALI_IP` tunneling a remote Kali box back to `http://127.0.0.1:5000`.",
]

DESIGN_PRINCIPLES = [
    "Evidence-first answers: Tlamatini grounds responses in selected project context and hybrid retrieval rather than freeform model memory.",
    "Explicit orchestration: checked Multi-Turn uses a visible tool loop, capability scoring, and staged planning instead of a single opaque call.",
    "Operational reversibility: risky changes such as database replacement are staged, archived, and delayed to the only safe window instead of hot-swapped mid-session.",
    "Fail-open diagnostics: GPU pressure probes and session-restore safeguards warn early without breaking CPU-only or degraded environments.",
    "Runtime isolation: wrapped chat-agent copies run in session-scoped folders so template agents remain pristine while live runs stay inspectable.",
    "Operator truth over vibes: Exec Report tables, tlamatini.log, skill audits, and ACPX transcripts make the system auditable after execution.",
]

INSTALLATION_GUIDE = [
    "Python 3.12.10 is the strongly recommended source-mode version in the README, and the codebase has been tested most deeply there.",
    "Source installs require a clone, virtual environment, dependency install from `requirements.txt`, migrations, a superuser, static collection, and then the web server.",
    "You can run either the checked-in cloud/back-end defaults from `Tlamatini/agent/config.json` or a local Ollama-backed configuration with matching model names.",
    "Packaged Windows installs create a default `user / changeme` account; manual source installs use your own `createsuperuser` account instead.",
]

CONFIGURATION_GUIDE = [
    "Source mode resolves `Tlamatini/agent/config.json`; frozen builds resolve `config.json` next to the executable; `CONFIG_PATH` overrides both.",
    "Core keys include `embeding-model`, `chained-model`, `ollama_base_url`, `ollama_token`, `enable_unified_agent`, `unified_agent_model`, and `unified_agent_max_iterations`.",
    "The chat-side Config -> Models and Config -> URLs dialogs are now first-class configuration surfaces, and they can explicitly ask the operator to reconnect when saved values change live-session assumptions.",
    "The separate DB dropdown is not a config editor: it is a maintenance surface for copying the live SQLite database out or staging a replacement for the next full start-up.",
    "Multi-Turn is toggled from the chat toolbar, but it depends on the unified-agent configuration and the selected model/base-url pairing being valid.",
    "Image interpretation can run through Claude-backed cloud paths or Qwen/Ollama-backed local paths, and remote Ollama can be protected with a bearer token.",
]

RUNNING_GUIDE = [
    "Development server: `python Tlamatini/manage.py runserver --noreload`.",
    "Preferred async/dev bootstrap: `python Tlamatini/manage.py startserver`, which starts MCP services before the Django server.",
    "Production-style ASGI entrypoint: `daphne -b 127.0.0.1 -p 8000 tlamatini.asgi:application`.",
    "Current startup also re-applies GPU-performance / Ollama-pinning hooks in the background on supported NVIDIA Windows hosts, so restart-time behavior stays closer to the tuned development baseline.",
    "That same early startup window is also where a staged `DB/ToLoad/db.sqlite3` file is promoted into the live database path, before Django opens SQLite.",
    "Startup now also prints a `--- [VERSION] Tlamatini ...` banner, making the running build visible in both the console and `tlamatini.log` without an HTTP call.",
    "Startup cleans pool state, repopulates the agent registry, launches MCP metrics/file-search servers, and then serves HTTP plus WebSocket traffic.",
]

DB_MENU_GUIDE = [
    "The new DB dropdown gives operators two GUI-first maintenance paths: `Backup database` copies the live SQLite file out, and `Set DB` stages a chosen `db.sqlite3` for the next full start-up.",
    "Both dialogs are live-validated in the browser and now expose Browse buttons that open native host-side pickers for folders or `db.sqlite3` files.",
    "Backup is read-only and uses the currently live database path; Set DB never hot-swaps the file mid-session because Django already holds SQLite open.",
]

DB_SWAP_GUIDE = [
    "Set DB writes the selected file to `DB/ToLoad/db.sqlite3`; the real swap happens only at the top of `manage.py` before Django imports anything.",
    "When that swap runs, the previous live database is moved into `DB/Older/<timestamp>/db.sqlite3`, creating a built-in rollback trail instead of overwriting history.",
    "Reconnect is not enough for this path: the operator must fully restart Tlamatini so the pre-Django swap window opens again.",
    "If the staged file is bad or locked, startup fails open: Tlamatini logs the error and continues with the previous live database.",
]

VERSIONING_GUIDE = [
    "Tlamatini now follows Semantic Versioning 2.0.0 with git tags as the single source of truth: you tag, then you build, instead of hand-editing version strings across files.",
    "The build path resolves a version once and propagates it into generated runtime metadata, Win32 VERSIONINFO resources, and the release-folder naming convention.",
    "On untagged commits the resolver falls back honestly to a git-derived development version instead of failing the build or lying about the release state.",
]

VERSION_SURFACES_GUIDE = [
    "Operators can now see the running version in the About dialog, the startup banner, the open `GET /agent/version/` health-check endpoint, and Windows file properties on the built executables.",
    "The runtime resolver lives in `Tlamatini/agent/version.py`, while the build-oriented coordination logic lives in the repo-root `versioning.py` and the longer policy notes live in `VERSIONING.md`.",
    "Build overrides are supported in a predictable order: CLI `--version`, then `TLAMATINI_VERSION`, then git describe, then the sentinel `0.0.0+unknown`.",
]

DE_COMPRESSER_GUIDE = [
    "De-Compresser is the deterministic archive worker for compression and decompression tasks, deciding direction from whichever side exposes a recognized archive extension.",
    "Supported archive families are `.gz`, `.zip`, `.7z`, `.tar.gz`, and `.gz.tar`; file-to-folder extraction and file-or-directory packing are both documented in the README and Book.",
    "Password handling is explicit: `passwordless=true` skips it, while `passwordless=false` requires the `DE_COMPRESSER_PWD` environment variable and fails fast if the secret is missing.",
]

DE_COMPRESSER_INTEGRATION_GUIDE = [
    "The agent is reachable from both operator surfaces: ACP canvas nodes wire through dedicated connection-update views, and checked Multi-Turn can invoke it through `chat_agent_de_compresser`.",
    "Format engines are practical rather than magical: stdlib `gzip` and `zipfile` cover core cases, `7z` is preferred for encrypted `7z` or `zip`, and `py7zr` was added to `requirements.txt` as the Python fallback.",
    "Every run emits an `INI_SECTION_DE_COMPRESSER<<< ... >>>END_SECTION_DE_COMPRESSER` block and still triggers `target_agents`, so downstream Parametrizer or Raiser logic can branch on `success=true|false` instead of guessing from prose.",
]

UNREAL_MCP_GUIDE = [
    "Unreal MCP is a UE5 plugin that runs inside the editor and listens on `127.0.0.1:55557` for one JSON command per TCP connection; Tlamatini is the client side of that link, not the plugin host.",
    "The Unrealer workflow agent exposes the upstream 28-command surface: actor manipulation, Blueprint authoring and node wiring, input mappings, and UMG widget building.",
    "The same integration is available in both operator surfaces: checked Multi-Turn via `chat_agent_unrealer`, and ACP canvas flows via the visual Unrealer node plus Parametrizer chaining.",
]

UNREAL_INSTALL_GUIDE = [
    "Install the upstream plugin into `<YourProject>/Plugins/UnrealMCP/`, enable it from `Edit -> Plugins`, restart UE5, and confirm the Output Log says `UnrealMCP listening on 127.0.0.1:55557`.",
    "Tlamatini does not compile or embed the plugin; the Unreal editor must already be running with the listener bound before any Unrealer call can succeed.",
    "A seeded smoke test ships in the Prompts table: `Unreal MCP End-to-End Editor Drive` walks through sanity-check, actor spawn, Blueprint creation/compile, and UMG widget assembly.",
]

UNREAL_RUNTIME_GUIDE = [
    "Each Unrealer run is one command: load `config.yaml`, open a fresh TCP socket, send `{\"type\": command, \"params\": params}`, read until valid JSON arrives, and log one atomic `INI_SECTION_UNREALER<<< ... >>>END_SECTION_UNREALER` block.",
    "The wrapped-tool path stores chat runs under `agent/agents/pools/_chat_runs_/unrealer_<seq>_<id>/`, while visual flows use normal `unrealer_<n>` pool folders and can chain response fields through Parametrizer mappings.",
    "Exec Report treats Unrealer as its own row family, and troubleshooting stays concrete: connection-refused means the plugin is not listening, while read-timeout usually means UE5's game thread is busy.",
]

ORPHAN_REAPER_GUIDE = [
    "Tlamatini now ships a three-tier orphan reaper in `Tlamatini/agent/orphan_reaper.py` focused on Windows console-host leftovers such as `conhost.exe` and `openconsole.exe`.",
    "Tier 1 runs after spawn-capable Multi-Turn tool calls, Tier 2 runs once after the final answer in a background thread, and Tier 3 runs again during application shutdown through the same cleanup path that already tears down pools.",
    "The candidate set stays narrow on purpose: dead descendants of the current process tree, orphaned console hosts tied to that tree, and pool-linked processes whose `cmdline` still points into `agents/pools/...` even though tracking records are gone.",
]

ORPHAN_PREVENTION_GUIDE = [
    "Prevention landed alongside cleanup: Windows spawn sites now use `CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` with stdio piped to `DEVNULL`, so the console host is usually never allocated in the first place.",
    "The ACPX runtime now kills full process trees instead of only top-level wrappers, and pool-agent scripts gained a conservative `subprocess.Popen` guard so forgotten descendants still inherit `CREATE_NO_WINDOW`.",
    "If something survives both cleanup tiers, Tlamatini sends a second chat bubble listing each surviving `name + PID`; the reaper never raises into the user path because a cleanup crash would be worse than the leftovers it tried to remove.",
]

EMBEDDING_GUARD_GUIDE = [
    "README and BookOfTlamatini now document an embedding-memory pre-flight guard for GPU hosts before a directory-context load starts its FAISS embedding burst.",
    "On supported NVIDIA hosts it estimates embedding-model VRAM pressure, and when the projected load is too high it emits a non-blocking warning chat bubble instead of silently letting RAM<->VRAM thrash surprise the operator.",
    "CPU-only, AMD, and Apple-Silicon hosts stay fail-open: the guard becomes a no-op when the NVIDIA probe does not apply.",
    "The practical operator response is straightforward: switch to a smaller embedding model, reconnect if needed, or proceed knowingly with the heavier model.",
]

RECENT_RUNTIME_SAFEGUARDS = [
    "Config -> Models and Config -> URLs dialogs now track their pre-edit baseline and can show a reconnect-required dialog when the saved values change what the live chat session should trust.",
    "The restored-session autoload path now buffers early WebSocket frames so context-loading spinners and disabled-input state are not lost during automatic reconnect/restore flows.",
    "Startup and restart behavior now also re-apply GPU performance and Ollama keep-alive hooks in the background on supported NVIDIA Windows hosts, improving warm-model readiness without blocking Django boot.",
    "Windows process hygiene is now part of that safety story too: detached no-window spawns and the three-tier orphan reaper reduce the chance that Task Manager shows stale Tlamatini-icon console helpers after long runs.",
]

RELEASE_GUIDE = [
    "Release production is a three-step pipeline: `build.py` -> `build_uninstaller.py` -> `build_installer.py`.",
    "The final distributable is the full `dist/Tlamatini_Release/` folder, not a stray executable copied outside its payload.",
    "Current `build.py` treats `README.md` and `jd-cli/` as required post-build assets and fails hard if those payloads are missing.",
    "Bundled support scripts cover shortcut creation/removal, `.flw` association, the PowerShell launcher, and Windows-specific installer ergonomics.",
]

EXEC_REPORT_GUIDE = [
    "Exec Report is a Multi-Turn-only transparency layer that appends one operation table per state-changing agent family to the final answer.",
    "Rows are recorded from the live tool-call stream rather than guessed from the LLM prose, so the report is the operational ground truth.",
    "Each row receives a SUCCESS/FAILURE verdict from raw tool returns, making long installs, deployments, and remediations inspectable after the fact.",
]

ACPX_GUIDE = [
    "ACPX lets Tlamatini spawn external coding-agent CLIs such as Codex, Claude Code, Cursor, Gemini, Qwen, and others as managed child processes.",
    "It pairs those agents with markdown-driven `SKILL.md` packages, validated I/O contracts, permission gating, and append-only audit logs.",
    "Transport-aware drain rules and bounded event bodies reduce latency while protecting the LLM context budget during external-agent relays.",
    "The operator-facing references are `README.md` and `ACPX.md`, while the implementation lives under `agent/acpx/`, `agent/skills/`, and `agent/skills_pkg/`.",
]

APP_LOG_GUIDE = [
    "The built-in `tlamatini.log` file captures both stdout and stderr through a tee stream initialized in `manage.py` before Django starts.",
    "In source mode the log sits next to `manage.py`; in frozen mode it lives next to the executable.",
    "Immediate flush behavior makes the log the primary forensic artifact for startup problems, warnings, tracebacks, and runtime diagnostics.",
]

OLLAMA_COMMANDS = "\n".join(
    [
        '$env:OLLAMA_INSTALL_DIR = "$env:LOCALAPPDATA\\Programs\\Ollama"',
        "irm https://ollama.com/install.ps1 | iex",
        "ollama --version",
        "ollama serve",
        "Invoke-WebRequest http://127.0.0.1:11434/api/tags -UseBasicParsing",
        "ollama pull qwen3-embedding:8b",
        "ollama pull glm-5:cloud",
        "ollama pull qwen3.5:cloud",
        "ollama pull gpt-oss:120b-cloud",
        "ollama pull qwen3.5:397b-cloud",
        "ollama pull llama3.2-vision:11b",
    ]
)

OLLAMA_GUIDE = [
    "Open a normal PowerShell window, not an elevated one, for the safest no-admin Windows installation path.",
    "Install into `%LOCALAPPDATA%\\Programs\\Ollama` with the official PowerShell installer script and then reopen PowerShell so PATH updates are visible.",
    "Verify the CLI with `ollama --version`, start `ollama serve` if the background service is not already active, and confirm `http://127.0.0.1:11434/api/tags` responds.",
    "Pull the default repository model tags exactly as written if you want the shipped config and agent templates to work unchanged.",
]

ARCHITECTURE_LAYERS = [
    ("Browser interfaces", "Chat page plus Agentic Control Panel templates and JavaScript modules."),
    ("Django/Channels", "Authentication, views, WebSockets, session state, message persistence, and ASGI startup."),
    ("RAG and context", "Metadata extraction, text splitting, FAISS/BM25 retrieval, context budgeting, and fallback behavior."),
    ("Multi-Turn engine", "Capability registry, global execution planner, explicit tool loop, answer parsing, and answer-success classification."),
    ("Tools and agents", "Core tools, MCP context providers, wrapped chat-agent launchers, and the current visual workflow agent templates."),
    ("Packaging", "PyInstaller build scripts, shortcut registration, `.flw` association, installer, uninstaller, and release folder assembly."),
]

AGENT_CATEGORIES = [
    ("Control", "starter, ender, stopper, cleaner, barrier, flowbacker"),
    ("Execution and files", "executer, pythonxer, pser, file_creator, file_extractor, file_interpreter, de_compresser, playwrighter, windower, unrealer, kalier, mover, deleter"),
    ("DevOps and infra", "gitter, dockerer, kuberneter, jenkinser, ssher, scper"),
    ("Data and APIs", "sqler, mongoxer, apirer, crawler, googler"),
    ("Monitoring and routing", "monitor_log, monitor_netstat, flowhypervisor, forker, asker, counter, and, or"),
    ("Communication", "notifier, emailer, recmailer, telegramer, telegramrx, teletlamatini, whatsapper, whatstlamatini"),
    ("Security and media", "kyber_keygen, kyber_cipher, kyber_decipher, image_interpreter, shoter, j_decompiler"),
    ("Workflow intelligence", "flowcreator, gatewayer, gateway_relayer, node_manager, parametrizer, prompter, summarizer, acpxer"),
]


def pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TlamatiniTitle",
            parent=base["Title"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=34,
            textColor=colors.HexColor("#17342d"),
            spaceAfter=14,
        ),
        "subtitle": ParagraphStyle(
            "TlamatiniSubtitle",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#6b4a34"),
            spaceAfter=20,
        ),
        "h1": ParagraphStyle(
            "TlamatiniH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f3b31"),
            spaceBefore=14,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "TlamatiniH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#8f5c35"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "TlamatiniBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12.5,
            textColor=colors.HexColor("#1f2933"),
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "TlamatiniBullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12.2,
            leftIndent=13,
            firstLineIndent=-8,
            textColor=colors.HexColor("#1f2933"),
            spaceAfter=4,
        ),
        "mono": ParagraphStyle(
            "TlamatiniMono",
            parent=base["Code"],
            fontName="Courier",
            fontSize=6.7,
            leading=7.7,
            textColor=colors.HexColor("#17231f"),
        ),
    }


def p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)


def bullet(text: str, style: ParagraphStyle) -> Paragraph:
    return p(f"- {text}", style)


def table(data: list[list], widths: list[float] | None = None, font_size: int = 8) -> Table:
    tbl = Table(data, colWidths=widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17342d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("LEADING", (0, 0), (-1, -1), font_size + 2),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#a8b1aa")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8faf7"), colors.HexColor("#eef4ef")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tbl


def split_lines(text: str, per_page: int) -> list[str]:
    lines = text.splitlines()
    return ["\n".join(lines[index : index + per_page]) for index in range(0, len(lines), per_page)]


def split_items(items: list, size: int) -> list[list]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def pdf_page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#8f5c35"))
    canvas.setLineWidth(0.4)
    canvas.line(doc.leftMargin, 0.48 * inch, A4[0] - doc.rightMargin, 0.48 * inch)
    canvas.setFillColor(colors.HexColor("#17342d"))
    canvas.setFont("Helvetica", 7)
    canvas.drawString(doc.leftMargin, 0.32 * inch, "Tlamatini complete project dossier")
    canvas.drawRightString(A4[0] - doc.rightMargin, 0.32 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(context: dict) -> None:
    styles = pdf_styles()
    doc = SimpleDocTemplate(
        str(PDF_OUTPUT),
        pagesize=A4,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.68 * inch,
        title="Tlamatini App Summary",
        author="Tlamatini",
    )
    story: list = []

    cover_image = context["reference_media"][0] if context["reference_media"] else REPO_ROOT / "Tlamatini.jpg"
    story.append(p("TLAMATINI", styles["title"]))
    story.append(
        p(
            "Complete Project Dossier: what the system does, how it works, how to use it, complete tracked file tree, and effective line inventory",
            styles["subtitle"],
        )
    )
    if cover_image.exists():
        try:
            story.append(Image(str(cover_image), width=6.8 * inch, height=3.8 * inch))
            story.append(Spacer(1, 12))
        except Exception:
            pass
    story.append(
        table(
            [
                ["Measure", "Value"],
                ["Generated", context["generated_at"]],
                ["Current HEAD", f"{context['head_short']} - {context['head_subject']}"],
                ["Resolved version", f"{context['version_info']['version']} ({context['version_info']['source']})"],
                ["Tracked files", str(context["tracked_files"])],
                ["Workflow agents", str(context["workflow_agent_count"])],
                ["Multi-Turn tools", str(context["total_multi_turn_tools"])],
                ["Skills", str(context["skills_count"])],
                ["Total effective lines", f"{context['total_effective_lines']:,}"],
                ["Total physical text lines", f"{context['total_lines']:,}"],
            ],
            widths=[1.9 * inch, 4.8 * inch],
            font_size=8,
        )
    )
    story.append(PageBreak())

    story.append(p("1. What Tlamatini Is", styles["h1"]))
    for item in SYSTEM_OVERVIEW:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("What the system does", styles["h2"]))
    for item in WHAT_IT_DOES:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("How it works", styles["h2"]))
    for item in HOW_IT_WORKS:
        story.append(bullet(item, styles["bullet"]))
    story.append(PageBreak())

    story.append(p("2. Architecture Layers", styles["h1"]))
    arch_rows = [["Layer", "Role"]] + [[layer, desc] for layer, desc in ARCHITECTURE_LAYERS]
    story.append(table(arch_rows, widths=[1.75 * inch, 5.0 * inch], font_size=8))
    story.append(p("Design principles", styles["h2"]))
    for item in DESIGN_PRINCIPLES:
        story.append(bullet(item, styles["bullet"]))
    story.append(PageBreak())

    story.append(p("3. Installation, Configuration, and Everyday Use", styles["h1"]))
    story.append(p("Installation essentials", styles["h2"]))
    for item in INSTALLATION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Configuration essentials", styles["h2"]))
    for item in CONFIGURATION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("DB menu and database swap-in", styles["h2"]))
    for item in DB_MENU_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    for item in DB_SWAP_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Versioning system", styles["h2"]))
    for item in VERSIONING_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Version surfaces", styles["h2"]))
    for item in VERSION_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("De-Compresser agent", styles["h2"]))
    for item in DE_COMPRESSER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("De-Compresser integration and fallback behavior", styles["h2"]))
    for item in DE_COMPRESSER_INTEGRATION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Unreal MCP and the Unrealer agent", styles["h2"]))
    for item in UNREAL_MCP_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Installing the UE5 plugin and smoke-testing it", styles["h2"]))
    for item in UNREAL_INSTALL_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Orphan-process cleanup", styles["h2"]))
    for item in ORPHAN_REAPER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Orphan-process prevention and survivor reporting", styles["h2"]))
    for item in ORPHAN_PREVENTION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("How to use it", styles["h2"]))
    for item in HOW_TO_USE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Agent descriptions and catalog source of truth", styles["h2"]))
    for item in AGENT_DESCRIPTION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Reviewer and Analyzer", styles["h2"]))
    for item in REVIEWER_ANALYZER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    for item in REVIEWER_ANALYZER_SURFACES:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Operator surface counts", styles["h2"]))
    for item in OPERATOR_SURFACE_COUNTS_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Kalier in v1.7.0", styles["h2"]))
    for item in KALIER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    for item in KALIER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Windower on Multi-Turn and canvas", styles["h2"]))
    for item in WINDOWER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    for item in WINDOWER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Playwrighter in v1.5.0", styles["h2"]))
    for item in PLAYWRIGHTER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    for item in PLAYWRIGHTER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Reviewer precision patch in v1.4.1", styles["h2"]))
    for item in REVIEWER_PRECISION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Native dialogs and Tkinter removal in v1.4.2", styles["h2"]))
    for item in NATIVE_DIALOGS_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("ACPX-Skills menu", styles["h2"]))
    for item in ACPX_SKILLS_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Source-mode bootstrap commands", styles["h2"]))
    story.append(
        Preformatted(
            "\n".join(
                [
                    "python -m venv venv",
                    "venv\\Scripts\\activate",
                    "pip install -r requirements.txt",
                    "python Tlamatini/manage.py migrate",
                    "python Tlamatini/manage.py createsuperuser",
                    "python Tlamatini/manage.py collectstatic --noinput",
                    "python Tlamatini/manage.py runserver --noreload",
                ]
            ),
            styles["mono"],
        )
    )
    story.append(PageBreak())

    story.append(p("4. Ollama Setup Without Administrative Rights", styles["h1"]))
    for item in OLLAMA_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("No-admin Ollama commands and default model pulls", styles["h2"]))
    story.append(Preformatted(OLLAMA_COMMANDS, styles["mono"]))
    story.append(PageBreak())

    story.append(p("5. Runtime, Release, and Operator Diagnostics", styles["h1"]))
    story.append(p("Running the application", styles["h2"]))
    for item in RUNNING_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Embedding-memory pre-flight guard", styles["h2"]))
    for item in EMBEDDING_GUARD_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Reconnect and restart safeguards", styles["h2"]))
    for item in RECENT_RUNTIME_SAFEGUARDS:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Prompt catalog and answer readability discipline", styles["h2"]))
    for item in PROMPT_CATALOG_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Unreal MCP runtime behavior", styles["h2"]))
    for item in UNREAL_RUNTIME_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Orphan reaper runtime behavior", styles["h2"]))
    for item in ORPHAN_REAPER_GUIDE + ORPHAN_PREVENTION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Release pipeline", styles["h2"]))
    for item in RELEASE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Exec Report", styles["h2"]))
    for item in EXEC_REPORT_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("ACPX and skills", styles["h2"]))
    for item in ACPX_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Application log", styles["h2"]))
    for item in APP_LOG_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(PageBreak())

    story.append(p("6. Agent Catalog and Runtime Model", styles["h1"]))
    story.append(p(f"Tlamatini currently exposes {context['workflow_agent_count']} workflow-agent templates.", styles["body"]))
    story.append(table([["Category", "Representative agents"]] + AGENT_CATEGORIES, widths=[1.85 * inch, 4.9 * inch], font_size=7.8))
    story.append(p("All workflow agents follow a common deployment pattern: template directory, YAML configuration, session-scoped pool copy, PID/status/log files, target/source wiring, and optional reanimation state.", styles["body"]))
    story.append(p("Agent catalog validation", styles["h2"]))
    for item in AGENT_DESCRIPTION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("How agent runtimes are shaped", styles["h2"]))
    for item in AGENT_RUNTIME_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Reviewer and Analyzer spotlight", styles["h2"]))
    for item in REVIEWER_ANALYZER_GUIDE + REVIEWER_ANALYZER_SURFACES:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Operator surface counts", styles["h2"]))
    for item in OPERATOR_SURFACE_COUNTS_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Kalier spotlight", styles["h2"]))
    for item in KALIER_GUIDE + KALIER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Windower spotlight", styles["h2"]))
    for item in WINDOWER_GUIDE + WINDOWER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Playwrighter spotlight", styles["h2"]))
    for item in PLAYWRIGHTER_GUIDE + PLAYWRIGHTER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Reviewer precision spotlight", styles["h2"]))
    for item in REVIEWER_PRECISION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Native-dialog spotlight", styles["h2"]))
    for item in NATIVE_DIALOGS_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Unrealer spotlight", styles["h2"]))
    for item in UNREAL_MCP_GUIDE + UNREAL_RUNTIME_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("De-Compresser spotlight", styles["h2"]))
    for item in DE_COMPRESSER_GUIDE + DE_COMPRESSER_INTEGRATION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Orphan-reaper spotlight", styles["h2"]))
    for item in ORPHAN_REAPER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(PageBreak())

    story.append(p("7. Repository Facts and Git Changes", styles["h1"]))
    repo_rows = [
        ["Metric", "Value"],
        ["Tracked files in git", f"{context['tracked_files']}"],
        ["Workflow agents", f"{context['workflow_agent_count']}"],
        ["Multi-Turn tools", f"{context['total_multi_turn_tools']}"],
        ["Wrapped chat-agent tools", f"{context['wrapped_chat_agent_count']}"],
        ["Skills", f"{context['skills_count']}"],
        ["agents_descriptions.md rows", f"{context['agent_description_rows']}"],
        ["Django migrations", f"{context['migrations']}"],
        ["Frontend JavaScript modules", f"{context['js_modules']}"],
        ["Frontend CSS files", f"{context['css_files']}"],
        ["HTML templates", f"{context['html_templates']}"],
        ["Python requirements", f"{context['requirements_count']}"],
        ["Binary/asset tracked files skipped from line count", f"{context['binary_count']}"],
        ["Resolved version", f"{context['version_info']['version']}"],
        ["Version source", f"{context['version_info']['source']}"],
    ]
    story.append(table(repo_rows, widths=[3.0 * inch, 3.7 * inch], font_size=8))
    story.append(p("Latest commits", styles["h2"]))
    commit_rows = [["Date", "Commit", "Subject"]]
    for commit in context["recent_commits"]:
        commit_rows.append([iso_date(commit.committed_at), commit.short_hash, commit.subject])
    story.append(table(commit_rows, widths=[1.0 * inch, 0.8 * inch, 4.9 * inch], font_size=7))
    git_window_heading = "Git changes from today" if RECENT_GIT_WINDOW_LABEL == "today" else f"Git changes from the {RECENT_GIT_WINDOW_LABEL}"
    story.append(p(git_window_heading, styles["h2"]))
    for item in context["weekly_highlights"]:
        story.append(bullet(item, styles["bullet"]))
    weekly_chunks = split_items(context["weekly_commits"], 12)
    for index, chunk in enumerate(weekly_chunks, 1):
        appendix_heading = (
            f"Today's commit appendix {index} of {len(weekly_chunks)}"
            if RECENT_GIT_WINDOW_LABEL == "today"
            else f"{RECENT_GIT_WINDOW_DAYS}-day commit appendix {index} of {len(weekly_chunks)}"
        )
        story.append(p(appendix_heading, styles["h2"]))
        weekly_rows = [["Date", "Commit", "Subject"]]
        for commit in chunk:
            weekly_rows.append([iso_date(commit.committed_at), commit.short_hash, commit.subject])
        story.append(table(weekly_rows, widths=[1.0 * inch, 0.8 * inch, 4.9 * inch], font_size=7))
        if index != len(weekly_chunks):
            story.append(PageBreak())
    story.append(PageBreak())

    story.append(p("8. Effective Line Inventory by Language", styles["h1"]))
    story.append(
        p(
            "Methodology: tracked text files only. Blank lines and comment-only lines are excluded. Python counts also remove module, class, and function docstrings detected through AST parsing.",
            styles["body"],
        )
    )
    line_rows = [["Language", "Files", "Effective lines", "Total lines", "Share"]]
    for row in context["language_rows"]:
        share = row.effective_lines / max(context["total_effective_lines"], 1)
        line_rows.append(
            [
                row.language,
                f"{row.files}",
                f"{row.effective_lines:,}",
                f"{row.total_lines:,}",
                f"{share:.1%}",
            ]
        )
    story.append(table(line_rows, widths=[1.65 * inch, 0.75 * inch, 1.35 * inch, 1.25 * inch, 0.85 * inch], font_size=7.5))
    story.append(p(f"Total effective lines: {context['total_effective_lines']:,}", styles["h2"]))
    story.append(PageBreak())

    story.append(p("9. Largest Effective Source Files", styles["h1"]))
    largest_rows = [["Path", "Language", "Effective", "Total"]]
    for file_stat in context["file_rows"][:25]:
        largest_rows.append([file_stat.path, file_stat.language, f"{file_stat.effective_lines:,}", f"{file_stat.total_lines:,}"])
    story.append(table(largest_rows, widths=[4.0 * inch, 1.2 * inch, 0.75 * inch, 0.75 * inch], font_size=6.7))
    story.append(PageBreak())

    story.append(p("10. Complete Tracked File Tree (Repository Appendix)", styles["h1"]))
    TREE_OUTPUT.write_text(context["tree_text"], encoding="utf-8")
    tree_chunks = split_lines(context["tree_text"], 76)
    for index, chunk in enumerate(tree_chunks, 1):
        story.append(p(f"Tree appendix {index} of {len(tree_chunks)}", styles["h2"]))
        story.append(Preformatted(chunk, styles["mono"]))
        if index != len(tree_chunks):
            story.append(PageBreak())

    doc.build(story, onFirstPage=pdf_page_footer, onLaterPages=pdf_page_footer)


def rgb_hex(color: RGBColor) -> str:
    return f"{color[0]:02X}{color[1]:02X}{color[2]:02X}"


def fill(shape, color: RGBColor, transparency: int = 0) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.fill.transparency = transparency
    shape.line.color.rgb = color


def add_dark_background(slide, accent: RGBColor, image_path: Path | None = None) -> None:
    if image_path and image_path.exists():
        slide.shapes.add_picture(str(image_path), 0, 0, width=Inches(SLIDE_W), height=Inches(SLIDE_H))
        veil = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, 0, Inches(SLIDE_W), Inches(SLIDE_H))
        fill(veil, THEME["obsidian"], 22)
        veil.line.fill.background()
    else:
        bg = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, 0, Inches(SLIDE_W), Inches(SLIDE_H))
        fill(bg, THEME["obsidian"])
        bg.line.fill.background()

    for x in [0.35, SLIDE_W - 0.52]:
        line = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, Inches(x), Inches(0.42), Inches(0.04), Inches(6.65))
        fill(line, accent, 25)
        line.line.fill.background()
    top = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, Inches(0.55), Inches(0.42), Inches(12.2), Inches(0.03))
    fill(top, accent, 15)
    top.line.fill.background()
    bottom = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, Inches(0.55), Inches(7.04), Inches(12.2), Inches(0.03))
    fill(bottom, accent, 40)
    bottom.line.fill.background()


def add_run(paragraph, text: str, size: int, color: RGBColor, bold: bool = False, font: str = "Aptos") -> None:
    run = paragraph.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def add_text(
    slide,
    audit: list[tuple[float, float, float, float, str]],
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    size: int = 18,
    color: RGBColor | None = None,
    bold: bool = False,
    align: PP_ALIGN = PP_ALIGN.LEFT,
    name: str = "text",
    font: str = "Aptos",
) -> None:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.TOP
    p0 = frame.paragraphs[0]
    p0.alignment = align
    add_run(p0, text, size, color or THEME["white"], bold, font)
    audit.append((x, y, w, h, name))


def add_bullets(
    slide,
    audit: list[tuple[float, float, float, float, str]],
    x: float,
    y: float,
    w: float,
    h: float,
    bullets: list[str],
    size: int = 16,
    color: RGBColor | None = None,
    name: str = "bullets",
) -> None:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.TOP
    frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    frame.margin_left = Pt(3)
    frame.margin_right = Pt(3)
    frame.margin_top = Pt(2)
    frame.margin_bottom = Pt(2)
    for idx, item in enumerate(bullets):
        para = frame.paragraphs[0] if idx == 0 else frame.add_paragraph()
        para.text = item
        para.level = 0
        para.font.name = "Aptos"
        para.font.size = Pt(size)
        para.font.color.rgb = color or THEME["muted"]
        para.space_after = Pt(6)
        para.bullet = True
    try:
        frame.fit_text(max_size=size)
    except Exception:
        frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    audit.append((x, y, w, h, name))


def add_title(slide, audit: list[tuple[float, float, float, float, str]], title: str, kicker: str, accent: RGBColor) -> None:
    add_text(slide, audit, 0.78, 0.6, 11.7, 0.33, kicker.upper(), 10, accent, True, name="kicker", font="Aptos")
    add_text(slide, audit, 0.76, 0.93, 11.9, 0.62, title, 27, THEME["white"], False, name="title", font="Aptos Display")


def add_panel(
    slide,
    audit: list[tuple[float, float, float, float, str]],
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    bullets: list[str],
    accent: RGBColor,
    name: str,
    size: int = 15,
) -> None:
    shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    fill(shape, THEME["panel"], 8)
    shape.line.color.rgb = THEME["line"]
    bar = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.12))
    fill(bar, accent, 0)
    bar.line.fill.background()
    add_text(slide, audit, x + 0.22, y + 0.22, w - 0.44, 0.34, title, 14, accent, True, name=f"{name}-title")
    add_bullets(slide, audit, x + 0.22, y + 0.72, w - 0.44, h - 0.88, bullets, size=size, name=f"{name}-body")
    audit.append((x, y, w, h, name))


def add_metric_card(
    slide,
    audit: list[tuple[float, float, float, float, str]],
    x: float,
    y: float,
    w: float,
    label: str,
    value: str,
    accent: RGBColor,
    name: str,
) -> None:
    shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(1.02))
    fill(shape, THEME["panel2"], 4)
    shape.line.color.rgb = accent
    add_text(slide, audit, x + 0.16, y + 0.15, w - 0.32, 0.24, label.upper(), 8, accent, True, name=f"{name}-label")
    add_text(slide, audit, x + 0.16, y + 0.42, w - 0.32, 0.38, value, 20, THEME["white"], True, name=f"{name}-value")
    audit.append((x, y, w, 1.02, name))


def add_flow_boxes(
    slide,
    audit: list[tuple[float, float, float, float, str]],
    x: float,
    y: float,
    labels: list[str],
    accent: RGBColor,
) -> None:
    box_w = 1.74
    gap = 0.27
    for idx, label in enumerate(labels):
        bx = x + idx * (box_w + gap)
        shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Inches(bx), Inches(y), Inches(box_w), Inches(0.75))
        fill(shape, THEME["stone"], 3)
        shape.line.color.rgb = accent
        add_text(slide, audit, bx + 0.08, y + 0.18, box_w - 0.16, 0.28, label, 10, THEME["white"], True, PP_ALIGN.CENTER, name=f"flow-{idx}")
        audit.append((bx, y, box_w, 0.75, f"flowbox-{idx}"))
        if idx < len(labels) - 1:
            add_text(slide, audit, bx + box_w, y + 0.19, gap, 0.2, ">", 12, accent, True, PP_ALIGN.CENTER, name=f"arrow-{idx}")


def audit_layout(audit: list[tuple[float, float, float, float, str]], slide_no: int) -> None:
    for x, y, w, h, name in audit:
        if x < -0.01 or y < -0.01 or x + w > SLIDE_W + 0.01 or y + h > SLIDE_H + 0.01:
            raise RuntimeError(f"Slide {slide_no}: {name} is outside slide bounds")
    major = [
        item
        for item in audit
        if not item[4].endswith("-label")
        and not item[4].endswith("-value")
        and not item[4].startswith("flow-")
        and not item[4].startswith("arrow-")
    ]
    for i, a in enumerate(major):
        for b in major[i + 1 :]:
            if a[4].split("-")[0] == b[4].split("-")[0]:
                continue
            if rects_overlap(a, b):
                raise RuntimeError(f"Slide {slide_no}: {a[4]} overlaps {b[4]}")


def rects_overlap(a: tuple[float, float, float, float, str], b: tuple[float, float, float, float, str]) -> bool:
    ax, ay, aw, ah, _ = a
    bx, by, bw, bh, _ = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def add_slide(prs: Presentation, title: str, kicker: str, accent: RGBColor, image: Path | None = None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    audit: list[tuple[float, float, float, float, str]] = []
    add_dark_background(slide, accent, image)
    add_title(slide, audit, title, kicker, accent)
    return slide, audit


def language_table_text(rows: list[LineStats], total_effective: int) -> str:
    lines = ["LANGUAGE                 FILES   EFFECTIVE      TOTAL   SHARE"]
    for row in rows:
        share = row.effective_lines / max(total_effective, 1)
        lines.append(
            f"{row.language[:22]:22} {row.files:5d} {row.effective_lines:11,d} {row.total_lines:10,d} {share:6.1%}"
        )
    return "\n".join(lines)


def file_table_text(rows: list[FileStats], limit: int = 14) -> str:
    lines = ["PATH                                                     LANGUAGE     EFFECTIVE   TOTAL"]
    for row in rows[:limit]:
        path = row.path
        if len(path) > 55:
            path = "..." + path[-52:]
        lines.append(f"{path:55} {row.language[:10]:10} {row.effective_lines:9,d} {row.total_lines:7,d}")
    return "\n".join(lines)


def build_ppt(context: dict) -> None:
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    cover = context["reference_media"][0] if context["reference_media"] else None

    slide, audit = add_slide(
        prs,
        "TLAMATINI",
        "Complete project dossier: what it does, how it works, how to use it",
        THEME["copper"],
        cover,
    )
    add_text(slide, audit, 0.9, 2.0, 5.5, 0.6, "El Saber Cosmico del Desarrollo", 24, THEME["white"], False, name="cover-tag", font="Aptos Display")
    add_text(
        slide,
        audit,
        0.9,
        2.76,
        6.3,
        1.0,
        f"Local AI developer assistant with RAG, Multi-Turn orchestration, {context['workflow_agent_count']} agents, ACPX delegation, visual workflows, and Windows packaging.",
        17,
        THEME["muted"],
        False,
        name="cover-body",
    )
    add_metric_card(slide, audit, 0.9, 4.25, 1.75, "Files", str(context["tracked_files"]), THEME["jade"], "cover-m1")
    add_metric_card(slide, audit, 2.85, 4.25, 1.75, "Agents", str(context["workflow_agent_count"]), THEME["copper"], "cover-m2")
    add_metric_card(slide, audit, 4.8, 4.25, 1.95, "Effective", f"{context['total_effective_lines']:,}", THEME["amber"], "cover-m3")
    add_text(slide, audit, 0.9, 6.35, 6.2, 0.32, f"Generated {context['generated_at']} at HEAD {context['head_short']}", 9, THEME["muted"], name="cover-foot")
    audit_layout(audit, 1)

    slide, audit = add_slide(prs, "What Tlamatini Is", "system identity", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.65, 5.85, 4.95, "Definition", SYSTEM_OVERVIEW, THEME["jade"], "identity-a", 16)
    add_panel(slide, audit, 6.92, 1.65, 5.55, 4.95, "Core interfaces", [
        "Chat page at `/agent/` for context-grounded Q&A, code generation, tool calls, and Multi-Turn execution.",
        "Agentic Control Panel at `/agentic_control_panel/` for visual workflow design.",
        "Django admin and config dialogs for MCPs, tools, agents, users, and persistent settings.",
    ], THEME["copper"], "identity-b", 16)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "What The System Does", "capability map", THEME["copper"])
    add_panel(slide, audit, 0.72, 1.56, 3.85, 4.95, "Knowledge", WHAT_IT_DOES[:3], THEME["jade"], "does-a", 15)
    add_panel(slide, audit, 4.86, 1.56, 3.85, 4.95, "Action", WHAT_IT_DOES[3:5], THEME["copper"], "does-b", 15)
    add_panel(slide, audit, 9.0, 1.56, 3.35, 4.95, "Delivery", WHAT_IT_DOES[5:], THEME["amber"], "does-c", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "How It Works", "execution pipeline", THEME["jade"])
    add_flow_boxes(slide, audit, 0.82, 2.0, ["Browser", "Channels", "RAG", "Planner", "Tools", "Answer"], THEME["jade"])
    add_panel(slide, audit, 0.78, 3.25, 5.85, 3.05, "Request path", HOW_IT_WORKS[:3], THEME["jade"], "works-a", 15)
    add_panel(slide, audit, 6.92, 3.25, 5.55, 3.05, "Runtime path", HOW_IT_WORKS[3:], THEME["copper"], "works-b", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Design Principles", "how the software is shaped", THEME["amber"])
    add_panel(slide, audit, 0.82, 1.72, 11.55, 4.75, "Core design choices", DESIGN_PRINCIPLES, THEME["amber"], "design", 16)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "RAG And Context Engine", "retrieval core", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.8, 4.95, "RAG responsibilities", [
        "Load selected file or directory context from the chat interface.",
        "Extract metadata, split text, rank chunks with hybrid retrieval, and respect context budgets.",
        "Fallback to explicit loaded files when retrieval cannot provide enough memory.",
        "Preserve the difference between direct one-shot chat and checked Multi-Turn orchestration.",
    ], THEME["amber"], "rag-a", 15)
    add_panel(slide, audit, 6.9, 1.6, 5.6, 4.95, "Why it matters", [
        "The assistant answers from project evidence instead of generic memory.",
        "Large codebases remain navigable without injecting the whole repository into every prompt.",
        "Multi-Turn can prefetch only the contexts required by the current execution plan.",
    ], THEME["jade"], "rag-b", 16)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Multi-Turn Oracle", "agentic execution", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Checked mode", [
        "Capability registry scores context providers, tools, and wrapped agents for the current request.",
        "Global planner builds prefetch, execute, monitor, and answer stages.",
        "Explicit tool loop runs tool calls, appends observations, and asks again until final answer or limit.",
        "Answer Analizer classifies success so the UI can expose Create Flow only when useful.",
    ], THEME["copper"], "mt-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Unchecked mode", [
        "Keeps the original prompt validation and legacy prefetch behavior.",
        "Maintains compatibility for fast Q&A and simple context-grounded answers.",
        "Avoids forcing every chat request into agentic execution.",
    ], THEME["jade"], "mt-b", 16)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Agentic Control Panel", "visual workflow temple", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "ACP workflow", [
        "Drag prebuilt agents onto the canvas and connect them visually.",
        "Configure deployed pool instances, not only static template folders.",
        "Validate structural rules before execution.",
        "Start through Starter, pause/resume through reanimation state, and stop through Ender semantics.",
    ], THEME["jade"], "acp-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Flow files", [
        "Workflows save and load as `.flw` files.",
        "Generated flows from chat are starter drafts, not a replacement for ACP validation.",
        "LED indicators and logs show runtime health across the session pool.",
    ], THEME["copper"], "acp-b", 16)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, f"The {context['workflow_agent_count']} Guardians", "workflow agent catalog", THEME["copper"])
    left = [f"{name}: {desc}" for name, desc in AGENT_CATEGORIES[:4]]
    right = [f"{name}: {desc}" for name, desc in AGENT_CATEGORIES[4:]]
    add_panel(slide, audit, 0.72, 1.56, 5.95, 5.1, "Agent families", left, THEME["copper"], "agents-a", 13)
    add_panel(slide, audit, 6.92, 1.56, 5.65, 5.1, "More guardians", right, THEME["jade"], "agents-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Agent Catalog Integrity", "count and description source of truth", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Count alignment", [
        f"Templates on disk with config.yaml: {context['workflow_agent_count']}",
        f"Description rows in `agents_descriptions.md`: {context['agent_description_rows']}",
        f"README and Book bestiary sections align with the same {context['workflow_agent_count']}-agent inventory.",
    ], THEME["jade"], "agent-proof-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Description source", AGENT_DESCRIPTION_GUIDE, THEME["copper"], "agent-proof-b", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Reviewer And Analyzer", "new review and security surfaces", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What they do", REVIEWER_ANALYZER_GUIDE, THEME["amber"], "reviewer-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators reach them", REVIEWER_ANALYZER_SURFACES, THEME["jade"], "reviewer-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Operator Surface Counts", "README header and planner-facing inventory", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Current counts", OPERATOR_SURFACE_COUNTS_GUIDE, THEME["copper"], "surface-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Why the counts matter", [
        "The README now surfaces the same operator picture the app exposes in practice: broad capability, selective planner binding, and a capped tool budget per request.",
        f"Those counts complement the {context['workflow_agent_count']}-agent bestiary instead of replacing it: skills, wrapped tools, and ACPX tools are different layers of the same operating surface.",
        "For dossier readers, this closes a gap between the capability narrative and the quick-glance repo badges at the top of the handbook.",
    ], THEME["jade"], "surface-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Kalier In v1.7.0", "Kali Linux control for chat and canvas", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What it adds", KALIER_GUIDE, THEME["jade"], "kalier-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators reach it", KALIER_SURFACES_GUIDE, THEME["amber"], "kalier-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Windower In Multi-Turn", "desktop window management for chat and canvas", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What it adds", WINDOWER_GUIDE, THEME["amber"], "window-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators reach it", WINDOWER_SURFACES_GUIDE, THEME["jade"], "window-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Playwrighter In v1.5.0", "real-browser automation for chat and canvas", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What it adds", PLAYWRIGHTER_GUIDE, THEME["jade"], "play-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators reach it", PLAYWRIGHTER_SURFACES_GUIDE, THEME["amber"], "play-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Reviewer Precision In v1.4.1", "commit-state and secret-handling refinement", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Behavioral accuracy patch", REVIEWER_PRECISION_GUIDE, THEME["jade"], "reviewer-c", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Why it matters", [
        "Local working-copy credentials in managed config files are no longer described as already committed when the diff is still uncommitted or only staged.",
        "Review findings stay stricter on true secrets in source code or outside the managed scrub-path set, so the patch reduces noise without weakening real security findings.",
        "The same rules apply in both the canvas Reviewer agent and the `code-review` skill, keeping the two review surfaces behaviorally aligned.",
    ], THEME["amber"], "reviewer-d", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Native Dialogs In v1.4.2", "Tkinter removed from the unstable runtime path", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What changed", NATIVE_DIALOGS_GUIDE, THEME["amber"], "native-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Release meaning", [
        "This stability-focused patch sits immediately before the current `v1.5.0` Playwrighter release and remains part of the current operator/runtime story.",
        "It preserves the operator experience of Browse-driven file and folder picking while removing a UI technology that was destabilizing the application.",
        "Because the fix landed with tests and runtime cleanup updates, it belongs in the technical dossier even though the markdown handbook has not yet been fully rewritten around it.",
    ], THEME["jade"], "native-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Gatewayer And External Signals", "inbound automation boundary", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Ingress role", [
        "Receives HTTP webhook events or optional folder-drop files.",
        "Normalizes, persists, queues, and dispatches events into downstream workflow agents.",
        "Supports bearer/HMAC-style auth patterns, IP allowlists, dedup files, and crash recovery state.",
    ], THEME["amber"], "gate-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Operating note", [
        "Gatewayer is a workflow trigger, not a chat-router clone.",
        "Declared config fields are now documented with clear caveats where enforcement is not complete.",
        "Stable log markers let Monitor Log and Summarizer watch gateway health.",
    ], THEME["jade"], "gate-b", 16)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "How To Use It", "operator path", THEME["jade"])
    add_panel(slide, audit, 0.72, 1.56, 5.9, 5.0, "Daily use", HOW_TO_USE[:3], THEME["jade"], "use-a", 15)
    add_panel(slide, audit, 6.92, 1.56, 5.65, 5.0, "Workflows and releases", HOW_TO_USE[3:], THEME["copper"], "use-b", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Source Mode Bootstrap", "commands that matter", THEME["copper"])
    commands = "\n".join([
        "python -m venv venv",
        "venv\\Scripts\\activate",
        "pip install -r requirements.txt",
        "python Tlamatini/manage.py migrate",
        "python Tlamatini/manage.py createsuperuser",
        "python Tlamatini/manage.py collectstatic --noinput",
        "python Tlamatini/manage.py runserver --noreload",
    ])
    add_text(slide, audit, 0.92, 1.75, 11.35, 3.0, commands, 18, THEME["white"], False, name="commands", font="Cascadia Mono")
    add_panel(slide, audit, 0.92, 5.1, 11.35, 1.18, "First run checklist", [
        "Open the browser, log in with your source-mode superuser, load a context path, and decide whether the task needs Multi-Turn.",
    ], THEME["jade"], "checklist", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Installation And Configuration", "README-backed operator path", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.85, 4.95, "Install essentials", INSTALLATION_GUIDE, THEME["jade"], "install-a", 15)
    add_panel(slide, audit, 6.92, 1.6, 5.55, 4.95, "Config essentials", CONFIGURATION_GUIDE, THEME["copper"], "install-b", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "ACPX-Skills And Prompts", "recent operator-surface documentation updates", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "ACPX-Skills menu", ACPX_SKILLS_GUIDE, THEME["amber"], "skills-a", 14)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Prompt catalog and readability", PROMPT_CATALOG_GUIDE, THEME["jade"], "skills-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "DB Menu And Startup Swap", "today's new operator surface", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Backup and Set DB", DB_MENU_GUIDE, THEME["copper"], "db-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "What happens on next start-up", DB_SWAP_GUIDE, THEME["jade"], "db-b", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Versioning System", "today's release-identity work", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.58, "SemVer and resolver", VERSIONING_GUIDE, THEME["amber"], "ver-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.58, "Where version appears", VERSION_SURFACES_GUIDE, THEME["jade"], "ver-b", 14)
    add_text(
        slide,
        audit,
        0.92,
        6.34,
        11.1,
        0.22,
        f"Resolved current version: {context['version_info']['version']} | build: {context['version_info']['build']}",
        9,
        THEME["muted"],
        False,
        name="version-foot",
        font="Cascadia Mono",
    )
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "De-Compresser Agent", "today's new archive worker", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Operator contract", DE_COMPRESSER_GUIDE, THEME["copper"], "decomp-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Integration and fallbacks", DE_COMPRESSER_INTEGRATION_GUIDE, THEME["jade"], "decomp-b", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Unreal MCP And Unrealer", "today's UE5 bridge", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What it adds", UNREAL_MCP_GUIDE, THEME["jade"], "unreal-a", 14)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Install and runtime path", UNREAL_INSTALL_GUIDE + UNREAL_RUNTIME_GUIDE[:1], THEME["copper"], "unreal-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Orphan-Process Cleanup", "today's Windows process-hygiene work", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Three-tier reaper", ORPHAN_REAPER_GUIDE, THEME["amber"], "reaper-a", 14)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Prevention and survivor reporting", ORPHAN_PREVENTION_GUIDE, THEME["jade"], "reaper-b", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Ollama Without Admin Rights", "local model setup on Windows", THEME["amber"])
    add_text(slide, audit, 0.85, 1.72, 11.55, 3.45, OLLAMA_COMMANDS, 9, THEME["white"], False, name="ollama-commands", font="Cascadia Mono")
    add_panel(slide, audit, 0.85, 5.32, 11.55, 1.0, "Checklist", OLLAMA_GUIDE[:2], THEME["amber"], "ollama-check", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Ollama Readiness", "service, API, and model pulls", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Service and API", OLLAMA_GUIDE[2:], THEME["jade"], "ollama-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Default pull set", [
        "qwen3-embedding:8b",
        "glm-5:cloud",
        "qwen3.5:cloud",
        "gpt-oss:120b-cloud",
        "qwen3.5:397b-cloud",
        "llama3.2-vision:11b",
    ], THEME["copper"], "ollama-b", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "GPU Guard And Reconnect UX", "README and Book driven operator safeguards", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Embedding-memory pre-flight guard", EMBEDDING_GUARD_GUIDE, THEME["amber"], "guard-a", 14)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Reconnect and restart safeguards", RECENT_RUNTIME_SAFEGUARDS, THEME["jade"], "guard-b", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Running Modes", "development, MCP bootstrap, and ASGI", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "How to run", RUNNING_GUIDE, THEME["copper"], "run-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "What startup does", [
        "Initializes Django and runtime guards in manage.py.",
        "Cleans pool state and repopulates the Agent table from current disk templates.",
        "Launches MCP metrics and gRPC file-search servers before steady-state traffic.",
        "Handles shutdown by killing tracked/untracked agent processes and clearing pool artifacts.",
    ], THEME["jade"], "run-b", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Packaging Path", "source usage is separate from release building", THEME["amber"])
    add_flow_boxes(slide, audit, 1.15, 2.0, ["build.py", "pkg.zip", "build_uninstaller", "Uninstaller", "build_installer", "Release"], THEME["amber"])
    add_panel(slide, audit, 0.92, 3.35, 11.35, 2.55, "Release rule", [
        "Run packaging only when preparing a Windows distribution.",
        "The final distributable is the full `dist/Tlamatini_Release/` folder, not one executable copied out of context.",
        "Installer scripts register shortcuts and `.flw` file associations and place the uninstaller next to the app.",
    ], THEME["amber"], "packaging", 16)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Exec Report", "show-your-work visibility for Multi-Turn", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Why it exists", EXEC_REPORT_GUIDE, THEME["jade"], "exec-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Operator effect", [
        "Tables appear only for state-changing agent families that actually fired.",
        "Verdicts are derived from real tool returns, not inferred from prose summaries.",
        "This is the audit surface that makes long jobs debuggable from the chat output itself.",
    ], THEME["amber"], "exec-b", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "ACPX And Skills", "external coding-agent runtime", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What ACPX adds", ACPX_GUIDE, THEME["copper"], "acpx-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Files and operator model", [
        "`agent/acpx/` hosts the runtime, permission gate, registry, and tools.",
        "`agent/skills/` and `agent/skills_pkg/` host the in-process skill harness and markdown catalog.",
        "Transcripts and audit logs are persisted so external delegation stays replayable.",
    ], THEME["jade"], "acpx-b", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Application Log", "tlamatini.log as forensic truth", THEME["amber"])
    add_panel(slide, audit, 0.85, 1.75, 11.45, 4.6, "How the log works", APP_LOG_GUIDE, THEME["amber"], "log", 17)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Repository Facts", "current head inventory", THEME["jade"])
    metrics = [
        ("Tracked", context["tracked_files"]),
        ("Agents", context["workflow_agent_count"]),
        ("Migrations", context["migrations"]),
        ("JS", context["js_modules"]),
        ("CSS", context["css_files"]),
        ("HTML", context["html_templates"]),
    ]
    for idx, (label, value) in enumerate(metrics):
        add_metric_card(slide, audit, 0.82 + idx * 2.05, 1.75, 1.75, label, str(value), THEME["jade"] if idx % 2 == 0 else THEME["copper"], f"repo-{idx}")
    add_panel(slide, audit, 1.05, 3.55, 10.85, 2.05, "Current HEAD", [
        f"{context['head_short']} - {context['head_subject']}",
        f"Resolved version: {context['version_info']['version']} ({context['version_info']['source']})",
        f"Generated on {context['generated_at']}",
        f"Multi-Turn tools: {context['total_multi_turn_tools']}; wrapped chat-agent tools: {context['wrapped_chat_agent_count']}; skills: {context['skills_count']}",
        f"Python requirements: {context['requirements_count']}; authoritative agent-description rows: {context['agent_description_rows']}",
        f"Binary or asset tracked files skipped from line count: {context['binary_count']}",
    ], THEME["amber"], "repo-head", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Effective Lines By Language", "no comments, no blanks", THEME["copper"])
    add_metric_card(slide, audit, 0.9, 1.64, 2.35, "Total effective", f"{context['total_effective_lines']:,}", THEME["copper"], "lines-m1")
    add_metric_card(slide, audit, 3.55, 1.64, 2.35, "Total physical", f"{context['total_lines']:,}", THEME["jade"], "lines-m2")
    add_metric_card(slide, audit, 6.2, 1.64, 2.35, "Text languages", str(len(context["language_rows"])), THEME["amber"], "lines-m3")
    add_text(slide, audit, 0.92, 3.05, 11.35, 3.2, language_table_text(context["language_rows"], context["total_effective_lines"]), 8, THEME["white"], False, name="language-table", font="Cascadia Mono")
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Largest Files By Effective Lines", "where most authored text lives", THEME["jade"])
    add_text(slide, audit, 0.85, 1.72, 11.7, 4.85, file_table_text(context["file_rows"]), 8, THEME["white"], False, name="largest-table", font="Cascadia Mono")
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, RECENT_GIT_WINDOW_TITLE, "recent changes according to git history", THEME["amber"])
    add_panel(slide, audit, 0.82, 1.65, 11.55, 4.9, RECENT_GIT_HIGHLIGHT_TITLE, context["weekly_highlights"], THEME["amber"], "latest", 15)
    audit_layout(audit, len(prs.slides))

    weekly_chunks = split_items(context["weekly_commits"], 6)
    for idx, chunk in enumerate(weekly_chunks, 1):
        slide, audit = add_slide(
            prs,
            (
                f"Today's Commit Appendix {idx}/{len(weekly_chunks)}"
                if RECENT_GIT_WINDOW_LABEL == "today"
                else f"{RECENT_GIT_WINDOW_DAYS}-Day Commit Appendix {idx}/{len(weekly_chunks)}"
            ),
            RECENT_GIT_APPENDIX_SUBTITLE,
            THEME["copper"] if idx % 2 else THEME["jade"],
        )
        weekly_lines = [f"{iso_date(c.committed_at)} | {c.short_hash} | {c.subject}" for c in chunk]
        add_panel(slide, audit, 0.82, 1.68, 11.55, 4.86, "Commit timeline", weekly_lines, THEME["copper"] if idx % 2 else THEME["jade"], f"week-{idx}", 12)
        audit_layout(audit, len(prs.slides))

    tree_chunks = split_lines(context["tree_text"], 31)
    for idx, chunk in enumerate(tree_chunks, 1):
        slide, audit = add_slide(
            prs,
            f"Tracked File Tree Appendix {idx}/{len(tree_chunks)}",
            "complete tracked file tree, no tracked file omitted",
            THEME["jade"] if idx % 2 else THEME["copper"],
        )
        add_text(slide, audit, 0.72, 1.56, 11.95, 5.42, chunk, 7, THEME["white"], False, name=f"tree-{idx}", font="Cascadia Mono")
        audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "How To Keep Docs Excellent", "future refresh discipline", THEME["copper"])
    add_panel(slide, audit, 0.85, 1.75, 11.55, 4.6, "Recommended practice", [
        "Regenerate the PDF and deck whenever README, architecture, agent catalog, line inventory, or packaging behavior changes.",
        "Keep the PDF exhaustive and evidence-heavy; keep the PPT visual, split dense appendices, and audit geometry before delivery.",
        "Use the new Skills in `.codex/skills/` so future refreshes follow the same no-overlap and full-dossier rules.",
    ], THEME["copper"], "final", 17)
    audit_layout(audit, len(prs.slides))

    prs.save(PPT_OUTPUT)


def serialize_context(context: dict) -> dict:
    return {
        "generated_at": context["generated_at"],
        "head_short": context["head_short"],
        "head_full": context["head_full"],
        "head_subject": context["head_subject"],
        "head_date": context["head_date"],
        "tracked_files": context["tracked_files"],
        "total_effective_lines": context["total_effective_lines"],
        "total_lines": context["total_lines"],
        "workflow_agent_count": context["workflow_agent_count"],
        "agent_description_rows": context["agent_description_rows"],
        "wrapped_chat_agent_count": context["wrapped_chat_agent_count"],
        "core_python_tool_count": context["core_python_tool_count"],
        "acpx_tool_count": context["acpx_tool_count"],
        "total_multi_turn_tools": context["total_multi_turn_tools"],
        "skills_count": context["skills_count"],
        "requirements_count": context["requirements_count"],
        "js_modules": context["js_modules"],
        "css_files": context["css_files"],
        "html_templates": context["html_templates"],
        "migrations": context["migrations"],
        "binary_count": context["binary_count"],
        "skipped_count": context["skipped_count"],
        "version": context["version_info"]["version"],
        "version_source": context["version_info"]["source"],
        "version_info": context["version_info"],
        "language_rows": [row.__dict__ for row in context["language_rows"]],
        "largest_files": [row.__dict__ for row in context["file_rows"][:50]],
        "recent_commits": [row.__dict__ for row in context["recent_commits"]],
        "weekly_commits": [row.__dict__ for row in context["weekly_commits"]],
        "weekly_highlights": context["weekly_highlights"],
        "workflow_agents": context["workflow_agents"],
    }


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    context = collect_context()
    build_pdf(context)
    build_ppt(context)
    CONTEXT_OUTPUT.write_text(json.dumps(serialize_context(context), indent=2), encoding="utf-8")
    print(f"Updated PDF: {PDF_OUTPUT}")
    print(f"Updated PPTX: {PPT_OUTPUT}")
    print(f"Wrote context: {CONTEXT_OUTPUT}")
    print(f"Wrote tree: {TREE_OUTPUT}")


if __name__ == "__main__":
    main()
