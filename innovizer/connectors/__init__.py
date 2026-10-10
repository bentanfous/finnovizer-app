"""
Innovizer — connecteurs : ingestion des sources vers le substrat.

Chaque connecteur lit une source (fichier ou API) et produit un DataFrame
conforme au schéma de l'entité correspondante dans `innovizer.models`.

  paie       -> payroll (livre de paie)
  bulletins  -> people  (bulletins PDF)
  temps      -> time_entries (suivi des temps)
  ventes     -> revenues (export produits 7xx / Pennylane) — famille IP Box
  fec        -> financial_entries (FEC) — dénominateur IP Box, base Social
  factures   -> valorisation HT + backfill SIREN (sous-traitance agréée)

Connecteurs API (ingestion automatisée, mêmes schémas que les fichiers) :
  payfit     -> people (collaborators+contracts), financial_entries
                (accounting-v2) et assiette CIR si export « par employé +
                détail cotisation ». Mode fixture pour tester sans clé.

À venir : patrimoine -> real_estate (famille fiscalité locale) ; Silae, Lucca.
"""
