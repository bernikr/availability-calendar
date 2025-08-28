FROM ghcr.io/astral-sh/uv:debian AS builder
SHELL ["sh", "-exc"]

ENV UV_COMPILE_BYTECODE=1 \ 
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed\
    UV_PROJECT_ENVIRONMENT=/app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv venv /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . /src
WORKDIR /src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM debian:stable-slim
SHELL ["sh", "-exc"]

RUN <<EOT
apt-get update -qy
apt-get install -qyy \
    -o APT::Install-Recommends=false \
    -o APT::Install-Suggests=false \
    ca-certificates
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOT

COPY --from=builder --chown=python:python /python /python
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/bin:$PATH"

COPY log_config.yaml ./

ARG VERSION
ENV VERSION=${VERSION:-"unspecified"}
ENV CONFIG_FILE=/config.yaml
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=8000", "--proxy-headers", "--log-config=log_config.yaml"]
