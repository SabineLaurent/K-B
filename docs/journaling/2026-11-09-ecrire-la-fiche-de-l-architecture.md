# Écrire la fiche de l'architecture de l'application entière, avec son flux de données

- Date : 2026-11-09
- Branche : `docs/architecture-sheet`
- Issue : #511
- Fichier principal : `documentation/architecture_pour_docu.md` (neuf)
- Série : [2026-11-09-ecrire-la-fiche-de-l-installation.md](2026-11-09-ecrire-la-fiche-de-l-installation.md) et
  [2026-11-08-ecrire-la-fiche-de-l-api-ia.md](2026-11-08-ecrire-la-fiche-de-l-api-ia.md).

La note couvre les trois commits de la branche : 9a173a8 (la fiche), ed09991 (la première relecture), 7707f5f (la
seconde). Les autres commits et fichiers que liste l'outil (`src/k_b/ai_api/`, `tests/`, `README.md`, les autres
fiches…) sont ceux de #495, #502, #507, #518, #526 et #164, déjà sur `main` : ils ne sont pas de cette PR.

## Le pourquoi

Le référentiel demande une documentation technique (C17), et aucune ne décrivait l'application entière :
`docs/architecture-api-ia.md` ne couvre que l'API IA. La revue de la certif du 08/11 a demandé, pour l'oral blanc du
12/11, un diagramme de flux de données de bout en bout ; Sabine l'a ajouté au critère de fin de #511 (choix 37, le
09/11). La fiche décrit `main` : ce que le code fait, ce qui est codé sans être en ligne, et ce qui n'est pas codé.

## Le comment

### Un diagramme qui suit les données, en trois états

`documentation/architecture_pour_docu.md:17-19` :

```markdown
Les flèches suivent les données, pas les appels: l'API IA appelle l'API de données, et les items vont de l'API de
données à l'API IA. Un trait plein est un flux que le code fait aujourd'hui. Un trait en pointillés n'est pas encore
en ligne: il est codé, sauf si son étiquette dit « pas encore codé ».
```

Un diagramme de flux de données dessine ce qui circule, pas qui appelle qui. Le sens compte ici : c'est l'API IA qui
appelle l'API de données (`src/k_b/ai_api/connectors/data_api_client.py:266-270`, `send(http_client, ITEMS_PATH, …)`),
mais les items vont dans l'autre sens. La légende le dit avant le diagramme, pour qu'une flèche ne soit pas lue comme un
appel. Trois états, deux traits : la première version n'en avait que deux (« fait » et « codé »), et la relecture a
montré que l'envoi des clips depuis le Mac n'est pas codé du tout (#424). L'étiquette porte ce troisième état.

### Le stockage d'échange : dire ce qui existe en ligne

`documentation/architecture_pour_docu.md:42-51` dessine trois conteneurs, mais un seul en trait plein. Le Bicep n'en
crée qu'un, `infra/modules/exchange-storage.bicep:39-42` :

```bicep
// SMOKE_TEST_CONTAINER of src/k_b/core/config.py, which kb smoke-test lists.
resource smokeTestContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-06-01' = {
  parent: blobService
  name: 'smoke-test'
```

et `infra/deployment.json` ne déclare que deux apps et deux jobs, ni `kb daily-routine` ni `kb digest-watch`. Le code
qui lit `clippings` et écrit `watch` existe pourtant (`src/k_b/commands/job_transfers.py:38`, `mirror_the_clips` ;
`:68`, `publish_the_watch`) : d'où les pointillés. Dessiner les trois conteneurs en plein aurait décrit le plan, pas
`main`.

### Une description en texte qui suit le même ordre

`documentation/architecture_pour_docu.md:54-85` reprend le diagramme en six points, les six flux du critère de fin,
dans le même ordre. C'est l'alternative textuelle d'une image (#167, RGAA) : un lecteur d'écran ne lit pas un
`flowchart` Mermaid, et le texte porte aussi les renvois `fichier:ligne` que les étiquettes du diagramme n'ont pas la
place de porter.

### Les couches : ce que les tests interdisent, pas ce qu'on souhaite

Le tableau des paquets (`documentation/architecture_pour_docu.md:94-105`) donne, pour chacun, l'interdit que tient un
test de `tests/architecture/`, avec sa ligne. Par exemple l'API IA, `tests/architecture/test_apis.py:118-121` :

```python
def test_ai_api_imports_only_ai_api_items_and_core():
    for path in list_python_files("ai_api"):
        imported = list_imported_modules(path, find_package(path))
        assert list_forbidden_imports_of_the_ai_api(imported) == set(), path
```

Une règle d'architecture écrite sans test peut être fausse sans que rien ne le montre ; un test qui lit les imports
échoue dès qu'elle l'est. La fiche s'appuie donc sur les tests plutôt que sur `conventions.md` seul.

### Une fiche qui se vérifie

`documentation/architecture_pour_docu.md:229-254`, « Vérifier cette fiche », donne les commandes qui retrouvent ses
faits au commit `d7e5b22` : les tests d'architecture, les sources, les routes, les 15 tables, ce qui est déclaré en
ligne. C'est le critère « chaque fait se vérifie dans le code, commande à l'appui ». La fiche date son code : `main`
à `d7e5b22`, dont `src/` et `infra/` sont ceux de `cbada1e` (`git diff --stat cbada1e d7e5b22 -- src/ infra/` vide).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Mermaid dans le `.md` | format fixé par la mission du 09/11 : GitHub le rend, le texte se relit en revue | une image : ne se relit pas ligne à ligne, se périme sans que le diff le montre |
| Les flèches suivent les données | c'est un diagramme de flux de données, la demande de la revue | les flèches des appels : l'API IA → l'API de données, à rebours des items |
| Trois états (plein, pointillés, pointillés « pas encore codé ») | `main` a les trois ; le critère demande le stockage d'échange, en ligne pour une part seulement | tout en plein : décrirait le plan ; omettre le non-codé : le flux Mac ↔ stockage disparaîtrait |
| L'interface web absente | décision de Sabine du 09/11 : la fiche décrit `main`, où elle n'existe pas | la dessiner en pointillés : rien n'en est codé |
| Une seule fiche, renvois aux fiches existantes (installation, tests, API IA, livraison) | critère de fin de #511 ; deux copies divergeraient | recopier leur détail |
| Les corrections de chaque relecture en un commit | la seconde relecture porte sur le delta d'un seul commit (`9a173a8..ed09991`) | un commit par constat : 26 commits de doc pour une fiche |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `awk '/^```/{c=!c;next} !c' documentation/architecture_pour_docu.md \| grep -cE "[^ ] [:;]( \|$)"` → `0` | la ponctuation de la fiche suit le choix 30 |
| script Python : aucun caractère `Cc` ou `Cf` hors tabulation et saut de ligne | aucun caractère invisible |
| 12 liens relatifs, 12 fichiers qui existent | aucun renvoi mort |
| `git diff --stat origin/main -- docs/ README.md` → vide (avant cette note) | la fiche ne touche ni `docs/` ni le README |
| `uv run pytest tests/architecture/` → `243 passed` | les interdits du tableau des couches sont tenus à `d7e5b22` |
| première relecture, en deux passes (5 constats, 3 retenus ; puis 18 et 1 de la session, tous retenus), puis seconde sur le delta (4 constats, retenus), triées par time-knight | chaque flèche et chaque renvoi relus contre le code |

La note elle-même est dans `docs/journaling/` : c'est le seul fichier de `docs/` que la PR ajoute.

## Ce que tu dois pouvoir défendre

1. **Pourquoi la flèche va de l'API de données à l'API IA, alors que c'est l'API IA qui appelle ?** Un diagramme de
   flux de données suit les données : les items sortent de la base, passent par l'API de données, arrivent à l'API IA
   (`GET /items`, `src/k_b/ai_api/connectors/data_api_client.py:266-270`). La légende le dit
   (`documentation/architecture_pour_docu.md:17-18`).
2. **Qu'est-ce qui tourne en ligne aujourd'hui ?** Les deux API, le job `caj-kb-smoke-test` et le job
   `caj-kb-migrate-database` (`infra/deployment.json`), sur PostgreSQL et le seul conteneur `smoke-test`. Rien ne
   collecte, n'importe ni n'écrit de fiche en ligne (`documentation/architecture_pour_docu.md:221-223`).
3. **Comment sait-on que les couches sont respectées ?** Les tests de `tests/architecture/` lisent les imports de chaque
   module et échouent sur un import interdit (par exemple `tests/architecture/test_apis.py:118-121`) ; la CI les lance
   à chaque PR.
4. **Pourquoi l'API IA ne lit-elle pas la base ?** Elle ne peut importer qu'`ai_api`, `items` et `core`
   (`tests/architecture/test_apis.py:118`) : elle demande les items à l'API de données par HTTP, avec sa clé. L'accès
   à la base reste à un seul composant, en lecture seule (`src/k_b/database/engine.py:58-87`).
5. **Où est l'accessibilité du diagramme ?** Sous le diagramme, la description en six points suit les mêmes flux, dans
   le même ordre (`documentation/architecture_pour_docu.md:54-85`).

## Zones non vérifiées

- Le rendu du Mermaid sur GitHub : pas encore vu, à regarder dans la PR une fois la branche poussée.
- L'état réel d'Azure : la fiche lit le Bicep et `infra/deployment.json`, pas les ressources en ligne
  (`az … show` non lancé).
- L'intitulé de C17 est recopié du critère de fin de #511 : le référentiel lui-même, hors du dépôt, n'a pas été relu.
- La description en texte n'a pas été relue au regard de #167 (critères RGAA précis) ; elle suit le diagramme, sans
  contrôle d'accessibilité outillé.
- La seconde relecture n'a pas relancé les tests ; ils l'ont été ensuite, avant cette note (`243 passed`).

## Ce qui reste

- Les jobs `kb daily-routine` et `kb digest-watch` en ligne, avec les conteneurs `clippings` et `watch` (#420) : le
  diagramme passera leurs pointillés en trait plein.
- L'envoi des clips depuis le Mac et la relecture de `watch` (#424), la copie de Zotero dans un job (#425).
- L'interface web d'E4 : elle entrera dans la fiche quand elle existera sur `main`.
