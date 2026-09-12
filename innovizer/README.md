# Innovizer — Brique 01 : Data Connectors & Evidence Hub

Reconstruit, rapproche, contrôle et documente les données d'un dossier CIR/CII.
**Ne décide d'aucune éligibilité.**

## Entrées réelles

Fichiers, pas connecteurs API. Ce sont les pièces que le client transmet déjà.

| Source | Format | Module |
|---|---|---|
| Livre de paie (détail par salarié) | .xlsx format long | `ingest/paie.py` |
| Bulletins de paie mensuels | .pdf texte | `ingest/bulletins.py` |
| Suivi des temps PayFit | .xlsx, onglet `Détails` | `ingest/temps.py` |
| Extrait fournisseurs | comptabilité | `engines/subcontracting.py` |
| État des immobilisations | comptabilité | `engines/assets.py` |
| CV, diplômes, attestations | .pdf | `engines/people.py` |
| Référentiels MESR CIR / CII | .xlsx open data | `pipeline.charger_referentiels_mesr` |

## Usage

```python
from innovizer import config
from innovizer.pipeline import Brique01

b = Brique01(config.DUNASYS_2025)
b.charger_paie("livre_de_paie.xlsx")
b.charger_bulletins("bulletins/*.pdf")
b.charger_temps("temps/time-tracking-*.xlsx")
b.charger_referentiels_mesr("mesr_cir.xlsx", "mesr_cii.xlsx")
b.moteur_personnel().moteur_assiette().moteur_projets(amorce)
b.moteur_soustraitance(fournisseurs)
b.moteur_preuves(pieces)
b.exporter("dossier.xlsx")
```

## Principes non négociables

1. **Rien en dur.** Tout ce qui varie par client ou par année est dans
   `config.Dossier` : durée journalière, périmètre des cotisations, seuils,
   alias d'identité, activités support. Un exercice doit pouvoir être
   recalculé trois ans plus tard avec ses propres paramètres.

2. **Le silence n'est jamais une éligibilité.** Projet non classé, diplôme non
   collecté, rubrique inconnue, SIREN absent : tout tombe en « à instruire »
   et sort de l'assiette tant qu'une décision n'est pas saisie.

3. **Éligibilité ≠ défendabilité.** Deux colonnes distinctes dans le screening.
   Un projet éligible mais sans matière technique sort de l'assiette : c'est
   une décision de risque, pas de droit.

4. **Agréé ≠ dépense éligible.** Le référentiel MESR répond à une seule
   question sur six. Les listes ouvertes sont indicatives et non opposables :
   la décision d'agrément doit être réclamée au prestataire.

5. **Le SIREN, jamais la raison sociale.** SIREN absent → `NO_SIREN`, pas
   `NOT_FOUND`. Une pièce manquante n'est pas un résultat négatif.

6. **Les parsers échouent bruyamment.** Nombre de colonnes inattendu →
   exception. Un éditeur qui change sa mise en page en cours d'année doit
   casser le parser, pas produire des zéros silencieux.

7. **Minimisation.** Les bulletins contiennent numéro de sécurité sociale,
   adresse, situation familiale, absences maladie. Rien de tout cela n'est
   extrait. L'Evidence Hub référence les pièces, il n'en recopie pas le contenu.

## Contrôles

| Code | Objet |
|---|---|
| P1, P2 | réconciliation brut et cotisations patronales |
| P3 | matricule absent du SIRH |
| P4 | taux de charges hors bornes |
| B1, B2 | couverture bulletins, heures travaillées |
| T1, T2 | rapprochement paie ↔ suivi des temps |
| T3 | heures sur projets non classés |
| T4, T5 | heures valorisées > travaillées, quotité élevée |
| T6 | intégrité arithmétique des tableaux de répartition |
| Q1 | salarié valorisé sans qualification établie |
| S1 | régime sous-traitance ≠ régime de l'opération |

## Reste à faire

- résolution raison sociale → SIREN (API SIRENE) pour les fournisseurs
- ingestion de l'état des immobilisations au format comptable
- rattachement actif → utilisateur → quotité
