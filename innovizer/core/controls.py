"""
Innovizer — registre des CONTRÔLES.

Chaque contrôle est une fonction pure qui renvoie un dict normalisé :
    code, libelle, attendu, calcule, ecart, statut, detail

STATUTS
    OK           le contrôle passe
    ECART        écart chiffré à corriger
    A_TRAITER    donnée manquante bloquante
    A_VERIFIER   valeur plausible mais atypique, à justifier
    A_ARBITRER   décision de conseil à prendre et à documenter

Un contrôle ne corrige jamais. Il constate, et laisse la décision à l'humain.
C'est ce qui rend la piste d'audit lisible : on voit ce qui a été vu, quand,
et ce qui en a été fait.
"""

import pandas as pd


def _c(code, libelle, attendu, calcule, statut, detail=""):
    ecart = None
    try:
        ecart = round(float(calcule) - float(attendu), 2)
    except (TypeError, ValueError):
        pass
    return dict(code=code, libelle=libelle, attendu=attendu, calcule=calcule,
                ecart=ecart, statut=statut, detail=detail)


# ------------------------------------------------------------------ paie

def reconciliation_paie(df, rec, agg):
    out = []
    st = df[df.is_soustotal].set_index("libelle")
    if "Sous-total Rémunération brute (1)" in st.index:
        ref = float(st.loc["Sous-total Rémunération brute (1)", "montant_total"])
        calc = float(rec[rec.section == "Rémunération brute (1)"].montant_total.sum())
        out.append(_c("P1", "réconciliation brut annuel", round(ref, 2),
                      round(calc, 2), "OK" if abs(calc - ref) < 0.01 else "ECART"))
    tn = df[df.annee.astype(str).str.contains("TOTAL NET", na=False)]
    if len(tn):
        ref = abs(float(tn.montant_patronal.iloc[0]))
        calc = float(rec.montant_patronal.sum())
        out.append(_c("P2", "réconciliation cotisations patronales", round(ref, 2),
                      round(calc, 2), "OK" if abs(calc - ref) < 0.01 else "ECART"))
    sans = agg[agg.matricule.isna()]
    out.append(_c("P3", "matricule absent du SIRH", 0, len(sans),
                  "OK" if not len(sans) else "A_TRAITER",
                  "; ".join(sans.nom.astype(str))))
    return out


def plausibilite_charges(agg, dossier):
    hb = agg[(agg.brut_annuel > 0)
             & (agg.statut_contrat == "salarié")
             & ((agg.taux_charges_pct < dossier.taux_charges_min * 100)
                | (agg.taux_charges_pct > dossier.taux_charges_max * 100))]
    return [_c("P4", "taux de charges hors bornes", 0, len(hb),
               "OK" if not len(hb) else "A_VERIFIER",
               "; ".join(f"{r.nom} ({r.taux_charges_pct}%)" for r in hb.itertuples()))]


# --------------------------------------------------------------- bulletins

def couverture_bulletins(agg, ref):
    out = [_c("B1", "salariés bulletins vs livre de paie", len(agg), len(ref),
              "OK" if len(agg) == len(ref) else "ECART")]
    manque = ref[ref.heures_travaillees.isna() | (ref.heures_travaillees == 0)]
    out.append(_c("B2", "heures travaillées manquantes", 0, len(manque),
                  "OK" if not len(manque) else "A_TRAITER",
                  "; ".join(manque.nom.astype(str))))
    return out


# -------------------------------------------------------------------- temps

def coherence_temps(quotites, annexe_keys):
    tk = set(quotites.person_key)
    manquants = sorted(annexe_keys - tk)
    extra = sorted(tk - annexe_keys)
    return [
        _c("T1", "salariés payés sans temps déclaré", 0, len(manquants),
           "OK" if not manquants else "A_TRAITER", "; ".join(manquants)),
        _c("T2", "temps déclaré sans salarié en paie", 0, len(extra),
           "OK" if not extra else "A_TRAITER", "; ".join(extra)),
        _c("T3", "heures sur projets non classés", 0,
           round(float(quotites.h_non_classe.sum()), 2), "A_ARBITRER",
           f"{int((quotites.h_non_classe > 0).sum())} collaborateurs"),
    ]


def quotites_plausibles(valorisation, dossier):
    """valorisation : person_key, nom, h_valorisees, heures_travaillees"""
    v = valorisation.copy()
    v["quotite"] = (v.h_valorisees / v.heures_travaillees).round(3)
    impossible = v[v.quotite > 1]
    elevee = v[(v.quotite > dossier.seuil_quotite_alerte) & (v.quotite <= 1)]
    return [
        _c("T4", "heures valorisées > heures travaillées", 0, len(impossible),
           "OK" if not len(impossible) else "ECART",
           "; ".join(f"{r.nom} ({r.quotite:.0%})" for r in impossible.itertuples())),
        _c("T5", f"quotité > {dossier.seuil_quotite_alerte:.0%}", 0, len(elevee),
           "OK" if not len(elevee) else "A_VERIFIER",
           "; ".join(f"{r.nom} ({r.quotite:.0%})" for r in elevee.itertuples())),
    ]


def integrite_tableau(tableau, colonnes_valeurs, col_total):
    """Totaux de ligne cohérents avec la somme des cellules."""
    t = tableau.copy()
    t["_recalc"] = t[colonnes_valeurs].sum(axis=1)
    faux = t[(t["_recalc"] - t[col_total]).abs() > 0.005]
    return [_c("T6", "totaux de ligne incohérents", 0, len(faux),
               "OK" if not len(faux) else "ECART",
               "; ".join(f"{r[0]} ({r[col_total]} vs {r['_recalc']})"
                         for _, r in faux.iterrows()))]


# ------------------------------------------------------------ qualification

def qualification_personnel(qualif, valorisation):
    """Tout salarié valorisé doit être ELIGIBLE."""
    val = set(valorisation.loc[valorisation.h_valorisees > 0, "person_key"])
    q = qualif.copy()
    q["ok"] = q.statut.isin(["ELIGIBLE_CONFIRMED", "ELIGIBLE_TECHNICIAN"])
    faux = q[q.person_key.isin(val) & ~q.ok]
    return [_c("Q1", "salariés valorisés sans qualification établie", 0, len(faux),
               "OK" if not len(faux) else "A_TRAITER",
               "; ".join(f"{r.nom} [{r.statut}]" for r in faux.itertuples()))]


# ------------------------------------------------------------ sous-traitance

def coherence_soustraitance(depenses, screening_projets):
    """Le régime de la sous-traitance doit suivre celui de l'opération."""
    reg = dict(zip(screening_projets.thematique_chapeau,
                   screening_projets.regime))
    lignes = []
    for r in depenses.itertuples():
        attendu = reg.get(getattr(r, "operation_rattachee", ""), None)
        decl = getattr(r, "regime_declare", None)
        if attendu and decl and attendu != decl:
            lignes.append(f"{r.prestataire} : déclaré {decl}, opération {attendu}")
    return [_c("S1", "régime sous-traitance ≠ régime de l'opération", 0,
               len(lignes), "OK" if not lignes else "ECART", " ; ".join(lignes))]


# ------------------------------------------------------------------ agrégat

def executer(blocs) -> pd.DataFrame:
    """blocs : liste de listes de dicts de contrôle."""
    plat = [c for bloc in blocs for c in bloc]
    df = pd.DataFrame(plat)
    ordre = {"ECART": 0, "A_TRAITER": 1, "A_VERIFIER": 2, "A_ARBITRER": 3, "OK": 4}
    return df.sort_values("statut", key=lambda s: s.map(ordre)).reset_index(drop=True)
