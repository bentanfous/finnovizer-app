"""
Innovizer — connecteur VENTES (produits, comptes 7xx) -> substrat `revenues`.

SOURCE
    Export de ventes / grand livre des produits (Pennylane, ou tout logiciel
    comptable exportant les comptes de classe 7). Format attendu, souple :
    une colonne date, une colonne compte, un libellé, un montant. Les noms de
    colonnes varient d'un éditeur à l'autre — on les reconnaît par mot-clé.

SORTIE
    DataFrame conforme au schéma `revenues` (innovizer.models) :
        ligne, date, compte, libelle, montant, nature
    `ligne` : index stable au sein d'un export (clé technique, toujours
    présente). `nature` : dérivée DÉTERMINISTE du compte (voir NATURES).

CE QUE CE CONNECTEUR NE FAIT PAS
    Il ne rattache AUCUNE recette à un actif incorporel (brevet, logiciel).
    Le rattachement actif↔recette, comme la qualification d'un actif éligible
    à l'IP Box, est une décision de conseil portée par le moteur IP Box, pas
    par le substrat. La donnée brute va au substrat ; la qualification va au
    moteur. Le silence n'est jamais une éligibilité.
"""

import re
import pandas as pd

#: préfixe de compte (classe 7) -> nature normalisée.
#: 751 (redevances pour concessions, brevets, licences) est la recette-cible
#: de l'IP Box ; les autres sont transportées mais non présumées éligibles.
NATURES = {
    "751": "redevances_licences",   # concessions de brevets/licences — cœur IP Box
    "706": "prestations_services",
    "707": "ventes_marchandises",
    "705": "etudes",
    "708": "produits_activites_annexes",
    "70":  "ventes",                 # repli classe 70
    "74":  "subventions_exploitation",
    "75":  "autres_produits_gestion",
    "76":  "produits_financiers",
    "77":  "produits_exceptionnels",
    "78":  "reprises_amortissements",
}

_ALIAS = {
    "date": ["date", "date_piece", "date_ecriture", "jour"],
    "compte": ["compte", "compte_num", "numero_compte", "n_compte", "account"],
    "libelle": ["libelle", "libellé", "intitule", "description", "label", "nom"],
    "montant": ["montant", "credit", "crédit", "montant_credit", "amount",
                "montant_ttc", "montant_ht"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def _trouver(colonnes, cles) -> str | None:
    norm = {_norm(c): c for c in colonnes}
    for k in cles:
        if k in norm:
            return norm[k]
    # repli : sous-chaîne
    for k in cles:
        for n, orig in norm.items():
            if k in n:
                return orig
    return None


def load(path: str) -> pd.DataFrame:
    if str(path).lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path, sep=None, engine="python")


def nature_du_compte(compte) -> str:
    """Nature normalisée par préfixe de compte, du plus spécifique au plus
    général (751 avant 75 avant 7). Toute classe ≠ 7 -> 'hors_produits'."""
    c = re.sub(r"\D", "", str(compte))
    if not c.startswith("7"):
        return "hors_produits"
    for p in sorted(NATURES, key=len, reverse=True):
        if c.startswith(p):
            return NATURES[p]
    return "autres_produits"


def revenues_records(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise un export ventes vers le substrat `revenues`.

    - repère les colonnes par mot-clé (formats éditeurs variables) ;
    - ne garde que les comptes de classe 7 (produits) ;
    - dérive la nature du compte ;
    - émet une clé technique `ligne` stable, toujours présente.
    """
    cols = list(df.columns)
    c_date = _trouver(cols, _ALIAS["date"])
    c_cpt = _trouver(cols, _ALIAS["compte"])
    c_lib = _trouver(cols, _ALIAS["libelle"])
    c_mnt = _trouver(cols, _ALIAS["montant"])
    if c_cpt is None or c_mnt is None:
        raise ValueError(
            "export ventes non reconnu : colonnes 'compte' et 'montant' "
            f"introuvables parmi {cols}")

    out = pd.DataFrame({
        "compte": df[c_cpt].astype("string").str.strip(),
        "montant": pd.to_numeric(df[c_mnt], errors="coerce"),
    })
    out["date"] = (df[c_date].astype("string") if c_date else pd.NA)
    out["libelle"] = (df[c_lib].astype("string") if c_lib else pd.NA)
    out["nature"] = out.compte.map(nature_du_compte)

    # produits uniquement (classe 7), montant exploitable
    out = out[(out.nature != "hors_produits") & out.montant.notna()].copy()
    out = out.reset_index(drop=True)
    out.insert(0, "ligne", [f"V{i:06d}" for i in range(len(out))])
    return out[["ligne", "date", "compte", "libelle", "montant", "nature"]]


def agregat_par_nature(rec: pd.DataFrame) -> pd.DataFrame:
    """Chiffre d'affaires par nature — vue de cadrage avant IP Box."""
    g = (rec.groupby("nature").montant.agg(["sum", "count"])
         .rename(columns={"sum": "montant", "count": "lignes"})
         .sort_values("montant", ascending=False).reset_index())
    g["montant"] = g.montant.round(2)
    return g


def charger(chemins: list[str]) -> pd.DataFrame:
    """Un ou plusieurs exports -> substrat revenues concaténé."""
    morceaux = [revenues_records(load(p)) for p in chemins]
    if not morceaux:
        return revenues_records(pd.DataFrame({"compte": [], "montant": []}))
    rec = pd.concat(morceaux, ignore_index=True)
    rec["ligne"] = [f"V{i:06d}" for i in range(len(rec))]  # clé globale re-séquencée
    return rec


def run(path: str):
    rec = revenues_records(load(path))
    return rec, agregat_par_nature(rec)


if __name__ == "__main__":
    import sys
    rec, agg = run(sys.argv[1])
    print(agg.to_string(index=False))
    red = rec[rec.nature == "redevances_licences"].montant.sum()
    print(f"\n{len(rec)} lignes de produits | redevances/licences (751) "
          f"= {red:,.2f} € — recette-cible IP Box")
