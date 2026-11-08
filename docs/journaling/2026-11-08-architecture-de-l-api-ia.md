# L'architecture de l'API IA, en un document

- **Date** : 2026-11-08
- **Branche** : `docs/ai-api-architecture`
- **Issue** : #279
- **Fichiers principaux** : `docs/architecture-api-ia.md` (nouveau), `README.md`, `docs/fiches-veille.md`
- **Série** : fait suite à [Ranger l'API IA par rôle](2026-10-18-ranger-l-api-ia-par-role.md) (#242), dont il
  montre les couches.

## Le pourquoi

L'API IA s'est construite issue après issue : les fiches (#156), les tendances (#364 à #370), les traces (#345),
puis la mise en ligne (#414). Ses contrats sont écrits, dans `docs/fiches-veille.md` et `docs/tendances.md`. Il
manquait une vue d'ensemble : ce qui la compose, ce qu'elle appelle et qui l'appelle. La certification lit le
critère C9.8 d'E3 comme partiel sans ce document. Il sert aussi d'annexe au rapport E3 : chaque fait doit donc être
vrai dans le code, au commit cité (`56d013b`).

C'est une PR de documentation seule : aucun code ni test ne change.

## Le comment

### 1. Un document qui renvoie aux contrats au lieu de les recopier

Le document ne redit ni les schémas, ni les contrôles, ni les états nommés. Il renvoie à `fiches-veille.md` et à
`tendances.md` (`docs/architecture-api-ia.md:3-6`). Une connaissance ne vit qu'à un seul endroit (`code.md`,
« Duplication ») : si un contrat change, un seul fichier est à corriger.

### 2. Les couches viennent du test, pas d'une relecture du code

La table des 16 couches recopie `AI_API_LAYERS`, que tient un test :

```python
AI_API_LAYERS = (
    {
        "ai_api.deadline",
        "ai_api.watch_items",
```

(`tests/architecture/test_apis.py:151-155`). Le test vérifie que chaque module est dans une seule couche (`:212`)
et qu'aucun n'importe sa propre couche ni celles du dessus (`:223`). Si le code change de rangement, le test casse
avant que le document ne mente.

### 3. Les secrets : la même variable sur le Mac et en ligne

Le code lit une seule variable par secret. Seule sa source change : le `.env` sur le Mac, le coffre Key Vault en
ligne. Le Bicep fait la correspondance :

```bicep
var aiApiSecretVariables = {
  KB_AI_API_KEY_KB_DIGEST: 'kb-ai-api-key-kb-digest'
  KB_AI_API_KEY_KB_TREND_REPORT: 'kb-ai-api-key-kb-trend-report'
```

(`infra/main.bicep:136-138`). Le tableau des secrets du document met côte à côte la variable, le module qui la lit
et son secret en ligne.

### 4. Un schéma n'est jamais seul

Chaque schéma Mermaid est suivi d'une liste qui dit la même chose, avec ses `fichier:ligne`. Le critère de #279 le
demande, comme le RGAA pour la documentation publiée : un schéma est décrit par un texte (`.claude/rules/conformite.md`). Les schémas de séquence évitent les `<…>` : Mermaid peut les prendre pour des balises.

## Choix faits et options écartées

- **Un fichier nouveau, `docs/architecture-api-ia.md`**, à côté des deux contrats, nommé en français comme le reste
  de `docs/`. Écarté : une section dans `fiches-veille.md`, qui ne parle que de `POST /digests` et fait déjà
  1 900 lignes.
- **Les manques dits comme des manques** : en ligne, seul `caj-kb-smoke-test` appelle l'API IA, par `GET /health`.
  Le job `caj-kb-digest-watch` est prévu par #423, mais il n'est pas encore déclaré dans `infra/`. Formulation
  donnée par time-knight.
- **Renvois** : une ligne dans le README et une dans `fiches-veille.md`, comme le demande le critère. Écarté : un
  renvoi dans `tendances.md`, hors du critère.
- **README, deux corrections** : la phrase qui annonçait les textes de #369 comme « à venir » dit maintenant ce
  qu'ils font, à la demande de Sabine, puisque #468 les a livrés. Le paragraphe des jobs planifiés ne présente plus
  `caj-kb-daily-routine` et `caj-kb-digest-watch` comme déclarés (#330, #423) : sinon le README contredirait le
  document (tranché par time-knight).
- **La relecture** : un sous-agent neuf a vérifié chaque fait contre le code et a rendu 16 constats. Les 16 ont été
  corrigés : tranché par time-knight, sous la délégation de Sabine du 15/10. Les plus lourds : un échec de GitHub
  sur un README prive de textes tous les dépôts choisis, pas un seul ; le plafond de débit repart de zéro à chaque
  redémarrage ; l'export OTLP a trois signaux, pas deux. Une seconde relecture, sur les seules corrections, a rendu
  10 constats de plus, corrigés de même : par exemple, la phrase sur les blocs du schéma des couches disait plus
  que le code, ce qu'un contrôle AST a montré.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest tests/architecture/test_apis.py tests/architecture/test_opentelemetry.py` → 68 passed | les couches et les imports interdits que le document décrit sont tenus |
| `grep -rnE "raw_store\|writers\|write_file_atomically\|write_text\|write_bytes\|[^a-z_]open\(" src/k_b/ai_api \| wc -l` → 0 | règle 7 de `poc.md` : l'API IA n'écrit aucun fichier |
| `grep -rn "caj-kb-digest-watch" infra/` → rien | le manque écrit dans « En ligne » est réel |
| contrôle des caractères `Cc` et `Cf`, et des liens relatifs | aucun caractère invisible ; chaque lien ouvre un fichier |
| `uv run pytest` → 4035 passed, 328 deselected, sur la branche rebasée sur `56d013b` | la PR ne casse rien |

## Ce que tu dois pouvoir défendre

- **Pourquoi l'API IA ne lit-elle pas la base directement ?** Elle ne voit que ce que l'API de données lui sert, avec
  sa propre clé (`AI_DIGEST`), et elle n'a aucun droit d'écriture. C'est le moindre privilège. Un test l'interdit
  (`tests/architecture/test_apis.py:105-121`).
- **Que perd-on si l'API IA redémarre ?** Les mesures pas encore envoyées, le compteur de débit et le verrou par route
  (`ai_api/app.py:1-4`, `:80-81`). Ni une fiche ni un compte rendu : seul `kb` écrit le coffre.
- **Comment sait-on que la table des couches est juste ?** Elle recopie `AI_API_LAYERS`, et deux tests vérifient
  le code contre cette table (`tests/architecture/test_apis.py:212`, `:223`).
- **Où est la clé du modèle en ligne ?** Dans le secret `kb-llm-api-key` du coffre Key Vault. Seule l'identité de
  `ca-kb-ai-api` le lit (`infra/main.bicep:141`, `infra/README.md`, « 4. Poser les secrets »).

## Zones non vérifiées

- Le rendu des schémas Mermaid n'a pas été vu dans GitHub : la syntaxe a été relue, pas l'affichage.
- Le temps de réveil d'environ 20 s est repris de la mesure du 06/11 (`infra/README.md`). Il n'a pas été mesuré ici.

## Ce qui reste

- Déclarer le job `caj-kb-digest-watch` en ligne : #423. Le document devra alors changer sa section « En ligne ».
- Le compte rendu interprété des tests de l'API IA et de la chaîne des fiches : #280, la PR suivante.
