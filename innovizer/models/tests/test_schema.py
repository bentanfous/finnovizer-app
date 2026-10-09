"""Tests du substrat : contrats de schéma. `pytest innovizer/models/tests -q`"""
import pandas as pd
import pytest
from innovizer import models as m
from innovizer.models.schema import SchemaError


def test_neuf_entites():
    assert len(m.SUBSTRAT) == 9
    assert set(m.WIRED) == {"people", "payroll", "time_entries",
                            "suppliers", "fixed_assets", "documents",
                            "revenues", "financial_entries"}
    assert set(m.PLANNED) == {"real_estate"}


def test_chaque_schema_a_cle_et_statut():
    for s in m.SUBSTRAT.values():
        assert s.key, f"{s.name} sans clé"
        assert s.status in ("wired", "planned")
        assert s.source


def test_sortie_connecteur_fournisseurs_conforme_au_substrat():
    """Régression suppliers : la clé du schéma doit nommer une colonne que
    le connecteur produit réellement. Le schéma visait key=('compte',) alors
    que screening_fournisseurs ne produit jamais 'compte' — toute donnée
    conforme était rejetée. On vérifie que la sortie réelle du connecteur
    valide contre le substrat (c'est le point de passage _substrat du
    pipeline, testé hors pipeline et sans fichier externe)."""
    from innovizer.engines.fiscalite_recherche import subcontracting as sc
    out = sc.screening_fournisseurs(pd.DataFrame(
        {"libelle": ["ACME SAS", "BigCorp"], "siren": ["552100554", ""]}))
    assert m.SUPPLIERS.validate(out)


def test_sortie_connecteur_documents_conforme_au_substrat():
    """Même garde pour l'Evidence Hub : registre() -> schéma documents."""
    from innovizer.core import evidence
    reg = evidence.registre([dict(
        document_id="D1", type="cv", fichier="x.pdf", date="2025-01",
        entite="personne", cle_entite="a_b", note="")])
    assert m.DOCUMENTS.validate(reg)


def test_df_conforme_passe():
    df = pd.DataFrame([{"person_key": "A B", "mois": 1, "matricule": "001",
                        "nom": "A B", "annee": "2025", "section": "Rémunération brute (1)",
                        "rubrique": "Salaire de base", "base": 151.67,
                        "montant_salarial": 3000.0, "montant_patronal": 0.0,
                        "montant_total": 3000.0}])
    assert m.PAYROLL.validate(df)


def test_colonne_cle_manquante_rejetee():
    df = pd.DataFrame([{"mois": 1, "montant_total": 3000.0}])  # pas de person_key
    with pytest.raises(SchemaError):
        m.PAYROLL.validate(df)


def test_cle_entierement_nulle_rejetee():
    df = pd.DataFrame([{"person_key": None, "mois": 1, "matricule": "001",
                        "nom": "x", "annee": "2025", "section": "s", "rubrique": "r",
                        "base": 0.0, "montant_salarial": 0.0,
                        "montant_patronal": 0.0, "montant_total": 0.0}])
    with pytest.raises(SchemaError):
        m.PAYROLL.validate(df)


def test_colonnes_supplementaires_tolerees():
    # un moteur enrichit le substrat sans casser le contrat
    df = pd.DataFrame([{"person_key": "A B", "code_projet": "P1", "matricule": "001",
                        "jour": "02/01/2025", "nom_projet": "P1", "temps": 1.0,
                        "unite": "jours", "heures": 7.8, "mois": 1,
                        "classe": "R&D", "quotite_rd": 0.5}])  # 2 colonnes en plus
    assert m.TIME_ENTRIES.validate(df)


def test_required_inclut_cle_et_colonnes():
    assert "person_key" in m.PEOPLE.required()
    assert "cout_employeur" in m.PEOPLE.required()


def test_df_vide_conforme_accepte():
    # 0 fournisseur est un résultat valide, pas une violation de contrat
    vide = pd.DataFrame({c: [] for c in m.SUPPLIERS.required()})
    assert m.SUPPLIERS.validate(vide)
