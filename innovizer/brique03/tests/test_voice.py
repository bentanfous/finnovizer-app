"""Tests du pont vocal Vapi (Brique 03). Testable sans compte Vapi."""

from innovizer.engines.fiscalite_recherche import fiche_projet as fp
from innovizer.brique03.voice import VapiBridge


def _fiche():
    ctx = fp.Contexte(code_projet="TEST", heures=1200.0,
                      periode="01 → 12",
                      collaborateurs=[dict(nom="A B", emploi="Ingénieur",
                                           statut_qualif="ELIGIBLE_CONFIRMED", heures=800)])
    f = fp.FicheProjet(contexte=ctx)
    f.investigation.regime_pressenti = "CIR"
    return f


def _payload(cle, user=None, history=None):
    msgs = list(history or [])
    if user is not None:
        msgs.append({"role": "user", "content": user})
    return {"call": {"id": cle}, "messages": msgs}


def test_session_inconnue_ne_plante_pas():
    b = VapiBridge()
    r = b.handle_chat_completion(_payload("inexistant", user="bonjour"))
    assert r["choices"][0]["message"]["content"]
    assert r["_innovizer"]["fin_entretien"] is True


def test_premier_tour_ouvre_et_pose_question():
    b = VapiBridge()
    cle, e = b.ouvrir(_fiche())
    r = b.handle_chat_completion(_payload(cle))  # pas encore de réponse user
    txt = r["choices"][0]["message"]["content"]
    assert "TEST" in txt            # l'ouverture nomme le projet
    assert len(e.transcript) >= 1   # une question a été posée


def test_interview_id_en_variable_dynamique():
    b = VapiBridge()
    cle, _ = b.ouvrir(_fiche(), cle="iv-123")
    payload = {"call": {"id": "autre-call-id",
                        "assistantOverrides": {"variableValues": {"interview_id": "iv-123"}}},
               "messages": []}
    r = b.handle_chat_completion(payload)
    assert "TEST" in r["choices"][0]["message"]["content"]


def test_reponse_fait_avancer_l_entretien():
    b = VapiBridge()
    cle, e = b.ouvrir(_fiche())
    b.handle_chat_completion(_payload(cle))  # ouverture + Q1
    q1 = e.transcript[-1].question
    r = b.handle_chat_completion(_payload(
        cle, user="Le problème était qu'on ne savait pas faire fonctionner le système."))
    q2 = r["choices"][0]["message"]["content"]
    assert q2 and q2 != q1           # on a avancé


def test_fin_entretien_leve_le_drapeau():
    b = VapiBridge()
    cle, e = b.ouvrir(_fiche())
    b.handle_chat_completion(_payload(cle))
    fin = False
    for _ in range(80):
        r = b.handle_chat_completion(_payload(cle, user="réponse neutre de longueur correcte ici"))
        if r["_innovizer"]["fin_entretien"]:
            fin = True
            break
    assert fin
    # la fiche a été finalisée
    assert e.fiche.synthese.defendabilite in ("FAIBLE", "MOYENNE", "FORTE")


def test_streaming_chunks_bien_formes():
    chunks = list(VapiBridge.completion_stream_chunks("Bonjour."))
    assert chunks[-1] == "data: [DONE]\n\n"
    assert any("Bonjour." in c for c in chunks)
