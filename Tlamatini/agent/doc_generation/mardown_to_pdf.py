from __future__ import annotations

import argparse
from pathlib import Path

from markdown import markdown
from xhtml2pdf import pisa


DEFAULT_CSS = """
@page { size: A4; margin: 18mm; }

body {
  font-family: Helvetica, Arial, sans-serif;
  line-height: 1.35;
  font-size: 11pt;
}

h1, h2, h3 { margin: 0.6em 0 0.3em; }
p { margin: 0.35em 0; }

code, pre {
  font-family: Courier, monospace;
  font-size: 9.5pt;
}

pre {
  padding: 10px;
  border: 1px solid #ddd;
  white-space: pre-wrap;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.6em 0;
}
th, td {
  border: 1px solid #ddd;
  padding: 6px;
  vertical-align: top;
}
"""


def markdown_text_to_pdf(md_text: str, output_pdf: Path, base_dir: Path | None = None, css_text: str = DEFAULT_CSS) -> None:
    """
    Convert Markdown text to a styled PDF.
    base_dir is used to resolve relative paths like images: ![](images/a.png)
    """
    # Good baseline extensions (tables + fenced code blocks):
    html_body = markdown(
        md_text,
        extensions=["fenced_code", "tables", "toc"],
        output_format="html5",
    )

    html_doc = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Document</title>
    <style>
      {css_text}
    </style>
  </head>
  <body>
    {html_body}
  </body>
</html>
"""

    with open(str(output_pdf), "w+b") as pdf_file:
        pisa_status = pisa.CreatePDF(
            html_doc,
            dest=pdf_file,
            encoding="utf-8",
        )

    if pisa_status.err:
        raise RuntimeError(f"xhtml2pdf encountered {pisa_status.err} error(s) during conversion.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert Markdown to PDF using Markdown + xhtml2pdf.")
    ap.add_argument("input", help="Path to a .md file (or '-' to read from stdin)")
    ap.add_argument("output", help="Path to output .pdf")
    ap.add_argument("--css", help="Optional path to a CSS file for styling", default=None)
    args = ap.parse_args()

    output_pdf = Path(args.output)

    if args.input == "-":
        md_text = __import__("sys").stdin.read()
        base_dir = Path.cwd()
    else:
        input_md = Path(args.input)
        md_text = input_md.read_text(encoding="utf-8")
        base_dir = input_md.parent

    css_text = DEFAULT_CSS
    if args.css:
        css_text = Path(args.css).read_text(encoding="utf-8")

    markdown_text_to_pdf(md_text, output_pdf, base_dir=base_dir, css_text=css_text)
    print(f"Wrote: {output_pdf.resolve()}")


if __name__ == "__main__":
    main()
