"""
Innovizer — substrat : les neuf entités du system of record.

Six sont alimentées aujourd'hui par la Brique 01 (status="wired"), trois
attendent les familles futures (status="planned") : financial_entries,
revenues (IP Box), real_estate (fiscalité locale). Les colonnes des entités
câblées sont celles que les parsers/moteurs actuels produisent déjà — le
refactor contractualise l'existant, il ne le réécrit pas.
"""

from .schema import Schema, SchemaError

# --- câblées aujourd'hui -----------------------------------------------------

PEOPLE = Schema(
    name="people", key=("person_key",),
    columns={"nom": "str", "matricule": "str", "emploi": "str",
             "classification": "str", "debut_contrat": "str",
             "heures_travaillees": "float", "cout_employeur": "float"},
    source="bulletins de paie (referentiel_salaries)")

PAYROLL = Schema(
    name="payroll", key=("person_key", "mois"),
    columns={"matricule": "str", "nom": "str", "annee": "str",
             "section": "str", "rubrique": "str", "base": "float",
             "montant_salarial": "float", "montant_patronal": "float",
             "montant_total": "float"},
    source="livre de paie (payroll_records)",
    note="cotisations stockées PAR NATURE (une ligne par rubrique) — "
         "non agrégées, pour servir aussi la famille Social")

TIME_ENTRIES = Schema(
    name="time_entries", key=("person_key", "code_projet"),
    columns={"matricule": "str", "jour": "str", "nom_projet": "str",
             "temps": "float", "unite": "str", "heures": "float",
             "mois": "int"},
    source="suivi des temps PayFit (temps.charger)")

SUPPLIERS = Schema(
    name="suppliers", key=("libelle",),
    columns={"libelle": "str", "siren": "str"},
    source="extrait fournisseurs (compta)",
    note="clé = libellé (toujours présent) ; siren nullable (indépendants, "
         "étranger). Le compte auxiliaire 401xxx deviendra la clé naturelle "
         "quand un connecteur FEC/balance alimentera le substrat.")

FIXED_ASSETS = Schema(
    name="fixed_assets", key=("num",),
    columns={"designation": "str", "date_acquisition": "str",
             "duree_mois": "float", "valeur_brute": "float",
             "amort_cumules": "float", "dotation_periode": "float",
             "vnc": "float"},
    source="état des immobilisations / Pennylane")

DOCUMENTS = Schema(
    name="documents", key=("document_id",),
    columns={"type": "str", "fichier": "str", "date": "str",
             "entite": "str", "cle_entite": "str"},
    source="Evidence Hub (evidence.registre)")

# --- familles futures (schéma fixé, source à brancher) -----------------------

FINANCIAL_ENTRIES = Schema(
    name="financial_entries", key=("ligne",),
    columns={"date": "str", "journal": "str", "piece": "str", "compte": "str",
             "libelle": "str", "debit": "float", "credit": "float"},
    source="FEC (fec.financial_records) / Pennylane",
    note="clé = ligne (index technique) ; une écriture équilibrée a plusieurs "
         "lignes, donc 'piece' n'est pas unique et reste une colonne. Pools de "
         "charges 6x/68x = cadrage du dénominateur IP Box et base famille Social.")

REVENUES = Schema(
    name="revenues", key=("ligne",),
    columns={"date": "str", "compte": "str", "libelle": "str",
             "montant": "float", "nature": "str"},
    source="export ventes / Pennylane (comptes 7xx) — ventes.revenues_records",
    note="clé = ligne (index technique stable produit par le connecteur) ; "
         "le rattachement recette↔actif incorporel est une décision portée "
         "par le moteur IP Box, pas par le substrat. Dénominateur des "
         "recettes-cibles IP Box = nature 'redevances_licences' (751).")

REAL_ESTATE = Schema(
    name="real_estate", key=("ref_cadastrale",),
    columns={"adresse": "str", "surface": "float", "usage": "str",
             "valeur": "float", "bases_imposees": "float"},
    source="données patrimoine", status="planned",
    note="famille fiscalité locale")

SUBSTRAT = {s.name: s for s in [
    PEOPLE, PAYROLL, TIME_ENTRIES, SUPPLIERS, FIXED_ASSETS, DOCUMENTS,
    FINANCIAL_ENTRIES, REVENUES, REAL_ESTATE]}

WIRED = {n: s for n, s in SUBSTRAT.items() if s.status == "wired"}
PLANNED = {n: s for n, s in SUBSTRAT.items() if s.status == "planned"}

__all__ = ["Schema", "SchemaError", "SUBSTRAT", "WIRED", "PLANNED",
           "PEOPLE", "PAYROLL", "TIME_ENTRIES", "SUPPLIERS", "FIXED_ASSETS",
           "DOCUMENTS", "FINANCIAL_ENTRIES", "REVENUES", "REAL_ESTATE"]
