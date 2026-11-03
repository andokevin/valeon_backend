# Déployer l'API Valeon gratuitement sur Hugging Face Spaces

Gratuit, **sans carte bancaire**, avec une adresse HTTPS fournie par Hugging Face
(`https://<utilisateur>-valeon-api.hf.space`). Tout se fait dans le navigateur : le Space ne
contient que 2 petits fichiers, et c'est Hugging Face qui télécharge le code depuis GitHub et
construit l'image (presque aucune donnée ne passe par votre connexion).

> **Limites de l'offre gratuite (CPU basic)**
> - Le Space **se met en veille après ~48 h sans visite** ; la requête suivante le réveille
>   (environ 1 minute d'attente).
> - **La base SQLite est effacée à chaque redémarrage** (veille, reconstruction, maintenance).
>   Les utilisateurs doivent alors se réinscrire. Pour garder les données, activer le
>   **stockage persistant** (payant) dans les réglages du Space : il est monté sur `/data`,
>   où se trouve déjà la base — aucune autre modification n'est nécessaire.

## 0. Avant de commencer

Le code doit être à jour sur GitHub (le Space le récupère depuis
`github.com/andokevin/valeon_backend`, qui doit rester **public**) :

```bash
cd /mnt/d/valeon/valeon_backend && git push
```

Préparez aussi, sur votre PC :
- le contenu de votre fichier `valeon_backend\.env` (avec les clés à jour) ;
- le contenu de `valeon_backend\app\serviceAccountKey.json` (clé Firebase du projet **valeon-bab93**).

## 1. Créer un compte Hugging Face

https://huggingface.co/join — e-mail et mot de passe, puis confirmez l'e-mail. Aucune carte demandée.

## 2. Créer le Space

https://huggingface.co/new-space :

| Champ | Valeur |
|---|---|
| Space name | `valeon-api` |
| License | `other` (ou laissez vide) |
| Select the Space SDK | **Docker** → modèle **Blank** |
| Space hardware | **CPU basic · FREE** |
| Visibility | **Public** (obligatoire : l'application doit pouvoir l'appeler sans compte Hugging Face) |

Cliquez **Create Space**. Les secrets ne sont jamais visibles publiquement, seuls les 2 fichiers le sont.

## 3. Ajouter les 2 fichiers

Dans le Space, onglet **Files** :

1. **Dockerfile** : **+ Add file → Create a new file**, nommez-le `Dockerfile`, collez le contenu de
   [deploy/huggingface/Dockerfile](deploy/huggingface/Dockerfile), puis **Commit new file to main**.
2. **README.md** : cliquez sur `README.md` → **Edit**, remplacez tout par le contenu de
   [deploy/huggingface/README.md](deploy/huggingface/README.md) (l'en-tête entre `---` est
   indispensable : `sdk: docker` et `app_port: 7860`), puis **Commit changes to main**.

## 4. Ajouter les secrets

Onglet **Settings** → section **Variables and secrets** → **New secret** (deux fois) :

| Name | Value |
|---|---|
| `VALEON_ENV` | tout le contenu de votre fichier `.env` |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | tout le contenu de `serviceAccountKey.json` (de `{` à `}`) |

Les réglages de production (base SQLite, `ENVIRONMENT=production`, `DEBUG=False`, Redis
désactivé…) sont déjà dans le Dockerfile et passent avant ceux de votre `.env` : inutile de
modifier votre `.env` avant de le coller.

## 5. Attendre la construction

Le Space se construit automatiquement (onglet **App**, statut « Building », puis « Running »).
Comptez 5 à 15 minutes. En cas d'erreur, le bouton **Logs** affiche le détail.

## 6. Vérifier

Adresse de l'API : `https://<votre-utilisateur>-valeon-api.hf.space`
(visible aussi via le menu **⋮ → Embed this Space → Direct URL**).

Ouvrez `https://<votre-utilisateur>-valeon-api.hf.space/health` : il doit afficher
`"status": "healthy"`, `"database": "ok"` et `"firebase": "ok"`.

## 7. Compiler l'application

Sur votre PC (PowerShell), sans consommer de données :

```powershell
wsl bash /mnt/d/valeon/valeon-build.sh https://<votre-utilisateur>-valeon-api.hf.space/api --offline
```

L'APK est copié dans `D:\valeon\valeon-release.apk`. L'adresse du Space ne change pas :
inutile de recompiler l'APK après une mise à jour du backend.

## Mettre à jour le backend

1. `git push` sur GitHub (depuis votre PC).
2. Space → **Settings** → **Factory rebuild** : le Space récupère le nouveau code et se reconstruit.
   ⚠️ La base est remise à zéro (sauf stockage persistant).

Pour changer une clé : **Settings → Variables and secrets** → modifiez `VALEON_ENV`,
le Space redémarre tout seul.

## Problèmes fréquents

| Symptôme | Solution |
|---|---|
| Construction en échec sur `ADD https://api.github.com/...` | Limite de requêtes GitHub atteinte (rare) : relancer **Factory rebuild** un peu plus tard |
| Construction en échec sur `git clone` | Vérifier que le dépôt GitHub `valeon_backend` est **public** et à jour |
| `/health` : `"firebase": "disabled"` | Vérifier le nom exact du secret `FIREBASE_SERVICE_ACCOUNT_JSON` et que tout le JSON a été collé |
| L'app est déconnectée / « Utilisateur introuvable » | Le Space a redémarré et la base a été vidée : se réinscrire (ou activer le stockage persistant) |
| Première requête très lente | Le Space sortait de veille : normal après 48 h d'inactivité |
| Scan image / chat en mode « démo » | Clé Gemini invalide dans `VALEON_ENV`, ou modèle surchargé (réessayer) |
