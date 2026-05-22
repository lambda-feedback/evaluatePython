import unittest

from .evaluation import evaluation_function

_SQUARE_CODE = "n = int(input())\nprint(n * n)"
_CRASH_CODE = "raise ValueError('oops')"
_INFINITE_CODE = "while True: pass"


def _params(*tests):
    return {"tests": list(tests)}


def _test(inp, expected, hidden=False):
    return {"input": inp, "expected_output": expected, "hidden": hidden}


class TestEvaluationFunction(unittest.TestCase):

    def test_all_pass(self):
        params = _params(_test("5\n", "25\n"), _test("3\n", "9\n"))
        result = evaluation_function(_SQUARE_CODE, None, params).to_dict()

        self.assertTrue(result["is_correct"])
        self.assertIn("2/2 tests passed", result["feedback"])

    def test_partial_fail(self):
        params = _params(_test("5\n", "25\n"), _test("3\n", "99\n"))
        result = evaluation_function(_SQUARE_CODE, None, params).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("1/2 tests passed", result["feedback"])

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

    def test_no_tests(self):
        result = evaluation_function(_SQUARE_CODE, None, {}).to_dict()

        self.assertFalse(result["is_correct"])
        self.assertIn("No test cases", result["feedback"])