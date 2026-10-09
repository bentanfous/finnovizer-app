"""
Brique 03 — pont vocal Vapi (architecture B : Vapi = voix, Eva = cerveau).

PRINCIPE
    Vapi gère le temps réel (micro → transcription → voix), mais ne décide
    RIEN de l'entretien. À chaque tour, Vapi appelle cet endpoint en mode
    « custom LLM » (compatible OpenAI chat/completions) ; on extrait la
    dernière réponse de l'interlocuteur, on la passe au moteur Eva, et on
    renvoie la question suivante — qu'Eva a décidée — pour que Vapi la
    prononce avec la voix ElevenLabs configurée côté Vapi.

POURQUOI C'EST OPTIMAL EN TOKENS
    Le « LLM » que Vapi appelle, c'est nous. La conduite d'entretien
    (classement VIDE/PARTIEL/COMPLET, relance, challenge, question suivante)
    tourne sur ClassifieurRegles : déterministe, ZÉRO token LLM. Vapi nous
    envoie tout l'historique à chaque tour, mais on ne le repaye pas : on
    ignore l'historique et on lit l'état de la session côté serveur. Le seul
    coût LLM optionnel est le classement fin (ClassifieurLLM) et la synthèse
    finale, appelée une seule fois. Voir calcul de coût dans le README voix.

CE QUE CE MODULE NE FAIT PAS
    Ni STT, ni TTS, ni WebRTC : tout ça reste chez Vapi. Ce module est une
    couche de traduction de protocole autour du moteur Eva déjà testé. La
    logique métier n'est pas dupliquée ici.
"""

import json
import time
import uuid

from ..engines.fiscalite_recherche import fiche_projet as fp
from .interview import Entretien


class VapiBridge:
    """Tient les sessions d'entretien et traduit le protocole Vapi ↔ Eva.

    Une session Vapi est identifiée par son `call.id` (ou un `interview_id`
    passé en variable dynamique). On la relie à un objet Entretien vivant.
    """

    def __init__(self):
        self._sessions: dict[str, Entretien] = {}

    # ------------------------------------------------- cycle de vie

    def ouvrir(self, fiche: fp.FicheProjet, projets_connus=None,
               interlocuteur="", cle: str | None = None) -> tuple[str, Entretien]:
        e = Entretien(fiche, projets_connus=projets_connus, interlocuteur=interlocuteur)
        cle = cle or e.id
        self._sessions[cle] = e
        return cle, e

    def get(self, cle: str) -> Entretien | None:
        return self._sessions.get(cle)

    # ------------------------------------------------- protocole Vapi

    @staticmethod
    def _cle_depuis_payload(payload: dict) -> str | None:
        """Vapi passe les variables dynamiques de l'assistant et un call.id.
        On accepte interview_id (variable dynamique) en priorité, puis call.id."""
        call = payload.get("call") or {}
        meta = (call.get("assistantOverrides") or {}).get("variableValues") or {}
        return meta.get("interview_id") or call.get("id") or payload.get("interview_id")

    @staticmethod
    def _dernier_message_user(payload: dict) -> str:
        msgs = payload.get("messages") or []
        for m in reversed(msgs):
            if m.get("role") == "user":
                return (m.get("content") or "").strip()
        return ""

    def handle_chat_completion(self, payload: dict) -> dict:
        """Point d'entrée du webhook custom-LLM de Vapi.

        Entrée : corps OpenAI-compatible envoyé par Vapi (messages, call…).
        Sortie : une complétion OpenAI-compatible dont le `content` est la
        prochaine phrase qu'Eva doit prononcer.
        """
        cle = self._cle_depuis_payload(payload)
        e = self.get(cle) if cle else None

        if e is None:
            # session inconnue : Vapi a appelé sans interview_id valide.
            # On répond poliment plutôt que de planter la ligne.
            return self._completion(
                "Je ne retrouve pas le dossier de cet entretien. "
                "Nous allons devoir le reprendre. Pouvez-vous vérifier le lien ?",
                fin=True)

        user = self._dernier_message_user(payload)

        # Premier tour : pas encore de réponse → on ouvre et on pose Q1.
        if not e.transcript:
            t = e.prochaine_question()
            return self._completion(f"{e.ouverture()} {t.question}")

        # Tours suivants : on enregistre la réponse, on avance.
        if user:
            try:
                e.repondre(user)
            except RuntimeError:
                # pas de question en attente côté moteur : on resynchronise
                pass

        t = e.prochaine_question()
        if t is None or e.termine():
            # fin : on finalise la fiche en arrière-plan et on clôt la ligne.
            e.finaliser()
            phrase = ("Merci, j'ai tout ce qu'il me faut pour cette étape. "
                      "Un expert reprendra la synthèse avant intégration au dossier.")
            return self._completion(phrase, fin=True)
        return self._completion(t.question)

    # ------------------------------------------------- mise en forme OpenAI

    @staticmethod
    def _completion(contenu: str, fin: bool = False) -> dict:
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "innovizer-eva",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": contenu},
                "finish_reason": "stop",
            }],
            # drapeau interne lu par l'endpoint pour décider d'un end-of-call
            "_innovizer": {"fin_entretien": fin},
        }

    @staticmethod
    def completion_stream_chunks(contenu: str):
        """Variante SSE si Vapi est configuré en streaming. Un seul chunk
        suffit : la phrase d'Eva est courte et déjà entièrement décidée."""
        cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        base = {"id": cid, "object": "chat.completion.chunk",
                "created": int(time.time()), "model": "innovizer-eva"}
        yield "data: " + json.dumps({**base, "choices": [
            {"index": 0, "delta": {"role": "assistant", "content": contenu},
             "finish_reason": None}]}) + "\n\n"
        yield "data: " + json.dumps({**base, "choices": [
            {"index": 0, "delta": {}, "finish_reason": "stop"}]}) + "\n\n"
        yield "data: [DONE]\n\n"


BRIDGE = VapiBridge()
