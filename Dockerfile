# The image of K-B: one image for every kb command, each run as its own container app or job on
# Azure Container Apps (issue #200). Base images are pinned by digest, tag in front (Dependabot
# updates both). Build: docker buildx build --platform linux/amd64 --tag k-b . (README).

# uv builds K-B with its own build backend: its version stays in the range of build-system.requires
# of pyproject.toml (uv_build>=0.11.13,<0.12.0).
FROM ghcr.io/astral-sh/uv:0.11.13@sha256:841c8e6fe30a8b07b4478d12d0c608cba6de66102d29d65d1cc423af86051563 AS uv

# Build stage: the virtual environment, from uv.lock, without the development dependencies.
FROM python:3.13-slim-trixie@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc AS builder
COPY --from=uv /uv /usr/local/bin/uv
# The Python of the base image, never one uv downloads; .pyc compiled now, since the final image
# cannot write them (owned by root).
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
# The base image ships its standard library without .pyc: compiled here, as root, or every start
# compiles them again in memory.
RUN python -m compileall -q /usr/local/lib/python3.13
# A fixed UID and GID, not root: the owner of /data, and of the files kb writes there in mode 0600
# (comment of 2026-10-16 on #200). /data is the data directory, where the volume is mounted.
RUN groupadd --gid 10001 kb \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin kb \
    && mkdir /data \
    && chown 10001:10001 /data
COPY --from=builder /app/.venv /app/.venv
# Defaults of the image, each changed by its variable at run time. In a container, stderr is the
# log (.claude/rules/conventions.md, rule 3). stdout is not buffered: a result or a metric line
# reaches the log at once, and is not lost when the container stops. KB_DATA_DIR has a value here,
# an exception to .claude/rules/poc.md, rule 2 (decision of Sabine of 2026-11-06, journal ADR).
ENV PATH="/app/.venv/bin:$PATH" \
    KB_DATA_DIR=/data \
    KB_LOG_TO_FILE=false \
    PYTHONUNBUFFERED=1
USER 10001:10001
# Exec form: kb is PID 1 and receives SIGTERM itself (.claude/rules/poc.md, rule 6). No init
# process: docker stop of kb serve-data is measured in the pull request of #200.
ENTRYPOINT ["/app/.venv/bin/kb"]
