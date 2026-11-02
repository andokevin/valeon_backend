# Valeon API

API FastAPI de Valeon : identification de musiques, films et images (scan audio,
image, vidéo), bibliothèque utilisateur, recommandations et chat IA.

## Installation

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # puis remplir les valeurs
python scripts/init_db.py --seed
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Le scan vidéo nécessite `ffmpeg` installé sur le serveur. La transcription audio locale
nécessite en plus `pip install openai-whisper` (optionnel, environ 2 Go).

## Configuration

- `.env` : voir `.env.example`. En production : `ENVIRONMENT=production`, `DEBUG=false`
  et une `SECRET_KEY` longue et aléatoire.
- Connexion Google/Facebook : placer la clé de compte de service Firebase du projet
  **valeon-bab93** dans `app/serviceAccountKey.json`. Si elle manque, la connexion
  sociale répond 503 (aucun token n'est accepté sans vérification).
- Vérification : `GET /health` doit renvoyer `"database": "ok"` et `"firebase": "ok"`.

Les fichiers `.env`, `serviceAccountKey.json` et `credentials/` ne doivent jamais être commités.
