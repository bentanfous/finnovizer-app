"""
Innovizer — BRIQUE 01, orchestrateur.

    ENTRÉES (fichiers, pas connecteurs)
        livre de paie .xlsx  ·  bulletins .pdf  ·  suivi des temps .xlsx
        extrait fournisseurs ·  état des immobilisations  ·  CV & diplômes
        référentiels MESR CIR / CII .xlsx
                              │
                              ▼
                IDENTITÉ & RÉCONCILIATION
                              │
                              ▼
                   MODÈLE DE DONNÉES
              people · projets · fournisseurs · actifs · documents
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   PEOPLE ENGINE      SUBCONTRACTING         FIXED ASSETS
   qualification      agrément MESR          usage / dotations
   assiette           SIREN                  rattachement projet
        └─────────────────────┼─────────────────────┘
                              ▼
                        CONTRÔLES
                              ▼
                      EVIDENCE HUB
                              ▼
              PRÊT POUR LA BRIQUE 02 — PROJECT MAPPER

La brique ne décide d'aucune éligibilité. Elle reconstruit, rapproche, contrôle
et documente. Les décisions (éligibilité, défendabilité, arbitrages de
cotisations, périmètre des actifs) restent des actes de conseil, saisis dans
les colonnes prévues et tracés.
"""

from pathlib import Path
import glob as _glob
import pandas as pd

from . import config, identity, controls, evidence
from .ingest import paie as ing_paie, bulletins as ing_bul, temps as ing_tps
from .engines import people, assiette as eng_assiette, screening, subcontracting


class Brique01:
    def __init__(self, dossier: config.Dossier, cache_dir: str | None = ".cache"):
        self.d = dossier
        self.cache_dir = cache_dir
        self.data = {}
        self.ctrl = []

    # ---------------------------------------------------------- ingestion

    def charger_paie(self, chemin):
        df = ing_paie.sectionner(ing_paie.load(chemin))
        rec = ing_paie.payroll_records(df)
        agg = ing_paie.agregat_annuel(rec)
        self.data.update(paie_brut=df, paie_lignes=rec, paie_agregat=agg)
        self.ctrl.append(controls.reconciliation_paie(df, rec, agg))
        self.ctrl.append(controls.plausibilite_charges(agg, self.d))
        return self

    def charger_bulletins(self, motif):
        b = ing_bul.parse_annee(_glob.glob(motif), cache_dir=self.cache_dir)
        ref = ing_bul.referentiel_salaries(b)
        self.data.update(bulletins=b, salaries=ref)
        if "paie_agregat" in self.data:
            self.ctrl.append(controls.couverture_bulletins(
                self.data["paie_agregat"], ref))
        return self

    def charger_temps(self, motif):
        ing_tps.HEURES_PAR_JOUR = self.d.heures_par_jour
        tt = ing_tps.charger(_glob.glob(motif))
        self.data["temps"] = tt
        return self

    def charger_referentiels_mesr(self, chemin_cir, chemin_cii):
        def norm(p):
            x = pd.read_excel(p)
            x["siren"] = x["Numéro SIREN"].map(identity.cle_siren).astype("string")
            x["debut"] = pd.to_numeric(x["Début d'agrément"], errors="coerce")
            x["fin"] = pd.to_numeric(x["Fin d'agrément"], errors="coerce")
            return x
        self.data.update(mesr_cir=norm(chemin_cir), mesr_cii=norm(chemin_cii))
        return self

    # ------------------------------------------------------------ moteurs

    def moteur_personnel(self):
        ref = self.data["salaries"]
        self.data["qualification"] = people.construire(ref)
        return self

    def moteur_assiette(self):
        rec = self.data["paie_lignes"]
        cot = eng_assiette.cotisations_par_classe(rec)
        annexe = eng_assiette.construire_annexe(
            self.data["paie_agregat"], self.data["salaries"], cot,
            self.data["bulletins"])
        self.data.update(cotisations=cot, annexe=annexe,
                         classement_cotisations=eng_assiette.synthese_classement(rec))
        return self

    def moteur_projets(self, amorce=None):
        tt = self.data["temps"]
        scr = screening.screening(tt, amorce)
        self.data["screening_projets"] = scr
        proj = scr[["code_projet"]].copy()
        proj["classe"] = scr.eligibilite.map(
            lambda e: "NON_RD" if e == "NON_ELIGIBLE" else "NON_CLASSE")
        ht = None
        if "salaries" in self.data:
            ref = self.data["salaries"].copy()
            ref["person_key"] = ref.nom.map(
                lambda n: identity.cle_personne(n, self.d.alias_personnes))
            ht = ref.set_index("person_key").heures_travaillees
        q = ing_tps.quotites(tt, proj, heures_travaillees=ht)
        self.data["quotites"] = q
        keys = set(self.data["annexe"]["Nom - Prénom"].map(
            lambda n: identity.cle_personne(n, self.d.alias_personnes)))
        self.ctrl.append(controls.coherence_temps(q, keys))
        return self

    def moteur_soustraitance(self, fournisseurs: pd.DataFrame):
        s = subcontracting.screening_fournisseurs(fournisseurs)
        s["siren_norm"] = s.siren.map(identity.cle_siren).astype("string")
        cir, cii = self.data.get("mesr_cir"), self.data.get("mesr_cii")
        s[["statut_cir", "statut_cii"]] = s.siren_norm.apply(
            lambda x: pd.Series(self._verifier(x, cir, cii)))
        self.data["fournisseurs"] = s
        return self

    def _verifier(self, siren, cir, cii):
        # pd.NA n'est pas évaluable en booléen : tester explicitement
        if siren is None or pd.isna(siren) or not str(siren).strip():
            return "NO_SIREN", "NO_SIREN"
        res = []
        for ref in (cir, cii):
            if ref is None:
                res.append("NON_VERIFIE"); continue
            m = ref[ref.siren == siren]
            if m.empty:
                res.append("NOT_FOUND")
            elif ((m.debut <= self.d.exercice) & (m.fin >= self.d.exercice)).any():
                res.append("APPROVED")
            else:
                res.append("FOUND_NOT_VALID_FOR_YEAR")
        return tuple(res)

    def moteur_preuves(self, pieces: list):
        reg = evidence.registre(pieces)
        self.data["documents"] = reg
        q = self.data.get("qualification")
        if q is not None:
            q = q.copy()
            q["person_key"] = q.nom.map(
                lambda n: identity.cle_personne(n, self.d.alias_personnes))
            self.data["couverture_preuves"] = evidence.couverture(
                reg, q, "personne", "person_key")
        return self

    # ------------------------------------------------------------- sortie

    def controles(self) -> pd.DataFrame:
        return controls.executer(self.ctrl)

    def exporter(self, chemin):
        onglets = {
            "Controles": self.controles(),
            "Annexe personnel": self.data.get("annexe"),
            "Qualification": self.data.get("qualification"),
            "Classement cotisations": self.data.get("classement_cotisations"),
            "Screening projets": self.data.get("screening_projets"),
            "Quotites": self.data.get("quotites"),
            "Fournisseurs": self.data.get("fournisseurs"),
            "Documents": self.data.get("documents"),
            "Couverture preuves": self.data.get("couverture_preuves"),
        }
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(chemin, engine="openpyxl") as w:
            for nom, df in onglets.items():
                if df is not None and len(df):
                    vis = [c for c in df.columns if not str(c).startswith("_")]
                    df[vis].to_excel(w, sheet_name=nom[:31], index=False)
        return chemin
