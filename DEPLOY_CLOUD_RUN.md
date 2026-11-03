# Déployer l'API Valeon sur Google Cloud (Cloud Run + Cloud SQL) — option PAYANTE

> ⚠️ **Cette option coûte environ 10 à 15 $/mois** (la base Cloud SQL n'a pas d'offre gratuite).
> Pour un hébergement **gratuit**, suivez **[DEPLOY_VM_GRATUIT.md](DEPLOY_VM_GRATUIT.md)**
> (VM e2-micro « Always Free »). Ce guide reste utile si l'application grandit et a besoin
> d'un service plus rapide et sans maintenance.

Tout se fait dans **Cloud Shell**, le terminal de Google Cloud dans le navigateur :
la construction de l'image se fait chez Google, rien de lourd n'est téléchargé sur votre PC.

- Projet : `valeon-bab93` (le même que Firebase)
- Région : `europe-west1` (Belgique). Pour être plus proche de Madagascar, `africa-south1`
  (Johannesburg) fonctionne aussi, un peu plus cher : remplacez la valeur de `REGION` partout.
- Coût estimé : **~10 à 15 $/mois**, surtout la base Cloud SQL.

## 0. Avant de commencer

1. **Facturation** : console Google Cloud → menu ☰ → **Facturation** → associer un compte de
   facturation au projet `valeon-bab93` (carte bancaire demandée).
2. **Alerte de budget** (recommandé) : Facturation → **Budgets et alertes** → Créer →
   montant 15 $ → alertes par e-mail à 50 %, 90 %, 100 %.
3. Le code doit être à jour sur GitHub (`git push` depuis votre PC).
4. Ouvrez Cloud Shell : icône **>_** en haut à droite de la console.

Dans Cloud Shell, collez les blocs de commandes un par un.

## 1. Configurer le projet et activer les services

```bash
gcloud config set project valeon-bab93
REGION=europe-west1
PROJECT_NUMBER=$(gcloud projects describe valeon-bab93 --format='value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```

## 2. Créer la base MySQL (environ 10 minutes)

```bash
gcloud sql instances create valeon-db --database-version=MYSQL_8_0 \
  --edition=enterprise --tier=db-f1-micro --region=$REGION --storage-size=10

gcloud sql databases create valeon --instance=valeon-db \
  --charset=utf8mb4 --collation=utf8mb4_unicode_ci

DB_PASS=$(openssl rand -base64 24 | tr -d '/+=')
gcloud sql users create valeon --instance=valeon-db --password="$DB_PASS"
echo "Mot de passe MySQL : $DB_PASS"
```

Notez le mot de passe affiché (gestionnaire de mots de passe). Il ne sera plus réaffiché.

## 3. Récupérer le code

```bash
git clone https://github.com/andokevin/valeon_backend.git
cd valeon_backend
```

## 4. Préparer la configuration de production

1. Dans Cloud Shell, menu **⋮** (en haut du terminal) → **Importer** → choisissez votre fichier
   `.env` local (celui avec les clés à jour). Il arrive dans votre dossier personnel.
2. Créez la version de production :

```bash
cp ~/.env .env.prod
set_env() { grep -q "^$1=" .env.prod && sed -i "s|^$1=.*|$1=$2|" .env.prod || echo "$1=$2" >> .env.prod; }

set_env DATABASE_URL "mysql+pymysql://valeon:${DB_PASS}@/valeon?unix_socket=/cloudsql/valeon-bab93:${REGION}:valeon-db"
set_env ENVIRONMENT production
set_env DEBUG False
set_env REDIS_ENABLED false
set_env DATABASE_POOL_SIZE 5
set_env DATABASE_MAX_OVERFLOW 2
set_env AUTO_CREATE_TABLES true
set_env FIREBASE_PROJECT_ID valeon-bab93
sed -i '/^FIREBASE_SERVICE_ACCOUNT_KEY=/d' .env.prod
rm ~/.env
```

Firebase n'a pas besoin du fichier `serviceAccountKey.json` sur Cloud Run : l'API utilise
l'identité du service, qui appartient déjà au projet `valeon-bab93`.

## 5. Ranger la configuration dans Secret Manager

```bash
gcloud secrets create valeon-env --data-file=.env.prod
gcloud secrets add-iam-policy-binding valeon-env \
  --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
gcloud projects add-iam-policy-binding valeon-bab93 \
  --member="serviceAccount:$SA" --role=roles/cloudsql.client
rm .env.prod
```

## 6. Déployer

```bash
gcloud run deploy valeon-api --source . --region $REGION \
  --allow-unauthenticated \
  --add-cloudsql-instances valeon-bab93:${REGION}:valeon-db \
  --set-secrets /secrets/.env=valeon-env:latest \
  --set-env-vars ENV_FILE=/secrets/.env \
  --no-cpu-throttling --max-instances 1 --memory 1Gi --cpu 1 --timeout 300
```

Répondez `Y` si on vous propose de créer un dépôt Artifact Registry. La première fois,
la construction prend 5 à 10 minutes. À la fin, l'adresse du service s'affiche, par exemple
`https://valeon-api-xxxxxxxx.europe-west1.run.app`.

Pourquoi ces options :
- `--no-cpu-throttling` : les scans sont analysés **après** la réponse à l'app ; sans cette
  option, Cloud Run met le processeur en pause et les scans restent « en cours » pour toujours.
- `--max-instances 1` : les connexions WebSocket et le rate limit sont gardés en mémoire,
  ils doivent rester sur une seule instance.

## 7. Vérifier

Ouvrez `https://VOTRE-ADRESSE/health` : il doit afficher `"status": "healthy"`,
`"database": "ok"` et `"firebase": "ok"`.

## 8. Compiler l'application avec cette adresse

```bash
flutter build apk --release --dart-define=API_BASE_URL=https://VOTRE-ADRESSE/api
```

L'adresse Cloud Run ne change pas d'un déploiement à l'autre : inutile de recompiler l'APK
après une mise à jour du backend.

## Mettre à jour plus tard

- **Nouveau code** (après un `git push`) :
  ```bash
  cd ~/valeon_backend && git pull
  gcloud run deploy valeon-api --source . --region europe-west1
  ```
- **Changer une clé** : récréez `.env.prod` comme à l'étape 4, puis
  ```bash
  gcloud secrets versions add valeon-env --data-file=.env.prod && rm .env.prod
  gcloud run services update valeon-api --region europe-west1
  ```
- **Logs** : console → Cloud Run → `valeon-api` → onglet **Journaux**.

## Arrêter les frais

- Mettre la base en pause : `gcloud sql instances patch valeon-db --activation-policy=NEVER`
  (relancer avec `--activation-policy=ALWAYS`). Sans base, l'API répond `"database": "error"`.
- Tout supprimer : `gcloud run services delete valeon-api --region europe-west1` puis
  `gcloud sql instances delete valeon-db`.

## Problèmes fréquents

| Symptôme | Solution |
|---|---|
| `PERMISSION_DENIED` pendant le déploiement | `gcloud projects add-iam-policy-binding valeon-bab93 --member="serviceAccount:$SA" --role=roles/run.builder` puis relancer |
| `/health` : `"database": "error"` | Vérifier l'option `--add-cloudsql-instances` et `DATABASE_URL` (étape 4) |
| `/health` : `"firebase": "disabled"` | Vérifier `FIREBASE_ENABLED=true` dans la configuration |
| Les scans restent « en cours » | Le service a été déployé sans `--no-cpu-throttling` : relancer l'étape 6 |
| Scan image ou chat en mode « démo » | Clé Gemini invalide ou modèle surchargé (réessayer plus tard) |
