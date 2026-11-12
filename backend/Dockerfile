# Image du backend MediMind. Contexte de build : racine du dépôt (pour inclure referential/).
# Ordre des couches : dépendances système, dépendances Python, poids du modèle, puis code (le plus souvent
# modifié en dernier, pour profiter du cache).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tesseract (OCR français) et curl (contrôle de santé)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra curl \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 medimind && mkdir -p /data/storage /app && chown -R medimind /data /app
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# Poids du modèle d'imagerie intégrés à l'image : la démonstration fonctionne sans accès à internet
USER medimind
RUN python -c "import torchxrayvision as xrv; xrv.models.DenseNet(weights='densenet121-res224-all')"
# Modèle de recherche de l'assistant (F-E4), lui aussi intégré ; ensuite plus aucun accès au Hub
RUN python -c "from transformers import AutoModel, AutoTokenizer; n='intfloat/multilingual-e5-small'; AutoTokenizer.from_pretrained(n); AutoModel.from_pretrained(n)"
ENV HF_HUB_OFFLINE=1

COPY --chown=medimind backend/ .
COPY --chown=medimind referential/ ./referential/

ENV STORAGE_PATH=/data/storage \
    REFERENTIAL_PATH=/app/referential/referentiel_clinique.yaml
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s CMD curl -fs http://localhost:8000/api/health || exit 1

# Migrations puis serveur
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
