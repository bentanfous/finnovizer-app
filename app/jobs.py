"""
Innovizer Pilot — orchestration d'un dossier de bout en bout.

Un « job » = un dossier client. On lui verse des fichiers bruts par catégorie,
puis on construit le Data Hub (Brique 01), le screening (Brique 02), et on
ouvre des entretiens Eva (Brique 03) sur les projets.

L'état d'un job est persisté en JSON sous DERIVED_DIR/<job_id>/ ; les fichiers
bruts sous RAW_DIR/<job_id>/<catégorie>/. Rien en base : un dossier de JSON se
relit, se versionne, s'audite. C'est aussi ce qui survit à un redéploiement
Railway dès lors que /data est un volume persistant.

Ce module ne contient AUCUNE règle métier : il appelle le package innovizer.
"""

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .settings import RAW_DIR, DERIVED_DIR
from innovizer import config, identity
from innovizer.pipeline import Brique01
from innovizer.engines import fiche_projet as fp
from innovizer.brique03.interview import Entretien

CATEGORIES = ["paie", "bulletins", "temps", "fournisseurs", "immobilisations",
              "cv_diplomes", "mesr_cir", "mesr_cii"]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Job:
    def __init__(self, job_id: str, client: str = "", exercice: int = 2025):
        self.id = job_id
        self.client = client
        self.exercice = exercice
        self.raw = RAW_DIR / job_id
        self.derived = DERIVED_DIR / job_id
        self.raw.mkdir(parents=True, exist_ok=True)
        self.derived.mkdir(parents=True, exist_ok=True)
        for c in CATEGORIES:
            (self.raw / c).mkdir(exist_ok=True)
        self._b01 = None
        self._entretiens: dict[str, Entretien] = {}

    # ------------------------------------------------------------- méta

    @property
    def meta_path(self):
        return self.derived / "job.json"

    def meta(self):
        return dict(id=self.id, client=self.client, exercice=self.exercice,
                    fichiers=self.inventaire(), maj=_now())

    def sauver_meta(self):
        self.meta_path.write_text(json.dumps(self.meta(), ensure_ascii=False, indent=2))

    def inventaire(self):
        return {c: sorted(p.name for p in (self.raw / c).glob("*") if p.is_file())
                for c in CATEGORIES}

    # -------------------------------------------------------- ingestion

    def ajouter_fichier(self, categorie: str, nom: str, contenu: bytes):
        if categorie not in CATEGORIES:
            raise ValueError(f"catégorie inconnue : {categorie}")
        dest = self.raw / categorie / Path(nom).name
        dest.write_bytes(contenu)
        self.sauver_meta()
        return dest

    def _un(self, categorie):
        fs = sorted((self.raw / categorie).glob("*"))
        return str(fs[0]) if fs else None

    def _glob(self, categorie, pattern="*"):
        return str(self.raw / categorie / pattern)

    # ---------------------------------------------------- brique 01+02

    def construire_data_hub(self, arbitrages: dict | None = None) -> dict:
        dossier = config.Dossier(client=self.client or self.id, exercice=self.exercice)
        b = Brique01(dossier, cache_dir=str(self.derived / ".cache"))

        if self._un("paie"):
            b.charger_paie(self._un("paie"))
        if list((self.raw / "bulletins").glob("*.pdf")):
            b.charger_bulletins(self._glob("bulletins", "*.pdf"))
        if list((self.raw / "temps").glob("*")):
            b.charger_temps(self._glob("temps"))
        if self._un("mesr_cir") and self._un("mesr_cii"):
            b.charger_referentiels_mesr(self._un("mesr_cir"), self._un("mesr_cii"))

        if "paie_lignes" in b.data:
            b.moteur_personnel()
            b.moteur_assiette()
        if "temps" in b.data and "annexe" in b.data:
            b.moteur_projets(None)
        if self._un("fournisseurs"):
            f = self._lire_fournisseurs()
            if f is not None:
                b.moteur_soustraitance(f)

        self._b01 = b
        resume = self._resumer(b)
        (self.derived / "data_hub.json").write_text(
            json.dumps(resume, ensure_ascii=False, indent=2, default=str))
        # export tableur complet
        try:
            b.exporter(str(self.derived / "brique01.xlsx"))
        except Exception:  # noqa: BLE001
            pass
        return resume

    def _lire_fournisseurs(self):
        p = self._un("fournisseurs")
        try:
            if p.endswith((".xlsx", ".xls")):
                df = pd.read_excel(p)
            else:
                df = pd.read_csv(p, sep=None, engine="python")
        except Exception:  # noqa: BLE001
            return None
        cols = {c.lower(): c for c in df.columns}
        lib = next((cols[k] for k in cols if "lib" in k or "nom" in k or "fourni" in k), df.columns[-1])
        out = pd.DataFrame({"libelle": df[lib].astype(str)})
        sir = next((cols[k] for k in cols if "siren" in k or "siret" in k), None)
        out["siren"] = df[sir].astype(str) if sir else None
        return out

    def _resumer(self, b: Brique01) -> dict:
        d = b.data
        r = dict(job=self.id, maj=_now(), controles=[])
        if "paie_agregat" in d:
            agg = d["paie_agregat"]
            r["personnel"] = dict(
                salaries=int(len(agg)),
                cout_charge=float(agg.cout_charge.sum()),
                brut=float(agg.brut_annuel.sum()))
        if "cotisations" in d:
            cot = d["cotisations"]
            r["cotisations"] = {c: float(cot[c].sum()) for c in
                                ("ELIGIBLE", "NON_ELIGIBLE", "A_ARBITRER") if c in cot}
        if "qualification" in d:
            q = d["qualification"]
            r["qualification"] = q.statut.value_counts().to_dict()
        if "screening_projets" in d:
            s = d["screening_projets"]
            r["projets"] = dict(
                total=int(len(s)),
                ecartes=int((s.statut_screening == "ECARTE_DE_FACTO").sum()),
                a_instruire=int((s.statut_screening == "A_INSTRUIRE").sum()))
        if "fournisseurs" in d:
            f = d["fournisseurs"]
            r["fournisseurs"] = dict(
                total=int(len(f)),
                a_verifier=int(f.a_verifier_mesr.sum()) if "a_verifier_mesr" in f else 0,
                approuves_cir=int((f.get("statut_cir") == "APPROVED").sum())
                if "statut_cir" in f else 0)
        try:
            c = b.controles()
            r["controles"] = c[["code", "libelle", "statut", "calcule", "attendu"]].to_dict("records")
        except Exception:  # noqa: BLE001
            pass
        return r

    # --------------------------------------------------------- projets

    def projets(self):
        if self._b01 is None:
            return []
        s = self._b01.data.get("screening_projets")
        if s is None:
            return []
        return s[s.statut_screening == "A_INSTRUIRE"].sort_values(
            "heures", ascending=False)[
            ["code_projet", "thematique_chapeau", "heures", "collaborateurs"]
        ].to_dict("records")

    def contexte_projet(self, code_projet: str) -> dict:
        if self._b01 is None:
            raise RuntimeError("Data Hub non construit")
        ctx = fp.contexte_depuis_brique01(
            code_projet, self._b01.data, config.Dossier(client=self.id, exercice=self.exercice).alias_personnes)
        from dataclasses import asdict
        return asdict(ctx)

    # ------------------------------------------------------------- eva

    def ouvrir_entretien(self, code_projet: str, regime="A_DETERMINER",
                         interlocuteur="") -> dict:
        alias = config.Dossier(client=self.id, exercice=self.exercice).alias_personnes
        ctx = fp.contexte_depuis_brique01(code_projet, self._b01.data, alias)
        fiche = fp.FicheProjet(contexte=ctx)
        fiche.investigation.regime_pressenti = regime
        projets = self._b01.data["temps"].code_projet.unique().tolist()
        e = Entretien(fiche, projets_connus=projets, interlocuteur=interlocuteur)
        self._entretiens[e.id] = e
        t = e.prochaine_question()
        from dataclasses import asdict
        return dict(id=e.id, ouverture=e.ouverture(), question=asdict(t))

    def repondre(self, entretien_id: str, reponse: str) -> dict:
        from dataclasses import asdict
        e = self._entretiens[entretien_id]
        cl = e.repondre(reponse)
        t = e.prochaine_question()
        self._sauver_entretien(e)
        return dict(classification=cl, couverture=e.couverture(),
                    question=asdict(t) if t else None, termine=e.termine())

    def finaliser(self, entretien_id: str) -> dict:
        from dataclasses import asdict
        e = self._entretiens[entretien_id]
        f = e.finaliser()
        self._sauver_entretien(e)
        return asdict(f)

    def _sauver_entretien(self, e: Entretien):
        from dataclasses import asdict
        d = self.derived / "entretiens"
        d.mkdir(exist_ok=True)
        (d / f"{e.id}.json").write_text(json.dumps(
            dict(entretien=e.export(), fiche=asdict(e.fiche)),
            ensure_ascii=False, indent=2, default=str))


class JobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def creer(self, client="", exercice=2025) -> Job:
        jid = uuid.uuid4().hex[:12]
        j = Job(jid, client, exercice)
        j.sauver_meta()
        self._jobs[jid] = j
        return j

    def get(self, jid) -> Job:
        if jid in self._jobs:
            return self._jobs[jid]
        if (DERIVED_DIR / jid / "job.json").exists():
            m = json.loads((DERIVED_DIR / jid / "job.json").read_text())
            j = Job(jid, m.get("client", ""), m.get("exercice", 2025))
            self._jobs[jid] = j
            return j
        raise KeyError(jid)

    def lister(self):
        vus = set(self._jobs)
        for p in DERIVED_DIR.glob("*/job.json"):
            vus.add(p.parent.name)
        return sorted(vus)


STORE = JobStore()
