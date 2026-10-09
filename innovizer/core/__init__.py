"""
Innovizer — core : briques transverses à tous les dispositifs.

  identity  — réconciliation des identités (person_key, SIREN, projets)
  controls  — registre des contrôles de cohérence
  evidence  — Evidence Hub (registre des pièces, entité `documents`)

Elles ne portent aucune doctrine fiscale : elles servent le CIR comme elles
serviront le Social, l'IP Box ou le local.
"""
from . import identity, controls, evidence  # noqa: F401
