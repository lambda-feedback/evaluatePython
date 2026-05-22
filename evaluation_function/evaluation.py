import os
import subprocess
import tempfile
from typing import Any
from lf_toolkit.evaluation import Result, Params

_TIMEOUT = 5


def _run_code(code: str, stdin: str) -> tuple[str, str, bool]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmpfile = f.name
    try:
        proc = subprocess.run(
            ["python", tmpfile],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        return proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired:
        return "", "", True
    finally:
        os.unlink(tmpfile)


def evaluation_function(response: Any, answer: Any, params: Params) -> Result:
    tests = params.get("tests", [])

    if not tests:
        result = Result(is_correct=False)
        result.add_feedback("error", "No test cases provided.")
        return result

    passed = 0
    result = Result()

    for i, test in enumerate(tests, 1):
        stdin = test.get("input", "")
        expected = test.get("expected_output", "").rstrip()
        hidden = test.get("hidden", False)

        stdout, stderr, timed_out = _run_code(str(response), stdin)
        actual = stdout.rstrip()

        if timed_out:
            tag = "hidden_fail" if hidden else "fail"
            label = f"Hidden test {i}" if hidden else f"Test {i}"
            result.add_feedback(tag, f"{label}: timed out after {_TIMEOUT}s.")
        elif stderr and not stdout:
            tag = "hidden_fail" if hidden else "fail"
            label = f"Hidden test {i}" if hidden else f"Test {i}"
            msg = f"{label}: runtime error." if hidden else f"{label}: runtime error.\n{stderr.strip()}"
            result.add_feedback(tag, msg)
        elif actual == expected:
            passed += 1
            label = f"Hidden test {i}" if hidden else f"Test {i}"
            result.add_feedback("pass", f"{label}: passed.")
        else:
            tag = "hidden_fail" if hidden else "fail"
            if hidden:
                result.add_feedback(tag, f"Hidden test {i}: failed.")
            else:
                result.add_feedback(tag, (
                    f"Test {i}: failed.\n"
                    f"  Input:    {stdin.rstrip()}\n"
                    f"  Expected: {expected}\n"
                    f"  Got:      {actual}"
                ))

    result.is_correct = passed == len(tests)
    result.add_feedback("summary", f"{passed}/{len(tests)} tests passed.")
    return result