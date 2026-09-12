"""
Innovizer — chargeur de doctrine.

Les règles fiscales ne sont plus des listes Python dans les moteurs : elles
vivent dans doctrine/*.yaml, sourcées et versionnées. Ce module les charge et
expose une fonction de classification unique.

Avantages :
  - une règle porte sa source (BOFiP), son paragraphe, son niveau de certitude
  - un changement de doctrine ne touche pas le code, seulement le YAML
  - la piste d'audit peut citer la source de chaque décision de classement
  - une rubrique inconnue tombe en TO_REVIEW, jamais en éligible

Une position de dossier (client_position) reste TO_REVIEW dans le moteur
global. Elle n'est appliquée qu'après arbitrage explicite, via
`arbitrages` passé au classement — ce qui laisse une trace de la décision.
"""

import re
from pathlib import Path
from functools import lru_cache

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DOCTRINE_DIR = Path(__file__).parent


@lru_cache(maxsize=8)
def charger(nom="cir_personnel"):
    if yaml is None:
        raise RuntimeError("PyYAML requis : pip install pyyaml")
    p = DOCTRINE_DIR / f"{nom}.yaml"
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def classer_rubrique(rubrique: str, doctrine: dict,
                     arbitrages: dict | None = None) -> dict:
    """Renvoie {cir_status, source, paragraph, confidence, regle, note}.

    arbitrages : {nom_regle: 'ELIGIBLE'|'NON_ELIGIBLE'} — décisions de dossier
    qui surchargent un TO_REVIEW. Toute autre valeur reste au statut doctrinal.
    """
    r = str(rubrique)
    arbitrages = arbitrages or {}
    for nom, regle in doctrine["rules"].items():
        for pat in regle["match"]:
            if re.search(pat, r, re.I):
                statut = regle["cir_status"]
                if statut == "TO_REVIEW" and nom in arbitrages:
                    statut = arbitrages[nom]
                    origine = "arbitrage de dossier"
                else:
                    origine = regle.get("confidence", "")
                return dict(
                    cir_status=statut, regle=nom,
                    source=regle.get("source", doctrine.get("source_principale", "")),
                    paragraph=regle.get("paragraph", ""),
                    confidence=origine, note=regle.get("note", ""))
    return dict(cir_status="TO_REVIEW", regle="inconnue", source="",
                paragraph="", confidence="rubrique non référencée",
                note="rubrique absente de la doctrine — à qualifier, jamais éligible par défaut")
