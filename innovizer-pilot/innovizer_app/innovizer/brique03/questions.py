"""
Brique 03 — banque de questions.

Chaque axe a :
  ouverture    la question de départ
  relances     ce qu'Eva demande si la réponse est PARTIELle
  challenge    ce qu'Eva oppose à une réponse vague ou hors sujet
  preuves      les pièces qu'Eva demande systématiquement sur cet axe
  criteres     ce qu'une réponse COMPLETE doit contenir (pour le classifieur)

Les formulations sont écrites pour l'oral : courtes, une idée par question,
sans jargon fiscal. Eva ne dit jamais « éligible », « CIR » ou « verrou » au
CTO ; elle parle de problème, d'incertitude, d'essais, d'échecs.
"""

QUESTIONS = {
    "probleme": dict(
        ouverture="Pour commencer, quel problème technique cherchiez-vous à résoudre "
                  "sur ce projet ? Décrivez-le comme si je ne connaissais pas votre domaine.",
        relances=[
            "Qu'est-ce qui rendait ce problème difficile, concrètement ?",
            "À quoi ressemblait la situation avant que vous ne commenciez ?",
        ],
        challenge="J'entends l'objectif, mais pas encore le problème. Qu'est-ce qui "
                  "ne fonctionnait pas, ou qu'on ne savait pas faire ?",
        preuves=["cahier des charges ou note de cadrage initiale"],
        criteres=["difficulte", "contexte"],
    ),
    "etat_art": dict(
        ouverture="Avant de démarrer, qu'avez-vous regardé de ce qui existait déjà : "
                  "solutions du marché, publications, ce que font les concurrents ?",
        relances=[
            "Pourquoi ces solutions existantes ne convenaient-elles pas ?",
            "Avez-vous testé ou évalué l'une d'elles avant de développer la vôtre ?",
        ],
        challenge="Si rien n'a été examiné, comment saviez-vous que le problème n'était "
                  "pas déjà résolu ailleurs ?",
        preuves=["note de veille datée", "comparatif de solutions"],
        criteres=["solutions_examinees", "limites"],
    ),
    "verrou": dict(
        ouverture="Qu'est-ce qui, au départ, vous empêchait d'obtenir le résultat avec "
                  "les techniques disponibles ? Qu'est-ce que vous ne saviez pas faire ?",
        relances=[
            "Y avait-il une incertitude sur le fait même d'y arriver, ou seulement "
            "sur le temps que ça prendrait ?",
            "Un ingénieur expérimenté de votre domaine, avec les outils du moment, "
            "aurait-il pu le faire directement ?",
        ],
        challenge="Une amélioration de performance ne suffit pas à caractériser une "
                  "incertitude. Quel était le point précis dont vous ne connaissiez pas "
                  "la solution ?",
        preuves=["document décrivant les difficultés anticipées"],
        criteres=["incertitude", "point_precis"],
    ),
    "hypotheses": dict(
        ouverture="Quelles pistes avez-vous envisagées pour lever cette difficulté ? "
                  "Y en avait-il plusieurs ?",
        relances=[
            "Pourquoi avoir retenu celle-là plutôt qu'une autre ?",
            "Comment avez-vous choisi par où commencer ?",
        ],
        challenge="Une seule approche envisagée dès le départ suggère que la solution "
                  "était connue. Y a-t-il eu un moment d'hésitation ?",
        preuves=["notes d'architecture", "compte-rendu de réunion de conception"],
        criteres=["plusieurs_approches", "choix_motive"],
    ),
    "essais": dict(
        ouverture="Concrètement, comment avez-vous testé ces pistes ? Décrivez-moi une "
                  "campagne d'essais.",
        relances=[
            "Quels indicateurs mesuriez-vous, et avec quels moyens ?",
            "Sur quelle période, et à quelle fréquence ?",
        ],
        challenge="Je n'entends pas de protocole. Comment saviez-vous si un essai était "
                  "réussi ou non ?",
        preuves=["PV de test", "logs horodatés", "cahier de manip"],
        criteres=["protocole", "mesure"],
    ),
    "echecs": dict(
        ouverture="Qu'est-ce qui n'a pas marché ? Quelles pistes avez-vous abandonnées, "
                  "et pourquoi ?",
        relances=[
            "À quel moment avez-vous décidé d'abandonner cette piste ?",
            "Qu'est-ce que cet échec vous a appris pour la suite ?",
        ],
        challenge="Un projet sans aucun échec ressemble à une exécution, pas à une "
                  "recherche. Vraiment aucune impasse ?",
        preuves=["compte-rendu de revue d'avancement", "tickets ou commits d'abandon"],
        criteres=["abandon", "raison"],
    ),
    "resultats": dict(
        ouverture="Où en êtes-vous aujourd'hui ? Qu'avez-vous obtenu, et qu'est-ce qui "
                  "reste ouvert ?",
        relances=[
            "Qu'avez-vous appris que vous ne saviez pas avant ?",
            "Ce résultat est-il généralisable ou limité à un cas ?",
        ],
        challenge="Un résultat est aussi une connaissance acquise. Qu'est-ce que vous "
                  "sauriez faire demain que vous ne saviez pas faire hier ?",
        preuves=["rapport technique", "démonstrateur", "mesures finales"],
        criteres=["acquis", "limites"],
    ),
    "moyens": dict(
        ouverture="Qui a travaillé sur ce projet, et avec quels moyens : sous-traitants, "
                  "matériel spécifique ?",
        relances=[
            "Les sous-traitants ont-ils réalisé des travaux de recherche ou de la "
            "prestation classique ?",
        ],
        challenge="",
        preuves=["contrats de sous-traitance", "factures détaillées"],
        criteres=["personnes", "moyens"],
    ),
    "preuves": dict(
        ouverture="Si je devais reconstituer le déroulé du projet dans deux ans, quels "
                  "documents datés pourriez-vous me montrer ?",
        relances=[
            "Où sont-ils stockés, et sont-ils horodatés ?",
            "Y a-t-il des traces écrites des décisions, pas seulement du code ?",
        ],
        challenge="Des explications orales ne se défendent pas. Quel document daté "
                  "prouve ce que vous venez de me dire ?",
        preuves=["export Git avec dates", "comptes-rendus", "rapports datés"],
        criteres=["documents", "dates"],
    ),
}

QUESTIONS_CII = {
    "produit": dict(
        ouverture="Quel produit ou prototype avez-vous conçu, et à qui est-il destiné ?",
        relances=["Quel est le périmètre exact : un produit entier, un composant ?"],
        challenge="", preuves=["spécification produit"], criteres=["produit", "cible"],
    ),
    "marche": dict(
        ouverture="Qu'est-ce qui existait sur le marché au moment où vous avez commencé ?",
        relances=["Quelles offres avez-vous comparées, et sur quels critères ?"],
        challenge="Sans comparaison de marché, comment établir la nouveauté ?",
        preuves=["benchmark concurrentiel daté"], criteres=["offres", "criteres"],
    ),
    "nouveaute": dict(
        ouverture="En quoi votre produit fait-il mieux que ce qui existait : "
                  "performances, fonctionnalités, ergonomie ?",
        relances=["Pouvez-vous chiffrer cet écart ?"],
        challenge="Différent n'est pas supérieur. Sur quel critère mesurable ?",
        preuves=["mesures comparatives"], criteres=["superiorite", "mesure"],
    ),
    "iterations": dict(
        ouverture="Combien de versions ou de prototypes avant d'arriver au résultat ?",
        relances=["Qu'est-ce qui changeait d'une version à l'autre ?"],
        challenge="", preuves=["historique des versions"], criteres=["versions", "changements"],
    ),
}

#: ordre d'entretien. Le verrou vient tôt : c'est le pivot. Les moyens
#: viennent tard parce que la Brique 01 les connaît déjà en grande partie.
ORDRE = ["probleme", "etat_art", "verrou", "hypotheses", "essais", "echecs",
         "resultats", "moyens", "preuves"]
ORDRE_CII = ["produit", "marche", "nouveaute", "iterations"]

#: question de regroupement, posée en fin d'entretien pour alimenter le mapper
QUESTION_LIENS = ("Cette difficulté que vous décrivez, l'avez-vous rencontrée sur "
                  "d'autres projets ? Lesquels ?")
