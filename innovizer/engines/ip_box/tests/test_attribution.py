"""Tests IP Box / rattachement par actif. `pytest innovizer/engines/ip_box/tests -q`"""
import pandas as pd
import pytest

from innovizer.engines.ip_box import attribution as attr


def _cle(n):
    return str(n).strip().upper()


# ------------------------------------------- coût R&D éligible par personne

def _substrat():
    salaries = pd.DataFrame({
        "nom": ["ALICE MARTIN", "BOB DURAND", "CLARA PETIT"],
        "cout_employeur": [100000.0, 80000.0, 60000.0],
    })
    qualification = pd.DataFrame({
        "nom": ["ALICE MARTIN", "BOB DURAND", "CLARA PETIT"],
        "statut": ["ELIGIBLE_CONFIRMED", "ELIGIBLE_TECHNICIAN", "NON_RD_FUNCTION"],
    })
    return salaries, qualification


def test_cout_eligible_exclut_les_non_eligibles():
    salaries, qualification = _substrat()
    c = attr.cout_eligible_par_personne(salaries, qualification, _cle)
    # même base que le numérateur firm-level : coût chargé, éligibles seulement
    assert c["ALICE MARTIN"] == 100000.0
    assert c["BOB DURAND"] == 80000.0
    assert "CLARA PETIT" not in c.index


# ------------------------------------------- répartition R&D par actif

def test_repartition_au_prorata_des_heures_par_actif():
    temps = pd.DataFrame({
        "person_key": ["ALICE MARTIN", "ALICE MARTIN", "BOB DURAND"],
        "code_projet": ["P1", "P2", "P1"],
        "heures": [300.0, 100.0, 200.0],
    })
    cout = pd.Series({"ALICE MARTIN": 80000.0, "BOB DURAND": 40000.0})
    # P1 -> actif A, P2 -> actif B
    r = attr.rd_eligible_par_actif(temps, cout, {"P1": "A", "P2": "B"})
    pa = dict(zip(r["par_actif"].actif_id, r["par_actif"].cout_rd_eligible))
    # Alice : 300/400 sur A = 60000, 100/400 sur B = 20000 ; Bob : tout sur A = 40000
    assert pa["A"] == pytest.approx(100000.0)   # 60000 + 40000
    assert pa["B"] == pytest.approx(20000.0)
    assert r["projets_non_mappes"] == []


def test_projet_non_mappe_laisse_le_reste_hors_actif():
    temps = pd.DataFrame({
        "person_key": ["ALICE MARTIN", "ALICE MARTIN"],
        "code_projet": ["P1", "PX"],
        "heures": [100.0, 100.0],
    })
    cout = pd.Series({"ALICE MARTIN": 80000.0})
    r = attr.rd_eligible_par_actif(temps, cout, {"P1": "A"})
    # dénominateur = temps TOTAL (200 h) : seule la moitié (P1) tombe sur A,
    # la part PX (non mappée) n'est attribuée à aucun actif -> conservation
    pa = dict(zip(r["par_actif"].actif_id, r["par_actif"].cout_rd_eligible))
    assert pa["A"] == 40000.0            # 80000 × 100/200
    assert r["projets_non_mappes"] == ["PX"]


# ------------------------------------------- recettes par actif

def test_conservation_somme_actifs_inferieure_ou_egale_au_cout_total():
    """Invariant : la somme des coûts R&D répartis par actif ne dépasse jamais
    le coût éligible total (le temps non rattaché reste hors actif), et l'égale
    exactement quand tout le temps des personnes est sur des projets mappés."""
    temps = pd.DataFrame({
        "person_key": ["ALICE MARTIN", "ALICE MARTIN", "BOB DURAND", "BOB DURAND"],
        "code_projet": ["P1", "PX", "P1", "P2"],
        "heures": [100.0, 100.0, 50.0, 50.0],
    })
    cout = pd.Series({"ALICE MARTIN": 80000.0, "BOB DURAND": 40000.0})
    r = attr.rd_eligible_par_actif(temps, cout, {"P1": "A", "P2": "B"})
    som = r["par_actif"].cout_rd_eligible.sum()
    # Alice : PX non mappé -> 40000 hors actif ; Bob : tout mappé -> 40000
    assert som <= cout.sum()
    assert som == pytest.approx(40000.0 + 40000.0)   # 80000, pas 120000


def test_recettes_explicites_priment():
    rec = attr.recettes_par_actif(None, explicites={"A": 300000.0, "B": 50000.0})
    assert dict(zip(rec.actif_id, rec.recettes)) == {"A": 300000.0, "B": 50000.0}


def test_recettes_depuis_map_lignes_sur_le_substrat():
    revenues = pd.DataFrame({
        "ligne": ["V000000", "V000001", "V000002"],
        "montant": [200000.0, 100000.0, 50000.0],
        "nature": ["redevances_licences", "redevances_licences", "prestations_services"],
    })
    rec = attr.recettes_par_actif(
        revenues, map_lignes={"V000000": "A", "V000001": "A"})
    assert dict(zip(rec.actif_id, rec.recettes)) == {"A": 300000.0}


# ------------------------------------------- synthèse par actif

def _actifs():
    return pd.DataFrame({"actif_id": ["A", "B"],
                         "libelle": ["Brevet moteur", "Logiciel X"]})


def test_actif_sans_arbitrage_sort_en_to_review():
    rd = pd.DataFrame({"actif_id": ["A", "B"], "cout_rd_eligible": [100000.0, 50000.0]})
    rec = pd.DataFrame({"actif_id": ["A", "B"], "recettes": [300000.0, 80000.0]})
    s = attr.synthese_par_actif(_actifs(), rd, rec,
                                depenses_totales={"A": 200000.0},
                                resultat_net={"A": 250000.0})
    par = dict(zip(s.actif, s.statut))
    assert par["Brevet moteur"] == "OK"       # A : net + dénominateur fournis
    assert par["Logiciel X"] == "TO_REVIEW"   # B : arbitrages manquants


def test_calcul_par_actif_et_total_n_agrege_que_les_ok():
    rd = pd.DataFrame({"actif_id": ["A", "B"], "cout_rd_eligible": [100000.0, 50000.0]})
    rec = pd.DataFrame({"actif_id": ["A", "B"], "recettes": [300000.0, 80000.0]})
    s = attr.synthese_par_actif(
        _actifs(), rd, rec,
        depenses_totales={"A": 200000.0, "B": 100000.0},
        resultat_net={"A": 250000.0, "B": 40000.0})
    row = {r.actif: r for r in s.itertuples()}
    # A : ratio = min(1 ; 1,3×100000/200000)=0,65 ; base=250000×0,65=162500
    assert row["Brevet moteur"].ratio_nexus == pytest.approx(0.65)
    assert row["Brevet moteur"].base_10 == pytest.approx(162500.0)
    # B : ratio = min(1 ; 1,3×50000/100000)=0,65 ; base=40000×0,65=26000
    assert row["Logiciel X"].base_10 == pytest.approx(26000.0)
    total = [r for r in s.itertuples() if r.actif.startswith("TOTAL")][0]
    assert total.base_10 == pytest.approx(162500.0 + 26000.0)
    assert total.economie == pytest.approx((162500.0 + 26000.0) * 0.15)
