"""Pipeline : le Data Hub se construit avec le livre de paie SEUL ou les
bulletins SEULS (pour l'instant), sans exiger l'autre source ni planter."""
import pandas as pd
from innovizer import config
from innovizer.pipeline import Brique01


def _b():
    return Brique01(config.Dossier(client="T", exercice=2025), cache_dir=None)


def _paie_lignes():
    base = dict(section="Cotisations", nom="A B", mois=1, annee="2025",
                base=0.0, matricule="1", montant_salarial=0.0, montant_total=0.0)
    return pd.DataFrame([
        {**base, "person_key": "A B", "rubrique": "URSSAF Maladie", "montant_patronal": 1000.0},
        {**base, "person_key": "A B", "rubrique": "APEC", "montant_patronal": 50.0},
    ])


def test_livre_de_paie_seul_classe_les_cotisations_sans_annexe():
    b = _b()
    b.data["paie_lignes"] = _paie_lignes()
    b.moteur_assiette()                       # ne doit PAS exiger salaries/bulletins
    assert "cotisations" in b.data
    assert "classement_cotisations" in b.data
    assert "annexe" not in b.data             # pas de bulletins -> pas d'annexe


def test_bulletins_seuls_qualifient_le_personnel_sans_paie():
    b = _b()
    b.data["salaries"] = pd.DataFrame([dict(
        nom="A B", emploi="Ingénieur R&D", classification="Cadre",
        debut_contrat="2020", mois_presence=12,
        heures_travaillees=1600.0, cout_employeur=80000.0, matricule="1")])
    b.moteur_personnel()                      # ne doit PAS exiger paie_lignes
    assert "qualification" in b.data
    assert len(b.data["qualification"]) == 1
