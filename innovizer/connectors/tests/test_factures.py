"""Connecteur factures : nombres français, agrégation HT, backfill SIREN."""
import pandas as pd
from innovizer.connectors import factures as fa


def test_num_francais():
    assert fa._num("28 804,08") == 28804.08
    assert fa._num("3 200,00") == 3200.0
    assert fa._num("603,60") == 603.60
    assert fa._num(None) is None


def test_agreger_somme_ht_et_backfill_siren():
    df = pd.DataFrame([
        dict(fournisseur="SAVELEC", siren="325214765", numero="A",
             montant_ht=3200.0, montant_ttc=3840.0),
        dict(fournisseur="SAVELEC", siren=None, numero="B",
             montant_ht=603.60, montant_ttc=724.32),
        dict(fournisseur="SAVELEC", siren="325214765", numero="C",
             montant_ht=24003.40, montant_ttc=28804.08)])
    g = fa.agreger_par_fournisseur(df)
    r = g.iloc[0]
    assert r.fournisseur == "SAVELEC"
    assert r.montant_ht == 27807.0          # 3200 + 603,60 + 24003,40
    assert r.siren == "325214765"           # backfill depuis les factures qui l'ont
    assert r.nb_factures == 3
