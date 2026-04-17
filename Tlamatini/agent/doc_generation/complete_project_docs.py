from __future__ import annotations

import ast
import io
import json
import math
import re
import subprocess
import sys
import tokenize
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
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
    KeepTogether,
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


def collect_context() -> dict:
    paths = tracked_paths()
    tree_text = build_tree(paths)
    language_rows, file_rows, binary_count, skipped_count = line_stats_for_paths(paths)
    total_effective = sum(row.effective_lines for row in language_rows)
    total_lines = sum(row.total_lines for row in language_rows)
    agents = workflow_agents()
    reference_media = extract_reference_media()

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
        "requirements_count": count_requirements(),
        "js_modules": len(list((PROJECT_DIR / "agent" / "static" / "agent" / "js").glob("*.js"))),
        "css_files": len(list((PROJECT_DIR / "agent" / "static" / "agent" / "css").glob("*.css"))),
        "html_templates": len(list((PROJECT_DIR / "agent" / "templates" / "agent").glob("*.html"))),
        "migrations": len(list((PROJECT_DIR / "agent" / "migrations").glob("*.py"))) - 1,
        "recent_commits": recent_commits(),
        "reference_media": reference_media,
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
    "Runs checked Multi-Turn requests through request-scoped planning, capability selection, tool calls, observations, monitoring, and final synthesis.",
    "Launches wrapped copies of selected workflow agents in isolated runtime folders without mutating templates.",
    "Lets users design, validate, save, pause, resume, and stop visual workflows through the Agentic Control Panel.",
    "Turns successful Multi-Turn tool executions into starter `.flw` workflows that can be inspected and validated in ACP.",
    "Packages the project into a distributable Windows release with installer and uninstaller tooling.",
]

HOW_IT_WORKS = [
    "Browser UI sends chat and workflow requests through Django views and Channels WebSockets.",
    "RAG chains load selected file/directory context, retrieve relevant chunks, and build answer prompts.",
    "When Multi-Turn is enabled, the global planner selects context and tool stages before the executor binds only the relevant tools.",
    "Tool calls execute in the backend, append observations, and may create wrapped runtime copies under `agent/agents/pools/_chat_runs_/`.",
    "ACP flows deploy session-scoped pool instances, wire config values, validate NxN graph rules, and execute through Starter-driven flow semantics.",
    "Build scripts collect static assets, bundle Django/Python resources, add agent templates, and assemble `pkg.zip`, `Uninstaller.exe`, and `dist/Tlamatini_Release/`.",
]

HOW_TO_USE = [
    "Run from source: create a virtual environment, install requirements, migrate, create a superuser, collect static files, and start Django.",
    "Open `/agent/` for chat. Load a file or directory context before asking codebase-specific questions.",
    "Keep Multi-Turn unchecked for direct Q&A; enable Multi-Turn for tasks that need tools, wrapped agents, monitoring, or workflow seeding.",
    "Open `/agentic_control_panel/` to drag agents, connect them, configure each node, validate, start, pause/resume, stop, and save `.flw` workflows.",
    "Use `python build.py`, `python build_uninstaller.py`, and `python build_installer.py` only when producing a packaged Windows release.",
]

ARCHITECTURE_LAYERS = [
    ("Browser interfaces", "Chat page plus Agentic Control Panel templates and JavaScript modules."),
    ("Django/Channels", "Authentication, views, WebSockets, session state, message persistence, and ASGI startup."),
    ("RAG and context", "Metadata extraction, text splitting, FAISS/BM25 retrieval, context budgeting, and fallback behavior."),
    ("Multi-Turn engine", "Capability registry, global execution planner, explicit tool loop, answer parsing, and answer-success classification."),
    ("Tools and agents", "Core tools, MCP context providers, wrapped chat-agent launchers, and 57 visual workflow agent templates."),
    ("Packaging", "PyInstaller build scripts, shortcut registration, `.flw` association, installer, uninstaller, and release folder assembly."),
]

AGENT_CATEGORIES = [
    ("Control", "starter, ender, stopper, cleaner, barrier, flowbacker"),
    ("Execution and files", "executer, pythonxer, pser, file_creator, file_extractor, file_interpreter, mover, deleter"),
    ("DevOps and infra", "gitter, dockerer, kuberneter, jenkinser, ssher, scper"),
    ("Data and APIs", "sqler, mongoxer, apirer, crawler, googler"),
    ("Monitoring and routing", "monitor_log, monitor_netstat, flowhypervisor, forker, asker, counter, and, or"),
    ("Communication", "notifier, emailer, recmailer, telegramer, telegramrx, whatsapper"),
    ("Security and media", "kyber_keygen, kyber_cipher, kyber_decipher, image_interpreter, shoter, j_decompiler"),
    ("Workflow intelligence", "flowcreator, gatewayer, gateway_relayer, node_manager, parametrizer, prompter, summarizer"),
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
    story.append(p("Complete Project Dossier: system purpose, architecture, usage, source tree, and effective line inventory", styles["subtitle"]))
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
                ["Tracked files", str(context["tracked_files"])],
                ["Workflow agents", str(context["workflow_agent_count"])],
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
    story.append(p("How to use it", styles["h2"]))
    for item in HOW_TO_USE:
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

    story.append(p("3. Agent Catalog and Runtime Model", styles["h1"]))
    story.append(p(f"Tlamatini currently exposes {context['workflow_agent_count']} workflow-agent templates.", styles["body"]))
    story.append(table([["Category", "Representative agents"]] + AGENT_CATEGORIES, widths=[1.85 * inch, 4.9 * inch], font_size=7.8))
    story.append(p("All workflow agents follow a common deployment pattern: template directory, YAML configuration, session-scoped pool copy, PID/status/log files, target/source wiring, and optional reanimation state.", styles["body"]))
    story.append(PageBreak())

    story.append(p("4. Repository Facts", styles["h1"]))
    repo_rows = [
        ["Metric", "Value"],
        ["Tracked files in git", f"{context['tracked_files']}"],
        ["Workflow agents", f"{context['workflow_agent_count']}"],
        ["Django migrations", f"{context['migrations']}"],
        ["Frontend JavaScript modules", f"{context['js_modules']}"],
        ["Frontend CSS files", f"{context['css_files']}"],
        ["HTML templates", f"{context['html_templates']}"],
        ["Python requirements", f"{context['requirements_count']}"],
        ["Binary/asset tracked files skipped from line count", f"{context['binary_count']}"],
    ]
    story.append(table(repo_rows, widths=[3.0 * inch, 3.7 * inch], font_size=8))
    story.append(p("Latest commits", styles["h2"]))
    commit_rows = [["Date", "Commit", "Subject"]]
    for commit in context["recent_commits"]:
        commit_rows.append([iso_date(commit.committed_at), commit.short_hash, commit.subject])
    story.append(table(commit_rows, widths=[1.0 * inch, 0.8 * inch, 4.9 * inch], font_size=7))
    story.append(PageBreak())

    story.append(p("5. Effective Line Inventory by Language", styles["h1"]))
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

    story.append(p("6. Largest Effective Source Files", styles["h1"]))
    largest_rows = [["Path", "Language", "Effective", "Total"]]
    for file_stat in context["file_rows"][:25]:
        largest_rows.append([file_stat.path, file_stat.language, f"{file_stat.effective_lines:,}", f"{file_stat.total_lines:,}"])
    story.append(table(largest_rows, widths=[4.0 * inch, 1.2 * inch, 0.75 * inch, 0.75 * inch], font_size=6.7))
    story.append(PageBreak())

    story.append(p("7. Complete Tracked Repository File Tree", styles["h1"]))
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

    slide, audit = add_slide(prs, "TLAMATINI", "Complete project dossier", THEME["copper"], cover)
    add_text(slide, audit, 0.9, 2.0, 5.5, 0.6, "El Saber Cosmico del Desarrollo", 24, THEME["white"], False, name="cover-tag", font="Aptos Display")
    add_text(slide, audit, 0.9, 2.76, 5.8, 1.0, "Local AI developer assistant with RAG, Multi-Turn orchestration, 57 agents, visual workflows, and Windows packaging.", 17, THEME["muted"], False, name="cover-body")
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

    slide, audit = add_slide(prs, "The 57 Guardians", "workflow agent catalog", THEME["copper"])
    left = [f"{name}: {desc}" for name, desc in AGENT_CATEGORIES[:4]]
    right = [f"{name}: {desc}" for name, desc in AGENT_CATEGORIES[4:]]
    add_panel(slide, audit, 0.72, 1.56, 5.95, 5.1, "Agent families", left, THEME["copper"], "agents-a", 13)
    add_panel(slide, audit, 6.92, 1.56, 5.65, 5.1, "More guardians", right, THEME["jade"], "agents-b", 13)
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

    slide, audit = add_slide(prs, "Packaging Path", "source usage is separate from release building", THEME["amber"])
    add_flow_boxes(slide, audit, 1.15, 2.0, ["build.py", "pkg.zip", "build_uninstaller", "Uninstaller", "build_installer", "Release"], THEME["amber"])
    add_panel(slide, audit, 0.92, 3.35, 11.35, 2.55, "Release rule", [
        "Run packaging only when preparing a Windows distribution.",
        "The final distributable is the full `dist/Tlamatini_Release/` folder, not one executable copied out of context.",
        "Installer scripts register shortcuts and `.flw` file associations and place the uninstaller next to the app.",
    ], THEME["amber"], "packaging", 16)
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
        f"Generated on {context['generated_at']}",
        f"Python requirements: {context['requirements_count']}; binary or asset tracked files skipped from line count: {context['binary_count']}",
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

    slide, audit = add_slide(prs, "Latest Optimizations", "recent current-head changes, not the whole story", THEME["amber"])
    latest = [f"{iso_date(c.committed_at)} | {c.short_hash} | {c.subject}" for c in context["recent_commits"][:6]]
    add_panel(slide, audit, 0.82, 1.65, 11.55, 4.9, "Latest commits", latest, THEME["amber"], "latest", 13)
    audit_layout(audit, len(prs.slides))

    tree_chunks = split_lines(context["tree_text"], 31)
    for idx, chunk in enumerate(tree_chunks, 1):
        slide, audit = add_slide(prs, f"File Tree Appendix {idx}/{len(tree_chunks)}", "complete tracked repository tree", THEME["jade"] if idx % 2 else THEME["copper"])
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
        "requirements_count": context["requirements_count"],
        "js_modules": context["js_modules"],
        "css_files": context["css_files"],
        "html_templates": context["html_templates"],
        "migrations": context["migrations"],
        "binary_count": context["binary_count"],
        "skipped_count": context["skipped_count"],
        "language_rows": [row.__dict__ for row in context["language_rows"]],
        "largest_files": [row.__dict__ for row in context["file_rows"][:50]],
        "recent_commits": [row.__dict__ for row in context["recent_commits"]],
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
