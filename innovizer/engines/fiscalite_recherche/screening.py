"""
Innovizer — Brique 01 / sous-module SCREENING PROJETS

Trois étages, dans cet ordre. Ne jamais court-circuiter : chaque étage a une
nature différente et une valeur probante différente.

ÉTAGE 1 — FILTRE DE FACTO (automatique)
    Écarte les activités qui ne relèvent en aucun cas de la R&D : commerce,
    RH, administration/finance, logistique, supply chain, support informatique,
    déplacements, salons, CSE. Ce sont des fonctions support, pas des projets.
    Automatisable sans risque parce que le motif d'exclusion est la nature de
    l'activité, pas son contenu technique.

ÉTAGE 2 — SCREENING LARGE (automatique, non décisionnel)
    Tout le reste entre dans le périmètre d'examen, y compris les projets
    clients, les projets internes techniques et les zones grises (Management,
    Qualité, Scrum Master). Le screening ne qualifie rien : il constitue la
    liste à instruire. Un projet qui n'est pas dans cette liste ne pourra pas
    être rattrapé plus tard, donc on ratisse large.

ÉTAGE 3 — AUDIT TECHNIQUE (manuel, jamais automatisé)
    Pour chaque projet retenu au screening, l'audit tranche deux questions
    DISTINCTES, qu'il ne faut pas confondre :
      - ELIGIBILITE    : les travaux relèvent-ils de la R&D (CIR) ou de
                         l'innovation (CII) au sens fiscal ?
      - DEFENDABILITE  : dispose-t-on de la matière technique (verrou, état de
                         l'art, démarche expérimentale, preuves) pour le
                         soutenir en contrôle ?
    Un projet peut être éligible et indéfendable. Dans ce cas il sort de
    l'assiette : c'est une décision de risque, pas une décision de droit.

REGROUPEMENT THÉMATIQUE
    Les projets sont rattachés à une THÉMATIQUE CHAPEAU (opération de R&D au
    sens du dossier), qui agrège plusieurs codes projet partageant le même
    verrou technique. Ce rattachement est une conclusion d'audit, pas une
    donnée d'entrée : il est proposé, jamais déduit du nom du projet.
"""

import re
import pandas as pd

# ---------------------------------------------------------- étage 1

ACTIVITES_SUPPORT = [
    r"^INT_Commerce$", r"^INT_RH$", r"^INT_ADMIN_FI$", r"^INT_Logistique$",
    r"^INT_Supply Chain$", r"^INT_Support informatique$", r"^INT_D[ée]placement$",
    r"^INT_SALONS", r"^INT_CSE$",
]

MOTIF_SUPPORT = ("fonction support — sans lien possible avec des travaux de R&D "
                 "ou d'innovation")


def filtre_de_facto(code_projet: str) -> bool:
    """True si le projet est écarté d'office (étage 1)."""
    return any(re.search(p, str(code_projet), re.I) for p in ACTIVITES_SUPPORT)


# ---------------------------------------------------------- étage 2

COLONNES_AUDIT = [
    "thematique_chapeau",   # opération de R&D proposée
    "regime",               # CIR / CII / MIXTE / HORS
    "eligibilite",          # ELIGIBLE / NON_ELIGIBLE / A_INSTRUIRE
    "defendabilite",        # FORTE / MOYENNE / FAIBLE / A_EVALUER
    "verrou_technique",     # description du verrou — vide tant que non instruit
    "preuves_disponibles",
    "decision",             # RETENU / ECARTE / EN_ATTENTE
    "commentaire_audit",
]

VALEURS = {
    "regime": ["CIR", "CII", "MIXTE", "HORS", "A_DETERMINER"],
    "eligibilite": ["ELIGIBLE", "NON_ELIGIBLE", "A_INSTRUIRE"],
    "defendabilite": ["FORTE", "MOYENNE", "FAIBLE", "A_EVALUER"],
    "decision": ["RETENU", "ECARTE", "EN_ATTENTE"],
}


def screening(tt: pd.DataFrame, amorce: pd.DataFrame | None = None) -> pd.DataFrame:
    """Construit le référentiel de screening à partir du suivi des temps.

    amorce : table optionnelle (code_projet, thematique_chapeau, commentaire)
    reprenant un classement déjà établi sur un exercice précédent. Elle
    PRÉ-REMPLIT la thématique ; elle ne vaut pas décision d'audit, et toutes
    les colonnes de décision restent à instruire.
    """
    g = (tt.groupby("code_projet")
           .agg(heures=("heures", "sum"),
                collaborateurs=("person_key", "nunique"),
                premier_mois=("mois", "min"),
                dernier_mois=("mois", "max"))
           .reset_index())
    g["heures"] = g.heures.round(2)
    g["etage_1_support"] = g.code_projet.map(filtre_de_facto)
    g["statut_screening"] = g.etage_1_support.map(
        lambda x: "ECARTE_DE_FACTO" if x else "A_INSTRUIRE")
    g["motif_ecart"] = g.etage_1_support.map(lambda x: MOTIF_SUPPORT if x else "")

    for c in COLONNES_AUDIT:
        g[c] = ""
    g.loc[g.etage_1_support, "decision"] = "ECARTE"
    g.loc[g.etage_1_support, "eligibilite"] = "NON_ELIGIBLE"
    g.loc[~g.etage_1_support, "decision"] = "EN_ATTENTE"
    g.loc[~g.etage_1_support, "eligibilite"] = "A_INSTRUIRE"
    g.loc[~g.etage_1_support, "defendabilite"] = "A_EVALUER"
    g.loc[~g.etage_1_support, "regime"] = "A_DETERMINER"

    if amorce is not None:
        m = dict(zip(amorce.code_projet, amorce.thematique_chapeau))
        c = dict(zip(amorce.code_projet, amorce.get("commentaire", "")))
        g["thematique_chapeau"] = g.apply(
            lambda r: "" if r.etage_1_support else m.get(r.code_projet, ""), axis=1)
        g["commentaire_audit"] = g.code_projet.map(lambda k: c.get(k, ""))

    return g.drop(columns=["etage_1_support"]).sort_values(
        ["statut_screening", "heures"], ascending=[True, False])


def apparier_amorce(tt: pd.DataFrame, liste_projets: pd.DataFrame) -> pd.DataFrame:
    """Rapproche les codes PayFit d'une liste de screening antérieure.

    Les intitulés diffèrent (PayFit 'INT_DCar-S' vs dossier 'DCar-S (ex DCar-4G)').
    La clé d'appariement retenue est le VOLUME HORAIRE, qui est identique des
    deux côtés dès lors que la conversion jours->heures est la même. Un volume
    qui correspond à plusieurs projets n'est pas apparié automatiquement :
    l'ambiguïté est signalée, jamais tranchée.
    """
    ref = tt.groupby("code_projet").heures.sum().round(2)
    lp = liste_projets.copy()
    lp["heures"] = pd.to_numeric(lp.heures, errors="coerce").round(2)

    index = {}
    for r in lp.itertuples():
        index.setdefault(r.heures, []).append((r.projet, r.thematique))

    lignes = []
    for code, h in ref.items():
        cand = index.get(round(h, 2), [])
        if len(cand) == 1:
            lignes.append(dict(code_projet=code, heures=h,
                               projet_dossier=cand[0][0],
                               thematique_chapeau=cand[0][1] if pd.notna(cand[0][1]) else "",
                               appariement="UNIQUE"))
        elif len(cand) > 1:
            lignes.append(dict(code_projet=code, heures=h,
                               projet_dossier=" | ".join(c[0] for c in cand),
                               thematique_chapeau="",
                               appariement="AMBIGU — à trancher"))
        else:
            lignes.append(dict(code_projet=code, heures=h, projet_dossier="",
                               thematique_chapeau="", appariement="ABSENT"))
    return pd.DataFrame(lignes)
