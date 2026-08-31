FROM ghcr.io/lambda-feedback/evaluation-function-base/python:3.12 AS builder

RUN pip install poetry==1.8.3

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

COPY pyproject.toml poetry.lock ./

RUN --mount=type=cache,target=$POETRY_CACHE_DIR \
    poetry install --without dev --no-root

FROM ghcr.io/lambda-feedback/evaluation-function-base/python:3.12

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Precompile python files for faster startup
RUN python -m compileall -q .

# Copy the evaluation function to the app directory
COPY evaluation_function ./evaluation_function

# Command to start the evaluation function with
ENV FUNCTION_COMMAND="python"

# Args to start the evaluation function with
ENV FUNCTION_ARGS="-m,evaluation_function.main"

# The transport to use for the RPC server.
# stdio (not ipc): the worker runs inside an nsjail mount namespace with a
# private tmpfs /tmp (see the sandbox settings below), so a host unix-socket
# rendezvous at /tmp/eval.sock would be unreachable. shimmy's sandbox is
# designed around stdio; lf_toolkit routes its logs to stderr, keeping stdout
# clean for the RPC framing.
ENV FUNCTION_RPC_TRANSPORT="stdio"

# --- Sandboxed execution of untrusted student code (shimmy + nsjail) ---
# shimmy wraps the worker process -- and every `python` subprocess it spawns to
# run a submission -- in an nsjail sandbox: unprivileged uid (nobody:nogroup),
# a minimal bind-mounted view of the filesystem, and seccomp syscall filtering.
#
# Run-time requirements (cannot be expressed in the image):
#   * the container must run with --privileged (or --cap-add SYS_ADMIN) so
#     nsjail can create its namespaces -- see the shimmy README, "Sandboxed
#     Execution". Without it the worker will not boot.
#   * nsjail must exist at /usr/sbin/nsjail (provided by the base image's
#     shimmy stage).
# If the worker fails to start, drop SANDBOX_SECCOMP first, then widen
# SANDBOX_RO_BINDS (the list is linux/x86_64 + Debian-specific).
#
# Network is deliberately left enabled -- the function uploads matplotlib
# plots to S3 via boto3. Untrusted network/filesystem use is blocked one layer
# up, at the AST gate in evaluation_function/security.py (check_code_safety).
#
# No CPU/memory rlimits here: the RPC worker is long-lived and shared across
# requests, so a cumulative RLIMIT_CPU / RLIMIT_AS would eventually kill it.
# Per-execution wall-clock limits are enforced in evaluation.py (_TIMEOUT).
ENV SANDBOX_ENABLED="true" \
    SANDBOX_SECCOMP="true" \
    SANDBOX_RO_BINDS="/usr:/lib:/lib64:/bin:/sbin:/etc:/app" \
    SANDBOX_TMPFS="/tmp"

ENV LOG_LEVEL="debug"
