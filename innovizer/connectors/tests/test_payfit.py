"""Connecteur PayFit (API) — mappers testés sur fixtures, sans clé ni réseau.
Les fixtures suivent les VRAIS schémas OpenAPI PayFit (developers.payfit.io
/reference) : collaborators, contracts-fr, et accounting-v2 (tableau nu)."""
import pandas as pd

from innovizer import models as m
from innovizer.connectors import payfit as pf


COLLABORATORS = [
    {"id": "col_1", "firstName": "Alice", "lastName": "Martin", "matricule": "001"},
    {"id": "col_2", "firstName": "Bob", "lastName": "Durand", "matricule": "002"},
]
CONTRACTS = [
    {"contractId": "ct_1", "collaboratorId": "col_1", "jobName": "Ingénieur R&D",
     "statutConventionnelDsn": "Cadre", "startDate": "2020-01-01"},
    {"contractId": "ct_2", "collaboratorId": "col_2", "jobName": "Comptable",
     "statutConventionnelDsn": "ETAM", "startDate": "2019-01-01"},
]
# accounting-v2 = TABLEAU NU ; employeeFullName + contractId (pas d'employeeId)
ACCOUNTING = [
    {"operationDate": "2025-01-31", "accountId": "645300",
     "accountName": "Assurance vieillesse", "debit": 1000.0, "credit": None,
     "employeeFullName": "Alice Martin", "contractId": "ct_1",
     "analyticCodes": [{"type": "Section", "code": "RD", "value": "R&D"}]},
    {"operationDate": "2025-01-31", "accountId": "645400", "accountName": "APEC",
     "debit": 50.0, "credit": None, "employeeFullName": "Alice Martin",
     "contractId": "ct_1", "analyticCodes": []},
    {"operationDate": "2025-01-31", "accountId": "645500", "accountName": "FNAL",
     "debit": 30.0, "credit": None, "employeeFullName": "Alice Martin",
     "contractId": "ct_1", "analyticCodes": []},
    {"operationDate": "2025-01-31", "accountId": "645300",
     "accountName": "Assurance vieillesse", "debit": 800.0, "credit": None,
     "employeeFullName": "Bob Durand", "contractId": "ct_2", "analyticCodes": []},
    {"operationDate": "2025-01-31", "accountId": "431000",
     "accountName": "URSSAF à payer", "debit": None, "credit": 1880.0,
     "employeeFullName": None, "contractId": None, "analyticCodes": []},
]


def _transport(path, params):
    if path == "/introspect":
        return {"company_id": "comp_1"}
    if path.endswith("/collaborators"):
        return {"collaborators": COLLABORATORS, "meta": {"nextPageToken": None}}
    if path.endswith("/contracts-fr") or path.endswith("/contracts"):
        return {"contracts": CONTRACTS, "meta": {"nextPageToken": None}}
    if path.endswith("/accounting-v2"):
        assert params and params.get("date") == "202501"   # format YYYYMM
        return ACCOUNTING
    raise AssertionError(f"chemin non prévu: {path}")


def _client():
    return pf.PayfitClient(transport=_transport)


def test_people_conforme_au_substrat():
    people = pf.charger_people(_client())
    assert m.PEOPLE.validate(people)
    a = people[people.nom == "Alice Martin"].iloc[0]
    assert a.emploi == "Ingénieur R&D" and a.matricule == "001"
    assert a.person_key == "ALICE MARTIN"


def test_financial_entries_conforme_au_substrat():
    fe = pf.charger_financial_entries(_client(), "2025-01")
    assert m.FINANCIAL_ENTRIES.validate(fe)
    assert fe.ligne.is_unique
    assert fe.loc[fe.libelle == "APEC", "debit"].iloc[0] == 50.0
    # analyticCodes aplati
    assert fe.loc[fe.libelle == "Assurance vieillesse", "analytique"].iloc[0] == "R&D"


def test_assiette_classe_par_doctrine_et_filtre_les_eligibles():
    client = _client()
    people = pf.charger_people(client)
    s = pf.assiette_depuis(client.accounting_v2("2025-01"), people,
                           eligibles={"ALICE MARTIN"})
    assert list(s.person_key) == ["ALICE MARTIN"]     # Bob (non éligible) exclu
    r = s.iloc[0]
    assert r["ELIGIBLE"] == 1000.0                    # Assurance vieillesse
    assert r["NON_ELIGIBLE"] == 80.0                  # APEC 50 + FNAL 30


def test_rattachement_par_contractId_si_nom_absent():
    # ligne sans employeeFullName mais avec contractId -> doit retrouver la personne
    acc = [{"operationDate": "2025-01-31", "accountId": "645300",
            "accountName": "Assurance vieillesse", "debit": 500.0, "credit": None,
            "employeeFullName": None, "contractId": "ct_1", "analyticCodes": []}]
    people = pf.charger_people(_client())
    s = pf.assiette_depuis(acc, people)
    assert s.iloc[0].person_key == "ALICE MARTIN" and s.iloc[0]["ELIGIBLE"] == 500.0


def test_introspect_fixture():
    assert _client().introspect() == "comp_1"
