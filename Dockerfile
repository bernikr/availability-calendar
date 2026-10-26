# SPDX-FileCopyrightText: 2025 bernikr <hi@berni.kr>
#
# SPDX-License-Identifier: MIT

FROM ghcr.io/astral-sh/uv:trixie-slim AS builder
SHELL ["sh", "-exc"]

ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PROJECT_ENVIRONMENT=/venv

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --preview-features frozen-lockfile

# prune unnecessary python files
RUN find /python -type d \( \
    -name "test" \
    -o -name "tests" \
    -o -name "idlelib" \
    -o -name "turtledemo" \
    -o -name "ensurepip" \
    \) -exec rm -rf {} + \
    && find /python (-name "*.a" -o -name "*.pyc" -o -name "*.pyo") -delete

COPY . /src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --directory /src

FROM gcr.io/distroless/cc-debian13:latest AS runtime

COPY --from=builder /python /python
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY log_config.yaml ./

ARG VERSION
ENV VERSION=${VERSION:-"unspecified"}
ENV CONFIG_FILE=/config.yaml

USER 65532:65532
EXPOSE 8000
HEALTHCHECK --start-period=30s --interval=30s --timeout=3s --retries=3 \
    CMD ["/venv/bin/python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/hc').read() == b'OK' else 1)"]
CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=8000", "--proxy-headers", "--log-config=log_config.yaml"]
