# CPU image. Models are not baked in: mount a volume at /app/models so they download once.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

ARG EXTRAS=""
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project $EXTRAS

COPY app ./app

RUN useradd --create-home --uid 10001 speech && mkdir -p /app/models && chown speech /app/models
USER speech

ENV ICORE_MODELS_DIR=/app/models ICORE_STT_DEVICE=cpu ICORE_TTS_ENGINE=piper ICORE_PRELOAD_MODELS=true
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
