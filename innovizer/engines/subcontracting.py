"""
Innovizer — Brique 01 / sous-module SOUS-TRAITANCE

Chaîne de qualification, dans cet ordre. Chaque étape est bloquante : un
prestataire qui échoue à l'une d'elles ne passe pas à la suivante.

  1. Est-ce une PRESTATION ?        (vs achat de biens, frais généraux)
  2. Est-ce de la SOUS-TRAITANCE R&D ? (nature technique de la prestation)
  3. Le prestataire est-il AGRÉÉ ?   (référentiel MESR, clé SIREN)
  4. L'agrément couvre-t-il l'ANNÉE ?
  5. La prestation se rattache-t-elle à une OPÉRATION éligible ?
  6. Dispose-t-on des PIÈCES (facture détaillée, décision d'agrément) ?

RÈGLE CARDINALE
    agréé  ≠  dépense éligible.
    Le référentiel MESR répond à l'étape 3 seulement. Les listes ouvertes du
    ministère sont explicitement INDICATIVES et non opposables à
    l'administration : elles ne remplacent pas la décision d'agrément, que le
    donneur d'ordre doit se faire remettre par le prestataire.

CLÉ D'APPARIEMENT
    Le SIREN, jamais la raison sociale. Un rapprochement par nom produit des
    faux positifs (homonymies, filiales, enseignes) et des faux négatifs
    (raison sociale ≠ nom commercial). Un extrait comptable qui ne porte pas
    le SIREN ne permet PAS de conclure : il permet seulement d'établir une
    liste de candidats à vérifier.
"""

import re
import pandas as pd

# ---------------------------------------------------------------- étape 1

CATEGORIES = {
    "FRAIS_GENERAUX": [
        r"AIR FRANCE|AIR INDIA|TRANSAVIA|AIRBNB|BOOKING|HOTEL|SNCF|RATP|UBER|"
        r"SIXT|EUROPCAR|GETAROUND|ZOOMCAR|SWIGGY|POKAWA|RESTAURANT|LECLERC|LIDL|"
        r"METRO RECEPTION|BOULANGER|PUNJAB|MAGIQUE TERRACE|SOI HOSPITALITY|"
        r"TBB HOSPITALITY|LE BIENVENU|BOWLING|SPEED PARK|LUDERIC|MDC|MAS DUCLOS",
        r"CARBURANT|TOTAL|SHELL|PEAGE|ULYS|PARKING|APCOA|LAVAGE|MIDAS|NORAUTO|"
        r"EUROMASTER|CARGLASS|CONTROL TECHNIQUE|AUTO BILAN|VAUBAN|SVD |"
        r"SUPER LUXURY CARS|PETRO BELMONT|FREE 2 MOVE|FLOTTES",
        r"AXA|ALLIANZ|MACIF|AFER|EUROP ASSISTANCE|HORIZON SANTE|GLADY|SWILE|"
        r"TRESOR PUBLIC|GREFFE|INFOGREFFE|SIAE|CHAMBRE FRANCAISE|IFCCI|BUSINESS FRANCE",
        r"FREE|SFR|BOUYGUES|OVH|REGUS|DIGIDOM|LA POSTE|DHL|FEDEX|UPS|LETMESHIP|"
        r"GEFCO|CETUP|INTEGRE TRANS|RAJA|CENPAC|FRANKEL",
        r"MICROSOFT|ADOBE|CANVA|DOCUSIGN|OPENAI|LINKEDIN|LINKEDLN|SELLSY|KASPR|"
        r"RINGOVER|QUICKTALK|PAYFIT|APOGEA|TENOR EDI|GLOBALIZATION PARTNERS|"
        r"BOOST.RH|WORKS AGENCY|A2W|PIXARPRINTING|VISTAPRINT|KORUS|GT PRINT|"
        r"GRAPHI THERMO|PRINTO|FRANCETONER|BUREAU VALLEE|IKEA|CONFORAMA|"
        r"LEROY MERLIN|ACTION|DARTY|AMAZON|CDISCOUNT|RAKUTEN|ALIBABA|BACK MARKET|"
        r"MEDIA MARKT|CROMA|SIGN-FIX|SOYOUST|EBONY|JAUNET|PENS\.COM|ETTINGER",
        r"AFNOR|AFORP|EFAP|ECE$|ECOVADIS|ASAM|ENX ASSOCIATION|IEEE|"
        r"AUTOMOTIVE TESTING EXPO|MESSE STUTTGART|LANDESMESSE|EUROPABAND|"
        r"LAGARDERE|TUNELS DE BARCELONA|SALVA ARG|LETIETI",
        r"ACA NEXIA|FACTUM LEGAL|SAVOURE NOTAIRE|CONSEIL BUREAUTIQUE|"
        r"HITECHPROS|CONTRACT FACTORY|KEYTO CONSULTING|JMB CONSEIL",
    ],
    "ACHAT_COMPOSANTS": [
        r"MOUSER|FARNELL|RS COMPONENTS|RS ELETTRONICA|DIGI ?KEY|DISTRELEC|TTI INC|"
        r"LDLC|DELL|MATERIELNET|L.ATELIER DU PORTABLE|TINDIE|DFROBOT|M5STACK|"
        r"MICROCHIP|QUECTEL|TAOGLAS|ROSENBERGER|PHOENIX MECANO|SILMID|SOYTER|"
        r"COYTER|MOUSSE ELECTRONICS|SHENZHEN|AOTAI|ROLEC|MANTELEC|"
        r"DIGITAL LOGIC|KVASER|UNIZ|TELTONIKA|1NCE|OCTOPUCELY",
    ],
    "FABRICATION_PROTO": [
        r"JLCPCB|SAFE PCB|XOMETRY|PROTOELECTRONIQUE|LA TOLERIE PLASTIQUE|"
        r"FREMACH|EMS$|SOPRINJEC|SERTIP|TOHTEM|SAVELEC",
    ],
    "LIEN_DE_DEPENDANCE": [
        r"DUNASYS GROUP|DR GROUP|INNOVIZER",
    ],
    "CANDIDAT_SOUS_TRAITANCE": [
        r"UTAC|LCIE|TRIGO|OCETA|CODIN|ALLIANCE HIGH TECH|AEROLYCE|IVANIUM|"
        r"INVENTURE|SMILE IT IS OPEN|BRIOSOFT|BEECOM|SOASTE|VERSION|ALTIUM|"
        r"INTREPID|PHYTEC|GEEKO|GEOCLIC|OPEN FLEET|NEXT MOVE|EUROCADE|ELONGO|"
        r"EMG|E D S|FIADEX|FIRE|HMF|ALTE|ATLAS|ATLA|ADVANCE|PC21|TBS SERVICES|"
        r"DEKOM|GREEN 100|KALIOU|SYLARELE|SAS NAVARRE|PIOTRAUT|TRUMER|"
        r"MAINS GAUCHE|DEVISTORE|NEST GREEN|STELLANTIS|STELLAN|RENAULT|"
        r"PEUGEOT CITROEN|MONSIEUR MICHEL DURAN|BUSITEL|CORUSCANT",
    ],
}

MOTIFS = {
    "FRAIS_GENERAUX": "frais généraux ou achat courant — hors sous-traitance R&D",
    "ACHAT_COMPOSANTS": "achat de biens (composants, matériel) — pas une prestation",
    "FABRICATION_PROTO": "fabrication / prototypage — relève le cas échéant des "
                         "dépenses de prototypes, pas de la sous-traitance agréée",
    "LIEN_DE_DEPENDANCE": "entité liée — régime spécifique, plafonds et "
                          "retraitements à appliquer",
    "CANDIDAT_SOUS_TRAITANCE": "prestation potentiellement technique — à vérifier",
}


def classer(libelle: str) -> str:
    lib = str(libelle).upper()
    for cat, motifs in CATEGORIES.items():
        for pat in motifs:
            if re.search(pat, lib):
                return cat
    return "A_QUALIFIER"


def screening_fournisseurs(df: pd.DataFrame) -> pd.DataFrame:
    """df : colonnes 'compte' et 'libelle' issues de l'extrait comptable."""
    out = df.copy()
    out["categorie"] = out.libelle.map(classer)
    out["motif"] = out.categorie.map(lambda c: MOTIFS.get(c, "non classé — à instruire"))
    out["a_verifier_mesr"] = out.categorie.isin(
        ["CANDIDAT_SOUS_TRAITANCE", "A_QUALIFIER", "LIEN_DE_DEPENDANCE",
         "FABRICATION_PROTO"])
    if "siren" not in out:
        out["siren"] = ""
    for c in ["montant_annuel", "objet_prestation", "agrement_cir",
              "agrement_cii", "validite_annee", "operation_rattachee",
              "piece_agrement", "decision"]:
        out[c] = ""
    return out.sort_values(["a_verifier_mesr", "categorie", "libelle"],
                           ascending=[False, True, True])


# ---------------------------------------------------------------- étape 3-4

STATUTS = ["APPROVED", "FOUND_NOT_VALID_FOR_YEAR", "NOT_FOUND", "NO_SIREN"]


def verifier_agrement(siren, annee, referentiel_cir, referentiel_cii):
    """Contrôle par SIREN contre les référentiels MESR chargés localement.

    referentiel_* : DataFrame avec au minimum les colonnes
        siren, designation, date_debut_agrement, date_fin_agrement

    Renvoie NO_SIREN si le SIREN est absent : on ne rapproche JAMAIS sur la
    raison sociale, même approximativement. Une absence de SIREN est une
    pièce manquante, pas un résultat négatif.
    """
    if not siren or not str(siren).strip().isdigit():
        return dict(statut="NO_SIREN", source="—",
                    detail="SIREN absent de l'extrait comptable — vérification impossible")

    s = str(siren).strip().zfill(9)
    res = {}
    for nom, ref in (("CIR", referentiel_cir), ("CII", referentiel_cii)):
        if ref is None:
            res[nom] = "NON_VERIFIE"
            continue
        m = ref[ref.siren.astype(str).str.zfill(9) == s]
        if m.empty:
            res[nom] = "NOT_FOUND"
            continue
        debut = pd.to_datetime(m.date_debut_agrement, errors="coerce")
        fin = pd.to_datetime(m.date_fin_agrement, errors="coerce")
        couvre = ((debut.dt.year <= annee) & (fin.dt.year >= annee)).any()
        res[nom] = "APPROVED" if couvre else "FOUND_NOT_VALID_FOR_YEAR"
    return dict(statut_cir=res.get("CIR"), statut_cii=res.get("CII"),
                source="MESR open data (liste indicative, non opposable)",
                detail="décision d'agrément à réclamer au prestataire")
