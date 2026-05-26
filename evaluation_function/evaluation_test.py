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


def _inject_test(inject, expected, hidden=False):
    return {"inject": inject, "expected_output": expected, "hidden": hidden}


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


class TestInjectMode(unittest.TestCase):

    def test_inject_pass(self):
        params = _params(_inject_test({"n": 5}, "25\n"))
        result = evaluation_function("print(n * n)", None, params).to_dict()

        self.assertTrue(result["is_correct"])
        self.assertIn("1/1 tests passed", result["feedback"])
        self.assertIn("Variables", result["feedback"])
        self.assertIn("n = 5", result["feedback"])

    def test_inject_fail_shows_variables(self):
        params = _params(_inject_test({"n": 5}, "999\n"))
        result = evaluation_function("print(n * n)", None, params).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("Variables", result["feedback"])
        self.assertIn("n = 5", result["feedback"])

    def test_inject_multiple_vars(self):
        params = _params(_inject_test({"a": 3, "b": 4}, "7\n"))
        result = evaluation_function("print(a + b)", None, params).to_dict()

        self.assertTrue(result["is_correct"])

    def test_inject_hidden_suppresses_variables(self):
        params = _params(_inject_test({"n": 5}, "999\n", hidden=True))
        result = evaluation_function("print(n * n)", None, params).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertNotIn("n = 5", result["feedback"])

    def test_inject_string_value(self):
        params = _params(_inject_test({"name": "Alice"}, "Hello, Alice\n"))
        result = evaluation_function('print(f"Hello, {name}")', None, params).to_dict()

        self.assertTrue(result["is_correct"])


class TestReplExpression(unittest.TestCase):

    def test_bare_expression_demo(self):
        result = evaluation_function("3.14159*2*5", None, {"mode": "demo"}).to_dict()
        self.assertIn("31.4159", result["feedback"])

    def test_bare_expression_io_test(self):
        params = _params(_test("", "31.4159\n"))
        result = evaluation_function("3.14159*2*5", None, params).to_dict()
        self.assertTrue(result["is_correct"])

    def test_existing_print_not_double_wrapped(self):
        params = _params(_test("", "31.4159\n"))
        result = evaluation_function("print(31.4159)", None, params).to_dict()
        self.assertTrue(result["is_correct"])

    def test_assignment_no_auto_print(self):
        params = _params(_test("", "5\n"))
        result = evaluation_function("x = 5", None, params).to_dict()
        self.assertFalse(result["is_correct"])


class TestIoAnswerMode(unittest.TestCase):

    def test_answer_used_as_expected(self):
        params = {"mode": "io_test", "use_answer_as_expected_output": True,
                  "tests": [{"input": ""}]}
        result = evaluation_function("3.14159*2*5", "3.14159*2*5", params).to_dict()
        self.assertTrue(result["is_correct"])

    def test_answer_used_student_wrong(self):
        params = {"mode": "io_test", "use_answer_as_expected_output": True,
                  "tests": [{"input": ""}]}
        result = evaluation_function("3.14159*2*6", "3.14159*2*5", params).to_dict()
        self.assertFalse(result["is_correct"])

    def test_answer_with_inject(self):
        params = {"mode": "io_test", "use_answer_as_expected_output": True,
                  "tests": [{"inject": {"n": 5}}]}
        result = evaluation_function("print(n * n)", "print(n * n)", params).to_dict()
        self.assertTrue(result["is_correct"])

    def test_flag_absent_uses_expected_output_field(self):
        params = _params(_test("", "31.4159\n"))
        result = evaluation_function("3.14159*2*5", "ignored", params).to_dict()
        self.assertTrue(result["is_correct"])


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


_SQUARE_FN = "def square(n): return n * n"
_WRONG_SQUARE_FN = "def square(n): return n + 1"
_CRASH_FN = "raise ValueError('boom')"

_SQUARE_TESTS = (
    "def test_positive():\n"
    "    assert square(5) == 25, 'expected 25'\n"
    "def test_zero():\n"
    "    assert square(0) == 0\n"
)

_SQUARE_TESTS_UNITTEST = (
    "import unittest\n"
    "class SquareTest(unittest.TestCase):\n"
    "    def test_positive(self):\n"
    "        self.assertEqual(square(5), 25)\n"
    "    def test_zero(self):\n"
    "        self.assertEqual(square(0), 0)\n"
)

_SQUARE_TESTS_HYPOTHESIS = (
    "from hypothesis import given, settings\n"
    "import hypothesis.strategies as st\n"
    "@given(st.integers(-100, 100))\n"
    "@settings(max_examples=50)\n"
    "def test_square(n):\n"
    "    assert square(n) == n * n, f'square({n}) = {square(n)}, expected {n*n}'\n"
)


def _unit_params(test_code):
    return {"mode": "unit_test", "test_code": test_code}


class TestUnitTestMode(unittest.TestCase):

    def test_all_pass(self):
        result = evaluation_function(_SQUARE_FN, None, _unit_params(_SQUARE_TESTS)).to_dict()

        self.assertTrue(result["is_correct"])
        self.assertIn("2/2 tests passed", result["feedback"])
        self.assertIn("test_positive: passed", result["feedback"])
        self.assertIn("test_zero: passed", result["feedback"])

    def test_assertion_fail(self):
        result = evaluation_function(_WRONG_SQUARE_FN, None, _unit_params(_SQUARE_TESTS)).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("0/2 tests passed", result["feedback"])
        self.assertIn("failed", result["feedback"])
        self.assertIn("expected 25", result["feedback"])

    def test_unittest_style(self):
        result = evaluation_function(_SQUARE_FN, None, _unit_params(_SQUARE_TESTS_UNITTEST)).to_dict()

        self.assertTrue(result["is_correct"])
        self.assertIn("2/2 tests passed", result["feedback"])

    def test_module_level_crash(self):
        result = evaluation_function(_CRASH_FN, None, _unit_params(_SQUARE_TESTS)).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("boom", result["feedback"])

    def test_empty_test_code(self):
        result = evaluation_function(_SQUARE_FN, None, _unit_params("")).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("No test code", result["feedback"])

    def test_student_print_no_pollution(self):
        code_with_print = _SQUARE_FN + "\nprint('hello')"
        result = evaluation_function(code_with_print, None, _unit_params(_SQUARE_TESTS)).to_dict()

        self.assertTrue(result["is_correct"])
        self.assertIn("2/2 tests passed", result["feedback"])

    def test_hypothesis_pass(self):
        result = evaluation_function(_SQUARE_FN, None, _unit_params(_SQUARE_TESTS_HYPOTHESIS)).to_dict()

        self.assertTrue(result["is_correct"])
        self.assertIn("1/1 tests passed", result["feedback"])

    def test_use_answer_as_test_code(self):
        params = {"mode": "unit_test", "use_answer_as_test_code": True}
        result = evaluation_function(_SQUARE_FN, _SQUARE_TESTS, params).to_dict()
        self.assertTrue(result["is_correct"])
        self.assertIn("2/2 tests passed", result["feedback"])

    def test_hypothesis_fail_shows_minimal_example(self):
        result = evaluation_function(_WRONG_SQUARE_FN, None, _unit_params(_SQUARE_TESTS_HYPOTHESIS)).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("0/1 tests passed", result["feedback"])
        self.assertIn("square(", result["feedback"])


class TestPep8Feedback(unittest.TestCase):

    def test_violations_reported(self):
        # E225: missing whitespace around operator
        result = evaluation_function("x=1\nprint(x)", None, {"mode": "demo", "pep8_feedback": True}).to_dict()
        self.assertIn("Style suggestions", result["feedback"])
        self.assertIn("E225", result["feedback"])

    def test_clean_code_no_issues(self):
        result = evaluation_function("x = 1\nprint(x)", None, {"mode": "demo", "pep8_feedback": True}).to_dict()
        self.assertIn("No style issues found", result["feedback"])

    def test_not_set_no_style_feedback(self):
        result = evaluation_function("x=1\nprint(x)", None, {"mode": "demo"}).to_dict()
        self.assertNotIn("Style suggestions", result["feedback"])
        self.assertNotIn("No style issues found", result["feedback"])

    def test_custom_rule_list(self):
        # E225 and E231 both violated: x=1 and print(x,y)
        code = "x=1\nprint(x,x)"
        result = evaluation_function(code, None, {"mode": "demo", "pep8_feedback": ["E225"]}).to_dict()
        self.assertIn("E225", result["feedback"])
        self.assertNotIn("E231", result["feedback"])

    def test_pep8_appended_to_io_test_result(self):
        params = {**_params(_test("5\n", "25\n")), "pep8_feedback": True}
        result = evaluation_function(_SQUARE_CODE, None, params).to_dict()
        self.assertTrue(result["is_correct"])
        self.assertIn("No style issues found", result["feedback"])