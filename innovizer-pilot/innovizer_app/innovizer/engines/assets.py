"""
Innovizer — moteur IMMOBILISATIONS.

Deux périmètres à ne jamais confondre.

  COMPTE 203 — FRAIS DE R&D IMMOBILISÉS
      Enjeu principal en montant. Point de contrôle obligatoire : si les
      dépenses sous-jacentes (personnel, sous-traitance) ont déjà été
      déclarées au CIR de l'exercice où elles ont été engagées, reprendre
      leur amortissement revient à les compter deux fois. Le module signale
      ces lignes et refuse de les valoriser automatiquement.

  MATÉRIELS ET LOGICIELS
      Enjeu faible en montant, enjeu fort en crédibilité. Un téléphone, une
      imprimante ou un vidéoprojecteur valorisés en R&D décrédibilisent le
      reste du dossier pour quelques dizaines d'euros.

TAUX D'USAGE R&D
    Un taux moyen unique appliqué à tous les actifs n'est pas défendable quand
    les quotités individuelles vont de 0 à 97 %. Le module privilégie le
    rattachement actif → utilisateur → quotité réelle du salarié, et ne
    retombe sur un taux forfaitaire que si l'affectation est inconnue — en le
    signalant comme tel.
"""

import re
import pandas as pd

COMPTE_FRAIS_RD = "203"

CATEGORIES_EXCLUES = {
    "TELEPHONIE": r"IPHONE|SMARTPHONE|SAMSUNG GALAXY|MOBILE",
    "BUREAUTIQUE": r"IMPRIMANTE|SCANNER|MULTIFONCTION|BUSITEL",
    "PRESENTATION": r"OPTOMA|VIDEOPROJECTEUR|PROJECTEUR|ECRAN GEANT",
    "MOBILIER": r"BUREAU VALLEE|IKEA|CONFORAMA|MOBILIER|CHAISE|ARMOIRE",
}

CATEGORIES_TECHNIQUES = {
    "POSTE_DEV": r"DELL|LENOVO|ASUS|ACER|MATERIELNET|LDLC|THINKPAD|NITRO",
    "SERVEUR": r"SERVEUR|SERVER|1U-|RACK|GPU|NVIDIA",
    "LOGICIEL_TECHNIQUE": r"INTREPID|ALTIUM|VECTOR|CANOE|MATLAB|LABVIEW|"
                          r"KVASER|CONTROL SYSTEMS",
    "INSTRUMENT": r"OSCILLO|ANALYSEUR|BANC|SONDE|ALIMENTATION LABO",
}

#: pays hors EEE rencontrés dans les libellés fournisseurs
INDICES_HORS_EEE = r"\bINR\b|CROMA|SHENZHEN|AOTAI|MAROC|ALIBABA"


def classer_actif(designation: str) -> tuple:
    """(categorie, statut) — statut ∈ RETENU / ECARTE / A_ARBITRER"""
    d = str(designation).upper()
    for cat, pat in CATEGORIES_EXCLUES.items():
        if re.search(pat, d):
            return cat, "ECARTE"
    if re.search(INDICES_HORS_EEE, d):
        return "HORS_EEE", "A_ARBITRER"
    for cat, pat in CATEGORIES_TECHNIQUES.items():
        if re.search(pat, d):
            return cat, "RETENU"
    return "NON_CLASSE", "A_ARBITRER"


MOTIFS = {
    "TELEPHONIE": "téléphone — pas un équipement de recherche",
    "BUREAUTIQUE": "matériel bureautique",
    "PRESENTATION": "matériel de présentation",
    "MOBILIER": "mobilier ou fourniture de bureau",
    "HORS_EEE": "actif possiblement localisé hors EEE — territorialité à vérifier",
    "NON_CLASSE": "nature à qualifier",
}


def traiter_frais_rd(etat: pd.DataFrame) -> pd.DataFrame:
    """Lignes du compte 203 avec dotation sur l'exercice.

    etat : colonnes num, designation, date_acquisition, duree_mois,
           valeur_brute, amort_cumules, dotation_periode, vnc
    """
    d = etat.copy()
    d["duree_annees"] = pd.to_numeric(d.duree_mois, errors="coerce") / 12
    d["dotation_theorique"] = (pd.to_numeric(d.valeur_brute, errors="coerce")
                               / d.duree_annees).round(2)
    d["ecart_dotation"] = (pd.to_numeric(d.dotation_periode, errors="coerce")
                           - d.dotation_theorique).round(2)
    d["coherence_vnc"] = (pd.to_numeric(d.valeur_brute, errors="coerce")
                          - pd.to_numeric(d.amort_cumules, errors="coerce")
                          - pd.to_numeric(d.vnc, errors="coerce")).round(2)
    d["statut"] = "CONTROLE_DOUBLE_COMPTAGE_REQUIS"
    d["motif"] = ("dotation de frais de R&D immobilisés — vérifier que les "
                  "dépenses sous-jacentes n'ont pas déjà été déclarées au CIR "
                  "de leur exercice d'engagement")
    return d[pd.to_numeric(d.dotation_periode, errors="coerce").fillna(0) != 0]


def traiter_materiels(registre: pd.DataFrame, quotites: pd.DataFrame | None = None,
                      taux_defaut: float | None = None) -> pd.DataFrame:
    """registre : num, designation, date_acquisition, valeur_acquisition,
                  dotation_annuelle, [utilisateur]
    quotites  : person_key, quotite_rd
    """
    d = registre.copy()
    d[["categorie", "statut"]] = d.designation.apply(
        lambda x: pd.Series(classer_actif(x)))
    d["motif"] = d.categorie.map(lambda c: MOTIFS.get(c, ""))

    d["taux_rd"] = pd.NA
    d["origine_taux"] = ""
    if quotites is not None and "utilisateur" in d:
        q = dict(zip(quotites.person_key, quotites.quotite_rd))
        d["taux_rd"] = d.utilisateur.map(lambda u: q.get(u))
        d.loc[d.taux_rd.notna(), "origine_taux"] = "quotité réelle du salarié"
    if taux_defaut is not None:
        manque = d.taux_rd.isna()
        d.loc[manque, "taux_rd"] = taux_defaut
        d.loc[manque, "origine_taux"] = (
            f"taux forfaitaire {taux_defaut:.0%} — affectation inconnue, à justifier")

    dot = pd.to_numeric(d.dotation_annuelle, errors="coerce")
    d["montant_candidat"] = (dot * pd.to_numeric(d.taux_rd, errors="coerce")).round(2)
    d.loc[d.statut == "ECARTE", "montant_candidat"] = 0.0
    return d
