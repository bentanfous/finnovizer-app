"""
Innovizer — connecteur FEC -> substrat `financial_entries`.

SOURCE
    Fichier des Écritures Comptables (FEC, art. A47 A-1 du LPF) : 18 champs
    normalisés, séparés par tabulation ou pipe, encodage souvent Latin-1. Les
    noms de champs sont standard (JournalCode, CompteNum, Debit…) ; on les
    reconnaît, avec repli tolérant sur un export Excel.

SORTIE
    DataFrame conforme au schéma `financial_entries` :
        ligne, date, journal, piece, compte, libelle, debit, credit
    `ligne` : clé technique stable (une écriture équilibrée a plusieurs lignes,
    donc `piece` n'est PAS une clé unique — elle reste une colonne).

CE QUE CE CONNECTEUR NE FAIT PAS
    Aucune imputation analytique ni rattachement à un actif ou à un projet :
    le FEC brut n'en porte généralement pas. Les pools de charges par classe
    de compte sont un simple cadrage (la donnée brute), pas une qualification.
    L'attribution reste un acte de conseil porté par les moteurs.
"""

import re
import pandas as pd

#: champs FEC standard (ordre officiel), en clés normalisées.
FEC_CHAMPS = ["journalcode", "journallib", "ecriturenum", "ecrituredate",
              "comptenum", "comptelib", "compauxnum", "compauxlib", "pieceref",
              "piecedate", "ecriturelib", "debit", "credit", "ecriturelet",
              "datelet", "validdate", "montantdevise", "idevise"]

_ALIAS = {
    "date": ["ecrituredate", "date", "piecedate"],
    "journal": ["journalcode", "journal"],
    "piece": ["ecriturenum", "pieceref", "piece", "num"],
    "compte": ["comptenum", "compte", "account"],
    "libelle": ["ecriturelib", "comptelib", "libelle", "intitule"],
    "debit": ["debit"],
    "credit": ["credit"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def _trouver(colonnes, cles):
    norm = {_norm(c): c for c in colonnes}
    for k in cles:
        if k in norm:
            return norm[k]
    for k in cles:
        for n, orig in norm.items():
            if k in n:
                return orig
    return None


def _nombre(s):
    """FEC : décimale virgule ou point, parfois signe en fin. -> float."""
    return pd.to_numeric(
        s.astype("string").str.replace(r"\s", "", regex=True)
         .str.replace(",", ".", regex=False), errors="coerce").fillna(0.0)


def load(path: str) -> pd.DataFrame:
    if str(path).lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path, dtype=str)
    # FEC texte : séparateur tab ou pipe, encodage à tester
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(path, sep=None, engine="python", dtype=str,
                               encoding=enc)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    return pd.read_csv(path, sep="\t", dtype=str, encoding="latin-1")


def financial_records(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise un FEC vers le substrat `financial_entries`."""
    cols = list(df.columns)
    c_cpt = _trouver(cols, _ALIAS["compte"])
    c_deb = _trouver(cols, _ALIAS["debit"])
    c_cre = _trouver(cols, _ALIAS["credit"])
    if c_cpt is None or (c_deb is None and c_cre is None):
        raise ValueError(
            f"FEC non reconnu : compte/debit/credit introuvables parmi {cols}")

    c_date = _trouver(cols, _ALIAS["date"])
    c_jnl = _trouver(cols, _ALIAS["journal"])
    c_pce = _trouver(cols, _ALIAS["piece"])
    c_lib = _trouver(cols, _ALIAS["libelle"])

    out = pd.DataFrame({
        "compte": df[c_cpt].astype("string").str.strip(),
        "debit": _nombre(df[c_deb]) if c_deb else 0.0,
        "credit": _nombre(df[c_cre]) if c_cre else 0.0,
    })
    out["date"] = df[c_date].astype("string") if c_date else pd.NA
    out["journal"] = df[c_jnl].astype("string") if c_jnl else pd.NA
    out["piece"] = df[c_pce].astype("string") if c_pce else pd.NA
    out["libelle"] = df[c_lib].astype("string") if c_lib else pd.NA
    out = out[out.compte.notna() & (out.compte.str.strip() != "")].reset_index(drop=True)
    out.insert(0, "ligne", [f"E{i:07d}" for i in range(len(out))])
    return out[["ligne", "date", "journal", "piece", "compte", "libelle",
                "debit", "credit"]]


#: classe de compte (1er chiffre / préfixe) -> nature, pour le cadrage charges.
CLASSES_CHARGES = {
    "60": "achats",
    "61": "services_exterieurs",
    "62": "autres_services_exterieurs",
    "63": "impots_taxes",
    "64": "charges_personnel",
    "65": "autres_charges_gestion",
    "68": "dotations_amortissements",
}


def pools_par_classe(rec: pd.DataFrame) -> pd.DataFrame:
    """Cadrage : solde (débit − crédit) des charges par classe de compte 6x
    et des dotations 68x. Vue brute, non qualifiée — utile au dénominateur
    IP Box et à la famille Social, jamais une imputation par actif."""
    r = rec.copy()
    r["c2"] = r.compte.astype("string").str.replace(r"\D", "", regex=True).str[:2]
    r = r[r.c2.isin(CLASSES_CHARGES)]
    g = (r.groupby("c2").apply(
            lambda x: round(float(x.debit.sum() - x.credit.sum()), 2),
            include_groups=False)
         .rename("solde").reset_index())
    g["nature"] = g.c2.map(CLASSES_CHARGES)
    return g[["c2", "nature", "solde"]].sort_values("c2").reset_index(drop=True)


def charger(chemins: list[str]) -> pd.DataFrame:
    morceaux = [financial_records(load(p)) for p in chemins]
    if not morceaux:
        return financial_records(pd.DataFrame({"comptenum": [], "debit": [], "credit": []}))
    rec = pd.concat(morceaux, ignore_index=True)
    rec["ligne"] = [f"E{i:07d}" for i in range(len(rec))]
    return rec


def run(path: str):
    rec = financial_records(load(path))
    return rec, pools_par_classe(rec)


if __name__ == "__main__":
    import sys
    rec, pools = run(sys.argv[1])
    print(pools.to_string(index=False))
    print(f"\n{len(rec)} écritures | charges 6x "
          f"{pools[pools.c2.str.startswith('6')].solde.sum():,.2f} €")
