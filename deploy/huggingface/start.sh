#!/bin/sh
# Démarrage sur Hugging Face Spaces : les secrets du Space deviennent des fichiers de config.
set -e

# Secret VALEON_ENV : contenu complet du fichier .env (les variables d'environnement
# définies dans le Dockerfile ou dans le Space restent prioritaires)
if [ -n "$VALEON_ENV" ]; then
  printf '%s\n' "$VALEON_ENV" > /tmp/valeon.env
  export ENV_FILE=/tmp/valeon.env
fi

# Secret FIREBASE_SERVICE_ACCOUNT_JSON : contenu de serviceAccountKey.json (projet valeon-bab93)
if [ -n "$FIREBASE_SERVICE_ACCOUNT_JSON" ]; then
  printf '%s' "$FIREBASE_SERVICE_ACCOUNT_JSON" > /tmp/firebase-key.json
  chmod 600 /tmp/firebase-key.json
  export FIREBASE_SERVICE_ACCOUNT_KEY=/tmp/firebase-key.json
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-7860}" \
  --proxy-headers --forwarded-allow-ips="*"
