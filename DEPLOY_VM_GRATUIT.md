# Déployer l'API Valeon gratuitement (VM e2-micro « Always Free »)

Une petite machine virtuelle Google Cloud gratuite fait tourner l'API et une base SQLite,
derrière Caddy qui fournit le HTTPS automatiquement. Tout se fait depuis le navigateur
(console + fenêtre SSH) : la construction se passe sur la VM, pas sur votre PC.

> Conditions de l'offre gratuite (à vérifier sur https://cloud.google.com/free) :
> 1 VM **e2-micro** dans **us-central1, us-west1 ou us-east1**, 30 Go de disque **standard**,
> 1 Go de trafic sortant par mois. L'adresse IP publique peut être facturée (quelques $/mois)
> selon les conditions en vigueur : vérifiez la page tarifs et créez une alerte de budget.

## 0. Avant de commencer

1. **Facturation** : console Google Cloud (projet `valeon-bab93`) → ☰ **Facturation** →
   associer un compte de facturation (carte demandée, même pour l'offre gratuite).
2. **Alerte de budget** : Facturation → **Budgets et alertes** → Créer → montant **1 $** →
   alertes à 50 % / 100 %. Vous serez prévenu au moindre frais.
3. Le code doit être à jour sur GitHub (`git push`).

## 1. Créer la VM

Console → ☰ **Compute Engine** → **Instances de VM** → **Créer une instance**
(activez l'API Compute Engine si demandé) :

| Réglage | Valeur |
|---|---|
| Nom | `valeon` |
| Région | `us-central1` (Iowa) — obligatoire pour la gratuité |
| Type de machine | **e2-micro** (série E2) |
| Disque de démarrage → Modifier | **Ubuntu 24.04 LTS** (x86/64), type **Disque persistant standard**, **30 Go** |
| Pare-feu | cocher **Autoriser le trafic HTTP** et **Autoriser le trafic HTTPS** |

Cliquez **Créer**. Notez l'**adresse IP externe** affichée (ex. `34.123.45.67`).

**Ne supprimez/arrêtez pas la VM inutilement** : l'adresse IP peut changer après un arrêt,
et l'APK devrait alors être recompilé avec la nouvelle adresse.

## 2. Se connecter et installer Docker

Dans la liste des VM, cliquez **SSH** à côté de `valeon` : un terminal s'ouvre dans le
navigateur. Collez :

```bash
# Mémoire d'appoint (la VM n'a que 1 Go de RAM)
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Fermez la fenêtre SSH et rouvrez-la (pour que le groupe `docker` soit pris en compte).

## 3. Récupérer le code

```bash
git clone https://github.com/andokevin/valeon_backend.git
cd valeon_backend/deploy/vm
```

## 4. Préparer la configuration

1. Dans la fenêtre SSH : bouton **Importer le fichier** (icône en haut à droite) → choisissez
   votre fichier `.env` local (avec les clés à jour). Il arrive dans votre dossier personnel.
2. Créez la configuration du serveur :

```bash
IP=$(curl -s -H "Metadata-Flavor: Google" http://metadata/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip)
DOMAIN="${IP//./-}.sslip.io"
echo "Adresse de l'API : https://$DOMAIN"

cp ~/.env .env && rm ~/.env
set_env() { grep -q "^$1=" .env && sed -i "s|^$1=.*|$1=$2|" .env || echo "$1=$2" >> .env; }
set_env DATABASE_URL "sqlite:////data/valeon.db"
set_env ENVIRONMENT production
set_env DEBUG False
set_env REDIS_ENABLED false
set_env AUTO_CREATE_TABLES true
set_env FIREBASE_USE_ADC true
set_env FIREBASE_PROJECT_ID valeon-bab93
set_env DOMAIN "$DOMAIN"
sed -i '/^FIREBASE_SERVICE_ACCOUNT_KEY=/d' .env
chmod 600 .env
```

`sslip.io` est un service gratuit qui transforme l'IP en nom de domaine
(`34-123-45-67.sslip.io` → `34.123.45.67`), ce qui permet à Caddy d'obtenir un vrai
certificat HTTPS sans acheter de domaine.

Firebase n'a pas besoin de fichier de clé : la VM utilise son identité Google Cloud, qui
appartient au projet `valeon-bab93`.

## 5. Lancer

```bash
docker compose --env-file .env up -d --build
```

La première construction prend 10 à 20 minutes sur la petite VM. Ensuite :

```bash
docker compose ps                 # les 2 services doivent être "running"
curl -s https://$DOMAIN/health    # "status": "healthy", "database": "ok", "firebase": "ok"
```

L'API redémarre toute seule si la VM redémarre (`restart: unless-stopped`).

## 6. Compiler l'application

Sur votre PC (PowerShell) :

```powershell
wsl bash /mnt/d/valeon/valeon-build.sh https://34-123-45-67.sslip.io/api --offline
```

(remplacez par votre adresse, avec `/api` à la fin).

## Entretien

- **Mettre à jour le code** (après un `git push`) :
  ```bash
  cd ~/valeon_backend && git pull && cd deploy/vm && docker compose --env-file .env up -d --build
  ```
- **Voir les erreurs** : `docker compose logs --tail 100 api`
- **Sauvegarder la base** (à faire régulièrement) :
  ```bash
  docker compose exec api python -c "import sqlite3; sqlite3.connect('/data/valeon.db').backup(sqlite3.connect('/data/backup.db'))"
  docker compose cp api:/data/backup.db ~/valeon-backup-$(date +%F).db
  ```
  puis téléchargez le fichier avec le bouton **Télécharger le fichier** de la fenêtre SSH.
- **Mises à jour de sécurité Ubuntu** : `sudo apt update && sudo apt upgrade -y` de temps en temps.

## Problèmes fréquents

| Symptôme | Solution |
|---|---|
| `https://...sslip.io` ne répond pas | Vérifier que HTTP **et** HTTPS sont autorisés dans le pare-feu de la VM ; `docker compose logs caddy` |
| `"database": "error"` | `docker compose logs api` ; vérifier `DATABASE_URL=sqlite:////data/valeon.db` (4 barres obliques) |
| `"firebase": "disabled"` | Vérifier `FIREBASE_USE_ADC=true` et `FIREBASE_ENABLED=true` dans `.env`, puis relancer l'étape 5 |
| La construction s'arrête (mémoire) | Vérifier le swap : `free -h` doit montrer 2 Go de swap |
| Scans lents | Normal sur e2-micro (processeur partagé) ; un scan peut prendre 10 à 30 s |
