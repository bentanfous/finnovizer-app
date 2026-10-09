"""
Innovizer — IP Box / RATTACHEMENT RECETTE↔ACTIF et DÉPENSES↔ACTIF.

L'IP Box se calcule PAR ACTIF incorporel éligible (art. 238, II-III du CGI) :
chaque brevet, logiciel ou COV a son propre résultat net et son propre ratio
Nexus. Ce module fait passer la synthèse d'un niveau firme à un niveau actif.

DEUX RATTACHEMENTS, DEUX NATURES
    recette↔actif   : quelle redevance/cession se rapporte à quel actif.
                      N'existe PAS dans l'export brut — c'est un arbitrage de
                      conseil (fourni en clair, ou via une table ligne→actif).
    dépense R&D↔actif : quelle R&D a développé quel actif. Là, le substrat
                      PARTAGÉ suffit : le temps passé par projet (time_entries)
                      mappé projet→actif répartit le coût R&D éligible déjà
                      calculé pour le CIR. Aucune ressaisie : la quotité R&D
                      d'une personne, son coût chargé et ses heures par projet
                      viennent tous du socle.

RÈGLE
    Ce qui n'est pas rattaché n'est pas présumé. Un actif sans dénominateur ou
    sans résultat net fourni sort en TO_REVIEW ; un projet ou une recette non
    mappé est constaté, pas réparti au hasard. Le silence n'est jamais une
    éligibilité.
"""

import pandas as pd

from . import nexus


# ------------------------------------------- dépenses R&D éligibles par actif

def rd_eligible_par_actif(temps: pd.DataFrame,
                          cout_par_personne: dict | pd.Series,
                          map_projets: dict) -> dict:
    """Répartit le coût chargé des personnes R&D éligibles sur les actifs, au
    prorata des heures que chaque personne a passées sur les projets rattachés
    à chaque actif, RAPPORTÉES À SON TEMPS TOTAL.

    temps             : substrat time_entries [person_key, code_projet, heures]
    cout_par_personne : person_key -> coût chargé éligible (MÊME base que le
                        numérateur firm-level ; non éligibles déjà exclus)
    map_projets       : code_projet -> actif_id (arbitrage conseil)

    part(p, a) = heures(p sur projets de a) / heures totales(p)   → somme ≤ 1
    coût(p, a) = coût(p) × part(p, a)

    Le dénominateur est le temps TOTAL de la personne (projets mappés ou non) :
    le temps non rattaché à un actif déclaré n'est attribué à aucun — la somme
    par actif conserve donc le numérateur firm-level SANS jamais le dépasser.
    Rien n'est présumé : un projet non mappé est constaté, pas réparti.

    Retour : {par_actif: DataFrame[actif_id, cout_rd_eligible],
              detail: DataFrame[person_key, actif_id, heures, cout_rd],
              projets_non_mappes: [code_projet…]}"""
    cout = pd.Series(cout_par_personne, dtype="float64")
    t = temps.copy()
    t["heures"] = pd.to_numeric(t.heures, errors="coerce").fillna(0.0)

    # heures TOTALES par personne (toutes lignes de temps) = dénominateur
    h_total = t.groupby("person_key").heures.sum()

    t["actif_id"] = t.code_projet.map(map_projets)
    projets_non_mappes = sorted(
        set(t.loc[t.actif_id.isna(), "code_projet"].dropna().astype(str)))

    t = t[t.actif_id.notna() & t.person_key.isin(cout.index)].copy()
    if not len(t):
        return dict(
            par_actif=pd.DataFrame(columns=["actif_id", "cout_rd_eligible"]),
            detail=pd.DataFrame(columns=["person_key", "actif_id", "heures", "cout_rd"]),
            projets_non_mappes=projets_non_mappes)

    h_pa = t.groupby(["person_key", "actif_id"]).heures.sum().reset_index()
    denom = h_pa.person_key.map(h_total).astype(float)
    h_pa["part"] = (h_pa.heures / denom).where(denom > 0, 0.0)
    h_pa["cout_rd"] = (h_pa.person_key.map(cout).astype(float) * h_pa.part).round(2)

    par_actif = (h_pa.groupby("actif_id").cout_rd.sum().round(2)
                 .rename("cout_rd_eligible").reset_index())
    detail = h_pa[["person_key", "actif_id", "heures", "cout_rd"]].sort_values(
        ["actif_id", "cout_rd"], ascending=[True, False]).reset_index(drop=True)
    return dict(par_actif=par_actif, detail=detail,
                projets_non_mappes=projets_non_mappes)


def cout_eligible_par_personne(salaries: pd.DataFrame,
                               qualification: pd.DataFrame, cle) -> pd.Series:
    """Coût chargé par personne R&D éligible, RELU du substrat partagé — MÊME
    base que le numérateur firm-level (`nexus.depenses_rd_personnel_eligibles`)
    mais gardée par personne pour la répartition par actif.

    salaries      : substrat people (nom, cout_employeur)
    qualification : sortie moteur CIR (nom, statut)
    cle           : fonction nom -> person_key (identity.cle_personne partielle),
                    pour aligner la clé sur le substrat temps
    """
    s = salaries[["nom", "cout_employeur"]].copy()
    s["person_key"] = s.nom.map(cle)
    q = qualification[["nom", "statut"]].copy()
    q["person_key"] = q.nom.map(cle)
    elig = set(q.loc[q.statut.isin(nexus.STATUTS_RD_ELIGIBLE), "person_key"])
    s = s[s.person_key.isin(elig)].copy()
    s["cout_employeur"] = pd.to_numeric(s.cout_employeur, errors="coerce").fillna(0.0)
    return s.groupby("person_key").cout_employeur.sum()


# --------------------------------------------------- recettes par actif

def recettes_par_actif(revenues: pd.DataFrame, *,
                       explicites: dict | None = None,
                       map_lignes: dict | None = None) -> pd.DataFrame:
    """Recettes IP par actif. Deux voies d'arbitrage :
      - explicites : {actif_id: montant} fourni par le conseil ;
      - map_lignes : {ligne: actif_id} appliqué au substrat revenues (traçable
        à la ligne comptable).
    Sans l'un ni l'autre : DataFrame vide (rien n'est présumé)."""
    if explicites:
        return pd.DataFrame(
            [{"actif_id": a, "recettes": round(float(m), 2)}
             for a, m in explicites.items()])
    if map_lignes and revenues is not None and len(revenues):
        r = revenues.copy()
        r["actif_id"] = r.ligne.map(map_lignes)
        r = r[r.actif_id.notna()]
        g = r.groupby("actif_id").montant.sum().round(2).rename("recettes")
        return g.reset_index()
    return pd.DataFrame(columns=["actif_id", "recettes"])


# ---------------------------------------------------- synthèse par actif

def synthese_par_actif(actifs: pd.DataFrame, rd_par_actif: pd.DataFrame,
                       rec_par_actif: pd.DataFrame, *,
                       depenses_totales: dict | None = None,
                       resultat_net: dict | None = None,
                       taux_normal: float = nexus.TAUX_IS_NORMAL) -> pd.DataFrame:
    """Une ligne par actif + une ligne TOTAL. Ratio Nexus, base 10 % et
    économie calculés par actif quand les arbitrages (dénominateur, résultat
    net) sont fournis ; TO_REVIEW sinon. Le total n'agrège que les actifs
    calculés (OK) — il ne présume rien pour les actifs en attente."""
    depenses_totales = depenses_totales or {}
    resultat_net = resultat_net or {}

    ref = actifs[["actif_id", "libelle"]].copy() if "libelle" in actifs \
        else actifs[["actif_id"]].assign(libelle=actifs["actif_id"])
    ref = ref.merge(rd_par_actif, on="actif_id", how="left") \
             .merge(rec_par_actif, on="actif_id", how="left")
    ref["cout_rd_eligible"] = ref.cout_rd_eligible.fillna(0.0)
    ref["recettes"] = ref.recettes.fillna(0.0)

    lignes = []
    tot_base = tot_eco = 0.0
    n_ok = 0
    for r in ref.itertuples():
        den = depenses_totales.get(r.actif_id)
        net = resultat_net.get(r.actif_id)
        ratio = nexus.ratio_nexus(r.cout_rd_eligible, den)
        base = nexus.base_ip_box(net, ratio)
        eco = nexus.economie_impot(base, taux_normal)
        calcule = base is not None
        if calcule:
            tot_base += base
            tot_eco += eco
            n_ok += 1
        manque = []
        if net is None:
            manque.append("résultat net")
        if den is None:
            manque.append("dépenses totales")
        lignes.append(dict(
            actif=r.libelle,
            cout_rd_eligible=round(r.cout_rd_eligible, 2),
            recettes=round(r.recettes, 2),
            resultat_net=net,
            depenses_totales=den,
            ratio_nexus=round(ratio, 4) if ratio is not None else None,
            base_10=round(base, 2) if base is not None else None,
            economie=round(eco, 2) if eco is not None else None,
            statut="OK" if calcule else "TO_REVIEW",
            arbitrage_manquant="; ".join(manque)))
    lignes.append(dict(
        actif=f"TOTAL ({n_ok} actif(s) calculé(s))",
        cout_rd_eligible=round(float(ref.cout_rd_eligible.sum()), 2),
        recettes=round(float(ref.recettes.sum()), 2),
        resultat_net=None, depenses_totales=None, ratio_nexus=None,
        base_10=round(tot_base, 2), economie=round(tot_eco, 2),
        statut="OK" if n_ok else "TO_REVIEW", arbitrage_manquant=""))
    return pd.DataFrame(lignes)
