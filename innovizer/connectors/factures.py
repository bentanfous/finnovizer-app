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

import os
import re
import pandas as pd
import pypdf

# nombre à la française, séparateur de milliers espace OU point :
# "28 804,08", "3 200,00", "3.394,75" -> 28804.08 / 3200.00 / 3394.75
_NUM = r"\d[\d\s  .]*,\d{2}"

#: emails à ignorer pour déduire le fournisseur (client, messageries génériques)
_EMAILS_IGNORES = {"dunasys", "gmail", "outlook", "hotmail", "yahoo",
                   "bureauveritas", "wanadoo", "orange", "free"}


def _num(s) -> float | None:
    if not s:
        return None
    s = re.sub(r"[\s  .]", "", str(s)).replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _premier(texte, motifs, flags=re.I | re.S):
    """Premier motif qui matche, dans l'ordre (robustesse multi-éditeurs)."""
    for m in motifs:
        r = re.search(m, texte, flags)
        if r:
            return r.group(1).strip()
    return None


def _siren(texte) -> str | None:
    """SIREN (9 chiffres) depuis RCS, SIRET ou TVA intracom, en tolérant les
    espaces (« 408 363 174 ») et le préfixe B."""
    brut = _premier(texte, [
        r"RCS[^\n]*?\bB?\s*([\d][\d\s]{8,16})",
        r"SIRET\s*:?\s*([\d][\d\s]{8,18})",
        r"TVA[^\n]*?FR\s*[0-9A-Z]{2}\s*([\d][\d\s]{8,14})",
    ])
    if not brut:
        return None
    digits = re.sub(r"\D", "", brut)
    return digits[:9] if len(digits) >= 9 else None


def _fournisseur(texte, path) -> str | None:
    """Raison sociale : domaine d'email émetteur (générique, marche pour LCIE
    comme Savelec), à défaut nom avant la forme juridique, à défaut nom de
    fichier."""
    for dom in re.findall(r"[\w.\-]+@([\w\-]+)\.", texte):
        if dom.lower() not in _EMAILS_IGNORES:
            return dom.upper()
    nom = _premier(texte, [
        r"\n([A-ZÀ-Ÿ][\w&'.\- ]{2,40}?)\s+(?:SASU|SAS|SARL|SA|EURL|SNC)\s+(?:au\s+)?[Cc]apital"])
    if nom:
        return nom
    m = re.search(r"([A-Z]{3,})", os.path.basename(path))
    return m.group(1) if m else None


def parse_facture(path: str) -> dict:
    """Extrait d'une facture PDF : fournisseur, SIREN, n°, date, HT, TTC.
    Robuste à plusieurs mises en page (Savelec/PayFit, LCIE…) par cascade de
    motifs ; constate sans conclure sur l'éligibilité."""
    # toutes les pages : certains éditeurs (LCIE) portent les totaux en page 2
    texte = "\n".join((pg.extract_text() or "")
                      for pg in pypdf.PdfReader(path).pages)

    ht = _premier(texte, [
        rf"Total\s*HT\s*:\s*Net\s*[àa]\s*payer\s*:\s*({_NUM})",   # Savelec
        rf"Total\s*HT\s*:?[\s\S]{{0,40}}?({_NUM})",               # LCIE / générique
        rf"Montant\s*HT\s*:?[\s\S]{{0,30}}?({_NUM})",
    ])
    ttc = _premier(texte, [
        rf"Net\s*TTC\s*:\s*({_NUM})",                             # Savelec
        rf"Total\s*TTC[^\d\n]*({_NUM})",                          # LCIE
        rf"Net\s*[àa]\s*payer\s*:?[\s\S]{{0,30}}?({_NUM})",
    ])
    return dict(
        fournisseur=_fournisseur(texte, path),
        siren=_siren(texte),
        numero=_premier(texte, [r"Facture\s*N°\s*(\w+)", r"Facture\s*(RI\s*\w+)"]),
        date=_premier(texte, [r"Date\s*:\s*([^\n]+?)\s*(?:Facture|Date)",
                              r"Date\s*:?\s*(\d{2}/\d{2}/\d{4})"]),
        montant_ht=_num(ht),
        montant_ttc=_num(ttc),
        fichier=os.path.basename(path),
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
