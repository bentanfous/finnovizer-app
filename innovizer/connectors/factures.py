"""
Innovizer — connecteur FACTURES fournisseurs (PDF) -> valorisation HT.

La balance fournisseurs (Pennylane) donne la LISTE des prestataires mais pas le
montant par prestataire, et rarement le SIREN. Les factures, elles, portent les
deux : le montant HT et l'identité légale (SIREN via RCS/SIRET/TVA). Ce
connecteur lit les factures, en extrait montant HT, montant TTC, SIREN et
fournisseur, et agrège le HT par fournisseur.

DOUBLE APPORT
    1. Valorisation : somme du HP par fournisseur, pour chiffrer la
       sous-traitance candidate à l'assiette CIR.
    2. Backfill SIREN : le SIREN lu sur la facture complète l'extrait comptable
       qui ne le porte pas — ce qui fait passer un fournisseur de « candidat par
       nom » à « agréé confirmé par SIREN ».

Le connecteur CONSTATE, il ne décide pas de l'éligibilité : un montant HT
facturé n'est éligible que si la prestation est de la R&D sous-traitée à un
organisme agréé, rattachée à une opération — ce que tranche le conseil.
"""

import re
import pandas as pd
import pypdf

# nombre à la française : "28 804,08" / "3 200,00" -> 28804.08 / 3200.00
_NUM = r"\d[\d\s  .]*,\d{2}"


def _num(s) -> float | None:
    if not s:
        return None
    s = re.sub(r"[\s  .]", "", str(s)).replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _champ(texte, motif, flags=re.I):
    m = re.search(motif, texte, flags)
    return m.group(1).strip() if m else None


def parse_facture(path: str) -> dict:
    """Extrait d'une facture PDF : fournisseur, SIREN, n°, date, HT, TTC."""
    texte = pypdf.PdfReader(path).pages[0].extract_text() or ""

    # SIREN : RCS B<9>, à défaut SIRET (9 premiers), à défaut TVA FRxx<9>
    siren = (_champ(texte, r"RCS\s*:?\s*B?\s*(\d{9})")
             or _champ(texte, r"Siret\s*:?\s*(\d{9})")
             or _champ(texte, r"TVA\s*intracom[^\n]*?FR\w{2}(\d{9})"))

    # fournisseur : la raison sociale qui précède la forme juridique + "Capital"
    fournisseur = _champ(
        texte, r"\n?([A-ZÀ-Ÿ][\w&'.\- ]+?)\s+(?:SASU|SAS|SARL|SA|EURL|SNC)\s+Capital")
    if not fournisseur:  # repli : domaine de l'email
        dom = _champ(texte, r"[Ee]mail\s*:?\s*[\w.\-]+@([\w\-]+)\.")
        fournisseur = dom.upper() if dom else None

    ht = _champ(texte, rf"Total\s*HT\s*:\s*Net\s*[àa]\s*payer\s*:\s*({_NUM})")
    if ht is None:  # repli : premier "Total HT" suivi d'un nombre
        ht = _champ(texte, rf"Total\s*HT\s*:?\s*({_NUM})")
    ttc = _champ(texte, rf"Net\s*TTC\s*:\s*({_NUM})")

    return dict(
        fournisseur=fournisseur,
        siren=siren,
        numero=_champ(texte, r"Facture\s*N°\s*(\w+)"),
        date=_champ(texte, r"Date\s*:\s*([^\n]+?)\s*Facture"),
        montant_ht=_num(ht),
        montant_ttc=_num(ttc),
        fichier=path.split("/")[-1],
    )


def charger(paths: list[str]) -> pd.DataFrame:
    """Toutes les factures -> une ligne par facture."""
    lignes = [parse_facture(p) for p in paths]
    return pd.DataFrame(lignes) if lignes else pd.DataFrame(
        columns=["fournisseur", "siren", "numero", "date", "montant_ht",
                 "montant_ttc", "fichier"])


def agreger_par_fournisseur(factures: pd.DataFrame) -> pd.DataFrame:
    """HT cumulé + SIREN (backfill) par fournisseur, pour rattachement à la
    balance. Clé = raison sociale normalisée (le SIREN de la facture est
    conservé pour le rapprochement autoritaire au MESR)."""
    if factures is None or not len(factures):
        return pd.DataFrame(columns=["fournisseur", "siren", "montant_ht", "nb_factures"])
    f = factures.copy()
    f["montant_ht"] = pd.to_numeric(f.montant_ht, errors="coerce").fillna(0.0)
    g = (f.groupby(f.fournisseur.fillna("?"))
         .agg(siren=("siren", lambda s: next((x for x in s if x), None)),
              montant_ht=("montant_ht", "sum"),
              nb_factures=("numero", "count"))
         .reset_index().rename(columns={"index": "fournisseur"}))
    g["montant_ht"] = g.montant_ht.round(2)
    return g.sort_values("montant_ht", ascending=False)


def run(paths):
    f = charger(paths)
    return f, agreger_par_fournisseur(f)
