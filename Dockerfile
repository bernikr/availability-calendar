FROM ghcr.io/astral-sh/uv:debian

WORKDIR /app
ENV CONFIG_FILE=/config.yaml

# Save Version build argument as an environment variable
ARG VERSION
ENV VERSION=${VERSION:-"unspecified"}

ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=.python-version,target=.python-version \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
COPY pyproject.toml uv.lock .python-version /app/
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

EXPOSE 8000
WORKDIR /app/src
CMD ["uvicorn", "main:app", "--host=0.0.0.0", "--port=8000", "--proxy-headers", "--log-config=log_config.yaml"]
