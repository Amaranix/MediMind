# Image du backend MediMind. Contexte de build : racine du dépôt (pour inclure referential/).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tesseract (OCR français) : utilisé à partir de la phase 3
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .
COPY referential/ ./referential/

RUN useradd --create-home --uid 1000 medimind && mkdir -p /data/storage && chown -R medimind /data /app
USER medimind

ENV STORAGE_PATH=/data/storage \
    REFERENTIAL_PATH=/app/referential/referentiel_clinique.yaml
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s CMD curl -fs http://localhost:8000/api/health || exit 1

# Migrations puis serveur
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
