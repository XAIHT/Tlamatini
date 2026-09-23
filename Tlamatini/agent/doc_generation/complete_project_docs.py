# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from __future__ import annotations

import ast
import hashlib
import io
import importlib.util
import json
import os
import re
import subprocess
import tokenize
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from PIL import Image as PillowImage

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
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
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
    ".bcmap",
    ".gif",
    ".icc",
    ".pfb",
    ".ttf",
    ".wasm",
    ".woff",
    ".woff2",
    ".7z",
    ".dll",
    ".exe",
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
    ".sqlite3",
    ".wav",
    ".zip",
}

LANGUAGE_BY_EXTENSION = {
    ".bat": ("Batch", "Batch"),
    ".cpp": ("C++", "C++"),
    ".css": ("CSS", "CSS"),
    ".flw": ("Tlamatini Flow", "Flow"),
    ".html": ("HTML", "HTML"),
    ".ini": ("INI", "INI"),
    ".js": ("JavaScript", "JS"),
    ".cjs": ("JavaScript", "JS"),
    ".json": ("JSON", "JSON"),
    ".md": ("Markdown", "MD"),
    ".mjs": ("JavaScript module", "MJS"),
    ".pmt": ("Prompt template", "Prompt"),
    ".proto": ("Protocol Buffers", "Proto"),
    ".ps1": ("PowerShell", "PowerShell"),
    ".py": ("Python", "Python"),
    ".svg": ("SVG", "SVG"),
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
RECENT_GIT_WINDOW_DAYS = 3
RECENT_GIT_WINDOW_LABEL = "last 3 days"
RECENT_GIT_WINDOW_TITLE = "Recent Git Window"
RECENT_GIT_HIGHLIGHT_TITLE = "recent highlights"
RECENT_GIT_APPENDIX_SUBTITLE = "all commits from the last 3 days according to git"


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


@dataclass
class CommitBaseline:
    full_hash: str
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


def release_identity() -> str:
    """Keep tagged release identity separate from the inspected checkout."""
    tag = git("describe", "--tags", "--abbrev=0", "HEAD")
    tag_commit = git("rev-parse", "--short", f"{tag}^{{commit}}")
    head = git("rev-parse", "--short", "HEAD")
    distance = git("rev-list", "--count", f"{tag}..HEAD")
    remote = git("rev-parse", "--short", "origin/main")
    try:
        advertised = git("ls-remote", "--tags", "origin", f"refs/tags/{tag}")
        publication = (f"Origin advertises {tag}. " if advertised else
                       f"Origin does not advertise {tag}; it is a local tag. ")
    except subprocess.CalledProcessError:
        publication = "Remote tag publication could not be checked. "
    return (
        f"The reachable local tag {tag} resolves to {tag_commit}. "
        f"Current source HEAD is {head}, {distance} commit(s) beyond that tag. "
        f"Fetched origin/main resolves to {remote}. {publication}Runtime version resolution remains "
        "Git/build-derived. A source revision beyond the tag is not a new tagged release."
    )


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


def git_tracked_paths() -> list[str]:
    return [line for line in git("ls-files").splitlines() if line.strip()]


def git_untracked_paths() -> list[str]:
    return [line for line in git("ls-files", "--others", "--exclude-standard").splitlines() if line.strip()]


def inventory_paths() -> list[str]:
    return sorted(set(git_tracked_paths()) | set(git_untracked_paths()))


def has_esphomer_assets() -> bool:
    return (PROJECT_DIR / "agent" / "agents" / "esphomer" / "config.yaml").exists()


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
    source_lines = text.splitlines()
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
            # Executable multiline strings (SQL, prompts, JS) occupy multiple
            # physical source lines. Counting only the opening token line
            # silently discarded their authored continuation lines.
            for line_number in range(token.start[0], token.end[0] + 1):
                if (line_number not in doc_lines and line_number <= len(source_lines)
                        and source_lines[line_number - 1].strip()):
                    effective_lines.add(line_number)
    except tokenize.TokenError:
        return count_generic_effective(text, ".py")
    return len(effective_lines)


def remove_block_comments(text: str, suffix: str) -> str:
    if suffix in {".js", ".cjs", ".mjs", ".css", ".proto", ".cpp"}:
        return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    if suffix in {".html", ".md", ".svg"}:
        return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    if suffix == ".ps1":
        return re.sub(r"<#.*?#>", "", text, flags=re.DOTALL)
    return text


def strip_inline_comment(line: str, suffix: str) -> str:
    stripped = line.strip()
    if suffix in {".yaml", ".yml", ".ps1"}:
        return "" if stripped.startswith("#") else line
    if suffix in {".js", ".cjs", ".mjs", ".css", ".proto", ".cpp"}:
        return "" if stripped.startswith("//") else line
    if suffix == ".ini":
        return "" if stripped.startswith((";", "#")) else line
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
        if not absolute.is_file():
            skipped_count += 1
            continue
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


def _commit_is_retired_for_dossier(subject: str) -> bool:
    lowered = subject.lower()
    return any(token in lowered for token in ("toast", "toaster", "native_toast", "windows-toast"))


def recent_commits(limit: int = 10) -> list[CommitInfo]:
    raw = git("log", "-n40", "--format=%h%x1f%cI%x1f%s")
    commits: list[CommitInfo] = []
    for line in raw.splitlines():
        short_hash, committed_at, subject = line.split("\x1f", 2)
        if _commit_is_retired_for_dossier(subject):
            continue
        commits.append(CommitInfo(short_hash, committed_at, subject))
        if len(commits) >= limit:
            break
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


def last_visual_doc_commit() -> CommitBaseline | None:
    raw = git(
        "log",
        "-n1",
        "--format=%H%x1f%h%x1f%cI%x1f%s",
        "--",
        PDF_OUTPUT.name,
        PPT_OUTPUT.name,
    )
    if not raw:
        return None
    full_hash, short_hash, committed_at, subject = raw.split("\x1f", 3)
    return CommitBaseline(full_hash, short_hash, committed_at, subject)


def commits_since_visual_docs(baseline: CommitBaseline | None) -> list[CommitInfo]:
    if baseline is None:
        return recent_commits()
    raw = git("log", f"{baseline.full_hash}..HEAD", "--format=%h%x1f%cI%x1f%s")
    commits: list[CommitInfo] = []
    for line in raw.splitlines():
        short_hash, committed_at, subject = line.split("\x1f", 2)
        commits.append(CommitInfo(short_hash, committed_at, subject))
    return commits


def weekly_highlights(commits: list[CommitInfo]) -> list[str]:
    """Use commit-specific evidence, never broad keyword guesses or disk presence."""
    notes = {
        "11d8130": "Extends Video-Analyzer with timestamped audio-track transcription and audiovisual summaries, retaining robotics as the default. Adds PyAV decoding, local faster-whisper, bounded visual batches, structured artifacts and migration 0207. Parametrizer, UI, wrapped tools, MCP and packaging contracts move together.",
        "2cf8e7f": "Carries the published v1.63.0 tag even though its commit subject names 1.62.2. Git tags, not commit-subject prose, determine the current release version. Later Video-Analyzer source is at 11d8130.",
        "5275f44": "Repairs unambiguous external-MCP scalar mismatches before schema validation: Boolean/string enum spelling, true/false strings and numeric strings. Ambiguous values remain validation errors. Nine focused regression cases accompany the change.",
        "2bac945": "The last committed dossier baseline covers Whisperer trailing silence at 3.5 seconds and the jcyhsiao/qwen3.5cloud:latest model tag, with migrations 0205/0206. This refresh compares that committed baseline with current source.",
        "2db5e26": "Sets Whisperer's default trailing silence to 3.5 seconds and preserves fractional seconds in its console label. Renames the configured Qwen vision tag to jcyhsiao/qwen3.5cloud:latest. Migrations 0205/0206 update existing prompt content without changing catalog identities. This source commit follows v1.62.2; no migrations or tests were executed for this refresh.",
        "92a5830": "Carries the v1.62.2 tag: local frontend dependencies, strict static/runtime asset receipts, the 1.99 GB ZIP ceiling, complete self-modify snapshots and pre-shutdown update verification. Carries the integrity helper, shared preservation contract and WAL/evidence safeguards. Source inspection does not establish a successful frozen release build.",
        "cae78c3": "Repairs five order-dependent log-capture harnesses. AudioPlayer suppresses real audio under TLAMATINI_NO_AUDIO while explicitly marked fake sounddevice modules can exercise streaming math. No tests ran in this dossier refresh.",
        "6dd2b7e": "Updates README, Book, self-knowledge and document-agent contracts. Clarifies audit confidence, partial LaTeX results and repair boundaries instead of equating creation with verification.",
        "63afbf9": "Adds explicit frozen PDF/PyMuPDF collection, a LAN-safe UUID fallback, strict source-snapshot carriage and WAL-aware update backup. These changes were source-reviewed without a full frozen-build run.",
        "814cd9a": "Introduces the PDF canvas with local range reads, whole-document context, optional Image-Interpreter analysis and cancellable progress. Adds pinned PDF.js assets and removes six gallery videos. The v1.62.0 tag resolves here.",
        "f3138d4": "Commits the preceding 73-page PDF and 197-slide deck, covering v1.60.0, visual styles, desktop contracts and the 1,148-file inventory.",
        "c4daacc": "Updates release-facing handbooks, self-knowledge and package metadata to v1.60.0. The tag remains at cef3995, one commit before this documentation commit.",
        "cef3995": (
            "Tightens Mouser/Keyboarder/Shoter input receipts, Parametrizer mappings, "
            "FlowCreator validation and FlowHypervisor monitoring. Bundles usable ESP32 "
            "and ESPHome starter projects. GUI-Manager remains a design. Pins fonttools."
        ),
        "14647ab": "Adds LaTeXer's 30 signature styles, independent template controls, original TikZ artwork and engine-free style discovery. Records implementation verification separately from this refresh.",
        "1d22228": "Adds PDFer's 24 signature styles and PPTXer's 12 explicit styles, with typography and layout repairs. Removes the 62 earlier output assets from the tracked tree. Reusable verifier sources remain.",
        "5c6d47e": "Introduces PPTXer, the 89th installed agent and 67th wrapped tool. Adds three migrations, document prompts 123/124, native rendering and reusable layout/visibility sources.",
        "97b5bac": "Commits the preceding whole-project PDF/PPTX refresh for Grepper's line-reading contract and the earlier release boundary.",
        "7764353": "Restores CRLF endings in eleven files changed by the Grepper feature commit, without changing their behavior.",
        "4ae6da6": (
            "Adds Grepper's single-file lines mode, inclusive ranges and content_b64 "
            "transport. Updates wrapped-tool and Parametrizer contracts, self-knowledge "
            "and handbooks. Adds three regression/visible-harness sources, not run here."
        ),
        "1dcd805": "Updates release-facing documentation and package metadata to v1.51.9. The annotated tag resolves to cb30edf, before the Grepper change.",
        "7800610": "Commits the previous dossiers and expands sampler/uninstaller maintainer guidance. The mcp_agent.py change adds explanatory comments, not a new sampler path.",
        "cb30edf": (
            "Forwards repeat_last_n through both Ollama chains and ChatOllama, adds "
            "it to the parameter banner, and aligns defaults at 256 / 1,048,576 "
            "for repeat_last_n / num_ctx. Commit measurements are historical and model-specific."
        ),
        "f6404a3": (
            "Aligns both Ollama repeat_penalty fallbacks and the shipped setting at "
            "1.2. The commit reports fewer empty answers in its eight-trial workload. "
            "Those experiments were not rerun for this dossier."
        ),
        "a2287c9": "Commits the previous dossier refresh and simplifies commit-specific recent-change summaries.",
        "b07f9d5": (
            "Adds the uninstaller's Retry/Exit running-process gate and preserves "
            "five named content directories when populated or unreadable. Includes "
            "mechanics and visible-harness sources, inspected without execution."
        ),
        "36c0139": (
            "Adds standalone ollama_credits.py for signed Ollama account-usage requests "
            "and console/JSON output. The card's $300 denominator and default reset "
            "day are script assumptions, not account-verified billing facts."
        ),
        "ac72b6c": (
            "Repairs chat_agent_run_wait by reconciling the real child process on "
            "every poll and using RUNNING_STATUSES. Five regression cases accompany "
            "the fix. They were not executed for the 2026-09-13 dossier refresh."
        ),
        "efe2ca1": (
            "Updates the PDF/PPTX for canvas presence, Whisperer's sound gate and "
            "Voice Commands. Corrects Python multiline-string effective-line counting."
        ),
        "a867567": (
            "Adds Voice Commands as the first prompt-catalog category, with guided "
            "rehearsal 121 and spoken-prompt execution 122. The transcript is shown "
            "before execution and irreversible/external actions need typed confirmation."
        ),
        "e403d5c": (
            "Reconciles the Whisperer sound-gate documentation, prompt 74 and runtime "
            "contracts. FlowHypervisor allows the bounded capture wait."
        ),
        "96fdbde": (
            "Adds Whisperer's default silence gate, actual captured duration and "
            "explicit fixed-fallback reporting. This is the v1.51.7 tag commit."
        ),
        "7e48e63": (
            "Adds word-timed canvas avatar presence, asymmetric blinks and adaptive "
            "frame rates, with CPU-only rendering and an opaque fallback."
        ),
        "7ae8d86": (
            "Introduces blended avatar rendering, followed by the presence renderer "
            "in 7e48e63. The four portrait JPGs remain the expression sources."
        ),
        "590cb8b": (
            "Repairs Gitter Windows-path tokenization and refreshes project dossiers. "
            "The commit carries the earlier avatar assets and verification evidence."
        ),
        "2ea219a": "Changes the default cloud model from glm-5.2:cloud to glm-5.3:cloud.",
        "46a18c8": (
            "Repairs full-portrait transparency flashing and publishes image packages, "
            "visible-test evidence and the Python launcher. This is historical atomic-renderer evidence."
        ),
        "4a7f1cb": "Refreshes visual documentation for console shielding and welcome-page navigation.",
        "d8f21f3": "Continues handbook reconciliation for console shielding and welcome-page navigation.",
        "0d2c09c": "Documents console shielding and the welcome-page keyboard default.",
        "c8cf369": (
            "Adds a queued console sink with file-first logging, frozen QuickEdit "
            "protection and an Enter-to-chat shortcut on the welcome page."
        ),
    }
    return [
        f"Commit {row.short_hash}: {notes.get(row.short_hash, row.subject)}"
        for row in commits
    ] or ["No commits fall in this Git window."]


def visual_doc_highlights(commits: list[CommitInfo]) -> list[str]:
    """Describe exactly the selected baseline-to-HEAD commits."""
    return weekly_highlights(commits)


def _load_module_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_version_info() -> dict[str, str]:
    # Honor an explicit TLAMATINI_VERSION override, exactly like the build
    # scripts do (versioning.py precedence #2). This lets a release be
    # documented before its git tag is cut — set TLAMATINI_VERSION=X.Y.Z when
    # running the generator. With no override it falls through to git tags.
    override = os.environ.get("TLAMATINI_VERSION", "").strip()
    if override:
        return {
            "version": override,
            "build": override,
            "commit": git("rev-parse", "--short", "HEAD"),
            "date": git("show", "-s", "--format=%cI", "HEAD"),
            "source": "environment release target",
        }
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


def agent_description_names() -> list[str]:
    path = REPO_ROOT / "agents_descriptions.md"
    return re.findall(
        r"^\|\s+\*\*([^*]+)\*\*\s+\|",
        path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )


def validate_agent_description_parity(agents: list[str], descriptions: list[str]) -> None:
    def normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    agent_keys = {normalize(name): name for name in agents}
    description_keys: dict[str, str] = {}
    duplicates: list[str] = []
    for name in descriptions:
        key = normalize(name)
        if key in description_keys:
            duplicates.append(name)
        description_keys[key] = name

    missing_rows = sorted(agent_keys[key] for key in agent_keys.keys() - description_keys.keys())
    stale_rows = sorted(description_keys[key] for key in description_keys.keys() - agent_keys.keys())
    if duplicates or missing_rows or stale_rows:
        raise RuntimeError(
            "agents_descriptions.md parity failed: "
            f"duplicates={duplicates}, missing_rows={missing_rows}, stale_rows={stale_rows}"
        )


def count_wrapped_chat_agent_tools() -> int:
    path = PROJECT_DIR / "agent" / "chat_agent_registry.py"
    text = path.read_text(encoding="utf-8")
    return len(re.findall(r'tool_name\s*=\s*"([^"]+)"', text))


def count_skills() -> int:
    skills_root = PROJECT_DIR / "agent" / "skills_pkg"
    return sum(1 for entry in skills_root.iterdir() if entry.is_dir() and (entry / "SKILL.md").exists())


def count_external_mcp_supervisor_tools() -> int:
    path = PROJECT_DIR / "agent" / "external_mcp_manager.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "_SUPERVISOR_TOOL_NAMES"
                   for target in node.targets):
            continue
        value = node.value
        if isinstance(value, ast.Call) and value.args:
            value = value.args[0]
        if isinstance(value, (ast.Set, ast.List, ast.Tuple)):
            return sum(1 for item in value.elts if isinstance(item, ast.Constant))
    raise RuntimeError("Could not derive External-MCP supervisor count from source")


def collect_context() -> dict:
    tracked = git_tracked_paths()
    untracked = git_untracked_paths()
    paths = inventory_paths()
    tree_text = build_tree(paths)
    language_rows, file_rows, binary_count, skipped_count = line_stats_for_paths(paths)
    total_effective = sum(row.effective_lines for row in language_rows)
    total_lines = sum(row.total_lines for row in language_rows)
    agents = workflow_agents()
    descriptions = agent_description_names()
    validate_agent_description_parity(agents, descriptions)
    wrapped_chat_tools = count_wrapped_chat_agent_tools()
    skills_count = count_skills()
    external_mcp_supervisors = count_external_mcp_supervisor_tools()
    reference_media = extract_reference_media()
    weekly = recent_week_commits()
    visual_baseline = last_visual_doc_commit()
    visual_commits = commits_since_visual_docs(visual_baseline)
    version_info = resolve_version_info()

    context = {
        "generated_at": local_stamp(),
        "head_short": git("rev-parse", "--short", "HEAD"),
        "head_full": git("rev-parse", "HEAD"),
        "head_subject": git("show", "-s", "--format=%s", "HEAD"),
        "head_date": git("show", "-s", "--format=%cI", "HEAD"),
        "inventory_files": len(paths),
        "tracked_files": len(tracked),
        "untracked_files": len(untracked),
        "tracked_paths": tracked,
        "untracked_paths": untracked,
        "missing_paths": [path for path in paths if not (REPO_ROOT / path).is_file()],
        "inventory_paths": paths,
        "tree_text": tree_text,
        "language_rows": language_rows,
        "file_rows": file_rows,
        "binary_count": binary_count,
        "skipped_count": skipped_count,
        "total_effective_lines": total_effective,
        "total_lines": total_lines,
        "workflow_agents": agents,
        "workflow_agent_count": len(agents),
        "agent_description_rows": len(descriptions),
        "wrapped_chat_agent_count": wrapped_chat_tools,
        "core_python_tool_count": 20,
        "acpx_tool_count": 12,
        "external_mcp_supervisor_count": external_mcp_supervisors,
        "total_multi_turn_tools": 20 + wrapped_chat_tools + 12 + external_mcp_supervisors,
        "skills_count": skills_count,
        "requirements_count": count_requirements(),
        "js_modules": len(list((PROJECT_DIR / "agent" / "static" / "agent" / "js").glob("*.js"))),
        "css_files": len(list((PROJECT_DIR / "agent" / "static" / "agent" / "css").glob("*.css"))),
        "html_templates": len(list((PROJECT_DIR / "agent" / "templates" / "agent").glob("*.html"))),
        "migrations": len(list((PROJECT_DIR / "agent" / "migrations").glob("*.py"))) - 1,
        "recent_commits": recent_commits(),
        "weekly_commits": weekly,
        "weekly_highlights": weekly_highlights(weekly),
        "visual_doc_baseline": visual_baseline,
        "visual_doc_commits": visual_commits,
        "visual_doc_highlights": visual_doc_highlights(visual_commits),
        "reference_media": reference_media,
        "version_info": version_info,
    }
    context.update(collect_publication_context(context))
    vendor_prefix = "Tlamatini/agent/static/agent/vendor/pdfjs/"
    vendor_rows = [row for row in file_rows if row.path.startswith(vendor_prefix) and row.path in tracked]
    context["pdfjs_inventory"] = {
        "tracked_files": sum(path.startswith(vendor_prefix) for path in tracked),
        "physical": sum(row.total_lines for row in vendor_rows),
        "effective": sum(row.effective_lines for row in vendor_rows),
        "local_only": [],
    }
    for name in ("build/pdf.mjs", "build/pdf.worker.mjs"):
        relative = vendor_prefix + name
        path = REPO_ROOT / relative
        if relative not in tracked and path.is_file():
            text = path.read_text(encoding="utf-8")
            context["pdfjs_inventory"]["local_only"].append({
                "path": relative, "bytes": path.stat().st_size,
                "physical": len(text.splitlines()),
                "effective": count_generic_effective(text, ".mjs"),
            })
    return context


def collect_publication_context(context: dict) -> dict:
    """Inventory published evidence without loading private configuration values."""
    tag = git("describe", "--tags", "--abbrev=0", "HEAD")
    baseline = context["visual_doc_baseline"]
    baseline_ref = baseline.short_hash if baseline else tag
    added = sorted(set(git("diff", "--name-only", "--diff-filter=A", f"{baseline_ref}..HEAD").splitlines())
                   | set(context["untracked_paths"]))
    removed = sorted(set(git("diff", "--name-only", "--diff-filter=D", f"{baseline_ref}..HEAD").splitlines())
                     | set(git("diff", "--name-only", "--diff-filter=D", "HEAD").splitlines()))
    stats = {row.path: row for row in context["file_rows"]}
    published = [path for path in context["tracked_paths"] if path.startswith("output/")]
    # A local leftover is not evidence that Git still publishes it. The style
    # release removed the old output corpus, so its manifest is now optional.
    manifest_assets = []
    manifest_name = "output/ASSET_MANIFEST.json"
    if manifest_name in published:
        manifest_assets = json.loads((REPO_ROOT / manifest_name).read_text(encoding="utf-8"))["assets"]
        for asset in manifest_assets:
            data = (REPO_ROOT / asset["path"]).read_bytes()
            if len(data) != asset["bytes"] or hashlib.sha256(data).hexdigest() != asset["sha256"]:
                raise RuntimeError(f"Published asset manifest mismatch: {asset['path']}")
        if set(published) != {row["path"] for row in manifest_assets} | {manifest_name}:
            raise RuntimeError("Published output manifest path parity failed")
    evidence_path = "output/avatar_flash_fix/visible-test/results.json"
    evidence_commit = git("log", "-1", "--diff-filter=AM", "--format=%H", "HEAD", "--", evidence_path)
    evidence = json.loads(git("show", f"{evidence_commit}:{evidence_path}")) if evidence_commit else None
    rows = []
    for path in added:
        absolute = REPO_ROOT / path
        if not absolute.is_file():
            continue
        row = stats.get(path)
        kind = "text" if row else "binary"
        if absolute.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            with PillowImage.open(absolute) as img:
                kind = f"{img.width}x{img.height} {img.mode}"
        rows.append({
            "path": path, "bytes": absolute.stat().st_size, "kind": kind,
            "physical": row.total_lines if row else None,
            "effective": row.effective_lines if row else None,
        })
    return {
        "release_identity": release_identity(), "release_tag": tag,
        "remote_head": git("rev-parse", "origin/main"),
        "git_describe": git("describe", "--tags", "--long", "HEAD"),
        "worktree_status": git("status", "--short"),
        "new_assets": rows, "published_files": len(published),
        "removed_assets": removed,
        "removed_output_files": sum(path.startswith("output/") for path in removed),
        "published_bytes": sum((REPO_ROOT / path).stat().st_size for path in published),
        "manifest_verified_files": len(manifest_assets),
        "avatar_evidence": None if evidence is None else {
            "source_commit": evidence_commit, "source_path": evidence_path,
            "reported_clean": bool(evidence["finished"] and not evidence["failures"] and not evidence["pageErrors"]),
            "transitions": len(evidence["transitions"]), "paints": evidence["paints"],
            "min_coverage": evidence["minCoverage"], "states": len(evidence["states"]),
            "viewports": len(evidence["rectangles"]), "controls": evidence["controls"],
            "voice": evidence["voice"]["name"],
        },
    }


def publication_guide(context: dict) -> list[str]:
    evidence = context["avatar_evidence"]
    baseline = context["visual_doc_baseline"]
    baseline_ref = baseline.short_hash if baseline else context["release_tag"]
    historical = (
        f"Git history at {evidence['source_commit'][:7]} retains the older atomic-renderer "
        f"report: {evidence['transitions']} transitions, {evidence['paints']:,} paints, "
        f"minimum coverage {evidence['min_coverage']:.0%}, reported clean={evidence['reported_clean']}. "
        "It describes that earlier renderer, not a fresh canvas verification."
        if evidence else "No historical avatar result was found in the reachable Git history."
    )
    return [
        f"Since the last committed dossier revision, the inspected checkout adds {len(context['new_assets'])} files "
        f"including {context['untracked_files']} untracked working additions. "
        f"The delta removes {len(context['removed_assets'])} paths (including pending deletions), with "
        f"{context['removed_output_files']} under output/. The current tracked output inventory "
        f"has {context['published_files']} files. Local leftovers never establish publication.",
        "The new-asset table lists the actual delta from the committed dossier baseline, "
        "not the older PDF-canvas rollout. The four additions are Video-Analyzer's README, "
        "video_content.py, migration 0207 and the content regression suite. PDF.js and release gates are "
        "already tracked. Binary fonts, character maps, decoders and media have no line count.",
        f"Current inventory: {context['tracked_files']:,} tracked plus {context['untracked_files']} pending files, "
        f"{context['total_lines']:,} physical text lines, {context['total_effective_lines']:,} "
        f"effective lines, and {context['binary_count']} binary assets. Counts include source "
        "and documentation plus vendored third-party code. Ignored galleries, caches and "
        f"runtime state are excluded. {len(context['missing_paths'])} index paths are absent "
        "from disk and excluded from line/binary totals. Config values are never reproduced.",
        f"Changes after dossier commit {baseline_ref} are listed in the Git appendix. "
        "Video audio transcription, summaries and external-MCP scalar repair join the whole-system coverage. "
        "The tag and later source commits are distinguished. Runtime avatar JPGs remain "
        "tracked despite the earlier removal of the old output corpus.",
        historical + " Focused source regressions and document validation are checked separately. "
        "Document rendering and layout inspection are the only new visual evidence.",
        f"Historical v1.62.0 handbook snapshots precede the current {context['version_info']['version']} "
        "release; the September 16 commit-assets instructions describe already tracked files. Historical 108-tool/66-wrapper "
        "labels, 204 migrations and old line totals were reconciled to live source. Django is pinned "
        "at 5.2.15. The viewer exposes navigation and text selection; no dedicated find control exists. "
        "These dossiers use source-derived counts and actual Git refs, preserving historical evidence.",
    ]


PDF_CANVAS_GUIDE = [
    "Open or Reopen accepts PDF beside ordinary text files. The isolated PDF.js frame "
    "supports selectable text, page navigation, fit width/page, zoom, rotation and "
    "continuous/single-page scrolling. Password entry stays in the viewer.",
    "Copy extracts selectable text from every page and reports image-only scans. "
    "Save As returns the original PDF bytes. Clear, text selection or generated text "
    "removes the frame and worker. Generation checks reject stale asynchronous reads.",
    "Opening uses File.slice range requests of 256 KiB with streaming and auto-fetch "
    "disabled. It uploads no document and invokes no model. There is no application "
    "size/page cutoff, but memory, disk and document complexity still limit capacity.",
    "Visible/nearby pages render within an 8-megapixel canvas budget and 16,384-pixel "
    "dimension limit. Above 10,000 pages PDF.js selects single-page scrolling. Copying "
    "all text still allocates that text in memory. These are policies, not unlimited capacity.",
    "Divider pointer capture survives movement across the PDF frame. Release, cancelled "
    "touch, lost capture and focus loss end resizing. Keyboard resizing remains. The "
    "frame bridge checks source window, same origin and a fixed channel.",
    "Source: agent_page_pdf.js, pdf_canvas_viewer.js and pdf/canvas.html. PDF scripting "
    "is disabled. The custom toolbar has no find/search control or PDFFindController "
    "wiring, despite search wording in the handbooks. This refresh does not add one.",
]

PDF_CONTEXT_GUIDE = [
    "Use as context first opens an options dialog. Process images starts unchecked "
    "every time. Continue is required before upload or preparation. Earlier Cancel, "
    "Escape or close leaves the existing context unchanged.",
    "Text-only extracts every page with PyMuPDF and skips rendering, image extraction "
    "and vision calls. A scan without selectable text refuses with an image-mode hint. "
    "Mixed documents mark pages without text. Each mode keeps a separate cache.",
    "Image mode renders every page preview and extracts unique embedded images. "
    "The saved Image-Interpreter configuration drives two parallel vision calls and "
    "a merger for each artifact. PDF-specific instructions request OCR, chart/table "
    "interpretation and explicit uncertainty. Configured model services may be remote.",
    "Continue uploads to the configured Tlamatini server, which can be reached over LAN. "
    "A serial background queue prepares source.pdf, document.txt and optional images/reports "
    "under context_files/pdf_canvas/<user-id>/<document-id>/. Login, CSRF, method guards "
    "and user-bound signed tokens protect prepare/status/cancel and RAG handoff.",
    "All extracted text and complete image reports remain in the index. Normal RAG "
    "retrieval and model context limits still govern each answer. Reading the full index "
    "does not mean sending every page to the model on every turn. Text-only preparation "
    "needs no vision service, but later RAG/chat uses the configured services.",
    "Successful packages persist for session restoration. Failed/cancelled preparation "
    "removes its own incomplete package and upload staging. Passwords stay in parsing "
    "memory, outside storage/context/logs. Job status is process-local, with completed "
    "entries pruned after one hour during later activity. Restarted jobs require retry.",
]

PDF_PROGRESS_GUIDE = [
    "Four progress rows separate upload bytes, extracted pages, analyzed images and "
    "context loading. Text-only marks images Skipped. The elapsed timer starts at "
    "Continue and RAG stays indeterminate until the consumer acknowledges completion.",
    "Cancel aborts browser requests and signals a user-scoped UUID, including uploads "
    "whose job response has not arrived. Workers check between chunks, pages and image "
    "calls. An in-flight model request may finish before cancellation takes effect.",
    "After RAG loading starts, Close dismisses the dialog without cancelling that phase. "
    "Success closes automatically. Failure remains visible and allows retry. Incomplete "
    "image analyses remain in saved reports and the viewer warning, not a false clean result.",
    "PDF and chat own separate busy indicators. Reopen prepares a replacement before "
    "rebuilding active context. Preparation cancellation keeps prior backend context. "
    "A UUID fallback uses crypto.getRandomValues when randomUUID is unavailable on HTTP LAN.",
    "docs/pdf-canvas.md records earlier September 16 results: 12 browser/static tests "
    "and 32 Django/image/JS-gate tests, plus a 256 MB sparse fixture and page 10,001. "
    "Later frozen-carriage changes explicitly have source-review evidence only.",
    "This dossier refresh does not run the app server, cloud model calls, collectstatic or "
    "a frozen build. Earlier application test results remain dated historical evidence. "
    "Document rendering establishes dossier layout evidence only, not runtime behavior.",
]


def pdf_distribution_guide(context: dict) -> list[str]:
    vendor = context["pdfjs_inventory"]
    local = vendor["local_only"]
    local_summary = "; ".join(
        f"{Path(row['path']).name}: {row['bytes']:,} bytes, "
        f"{row['physical']:,} physical / {row['effective']:,} effective lines"
        for row in local
    )
    return [
        "Mozilla PDF.js 6.3.289 supplies the viewer, fonts, CMaps, annotation artwork, "
        "ICC profile and WASM decoders. scripts/vendor_pdfjs.py checks a pinned npm "
        "archive's SHA-512 before extracting an explicit subset. Runtime rendering "
        "needs neither npm nor a CDN when all assets are present.",
        f"Tracked PDF.js contribution: {vendor['tracked_files']} files, "
        f"{vendor['physical']:,} physical and {vendor['effective']:,} effective text lines. "
        "These third-party lines are included in repository totals and should not be "
        "mistaken for new Tlamatini-authored logic. Binary resources count as files only.",
        ("Git publication pending: build/pdf.mjs and build/pdf.worker.mjs were hidden "
         "by the global build/ ignore rule. A narrow exception now exposes them as "
         "working-tree additions. Commit these files with the packaging changes; "
         "remote clones remain incomplete until publication or explicit vendoring."
         if local else "Both required PDF.js build modules are present in the tracked inventory."),
        ("Untracked modules, included in combined working-tree totals but not tracked totals: " + local_summary + "."
         if local else "No local-only PDF.js build modules were found in this checkout."),
        "PyMuPDF 1.26.5 already existed in requirements. Frozen web imports now "
        "explicitly include four PDF services, the reusable Image-Interpreter and "
        "PyMuPDF. hook-pymupdf.py collects native MuPDF libraries. Carried pool Python "
        "cannot supply imports inside Tlamatini.exe.",
        "Django and WhiteNoise override .mjs and .wasm MIME types on Windows. "
        "The September 16 handbook records 354 pre-change static files matching a "
        "v1.62.0 ZIP in both frozen locations, plus native MuPDF extensions/DLL. "
        f"The v{context['version_info']['version']} source carries local frontend libraries and stricter build gates; those changes have not "
        "been built or runtime-tested during this refresh.",
    ]


MODEL_CONFIGURATION_GUIDE = [
    "Config > Models exposes 38 model, engine and voice settings for core services and 21 model-backed agents. Six searchable categories: Core 7, Vision 7, Speech 7, Workflows 6, Documents 5, Monitoring & messaging 6.",
    "Talker model/voice, Whisperer recognition engine/local/cloud/cleanup models, Video-Analyzer local audio, vision observers/mergers, workflows, documents and monitors all have dedicated choices. External ACPX/MCP providers retain their own settings.",
    "Save submits all 38 values, preserves unrelated configuration and downloads no weights. Changed Ollama choices are checked against the catalog; local and provider names are separate. Catalog presence is not a capability or entitlement test.",
    "Reconnect chat to rebuild clients. Agent choices apply at their next configuration load; restart an already running monitor when needed. Existing literal workflow choices are not silently rewritten by a global save.",
    "Quoted @config or a missing registered YAML field inherits. Canvas literals remain overrides. Wrapped chat seeds globals before explicit tool arguments; standalone MCP resolves template inheritance before invocation overrides.",
    "The full key/default/YAML-path reference, validation API and troubleshooting are in docs/model_configuration.md. The stdlib-only model_settings.py registry supplies metadata for the UI and portable agent loaders.",
]

MODEL_COMPATIBILITY_GUIDE = [
    "Talker requires an Orpheus-compatible audio-token model; ordinary chat models cannot speak. Supported voices: tara, leah, jess, mia, zoe. The SNAC 24 kHz decoder remains an internal format dependency.",
    "Whisperer engines: faster-whisper, cloud-groq, cloud-openai. Empty cloud model uses the code's provider default. Keys/endpoints remain agent settings. Selecting the cleanup model does not enable ollama_cleanup.",
    "Video audio uses an independent local faster-whisper model, initially base. Whisperer's cloud engine and microphone settings do not apply. Empty LaTeXer repair model disables model repair.",
    "Video vision initially uses gemma4:cloud and jcyhsiao/qwen3.5cloud:latest, merged by glm-5.3:cloud. Each observer must support images. Defaults record application choices, not permanent provider availability.",
    "Summary observer HTTP 401/403/404/410 failures disable that observer only for the current run. Healthy observers continue; status remains partial. visual_coverage distinguishes frames seen by any observer from those seen by both.",
    "Errors retain model, HTTP status and provider explanation. A retired HTTP 410 selection needs an available replacement and a check of existing workflow overrides. Robotics still requires two explicit independent passes for PASS_OK.",
]

MODEL_RUNTIME_GUIDE = [
    "Source config: Tlamatini/agent/config.json. Installed config: beside Tlamatini.exe. CONFIG_PATH overrides either. Portable agents locate the ancestor agents root; copied agents outside it need an explicit config path and helper.",
    "Frozen web code imports compiled agent.agents.model_settings. Portable helpers come from get_agents_root(), not synthetic _internal module paths. Non-model agents prepare without a loose registry; reusable pools refresh helpers.",
    "Monitor-Log, Monitor-Netstat and RecMailer read UTF-8 YAML including a BOM. The execution gate checks actual model loaders under Windows' default code page as well as normal source operation.",
    "build.py must carry check_agent_runtimes and execute it in the new frozen executable before packaging. The self-modify snapshot carries registry, runtime code, command, tests and documentation. Source snapshots remain optional at runtime.",
    "September 20 checks passed 89 runtime preparations, 21 model loaders, 3 catalog refreshes and exact File-Creator bytes in source, fresh frozen, snapshot-absent frozen and installed modes. Wrapped-chat and standalone MCP File-Creator also passed.",
    "Dated regression evidence: 394 passed, 5 skipped. Visible Models save/reopen changed Talker voice to jess, confirmed loader resolution, restored tara and reconnected. This does not exercise every provider or hardware action. See docs/model-configuration-verification.md.",
]


def model_reference_groups() -> dict[str, list[dict]]:
    """Load public metadata only; never read the operator's config or credentials."""
    path = REPO_ROOT / "Tlamatini/agent/agents/model_settings.py"
    spec = importlib.util.spec_from_file_location("dossier_model_settings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    groups: dict[str, list[dict]] = {}
    for field in module.FIELDS:
        groups.setdefault(field["group"], []).append(field)
    return groups


LATEST_SOURCE_GUIDE = [
    "Video-Analyzer keeps analysis_type=robotics by default. Transcription reads selected video audio tracks with local faster-whisper, preserving stream offsets, segment timestamps and optional word timestamps.",
    "Summary combines audio evidence with two independent visual observers per sampled frame batch and hierarchical text synthesis. Scenes, actions, readable text, numbers, procedures, decisions and limitations are retained with timestamps.",
    "The portable video_content.py helper bounds decoding and model context. Reports include UTF-8 transcript text, timestamped JSON and visual observations. Embedded subtitle streams are not extracted. Content modes bypass motion rejection and never emit a robotics PASS.",
    "Parametrizer, the agent registry, workflow controls, root MCP and prompt migration 0207 expose the same modes and result fields. PyAV 17.1.0 is pinned and the helper is carried by frozen builds and source snapshots.",
    "External MCP calls repair only unambiguous scalar type mismatches before server-schema validation. Boolean/string enum spelling and numeric strings can be normalized; ambiguous inputs still fail validation.",
    "Repository facts report actual HEAD and fetched origin/main separately from the requested 1.63.0 document/build version and reachable tags. The checkout includes uncommitted model/runtime changes; no tag is moved by this refresh.",
]


LATEST_DEFAULTS_GUIDE = [
    "Source commit 2bac945 follows the v1.62.2 tag. Whisperer now waits for 3.5 seconds "
    "of trailing silence by default. record_seconds=0 enables the gate, while the "
    "300-second maximum recording ceiling remains unchanged.",
    "The console uses fractional-second formatting, so the operator sees 3.5 rather "
    "than a rounded 4. Migration 0205 replaces old default text only in Voice Commands "
    "prompts 74, 121 and 122. Missing or differently edited passages are left alone.",
    "The configured vision model tag changes from qwen3.5:cloud to "
    "jcyhsiao/qwen3.5cloud:latest in application defaults, agent templates and prompts. "
    "This records repository configuration, not a fresh model-service availability check.",
    "Migration 0206 rewrites matching promptContent values across the catalog. Both "
    "migrations preserve prompt IDs, names, categories, sort ranks and visibility. "
    "Their reverse operations restore the preceding default text or model tag.",
    "Fresh seed migrations 0165/0168 and existing prompt-update paths use the new tag. "
    "Image-Interpreter slot 1 and Video-Analyzer slot 2 use it. The other configured "
    "vision and merger models are configurable in Config > Models.",
    "Migration 0207 adds Video-Analyzer content prompts; 0208 points matching robotics demo text to Config > Models. "
    "Repository facts derive the migration count from source. This dossier does not apply migrations. "
    "September 20 source/frozen runtime evidence is recorded separately from document rendering.",
]


LOCAL_RELEASE_GUIDE = [
    "The v1.63.0 source carries the removal of CDN resource tags from all four application templates. "
    "Bootstrap 5.3.3, jQuery 3.7.1, jQuery UI 1.13.3, highlight.js 11.9.0 and Nunito "
    "400/700 are local. The duplicate Bootstrap 5.3.0 load is removed; UI ordering "
    "is retained and new URLs use the startup cache stamp plus an offline suffix.",
    "scripts/vendor_frontend.py reproduces 50 files plus a vendor manifest: 2.18 MB "
    "before ZIP compression. Pinned npm archives are SHA-512 checked; licenses, "
    "font subsets and SHA-256 receipts ship locally. Builds do not invoke this "
    "download script. Model/API and Internet-agent traffic still needs networking.",
    "build_runtime_assets.py inventories source static, collected Django assets, "
    "templates, agents, skills and required helpers. Byte checks detect missing or "
    "stale source-to-collected/frozen copies. Literal static tags and CSS resources "
    "must resolve; reintroduced template CDN loads stop packaging.",
    "Missing Java/Git/active Playwright revisions, required copies or unreadable "
    "frozen module archives now fail closed. Frozen migration, default-user setup, "
    "collectstatic and executable rename must succeed. Session/pool/cache files "
    "are not shipped as agent templates. Snapshot rules carry the new helper/assets.",
    "A runtime-assets.json receipt hashes every assembled payload file. ZIP "
    "membership and streamed SHA-256/CRC are checked before pkg.zip.part is "
    "published; installer assembly verifies the receipt and version again. Both "
    "complete-release wrappers cap the final outer ZIP at 1,990,000,000 bytes.",
    "The September 16 handbook records a v1.62.0 ZIP of 1,905,278,037 bytes: "
    "84,721,963 bytes below the ceiling. This is historical headroom, not a current build result. Oversized "
    "final output stays .pending.zip and fails; required files are not removed. "
    "The dossier refresh checks source and rendered documents; no release build is claimed.",
]


SELF_CARRIAGE_GUIDE = [
    "A --self-modify build generates a fresh sanitized TlamatiniSourceCode tree and "
    "self-knowledge file. Default builds omit both. --no-self-modify wins if both "
    "flags appear. Missing required inputs, generation errors and copy failures now "
    "abort packaging instead of falling back to a stale tree.",
    "The exact PDF.js vendor/build directory bypasses the generic build-directory "
    "snapshot exclusion. Fonts, CMaps, decoders and licenses travel with that source "
    "snapshot. Secret/state exclusions retain priority. This is independent of Git's ignore rules.",
    "Snapshots omit .git and generated version modules. Rebuild instructions therefore "
    "require an intentional TLAMATINI_VERSION for all three build scripts. Restore "
    "omitted required binaries using the manifest, install dependencies and regenerate "
    "static files before a separate authorized rebuild.",
    "apply_update.ps1, preserved_user_state.json, sqlite_copy.py and the runtime "
    "integrity helper are mandatory carried assets. The checker is also embedded in "
    "the app and installer. Downloaded ZIP and staging receipts are verified before shutdown.",
    "Backup prerequisites are checked before shutdown. Carried Python runs the "
    "helper with -I -B -S, avoiding bytecode and site startup hooks. SQLite online backup includes committed WAL pages and "
    "atomically stages one standalone DB in DB/ToLoad. Failure stops before agents "
    "rename or file replacement. Only success creates the migration marker.",
    "The shared 13-name preservation contract retains configuration, contacts, DB, "
    "context and generated content. Reinstall retains the live DB/WAL and requests "
    "migration. Security-evidence stash failure stops deletion. The September 16 "
    "guide records 740 snapshot inputs and 15 PDFer ornaments. September 20 reran both inclusion sweeps clean; execution evidence is separate.",
]

DOCUMENT_CONTRACT_GUIDE = [
    "PDFer creation confirms a file exists. layout_audit=true on the atelier route "
    "supplies layout_clean and detailed findings. Blank audit evidence is unverified. "
    "Zero overlaps does not exclude contrast, blank-page or off-sheet problems. "
    "Legacy CSS, image-only and merged pages retain their own layouts.",
    "PPTXer reports status/success alongside layout_clean, ground_truth, render_tier "
    "and slides_rendered. Native rendering does not itself prove full measurement "
    "coverage. created_with_findings may still have success=true. Required missing "
    "media and skipped audit measurements must remain explicit.",
    "PPTXer's auto rendering tries PowerPoint, LibreOffice, then an approximate Pillow "
    "preview. None skips slide images while geometry may still be measured. Styles "
    "use nuance, with no separate style parameter. Native applications remain optional "
    "for creation; 256 characters is a stress case, not a content limit.",
    "LaTeXer compiled_with_errors and degraded mean an existing but incomplete/errored "
    "PDF with success=false. Clean compiled output is the stopping point unless a "
    "remaining requirement warrants edits. Compilation does not certify visual layout. "
    "Catalog/source actions work without a TeX engine.",
    "LaTeXer repair_write_back=false preserves source through a fixed copy. Model "
    "failure/timeout blocks destructive bisect; decoded base64 edit fields take "
    "precedence. Beamer scaffolds expect frame bodies. A full explicit frame sequence "
    "belongs in complete source without a style override.",
    "The current commit also detaches/restores global logging handlers in five "
    "regression harnesses. TLAMATINI_NO_AUDIO suppresses real AudioPlayer output, "
    "while a marked fake sounddevice can exercise callback frame math. These source "
    "changes are recorded without executing the tests.",
]


PPTXER_GUIDE = [
    "PPTXer creates editable PowerPoint from text, Markdown, outlines or JSON. "
    "Actions: create, outline, render, audit, info, fonts and validate. It supports "
    "16:9, 4:3 and vertical decks with native tables/charts, diagrams and embedded media.",
    "The registry has 36 treatments: 24 content treatments plus 12 explicit visual "
    "styles. Empty nuance retains automatic classification. nuance=blueprint or "
    "nuance=botanical selects a preset. Color, background, density and font overrides remain available.",
    "Seventeen font pairings resolve against installed fonts. Measurements account "
    "for face, tracking, line spacing and text insets. Dense content continues onto "
    "additional slides. The 256-character fixtures describe a tested length, not an input limit.",
    "Read status, layout_clean, ground_truth and report confidence together. "
    "created_with_findings requires review. Disabled audits leave the verdict "
    "unavailable. Native PowerPoint evidence, LibreOffice and geometric previews have different scopes.",
    "Migrations 0202/0203 register the agent and chat_agent_pptxer. Migration 0204 "
    "adds Documents prompts 123/124 at ranks 56/58, between PDFer and LaTeXer. "
    "Native rendering needs PowerPoint for its strongest evidence, although writing the deck does not.",
    "Source: agents/pptxer/ and its STYLES.md. The guide records 126 implementation "
    "tests and a 151-slide native run for the twelve new 16:9 styles. Those runs "
    "were not repeated here. scripts/verify_pptxer_styles.py regenerates the ignored gallery.",
]

PDFER_STYLES_GUIDE = [
    "PDFer adds 24 explicit visual identities across playful, cyberpunk, cosmic, "
    "electronics and Tlamatini families. The original 20 semantic themes remain. "
    "mode=styles lists IDs and aliases without creating a PDF.",
    "style selects appearance while nuance describes document purpose. For example, "
    "style=tlamatini_celestial with nuance=marketing selects a celestial brochure. "
    "Legal, clinical and financial semantics keep their no-ornament ceiling.",
    "predominant_color recolors the palette. Explicit role colors, typography and "
    "page settings override defaults before contrast repair. Host font availability "
    "affects the resolved face. Unknown style names retain the semantic theme with a diagnostic.",
    "Styles apply to the atelier renderer. Custom-CSS legacy rendering, image-only "
    "composition and merged PDFs keep their own layouts. Deterministic vector artwork "
    "adds no external image service or font download.",
    "The new helpers measure covers and reserve footer/page-number space. Complete "
    "titles can continue across pages. Check layout_clean and the detailed audit, "
    "including off-page ink and contrast. status=created alone establishes only file creation.",
    "Source: pdfer_styles.py, pdfer_artwork.py and STYLES.md. The guide records "
    "130 implementation tests and 24 two-page style samples with clean audits. "
    "scripts/verify_pdfer_styles.py can regenerate the ignored gallery. No such run occurred here.",
]

LATEXER_STYLES_GUIDE = [
    "LaTeXer adds 30 explicit styles in six families, independent of its eight "
    "document templates. action=list_styles returns IDs, aliases, motifs and "
    "style_count=30 without probing or requiring a TeX engine.",
    "Select template=report and style=tlamatini_celestial for a styled report. "
    "screen retains the preset ground. print uses white paper. style_decoration "
    "accepts none/restrained/rich. style_cover=false gives a compact document title.",
    "Article, report, book, beamer, letter, cv, homework and spanish-article remain "
    "distinct structures. Beamer uses a separate frame recipe and retains its title "
    "frame when cover art is disabled. Metadata and body remain LaTeX, so escape special characters.",
    "Styles work on scaffolds and fragment compile with auto_preamble=true. Complete "
    "TeX sources own their preamble, so an explicit style is refused on that route. "
    "Empty/none/plain/default preserves legacy generation. Unknown names fail clearly.",
    "Original TikZ geometry and Latin Modern fonts travel with editable TeX. "
    "Assigned text palettes target 4.5:1 contrast. Custom content still needs "
    "review. Check status/success before output_path. The runtime has no layout_clean field.",
    "Source: latexer_styles.py, latexer_design.py, latexer_artwork.py and STYLES.md. "
    "The guide records 483 tests and 132 fresh real-engine builds at implementation "
    "time. scripts/verify_latexer_styles.py regenerates the ignored gallery. No engines ran here.",
]

DESKTOP_INPUT_GUIDE = [
    "Mouser declares coordinate_space: screen, desktop, normalized, window, "
    "window_normalized or screenshot. Physical screen coordinates support negative "
    "monitor origins. Monitor gaps and ambiguous targets produce explicit failures.",
    "Shoter reports image dimensions, the physical capture rectangle, monitor "
    "geometry and capture time. Screenshot targets require all six geometry fields "
    "and Mouser's screenshot space. Cropping/resizing must update the corresponding geometry.",
    "The screenshot transform scales image coordinates into the captured desktop "
    "rectangle. It cannot establish which button occupies a point or repair a "
    "stale image. Reobserve after movement. inspect reads geometry without sending input.",
    "Keyboarder binds an HWND/PID, verifies foreground ownership during delivery "
    "and stops on focus loss. input_mode=text sends literal Unicode through checked "
    "SendInput. sequence keeps key/chord grammar. The clipboard remains untouched.",
    "input_sent proves delivery only. It does not prove editing, saving or "
    "application acceptance. Inspect partial-delivery counts and error receipts "
    "before replay. Target agents still receive failure notifications, so branch deliberately.",
    "Source: mouser_coordinates.py, keyboarder_input.py and shoter.py. Pool/chat "
    "refresh copies the helpers. Serialize desktop control within one interactive "
    "session. docs/GUI-Manager-design.md is a proposal, not an installed agent or global broker.",
]

FLOW_CONTRACT_GUIDE = [
    "FlowCreator first selects from all 89 installed types, then receives relevant "
    "guide sections and current schemas. Starter, Ender and Parametrizer remain "
    "available. Unknown or unselected types fail validation before publication.",
    "The validator checks references, branch slots, configuration types, singleton "
    "wiring and mapping fields. Counter's two branches are explicit. Ender's "
    "target_agents is a kill list and output_agents is its execution output.",
    "Bounded requests use llm.num_ctx=65536, max_prompt_chars=180000 and two "
    "repair attempts by default. These requests depend on provider support. "
    "Graph validation does not establish valid credentials or successful live application behavior.",
    "Parametrizer registers 53 declared structured-output producers. It preserves "
    "CRLF and empty values, converts typed scalar mappings and requires every "
    "mapping to succeed before writing or launching the target.",
    "Interrupted desktop segments at config_applied or waiting_target stop for "
    "inspection instead of replaying input. FlowHypervisor separates execution, "
    "kill and observation relationships and retains current desktop receipts and timing.",
    "services/flow_knowledge.py exports field names/types without local values. "
    "Deployment refreshes the shipped catalog and guides. docs/agent-coverage.md "
    "records discoverability, not successful execution of every workflow. Catalog and regression scripts were not run here.",
]

AVATAR_GUIDE = [
    "Four opaque 1024x1024 RGB JPGs combine open/closed eyes with neutral/smiling mouth. "
    "They share one square viewport. Existing non-rigid expression differences remain.",
    "The former 90 ms full-image opacity transition exposed the dark background. "
    "At two half-opaque frames, combined coverage is 75%. The recorded reproduction "
    "measured approximately 75.3%. Django collectstatic copied the JPG bytes correctly.",
    "avatar_presence.js now draws four decoded portraits on one 2D canvas. Eye/mouth "
    "weights form a convex blend with full coverage. Each corner is pre-scaled on resize. "
    "The old opaque image stack remains a fail-open fallback if canvas startup fails.",
    "Native speechSynthesis boundary events anchor a text-derived mouth track. Vowels "
    "open it, m/b/p close it, and punctuation introduces rests. Timing falls back to "
    "an estimated speaking rate when the voice exposes no word boundaries. There is "
    "no audio-amplitude analyzer, video stream, neural lip model or dedicated-GPU requirement.",
    "Blink timing uses 55 ms closing, 25 ms hold and 130 ms opening, with randomized "
    "intervals. Adaptive 12/20/30/60 FPS tiers respond to drawing cost. Portrait translation "
    "was removed, so the head/body coordinate system remains fixed.",
    "The current presence renderer intentionally keeps animating when the system requests "
    "reduced motion. This differs from the earlier atomic renderer. Resize by dragging "
    "the corner handle, arrow keys, or double-click presets. The chosen size persists in "
    "localStorage. Handle clicks do not trigger the greeting/stop control.",
]


AVATAR_TEST_GUIDE = [
    r"Current canvas regression: .\python\python.exe Tests\run_avatar_tests.py --presence-only --auto-close",
    "Use --check for dependency validation, --prepare-only for database/static preparation, "
    "or --auto-close to close the visible browser and its server after passing.",
    "The launcher prepares the isolated Temp/avatar_flash_fix database, applies migrations, "
    "creates the ordinary user/changeme test account, runs collectstatic, and starts real "
    "Django on 127.0.0.1:8001. It leaves the frozen app and normal database untouched.",
    "The presence suite uses Python Playwright, headed Chrome/Edge/Chromium and disabled "
    "GPU acceleration. It checks real canvas pixels, mouth-track correlation, native "
    "speech instrumentation, reduced-motion behavior, resizing and a 6x CPU throttle. No Node.js "
    "is needed for --presence-only. Simulated speech proves rendering, not microphone ASR.",
    "Current reports and whole-desktop Shoter photographs land in Temp/avatar_presence. "
    "Tests/run_presence_tests.ps1 is an alternative launcher. The older default suite "
    "uses Node.js and writes output/avatar_flash_fix/visible-test. Its atomic-state "
    "assumptions are historical. Use the presence-only command for the current renderer. "
    "The generic test credential must not become a production password.",
    "Recorded verification from 2026-09-12: all 74 presence checks passed in a visible "
    "browser. The separate Django run passed 110 Whisperer, voice-catalog and Gitter "
    "tests. These historical runs were not repeated for this refresh. They do not "
    "prove real microphone transcription, audible voice "
    "synchronization on every host, or a rebuilt frozen installation.",
]


GITTER_WORKTREE_GUIDE = [
    "Commit 590cb8b repairs Gitter custom_command tokenization on Windows. "
    "POSIX shlex treated backslashes as escapes and turned C:\\Dev\\msg.txt into C:Devmsg.txt.",
    "Windows now uses shlex.split(..., posix=False) plus one matching outer-quote removal. "
    "Backslashes survive and quoted multi-word arguments remain single tokens. "
    "POSIX hosts retain posix=True. Malformed quotes retain the existing split fallback.",
    "agent/test_gitter_custom_command.py adds 23 tests. The tests AST-load only the two "
    "helpers so they do not start a pool agent or write PID/log state. They cover Windows "
    "paths, quoted arguments, malformed input, POSIX behavior and source contracts.",
    "Source: agent/agents/gitter/gitter.py. Maintainer record: docs/claude/recent-fixes.md, "
    "2026-09-11 entry. The public handbooks describe Gitter generally but do not yet "
    "explain this tokenizer repair. It is committed in the current release ancestry.",
]


WHISPERER_GATE_GUIDE = [
    "Whisperer captures microphone audio itself or accepts an audio file. Local "
    "faster-whisper uses GPU when available and falls back to CPU. Cloud Whisper is "
    "an alternative engine. Ollama is optional transcript cleanup, never audio ASR.",
    "record_seconds=0 now selects the silence gate. Default trailing silence is 3.5 s "
    "and the hard ceiling is 300 s. A positive record_seconds selects fixed duration "
    "in auto mode. Explicit silence_gate=on forces gating, while off uses fixed capture.",
    "A 20 ms RMS callback tracks noise with a 9 dB margin, two-block attack and "
    "3 dB hysteresis. The floor starts at -50 dBFS to retain immediate speech. "
    "A 15 s sustained sound rebase handles steady noise. A negative threshold overrides "
    "automatic calibration. The console VU includes a silence countdown and stop reason.",
    "The result reports actual duration_seconds and appends capture_mode, stop_reason, "
    "silence_timeout_seconds and speech_seconds. A device backend without InputStream "
    "uses explicitly labeled fixed_fallback. Parametrizer's generic KV parser accepts "
    "the appended fields without a special parser rewrite.",
    "Migration 0200 updates prompt 74, TLAMATINI LISTENS, without changing its identity "
    "or ordering. Registry instructions omit duration unless the user requests one. "
    "FlowHypervisor tolerates the bounded gate wait and no longer calls it stuck. "
    "Existing workflows with positive durations deliberately keep fixed recording.",
]


VOICE_COMMAND_GUIDE = [
    "Migration 0201 appends prompts 121 and 122. views.PROMPT_CATEGORY_ORDER places "
    "voice_commands first. This is an explicit record-and-transcribe command, not an "
    "always-listening assistant or wake-word service.",
    "YOUR FIRST VOICE COMMAND (121) is a read-only rehearsal with Multi-Turn, Step-by-Step "
    "and Exec Report, without ACPX. SPEAK YOUR PROMPT (122) enables Multi-Turn, Exec Report "
    "and ACPX, with Step-by-Step off. The existing JS classifier derives these modes "
    "from prompt text. No frontend asset bump was required for this catalog change.",
    "The second card preserves the author's requested sentence verbatim. Whisperer "
    "records until the silence gate closes, then the transcript becomes the next prompt "
    "through the existing planner and tools. Omit duration unless the user specifies it.",
    "Display or read back the transcript verbatim before execution. Stop on empty or "
    "engine_unavailable results rather than inventing instructions. Irreversible or "
    "external actions require typed confirmation under the voice-command contract.",
    "Coverage spans prompt rule 18e, self-knowledge, FlowCreator, FlowHypervisor and "
    "agent-creation guidance. test_voice_commands_catalog.py checks ordering, sentence "
    "fidelity and classifier parity. The headed catalog harness checks browser cards "
    "and toggles, but does not prove real microphone recognition or spoken task execution.",
]


GREPPER_LINES_GUIDE = [
    "After the v1.51.9 tag, commit 4ae6da6 adds output_mode=lines to Grepper. "
    "It reads one text file without a regex. Existing content/files/count search "
    "modes remain available. Globber can select the file before the read.",
    "start_line/end_line are 1-based inclusive. Zero means first/last. The "
    "implementation clamps endpoints into the file and caps the slice at "
    "max_results (default 200). lines_returned, total_lines and truncated "
    "describe the returned slice. Directories and binary files are refused.",
    "line_numbers=true prefixes each displayed line with N:. With false, "
    "content_b64 carries base64 of the decoded slice encoded as UTF-8, retaining "
    "its line endings. Windows text-mode logging can rewrite the readable body. "
    "Use the encoded channel when constructing an Editor old_string.",
    "The shared reader checks UTF-8/16/32 BOMs before the NUL-byte binary rule, "
    "then uses UTF-8, cp1252 or Latin-1. content_b64 is not a byte-for-byte copy "
    "of a UTF-16/cp1252 source file. Editor itself reads/writes UTF-8, so this "
    "read capability does not make editing every supported source encoding safe.",
    "The wrapped chat_agent_grepper description and Parametrizer field map "
    "include the new contract. Success is listed, while missing paths give "
    "not_found. Self-knowledge and FlowCreator describe the read step. "
    "TLAMATINI_VERSION in self-knowledge is an offline fallback behind live metadata.",
    "Three new assets: test_grepper_lines_mode.py, grepper_lines_visible.py "
    "and grepper_login_probe.py. The commit reports 505 passing cases and a "
    "headed chat search/read demonstration. Those are historical claims, not "
    "results from this refresh. No test, browser harness or app was executed.",
]


OLLAMA_SAMPLER_GUIDE = [
    "Commits f6404a3 and cb30edf align prompt-only and retrieval defaults: "
    "ollama_repeat_penalty=1.2, ollama_repeat_last_n=256 and ollama_num_ctx=1048576. "
    "Explicit configuration overrides these factory fallbacks.",
    "Both chains in rag/factory.py pass all three values. mcp_agent.py forwards "
    "repeat_last_n when adapting to ChatOllama and includes it in the LLM-PARAMS "
    "banner. Previously, setting that config key could not reach this adapter.",
    "Commit f6404a3 reports eight trials per setting on a roughly 78k-token, "
    "117-bound-tool workload. For glm-5.3:cloud, failures fell from 7/8 at penalty "
    "1.9 to 1/8 at 1.2. The historical workload's bound-tool count differs from today's registry total.",
    "Commit cb30edf isolates lookback with penalty 1.2: glm failures were 5/8 at "
    "64 versus 2/8 at 256, with reported medians 154.0s and 26.3s. Kimi-k3 moved "
    "from 0/8 to 1/8 failures and 50.5s to 97.5s. The tradeoff is model-specific.",
    "The commit reports cloud requests exceeding a smaller num_ctx and a server "
    "rejection above 1,048,576 tokens for its tested model. This is recorded "
    "evidence, not a universal cloud limit. Local models use num_ctx for context "
    "allocation, so a 1M setting can demand substantial memory.",
    "README and Book now describe these changes. Performance and context results "
    "are attributed to the September 13 commit records, not new validation. "
    "No model requests or automated tests ran for this refresh. Lower failure "
    "counts do not guarantee every request completes.",
]


UNINSTALLER_SAFETY_GUIDE = [
    "Commit b07f9d5 adds a gate before confirmation or deletion. The Windows "
    "process scan checks executable paths inside the selected installation, "
    "with top-level executable-name fallback when an image path is unreadable.",
    "Detected processes appear with PID and evidence in a modal Retry/Exit "
    "dialog. Retry rescans and stays blocked while matches remain. Exit and the "
    "window close button leave the uninstaller. There is no continue-anyway button.",
    "The detector excludes this uninstaller and the same executable image. "
    "Detection errors allow progress by design, so this is best-effort protection. "
    "Close Tlamatini cleanly with Ctrl+C in its console before retrying.",
    "Top-level agents/ always survives. application/, applications/, "
    "content_generated/, context_files/ and Temp/ survive when they contain a "
    "file at any depth. Unreadable directories count as having content. Empty "
    "scaffolding may be removed; arbitrary folders outside this list are not protected.",
    "The final dialog names only the content directories actually preserved. "
    "Companion-agent discovery markers remain supported. The window body now "
    "builds independently of version-badge resolution, avoiding an empty card "
    "when the version is unavailable.",
    "Source assets: agent/test_uninstaller_mechanics.py and the Claude-skill "
    "harness uninstaller_visible.py. The commit records 49 mechanics cases and "
    "19/19 disk checks from a visible run with registry/Explorer actions stubbed. "
    "These are historical results. Neither runner nor the uninstaller ran here.",
]


WRAPPED_WAIT_GUIDE = [
    "Commit ac72b6c fixes chat_agent_run_wait in agent/tools.py. The previous loop "
    "reread the ChatAgentRun row, but no writer kept that row current during the "
    "child's execution. A finished child could therefore consume the full wait budget.",
    "Each poll now calls reconcile_chat_agent_run. That runtime helper checks process "
    "liveness, consults the process handle when available, persists the resulting "
    "status and stamps finishedAt when it first observes completion.",
    "The loop breaks only outside RUNNING_STATUSES, which includes created and "
    "running. It no longer treats a created status alone as completion. This applies "
    "to wrapped agents generally, including Whisperer after transcription.",
    "max_seconds defaults to 120 and is clamped to 1-600. Poll cadence defaults to "
    "2 seconds with a 1-second minimum. Expiry returns a status envelope and log "
    "excerpt without stopping the child. The caller may wait again or request stop.",
    "waited_seconds counts scheduled sleeps rather than exact wall-clock time. "
    "A full final poll sleep can exceed the nominal budget, plus reconciliation "
    "overhead. finishedAt remains an observation timestamp, not the OS exit instant.",
    "agent/test_chat_agent_run_wait.py adds five cases covering stale-row avoidance, "
    "process reconciliation, unfinished states, early return and timeout behavior. "
    "Source reviewed only in this refresh; the cases were not executed.",
]


OLLAMA_USAGE_GUIDE = [
    "ollama_credits.py is a standalone account-usage utility added by commit 36c0139. "
    "It does not add a workflow agent, a wrapped tool, a migration or a chat UI. "
    "The source uses only Python's standard library.",
    "It reads the operator's local .ollama/id_ed25519 OpenSSH key and constructs "
    "timestamped Ed25519 signatures. The key parser accepts an unencrypted "
    "ssh-ed25519 key. Keep the key private and review the utility before running it.",
    "The implemented account requests are GET /api/usage and POST /api/me at "
    "ollama.com, each with a 20-second timeout. This describes the checked-in "
    "implementation; endpoint availability and account responses were not exercised.",
    r"Manual use from the repository root: .\python\python.exe ollama_credits.py. "
    "Add --json for the returned account and usage payloads. The console report "
    "shows monthly use, model request counts and four-week activity. It pauses "
    "for Enter on an interactive terminal.",
    "The card hardcodes a $300 monthly denominator and infers reset day 3 by "
    "default. These assumptions may not match the account. --reset-day 0 hides "
    "the caption, and --json avoids the derived dollar card. Colored model "
    "segments reflect request shares, not measured per-model cost shares.",
    "This documentation refresh did not execute the utility or read account keys. "
    "Account email and usage can appear in its output. Redact reports before "
    "sharing. The script queries usage; it does not buy, grant or reset credits.",
]


SYSTEM_OVERVIEW = [
    "Tlamatini is a self-hosted AI developer assistant (cloud LLMs by default; the app and RAG run locally) built with Django, Django Channels, LangChain, LangGraph, FAISS/BM25 retrieval, and a large in-repository agent application.",
    "She combines a browser chat surface, a Retrieval-Augmented Generation stack, a Multi-Turn tool executor, MCP-backed context providers, wrapped chat-agent runtimes, and a visual Agentic Control Panel for workflow design.",
    "She is designed for development operations: codebase analysis, file and directory context, deterministic file discovery/search/editing, command execution, Python execution, screenshots, web/search helpers, notifications and attention routing, DevOps tools, authorized cyber-security assessment, local model operation, Windows packaging and uninstall registration, first-person self-knowledge about her own runtime, and embedded-firmware control for STM32, ESP32-class, Arduino-class, and ESPHome smart-home boards.",
]

AGENT_DIRECTORY_DISCLAIMER = [
    "Every agent in `Tlamatini/agent/agents/` is intentionally plain Python so the user can read, audit, edit, restrict, or disable its operating code. This transparency is a user-control mechanism, not a warranty that an agent is secure or suitable for a particular environment.",
    "Agents have no independent authority or jurisdiction. The user alone decides whether, where, how, and with which permissions an agent runs; enabling, configuring, modifying, chaining, or executing it places that execution under the user's control and jurisdiction.",
    "The user is responsible for code/config review, least-privilege secrets and credentials, authorized files and targets, browsers, shells, APIs, external MCPs, machines, hardware, downstream systems, supervision, and compliance with applicable law, policy, license, contract, and authorization.",
    "By running an agent, the user accepts responsibility for its actions and consequences. To the fullest extent permitted by applicable law, security breaches, data exposure or loss, unauthorized actions, credential leaks, unsafe automation, violations, compromise, device damage, financial loss, or other harm arising from use are the responsibility of the user who runs it.",
    "Tlamatini's orchestration, documentation, examples, and guardrails do not authorize third-party access and cannot replace the user's security review, permission controls, monitoring, or legal compliance.",
]

BLUE_HAT_SECURITY_GUIDE = [
    "The `security/` directory is an administrator-operated Windows defensive toolkit, not a new chat tool or database-backed workflow Agent row. Tlamatini helps collect and respond to signals only on systems the operator owns or is explicitly authorized to defend.",
    "The six shipped assets are `README.md`, `enable_tlamatini_v2.bat`, `tlamatini_whitelist_v2.ps1`, `run_defender.bat`, `tlamatini_defender.ps1`, and `automated_tests_of_security_assets.py`; runtime evidence is written under git-ignored `security_logs/`.",
    "Use the safe sequence validate -> record a Windows baseline -> enable -> restart -> run detect-only -> investigate -> arm only when justified. There is no bundled rollback script, so Defender, ASR, CFA, firewall, execution-policy, audit-policy, and Security-log state must be recorded before elevation.",
    "The visible non-destructive harness parses both PowerShell files, exercises the self-safe classifier, validates official ASR/audit GUIDs, watch timing, UAC path handling, launcher failure propagation, Shoter capture, and headed-browser proof. The audited run passed 40/40 checks, but it does not apply Windows policy or execute an armed sweep.",
    "Enablement keeps core Defender/firewall services running but deliberately adds the Tlamatini root and selected executables to Defender exclusions, allows `Tlamatini.exe` through Controlled Folder Access, moves six selected ASR rules to action 6 (Audit), sets current-user PowerShell to RemoteSigned, and creates broad outbound application rules.",
    "The ASR rules cover Office child processes, LSASS credential stealing, WMI event-subscription persistence, email/webmail executables, untrusted or unsigned USB processes, and PSExec/WMI child processes. The script uses Microsoft's published IDs and reads Defender's effective ID/action arrays back before reporting success.",
    "Audit setup uses stable subcategory GUIDs for Logon, Credential Validation, Process Creation, Sensitive Privilege Use, and User Account Management, and checks every `auditpol` exit code. Command-line event 4688 and PowerShell Script Block Logging improve evidence but can record sensitive arguments.",
    "The ten monitor families are Defender health, logons, established TCP/listeners, processes, scheduled tasks, services, registry persistence, recently changed critical files, ransomware/recovery tampering, and account/administrator-group events.",
    "Detect-only logs `WOULD BLOCK` and `WOULD KILL`. Default armed mode may add persistent inbound/outbound firewall blocks after repeated non-local failed logons and may force-stop known attacker-tool process-name matches; most other findings alert only.",
    "Dual-use names alert unless `-Aggressive` is supplied. Recognized Tlamatini paths are protected from auto-kill, but that is only a path-prefix check, not signature or provenance proof; malicious content inside an excluded/self path can inherit a blind spot.",
    "Watch mode is a foreground loop with `-IntervalSeconds` constrained to 5..86400. It is not a service or scheduled task, and `run_defender.bat` deliberately selects one default armed sweep, so baseline runs should invoke the PowerShell script directly with `-DetectOnly`.",
    "`alerts.log` and `monitor.log` append sensitive usernames, IP addresses, paths, command lines, task/registry details, and response records without built-in rotation, deduplication, automatic unblock, or SIEM forwarding. Treat every severity as triage priority, not certainty.",
    "The batch launchers preserve paths containing spaces through UAC and propagate PowerShell failures. `build.py` ships the security source while excluding logs; self-modify snapshots likewise prune `security_logs/` so screenshots and host telemetry are not published.",
]

WHAT_IT_DOES = [
    "Answers codebase questions with file/directory context and reads PDFs in the canvas. Use as context indexes the whole PDF, with optional Image-Interpreter analysis.",
    "Uses hybrid retrieval to extract metadata, split content, rank source chunks, and respect context budgets.",
    "Can discover files by glob pattern, search their contents by regex through Grepper's BOM-first UTF-8/16/32 and cp1252/Latin-1 decoder while skipping genuine binary data, and make surgical in-place replacements through Editor.",
    "Can connect to external MCP servers declared in `external_mcps.json`, expose their remote tools to Multi-Turn under the `ext__<server>__<tool>` naming convention, and supervise those connections through ten status / reconnect / doctor / runtime / import / list / call / activate / wait helpers.",
    "Ships official Memory and Sequential-Thinking MCP catalog defaults in every install, both inactive, and can provision a private per-user Node/npm/npx/pnpm or uv/uvx runtime without admin access or system-PATH changes.",
    "Gives operators GUI-first database maintenance through the new DB dropdown for backup and staged database replacement.",
    "Makes those SQLite operations WAL-safe: online backup reads through committed WAL pages, creates a self-contained destination, verifies it with `quick_check`, and keeps sidecars attached to the database they belong to.",
    "Can measure this machine's Internet connection through NetSpeed-Calculator, reporting throughput with confidence intervals, latency, jitter, loss, bufferbloat grade, and provider heterogeneity instead of trusting one speed-test endpoint.",
    "Lets operators manage provider secrets from the browser through the Config -> Access Keys Wizard instead of hand-editing `config.json`.",
    "Can drive Blender through the Blenderer agent, using the official Blender MCP add-on socket to inspect scenes, mutate objects and materials, run raw code, and automate renders from chat or the workflow canvas.",
    "Can pause before every state-changing Multi-Turn execution and ask the operator to approve or deny that exact step through the Ask Execs checkbox.",
    "Can raise a Windows attention signal when the browser needs the operator: Ask Execs prompts and Notifier events can flash Tlamatini’s own taskbar presence and leave an uppercase banner in `tlamatini.log`.",
    "Registers packaged installs in Windows `Installed apps` / `Programs and Features` with a real uninstall entry, so the release behaves like a normal installed application instead of only a shortcut bundle.",
    "Can update packaged installs in place through About -> Check for updates: she checks the latest GitHub release, stages the download, swaps locked files externally, and preserves operator state such as `config.json`, the database, and content.",
    "Hardens generated files: File-Creator’s bulk-write path now preserves long content byte-complete even when it contains heavy quoting or semicolon-rich source text.",
    "Warns GPU-host operators before a directory-context load is likely to saturate VRAM and degrade embedding throughput.",
    "Exposes a coherent versioning surface across builds, runtime UI, logs, and an open health-check endpoint.",
    "Carries a first-person self-knowledge map so she can answer more accurately about her own architecture, ports, runtime modes, pages, and capabilities.",
    "Can command Kali Linux offensive-security tooling through MCP-Kali-Server for authorized recon, enumeration, web scanning, and assessment workflows.",
    "Can run local authorized nmap reconnaissance through Nmapper, a use-only bridge that resolves a user-installed nmap, defaults to unprivileged TCP connect scanning, refuses unsafe/missing prerequisites gracefully, and never bundles or redistributes nmap.",
    "Can support operator-controlled Windows Blue-hat monitoring through the host-side `security/` toolkit, with persistent enablement tradeoffs, detect-only baselining, ten signal families, bounded armed response, and explicit evidence/privacy limits.",
    "Can diagnose an external MCP before the first live connection through the MCP Doctor agent and wrapped `chat_agent_mcp_doctor` tool, checking transport, runtime requirements, PATH availability, placeholder secrets, and the next operator step.",
    "Can scaffold, author, build, flash, reset, and observe STM32 firmware through STM32er: the template-MCP path remains for STM32F407, while released `v1.42.0` adds a PlatformIO path for supported boards from Blue Pill/F1 through mainstream F/G/L/H7/U5/WB families, with fail-safe preflight before hardware mutation.",
    "Can scaffold, author, build, upload, and monitor ESP32-class firmware through ESP32er and PlatformIO Core, with zero-config bootstrap and a serial-aware preflight before hardware mutation.",
    "Can author YAML-based smart-home firmware through ESPHomer and ESPHome, including zero-config bootstrap, device-config generation, validation, compile, USB/OTA upload, and bounded log observation for ESP32 / ESP8266 / RP2040 / BK72xx devices.",
    "Can play media on the operator's machine: an audio file to the speakers through AudioPlayer (soundfile + sounddevice — volume in percent and a time-played budget that truncates a longer file or loops a shorter one), or a video file with audio on a chosen display through VideoPlayer (ffpyplayer, whose wheel bundles ffmpeg + SDL, plus an OpenCV window — display, volume, the same truncate/loop time budget, window size, and fullscreen); both are observational/output and ship on the canvas and as wrapped chat tools.",
    "Can SPEAK and LISTEN: Talker (text-to-speech) renders input_text to a 24 kHz WAV through an Ollama neural TTS model (selected in Config > Models > Speech) and is female-voice-only by design, while Whisperer (speech-to-text) records the microphone itself or transcribes a file via faster-whisper locally (NVIDIA-GPU auto-detect with an always-present CPU fallback) or a cloud Whisper API; both light a zero-latency console REC indicator driven by the live audio stream and are observational/output, on the canvas and as wrapped chat tools.",
    "Can manage real desktop windows by title: focus them, tile them, resize them, list them, and close them deterministically through Win32 calls.",
    "Can search with Googler through four plain-HTTP server-rendered routes first and, if empty, visible installed Chrome/bundled Chromium across seven browser routes, using bounded retries, manual query operators or a visual/pool structured dork builder, and URL-only output for indexed-file workflows.",
    "Can drive a real Playwright browser through scripted interactive steps for logins, forms, assertions, downloads, extraction, and end-to-end UI checks.",
    "Can drive a live Unreal Engine 5 editor through the Unreal MCP plugin, from either Multi-Turn chat or the visual workflow canvas.",
    "Actively reaps orphaned Windows console-host and pool-child processes so long Multi-Turn or ACPX sessions do not leave misleading Tlamatini-icon ghosts in Task Manager.",
    "Can autonomously kill only genuinely hung shell-wrapper subtrees through a boot-time command watchdog that measures CPU and I/O progress instead of guessing from elapsed time.",
    "Runs checked Multi-Turn requests through request-scoped planning, capability selection, tool calls, observations, monitoring, and final synthesis.",
    "Can optionally inspect and modify her own bundled source tree in self-modify builds after verifying that `TlamatiniSourceCode/` is actually present.",
    "Launches wrapped copies of selected workflow agents in isolated runtime folders without mutating templates.",
    "Lets users design, validate, save, pause, resume, and stop visual workflows through the Agentic Control Panel.",
    "Turns successful Multi-Turn tool executions into starter `.flw` workflows that can be inspected and validated in ACP.",
    "Packages the project into a distributable Windows release with installer and uninstaller tooling.",
]

HOW_IT_WORKS = [
    "Browser UI sends chat and workflow requests through Django views and Channels WebSockets.",
    "RAG chains load selected file/directory context, retrieve relevant chunks, and build answer prompts. PDF preparation supplies a complete private text/image index through a user-bound signed token; normal retrieval and model limits still apply.",
    "DB-menu actions validate directories or SQLite files in the browser, then call Django views that use `sqlite_copy.consistent_copy()` to read through WAL, create a self-contained checked destination, and either back it up or stage it under `DB/ToLoad/db.sqlite3`.",
    "Config -> Access Keys Wizard reads masked provider-key status from the backend and persists only the edited secrets, keeping the browser flow honest without dumping live values back to the page.",
    "The file-navigation and file-edit trio sits above raw shell execution: Globber enumerates matching files, Grepper decodes BOM-marked UTF-8/16/32 before cp1252/Latin-1 fallbacks while pruning genuine binary/noisy trees, and Editor performs byte-exact in-place replacements without rewriting an entire file.",
    "External MCP connectivity is catalog-driven: `external_mcps.json` stores preserved Claude-style `mcpServers` state, `external_mcp_defaults.py` seeds inactive Memory/Sequential-Thinking defaults with edit/tombstone semantics, `runtime_provisioner.py` resolves or privately provisions npx/uvx managers, and `external_mcp_manager.py` negotiates stdio / streamable-HTTP / SSE / WebSocket before healthy remote tools become `ext__<server>__<tool>` planner entries.",
    "The `adding-external-mcp` skill applies that machinery in one guarded sequence: classify transport, import secret-separated configuration, diagnose, activate only on intent, wait for healthy tools, inspect status/list output, then call.",
    "The MCP Doctor path is intentionally safer than a live connect: it reads the configured server entry, validates transport shape, runtime commands, PATH/toolchain presence, placeholder secrets, and docs/source URLs, then returns an onboarding diagnosis without consuming the server's real tool surface.",
    "Blenderer opens the official Blender MCP add-on TCP socket (default `localhost:9876`), sends one action payload or raw code-execution request, and returns the structured result through the same wrapped-tool / canvas contract used by the rest of the agent catalog.",
    "When Ask Execs is enabled, the synchronous Multi-Turn executor stops before each state-changing tool call, emits an `exec_permission_request`, and waits on `ExecPermissionBroker` until the browser sends Proceed or Deny.",
    "When the browser surfaces an Ask Execs prompt or a Notifier event, JavaScript can POST to `/agent/flash_window/`; the backend then best-effort flashes the `Tlamatini.exe` console/taskbar window through `window_flash.py` and prints an uppercase attention banner for the log.",
    "Installer-time registration writes a per-user HKCU Add/Remove Programs entry pointing at `Uninstaller.exe`, and frozen startup re-checks that entry through `windows_app_registration.self_heal_for_frozen()` so older installs retroactively appear in Windows' uninstall surfaces.",
    "In-app self-update uses Django views plus `self_update.py` to check GitHub releases, download and stage the selected package, then hand off the locked-file swap to `apply_update.ps1`; the preserve contract retains operator state and `Uninstaller.exe` before relaunch.",
    "Frozen-build hardening now verifies media dependencies during packaging too: `build.py` embeds numpy and OpenCV in both shipped Python runtimes and refuses to produce a release if those imports are missing.",
    "Before a heavy directory embedding run on supported NVIDIA hosts, a fail-open pre-flight guard can estimate VRAM pressure and surface a non-blocking warning in chat.",
    "Version resolution now flows through git tags, a runtime resolver module, generated build artefacts, and an open `/agent/version/` endpoint.",
    "A first-person self-knowledge file (`Tlamatini.md`) is injected into prompt construction for all chains, but loaded user context still outranks that self-reference when the request is a generic summary of the provided project.",
    "When Multi-Turn is enabled, the global planner selects context and tool stages before the executor binds only the relevant tools, including wrapped deterministic agents such as De-Compresser.",
    "Optional self-modify builds bundle `TlamatiniSourceCode/`; `copy_source_assets.py` generates that snapshot with rebuild instructions and redacted secrets, and prompt rules require her to verify that directory exists before claiming she can inspect or change her own code.",
    "The Kalier path talks directly to the MCP-Kali-Server Flask API over HTTP with Python-stdlib `urllib`, auto-seeding the default box from `kali_server_url` in Config -> URLs before any one-off per-call override is applied, and captures one atomic `INI_SECTION_KALIER` block per run.",
    "The Nmapper path resolves a user-installed `nmap` from explicit config, PATH, Program Files, or `%LOCALAPPDATA%`, constructs one safe scan action, captures XML plus normal output, parses hosts/open ports with the standard library, and emits one atomic `INI_SECTION_NMAPPER` block for Parametrizer/Forker routing.",
    "The NetSpeed-Calculator path opens parallel keyless-provider streams, drops the slow-start warmup, samples byte derivatives, rejects outliers, computes Student-t intervals, and pools provider estimates with inverse-variance or DerSimonian-Laird random effects; `validate` and `providers` are read-only, while throughput actions are metered tier-D work.",
    "The STM32er path spawns the STM32 Template Project MCP stdio server, performs the MCP initialize handshake, runs exactly one requested tool or composite action, and emits one atomic `INI_SECTION_STM32ER` block with the result, project directory, and stage metadata.",
    "Before any flash-capable STM32er action, a critical-mission preflight validates the arm-none-eabi toolchain, STM32CubeIDE, programmer path, ST-LINK presence, and STM32F-family match; compile-only steps can run boardless, but unsafe hardware mutations are refused fail-safe.",
    "The ESP32er path resolves or bootstraps PlatformIO Core, invokes `pio` subcommands directly with Python-stdlib process control, validates project and serial-port readiness, and emits one atomic `INI_SECTION_ESP32ER` block with stage, project, port, and stdout/stderr payloads.",
    "The ESPHomer path resolves or bootstraps the `esphome` CLI, can generate a minimal valid YAML device config headlessly, validates either a serial board or OTA host before upload/log actions, and emits one atomic `INI_SECTION_ESPHOMER` block with action, config path, stage, and captured CLI output.",
    "The Windower path uses Win32 APIs plus the cross-process `AttachThreadInput` focus-transfer dance to locate windows by title and apply one lifecycle action while still returning structured geometry/state fields.",
    "The Playwrighter path loads a declarative step list, drives Playwright against Chromium/Firefox/WebKit, and emits one atomic `INI_SECTION_PLAYWRIGHTER` block with status, assertions, extracted values, and the final URL.",
    "The Unrealer path opens a TCP socket to the Unreal MCP plugin, sends one `{\"type\": command, \"params\": {...}}` payload, captures the JSON reply, and emits one `INI_SECTION_UNREALER` block for downstream logic.",
    "A boot-time command watchdog samples CPU time and I/O bytes across shell-interpreter subtrees and reaps only the ones that stay idle past the grace-and-streak window, protecting healthy long-running commands while rescuing wedged prompt waits.",
    "After spawn-capable tool calls and again after the final answer, the orphan reaper can sweep dead descendants, orphaned `conhost.exe` companions, and stale pool-linked processes without ever raising into the chat path.",
    "Tool calls execute in the backend, append observations, and may create wrapped runtime copies under `agent/agents/pools/_chat_runs_/`.",
    "On the next full start-up, `manage.py` archives the previous database with its WAL/SHM/journal sidecars under `DB/Older/<timestamp>/`, clears stale destination sidecars, and only then promotes the verified staged database before Django imports.",
    "ACP flows deploy session-scoped pool instances, wire config values, validate NxN graph rules, and execute through Starter-driven flow semantics.",
    "Build scripts collect static assets, bundle Django/Python resources, add agent templates, and assemble `pkg.zip`, `Uninstaller.exe`, and `dist/Tlamatini_Release/`; `build.py --self-modify` additionally injects the generated source snapshot, while the explicit private builder can synchronize same-machine contacts into gitignored private staging without exposing them in public output.",
]

HOW_TO_USE = [
    "Run from source: create a virtual environment, install requirements, migrate, create a superuser, collect static files, and start Django.",
    "Open `/agent/` for chat. Load file/directory context for code questions. For PDFs, use Open in the canvas, then Use as context and Continue. Process images is off by default and adds configured vision calls only when selected.",
    "Keep Multi-Turn unchecked for direct Q&A; enable Multi-Turn for tasks that need tools, wrapped agents, monitoring, or workflow seeding.",
    "Use `chat_agent_globber` to find files, `chat_agent_grepper` to search or read a range with output_mode=lines, and `chat_agent_editor` for an exact in-place change. Use content_b64 for line-ending-safe text transport and observe Editor's UTF-8 scope.",
    "To use the External MCP capability, open `External -> MCPs`, register or import a server into `external_mcps.json`, choose the transport/runtime fields, and let the dialog connect it before expecting its `ext__<server>__<tool>` tools to appear in Multi-Turn.",
    "When you are onboarding or debugging an external MCP, call `chat_agent_mcp_doctor` first or use the MCP Doctor workflow node; it can tell you whether the issue is transport selection, a missing runtime on PATH, placeholder secrets, or a bad endpoint before you spend time on a live connect attempt.",
    "If you want a guided external-MCP onboarding flow, use the Step-by-Step mode in the External MCP dialog so each required field is introduced progressively instead of dumping the whole connection contract at once.",
    "For a deterministic MCP setup, invoke the `adding-external-mcp` skill and follow classify -> import -> doctor -> activate -> wait -> status/list -> call; do not treat a saved catalog row as a connected server.",
    "Use Config -> Access Keys Wizard when you need to wire or update provider credentials without editing `config.json` manually.",
    "Use About -> Check for updates on packaged installs when you want Tlamatini to fetch and stage the latest release without manually replacing the install folder.",
    "Tick `Ask Execs` when you want human approval before each state-changing Multi-Turn step; it is disabled until Multi-Turn is on, and a single Deny stops the whole chain with an explicit red interruption banner.",
    "When you are using a packaged install on Windows 10 or Windows 11, uninstall it through Settings -> Apps -> Installed apps or the legacy Programs and Features entry, not by manually deleting the folder.",
    "If an Ask Execs approval dialog or a Notifier event needs you while the browser is buried, watch for Tlamatini’s taskbar-attention flash and the matching uppercase banner in `tlamatini.log`.",
    "If you want her to inspect or modify herself, verify that `TlamatiniSourceCode/` exists in the current build first; self-modify is optional and absent builds must be treated honestly as read-only about their own code tree.",
    "For authorized Kali Linux assessments, run MCP-Kali-Server on the Kali box, set `Config -> URLs -> Kali server (Kalier)` once, and then call `chat_agent_kalier` from Multi-Turn with the desired `action` and `target` without repeating the box URL each turn.",
    "For local nmap reconnaissance, install nmap yourself or call `chat_agent_nmapper` with `action='install'` to launch the official free installer; then use `quick`, `full`, `top_ports`, `version`, `scripts`, `host_discovery`, `udp`, `custom`, or `validate` only against hosts you own or are explicitly authorized to test.",
    "For Internet measurement, call `chat_agent_netspeed_calculator` once with `latency` or `validate` for low-bandwidth diagnosis, or explicitly approve `full` / `download` / `upload` knowing a full run commonly transfers 100-200 MB; report the confidence interval and provider disagreement, not only one Mbps number.",
    "For STM32 firmware work, install STM32CubeIDE, leave `Config -> URLs -> STM32 MCP server script` blank for zero-config bootstrap, and then call `chat_agent_stm32er` from Multi-Turn with one `action` at a time such as `validate`, `create_project`, `write_source`, `build`, `build_and_flash`, `serial_session`, or `live_monitor`.",
    "For ESP32 firmware work, leave `Config -> URLs -> pio_executable` blank for zero-config PlatformIO bootstrap, then call `chat_agent_esp32er` from Multi-Turn with actions like `bootstrap`, `validate`, `create_project`, `write_source`, `build`, `upload`, `build_and_upload`, `monitor`, or `monitor_session`.",
    "For ESPHome smart-home firmware work, leave `Config -> URLs -> esphome_executable` blank for zero-config bootstrap, then call `chat_agent_esphomer` from Multi-Turn with actions like `bootstrap`, `validate`, `new_config`, `config`, `compile`, `upload`, `logs`, or the one-shot `scaffold_compile_upload` flow.",
    "For desktop-window control, call `chat_agent_windower` from Multi-Turn to focus, tile, resize, list, or close a window by title, or model the same action in ACP with the Windower node.",
    "For interactive web automation, call `chat_agent_playwrighter` from Multi-Turn with a `steps_json` script, or author the same step list visually with the Playwrighter node on the canvas.",
    "For Blender work, enable the official Blender MCP add-on in Blender, make sure its TCP listener is reachable (default `localhost:9876`), then call `chat_agent_blenderer` from Multi-Turn or use the Blenderer node on the canvas.",
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
        "Specialized agents now stretch the platform in different directions: Globber/Grepper/Editor cover deterministic file discovery, regex search, and surgical in-place edits; Video-Analyzer closes hardware-in-the-loop video verdicts; MCP Doctor performs safe external-MCP onboarding diagnosis; ACPXer drives external coding-agent CLIs; Kalier drives a remote or tunneled Kali Linux tool server; Nmapper drives local use-only nmap scans for authorized targets; STM32er drives a zero-config STM32 firmware MCP bridge; ESP32er drives PlatformIO directly; ESPHomer drives ESPHome directly for YAML-authored smart-home devices; Blenderer drives a live Blender editor over the official MCP add-on socket; Unrealer drives a live UE5 editor; TeleTlamatini bridges full Tlamatini conversations into Telegram; Telegrammer uses official Telegram surfaces; Whatsapper defaults to Meta's official business Cloud API but can explicitly use an unofficial personal-account Web route; and Instant Messaging Doctor diagnoses the official messaging credentials and policy without silently switching providers.",
]

ACPX_SKILLS_GUIDE = [
    "The new `ACPX-Skills` navbar menu gives operators four direct actions over the skill catalog: Browse Skills, Configure Skills, Diagnostics, and Reload Registry.",
    "`Configure Skills` flips `Skill.enabled` exactly the way MCPs and Tools are toggled, so disabled skills disappear from `list_skills` and reject `invoke_skill` with `SKILL_DISABLED` instead of silently half-working.",
    "The diagnostics view cross-checks skill dependencies against disabled tools, disabled MCPs, missing ACPX agents, and orphan database rows whose SKILL.md disappeared from disk.",
]

def operator_surface_counts_guide(context: dict) -> list[str]:
    return [
        f"The live operator surface now stands at {context['workflow_agent_count']} workflow agents, {context['total_multi_turn_tools']} Multi-Turn tools, {context['acpx_tool_count']} ACPX tools, and {context['skills_count']} skills.",
        f"Source inspection confirms the total: {context['core_python_tool_count']} core Python tools + {context['wrapped_chat_agent_count']} wrapped chat-agent tools + {context['acpx_tool_count']} ACPX/Skill tools + {context['external_mcp_supervisor_count']} External-MCP supervisors = {context['total_multi_turn_tools']} built-in Multi-Turn tools; healthy active servers add dynamic `ext__*` remotes separately.",
        "The count growth over older public badges comes from stacked waves: the deterministic file trio, ESPHomer, MCP Doctor, Zavuerer, Video-Analyzer, Nmapper, NetSpeed-Calculator, and the `adding-external-mcp` skill.",
        "The workflow-agent and wrapped-tool totals are validated from the live tree even when some handbook badges or older prose lines lag behind the newest release wave, so the dossier stays tied to source truth instead of stale summaries.",
        "This matters operationally because the planner never binds everything at once: the documented default `max_selected_tools` cap stays at 20, so breadth of capability does not mean uncontrolled tool sprawl per turn.",
    ]

CURRENT_RELEASE_GUIDE = [
    release_identity(),
    "Commit `c8cf369` makes console output non-blocking. `manage.py::_ConsoleWriter` drains a bounded 10,000-chunk queue on one daemon thread, while `_TeeStream` writes `tlamatini.log` first on the caller thread. Frozen builds ship `console_quick_edit: false`; source runs leave the developer's terminal mode untouched. Ctrl+C is forced on, verified after the mode change, and the original mode is restored if that bit does not survive. The 600-line `agent/test_console_shield.py` contains 28 focused tests.",
    "The same commit adds the 92-line `welcome_enter_default.js`: the existing Go to Chat link receives focus after login, while a guarded document fallback handles plain Enter only when no button, link, input, or editable element already owns it. Modifier chords, IME composition, claimed events, missing links, and failed focus all fail open. The earlier `00ecdc9` shim still centralizes correct `.exe`, Python, `.cmd`, and `.bat` startup across ACPX and runtime provisioning.",
    "The shared v1.51.2/v1.51.3 tag commit adds `agent/acpx/child_health.py`, live readiness probes, named non-delivery verdicts, and transport overrides. PDFer's upgrade and v1.51.1 program/snippet collision repair remain carried. The repository facts section derives current agent, tool, frontend and migration counts directly from source.",
    "`agent/agent_verdict.py` now owns the CLOSED `KNOWN_STATUSES` union of five disjoint sets: `DIAGNOSTIC_COMPLETED_STATUSES`, `WORK_COMPLETED_STATUSES`, `WORK_DEGRADED_STATUSES`, `WORK_NOT_DONE_STATUSES`, and `AGENT_ERROR_STATUSES`. The first two are green; the last three are red. R8b remains fail-open for unknown runtime input, while `agent/test_status_vocabulary.py` rejects unknown literals before release.",
    "Grepper detects BOM-marked UTF-8/16/32 before cp1252/Latin-1 fallbacks and before the NUL-byte binary test. The self-report outranks process exit code; Kuberneter emits `returncode`, `success`, and semantic `status: ok|failed`. Source-derived tests stop status, supervisor, prompt, and catalog drift.",
    "`agent/sqlite_copy.py` routes Backup DB, Set DB, and pre-Django hot-swap through SQLite's online backup API. Destinations become self-contained DELETE-journal files, must pass `PRAGMA quick_check`, and keep or clear WAL/SHM/journal sidecars in the correct order before promotion.",
    "Frontend dialogs now share one visual language through `dialog_theme.css` and one fail-open dismissal contract through `dialog_policy.js`: an outside click never dismisses, while Escape finds the topmost open dialog and invokes that dialog's own X/Cancel path so permission denials, confirmation-false results, and scroll-lock cleanup remain intact. A sealed downloading updater is the single exception and refuses Escape/reload shortcuts. `tlmAlert` / `tlmConfirm` replace the remaining native pop-ups inside Contacts and External MCP dialogs, while `release_notes_renderer.js` safely renders update notes.",
    "The `v1.48.16` build proof names fail-open imports explicitly with hidden-import flags, opens the PyInstaller archive it just produced, and aborts if any of seven required `agent.*` modules is genuinely absent. Unreadable archive formats warn rather than fabricate failure, but a readable archive missing a required module cannot ship.",
    "Long operations use `LONG_OPERATION_DISABLED_MENU_BUTTONS` as the single Open/Save/Context/MCPs/Skills/External/Config/DB/Reconnect lock list; disable/restore paths preserve `data-bs-toggle`, while only Check for Updates and Configure Agents receive the targeted extra lock. Application logging now attributes output by user, request, stream, and source line.",
    "Shoter captures the whole desktop by default, supports an exact basename, and emits physical capture bounds, analyzed-image dimensions, monitor geometry and capture time. Unproven geometry is marked unknown. Mouser maps explicit physical/window/screenshot coordinates and rejects ambiguous targets; Keyboarder binds checked Unicode SendInput to a window and stops on focus loss. Input delivery is distinct from verified application success.",
    "FlowCreator selects from all 89 installed agents, then uses selected guide sections and current configuration/connection contracts. It validates references, branch slots, singleton wiring and Parametrizer mappings, supports bounded repair, and reports failure if the .flw cannot be written. The generated catalog exports field types rather than local configuration values, and deployment refreshes runtime knowledge.",
    "Parametrizer derives parser membership from 53 structured-output contracts, preserves CRLF/empty fields, checks numeric/Boolean conversions, requires all mappings before writing/launching and blocks automatic replay of interrupted desktop input. FlowHypervisor separates execution branches from kill/observation dependencies and includes current timing and persistent desktop receipts. GUI-Manager remains design only. See docs/desktop-input-and-flow-contracts.md and docs/agent-coverage.md for verification scope and maintenance.",
    "PDFer now localizes its own footer/fallback-title labels through `document_language` and forces optional Ollama polish to preserve the source language. External-MCP catalog refinements pin active services first, keep them alphabetized, add active/catalog headings, and preserve focus after rerendering.",
    "The binary-content guard, PDFer, LaTeXer repair ladder, FlowCreator, prompt grammar, recon free-run, STM32er PlatformIO/camera demos, and External-MCP structured-result delivery remain carried behavior rather than disappearing behind the latest changes.",
    "The private External-MCP runtime, inactive Memory/Sequential-Thinking defaults, tombstones, persistent Memory state, secret-separated catalogs, nested-diagram restoration, Mover/Deleter placement guard, and updater preservation remain carried from the v1.48.14-v1.48.17 lineage.",
    "The categorized prompt catalog, per-user Hard Cancel epochs, path-native screenshot paste/drop, configurable port, FlowPills discovery, Unreal scaffold, self-healing, robotic loop, firmware/media agents, External MCPs, ACPX skills, and deterministic file tools remain part of the complete product rather than being reduced to a latest-changes summary.",
    "README.md and BookOfTlamatini.md retain the complete MIT-licensed installation, Ollama setup, architecture, everyday-use, agent, and responsibility narrative. The plain-Python agent disclaimer is explicit: transparency enables user control but is not a security warranty, and authorization, review, permissions, and consequences remain the operator's responsibility.",
    release_identity(),
    "The inventory is rebuilt from Git-tracked plus Git-unignored files without reproducing credentials, endpoints, private values, or machine-specific configuration. This generation pass does not stage, commit, or push anything.",
    "The regenerated PDF/PPTX preserve the whole system, architecture, installation/use guidance, recent Git history, complete file tree, effective-line inventory, and validation evidence; target behavior and tagged historical predecessors are described separately.",
]


NETSPEED_GUIDE = [
    "Actions are `full`, `download`, `upload`, `latency`, `validate`, and `providers`. `validate` checks reachability and `providers` lists the catalog; neither runs a throughput transfer.",
    "Each throughput direction uses parallel TCP flows, discards the configured warmup/slow-start interval, and samples d(bytes)/dt so the excluded ramp cannot contaminate the estimate.",
    "Per-provider samples are cleaned with Tukey-IQR or MAD rejection, summarized with a trimmed mean, and assigned a small-sample Student-t confidence interval.",
    "Cross-provider fusion starts with inverse-variance weighting and switches to DerSimonian-Laird random effects when Cochran's Q shows genuine disagreement; I-squared quantifies heterogeneity.",
    "Bufferbloat is the RTT increase while the link is saturated, graded A+ through F. A fast idle Mbps number does not excuse poor latency under load.",
    "A zero-byte transfer records and reports its endpoint/network cause instead of masquerading as a measured 0.00 Mbps connection.",
    "Full runs commonly transfer 100-200 MB and deliberately saturate the link. The agent is Ask-Execs tier D; run once with explicit operator awareness and do not repeat only to seek a prettier result.",
    "The network/measurement stack uses Python's standard library; existing PyYAML reads `config.yaml`. JSON evidence lands under `<app>/Temp/NetSpeedCalculator`, and `INI_SECTION_NETSPEED_CALCULATOR` feeds Parametrizer/Forker and Exec Report.",
]

GOOGLER_DORK_GUIDE = [
    "The visual/pool Googler compiles structured fields into valid Google syntax: operator colons have no following space, exact phrases are double-quoted, alternatives use uppercase OR inside parentheses, and exclusions use `-term` without a gap.",
    "Presets are `book`, `book_public`, `paper`, `manual`, `docs`, `slides`, `sheets`, and `directory`. A preset fills only empty fields, so an explicit user value always wins.",
    "File aliases expand `ebook`, `book`, `docs`, `slides`, `sheets`, `text`, `code`, and `data`; multiple file types or sites become grouped OR clauses, while excluded sites become `-site:` filters.",
    "The remaining fields cover exact/author phrases; title, URL, text, and anchor operators; alternatives; AROUND proximity; numeric ranges; before/after dates; related/cache/define/source discovery; and term exclusions.",
    "For PDF, EPUB, document, slide, sheet, code, or data hunts, `content_mode: links_only` is the correct success path: Googler returns URL/title records without trying to extract text from a binary response.",
    "A typical downstream flow is Googler (`links_only`) -> Parametrizer -> Apirer (authorized download) -> File-Extractor or File-Interpreter -> Summarizer. Crawler remains appropriate when the target is an already-known web page.",
    "The direct Multi-Turn `googler` tool accepts equivalent hand-written operators inside `query`; the structured fields and presets belong to the visual/pool agent and must not be advertised as direct-tool parameters.",
    "Googler locates publicly indexed URLs only and does not bypass access controls. Indexing is not permission: copyright, licensing, authorization, downloading, and use remain the operator's responsibility.",
]

GOOGLER_RESILIENCE_GUIDE = [
    "A measured failure drove the redesign: bundled headless Chromium returned zero results even for a plain control query, and the old single DuckDuckGo fallback returned an error page, while the same dork in visible installed Chrome returned real EPUB URLs.",
    "Tier 0 uses plain `urllib` before any browser: DuckDuckGo HTML, Bing, DuckDuckGo Lite, and Mojeek provide server-rendered pages without browser fingerprints or CSS-selector dependence. v1.50.3 unescapes HTML entities, decodes Bing `ck/a` Base64URL targets, and filters Mojeek's own promotional links before the first non-empty result set wins.",
    "If Tier 0 is empty, Tier 1 defaults to visible installed Chrome, falls back to bundled Chromium, and walks seven direct-result browser routes: DuckDuckGo HTML/Lite, Mojeek, Bing, Google, Brave, Startpage. Headless remains opt-in and more refusal-prone.",
    "Each browser route receives `attempts_per_engine` bounded attempts with polite jittered backoff. The log names the route that actually answered instead of implying every result came from Google.",
    "`engines` can pin a browser route such as `[google]` and deliberately skips Tier 0. Empty selection enables both documented tiers; tolerant booleans keep wrapped string `false` from silently becoming true.",
    "`site:` and `filetype:` work broadly, but `before:`, `after:`, `AROUND()`, and numeric-range semantics are Google-specific. A fallback engine may return broader candidates, so exact full-vocabulary work should pin Google and reports must preserve the answering-engine truth.",
    "The 73-test deterministic suite covers query compilation, config defaults, HTTP-before-browser order, seven-route browser order, retry/fallback stopping, pinned-engine Tier-0 bypass, tolerant booleans, and redirect unwrapping. The optional headed dork-hunt harness stores public/open-source proof under Tlamatini `Temp`; the v1.50.3 tag records the first paired-Tlamatinis Googler improvement phase.",
]

WAL_SAFE_DB_GUIDE = [
    "SQLite WAL mode can hold committed pages in `db.sqlite3-wal`, so copying only the main file can silently produce an old backup while claiming success.",
    "`sqlite_copy.consistent_copy()` uses SQLite's online backup API to read through WAL, converts the destination to DELETE journal mode, and requires `PRAGMA quick_check` before success.",
    "Backup DB writes that verified self-contained copy to the selected directory. Set DB writes the same safe form into `DB/ToLoad/db.sqlite3` without touching Django's open live connection.",
    "Before Django imports, `manage.py::_apply_pending_db_swap()` archives the outgoing main database plus WAL/SHM/journal sidecars under `DB/Older/<timestamp>/`.",
    "The swap removes stale sidecars beside the destination before promotion, preventing SQLite from replaying pages belonging to the previous database over the selected replacement.",
    "Database copy truth is fail-safe: unreadable, inconsistent, or unchecked output is failure. The previous live database remains available if promotion cannot finish safely.",
]

MCP_RESEARCH_PRIVACY_GUIDE = [
    "The External MCP Adder skill's eight-step lifecycle is transport classification, secret-separated configuration, import, Doctor, intentional activation, healthy wait, status/list inspection, and remote call.",
    "Memory and Sequential Thinking remain inactive shipped defaults; deletion tombstones and persistent per-user state are respected, and at most five catalog servers are active at once.",
    "Deep Internet Research is append-only prompt 118 (`getting_started`, `sort_rank=100`). It requests Multi-Turn plus Exec Report for a long, link-rich search and may use authorized MCPs/agents without making them hidden requirements.",
    "Ollama Pro or higher is the documented minimum tier for complete intended cloud-model operation. This is not sponsorship, and plan pricing/limits must be checked with Ollama.",
    "The explicit private builder merges same-machine contact sources into gitignored `contacts.private.json` using normalized names, alias union, and non-empty-value preservation.",
    "Public builds ship an empty contacts book; self-modify snapshots contain no contact files; generated dossiers never reproduce contact values, credentials, or live catalog secrets.",
]

STRUCTURED_CONTENT_1414_GUIDE = [
    "Modern MCP servers may return a short human-readable pointer in `content` while placing the actual result in `structuredContent`; the old parser discarded that machine-readable payload.",
    "Without the actual data, the model could repeat the same valid tool call until Tlamatini's repetition breaker force-stopped the run, making a successful external server appear to auto-cancel.",
    "`_format_mcp_tool_result` is now the single formatter used by both `_StdioMcpClient.call_tool` and `_NetworkMcpClientBase.call_tool`, so transport choice no longer changes result fidelity.",
    "Text blocks and non-text content are retained, while a sole `{\"result\": ...}` structured envelope is unwrapped before JSON serialization.",
    "`isError` still returns an explicit error and can now include structured-only error details; non-dict results are stringified safely.",
    "Structured payloads are capped at 24,000 characters by default with an explicit truncation marker, protecting the model context from unexpectedly huge tool responses.",
    "Seven tests cover pointer-plus-data, unchanged plain text, envelope unwrapping, text and structured-only errors, payload capping, and non-dict input.",
    "The fix is released as `v1.41.4` at `cec16594` and is present on `origin/main`.",
]

STM32ER_PLATFORMIO_WORKTREE_GUIDE = [
    "Release status: STM32er PlatformIO Phase 1 was published in tagged `v1.42.0` at `c58b01ad`.",
    "`stm32_backend=auto` keeps the legacy Template-MCP path for blank/STM32F4 requests, but a board, a non-F4 device, or a PlatformIO-only action routes to the new direct PlatformIO backend.",
    "Friendly board aliases and device-to-board mappings include the STM32F103 Blue Pill, while raw PlatformIO board ids remain accepted for broader `ststm32` coverage.",
    "The backend mirrors ESP32er's zero-config bootstrap and shared per-user PlatformIO core, then supports environment, board, project, source, package, build, upload, monitor, QA, and artifact actions.",
    "A preflight resolves the board/family, validates `platformio.ini`, probes PlatformIO and ST-LINK readiness, and requires hardware only for upload/monitor operations; compile-only actions remain boardless-safe.",
    "`scaffold_build_flash` creates or reuses a project, writes source, builds, and flashes only when ST-LINK is confidently detected; otherwise a successful build is reported with a clear connect-and-flash next step.",
    "The broad family parser recognizes the full ST line, but PlatformIO-incompatible newest families C0/H5/U0/WBA/N6 are deliberately refused instead of risking an incorrect linker or target.",
    "The planned CubeCLT/CubeMX backend remains proposal-only for those newest devices, especially STM32N6 signing and external-flash requirements.",
    "New assets include the all-families proposal and migrations `0177`-`0179`: one-call Blue Pill build/conditional flash, two stepwise camera-verified board walkthroughs, then a deliberate category-grouped no-gap catalog renumber.",
    "Registry, contracts, wrapped-tool defaults, config, agent code, descriptions, and tests move together; focused coverage pins family/routing safety plus catalog contiguity, prompt-name identity, category ordering, and demo presence.",
]

STM32ER_STEPWISE_DEMOS_GUIDE = [
    "Migration `0178_add_stm32_stepwise_blink_camera_prompts.py` adds two `firmware_iot` walkthroughs: STM32F103 Blue Pill over an external ST-LINK V2 and STM32F407G-DISC1 over its embedded ST-LINK/V2.",
    "Both prompts require Multi-Turn, Exec Report, and Step-by-Step mode, execute exactly one stage per turn, wait for the operator's `READY`, and verify each prerequisite before moving forward.",
    "The six-stage Blue Pill path covers driver/CLI readiness, four-wire SWD wiring and probe detection, PlatformIO bootstrap, project/source/build, ST-LINK flash, and camera proof of the PC13 LED.",
    "The five-stage Discovery path uses the board's ST-LINK USB port, then bootstrap, project/source/build, embedded-probe flash, and camera proof of the green PD12 LED.",
    "Final evidence comes from `chat_agent_camcorder`; the prompt may pass the clip to Video-Analyzer or Image-Interpreter and must return a clear PASS or FAIL with the saved file path.",
    "These are seeded demonstrations and operator procedures, not a claim that hardware verification occurred during dossier generation.",
]

PROMPT_CATALOG_WORKTREE_GUIDE = [
    "Released migration `0179_regroup_resort_prompts_no_gaps.py` is a one-time deliberate override of the earlier no-renumber convention; it runs after the two new STM32 walkthroughs are appended.",
    "Every Prompt is sorted by the same category-display rank used by the UI and then by its prior id, so each category becomes one contiguous block from beginner workflows through specialized surfaces and the `other` fallback.",
    "Because `idPrompt` is the primary key, the migration first parks rows above 1,000,000 and then assigns final ids 1..N, avoiding collisions while rewriting `promptName` to `prompt-<id>`.",
    "The migration is intentionally one-way: reverse is a no-op because original ids are not stored; the source documents that no runtime foreign key references fixed prompt numbers.",
    "Future additions still append at max(idPrompt)+1, preserving contiguity until another deletion; the frontend's gap-tolerant fallback remains a defensive compatibility path.",
    "`test_prompt_catalog_contiguous.py` adds four database tests for no gaps, promptName/id agreement, nondecreasing category rank, and presence of both STM32 board demos plus Camcorder evidence.",
]

PROMPT_CATALOG_1413_GUIDE = [
    "Migration `0175_prompt_category_and_dedup.py` classifies the 106 historical prompt rows into 13 named operator categories, from Getting Started and Files/Search through ACPX, firmware, security, messaging, media, and a fail-safe More bucket.",
    "Migration `0176_delete_duplicate_acpx_prompts.py` physically deletes ids 40-52: 13 banner/Gemini variants that duplicate the seven portable ACPX demos retained at ids 33-39; surviving ids are never renumbered.",
    "Gaps are now valid. `/agent/list_prompts/` returns all visible rows regardless of id continuity, and the offline `prompt-N` fallback skips a missing id instead of terminating the catalog at the first gap.",
    "`Prompt.category` and `Prompt.hidden` remain schema-level controls, while `PROMPT_CATEGORY_ORDER` gives every known category a stable display rank and routes unknown or future values into `other` rather than dropping them.",
    "The modal renders explicit category headers and counts, then restores that grouped basic-to-advanced order whenever the search query clears.",
    "Live search accepts a prompt number, title words, mode labels, acronym, contiguous text, or fuzzy subsequence; it requires every query token, ranks best-first, highlights matched characters, and exposes Enter-to-open plus Escape/clear behavior.",
    "Prompt cards retain their One-Shot, Multi-Turn, ACPX, Exec Report, and Step-by-Step mode badges and continue to set the matching toolbar toggles when selected.",
    "The catalog stays viewport-pinned and bounded in CSS so its header and search bar remain reachable independently of the chat input height, with no JavaScript geometry coupling reintroduced.",
]

HARD_CANCEL_GUIDE = [
    "`agent/cancellation.py` mints a monotonically increasing run epoch per user and permanently latches the highest cancelled epoch; clearing the legacy setup boolean can no longer resurrect that run.",
    "Cancellation is isolated per user, so a browser tab cannot kill another user's TeleTlamatini or concurrent browser run; a missing epoch is deliberately fail-open so a dropped payload field cannot poison all future requests.",
    "`ask_rag`, both unified-chain payload rebuilds, and `CapabilityAwareToolAgentExecutor` carry and check `run_epoch`, closing the prior gap where model retries or tool loops could continue after Cancel.",
    "The executor returns a structured cancelled result instead of raising, preserving already-completed tool evidence, Exec Report data, and Create Flow inputs without triggering a fabricated transient-error fallback.",
    "Self-healing consults the same latch before retries, after watchdog waits, and before tactic announcements, so no new recovery tactic can be emitted once the operator cancels.",
    "Ask Execs polls the run latch and resolves a blocked Proceed/Deny request as deny; consumer teardown revokes the exact status emitter so a dying run cannot re-arm the UI.",
    "Frontend `userCancelledRun` is mutable per-session state: late tactic frames become strict no-ops until the next submit/reconnect, preventing the Send button from flipping back to Cancel.",
    "Coverage includes 24 cancellation contract tests, focused Ask-Execs/self-healing tests, and visible browser regression harnesses for long tool chains, model steps, repeated cancels, next-request recovery, and approval-modal cancellation.",
]

CHAT_IMAGE_1410_GUIDE = [
    "The chat accepts clipboard bitmaps through document-level Ctrl+V handling and image files dropped only onto the main chat column, avoiding conflict with the External-MCP dialog's document-level JSON drop surface.",
    "`POST /agent/paste_image/` validates the request, enforces a 25 MB ceiling, uses Pillow to flatten transparency onto white, re-encodes to JPEG, and writes a collision-safe `image_<timestamp>.jpg` under Tlamatini's guarded Temp directory.",
    "The browser inserts the saved absolute path at the remembered caret, including after focus moves to the page body during Alt+Tab, then renders one removable thumbnail chip per image.",
    "Removing a chip removes both its thumbnail and its exact path from the message, so an accidental paste can be reversed before submission.",
    "The path is the integration contract: Image-Interpreter reads local files, and `prompt.pmt` teaches Tlamatini to treat a fresh Temp image path as the user's supplied screenshot instead of asking for another attachment.",
    "`computeFormMinHeight()` measures the chips row and a ResizeObserver watches it, preventing the new row from pushing the textarea or Send button beyond the viewport.",
    "Implementation assets include `chat_image_paste.js`, the paste view/URL, template chip/drop-overlay nodes, `.chat-img-*` CSS, layout integration, self-knowledge/prompt guidance, and Temp-policy regression coverage.",
]

DJANGO_PORT_GUIDE = [
    "`django_port` moves the web UI and chat WebSocket bind away from a hardcoded 8000: edit the integer in `config.json`, restart Tlamatini, and no rebuild or source edit is required.",
    "The motivating failure is Windows `WinError 10013`: Hyper-V, WSL, or Docker can reserve port 8000 inside a dynamic exclusion range, making a frozen build unable to bind until the port is changed.",
    "Three stdlib-only helpers run before Django imports: `_resolve_config_path()` chooses `CONFIG_PATH`, the frozen executable's neighbor, or source `agent/config.json`; `_resolve_django_port()` validates `1..65535`; `_apply_configured_port()` injects the result.",
    "The completion pass calls `_apply_configured_port(sys.argv)` once from `main()`, outside the frozen branch, so frozen double-click, `.flw` association, browser auto-open, source `runserver`, and `startserver` all agree.",
    "Resolution is fail-open to 8000 for missing, unreadable, malformed, non-numeric, or out-of-range values, while an explicit CLI port such as `runserver 9100` always wins and is never double-appended.",
    "The injected source-mode value is a bare port so Django keeps its loopback host; direct Daphne/Uvicorn bypasses `manage.py`, MCP listeners `8765`/`50051` use their own settings, and TeleTlamatini keeps its own base URL.",
    "The 24-test `agent/test_django_port_config.py` suite AST-lifts the pre-Django helpers and pins path resolution, validation, fail-open behavior, CLI precedence, frozen/source wiring, and `startserver` forwarding without importing side-effectful `manage.py`.",
    "`freeingport8000.ps1` is a separate elevated Windows repair helper that resets dynamic TCP/UDP ranges, restarts WinNAT, reports excluded ranges, and performs a loopback bind test; changing `django_port` remains the safer normal remedy, and generated docs never reproduce the script's machine-specific log path.",
]

NMAPPER_GUIDE = [
    "Nmapper is the `v1.39.3` local nmap bridge for authorized pentesting and CTF recon: it is a use-only integration, not a bundled scanner.",
    "The agent never ships or redistributes nmap; it resolves a user-installed `nmap` from explicit config, PATH, Program Files, or `%LOCALAPPDATA%`, and its `install` action launches the official free installer path.",
    "The default scan path is an unprivileged TCP connect scan (`-sT`), while raw-packet features such as SYN/OS/UDP are downgraded or refused safely when Npcap or elevated packet capture is unavailable.",
    "Supported actions include `quick`, `full`, `top_ports`, `version`, `scripts`, `host_discovery`, `udp`, `custom`, `validate`, and `install`, always for targets the operator owns or is explicitly authorized to assess.",
    "Each run emits one atomic `INI_SECTION_NMAPPER` block with action, target, scan technique, ports, return code, success state, hosts-up/open-port summaries, Npcap state, XML path/content, normal output, and stage.",
    "Implementation assets include `agent/agents/nmapper/`, migrations `0170`-`0172`, `test_nmapper_agent.py`, `chat_agent_nmapper`, `update_nmapper_connection`, contracts/Parametrizer fields, ACP connector assets, FlowCreator/FlowHypervisor entries, and handbook/docs updates.",
]

STARTUP_PROMPT_POLISH_GUIDE = [
    "`v1.39.4` restored first-run/startup dialog closeability so a fresh launch can no longer be trapped behind an unclosable overlay.",
    "Commit `a45fe0e0` followed the public `v1.39.4` tag with Catalog-of-Prompts localization cleanup; that historical polish remains carried by the current release line.",
    "The prompt catalog path stays centralized through the secure one-call `/agent/list_prompts/` endpoint ordered by category rank and stable surviving id, while the gap-tolerant probe loop remains only as an offline fallback.",
    "Frontend mutable-state tests and dialog templates continue to guard the chat/startup/overlay surfaces so future cleanup passes do not reintroduce const-poison or close-button regressions.",
]

FLOWPILLS_DISCOVERY_GUIDE = [
    "Tlamatini-FlowPills reads `HKCU\\Software\\XAIHT\\Tlamatini` first, especially the exact `AgentsRoot`, before falling back to Installed Apps, `.flw` association data, executable-relative roots, or source/preserved probes.",
    "The registry contract always rewrites six REG_SZ values — `InstallLocation`, `AgentsRoot`, `SourceAgentsRoot`, `AgentManifestPath`, `Version`, and `AgentCatalogVersion` — using an empty value when something is unknown so stale metadata cannot survive across source and frozen runs.",
    "`agent_manifest.py` discovers only complete templates, excludes `pools` and `__pycache__`, hashes script/config contents, computes a name-set catalog id, and writes atomically only when meaningful data changed.",
    "Launch publication runs first in `AgentConfig.ready()` on a daemon thread with its own idempotency gate, so optional MCP, model, ACPX, or skill import failures cannot suppress companion discovery.",
    "An agents-preserving uninstall restamps the manifest as `preserved`, writes `.tlamatini-preserved-agents.json` with the manifest SHA-256, and keeps the discovery key pointing to the preserved catalog.",
    "The contract is HKCU-only, no-admin, fail-open, and read-only with respect to agent templates; the filesystem remains the final validity authority for companion applications.",
]

UNREAL_SCAFFOLD_GUIDE = [
    "The new Unreal scaffold prompt asks for only project name and destination, locates or obtains `XaihtUnrealEngineMCP`, and invokes its deterministic `scaffold_unreal_project.py` helper.",
    "The scaffold copies and renames `MCPGameProject`, sets EngineAssociation 5.8, finds an installed UE 5.8 even when it is not registered, bundles UnrealMCP, and generates the Visual Studio 2026 solution.",
    "UE 5.8 build compatibility is explicit: V7 build settings, `Unreal5_8` include order, a `Directory.Build.targets` mitigation for the Windows environment-length limit, and a pre-fixed Visual Studio Tools plugin.",
    "The prompt instructs operators to build the project target rather than the entire solution, then open the editor; UnrealMCP starts its TCP listener at `127.0.0.1:55557` for Unrealer.",
    "Unrealer normalizes disk-style `/Content` references to `/Game`, maps the friendly material `slot` input to `slot_index`, and forwards one command per TCP connection into the live editor.",
    "Migrations `0173` and `0174`, Unrealer code/config comments, README/Book entries, and the current release metadata carry the scaffold workflow across source, catalog, and operator documentation.",
]

RESPONSIVENESS_HARDENING_GUIDE = [
    "The `v1.39.5` smoothness wave focuses on bounded waits, concurrency isolation, accurate partial-result reporting, and lossless final answers rather than a new agent count.",
    "Image-Interpreter now bounds Ollama connect/read gaps; the System-Metrics WebSocket bounds receive time; External MCP warm-connect/supervisor gates recover if thread start fails; and command/ACPX output decoding is UTF-8-safe.",
    "Nmapper assigns per-host budgets to slow actions, keeps the outer kill budget above them, preserves partial output, uses collision-proof filenames for parallel scans, and labels hard timeouts honestly.",
    "Multi-Turn folds deferred completion deliverables into every exit path, while orphan-survivor state is keyed by conversation user so simultaneous requests cannot consume or clear each other's evidence.",
    "`.flw` export redaction covers ordinary secret paths and URI userinfo, and the command parser distinguishes Windows trailing backslashes from escaped inner quotes at assignment boundaries.",
    "These changes are now committed release behavior; the user's pre-refresh uncommitted configuration values remain private and are not quoted in this dossier.",
]

ROBOTIC_LOOP_GUIDE = [
    "`v1.38.0` is the milestone where the Robotic-Loop-Training story became concrete: Tlamatini demonstrated a closed hardware loop by programming a robotic arm from a blank page and two cameras.",
    "The loop is intentionally composable rather than one monolith: STM32er writes/builds/flashes firmware, Camcorder records the physical attempt, Video-Analyzer judges the captured motion, and Forker routes the next branch.",
    "Video-Analyzer keeps the loop conservative: a deterministic OpenCV gate rejects no-motion clips before model spending, then two independent Ollama cloud vision interpreters must agree before `PASS_OK` is emitted.",
    "Forker branches on substring-safe `TLM_VERDICT::<TOKEN>` markers, so `FAIL_NO_MOTION`, `FAIL_WRONG_MOTION`, `UNCLEAR`, or `ANALYSIS_ERROR` can never accidentally match the success route.",
    "The PDF and PPTX now describe that loop as a system capability, not merely a release-note flourish, because it explains how Tlamatini can iteratively improve real hardware with observed evidence.",
]

FRONTEND_HOTFIX_GUIDE = [
    "`v1.38.1` was the same-week frontend-state-recovery hotfix: `package.json` was aligned at the tagged commit `08efa1d2`, while the functional fix landed in `af356c31` after the `85ee4e6c` const-poison incident.",
    "The core contract is explicit: cross-file runtime globals in `agent_page_state.js` and `acp-globals.js` that other modules reassign must remain `let`, because per-file ESLint cannot see those cross-file writes.",
    "`agent/test_frontend_mutable_state.py` now guards both source files and collected staticfiles so an automated cleanup cannot silently turn chat state, ACP state, tools, agents, skills, history, or busy flags back into `const`.",
    "The Catalog of Prompts now loads through one secure `GET /agent/list_prompts/` endpoint ordered by `idPrompt`, eliminating expected-404 console spam and preventing an `idPrompt` gap from hiding later prompts.",
    "The legacy prompt probe loop remains as an offline fallback, and the same fix also hardened dialogs: Configure-Mcps probe loops exit cleanly, About-video `play()` promises are guarded, and Esc closes About/Update overlays.",
]

V136_RELEASE_GUIDE = [
    release_identity(),
    "Historical introduction: Video-Analyzer joined as a media-verdict workflow agent and wrapped `chat_agent_video_analyzer`, complementing Image-Interpreter with video-specific motion analysis.",
    "Implementation assets: `agent/agents/video_analyzer/`, migrations `0166_add_video_analyzer.py`, `0167_add_chat_agent_video_analyzer_tool.py`, `0168_add_video_analyzer_demo_prompt.py`, `test_video_analyzer_agent.py`, `chat_agent_registry.py`, `mcp_agent.py`, and `services/agent_contracts.py` all move together.",
    "Model strategy: `interpreter_model_1` defaults to `gemma4:cloud`, `interpreter_model_2` defaults to `jcyhsiao/qwen3.5cloud:latest`, and `merging_model` defaults to `glm-5.3:cloud`, with independent calls merged only after both interpreters report.",
    "Robotics routing contract: each robotics run emits `INI_SECTION_VIDEO_ANALYZER` plus `TLM_VERDICT::<TOKEN>` markers such as `PASS_OK`, `FAIL_NO_MOTION`, `FAIL_WRONG_MOTION`, `UNCLEAR`, and `ANALYSIS_ERROR` for Forker and Parametrizer.",
    "Adjacent UI work: prompt search moved from exact-title hunting to substring, word-start, and fuzzy matching, and generated `.flw` files now use a serpentine layout to reduce visual congestion.",
]

VIDEO_ANALYZER_GUIDE = [
    "Video-Analyzer selects analysis_type: robotics (default), transcription, or summary. Input is a video file, wildcard, folder-newest rule, or Camcorder pool name.",
    "Robotics retains the motion gate and two independent vision interpreters plus merger. PASS_OK requires both explicit passes; a missing verdict is never agreement.",
    "Transcription reads selected video audio tracks through local faster-whisper with GPU auto/CPU fallback, timestamps and track indexes. It never opens the microphone.",
    "Summary combines speech with timestamped visual batches across the full clip, then synthesizes chronology, readable text, facts, steps, decisions, action items and limitations.",
    "Content modes bypass the motion gate and route on TLM_ANALYSIS tokens. Parametrizer receives transcript, summary, segments_json, audio_status and artifact paths in INI_SECTION_VIDEO_ANALYZER.",
    "Unique run artifacts contain the complete transcript, segments, report and analysis. Missing audio and partial failures are explicit; sampled perception is not exhaustive. See agents/video_analyzer/README.md.",
]

PROMPT_SEARCH_AND_FLOW_GUIDE = [
    "Prompt search now behaves like an operator tool instead of a static dropdown: category grouping, numeric/acronym/substring/word-start/subsequence matching, best-first ranking, highlighted hits, and mode badges make the deduplicated catalog navigable.",
    "The prompt-card rendering keeps One-Shot, Multi-Turn, ACPX, Exec Report, and Step-by-Step families distinguishable while migrations `0175`-`0176` remove redundant ACPX variants without renumbering surviving prompt ids.",
    "Generated `.flw` workflows now use a serpentine canvas layout with row capacity and alternating direction, preserving the logical Starter -> Agent -> ... -> Ender order without pushing large chains into an unreadable line.",
    "This matters for documentation because the PDF and deck must describe not only new agents, but also the operator usability improvements that make the larger system actually usable.",
]

SELF_HEALING_GUIDE = [
    "Every Multi-Turn model step now goes through `agent/self_healing.py::SelfHealingInvoker`, so model calls are bounded by `unified_agent_llm_step_timeout_seconds` and retried with distinct tactics instead of hanging silently.",
    "Recovery tactics include plain retry, short back-off, trimming oldest messages with `trim_messages`, and a tool-less summary fallback; the ladder can run up to `unified_agent_llm_step_max_tactics` unless the user presses Cancel.",
    "A status broadcaster registered by `consumers.py` sends live first-person recovery messages to the user's chat while the executor works in a worker thread.",
    "If recovery is exhausted after agents already ran, `mcp_agent.py` builds a degraded but truthful answer from real `ToolMessage` results, preserves Exec Report/Create Flow evidence, and prepends `recovery_preamble(...)` instead of claiming no tools ran.",
    "Coverage includes `agent/test_self_healing.py`, `agent/tests.py`, `Tlamatini/tests_e2e/test_self_healing_visual.py`, and `Tlamatini/tests_e2e/test_create_flow_visual.py` for visible browser validation.",
    "Frontend follow-up: `agent_page_ui.js::isSelfHealingStatusMessage()` anchors on leading `Tactic #` or `Tactic '` status frames so `appendChatMessage()` keeps controls disabled and the Send button on Cancel while the run is still executing.",
    "The matcher deliberately avoids substring matching because the final `recovery_preamble(...)` quotes tactic lines; a loose `includes` match would misclassify the final answer and trap the UI on Cancel forever.",
]

CREATE_FLOW_GUIDE = [
    "The whole-answer SUCCESS/FAILURE classifier `agent/services/answer_analizer.py` was removed on 2026-07-06, so no extra LLM round trip computes `answer_success`.",
    "The browser now shows Create Flow when Multi-Turn ran, at least one successful tool call resolves to a registered canvas agent, and the user is not anonymous.",
    "Successful tool calls are resolved through a punctuation/space/case-insensitive registry key, so display names such as `File Creator`, `File-Creator`, and `filecreator` converge to the live Agents sidebar entry.",
    "Generated `.flw` downloads keep only successful, resolvable tool-call entries, post a successful-only `tool_calls_log` to `/agent/flow_from_tool_calls/`, and drop failed or unregistered executions rather than turning them into broken workflow nodes.",
    "If the registry cannot load, the frontend fails open: the button stays available and the backend flow normalizer remains the final validation layer.",
    "Exec Report remains per-tool evidence, not a whole-answer verdict; the checkbox is disabled/greyed unless Multi-Turn is checked.",
]

FRONTEND_RECOVERY_GUIDE = [
    "`agent_page_chat.js::appendChatMessage()` now has a self-healing status branch before the final-answer branch, so status frames render without calling `enableControlsAfterOperation()`.",
    "`disableControlsDuringOperation()` is re-applied idempotently for each live tactic status line, preserving the user's Cancel button while the worker thread continues.",
    "`agent_page_ui.js::isSelfHealingStatusMessage()` strips leading icons/symbols and then anchors on `Tactic #` / `Tactic '`, matching standalone status frames but not the final recovery summary.",
    "Create Flow validation now uses `_resolveSuccessfulAgents()`, `_agentNameKey()`, and `_buildRegistryKeyMap()` to normalize display names against the live registry and skip only unresolved successful entries.",
    "`eslint.config.mjs` declares `isSelfHealingStatusMessage` as a global, while `docs/claude/frontend.md`, `docs/claude/multi-turn.md`, and `docs/claude/recent-fixes.md` document the gotcha and the no-substring rule.",
]

DISCOVERER_PDCP_GUIDE = [
    "Discoverer now has an optional ProjectDiscovery Cloud Platform key (`pdcp_api_key` / `PDCP_API_KEY`) for cvemap/vulnx rate limits and nuclei `-ai` or cloud upload features.",
    "Config -> Access Keys Wizard exposes `Security Recon (ProjectDiscovery)`, writes the key to `config.json`, `data.keys`, and `agent/agents/discoverer/config.yaml`, and blank fields preserve existing values.",
    "`tools._seed_global_agent_defaults` auto-injects the configured key into every `chat_agent_discoverer` run so prompts never paste the credential.",
    "`agent_contracts.py` redacts `pdcp_api_key` from `.flw` exports, and `regen_secrets.py` scrubs it back to `PDCP_API_KEY` before a push-able tree.",
    "The new `0169_add_discoverer_cvemap_latest_demo_prompt.py` migration seeds a passive latest-CVE briefing prompt that uses cvemap/vulnx and reports whether `pdcp_used` was active.",
]

DISCOVERER_VULNX_GO_GUARD_GUIDE = [
    "ProjectDiscovery retired cvemap's CVE API in August 2025, so Tlamatini keeps the operator-facing `cvemap` tool key but installs and runs ProjectDiscovery's successor binary, `vulnx`.",
    "`discoverer.py` now maps `cvemap` to `github.com/projectdiscovery/cvemap/cmd/vulnx@latest`, resolves the installed binary as `vulnx`, and builds `vulnx id <CVE>` or `vulnx search --severity ... --product ... --limit ...` arguments.",
    "The findings counter now understands vulnx object JSON such as `{\"count\": N, \"results\": [...]}`, so Exec Report and Forker routing see the real result count instead of a misleading one-line object.",
    "The private Go compiler and ProjectDiscovery tool binaries still install under `<install_dir>/Go` / `<install_dir>/Go/bin-tools`, keeping the runtime self-contained and avoiding any system Go or PATH mutation.",
    "The `.gitignore` Go-deny block, tracked `git_deny_go.py`, and its managed pre-commit hook prevent `Go/`, `bin-tools/`, `go-build/`, `pkg/mod/`, and downloaded Go archives from entering source control; ignored `Go/` content is not counted as project code.",
    "The committed asset wave also includes `0169_add_discoverer_cvemap_latest_demo_prompt.py`, `.claude/skills/tlamatini-daily-chat-test/harness/discoverer_1000.py`, and `Tlamatini/agent/test_discoverer_thousand.py` for latest-CVE and high-volume Discoverer validation.",
]

V1332_RELEASE_GUIDE = [
    "Historical release family: `v1.33.2` introduced the Zavuerer wave and subsequent cleanup, preserving the v1.32.0 quality-and-identity background. The current release version is 1.65.4.",
    "New agent: Zavuerer becomes the 83rd workflow-agent type and the 60th wrapped chat-agent, adding `chat_agent_zavuerer` for Zavu unified messaging across SMS, WhatsApp, Telegram, Email, and Voice.",
    "Configuration: Config -> Access Keys Wizard now includes `Unified Messaging (Zavu)` and persists `zavu_api_key`, which the wrapped runtime seeds into Zavuerer without exposing the secret in prompts.",
    "Canvas/runtime support: `agent_contracts.py`, `views.py`, `capability_registry.py`, `chat_agent_registry.py`, `tools.py`, frontend ACP JS/CSS, and migrations `0159`-`0164` all move together to make Zavuerer usable from both surfaces.",
    "Follow-up defaults: `config.json` now favors `glm-5.3:cloud` across the primary chat/model slots, and the latest commits also adjust runtime parsing/middleware/settings surfaces around the release.",
    "Cost and safety wording: sign-up for Zavu is free, but sends are pay-as-you-go per message; the docs keep the authorized, opted-in recipient boundary explicit for A2P, WhatsApp-window, consent, and GDPR-style rules.",
]

IMAGE_INTERPRETER_GUIDE = [
    "Image-Interpreter is now a triple-model vision analyst, not a single generic image describer: each image goes through two parallel interpreter calls and one merger pass.",
    "`interpreter_model_1` defaults to `jcyhsiao/qwen3.5cloud:latest` and is tuned for forensic OCR, mockup/GUI element inventories, percent-based positions/sizes, colors, fonts, and verbatim text.",
    "`interpreter_model_2` defaults to `gemma4:cloud` and reads the image holistically: design intent, visual hierarchy, scene meaning, people, and reasoned identity hypotheses.",
    "`merging_model` defaults to `glm-5.3:cloud`; it waits behind a barrier until both interpretations arrive, then emits one definitive report with union-of-facts, conflict notes, and discrepancy handling.",
    "All four prompt surfaces (`prompt_user`, `prompt_interpreter_model_1`, `prompt_interpreter_model_2`, and `prompt_merging_model`) receive the image file name as an identity clue, because a file named after a person often depicts that person.",
    "Fail-safe behavior is explicit: one failed interpreter still lets the merger work from the survivor; a failed merger returns both raw interpretations concatenated instead of losing the analysis.",
    "The structured output is now `INI_SECTION_IMAGE_INTERPRETER` with `file_path`, `interpreter_model_1`, `interpreter_model_2`, `merging_model`, `status`, and the merged report body for Parametrizer/Forker routing.",
    "Config -> Models exposes 38 settings in six categories, including Image-Interpreter's three slots, Video-Analyzer, Talker, Whisperer, workflows, documents and monitors. Missing new keys in preserved configs receive registry defaults.",
]

ZAVUERER_GUIDE = [
    "Zavuerer is Tlamatini's new Zavu unified-messaging agent: one workflow node and one wrapped `chat_agent_zavuerer` tool can send SMS, WhatsApp, Telegram, Email, or Voice messages through Zavu's `/v1/messages` API.",
    "The operator configures one `zavu_api_key` through Config -> Access Keys Wizard -> Unified Messaging (Zavu), and the runtime seeds that key into Zavuerer automatically so prompts never need to repeat or expose the secret.",
    "The agent speaks direct HTTP through the Python standard library, has a safe `health` action, refuses sends when the key/recipient/body/channel are invalid, and always emits `INI_SECTION_ZAVUERER` for Parametrizer/Forker branching.",
    "Canvas integration is complete: `agent_contracts.py` redacts `zavu_api_key`, `views.py` handles Zavuerer connections, frontend CSS/JS gives the node a visible identity, and migrations `0159`-`0164` seed the Agent, Tool, demo/catalog prompts, and setup-wizard dedupe.",
    "Cost and safety boundary: Zavu sign-up is free, but sending is pay-as-you-go per message; Zavuerer must only message authorized, opted-in recipients, with A2P, WhatsApp 24-hour-window, consent, and GDPR-style responsibilities called out explicitly.",
]

EXTERNAL_MCPS_GUIDE = [
    "The `v1.26.0` headline feature is the External MCP universal client: Tlamatini can now consume any MCP server declared in `external_mcps.json` instead of depending only on bundled MCP integrations.",
    "Four transports are supported in the current implementation — stdio, streamable HTTP, legacy SSE, and WebSocket — and the active server set is intentionally bounded so operators can expose high-value remote tools without flooding the planner.",
    "Once connected, remote MCP tools are wrapped into the same Multi-Turn execution surface under `ext__<server>__<tool>`, so they participate in planning, execution reporting, Ask Execs, and the rest of the operator guardrails instead of becoming a parallel hidden subsystem.",
]

MCP_DOCTOR_GUIDE = [
    "MCP Doctor is the new onboarding and triage specialist added with the External MCP release: she inspects a configured server entry and tells the operator what is wrong before a live connection attempt wastes time.",
    "The diagnostic checks cover transport shape, runtime command availability on PATH, placeholder or missing secrets, endpoint/source/docs links, and the concrete next step the operator should take to make the server connectable.",
    "Operators can reach the same behavior from both surfaces that matter: the MCP Doctor workflow agent on the canvas and the wrapped `chat_agent_mcp_doctor` tool inside Multi-Turn.",
]

EXTERNAL_MCP_ASSETS_GUIDE = [
    "The release is backed by real tracked assets rather than markdown-only claims: `agent/external_mcp_manager.py`, `agent/external_mcps.json`, the `agent/agents/mcp_doctor/` tree, the `0141`-`0143` migrations, `static/agent/js/external_mcps_dialog.js`, and `static/agent/css/external_mcps_dialog.css` are the core implementation wave.",
    "The current test surface proves this is not a shallow UI feature: `test_external_mcp_universal.py`, `test_external_mcp_transports.py`, `test_external_mcp_e2e.py`, `test_external_mcp_add_flow.py`, and `test_parametrizer_mcp_doctor.py` exercise the universal-client path and the onboarding diagnosis path.",
    "Handbook evidence now exists alongside the code too: the README tutorial, Book sections, capability/planner wiring, and the dialog assets all moved together in the same release wave, with later cleanup removing obsolete draft documentation from the tracked tree.",
]

BLENDERER_GUIDE = [
    "Blenderer was introduced in `v1.20.0` as the 77th workflow agent and remains the direct bridge to the official Blender MCP add-on, letting Tlamatini operate a live Blender session from either Multi-Turn chat or the visual workflow canvas.",
    "The bridge talks over a TCP socket (default `localhost:9876`) and supports both raw `execute_code` requests and higher-level scene/object/material/render actions, so operators can mix deterministic verbs with precise Python-driven 3D automation.",
    "This extends Tlamatini beyond code and firmware orchestration into DCC / 3D-production work: asset inspection, scene mutation, material changes, camera setup, and render-triggering now live inside the same operator surface as the rest of the system.",
]

SELF_UPDATE_GUIDE = [
    "The packaged application now includes an in-app self-update flow exposed from About -> Check for updates, so operators can refresh a frozen install without manually unpacking and replacing the entire release folder.",
    "The backend checks the latest GitHub release, downloads and stages the package, then hands off the locked-file swap to `apply_update.ps1`, which performs the replacement after the running executable exits and relaunches the updated app.",
    "The update path is state-preserving by design: it keeps `config.json`, user content, and one `agents_backup` generation, and it stages the user's database through `DB/ToLoad/` plus `post_update_migrate.flag` so the next launch restores and migrates that DB instead of wiping it.",
]

SOURCE_SNAPSHOT_GUIDE = [
    "Self-modify builds now rely on `copy_source_assets.py` to generate `TlamatiniSourceCode/` as a fresh rebuild-oriented snapshot of the repository.",
    "That snapshot includes source, build scripts, docs, skills, and small required binaries while deliberately omitting or redacting heavy media and secrets; `_REBUILD_INSTRUCTIONS.md` plus `_SOURCE_SNAPSHOT_MANIFEST.json` explain how to restore the missing payloads.",
    "Because the snapshot is optional, the runtime contract remains strict: Tlamatini must verify that `TlamatiniSourceCode/` exists before claiming she can inspect, modify, or rebuild herself.",
]

API_KEYS_WIZARD_GUIDE = [
    "Config now includes an Access Keys Wizard / API-Keys Wizard path so operators can manage provider credentials from the browser instead of editing `config.json` directly.",
    "The backend exposes masked status plus explicit save endpoints, which keeps the operator flow convenient without echoing raw secrets back into the page.",
    "That feature arrives as a real asset wave, not just a hidden helper: `agent/access_key_wizard.py`, `static/agent/js/access_keys_wizard.js`, `static/agent/css/access_keys_wizard.css`, and the updated `templates/agent/agent_page.html` now form a dedicated setup surface.",
    "This matters operationally because ACPX agents, cloud LLM providers, and adjacent integrations often fail for simple missing-key reasons; the wizard turns that setup into a first-class UI workflow.",
]

FILE_CREATOR_HARDENING_GUIDE = [
    "The `v1.19.5` File-Creator hardening pass fixes the wrong-symbol / wrong-escape corruption path that hit backslash-dense Java, JSON, CSS, and regex files during wrapped chat-agent execution.",
    "Two byte-exact channels now exist: plain `content` is re-extracted verbatim from the raw request, and `content_b64` can carry source or binary bytes through a parser-immune base64 path when exact escaping matters most.",
    "For operators, the consequence is straightforward: code generation and document generation can now be described as byte-complete file writes rather than best-effort convenience output.",
    "This belongs in the dossier because File-Creator is one of Tlamatini’s central deterministic execution surfaces and one of the safest alternatives to GUI typing or editor-driving automation.",
]

MEDIA_VOICE_GUIDE = [
    "The current media family spans capture, playback, and speech: Shoter (screen), Camcorder (camera-in), Recorder (mic-in), AudioPlayer (speakers-out), VideoPlayer (screen-out with audio), Talker (text-to-speech), and Whisperer (speech-to-text).",
    "Talker remains female-only by design and uses an Ollama neural TTS model with SNAC decoding, while Whisperer records the microphone itself or transcribes a file through faster-whisper locally or cloud Whisper APIs.",
    "Recent stability work matters here too: Talker now chunks long input by sentence for long-form speech, and media-output defaults were moved into the application `Temp` directory rather than user content folders.",
]

COMMAND_WATCHDOG_GUIDE = [
    "A boot-time autonomous command watchdog now protects the chat against shell wrappers that stay alive while making zero CPU or I/O progress, the classic signature of a mangled prompt waiting forever on stdin.",
    "It never kills on elapsed time alone: the subtree must outlive the grace window and remain idle for a configured streak, so long builds, downloads, and compiles are preserved while only genuinely wedged interpreters are reaped.",
    "This watchdog complements rather than replaces the orphan reaper: the watchdog rescues blocked synchronous tool calls before they return, while the orphan reaper still handles post-return survivors and stale console companions.",
]

NEW_ASSETS_GUIDE = [
    "The tagged `v1.41.4` wave adds the shared `_format_mcp_tool_result` path in `external_mcp_manager.py` plus seven focused cases in `test_external_mcp_universal.py` for machine-readable MCP results.",
    "The tagged `v1.42.0` STM32er/prompt wave adds over one thousand lines to `stm32er.py`, expands config/registry/contracts/tools/tests/docs, and tracks the all-families proposal, migrations `0177`-`0179`, and `test_prompt_catalog_contiguous.py`.",
    "The clearer disclaimer commit for README.md and BookOfTlamatini.md is included in the `v1.42.0` ancestry; neither handbook is modified by this generation pass.",
    "The `v1.41.0` image-ingestion wave adds `chat_image_paste.js`, paste view/URL wiring, chat chip/drop-overlay template nodes, image CSS, layout observation, Temp-policy coverage, and matching README/Book/self-knowledge guidance.",
    "The `v1.41.2` cancellation wave adds `agent/cancellation.py`, `test_cancellation.py`, `test_ask_execs_allowlist.py`, expanded self-healing/frontend tests, and coordinated changes across consumers, executor, RAG, retry, permission, settings, and chat-state surfaces.",
    "Two browser regression harnesses under `.claude/skills/tlamatini-daily-chat-test/harness/` exercise repeated cancels, next-request recovery, model/tool-chain cancellation, Ask-Execs cancellation, and the destructive/human-contacting/network allowlist contract.",
    "The `v1.41.3` prompt-catalog wave adds migrations `0175`-`0176`, Prompt category/hidden fields, ordered category metadata in `views.py`, and grouped, gap-tolerant, fuzzy-searchable catalog behavior in `tools_dialog.js`/`.css`.",
    "The same prompt wave physically removes 13 duplicate ACPX rows while retaining seven portable originals and stable surviving ids; the primary endpoint and offline fallback both tolerate the resulting gap.",
    "`freeingport8000.ps1` is the new Windows repair asset for resetting dynamic ranges, restarting WinNAT, reporting exclusions, and bind-testing 8000; its machine-specific scratch path is deliberately excluded from generated prose.",
    "The committed Discoverer PDCP assets include `access_key_wizard.py` Security Recon fields, `tools.py` default seeding, `agent_contracts.py` `.flw` redaction, `regen_secrets.py` scrubbing, and migration `0169_add_discoverer_cvemap_latest_demo_prompt.py` for the latest-CVE prompt.",
    "Discoverer hardening assets now include `discoverer.py` changes for `cvemap` -> `vulnx`, `.gitignore` Go-deny patterns, tracked `git_deny_go.py` guard/pre-commit installer, `discoverer_1000.py`, and `test_discoverer_thousand.py` validation coverage.",
    "The project inventory is rebuilt from `git ls-files` plus `git ls-files --others --exclude-standard` on every run, so any git-unignored local assets are counted while ignored runtime caches such as `Go/` remain outside the dossier.",
    "The newest frontend assets include `agent_page_chat.js`, `agent_page_ui.js`, `eslint.config.mjs`, and the Claude frontend/Multi-Turn/recent-fixes notes that document self-healing status frames and Create Flow name resolution.",
    "The `v1.40.1` port assets span committed `manage.py`/`config.json`, source/startserver integration, the committed 24-test `agent/test_django_port_config.py` suite, version surfaces in `package.json`/`VERSIONING.md`, and operator contracts across README, Book, self-knowledge, prompt guidance, and `docs/claude`.",
    "The newest agent assets are concrete: `agent/agents/zavuerer/`, migrations `0159_add_zavuerer.py` through `0164_dedup_zavuerer_setup_wizards.py`, `test_zavuerer_agent.py`, Access Keys Wizard Zavu fields, planner capability hints, wrapped-tool registration, and ACP canvas styling/connection support.",
    "The latest cleanup/assets span also includes `GEMINI.md`, `FirstFinalPlanToSpeedUp.md`, `docs/claude/recent-fixes.md`, response-parser/runtime/settings/middleware touch-ups, and removal of the stale `Tlamatini/db.sqlite3.bak-prereseat` backup from the tracked surface.",
    "The same wave preserves evidence-oriented tests and build guards such as `test_private_data_guard.py`, performance/visual checks, About-window authorship tests, and public-release verification rules that distinguish sensitive PII from valid creator names.",
    "The same span refreshes shipped visual/media assets: `TlamatiniAbout.png` replaces the old `TlamatiniAbout.jpg`, and `agent/images/TlamatiniAndKyber.mp4` is part of the repository asset set described by the dossier.",
    "The same recent window also retains the earlier self-modify/browser-setup asset wave — `copy_source_assets.py`, `agent/access_key_wizard.py`, `static/agent/js/access_keys_wizard.js`, `static/agent/css/access_keys_wizard.css`, and the Blender control surface in `agent/agents/blenderer/`.",
    "Key operator/runtime files such as `prompt.pmt`, `chat_agent_registry.py`, `tools.py`, `views.py`, `urls.py`, `manage.py`, `file_extractor.py`, and the File-Creator/File-Extractor templates also changed, so the visible features are backed by concrete implementation assets rather than documentation-only promises.",
    "Because the dossier already includes the full repository inventory (git-tracked files plus git-unignored working-tree additions) and the full line-count inventory, these named assets serve as the human-readable shortlist of what changed most materially in the latest release wave.",
]

PROMPT_CATALOG_GUIDE = [
    "Version `1.3.2` tightened the HTML answer contract with a Prime Directive on visual readability: explicit background and text color, no grey-on-dark body text, and safer table-body defaults.",
    "The seeded `Prompts` dropdown was also re-sorted into a learner path: context-only Q&A first, then metrics, files search, shell, code generation, vision, specialized single-tool actions, agent control, Unrealer, and heavier Multi-Turn/ACPX demos last.",
    "The `v1.35.0` prompt-search pass then makes that larger catalog easier to operate: prompt cards support substring, word-start, and fuzzy matching, with mode badges that keep one-shot, Multi-Turn, ACPX, Exec Report, and Step-by-Step demos visually distinct.",
    "Those readability rules remain in force in the current release documentation set. PDF canvas/context and stricter build/update carriage join measured networking, WAL-safe database movement, resilient Googler discovery and guided MCP onboarding. Encoding-safe search, guarded execution truth, private MCP runtimes, document agents and ranked prompt search remain carried.",
]

SELF_KNOWLEDGE_GUIDE = [
    "Version `1.8.0` gives Tlamatini a first-person self-knowledge map in `Tlamatini/agent/Tlamatini.md`, so she can answer more accurately about her own architecture, runtime modes, open ports, pages, and internal capability surface.",
    "That self-reference is injected into all prompt chains through `prompt.pmt` and `agent/rag/config.py`, but it fails open if the file is missing or unreadable and it never overrides a user-loaded project when the request is a generic summary of the provided context.",
    "The language contract matters too: when a pronoun is used for Tlamatini in the documentation or prompt guidance, she is referred to as `she` / `her`, matching the updated handbook identity rules.",
]

SELF_MODIFY_GUIDE = [
    "Self-modification is a separate capability axis from frozen-vs-source runtime: only builds created with `python build.py --self-modify` bundle `TlamatiniSourceCode/` next to the application.",
    "When that directory is present, she can inspect and modify her own shipped source tree; when it is absent, she must say so plainly and fall back to her injected self-knowledge plus the surrounding docs.",
    "The build pipeline now announces that choice explicitly, so operators can tell whether a release is self-modify-capable before asking her to work on herself.",
]

MULTITURN_4096_GUIDE = [
    "The unified-agent loop now defaults to 4096 iterations instead of 256, giving long autonomous operator runs much more room before they exhaust the turn budget.",
    "That expansion is about conversational/tool-loop depth, not about blindly firing more tools at once: the planner’s selected-tool cap still keeps the tool surface bounded per request.",
    "Operationally, the bigger ceiling helps long workflows, while duplicate-call guards and the dedicated `chat_agent_sleeper` tool remain the antidote to accidental busy-polling loops.",
]

ASK_EXECS_GUIDE = [
    "Introduced in `v1.10.0` and still part of the current release, `Ask Execs` is the Multi-Turn-only safety modifier that makes Tlamatini ask before each state-changing Tool, MCP, wrapped agent, or skill-backed execution instead of running it immediately.",
    "The permission dialog is explicit and auditable: it names the Tool or Agent family, the underlying raw tool name, the full parameters, the program or command to be executed, and the shell or execution surface involved.",
    "Proceed runs that one step and then prompts again at the next state-changing step; Deny halts the entire chain immediately and appends a red `Execution interrupted` banner even when Exec Report itself is off.",
]

ASK_EXECS_PIPELINE_GUIDE = [
    "Under the hood, `agent/exec_permission.py` provides `ExecPermissionBroker`, which lets the synchronous worker-thread executor emit a permission request onto the WebSocket event loop and then block on a `threading.Event` until the browser replies.",
    "The gate sits after deduplication and quota checks, so skipped calls never prompt and denied calls never appear as executed rows; only work that truly ran lands in Exec Report.",
    "The round-trip is fail-safe: browser disconnect, emit failure, cancel, or broker shutdown all resolve to Deny, so an unconfirmed state-changing action never slips through just because the UI vanished at the wrong time.",
]

WINDOWS_ATTENTION_GUIDE = [
    "The current Windows attention path is explicit and local: the browser calls `POST /agent/flash_window/`, and the backend routes that request through `agent/window_flash.py`.",
    "That helper can flash the `Tlamatini.exe` console/taskbar window with `FlashWindowEx` and always prints an uppercase attention banner, so the signal survives in `tlamatini.log` even when the browser is minimized.",
    "Two concrete reasons are wired today: Ask Execs execution approval prompts and Notifier notifications. The path is best-effort and fail-safe, degrading cleanly on non-Windows or windowless launches.",
]

WINDOWS_APP_REGISTRATION_GUIDE = [
    "Introduced in `v1.11.0` and still carried by the current release, the frozen install behaves like a Windows application: `install.py` writes a per-user HKCU Add/Remove Programs entry so Tlamatini appears in Settings -> Apps -> Installed apps and in the legacy Programs and Features list.",
    "The entry carries `DisplayName`, `DisplayVersion`, `InstallLocation`, `DisplayIcon`, `UninstallString`, `QuietUninstallString`, `NoModify`, `NoRepair`, and best-effort `EstimatedSize`, all pointing at the bundled `Uninstaller.exe` without requiring administrator rights.",
    "The matching runtime self-heal in `agent/apps.py` calls `windows_app_registration.self_heal_for_frozen()` on every frozen launch, so installs created before this feature existed can appear in Windows' uninstall UI after the next normal app start.",
]

UNREAL_EXTENDED_GUIDE = [
    "Unrealer’s documentation now points at the public `XAIHT/XaihtUnrealEngineMCP` fork, the Unreal Engine MCP variant developed specifically for Tlamatini.",
    "That fork exposes the extended 53-command, nine-category surface documented in README and Book: not only the base editor/Blueprint/UMG verbs, but also system, level, asset, material, screenshot, viewport, and in-editor Python paths.",
    "The practical message for operators is simple: Unrealer forwards the connected plugin’s verb surface directly, so Tlamatini’s client does not need a new release every time the plugin adds another supported command.",
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
    "Carried into v1.65.4 from `v1.4.2`: Tkinter was removed from the unstable runtime-facing dialog path and replaced with `Tlamatini/agent/native_dialogs.py`, a native Windows dialog bridge used by browser-triggered pickers.",
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
    "Kalier is Tlamatini’s current Kali Linux bridge: a direct client for MCP-Kali-Server that lets her drive authorized recon, enumeration, web scanning, and offensive-security workflows from chat or canvas.",
    "It can issue one capability per run, including `nmap`, `gobuster`, `dirb`, `nikto`, `sqlmap`, `metasploit`, `hydra`, `john`, `wpscan`, `enum4linux`, arbitrary `command`, or a safe `health` probe of the remote server.",
    "The agent emits `INI_SECTION_KALIER` with `action`, `endpoint`, `subject`, `return_code`, `success`, `timed_out`, and `server_url`, so downstream Forker or Parametrizer logic can branch on results without scraping prose.",
    "The practical operator result is simpler prompts: after the Kali box URL is configured once, normal Multi-Turn requests no longer repeat `server_url` unless you intentionally override it for a one-off target.",
]

KALIER_SURFACES_GUIDE = [
    "Two operator surfaces ship in lock-step: the wrapped Multi-Turn tool `chat_agent_kalier` now auto-injects the configured `kali_server_url`, while the visual Kalier canvas node still stores `server_url` explicitly in YAML per node.",
    "Kalier talks straight to the Kali-side Flask API over HTTP using Python-stdlib `urllib`, so it stays self-contained in the pool subprocess and works the same in source or frozen builds; the embedded-client injection fails open if the config value is blank or unreadable.",
    "Authorized use only: the intended operator flow is an in-scope lab, CTF, or permitted engagement, often with `ssh -L 5000:localhost:5000 user@KALI_IP` tunneling a remote Kali box back to `http://127.0.0.1:5000`, and the repo now includes `Tlamatini-Kali-Setup.md` for the zero-client walkthrough.",
]

STM32ER_GUIDE = [
    "STM32er is Tlamatini's critical-mission STM32 bridge. The established route talks to the `STM32 Template Project MCP` for STM32F407, while released `v1.42.0` adds a direct PlatformIO route for supported mainstream STM32 boards without removing that flow.",
    "Both backends keep zero-config intent: the template route bootstraps its MCP dependencies, and the new route resolves or installs PlatformIO Core in the same shared per-user location used by ESP32er.",
    "Backend-specific preflight preserves target safety: compile-only work may proceed without attached hardware, but upload, reset, serial, and live operations are refused when the required toolchain, project, board mapping, programmer, or ST-LINK evidence is missing.",
]

STM32ER_SURFACES_GUIDE = [
    "Two operator surfaces ship in lock-step: the wrapped Multi-Turn tool `chat_agent_stm32er` takes one `action` per call, while the visual STM32er canvas node stores the same fields in YAML and triggers downstream agents on both success and failure.",
    "The tool surface retains the 23 MCP verbs and locally adds PlatformIO environment, board, project, source, build, flash, monitor, package, QA, artifact, and safe scaffold composites; every run still emits one `INI_SECTION_STM32ER` block for routing.",
    "Config seeding supplies both MCP and PlatformIO defaults, while `stm32_backend=auto`, `board`, and `device` keep the normal prompt focused on firmware intent. Newest-silicon CubeCLT/N6 handling remains proposal-only and is not advertised as implemented.",
]

ESP32ER_GUIDE = [
    "ESP32er is Tlamatini’s current PlatformIO Core bridge: she can scaffold, author, build, upload, and monitor ESP32-class firmware without relying on an external MCP server or IDE.",
    "The operator promise is zero-config bootstrap: leave `pio_executable` blank and ESP32er downloads or pip-falls-back to PlatformIO Core on first use, validates it, and caches it under a per-user directory so the user installs only the board USB driver plus Tlamatini.",
    "Before any build-or-upload action, ESP32er runs a serial-aware preflight over `pio` resolution, project shape, and connected ports; upload and monitor require a real serial device, while non-espressif32 targets are warned about rather than hard-refused because PlatformIO is intentionally multi-target.",
]

ESP32ER_SURFACES_GUIDE = [
    "Two operator surfaces ship in lock-step: the wrapped Multi-Turn tool `chat_agent_esp32er` takes one `action` per call, while the visual ESP32er canvas node stores the same fields in YAML and triggers downstream agents on both success and failure.",
    "The tool surface covers environment/meta (`bootstrap`, `validate`, `system_info`, `boards`), project lifecycle (`create_project`, `write_source`, `read_source`, `list_sources`, `clean`), build and flash (`build`, `upload`, `build_and_upload`, `list_artifacts`), serial HIL (`device_list`, `monitor`, `monitor_session`), and package / QA paths (`pkg_install`, `pkg_list`, `pkg_update`, `check`, `test`), with every run emitting an `INI_SECTION_ESP32ER` block for Forker or Parametrizer routing.",
    "Config -> URLs now seeds the chat path with `pio_executable` and `pio_core_dir`, so firmware prompts usually describe only the board, project, and task while the wrapped tool auto-injects the PlatformIO runtime plumbing.",
]

ESP32_TEMPLATE_GUIDE = [
    "ESP32er now ships ESP32TemplateProject inside its agent directory. create_project copies its PlatformIO project and stamps the requested board/framework. The blink-and-print main.cpp supplies setup/loop for an Arduino build.",
    "Six tracked files include platformio.ini, src/main.cpp and README files for the root/include/lib/test directories. The narrow Git exception retains lib/README.md. No standalone GitHub repository or CI publication is implied by this bundled tree.",
    "Use a new project_dir, then build and inspect the result before upload/monitor. The copy merges with an existing destination and may overwrite matching template files. If the bundle is unavailable, pio project init falls back to minimal source when appropriate.",
]

ESPHOMER_GUIDE = [
    "ESPHomer is Tlamatini’s ESPHome bridge: she can author YAML-based smart-home device configs, validate them, compile firmware, upload over USB or OTA, and observe logs without introducing an extra MCP server or IDE.",
    "The operator promise is zero-config bootstrap: leave `esphome_executable` blank and ESPHomer installs or resolves ESPHome on first use, so the user installs only the board USB driver plus Tlamatini.",
    "Before any compile-or-upload action, ESPHomer runs a fail-safe preflight over `esphome` resolution, YAML existence, and serial-or-OTA readiness; upload, run, and logs require a real serial board or an OTA host because the first flash is always USB.",
]

ESPHOMER_SURFACES_GUIDE = [
    "Two operator surfaces ship in lock-step: the wrapped Multi-Turn tool `chat_agent_esphomer` takes one `action` per call, while the visual ESPHomer canvas node stores the same fields in YAML and triggers downstream agents on both success and failure.",
    "The tool surface covers environment/meta (`bootstrap`, `validate`, `version`), device-YAML lifecycle (`new_config`, `write_config`, `read_config`, `config`, `clean`), build and flash (`compile`, `upload`, `run`, `list_artifacts`), bounded observation (`logs`), and the one-shot `scaffold_compile_upload` lifecycle.",
    "Config -> URLs now seeds the chat path with `esphome_executable`, so smart-home firmware prompts usually describe only the device, board, and task while the wrapped tool auto-injects the ESPHome runtime plumbing.",
]

ESPHOME_TEMPLATE_GUIDE = [
    "ESPHomer's scaffold_template now copies the complete bundled ESPHomeTemplateProject into project_dir. It contains the light, a sensor example, common/base.yaml, placeholder secrets.yaml.example and a project .gitignore.",
    "new_config remains a separate single-device generator. use_secrets=true emits !secret references and creates a sibling secrets.yaml only when one does not already exist. Keep actual credentials outside Git and inspect the generated device YAML before compilation.",
    "Use a new destination for scaffold_template because its merge can replace matching template files. Validate configuration before compile/upload. A real board, USB driver and later OTA setup remain necessary for hardware verification, which was not performed in this refresh.",
]

DESIGN_PRINCIPLES = [
    "Evidence-first answers: Tlamatini grounds responses in selected project context and hybrid retrieval rather than freeform model memory.",
    "Explicit orchestration: checked Multi-Turn uses a visible tool loop, capability scoring, and staged planning instead of a single opaque call.",
    "Operational reversibility: risky changes such as database replacement are staged, archived, and delayed to the only safe window instead of hot-swapped mid-session.",
    "Fail-open diagnostics: GPU pressure probes and session-restore safeguards warn early without breaking CPU-only or degraded environments.",
    "Runtime isolation: wrapped chat-agent copies run in session-scoped folders so template agents remain pristine while live runs stay inspectable.",
    "Self-knowledge with scope discipline: she can talk accurately about herself without letting self-reference override a user-loaded project context.",
    "Operator truth over vibes: Exec Report tables, tlamatini.log, skill audits, and ACPX transcripts make the system auditable after execution.",
]

INSTALLATION_GUIDE = [
    "The easiest path for most users is the packaged installer from GitHub Releases: no manual Python install is required because the release already carries Python 3.12.10 and the project dependencies.",
    "For Tlamatini's complete intended cloud-model workload, activate Ollama Pro or a higher plan such as Max and sign in with the Ollama CLI. Free/local-only operation is a limited compatibility path, not the documented full-workload baseline; verify current plan pricing and limits on Ollama's official site.",
    "Source mode remains the developer path: clone the repo, create a virtual environment, install `requirements.txt`, run migrations, create a superuser, collect static files, and then launch Django.",
    "Packaged Windows installs open the browser at `http://127.0.0.1:8000/` and create the default `user / changeme` login; manual source installs use your own `createsuperuser` account instead.",
    "Port 8000 is only the default: `config.json`'s `django_port` moves the web UI to any free port on every launch path, which is the fix when Windows or Hyper-V has RESERVED port 8000 and startup fails with `WinError 10013`.",
    "When a newer packaged release exists, the intended upgrade path is in-app: `About -> Check for updates`, not manual folder replacement.",
    "You can run either the checked-in cloud/back-end defaults from `Tlamatini/agent/config.json` or a local/remote Ollama-backed configuration with matching model names.",
]

CONFIGURATION_GUIDE = [
    "Source mode resolves `Tlamatini/agent/config.json`; frozen builds resolve `config.json` next to the executable; `CONFIG_PATH` overrides both.",
    "Core keys include `embeding-model`, `chained-model`, `ollama_base_url`, `ollama_token`, `enable_unified_agent`, `unified_agent_model`, and `unified_agent_max_iterations`.",
    "Ollama defaults are `ollama_repeat_penalty=1.2`, `ollama_repeat_last_n=256` and `ollama_num_ctx=1048576`. Both factory chains and the ChatOllama adapter carry them. The dedicated sampler section separates source behavior from the September 13 commit measurements and explains the local-model memory caveat. Keep new sampler keys aligned across both chains, adapter forwarding and the `[LLM-PARAMS]` banner.",
    "The checked-in default model baseline moved again in the recent Git window: the shared config now favors `glm-5.3:cloud`, so source or frozen installs that keep the shipped config should be documented as cloud-first unless the operator intentionally swaps models.",
    "URL configuration now also includes `kali_server_url`, the STM32er bootstrap fields `stm32_mcp_server_script`, `stm32_mcp_python`, `stm32_template_dir`, `stm32_ide_root`, `stm32_mcp_repo_url`, and `stm32_mcp_install_dir`, plus ESP32er’s `pio_executable` and `pio_core_dir`, all edited from `Config -> URLs` and inherited automatically by the chat-side wrapped tools.",
    "Credential configuration is no longer hand-edit-only: Config -> Access Keys Wizard provides a browser-side path for ACPX, provider secrets, unified messaging, and Security Recon (ProjectDiscovery) keys such as `pdcp_api_key` while preserving masked status in the UI.",
    "The chat-side Config -> Models and Config -> URLs dialogs are now first-class configuration surfaces, and they can explicitly ask the operator to reconnect when saved values change live-session assumptions.",
    "The separate DB dropdown is not a config editor: it is a maintenance surface for copying the live SQLite database out or staging a replacement for the next full start-up.",
    "Multi-Turn is toggled from the chat toolbar, but it depends on the unified-agent configuration and the selected model/base-url pairing being valid; the current default iteration ceiling is 4096, and Ask Execs only becomes available when Multi-Turn itself is on.",
    "Image-Interpreter now uses three model slots from Config -> Models: `image_interpreter_model` for the first forensic interpreter, `image_interpreter_model_2` for the second holistic interpreter, and `image_merging_model` for the final report merger.",
]

START_HERE_GUIDE = [
    "BookOfTlamatini now leads with a five-step onboarding path because the easiest way to succeed with Tlamatini is to treat setup as one guided sequence instead of reading the whole handbook first.",
    "Recommended path for most operators: install the packaged release from GitHub Releases, launch the Start-menu shortcut, and let the bundled Python 3.12.10 plus dependencies carry the runtime without asking the user to install Python manually.",
    "Developer path stays available: clone the repo, create a virtual environment, install `requirements.txt`, run migrations, and start Django with `python Tlamatini/manage.py runserver` (the `--noreload` flag is optional since 2026-07-11 — plain `runserver` now boots clean and auto-reloads).",
    "Before pulling the shipped `:cloud` model tags, activate Ollama Pro or higher and run `ollama signin`; this is an operating requirement for the complete intended workload, not a sponsorship or affiliate relationship.",
    "After the app opens, the first in-app surfaces that matter are `Config -> Models`, `Config -> URLs`, and `Config -> Access Keys Wizard`; those now form the real beginner path, not manual JSON editing.",
    "For ordinary question-answering keep Multi-Turn off; turn it on only when you want Tlamatini to execute tools, wrapped agents, or remote MCP capabilities instead of answering directly.",
]

FIRST_RUN_CONFIG_GUIDE = [
    "The first-run path is Config > Models, URLs and Access Keys Wizard. Historical screenshots may show older menus; docs/model_configuration.md describes the current six-category Models dialog.",
    "Config > Models has 38 fields for embedding, reasoning, vision, speech, workflows, documents and monitors. Ollama catalog choices, local speech names, provider IDs and engine/voice selectors have distinct validation.",
    "`Config -> Access Keys Wizard` now carries an especially important rule: a localhost Ollama usually needs no Ollama token, while a remote Ollama endpoint may require one.",
    "Saved model, URL, or credential changes can invalidate the assumptions of the current session, so reconnecting after major Config edits is now part of the honest operator guidance.",
]

RUNNING_GUIDE = [
    "Development server: `python Tlamatini/manage.py runserver` — the `--noreload` flag is now OPTIONAL (plain `runserver` boots clean and auto-reloads since the 2026-07-11 `agent/apps.py` reloader-aware fix; it used to double-start the MCP helper ports :8765 / :50051 and crash with WinError 10048).",
    "Preferred async/dev bootstrap: `python Tlamatini/manage.py startserver`, which starts MCP services before the Django server.",
    "Production-style ASGI entrypoint: `daphne -b 127.0.0.1 -p 8000 tlamatini.asgi:application` — this path bypasses `manage.py`, so it does not read `django_port` and the port must be passed on the command line.",
    "Current startup also re-applies GPU-performance / Ollama-pinning hooks in the background on supported NVIDIA Windows hosts, so restart-time behavior stays closer to the tuned development baseline.",
    "That same early startup window is also where a staged `DB/ToLoad/db.sqlite3` file is promoted into the live database path, before Django opens SQLite.",
    "In frozen mode, startup now also self-heals the per-user Windows Installed-apps entry when `Uninstaller.exe` is present beside `Tlamatini.exe`, so old installs can gain a standard uninstall surface without a reinstall.",
    "Startup now also prints a `--- [VERSION] Tlamatini ...` banner, making the running build visible in both the console and `tlamatini.log` without an HTTP call.",
    "Startup cleans pool state, repopulates the agent registry, launches MCP metrics/file-search servers, and then serves HTTP plus WebSocket traffic.",
]

DB_MENU_GUIDE = [
    "The DB dropdown gives operators two GUI-first maintenance paths: `Backup database` creates a WAL-consistent verified snapshot, and `Set DB` stages a WAL-consistent chosen database for the next full start-up.",
    "Both dialogs are live-validated in the browser and now expose Browse buttons that open native host-side pickers for folders or `db.sqlite3` files.",
    "Both paths use `sqlite_copy.consistent_copy()`: SQLite's online backup API reads through committed WAL pages, the destination switches to DELETE journal mode, and `PRAGMA quick_check` must pass before success. Set DB never hot-swaps mid-session because Django already holds SQLite open.",
]

DB_SWAP_GUIDE = [
    "Set DB writes a verified self-contained copy to `DB/ToLoad/db.sqlite3`; the real swap happens only at the top of `manage.py` before Django imports anything.",
    "When that swap runs, the previous live database and its `-wal`/`-shm`/`-journal` family move into `DB/Older/<timestamp>/`, creating a rollback trail instead of overwriting history.",
    "Stale sidecars beside the destination are removed before promotion so SQLite can never replay pages belonging to the previous database over the newly selected file.",
    "Reconnect is not enough for this path: the operator must fully restart Tlamatini so the pre-Django swap window opens again.",
    "Copy verification is fail-safe: an unreadable, inconsistent, or unchecked result is reported as failure rather than called a backup. Startup preserves the previous live database if promotion cannot complete safely.",
]

VERSIONING_GUIDE = [
    "Tlamatini now follows Semantic Versioning 2.0.0 with git tags as the single source of truth: you tag, then you build, instead of hand-editing version strings across files.",
    "The build path resolves a version once and propagates it into generated runtime metadata, Win32 VERSIONINFO resources, and the release-folder naming convention.",
    release_identity(),
]

VERSION_SURFACES_GUIDE = [
    "Operators can now see the running version in the About dialog, the startup banner, the open `GET /agent/version/` health-check endpoint, and Windows file properties on the built executables.",
    "Packaged installs also project the same release identity into Windows' Installed-apps metadata through the ARP `DisplayVersion` field, so the uninstall surface and the binaries agree on the version being removed.",
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
    "The Unrealer workflow agent forwards any command the connected plugin build exposes, up to a 53-command surface across nine categories: actor manipulation (incl. viewport screenshots), Blueprint authoring and node wiring, input mappings, UMG widget building, in-editor Python/console execution, level I/O, asset import, and material authoring. Headless build/cook/test is out of scope (it needs UnrealEditor-Cmd, not the editor socket).",
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
    "Browser-driven attention routing is now part of that operator-safety layer too: Ask Execs prompts and Notifier events can raise a taskbar flash plus a log banner without relying on the browser window already being visible.",
    "Windows process hygiene is now part of that safety story too: detached no-window spawns and the three-tier orphan reaper reduce the chance that Task Manager shows stale Tlamatini-icon console helpers after long runs.",
    "Ask Execs extends that safety story into execution approval itself: the operator can now stop a destructive chain before the next mutation instead of only auditing it after the fact in Exec Report.",
]

RELEASE_GUIDE = [
    "Release production is a three-step pipeline: `build.py` -> `build_uninstaller.py` -> `build_installer.py`.",
    "The final distributable is the full versioned release folder `dist/Tlamatini_Release_v<version>/`, not a stray executable copied outside its payload.",
    "Use `build.py --self-modify` when you intentionally want a release that ships `TlamatiniSourceCode/` so she can inspect or modify herself at runtime.",
    "Current `build.py` treats `README.md` and `jd-cli/` as required post-build assets and fails hard if those payloads are missing.",
    "Bundled support scripts cover shortcut creation/removal, `.flw` association, the PowerShell launcher, Windows-specific installer ergonomics, and the per-user Installed-apps registration path.",
]

EXEC_REPORT_GUIDE = [
    "Exec Report is a Multi-Turn-only transparency layer that appends operation tables for every wrapped agent family, including observational and read-only agents; `_EXEC_REPORT_TOOLS` only refines grouping and style.",
    "Rows are recorded from the live tool-call stream rather than guessed from the LLM prose, so the report is the operational ground truth.",
    "Each row receives a deterministic SUCCESS/FAILURE verdict from the agent's structured self-report: completed diagnostics and intact work are green, while degraded, not-done, and agent-error statuses are red under the guarded five-class vocabulary.",
    "When Ask Execs is enabled, Exec Report and the red denial banner complement each other: already-executed steps still render as tables, while the denied step stays out of the tables and is surfaced only through the interruption banner.",
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
        "ollama signin",
        "ollama serve",
        "Invoke-WebRequest http://127.0.0.1:11434/api/tags -UseBasicParsing",
        "ollama pull Nomic-Embed-Text:latest",
        "ollama pull glm-5.3:cloud",
        "ollama pull jcyhsiao/qwen3.5cloud:latest",
        "ollama pull gemma4:cloud",
    ]
)

OLLAMA_GUIDE = [
    "Open a normal PowerShell window, not an elevated one, for the safest no-admin Windows installation path.",
    "Install into `%LOCALAPPDATA%\\Programs\\Ollama` with the official PowerShell installer script and then reopen PowerShell so PATH updates are visible.",
    "Activate Ollama Pro or a higher plan such as Max for Tlamatini's complete intended functionality, then run `ollama signin` so the host is linked before using the shipped `:cloud` defaults. This requirement is not a sponsorship; verify current plan details directly with Ollama.",
    "Verify the CLI with `ollama --version`, start `ollama serve` if the background service is not already active, and confirm `http://127.0.0.1:11434/api/tags` responds.",
    "Pull the default repository model tags exactly as written if you want the shipped config and agent templates to work unchanged.",
    "The Book now clarifies the token rule: a localhost Ollama usually needs no Ollama bearer token in Tlamatini, while a remote Ollama endpoint may require one in `Config -> Access Keys Wizard` or the matching config key.",
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
    ("Execution and files", "executer, pythonxer, pser, file_creator, file_extractor, file_interpreter, de_compresser, playwrighter, windower, unrealer, kalier, stm32er, esp32er, esphomer, arduiner, mover, deleter"),
    ("DevOps and infra", "gitter, dockerer, kuberneter, jenkinser, ssher, scper"),
    ("Data and APIs", "sqler, mongoxer, apirer, crawler, googler"),
    ("Monitoring and routing", "monitor_log, monitor_netstat, flowhypervisor, forker, asker, counter, and, or"),
    ("Communication", "notifier, emailer, recmailer, telegrammer, teletlamatini, whatsapper"),
    ("Security and media", "kyber_keygen, kyber_cipher, kyber_decipher, image_interpreter, video_analyzer, shoter, camcorder, recorder, audioplayer, videoplayer, j_decompiler"),
    ("Workflow intelligence", "flowcreator, gatewayer, gateway_relayer, node_manager, parametrizer, prompter, summarizer, acpxer"),
]


def pdf_styles() -> dict[str, ParagraphStyle]:
    # Embed Unicode fonts so names and punctuation survive rendering/extraction.
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name, filename in (("DossierSans", "arial.ttf"),
                           ("DossierSans-Bold", "arialbd.ttf"),
                           ("DossierMono", "consola.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TlamatiniTitle",
            parent=base["Title"],
            alignment=TA_CENTER,
            fontName="DossierSans-Bold",
            fontSize=28,
            leading=34,
            textColor=colors.HexColor("#17342d"),
            spaceAfter=14,
        ),
        "subtitle": ParagraphStyle(
            "TlamatiniSubtitle",
            parent=base["Normal"],
            alignment=TA_CENTER,
            fontName="DossierSans",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#6b4a34"),
            spaceAfter=20,
        ),
        "h1": ParagraphStyle(
            "TlamatiniH1",
            parent=base["Heading1"],
            keepWithNext=True,
            fontName="DossierSans-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f3b31"),
            spaceBefore=14,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "TlamatiniH2",
            parent=base["Heading2"],
            keepWithNext=True,
            fontName="DossierSans-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#8f5c35"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "TlamatiniBody",
            parent=base["BodyText"],
            fontName="DossierSans",
            fontSize=9.5,
            leading=12.5,
            textColor=colors.HexColor("#1f2933"),
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "TlamatiniBullet",
            parent=base["BodyText"],
            fontName="DossierSans",
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
            fontName="DossierMono",
            fontSize=6.7,
            leading=7.7,
            textColor=colors.HexColor("#17231f"),
        ),
    }


def p(text: str, style: ParagraphStyle) -> Paragraph:
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe.replace("&lt;br/&gt;", "<br/>"), style)


def bullet(text: str, style: ParagraphStyle) -> Paragraph:
    return p(f"- {text}", style)


def _table_cell(text: str, font_size: float, *, header: bool) -> Paragraph:
    """Wrap a string cell in a Paragraph so ReportLab word-wraps it inside the
    column width instead of letting a long single-line string overflow the page.
    Long unbreakable tokens (e.g. deep slash-paths) are force-split by
    Paragraph's default splitLongWords behavior."""
    style = ParagraphStyle(
        "TableHeaderCell" if header else "TableBodyCell",
        fontName="DossierSans-Bold" if header else "DossierSans",
        fontSize=font_size,
        leading=font_size + 2,
        textColor=colors.white if header else colors.HexColor("#1f2933"),
    )
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe, style)


def table(data: list[list], widths: list[float] | None = None, font_size: int = 8) -> Table:
    # Cells are wrapped in Paragraphs (the only flowable that word-wraps within a
    # column). Plain string cells passed straight to Table render on a single
    # line and overflow narrow columns; Paragraphs wrap to the column width.
    wrapped = [
        [
            _table_cell(cell, font_size, header=(row_index == 0)) if isinstance(cell, str) else cell
            for cell in row
        ]
        for row_index, row in enumerate(data)
    ]
    tbl = Table(wrapped, colWidths=widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17342d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "DossierSans-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "DossierSans"),
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
    canvas.setFont("DossierSans", 7)
    canvas.drawString(doc.leftMargin, 0.32 * inch, "Tlamatini complete project dossier")
    canvas.drawRightString(A4[0] - doc.rightMargin, 0.32 * inch, f"Page {doc.page}")
    canvas.restoreState()


def cover_image_flowable(image_path: Path, max_width: float, max_height: float) -> Image:
    """Return a reportlab Image scaled to fit WITHIN ``max_width`` x ``max_height``
    (points) while PRESERVING the source image's natural aspect ratio — so the
    cover is letter-boxed, never stretched. Falls back to the box size if the
    image's dimensions cannot be read."""
    try:
        src_w, src_h = ImageReader(str(image_path)).getSize()
    except Exception:
        src_w = src_h = 0
    if src_w <= 0 or src_h <= 0:
        img = Image(str(image_path), width=max_width, height=max_height)
    else:
        scale = min(max_width / src_w, max_height / src_h)
        img = Image(str(image_path), width=src_w * scale, height=src_h * scale)
    img.hAlign = "CENTER"
    return img


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
        author="Angela López Mendoza",
    )
    story: list = []

    cover_image = context["reference_media"][0] if context["reference_media"] else REPO_ROOT / "Tlamatini.jpg"
    story.append(p("TLAMATINI", styles["title"]))
    story.append(
        p(
            "Complete Project Dossier: what the system does, how it works, how to use Tlamatini, complete repository file tree, and effective line inventory<br/>Created by Angela López Mendoza · @angelahack1",
            styles["subtitle"],
        )
    )
    if cover_image.exists():
        try:
            story.append(cover_image_flowable(cover_image, 6.8 * inch, 3.8 * inch))
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
                ["Repository inventory files", str(context["inventory_files"])],
                ["Tracked files", str(context["tracked_files"])],
                ["Git-unignored working-tree additions", str(context["untracked_files"])],
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
    story.append(p("Agent-directory disclaimer: user jurisdiction and responsibility", styles["h2"]))
    for item in AGENT_DIRECTORY_DISCLAIMER:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Enable Tlamatini as a Blue-hat agent", styles["h2"]))
    for item in BLUE_HAT_SECURITY_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("What the system does", styles["h2"]))
    for item in WHAT_IT_DOES:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("How it works", styles["h2"]))
    for item in HOW_IT_WORKS:
        story.append(bullet(item, styles["bullet"]))
    story.append(CondPageBreak(4 * inch))

    story.append(p("2. Architecture Layers", styles["h1"]))
    arch_rows = [["Layer", "Role"]] + [[layer, desc] for layer, desc in ARCHITECTURE_LAYERS]
    story.append(table(arch_rows, widths=[1.75 * inch, 5.0 * inch], font_size=8))
    story.append(p("Design principles", styles["h2"]))
    for item in DESIGN_PRINCIPLES:
        story.append(bullet(item, styles["bullet"]))
    story.append(PageBreak())

    story.append(p("3. Installation, Configuration, and Everyday Use", styles["h1"]))
    story.append(p("Start here - the easiest path", styles["h2"]))
    for item in START_HERE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Installation essentials", styles["h2"]))
    for item in INSTALLATION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("First configuration screens", styles["h2"]))
    for item in FIRST_RUN_CONFIG_GUIDE:
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
    story.append(p(f"Current release focus in {context['version_info']['version']}", styles["h2"]))
    for item in CURRENT_RELEASE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("NetSpeed-Calculator measurement and safety contract", styles["h2"]))
    for item in NETSPEED_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Googler structured search, file discovery, and responsibility boundary", styles["h2"]))
    for item in GOOGLER_DORK_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Googler plain-HTTP-first and browser-fallback search resilience", styles["h2"]))
    for item in GOOGLER_RESILIENCE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("WAL-safe SQLite backup, staging, and hot-swap", styles["h2"]))
    for item in WAL_SAFE_DB_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("External MCP onboarding, deep research, and private-build boundaries", styles["h2"]))
    for item in MCP_RESEARCH_PRIVACY_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Recent implementation assets and inventory impact", styles["h2"]))
    for item in publication_guide(context):
        story.append(bullet(item, styles["bullet"]))
    for title, guide in (("Central model configuration", MODEL_CONFIGURATION_GUIDE),
                         ("Model compatibility and partial video coverage", MODEL_COMPATIBILITY_GUIDE),
                         ("Source and frozen model runtime", MODEL_RUNTIME_GUIDE),
                         ("Current video analysis and MCP changes", LATEST_SOURCE_GUIDE),
                         ("Latest defaults and prompt migrations 0205/0206", LATEST_DEFAULTS_GUIDE),
                         ("PDF canvas reading and file lifecycle", PDF_CANVAS_GUIDE),
                         ("Whole-document PDF context", PDF_CONTEXT_GUIDE),
                         ("PDF progress, cancellation and evidence", PDF_PROGRESS_GUIDE),
                         ("PDF distribution and tracked Git assets", pdf_distribution_guide(context)),
                         ("Local frontend and 1.99 GB release gate", LOCAL_RELEASE_GUIDE),
                         ("Self-modify and self-update carriage", SELF_CARRIAGE_GUIDE),
                         ("Document-agent result and repair contracts", DOCUMENT_CONTRACT_GUIDE),
                         ("PPTXer editable presentations", PPTXER_GUIDE),
                         ("PDFer signature styles", PDFER_STYLES_GUIDE),
                         ("LaTeXer signature styles", LATEXER_STYLES_GUIDE),
                         ("Desktop input and capture contracts", DESKTOP_INPUT_GUIDE),
                         ("Flow planning and mapping contracts", FLOW_CONTRACT_GUIDE),
                         ("Canvas avatar presence", AVATAR_GUIDE),
                         ("Reproducible visible avatar tests", AVATAR_TEST_GUIDE),
                         ("Whisperer silence gate", WHISPERER_GATE_GUIDE),
                         ("Voice Commands catalog and execution", VOICE_COMMAND_GUIDE),
                         ("Grepper line reading and encoded text transport", GREPPER_LINES_GUIDE),
                         ("Ollama sampler defaults and recorded measurements", OLLAMA_SAMPLER_GUIDE),
                         ("Uninstaller process gate and content preservation", UNINSTALLER_SAFETY_GUIDE),
                         ("Wrapped-agent wait and completion", WRAPPED_WAIT_GUIDE),
                         ("Standalone Ollama account-usage utility", OLLAMA_USAGE_GUIDE),
                         ("Committed Gitter Windows-path repair", GITTER_WORKTREE_GUIDE)):
        story.append(p(title, styles["h2"]))
        for item in guide:
            story.append(bullet(item, styles["bullet"]))
    story.append(p("Complete model setting reference", styles["h2"]))
    story.append(p("Defaults below come from the public registry, not private operator configuration. "
                   "Missing dedicated workflow/document/monitor settings fall back to unified_agent_model. "
                   "Optional blank cloud speech selects the provider default; optional blank LaTeXer disables repair. "
                   "See docs/model_configuration.md for precedence, validation and credentials.", styles["body"]))
    for group, fields in model_reference_groups().items():
        story.append(CondPageBreak(1.5 * inch))
        story.append(p(group, styles["h2"]))
        rows = [["Global key", "Agent YAML path", "Default / kind"]]
        for field in fields:
            path = f"{field['agent']}.{field['path']}" if field["agent"] else "In-process service"
            rows.append([field["key"], path,
                         f"{field['default'] or '(empty)'} / {field['kind']}"])
        story.append(table(rows, widths=[2.3 * inch, 2.35 * inch, 2.1 * inch], font_size=7))
    story.append(p("v1.41.4 External-MCP structured output", styles["h2"]))
    for item in STRUCTURED_CONTENT_1414_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.42.0 STM32er PlatformIO expansion", styles["h2"]))
    for item in STM32ER_PLATFORMIO_WORKTREE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.42.0 stepwise STM32 camera-verification demos", styles["h2"]))
    for item in STM32ER_STEPWISE_DEMOS_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.42.0 category-grouped prompt catalog with no gaps", styles["h2"]))
    for item in PROMPT_CATALOG_WORKTREE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.41.3 categorized and deduplicated prompt catalog", styles["h2"]))
    for item in PROMPT_CATALOG_1413_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.41.2 per-user Hard Cancel", styles["h2"]))
    for item in HARD_CANCEL_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.41.0 screenshot paste and image drop", styles["h2"]))
    for item in CHAT_IMAGE_1410_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.40.1 configurable web port", styles["h2"]))
    for item in DJANGO_PORT_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Tlamatini-FlowPills companion discovery", styles["h2"]))
    for item in FLOWPILLS_DISCOVERY_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Unreal Engine 5.8 one-prompt scaffold", styles["h2"]))
    for item in UNREAL_SCAFFOLD_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.39.5 responsiveness and safety hardening", styles["h2"]))
    for item in RESPONSIVENESS_HARDENING_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Nmapper local nmap bridge", styles["h2"]))
    for item in NMAPPER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Startup dialog and prompt-catalog polish", styles["h2"]))
    for item in STARTUP_PROMPT_POLISH_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.38.0 robotic loop closure", styles["h2"]))
    for item in ROBOTIC_LOOP_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.38.1 frontend-state recovery hotfix", styles["h2"]))
    for item in FRONTEND_HOTFIX_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Post-v1.36.0 self-healing Multi-Turn reliability", styles["h2"]))
    for item in SELF_HEALING_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Create Flow and Exec Report gating", styles["h2"]))
    for item in CREATE_FLOW_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Frontend recovery controls and Create Flow name resolution", styles["h2"]))
    for item in FRONTEND_RECOVERY_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Discoverer PDCP key integration", styles["h2"]))
    for item in DISCOVERER_PDCP_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Discoverer vulnx and Go-toolchain Git-deny guard", styles["h2"]))
    for item in DISCOVERER_VULNX_GO_GUARD_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.36.0 Video-Analyzer release delta", styles["h2"]))
    for item in V136_RELEASE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Video-Analyzer: robotics, transcription and summaries", styles["h2"]))
    for item in VIDEO_ANALYZER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Prompt search and generated .flw layout", styles["h2"]))
    for item in PROMPT_SEARCH_AND_FLOW_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("v1.33.2 Zavuerer release delta", styles["h2"]))
    for item in V1332_RELEASE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Zavuerer unified-messaging agent", styles["h2"]))
    for item in ZAVUERER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Image-Interpreter triple-model vision pipeline", styles["h2"]))
    for item in IMAGE_INTERPRETER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("External MCP universal client", styles["h2"]))
    for item in EXTERNAL_MCPS_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("MCP Doctor agent and wrapped tool", styles["h2"]))
    for item in MCP_DOCTOR_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("External MCP implementation assets", styles["h2"]))
    for item in EXTERNAL_MCP_ASSETS_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Blenderer", styles["h2"]))
    for item in BLENDERER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("In-app self-update", styles["h2"]))
    for item in SELF_UPDATE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Self-modify source snapshot", styles["h2"]))
    for item in SOURCE_SNAPSHOT_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("API-Keys Wizard", styles["h2"]))
    for item in API_KEYS_WIZARD_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Earlier implementation assets retained in the current tree", styles["h2"]))
    for item in NEW_ASSETS_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("File-Creator hardening", styles["h2"]))
    for item in FILE_CREATOR_HARDENING_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Self-knowledge and identity contract", styles["h2"]))
    for item in SELF_KNOWLEDGE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Self-modify builds", styles["h2"]))
    for item in SELF_MODIFY_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Multi-Turn 4096-turn autonomy", styles["h2"]))
    for item in MULTITURN_4096_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Ask Execs in Multi-Turn", styles["h2"]))
    for item in ASK_EXECS_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Ask Execs runtime path", styles["h2"]))
    for item in ASK_EXECS_PIPELINE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Windows attention issuing", styles["h2"]))
    for item in WINDOWS_ATTENTION_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Windows Installed-apps registration", styles["h2"]))
    for item in WINDOWS_APP_REGISTRATION_GUIDE:
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
    story.append(p("Extended Unreal MCP surface", styles["h2"]))
    for item in UNREAL_EXTENDED_GUIDE:
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
    for item in operator_surface_counts_guide(context):
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Kalier current role", styles["h2"]))
    for item in KALIER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    for item in KALIER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("STM32er current role", styles["h2"]))
    for item in STM32ER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    for item in STM32ER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("ESP32er current role", styles["h2"]))
    for item in ESP32ER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    for item in ESP32ER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("ESP32 Template Project reference baseline", styles["h2"]))
    for item in ESP32_TEMPLATE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("ESPHomer current role", styles["h2"]))
    for item in ESPHOMER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    for item in ESPHOMER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("ESPHome template baseline", styles["h2"]))
    for item in ESPHOME_TEMPLATE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Windower on Multi-Turn and canvas", styles["h2"]))
    for item in WINDOWER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    for item in WINDOWER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Playwrighter current role", styles["h2"]))
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
    story.append(p("Media and voice family", styles["h2"]))
    for item in MEDIA_VOICE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Autonomous command watchdog", styles["h2"]))
    for item in COMMAND_WATCHDOG_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Prompt catalog and answer readability discipline", styles["h2"]))
    for item in PROMPT_CATALOG_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Ask Execs and execution approval", styles["h2"]))
    for item in ASK_EXECS_GUIDE + ASK_EXECS_PIPELINE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Windows attention issuing", styles["h2"]))
    for item in WINDOWS_ATTENTION_GUIDE:
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
    story.append(p("Windows uninstall registration", styles["h2"]))
    for item in WINDOWS_APP_REGISTRATION_GUIDE:
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
    story.append(p("User jurisdiction over plain-Python agents", styles["h2"]))
    for item in AGENT_DIRECTORY_DISCLAIMER:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("How agent runtimes are shaped", styles["h2"]))
    for item in AGENT_RUNTIME_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("MCP Doctor spotlight", styles["h2"]))
    for item in MCP_DOCTOR_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Blenderer spotlight", styles["h2"]))
    for item in BLENDERER_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Self-update spotlight", styles["h2"]))
    for item in SELF_UPDATE_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Reviewer and Analyzer spotlight", styles["h2"]))
    for item in REVIEWER_ANALYZER_GUIDE + REVIEWER_ANALYZER_SURFACES:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Operator surface counts", styles["h2"]))
    for item in operator_surface_counts_guide(context):
        story.append(bullet(item, styles["bullet"]))
    story.append(p("Kalier spotlight", styles["h2"]))
    for item in KALIER_GUIDE + KALIER_SURFACES_GUIDE:
        story.append(bullet(item, styles["bullet"]))
    story.append(p("STM32er spotlight", styles["h2"]))
    for item in STM32ER_GUIDE + STM32ER_SURFACES_GUIDE:
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
        ["Repository inventory files", f"{context['inventory_files']}"],
        ["Tracked files in git", f"{context['tracked_files']}"],
        ["Git-unignored working-tree additions", f"{context['untracked_files']}"],
        ["Index paths absent locally (pending deletions)", str(len(context["missing_paths"]))],
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
        ["Binary/asset inventory files skipped from line count", f"{context['binary_count']}"],
        ["Resolved version", f"{context['version_info']['version']}"],
        ["Version source", f"{context['version_info']['source']}"],
    ]
    story.append(table(repo_rows, widths=[3.0 * inch, 3.7 * inch], font_size=8))
    if context["missing_paths"]:
        story.append(p("Pending working-tree deletions", styles["h2"]))
        story.append(p("The Git-index tree retains these paths until a deletion commit. "
                       "They are absent locally and have no current line/byte inventory. "
                       "Unrelated user deletions were preserved during this refresh.", styles["body"]))
        for missing in context["missing_paths"]:
            story.append(p(missing, styles["body"]))
    story.append(p("Latest commits", styles["h2"]))
    commit_rows = [["Date", "Commit", "Subject"]]
    for commit in context["recent_commits"]:
        commit_rows.append([iso_date(commit.committed_at), commit.short_hash, commit.subject])
    story.append(table(commit_rows, widths=[1.0 * inch, 0.8 * inch, 4.9 * inch], font_size=7))
    baseline = context["visual_doc_baseline"]
    if baseline is not None:
        story.append(p("Changes since the last committed PDF/PPTX refresh", styles["h2"]))
        story.append(
            p(
                f"Last committed visual-dossier refresh: {baseline.short_hash} on {iso_date(baseline.committed_at)} — {baseline.subject}",
                styles["body"],
            )
        )
        for item in context["visual_doc_highlights"]:
            story.append(bullet(item, styles["bullet"]))
        visual_chunks = split_items(context["visual_doc_commits"], 12)
        for index, chunk in enumerate(visual_chunks, 1):
            story.append(p(f"Visual-dossier change appendix {index} of {len(visual_chunks)}", styles["h2"]))
            visual_rows = [["Date", "Commit", "Subject"]]
            for commit in chunk:
                visual_rows.append([iso_date(commit.committed_at), commit.short_hash, commit.subject])
            story.append(table(visual_rows, widths=[1.0 * inch, 0.8 * inch, 4.9 * inch], font_size=7))
            if index != len(visual_chunks):
                story.append(PageBreak())
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
            "Methodology: git-tracked text files plus git-unignored working-tree additions. Blank lines and comment-only lines are excluded. Python counts remove module, class, and function docstrings through AST parsing. Executable multiline strings count every nonblank occupied line. The 2026-09-12 correction replaced the former token-start-only undercount, so comparisons with earlier dossiers require a recount. Other text uses language-specific comment stripping. Binary/media assets have no line count.",
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

    story.append(p("10. Complete Repository File Tree (Repository Appendix)", styles["h1"]))
    TREE_OUTPUT.write_text(context["tree_text"], encoding="utf-8")
    tree_chunks = split_lines(context["tree_text"], 76)
    for index, chunk in enumerate(tree_chunks, 1):
        story.append(p(f"Tree appendix {index} of {len(tree_chunks)}", styles["h2"]))
        story.append(Preformatted(chunk, styles["mono"]))
        if index != len(tree_chunks):
            story.append(PageBreak())

    story.append(PageBreak())
    story.append(p("11. New Assets Since the Last Committed Dossier", styles["h1"]))
    story.append(p("Includes current git-unignored additions. A dash means binary, so source-line counts do not apply. Image dimensions describe the stored asset. Historical backups are evidence, not extra runtime modules.", styles["body"]))
    asset_rows = [["Path", "Bytes", "Physical", "Effective", "Type / pixels"]]
    for row in context["new_assets"]:
        asset_rows.append([row["path"], f"{row['bytes']:,}",
                           "-" if row["physical"] is None else str(row["physical"]),
                           "-" if row["effective"] is None else str(row["effective"]), row["kind"]])
    if context["new_assets"]:
        story.append(table(asset_rows, widths=[3.25 * inch, 0.8 * inch, 0.65 * inch, 0.65 * inch, 1.3 * inch], font_size=7))
    else:
        story.append(p("No new file paths were added after the last committed dossier. The recent uninstaller harness and mechanics files landed before that baseline and are included in the complete tree. Existing-file changes, including sampler wiring, are described in the Git and implementation sections.", styles["body"]))

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
    auto_fit: bool = True,
    word_wrap: bool = True,
) -> None:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = word_wrap
    frame.vertical_anchor = MSO_ANCHOR.TOP
    frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE if auto_fit else MSO_AUTO_SIZE.NONE
    # PowerPoint's implicit textbox margins vary by host and can make text that
    # fits geometrically report a small native-render overflow. Pin them so the
    # generated deck has the same conservative text bounds everywhere.
    frame.margin_left = Pt(1)
    frame.margin_right = Pt(6)
    frame.margin_top = Pt(1)
    frame.margin_bottom = Pt(1)
    p0 = frame.paragraphs[0]
    p0.alignment = align
    add_run(p0, text, size, color or THEME["white"], bold, font)
    audit.append((x, y, w, h, name))


def fit_bullet_size(
    bullets: list[str],
    box_w_in: float,
    box_h_in: float,
    max_size: float,
    min_size: float = 9.0,
    space_after_pt: float = 4.0,
) -> int:
    """Deterministically pick the LARGEST font size in [min_size, max_size] at
    which the bullet block is estimated to fit inside ``box_w_in`` x ``box_h_in``.

    This does NOT rely on ``TextFrame.fit_text`` — that path silently fails when
    PowerPoint cannot resolve the display font (Aptos) on the build host, which is
    exactly why dense cards used to overflow. The estimate is intentionally
    CONSERVATIVE (slightly over-counts wrapped lines and reserves a vertical
    gutter) so rendered text never spills its card. ``space_after_pt`` must match
    the paragraph spacing used by :func:`add_bullets`."""
    usable_w_pt = max(box_w_in * 72.0 - 30.0, 36.0)   # minus bullet glyph + indent + margins
    budget_h_pt = box_h_in * 72.0 * 0.93              # keep a safety gutter
    lo, hi = int(round(min_size)), int(round(max_size))
    for size in range(hi, lo - 1, -1):
        chars_per_line = max(int(usable_w_pt / (0.52 * size)), 6)
        line_h = 1.26 * size
        total = 0.0
        for text in bullets:
            n_lines = max(1, -(-len(str(text)) // chars_per_line))  # ceil
            total += n_lines * line_h + space_after_pt
        if total <= budget_h_pt:
            return size
    return lo


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
    # Backstop only: PowerPoint may re-shrink on edit. The deterministic size
    # computed below is the primary guarantee against overflow.
    frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    frame.margin_left = Pt(1)
    frame.margin_right = Pt(6)
    frame.margin_top = Pt(2)
    frame.margin_bottom = Pt(2)
    space_after_pt = 4.0
    fitted = fit_bullet_size(bullets, w, h, size, space_after_pt=space_after_pt)
    for idx, item in enumerate(bullets):
        para = frame.paragraphs[0] if idx == 0 else frame.add_paragraph()
        para.text = item
        para.level = 0
        para.font.name = "Aptos"
        para.font.size = Pt(fitted)
        para.font.color.rgb = color or THEME["muted"]
        para.space_after = Pt(space_after_pt)
        para.bullet = True
    audit.append((x, y, w, h, name))


def add_title(slide, audit: list[tuple[float, float, float, float, str]], title: str, kicker: str, accent: RGBColor) -> None:
    # Titles are sized conservatively and must stay single-line. PowerPoint's
    # normAutofit occasionally clips a valid title to its final characters on
    # export, so fixed title sizing is safer than host-dependent auto-fit.
    add_text(slide, audit, 0.78, 0.6, 11.7, 0.33, kicker.upper(), 10, accent, True, name="kicker", font="Aptos", auto_fit=False, word_wrap=False)
    add_text(slide, audit, 0.76, 0.93, 11.9, 0.62, title, 27, THEME["white"], False, name="title", font="Aptos Display", auto_fit=False, word_wrap=False)


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
            add_text(slide, audit, bx + box_w, y + 0.19, gap, 0.28, ">", 12, accent, True, PP_ALIGN.CENTER, name=f"arrow-{idx}")


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


def add_themed_column_slides(
    prs: Presentation,
    title: str,
    kicker: str,
    accent: RGBColor,
    columns: list[tuple[str, RGBColor, list[str]]],
    per_column: int = 5,
    top: float = 1.58,
    height: float = 5.0,
    size: int = 14,
) -> None:
    """Render labelled columns of bullets, PAGINATING onto as many slides as
    needed so no column ever holds more than ``per_column`` bullets — the
    "split into more slides" rule that keeps dense content from overflowing its
    cards. Each ``columns`` entry is ``(header, accent, items)``; a column's
    items beyond ``per_column`` continue on the next page. Finished columns
    disappear and remaining content uses the available width."""
    margin, gap = 0.72, 0.3
    max_items = max((len(items) for _, _, items in columns), default=0)
    pages = max(1, -(-max_items // per_column))  # ceil
    for page in range(pages):
        page_title = title if pages == 1 else f"{title} ({page + 1}/{pages})"
        slide, audit = add_slide(prs, page_title, kicker, accent)
        active = [(header, color, items[page * per_column:(page + 1) * per_column])
                  for header, color, items in columns if len(items) > page * per_column]
        n = max(1, len(active))
        col_w = (SLIDE_W - 2 * margin - (n - 1) * gap) / n
        for ci, (header, col_accent, seg) in enumerate(active):
            x = margin + ci * (col_w + gap)
            add_panel(slide, audit, x, top, col_w, height, header, seg, col_accent, f"col-{page}-{ci}", size)
        audit_layout(audit, len(prs.slides))


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
    prs.core_properties.title = "Tlamatini eXtended Artificial Intelligence Humanly Tempered"
    prs.core_properties.subject = "Complete technical project dossier"
    prs.core_properties.author = "Angela López Mendoza"
    prs.core_properties.last_modified_by = "Angela López Mendoza"
    prs.core_properties.comments = "Generated from the Tlamatini repository by the deterministic project dossier workflow."
    cover = context["reference_media"][0] if context["reference_media"] else None

    slide, audit = add_slide(
        prs,
        "TLAMATINI",
        "Complete project dossier: what she does, how she works, how to use Tlamatini",
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
        1.2,
        f"Self-hosted AI developer assistant (cloud LLMs by default) with RAG, Multi-Turn orchestration, {context['workflow_agent_count']} agents, ACPX delegation, visual workflows, self-knowledge, and Windows packaging.",
        17,
        THEME["muted"],
        False,
        name="cover-body",
    )
    add_metric_card(slide, audit, 0.9, 4.25, 1.75, "Files", str(context["inventory_files"]), THEME["jade"], "cover-m1")
    add_metric_card(slide, audit, 2.85, 4.25, 1.75, "Agents", str(context["workflow_agent_count"]), THEME["copper"], "cover-m2")
    add_metric_card(slide, audit, 4.8, 4.25, 1.95, "Effective", f"{context['total_effective_lines']:,}", THEME["amber"], "cover-m3")
    add_text(slide, audit, 0.9, 5.62, 6.2, 0.32, "Created by Angela López Mendoza · @angelahack1", 10, THEME["copper"], True, name="cover-creator")
    add_text(slide, audit, 0.9, 6.35, 6.2, 0.32, f"v{context['version_info']['version']} · Generated {context['generated_at']} at HEAD {context['head_short']}", 9, THEME["muted"], name="cover-foot")
    audit_layout(audit, 1)

    slide, audit = add_slide(prs, "What Tlamatini Is", "system identity", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.65, 5.85, 4.95, "Definition", SYSTEM_OVERVIEW, THEME["jade"], "identity-a", 16)
    add_panel(slide, audit, 6.92, 1.65, 5.55, 4.95, "Core interfaces", [
        "Chat page at `/agent/` for context-grounded Q&A, code generation, tool calls, and Multi-Turn execution.",
        "Agentic Control Panel at `/agentic_control_panel/` for visual workflow design.",
        "Django admin and config dialogs for MCPs, tools, agents, users, and persistent settings.",
    ], THEME["copper"], "identity-b", 16)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Agent Directory Disclaimer", "plain-Python agents are user-jurisdiction code", THEME["amber"])
    add_panel(
        slide,
        audit,
        0.78,
        1.6,
        5.9,
        4.95,
        "User jurisdiction",
        AGENT_DIRECTORY_DISCLAIMER[:2],
        THEME["amber"],
        "agent-disclaimer-a",
        12,
    )
    add_panel(
        slide,
        audit,
        6.95,
        1.6,
        5.55,
        4.95,
        "Responsibility boundary",
        AGENT_DIRECTORY_DISCLAIMER[2:],
        THEME["copper"],
        "agent-disclaimer-b",
        12,
    )
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(
        prs,
        "Blue-hat Security Toolkit",
        "operator-controlled Windows defense, not an autonomous Agent row",
        THEME["jade"],
    )
    add_panel(
        slide, audit, 0.78, 1.6, 5.9, 4.95,
        "Purpose and assets", BLUE_HAT_SECURITY_GUIDE[:2],
        THEME["jade"], "bluehat-a", 11,
    )
    add_panel(
        slide, audit, 6.95, 1.6, 5.55, 4.95,
        "Safe enablement path", BLUE_HAT_SECURITY_GUIDE[2:4],
        THEME["amber"], "bluehat-b", 11,
    )
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(
        prs,
        "Blue-hat Controls And Monitoring",
        "persistent host changes plus ten evidence families",
        THEME["copper"],
    )
    add_panel(
        slide, audit, 0.78, 1.6, 5.9, 4.95,
        "Enablement and audit controls", BLUE_HAT_SECURITY_GUIDE[4:7],
        THEME["copper"], "bluehat-controls-a", 10,
    )
    add_panel(
        slide, audit, 6.95, 1.6, 5.55, 4.95,
        "What the defender examines", BLUE_HAT_SECURITY_GUIDE[7:8],
        THEME["jade"], "bluehat-controls-b", 12,
    )
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(
        prs,
        "Blue-hat Response Boundaries",
        "detect first; investigate before containment or attribution",
        THEME["amber"],
    )
    add_panel(
        slide, audit, 0.78, 1.6, 5.9, 4.95,
        "Armed behavior and self protection", BLUE_HAT_SECURITY_GUIDE[8:11],
        THEME["amber"], "bluehat-response-a", 10,
    )
    add_panel(
        slide, audit, 6.95, 1.6, 5.55, 4.95,
        "Evidence, privacy, and packaging", BLUE_HAT_SECURITY_GUIDE[11:],
        THEME["jade"], "bluehat-response-b", 10,
    )
    audit_layout(audit, len(prs.slides))

    add_themed_column_slides(prs, "What The System Does", "capability map", THEME["copper"], [
        ("Knowledge", THEME["jade"], WHAT_IT_DOES[:6]),
        ("Action", THEME["copper"], WHAT_IT_DOES[6:12]),
        ("Delivery", THEME["amber"], WHAT_IT_DOES[12:]),
    ], per_column=3)

    slide, audit = add_slide(prs, "How It Works", "execution pipeline", THEME["jade"])
    add_flow_boxes(slide, audit, 0.95, 2.6, ["Browser", "Channels", "RAG", "Planner", "Tools", "Answer"], THEME["jade"])
    add_panel(slide, audit, 0.82, 4.0, 11.55, 2.45, "Request-to-answer flow", [
        "A browser request flows through Django Channels into the RAG/context layer, the Multi-Turn planner, the tool executor, and back as a synthesized answer.",
        "The next two pages detail the request path (intake, retrieval, permission gating) and the runtime path (planning, tool execution, agent bridges, packaging).",
    ], THEME["jade"], "works-intro", 15)
    audit_layout(audit, len(prs.slides))

    add_themed_column_slides(prs, "How It Works — Detail", "execution pipeline", THEME["jade"], [
        ("Request path", THEME["jade"], HOW_IT_WORKS[:11]),
        ("Runtime path", THEME["copper"], HOW_IT_WORKS[11:]),
    ], per_column=6)

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
        "Explicit tool loop runs tool calls, appends observations, and asks again until final answer or the 4096-turn limit.",
        "Create Flow no longer uses the removed answer classifier; it appears when Multi-Turn has at least one successful agent call.",
    ], THEME["copper"], "mt-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Unchecked mode", [
        "Keeps the original prompt validation and legacy prefetch behavior.",
        "Maintains compatibility for fast Q&A and simple context-grounded answers.",
        "Avoids forcing every chat request into agentic execution.",
    ], THEME["jade"], "mt-b", 16)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Ask Execs", "v1.10.0 safety modifier retained in the current release", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Operator contract", ASK_EXECS_GUIDE, THEME["amber"], "ask-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Runtime mechanics", ASK_EXECS_PIPELINE_GUIDE, THEME["jade"], "ask-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Windows Attention Issuing", "taskbar flash and uppercase log banner when she needs you", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Current mechanism", WINDOWS_ATTENTION_GUIDE, THEME["jade"], "attention-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Why operators care", [
        "If the browser is buried, Tlamatini still has a local way to pull the operator back at the exact moment an approval prompt or notification matters.",
        "The path is concrete and auditable: `POST /agent/flash_window/`, `window_flash.py`, `FlashWindowEx`, and the matching uppercase banner in `tlamatini.log`.",
        "Because the helper is best-effort and fail-safe, a missed flash never breaks the request path or blocks the surrounding workflow.",
    ], THEME["amber"], "attention-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Windows Installed-App Registration", "v1.11.0 uninstall integration retained in the current release", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What changed", WINDOWS_APP_REGISTRATION_GUIDE, THEME["copper"], "arp-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Why operators care", [
        "Packaged installs now show up in normal Windows uninstall surfaces instead of only leaving behind shortcuts and a loose `Uninstaller.exe` in the install folder.",
        "The registration is HKCU-only and non-elevated, matching the installer’s per-user design on Windows 10 and Windows 11.",
        "Because frozen startup self-heals the entry, even older installs can gain the uninstall surface after a later app launch without a reinstall.",
    ], THEME["jade"], "arp-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Release Identity and Runtime Foundations", context["git_describe"], THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Release line", CURRENT_RELEASE_GUIDE[:2], THEME["amber"], "rel-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "MCP, research, service, and privacy", CURRENT_RELEASE_GUIDE[2:4], THEME["jade"], "rel-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "NetSpeed-Calculator", "agent 88 - measured throughput with uncertainty, not a single flattering number", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Measurement method", NETSPEED_GUIDE[:4], THEME["jade"], "netspeed-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Safety, evidence, and operation", NETSPEED_GUIDE[4:], THEME["amber"], "netspeed-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Googler Structured Discovery", "valid dork syntax, indexed-file workflows, and a clear responsibility boundary", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Builder, presets, and operators", GOOGLER_DORK_GUIDE[:4], THEME["amber"], "googler-dork-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "File workflow and responsible use", GOOGLER_DORK_GUIDE[4:], THEME["jade"], "googler-dork-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Googler Search Resilience", "plain HTTP first, seven browser routes second, bounded retries, and honest attribution", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Measured failure and browser policy", GOOGLER_RESILIENCE_GUIDE[:3], THEME["jade"], "googler-resilience-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Fallback, semantics, and proof", GOOGLER_RESILIENCE_GUIDE[3:], THEME["amber"], "googler-resilience-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "WAL-Safe Database Movement", "Backup DB, Set DB, and startup promotion now preserve committed SQLite truth", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Consistent copy", WAL_SAFE_DB_GUIDE[:3], THEME["copper"], "wal-db-a", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Sidecar-safe promotion", WAL_SAFE_DB_GUIDE[3:], THEME["jade"], "wal-db-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "MCP, Research, And Private Builds", "guided onboarding, a deep-research starter, and strict PII boundaries", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "MCP and research lifecycle", MCP_RESEARCH_PRIVACY_GUIDE[:3], THEME["amber"], "mcp-research-a", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Service and privacy boundary", MCP_RESEARCH_PRIVACY_GUIDE[3:], THEME["jade"], "mcp-research-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Execution Truth And Runtime Reliability", "closed status vocabulary, canonical result fields, and runtime safeguards", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Deterministic execution truth", CURRENT_RELEASE_GUIDE[4:6], THEME["jade"], "rel-c", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Database startup safeguard", CURRENT_RELEASE_GUIDE[6:7], THEME["amber"], "rel-d", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Dialog And Bundle Proof", "v1.48.16 - v1.48.17 safety lineage retained in the current release", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Uniform dismissal and themed pop-ups", [
        CURRENT_RELEASE_GUIDE[7],
        "The bubble-phase dispatcher closes only the topmost layer through its own dismiss control; no affirmative action is selected and one Escape cannot close two stacked dialogs.",
    ], THEME["copper"], "dialog-release-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Frozen payload proof", [
        CURRENT_RELEASE_GUIDE[8],
        "Evidence: 35 focused dismissal-policy tests, a visible headed-Chrome proof runner, the tree-wide `closeOnEscape: false` guard, and build tests for CArchive/PYZ inspection.",
    ], THEME["jade"], "dialog-release-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Operator Refinements", "capture, PDF language, and External-MCP catalog behavior", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Menus, logging, and whole-desktop capture", CURRENT_RELEASE_GUIDE[9:11], THEME["copper"], "rel-operator-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Document and MCP refinements", CURRENT_RELEASE_GUIDE[11:12], THEME["jade"], "rel-operator-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Recent Implementation Assets", "new source, tests, migrations, harnesses, and inventory effects", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Published inventory", publication_guide(context)[:3], THEME["amber"], "recent-assets-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Source and evidence", publication_guide(context)[3:], THEME["jade"], "recent-assets-b", 12)
    audit_layout(audit, len(prs.slides))

    for title, guide in (("Central Model Configuration", MODEL_CONFIGURATION_GUIDE),
                         ("Model Compatibility and Coverage", MODEL_COMPATIBILITY_GUIDE),
                         ("Source and Frozen Model Runtime", MODEL_RUNTIME_GUIDE),
                         ("Video Analysis and MCP Updates", LATEST_SOURCE_GUIDE),
                         ("Latest Defaults and Prompt Migrations", LATEST_DEFAULTS_GUIDE),
                         ("PDF Canvas Reading", PDF_CANVAS_GUIDE),
                         ("Whole-Document PDF Context", PDF_CONTEXT_GUIDE),
                         ("PDF Progress and Cancellation", PDF_PROGRESS_GUIDE),
                         ("PDF Distribution and Tracked Assets", pdf_distribution_guide(context)),
                         ("Local Frontend and Release Budget", LOCAL_RELEASE_GUIDE),
                         ("Self-Modify and Update Carriage", SELF_CARRIAGE_GUIDE),
                         ("Document-Agent Result Contracts", DOCUMENT_CONTRACT_GUIDE),
                         ("PPTXer Presentations", PPTXER_GUIDE),
                         ("PDFer Signature Styles", PDFER_STYLES_GUIDE),
                         ("LaTeXer Signature Styles", LATEXER_STYLES_GUIDE),
                         ("Desktop Input Contracts", DESKTOP_INPUT_GUIDE),
                         ("Flow Planning Contracts", FLOW_CONTRACT_GUIDE),
                         ("Canvas Avatar Presence", AVATAR_GUIDE),
                         ("Visible Avatar Test Runner", AVATAR_TEST_GUIDE),
                         ("Whisperer Silence Gate", WHISPERER_GATE_GUIDE),
                         ("Voice Commands", VOICE_COMMAND_GUIDE),
                         ("Grepper Line Reading", GREPPER_LINES_GUIDE),
                         ("Ollama Sampler Defaults", OLLAMA_SAMPLER_GUIDE),
                         ("Uninstaller Safety", UNINSTALLER_SAFETY_GUIDE),
                         ("Wrapped-Agent Wait Completion", WRAPPED_WAIT_GUIDE),
                         ("Ollama Account-Usage Utility", OLLAMA_USAGE_GUIDE),
                         ("Gitter Windows Paths", GITTER_WORKTREE_GUIDE)):
        add_themed_column_slides(prs, title, "current source and verification evidence",
                                 THEME["jade"], [("Behavior", THEME["jade"], guide[:3]),
                                 ("Operation and scope", THEME["copper"], guide[3:])], size=16)

    for group, fields in model_reference_groups().items():
        items = []
        for field in fields:
            path = f"{field['agent']}.{field['path']}" if field["agent"] else "in-process service"
            items.append(f"{field['key']}: {field['default'] or '(empty provider default)'}. "
                         f"YAML: {path}. Kind: {field['kind']}.")
        midpoint = (len(items) + 1) // 2
        add_themed_column_slides(prs, f"Models: {group}",
                                 "registry defaults; full semantics in docs/model_configuration.md",
                                 THEME["jade"], [("Settings", THEME["jade"], items[:midpoint]),
                                 ("Settings continued", THEME["copper"], items[midpoint:])],
                                 per_column=3, size=16)

    slide, audit = add_slide(prs, "Release Continuity", "older waves still carried by the current dossier", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Carried product story", CURRENT_RELEASE_GUIDE[12:16], THEME["copper"], "rel-e", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Documentation contract", CURRENT_RELEASE_GUIDE[16:], THEME["jade"], "rel-f", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "External MCP Structured Results", "v1.41.4 - successful server data reaches the model", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Failure mechanism", STRUCTURED_CONTENT_1414_GUIDE[:3], THEME["jade"], "mcp-1414-a", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Unified transport path", STRUCTURED_CONTENT_1414_GUIDE[3:5], THEME["amber"], "mcp-1414-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Structured Output Boundaries", "context protection, errors, and regression proof", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Payload safety", STRUCTURED_CONTENT_1414_GUIDE[5:6], THEME["copper"], "mcp-1414-c", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Coverage and release", STRUCTURED_CONTENT_1414_GUIDE[6:], THEME["jade"], "mcp-1414-d", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "STM32er PlatformIO Release", "published in tagged v1.42.0", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Routing and coverage", STM32ER_PLATFORMIO_WORKTREE_GUIDE[:4], THEME["amber"], "stm32-pio-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Preflight and safe composite", STM32ER_PLATFORMIO_WORKTREE_GUIDE[4:6], THEME["jade"], "stm32-pio-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "PlatformIO Coverage Boundary", "what STM32er Phase 1 implements and what remains planned", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Deliberate refusal", STM32ER_PLATFORMIO_WORKTREE_GUIDE[6:8], THEME["copper"], "stm32-pio-c", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "New assets and tests", STM32ER_PLATFORMIO_WORKTREE_GUIDE[8:], THEME["jade"], "stm32-pio-d", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "STM32 Stepwise Proof Demos", "Blue Pill and F407 Discovery from driver to camera evidence", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Operator contract", STM32ER_STEPWISE_DEMOS_GUIDE[:3], THEME["jade"], "stm32-step-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Hardware and evidence", STM32ER_STEPWISE_DEMOS_GUIDE[3:], THEME["amber"], "stm32-step-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Prompt Catalog No-Gap Renumber", "v1.42.0 - deliberate one-time primary-key migration", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Migration mechanics", PROMPT_CATALOG_WORKTREE_GUIDE[:3], THEME["copper"], "prompt-live-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Boundaries and proof", PROMPT_CATALOG_WORKTREE_GUIDE[3:], THEME["jade"], "prompt-live-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Prompt Catalog Reorganized", "v1.41.3 - 13 categories and duplicate removal", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Migration contract", PROMPT_CATALOG_1413_GUIDE[:4], THEME["jade"], "prompt-1413-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Stable identity", PROMPT_CATALOG_1413_GUIDE[4:5], THEME["amber"], "prompt-1413-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Prompt Catalog Search", "grouped at rest, ranked and flattened while searching", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Search behavior", PROMPT_CATALOG_1413_GUIDE[5:7], THEME["amber"], "prompt-1413-c", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Viewport contract", PROMPT_CATALOG_1413_GUIDE[7:], THEME["jade"], "prompt-1413-d", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Hard Cancel Run Latch", "v1.41.2 - cancelled runs stay cancelled", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Per-user epoch", HARD_CANCEL_GUIDE[:4], THEME["copper"], "hard-cancel-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Evidence preservation", HARD_CANCEL_GUIDE[4:5], THEME["jade"], "hard-cancel-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Hard Cancel Boundaries", "approval, recovery, frontend, and regression coverage", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "No resurrection", HARD_CANCEL_GUIDE[5:7], THEME["jade"], "hard-cancel-c", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Coverage", HARD_CANCEL_GUIDE[7:], THEME["amber"], "hard-cancel-d", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Screenshot To Chat", "v1.41.0 - paste or drop an image path into the prompt", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Ingestion path", CHAT_IMAGE_1410_GUIDE[:4], THEME["amber"], "image-chat-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Reversible input", CHAT_IMAGE_1410_GUIDE[4:5], THEME["jade"], "image-chat-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Image Ingestion Boundaries", "vision handoff, layout safety, and implementation assets", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Vision and layout", CHAT_IMAGE_1410_GUIDE[5:6], THEME["copper"], "image-chat-c", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Concrete assets", CHAT_IMAGE_1410_GUIDE[6:], THEME["jade"], "image-chat-d", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Configurable Web Port", "v1.40.1 — escape reserved port 8000 without rebuilding", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Why and where", DJANGO_PORT_GUIDE[:3], THEME["amber"], "django-port-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Every manage.py launch path", DJANGO_PORT_GUIDE[3:5], THEME["jade"], "django-port-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Web Port Boundaries", "fail-open resolution, CLI precedence, and focused coverage", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Deliberate boundaries", DJANGO_PORT_GUIDE[5:6], THEME["copper"], "django-port-c", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Regression contract", DJANGO_PORT_GUIDE[6:], THEME["jade"], "django-port-d", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "FlowPills Companion Discovery", "v1.40.0 — find agent templates without Python or drive scans", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Lookup contract", FLOWPILLS_DISCOVERY_GUIDE[:3], THEME["jade"], "flowpills-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Publication and preservation", FLOWPILLS_DISCOVERY_GUIDE[3:], THEME["amber"], "flowpills-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Unreal 5.8 Project Scaffold", "v1.39.5 — two prompt fields to a ready-to-build C++ project", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Deterministic scaffold", UNREAL_SCAFFOLD_GUIDE[:3], THEME["copper"], "unreal-scaffold-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Build and editor handoff", UNREAL_SCAFFOLD_GUIDE[3:], THEME["jade"], "unreal-scaffold-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "v1.39.5 Runtime Hardening", "bounded waits, accurate partial results, and request isolation", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Responsiveness", RESPONSIVENESS_HARDENING_GUIDE[:3], THEME["amber"], "responsive-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Safety and result integrity", RESPONSIVENESS_HARDENING_GUIDE[3:], THEME["jade"], "responsive-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Nmapper Local Recon", "use-only nmap bridge for authorized targets", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Operator contract", NMAPPER_GUIDE[:3], THEME["jade"], "nmapper-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Actions and assets", NMAPPER_GUIDE[3:], THEME["amber"], "nmapper-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Startup And Prompt Polish", "v1.39.4 closeability plus current prompt localization", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Startup dialog", STARTUP_PROMPT_POLISH_GUIDE[:2], THEME["amber"], "startup-prompt-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Prompt catalog", STARTUP_PROMPT_POLISH_GUIDE[2:], THEME["jade"], "startup-prompt-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Robotic Loop Closed", "v1.38.0 — from blank page to observed hardware behavior", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Closed-loop chain", ROBOTIC_LOOP_GUIDE[:2], THEME["copper"], "robot-loop-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Verdict safety", ROBOTIC_LOOP_GUIDE[2:], THEME["jade"], "robot-loop-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "v1.38.1 Frontend Hotfix", "mutable-state recovery and one-call prompt catalog", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Const-poison recovery", FRONTEND_HOTFIX_GUIDE[:3], THEME["amber"], "frontend-hotfix-a", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Prompt catalog path", FRONTEND_HOTFIX_GUIDE[3:], THEME["jade"], "frontend-hotfix-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Self-Healing Multi-Turn", "watchdog-bounded model steps and truthful recovery", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Recovery loop", SELF_HEALING_GUIDE[:3], THEME["copper"], "heal-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Evidence preservation", SELF_HEALING_GUIDE[3:5], THEME["jade"], "heal-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Create Flow Gate", "successful-only flows without answer_success", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What changed", CREATE_FLOW_GUIDE[:2], THEME["jade"], "flow-gate-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Operator result", CREATE_FLOW_GUIDE[2:], THEME["amber"], "flow-gate-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Frontend Recovery Controls", "status frames stay busy until the real final answer", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Self-healing status frames", FRONTEND_RECOVERY_GUIDE[:3], THEME["copper"], "frontend-recovery-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Create Flow name resolution", FRONTEND_RECOVERY_GUIDE[3:], THEME["jade"], "frontend-recovery-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Discoverer PDCP Wiring", "ProjectDiscovery key without prompt-pasted secrets", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Configuration path", DISCOVERER_PDCP_GUIDE[:3], THEME["amber"], "pdcp-a", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Redaction and prompt seed", DISCOVERER_PDCP_GUIDE[3:], THEME["copper"], "pdcp-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Discoverer Vulnx And Go Guard", "current CVE search plus source-control protection", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "vulnx CVE lane", DISCOVERER_VULNX_GO_GUARD_GUIDE[:3], THEME["copper"], "vulnx-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Go-deny guard", DISCOVERER_VULNX_GO_GUARD_GUIDE[3:], THEME["jade"], "vulnx-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "v1.36.0 Release Delta", "Video-Analyzer, prompts, and generated workflow layout", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Exact release checklist", V136_RELEASE_GUIDE[:3], THEME["copper"], "v136-a", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Runtime contract", V136_RELEASE_GUIDE[3:], THEME["jade"], "v136-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Video-Analyzer", "robotics, audio-track transcription and video summaries", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What she does", VIDEO_ANALYZER_GUIDE[:3], THEME["jade"], "video-analyzer-a", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Verdicts and routing", VIDEO_ANALYZER_GUIDE[3:], THEME["amber"], "video-analyzer-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Prompt Search And .flw Layout", "operator usability after the catalog grew", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Prompt search", PROMPT_SEARCH_AND_FLOW_GUIDE[:2], THEME["amber"], "prompt-flow-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Generated flows", PROMPT_SEARCH_AND_FLOW_GUIDE[2:], THEME["copper"], "prompt-flow-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "v1.33.2 Release Delta", "Zavuerer, model defaults, cleanup, and safety", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Exact release checklist", V1332_RELEASE_GUIDE, THEME["copper"], "v1332-a", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Recent implementation assets", [
        "`agent/agents/zavuerer/` carries the stdlib-only Zavu REST client and config template.",
        "`0159`-`0164` seed the Agent, Tool, prompts, and setup-wizard dedupe.",
        "`access_key_wizard.py`, `tools.py`, and `config.json` wire the Zavu key path.",
        "`config.json` now favors `glm-5.3:cloud` for the shipped cloud model baseline.",
        "`views.py`, ACP JS/CSS, and `agent_contracts.py` make canvas wiring and redaction work.",
    ], THEME["jade"], "v1332-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Zavuerer", "new unified messaging agent for Zavu", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What she does", ZAVUERER_GUIDE[:3], THEME["amber"], "zavu-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Implementation and safety", ZAVUERER_GUIDE[3:], THEME["jade"], "zavu-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Image-Interpreter", "triple-model vision analysis with fail-safe merging", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Parallel vision pipeline", IMAGE_INTERPRETER_GUIDE[:4], THEME["copper"], "image-interpreter-a", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Prompts, output, and config", IMAGE_INTERPRETER_GUIDE[4:], THEME["jade"], "image-interpreter-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "External MCPs", "how Tlamatini now reaches tools outside her bundled runtime", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Operator model", EXTERNAL_MCPS_GUIDE, THEME["jade"], "xmcp-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Concrete implementation", EXTERNAL_MCP_ASSETS_GUIDE, THEME["amber"], "xmcp-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "MCP Doctor", "safe onboarding and diagnostics before live external MCP use", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What she does", MCP_DOCTOR_GUIDE, THEME["copper"], "doctor-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators use it", [
        "Open `External -> MCPs` to add or import a server, then run MCP Doctor before the first real connect if the runtime, endpoint, or secret story is still uncertain.",
        "In Multi-Turn, call `chat_agent_mcp_doctor` when you want the LLM to triage a server declaratively instead of guessing from prose about PATH, env vars, or transport settings.",
        "Because the diagnosis path is static and fail-safe, it surfaces onboarding mistakes early without leaking into a half-connected remote-tool session.",
    ], THEME["jade"], "doctor-b", 11)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Start Here", "the new easy-follow onboarding path", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Five-step path", START_HERE_GUIDE, THEME["amber"], "start-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "First configuration surfaces", FIRST_RUN_CONFIG_GUIDE, THEME["jade"], "start-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Blenderer And Self-Update", "how to use the newest release surfaces", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Blenderer", BLENDERER_GUIDE, THEME["jade"], "blend-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Self-update", SELF_UPDATE_GUIDE, THEME["amber"], "blend-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Self-Modify Source Snapshot", "generated `TlamatiniSourceCode/` and rebuild contract", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Snapshot contract", SOURCE_SNAPSHOT_GUIDE, THEME["jade"], "snap-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Access Keys, Updates, And File Writes", API_KEYS_WIZARD_GUIDE[:2] + SELF_UPDATE_GUIDE[:1] + FILE_CREATOR_HARDENING_GUIDE[:1], THEME["amber"], "snap-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Media, Voice, And Runtime Resilience", "Talker / Whisperer family plus watchdog hardening", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Media and voice", MEDIA_VOICE_GUIDE, THEME["copper"], "media-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Autonomous watchdog", COMMAND_WATCHDOG_GUIDE, THEME["jade"], "media-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Earlier Asset Waves", "backend, frontend, and build assets retained in the current tree", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Named assets", NEW_ASSETS_GUIDE[:3], THEME["jade"], "assets-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Hardening assets", NEW_ASSETS_GUIDE[3:6], THEME["amber"], "assets-b", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Earlier Assets Appendix", "retained implementation deltas", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Discoverer and frontend", NEW_ASSETS_GUIDE[6:9], THEME["amber"], "assets-c", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Frontend, port, and agent assets", NEW_ASSETS_GUIDE[9:12], THEME["jade"], "assets-d", 10)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Earlier Assets Source Trail", "retained assets behind the current inventory", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Media and browser setup", NEW_ASSETS_GUIDE[12:15], THEME["copper"], "assets-e", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Inventory meaning", NEW_ASSETS_GUIDE[15:], THEME["jade"], "assets-f", 10)
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
        f"This dossier reconciles README and Book wording back to the same {context['workflow_agent_count']}-agent inventory when older badges or legacy prose lines lag behind the live tree.",
    ], THEME["jade"], "agent-proof-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Description source", AGENT_DESCRIPTION_GUIDE, THEME["copper"], "agent-proof-b", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Reviewer And Analyzer", "new review and security surfaces", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What they do", REVIEWER_ANALYZER_GUIDE, THEME["amber"], "reviewer-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators reach them", REVIEWER_ANALYZER_SURFACES, THEME["jade"], "reviewer-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Operator Surface Counts", "README header and planner-facing inventory", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Current counts", operator_surface_counts_guide(context), THEME["copper"], "surface-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Why the counts matter", [
        "The README now surfaces the same operator picture the app exposes in practice: broad capability, selective planner binding, and a capped tool budget per request.",
        f"Those counts complement the {context['workflow_agent_count']}-agent bestiary instead of replacing it: skills, wrapped tools, and ACPX tools are different layers of the same operating surface.",
        "For dossier readers, this closes a gap between the capability narrative and the quick-glance repo badges at the top of the handbook.",
    ], THEME["jade"], "surface-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Kalier", "embedded-client Kali Linux control for chat and canvas", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What it adds", KALIER_GUIDE, THEME["jade"], "kalier-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators reach it", KALIER_SURFACES_GUIDE, THEME["amber"], "kalier-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "STM32er", "critical-mission STM32 firmware control with dual backends", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What it adds", STM32ER_GUIDE, THEME["copper"], "stm32-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators reach it", STM32ER_SURFACES_GUIDE, THEME["jade"], "stm32-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "ESP32er", "PlatformIO-driven ESP32 firmware control", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What it adds", ESP32ER_GUIDE, THEME["jade"], "esp32-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators reach it", ESP32ER_SURFACES_GUIDE, THEME["amber"], "esp32-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "ESP32 Template Project", "known-good PlatformIO baseline for ESP32er", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Why it matters", ESP32_TEMPLATE_GUIDE, THEME["amber"], "esp32-c", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Operator result", [
        "The reference project gives Tlamatini a stable build/upload/monitor proving ground before a user asks her to generate larger ESP32 firmware.",
        "Because it is a plain PlatformIO repo, it matches the exact grain of `chat_agent_esp32er` and the visual ESP32er node instead of introducing another sidecar protocol.",
        "This closes the gap between the new agent and a practical first project a user can build, flash, and watch over serial on real silicon.",
    ], THEME["jade"], "esp32-d", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "ESPHomer", "ESPHome-driven smart-home firmware control", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What it adds", ESPHOMER_GUIDE, THEME["copper"], "esphome-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators reach it", ESPHOMER_SURFACES_GUIDE, THEME["jade"], "esphome-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "ESPHome Template Project", "known-good YAML baseline for ESPHomer", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Why it matters", ESPHOME_TEMPLATE_GUIDE, THEME["jade"], "esphome-c", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Operator result", [
        "The bundled sample gives Tlamatini a stable validate/compile/upload proving ground before a user asks her to generate a custom ESPHome device.",
        "Because the source-of-truth is a single YAML file, it matches the exact grain of `chat_agent_esphomer` and the visual ESPHomer node instead of introducing a separate project-server protocol.",
        "This closes the gap between the new agent and a practical first device a user can build, flash, and then control from a smart-home hub.",
    ], THEME["amber"], "esphome-d", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Self-Knowledge And Self-Modify", "who she is and how she can improve herself", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What changed", SELF_KNOWLEDGE_GUIDE, THEME["amber"], "self-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Self-modify and autonomy", SELF_MODIFY_GUIDE + MULTITURN_4096_GUIDE[:2], THEME["jade"], "self-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Windower In Multi-Turn", "desktop window management for chat and canvas", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What it adds", WINDOWER_GUIDE, THEME["amber"], "window-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "How operators reach it", WINDOWER_SURFACES_GUIDE, THEME["jade"], "window-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Playwrighter", "real-browser automation for chat and canvas", THEME["jade"])
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
        "This stability-focused patch preceded the historical `v1.5.0` Playwrighter release and remains part of the v1.65.4 operator/runtime behavior.",
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

    add_themed_column_slides(prs, "How To Use Tlamatini", "operator path", THEME["jade"], [
        ("Daily use", THEME["jade"], HOW_TO_USE[:10]),
        ("Workflows and releases", THEME["copper"], HOW_TO_USE[10:]),
    ], per_column=5)

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
    add_panel(slide, audit, 6.92, 1.6, 5.55, 4.95, "Config essentials", CONFIGURATION_GUIDE[:4], THEME["copper"], "install-b", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Configuration Essentials (continued)", "README-backed operator path", THEME["jade"])
    add_panel(slide, audit, 0.82, 1.6, 11.55, 4.95, "Config essentials", CONFIGURATION_GUIDE[4:], THEME["copper"], "install-c", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "ACPX-Skills And Prompts", "recent operator-surface documentation updates", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "ACPX-Skills menu", ACPX_SKILLS_GUIDE, THEME["amber"], "skills-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Prompt catalog and readability", PROMPT_CATALOG_GUIDE, THEME["jade"], "skills-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "DB Menu And Startup Swap", "operator-facing database maintenance surface", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Backup and Set DB", DB_MENU_GUIDE, THEME["copper"], "db-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "What happens on next start-up", DB_SWAP_GUIDE, THEME["jade"], "db-b", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Versioning System", "release-identity work across runtime and builds", THEME["amber"])
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

    slide, audit = add_slide(prs, "De-Compresser Agent", "archive compression and decompression worker", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Operator contract", DE_COMPRESSER_GUIDE, THEME["copper"], "decomp-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Integration and fallbacks", DE_COMPRESSER_INTEGRATION_GUIDE, THEME["jade"], "decomp-b", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Unreal MCP And Unrealer", "UE5 editor bridge for chat and canvas", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What it adds", UNREAL_MCP_GUIDE, THEME["jade"], "unreal-a", 14)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Install and runtime path", UNREAL_INSTALL_GUIDE + UNREAL_RUNTIME_GUIDE[:1], THEME["copper"], "unreal-b", 13)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Extended Unrealer Surface", "the 53-command fork and why it matters", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Extended fork", UNREAL_EXTENDED_GUIDE, THEME["amber"], "unreal-c", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Runtime consequences", UNREAL_RUNTIME_GUIDE[1:] + ["The seeded Unreal demo prompts now cover screenshots, scene-building, and in-editor Python/introspection paths on top of the original blueprint flow."], THEME["jade"], "unreal-d", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Orphan-Process Cleanup", "Windows process-hygiene and survivor reporting", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Three-tier reaper", ORPHAN_REAPER_GUIDE, THEME["amber"], "reaper-a", 14)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Prevention and survivor reporting", ORPHAN_PREVENTION_GUIDE, THEME["jade"], "reaper-b", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Ollama Without Admin Rights", "local model setup on Windows", THEME["amber"])
    add_text(slide, audit, 0.85, 1.72, 11.55, 3.2, OLLAMA_COMMANDS, 9, THEME["white"], False, name="ollama-commands", font="Cascadia Mono")
    add_panel(slide, audit, 0.85, 5.02, 11.55, 1.9, "Checklist", OLLAMA_GUIDE[:2], THEME["amber"], "ollama-check", 14)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Ollama Readiness", "service, API, and model pulls", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Service and API", OLLAMA_GUIDE[2:], THEME["jade"], "ollama-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Default pull set", [
        "Nomic-Embed-Text:latest",
        "glm-5.3:cloud",
        "jcyhsiao/qwen3.5cloud:latest",
        "gemma4:cloud",
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
        "Self-heals the frozen Windows Installed-apps entry when `Uninstaller.exe` is present beside the executable.",
        "Handles shutdown by killing tracked/untracked agent processes and clearing pool artifacts.",
    ], THEME["jade"], "run-b", 15)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Packaging Path", "source usage is separate from release building", THEME["amber"])
    add_flow_boxes(slide, audit, 1.15, 2.0, ["build.py", "pkg.zip", "build_uninstaller", "Uninstaller", "build_installer", "Release"], THEME["amber"])
    add_panel(slide, audit, 0.92, 3.35, 11.35, 2.55, "Release rule", [
        "Run packaging only when preparing a Windows distribution.",
        "The final distributable is the full `dist/Tlamatini_Release_v<version>/` folder, not one executable copied out of context.",
        "Installer scripts register shortcuts, `.flw` file associations, the bundled uninstaller, and the per-user Installed-apps entry.",
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
        ("Repo files", context["inventory_files"]),
        ("Agents", context["workflow_agent_count"]),
        ("Migrations", context["migrations"]),
        ("JS", context["js_modules"]),
        ("CSS", context["css_files"]),
        ("HTML", context["html_templates"]),
    ]
    for idx, (label, value) in enumerate(metrics):
        add_metric_card(slide, audit, 0.82 + idx * 1.96, 1.75, 1.75, label, str(value), THEME["jade"] if idx % 2 == 0 else THEME["copper"], f"repo-{idx}")
    add_panel(slide, audit, 1.05, 3.1, 10.85, 3.35, "Current HEAD", [
        f"{context['head_short']} - {context['head_subject']}",
        f"Resolved version: {context['version_info']['version']} ({context['version_info']['source']})",
        f"Generated on {context['generated_at']}",
        f"Inventory scope: {context['inventory_files']} files = {context['tracked_files']} tracked + {context['untracked_files']} git-unignored working-tree additions",
        f"Multi-Turn tools: {context['total_multi_turn_tools']}; wrapped chat-agent tools: {context['wrapped_chat_agent_count']}; skills: {context['skills_count']}",
        f"Python requirements: {context['requirements_count']}; authoritative agent-description rows: {context['agent_description_rows']}",
        f"Binary assets: {context['binary_count']}; index paths absent locally: {len(context['missing_paths'])} (not counted as bytes/lines)",
    ], THEME["amber"], "repo-head", 15)
    audit_layout(audit, len(prs.slides))

    baseline = context["visual_doc_baseline"]
    if baseline is not None:
        visual_highlights = context["visual_doc_highlights"]
        slide, audit = add_slide(prs, "Since Last Dossier Refresh", "all important changes since the last committed PDF/PPTX update", THEME["copper"])
        add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Baseline", [
            f"{baseline.short_hash} on {iso_date(baseline.committed_at)}",
            baseline.subject,
            f"Commits since then: {len(context['visual_doc_commits'])}",
        ], THEME["copper"], "since-a", 13)
        add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Key changes", visual_highlights[:3], THEME["jade"], "since-b", 10)
        audit_layout(audit, len(prs.slides))

        remaining_highlights = visual_highlights[3:]
        for offset in range(0, len(remaining_highlights), 6):
            group = remaining_highlights[offset:offset + 6]
            slide, audit = add_slide(
                prs,
                "Dossier Delta Continued",
                f"verified implementation changes {offset + 4}-{offset + 3 + len(group)}",
                THEME["jade"],
            )
            if len(group) == 1:
                add_panel(slide, audit, 0.78, 1.6, 11.72, 4.95, "Additional verified change", group, THEME["jade"], f"since-more-{offset}", 12)
            else:
                split_at = (len(group) + 1) // 2
                add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Runtime and UI", group[:split_at], THEME["jade"], f"since-more-a-{offset}", 10)
                add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Data and operator contract", group[split_at:], THEME["amber"], f"since-more-b-{offset}", 10)
            audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Recent Platform Additions", "tagged foundation and subsequent source changes", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Recent agents and execution surfaces", [
        "NetSpeed-Calculator: agent 88 / wrapped launcher 66, with multi-provider confidence intervals, I-squared heterogeneity, bufferbloat, named endpoint failures, and tier-D metered-bandwidth gating.",
        "Googler: four plain-HTTP server-rendered routes first, then visible Chrome/bundled Chromium across seven browser routes, with bounded retries, answer attribution, structured dork presets/aliases, URL-only file hunts, and a lawful-use boundary.",
        "WAL-safe SQLite: online backup API, self-contained DELETE-journal copies, quick_check proof, and sidecar-safe Backup DB / Set DB / startup promotion.",
        "External MCP Adder: the 29th skill codifies transport classification, secret-separated import, Doctor, activation, wait, status/list, and call.",
        "Deep Internet Research: append-only prompt 118 requests a long, link-rich Multi-Turn + Exec Report research run without hiding tool prerequisites.",
    ], THEME["copper"], "monday-a", 10)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Lifecycle, policy, and monitoring", [
        release_identity(),
        "Complete cloud-model operation requires Ollama Pro or higher; this is an operating requirement, not sponsorship, and current plan details belong to Ollama's official site.",
        "Private contact synchronization merges same-machine sources only for the explicit keyed build; public output and source snapshots remain free of contact PII.",
        "The stronger disclaimer says plain-Python transparency enables user control but is not a security warranty; the operator owns authorization, permissions, review, and consequences.",
        f"Catalog now stands at {context['workflow_agent_count']} workflow agents and {context['total_multi_turn_tools']} built-in Multi-Turn tools ({context['core_python_tool_count']} core + {context['wrapped_chat_agent_count']} wrapped + {context['acpx_tool_count']} ACPX/Skill + {context['external_mcp_supervisor_count']} External-MCP supervisors), with {context['skills_count']} skills; dynamic ext__ remotes are separate.",
    ], THEME["jade"], "monday-b", 10)
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

    slide, audit = add_slide(prs, "Line Inventory Method", "reproducible source measurements", THEME["copper"])
    add_panel(slide, audit, 0.82, 1.65, 11.55, 4.9, "Counting boundary", [
        "The primary inventory uses git ls-files. Nonignored untracked additions, when present, are labeled separately. Ignored build output, caches and environments are excluded.",
        f"{len(context['missing_paths'])} index paths are absent locally (pending deletions): retained in the index tree, excluded from line and binary totals.",
        "Physical lines include blanks and comments in text files. Effective lines exclude blank and comment-only lines. Python also excludes module, class and function docstrings identified by AST parsing.",
        "Executable Python multiline strings count every nonblank occupied line. The 2026-09-12 correction replaced the token-start-only undercount. Comparisons with earlier dossiers require recounting them.",
        "Other languages use comment stripping rather than semantic execution analysis. Markdown counts authored nonblank documentation. Binary and media assets have no source-line count. Published historical source snapshots contribute text lines but do not increase runtime module or agent totals.",
        "The generated context JSON retains per-file physical/effective counts, per-language totals and all inventory paths. Both dossiers contain the complete repository tree and a separate new-asset appendix.",
    ], THEME["copper"], "line-method", 17)
    audit_layout(audit, len(prs.slides))

    if context["missing_paths"]:
        slide, audit = add_slide(prs, "Pending Working-Tree Deletions", "Git-index entries absent locally; unrelated user changes preserved", THEME["amber"])
        add_text(slide, audit, 0.85, 1.72, 11.7, 4.85, "\n".join(context["missing_paths"]), 11,
                 THEME["white"], False, name="missing-paths", font="Cascadia Mono")
        audit_layout(audit, len(prs.slides))

    recent_highlight_chunks = split_items(context["weekly_highlights"], 5)
    for idx, chunk in enumerate(recent_highlight_chunks, 1):
        slide_title = (
            RECENT_GIT_WINDOW_TITLE
            if len(recent_highlight_chunks) == 1
            else f"{RECENT_GIT_WINDOW_TITLE} ({idx}/{len(recent_highlight_chunks)})"
        )
        slide, audit = add_slide(prs, slide_title, "recent changes according to git history", THEME["amber"])
        add_panel(slide, audit, 0.82, 1.65, 11.55, 4.9, RECENT_GIT_HIGHLIGHT_TITLE, chunk, THEME["amber"], f"latest-{idx}", 15)
        audit_layout(audit, len(prs.slides))

    visual_chunks = split_items(context["visual_doc_commits"], 6)
    for idx, chunk in enumerate(visual_chunks, 1):
        slide, audit = add_slide(
            prs,
            f"Visual Dossier Change Appendix {idx}/{len(visual_chunks)}",
            "commits since the last committed PDF/PPTX refresh",
            THEME["jade"] if idx % 2 else THEME["copper"],
        )
        visual_lines = [f"{iso_date(c.committed_at)} | {c.short_hash} | {c.subject}" for c in chunk]
        add_panel(slide, audit, 0.82, 1.68, 11.55, 4.86, "Commit timeline", visual_lines, THEME["jade"] if idx % 2 else THEME["copper"], f"visual-{idx}", 12)
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
    if len(tree_chunks) > 1:
        final_lines = tree_chunks[-1].splitlines()
        previous_lines = tree_chunks[-2].splitlines()
        if len(final_lines) < 20 and len(previous_lines) > 20:
            moved = min(20 - len(final_lines), len(previous_lines) - 20)
            tree_chunks[-2] = "\n".join(previous_lines[:-moved])
            tree_chunks[-1] = "\n".join(previous_lines[-moved:] + final_lines)
    for idx, chunk in enumerate(tree_chunks, 1):
        slide, audit = add_slide(
            prs,
            f"Repository File Tree - {idx} of {len(tree_chunks)}",
            "complete repository inventory tree, including git-unignored working additions",
            THEME["jade"] if idx % 2 else THEME["copper"],
        )
        add_text(slide, audit, 0.72, 1.56, 11.95, 5.42, chunk, 7, THEME["white"], False, name=f"tree-{idx}", font="Cascadia Mono")
        audit_layout(audit, len(prs.slides))

    for idx, chunk in enumerate(split_items(context["new_assets"], 10), 1):
        slide, audit = add_slide(prs, f"New Asset Inventory - {idx}",
                                 "since last committed dossier, including untracked working additions", THEME["jade"])
        y = 1.65
        for row in chunk:
            metrics = (f"{row['bytes']:,} bytes; {row['kind']}; "
                       + ("binary: no lines" if row["physical"] is None else
                          f"{row['physical']} physical / {row['effective']} effective lines"))
            add_text(slide, audit, 0.8, y, 11.7, 0.22, row["path"], 9, THEME["white"],
                     name=f"asset-path-{y}", font="Cascadia Mono")
            add_text(slide, audit, 0.8, y + 0.22, 11.7, 0.2, metrics, 9, THEME["muted"],
                     name=f"asset-metrics-{y}")
            y += 0.52
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
        "inventory_files": context["inventory_files"],
        "tracked_files": context["tracked_files"],
        "untracked_files": context["untracked_files"],
        "total_effective_lines": context["total_effective_lines"],
        "total_lines": context["total_lines"],
        "workflow_agent_count": context["workflow_agent_count"],
        "agent_description_rows": context["agent_description_rows"],
        "wrapped_chat_agent_count": context["wrapped_chat_agent_count"],
        "core_python_tool_count": context["core_python_tool_count"],
        "acpx_tool_count": context["acpx_tool_count"],
        "external_mcp_supervisor_count": context["external_mcp_supervisor_count"],
        "total_multi_turn_tools": context["total_multi_turn_tools"],
        "skills_count": context["skills_count"],
        "requirements_count": context["requirements_count"],
        "js_modules": context["js_modules"],
        "css_files": context["css_files"],
        "html_templates": context["html_templates"],
        "migrations": context["migrations"],
        "binary_count": context["binary_count"],
        "skipped_count": context["skipped_count"],
        "missing_paths": context["missing_paths"],
        "version": context["version_info"]["version"],
        "version_source": context["version_info"]["source"],
        "version_info": context["version_info"],
        "language_rows": [row.__dict__ for row in context["language_rows"]],
        "largest_files": [row.__dict__ for row in context["file_rows"][:50]],
        "all_text_files": [row.__dict__ for row in context["file_rows"]],
        "inventory_paths": context["inventory_paths"],
        "new_assets": context["new_assets"],
        "pdfjs_inventory": context["pdfjs_inventory"],
        "removed_assets": context["removed_assets"],
        "publication": {key: context[key] for key in (
            "release_identity", "remote_head", "git_describe", "worktree_status",
            "published_files", "published_bytes", "manifest_verified_files", "removed_output_files", "avatar_evidence")},
        "recent_commits": [row.__dict__ for row in context["recent_commits"]],
        "weekly_commits": [row.__dict__ for row in context["weekly_commits"]],
        "weekly_highlights": context["weekly_highlights"],
        "visual_doc_baseline": (
            None
            if context["visual_doc_baseline"] is None
            else context["visual_doc_baseline"].__dict__
        ),
        "visual_doc_commits": [row.__dict__ for row in context["visual_doc_commits"]],
        "visual_doc_highlights": context["visual_doc_highlights"],
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
