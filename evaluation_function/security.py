import ast

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


def check_code_safety(code: str) -> list[str]:
    """Return the list of security violations in ``code`` (empty means safe).

    Shared by ``preview_function`` (pre-submission check) and
    ``evaluation_function`` (pre-execution gate). A syntax error is not a
    safety violation -- it is surfaced elsewhere -- so it yields an empty list.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    visitor = _SecurityVisitor()
    visitor.visit(tree)
    return visitor.violations