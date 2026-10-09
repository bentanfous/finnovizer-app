"""
Innovizer — connecteurs : ingestion des sources vers le substrat.

Chaque connecteur lit une source (fichier ou API) et produit un DataFrame
conforme au schéma de l'entité correspondante dans `innovizer.models`.

  paie       -> payroll (livre de paie)
  bulletins  -> people  (bulletins PDF)
  temps      -> time_entries (suivi des temps)
  ventes     -> revenues (export produits 7xx / Pennylane) — famille IP Box
  fec        -> financial_entries (FEC) — dénominateur IP Box, base Social

À venir : patrimoine -> real_estate (famille fiscalité locale).
"""
