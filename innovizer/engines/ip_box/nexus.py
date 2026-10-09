"""
Innovizer — IP Box / RATIO NEXUS (art. 238, III du CGI ; BOI-BIC-BASE-110).

Trois fonctions pures (le calcul) + deux fonctions de substrat (la réutilisation
du socle partagé) + une synthèse qui assemble et marque ce qui reste à arbitrer.

    ratio = min(1, uplift × dépenses_éligibles / dépenses_totales)   uplift = 1,3
    base_10% = résultat_net_IP × ratio
    économie = base_10% × (taux_normal − 0,10)

Rien n'est inventé : les dépenses éligibles viennent du substrat (personnel de
R&D déjà qualifié) ; le résultat net et le dénominateur, s'ils ne sont pas
fournis, ne sont PAS présumés — l'indicateur sort en TO_REVIEW.
"""

import pandas as pd

UPLIFT = 1.3            # majoration de 30 % du numérateur, plafonnée par min(…,1)
TAUX_IP_BOX = 0.10
TAUX_IS_NORMAL = 0.25
STATUTS_RD_ELIGIBLE = {"ELIGIBLE_CONFIRMED", "ELIGIBLE_TECHNICIAN"}
NATURE_RECETTE_CIBLE = "redevances_licences"   # compte 751

# --------------------------------------------------------------- calcul pur


def ratio_nexus(depenses_eligibles: float, depenses_totales: float,
                uplift: float = UPLIFT) -> float | None:
    """Ratio Nexus plafonné à 1. None si le dénominateur est inconnu ou nul
    (on ne présume pas un ratio : l'absence de dépenses totales est un trou
    d'instruction, pas un ratio de 1)."""
    if not depenses_totales or depenses_totales <= 0:
        return None
    return min(1.0, uplift * float(depenses_eligibles) / float(depenses_totales))


def base_ip_box(resultat_net_ip: float, ratio: float | None) -> float | None:
    if ratio is None or resultat_net_ip is None:
        return None
    return float(resultat_net_ip) * float(ratio)


def economie_impot(base_10: float | None, taux_normal: float = TAUX_IS_NORMAL,
                   taux_ip_box: float = TAUX_IP_BOX) -> float | None:
    if base_10 is None:
        return None
    return float(base_10) * (float(taux_normal) - float(taux_ip_box))


# ----------------------------------------------- réutilisation du substrat


def depenses_rd_personnel_eligibles(salaries: pd.DataFrame,
                                    qualification: pd.DataFrame) -> dict:
    """Numérateur Nexus (volet personnel) RELU depuis le substrat partagé.

    `salaries`      = substrat people (nom, cout_employeur…)
    `qualification` = sortie du moteur CIR (nom, statut)

    On joint sur `nom` (même source : la qualification est construite à partir
    du référentiel salariés). On somme le coût chargé des personnes dont le
    statut CIR est éligible. AUCUNE nouvelle ingestion : c'est le même euro de
    masse salariale de R&D qui sert le CIR et l'IP Box.
    """
    if salaries is None or qualification is None or not len(qualification):
        return dict(total=0.0, detail=pd.DataFrame(columns=["nom", "statut", "cout_employeur"]),
                    source="substrat people × qualification CIR (aucune donnée)")
    q = qualification[["nom", "statut"]].copy()
    s = salaries[["nom", "cout_employeur"]].copy()
    j = q.merge(s, on="nom", how="left")
    elig = j[j.statut.isin(STATUTS_RD_ELIGIBLE)].copy()
    elig["cout_employeur"] = pd.to_numeric(elig.cout_employeur, errors="coerce").fillna(0.0)
    return dict(
        total=round(float(elig.cout_employeur.sum()), 2),
        detail=elig.sort_values("cout_employeur", ascending=False).reset_index(drop=True),
        source="substrat people × qualification CIR (statuts ELIGIBLE_*)")


def recettes_cibles(revenues: pd.DataFrame,
                    nature: str = NATURE_RECETTE_CIBLE) -> float:
    """Recettes brutes candidates à l'IP Box depuis le substrat revenues —
    par défaut les redevances/licences (compte 751). Recette BRUTE : le
    résultat NET (après charges affectées) reste un arbitrage de conseil."""
    if revenues is None or not len(revenues):
        return 0.0
    r = revenues[revenues.nature == nature]
    return round(float(pd.to_numeric(r.montant, errors="coerce").sum()), 2)


# ------------------------------------------------------------- synthèse


def synthese(revenues: pd.DataFrame, salaries: pd.DataFrame,
             qualification: pd.DataFrame, *,
             resultat_net_ip: float | None = None,
             depenses_totales: float | None = None,
             taux_normal: float = TAUX_IS_NORMAL) -> pd.DataFrame:
    """Assemble les indicateurs IP Box et marque explicitement ce qui exige
    un arbitrage. Chaque ligne : indicateur, valeur, statut, source.

    - numérateur R&D éligible : CALCULÉ (substrat partagé) -> OK
    - recettes 751 brutes : CALCULÉ (substrat revenues) -> OK
    - résultat net IP : si non fourni -> TO_REVIEW (quelles charges imputer)
    - dénominateur dépenses totales : si non fourni -> TO_REVIEW
    - ratio / base / économie : calculés seulement si les arbitrages sont là
    """
    num = depenses_rd_personnel_eligibles(salaries, qualification)
    rec_751 = recettes_cibles(revenues)

    # le résultat net par défaut n'est PAS présumé égal aux recettes brutes
    rni = resultat_net_ip
    ratio = ratio_nexus(num["total"], depenses_totales)
    base = base_ip_box(rni, ratio)
    eco = economie_impot(base, taux_normal)

    def ligne(ind, val, statut, src):
        return dict(indicateur=ind, valeur=val, statut=statut, source=src)

    lignes = [
        ligne("dépenses R&D personnel éligibles (numérateur Nexus)",
              num["total"], "OK", num["source"]),
        ligne("recettes redevances/licences 751 (brutes)",
              rec_751, "OK", "substrat revenues (nature=redevances_licences)"),
        ligne("résultat net IP imposable",
              rni if rni is not None else None,
              "OK" if rni is not None else "TO_REVIEW",
              "fourni" if rni is not None
              else "arbitrage conseil : charges à imputer aux recettes IP"),
        ligne("dépenses totales de l'actif (dénominateur Nexus)",
              depenses_totales if depenses_totales is not None else None,
              "OK" if depenses_totales is not None else "TO_REVIEW",
              "fourni" if depenses_totales is not None
              else "arbitrage conseil : périmètre complet des dépenses de l'actif"),
        ligne("ratio Nexus (plafonné à 1)",
              round(ratio, 4) if ratio is not None else None,
              "OK" if ratio is not None else "TO_REVIEW",
              f"min(1 ; {UPLIFT} × numérateur / dénominateur)"),
        ligne("base imposable à 10 %",
              round(base, 2) if base is not None else None,
              "OK" if base is not None else "TO_REVIEW",
              "résultat net IP × ratio Nexus"),
        ligne(f"économie d'impôt vs {int(taux_normal*100)} %",
              round(eco, 2) if eco is not None else None,
              "OK" if eco is not None else "TO_REVIEW",
              f"base 10 % × ({int(taux_normal*100)}% − {int(TAUX_IP_BOX*100)}%)"),
    ]
    return pd.DataFrame(lignes)
