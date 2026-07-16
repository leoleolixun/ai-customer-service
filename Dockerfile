FROM node:22-alpine AS frontend

WORKDIR /src

COPY package.json package-lock.json ./
COPY tsconfig.base.json ./
COPY apps/admin/package.json ./apps/admin/package.json
COPY apps/demo/package.json ./apps/demo/package.json
COPY packages/sdk/package.json ./packages/sdk/package.json
COPY packages/widget/package.json ./packages/widget/package.json
RUN npm ci

COPY apps/admin ./apps/admin
COPY packages/sdk ./packages/sdk
COPY packages/widget ./packages/widget
RUN npm run build --workspace @ai-support/sdk \
    && npm run build --workspace @ai-support/widget \
    && npm run build --workspace @ai-support/admin


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/tmp

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY eval ./eval
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./
COPY --from=frontend /src/apps/admin/dist ./apps/admin/dist
COPY --from=frontend /src/packages/sdk/dist ./packages/sdk/dist
COPY --from=frontend /src/packages/widget/dist ./packages/widget/dist
RUN uv sync --frozen --no-dev

USER 10001:10001

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
