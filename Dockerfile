FROM python:3.12-slim

# ffmpeg : scan vidéo et découpe des audios longs ; libglib : requis par opencv-headless
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# /data : base SQLite persistante (hébergement VM gratuit, voir DEPLOY_VM_GRATUIT.md)
RUN useradd --create-home valeon && mkdir -p uploads /data && chown -R valeon /app /data
USER valeon

# --proxy-headers : derrière le proxy Google, utiliser la vraie IP du client (rate limit)
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*"
