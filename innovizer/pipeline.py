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

from . import config
from .core import identity, controls, evidence
from .connectors import (paie as ing_paie, bulletins as ing_bul,
                         temps as ing_tps, ventes as ing_ventes, fec as ing_fec)
from .engines.fiscalite_recherche import (assiette as eng_assiette, screening,
                                           subcontracting, qualification as people)
from .engines.ip_box import nexus as eng_nexus, attribution as eng_attr


class Brique01:
    def __init__(self, dossier: config.Dossier, cache_dir: str | None = ".cache"):
        self.d = dossier
        self.cache_dir = cache_dir
        self.data = {}
        self.ctrl = []

    # ---------------------------------------------------------- substrat

    def _substrat(self, nom: str, df):
        """Point de passage obligé : valide la sortie d'un connecteur contre
        le schéma de l'entité (innovizer.models) avant que les moteurs la
        lisent. Non bloquant : une non-conformité devient un contrôle ECART,
        le Data Hub se construit quand même et signale."""
        from . import models as _m
        try:
            _m.SUBSTRAT[nom].validate(df)
            statut, detail = "OK", ""
        except _m.SchemaError as e:
            statut, detail = "ECART", str(e)
        self.ctrl.append([dict(code=f"SUB-{nom}", libelle=f"conformité substrat {nom}",
                               attendu="conforme", calcule=statut, ecart=None,
                               statut=statut, detail=detail)])
        return df

    # ---------------------------------------------------------- ingestion

    def charger_paie(self, chemin):
        df = ing_paie.sectionner(ing_paie.load(chemin))
        rec = self._substrat("payroll", ing_paie.payroll_records(df))
        agg = ing_paie.agregat_annuel(rec)
        self.data.update(paie_brut=df, paie_lignes=rec, paie_agregat=agg)
        self.ctrl.append(controls.reconciliation_paie(df, rec, agg))
        self.ctrl.append(controls.plausibilite_charges(agg, self.d))
        return self

    def charger_bulletins(self, motif):
        b = ing_bul.parse_annee(_glob.glob(motif), cache_dir=self.cache_dir)
        ref = self._substrat("people", ing_bul.referentiel_salaries(b))
        self.data.update(bulletins=b, salaries=ref)
        if "paie_agregat" in self.data:
            self.ctrl.append(controls.couverture_bulletins(
                self.data["paie_agregat"], ref))
        return self

    def charger_temps(self, motif):
        ing_tps.HEURES_PAR_JOUR = self.d.heures_par_jour
        tt = self._substrat("time_entries", ing_tps.charger(_glob.glob(motif)))
        self.data["temps"] = tt
        return self

    def charger_ventes(self, motif):
        """Famille IP Box : ingère un ou plusieurs exports de ventes (7xx) et
        passe par le substrat `revenues` avant tout calcul Nexus."""
        rec = self._substrat("revenues", ing_ventes.charger(_glob.glob(motif)))
        self.data.update(revenues=rec,
                         revenues_par_nature=ing_ventes.agregat_par_nature(rec))
        return self

    def charger_fec(self, motif):
        """Ingère un ou plusieurs FEC et passe par le substrat
        `financial_entries` avant tout cadrage. Les pools de charges 6x/68x
        servent le dénominateur IP Box et la future famille Social."""
        rec = self._substrat("financial_entries", ing_fec.charger(_glob.glob(motif)))
        self.data.update(fec=rec, pools_charges=ing_fec.pools_par_classe(rec))
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
        self.data.update(cotisations=cot,
                         classement_cotisations=eng_assiette.synthese_classement(rec))
        # L'annexe personnel croise le livre de paie ET les bulletins. On ne la
        # construit que si les deux sources sont là. Avec le livre de paie seul :
        # cotisations classées, mais pas d'annexe (donc pas de projets, qui s'y
        # rattachent). Pour l'instant une seule source suffit à construire.
        if "paie_agregat" in self.data and "salaries" in self.data \
                and "bulletins" in self.data:
            self.data["annexe"] = eng_assiette.construire_annexe(
                self.data["paie_agregat"], self.data["salaries"], cot,
                self.data["bulletins"])
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

    def moteur_ip_box(self, resultat_net_ip=None, depenses_totales=None):
        """Synthèse IP Box : relit le substrat partagé (people × qualification
        pour le numérateur Nexus, revenues pour les recettes 751) et calcule
        ce que les arbitrages fournis permettent. Sans moteur_personnel au
        préalable, la qualification est absente et le numérateur vaut 0 —
        constaté, jamais présumé."""
        self.data["ip_box"] = eng_nexus.synthese(
            self.data.get("revenues"),
            self.data.get("salaries"),
            self.data.get("qualification"),
            resultat_net_ip=resultat_net_ip,
            depenses_totales=depenses_totales)
        return self

    def moteur_ip_box_actifs(self, actifs, map_projets, *,
                             recettes_explicites=None, map_recettes_lignes=None,
                             depenses_totales_par_actif=None,
                             resultat_net_par_actif=None):
        """Synthèse IP Box PAR ACTIF. Réutilise le substrat partagé pour la
        R&D (temps × quotités × coût × qualification, réparti projet→actif) ;
        l'attribution des recettes et les dénominateurs/résultats nets restent
        des arbitrages de conseil. Ce qui n'est pas rattaché sort en TO_REVIEW
        et les projets non mappés sont constatés (contrôle IPB-actifs)."""
        cle = lambda n: identity.cle_personne(n, self.d.alias_personnes)
        cout = eng_attr.cout_eligible_par_personne(
            self.data["salaries"], self.data["qualification"], cle)
        rd = eng_attr.rd_eligible_par_actif(
            self.data["temps"], cout, map_projets)
        rec = eng_attr.recettes_par_actif(
            self.data.get("revenues"), explicites=recettes_explicites,
            map_lignes=map_recettes_lignes)
        actifs_df = actifs if isinstance(actifs, pd.DataFrame) else pd.DataFrame(actifs)
        synth = eng_attr.synthese_par_actif(
            actifs_df, rd["par_actif"], rec,
            depenses_totales=depenses_totales_par_actif,
            resultat_net=resultat_net_par_actif)
        self.data.update(ip_box_actifs=synth, ip_box_rd_detail=rd["detail"])

        nm = rd["projets_non_mappes"]
        self.ctrl.append([dict(
            code="IPB-actifs", libelle="rattachement projets→actifs IP Box",
            attendu="tous les projets R&D mappés",
            calcule=f"{len(nm)} projet(s) non mappé(s)",
            ecart=len(nm),
            statut="OK" if not nm else "A_ARBITRER",
            detail="; ".join(nm))])
        return self

    def moteur_soustraitance(self, fournisseurs: pd.DataFrame):
        s = self._substrat("suppliers", subcontracting.screening_fournisseurs(fournisseurs))
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
        reg = self._substrat("documents", evidence.registre(pieces))
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
            "Revenues par nature": self.data.get("revenues_par_nature"),
            "IP Box Nexus": self.data.get("ip_box"),
            "IP Box par actif": self.data.get("ip_box_actifs"),
            "Pools charges FEC": self.data.get("pools_charges"),
        }
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(chemin, engine="openpyxl") as w:
            for nom, df in onglets.items():
                if df is not None and len(df):
                    vis = [c for c in df.columns if not str(c).startswith("_")]
                    df[vis].to_excel(w, sheet_name=nom[:31], index=False)
        return chemin
