"""
Innovizer — connecteur PayFit (API) -> substrat.

Ingestion par API au lieu de fichiers, vers les MÊMES schémas `models/` et avec
la MÊME doctrine que les connecteurs fichiers. Trois tirages :

    collaborators + contracts  -> people
    accounting-v2 (journal)    -> financial_entries
    accounting-v2 (par employé + détail cotisation) -> assiette CIR (via doctrine)

PÉRIMÈTRE RÉEL (confirmé sur la doc PayFit Developers)
    - Le journal de paie = 5 champs comptables (date, compte, nom, débit, crédit)
      -> c'est `financial_entries`, pas le livre de paie détaillé.
    - L'assiette par personne (exclure APEC/FNAL des éligibles) n'est possible
      par API QUE si l'admin PayFit a configuré l'export comptable
      « par employé + détail par cotisation » : alors `accounting-v2` porte un
      libellé de cotisation (name) et un employeeId par ligne. Sinon, agrégat.
    - `payslips` ne renvoie que le PDF (pas de JSON de cotisations).

NOMS DE CHAMPS : durcis sur l'OpenAPI officielle PayFit (developers.payfit.io
   /reference) — collaborators, contracts-fr, accounting-v2. Tous centralisés
   dans les dictionnaires CHAMPS_* ci-dessous. Reste à confirmer sur une vraie
   réponse : la forme de pagination et le fait que employeeFullName n'est peuplé
   que si l'export comptable PayFit est configuré « par employé ».

Testable SANS clé ni réseau : le client accepte un `transport` (callable
path,params -> json) que les tests remplissent avec des fixtures.
"""

import re
import unicodedata
import pandas as pd

from ..engines.fiscalite_recherche import assiette as eng_assiette

BASE_URL = "https://partner-api.payfit.com"
INTROSPECT_URL = "https://oauth.payfit.com/introspect"

# Noms de champs DURCIS sur l'OpenAPI officielle PayFit (developers.payfit.io
# /reference). Restent isolés ici : un seul endroit à ajuster si l'API évolue.
CHAMPS_COLLAB = dict(id="id", prenom="firstName", nom="lastName",
                     matricule="matricule")
CHAMPS_CONTRAT = dict(id="contractId", collaborateur="collaboratorId",
                      emploi="jobName", classification="statutConventionnelDsn",
                      debut="startDate")
# accounting-v2 : TABLEAU NU (pas de wrapper). Lien salarié = employeeFullName
# (+ contractId), PAS d'employeeId. analyticCodes = tableau {type,code,value}.
CHAMPS_COMPTA = dict(date="operationDate", compte="accountId",
                     libelle="accountName", debit="debit", credit="credit",
                     employe="employeeFullName", contrat="contractId",
                     analytique="analyticCodes")
# clés de liste et de pagination de l'API
_LISTE_KEYS = ("collaborators", "contracts", "items", "data", "results")


def _cle(nom) -> str:
    """person_key : même normalisation que les connecteurs fichiers."""
    s = unicodedata.normalize("NFKD", str(nom))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z\- ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().upper()


def _num(v) -> float:
    if v is None:
        return 0.0
    try:
        return round(float(str(v).replace(" ", "").replace(" ", "")
                          .replace(",", ".")), 2)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------- client

class PayfitClient:
    """Client Partner API PayFit. En prod : Bearer + introspect pour le
    company_id. En test : passer `transport=` pour servir des fixtures."""

    def __init__(self, token: str = "", company_id: str | None = None,
                 base_url: str = BASE_URL, transport=None, session=None,
                 introspect_url: str = INTROSPECT_URL):
        self.token = token
        self.company_id = company_id
        self.base_url = base_url
        self.introspect_url = introspect_url
        self._transport = transport   # callable(path, params) -> dict/list (tests)
        self._session = session       # requests.Session optionnelle (prod/tests HTTP)

    def _http(self):
        if self._session is not None:
            return self._session
        import requests  # import paresseux : les mappers restent testables sans
        return requests

    def _get(self, path: str, params: dict | None = None):
        if self._transport is not None:
            return self._transport(path, params)
        r = self._http().get(self.base_url + path, params=params, timeout=30,
                             headers={"Authorization": f"Bearer {self.token}"})
        r.raise_for_status()
        return r.json()

    def introspect(self) -> str:
        """Récupère le company_id à partir de la clé (POST /introspect)."""
        if self._transport is not None:
            self.company_id = self._transport("/introspect", None).get("company_id")
            return self.company_id
        r = self._http().post(self.introspect_url, json={"token": self.token},
                              timeout=30)
        r.raise_for_status()
        self.company_id = r.json().get("company_id")
        return self.company_id

    def _pager(self, path: str) -> list:
        """Agrège les pages. Tolère une liste nue ou {<_LISTE_KEYS>,
        meta:{nextPageToken}} (forme réelle de collaborators/contracts)."""
        out, token = [], None
        while True:
            data = self._get(path, {"nextPageToken": token} if token else None)
            if isinstance(data, list):
                out.extend(data)
                break
            out.extend(next((data[k] for k in _LISTE_KEYS if k in data), []))
            token = (data.get("meta") or {}).get("nextPageToken") \
                or data.get("nextPageToken")
            if not token:
                break
        return out

    def collaborators(self) -> list:
        return self._pager(f"/companies/{self.company_id}/collaborators")

    def contracts(self, fr: bool = True) -> list:
        """fr=True -> /contracts-fr (porte statutConventionnelDsn, idcc…)."""
        suffixe = "contracts-fr" if fr else "contracts"
        return self._pager(f"/companies/{self.company_id}/{suffixe}")

    def accounting_v2(self, mois: str) -> list:
        """mois en AAAA-MM ou AAAAMM. Renvoie un TABLEAU de lignes comptables."""
        aaaamm = str(mois).replace("-", "")[:6]
        return self._get(f"/companies/{self.company_id}/accounting-v2",
                         {"date": aaaamm})


# --------------------------------------------------------- mappers (purs)

def _analytique_txt(codes) -> str | None:
    """analyticCodes (tableau {type,code,value}) -> chaîne lisible."""
    if not codes:
        return None
    return "; ".join(str(c.get("value") or c.get("code") or "") for c in codes
                     if isinstance(c, dict)).strip("; ") or None


def people_depuis(collaborators: list, contracts: list) -> pd.DataFrame:
    """collaborators + contracts -> substrat `people`. Un contrat = une ligne ;
    l'identité vient du collaborateur rattaché. heures/coût non portés par ces
    endpoints (viennent de accounting-v2) -> None. On conserve les ids PayFit
    (collaborateur + contrat) pour rattacher ensuite les lignes comptables."""
    collab = {c.get(CHAMPS_COLLAB["id"]): c for c in (collaborators or [])}
    rows = []
    for ct in (contracts or []):
        c = collab.get(ct.get(CHAMPS_CONTRAT["collaborateur"]), {})
        nom = f"{c.get(CHAMPS_COLLAB['prenom'], '')} {c.get(CHAMPS_COLLAB['nom'], '')}".strip()
        rows.append(dict(
            person_key=_cle(nom), nom=nom,
            payfit_collaborateur=ct.get(CHAMPS_CONTRAT["collaborateur"]),
            payfit_contrat=ct.get(CHAMPS_CONTRAT["id"]),
            matricule=c.get(CHAMPS_COLLAB["matricule"]),
            emploi=ct.get(CHAMPS_CONTRAT["emploi"]),
            classification=ct.get(CHAMPS_CONTRAT["classification"]),
            debut_contrat=ct.get(CHAMPS_CONTRAT["debut"]),
            heures_travaillees=None, cout_employeur=None))
    return pd.DataFrame(rows, columns=[
        "person_key", "nom", "payfit_collaborateur", "payfit_contrat",
        "matricule", "emploi", "classification", "debut_contrat",
        "heures_travaillees", "cout_employeur"])


def financial_entries_depuis(accounting: list) -> pd.DataFrame:
    """accounting-v2 (TABLEAU NU) -> substrat `financial_entries`.
    employeeFullName / contractId / analytique conservés en enrichissement."""
    lignes = accounting if isinstance(accounting, list) else []
    rows = []
    for L in lignes:
        rows.append(dict(
            date=L.get(CHAMPS_COMPTA["date"]), journal="PAIE", piece=None,
            compte=str(L.get(CHAMPS_COMPTA["compte"], "")).strip(),
            libelle=L.get(CHAMPS_COMPTA["libelle"]),
            debit=_num(L.get(CHAMPS_COMPTA["debit"])),
            credit=_num(L.get(CHAMPS_COMPTA["credit"])),
            employe=L.get(CHAMPS_COMPTA["employe"]),
            contrat=L.get(CHAMPS_COMPTA["contrat"]),
            analytique=_analytique_txt(L.get(CHAMPS_COMPTA["analytique"]))))
    df = pd.DataFrame(rows, columns=["date", "journal", "piece", "compte",
                                     "libelle", "debit", "credit", "employe",
                                     "contrat", "analytique"])
    df.insert(0, "ligne", [f"P{i:07d}" for i in range(len(df))])
    return df


def assiette_depuis(accounting: list, people: pd.DataFrame, *,
                    eligibles: set | None = None,
                    arbitrages: dict | None = None) -> pd.DataFrame:
    """Reclasse les cotisations PATRONALES de accounting-v2 par la doctrine (sur
    le libellé `accountName`), par personne, en ne gardant que les éligibles.

    Rattachement à la personne : `employeeFullName` (normalisé en person_key),
    avec repli sur `contractId` → référentiel people. Il n'y a PAS d'employeeId
    dans l'API.

    ⚠️ Ne donne un résultat fin QUE si l'export PayFit est « par employé +
    détail par cotisation » : sinon employeeFullName est null et le libellé
    agrégé (tout en A_ARBITRER) — CONSTATÉ, jamais présumé.
    """
    fe = financial_entries_depuis(accounting)
    ct2key = dict(zip(people.get("payfit_contrat", []), people.get("person_key", [])))
    ch = fe[fe.compte.str.startswith("64")].copy()
    ch["person_key"] = ch.employe.map(lambda n: _cle(n) if n else None)
    manque = ch.person_key.isna()
    ch.loc[manque, "person_key"] = ch.loc[manque, "contrat"].map(ct2key)
    ch = ch[ch.person_key.notna()]
    if not len(ch):
        return pd.DataFrame(columns=["person_key", "ELIGIBLE", "NON_ELIGIBLE",
                                     "A_ARBITRER"])
    ch["classe"] = ch.libelle.map(lambda x: eng_assiette.classer(x, arbitrages))
    ch["montant_patronal"] = (ch.debit - ch.credit).round(2)
    if eligibles is not None:
        ch = ch[ch.person_key.isin(eligibles)]
    return (ch.pivot_table(index="person_key", columns="classe",
                           values="montant_patronal", aggfunc="sum")
            .fillna(0).reset_index())


# ------------------------------------------------------- orchestrateurs

def charger_people(client: PayfitClient) -> pd.DataFrame:
    return people_depuis(client.collaborators(), client.contracts())


def charger_financial_entries(client: PayfitClient, mois: str) -> pd.DataFrame:
    return financial_entries_depuis(client.accounting_v2(mois))


# --------------------------------------------------------------- démo (mock)
# Jeu de données factice au format RÉEL de l'API, pour jouer la chaîne
# API -> substrat -> résultats sans clé ni réseau (démo client, tests).

_DEMO_COLLAB = [
    {"id": "col_1", "firstName": "Claire", "lastName": "Dubois", "matricule": "0101"},
    {"id": "col_2", "firstName": "Marc", "lastName": "Lefevre", "matricule": "0102"},
    {"id": "col_3", "firstName": "Sophie", "lastName": "Bernard", "matricule": "0103"},
    {"id": "col_4", "firstName": "Paul", "lastName": "Girard", "matricule": "0104"},
]
_DEMO_CONTRACTS = [
    {"contractId": "ct_1", "collaboratorId": "col_1", "jobName": "Ingénieur R&D",
     "statutConventionnelDsn": "Cadre", "startDate": "2021-03-01"},
    {"contractId": "ct_2", "collaboratorId": "col_2", "jobName": "Technicien d'essais",
     "statutConventionnelDsn": "ETAM", "startDate": "2022-09-01"},
    {"contractId": "ct_3", "collaboratorId": "col_3", "jobName": "Chercheuse",
     "statutConventionnelDsn": "Cadre", "startDate": "2020-01-06"},
    {"contractId": "ct_4", "collaboratorId": "col_4", "jobName": "Comptable",
     "statutConventionnelDsn": "ETAM", "startDate": "2019-05-02"},
]


def _demo_cotisations(nom, contrat, cadre):
    """Lignes de charges patronales type pour un salarié (format accounting-v2)."""
    rd = [{"type": "Section", "code": "RD", "value": "R&D"}]
    lignes = [
        ("645300", "Assurance vieillesse", 980.0),   # ELIGIBLE
        ("645100", "URSSAF Maladie", 310.0),          # A_ARBITRER
        ("645500", "FNAL", 28.0),                     # NON_ELIGIBLE
        ("647500", "Titres restaurant", 90.0),        # A_ARBITRER
    ]
    if cadre:
        lignes.append(("645400", "APEC", 12.0))       # NON_ELIGIBLE (cadres)
    return [dict(operationDate="2025-01-31", accountId=cpt, accountName=lib,
                 debit=mt, credit=None, employeeFullName=nom, contractId=contrat,
                 analyticCodes=rd) for cpt, lib, mt in lignes]


_DEMO_ACCOUNTING = (
    _demo_cotisations("Claire Dubois", "ct_1", True)
    + _demo_cotisations("Marc Lefevre", "ct_2", False)
    + _demo_cotisations("Sophie Bernard", "ct_3", True)
    + _demo_cotisations("Paul Girard", "ct_4", False)
    + [dict(operationDate="2025-01-31", accountId="431000",
            accountName="URSSAF à payer", debit=None, credit=4800.0,
            employeeFullName=None, contractId=None, analyticCodes=[])]
)


def client_demo() -> "PayfitClient":
    """Client PayFit en mode mock : sert des données de démo au format réel."""
    def transport(path, params):
        if path == "/introspect":
            return {"company_id": "demo"}
        if path.endswith("/collaborators"):
            return {"collaborators": _DEMO_COLLAB, "meta": {"nextPageToken": None}}
        if path.endswith("/contracts-fr") or path.endswith("/contracts"):
            return {"contracts": _DEMO_CONTRACTS, "meta": {"nextPageToken": None}}
        if path.endswith("/accounting-v2"):
            return _DEMO_ACCOUNTING
        return {}
    return PayfitClient(company_id="demo", transport=transport)
