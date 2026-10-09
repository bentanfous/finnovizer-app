"""Bulletins : mois lu dans le contenu (options 1 & 2) + agrégation par salarié
sur ses mois réellement présents (entrées/sorties en cours d'année)."""
import pandas as pd
from innovizer.connectors import bulletins as b


def test_mois_du_texte_periode_prioritaire_puis_nom():
    assert b._mois_du_texte("Début de période: 01/03/2025") == 3   # date de période
    assert b._mois_du_texte("Bulletin — Paie de septembre 2025") == 9  # repli nom
    assert b._mois_du_texte("aucun indice de mois ici") is None


def _rows(person, matricule, emploi, mois_iter, h=150.0, cout=5000.0):
    return [dict(person_key=person, nom=person, matricule=matricule, emploi=emploi,
                 categorie="Cadre", classification="3.1", debut_contrat="2020",
                 mois=m, temps_travaille_h=h, total_employeur=cout) for m in mois_iter]


def test_referentiel_agrege_sur_les_mois_presents():
    # option 1 (ou option 2 multi-fichiers) : 1 salarié sur 3 mois -> 1 ligne agrégée
    ref = b.referentiel_salaries(pd.DataFrame(_rows("A B", "1", "Ingénieur", (3, 4, 5))))
    r = ref.iloc[0]
    assert r.mois_presence == 3
    assert r.heures_travaillees == 450.0      # 3 × 150
    assert r.cout_employeur == 15000.0        # 3 × 5000


def test_referentiel_entree_en_cours_d_annee():
    # arrivé en mars : 10 mois de présence, pas 12
    ref = b.referentiel_salaries(pd.DataFrame(_rows("C D", "2", "Technicien", range(3, 13))))
    assert ref.iloc[0].mois_presence == 10


def test_referentiel_sortie_en_cours_d_annee():
    # parti en juin : 6 mois (jan→juin)
    ref = b.referentiel_salaries(pd.DataFrame(_rows("E F", "3", "Chercheur", range(1, 7))))
    assert ref.iloc[0].mois_presence == 6
