# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Input / output contract validation for skills.

Skills declare their inputs/outputs in the frontmatter:

    inputs:
      - name: file_path
        type: string
        required: true
      - name: max_lines
        type: number
        required: false
        default: 100

    outputs:
      - name: diff_summary
        type: string
        required: true

The validator coerces & checks values; on failure it returns a
ValidationResult with `ok=False` and a list of error strings, never
raising. The harness then surfaces those errors as the skill's failure
reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ValidationResult:
    ok: bool
    coerced: Dict[str, Any]
    errors: List[str]


_PRIMITIVE_PY_TYPES: Dict[str, tuple] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "object": (dict,),
}


def _coerce_one(name: str, declared: Dict[str, Any], value: Any
                ) -> Tuple[Any, Optional[str]]:
    declared_type = (declared.get("type") or "string").lower()

    # Enum
    if declared_type == "enum":
        choices = declared.get("values") or declared.get("choices") or []
        if value in choices:
            return value, None
        return value, f"{name}: value '{value}' not in enum {choices!r}"

    # Array
    if declared_type.startswith("array"):
        if not isinstance(value, list):
            return value, f"{name}: expected array, got {type(value).__name__}"
        return value, None

    # Primitive
    py_types = _PRIMITIVE_PY_TYPES.get(declared_type)
    if py_types is None:
        # Unknown type → accept as-is.
        return value, None
    if isinstance(value, py_types):
        return value, None
    # Best-effort coercion for string→number etc.
    try:
        if py_types == (str,):
            return str(value), None
        if py_types == (int, float):
            if isinstance(value, str):
                return float(value), None
        if py_types == (int,):
            return int(value), None
        if py_types == (bool,):
            if isinstance(value, str):
                return value.lower() in ("1", "true", "yes", "y"), None
    except Exception:
        pass
    return value, f"{name}: expected {declared_type}, got {type(value).__name__}"


def validate_inputs(input_decls: List[Dict[str, Any]],
                    args: Dict[str, Any]) -> ValidationResult:
    errors: List[str] = []
    coerced: Dict[str, Any] = {}
    for decl in input_decls:
        name = decl.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"input_decl missing 'name': {decl!r}")
            continue
        required = bool(decl.get("required", False))
        if name not in args:
            if required:
                errors.append(f"{name}: required input missing")
            elif "default" in decl:
                coerced[name] = decl["default"]
            continue
        value, err = _coerce_one(name, decl, args[name])
        if err:
            errors.append(err)
        coerced[name] = value
    # Allow extra keys through unchanged — skills may use them as opaque hints.
    for k, v in args.items():
        if k not in coerced:
            coerced[k] = v
    return ValidationResult(ok=not errors, coerced=coerced, errors=errors)


def validate_outputs(output_decls: List[Dict[str, Any]],
                     output: Any) -> ValidationResult:
    if not isinstance(output, dict):
        return ValidationResult(False, {}, [f"output must be an object, got {type(output).__name__}"])
    errors: List[str] = []
    coerced: Dict[str, Any] = {}
    for decl in output_decls:
        name = decl.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"output_decl missing 'name': {decl!r}")
            continue
        required = bool(decl.get("required", False))
        if name not in output:
            if required:
                errors.append(f"{name}: required output missing")
            continue
        value, err = _coerce_one(name, decl, output[name])
        if err:
            errors.append(err)
        coerced[name] = value
    for k, v in output.items():
        if k not in coerced:
            coerced[k] = v
    return ValidationResult(ok=not errors, coerced=coerced, errors=errors)
