# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza   ·   @angelahack1
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""1000 data-driven tests for the Discoverer agent, runnable in the Tlamatini dev
(`python manage.py test agent.test_discoverer_thousand`).

Each of the 1000 counted tests is a DISTINCT input -> expected assertion over the
Discoverer agent's pure logic — no network, deterministic, fast:

  * argv builders for every tool (subfinder/httpx/naabu/katana/nuclei) + their JSON flag
  * the cvemap -> vulnx migration: `vulnx search` (severity x limit) and `vulnx id <CVE>`
  * the Go-toolchain default lives UNDER Tlamatini (explicit go_dir wins)
  * placeholder-safe secrets (`_real_secret`)
  * findings-count parsing (`_findings_count`)
"""
import importlib.util
import logging
import os
import unittest


def _load_discoverer():
    path = os.path.join(os.path.dirname(__file__), "agents", "discoverer", "discoverer.py")
    spec = importlib.util.spec_from_file_location("disc_thousand_mod", path)
    mod = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    before = list(root.handlers)
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
    return mod


M = _load_discoverer()

_JSON_FLAG = {"subfinder": "-oJ", "httpx": "-json", "naabu": "-json",
              "katana": "-jsonl", "nuclei": "-jsonl"}
_SEVS = ["critical", "high", "medium", "low", "info", "unknown",
         "critical,high", "high,medium", "critical,high,medium", "critical,medium",
         "high,low", "medium,low", "critical,high,medium,low", "critical,info",
         "high,info", "low,info"]


def _argv_case(tool, flag, cfg):
    def t(self):
        a = M._build_argv(tool, tool + ".exe", dict(cfg), "o.json")
        self.assertEqual(a[0], tool + ".exe")
        self.assertIn(flag, a)
    return t


def _cvemap_search_case(sev, lim, cfg):
    def t(self):
        a = M._build_argv("cvemap", "vulnx.exe", dict(cfg), "o.json")
        self.assertIn("search", a)
        self.assertEqual(a[a.index("--severity") + 1], sev)
        self.assertEqual(a[a.index("--limit") + 1], str(lim))
        self.assertIn("-j", a)
    return t


def _cvemap_id_case(cid):
    def t(self):
        a = M._build_argv("cvemap", "vulnx.exe", {"cvemap_id": cid, "json_output": True}, "o.json")
        self.assertEqual(a[a.index("id") + 1], cid)
        self.assertNotIn("search", a)
    return t


def _go_dir_case(gd):
    def t(self):
        # Explicit go_dir always wins; the empty default resolves UNDER app_root (Tlamatini).
        self.assertEqual(M._default_go_dir({"go_dir": gd}), gd)
        self.assertEqual(os.path.normpath(M._default_go_dir({})),
                         os.path.normpath(os.path.join(M._app_root(), "Go")))
    return t


def _secret_case(val, exp):
    def t(self):
        self.assertEqual(M._real_secret(val), exp)
    return t


def _findings_case(n, stdout):
    def t(self):
        self.assertEqual(M._findings_count("", stdout), n)
    return t


def _build_cases():
    cases = []
    # A) exe-first + per-tool JSON flag — 5 tools x 40 = 200
    for tool, flag in _JSON_FLAG.items():
        for i in range(40):
            cases.append((f"argv_{tool}_{i:02d}",
                          _argv_case(tool, flag, {"target": f"host{i}.example.com", "json_output": True})))
    # B) cvemap -> vulnx search: severity x limit — 16 x 25 = 400
    for sev in _SEVS:
        for lim in range(1, 26):
            cases.append((f"cvemap_search_{sev.replace(',', '_')}_{lim:02d}",
                          _cvemap_search_case(sev, lim,
                                              {"cvemap_severity": sev, "cvemap_limit": lim, "json_output": True})))
    # C) cvemap -> vulnx id — 100
    for i in range(100):
        cases.append((f"cvemap_id_{i:03d}", _cvemap_id_case(f"CVE-2026-{10000 + i}")))
    # D) Go toolchain default under Tlamatini (explicit wins) — 100
    for i in range(100):
        cases.append((f"go_dir_{i:03d}", _go_dir_case(os.path.join("Z:\\", f"go{i}"))))
    # E) placeholder-safe secrets — 100
    for i in range(100):
        if i % 3 == 0:
            val, exp = f"<KEY_{i} goes here>", ""
        elif i % 3 == 1:
            val, exp = f"realkey{i}", f"realkey{i}"
        else:
            val, exp = "", ""
        cases.append((f"real_secret_{i:03d}", _secret_case(val, exp)))
    # F) findings-count parsing — 100
    for n in range(100):
        cases.append((f"findings_count_{n:03d}", _findings_case(n, "\n".join(f"line{j}" for j in range(n)))))
    return cases[:1000]


class DiscovererThousandTests(unittest.TestCase):
    """1000 deterministic assertions over the Discoverer agent's pure logic."""


for _idx, (_label, _fn) in enumerate(_build_cases()):
    setattr(DiscovererThousandTests, f"test_{_idx:04d}_{_label}", _fn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
