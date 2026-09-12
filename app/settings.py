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

VERSION = "1.0.0"

RAW_DIR = Path(os.environ.get("INNOVIZER_RAW_DIR", "./data/raw_uploads"))
DERIVED_DIR = Path(os.environ.get("INNOVIZER_DERIVED_DIR", "./data/derived"))
# alias historique accepté (compat v0.4)
if "INNOVIZER_UPLOAD_DIR" in os.environ and "INNOVIZER_DERIVED_DIR" not in os.environ:
    DERIVED_DIR = Path(os.environ["INNOVIZER_UPLOAD_DIR"])

for d in (RAW_DIR, DERIVED_DIR):
    d.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("PORT", "8000"))

#: taille max d'un fichier uploadé (Mo) — les livres de paie annuels sont gros
MAX_UPLOAD_MB = int(os.environ.get("INNOVIZER_MAX_UPLOAD_MB", "50"))
