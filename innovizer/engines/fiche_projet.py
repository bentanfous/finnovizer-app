"""
Innovizer — FICHE PROJET
Contrat d'interface entre la Brique 03 (Eva, audit technique) et la Brique 04
(Project Mapper, regroupement thématique).

    BRIQUE 01 ──contexte──▶ EVA ──fiche──▶ MAPPER ──opérations──▶ ASSIETTE

Trois blocs, trois natures différentes :

  CONTEXTE     rempli par la Brique 01 AVANT l'entretien. Chiffré, factuel,
               jamais modifié par Eva. C'est ce qui lui permet d'arriver en
               sachant, et de confronter.

  INVESTIGATION rempli par Eva PENDANT l'entretien. Neuf axes. Chaque axe a un
               état (VIDE / PARTIEL / COMPLET), un contenu et les preuves
               demandées. Eva ne qualifie pas : elle collecte et challenge.

  SYNTHESE     produit APRÈS l'entretien. Matrice de couverture, score de
               défendabilité, questions ouvertes, arêtes de regroupement.

CE QUI N'EST PAS DANS LA FICHE
    Aucun « signal CIR » ni « score d'éligibilité ». L'éligibilité est une
    qualification juridique sur la nature des travaux ; elle est décidée par
    le conseil, après audit, et saisie dans le screening (colonne
    `eligibilite`). La fiche mesure deux choses seulement : la complétude de
    l'entretien et la présence de matière défendable.
"""

from dataclasses import dataclass, field, asdict
import json
import pandas as pd

# ------------------------------------------------------------------ axes

AXES = {
    "probleme":    "Problème technique à résoudre",
    "etat_art":    "État de l'art et limites des solutions existantes",
    "verrou":      "Verrou scientifique ou technique / incertitude",
    "hypotheses":  "Hypothèses et approches envisagées",
    "essais":      "Démarche expérimentale, essais réalisés",
    "echecs":      "Échecs, itérations, abandons",
    "resultats":   "Résultats obtenus et acquis de connaissance",
    "moyens":      "Moyens : personnel, sous-traitance, matériel",
    "preuves":     "Éléments de preuve datés et localisés",
}

#: axes CII, activés quand le régime pressenti est l'innovation
AXES_CII = {
    "produit":     "Produit ou prototype et son périmètre",
    "marche":      "État du marché et offres comparables",
    "nouveaute":   "Nouveauté et performances supérieures",
    "iterations":  "Itérations de conception et prototypes",
}

ETATS = ["VIDE", "PARTIEL", "COMPLET"]

#: poids des axes dans la défendabilité. Le verrou et les preuves pèsent
#: le plus : sans verrou, pas de R&D ; sans preuve, pas de défense.
POIDS_DEFENDABILITE = {
    "probleme": 1, "etat_art": 2, "verrou": 3, "hypotheses": 1,
    "essais": 2, "echecs": 2, "resultats": 1, "moyens": 1, "preuves": 3,
}

#: signaux qui, s'ils apparaissent, font baisser la défendabilité
RED_FLAGS = {
    "performance_seule": "l'objectif se résume à une amélioration de performance "
                         "sans incertitude identifiée",
    "etat_art_absent": "aucune solution existante n'a été examinée",
    "aucun_echec": "aucun essai infructueux — démarche linéaire, pas expérimentale",
    "preuve_orale": "les preuves sont uniquement déclaratives",
    "temps_non_valide": "les feuilles de temps du responsable ne sont pas validées",
    "prestataire_non_agree": "sous-traitance déclarée auprès d'un prestataire non agréé",
    "regime_incoherent": "régime pressenti ≠ régime de la sous-traitance ou du temps",
}


@dataclass
class Contexte:
    """Rempli par la Brique 01. Lecture seule pour Eva."""
    code_projet: str
    projet_dossier: str = ""
    thematique_amorce: str = ""
    heures: float = 0.0
    collaborateurs: list = field(default_factory=list)   # [{nom, emploi, statut_qualif, heures}]
    periode: str = ""
    sous_traitants: list = field(default_factory=list)   # [{nom, siren, statut_cir, statut_cii, montant}]
    immobilisations: list = field(default_factory=list)  # [{designation, dotation, taux}]
    aides: list = field(default_factory=list)            # [{organisme, montant, nature}]
    pieces: list = field(default_factory=list)           # [{document_id, type, valeur_probante}]
    alertes: list = field(default_factory=list)          # contrôles B01 touchant ce projet


@dataclass
class Axe:
    etat: str = "VIDE"
    contenu: str = ""
    preuves_demandees: list = field(default_factory=list)
    citations: list = field(default_factory=list)   # extraits du transcript
    challenge: str = ""                             # relance faite par Eva


@dataclass
class Investigation:
    regime_pressenti: str = "A_DETERMINER"          # CIR / CII / MIXTE / HORS
    axes: dict = field(default_factory=lambda: {k: Axe() for k in AXES})
    axes_cii: dict = field(default_factory=dict)
    interlocuteur: str = ""
    date_entretien: str = ""
    duree_min: int = 0
    transcript_id: str = ""


@dataclass
class Synthese:
    couverture_pct: float = 0.0
    defendabilite: str = "A_EVALUER"                # FORTE / MOYENNE / FAIBLE
    score_defendabilite: float = 0.0
    red_flags: list = field(default_factory=list)
    questions_ouvertes: list = field(default_factory=list)
    pieces_a_reclamer: list = field(default_factory=list)
    liens_verrou: list = field(default_factory=list)   # [{code_projet, nature_du_lien, source}]
    revue_experte_requise: bool = True


@dataclass
class FicheProjet:
    contexte: Contexte
    investigation: Investigation = field(default_factory=Investigation)
    synthese: Synthese = field(default_factory=Synthese)
    version: str = "1.0"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


# --------------------------------------------------------------- moteur

def contexte_depuis_brique01(code_projet, data: dict, alias: dict | None = None) -> Contexte:
    """Assemble le contexte d'un projet depuis les sorties de la Brique 01."""
    from ..identity import cle_personne
    tt = data["temps"]
    t = tt[tt.code_projet == code_projet]
    scr = data["screening_projets"]
    s = scr[scr.code_projet == code_projet].iloc[0] if (scr.code_projet == code_projet).any() else None
    qual = data.get("qualification")
    qmap = {}
    if qual is not None:
        for r in qual.itertuples():
            qmap[cle_personne(r.nom, alias)] = (r.fonction, r.statut)

    collab = (t.groupby("person_key").heures.sum().sort_values(ascending=False))
    collaborateurs = [dict(nom=k, emploi=qmap.get(k, ("", ""))[0],
                           statut_qualif=qmap.get(k, ("", "PIECE_MANQUANTE"))[1],
                           heures=round(float(h), 1)) for k, h in collab.items()]

    alertes = []
    STATUTS_OK = ("ELIGIBLE_CONFIRMED", "ELIGIBLE_TECHNICIAN")
    if any(c["statut_qualif"] not in STATUTS_OK for c in collaborateurs):
        alertes.append("au moins un collaborateur sans qualification établie")
    ctrl = data.get("_controles")
    return Contexte(
        code_projet=code_projet,
        projet_dossier=str(s.projet_dossier) if s is not None and "projet_dossier" in s else "",
        thematique_amorce=str(s.thematique_chapeau) if s is not None else "",
        heures=round(float(t.heures.sum()), 1),
        collaborateurs=collaborateurs,
        periode=f"{int(t.mois.min()):02d}/2025 → {int(t.mois.max()):02d}/2025" if len(t) else "",
        alertes=alertes,
    )


def questions_manquantes(inv: Investigation) -> list:
    """Grille d'entretien : ce qu'Eva doit encore obtenir."""
    q = []
    for k, ax in inv.axes.items():
        if ax.etat != "COMPLET":
            q.append(dict(axe=k, libelle=AXES[k], etat=ax.etat))
    if inv.regime_pressenti in ("CII", "MIXTE"):
        for k, lib in AXES_CII.items():
            ax = inv.axes_cii.get(k, Axe())
            if ax.etat != "COMPLET":
                q.append(dict(axe=k, libelle=lib, etat=ax.etat))
    return q


def detecter_red_flags(fiche: FicheProjet) -> list:
    inv, ctx = fiche.investigation, fiche.contexte
    flags = []
    v = inv.axes["verrou"]
    if v.etat != "VIDE" and any(m in v.contenu.lower() for m in
                                ("améliorer les performances", "plus rapide", "optimiser")) \
            and "incertitude" not in v.contenu.lower():
        flags.append("performance_seule")
    if inv.axes["etat_art"].etat == "VIDE":
        flags.append("etat_art_absent")
    if inv.axes["echecs"].etat == "VIDE" and inv.axes["essais"].etat == "COMPLET":
        flags.append("aucun_echec")
    if inv.axes["preuves"].etat != "VIDE" and not ctx.pieces \
            and not inv.axes["preuves"].preuves_demandees:
        flags.append("preuve_orale")
    if any("non validé" in a or "Brouillon" in a for a in ctx.alertes):
        flags.append("temps_non_valide")
    if any(st.get("statut_cir") not in ("APPROVED",) and st.get("statut_cii") not in ("APPROVED",)
           for st in ctx.sous_traitants):
        flags.append("prestataire_non_agree")
    return flags


def synthetiser(fiche: FicheProjet) -> Synthese:
    inv = fiche.investigation
    axes = inv.axes
    n = len(AXES)
    complet = sum(1 for a in axes.values() if a.etat == "COMPLET")
    partiel = sum(1 for a in axes.values() if a.etat == "PARTIEL")
    couverture = round((complet + 0.5 * partiel) / n * 100, 1)

    total_poids = sum(POIDS_DEFENDABILITE.values())
    acquis = sum(POIDS_DEFENDABILITE[k] * (1 if a.etat == "COMPLET" else 0.5 if a.etat == "PARTIEL" else 0)
                 for k, a in axes.items())
    flags = detecter_red_flags(fiche)
    score = round(acquis / total_poids * 100 - 10 * len(flags), 1)
    score = max(0.0, min(100.0, score))

    # le verrou et les preuves sont bloquants : sans eux, jamais FORTE
    bloquant = axes["verrou"].etat != "COMPLET" or axes["preuves"].etat == "VIDE"
    if bloquant or score < 40:
        niveau = "FAIBLE"
    elif score < 70:
        niveau = "MOYENNE"
    else:
        niveau = "FORTE"

    pieces = sorted({p for a in axes.values() for p in a.preuves_demandees})
    return Synthese(
        couverture_pct=couverture,
        defendabilite=niveau,
        score_defendabilite=score,
        red_flags=[dict(code=f, libelle=RED_FLAGS[f]) for f in flags],
        questions_ouvertes=questions_manquantes(inv),
        pieces_a_reclamer=pieces,
        liens_verrou=fiche.synthese.liens_verrou,
        revue_experte_requise=True,
    )


def table_fiches(fiches: list) -> pd.DataFrame:
    """Vue tabulaire pour le mapper et le classeur."""
    rows = []
    for f in fiches:
        s, c, i = f.synthese, f.contexte, f.investigation
        rows.append(dict(
            code_projet=c.code_projet, thematique_amorce=c.thematique_amorce,
            heures=c.heures, nb_collaborateurs=len(c.collaborateurs),
            regime_pressenti=i.regime_pressenti,
            couverture_pct=s.couverture_pct,
            defendabilite=s.defendabilite, score=s.score_defendabilite,
            nb_red_flags=len(s.red_flags),
            verrou=i.axes["verrou"].contenu[:120],
            liens=", ".join(l["code_projet"] for l in s.liens_verrou),
            questions_ouvertes=len(s.questions_ouvertes),
            revue_experte=s.revue_experte_requise,
        ))
    return pd.DataFrame(rows).sort_values(["defendabilite", "heures"], ascending=[True, False])
