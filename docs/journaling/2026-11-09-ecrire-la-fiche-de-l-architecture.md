# Écrire la fiche de l'architecture de l'application entière, avec son flux de données

- Date : 2026-11-09
- Branche : `docs/architecture-sheet`
- Issue : #511
- Fichier principal : `documentation/architecture_pour_docu.md` (neuf)
- Série : [2026-11-09-ecrire-la-fiche-de-l-installation.md](2026-11-09-ecrire-la-fiche-de-l-installation.md) et
  [2026-11-08-ecrire-la-fiche-de-l-api-ia.md](2026-11-08-ecrire-la-fiche-de-l-api-ia.md).

La note couvre les commits de la branche : 9a173a8 (la fiche), ed09991 et 7707f5f (ses deux relectures), e9f47ee (cette
note), ab082b3 (la lecture choisie), 8f036a6 (le flux le long du code), 47db667 (sa relecture), 30faf0d (les trois
schémas) et le commit qui applique la relecture des trois schémas. Les autres commits et fichiers que liste l'outil
(`src/k_b/ai_api/`, `tests/`, `README.md`, les autres fiches…) sont ceux de #495, #502, #507, #518, #526 et #164, déjà
sur `main` : ils ne sont pas de cette PR.

## Le pourquoi

Le référentiel demande une documentation technique (C17), et aucune ne décrivait l'application entière :
`docs/architecture-api-ia.md` ne couvre que l'API IA. La revue de la certif du 08/11 a demandé, pour l'oral blanc du
12/11, un diagramme de flux de données de bout en bout ; Sabine l'a ajouté au critère de fin de #511 (choix 37, le
09/11). La fiche décrit `main` : ce que le code fait, ce qui est codé sans être en ligne, et ce qui n'est pas codé.

## Le comment

### Trois schémas, du plus simple au plus détaillé

La fiche porte trois schémas, chacun dans sa section, avec les mêmes noms d'un schéma à l'autre (choix 72 de Sabine,
le 09/11) : le flux en bref, pour un lecteur qui ne connaît pas K-B, dix boîtes en mots courants, sans nom de commande
ni de fichier (`documentation/architecture_pour_docu.md:15-46`) ; le flux en détail, tracé dans le code, en deux
dessins, des sources au coffre puis les jobs en ligne et le stockage d'échange (`:47-228`) ; le déploiement sur
Azure, d'après `infra/` et `deploy.yml` : où est quoi, ce qui s'y passe, les identités et leurs rôles (`:362-453`).
Un seul dessin pour tout le flux se lisait mal : rendu en local par mermaid-cli, ses 34 flèches se croisaient, et le
groupe des sources s'étirait sur toute la largeur.

### Le flux en détail suit le chemin du code

`documentation/architecture_pour_docu.md:49-55` :

```markdown
Les deux schémas suivants suivent le chemin du code: le premier va des sources au coffre, le second montre les jobs
en ligne et le stockage d'échange. Un rectangle est une commande `kb`, un cylindre un fichier, une base ou un
conteneur, un rectangle arrondi un service extérieur ou le Mac. Une flèche est une lecture, une écriture ou un appel
que fait la commande, dans le sens où vont les données: l'API IA appelle l'API de données, et les items vont de l'API
de données à l'API IA. Un trait plein est un flux que le code fait aujourd'hui. Un trait en pointillés n'est pas
encore en ligne: il est codé, sauf si son étiquette dit « pas encore codé ». Un conteneur ou un groupe bordé de
pointillés n'est pas encore créé.
```

Le flux en détail part de chaque commande de `src/k_b/cli.py` (`RUN_BY_COMMAND`, `run_command`) et suit ses appels
jusqu'à chaque lecture et chaque écriture : fichier, base, API, modèle, coffre, conteneur. C'est la demande de Sabine
après lecture de la PR, dont la première version donnait une vue d'ensemble : une flèche du dessin doit être un appel du
code, avec son `fichier:ligne` dans le texte. Ce tracé a fait entrer ce que la vue d'ensemble ne montrait pas : les deux
fichiers d'état (choix 71), `kb create-db` et `kb migrate-database`, les purges de `kb import`, la relecture du dernier
extrait Zotero par `kb collect`, la suppression des classements remplacés par `kb write-tops`, et les commandes que
relancent les deux routines.

Dans le flux en détail, une flèche suit le sens des données, pas celui de l'appel ; le déploiement sur Azure garde
ce sens, et y ajoute deux appels sans donnée, `GET /health`. Le sens compte ici : c'est l'API IA qui
appelle l'API de données (`src/k_b/ai_api/connectors/data_api_client.py:266-270`, `send(http_client, ITEMS_PATH, …)`),
mais les items vont dans l'autre sens. La légende le dit avant le diagramme, pour qu'une flèche ne soit pas lue comme un
appel. Trois états, deux traits : la première version n'en avait que deux (« fait » et « codé »), et la relecture a
montré que l'envoi des clips depuis le Mac n'est pas codé du tout (#424). L'étiquette porte ce troisième état. Le
bord en pointillés d'un conteneur ou d'un groupe dit autre chose : la ressource elle-même n'existe pas encore en ligne.

### Le stockage d'échange : dire ce qui existe en ligne

`documentation/architecture_pour_docu.md:108-144` dessine le stockage d'échange : le conteneur `smoke-test`, le groupe
« Lecture choisie (clips, Zotero), prévue par #420 » et le conteneur `watch`. Seul `smoke-test` a un bord plein. Le
Bicep n'en crée qu'un, `infra/modules/exchange-storage.bicep:39-42` :

```bicep
// SMOKE_TEST_CONTAINER of src/k_b/core/config.py, which kb smoke-test lists.
resource smokeTestContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-06-01' = {
  parent: blobService
  name: 'smoke-test'
```

et `infra/deployment.json` ne déclare que deux apps et deux jobs, ni `kb daily-routine` ni `kb digest-watch`. Le code
qui lit les clips et écrit `watch` existe pourtant (`src/k_b/commands/job_transfers.py:38`, `mirror_the_clips` ;
`:68`, `publish_the_watch`) : d'où les flèches en pointillés. La copie de Zotero dans un job, elle, n'est pas codée :
sa place est réservée par un commentaire, `src/k_b/commands/daily_routine_command.py:50` :

```python
    # The copy of the Zotero library comes here, between the mirror and kb collect (#425).
```

Sa flèche dit donc « pas encore codé (#425) ». La lecture choisie est un groupe, à la demande de Sabine après lecture de
la PR : #420 y prévoit deux conteneurs montants, `clippings` pour les clips et `zotero` pour les copies de Zotero. Le
flux en détail nomme ce qu'ils contiennent ; le déploiement sur Azure, où une ressource se lit par son nom, ajoute le
nom du conteneur. Dessiner un seul conteneur `clippings` laissait Zotero hors du flux en ligne.

### Une description en texte qui suit le même ordre

`documentation/architecture_pour_docu.md:146-211` reprend les deux dessins en six points, les six flux du critère de
fin, dans le même ordre. C'est l'alternative textuelle d'une image (#167, RGAA) : un lecteur d'écran ne lit pas un
`flowchart` Mermaid, et le texte porte aussi les renvois `fichier:ligne` que les étiquettes du diagramme n'ont pas la
place de porter.

### Les couches : ce que les tests interdisent, pas ce qu'on souhaite

Le tableau des paquets (`documentation/architecture_pour_docu.md:237-248`) donne, pour chacun, l'interdit que tient un
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

`documentation/architecture_pour_docu.md:465-490`, « Vérifier cette fiche », donne les commandes qui retrouvent ses
faits au commit `d7e5b22` : les tests d'architecture, les sources, les routes, les 15 tables, ce qui est déclaré en
ligne. C'est le critère « chaque fait se vérifie dans le code, commande à l'appui ». La fiche date son code : `main`
à `d7e5b22`, dont `src/` et `infra/` sont ceux de `cbada1e` (`git diff --stat cbada1e d7e5b22 -- src/ infra/` vide).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Mermaid dans le `.md` | format fixé par la mission du 09/11 : GitHub le rend, le texte se relit en revue | une image : ne se relit pas ligne à ligne, se périme sans que le diff le montre |
| Trois schémas : en bref, en détail, le déploiement sur Azure | choix 72 de Sabine : un lecteur néophyte, le flux de données (C15.3), l'environnement d'exécution (C15.1) | un dessin unique : 34 flèches croisées au rendu ; deux dessins de flux sans vue simple ni vue d'Azure |
| Le chemin du code, commande par commande | demande de Sabine après lecture de la PR : une flèche est un appel du code, avec son `fichier:ligne` | la vue d'ensemble de la première version : elle sautait les fichiers d'état, les purges et les commandes que relancent les routines |
| Les deux fichiers d'état dessinés, les journaux cités seulement | choix 71 de Sabine : `collection_state.json` et `trend_reports.json` décident de ce qui circule ; aucune commande ne relit un journal, sauf la purge | dessiner les journaux : des flèches sans donnée de la veille |
| `kb create-db` et `kb migrate-database` dessinés, `kb openapi` cité | tranché par time-knight : les deux premières écrivent la base ; `kb openapi` écrit un fichier du dépôt | dessiner `kb openapi` |
| `GET /health` et les jetons de l'identité managée cités, pas dessinés | ils ne portent pas de donnée de la veille | six flèches de plus au moins, sans donnée |
| Le sens d'une flèche est celui des données, dans les trois schémas | c'est un diagramme de flux de données, la demande de la revue ; le déploiement y ajoute les deux `GET /health` | le sens des appels : l'API IA → l'API de données, à rebours des items ; seules les flèches « lance » des routines sont des appels sans donnée |
| Trois états (plein, pointillés, pointillés « pas encore codé ») | `main` a les trois ; le critère demande le stockage d'échange, en ligne pour une part seulement | tout en plein : décrirait le plan ; omettre le non-codé : le flux Mac ↔ stockage disparaîtrait |
| La lecture choisie en groupe | demande de Sabine après lecture de la PR : #420 prévoit deux conteneurs montants, `clippings` et `zotero` ; le flux en détail nomme leur contenu, le déploiement sur Azure ajoute leur nom | un seul conteneur `clippings` : Zotero disparaissait du flux en ligne |
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
| les treize commandes de `cli.py` sont tracées : dix par quatre sous-agents en lecture seule, trois par la session ; la session revérifie une cinquantaine de leurs renvois ; deux ne visaient pas l'appel : `metrics_export.py:105-112` (le refus des variables `OTEL_*`), remplacé par `:301`, trouvé par la session, et `github_client.py:155-161` (la construction du client), remplacé par `:173`, trouvé par la relecture | chaque flèche du chemin du code a sa ligne |
| les quatre blocs Mermaid rendus en local par mermaid-cli 11.17.0 : aucune erreur, PNG montrés à Sabine | la syntaxe se rend, `style` d'un sous-graphe compris |
| première relecture, en deux passes (5 constats, 3 retenus ; puis 18 et 1 de la session, tous retenus), puis seconde sur le delta (4 constats, retenus) ; relecture du flux le long du code (19 constats retenus, 47db667) ; relecture des trois schémas (22 retenus, le 23e en « Not verified ») ; toutes triées par time-knight | chaque flèche et chaque renvoi relus contre le code |

La note elle-même est dans `docs/journaling/` : c'est le seul fichier de `docs/` que la PR ajoute.

## Ce que tu dois pouvoir défendre

1. **Pourquoi la flèche va de l'API de données à l'API IA, alors que c'est l'API IA qui appelle ?** Un diagramme de
   flux de données suit les données : les items sortent de la base, passent par l'API de données, arrivent à l'API IA
   (`GET /items`, `src/k_b/ai_api/connectors/data_api_client.py:266-270`). La légende le dit
   (`documentation/architecture_pour_docu.md:52-53`).
2. **Qu'est-ce qui tourne en ligne aujourd'hui ?** Les deux API, le job `caj-kb-smoke-test` et le job
   `caj-kb-migrate-database` (`infra/deployment.json`), sur PostgreSQL et le seul conteneur `smoke-test`. Rien ne
   collecte, n'importe ni n'écrit de fiche en ligne (`documentation/architecture_pour_docu.md:457-459`).
3. **Comment sait-on que les couches sont respectées ?** Les tests de `tests/architecture/` lisent les imports de chaque
   module et échouent sur un import interdit (par exemple `tests/architecture/test_apis.py:118-121`) ; la CI les lance
   à chaque PR.
4. **Pourquoi l'API IA ne lit-elle pas la base ?** Elle ne peut importer qu'`ai_api`, `items` et `core`
   (`tests/architecture/test_apis.py:118`) : elle demande les items à l'API de données par HTTP, avec sa clé. L'accès
   à la base reste à un seul composant, en lecture seule (`src/k_b/database/engine.py:58-87`).
5. **Où est l'accessibilité des schémas ?** Sous chacun, un texte suit le même parcours : une phrase sous le flux en
   bref, six points sous le flux en détail (`documentation/architecture_pour_docu.md:146-211`), une liste sous le
   déploiement sur Azure (`:424-453`).

## Zones non vérifiées

- Le rendu sur GitHub : les quatre blocs se rendent sans erreur en local (mermaid-cli 11.17.0), pas encore vus sur
  GitHub, dont la version de Mermaid n'est pas connue.
- L'état réel d'Azure : la fiche lit le Bicep et `infra/deployment.json`, pas les ressources en ligne
  (`az … show` non lancé).
- L'intitulé de C17 est recopié du critère de fin de #511 : le référentiel lui-même, hors du dépôt, n'a pas été relu.
- La description en texte n'a pas été relue au regard de #167 (critères RGAA précis) ; elle suit le diagramme, sans
  contrôle d'accessibilité outillé.
- La seconde relecture n'a pas relancé les tests ; ils l'ont été ensuite, avant cette note (`243 passed`).

## Ce qui reste

- Les jobs `caj-kb-daily-routine` (#330) et `caj-kb-digest-watch` (#423) en ligne, avec les conteneurs et le partage
  `job-data` (#420) : les schémas passeront leurs pointillés en trait plein.
- L'envoi des clips depuis le Mac et la relecture de `watch` (#424), la copie de Zotero dans un job (#425).
- L'interface web d'E4 : elle entrera dans la fiche quand elle existera sur `main`.
