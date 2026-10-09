"""
Innovizer — Brique 01 / sous-module BULLETINS
Extraction des bulletins de paie (PDF texte). Deux organisations de fichiers
sont gérées indifféremment, le mois étant lu DANS le contenu de chaque bulletin :
    option 2 — un PDF = un mois, tous les salariés (cas Dunasys) ;
    option 1 — un PDF = un salarié, ses 12 bulletins mensuels de l'année.
Les entrées/sorties en cours d'année sont correctes : un salarié n'est agrégé
que sur les mois où il a effectivement un bulletin (mois_presence réel).

Complète le livre de paie avec ce qu'il ne contient pas :
    emploi, catégorie, classification, date de début de contrat,
    temps travaillé du mois, durée mensuelle contractuelle,
    total versé par l'employeur (coût chargé, directement lisible).

MINIMISATION : le bulletin contient des données personnelles inutiles au CIR
(n° de sécurité sociale, adresse, situation familiale, absences maladie).
Ce parser ne les extrait JAMAIS. Ne pas ajouter de champ sans arbitrage RGPD.
"""

import os
import re
import unicodedata
import pandas as pd
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


def _mois_du_texte(texte: str) -> int | None:
    """Mois de la période de paie, LU DANS LE CONTENU du bulletin (et non dans
    le nom de fichier). C'est ce qui permet de traiter indifféremment :
      - option 2 : un PDF = un mois, tous les salariés (toutes les pages ont le
        même mois) ;
      - option 1 : un PDF = un salarié, toute l'année (chaque bulletin mensuel
        porte son propre mois).
    Priorité à la date de début de période (JJ/MM/AAAA), repli sur le nom du
    mois en toutes lettres."""
    m = re.search(r"D[ée]but de p[ée]riode\s*:?\s*\d{2}/(\d{2})/\d{4}", texte)
    if m:
        return int(m.group(1))
    for nom, num in MOIS.items():
        if re.search(rf"\b{re.escape(nom)}\b", texte, re.I):
            return num
    return None


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
        "mois": _mois_du_texte(texte),   # mois lu dans le bulletin (options 1 & 2)
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
    """Extrait un enregistrement par (salarié, mois).

    Le mois vient du CONTENU de chaque bulletin, avec repli sur le mois déduit
    du nom de fichier (utile en option 2 si une page n'a pas la période). On
    regroupe par (salarié, mois) — pas seulement par salarié — pour que
    l'option 1 (un PDF = un salarié sur 12 mois) produise bien 12 lignes et non
    une seule. Les pages d'un même bulletin se complètent (champs vides)."""
    mois_fichier = next(
        (v for k, v in MOIS.items() if k in os.path.basename(path).lower()), None)
    reader = pypdf.PdfReader(path)
    par_cle = {}
    for page in reader.pages:
        d = parse_page(page.extract_text())
        if not d:
            continue
        d["mois"] = d.get("mois") or mois_fichier
        cle = (d["person_key"], d["mois"])
        if cle not in par_cle:
            par_cle[cle] = d
        else:
            for k, v in d.items():
                if par_cle[cle].get(k) in (None, "") and v not in (None, ""):
                    par_cle[cle][k] = v
    return list(par_cle.values())


def parse_annee(paths: list, cache_dir: str | None = None, workers: int | None = None):
    """Parse en parallèle, avec cache par fichier (clé = chemin + mtime).

    L'extraction texte de ~140 pages par PDF coûte ~25 s ; sur 12 mois c'est
    5 minutes. Les bulletins ne changent jamais une fois émis : on les parse
    une fois, on garde le résultat.

    MÉMOIRE : chaque worker charge un PDF entier (plusieurs dizaines de Mo en
    pointe). Pour ne pas saturer un conteneur contraint (Railway), le nombre de
    workers est volontairement bas et réglable via INNOVIZER_PDF_WORKERS
    (défaut 2), borné au nombre de fichiers ; en cas d'échec du pool, repli
    séquentiel."""
    import pandas as pd, json, hashlib, os
    from concurrent.futures import ProcessPoolExecutor

    if workers is None:
        try:
            workers = max(1, int(os.environ.get("INNOVIZER_PDF_WORKERS", "2")))
        except ValueError:
            workers = 2

    def cle(p):
        st = os.stat(p)
        return hashlib.md5(f"{p}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()

    lignes, a_parser = [], []
    for p in sorted(paths):
        if cache_dir:
            f = os.path.join(cache_dir, cle(p) + ".json")
            if os.path.exists(f):
                cached = json.load(open(f))
                if cached:                      # un cache VIDE est ignoré (poison)
                    lignes.extend(cached); continue
        a_parser.append(p)

    if a_parser:
        workers = max(1, min(workers, len(a_parser)))
        try:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                resultats = list(ex.map(parse_pdf, a_parser))
        except Exception:  # noqa: BLE001
            # Certains conteneurs (quotas, /dev/shm restreint) ne peuvent pas
            # forker de workers : repli séquentiel, plus lent mais fiable.
            resultats = [parse_pdf(p) for p in a_parser]
        for p, res in zip(a_parser, resultats):
            lignes.extend(res)
            # On ne met en cache QUE du non-vide : un parsing raté ne doit
            # jamais empoisonner le volume persistant et figer les builds suivants.
            if cache_dir and res:
                os.makedirs(cache_dir, exist_ok=True)
                json.dump(res, open(os.path.join(cache_dir, cle(p) + ".json"), "w"),
                          ensure_ascii=False)
    return pd.DataFrame(lignes)


#: colonnes du référentiel salariés (substrat people enrichi).
_COLS_REF = ["person_key", "nom", "matricule", "emploi", "classification",
             "debut_contrat", "mois_presence", "heures_travaillees",
             "cout_employeur", "emploi_normalise"]


def referentiel_salaries(df):
    """Une ligne par salarié : identité + poste le plus récent + heures cumulées.

    Robuste à un parsing vide : si aucun bulletin n'a été exploité (format non
    reconnu, PDF scanné sans couche texte), on renvoie un référentiel vide aux
    bonnes colonnes plutôt que de planter — l'appelant constate l'absence."""
    if df is None or not len(df) or "mois" not in df.columns:
        return pd.DataFrame(columns=_COLS_REF)
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
