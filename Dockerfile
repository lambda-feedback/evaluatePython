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

# How lf_toolkit's runner launches the worker.
ENV FUNCTION_COMMAND="python" \
    FUNCTION_ARGS="-m,evaluation_function.main"

# RPC transport: stdio, not ipc. The sandboxed worker runs in an nsjail mount
# namespace where the /tmp/eval.sock IPC rendezvous is fragile; stdio sidesteps
# it. lf_toolkit logs to stderr, so stdout stays clean for the RPC framing.
ENV FUNCTION_RPC_TRANSPORT="stdio"

# --- Sandboxed execution of untrusted student code (shimmy + nsjail) ---
# Always on. shimmy wraps the worker -- and every `python` subprocess it spawns
# per submission -- in nsjail: run as nobody, a read-only bind-mounted rootfs,
# namespace isolation. Defence in depth on top of the AST gate in
# evaluation_function/security.py, which rejects unsafe imports/builtins before
# any code runs.
#
# Requires a base image that ships /usr/sbin/nsjail AND a shimmy build with the
# sandbox fixes (--keep_env, PATH resolution of FUNCTION_COMMAND, --cwd fallback,
# kafel seccomp, namespace toggles). With stock shimmy the worker fails to start.
#
# Run-time: the container must run --privileged (or --cap-add SYS_ADMIN) -- nsjail
# needs CAP_SYS_ADMIN for unshare(CLONE_NEWNS). Running as uid 0, nsjail's "auto"
# userns handling then drops CLONE_NEWUSER (a nested userns' unprivileged gid_map
# write fails); --user still drops the worker to nobody. Network stays up so
# matplotlib plots can be uploaded to object storage (see below).
#
# SANDBOX_RO_BINDS / _RW_BINDS: shimmy splits these env vars on COMMA. Bind "/"
# read-only (whole rootfs -- arch-independent, where an explicit list would need
# /lib64 only on x86_64, and a missing bind source is fatal to nsjail), then
# re-mount /tmp read-write. Not SANDBOX_TMPFS: nsjail's tmpfs defaults to 4 MiB,
# too small for matplotlib's font cache + plot output.
#
# SANDBOX_DISABLE_CLONE_NEWPID: a nested PID namespace breaks worker thread
# creation on some hosts ("pthread_create ... Invalid argument"); the mount and
# user namespaces still isolate the filesystem and privileges.
#
# Network stays up so matplotlib plots (see evaluation.py::_upload_plots) can be
# pushed to object storage. On GCP we use lf_toolkit's GCS backend
# (IMAGE_UPLOAD_BACKEND=gcs): the worker authenticates with Application Default
# Credentials via the Cloud Run runtime service account -- no static keys -- and
# needs GCS_BUCKET set on the service (staging/prod differ). To fall back to S3,
# override IMAGE_UPLOAD_BACKEND=s3 on the service and set S3_BUCKET_URI / AWS_*.
#
# No seccomp (nsjail has no built-in default policy; the fixed shimmy takes a
# kafel policy via SANDBOX_SECCOMP_STRING / _POLICY_FILE if wanted) and no
# rlimits (the RPC worker is long-lived and shared; per-run limits are the
# _TIMEOUT in evaluation.py).
ENV SANDBOX_ENABLED="true" \
    SANDBOX_RO_BINDS="/" \
    SANDBOX_RW_BINDS="/tmp" \
    SANDBOX_DISABLE_CLONE_NEWPID="true"

# Plot upload backend (lf_toolkit). GCS_BUCKET is supplied per-environment on the
# Cloud Run service.
ENV IMAGE_UPLOAD_BACKEND="gcs"

ENV LOG_LEVEL="debug"
