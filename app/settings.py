"""
Innovizer Pilot — configuration d'exécution, depuis l'environnement.

Sur Railway, monter un volume sur /data et définir :
    INNOVIZER_RAW_DIR=/data/raw_uploads
    INNOVIZER_DERIVED_DIR=/data/derived
Sinon les fichiers disparaissent au redéploiement.

En local, les valeurs par défaut écrivent sous ./data.
"""

import os
from pathlib import Path

VERSION = "1.4.0"  # connecteur factures : valorisation HT + backfill SIREN (agrément confirme)

RAW_DIR = Path(os.environ.get("INNOVIZER_RAW_DIR", "./data/raw_uploads"))
DERIVED_DIR = Path(os.environ.get("INNOVIZER_DERIVED_DIR", "./data/derived"))
# alias historique accepté (compat v0.4)
if "INNOVIZER_UPLOAD_DIR" in os.environ and "INNOVIZER_DERIVED_DIR" not in os.environ:
    DERIVED_DIR = Path(os.environ["INNOVIZER_UPLOAD_DIR"])

#: les deux dossiers ont-ils été fixés explicitement (volume persistant Railway)
#: ou retombe-t-on sur ./data (éphémère, perdu au redéploiement) ?
_RAW_FROM_ENV = "INNOVIZER_RAW_DIR" in os.environ
_DERIVED_FROM_ENV = ("INNOVIZER_DERIVED_DIR" in os.environ
                     or "INNOVIZER_UPLOAD_DIR" in os.environ)

for d in (RAW_DIR, DERIVED_DIR):
    d.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("PORT", "8000"))

#: taille max d'un fichier uploadé (Mo) — les livres de paie annuels sont gros
MAX_UPLOAD_MB = int(os.environ.get("INNOVIZER_MAX_UPLOAD_MB", "50"))

# --- Eva vocale (Brique 03) --------------------------------------------------
# Clés PUBLIQUES uniquement côté client ; la clé privée Vapi ne doit jamais
# atteindre le frontend. Voir docs/eva-voice.md.
VAPI_PUBLIC_KEY = os.environ.get("VAPI_PUBLIC_KEY", "")
VAPI_ASSISTANT_ID = os.environ.get("VAPI_ASSISTANT_ID", "")
# secret partagé que Vapi renvoie dans l'en-tête du webhook custom-LLM ;
# protège l'endpoint /api/vapi/* contre les appels non authentifiés.
VAPI_WEBHOOK_SECRET = os.environ.get("VAPI_WEBHOOK_SECRET", "")

def eva_voice_config() -> dict:
    """Config publique exposée au frontend pour initialiser le widget Vapi."""
    return {"enabled": bool(VAPI_PUBLIC_KEY and VAPI_ASSISTANT_ID),
            "public_key": VAPI_PUBLIC_KEY, "assistant_id": VAPI_ASSISTANT_ID}


# --- diagnostic d'environnement ---------------------------------------------
# Expose l'état du déploiement (persistance, inscriptibilité, secrets présents
# — jamais leurs valeurs) pour /api/health : la checklist Railway se vérifie
# alors d'un coup d'œil après le déploiement.

def _inscriptible(p: Path) -> bool:
    try:
        return os.access(p, os.W_OK)
    except Exception:  # noqa: BLE001
        return False


def runtime_status() -> dict:
    persistant = bool(_RAW_FROM_ENV and _DERIVED_FROM_ENV
                      and RAW_DIR.is_absolute() and DERIVED_DIR.is_absolute())
    avert = None if persistant else (
        "stockage EPHEMERE (./data) : monter un volume Railway et definir "
        "INNOVIZER_RAW_DIR / INNOVIZER_DERIVED_DIR, sinon perte au redeploiement")
    return {
        "version": VERSION,
        "stockage": {
            "raw_dir": str(RAW_DIR), "derived_dir": str(DERIVED_DIR),
            "persistant": persistant,
            "inscriptible": _inscriptible(RAW_DIR) and _inscriptible(DERIVED_DIR),
            "avertissement": avert,
        },
        "upload_max_mb": MAX_UPLOAD_MB,
        "voix_eva": {
            "configuree": bool(VAPI_PUBLIC_KEY and VAPI_ASSISTANT_ID),
            "webhook_protege": bool(VAPI_WEBHOOK_SECRET),
        },
    }


# avertissement au démarrage si le stockage est éphémère (log Railway)
if not (_RAW_FROM_ENV and _DERIVED_FROM_ENV):
    print("[innovizer] ATTENTION stockage ephemere (./data) — "
          "monter un volume et definir INNOVIZER_RAW_DIR / INNOVIZER_DERIVED_DIR",
          flush=True)
