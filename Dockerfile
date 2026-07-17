# Imagen para Cloud Run — corre FastAPI con uvicorn.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY web ./web

# Cloud Run inyecta la variable PORT (por defecto 8080). Uvicorn debe escuchar ahí.
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
