# Innovizer Pilot

Chaîne complète de préparation d'un dossier CIR/CII, des fichiers bruts du
client à la fiche d'audit par projet. Une seule application web, déployable sur
Railway.

```
FICHIERS BRUTS CLIENT
  paie · bulletins · temps · fournisseurs · immos · CV/diplômes · référentiels MESR
        │
        ▼
BRIQUE 01 — Data Hub            reconstruit, rapproche, contrôle, documente
        │                       (ne décide d'aucune éligibilité)
        ▼
BRIQUE 02 — Screening projets   écarte les fonctions support, liste ce qui s'instruit
        │
        ▼
BRIQUE 03 — Audit Eva           entretien technique par projet, fiche défendabilité
        │
        ▼
        (Brique 04 — regroupement thématique : à venir)
```

## Ce que l'app fait

À partir des fichiers que le client envoie déjà — sans format à préparer —
Innovizer reconstruit :

- **Personnel** : coût chargé par salarié, réconcilié au centime avec le livre
  de paie ; heures travaillées issues des bulletins ; cotisations classées par
  une doctrine sourcée (`doctrine/cir_personnel.yaml`).
- **Qualification** : statuts fins (`ELIGIBLE_CONFIRMED`, `ELIGIBLE_TECHNICIAN`,
  `TO_REVIEW`, `INSUFFICIENT_EVIDENCE`, `NON_RD_FUNCTION`). Un diplôme non
  aligné ouvre une question, jamais une exclusion ni une éligibilité automatique.
- **Temps** : quotité R&D sur les heures **travaillées** (pas déclarées), avec
  un **taux de couverture** qui signale les saisies partielles.
- **Screening projets** : fonctions support écartées d'office, le reste à instruire.
- **Sous-traitance** : vérification d'agrément MESR **par SIREN**, jamais par
  raison sociale.
- **Contrôles** : réconciliations, cohérences temps/paie, pièces manquantes.
- **Audit Eva** : entretien technique adaptatif par projet, qui challenge les
  réponses vagues et produit une fiche de défendabilité.

## Principes non négociables

1. **Le silence n'est jamais une éligibilité.** Rubrique inconnue, diplôme
   non collecté, projet non classé, SIREN absent → « à instruire », hors assiette.
2. **Éligibilité ≠ défendabilité.** Deux dimensions distinctes à l'audit.
3. **Agréé ≠ dépense éligible.** Le MESR répond à une question sur six.
4. **Les règles fiscales sont sourcées, hors du code**, dans `doctrine/*.yaml`.
5. **La doctrine ne décide pas seule.** Eva et les contrôles préparent ;
   l'expert tranche. Toute fiche porte `revue_experte_requise = true`.

## Lancer en local

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# http://localhost:8000
```

Les données vont sous `./data`. Ouvrir l'app, créer un dossier, déposer les
fichiers, cliquer « Construire le Data Hub ».

## Tests

```bash
python -m pytest innovizer/brique03/tests -q
```

## Déploiement Railway

Voir `DEPLOY.md`. En bref : pousser sur GitHub, connecter le repo à Railway,
monter un volume sur `/data`, définir les deux variables d'environnement.

## ⚠ Données personnelles

L'app ingère de la paie nominative, des CV et des diplômes. Avant tout test
avec des données réelles : hébergement en UE, et base légale RGPD côté client
(convention de sous-traitance). Pour éprouver la tuyauterie, utiliser un jeu
anonymisé.

## Structure

```
app/            API FastAPI + orchestration des dossiers
  main.py       routes REST
  jobs.py       un dossier = un job, du brut à la fiche Eva
  settings.py   config depuis l'environnement
web/            frontend une page (sources → hub → screening → Eva)
innovizer/      le moteur métier (indépendant du web)
  ingest/       parsers paie, bulletins, temps
  engines/      assiette, qualification, screening, sous-traitance, immos, fiche projet
  doctrine/     règles fiscales sourcées (YAML)
  brique03/     moteur d'entretien Eva
  controls.py   registre des contrôles
  pipeline.py   orchestrateur Brique 01
```
