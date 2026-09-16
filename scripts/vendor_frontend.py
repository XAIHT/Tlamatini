# Tlamatini Author Banner — Angela López Mendoza
"""Reproduce local UI dependencies from version/integrity-pinned npm archives.

Run explicitly with Python; normal builds and the app do not download these.
Upstream licenses and per-file SHA-256 receipts are retained with the assets.
"""

import base64
import fnmatch
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen


DESTINATION = Path(__file__).resolve().parents[1] / "Tlamatini/agent/static/agent/vendor/frontend"
PACKAGES = (
    ("bootstrap", "5.3.3", "https://registry.npmjs.org/bootstrap/-/bootstrap-5.3.3.tgz",
     "8HLCdWgyoMguSO9o+aH+iuZ+aht+mzW0u3HIMzVu7Srrpv7EBBxTnrFlSCskwdY1+EOFQSm7uMJhNQHkdPcmjg==",
     ("dist/css/bootstrap.min.css*", "dist/js/bootstrap.bundle.min.js*", "LICENSE")),
    ("jquery", "3.7.1", "https://registry.npmjs.org/jquery/-/jquery-3.7.1.tgz",
     "m4avr8yL8kmFN8psrbFFFmB/If14iN5o9nw/NgnnM+kybDJpRsAynV2BsfpTYrTRysYUdADVD7CkUUizgkpLfg==",
     ("dist/jquery.min.js", "dist/jquery.min.map", "LICENSE.txt")),
    ("jquery-ui", "1.13.3", "https://registry.npmjs.org/jquery-ui-dist/-/jquery-ui-dist-1.13.3.tgz",
     "qeTR3SOSQ0jgxaNXSFU6+JtxdzNUSJKgp8LCzVrVKntM25+2YBJW1Ea8B2AwjmmSHfPLy2dSlZxJQN06OfVFhg==",
     ("jquery-ui.min.js", "LICENSE.txt")),
    ("highlightjs", "11.9.0", "https://registry.npmjs.org/@highlightjs/cdn-assets/-/cdn-assets-11.9.0.tgz",
     "F1vJKVAkLwj2Uz2ik1PDc+mDbkrecLI6gcBlAxSRUjyDpMPJjeDBanT9Y2B+xpNe1MT6zSG204Ohm/+nUMCApQ==",
     ("highlight.min.js", "styles/atom-one-dark.min.css", "LICENSE",
      *(f"languages/{name}.min.js" for name in (
          "python", "java", "javascript", "c", "cpp", "css", "sql", "xml",
          "yaml", "bash", "typescript", "kotlin", "rust", "ini")))),
    ("nunito", "5.2.6", "https://registry.npmjs.org/@fontsource/nunito/-/nunito-5.2.6.tgz",
     "FjSPmzBFZ3za4w2USmCWrxDaZ1fTWowSpV9DXfs7Ll/150BI48epE6E69MtOx8GqOPimHNkVUkES22lqDw+bug==",
     ("400.css", "700.css", "files/*-400-normal.woff*", "files/*-700-normal.woff*", "LICENSE")),
)


def main():
    output = {}
    packages = []
    for name, version, url, integrity, patterns in PACKAGES:
        with urlopen(url, timeout=60) as response:
            data = response.read()
        if base64.b64encode(hashlib.sha512(data).digest()).decode("ascii") != integrity:
            raise RuntimeError(f"Upstream archive integrity mismatch: {name} {version}")
        selected = set()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                path = member.name.removeprefix("package/")
                if not member.isfile() or not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
                    continue
                target = (DESTINATION / name / path).resolve()
                if not target.is_relative_to(DESTINATION.resolve()):
                    raise RuntimeError(f"Unsafe upstream archive path: {path}")
                selected.add(path)
                output[target] = archive.extractfile(member).read()
        if any(not any(fnmatch.fnmatchcase(path, pattern) for path in selected) for pattern in patterns):
            raise RuntimeError(f"Expected files missing from pinned upstream package: {name}")
        packages.append(dict(name=name, version=version, url=url, integrity="sha512-" + integrity))
    # Validate ALL downloads before replacing any assets. No arbitrary extraction.
    manifest = {}
    for path, data in sorted(output.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest[path.relative_to(DESTINATION).as_posix()] = {
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        }
    (DESTINATION / "manifest.json").write_text(
        json.dumps(dict(schema=1, packages=packages, files=manifest), indent=2) + "\n", encoding="utf-8",
    )
    print(f"Vendored {len(output)} frontend files with licenses and SHA-256 receipts.")


if __name__ == "__main__":
    main()
