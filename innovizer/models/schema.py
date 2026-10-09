"""
Innovizer — substrat : contrats de schéma des entités du system of record.

Une entité = une table normalisée, agnostique au dispositif. Le schéma fixe
son nom, sa ou ses clés de rapprochement, ses colonnes substrat (le contrat
minimal) et sa source. Il ne porte AUCUNE colonne de décision d'éligibilité :
celles-ci sont calculées par les moteurs de doctrine qui lisent le substrat.

Principe de validation : le contrat est un SOUS-ENSEMBLE requis. Un DataFrame
conforme contient au moins les colonnes du contrat et ses clés ; il peut en
porter d'autres (enrichissements d'un moteur) sans être rejeté. C'est ce qui
permet d'ajouter un moteur Social ou IP Box sans retoucher le substrat.
"""

from dataclasses import dataclass, field


class SchemaError(ValueError):
    """Un DataFrame ne respecte pas le contrat d'une entité."""


@dataclass(frozen=True)
class Schema:
    name: str
    key: tuple               # colonnes de rapprochement
    columns: dict            # colonne -> type logique (str/int/float/date/bool)
    source: str              # d'où vient la donnée
    status: str = "wired"    # "wired" (alimenté aujourd'hui) | "planned" (famille future)
    note: str = ""

    def required(self) -> set:
        return set(self.columns) | set(self.key)

    def validate(self, df, *, strict_key=True):
        """Vérifie la présence des colonnes du contrat et des clés.
        strict_key : la ou les colonnes clés doivent être présentes ET non nulles."""
        cols = set(df.columns)
        manque = self.required() - cols
        if manque:
            raise SchemaError(
                f"{self.name}: colonnes manquantes {sorted(manque)}")
        if strict_key and len(df):          # un df vide est conforme (0 ligne = 0 violation)
            for k in self.key:
                if df[k].isna().all():
                    raise SchemaError(f"{self.name}: clé '{k}' entièrement nulle")
        return True
