# The engine's production image: CPU only, no PyTorch, no GPU libraries (tech.md). Built from the
# repository root so the uv workspace lockfile pins every dependency.
FROM ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 AS uv

FROM python:3.13-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/engine
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY services/engine/pyproject.toml services/engine/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package orrery-engine
COPY services/engine services/engine
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package orrery-engine

FROM python:3.13-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
RUN useradd --system --uid 10002 --home-dir /nonexistent --shell /usr/sbin/nologin engine
COPY --from=build /opt/engine /opt/engine
ENV PATH=/opt/engine/bin:$PATH PYTHONUNBUFFERED=1
USER engine
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["python", "-m", "orrery_engine"]
