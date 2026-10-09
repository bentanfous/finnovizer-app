# Eva vocale — architecture, déploiement, coûts

## Architecture B : Vapi = voix, Innovizer = cerveau

```
Interlocuteur  ⇄  Vapi (STT + voix ElevenLabs + temps réel)
                      │  à chaque tour, webhook « custom LLM »
                      ▼
        POST /api/vapi/chat/completions
                      │
                      ▼
              Moteur Eva (Brique 03)
   classement · relance · challenge · question suivante
                      │
                      ▼
          réponse = phrase exacte à prononcer
```

Vapi ne décide rien. La conduite d'entretien reste dans le moteur Eva déjà
testé : même code pour le texte et pour la voix, et toute la piste d'audit
reste côté serveur.

## Pourquoi c'est optimal en tokens

Le « LLM » que Vapi appelle, c'est notre backend. La conduite tourne sur
`ClassifieurRegles` : **déterministe, zéro token LLM**. Vapi renvoie tout
l'historique à chaque tour, mais on l'ignore et on lit l'état de session
côté serveur, donc on ne le repaye jamais.

Coût d'un audit de 30 min (~50 tours), ordres de grandeur à revérifier :

| Poste | Fourchette |
|---|---|
| Transcription (STT) | 0,10 – 0,25 $ |
| **Voix (TTS ElevenLabs)** | **0,50 – 2,00 $** ← poste dominant |
| LLM entretien | ≈ 0 (règles) ; 0,05–0,15 $ si ClassifieurLLM + cache |
| LLM synthèse finale (1 appel) | ~0,05 $ |
| Orchestration Vapi | 0,15 – 0,30 $ |
| **Total** | **≈ 0,85 – 2,75 $ / audit** |

La variable de coût est la **voix**, pas le LLM. Pour optimiser : plan volume
ElevenLabs et choix de voix.

## Configuration Vapi

1. Créer un assistant Vapi.
2. **Model** → *Custom LLM*, URL : `https://<domaine>/api/vapi/chat/completions`.
3. **Voice** → ElevenLabs, voix française posée.
4. **Transcriber** → français.
5. **First message mode** → l'assistant ne parle pas en premier (la 1re phrase
   vient du backend au premier tour).
6. Coller `docs/eva-system-prompt.txt` comme prompt système (persona/ton seuls).

## Variables d'environnement (Railway)

| Name | Rôle |
|---|---|
| `VAPI_PUBLIC_KEY` | clé publique, exposée au widget navigateur |
| `VAPI_ASSISTANT_ID` | id de l'assistant Vapi |
| `VAPI_WEBHOOK_SECRET` | secret partagé ; Vapi doit l'envoyer dans l'en-tête `x-vapi-secret` du webhook. Protège l'endpoint. |

La clé **privée** Vapi ne doit jamais atteindre le frontend.

## Flux applicatif

1. Dans l'app, sur un projet : « 🎙 Démarrer en voix ».
2. Le frontend appelle `/api/jobs/{id}/interviews/voice` → reçoit un
   `interview_id`, crée la session Eva côté serveur (sans consommer la 1re
   question).
3. Le widget Vapi démarre avec `variableValues.interview_id`.
4. À chaque tour, Vapi POSTe le webhook ; le backend renvoie la phrase d'Eva.
5. En fin d'appel, la fiche est finalisée ; « Finaliser le pré-audit » génère
   la synthèse (défendabilité, red flags, pièces à réclamer).

Sans clés Vapi, le bouton voix l'indique et l'entretien **texte** reste
pleinement fonctionnel — c'est le mode de test par défaut.

## Sécurité / RGPD

L'audio transite par Vapi et le fournisseur de voix. Avant tout entretien réel :
vérifier la localisation de traitement, informer l'interlocuteur de
l'enregistrement, et cadrer la conservation du transcript. Ceci n'est pas un
conseil juridique.
