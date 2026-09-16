# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Portable styled LaTeX scaffolds, with separate document and Beamer recipes.

Only newly authored documents use this renderer. Existing sources are never
regex-restyled. The exported .tex is self-contained and builds independently of
Python with pdfLaTeX, XeLaTeX or LuaLaTeX. Metadata and content remain LaTeX.
"""
import re

from latexer_artwork import artwork
from latexer_styles import build_theme


SUPPORTED_CLASSES = ("article", "report", "book", "letter", "beamer")
SUPPORTED_TEMPLATES = (*SUPPORTED_CLASSES, "cv", "homework", "spanish-article")


def _sub(template, values):
    """Single pass: tokens inside author content must never be expanded."""
    return re.sub(r"@@([A-Z_]+)@@", lambda m: str(values[m[1]]), template)


def _packages(config):
    raw = config.get("packages") or []
    if isinstance(raw, str):
        raw = [name for name in re.split(r"[,\n]", raw) if name.strip()]
    if not isinstance(raw, (list, tuple)):
        raise ValueError("packages must be a list or comma/newline-separated package names")
    packages = []
    for entry in raw:
        for name in str(entry).split(","):
            name = name.strip()
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                raise ValueError("Styled packages must be package names; put package options in a custom preamble.")
            if name not in packages:
                packages.append(name)
    return packages


def validate_design(config, template=None):
    theme = build_theme(config)
    if theme is None:
        return None
    cls = template or str(config.get("documentclass") or "article").strip()
    if cls not in (SUPPORTED_TEMPLATES if template else SUPPORTED_CLASSES):
        raise ValueError("Style rendering supports %s; custom classes should supply their own complete .tex." %
                         ", ".join(SUPPORTED_TEMPLATES if template else SUPPORTED_CLASSES))
    _packages(config)
    return theme


_FONTS = r"""\usepackage{iftex}
\ifPDFTeX
  \usepackage[utf8]{inputenc}
  \usepackage[T1]{fontenc}
  \usepackage{lmodern}
\else
  \usepackage{fontspec}
  \setmainfont{Latin Modern Roman}
  \setsansfont{Latin Modern Sans}
  \setmonofont{Latin Modern Mono}
\fi
"""

_COMPONENTS = r"""
% Opt-in, flow-based components; ordinary LaTeX remains ordinary LaTeX.
\newcommand{\TLtablehead}{\rowcolor{TLPrimary}\color{TLOnPrimary}}
\newcommand{\TLcellhead}[1]{\textcolor{TLOnPrimary}{\bfseries #1}}
\newenvironment{TLcallout}[1]{%
  \par\addvspace{1em}\begin{quote}\color{TLPrimary}%
  \noindent\rule{\linewidth}{.6pt}\par\smallskip
  \noindent\textbf{#1}\par\smallskip\color{TLInk}\ignorespaces
}{\par\smallskip\noindent\textcolor{TLRule}{\rule{\linewidth}{.4pt}}\end{quote}\addvspace{.5em}}
\lstset{basicstyle=\ttfamily\small\color{TLSurfaceInk},
  backgroundcolor=\color{TLSurface},keywordstyle=\bfseries\color{TLSurfaceAccent},
  commentstyle=\color{TLSurfaceAccent},stringstyle=\color{TLSurfaceInk},
  breaklines=true,columns=fullflexible,keepspaces=true,showstringspaces=false,
  frame=single,rulecolor=\color{TLRule},framerule=.4pt,
  xleftmargin=5pt,xrightmargin=5pt,framexleftmargin=4pt,framexrightmargin=4pt,
  aboveskip=1em,belowskip=1em}
\renewcommand{\arraystretch}{1.3}
\setlength{\tabcolsep}{7pt}
"""

_PAGE_STYLE = r"""
\pagecolor{TLBackground}\color{TLInk}
\AtBeginDocument{\color{TLInk}}
\linespread{@@LEADING@@}
\setlength{\parindent}{0pt}
\setlength{\parskip}{.65em plus .15em minus .1em}
\setlength{\emergencystretch}{2em}
\setlength{\headheight}{15pt}
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\footnotesize\sffamily\textcolor{TLMuted}{@@LABEL@@}}
\fancyhead[R]{\footnotesize\sffamily\textcolor{TLMuted}{TLAMATINI}}
\fancyfoot[L]{\scriptsize\sffamily\textcolor{TLMuted}{@@FAMILY@@ / LATEXER}}
\fancyfoot[R]{\small\sffamily\textcolor{TLPrimary}{\thepage}}
\renewcommand{\headrulewidth}{.4pt}
\renewcommand{\headrule}{\hbox to\headwidth{\color{TLRule}\leaders\hrule height \headrulewidth\hfill}}
\fancypagestyle{plain}{\fancyhf{}%
  \fancyfoot[L]{\scriptsize\sffamily\textcolor{TLMuted}{@@LABEL@@}}%
  \fancyfoot[R]{\small\sffamily\textcolor{TLPrimary}{\thepage}}%
  \renewcommand{\headrulewidth}{0pt}}
"""

_HEADINGS = r"""
\titleformat{\section}{@@HEADING@@\Large\bfseries\color{TLPrimary}}{\thesection}{.7em}{}
\titleformat{\subsection}{@@HEADING@@\large\bfseries\color{TLSecondary}}{\thesubsection}{.7em}{}
\titleformat{\subsubsection}{@@HEADING@@\normalsize\bfseries\color{TLPrimary}}{\thesubsubsection}{.7em}{}
\titlespacing*{\section}{0pt}{1.6em}{.65em}
\titlespacing*{\subsection}{0pt}{1.2em}{.45em}
"""

_CHAPTERS = r"""
\titleformat{\chapter}[display]{@@HEADING@@\bfseries\color{TLPrimary}}
  {\large\chaptertitlename\ \thechapter}{.6em}{\Huge}
\titlespacing*{\chapter}{0pt}{0pt}{1.6em}
"""

_COVER = r"""
\begin{titlepage}
\thispagestyle{empty}
{\sffamily\small\color{TLPrimary} TLAMATINI\hfill @@LABEL@@\par}
\vspace{.6em}{\color{TLRule}\hrule}\vspace{2.3em}
{@@HEADING@@\bfseries\fontsize{@@TITLE_SIZE@@}{@@TITLE_LEADING@@}\selectfont\color{TLPrimary}
\raggedright @@TITLE@@\par}
@@SUBTITLE@@
\vfill
@@ART@@
\vfill
{\color{TLRule}\hrule}\vspace{.8em}
{\sffamily\color{TLInk}@@AUTHOR@@\par}
{\small\color{TLMuted}@@DATE@@\par}
\end{titlepage}
"""

_COMPACT_TITLE = r"""
{@@HEADING@@\LARGE\bfseries\color{TLPrimary}\raggedright @@TITLE@@\par}
@@SUBTITLE@@
{\small\color{TLMuted}@@AUTHOR@@\par @@DATE@@\par}
\medskip{\color{TLRule}\hrule}\bigskip
"""

_BEAMER = r"""
\setbeamercolor{normal text}{fg=TLInk,bg=TLBackground}
\setbeamercolor{structure}{fg=TLPrimary}
\setbeamercolor{frametitle}{fg=TLPrimary,bg=TLBackground}
\setbeamercolor{title}{fg=TLPrimary,bg=TLBackground}
\setbeamercolor{subtitle}{fg=TLSecondary}
\setbeamercolor{author}{fg=TLInk}
\setbeamercolor{date}{fg=TLMuted}
\setbeamercolor{block title}{fg=TLOnPrimary,bg=TLPrimary}
\setbeamercolor{block body}{fg=TLSurfaceInk,bg=TLSurface}
\setbeamercolor{footline}{fg=TLMuted,bg=TLBackground}
\setbeamerfont{title}{family=@@HEADING@@,size=\LARGE,series=\bfseries}
\setbeamerfont{frametitle}{family=@@HEADING@@,series=\bfseries}
\setbeamertemplate{navigation symbols}{}
\setbeamertemplate{footline}{\begin{beamercolorbox}[wd=\paperwidth,ht=3mm,dp=4mm,leftskip=4mm,rightskip=4mm]{footline}%
  \scriptsize @@LABEL@@\hfill\insertframenumber\end{beamercolorbox}}
\setbeamertemplate{itemize item}{\color{TLPrimary}\small$\blacktriangleright$}
"""


def render_document(config, template=None):
    """Build a complete source. template=None means discrete create_file inputs."""
    theme = validate_design(config, template)
    if not theme:
        raise ValueError("render_document requires an explicit style")
    kind = template or str(config.get("documentclass") or "article").strip()
    cls = "article" if kind in ("cv", "homework", "spanish-article") else kind
    beamer = cls == "beamer"
    options = str(config.get("class_options") or (
        "aspectratio=169" if beamer else "11pt,a4paper,openany" if cls == "book" else "11pt,a4paper"))
    title = str(config.get("title") or ("Untitled Document" if template else "")).strip()
    author = str(config.get("author") or "Tlamatini").strip()
    date = str(config.get("date") or r"\today").strip()
    subtitle = str(config.get("subtitle") or "").strip()
    content = str(config.get("content") or "Replace this paragraph with your own text.")
    heading = {"sans": r"\sffamily", "serif": r"\rmfamily", "mono": r"\ttfamily"}[theme["heading"]]
    values = dict(LABEL=theme["label"], FAMILY=theme["family"].upper(),
                  LEADING=theme["leading"], HEADING=heading, TITLE=title, AUTHOR=author,
                  DATE=date, TITLE_SIZE=28 if len(title) > 90 else 36,
                  TITLE_LEADING=34 if len(title) > 90 else 42,
                  SUBTITLE=(r"\vspace{.9em}{\large\color{TLSecondary}" + subtitle + "\\par}\n") if subtitle else "")
    art = artwork(theme["motif"], theme["decoration"])
    values["ART"] = (r"\begin{center}\resizebox{.96\linewidth}{!}{%" + "\n" + art + "\n}\\end{center}") if art else ""

    # Pass options before Beamer (or TikZ) can load xcolor on our behalf.
    lines = ["%% LaTeXer style: %s | %s | %s\n" % (theme["id"], theme["mode"], theme["decoration"]),
             r"\PassOptionsToPackage{table}{xcolor}" + "\n",
             "\\documentclass[%s]{%s}\n" % (options, cls), _FONTS]
    spanish = kind == "spanish-article" or str(config.get("document_language") or "en").lower().startswith("es")
    if spanish:
        # shorthands=off keeps active babel punctuation from altering TikZ syntax.
        lines.append("\\usepackage[spanish,mexico,shorthands=off]{babel}\n")
    if not beamer:
        geometry = config.get("geometry", "margin=2.5cm")
        if geometry:
            lines.append("\\usepackage[%s]{geometry}\n" % geometry)
    standard = ["xcolor", "graphicx", "amsmath", "amssymb", "tikz", "booktabs", "tabularx", "listings"]
    if not beamer:
        standard += ["fancyhdr"]
        if cls != "letter":
            standard += ["titlesec", "enumitem"]
    implicit = {"iftex", "inputenc", "fontenc", "lmodern", "fontspec", "babel", "geometry", "hyperref"}
    for package in dict.fromkeys(standard + _packages(config)):
        if package not in implicit:
            lines.append("\\usepackage{%s}\n" % package)
    if not beamer:
        lines.append("\\usepackage{hyperref}\n")
    for role, color in theme["palette"].items():
        lines.append("\\definecolor{TL%s}{HTML}{%s}\n" % (role, color))
    lines.append(r"\hypersetup{colorlinks=true,linkcolor=TLPrimary,urlcolor=TLPrimary,citecolor=TLSecondary}" + "\n")
    # Preserve ordinary LaTeX metadata for the agent's structure/read actions,
    # even though the visible title is laid out by our own cover recipe.
    lines.append("\\title{%s}\n\\author{%s}\n\\date{%s}\n" % (title, author, date))
    lines.append("\\hypersetup{pdftitle={%s},pdfauthor={%s}}\n" % (title, author))
    if theme["body"] == "sans":
        lines.append(r"\renewcommand{\familydefault}{\sfdefault}" + "\n")
    elif beamer:
        lines.append(r"\usefonttheme{serif}" + "\n")
    lines.append(_COMPONENTS)
    if beamer:
        lines.append(_sub(_BEAMER, values))
    else:
        lines.append(_sub(_PAGE_STYLE, values))
        if cls != "letter":
            lines.append(_sub(_HEADINGS, values))
            lines.append(r"\setlist{itemsep=.3em,topsep=.5em,leftmargin=*}" + "\n")
        if cls in ("report", "book"):
            lines.append(_sub(_CHAPTERS, values))
    lines.append("\n\\begin{document}\n")
    if cls == "book":
        lines.append("\\frontmatter\n")
    if beamer:
        if title:
            # Side-by-side title and artwork stay inside independent columns.
            lines += ["\\begin{frame}[plain]\n\\begin{columns}[c,onlytextwidth]\n\\begin{column}{.55\\textwidth}\n",
                      _sub(_COMPACT_TITLE, values), "\\end{column}\n\\begin{column}{.41\\textwidth}\n",
                      values["ART"] if theme["cover"] else "", "\n\\end{column}\n\\end{columns}\n\\end{frame}\n"]
        lines += ["\\begin{frame}[fragile,allowframebreaks]{%s}\n" % ("Contenido" if spanish else "Overview"),
                  content, "\n\\end{frame}\n"]
    elif cls == "letter":
        lines += ["\\signature{%s}\n\\date{%s}\n\\begin{letter}{}\n" % (author, date),
                  "\\opening{%s}\n" % ("Estimado lector:" if spanish else "Dear Reader,"),
                  content, "\n\\closing{%s}\n\\end{letter}\n" % ("Atentamente," if spanish else "Sincerely,")]
    else:
        if title:
            lines.append(_sub(_COVER if theme["cover"] and kind not in ("cv", "homework") else _COMPACT_TITLE, values))
        if template and cls in ("report", "book"):
            lines.append("\\tableofcontents\n\\clearpage\n")
        if cls == "book":
            lines.append("\\mainmatter\n")
        if template:
            intro = "Introducción" if spanish else "Introduction"
            if cls in ("report", "book"):
                lines.append("\\chapter{%s}\n" % intro)
            elif kind == "cv":
                lines.append("\\section*{%s}\n" % ("Experiencia" if spanish else "Experience"))
            elif kind == "homework":
                lines.append("\\section*{%s}\n" % ("Problemas" if spanish else "Problems"))
            else:
                lines.append("\\section{%s}\n" % intro)
        lines.append(content)
    lines.append("\n\\end{document}\n")
    return "".join(lines)
