#!/usr/bin/env python3
"""K138 substrate projection — module/symbol docs and invariant checks."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PKG_ROOT = ROOT / "xsp_killer"


def resolve_module_path(dotted: str) -> Path:
    spec = importlib.util.find_spec(dotted)
    if spec and spec.origin and spec.origin not in ("namespace", "built-in"):
        return Path(spec.origin)
    parts = dotted.split(".")
    if parts[0] != "xsp_killer":
        raise FileNotFoundError(f"cannot resolve module: {dotted}")
    rel = Path(*parts[1:]) if len(parts) > 1 else Path("__init__.py")
    candidate = PKG_ROOT / rel
    if candidate.is_dir():
        candidate = candidate / "__init__.py"
    elif candidate.suffix != ".py":
        candidate = candidate.with_suffix(".py")
    if not candidate.is_file():
        raise FileNotFoundError(f"module not found: {dotted}")
    return candidate


def parse_module_ast(path: Path) -> ast.Module:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if not isinstance(tree, ast.Module):
        raise TypeError(f"expected module AST in {path}")
    return tree


def module_docstring(tree: ast.Module) -> str | None:
    return ast.get_docstring(tree)


def extract_invariants(docstring: str | None) -> str | None:
    if not docstring or "Invariants:" not in docstring:
        return None
    rest = docstring.split("Invariants:", 1)[1]
    text = rest.strip()
    return text or None


def first_line_summary(docstring: str | None) -> str | None:
    if not docstring:
        return None
    for line in docstring.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def has_invariants_line(docstring: str | None) -> bool:
    if not docstring:
        return False
    return any(line.strip().startswith("Invariants:") for line in docstring.splitlines())


def top_level_symbols(tree: ast.Module) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(
                {
                    "kind": "function",
                    "name": node.name,
                    "summary": first_line_summary(ast.get_docstring(node)),
                }
            )
        elif isinstance(node, ast.ClassDef):
            out.append(
                {
                    "kind": "class",
                    "name": node.name,
                    "summary": first_line_summary(ast.get_docstring(node)),
                }
            )
    return out


def module_bundle(dotted: str) -> dict[str, Any]:
    path = resolve_module_path(dotted)
    tree = parse_module_ast(path)
    doc = module_docstring(tree)
    return {
        "module": dotted,
        "path": str(path),
        "docstring": doc,
        "invariants": extract_invariants(doc),
        "symbols": top_level_symbols(tree),
    }


def symbol_bundle(dotted: str, name: str) -> dict[str, Any]:
    path = resolve_module_path(dotted)
    tree = parse_module_ast(path)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name != name:
                continue
            doc = ast.get_docstring(node)
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            return {
                "module": dotted,
                "name": name,
                "kind": kind,
                "path": str(path),
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "docstring": doc,
                "invariants": extract_invariants(doc),
            }
    raise KeyError(f"symbol not found: {name} in {dotted}")


def check_invariants(modules: list[str]) -> int:
    rc = 0
    for dotted in modules:
        path = resolve_module_path(dotted)
        doc = module_docstring(parse_module_ast(path))
        if has_invariants_line(doc):
            print(f"ok {dotted}")
        else:
            print(f"missing Invariants: {dotted}", file=sys.stderr)
            rc = 1
    return rc


def main(argv: list[str] | None = None) -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    parser = argparse.ArgumentParser(description="K138 substrate projection for xsp_killer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_mod = sub.add_parser("module", help="JSON bundle for a module")
    p_mod.add_argument("dotted_path")

    p_sym = sub.add_parser("symbol", help="JSON for one top-level symbol")
    p_sym.add_argument("dotted_path")
    p_sym.add_argument("name")

    p_chk = sub.add_parser("check-invariants", help="Require Invariants: in module docstrings")
    p_chk.add_argument("dotted_path", nargs="+")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "module":
            payload = module_bundle(args.dotted_path)
        elif args.cmd == "symbol":
            payload = symbol_bundle(args.dotted_path, args.name)
        else:
            return check_invariants(args.dotted_path)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (FileNotFoundError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
