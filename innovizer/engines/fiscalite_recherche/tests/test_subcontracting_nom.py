"""Rapprochement par nom contre le référentiel MESR (candidat à confirmer)."""
import pandas as pd
from innovizer.engines.fiscalite_recherche import subcontracting as sc


def test_normaliser_nom_retire_formes_juridiques():
    assert sc.normaliser_nom("Savelec SAS") == "SAVELEC"
    assert sc.normaliser_nom("SAVELEC") == "SAVELEC"
    assert sc.normaliser_nom("Groupe Dunasys France") == "DUNASYS"


def test_indexer_et_candidat_couverture_annee():
    ref = pd.DataFrame({
        "Désignation": ["SAVELEC", "SAVELEC"],
        "Numéro SIREN": [325214765, 325214765],
        "Début d'agrément": [2023, 2026],
        "Fin d'agrément": [2025, 2028]})
    idx = sc.indexer_referentiel(ref)
    c = sc.candidat_par_nom("SAVELEC SAS", idx, 2025)     # forme juridique tolérée
    assert c and c["siren_mesr"] == "325214765" and c["couvre_annee"]
    assert sc.candidat_par_nom("INCONNU SARL", idx, 2025) is None


def test_candidat_hors_exercice():
    ref = pd.DataFrame({"Désignation": ["VIEUXPRESTA"], "Numéro SIREN": [111222333],
                        "Début d'agrément": [2010], "Fin d'agrément": [2014]})
    c = sc.candidat_par_nom("VieuxPresta", sc.indexer_referentiel(ref), 2025)
    assert c and not c["couvre_annee"]
