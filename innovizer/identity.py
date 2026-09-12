"""
Innovizer — couche IDENTITÉ & RÉCONCILIATION.

Sans elle on a des connecteurs. Avec elle on a un system of record.

Trois problèmes distincts, trois traitements :

  PERSONNES   Le même salarié apparaît sous des formes divergentes selon le
              système : « Ramla BEN ABDELKADER » en paie, « RAMLA ABDELKADER »
              dans PayFit, « MARGUERITE-MARIE PASQUERON DE » tronqué par un
              retour à la ligne de PDF. La normalisation absorbe la casse, les
              accents et les espaces multiples ; le reste passe par une table
              d'alias EXPLICITE, tenue dans la config du dossier.
              On ne rapproche jamais deux personnes sur une similarité
              approximative : un faux positif fusionne deux salariés et fausse
              l'assiette sans laisser de trace.

  FOURNISSEURS Clé = SIREN, exclusivement. Un rapprochement sur la raison
              sociale produit des faux positifs (« ATLAS », « VERSION ») et des
              faux négatifs (nom commercial ≠ raison sociale). Quand le SIREN
              est absent de l'extrait comptable, le résultat n'est pas
              « non agréé » mais « vérification impossible ».

  PROJETS     Les intitulés divergent entre l'outil de saisie et le dossier
              (« INT_DCar-S » vs « DCar-S (ex DCar-4G) - Car sharing 1 »).
              La clé retenue est le VOLUME HORAIRE, identique des deux côtés
              dès lors que la conversion jours→heures est la même. Une valeur
              qui correspond à plusieurs projets n'est pas appariée : on
              signale l'ambiguïté, on ne la tranche pas.
"""

import re
import unicodedata
import pandas as pd


def cle_personne(nom: str, alias: dict | None = None) -> str:
    """Clé d'identité : sans accents, sans ponctuation, espaces réduits, majuscules."""
    s = unicodedata.normalize("NFKD", str(nom))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z\- ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().upper()
    return (alias or {}).get(s, s)


def cle_siren(valeur) -> str | None:
    """Normalise un SIREN sur 9 chiffres. Accepte un SIRET (14) et le tronque."""
    if valeur is None:
        return None
    v = str(valeur)
    if v.endswith(".0"):
        v = v[:-2]
    d = re.sub(r"\D", "", v)
    if len(d) == 14:
        d = d[:9]
    return d.zfill(9) if len(d) == 9 else None


def rapprocher_personnes(*tables, alias: dict | None = None) -> pd.DataFrame:
    """Table de correspondance entre sources.

    tables : (nom_source, DataFrame avec colonne 'nom')
    Renvoie une ligne par personne avec sa présence dans chaque source.
    """
    presence = {}
    for source, df in tables:
        for n in df["nom"].dropna().unique():
            k = cle_personne(n, alias)
            presence.setdefault(k, {"person_key": k})
            presence[k][source] = n
    out = pd.DataFrame(presence.values())
    sources = [s for s, _ in tables]
    for s in sources:
        if s not in out:
            out[s] = None
    out["nb_sources"] = out[sources].notna().sum(axis=1)
    out["complet"] = out.nb_sources == len(sources)
    return out.sort_values(["complet", "person_key"])


def apparier_par_volume(gauche: pd.Series, droite: pd.DataFrame,
                        col_cle: str, col_valeur: str,
                        tolerance: float = 0.01) -> pd.DataFrame:
    """Apparie deux nomenclatures de projets par volume horaire.

    gauche : Series indexée par code projet -> heures
    droite : DataFrame avec col_cle (intitulé) et col_valeur (heures)
    """
    index = {}
    for r in droite.itertuples():
        v = getattr(r, col_valeur)
        if pd.notna(v):
            index.setdefault(round(float(v), 2), []).append(getattr(r, col_cle))

    lignes = []
    for code, h in gauche.items():
        cand = index.get(round(float(h), 2), [])
        lignes.append(dict(
            code_source=code, heures=round(float(h), 2),
            correspondance=cand[0] if len(cand) == 1 else " | ".join(cand),
            statut=("UNIQUE" if len(cand) == 1
                    else "AMBIGU" if cand else "ABSENT")))
    return pd.DataFrame(lignes)
