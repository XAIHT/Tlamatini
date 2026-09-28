# Tlamatini - Created by Angela Lopez Mendoza - @angelahack1
# Tlamatini Author Banner - do not remove
"""Static repository-wide Python dependency coverage; imports no application code.

Run ONLY in a verified visible foreground console, kept open after completion:
    python scripts/check_requirements_coverage.py --report Temp/dependency-audit/coverage.json
Includes tracked and non-ignored new source, hidden skill harnesses, optional
imports, literal dynamic imports, generated Python and explicit build inventories.
JavaScript/native SDK dependencies belong to their own runtimes, not pip.
"""
import argparse
import ast
from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess
import sys
import tokenize

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "PIL": "pillow", "PyInstaller": "pyinstaller", "pyi_splash": "pyinstaller",
    "bs4": "beautifulsoup4", "cv2": "opencv-python", "docx": "python-docx",
    "dotenv": "python-dotenv", "fitz": "pymupdf", "fontTools": "fonttools",
    "google.protobuf": "protobuf", "grpc": "grpcio", "grpc_tools": "grpcio-tools",
    "odf": "odfpy", "pptx": "python-pptx", "serial": "pyserial", "yaml": "pyyaml",
    "whisper": "openai-whisper", "faiss": "faiss-cpu", "sklearn": "scikit-learn",
    "git": "GitPython", "pythoncom": "pywin32", "pywintypes": "pywin32",
}
HOST_MODULES = {"bpy": "Blender's embedded Python", "unreal": "Unreal Editor's embedded Python"}
MANAGED_MODULES = {"esphome": "requirements-esphome.txt"}
IMPORT_ROOTS = (
    "", "Tlamatini", "Tlamatini/agent", "Tlamatini/agent/services", "scripts",
    "Tlamatini/agent/agents/pdfer", "Tlamatini/agent/agents/pptxer",
    "Tlamatini/agent/agents/latexer",
    ".claude/skills/tlamatini-daily-chat-test/harness",
)
# Computed local imports and generic package-location helpers reviewed explicitly.
# New unresolved expressions fail, rather than silently disappearing from coverage.
REVIEWED_DYNAMIC = {
    ("build.py", "importlib.util.find_spec(import_name)"):
        "find_package_data_paths callers use literal import_name keywords, scanned below",
    ("build.py", "importlib.util.find_spec(package_name)"):
        "find_package_code_path callers use literal package names, scanned below",
    ("scripts/update_flow_catalog.py", "importlib.import_module(package.__name__ + '.flow_knowledge')"):
        "local services package under a temporary import namespace",
    ("Tlamatini/agent/test_flow_knowledge.py", "importlib.import_module(UPDATER.package.__name__ + '.flow_spec')"):
        "local services test namespace",
    ("Tlamatini/agent/test_flow_knowledge.py", "importlib.import_module(UPDATER.package.__name__ + '.flow_compiler')"):
        "local services test namespace",
    ("Tlamatini/agent/test_flow_knowledge.py", "importlib.import_module(UPDATER.package.__name__ + '.agent_contracts')"):
        "local services test namespace",
    ("Tlamatini/agent/test_latexer_suite.py", "__import__(__name__)"):
        "test imports itself",
}
INVENTORY_NAMES = {"hiddenimports", "_AGENT_RUNTIME_IMPORTS", "_CARRIED_PYTHON_REQUIRED_IMPORTS",
                   "_FROZEN_PDF_MODULES", "_FROZEN_PROMPT_FLOW_PANEL_MODULES",
                   "_FROZEN_REQUIRED_AGENT_MODULES", "INSTALLED_APPS", "MIDDLEWARE"}


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def source_files(root):
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root, check=True, capture_output=True)
    return sorted({Path(p) for p in result.stdout.decode("utf-8").split("\0")
                   if p.endswith((".py", ".pyw")) and (root / p).is_file()})


def requirements(root, filename="requirements.txt"):
    names = {}
    for line in (root / filename).read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\s|[<>=!~\[;@]|$)", line.strip())
        if match:
            key = canonical(match[1])
            if key in names:
                raise ValueError("Duplicate requirement: " + key)
            names[key] = line
    return names


def literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def string_items(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (tuple, list)):
        for child in value:
            yield from string_items(child)


def loop_values(node, name, parents):
    parent = parents.get(node)
    while parent:
        if isinstance(parent, ast.For):
            targets = ([parent.target.id] if isinstance(parent.target, ast.Name) else
                       [n.id for n in parent.target.elts if isinstance(n, ast.Name)]
                       if isinstance(parent.target, (ast.Tuple, ast.List)) else [])
            values = literal(parent.iter)
            if name in targets and isinstance(values, (tuple, list)):
                index = targets.index(name)
                return [v if len(targets) == 1 else v[index] for v in values]
        parent = parents.get(parent)
    return []


def extract_references(source, path):
    tree = ast.parse(source, filename=path.as_posix())
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    refs, unresolved = [], []
    is_test = path.stem.startswith("test") or any(p.lower() in {"tests", "tests_e2e"} for p in path.parts)

    def add(module, node, kind):
        if isinstance(module, str) and re.fullmatch(r"[A-Za-z_]\w*(?:\.\w+)*", module):
            refs.append({"module": module, "file": path.as_posix(), "line": node.lineno, "kind": kind})

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name, node, "import")
        elif isinstance(node, ast.ImportFrom) and not node.level:
            add(node.module, node, "from")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name in {"__import__", "import_module", "find_spec"}:
                value = literal(node.args[0]) if node.args else None
                values = [value] if isinstance(value, str) else (
                    loop_values(node, node.args[0].id, parents)
                    if node.args and isinstance(node.args[0], ast.Name) else [])
                if values:
                    for value in values:
                        add(value, node, "dynamic")
                else:
                    expression = ast.unparse(node)
                    key = (path.as_posix(), expression)
                    if key not in REVIEWED_DYNAMIC:
                        unresolved.append({"file": path.as_posix(), "line": node.lineno, "expression": expression})
            elif name in {"collect_dynamic_libs", "collect_submodules", "collect_data_files", "find_package_code_path"}:
                if node.args:
                    add(literal(node.args[0]), node, "build")
            elif name == "find_package_data_paths":
                for keyword in node.keywords:
                    if keyword.arg == "import_name":
                        add(literal(keyword.value), node, "build")
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id in INVENTORY_NAMES for t in targets):
                for value in string_items(literal(node.value)):
                    add(value, node, "inventory")
        elif isinstance(node, (ast.List, ast.Tuple)):
            for index, element in enumerate(node.elts):
                value = literal(element)
                if not isinstance(value, str):
                    continue
                if value.startswith("--hidden-import="):
                    add(value.split("=", 1)[1], element, "build")
                # Test command arrays describe fake external-MCP launch shapes.
                # Real Python imports in every test file are still scanned above.
                if value == "-m" and is_test:
                    continue
                if value in {"--collect-all", "-m"} and index + 1 < len(node.elts):
                    add(literal(node.elts[index + 1]), element, "build")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and not is_test:
            parent = parents.get(node)
            # Docstrings are documentation, not executed imports. Test strings
            # are fixtures/assertions; their real imports above still count.
            if isinstance(parent, ast.Expr):
                container = parents.get(parent)
                if getattr(container, "body", [None])[0] is parent:
                    continue
            if "\n" not in node.value and ";" not in node.value:
                continue
            for line in node.value.splitlines():
                line = line.strip()
                if not line.startswith(("import ", "from ")):
                    continue
                try:
                    statements = ast.parse(line).body
                except SyntaxError:
                    continue
                for statement in statements:
                    if isinstance(statement, ast.Import):
                        for alias in statement.names:
                            add(alias.name, node, "generated")
                    elif isinstance(statement, ast.ImportFrom) and not statement.level:
                        add(statement.module, node, "generated")
    return refs, unresolved


def classify(reference, root):
    module = reference["module"]
    name = module.split(".")[0]
    if name in sys.stdlib_module_names:
        return "stdlib", name
    if name in HOST_MODULES:
        return "host", HOST_MODULES[name]
    if name in MANAGED_MODULES:
        return "managed", MANAGED_MODULES[name]
    path = Path(reference["file"])
    for parent in [path.parent, *path.parents, *(Path(p) for p in IMPORT_ROOTS)]:
        candidate = root / parent / name
        if candidate.with_suffix(".py").is_file() or (
            candidate.is_dir() and any(candidate.glob("*.py"))
        ):
            return "local", candidate.relative_to(root).as_posix()
    for prefix in sorted(ALIASES, key=len, reverse=True):
        if module == prefix or module.startswith(prefix + "."):
            return "pip", canonical(ALIASES[prefix])
    if name.startswith("win32"):
        return "pip", "pywin32"
    return "pip", canonical(name)


def audit(root, paths=None):
    paths = source_files(root) if paths is None else paths
    declared = requirements(root)
    imports = defaultdict(list)
    host = []
    managed = []
    syntax_errors = []
    unresolved = []
    for path in paths:
        try:
            with tokenize.open(root / path) as stream:
                refs, dynamic = extract_references(stream.read(), path)
        except (SyntaxError, UnicodeError) as exc:
            syntax_errors.append({"file": str(path), "error": str(exc)})
            continue
        unresolved.extend(dynamic)
        for reference in refs:
            kind, distribution = classify(reference, root)
            if kind == "pip" and reference not in imports[distribution]:
                imports[distribution].append(reference)
            elif kind == "host" and reference not in host:
                host.append({**reference, "provided_by": distribution})
            elif kind == "managed":
                module = canonical(reference["module"].split(".")[0])
                if not (root / distribution).is_file() or module not in requirements(root, distribution):
                    imports[module].append(reference)
                else:
                    managed.append({**reference, "manifest": distribution})
    missing = {name: refs for name, refs in imports.items() if name not in declared}
    agents = root / "Tlamatini/agent/agents"
    count = sum((p / (p.name + ".py")).is_file() for p in agents.iterdir() if p.is_dir()) if agents.exists() else 0
    return {"python_files": len(paths), "runnable_agents": count,
            "source_files": [p.as_posix() for p in paths],
            "requirements": dict(sorted(declared.items())),
            "distributions": dict(sorted(imports.items())), "host_modules": host,
            "managed_runtimes": managed,
            "missing": missing, "syntax_errors": syntax_errors,
            "unreviewed_dynamic_imports": unresolved}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    options = parser.parse_args()
    report = audit(ROOT)
    if options.report:
        options.report.parent.mkdir(parents=True, exist_ok=True)
        options.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Scanned {report['python_files']} Python files across {report['runnable_agents']} runnable agents.")
    print(f"Referenced pip distributions: {len(report['distributions'])}; declared: {len(report['requirements'])}")
    for key in ("missing", "syntax_errors", "unreviewed_dynamic_imports"):
        print(key + ": " + json.dumps(report[key], ensure_ascii=True))
    return int(any(report[key] for key in ("missing", "syntax_errors", "unreviewed_dynamic_imports")))


if __name__ == "__main__":
    raise SystemExit(main())
