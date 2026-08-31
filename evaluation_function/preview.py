import ast
from typing import Any
from lf_toolkit.preview import Result, Params, Preview

from .security import check_code_safety


def preview_function(response: Any, params: Params) -> Result:
    code = str(response)
    try:
        ast.parse(code)
    except SyntaxError as e:
        return Result(preview=Preview(feedback=f"SyntaxError: {e.msg} (line {e.lineno})"))

    violations = check_code_safety(code)
    if violations:
        lines = "\n".join(f"- {v}" for v in violations)
        return Result(preview=Preview(feedback=f"Unsafe code detected:\n{lines}"))

    return Result(preview=Preview(feedback="Valid Python syntax."))