import unittest
from unittest.mock import patch

from lf_toolkit.evaluation.image_upload import ImageUploadError

from .evaluation import evaluation_function, _run_code

_SQUARE_CODE = "n = int(input())\nprint(n * n)"
_CRASH_CODE = "raise ValueError('oops')"
_INFINITE_CODE = "while True: pass"


def _params(*tests):
    return {"mode": "io_test", "tests": list(tests)}


def _test(inp, expected, hidden=False):
    return {"input": inp, "expected_output": expected, "hidden": hidden}


class TestEvaluationFunction(unittest.TestCase):

    def test_all_pass(self):
        params = _params(_test("5\n", "25\n"), _test("3\n", "9\n"))
        result = evaluation_function(_SQUARE_CODE, None, params).to_dict()

        self.assertTrue(result["is_correct"])
        self.assertIn("2/2 tests passed", result["feedback"])
        self.assertIn("```", result["feedback"])

    def test_partial_fail(self):
        params = _params(_test("5\n", "25\n"), _test("3\n", "99\n"))
        result = evaluation_function(_SQUARE_CODE, None, params).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("1/2 tests passed", result["feedback"])
        self.assertIn("```", result["feedback"])

    def test_hidden_test_fail(self):
        params = _params(_test("5\n", "999\n", hidden=True))
        result = evaluation_function(_SQUARE_CODE, None, params).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("Hidden test 1", result["feedback"])
        self.assertNotIn("999", result["feedback"])
        self.assertNotIn("5", result["feedback"])

    def test_runtime_error(self):
        params = _params(_test("5\n", "25\n"))
        result = evaluation_function(_CRASH_CODE, None, params).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("runtime error", result["feedback"])
        self.assertIn("```", result["feedback"])

    def test_no_tests(self):
        result = evaluation_function(_SQUARE_CODE, None, {"mode": "demo"}).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("```", result["feedback"])

    def test_missing_mode(self):
        result = evaluation_function(_SQUARE_CODE, None, {}).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("mode", result["feedback"])


_PLOT_CODE = "import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])\n"
_MULTI_PLOT_CODE = (
    "import matplotlib.pyplot as plt\n"
    "plt.figure(1); plt.plot([1, 2])\n"
    "plt.figure(2); plt.plot([3, 4])\n"
)
_FAKE_URL = "https://example.com/plot.png"


class TestImageGeneration(unittest.TestCase):

    @patch("evaluation_function.evaluation.upload_image", return_value=_FAKE_URL)
    def test_single_plot_demo_mode(self, mock_upload):
        result = evaluation_function(_PLOT_CODE, None, {"mode": "demo"}).to_dict()
        mock_upload.assert_called_once()
        self.assertIn("![Plot 1]", result["feedback"])

    @patch("evaluation_function.evaluation.upload_image", return_value=_FAKE_URL)
    def test_single_plot_passing_test(self, mock_upload):
        params = _params(_test("", ""))
        result = evaluation_function(_PLOT_CODE, None, params).to_dict()
        self.assertIn("![Plot 1]", result["feedback"])

    @patch("evaluation_function.evaluation.upload_image", return_value=_FAKE_URL)
    def test_single_plot_failing_test(self, mock_upload):
        params = _params(_test("", "wrong"))
        result = evaluation_function(_PLOT_CODE, None, params).to_dict()
        self.assertIn("![Plot 1]", result["feedback"])

    @patch("evaluation_function.evaluation.upload_image", return_value=_FAKE_URL)
    def test_multiple_plots(self, mock_upload):
        result = evaluation_function(_MULTI_PLOT_CODE, None, {"mode": "demo"}).to_dict()
        self.assertEqual(mock_upload.call_count, 2)
        self.assertIn("![Plot 1]", result["feedback"])
        self.assertIn("![Plot 2]", result["feedback"])

    @patch("evaluation_function.evaluation.upload_image", side_effect=ImageUploadError)
    def test_upload_failure_graceful(self, mock_upload):
        result = evaluation_function(_PLOT_CODE, None, {"mode": "demo"}).to_dict()
        self.assertNotIn("![Plot", result["feedback"])

    def test_run_code_captures_images(self):
        _, _, timed_out, images = _run_code(_PLOT_CODE, "")
        self.assertFalse(timed_out)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].format, "PNG")