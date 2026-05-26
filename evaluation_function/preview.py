import ast
from typing import Any
from lf_toolkit.preview import Result, Params, Preview

_BLOCKED_MODULES = {
    "os", "sys", "subprocess", "socket", "urllib", "http",
    "requests", "shutil", "pathlib", "ftplib", "smtplib",
    "ctypes", "multiprocessing", "threading", "importlib",
    "pickle", "builtins",
}

_BLOCKED_BUILTINS = {"exec", "eval", "compile", "open", "__import__"}


class _SecurityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.violations: list[str] = []

    def visit_Import(self, node):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in _BLOCKED_MODULES:
                self.violations.append(f"import of '{root}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            root = node.module.split(".")[0]
            if root in _BLOCKED_MODULES:
                self.violations.append(f"import of '{root}' is not allowed")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_BUILTINS:
            self.violations.append(f"use of '{node.func.id}()' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr.startswith("__") and node.attr.endswith("__"):
            self.violations.append(f"access to '{node.attr}' is not allowed")
        self.generic_visit(node)


def preview_function(response: Any, params: Params) -> Result:
    try:
        tree = ast.parse(str(response))
    except SyntaxError as e:
        return Result(preview=Preview(feedback=f"SyntaxError: {e.msg} (line {e.lineno})"))

    visitor = _SecurityVisitor()
    visitor.visit(tree)
    if visitor.violations:
        lines = "\n".join(f"- {v}" for v in visitor.violations)
        return Result(preview=Preview(feedback=f"Unsafe code detected:\n{lines}"))

    return Result(preview=Preview(feedback="Valid Python syntax."))