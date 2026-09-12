"""
Innovizer — Brique 01 / sous-module SUIVI DES TEMPS (connecteur PayFit)

Source : export mensuel PayFit "time-tracking-export-AAAA-M.xlsx".
Structure : onglets 'Avertissement', 'Synthèse', 'Détails', puis un onglet
par projet. SEUL l'onglet 'Détails' est lu — les onglets projet en sont des
vues dérivées, les relire créerait un double comptage.

Grain de 'Détails' : une ligne = collaborateur × jour × projet.

PRINCIPE DE CALCUL
L'export mélange deux unités ('jours' et 'heures') selon le collaborateur.
La conversion jours -> heures se fait via HEURES_PAR_JOUR, paramètre PROPRE AU
CLIENT et non une constante : il découle de la durée hebdomadaire contractuelle
(Dunasys : 39 h/semaine sur 5 jours => 7,8 h/jour). Ne jamais le laisser en dur
dans un calcul : il doit être renseigné et tracé dossier par dossier.
Les quotités R&D restent calculées comme un rapport, donc insensibles à l'unité ;
la conversion sert à produire des volumes horaires comparables et sommables.

La classification des projets n'est PAS automatique. Un préfixe 'INT_' ne
signifie pas 'non R&D' : INT_Maintenance prédictive ou INT_Piles de protocoles
sont des projets internes potentiellement éligibles, INT_RH ne l'est pas.
Tout projet non classé reste NON_CLASSE et sort de l'assiette.
"""

import re
import glob
import unicodedata
import pandas as pd

HEURES_PAR_JOUR = 7.8   # Dunasys : 39 h/semaine sur 5 jours. À redéfinir par client.

COLONNES = ["id_payfit", "matricule", "nom", "prenom", "jour", "code_projet",
            "nom_projet", "temps", "unite", "heure_debut", "heure_fin"]


def normalize_key(nom: str) -> str:
    s = unicodedata.normalize("NFKD", str(nom))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z\- ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().upper()


def charger(dossier_ou_paths) -> pd.DataFrame:
    if isinstance(dossier_ou_paths, str):
        paths = glob.glob(dossier_ou_paths)
    else:
        paths = list(dossier_ou_paths)
    paths = sorted(paths, key=lambda p: int(re.search(r"-(\d+)(?:__\d+_)?\.xlsx$",
                                                      p.replace("_2025", "")).group(1))
                   if re.search(r"-(\d+)", p) else 0)
    blocs = []
    for p in paths:
        m = re.search(r"export-\d{4}-(\d{1,2})", p)
        d = pd.read_excel(p, sheet_name="Détails", header=0)
        if len(d.columns) != len(COLONNES):
            raise ValueError(f"{p}: {len(d.columns)} colonnes, {len(COLONNES)} attendues")
        d.columns = COLONNES
        d["mois"] = int(m.group(1)) if m else None
        d["fichier"] = p.split("/")[-1]
        blocs.append(d)
    a = pd.concat(blocs, ignore_index=True)
    a["temps"] = pd.to_numeric(a.temps, errors="coerce")
    a["heures"] = a.apply(
        lambda r: r.temps * HEURES_PAR_JOUR if str(r.unite).startswith("jour")
        else r.temps, axis=1)
    a["person_key"] = (a.prenom.fillna("") + " " + a.nom.fillna("")).map(normalize_key)
    return a


def referentiel_projets(tt: pd.DataFrame) -> pd.DataFrame:
    """Table de classification à remplir par le conseil.
    classe ∈ {R&D, NON_RD, NON_CLASSE}. Aucune valeur par défaut autre que
    NON_CLASSE : l'absence de décision n'ouvre jamais droit à l'assiette."""
    g = (tt.groupby(["code_projet", "unite"]).heures.sum().unstack(fill_value=0)
         .reset_index())
    g["nb_collaborateurs"] = tt.groupby("code_projet").person_key.nunique().values
    g["classe"] = "NON_CLASSE"
    g["operation_rd"] = ""          # rattachement à l'opération du dossier CIR
    g["justification"] = ""
    return g.sort_values([c for c in ("jours", "heures") if c in g],
                         ascending=False)


#: en deçà de ce taux de couverture, la saisie de temps ne couvre pas assez
#: le temps réellement travaillé : la quotité issue du timesheet n'est pas fiable.
SEUIL_COUVERTURE = 0.80


def quotites(tt: pd.DataFrame, projets: pd.DataFrame,
             heures_travaillees: pd.Series | None = None) -> pd.DataFrame:
    """Quotité R&D par collaborateur.

    Deux dénominateurs, deux usages distincts :

      quotite_declaree = h_rd / h_declarees
          part de R&D DANS le temps saisi. Sert au diagnostic, pas au coût.

      quotite_rd       = h_rd / h_travaillees
          part de R&D dans le temps RÉELLEMENT travaillé (issu des bulletins).
          C'est elle qui s'applique au coût chargé. Si le salarié ne saisit
          pas tout son temps, elle est plus basse que la déclarée — et c'est
          la bonne : on n'impute pas au CIR des heures non travaillées.

      taux_couverture  = h_declarees / h_travaillees
          fiabilité de la saisie. En deçà de SEUIL_COUVERTURE, la répartition
          R&D/non-R&D du timesheet est trop partielle pour être fiable :
          la quotité doit être documentée à l'audit, pas prise telle quelle.

    heures_travaillees : Series person_key -> heures (référentiel bulletins).
    Absente, on retombe sur la quotité déclarée en le signalant.
    """
    m = tt.merge(projets[["code_projet", "classe"]], on="code_projet", how="left")
    m["classe"] = m.classe.fillna("NON_CLASSE")
    piv = (m.pivot_table(index=["person_key", "unite"], columns="classe",
                         values="heures", aggfunc="sum").fillna(0))
    for c in ("R&D", "NON_RD", "NON_CLASSE"):
        if c not in piv:
            piv[c] = 0.0
    piv = piv.reset_index()
    g = piv.groupby("person_key")[["R&D", "NON_RD", "NON_CLASSE"]].sum()
    g.columns = ["h_rd", "h_non_rd", "h_non_classe"]
    g["h_declarees"] = g[["h_rd", "h_non_rd", "h_non_classe"]].sum(axis=1)
    g["quotite_declaree"] = (g.h_rd / g.h_declarees).round(4)
    g["unites"] = piv.groupby("person_key").unite.apply(lambda s: "+".join(sorted(set(s))))

    if heures_travaillees is not None:
        g["h_travaillees"] = g.index.map(heures_travaillees).astype(float)
        g["taux_couverture"] = (g.h_declarees / g.h_travaillees).round(4)
        g["quotite_rd"] = (g.h_rd / g.h_travaillees).round(4)
        g["fiabilite"] = g.taux_couverture.map(
            lambda t: "FIABLE" if t >= SEUIL_COUVERTURE
            else "SAISIE_PARTIELLE" if pd.notna(t) else "SANS_REFERENCE")
    else:
        g["h_travaillees"] = pd.NA
        g["taux_couverture"] = pd.NA
        g["quotite_rd"] = g["quotite_declaree"]
        g["fiabilite"] = "SANS_REFERENCE_HEURES_TRAVAILLEES"
    return g.reset_index()


def controles(tt: pd.DataFrame, q: pd.DataFrame, annexe_keys: set) -> pd.DataFrame:
    out = []
    tk = set(q.person_key)
    out.append({"controle": "T1 collaborateurs suivi temps vs paie",
                "calcule": len(tk), "attendu": len(annexe_keys),
                "statut": "OK" if tk == annexe_keys else "ECART",
                "detail": "paie sans temps : " + "; ".join(sorted(annexe_keys - tk))})
    out.append({"controle": "T2 collaborateurs temps sans paie",
                "calcule": len(tk - annexe_keys), "attendu": 0,
                "statut": "OK" if not (tk - annexe_keys) else "A TRAITER",
                "detail": "; ".join(sorted(tk - annexe_keys))})
    nc = q[q.h_non_classe > 0]
    out.append({"controle": "T3 heures sur projets non classés",
                "calcule": round(float(nc.h_non_classe.sum()), 2), "attendu": 0,
                "statut": "A CLASSER",
                "detail": f"{len(nc)} collaborateurs concernés"})
    out.append({"controle": "T4 matricule absent de l'export temps",
                "calcule": int(tt.matricule.isna().sum()), "attendu": 0,
                "statut": "INFO",
                "detail": "rapprochement fait sur l'ID PayFit et le nom"})
    return pd.DataFrame(out)


def heures_rd(quotites_df: pd.DataFrame, annexe: pd.DataFrame) -> pd.DataFrame:
    """Applique la quotité aux heures travaillées de la paie."""
    a = annexe.copy()
    a["person_key"] = a["Nom - Prénom"].map(normalize_key)
    m = a.merge(quotites_df, on="person_key", how="left")
    m["Heures R&D"] = (m["Nombre d'heures travaillées"] * m.quotite_rd).round(2)
    m["Coût R&D"] = (m["Salaire Annuel Brut Chargé"] * m.quotite_rd).round(2)
    # garde-fou : une quotité issue d'une saisie partielle est signalée
    if "fiabilite" in m:
        m.loc[m.fiabilite != "FIABLE", "Coût R&D"] = m["Coût R&D"]  # valeur gardée mais tracée
    return m
