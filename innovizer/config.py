"""
Innovizer — configuration par dossier.

RÈGLE : rien de ce qui varie d'un client à l'autre ou d'une année à l'autre ne
doit être écrit en dur dans un moteur. Tout est ici, versionné avec le dossier,
pour qu'un exercice puisse être recalculé plus tard avec les paramètres qui
étaient les siens. C'est ce qui permet de répondre à un contrôle trois ans après.
"""

from dataclasses import dataclass, field


@dataclass
class ReglesCotisations:
    """Périmètre des cotisations patronales retenues dans l'assiette.

    Ce découpage est une POSITION DE CONSEIL, arbitrée dossier par dossier et
    à documenter dans le rapport. Il n'est pas une donnée technique.
    """
    eligibles: list = field(default_factory=lambda: [
        r"Assurance maladie", r"Compl[ée]ment d'assurance maladie",
        r"Assurance vieillesse", r"Allocations familiales",
        r"Compl[ée]ment d'allocations familiales", r"Accidents du travail",
        r"Assurance ch[oô]mage", r"Fonds national de garantie des salaires",
        r"Retraite compl[ée]mentaire unifi[ée]e AGIRC-ARRCO", r"CEG sur tranche",
        r"Contribution d'Equilibre Technique", r"APEC",
        r"Pr[ée]voyance - Tranche", r"Mutuelle",
        r"R[ée]duction Fillon", r"R[ée]duction des cotisations patronales",
    ])
    non_eligibles: list = field(default_factory=lambda: [
        r"Taxe d'apprentissage", r"formation professionnelle continue",
        r"CPF-CDD", r"Fonds pour le paritarisme", r"Organisations syndicales",
        r"Forfait social", r"Contribution patronale Rupture Conventionnelle",
        r"FNAL", r"Contribution Solidarit[ée] Autonomie",
    ])
    #: rubriques dont le classement a été arbitré explicitement — à tracer
    arbitrages: dict = field(default_factory=lambda: {
        "Titres-restaurant": "ELIGIBLE — position du conseil, à documenter",
        "FNAL": "NON_ELIGIBLE — arbitré",
        "Contribution Solidarité Autonomie": "NON_ELIGIBLE — arbitré",
    })


@dataclass
class Dossier:
    client: str
    exercice: int
    siret: str = ""

    #: durée journalière contractuelle, pour convertir les jours en heures.
    #: Découle du contrat de travail (39 h/semaine sur 5 j => 7,8). JAMAIS une
    #: constante : à redéfinir pour chaque client.
    heures_par_jour: float = 7.8

    #: base retenue pour le taux horaire : "travaillees" ou "payees".
    #: Les deux conventions existent et ne donnent pas le même résultat.
    base_taux_horaire: str = "travaillees"

    #: seuil d'alerte sur la quotité R&D d'un salarié. Au-delà, le temps non
    #: productif devient invraisemblable et doit être justifié.
    seuil_quotite_alerte: float = 0.90

    #: bornes de plausibilité du taux de charges patronales
    taux_charges_min: float = 0.20
    taux_charges_max: float = 0.60

    cotisations: ReglesCotisations = field(default_factory=ReglesCotisations)

    #: alias d'identité constatés entre systèmes (SIRH, paie, suivi des temps)
    alias_personnes: dict = field(default_factory=dict)

    #: activités support écartées d'office du screening projets
    activites_support: list = field(default_factory=lambda: [
        r"^INT_Commerce$", r"^INT_RH$", r"^INT_ADMIN_FI$", r"^INT_Logistique$",
        r"^INT_Supply Chain$", r"^INT_Support informatique$",
        r"^INT_D[ée]placement$", r"^INT_SALONS", r"^INT_CSE$",
    ])


DUNASYS_2025 = Dossier(
    client="DUNASYS INGENIERIE",
    exercice=2025,
    siret="80075483000035",
    heures_par_jour=7.8,
    alias_personnes={
        "RAMLA ABDELKADER": "RAMLA BEN ABDELKADER",
        "THIBAUT DELATTRE": "THIBAULT DELATTRE",
        "MARGUERITE-MARIE PASQUERON DE": "MARGUERITE-MARIE PASQUERON DE FOMMERVAULT",
    },
)
