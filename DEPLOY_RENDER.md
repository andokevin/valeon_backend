# Déployer l'API Valeon gratuitement : Render (API) + Neon (base de données)

- **Render** fait tourner l'API (Docker) gratuitement et construit l'image depuis GitHub :
  presque aucune donnée ne passe par votre connexion.
- **Neon** héberge la base PostgreSQL gratuitement : les données sont conservées.
- Adresse fournie : `https://valeon-api.onrender.com` (ou proche), en HTTPS.

> **Limites de l'offre gratuite Render** (à vérifier sur https://render.com/pricing)
> - Mise en **veille après ~15 min sans requête** ; la suivante attend ~50 s le réveil.
>   Astuce gratuite : un moniteur (étape 6) appelle `/health` toutes les 5 min pour l'éviter.
> - 512 Mo de RAM, 750 h d'exécution par mois (assez pour un service allumé en continu).

## 0. Avant de commencer

- Le code doit être à jour sur GitHub (`git push`), dépôt `andokevin/valeon_backend`.
- Base Neon créée, avec sa **connection string** (`postgresql://…?sslmode=require`,
  *Connection pooling* sur OFF) — voir la partie Neon de [DEPLOY_HUGGINGFACE.md](DEPLOY_HUGGINGFACE.md#4-bis-base-de-données-permanente-avec-neon-recommandé-gratuit).

## 1. Créer le compte Render

https://dashboard.render.com/register → **GitHub** (le plus simple : Render pourra lire vos dépôts).
Autorisez Render sur votre compte GitHub.

## 2. Créer le service

1. Tableau de bord Render → **+ New** → **Web Service**.
2. **Git Provider : GitHub** → choisissez le dépôt **valeon_backend** → **Connect**
   (si la liste est vide : **Configure account** et donnez l'accès à ce dépôt).
3. Remplissez :

| Champ | Valeur |
|---|---|
| Name | `valeon-api` (donne l'adresse `valeon-api.onrender.com`) |
| Language / Runtime | **Docker** |
| Branch | `main` |
| Region | **Frankfurt (EU Central)** |
| Root Directory | laisser vide |
| Instance Type | **Free** |

## 3. Variables d'environnement

Toujours sur la même page, section **Environment Variables** → **Add Environment Variable** :

| Key | Value |
|---|---|
| `DATABASE_URL` | la connection string Neon |
| `ENV_FILE` | `/etc/secrets/.env` |
| `FIREBASE_SERVICE_ACCOUNT_KEY` | `/etc/secrets/serviceAccountKey.json` |
| `ENVIRONMENT` | `production` |
| `DEBUG` | `False` |
| `REDIS_ENABLED` | `false` |
| `AUTO_CREATE_TABLES` | `true` |
| `DATABASE_POOL_SIZE` | `5` |
| `DATABASE_MAX_OVERFLOW` | `5` |

Ces variables passent avant celles du fichier `.env` : inutile de modifier votre `.env`.

## 4. Fichiers secrets

Section **Secret Files** (même page, ou plus tard dans **Environment**) → **Add Secret File** (deux fois) :

| Filename | Contents |
|---|---|
| `.env` | tout le contenu de `valeon_backend\.env` |
| `serviceAccountKey.json` | tout le contenu de `valeon_backend\app\serviceAccountKey.json` |

Render les place dans `/etc/secrets/`, qui correspond aux variables de l'étape 3.

## 5. Déployer

Section **Advanced** (en bas) : **Health Check Path** = `/health`.

Cliquez **Deploy Web Service**. La construction prend 5 à 15 minutes (onglet **Logs**).
Quand le statut est **Live**, ouvrez `https://valeon-api.onrender.com/health` (l'adresse exacte
est affichée en haut de la page du service) : il doit afficher `"status": "healthy"`,
`"database": "ok"` et `"firebase": "ok"`.

## 6. (Optionnel) Éviter la mise en veille

https://uptimerobot.com → compte gratuit → **Add New Monitor** :
type **HTTP(s)**, URL `https://valeon-api.onrender.com/health`, intervalle **5 minutes**.

## 7. Compiler l'application

Sur votre PC (PowerShell), sans consommer de données :

```powershell
wsl bash /mnt/d/valeon/valeon-build.sh https://valeon-api.onrender.com/api --offline
```

L'APK est copié dans `D:\valeon\valeon-release.apk`.

## Mettre à jour

Chaque `git push` sur la branche `main` redéploie automatiquement le service.
Pour changer une clé : page du service → **Environment** → modifiez le fichier secret `.env`
→ **Save Changes** (redéploiement automatique).

## Problèmes fréquents

| Symptôme | Solution |
|---|---|
| Échec « Out of memory » / redémarrages en boucle | La RAM gratuite (512 Mo) est dépassée : consulter **Logs** et me les envoyer |
| `/health` : `"database": "error"` | Vérifier `DATABASE_URL` (connection string Neon complète, avec `?sslmode=require`) |
| `/health` : `"firebase": "disabled"` | Vérifier le fichier secret `serviceAccountKey.json` et la variable `FIREBASE_SERVICE_ACCOUNT_KEY` |
| Erreur au démarrage sur `/etc/secrets/...` (permission) | Me transmettre les Logs : les fichiers secrets peuvent nécessiter un ajustement |
| Première requête très lente | Réveil après veille : normal, ou activer l'étape 6 |
