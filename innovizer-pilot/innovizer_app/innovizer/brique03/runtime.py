"""
Brique 03 — couches d'exécution autour du moteur.

  store    persistance JSON des sessions (transcript + fiche), un fichier par
           entretien, réécrit à chaque tour. Pas de base de données au MVP :
           un dossier de JSON se relit, se versionne et s'audite.
  cli      mode texte interactif, ou scripté pour les tests
  api      serveur HTTP minimal (stdlib) : le frontend ou le webhook Vapi
           POST /interviews, POST /interviews/{id}/answer, GET /interviews/{id}

La voix n'est pas ici. Vapi appelle l'API en texte ; le moteur ne sait pas
s'il parle à un humain, à un widget ou à un test.
"""

import json
import sys
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ..engines import fiche_projet as fp
from .interview import Entretien


# ------------------------------------------------------------------ store

class Store:
    def __init__(self, dossier="./entretiens"):
        self.d = Path(dossier)
        self.d.mkdir(parents=True, exist_ok=True)

    def sauver(self, e: Entretien):
        p = self.d / f"{e.id}.json"
        p.write_text(json.dumps(dict(
            entretien=e.export(), fiche=asdict(e.fiche)), ensure_ascii=False, indent=2))
        return p

    def lister(self):
        return sorted(p.stem for p in self.d.glob("*.json"))

    def charger_fiche(self, id_):
        d = json.loads((self.d / f"{id_}.json").read_text())["fiche"]
        return d


# -------------------------------------------------------------------- cli

def executer_cli(fiche: fp.FicheProjet, reponses: list | None = None,
                 projets_connus=None, interlocuteur="", store: Store | None = None,
                 silencieux=False):
    """reponses : liste de chaînes pour un déroulé scripté, sinon interactif."""
    e = Entretien(fiche, projets_connus=projets_connus, interlocuteur=interlocuteur)
    out = (lambda *a, **k: None) if silencieux else print
    out(f"\nEVA › {e.ouverture()}\n")
    it = iter(reponses) if reponses is not None else None
    while True:
        t = e.prochaine_question()
        if t is None:
            break
        out(f"EVA [{t.axe}/{t.nature}] › {t.question}")
        if t.nature == "cloture":
            break
        if it is not None:
            try:
                rep = next(it)
            except StopIteration:
                rep = ""
            out(f"CTO › {rep}")
        else:
            rep = input("CTO › ")
        cl = e.repondre(rep)
        if cl and "etat" in cl:
            out(f"      ↳ {cl['etat']}  {cl.get('justification','')}")
        if store:
            store.sauver(e)
        out("")
    fiche = e.finaliser()
    if store:
        store.sauver(e)
    return e, fiche


# -------------------------------------------------------------------- api

_SESSIONS: dict[str, Entretien] = {}


class Handler(BaseHTTPRequestHandler):
    store = Store()

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _corps(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        parts = self.path.strip("/").split("/")
        if parts == ["interviews"]:
            d = self._corps()
            ctx = fp.Contexte(**d["contexte"])
            fiche = fp.FicheProjet(contexte=ctx)
            fiche.investigation.regime_pressenti = d.get("regime_pressenti", "A_DETERMINER")
            e = Entretien(fiche, projets_connus=d.get("projets_connus", []),
                          interlocuteur=d.get("interlocuteur", ""))
            _SESSIONS[e.id] = e
            t = e.prochaine_question()
            return self._json(201, dict(id=e.id, ouverture=e.ouverture(),
                                        question=asdict(t)))
        if len(parts) == 3 and parts[0] == "interviews" and parts[2] == "answer":
            e = _SESSIONS.get(parts[1])
            if not e:
                return self._json(404, dict(erreur="session inconnue"))
            cl = e.repondre(self._corps().get("reponse", ""))
            t = e.prochaine_question()
            self.store.sauver(e)
            return self._json(200, dict(classification=cl, couverture=e.couverture(),
                                        question=asdict(t) if t else None,
                                        termine=e.termine()))
        if len(parts) == 3 and parts[0] == "interviews" and parts[2] == "finalize":
            e = _SESSIONS.get(parts[1])
            if not e:
                return self._json(404, dict(erreur="session inconnue"))
            f = e.finaliser()
            self.store.sauver(e)
            return self._json(200, dict(fiche=asdict(f)))
        self._json(404, dict(erreur="route inconnue"))

    def do_GET(self):
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "interviews":
            e = _SESSIONS.get(parts[1])
            if not e:
                return self._json(404, dict(erreur="session inconnue"))
            return self._json(200, e.export())
        self._json(404, dict(erreur="route inconnue"))

    def log_message(self, *a):  # silence
        pass


def servir(port=3013):
    print(f"Brique 03 — API sur http://localhost:{port}")
    HTTPServer(("", port), Handler).serve_forever()


if __name__ == "__main__":
    servir(int(sys.argv[1]) if len(sys.argv) > 1 else 3013)
