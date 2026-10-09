"""Tests connecteur FEC -> substrat financial_entries."""
import io
import pandas as pd
import pytest

from innovizer import models as m
from innovizer.connectors import fec


def _fec_df():
    # FEC minimal : une vente (707/411) + une charge de personnel (641/421)
    return pd.DataFrame({
        "JournalCode": ["VE", "VE", "OD", "OD"],
        "EcritureNum": ["1", "1", "2", "2"],
        "EcritureDate": ["20250131", "20250131", "20250228", "20250228"],
        "CompteNum": ["411000", "707000", "641100", "421000"],
        "CompteLib": ["Clients", "Ventes", "Salaires", "Personnel"],
        "EcritureLib": ["Facture 1", "Facture 1", "Paie fév", "Paie fév"],
        "Debit": ["1200,00", "0", "50000,00", "0"],
        "Credit": ["0", "1200,00", "0", "50000,00"],
    })


def test_normalisation_cle_ligne_et_montants():
    rec = fec.financial_records(_fec_df())
    assert list(rec.columns) == ["ligne", "date", "journal", "piece",
                                 "compte", "libelle", "debit", "credit"]
    assert rec.ligne.is_unique and rec.ligne.notna().all()
    # virgule décimale correctement lue
    assert rec.loc[rec.compte == "641100", "debit"].iloc[0] == 50000.0


def test_sortie_conforme_au_substrat_financial_entries():
    """Régression (garde clé↔connecteur) : la sortie valide contre le schéma."""
    rec = fec.financial_records(_fec_df())
    assert m.FINANCIAL_ENTRIES.validate(rec)


def test_pools_par_classe_ne_garde_que_les_charges():
    rec = fec.financial_records(_fec_df())
    pools = fec.pools_par_classe(rec)
    # seule la classe 64 (charges personnel) est une charge ici ; 41/70 exclus
    assert set(pools.c2) == {"64"}
    assert pools.loc[pools.c2 == "64", "solde"].iloc[0] == 50000.0


def test_piece_non_unique_reste_colonne():
    rec = fec.financial_records(_fec_df())
    # la pièce 1 porte 2 lignes : piece n'est pas une clé, ligne l'est
    assert (rec.piece == "1").sum() == 2
