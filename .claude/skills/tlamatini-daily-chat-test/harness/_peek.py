import re
import sys

p = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 14
raw = open(p, "rb").read()
txt = None
for bom, c in ((b"\xff\xfe\x00\x00", "utf-32-le"), (b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
    if raw.startswith(bom):
        txt = raw.decode(c, "replace")
        break
if txt is None:
    txt = raw.decode("utf-8", "replace")
txt = txt.replace("\ufeff", "")
lines = [line.rstrip() for line in txt.splitlines() if line.strip()]
rows = [line for line in lines if re.match(r"^\s*\[\s*\d+/", line)]
bad = [line for line in lines if ("!!" in line or "Traceback" in line or "Error" in line or "ERROR" in line)]
out = []
out.append("lines=%d  prompts_done=%d  problems=%d" % (len(lines), len(rows), len(bad)))
for line in lines[-n:]:
    out.append("  " + line)
if bad:
    out.append("-- problems --")
    for line in bad[:5]:
        out.append("  " + line)
sys.stdout.buffer.write(("\n".join(out) + "\n").encode("utf-8", "replace"))
