"""
Innovizer — EVIDENCE HUB.

Registre des pièces justificatives, rattachées aux entités du modèle.
C'est la sortie qui fait la différence en contrôle : pour chaque euro déclaré,
on remonte au salarié, au projet, à la pièce.

VALEUR PROBANTE — hiérarchie explicite, portée par le registre lui-même :
    OPPOSABLE    diplôme, titre, décision d'agrément, contrat, facture,
                 bulletin de paie, attestation de réussite
    CORROBORANT  attestation de comparabilité ENIC-NARIC, traduction assermentée,
                 relevé de notes
    INFORMATIF   CV, profil en ligne, échange de mails
    INSUFFISANT  pièce partielle ou conditionnelle (« inscrit en 5e année »,
                 « a obtenu les prérequis permettant de valider »)

Une pièce INFORMATIVE ne fonde jamais une décision d'assiette. Le registre le
signale, il ne l'interdit pas : c'est au conseil de trancher et d'assumer.

MINIMISATION
    Les pièces sources contiennent des données personnelles inutiles au CIR
    (numéro de sécurité sociale, adresse, situation familiale, absences
    maladie). Le registre référence les pièces, il n'en recopie pas le contenu.
"""

import pandas as pd

VALEUR_PROBANTE = {
    "diplome": "OPPOSABLE",
    "titre_ingenieur": "OPPOSABLE",
    "attestation_reussite": "OPPOSABLE",
    "certificat_diplome": "OPPOSABLE",
    "decision_agrement": "OPPOSABLE",
    "contrat_travail": "OPPOSABLE",
    "fiche_de_poste": "OPPOSABLE",
    "bulletin_paie": "OPPOSABLE",
    "facture": "OPPOSABLE",
    "enic_naric": "CORROBORANT",
    "traduction_assermentee": "CORROBORANT",
    "releve_notes": "CORROBORANT",
    "cv": "INFORMATIF",
    "attestation_prerequis": "INSUFFISANT",
    "attestation_inscription": "INSUFFISANT",
}

ENTITES = ["personne", "projet", "fournisseur", "actif", "operation"]


def registre(pieces: list) -> pd.DataFrame:
    """pieces : liste de dicts
        {document_id, type, fichier, date, entite, cle_entite, note}
    """
    d = pd.DataFrame(pieces)
    if d.empty:
        return pd.DataFrame(columns=["document_id", "type", "valeur_probante",
                                     "fichier", "date", "entite", "cle_entite",
                                     "note"])
    d["valeur_probante"] = d.type.map(
        lambda t: VALEUR_PROBANTE.get(t, "A_QUALIFIER"))
    return d.sort_values(["entite", "cle_entite", "valeur_probante"])


def couverture(registre_df: pd.DataFrame, attendus: pd.DataFrame,
               entite: str, col_cle: str) -> pd.DataFrame:
    """Qui a une pièce opposable, qui n'en a pas."""
    r = registre_df[registre_df.entite == entite]
    opposables = set(r.loc[r.valeur_probante == "OPPOSABLE", "cle_entite"])
    toutes = set(r.cle_entite)
    out = attendus.copy()
    out["piece_opposable"] = out[col_cle].isin(opposables)
    out["piece_quelconque"] = out[col_cle].isin(toutes)
    out["statut_preuve"] = out.apply(
        lambda x: "COUVERT" if x.piece_opposable
        else "INSUFFISANT" if x.piece_quelconque else "MANQUANT", axis=1)
    return out


def piste_audit(person_key, assiette, quotites, registre_df) -> dict:
    """Chaîne complète pour un salarié : euro → salarié → temps → projet → preuve."""
    a = assiette[assiette.person_key == person_key]
    q = quotites[quotites.person_key == person_key]
    p = registre_df[(registre_df.entite == "personne")
                    & (registre_df.cle_entite == person_key)]
    return {
        "salarie": person_key,
        "cout_charge": float(a["Salaire Annuel Brut Chargé"].iloc[0]) if len(a) else None,
        "heures_travaillees": float(a["Nombre d'heures travaillées"].iloc[0]) if len(a) else None,
        "heures_rd": float(q.h_rd.iloc[0]) if len(q) else None,
        "quotite": float(q.quotite_rd.iloc[0]) if len(q) else None,
        "pieces": p[["type", "valeur_probante", "fichier"]].to_dict("records"),
    }
