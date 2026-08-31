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
# stdio (not ipc): the sandboxed worker runs inside an nsjail mount namespace,
# so the /tmp/eval.sock IPC rendezvous shimmy would otherwise use is fragile.
# stdio sidesteps it; lf_toolkit sends its logs to stderr, so stdout stays
# clean for the RPC framing.
ENV FUNCTION_RPC_TRANSPORT="stdio"

# --- Sandboxed execution of untrusted student code (shimmy + nsjail) ---
# Always on for this function. shimmy wraps the worker process -- and every
# `python` subprocess it spawns for a submission -- in an nsjail sandbox:
# unprivileged uid (nobody:nogroup), a minimal bind-mounted filesystem, and a
# seccomp syscall filter.
#
# DEPENDS ON THE BASE IMAGE shipping nsjail. shimmy provides the `--sandbox`
# feature but not the nsjail binary; `evaluation-function-base/python` currently
# copies only the shimmy binary, not `/usr/sbin/nsjail` or its shared libs
# (libprotobuf, libnl-route-3, libcap2). Until that is fixed upstream, a build
# of this image has shimmy fail to start (missing /usr/sbin/nsjail).
# Tracking: lambda-feedback/evaluation-function-base -- add nsjail to the image.
#
# RUN-TIME: the container must run with --privileged (or --cap-add SYS_ADMIN)
# so nsjail can create its namespaces (shimmy README, "Sandboxed Execution").
#
# Network stays enabled -- matplotlib plots are uploaded to S3 via boto3.
# Untrusted network/filesystem use is already rejected before execution by the
# AST gate in evaluation_function/security.py (check_code_safety).
#
# /tmp is a read-write bind of the container's own /tmp (not SANDBOX_TMPFS):
# nsjail's tmpfs defaults to 4 MiB, too small for matplotlib's font cache and
# plot output. No CPU/memory rlimits -- the RPC worker is long-lived and shared
# across requests, so a cumulative RLIMIT_CPU/AS would eventually kill it;
# per-run wall-clock limits live in evaluation.py (_TIMEOUT).
#
# The bind list is linux/x86_64 + Debian-specific (matches the CI/prod build
# platform). If the worker fails to start, drop SANDBOX_SECCOMP first.
ENV SANDBOX_ENABLED="true" \
    SANDBOX_SECCOMP="true" \
    SANDBOX_RO_BINDS="/usr:/lib:/lib64:/bin:/sbin:/etc:/app" \
    SANDBOX_RW_BINDS="/tmp"

ENV LOG_LEVEL="debug"
