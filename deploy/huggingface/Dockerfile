# Dockerfile du Space Hugging Face : à copier tel quel dans le Space (avec README.md).
# Le code est récupéré depuis GitHub au moment de la construction, chez Hugging Face.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 git \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face exécute le conteneur avec l'utilisateur 1000
RUN useradd -m -u 1000 user

# Réglages de production (prioritaires sur ceux du secret VALEON_ENV)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    ENVIRONMENT=production \
    DEBUG=False \
    DATABASE_URL=sqlite:////data/valeon.db \
    DATABASE_POOL_SIZE=5 \
    DATABASE_MAX_OVERFLOW=5 \
    REDIS_ENABLED=false \
    AUTO_CREATE_TABLES=true

# Ce fichier change à chaque nouveau commit sur GitHub : force la récupération du code à jour
ADD https://api.github.com/repos/andokevin/valeon_backend/commits/main /tmp/latest-commit.json
RUN git clone --depth 1 https://github.com/andokevin/valeon_backend.git /app

WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /data uploads \
    && chown -R user /app /data

USER user
EXPOSE 7860
CMD ["sh", "deploy/huggingface/start.sh"]
