# SPDX-FileCopyrightText: 2025 bernikr <hi@berni.kr>
#
# SPDX-License-Identifier: MIT

FROM ghcr.io/astral-sh/uv:alpine AS env-builder
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

FROM env-builder AS app-builder

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=.,target=/src  \
    uv sync --locked --no-editable --directory /src

FROM alpine:latest AS runtime

RUN addgroup -g 999 -S nonroot \
    && adduser -u 999 -S -G nonroot nonroot

COPY --from=env-builder /python /python
COPY --from=env-builder --chown=nonroot:nonroot /venv /venv
COPY --from=app-builder --chown=nonroot:nonroot /venv /venv
ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER nonroot

COPY --chown=nonroot:nonroot log_config.yaml ./

ARG VERSION
ENV VERSION=${VERSION:-"unspecified"}
ENV CONFIG_FILE=/config.yaml
EXPOSE 8000
HEALTHCHECK --start-period=30s CMD [ "$( wget -qO - http://127.0.0.1:8000/hc )" = OK ]
CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=8000", "--proxy-headers", "--log-config=log_config.yaml"]
