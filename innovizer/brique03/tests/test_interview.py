"""Tests Brique 03 — moteur d'entretien. `python -m pytest innovizer/brique03/tests -q`"""

import json
import pytest

from innovizer.engines import fiche_projet as fp
from innovizer.brique03 import questions as Q
from innovizer.brique03.classifier import ClassifieurRegles, ClassifieurLLM
from innovizer.brique03.interview import Entretien, MAX_TOURS
from innovizer.brique03.runtime import executer_cli, Store


def fiche(regime="CIR", collab=True):
    ctx = fp.Contexte(code_projet="TEST", heures=1200.0, periode="01/2025 → 12/2025",
                      collaborateurs=[dict(nom="A B", emploi="Ingénieur", statut_qualif="ELIGIBLE", heures=800)]
                      if collab else [])
    f = fp.FicheProjet(contexte=ctx)
    f.investigation.regime_pressenti = regime
    return f


# ---------------------------------------------------------------- classifieur

def test_reponse_vide():
    c = ClassifieurRegles().classer("verrou", "non", ["incertitude", "point_precis"])
    assert c.etat == "VIDE"


def test_reponse_vague_declenche_challenge():
    c = ClassifieurRegles().classer("verrou", "On voulait améliorer les performances de "
                                    "notre système, le rendre plus rapide et plus efficace.",
                                    ["incertitude", "point_precis"])
    assert c.vague and c.etat != "COMPLET"


def test_reponse_complete():
    r = ("On ne savait pas s'il était possible d'inférer la structure des messages "
         "multiplexés avec un taux de faux positifs sous 5 %, aucune garantie de converger.")
    c = ClassifieurRegles().classer("verrou", r, ["incertitude", "point_precis"])
    assert c.etat == "COMPLET" and not c.vague


def test_preuves_citees():
    c = ClassifieurRegles().classer("preuves", "Tout est dans le dépôt git avec les "
                                    "commits datés, plus les comptes-rendus de revue de 2025.",
                                    ["documents", "dates"])
    assert "git" in c.preuves_citees and "compte-rendu" in c.preuves_citees


def test_llm_bascule_sur_regles_en_cas_d_erreur():
    def casse(_):
        raise ConnectionError("réseau")
    c = ClassifieurLLM(casse).classer("verrou", "non", ["incertitude"])
    assert c.etat == "VIDE" and "LLM indisponible" in c.justification


def test_llm_json_valide():
    rep = json.dumps(dict(etat="COMPLET", criteres_ok=["incertitude"], vague=False,
                          hors_sujet=False, preuves_citees=[], projets_cites=[],
                          confiance=0.9, justification="ok"))
    c = ClassifieurLLM(lambda _: rep).classer("verrou", "x", ["incertitude"])
    assert c.etat == "COMPLET" and c.confiance == 0.9


# ------------------------------------------------------------------ moteur

def test_ordre_et_ouverture():
    e = Entretien(fiche())
    t = e.prochaine_question()
    assert t.axe == "probleme" and t.nature == "ouverture"
    assert "TEST" in e.ouverture() and "1200" in e.ouverture()


def test_moyens_prerempli_depuis_contexte():
    e = Entretien(fiche())
    assert e.fiche.investigation.axes["moyens"].etat == "PARTIEL"
    assert e.fiche.investigation.axes["moyens"].contenu.startswith("[Brique 01]")


def test_repondre_sans_question_leve():
    e = Entretien(fiche())
    with pytest.raises(RuntimeError):
        e.repondre("x")


def test_challenge_pose_une_seule_fois():
    e = Entretien(fiche())
    while e.prochaine_question().axe != "verrou":
        e.repondre("Réponse suffisamment longue et détaillée pour être partielle sans rien dire.")
    e.repondre("On voulait optimiser et améliorer les performances.")
    t = e.prochaine_question()
    assert t.nature == "challenge"
    e.repondre("On voulait aller plus vite.")
    t2 = e.prochaine_question()
    assert t2.nature != "challenge"
    assert e.fiche.investigation.axes["verrou"].challenge


def test_max_tours_ferme_l_axe():
    e = Entretien(fiche())
    n = 0
    while True:
        t = e.prochaine_question()
        if t.axe != "probleme":
            break
        e.repondre("Une réponse partielle de longueur suffisante pour ne pas être vide.")
        n += 1
    assert n == MAX_TOURS


def test_jamais_retrograde():
    e = Entretien(fiche())
    e.prochaine_question()
    e.repondre("Le problème était difficile car au départ la situation ne fonctionnait pas "
               "du tout et personne ne savait comment faire.")
    assert e.fiche.investigation.axes["probleme"].etat == "COMPLET"
    # une réponse VIDE ultérieure sur le même axe ne le fait pas redescendre
    e.etats["probleme"].clos = False
    e.prochaine_question()
    e.repondre("non")
    assert e.fiche.investigation.axes["probleme"].etat == "COMPLET"


def test_liens_alimentent_le_mapper():
    e = Entretien(fiche(), projets_connus=["INT_Dunagate", "INT_DCar-S"])
    for _ in range(50):
        t = e.prochaine_question()
        if t is None or t.nature == "cloture":
            break
        e.repondre("Oui, on a eu exactement la même difficulté sur INT_Dunagate."
                   if t.nature == "liens" else "Une réponse partielle assez longue pour compter.")
    liens = [l["code_projet"] for l in e.fiche.synthese.liens_verrou]
    assert liens == ["INT_Dunagate"]


def test_regime_cii_ajoute_les_axes():
    e = Entretien(fiche(regime="CII"))
    assert "produit" in e.couverture() and "marche" in e.couverture()


def test_finaliser_produit_synthese():
    e, f = executer_cli(fiche(), reponses=["x"] * 40, silencieux=True)
    assert f.synthese.defendabilite in ("FAIBLE", "MOYENNE", "FORTE")
    assert 0 <= f.synthese.couverture_pct <= 100
    assert f.synthese.revue_experte_requise is True


def test_store_roundtrip(tmp_path):
    s = Store(tmp_path)
    e, f = executer_cli(fiche(), reponses=["x"] * 40, store=s, silencieux=True)
    assert e.id in s.lister()
    d = s.charger_fiche(e.id)
    assert d["contexte"]["code_projet"] == "TEST"
    assert d["synthese"]["defendabilite"] == f.synthese.defendabilite


def test_toutes_les_questions_ont_criteres_connus():
    from innovizer.brique03.classifier import CRITERES
    for banque in (Q.QUESTIONS, Q.QUESTIONS_CII):
        for axe, q in banque.items():
            for c in q["criteres"]:
                assert c in CRITERES, f"{axe}: critère {c} sans regex"
