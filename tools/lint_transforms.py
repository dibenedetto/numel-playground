#!/usr/bin/env python
"""Lint workflow `transform_flow` scripts for split-namespace `exec` hazards.

The Numel engine runs every transform_flow script via:

    exec(script, None, local_vars)         # app/nodes.py:295

This puts top-level defs and constants into `local_vars`, but any function /
comprehension / lambda defined inside the script gets `__globals__` pointing
at the engine module, so a lookup of *another* top-level script name from
within an inner scope raises NameError at runtime.

This linter scans every `transform_flow` script in workflow JSON files and
reports four classes of hazards:

  1. RECURSIVE-DEF       — a function references its own name.
  2. HELPER-CALL         — a function references another top-level function.
  3. CAPTURE             — a function references a top-level constant or
                           imported name.
  4. COMPREHENSION-LEAK  — a comprehension/genexp/lambda body references a
                           top-level name (same scope rules as a function).

Usage
-----

    python tools/lint_transforms.py [paths…]

When no paths are given, defaults to all `examples/*.json`. Exit code is 0
when there are no findings, 1 otherwise.

Each finding cites the workflow file, the node index + name, the script
line/column, the offending name, and the kind. False positives are possible
(eager-eval defaults that we miss) but the four patterns above were enough
to catch every real bug observed during Phase 3 testing.

See `docs/transform-flow-scripts.md` for the underlying mechanism and
recommended workarounds.
"""

from __future__ import annotations

import ast
import builtins
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

_INNER_SCOPE_TYPES: Tuple[type, ...] = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)

_BUILTIN_NAMES: Set[str] = set(dir(builtins))


def _target_names(node: ast.AST) -> Set[str]:
    """Collect names bound by an assignment or for-loop target."""
    out: Set[str] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Starred):
            stack.append(n.value)
        elif isinstance(n, (ast.Tuple, ast.List)):
            stack.extend(n.elts)
    return out


def _top_level_bindings(tree: ast.Module) -> Set[str]:
    """Names introduced at the module top level (visible to top-level code,
    NOT visible from inside an inner scope under split-namespace exec)."""
    names: Set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                names |= _target_names(tgt)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
        elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(stmt, ast.ImportFrom):
            for alias in stmt.names:
                names.add(alias.asname or alias.name)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(stmt.name)
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            names |= _target_names(stmt.target)
        elif isinstance(stmt, (ast.While, ast.If, ast.Try, ast.With, ast.AsyncWith)):
            # Statements nested inside compound statements still count as
            # top-level for our purposes (they share the script's namespace).
            sub = ast.Module(body=stmt.body, type_ignores=[])
            names |= _top_level_bindings(sub)
            for handler in getattr(stmt, "handlers", []):
                if isinstance(handler, ast.ExceptHandler):
                    if handler.name:
                        names.add(handler.name)
                    sub = ast.Module(body=handler.body, type_ignores=[])
                    names |= _top_level_bindings(sub)
            for orelse in (getattr(stmt, "orelse", []), getattr(stmt, "finalbody", [])):
                if orelse:
                    sub = ast.Module(body=orelse, type_ignores=[])
                    names |= _top_level_bindings(sub)
    return names


def _function_locals(node: ast.AST) -> Set[str]:
    """Names bound inside a function/lambda body — parameters + local
    assignments + nested defs. Used to filter out reads that resolve to a
    function-local rather than a top-level name."""
    locals_: Set[str] = set()

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        args = node.args
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            locals_.add(arg.arg)
        if args.vararg:  locals_.add(args.vararg.arg)
        if args.kwarg:   locals_.add(args.kwarg.arg)

        body = node.body if isinstance(node.body, list) else [node.body]
    else:
        body = list(ast.iter_child_nodes(node))

    # Walk the body looking for local bindings (assignments / defs / imports),
    # but stop at nested scopes (their bindings are theirs, not ours).
    stack: List[ast.AST] = list(body)
    while stack:
        cur = stack.pop()
        if isinstance(cur, _INNER_SCOPE_TYPES):
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                locals_.add(cur.name)
            continue
        if isinstance(cur, ast.Assign):
            for tgt in cur.targets:
                locals_ |= _target_names(tgt)
        elif isinstance(cur, ast.AnnAssign) and isinstance(cur.target, ast.Name):
            locals_.add(cur.target.id)
        elif isinstance(cur, ast.AugAssign) and isinstance(cur.target, ast.Name):
            locals_.add(cur.target.id)
        elif isinstance(cur, ast.NamedExpr) and isinstance(cur.target, ast.Name):
            locals_.add(cur.target.id)
        elif isinstance(cur, (ast.For, ast.AsyncFor)):
            locals_ |= _target_names(cur.target)
        elif isinstance(cur, ast.Import):
            for alias in cur.names:
                locals_.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(cur, ast.ImportFrom):
            for alias in cur.names:
                locals_.add(alias.asname or alias.name)
        elif isinstance(cur, ast.With):
            for item in cur.items:
                if item.optional_vars:
                    locals_ |= _target_names(item.optional_vars)
        elif isinstance(cur, ast.ExceptHandler) and cur.name:
            locals_.add(cur.name)
        stack.extend(ast.iter_child_nodes(cur))

    return locals_


def _comprehension_locals(node: ast.AST) -> Set[str]:
    """Names bound inside a comprehension — its iter variables."""
    locals_: Set[str] = set()
    for gen in node.generators:
        locals_ |= _target_names(gen.target)
    return locals_


def _scope_loads(scope: ast.AST, *, kind: str) -> Iterable[Tuple[ast.Name, ast.AST]]:
    """Yield Name(Load) reads inside `scope` that are NOT inside a deeper
    nested scope (those are processed separately as their own scope).

    For comprehensions, the FIRST generator's `iter` is intentionally NOT
    included because Python evaluates it eagerly in the enclosing scope, so
    references there are safe under split-namespace exec.
    """
    if kind == "function":
        body_nodes: List[ast.AST] = scope.body if isinstance(scope.body, list) else [scope.body]
        roots = list(body_nodes)
    else:  # comprehension
        roots = []
        if isinstance(scope, ast.DictComp):
            roots.extend([scope.key, scope.value])
        else:
            roots.append(scope.elt)
        for i, gen in enumerate(scope.generators):
            if i > 0:
                roots.append(gen.iter)
            roots.extend(gen.ifs)

    stack: List[ast.AST] = list(roots)
    while stack:
        cur = stack.pop()
        if cur is scope:
            continue
        if isinstance(cur, _INNER_SCOPE_TYPES) and cur is not scope:
            # Don't descend into a deeper inner scope; it'll be analyzed on
            # its own.
            continue
        if isinstance(cur, ast.Name) and isinstance(cur.ctx, ast.Load):
            yield cur, scope
            continue
        stack.extend(ast.iter_child_nodes(cur))


# ---------------------------------------------------------------------------
# Linter core
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    file: str
    node_index: int
    node_name: str
    line: int
    col: int
    name: str
    kind: str               # "RECURSIVE-DEF" / "HELPER-CALL" / "CAPTURE" / "COMPREHENSION-LEAK" / "SYNTAX"
    detail: str

    def format(self) -> str:
        loc = f"{self.file}:[{self.node_index}] {self.node_name!r}"
        return f"{loc}  L{self.line}:C{self.col}  {self.kind:<20s} {self.name!r}  ({self.detail})"


def _lint_script(
    script: str,
    file: str,
    node_index: int,
    node_name: str,
) -> List[Finding]:
    findings: List[Finding] = []
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        findings.append(Finding(file, node_index, node_name, exc.lineno or 0,
                                exc.offset or 0, "<syntax>", "SYNTAX", str(exc)))
        return findings

    top_level   = _top_level_bindings(tree)
    top_level_fns = {
        s.name for s in tree.body
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    # Walk every scope-defining node (not just top level) so nested scopes
    # are analyzed too.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            locals_  = _function_locals(node)
            self_name = getattr(node, "name", None)
            for ref, _ in _scope_loads(node, kind="function"):
                name = ref.id
                if name in locals_ or name in _BUILTIN_NAMES:
                    continue
                if name not in top_level:
                    continue
                if name == self_name:
                    kind   = "RECURSIVE-DEF"
                    detail = f"function {self_name!r} references its own name"
                elif name in top_level_fns:
                    kind   = "HELPER-CALL"
                    detail = f"calls top-level function {name!r}"
                else:
                    kind   = "CAPTURE"
                    detail = f"reads top-level binding {name!r}"
                findings.append(Finding(file, node_index, node_name,
                                        ref.lineno, ref.col_offset, name, kind, detail))

        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            locals_ = _comprehension_locals(node)
            for ref, _ in _scope_loads(node, kind="comprehension"):
                name = ref.id
                if name in locals_ or name in _BUILTIN_NAMES:
                    continue
                if name not in top_level:
                    continue
                kind_label = type(node).__name__
                findings.append(Finding(file, node_index, node_name,
                                        ref.lineno, ref.col_offset, name,
                                        "COMPREHENSION-LEAK",
                                        f"{kind_label} body reads top-level {name!r}"))

    return findings


# ---------------------------------------------------------------------------
# Workflow scanning
# ---------------------------------------------------------------------------

def _iter_transform_scripts(workflow_path: Path):
    """Yield (node_index, node_name, script) for every transform_flow node
    in a workflow JSON file."""
    try:
        data = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        yield "ERROR", str(exc), None
        return
    nodes = data.get("nodes") or []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        if node.get("type") != "transform_flow":
            continue
        if str(node.get("lang") or "python") != "python":
            continue
        script = node.get("script")
        if not isinstance(script, str):
            continue
        name = (node.get("extra") or {}).get("name") or f"transform_flow[{i}]"
        yield i, name, script


def lint_workflow(path: Path) -> List[Finding]:
    findings: List[Finding] = []
    for node_index, node_name, script in _iter_transform_scripts(path):
        if script is None:
            findings.append(Finding(str(path), -1, node_name, 0, 0, "<file>",
                                    "SYNTAX", node_index))
            continue
        findings.extend(_lint_script(script, str(path), node_index, node_name))
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args:
        targets = [Path(a) for a in args]
    else:
        targets = sorted(Path("examples").glob("*.json"))

    if not targets:
        print("no workflow JSONs to lint", file=sys.stderr)
        return 0

    all_findings: List[Finding] = []
    for path in targets:
        if not path.is_file():
            print(f"skip (not a file): {path}", file=sys.stderr)
            continue
        all_findings.extend(lint_workflow(path))

    if not all_findings:
        print(f"clean: {len(targets)} workflow(s) — no transform_flow hazards detected.")
        return 0

    by_file: dict = {}
    for f in all_findings:
        by_file.setdefault(f.file, []).append(f)
    for file, items in by_file.items():
        print(f"\n{file}  ({len(items)} finding{'s' if len(items) != 1 else ''})")
        for f in items:
            print(f"  {f.format()}")
    print(f"\n{len(all_findings)} finding(s) across {len(by_file)} file(s).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
