"""
Brique 03 — classification des réponses.

Une réponse est classée VIDE / PARTIEL / COMPLET pour l'axe interrogé, avec :
  - les critères satisfaits
  - un indicateur de vague (déclenche le challenge)
  - les preuves que la réponse mentionne
  - les projets liés cités (pour le mapper)

DEUX IMPLÉMENTATIONS, MÊME INTERFACE
  ClassifieurRegles   déterministe, sans réseau, utilisé par défaut et par
                      les tests. Volontairement conservateur : dans le doute,
                      PARTIEL. Il vaut mieux une relance de trop qu'un axe
                      marqué COMPLET à tort.
  ClassifieurLLM      délègue à un modèle via un adaptateur. Doit renvoyer le
                      même schéma. Non activé par défaut.

Le classifieur ne décide jamais de l'éligibilité. Il décide si Eva a assez
d'éléments pour passer à la question suivante.
"""

from dataclasses import dataclass, field
import re


@dataclass
class Classification:
    etat: str                       # VIDE / PARTIEL / COMPLET
    criteres_ok: list = field(default_factory=list)
    vague: bool = False
    hors_sujet: bool = False
    preuves_citees: list = field(default_factory=list)
    projets_cites: list = field(default_factory=list)
    confiance: float = 0.5
    justification: str = ""


MARQUEURS_VAGUE = [
    r"\bam[ée]liorer (les |la )?perf", r"\bplus rapide\b", r"\boptimis", r"\bmieux\b",
    r"\bplus efficace\b", r"\bmoderniser\b", r"\bà jour\b", r"\bcomme d'habitude\b",
    r"\bclassique\b", r"\bstandard\b", r"\bon a fait\b(?!.*(mesur|test|essa))",
]
MARQUEURS_VIDE = [
    r"^\s*(non|aucun|aucune|pas vraiment|je ne sais pas|rien|pas de)\b",
    r"^\s*.{0,25}$",
]
MARQUEURS_PREUVES = {
    "git": r"\bgit\b|\bcommit|\bd[ée]p[oô]t\b|\brepo\b",
    "compte-rendu": r"comptes?[- ]rendus?|\bcr\b|\bproc[eè]s[- ]verbal|\bpv\b",
    "rapport": r"\brapport", "logs": r"\blogs?\b|\btraces?\b",
    "tests": r"\bpv de test|\bplan de test|\brésultats? de test",
    "mails": r"\bmails?\b|\bcourriels?\b", "ticket": r"\bjira\b|\bticket",
    "cahier": r"cahier des charges|\bspec", "photos": r"\bphotos?\b|\bvid[ée]os?\b",
}

CRITERES = {
    "difficulte": r"difficil|complexe|impossible|on ne (savait|pouvait)|probl[eè]me|ne fonctionn",
    "contexte": r"avant|jusqu'|initial|au d[ée]part|situation",
    "solutions_examinees": r"existant|march[ée]|concurren|publication|biblio|outil|solution|librairie",
    "limites": r"ne (couvr|permet|conv)|insuffisant|limit|pas adapt|ne fonctionn",
    "incertitude": r"incertitude|ne savait pas|pas s[uû]r|impossible de savoir|on ignorait|sans garantie|risque",
    "point_precis": r"taux|pr[ée]cision|seuil|temps r[ée]el|multiplex|inf[ée]r|g[ée]n[ée]ralis|robust|converg",
    "plusieurs_approches": r"plusieurs|trois|deux|diff[ée]rentes|alternativ|autre piste|soit .* soit",
    "choix_motive": r"parce que|car|retenu|choisi|privil[ée]gi",
    "protocole": r"protocole|campagne|banc|mesur|proc[ée]dure|test|essai|roulage|capteur",
    "mesure": r"\d|indicateur|taux|%|mesur|m[ée]trique",
    "abandon": r"abandon|arr[eê]t|renonc|[ée]chec|impasse|pas march|rat[ée]",
    "raison": r"parce que|car|à cause|trop|faux positif|instable|insuffisant",
    "acquis": r"appris|compris|d[ée]sormais|on sait|valid[ée]|obten|r[ée]sultat",
    "limites": r"reste|pas encore|limit|ouvert|g[ée]n[ée]ralis|seulement",
    "personnes": r"ing[ée]nieur|d[ée]veloppeur|[ée]quipe|personne|collaborateur|docteur",
    "moyens": r"sous[- ]trait|prestataire|mat[ée]riel|banc|serveur|licence",
    "documents": r"document|rapport|compte[- ]rendu|git|commit|mail|ticket|pv|log",
    "dates": r"dat[ée]|horodat|\b20\d\d\b|janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre",
    "produit": r"produit|prototype|version|module|boîtier|application",
    "cible": r"client|utilisateur|march[ée]|flotte|v[ée]hicule",
    "offres": r"concurren|offre|march[ée]|existant",
    "criteres": r"crit[eè]re|compar|prix|perf|fonction",
    "superiorite": r"mieux|sup[ée]rieur|plus|nouveau|in[ée]dit",
    "versions": r"version|prototype|it[ée]ration|v\d",
    "changements": r"chang|modifi|revu|refait|am[ée]lior",
}


class ClassifieurRegles:
    def classer(self, axe: str, reponse: str, criteres: list,
                projets_connus: list | None = None) -> Classification:
        r = reponse.strip()
        low = r.lower()

        if any(re.search(p, low) for p in MARQUEURS_VIDE):
            return Classification("VIDE", confiance=0.9,
                                  justification="réponse absente ou trop courte")

        ok = [c for c in criteres if re.search(CRITERES.get(c, "$^"), low)]
        vague = any(re.search(p, low) for p in MARQUEURS_VAGUE) and len(ok) < len(criteres)
        preuves = [k for k, p in MARQUEURS_PREUVES.items() if re.search(p, low)]
        projets = [p for p in (projets_connus or []) if isinstance(p, str) and p.lower() in low]

        if len(ok) == len(criteres) and not vague and len(r) >= 80:
            etat, conf = "COMPLET", 0.8
        elif ok or preuves:
            etat, conf = "PARTIEL", 0.7
        else:
            etat, conf = "PARTIEL" if len(r) >= 80 else "VIDE", 0.6

        return Classification(etat, criteres_ok=ok, vague=vague,
                              preuves_citees=preuves, projets_cites=projets,
                              confiance=conf,
                              justification=f"critères {ok}/{criteres}, vague={vague}")


class ClassifieurLLM:
    """Adaptateur vers un modèle. `appel` : callable(prompt) -> str JSON."""

    SCHEMA = ('{"etat":"VIDE|PARTIEL|COMPLET","criteres_ok":[],"vague":bool,'
              '"hors_sujet":bool,"preuves_citees":[],"projets_cites":[],'
              '"confiance":0.0,"justification":""}')

    def __init__(self, appel, secours: ClassifieurRegles | None = None):
        self.appel = appel
        self.secours = secours or ClassifieurRegles()

    def classer(self, axe, reponse, criteres, projets_connus=None) -> Classification:
        import json
        prompt = (
            "Tu évalues une réponse d'entretien d'audit technique. Tu ne juges pas "
            "l'éligibilité fiscale, seulement si la réponse couvre les critères.\n"
            f"Axe : {axe}\nCritères attendus : {criteres}\n"
            f"Projets connus : {projets_connus or []}\n"
            f"Réponse : «{reponse}»\n"
            f"Réponds UNIQUEMENT en JSON selon ce schéma : {self.SCHEMA}"
        )
        try:
            brut = self.appel(prompt)
            d = json.loads(re.sub(r"```json|```", "", brut).strip())
            return Classification(**{k: d[k] for k in Classification.__dataclass_fields__
                                     if k in d})
        except Exception as e:  # noqa: BLE001 — tout échec bascule sur les règles
            c = self.secours.classer(axe, reponse, criteres, projets_connus)
            c.justification += f" [LLM indisponible : {type(e).__name__}]"
            return c
