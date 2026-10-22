FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /service
COPY apps/worker/pyproject.toml ./
COPY apps/worker/worker ./worker
COPY model-artifacts/isolation_forest.v1.joblib /models/isolation_forest.v1.joblib
COPY model-artifacts/isolation_forest.v1.metadata.json /models/isolation_forest.v1.metadata.json
RUN pip install --upgrade pip && pip install . && useradd --create-home --uid 10001 appuser
USER appuser
CMD ["python", "-m", "worker.main"]
