# -*- coding: utf-8 -*-
"""Tlamatini dependency audit — run it on ANY interpreter, it changes nothing.

    python audit_dependencies.py requirements.txt              # this interpreter
    "C:\\Tlamatini\\python\\python.exe" audit_dependencies.py requirements.txt   # carried

Why it exists (Angela, 2026-07-26): pip reported
`pyhackrf 0.2.0 requires numpy<2.0.0, but you have numpy 2.2.6`, and the honest
answer needed the FULL picture — who else constrains numpy, which of those
requirements are actually ACTIVE on this interpreter, and what drifted from
requirements.txt.

It evaluates PEP 508 environment markers, which a naive scan does not: on
Python 3.12 both `opencv-python: numpy<2.0 ; python_version < "3.9"` and
`pandas: numpy>=2.3.3 ; python_version >= "3.14"` are INACTIVE and must not be
reported as conflicts. Skipping that step turns 1 real conflict into 3 fake ones.

Read-only: installs nothing, uninstalls nothing, writes nothing.
"""
import os
import sys
from importlib import metadata

try:
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version
except Exception:                                   # noqa: BLE001
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.version import Version

FOCUS = ("numpy",)


def norm(name):
    return (name or "").lower().replace("_", "-").strip()


def main():
    print("=" * 100)
    print("INTERPRETER : %s" % sys.executable)
    print("VERSION     : %s" % sys.version.split()[0])
    print("EXISTS      : %s" % os.path.isfile(sys.executable))
    print("=" * 100)

    dists = {}
    for d in metadata.distributions():
        try:
            nm = norm(d.metadata["Name"])
            if nm:
                dists[nm] = d
        except Exception:                           # noqa: BLE001
            continue
    print("installed distributions: %d" % len(dists))

    installed = {}
    for nm, d in dists.items():
        try:
            installed[nm] = d.version
        except Exception:                           # noqa: BLE001
            pass

    for focus in FOCUS:
        have = installed.get(focus)
        print()
        print("### WHO CONSTRAINS %r  (installed: %s) ###" % (focus, have or "NOT INSTALLED"))
        constraints = []
        for nm, d in sorted(dists.items()):
            for raw in (d.requires or []):
                try:
                    req = Requirement(raw)
                except Exception:                   # noqa: BLE001
                    continue
                if norm(req.name) != focus:
                    continue
                # Skip optional extras AND markers that are FALSE for THIS
                # interpreter. Without this the audit lies: opencv-python's
                # `numpy<2.0 ; python_version < "3.9"` and pandas'
                # `numpy>=2.3.3 ; python_version >= "3.14"` look like conflicts
                # on 3.12 when neither requirement is active at all.
                marker = str(req.marker) if req.marker else ""
                if "extra ==" in marker:
                    continue
                if req.marker is not None:
                    try:
                        if not req.marker.evaluate():
                            continue
                    except Exception:               # noqa: BLE001
                        pass
                spec = str(req.specifier) or "(any)"
                ok = True
                if have and req.specifier:
                    try:
                        ok = Version(have) in req.specifier
                    except Exception:               # noqa: BLE001
                        ok = True
                constraints.append((nm, installed.get(nm, "?"), spec, ok, marker))
        if not constraints:
            print("  (nothing constrains it)")
        for nm, ver, spec, ok, marker in constraints:
            print("  %-26s %-14s requires %-22s %s%s"
                  % (nm, ver, spec, "OK" if ok else "*** CONFLICT ***",
                     ("   [marker: %s]" % marker) if marker else ""))

        # feasible intersection across ALL constraints
        combined = SpecifierSet("")
        for _, _, spec, _, _ in constraints:
            if spec != "(any)":
                try:
                    combined &= SpecifierSet(spec)
                except Exception:                   # noqa: BLE001
                    pass
        print("  COMBINED SPECIFIER : %s" % (str(combined) or "(any)"))
        if have:
            try:
                print("  installed %s satisfies combined: %s"
                      % (have, Version(have) in combined))
            except Exception:                       # noqa: BLE001
                pass

    # --- pip check equivalent: every unsatisfied requirement, whole env ---
    print()
    print("### BROKEN REQUIREMENTS (whole environment) ###")
    broken = 0
    for nm, d in sorted(dists.items()):
        for raw in (d.requires or []):
            try:
                req = Requirement(raw)
            except Exception:                       # noqa: BLE001
                continue
            if req.marker and "extra ==" in str(req.marker):
                continue
            if req.marker is not None:
                try:
                    if not req.marker.evaluate():
                        continue          # requirement is inactive on this interpreter
                except Exception:                   # noqa: BLE001
                    pass
            dep = norm(req.name)
            if dep not in installed:
                continue
            if req.specifier and Version(installed[dep]) not in req.specifier:
                broken += 1
                print("  %-26s %-12s requires %s%-18s but %s is installed"
                      % (nm, d.version, dep, str(req.specifier), installed[dep]))
    if not broken:
        print("  none")
    print("  total broken: %d" % broken)

    # --- requirements.txt drift ---
    reqfile = sys.argv[1] if len(sys.argv) > 1 else ""
    if reqfile and os.path.isfile(reqfile):
        print()
        print("### requirements.txt DRIFT (%s) ###" % reqfile)
        missing, mismatch, okc = [], [], 0
        with open(reqfile, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if not line or line.startswith("-"):
                    continue
                try:
                    req = Requirement(line)
                except Exception:                   # noqa: BLE001
                    continue
                dep = norm(req.name)
                if dep not in installed:
                    missing.append((dep, str(req.specifier) or "(any)"))
                    continue
                if req.specifier and Version(installed[dep]) not in req.specifier:
                    mismatch.append((dep, str(req.specifier), installed[dep]))
                else:
                    okc += 1
        print("  satisfied: %d" % okc)
        print("  MISSING  : %d" % len(missing))
        for dep, spec in missing:
            print("     %-26s pinned %s" % (dep, spec))
        print("  MISMATCH : %d" % len(mismatch))
        for dep, spec, got in mismatch:
            print("     %-26s pinned %-18s installed %s" % (dep, spec, got))


if __name__ == "__main__":
    main()
