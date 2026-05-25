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
2. For each test case (or once if none):
   - Inject matplotlib figure-capture preamble
   - Execute student code in a subprocess with 25-second timeout (`_TIMEOUT = 25`)
   - Compare stdout against `expected_output`
3. Upload any captured matplotlib figures to S3 (`_UPLOAD_FOLDER = "evaluatePython"`)
4. Return a `Result` with feedback tags: `pass`, `fail`, `hidden_pass`, `hidden_fail`, `error`, `output`, `summary`

### Request shape

```python
# params["tests"] is optional
{
    "tests": [
        {
            "input": "5\n",           # stdin fed to student code
            "expected_output": "25\n", # expected stdout
            "hidden": False            # if True, suppress expected/actual in feedback
        }
    ]
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

# Manual local testing
python -m evaluation_function.dev "print(5*5)" "25"
# With params JSON as third argument:
python -m evaluation_function.dev "print(5*5)" "" '{"tests":[{"input":"","expected_output":"25\n"}]}'

# Docker build
docker build -t evaluatepython .
# Cross-platform (CI uses linux/x86_64):
docker build --platform=linux/x86_64 .

# Run the server locally (port 8080)
docker run -it --rm -p 8080:8080 evaluatepython
```

## Tests

Two test files, run with `pytest`:

- `evaluation_function/evaluation_test.py` — integration tests covering: all pass, partial fail, hidden test failure, runtime error, no test cases
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
