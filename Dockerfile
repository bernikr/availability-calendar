FROM ghcr.io/astral-sh/uv:python3.13-alpine AS env-builder
SHELL ["sh", "-exc"]

ENV UV_COMPILE_BYTECODE=1 \ 
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/venv

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv venv /venv

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

FROM env-builder AS app-builder

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=.,target=/src,rw  \
    uv sync --locked --no-dev --no-editable --directory /src

FROM python:3.13-alpine

COPY --from=env-builder /venv /venv
COPY --from=app-builder /venv /venv
ENV PATH="/venv/bin:$PATH"

COPY log_config.yaml ./

ARG VERSION
ENV VERSION=${VERSION:-"unspecified"}
ENV CONFIG_FILE=/config.yaml
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=8000", "--proxy-headers", "--log-config=log_config.yaml"]
