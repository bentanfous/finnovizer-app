# Déploiement — GitHub + Railway

Guide pas à pas, du repo au service en ligne.

## 1. Pousser sur GitHub

Depuis le dossier du projet :

```bash
git init
git add .
git commit -m "Innovizer Pilot — chaîne complète B01/B02/B03"
git branch -M main
git remote add origin https://github.com/<toi>/innovizer-pilot.git
git push -u origin main
```

Le `.gitignore` exclut déjà `data/`, les `.xlsx` et les caches : aucune donnée
client ne part sur GitHub. Vérifie-le avant le premier push.

## 2. Créer le service Railway

1. Sur railway.app → **New Project** → **Deploy from GitHub repo**.
2. Choisis `innovizer-pilot`. Railway détecte Python (Nixpacks) et lit
   `railway.json` : build automatique, start `uvicorn app.main:app`.
3. Le premier déploiement se lance seul.

## 3. Monter le volume persistant

Sans volume, les fichiers uploadés disparaissent à chaque redéploiement.

L'interface Railway a changé : le volume ne se crée plus dans Settings.

1. Sur le **canvas** du projet (la vue avec le bloc du service), fais
   **clic droit** sur une zone vide, ou appuie sur **Cmd/Ctrl + K**.
2. Cherche **Volume** → **Create Volume**.
3. Attache-le au service `innovizer-pilot`.
4. **Mount path** : `/data`

## 4. Définir les variables d'environnement

Onglet **Variables** du service → **New Variable**, deux fois :

| Name | Value |
|---|---|
| `INNOVIZER_RAW_DIR` | `/data/raw_uploads` |
| `INNOVIZER_DERIVED_DIR` | `/data/derived` |

Optionnel :

| Name | Value | Rôle |
|---|---|---|
| `INNOVIZER_MAX_UPLOAD_MB` | `50` | taille max d'un fichier |
| `PORT` | *(laisser Railway le fixer)* | port d'écoute |

Ne mets **jamais** ces variables dans GitHub : elles vivent dans Railway.

## 5. Redéployer et vérifier

Railway redéploie automatiquement après l'ajout du volume. Sinon, **Redeploy**.

Health check :

```
https://<ton-service>.up.railway.app/api/health
→ {"ok": true, "version": "1.0.0", "jobs": 0}
```

Puis ouvre la racine : l'écran **00 · Sources** s'affiche avec les 8 catégories
d'upload.

## 6. Premier test — jeu anonymisé

Ordre recommandé :

1. Créer un dossier (client, exercice).
2. Déposer, dans l'ordre : livre de paie, bulletins PDF, suivi des temps,
   référentiels MESR CIR et CII, puis fournisseurs si tu les as.
3. **Construire le Data Hub**.

Le premier build parse les bulletins (~5 min pour 12 mois, une seule fois : le
résultat est mis en cache sur le volume). Les builds suivants sont quasi
instantanés.

## Dépannage — `ModuleNotFoundError: No module named 'app'`

Uvicorn démarre mais ne trouve pas le dossier `app/`. Cause quasi certaine :
**le contenu du projet n'est pas à la racine du repo GitHub**.

Vérifie sur GitHub : à la racine du repo, tu dois voir directement `app/`,
`innovizer/`, `requirements.txt`, `railway.json`. Si à la place tu vois un
seul dossier (ex. `innovizer_app/` ou `innovizer-pilot/`) qui contient tout
ça, c'est le problème.

Deux réparations, l'une suffit :

- **La plus simple** — dans Railway → service → **Settings → Source** →
  **Root Directory**, mets le nom du sous-dossier (ex. `innovizer_app`).
  Railway se placera dedans. Redeploy.
- **Ou** remets le contenu à la racine du repo :
  ```bash
  git mv innovizer_app/* .
  git mv innovizer_app/.gitignore innovizer_app/.env.example .
  rmdir innovizer_app
  git commit -m "contenu à la racine" && git push
  ```

Le projet inclut un `nixpacks.toml` qui force `PYTHONPATH=.`, ce qui règle le
cas où le module n'est pas résolu même à la racine. Si tu utilises le
`Dockerfile` plutôt que Nixpacks, il n'y a pas ce souci : le `WORKDIR /app`
place déjà tout au bon endroit.

## Arborescence du volume après usage

```
/data
 ├── raw_uploads/<job>/
 │    ├── paie/  bulletins/  temps/  fournisseurs/
 │    ├── immobilisations/  cv_diplomes/
 │    └── mesr_cir/  mesr_cii/
 └── derived/<job>/
      ├── job.json          état du dossier
      ├── data_hub.json     résumé Brique 01+02
      ├── brique01.xlsx      export tableur complet
      ├── entretiens/        fiches Eva (une par entretien)
      └── .cache/            cache de parsing des bulletins
```

## Notes d'exploitation

- **Mémoire.** Le référentiel MESR CIR fait ~30 000 lignes. Le plan Railway par
  défaut suffit ; si le build est tué (OOM) sur un très gros dossier, monte la
  RAM du service dans Settings.
- **Timeout de build.** Le health check attend 120 s (`railway.json`). Le
  serveur démarre en quelques secondes ; le parsing lourd se fait à la demande,
  pas au démarrage, donc le health check passe tout de suite.
- **Sauvegarde.** Le volume n'est pas sauvegardé automatiquement. Pour un vrai
  dossier client, exporte régulièrement `brique01.xlsx`.

## ⚠ RGPD — à régler avant toute donnée réelle

L'application stocke paie nominative, CV et diplômes sur le volume Railway.

- Vérifie la **région d'hébergement** Railway (UE de préférence).
- N'y mets de la donnée réelle qu'avec une **base légale** côté client : une
  convention de sous-traitance RGPD qui te désigne sous-traitant, précise les
  finalités, la durée de conservation et la sécurité.
- Pour éprouver la tuyauterie sans risque, utilise un **jeu anonymisé**.

Ceci n'est pas un conseil juridique.
