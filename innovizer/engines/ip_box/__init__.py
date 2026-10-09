"""
Innovizer — moteurs de la famille « IP Box » (art. 238 du CGI).

L'IP Box impose au taux réduit de 10 % le résultat net de cession, concession
ou sous-concession d'actifs incorporels éligibles (brevets, logiciels protégés,
certificats d'obtention végétale…). Le résultat net imposable à 10 % est
plafonné par le RATIO NEXUS :

    base_10% = résultat_net_IP × min(1, 1,3 × dépenses_R&D_éligibles
                                           / dépenses_totales_de_l'actif)

EFFET DE RÉSEAU DE LA DONNÉE
    Le numérateur du Nexus — les dépenses de R&D engagées pour développer
    l'actif — est très largement le MÊME substrat que celui du CIR : coût
    chargé du personnel de R&D déjà qualifié (`people` × `qualification`),
    sous-traitance de R&D. Le moteur IP Box ne ré-ingère rien : il relit le
    substrat partagé. C'est l'avantage structurel d'un socle unique.

CE QUE LE MOTEUR NE DÉCIDE PAS
    Ni l'éligibilité d'un actif, ni le rattachement recette↔actif, ni le
    résultat net (quelles charges imputer), ni le dénominateur complet des
    dépenses. Ce sont des actes de conseil. Le moteur CALCULE ce que le
    substrat permet et marque TO_REVIEW tout ce qui exige un arbitrage. Le
    silence n'est jamais une éligibilité.
"""

from . import nexus, attribution

__all__ = ["nexus", "attribution"]
