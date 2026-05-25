# evaluatePython

A [Lambda Feedback](https://lambda-feedback.github.io/user-documentation/) evaluation function that executes student Python code submissions, runs them against test cases, and returns structured formative feedback. Deployed as a Docker container on the Lambda Feedback platform.

## Architecture

All source lives in `evaluation_function/`:

| File | Role |
|------|------|
| `main.py` | IPC server entry point; registers `evaluation_function` and `preview_function` with lf_toolkit |
| `evaluation.py` | Core evaluation pipeline: security check → subprocess execution → output comparison → S3 plot upload → structured feedback |
| `preview.py` | AST-based pre-execution security validator (`_SecurityVisitor`) |
| `dev.py` | CLI wrapper for local manual testing |

### Evaluation pipeline (`evaluation.py`)

1. Run AST security check on student code
2. Dispatch by `params["mode"]` (required):
   - **`demo`**: execute code with no stdin; return stdout/plots as `output` feedback (no pass/fail)
   - **`io_test`**: for each test in `params["tests"]`, execute with `test["input"]` as stdin and compare stdout against `test["expected_output"]`; upload matplotlib plots on pass or fail
   - **`unit_test`**: append `params["test_code"]` + unit-runner harness to student code; execute once; parse JSON results; supports plain `test_*` functions, `unittest.TestCase` subclasses, and Hypothesis-based tests
3. Upload any captured matplotlib figures to S3 (`_UPLOAD_FOLDER = "evaluatePython"`)
4. Return a `Result` with feedback tags: `pass`, `fail`, `hidden_fail`, `error`, `output`, `summary`

### Request shape

```python
# params["mode"] is required

# demo — run and show output, no pass/fail
{"mode": "demo"}

# io_test — run against stdin/stdout test cases
{
    "mode": "io_test",
    "tests": [
        {
            "input": "5\n",            # stdin fed to student code
            "expected_output": "25\n", # expected stdout
            "hidden": False            # True = suppress input/output in feedback
        }
    ]
}

# unit_test — run student code then execute test functions/TestCases
{
    "mode": "unit_test",
    "test_code": "def test_square():\n    assert square(5) == 25\n"
}
```

### Security model (`preview.py`)

`_SecurityVisitor` walks the AST before any execution and blocks:

- **Modules**: `os`, `sys`, `subprocess`, `socket`, `urllib`, `http`, `requests`, `shutil`, `pathlib`, `ftplib`, `smtplib`, `ctypes`, `multiprocessing`, `threading`, `importlib`, `pickle`, `builtins`
- **Builtins**: `exec`, `eval`, `compile`, `open`, `__import__`, `input`
- **Dunder attribute access**: any `__attr__` style attribute

## Key commands

```bash
# Install dependencies
poetry install

# Run all tests
pytest

# Lint (critical errors fail CI; style/complexity are informational)
flake8 ./evaluation_function --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 ./evaluation_function --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

# Manual local testing (defaults to demo mode)
python -m evaluation_function.dev "print(5*5)"
# io_test mode with params JSON:
python -m evaluation_function.dev "print(5*5)" "" '{"mode":"io_test","tests":[{"input":"","expected_output":"25\n"}]}'
# unit_test mode:
python -m evaluation_function.dev "def sq(n): return n*n" "" '{"mode":"unit_test","test_code":"def test_sq():\n    assert sq(3)==9\n"}'

# Docker build
docker build -t evaluatepython .
# Cross-platform (CI uses linux/x86_64):
docker build --platform=linux/x86_64 .

# Run the server locally (port 8080)
docker run -it --rm -p 8080:8080 evaluatepython
```

## Tests

Two test files, run with `pytest`:

- `evaluation_function/evaluation_test.py` — integration tests covering: all modes (demo, io_test, unit_test), all pass, partial fail, hidden test failure, runtime error, matplotlib plot capture, Hypothesis support
- `evaluation_function/preview_test.py` — unit tests covering: valid Python, syntax errors, dangerous imports, dangerous builtins, dunder access

CI runs on Python 3.12 and uploads JUnit XML results (`.github/workflows/test-lint.yml`).

## Environment

| Variable | Value | Purpose |
|----------|-------|---------|
| `VIRTUAL_ENV` | `/app/.venv` | Set in Dockerfile |
| `MPLBACKEND` | `Agg` | Set at subprocess runtime to suppress GUI |
| `FUNCTION_COMMAND` | `python` | lf_toolkit runner |
| `FUNCTION_ARGS` | `-m,evaluation_function.main` | lf_toolkit runner |
| `FUNCTION_RPC_TRANSPORT` | `ipc` | lf_toolkit transport |
| `LOG_LEVEL` | `debug` | Logging verbosity |
| `AWS_*` / boto3 credentials | Runtime env | Required for S3 plot uploads |

Dependencies managed via Poetry; `.venv` is created in-project (`poetry.toml`).

## Deployment

- Push to `main` triggers GitHub Actions (`.github/workflows/`) which builds and deploys to Lambda Feedback automatically
- The function name is declared in `config.json` as `EvaluationFunctionName: "evaluatePython"` (lowerCamelCase)
- The base Docker image is `ghcr.io/lambda-feedback/evaluation-function-base/python:test-sandbox-3.12`
