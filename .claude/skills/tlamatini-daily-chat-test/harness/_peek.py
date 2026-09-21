import sys, re
p = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 14
raw = open(p, "rb").read()
txt = None
for bom, c in ((b"\xff\xfe\x00\x00","utf-32-le"),(b"\xef\xbb\xbf","utf-8-sig"),(b"\xff\xfe","utf-16-le"),(b"\xfe\xff","utf-16-be")):
    if raw.startswith(bom):
        txt = raw.decode(c, "replace"); break
if txt is None:
    txt = raw.decode("utf-8", "replace")
txt = txt.replace("\ufeff", "")
lines = [l.rstrip() for l in txt.splitlines() if l.strip()]
rows = [l for l in lines if re.match(r"^\s*\[\s*\d+/", l)]
bad = [l for l in lines if ("!!" in l or "Traceback" in l or "Error" in l or "ERROR" in l)]
out = []
out.append("lines=%d  prompts_done=%d  problems=%d" % (len(lines), len(rows), len(bad)))
for l in lines[-n:]:
    out.append("  " + l)
if bad:
    out.append("-- problems --")
    for l in bad[:5]:
        out.append("  " + l)
sys.stdout.buffer.write(("\n".join(out) + "\n").encode("utf-8", "replace"))
