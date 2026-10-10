"""Test de la PLOMBERIE LIVE du connecteur PayFit : on lance un petit serveur
HTTP local qui imite l'API PayFit (réponses au format OpenAPI, auth Bearer,
pagination meta.nextPageToken, param date=YYYYMM), et on fait tourner le VRAI
code client `requests` dessus (pas le raccourci fixture). Seule chose non
couverte sans clé : que le serveur RÉEL de PayFit respecte sa propre spec."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import pytest

from innovizer import models as m
from innovizer.connectors import payfit as pf

requests = pytest.importorskip("requests")

CID = "comp_live"
_COLLAB_P1 = [{"id": "col_1", "firstName": "Alice", "lastName": "Martin", "matricule": "001"}]
_COLLAB_P2 = [{"id": "col_2", "firstName": "Bob", "lastName": "Durand", "matricule": "002"}]
_CONTRACTS = [
    {"contractId": "ct_1", "collaboratorId": "col_1", "jobName": "Ingénieur R&D",
     "statutConventionnelDsn": "Cadre", "startDate": "2020-01-01"},
    {"contractId": "ct_2", "collaboratorId": "col_2", "jobName": "Comptable",
     "statutConventionnelDsn": "ETAM", "startDate": "2019-01-01"},
]
_ACCOUNTING = [
    {"operationDate": "2025-01-31", "accountId": "645300",
     "accountName": "Assurance vieillesse", "debit": 900.0, "credit": None,
     "employeeFullName": "Alice Martin", "contractId": "ct_1", "analyticCodes": []},
    {"operationDate": "2025-01-31", "accountId": "645400", "accountName": "APEC",
     "debit": 20.0, "credit": None, "employeeFullName": "Alice Martin",
     "contractId": "ct_1", "analyticCodes": []},
]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/introspect":
            self._json(200, {"company_id": CID})
        else:
            self._json(404, {})

    def do_GET(self):
        # auth obligatoire
        if self.headers.get("Authorization") != "Bearer LIVE-KEY":
            return self._json(401, {"error": "unauthorized"})
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == f"/companies/{CID}/collaborators":
            if q.get("nextPageToken") == ["p2"]:
                return self._json(200, {"collaborators": _COLLAB_P2,
                                        "meta": {"nextPageToken": None}})
            return self._json(200, {"collaborators": _COLLAB_P1,
                                    "meta": {"nextPageToken": "p2"}})
        if u.path == f"/companies/{CID}/contracts-fr":
            return self._json(200, {"contracts": _CONTRACTS,
                                    "meta": {"nextPageToken": None}})
        if u.path == f"/companies/{CID}/accounting-v2":
            assert q.get("date") == ["202501"], f"param date attendu 202501, reçu {q}"
            return self._json(200, _ACCOUNTING)   # tableau nu
        self._json(404, {})


@pytest.fixture
def serveur():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _client(base):
    s = requests.Session()
    s.trust_env = False   # ignore le proxy pour atteindre 127.0.0.1
    return pf.PayfitClient(token="LIVE-KEY", base_url=base, session=s,
                           introspect_url=base + "/introspect")


def test_plomberie_live_de_bout_en_bout(serveur):
    c = _client(serveur)
    assert c.introspect() == CID                      # POST /introspect réel
    people = pf.charger_people(c)                      # GET paginé (2 pages)
    assert set(people.nom) == {"Alice Martin", "Bob Durand"}  # pagination OK
    assert m.PEOPLE.validate(people)

    fe = pf.charger_financial_entries(c, "2025-01")    # param date=202501 vérifié serveur
    assert m.FINANCIAL_ENTRIES.validate(fe)

    s = pf.assiette_depuis(c.accounting_v2("2025-01"), people)
    r = s[s.person_key == "ALICE MARTIN"].iloc[0]
    assert r["ELIGIBLE"] == 900.0 and r["NON_ELIGIBLE"] == 20.0


def test_auth_refusee_sans_bonne_cle(serveur):
    c = pf.PayfitClient(token="MAUVAISE", base_url=serveur,
                        session=_no_proxy(), company_id=CID)
    with pytest.raises(requests.HTTPError):
        c.collaborators()


def _no_proxy():
    s = requests.Session()
    s.trust_env = False
    return s
