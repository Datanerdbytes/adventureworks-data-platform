FROM node:22-bookworm-slim AS auth-build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY auth_frontend ./auth_frontend
COPY scripts/build-auth.mjs ./scripts/build-auth.mjs
RUN npm run build:auth

FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.9.4 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY my-dash-app ./my-dash-app
COPY --from=auth-build /build/my-dash-app/assets/auth.js ./my-dash-app/assets/auth.js
RUN useradd --create-home appuser
USER appuser
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
EXPOSE 8050
CMD ["gunicorn", "--chdir", "my-dash-app", "--bind", "0.0.0.0:8050", "--workers", "2", "--timeout", "120", "app:server"]
