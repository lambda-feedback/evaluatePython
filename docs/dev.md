# evaluatePython — Developer Reference

## Overview

`evaluatePython` executes student Python code in a sandboxed subprocess and returns structured formative feedback. It exposes two functions to the Lambda Feedback platform:

- **`evaluation_function`** — run and grade student code
- **`preview_function`** — static AST-based security check (called before execution)

---

## `evaluation_function`

### Request

```json
{
  "response": "<student code string>",
  "answer":   "<reference solution — used when use_answer_as_test_code or use_answer_as_expected_output is set>",
  "params": { ... }
}
```

`params` must include a `mode` field. The three supported modes are described below.

---

### Mode: `demo`

Run student code with no stdin and return its stdout as output feedback. No pass/fail verdict is set (`is_correct` is always `false`).

```json
{
  "mode": "demo"
}
```

If the last statement is a bare expression (e.g. `3.14 * 2 * 5`), it is automatically wrapped in `print(repr(...))` so it prints like a REPL. Existing `print()` calls are not double-wrapped.

Feedback tags produced: `output` (stdout + any plots), or `error` (timeout / runtime error).

---

### Mode: `io_test`

Run student code against a list of stdin/stdout test cases.

Each test case uses either `input` (stdin-based) or `inject` (variable injection):

```json
{
  "mode": "io_test",
  "tests": [
    {
      "input":           "5\n",   // stdin — student code calls input()
      "expected_output": "25\n",
      "hidden":          false
    },
    {
      "inject":          {"n": 5}, // variables set before student code runs — no input() needed
      "expected_output": "25\n",
      "hidden":          false
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `input` | Text piped to stdin. Mutually exclusive with `inject`. |
| `inject` | Dict of `{variable_name: value}` prepended as assignments before student code. Values can be any JSON type. Mutually exclusive with `input`. |
| `expected_output` | Expected stdout; trailing whitespace stripped before comparison. Required unless `use_answer_as_expected_output` is set. |
| `hidden` | `true` = suppress input/variables and expected output from feedback. |

- `tests` is required; an empty list sets `is_correct = true` with `0/0 tests passed`.
- `hidden: true` replaces details with `"Hidden test N: failed."` so students cannot reverse-engineer the answer.
- With `inject`, feedback shows a "Variables:" block (e.g. `n = 5`) instead of "Input:".
- Bare final expressions in student code are auto-wrapped in `print(repr(...))` (REPL behaviour).
- Matplotlib figures generated during a test are uploaded to S3 and embedded in the feedback.

#### `use_answer_as_expected_output`

When `true`, the `answer` argument (reference solution code) is executed with the same input/inject as each test, and its stdout is used as the expected output. The `expected_output` field on each test object is ignored.

```json
{
  "mode": "io_test",
  "use_answer_as_expected_output": true,
  "tests": [
    { "input": "5\n" },
    { "inject": {"n": 5} }
  ]
}
```

This avoids hardcoding expected outputs in params — useful when the LF UI code editor holds the reference solution.

Feedback tags produced per test: `pass`, `fail`, or `hidden_fail`. Global: `summary`, `error` (timeout / runtime error).

---

### Mode: `unit_test`

Append teacher-supplied test code to the student submission, then execute the combined script. The runner collects results from:

1. **Plain functions** — any top-level function named `test_*` is called; `AssertionError` = fail, other exception = error.
2. **`unittest.TestCase` subclasses** — discovered and run via `unittest.TestSuite`.
3. **Hypothesis tests** — `@given`-decorated `test_*` functions are supported transparently.

```json
{
  "mode": "unit_test",
  "test_code": "def test_square():\n    assert square(5) == 25\n"
}
```

- `test_code` must be non-empty; an empty string returns an `error` feedback item.
- Student `print()` calls do not pollute test results (stdout is discarded; results are passed via a temp JSON file).
- `is_correct` is `true` only when all tests pass and at least one test ran.

#### `use_answer_as_test_code`

When `true`, the `answer` argument is used as the test code instead of `params["test_code"]`. This is preferred when using the LF UI, whose params field is a plain JSON editor (poor for multiline code) while the answer field is a proper code editor.

```json
{
  "mode": "unit_test",
  "use_answer_as_test_code": true
}
```

Feedback tags produced per test: `pass`, `fail`. Global: `summary`, `error` (timeout / module-level crash / empty test_code).

---

### Response

```json
{
  "is_correct": true,
  "feedback":   "<markdown string with all feedback items>"
}
```

#### Feedback tags

| Tag | Meaning |
|-----|---------|
| `pass` | A test passed |
| `fail` | A test failed (visible) |
| `hidden_fail` | A hidden test failed (details suppressed) |
| `error` | Security violation, runtime error, or timeout |
| `output` | Demo-mode stdout + plots |
| `summary` | `N/M tests passed` line |

---

## `preview_function`

Called before evaluation. Parses the student code as an AST and checks for security violations.

### Blocked constructs

| Category | Blocked items |
|----------|--------------|
| Module imports | `os`, `sys`, `subprocess`, `socket`, `urllib`, `http`, `requests`, `shutil`, `pathlib`, `ftplib`, `smtplib`, `ctypes`, `multiprocessing`, `threading`, `importlib`, `pickle`, `builtins` |
| Builtins | `exec`, `eval`, `compile`, `open`, `__import__` |
| Attribute access | Any dunder (`__attr__`) attribute |

### Response

On clean code:
```json
{ "preview": { "feedback": "Valid Python syntax." } }
```

On syntax error:
```json
{ "preview": { "feedback": "SyntaxError: invalid syntax (line 3)" } }
```

On security violation:
```json
{ "preview": { "feedback": "Unsafe code detected:\n- import of 'os' is not allowed" } }
```

---

## Execution environment

- Python 3.12 subprocess with a **25-second timeout** (`_TIMEOUT`)
- `MPLBACKEND=Agg` and `MPLCONFIGDIR=/tmp` injected at runtime
- Matplotlib figures are captured via an injected preamble and uploaded to S3 under `evaluatePython/`
- AWS credentials must be present in the environment for plot uploads; upload failures are silently ignored

---

## Examples

### Demo mode

**Request**
```json
{
  "response": "for i in range(1, 4):\n    print(i ** 2)",
  "params": { "mode": "demo" }
}
```

**Response**
```json
{
  "is_correct": false,
  "feedback": "Output:\n```\n1\n4\n9\n```"
}
```

---

### io_test mode

**Request**
```json
{
  "response": "n = int(input())\nprint(n * n)",
  "params": {
    "mode": "io_test",
    "tests": [
      { "input": "5\n", "expected_output": "25\n" },
      { "input": "3\n", "expected_output": "9\n" }
    ]
  }
}
```

**Response**
```json
{
  "is_correct": true,
  "feedback": "Test 1: passed.\n\nInput:\n```\n5\n```\n\nOutput:\n```\n25\n```\n\nTest 2: passed. ...\n\n2/2 tests passed."
}
```

---

### unit_test mode

**Request**
```json
{
  "response": "def square(n): return n * n",
  "params": {
    "mode": "unit_test",
    "test_code": "def test_positive():\n    assert square(5) == 25\ndef test_zero():\n    assert square(0) == 0\n"
  }
}
```

**Response**
```json
{
  "is_correct": true,
  "feedback": "test_positive: passed.\n\ntest_zero: passed.\n\n2/2 tests passed."
}
```
