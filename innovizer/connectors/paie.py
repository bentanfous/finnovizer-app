"""
Innovizer — Brique 01 / sous-module PAIE
Parser de livre de paie (export "détail par salarié") -> modèle de données normalisé.

Sortie : DataFrame payroll_records au format long
    person_key, matricule, nom, mois, annee, section, rubrique,
    base, montant_salarial, montant_patronal

+ agrégat annuel par salarié : brut, cotisations patronales, coût chargé.
+ rapport de contrôles (réconciliation + qualité des identités).

Aucune valeur fiscale n'est décidée ici : ce module ne fait que reconstruire
le coût employeur. L'éligibilité CIR est décidée par un moteur en aval.
"""

import re
import unicodedata
import pandas as pd

COLS = [
    "matricule", "mois", "annee", "salarie", "libelle", "effectif",
    "base", "taux_sal", "montant_salarial", "taux_pat", "montant_patronal",
    "total_taux", "montant_total",
]

SECTION_BRUT = "Rémunération brute (1)"
LIGNE_TOTAL_COMPTE = "Total compte"


def normalize_key(nom: str) -> str:
    """Clé d'identité stable : sans accents, sans espaces multiples, majuscules."""
    s = unicodedata.normalize("NFKD", str(nom))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z\- ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def load(path: str, sheet: str = "Livre de paie") -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, header=0)
    if len(df.columns) != len(COLS):
        raise ValueError(
            f"{len(df.columns)} colonnes lues, {len(COLS)} attendues. "
            "Format d'export non reconnu : ajouter un profil éditeur."
        )
    df.columns = COLS
    for c in ["base", "taux_sal", "montant_salarial", "taux_pat",
              "montant_patronal", "montant_total", "effectif"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def sectionner(df: pd.DataFrame) -> pd.DataFrame:
    """Le livre de paie est trié par rubrique ; les lignes 'Sous-total X'
    ferment une section. On propage la section courante sur chaque ligne."""
    df = df.copy()
    df["is_soustotal"] = df.libelle.astype(str).str.startswith("Sous-total")
    # chaque ligne appartient à la section que FERME le prochain sous-total
    sections, bloc = [], []
    for is_st, lib in zip(df.is_soustotal, df.libelle):
        bloc.append(len(sections))
        sections.append(None)
        if is_st:
            nom = str(lib).replace("Sous-total ", "")
            for i in bloc:
                sections[i] = nom
            bloc = []
    for i in bloc:
        sections[i] = "Hors section"
    df["section"] = sections
    return df


def payroll_records(df: pd.DataFrame) -> pd.DataFrame:
    """Lignes salarié uniquement : ni sous-totaux, ni 'Total compte'."""
    d = df[
        (~df.is_soustotal)
        & (df.salarie.notna())
        & (df.salarie != LIGNE_TOTAL_COMPTE)
    ].copy()
    d["person_key"] = d.salarie.map(normalize_key)
    d["nom"] = d.salarie.str.strip()
    d = d.rename(columns={"libelle": "rubrique"})
    return d[[
        "person_key", "matricule", "nom", "mois", "annee", "section",
        "rubrique", "base", "montant_salarial", "montant_patronal",
        "montant_total",
    ]]


RUBRIQUES_APPRENTISSAGE = r"apprentissage|professionnalisation"


def statut_contrat(rec: pd.DataFrame) -> pd.Series:
    """Détection du contrat d'alternance via les rubriques d'exonération.
    Indicatif : à confirmer par le contrat de travail avant tout usage fiscal."""
    exo = rec[rec.rubrique.str.contains(r"Exon[ée]ration.*apprentissage", case=False,
                                        na=False, regex=True)]
    alternants = set(exo.person_key)
    return pd.Series({k: ("alternant (à confirmer)" if k in alternants else "salarié")
                      for k in rec.person_key.unique()}, name="statut_contrat")


def agregat_annuel(rec: pd.DataFrame) -> pd.DataFrame:
    brut = (rec[rec.section == SECTION_BRUT]
            .groupby("person_key").montant_total.sum().rename("brut_annuel"))
    pat = rec.groupby("person_key").montant_patronal.sum().rename("cot_patronales")
    nom = rec.groupby("person_key").nom.first()
    mat = rec.groupby("person_key").matricule.first()
    mois = rec.groupby("person_key").mois.nunique().rename("mois_presence")

    stat = statut_contrat(rec)
    t = pd.concat([nom, mat, stat, mois, brut, pat], axis=1).fillna(
        {"brut_annuel": 0, "cot_patronales": 0})
    t["cout_charge"] = t.brut_annuel + t.cot_patronales
    t["taux_charges_pct"] = (t.cot_patronales / t.brut_annuel * 100).round(2)
    t.index.name = "person_key"
    return t.sort_values("cout_charge", ascending=False).reset_index()


def controles(df: pd.DataFrame, rec: pd.DataFrame, agg: pd.DataFrame) -> list:
    """Contrôles de réconciliation et de qualité. Chaque anomalie est un dict."""
    out = []
    st = df[df.is_soustotal].set_index("libelle")

    # C1 — le brut recalculé doit égaler le sous-total du fichier
    if "Sous-total Rémunération brute (1)" in st.index:
        ref = float(st.loc["Sous-total Rémunération brute (1)", "montant_total"])
        calc = float(rec[rec.section == SECTION_BRUT].montant_total.sum())
        out.append({
            "controle": "C1 réconciliation brut",
            "attendu": round(ref, 2), "calcule": round(calc, 2),
            "ecart": round(calc - ref, 2),
            "statut": "OK" if abs(calc - ref) < 0.01 else "ECART",
        })

    # C2 — les cotisations patronales recalculées doivent égaler la ligne TOTAL NET
    tn = df[df.annee.astype(str).str.contains("TOTAL NET", na=False)]
    if len(tn):
        ref = abs(float(tn.montant_patronal.iloc[0]))  # le fichier stocke le total en négatif
        calc = float(rec.montant_patronal.sum())
        out.append({
            "controle": "C2 réconciliation cot. patronales",
            "attendu": round(ref, 2), "calcule": round(calc, 2),
            "ecart": round(calc - ref, 2),
            "statut": "OK" if abs(calc - ref) < 0.01 else "ECART",
        })

    # C3 — identité : salariés sans matricule (clé de rapprochement absente)
    sans_mat = agg[agg.matricule.isna()]
    out.append({
        "controle": "C3 matricule manquant",
        "attendu": 0, "calcule": len(sans_mat), "ecart": len(sans_mat),
        "statut": "OK" if len(sans_mat) == 0 else "A TRAITER",
        "detail": "; ".join(sans_mat.nom.tolist()),
    })

    # C4 — brut nul ou négatif
    anomal = agg[agg.brut_annuel <= 0]
    out.append({
        "controle": "C4 brut nul ou négatif",
        "attendu": 0, "calcule": len(anomal), "ecart": len(anomal),
        "statut": "OK" if len(anomal) == 0 else "A TRAITER",
        "detail": "; ".join(anomal.nom.tolist()),
    })

    # C5 — taux de charges hors bornes plausibles (20 % – 60 %)
    hb = agg[(agg.brut_annuel > 0)
             & (agg.statut_contrat == "salarié")
             & ((agg.taux_charges_pct < 20) | (agg.taux_charges_pct > 60))]
    out.append({
        "controle": "C5 taux de charges atypique",
        "attendu": 0, "calcule": len(hb), "ecart": len(hb),
        "statut": "OK" if len(hb) == 0 else "A VERIFIER",
        "detail": "; ".join(f"{r.nom} ({r.taux_charges_pct}%)"
                            for r in hb.itertuples()),
    })
    return out


def run(path: str):
    df = sectionner(load(path))
    rec = payroll_records(df)
    agg = agregat_annuel(rec)
    ctrl = pd.DataFrame(controles(df, rec, agg))
    return rec, agg, ctrl


if __name__ == "__main__":
    import sys
    rec, agg, ctrl = run(sys.argv[1])
    print(ctrl.to_string(index=False))
    print(f"\n{len(agg)} salariés | coût chargé total "
          f"{agg.cout_charge.sum():,.2f} €")
