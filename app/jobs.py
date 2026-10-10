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
from innovizer import config
from innovizer.core import identity
from innovizer.pipeline import Brique01
from innovizer.engines.fiscalite_recherche import fiche_projet as fp
from innovizer.brique03.interview import Entretien

CATEGORIES = ["paie", "bulletins", "temps", "fournisseurs", "factures",
              "immobilisations", "cv_diplomes", "mesr_cir", "mesr_cii",
              "ventes", "fec", "actifs"]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_safe(o):
    """Rend une structure strictement sérialisable en JSON (Starlette sérialise
    avec allow_nan=False) : NaN/Inf -> None, scalaires numpy/pandas -> natifs.
    Sans ça, un seul montant NaN (fournisseur sans facture) fait planter toute
    la réponse en 500."""
    import math
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    if o is None or isinstance(o, (str, int, bool)):
        return o
    # scalaires numpy / pandas (ont .item()), pd.NA / NaT -> None
    try:
        if pd.isna(o):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(o, "item"):
        try:
            return _json_safe(o.item())
        except Exception:  # noqa: BLE001
            return str(o)
    return o


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

        # Personnel : qualifié depuis les bulletins (emploi + diplôme).
        if "salaries" in b.data:
            b.moteur_personnel()
        # Assiette cotisations : depuis le livre de paie. L'annexe (et donc les
        # projets) n'apparaît que si les bulletins sont aussi présents — mais la
        # paie seule OU les bulletins seuls suffisent à construire le Data Hub.
        if "paie_lignes" in b.data:
            b.moteur_assiette()
        if "temps" in b.data and "annexe" in b.data:
            b.moteur_projets(None)
        if self._un("fournisseurs"):
            f = self._lire_fournisseurs()
            if f is not None:
                fac = self._agreger_factures()
                if fac is not None and len(fac):
                    f = self._enrichir_par_factures(f, fac)
                b.moteur_soustraitance(f)

        # famille IP Box
        if list((self.raw / "ventes").glob("*")):
            b.charger_ventes(self._glob("ventes"))
        if list((self.raw / "fec").glob("*")):
            b.charger_fec(self._glob("fec"))
        self._construire_ip_box(b, (arbitrages or {}).get("ip_box", {}))

        self._b01 = b
        resume = _json_safe(self._resumer(b))   # NaN -> None, sinon 500 à la sérialisation
        (self.derived / "data_hub.json").write_text(
            json.dumps(resume, ensure_ascii=False, indent=2, default=str))
        # export tableur complet
        try:
            b.exporter(str(self.derived / "brique01.xlsx"))
        except Exception:  # noqa: BLE001
            pass
        return resume

    def construire_depuis_payfit(self, *, mock: bool = True, token: str = "",
                                 mois: str = "2025-01") -> dict:
        """Construit un Data Hub depuis l'API PayFit (mode mock par défaut :
        données de démo, sans clé ni réseau). Même substrat, même doctrine que
        la voie fichiers : collaborators/contracts -> qualification,
        accounting-v2 -> financial_entries + assiette classée."""
        from innovizer.connectors import payfit as pf, fec
        from innovizer.engines.fiscalite_recherche import qualification as q

        client = pf.client_demo() if mock else pf.PayfitClient(token=token)
        if not mock:
            client.introspect()

        people = pf.charger_people(client)
        acc = client.accounting_v2(mois)
        fe = pf.financial_entries_depuis(acc)

        ref = people.copy()
        ref["mois_presence"] = 12
        qual = q.construire(ref)
        assiette = pf.assiette_depuis(acc, people)      # démo : tout le monde
        pools = fec.pools_par_classe(fe)

        resume = dict(
            job=self.id, source="payfit", mock=mock, maj=_now(),
            personnel=dict(salaries=int(len(people))),
            qualification=qual.statut.value_counts().to_dict(),
            assiette_payfit=assiette.to_dict("records"),
            financial_entries=dict(lignes=int(len(fe))),
            pools_charges=pools.to_dict("records"),
            controles=[dict(code="PAYFIT", libelle="source API PayFit",
                            statut="OK" if mock else "LIVE",
                            calcule=f"{len(people)} salariés, {len(fe)} écritures",
                            attendu=None)])
        resume = _json_safe(resume)
        (self.derived / "data_hub.json").write_text(
            json.dumps(resume, ensure_ascii=False, indent=2, default=str))
        return resume

    def _construire_ip_box(self, b, cfg: dict):
        """IP Box : synthèse firm-level dès que des ventes sont présentes ;
        synthèse par actif si un fichier `actifs` et une table projet→actif
        sont fournis. Les arbitrages (résultat net, dénominateur, attribution
        des recettes) viennent de la config `ip_box` du corps de build —
        jamais présumés : sans eux, la synthèse sort en TO_REVIEW."""
        if "revenues" not in b.data:
            return
        # firm-level (toujours)
        try:
            b.moteur_ip_box(
                resultat_net_ip=cfg.get("resultat_net_ip"),
                depenses_totales=cfg.get("depenses_totales"))
        except Exception:  # noqa: BLE001
            pass
        # par actif (si référentiel + mapping projets fournis)
        actifs = self._lire_actifs()
        map_projets = cfg.get("map_projets") or {}
        if actifs is not None and len(actifs) and map_projets and "qualification" in b.data:
            try:
                b.moteur_ip_box_actifs(
                    actifs, map_projets,
                    recettes_explicites=cfg.get("recettes_explicites"),
                    map_recettes_lignes=cfg.get("map_recettes_lignes"),
                    depenses_totales_par_actif=cfg.get("depenses_totales_par_actif"),
                    resultat_net_par_actif=cfg.get("resultat_net_par_actif"))
            except Exception:  # noqa: BLE001
                pass

    def _lire_actifs(self):
        """Référentiel des actifs incorporels déclarés : colonnes actif_id,
        libelle (le reste est ignoré). Pas de fichier -> None."""
        p = self._un("actifs")
        if not p:
            return None
        try:
            df = pd.read_excel(p) if p.endswith((".xlsx", ".xls")) \
                else pd.read_csv(p, sep=None, engine="python")
        except Exception:  # noqa: BLE001
            return None
        cols = {c.lower().strip(): c for c in df.columns}
        cid = next((cols[k] for k in cols if "id" in k or "actif" in k or "ref" in k),
                   df.columns[0])
        clib = next((cols[k] for k in cols if "lib" in k or "nom" in k or "designation" in k),
                    df.columns[-1])
        return pd.DataFrame({"actif_id": df[cid].astype(str),
                             "libelle": df[clib].astype(str)})

    def _agreger_factures(self):
        """Lit les factures PDF uploadées et agrège le HT + SIREN par
        fournisseur. None s'il n'y a pas de factures."""
        pdfs = list((self.raw / "factures").glob("*.pdf"))
        if not pdfs:
            return None
        from innovizer.connectors import factures
        try:
            return factures.agreger_par_fournisseur(
                factures.charger([str(p) for p in pdfs]))
        except Exception:  # noqa: BLE001
            return None

    def _enrichir_par_factures(self, fournisseurs, agg):
        """Rattache les factures à la balance : montant HT valorisé + backfill
        du SIREN (que la balance ne porte pas). Appariement par raison sociale
        normalisée ; le SIREN de la facture rend le rapprochement MESR
        autoritaire (plus seulement candidat par nom)."""
        from innovizer.engines.fiscalite_recherche.subcontracting import normaliser_nom
        agg = agg.copy()
        agg["_cle"] = agg.fournisseur.map(normaliser_nom)
        ht = dict(zip(agg._cle, agg.montant_ht))
        sir = dict(zip(agg._cle, agg.siren))
        f = fournisseurs.copy()
        cle = f.libelle.map(normaliser_nom)
        f["montant"] = cle.map(ht)
        # backfill SIREN uniquement là où la balance n'en a pas
        sinon = cle.map(sir)
        if "siren" not in f:
            f["siren"] = None
        f["siren"] = f.siren.where(f.siren.notna() & (f.siren.astype(str) != ""), sinon)
        return f

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
        lib = next((cols[k] for k in cols if "lib" in k or "nom" in k or "fourni" in k
                    or "tiers" in k or "raison" in k), df.columns[-1])
        out = pd.DataFrame({"libelle": df[lib].astype(str)})
        sir = next((cols[k] for k in cols if "siren" in k or "siret" in k), None)
        out["siren"] = df[sir].astype(str) if sir else None
        # montant si l'extrait en porte un (total, HT, débit, solde fournisseur)
        mnt = next((cols[k] for k in cols
                    if "montant" in k or k.strip() in ("ht", "total", "debit", "débit", "solde")
                    or "ht" == k or "total" in k), None)
        if mnt:
            out["montant"] = pd.to_numeric(
                df[mnt].astype(str).str.replace(r"[^\d,.\-]", "", regex=True)
                .str.replace(",", ".", regex=False), errors="coerce")
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
            agree = f[f.agrement.str.startswith(("AGRÉÉ", "CANDIDAT"))] \
                if "agrement" in f else f.iloc[0:0]
            r["fournisseurs"] = dict(
                total=int(len(f)),
                a_verifier=int(f.a_verifier_mesr.sum()) if "a_verifier_mesr" in f else 0,
                approuves_cir=int((f.get("statut_cir") == "APPROVED").sum())
                if "statut_cir" in f else 0,
                agrees=int(len(agree)))
            # détail affichable : les fournisseurs à vérifier + tout agrément trouvé
            cols = [c for c in ["libelle", "categorie", "agrement", "montant_annuel",
                                "siren_mesr", "periode_agrement"] if c in f]
            vis = f[f.a_verifier_mesr | f.index.isin(agree.index)] if "a_verifier_mesr" in f else f
            r["fournisseurs_detail"] = vis[cols].head(100).to_dict("records")
        if "revenues_par_nature" in d:
            r["revenues"] = d["revenues_par_nature"].to_dict("records")
        if "ip_box" in d:
            r["ip_box"] = d["ip_box"].to_dict("records")
        if "ip_box_actifs" in d:
            r["ip_box_actifs"] = d["ip_box_actifs"].to_dict("records")
        if "pools_charges" in d:
            r["pools_charges"] = d["pools_charges"].to_dict("records")
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
        return _json_safe(s[s.statut_screening == "A_INSTRUIRE"].sort_values(
            "heures", ascending=False)[
            ["code_projet", "thematique_chapeau", "heures", "collaborateurs"]
        ].to_dict("records"))

    def contexte_projet(self, code_projet: str) -> dict:
        if self._b01 is None:
            raise RuntimeError("Data Hub non construit")
        ctx = fp.contexte_depuis_brique01(
            code_projet, self._b01.data, config.Dossier(client=self.id, exercice=self.exercice).alias_personnes)
        from dataclasses import asdict
        return _json_safe(asdict(ctx))

    # ------------------------------------------------------------- eva

    def _nouvel_entretien(self, code_projet, regime, interlocuteur) -> Entretien:
        alias = config.Dossier(client=self.id, exercice=self.exercice).alias_personnes
        ctx = fp.contexte_depuis_brique01(code_projet, self._b01.data, alias)
        fiche = fp.FicheProjet(contexte=ctx)
        fiche.investigation.regime_pressenti = regime
        projets = [p for p in self._b01.data["temps"].code_projet.unique().tolist()
                   if isinstance(p, str)]
        e = Entretien(fiche, projets_connus=projets, interlocuteur=interlocuteur)
        self._entretiens[e.id] = e
        return e

    def ouvrir_entretien(self, code_projet: str, regime="A_DETERMINER",
                         interlocuteur="") -> dict:
        """Mode TEXTE : consomme la première question pour l'afficher."""
        e = self._nouvel_entretien(code_projet, regime, interlocuteur)
        t = e.prochaine_question()
        from dataclasses import asdict
        return _json_safe(dict(id=e.id, ouverture=e.ouverture(), question=asdict(t)))

    def ouvrir_entretien_vocal(self, code_projet: str, regime="A_DETERMINER",
                               interlocuteur="") -> dict:
        """Mode VOIX : crée l'entretien, l'enregistre dans le pont Vapi SANS
        consommer la première question (Vapi la déclenchera au premier appel
        du webhook). Renvoie l'interview_id à passer en variable dynamique."""
        from innovizer.brique03.voice import BRIDGE
        e = self._nouvel_entretien(code_projet, regime, interlocuteur)
        BRIDGE._sessions[e.id] = e
        return dict(id=e.id, code_projet=code_projet, regime=regime)

    def repondre(self, entretien_id: str, reponse: str) -> dict:
        from dataclasses import asdict
        e = self._entretiens[entretien_id]
        cl = e.repondre(reponse)
        t = e.prochaine_question()
        self._sauver_entretien(e)
        return _json_safe(dict(classification=cl, couverture=e.couverture(),
                    question=asdict(t) if t else None, termine=e.termine()))

    def finaliser(self, entretien_id: str) -> dict:
        from dataclasses import asdict
        e = self._entretiens[entretien_id]
        f = e.finaliser()
        self._sauver_entretien(e)
        return _json_safe(asdict(f))

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
