# -*- coding: utf-8 -*-
# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Generate Tlamatini-Architecture.tex: a multi-sheet architecture atlas of Tlamatini.

Every listed application file of the repository appears (1) as a clickable tile on an atlas
sheet, grouped by architectural cluster, and (2) as an entry of the file index
with a description extracted from the file itself. Overview sheets draw the
runtime topology, the request lifecycle, the intelligence core, the agent
ecosystem, the integration surfaces, the frontend module map (parsed from the
templates), the data model (parsed from models.py), the build/release pipeline,
verification & knowledge, and a Python module dependency matrix (parsed imports).

Output: <repo>/Temp/architecture/Tlamatini-Architecture.tex (+ generator_report.txt)

Usage (from anywhere; the repository is located from this file's own path):
    python scripts/architecture_atlas/gen_architecture.py

To regenerate the finished PDF in one step (generate, typeset with Tlamatini's
LaTeXer agent, then verify that every listed application file is present) run instead:
    python scripts/architecture_atlas/build_architecture_pdf.py

Set TLAMATINI_REPO to point the generator at another checkout. Standard library
only; needs git on PATH. Exit code 2 = a tracked file could not be placed.
"""
import ast
import collections
import datetime
import json
import math
import os
import re
import subprocess
import sys

ROOT = os.environ.get("TLAMATINI_REPO") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir))
OUT = os.path.join(ROOT, "Temp", "architecture")
TEX_PATH = os.path.join(OUT, "Tlamatini-Architecture.tex")
REPORT_PATH = os.path.join(OUT, "generator_report.txt")
A = "Tlamatini/agent/"
REPORT = []
FATAL = []


def note(msg):
    REPORT.append(msg)
    print(msg, flush=True)


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, check=True).stdout.decode("utf-8", "replace")


def T(tpl, **kw):
    for k, v in kw.items():
        tpl = tpl.replace("<" + k + ">", str(v))
    return tpl


def n2(x):
    s = "%.2f" % x
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ----------------------------------------------------------------------------- inventory
ALL_FILES = sorted([f for f in git("ls-files", "-z").split("\0") if f], key=lambda p: p.lower())
FILES = [f for f in ALL_FILES if not f.startswith(A + "migrations/")]
PATHSET = set(FILES)
HEAD = git("rev-parse", "--short", "HEAD").strip()
try:
    TAG = git("describe", "--tags", "--abbrev=0").strip()
except subprocess.CalledProcessError:
    TAG = "untagged"
COMMIT_DATE = git("log", "-1", "--format=%cs").strip()
TODAY = datetime.date.today().isoformat()

BINARY_EXT = {".bcmap", ".woff", ".woff2", ".pfb", ".ttf", ".wasm", ".jpg", ".jpeg", ".png", ".gif",
              ".ico", ".mp4", ".wav", ".pdf", ".pptx", ".jar", ".icc", ".zip"}


class FileInfo:
    def __init__(self, path):
        self.path = path
        self.name = path.rsplit("/", 1)[-1]
        self.dir = path.rsplit("/", 1)[0] if "/" in path else ""
        root, ext = os.path.splitext(self.name)
        self.ext = ext.lower() if root else ""
        full = os.path.join(ROOT, path.replace("/", os.sep))
        with open(full, "rb") as fh:
            data = fh.read()
        self.size = len(data)
        self.text = self.ext not in BINARY_EXT and b"\0" not in data[:8192]
        if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
            self.text = True
            self.content = data.decode("utf-16", "replace")
        elif self.text:
            self.content = data.decode("utf-8", "replace")
        else:
            self.content = ""
        if self.text:
            self.loc = self.content.count("\n") + (1 if self.content and not self.content.endswith("\n") else 0)
        else:
            self.loc = 0
        self.desc = ""
        self.id = ""
        self.cluster = None
        self.sheet = None


FI = collections.OrderedDict()
for _p in FILES:
    FI[_p] = FileInfo(_p)
for _i, _p in enumerate(FILES, 1):
    FI[_p].id = "F%04d" % _i
TOTAL_LOC = sum(f.loc for f in FI.values())
note("Tracked files: %d  text lines: %d  HEAD %s  tag %s" % (len(FILES), TOTAL_LOC, HEAD, TAG))

# ----------------------------------------------------------------------------- file types
TYPES = [
    ("py", "Python", "3572A5"),
    ("js", "JavaScript", "E2B007"),
    ("css", "CSS", "D6338A"),
    ("html", "HTML", "E4572E"),
    ("md", "Markdown", "5C6770"),
    ("cfg", "YAML/JSON", "2E9E44"),
    ("sh", "PS1/BAT/CMD", "0F97A8"),
    ("flow", "Prompts/flows", "9C6ADE"),
    ("cpp", "C++/Arduino", "00599C"),
    ("txt", "Text/other", "A3AAB1"),
    ("bin", "Binary/media", "222222"),
]
TYPE_OF_EXT = {".py": "py", ".js": "js", ".mjs": "js", ".cjs": "js", ".css": "css", ".html": "html",
               ".md": "md", ".yaml": "cfg", ".yml": "cfg", ".json": "cfg", ".ini": "cfg", ".example": "cfg",
               ".ps1": "sh", ".bat": "sh", ".cmd": "sh", ".pmt": "flow", ".fpmt": "flow", ".flw": "flow",
               ".cpp": "cpp", ".h": "cpp", ".ino": "cpp", ".svg": "bin"}


def ftype(fi):
    if not fi.text:
        return "bin"
    return TYPE_OF_EXT.get(fi.ext, "txt")


# ----------------------------------------------------------------------------- LaTeX escaping
SPECIAL = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&", "#": r"\#",
           "^": r"\textasciicircum{}", "_": r"\_", "%": r"\%", "~": r"\textasciitilde{}",
           "<": r"\textless{}", ">": r"\textgreater{}", "|": r"\textbar{}"}
UNI = {"\u2014": "---", "\u2013": "--", "\u2026": r"\ldots{}", "\u2019": "'", "\u2018": "`", "\u201c": "``",
       "\u201d": "''", "\u2192": r"$\rightarrow$", "\u2190": r"$\leftarrow$", "\u2194": r"$\leftrightarrow$",
       "\u21d2": r"$\Rightarrow$", "\u2265": r"$\geq$", "\u2264": r"$\leq$", "\u00d7": r"$\times$",
       "\u00b7": r"\textperiodcentered{}", "\u2022": r"\textbullet{}", "\u2248": r"$\approx$",
       "\u00b1": r"$\pm$", "\u00b0": r"\textdegree{}", "\u2260": r"$\neq$", "\u221e": r"$\infty$",
       "\u2122": r"\texttrademark{}", "\u00a9": r"\textcopyright{}", "\u00ae": r"\textregistered{}",
       "\u00a7": r"\S{}", "\u00a0": " ", "\u203a": r"\guilsinglright{}", "\u2039": r"\guilsinglleft{}",
       "\u00bb": r"\guillemotright{}", "\u00ab": r"\guillemotleft{}", "\u25b8": r"$\triangleright$",
       "\u25b6": r"$\triangleright$", "\u2605": r"$\star$", "\u21c4": r"$\rightleftarrows$",
       "\u2191": r"$\uparrow$", "\u2193": r"$\downarrow$", "\u2212": "-", "\u00b5": r"$\mu$",
       "\u2032": "'", "\u00bd": "1/2", "\u2715": "x", "\u2716": "x", "\u2717": "x"}
LATIN_OK = set("áéíóúÁÉÍÓÚñÑüÜçÇàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛäëïöÄËÏÖ¿¡ãõÃÕß")


def esc(s):
    out = []
    for ch in s:
        if ch in SPECIAL:
            out.append(SPECIAL[ch])
        elif ord(ch) < 128:
            out.append(ch if (ch.isprintable() or ch == " ") else " ")
        elif ch in UNI:
            out.append(UNI[ch])
        elif ch in LATIN_OK:
            out.append(ch)
    return "".join(out)


def esc_tt(s):
    return esc(s).replace("/", r"/\allowbreak{}").replace(r"\_", r"\_\allowbreak{}")


def plain_bm(s):
    """Bookmark-safe plain ASCII."""
    s = s.replace("\u2014", "-").replace("\u2013", "-").replace("\u00b7", "-")
    return re.sub(r"[^A-Za-z0-9 .,:()/+-]", " ", s).strip()


# ----------------------------------------------------------------------------- descriptions
DECOR_RE = re.compile(r"(T\s+L\s+A\s+M\s+A|one who knows|Created\s+by\s+Angela|Every\s+line\s+of\s+this\s+file|"
                      r"Author\s+Banner|Creator\s+of\s+Tlamatini|"
                      r"^[\w./\\-]+\.(py|js|mjs|cjs|css|html|ps1|bat|cmd|md|yaml|yml|json|txt)$|"
                      r"Developer\s*\S\s*Architect|^[\u2550=\-_*~#\u2726\s]+$|^-\*-|coding[:=]|^!/|noqa|"
                      r"pylint:|SPDX|^type:|^@echo off|^setlocal)", re.I)


def clean_comment(text):
    keep = []
    for ln in text.splitlines():
        t = ln.strip().lstrip("*#/").strip()
        if not t or DECOR_RE.search(t):
            continue
        keep.append(t)
    return " ".join(keep)


def tidy(s):
    s = re.sub(r"`{1,3}", "", s)
    s = re.sub(r"\*\*|__(?=\w)", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = " ".join(s.split())
    return s.strip(" -:#|=*")


def sentence(s, limit=150):
    s = tidy(s)
    m = re.search(r"(?<=[A-Za-z0-9)\]'\"])[.!?](?=\s+[A-Z(\"'])", s)
    if m and 24 <= m.end() <= limit:
        s = s[:m.end()]
    if len(s) > limit:
        cut = s[:limit - 1]
        if " " in cut[60:]:
            cut = cut.rsplit(" ", 1)[0]
        s = cut.rstrip(",;:") + "\u2026"
    return s


def first_paragraph(text):
    buf = []
    for line in text.splitlines():
        t = line.strip()
        if not t:
            if buf:
                break
            continue
        if DECOR_RE.search(t):
            continue
        if buf and re.match(r"^(why this exists|overview|usage|example|contract)", t, re.I):
            break
        buf.append(t)
        if len(" ".join(buf)) > 420:
            break
    return " ".join(buf)


def leading_hash_comments(text, prefixes=("#",)):
    out = []
    for line in text.splitlines()[:90]:
        t = line.strip()
        hit = next((p for p in prefixes if t.lower().startswith(p)), None)
        if hit is not None:
            c = t[len(hit):].strip().lstrip("#").strip()
            if c.startswith("<#") or c.startswith("#>") or c in ("<#", "#>"):
                continue
            if not c or DECOR_RE.search(c) or re.match(r"^(requires|region|endregion)\b", c, re.I):
                if out and not c:
                    break
                continue
            out.append(c)
            if len(" ".join(out)) > 260:
                break
        elif not t or t in ("<#", "#>"):
            if out:
                break
        elif t.startswith("<#"):
            continue
        else:
            if out:
                break
            if not t.lower().startswith(("param", "[", "@", "set-strictmode", "import", "from", "setlocal", "chcp", "title", "cls")):
                break
    return " ".join(out)


def leading_c_comments(text):
    out = []
    in_block = False
    skip_block = False
    for line in text.splitlines()[:140]:
        t = line.strip()
        if in_block:
            end = "*/" in t
            c = t.split("*/")[0].lstrip("*").strip()
            if not skip_block and c and not DECOR_RE.search(c):
                out.append(c)
            if end:
                in_block = False
                skip_block = False
                if len(" ".join(out)) > 80:
                    break
            continue
        if t.startswith("/*"):
            body = t[2:].lstrip("*").strip()
            directive = bool(re.match(r"^(global|eslint|exported|jshint|istanbul|\!)", body))
            if "*/" in body:
                c = body.split("*/")[0].strip()
                if c and not directive and not DECOR_RE.search(c):
                    out.append(c)
            else:
                in_block = True
                skip_block = directive
                if body and not directive and not DECOR_RE.search(body):
                    out.append(body)
            continue
        if t.startswith("//"):
            c = t.lstrip("/").strip()
            if c and not DECOR_RE.search(c) and not re.match(r"^(eslint|@ts-|global\b)", c):
                out.append(c)
            elif out and not c:
                break
            continue
        if not t or t in ("'use strict';", '"use strict";', "@charset \"UTF-8\";", "@charset 'UTF-8';"):
            if out and not t:
                break
            continue
        break
    return " ".join(out)


def frontmatter_value(text, key):
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    block = text[3:end]
    m = re.search(r"^\s*" + key + r"\s*:\s*(.+(?:\n\s{2,}.+)*)", block, re.M)
    if not m:
        return ""
    v = m.group(1).strip()
    if v in (">", "|", ">-", "|-"):
        v = " ".join(x.strip() for x in m.group(0).splitlines()[1:])
    return v.strip("'\"")


AGENT_DISPLAY = {}
AGENT_CATEGORY = {}
AGENT_DESC = {}
CATEGORY_ORDER = []


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def load_agent_catalog():
    text = FI["agents_descriptions.md"].content
    cat = None
    table = {}
    for line in text.splitlines():
        if line.startswith("## ") and "Workflow Agents" not in line and cat:
            cat = None
            continue
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m:
            cat = m.group(1).strip()
            if cat not in CATEGORY_ORDER:
                CATEGORY_ORDER.append(cat)
            continue
        m = re.match(r"^\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|\s*$", line)
        if m and cat:
            table[norm(m.group(1))] = (m.group(1), cat, m.group(2))
    dirs = sorted({p.split("/")[3] for p in FILES if p.startswith(A + "agents/") and p.count("/") >= 4})
    for d in dirs:
        hit = table.get(norm(d))
        if hit:
            AGENT_DISPLAY[d], AGENT_CATEGORY[d], AGENT_DESC[d] = hit
        else:
            AGENT_DISPLAY[d] = d.replace("_", " ").title()
            AGENT_CATEGORY[d] = "Other"
            AGENT_DESC[d] = ""
            note("WARN agent %s not found in agents_descriptions.md" % d)
    if "Other" in AGENT_CATEGORY.values() and "Other" not in CATEGORY_ORDER:
        CATEGORY_ORDER.append("Other")
    return dirs


AGENT_DIRS = load_agent_catalog()
WRAPPED = set(re.findall(r'template_dir="([^"]+)"', FI[A + "chat_agent_registry.py"].content))

VENDOR_DESC = {
    "frontend/bootstrap": "Bootstrap 5 (navbar, dropdowns, modals, grid)",
    "frontend/dompurify": "DOMPurify HTML sanitizer used by the Markdown canvas",
    "frontend/highlightjs": "highlight.js syntax highlighter, languages and theme",
    "frontend/jquery": "jQuery",
    "frontend/jquery-ui": "jQuery UI (dialogs, resizing)",
    "frontend/marked": "Marked Markdown parser (license)",
    "frontend/nunito": "Nunito web font (site typography)",
    "frontend/xterm": "xterm.js 5.5.0 terminal renderer of the Terminals area (Terminater)",
    "frontend/xterm-addon-fit": "xterm.js fit add-on 0.10.0 (sizes a terminal to its pane)",
    "frontend/xterm-addon-web-links": "xterm.js web-links add-on 0.11.0 (clickable links in a terminal)",
    "frontend": "Vendored-frontend manifest (versions + integrity)",
    "pdfjs": "PDF.js license and pinned version",
    "pdfjs/build": "PDF.js core library and worker",
    "pdfjs/cmaps": "PDF.js binary CMaps for CJK and legacy encodings",
    "pdfjs/iccs": "PDF.js ICC color profile",
    "pdfjs/standard_fonts": "PDF.js standard fonts",
    "pdfjs/wasm": "PDF.js WebAssembly decoders (JBIG2, OpenJPEG, QuickJS)",
    "pdfjs/web": "PDF.js viewer and its toolbar icons",
}


def vendor_lib(path):
    rest = path.split("/static/agent/vendor/", 1)[1]
    parts = rest.split("/")
    if len(parts) <= 2:
        return parts[0]
    return parts[0] + "/" + parts[1]


def binary_desc(fi):
    p, e = fi.path, fi.ext
    if e == ".bcmap":
        return "PDF.js binary CMap %s (character-code to CID mapping for the PDF canvas)." % fi.name[:-6]
    if e in (".woff", ".woff2"):
        return "Nunito web-font file (%s)." % fi.name.rsplit(".", 1)[0].replace("nunito-", "")
    if e in (".pfb", ".ttf"):
        return "Standard font shipped with PDF.js for PDFs that do not embed it."
    if e == ".wasm":
        return "PDF.js WebAssembly decoder module."
    if e == ".icc":
        return "ICC color profile used by PDF.js."
    if e == ".jar":
        return "jd-cli Java decompiler, run by the J-Decompiler agent and the decompile_java tool."
    if e in (".jpg", ".jpeg", ".png", ".gif"):
        if "/avatar/" in p:
            stem = fi.name.rsplit(".", 1)[0]
            eyes = "open" if stem.startswith("eo") else "closed"
            mouth = "open" if stem.endswith("mo") else "closed"
            return "Avatar portrait: eyes %s, mouth %s (blended by the presence compositor)." % (eyes, mouth)
        if "guide_assets" in p:
            return "Step-by-step setup screenshot used by the messaging-agent guide."
        return "Image (%s): %s." % (e[1:].upper(), fi.name.rsplit(".", 1)[0].replace("_", " "))
    if e == ".ico":
        return "Tlamatini application icon."
    if e == ".mp4":
        return "Tlamatini presentation video."
    if e == ".wav":
        return "Notification sound played by the chat/canvas pages."
    if e == ".pdf":
        return "PDF document: %s." % fi.name[:-4].replace("_", " ")
    if e == ".pptx":
        return "Project presentation deck generated by the dossier generator."
    return "Binary file (%s, %d bytes)." % (e or "no extension", fi.size)


def py_desc(fi):
    text = fi.content
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        tree = None
    doc = ast.get_docstring(tree) if tree is not None else None
    base = sentence(first_paragraph(doc)) if doc else ""
    if not base:
        c = leading_hash_comments(text)
        base = sentence(c) if c else ""
    defs = []
    ntests = 0
    if tree is not None:
        for n in tree.body:
            if isinstance(n, ast.ClassDef):
                defs.append(n.name)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_"):
                defs.append(n.name + "()")
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"):
                ntests += 1
    fi.ntests = ntests
    if not base:
        if defs:
            more = " and %d more" % (len(defs) - 4) if len(defs) > 4 else ""
            base = "Defines " + ", ".join(defs[:4]) + more + "."
        elif tree is not None:
            names = []
            mods = []
            for n in tree.body:
                if isinstance(n, ast.Assign):
                    names += [t.id for t in n.targets if isinstance(t, ast.Name)]
                elif isinstance(n, ast.Import):
                    mods += [a.name.split(".")[0] for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.module:
                    mods.append(n.module.split(".")[0] if not n.module.startswith("agent") else n.module)
            mods = [m for i, m in enumerate(mods) if m not in mods[:i]]
            if fi.name == "__init__.py" and not names:
                base = "Package marker for %s/." % fi.dir.rsplit("/", 1)[-1]
            elif names:
                base = "Module that sets %s%s." % (", ".join(names[:4]), (" using " + ", ".join(mods[:4])) if mods else "")
            elif mods:
                base = "Module importing %s." % ", ".join(mods[:5])
            else:
                base = "Python module."
        else:
            base = "Python module."
    if "/migrations/" in fi.path and fi.name[:4].isdigit():
        words = fi.name[5:-3].replace("_", " ")
        base = "Migration %s: %s." % (fi.name[:4], words) + ("" if not doc else " " + sentence(first_paragraph(doc), 90))
    if (fi.name.startswith("test") or fi.name == "tests.py") and ntests:
        base = base.rstrip() + " [%d tests]" % ntests
    return base


def js_desc(fi):
    if "/vendor/" in fi.path:
        lib = vendor_lib(fi.path)
        return "Vendored %s: %s." % (VENDOR_DESC.get(lib, lib), fi.name)
    c = leading_c_comments(fi.content)
    if c:
        return sentence(c)
    funcs = re.findall(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", fi.content, re.M)
    exports = re.findall(r"window\.([A-Z][\w$]*)\s*=", fi.content)
    if exports:
        return "Exports window." + ", window.".join(sorted(set(exports))[:3]) + "; %d functions." % len(funcs)
    if funcs:
        return "Defines %s%s." % (", ".join(f + "()" for f in funcs[:4]), " and %d more" % (len(funcs) - 4) if len(funcs) > 4 else "")
    return "JavaScript module."


def css_desc(fi):
    if "/vendor/" in fi.path:
        return "Vendored %s: %s." % (VENDOR_DESC.get(vendor_lib(fi.path), "stylesheet"), fi.name)
    c = leading_c_comments(fi.content)
    rules = fi.content.count("{")
    return (sentence(c) + " " if c else "Stylesheet. ") + "[%d rule blocks]" % rules


def html_desc(fi):
    t = fi.content
    comment = ""
    for cm in re.finditer(r"\{#\s*(.+?)\s*#\}|<!--\s*(.+?)\s*-->", t, re.S):
        comment = clean_comment(cm.group(1) or cm.group(2) or "")
        if comment:
            break
    title = re.search(r"<title>(.*?)</title>", t, re.S)
    statics = re.findall(r"\{%\s*static\s+['\"]([^'\"]+)['\"]", t)
    js = sum(1 for s in statics if s.endswith(".js") or s.endswith(".mjs"))
    css = sum(1 for s in statics if s.endswith(".css"))
    head = sentence(comment, 110) if comment else ("Page \u201c%s\u201d" % tidy(re.sub(r"\{[{%].*?[%}]\}", "", title.group(1))) if title else "HTML template")
    extra = " Loads %d scripts and %d stylesheets." % (js, css) if statics else ""
    return head.rstrip(".") + "." + extra


def md_desc(fi):
    t = fi.content
    d = frontmatter_value(t, "description")
    if d:
        return sentence(d)
    body = t
    if t.startswith("---"):
        end = t.find("\n---", 3)
        body = t[end + 4:] if end > 0 else t
    head = re.search(r"^#{1,3}\s+(.+)$", body, re.M)
    lines = [ln for ln in body.splitlines()]
    para = ""
    started = False
    buf = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("#"):
            if buf:
                break
            started = True
            continue
        if not s or s.startswith(("|", "```", "<", "---", "![", ">")):
            if buf:
                break
            continue
        if DECOR_RE.search(s):
            continue
        if started or not head:
            buf.append(s)
            if len(" ".join(buf)) > 300:
                break
    para = " ".join(buf)
    h = tidy(head.group(1)) if head else ""
    if h and para and len(h) < 70:
        return sentence(h + ": " + para, 160)
    return sentence(h or para or "Markdown document")


def yaml_desc(fi):
    keys = re.findall(r"^([A-Za-z_][\w-]*)\s*:", fi.content, re.M)
    seen = []
    for k in keys:
        if k not in seen:
            seen.append(k)
    m = re.match(r"^" + re.escape(A) + r"agents/([^/]+)/config\.yaml$", fi.path)
    if m:
        disp = AGENT_DISPLAY.get(m.group(1), m.group(1))
        shown = [k for k in seen if k not in ("source_agents", "target_agents")]
        more = " +%d more" % (len(shown) - 7) if len(shown) > 7 else ""
        return "Default config.yaml of the %s agent: %s%s." % (disp, ", ".join(shown[:7]), more)
    c = leading_hash_comments(fi.content)
    if c:
        return sentence(c)
    return "YAML document: keys %s." % ", ".join(seen[:8]) if seen else "YAML document."


def json_desc(fi):
    try:
        data = json.loads(fi.content)
    except ValueError:
        return "JSON document."
    if isinstance(data, dict):
        keys = list(data.keys())
        if fi.name == "package.json":
            deps = len(data.get("devDependencies", {})) + len(data.get("dependencies", {}))
            return "Node tooling manifest (%s): %d dependencies, scripts %s." % (data.get("name", "?"), deps, ", ".join(list(data.get("scripts", {}))[:4]))
        return "JSON document with keys: %s%s." % (", ".join(str(k) for k in keys[:7]), " +%d more" % (len(keys) - 7) if len(keys) > 7 else "")
    if isinstance(data, list):
        return "JSON array of %d items." % len(data)
    return "JSON value."


def ps_desc(fi):
    t = fi.content
    m = re.search(r"\.SYNOPSIS\s*\n(.+?)(?:\n\s*\n|\.DESCRIPTION|#>)", t, re.S)
    if m:
        return sentence(m.group(1))
    c = leading_hash_comments(t)
    return sentence(c) if c else "PowerShell script."


def bat_desc(fi):
    c = leading_hash_comments(fi.content, prefixes=("rem ", "rem\t", "::"))
    return sentence(c.lstrip("= ")) if c else "Windows batch script."


SPECIAL_DESC = {
    "LICENSE": "MIT license of Tlamatini.",
    ".gitignore": "Git ignore rules: Temp/, Templates/, databases, secrets (data.keys), build output, generated _version.py.",
    ".gitattributes": "Git attributes: line-ending and binary handling.",
    A + "prompt.pmt": "System prompt of the chat LLM: Tlamatini's identity, operating rules, tool-usage contract, Temp/Templates policy and the self-knowledge slot.",
    A + "agents/flowhypervisor/monitoring-prompt.pmt": "FlowHypervisor watchdog prompt: answers OK or ATTENTION NEEDED, with per-agent special notes and normal-behaviour lists.",
    A + "config.json": "Main configuration template: models, ports, timeouts, Model Brain, Compact mode, binary guard, ACPX; secrets are placeholders.",
    A + "external_mcps.json": "External-MCP catalog (mcpServers shape) + active list; user state preserved across self-update.",
    A + "model_profiles.json": "Model Brain knowledge base: sourced sampling/thinking profiles per model family.",
    A + "filesearch.proto": "gRPC contract of the Files-Search MCP service.",
    A + "command_togen_pb2.txt": "Command used to regenerate the Files-Search protobuf/gRPC stubs.",
    A + "agents/flowcreator/flow_catalog.json": "Generated agent catalog (contracts + output fields) read by FlowCreator and Parametrizer.",
    "Tlamatini/tlamatini/asgi.py": "ASGI application: ProtocolTypeRouter sends HTTP to Django and WebSockets (AuthMiddlewareStack) to agent.routing.",
    "Tlamatini/tlamatini/wsgi.py": "Standard Django WSGI entry point (the app itself runs on ASGI/Daphne).",
    A + "test_fixtures/talker_orpheus_tokens.txt": "Recorded Orpheus audio-token stream (one line of custom tokens) replayed by the Talker tests without a model.",
    "requirements.txt": None, "requirements-esphome.txt": None, "pnpm-lock.yaml": "pnpm lockfile pinning the JavaScript lint tooling.",
    "Tlamatini-Architecture.pdf": "This architecture atlas: every listed application file on A3 sheets; rebuilt by scripts/architecture_atlas/build_architecture_pdf.py and typeset by LaTeXer.",
}


def describe(fi):
    if fi.path in SPECIAL_DESC and SPECIAL_DESC[fi.path]:
        return SPECIAL_DESC[fi.path]
    if fi.name.startswith("requirements") and fi.ext == ".txt":
        pk = [ln for ln in fi.content.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        return "Python dependency list: %d pinned requirements%s." % (len(pk), " (private ESPHome runtime)" if "esphome" in fi.name else "")
    if not fi.text:
        return binary_desc(fi)
    e = fi.ext
    if fi.name.endswith(".antes_shoter"):
        return "Pre-Shoter copy of %s kept as a comparison baseline." % fi.name[:-len(".antes_shoter")]
    if e == ".patch":
        return "Patch recorded together with the change note %s." % fi.name[:-6]
    if e == ".py":
        return py_desc(fi)
    if e in (".js", ".mjs", ".cjs"):
        return js_desc(fi)
    if e == ".css":
        return css_desc(fi)
    if e == ".html":
        return html_desc(fi)
    if e == ".md":
        return md_desc(fi)
    if e in (".yaml", ".yml"):
        return yaml_desc(fi)
    if e == ".json":
        return json_desc(fi)
    if e == ".ps1":
        return ps_desc(fi)
    if e in (".bat", ".cmd"):
        return bat_desc(fi)
    if e == ".svg":
        if "/vendor/" in fi.path:
            return "PDF.js viewer icon: %s." % fi.name[:-4].replace("-", " ").replace("_", " ")
        return "SVG graphic: %s." % fi.name[:-4]
    if e == ".flw":
        try:
            data = json.loads(fi.content)
            nodes = data.get("nodes") or data.get("items") or data.get("agents") or []
            return "Agentic flow (.flw) for the Agentic Control Panel with %d nodes." % len(nodes)
        except (ValueError, AttributeError):
            return "Agentic flow (.flw) for the Agentic Control Panel."
    if e == ".fpmt":
        return "Example Prompt Flow Panel diagram (JSON format tlamatini-prompting-flow)."
    if e in (".cpp", ".h", ".ino"):
        c = leading_c_comments(fi.content)
        return sentence(c) if c else "Firmware source of the template project."
    if e == ".map":
        return "Source map of the vendored minified bundle."
    first = next((ln.strip() for ln in fi.content.splitlines() if ln.strip() and not DECOR_RE.search(ln.strip())), "")
    if fi.name in ("VERSION",):
        return "Pinned PDF.js version: %s." % first
    if fi.name.startswith("LICENSE"):
        return "Third-party license text: %s" % sentence(first, 90)
    return sentence(first) if first else "Text file."


for _f in FI.values():
    _f.ntests = 0
    try:
        _f.desc = describe(_f)
    except Exception as exc:  # noqa: BLE001 - a description must never stop the atlas
        _f.desc = "File."
        note("WARN description failed for %s: %s" % (_f.path, exc))
    if not _f.desc:
        _f.desc = "File."
    # no description may carry an unbreakable run wider than an index column
    _f.desc = re.sub(r"\S{46,}", lambda m: m.group(0)[:38] + "…", _f.desc)

# ----------------------------------------------------------------------------- analysis
TEMPLATES = {
    "chat": A + "templates/agent/agent_page.html",
    "acp": A + "templates/agent/agentic_control_panel.html",
    "pfp": A + "templates/agent/prompt_flow_panel.html",
    "login": A + "templates/agent/login.html",
    "welcome": A + "templates/agent/welcome.html",
    "admin": A + "templates/admin/base_site.html",
    "usage": A + "templates/agent/usage_dialog.html",
    "pdf": A + "static/agent/pdf/canvas.html",
}
PAGE_REFS = collections.OrderedDict()
for _k, _t in TEMPLATES.items():
    txt = FI[_t].content
    refs = []
    if _k == "pdf":
        base = _t.rsplit("/", 1)[0]
        for r in re.findall(r"(?:src|href)=\"([^\"#?]+)", txt):
            p = os.path.normpath(base + "/" + r).replace("\\", "/")
            if p in PATHSET and p not in refs:
                refs.append(p)
    else:
        for r in re.findall(r"\{%\s*static\s+['\"]([^'\"?]+)", txt):
            p = A + "static/" + r
            if p in PATHSET and p not in refs:
                refs.append(p)
    PAGE_REFS[_k] = refs
USED_BY = collections.defaultdict(set)
for _k, refs in PAGE_REFS.items():
    for r in refs:
        USED_BY[r].add(_k)


def page_group(path):
    pages = USED_BY.get(path, set())
    main = pages & {"chat", "acp", "pfp"}
    if len(pages) >= 2 and (len(main) >= 2 or (main and pages - main)):
        return "shared"
    if main:
        return next(iter(main))
    return "other"


# models
MODELS = []
_mt = ast.parse(FI[A + "models.py"].content)
for _n in _mt.body:
    if isinstance(_n, ast.ClassDef) and any((isinstance(b, ast.Attribute) and b.attr == "Model") for b in _n.bases):
        fields = []
        for st in _n.body:
            targets, val = [], None
            if isinstance(st, ast.Assign) and isinstance(st.value, ast.Call):
                targets, val = [t.id for t in st.targets if isinstance(t, ast.Name)], st.value
            elif isinstance(st, ast.AnnAssign) and isinstance(st.value, ast.Call) and isinstance(st.target, ast.Name):
                targets, val = [st.target.id], st.value
            if not val:
                continue
            fn = val.func
            ftype_ = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "?")
            if not (ftype_.endswith("Field") or ftype_ in ("ForeignKey", "OneToOneField", "ManyToManyField")):
                continue
            tgt = ""
            if ftype_ in ("ForeignKey", "OneToOneField", "ManyToManyField") and val.args:
                a0 = val.args[0]
                if isinstance(a0, ast.Name):
                    tgt = a0.id
                elif isinstance(a0, ast.Attribute):
                    tgt = a0.attr
                elif isinstance(a0, ast.Constant):
                    tgt = str(a0.value)
            for t in targets:
                fields.append((t, ftype_.replace("Field", "") or ftype_, tgt))
        MODELS.append((_n.name, fields, ast.get_docstring(_n) or ""))
note("Models parsed: %d" % len(MODELS))

URL_COUNT = len(re.findall(r"\bpath\(", FI[A + "urls.py"].content))
WS_ROUTES = re.findall(r"re_path\(r?'([^']+)'", FI[A + "routing.py"].content)
try:
    _sup = 0
    for _n in ast.walk(ast.parse(FI[A + "external_mcp_manager.py"].content)):
        if isinstance(_n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_SUPERVISOR_TOOL_NAMES" for t in _n.targets):
            _sup = len([c for c in ast.walk(_n.value) if isinstance(c, ast.Constant) and isinstance(c.value, str)])
    SUPERVISORS = _sup
except SyntaxError:
    SUPERVISORS = 0
SKILL_PKGS = sorted({p.split("/")[3] for p in FILES if p.startswith(A + "skills_pkg/") and p.endswith("/SKILL.md")})
TEST_FILES = [f for f in FI.values() if f.ext == ".py" and (f.name.startswith("test") or f.name == "tests.py")]
TEST_FUNCS = sum(f.ntests for f in TEST_FILES)
UNIT_TEST_MODULES = [f for f in FI.values() if re.match(r"^" + re.escape(A) + r"test[^/]*\.py$", f.path)]
POOL_PY = [f for f in FI.values() if f.path.startswith(A + "agents/") and f.ext == ".py"]
POOL_AGENT_IMPORTS = sum(1 for f in POOL_PY if re.search(r"^\s*(from|import)\s+agent(\.|\s)", f.content, re.M))


def mig_kind(name):
    n = name.lower()
    if not n[:4].isdigit():
        return "schema"
    if "prompt" in n:
        return "prompts"
    if re.search(r"_tools?(_|\.|$)|tool_", n):
        return "tools"
    if "skill" in n:
        return "skills"
    if "mcp" in n:
        return "mcps"
    if n.startswith("0001"):
        return "schema"
    if "_add_" in n or "agent" in n:
        return "agents"
    return "schema"


MIG_KINDS = collections.OrderedDict([("agents", ("Agent rows", "2E8B3A")), ("prompts", ("Catalog prompts", "D4A017")),
                                     ("tools", ("Tool rows", "1F6FB2")), ("skills", ("Skills", "D9731A")),
                                     ("mcps", ("MCP rows", "6B3FA0")), ("schema", ("Schema & data", "7F8C8D"))])
MIGRATIONS = [FileInfo(p) for p in ALL_FILES
              if p.startswith(A + "migrations/") and p.rsplit("/", 1)[-1][:4].isdigit()]

# ----------------------------------------------------------------------------- layers & clusters
LAYERS = collections.OrderedDict([
    ("presentation", ("Presentation (browser)", "0E9F8E")),
    ("transport", ("Process & transport", "1F6FB2")),
    ("intelligence", ("Intelligence core", "6B3FA0")),
    ("integration", ("Integration surfaces", "D9731A")),
    ("agents", ("Agent pool", "2E8B3A")),
    ("persistence", ("Persistence & state", "8B5A2B")),
    ("platform", ("Platform & safety", "3F5468")),
    ("build", ("Build, release & install", "C0392B")),
    ("quality", ("Verification", "6C7A89")),
    ("knowledge", ("Knowledge & governance", "B07D10")),
    ("vendor", ("Vendored third-party", "8395A7")),
])
CAT_COLORS = ["1F6FB2", "D9731A", "6B3FA0", "2E8B3A", "C0392B", "0E9F8E", "B07D10", "8B5A2B", "3F5468", "7F8C8D", "D6338A"]
CAT_COLOR = {c: CAT_COLORS[i % len(CAT_COLORS)] for i, c in enumerate(CATEGORY_ORDER)}

TRANSPORT = {"admin.py", "apps.py", "consumers.py", "routing.py", "urls.py", "views.py", "chat_voice_consumer.py",
             "prompt_flow_panel_consumer.py", "flow_file_views.py", "model_brain_views.py", "pdf_context_views.py",
             "usage_views.py", "constants.py", "version.py", "__init__.py", "access_key_wizard.py", "contacts.py",
             "native_dialogs.py", "window_flash.py"}
INTEL = {"mcp_agent.py", "tools.py", "global_execution_planner.py", "capability_registry.py", "self_healing.py",
         "model_brain.py", "model_brain_chat.py", "model_profiles.json", "context_fitter.py", "context_governor.py",
         "context_baseline.py", "compact_mode.py", "cancellation.py", "global_state.py", "chat_history_loader.py",
         "local_toolcall_parser.py", "ollama_stop.py", "llm_timing.py", "web_search_llm.py", "inet_determiner.py",
         "rag_enhancements.py", "prompt.pmt", "Tlamatini.md", "agent_verdict.py", "exec_permission.py",
         "chat_agent_registry.py", "chat_agent_runtime.py", "gpu_perf.py", "embedding_memory_guard.py",
         "pdf_context.py", "pdf_context_jobs.py", "pdf_image_analysis.py", "visual_error_reporting.py",
         "prompt_flow_panel_runtime.py", "chat_voice_runtime.py", "chat_voice_settings.py", "usage_provider.py",
         "usage_tracking.py", "config_loader.py", "config.json"}
INTEG = {"mcp_system_server.py", "mcp_system_client.py", "mcp_files_search_server.py", "mcp_files_search_client.py",
         "chain_system_lcel.py", "chain_files_search_lcel.py", "filesearch.proto", "filesearch_pb2.py",
         "filesearch_pb2_grpc.py", "command_togen_pb2.txt", "context_sidecar_timeout.py", "external_mcp_manager.py",
         "external_mcp_defaults.py", "external_mcps.json", "runtime_provisioner.py", "win_shim.py"}
PLATFORM = {"path_guard.py", "orphan_reaper.py", "command_watchdog.py", "log_identity.py", "self_update.py",
            "agent_manifest.py", "windows_app_registration.py", "flow_file_open.py"}
PERSIST = {"models.py", "sqlite_copy.py", "run_db_wal_tests.ps1"}
BUILD_ROOT = {"build.py", "build_all.cmd", "build_installer.py", "build_uninstaller.py", "build_runtime_assets.py",
              "build_complete_private_release.py", "build_complete_public_release.py", "copy_source_assets.py",
              "versioning.py", "audit_dependencies.py", "check_private_data.py", "regen_secrets.py", "git_deny_go.py",
              "uncommit-keys.bat", "private_targets.example.json", "requirements.txt", "requirements-esphome.txt",
              "package.json", "pnpm-lock.yaml", "eslint.config.mjs", ".gitignore", ".gitattributes"}
INSTALL_ROOT = {"install.py", "uninstall.py", "uninstall_processes.py", "setup_wizard.py", "setup_recovery.py",
                "setup_windows.py", "setup_logging.py", "apply_update.ps1", "preserved_user_state.json",
                "CreateShortcut.ps1", "CreateShortcut.json", "RemoveShortcut.ps1", "Tlamatini.ps1",
                "flow_file_associations.ps1", "register_flw.ps1", "unregister_flw.ps1", "register_fpmt.ps1",
                "unregister_fpmt.ps1", "freeingport8000.ps1", "backup_db.py", "ollama_credits.py"}
MCPSERVER_ROOT = {"tlamatini_mcp_server.py", "tlamatini_acpx.py", ".mcp.json"}


def mig_era(name):
    n = int(name[:4]) if name[:4].isdigit() else 1
    lo = ((n - 1) // 50) * 50 + 1
    return "%04d" % lo


def assign(p):
    b = p.rsplit("/", 1)[-1]
    if p in ("Tlamatini/manage.py", "Tlamatini/cat_art.py"):
        return "proc"
    if p.startswith("Tlamatini/tlamatini/"):
        return "django"
    if p.startswith(A + "templates/"):
        return "templates"
    if p.startswith(A + "management/"):
        return "mgmt"
    if p.startswith(A + "rag/chains/"):
        return "chains"
    for pre, key in (("interactor/", "interactor"), ("rag/", "rag"), ("services/", "services"), ("imaging/", "imaging"), ("opus_client/", "opus"),
                     ("monitors/", "monitors"), ("doc_generation/", "docgen"), ("acpx/", "acpx"), ("skills/", "skills"),
                     ("skills_pkg/", "skillspkg"), ("images/", "images"), ("TlamatiniSourceCode/", "selfsrc"),
                     ("test_fixtures/", "fixtures")):
        if p.startswith(A + pre):
            return key
    if p.startswith(A + "migrations/"):
        return "mig_" + mig_era(b)
    if p.startswith(A + "static/agent/vendor/"):
        return "vendor_" + vendor_lib(p)
    if p.startswith(A + "static/agent/interactor/"):
        return "interactor_front"
    if p.startswith(A + "static/agent/js/"):
        return "js_" + page_group(p)
    if p.startswith(A + "static/agent/css/"):
        return "css_" + page_group(p)
    if p.startswith(A + "static/"):
        return "static_media"
    if p.startswith(A + "agents/"):
        sub = p[len(A + "agents/"):]
        return "ag__shared" if "/" not in sub else "ag_" + sub.split("/")[0]
    if p.startswith("Tlamatini/DB/"):
        return "persist"
    if p.startswith("Tlamatini/jd-cli/"):
        return "jdcli"
    if p.startswith("Tlamatini/tests_e2e/"):
        return "e2e"
    if p.startswith(("Tlamatini/.agents/", "Tlamatini/.mcps/", "Tlamatini/.skills/")):
        return "guides"
    if p.startswith(A) and "/" not in p[len(A):]:
        if b.startswith("test"):
            return "unit"
        for s, k in ((TRANSPORT, "transport"), (INTEL, "intel"), (INTEG, "integ"), (PLATFORM, "platform"), (PERSIST, "persist")):
            if b in s:
                return k
        return "agent_other"
    if p.startswith("Tests/"):
        return "tests_root"
    if p.startswith("AuxTests/"):
        return "auxtests"
    if p.startswith("scripts/architecture_atlas/") or p == "Tlamatini-Architecture.pdf":
        return "atlas"
    if p.startswith("scripts/"):
        return "scripts"
    if p.startswith(".claude/skills/tlamatini-daily-chat-test/harness/"):
        return "harness_claude"
    if p.startswith(".gemini/skills/tlamatini-daily-chat-test/harness/"):
        return "harness_gemini"
    if p.startswith(".claude/memory/"):
        return "memory"
    if p.startswith(".claude/"):
        return "claude_cfg"
    if p.startswith(".gemini/"):
        return "gemini_skills"
    if p.startswith(".codex/"):
        return "codex_skills"
    if p.startswith("docs/changes/"):
        return "docs_changes"
    if p.startswith("docs/claude/"):
        return "docs_claude"
    if p.startswith("docs/"):
        return "docs"
    if p.startswith("pyinstaller_hooks/"):
        return "build"
    if p.startswith("security/"):
        return "security"
    if p.startswith((".github/", ".scanning/")):
        return "ci"
    if p.startswith("demo_flows/"):
        return "demo"
    if "/" not in p:
        if b in BUILD_ROOT:
            return "build"
        if b in INSTALL_ROOT:
            return "install"
        if b in MCPSERVER_ROOT:
            return "mcpserver"
        if b.startswith("test_") and b.endswith(".py"):
            return "roottests"
        if b.endswith(".flw"):
            return "demo"
        if b.endswith((".md", ".txt")):
            return "rootdocs"
        return "rootmedia"
    return None


CHAPTERS = collections.OrderedDict([
    ("core", ("Atlas I \u2014 Server core: process, web tier and intelligence",
              "Django/Channels process, HTTP and WebSocket entry points, the RAG chains, the Multi-Turn executor and its services.", 4)),
    ("integ", ("Atlas II \u2014 Integration surfaces, platform and state",
               "Built-in MCP servers, the universal external-MCP client, ACPX, the skill harness, platform guards and persistence core.", 4)),
    ("migr", ("Atlas III \u2014 Persistence history: every Django migration",
              "Tiles are tinted by what each migration seeds or changes (classified from its file name).", 5)),
    ("front", ("Atlas IV \u2014 Presentation layer: first-party frontend",
               "Scripts and stylesheets grouped by the page template that loads them (parsed from the templates).", 4)),
    ("vendor", ("Atlas V \u2014 Vendored third-party frontend and PDF.js",
                "Pinned, offline copies served by WhiteNoise: no CDN at runtime.", 6)),
    ("agents", ("Atlas VI \u2014 Agent pool: every workflow agent template",
                "One cluster per agent, ordered by category; MT = also a Multi-Turn chat tool (chat_agent_*).", 5)),
    ("verify", ("Atlas VII \u2014 Verification: unit, contract, visible and release tests",
                "Every automated test runs headed and visible on the real desktop; screenshots are taken by Shoter.", 4)),
    ("build", ("Atlas VIII \u2014 Build, release, install, security and repository root",
               "From source to Installer.exe, self-update and uninstall; guards that keep private data out of git.", 4)),
    ("know", ("Atlas IX \u2014 Knowledge and governance",
              "Documentation, change records, assistant onboarding, memory and the four tracked skill locations.", 4)),
])

META = {
    "vendor_canvas-editor": ("vendor", "vendor/canvas-editor - offline CodeMirror", "editable text and tutoring extension; manifest and licenses carried locally", "vendor"),
    "interactor": ("core", "agent/interactor/ - live editor module", "authenticated tab bridge, fresh buffer reads, typed teaching segments and learner handoffs", "intelligence"),
    "interactor_front": ("front", "static/agent/interactor/ - tutor controls", "browser bridge, local field completion and learner-first interruption", "presentation"),
    "proc": ("core", "Tlamatini/ \u00b7 process entry", "manage.py: log tee, console shield, colours, django_port, Temp pin, post-update DB swap", "transport"),
    "django": ("core", "Tlamatini/tlamatini/ \u00b7 Django project", "settings (SQLite WAL, WhiteNoise, temp pin), ASGI app, root URLs, per-user log-tag middleware", "transport"),
    "transport": ("core", "agent/ \u00b7 transport and web endpoints", "Channels consumers, HTTP views, app boot (AgentConfig.ready), admin, fixed chat lines", "transport"),
    "templates": ("core", "agent/templates/ \u00b7 server-rendered pages", "chat page, Agentic Control Panel, Prompt Flow Panel, login, welcome, usage dialog, admin skin", "presentation"),
    "mgmt": ("core", "agent/management/ \u00b7 manage.py commands", "startserver plus build gates (check_agent_runtimes, check_prompt_flow_panel) and acpx_lint", "transport"),
    "intel": ("core", "agent/ \u00b7 intelligence core", "Multi-Turn executor, tool surface, planner, self-healing, Model Brain, context fitting, prompts", "intelligence"),
    "rag": ("core", "agent/rag/ \u00b7 retrieval-augmented generation", "chain factory, ask_rag interface, FAISS + BM25 retrieval, loaders, splitters, binary guard", "intelligence"),
    "chains": ("core", "agent/rag/chains/ \u00b7 answer chains", "prompt-only, history-aware RAG and unified tool-agent chains", "intelligence"),
    "services": ("core", "agent/services/ \u00b7 flow compiler and contracts", "FlowSpec, flow compiler, agent contracts and paths, response parser, prompt-flow interpreter", "intelligence"),
    "imaging": ("core", "agent/imaging/ \u00b7 image analysis", "dual-backend (Claude + Qwen) interpretation, conversion, screenshots", "intelligence"),
    "opus": ("core", "agent/opus_client/ \u00b7 Claude API client", "chat, images, PDFs, streaming, tools", "integration"),
    "monitors": ("core", "agent/monitors/ \u00b7 SQL monitor", "", "platform"),
    "docgen": ("core", "agent/doc_generation/ \u00b7 project dossier generator", "builds and verifies the summary PDF and the PPTX deck from source facts", "build"),
    "agent_other": ("core", "agent/ \u00b7 other modules", "", "intelligence"),
    "integ": ("integ", "agent/ \u00b7 context providers and external-MCP client", "System-Metrics (WS 8765), Files-Search (gRPC 50051), sidecars, universal MCP client, runtimes, Windows shim", "integration"),
    "acpx": ("integ", "agent/acpx/ \u00b7 ACPX runtime", "external coding-agent CLIs as children: registry, transports, delivery verdict, 12 tools", "integration"),
    "skills": ("integ", "agent/skills/ \u00b7 skill harness", "SKILL.md frontmatter, registry, planning-handoff harness, I/O contract, redaction, validator", "integration"),
    "skillspkg": ("integ", "agent/skills_pkg/ \u00b7 SKILL.md packages", "%d packages loaded by boot_skills() and invoked through list_skills / invoke_skill" % len(SKILL_PKGS), "integration"),
    "platform": ("integ", "agent/ \u00b7 platform, safety and lifecycle", "Temp/Templates policy, orphan reaper, watchdog, log tags, self-update, companion discovery", "platform"),
    "persist": ("integ", "persistence core", "Django models, WAL-safe SQLite copy (online backup API), DB staging for self-update", "persistence"),
    "jdcli": ("integ", "Tlamatini/jd-cli/ \u00b7 bundled Java decompiler", "", "integration"),
    "images": ("integ", "agent/images/ \u00b7 documentation media", "", "knowledge"),
    "selfsrc": ("integ", "agent/TlamatiniSourceCode/ \u00b7 self-modify snapshot slot", "filled by copy_source_assets.py in --self-modify builds", "platform"),
    "fixtures": ("integ", "agent/test_fixtures/", "recorded model output for offline tests", "quality"),
    "static_media": ("front", "agent/static/ \u00b7 images, avatar, PDF frame, sounds, video", "", "presentation"),
    "unit": ("verify", "agent/ \u00b7 unit and contract tests", "%d modules, Django test runner; pin the contracts described in CLAUDE.md" % len(UNIT_TEST_MODULES), "quality"),
    "tests_root": ("verify", "Tests/ \u00b7 avatar, PDF canvas and requirement tests", "", "quality"),
    "auxtests": ("verify", "AuxTests/", "", "quality"),
    "e2e": ("verify", "Tlamatini/tests_e2e/ \u00b7 visible end-to-end runs", "headed Chrome against the real chat GUI", "quality"),
    "roottests": ("verify", "repository root \u00b7 guard tests", "private-data guard, author banner, performance", "quality"),
    "scripts": ("verify", "scripts/ \u00b7 visible checks, release checks and tooling", "*_visible.py, release_*_checks.py, setup cycles, vendoring, catalog and inventory tools", "quality"),
    "harness_claude": ("verify", ".claude/\u2026/tlamatini-daily-chat-test/harness/", "daily chat regression + feature labs (Playwright headed, Shoter screenshots)", "quality"),
    "harness_gemini": ("verify", ".gemini/\u2026/tlamatini-daily-chat-test/harness/", "Gemini mirror of the daily chat harness", "quality"),
    "build": ("build", "build and release tooling", "PyInstaller build, inventories, versioning, release wrappers, dependency and private-data audits", "build"),
    "install": ("build", "install, update and launch", "setup window, recovery, Windows integration, self-update swap, uninstall, launchers", "build"),
    "mcpserver": ("build", "root stdio MCP server", "exposes every pool agent and ACPX to external MCP clients", "integration"),
    "security": ("build", "security/ \u00b7 security arsenal", "Active Defender, whitelist v2 (Controlled Folder Access), access tests", "platform"),
    "ci": ("build", "CI and scanning policy", "", "build"),
    "demo": ("build", "demo flows", "ready-made .flw files for the Agentic Control Panel", "agents"),
    "rootmedia": ("build", "repository root \u00b7 media, documents and license", "", "knowledge"),
    "rootdocs": ("know", "repository root \u00b7 Markdown and text documents", "README, onboarding files for each assistant, design notes and session records", "knowledge"),
    "docs": ("know", "docs/ \u00b7 feature guides", "", "knowledge"),
    "docs_claude": ("know", "docs/claude/ \u00b7 assistant onboarding (auto-imported)", "", "knowledge"),
    "docs_changes": ("know", "docs/changes/ \u00b7 dated change records", "", "knowledge"),
    "guides": ("know", "authoring guides", "create a new agent, MCP/tool or skill", "knowledge"),
    "atlas": ("know", "scripts/architecture_atlas/ and this atlas", "generator and build script of Tlamatini-Architecture.pdf", "knowledge"),
    "claude_cfg": ("know", ".claude/ \u00b7 Claude Code skills, hooks and settings", "canonical skill set; SessionStart hook", "knowledge"),
    "memory": ("know", ".claude/memory/ \u00b7 persistent assistant memory", "feedback, project and user notes", "knowledge"),
    "gemini_skills": ("know", ".gemini/skills/ \u00b7 Gemini mirror", "", "knowledge"),
    "codex_skills": ("know", ".codex/skills/ \u00b7 Codex dossier and release skills", "", "knowledge"),
}
PAGE_NAMES = {"chat": "chat page (agent_page.html)", "acp": "Agentic Control Panel", "pfp": "Prompt Flow Panel",
              "shared": "shared by several pages", "other": "entry pages, PDF frame and indirect loads"}
for _g, _nm in PAGE_NAMES.items():
    META["js_" + _g] = ("front", "agent/static/agent/js/ \u00b7 " + _nm, "", "presentation")
    META["css_" + _g] = ("front", "agent/static/agent/css/ \u00b7 " + _nm, "", "presentation")
for _lib, _d in VENDOR_DESC.items():
    META["vendor_" + _lib] = ("vendor", "vendor/" + _lib, _d, "vendor")


class Cluster:
    def __init__(self, key, chapter, title, sub, layer):
        self.key, self.chapter, self.title, self.sub, self.layer = key, chapter, title, sub, layer
        self.files = []
        self.anchor = ""
        self.sheet = None
        self.color = None
        self.badge = ""


CLUSTERS = collections.OrderedDict()
UNASSIGNED = []
for _p in FILES:
    k = assign(_p)
    if k is None:
        UNASSIGNED.append(_p)
        continue
    if k not in CLUSTERS:
        if k.startswith("ag_") and k != "ag__shared":
            d = k[3:]
            cat = AGENT_CATEGORY.get(d, "Other")
            CLUSTERS[k] = Cluster(k, "agents", AGENT_DISPLAY.get(d, d), cat + ": " + sentence(AGENT_DESC.get(d, ""), 118), "agents")
            CLUSTERS[k].color = "CAT%d" % CATEGORY_ORDER.index(cat)
            CLUSTERS[k].badge = "MT" if d in WRAPPED else ""
        elif k == "ag__shared":
            CLUSTERS[k] = Cluster(k, "agents", "agents/ \u00b7 shared helpers", "copied beside every pool agent: model settings (@config) and visual-error reporting", "agents")
        elif k.startswith("mig_"):
            CLUSTERS[k] = Cluster(k, "migr", "agent/migrations/ \u00b7 from %s" % k[4:], "", "persistence")
        elif k in META:
            ch, ti, su, la = META[k]
            CLUSTERS[k] = Cluster(k, ch, ti, su, la)
        else:
            FATAL.append("No META for cluster key %s (%s)" % (k, _p))
            continue
    CLUSTERS[k].files.append(FI[_p])
    FI[_p].cluster = CLUSTERS[k]
if UNASSIGNED:
    FATAL.append("Unassigned files: %s" % UNASSIGNED)

# migration era subtitles
for _k, _c in CLUSTERS.items():
    if _k.startswith("mig_"):
        nums = [int(f.name[:4]) for f in _c.files if f.name[:4].isdigit()]
        cnt = collections.Counter(mig_kind(f.name) for f in _c.files)
        _c.title = "agent/migrations/ \u00b7 %04d\u2013%04d" % (min(nums), max(nums))
        _c.sub = " \u00b7 ".join("%d %s" % (cnt[k], MIG_KINDS[k][0].lower()) for k in MIG_KINDS if cnt.get(k))

# order clusters per chapter
ORDER = {
    "core": ["proc", "django", "transport", "templates", "mgmt", "intel", "interactor", "rag", "chains", "services", "imaging", "opus", "monitors", "docgen", "agent_other"],
    "integ": ["integ", "acpx", "skills", "skillspkg", "platform", "persist", "jdcli", "images", "selfsrc", "fixtures"],
    "front": ["interactor_front", "js_chat", "js_acp", "js_pfp", "js_shared", "js_other", "css_chat", "css_acp", "css_pfp", "css_shared", "css_other", "static_media"],
    "verify": ["unit", "tests_root", "auxtests", "e2e", "roottests", "scripts", "harness_claude", "harness_gemini"],
    "build": ["build", "install", "mcpserver", "security", "ci", "demo", "rootmedia"],
    "know": ["rootdocs", "docs", "docs_claude", "docs_changes", "guides", "atlas", "claude_cfg", "memory", "gemini_skills", "codex_skills"],
}
CH_CLUSTERS = collections.OrderedDict((ch, []) for ch in CHAPTERS)
for ch in CHAPTERS:
    if ch in ORDER:
        CH_CLUSTERS[ch] = [CLUSTERS[k] for k in ORDER[ch] if k in CLUSTERS]
    elif ch == "migr":
        CH_CLUSTERS[ch] = [CLUSTERS[k] for k in sorted(CLUSTERS) if k.startswith("mig_")]
    elif ch == "vendor":
        CH_CLUSTERS[ch] = [CLUSTERS[k] for k in sorted(CLUSTERS, key=lambda s: (not s.startswith("vendor_frontend"), s)) if k.startswith("vendor_")]
    elif ch == "agents":
        ags = [c for k, c in CLUSTERS.items() if k.startswith("ag_") and k != "ag__shared"]
        ags.sort(key=lambda c: (CATEGORY_ORDER.index(AGENT_CATEGORY.get(c.key[3:], "Other")), c.title.lower()))
        CH_CLUSTERS[ch] = ([CLUSTERS["ag__shared"]] if "ag__shared" in CLUSTERS else []) + ags
# A summarized directory has no file tiles and needs no empty atlas chapter.
CH_CLUSTERS = collections.OrderedDict((ch, clusters) for ch, clusters in CH_CLUSTERS.items() if clusters)
CHAPTERS = collections.OrderedDict((ch, info) for ch, info in CHAPTERS.items() if ch in CH_CLUSTERS)
placed = set()
for ch, cl in CH_CLUSTERS.items():
    for c in cl:
        placed.add(c.key)
missing = [k for k in CLUSTERS if k not in placed]
if missing:
    FATAL.append("Clusters not in any chapter: %s" % missing)
for i, c in enumerate([c for cl in CH_CLUSTERS.values() for c in cl], 1):
    c.anchor = "cl%03d" % i
    if c.color is None:
        c.color = "L" + c.layer

# ----------------------------------------------------------------------------- python dependency matrix (DSM)
DSM_EXCL = re.compile(r"(/migrations/|/agents/|/skills_pkg/|/TlamatiniSourceCode/|/test_[^/]*\.py$|/tests\.py$|_pb2(_grpc)?\.py$|/__init__\.py$)")


def modname(p):
    return p[len("Tlamatini/"):-3].replace("/", ".")


DSM_FILES = [p for p in FILES if p.endswith(".py") and (p.startswith(A) or p.startswith("Tlamatini/tlamatini/") or p == "Tlamatini/manage.py") and not DSM_EXCL.search(p)]
MODS = {modname(p): p for p in DSM_FILES}
PACKAGES = {modname(p)[:-len(".__init__")] for p in FILES if p.endswith("/__init__.py") and p.startswith("Tlamatini/")}


def dsm_group(p):
    if p == "Tlamatini/manage.py" or p.startswith("Tlamatini/tlamatini/"):
        return "project"
    if p.startswith(A) and "/" not in p[len(A):]:
        k = assign(p)
        return {"transport": "transport", "intel": "intelligence", "integ": "integration", "platform": "platform", "persist": "persistence"}.get(k, "intelligence")
    sub = p[len(A):].split("/")[0]
    return {"rag": "rag", "services": "services", "acpx": "acpx", "skills": "skills", "imaging": "intelligence",
            "opus_client": "integration", "monitors": "platform", "management": "transport", "doc_generation": "build"}.get(sub, "intelligence")


DSM_GROUPS = collections.OrderedDict([("project", ("Django project", "Ltransport")), ("transport", ("transport", "Ltransport")),
                                      ("intelligence", ("intelligence", "Lintelligence")), ("rag", ("rag", "Lintelligence")),
                                      ("services", ("services", "Lintelligence")), ("integration", ("integration", "Lintegration")),
                                      ("acpx", ("acpx", "Lintegration")), ("skills", ("skills", "Lintegration")),
                                      ("platform", ("platform", "Lplatform")), ("persistence", ("persistence", "Lpersistence")),
                                      ("build", ("doc generation", "Lbuild"))])
DSM_ORDER = sorted(MODS, key=lambda m: (list(DSM_GROUPS).index(dsm_group(MODS[m])), m))
EDGES = set()
for m in DSM_ORDER:
    p = MODS[m]
    is_pkg = False
    try:
        tree = ast.parse(FI[p].content)
    except SyntaxError:
        continue
    parts = m.split(".")
    for node in ast.walk(tree):
        cands = []
        if isinstance(node, ast.Import):
            cands = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = parts[:-1] if not is_pkg else parts
                base = base[:len(base) - (node.level - 1)] if node.level > 1 else base
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            for a in node.names:
                cands.append(target + "." + a.name)
                cands.append(target)
        for c in cands:
            c = c.strip(".")
            while c:
                if c in MODS:
                    if c != m:
                        EDGES.add((m, c))
                    break
                if c in PACKAGES:
                    break
                c = c.rsplit(".", 1)[0] if "." in c else ""
note("DSM modules %d, edges %d" % (len(DSM_ORDER), len(EDGES)))


def tarjan(nodes, edges):
    adj = collections.defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
    index, low, on, stack, out = {}, {}, set(), [], []
    counter = [0]
    sys.setrecursionlimit(10000)

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in adj[v]:
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            out.append(comp)
    for v in nodes:
        if v not in index:
            strong(v)
    return out


SCCS = [c for c in tarjan(DSM_ORDER, EDGES) if len(c) > 1]

# ----------------------------------------------------------------------------- refs in overview text
REF_ERRORS = []


def resolve_ref(spec):
    if spec in PATHSET:
        return spec
    cands = [p for p in FILES if p.endswith("/" + spec)]
    if len(cands) == 1:
        return cands[0]
    REF_ERRORS.append("%s -> %s" % (spec, cands[:5] if cands else "NOT FOUND"))
    return None


TOKEN_RE = re.compile(r"\[\[([^\]]+)\]\]|\*\*(.+?)\*\*|`([^`]+)`")


def md(text):
    out, pos = [], 0
    for m in TOKEN_RE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        if m.group(1):
            spec, _, label = m.group(1).partition("|")
            label = label or spec
            path = resolve_ref(spec)
            if path:
                out.append(r"\FR{" + FI[path].id + "}{" + esc_tt(label) + "}")
            else:
                out.append(r"\texttt{" + esc(label) + "}")
        elif m.group(2):
            out.append(r"\textbf{" + esc(m.group(2)) + "}")
        else:
            out.append(r"\CODE{" + esc_tt(m.group(3)) + "}")
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


def plain_counts(text):
    sans, tt = 0, 0
    pos = 0
    for m in TOKEN_RE.finditer(text):
        sans += len(text[pos:m.start()])
        if m.group(1):
            tt += len(m.group(1).partition("|")[2] or m.group(1))
        elif m.group(2):
            sans += len(m.group(2)) * 1.08
        else:
            tt += len(m.group(3))
        pos = m.end()
    sans += len(text[pos:])
    return sans, tt


PT = 0.3515


def est_lines(text, tw, size, bullet=True):
    sans, tt = plain_counts(text)
    width = sans * 0.47 * size * PT + tt * 0.53 * size * PT + (0.9 * size * PT if bullet else 0)
    return max(1, math.ceil(width / (tw * 0.86)))


# ----------------------------------------------------------------------------- sheets
class Sheet:
    def __init__(self, title, subtitle, layer, legend=None, bm=None):
        self.title, self.subtitle, self.layer, self.legend = title, subtitle, layer, legend
        self.body = []
        self.num = None
        self.bm = bm or title


SHEETS = []


def new_sheet(title, subtitle, layer, legend=None, bm=None):
    s = Sheet(title, subtitle, layer, legend, bm)
    SHEETS.append(s)
    s.num = len(SHEETS)
    return s


TOP, BOTTOM = 271.5, 16.2
FS = [1.0]       # font scale applied by box()/need_height(); tuned per sheet by autofit()
MINY = [1e9]     # lowest box bottom drawn since the last reset
QUIET = [False]  # suppress layout warnings during autofit trials


def box(out, x, ytop, w, color, title, items, h=None, name=None, size=6.0, tsize=7.0, tint=7, bullet=True, warn_floor=BOTTOM):
    """Titled, rounded box with bullet items (markup). Returns the bottom y."""
    size, tsize = size * FS[0], tsize * FS[0]
    tw = w - 3.0
    hh = tsize * PT + 2.9
    lead = size * 1.24 * PT
    lines = sum(est_lines(it, tw, size, bullet and not it.startswith("!")) for it in items)
    body_h = lines * lead + max(0, len(items) - 1) * 0.45
    need = hh + 1.3 + body_h + 1.5 if items else hh + 0.6
    if h is None:
        h = need
    elif h < need - 0.3 and not QUIET[0]:
        note("WARN box '%s' may overflow (h=%.1f need=%.1f)" % (title, h, need))
    yb = ytop - h
    MINY[0] = min(MINY[0], yb)
    if yb < warn_floor - 0.2 and not QUIET[0]:
        note("WARN box '%s' bottom %.1f below floor %.1f" % (title, yb, warn_floor))
    out.append(T(r"\fill[<c>!<t>, rounded corners=1.1mm] (<x>,<yb>) rectangle (<x2>,<yt>);", c=color, t=tint, x=n2(x), yb=n2(yb), x2=n2(x + w), yt=n2(ytop)))
    out.append(T(r"\fill[<c>, rounded corners=1.1mm] (<x>,<yh>) rectangle (<x2>,<yt>);", c=color, x=n2(x), yh=n2(ytop - hh), x2=n2(x + w), yt=n2(ytop)))
    if items:
        out.append(T(r"\fill[<c>] (<x>,<yh>) rectangle (<x2>,<yh2>);", c=color, x=n2(x), yh=n2(ytop - hh), x2=n2(x + w), yh2=n2(ytop - hh + 1.3)))
    out.append(T(r"\draw[<c>!75!black, line width=0.45pt, rounded corners=1.1mm] (<x>,<yb>) rectangle (<x2>,<yt>);", c=color, x=n2(x), yb=n2(yb), x2=n2(x + w), yt=n2(ytop)))
    out.append(T(r"\node[anchor=west, inner sep=0pt, text=white] at (<x>,<y>) {\adjustbox{max width=<mw>mm}{\fontsize{<ts>}{<tl>}\selectfont\sffamily\bfseries <title>}};",
                 x=n2(x + 1.5), y=n2(ytop - hh / 2), mw=n2(w - 3), ts=n2(tsize), tl=n2(tsize * 1.2), title=md(title)))
    if items:
        parts = []
        for it in items:
            if it.startswith("!"):
                parts.append(md(it[1:]))
            elif bullet:
                parts.append(r"\hangindent=0.95em\hangafter=1{\color{<c>!80!black}\textbullet}\hspace{0.35em}".replace("<c>", color) + md(it))
            else:
                parts.append(md(it))
        body = r"\par\vspace{0.45mm}".join(parts)
        out.append(T(r"\node[anchor=north west, inner sep=0pt, text width=<tw>mm, align=left, text=black!88] at (<x>,<y>) {\fontsize{<s>}{<l>}\selectfont\sffamily <body>\par};",
                     tw=n2(tw), x=n2(x + 1.5), y=n2(ytop - hh - 1.3), s=n2(size), l=n2(size * 1.24), body=body))
    if name:
        out.append(T(r"\node[inner sep=0pt, minimum width=<w>mm, minimum height=<h>mm] (<n>) at (<x>,<y>) {};", w=n2(w), h=n2(h), n=name, x=n2(x + w / 2), y=n2(ytop - h / 2)))
    return yb


def stack(out, x, ytop, w, specs, gap=2.4, **kw):
    y = ytop
    for spec in specs:
        name, color, title, items = spec[:4]
        y = box(out, x, y, w, color, title, items, name=name, **kw) - gap
    return y + gap


def need_height(w, items, size=6.0, tsize=7.0, bullet=True):
    size, tsize = size * FS[0], tsize * FS[0]
    tw = w - 3.0
    hh = tsize * PT + 2.9
    lead = size * 1.24 * PT
    lines = sum(est_lines(it, tw, size, bullet) for it in items)
    return hh + 1.3 + lines * lead + max(0, len(items) - 1) * 0.45 + 1.5


def arrow(out, a, b, label=None, style="arr", path="--", lpos="0.5", lopt="above", color="black!62"):
    lbl = ""
    if label:
        lbl = T(r" node[lbl, pos=<p>, <o>] {<t>}", p=lpos, o=lopt, t=md(label))
    out.append(T(r"\draw[<s>, <c>] (<a>) <path> (<b>)<lbl>;", s=style, c=color, a=a, path=path, b=b, lbl=lbl))


def container(out, x, ytop, w, h, color, title, tint=3):
    out.append(T(r"\fill[<c>!<t>, rounded corners=1.6mm] (<x>,<yb>) rectangle (<x2>,<yt>);", c=color, t=tint, x=n2(x), yb=n2(ytop - h), x2=n2(x + w), yt=n2(ytop)))
    out.append(T(r"\draw[<c>!70!black, line width=0.7pt, dash pattern=on 2.2mm off 0.9mm, rounded corners=1.6mm] (<x>,<yb>) rectangle (<x2>,<yt>);", c=color, x=n2(x), yb=n2(ytop - h), x2=n2(x + w), yt=n2(ytop)))
    out.append(T(r"\node[anchor=north west, inner sep=0pt, text=<c>!75!black] at (<x>,<y>) {\adjustbox{max width=<mw>mm}{\fontsize{7.6}{9}\selectfont\sffamily\bfseries <t>}};", c=color, x=n2(x + 2), y=n2(ytop - 1.6), mw=n2(w - 4), t=md(title)))


def text_node(out, x, y, txt, size=6.0, anchor="north west", width=None, color="black!80", style=r"\sffamily"):
    tw = (", text width=%smm, align=left" % n2(width)) if width else ""
    endpar = r"\par" if width else ""
    out.append(T(r"\node[anchor=<a>, inner sep=0pt<tw>, text=<c>] at (<x>,<y>) {\fontsize{<s>}{<l>}\selectfont<st> <t><e>};",
                 a=anchor, tw=tw, c=color, x=n2(x), y=n2(y), s=n2(size), l=n2(size * 1.25), st=style, e=endpar, t=txt))


# ----------------------------------------------------------------------------- sheet 1: cover (filled at the end)
COVER = new_sheet("Tlamatini \u2014 Complete Architecture Atlas", "", "presentation", bm="Cover, figures and sheet index")


# ----------------------------------------------------------------------------- sheet 2: runtime topology
def sheet_topology():
    sh = new_sheet("Runtime topology \u2014 processes, ports and stores",
                   "One Python process serves the browser pages over HTTP and %d WebSocket routes, starts two built-in MCP servers, and drives pool agents, ACPX children and external MCP servers." % len(WS_ROUTES),
                   "transport")
    o = sh.body
    colA = [
        ("pA1", "Lpresentation", "Chat page", [
            "[[templates/agent/agent_page.html|agent_page.html]]: composer, toolbar modes (Multi-Turn, Exec report, ACPX, Ask Execs, Step-by-Step, Compact mode, Self-modify), canvas, avatar",
            "Boot and state: [[agent_page_init.js]], [[agent_page_state.js]], [[agent_page_ui.js]], [[agent_page_layout.js]]",
            "Messages: [[agent_page_chat.js]] (Copy/Drop, Create Flow, Exec Report)",
            "Canvas: [[agent_page_canvas.js]], [[agent_page_markdown.js]], [[agent_page_pdf.js]]",
            "Voice and avatar: [[chat_dictation.js]], [[mic_settings.js]], [[avatar.js]]",
            "Gauges: [[context_gauge.js]], [[model_capacity.js]], [[self_modify_switch.js]]"]),
        ("pA2", "Lpresentation", "Agentic Control Panel", [
            "[[agentic_control_panel.html]] + [[agentic_control_panel.js]]",
            "Canvas engine: [[acp-canvas-core.js]], [[acp-canvas-undo.js]], [[acp-undo-manager.js]], [[acp-editor-tools.js]]",
            "Flow I/O: [[acp-file-io.js]] (.flw), [[acp-flow-snapshot.js]] \u2192 `/agent/compile_flow/`",
            "Run control: [[acp-control-buttons.js]], [[acp-running-state.js]], [[acp-session.js]], [[acp-validate.js]]"]),
        ("pA3", "Lpresentation", "Prompt Flow Panel", [
            "[[prompt_flow_panel.html]]: diagram editor for chains of prompts saved as `.fpmt`",
            "[[prompt-flow-panel-model.js]] (document contract) and [[prompt-flow-panel.js]] (editor, playback)",
            "Shared canvas mechanics: [[flow-canvas-interactions.js]], [[flow_canvas.css]]"]),
        ("pA4", "Lpresentation", "Entry pages, admin and PDF frame", [
            "[[login.html]], [[welcome.html]] + [[welcome_enter_default.js]]",
            "Django admin skin: [[admin/base_site.html|base_site.html]] + [[admin_theme.css]]",
            "PDF iframe: [[pdf/canvas.html]] + [[pdf_canvas_viewer.js]] + vendored PDF.js"]),
        ("pA5", "Lpresentation", "Shared shell on every page", [
            "Dismissal policy and themed popups: [[dialog_policy.js]], [[dialog_theme.css]]",
            "Theme and splitters: [[ui_tokens.css]], [[ui_shell.css]], [[ui_splitters.css]], [[ui_splitters.js]]",
            "Smart file drop: [[file_drop_router.js]]; bulk toggle: [[checkbox_bulk_toggle.js]]"]),
    ]
    ya = stack(o, 10, TOP, 76, colA)
    inner = []
    col1 = [
        ("pB1", "Ltransport", "Process bootstrap", [
            "[[Tlamatini/manage.py|manage.py]]: tees stdout/stderr into `tlamatini.log`, console shield, coloured console, `django_port`, Temp pin, post-update DB swap and migrate",
            "[[tlamatini/settings.py]] (SQLite WAL, WhiteNoise), [[tlamatini/asgi.py]], [[tlamatini/middleware.py]] (per-user log tags), [[tlamatini/logging_filters.py]]",
            "[[agent/apps.py]] `AgentConfig.ready()`: rebuilds the Agent table, starts the MCP servers, `boot_skills()`, Tier-3 reaper, companion manifest"]),
        ("pB2", "Ltransport", "HTTP surface", [
            "[[tlamatini/urls.py]] \u2192 [[agent/urls.py]]: %d routes" % URL_COUNT,
            "[[agent/views.py]] (pages, agents, flows, DB, prompts, skills, external MCPs), [[flow_file_views.py]], [[model_brain_views.py]], [[pdf_context_views.py]], [[usage_views.py]], [[agent/admin.py]]"]),
        ("pB3", "Ltransport", "WebSocket surface (routing.py)", [
            "Routes declared in [[agent/routing.py]]",
            "`ws/agent/` \u2192 [[agent/consumers.py]] `AgentConsumer`: chat, toggles, Drop, Compact and Self-modify switches, Ask-Execs replies",
            "`ws/prompt-flow-panel/` \u2192 [[prompt_flow_panel_consumer.py]] (one run per connection)",
            "`ws/chat-voice/` \u2192 [[chat_voice_consumer.py]] (direct microphone)"]),
        ("pB4", "Lintelligence", "RAG and answer chains", [
            "[[rag/interface.py]] `ask_rag()` \u2192 [[rag/factory.py]] builds the chain; sidecars inject system and file context",
            "[[rag/chains/basic.py]], [[rag/chains/history_aware.py]], [[rag/chains/unified.py]]",
            "Retrieval: [[rag/retrieval.py]], [[rag/loaders.py]], [[rag/splitters.py]], [[rag/binary_guard.py]] (FAISS + BM25)"]),
    ]
    col2 = [
        ("pB5", "Lintelligence", "Multi-Turn agent", [
            "[[mcp_agent.py]]: capability-aware tool-loop executor",
            "[[global_execution_planner.py]], [[capability_registry.py]], [[self_healing.py]], [[exec_permission.py]]",
            "[[context_fitter.py]], [[compact_mode.py]], [[model_brain.py]], [[model_brain_chat.py]]"]),
        ("pB6", "Lintegration", "Tool surface", [
            "[[agent/tools.py]]: direct tools and one `chat_agent_*` launcher per wrapped agent ([[chat_agent_registry.py]]: %d specs; [[chat_agent_runtime.py]])" % len(WRAPPED),
            "[[acpx/tools.py]]: 12 ACPX/Skill tools; [[external_mcp_manager.py]]: %d supervisors + `ext__<server>__<tool>`" % SUPERVISORS,
            "[[agent_verdict.py]]: deterministic SUCCESS/FAILED from each agent's `INI_SECTION`"]),
        ("pB7", "Lintelligence", "Flow services", [
            "[[services/flow_spec.py]] \u2192 [[services/flow_compiler.py]] with [[services/agent_contracts.py]] and [[services/agent_paths.py]]",
            "[[services/response_parser.py]]: answer cleanup and Exec Report tables",
            "[[services/prompt_flow_panel.py]]: `.fpmt` validator and interpreter"]),
        ("pB8", "Lplatform", "Platform guards", [
            "[[path_guard.py]] (Temp/Templates policy), [[orphan_reaper.py]] (three-tier reaper), [[command_watchdog.py]]",
            "[[log_identity.py]] (`[a3]` user tags), [[cancellation.py]], [[global_state.py]]"]),
    ]
    yb1 = stack(inner, 101, TOP - 10.5, 99, col1)
    yb2 = stack(inner, 203, TOP - 10.5, 100, col2)
    cb = min(yb1, yb2) - 2.5
    container(o, 98, TOP, 208, TOP - cb, "Ltransport", "TLAMATINI SERVER \u2014 manage.py \u2192 Django + Channels on Daphne (ASGI), port `django_port` (default 8000)")
    o.append(T(r"\node[inner sep=0pt, minimum width=208mm, minimum height=<h>mm] (SRV) at (202,<y>) {};", h=n2(TOP - cb), y=n2((TOP + cb) / 2)))
    o.extend(inner)
    colC = [
        ("pC1", "Lintegration", "System-Metrics MCP \u00b7 WebSocket :8765", [
            "[[mcp_system_server.py]] \u2194 [[mcp_system_client.py]]; sidecar [[chain_system_lcel.py]]"]),
        ("pC2", "Lintegration", "Files-Search MCP \u00b7 gRPC :50051", [
            "[[mcp_files_search_server.py]], [[filesearch.proto]] \u2192 [[filesearch_pb2.py]], [[filesearch_pb2_grpc.py]]; sidecar [[chain_files_search_lcel.py]], bounded by [[context_sidecar_timeout.py]]"]),
        ("pC3", "Lintelligence", "LLM back-ends", [
            "Ollama local and cloud (chat, embeddings, vision); sampling per model from [[model_profiles.json]]",
            "Anthropic Claude: [[opus_client/claude_opus_client.py|claude_opus_client.py]]; images: [[imaging/image_interpreter.py]]"]),
        ("pC4", "Lagents", "Pool agent processes", [
            "%d templates in `agent/agents/<type>/`, copied to `agents/pools/<session>/<type>_N` (canvas) or `_chat_runs_` (chat)" % len(AGENT_DIRS),
            "Each run: `<type>.py` + `config.yaml`, PID file, `reanim*` state, `INI_SECTION_<TYPE>` output"]),
        ("pC5", "Lintegration", "ACPX child CLIs", [
            "claude, codex, gemini, cursor, qwen, kiro, kimi, copilot\u2026 spawned by [[acpx/runtime.py]] via [[acpx/windows_spawn.py]] and [[win_shim.py]]; verdict [[acpx/child_health.py]]"]),
        ("pC6", "Lintegration", "External MCP servers", [
            "stdio, streamable-http, sse, websocket; at most 5 active; catalog [[agent/external_mcps.json|external_mcps.json]]; defaults [[external_mcp_defaults.py]]; runtimes [[runtime_provisioner.py]]"]),
        ("pC7", "Lintelligence", "Voice worker", [
            "[[agents/whisperer/chat_worker.py|whisperer/chat_worker.py]] over an authenticated loopback socket ([[chat_voice_runtime.py]], [[chat_voice_settings.py]])"]),
        ("pC8", "Lintegration", "Root stdio MCP server", [
            "[[tlamatini_mcp_server.py]] + [[tlamatini_acpx.py]] expose every pool agent and ACPX to external MCP clients (Claude Code, Kimi): [[.mcp.json]]"]),
    ]
    yc = stack(o, 318, TOP, 92, colC, size=5.8)
    st_top = min(ya, cb, yc) - 6
    stor = [
        ("pS1", "Lpersistence", "SQLite (WAL)", ["`db.sqlite3`: %d models in [[agent/models.py]], %d migrations; WAL-safe backup and Set-DB by [[sqlite_copy.py]]" % (len(MODELS), len(MIGRATIONS))]),
        ("pS2", "Lpersistence", "User state and configuration", ["`config.json` ([[agent/config.json]] template), [[agent/external_mcps.json|external_mcps.json]], contacts, [[preserved_user_state.json]]"]),
        ("pS3", "Lplatform", "Working directories", ["`<app>/Temp` (all scratch) and `<app>/Templates` (scaffolded projects) via [[path_guard.py]]; `agents/pools/` session pools"]),
        ("pS4", "Lplatform", "Logs", ["`tlamatini.log` (truncated at start, per-user tags), each pool agent's own log with `INI_SECTION` blocks"]),
        ("pS5", "Lplatform", "Per-user machine stores", ["`%LOCALAPPDATA%\\Tlamatini`: private runtimes, memory knowledge graph, learned model profiles, setup logs"]),
    ]
    wst = (400 - 4 * 3) / 5.0
    hst = max(need_height(wst, s[3], size=5.8) for s in stor)
    for i, s in enumerate(stor):
        box(o, 10 + i * (wst + 3), st_top - 6.5, wst, s[1], s[2], s[3], h=hst, name=s[0], size=5.8)
    text_node(o, 10, st_top - 0.5, r"\bfseries STORAGE AND STATE", size=7, color="Lpersistence!80!black")
    o.append(T(r"\node[inner sep=0pt, minimum width=400mm, minimum height=<h>mm] (STO) at (210,<y>) {};", h=n2(hst + 6.5), y=n2(st_top - (hst + 6.5) / 2)))
    for nm, lab in (("pA1", "HTTP, WS"), ("pA2", "HTTP"), ("pA3", "WS"), ("pA4", "HTTP"), ("pA5", "")):
        arrow(o, nm + ".east", nm + ".east -| SRV.west", label=lab or None, style="arr2", lopt="above")
    for nm, lab in (("pC1", "WS"), ("pC2", "gRPC"), ("pC3", "HTTP"), ("pC4", "spawn"), ("pC5", "stdio"), ("pC6", "connect"), ("pC7", "socket"), ("pC8", "")):
        if lab:
            arrow(o, nm + ".west -| SRV.east", nm + ".west", label=lab, style="arr2", lopt="above")
    arrow(o, "SRV.south", "SRV.south |- STO.north", label="read / write", style="arr2", lopt="right")
    return sh


# ----------------------------------------------------------------------------- sheet 3: request lifecycle
def sheet_lifecycle():
    sh = new_sheet("Request lifecycle \u2014 from the composer to the rendered answer",
                   "Twelve steps of one chat message in Multi-Turn mode, by the layer that performs them. Every application file named is clickable.", "intelligence")
    o = sh.body
    lanes = [("Browser", "Lpresentation"), ("Channels consumer", "Ltransport"), ("RAG interface and chains", "Lintelligence"),
             ("Multi-Turn executor", "Lintelligence"), ("Tools and agents", "Lagents"), ("Response and persistence", "Lpersistence")]
    ytop, ybot = TOP, 41.0
    lh = (ytop - ybot) / len(lanes)
    for i, (nm, c) in enumerate(lanes):
        yt = ytop - i * lh
        o.append(T(r"\fill[<c>!<t>] (10,<yb>) rectangle (410,<yt>);", c=c, t=5 if i % 2 == 0 else 9, yb=n2(yt - lh), yt=n2(yt)))
        o.append(T(r"\fill[<c>] (10,<yb>) rectangle (16,<yt>);", c=c, yb=n2(yt - lh), yt=n2(yt)))
        o.append(T(r"\node[rotate=90, text=white, inner sep=0pt] at (13,<y>) {\adjustbox{max width=<w>mm}{\fontsize{6.4}{7}\selectfont\sffamily\bfseries <t>}};", y=n2(yt - lh / 2), w=n2(lh - 2), t=esc(nm)))
    steps = [
        (0, "Compose and send", ["[[agent_page_init.js]] sends the prompt and the mode flags over `ws/agent/`"]),
        (1, "Receive", ["[[agent/consumers.py]] binds the user tag ([[log_identity.py]]), saves the prompt (`AgentMessage`), queues retrieval on a worker thread"]),
        (2, "Decide context", ["Internet check ([[inet_determiner.py]]); [[rag/interface.py]] `ask_rag()`; last 8 messages from [[chat_history_loader.py]]"]),
        (2, "Build chain", ["[[rag/factory.py]] picks basic, history-aware or unified; patched `invoke()` pulls sidecar context ([[chain_system_lcel.py]], [[chain_files_search_lcel.py]])"]),
        (3, "Plan and fit", ["[[global_execution_planner.py]] + [[capability_registry.py]]; ACPX filter; `fit_request` ([[context_fitter.py]], [[compact_mode.py]]); [[model_brain.py]]"]),
        (3, "Tool loop", ["[[mcp_agent.py]] executor; each model step through [[self_healing.py]] (watchdog, tactic ladder); dedup and quota guards"]),
        (0, "Ask Execs", ["[[exec_permission.py]] broker \u2192 Proceed/Deny dialog ([[agent_page_dialogs.js]]); Deny halts the chain"]),
        (4, "Run tools", ["[[agent/tools.py]] \u2192 [[chat_agent_runtime.py]] copies and starts a pool agent; `acp_*` children; `ext__*` remote tools"]),
        (4, "Judge", ["Agent prints `INI_SECTION_<TYPE>`; [[agent_verdict.py]] rules SUCCESS/FAILED; Tier-1 [[orphan_reaper.py]]"]),
        (5, "Compose answer", ["[[services/response_parser.py]] strips `END-RESPONSE`, appends the Exec Report and any denial banner, then saves the row"]),
        (1, "Broadcast", ["`agent_message` with `message_id` and `tool_calls_log`; Tier-2 reaper; [[context_governor.py]]; [[usage_tracking.py]]"]),
        (0, "Render", ["[[agent_page_chat.js]] draws the card; [[context_gauge.js]] ring; [[avatar.js]] speaks; Create Flow \u2192 `/agent/flow_from_tool_calls/`"]),
    ]
    x0, slot = 18.0, (410 - 18.0) / len(steps)
    bw = slot - 2.8
    for i, (lane, title, items) in enumerate(steps):
        yt = ytop - lane * lh - 2.2
        bx = x0 + i * slot + 0.4
        c = lanes[lane][1]
        yb = box(o, bx, yt, bw, c, "%d \u00b7 %s" % (i + 1, title), items, name="st%d" % i, size=6.6, tsize=6.9, bullet=False, tint=14)
        if yb < ytop - (lane + 1) * lh + 0.5:
            note("WARN lifecycle step %d overflows its lane" % (i + 1))
    for i in range(len(steps) - 1):
        o.append(T(r"\draw[arr, black!70] (st<a>.east) -- ++(1.4,0) |- (st<b>.west);", a=i, b=i + 1))
    notes = [
        ("Mode gates", ["Multi-Turn off: the legacy one-shot answer. ACPX off: `filter_acpx_tools` strips the 12 ACPX/Skill tools. Exec report and Ask Execs act only inside Multi-Turn. Step-by-Step paces one action per reply; Compact mode binds only the ticked tools."]),
        ("Never hang, never discard, never lie", ["Each model attempt has a watchdog; distinct recovery tactics follow; a graceful answer is built from the work already done, and a recovery preamble tells the user what happened. Only Cancel ([[cancellation.py]]) or an exhausted ladder stops it."]),
        ("What returns to the browser", ["Answer HTML; Exec Report tables (one per agent kind); `tool_calls_log` for Create Flow; context-gauge frames with Ollama's real token count; Compact and Self-modify state frames; message ids for Drop."]),
    ]
    wn = (400 - 2 * 3) / 3.0
    hn = max(need_height(wn, n[1], size=6.0) for n in notes)
    for i, (t, it) in enumerate(notes):
        box(o, 10 + i * (wn + 3), ybot - 3.5, wn, "Lplatform", t, it, h=hn, bullet=False, tint=6)
    return sh


# ----------------------------------------------------------------------------- sheet 4: intelligence core
def sheet_intelligence():
    sh = new_sheet("Intelligence core \u2014 five layers, the Multi-Turn executor and the Model Brain",
                   "How context reaches the model, how each request is fitted to the model's real window, and how every model step is protected.", "intelligence")
    o = sh.body
    layers = [
        ("i1", "Lpersistence", "1 \u00b7 Persisted toggles", ["`Mcp`, `Tool`, `Agent`, `Skill` rows ([[agent/models.py]]) loaded by [[agent/consumers.py]] into status flags; [[compact_mode.py]] rewrites them as one switch"]),
        ("i2", "Lintegration", "2 \u00b7 Runtime MCP services", ["System-Metrics ([[mcp_system_server.py]]) and Files-Search ([[mcp_files_search_server.py]]), started by [[agent/apps.py]] or [[startserver.py]]"]),
        ("i3", "Lintegration", "3 \u00b7 Context sidecars", ["[[chain_system_lcel.py]] and [[chain_files_search_lcel.py]] decide whether `system_context` or `files_context` is needed"]),
        ("i4", "Lintelligence", "4 \u00b7 Answer chains", ["[[rag/chains/basic.py]], [[rag/chains/history_aware.py]], [[rag/chains/unified.py]]; [[rag/factory.py]] patches `invoke()`; [[rag/chains/base.py]] callbacks"]),
        ("i5", "Lagents", "5 \u00b7 Unified-agent tools", ["[[agent/tools.py]] `get_mcp_tools()` + `tool_gate_table()`: direct, wrapped (`chat_agent_*`), ACPX and external-MCP tools"]),
    ]
    y = TOP
    for k, (nm, c, t, it) in enumerate(layers):
        y = box(o, 10, y, 128, c, t, it, name=nm, size=6.8) - 7
    for k in range(len(layers) - 1):
        arrow(o, layers[k][0] + ".south", layers[k + 1][0] + ".north")
    stack(o, 10, y + 2, 128, [
        (None, "Lintelligence", "Chain selection", [
            "`basic`: prompt only, no documents ([[rag/chains/basic.py]])",
            "`history_aware`: RAG with reranking over the loaded context ([[rag/chains/history_aware.py]])",
            "`unified`: tool-enabled agent chains ([[rag/chains/unified.py]]); Multi-Turn binds the full enabled tool surface",
            "Sidecars fetch System-Metrics or Files-Search context only when the question needs it"]),
        (None, "Lplatform", "Ask-Execs allowlist", [
            "Prompts only for tools in `_ASK_EXECS_REQUIRED_TOOLS` ([[mcp_agent.py]]): command and script runners; tier A data-changing (Deleter, Mover, File-Creator, Editor, De-Compresser, PDFer, LaTeXer); tier D remote/network (SCPer, Apirer, Nmapper, Discoverer, Crawler, NetSpeed-Calculator)",
            "Not gated on purpose: tier B messaging and tier C visible desktop/hardware agents",
            "Deny halts the whole chain and shows a red banner; pinned by [[test_ask_execs_allowlist.py]]"]),
    ], size=6.6)
    mid = [
        ("m1", "Ltransport", "Request payload", ["message, history, `multi_turn_enabled`, `acpx_enabled`, `ask_execs_enabled`, `exec_report_enabled`, `step_by_step_enabled` (whitelisted when [[rag/chains/unified.py|unified.py]] rebuilds the payload)"]),
        ("m2", "Lintelligence", "fit_request", ["[[context_fitter.py]] measures the prompt and tool schemas against the model's real window: FULL, COMPACT or STRICT (locked); switch state in [[compact_mode.py]] (`CompactState`)"]),
        ("m3", "Lintelligence", "System prompt", ["[[agent/prompt.pmt]] + self-knowledge [[agent/Tlamatini.md]] (only when Self-modify is on and fits) via [[rag/config.py]]; Temp and Templates rules"]),
        ("m4", "Lintelligence", "Model step", ["[[self_healing.py]] `SelfHealingInvoker` \u2192 [[model_brain_chat.py]] `BrainChatOllama` (reasoning kept inside the tool loop); stop sequences fitted by [[ollama_stop.py]]; text tool-calls recovered by [[local_toolcall_parser.py]]"]),
        ("m5", "Lagents", "Tool call", ["dedup and quota \u2192 Ask-Execs allowlist ([[exec_permission.py]]) \u2192 tool \u2192 Tier-1 reaper ([[orphan_reaper.py]]) \u2192 verdict ([[agent_verdict.py]])"]),
        ("m6", "Lpersistence", "Result", ["`output`, `tool_calls_log`, `exec_report_entries`, `exec_report_denied`, recovery preamble \u2192 [[services/response_parser.py]]"]),
    ]
    y = TOP
    for nm, c, t, it in mid:
        y = box(o, 146, y, 130, c, t, it, name=nm, size=6.6) - 5.2
    for k in range(len(mid) - 1):
        arrow(o, mid[k][0] + ".south", mid[k + 1][0] + ".north")
    o.append(r"\draw[arr, Lintelligence!80!black, dashed] (m5.east) -- ++(4,0) |- (m4.east) node[lbl, pos=0.25, right] {loop};")
    stack(o, 146, y + 1.2, 130, [
        (None, "Lintelligence", "Self-healing tactic ladder", [
            "Each model attempt runs under a watchdog (`unified_agent_llm_step_timeout_seconds`, default 80 s)",
            "Distinct tactics: plain retry, back-off, message-tail trim, plain-LLM fallback, up to `unified_agent_llm_step_max_tactics`",
            "Live status lines reach the chat; the answer carries a recovery preamble; finished work is kept, so Create Flow and the Exec Report survive"]),
        (None, "Lagents", "Verdict engine", [
            "[[agent_verdict.py]] parses `INI_SECTION_<TYPE>` into a typed record; ordered rules decide SUCCESS or FAILED; the agent's self-report outranks the exit code",
            "Closed vocabulary of five disjoint status sets, pinned by [[test_status_vocabulary.py]]"]),
    ], size=6.4)
    right = [
        ("r1", "Lintelligence", "Model Brain", ["Sources in order: overrides \u203a [[model_profiles.json]] \u203a learned profile \u203a Ollama `/api/show` \u203a model defaults", "[[model_brain.py]], [[model_brain_views.py]]; Auto-tuning dialog [[model_brain_tuning.js]]"]),
        ("r2", "Lintelligence", "Context governor", ["[[context_governor.py]] pairs Ollama's `prompt_eval_count` with each request; [[context_baseline.py]] probes the next request at rest; ring in [[context_gauge.js]]"]),
        ("r3", "Lintelligence", "Retrieval stack", ["FAISS + BM25 ([[rag/retrieval.py]]), metadata ([[rag_enhancements.py]]), [[rag/loaders.py]], [[rag/splitters.py]], [[rag/binary_guard.py]], VRAM pre-flight [[embedding_memory_guard.py]], [[gpu_perf.py]]"]),
        ("r4", "Lintelligence", "Documents and vision", ["PDF context: [[pdf_context.py]], [[pdf_context_jobs.py]], [[pdf_image_analysis.py]]; [[visual_error_reporting.py]]; [[imaging/converter.py]], [[imaging/screenshot.py]]"]),
        ("r5", "Lintelligence", "Usage, voice and web", ["[[usage_provider.py]] (Ollama balance), [[usage_tracking.py]] (`UsageDaily`); dictation [[chat_voice_runtime.py]]; [[web_search_llm.py]], [[llm_timing.py]]"]),
        ("r6", "Lintelligence", "Prompt Flow runtime", ["[[prompt_flow_panel_runtime.py]]: own chain, history and embeddings per run; interpreter [[services/prompt_flow_panel.py]]"]),
    ]
    y = TOP
    for nm, c, t, it in right:
        y = box(o, 284, y, 126, c, t, it, name=nm, size=6.6) - 3.2
    stack(o, 284, y - 0.8, 126, [
        (None, "Lintelligence", "Compact mode switch", [
            "Ticking it unticks every MCP, tool, agent and skill row except System-Metrics, Files-Search and Current-Time; unticking re-ticks every row",
            "STRICT: a model that cannot hold everything activated locks it ON; saved rows apply at once (`after_toggles_saved`)",
            "Toolbar box [[model_capacity.js]]; per-row token prices [[compact_costs.js]]"]),
        (None, "Lintelligence", "Self-modify switch", [
            "Rendered only where self-modify is possible: a source run, or a `--self-modify` build",
            "ON sends [[agent/Tlamatini.md]] as self-knowledge when it fits; a small model shows it locked OFF ([[self_modify_switch.js]])"]),
        (None, "Lintelligence", "Ollama limits handled", [
            "At most four stop sequences per request ([[ollama_stop.py]]); the real context window is learned from Ollama's `prompt_eval_count` when a request is cut"]),
    ], size=6.4)
    return sh


# ----------------------------------------------------------------------------- sheet 5: agent ecosystem
def sheet_agents():
    sh = new_sheet("Agent ecosystem \u2014 %d workflow agent types and the flow pipeline" % len(AGENT_DIRS),
                   "From a drawing on the canvas (or a chat answer) to running processes; every chip opens that agent's files in the atlas.", "agents")
    o = sh.body
    pipe = [
        ("q1", "Lpresentation", "Design", ["ACP canvas ([[acp-canvas-core.js]]); FlowCreator AI ([[agents/flowcreator/flowcreator.py|flowcreator.py]], [[agentic_skill.md]], [[flow_catalog.json]]); chat Create Flow"]),
        ("q2", "Lpresentation", "Snapshot", ["[[acp-flow-snapshot.js]] builds `schemaVersion 2`; `.flw` files via [[acp-file-io.js]]"]),
        ("q3", "Lintelligence", "Normalize", ["[[services/flow_spec.py]]: FlowNode, FlowConnection, FlowSpec"]),
        ("q4", "Lintelligence", "Compile", ["[[services/flow_compiler.py]] wires slots per [[services/agent_contracts.py]], redacts secrets; names from [[services/agent_paths.py]]"]),
        ("q5", "Lagents", "Session pool", ["`agents/pools/<session>/<type>_N/config.yaml` + `interconnection-scheme.csv`; shared helpers [[agents/model_settings.py|model_settings.py]]"]),
        ("q6", "Lagents", "Run", ["Starter \u2192 agents \u2192 Parametrizer (`INI_SECTION_<TYPE>`) \u2192 Ender \u2192 Cleaner; LEDs and logs polled by [[acp-running-state.js]]"]),
        ("q7", "Lplatform", "Watch", ["FlowHypervisor ([[monitoring-prompt.pmt]]) answers OK or ATTENTION NEEDED"]),
    ]
    wq = (400 - 6 * 5.0) / 7
    hq = max(need_height(wq, p[3], size=6.3) for p in pipe)
    for i, (nm, c, t, it) in enumerate(pipe):
        box(o, 10 + i * (wq + 5), TOP, wq, c, t, it, h=hq, name=nm, size=6.3)
    for i in range(len(pipe) - 1):
        arrow(o, pipe[i][0] + ".east", pipe[i + 1][0] + ".west")
    top2 = TOP - hq - 7
    text_node(o, 10, top2 + 4.2, r"\bfseries WORKFLOW AGENTS BY CATEGORY \quad\mdseries\color{black!60} chip = agent \textperiodcentered{} MT = also a Multi-Turn chat tool \textperiodcentered{} number = tracked files", size=6.4, color="Lagents!80!black")
    cats = collections.OrderedDict((c, []) for c in CATEGORY_ORDER)
    for d in AGENT_DIRS:
        cats[AGENT_CATEGORY[d]].append(d)
    ncol, gap = 5, 3.0
    cw = (400 - (ncol - 1) * gap) / ncol
    heights = [top2] * ncol
    max_rows = max(math.ceil(len(v) / 2) for v in cats.values() if v)
    pitch = max(6.0, min(7.8, (top2 - BOTTOM - 6.0 - 9.0 - 1.2) / max_rows))
    chip_h = pitch - 1.0
    roles = {"Control Agents": "start, stop, schedule and clean up flows", "Routing Agents": "branch on patterns, choices and counters",
             "Logic Gates": "join parallel branches", "Action Agents": "do the work: shell, files, web, cloud, devices, media, documents",
             "Notification Agents": "watch, notify and message people", "Utility Agents": "parametrize, back up, design and supervise flows",
             "Cryptography Agents": "post-quantum CRYSTALS-Kyber", "Multi-Channel Bridges": "bridges between outside channels and Tlamatini",
             "External Coding-Agent Driver": "external coding-agent CLIs from the canvas"}
    for cat, ds in cats.items():
        if not ds:
            continue
        ds.sort(key=lambda d: AGENT_DISPLAY[d].lower())
        rows = math.ceil(len(ds) / 2)
        h = 9.0 + rows * pitch + 1.2
        col = max(range(ncol), key=lambda i: heights[i])
        x, yt = 10 + col * (cw + gap), heights[col]
        c = "CAT%d" % CATEGORY_ORDER.index(cat)
        o.append(T(r"\fill[<c>!7, rounded corners=1.1mm] (<x>,<yb>) rectangle (<x2>,<yt>);", c=c, x=n2(x), yb=n2(yt - h), x2=n2(x + cw), yt=n2(yt)))
        o.append(T(r"\fill[<c>, rounded corners=1.1mm] (<x>,<yh>) rectangle (<x2>,<yt>);", c=c, x=n2(x), yh=n2(yt - 7.6), x2=n2(x + cw), yt=n2(yt)))
        o.append(T(r"\draw[<c>!75!black, line width=0.45pt, rounded corners=1.1mm] (<x>,<yb>) rectangle (<x2>,<yt>);", c=c, x=n2(x), yb=n2(yt - h), x2=n2(x + cw), yt=n2(yt)))
        o.append(T(r"\node[anchor=north west, inner sep=0pt, text=white] at (<x>,<y>) {\adjustbox{max width=<mw>mm}{\fontsize{6.6}{7.5}\selectfont\sffamily\bfseries <t> (<n>)}};", x=n2(x + 1.5), y=n2(yt - 1.0), mw=n2(cw - 3), t=esc(cat), n=len(ds)))
        o.append(T(r"\node[anchor=north west, inner sep=0pt, text=white] at (<x>,<y>) {\adjustbox{max width=<mw>mm}{\fontsize{4.9}{5.5}\selectfont\sffamily\itshape <t>}};", x=n2(x + 1.5), y=n2(yt - 4.3), mw=n2(cw - 3), t=esc(roles.get(cat, ""))))
        chw = (cw - 3 - 1.4) / 2
        for i, d in enumerate(ds):
            r, k = i // 2, i % 2
            cx = x + 1.5 + k * (chw + 1.4)
            cy = yt - 9.0 - r * pitch - chip_h
            cl = CLUSTERS["ag_" + d]
            o.append(T(r"\filldraw[fill=white, draw=<c>!70, line width=0.35pt, rounded corners=0.8mm] (<x>,<y>) rectangle (<x2>,<y2>);", c=c, x=n2(cx), y=n2(cy), x2=n2(cx + chw), y2=n2(cy + chip_h)))
            o.append(T(r"\fill[<c>, rounded corners=0.5mm] (<x>,<y>) rectangle (<x2>,<y2>);", c=c, x=n2(cx + 0.6), y=n2(cy + 0.7), x2=n2(cx + 1.6), y2=n2(cy + chip_h - 0.7)))
            o.append(T(r"\node[anchor=west, inner sep=0pt] at (<x>,<y>) {\hyperlink{<a>}{\adjustbox{max width=<mw>mm}{\fontsize{<fs>}{<fs>}\selectfont\sffamily\bfseries\color{black!85}<t>}}};", x=n2(cx + 2.3), y=n2(cy + chip_h / 2), a=cl.anchor, mw=n2(chw - 11), fs=n2(min(7.8, 6.7 * pitch / 6.5)), t=esc(AGENT_DISPLAY[d])))
            o.append(T(r"\node[anchor=east, inner sep=0pt, text=black!50] at (<x>,<y>) {\fontsize{4.6}{5}\selectfont\sffamily <n>};", x=n2(cx + chw - 0.7), y=n2(cy + chip_h / 2), n=len(cl.files)))
            if d in WRAPPED:
                o.append(T(r"\node[anchor=east, inner sep=0.45mm, fill=<c>, text=white, rounded corners=0.4mm] at (<x>,<y>) {\fontsize{4.2}{4.5}\selectfont\sffamily\bfseries MT};", c=c, x=n2(cx + chw - 3.3), y=n2(cy + chip_h / 2)))
        heights[col] = yt - h - gap
    anat = ["Each template: `<type>.py` + `config.yaml`; flat helper siblings travel with pool copies (PDFer, PPTXer, LaTeXer, Googler, Video-Analyzer\u2026)",
            "Lifecycle: PID file while running; `AGENT_REANIMATED=1` resumes after pause with `reanim*` state; Ender clears it",
            "Connections: `source_agents` (watch), `target_agents` (start), special slots for OR/AND, Forker/Asker, Counter, Ender",
            "Pool agents import nothing from `agent.*`: %d of %d pool Python files do (checked)" % (POOL_AGENT_IMPORTS, len(POOL_PY))]
    col = max(range(ncol), key=lambda i: heights[i])
    box(o, 10 + col * (cw + gap), heights[col], cw, "Lagents", "Anatomy of a pool agent", anat, size=5.6)
    return sh


# ----------------------------------------------------------------------------- sheet 6: integration surfaces
def sheet_integration():
    sh = new_sheet("Integration surfaces \u2014 ACPX, skills, external MCPs and bridges",
                   "Four ways Tlamatini reaches beyond its own process: coding-agent CLIs, procedural skills, any MCP server, and the outside world.", "integration")
    o = sh.body
    q = {
        "ACPX \u2014 external coding-agent CLIs": (
            [("Registry and transports", ["[[acpx/agent_registry.py]]: agent ids with `oneshot-prompt`, `json-acp`, `tui-repl`, `one-shot` transports; per-agent overrides from `config.json` ([[acpx/config.py]])"]),
             ("Runtime", ["[[acpx/runtime.py]]: reader thread, transport-aware idle rule, NDJSON transcripts ([[acpx/session_store.py]]); [[acpx/permissions.py]] gate"]),
             ("Delivery verdict", ["[[acpx/child_health.py]]: PERMISSION_BLOCKED, AUTH_FAILED, NO_CREDIT, NO_OUTPUT\u2026 an exit code is one bit, so the child's output is judged"])],
            [("LLM surface", ["[[acpx/tools.py]]: `acp_doctor`, `acp_spawn`, `acp_send`, `acp_send_and_wait`, `acp_relay`, `acp_kill`, transcripts, sessions, `list_skills`, `invoke_skill`"]),
             ("Twins", ["Canvas node [[agents/acpxer/acpxer.py|acpxer.py]] and the Django-free root [[tlamatini_acpx.py]] share the same verdict; Windows spawning by [[acpx/windows_spawn.py]] + [[win_shim.py]]"]),
             ("Tests", ["[[acpx/tests.py]]: every failure string copied from real transcripts"])]),
        "Skills \u2014 SKILL.md packages": (
            [("Harness", ["[[skills/registry.py]] discovers packages, [[skills/frontmatter.py]] parses, [[skills/validation.py]] is the one validator, [[skills/harness.py]] returns a planning handoff, [[skills/io_contract.py]], [[skills/redaction.py]]"]),
             ("Boot and admin", ["[[acpx/service.py]] `boot_skills()` mirrors packages into `Skill` rows; ACPX-Skills menu [[skills_dialog.js]]"])],
            [("%d packages in agent/skills_pkg/" % len(SKILL_PKGS), ["!" + ", ".join("`%s`" % s for s in SKILL_PKGS)]),
             ("Assistant skill sets", [".claude/skills (canonical), .gemini/skills (mirror), .codex/skills; counted by [[scripts/skill_inventory.py|skill_inventory.py]]"])]),
        "External MCPs \u2014 universal MCP client": (
            [("Client", ["[[external_mcp_manager.py]]: four transports, background connects, negative cache, supervisor; remote tools as `ext__<server>__<tool>`; %d supervisor tools" % SUPERVISORS]),
             ("Catalog and defaults", ["[[agent/external_mcps.json|external_mcps.json]] (user state, at most 5 active); [[external_mcp_defaults.py]] seeds `memory` and `sequential-thinking`, inactive"])],
            [("Runtime provisioner", ["[[runtime_provisioner.py]]: private node, npm, npx, pnpm, uv, uvx in `%LOCALAPPDATA%`; SHA-256 verified; no admin; npx shims rewritten by [[win_shim.py]]"]),
             ("UI and triage", ["External \u203a MCPs dialog [[external_mcps_dialog.js]]; static triage agent [[agents/mcp_doctor/mcp_doctor.py|mcp_doctor.py]]; runbook [[skills_pkg/adding_external_mcp/SKILL.md|adding_external_mcp]]"])]),
        "Built-in providers and the root MCP server": (
            [("Context providers", ["System-Metrics: [[mcp_system_server.py]] (WebSocket 8765); Files-Search: [[mcp_files_search_server.py]] (gRPC 50051); both started by [[agent/apps.py]]"]),
             ("Root MCP server", ["[[tlamatini_mcp_server.py]] publishes every pool agent as an MCP tool for Claude Code, Kimi and other clients ([[.mcp.json]], [[TLAMATINI_MCP.md]])"])],
            [("One definition of Windows spawning", ["[[win_shim.py]] prefers a real `.exe`, rewrites npm/pnpm shims to `node.exe <script.js>` and avoids cmd.exe, which cuts a multi-line prompt at its first newline; shared by ACPX, the stdio MCP server and External MCPs"])]),
        "Messaging bridges": (
            [("TeleTlamatini", ["[[agents/teletlamatini/teletlamatini.py|teletlamatini.py]]: long-running Telegram bot that brings authorized users into the full Multi-Turn chat"]),
             ("Telegrammer and Whatsapper", ["[[agents/telegrammer/telegrammer.py|telegrammer.py]]: send as the bot or as your own account; [[agents/whatsapper/whatsapper.py|whatsapper.py]]: Meta Cloud API by default, WhatsApp Web on request"])],
            [("Emailer, RecMailer, Notifier", ["SMTP send through Emailer, IMAP watch through RecMailer, and in-browser notifications through Notifier"]),
             ("Instant Messaging Doctor", ["[[instant_messaging_doctor.py]] diagnoses tokens, contacts, templates and the 24-hour window, and is launched after a messaging failure"])]),
        "Devices, engines and security bridges": (
            [("Firmware", ["STM32er (PlatformIO + template MCP, ST-LINK preflight), ESP32er ([[ESP32TemplateProject/platformio.ini|platformio.ini]] template), Arduiner (arduino-cli, [[ArduinoTemplateProject/sketch.yaml|sketch.yaml]]), ESPHomer (YAML devices)"]),
             ("3D engines", ["Blenderer speaks to the Blender MCP add-on socket (9876); Unrealer to the Unreal MCP plugin socket (55557)"])],
            [("Security tooling", ["Kalier (MCP-Kali-Server HTTP API), Nmapper (a locally installed nmap; connect scan by default), Discoverer (ProjectDiscovery tools through a private Go toolchain); authorized targets only"]),
             ("Desktop control", ["Mouser, Keyboarder, Windower and Shoter drive and observe the real desktop; Playwrighter drives a real browser"])]),
    }
    qw = 197.0
    tops = [TOP, TOP]
    bottoms = []
    for qi, (title, (c1, c2)) in enumerate(q.items()):
        col = qi % 2
        x = 10 + col * (qw + 6)
        yt = tops[col]
        if qi >= 2:
            row_prev = bottoms[2 * (qi // 2 - 1): 2 * (qi // 2)]
            yt = min(row_prev) - 5
        inner = []
        iw = (qw - 6 - 3) / 2
        b1 = stack(inner, x + 3, yt - 9.5, iw, [(None, "Lintegration", t, it) for t, it in c1], size=7.0, tsize=7.6)
        b2 = stack(inner, x + 3 + iw + 3, yt - 9.5, iw, [(None, "Lintegration", t, it) for t, it in c2], size=7.0, tsize=7.6)
        bot = min(b1, b2) - 3
        container(o, x, yt, qw, yt - bot, "Lintegration", title)
        o.extend(inner)
        bottoms.append(bot)
    return sh


# ----------------------------------------------------------------------------- sheet 7: frontend module map
def sheet_frontend():
    sh = new_sheet("Frontend module map \u2014 what each page loads, in order",
                   "Parsed from the templates' {% static %} tags. Numbers give the load order; a star marks a module loaded by more than one page.", "presentation")
    o = sh.body
    pages = [("chat", "Chat page \u00b7 agent_page.html", 150.0), ("acp", "Agentic Control Panel", 82.0),
             ("pfp", "Prompt Flow Panel", 76.0), ("misc", "Entry pages, admin, usage dialog, PDF frame", 80.0)]
    misc_refs = []
    for k in ("login", "welcome", "admin", "usage", "pdf"):
        for r in PAGE_REFS[k]:
            misc_refs.append((k, r))
    def _rows(key):
        n = len(misc_refs) if key == "misc" else len(PAGE_REFS[key])
        return math.ceil(n / (2 if key == "chat" else 1))
    s = min(1.6, (TOP - BOTTOM - 13.0) / (max(_rows(k) for k, _, _ in pages) * 3.55))
    o.append(r"\renewcommand{\tilescale}{%s}" % n2(s))
    x = 10.0
    for key, title, w in pages:
        if key == "misc":
            refs = [(k, r) for k, r in misc_refs]
        else:
            refs = [(key, r) for r in PAGE_REFS[key]]
        tiles = []
        for i, (pg, r) in enumerate(refs, 1):
            fi = FI[r]
            label = ("%d " % i) + fi.name + (" \u2605" if len(USED_BY[r]) > 1 else "")
            if key == "misc":
                label = "%s: %s" % ({"login": "login", "welcome": "welcome", "admin": "admin", "usage": "usage", "pdf": "pdf"}[pg], fi.name)
            tiles.append((fi, label))
        k = 2 if key == "chat" else 1
        rows = math.ceil(len(tiles) / k)
        h = 9.0 + rows * 3.55 * s + 2.0
        o.append(T(r"\fill[Lpresentation!6, rounded corners=1.1mm] (<x>,<yb>) rectangle (<x2>,<yt>);", x=n2(x), yb=n2(TOP - h), x2=n2(x + w), yt=n2(TOP)))
        o.append(T(r"\fill[Lpresentation, rounded corners=1.1mm] (<x>,<yh>) rectangle (<x2>,<yt>);", x=n2(x), yh=n2(TOP - 7.2), x2=n2(x + w), yt=n2(TOP)))
        o.append(T(r"\draw[Lpresentation!75!black, rounded corners=1.1mm, line width=0.45pt] (<x>,<yb>) rectangle (<x2>,<yt>);", x=n2(x), yb=n2(TOP - h), x2=n2(x + w), yt=n2(TOP)))
        o.append(T(r"\node[anchor=west, inner sep=0pt, text=white] at (<x>,<y>) {\adjustbox{max width=<mw>mm}{\fontsize{6.8}{8}\selectfont\sffamily\bfseries <t> (<n> assets)}};", x=n2(x + 1.5), y=n2(TOP - 3.6), mw=n2(w - 3), t=esc(title), n=len(tiles)))
        if h > TOP - BOTTOM:
            note("WARN frontend page column %s too tall (%.1f)" % (key, h))
        cw = (w - 3 - (k - 1) * 1.2) / k
        for i, (fi, label) in enumerate(tiles):
            r, c = i % rows, i // rows
            tx = x + 1.5 + c * (cw + 1.2)
            ty = TOP - 9.0 - r * 3.55 * s - 3.1 * s
            o.append(tile_cmd(fi, tx, ty, cw / s, "fill=white,draw=Lpresentation!40", label=label))
        x += w + 4
    o.append(r"\renewcommand{\tilescale}{1}")
    return sh


def tile_cmd(fi, x, y, w, style, label=None, typecolor=None):
    label = fi.name if label is None else label
    loc = short_loc(fi)
    locw = 0.66 * len(loc) + 0.3
    maxw = max(4.0, w - 2.65 - locw - 1.0)
    tc = typecolor or ("T" + ftype(fi))
    return T(r"\Tile{<x>}{<y>}{<w>}{<s>}{<tc>}{<id>}{<mw>}{<lab>}{<loc>}", x=n2(x), y=n2(y), w=n2(w), s=style, tc=tc,
             id=fi.id, mw=n2(maxw), lab=esc(label), loc=esc(loc))


def short_loc(fi):
    if fi.text:
        n = fi.loc
        if n < 1000:
            return str(n)
        if n < 10000:
            return "%.1fk" % (n / 1000.0)
        return "%dk" % round(n / 1000.0)
    b = fi.size
    if b < 1024:
        return "%dB" % b
    if b < 1048576:
        return "%dKB" % round(b / 1024.0)
    return "%.1fMB" % (b / 1048576.0)


# ----------------------------------------------------------------------------- sheet 8: data model
def sheet_data():
    sh = new_sheet("Data model and state \u2014 %d Django models, %d migrations, WAL-safe copies" % (len(MODELS), len(MIGRATIONS)),
                   "Fields parsed from agent/models.py. FK arrows are written as \u2192 Target. The history chart classifies each migration by its file name.", "persistence")
    o = sh.body
    mfi = FI[A + "models.py"]
    ncol, gap = 5, 3.0
    area_w = 268.0
    cw = (area_w - (ncol - 1) * gap) / ncol
    heights = [TOP] * ncol

    def _sim(p):
        hs = [TOP] * ncol
        for _n, flds, _d in MODELS:
            hh = 8.6 * p / 3.7 + max(1, len(flds)) * p + 1.8
            cc = max(range(ncol), key=lambda i: hs[i])
            hs[cc] -= hh + gap
        return min(hs)
    p = 3.7
    while p < 5.6 and _sim(p + 0.1) >= BOTTOM + 2:
        p += 0.1
    for name, fields, doc in MODELS:
        h = 8.6 * p / 3.7 + max(1, len(fields)) * p + 1.8
        col = max(range(ncol), key=lambda i: heights[i])
        x, yt = 10 + col * (cw + gap), heights[col]
        o.append(T(r"\fill[Lpersistence!5, rounded corners=1mm] (<x>,<yb>) rectangle (<x2>,<yt>);", x=n2(x), yb=n2(yt - h), x2=n2(x + cw), yt=n2(yt)))
        o.append(T(r"\fill[Lpersistence, rounded corners=1mm] (<x>,<yh>) rectangle (<x2>,<yt>);", x=n2(x), yh=n2(yt - 6.6 * p / 3.7), x2=n2(x + cw), yt=n2(yt)))
        o.append(T(r"\draw[Lpersistence!75!black, rounded corners=1mm, line width=0.45pt] (<x>,<yb>) rectangle (<x2>,<yt>);", x=n2(x), yb=n2(yt - h), x2=n2(x + cw), yt=n2(yt)))
        o.append(T(r"\node[anchor=west, inner sep=0pt, text=white] at (<x>,<y>) {\hyperlink{fi<id>}{\adjustbox{max width=<mw>mm}{\color{white}\fontsize{<tf>}{<tf>}\selectfont\sffamily\bfseries <t>}}};", x=n2(x + 1.4), y=n2(yt - 3.3 * p / 3.7), id=mfi.id, mw=n2(cw - 3), tf=n2(min(9.4, 7.6 * p / 3.7)), t=esc(name)))
        for i, (fn, ft, tgt) in enumerate(fields):
            y = yt - 8.6 * p / 3.7 - i * p - 1.3 * p / 3.7
            txt = r"{\ttfamily " + esc(fn) + r"} {\color{black!50}" + esc(ft) + (r" $\rightarrow$ \textbf{" + esc(tgt) + "}" if tgt else "") + "}"
            o.append(T(r"\node[anchor=west, inner sep=0pt] at (<x>,<y>) {\adjustbox{max width=<mw>mm}{\fontsize{<ff>}{<ff>}\selectfont\sffamily <t>}};", x=n2(x + 1.4), y=n2(y), mw=n2(cw - 2.8), ff=n2(min(8.4, 6.3 * p / 3.7)), t=txt))
        heights[col] = yt - h - gap
    if min(heights) < BOTTOM:
        note("WARN data model columns overflow (%.1f)" % min(heights))
    # migration history chart
    x0, w0 = 286.0, 124.0
    buckets = collections.OrderedDict()
    for f in MIGRATIONS:
        n = int(f.name[:4])
        b = ((n - 1) // 25) * 25 + 1
        buckets.setdefault(b, collections.Counter())[mig_kind(f.name)] += 1
    yt = TOP
    text_node(o, x0, yt, r"\bfseries Migration history \mdseries(25 per bar, by kind)", size=7, color="Lpersistence!80!black")
    maxc = max(sum(c.values()) for c in buckets.values())
    bar_w = (w0 - 28) / maxc
    for i, (b, cnt) in enumerate(buckets.items()):
        y = yt - 7 - i * 5.2
        text_node(o, x0, y - 0.6, "%04d\u2013%04d" % (b, b + 24), size=5.2, anchor="north west", style=r"\ttfamily")
        xx = x0 + 24
        for k, (lab, col) in MIG_KINDS.items():
            v = cnt.get(k, 0)
            if v:
                o.append(T(r"\fill[M<k>] (<x>,<y1>) rectangle (<x2>,<y2>);", k=k, x=n2(xx), y1=n2(y - 3.6), x2=n2(xx + v * bar_w), y2=n2(y - 0.4)))
                xx += v * bar_w
        text_node(o, xx + 0.8, y - 0.6, str(sum(cnt.values())), size=5.0)
    y = yt - 7 - len(buckets) * 5.2 - 2
    for i, (k, (lab, col)) in enumerate(MIG_KINDS.items()):
        xx = x0 + (i % 3) * 41
        yy = y - (i // 3) * 4.2
        o.append(T(r"\fill[M<k>] (<x>,<y1>) rectangle ++(2.6,2.6);", k=k, x=n2(xx), y1=n2(yy - 3)))
        text_node(o, xx + 3.4, yy - 0.3, esc(lab), size=5.4)
    y -= 12
    flows = [
        ("Backup database", ["[[sqlite_copy.py]] `consistent_copy`: SQLite online backup API (reads through the WAL) \u2192 copy written in DELETE journal mode \u2192 `PRAGMA quick_check` before success"]),
        ("Set DB", ["`move_with_sidecars` / `remove_sidecars` keep `-wal`, `-shm`, `-journal` with their own database; fail-safe, never deletes the source"]),
        ("Self-update carry-over", ["[[apply_update.ps1]] copies the live DB to `DB/ToLoad` + a flag; on next launch [[Tlamatini/manage.py|manage.py]] swaps it back and runs `migrate` in a child ([[DB/ToLoad/README.md|ToLoad]], [[DB/Older/README.md|Older]])"]),
        ("Chat history", ["`AgentMessage` rows are the only history the model reads: [[chat_history_loader.py]] reloads the last 8 per request, so Drop needs no reconnect"]),
    ]
    stack(o, x0, y, w0, [(None, "Lpersistence", t, it) for t, it in flows], size=6.8, tsize=7.4)
    return sh


# ----------------------------------------------------------------------------- sheet 9: build / release / install / update
def sheet_build():
    sh = new_sheet("Build, release, install and self-update pipeline",
                   "From the repository to Installer.exe, then in-app updates that keep user state; plus the guards that keep secrets out of git.", "build")
    o = sh.body
    rows = [
        ("Build", "Lbuild", [
            ("b1", "Version", ["[[versioning.py]] writes `agent/_version.py` (gitignored) from git tags; rules in [[VERSIONING.md]]"]),
            ("b2", "Inputs", ["[[build_runtime_assets.py]] (fail-closed inventory), [[pyinstaller_hooks/hook-numpy.py|hook-numpy]], [[pyinstaller_hooks/hook-torch.py|hook-torch]], [[pyinstaller_hooks/hook-pymupdf.py|hook-pymupdf]], [[requirements.txt]]"]),
            ("b3", "Freeze", ["[[build.py]]: PyInstaller onedir of [[Tlamatini/manage.py|manage.py]], `collectstatic`, carried Python, hidden imports, `verify_frozen_agent_modules()`, gates [[check_agent_runtimes.py]] and [[check_prompt_flow_panel.py]]"]),
            ("b4", "Self-modify (optional)", ["`--self-modify` \u2192 [[copy_source_assets.py]] writes `TlamatiniSourceCode/` and rebuild instructions; bundles [[agent/Tlamatini.md]]"]),
            ("b5", "Package", ["`pkg.zip` \u2192 [[build_uninstaller.py]] (`Uninstaller.exe`) \u2192 [[build_installer.py]] (`Installer.exe`); [[build_all.cmd]] end-to-end"]),
            ("b6", "Release", ["[[build_complete_private_release.py]] / [[build_complete_public_release.py]]; private data audited by [[check_private_data.py]]; keys toggled by [[regen_secrets.py]]"])]),
        ("Install", "Lbuild", [
            ("n1", "Setup window", ["[[install.py]] + [[setup_wizard.py]] (one window for Installer and Uninstaller), transcripts by [[setup_logging.py]]"]),
            ("n2", "Recovery", ["[[setup_recovery.py]]: verified recovery copy and journal before any change; [[setup_windows.py]]: snapshot of Tlamatini's own registry keys and shortcut"]),
            ("n3", "Windows integration", ["[[CreateShortcut.ps1]], [[flow_file_associations.ps1]] (.flw and .fpmt), [[register_flw.ps1]], [[register_fpmt.ps1]]; [[windows_app_registration.py]] + [[agent_manifest.py]] (HKCU discovery)"]),
            ("n4", "Uninstall", ["[[uninstall.py]] + [[uninstall_processes.py]] (owned workers only); keeps `agents/` and non-empty user folders listed in [[preserved_user_state.json]]"])]),
        ("Run and update", "Ltransport", [
            ("u1", "Launch", ["[[Tlamatini.ps1]] or `Tlamatini.exe` \u2192 [[Tlamatini/manage.py|manage.py]] runserver; Explorer-opened flows handled by [[flow_file_open.py]]"]),
            ("u2", "Check", ["About \u203a Check for updates \u2192 [[self_update.py]]: latest GitHub release, download and stage; the dialog is sealed while it downloads"]),
            ("u3", "Swap", ["[[apply_update.ps1]] runs outside the install: stops the tree, `agents` \u2192 `agents_backup`, keeps the preserve set, stages the DB in `DB/ToLoad`"]),
            ("u4", "Migrate", ["Next launch swaps the DB back and runs `migrate` in a child; daily copies by [[backup_db.py]]"])]),
        ("Security and hygiene", "Lplatform", [
            ("h1", "Active defense", ["[[security/tlamatini_defender.ps1|tlamatini_defender.ps1]], [[security/tlamatini_whitelist_v2.ps1|tlamatini_whitelist_v2.ps1]] (Controlled Folder Access), [[security/enable_tlamatini_v2.bat|enable_tlamatini_v2.bat]]"]),
            ("h2", "Repository guards", ["[[test_private_data_guard.py]], [[git_deny_go.py]], [[.github/workflows/name-guard.yml|name-guard.yml]], [[.scanning/finding-policy.json|finding-policy.json]]"]),
            ("h3", "Dependencies", ["[[audit_dependencies.py]], [[scripts/check_requirements_coverage.py|check_requirements_coverage.py]], [[requirements-esphome.txt]]"]),
            ("h4", "Secrets", ["[[regen_secrets.py]] toggles placeholders and keys from the gitignored `data.keys`; [[uncommit-keys.bat]]; [[private_targets.example.json]]"])]),
        ("What ships and what survives", "Lpersistence", [
            ("w1", "Install layout", ["`Tlamatini.exe` + `_internal/` (frozen Django app and collected statics), carried `python/`, `jre/` and `git/`, the `agents/` templates, `DB/`, `Temp/`, `Templates/`"]),
            ("w2", "Kept by self-update", ["`config.json`, `DB`, `Temp`, `Templates`, `application(s)`, the `*_generated` and `context_files` folders and `Uninstaller.exe`; uninstall keeps what [[preserved_user_state.json]] lists"]),
            ("w3", "Self-modify snapshot", ["`TlamatiniSourceCode/` with a manifest and rebuild instructions; secrets redacted and heavy media omitted by [[copy_source_assets.py]]"]),
            ("w4", "Inclusion sweeps", ["[[.claude/skills/tlamatini-self-update-inclusion/scripts/sweep_self_update.py|sweep_self_update.py]] and [[.claude/skills/tlamatini-self-modify-inclusion/scripts/sweep_self_modify.py|sweep_self_modify.py]] prove both pipelines carry every new asset"])], False),
    ]
    pre = []
    for _t, _c, bxs, *_f in rows:
        _bw = (400 - 20 - (len(bxs) - 1) * 5.0) / len(bxs)
        pre.append(max(need_height(_bw, it, size=7.0) for _, _, it in bxs) + 4)
    spare = (TOP - BOTTOM - 2) - sum(pre) - 4 * (len(rows) - 1)
    extra = max(0.0, min(16.0, spare / max(1, len(rows) - 1)))
    y = TOP
    for title, color, boxes, *flags in rows:
        n = len(boxes)
        gapx = 5.0
        bw = (400 - 20 - (n - 1) * gapx) / n
        bh = max(need_height(bw, it, size=7.0) for _, _, it in boxes)
        lane_h = bh + 4
        o.append(T(r"\fill[<c>!5] (10,<yb>) rectangle (410,<yt>);", c=color, yb=n2(y - lane_h), yt=n2(y)))
        o.append(T(r"\fill[<c>] (10,<yb>) rectangle (16,<yt>);", c=color, yb=n2(y - lane_h), yt=n2(y)))
        o.append(T(r"\node[rotate=90, text=white, inner sep=0pt] at (13,<y>) {\adjustbox{max width=<w>mm}{\fontsize{6.4}{7}\selectfont\sffamily\bfseries <t>}};", y=n2(y - lane_h / 2), w=n2(lane_h - 2), t=esc(title)))
        for i, (nm, t, it) in enumerate(boxes):
            box(o, 30 + i * (bw + gapx), y - 2, bw, color, t, it, h=bh, name=nm, size=7.0)
        if not flags or flags[0]:
            for i in range(n - 1):
                arrow(o, boxes[i][0] + ".east", boxes[i + 1][0] + ".west")
        y -= lane_h + 4 + extra
    if y + 4 + extra < BOTTOM and not QUIET[0]:
        note("WARN build sheet overflows (%.1f)" % (y + 4 + extra))
    arrow(o, "b6.south", "n1.north", style="arr", path="-- ++(0,-2) -|", label="Installer.exe", lpos="0.25")
    return sh


# ----------------------------------------------------------------------------- sheet 10: verification and knowledge
def sheet_quality():
    sh = new_sheet("Verification and knowledge \u2014 how Tlamatini is tested and documented",
                   "%d test modules hold %d test functions; every automated run is visible. The documentation graph is what every assistant reads first." % (len(TEST_FILES), TEST_FUNCS), "quality")
    o = sh.body
    left = [
        (None, "Lquality", "Unit and contract tests", ["%d modules in `agent/` (`test_*.py`) + [[acpx/tests.py]]; e.g. [[test_status_vocabulary.py]], [[test_agent_display_names.py]], [[test_dialog_dismissal_policy.py]], [[test_ask_execs_allowlist.py]], [[test_console_shield.py]]" % len(UNIT_TEST_MODULES)]),
        (None, "Lquality", "Visible end-to-end", ["[[Tlamatini/tests_e2e/README.md|tests_e2e]]: headed Chrome against the real GUI, e.g. [[test_self_healing_visual.py]], [[test_create_flow_visual.py]], [[test_db_backup_set_visible.py]]"]),
        (None, "Lquality", "Daily chat harness", ["[[.claude/skills/tlamatini-daily-chat-test/harness/run_test.py|run_test.py]] with [[.claude/skills/tlamatini-daily-chat-test/harness/preflight.py|preflight.py]] (repairs DB, server and login before Chrome opens), [[.claude/skills/tlamatini-daily-chat-test/harness/qualify.py|qualify.py]] and Shoter photos ([[.claude/skills/tlamatini-daily-chat-test/harness/shoter_shot.py|shoter_shot.py]]); Gemini mirror"]),
        (None, "Lquality", "Visible and release checks", ["`scripts/`: `*_visible.py` runners, `release_*_checks.py`, setup lifecycle cycles; JS gates [[scripts/check_js_parse.mjs|check_js_parse.mjs]] + [[eslint.config.mjs]]; Python gate: ruff"]),
        (None, "Lquality", "Policy", ["Headless runs are forbidden: [[TestsVisiblesAndVisibleExecutionFromClaude2Codex.md]]; screenshots only by the Shoter agent; tests must establish their own environment"]),
    ]
    right = [
        (None, "Lknowledge", "Onboarding chain", ["[[CLAUDE.md]] @-imports [[docs/claude/architecture.md|architecture]], [[docs/claude/multi-turn.md|multi-turn]], [[docs/claude/exec-report.md|exec-report]], [[docs/claude/agents.md|agents]], [[docs/claude/acpx.md|acpx]], [[docs/claude/mcp-tools.md|mcp-tools]], [[docs/claude/frontend.md|frontend]], [[docs/claude/gotchas.md|gotchas]]; on demand [[docs/claude/recent-fixes.md|recent-fixes]]"]),
        (None, "Lknowledge", "Other assistants", ["[[AGENTS.md]], [[GEMINI.md]], [[KIMI.md]]; authoring guides [[create_new_agent.md]], [[create_new_mcp.md]], [[create_new_skill.md]]"]),
        (None, "Lknowledge", "Feature guides and records", ["`docs/` feature guides (e.g. [[docs/setup-wizards.md|setup-wizards]], [[docs/canvas-refresh.md|canvas-refresh]], [[docs/model_configuration.md|model_configuration]]) and dated records in `docs/changes/` (e.g. [[docs/changes/2026-10-20-v1.88.0.md|v1.88.0]])"]),
        (None, "Lknowledge", "User-facing", ["[[README.md]], [[BookOfTlamatini.md]], [[agents_descriptions.md]] (tooltips and canvas descriptions), [[ACPX.md]], [[TLAMATINI_MCP.md]]"]),
        (None, "Lknowledge", "Memory, hooks and skills", ["`.claude/memory/` notes, [[.claude/hooks/announce_skills.py|announce_skills.py]] (SessionStart), [[.claude/settings.json]]; four skill locations checked by [[scripts/skill_inventory.py|skill_inventory.py]]"]),
    ]
    yl = stack(o, 10, TOP, 197, left, size=7.4, tsize=8.0)
    yr = stack(o, 213, TOP, 197, right, size=7.4, tsize=8.0)
    y = min(yl, yr) - 7

    def bars(x0, title, color, clusters):
        text_node(o, x0, y, r"\bfseries " + esc(title), size=7.8, color=color + "!80!black")
        maxv = max(len(c.files) for c in clusters) or 1
        for i, c in enumerate(clusters):
            v = len(c.files)
            yy = y - 7.5 - i * 5.8
            text_node(o, x0, yy, esc(c.title), size=6.4, anchor="north west")
            bx = x0 + 90
            bw = 70.0 * v / maxv
            o.append(T(r"\fill[<c>!70] (<x>,<y1>) rectangle (<x2>,<y2>);", c=color, x=n2(bx), y1=n2(yy - 3.6), x2=n2(bx + bw), y2=n2(yy - 0.2)))
            text_node(o, bx + bw + 1.2, yy, esc("%d files, %s lines" % (v, "{:,}".format(sum(f.loc for f in c.files)))), size=6.0)
    bars(10, "Verification assets per cluster", "Lquality", CH_CLUSTERS["verify"])
    bars(213, "Knowledge assets per cluster", "Lknowledge", CH_CLUSTERS["know"])
    nrows = max(len(CH_CLUSTERS["verify"]), len(CH_CLUSTERS["know"]))
    y2 = y - 7.5 - nrows * 5.8 - 6
    top = sorted(TEST_FILES, key=lambda f: (-f.ntests, f.path))[:20]
    text_node(o, 10, y2, r"\bfseries Largest test suites \mdseries(test functions per file, counted with ast)", size=7.8, color="Lquality!80!black")
    maxv = max(1, top[0].ntests)
    for i, f in enumerate(top):
        cc, r = i // 10, i % 10
        x0 = 10 + cc * 203
        yy = y2 - 7.5 - r * 5.4
        label = f.path.replace("Tlamatini/agent/", "agent/").replace("Tlamatini/", "")
        text_node(o, x0, yy, r"\hyperlink{fi%s}{\ttfamily\color{refc}%s}" % (f.id, esc(label)), size=5.9)
        bx = x0 + 112
        bw = 62.0 * f.ntests / maxv
        o.append(T(r"\fill[Lquality!70] (<x>,<y1>) rectangle (<x2>,<y2>);", x=n2(bx), y1=n2(yy - 3.4), x2=n2(bx + bw), y2=n2(yy - 0.3)))
        text_node(o, bx + bw + 1.2, yy, str(f.ntests), size=5.9)
    return sh


# ----------------------------------------------------------------------------- sheet 11: dependency matrix
def sheet_dsm():
    sh = new_sheet("Python module dependency matrix (DSM)",
                   "Row imports column (module-level and lazy in-function imports). %d backend modules, %d dependencies, parsed with ast." % (len(DSM_ORDER), len(EDGES)), "intelligence")
    o = sh.body
    n = len(DSM_ORDER)
    label_w = 44.0
    avail_h = TOP - BOTTOM - 40
    cell = min(avail_h / n, (300 - label_w) / n)
    x0 = 10 + label_w
    ytop = TOP - 40
    idx = {m: i for i, m in enumerate(DSM_ORDER)}
    o.append(T(r"\fill[black!3] (<x>,<yb>) rectangle (<x2>,<yt>);", x=n2(x0), yb=n2(ytop - n * cell), x2=n2(x0 + n * cell), yt=n2(ytop)))
    # group blocks
    start = 0
    groups = []
    for i, m in enumerate(DSM_ORDER + [None]):
        g = dsm_group(MODS[m]) if m else None
        if i > 0 and (m is None or g != dsm_group(MODS[DSM_ORDER[i - 1]])):
            groups.append((dsm_group(MODS[DSM_ORDER[i - 1]]), start, i))
            start = i
    for g, a, b in groups:
        c = DSM_GROUPS[g][1]
        o.append(T(r"\fill[<c>!14] (<x>,<y1>) rectangle (<x2>,<y2>);", c=c, x=n2(x0 + a * cell), y1=n2(ytop - b * cell), x2=n2(x0 + b * cell), y2=n2(ytop - a * cell)))
        o.append(T(r"\draw[<c>!60, line width=0.25pt] (<x>,<y1>) -- (<x2>,<y1>);", c=c, x=n2(x0), y1=n2(ytop - b * cell), x2=n2(x0 + n * cell)))
        o.append(T(r"\draw[<c>!60, line width=0.25pt] (<x>,<y1>) -- (<x>,<y2>);", c=c, x=n2(x0 + b * cell), y1=n2(ytop), y2=n2(ytop - n * cell)))
    for a, b in EDGES:
        i, j = idx[a], idx[b]
        c = DSM_GROUPS[dsm_group(MODS[b])][1]
        o.append(T(r"\fill[<c>!85!black] (<x>,<y>) rectangle ++(<s>,<s>);", c=c, x=n2(x0 + j * cell + 0.12 * cell), y=n2(ytop - (i + 1) * cell + 0.12 * cell), s=n2(cell * 0.76)))
    for i in range(n):
        o.append(T(r"\fill[black!70] (<x>,<y>) rectangle ++(<s>,<s>);", x=n2(x0 + i * cell + 0.3 * cell), y=n2(ytop - (i + 1) * cell + 0.3 * cell), s=n2(cell * 0.4)))
    fs = max(3.0, min(4.6, cell / PT * 0.82))
    for i, m in enumerate(DSM_ORDER):
        g = dsm_group(MODS[m])
        lab = m[len("agent."):] if m.startswith("agent.") else m
        fi = FI[MODS[m]]
        o.append(T(r"\node[anchor=east, inner sep=0pt] at (<x>,<y>) {\hyperlink{fi<id>}{\adjustbox{max width=<mw>mm}{\fontsize{<s>}{<s>}\selectfont\ttfamily\color{<c>!80!black}<t>}}};",
                   x=n2(x0 - 0.8), y=n2(ytop - (i + 0.5) * cell), id=fi.id, mw=n2(label_w - 2), s=n2(fs), c=DSM_GROUPS[g][1], t=esc(lab)))
        o.append(T(r"\node[anchor=west, rotate=90, inner sep=0pt] at (<x>,<y>) {\adjustbox{max width=36mm}{\fontsize{<s>}{<s>}\selectfont\ttfamily\color{<c>!80!black}<t>}};",
                   x=n2(x0 + (i + 0.5) * cell), y=n2(ytop + 0.8), s=n2(fs), c=DSM_GROUPS[g][1], t=esc(lab)))
    # side panel
    sx = x0 + n * cell + 8
    sw = 410 - sx
    fan_in = collections.Counter(b for a, b in EDGES)
    fan_out = collections.Counter(a for a, b in EDGES)

    def short(m):
        return m[len("agent."):] if m.startswith("agent.") else m
    items_in = ["%s \u2014 %d" % (short(m), v) for m, v in fan_in.most_common(12)]
    items_out = ["%s \u2014 %d" % (short(m), v) for m, v in fan_out.most_common(12)]
    items_in = ["%s: %d" % (short(m), v) for m, v in fan_in.most_common(12)]
    items_out = ["%s: %d" % (short(m), v) for m, v in fan_out.most_common(12)]
    scc_items = ["%d modules: %s" % (len(c), ", ".join(short(m) for m in sorted(c)[:9]) + (" \u2026" if len(c) > 9 else "")) for c in sorted(SCCS, key=len, reverse=True)[:6]] or ["none"]
    leg = ["!" + ", ".join(r"%s" % DSM_GROUPS[g][0] for g in DSM_GROUPS)]
    y = TOP
    y = box(o, sx, y, sw, "Lintelligence", "Most imported (fan-in)", ["`" + s + "`" for s in items_in], size=5.6, bullet=False) - 3
    y = box(o, sx, y, sw, "Lintelligence", "Most importing (fan-out)", ["`" + s + "`" for s in items_out], size=5.6, bullet=False) - 3
    y = box(o, sx, y, sw, "Lplatform", "Import cycles (strongly connected)", scc_items, size=5.6) - 3
    y = box(o, sx, y, sw, "Lplatform", "Reading the matrix", ["Diagonal = the module itself; shaded squares = groups (%s). Marks below the diagonal point back to groups listed earlier." % ", ".join(DSM_GROUPS[g][0] for g, a, b in groups), "Pool agents are excluded: they run as separate processes and import nothing from `agent.*`."], size=5.6)
    del leg
    return sh



def sheet_live_editor():
    sh = new_sheet("Live canvas editor and Interactor - v1.91.0",
                   "Editable source, native persistence and tutoring share one document authority. Interactor is a module/tool, not a workflow agent.",
                   "presentation")
    o = sh.body
    left = [
        ("ed1", "Lpresentation", "Editable document", [
            "[[agent_page_editing.js]] owns the CodeMirror buffer, dirty baseline, encoding and save snapshots.",
            "[[agent_page_canvas.js]] owns Open/Refresh and cancellation; Markdown Preview/Source share the current buffer.",
            "Text/code/JSON are editable. HTML/SVG stay inert source. PDFs remain read-only and export original bytes.",
            "Save, Save as, Undo/Redo, Find/replace, Wrap; Ctrl/Cmd+S and Ctrl/Cmd+Shift+S."]),
        ("ed2", "Lpresentation", "Learner control and latency", [
            "Live editor opt-in; first read exact unsaved text and selection, then type a short segment.",
            "guide hands the next field to the learner and ends mutations for that turn. Continue starts fresh chat/read.",
            "Prepared choices match locally: Tab accepts, Ctrl+Right takes one word, Escape dismisses. No per-key model call.",
            "User input/selection, Stop, cancellation or disconnect interrupts and preserves the typed prefix."]),
        ("ed3", "Lpresentation", "Visibility and layout", [
            "A hidden/occluded tab pauses the same command for up to 120 extra seconds; resume at the next character.",
            "No automatic replay after a partial edit. Preview or hiding the canvas returns control.",
            "Automatic layout reserves canvas width; editor fills available height. Manual divider choices remain valid."]),
    ]
    right = [
        ("ed4", "Ltransport", "Authenticated live bridge", [
            "[[interactor/consumer.py]] serves ws/interactor/ with exact Origin/Host and session authentication.",
            "[[interactor/hub.py]] binds server-issued tab IDs to account/session; ContextVar carries identity into tool workers.",
            "Bounded command queues, IDs, deadlines and document/revision checks reject stale work. Full-buffer receipts verify edits.",
            "Live tutoring: 262,144 UTF-16 units; a smaller tool-result budget can refuse content, never silently truncate it."]),
        ("ed5", "Lpersistence", "Native file persistence", [
            "[[canvas_file_views.py]] and [[native_dialogs.py]] provide local Save As outside Downloads.",
            "Authenticated CSRF-protected loopback requests use account/session-bound capabilities; browser filenames are not host-path authority.",
            "Compare full disk revision, stage and flush on the same volume, recheck, then replace. Preserve BOM/encoding, line endings and Windows metadata.",
            "64 MiB text/native-save limit. Save cancellation/failure keeps dirty edits. DB backup/restore is unchanged."]),
        ("ed6", "Lintelligence", "Tool and release carriage", [
            "Migration 0218 registers the Tool and catalog example, not an Agent. tool_gate_table drives binding, Compact and costs.",
            "Ask Execs gates new/save. New unnamed-path work uses a unique Temp/interactor directory; manual files need user-granted write access.",
            "Password input is not command ownership; an email field or DONE reply does not authorize outbound notification.",
            "Current tag and source a771d27c (v1.91.0). Source checks do not certify a newly built installed package."]),
    ]
    stack(o, 12, TOP, 193, left, size=12.0)
    stack(o, 215, TOP, 193, right, size=12.0)
    return sh


def sheet_interaction_settings():
    sh = new_sheet("Live Editor and Terminater configuration - v1.91.0",
                   "One account schema controls real actions; local appearance and a shared speech queue complete the user experience.",
                   "presentation")
    o = sh.body
    left = [
        ("is1", "Lpresentation", "Dialog and draft", [
            "Config / canvas Settings / terminal Settings open [[interaction_settings.html]] on chat, ACP and PFP.",
            "[[interaction_settings.js]] builds Live Editor, Terminater and Voice fields from the server schema.",
            "Presets, reset and preview edit a draft; Save applies, Cancel/Escape discard. Stop, mute and tab access are immediate.",
            "[[interaction_settings.css]] keeps tabs, scrolling and footer controls inside the viewport."]),
        ("is2", "Lpersistence", "Account settings and revisions", [
            "[[interaction_settings.py]] validates ranges/types and serves authenticated CSRF-protected /agent/interaction-settings/.",
            "Migration 0220 adds InteractionSettings: one user, JSON preferences, optimistic revision.",
            "Each action reads a committed snapshot. Conflicting saves ask the user to reload; appearance stays account/browser-local."]),
        ("is3", "Lpresentation", "Real editor behavior", [
            "[[interactor/tool.py]] returns teaching-detail guidance and sends saved pacing, pause and narration with the action.",
            "[[interactor/bridge.js]] keeps document/revision checks and user-first cancellation; guide applies suggestions/ghost choices.",
            "[[agent_page_editing.js]] and the offline CodeMirror bundle apply font, wrap and line numbers; manual scrolling suspends following."]),
    ]
    right = [
        ("is4", "Ltransport", "One terminal dispatch policy", [
            "[[terminal_hub.py]] attaches account preference, presentation and result callbacks to the stdlib TerminalHub engine.",
            "Chat, ACP, PFP and browser actions share it. New flows can use_my_defaults; old explicit flow values remain.",
            "User-only Enter rejects automatic submission and control characters, including aliases/base64. User keys still work.",
            "Shell/advisor defaults affect new terminals. Command wait, no-output and handoff windows stay distinct; timeout does not kill."]),
        ("is5", "Ltransport", "Narration receipts and cancellation", [
            "[[interaction_narration.py]] selects one focused visible account tab; receipts are bound to its exact connection.",
            "Before-typing wait is bounded to 120 seconds. Missing listener, Stop or disconnect cancels; reconnect never replays.",
            "[[voice_runtime.js]] shares one queue with avatar speech; [[interaction_speech.js]] offers explicit skip/stop when voice is unavailable.",
            "Mute and microphone listening win. Secret-marked text and handoff values are not narrated; results speak status only."]),
        ("is6", "Lbuild", "Delivery and dated evidence", [
            "[[build_runtime_assets.py]], [[copy_source_assets.py]], frozen imports, templates and rebuilt editor manifest travel together.",
            "October 23: 17 visible browser checks passed; real OS speech completed before the first terminal key.",
            "Implementation regressions: 929/931 passed; two baseline README assertions were corrected by the documentation sweep.",
            "Existing tag a771d27c. No new executable build or installed acceptance is claimed."]),
    ]
    stack(o, 12, TOP, 193, left, size=11.5)
    stack(o, 215, TOP, 193, right, size=11.5)
    return sh


# ----------------------------------------------------------------------------- atlas flow
HDR, PAD, PADX, PITCH, TILE_H, CGAP, COLGAP = 7.6, 1.3, 1.5, 3.55, 3.1, 2.4, 1.2
CH_LAYER = {"core": "transport", "integ": "integration", "migr": "persistence", "front": "presentation", "vendor": "vendor",
            "agents": "agents", "verify": "quality", "build": "build", "know": "knowledge"}


def tile_width(fi, label):
    loc = short_loc(fi)
    return 2.65 + 0.97 * len(label) + 1.0 + 0.66 * len(loc) + 0.9


def arrange(tiles, inner_w):
    n = len(tiles)
    widths = [tile_width(fi, lab) for fi, lab in tiles]
    kmax = max(1, min(n, int(inner_w // max(10.0, min(widths)))))
    for k in range(kmax, 0, -1):
        rows = math.ceil(n / k)
        chunks = [list(range(j * rows, min(n, (j + 1) * rows))) for j in range(k)]
        chunks = [c for c in chunks if c]
        colw = [max(widths[i] for i in c) for c in chunks]
        total = sum(colw) + (len(chunks) - 1) * COLGAP
        if total <= inner_w or k == 1:
            if total < inner_w:
                extra = (inner_w - total) / len(chunks)
                colw = [w + extra for w in colw]
            else:
                colw = [min(w, inner_w) for w in colw]
            return rows, chunks, colw
    return n, [list(range(n))], [inner_w]


def fit(tiles, inner_w, max_rows):
    n = len(tiles)
    lo = 0
    best = None
    widths = [tile_width(fi, lab) for fi, lab in tiles]
    kmax = max(1, int(inner_w // max(10.0, min(widths))))
    cand = min(n, max_rows * kmax)
    while cand > 0:
        lay = arrange(tiles[:cand], inner_w)
        if lay[0] <= max_rows:
            best = (cand, lay)
            break
        cand -= max(1, (lay[0] - max_rows) * max(1, len(lay[1]) // 2))
    if best is None:
        return lo, None
    return best


def mig_style(fi):
    k = mig_kind(fi.name)
    return "fill=M%s!16,draw=M%s!70" % (k, k)


def emit_piece(sh, cl, x, ytop, w, tiles, layout, cont):
    rows, chunks, colw = layout
    h = HDR + PAD + rows * PITCH - (PITCH - TILE_H) + PAD
    c = cl.color
    o = sh.body
    o.append(T(r"\fill[<c>!6] (<x>,<yb>) rectangle (<x2>,<yt>);", c=c, x=n2(x), yb=n2(ytop - h), x2=n2(x + w), yt=n2(ytop)))
    o.append(T(r"\fill[<c>] (<x>,<yh>) rectangle (<x2>,<yt>);", c=c, x=n2(x), yh=n2(ytop - HDR), x2=n2(x + w), yt=n2(ytop)))
    o.append(T(r"\draw[<c>!75!black, line width=0.4pt] (<x>,<yb>) rectangle (<x2>,<yt>);", c=c, x=n2(x), yb=n2(ytop - h), x2=n2(x + w), yt=n2(ytop)))
    lines = sum(f.loc for f in cl.files)
    cnt = "%d file%s \u00b7 %s lines%s" % (len(cl.files), "" if len(cl.files) == 1 else "s", "{:,}".format(lines), (" \u00b7 " + cl.badge) if cl.badge else "")
    anchor = "" if cont else r"\hypertarget{" + cl.anchor + "}{}"
    title = esc(cl.title) + (r" \mdseries\itshape(continued)" if cont else "")
    o.append(T(r"\node[anchor=north west, inner sep=0pt, text=white] at (<x>,<y>) {<a>\adjustbox{max width=<mw>mm}{\fontsize{6.3}{7}\selectfont\sffamily\bfseries <t>}};",
               x=n2(x + 1.3), y=n2(ytop - 0.9), a=anchor, mw=n2(w - 32), t=title))
    o.append(T(r"\node[anchor=north east, inner sep=0pt, text=white] at (<x>,<y>) {\adjustbox{max width=30mm}{\fontsize{4.8}{5.4}\selectfont\sffamily <t>}};",
               x=n2(x + w - 1.3), y=n2(ytop - 1.1), t=esc(cnt)))
    if cl.sub:
        o.append(T(r"\node[anchor=north west, inner sep=0pt, text=white] at (<x>,<y>) {\adjustbox{max width=<mw>mm}{\fontsize{4.9}{5.5}\selectfont\sffamily\itshape <t>}};",
                   x=n2(x + 1.3), y=n2(ytop - 4.35), mw=n2(w - 2.6), t=esc(cl.sub)))
    style = "fill=white,draw=%s!45" % c
    for j, chunk in enumerate(chunks):
        tx = x + PADX + sum(colw[:j]) + j * COLGAP
        for r, i in enumerate(chunk):
            fi, lab = tiles[i]
            ty = ytop - HDR - PAD - r * PITCH - TILE_H
            st = mig_style(fi) if cl.chapter == "migr" else style
            o.append(tile_cmd(fi, tx, ty, colw[j], st, label=lab))
            fi.sheet = sh.num
    if not cont:
        cl.sheet = sh.num
    return h


def common_root(files):
    dirs = [f.dir for f in files]
    if not dirs or any(d == "" for d in dirs):
        return ""
    pre = os.path.commonprefix([d + "/" for d in dirs])
    return pre[:pre.rfind("/") + 1] if "/" in pre else ""


def flow_chapter(ch, balance=True):
    title, sub, ncol = CHAPTERS[ch]
    colw = (400 - (ncol - 1) * 4.0) / ncol
    inner_w = colw - 2 * PADX
    state = {"sh": None, "col": 0, "y": TOP, "page": 0}

    def new_page():
        state["page"] += 1
        t = title + ("" if state["page"] == 1 else "  (continued %d)" % state["page"])
        state["sh"] = new_sheet(t, sub, CH_LAYER[ch], legend="migr" if ch == "migr" else "types", bm=title + (" - part %d" % state["page"] if state["page"] > 1 else ""))
        state["col"], state["y"] = 0, TOP

    def advance():
        state["col"] += 1
        state["y"] = TOP
        if state["col"] >= ncol:
            new_page()

    def full_h(cl):
        rt = common_root(cl.files)
        rows = arrange([(f, f.path[len(rt):]) for f in cl.files], inner_w)[0]
        return HDR + PAD + rows * PITCH - (PITCH - TILE_H) + PAD

    total = sum(full_h(c) + CGAP for c in CH_CLUSTERS[ch])
    col_target = total / ncol * 1.08 if balance and total <= ncol * (TOP - BOTTOM) * 0.92 else None

    new_page()
    for cl in CH_CLUSTERS[ch]:
        root = common_root(cl.files)
        tiles = [(f, f.path[len(root):]) for f in cl.files]
        remaining = tiles
        if col_target is not None and state["y"] < TOP - 0.1 and state["col"] < ncol - 1:
            if (TOP - state["y"]) + full_h(cl) > col_target:
                advance()
        first = True
        guard = 0
        while remaining:
            guard += 1
            if guard > 400:
                FATAL.append("flow loop for %s" % cl.key)
                break
            avail = state["y"] - BOTTOM
            max_rows = int((avail - HDR - 2 * PAD + (PITCH - TILE_H)) // PITCH)
            full = arrange(remaining, inner_w)
            fresh_rows = int((TOP - BOTTOM - HDR - 2 * PAD + (PITCH - TILE_H)) // PITCH)
            if full[0] <= max_rows:
                n, lay = len(remaining), full
            elif max_rows < 3 or (full[0] <= fresh_rows and state["y"] < TOP - 0.1):
                advance()
                continue
            else:
                n, lay = fit(remaining, inner_w, max_rows)
                if not n:
                    advance()
                    continue
            x = 10 + state["col"] * (colw + 4.0)
            h = emit_piece(state["sh"], cl, x, state["y"], colw, remaining[:n], lay, not first)
            remaining = remaining[n:]
            first = False
            state["y"] -= h + CGAP


# ----------------------------------------------------------------------------- build all sheets
def autofit(fn, target, lo=0.85, hi=1.45):
    """Largest font scale whose lowest box still ends above `target` (binary search)."""
    best = lo
    QUIET[0] = True
    n_before = len(REF_ERRORS)
    for _ in range(10):
        mid = (lo + hi) / 2.0
        FS[0] = mid
        MINY[0] = 1e9
        fn()
        SHEETS.pop()
        if MINY[0] >= target:
            best, lo = mid, mid
        else:
            hi = mid
    del REF_ERRORS[n_before:]
    QUIET[0] = False
    FS[0] = best
    MINY[0] = 1e9
    fn()
    note("autofit %s: font scale %.3f, lowest box %.1f mm (target %.1f)" % (fn.__name__, best, MINY[0], target))
    FS[0] = 1.0


autofit(sheet_topology, BOTTOM + 1.5)
sheet_lifecycle()
sheet_live_editor()
sheet_interaction_settings()
autofit(sheet_intelligence, BOTTOM + 1.5)
sheet_agents()
autofit(sheet_integration, BOTTOM + 4.5)
sheet_frontend()
sheet_data()
autofit(sheet_build, BOTTOM + 4.0)
autofit(sheet_quality, BOTTOM + 7.0 + 7.5 + max(len(CH_CLUSTERS["verify"]), len(CH_CLUSTERS["know"])) * 5.8 + 6.0 + 7.5 + 10 * 5.4 + 3.0)
sheet_dsm()
OVERVIEW_COUNT = len(SHEETS)
CHAPTER_FIRST_SHEET = {}
for ch in CHAPTERS:
    CHAPTER_FIRST_SHEET[ch] = len(SHEETS) + 1
    n0 = len(SHEETS)
    flow_chapter(ch, balance=True)
    if len(SHEETS) - n0 > 1:
        del SHEETS[n0:]
        flow_chapter(ch, balance=False)
NSHEETS = len(SHEETS)

notplaced = [f.path for f in FI.values() if f.sheet is None]
if notplaced:
    FATAL.append("Files without a tile: %s" % notplaced[:20])


# ----------------------------------------------------------------------------- cover
def fill_cover():
    o = COVER.body
    text_node(o, 14, 262, r"\bfseries TLAMATINI", size=58, color="Lpresentation!70!black")
    text_node(o, 14, 238, r"Complete Architecture Atlas", size=26, color="black!80")
    text_node(o, 14, 226.5, r"\itshape eXtended Artificial Intelligence, Humanly Tempered \textperiodcentered{} ``one who knows''", size=12, color="black!65")
    text_node(o, 14, 218, r"Created by \textbf{Angela L\'opez Mendoza} \textperiodcentered{} XAIHT", size=11.5, color="black!75")
    text_node(o, 14, 211, esc("Release %s \u00b7 commit %s (%s) \u00b7 atlas generated %s from application files tracked in git; database history is summarized" % (TAG, HEAD, COMMIT_DATE, TODAY)), size=8, color="black!60")
    kpis = [
        ("{:,}".format(len(FILES)), "listed application files"),
        ("{:,}".format(TOTAL_LOC), "lines of text"),
        (str(sum(1 for f in FI.values() if f.ext == ".py")), "Python files"),
        (str(len(AGENT_DIRS)), "workflow agent types"),
        (str(len(WRAPPED)), "Multi-Turn chat-agent tools"),
        ("%d + %d" % (URL_COUNT, len(WS_ROUTES)), "HTTP routes + WebSocket routes"),
        (str(len(MODELS)), "Django models"),
        (str(len(MIGRATIONS)), "migrations"),
        ("%d / %d" % (len(CH_CLUSTERS and [c for c in CLUSTERS if c.startswith("js_")]) and sum(len(CLUSTERS[c].files) for c in CLUSTERS if c.startswith("js_")), sum(len(CLUSTERS[c].files) for c in CLUSTERS if c.startswith("css_"))), "first-party JS / CSS files"),
        (str(len(SKILL_PKGS)), "SKILL.md packages"),
        ("{:,}".format(TEST_FUNCS), "test functions in %d files" % len(TEST_FILES)),
        (str(sum(1 for f in FI.values() if f.ext == ".md")), "Markdown documents"),
    ]
    cw, chh = 58.0, 18.0
    for i, (v, lab) in enumerate(kpis):
        r, c = i // 4, i % 4
        x, y = 14 + c * (cw + 3), 203 - r * (chh + 3)
        col = list(LAYERS.values())[i % len(LAYERS)][1]
        o.append(T(r"\fill[K<i>!8, rounded corners=1.2mm] (<x>,<yb>) rectangle (<x2>,<yt>);", i=i % len(LAYERS), x=n2(x), yb=n2(y - chh), x2=n2(x + cw), yt=n2(y)))
        o.append(T(r"\fill[K<i>, rounded corners=0.6mm] (<x>,<yb>) rectangle (<x2>,<yt>);", i=i % len(LAYERS), x=n2(x), yb=n2(y - chh), x2=n2(x + 1.6), yt=n2(y)))
        text_node(o, x + 4, y - 2.0, r"\bfseries " + esc(v), size=17, color="K%d!80!black" % (i % len(LAYERS)))
        text_node(o, x + 4, y - 11.6, esc(lab), size=7, color="black!70")
        del col
    # lines by layer bar
    by_layer = collections.Counter()
    files_layer = collections.Counter()
    for c in CLUSTERS.values():
        by_layer[c.layer] += sum(f.loc for f in c.files)
        files_layer[c.layer] += len(c.files)
    y = 132
    text_node(o, 14, y + 6, r"\bfseries Lines of text by architectural layer", size=8, color="black!75")
    total = sum(by_layer.values())
    xx = 14.0
    W = 241.0
    for k in LAYERS:
        v = by_layer.get(k, 0)
        if not v:
            continue
        w = W * v / total
        o.append(T(r"\fill[L<k>] (<x>,<y1>) rectangle (<x2>,<y2>);", k=k, x=n2(xx), y1=n2(y - 7), x2=n2(xx + w), y2=n2(y)))
        xx += w
    for i, k in enumerate(LAYERS):
        r, c = i // 3, i % 3
        x, yy = 14 + c * 81, y - 11 - r * 5.2
        o.append(T(r"\fill[L<k>] (<x>,<y1>) rectangle ++(3,3);", k=k, x=n2(x), y1=n2(yy - 3.2)))
        text_node(o, x + 4.2, yy - 0.2, esc("%s \u2014 %d files, %s lines" % (LAYERS[k][0], files_layer.get(k, 0), "{:,}".format(by_layer.get(k, 0)))), size=6.4)
    y = 92
    text_node(o, 14, y, r"\bfseries File-type markers on every tile", size=8, color="black!75")
    for i, (k, lab, col) in enumerate(TYPES):
        r, c = i // 6, i % 6
        x, yy = 14 + c * 40, y - 6 - r * 5
        o.append(T(r"\fill[T<k>] (<x>,<y1>) rectangle ++(2.6,2.6);", k=k, x=n2(x), y1=n2(yy - 3)))
        text_node(o, x + 3.6, yy - 0.2, esc(lab), size=6.4)
    howto = [
        "**Part A (sheets 2\u2013%d)** draws the architecture: runtime topology, request lifecycle, intelligence core, agents, integrations, frontend, data, build/release, verification and a module dependency matrix. File names in blue are links to the index." % OVERVIEW_COUNT,
        "**Part B (sheets %d\u2013%d)** is the file atlas: every listed application file is a tile inside the cluster where it lives architecturally. Marker = file type, right number = lines (or size for binaries)." % (OVERVIEW_COUNT + 1, NSHEETS),
        "**Part C** is the file index: every file with its ID, path, size and a description extracted from the file itself (docstring, header comment, heading or parsed structure).",
        "Click a tile to open its index entry; click an ID in the index to jump back to the tile. PDF bookmarks list every sheet and cluster.",
    ]
    box(o, 14, 72, 241, "Lpresentation", "How to read this atlas", howto, size=6.6, bullet=True, tint=5)
    # sheet index
    x0 = 268.0
    text_node(o, x0, 271, r"\bfseries SHEET INDEX", size=9, color="Lpresentation!75!black")
    y = 264
    groups = [("Part A \u2014 architecture overview", SHEETS[1:OVERVIEW_COUNT]), ("Part B \u2014 file atlas", SHEETS[OVERVIEW_COUNT:])]
    for gt, ss in groups:
        text_node(o, x0, y, r"\bfseries " + esc(gt), size=7.2, color="black!70")
        y -= 4.6
        for s in ss:
            t = r"\hyperlink{sheet%d}{\textbf{%02d}\enspace %s}" % (s.num, s.num, esc(s.title))
            o.append(T(r"\node[anchor=north west, inner sep=0pt, text width=140mm, align=left] at (<x>,<y>) {\fontsize{6.4}{7.4}\selectfont\sffamily <t>\par};", x=n2(x0 + 2), y=n2(y), t=t))
            y -= 3.9 if len(s.title) < 95 else 6.6
        y -= 2.5
    text_node(o, x0, y, r"\bfseries Part C \textemdash{} \hyperlink{fileindex}{file index (%d entries)}" % len(FILES), size=7.2, color="black!70")
    if y < BOTTOM:
        note("WARN cover sheet index overflows (%.1f)" % y)


fill_cover()


# ----------------------------------------------------------------------------- render
def frame(sh):
    o = []
    c = ("L" + sh.layer) if sh.layer else "Lpresentation"
    num = "%02d" % sh.num
    o.append(r"\node[inner sep=0pt] at (6,292) {\pdfbookmark[0]{%s}{bmsheet%d}\hypertarget{sheet%d}{}};" % (plain_bm("%s %s" % (num, sh.bm)), sh.num, sh.num))
    o.append(r"\draw[black!55, line width=0.9pt] (4,3) rectangle (416,293);")
    o.append(r"\draw[black!22, line width=0.3pt] (5.5,4.5) rectangle (414.5,291.5);")
    if sh is not COVER:
        o.append(T(r"\fill[<c>] (5.5,276) rectangle (9.5,291.5);", c=c))
        o.append(T(r"\node[anchor=west, inner sep=0pt, text=black!88] at (13,286.3) {\adjustbox{max width=<mw>mm}{\fontsize{16.5}{19}\selectfont\sffamily\bfseries <t>}};", mw=232 if sh.legend else 370, t=esc(sh.title)))
        o.append(T(r"\node[anchor=west, inner sep=0pt, text=black!58] at (13,279.4) {\adjustbox{max width=<mw>mm}{\fontsize{7.4}{9}\selectfont\sffamily <t>}};", mw=232 if sh.legend else 370, t=esc(sh.subtitle)))
        o.append(r"\draw[black!22, line width=0.3pt] (5.5,275.6) -- (414.5,275.6);")
    o.append(T(r"\fill[<c>] (391.5,277.4) rectangle (413.5,290.4);", c=c))
    o.append(r"\node[text=white, inner sep=0pt] at (402.5,287.5) {\fontsize{5}{6}\selectfont\sffamily SHEET};")
    o.append(r"\node[text=white, inner sep=0pt] at (402.5,282.0) {\fontsize{14}{15}\selectfont\sffamily\bfseries %s};" % num)
    if sh.legend == "types":
        for i, (k, lab, col) in enumerate(TYPES):
            r, cc = i // 6, i % 6
            x, y = 250 + cc * 23.2, 288.6 - r * 5.6
            o.append(T(r"\fill[T<k>] (<x>,<y>) rectangle ++(2.2,2.2);", k=k, x=n2(x), y=n2(y - 1.1)))
            o.append(T(r"\node[anchor=west, inner sep=0pt, text=black!65] at (<x>,<y>) {\fontsize{5.2}{6}\selectfont\sffamily <t>};", x=n2(x + 2.9), y=n2(y), t=esc(lab)))
    elif sh.legend == "migr":
        for i, (k, (lab, col)) in enumerate(MIG_KINDS.items()):
            r, cc = i // 3, i % 3
            x, y = 262 + cc * 41, 288.6 - r * 5.6
            o.append(T(r"\filldraw[fill=M<k>!16, draw=M<k>!70] (<x>,<y>) rectangle ++(3.4,2.4);", k=k, x=n2(x), y=n2(y - 1.2)))
            o.append(T(r"\node[anchor=west, inner sep=0pt, text=black!65] at (<x>,<y>) {\fontsize{5.4}{6}\selectfont\sffamily <t>};", x=n2(x + 4.2), y=n2(y), t=esc(lab)))
    # title block
    o.append(r"\draw[black!35, line width=0.4pt] (5.5,13.6) -- (414.5,13.6);")
    cells = [(5.5, 128, "TLAMATINI \u00b7 COMPLETE ARCHITECTURE ATLAS", "XAIHT \u00b7 github.com/XAIHT/Tlamatini \u00b7 MIT"),
             (128, 262, "DRAWING", sh.title),
             (262, 312, "RELEASE", "%s \u00b7 commit %s" % (TAG, HEAD)),
             (312, 360, "AUTHOR", "Angela L\u00f3pez Mendoza"),
             (360, 386, "DATE", TODAY),
             (386, 414.5, "SHEET", "%s of %d" % (num, NSHEETS))]
    for i, (xa, xb, lab, val) in enumerate(cells):
        if i:
            o.append(T(r"\draw[black!35, line width=0.4pt] (<x>,4.5) -- (<x>,13.6);", x=n2(xa)))
        bold = r"\bfseries" if i in (0, 5) else ""
        o.append(T(r"\node[anchor=north west, inner sep=0pt, text=black!50] at (<x>,12.8) {\fontsize{4.4}{5}\selectfont\sffamily <b> <t>};", x=n2(xa + 1.6), b=r"\bfseries" if i == 0 else "", t=esc(lab)))
        o.append(T(r"\node[anchor=north west, inner sep=0pt, text=black!82] at (<x>,9.1) {\adjustbox{max width=<mw>mm}{\fontsize{6.2}{7}\selectfont\sffamily<b> <t>}};", x=n2(xa + 1.6), mw=n2(xb - xa - 3.2), b=bold, t=esc(val)))
    return o


PREAMBLE = r"""\documentclass{article}
\usepackage[paperwidth=420mm,paperheight=297mm,margin=0mm]{geometry}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[utf8]{inputenc}
\usepackage{amssymb}
\usepackage{xcolor}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,calc}
\usepackage{adjustbox}
\usepackage{multicol}
\usepackage{fancyhdr}
\usepackage[hidelinks,bookmarksnumbered,bookmarksopen,bookmarksopenlevel=0]{hyperref}
\hypersetup{pdftitle={Tlamatini - Complete Architecture Atlas},pdfauthor={Angela L\'opez Mendoza},pdfsubject={Architecture diagrams of every listed application file of Tlamatini},pdfkeywords={Tlamatini, architecture, Django, Channels, agents, MCP, ACPX, RAG}}
\setlength{\parindent}{0pt}
\setlength{\topskip}{0pt}
\setlength{\parskip}{0pt}
\pagestyle{empty}
\tikzset{arr/.style={-{Stealth[length=2.2mm,width=1.6mm]}, line width=0.75pt},
         arr2/.style={{Stealth[length=2mm,width=1.5mm]}-{Stealth[length=2mm,width=1.5mm]}, line width=0.75pt},
         lbl/.style={font=\sffamily\fontsize{5}{5.6}\selectfont, fill=white, inner sep=0.6pt, text=black!75}}
\definecolor{refc}{HTML}{1A56A8}
\definecolor{codec}{HTML}{6A2C70}
\newcommand{\FR}[2]{\hyperlink{fi#1}{\textcolor{refc}{\ttfamily #2}}}
\newcommand{\CODE}[1]{{\ttfamily\color{codec}#1}}
\newcommand{\tilescale}{1}
\newcommand{\Tile}[9]{\begin{scope}[shift={(#1,#2)},scale=\tilescale,transform shape]%
\filldraw[#4,line width=0.18pt] (0,0) rectangle (#3,3.1);%
\fill[#5] (0.55,0.75) rectangle (2.15,2.35);%
\node[anchor=west,inner sep=0pt] at (2.65,1.55) {\hypertarget{ft#6}{}\hyperlink{fi#6}{\adjustbox{max width=#7mm}{\fontsize{5}{5.5}\selectfont\ttfamily\color{black!88}#8}}};%
\node[anchor=east,inner sep=0pt,text=black!52] at (#3-0.45,1.55) {\fontsize{3.5}{4}\selectfont\sffamily #9};%
\end{scope}}
\newcommand{\FE}[4]{\par\hangindent=1.2em\hangafter=1\noindent\hypertarget{fi#1}{}\hyperlink{ft#1}{\textbf{\color{refc}#1}}\enspace{\ttfamily\color{black!85}#2}\enspace{\color{black!45}\fontsize{4.6}{5}\selectfont[#3]}\enspace{\color{black!62}\itshape #4}\par}
\newcommand{\IH}[4]{\par\addvspace{1.5mm}\noindent\colorbox{#1}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{\color{white}\sffamily\bfseries #2\hfill\mdseries\hyperlink{#4}{\color{white}sheet #3}}}\par\nobreak\vspace{0.7mm}\nobreak}
"""


def colors_tex():
    out = []
    for k, (lab, hx) in LAYERS.items():
        out.append(r"\definecolor{L%s}{HTML}{%s}" % (k, hx))
    for i, (k, (lab, hx)) in enumerate(LAYERS.items()):
        out.append(r"\definecolor{K%d}{HTML}{%s}" % (i, hx))
    for k, lab, hx in TYPES:
        out.append(r"\definecolor{T%s}{HTML}{%s}" % (k, hx))
    for i, c in enumerate(CATEGORY_ORDER):
        out.append(r"\definecolor{CAT%d}{HTML}{%s}" % (i, CAT_COLOR[c]))
    for k, (lab, hx) in MIG_KINDS.items():
        out.append(r"\definecolor{M%s}{HTML}{%s}" % (k, hx))
    return "\n".join(out)


def render_index():
    out = []
    out.append(r"\newgeometry{left=9mm,right=9mm,top=15mm,bottom=12mm,headheight=6mm,headsep=3mm,footskip=6mm}")
    out.append(r"\pagestyle{fancy}\fancyhf{}")
    out.append(r"\fancyhead[L]{\sffamily\fontsize{7}{8}\selectfont\bfseries TLAMATINI \textperiodcentered{} COMPLETE ARCHITECTURE ATLAS \textemdash{} Part C: file index}")
    out.append(r"\fancyhead[R]{\sffamily\fontsize{7}{8}\selectfont %s \textperiodcentered{} commit %s \textperiodcentered{} Angela L\'opez Mendoza}" % (esc(TAG), HEAD))
    out.append(r"\fancyfoot[C]{\sffamily\fontsize{7}{8}\selectfont page \thepage}")
    out.append(r"\renewcommand{\headrulewidth}{0.3pt}")
    out.append(r"\pdfbookmark[0]{Part C - file index}{bmfileindex}\hypertarget{fileindex}{}")
    out.append(r"\setlength{\columnsep}{4mm}\setlength{\columnseprule}{0.2pt}")
    out.append(r"\noindent{\sffamily\fontsize{12}{14}\selectfont\bfseries File index \textemdash{} %d tracked files}\par" % len(FILES))
    out.append(r"\noindent{\sffamily\fontsize{6.6}{8}\selectfont\color{black!60} ID (click to see the tile) \textperiodcentered{} path \textperiodcentered{} [lines or size] \textperiodcentered{} description extracted from the file itself. Grouped exactly like the atlas.}\par\vspace{2mm}")
    out.append(r"\begin{multicols*}{4}")
    out.append(r"\raggedright\sffamily\fontsize{5.6}{6.75}\selectfont\interlinepenalty=10000\relax")
    for ch, cls in CH_CLUSTERS.items():
        out.append(r"\par\addvspace{2mm}\noindent{\fontsize{7.4}{8.6}\selectfont\bfseries\color{black!75}%s}\par\nobreak\vspace{0.6mm}" % esc(CHAPTERS[ch][0]))
        out.append(r"\pdfbookmark[1]{%s}{bmch%s}" % (plain_bm(CHAPTERS[ch][0]), ch))
        for cl in cls:
            out.append(r"\pdfbookmark[2]{%s}{bm%s}" % (plain_bm(cl.title), cl.anchor))
            out.append(r"\IH{%s}{%s}{%d}{%s}" % (cl.color, esc(cl.title), cl.sheet or 0, cl.anchor))
            for f in cl.files:
                out.append(r"\FE{%s}{%s}{%s}{%s}" % (f.id, esc_tt(f.path), esc(short_loc(f) + (" lines" if f.text else "")), esc(f.desc)))
    out.append(r"\end{multicols*}")
    return "\n".join(out)


def write_tex():
    parts = [PREAMBLE, colors_tex(), r"\begin{document}"]
    for sh in SHEETS:
        parts.append(r"\noindent\begin{tikzpicture}[x=1mm,y=1mm]")
        parts.append(r"\useasboundingbox (0,0) rectangle (420,296);")
        parts.extend(frame(sh))
        parts.extend(sh.body)
        parts.append(r"\end{tikzpicture}")
        parts.append(r"\clearpage")
    parts.append(render_index())
    parts.append(r"\end{document}")
    tex = "\n".join(parts) + "\n"
    os.makedirs(OUT, exist_ok=True)
    with open(TEX_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(tex)
    return len(tex)


if REF_ERRORS:
    FATAL.append("Unresolved file references: %s" % REF_ERRORS)
size = write_tex()
ids = [f.id for f in FI.values()]
note("Sheets: %d (overview %d, atlas %d); clusters %d; tiles placed %d of %d; unique ids %d" % (
    NSHEETS, OVERVIEW_COUNT, NSHEETS - OVERVIEW_COUNT, len(CLUSTERS), sum(1 for f in FI.values() if f.sheet), len(FILES), len(set(ids))))
note("TeX written: %s (%d bytes)" % (TEX_PATH, size))
for ch in CHAPTERS:
    note("  chapter %s starts at sheet %d with %d clusters" % (ch, CHAPTER_FIRST_SHEET[ch], len(CH_CLUSTERS[ch])))
if SCCS:
    note("Import cycles: " + "; ".join("%d mods" % len(c) for c in SCCS))
for msg in FATAL:
    note("FATAL " + msg)
with open(REPORT_PATH, "w", encoding="utf-8") as fh:
    fh.write("\n".join(REPORT) + "\n")
sys.exit(2 if FATAL else 0)
