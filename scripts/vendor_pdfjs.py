# Tlamatini Author Banner — Angela López Mendoza
"""Reproduce the offline PDF canvas assets from the pinned upstream npm archive.

Run with Python's standard library: python scripts/vendor_pdfjs.py
No npm install or runtime network connection is required by the application.
"""

import base64
import hashlib
import io
from pathlib import Path
import tarfile
from urllib.request import urlopen


VERSION = "6.3.289"
URL = f"https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-{VERSION}.tgz"
INTEGRITY = (
    "ZHjSVpDa3D6izMq8/04lvkhkATUmL9px6ChPaXc1k6nU2Mrhlg1/7F0bdUqCwUjw"
    "3NsPTfPZsMDUU6ZIcRaeQw=="
)
DESTINATION = (
    Path(__file__).resolve().parents[1]
    / "Tlamatini/agent/static/agent/vendor/pdfjs"
)
FILES = {
    "LICENSE", "build/pdf.mjs", "build/pdf.worker.mjs",
    "web/pdf_viewer.mjs", "web/pdf_viewer.css",
}
DIRECTORIES = ("cmaps/", "standard_fonts/", "wasm/", "iccs/", "web/images/")


def main():
    with urlopen(URL, timeout=60) as response:
        archive = response.read()
    actual = base64.b64encode(hashlib.sha512(archive).digest()).decode("ascii")
    if actual != INTEGRITY:
        raise RuntimeError("PDF.js archive integrity check failed")
    count = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        for member in package.getmembers():
            name = member.name.removeprefix("package/")
            if not member.isfile() or not (name in FILES or name.startswith(DIRECTORIES)):
                continue
            # Never extract arbitrary paths or symlinks from a downloaded archive.
            target = (DESTINATION / name).resolve()
            if not target.is_relative_to(DESTINATION.resolve()):
                raise RuntimeError(f"Invalid archive path: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.extractfile(member).read())
            count += 1
    (DESTINATION / "VERSION").write_text(VERSION + "\n", encoding="utf-8")
    print(f"Vendored PDF.js {VERSION}: {count} files into {DESTINATION}")


if __name__ == "__main__":
    main()
