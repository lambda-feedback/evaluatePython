import json
import os
import shutil
import subprocess
import tempfile
from typing import Any

from PIL import Image
from lf_toolkit.evaluation import Result, Params
from lf_toolkit.evaluation.image_upload import upload_image, ImageUploadError

_TIMEOUT = 25
_UPLOAD_FOLDER = "evaluatePython"

_PREAMBLE_TEMPLATE = """\
import os as _os

_plot_dir = {plot_dir!r}
_plot_idx = [0]

def _capture_plots():
    import sys as _sys
    if 'matplotlib.pyplot' not in _sys.modules:
        return
    import matplotlib.pyplot as _plt
    for num in _plt.get_fignums():
        _plot_idx[0] += 1
        _plt.figure(num).savefig(
            _os.path.join(_plot_dir, str(_plot_idx[0]).zfill(4) + '.png'))
"""

_CAPTURE_CALL = "_capture_plots()\n"

_UNIT_RUNNER_TEMPLATE = """
import json as _json
import unittest as _ut

_unit_results = []

class _UnitTrackingResult(_ut.TestResult):
    def __init__(self):
        super().__init__()
        self.successes = []
    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.append(test)

_unit_tc_classes = [v for v in globals().values()
                    if isinstance(v, type) and issubclass(v, _ut.TestCase) and v is not _ut.TestCase]
if _unit_tc_classes:
    _unit_suite = _ut.TestSuite()
    for _unit_cls in _unit_tc_classes:
        _unit_suite.addTests(_ut.TestLoader().loadTestsFromTestCase(_unit_cls))
    _unit_tr = _UnitTrackingResult()
    _unit_suite.run(_unit_tr)
    for _unit_t in _unit_tr.successes:
        _unit_results.append({{'name': _unit_t.id().split('.')[-1], 'status': 'pass'}})
    for _unit_t, _unit_e in _unit_tr.failures:
        _unit_results.append({{'name': _unit_t.id().split('.')[-1], 'status': 'fail', 'message': _unit_e}})
    for _unit_t, _unit_e in _unit_tr.errors:
        _unit_results.append({{'name': _unit_t.id().split('.')[-1], 'status': 'error', 'message': _unit_e}})

_unit_plain = [(n, f) for n, f in sorted(globals().items())
               if n.startswith('test_') and callable(f) and not isinstance(f, type)]
for _unit_name, _unit_fn in _unit_plain:
    try:
        _unit_fn()
        _unit_results.append({{'name': _unit_name, 'status': 'pass'}})
    except AssertionError as _unit_exc:
        _unit_results.append({{'name': _unit_name, 'status': 'fail', 'message': str(_unit_exc)}})
    except Exception as _unit_exc:
        _unit_results.append({{'name': _unit_name, 'status': 'error', 'message': repr(_unit_exc)}})

with open({results_path!r}, 'w') as _unit_f:
    _json.dump(_unit_results, _unit_f)
"""


def _run_code(code: str, stdin: str) -> tuple[str, str, bool, list[Image.Image]]:
    plot_dir = tempfile.mkdtemp()
    preamble = _PREAMBLE_TEMPLATE.format(plot_dir=plot_dir)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(preamble + "\n" + code + "\n" + _CAPTURE_CALL)
        tmpfile = f.name
    try:
        proc = subprocess.run(
            ["python", tmpfile],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            env={**os.environ, "MPLBACKEND": "Agg", "MPLCONFIGDIR": "/tmp"},
        )
        images = []
        for fn in sorted(os.listdir(plot_dir)):
            if fn.endswith(".png"):
                img = Image.open(os.path.join(plot_dir, fn))
                img.load()
                img.format = "PNG"
                images.append(img)
        return proc.stdout, proc.stderr, False, images
    except subprocess.TimeoutExpired:
        return "", "", True, []
    finally:
        os.unlink(tmpfile)
        shutil.rmtree(plot_dir, ignore_errors=True)


def _code_block(label: str, content: str) -> str:
    return f"{label}:\n```\n{content}\n```"


def _upload_plots(images: list[Image.Image]) -> list[str]:
    result = []
    for i, img in enumerate(images, 1):
        try:
            url = upload_image(img, _UPLOAD_FOLDER)
            result.append(f"![Plot {i}]({url})")
        except ImageUploadError:
            pass
    return result


def _evaluate_demo(response: str, result: Result) -> Result:
    stdout, stderr, timed_out, images = _run_code(response, "")
    if timed_out:
        result.add_feedback("error", f"Code timed out after {_TIMEOUT}s.")
    elif stderr and not stdout:
        result.add_feedback("error", _code_block("Error", stderr.strip()))
    else:
        parts = [_code_block("Output", stdout.rstrip() or "(no output)")]
        parts.extend(_upload_plots(images))
        result.add_feedback("output", "\n\n".join(parts))
    return result


def _evaluate_io(response: str, tests: list, result: Result) -> Result:
    passed = 0

    for i, test in enumerate(tests, 1):
        inject = test.get("inject")
        stdin = test.get("input", "")
        expected = test.get("expected_output", "").rstrip()
        hidden = test.get("hidden", False)

        if inject:
            prefix = "".join(f"{k} = {v!r}\n" for k, v in inject.items())
            run_code = prefix + response
            run_stdin = ""
            input_block = _code_block("Variables", "\n".join(f"{k} = {v!r}" for k, v in inject.items()))
        else:
            run_code = response
            run_stdin = stdin
            input_block = _code_block("Input", stdin.rstrip()) if stdin.strip() else None

        stdout, stderr, timed_out, images = _run_code(run_code, run_stdin)
        actual = stdout.rstrip()
        label = f"Hidden test {i}" if hidden else f"Test {i}"

        if timed_out:
            tag = "hidden_fail" if hidden else "fail"
            result.add_feedback(tag, f"{label}: timed out after {_TIMEOUT}s.")
        elif stderr and not stdout:
            tag = "hidden_fail" if hidden else "fail"
            if hidden:
                result.add_feedback(tag, f"{label}: runtime error.")
            else:
                parts = [f"{label}: runtime error."]
                if input_block:
                    parts.append(input_block)
                parts.append(_code_block("Error", stderr.strip()))
                result.add_feedback(tag, "\n\n".join(parts))
        elif actual == expected:
            passed += 1
            if hidden:
                result.add_feedback("pass", f"{label}: passed.")
            else:
                parts = [f"{label}: passed."]
                if input_block:
                    parts.append(input_block)
                parts.append(_code_block("Output", actual or "(no output)"))
                parts.extend(_upload_plots(images))
                result.add_feedback("pass", "\n\n".join(parts))
        else:
            tag = "hidden_fail" if hidden else "fail"
            if hidden:
                result.add_feedback(tag, f"{label}: failed.")
            else:
                parts = [f"{label}: failed."]
                if input_block:
                    parts.append(input_block)
                parts.append(_code_block("Your output", actual or "(no output)"))
                parts.append(_code_block("Expected", expected))
                parts.extend(_upload_plots(images))
                result.add_feedback(tag, "\n\n".join(parts))

    result.is_correct = passed == len(tests)
    result.add_feedback("summary", f"{passed}/{len(tests)} tests passed.")
    return result


def _evaluate_unit(response: str, test_code: str, result: Result) -> Result:
    if not test_code.strip():
        result.add_feedback("error", "No test code provided for unit_test mode.")
        return result

    results_path = tempfile.mktemp(suffix=".json")
    runner = _UNIT_RUNNER_TEMPLATE.format(results_path=results_path)
    combined = response + "\n\n" + test_code + runner
    stdout, stderr, timed_out, _ = _run_code(combined, "")

    test_results = None
    try:
        if timed_out:
            result.add_feedback("error", f"Code timed out after {_TIMEOUT}s.")
        elif not os.path.exists(results_path):
            msg = _code_block("Error", stderr.strip()) if stderr else "Unknown error — no results produced."
            result.add_feedback("error", msg)
        else:
            with open(results_path) as f:
                test_results = json.load(f)
    finally:
        if os.path.exists(results_path):
            os.unlink(results_path)

    if test_results is None:
        return result

    passed = 0
    for r in test_results:
        name, status = r["name"], r["status"]
        if status == "pass":
            passed += 1
            result.add_feedback("pass", f"{name}: passed.")
        else:
            msg = r.get("message", "")
            body = f"{name}: {'failed' if status == 'fail' else 'runtime error'}."
            if msg:
                label = "AssertionError" if status == "fail" else "Error"
                body += f"\n\n{_code_block(label, msg.strip())}"
            result.add_feedback("fail", body)

    total = len(test_results)
    result.is_correct = total > 0 and passed == total
    result.add_feedback("summary", f"{passed}/{total} tests passed.")
    return result


def evaluation_function(response: Any, answer: Any, params: Params) -> Result:
    result = Result()
    mode = params.get("mode")
    if mode not in ("demo", "io_test", "unit_test"):
        result.add_feedback("error", f"Unknown or missing mode: {mode!r}. Expected 'demo', 'io_test', or 'unit_test'.")
        return result

    if mode == "demo":
        return _evaluate_demo(str(response), result)
    if mode == "io_test":
        return _evaluate_io(str(response), params.get("tests", []), result)
    return _evaluate_unit(str(response), params.get("test_code", ""), result)