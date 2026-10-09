"""Tests IP Box / Nexus. `pytest innovizer/engines/ip_box/tests -q`"""
import pandas as pd
import pytest

from innovizer import models as m
from innovizer.connectors import ventes
from innovizer.engines.ip_box import nexus


# ------------------------------------------------- connecteur ventes

def _export():
    return pd.DataFrame({
        "Date": ["2025-03-01", "2025-06-30", "2025-09-15", "2025-01-10"],
        "Compte": ["751000", "706000", "707000", "411000"],  # 411 = hors produits
        "Libellé": ["Redevance licence brevet X", "Presta conseil",
                    "Vente marchandise", "Créance client"],
        "Montant": [120000.0, 45000.0, 30000.0, 9999.0],
    })


def test_connecteur_ne_garde_que_les_produits_7xx():
    rec = ventes.revenues_records(_export())
    assert len(rec) == 3                       # le 411 est écarté
    assert set(rec.compte) == {"751000", "706000", "707000"}


def test_connecteur_derive_la_nature_du_compte():
    rec = ventes.revenues_records(_export())
    nat = dict(zip(rec.compte, rec.nature))
    assert nat["751000"] == "redevances_licences"
    assert nat["706000"] == "prestations_services"
    assert nat["707000"] == "ventes_marchandises"


def test_sortie_connecteur_ventes_conforme_au_substrat():
    """Régression (même garde que suppliers/documents) : la sortie réelle du
    connecteur valide contre le schéma revenues, clé 'ligne' comprise."""
    rec = ventes.revenues_records(_export())
    assert m.REVENUES.validate(rec)


def test_cle_ligne_unique_et_presente():
    rec = ventes.revenues_records(_export())
    assert rec.ligne.notna().all()
    assert rec.ligne.is_unique


# ------------------------------------------------- calcul pur Nexus

def test_ratio_plafonne_a_un():
    # 1,3 × 100 / 100 = 1,3 -> plafonné à 1
    assert nexus.ratio_nexus(100, 100) == 1.0


def test_ratio_proportionnel_sous_le_plafond():
    # 1,3 × 50 / 100 = 0,65
    assert nexus.ratio_nexus(50, 100) == pytest.approx(0.65)


def test_ratio_none_si_denominateur_inconnu():
    # un dénominateur absent n'est PAS un ratio de 1
    assert nexus.ratio_nexus(100, None) is None
    assert nexus.ratio_nexus(100, 0) is None


def test_base_et_economie():
    ratio = nexus.ratio_nexus(60, 100)         # 0,78
    base = nexus.base_ip_box(200000, ratio)    # 156000
    assert base == pytest.approx(156000.0)
    eco = nexus.economie_impot(base)           # × (0,25 − 0,10)
    assert eco == pytest.approx(156000.0 * 0.15)


def test_base_none_propage_si_ratio_inconnu():
    assert nexus.base_ip_box(200000, None) is None
    assert nexus.economie_impot(None) is None


# ------------------------------------------- réutilisation du substrat

def _substrat_partage():
    salaries = pd.DataFrame({
        "nom": ["ALICE MARTIN", "BOB DURAND", "CLARA PETIT"],
        "cout_employeur": [90000.0, 70000.0, 50000.0],
    })
    qualification = pd.DataFrame({
        "nom": ["ALICE MARTIN", "BOB DURAND", "CLARA PETIT"],
        "statut": ["ELIGIBLE_CONFIRMED", "ELIGIBLE_TECHNICIAN", "NON_RD_FUNCTION"],
    })
    return salaries, qualification


def test_numerateur_relu_depuis_le_substrat_partage():
    salaries, qualification = _substrat_partage()
    num = nexus.depenses_rd_personnel_eligibles(salaries, qualification)
    # Clara (NON_RD) exclue : 90000 + 70000
    assert num["total"] == 160000.0
    assert set(num["detail"].nom) == {"ALICE MARTIN", "BOB DURAND"}


def test_recettes_cibles_751_seulement():
    rec = ventes.revenues_records(_export())
    assert nexus.recettes_cibles(rec) == 120000.0   # la ligne 751 uniquement


# ------------------------------------------------------- synthèse

def test_synthese_marque_to_review_sans_arbitrage():
    salaries, qualification = _substrat_partage()
    rec = ventes.revenues_records(_export())
    s = nexus.synthese(rec, salaries, qualification)   # ni net ni dénominateur
    par = dict(zip(s.indicateur, s.statut))
    # ce que le substrat permet est calculé...
    assert par["dépenses R&D personnel éligibles (numérateur Nexus)"] == "OK"
    assert par["recettes redevances/licences 751 (brutes)"] == "OK"
    # ...ce qui exige un arbitrage sort en TO_REVIEW (jamais présumé)
    assert par["ratio Nexus (plafonné à 1)"] == "TO_REVIEW"
    assert par["base imposable à 10 %"] == "TO_REVIEW"


def test_synthese_calcule_avec_arbitrages():
    salaries, qualification = _substrat_partage()
    rec = ventes.revenues_records(_export())
    s = nexus.synthese(rec, salaries, qualification,
                       resultat_net_ip=100000.0, depenses_totales=200000.0)
    val = dict(zip(s.indicateur, s.valeur))
    sta = dict(zip(s.indicateur, s.statut))
    # ratio = min(1 ; 1,3 × 160000 / 200000) = min(1 ; 1,04) = 1
    assert val["ratio Nexus (plafonné à 1)"] == 1.0
    assert sta["ratio Nexus (plafonné à 1)"] == "OK"
    assert val["base imposable à 10 %"] == 100000.0
    assert val["économie d'impôt vs 25 %"] == pytest.approx(15000.0)
