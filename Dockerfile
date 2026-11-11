FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.9.4 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY my-dash-app ./my-dash-app
COPY scripts/vercel_start.py ./scripts/vercel_start.py
RUN useradd --create-home appuser
USER appuser
# PORT is the Vercel-injected listen port; 8050 is the local/default fallback.
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PORT=8050
EXPOSE 8050
CMD ["python", "scripts/vercel_start.py"]
