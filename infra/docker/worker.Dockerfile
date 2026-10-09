FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /service
COPY pyproject.toml ./
COPY worker ./worker
RUN pip install --upgrade pip && pip install . && useradd --create-home --uid 10001 appuser
USER appuser
CMD ["python", "-m", "worker.main"]
