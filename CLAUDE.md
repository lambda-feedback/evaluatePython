# evaluatePython

A [Lambda Feedback](https://lambda-feedback.github.io/user-documentation/) evaluation function that executes student Python code submissions, runs them against test cases, and returns structured formative feedback. Deployed as a Docker container on the Lambda Feedback platform.

## Architecture

All source lives in `evaluation_function/`:

| File | Role |
|------|------|
| `main.py` | IPC server entry point; registers `evaluation_function` and `preview_function` with lf_toolkit |
| `evaluation.py` | Core evaluation pipeline: security check → subprocess execution → output comparison → plot upload (GCS/S3 via lf_toolkit) → structured feedback |
| `preview.py` | AST-based pre-execution security validator (`_SecurityVisitor`) |
| `s3_files.py` | Downloads `params["answer_files"]`/`params["response_files"]` objects into the per-request working directory |
| `dev.py` | CLI wrapper for local manual testing |

### Evaluation pipeline (`evaluation.py`)

1. Run AST security check on student code
2. Gather file specs from params via `_collect_file_specs`: `params["answer_files"]` (teacher, plus legacy `params["files"]`) and `params["response_files"]` (student); teacher files win on a name clash. The response and answer are plain code strings. If any files are listed, download the listed objects once into a per-request working directory (see `s3_files.py`), used as the subprocess `cwd` for every run in this request
3. Dispatch by `params["mode"]` (required):
   - **`demo`**: execute code with no stdin; return stdout/plots as `output` feedback (no pass/fail)
   - **`io_test`**: for each test in `params["tests"]`, execute with `test["input"]` as stdin and compare stdout against `test["expected_output"]`; upload matplotlib plots on pass or fail
   - **`unit_test`**: append `params["test_code"]` + unit-runner harness to student code; execute once; parse JSON results; supports plain `test_*` functions, `unittest.TestCase` subclasses, and Hypothesis-based tests
4. Upload any captured matplotlib figures via `lf_toolkit` `upload_image` (`_UPLOAD_FOLDER = "evaluatePython"`); backend is GCS or S3 per `IMAGE_UPLOAD_BACKEND`
5. Return a `Result` with feedback tags: `pass`, `fail`, `hidden_fail`, `error`, `output`, `summary`

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
            # stdin-based: student code calls input()
            "input": "5\n",            # stdin fed to student code
            "expected_output": "25\n", # expected stdout
            "hidden": False            # True = suppress input/output in feedback
        },
        {
            # inject-based: variables are set before student code runs (no input() needed)
            "inject": {"n": 5},        # dict of {variable_name: value} to inject
            "expected_output": "25\n",
            "hidden": False
        }
    ]
}

# io_test — expected outputs derived from answer code (preferred when using LF UI)
# Write the reference solution in the answer field; only provide inputs in tests.
# The system runs the answer code with each test's input to compute expected output.
{
    "mode": "io_test",
    "use_answer_as_expected_output": True,   # runs answer code to get expected output
    "tests": [
        {"input": "5\n"},
        {"inject": {"n": 5}}
    ]
}

# unit_test — run student code then execute test functions/TestCases
{
    "mode": "unit_test",
    "test_code": "def test_square():\n    assert square(5) == 25\n"
}

# unit_test — test code in the answer field (preferred when using LF UI)
# The LF params editor handles multiline code poorly; the answer field is a
# proper code editor. Set use_answer_as_test_code=True and write test code
# in the response area's answer field instead of params["test_code"].
{
    "mode": "unit_test",
    "use_answer_as_test_code": True   # reads test code from the answer argument
}

# pep8_feedback — optional, works with all modes
# Adds a "style" feedback item with PEP8 violations from the student's code.
# True uses the default curated rule set; a list overrides with specific codes.
# Default rules: E111 (indentation), E225 (whitespace around operator),
#   E231 (whitespace after comma/colon), E303 (too many blank lines),
#   W191 (tabs), E711 (== None), E712 (== True/False).
{
    "mode": "io_test",
    "pep8_feedback": True,              # use default curated rules
    # or:
    "pep8_feedback": ["E225", "E231"],  # custom rule list
    "tests": [...]
}

# answer_files / response_files — optional, work with all modes
# answer_files: the teacher's files, saved in the response area's gradeParams.
# response_files: the student's uploads, sent with each check as additionalParams.
# params["files"] is still accepted as a legacy alias for answer_files.
# All listed files are downloaded into one per-request working directory
# (the subprocess's cwd) before student code runs, given a pre-signed or
# public HTTPS URL per file (fetched directly with a GET — no AWS
# credentials needed here). On a name clash the teacher's file wins. Entries
# may be dicts or JSON strings of dicts. Data files can be read with
# open()/pandas.read_csv()/etc.; .py files are importable since they're
# co-located with the generated script. The same files are also available
# to the answer code when use_answer_as_expected_output/use_answer_as_test_code is set.
{
    "mode": "demo",
    "answer_files": [
        {"url": "https://.../data.csv?X-Amz-Signature=...", "name": "data.csv"},
        {"url": "https://.../helper.py?X-Amz-Signature=...", "name": "helper.py"},
    ],
    "response_files": [
        {"url": "https://.../mine.csv?X-Amz-Signature=...", "name": "mine.csv"},
    ]
}
```

### Security model (`preview.py`)

`_SecurityVisitor` walks the AST and blocks:

- **Modules**: `os`, `sys`, `subprocess`, `socket`, `urllib`, `http`, `requests`, `shutil`, `ftplib`, `smtplib`, `ctypes`, `multiprocessing`, `threading`, `importlib`, `pickle`, `builtins`
- **Builtins**: `exec`, `eval`, `compile`, `__import__`
- **Dunder attribute access**: any `__attr__` style attribute

`open`/`pathlib` are intentionally **not** blocked here — they're needed to read files loaded via `params["answer_files"]`/`params["response_files"]` (see above). **Important caveat**: `preview_function` (this check) and `evaluation_function` (actual grading) are registered as two independent RPC methods in `main.py`; `evaluation.py` never calls `preview.py`. This check only powers editor-time linting feedback — it does not gate what code can do at grading time. The real, load-bearing control for file access is a runtime-injected restricted `open`/`io.open` in `evaluation.py`'s subprocess preamble (`_safe_open`), which blocks *write* access to anything inside the per-run files directory. It is not a hard sandbox boundary — since `os`/`subprocess` remain fully importable and runnable at grading time regardless of this feature, a student can bypass file restrictions entirely via `os`. Treat this as scoping the intended file-access path, not as isolation.

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

# Run the server locally (port 8080).
# --privileged is required: the image enables shimmy's nsjail sandbox
# (SANDBOX_ENABLED=true), and nsjail needs it to create namespaces.
docker run -it --rm --privileged -p 8080:8080 evaluatepython
```

## Tests

Three test files, run with `pytest`:

- `evaluation_function/evaluation_test.py` — integration tests covering: all modes (demo, io_test, unit_test), all pass, partial fail, hidden test failure, runtime error, matplotlib plot capture, Hypothesis support, the pre-execution security gate
- `evaluation_function/preview_test.py` — unit tests covering: valid Python, syntax errors, dangerous imports, dangerous builtins, dunder access
- `evaluation_function/security_test.py` — unit tests for `check_code_safety` (the shared AST blocklist used by both `preview_function` and `evaluation_function`)

CI runs on Python 3.12 and uploads JUnit XML results (`.github/workflows/test-lint.yml`).

## Environment

| Variable | Value | Purpose |
|----------|-------|---------|
| `VIRTUAL_ENV` | `/app/.venv` | Set in Dockerfile |
| `MPLBACKEND` | `Agg` | Set at subprocess runtime to suppress GUI |
| `FUNCTION_COMMAND` | `python` | lf_toolkit runner |
| `FUNCTION_ARGS` | `-m,evaluation_function.main` | lf_toolkit runner |
| `FUNCTION_RPC_TRANSPORT` | `stdio` | shimmy↔worker transport (stdio so it survives the sandbox mount namespace) |
| `LOG_LEVEL` | `debug` | Logging verbosity |
| `IMAGE_UPLOAD_BACKEND` | `gcs` | Plot upload backend in lf_toolkit (`gcs` set in Dockerfile; override to `s3` on the service to use AWS) |
| `GCS_BUCKET` | Runtime env | Target bucket for matplotlib plot uploads; set per-environment on the Cloud Run service. Auth is via the runtime service account (ADC) — no keys |
| `AWS_*` / `S3_BUCKET_URI` | Runtime env | Only for the legacy S3 plot-upload backend (`IMAGE_UPLOAD_BACKEND=s3`). Not needed for `answer_files` / `response_files` downloads — those are plain HTTPS GETs from a pre-signed/public URL |
| `SANDBOX_ENABLED` | `true` | Wrap the worker in shimmy's nsjail sandbox (needs `--privileged` at run time) |
| `SANDBOX_SECCOMP` | `true` | nsjail seccomp syscall filter |
| `SANDBOX_RO_BINDS` | `/usr:/lib:/lib64:/bin:/sbin:/etc:/app` | Read-only bind mounts visible inside the jail |
| `SANDBOX_TMPFS` | `/tmp` | Writable tmpfs inside the jail (student scripts, plot dirs, MPLCONFIGDIR) |

Dependencies managed via Poetry; `.venv` is created in-project (`poetry.toml`).

## Deployment

- Push to `main` triggers GitHub Actions (`.github/workflows/`) which builds and deploys to Lambda Feedback automatically
- The function name is declared in `config.json` as `EvaluationFunctionName: "evaluatePython"` (lowerCamelCase)
- The base Docker image is `ghcr.io/lambda-feedback/evaluation-function-base/python:3.12` (bundles shimmy + nsjail; sandboxing is enabled via the `SANDBOX_*` env vars in the Dockerfile, not by the base tag)
