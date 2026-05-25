# evaluatePython

A [Lambda Feedback](https://lambda-feedback.github.io/user-documentation/) evaluation function that executes student Python code submissions in a secure sandbox, runs them against test cases, and returns structured formative feedback. Deployed as a Docker container on the Lambda Feedback platform.

## Deployment

[![Create Release Request](https://img.shields.io/badge/Create%20Release%20Request-blue?style=for-the-badge)](https://github.com/lambda-feedback/evaluatePython/issues/new?template=release-request.yml)

Push to `main` triggers GitHub Actions which automatically builds and deploys to Lambda Feedback. See [`.github/workflows/`](.github/workflows/) for CI/CD configuration.

## Usage

### Run the Docker Image

```bash
docker run -it --rm -p 8080:8080 ghcr.io/lambda-feedback/evaluatepython:latest
```

The image includes [Shimmy](https://github.com/lambda-feedback/shimmy), which listens for HTTP requests on port 8080 and forwards them to the evaluation function.

### Evaluation Modes

The function supports three modes, set via `params.mode`.

**`demo`** — run student code and show output (no pass/fail):

```json
{
  "response": "print(5 * 5)",
  "params": { "mode": "demo" }
}
```

**`io_test`** — compare stdout against expected output for each test case:

```json
{
  "response": "n = int(input())\nprint(n * n)",
  "params": {
    "mode": "io_test",
    "tests": [
      { "input": "5\n", "expected_output": "25\n" },
      { "input": "3\n", "expected_output": "9\n", "hidden": true }
    ]
  }
}
```

**`unit_test`** — run student code then execute `test_*` functions or `unittest.TestCase` subclasses (including Hypothesis tests):

```json
{
  "response": "def square(n): return n * n",
  "params": {
    "mode": "unit_test",
    "test_code": "def test_positive():\n    assert square(5) == 25\ndef test_zero():\n    assert square(0) == 0\n"
  }
}
```

## Development

### Prerequisites

- [Python 3.12+](https://www.python.org)
- [Poetry](https://python-poetry.org)
- [Docker](https://docs.docker.com/get-docker/) (for container builds)

### Repository Structure

```
evaluation_function/main.py             # IPC server entry point
evaluation_function/evaluation.py       # core evaluation pipeline (all three modes)
evaluation_function/preview.py          # AST-based security validator
evaluation_function/dev.py              # CLI wrapper for local testing
evaluation_function/evaluation_test.py  # integration tests
evaluation_function/preview_test.py     # preview/security tests
config.json                             # deployment configuration
```

### Setup

```bash
poetry install
```

### Local Testing

The `dev.py` script calls the evaluation function directly (no Docker required). It defaults to `demo` mode if no params are supplied:

```bash
# demo mode (default)
python -m evaluation_function.dev "print(5 * 5)"

# io_test mode
python -m evaluation_function.dev "print(int(input())**2)" "" \
  '{"mode":"io_test","tests":[{"input":"5\n","expected_output":"25\n"}]}'

# unit_test mode
python -m evaluation_function.dev "def square(n): return n*n" "" \
  '{"mode":"unit_test","test_code":"def test_sq():\n    assert square(3)==9\n"}'
```

### Running Tests

```bash
pytest
```

### Linting

```bash
# Critical errors (fail CI)
flake8 ./evaluation_function --count --select=E9,F63,F7,F82 --show-source --statistics
# Style/complexity (informational)
flake8 ./evaluation_function --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
```

### Building the Docker Image

```bash
docker build -t evaluatepython .
# Cross-platform (CI uses linux/x86_64):
docker build --platform=linux/x86_64 -t evaluatepython .
```

### Running the Docker Image

```bash
docker run -it --rm -p 8080:8080 evaluatepython
```

## Deployment to Lambda Feedback

The function name is declared in [`config.json`](config.json) as `"evaluatePython"` (lowerCamelCase). Pushing to `main` triggers automated deployment via GitHub Actions.

> [!IMPORTANT]
> The evaluation function name must be unique within the Lambda Feedback organization and must be in `lowerCamelCase`.

## Troubleshooting

### Containerized Function Fails to Start

- **Run-time dependencies**: ensure all packages are in `pyproject.toml` and installed via `poetry install` in the Dockerfile.
- **Architecture**: some packages are platform-specific. Build with `--platform=linux/x86_64` to match the CI/production environment.
- **Standalone check**: run the function directly inside the container to isolate startup errors:

```bash
docker run -it --rm evaluatepython python -m evaluation_function.main
```

### Pulling Changes from the Template Repository

```bash
git remote add template https://github.com/lambda-feedback/evaluation-function-boilerplate-python.git
git fetch --all
git merge template/main --allow-unrelated-histories
```

> [!WARNING]
> Resolve conflicts carefully — template updates may overwrite evaluatePython-specific code.
