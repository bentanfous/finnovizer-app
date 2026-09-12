"""
Brique 03 — moteur d'entretien.

Machine à états par axe :

    VIDE ──ouverture──▶ répondu ──classé──┬──COMPLET──▶ axe clos
                                          ├──PARTIEL, non challengé──▶ relance
                                          ├──PARTIEL, vague──▶ challenge
                                          └──VIDE──▶ relance puis clos VIDE

Règles :
  - un axe reçoit au plus MAX_TOURS questions (ouverture + relances/challenge).
    Au-delà, on passe : Eva n'insiste pas, elle note ce qui manque.
  - le challenge est posé une seule fois par axe, et uniquement si la réponse
    est vague. Il est tracé dans la fiche (champ `challenge`).
  - les axes déjà couverts par le contexte Brique 01 (moyens) démarrent
    PARTIEL, avec la question d'ouverture reformulée en confirmation.
  - l'entretien se termine par la question de liens pour le mapper.

Toute la logique est synchrone et sans I/O : le moteur reçoit du texte, rend
du texte. La voix, l'HTTP et la persistance sont des couches autour.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import uuid

from ..engines import fiche_projet as fp
from . import questions as Q
from .classifier import ClassifieurRegles

MAX_TOURS = 3


@dataclass
class Tour:
    horodatage: str
    axe: str
    nature: str             # ouverture / relance / challenge / liens / cloture
    question: str
    reponse: str = ""
    classification: dict | None = None


@dataclass
class EtatAxe:
    tours: int = 0
    challenge_pose: bool = False
    clos: bool = False


class Entretien:
    def __init__(self, fiche: fp.FicheProjet, classifieur=None,
                 projets_connus: list | None = None, interlocuteur: str = ""):
        self.id = str(uuid.uuid4())[:8]
        self.fiche = fiche
        self.cls = classifieur or ClassifieurRegles()
        self.projets_connus = projets_connus or []
        self.transcript: list[Tour] = []
        self.etats = {a: EtatAxe() for a in Q.ORDRE}
        self._ordre = list(Q.ORDRE)
        self._liens_pose = False
        self._termine = False
        self.fiche.investigation.interlocuteur = interlocuteur
        self.fiche.investigation.date_entretien = datetime.now(timezone.utc).date().isoformat()
        self.fiche.investigation.transcript_id = self.id
        self._preremplir_depuis_contexte()

    # ------------------------------------------------------------ contexte

    def _preremplir_depuis_contexte(self):
        c = self.fiche.contexte
        if c.collaborateurs:
            ax = self.fiche.investigation.axes["moyens"]
            ax.etat = "PARTIEL"
            ax.contenu = (f"[Brique 01] {len(c.collaborateurs)} collaborateurs, "
                          f"{c.heures} h sur {c.periode}.")
        if self.fiche.investigation.regime_pressenti in ("CII", "MIXTE"):
            for k in Q.ORDRE_CII:
                self.fiche.investigation.axes_cii.setdefault(k, fp.Axe())
                self.etats[k] = EtatAxe()
            self._ordre += Q.ORDRE_CII

    def ouverture(self) -> str:
        c = self.fiche.contexte
        equipe = ", ".join(x["nom"].title() for x in c.collaborateurs[:3])
        plus = f" et {len(c.collaborateurs) - 3} autres" if len(c.collaborateurs) > 3 else ""
        return (f"Bonjour. Je vais vous interroger sur le projet {c.code_projet}. "
                f"Je sais déjà qu'il a mobilisé {c.heures:.0f} heures sur la période "
                f"{c.periode}, avec {equipe}{plus}. Je vais me concentrer sur ce que "
                f"les chiffres ne disent pas : le problème, les difficultés, les essais.")

    # ------------------------------------------------------------ moteur

    def _axe_courant(self):
        for a in self._ordre:
            if not self.etats[a].clos:
                return a
        return None

    def _banque(self, axe):
        return Q.QUESTIONS.get(axe) or Q.QUESTIONS_CII[axe]

    def _axe_obj(self, axe) -> fp.Axe:
        inv = self.fiche.investigation
        return inv.axes[axe] if axe in inv.axes else inv.axes_cii[axe]

    def prochaine_question(self) -> Tour | None:
        if self._termine:
            return None
        axe = self._axe_courant()
        if axe is None:
            if not self._liens_pose:
                return self._enregistrer("liens", "liens", Q.QUESTION_LIENS)
            self._termine = True
            return self._enregistrer("cloture", "cloture",
                                     "Merci. J'ai ce qu'il me faut pour cette étape.")

        st, b, ax = self.etats[axe], self._banque(axe), self._axe_obj(axe)
        if st.tours == 0:
            q = b["ouverture"]
            if ax.etat == "PARTIEL" and ax.contenu.startswith("[Brique 01]"):
                q = (f"D'après les données de paie et de temps, {ax.contenu[12:]} "
                     f"Est-ce exact, et y a-t-il eu des sous-traitants ou du matériel "
                     f"spécifique ?")
            return self._enregistrer(axe, "ouverture", q)

        dernier = next((t for t in reversed(self.transcript) if t.axe == axe), None)
        cl = dernier.classification if dernier else {}
        if cl and cl.get("vague") and not st.challenge_pose and b["challenge"]:
            st.challenge_pose = True
            ax.challenge = b["challenge"]
            return self._enregistrer(axe, "challenge", b["challenge"])
        idx = min(st.tours - 1, len(b["relances"]) - 1)
        if idx < 0 or not b["relances"]:
            st.clos = True
            return self.prochaine_question()
        return self._enregistrer(axe, "relance", b["relances"][idx])

    def repondre(self, texte: str) -> dict:
        if not self.transcript or self.transcript[-1].reponse:
            raise RuntimeError("aucune question en attente")
        tour = self.transcript[-1]
        tour.reponse = texte

        if tour.nature == "liens":
            self._liens_pose = True
            cites = [p for p in self.projets_connus if p.lower() in texte.lower()]
            for p in cites:
                self.fiche.synthese.liens_verrou.append(
                    dict(code_projet=p, nature_du_lien="cité par l'interlocuteur",
                         source=self.fiche.investigation.interlocuteur or "entretien"))
            tour.classification = dict(projets_cites=cites)
            return tour.classification
        if tour.nature == "cloture":
            return {}

        axe = tour.axe
        b, ax, st = self._banque(axe), self._axe_obj(axe), self.etats[axe]
        c = self.cls.classer(axe, texte, b["criteres"], self.projets_connus)
        tour.classification = asdict(c)
        st.tours += 1

        # fusion : on ne rétrograde jamais un axe, on l'enrichit
        rang = {"VIDE": 0, "PARTIEL": 1, "COMPLET": 2}
        if rang[c.etat] >= rang[ax.etat]:
            ax.etat = c.etat
        if texte.strip() and not any(re.search(p, texte.lower()) for p in
                                     (r"^\s*(non|aucun|rien)\b",)):
            ax.contenu = (ax.contenu + " " + texte.strip()).strip()
        ax.citations.append(texte.strip()[:300])
        for p in c.preuves_citees:
            if p not in ax.preuves_demandees:
                ax.preuves_demandees.append(p)
        for p in b["preuves"]:
            if p not in ax.preuves_demandees:
                ax.preuves_demandees.append(p)

        if c.etat == "COMPLET" or st.tours >= MAX_TOURS:
            st.clos = True
        return tour.classification

    def _enregistrer(self, axe, nature, question) -> Tour:
        t = Tour(datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 axe, nature, question)
        self.transcript.append(t)
        return t

    # ------------------------------------------------------------ sortie

    def termine(self) -> bool:
        return self._termine

    def finaliser(self) -> fp.FicheProjet:
        self.fiche.investigation.duree_min = max(
            1, len([t for t in self.transcript if t.reponse]) * 2)
        self.fiche.synthese = fp.synthetiser(self.fiche)
        return self.fiche

    def couverture(self) -> dict:
        return {a: self._axe_obj(a).etat for a in self._ordre}

    def export(self) -> dict:
        return dict(id=self.id, projet=self.fiche.contexte.code_projet,
                    transcript=[asdict(t) for t in self.transcript],
                    couverture=self.couverture(), termine=self._termine)


import re  # noqa: E402  (utilisé dans repondre)
