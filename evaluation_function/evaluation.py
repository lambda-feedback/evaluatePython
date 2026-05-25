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


def evaluation_function(response: Any, answer: Any, params: Params) -> Result:
    tests = params.get("tests", [])
    result = Result()

    if not tests:
        stdout, stderr, timed_out, images = _run_code(str(response), "")
        if timed_out:
            result.add_feedback("error", f"Code timed out after {_TIMEOUT}s.")
        elif stderr and not stdout:
            result.add_feedback("error", _code_block("Error", stderr.strip()))
        else:
            parts = [_code_block("Output", stdout.rstrip() or "(no output)")]
            parts.extend(_upload_plots(images))
            result.add_feedback("output", "\n\n".join(parts))
        return result


    passed = 0

    for i, test in enumerate(tests, 1):
        stdin = test.get("input", "")
        expected = test.get("expected_output", "").rstrip()
        hidden = test.get("hidden", False)

        stdout, stderr, timed_out, images = _run_code(str(response), stdin)
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
                if stdin.strip():
                    parts.append(_code_block("Input", stdin.rstrip()))
                parts.append(_code_block("Error", stderr.strip()))
                result.add_feedback(tag, "\n\n".join(parts))
        elif actual == expected:
            passed += 1
            if hidden:
                result.add_feedback("pass", f"{label}: passed.")
            else:
                parts = [f"{label}: passed."]
                if stdin.strip():
                    parts.append(_code_block("Input", stdin.rstrip()))
                parts.append(_code_block("Output", actual or "(no output)"))
                parts.extend(_upload_plots(images))
                result.add_feedback("pass", "\n\n".join(parts))
        else:
            tag = "hidden_fail" if hidden else "fail"
            if hidden:
                result.add_feedback(tag, f"{label}: failed.")
            else:
                parts = [f"{label}: failed."]
                if stdin.strip():
                    parts.append(_code_block("Input", stdin.rstrip()))
                parts.append(_code_block("Your output", actual or "(no output)"))
                parts.append(_code_block("Expected", expected))
                parts.extend(_upload_plots(images))
                result.add_feedback(tag, "\n\n".join(parts))

    result.is_correct = passed == len(tests)
    result.add_feedback("summary", f"{passed}/{len(tests)} tests passed.")
    return result