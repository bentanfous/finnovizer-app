"""
Innovizer — Brique 01 / sous-module ASSIETTE PERSONNEL
Classification des cotisations patronales et construction du tableau
au format "annexe personnel" (Annexe 3 bis).

AVERTISSEMENT DOCTRINAL
Ce module PROPOSE une classification, il ne la décide pas. Le périmètre des
cotisations patronales retenues au CIR relève d'une position à arbitrer par
le conseil et à documenter dans le dossier. Trois classes :
    ELIGIBLE      — cotisations sociales obligatoires ouvrant droit à prestation
    NON_ELIGIBLE  — taxes et participations assises sur les salaires
    A_ARBITRER    — position à trancher explicitement, dossier par dossier
Toute ligne non reconnue tombe en A_ARBITRER : le silence n'est jamais
interprété comme une éligibilité.
"""

import re
import pandas as pd

from ..doctrine import charger, classer_rubrique

#: statut doctrinal -> colonne d'assiette
_MAP = {"ELIGIBLE": "ELIGIBLE", "NON_ELIGIBLE": "NON_ELIGIBLE",
        "TO_REVIEW": "A_ARBITRER"}


def classer(rubrique: str, arbitrages: dict | None = None) -> str:
    """Classement via la doctrine sourcée (doctrine/cir_personnel.yaml).

    arbitrages : décisions de dossier surchargeant un TO_REVIEW, p.ex.
        {"titres_restaurant": "ELIGIBLE"} sur position explicite du conseil.
    """
    d = classer_rubrique(rubrique, charger(), arbitrages)
    return _MAP.get(d["cir_status"], "A_ARBITRER")


def detail_rubrique(rubrique: str, arbitrages: dict | None = None) -> dict:
    """Classement + source, pour la piste d'audit."""
    return classer_rubrique(rubrique, charger(), arbitrages)


def cotisations_par_classe(rec: pd.DataFrame, arbitrages: dict | None = None) -> pd.DataFrame:
    """Ventile les cotisations patronales par salarié et par classe."""
    p = rec[rec.montant_patronal.notna() & (rec.montant_patronal != 0)].copy()
    p["classe"] = p.rubrique.map(lambda x: classer(x, arbitrages))
    return (p.pivot_table(index="person_key", columns="classe",
                          values="montant_patronal", aggfunc="sum")
            .fillna(0).reset_index())


def synthese_classement(rec: pd.DataFrame, arbitrages: dict | None = None) -> pd.DataFrame:
    p = rec[rec.montant_patronal.notna() & (rec.montant_patronal != 0)].copy()
    p["classe"] = p.rubrique.map(lambda x: classer(x, arbitrages))
    p["source"] = p.rubrique.map(lambda x: detail_rubrique(x, arbitrages)["source"])
    p["rubrique_base"] = p.rubrique.str.replace(
        r"\s*\(r[ée]gularisation[^)]*\)", "", regex=True).str.strip()
    s = (p.groupby(["classe", "rubrique_base"]).montant_patronal.sum()
         .round(2).reset_index()
         .sort_values(["classe", "montant_patronal"], ascending=[True, False]))
    return s


# ---------------------------------------------------------------- annexe

COLONNES_ANNEXE = [
    "Nom - Prénom", "Fonction", "Formation/Diplôme", "Année dernier diplôme",
    "Statut", "Coefficient", "Date d'entrée dans l'entreprise",
    "Date de sortie de l'entreprise", "Salaire Annuel Brut",
    "Cotisations Patronales éligibles", "Taux de charges",
    "Salaire Annuel Brut Chargé", "Nombre d'heures payées",
    "Nombre d'heures travaillées", "Taux horaire",
]


def coefficient(categorie: str):
    """Le coefficient Syntec figure dans CATEGORIE ('... - 115 - 2.1').
    Attention : 'MINIMUM COEFFICIENT' du bulletin est un montant en euros,
    pas un coefficient."""
    if not isinstance(categorie, str):
        return None
    m = re.search(r"-\s*(\d{2,3})\s*-\s*([\d.]+)", categorie)
    return f"{m.group(1)} - {m.group(2)}" if m else None


def construire_annexe(agg, ref, cot, bulletins):
    """agg = agrégat livre de paie · ref = référentiel bulletins
    cot = cotisations par classe · bulletins = lignes mensuelles"""
    # heures payées = durée mensuelle contractuelle cumulée sur les mois présents
    payees = (bulletins.dropna(subset=["duree_mensuelle_h"])
              .groupby("person_key").duree_mensuelle_h.sum().rename("heures_payees"))
    sortie = (bulletins.groupby("person_key").mois.max().rename("dernier_mois"))
    categorie = bulletins.sort_values("mois").groupby("person_key").categorie.last()

    df = (agg.merge(ref, on="person_key", how="outer", suffixes=("", "_bul"))
             .merge(cot, on="person_key", how="left")
             .merge(payees, on="person_key", how="left")
             .merge(sortie, on="person_key", how="left")
             .merge(categorie.rename("categorie"), on="person_key", how="left"))

    for c in ["ELIGIBLE", "NON_ELIGIBLE", "A_ARBITRER"]:
        if c not in df:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0)

    out = pd.DataFrame()
    out["Nom - Prénom"] = df.nom.fillna(df.nom_bul)
    out["Fonction"] = df.emploi
    out["Formation/Diplôme"] = ""          # absent des documents de paie
    out["Année dernier diplôme"] = ""      # absent des documents de paie
    out["Statut"] = df.classification
    out["Coefficient"] = df.categorie.map(coefficient)
    out["Date d'entrée dans l'entreprise"] = df.debut_contrat
    out["Date de sortie de l'entreprise"] = df.dernier_mois.map(
        lambda m: "" if pd.isna(m) or m == 12 else f"fin {int(m):02d}/2025 (à confirmer)")
    out["Salaire Annuel Brut"] = df.brut_annuel.round(2)
    out["Cotisations Patronales éligibles"] = df.ELIGIBLE.round(2)
    out["Taux de charges"] = (df.ELIGIBLE / df.brut_annuel).round(4)
    out["Salaire Annuel Brut Chargé"] = (df.brut_annuel + df.ELIGIBLE).round(2)
    out["Nombre d'heures payées"] = df.heures_payees.round(2)
    out["Nombre d'heures travaillées"] = df.heures_travaillees.round(2)
    out["Taux horaire"] = ((df.brut_annuel + df.ELIGIBLE)
                           / df.heures_travaillees).round(2)
    out["_cot_non_eligibles"] = df.NON_ELIGIBLE.round(2)
    out["_cot_a_arbitrer"] = df.A_ARBITRER.round(2)
    return out.sort_values("Salaire Annuel Brut Chargé", ascending=False)
