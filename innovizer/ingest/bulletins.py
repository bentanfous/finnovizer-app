"""
Innovizer — Brique 01 / sous-module BULLETINS
Extraction des bulletins de paie mensuels (PDF texte, un PDF = tous les salariés du mois).

Complète le livre de paie avec ce qu'il ne contient pas :
    emploi, catégorie, classification, date de début de contrat,
    temps travaillé du mois, durée mensuelle contractuelle,
    total versé par l'employeur (coût chargé, directement lisible).

MINIMISATION : le bulletin contient des données personnelles inutiles au CIR
(n° de sécurité sociale, adresse, situation familiale, absences maladie).
Ce parser ne les extrait JAMAIS. Ne pas ajouter de champ sans arbitrage RGPD.
"""

import re
import unicodedata
import pypdf

CHAMPS_INTERDITS = {"n_securite_sociale", "adresse", "absences_maladie"}

MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}


def normalize_key(nom: str) -> str:
    s = unicodedata.normalize("NFKD", str(nom))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z\- ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().upper()


def _num(s):
    """'4 169,57' -> 4169.57 ; '148.2 h' -> 148.2"""
    if s is None:
        return None
    s = str(s).replace("\u202f", " ").replace("\xa0", " ")
    s = re.sub(r"[^0-9,.\- ]", "", s).replace(" ", "")
    if s.count(",") and s.count("."):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _nom(texte: str) -> str | None:
    """Le nom suit le bloc adresse employeur. Le PDF colle parfois
    prénom et NOM ('OussamaAKENNAF') : on réinsère l'espace.
    L'éditeur a changé la mise en page en cours d'année ('75008 PARIS 08'
    -> '75008PARIS 08') : l'ancre tolère l'espace optionnel."""
    m = re.search(r"75008\s*PARIS 08\s*\n(.+)", texte)
    if not m:
        return None
    brut = m.group(1).strip()
    return re.sub(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Ý])", " ", brut).strip()


def _champ(texte, motif, groupe=1):
    m = re.search(motif, texte)
    return m.group(groupe).strip() if m else None


def parse_page(texte: str) -> dict | None:
    if "BULLETIN DE PAIE" not in texte:
        return None
    mat = _champ(texte, r"MATRICULE\s+(\d{3,})")  # vide si absent, jamais 'CODE'
    nom = _nom(texte)
    if not nom:
        return None
    return {
        "person_key": normalize_key(nom),
        "nom": nom,
        "matricule": mat,
        "emploi": _champ(texte, r"EMPLOI\s+(.+)"),
        "categorie": _champ(texte, r"CATEGORIE\s+(.+)"),
        "classification": _champ(texte, r"CLASSIFICATION\s+(.+)"),
        "debut_contrat": _champ(texte, r"Début de contrat:\s*([\d/]+)"),
        "anciennete": _champ(texte, r"[Aa]nciennet[ée]\s*:\s*(.+)"),
        "debut_periode": _champ(texte, r"Début de période:\s*([\d/]+)"),
        "duree_mensuelle_h": _num(_champ(texte, r"Durée mensuelle\s+([\d.,]+)\s*h")),
        "temps_travaille_h": _num(_champ(texte, r"Temps travaillé ce mois\s+([\d.,]+)")),
        "brut_mois": _num(_champ(texte, r"Salaire contractuel\s+([\d\s.,]+)")),
        "total_employeur": _num(_champ(texte, r"Total versé par l'employeur\s+([\d\s.,]+)")),
        "allegement_employeur": _num(
            _champ(texte, r"Allègement de cotisations employeur\s+([\d\s.,]+)")),
    }


def parse_pdf(path: str) -> list:
    """Un PDF mensuel contient N salariés sur ~3 pages chacun.
    On fusionne les pages d'un même salarié (les champs vides sont complétés)."""
    mois = next((v for k, v in MOIS.items() if k in path.lower()), None)
    reader = pypdf.PdfReader(path)
    par_personne = {}
    for page in reader.pages:
        d = parse_page(page.extract_text())
        if not d:
            continue
        d["mois"] = mois
        cle = d["person_key"]
        if cle not in par_personne:
            par_personne[cle] = d
        else:
            for k, v in d.items():
                if par_personne[cle].get(k) in (None, "") and v not in (None, ""):
                    par_personne[cle][k] = v
    return list(par_personne.values())


def parse_annee(paths: list, cache_dir: str | None = None, workers: int = 4):
    """Parse en parallèle, avec cache par fichier (clé = chemin + mtime).

    L'extraction texte de ~140 pages par PDF coûte ~25 s ; sur 12 mois c'est
    5 minutes. Les bulletins ne changent jamais une fois émis : on les parse
    une fois, on garde le résultat."""
    import pandas as pd, json, hashlib, os
    from concurrent.futures import ProcessPoolExecutor

    def cle(p):
        st = os.stat(p)
        return hashlib.md5(f"{p}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()

    lignes, a_parser = [], []
    for p in sorted(paths):
        if cache_dir:
            f = os.path.join(cache_dir, cle(p) + ".json")
            if os.path.exists(f):
                lignes.extend(json.load(open(f))); continue
        a_parser.append(p)

    if a_parser:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for p, res in zip(a_parser, ex.map(parse_pdf, a_parser)):
                lignes.extend(res)
                if cache_dir:
                    os.makedirs(cache_dir, exist_ok=True)
                    json.dump(res, open(os.path.join(cache_dir, cle(p) + ".json"), "w"),
                              ensure_ascii=False)
    return pd.DataFrame(lignes)


def referentiel_salaries(df):
    """Une ligne par salarié : identité + poste le plus récent + heures cumulées."""
    df = df.sort_values("mois")
    g = df.groupby("person_key")
    ref = g.agg(
        nom=("nom", "last"),
        matricule=("matricule", "last"),
        emploi=("emploi", "last"),
        classification=("classification", "last"),
        debut_contrat=("debut_contrat", "last"),
        mois_presence=("mois", "nunique"),
        heures_travaillees=("temps_travaille_h", "sum"),
        cout_employeur=("total_employeur", "sum"),
    ).reset_index()
    ref["emploi_normalise"] = (
        ref.emploi.fillna("").str.upper()
        .str.replace(r"[^A-ZÀ-Ý ]", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True).str.strip()
    )
    return ref.sort_values("cout_employeur", ascending=False)


if __name__ == "__main__":
    import sys
    df = parse_annee(sys.argv[1:])
    ref = referentiel_salaries(df)
    print(f"{len(df)} bulletins | {len(ref)} salariés | "
          f"{ref.heures_travaillees.sum():,.1f} h | "
          f"{ref.cout_employeur.sum():,.2f} €")
