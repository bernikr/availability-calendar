# SPDX-FileCopyrightText: 2025 bernikr <hi@berni.kr>
#
# SPDX-License-Identifier: MIT

FROM ghcr.io/astral-sh/uv:alpine AS builder
SHELL ["sh", "-exc"]

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PROJECT_ENVIRONMENT=/venv

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY . /src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --directory /src

FROM alpine:latest AS runtime

WORKDIR /app
RUN adduser -D -u 1000 nonroot
USER 1000:1000

COPY --from=builder /python /python
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY log_config.yaml ./

ARG VERSION
ENV VERSION=${VERSION:-"unspecified"}
ENV CONFIG_FILE=/config.yaml
EXPOSE 8000
HEALTHCHECK --start-period=30s CMD test "$(wget -qO- -T 3 http://127.0.0.1:8000/hc)" = "OK"
CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=8000", "--proxy-headers", "--log-config=log_config.yaml"]
