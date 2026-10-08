FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN useradd --uid 1000 app \
    && mkdir output \
    && chown app:app output

COPY bank_master_creator.py ./

USER app

# 引数をそのまま渡せるようにします (例: docker compose run --rm app --help)。
ENTRYPOINT ["python", "bank_master_creator.py"]

FROM runtime AS dev

USER root

COPY pyproject.toml ./
RUN pip install --no-cache-dir --group dev \
    && chown app:app /app

COPY tests ./tests

USER app

ENTRYPOINT []
CMD ["sh", "-c", "ruff check . && ruff format --check . && pytest"]
