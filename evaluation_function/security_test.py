import unittest

from .security import check_code_safety


class TestCheckCodeSafety(unittest.TestCase):

    def test_safe_code_returns_no_violations(self):
        self.assertEqual(check_code_safety("x = int(input())\nprint(x * x)"), [])

    def test_safe_stdlib_import_allowed(self):
        self.assertEqual(check_code_safety("import math\nprint(math.pi)"), [])

    def test_blocked_import(self):
        violations = check_code_safety("import os")
        self.assertEqual(violations, ["import of 'os' is not allowed"])

    def test_blocked_from_import(self):
        violations = check_code_safety("from subprocess import call")
        self.assertEqual(violations, ["import of 'subprocess' is not allowed"])

    def test_blocked_submodule_import(self):
        violations = check_code_safety("import urllib.request")
        self.assertEqual(violations, ["import of 'urllib' is not allowed"])

    def test_blocked_builtin_call(self):
        violations = check_code_safety("exec('x = 1')")
        self.assertEqual(violations, ["use of 'exec()' is not allowed"])

    def test_dunder_attribute_access(self):
        violations = check_code_safety("().__class__.__bases__")
        self.assertIn("access to '__class__' is not allowed", violations)
        self.assertIn("access to '__bases__' is not allowed", violations)

    def test_syntax_error_is_not_a_violation(self):
        self.assertEqual(check_code_safety("def f(:\n"), [])

    def test_multiple_violations_collected(self):
        violations = check_code_safety("import os\nimport socket\nopen('/etc/passwd')")
        self.assertIn("import of 'os' is not allowed", violations)
        self.assertIn("import of 'socket' is not allowed", violations)
        self.assertIn("use of 'open()' is not allowed", violations)
