# evaluatePython — Teacher Guide

## What this function does

`evaluatePython` runs a student's Python code submission and checks it against criteria you define. You choose how it is graded:

| Mode | Use when… |
|------|-----------|
| `demo` | You want students to explore and see their output — no grading |
| `io_test` | The program reads from stdin and writes to stdout |
| `unit_test` | The program defines functions/classes you want to test directly |

---

## Mode: `demo`

Runs the student's code and shows them their output. No pass/fail verdict is given. Useful for exploratory exercises or visualisation tasks.

**Params**
```json
{ "mode": "demo" }
```

Students see their stdout and any matplotlib figures they produced. Bare expressions (e.g. `3.14 * 2 * 5`) print automatically without needing `print()`, just like a Jupyter notebook.

---

## Mode: `io_test`

Runs the student's code once per test case, feeding it a string via stdin and comparing its stdout to an expected output.

**Params**
```json
{
  "mode": "io_test",
  "tests": [
    {
      "input":           "5\n",
      "expected_output": "25\n"
    }
  ]
}
```

### Test case fields

Each test case uses **either** `input` (student reads via `input()`) **or** `inject` (variables are pre-set, no `input()` needed):

| Field | Description |
|-------|-------------|
| `input` | Text sent to stdin. Student code reads it with `input()`. Use `\n` for newlines. |
| `inject` | Dict of variable names and values injected before student code runs. Student uses the variables directly — no `input()` required. Values can be numbers, strings, lists, or dicts. |
| `expected_output` | The exact stdout the program should produce. Trailing whitespace is ignored. |
| `hidden` | `true` = hide the input/variables and expected output from the student. They see only "Hidden test N: passed/failed." |

### Tips

- Use `hidden: true` for mark-scheme test cases students should not be able to reverse-engineer.
- You can mix visible and hidden tests in the same question.
- Matplotlib figures produced during a passing or failing test are shown to the student.
- A 25-second per-test timeout applies; timed-out tests count as failures.
- Students can write bare expressions (e.g. `3.14 * r * r`) without `print()` — the output is captured automatically.

### Using the answer field as the reference solution

If you set `"use_answer_as_expected_output": true`, you can write your reference solution in the **answer** field (the code editor in the LF UI) instead of hardcoding `expected_output` in every test case. The system runs your solution with each test's input and uses its output as the expected result.

**Params**
```json
{
  "mode": "io_test",
  "use_answer_as_expected_output": true,
  "tests": [
    { "input": "5\n" },
    { "input": "0\n" },
    { "input": "-3\n", "hidden": true }
  ]
}
```

**Answer field** (reference solution):
```python
n = int(input())
print(n * n)
```

This is especially convenient when the reference solution is already in the answer field for the worked solution display — you don't need to duplicate the expected outputs.

### Example — square a number (stdin-based)

Student code:
```python
n = int(input())
print(n * n)
```

Params:
```json
{
  "mode": "io_test",
  "tests": [
    { "input": "5\n",  "expected_output": "25\n" },
    { "input": "0\n",  "expected_output": "0\n"  },
    { "input": "-3\n", "expected_output": "9\n", "hidden": true }
  ]
}
```

### Example — square a number (inject-based)

Use `inject` when students shouldn't need to handle input themselves — they just write an expression or use the named variable directly:

Student code:
```python
print(n * n)
```

Params:
```json
{
  "mode": "io_test",
  "tests": [
    { "inject": {"n": 5},  "expected_output": "25\n" },
    { "inject": {"n": 0},  "expected_output": "0\n"  },
    { "inject": {"n": -3}, "expected_output": "9\n", "hidden": true }
  ]
}
```

---

## Mode: `unit_test`

Runs the student's code and then calls test functions you write. The student must define functions or classes that your tests exercise directly — there is no stdin/stdout comparison.

**Params**
```json
{
  "mode": "unit_test",
  "test_code": "<your test code as a string>"
}
```

### Writing test functions

You can write tests in three styles:

**Plain functions** (simplest):
```python
def test_positive():
    assert square(5) == 25

def test_zero():
    assert square(0) == 0
```

**`unittest.TestCase`** (for more structured tests):
```python
import unittest

class SquareTests(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(square(5), 25)

    def test_negative(self):
        self.assertEqual(square(-3), 9)
```

**Hypothesis** (property-based testing — generates many random inputs automatically):
```python
from hypothesis import given, settings
import hypothesis.strategies as st

@given(st.integers(-100, 100))
@settings(max_examples=50)
def test_square_is_nonnegative(n):
    assert square(n) >= 0
```

### Tips

- Each `test_*` function counts as one test in the summary.
- Use assertion messages to give students a hint when they fail: `assert square(5) == 25, "square(5) should be 25"`.
- If the student's code raises an exception at module level (e.g. a syntax or runtime error outside any function), all tests are reported as an error.
- Student `print()` calls do not affect test results.
- A 25-second total timeout applies to the entire execution.

### Writing test code in the answer field

The LF params editor is a plain JSON editor, which makes writing multiline test code awkward. Instead, set `"use_answer_as_test_code": true` and write your test functions in the **answer** field (the proper code editor):

**Params**
```json
{
  "mode": "unit_test",
  "use_answer_as_test_code": true
}
```

**Answer field** (test code):
```python
def test_positive():
    assert square(5) == 25, "square(5) should be 25"

def test_zero():
    assert square(0) == 0
```

### Example — testing a `square` function

Student code:
```python
def square(n):
    return n * n
```

Params:
```json
{
  "mode": "unit_test",
  "test_code": "def test_positive():\n    assert square(5) == 25, 'square(5) should be 25'\ndef test_zero():\n    assert square(0) == 0\ndef test_negative():\n    assert square(-3) == 9\n"
}
```

---

## Security restrictions

Students' code is checked before execution. The following are blocked and will return an error before the code runs:

- Importing: `os`, `sys`, `subprocess`, `socket`, `requests`, `pathlib`, and other system/network modules
- Calling: `exec`, `eval`, `compile`, `open`, `__import__` (but **`input()` is allowed**)
- Accessing dunder attributes (`__class__`, `__dict__`, etc.)

These restrictions cannot be bypassed; attempts result in an error feedback item rather than execution.