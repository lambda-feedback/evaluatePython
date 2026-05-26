import unittest

from .preview import Params, preview_function


class TestPreviewFunction(unittest.TestCase):

    def test_valid_python(self):
        response, params = "x = 1 + 2", Params()
        result = preview_function(response, params)

        self.assertIn("preview", result)
        self.assertNotIn("SyntaxError", result["preview"].get("feedback", ""))
        self.assertNotIn("Unsafe", result["preview"].get("feedback", ""))

    def test_invalid_python(self):
        response, params = "def foo(:", Params()
        result = preview_function(response, params)

        self.assertIn("preview", result)
        self.assertIn("SyntaxError", result["preview"].get("feedback", ""))

    def test_dangerous_import(self):
        response, params = "import os", Params()
        result = preview_function(response, params)

        self.assertIn("preview", result)
        self.assertIn("Unsafe", result["preview"].get("feedback", ""))

    def test_dangerous_from_import(self):
        response, params = "from subprocess import call", Params()
        result = preview_function(response, params)

        self.assertIn("preview", result)
        self.assertIn("Unsafe", result["preview"].get("feedback", ""))

    def test_dangerous_builtin_call(self):
        response, params = "exec('x=1')", Params()
        result = preview_function(response, params)

        self.assertIn("preview", result)
        self.assertIn("Unsafe", result["preview"].get("feedback", ""))

    def test_dunder_access(self):
        response, params = "x.__class__.__bases__", Params()
        result = preview_function(response, params)

        self.assertIn("preview", result)
        self.assertIn("Unsafe", result["preview"].get("feedback", ""))

    def test_input_is_allowed(self):
        response, params = "x = int(input())", Params()
        result = preview_function(response, params)

        self.assertIn("preview", result)
        self.assertNotIn("Unsafe", result["preview"].get("feedback", ""))