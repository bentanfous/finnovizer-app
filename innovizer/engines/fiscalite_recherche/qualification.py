"""
Innovizer — Brique 01 / sous-module QUALIFICATION DU PERSONNEL

Deux filtres successifs, dans cet ordre :
  1. FONCTION  — l'intitulé de poste exclut d'emblée les profils non techniques
                 (commerce, RH, finance, logistique, communication, direction générale).
  2. DIPLÔME   — pour les fonctions techniques, le niveau et le domaine du diplôme
                 décident : technicien BAC+2 technique minimum, ingénieur/master.

Règles retenues sur ce dossier :
  - stagiaires et alternants sur poste TECHNIQUE : éligibles
  - alternants sur poste non technique (RH, finance, commerce, qualité) : exclus
  - un diplôme BAC+5 non technique (école de commerce, droit/gestion) sur un poste
    non technique : exclu

Aucune décision n'est prise sans pièce : un profil dont le diplôme n'a pas été
collecté reste PIECE_MANQUANTE et sort de l'assiette tant qu'il n'est pas documenté.

Valeur probante : le diplôme ou le titre prime. Un CV est un élément d'information,
pas une pièce justificative opposable ; il est accepté à titre provisoire et signalé.
"""

import re
import pandas as pd

# --------------------------------------------------------------- filtre fonction

FONCTIONS_EXCLUES = [
    r"COMMERCIAL", r"COMMERCE", r"MARKETING", r"COMMUNICATION", r"RESSOURCES HUMAINES",
    r"\bRH\b", r"FINANCE", r"FINANCI", r"ADMINISTRATIF", r"ADMINISTRATION",
    r"COMPTAB", r"LOGISTIQUE", r"SUPPLY CHAIN", r"QUALIT",
    r"PR[EÉ]SIDENT", r"CONTR[OÔ]LE DE GESTION",
]

FONCTIONS_TECHNIQUES = [
    r"ING[EÉ]NIEUR", r"TECHNICIEN", r"D[EÉ]VELOPPEUR", r"CHEF DE PROJET",
    r"DIRECTEUR TECHNIQUE", r"P[OÔ]LE T[EÉ]L[EÉ]MATIQUE",
    r"ADMINISTRATEUR SYST",
]


def filtre_fonction(emploi: str) -> str:
    """NON_TECHNIQUE / TECHNIQUE / A_QUALIFIER"""
    e = str(emploi).upper()
    for pat in FONCTIONS_EXCLUES:
        if re.search(pat, e):
            # un intitulé mixte (ex. « ingénieur commercial ») reste exclu
            return "NON_TECHNIQUE"
    for pat in FONCTIONS_TECHNIQUES:
        if re.search(pat, e):
            return "TECHNIQUE"
    return "A_QUALIFIER"


# --------------------------------------------------------------- dossier diplômes
# Renseigné à partir des pièces reçues. 'piece' = nature du justificatif détenu.

DIPLOMES = {
    "CORENTIN AUSSET": dict(
        diplome="Programme Grande École MBS (BAC+5, grade Master)", annee=2024,
        domaine="management", niveau=5, piece="attestation de réussite"),
    "THIBAULT DELATTRE": dict(
        diplome="Diplôme d'ingénieur ISEN — JUNIA", annee=2023,
        domaine="électronique / numérique", niveau=5, piece="attestation de diplôme"),
    "BASTIEN JAFFRE": dict(
        diplome="Maîtrise Droit-Économie-Gestion, mention GRH (Toulouse 1)", annee=2022,
        domaine="gestion / RH", niveau=4, piece="diplôme"),
    "ARTHUR KRAMM": dict(
        diplome="Diplôme d'ingénieur ENSICAEN, génie physique et systèmes embarqués",
        annee=2024, domaine="systèmes embarqués", niveau=5, piece="diplôme"),
    "VADYM LOIK": dict(
        diplome="Diplôme de spécialiste, Université nationale d'aviation (Ukraine) — "
                "ingénieur en énergie", annee=2014,
        domaine="électrotechnique", niveau=5, piece="diplôme + traduction assermentée"),
    "ANTHONY MATHIEU": dict(
        diplome="Expert en Systèmes d'information — RNCP niveau 7 (Sup de Vinci)",
        annee=2025, domaine="systèmes d'information", niveau=5,
        piece="attestation de prérequis"),
    "JEROME MERCIER": dict(
        diplome="BTS Maintenance et Après-Vente Automobile", annee=1998,
        domaine="maintenance automobile", niveau=2, piece="diplôme + relevé de notes"),
    "ALEXIS RAULT": dict(
        diplome="Master Génie industriel, parcours Électronique embarquée et systèmes "
                "de communication (Paris Ouest Nanterre)", annee=2015,
        domaine="électronique embarquée", niveau=5, piece="diplôme"),
    "JULIEN AYIVI": dict(
        diplome="Licence pro systèmes embarqués (Sorbonne Paris Nord) ; "
                "Licence génie industriel (Gustave Eiffel)", annee=2023,
        domaine="électronique / systèmes embarqués", niveau=3, piece="CV uniquement"),
    "SERVAN DELAHAIES": dict(
        diplome="Diplôme d'ingénieur Polytech Lille, systèmes embarqués", annee=2024,
        domaine="systèmes embarqués", niveau=5, piece="CV uniquement"),
    "OUSSAMA AKENNAF": dict(
        diplome="Master 2 EEEA — Électronique et Systèmes Embarqués (Lyon 1)",
        annee=2023, domaine="électronique embarquée", niveau=5, piece="CV uniquement"),
    "ADEOLA AKINBIYI": dict(
        diplome="MSc Agricultural & Food Data Management (UniLaSalle Rouen)",
        annee=2023, domaine="data management (agroalimentaire)", niveau=5,
        piece="diplôme + attestation"),
    "MARWEN AOUINI": dict(
        diplome="Doctorat Automatique, traitement du signal, génie informatique "
                "(Université de Lorraine)", annee=2022,
        domaine="automatique / IA", niveau=8,
        piece="diplôme + CV + contrat de travail"),
    # --- lot 2 ---
    "IVAN BAKLAN": dict(
        diplome="Bachelor en chorégraphie, Université de la culture de Kyiv "
                "(ENIC-NARIC : niveau 6, 240 ECTS)", annee=2021,
        domaine="culture et arts / chorégraphie", niveau=3,
        piece="diplôme + attestation de comparabilité ENIC-NARIC"),
    "RAMLA BEN ABDELKADER": dict(
        diplome="Master 2 Signaux et télécommunications (Université de Brest)",
        annee=2021, domaine="signal / télécommunications", niveau=5,
        piece="attestation de réussite + relevé de notes + CV"),
    "FATMA BEN AMOR": dict(
        diplome="Master de recherche Sciences & Technologie, spécialité "
                "micro-nanoélectronique (Université de Monastir)", annee=2021,
        domaine="micro-nanoélectronique", niveau=5,
        piece="diplôme (traduction certifiée)"),
    "SEIF-EDDINE BEN BOUSSAHA": dict(
        diplome="Diplôme d'ingénieur en informatique industrielle et automatique "
                "(INSAT Tunis)", annee=2018,
        domaine="informatique industrielle / automatique", niveau=5,
        piece="CV uniquement"),
    "OUMAYMA BENJEDDI": dict(
        diplome="Diplôme d'ingénieur ENSISA, spécialité automatique et systèmes "
                "embarqués", annee=2019, domaine="automatique / systèmes embarqués",
        niveau=5, piece="attestation d'obtention de diplôme + CV"),
    "VINCIANE BRONNER": dict(
        diplome="Diplôme d'ingénieur ENSSAT Lannion, électronique et informatique "
                "industrielle (grade de master)", annee=2005,
        domaine="électronique / informatique industrielle", niveau=5,
        piece="diplôme + CV"),
    "ROBIN COSTE": dict(
        diplome="Ingénieur CESI, spécialité systèmes électroniques et électriques "
                "embarqués", annee=2024, domaine="systèmes embarqués", niveau=5,
        piece="attestation de réussite + décision du jury national"),
    "JONATHAN COURTOUX": dict(
        diplome="Master STIC, spécialité génie électrique et informatique "
                "industrielle (Université Bretagne-Sud)", annee=2014,
        domaine="génie électrique / informatique industrielle", niveau=5,
        piece="diplôme"),
}

DOMAINES_NON_TECHNIQUES = r"management|gestion|\bRH\b|commerce|droit|culture|arts|chor[ée]graphie"


# Vocabulaire de qualification (doctrine CIR : le diplôme n'est pas le seul
# critère ; l'assimilation par l'expérience et, pour les techniciens, les
# travaux réellement réalisés comptent aussi).
#
#   ELIGIBLE_CONFIRMED    diplôme technique aligné, pièce opposable
#   ELIGIBLE_TECHNICIAN   BAC+2 technique — technicien de recherche, à confirmer
#                         par les travaux réalisés
#   TO_REVIEW             fonction technique mais diplôme non aligné, ou pièce
#                         seulement informative : à instruire à l'audit
#                         (assimilation par expérience possible mais NON acquise)
#   INSUFFICIENT_EVIDENCE diplôme non collecté
#   NON_RD_FUNCTION       fonction support, hors périmètre
#
# Règle cardinale : un diplôme non aligné fait passer en TO_REVIEW, JAMAIS
# directement en éligible. Le silence — ici, l'absence de diplôme parfaitement
# aligné — n'ouvre pas droit ; il ouvre une question.

def qualifier(nom: str, emploi: str) -> dict:
    f = filtre_fonction(emploi)
    d = DIPLOMES.get(str(nom).upper())

    if f == "NON_TECHNIQUE":
        return dict(filtre_fonction=f, statut="NON_RD_FUNCTION",
                    motif="fonction non technique — hors périmètre R&D",
                    **{k: (d or {}).get(k) for k in
                       ("diplome", "annee", "domaine", "niveau", "piece")})

    if d is None:
        return dict(filtre_fonction=f, statut="INSUFFICIENT_EVIDENCE",
                    motif="diplôme non collecté — à réclamer", diplome=None,
                    annee=None, domaine=None, niveau=None, piece=None)

    base = dict(filtre_fonction=f, **{k: d[k] for k in
                ("diplome", "annee", "domaine", "niveau", "piece")})

    # diplôme hors domaine technique : NE PAS exclure, instruire.
    if re.search(DOMAINES_NON_TECHNIQUES, d["domaine"], re.I):
        return dict(base, statut="TO_REVIEW",
                    motif="diplôme hors domaine technique — assimilation par "
                          "l'expérience à instruire à l'audit (travaux réalisés, "
                          "technicité), non acquise")
    if d["niveau"] < 2:
        return dict(base, statut="TO_REVIEW",
                    motif="niveau < BAC+2 — qualification technicien à établir "
                          "par les travaux et l'expérience")
    if d["niveau"] == 2:
        return dict(base, statut="ELIGIBLE_TECHNICIAN",
                    motif="BAC+2 technique — technicien de recherche, à confirmer "
                          "par les travaux réalisés")
    if d["piece"] == "CV uniquement":
        return dict(base, statut="TO_REVIEW",
                    motif="diplôme non collecté — CV sans valeur probante, "
                          "pièce opposable à réclamer")
    return dict(base, statut="ELIGIBLE_CONFIRMED", motif="")


def construire(ref: pd.DataFrame) -> pd.DataFrame:
    lignes = []
    for r in ref.itertuples():
        q = qualifier(r.nom, r.emploi)
        lignes.append(dict(nom=r.nom, fonction=r.emploi,
                           classification=r.classification,
                           debut_contrat=r.debut_contrat,
                           mois_presence=r.mois_presence, **q))
    return pd.DataFrame(lignes).sort_values(["statut", "nom"])
