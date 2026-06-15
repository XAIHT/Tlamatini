from __future__ import annotations

import ast
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
    subjects = [commit.subject.lower() for commit in commits]
    highlights: list[str] = []
    if any("1.24.0" in subject or "esphomer" in subject for subject in subjects):
        highlights.append(
            "The current Git window establishes the new `v1.24.0` baseline: the latest tag `v1.24.0` sits at commit `eb92877` on June 15, 2026, and the current HEAD `c0c633c` later that same day layers the ESPHomer implementation on top of that version line."
        )
    if has_esphomer_assets():
        highlights.append(
            "The live working tree is already beyond the tagged `v1.24.0` release: ESPHomer is present as a fourth firmware lane, bridging Tlamatini to ESPHome so she can author YAML device configs, validate, compile, upload, and observe smart-home firmware from chat or canvas."
        )
    if any("image about" in subject or "video" in subject or "kyber" in subject for subject in subjects):
        highlights.append(
            "The same window refreshes the visible about/presentation media too: `TlamatiniAbout.png` replaces the old JPEG asset, and `TlamatiniAndKyber.mp4` joins the repository as a new shipped visual asset that the dossier inventory now counts."
        )
    if any("v1.23.0" in subject or "data-preserving self-update" in subject or "migrate users' db on self-update" in subject for subject in subjects):
        highlights.append(
            "The current Git window includes the `v1.23.0` release from June 15, 2026: the in-app updater now preserves the user's database and migrates it back into the new build on first launch, so chat history and custom Tool/Mcp/Agent toggles survive a packaged update."
        )
    if any("numpy/opencv" in subject or ("embed" in subject and ("numpy" in subject or "opencv" in subject)) for subject in subjects):
        highlights.append(
            "The same `v1.23.0` wave hardens frozen builds for the media family: numpy and OpenCV are now embedded in both the carried Python and the frozen `_internal`, and `build.py` fails loudly if either import is missing instead of shipping a broken Recorder / Camcorder / AudioPlayer / VideoPlayer / Whisperer path."
        )
    if any("file-reading" in subject or "file-modification" in subject or "tool-order rule" in subject or "quoted args" in subject for subject in subjects):
        highlights.append(
            "The working tree also advances the file-navigation and file-editing operator surface: the new Globber, Grepper, and Editor agents/tools let Tlamatini discover files by pattern, search contents by regex, and make surgical in-place edits without falling back to a shell command."
        )
    if any("blenderer" in subject or "blender" in subject for subject in subjects):
        highlights.append(
            "The same recent release span still includes the Blenderer foundation: Tlamatini reaches a live Blender session through the official Blender MCP add-on socket (`localhost:9876`), both as the wrapped `chat_agent_blenderer` tool and as a visual workflow node."
        )
    if any("self-update" in subject or "check for updates" in subject or "apply_update.ps1" in subject or "start_update" in subject for subject in subjects):
        highlights.append(
            "The in-app self-update path itself is now mature across the current Git window: packaged installs can check GitHub releases, stage a download, hand the locked-file replacement to `apply_update.ps1`, and preserve both operator state and one `agents_backup` generation."
        )
    if any("1.24.0" in subject or ("documentation" in subject and "1.24.0" in subject) for subject in subjects):
        highlights.append(
            "The latest documentation pass aligns the handbook and source with `v1.24.0`, which matters here because some older badges or prose lines still lag behind the live 81-agent / 88-tool inventory."
        )
    if any("filecreator" in subject or "file creator" in subject or ("truncate" in subject and "file" in subject) for subject in subjects):
        highlights.append(
            "The `v1.19.5` File-Creator hardening pass now writes content byte-for-byte: plain `content` is re-extracted verbatim, and heavy escape/binary payloads can travel through `content_b64`, eliminating the wrong-symbol corruption that broke backslash-dense Java, JSON, and regex files."
        )
    if any("source code as the codebase" in subject or "self modify" in subject or "copy_source_assets" in subject or "source snapshot" in subject for subject in subjects):
        highlights.append(
            "The same release completes the self-modify story: `build.py --self-modify` now generates a rebuildable `TlamatiniSourceCode/` snapshot through `copy_source_assets.py`, so a self-able-modify build carries her own source tree, rebuild instructions, and redacted secrets in one honest package."
        )
    if any("api-keys wizard" in subject or "api keys wizard" in subject or ("api" in subject and "wizard" in subject) for subject in subjects):
        highlights.append(
            "Operator ergonomics improved too: the Config menu now includes an API-Keys Wizard dialog, giving the user a browser-side way to enter and persist provider credentials without hand-editing `config.json`."
        )
    if any("talker" in subject or "whisperer" in subject or "recorder" in subject or "camcorder" in subject or "audio" in subject for subject in subjects):
        highlights.append(
            "The recent media-and-voice wave is still visible in Git: Talker and Whisperer extend Tlamatini from text-only operation into female-voice text-to-speech plus speech-to-text, while Recorder/Camcorder/Shoter/AudioPlayer/VideoPlayer complete the broader media I/O family."
        )
    if any("watchdog" in subject or "hung command" in subject or "hanged" in subject for subject in subjects):
        highlights.append(
            "Runtime resilience advanced as well: the autonomous command watchdog can now detect shell wrappers that are alive but making no CPU or I/O progress, then reap only the wedged console-interpreter subtree without touching healthy long-running work."
        )
    if any("audioplayer" in subject or "videoplayer" in subject or ("playback" in subject and ("audio" in subject or "video" in subject)) for subject in subjects):
        highlights.append(
            "New media-playback pair completes the media-I/O family: AudioPlayer plays an audio file to the speakers (soundfile + sounddevice, volume and a truncate/loop time budget) and VideoPlayer plays a video file with audio on a chosen display (ffpyplayer — its wheel bundles ffmpeg + SDL — plus an OpenCV window, with display/volume/time-budget/window/fullscreen). Both are observational/output, on the canvas and as wrapped chat_agent_audioplayer / chat_agent_videoplayer tools."
        )
    if any("camcorder" in subject or "recorder" in subject for subject in subjects):
        highlights.append(
            "New observational capture pair: Camcorder (webcam photo/video via OpenCV) and Recorder (microphone WAV via sounddevice) — read-only siblings of Shoter, on the canvas and as wrapped chat_agent_camcorder / chat_agent_recorder tools."
        )
    if any("arduiner" in subject or "arduino" in subject for subject in subjects):
        highlights.append(
            "Arduiner added as the third microcontroller agent: a direct arduino-cli bridge that builds and uploads firmware for any fqbn-selected board, with zero-config bootstrap, auto board-core install, and a serial-port safety preflight."
        )
    if any("flow-making" in subject or "flow making" in subject or "flw" in subject for subject in subjects):
        highlights.append(
            "The new in-process flow-making skill turns a plain objective into a canvas-loadable .flw by driving the FlowCreator engine, so operators build runnable flows straight from chat."
        )
    if any("temp/template" in subject or "template generation" in subject for subject in subjects):
        highlights.append(
            "Directory policy: every transient file now stays under <app>/Temp and every scaffolded firmware/engine project tree under <app>/Templates (never C:/Temp or %TEMP%), pinned before Django starts."
        )
    if any("esp32er" in subject or "es32er" in subject or "platformio" in subject for subject in subjects):
        highlights.append(
            "The embedded-firmware surface remains broad in the current tree: ESP32er keeps the direct PlatformIO Core path for scaffold/build/upload/monitor work, STM32er and Arduiner cover the other hardware lanes, and the live working tree now adds ESPHomer as the ESPHome smart-home device bridge."
        )
    if any("asking on the chain of multi-turn" in subject or "ask exec" in subject or "execution interrupted" in subject for subject in subjects):
        highlights.append(
            "Human approval remains part of the modern safety story too: Ask Execs can still stop Multi-Turn before the next state-changing step, wait for a Proceed or Deny decision, and surface denial through the explicit red interruption banner."
        )
    if any("stm32" in subject or "stmer" in subject or "firmware" in subject and "hardware" in subject for subject in subjects):
        highlights.append(
            "The firmware-control branch remains active in the current codebase: STM32er still bridges the STM32 Template Project MCP for scaffold/build/flash/observe/reset flows, guarded by a fail-safe hardware preflight before unsafe mutations."
        )
    if any("herself" in subject or "self" in subject and "modify" in subject or "self knowledge" in subject for subject in subjects):
        highlights.append(
            "Self-awareness is now part of the steady baseline rather than a one-off milestone: Tlamatini carries a first-person self-knowledge map and, in self-modify builds, can inspect the bundled source snapshot that describes how she actually works."
        )
    if any("4096" in subject or "degrees of liberty" in subject or "turn" in subject and "freedom" in subject for subject in subjects):
        highlights.append(
            "Multi-Turn autonomy expanded too: the default iteration ceiling now reaches 4096 turns, giving long operator chains far more room before they hit the loop cap."
        )
    if any("unrealer" in subject or "unreal mcp" in subject or "xaiht" in subject for subject in subjects):
        highlights.append(
            "Unrealer kept growing across the same window: the docs now point at the public `XAIHT/XaihtUnrealEngineMCP` fork and the full 53-command, nine-category Unreal MCP surface it exposes to chat and canvas."
        )
    if any("kalier" in subject or "kali" in subject or "pentest" in subject for subject in subjects):
        highlights.append(
            "A still-relevant platform branch remains the Kali Linux bridge: Kalier behaves as the embedded MCP-Kali-Server client, so the Kali box URL is configured once in `Config -> URLs` and auto-injected into `chat_agent_kalier` runs."
        )
    if any("windower" in subject or "window manager" in subject or "window" in subject and "multi-turn" in subject for subject in subjects):
        highlights.append(
            "Another still-visible platform branch is Windower: a deterministic Win32 window-manager surface for focusing, tiling, resizing, listing, and closing windows from both Multi-Turn chat and the visual canvas."
        )
    if any("playwrighter" in subject or "playwright" in subject for subject in subjects):
        highlights.append(
            "Playwrighter remains part of the broader platform story too: a real-browser automation surface for scripted Playwright flows from both Multi-Turn chat and the visual canvas."
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
            "A still-relevant reviewer follow-up is the behavioral-accuracy patch: the review prompt distinguishes uncommitted working-tree diffs from committed history and teaches the model Tlamatini’s managed-secret scrub convention, reducing false positives around local credentials in config files."
        )
    if any("reviewer" in subject or "analyzer" in subject or "security audit" in subject or "code review" in subject for subject in subjects):
        highlights.append(
            "A still-visible platform branch is Reviewer and Analyzer: code review plus deterministic security scanning are available from both the canvas and the skill layer."
        )
    if any("number and descriptions of agents" in subject or "markdowns" in subject or "agentic_skill" in subject for subject in subjects):
        highlights.append(
            "Agent-catalog consistency work also remains visible: the live count, the markdown bestiaries, the flow-creator skill catalog, and the sidebar-description source were brought back into alignment around one shared workflow-agent inventory."
        )
    if any("unreal" in subject or "unreal-engine mcp" in subject or "unreal engine enabled" in subject for subject in subjects):
        highlights.append(
            "Unreal MCP support remains part of the broader platform story: the Unrealer agent, its chat-wrapped tool, canvas wiring, seeded prompts, and the direct TCP bridge into a live Unreal Engine 5 editor."
        )
    if any("orphan" in subject or "cleanup" in subject or "sec/perf" in subject for subject in subjects):
        highlights.append(
            "Windows process hygiene also remains visible in recent history: a three-tier reaper, hardened detached spawn sites, ACPX process-tree termination, and user-visible survivor reporting when anything truly refuses to die."
        )
    if any("de-compresser" in subject or "de compresser" in subject for subject in subjects):
        highlights.append(
            "The archive-automation branch remains visible too: De-Compresser adds deterministic archive compression/decompression, Multi-Turn exposure, ACP canvas wiring, and the `py7zr` fallback path."
        )
    if any("version" in subject or "worldwide system" in subject for subject in subjects):
        highlights.append(
            "Release-identity work also remains relevant: the SemVer policy, git-tag sourcing, runtime version surfaces, and build-time embedding across the Windows artefacts now define how Tlamatini reports her version."
        )
    if any("menu db" in subject or "database" in subject or "browse buttons" in subject for subject in subjects):
        highlights.append(
            "Another still-relevant operator-facing branch is the DB dropdown: backup, Set DB staging for the next start-up, startup swap-in/rollback mechanics, and native Browse buttons on both dialogs."
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
    if any("kimi-k2.6:cloud" in subject or "default in config.json" in subject for subject in subjects):
        highlights.append(
            "The checked-in runtime defaults also moved: the shared config now points at `kimi-k2.6:cloud`, so the handbook and dossier need to describe the shipped cloud-first baseline honestly instead of assuming only the older local model defaults."
        )
    if any("attention" in subject or "flash" in subject or "notifications" in subject or "notifier" in subject for subject in subjects):
        highlights.append(
            "Operator attention routing also changed: when Ask Execs or a Notifier event needs the user, Tlamatini can now flash her own Windows taskbar presence and write an uppercase attention banner into `tlamatini.log`."
        )
    if any("pythonxer" in subject or "forked windows execution" in subject or "reporting on the log file" in subject or "project skills" in subject for subject in subjects):
        highlights.append(
            "Follow-up implementation work in the same post-STM32 window tightened Pythonxer downstream execution, Windows forked-command launching, execution-log detail, and project-skill loading, so the release story is not only a UI toggle but also a reliability pass around the operator chain."
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
            "Documentation itself changed during the recent window, so the regenerated dossier is part of the tracked operator surface rather than an external afterthought."
        )
    if highlights:
        return highlights
    return [f"Git history shows focused maintenance across the operator surface, release mechanics, and runtime behavior during {RECENT_GIT_WINDOW_LABEL}."]


def visual_doc_highlights(commits: list[CommitInfo]) -> list[str]:
    subjects = [commit.subject.lower() for commit in commits]
    highlights: list[str] = []
    if any("1.24.0" in subject or "esphomer" in subject for subject in subjects):
        highlights.append(
            "Since the last committed PDF/PPTX refresh, the repository moved onto the `v1.24.0` version line: tag `eb92877` establishes the new release identity, and HEAD `c0c633c` adds the ESPHomer implementation on top of it."
        )
    if has_esphomer_assets():
        highlights.append(
            "The live workspace now includes the untagged ESPHomer wave: a new ESPHome firmware agent, wrapped `chat_agent_esphomer` tool, sample YAML project, migrations, tests, and handbook chapters that extend Tlamatini into smart-home device provisioning."
        )
    if any("image about" in subject or "video" in subject or "kyber" in subject for subject in subjects):
        highlights.append(
            "The same span also refreshes the shipped visual media: the old `TlamatiniAbout.jpg` gives way to `TlamatiniAbout.png`, and `TlamatiniAndKyber.mp4` is now part of the repository asset tree and line/inventory context."
        )
    if any("v1.23.0" in subject or "data-preserving self-update" in subject or "migrate users' db on self-update" in subject for subject in subjects):
        highlights.append(
            "Since the last committed PDF/PPTX refresh, `v1.23.0` made packaged self-update data-preserving: the user's database is staged through `DB/ToLoad/`, restored into the new build, and migrated on next launch so chat history and custom toggles survive the upgrade."
        )
    if any("numpy/opencv" in subject or ("embed" in subject and ("numpy" in subject or "opencv" in subject)) for subject in subjects):
        highlights.append(
            "The same window also embedded numpy and OpenCV into both shipped Python runtimes, closing the frozen-build dependency gap for Recorder, Camcorder, AudioPlayer, VideoPlayer, and Whisperer."
        )
    if any("file-reading" in subject or "file-modification" in subject or "tool-order rule" in subject or "quoted args" in subject for subject in subjects):
        highlights.append(
            "The operator surface also expanded with the file-navigation/file-edit trio: Globber, Grepper, and Editor now exist as workflow agents and wrapped chat tools, giving Tlamatini deterministic file discovery, regex search, and surgical in-place edit steps."
        )
    if any("blenderer" in subject or "blender" in subject for subject in subjects):
        highlights.append(
            "Since the last committed PDF/PPTX refresh, Blenderer entered the platform: a live Blender bridge over the official MCP add-on socket, available both on the canvas and as `chat_agent_blenderer`."
        )
    if any("self-update" in subject or "check for updates" in subject or "apply_update.ps1" in subject or "start_update" in subject for subject in subjects):
        highlights.append(
            "The same refresh window also delivered the in-app self-update path: `self_update.py`, new update endpoints, staged release downloads, and the external `apply_update.ps1` swap helper that preserves operator state during upgrade."
        )
    if any("1.24.0" in subject or ("documentation" in subject and "1.24.0" in subject) for subject in subjects):
        highlights.append(
            "The latest versioning/documentation commits move the source-of-truth product story to `v1.24.0`, and this refresh layers the live ESPHomer working-tree additions on top of that tag so the dossier matches the current 81-agent / 88-tool runtime surface."
        )
    if any("filecreator" in subject or "file creator" in subject or ("truncate" in subject and "file" in subject) for subject in subjects):
        highlights.append(
            "Since the last committed PDF/PPTX refresh, `v1.19.5` hardened File-Creator with a byte-exact write path: verbatim `content` plus a `content_b64` channel now preserve backslash-heavy and binary payloads without wrong-symbol corruption."
        )
    if any("source code as the codebase" in subject or "self modify" in subject or "copy_source_assets" in subject or "source snapshot" in subject for subject in subjects):
        highlights.append(
            "The same release also completes the self-modify packaging story: `build.py --self-modify` now uses `copy_source_assets.py` to generate a rebuildable `TlamatiniSourceCode/` snapshot with redacted secrets, omitted heavy media, and rebuild instructions carried beside the application."
        )
    if any("api-keys wizard" in subject or "api keys wizard" in subject or ("api" in subject and "wizard" in subject) for subject in subjects):
        highlights.append(
            "A new operator-facing convenience layer landed too: Config now exposes an API-Keys Wizard dialog so cloud-provider credentials can be entered and updated from the browser instead of by manually editing `config.json`."
        )
    if any("watchdog" in subject or "hung command" in subject or "hanged" in subject for subject in subjects):
        highlights.append(
            "Recent runtime hardening added the autonomous command watchdog: a boot-time daemon thread that samples CPU and I/O progress across shell-interpreter subtrees and reaps only the genuinely wedged ones, closing the gap left by timeouts and post-return orphan cleanup."
        )
    if any("audioplayer" in subject or "videoplayer" in subject or ("playback" in subject and ("audio" in subject or "video" in subject)) for subject in subjects):
        highlights.append(
            "Since the last committed PDF/PPTX refresh, the media-PLAYBACK pair landed and completed the media-I/O family: AudioPlayer plays an audio file to the speakers (soundfile + sounddevice — volume in percent and a time-played budget that truncates a longer file or loops a shorter one), and VideoPlayer plays a video file with audio on a chosen display (ffpyplayer, whose wheel bundles ffmpeg + SDL, plus an OpenCV window — display, volume, the same time budget, window size, and fullscreen). Both are observational/output and ship on the canvas and as wrapped chat_agent_audioplayer / chat_agent_videoplayer tools."
        )
    if any("camcorder" in subject or "recorder" in subject for subject in subjects):
        highlights.append(
            "New observational capture pair: Camcorder (webcam photo/video via OpenCV) and Recorder (microphone WAV via sounddevice) — read-only siblings of Shoter, on the canvas and as wrapped chat_agent_camcorder / chat_agent_recorder tools."
        )
    if any("arduiner" in subject or "arduino" in subject for subject in subjects):
        highlights.append(
            "Arduiner added as the third microcontroller agent: a direct arduino-cli bridge that builds and uploads firmware for any fqbn-selected board, with zero-config bootstrap, auto board-core install, and a serial-port safety preflight."
        )
    if any("flow-making" in subject or "flow making" in subject or "flw" in subject for subject in subjects):
        highlights.append(
            "The new in-process flow-making skill turns a plain objective into a canvas-loadable .flw by driving the FlowCreator engine, so operators build runnable flows straight from chat."
        )
    if any("temp/template" in subject or "template generation" in subject for subject in subjects):
        highlights.append(
            "Directory policy: every transient file now stays under <app>/Temp and every scaffolded firmware/engine project tree under <app>/Templates (never C:/Temp or %TEMP%), pinned before Django starts."
        )
    if any("esp32er" in subject or "es32er" in subject or "platformio" in subject for subject in subjects):
        highlights.append(
            "The embedded-firmware branch remains part of the current product story too: ESP32er keeps the PlatformIO path for scaffold/build/upload/monitor work, while the broader handbook now needs to present the firmware stack as STM32er + ESP32er + Arduiner + ESPHomer rather than a smaller trio."
        )
    if any("asking on the chain of multi-turn" in subject or "ask exec" in subject or "execution interrupted" in subject for subject in subjects):
        highlights.append(
            "The human-in-the-loop gate remains current: Ask Execs can still pause before each state-changing Multi-Turn step, wait for Proceed or Deny through `ExecPermissionBroker`, and halt the chain safely with the explicit red interruption banner."
        )
    if any("stm32" in subject or "stmer" in subject or "firmware" in subject and "hardware" in subject for subject in subjects):
        highlights.append(
            "The STM32 branch is still active in the same modern operator surface: STM32er remains the bridge into the STM32 Template Project MCP for scaffold/build/flash/observe/reset workflows guarded by a critical preflight."
        )
    if any("self" in subject and ("herself" in subject or "modify" in subject or "source code" in subject) for subject in subjects):
        highlights.append(
            "The self-knowledge and optional self-modification surface has matured into the current baseline: she can describe her runtime honestly and, when `TlamatiniSourceCode/` is present, inspect the bundled rebuildable source tree that explains how she works."
        )
    if any("4096" in subject or "degrees of liberty" in subject or "turn" in subject and "freedom" in subject for subject in subjects):
        highlights.append(
            "The same window raised the default Multi-Turn iteration ceiling from 256 to 4096, making long autonomous operator chains practical without an early loop-cap failure."
        )
    if any("unrealer" in subject or "unreal mcp" in subject or "xaiht" in subject for subject in subjects):
        highlights.append(
            "Unrealer advanced substantially too: the docs now point at the public `XAIHT/XaihtUnrealEngineMCP` fork and the full 53-command Unreal MCP surface, with new demos and better parameter-path guidance."
        )
    if any("kalier" in subject or "kali" in subject for subject in subjects):
        highlights.append(
            "Kalier also matured during the same span: `v1.7.1` made Tlamatini the embedded MCP-Kali-Server client for chat-side runs, so operators configure the Kali box once in `Config -> URLs` instead of repeating it in every prompt."
        )
    if any("kimi-k2.6:cloud" in subject or "default in config.json" in subject or "pythonxer" in subject or "forked windows execution" in subject or "project skills" in subject or "reporting on the log file" in subject for subject in subjects):
        highlights.append(
            "The same span also refined the shipped operating baseline: handbook simplification, a `kimi-k2.6:cloud` checked-in default, stronger execution logging, Pythonxer downstream fixes, Windows forked-process polish, and cleaner project-skill loading."
        )
    if any("attention" in subject or "flash" in subject or "notifications" in subject or "notifier" in subject for subject in subjects):
        highlights.append(
            "Since the last committed PDF/PPTX refresh, operator attention handling moved to a concrete Windows path: browser-side Ask Execs and Notifier events can call `/agent/flash_window/`, which lets Tlamatini flash her own taskbar button and persist an uppercase attention banner in `tlamatini.log`."
        )
    if any("esp32 template project" in subject or "template project" in subject and "esp32" in subject for subject in subjects):
        highlights.append(
            "The same span also documented the `ESP32TemplateProject` reference repository: a plain PlatformIO project that gives ESP32er a known-good, GitHub-ready firmware baseline for build, upload, and serial-monitor verification."
        )
    if any("doc" in subject or "markdown" in subject or "graphical" in subject for subject in subjects):
        highlights.append(
            "The markdown handbooks themselves were revised during that span, so this dossier refresh is carrying forward not only code/runtime changes but also the corrected operator-language and release-story wording."
        )
    if highlights:
        return highlights
    return ["Since the last committed PDF/PPTX refresh, Git shows focused platform evolution across autonomy, operator ergonomics, runtime self-knowledge, and documentation fidelity."]


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
        return {"version": override, "build": override, "commit": "override", "date": "", "source": "env"}
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
    tracked = git_tracked_paths()
    untracked = git_untracked_paths()
    paths = inventory_paths()
    tree_text = build_tree(paths)
    language_rows, file_rows, binary_count, skipped_count = line_stats_for_paths(paths)
    total_effective = sum(row.effective_lines for row in language_rows)
    total_lines = sum(row.total_lines for row in language_rows)
    agents = workflow_agents()
    wrapped_chat_tools = count_wrapped_chat_agent_tools()
    skills_count = count_skills()
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
        "visual_doc_baseline": visual_baseline,
        "visual_doc_commits": visual_commits,
        "visual_doc_highlights": visual_doc_highlights(visual_commits),
        "reference_media": reference_media,
        "version_info": version_info,
    }
    return context


SYSTEM_OVERVIEW = [
    "Tlamatini is a self-hosted AI developer assistant (cloud LLMs by default; the app and RAG run locally) built with Django, Django Channels, LangChain, LangGraph, FAISS/BM25 retrieval, and a large in-repository agent application.",
    "She combines a browser chat surface, a Retrieval-Augmented Generation stack, a Multi-Turn tool executor, MCP-backed context providers, wrapped chat-agent runtimes, and a visual Agentic Control Panel for workflow design.",
    "She is designed for development operations: codebase analysis, file and directory context, deterministic file discovery/search/editing, command execution, Python execution, screenshots, web/search helpers, notifications and attention routing, DevOps tools, local model operation, Windows packaging and uninstall registration, first-person self-knowledge about her own runtime, and embedded-firmware control for STM32F4, ESP32-class, Arduino-class, and ESPHome smart-home boards.",
]

WHAT_IT_DOES = [
    "Answers codebase questions with loaded file or directory context.",
    "Uses hybrid retrieval to extract metadata, split content, rank source chunks, and respect context budgets.",
    "Can discover files by glob pattern, search their contents by regex, and make surgical in-place replacements through the Globber, Grepper, and Editor agent/tool trio.",
    "Gives operators GUI-first database maintenance through the new DB dropdown for backup and staged database replacement.",
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
    "Can scaffold, author, build, flash, reset, and observe STM32F4 firmware through STM32er and the STM32 Template Project MCP, with a fail-safe preflight before any hardware mutation.",
    "Can scaffold, author, build, upload, and monitor ESP32-class firmware through ESP32er and PlatformIO Core, with zero-config bootstrap and a serial-aware preflight before hardware mutation.",
    "Can author YAML-based smart-home firmware through ESPHomer and ESPHome, including zero-config bootstrap, device-config generation, validation, compile, USB/OTA upload, and bounded log observation for ESP32 / ESP8266 / RP2040 / BK72xx devices.",
    "Can play media on the operator's machine: an audio file to the speakers through AudioPlayer (soundfile + sounddevice — volume in percent and a time-played budget that truncates a longer file or loops a shorter one), or a video file with audio on a chosen display through VideoPlayer (ffpyplayer, whose wheel bundles ffmpeg + SDL, plus an OpenCV window — display, volume, the same truncate/loop time budget, window size, and fullscreen); both are observational/output and ship on the canvas and as wrapped chat tools.",
    "Can SPEAK and LISTEN: Talker (text-to-speech) renders input_text to a 24 kHz WAV through an Ollama neural TTS model (default Orpheus-3b-FT) and is female-voice-only by design, while Whisperer (speech-to-text) records the microphone itself or transcribes a file via faster-whisper locally (NVIDIA-GPU auto-detect with an always-present CPU fallback) or a cloud Whisper API; both light a zero-latency console REC indicator driven by the live audio stream and are observational/output, on the canvas and as wrapped chat tools.",
    "Can manage real desktop windows by title: focus them, tile them, resize them, list them, and close them deterministically through Win32 calls.",
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
    "RAG chains load selected file/directory context, retrieve relevant chunks, and build answer prompts.",
    "DB-menu actions validate directories or SQLite files in the browser, then call Django views that either copy the live database out or stage a replacement into `DB/ToLoad/db.sqlite3`.",
    "Config -> Access Keys Wizard reads masked provider-key status from the backend and persists only the edited secrets, keeping the browser flow honest without dumping live values back to the page.",
    "The file-navigation and file-edit trio sits above raw shell execution: Globber enumerates matching files, Grepper scans content with regex while pruning noisy/binary trees, and Editor performs byte-exact in-place replacements without rewriting an entire file.",
    "Blenderer opens the official Blender MCP add-on TCP socket (default `localhost:9876`), sends one action payload or raw code-execution request, and returns the structured result through the same wrapped-tool / canvas contract used by the rest of the agent catalog.",
    "When Ask Execs is enabled, the synchronous Multi-Turn executor stops before each state-changing tool call, emits an `exec_permission_request`, and waits on `ExecPermissionBroker` until the browser sends Proceed or Deny.",
    "When the browser surfaces an Ask Execs prompt or a Notifier event, JavaScript can POST to `/agent/flash_window/`; the backend then best-effort flashes the `Tlamatini.exe` console/taskbar window through `window_flash.py` and prints an uppercase attention banner for the log.",
    "Installer-time registration writes a per-user HKCU Add/Remove Programs entry pointing at `Uninstaller.exe`, and frozen startup re-checks that entry through `windows_app_registration.self_heal_for_frozen()` so older installs retroactively appear in Windows' uninstall surfaces.",
    "In-app self-update uses Django views plus `self_update.py` to check GitHub releases, download and stage the selected package, then hand off the locked-file swap to the external `apply_update.ps1` helper before relaunch.",
    "Frozen-build hardening now verifies media dependencies during packaging too: `build.py` embeds numpy and OpenCV in both shipped Python runtimes and refuses to produce a release if those imports are missing.",
    "Before a heavy directory embedding run on supported NVIDIA hosts, a fail-open pre-flight guard can estimate VRAM pressure and surface a non-blocking warning in chat.",
    "Version resolution now flows through git tags, a runtime resolver module, generated build artefacts, and an open `/agent/version/` endpoint.",
    "A first-person self-knowledge file (`Tlamatini.md`) is injected into prompt construction for all chains, but loaded user context still outranks that self-reference when the request is a generic summary of the provided project.",
    "When Multi-Turn is enabled, the global planner selects context and tool stages before the executor binds only the relevant tools, including wrapped deterministic agents such as De-Compresser.",
    "Optional self-modify builds bundle `TlamatiniSourceCode/`; `copy_source_assets.py` generates that snapshot with rebuild instructions and redacted secrets, and prompt rules require her to verify that directory exists before claiming she can inspect or change her own code.",
    "The Kalier path talks directly to the MCP-Kali-Server Flask API over HTTP with Python-stdlib `urllib`, auto-seeding the default box from `kali_server_url` in Config -> URLs before any one-off per-call override is applied, and captures one atomic `INI_SECTION_KALIER` block per run.",
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
    "On the next full start-up, `manage.py` can swap a staged database into place before Django imports, while archiving the previous live database under `DB/Older/<timestamp>/`.",
    "ACP flows deploy session-scoped pool instances, wire config values, validate NxN graph rules, and execute through Starter-driven flow semantics.",
    "Build scripts collect static assets, bundle Django/Python resources, add agent templates, and assemble `pkg.zip`, `Uninstaller.exe`, and `dist/Tlamatini_Release/`; `build.py --self-modify` additionally injects the generated source snapshot for self-rebuildable releases.",
]

HOW_TO_USE = [
    "Run from source: create a virtual environment, install requirements, migrate, create a superuser, collect static files, and start Django.",
    "Open `/agent/` for chat. Load a file or directory context before asking codebase-specific questions.",
    "Keep Multi-Turn unchecked for direct Q&A; enable Multi-Turn for tasks that need tools, wrapped agents, monitoring, or workflow seeding.",
    "Use `chat_agent_globber` to find files by pattern, `chat_agent_grepper` to locate matching content, and `chat_agent_editor` when you need an exact in-place change instead of rewriting a whole file or shelling out to grep/findstr/sed.",
    "Use Config -> Access Keys Wizard when you need to wire or update provider credentials without editing `config.json` manually.",
    "Use About -> Check for updates on packaged installs when you want Tlamatini to fetch and stage the latest release without manually replacing the install folder.",
    "Tick `Ask Execs` when you want human approval before each state-changing Multi-Turn step; it is disabled until Multi-Turn is on, and a single Deny stops the whole chain with an explicit red interruption banner.",
    "When you are using a packaged install on Windows 10 or Windows 11, uninstall it through Settings -> Apps -> Installed apps or the legacy Programs and Features entry, not by manually deleting the folder.",
    "If an Ask Execs approval dialog or a Notifier event needs you while the browser is buried, watch for Tlamatini’s taskbar-attention flash and the matching uppercase banner in `tlamatini.log`.",
    "If you want her to inspect or modify herself, verify that `TlamatiniSourceCode/` exists in the current build first; self-modify is optional and absent builds must be treated honestly as read-only about their own code tree.",
    "For authorized Kali Linux assessments, run MCP-Kali-Server on the Kali box, set `Config -> URLs -> Kali server (Kalier)` once, and then call `chat_agent_kalier` from Multi-Turn with the desired `action` and `target` without repeating the box URL each turn.",
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
    "Specialized agents now stretch the platform in different directions: Globber/Grepper/Editor cover deterministic file discovery, regex search, and surgical in-place edits; ACPXer drives external coding-agent CLIs; Kalier drives a remote or tunneled Kali Linux tool server; STM32er drives a zero-config STM32 firmware MCP bridge; ESP32er drives PlatformIO directly; ESPHomer drives ESPHome directly for YAML-authored smart-home devices; Blenderer drives a live Blender editor over the official MCP add-on socket; Unrealer drives a live UE5 editor; and TeleTlamatini / WhatsTlamatini bridge full Tlamatini conversations into messaging platforms.",
]

ACPX_SKILLS_GUIDE = [
    "The new `ACPX-Skills` navbar menu gives operators four direct actions over the skill catalog: Browse Skills, Configure Skills, Diagnostics, and Reload Registry.",
    "`Configure Skills` flips `Skill.enabled` exactly the way MCPs and Tools are toggled, so disabled skills disappear from `list_skills` and reject `invoke_skill` with `SKILL_DISABLED` instead of silently half-working.",
    "The diagnostics view cross-checks skill dependencies against disabled tools, disabled MCPs, missing ACPX agents, and orphan database rows whose SKILL.md disappeared from disk.",
]

def operator_surface_counts_guide(context: dict) -> list[str]:
    return [
        f"The live operator surface now stands at {context['workflow_agent_count']} workflow agents, {context['total_multi_turn_tools']} Multi-Turn tools, {context['acpx_tool_count']} ACPX tools, and {context['skills_count']} skills.",
        f"Source inspection confirms the total: {context['wrapped_chat_agent_count']} distinct wrapped chat-agent tools bound from `chat_agent_registry.py`, which combines with {context['core_python_tool_count']} core Python tools and {context['acpx_tool_count']} ACPX/Skill tools for {context['total_multi_turn_tools']} Multi-Turn tools overall.",
        "The count increase over the older 77/84 story now comes from two waves together: the deterministic file-navigation/file-edit trio — Globber, Grepper, and Editor — plus ESPHomer, the new ESPHome smart-home firmware lane. All four exist both on the visual canvas and as wrapped chat-agent tools.",
        "The workflow-agent and wrapped-tool totals are validated from the live tree even when some handbook badges or older prose lines lag behind the newest release wave, so the dossier stays tied to source truth instead of stale summaries.",
        "This matters operationally because the planner never binds everything at once: the documented default `max_selected_tools` cap stays at 20, so breadth of capability does not mean uncontrolled tool sprawl per turn.",
    ]

CURRENT_RELEASE_GUIDE = [
    "The repository currently resolves to `v1.24.0` from the latest tag `eb92877` dated June 15, 2026; the current HEAD `c0c633c` later the same day keeps that version line and layers the ESPHomer smart-home firmware surface on top of it.",
    "Data-preserving update is the key fix: the live database sits inside the PyInstaller `_internal/` folder, which an update replaces wholesale, so a naive swap would wipe chat history and custom toggles. `apply_update.ps1` now stages the user's database through `DB/ToLoad/` and drops a `post_update_migrate.flag`; on the next launch `manage.py` swaps that database back over the freshly shipped one and runs `migrate` in a child process, so the user keeps their history and toggles and still receives new agent / tool / prompt rows.",
    "The second pillar is media-agent reliability: numpy and OpenCV (`cv2`) are now embedded in both the carried Python that runs the pool agents and the frozen `_internal`, with `build.py` asserting both imports so the build aborts loudly rather than shipping a Recorder, Camcorder, AudioPlayer, VideoPlayer, or Whisperer that would crash at runtime for a missing native library.",
    "The broader operator surface around this release is larger too: Globber, Grepper, and Editor give Tlamatini deterministic file discovery, regex search, and surgical in-place editing, and the current HEAD extends the firmware stack further with ESPHomer for ESPHome-based smart-home devices.",
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
    "Recent assets worth calling out explicitly now span several release waves: `agent/self_update.py` plus `apply_update.ps1` for the data-preserving updater, `build.py` for numpy/OpenCV embedding checks, the `agent/agents/{editor,grepper,globber}/` directories plus their migrations/tests for deterministic file discovery, and the new `agent/agents/esphomer/` tree plus migrations/tests/sample YAML for ESPHome-based smart-home firmware control.",
    "The current `v1.24.0` window also refreshes shipped visual assets: `TlamatiniAbout.png` replaces the old `TlamatiniAbout.jpg`, and `agent/images/TlamatiniAndKyber.mp4` is now part of the repository asset set described by the dossier.",
    "The same recent window also retains the earlier self-modify/browser-setup asset wave — `copy_source_assets.py`, `agent/access_key_wizard.py`, `static/agent/js/access_keys_wizard.js`, `static/agent/css/access_keys_wizard.css`, and the Blender control surface in `agent/agents/blenderer/`.",
    "Key operator/runtime files such as `prompt.pmt`, `chat_agent_registry.py`, `tools.py`, `views.py`, `urls.py`, `manage.py`, `file_extractor.py`, and the File-Creator/File-Extractor templates also changed, so the visible features are backed by concrete implementation assets rather than documentation-only promises.",
    "Because the dossier already includes the full repository inventory (git-tracked files plus git-unignored working-tree additions) and the full line-count inventory, these named assets serve as the human-readable shortlist of what changed most materially in the latest release wave.",
]

PROMPT_CATALOG_GUIDE = [
    "Version `1.3.2` tightened the HTML answer contract with a Prime Directive on visual readability: explicit background and text color, no grey-on-dark body text, and safer table-body defaults.",
    "The seeded `Prompts` dropdown was also re-sorted into a learner path: context-only Q&A first, then metrics, files search, shell, code generation, vision, specialized single-tool actions, agent control, Unrealer, and heavier Multi-Turn/ACPX demos last.",
    "Those readability rules remain in force in the current documentation set, and the current `v1.24.0` release state keeps the version badge, runtime surfaces, self-knowledge wording, STM32er/ESP32er demo prompts, and operator handbook aligned.",
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
    "Introduced in `v1.10.0` and still part of the current `v1.24.0` surface, `Ask Execs` is the Multi-Turn-only safety modifier that makes Tlamatini ask before each state-changing Tool, MCP, wrapped agent, or skill-backed execution instead of running it immediately.",
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
    "Introduced in `v1.11.0` and still carried by the current `v1.24.0` release, the frozen install now behaves like a real Windows application: `install.py` writes a per-user HKCU Add/Remove Programs entry so Tlamatini appears in Settings -> Apps -> Installed apps and in the legacy Programs and Features list.",
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
    "STM32er is Tlamatini’s current STM32 bridge: she talks to the `STM32 Template Project MCP` so she can scaffold, author, build, flash, reset, and observe STM32F4 firmware without driving STM32CubeIDE manually.",
    "The operator promise is zero-config bootstrap: leave `server_script` blank and STM32er downloads or zip-falls-back to the MCP server on first use, installs `mcp` and `pyserial` if needed, validates, and caches the result so the user only installs STM32CubeIDE plus Tlamatini.",
    "Before any compile-or-hardware action, STM32er runs a critical-mission fail-safe preflight over the arm-none-eabi toolchain, STM32CubeIDE, programmer path, ST-LINK probe, and target family; compile-only steps can run boardless, but flash, erase, reset, serial, and SWD/live-memory operations are refused when the environment or device is wrong.",
]

STM32ER_SURFACES_GUIDE = [
    "Two operator surfaces ship in lock-step: the wrapped Multi-Turn tool `chat_agent_stm32er` takes one `action` per call, while the visual STM32er canvas node stores the same fields in YAML and triggers downstream agents on both success and failure.",
    "The tool surface includes the full project lifecycle plus hardware-in-the-loop composites: `validate`, `bootstrap`, `create_project`, `write_source`, `build`, `build_and_flash`, `serial_session`, `live_monitor`, and the rest of the 23 MCP verbs, with every run emitting an `INI_SECTION_STM32ER` block for Forker or Parametrizer routing.",
    "Config -> URLs now seeds the chat path with `stm32_mcp_server_script`, `stm32_mcp_python`, `stm32_template_dir`, `stm32_ide_root`, `stm32_mcp_repo_url`, and `stm32_mcp_install_dir`, so firmware prompts normally describe only the task and target board instead of the plumbing.",
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
    "The new `ESP32TemplateProject` repository is the known-good baseline documented in BookOfTlamatini’s bonus chapter: a plain PlatformIO project, not a server, meant to prove an ESP32 board and toolchain are healthy before larger firmware work.",
    "It mirrors ESP32er’s grain: `platformio.ini`, `src/`, `include/`, `lib/`, `test/`, a blinking `main.cpp`, serial output at 115200, and GitHub-ready docs/CI so the reference project does not silently rot.",
    "Operationally, ESP32er can either point at a checkout of that template (`project_dir`) or scaffold an equivalent from scratch with `action='create_project'`, then carry the directory through build, upload, and monitor steps.",
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
    "The bundled `ESPHomeTemplateProject` is the known-good ESPHome baseline documented in README and Book: a phone-controllable light with native `api`, `ota`, `wifi`, and a board LED output, shipped as `agent/agents/esphomer/ESPHomeTemplateProject/tlamatini-light.yaml`.",
    "It matters because ESPHomer’s source-of-truth is a YAML device file, not a C++ project tree: that sample proves the first real workflow of `new_config` -> `config` -> `compile` -> `upload` without forcing users to invent a valid starter config from memory.",
    "Operationally, the sample closes the gap between the new agent and a practical first build a user can validate, compile, flash, and then control from a smart-home hub such as Home Assistant.",
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
    "Python 3.12.10 is the strongly recommended source-mode version in the README, and the codebase has been tested most deeply there.",
    "Source installs require a clone, virtual environment, dependency install from `requirements.txt`, migrations, a superuser, static collection, and then the web server.",
    "You can run either the checked-in cloud/back-end defaults from `Tlamatini/agent/config.json` or a local Ollama-backed configuration with matching model names.",
    "Packaged Windows installs create a default `user / changeme` account; manual source installs use your own `createsuperuser` account instead.",
]

CONFIGURATION_GUIDE = [
    "Source mode resolves `Tlamatini/agent/config.json`; frozen builds resolve `config.json` next to the executable; `CONFIG_PATH` overrides both.",
    "Core keys include `embeding-model`, `chained-model`, `ollama_base_url`, `ollama_token`, `enable_unified_agent`, `unified_agent_model`, and `unified_agent_max_iterations`.",
    "The checked-in default model baseline moved again in the recent Git window: the shared config now favors `kimi-k2.6:cloud`, so source or frozen installs that keep the shipped config should be documented as cloud-first unless the operator intentionally swaps models.",
    "URL configuration now also includes `kali_server_url`, the STM32er bootstrap fields `stm32_mcp_server_script`, `stm32_mcp_python`, `stm32_template_dir`, `stm32_ide_root`, `stm32_mcp_repo_url`, and `stm32_mcp_install_dir`, plus ESP32er’s `pio_executable` and `pio_core_dir`, all edited from `Config -> URLs` and inherited automatically by the chat-side wrapped tools.",
    "Credential configuration is no longer hand-edit-only: Config -> Access Keys Wizard provides a browser-side path for ACPX and provider secrets while preserving masked status in the UI.",
    "The chat-side Config -> Models and Config -> URLs dialogs are now first-class configuration surfaces, and they can explicitly ask the operator to reconnect when saved values change live-session assumptions.",
    "The separate DB dropdown is not a config editor: it is a maintenance surface for copying the live SQLite database out or staging a replacement for the next full start-up.",
    "Multi-Turn is toggled from the chat toolbar, but it depends on the unified-agent configuration and the selected model/base-url pairing being valid; the current default iteration ceiling is 4096, and Ask Execs only becomes available when Multi-Turn itself is on.",
    "Image interpretation can run through Claude-backed cloud paths or Qwen/Ollama-backed local paths, and remote Ollama can be protected with a bearer token.",
]

RUNNING_GUIDE = [
    "Development server: `python Tlamatini/manage.py runserver --noreload`.",
    "Preferred async/dev bootstrap: `python Tlamatini/manage.py startserver`, which starts MCP services before the Django server.",
    "Production-style ASGI entrypoint: `daphne -b 127.0.0.1 -p 8000 tlamatini.asgi:application`.",
    "Current startup also re-applies GPU-performance / Ollama-pinning hooks in the background on supported NVIDIA Windows hosts, so restart-time behavior stays closer to the tuned development baseline.",
    "That same early startup window is also where a staged `DB/ToLoad/db.sqlite3` file is promoted into the live database path, before Django opens SQLite.",
    "In frozen mode, startup now also self-heals the per-user Windows Installed-apps entry when `Uninstaller.exe` is present beside `Tlamatini.exe`, so old installs can gain a standard uninstall surface without a reinstall.",
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
    "Exec Report is a Multi-Turn-only transparency layer that appends one operation table per state-changing agent family to the final answer.",
    "Rows are recorded from the live tool-call stream rather than guessed from the LLM prose, so the report is the operational ground truth.",
    "Each row receives a SUCCESS/FAILURE verdict from raw tool returns, making long installs, deployments, and remediations inspectable after the fact.",
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
        "ollama serve",
        "Invoke-WebRequest http://127.0.0.1:11434/api/tags -UseBasicParsing",
        "ollama pull Nomic-Embed-Text:latest",
        "ollama pull kimi-k2.6:cloud",
        "ollama pull qwen3.5:cloud",
        "ollama pull gpt-oss:120b-cloud",
        "ollama pull qwen3.5:397b-cloud",
        "ollama pull glm-5.1:cloud",
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
    ("Execution and files", "executer, pythonxer, pser, file_creator, file_extractor, file_interpreter, de_compresser, playwrighter, windower, unrealer, kalier, stm32er, esp32er, esphomer, arduiner, mover, deleter"),
    ("DevOps and infra", "gitter, dockerer, kuberneter, jenkinser, ssher, scper"),
    ("Data and APIs", "sqler, mongoxer, apirer, crawler, googler"),
    ("Monitoring and routing", "monitor_log, monitor_netstat, flowhypervisor, forker, asker, counter, and, or"),
    ("Communication", "notifier, emailer, recmailer, telegramer, telegramrx, teletlamatini, whatsapper, whatstlamatini"),
    ("Security and media", "kyber_keygen, kyber_cipher, kyber_decipher, image_interpreter, shoter, camcorder, recorder, audioplayer, videoplayer, j_decompiler"),
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


def _table_cell(text: str, font_size: float, *, header: bool) -> Paragraph:
    """Wrap a string cell in a Paragraph so ReportLab word-wraps it inside the
    column width instead of letting a long single-line string overflow the page.
    Long unbreakable tokens (e.g. deep slash-paths) are force-split by
    Paragraph's default splitLongWords behavior."""
    style = ParagraphStyle(
        "TableHeaderCell" if header else "TableBodyCell",
        fontName="Helvetica-Bold" if header else "Helvetica",
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
        author="Tlamatini",
    )
    story: list = []

    cover_image = context["reference_media"][0] if context["reference_media"] else REPO_ROOT / "Tlamatini.jpg"
    story.append(p("TLAMATINI", styles["title"]))
    story.append(
        p(
            "Complete Project Dossier: what the system does, how it works, how to use Tlamatini, complete repository file tree, and effective line inventory",
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
    story.append(p("Current release focus in v1.24.0", styles["h2"]))
    for item in CURRENT_RELEASE_GUIDE:
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
    story.append(p("New assets in the current release wave", styles["h2"]))
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
    story.append(p("How agent runtimes are shaped", styles["h2"]))
    for item in AGENT_RUNTIME_GUIDE:
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

    story.append(p("10. Complete Repository File Tree (Repository Appendix)", styles["h1"]))
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
    frame.margin_left = Pt(3)
    frame.margin_right = Pt(3)
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
    items beyond ``per_column`` continue, in the same lane, on the next page."""
    margin, gap = 0.72, 0.3
    n = len(columns)
    col_w = (SLIDE_W - 2 * margin - (n - 1) * gap) / n
    max_items = max((len(items) for _, _, items in columns), default=0)
    pages = max(1, -(-max_items // per_column))  # ceil
    for page in range(pages):
        page_title = title if pages == 1 else f"{title} ({page + 1}/{pages})"
        slide, audit = add_slide(prs, page_title, kicker, accent)
        for ci, (header, col_accent, items) in enumerate(columns):
            seg = items[page * per_column:(page + 1) * per_column]
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
        1.0,
        f"Self-hosted AI developer assistant (cloud LLMs by default) with RAG, Multi-Turn orchestration, {context['workflow_agent_count']} agents, ACPX delegation, visual workflows, self-knowledge, and Windows packaging.",
        17,
        THEME["muted"],
        False,
        name="cover-body",
    )
    add_metric_card(slide, audit, 0.9, 4.25, 1.75, "Files", str(context["inventory_files"]), THEME["jade"], "cover-m1")
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

    add_themed_column_slides(prs, "What The System Does", "capability map", THEME["copper"], [
        ("Knowledge", THEME["jade"], WHAT_IT_DOES[:6]),
        ("Action", THEME["copper"], WHAT_IT_DOES[6:12]),
        ("Delivery", THEME["amber"], WHAT_IT_DOES[12:]),
    ], per_column=5)

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
        "Answer Analizer classifies success so the UI can expose Create Flow only when useful.",
    ], THEME["copper"], "mt-a", 15)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Unchecked mode", [
        "Keeps the original prompt validation and legacy prefetch behavior.",
        "Maintains compatibility for fast Q&A and simple context-grounded answers.",
        "Avoids forcing every chat request into agentic execution.",
    ], THEME["jade"], "mt-b", 16)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Ask Execs", "v1.10.0 safety modifier still active in v1.24.0", THEME["amber"])
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

    slide, audit = add_slide(prs, "Windows Installed-App Registration", "v1.11.0 uninstall integration carried into v1.24.0", THEME["copper"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What changed", WINDOWS_APP_REGISTRATION_GUIDE, THEME["copper"], "arp-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Why operators care", [
        "Packaged installs now show up in normal Windows uninstall surfaces instead of only leaving behind shortcuts and a loose `Uninstaller.exe` in the install folder.",
        "The registration is HKCU-only and non-elevated, matching the installer’s per-user design on Windows 10 and Windows 11.",
        "Because frozen startup self-heals the entry, even older installs can gain the uninstall surface after a later app launch without a reinstall.",
    ], THEME["jade"], "arp-b", 12)
    audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Current Release Focus", "v1.24.0 tag plus same-day HEAD updates", THEME["amber"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "What changed", CURRENT_RELEASE_GUIDE, THEME["amber"], "rel-a", 13)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Why it matters", [
        "The version story is now explicit: the repo resolves to `v1.24.0` from the latest tag, while the current HEAD one commit later adds ESPHomer without changing that version baseline.",
        "Operators still inherit the two major foundations from the immediately prior release line: self-update preserves the user's database and custom toggles, and frozen builds ship the numpy/OpenCV native libraries the media agents need.",
        "The resulting narrative matches the current README, Book, Git history, new media assets, and source tree more honestly than the older milestone-only framing.",
    ], THEME["jade"], "rel-b", 13)
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

    slide, audit = add_slide(prs, "Newest Assets And Surfaces", "backend, frontend, and build files added or upgraded recently", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Named assets", NEW_ASSETS_GUIDE, THEME["jade"], "assets-a", 12)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Why they matter", [
        "These files are the concrete proof behind the release narrative: build-time self-snapshotting, a graphical credentials setup surface, and a safer File-Creator transport are all implemented in tracked source, not merely described in markdown.",
        "They also increase the line inventory in JavaScript, CSS, HTML, Markdown, YAML, and Python, which the dossier’s language tables and complete repository tree now pick up automatically.",
        "For operators and maintainers, this makes the PDF/PPTX useful as both a product overview and a change-orientation map after a busy sprint.",
    ], THEME["amber"], "assets-b", 12)
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

    slide, audit = add_slide(prs, "STM32er", "critical-mission STM32F4 firmware control", THEME["copper"])
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
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "ACPX-Skills menu", ACPX_SKILLS_GUIDE, THEME["amber"], "skills-a", 14)
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
        "kimi-k2.6:cloud",
        "qwen3.5:cloud",
        "gpt-oss:120b-cloud",
        "qwen3.5:397b-cloud",
        "glm-5.1:cloud",
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
        add_metric_card(slide, audit, 0.82 + idx * 2.05, 1.75, 1.75, label, str(value), THEME["jade"] if idx % 2 == 0 else THEME["copper"], f"repo-{idx}")
    add_panel(slide, audit, 1.05, 3.1, 10.85, 3.35, "Current HEAD", [
        f"{context['head_short']} - {context['head_subject']}",
        f"Resolved version: {context['version_info']['version']} ({context['version_info']['source']})",
        f"Generated on {context['generated_at']}",
        f"Inventory scope: {context['inventory_files']} files = {context['tracked_files']} tracked + {context['untracked_files']} git-unignored working-tree additions",
        f"Multi-Turn tools: {context['total_multi_turn_tools']}; wrapped chat-agent tools: {context['wrapped_chat_agent_count']}; skills: {context['skills_count']}",
        f"Python requirements: {context['requirements_count']}; authoritative agent-description rows: {context['agent_description_rows']}",
        f"Binary or asset inventory files skipped from line count: {context['binary_count']}",
    ], THEME["amber"], "repo-head", 15)
    audit_layout(audit, len(prs.slides))

    baseline = context["visual_doc_baseline"]
    if baseline is not None:
        slide, audit = add_slide(prs, "Since Last Dossier Refresh", "all important changes since the last committed PDF/PPTX update", THEME["copper"])
        add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Baseline", [
            f"{baseline.short_hash} on {iso_date(baseline.committed_at)}",
            baseline.subject,
            f"Commits since then: {len(context['visual_doc_commits'])}",
        ], THEME["copper"], "since-a", 13)
        add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Key changes", context["visual_doc_highlights"], THEME["jade"], "since-b", 13)
        audit_layout(audit, len(prs.slides))

    slide, audit = add_slide(prs, "Recent Platform Additions", "release waves from v1.17.x through v1.24.0", THEME["jade"])
    add_panel(slide, audit, 0.78, 1.6, 5.9, 4.95, "Recent agents and execution surfaces", [
        "Globber / Grepper / Editor (v1.22.0 wave): a deterministic file-discovery/search/edit trio — find files by pattern, search them by regex, and make exact in-place replacements without dropping to shell `dir` / `findstr` / `sed` workflows.",
        "ESPHomer (current working tree): the ESPHome bridge for YAML-authored smart-home devices — zero-config bootstrap, `new_config`, validation, compile, USB/OTA upload, bounded logs, and a bundled sample `tlamatini-light.yaml` baseline.",
        "Blenderer (introduced in v1.20.0): the live Blender bridge over the official MCP add-on socket, so Tlamatini can inspect scenes, mutate geometry/materials, run raw code, and trigger renders from chat or canvas.",
        "Talker (text-to-speech): SPEAKS input_text aloud via an Ollama neural TTS model (default Orpheus-3b-FT), SNAC-decoded to a 24 kHz WAV — FEMALE-VOICE-ONLY by design (a male voice is refused, never substituted); needs snac+torch (CPU is fine) else degrades to tokens_only.",
        "Whisperer (speech-to-text): records the mic ITSELF (no Recorder dep, 30 s default) or transcribes a file, via faster-whisper LOCALLY — NVIDIA-GPU auto-detect with an ALWAYS-present CPU fallback — or cloud Groq/OpenAI; Ollama can only tidy the finished transcript.",
        "Both audio agents now light a zero-latency console REC indicator (blinking dot + live VU bar) driven by the audio-stream callback — ON within ~20 ms of real samples, OFF the instant the stream stops; the agent reveals its own console even when spawned headless.",
        "Camcorder + Recorder (capture): webcam photo/video via OpenCV and microphone WAV via sounddevice; AudioPlayer + VideoPlayer (playback): file to speakers / to a chosen display — the media-I/O family (screen / camera-in / mic-in / speakers-out / screen-out).",
        "The capture/playback/voice family is observational/output, so it stays out of the Exec Report; each ships on the canvas and as a wrapped Multi-Turn tool. Arduiner adds a direct arduino-cli firmware bridge, and ESPHomer now adds the smart-home YAML/device lane on top of STM32er and ESP32er.",
    ], THEME["copper"], "monday-a", 11)
    add_panel(slide, audit, 6.95, 1.6, 5.55, 4.95, "Lifecycle, policy, and monitoring", [
        "Version identity (v1.24.0): the latest tag now resolves the product to `1.24.0` across VERSIONING.md, release-folder naming, the About dialog story, startup banner wording, and `/agent/version/` expectations.",
        "Visual/media asset refresh (v1.24.0 window): `TlamatiniAbout.png` replaces the earlier JPEG and `TlamatiniAndKyber.mp4` is now part of the shipped repository assets, so the dossier inventory and appendices need to count those new binaries.",
        "Self-update foundation (v1.23.0 carried into v1.24.0): packaged installs preserve the user's DB across the swap — `apply_update.ps1` stages it through `DB/ToLoad/` and the next launch migrates it back into the new build.",
        "Frozen-build hardening (v1.23.0 carried into v1.24.0): numpy and OpenCV are embedded in both bundled Python runtimes and `build.py` aborts if either import is missing, closing the last media-agent dependency gap in installed builds.",
        "flow-making skill: turns a plain objective into a canvas-loadable .flw by driving the FlowCreator engine, so chat can build runnable flows without opening the designer.",
        "Temp/Templates policy: every transient file stays under <app>/Temp and every scaffolded firmware/engine project under <app>/Templates (never C:/Temp or %TEMP%), pinned before Django starts and taught to the LLM as Rules 15/16.",
        "FlowHypervisor monitoring now covers every agent — ESP32er, Arduiner, ESPHomer, Camcorder, and Recorder were added to its categorization, timing, startup markers, and do-not-flag rules, with first-build-downloads-a-large-toolchain caveats where needed.",
        f"Catalog now stands at {context['workflow_agent_count']} workflow agents and {context['total_multi_turn_tools']} Multi-Turn tools ({context['wrapped_chat_agent_count']} wrapped chat-agent + {context['acpx_tool_count']} ACPX/Skill + {context['core_python_tool_count']} core), with {context['skills_count']} skills.",
    ], THEME["jade"], "monday-b", 12)
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
    for idx, chunk in enumerate(tree_chunks, 1):
        slide, audit = add_slide(
            prs,
            f"Repository File Tree Appendix {idx}/{len(tree_chunks)}",
            "complete repository inventory tree, including git-unignored working additions",
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
