# The image of K-B: one image for every kb command, each run as its own container app or job on
# Azure Container Apps (issue #200). Base images are pinned by digest, tag in front (Dependabot
# updates both). Build: docker buildx build --platform linux/amd64 --tag k-b . (README).

FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

# Build stage: the virtual environment, from uv.lock, without the development dependencies.
FROM python:3.13-slim-trixie@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc AS builder
COPY --from=uv /uv /usr/local/bin/uv
# The Python of the base image, never one uv downloads; .pyc compiled now, since the final image
# cannot write them (owned by root, read-only file system on Azure).
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1
WORKDIR /app
# The dependencies first, in their own layer: a change of src/ alone does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-editable
# K-B itself, installed as a package (not editable): the final image needs no src/. README.md is
# the readme of pyproject.toml, which the build backend reads.
COPY README.md ./
COPY src/ src/
RUN uv sync --locked --no-dev --no-editable

# Final stage: the same base, the virtual environment only, without uv.
FROM python:3.13-slim-trixie@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc
# A fixed UID and GID, not root: the owner of /data, and of the files kb writes there in mode 0600
# (comment of 2026-10-16 on #200). /data is the data directory, where Azure mounts its volume.
RUN groupadd --system --gid 10001 kb \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin kb \
    && mkdir /data \
    && chown 10001:10001 /data
COPY --from=builder /app/.venv /app/.venv
# Defaults of the image, each changed by its variable at run time. In a container, stderr is the
# log (.claude/rules/conventions.md, rule 3). stdout is not buffered: a result or a metric line
# reaches the log at once, and is not lost when the container stops.
ENV PATH="/app/.venv/bin:$PATH" \
    KB_DATA_DIR=/data \
    KB_LOG_TO_FILE=false \
    PYTHONUNBUFFERED=1
USER 10001:10001
# Exec form: kb is PID 1 and receives SIGTERM itself (.claude/rules/poc.md, rule 6). No init
# process: docker stop of kb serve-data is measured in the pull request of #200.
ENTRYPOINT ["/app/.venv/bin/kb"]
